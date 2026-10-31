/*
 * bm_sdk_boost_modifier.c - bmashup-sdk example (b): a BOOST_AWARD MODIFIER with caps on "bmashup.events" version 5.
 * Adapted from the runtime-validated G8-E2M demo bm_boost_bonus_demo.c (+50 % drift / oncoming boost for player 1); this
 * version adds the plugin's own caps on top of the service's rules, and discovers the service through bmashup_sdk.h.
 *
 * Rule (each value can be changed at build time, -D...):
 *   player 1 (recipient 0) gets BONUS_FACTOR x the amount for the sources BONUS_SOURCE_A / BONUS_SOURCE_B (default drift,
 *   oncoming); every other award, racer and source is left exactly as the game made it. Caps:
 *     - per award:  the extra is at most BONUS_MAX_EXTRA boost units;
 *     - per race:   the extra of all awards together is at most BONUS_RACE_BUDGET; when it is spent, awards are left alone
 *                   until the next race (reset at LOAD_DONE of a track / restart and at RACE_EXIT);
 *     - always:     a non-finite or negative amount is left alone.
 * The service adds its own rules (bmashup_events.h): the result must be finite and 0 .. 16 x what the game asked for, else
 * it is ignored and counted (stats.rejected); modifiers run in subscription order (the plugins' start order), each seeing
 * the previous result; the host's own adds (BM_BOOST_HOST) are never modified; nothing re-enters.
 * At each race exit it logs how many awards it boosted, the extra given, how often a cap acted, and the service's own
 * counts for this plugin (stats.modified / stats.rejected).
 */
#include "bmashup_sdk.h"

#ifndef BONUS_FACTOR
#define BONUS_FACTOR      1.5f
#endif
#ifndef BONUS_MAX_EXTRA
#define BONUS_MAX_EXTRA   5.0f          /* boost units per award */
#endif
#ifndef BONUS_RACE_BUDGET
#define BONUS_RACE_BUDGET 40.0f         /* boost units per race */
#endif
#ifndef BONUS_SOURCE_A
#define BONUS_SOURCE_A    BM_BOOST_DRIFT
#endif
#ifndef BONUS_SOURCE_B
#define BONUS_SOURCE_B    BM_BOOST_ONCOMING
#endif

static const td_host_api *s_api;
static const bm_events_api *s_ev;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_EVENTS_SERVICE, 5, BMSDK_EVENTS_TABLE_V5, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;

/* this race (the modifier runs on the game's thread only) */
static float s_extra;
static unsigned s_boosted, s_capped_award, s_capped_race;

static int finite_f(float f) { return f == f && f - f == 0.0f; }

static void reset_race(void)
{
    s_extra = 0.0f;
    s_boosted = s_capped_award = s_capped_race = 0;
}

static int32_t TD_CALL modifier(const bm_event *ev, float *amount, void *user)
{
    float want, extra;
    (void)user;
    if (!BMSDK_HAS_FIELD(ev, bm_event, award_modified) || ev->recipient != 0 ||
        (ev->award_source != BONUS_SOURCE_A && ev->award_source != BONUS_SOURCE_B))
        return 0;
    if (!finite_f(*amount) || *amount <= 0.0f)
        return 0;
    want = *amount * BONUS_FACTOR;
    extra = want - *amount;
    if (extra > BONUS_MAX_EXTRA) {
        extra = BONUS_MAX_EXTRA;
        s_capped_award++;
    }
    if (s_extra + extra > BONUS_RACE_BUDGET) {
        extra = BONUS_RACE_BUDGET - s_extra;
        s_capped_race++;
    }
    if (!(extra > 0.0f))
        return 0;                                   /* budget spent: the award stays as it is */
    *amount += extra;
    s_extra += extra;
    s_boosted++;
    return 1;
}

static void TD_CALL on_event(const bm_event *ev, void *user)
{
    char line[300];
    bm_events_stats st;
    (void)user;
    if (!BMSDK_HAS_FIELD(ev, bm_event, load_kind))
        return;
    if (ev->event == BM_EVENT_LOAD_DONE) {
        bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
        if (ev->load_kind == BM_LOAD_TRACK || ev->load_kind == BM_LOAD_RESTART)
            reset_race();
        return;
    }
    if (ev->event != BM_EVENT_RACE_EXIT)
        return;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_ev->stats(s_api->host, BM_EVENT_BOOST_AWARD, &st) != BM_EVENTS_OK)
        memset(&st, 0, sizeof st);
    snprintf(line, sizeof line, "boost modifier: race over: %u awards boosted, +%.2f boost of %.2f per race; capped per award "
             "%u, by the race budget %u; service: modified %u, rejected %u", s_boosted, (double)s_extra,
             (double)BONUS_RACE_BUDGET, s_capped_award, s_capped_race,
             BMSDK_HAS_FIELD(&st, bm_events_stats, modified) ? (unsigned)st.modified : 0u,
             BMSDK_HAS_FIELD(&st, bm_events_stats, rejected) ? (unsigned)st.rejected : 0u);
    s_api->log(s_api->host, TD_LOG_INFO, line);
    reset_race();
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

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    int32_t rc;
    if (!w)
        return 1;
    if (w->state != BMSDK_BOUND) {
        bmsdk_log_need(api, w);                     /* e.g. a version-4 host: no modifiers there */
        s_reported = 1;
        return 1;
    }
    s_ev = (const bm_events_api *)w->table;
    rc = s_ev->subscribe_modifier(api->host, BM_EVENT_BOOST_AWARD, modifier, NULL);
    if (rc == BM_EVENTS_OK)
        rc = s_ev->subscribe(api->host, BM_EVENT_LOAD_DONE, on_event, NULL);
    if (rc == BM_EVENTS_OK)
        rc = s_ev->subscribe(api->host, BM_EVENT_RACE_EXIT, on_event, NULL);
    if (rc != BM_EVENTS_OK) {
        bmsdk_fail(w, rc);
        bmsdk_log_need(api, w);
        s_reported = 1;
        return 1;
    }
    bmsdk_log(api, TD_LOG_INFO, "boost modifier: bmashup.events %u bound: player 1, sources %d / %d x %.2f, at most +%.2f "
              "per award and +%.2f per race", (unsigned)version, (int)BONUS_SOURCE_A, (int)BONUS_SOURCE_B,
              (double)BONUS_FACTOR, (double)BONUS_MAX_EXTRA, (double)BONUS_RACE_BUDGET);
    return TD_OK;
}
