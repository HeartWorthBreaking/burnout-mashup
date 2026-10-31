/*
 * bm_engine_service.c - "bmashup.engine" (include/bmashup_engine.h), version 1:
 * the AI route-lane capacity of the lane extension (bm_lanes.c, G8-L5a).
 *
 * Plugins request a TOTAL lane capacity while they start; the capacity is the
 * largest accepted request or the default (65 total = 1 extension entry, the
 * G8-L4 behaviour). bo3_bm_engine_close, right after bo3_plugins_init and so
 * before the guest runs, fixes it and gives the lane extension its entry
 * count (total - 64). The extension's memory is still taken only when a track
 * with more than 64 lanes loads (bm_lanes.c). Requests are refused, and
 * nothing is recorded, when out of range, late, or on a game build the lane
 * extension is not verified for (its own build check, the four .rdata words,
 * which are in guest memory before plugins load).
 *
 * Requests come on the main thread only (the plugins' start); lanes_info reads
 * plain 32-bit fields and may be called from any thread.
 */
#include "bm_engine_service.h"

#include <stdio.h>
#include <string.h>

#include "bm_lanes.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

/* main18: one request slot per requester; every mod's [bmashup.capacity] (bm_capdecl.c) is a requester, so the slots follow
 * BO3_MODFS_MAX_MODS (a slot is 16 bytes of host memory; the requests are a maximum, not a sum). */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BX_SLOTS 64
#else
#define BX_SLOTS 256
#endif

static struct { td_host *host; uint32_t max; } s_req[BX_SLOTS];
static int s_nreq;
static int s_open = 1;
static uint32_t s_merged = BM_ENGINE_LANES_DEFAULT;
static int s_owner = -1;                    /* the slot whose request is the merged value; -1: the default */
static uint32_t s_frozen;                   /* 0 while open */
static int s_supported = -1;                /* the build check's answer, once asked */

_Static_assert(BM_ENGINE_LANES_MAX == BO3_LANE_TOTAL_MAX, "the service's ceiling is the extension's");
_Static_assert(BM_ENGINE_LANES_GAME == BO3_LANE_LEGACY_MAX, "the game's own lanes");
_Static_assert(BM_ENGINE_LANES_DEFAULT == BO3_LANE_LEGACY_MAX + BO3_LANE_EXT_COUNT, "the default is G8-L4's");
_Static_assert(sizeof(bm_engine_lanes) == 48, "bm_engine_lanes layout");

static int supported(void)
{
    if (s_supported < 0)
        s_supported = g_bo3_lanes.configured && g_bo3_lanes.build_check(g_bo3_lanes.user) ? 1 : 0;
    return s_supported;
}

static int slot_of(td_host *host)
{
    for (int k = 0; k < s_nreq; k++)
        if (s_req[k].host == host)
            return k;
    if (s_nreq == BX_SLOTS)
        return -1;
    s_req[s_nreq].host = host;
    s_req[s_nreq].max = 0;
    return s_nreq++;
}

static int32_t TD_CALL bx_request_lanes(td_host *host, uint32_t total, uint32_t *merged_total)
{
    int k;

    if (merged_total)
        *merged_total = s_merged;
    if (!host)
        return BM_ENGINE_BAD_ARG;
#if MUT == 13
    if (total > BM_ENGINE_LANES_MAX)
        total = BM_ENGINE_LANES_MAX;            /* defect: clamped instead of refused */
#endif
    if (total == 0 || total > BM_ENGINE_LANES_MAX) {
        fprintf(stderr, "[ENGINE] bmashup.engine: lane request %u refused: out of range (1..%u total)\n",
                (unsigned)total, (unsigned)BM_ENGINE_LANES_MAX);
        return BM_ENGINE_OUT_OF_RANGE;
    }
#if MUT != 12
    if (!s_open) {
        fprintf(stderr, "[ENGINE] bmashup.engine: lane request %u refused: the plugins have started, the capacity "
                "is fixed at %u total\n", (unsigned)total, (unsigned)s_frozen);
        return BM_ENGINE_CLOSED;
    }
#endif
    if (!supported()) {
        fprintf(stderr, "[ENGINE] bmashup.engine: lane request %u refused: this game build is not one the lane "
                "extension is verified for (64 lanes)\n", (unsigned)total);
        return BM_ENGINE_UNSUPPORTED;
    }
    k = slot_of(host);
    if (k >= 0 && total > s_req[k].max)
        s_req[k].max = total;
#if MUT == 11
    s_merged = total > BM_ENGINE_LANES_DEFAULT ? total : BM_ENGINE_LANES_DEFAULT;   /* defect: the last one wins */
    s_owner = k;
#else
    if (total > s_merged) {
        s_merged = total;
        s_owner = k;
    }
#endif
    if (merged_total)
        *merged_total = s_merged;
    return BM_ENGINE_OK;
}

static int32_t TD_CALL bx_lanes_info(td_host *host, bm_engine_lanes *out)
{
    bm_engine_lanes s;
    uint32_t room;
    int k;

    if (!host || !out || out->struct_size < 8)
        return BM_ENGINE_BAD_ARG;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.open = (uint32_t)s_open;
    s.requested_total = s_merged;
    s.frozen_total = s_frozen;
    s.entries = bo3_lanes_entries(&g_bo3_lanes);
    if (!supported() || (g_bo3_lanes.alloc_tried && g_bo3_lanes.alloc_result == BO3_LANES_UNSUPPORTED))
        s.state = BM_ENGINE_LANES_UNSUPPORTED;
    else if (g_bo3_lanes.state == BO3_LANES_EXTENDED)
        s.state = BM_ENGINE_LANES_ALLOCATED;
    else if (g_bo3_lanes.alloc_tried)
        s.state = BM_ENGINE_LANES_FAILED;
    else
        s.state = BM_ENGINE_LANES_PLANNED;
    s.effective_total = s.state == BM_ENGINE_LANES_ALLOCATED || s.state == BM_ENGINE_LANES_PLANNED
                        ? BO3_LANE_LEGACY_MAX + s.entries : BO3_LANE_LEGACY_MAX;
    s.track_loads = g_bo3_lanes.loads;
    s.last_track_lanes = g_bo3_lanes.last_count;
    s.installed = g_bo3_lanes.installed;
    s.refused = g_bo3_lanes.load_refused;
    for (k = 0; k < s_nreq; k++)
        if (s_req[k].host == host)
            s.your_request = s_req[k].max;
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_ENGINE_OK;
}

static const bm_engine_api s_api = {
    (uint32_t)sizeof(bm_engine_api), BM_ENGINE_VERSION, bx_request_lanes, bx_lanes_info
};

const bm_engine_api *bo3_bm_engine_api(void)
{
    return &s_api;
}

void bo3_bm_engine_init(void)
{
    bo3_plugins_service(BM_ENGINE_SERVICE, BM_ENGINE_VERSION, &s_api);
}

void bo3_bm_engine_close(void)
{
    uint32_t entries;
    int rc;

    if (!s_open)
        return;
    s_open = 0;
    s_frozen = s_merged;
    entries = s_frozen - BO3_LANE_LEGACY_MAX;
#if MUT == 14
    rc = BO3_LANES_OK;                          /* defect: the capacity is not handed to the lane extension */
#else
    rc = bo3_lanes_set_entries(&g_bo3_lanes, entries);
#endif
    if (s_owner < 0)
        fprintf(stderr, "[ENGINE] lane capacity frozen: %u total (%u extension entr%s), the default; %d plugin%s "
                "asked\n", (unsigned)s_frozen, (unsigned)entries, entries == 1 ? "y" : "ies", s_nreq,
                s_nreq == 1 ? "" : "s");
    else
        fprintf(stderr, "[ENGINE] lane capacity frozen: %u total (%u extension entr%s), requested by plugin %d of "
                "%d that asked\n", (unsigned)s_frozen, (unsigned)entries, entries == 1 ? "y" : "ies", s_owner + 1,
                s_nreq);
    if (rc != BO3_LANES_OK)
        fprintf(stderr, "[ENGINE] ERROR: the lane extension did not take the capacity (%d)\n", rc);
}
