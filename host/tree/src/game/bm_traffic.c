/* bm_traffic.c - gp slice traffic1 EXPERIMENTAL: "bmashup.traffic" (include/bmashup_traffic.h; atlas gp\atlas\TRAFFIC.md).
 *
 * The game's traffic spawns from the FLOW records of the race's traffic set (vehicles per minute per lane and class): the valve
 * timers start a class only when its flow is > 0 (sub_001A5790), the interval is 60 / flow (sub_001A5DC0) and the lane
 * population counts length / speed x sum of flows (sub_001A6070). Every trigger of the set has its own flow array (p4, the
 * later triggers replace the lanes they list). The service scales ALL of them to original x density at the traffic set-up:
 * the marks at the start of sub_001A13F0 (traffic init, before its population loop) and sub_001A28B0 (pre-race population).
 *
 * Idempotent: the original of every value written is kept by position; at the next set-up a value equal to what was written
 * is taken back to its original, any other value is a fresh original (a reloaded set). Fail closed: the whole set is checked
 * before the first write. MUT=n (tests only) compiles one deliberate defect. */
#include "bm_traffic.h"

#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 0
#endif
#ifndef BO3_HOOKREQ_P5A
#define BO3_HOOKREQ_P5A 0
#endif

/* ---- v4 (main21 patch 67, hook request v2 P5a; gp\hookreq\HOOK_REQUEST_DESIGN.md s12-13) ----
 * VERIFIED statically (and in the census below): the traffic reset sub_001A3EA0 is the only constant writer of the spawn
 * generator T + 0x36348 / + 0x3634C (0xFD462907 / 0x02B9D6F8, no clock mixed in); the traffic init calls it at 0x1A1A1A
 * (mov eax, esi; call) and the reset makes no call and no draw after it, so the mark at loc_001A1A1F (esi = T) runs before the
 * first draw. NOT VERIFIED: whether a replay runs the traffic init again (probe P5a-R). */
static const td_host *s_seed_owner;
static uint32_t s_seed_mode = BM_TRAFFIC_SEED_GAME, s_seed, s_seeds_applied, s_seed_refusals, s_seed_marks;
static float s_floor;                       /* lane floor requested (0 = off) */
static uint32_t s_lanes_raised;             /* by the last set-up */
static uint32_t s_fill, s_lanes_filled;     /* v6: fill empty lanes (requested), lanes filled by the last set-up */
static int s_p5a_census_ok = -1;

/* ---- v3 (platform 0.1.9, main19 item 25, hook request P2 F4 / F5; gp\hookreq\p23\SITES_VERIFIED.md s2, tests\p23\STEP0_A.md) ----
 * VERIFIED (and in the census below): the crash pool M + 0x33780 (M = the physics world 0x64B310), 64 slots of 0x2430 bytes,
 * occupancy byte slot + 0x210 (sub_00114910 0x114922 / 0x11495C - no full check: index 64 falls to M + 0xC4380); the induced
 * crash sub_00111750 (ESI = M, EBX = the inducing car, stack 1 = the traffic vehicle record, stack 2 = 1, ret 8; the retail
 * call at 0x19F820 passes the record T + 0x127D0 + 0x180 i); the fatal table 0x39AE50 (7 x 7).
 * NOT VERIFIED (constants; nothing is guessed while 0):
 *   BM_P23_TRAFFIC_VEHICLES_KNOWN  the record's live / position / velocity / crashed / class fields and player 1's inducer object
 *                                  (the 0x731E90 list entry of sub_0019F560): near_vehicles / wreck UNAVAILABLE while 0 (RE + PR-B)
 *   BM_P23_TRAFFIC_DESPAWN_FREES   PR-B: the game's despawn sub_001A3970 frees the crash slot: clear_wrecked UNAVAILABLE while 0
 *   BM_P23_TRAFFIC_CRASHING_CAP    the game's crashing cap (atlas TRAFFIC: the draw's 8 crashing; PR-B confirms) */
#define BM_P23_TRAFFIC_VEHICLES_KNOWN 0   /* main21 patch 68: superseded by BO3_HOOKREQ_P5B (the statically mapped records, below) */
#define BM_P23_TRAFFIC_DESPAWN_FREES 0
#define BM_P23_TRAFFIC_CRASHING_CAP 8u
#define TR3_M          0x0064B310u
#define TR3_POOL       (TR3_M + 0x33780u)
#define TR3_SLOT       0x2430u
#define TR3_OCC        0x210u
#define TR3_RATE_STEPS 60u
#define TR3_STEP       0x004A1EB4u
#define TR3_SLOTS      16u           /* plugins with their own wreck rate */
static int s_tr3_census_ok = -1;
static uint32_t s_wrecks_by_plugins, s_pool_refusals;
static uintptr_t s_wr_host[TR3_SLOTS];
static uint32_t s_wr_recent[TR3_SLOTS][4], s_wr_n[TR3_SLOTS];   /* 4 = BM_TRAFFIC_WRECKS_PER_SECOND */
void bo3_tr3_new_race(void);
static void bo3_tr5_reset(void);
static void bo3_tr5c_reset(void);
static void pk_reset(void);       /* C3-4 */
static void pk_new_load(void);
static void pk_release_host(const td_host *host);

static bo3_tr_guest s_g;
static int s_configured, s_verified;
static const td_host *s_owner;
static double s_density = 1.0;              /* requested */
static float s_density_applied = 1.0f;
static uint32_t s_applications, s_refusals, s_written, s_marks;
static void (*s_log)(const char *line);

/* the values written, by position (the order the set is walked in) */
static uint32_t s_cache_set;                /* set it belongs to (0 = none) */
static uint32_t s_cache_n;
static uint32_t *s_va, *s_orig, *s_wrote;
static float s_t0_game, s_t0_now;          /* start trigger sums at the last set-up */

static int rd(uint32_t va, void *out, uint32_t n)
{
    return s_configured && s_g.read && s_g.read(s_g.user, va, out, n);
}

static int rd32(uint32_t va, uint32_t *v)
{
    return rd(va, v, 4);
}

static float bits_f(uint32_t u)
{
    float f;
    memcpy(&f, &u, 4);
    return f;
}

static uint32_t f_bits(float f)
{
    uint32_t u;
    memcpy(&u, &f, 4);
    return u;
}

void bo3_tr_set_log(void (*fn)(const char *line))
{
    s_log = fn;
}

void bo3_tr_configure(const bo3_tr_guest *g, int verified)
{
    s_g = *g;
    s_configured = 1;
    s_verified = verified;
    s_owner = NULL;
    s_density = 1.0;
    s_density_applied = 1.0f;
    s_applications = s_refusals = s_written = s_marks = 0;
    s_cache_set = s_cache_n = 0;
    s_t0_game = s_t0_now = 0.0f;
    s_tr3_census_ok = -1;                               /* v3 */
    memset(s_wr_host, 0, sizeof s_wr_host);
    bo3_tr3_new_race();
    s_seed_owner = NULL;                                /* v4 */
    s_seed_mode = BM_TRAFFIC_SEED_GAME;
    s_seed = s_seeds_applied = s_seed_refusals = s_seed_marks = 0;
    s_floor = 0.0f;
    s_lanes_raised = 0;
    s_fill = s_lanes_filled = 0;                        /* v6 */
    s_p5a_census_ok = -1;
    bo3_tr5_reset();                                    /* P5b */
    bo3_tr5c_reset();                                   /* P5c */
    pk_reset();                                         /* C3-4 */
}

uint32_t bo3_tr_stat(uint32_t which)
{
    return which == 0 ? s_applications : which == 1 ? s_refusals : which == 2 ? s_written : which == 3 ? s_marks :
           which == 4 ? s_seed_marks : which == 5 ? s_seed_refusals : s_lanes_raised;   /* 4..6: v4 */
}

/* Walks the set: every trigger's flow floats, in order. Fills va[] (the six floats of each record) up to cap; returns the count,
 * or -1 with *why set when the set fails the structural check. */
static long walk(uint32_t set, uint32_t *va, uint32_t cap, const char **why, uint32_t *ntrig_out, uint32_t *t0_out)
{
    uint32_t ntrig = 0, tp = 0;
    long n = 0;
    if (!rd32(set + BO3_TR_SET_TRIG, &tp) || !rd32(set + BO3_TR_SET_TRIG + 4, &ntrig)) {
        *why = "set header not readable";
        return -1;
    }
#if MUT != 3
    if (ntrig > BO3_TR_MAX_TRIG) {
        *why = "too many triggers";
        return -1;
    }
#endif
    *ntrig_out = ntrig;
    for (uint32_t k = 0; k < ntrig; k++) {
        uint32_t trig = tp + k * BO3_TR_TRIG_SIZE, fp = 0, fn = 0, probe = 0;
        (void)probe;
        if (!rd32(trig + BO3_TR_TRIG_FLOWP, &fp) || !rd32(trig + BO3_TR_TRIG_FLOWN, &fn)) {
            *why = "trigger not readable";
            return -1;
        }
#if MUT == 6
        if (k > 0)
            break;                                      /* defect: the later triggers are not scaled */
#endif
        if (k == 0)
            *t0_out = fn;
        if (!fn)
            continue;
#if MUT != 3
        if (fn > BO3_TR_MAX_FLOWS) {
            *why = "too many flow records in a trigger";
            return -1;
        }
        /* the whole table must be readable (one read of its last byte range proves the window) */
        if (!rd(fp, &probe, 4) || !rd(fp + fn * BO3_TR_FLOW_REC - 4, &probe, 4)) {
            *why = "flow table outside guest memory";
            return -1;
        }
#endif
        for (uint32_t j = 0; j < fn; j++)
            for (uint32_t c = 0; c < 6; c++) {
                if ((uint32_t)n >= cap) {
                    *why = "too many flow values";
                    return -1;
                }
                va[n++] = fp + j * BO3_TR_FLOW_REC + 4 + 4 * c;
            }
    }
    return n;
}

/* v6 (patch 70): each flow record's road key (trigger << 8 | the trigger's p5 road byte), in walk() order; 0xFFFFFFFF = no road
 * byte for it. Returns 0 when the walk does not give exactly nrec records (then no fill at all). */
/* main21 patch 90 (open-list item 12, the modder's "lanes outside the sectors filled"): the record whose rates an empty lane r
 * takes. key = (trigger << 8) | road (rec_keys). mode 1 (v6): the first flowing lane of the same road in the same trigger;
 * mode 2 (BM_TRAFFIC_FILL_EARLIER): else the same road in an EARLIER trigger, the nearest first; mode 3 (BM_TRAFFIC_FILL_ANY): else
 * a LATER trigger, the nearest first. r = none (the lane stays empty). Retail census (patch 70, 377 sets): 2,807 lanes by mode 1,
 * 5,568 by mode 2, 6,841 by mode 3. MUT 64: mode 1 also takes earlier triggers  65: mode 2 also takes later triggers */
static int lane_flows(const uint32_t *orig, long q)
{
    double s = 0.0;
    for (int c = 0; c < 6; c++)
        s += bits_f(orig[q + c]);
    return s > 0.0;
}

static long fill_src(const uint32_t *key, const uint32_t *orig, long n, long r, uint32_t mode)
{
    uint32_t kr = key[r / 6];
    for (long q = 0; q + 6 <= n; q += 6) {
#if MUT == 61
        if (q == r)                                     /* defect: a lane of any road lends its rates */
#else
        if (q == r || key[q / 6] != kr)
#endif
            continue;
        if (lane_flows(orig, q))
            return q;
    }
#if MUT != 64
    if (mode < BM_TRAFFIC_FILL_EARLIER)
        return r;
#endif
    for (long q = r - 6; q >= 0; q -= 6)
        if (key[q / 6] != 0xFFFFFFFFu && (key[q / 6] & 0xFFu) == (kr & 0xFFu) && (key[q / 6] >> 8) < (kr >> 8) && lane_flows(orig, q))
            return q;
#if MUT == 65
    if (mode < BM_TRAFFIC_FILL_EARLIER)
#else
    if (mode < BM_TRAFFIC_FILL_ANY)
#endif
        return r;
    for (long q = r + 6; q + 6 <= n; q += 6)
        if (key[q / 6] != 0xFFFFFFFFu && (key[q / 6] & 0xFFu) == (kr & 0xFFu) && (key[q / 6] >> 8) > (kr >> 8) && lane_flows(orig, q))
            return q;
    return r;
}

static int rec_keys(uint32_t set, uint32_t ntrig, uint32_t *key, uint32_t nrec)
{
    uint32_t tp = 0, m = 0;
    if (!rd32(set + BO3_TR_SET_TRIG, &tp))
        return 0;
    for (uint32_t k = 0; k < ntrig; k++) {
        uint32_t trig = tp + k * BO3_TR_TRIG_SIZE, fn = 0, rp = 0;
        if (!rd32(trig + BO3_TR_TRIG_FLOWN, &fn) || !rd32(trig + BO3_TR_TRIG_ROADS, &rp))
            return 0;
        for (uint32_t j = 0; j < fn; j++) {
            uint8_t road = 0;
            if (m >= nrec)
                return 0;
#if MUT == 62
            key[m++] = road;                            /* defect: the trigger not part of the key (roads of other triggers lend) */
            (void)rp;
#else
            key[m++] = rp && rd(rp + j, &road, 1) ? (k << 8) | road : 0xFFFFFFFFu;
#endif
        }
    }
    return m == nrec;
}

static void apply(uint32_t t)
{
    uint32_t set = 0, ntrig = 0, t0 = 0, *va = NULL, *cur = NULL, *orig = NULL;
    const char *why = NULL;
    long n;
    int same, wrote_any = 0;
    float d = (float)s_density;
    double t0_game = 0, t0_now = 0;
    uint32_t written = 0;

    if (!s_verified || t != BO3_TR_SYSTEM)
        return;
    if (!rd32(t + BO3_TR_SET, &set) || !set)
        return;                                         /* no set (a mode without traffic data) */
    /* zero touch: density 1, no lane floor and nothing written for this set -> nothing to do */
#if MUT == 32
    if (s_density == 1.0 && s_cache_set != set)         /* defect: the floor alone never applies */
#else
    if (s_density == 1.0 && !(BO3_HOOKREQ_P5A && (s_floor > 0.0f || s_fill)) && s_cache_set != set)
#endif
        return;
    va = (uint32_t *)malloc(sizeof(uint32_t) * BO3_TR_MAX_VALUES);
    if (!va)
        return;
    n = walk(set, va, BO3_TR_MAX_VALUES, &why, &ntrig, &t0);
    if (n < 0) {
        s_refusals++;
        if (s_log) {
            char line[200];
            snprintf(line, sizeof line, "[TRAFFIC] traffic set refused (%s): nothing written", why);
            s_log(line);
        }
        free(va);
        return;
    }
    cur = (uint32_t *)malloc(sizeof(uint32_t) * (size_t)(n ? n : 1));
    orig = (uint32_t *)malloc(sizeof(uint32_t) * (size_t)(n ? n : 1));
    if (!cur || !orig) {
        free(va), free(cur), free(orig);
        return;
    }
    same = s_cache_set == set && s_cache_n == (uint32_t)n && (n == 0 || memcmp(s_va, va, sizeof(uint32_t) * (size_t)n) == 0);
    for (long i = 0; i < n; i++) {
        float o;
        if (!rd32(va[i], &cur[i])) {
            why = "flow value not readable";
            break;
        }
#if MUT == 2
        (void)same;
        orig[i] = cur[i];                               /* defect: every set-up scales the scaled values again */
#else
        orig[i] = (same && cur[i] == s_wrote[i]) ? s_orig[i] : cur[i];
#endif
        o = bits_f(orig[i]);
#if MUT == 3
        (void)o;
#else
        if (!(o >= 0.0f && o <= BO3_TR_MAX_FLOW)) {     /* also refuses NaN */
            why = "a flow value outside 0 .. 1000";
            break;
        }
#endif
    }
    if (why) {
        s_refusals++;
        if (s_log) {
            char line[200];
            snprintf(line, sizeof line, "[TRAFFIC] traffic set refused (%s): nothing written", why);
            s_log(line);
        }
        free(va), free(cur), free(orig);
        return;
    }
    /* the new cache (positions, originals, what is written): made whole before the first write */
    {
        size_t sz = sizeof(uint32_t) * (size_t)(n ? n : 1);
        uint32_t *nva = (uint32_t *)malloc(sz), *nor = (uint32_t *)malloc(sz), *nwr = (uint32_t *)malloc(sz);
        if (!nva || !nor || !nwr) {
            free(nva), free(nor), free(nwr);
            free(va), free(cur), free(orig);
            return;                                     /* out of host memory: nothing written, the old cache kept */
        }
        free(s_va), free(s_orig), free(s_wrote);
        s_va = nva, s_orig = nor, s_wrote = nwr;
    }
    /* v4: the lane floor, per flow record (6 class values in walk order), after the density: a lane summing to 0 < S < floor is
     * scaled by floor / S; lanes at or above it and empty lanes keep their (density) values */
    {
        float fl = BO3_HOOKREQ_P5A ? s_floor : 0.0f;
        uint32_t *key = (BO3_HOOKREQ_P5A && s_fill && n >= 6) ? (uint32_t *)malloc(sizeof(uint32_t) * (size_t)(n / 6)) : NULL;
        if (key && !rec_keys(set, ntrig, key, (uint32_t)(n / 6))) {
            free(key);                                  /* the road arrays are not readable: no fill (the rest as before) */
            key = NULL;
        }
        s_lanes_raised = 0;
        s_lanes_filled = 0;
        for (long r = 0; r + 6 <= n; r += 6) {
            double S = 0.0;
            long src = r;                               /* v6: the record whose originals this lane uses */
            if (key && key[r / 6] != 0xFFFFFFFFu) {
                int empty = 1;
                for (int c = 0; c < 6; c++)
                    empty &= bits_f(orig[r + c]) == 0.0f;
                if (empty && (src = fill_src(key, orig, n, r, s_fill)) != r)
                    s_lanes_filled++;
            }
            for (int c = 0; c < 6; c++)
#if MUT == 33
                S += bits_f(orig[src + c]);             /* defect: the floor compared before the density */
#else
                S += (double)(bits_f(orig[src + c]) * d);
#endif
            if (fl > 0.0f && S > 0.0
#if MUT != 31
                && S < (double)fl                       /* MUT 31 defect: a multiplier, lanes above the floor scaled too */
#endif
                ) {
                double k = (double)fl / S;
                for (int c = 0; c < 6; c++) {
                    float v = (float)((double)(bits_f(orig[src + c]) * d) * k);
                    s_wrote[r + c] = f_bits(v);         /* the raised value, taken below */
                }
                s_lanes_raised++;
            } else {
                for (int c = 0; c < 6; c++)
                    s_wrote[r + c] = d == 1.0f ? orig[src + c] : f_bits(bits_f(orig[src + c]) * d);
            }
        }
        free(key);
    }
    for (long i = 0; i < n; i++) {
        float o = bits_f(orig[i]);
        uint32_t w = s_wrote[i];                        /* density x original, the floor applied (v4) */
#if MUT == 7
        if (1) {                                        /* defect: every value rewritten, changed or not */
#else
        if (w != cur[i]) {
#endif
            if (!s_g.write(s_g.user, va[i], &w, 4))
                w = cur[i];                             /* (a refused write keeps the value; checked windows make it rare) */
            else
                written++, wrote_any = 1;
        }
        s_va[i] = va[i];
        s_orig[i] = orig[i];
        s_wrote[i] = w;
        if ((uint32_t)i < t0 * 6u) {
            t0_game += o;
            t0_now += bits_f(w);
        }
    }
    s_cache_set = set;
    s_cache_n = (uint32_t)n;
    s_t0_game = (float)t0_game;
    s_t0_now = (float)t0_now;
    s_density_applied = d;
    s_written += written;
    if (wrote_any || d != 1.0f || s_lanes_raised || s_lanes_filled)
        s_applications++;
    if (wrote_any && s_log) {
        char line[360];
        snprintf(line, sizeof line, "[TRAFFIC] %sdensity %.2f at the traffic set-up: %u triggers, %u flow records, start flow %.1f -> %.1f "
                 "vehicles/min (%u values written); lane floor %.2f: %u lanes raised", d > (float)BM_TRAFFIC_DENSITY_LABELLED ?
                 "EXPERIMENTAL " : "", (double)d, (unsigned)ntrig, (unsigned)(n / 6), t0_game, t0_now, (unsigned)written,
                 (double)(BO3_HOOKREQ_P5A ? s_floor : 0.0f), (unsigned)s_lanes_raised);
        s_log(line);
    }
    free(va), free(cur), free(orig);
}

void bo3_tr_gen_init(uint32_t traffic)
{
    s_marks++;
    pk_new_load();                                      /* C3-4: a new traffic set-up rebuilds the cursors: parked cars forgotten */
    apply(traffic);
}

/* ---- v4: the traffic reset's seed ---- */
/* the census of the sites v4 relies on (default.xbe 9f497acd; tests\p5a checks the table against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_p5a_census[] = {
    { 0x001A3EA0u, 32, { 0x0f,0x57,0xc0,0x83,0xec,0x0c,0x56,0xc7,0x80,0x4c,0x63,0x03,0x00,0xf8,0xd6,0xb9,0x02,0xc7,0x80,0x48,
                         0x63,0x03,0x00,0x07,0x29,0x46,0xfd,0x33,0xc9,0x57,0xf3,0x0f } },     /* the reset: both seed words */
    { 0x001A1A18u, 7,  { 0x8b,0xc6,0xe8,0x81,0x24,0x00,0x00 } },                              /* init: mov eax, esi; call */
};
/* END-CENSUS */

static int p5a_census(void)
{
    if (s_p5a_census_ok >= 0)
        return s_p5a_census_ok;
    if (!s_configured || !s_g.read)
        return 0;
#if MUT == 36
    s_p5a_census_ok = 1;                                /* defect: the sites' bytes not checked */
#else
    s_p5a_census_ok = BO3_HOOKREQ_P5A && s_verified;
    for (size_t k = 0; s_p5a_census_ok && k < sizeof s_p5a_census / sizeof s_p5a_census[0]; k++) {
        uint8_t b[32];
        if (!rd(s_p5a_census[k].va, b, s_p5a_census[k].n) || memcmp(b, s_p5a_census[k].b, s_p5a_census[k].n))
            s_p5a_census_ok = 0;
    }
#endif
    return s_p5a_census_ok;
}

void bo3_tr_gen_seed(uint32_t traffic)
{
    uint32_t lo = 0, hi = 0, nlo, nhi;
    if (!BO3_HOOKREQ_P5A)
        return;
    s_seed_marks++;
    if (s_seed_mode != BM_TRAFFIC_SEED_FIXED)
        return;                                         /* the game's own seed: nothing written */
    if (traffic != BO3_TR_SYSTEM || !p5a_census())
        return;
    /* fail closed: only the state the reset has just written is replaced (anything else = not the expected path) */
    if (!rd32(traffic + BO3_TR_SEED_LO, &lo) || !rd32(traffic + BO3_TR_SEED_HI, &hi)
#if MUT != 34
        || lo != BO3_TR_GAME_SEED_LO || hi != BO3_TR_GAME_SEED_HI
#endif
        ) {
        s_seed_refusals++;
        if (s_log)
            s_log("[TRAFFIC] seed not applied: the spawn generator does not hold the game's reset value (nothing written)");
        return;
    }
#if MUT == 35
    nlo = s_seed;                                       /* defect: seed 0 is not the game's own state */
#else
    nlo = BO3_TR_GAME_SEED_LO ^ s_seed;
#endif
    nhi = BO3_TR_GAME_SEED_HI;
    if (s_g.write(s_g.user, traffic + BO3_TR_SEED_LO, &nlo, 4) && s_g.write(s_g.user, traffic + BO3_TR_SEED_HI, &nhi, 4))
        s_seeds_applied++;
    else
        s_seed_refusals++;
}

static int32_t TD_CALL t_set_seed(td_host *host, uint32_t mode, uint32_t seed)
{
    if (!host || mode > BM_TRAFFIC_SEED_FIXED || (mode == BM_TRAFFIC_SEED_GAME && seed != 0))
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P5A || !p5a_census())
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT != 37
    if (s_seed_owner && s_seed_owner != host)
        return BM_TRAFFIC_CONFLICT;
#endif
    s_seed_mode = mode;
    s_seed = seed;
    s_seed_owner = mode == BM_TRAFFIC_SEED_GAME ? NULL : host;     /* GAME by the owner releases */
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_set_lane_floor(td_host *host, float cars_per_min)
{
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P5A || !s_verified)
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT != 38
    if (!isfinite(cars_per_min) || cars_per_min < 0.0f || cars_per_min > BM_TRAFFIC_LANE_FLOOR_MAX)
        return BM_TRAFFIC_OUT_OF_RANGE;
#endif
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;                     /* one owner of the set's flows (the density's) */
    s_owner = host;
    s_floor = cars_per_min;
    return BM_TRAFFIC_OK;
}

/* ---- v3: the crash pool ---- */
/* the census of the sites v3 relies on (default.xbe 9f497acd; tests\p23\traffic_v3 checks the table against the XBE file)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_tr3_census[] = {
    { 0x00114910u, 32, { 0x53,0x55,0x56,0x57,0x8b,0x7c,0x24,0x14,0x8b,0x5f,0x0c,0x8b,0xe9,0xc6,0x07,0x04,0x33,0xc0,0x8d,0x8d,
                         0xc0,0x5d,0x03,0x00,0xeb,0x06,0x8d,0x9b,0x00,0x00,0x00,0x00 } },          /* the pool walk */
    { 0x0011495Cu, 16, { 0x83,0xf8,0x40,0x7c,0xcf,0xeb,0x0b,0x40,0xeb,0x08,0x83,0xc0,0x02,0xeb,0x03,0x83 } },  /* no full guard */
    { 0x00111750u, 16, { 0x51,0x8a,0x83,0x18,0x02,0x00,0x00,0x33,0xc9,0x3c,0xff,0x89,0x0c,0x24,0x75,0x06 } },  /* induce */
    { 0x0019F818u, 16, { 0x0f,0x8c,0x62,0xfe,0xff,0xff,0xeb,0x17,0x8b,0x4c,0x24,0x20,0x6a,0x01,0x8b,0xde } },  /* its retail call */
};
/* END-CENSUS */

static int tr3_census(void)
{
    if (s_tr3_census_ok >= 0)
        return s_tr3_census_ok;
    if (!s_configured || !s_g.read)
        return 0;
#if MUT == 25
    s_tr3_census_ok = 1;                                /* defect: the sites' bytes not checked */
#else
    s_tr3_census_ok = BO3_HOOKREQ_P23 && s_verified;
    for (size_t k = 0; s_tr3_census_ok && k < sizeof s_tr3_census / sizeof s_tr3_census[0]; k++) {
        uint8_t b[32];
        if (!rd(s_tr3_census[k].va, b, s_tr3_census[k].n) || memcmp(b, s_tr3_census[k].b, s_tr3_census[k].n))
            s_tr3_census_ok = 0;
    }
#endif
    return s_tr3_census_ok;
}

/* the crash pool's used slots (0 .. 64), or -1 when unreadable */
static int pool_used(void)
{
    int used = 0;
    for (uint32_t i = 0; i < BM_TRAFFIC_WRECK_SLOTS; i++) {
        uint8_t b = 0;
#if MUT == 21
        if (!rd(TR3_POOL + i * TR3_SLOT, &b, 1))        /* defect: the slot's first byte, not its occupancy byte */
#else
        if (!rd(TR3_POOL + i * TR3_SLOT + TR3_OCC, &b, 1))
#endif
            return -1;
        used += b != 0;
    }
    return used;
}

/* the pre-check of a wreck: BM_TRAFFIC_OK or POOL_FULL (free slots >= FREE_MIN and crashing < the game's cap) */
static int32_t pool_check(uint32_t crashing)
{
    int used = pool_used();
    if (used < 0)
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT == 22
    if ((int)BM_TRAFFIC_WRECK_SLOTS - used < 1)         /* defect: one free slot is enough (a linked pair takes 3) */
#else
    if ((int)BM_TRAFFIC_WRECK_SLOTS - used < (int)BM_TRAFFIC_WRECK_FREE_MIN)
#endif
        return BM_TRAFFIC_POOL_FULL;
#if MUT != 23
    if (crashing >= BM_P23_TRAFFIC_CRASHING_CAP)
        return BM_TRAFFIC_POOL_FULL;
#endif
    return BM_TRAFFIC_OK;
}

static int32_t wreck_rate(td_host *host, uint32_t step)
{
    uint32_t k, recent = 0;
    for (k = 0; k < TR3_SLOTS && s_wr_host[k] && s_wr_host[k] != (uintptr_t)host; k++)
        ;
    if (k == TR3_SLOTS)
        return BM_TRAFFIC_RATE;
    s_wr_host[k] = (uintptr_t)host;
    for (uint32_t i = 0; i < s_wr_n[k]; i++)
        recent += step - s_wr_recent[k][i] < TR3_RATE_STEPS;
#if MUT != 24
    if (recent >= BM_TRAFFIC_WRECKS_PER_SECOND)
        return BM_TRAFFIC_RATE;
#endif
    s_wr_recent[k][s_wr_n[k] < BM_TRAFFIC_WRECKS_PER_SECOND ? s_wr_n[k]++ : step % BM_TRAFFIC_WRECKS_PER_SECOND] = step;
    return BM_TRAFFIC_OK;
}

/* tests: the guard and the rate on their own (the vehicle layout is not verified in this build) */
int32_t bo3_tr3_pool_check_for_test(uint32_t crashing) { return pool_check(crashing); }
int32_t bo3_tr3_rate_for_test(const void *host, uint32_t step) { return wreck_rate((td_host *)(uintptr_t)host, step); }
void bo3_tr3_new_race(void)
{
    s_wrecks_by_plugins = s_pool_refusals = 0;
    memset(s_wr_n, 0, sizeof s_wr_n);
}

/* ---- P5b (main21 patch 68, hook request v2): the traffic vehicle records -> near_vehicles / wreck of v3 ----
 * STATIC facts (census below): the active bitmap T + 0x362E0 and the record base T + 0x127D0 (0x180 a record) as the traffic update
 * walks them (0x1A2567); the position at record + 0xA0 (the per-vehicle update's live-radius test, 0x1A6B89); the record by index
 * 0x625FB0 + 0x180 i and the state bits + 0x174 (& 4 / & 6) in the kamikaze pass (0x19F576, 0x19F65A: "& 6" = do not induce);
 * the induce call shape EBX = racer physics vehicle, ESI = 0x64B310, push record, push 1 (0x19F820, P23 census). From the modder's
 * PS2 map, cross-checked by those reads: + 0x173 class. NOT runtime-verified yet (combined probe): speeds are host-derived from
 * the sampled positions (steps / 60 s); "crashed" = the game's own "& 6" test. BO3_HOOKREQ_P5B=0: both answer UNAVAILABLE. */
#ifndef BO3_HOOKREQ_P5B
#define BO3_HOOKREQ_P5B 0
#endif
#define TR5_CAR1      0x0073A1D0u   /* player 1's car R; world matrix R + 0x10 right, + 0x20 up, + 0x30 at, + 0x40 pos (bm_racers.c, RT) */
#define TR5_PLAYERS   (TR3_M + 0x1CB80u)    /* the players' physics vehicles (2 x 0x4AD0, vtable 0x3B1160; V + 0x13F4 = R) */
#define TR5_PLAYER_SZ 0x4AD0u
#define TR5_PLAYER_VT 0x003B1160u
#define TR5_V_R       0x13F4u
#define TR5_JUMP_M    50.0f         /* a step that moves farther is a respawn: the samples start again */
#define TR5_PENDING   16u
static int s_p5b_census_ok = -1;
static float s_vpos[BO3_TR_MAX_VEH][3], s_vvel[BO3_TR_MAX_VEH][3];
static uint32_t s_vstep[BO3_TR_MAX_VEH];
static uint8_t s_vhave[BO3_TR_MAX_VEH];     /* 0 none, 1 position, 2 position + velocity */
static float s_ppos[3], s_pvel[3];
static uint32_t s_pstep, s_phave;
static uint32_t s_pend[TR5_PENDING], s_npend, s_wreck_done, s_wreck_none;
static uint32_t (*s_induce)(void *user, uint32_t inducer_vehicle, uint32_t record);
static void *s_induce_user;
void bo3_tr_set_induce(uint32_t (*fn)(void *user, uint32_t inducer_vehicle, uint32_t record), void *user)
{
    s_induce = fn;
    s_induce_user = user;
}
uint32_t bo3_tr5_stat(uint32_t which) { return which == 0 ? s_wreck_done : which == 1 ? s_wreck_none : s_npend; }
static void bo3_tr5_reset(void)
{
    s_p5b_census_ok = -1;
    memset(s_vhave, 0, sizeof s_vhave);
    s_phave = 0;
    s_npend = s_wreck_done = s_wreck_none = 0;
}

/* BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_p5b_census[] = {
    { 0x001A2567u, 24, { 0x8b,0x83,0xe0,0x62,0x03,0x00,0x33,0xff,0x89,0x44,0x24,0x30,0x8a,0x83,0xab,0x63,0x03,0x00,0x84,0xc0,
                         0x8d,0xb3,0xd0,0x27 } },                                             /* bitmap, pool, record base */
    { 0x001A6B89u, 16, { 0x0f,0x28,0x06,0x0f,0x28,0x8f,0xa0,0x00,0x00,0x00,0x0f,0x5c,0xc8,0x0f,0x57,0xc0 } },  /* pos + 0xA0 */
    { 0x0019F576u, 24, { 0x0f,0xb6,0x47,0x4a,0x8d,0x1c,0x40,0xc1,0xe3,0x07,0x81,0xc3,0xb0,0x5f,0x62,0x00,0xf6,0x83,0x74,0x01,
                         0x00,0x00,0x04,0x89 } },                                             /* record by index, + 0x174 & 4 */
    { 0x0019F65Au, 7,  { 0xf6,0x83,0x74,0x01,0x00,0x00,0x06 } },                              /* + 0x174 & 6: do not induce */
};
/* END-CENSUS */

static int p5b_census(void)
{
    if (s_p5b_census_ok >= 0)
        return s_p5b_census_ok;
    if (!s_configured || !s_g.read)
        return 0;
#if MUT == 41
    s_p5b_census_ok = 1;                                /* defect: the sites' bytes not checked */
#else
    s_p5b_census_ok = BO3_HOOKREQ_P5B && s_verified;
    for (size_t k = 0; s_p5b_census_ok && k < sizeof s_p5b_census / sizeof s_p5b_census[0]; k++) {
        uint8_t b[32];
        if (!rd(s_p5b_census[k].va, b, s_p5b_census[k].n) || memcmp(b, s_p5b_census[k].b, s_p5b_census[k].n))
            s_p5b_census_ok = 0;
    }
#endif
    return s_p5b_census_ok;
}

static uint32_t rec_of(uint32_t i) { return BO3_TR_SYSTEM + BO3_TR_RECS + i * BO3_TR_REC_SIZE; }
static uint32_t crashing_now(void);

static int alive(uint32_t i)
{
    uint32_t w = 0;
    uint8_t pool = 0;
    if (i >= BO3_TR_MAX_VEH || !rd(BO3_TR_SYSTEM + BO3_TR_POOL, &pool, 1) || i >= pool)
        return 0;
#if MUT == 42
    return rd32(BO3_TR_SYSTEM + BO3_TR_BITMAP + 4u * i, &w) && w;   /* defect: the word of index i, not bit i of word i / 32 */
#else
    return rd32(BO3_TR_SYSTEM + BO3_TR_BITMAP + 4u * (i / 32u), &w) && ((w >> (i % 32u)) & 1u);
#endif
}

static int rdvec(uint32_t va, float *v)
{
    if (!rd(va, v, 12))
        return 0;
    return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

static uint8_t rec_flags(uint32_t i)
{
    uint8_t f = 0xFF;
    rd(rec_of(i) + BO3_TR_REC_FLAGS, &f, 1);
    return f;
}

/* player 1's physics vehicle (the inducer): the players' pool entry whose V + 0x13F4 is the car R (bm_racers.c's search) */
static uint32_t player_vehicle(void)
{
    for (uint32_t k = 0; k < 2u; k++) {
        uint32_t v = TR5_PLAYERS + k * TR5_PLAYER_SZ, vt = 0, back = 0;
        if (rd32(v, &vt) && vt == TR5_PLAYER_VT && rd32(v + TR5_V_R, &back) && back == TR5_CAR1)
            return v;
    }
    return 0;
}

static void sample(float *pos, float *vel, uint32_t *pstep, uint8_t *have, const float *now, uint32_t step)
{
    if (*have && step > *pstep) {
        float d[3] = {now[0] - pos[0], now[1] - pos[1], now[2] - pos[2]};
        float dt = (float)(step - *pstep) / 60.0f;
        if (sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) > TR5_JUMP_M)
            *have = 1;                                  /* a respawn / reset: start again */
        else {
            for (int c = 0; c < 3; c++)
#if MUT == 43
                vel[c] = d[c];                          /* defect: not divided by the step time */
#else
                vel[c] = d[c] / dt;
#endif
            *have = 2;
        }
    } else if (!*have)
        *have = 1;
    if (step != *pstep || *have == 1)
        memcpy(pos, now, 12), *pstep = step;
}

/* ---- main21 patch 89: DEV-ONLY traffic lane probe (open-list items 10 parked cars / 11 racing-lane traffic; NEVER a release) ----
 * STATIC facts it checks at run time (sub_001A6B40, the per-vehicle update; sub_001A75A0, the removal):
 *   record + 0x114 = the lane cursor C (C + 0x30 float progress, C + 0x2C copied to record + 0xC4, C + 0x41 road index into the
 *   road table 0x60EC2C (0x4C a road; [road] + 0x10 = its node count), C + 0x46 a flag), + 0x118 the next lane, + 0x110 a linked
 *   record (removed with it), + 0x11C a float set with the lane, + 0x140 / + 0x144 / + 0x148 floats (speed / target / step:
 *   HYPOTHESIS), + 0x173 class, + 0x174 state, + 0x70 .. + 0xAC the matrix rows (HYPOTHESIS from pos + 0xA0).
 *   Removal: C + 0x46 == 0 and (int)C + 0x30 >= nodes - 1 and + 0x118 == 0 -> sub_001A75A0 -> the despawn sub_001A3970.
 * Logged (stderr, "[TRPROBE]"): once per load the first 48 roads (pointer, nodes, the first 4 words of the 0x4C entry); every 2 s
 * (120 steps) the player position and the 4 live records nearest to it (all the fields above). At most 600 lines a load. */
#ifndef BO3_DEV_TRPROBE
#define BO3_DEV_TRPROBE 0
#endif
#if BO3_DEV_TRPROBE
#define TP_ROADS 0x0060EC2Cu
static uint32_t s_tp_last = 0xFFFFFFFFu, s_tp_lines, s_tp_said, s_tp_loads;
static double s_tp_tsum, s_tp_tmax, s_tp_t0;           /* main21 patch 90: the per-vehicle loop's time (us) */
static uint32_t s_tp_tn;
/* main21 patch 92 (DEV ONLY, open-list item 17): the entry of the wreck conversion sub_00114910 (ECX = M, the physics world;
 * [esp] = the caller's return address, [esp + 4] = the participant V (type byte [V], set to 4 by the routine), [V + 0xC] = its
 * body, [body + 0x13F4] = a racer's race object R; [esp + 8 .. + 0x18] = the other 5 arguments as the callers push them: the
 * contact response sub_001135E0 passes [0x73BB8C], body + 0x218, 1, 1, 1). Every conversion of a load is logged (at most 64). */
static uint32_t s_tw_n, s_tw_load;
void bo3_tr_dev_wreck(uint32_t m, uint32_t esp)
{
    uint32_t a[7] = { 0, 0, 0, 0, 0, 0, 0 }, v, body = 0, r = 0;
    uint8_t ty = 0;
    if (s_tw_load != s_tp_loads) {
        s_tw_load = s_tp_loads;
        s_tw_n = 0;
    }
    if (s_tw_n >= 64u)
        return;
    s_tw_n++;
    for (int k = 0; k < 7; k++)
        rd32(esp + 4u * (uint32_t)k, &a[k]);
    v = a[1];
    if (v) {
        rd(v, &ty, 1);
        rd32(v + 0xCu, &body);
        if (body)
            rd32(body + 0x13F4u, &r);
    }
    fprintf(stderr, "[TRPROBE] wreck %u: M %08x caller %08x V %08x type %u body %08x race object %08x | args %08x %08x %08x %08x %08x\n",
            (unsigned)s_tw_n, (unsigned)m, (unsigned)a[0], (unsigned)v, (unsigned)ty, (unsigned)body, (unsigned)r,
            (unsigned)a[2], (unsigned)a[3], (unsigned)a[4], (unsigned)a[5], (unsigned)a[6]);
}

/* main21 patch 97 (DEV ONLY, item 17 probe R34): the racer crash entry sub_0011FC60 (reached from the physics vehicle's vtable
 * 0x3B1160 slot + 8, sub_00118E30). ECX = the vehicle; at this entry [esp] = the return into sub_00118E30, [esp + 4] = a (the s8
 * "crashed by" index stored at vehicle + 0x218), [esp + 8] = b (passed to R->vt[+0xC]); sub_00118E30 pushed ebx / esi / edi
 * ([esp + 0xC .. + 0x14]), so [esp + 0x18] = the return into ITS caller (the code that decided the crash) and [esp + 0x1C] /
 * [esp + 0x20] its two arguments. Logged: the vehicle's crashed byte + 0x210 and + 0x218 before, R =
 * [vehicle + 0x13F4] and R's vtable (0x3B11A0 player, 0x3B1204 AI), R + 0x18FA. At most 64 a load. */
static uint32_t s_tc_n, s_tc_load;
void bo3_tr_dev_crash(uint32_t veh, uint32_t esp)
{
    uint32_t s[9] = { 0, 0, 0, 0, 0, 0, 0, 0, 0 }, r = 0, rvt = 0;
    uint8_t crashed = 0, by = 0, wr = 0;
    if (s_tc_load != s_tp_loads) {
        s_tc_load = s_tp_loads;
        s_tc_n = 0;
    }
    if (s_tc_n >= 64u || !veh)
        return;
    s_tc_n++;
    for (int k = 0; k < 9; k++)
        rd32(esp + 4u * (uint32_t)k, &s[k]);
    rd(veh + 0x210u, &crashed, 1);
    rd(veh + 0x218u, &by, 1);
    rd32(veh + 0x13F4u, &r);
    if (r) {
        rd32(r, &rvt);
        rd(r + 0x18FAu, &wr, 1);
    }
    fprintf(stderr, "[TRPROBE] crash %u: vehicle %08x crashed %u by %d | race object %08x vt %08x wrecked %u | ret %08x a %08x b %08x"
            " | decider %08x a %08x b %08x\n", (unsigned)s_tc_n, (unsigned)veh, (unsigned)crashed, (int)(int8_t)by, (unsigned)r,
            (unsigned)rvt, (unsigned)wr, (unsigned)s[0], (unsigned)s[1], (unsigned)s[2], (unsigned)s[6], (unsigned)s[7],
            (unsigned)s[8]);
}

/* main21 patch 90 (DEV ONLY): marks before (0) / after (1) the per-vehicle loop of sub_001A20F0 (loc_001A25EC / loc_001A264F) */
void bo3_tr_dev_time(uint32_t edge)
{
    struct timespec ts;
    double us;
    timespec_get(&ts, TIME_UTC);
    us = (double)ts.tv_sec * 1e6 + (double)ts.tv_nsec / 1e3;
    if (!edge) {
        s_tp_t0 = us;
        return;
    }
    if (s_tp_t0 > 0.0 && us >= s_tp_t0) {
        s_tp_tsum += us - s_tp_t0;
        s_tp_tmax = us - s_tp_t0 > s_tp_tmax ? us - s_tp_t0 : s_tp_tmax;
        s_tp_tn++;
    }
    s_tp_t0 = 0.0;
}
static float tp_f(uint32_t va) { uint32_t u = 0; rd32(va, &u); return bits_f(u); }
static uint32_t tp_u8(uint32_t va) { uint8_t b = 0; rd(va, &b, 1); return b; }
static void tr_probe(uint32_t step)
{
    float pp[3] = { 0, 0, 0 }, d2[4] = { 1e30f, 1e30f, 1e30f, 1e30f };
    uint32_t best[4] = { 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu };
    if (!s_tp_said) {
        s_tp_said = 1;
        fprintf(stderr, "[TRPROBE] DEV ONLY traffic lane probe active (BO3_DEV_TRPROBE): never a release\n");
    }
    if (step < s_tp_last || s_tp_last == 0xFFFFFFFFu) {          /* a new load (the step count starts again) */
        s_tp_lines = 0;
        s_tp_loads++;
        for (uint32_t k = 0; k < 48u; k++) {
            uint32_t e = TP_ROADS + 0x4Cu * k, p = 0, w[4] = { 0, 0, 0, 0 }, nodes = 0;
            rd32(e, &p);
            for (int j = 0; j < 4; j++)
                rd32(e + 4u * (uint32_t)j, &w[j]);
            if (p)
                rd32(p + 0x10u, &nodes);
            fprintf(stderr, "[TRPROBE] load %u road %u entry %08x: [0] %08x nodes %u, words %08x %08x %08x %08x\n", (unsigned)s_tp_loads,
                    (unsigned)k, (unsigned)e, (unsigned)p, (unsigned)nodes, (unsigned)w[0], (unsigned)w[1], (unsigned)w[2], (unsigned)w[3]);
        }
        s_tp_last = step;
    }
    if (step - s_tp_last < 120u || s_tp_lines >= 600u)
        return;
    s_tp_last = step;
    rdvec(TR5_CAR1 + 0x40u, pp);
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {
        float p[3], d;
        if (!alive(i) || !rdvec(rec_of(i) + BO3_TR_REC_POS, p))
            continue;
        d = (p[0] - pp[0]) * (p[0] - pp[0]) + (p[1] - pp[1]) * (p[1] - pp[1]) + (p[2] - pp[2]) * (p[2] - pp[2]);
        for (int k = 0; k < 4; k++)
            if (d < d2[k]) {
                for (int j = 3; j > k; j--)
                    d2[j] = d2[j - 1], best[j] = best[j - 1];
                d2[k] = d, best[k] = i;
                break;
            }
    }
    fprintf(stderr, "[TRPROBE] step %u player %.1f %.1f %.1f\n", (unsigned)step, (double)pp[0], (double)pp[1], (double)pp[2]);
    s_tp_lines++;
    {   /* main21 patch 90: the trigger machine (sub_001A3AE0): current trigger + 0x363B1, stage + 0x363B2, time / position mode
         * + 0x363B7 / + 0x363B8, the next threshold: float + 0x363A0 (time), u16 + 0x363A4 + byte + 0x363A6 (position), clock 0x60EA20;
         * the vehicle loop's mean time (item 13) */
        uint16_t a4 = 0;
        rd(BO3_TR_SYSTEM + 0x363A4u, &a4, 2);
        fprintf(stderr, "[TRPROBE] trigger %u stage %u mode B7 %u B8 %u | next: time %.2f (clock %.2f) position %u + %u | vehicle loop "
                "%.1f us mean over %u frames (max %.1f)\n", (unsigned)tp_u8(BO3_TR_SYSTEM + 0x363B1u),
                (unsigned)tp_u8(BO3_TR_SYSTEM + 0x363B2u), (unsigned)tp_u8(BO3_TR_SYSTEM + 0x363B7u),
                (unsigned)tp_u8(BO3_TR_SYSTEM + 0x363B8u), (double)tp_f(BO3_TR_SYSTEM + 0x363A0u), (double)tp_f(0x0060EA20u),
                (unsigned)a4, (unsigned)tp_u8(BO3_TR_SYSTEM + 0x363A6u), s_tp_tn ? s_tp_tsum / (double)s_tp_tn : 0.0,
                (unsigned)s_tp_tn, s_tp_tmax);
        s_tp_tsum = 0.0, s_tp_tn = 0, s_tp_tmax = 0.0;
        s_tp_lines++;
    }
    for (int k = 0; k < 4 && best[k] != 0xFFFFFFFFu; k++) {
        uint32_t r = rec_of(best[k]), c = 0, nx = 0, lk = 0, road, nodes = 0, rp = 0;
        float p[3];
        rd32(r + 0x114u, &c);
        rd32(r + 0x118u, &nx);
        rd32(r + 0x110u, &lk);
        rdvec(r + BO3_TR_REC_POS, p);
        road = c ? tp_u8(c + 0x41u) : 0xFFu;
        if (road != 0xFFu && rd32(TP_ROADS + 0x4Cu * road, &rp) && rp)
            rd32(rp + 0x10u, &nodes);
        fprintf(stderr, "[TRPROBE]  rec %u (%.0f m) class %u state %02x cursor %08x next %08x link %08x | C+30 %.2f C+2C %.2f road %u "
                "(%u nodes) C+46 %u | +11C %.2f +140 %.2f +144 %.2f +148 %.2f +C4 %.2f | pos %.1f %.1f %.1f | +70 %.2f %.2f %.2f "
                "+80 %.2f %.2f %.2f +90 %.2f %.2f %.2f\n", (unsigned)best[k], (double)sqrtf(d2[k]), (unsigned)tp_u8(r + 0x173u),
                (unsigned)tp_u8(r + 0x174u), (unsigned)c, (unsigned)nx, (unsigned)lk, c ? (double)tp_f(c + 0x30u) : -1.0,
                c ? (double)tp_f(c + 0x2Cu) : -1.0, (unsigned)road, (unsigned)nodes, c ? (unsigned)tp_u8(c + 0x46u) : 0u,
                (double)tp_f(r + 0x11Cu), (double)tp_f(r + 0x140u), (double)tp_f(r + 0x144u), (double)tp_f(r + 0x148u),
                (double)tp_f(r + 0xC4u), (double)p[0], (double)p[1], (double)p[2], (double)tp_f(r + 0x70u), (double)tp_f(r + 0x74u),
                (double)tp_f(r + 0x78u), (double)tp_f(r + 0x80u), (double)tp_f(r + 0x84u), (double)tp_f(r + 0x88u),
                (double)tp_f(r + 0x90u), (double)tp_f(r + 0x94u), (double)tp_f(r + 0x98u));
        s_tp_lines++;
    }
}
#endif

#ifndef BO3_DEV_PROPPROBE
#define BO3_DEV_PROPPROBE 0
#endif
#if BO3_DEV_PROPPROBE
/* main21 patch 100 (DEV ONLY, open-list item 3, never a release): Road Rage prop bodies. sub_00110420 (T = ebx, the traffic system
 * object) asks the mode at 0x1108E6 (patch 80 may change the answer); answer != 0 jumps straight to loc_00110A9D (no prop bodies),
 * else loc_0011094B / loc_001109B3 set the unit loop limit and the loop raises the u32 count T + 0x1CB70 once per body. "made" =
 * count at loc_00110A9D minus count at the gate. sub_00111850 (T = esi, called by the traffic system sub_001AA720) walks the bodies
 * and decrements the count at loc_0011188D per body whose byte [rec + 1] == 1; kind = byte [rec]. One summary line per call that
 * removed bodies, at most PP_RM_LINES per build; at most PP_BUILD_LINES build lines in all. */
#define PP_BUILD_LINES 32u
#define PP_RM_LINES    32u
#define PP_KINDS       8u           /* kinds 0..6, then "other" */
static uint32_t s_pp_builds, s_pp_t, s_pp_ans, s_pp_before, s_pp_path, s_pp_limit, s_pp_lines, s_pp_rm_lines, s_pp_rm_calls;
static int32_t s_pp_made;
static uint32_t s_pp_rm_t, s_pp_rm_ret, s_pp_rm_before, s_pp_rm_n, s_pp_kind[PP_KINDS];

void bo3_pp_dev_gate(uint32_t t, uint32_t answer)
{
    if (!s_pp_builds)
        fprintf(stderr, "[PROPPROBE] DEV ONLY Road Rage prop probe active (BO3_DEV_PROPPROBE): never a release\n");
    s_pp_builds++;
    s_pp_t = t;
    s_pp_ans = answer & 0xFFu;
    s_pp_before = 0;
    rd32(t + 0x1CB70u, &s_pp_before);
    s_pp_path = 0;
    s_pp_limit = 0;
#if MUT != 91
    s_pp_rm_lines = 0;
#endif
}

void bo3_pp_dev_path(uint32_t path)
{
#if MUT == 92
    s_pp_path = path;
#else
    if (!s_pp_path)
        s_pp_path = path;
#endif
}

void bo3_pp_dev_limit(uint32_t limit) { s_pp_limit = limit; }

void bo3_pp_dev_made(uint32_t t)
{
    static const char *const k_path[3] = { "skip", "94B", "9B3" };
    uint32_t after = 0;
    rd32(t + 0x1CB70u, &after);
#if MUT == 93
    s_pp_made = (int32_t)after;
#else
    s_pp_made = (int32_t)(after - s_pp_before);
#endif
    if (s_pp_lines >= PP_BUILD_LINES)
        return;
    s_pp_lines++;
    fprintf(stderr, "[PROPPROBE] build %u: T %08x%s answer %02x (%s) path %s limit %d count %u -> %u made %d\n",
            (unsigned)s_pp_builds, (unsigned)t, t == s_pp_t ? "" : " (gate T differs)", (unsigned)s_pp_ans,
            s_pp_ans ? "Road Rage: no props" : "props allowed", k_path[s_pp_path < 3u ? s_pp_path : 0u], (int)s_pp_limit,
            (unsigned)s_pp_before, (unsigned)after, (int)s_pp_made);
}

void bo3_pp_dev_rm_begin(uint32_t t, uint32_t esp)
{
    s_pp_rm_t = t;
    s_pp_rm_ret = 0;
    rd32(esp, &s_pp_rm_ret);
    s_pp_rm_before = 0;
    rd32(t + 0x1CB70u, &s_pp_rm_before);
    s_pp_rm_n = 0;
#if MUT != 94
    memset(s_pp_kind, 0, sizeof s_pp_kind);
#endif
}

void bo3_pp_dev_rm_one(uint32_t rec)
{
    uint8_t k = 0;
    rd(rec, &k, 1);
    s_pp_rm_n++;
#if MUT == 95
    s_pp_kind[k & 7u]++;
#else
    s_pp_kind[k < PP_KINDS - 1u ? k : PP_KINDS - 1u]++;
#endif
}

void bo3_pp_dev_rm_end(uint32_t t)
{
    uint32_t after = 0;
#if MUT != 96
    if (!s_pp_rm_n)
        return;
#endif
    s_pp_rm_calls++;
    if (s_pp_rm_lines >= PP_RM_LINES)
        return;
    s_pp_rm_lines++;
    rd32(t + 0x1CB70u, &after);
    fprintf(stderr, "[PROPPROBE] remove %u (build %u): T %08x%s ret %08x count %u -> %u removed %u | kind 0:%u 1:%u 2:%u 3:%u 4:%u"
            " 5:%u 6:%u other:%u\n", (unsigned)s_pp_rm_calls, (unsigned)s_pp_builds, (unsigned)t, t == s_pp_rm_t ? "" : " (entry T differs)",
            (unsigned)s_pp_rm_ret, (unsigned)s_pp_rm_before, (unsigned)after, (unsigned)s_pp_rm_n, (unsigned)s_pp_kind[0],
            (unsigned)s_pp_kind[1], (unsigned)s_pp_kind[2], (unsigned)s_pp_kind[3], (unsigned)s_pp_kind[4], (unsigned)s_pp_kind[5],
            (unsigned)s_pp_kind[6], (unsigned)s_pp_kind[7]);
}

void bo3_pp_dev_stats(uint32_t out[14])
{
    out[0] = s_pp_builds;
    out[1] = (uint32_t)s_pp_made;
    out[2] = s_pp_path;
    out[3] = s_pp_limit;
    out[4] = s_pp_lines;
    out[5] = s_pp_rm_lines;
    for (uint32_t k = 0; k < PP_KINDS; k++)
        out[6u + k] = s_pp_kind[k];
}
#endif

#if BO3_DEV_TRPROBE
static void pk_probe(uint32_t step);
#endif
void bo3_tr_gen_update(uint32_t traffic)
{
    uint32_t step = 0;
    float p[3];
    if (!BO3_HOOKREQ_P5B || traffic != BO3_TR_SYSTEM || !p5b_census() || !rd32(TR3_STEP, &step))
        return;
#if BO3_DEV_TRPROBE
    tr_probe(step);
    pk_probe(step);                                     /* C3-4 DEV: parked cars + the racing-lane layout */
#endif
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {
        if (!alive(i) || !rdvec(rec_of(i) + BO3_TR_REC_POS, p)) {
            s_vhave[i] = 0;                             /* a new vehicle in this slot starts its samples again */
            continue;
        }
        sample(s_vpos[i], s_vvel[i], &s_vstep[i], &s_vhave[i], p, step);
    }
    if (rdvec(TR5_CAR1 + 0x40u, p)) {
        uint8_t h = (uint8_t)s_phave;
        sample(s_ppos, s_pvel, &s_pstep, &h, p, step);
        s_phave = h;
    } else
        s_phave = 0;
    /* the queued wrecks, re-checked now (live, inducible, the crash pool), the game's own call with its retail shape */
    for (uint32_t k = 0; k < s_npend; k++) {
        uint32_t i = s_pend[k], v = player_vehicle();
#if MUT != 44
        if (!alive(i) || (rec_flags(i) & BO3_TR_NOT_INDUCIBLE))
            continue;                                   /* gone or crashing meanwhile: nothing */
#endif
        if (!v || !s_induce || pool_check(crashing_now()) != BM_TRAFFIC_OK) {
            s_pool_refusals += s_induce && v;
            continue;
        }
        if (s_induce(s_induce_user, v, rec_of(i)))
            s_wreck_done++, s_wrecks_by_plugins++;
        else
            s_wreck_none++;                             /* the game's fatal table refused the pair: no wreck */
    }
    s_npend = 0;
}

static float dot3(const float *a, const float *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

/* vehicles the game itself would not induce now (state & 6): the crashing count of the pool guard */
static uint32_t crashing_now(void)
{
    uint32_t c = 0;
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++)
        c += alive(i) && (rec_flags(i) & BO3_TR_NOT_INDUCIBLE);
    return c;
}

static int32_t TD_CALL t_near_vehicles(td_host *host, uint32_t player, bm_traffic_vehicle *out, uint32_t *n)
{
    uint32_t set = 0, step = 0, idx[BO3_TR_MAX_VEH], cnt = 0, room, sz;
    float m[4][4], d2[BO3_TR_MAX_VEH];
    if (!host || !out || !n || out->struct_size < 8 || *n > BM_TRAFFIC_NEAR_MAX)
        return BM_TRAFFIC_BAD_ARG;
    room = *n;
    sz = out->struct_size < sizeof(bm_traffic_vehicle) ? out->struct_size : (uint32_t)sizeof(bm_traffic_vehicle);
    *n = 0;
    if (!BO3_HOOKREQ_P5B || !p5b_census())
        return BM_TRAFFIC_UNAVAILABLE;
    if (player != 0)
        return BM_TRAFFIC_BAD_ARG;                      /* one player only (split screen untested platform-wide) */
    if (!rd32(BO3_TR_SYSTEM + BO3_TR_SET, &set) || !set || !rd32(TR3_STEP, &step))
        return BM_TRAFFIC_UNAVAILABLE;                  /* not in a race */
    for (int r = 0; r < 4; r++)
        if (!rdvec(TR5_CAR1 + 0x10u + 0x10u * (uint32_t)r, m[r]))
            return BM_TRAFFIC_UNAVAILABLE;
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {
        float p[3], d[3];
        if (!alive(i) || !rdvec(rec_of(i) + BO3_TR_REC_POS, p))
            continue;
        for (int c = 0; c < 3; c++)
            d[c] = p[c] - m[3][c];
        d2[cnt] = dot3(d, d);
        idx[cnt++] = i;
    }
    /* the nearest first (selection of `room` entries) */
    for (uint32_t k = 0; k < room && k < cnt; k++) {
        uint32_t best = k;
#if MUT != 45
        for (uint32_t j = k + 1; j < cnt; j++)
            if (d2[j] < d2[best])
                best = j;
#endif
        {
            float t = d2[k];
            uint32_t ti = idx[k];
            d2[k] = d2[best], idx[k] = idx[best];
            d2[best] = t, idx[best] = ti;
        }
    }
    for (uint32_t k = 0; k < room && k < cnt; k++) {
        bm_traffic_vehicle e;
        uint32_t i = idx[k];
        float p[3], d[3];
        uint8_t cls = 0, fl = rec_flags(i);
        memset(&e, 0, sizeof e);
        rdvec(rec_of(i) + BO3_TR_REC_POS, p);
        rd(rec_of(i) + BO3_TR_REC_CLASS, &cls, 1);
        for (int c = 0; c < 3; c++)
            d[c] = p[c] - m[3][c];
        e.struct_size = sz;
        e.handle = ((step & 0xFFFFFFu) << 8) | (i + 1u);
#if MUT == 46
        e.rel_pos_m[0] = -dot3(d, m[0]);                /* defect: right / left swapped */
#else
        e.rel_pos_m[0] = dot3(d, m[0]);                 /* x right, y up, z forward (the car's own matrix rows) */
#endif
        e.rel_pos_m[1] = dot3(d, m[1]);
        e.rel_pos_m[2] = dot3(d, m[2]);
        e.speed_mps = s_vhave[i] == 2 ? sqrtf(dot3(s_vvel[i], s_vvel[i])) : 0.0f;
        e.same_direction = s_vhave[i] == 2 && dot3(s_vvel[i], m[2]) > 0.0f;
        e.crashed = (fl & BO3_TR_NOT_INDUCIBLE) != 0;
        e.vehicle_class = cls;
        memcpy((uint8_t *)out + (size_t)k * sz, &e, sz);
        (*n)++;
    }
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_wreck(td_host *host, uint32_t handle)
{
    uint32_t step = 0, i = (handle & 0xFFu) - 1u;
    int32_t rc;
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !tr3_census() || !BO3_HOOKREQ_P5B || !p5b_census() || !s_induce)
        return BM_TRAFFIC_UNAVAILABLE;
    if (!rd32(TR3_STEP, &step))
        return BM_TRAFFIC_UNAVAILABLE;
    if ((handle & 0xFFu) == 0 || i >= BO3_TR_MAX_VEH)
        return BM_TRAFFIC_BAD_ARG;
#if MUT != 47
    if ((handle >> 8) != (step & 0xFFFFFFu))
        return BM_TRAFFIC_STALE;                        /* a handle from another step */
#endif
    if (!alive(i) || (rec_flags(i) & BO3_TR_NOT_INDUCIBLE))
        return BM_TRAFFIC_NOT_LIVE;
    for (uint32_t k = 0; k < s_npend; k++)
        if (s_pend[k] == i)
            return BM_TRAFFIC_OK;                       /* already queued for this update */
    if ((rc = pool_check(crashing_now())) != BM_TRAFFIC_OK) {
        s_pool_refusals += rc == BM_TRAFFIC_POOL_FULL;
        return rc;
    }
    if ((rc = wreck_rate(host, step)) != BM_TRAFFIC_OK)
        return rc;
#if MUT != 48
    if (s_npend >= TR5_PENDING)
        return BM_TRAFFIC_RATE;
#endif
    s_pend[s_npend++ % TR5_PENDING] = i;
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_clear_wrecked(td_host *host, float min_distance_m)
{
    if (!host || !isfinite(min_distance_m) || min_distance_m < BM_TRAFFIC_CLEAR_MIN_M)
        return BM_TRAFFIC_BAD_ARG;
#if BM_P23_TRAFFIC_DESPAWN_FREES && BM_P23_TRAFFIC_VEHICLES_KNOWN && MUT != 26
#error "BM_P23_TRAFFIC_DESPAWN_FREES: add the despawn path first"
#else
    return MUT == 26 ? BM_TRAFFIC_OK : BM_TRAFFIC_UNAVAILABLE;   /* PR-B decides (MUT 26: defect, accepted unproven) */
#endif
}

/* ---- P5c (main21 patch 69, hook request v2 "Traffic Attack spread"): the lane section fill sub_001A6070 ----
 * STATIC (census): loc_001A61C1 computes e = length / (mph x 0.44704) x (1 / 60) x the lane's summed flows and skips the section
 * when 0.5 > e (0x1A61D9 comiss / ja); loc_001A61E5: spacing = length / e, N = (int)(e + 0.5); per car i loc_001A62A4: position =
 * (float)i x xmm1, xmm1 = rand x spacing (a fresh draw of the spawn generator) unless 0x649B97 / 0x649B98 are set (then spacing),
 * then sub_001A6070's placement call 0x19E160. The marks change e (the minimum) and the position (the spread) only. */
#ifndef BO3_HOOKREQ_P5C
#define BO3_HOOKREQ_P5C 0
#endif
static int s_p5c_census_ok = -1;
static uint32_t s_spread, s_sections_raised, s_cars_spread;
static float s_secmin;
static float s_sec_e;                       /* the last section's e as continued (the placements of that section follow) */
static uint32_t s_sec_n;

/* BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[36]; } s_p5c_census[] = {
    { 0x001A61C1u, 36, { 0x0f,0x28,0xc1,0xf3,0x0f,0x5e,0xc2,0xf3,0x0f,0x59,0x05,0x38,0x18,0x3b,0x00,0xf3,0x0f,0x10,0x15,0x84,
                         0x16,0x3b,0x00,0xf3,0x0f,0x59,0xc3,0x0f,0x2f,0xd0,0x0f,0x87,0xa1,0x03,0x00,0x00 } },  /* e, 0.5 > e: none */
    { 0x001A61E5u, 13, { 0xf3,0x0f,0x5e,0xc8,0xf3,0x0f,0x58,0xc2,0xf3,0x0f,0x2c,0xc8,0x85 } },            /* spacing, N = e + 0.5 */
    { 0x001A62A4u, 15, { 0xf3,0x0f,0x2a,0x44,0x24,0x18,0xf3,0x0f,0x59,0xc1,0xe8,0xad,0x7e,0xff,0xff } },  /* i x (rand x spacing) */
    { 0x001A6240u, 20, { 0x8a,0x0d,0x97,0x9b,0x64,0x00,0x84,0xc9,0x75,0x54,0x8a,0x0d,0x98,0x9b,0x64,0x00,0x84,0xc9,0x75,0x4a } },
};
/* END-CENSUS */

static int p5c_census(void)
{
    if (s_p5c_census_ok >= 0)
        return s_p5c_census_ok;
    if (!s_configured || !s_g.read)
        return 0;
#if MUT == 51
    s_p5c_census_ok = 1;                                /* defect: the sites' bytes not checked */
#else
    s_p5c_census_ok = BO3_HOOKREQ_P5C && s_verified;
    for (size_t k = 0; s_p5c_census_ok && k < sizeof s_p5c_census / sizeof s_p5c_census[0]; k++) {
        uint8_t b[36];
        if (!rd(s_p5c_census[k].va, b, s_p5c_census[k].n) || memcmp(b, s_p5c_census[k].b, s_p5c_census[k].n))
            s_p5c_census_ok = 0;
    }
#endif
    return s_p5c_census_ok;
}

static void bo3_tr5c_reset(void)
{
    s_p5c_census_ok = -1;
    s_spread = 0;
    s_secmin = 0.0f;
    s_sections_raised = s_cars_spread = 0;
    s_sec_e = 0.0f;
    s_sec_n = 0;
}

float bo3_tr_gen_section(float e)
{
    float out = e;
    if (BO3_HOOKREQ_P5C && s_secmin > 0.0f && isfinite(e) && e > 0.0f &&
#if MUT == 52
        1 &&                                            /* defect: sections at or above the minimum lowered to it */
#else
        e < s_secmin &&
#endif
        p5c_census()) {
        out = s_secmin;
        s_sections_raised++;
    }
#if MUT == 53
    if (BO3_HOOKREQ_P5C && s_secmin > 0.0f && e <= 0.0f && p5c_census())
        out = s_secmin;                                 /* defect: a lane without flow gets cars */
#endif
    s_sec_e = out;
    s_sec_n = out >= 0.5f ? (uint32_t)(int32_t)(out + 0.5f) : 0u;   /* the game's own cvttss2si (e + 0.5) */
    return out;
}

float bo3_tr_gen_place(float game_pos, float i, float rand_spacing, float spacing)
{
    uint8_t f1 = 1, f2 = 1;
    float frac, len;
    if (!BO3_HOOKREQ_P5C || !s_spread || !p5c_census() || !s_sec_n || !(spacing > 0.0f) || !isfinite(rand_spacing))
        return game_pos;
    /* the game's no-random case (0x649B97 / 0x649B98 set: xmm1 = spacing, no draw) keeps its position */
#if MUT != 54
    if (!rd(0x00649B97u, &f1, 1) || !rd(0x00649B98u, &f2, 1) || f1 || f2)
        return game_pos;
#endif
    frac = rand_spacing / spacing;                      /* the game's draw, 0 .. 1 */
    if (!(frac >= 0.0f && frac < 1.0f))
        return game_pos;
    len = spacing * s_sec_e;                            /* the section length */
    s_cars_spread++;
#if MUT == 55
    return (i + frac) * spacing;                        /* defect: N > e puts the last cars past the section end */
#else
    return (i + frac) * len / (float)s_sec_n;
#endif
}

static int32_t TD_CALL t_set_spawn_spread(td_host *host, uint32_t on)
{
    if (!host || on > 1u)
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P5C || !p5c_census())
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT != 56
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;
#endif
    s_owner = host;
    s_spread = on;
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_set_section_min(td_host *host, float cars)
{
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P5C || !p5c_census())
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT != 57
    if (!isfinite(cars) || cars < 0.0f || cars > BM_TRAFFIC_SECTION_MIN_MAX)
        return BM_TRAFFIC_OUT_OF_RANGE;
#endif
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;
    s_owner = host;
    s_secmin = cars;
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_set_fill_empty_lanes(td_host *host, uint32_t on)
{
    if (!host || on > BM_TRAFFIC_FILL_ANY)              /* main21 patch 90: 2 / 3 accepted (older hosts: BAD_ARG) */
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P5A || !s_verified)
        return BM_TRAFFIC_UNAVAILABLE;
#if MUT != 63
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;
#endif
    s_owner = host;
    s_fill = on;
    return BM_TRAFFIC_OK;
}

/* ---- main21 patch 109 (Bryan item 12 pre-load, traffic v7): the trigger ("sector") machine sub_001A3AE0's stage 7
 * (loc_001A3DC2) advances T + 0x363B1 and writes the NEXT trigger's start threshold: position mode (T + 0x363B7 == 0 and + 0x363B8
 * == 0) u16 T + 0x363A4 (+ byte + 0x363A6), compared with the player's race progress in sub_001A20F0 (0x1A22C3..); time mode float
 * T + 0x363A0 (clock [0x60EA20]); 0 / -1 = no next trigger. The mark at the common exit loc_001A3E61 (EBP = T) lowers the threshold
 * of each new trigger ONCE (the exit has several paths) by the plugin's amount: the next sector's cars are set up earlier.
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[32]; } s_pl_rows[] = {
    { 0x001A3DC2u, 32, { 0x8a,0x8d,0xb7,0x63,0x03,0x00,0xfe,0xc2,0x84,0xc9,0x88,0x95,0xb1,0x63,0x03,0x00,0x75,0x45,0x8a,0x8d,0xb8,
                         0x63,0x03,0x00,0x84,0xc9,0x75,0x3b,0x0f,0xb6,0xca,0x3b } },
    { 0x001A3DE2u, 32, { 0x48,0x50,0x7d,0x21,0x8b,0x50,0x4c,0x6b,0xc9,0x58,0x66,0x8b,0x54,0x11,0x50,0x66,0x89,0x95,0xa4,0x63,0x03,
                         0x00,0x8b,0x40,0x4c,0x8a,0x4c,0x01,0x52,0x88,0x8d,0xa6 } },
    { 0x001A3E02u, 32, { 0x63,0x03,0x00,0xeb,0x5a,0x66,0xc7,0x85,0xa4,0x63,0x03,0x00,0x00,0x00,0xc6,0x85,0xa6,0x63,0x03,0x00,0x00,
                         0xeb,0x48,0x0f,0xb6,0xca,0x3b,0x48,0x50,0x7d,0x30,0x8a } },
    { 0x001A3E22u, 32, { 0x95,0xb8,0x63,0x03,0x00,0x84,0xd2,0x74,0x14,0x8a,0x15,0x80,0x2d,0x75,0x00,0x84,0xd2,0x74,0x0a,0xf3,0x0f,
                         0x10,0x05,0xc4,0x69,0x3a,0x00,0xeb,0x1a,0x8b,0x50,0x4c } },
    { 0x001A3E42u, 32, { 0x6b,0xc9,0x58,0x8b,0x44,0x11,0x4c,0x89,0x85,0xa0,0x63,0x03,0x00,0xeb,0x10,0xf3,0x0f,0x10,0x05,0xc0,0x16,
                         0x3b,0x00,0xf3,0x0f,0x11,0x85,0xa0,0x63,0x03,0x00,0xc6 } },
    { 0x001A3E62u, 8,  { 0x85,0xbd,0x63,0x03,0x00,0x00,0xc6,0x85 } },
};
/* END-CENSUS */
#ifndef BO3_HOOKREQ_ZPL
#define BO3_HOOKREQ_ZPL 1           /* unit tests: the CMake option is not there */
#endif
#define PL_TRIG  0x363B1u
#define PL_B7    0x363B7u
#define PL_B8    0x363B8u
#define PL_POS   0x363A4u
#define PL_TIME  0x363A0u
static int s_pl_ok = -1;
static uint32_t s_pl_units, s_pl_set, s_pl_trig = 0xFFFFFFFFu, s_preloads, s_pl_lines;
static float s_pl_secs;

static int wr(uint32_t va, const void *in, uint32_t n)
{
    return s_configured && s_g.write && s_g.write(s_g.user, va, in, n);
}

static int pl_census(void)
{
#if MUT == 66
    return 1;
#endif
    if (s_pl_ok != 1) {
        s_pl_ok = 1;
        for (size_t k = 0; k < sizeof s_pl_rows / sizeof s_pl_rows[0]; k++) {
            uint8_t x[32];
            if (!rd(s_pl_rows[k].va, x, s_pl_rows[k].n) || memcmp(x, s_pl_rows[k].b, s_pl_rows[k].n))
                s_pl_ok = 0;
        }
    }
    return s_pl_ok;
}

void bo3_tr_gen_preload(uint32_t t)
{
    uint8_t cur = 0, b7 = 1, b8 = 1;
    uint32_t set = 0;
    if (!BO3_HOOKREQ_ZPL || t != BO3_TR_SYSTEM || (!s_pl_units && !(s_pl_secs > 0.0f)) || pl_census() != 1)
        return;
    if (!rd(t + PL_TRIG, &cur, 1) || !rd32(t + BO3_TR_SET, &set) || !set)
        return;
#if MUT != 67
    if (set == s_pl_set && cur == s_pl_trig)
        return;                                         /* this trigger's threshold is lowered already */
#endif
    s_pl_set = set;
    s_pl_trig = cur;
    rd(t + PL_B7, &b7, 1);
    rd(t + PL_B8, &b8, 1);
    if (!b7 && !b8) {                                   /* position mode, the game's own test */
        uint16_t a = 0, was;
        if (!rd(t + PL_POS, &a, 2) || a == 0u || a == 0xFFFFu || !s_pl_units)
            return;                                     /* no next trigger */
        was = a;
#if MUT == 68
        a = (uint16_t)(a - s_pl_units);                 /* defect: wraps below 0 */
#else
        a = a > s_pl_units + 1u ? (uint16_t)(a - s_pl_units) : (uint16_t)1u;
#endif
        wr(t + PL_POS, &a, 2);
        if (s_pl_lines++ < 8u)
            fprintf(stderr, "[TRAFFIC] pre-load: trigger %u position threshold %u -> %u\n", (unsigned)cur, (unsigned)was, (unsigned)a);
    } else {
        float f = 0.0f, was;
        if (!rd(t + PL_TIME, &f, 4) || !(f > 0.0f) || !(s_pl_secs > 0.0f))
            return;                                     /* -1 / 0: no next trigger */
        was = f;
        f = f > s_pl_secs ? f - s_pl_secs : 0.0f;
        wr(t + PL_TIME, &f, 4);
        if (s_pl_lines++ < 8u)
            fprintf(stderr, "[TRAFFIC] pre-load: trigger %u time threshold %.2f -> %.2f s\n", (unsigned)cur, (double)was, (double)f);
    }
    s_preloads++;
}

static int32_t TD_CALL t_set_preload(td_host *host, uint32_t position_units, float seconds)
{
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
#if MUT != 69
    if (position_units > BM_TRAFFIC_PRELOAD_POS_MAX || !isfinite(seconds) || seconds < 0.0f || seconds > BM_TRAFFIC_PRELOAD_S_MAX)
        return BM_TRAFFIC_OUT_OF_RANGE;
#endif
    if (!BO3_HOOKREQ_ZPL || !s_verified || pl_census() != 1)
        return BM_TRAFFIC_UNAVAILABLE;
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;
    s_owner = host;
    s_pl_units = position_units;
    s_pl_secs = seconds;
    s_pl_trig = 0xFFFFFFFFu;                            /* the current trigger's threshold may be lowered now */
    return BM_TRAFFIC_OK;
}

uint32_t bo3_tr_preloads(void) { return s_preloads; }

/* ---- main21 C3-4 (open-list item 10 "parked traffic", owner-approved; traffic v8 set_parked; notes\C3_4_PARKED_LANE_RE.md) ----
 * STATIC FACTS (census below; RE note s1 / s2):
 *   - the draw (sub_001A4710 0x1A4A49, sub_000303D0) and the players' collision (sub_0016EB60 -> sub_0016E5E0) use the record's
 *     matrix R + 0x70 / + 0x80 / + 0x90 rows + R + 0xA0 position as it is after the traffic update; the per-vehicle update
 *     sub_001A6B40 rewrites it every step (far: 0x1A7011 copies the cursor matrix; near: sub_001A7910). The pin is written at
 *     loc_001A264F, after the vehicle loop and the + 0x10C pass (ebx = T), so the draw and the collision see the pinned pose.
 *   - the collision needs a cursor (R + 0x114 = C) and takes the velocity from the cursor speed C + 0x2C: the car keeps its cursor,
 *     C + 0x00 (target) = C + 0x2C (speed) = 0, C + 0x30 (progress) fixed, C + 0x48 (lane-change budget) = 0, C + 0x4B bit 0 (road
 *     change) clear: it never reaches its road end and never changes lane.
 *   - the follow law (sub_0019F560 0x19FA05) reads only C + 0x44 (the cursor ahead): the game's unlink sub_001A0600 (EAX = C, a
 *     plain ret: no stack argument; it splices C out, moves the road front E + 0x46 when C was the front, clears C's node
 *     occupancy, C + 0x44 = C + 0x45 = 0xFF; no despawn) is called ONCE, so the cars behind follow the car ahead of it instead.
 *   HYPOTHESIS (the probe decides): the wreck path calls the unlink a second time (0x114BA7). Held with C + 0x44 = 0xFF and C + 0x45
 *   = the road's current front, that second unlink writes the front back unchanged (front.+0x44 = 0xFF, E + 0x46 = front). A front
 *   that changes between the last update and the crash (one step) is NOT covered.
 *   Adopted only in cursor states 1..5 (the RE recipe's far-car probe took state 1 only; 0 = ending its road and 6 / 7 = merging
 *   are refused), class 1, no + 0x10C / + 0x110 / + 0x118 link, not crashing, progress below its road's last node.
 * Release (set_parked(h, 0)): the host never re-links (sub_001A03F0's signature is not read). The target speed is given back and the
 *   pin stops; the link hold stays until the game's own road change (C + 0x41 changes: its unlink, then its insert) re-links it, or
 *   the record despawns. While releasing the car does not see the car ahead (it may run into / through it).
 * MUT 71: class rule not checked  72: unlinked at every update (not once)  73: C + 0x45 held at 0xFF (the second unlink empties the
 *   road front)  74: the guest call does not put the registers back */
#ifndef BO3_HOOKREQ_ZPK
#define BO3_HOOKREQ_ZPK 0
#endif
#define PK_CURS     0x0063DCB0u    /* lane cursors C = 0x63DCB0 + 0x50 j (sub_001A0600 0x1A0629) */
#define PK_CUR_SZ   0x50u
#define PK_ROADS    0x0060EC2Cu    /* road table E = 0x60EC2C + 0x4C r (sub_001A0600 0x1A0615) */
#define PK_ROAD_SZ  0x4Cu
#define PK_ROAD_N   48u
#define PK_R_MAT    0x70u          /* 4 x vec4: right, up, forward, position (64 bytes) */
#define PK_R_LINK   0x10Cu
#define PK_R_LINK2  0x110u
#define PK_R_CUR    0x114u
#define PK_R_NEXT   0x118u
#define PK_C_TARGET 0x00u
#define PK_C_SPEED  0x2Cu
#define PK_C_PROG   0x30u
#define PK_C_ROAD   0x41u
#define PK_C_AHEAD  0x44u
#define PK_C_BEHIND 0x45u
#define PK_C_STATE  0x46u
#define PK_C_LCB    0x48u
#define PK_C_J      0x49u
#define PK_C_REC    0x4Au
#define PK_C_FLAGS  0x4Bu
#define PK_E_FRONT  0x46u
#define PK_CLASS_CAR 1u
#define PK_NODES_MAX 4096u
enum { PK_FREE = 0, PK_PENDING, PK_PARKED, PK_RELEASING };
typedef struct pk_slot {
    uint32_t st, i, cur, j, set, road, target, given_back;
    float prog;
    uint32_t pose[16];
    const td_host *host;
    float game_d;                   /* how far the game's own vehicle pass had moved it before the pin (probe) */
} pk_slot;
static pk_slot s_pk[BM_TRAFFIC_PARK_MAX];
static int s_pk_ok = -1, s_pk_broken;
static uint32_t s_pk_parks, s_pk_refused, s_pk_released, s_pk_forgotten, s_pk_marks, s_pk_unlinks;
static uint32_t (*s_unlink)(void *user, uint32_t cursor);
static void *s_unlink_user;

/* binds the game's unlink sub_001A0600 (EAX = cursor); fn returns bit 0 = AL == 1 (the routine's own return), bit 1 = the stack
 * balanced. NULL (default) = set_parked UNAVAILABLE. */
void bo3_tr_set_unlink(uint32_t (*fn)(void *user, uint32_t cursor), void *user)
{
    s_unlink = fn;
    s_unlink_user = user;
}

/* BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_pk_rows[] = {
    { 0x001A264Fu, 12, { 0x8a,0x83,0xb0,0x63,0x03,0x00,0x33,0xf6,0x84,0xc0,0x76,0x28 } },          /* the pin mark: after the loops */
    { 0x001A0600u, 16, { 0x8a,0x48,0x41,0x80,0xf9,0xff,0x55,0x8b,0x2d,0x7c,0x9b,0x64,0x00,0x56,0x57,0x75 } },  /* the unlink */
    { 0x001A06D8u, 22, { 0x0f,0x57,0xc0,0x5f,0x5e,0xc6,0x40,0x44,0xff,0xc6,0x40,0x45,0xff,0xf3,0x0f,0x11,0x40,0x1c,0xb0,0x01,
                         0x5d,0xc3 } },                                                       /* its exit: + 44 / + 45 = FF, ret */
    { 0x001A7011u, 12, { 0x8a,0x9f,0x7a,0x01,0x00,0x00,0x8b,0x8f,0x14,0x01,0x00,0x00 } },          /* the far copy from the cursor */
    { 0x001A4A49u, 16, { 0x0f,0x28,0x47,0x70,0x0f,0x29,0x84,0x24,0xa0,0x00,0x00,0x00,0x0f,0x28,0x87,0x80 } },  /* draw: R + 0x70 */
    { 0x0019FA05u, 11, { 0x8a,0x47,0x44,0x3c,0xff,0x0f,0x84,0x50,0x01,0x00,0x00 } },               /* follow: only C + 0x44 */
};
/* END-CENSUS */

static int pk_census(void)
{
    if (s_pk_ok >= 0)
        return s_pk_ok;
    if (!s_configured || !s_g.read)
        return 0;
    s_pk_ok = BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZPK && BO3_HOOKREQ_P5B && s_verified && p5b_census();
    for (size_t k = 0; s_pk_ok && k < sizeof s_pk_rows / sizeof s_pk_rows[0]; k++) {
        uint8_t b[24];
        if (!rd(s_pk_rows[k].va, b, s_pk_rows[k].n) || memcmp(b, s_pk_rows[k].b, s_pk_rows[k].n))
            s_pk_ok = 0;
    }
    return s_pk_ok;
}

static void pk_new_load(void)
{
    memset(s_pk, 0, sizeof s_pk);       /* no guest write: the traffic init rebuilds every cursor */
}

static void pk_reset(void)
{
    memset(s_pk, 0, sizeof s_pk);       /* no guest write: a new load / configure rebuilds every cursor */
    s_pk_ok = -1;
    s_pk_broken = 0;
}

static uint8_t u8_at(uint32_t va) { uint8_t b = 0xFF; rd(va, &b, 1); return b; }

/* the checks a car must pass to be parked (at the request and again at the mark): BM_TRAFFIC_OK, NOT_LIVE or NOT_ALLOWED */
static int32_t pk_eligible(uint32_t i, uint32_t *cur_out, uint32_t *road_out, float *prog_out)
{
    uint32_t r = rec_of(i), c = 0, l1 = 1, l2 = 1, nx = 1, h = 0, nodes = 0;
    float prog = -1.0f;
    uint8_t road, s;
    if (!alive(i) || (rec_flags(i) & BO3_TR_NOT_INDUCIBLE))
        return BM_TRAFFIC_NOT_LIVE;
#if MUT != 71
    if (u8_at(r + BO3_TR_REC_CLASS) != PK_CLASS_CAR)
        return BM_TRAFFIC_NOT_ALLOWED;                  /* the modder's prototype rule: cars only */
#endif
    if (!rd32(r + PK_R_CUR, &c) || !c || c < PK_CURS || (c - PK_CURS) % PK_CUR_SZ || (c - PK_CURS) / PK_CUR_SZ >= 0xFFu)
        return BM_TRAFFIC_NOT_ALLOWED;                  /* no lane cursor (the collision needs one) */
    if (u8_at(c + PK_C_J) != (c - PK_CURS) / PK_CUR_SZ || u8_at(c + PK_C_REC) != i)
        return BM_TRAFFIC_NOT_ALLOWED;                  /* the cursor is not this record's */
    if (!rd32(r + PK_R_LINK, &l1) || !rd32(r + PK_R_LINK2, &l2) || !rd32(r + PK_R_NEXT, &nx) || l1 || l2 || nx)
        return BM_TRAFFIC_NOT_ALLOWED;                  /* towing / linked / changing lane */
    s = u8_at(c + PK_C_STATE);
    if (s == 0u || s > 5u || (u8_at(c + PK_C_FLAGS) & 1u))
        return BM_TRAFFIC_NOT_ALLOWED;                  /* ending its road (0), merging (6 / 7), or changing road */
    road = u8_at(c + PK_C_ROAD);
    if (road >= PK_ROAD_N || !rd32(PK_ROADS + PK_ROAD_SZ * road, &h) || !h || !rd32(h + 0x10u, &nodes) || nodes < 2u ||
        nodes > PK_NODES_MAX || !rd(c + PK_C_PROG, &prog, 4) || !isfinite(prog) || !(prog >= 0.0f) ||
        (int32_t)prog >= (int32_t)nodes - 1)
        return BM_TRAFFIC_NOT_ALLOWED;                  /* no road, or at its end (the game would remove it) */
    *cur_out = c;
    *road_out = road;
    *prog_out = prog;
    return BM_TRAFFIC_OK;
}

static int pk_find(uint32_t i)
{
    for (int k = 0; k < (int)BM_TRAFFIC_PARK_MAX; k++)
        if (s_pk[k].st != PK_FREE && s_pk[k].i == i)
            return k;
    return -1;
}

static uint32_t pk_used(int state)
{
    uint32_t n = 0;
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++)
        n += state < 0 ? s_pk[k].st != PK_FREE : s_pk[k].st == (uint32_t)state;
    return n;
}

static int32_t TD_CALL t_set_parked(td_host *host, uint32_t handle, uint32_t on)
{
    uint32_t step = 0, i = (handle & 0xFFu) - 1u, set = 0, cur = 0, road = 0;
    float prog = 0.0f;
    int k;
    int32_t rc;
    if (!host || on > 1u)
        return BM_TRAFFIC_BAD_ARG;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZPK || !BO3_HOOKREQ_P5B || !pk_census() || s_pk_broken || !s_unlink)
        return BM_TRAFFIC_UNAVAILABLE;
    if (!rd32(TR3_STEP, &step) || !rd32(BO3_TR_SYSTEM + BO3_TR_SET, &set) || !set)
        return BM_TRAFFIC_UNAVAILABLE;
    if ((handle & 0xFFu) == 0 || i >= BO3_TR_MAX_VEH)
        return BM_TRAFFIC_BAD_ARG;
    if ((handle >> 8) != (step & 0xFFFFFFu))
        return BM_TRAFFIC_STALE;
    k = pk_find(i);
    if (k >= 0 && s_pk[k].host != host)
        return BM_TRAFFIC_CONFLICT;                     /* another plugin's car */
    if (!on) {
        if (k < 0 || s_pk[k].st == PK_RELEASING)
            return BM_TRAFFIC_OK;
        s_pk[k].st = s_pk[k].st == PK_PENDING ? PK_FREE : PK_RELEASING;   /* pending: nothing done yet */
        return BM_TRAFFIC_OK;
    }
    if (k >= 0)
        return s_pk[k].st == PK_RELEASING ? BM_TRAFFIC_NOT_ALLOWED : BM_TRAFFIC_OK;
    if ((rc = pk_eligible(i, &cur, &road, &prog)) != BM_TRAFFIC_OK)
        return rc;
    if (pk_used(-1) >= BM_TRAFFIC_PARK_MAX)
        return BM_TRAFFIC_LIMIT;
    for (k = 0; s_pk[k].st != PK_FREE; k++)
        ;
    memset(&s_pk[k], 0, sizeof s_pk[k]);
    s_pk[k].st = PK_PENDING;
    s_pk[k].i = i;
    s_pk[k].cur = cur;
    s_pk[k].set = set;
    s_pk[k].host = host;
    return BM_TRAFFIC_OK;
}

/* releases the caller's cars (reset): parked -> releasing, pending -> nothing */
static void pk_release_host(const td_host *host)
{
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++)
        if (s_pk[k].st != PK_FREE && s_pk[k].host == host)
            s_pk[k].st = s_pk[k].st == PK_PENDING ? PK_FREE : PK_RELEASING;
}

/* the link hold: out of every list, the road front behind it (so a second unlink by the game writes the front back) */
static void pk_hold_links(const pk_slot *s)
{
    uint8_t ff = 0xFFu, front = u8_at(PK_ROADS + PK_ROAD_SZ * s->road + PK_E_FRONT);
#if MUT == 73
    front = 0xFFu;                                      /* defect: a second unlink sets the road front to none */
#endif
    if (front == s->j)
        front = 0xFFu;
    wr(s->cur + PK_C_AHEAD, &ff, 1);
    wr(s->cur + PK_C_BEHIND, &front, 1);
}

static void pk_forget(pk_slot *s, int released)
{
    s->st = PK_FREE;
    if (released)
        s_pk_released++;
    else
        s_pk_forgotten++;
}

/* the pending car: re-checked, its pose taken, unlinked once. 1 = parked now. */
static int pk_adopt(pk_slot *s)
{
    uint32_t r = rec_of(s->i), cur = 0, road = 0, res;
    float prog = 0.0f;
    int fin = 1;
    if (pk_eligible(s->i, &cur, &road, &prog) != BM_TRAFFIC_OK || cur != s->cur || s_pk_broken || !s_unlink ||
        !rd(r + PK_R_MAT, s->pose, sizeof s->pose) || !rd32(cur + PK_C_TARGET, &s->target))
        return 0;
    for (int q = 0; q < 16; q++)
        fin &= isfinite(bits_f(s->pose[q])) != 0;
    if (!fin)
        return 0;
    s->j = (cur - PK_CURS) / PK_CUR_SZ;
    s->road = road;
    s->prog = prog;
    res = s_unlink(s_unlink_user, cur);
    s_pk_unlinks++;
    if (!(res & 2u)) {
        s_pk_broken = 1;                                /* the stack did not balance: no new park in this process */
        if (s_log)
            s_log("[TRAFFIC] parked cars: the game's unlink did not balance the stack: set_parked UNAVAILABLE from now");
    }
    return (res & 1u) != 0;
}

void bo3_tr_gen_park(uint32_t traffic)
{
    uint32_t set = 0;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_ZPK || traffic != BO3_TR_SYSTEM || !pk_used(-1))
        return;                                         /* zero touch while nothing is parked */
    s_pk_marks++;
    if (!pk_census() || !rd32(traffic + BO3_TR_SET, &set))
        return;
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++) {
        pk_slot *s = &s_pk[k];
        uint32_t r = rec_of(s->i), c = 0, zero = 0;
        uint8_t fl;
        if (s->st == PK_FREE)
            continue;
        rd32(r + PK_R_CUR, &c);
        if (set != s->set || !alive(s->i) || c != s->cur || (rec_flags(s->i) & BO3_TR_NOT_INDUCIBLE)) {
            if (s->st == PK_PENDING)
                s->st = PK_FREE, s_pk_refused++;
            else
                pk_forget(s, s->st == PK_RELEASING);    /* gone, reused or crashed: the game's from here, no write */
            continue;
        }
        if (s->st == PK_PENDING) {
            if (!pk_adopt(s)) {
                s->st = PK_FREE, s_pk_refused++;
                continue;
            }
            s->st = PK_PARKED;
            s_pk_parks++;
        }
#if MUT == 72
        else if (s->st == PK_PARKED && s_unlink)
            s_unlink(s_unlink_user, s->cur), s_pk_unlinks++;   /* defect: unlinked again at every update */
#endif
        if (u8_at(s->cur + PK_C_ROAD) != s->road) {
            pk_forget(s, 1);                            /* the game's own road change re-linked it: not ours any more */
            continue;
        }
        if (s->st == PK_RELEASING) {
            if (!s->given_back) {
                wr(s->cur + PK_C_TARGET, &s->target, 4);   /* the game's target speed back: it drives off */
                s->given_back = 1;
            }
            continue;                                   /* links: below */
        }
        /* parked: speed 0 at the same progress, no lane / road change, out of the lists, the pose pinned */
        {
            float p[3];
            if (rdvec(r + BO3_TR_REC_POS, p)) {
                float dx = p[0] - bits_f(s->pose[12]), dy = p[1] - bits_f(s->pose[13]), dz = p[2] - bits_f(s->pose[14]);
                s->game_d = sqrtf(dx * dx + dy * dy + dz * dz);
            }
        }
        wr(s->cur + PK_C_TARGET, &zero, 4);
        wr(s->cur + PK_C_SPEED, &zero, 4);
        wr(s->cur + PK_C_PROG, &s->prog, 4);
        wr(s->cur + PK_C_LCB, &zero, 1);
        fl = (uint8_t)(u8_at(s->cur + PK_C_FLAGS) & ~1u);
        wr(s->cur + PK_C_FLAGS, &fl, 1);
        wr(r + PK_R_MAT, s->pose, sizeof s->pose);
    }
    /* the link holds last: an unlink above may have moved a road's front */
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++)
        if (s_pk[k].st == PK_PARKED || s_pk[k].st == PK_RELEASING)
            pk_hold_links(&s_pk[k]);
}

/* tests: 0 parks, 1 refused at the mark, 2 released, 3 forgotten, 4 marks with cars, 5 unlink calls, 6 broken */
uint32_t bo3_tr_pk_stat(uint32_t which)
{
    return which == 0 ? s_pk_parks : which == 1 ? s_pk_refused : which == 2 ? s_pk_released : which == 3 ? s_pk_forgotten :
           which == 4 ? s_pk_marks : which == 5 ? s_pk_unlinks : (uint32_t)s_pk_broken;
}

#if BO3_DEV_TRPROBE
/* ---- DEV ONLY (BO3_DEV_TRPROBE, never a release): the C3-4 probe, called from the P5b mark (loc_001A2567: the next update, before
 * the vehicle loop, so the record matrix read there is what the draw and the collision used) ----
 * parked (item 10), every 2 s while a car is parked / releasing: the pinned position vs the record's position read back now (what
 *   was drawn), how far the game's own vehicle pass had moved it before the pin, the cursor (speed, progress, links, state, budget,
 *   flags), the road front, the collision fields (R + 0x10C / + 0x114 / + 0x174 / + 0x17A), the cursors that still name it as their
 *   car ahead (0 expected) and the cars of its road within 15 nodes behind it (queued = slower than 1 m/s).
 * racing lane (item 11), once a load (2 s in): every road E with a header (H, occupancy base u16 + 4, front + 46, trigger / flow
 *   counts + 48 / + 49, + 4A / + 4B; H + 0 .. + 10, node 0's two vertex indices and vertices), the occupancy map pointer and the
 *   used end (max base + nodes); then every 2 s the player's nearest road / node (edge midpoints) with its place across, 0 (left
 *   edge) .. 1 (right edge), and for the 4 nearest cars their cursor's C + 08 / + 0C / + 4B and the cursor matrix M(j) position
 *   placed between its node's two edges (the lane offset rule). At most 300 lines a load. */
#define PK_M        0x00642C10u    /* cursor matrices M(j) = 0x642C10 + 0x50 j, + 0x30 position */
static uint32_t s_pkp_load = 0xFFFFFFFFu, s_pkp_step0, s_pkp_done, s_pkp_last, s_pkp_lines, s_pkp_auto, s_pkp_auto_step;
static int s_pkp_host;                                  /* the probe's own requester (DEV only) */
/* DEV only, so one probe run needs no plugin: 10 s into a load the nearest eligible class-1 car 20 .. 120 m from the player is
 * parked (once a load), and released 40 s later (the release path). */
static void pk_probe_auto(uint32_t step, const float *pp)
{
    const td_host *me = (const td_host *)(const void *)&s_pkp_host;
    uint32_t set = 0, best = 0xFFFFFFFFu, bcur = 0;
    float bd = 1e30f;
    if (s_pkp_auto == 1 && step - s_pkp_auto_step >= 2400u) {
        for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++)
            if (s_pk[k].st == PK_PARKED && s_pk[k].host == me) {
                s_pk[k].st = PK_RELEASING;
                fprintf(stderr, "[TRPROBE] parked auto: rec %u released at step %u\n", (unsigned)s_pk[k].i, (unsigned)step);
                s_pkp_lines++;
            }
        s_pkp_auto = 2;
        return;
    }
    if (s_pkp_auto || step - s_pkp_step0 < 600u || pk_used(-1) >= BM_TRAFFIC_PARK_MAX || !pk_census() || s_pk_broken || !s_unlink ||
        !rd32(BO3_TR_SYSTEM + BO3_TR_SET, &set) || !set)
        return;
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {
        uint32_t c = 0, road = 0;
        float p[3], prog = 0.0f, d;
        if (pk_find(i) >= 0 || pk_eligible(i, &c, &road, &prog) != BM_TRAFFIC_OK || !rdvec(rec_of(i) + BO3_TR_REC_POS, p))
            continue;
        d = sqrtf((p[0] - pp[0]) * (p[0] - pp[0]) + (p[1] - pp[1]) * (p[1] - pp[1]) + (p[2] - pp[2]) * (p[2] - pp[2]));
        if (d >= 20.0f && d <= 120.0f && d < bd)
            bd = d, best = i, bcur = c;
    }
    if (best == 0xFFFFFFFFu)
        return;
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++)
        if (s_pk[k].st == PK_FREE) {
            memset(&s_pk[k], 0, sizeof s_pk[k]);
            s_pk[k].st = PK_PENDING;
            s_pk[k].i = best;
            s_pk[k].cur = bcur;
            s_pk[k].set = set;
            s_pk[k].host = me;
            break;
        }
    s_pkp_auto = 1;
    s_pkp_auto_step = step;
    fprintf(stderr, "[TRPROBE] parked auto: rec %u (%.1f m from the player) requested at step %u\n", (unsigned)best, (double)bd,
            (unsigned)step);
    s_pkp_lines++;
}
static int pk_vert(uint32_t h, uint32_t node, float l[3], float rr[3])
{
    uint32_t na = 0, va = 0, n = 0;
    uint16_t lr[2] = { 0, 0 };
    if (!rd32(h, &na) || !rd32(h + 0xCu, &va) || !rd32(h + 0x10u, &n) || node >= n || n > PK_NODES_MAX || !rd(na + 4u * node, lr, 4))
        return 0;
    return rdvec(va + 16u * lr[0], l) && rdvec(va + 16u * lr[1], rr);
}
/* the place of p between the edges l .. rr: 0 = left, 1 = right; *d = distance to the midpoint */
static float pk_lat(const float *p, const float *l, const float *rr, float *d)
{
    float e[3] = { rr[0] - l[0], rr[1] - l[1], rr[2] - l[2] }, q[3] = { p[0] - l[0], p[1] - l[1], p[2] - l[2] }, ee = dot3(e, e);
    float m[3] = { p[0] - 0.5f * (l[0] + rr[0]), p[1] - 0.5f * (l[1] + rr[1]), p[2] - 0.5f * (l[2] + rr[2]) };
    *d = sqrtf(dot3(m, m));
    return ee > 0.0f ? dot3(q, e) / ee : -1.0f;
}
static void pk_probe_roads(void)
{
    uint32_t map = 0, end = 0;
    for (uint32_t r = 0; r < PK_ROAD_N; r++) {
        uint32_t e = PK_ROADS + PK_ROAD_SZ * r, h = 0, hw[5] = { 0, 0, 0, 0, 0 };
        uint16_t base = 0, lr[2] = { 0, 0 };
        float l[3] = { 0, 0, 0 }, rr[3] = { 0, 0, 0 };
        rd32(e, &h);
        if (!h)
            continue;
        rd(e + 4u, &base, 2);
        for (int q = 0; q < 5; q++)
            rd32(h + 4u * (uint32_t)q, &hw[q]);
        if (hw[0])
            rd(hw[0], lr, 4);
        pk_vert(h, 0, l, rr);
        if (hw[4] <= PK_NODES_MAX && base + hw[4] > end)
            end = base + hw[4];
        fprintf(stderr, "[TRPROBE] road %u E %08x: H %08x base %u front %u trig %u flow %u 4A %u 4B %u | H nodes@%08x +4 %08x +8 %08x"
                " verts@%08x n %u | node0 %u %u L %.1f %.1f %.1f R %.1f %.1f %.1f\n", (unsigned)r, (unsigned)e, (unsigned)h,
                (unsigned)base, (unsigned)u8_at(e + PK_E_FRONT), (unsigned)u8_at(e + 0x48u), (unsigned)u8_at(e + 0x49u),
                (unsigned)u8_at(e + 0x4Au), (unsigned)u8_at(e + 0x4Bu), (unsigned)hw[0], (unsigned)hw[1], (unsigned)hw[2],
                (unsigned)hw[3], (unsigned)hw[4], (unsigned)lr[0], (unsigned)lr[1], (double)l[0], (double)l[1], (double)l[2],
                (double)rr[0], (double)rr[1], (double)rr[2]);
        s_pkp_lines++;
    }
    rd32(0x00649B7Cu, &map);
    fprintf(stderr, "[TRPROBE] roads: occupancy map %08x, used end %u (max base + nodes)\n", (unsigned)map, (unsigned)end);
    s_pkp_lines++;
}
static void pk_probe_lane(const float *pp)
{
    float bd = 1e30f, bt = -1.0f, d2[4] = { 1e30f, 1e30f, 1e30f, 1e30f };
    uint32_t br = 0xFFu, bn = 0, best[4] = { 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu };
    for (uint32_t r = 0; r < PK_ROAD_N; r++) {          /* the player's road / node */
        uint32_t h = 0, n = 0;
        if (!rd32(PK_ROADS + PK_ROAD_SZ * r, &h) || !h || !rd32(h + 0x10u, &n) || n > PK_NODES_MAX)
            continue;
        for (uint32_t q = 0; q < n; q++) {
            float l[3], rr[3], d, t;
            if (!pk_vert(h, q, l, rr))
                break;
            t = pk_lat(pp, l, rr, &d);
            if (d < bd)
                bd = d, bt = t, br = r, bn = q;
        }
    }
    fprintf(stderr, "[TRPROBE] lane player %.1f %.1f %.1f: road %u node %u (%.1f m from the node middle, across %.2f)\n",
            (double)pp[0], (double)pp[1], (double)pp[2], (unsigned)br, (unsigned)bn, (double)bd, (double)bt);
    s_pkp_lines++;
    for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {     /* the lane offset of the 4 nearest cars' cursors */
        float p[3], d;
        if (!alive(i) || !rdvec(rec_of(i) + BO3_TR_REC_POS, p))
            continue;
        d = (p[0] - pp[0]) * (p[0] - pp[0]) + (p[1] - pp[1]) * (p[1] - pp[1]) + (p[2] - pp[2]) * (p[2] - pp[2]);
        for (int k = 0; k < 4; k++)
            if (d < d2[k]) {
                for (int q = 3; q > k; q--)
                    d2[q] = d2[q - 1], best[q] = best[q - 1];
                d2[k] = d, best[k] = i;
                break;
            }
    }
    for (int k = 0; k < 4 && best[k] != 0xFFFFFFFFu; k++) {
        uint32_t c = 0, j, h = 0, node;
        float m[3] = { 0, 0, 0 }, l[3] = { 0, 0, 0 }, rr[3] = { 0, 0, 0 }, d = -1.0f, t = -1.0f, prog = 0.0f;
        uint8_t road;
        if (!rd32(rec_of(best[k]) + PK_R_CUR, &c) || c < PK_CURS || (c - PK_CURS) % PK_CUR_SZ)
            continue;
        j = (c - PK_CURS) / PK_CUR_SZ;
        road = u8_at(c + PK_C_ROAD);
        rd(c + PK_C_PROG, &prog, 4);
        node = isfinite(prog) && prog >= 0.0f && prog < (float)PK_NODES_MAX ? (uint32_t)prog : 0u;
        rdvec(PK_M + PK_CUR_SZ * j + 0x30u, m);
        if (road < PK_ROAD_N && rd32(PK_ROADS + PK_ROAD_SZ * road, &h) && h && pk_vert(h, node, l, rr))
            t = pk_lat(m, l, rr, &d);
        fprintf(stderr, "[TRPROBE] lane rec %u j %u road %u node %u C+08 %.2f C+0C %.2f C+4B %02x | M %.1f %.1f %.1f | L %.1f %.1f %.1f"
                " R %.1f %.1f %.1f | across %.2f, %.1f m from the middle\n", (unsigned)best[k], (unsigned)j, (unsigned)road,
                (unsigned)node, (double)tp_f(c + 0x08u), (double)tp_f(c + 0x0Cu), (unsigned)u8_at(c + PK_C_FLAGS), (double)m[0],
                (double)m[1], (double)m[2], (double)l[0], (double)l[1], (double)l[2], (double)rr[0], (double)rr[1], (double)rr[2],
                (double)t, (double)d);
        s_pkp_lines++;
    }
}
static void pk_probe_parked(uint32_t step)
{
    for (uint32_t k = 0; k < BM_TRAFFIC_PARK_MAX; k++) {
        const pk_slot *s = &s_pk[k];
        uint32_t r = rec_of(s->i), c = s->cur, ahead_of = 0, queued = 0, behind = 0, lk = 0, cc = 0;
        float p[3] = { 0, 0, 0 }, q[3], dd, minsp = -1.0f;
        if (s->st != PK_PARKED && s->st != PK_RELEASING)
            continue;
        rdvec(r + BO3_TR_REC_POS, p);
        for (int a = 0; a < 3; a++)
            q[a] = p[a] - bits_f(s->pose[12 + a]);
        dd = sqrtf(dot3(q, q));
        rd32(r + PK_R_LINK, &lk);
        rd32(r + PK_R_CUR, &cc);
        for (uint32_t i = 0; i < BO3_TR_MAX_VEH; i++) {
            uint32_t oc = 0;
            float op = 0.0f, os = 0.0f;
            if (i == s->i || !alive(i) || !rd32(rec_of(i) + PK_R_CUR, &oc) || !oc || oc < PK_CURS || (oc - PK_CURS) % PK_CUR_SZ)
                continue;
            ahead_of += u8_at(oc + PK_C_AHEAD) == s->j;
            if (u8_at(oc + PK_C_ROAD) != s->road || !rd(oc + PK_C_PROG, &op, 4) || !rd(oc + PK_C_SPEED, &os, 4))
                continue;
            if (op < s->prog && op >= s->prog - 15.0f) {
                behind++;
                queued += os < 1.0f;
                if (minsp < 0.0f || os < minsp)
                    minsp = os;
            }
        }
        fprintf(stderr, "[TRPROBE] parked %u rec %u j %u %s step %u: pin %.2f %.2f %.2f drawn %.2f %.2f %.2f (off %.3f m; the game's pass "
                "had moved it %.2f m) | C+2C %.2f C+30 %.2f (held %.2f) C+44 %u C+45 %u C+46 %u C+48 %u C+4B %02x front %u | R+10C %08x "
                "R+114 %08x%s R+174 %02x R+17A %02x | named ahead by %u, behind within 15 nodes %u (queued %u, slowest %.1f m/s)\n",
                (unsigned)k, (unsigned)s->i, (unsigned)s->j, s->st == PK_PARKED ? "PARKED" : "RELEASING", (unsigned)step,
                (double)bits_f(s->pose[12]), (double)bits_f(s->pose[13]), (double)bits_f(s->pose[14]), (double)p[0], (double)p[1],
                (double)p[2], (double)dd, (double)s->game_d, (double)tp_f(c + PK_C_SPEED), (double)tp_f(c + PK_C_PROG),
                (double)s->prog, (unsigned)u8_at(c + PK_C_AHEAD), (unsigned)u8_at(c + PK_C_BEHIND), (unsigned)u8_at(c + PK_C_STATE),
                (unsigned)u8_at(c + PK_C_LCB), (unsigned)u8_at(c + PK_C_FLAGS),
                (unsigned)u8_at(PK_ROADS + PK_ROAD_SZ * s->road + PK_E_FRONT), (unsigned)lk, (unsigned)cc,
                cc == c ? "" : " (NOT the parked cursor)", (unsigned)u8_at(r + 0x174u), (unsigned)u8_at(r + 0x17Au),
                (unsigned)ahead_of, (unsigned)behind, (unsigned)queued, (double)minsp);
        s_pkp_lines++;
    }
}
static void pk_probe(uint32_t step)
{
    float pp[3] = { 0, 0, 0 };
    if (s_pkp_load != s_tp_loads) {                     /* tr_probe counted a new load */
        s_pkp_load = s_tp_loads;
        s_pkp_step0 = s_pkp_last = step;
        s_pkp_done = s_pkp_lines = s_pkp_auto = 0;
    }
    if (rdvec(TR5_CAR1 + 0x40u, pp))
        pk_probe_auto(step, pp);
    if (s_pkp_lines >= 300u)
        return;
    if (!s_pkp_done && step - s_pkp_step0 >= 120u) {
        s_pkp_done = 1;
        pk_probe_roads();
    }
    if (step - s_pkp_last < 120u)
        return;
    s_pkp_last = step;
    if (rdvec(TR5_CAR1 + 0x40u, pp))
        pk_probe_lane(pp);
    pk_probe_parked(step);
}
#endif


/* ---- the service ---- */
static int32_t TD_CALL t_status(td_host *host, bm_traffic_status *out)
{
    bm_traffic_status o;
    uint32_t set = 0;
    uint8_t pool = 0, active = 0;
    if (!host || !out || out->struct_size < 8)
        return BM_TRAFFIC_BAD_ARG;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.density = (float)s_density;
    o.density_applied = s_density_applied;
    o.applications = s_applications;
    o.refusals = s_refusals;
    o.owner = !s_owner ? BM_TRAFFIC_OWNER_NONE : s_owner == host ? BM_TRAFFIC_OWNER_YOU : BM_TRAFFIC_OWNER_OTHER;
#if MUT == 13
    o.experimental = 0;                                 /* defect: the label never shown */
#else
    o.experimental = (s_density > BM_TRAFFIC_DENSITY_LABELLED || s_density_applied > (float)BM_TRAFFIC_DENSITY_LABELLED) ? 1u : 0u;
#endif
    o.wrecks_by_plugins = s_wrecks_by_plugins;          /* v3 */
    o.pool_refusals = s_pool_refusals;
    o.lane_floor = s_floor;                             /* v4 */
    o.lanes_raised = s_lanes_raised;
    o.seed_mode = s_seed_mode;
    o.seed = s_seed;
    o.seeds_applied = s_seeds_applied;
    o.spawn_spread = s_spread;                          /* v5 */
    o.section_min = s_secmin;
    o.sections_raised = s_sections_raised;
    o.cars_spread = s_cars_spread;
    o.fill_empty_lanes = s_fill;                        /* v6 */
    o.lanes_filled = s_lanes_filled;
    o.preload_units = s_pl_units;                       /* v7 */
    o.preload_seconds = s_pl_secs;
    o.preloads = s_preloads;
    o.parked_now = pk_used(PK_PARKED);                  /* v8 */
    o.parks = s_pk_parks;
    o.park_refusals = s_pk_refused;
    o.releases = s_pk_released;
    if (s_verified && rd32(BO3_TR_SYSTEM + BO3_TR_SET, &set) && set && rd(BO3_TR_SYSTEM + BO3_TR_POOL, &pool, 1) &&
        rd(BO3_TR_SYSTEM + BO3_TR_ACTIVE, &active, 1) && pool) {
        uint32_t ntrig = 0, tp = 0, fp = 0, fn = 0, tot = 0;
        uint8_t fl = 0;
        double now = 0;
        o.in_race = 1;
        o.pool = pool;
        o.active = active;
        rd(set + BO3_TR_SET_FLAGS, &fl, 1);
        o.set_flags = fl;
        if (rd32(set + BO3_TR_SET_TRIG, &tp) && rd32(set + BO3_TR_SET_TRIG + 4, &ntrig) && ntrig <= BO3_TR_MAX_TRIG) {
            o.triggers = ntrig;
            for (uint32_t k = 0; k < ntrig; k++) {
                uint32_t n = 0;
                if (rd32(tp + k * BO3_TR_TRIG_SIZE + BO3_TR_TRIG_FLOWN, &n) && n <= BO3_TR_MAX_FLOWS)
                    tot += n;
            }
            o.flow_entries = tot;
            if (ntrig && rd32(tp + BO3_TR_TRIG_FLOWP, &fp) && rd32(tp + BO3_TR_TRIG_FLOWN, &fn) && fn <= BO3_TR_MAX_FLOWS)
                for (uint32_t j = 0; j < fn; j++)
                    for (uint32_t c = 0; c < 6; c++) {
                        uint32_t u = 0;
                        if (rd32(fp + j * BO3_TR_FLOW_REC + 4 + 4 * c, &u))
                            now += bits_f(u);
                    }
        }
        o.flow_start_now = (float)now;
        o.flow_start_game = s_cache_set == set ? s_t0_game : (float)now;
        if (o.struct_size > offsetof(bm_traffic_status, wreck_slots_used) && tr3_census()) {   /* v3 */
            int used = pool_used();
            o.wreck_slots_used = used > 0 ? (uint32_t)used : 0u;
        }
    } else if (!s_verified) {
        memcpy(out, &o, o.struct_size);
        return BM_TRAFFIC_UNAVAILABLE;
    }
    memcpy(out, &o, o.struct_size);
    return o.in_race ? BM_TRAFFIC_OK : BM_TRAFFIC_UNAVAILABLE;
}

/* v1 and v2 share one path; only the bound differs (the version of the function the plugin called) */
static int32_t set_bounded(td_host *host, double density, double max)
{
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
#if MUT != 1
    if (!isfinite(density) || density < 0.0 || density > max)
        return BM_TRAFFIC_OUT_OF_RANGE;
#endif
#if MUT != 4
    if (s_owner && s_owner != host)
        return BM_TRAFFIC_CONFLICT;
#endif
    s_owner = host;
    s_density = density;
    if (density > BM_TRAFFIC_DENSITY_LABELLED && s_log) {
        char line[200];
        snprintf(line, sizeof line, "[TRAFFIC] EXPERIMENTAL: density %.2f requested (above %.1f: the game's pool / spawn / draw "
                 "limits are unchanged and may refuse or not draw vehicles)", density, BM_TRAFFIC_DENSITY_LABELLED);
        s_log(line);
    }
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_set(td_host *host, double density)
{
#if MUT == 11
    return set_bounded(host, density, BM_TRAFFIC_DENSITY_MAX_V2);   /* defect: a v1 caller gets the v2 bound */
#else
    return set_bounded(host, density, BM_TRAFFIC_DENSITY_MAX);
#endif
}

static int32_t TD_CALL t_set_v2(td_host *host, double density)
{
#if MUT == 12
    return set_bounded(host, density, 4.0);                         /* defect: the v2 bound not 3.0 */
#else
    return set_bounded(host, density, BM_TRAFFIC_DENSITY_MAX_V2);
#endif
}

static int32_t TD_CALL t_get(td_host *host, double *density)
{
    if (!host || !density)
        return BM_TRAFFIC_BAD_ARG;
    *density = s_density;
    return BM_TRAFFIC_OK;
}

static int32_t TD_CALL t_reset(td_host *host)
{
    if (!host)
        return BM_TRAFFIC_BAD_ARG;
    pk_release_host(host);                              /* v8: the caller's parked cars released (whatever reset returns) */
    if (s_owner != host)
        return BM_TRAFFIC_CONFLICT;
#if MUT != 5
    s_density = 1.0;                                    /* originals back at the next set-up */
#endif
    s_floor = 0.0f;                                     /* v4: the floor too (one owner of the flows) */
    s_spread = 0;                                       /* v5 */
    s_secmin = 0.0f;
    s_fill = 0;                                         /* v6 */
    s_pl_units = 0;                                     /* v7 */
    s_pl_secs = 0.0f;
    s_owner = NULL;
    return BM_TRAFFIC_OK;
}

static const bm_traffic_api s_api = {(uint32_t)sizeof(bm_traffic_api), BM_TRAFFIC_VERSION, t_status, t_set, t_get, t_reset,
                                     t_set_v2, t_near_vehicles, t_wreck, t_clear_wrecked, t_set_seed, t_set_lane_floor,
                                     t_set_spawn_spread, t_set_section_min, t_set_fill_empty_lanes, t_set_preload,
                                     t_set_parked};

const bm_traffic_api *bo3_bm_traffic_api(void)
{
    return &s_api;
}

#if BO3_HOOKREQ_ZPK && (defined(BO3_TRAFFIC_GAME) || defined(BO3_TR_PK_REGTEST))
#include "recomp_types.h"
extern void sub_001A0600(void);

/* C3-4: the game's lane unlink sub_001A0600 with its callers' shape (mov eax, C; call; it ends in a plain ret: no stack argument,
 * the callee pops nothing but the return address; it pushes / pops ebp, esi, edi itself). Every guest register, both frame words,
 * XMM 0..7 and the fp top are put back. Returns bit 0 = AL == 1 (its own return), bit 1 = esp balanced. Game thread only (the mark
 * at loc_001A264F publishes g_ebp / g_seh_ebp first). Bound in the game build; tests call it over a stand-in sub_001A0600. */
uint32_t bo3_tr_pk_guest_unlink(void *u, uint32_t cursor);
uint32_t bo3_tr_pk_guest_unlink(void *u, uint32_t cursor)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp, seh = g_seh_ebp, al, after;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
    (void)u;
    g_eax = cursor;
    PUSH32(g_esp, 0);                                   /* the return address its ret takes */
    sub_001A0600();
    al = g_eax & 0xFFu;
    after = g_esp;
#if MUT == 74
    (void)a, (void)b, (void)c, (void)d, (void)si, (void)di, (void)bp, (void)seh, (void)x, (void)top;   /* defect: nothing put back */
#else
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp; g_seh_ebp = seh;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
#endif
    return (al == 1u ? 1u : 0u) | (after == sp ? 2u : 0u);
}
#endif

#ifdef BO3_TRAFFIC_GAME
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

static void g_log(const char *line)
{
    fprintf(stderr, "%s\n", line);
}

#if BO3_HOOKREQ_P5B
#include "recomp_types.h"
extern void sub_00111750(void);

/* the game's induced traffic crash as the retail code at 0x19F820..0x19F82E calls it (arguments 1 and the record, EBX = inducer,
 * ESI = 0x64B310, callee pops 8); every guest register put back (bm_rules.c / bm_boost.c's pattern). Game thread only (the mark). */
static uint32_t g_induce(void *u, uint32_t inducer, uint32_t record)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp, r;
    RecompXmm x[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 };
    int top = g_fp_top;
    (void)u;
    PUSH32(g_esp, 1);
    g_ebx = inducer;
    PUSH32(g_esp, record);
    g_esi = TR3_M;
    PUSH32(g_esp, 0);                           /* the return address its ret 8 takes */
    sub_00111750();
    r = g_eax;
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp;
    g_xmm0 = x[0]; g_xmm1 = x[1]; g_xmm2 = x[2]; g_xmm3 = x[3];
    g_xmm4 = x[4]; g_xmm5 = x[5]; g_xmm6 = x[6]; g_xmm7 = x[7];
    g_fp_top = top;
    return r;
}
#endif

void bo3_bm_traffic_init(void)
{
    static const bo3_tr_guest g = {g_read, g_write, NULL};
    uint32_t sixty = 0, k03 = 0;
    int ok;
    bo3_tr_configure(&g, 0);
    bo3_tr_set_log(g_log);
#if BO3_HOOKREQ_P5B
    bo3_tr_set_induce(g_induce, NULL);                  /* P5b: the game's induced crash for wreck() */
#endif
#if BO3_HOOKREQ_P5B && BO3_HOOKREQ_ZPK
    bo3_tr_set_unlink(bo3_tr_pk_guest_unlink, NULL);    /* C3-4: the game's lane unlink for set_parked() */
#endif
    /* build check: the spawn interval's constants where this build's code reads them (sub_001A5DC0: 60.0 @0x3B17E8,
     * 0.3 @0x3B1750) and a zero-initialised traffic object before any race */
    ok = bo3_guest_rd32(0x003B17E8u, &sixty) && sixty == 0x42700000u && bo3_guest_rd32(0x003B1750u, &k03) && k03 == 0x3E99999Au;
    bo3_tr_configure(&g, ok);
    fprintf(stderr, "[TRAFFIC] bmashup.traffic %u: %s; seed / lane floor (v4): %s\n", (unsigned)BM_TRAFFIC_VERSION,
            ok ? "traffic system verified on this game build" : "NOT verified on this game build: the service does nothing",
            !BO3_HOOKREQ_P5A ? "compiled out (BO3_HOOKREQ_P5A=OFF)" : p5a_census() ? "available" : "UNAVAILABLE (reset bytes differ)");
    bo3_plugins_service(BM_TRAFFIC_SERVICE, BM_TRAFFIC_VERSION, &s_api);
}
#endif
