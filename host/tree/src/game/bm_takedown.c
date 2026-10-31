/* bm_takedown.c - G8-E6 EXPERIMENTAL: bmashup.events version 3 TAKEDOWN / WRECK (include/bmashup_events.h) from three
 * single-line marks in the generated code (bo3_takedown_gen.h; e6_takedown\TAKEDOWN_TRACE.md):
 *   sub_00198E60 loc_00198E81  (the takedown counter, after its latch: edi = victim car, MEM32(esi + 0xC8) = attacker car)
 *       -> bo3_e6_gen_takedown_begin(victim, attacker): the attacker's three kind counters are noted
 *   sub_00198E60 loc_00198F0F  (sub_001994D0 has decided the kind)
 *       -> bo3_e6_gen_takedown_end(): the counter that moved is the kind; TAKEDOWN is delivered
 *   sub_0018C7D0 / sub_0018E010 (a car marked wrecked: MEM8(car + 0x18FA) = 1)
 *       -> bo3_e6_gen_wreck(car), before the store: WRECK only when the car was not wrecked yet
 * Racer index = the car's position in the race's list (count 0x73A19C, list 0x73A1A8; at most 8), else BM_EVENT_NO_RACER.
 * Car fields (SRC, TAKEDOWN_TRACE.md): +0x1138 per-race takedowns, +0x118C aftertouch, +0x1190 signature, +0x1194 standard.
 * Reads only; the game's state is never written. MUT=n (tests) compiles one deliberate defect. */
#include "bm_takedown.h"

#include <stdio.h>
#include <string.h>

#include "bm_events_service.h"

#ifndef MUT
#define MUT 0
#endif

#define TD_LISTN   0x0073A19Cu
#define TD_LIST    0x0073A1A8u
#define TD_COUNT   0x1138u
#define TD_AFTER   0x118Cu
#define TD_SIGN    0x1190u
#define TD_STD     0x1194u
#define TD_WRECKED 0x18FAu

extern ptrdiff_t g_xbox_mem_offset;

static uint32_t rd32(uint32_t va)
{
    uint32_t v = 0;
    if (g_xbox_mem_offset && va >= 0x10000u && va < 0x08000000u)
        memcpy(&v, (const void *)((uintptr_t)g_xbox_mem_offset + va), 4);
    return v;
}

static uint8_t rd8(uint32_t va)
{
    return g_xbox_mem_offset && va >= 0x10000u && va < 0x08000000u ? *(const uint8_t *)((uintptr_t)g_xbox_mem_offset + va) : 0;
}

uint32_t bo3_e6_racer_index(uint32_t car)
{
    uint32_t n = rd32(TD_LISTN);
    if (!car)
        return BM_EVENT_NO_RACER;
    for (uint32_t i = 0; i < n && i < 8u; i++)
        if (rd32(TD_LIST + 4u * i) == car)
            return i;
    return BM_EVENT_NO_RACER;
}

static struct {
    int pending;
    uint32_t victim, attacker, after, sign, std;
} s_td;
static uint32_t s_takedowns, s_wrecks, s_unknown, s_unpaired;

void bo3_e6_gen_takedown_begin(uint32_t victim, uint32_t attacker)
{
    if (s_td.pending)
        s_unpaired++;                    /* a begin without its end (never expected): counted */
    s_td.pending = 1;
    s_td.victim = victim;
    s_td.attacker = attacker;
    s_td.after = rd32(attacker + TD_AFTER);
    s_td.sign = rd32(attacker + TD_SIGN);
    s_td.std = rd32(attacker + TD_STD);
}

void bo3_e6_gen_takedown_end(void)
{
    uint32_t a, kind, actor, victim, count;
    if (!s_td.pending) {
        s_unpaired++;
        return;
    }
    s_td.pending = 0;
    a = s_td.attacker;
#if MUT == 1
    kind = BM_TAKEDOWN_STANDARD;         /* defect: the kind is not read */
#else
    kind = rd32(a + TD_AFTER) != s_td.after ? BM_TAKEDOWN_AFTERTOUCH :
           rd32(a + TD_SIGN) != s_td.sign ? BM_TAKEDOWN_SIGNATURE :
           rd32(a + TD_STD) != s_td.std ? BM_TAKEDOWN_STANDARD : BM_TAKEDOWN_UNKNOWN;
#endif
    s_unknown += kind == BM_TAKEDOWN_UNKNOWN;
    actor = bo3_e6_racer_index(a);
    victim = bo3_e6_racer_index(s_td.victim);
    count = rd32(a + TD_COUNT);
    s_takedowns++;
    fprintf(stderr, "[E6] takedown %u: actor %d victim %d kind %u (actor's takedowns this race %u)\n", (unsigned)s_takedowns,
            (int)actor, (int)victim, (unsigned)kind, (unsigned)count);
    bo3_bm_events_deliver_game(BM_EVENT_TAKEDOWN, actor, victim, kind, count);
}

void bo3_e6_gen_wreck(uint32_t car)
{
    uint32_t idx;
#if MUT != 2
    if (rd8(car + TD_WRECKED))
        return;                          /* already wrecked: not a new wreck */
#else
    (void)rd8;
#endif
    idx = bo3_e6_racer_index(car);
    s_wrecks++;
    fprintf(stderr, "[E6] wreck %u: racer %d (car 0x%08X)\n", (unsigned)s_wrecks, (int)idx, (unsigned)car);
    bo3_bm_events_deliver_game(BM_EVENT_WRECK, BM_EVENT_NO_RACER, idx, 0u, 0u);
    if (bo3_e6_wreck_tap)
        bo3_e6_wreck_tap(car, idx);                      /* main19 (item 39): bm_contact.c's credit window */
}

void (*bo3_e6_wreck_tap)(uint32_t car, uint32_t idx);

uint32_t bo3_e6_stats(uint32_t which)
{
    return which == 0 ? s_takedowns : which == 1 ? s_wrecks : which == 2 ? s_unknown : s_unpaired;
}
