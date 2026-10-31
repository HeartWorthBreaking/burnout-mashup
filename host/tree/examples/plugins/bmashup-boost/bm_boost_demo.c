/*
 * bm_boost_demo.c - Burnout Mashup's private example of a vehicle plugin
 * (docs/bmashup-boost.md): about five seconds into a race, it asks the
 * "bmashup.boost" service once to top up player 1's boost bar, then logs the
 * answer and each change of the service's status, with the bar before and
 * after the game's routine; and once a second of race time, the bar itself
 * (so a top-up and the drain while boosting show as numbers). It reads the
 * race through "takedawn.race" and changes nothing else: the player still
 * decides when to boost.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_boost_demo.c -o bm_boost_demo.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_boost.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#define DEMO_AFTER_S 5.0f                   /* race time before the request (G5 run 1: at 10 s a takedown had filled the bar) */

static const td_host_api *s_api;
static const bm_boost_api *s_bb;
static int s_asked;                         /* the one request was made */
static uint32_t s_state = 0xFFFFFFFFu, s_reason, s_race, s_fills;
static uint32_t s_race_state = 0xFFFFFFFFu; /* takedawn.race's state at the last call */
static float s_next_bar;                    /* the race time of the next bar line */

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static const char *state_name(uint32_t state)
{
    static const char *const names[] = { "IDLE", "PENDING", "DONE", "REFUSED" };
    return state < sizeof names / sizeof names[0] ? names[state] : "?";
}

static const char *reason_name(uint32_t reason)
{
    static const char *const names[] = { "OK", "BAD_ARG", "UNAVAILABLE", "WRONG_THREAD", "UNSUPPORTED",
                                         "DEBUG_AUTOPILOT", "NOT_IN_RACE", "COUNTDOWN", "PAUSED", "RACE_OVER",
                                         "NO_CAR", "ALREADY_PENDING", "LIMIT", "STALE", "NOT_ADDED" };
    return reason < sizeof names / sizeof names[0] ? names[reason] : "?";
}

/* On the game's thread after each of its updates: keep it short. */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    char line[200];
    bm_boost_status st;
    (void)user;
    if (!s_bb || snap->struct_size < sizeof *snap)
        return;
    if (!s_asked && snap->state == TD_RACE_RACING && (snap->valid & TD_RACE_HAVE_CAR)
            && snap->race_time_s >= DEMO_AFTER_S) {
        int32_t rc;
        memset(&st, 0, sizeof st);
        st.struct_size = (uint32_t)sizeof st;
        s_bb->status(s_api->host, &st);
        rc = s_bb->fill(s_api->host);
        s_asked = 1;
        snprintf(line, sizeof line, "fill at race %.1f s (bar %.1f of %.1f): %s", snap->race_time_s, st.meter,
                 st.meter_max, reason_name((uint32_t)rc));
        say(line);
    }
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_bb->status(s_api->host, &st) != BM_BOOST_OK || st.struct_size < sizeof st)
        return;
    if (snap->state != s_race_state) {
        s_race_state = snap->state;
        s_next_bar = 0.0f;
    }
    if (snap->state == TD_RACE_RACING && st.have_meter && snap->race_time_s >= s_next_bar) {
        snprintf(line, sizeof line, "bar at race %.1f s: %.1f of %.1f%s", snap->race_time_s, st.meter, st.meter_max,
                 st.boosting ? ", boosting" : "");
        say(line);
        s_next_bar = snap->race_time_s + 1.0f;
    }
    if (st.state != s_state || st.reason != s_reason || st.race != s_race || st.fills != s_fills) {
        if (st.state == BM_BOOST_STATE_DONE)
            snprintf(line, sizeof line, "status DONE (%s), race %u, top-ups %u: bar %.1f -> %.1f of %.1f",
                     reason_name(st.reason), (unsigned)st.race, (unsigned)st.fills, st.meter_before, st.meter_after,
                     st.meter_max);
        else
            snprintf(line, sizeof line, "status %s (%s), race %u, top-ups %u", state_name(st.state),
                     reason_name(st.reason), (unsigned)st.race, (unsigned)st.fills);
        say(line);
        s_state = st.state;
        s_reason = st.reason;
        s_race = st.race;
        s_fills = st.fills;
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("boost demo: started; one top-up, about 5 s into a race; the bar once a second");
    return TD_OK;
}

/* The services, one call each, right after init. */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_BOOST_SERVICE)) {
        const bm_boost_api *bb = (const bm_boost_api *)table;
        if (version < 1 || bb->struct_size < sizeof *bb)
            return 1;
        s_bb = bb;
        say("boost demo: bmashup.boost found");
        return TD_OK;
    }
    if (!strcmp(name, TD_RACE_SERVICE)) {
        const td_race_api *race = (const td_race_api *)table;
        if (version < 1 || race->struct_size < sizeof *race || race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
            return 1;
        say("boost demo: reading the race (takedawn.race)");
        return TD_OK;
    }
    return 1;                               /* not one this plugin uses */
}
