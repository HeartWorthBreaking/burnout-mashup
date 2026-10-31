/*
 * bm_sdk_capacity.c - bmashup-sdk example (d), plugin side: engine-capacity REQUESTS on "bmashup.engine" (AI route lanes)
 * and "bmashup.streaming" (low-detail unit slots; version 2: the STATIC track pool), with a report once a race runs
 * ("bmashup.events", optional). Adapted from the G8 demos bm_capacity_demo.c (services_docs), bm_lanes_demo.c (L5a, runtime
 * launch 39: 80 lanes) and bm_static_demo.c (L9). A mod that needs capacity but no code should use the mod.toml
 * declaration instead (examples/capacity/declaration-only): the host requests it for the mod, with the same checks.
 *
 * Requests are taken only while the host starts the plugins; afterwards each capacity is the LARGEST of every accepted
 * request (plugins and mod.toml declarations, in any order) and the game's default, and it is fixed for the process.
 * Build-time values (0 = do not ask): CAP_LANES (total lanes, 1..255; the game has 64), CAP_LOW_BYTES (a 4 KiB multiple
 * 0x18000..0x30000), CAP_STATIC_BYTES (a 4 KiB multiple above 0xA00000, at most 0x20C4000; needs streaming version 2).
 * Every service is optional here: without one the plugin says so and does not assume the limit was raised.
 */
#include "bmashup_sdk.h"

#ifndef CAP_LANES
#define CAP_LANES        80u
#endif
#ifndef CAP_LOW_BYTES
#define CAP_LOW_BYTES    0x1A000u
#endif
#ifndef CAP_STATIC_BYTES
#define CAP_STATIC_BYTES 0xD01000u
#endif

static const td_host_api *s_api;
enum { N_ENGINE = 0, N_STREAMING = 1, N_EVENTS = 2 };
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_ENGINE_SERVICE, 1, BMSDK_ENGINE_TABLE_V1, 0),
    BMSDK_NEED(BM_STREAMING_SERVICE, 1, BMSDK_STREAMING_TABLE_V1, 0),
    BMSDK_NEED(BM_EVENTS_SERVICE, 1, BMSDK_EVENTS_TABLE_V1, 0),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported, s_raced;

static void request(const char *what, int32_t rc, uint32_t asked, uint32_t merged, int ok_code)
{
    bmsdk_log(s_api, rc == ok_code ? TD_LOG_INFO : TD_LOG_WARN, "capacity: asked for %s 0x%X (%u): %s %d; merged so far 0x%X",
              what, (unsigned)asked, (unsigned)asked, rc == ok_code ? "accepted" : "REFUSED", (int)rc, (unsigned)merged);
}

/* Called on the game's thread once per player-car update: keep it short (it reports once). */
static void TD_CALL on_car_update(const bm_event *ev, void *user)
{
    (void)user;
    if (s_raced || !BMSDK_HAS_FIELD(ev, bm_event, car_phase) || ev->car_phase != 2)    /* 2: racing */
        return;
    s_raced = 1;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
    if (s_need[N_ENGINE].state == BMSDK_BOUND) {
        bm_engine_lanes l;
        memset(&l, 0, sizeof l);
        l.struct_size = (uint32_t)sizeof l;
        if (((const bm_engine_api *)s_need[N_ENGINE].table)->lanes_info(s_api->host, &l) == BM_ENGINE_OK)
            bmsdk_log(s_api, TD_LOG_INFO, "capacity: lanes fixed at %u (state %u), this track %u, on the extension %u, "
                      "refused %u", (unsigned)l.frozen_total, (unsigned)l.state, (unsigned)l.last_track_lanes,
                      (unsigned)l.installed, (unsigned)l.refused);
    }
    if (s_need[N_STREAMING].state == BMSDK_BOUND) {
        const bm_streaming_api *st = (const bm_streaming_api *)s_need[N_STREAMING].table;
        bm_streaming_lowslot s;
        memset(&s, 0, sizeof s);
        s.struct_size = (uint32_t)sizeof s;
        if (st->lowslot_info(s_api->host, &s) == BM_STREAMING_OK)
            bmsdk_log(s_api, TD_LOG_INFO, "capacity: low slots fixed at 0x%X (state %u), largest low unit 0x%X in %u reads",
                      (unsigned)s.frozen_bytes, (unsigned)s.state, (unsigned)s.low_largest, (unsigned)s.low_checks);
        if (bmsdk_has(&s_need[N_STREAMING], 2) && BMSDK_HAS_FIELD(st, bm_streaming_api, static_info)) {
            bm_streaming_static p;
            memset(&p, 0, sizeof p);
            p.struct_size = (uint32_t)sizeof p;
            if (st->static_info(s_api->host, &p) == BM_STREAMING_OK)
                bmsdk_log(s_api, TD_LOG_INFO, "capacity: STATIC pool 0x%X (state %u), one view 0x%X, largest static.dat 0x%X",
                          (unsigned)p.frozen_bytes, (unsigned)p.state, (unsigned)p.one_view_bytes, (unsigned)p.largest);
        }
    }
}

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
}

BMSDK_DEFINE_API_VERSION()
/* 0.2.0: platform hosts call this once after the last offer: a missing service is said during the start */
BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    s_api = api;
    if (info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {
        info->on_shutdown = on_shutdown;
        info->user = NULL;
    }
    return TD_OK;
}

/* The services, one call each, right after init: the moment to request (and to subscribe). */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    uint32_t merged = 0;
    int32_t rc;
    if (!w)
        return 1;
    if (w->state != BMSDK_BOUND) {
        bmsdk_log_need(api, w);
        return 1;
    }
    if (w == &s_need[N_ENGINE]) {
        if (CAP_LANES) {
            rc = ((const bm_engine_api *)w->table)->request_lanes(api->host, CAP_LANES, &merged);
            request("total AI lanes", rc, CAP_LANES, merged, BM_ENGINE_OK);
            if (rc != BM_ENGINE_OK)
                bmsdk_fail(w, rc);
        }
        return w->state == BMSDK_BOUND ? TD_OK : 1;
    }
    if (w == &s_need[N_STREAMING]) {
        const bm_streaming_api *st = (const bm_streaming_api *)w->table;
        if (CAP_LOW_BYTES) {
            rc = st->request_low_unit_bytes(api->host, CAP_LOW_BYTES, &merged);
            request("low-detail unit bytes", rc, CAP_LOW_BYTES, merged, BM_STREAMING_OK);
        }
        if (CAP_STATIC_BYTES) {
            if (bmsdk_has(w, 2) && BMSDK_HAS_FIELD(st, bm_streaming_api, request_static_bytes)) {
                rc = st->request_static_bytes(api->host, CAP_STATIC_BYTES, &merged);
                request("STATIC pool bytes", rc, CAP_STATIC_BYTES, merged, BM_STREAMING_OK);
            } else {
                bmsdk_log(api, TD_LOG_WARN, "capacity: STATIC pool not asked: bmashup.streaming %u has no STATIC request "
                          "(needs version 2)", (unsigned)version);
            }
        }
        return TD_OK;
    }
    rc = ((const bm_events_api *)w->table)->subscribe(api->host, BM_EVENT_PLAYER_CAR_UPDATE, on_car_update, NULL);
    if (rc != BM_EVENTS_OK) {
        bmsdk_fail(w, rc);                          /* e.g. BM_EVENTS_UNAVAILABLE: no race report, requests unaffected */
        bmsdk_log_need(api, w);
        return 1;
    }
    return TD_OK;
}
