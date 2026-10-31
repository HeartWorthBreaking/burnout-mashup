/*
 * bm_camera_roll.c - SDK 0.6.0 example: bmashup.camera version 2 set_adjust (chase-camera roll), with a smoothing time.
 * Visual only. Holds a 0.12 rad roll (right side up) and a 0.3 m lift while racing; gives the adjust back at the end of the race.
 * On a host build that cannot tell the chase camera set_adjust answers BM_CAMERA_UNAVAILABLE: the example says so once and does
 * nothing (platform 0.1.9 tells it: the camera dispatch's bit 2).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_camera_roll.c -o bm_camera_roll.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_camera.h"

static const td_host_api *s_api;
static const bm_camera_api *s_cam;
static int s_held, s_said;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_camera_adjust a;
    int32_t rc;
    (void)user;
    if (!s_cam)
        return;
    if (snap->state != TD_RACE_RACING) {
        if (s_held && s_cam->release_adjust(s_api->host) == BM_CAMERA_OK)
            s_held = 0;
        return;
    }
    if (s_held)
        return;
    memset(&a, 0, sizeof a);
    a.struct_size = (uint32_t)sizeof a;
    a.roll_rad = 0.12f;
    a.offset_m[1] = 0.3f;
    a.smoothing_s = 0.4f;
    rc = s_cam->set_adjust(s_api->host, &a);
    if (rc == BM_CAMERA_OK) {
        s_held = 1;
        say("camera roll example: chase-camera roll 0.12 rad held");
    } else if (!s_said) {
        s_said = 1;
        say(rc == BM_CAMERA_UNAVAILABLE ? "camera roll example: the chase-camera adjust is not available on this host build"
                                        : "camera roll example: set_adjust refused (another plugin owns it?)");
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("camera roll example: a small chase-camera roll while racing (bmashup.camera 2)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_CAMERA_SERVICE)) {
        const bm_camera_api *c = (const bm_camera_api *)table;
        if (version < BM_CAMERA_VERSION_2 || c->struct_size < sizeof *c)
            return 1;
        s_cam = c;
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