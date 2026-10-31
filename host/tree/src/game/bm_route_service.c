/*
 * bm_route_service.c - "bmashup.route" (include/bmashup_route.h), version 1, G8-E5: a read-only copy of each racer's route
 * holders, validated, from the fields the R3 ordering probe verified at run time (l5a\probe_r3):
 *   the world 0x60EA00: racer count +0x12B79C, racer list +0x12B7A8 (entries inside the world, 4-aligned; racers from
 *   world + 0x13BDC0 on have no AI driver)
 *   a racer: tracker lane wrapper +0x18C4, its segment +0x18C8 (u16); racing lane wrapper +0x1BD4, its segment +0x1BD8 (u16)
 * A wrapper is turned back into its lane only when it is one the game or the lane extension owns and its +0 holds that lane's
 * own number (the game's lane table 0x60EA2C + 8 i for i below the track's lanes; the extension's installed entries,
 * bm_lanes.c), or the game's "no lane" wrapper 0x60F224. Available only while the lifecycle (bm_lifecycle.c, G8-E1) says a
 * race's track is resident. MUT=n (test builds only) compiles one deliberate defect.
 * Version 2 (G8-E5s): final_race, a copy of every racer's route taken at the race-exit open, before the phase flips.
 */
#include "bm_route_service.h"

#include <stdatomic.h>
#include <string.h>

#include "bm_lanes.h"
#include "bm_lifecycle.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

#define RT_LIST       0x0012B7A8u
#define RT_STAGE_OFF  0x00144384u           /* racer objects lie in the world below this (probe v6) */
#define RT_NO_AI_FROM 0x0013BDC0u
#define RT_TRACKER    0x18C4u
#define RT_TSEG       0x18C8u
#define RT_RACING     0x1BD4u
#define RT_RSEG       0x1BD8u

static bo3_route_guest_fn s_guest;
static void *s_user;

void bo3_route_configure(bo3_route_guest_fn guest, void *user)
{
    s_guest = guest;
    s_user = user;
}

static int rd32(uint32_t va, uint32_t *v)
{
    const uint8_t *p = s_guest ? s_guest(s_user, va, 4) : NULL;
    if (!p || (va & 3u))
        return 0;
    *v = (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
    return 1;
}

static int rd16(uint32_t va, uint32_t *v)
{
    const uint8_t *p = s_guest ? s_guest(s_user, va, 2) : NULL;
    if (!p || (va & 1u))
        return 0;
    *v = (uint32_t)p[0] | (uint32_t)p[1] << 8;
    return 1;
}

static int resident(void)
{
#if MUT == 1
    return g_bo3_lc.last_load == BO3_LC_LD_TRACK || g_bo3_lc.last_load == BO3_LC_LD_RESTART;  /* defect: also after the exit */
#else
    return (g_bo3_lc.last_load == BO3_LC_LD_TRACK || g_bo3_lc.last_load == BO3_LC_LD_RESTART) &&
           g_bo3_lc.phase == BO3_LC_PH_LOADED;
#endif
}

int bo3_route_lane_of(uint32_t wrapper, uint32_t lanes, uint32_t *lane)
{
    uint32_t v;
    if (wrapper == BO3_LANE_NONE_VA) {
        *lane = BO3_LANE_NONE;
        return 1;
    }
    if (wrapper >= BO3_LANE_TABLE_VA && wrapper < BO3_LANE_TABLE_VA + 8u * BO3_LANE_LEGACY_MAX && !((wrapper - BO3_LANE_TABLE_VA) & 7u)) {
        uint32_t i = (wrapper - BO3_LANE_TABLE_VA) / 8u;
#if MUT == 2
        (void)v; (void)lanes;                   /* defect: any table slot is taken for a lane */
        *lane = i;
        return 1;
#else
        if (i < lanes && rd32(wrapper, &v) && v == i) {
            *lane = i;
            return 1;
        }
        return 0;
#endif
    }
    if (g_bo3_lanes.state == BO3_LANES_EXTENDED && wrapper >= g_bo3_lanes.ext_va &&
        wrapper < g_bo3_lanes.ext_va + 8u * g_bo3_lanes.installed && !((wrapper - g_bo3_lanes.ext_va) & 7u)) {
        uint32_t i = BO3_LANE_LEGACY_MAX + (wrapper - g_bo3_lanes.ext_va) / 8u;
        if (i < lanes && rd32(wrapper, &v) && v == i) {
            *lane = i;
            return 1;
        }
    }
    return 0;
}

static uint32_t racer_count(void)
{
    uint32_t n = 0;
    if (!rd32(BO3_LC_WORLD + BO3_LC_LIST_COUNT, &n) || n > BO3_LC_LIST_MAX)
        return 0;
    return n;
}

static int32_t TD_CALL rt_track(td_host *host, bm_route_track *out)
{
    bm_route_track t;
    uint32_t room;
    if (!host || !out || out->struct_size < 8)
        return BM_ROUTE_BAD_ARG;
    if (!resident())
        return BM_ROUTE_UNAVAILABLE;
    memset(&t, 0, sizeof t);
    t.struct_size = (uint32_t)sizeof t;
    t.lanes = g_bo3_lc.lanes;
    t.extension_lanes = t.lanes > BO3_LANE_LEGACY_MAX ? t.lanes - BO3_LANE_LEGACY_MAX : 0;
    t.racers = racer_count();
    t.load_kind = g_bo3_lc.last_load;
    t.track_loads = g_bo3_lc.loads[BO3_LC_LD_TRACK];
    room = out->struct_size < sizeof t ? out->struct_size : (uint32_t)sizeof t;
    memcpy(out, &t, room);
    out->struct_size = room;
    return BM_ROUTE_OK;
}

/* racer `index` of the list as it is now (the caller checked residency and the index) */
static void fill_racer(uint32_t index, bm_route_racer *out)
{
    bm_route_racer r;
    uint32_t rc, w, seg, lane, world = BO3_LC_WORLD, lanes = g_bo3_lc.lanes;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    r.index = index;
    r.tracker_lane = r.racing_lane = BM_ROUTE_NO_LANE;
    r.tracker_segment = r.racing_segment = 0xFFFFu;
#if MUT == 3
    if (rd32(world + RT_LIST + 4u * index, &rc) && rc) {     /* defect: any non-zero entry is taken for a racer */
#else
    if (rd32(world + RT_LIST + 4u * index, &rc) && rc && rc >= world && rc - world < RT_STAGE_OFF && !(rc & 3u)) {
#endif
        if (rd32(rc + RT_TRACKER, &w) && rd16(rc + RT_TSEG, &seg) && bo3_route_lane_of(w, lanes, &lane)) {
            r.flags |= BM_ROUTE_TRACKER_VALID;
            r.tracker_lane = lane;
            r.tracker_segment = seg;
        }
#if MUT == 4
        if (rd32(rc + RT_RACING, &w) && rd16(rc + RT_RSEG, &seg) && bo3_route_lane_of(w, lanes, &lane)) {   /* defect: AI-less racers too */
#else
        if (rc - world < RT_NO_AI_FROM && rd32(rc + RT_RACING, &w) && rd16(rc + RT_RSEG, &seg) && bo3_route_lane_of(w, lanes, &lane)) {
#endif
            r.flags |= BM_ROUTE_RACING_VALID;
            r.racing_lane = lane;
            r.racing_segment = seg;
        }
        if ((r.flags & BM_ROUTE_TRACKER_VALID && r.tracker_lane != BM_ROUTE_NO_LANE && r.tracker_lane >= BO3_LANE_LEGACY_MAX) ||
            (r.flags & BM_ROUTE_RACING_VALID && r.racing_lane != BM_ROUTE_NO_LANE && r.racing_lane >= BO3_LANE_LEGACY_MAX))
            r.flags |= BM_ROUTE_ON_EXTENSION;
    }
    *out = r;
}

static int32_t TD_CALL rt_racer(td_host *host, uint32_t index, bm_route_racer *out)
{
    bm_route_racer r;
    uint32_t room;
    if (!host || !out || out->struct_size < 8)
        return BM_ROUTE_BAD_ARG;
    if (!resident())
        return BM_ROUTE_UNAVAILABLE;
    if (index >= racer_count())
        return BM_ROUTE_NO_RACER;
    fill_racer(index, &r);
    room = out->struct_size < sizeof r ? out->struct_size : (uint32_t)sizeof r;
    memcpy(out, &r, room);
    out->struct_size = room;
    return BM_ROUTE_OK;
}

/* Version 2 (G8-E5s): the race's final route, copied by bo3_route_capture_final at the race-exit open (bm_lifecycle.c calls it
 * while the phase is still LOADED, before RACE_EXIT is delivered). Written only there, on the game's thread; s_fseq is odd while
 * the copy is being written, so a reader on another thread retries and never returns a half-written copy. */
static bm_route_final s_final;
static _Atomic uint32_t s_fseq;

void bo3_route_capture_final(void *user)
{
    bm_route_final f;
    uint32_t n = 0, ok;
    (void)user;
#if MUT == 7
    return;                                     /* defect: nothing is captured */
#endif
    if (!resident())
        return;
    memset(&f, 0, sizeof f);
    f.struct_size = (uint32_t)sizeof f;
    f.race_exit = g_bo3_lc.classes[BO3_LC_CL_RACE_EXIT];
    f.lanes = g_bo3_lc.lanes;
    f.extension_lanes = f.lanes > BO3_LANE_LEGACY_MAX ? f.lanes - BO3_LANE_LEGACY_MAX : 0;
    f.load_kind = g_bo3_lc.last_load;
    f.track_loads = g_bo3_lc.loads[BO3_LC_LD_TRACK];
    ok = rd32(BO3_LC_WORLD + BO3_LC_LIST_COUNT, &n) && n <= BO3_LC_LIST_MAX;
    if (!ok) {
        f.flags |= BM_ROUTE_FINAL_LIST_INVALID;
        n = 0;
    }
    f.racers = n;
    for (uint32_t i = 0; i < n && i < BM_ROUTE_FINAL_RACERS; i++)
        fill_racer(i, &f.racer[i]);
    atomic_fetch_add(&s_fseq, 1);               /* odd: being written */
    s_final = f;
    atomic_fetch_add(&s_fseq, 1);               /* even: complete */
}

static int32_t TD_CALL rt_final_race(td_host *host, bm_route_final *out)
{
    bm_route_final f;
    uint32_t room, a, b;
    if (!host || !out || out->struct_size < 8)
        return BM_ROUTE_BAD_ARG;
    for (int tries = 0; tries < 4; tries++) {
        a = atomic_load(&s_fseq);
        f = s_final;
        b = atomic_load(&s_fseq);
        if (a == b && !(a & 1u)) {
#if MUT == 8
            f.racers = racer_count();           /* defect: a live value in the copy */
#endif
            if (!a || !f.race_exit)
                return BM_ROUTE_UNAVAILABLE;    /* no race exit yet */
            room = out->struct_size < sizeof f ? out->struct_size : (uint32_t)sizeof f;
            memcpy(out, &f, room);
            out->struct_size = room;
            return BM_ROUTE_OK;
        }
    }
    return BM_ROUTE_UNAVAILABLE;
}

static const bm_route_api s_api = {(uint32_t)sizeof(bm_route_api), BM_ROUTE_VERSION, rt_track, rt_racer, rt_final_race};

const bm_route_api *bo3_bm_route_api(void)
{
    return &s_api;
}

void bo3_bm_route_init(void)
{
    bo3_plugins_service(BM_ROUTE_SERVICE, BM_ROUTE_VERSION, &s_api);
}

#ifdef BO3_ROUTE_GAME
#include <stddef.h>
extern ptrdiff_t g_xbox_mem_offset;

static const uint8_t *game_guest(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!g_xbox_mem_offset || va < 0x00010000u || va >= 0x04000000u || size > 0x04000000u - va)
        return NULL;
    return (const uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}

void bo3_route_game_init(void)
{
    bo3_route_configure(game_guest, NULL);
    bo3_lc_set_exit_capture(&g_bo3_lc, bo3_route_capture_final, NULL);   /* G8-E5s: after bo3_lc_game_init (main.c order) */
}
#endif
