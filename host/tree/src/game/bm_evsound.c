/*
 * bm_evsound.c - main19 (hook request P2, item 27; IMPLEMENTATION_PLAN patch 27, FEASIBILITY G1): bmashup.hooks v3 point 12
 * EVENT_SOUND. The takedown-sign sound (sub_001407B0's branch at loc_001408D7) always reaches one of two pitch calls with the
 * ladder LEVEL in EAX: sub_00140D30 at 0x14097C (levels 0..4 -> 1.0 .. 1.414 x) or the alternate sound sub_00141150 at 0x14099A
 * (0..4, the same ladder). The mark asks the plugins for the level (framework bound 0..4; anything else is ignored and counted)
 * and returns it to the game. No sound is played by the host and no voice is allocated: the voice pool cannot be exhausted by
 * this point. Sites: SITES_VERIFIED s6 + tests\p23\STEP0_B.md (every claim re-checked, incl. the uninitialised slot above 4).
 * BO3_HOOKREQ_P23 == 0: no mark in the generated code, the point is not offered.
 * MUT=n (tests only): 211 the census skipped, 212 a game level outside the ladder dispatched (the plugins could replace an
 * alternate-sound level the ladder does not have), 213 the game's level not given to the plugins (sound_level_game 0).
 * main21 patch 78 (open item 6, arbitrary pitch): out->sound_pitch (0.5 .. 2.0, bounded by bm_hooks.c) is kept for the ONE play
 * the level was asked for; marks in sub_00140D30 (loc_00140D72) and sub_00141150 (loc_001411D3), where both functions read
 * their pitch slot [esp] for their sub_00141010 plays, multiply that slot by it (bo3_es_gen_pitch). Own census (pitch sites);
 * BO3_HOOKREQ_P8P == 0: no pitch marks, the factor is accepted but not applied. MUT 214 the factor kept for later plays,
 * 215 the factor of the other sound applied, 216 the pitch census skipped.
 */
#include "bm_evsound.h"

#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_hooks.h"

#ifndef MUT
#define MUT 0
#endif

#define ES_SITE_VA 0x001408D7u
static const char k_site[] =
    "33ff81fd93000000745a81fda3000000744d81fd9f000000744581fda4000000743681fda0000000742e81fda5000000741f81fda1000000741781fd"
    "a6000000740881fda2000000751abf04000000eb13bf03000000eb0cbf02000000eb05bf010000008b1d70534d0085db7435b9a0714a00e8216aedff"
    "84c0742781bbb8010000284c4d00751b8b0d20b37300a108b373002b410885c07e0983f8057d123bc77f028bc7e8af0300005f5e5d5bc20c0083f804"
    "7e3b83c0fb83f8047e05b804000000e8b1070000";

static int s_ok;
static uint32_t s_changed;
#ifndef BO3_HOOKREQ_P8P
#define BO3_HOOKREQ_P8P 1           /* unit tests: the CMake option is not there */
#endif
/* patch 78: the pitch sites (default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_pitch_rows[] = {
    { 0x00140D6Du, 13, { 0xf3,0x0f,0x11,0x04,0x24,0x8b,0x46,0x38,0x57,0x8b,0x7c,0x24,0x04 } },   /* slot = level pitch; edi = slot */
    { 0x001411D3u, 13, { 0x8b,0x46,0x78,0x57,0x8b,0x7c,0x24,0x04,0x6a,0x00,0x6a,0x00,0x57 } },   /* alternate: edi = slot */
};
/* END-CENSUS */
static int s_pitch_ok;
static float s_pend_mul = 1.0f;
static int s_pend = -1;             /* the sound (0 / 1 = alternate) whose next play takes s_pend_mul; -1 none */
static uint32_t s_pitched;

static int pitch_census(void)
{
#if MUT == 216
    return 1;
#endif
    for (size_t k = 0; k < sizeof s_pitch_rows / sizeof s_pitch_rows[0]; k++) {
        uint8_t b[24];
        if (!bo3_guest_read(s_pitch_rows[k].va, b, s_pitch_rows[k].n) || memcmp(b, s_pitch_rows[k].b, s_pitch_rows[k].n))
            return 0;
    }
    return 1;
}

/* patch 78 marks: sp = the guest esp at loc_00140D72 (alt 0) / loc_001411D3 (alt 1); [sp] = the pitch the plays use */
void bo3_es_gen_pitch(uint32_t sp, uint32_t alt)
{
    float p;
#if MUT == 215
    (void)alt;
    if (s_pend < 0)
#else
    if (s_pend != (int)alt)
#endif
        return;
#if MUT != 214
    s_pend = -1;                                         /* this one play only */
#endif
    if (!bo3_guest_read(sp, &p, 4) || !(p > 0.0f) || p > 8.0f)
        return;                                          /* not a ladder pitch: the game's own */
    p *= s_pend_mul;
    if (bo3_guest_write(sp, &p, 4))
        s_pitched++;
}

uint32_t bo3_evsound_pitched(void) { return s_pitched; }

static int census(void)
{
    uint8_t cur[sizeof k_site / 2];
#if MUT == 211
    return 1;
#endif
    if (!bo3_guest_read(ES_SITE_VA, cur, (uint32_t)sizeof cur))
        return 0;
    for (size_t i = 0; i < sizeof cur; i++) {
        unsigned v = 0;
        for (int k = 0; k < 2; k++) {
            char c = k_site[2 * i + (size_t)k];
            v = v * 16u + (unsigned)(c >= '0' && c <= '9' ? c - '0' : c - 'a' + 10);
        }
        if (cur[i] != (uint8_t)v)
            return 0;
    }
    return 1;
}

uint32_t bo3_es_gen_level(uint32_t level, uint32_t event, uint32_t alt)
{
    bm_hook_ctx c;
    bm_hook_out o;
    s_pend = -1;
#if MUT != 212
    if (level > 4u)
        return level;                                    /* not a ladder level: the game's own value */
#endif
    if (!s_ok || !bo3_hk_point_wanted(BM_HOOK_EVENT_SOUND))
        return level;
    bo3_hk_ctx_v3(&c, BM_HOOK_EVENT_SOUND);
    c.sound = BM_SOUND_TAKEDOWN;
#if MUT != 213
    c.sound_level_game = level;
#endif
    c.sound_event = event;
    memset(&o, 0, sizeof o);
    o.output = BM_HOOK_OUT_SOUND_LEVEL;
    o.sound_level = level;
    o.sound_pitch = 1.0f;
    if (!bo3_hk_dispatch_v3(BM_HOOK_EVENT_SOUND, &c, &o))
        return level;
    if (o.sound_level > 4u)
        return level;                                    /* never outside the ladder (the framework already refuses it) */
    if (BO3_HOOKREQ_P8P && s_pitch_ok && o.sound_pitch != 1.0f && o.sound_pitch >= BM_HOOK_SOUND_PITCH_MIN &&
        o.sound_pitch <= BM_HOOK_SOUND_PITCH_MAX) {
        s_pend_mul = o.sound_pitch;                      /* patch 78: for the play that follows this call */
        s_pend = (int)(alt != 0);
    }
    s_changed++;
    return o.sound_level;
}

void bo3_evsound_init(void)
{
    s_ok = 0;
#if BO3_HOOKREQ_P23
    if (!census()) {
        fprintf(stderr, "[HOOKS] EVENT_SOUND: the game's bytes at the marks differ from this build's census: UNAVAILABLE\n");
        return;
    }
    s_ok = bo3_hk_offer_point(BM_HOOK_EVENT_SOUND, (1u << BM_HOOK_OBSERVE) | (1u << BM_HOOK_MODIFY), NULL) == 0;
    s_pend = -1;
    s_pitch_ok = BO3_HOOKREQ_P8P && pitch_census();
    if (s_ok && !s_pitch_ok)
        fprintf(stderr, "[HOOKS] EVENT_SOUND: the free pitch factor is not applied (BO3_HOOKREQ_P8P=OFF or its sites differ)\n");
#else
    (void)census;
#endif
}

int bo3_evsound_available(void)
{
    return s_ok;
}

uint32_t bo3_evsound_changed(void)
{
    return s_changed;
}
