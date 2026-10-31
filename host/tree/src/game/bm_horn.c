/* bm_horn.c - main21 patch 120 (batch C3-3, zackypoo 13): a PLAYER HORN (retail Xbox has none). Hold the left stick click (L3) of
 * player 1's pad in a race: the game's own traffic-horn sound (TRAFF_HORN14) plays at the player's car until the button is let go.
 *
 * Static RE: notes\C3_3_PLAYER_HORN_RE.md (route c, the traffic horn's own voice API without an emitter):
 *   lookup  sub_001C9E50  EAX = bank 0x40B7F4, EBX = &id64, push 0, ret 4 (callee pops)   -> EAX = sample handle or 0
 *   params  sub_001CD180  EAX = params P (0x47 bytes), plain ret                           -> the defaults
 *   start   sub_001CD8D0  ESI = voice pool 0x40B844, EDI = P, plain ret                     -> EAX = voice V or 0 (pool full)
 *   update  sub_001CC3E0  EAX = V (never 0), EDI = P (pos, velocity, volume, pitch), plain ret
 *   stop    the game's inline stop (sub_00146DD0): h = [V + 0xC]; sub_001FB100(h, 0) (caller pops 8), then
 *           sub_001FB140(h, 0) (caller pops 8); byte V + 0x34 = 0, float V + 0x30 = 0, byte V + 0x37 &= 1
 * Ownership guard: the voice's allocation serial [V + 0x14] and handle [V + 0x10] are kept at the start; a voice the pool took
 * back (a finished one-shot, a race exit) is never touched again. One horn at a time; nothing when the census differs.
 * Called once a race-audio tick (hirefresh.c bo3_race_audio, game thread) after the game's own audio manager ran.
 * Switch BO3_HOOKREQ_ZHN (CMake ON). MUT (tests): 1 no ownership guard  2 the horn not stopped on release  3 the callee-pop of
 * the lookup not respected (esp not restored) */
#include "bm_horn.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_input.h"
#include "bmashup_input.h"
#include "recomp_types.h"

#ifndef BO3_HOOKREQ_ZHN
#define BO3_HOOKREQ_ZHN 0
#endif
#ifndef MUT
#define MUT 0
#endif

extern void sub_001C9E50(void);
extern void sub_001CD180(void);
extern void sub_001CD8D0(void);
extern void sub_001CC3E0(void);
extern void sub_001FB100(void);
extern void sub_001FB140(void);

#define HN_BANK      0x0040B7F4u
#define HN_POOL      0x0040B844u
#define HN_MAXD      0x0040FC5Cu      /* the traffic horn's max distance (ValueDB-fed; 0 outside traffic modes) */
#define HN_ID_LO     0xAF0A9F27u      /* "TRAFF_HORN14" (base-40), variant 1 of 4 */
#define HN_ID_HI     0xBEADD71Au
#define HN_V0        0x00667E90u      /* player 1's physics vehicle */
#define HN_V_XFORM   0x204u           /* -> its transform, position at + 0x30 */
#define HN_V_VEL     0xB0u
#define HN_CLASS     9u               /* the traffic horn's voice class (V + 0x36) */

static const struct { uint32_t va; uint8_t n; uint8_t b[12]; } k_census[] = {
    { 0x001C9E50u, 12, { 0x56,0x8b,0x70,0x34,0x85,0xf6,0x57,0x8b,0x7c,0x24,0x0c,0x74 } },
    { 0x001CD180u, 8, { 0xf3,0x0f,0x10,0x05,0xbc,0x16,0x3b,0x00 } },
    { 0x001CD8D0u, 12, { 0x55,0x8b,0xec,0x83,0xe4,0xf0,0x83,0xec,0x3c,0x8a,0x47,0x45 } },
    { 0x001CC3E0u, 10, { 0x83,0xec,0x08,0x56,0x8b,0xf0,0x0f,0xb6,0x46,0x36 } },
    { 0x001FB100u, 8, { 0x8b,0x44,0x24,0x08,0x85,0xc0,0x74,0x1e } },
    { 0x001FB140u, 9, { 0x8b,0x44,0x24,0x04,0x8b,0x48,0x64,0x85,0xc9 } },
    { 0x00146367u, 10, { 0xb8,0x27,0x9f,0x0a,0xaf,0xb9,0x1a,0xd7,0xad,0xbe } },
    { 0x001480E8u, 5, { 0xb8,0xf4,0xb7,0x40,0x00 } },
    { 0x0014814Bu, 5, { 0xbe,0x44,0xb8,0x40,0x00 } },
    { 0x001CD9BAu, 10, { 0x8b,0x86,0x84,0x28,0x00,0x00,0x33,0xdb,0x85,0xc0 } },
};

static int s_census = -1;
static uint32_t s_v, s_serial, s_handle, s_starts, s_stops, s_lost, s_lines, s_ticks;
static int s_unavail;                 /* the sample is not in the bank (a mode without traffic sounds): until the next start */
static int s_prev;                    /* held at the last tick (the press edge is this file's own: ticks != pad reads) */

static int g_ok(uint32_t va, uint32_t n) { return va && bo3_guest_window(va, n) != BO3_GUEST_NONE; }
static uint32_t g32(uint32_t va) { uint32_t v = 0; if (g_ok(va, 4)) bo3_guest_read(va, &v, 4); return v; }
static float gf(uint32_t va) { float v = 0.0f; if (g_ok(va, 4)) bo3_guest_read(va, &v, 4); return v; }
static void w32(uint32_t va, uint32_t v) { if (g_ok(va, 4)) bo3_guest_write(va, &v, 4); }
static void wf(uint32_t va, float v) { if (g_ok(va, 4)) bo3_guest_write(va, &v, 4); }
static void w8(uint32_t va, uint8_t v) { if (g_ok(va, 1)) bo3_guest_write(va, &v, 1); }
static uint8_t g8(uint32_t va) { uint8_t v = 0; if (g_ok(va, 1)) bo3_guest_read(va, &v, 1); return v; }

int bo3_horn_census(void)
{
    if (s_census < 0) {
        s_census = 1;
        for (size_t k = 0; k < sizeof k_census / sizeof k_census[0]; k++) {
            uint8_t x[16];
            if (!bo3_guest_read(k_census[k].va, x, k_census[k].n) || memcmp(x, k_census[k].b, k_census[k].n))
                s_census = 0;
        }
    }
    return s_census;
}

static void line(const char *what, uint32_t a, uint32_t b)
{
    if (s_lines < 24u) {
        s_lines++;
        fprintf(stderr, "[HORN] %s %08x %08x (starts %u, stops %u, lost %u)\n", what, (unsigned)a, (unsigned)b, (unsigned)s_starts,
                (unsigned)s_stops, (unsigned)s_lost);
    }
}

/* every guest register, g_ebp / g_seh_ebp (the voice calls write both), the XMM registers and the FPU top put back; esp too.
 * The calls run on a stack below the scratch block (P at scratch, the id at scratch + 0x50). */
typedef struct { uint32_t a, b, c, d, si, di, sp, bp, seh; RecompXmm x[8]; int top; } regs;
static void save(regs *r)
{
    r->a = g_eax; r->b = g_ebx; r->c = g_ecx; r->d = g_edx; r->si = g_esi; r->di = g_edi; r->sp = g_esp; r->bp = g_ebp;
    r->seh = g_seh_ebp; r->top = g_fp_top;
    r->x[0] = g_xmm0; r->x[1] = g_xmm1; r->x[2] = g_xmm2; r->x[3] = g_xmm3;
    r->x[4] = g_xmm4; r->x[5] = g_xmm5; r->x[6] = g_xmm6; r->x[7] = g_xmm7;
}
static void restore(const regs *r)
{
    g_eax = r->a; g_ebx = r->b; g_ecx = r->c; g_edx = r->d; g_esi = r->si; g_edi = r->di; g_ebp = r->bp; g_seh_ebp = r->seh;
#if MUT != 3
    g_esp = r->sp;
#endif
    g_fp_top = r->top;
    g_xmm0 = r->x[0]; g_xmm1 = r->x[1]; g_xmm2 = r->x[2]; g_xmm3 = r->x[3];
    g_xmm4 = r->x[4]; g_xmm5 = r->x[5]; g_xmm6 = r->x[6]; g_xmm7 = r->x[7];
}

static void params(uint32_t p)
{
    g_eax = p;
    PUSH32(g_esp, 0);
    sub_001CD180();
}

static void car_pose(float *pos, float *vel)
{
    uint32_t xf = g32(HN_V0 + HN_V_XFORM);
    for (int i = 0; i < 3; i++) {
        pos[i] = gf(xf + 0x30u + 4u * (uint32_t)i);
        vel[i] = gf(HN_V0 + HN_V_VEL + 4u * (uint32_t)i);
        if (!(pos[i] == pos[i]) || fabsf(pos[i]) > 1e6f)
            pos[i] = 0.0f;
        if (!(vel[i] == vel[i]) || fabsf(vel[i]) > 1e3f)
            vel[i] = 0.0f;
    }
}

static float max_dist(void)
{
    float d = gf(HN_MAXD);
    return d > 1.0f && d < 1e5f ? d : 300.0f;
}

static int owned(void)
{
#if MUT == 1
    return s_v != 0;                                  /* defect: no ownership guard */
#else
    return s_v && g32(s_v + 0x14u) == s_serial && g32(s_v + 0x10u) == s_handle && g8(s_v + 0x36u) == HN_CLASS;
#endif
}

static void start(uint32_t scratch)
{
    uint32_t p = scratch, id = scratch + 0x50u, h, v, before;
    float pos[3], vel[3];
    w32(id, HN_ID_LO);
    w32(id + 4u, HN_ID_HI);
    g_eax = HN_BANK;
    g_ebx = id;
    before = g_esp;
    PUSH32(g_esp, 0);
    PUSH32(g_esp, 0);                                 /* the return address its ret 4 takes with the argument */
    sub_001C9E50();
    h = g_eax;
    if (g_esp != before) {
        line("lookup left esp off by", g_esp - before, 0);
        return;
    }
    if (!h) {
        s_unavail = 1;
        line("no TRAFF_HORN14 sample in the bank (no horn this race)", HN_BANK, 0);
        return;
    }
    params(p);
    car_pose(pos, vel);
    for (int i = 0; i < 3; i++)
        wf(p + 4u * (uint32_t)i, pos[i]);
    w32(p + 0x18u, h);
    wf(p + 0x1Cu, 0.0f);
    wf(p + 0x38u, max_dist());
    w8(p + 0x44u, (uint8_t)HN_CLASS);
    w8(p + 0x45u, 1);
    g_esi = HN_POOL;
    g_edi = p;
    PUSH32(g_esp, 0);
    sub_001CD8D0();
    v = g_eax;
    if (!v || g32(v + 0x10u) != h) {
        line("no voice (pool full or not started)", v, h);
        return;
    }
    s_v = v;
    s_handle = h;
    s_serial = g32(v + 0x14u);
    s_starts++;
    line("start: voice / handle", v, h);
}

static void update(uint32_t scratch)
{
    uint32_t p = scratch;
    float pos[3], vel[3];
    params(p);
    car_pose(pos, vel);
    for (int i = 0; i < 3; i++) {
        wf(p + 4u * (uint32_t)i, pos[i]);
        wf(p + 0xCu + 4u * (uint32_t)i, vel[i]);
    }
    wf(p + 0x1Cu, 1.0f);
    wf(p + 0x24u, 1.0f);
    wf(p + 0x38u, max_dist());
    g_eax = s_v;
    g_edi = p;
    PUSH32(g_esp, 0);
    sub_001CC3E0();
}

static void stop(void)
{
    uint32_t h = g32(s_v + 0xCu);
    PUSH32(g_esp, 0);
    PUSH32(g_esp, h);
    PUSH32(g_esp, 0);
    sub_001FB100();
    g_esp += 8;                                       /* the caller pops its two arguments */
    PUSH32(g_esp, 0);
    PUSH32(g_esp, h);
    PUSH32(g_esp, 0);
    sub_001FB140();
    g_esp += 8;
    w8(s_v + 0x34u, 0);
    wf(s_v + 0x30u, 0.0f);
    w8(s_v + 0x37u, (uint8_t)(g8(s_v + 0x37u) & 1u));
    s_stops++;
    line("stop: voice", s_v, h);
    s_v = 0;
}

void bo3_horn_tick(void)
{
    static int h_dummy;
    const bm_input_api *api;
    bm_input_pad pad;
    regs r;
    uint32_t scratch;
    int held, pressed;
    if (!BO3_HOOKREQ_ZHN || bo3_horn_census() != 1)
        return;
    s_ticks++;
    api = bo3_bm_input_api();
    memset(&pad, 0, sizeof pad);
    pad.struct_size = (uint32_t)sizeof pad;
    held = api && api->pad((td_host *)(void *)&h_dummy, 0, &pad) == BM_INPUT_OK && pad.context == BM_INPUT_CTX_RACE &&
           pad.owner == BM_INPUT_GAME && (pad.buttons & BM_PAD_LTHUMB);
    pressed = held && !s_prev;
    s_prev = held;
    if (s_v && !owned()) {                            /* the pool took it back (one-shot ended, race exit): never touch it */
        s_lost++;
        line("voice no longer ours (forgotten)", s_v, s_serial);
        s_v = 0;
    }
    if (!s_v && !pressed)
        return;
    save(&r);
    scratch = (g_esp - 0x100u) & ~0xFu;
    g_esp = scratch;                                  /* the calls' stack lies below the scratch block */
    if (s_v) {
#if MUT == 2
        update(scratch);                              /* defect: never stopped on release */
#else
        if (held)
            update(scratch);
        else
            stop();
#endif
    } else if (pressed) {
        s_unavail = 0;
        start(scratch);
    }
    restore(&r);
}

uint32_t bo3_horn_stat(uint32_t which)
{
    return which == 0 ? s_starts : which == 1 ? s_stops : which == 2 ? s_lost : which == 3 ? s_v : which == 5 ? (uint32_t)s_unavail
                                                                                                     : s_ticks;
}

void bo3_horn_reset(void)
{
    s_census = -1;
    s_v = s_serial = s_handle = s_starts = s_stops = s_lost = s_lines = s_ticks = 0;
    s_unavail = s_prev = 0;
}
