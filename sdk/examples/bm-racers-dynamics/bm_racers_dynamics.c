/*
 * bm_racers_dynamics.c - SDK 0.6.0 example: bmashup.racers version 3 reads (gear, speed, derived yaw rate / accelerations, parts, lights). Read only.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_racers_dynamics.c -o bm_racers_dynamics.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_racers.h"

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static float s_next;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    uint32_t n;
    char line[200];
    (void)user;
    if (!s_rc || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 1.0f;
    n = s_rc->count(s_api->host);
    for (uint32_t k = 0; k < n; k++) {
        bm_racer_info r;
        memset(&r, 0, sizeof r);
        r.struct_size = (uint32_t)sizeof r;
        if (s_rc->get(s_api->host, k, &r) != BM_RACERS_OK || r.player != 0 || !r.have_dynamics)
            continue;
        snprintf(line, sizeof line, "gear %d, %.1f km/h, yaw %.2f rad/s, lat %.1f m/s2, long %.1f m/s2, %u parts, lights %x",
                 (int)r.gear, r.speed_mps * 3.6f, r.yaw_rate_rps, r.lat_accel_mps2, r.long_accel_mps2, (unsigned)r.parts,
                 (unsigned)r.lights);
        say(line);
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("racers dynamics example: player 1's dynamics once a second (bmashup.racers 3, read only)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 3 || rc->struct_size < sizeof *rc || !rc->get)
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
