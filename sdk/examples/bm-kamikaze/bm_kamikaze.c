/*
 * bm_kamikaze.c - SDK 0.6.0 example: bmashup.traffic version 3 (wreck). CHANGES GAMEPLAY.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_kamikaze.c -o bm_kamikaze.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_traffic.h"

static const td_host_api *s_api;
static const bm_traffic_api *s_tr;
static float s_next;
static int s_said;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_traffic_vehicle v[BM_TRAFFIC_NEAR_MAX];
    uint32_t n = BM_TRAFFIC_NEAR_MAX, best = BM_TRAFFIC_NEAR_MAX;
    int32_t rc;
    char line[160];
    (void)user;
    if (!s_tr || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 2.0f;
    v[0].struct_size = (uint32_t)sizeof v[0];
    rc = s_tr->near_vehicles(s_api->host, 0, v, &n);
    if (rc != BM_TRAFFIC_OK) {
        if (!s_said++) {
            snprintf(line, sizeof line, "near_vehicles rc %d: wreck is not available on this host build", (int)rc);
            say(line);
        }
        return;
    }
    for (uint32_t k = 0; k < n; k++)
        if (!v[k].crashed && !v[k].same_direction && v[k].rel_pos_m[2] > 20.0f && v[k].rel_pos_m[2] < 120.0f &&
            (best == BM_TRAFFIC_NEAR_MAX || v[k].rel_pos_m[2] < v[best].rel_pos_m[2]))
            best = k;
    if (best == BM_TRAFFIC_NEAR_MAX)
        return;
    rc = s_tr->wreck(s_api->host, v[best].handle);
    snprintf(line, sizeof line, "wreck of the vehicle %.0f m ahead: rc %d", v[best].rel_pos_m[2], (int)rc);
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("kamikaze example: the nearest oncoming vehicle ahead crashes every 2 s (bmashup.traffic 3; CHANGES GAMEPLAY)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_TRAFFIC_SERVICE)) {
        const bm_traffic_api *tr = (const bm_traffic_api *)table;
        if (version < 3 || tr->struct_size < sizeof *tr || !tr->wreck)
            return 1;
        s_tr = tr;
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
