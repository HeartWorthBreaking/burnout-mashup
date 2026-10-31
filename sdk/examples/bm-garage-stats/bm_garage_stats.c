/*
 * bm_garage_stats.c - Burnout Mashup SDK 0.6.0 example for "bmashup.menu" v1 (bars): a TOP SPEED bar on car select, the
 * vehicle's "Max Speed In Boost" ValueDB record (bmashup.vphysics v2 vehicle query) scaled to 0..1 over 80..200 (clamped). Platform 0.1.9
 * (main19 item 47) draws it on car select with bmashup.hud 2's primitives for player 0's chosen car (feature_available(BARS) = 1).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_garage_stats.c -o bm_garage_stats.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_menu.h"
#include "bmashup_vphysics.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_vphys_api *s_vp;

/* find() takes the catalogue's FULL name (main21 probe S5d: the short "Max Speed In Boost" was NOT_FOUND for every car) */
#define TOP_SPEED_PARAM "Physics/Race Car/Misc | Max Speed In Boost"

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

/* main21 patch 87 (open-list item 8): one log line per car when the bar cannot be filled, naming the failing step */
static void why(const char *vehicle, const char *step, int32_t rc)
{
    static char s_last[32];
    char line[128];
    if (!strcmp(s_last, vehicle))
        return;
    snprintf(s_last, sizeof s_last, "%s", vehicle);
    snprintf(line, sizeof line, "garage stats: no TOP SPEED for \"%s\": %s (rc %d)", vehicle, step, (int)rc);
    say(line);
}

static float TD_CALL top_speed(const char *vehicle, void *user)
{
    uint32_t v = 0, param = 0;
    int32_t rc;
    bm_vphys_vehicle_value out;
    (void)user;
    if (!s_vp)
        return -1.0f;                               /* outside 0..1: the bar is not drawn */
    if ((rc = s_vp->vehicle_find(s_api->host, vehicle, &v)) != BM_VPHYS_OK) {
        why(vehicle, "vphysics vehicle_find", rc);
        return -1.0f;
    }
    if ((rc = s_vp->find(s_api->host, TOP_SPEED_PARAM, &param)) != BM_VPHYS_OK) {
        why(vehicle, "vphysics find(" TOP_SPEED_PARAM ")", rc);
        return -1.0f;
    }
    memset(&out, 0, sizeof out);
    out.struct_size = (uint32_t)sizeof out;
    if ((rc = s_vp->vehicle_value(s_api->host, v, param, &out)) != BM_VPHYS_OK || !out.have) {
        why(vehicle, "vphysics vehicle_value", rc);
        return -1.0f;
    }
    /* retail values are ~100..200 (COMPCAR1 123: physics1 run_c101); a value outside 0..1 is "not drawn", so clamp */
    {
        float f = (float)((out.value - 80.0) / 120.0);
        return f < 0.0f ? 0.0f : f > 1.0f ? 1.0f : f;
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
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_VPHYS_SERVICE)) {
        const bm_vphys_api *vp = (const bm_vphys_api *)table;
        if (version < 2 || vp->struct_size < sizeof *vp)
            return 1;
        s_vp = vp;
        return TD_OK;
    }
    if (!strcmp(name, BM_MENU_SERVICE)) {
        const bm_menu_api *m = (const bm_menu_api *)table;
        bm_menu_bar_decl b;
        char line[96];
        int32_t r;
        if (version < 1 || m->struct_size < sizeof *m)
            return 1;
        memset(&b, 0, sizeof b);
        b.struct_size = (uint32_t)sizeof b;
        b.label = "TOP SPEED";
        b.fn = top_speed;
        r = m->declare_bar(s_api->host, &b);
        snprintf(line, sizeof line, "garage stats: bar declared (%d); bars drawn by this host: %u", (int)r,
                 (unsigned)m->feature_available(s_api->host, BM_MENU_FEATURE_BARS));
        say(line);
        return TD_OK;
    }
    return 1;
}
