/*
 * bm_sdk_events_observer.c - bmashup-sdk example (a): a gameplay events OBSERVER on "bmashup.events".
 * Adapted from the runtime-validated G8 demos bm_lifecycle_demo.c (E1, v2), bm_takedown_demo.c (E6, v3) and
 * bm_boost_awards_demo.c (E2, v4); this version discovers the service through bmashup_sdk.h and degrades by version:
 *   version 2+  LOAD_DONE / RACE_EXIT          (required: without them the mod does nothing)
 *   version 3+  TAKEDOWN / WRECK               (off on an older host, said once in the log)
 *   version 4+  BOOST_AWARD                    (off on an older host, said once in the log)
 *   version 5   award_requested / award_modified are read when the event's struct_size covers them
 * At each race exit it logs player 1's tally: takedowns, times taken down, wrecks, boost awards (count, sum, how many a
 * modifier changed). Observe only: every event is a copy, valid during the call; nothing is written.
 *
 * Build: see BUILD.md (cmake), or  clang -shared -I../../include bm_sdk_events_observer.c -o bm_sdk_events_observer.asi
 */
#include "bmashup_sdk.h"

static const td_host_api *s_api;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_EVENTS_SERVICE, 2, BMSDK_EVENTS_TABLE_V2, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported, s_takedowns_on, s_boost_on;

/* this race */
static unsigned s_mine, s_against, s_wrecks, s_awards, s_awards_modified;
static double s_award_sum, s_award_requested_sum;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void reset_race(void)
{
    s_mine = s_against = s_wrecks = s_awards = s_awards_modified = 0;
    s_award_sum = s_award_requested_sum = 0.0;
}

static void TD_CALL on_event(const bm_event *ev, void *user)
{
    char line[300];
    (void)user;
    if (!BMSDK_HAS_FIELD(ev, bm_event, car_phase))
        return;
    switch (ev->event) {
    case BM_EVENT_LOAD_DONE:
        bmsdk_report_once(s_api, s_need, NNEED, &s_reported);   /* the first time the plugin runs after the start */
        if (BMSDK_HAS_FIELD(ev, bm_event, lanes) && (ev->load_kind == BM_LOAD_TRACK || ev->load_kind == BM_LOAD_RESTART)) {
            reset_race();
            snprintf(line, sizeof line, "events observer: race loaded (%s, %u AI lanes)",
                     ev->load_kind == BM_LOAD_TRACK ? "track" : "restart", (unsigned)ev->lanes);
            say(line);
        }
        break;
    case BM_EVENT_TAKEDOWN:
        if (!BMSDK_HAS_FIELD(ev, bm_event, actor_takedowns))
            break;
        if (ev->actor == 0)
            s_mine++;
        else if (ev->victim == 0)
            s_against++;
        break;
    case BM_EVENT_WRECK:
        if (BMSDK_HAS_FIELD(ev, bm_event, victim) && ev->victim == 0)
            s_wrecks++;
        break;
    case BM_EVENT_BOOST_AWARD:
        if (!BMSDK_HAS_FIELD(ev, bm_event, award_amount) || ev->recipient != 0)
            break;
        s_awards++;
        s_award_sum += ev->award_amount;
        if (BMSDK_HAS_FIELD(ev, bm_event, award_modified)) {      /* version 5 */
            s_award_requested_sum += ev->award_requested;
            s_awards_modified += ev->award_modified != 0;
        } else {
            s_award_requested_sum += ev->award_amount;
        }
        break;
    case BM_EVENT_RACE_EXIT:
        snprintf(line, sizeof line, "events observer: race over (%u racers): takedowns %u, taken down %u, wrecks %u%s; "
                 "boost awards %u, %.1f boost (game asked %.1f, %u changed by modifiers)%s",
                 BMSDK_HAS_FIELD(ev, bm_event, racers) ? (unsigned)ev->racers : 0u, s_mine, s_against, s_wrecks,
                 s_takedowns_on ? "" : " (not observed: host too old)", s_awards, s_award_sum, s_award_requested_sum,
                 s_awards_modified, s_boost_on ? "" : " (not observed: host too old)");
        say(line);
        reset_race();
        break;
    default:
        break;
    }
}

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);       /* the last resort: a missing service is said here */
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
    bmsdk_log(api, TD_LOG_INFO, "events observer: bmashup-sdk %s, plugin API %u", BMSDK_VERSION_STRING,
              (unsigned)TD_PLUGIN_API_VERSION);
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    const bm_events_api *ev;
    int32_t rc;
    if (!w)
        return 1;                                   /* not one this plugin uses */
    if (w->state != BMSDK_BOUND) {
        bmsdk_log_need(api, w);                     /* too old: said now */
        s_reported = 1;
        return 1;
    }
    ev = (const bm_events_api *)w->table;
    rc = ev->subscribe(api->host, BM_EVENT_LOAD_DONE, on_event, NULL);
    if (rc == BM_EVENTS_OK)
        rc = ev->subscribe(api->host, BM_EVENT_RACE_EXIT, on_event, NULL);
    if (rc != BM_EVENTS_OK) {
        bmsdk_fail(w, rc);
        bmsdk_log_need(api, w);
        s_reported = 1;
        return 1;
    }
    if (bmsdk_has(w, 3))
        s_takedowns_on = ev->subscribe(api->host, BM_EVENT_TAKEDOWN, on_event, NULL) == BM_EVENTS_OK &&
                         ev->subscribe(api->host, BM_EVENT_WRECK, on_event, NULL) == BM_EVENTS_OK;
    if (bmsdk_has(w, 4))
        s_boost_on = ev->subscribe(api->host, BM_EVENT_BOOST_AWARD, on_event, NULL) == BM_EVENTS_OK;
    bmsdk_log(api, TD_LOG_INFO, "events observer: bmashup.events %u bound; takedowns / wrecks %s, boost awards %s",
              (unsigned)version, s_takedowns_on ? "on" : bmsdk_has(w, 3) ? "REFUSED" : "off (needs version 3)",
              s_boost_on ? "on" : bmsdk_has(w, 4) ? "REFUSED" : "off (needs version 4)");
    return TD_OK;
}
