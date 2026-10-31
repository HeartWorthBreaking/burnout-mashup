/*
 * bm_traffic_kamikaze.c - example for bmashup.traffic near_vehicles / wreck (main21, hook request v2 P5b; the modder's mod 05
 * "Kamikaze" in its simplest form): every 2 s of race time the nearest traffic vehicle that drives the same way 5 .. 35 m ahead
 * in the player's lane (|x| < 3 m) wrecks itself (the game's own induced crash, the player counting as the inducer). The host
 * refuses with POOL_FULL / RATE / NOT_LIVE when it must; the example only logs. EXPERIMENTAL (the vehicle records are statically
 * mapped, runtime check pending). CHANGES GAMEPLAY.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_traffic_kamikaze.c -o bm_traffic_kamikaze.asi
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_traffic.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_traffic_api *s_tr;
static float s_next;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_traffic_vehicle v[BM_TRAFFIC_NEAR_MAX];
    uint32_t n = BM_TRAFFIC_NEAR_MAX;
    char line[200];
    (void)user;
    if (!s_tr || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 2.0f;
    v[0].struct_size = (uint32_t)sizeof v[0];
    if (s_tr->near_vehicles(s_api->host, 0, v, &n) != BM_TRAFFIC_OK)
        return;
    for (uint32_t i = 0; i < n; i++) {
        if (v[i].crashed || !v[i].same_direction || v[i].rel_pos_m[2] < 5.0f || v[i].rel_pos_m[2] > 35.0f ||
            fabsf(v[i].rel_pos_m[0]) > 3.0f)
            continue;
        snprintf(line, sizeof line, "t %.0f s: wreck the vehicle %.1f m ahead (class %u, %.1f m/s) -> %d", snap->race_time_s,
                 v[i].rel_pos_m[2], (unsigned)v[i].vehicle_class, v[i].speed_mps, (int)s_tr->wreck(s_api->host, v[i].handle));
        say(line);
        break;
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("traffic kamikaze example: the car ahead in your lane wrecks itself every 2 s (bmashup.traffic near_vehicles / wreck)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_TRAFFIC_SERVICE)) {
        const bm_traffic_api *tr = (const bm_traffic_api *)table;
        uint32_t n = 1;
        bm_traffic_vehicle probe;
        if (version < 3 || tr->struct_size < sizeof *tr || !tr->near_vehicles || !tr->wreck) {
            say("traffic kamikaze example: this host's bmashup.traffic has no near_vehicles / wreck");
            return 1;
        }
        probe.struct_size = (uint32_t)sizeof probe;
        if (tr->near_vehicles(s_api->host, 0, &probe, &n) == BM_TRAFFIC_UNAVAILABLE && version < 5)
            say("traffic kamikaze example: near_vehicles is UNAVAILABLE on this host (needs a main21 host)");
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
