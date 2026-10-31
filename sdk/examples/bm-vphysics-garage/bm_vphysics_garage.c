/*
 * bm_vphysics_garage.c - SDK 0.5.0 example for bmashup.vphysics version 2 (the vehicle query): at the first front-end
 * update (no race needed) it lists every vehicle of the game's ValueDB with a few handling values - mass, drag, top-speed
 * limit, acceleration multiplier - straight from the ValueDB the game loaded (the values the next race copies). Read only.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_vphysics_garage.c -o bm_vphysics_garage.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_vphysics.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_vphys_api *s_vp;
static int s_done;

static const char *const k_show[] = { "Physics/Vehicle | Mass (Kg)", "Physics/Race Car/Misc | Drag Coef",
                                      "Physics/Race Car/Misc | Max Speed In Boost", "Physics/Race Car/Misc | Accel Multiplier" };

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void list_all(void)
{
    uint32_t idx[4], n = s_vp->vehicle_count(s_api->host);
    char line[300];
    if (!n)
        return;                                     /* not loaded yet: try again at the next update */
    for (int k = 0; k < 4; k++)
        if (s_vp->find(s_api->host, k_show[k], &idx[k]) != BM_VPHYS_OK)
            return;
    for (uint32_t v = 0; v < n; v++) {
        bm_vphys_vehicle_info vi;
        size_t at;
        memset(&vi, 0, sizeof vi);
        vi.struct_size = (uint32_t)sizeof vi;
        if (s_vp->vehicle_info(s_api->host, v, &vi) != BM_VPHYS_OK)
            continue;
        at = (size_t)snprintf(line, sizeof line, "%-10s%s", vi.name, vi.race_vehicle ? "" : " (no race handling)");
        for (int k = 0; k < 4 && at < sizeof line; k++) {
            bm_vphys_vehicle_value vv;
            memset(&vv, 0, sizeof vv);
            vv.struct_size = (uint32_t)sizeof vv;
            if (s_vp->vehicle_value(s_api->host, v, idx[k], &vv) == BM_VPHYS_OK && vv.have)
                at += (size_t)snprintf(line + at, sizeof line - at, " | %s %g", strchr(k_show[k], '|') + 2, vv.value);
        }
        say(line);
    }
    s_done = 1;
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    (void)snap;
    (void)user;
    if (s_vp && !s_done)
        list_all();
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("vphysics garage example: every vehicle's handling values outside a race (bmashup.vphysics 2)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_VPHYS_SERVICE)) {
        const bm_vphys_api *vp = (const bm_vphys_api *)table;
        if (version < 2 || vp->struct_size < sizeof *vp || !vp->vehicle_value)
            return 1;
        s_vp = vp;
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
