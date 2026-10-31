/* bm_racers.c - G8-E7 EXPERIMENTAL: "bmashup.racers" (include/bmashup_racers.h): read-only racer queries over verified
 * car fields. Guest reads go through bm_guest.c (the runtime's mappings). MUT=n (tests) compiles one defect.
 * Version 2 (platform 0.1.8, hook request P1, gp\hookreq\drafts\bmashup_racers_v2.h): place / laps / time / phase per racer
 * (the race_service.c fields of player 1, read on every racer of the list), order(), session(). Still read only.
 * Version 3 (platform 0.1.9, main19 items 22..24, hook request P2 A2..A5; gp\hookreq\p23\SITES_VERIFIED.md s1.2..1.5, re-checked in
 * main19 tests\p23\STEP0_A.md): the racer's physics vehicle V (the pool entry whose + 0x13F4 is R, bm_vphysics.c's search) gives
 * gear (V + 0x1448 + 0x80), the damage parts (count int8 [[V+0xCC0]+0x40]+0xC, kinds [[V+0xCC0]+0x40]+0xAC4+4i, states
 * [V+0xCC4]+0x4B2+i) and the light flags the car update built ([V+0xCC0]+0x58). Speed / yaw rate / accelerations are DERIVED
 * by the host from R's world matrix (R + 0x10, RwMatrix: right, up, at, pos = R + 0x40; hirefresh.c, RT) sampled once per
 * simulation step at player 1's car update ("ap_update" observer, the game's thread). Probe-pending facts are constants
 * below (BM_P23_RACERS_*): a probe result only flips one. */
#include "bmashup_racers.h"

#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bm_events.h"
#include "bm_guest.h"
#include "plugins.h"
#include "race_service.h"
#include "takedawn_race.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 0
#endif

/* PR-A (gp\hookreq\p23\IMPLEMENTATION_PLAN.md s3): 0 = speed derived from the world position; 1 = the physics vehicle's speed
 * word V + 0xBC; 2 = player 1 from the speedometer's own object (main19 patch 37: PR-A2 FACT, the speedometer sub_00059BD0 runs
 * with ECX = 0x3FDD48, a HUD object, not V; its + 0xBC is the m/s value it shows), every other racer derived.
 * main19 patch 50 (runtime m19_r2a): source 2 READS 0 AT RUNTIME (0.0 km/h in all 324 samples while the gears changed - the wrong
 * object / view: 0x3FDD48 is not the live speedometer state outside the speedometer's own call); the default is back to 0
 * (derived: 80..214 km/h in the round-1 launch). 2 stays selectable for a later investigation only. */
#ifndef BM_P23_RACERS_SPEED_SOURCE
#define BM_P23_RACERS_SPEED_SOURCE 0
#endif
#define RC_SPEEDO 0x003FDD48u           /* the speedometer's object (PR-A2), + 0xBC = speed m/s */
/* main21 patch 71 (open item 2): the live engine speed is G + 0x54 (G = V + 0x1448, the transmission block) in RAD / S - the
 * transmission update sub_00121560 (every full physics step, sub_0011BE50) converts Idle / Max / Change-up RPM with 2 pi / 60
 * (0x3B17B8) and drives G + 0x54 toward final drive x ratio[gear] x wheel speed. PR-A2's shift dumps hold it (109 .. 850 rad/s =
 * 1,042 .. 8,121 rpm; idle 1000, redline 7600): PR-A2 looked for rpm units and missed it. Its own census below. */
#define BM_P23_RACERS_RPM_KNOWN 1
#define RC_RPM_OFF (0x1448u + 0x54u)
#define RC_RAD_TO_RPM 9.54929658f   /* 60 / 2 pi */
#define RC_RPM_MAX_RAD 2100.0f      /* 20,000 rpm: anything above (or negative, NaN) is not an engine speed */
/* PR-A: 1 once the light groups 5 / 6 (indicators) are verified per model (light_available / set_light / the lights read).
 * main19 patch 49 (owner): 1 - the renderer's lamp groups are read per model (sub_001879E0: count u8 D + 0x16AC + group, points
 * D + 0x1664 + 4 group, D = [E + 0x40], E = [V + 0xCC0]; tests\p23\STEP0_A.md), so light_available / lamp_counts tell a mod
 * whether a lamp shows; the bits themselves are written on any racer and blinked by the host. */
#define BM_P23_RACERS_INDICATORS_KNOWN 1
#define RC_LAMP_COUNT 0x16ACu           /* u8 per light group in the model data D */
#define RC_IND_BITS   0x60u             /* 0x20 group 5 (left), 0x40 group 6 (right) */
/* PR-A (A3): 1 = detach_part serves AI racers at their own car update (the mark at sub_0011BE50's entry); 0 = player 1's car
 * only, at its "ap_update". main19 patch 37: 1 (PR-A1 FACT: the entry runs for every racer, ECX = P, 6 / 6 in a race, 4 / 4 in Road
 * Rage, 1..6 calls a step; hanging (2) and detached (3) parts seen on AI cars too). */
#define BM_P23_RACERS_APPLY_PER_RACER 1
/* PR-A (A5, owner decision 4): how award_score reaches the displayed score total. 0 = UNAVAILABLE (this build: the word is not
 * verified); 2 = a host add of the verified word S + RC_SCORE_OFF (S = R + 0x10D0, the score object) at player 1's car update,
 * once PR-A shows that word is the total the HUD / results show and that an add stays consistent. (1 = through the game's award
 * sub_001994D0 tail: reserved - its ABI is not reduced.) */
#ifndef BM_P23_RACERS_SCORE_FIELD
#define BM_P23_RACERS_SCORE_FIELD 2     /* main19 patch 37: PR-A1 / PR-E FACT - S + 0x4C is the HUD SCORE (the HUD counts up to it) and the
                                         * results' BURNOUT POINTS (905 / 4,255 in p23_e2r / e1r); the game's award sub_001994D0 adds
                                         * to it too (and to S + 0xAC, the takedown points: not touched here) */
#endif
#if MUT == 52
#define RC_SCORE_OFF (0x10D0u + 0xACu)  /* defect: the takedown-points word */
#else
#define RC_SCORE_OFF (0x10D0u + 0x4Cu)  /* S + 0x4C, S = R + 0x10D0 */
#endif
#define RC_SCORE_PER_SECOND 8u
#define RC_SCORE_PER_RACE   512u
#define RC_SCORE_SLOTS      16u

#define RC_COUNT   0x0073A19Cu
#define RC_LIST    0x0073A1A8u
#define RC_CAR1    0x0073A1D0u      /* player 1's car (AP_CAR1) */
#define RC_TD      0x1138u          /* takedowns this race */
#define RC_WRECKED 0x18FAu          /* wrecked flag (u8) */
#define RC_METER   0x119Cu          /* the boost meter inside the car */
#define RC_BAR     0x38u
#define RC_MAX     0x34u
/* v2: race_service.c's fields (RS_PLACE / RS_TIME / RS_LAPS / RS_PHASE) */
#define RC_PLACE   0x10D0u          /* int16 */
#define RC_TIME    0x10DCu          /* float */
#define RC_LAPS    0x10E4u
#define RC_PHASE   0x134Cu
#define RC_LAPS_SANE 1000u
/* v3 */
#define RC_STEP     0x004A1EB4u     /* the simulation step count */
#define RC_MAT      0x10u           /* R's world matrix (RwMatrix): right + 0x00, up + 0x10, at + 0x20, pos + 0x30 */
#define RC_PW       0x0064B310u     /* the physics world (bm_vphysics.c) */
#define RC_V_R      0x13F4u         /* V + 0x13F4 = R */
#define RC_V_E      0xCC0u          /* V + 0xCC0 = the render entity E (light flags E + 0x58) */
#define RC_V_PS     0xCC4u          /* V + 0xCC4 = the part-state block (+ 0x4B2 + i) */
#define RC_GEAR     (0x1448u + 0x80u)
#define RC_SPEED    0xBCu
#define RC_JUMP_M   50.0f           /* a step that moves farther is a respawn / reset: the samples start again */

/* the physics vehicle pools (bm_vphysics.c s_pools, v1.0.2) */
static const struct { uint32_t base, stride, n, vtable; } s_pools[] = {
    { RC_PW + 0x1CB80u, 0x4AD0u, 2u, 0x003B1160u },
    { RC_PW + 0x26120u, 0x1580u, 5u, 0x003B1240u },
    { RC_PW + 0x2CCA0u, 0x1560u, 5u, 0x003B1138u },
};

static uint32_t list_count(void);

static uint32_t vehicle_of(uint32_t r)
{
    if (!r)
        return 0;
    for (size_t p = 0; p < sizeof s_pools / sizeof s_pools[0]; p++)
        for (uint32_t k = 0; k < s_pools[p].n; k++) {
            uint32_t v = s_pools[p].base + k * s_pools[p].stride, back = 0, vt = 0;
            if (bo3_guest_rd32(v, &vt) && vt == s_pools[p].vtable && bo3_guest_rd32(v + RC_V_R, &back) && back == r)
                return v;
        }
    return 0;
}

/* one racer's samples (game thread writes; get() reads the published floats) */
typedef struct rc_dyn {
    uint32_t r, step, n;            /* the racer it belongs to, the last sampled step, successive samples (<= 3) */
    float pos[3], vel[3];
    float fwd[3], right[3];
    _Atomic uint32_t have;
    _Atomic float speed, yaw, lat, lon;
} rc_dyn;
static rc_dyn s_dyn[BM_RACERS_MAX];
static _Atomic uint32_t s_ctl_owned[BM_RACERS_MAX];   /* v3 controls: bit (1 << BM_RACER_CTL_*) per racer index */

static float dot3(const float *a, const float *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static int rd_vec(uint32_t va, float *v)
{
    if (!bo3_guest_read(va, v, 12))
        return 0;
    return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

/* sample every racer once per simulation step (the "ap_update" observer: player 1's car update, the game's thread) */
static void sample_all(void)
{
    uint32_t n = list_count(), step = 0;
    if (!bo3_guest_rd32(RC_STEP, &step))
        return;
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {
        rc_dyn *d = &s_dyn[k];
        uint32_t r = 0;
        float pos[3], fwd[3], right[3], vel[3], dt;
        if (k >= n || !bo3_guest_rd32(RC_LIST + 4u * k, &r) || !r || !rd_vec(r + RC_MAT + 0x30u, pos) ||
            !rd_vec(r + RC_MAT + 0x20u, fwd) || !rd_vec(r + RC_MAT, right)) {
            d->n = 0;
            d->r = 0;
            atomic_store(&d->have, 0);
            continue;
        }
        if (d->r == r && d->n && step == d->step)
            continue;                                   /* this step was sampled already */
        if (d->r != r || !d->n || step <= d->step || step - d->step > 30u) {
            d->n = 0;                                   /* new racer, a reset of the step count or a long gap */
        }
        if (d->n) {
            dt = (float)(step - d->step) / 60.0f;
            for (int i = 0; i < 3; i++)
                vel[i] = (pos[i] - d->pos[i]) / dt;
#if MUT == 34
            if (0) {
#else
            if (sqrtf(dot3(vel, vel)) * dt > RC_JUMP_M) {
#endif
                d->n = 0;                               /* respawn / reset: start again from this sample */
            } else {
                float sp = sqrtf(dot3(vel, vel)), dv[3], c, s;
#if BM_P23_RACERS_SPEED_SOURCE == 1
                {
                    uint32_t v = vehicle_of(r);
                    float w = 0.0f;
                    if (v && bo3_guest_read(v + RC_SPEED, &w, 4) && isfinite(w))
                        sp = w;
                }
#elif BM_P23_RACERS_SPEED_SOURCE == 2 && MUT != 53
                if (r == RC_CAR1) {                     /* player 1: the speedometer's own value (AI racers stay derived) */
                    float w = -1.0f;
                    if (bo3_guest_read(RC_SPEEDO + RC_SPEED, &w, 4) && isfinite(w) && w >= 0.0f && w < 200.0f)
                        sp = w;
                }
#endif
                atomic_store(&d->speed, sp);
                if (d->n >= 2) {
                    for (int i = 0; i < 3; i++)
                        dv[i] = (vel[i] - d->vel[i]) / dt;
#if MUT == 31
                    atomic_store(&d->lon, dot3(dv, fwd));
                    atomic_store(&d->lat, dot3(dv, right));     /* defect: + = to the right */
#elif MUT == 32
                    atomic_store(&d->lon, dot3(dv, fwd) * dt);  /* defect: not divided by the step time */
                    atomic_store(&d->lat, -dot3(dv, right));
#else
                    atomic_store(&d->lon, dot3(dv, fwd));
                    atomic_store(&d->lat, -dot3(dv, right));
#endif
                }
                c = dot3(fwd, d->fwd);
                s = -dot3(fwd, d->right);               /* the forward turned toward the old left: + */
#if MUT == 33
                s = -s;                                 /* defect: yaw sign */
#endif
                atomic_store(&d->yaw, atan2f(s, c) / dt);
                memcpy(d->vel, vel, sizeof vel);
            }
        }
        d->r = r;
        d->step = step;
        memcpy(d->pos, pos, sizeof pos);
        memcpy(d->fwd, fwd, sizeof fwd);
        memcpy(d->right, right, sizeof right);
        if (d->n < 3)
            d->n++;
#if MUT == 35
        atomic_store(&d->have, d->n >= 1);              /* defect: valid from the first sample */
#else
        atomic_store(&d->have, d->n >= 3);
#endif
    }
}

/* ---- v3 controls (items 23 / 24) ---- */
extern void sub_00125A50(void);
/* main21 patch 98: the game's racer crash entries (the physics vehicle's vtable slot + 8; thiscall, 2 arguments, ret 8) */
extern void sub_00118E30(void);
extern void sub_0011FC60(void);
/* main21 patch 101: the game's crash decider (ECX = a, EBX = V, EAX = contact info; 2 stack arguments, ret 8) */
extern void sub_0010DD20(void);

/* the census: every site the controls use (default.xbe 9f497acd; tests\p23\racers_v3 checks the table against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_rc_census[] = {
    { 0x00125A50u, 22, { 0x53,0x8b,0x5c,0x24,0x08,0x8b,0x83,0xc4,0x0c,0x00,0x00,0x8a,0x8c,0x06,0xb2,0x04,0x00,0x00,0x80,0xf9,0x02,0x8d } },
    { 0x00024027u, 8, { 0x57,0x8b,0xf5,0xe8,0x21,0x1a,0x10,0x00 } },                         /* the retail call shape */
    { 0x0011BFDAu, 21, { 0x8b,0x8b,0xf4,0x13,0x00,0x00,0x8b,0x83,0xc0,0x0c,0x00,0x00,0x8a,0x91,0xff,0x18,0x00,0x00,0x08,0x50,0x58 } },
    { 0x0011BE50u, 21, { 0x55,0x8b,0xec,0x83,0xe4,0xf0,0x81,0xec,0xd4,0x00,0x00,0x00,0x53,0x8b,0xd9,0x8b,0x83,0xf4,0x13,0x00,0x00 } },
    { 0x00023F20u, 13, { 0x8b,0x87,0xc0,0x0c,0x00,0x00,0x8b,0x48,0x40,0x0f,0xbe,0x41,0x0c } }, /* part count / kinds */
    { 0x00059C05u, 8, { 0xf3,0x0f,0x10,0x81,0xbc,0x00,0x00,0x00 } },                        /* patch 37: the speedometer's read */
};
/* END-CENSUS */

/* patch 71: the engine-speed sites (default.xbe 9f497acd; main21 tests\p6 checks them against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_rpm_census[] = {
    { 0x001215A3u, 24, { 0xf3,0x0f,0x10,0x1d,0xb8,0x17,0x3b,0x00,0xf3,0x0f,0x10,0x46,0x20,0xf3,0x0f,0x59,0x44,0x86,0x04,0xf3,0x0f,0x10,
                         0x76,0x24 } },   /* movss xmm3, [2 pi / 60]; final drive; x ratio[gear]; idle rpm */
    { 0x003B17B8u, 4,  { 0x50,0x77,0xd6,0x3d } },                                            /* 0.10471976 = 2 pi / 60 */
};
/* END-CENSUS */
/* main21 patch 98 (wreck): the crash slot of each vehicle class, both entries' first bytes and the game's own "nobody" cause
 * (sub_0010F370: ECX = s8 [[V + 0x13F4] + 0x19BC] before the crash decider; default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_wk_census[] = {
    { 0x003B1168u, 4,  { 0x30,0x8e,0x11,0x00 } },                                            /* vt 0x3B1160 + 8 = 0x118E30 */
    { 0x003B1248u, 4,  { 0x60,0xfc,0x11,0x00 } },                                            /* vt 0x3B1240 + 8 = 0x11FC60 */
    { 0x003B1140u, 4,  { 0x60,0xfc,0x11,0x00 } },                                            /* vt 0x3B1138 + 8 = 0x11FC60 */
    { 0x00118E30u, 24, { 0x53,0x56,0x8b,0xd9,0x57,0x8b,0xbb,0xc4,0x0c,0x00,0x00,0x8d,0xb3,0x80,0x3a,0x00,0x00,0xe8,0x1a,0x00,
                         0x00,0x00,0x8b,0x44 } },
    { 0x0011FC60u, 24, { 0x83,0xec,0x10,0x53,0x8b,0xd9,0x8a,0x83,0x10,0x02,0x00,0x00,0x84,0xc0,0x0f,0x85,0x08,0x02,0x00,0x00,
                         0x8a,0x44,0x24,0x18 } },   /* + 0x210 crashed -> skip; + 0x218 = (s8) a */
    { 0x0010F484u, 13, { 0x8b,0x8e,0xf4,0x13,0x00,0x00,0x0f,0xbe,0x89,0xbc,0x19,0x00,0x00 } },
    /* main21 patch 101: the same site's call of 0x10DD20 (arguments 0 and 0x64ACE8, EAX cleared, EBX = ESI), the decider's
     * entry, its mode hook ([[0x4D5370] + 0x1B8] vt + 0x48) and its class-slot call (vt + 8 with a, info), the blame's checks
     * (phase 3, [j + 0x1198] + 0x18FA) and stores (0x197504: j + 0x15A8[v] = j + 0x10DC, + 0x15C0[v] = 0, + 0x15C6[v]) and the
     * confirm's counter call (0x1970BC: edi = victim, esi = ebp, call 0x198E60) */
    { 0x0010F491u, 15, { 0x53,0x68,0xe8,0xac,0x64,0x00,0x33,0xc0,0x8b,0xde,0xe8,0x80,0xe8,0xff,0xff } },
    { 0x0010DD20u, 24, { 0x55,0x8b,0xec,0x83,0xe4,0xf0,0x81,0xec,0xc8,0x00,0x00,0x00,0x56,0x57,0x8b,0xf8,0x8a,0x83,0x10,0x02,
                         0x00,0x00,0x84,0xc0 } },
    { 0x0010DD53u, 24, { 0x8b,0x0d,0x70,0x53,0x4d,0x00,0x8b,0x89,0xb8,0x01,0x00,0x00,0x8b,0x11,0x88,0x44,0x24,0x12,0x8b,0x83,
                         0xf4,0x13,0x00,0x00 } },
    { 0x0010DD74u, 9,  { 0x8b,0x03,0x57,0x56,0x8b,0xcb,0xff,0x50,0x08 } },
    { 0x001974E6u, 24, { 0x83,0xb8,0x4c,0x13,0x00,0x00,0x03,0x8a,0x96,0xb8,0x05,0x00,0x00,0x74,0x37,0x8b,0x98,0x98,0x11,0x00,
                         0x00,0x80,0xbb,0xfa } },
    { 0x00197504u, 24, { 0x0f,0xbe,0x89,0xbc,0x19,0x00,0x00,0x8b,0x98,0xdc,0x10,0x00,0x00,0x89,0x9c,0x88,0xa8,0x15,0x00,0x00,
                         0x33,0xdb,0x88,0x9c } },
    { 0x0019751Cu, 12, { 0x01,0xc0,0x15,0x00,0x00,0x88,0x94,0x01,0xc6,0x15,0x00,0x00 } },
    { 0x001970BCu, 10, { 0x8b,0x3c,0x01,0x8b,0xf5,0xe8,0x9a,0x1d,0x00,0x00 } },
};
/* END-CENSUS */
static _Atomic int s_rpm_census_ok = -1;
static int rpm_census(void)
{
    int c = atomic_load(&s_rpm_census_ok);
    if (c >= 0)
        return c;
#if MUT == 71
    c = 1;                                      /* defect: the engine-speed sites not checked */
#else
    c = 1;
    for (size_t k = 0; c && k < sizeof s_rpm_census / sizeof s_rpm_census[0]; k++) {
        uint8_t b[24];
        if (!bo3_guest_read(s_rpm_census[k].va, b, s_rpm_census[k].n) || memcmp(b, s_rpm_census[k].b, s_rpm_census[k].n))
            c = 0;
    }
#endif
    atomic_store(&s_rpm_census_ok, c);
    return c;
}

#define RC_LIGHT_BYTE 0x18FFu       /* R + 0x18FF: ORed into the light flags by the physics step (0x11BFE6), retail writes 0 only;
                                     * patch 103: NOT written - the car update clears it every update (sub_0018D790 loc_0018D985)
                                     * before the OR reads it; read only by the patch-99 line */
/* main21 patch 98: wreck(racer, cause) */
#ifndef BO3_HOOKREQ_P28W
#define BO3_HOOKREQ_P28W 0          /* unit tests without the option: version 4, wreck UNSUPPORTED; the game: CMake ON */
#endif
/* main21 patch 104: set_tail_stand_in (version 6) */
#ifndef BO3_HOOKREQ_P8T
#define BO3_HOOKREQ_P8T 0           /* unit tests without the option: version as before, stand-in UNSUPPORTED; the game: CMake ON */
#endif
#define RC_VERSION (BO3_HOOKREQ_P28W ? (BO3_HOOKREQ_P8T ? BM_RACERS_VERSION : BM_RACERS_VERSION_5) : BM_RACERS_VERSION_4)
#define RC_GAME_INDEX 0x19BCu       /* s8 R + 0x19BC: the racer's own index as the crash code passes it */
#define RC_V_CRASHED  0x210u        /* u8 V + 0x210: crashed (the crash entry returns at once when set) */
#define RC_V_BY       0x218u        /* s8 V + 0x218: crashed by (the crash entry stores its first argument) */
/* main21 patch 101: the crash decider sub_0010DD20 and the takedown staging of the blame sub_00197430 (0x197504) */
#define RC_MODE_PTR   0x004D5370u   /* [0x4D5370] + 0x1B8 = the game-mode object the decider asks (vt + 0x48) */
#define RC_MODE_OBJ   0x1B8u
#define RC_CRASH_TAB  0x0064ACE8u   /* the crash-record table every decider call passes (record = + a * 0x3C + 0x110) */
#define RC_SCORER     0x1198u       /* [car + 0x1198]: the racer object the blame reads the index / crashed byte from */
#define RC_TD_STAGE   0x15A8u       /* f32 car + 0x15A8[v]: staged takedown of victim v (the attacker's clock) */
#define RC_TD_AFTER   0x15C0u       /* u8 car + 0x15C0[v]: aftertouch flag */
#define RC_TD_PSYCHE  0x15C6u       /* u8 car + 0x15C6[v]: psyche-out flag */
#define RC_TD_SLOTS   6u            /* 0x15A8 + 4 * 6 = 0x15C0: six victims */
#define RC_TD_WATCH   240u          /* steps the probe line waits for the game's confirm (it counts ~1 s after the stage) */
#define RC_FAMILIES   3u
#define RC_RATE_STEPS 60u
/* main21 patch 95: REVERSE (7) = 0x80, the bit the car update sets in reverse gear ([car + 0x14C8] == -1, 0x11BFD0) */
#ifndef BO3_HOOKREQ_P26R
#define BO3_HOOKREQ_P26R 0          /* unit tests without the option: as before (the old suites); the game: CMake ON */
#endif
#if MUT == 44
static const uint8_t k_light_bit[8] = { 0, 0xFF, 0x08, 0x10, 0x20, 0x40, 0x60, 0x80 };   /* defect: HEAD writes every bit */
#else
static const uint8_t k_light_bit[8] = { 0, 0x04, 0x08, 0x10, 0x20, 0x40, 0x60, 0x80 };   /* by BM_LIGHT_*: head .. hazard, reverse */
#endif

static _Atomic(uintptr_t) s_owner[BM_RACERS_MAX][RC_FAMILIES + 1];
static _Atomic uint32_t s_light_want[BM_RACERS_MAX];   /* patch 103: the ON bits ORed into E + 0x58 at the patch-77 mark */
/* main21 patch 77 (open item 5): light OFF. The car update sub_0011BE50 rebuilds the light flags E + 0x58 every update (0 at
 * loc_0011BF4F, brake 0x10 / reverse 0x80, then the OR of R + 0x18FF); the renderer sub_00187C70 draws every lamp from those bits
 * (head 0x02 / 0x04, tail 0x08, brake 0x10, indicators 0x20 / 0x40). The mark at loc_0011BFEF (right after the OR) clears this
 * service's OFF bits of that racer, so OFF holds for the rest of the update and the draw. Patch 103: the same mark ORs in
 * the ON bits (s_light_want), OFF winning. */
#ifndef BO3_HOOKREQ_P7L
#define BO3_HOOKREQ_P7L 1           /* unit tests: the CMake option is not there */
#endif
#if MUT == 58
static const uint8_t k_off_bit[8] = { 0, 0x04, 0x08, 0x10, 0x20, 0x40, 0x60, 0x80 };   /* defect: head OFF leaves the 0x02 beam */
#elif MUT == 59
static const uint8_t k_off_bit[8] = { 0, 0x06, 0x08, 0x10, 0x20, 0x40, 0x60, 0x00 };   /* defect: reverse OFF clears nothing */
#else
static const uint8_t k_off_bit[8] = { 0, 0x06, 0x08, 0x10, 0x20, 0x40, 0x60, 0x80 };   /* head = both beams (0x02 / 0x04) */
#endif
static _Atomic uint32_t s_light_off[BM_RACERS_MAX];    /* E + 0x58 bits forced off after the game's rebuild */
static _Atomic uint32_t s_off_marks;                    /* flag bytes changed by the mark (tests) */
static uint32_t s_on_seen[BM_RACERS_MAX], s_on_lines;   /* patch 99: the light-ON probe line (game thread) */
static int s_loff_census = 0;
/* main21 patch 104 (tail lamps option b): the tail stand-in. s_tail_f = factor in permille (0 off); s_tail_e = the racer's render
 * entity E, recorded at the patch-77 light mark (the draw mark sub_00187C70 0x187D74 sees only E, so it matches E, never traffic) */
static _Atomic uint32_t s_tail_f[BM_RACERS_MAX];
static _Atomic uint32_t s_tail_e[BM_RACERS_MAX];
static _Atomic uint32_t s_tail_calls, s_tail_swaps;     /* tail-mark calls / group 1 -> 2 swaps (tests, DIAG) */
static uint32_t s_tail_lines;                           /* [DIAG] tail stand-in lines this race (game thread) */
static int s_tail_census = 0;
static _Atomic uint32_t s_detach_req[BM_RACERS_MAX];   /* parts waiting for the apply point (bit i) */
static _Atomic uint32_t s_detach_done[BM_RACERS_MAX];  /* parts detached by a plugin this race */
static _Atomic uint32_t s_wreck_req[BM_RACERS_MAX];    /* patch 98: 0 none, else cause + 2 (1 = NONE) */
static _Atomic uint32_t s_wreck_r[BM_RACERS_MAX];      /* the racer R the request was made for */
static uint32_t s_wreck_step[BM_RACERS_MAX], s_wreck_have[BM_RACERS_MAX];   /* the last applied wreck's step (game thread) */
static _Atomic uint32_t s_wrecks_done, s_wreck_refused;
static _Atomic uint32_t s_wreck_after[BM_RACERS_MAX];  /* patch 105: 1 = stage the credit as an aftertouch takedown */
static _Atomic uint32_t s_blast_wrecks;                /* patch 105: wrecks queued by Crash Breaker blasts (tests, DIAG) */
static uint32_t s_tdw_car[BM_RACERS_MAX], s_tdw_before[BM_RACERS_MAX], s_tdw_step[BM_RACERS_MAX];  /* patch 101 (game thread) */
static _Atomic uint32_t s_td_staged, s_td_confirmed;
static _Atomic int s_wk_census_ok = -1;
static uint32_t s_rate[BM_RACERS_MAX][BM_RACERS_LIGHT_CHANGES_PER_SECOND], s_rate_n[BM_RACERS_MAX];
static _Atomic int s_rc_census_ok = -1;
static _Atomic uint32_t s_mark_calls, s_mark_other;
static uint32_t s_prev_state;
static uint32_t (*s_state_fn)(void);
static int s_self;

static int rc_census(void)
{
    int c = atomic_load(&s_rc_census_ok);
    if (c >= 0)
        return c;
    if (!g_xbox_mem_offset)
        return 0;
#if MUT == 50
    c = 1;                                      /* defect: the sites' bytes not checked */
#else
    c = BO3_HOOKREQ_P23;
    for (size_t k = 0; c && k < sizeof s_rc_census / sizeof s_rc_census[0]; k++) {
        uint8_t b[24];
        if (!bo3_guest_read(s_rc_census[k].va, b, s_rc_census[k].n) || memcmp(b, s_rc_census[k].b, s_rc_census[k].n))
            c = 0;
    }
#endif
    atomic_store(&s_rc_census_ok, c);
    if (!c)
        fprintf(stderr, "[RACERS] bmashup.racers 3: the controls are UNSUPPORTED on this build (%s)\n",
                BO3_HOOKREQ_P23 ? "a site's bytes differ from the verified build" : "BO3_HOOKREQ_P23=OFF");
    return c;
}

static uint32_t step_now(void)
{
    uint32_t s = 0;
    bo3_guest_rd32(RC_STEP, &s);
    return s;
}

static uint32_t racer_car(uint32_t racer)
{
    uint32_t car = 0;
    if (racer >= list_count() || !bo3_guest_rd32(RC_LIST + 4u * racer, &car))
        return 0;
    return car;
}

static int take(td_host *host, uint32_t racer, uint32_t fam)
{
    uintptr_t none = 0;
    if (atomic_compare_exchange_strong(&s_owner[racer][fam], &none, (uintptr_t)host) || none == (uintptr_t)host) {
        atomic_fetch_or(&s_ctl_owned[racer], 1u << fam);
        return 1;
    }
    return 0;
}

static void give_back(uint32_t racer, uint32_t fam)
{
    atomic_store(&s_owner[racer][fam], 0);
    atomic_fetch_and(&s_ctl_owned[racer], ~(1u << fam));
    if (fam == BM_RACER_CTL_LIGHTS) {
#if MUT != 46
        atomic_store(&s_light_want[racer], 0);  /* patch 103: nothing ORed in at the next mark (the game's lamps) */
#endif
#if MUT != 57
        atomic_store(&s_light_off[racer], 0);   /* patch 77: the game's own lights again */
#endif
#if MUT != 88
        atomic_store(&s_tail_f[racer], 0);      /* patch 104: no stand-in (the game's tail draw) */
#endif
        atomic_store(&s_tail_e[racer], 0);
    } else if (fam == BM_RACER_CTL_DAMAGE) {
        atomic_store(&s_detach_req[racer], 0);
    }
}

/* part state byte of part i of V, or -1 */
static int part_state(uint32_t v, uint32_t i, uint32_t *count)
{
    uint32_t e = 0, d = 0, ps = 0;
    int8_t cnt = 0;
    uint8_t st = 0;
    if (!v || !bo3_guest_rd32(v + RC_V_E, &e) || !e || !bo3_guest_rd32(e + 0x40u, &d) || !d || !bo3_guest_read(d + 0xCu, &cnt, 1) ||
        cnt <= 0 || !bo3_guest_rd32(v + RC_V_PS, &ps) || !ps)
        return -1;
    *count = (uint32_t)cnt > BM_RACERS_PARTS_MAX ? BM_RACERS_PARTS_MAX : (uint32_t)cnt;
    if (i >= *count || !bo3_guest_read(ps + 0x4B2u + i, &st, 1))
        return -1;
    return st;
}

static int32_t TD_CALL r_detach_part(td_host *host, uint32_t racer, uint32_t part)
{
    uint32_t car, v, count = 0;
    int st;
    if (!host)
        return BM_RACERS_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !rc_census()))
        return BM_RACERS_UNSUPPORTED;
    if (!list_count())
        return BM_RACERS_NOT_IN_RACE;
    if (racer >= BM_RACERS_MAX || !(car = racer_car(racer)))
        return BM_RACERS_NO_RACER;
#if !BM_P23_RACERS_APPLY_PER_RACER && MUT != 47
    if (car != RC_CAR1)
        return BM_RACERS_UNSUPPORTED;           /* an AI racer: the per-racer apply point is not verified yet */
#endif
    v = vehicle_of(car);
    if (part >= BM_RACERS_PARTS_MAX)
        return BM_RACERS_OUT_OF_RANGE;
    st = part_state(v, part, &count);
    if (!v || count == 0)
        return BM_RACERS_UNAVAILABLE;
    if (part >= count)
        return BM_RACERS_OUT_OF_RANGE;
#if MUT != 42
    if (atomic_load(&s_detach_done[racer]) & (1u << part))
        return BM_RACERS_ALREADY;
#endif
#if MUT != 41
    if (st != 2)
        return BM_RACERS_NOT_HANGING;
#endif
    if (!take(host, racer, BM_RACER_CTL_DAMAGE))
        return BM_RACERS_CONFLICT;
    atomic_fetch_or(&s_detach_req[racer], 1u << part);
    return BM_RACERS_OK;
}

static uint32_t avail_mask(void)
{
    uint32_t m = (1u << BM_LIGHT_HEAD) | (1u << BM_LIGHT_TAIL) | (1u << BM_LIGHT_BRAKE);
#if BM_P23_RACERS_INDICATORS_KNOWN
    m |= (1u << BM_LIGHT_IND_LEFT) | (1u << BM_LIGHT_IND_RIGHT) | (1u << BM_LIGHT_HAZARD);   /* accepted (blinked) on any racer */
#endif
    if (BO3_HOOKREQ_P26R)
        m |= 1u << BM_LIGHT_REVERSE;
    return m;
}

/* patch 49: the racer's model's lamp-group 5 / 6 point counts (the renderer's sub_001879E0 reads D + 0x16AC + group) */
static int lamp_counts_of(uint32_t car, uint32_t *g5, uint32_t *g6)
{
    uint32_t v = vehicle_of(car), e = 0, d = 0;
    uint8_t c[2] = { 0, 0 };
    if (!v || !bo3_guest_rd32(v + RC_V_E, &e) || !e || !bo3_guest_rd32(e + 0x40u, &d) || !d)
        return 0;
#if MUT == 55
    if (!bo3_guest_read(d + RC_LAMP_COUNT + 4u, c, 2))            /* defect: groups 4 / 5 read */
#else
    if (!bo3_guest_read(d + RC_LAMP_COUNT + 5u, c, 2))
#endif
        return 0;
    *g5 = c[0];
    *g6 = c[1];
    return 1;
}

/* main21 patch 81 (racers 4): the racer's world pose from R + RC_MAT (right + 0, up + 0x10, at + 0x20, pos + 0x30).
 * MUT 74 the forward axis read from the right row, 75 the caller's room ignored */
static int32_t TD_CALL r_get_pose(td_host *host, uint32_t racer, bm_racer_pose *out)
{
    bm_racer_pose o;
    uint32_t car = 0;
    if (!host || !out || out->struct_size < 8u)
        return BM_RACERS_BAD_ARG;
    if (racer >= BM_RACERS_MAX || racer >= list_count())
        return BM_RACERS_NO_RACER;
    if (!bo3_guest_rd32(RC_LIST + 4u * racer, &car) || !car)
        return BM_RACERS_UNAVAILABLE;
    memset(&o, 0, sizeof o);
#if MUT == 74
    if (!rd_vec(car + RC_MAT + 0x30u, o.pos) || !rd_vec(car + RC_MAT, o.fwd) || !rd_vec(car + RC_MAT + 0x10u, o.up) ||
#else
    if (!rd_vec(car + RC_MAT + 0x30u, o.pos) || !rd_vec(car + RC_MAT + 0x20u, o.fwd) || !rd_vec(car + RC_MAT + 0x10u, o.up) ||
#endif
        !rd_vec(car + RC_MAT, o.right))
        return BM_RACERS_UNAVAILABLE;
    o.index = racer;
#if MUT == 75
    o.struct_size = (uint32_t)sizeof o;
#else
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
#endif
    memcpy(out, &o, o.struct_size);
    return BM_RACERS_OK;
}

static int32_t TD_CALL r_lamp_counts(td_host *host, uint32_t racer, uint32_t *g5, uint32_t *g6)
{
    uint32_t car;
    if (!host || !g5 || !g6)
        return BM_RACERS_BAD_ARG;
    *g5 = *g6 = 0;
    if (racer >= BM_RACERS_MAX || !(car = racer_car(racer)))
        return BM_RACERS_NO_RACER;
    return lamp_counts_of(car, g5, g6) ? BM_RACERS_OK : BM_RACERS_UNAVAILABLE;
}

static uint32_t TD_CALL r_light_available(td_host *host, uint32_t racer)
{
    uint32_t car, g5 = 0, g6 = 0, m;
    if (!host || !BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !rc_census()) || racer >= BM_RACERS_MAX || !(car = racer_car(racer)))
        return 0;
    m = (1u << BM_LIGHT_HEAD) | (1u << BM_LIGHT_TAIL) | (1u << BM_LIGHT_BRAKE);
#if BM_P23_RACERS_INDICATORS_KNOWN
    if (lamp_counts_of(car, &g5, &g6))
        m |= (g5 ? 1u << BM_LIGHT_IND_LEFT : 0u) | (g6 ? 1u << BM_LIGHT_IND_RIGHT : 0u);
#endif
    if (BO3_HOOKREQ_P26R)
        m |= 1u << BM_LIGHT_REVERSE;                /* main21 patch 95: every retail car draws it */
    return m;
}

/* patch 77: the light-OFF site (default.xbe 9f497acd; main21 tests\p7\run_light_off.py checks them against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_loff_rows[] = {
    { 0x0011BF4Fu, 10, { 0x8b,0x8b,0xc0,0x0c,0x00,0x00,0xc6,0x41,0x58,0x00 } },              /* E + 0x58 = 0 (the rebuild) */
    { 0x0011BFEFu, 12, { 0x8b,0x83,0xf4,0x13,0x00,0x00,0x8b,0x80,0x20,0x19,0x00,0x00 } },    /* right after the OR (the mark) */
};
/* END-CENSUS */
static int loff_census(void)
{
    if (!BO3_HOOKREQ_P7L)
        return 0;
    if (s_loff_census != 1) {                           /* re-read until it matches */
        s_loff_census = 1;
        for (size_t k = 0; k < sizeof s_loff_rows / sizeof s_loff_rows[0]; k++) {
            uint8_t b[24];
            if (!bo3_guest_read(s_loff_rows[k].va, b, s_loff_rows[k].n) || memcmp(b, s_loff_rows[k].b, s_loff_rows[k].n))
                s_loff_census = 0;
        }
    }
    return s_loff_census;
}

/* patch 104: the tail stand-in site, sub_00187C70's running-tail draw (default.xbe 9f497acd; test bit 0x08, push colour 0x4161D0,
 * at 0x187D74 (EDX = 1, ESI / EDI passed) the call of sub_001879E0 - which draws count = u8 [D + 0x16AC + group] lamps, D = [E + 0x40])
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_tail_rows[] = {
    { 0x00187D59u, 21, { 0xa8,0x08,0x74,0x23,0x51,0x0f,0x28,0xc4,0xf3,0x0f,0x59,0xc5,0xf3,0x0f,0x11,0x04,0x24,0x8d,0x4c,0x24,0x14 } },
    { 0x00187D6Eu, 18, { 0x51,0x68,0xd0,0x61,0x41,0x00,0xba,0x01,0x00,0x00,0x00,0x56,0x57,0xe8,0x60,0xfc,0xff,0xff } },  /* the mark */
};
/* END-CENSUS */
static int tail_census(void)
{
    if (!BO3_HOOKREQ_P8T)
        return 0;
#if MUT == 86
    return 1;                                           /* defect: the site's bytes not checked */
#endif
    if (s_tail_census != 1) {
        s_tail_census = 1;
        for (size_t k = 0; k < sizeof s_tail_rows / sizeof s_tail_rows[0]; k++) {
            uint8_t b[24];
            if (!bo3_guest_read(s_tail_rows[k].va, b, s_tail_rows[k].n) || memcmp(b, s_tail_rows[k].b, s_tail_rows[k].n))
                s_tail_census = 0;
        }
    }
    return s_tail_census;
}

/* main21 patch 86 (diagnostics, probe S4c): the light-OFF mark's counters and bounded [DIAG] lines (game thread; reset per race) */
static uint32_t s_dl_calls, s_dl_with_off, s_dl_matched, s_dl_cleared, s_dl_lines;

void bo3_racers_diag_lifecycle(uint32_t kind)
{
    if (s_dl_calls)
        fprintf(stderr, "[DIAG] light-off summary (%s): mark calls %u, with an OFF request %u, racer matched %u, bits cleared %u\n",
                kind == 2u ? "race exit" : "load", (unsigned)s_dl_calls, (unsigned)s_dl_with_off, (unsigned)s_dl_matched,
                (unsigned)s_dl_cleared);
    s_dl_calls = s_dl_with_off = s_dl_matched = s_dl_cleared = s_dl_lines = 0;
    if (atomic_load(&s_tail_calls))
        fprintf(stderr, "[DIAG] tail stand-in summary (%s): tail draws %u, brake-group stand-ins %u\n",
                kind == 2u ? "race exit" : "load", (unsigned)atomic_load(&s_tail_calls), (unsigned)atomic_load(&s_tail_swaps));
    atomic_store(&s_tail_calls, 0);
    atomic_store(&s_tail_swaps, 0);
#if MUT != 87
    memset(s_on_seen, 0, sizeof s_on_seen);     /* patch 104: the light-on cap (16 lines) is per race, not per session */
    s_on_lines = 0;
#endif
    s_tail_lines = 0;
}

/* patch 77 mark (generated code, sub_0011BE50 loc_0011BFEF; p = the physics car, EBX): this racer's lamps in E + 0x58.
 * main21 patch 103: E + 0x58 = (f | on) & ~off - ON is ORed in here (the blink's off phase applied), OFF wins. The racer byte
 * R + 0x18FF the game ORs just before is cleared by the game's own car update (sub_0018D790 loc_0018D985) before the physics
 * step reads it, so a write there never showed (S7 / S8d). */
void bo3_racers_gen_light_off(uint32_t p)
{
    uint32_t r = 0, e = 0, n, on, off;
    uint8_t f, nf;
    s_dl_calls++;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P7L || !p || !bo3_guest_rd32(p + 0x13F4u, &r) || !r)
        return;
    n = list_count();
    /* patch 104: the render entity E of a racer with a tail stand-in, for the draw mark (which sees only E) */
    for (uint32_t k = 0; BO3_HOOKREQ_P8T && k < n && k < BM_RACERS_MAX; k++)
        if (atomic_load(&s_tail_f[k]) && racer_car(k) == r) {
            uint32_t te = 0;
            if (bo3_guest_rd32(p + RC_V_E, &te) && te && atomic_load(&s_tail_e[k]) != te)
                atomic_store(&s_tail_e[k], te);
            break;
        }
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++)
        if (atomic_load(&s_light_off[k])) {
            s_dl_with_off++;
            break;
        }
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++) {
        on = atomic_load(&s_light_want[k]);
        off = atomic_load(&s_light_off[k]);
#if MUT == 85
        on = 0;                                         /* defect: ON not applied at the mark (the pre-103 behaviour) */
#endif
#if MUT == 56
        if (!off && !on)                                /* defect: any racer's lamps applied to this car */
#else
        if ((!off && !on) || racer_car(k) != r)
#endif
            continue;
#if MUT != 54
        if ((on & RC_IND_BITS) && (step_now() % BM_RACERS_BLINK_STEPS) >= BM_RACERS_BLINK_STEPS / 2u)
            on &= ~RC_IND_BITS;                         /* patch 49: the off phase of the host's indicator blink */
#endif
        if (!bo3_guest_rd32(p + 0xCC0u, &e) || !e || !bo3_guest_read(e + 0x58u, &f, 1))
            return;
        nf = (uint8_t)((f | on) & ~off);                /* set_light keeps on & off disjoint per racer; OFF wins over the game */
        if (off) {
            s_dl_matched++;
            if (s_dl_lines < 12u && (s_dl_matched == 1u || s_dl_matched % 600u == 0u)) {
                uint8_t g = 0;
                s_dl_lines++;
                bo3_guest_read(r + 0x10u + 0x58u, &g, 1);
                fprintf(stderr, "[DIAG] light-off mark: racer %u P %08x R %08x E %08x (R + 0x10 = %08x%s) E+0x58 %02x off %02x on %02x "
                        "-> %02x, [R + 0x68] %02x\n", (unsigned)k, (unsigned)p, (unsigned)r, (unsigned)e, (unsigned)(r + 0x10u),
                        e == r + 0x10u ? ", the lamp draw's entity" : ", NOT the lamp draw's entity", (unsigned)f, (unsigned)off,
                        (unsigned)on, (unsigned)nf, (unsigned)g);
            }
            if (f & off)
                s_dl_cleared++;
        }
        /* main21 patch 99 (S7: HEADLIGHTS On drew no lamps), patch 103: the flags before -> after the OR-in, what the draw sees */
        if (atomic_load(&s_light_want[k]) && s_on_lines < 16u && s_on_seen[k]++ % 600u == 0u) {
            uint32_t d = 0;
            uint8_t lb = 0, gc[7] = { 0 };
            s_on_lines++;
            bo3_guest_read(r + RC_LIGHT_BYTE, &lb, 1);
            if (bo3_guest_rd32(e + 0x40u, &d) && d)
                bo3_guest_read(d + RC_LAMP_COUNT, gc, 7);
            fprintf(stderr, "[DIAG] light-on: racer %u R %08x want %02x on %02x off %02x R+0x18FF %02x E %08x E+0x58 %02x -> %02x "
                    "D %08x groups 0..6 = %u %u %u %u %u %u %u\n", (unsigned)k, (unsigned)r, (unsigned)atomic_load(&s_light_want[k]),
                    (unsigned)on, (unsigned)off, (unsigned)lb, (unsigned)e, (unsigned)f, (unsigned)nf, (unsigned)d,
                    gc[0], gc[1], gc[2], gc[3], gc[4], gc[5], gc[6]);
        }
        if (nf != f) {
            bo3_guest_write(e + 0x58u, &nf, 1);
            atomic_fetch_add(&s_off_marks, 1);
        }
        return;
    }
}

/* patch 104 mark (generated code, sub_00187C70 0x187D74, the running-tail draw (bit 0x08) after mov edx, 1; e = E (ESI), sp = ESP:
 * [sp] colour 0x4161D0, [sp + 4] vector, [sp + 8] scale = the tail scale): the group to draw. A racer with a stand-in whose model
 * has no group-1 lamps but group-2 lamps -> 2 (the brake lamps at the tail colour, scale x factor <= 1.0); anything else -> 1. */
uint32_t bo3_racers_gen_tail(uint32_t e, uint32_t sp)
{
    atomic_fetch_add(&s_tail_calls, 1);
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P8T || !e)
        return 1u;
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {
        uint32_t f = atomic_load(&s_tail_f[k]), d = 0;
        uint8_t c[2] = { 0, 0 };
        float sc = 0.0f, ns;
#if MUT == 89
        if (!f)                                         /* defect: any car's E (traffic too) */
#else
        if (!f || atomic_load(&s_tail_e[k]) != e)
#endif
            continue;
        if (!bo3_guest_rd32(e + 0x40u, &d) || !d || !bo3_guest_read(d + RC_LAMP_COUNT + 1u, c, 2))
            return 1u;
#if MUT == 90
        if (c[1] == 0u)                                 /* defect: models with a group 1 swapped too */
#else
        if (c[0] != 0u || c[1] == 0u)                   /* group 1 present (the game's tail) or no brake lamps either */
#endif
            return 1u;
        if (bo3_guest_read(sp + 8u, &sc, 4) && isfinite(sc)) {
            ns = sc * (float)f / 1000.0f;
            bo3_guest_write(sp + 8u, &ns, 4);
        }
        atomic_fetch_add(&s_tail_swaps, 1);
        if (s_tail_lines < 8u && (atomic_load(&s_tail_swaps) == 1u || atomic_load(&s_tail_swaps) % 600u == 0u)) {
            s_tail_lines++;
            fprintf(stderr, "[DIAG] tail stand-in: racer %u E %08x D %08x groups 1 / 2 = %u / %u factor %u scale %.3f -> %.3f, group 1 -> 2\n",
                    (unsigned)k, (unsigned)e, (unsigned)d, c[0], c[1], (unsigned)f, (double)sc, (double)(sc * (float)f / 1000.0f));
        }
        return 2u;
    }
    return 1u;
}

uint32_t bo3_bm_racers_tail_swaps(void) { return atomic_load(&s_tail_swaps); }   /* patch 104 (tests) */
uint32_t bo3_bm_racers_tail_calls(void) { return atomic_load(&s_tail_calls); }

uint32_t bo3_bm_racers_off_marks(void) { return atomic_load(&s_off_marks); }
uint32_t bo3_bm_racers_on_lines(void) { return s_on_lines; }   /* patch 99 (tests) */

/* one light change of this racer within BM_RACERS_LIGHT_CHANGES_PER_SECOND a second: 1 (counted) or 0 (RATE) */
static int light_rate_take(uint32_t racer)
{
#if MUT != 45
    uint32_t s = step_now(), k, recent = 0;
    for (k = 0; k < s_rate_n[racer]; k++)
        recent += s - s_rate[racer][k] < RC_RATE_STEPS;
    if (recent >= BM_RACERS_LIGHT_CHANGES_PER_SECOND)
        return 0;
    if (s_rate_n[racer] < BM_RACERS_LIGHT_CHANGES_PER_SECOND) {
        s_rate[racer][s_rate_n[racer]++] = s;
    } else {
#if MUT == 91
        k = s % BM_RACERS_LIGHT_CHANGES_PER_SECOND;     /* defect (before patch 104): one slot per step, the limit leaks once full */
#else
        uint32_t old = 0;                               /* patch 104: replace the oldest change (the ring by step leaked) */
        for (k = 1; k < BM_RACERS_LIGHT_CHANGES_PER_SECOND; k++)
            if (s - s_rate[racer][k] > s - s_rate[racer][old])
                old = k;
        k = old;
#endif
        s_rate[racer][k] = s;
    }
#else
    (void)racer;
#endif
    return 1;
}

static int32_t TD_CALL r_set_light(td_host *host, uint32_t racer, uint32_t light, uint32_t state)
{
    uint32_t want, now, bit, off, noff;
    if (!host)
        return BM_RACERS_BAD_ARG;
#if MUT == 60
    if (light < BM_LIGHT_HEAD || light > BM_LIGHT_HAZARD || state > BM_LIGHT_ON)   /* defect: no REVERSE */
#else
    if (light < BM_LIGHT_HEAD || light > (BO3_HOOKREQ_P26R ? BM_LIGHT_REVERSE : BM_LIGHT_HAZARD) || state > BM_LIGHT_ON)
#endif
        return BM_RACERS_OUT_OF_RANGE;
#if MUT != 43
    if (state == BM_LIGHT_OFF && !(BO3_HOOKREQ_P23 && loff_census()))
        return BM_RACERS_UNSUPPORTED;           /* no light-OFF mark in this build / its site differs (the OR cannot clear) */
#endif
#if MUT != 83
    if (state == BM_LIGHT_ON && !(BO3_HOOKREQ_P23 && loff_census()))
        return BM_RACERS_UNSUPPORTED;           /* patch 103: ON is ORed in at the same mark */
#endif
    if (!BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !rc_census()) || !(avail_mask() & (1u << light)))
        return BM_RACERS_UNSUPPORTED;
    if (!list_count())
        return BM_RACERS_NOT_IN_RACE;
    if (racer >= BM_RACERS_MAX || !racer_car(racer))
        return BM_RACERS_NO_RACER;
    if (atomic_load(&s_owner[racer][BM_RACER_CTL_LIGHTS]) && atomic_load(&s_owner[racer][BM_RACER_CTL_LIGHTS]) != (uintptr_t)host)
        return BM_RACERS_CONFLICT;
    bit = k_light_bit[light];
    want = atomic_load(&s_light_want[racer]);
    now = state == BM_LIGHT_ON ? (want | bit) : (want & ~bit);
    off = atomic_load(&s_light_off[racer]);
    noff = state == BM_LIGHT_OFF ? (off | k_off_bit[light]) : (off & ~(uint32_t)k_off_bit[light]);   /* patch 77 */
    if ((now != want || noff != off) && !light_rate_take(racer))
        return BM_RACERS_RATE;
    if (!take(host, racer, BM_RACER_CTL_LIGHTS))
        return BM_RACERS_CONFLICT;
    atomic_store(&s_light_want[racer], now);
    atomic_store(&s_light_off[racer], noff);
    return BM_RACERS_OK;
}

/* main21 patch 104: set_tail_stand_in (version 6; LIGHTS family). The draw mark needs the racer's E, which the patch-77 light mark
 * records, so both sites must match the verified build. */
static int32_t TD_CALL r_set_tail_stand_in(td_host *host, uint32_t racer, uint32_t factor)
{
    if (!host)
        return BM_RACERS_BAD_ARG;
    if (factor != 0u && (factor < BM_TAIL_STAND_IN_MIN || factor > BM_TAIL_STAND_IN_MAX))
        return BM_RACERS_OUT_OF_RANGE;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P8T || !loff_census() || !tail_census() || (g_xbox_mem_offset && !rc_census()))
        return BM_RACERS_UNSUPPORTED;
    if (!list_count())
        return BM_RACERS_NOT_IN_RACE;
    if (racer >= BM_RACERS_MAX || !racer_car(racer))
        return BM_RACERS_NO_RACER;
    if (atomic_load(&s_owner[racer][BM_RACER_CTL_LIGHTS]) && atomic_load(&s_owner[racer][BM_RACER_CTL_LIGHTS]) != (uintptr_t)host)
        return BM_RACERS_CONFLICT;
    if (atomic_load(&s_tail_f[racer]) != factor && !light_rate_take(racer))
        return BM_RACERS_RATE;
    if (!take(host, racer, BM_RACER_CTL_LIGHTS))
        return BM_RACERS_CONFLICT;
    if (!factor)
        atomic_store(&s_tail_e[racer], 0);
    atomic_store(&s_tail_f[racer], factor);
    return BM_RACERS_OK;
}

/* item 24: award_score. Per plugin (slot by host) RC_SCORE_PER_SECOND accepted in any 60 steps and RC_SCORE_PER_RACE a race;
 * the sum waits for player 1's next car update (the game's thread), where it is added (mode 2) - never off the game thread. */
typedef struct rc_score_slot {
    _Atomic(uintptr_t) host;
    uint32_t recent[RC_SCORE_PER_SECOND], nrecent, race_n;
} rc_score_slot;
static rc_score_slot s_score[RC_SCORE_SLOTS];
static _Atomic int32_t s_score_pending;
static _Atomic uint32_t s_score_added;

static int32_t TD_CALL r_award_score(td_host *host, uint32_t player, int32_t amount)
{
    if (!host)
        return BM_RACERS_BAD_ARG;
    if (player > 1u)
        return BM_RACERS_NOT_PLAYER;
    if (player == 1u)
        return BM_RACERS_UNSUPPORTED;
    if (amount < 1 || amount > BM_RACERS_SCORE_AWARD_MAX)
        return BM_RACERS_OUT_OF_RANGE;
#if BM_P23_RACERS_SCORE_FIELD != 2 && MUT != 49
    return BM_RACERS_UNAVAILABLE;               /* the displayed total's word is not verified in this build */
#else
    rc_score_slot *sl = NULL;
    uint32_t s, k, recent = 0;
    if (!BO3_HOOKREQ_P23 || (g_xbox_mem_offset && !rc_census()))
        return BM_RACERS_UNSUPPORTED;
    if (!list_count() || racer_car(0) != RC_CAR1)
        return BM_RACERS_NOT_IN_RACE;
    for (k = 0; k < RC_SCORE_SLOTS && !sl; k++) {
        uintptr_t none = 0;
        if (atomic_load(&s_score[k].host) == (uintptr_t)host ||
            atomic_compare_exchange_strong(&s_score[k].host, &none, (uintptr_t)host))
            sl = &s_score[k];
    }
    if (!sl)
        return BM_RACERS_RATE;
    s = step_now();
    for (k = 0; k < sl->nrecent; k++)
        recent += s - sl->recent[k] < RC_RATE_STEPS;
    if (recent >= RC_SCORE_PER_SECOND || sl->race_n >= RC_SCORE_PER_RACE)
        return BM_RACERS_RATE;
    sl->recent[sl->nrecent < RC_SCORE_PER_SECOND ? sl->nrecent++ : (s % RC_SCORE_PER_SECOND)] = s;
    sl->race_n++;
    atomic_fetch_add(&s_score_pending, amount);
    return BM_RACERS_OK;
#endif
}

/* the apply (player 1's car update): mode 2 adds the pending sum to the verified word */
static void apply_score(void)
{
    int32_t p = atomic_exchange(&s_score_pending, 0);
#if BM_P23_RACERS_SCORE_FIELD == 2
    uint32_t w = 0;
    if (p > 0 && bo3_guest_rd32(RC_CAR1 + RC_SCORE_OFF, &w)) {
        bo3_guest_wr32(RC_CAR1 + RC_SCORE_OFF, w + (uint32_t)p);
        atomic_fetch_add(&s_score_added, (uint32_t)p);
    }
#else
    (void)p;
#endif
}

static int32_t TD_CALL r_release(td_host *host, uint32_t racer, uint32_t family)
{
    if (!host)
        return BM_RACERS_BAD_ARG;
    if (family < BM_RACER_CTL_DAMAGE || family > BM_RACER_CTL_SCORE)
        return BM_RACERS_OUT_OF_RANGE;
    if (racer >= BM_RACERS_MAX)
        return BM_RACERS_NO_RACER;
#if MUT != 48
    if (atomic_load(&s_owner[racer][family]) != (uintptr_t)host)
        return BM_RACERS_NOT_OWNER;
#endif
    give_back(racer, family);
    return BM_RACERS_OK;
}

static uint32_t race_state(void);

/* patch 98: the crash census (its own table, so the v3 controls keep working on a build whose crash sites differ) */
static int wk_census(void)
{
    int c = atomic_load(&s_wk_census_ok);
    if (c >= 0)
        return c;
#if MUT == 61
    c = 1;                                      /* defect: the crash sites not checked */
#else
    c = BO3_HOOKREQ_P28W && g_xbox_mem_offset;
    for (size_t k = 0; c && k < sizeof s_wk_census / sizeof s_wk_census[0]; k++) {
        uint8_t b[24];
        if (!bo3_guest_read(s_wk_census[k].va, b, s_wk_census[k].n) || memcmp(b, s_wk_census[k].b, s_wk_census[k].n))
            c = 0;
    }
#endif
    atomic_store(&s_wk_census_ok, c);
    if (!c && BO3_HOOKREQ_P28W)
        fprintf(stderr, "[RACERS] bmashup.racers 5: wreck is UNSUPPORTED on this build (a crash site's bytes differ)\n");
    return c;
}

static int32_t TD_CALL r_wreck(td_host *host, uint32_t racer, int32_t cause)
{
    uint32_t car, n, s;
    if (!host)
        return BM_RACERS_BAD_ARG;
    if (!BO3_HOOKREQ_P28W || !BO3_HOOKREQ_P23 || (g_xbox_mem_offset && (!rc_census() || !wk_census())))
        return BM_RACERS_UNSUPPORTED;
    n = list_count();
    if (!n || race_state() != TD_RACE_RACING)
        return BM_RACERS_NOT_IN_RACE;
    if (racer >= BM_RACERS_MAX || !(car = racer_car(racer)))
        return BM_RACERS_NO_RACER;
#if MUT != 62
    if (cause != BM_WRECK_CAUSE_NONE && (cause < 0 || (uint32_t)cause >= n))
        return BM_RACERS_OUT_OF_RANGE;
#endif
    {
        uint8_t w = 0, cr = 0;
        uint32_t v = vehicle_of(car);
#if MUT != 63
        if (atomic_load(&s_wreck_req[racer]) || (bo3_guest_read(car + RC_WRECKED, &w, 1) && w) ||
            (v && bo3_guest_read(v + RC_V_CRASHED, &cr, 1) && cr))
            return BM_RACERS_ALREADY;
#endif
    }
    s = step_now();
#if MUT != 64
    if (s_wreck_have[racer] && s - s_wreck_step[racer] < BM_RACERS_WRECK_GAP_STEPS)
        return BM_RACERS_RATE;
#endif
    atomic_store(&s_wreck_r[racer], car);
    atomic_store(&s_wreck_after[racer], 0);
    atomic_store(&s_wreck_req[racer], (uint32_t)(cause == BM_WRECK_CAUSE_NONE ? 1 : cause + 2));
    return BM_RACERS_OK;
}

/* main21 patch 105 (zackypoo 03, Crash Breaker in all modes; host internal, called by bm_rules.c at the detonation, game thread):
 * every AI racer within radius_m of the blasting player's car is wrecked through the patch-101 decider path (cause = the player)
 * and the takedown is staged as an AFTERTOUCH one (attacker + 0x15C0[v] = 1): the player is crashed while it blasts, and the
 * game's confirm sub_00197040 drops the entries of a crashed attacker unless they are aftertouch. v = the player's physics vehicle
 * (pool 0). Returns the number of wrecks queued (applied at the next "ap_update", every check made again there). */
#define RC_POOL0_BASE (RC_PW + 0x1CB80u)
#define RC_POOL0_END  (RC_POOL0_BASE + 2u * 0x4AD0u)
uint32_t bo3_racers_blast(uint32_t v, uint32_t radius_m)
{
    uint32_t n, r = 0, att = BM_RACERS_MAX, s, queued = 0;
    float c[3], p[3], r2 = (float)radius_m * (float)radius_m;
    if (!BO3_HOOKREQ_P28W || !BO3_HOOKREQ_P23 || (g_xbox_mem_offset && (!rc_census() || !wk_census())))
        return 0;
    if (v < RC_POOL0_BASE || v >= RC_POOL0_END || !bo3_guest_rd32(v + RC_V_R, &r) || !r || race_state() != TD_RACE_RACING)
        return 0;
    n = list_count();
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++)
        if (racer_car(k) == r)
            att = k;
    if (att == BM_RACERS_MAX || !rd_vec(r + RC_MAT + 0x30u, c))
        return 0;
    s = step_now();
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++) {
        uint32_t car = racer_car(k), vk;
        uint8_t w = 1;
        float d[3];
        if (k == att || !car)
            continue;
        vk = vehicle_of(car);
#if MUT != 92
        if (!vk || (vk >= RC_POOL0_BASE && vk < RC_POOL0_END))
            continue;                                   /* a human player (or no vehicle): never wrecked by the blast */
#endif
        if (!bo3_guest_read(car + RC_WRECKED, &w, 1) || w || atomic_load(&s_wreck_req[k]) || !rd_vec(car + RC_MAT + 0x30u, p))
            continue;
        d[0] = p[0] - c[0]; d[1] = p[1] - c[1]; d[2] = p[2] - c[2];
#if MUT != 93
        if (dot3(d, d) > r2)
            continue;
#endif
        if (s_wreck_have[k] && s - s_wreck_step[k] < BM_RACERS_WRECK_GAP_STEPS)
            continue;
        atomic_store(&s_wreck_r[k], car);
#if MUT != 94
        atomic_store(&s_wreck_after[k], 1);
#endif
        atomic_store(&s_wreck_req[k], att + 2u);
        queued++;
    }
    atomic_fetch_add(&s_blast_wrecks, queued);
    fprintf(stderr, "[RACERS] Crash Breaker blast by racer %u (V %08x, radius %u m): %u AI racer(s) queued for a wreck\n",
            (unsigned)att, (unsigned)v, (unsigned)radius_m, (unsigned)queued);
    return queued;
}

uint32_t bo3_bm_racers_blast_wrecks(void) { return atomic_load(&s_blast_wrecks); }

/* main21 patch 117 (Crash Breaker v2): the outward push of the AI racers within the radius, right after the game's blast routine
 * sub_00115130 ran for V (it pushes traffic and the wreck pool, never the racers). The racer's physics body has the game's common
 * layout (C3_1 notes, FACT): + 0x110 linear impulse accumulator (the step at 0x109728 adds it / mass to the velocity + 0xB0, then
 * clears it), + 0x1F0 mass, + 0x20E frozen (zeroes the body; cleared = awake, as the game's own impulses do). Direction = the
 * horizontal offset from the blaster lifted by 0.7 (the game's own blast direction), strength falling with the distance like the
 * game's: t = clamp(2 (1 - d / R), 0, 1), velocity change t x BM_RACERS_CB_PUSH_MPS. Human players are never pushed. */
#define BM_RACERS_CB_PUSH_MPS 14.0f
#define RC_BODY_IMPULSE 0x110u
#define RC_BODY_MASS    0x1F0u
#define RC_BODY_FROZEN  0x20Eu
uint32_t bo3_racers_push(uint32_t v, uint32_t radius_m)
{
    uint32_t n, r = 0, att = BM_RACERS_MAX, pushed = 0;
    float c[3], R = (float)radius_m;
    if (!BO3_HOOKREQ_P28W || !BO3_HOOKREQ_P23 || (g_xbox_mem_offset && (!rc_census() || !wk_census())) || radius_m == 0)
        return 0;
    if (v < RC_POOL0_BASE || v >= RC_POOL0_END || !bo3_guest_rd32(v + RC_V_R, &r) || !r || race_state() != TD_RACE_RACING)
        return 0;
    n = list_count();
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++)
        if (racer_car(k) == r)
            att = k;
    if (att == BM_RACERS_MAX || !rd_vec(r + RC_MAT + 0x30u, c))
        return 0;
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++) {
        uint32_t car = racer_car(k), vk, mb = 0;
        float p[3], d[3], h, dist, t, mass, dir[3], len, j[3], acc[3];
        uint8_t zero = 0;
        if (k == att || !car)
            continue;
        vk = vehicle_of(car);
#if MUT != 95
        if (!vk || (vk >= RC_POOL0_BASE && vk < RC_POOL0_END))
            continue;                                   /* a human player (or no vehicle): never pushed */
#endif
        if (!rd_vec(car + RC_MAT + 0x30u, p))
            continue;
        d[0] = p[0] - c[0]; d[1] = p[1] - c[1]; d[2] = p[2] - c[2];
        dist = sqrtf(dot3(d, d));
        if (dist > R)
            continue;                                   /* (also t = 0 below: kept as the plain rule) */
        if (!bo3_guest_rd32(vk + RC_BODY_MASS, &mb))
            continue;
        memcpy(&mass, &mb, 4);
        if (!(mass > 1.0f && mass < 100000.0f))
            continue;                                   /* not a live body */
        h = sqrtf(d[0] * d[0] + d[2] * d[2]);
        dir[0] = h > 0.01f ? d[0] / h : 0.0f;
        dir[1] = 0.7f;
        dir[2] = h > 0.01f ? d[2] / h : 0.0f;
        len = sqrtf(dot3(dir, dir));
        for (int i = 0; i < 3; i++)
            dir[i] /= len;
        t = 2.0f * (1.0f - dist / R);
        t = t < 0.0f ? 0.0f : t > 1.0f ? 1.0f : t;
#if MUT == 97
        t = 1.0f;                                       /* defect: no fall-off with the distance */
#endif
        if (t <= 0.0f || !rd_vec(vk + RC_BODY_IMPULSE, acc))
            continue;
        for (int i = 0; i < 3; i++)
            j[i] = acc[i] + t * BM_RACERS_CB_PUSH_MPS * mass * dir[i];
        bo3_guest_write(vk + RC_BODY_IMPULSE, j, 12);
        bo3_guest_write(vk + RC_BODY_FROZEN, &zero, 1);
        pushed++;
        fprintf(stderr, "[RACERS] Crash Breaker push: racer %u at %.1f m, mass %.0f, velocity change %.1f m/s\n", (unsigned)k,
                (double)dist, (double)mass, (double)(t * BM_RACERS_CB_PUSH_MPS));
    }
    return pushed;
}

static const char *TD_CALL r_result_text(int32_t code)
{
    static const char *const k[] = { "OK", "BAD_ARG", "NO_RACER", "UNAVAILABLE", "NOT_IN_RACE", "OUT_OF_RANGE", "CONFLICT",
                                     "NOT_OWNER", "UNSUPPORTED", "WRONG_THREAD", "RATE", "ALREADY", "NOT_HANGING", "NOT_PLAYER" };
    return code >= 0 && (size_t)code < sizeof k / sizeof k[0] ? k[code] : "UNKNOWN";
}

/* the game's DetachBodyPart on V, part i: ESI = i, V pushed, a 0 return address (its ret 4 takes V); registers put back */
static void game_detach(uint32_t v, uint32_t i)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
    g_esi = i;
    PUSH32(g_esp, v);
    PUSH32(g_esp, 0);
    sub_00125A50();
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
}

/* patch 101: the crash goes through the game's crash decider sub_0010DD20 exactly as the "nobody caused it" call at 0x10F484
 * does: ECX = a, EBX = V, EAX = 0 (no contact info), b (0) and the crash-record table 0x64ACE8 pushed, a 0 return address (its
 * ret 8 takes all three: callee pops). The decider asks the game mode (vt + 0x48: Road Rage / Crash scoring, the takedown blame),
 * calls the class's crash slot fn (vt + 8) itself, fills the crash record and tells a human racer's player controller (event 0x13:
 * crash camera / respawn). Patch 98 called the slot directly and so skipped all of that (S8b: the player never respawned).
 * Every guest register, g_ebp and g_seh_ebp (the decider writes both) put back afterwards. */
static uint32_t game_wreck(void (*fn)(void), uint32_t v, int32_t a)
{
    uint32_t ra = g_eax, rb = g_ebx, rc = g_ecx, rd = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp, seh = g_seh_ebp, after;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
#if MUT == 76
    g_ecx = v;                                  /* defect: patch 98's direct slot call (no decider) */
    PUSH32(g_esp, 0);
    PUSH32(g_esp, (uint32_t)a);
    PUSH32(g_esp, 0);
    fn();
#else
    (void)fn;
    g_ecx = (uint32_t)a;
    g_ebx = v;
    g_eax = 0;
    PUSH32(g_esp, 0);
#if MUT == 78
    PUSH32(g_esp, 0);                           /* defect: no crash-record table */
#else
    PUSH32(g_esp, RC_CRASH_TAB);
#endif
    PUSH32(g_esp, 0);
    sub_0010DD20();
#endif
    after = g_esp;
    g_eax = ra; g_ebx = rb; g_ecx = rc; g_edx = rd; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
#if MUT != 77
    g_seh_ebp = seh;
#endif
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
    return after - sp;                          /* 0 when the callee popped its 12 bytes */
}

static void wreck_refused(uint32_t k, const char *why)
{
    if (atomic_fetch_add(&s_wreck_refused, 1) < 16u)
        fprintf(stderr, "[RACERS] bmashup.racers 5: wreck of racer %u not carried out: %s\n", (unsigned)k, why);
}

/* patch 101: the game mode object the decider calls without a check must be there */
static int mode_object_there(void)
{
#if MUT == 81
    return 1;                                   /* defect: not checked */
#else
    uint32_t m = 0, o = 0, vt = 0;
    return bo3_guest_rd32(RC_MODE_PTR, &m) && m && bo3_guest_rd32(m + RC_MODE_OBJ, &o) && o && bo3_guest_rd32(o, &vt) && vt;
#endif
}

/* patch 101: takedown credit for a wreck caused by another racer. The game stages it only in the blame (sub_00197430, from the
 * decider's mode hook) for a car with contact or a psyche-out near the victim, which a host wreck does not have. So, right after
 * the decider, stage it as 0x197504 does, under the blame's own conditions on the attacker (not finished = phase != 3, its racer
 * object [att + 0x1198] not crashed): att + 0x15A8[v] = att + 0x10DC (its clock), + 0x15C0[v] = 0, + 0x15C6[v] = 0, v = the
 * victim's game index as the blame reads it (s8 [victim + 0x1198] + 0x19BC). The game's confirm sub_00197040 then counts the
 * takedown about 1 s later (banner, boost, results, Road Rage) - or drops it when the attacker is wrecked by then. */
static void stage_takedown(uint32_t k, uint32_t victim, uint32_t ki, uint32_t att, uint32_t after)
{
    uint32_t vo = 0, ao = 0, phase = 0, clock = 0, td = 0;
    uint8_t vi = 0, acr = 1;
    int32_t v;
    if (!bo3_guest_rd32(victim + RC_SCORER, &vo) || !vo || !bo3_guest_read(vo + RC_GAME_INDEX, &vi, 1)) {
        wreck_refused(k, "no takedown credit: the victim's index is not readable");
        return;
    }
#if MUT == 80
    v = (int32_t)k;                             /* defect: the list index, not the game index */
#else
    v = (int8_t)vi;
#endif
    if (v < 0 || (uint32_t)v >= RC_TD_SLOTS) {
        wreck_refused(k, "no takedown credit: the victim's index is out of range");
        return;
    }
    if (!bo3_guest_rd32(att + RC_PHASE, &phase) || !bo3_guest_rd32(att + RC_SCORER, &ao) || !ao ||
        !bo3_guest_read(ao + RC_WRECKED, &acr, 1)) {
        wreck_refused(k, "no takedown credit: the attacker is not readable");
        return;
    }
#if MUT != 79
    if (phase == 3u || (acr && !after)) {       /* patch 105: an aftertouch credit is for a crashed attacker */
        wreck_refused(k, "no takedown credit: the attacker is finished or crashed (as the game's blame)");
        return;
    }
#endif
#if MUT == 82
    clock = 0;                                  /* defect: not the attacker's clock */
#else
    bo3_guest_rd32(att + RC_TIME, &clock);
#endif
    bo3_guest_wr32(att + RC_TD_STAGE + 4u * (uint32_t)v, clock);
    bo3_guest_write(att + RC_TD_AFTER + (uint32_t)v, after ? "\1" : "\0", 1);
    bo3_guest_write(att + RC_TD_PSYCHE + (uint32_t)v, "\0", 1);
    bo3_guest_rd32(att + RC_TD, &td);
    s_tdw_car[ki] = att;
    s_tdw_before[ki] = td;
    s_tdw_step[ki] = step_now();
    atomic_fetch_add(&s_td_staged, 1);
    fprintf(stderr, "[RACERS] bmashup.racers 5: takedown of racer %u staged for racer %u (victim index %d, clock %08x, "
            "takedowns %u); the game's confirm counts it\n", (unsigned)k, (unsigned)ki, (int)v, (unsigned)clock, (unsigned)td);
}

/* patch 101: one probe line per staged credit - the game counted it (takedowns went up) or not within RC_TD_WATCH steps */
static void watch_takedowns(void)
{
    for (uint32_t i = 0; i < BM_RACERS_MAX; i++) {
        uint32_t td = 0, s = step_now();
        if (!s_tdw_car[i])
            continue;
        if (racer_car(i) != s_tdw_car[i]) {
            s_tdw_car[i] = 0;
            continue;
        }
        bo3_guest_rd32(s_tdw_car[i] + RC_TD, &td);
        if (td > s_tdw_before[i]) {
            atomic_fetch_add(&s_td_confirmed, 1);
            fprintf(stderr, "[RACERS] bmashup.racers 5: racer %u takedowns %u -> %u (the game counted the staged takedown, "
                    "%u steps)\n", (unsigned)i, (unsigned)s_tdw_before[i], (unsigned)td, (unsigned)(s - s_tdw_step[i]));
            s_tdw_car[i] = 0;
        } else if (s - s_tdw_step[i] > RC_TD_WATCH) {
            fprintf(stderr, "[RACERS] bmashup.racers 5: racer %u takedowns still %u after %u steps (the staged takedown was "
                    "not counted)\n", (unsigned)i, (unsigned)td, (unsigned)RC_TD_WATCH);
            s_tdw_car[i] = 0;
        }
    }
}

/* patch 98: the pending wrecks, at player 1's car update (the game's thread); everything re-checked here */
static void apply_wrecks(uint32_t st)
{
    if (st == TD_RACE_RACING)
        watch_takedowns();
    else
        memset(s_tdw_car, 0, sizeof s_tdw_car);
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {
        uint32_t req = atomic_exchange(&s_wreck_req[k], 0), car, v, vt = 0, slot = 0, cc = 0, left, after;
        uint8_t w = 1, cr = 1, own = 0, by = 0, cb = 0;
        int32_t cause, a;
        void (*fn)(void);
        if (!req)
            continue;
        after = atomic_exchange(&s_wreck_after[k], 0);   /* patch 105 */
        cause = (int32_t)req - 2;
        car = racer_car(k);
#if MUT != 65
        if (st != TD_RACE_RACING || !car || car != atomic_load(&s_wreck_r[k])) {
            wreck_refused(k, "the race or the racer changed");
            continue;
        }
#endif
        v = vehicle_of(car);
        if (!v || !bo3_guest_rd32(v, &vt) || !bo3_guest_rd32(vt + 8u, &slot)) {
            wreck_refused(k, "its physics vehicle is not found");
            continue;
        }
        if ((vt == 0x003B1160u && slot == 0x00118E30u) || MUT == 66)
            fn = sub_00118E30;
        else if ((vt == 0x003B1240u || vt == 0x003B1138u) && slot == 0x0011FC60u)
            fn = sub_0011FC60;
        else {
            wreck_refused(k, "its vehicle class is not a verified one");
            continue;
        }
        if (!bo3_guest_read(car + RC_WRECKED, &w, 1) || w || !bo3_guest_read(v + RC_V_CRASHED, &cr, 1) || cr) {
            wreck_refused(k, "the car is already crashed / wrecked");
            continue;
        }
        if (cause >= 0 && (uint32_t)cause != k) {
            cc = racer_car((uint32_t)cause);
            if (!cc || !bo3_guest_read(cc + RC_GAME_INDEX, &cb, 1)) {
                wreck_refused(k, "the causing racer is gone");
                continue;
            }
            a = (int8_t)cb;
        } else {
            if (!bo3_guest_read(car + RC_GAME_INDEX, &own, 1)) {
                wreck_refused(k, "its own index is not readable");
                continue;
            }
            a = (int8_t)own;
        }
        if (a < 0 || a >= (int32_t)BM_RACERS_MAX) {
            wreck_refused(k, "the cause index is out of range");
            continue;
        }
        if (!mode_object_there()) {
            wreck_refused(k, "the game mode object is not there (the crash decider needs it)");
            continue;
        }
        left = game_wreck(fn, v, a);
        s_wreck_step[k] = step_now();
        s_wreck_have[k] = 1;
        bo3_guest_read(v + RC_V_CRASHED, &cr, 1);
        bo3_guest_read(v + RC_V_BY, &by, 1);
        atomic_fetch_add(&s_wrecks_done, 1);
        fprintf(stderr, "[RACERS] bmashup.racers 5: racer %u wrecked by the game's crash decider 0x10DD20 (slot %s, V %08x vt %08x, "
                "cause %d -> a %d) at step %u: crashed %u by %d%s\n", (unsigned)k, fn == sub_00118E30 ? "0x118E30" : "0x11FC60",
                (unsigned)v, (unsigned)vt, (int)cause, (int)a, (unsigned)s_wreck_step[k], (unsigned)cr, (int)(int8_t)by,
                left ? " (STACK NOT BALANCED)" : "");
        if (cc && cr && !left)
            stage_takedown(k, car, (uint32_t)cause, cc, after);
    }
}

uint32_t bo3_bm_racers_takedowns_staged(void) { return atomic_load(&s_td_staged); }
uint32_t bo3_bm_racers_takedowns_confirmed(void) { return atomic_load(&s_td_confirmed); }

uint32_t bo3_bm_racers_wrecks_done(void) { return atomic_load(&s_wrecks_done); }

static void apply_detach(uint32_t k, uint32_t car)
{
    uint32_t req = atomic_exchange(&s_detach_req[k], 0), v = vehicle_of(car), count = 0;
    for (uint32_t i = 0; req && i < BM_RACERS_PARTS_MAX; i++) {
        if (!(req & (1u << i)))
            continue;
        if (part_state(v, i, &count) != 2)
            continue;                           /* no longer hanging: nothing called */
        game_detach(v, i);
        atomic_fetch_or(&s_detach_done[k], 1u << i);
        fprintf(stderr, "[RACERS] bmashup.racers 3: racer %u part %u detached by the game's DetachBodyPart at step %u\n",
                (unsigned)k, (unsigned)i, (unsigned)step_now());
    }
}

static uint32_t race_state(void)
{
    td_race_snapshot s;
    if (s_state_fn)
        return s_state_fn();
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (bo3_race_api()->get((td_host *)(void *)&s_self, &s) != TD_RACE_OK)
        return TD_RACE_NONE;
    return s.state;
}

static int in_stage(uint32_t st) { return st >= TD_RACE_PRESTART && st <= TD_RACE_FINISHED; }

/* a new race (or a restart): every control given back (patch 103: no racer byte is written, nothing to restore) */
static void new_race(void)
{
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {
        for (uint32_t f = 1; f <= RC_FAMILIES; f++)
            give_back(k, f);
        atomic_store(&s_detach_done[k], 0);
        s_rate_n[k] = 0;
        atomic_store(&s_wreck_req[k], 0);       /* patch 98: a pending wreck does not cross a race */
        atomic_store(&s_wreck_after[k], 0);     /* patch 105 */
        s_wreck_have[k] = 0;
    }
    atomic_store(&s_score_pending, 0);          /* item 24: pending awards do not cross a race */
    for (uint32_t k = 0; k < RC_SCORE_SLOTS; k++) {
        s_score[k].nrecent = 0;
        s_score[k].race_n = 0;
    }
}

/* the apply point: player 1's car update ("ap_update" writer, the game's thread) */
static void racers_apply(void *user)
{
    uint32_t st, n;
    (void)user;
    if (g_esi != RC_CAR1 || !BO3_HOOKREQ_P23)
        return;
    st = race_state();
    if (in_stage(st) && (!in_stage(s_prev_state) || (st == TD_RACE_PRESTART && s_prev_state != TD_RACE_PRESTART)))
        new_race();
    s_prev_state = st;
    if (!rc_census())
        return;
    n = list_count();
    for (uint32_t k = 0; k < n; k++) {               /* patch 103: lights are applied at the patch-77 mark, not here */
        uint32_t car = racer_car(k);
        if (!car)
            continue;
        if (atomic_load(&s_detach_req[k]) && (car == RC_CAR1 || MUT == 47))
            apply_detach(k, car);
    }
    apply_score();
    if (BO3_HOOKREQ_P28W && wk_census())
        apply_wrecks(st);
}

uint32_t bo3_bm_racers_score_added(void)
{
    return atomic_load(&s_score_added);
}

/* the per-car mark at sub_0011BE50's entry (bo3_racers_gen.h; ECX = the physics vehicle V): counts the calls (one log line a
 * race says whether AI cars pass it); with BM_P23_RACERS_APPLY_PER_RACER, AI racers' detaches are carried out here. */
void bo3_racers_gen_car(uint32_t v)
{
    uint32_t r = 0;
    if (!BO3_HOOKREQ_P23)
        return;
    atomic_fetch_add(&s_mark_calls, 1);
    if (bo3_guest_rd32(v + RC_V_R, &r) && r != RC_CAR1)
        atomic_fetch_add(&s_mark_other, 1);
#if BM_P23_RACERS_APPLY_PER_RACER
    {
        uint32_t n = list_count();
        for (uint32_t k = 0; k < n; k++)
#if MUT == 51
            if (racer_car(k) == r && atomic_load(&s_detach_req[k]) && rc_census())     /* defect: player 1's car here too */
#else
            if (racer_car(k) == r && r != RC_CAR1 && atomic_load(&s_detach_req[k]) && rc_census())
#endif
                apply_detach(k, r);
    }
#endif
}

void bo3_bm_racers_set_race_state_for_test(uint32_t (*fn)(void))
{
    s_state_fn = fn;
}

uint32_t bo3_bm_racers_mark_calls(uint32_t *other)
{
    if (other)
        *other = atomic_load(&s_mark_other);
    return atomic_load(&s_mark_calls);
}

static void racers_observer(void *user)
{
    (void)user;
    if (g_esi == RC_CAR1)
        sample_all();
}

/* the v3 reads of racer index k (car R) into o */
static void v3_reads(uint32_t k, uint32_t car, bm_racer_info *o)
{
    uint32_t v = vehicle_of(car), e = 0, dblk = 0, ps = 0;
    int32_t gear = 0;
    uint8_t fl = 0;
    int8_t cnt = 0;
    const rc_dyn *d = &s_dyn[k];
    memset(o->part_kind, BM_RACER_PART_NONE, sizeof o->part_kind);
    memset(o->part_state, BM_RACER_PART_NONE, sizeof o->part_state);
    o->controls_owned = atomic_load(&s_ctl_owned[k]);
    if (d->r == car && atomic_load(&d->have)) {
        o->have_dynamics = 1;
        o->speed_mps = atomic_load(&d->speed);
        o->yaw_rate_rps = atomic_load(&d->yaw);
        o->lat_accel_mps2 = atomic_load(&d->lat);
        o->long_accel_mps2 = atomic_load(&d->lon);
    }
    o->have_rpm = 0;
#if BM_P23_RACERS_RPM_KNOWN
    {
        float w = -1.0f;
        if (v && BO3_HOOKREQ_P23 && rpm_census() && bo3_guest_read(v + RC_RPM_OFF, &w, 4) && isfinite(w) && w >= 0.0f &&
#if MUT == 72
            1) {                                /* defect: no plausibility bound */
#else
            w <= RC_RPM_MAX_RAD) {
#endif
#if MUT == 73
            o->engine_rpm = w;                  /* defect: rad / s given as rpm */
#else
            o->engine_rpm = w * RC_RAD_TO_RPM;
#endif
            o->have_rpm = 1;
        }
    }
#endif
    if (!v)
        return;
    if (bo3_guest_rd32(v + RC_GEAR, (uint32_t *)&gear) && gear >= -1 && gear <= 16)
        o->gear = gear;
    if (!bo3_guest_rd32(v + RC_V_E, &e) || !e)
        return;
    if (bo3_guest_read(e + 0x58u, &fl, 1)) {
        o->lights = ((fl & 0x06u) ? 1u << BM_LIGHT_HEAD : 0u) | ((fl & 0x08u) ? 1u << BM_LIGHT_TAIL : 0u) |
                    ((fl & 0x10u) ? 1u << BM_LIGHT_BRAKE : 0u);
#if BM_P23_RACERS_INDICATORS_KNOWN
        o->lights |= ((fl & 0x20u) ? 1u << BM_LIGHT_IND_LEFT : 0u) | ((fl & 0x40u) ? 1u << BM_LIGHT_IND_RIGHT : 0u);
#endif
        if (BO3_HOOKREQ_P26R && (fl & 0x80u))
            o->lights |= 1u << BM_LIGHT_REVERSE;    /* main21 patch 95 */
    }
    if (bo3_guest_rd32(e + 0x40u, &dblk) && dblk && bo3_guest_read(dblk + 0xCu, &cnt, 1) && cnt > 0 &&
        bo3_guest_rd32(v + RC_V_PS, &ps) && ps) {
#if MUT == 36
        uint32_t m = (uint32_t)cnt;                     /* defect: the 32-part bound not applied */
#else
        uint32_t m = (uint32_t)cnt > BM_RACERS_PARTS_MAX ? BM_RACERS_PARTS_MAX : (uint32_t)cnt;
#endif
        for (uint32_t i = 0; i < m; i++) {
            uint32_t kind = 0;
            uint8_t st = 0;
            if (!bo3_guest_rd32(dblk + 0xAC4u + 4u * i, &kind) || !bo3_guest_read(ps + 0x4B2u + i, &st, 1))
                break;
            o->part_kind[i] = kind <= 6u ? (uint8_t)kind : BM_RACER_PART_NONE;
            o->part_state[i] = st <= 4u ? st : BM_RACER_PART_NONE;
            o->parts = i + 1;
        }
    }
}

static uint32_t list_count(void)
{
    uint32_t n = 0;
    if (!bo3_guest_rd32(RC_COUNT, &n))
        return 0;
#if MUT == 1
    return n;                                   /* defect: the list's 8-entry bound not applied */
#else
    return n > BM_RACERS_MAX ? BM_RACERS_MAX : n;
#endif
}

static uint32_t TD_CALL r_count(td_host *host)
{
    return host ? list_count() : 0;
}

/* v2: the racer's place (1 .. 8, else 0 = not ranked) */
static int32_t place_of(uint32_t car, uint32_t n)
{
    int16_t p = 0;
    if (!bo3_guest_read(car + RC_PLACE, &p, 2))
        return 0;
#if MUT == 3
    (void)n;
    return p;                                   /* defect: an out-of-range place passed through */
#else
    return p >= 1 && (uint32_t)p <= n ? (int32_t)p : 0;
#endif
}

static int32_t TD_CALL r_get(td_host *host, uint32_t index, bm_racer_info *out)
{
    bm_racer_info o;
    uint32_t car = 0, td = 0, n, laps = 0, phase = 0;
    uint8_t wr = 0;
    float t = 0.0f;
    if (!host || !out || out->struct_size < 8)
        return BM_RACERS_BAD_ARG;
    n = list_count();
    if (index >= n)
        return BM_RACERS_NO_RACER;
    if (!bo3_guest_rd32(RC_LIST + 4u * index, &car) || !car)
        return BM_RACERS_UNAVAILABLE;
    memset(&o, 0, sizeof o);
    if (!bo3_guest_rd32(car + RC_TD, &td) || !bo3_guest_read(car + RC_WRECKED, &wr, 1) ||
        !bo3_guest_read(car + RC_METER + RC_BAR, &o.boost, 4) || !bo3_guest_read(car + RC_METER + RC_MAX, &o.boost_max, 4))
        return BM_RACERS_UNAVAILABLE;
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.index = index;
    o.is_player1 = car == RC_CAR1;
    o.takedowns = td;
#if MUT == 2
    o.wrecked = wr;                             /* defect: the raw byte, not 0 / 1 */
#else
    o.wrecked = wr ? 1u : 0u;
#endif
    /* v2: read only when the caller's struct covers them (a v1 caller's read set is exactly v1's) */
    if (o.struct_size > offsetof(bm_racer_info, place)) {
        o.place = place_of(car, n);
        if (bo3_guest_rd32(car + RC_LAPS, &laps) && laps <= RC_LAPS_SANE)
            o.laps_done = laps;
        if (bo3_guest_read(car + RC_TIME, &t, 4) && isfinite(t) && t >= 0.0f)
            o.race_time_s = t;
        o.phase = bo3_guest_rd32(car + RC_PHASE, &phase) && phase <= 3u ? phase : BM_RACER_PHASE_UNKNOWN;
#if MUT == 4
        o.player = 0;                           /* defect: every car reported as a human player's */
#else
        o.player = car == RC_CAR1 ? 0u : BM_RACER_NO_PLAYER;
#endif
        o.eliminated = 0;
    }
    if (o.struct_size > offsetof(bm_racer_info, have_dynamics))
        v3_reads(index, car, &o);
#if MUT == 37
    o.struct_size = (uint32_t)sizeof o;         /* defect: the caller's room ignored (a v2-sized caller gets 160 bytes) */
#endif
    memcpy(out, &o, o.struct_size);
    return BM_RACERS_OK;
}

static int32_t TD_CALL r_order(td_host *host, uint32_t *order, uint32_t *n)
{
    uint32_t cnt, k, m = 0, idx[BM_RACERS_MAX];
    int32_t pl[BM_RACERS_MAX];
    if (!host || !order || !n)
        return BM_RACERS_BAD_ARG;
    cnt = list_count();
    if (!cnt) {
        *n = 0;
        return BM_RACERS_NOT_IN_RACE;
    }
    for (k = 0; k < cnt; k++) {
        uint32_t car = 0;
        if (!bo3_guest_rd32(RC_LIST + 4u * k, &car) || !car)
            return BM_RACERS_UNAVAILABLE;
        idx[k] = k;
        pl[k] = place_of(car, cnt);
    }
    /* stable insertion sort: ranked by place (1 first), unranked (0) last, ties by index */
    for (k = 1; k < cnt; k++) {
        uint32_t j = k, vi = idx[k];
        int32_t vp = pl[k];
#if MUT == 5
        uint32_t kv = (uint32_t)vp;             /* defect: unranked (0) sorted first */
#else
        uint32_t kv = vp ? (uint32_t)vp : 0xFFFFFFFFu;
#endif
        while (j > 0) {
#if MUT == 5
            uint32_t kj = (uint32_t)pl[j - 1];
#else
            uint32_t kj = pl[j - 1] ? (uint32_t)pl[j - 1] : 0xFFFFFFFFu;
#endif
            if (kj <= kv)
                break;
            idx[j] = idx[j - 1];
            pl[j] = pl[j - 1];
            j--;
        }
        idx[j] = vi;
        pl[j] = vp;
    }
    m = *n < cnt ? *n : cnt;
#if MUT == 6
    m = cnt;                                    /* defect: the caller's room ignored */
#endif
    for (k = 0; k < m; k++)
        order[k] = idx[k];
    *n = m;
    return BM_RACERS_OK;
}

static int32_t TD_CALL r_session(td_host *host, bm_racers_session *out)
{
    bm_racers_session o;
    uint32_t cnt;
    if (!host || !out || out->struct_size < 8)
        return BM_RACERS_BAD_ARG;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    cnt = list_count();
    o.racers = cnt;
    o.in_race = cnt ? 1u : 0u;
    o.mode = BM_MODE_UNKNOWN;
    o.context = BM_CONTEXT_UNKNOWN;
    for (uint32_t k = 0; k < cnt; k++) {
        uint32_t car = 0;
        if (bo3_guest_rd32(RC_LIST + 4u * k, &car) && car == RC_CAR1)
            o.players = 1;
    }
    memcpy(out, &o, o.struct_size);
    return BM_RACERS_OK;
}

static const bm_racers_api s_api = {(uint32_t)sizeof(bm_racers_api), RC_VERSION, r_count, r_get, r_order, r_session,
                                    r_detach_part, r_set_light, r_light_available, r_award_score, r_release, r_result_text,
                                    r_lamp_counts, r_get_pose, r_wreck, r_set_tail_stand_in};

const bm_racers_api *bo3_bm_racers_api(void)
{
    return &s_api;
}

void bo3_bm_racers_init(void)
{
    int mark;
    memset(s_dyn, 0, sizeof s_dyn);
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++)
        atomic_store(&s_ctl_owned[k], 0);
    mark = bo3_events_hook("ap_update");      /* v3: the dynamics sample (observer: reads only) */
    if (mark < 0 || bo3_events_subscribe(mark, BO3_EVENT_OBSERVER, racers_observer, NULL, "bmashup.racers") != 0)
        fprintf(stderr, "[RACERS] bmashup.racers 3: the car-update mark is not available: have_dynamics stays 0\n");
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {             /* v3 controls (item 23) */
        for (uint32_t f = 0; f <= RC_FAMILIES; f++)
            atomic_store(&s_owner[k][f], 0);
        atomic_store(&s_light_want[k], 0);
        atomic_store(&s_tail_f[k], 0);          /* patch 104 */
        atomic_store(&s_tail_e[k], 0);
        atomic_store(&s_detach_req[k], 0);
        atomic_store(&s_detach_done[k], 0);
        s_rate_n[k] = 0;
        atomic_store(&s_wreck_req[k], 0);
        atomic_store(&s_wreck_r[k], 0);
        s_wreck_have[k] = 0;
    }
    atomic_store(&s_rc_census_ok, -1);
    atomic_store(&s_wk_census_ok, -1);
    memset(s_on_seen, 0, sizeof s_on_seen);     /* patch 99 (patch 104: also per race, bo3_racers_diag_lifecycle) */
    s_on_lines = 0;
    s_tail_census = 0;                          /* patch 104 */
    s_tail_lines = 0;
    atomic_store(&s_tail_calls, 0);
    atomic_store(&s_tail_swaps, 0);
    memset(s_tdw_car, 0, sizeof s_tdw_car);     /* patch 101 */
    atomic_store(&s_td_staged, 0);
    atomic_store(&s_td_confirmed, 0);
    atomic_store(&s_wrecks_done, 0);
    atomic_store(&s_wreck_refused, 0);
    for (uint32_t k = 0; k < RC_SCORE_SLOTS; k++) {          /* item 24 */
        atomic_store(&s_score[k].host, 0);
        s_score[k].nrecent = 0;
        s_score[k].race_n = 0;
    }
    atomic_store(&s_score_pending, 0);
    atomic_store(&s_score_added, 0);
    atomic_store(&s_mark_calls, 0);
    atomic_store(&s_mark_other, 0);
    s_prev_state = TD_RACE_NONE;
    if (BO3_HOOKREQ_P23 && (mark < 0 || bo3_events_subscribe(mark, BO3_EVENT_WRITER, racers_apply, NULL, "bmashup.racers") != 0))
        fprintf(stderr, "[RACERS] bmashup.racers 3: the car-update mark is not available: the controls stay off\n");
    bo3_plugins_service(BM_RACERS_SERVICE, RC_VERSION, &s_api);
}

/* tests: one sample now (as the observer does) */
void bo3_bm_racers_sample_for_test(void)
{
    sample_all();
}
