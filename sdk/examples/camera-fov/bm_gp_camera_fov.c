/*
 * bm_gp_camera_fov.c - gp slice camset1 example plugin "bmashup-gp.camera-fov": a field-of-view setting on the MODS page
 * (bmashup.settings v1) that drives bmashup.camera v1's field-of-view scale. Experimental, private.
 *
 *   setting   fov_scale  "CAMERA FOV"  INT 70..140 step 5, default 100, unit "%"  (MODS > MOD SETTINGS; A steps it)
 *   effect    each value (the initial one at the first front-end set-up, then every change) is handed to
 *             bmashup.camera set_fov_scale: it applies from the next one-player race / Restart; 100 = the game's view.
 *   log       one line per value and the camera's state at each race exit (bmashup.events v2+, optional).
 * Needs: bmashup.settings >= 1, bmashup.camera >= 1. Without either it logs why and does nothing.
 * Uses only the public headers (takedawn_plugin.h, takedawn_services.h, bmashup_host.h, bmashup_settings.h,
 * bmashup_camera.h, bmashup_events.h). No game memory, no address.
 */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_services.h"
#include "bmashup_host.h"
#include "bmashup_settings.h"
#include "bmashup_camera.h"
#include "bmashup_events.h"

static const td_host_api *s_api;
static const bm_settings_api *s_set;
static const bm_camera_api *s_cam;
static int s_declared, s_value = -1, s_exits;

static void say(int level, const char *fmt, ...)
{
    char line[400];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    s_api->log(s_api->host, level, line);
}

static void TD_CALL on_value(const char *key, int32_t value, uint32_t reason, void *user)
{
    int32_t rc;
    (void)user;
    if (strcmp(key, "fov_scale"))
        return;
    s_value = value;
    rc = s_cam ? s_cam->set_fov_scale(s_api->host, (uint32_t)value) : -1;
    say(rc == BM_CAMERA_OK ? TD_LOG_INFO : TD_LOG_WARN, "camera-fov: fov_scale = %d %% (%s): camera %s", (int)value,
        reason == BM_SETTING_INITIAL ? "initial" : "changed on the MODS page",
        rc == BM_CAMERA_OK ? "from the next race" : rc == -1 ? "service missing" : "refused");
}

static void TD_CALL on_exit(const bm_event *ev, void *user)
{
    bm_camera_state st;
    (void)user;
    (void)ev;
    if (!s_cam)
        return;
    memset(&st, 0, sizeof st);
    st.struct_size = sizeof st;
    if (s_cam->state(s_api->host, &st) == BM_CAMERA_OK) {
        int32_t now = s_value;
        if (s_set)
            s_set->get(s_api->host, "fov_scale", &now);
        say(TD_LOG_INFO, "camera-fov: race exit %d: the race was set up with field of view %.4f (game %.4f x %u %%), "
            "aspect %.4f; %u stage set-up(s); next %u %% (setting %d %%)", ++s_exits, (double)st.applied_fov,
            (double)st.game_fov, (unsigned)st.applied_scale, (double)st.game_aspect, (unsigned)st.setups,
            (unsigned)st.requested_scale, (int)now);
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

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
    if (!strcmp(name, BM_SETTINGS_SERVICE) && version >= 1) {
        const bm_settings_api *t = (const bm_settings_api *)table;
        bm_setting_decl d;
        int32_t v = 0, rc;
        if (t->struct_size < sizeof *t)
            return 1;
        s_set = t;
        memset(&d, 0, sizeof d);
        d.struct_size = sizeof d;
        d.kind = BM_SETTING_INT;
        d.key = "fov_scale";
        d.label = "CAMERA FOV";
        d.unit = "%";
        d.min = 70;
        d.max = 140;
        d.step = 5;
        d.def = 100;
        rc = t->declare(s_api->host, &d, &v);
        if (rc == BM_SETTINGS_OK)
            rc = t->subscribe(s_api->host, on_value, NULL);
        s_declared = rc == BM_SETTINGS_OK;
        say(s_declared ? TD_LOG_INFO : TD_LOG_ERROR, "camera-fov: setting fov_scale %s (value now %d %%)",
            s_declared ? "declared" : "NOT declared", (int)v);
        return s_declared ? TD_OK : 1;
    }
    if (!strcmp(name, BM_CAMERA_SERVICE) && version >= 1) {
        const bm_camera_api *t = (const bm_camera_api *)table;
        if (t->struct_size < sizeof *t)
            return 1;
        s_cam = t;
        return TD_OK;
    }
    if (!strcmp(name, BM_EVENTS_SERVICE) && version >= 2) {
        const bm_events_api *t = (const bm_events_api *)table;
        return t->subscribe(s_api->host, BM_EVENT_RACE_EXIT, on_exit, NULL) == BM_EVENTS_OK ? TD_OK : 1;
    }
    return 1;
}

TD_EXPORT void TD_CALL takedawn_plugin_services_done(const td_host_api *api, uint32_t offered)
{
    (void)api;
    (void)offered;
    if (!s_declared || !s_cam)
        say(TD_LOG_WARN, "camera-fov: inactive (%s%s)", s_declared ? "" : "no bmashup.settings 1 ",
            s_cam ? "" : "no bmashup.camera 1");
    else
        say(TD_LOG_INFO, "camera-fov: ready (MODS > MOD SETTINGS > CAMERA FOV)");
}
