/* bm_ai.c - gp slice ai1 EXPERIMENTAL: "bmashup.ai" (include/bmashup_ai.h; atlas gp\atlas\AI.md).
 *
 * The AI's speed cap F+0xA08 (= R+0x2408) is computed from scratch every AI update by sub_00173690 (pace schedule / rubber band,
 * top speed, chase mode); the target speed F+0x1D0 = min(corner plan, cap) follows (sub_00176150). The mark right after that
 * call (sub_00171A10, esi = F) multiplies the cap of AI-driven rivals by the pace. Player objects are skipped; a controller whose
 * self link F+0x7A0 is not R = F - 0x1A00 is skipped (counted). Nothing is written at pace 1.0. MUT=n (tests) = one defect. */
#include "bm_ai.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

static bo3_ai_guest s_g;
static int s_configured, s_verified;
static const td_host *s_owner;
static double s_pace = 1.0;
static uint32_t s_scaled, s_players, s_bad, s_marks;
static struct { uint32_t f; float pace; } s_last[16];

static int rd(uint32_t va, void *out, uint32_t n)
{
    return s_configured && s_g.read && s_g.read(s_g.user, va, out, n);
}

void bo3_ai_configure(const bo3_ai_guest *g, int verified)
{
    s_g = *g;
    s_configured = 1;
    s_verified = verified;
    s_owner = NULL;
    s_pace = 1.0;
    s_scaled = s_players = s_bad = s_marks = 0;
    memset(s_last, 0, sizeof s_last);
}

uint32_t bo3_ai_stat(uint32_t which)
{
    return which == 0 ? s_scaled : which == 1 ? s_players : which == 2 ? s_bad : s_marks;
}

static int is_player(uint32_t r)
{
    return r == BO3_AI_PLAYER1 || r == BO3_AI_PLAYER1 + BO3_AI_PLAYER_STRIDE;
}

static void remember(uint32_t f, float pace)
{
    int free_i = -1;
    for (int i = 0; i < 16; i++) {
        if (s_last[i].f == f) {
            s_last[i].pace = pace;
            return;
        }
        if (!s_last[i].f && free_i < 0)
            free_i = i;
    }
    if (free_i < 0)
        free_i = (int)(f / 0x2470u) & 15;   /* full: replace one */
    s_last[free_i].f = f;
    s_last[free_i].pace = pace;
}

static float last_pace(uint32_t f)
{
    for (int i = 0; i < 16; i++)
        if (s_last[i].f == f)
            return s_last[i].pace;
    return 1.0f;
}

void bo3_ai_gen_cap(uint32_t f)
{
    uint32_t r, self = 0;
    float cap, p = (float)s_pace;
    s_marks++;
    if (!s_verified || f < BO3_AI_F)
        return;
    r = f - BO3_AI_F;
#if MUT != 1
    if (is_player(r)) {
        s_players++;
        return;
    }
#endif
#if MUT == 2
    (void)self;
#else
    if (!rd(f + BO3_AI_F_SELF, &self, 4) || self != r) {
        s_bad++;
        return;
    }
#endif
    if (p == 1.0f) {
        remember(f, 1.0f);
        return;                                     /* the game's own cap, untouched */
    }
    if (!rd(f + BO3_AI_F_CAP, &cap, 4))
        return;
#if MUT != 3
    if (!isfinite(cap) || cap <= 0.0f)
        return;                                     /* nothing sensible to scale */
#endif
    cap *= p;
    if (s_g.write(s_g.user, f + BO3_AI_F_CAP, &cap, 4)) {
        s_scaled++;
        remember(f, p);
    }
}

/* ---- the service ---- */
static uint32_t list_count(void)
{
    uint32_t n = 0;
    if (!s_verified || !rd(BO3_AI_LIST_COUNT, &n, 4))
        return 0;
    return n > 8u ? 8u : n;
}

static uint32_t TD_CALL a_count(td_host *host)
{
    return host ? list_count() : 0;
}

static int32_t TD_CALL a_get(td_host *host, uint32_t index, bm_ai_racer *out)
{
    bm_ai_racer o;
    uint32_t r = 0, car = 0, f;
    int32_t col = 0;
    int8_t zone = 0;
    if (!host || !out || out->struct_size < 8)
        return BM_AI_BAD_ARG;
    if (index >= list_count())
        return BM_AI_NO_RACER;
    if (!rd(BO3_AI_LIST + 4u * index, &r, 4) || !r)
        return BM_AI_UNAVAILABLE;
    f = r + BO3_AI_F;
    memset(&o, 0, sizeof o);
    if (!rd(f + BO3_AI_F_CAP, &o.speed_cap, 4) || !rd(f + BO3_AI_F_TARGET, &o.target_speed, 4) ||
        !rd(f + BO3_AI_F_SCHED, &o.schedule_offset, 4) || !rd(r + BO3_AI_R_COLUMN, &col, 4) || !rd(r + BO3_AI_R_ZONE, &zone, 1) ||
        !rd(r + BO3_AI_R_CAR, &car, 4))
        return BM_AI_UNAVAILABLE;
    if (car)
        rd(car + BO3_AI_CAR_SPEED, &o.car_speed, 4);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.index = index;
    o.is_player = (uint32_t)is_player(r);
    o.schedule_column = col < 0 ? 0u : col > 7 ? 7u : (uint32_t)col;
    o.zone = zone < 0 ? 0u : (uint32_t)zone;
    o.pace_applied = last_pace(f);
    memcpy(out, &o, o.struct_size);
    return BM_AI_OK;
}

static int32_t TD_CALL a_set(td_host *host, double pace)
{
    if (!host)
        return BM_AI_BAD_ARG;
#if MUT != 4
    if (!isfinite(pace) || pace < BM_AI_PACE_MIN || pace > BM_AI_PACE_MAX)
        return BM_AI_OUT_OF_RANGE;
#endif
#if MUT != 5
    if (s_owner && s_owner != host)
        return BM_AI_CONFLICT;
#endif
    s_owner = host;
    s_pace = pace;
    return BM_AI_OK;
}

static int32_t TD_CALL a_getp(td_host *host, double *pace)
{
    if (!host || !pace)
        return BM_AI_BAD_ARG;
    *pace = s_pace;
    return BM_AI_OK;
}

static int32_t TD_CALL a_reset(td_host *host)
{
    if (!host)
        return BM_AI_BAD_ARG;
    if (s_owner != host)
        return BM_AI_CONFLICT;
#if MUT != 6
    s_pace = 1.0;
#endif
    s_owner = NULL;
    return BM_AI_OK;
}

static const bm_ai_api s_api = {(uint32_t)sizeof(bm_ai_api), BM_AI_VERSION, a_count, a_get, a_set, a_getp, a_reset};

const bm_ai_api *bo3_bm_ai_api(void)
{
    return &s_api;
}

#ifdef BO3_AI_GAME
#include "bm_guest.h"
#include "plugins.h"

static int g_read(void *u, uint32_t va, void *out, uint32_t n)
{
    (void)u;
    return bo3_guest_read(va, out, n);
}

static int g_write(void *u, uint32_t va, const void *in, uint32_t n)
{
    (void)u;
    return bo3_guest_write(va, in, n);
}

void bo3_bm_ai_init(void)
{
    static const bo3_ai_guest g = {g_read, g_write, NULL};
    uint32_t k1 = 0, k2 = 0;
    int ok;
    bo3_ai_configure(&g, 0);
    /* build check: the cap's constants where this build's code reads them (sub_00172BC0: the +-4 s clamp 4.0 @0x3B1690 /
     * -4.0 @0x3B1948) */
    ok = bo3_guest_rd32(0x003B1690u, &k1) && k1 == 0x40800000u && bo3_guest_rd32(0x003B1948u, &k2) && k2 == 0xC0800000u;
    bo3_ai_configure(&g, ok);
    fprintf(stderr, "[AI] bmashup.ai %u: %s\n", (unsigned)BM_AI_VERSION,
            ok ? "racer AI fields verified on this game build" : "NOT verified on this game build: the service does nothing");
    bo3_plugins_service(BM_AI_SERVICE, BM_AI_VERSION, &s_api);
}

/* process-exit summary (log only) */
void bo3_ai_exit_summary(void)
{
    fprintf(stderr, "[AI] pace summary: %u caps scaled, %u player updates skipped, %u inconsistent skipped, %u marks\n",
            (unsigned)s_scaled, (unsigned)s_players, (unsigned)s_bad, (unsigned)s_marks);
}
#endif
