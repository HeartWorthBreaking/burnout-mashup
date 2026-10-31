/*
 * bm_boost_award.c - SDK 0.5.0 example for bmashup.boost version 2 (award): every takedown player 1 makes is rewarded
 * with an extra quarter of the boost bar, through the game's own add-boost routine (the game's factors and cap still
 * apply). It reads takedowns through bmashup.racers (v1 fields) and checks the award's outcome with award_status.
 * CHANGES GAMEPLAY (more boost). Player 0 only (split screen is not supported by the platform yet).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_boost_award.c -o bm_boost_award.asi
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_boost.h"
#include "bmashup_racers.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_boost_api *s_bb;
static const bm_racers_api *s_rc;
static uint32_t s_takedowns, s_done;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

/* the game's thread, after each update */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_racer_info r;
    bm_boost_award_status st;
    char line[160];
    (void)user;
    if (!s_bb || !s_rc || snap->state != TD_RACE_RACING)
        return;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    for (uint32_t i = 0; i < s_rc->count(s_api->host); i++) {
        r.struct_size = (uint32_t)sizeof r;
        if (s_rc->get(s_api->host, i, &r) != BM_RACERS_OK || !r.is_player1)
            continue;
        if (r.takedowns > s_takedowns && r.boost_max > 0.0f) {
            int32_t rc = s_bb->award(s_api->host, 0, 0.25f * r.boost_max);
            snprintf(line, sizeof line, "takedown %u: award %.1f -> %d", (unsigned)r.takedowns, 0.25 * r.boost_max, (int)rc);
            say(line);
        }
        s_takedowns = r.takedowns;
    }
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_bb->award_status(s_api->host, 0, &st) == BM_BOOST_OK && st.awards != s_done) {
        s_done = st.awards;
        snprintf(line, sizeof line, "award carried out (%u this race): bar %.1f -> %.1f", (unsigned)st.awards, st.meter_before,
                 st.meter_after);
        say(line);
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("boost award example: a quarter bar for each takedown (bmashup.boost 2)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_BOOST_SERVICE)) {
        const bm_boost_api *bb = (const bm_boost_api *)table;
        /* v2 functions exist only when the version is 2+ AND the table is long enough */
        if (version < 2 || bb->struct_size < sizeof *bb || !bb->award) {
            say("boost award example: this host's bmashup.boost has no award (needs version 2)");
            return 1;
        }
        s_bb = bb;
        return TD_OK;
    }
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 1 || rc->struct_size < offsetof(bm_racers_api, order))
            return 1;
        s_rc = rc;
        return TD_OK;
    }
    if (!strcmp(name, TD_RACE_SERVICE)) {
        const td_race_api *race = (const td_race_api *)table;
        if (version < 1 || race->struct_size < sizeof *race || race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
            return 1;
        return TD_OK;
    }
    return 1;
}
