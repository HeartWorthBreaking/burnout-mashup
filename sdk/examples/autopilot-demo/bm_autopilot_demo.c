/*
 * bm_autopilot_demo.c - Burnout Mashup's private example of a gameplay
 * plugin (docs/bmashup-autopilot.md): about five seconds into a race, it asks
 * the "bmashup.autopilot" service to let the game's own AI drive player 1's
 * car, then logs the answer and each change of the service's status. It
 * reads the race through "takedawn.race" and changes nothing else.
 *
 * Modes (build-time; the defaults are the "engage every race" mode):
 *   BM_AP_DEMO_EVERY_RACE 1   one takeover in every race of the process
 *                             (service version 2: engage2, policy
 *                             ONCE_PER_RACE, bound to status.race; version 1:
 *                             engage). A refusal the race can outgrow (the
 *                             countdown, a pause, the title's own AI still
 *                             holding the car, a dropped request) is asked
 *                             again a second later, at most DEMO_TRIES times
 *                             a race.
 *                       0     the G4 demo: one request in the whole process.
 *   BM_AP_DEMO_RELEASE_S N    (version 2) hand the car back N race seconds
 *                             after the takeover, in the demo's
 *                             BM_AP_DEMO_RELEASE_FROM-th engaged race and
 *                             later; 0 (default): never.
 *   BM_AP_DEMO_PROBE 1        (version 2) negative controls, each logged with
 *                             its answer: one engage2 and one release in the
 *                             front end, one engage2 in each countdown.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_autopilot_demo.c -o bm_autopilot_demo.asi
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_autopilot.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef BM_AP_DEMO_EVERY_RACE
#define BM_AP_DEMO_EVERY_RACE 1
#endif
#ifndef BM_AP_DEMO_RELEASE_S
#define BM_AP_DEMO_RELEASE_S 0
#endif
#ifndef BM_AP_DEMO_RELEASE_FROM
#define BM_AP_DEMO_RELEASE_FROM 1
#endif
#ifndef BM_AP_DEMO_PROBE
#define BM_AP_DEMO_PROBE 0
#endif

#define DEMO_AFTER_S 5.0f                   /* race time before the first request of a race */
#define DEMO_RETRY_S 1.0f                   /* race time between requests in one race */
#define DEMO_TRIES   5                      /* requests a race at most */
#define DEMO_FE_UPDATES 60                  /* front-end updates before the front-end probe */

static const td_host_api *s_api;
static const bm_autopilot_api *s_ap;
static int s_v2;                            /* the service has engage2 / release */
static int s_asked;                         /* once-per-process mode: the one request was made */
static uint32_t s_state = 0xFFFFFFFFu, s_reason, s_race, s_rel_reason;
/* this race (status.race) */
static uint32_t s_cur = 0xFFFFFFFFu;
static int s_tries;
static float s_next_s;
static int s_engaged_here, s_rel_asked, s_probed_countdown;
static float s_engaged_at;
static int s_engaged_races;                 /* races the demo saw ENGAGED in */
static int s_fe_updates, s_probed_fe;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static const char *state_name(uint32_t state)
{
    static const char *const names[] = { "IDLE", "PENDING", "ENGAGED", "ENDED", "REFUSED", "RELEASED" };
    return state < sizeof names / sizeof names[0] ? names[state] : "?";
}

static const char *reason_name(uint32_t reason)
{
    static const char *const names[] = { "OK", "BAD_ARG", "UNAVAILABLE", "WRONG_THREAD", "UNSUPPORTED",
                                         "DEBUG_AUTOPILOT", "NOT_IN_RACE", "COUNTDOWN", "PAUSED", "RACE_OVER",
                                         "NO_CAR", "AI_OWNED", "ALREADY_PENDING", "ALREADY_USED", "STALE",
                                         "WRONG_RACE", "NOT_ENGAGED" };
    return reason < sizeof names / sizeof names[0] ? names[reason] : "?";
}

/* a refusal the same race can outgrow: worth asking again a second later */
static int transient(int32_t rc)
{
    return rc == BM_AP_COUNTDOWN || rc == BM_AP_PAUSED || rc == BM_AP_AI_OWNED || rc == BM_AP_STALE;
}

static int32_t ask(uint32_t race)
{
    if (s_v2) {
        bm_autopilot_request req;
        memset(&req, 0, sizeof req);
        req.struct_size = (uint32_t)sizeof req;
        req.policy = BM_AP_POLICY_ONCE_PER_RACE;
        req.race = race;
        return s_ap->engage2(s_api->host, &req);
    }
    return s_ap->engage(s_api->host);
}

/* On the game's thread after each of its updates: keep it short. */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    char line[192];
    bm_autopilot_status st;
    (void)user;
    if (!s_ap || snap->struct_size < sizeof *snap)
        return;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_ap->status(s_api->host, &st) != BM_AP_OK)
        return;
    if (st.race != s_cur) {                 /* a new race: its own requests */
        s_cur = st.race;
        s_tries = 0;
        s_next_s = DEMO_AFTER_S;
        s_engaged_here = s_rel_asked = s_probed_countdown = 0;
    }
#if BM_AP_DEMO_PROBE
    if (s_v2 && snap->state == TD_RACE_FRONTEND && !s_probed_fe && ++s_fe_updates >= DEMO_FE_UPDATES) {
        int32_t a = ask(0), b = s_ap->release(s_api->host);
        s_probed_fe = 1;
        snprintf(line, sizeof line, "probe in the front end: engage2 %s, release %s (both must be refused)",
                 reason_name((uint32_t)a), reason_name((uint32_t)b));
        say(line);
    }
    if (s_v2 && snap->state == TD_RACE_PRESTART && !s_probed_countdown) {
        int32_t a = ask(st.race);
        s_probed_countdown = 1;
        snprintf(line, sizeof line, "probe in the countdown (race %u): engage2 %s (must be refused)", (unsigned)st.race,
                 reason_name((uint32_t)a));
        say(line);
    }
#else
    (void)s_fe_updates;
    (void)s_probed_fe;
#endif
    if (snap->state == TD_RACE_RACING && (snap->valid & TD_RACE_HAVE_CAR) && snap->race_time_s >= s_next_s
            && (BM_AP_DEMO_EVERY_RACE ? s_tries < DEMO_TRIES && !s_engaged_here
                                        && (st.state == BM_AP_STATE_IDLE || st.state == BM_AP_STATE_REFUSED)
                                      : !s_asked)) {
        int32_t rc = ask(st.race);
        int n = ++s_tries;
        s_asked = 1;
        s_next_s = snap->race_time_s + DEMO_RETRY_S;
        if (!transient(rc))
            s_tries = DEMO_TRIES;           /* nothing more to ask in this race */
        snprintf(line, sizeof line, "engage at race %.1f s (race %u, request %d): %s", snap->race_time_s,
                 (unsigned)st.race, n, reason_name((uint32_t)rc));
        say(line);
        memset(&st, 0, sizeof st);
        st.struct_size = (uint32_t)sizeof st;
        if (s_ap->status(s_api->host, &st) != BM_AP_OK)
            return;
    }
    if (st.state == BM_AP_STATE_ENGAGED && !s_engaged_here) {
        s_engaged_here = 1;
        s_engaged_at = snap->race_time_s;
        s_engaged_races++;
        snprintf(line, sizeof line, "engaged in race %u at %.1f s (engaged race %d of this process)", (unsigned)st.race,
                 s_engaged_at, s_engaged_races);
        say(line);
    }
#if BM_AP_DEMO_RELEASE_S > 0
    if (s_v2 && st.state == BM_AP_STATE_ENGAGED && !s_rel_asked && s_engaged_races >= BM_AP_DEMO_RELEASE_FROM
            && snap->state == TD_RACE_RACING && snap->race_time_s >= s_engaged_at + (float)BM_AP_DEMO_RELEASE_S) {
        int32_t rc = s_ap->release(s_api->host);
        s_rel_asked = 1;
        snprintf(line, sizeof line, "release at race %.1f s (race %u): %s", snap->race_time_s, (unsigned)st.race,
                 reason_name((uint32_t)rc));
        say(line);
    }
#endif
    if (st.state != s_state || st.reason != s_reason || st.race != s_race
            || (st.struct_size >= 24 && st.release_reason != s_rel_reason)) {
        if (st.struct_size >= 24)
            snprintf(line, sizeof line, "status %s (%s), race %u, release %s, engaged races %u", state_name(st.state),
                     reason_name(st.reason), (unsigned)st.race, reason_name(st.release_reason),
                     (unsigned)st.engaged_races);
        else
            snprintf(line, sizeof line, "status %s (%s), race %u", state_name(st.state), reason_name(st.reason),
                     (unsigned)st.race);
        say(line);
        s_state = st.state;
        s_reason = st.reason;
        s_race = st.race;
        s_rel_reason = st.struct_size >= 24 ? st.release_reason : 0;
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
    say(BM_AP_DEMO_EVERY_RACE ? "autopilot demo: started; asks in every race, about 5 s in"
                              : "autopilot demo: started; asks once, about 5 s into a race");
    return TD_OK;
}

/* The services, one call each, right after init. */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    char line[128];
    (void)api;
    if (!strcmp(name, BM_AUTOPILOT_SERVICE)) {
        const bm_autopilot_api *ap = (const bm_autopilot_api *)table;
        /* version 1's part of the table is all this demo needs; version 2's
         * functions only when the table has them */
        if (version < 1 || ap->struct_size < offsetof(bm_autopilot_api, engage2))
            return 1;
        s_ap = ap;
        s_v2 = version >= 2 && ap->struct_size >= sizeof *ap && ap->engage2 && ap->release;
        snprintf(line, sizeof line, "autopilot demo: bmashup.autopilot %u found (%s)", (unsigned)version,
                 s_v2 ? "engage2 / release" : "engage only");
        say(line);
        return TD_OK;
    }
    if (!strcmp(name, TD_RACE_SERVICE)) {
        const td_race_api *race = (const td_race_api *)table;
        if (version < 1 || race->struct_size < sizeof *race || race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
            return 1;
        say("autopilot demo: reading the race (takedawn.race)");
        return TD_OK;
    }
    return 1;                               /* not one this plugin uses */
}
