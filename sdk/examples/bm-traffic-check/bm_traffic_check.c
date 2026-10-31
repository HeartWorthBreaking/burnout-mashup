/*
 * bm_traffic_check.c - SDK 0.6.0 example: bmashup.traffic version 3 (crash pool counts, near_vehicles). Read only.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_traffic_check.c -o bm_traffic_check.asi
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

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_traffic_status st;
    bm_traffic_vehicle v[8];
    uint32_t n = 8;
    int32_t rc;
    char line[200];
    (void)user;
    if (!s_tr || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 1.0f;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_tr->status(s_api->host, &st) != BM_TRAFFIC_OK)
        return;
    v[0].struct_size = (uint32_t)sizeof v[0];
    rc = s_tr->near_vehicles(s_api->host, 0, v, &n);
    snprintf(line, sizeof line, "traffic %u of %u, crash pool %u / %u used, near_vehicles rc %d (%u)%s", (unsigned)st.active,
             (unsigned)st.pool, (unsigned)st.wreck_slots_used, (unsigned)BM_TRAFFIC_WRECK_SLOTS, (int)rc, (unsigned)n,
             rc == BM_TRAFFIC_UNAVAILABLE ? " - not available on this host build" : "");
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("traffic check example: crash pool and nearest traffic once a second (bmashup.traffic 3, read only)");
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
