/*
 * bm_streaming_service.c - "bmashup.streaming" (include/bmashup_streaming.h),
 * version 2: the low-detail unit slot size of the slot extension (bm_unitslots.c,
 * G8-L7, version 1) and the STATIC track pool size (bm_static.c, G8-L9, version 2;
 * the same request / freeze rules, its own merged value).
 *
 * Plugins request a slot size while they start; the size is the largest
 * accepted request or the game's 0x18000. bo3_bm_streaming_close, right after
 * bo3_plugins_init and so before the guest runs, fixes it and hands it to the
 * slot extension (bo3_us_set_low_bytes). The memory is taken when the game's
 * memory manager is set up (bo3_us_apply, after sub_00022F60). Requests are
 * refused, and nothing is recorded, when out of range, late, or on a game build
 * the extension is not verified for.
 *
 * Requests come on the main thread only (the plugins' start); lowslot_info
 * reads plain 32-bit fields and may be called from any thread.
 */
#include "bm_streaming_service.h"

#include <stdio.h>
#include <string.h>

#include "bm_static.h"
#include "bm_unitslots.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

/* main18: one request slot per requester; every mod's [bmashup.capacity] (bm_capdecl.c) is a requester, so the slots follow
 * BO3_MODFS_MAX_MODS (a slot is 16 bytes of host memory; the requests are a maximum, not a sum). */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BS_SLOTS 64
#else
#define BS_SLOTS 256
#endif

static struct { td_host *host; uint32_t max; } s_req[BS_SLOTS];
static int s_nreq;
static int s_open = 1;
static uint32_t s_merged = BM_STREAMING_LOW_GAME;
static int s_owner = -1;                    /* the slot whose request is the merged value; -1: the game's */
static uint32_t s_frozen;                   /* 0 while open */
static int s_supported = -1;
/* version 2: the STATIC pool (bm_static.c, G8-L9) */
static struct { td_host *host; uint32_t max; } s_sreq[BS_SLOTS];
static int s_nsreq;
static uint32_t s_smerged;                  /* 0: nobody asked */
static int s_sowner = -1;
static uint32_t s_sfrozen;
static int s_ssupported = -1;

_Static_assert(BM_STREAMING_STATIC_ONE_VIEW_GAME == BO3_ST_L1_GAME && BM_STREAMING_STATIC_SPLIT_GAME == BO3_ST_L2_GAME,
               "the game's STATIC pools");
_Static_assert(BM_STREAMING_STATIC_MAX == BO3_ST_MAX, "the service's STATIC ceiling is the extension's");
_Static_assert(sizeof(bm_streaming_static) == 48, "bm_streaming_static layout");

_Static_assert(BM_STREAMING_LOW_GAME == BO3_US_LOW_RETAIL, "the game's size");
_Static_assert(BM_STREAMING_LOW_MAX == BO3_US_LOW_MAX, "the service's ceiling is the extension's");
_Static_assert(BM_STREAMING_PAGE == BO3_US_PAGE, "page");
_Static_assert(sizeof(bm_streaming_lowslot) == 48, "bm_streaming_lowslot layout");

static int supported(void)
{
    if (s_supported < 0)
        s_supported = g_bo3_us.configured && g_bo3_us.build_check(g_bo3_us.user) ? 1 : 0;
    return s_supported;
}

static int slot_of(td_host *host)
{
    for (int k = 0; k < s_nreq; k++)
        if (s_req[k].host == host)
            return k;
    if (s_nreq == BS_SLOTS)
        return -1;
    s_req[s_nreq].host = host;
    s_req[s_nreq].max = 0;
    return s_nreq++;
}

static int32_t TD_CALL bs_request_low(td_host *host, uint32_t bytes, uint32_t *merged_bytes)
{
    int k;

    if (merged_bytes)
        *merged_bytes = s_merged;
    if (!host)
        return BM_STREAMING_BAD_ARG;
#if MUT == 13
    bytes = (bytes + BM_STREAMING_PAGE - 1) & ~(BM_STREAMING_PAGE - 1);   /* defect: rounded instead of refused */
#endif
    if (bytes < BM_STREAMING_LOW_GAME || bytes > BM_STREAMING_LOW_MAX || (bytes % BM_STREAMING_PAGE)) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: low-detail slot request 0x%X refused: out of range (0x%X..0x%X, "
                "whole 4 KiB pages)\n", (unsigned)bytes, (unsigned)BM_STREAMING_LOW_GAME, (unsigned)BM_STREAMING_LOW_MAX);
        return BM_STREAMING_OUT_OF_RANGE;
    }
#if MUT != 12
    if (!s_open) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: low-detail slot request 0x%X refused: the plugins have started, the "
                "size is fixed at 0x%X\n", (unsigned)bytes, (unsigned)s_frozen);
        return BM_STREAMING_CLOSED;
    }
#endif
    if (!supported()) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: low-detail slot request 0x%X refused: this game build is not one the "
                "slot extension is verified for\n", (unsigned)bytes);
        return BM_STREAMING_UNSUPPORTED;
    }
    k = slot_of(host);
    if (k >= 0 && bytes > s_req[k].max)
        s_req[k].max = bytes;
#if MUT == 11
    s_merged = bytes;                       /* defect: the last one wins */
    s_owner = k;
#else
    if (bytes > s_merged) {
        s_merged = bytes;
        s_owner = k;
    }
#endif
    if (merged_bytes)
        *merged_bytes = s_merged;
    return BM_STREAMING_OK;
}

static int32_t TD_CALL bs_lowslot_info(td_host *host, bm_streaming_lowslot *out)
{
    bm_streaming_lowslot s;
    uint32_t room;
    int k;

    if (!host || !out || out->struct_size < 8)
        return BM_STREAMING_BAD_ARG;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.open = (uint32_t)s_open;
    s.requested_bytes = s_merged;
    s.frozen_bytes = s_frozen;
    s.state = g_bo3_us.state == BO3_US_ST_EXPANDED ? BM_STREAMING_EXPANDED :
              g_bo3_us.state == BO3_US_ST_FAILED ? BM_STREAMING_FAILED :
              g_bo3_us.state == BO3_US_ST_RETAIL ? BM_STREAMING_GAME : BM_STREAMING_PLANNED;
    s.effective_bytes = s.state == BM_STREAMING_EXPANDED ? g_bo3_us.low_bytes : BM_STREAMING_LOW_GAME;
    s.low_checks = g_bo3_us.checks[BO3_US_LOW];
    s.low_largest = g_bo3_us.max_size[BO3_US_LOW];
    s.full_checks = g_bo3_us.checks[BO3_US_FULL];
    s.full_largest = g_bo3_us.max_size[BO3_US_FULL];
    s.unchecked = g_bo3_us.unknown[BO3_US_LOW] + g_bo3_us.unknown[BO3_US_FULL];
    for (k = 0; k < s_nreq; k++)
        if (s_req[k].host == host)
            s.your_request = s_req[k].max;
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_STREAMING_OK;
}

static int static_supported(void)
{
    if (s_ssupported < 0)
        s_ssupported = g_bo3_st.configured && g_bo3_st.build_check(g_bo3_st.user) ? 1 : 0;
    return s_ssupported;
}

static int32_t TD_CALL bs_request_static(td_host *host, uint32_t bytes, uint32_t *merged_bytes)
{
    int k;

    if (merged_bytes)
        *merged_bytes = s_smerged;
    if (!host)
        return BM_STREAMING_BAD_ARG;
#if MUT == 23
    if (bytes > BM_STREAMING_STATIC_MAX)
        bytes = BM_STREAMING_STATIC_MAX;        /* defect: clamped instead of refused */
#endif
    if (bytes <= BM_STREAMING_STATIC_SPLIT_GAME || bytes > BM_STREAMING_STATIC_MAX || (bytes % BM_STREAMING_PAGE)) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: STATIC pool request 0x%X refused: out of range (above 0x%X, at most "
                "0x%X, whole 4 KiB pages)\n", (unsigned)bytes, (unsigned)BM_STREAMING_STATIC_SPLIT_GAME,
                (unsigned)BM_STREAMING_STATIC_MAX);
        return BM_STREAMING_OUT_OF_RANGE;
    }
#if MUT != 22
    if (!s_open) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: STATIC pool request 0x%X refused: the plugins have started, the size "
                "is fixed at 0x%X\n", (unsigned)bytes, (unsigned)s_sfrozen);
        return BM_STREAMING_CLOSED;
    }
#endif
    if (!static_supported()) {
        fprintf(stderr, "[ENGINE] bmashup.streaming: STATIC pool request 0x%X refused: this game build is not one the STATIC "
                "extension is verified for\n", (unsigned)bytes);
        return BM_STREAMING_UNSUPPORTED;
    }
    for (k = 0; k < s_nsreq && s_sreq[k].host != host; k++)
        ;
    if (k == s_nsreq && s_nsreq < BS_SLOTS) {
        s_sreq[k].host = host;
        s_sreq[k].max = 0;
        s_nsreq++;
    }
    if (k < BS_SLOTS && bytes > s_sreq[k].max)
        s_sreq[k].max = bytes;
#if MUT == 21
    s_smerged = bytes;                          /* defect: the last one wins */
    s_sowner = k;
#else
    if (bytes > s_smerged) {
        s_smerged = bytes;
        s_sowner = k;
    }
#endif
    if (merged_bytes)
        *merged_bytes = s_smerged;
    return BM_STREAMING_OK;
}

static int32_t TD_CALL bs_static_info(td_host *host, bm_streaming_static *out)
{
    bm_streaming_static s;
    uint32_t room;

    if (!host || !out || out->struct_size < 8)
        return BM_STREAMING_BAD_ARG;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.open = (uint32_t)s_open;
    s.requested_bytes = s_smerged;
    s.frozen_bytes = s_sfrozen;
    s.state = g_bo3_st.state == BO3_ST_ST_EXPANDED ? BM_STREAMING_STATIC_EXPANDED :
              g_bo3_st.state == BO3_ST_ST_FAILED ? BM_STREAMING_STATIC_FAILED :
              g_bo3_st.state == BO3_ST_ST_GAME ? BM_STREAMING_STATIC_GAME : BM_STREAMING_STATIC_PLANNED;
    s.one_view_bytes = g_bo3_st.l1_bytes ? g_bo3_st.l1_bytes : BM_STREAMING_STATIC_ONE_VIEW_GAME;
    s.split_bytes = g_bo3_st.l2_bytes ? g_bo3_st.l2_bytes : BM_STREAMING_STATIC_SPLIT_GAME;
    s.loads = g_bo3_st.loads;
    s.complete = g_bo3_st.complete;
    s.truncated = g_bo3_st.truncated;
    s.largest = g_bo3_st.largest;
    for (int k = 0; k < s_nsreq; k++)
        if (s_sreq[k].host == host)
            s.your_request = s_sreq[k].max;
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_STREAMING_OK;
}

static const bm_streaming_api s_api = {
    (uint32_t)sizeof(bm_streaming_api), BM_STREAMING_VERSION, bs_request_low, bs_lowslot_info, bs_request_static,
    bs_static_info
};

const bm_streaming_api *bo3_bm_streaming_api(void)
{
    return &s_api;
}

void bo3_bm_streaming_init(void)
{
    bo3_plugins_service(BM_STREAMING_SERVICE, BM_STREAMING_VERSION, &s_api);
}

void bo3_bm_streaming_close(void)
{
    int rc;

    if (!s_open)
        return;
    s_open = 0;
    s_frozen = s_merged;
#if MUT == 14
    rc = BO3_US_OK;                         /* defect: the size is not handed to the slot extension */
#else
    rc = bo3_us_set_low_bytes(&g_bo3_us, s_frozen);
#endif
    if (s_owner < 0)
        fprintf(stderr, "[ENGINE] low-detail unit slot size frozen: 0x%X, the game's; %d plugin%s asked\n",
                (unsigned)s_frozen, s_nreq, s_nreq == 1 ? "" : "s");
    else
        fprintf(stderr, "[ENGINE] low-detail unit slot size frozen: 0x%X, requested by plugin %d of %d that asked\n",
                (unsigned)s_frozen, s_owner + 1, s_nreq);
    if (rc != BO3_US_OK)
        fprintf(stderr, "[ENGINE] ERROR: the slot extension did not take the size (%d)\n", rc);
    /* version 2: the STATIC pool */
    s_sfrozen = s_smerged;
#if MUT == 24
    rc = BO3_ST_OK;                             /* defect: the size is not handed to the STATIC extension */
#else
    rc = bo3_st_set_bytes(&g_bo3_st, s_sfrozen);
#endif
    if (s_sowner < 0)
        fprintf(stderr, "[ENGINE] STATIC pool size frozen: the game's (one view 0x%X, split screen 0x%X); %d plugin%s asked\n",
                (unsigned)BM_STREAMING_STATIC_ONE_VIEW_GAME, (unsigned)BM_STREAMING_STATIC_SPLIT_GAME, s_nsreq,
                s_nsreq == 1 ? "" : "s");
    else
        fprintf(stderr, "[ENGINE] STATIC pool size frozen: 0x%X, requested by plugin %d of %d that asked\n",
                (unsigned)s_sfrozen, s_sowner + 1, s_nsreq);
    if (rc != BO3_ST_OK)
        fprintf(stderr, "[ENGINE] ERROR: the STATIC extension did not take the size (%d)\n", rc);
}
