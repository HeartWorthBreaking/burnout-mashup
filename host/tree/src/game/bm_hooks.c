/*
 * bm_hooks.c - PLATFORM-HK EXPERIMENTAL: "bmashup.hooks" v1 (include/bmashup_hooks.h, bm_hooks.h).
 *
 * The points are the marks this build already has; nothing here places code. Occurrences arrive from:
 *   PLAYER_CAR_UPDATE  the engine-point dispatcher's "ap_update" mark (bm_events.c): one observer slot, taken at close only
 *                      when a plugin registered there (player 1's car only, as bmashup.events);
 *   LOAD_DONE / RACE_EXIT / TAKEDOWN / WRECK / BOOST_AWARD
 *                      bmashup.events' delivery (bm_events_service.c), through its one sink, after its own subscribers.
 * Registration tables are written only while the plugins start (one thread, before the guest runs) and only read afterwards,
 * so dispatch takes no lock; counters are atomics. MUT=n (tests only) compiles one deliberate defect. */
#include "bm_hooks.h"

#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ai_takeover.h"
#include "bm_autopilot.h"
#include "bm_events.h"
#include "bm_events_service.h"
#include "bm_lifecycle.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0   /* 101 priority ignored, 102 no re-entry guard, 103 registers not put back, 104 flags / x87 / mmx not saved,
                   105 exclusivity not enforced, 106 late registration accepted, 107 MODIFY output not validated;
                   main18 (v2): 108 CRASH_RESULT offers MODIFY, 109 CRASH_RESULT score not copied, 110 CRASH_RESULT
                   dispatched after the stop / on re-entry;
                   main19 (v3): 130 v3 output not validated, 131 an unoffered point registers, 132 the offered roles ignored
                   (WRECK_CAUSE MODIFY without the credit path), 133 NO_CRASH accepted for any contact, 134 SOUND_LEVEL 5
                   accepted, 135 CAMERA_ADJUST roll unbounded, 136 the events twin delivered before the MODIFY step,
                   137 a proposal of another output type accepted, 138 (main21 patch 78) the SOUND_PITCH factor unbounded,
                   139 (patch 79) the CONTACT push factor unbounded */
#endif

extern ptrdiff_t g_xbox_mem_offset;

/* The MMX register file: recomp_types.h declares it for generated code only (RECOMP_GENERATED_CODE); the runtime defines the
 * registers (xbox_memory_layout.c) and saves them itself around its own interrupt routines (kernel_hal.c IrqRegs). The same
 * union, under the same guard. */
#ifndef RECOMP_MMX_DEFINED
#define RECOMP_MMX_DEFINED
typedef union RecompMmx {
    int8_t   b[8];
    uint8_t  ub[8];
    int16_t  w[4];
    uint16_t uw[4];
    int32_t  d[2];
    uint32_t ud[2];
    uint64_t q;
} RecompMmx;
#endif
extern RECOMP_TLS RecompMmx g_mm0, g_mm1, g_mm2, g_mm3;
extern RECOMP_TLS RecompMmx g_mm4, g_mm5, g_mm6, g_mm7;

#define HK_STEP     0x004A1EB4u
#define HK_NPOINT   (BM_HOOK_POINTS_V3 + 1)
#define HK_NREG     (BM_HOOK_POINTS_V3 * 2 * BM_HOOK_MAX_PER_ROLE)
#define HK_NHOST    4
#define HK_M32(va)  (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define HK_MF(va)   (*(const float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define ROLE_BIT(r) (1u << (r))

static const struct {
    const char *name;
    uint32_t roles;
} k_point[HK_NPOINT] = {
    {"", 0},
    {"PLAYER_CAR_UPDATE", ROLE_BIT(BM_HOOK_OBSERVE)},
    {"LOAD_DONE",         ROLE_BIT(BM_HOOK_OBSERVE)},
    {"RACE_EXIT",         ROLE_BIT(BM_HOOK_OBSERVE)},
    {"TAKEDOWN",          ROLE_BIT(BM_HOOK_OBSERVE)},
    {"WRECK",             ROLE_BIT(BM_HOOK_OBSERVE)},
    {"BOOST_AWARD",       ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
#if MUT == 108
    {"CRASH_RESULT",      ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},   /* defect: MODIFY without an output */
#else
    {"CRASH_RESULT",      ROLE_BIT(BM_HOOK_OBSERVE)},                              /* main18: version 2 */
#endif
    /* main19: version 3 - the roles a point CAN have; the roles offered in a run are s_offer[] (bo3_hk_offer_point) */
    {"HUD_PASS",          ROLE_BIT(BM_HOOK_OBSERVE)},
    {"CAMERA_FINAL",      ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
    {"TRAFFIC_CONTACT",   ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
    {"WRECK_CAUSE",       ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
    {"EVENT_SOUND",       ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
    {"FINISH_CAMERA",     ROLE_BIT(BM_HOOK_OBSERVE) | ROLE_BIT(BM_HOOK_MODIFY)},
};
/* main19 (v3): the output type of each MODIFY point */
static const uint32_t k_out_type[HK_NPOINT] = {
    0, 0, 0, 0, 0, 0, BM_HOOK_OUT_BOOST_AMOUNT, 0, 0, BM_HOOK_OUT_CAMERA_ADJUST, BM_HOOK_OUT_CONTACT_OUTCOME,
    BM_HOOK_OUT_WRECK_CREDIT, BM_HOOK_OUT_SOUND_LEVEL, BM_HOOK_OUT_FINISH_CAMERA
};
_Static_assert(BM_HOOK_HUD_PASS == BM_EVENT_HUD_PASS && BM_HOOK_TRAFFIC_CONTACT == BM_EVENT_TRAFFIC_CONTACT &&
               BM_HOOK_WRECK_CAUSE == BM_EVENT_WRECK_CAUSE && BM_HOOK_EVENT_SOUND == BM_EVENT_EVENT_SOUND,
               "v3 hook points are numbered as bmashup.events v7's twins");
_Static_assert(offsetof(bm_hook_ctx, hud_visible) == offsetof(bm_hook_ctx, crash_track_id) + 16,
               "bm_hook_ctx v3 fields follow the v2 fields (append-only)");
_Static_assert(offsetof(bm_hook_out, roll_rad) == offsetof(bm_hook_out, amount) + 4,
               "bm_hook_out v3 fields follow the v1 fields (append-only)");
_Static_assert(BM_HOOK_PLAYER_CAR_UPDATE == BM_EVENT_PLAYER_CAR_UPDATE && BM_HOOK_LOAD_DONE == BM_EVENT_LOAD_DONE &&
               BM_HOOK_RACE_EXIT == BM_EVENT_RACE_EXIT && BM_HOOK_TAKEDOWN == BM_EVENT_TAKEDOWN &&
               BM_HOOK_WRECK == BM_EVENT_WRECK && BM_HOOK_BOOST_AWARD == BM_EVENT_BOOST_AWARD &&
               BM_HOOK_CRASH_RESULT == BM_EVENT_CRASH_RESULT && BM_HOOK_NO_JUNCTION == BM_EVENT_NO_JUNCTION,
               "hook points are numbered as bmashup.events' events");
_Static_assert(offsetof(bm_hook_ctx, player) == offsetof(bm_hook_ctx, award_modified) + 4,
               "bm_hook_ctx v2 fields follow the v1 fields (append-only)");

typedef struct {
    td_host *host;
    bm_hook_fn fn;
    void *user;
    uint32_t point, role, flags;
    int32_t prio;
    _Atomic uint32_t calls, changed, rejected, faults;
} hk_reg;

static hk_reg s_reg[HK_NREG];
static int s_nreg;
static int s_list[HK_NPOINT][3][BM_HOOK_MAX_PER_ROLE];   /* indices into s_reg in call order */
static int s_nlist[HK_NPOINT][3];
static td_host *s_excl[HK_NPOINT][3];
static struct {
    bo3_hk_host_fn fn;
    void *user;
    _Atomic uint32_t faults;
} s_hobs[HK_NPOINT][HK_NHOST];
static int s_nhobs[HK_NPOINT];
static _Atomic uint32_t s_occ[HK_NPOINT], s_reent[HK_NPOINT], s_after[HK_NPOINT];
static uint32_t s_offer[HK_NPOINT];                      /* main19 (v3): roles offered in this run (points 8..13) */
static bo3_hk_valid_fn s_valid[HK_NPOINT];
static int s_open = 1, s_car_mark = -1, s_car_attached, s_atexit;
static _Atomic int s_stopped;
static _Thread_local int s_depth;                        /* > 0 while a bmashup.hooks callback runs on this thread */
static _Thread_local uint32_t s_boost_seq;               /* the BOOST_AWARD occurrence the observers belong to */
static _Thread_local int s_boost_live;                   /* the modify step of this add dispatched (observers may run) */

/* ---- the guest state a callback must leave as it found it ---- */

typedef struct {
    uint32_t gpr[8], seh, fs, efl;
    RecompXmm x[8];
    RecompMmx m[8];
    double fp[8];
    int top, cmp, df;
    uint16_t cw, cc;
} hk_regs;

static void save(hk_regs *r)
{
    r->gpr[0] = g_eax; r->gpr[1] = g_ebx; r->gpr[2] = g_ecx; r->gpr[3] = g_edx;
    r->gpr[4] = g_esi; r->gpr[5] = g_edi; r->gpr[6] = g_ebp; r->gpr[7] = g_esp;
    r->x[0] = g_xmm0; r->x[1] = g_xmm1; r->x[2] = g_xmm2; r->x[3] = g_xmm3;
    r->x[4] = g_xmm4; r->x[5] = g_xmm5; r->x[6] = g_xmm6; r->x[7] = g_xmm7;
    r->top = g_fp_top;
#if MUT != 104
    r->seh = g_seh_ebp; r->fs = g_fs_base; r->efl = g_eflags; r->df = g_df;
    r->m[0] = g_mm0; r->m[1] = g_mm1; r->m[2] = g_mm2; r->m[3] = g_mm3;
    r->m[4] = g_mm4; r->m[5] = g_mm5; r->m[6] = g_mm6; r->m[7] = g_mm7;
    memcpy(r->fp, g_fp_stack, sizeof r->fp);
    r->cw = g_fp_control_word; r->cmp = g_fp_cmp; r->cc = g_fp_cc;
#else
    r->seh = r->fs = r->efl = 0; r->df = r->cmp = 0; r->cw = r->cc = 0;
    memset(r->m, 0, sizeof r->m);
    memset(r->fp, 0, sizeof r->fp);
#endif
}

static int same(const hk_regs *a, const hk_regs *b)
{
    return !memcmp(a->gpr, b->gpr, sizeof a->gpr) && !memcmp(a->x, b->x, sizeof a->x) && !memcmp(a->m, b->m, sizeof a->m) &&
           !memcmp(a->fp, b->fp, sizeof a->fp) && a->seh == b->seh && a->fs == b->fs && a->efl == b->efl &&
           a->top == b->top && a->cmp == b->cmp && a->df == b->df && a->cw == b->cw && a->cc == b->cc;
}

static void restore(const hk_regs *r)
{
    g_eax = r->gpr[0]; g_ebx = r->gpr[1]; g_ecx = r->gpr[2]; g_edx = r->gpr[3];
    g_esi = r->gpr[4]; g_edi = r->gpr[5]; g_ebp = r->gpr[6]; g_esp = r->gpr[7];
    g_xmm0 = r->x[0]; g_xmm1 = r->x[1]; g_xmm2 = r->x[2]; g_xmm3 = r->x[3];
    g_xmm4 = r->x[4]; g_xmm5 = r->x[5]; g_xmm6 = r->x[6]; g_xmm7 = r->x[7];
    g_fp_top = r->top;
#if MUT != 104
    g_seh_ebp = r->seh; g_fs_base = r->fs; g_eflags = r->efl; g_df = r->df;
    g_mm0 = r->m[0]; g_mm1 = r->m[1]; g_mm2 = r->m[2]; g_mm3 = r->m[3];
    g_mm4 = r->m[4]; g_mm5 = r->m[5]; g_mm6 = r->m[6]; g_mm7 = r->m[7];
    memcpy(g_fp_stack, r->fp, sizeof r->fp);
    g_fp_control_word = r->cw; g_fp_cmp = r->cmp; g_fp_cc = r->cc;
#endif
}

/* ---- diagnostics ---- */

static const char *who(const td_host *host)
{
    const char *id = host ? bo3_plugins_host_id(host) : NULL;
    return id && id[0] ? id : "?";
}

static const char *role_name(uint32_t role)
{
    return role == BM_HOOK_OBSERVE ? "observe" : role == BM_HOOK_MODIFY ? "modify" : "?";
}

static const char *TD_CALL hk_result_text(int32_t code)
{
    static const char *const k[] = {"OK", "BAD_ARG", "UNKNOWN_POINT", "BAD_ROLE", "BAD_FLAGS", "CLOSED", "UNAVAILABLE",
                                    "ALREADY", "CONFLICT", "FULL", "NOT_OWNER"};
    return code >= 0 && code < (int32_t)(sizeof k / sizeof k[0]) ? k[code] : "UNKNOWN_RESULT";
}

/* ---- calling a registration ---- */

static int32_t call_guarded(hk_reg *r, const bm_hook_ctx *ctx, bm_hook_out *out)
{
    hk_regs before, after;
    int32_t rc;
    memset(&before, 0, sizeof before);
    memset(&after, 0, sizeof after);
    save(&before);
    rc = r->fn(ctx, out, r->user);
    atomic_fetch_add(&r->calls, 1);
    save(&after);
    if (!same(&before, &after)) {
#if MUT != 103
        restore(&before);
#endif
        if (atomic_fetch_add(&r->faults, 1) == 0)
            fprintf(stderr, "[HOOKS] %s: its %s %s callback changed guest registers or flags; put back (said once)\n",
                    who(r->host), k_point[r->point].name, role_name(r->role));
    }
    return rc;
}

/* 1 when the occurrence is dispatched; counts it either way */
static int enter(uint32_t point)
{
    atomic_fetch_add(&s_occ[point], 1);
    if (atomic_load(&s_stopped)) {
        atomic_fetch_add(&s_after[point], 1);
        return 0;
    }
#if MUT != 102
    if (s_depth) {
        atomic_fetch_add(&s_reent[point], 1);
        return 0;
    }
#endif
    return 1;
}

static void base_ctx(bm_hook_ctx *c, uint32_t point, uint32_t seq)
{
    memset(c, 0, sizeof *c);
    c->struct_size = (uint32_t)sizeof *c;
    c->point = point;
    c->sequence = seq;
    c->step = g_xbox_mem_offset ? HK_M32(HK_STEP) : 0;
    c->actor = c->victim = c->recipient = BM_HOOK_NO_RACER;
}

static void run_observers(uint32_t point, const bm_hook_ctx *base)
{
    s_depth++;
    for (int k = 0; k < s_nlist[point][BM_HOOK_OBSERVE]; k++) {
        hk_reg *r = &s_reg[s_list[point][BM_HOOK_OBSERVE][k]];
        bm_hook_ctx c = *base;                            /* a fresh copy: what one callback writes, the next never sees */
        c.role = BM_HOOK_OBSERVE;
        (void)call_guarded(r, &c, NULL);
    }
    for (int k = 0; k < s_nhobs[point]; k++) {
        bm_hook_ctx c = *base;
        hk_regs before, after;
        memset(&before, 0, sizeof before);
        memset(&after, 0, sizeof after);
        c.role = BM_HOOK_OBSERVE;
        save(&before);
        s_hobs[point][k].fn(&c, s_hobs[point][k].user);
        save(&after);
        if (!same(&before, &after)) {
            restore(&before);
            atomic_fetch_add(&s_hobs[point][k].faults, 1);
        }
    }
    s_depth--;
}

static int wanted(uint32_t point)
{
    return s_nlist[point][BM_HOOK_OBSERVE] || s_nlist[point][BM_HOOK_MODIFY] || s_nhobs[point];
}

/* ---- the points ---- */

static void car_observer(void *user)
{
    uint32_t car = g_esi;
    bm_hook_ctx c;
    (void)user;
    if (car != AP_CAR1 || !g_xbox_mem_offset || HK_M32(car + AP_CAR_PLAYER) != 0)
        return;                                          /* player 1's car only (as bmashup.events) */
    if (!enter(BM_HOOK_PLAYER_CAR_UPDATE))
        return;
    base_ctx(&c, BM_HOOK_PLAYER_CAR_UPDATE, atomic_load(&s_occ[BM_HOOK_PLAYER_CAR_UPDATE]));
    c.race_time_s = HK_MF(car + AP_CAR_TIME);
    c.car_phase = HK_M32(car + AP_CAR_PHASE);
    run_observers(BM_HOOK_PLAYER_CAR_UPDATE, &c);
}

static void sk_lifecycle(const bo3_lc_event *lc)
{
    uint32_t point = !lc ? 0 : lc->kind == BO3_LC_EV_LOAD_DONE ? BM_HOOK_LOAD_DONE :
                     lc->kind == BO3_LC_EV_RACE_EXIT ? BM_HOOK_RACE_EXIT : 0;
    bm_hook_ctx c;
    if (!point || !enter(point) || !wanted(point))
        return;
    base_ctx(&c, point, atomic_load(&s_occ[point]));
    c.load_kind = lc->load_kind;
    c.track_loads = lc->track_loads;
    c.race_exits = lc->race_exits;
    c.lanes = lc->lanes;
    c.racers = lc->racers;
    run_observers(point, &c);
}

static void sk_game(uint32_t event, uint32_t actor, uint32_t victim, uint32_t kind, uint32_t actor_takedowns)
{
    bm_hook_ctx c;
    if ((event != BM_HOOK_TAKEDOWN && event != BM_HOOK_WRECK) || !enter(event) || !wanted(event))
        return;
    base_ctx(&c, event, atomic_load(&s_occ[event]));
    c.actor = actor;
    c.victim = victim;
    c.kind = kind;
    c.actor_takedowns = actor_takedowns;
    run_observers(event, &c);
}

static int finite_f(float f)
{
    return f == f && f - f == 0.0f;
}

static void boost_ctx(bm_hook_ctx *c, uint32_t recipient, uint32_t source, uint32_t site, float requested, float amount,
                      int modified)
{
    base_ctx(c, BM_HOOK_BOOST_AWARD, s_boost_seq);
    c->recipient = recipient;
    c->award_source = source;
    c->award_site = site;
    c->award_requested = requested;
    c->award_amount = amount;
    c->award_modified = (uint32_t)modified;
}

/* BOOST_AWARD, step 1 (every add): the hook modifiers after bmashup.events' modifiers. Returns the amount to use. */
static float sk_modify_boost(uint32_t recipient, uint32_t source, uint32_t site, float requested, float amount, int *modified)
{
    const uint32_t P = BM_HOOK_BOOST_AWARD;
    bm_hook_ctx base;
    if (!enter(P)) {
        if (!s_depth)
            s_boost_live = 0;                            /* stopped: this add's observers are not called either */
        return amount;                                   /* re-entry: the outer add's state stays as it is */
    }
    s_boost_seq = atomic_load(&s_occ[P]);
    s_boost_live = 1;
    if (!s_nlist[P][BM_HOOK_MODIFY] || source == BM_BOOST_HOST || !finite_f(requested) || requested < 0.0f)
        return amount;
    boost_ctx(&base, recipient, source, site, requested, amount, *modified);
    s_depth++;
    for (int k = 0; k < s_nlist[P][BM_HOOK_MODIFY]; k++) {
        hk_reg *r = &s_reg[s_list[P][BM_HOOK_MODIFY][k]];
        bm_hook_ctx c = base;
        bm_hook_out out;
        c.role = BM_HOOK_MODIFY;
        c.award_amount = amount;
        c.award_modified = (uint32_t)*modified;
        out.struct_size = (uint32_t)sizeof out;
        out.output = BM_HOOK_OUT_BOOST_AMOUNT;
        out.amount = amount;
        if (call_guarded(r, &c, &out) == BM_HOOK_CHANGE) {
#if MUT == 107
            amount = out.amount;                         /* defect: no validation */
            *modified = 1;
#else
            if (finite_f(out.amount) && out.amount >= 0.0f && out.amount <= BM_HOOK_MOD_MAX_FACTOR * requested) {
                if (out.amount != amount) {
                    amount = out.amount;
                    *modified = 1;
                    atomic_fetch_add(&r->changed, 1);
                }
            } else {
                atomic_fetch_add(&r->rejected, 1);
            }
#endif
        }
    }
    s_depth--;
    return amount;
}

/* BOOST_AWARD, step 2: the observers, with the final amount (after bmashup.events' observers). */
static void sk_boost(uint32_t recipient, uint32_t source, uint32_t site, float amount, float requested, int modified)
{
    bm_hook_ctx c;
#if MUT != 102
    if (s_depth)
        return;                                          /* an add inside a hooks callback: counted at step 1 */
#endif
    if (!s_boost_live)
        return;                                          /* step 1 did not dispatch this add (stopped): counted there */
    s_boost_live = 0;
    if (!s_nlist[BM_HOOK_BOOST_AWARD][BM_HOOK_OBSERVE] && !s_nhobs[BM_HOOK_BOOST_AWARD])
        return;
    boost_ctx(&c, recipient, source, site, requested, amount, modified);
    run_observers(BM_HOOK_BOOST_AWARD, &c);
}

/* main18 (v2): CRASH_RESULT, after bmashup.events' subscribers; observers only */
static void sk_crash(const bo3_bm_crash_result *cr)
{
    bm_hook_ctx c;
    const uint32_t P = BM_HOOK_CRASH_RESULT;
#if MUT == 110
    atomic_fetch_add(&s_occ[P], 1);                      /* defect: dispatched after the stop and on re-entry */
    if (!cr || !wanted(P))
        return;
#else
    if (!cr || !enter(P) || !wanted(P))
        return;
#endif
    base_ctx(&c, P, atomic_load(&s_occ[P]));
    c.player = 0;
    c.crash_junction = cr->junction;
#if MUT != 109
    c.crash_score = cr->score;
#endif
    c.crash_mode = cr->mode;
    memcpy(c.crash_junction_id, cr->junction_id, sizeof c.crash_junction_id);
    memcpy(c.crash_track_id, cr->track_id, sizeof c.crash_track_id);
    c.crash_junction_id[sizeof c.crash_junction_id - 1] = 0;
    c.crash_track_id[sizeof c.crash_track_id - 1] = 0;
    run_observers(P, &c);
}

static const bo3_bm_events_sink k_sink = {sk_lifecycle, sk_game, sk_modify_boost, sk_boost, sk_crash};

/* ---- main19: version 3, points 8..13 (hook request P2 / P3) ----
 * The items' marks (bm_hud.c, bm_camera.c, bm_contact.c, ...) build a ctx with bo3_hk_ctx_v3 and call bo3_hk_dispatch_v3 on the
 * game's thread. The framework owns the order, the copies, the register guard, re-entry / stop and the bounds of every output;
 * an item adds its own check (bo3_hk_valid_fn) for what only it can know (the finishing car's position, the contact log). */

static int finite3(const float *v)
{
    return finite_f(v[0]) && finite_f(v[1]) && finite_f(v[2]);
}

static float absf(float f)
{
    return f < 0.0f ? -f : f;
}

int bo3_hk_out_in_bounds(uint32_t point, const bm_hook_ctx *c, const bm_hook_out *o)
{
    if (!c || !o || point < BM_HOOK_CAMERA_FINAL || point > BM_HOOK_POINTS_V3)
        return 0;
#if MUT != 137
    if (o->output != k_out_type[point])
        return 0;
#endif
#if MUT == 130
    return 1;
#endif
    switch (point) {
    case BM_HOOK_CAMERA_FINAL:
        if (!finite_f(o->roll_rad) || !finite_f(o->pitch_rad) || !finite_f(o->yaw_rad) || !finite3(o->offset_m))
            return 0;
#if MUT != 135
        if (absf(o->roll_rad) > BM_HOOK_CAM_MAX_ROLL)
            return 0;
#endif
        return absf(o->pitch_rad) <= BM_HOOK_CAM_MAX_PITCH && absf(o->yaw_rad) <= BM_HOOK_CAM_MAX_YAW &&
               absf(o->offset_m[0]) <= BM_HOOK_CAM_MAX_OFFSET && absf(o->offset_m[1]) <= BM_HOOK_CAM_MAX_OFFSET &&
               absf(o->offset_m[2]) <= BM_HOOK_CAM_MAX_OFFSET;
    case BM_HOOK_TRAFFIC_CONTACT:
        if (o->outcome == BM_CONTACT_GAME)
            return 1;
#if MUT != 139
        if (!finite_f(o->push_scale) || o->push_scale < 0.0f || o->push_scale > 1.0f)
            return 0;                                    /* main21 patch 79: the push factor 0 .. 1 */
#endif
#if MUT == 133
        return o->outcome == BM_CONTACT_NO_CRASH;
#else
        return o->outcome == BM_CONTACT_NO_CRASH && c->contact_same_dir == 1 && finite_f(c->contact_closing_mps) &&
               c->contact_closing_mps >= 0.0f && c->contact_closing_mps < BM_HOOK_CONTACT_MAX_MPS;
#endif
    case BM_HOOK_WRECK_CAUSE:
        return o->credit_racer == BM_HOOK_NO_RACER || (o->credit_racer < 64u && o->credit_racer != c->cause_victim);
    case BM_HOOK_EVENT_SOUND:
#if MUT == 134
        return o->sound_level <= 5u;
#else
        if (o->sound_level > 4u)
            return 0;
#endif
#if MUT == 138
        return 1;                                        /* defect: the pitch factor unbounded */
#else
        return o->sound_pitch == 0.0f || (finite_f(o->sound_pitch) && o->sound_pitch >= BM_HOOK_SOUND_PITCH_MIN &&
                                          o->sound_pitch <= BM_HOOK_SOUND_PITCH_MAX);   /* main21 patch 78 (0 = none) */
#endif
    case BM_HOOK_FINISH_CAMERA:
        if (o->finish_camera == BM_FINISH_CAMERA_GAME)
            return 1;
        if (o->finish_camera != BM_FINISH_CAMERA_POSE || !finite3(o->pose_pos) || !finite3(o->pose_at) ||
            !finite_f(o->pose_fov_scale))
            return 0;
        if (o->pose_pos[0] == o->pose_at[0] && o->pose_pos[1] == o->pose_at[1] && o->pose_pos[2] == o->pose_at[2])
            return 0;
        return o->pose_fov_scale >= BM_HOOK_FOV_SCALE_MIN && o->pose_fov_scale <= BM_HOOK_FOV_SCALE_MAX;
    default:
        return 0;
    }
}

int bo3_hk_offer_point(uint32_t point, uint32_t roles, bo3_hk_valid_fn valid)
{
#if !BO3_HOOKREQ_P23
    (void)point; (void)roles; (void)valid;
    return -1;                                           /* BO3_HOOKREQ_P23=OFF: every v3 point stays UNAVAILABLE */
#else
    if (!s_open || point < BM_HOOK_HUD_PASS || point > BM_HOOK_POINTS_V3 || !roles || (roles & ~k_point[point].roles))
        return -1;
    s_offer[point] = roles;
    s_valid[point] = valid;
    if (point != BM_HOOK_CAMERA_FINAL && point != BM_HOOK_FINISH_CAMERA)
        bo3_bm_events_offer_v7(point);
    fprintf(stderr, "[HOOKS] v3 point %u %s offered (%s%s)\n", (unsigned)point, k_point[point].name,
            roles & ROLE_BIT(BM_HOOK_OBSERVE) ? "observe" : "", roles & ROLE_BIT(BM_HOOK_MODIFY) ? " modify" : "");
    return 0;
#endif
}

int bo3_hk_point_available(uint32_t point)
{
    return point >= BM_HOOK_HUD_PASS && point <= BM_HOOK_POINTS_V3 && s_offer[point] != 0;
}

int bo3_hk_point_wanted(uint32_t point)
{
    if (!bo3_hk_point_available(point))
        return 0;
    return wanted(point) || bo3_bm_events_v7_wanted(point);
}

void bo3_hk_ctx_v3(bm_hook_ctx *c, uint32_t point)
{
    base_ctx(c, point, 0);
    c->contact_racer = c->cause_aggressor = c->cause_victim = BM_HOOK_NO_RACER;
}

/* the MODIFY callbacks of one occurrence (priority order; each proposal bounded, then the item's check) */
static int modify_step(uint32_t point, const bm_hook_ctx *base, bm_hook_out *res)
{
    int changed = 0;
    if (!res || !k_out_type[point] || res->output != k_out_type[point] || !s_nlist[point][BM_HOOK_MODIFY] ||
        !(s_offer[point] & ROLE_BIT(BM_HOOK_MODIFY)))
        return 0;
    s_depth++;
    for (int k = 0; k < s_nlist[point][BM_HOOK_MODIFY]; k++) {
        hk_reg *r = &s_reg[s_list[point][BM_HOOK_MODIFY][k]];
        bm_hook_ctx c = *base;
        bm_hook_out out = *res;                          /* the value so far */
        c.role = BM_HOOK_MODIFY;
        out.struct_size = (uint32_t)sizeof out;
        if (call_guarded(r, &c, &out) != BM_HOOK_CHANGE)
            continue;
        if (bo3_hk_out_in_bounds(point, base, &out) && (!s_valid[point] || s_valid[point](base, &out))) {
            if (memcmp(&out, res, sizeof out) != 0) {
                *res = out;
                changed = 1;
                atomic_fetch_add(&r->changed, 1);
            }
        } else {
            atomic_fetch_add(&r->rejected, 1);
        }
    }
    s_depth--;
    return changed;
}

static void twin(uint32_t point, const bm_hook_ctx *b, const bm_hook_out *res)
{
    bm_event ev;
    if (point == BM_HOOK_CAMERA_FINAL || point == BM_HOOK_FINISH_CAMERA || !bo3_bm_events_v7_wanted(point))
        return;
    memset(&ev, 0, sizeof ev);
    ev.struct_size = (uint32_t)sizeof ev;
    ev.event = point;
    ev.sequence = b->sequence;
    ev.step = b->step;
    ev.actor = ev.victim = ev.recipient = BM_EVENT_NO_RACER;
    ev.junction = BM_EVENT_NO_JUNCTION;
    switch (point) {                                     /* the event's own group; the other groups stay 0 */
    case BM_HOOK_HUD_PASS:
        ev.hud_visible = b->hud_visible;
        ev.frame_dt_s = b->frame_dt_s;
        break;
    case BM_HOOK_TRAFFIC_CONTACT:
        ev.contact_racer = b->contact_racer;
        ev.contact_traffic = b->contact_traffic;
        ev.contact_closing_mps = b->contact_closing_mps;
        ev.contact_same_dir = b->contact_same_dir;
        ev.contact_outcome = res ? res->outcome : BM_CONTACT_GAME;
        break;
    case BM_HOOK_WRECK_CAUSE:
        ev.cause_aggressor = b->cause_aggressor;
        ev.cause_victim = b->cause_victim;
        break;
    default:                                             /* EVENT_SOUND */
        ev.sound = b->sound;
        ev.sound_level_game = b->sound_level_game;
        ev.sound_event = b->sound_event;
        ev.sound_level = res ? res->sound_level : b->sound_level_game;
        break;
    }
    s_depth++;                                           /* an occurrence the subscribers cause is not dispatched to the hooks */
    bo3_bm_events_deliver_v7(&ev);
    s_depth--;
}

static int modify_step(uint32_t point, const bm_hook_ctx *base, bm_hook_out *res);

int bo3_hk_point_modifiers(uint32_t point)
{
    if (!bo3_hk_point_available(point) || !(s_offer[point] & ROLE_BIT(BM_HOOK_MODIFY)))
        return 0;
    return s_nlist[point][BM_HOOK_MODIFY];
}

int bo3_hk_modify_v3(uint32_t point, const bm_hook_ctx *ctx, bm_hook_out *res)
{
    bm_hook_ctx base;
    if (!ctx || !res || !bo3_hk_point_modifiers(point) || atomic_load(&s_stopped) || s_depth)
        return 0;
    base = *ctx;
    base.struct_size = (uint32_t)sizeof base;
    base.point = point;
    base.sequence = atomic_load(&s_occ[point]);
    base.step = g_xbox_mem_offset ? HK_M32(HK_STEP) : 0;
    res->struct_size = (uint32_t)sizeof *res;
    return modify_step(point, &base, res);
}

int bo3_hk_dispatch_v3(uint32_t point, const bm_hook_ctx *ctx, bm_hook_out *res)
{
    bm_hook_ctx base;
    int changed = 0;
    if (!ctx || point < BM_HOOK_HUD_PASS || point > BM_HOOK_POINTS_V3 || !s_offer[point])
        return 0;
    if (!enter(point))
        return 0;
    if (!wanted(point) && !bo3_bm_events_v7_wanted(point))
        return 0;
    base = *ctx;
    base.struct_size = (uint32_t)sizeof base;
    base.point = point;
    base.sequence = atomic_load(&s_occ[point]);
    base.step = g_xbox_mem_offset ? HK_M32(HK_STEP) : 0;
    if (res)
        res->struct_size = (uint32_t)sizeof *res;
#if MUT == 136
    twin(point, &base, res);
#endif
    changed = modify_step(point, &base, res);
#if MUT != 136
    twin(point, &base, res);
#endif
    if (s_nlist[point][BM_HOOK_OBSERVE] || s_nhobs[point])
        run_observers(point, &base);
    return changed;
}

/* ---- registration ---- */

static td_host *other_in(uint32_t point, uint32_t role, td_host *host)
{
    for (int k = 0; k < s_nlist[point][role]; k++)
        if (s_reg[s_list[point][role][k]].host != host)
            return s_reg[s_list[point][role][k]].host;
    return NULL;
}

static int32_t do_register(td_host *host, const bm_hook_reg *reg, uint32_t *id, td_host **owner)
{
    uint32_t point, role;
    int n, at, idx;
    *owner = NULL;
    if (id)
        *id = 0;
    if (!host || !reg || !id || reg->struct_size < offsetof(bm_hook_reg, user) + sizeof reg->user || !reg->fn)
        return BM_HOOKS_BAD_ARG;
    point = reg->point;
    role = reg->role;
    if (point < 1 || point > BM_HOOK_POINTS_V3)
        return BM_HOOKS_UNKNOWN_POINT;
    if ((role != BM_HOOK_OBSERVE && role != BM_HOOK_MODIFY) || !(k_point[point].roles & ROLE_BIT(role)))
        return BM_HOOKS_BAD_ROLE;
#if MUT != 131
    if (point >= BM_HOOK_HUD_PASS && !s_offer[point])
        return BM_HOOKS_UNAVAILABLE;                     /* main19 (v3): the point's mark is not in this run */
#endif
#if MUT != 132
    if (point >= BM_HOOK_HUD_PASS && s_offer[point] && !(s_offer[point] & ROLE_BIT(role)))
        return BM_HOOKS_BAD_ROLE;                        /* main19 (v3): a role this run does not offer (WRECK_CAUSE MODIFY) */
#endif
    if (reg->flags & ~BM_HOOK_EXCLUSIVE)
        return BM_HOOKS_BAD_FLAGS;
    if (reg->priority < BM_HOOK_PRIORITY_MIN || reg->priority > BM_HOOK_PRIORITY_MAX)
        return BM_HOOKS_BAD_ARG;
#if MUT != 106
    if (!s_open)
        return BM_HOOKS_CLOSED;
#endif
    if (point == BM_HOOK_PLAYER_CAR_UPDATE && bo3_bm_car_update_mark() < 0)
        return BM_HOOKS_UNAVAILABLE;
    n = s_nlist[point][role];
    for (int k = 0; k < n; k++)
        if (s_reg[s_list[point][role][k]].host == host)
            return BM_HOOKS_ALREADY;
#if MUT != 105
    if (s_excl[point][role] && s_excl[point][role] != host) {
        *owner = s_excl[point][role];
        return BM_HOOKS_CONFLICT;
    }
    if ((reg->flags & BM_HOOK_EXCLUSIVE) && (*owner = other_in(point, role, host)) != NULL)
        return BM_HOOKS_CONFLICT;
#else
    (void)other_in;
#endif
    if (n == BM_HOOK_MAX_PER_ROLE || s_nreg == HK_NREG)
        return BM_HOOKS_FULL;
    idx = s_nreg++;
    memset(&s_reg[idx], 0, sizeof s_reg[idx]);
    s_reg[idx].host = host;
    s_reg[idx].fn = reg->fn;
    s_reg[idx].user = reg->user;
    s_reg[idx].point = point;
    s_reg[idx].role = role;
    s_reg[idx].flags = reg->flags;
    s_reg[idx].prio = reg->priority;
    /* ascending priority; an equal priority goes after the earlier registrations (registration order) */
    at = n;
#if MUT != 101
    while (at > 0 && s_reg[s_list[point][role][at - 1]].prio > reg->priority)
        at--;
#endif
    memmove(&s_list[point][role][at + 1], &s_list[point][role][at], (size_t)(n - at) * sizeof(int));
    s_list[point][role][at] = idx;
    s_nlist[point][role] = n + 1;
    if (reg->flags & BM_HOOK_EXCLUSIVE)
        s_excl[point][role] = host;
    *id = (uint32_t)idx + 1u;
    return BM_HOOKS_OK;
}

static int32_t TD_CALL hk_register(td_host *host, const bm_hook_reg *reg, uint32_t *id)
{
    td_host *owner;
    int32_t rc = do_register(host, reg, id, &owner);
    const char *pn = reg && reg->point >= 1 && reg->point <= BM_HOOK_POINTS_V3 ? k_point[reg->point].name : "(unknown point)";
    const char *rn = reg ? role_name(reg->role) : "?";
    if (rc == BM_HOOKS_OK)
        fprintf(stderr, "[HOOKS] %s: %s %s registered (priority %d%s)\n", who(host), pn, rn, (int)reg->priority,
                reg->flags & BM_HOOK_EXCLUSIVE ? ", exclusive" : "");
    else if (rc == BM_HOOKS_CONFLICT)
        fprintf(stderr, "[HOOKS] %s: %s %s refused: CONFLICT (%s holds it%s)\n", who(host), pn, rn, who(owner),
                s_excl[reg->point][reg->role] == owner ? " exclusively" : "; an exclusive registration must be the only one");
    else
        fprintf(stderr, "[HOOKS] %s: %s %s refused: %s\n", host ? who(host) : "?", pn, rn, hk_result_text(rc));
    return rc;
}

static int32_t TD_CALL hk_stats(td_host *host, uint32_t id, bm_hook_stats *out)
{
    bm_hook_stats s;
    uint32_t room;
    hk_reg *r;
    if (!host || !out || out->struct_size < 8 || id == 0 || id > (uint32_t)s_nreg)
        return BM_HOOKS_BAD_ARG;
    r = &s_reg[id - 1];
    if (r->host != host)
        return BM_HOOKS_NOT_OWNER;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.calls = atomic_load(&r->calls);
    s.changed = atomic_load(&r->changed);
    s.rejected = atomic_load(&r->rejected);
    s.register_faults = atomic_load(&r->faults);
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_HOOKS_OK;
}

static int32_t TD_CALL hk_point_info(td_host *host, uint32_t point, bm_hook_point_info *out)
{
    bm_hook_point_info s;
    uint32_t room;
    if (!host || !out || out->struct_size < 8)
        return BM_HOOKS_BAD_ARG;
    if (point < 1 || point > BM_HOOK_POINTS_V3)
        return BM_HOOKS_UNKNOWN_POINT;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.point = point;
    snprintf(s.name, sizeof s.name, "%s", k_point[point].name);
    s.roles = k_point[point].roles;
    s.available = 1;
    if (point == BM_HOOK_PLAYER_CAR_UPDATE)              /* hooked in this run, and (once closed) attached when needed */
        s.available = bo3_bm_car_update_mark() >= 0 && (s_open || s_car_attached || !wanted(point));
    if (point >= BM_HOOK_HUD_PASS) {                     /* main19 (v3): offered by its item in this run */
        s.available = s_offer[point] != 0;
        s.roles = s_offer[point];
    }
    s.occurrences = atomic_load(&s_occ[point]);
    s.reentered = atomic_load(&s_reent[point]);
    s.after_stop = atomic_load(&s_after[point]);
    s.observers = (uint32_t)s_nlist[point][BM_HOOK_OBSERVE];
    s.modifiers = (uint32_t)s_nlist[point][BM_HOOK_MODIFY];
    s.exclusive_roles = (s_excl[point][BM_HOOK_OBSERVE] ? ROLE_BIT(BM_HOOK_OBSERVE) : 0u) |
                        (s_excl[point][BM_HOOK_MODIFY] ? ROLE_BIT(BM_HOOK_MODIFY) : 0u);
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_HOOKS_OK;
}

static const bm_hooks_api s_api = {
    (uint32_t)sizeof(bm_hooks_api), BM_HOOKS_VERSION, hk_register, hk_stats, hk_point_info, hk_result_text
};

const bm_hooks_api *bo3_bm_hooks_api(void)
{
    return &s_api;
}

int bo3_hk_host_observe(uint32_t point, bo3_hk_host_fn fn, void *user)
{
    if (!s_open || !fn || point < 1 || point > BM_HOOK_POINTS_V3 || s_nhobs[point] == HK_NHOST)
        return -1;
    s_hobs[point][s_nhobs[point]].fn = fn;
    s_hobs[point][s_nhobs[point]].user = user;
    s_nhobs[point]++;
    return 0;
}

void bo3_hk_stop(void)
{
    atomic_store(&s_stopped, 1);
}

static void stop_at_exit(void)
{
    bo3_hk_stop();
}

void bo3_bm_hooks_init(void)
{
    s_car_mark = bo3_bm_car_update_mark();
    bo3_bm_events_set_sink(&k_sink);
    bo3_plugins_service(BM_HOOKS_SERVICE, BM_HOOKS_VERSION, &s_api);
}

void bo3_bm_hooks_close(void)
{
    const uint32_t C = BM_HOOK_PLAYER_CAR_UPDATE;
    int n = 0;
    if (!s_open)
        return;
    s_open = 0;
    if (s_nlist[C][BM_HOOK_OBSERVE] || s_nhobs[C]) {
        s_car_mark = bo3_bm_car_update_mark();
        if (s_car_mark >= 0 && bo3_events_subscribe(s_car_mark, BO3_EVENT_OBSERVER, car_observer, NULL, "bmashup.hooks") == 0)
            s_car_attached = 1;
        else
            fprintf(stderr, "[HOOKS] PLAYER_CAR_UPDATE: no dispatcher slot for the hooks (mark %d): its %d registrations are "
                            "never called\n", s_car_mark, s_nlist[C][BM_HOOK_OBSERVE]);
    }
    if (!s_atexit) {
        s_atexit = 1;
        atexit(stop_at_exit);                            /* after the plugins' on_shutdown handlers: runs before them */
    }
    for (uint32_t p = 1; p <= BM_HOOK_POINTS_V3; p++)
        n += s_nlist[p][BM_HOOK_OBSERVE] + s_nlist[p][BM_HOOK_MODIFY];
    fprintf(stderr, "[HOOKS] registration closed: %d plugin registrations\n", n);
}
