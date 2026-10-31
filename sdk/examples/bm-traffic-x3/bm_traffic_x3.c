/*
 * bm_traffic_x3.c - SDK 0.5.0 example for bmashup.traffic version 2: asks for traffic density 3.0 (EXPERIMENTAL above 2.0)
 * at start, and logs the traffic status (active / pool / flows / the experimental flag) every 5 s of race time. The game's
 * own pool, spawn and draw limits are unchanged: above 2.0 vehicles may be refused or not drawn. This is also the
 * measuring plugin of the traffic 3.0 launch. The density may be set from 0.0 to 3.0 with BM_TRAFFIC_X3_DENSITY at build
 * time. CHANGES GAMEPLAY.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_traffic_x3.c -o bm_traffic_x3.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_traffic.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef BM_TRAFFIC_X3_DENSITY
#define BM_TRAFFIC_X3_DENSITY 3.0
#endif

static const td_host_api *s_api;
static const bm_traffic_api *s_tr;
static float s_next;
static uint32_t s_max_active;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_traffic_status st;
    char line[260];
    (void)user;
    if (!s_tr)
        return;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_tr->status(s_api->host, &st) != BM_TRAFFIC_OK || !st.in_race)
        return;
    if (st.active > s_max_active)
        s_max_active = st.active;
    if (snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 5.0f;
    snprintf(line, sizeof line, "t %.0f s: active %u (max %u) of pool %u, start flow %.1f -> %.1f /min, density %.2f applied "
             "%.2f%s", snap->race_time_s, (unsigned)st.active, (unsigned)s_max_active, (unsigned)st.pool, st.flow_start_game,
             st.flow_start_now, st.density, st.density_applied, st.experimental ? " EXPERIMENTAL" : "");
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("traffic x3 example: density 3.0 (bmashup.traffic 2, EXPERIMENTAL above 2.0)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_TRAFFIC_SERVICE)) {
        const bm_traffic_api *tr = (const bm_traffic_api *)table;
        char line[120];
        int32_t rc;
        if (version < 2 || tr->struct_size < sizeof *tr || !tr->set_density_v2) {
            say("traffic x3 example: this host's bmashup.traffic has no set_density_v2 (needs version 2)");
            return 1;
        }
        s_tr = tr;
        rc = tr->set_density_v2(s_api->host, BM_TRAFFIC_X3_DENSITY);
        snprintf(line, sizeof line, "set_density_v2(%.2f) -> %d", BM_TRAFFIC_X3_DENSITY, (int)rc);
        say(line);
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
