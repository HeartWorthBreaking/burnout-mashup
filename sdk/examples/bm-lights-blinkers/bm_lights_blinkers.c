/*
 * bm_lights_blinkers.c - SDK 0.6.0 example: bmashup.racers version 3 (set_light indicators, lamp_counts).
 * Player 0's left indicator blinks from the GO (the host blinks it, about 1.5 Hz); once a race, every racer's indicator-lamp
 * group counts are logged (0 = that lamp does not show on the car's model).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_lights_blinkers.c -o bm_lights_blinkers.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_racers.h"

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static int s_done;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    char line[160];
    uint32_t n;
    (void)user;
    if (!s_rc || snap->state != TD_RACE_RACING) {
        if (snap->state != TD_RACE_PAUSED)
            s_done = 0;
        return;
    }
    if (s_done)
        return;
    s_done = 1;
    n = s_rc->count(s_api->host);
    for (uint32_t k = 0; k < n; k++) {
        bm_racer_info r;
        uint32_t g5 = 0, g6 = 0;
        int32_t rc = s_rc->lamp_counts(s_api->host, k, &g5, &g6);
        memset(&r, 0, sizeof r);
        r.struct_size = (uint32_t)sizeof r;
        s_rc->get(s_api->host, k, &r);
        snprintf(line, sizeof line, "racer %u%s: indicator lamps left %u / right %u (%s)", (unsigned)k,
                 r.player == 0 ? " (player 0)" : "", (unsigned)g5, (unsigned)g6, s_rc->result_text(rc));
        say(line);
        if (r.player == 0) {
            rc = s_rc->set_light(s_api->host, k, BM_LIGHT_IND_LEFT, BM_LIGHT_ON);   /* blinks until the race ends */
            snprintf(line, sizeof line, "player 0 left indicator: %s%s", s_rc->result_text(rc),
                     g5 ? "" : " (no lamp points on this model: nothing will show)");
            say(line);
        }
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("blinkers example: player 0's left indicator blinks; lamp group counts logged once a race (bmashup.racers 3)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 3 || rc->struct_size < sizeof *rc || !rc->lamp_counts)
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
