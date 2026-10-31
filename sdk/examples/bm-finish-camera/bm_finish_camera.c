/*
 * bm_finish_camera.c - SDK 0.6.0 example: bmashup.camera version 2 set_finish_poses (authored end-of-race poses). Visual only.
 * At the start of each race it gives three poses around the finishing car (front low, side, high behind), 2.5 s each; the
 * host shows them when player 0's end-of-race camera starts, then gives the view back to the game's camera. On a host that
 * cannot tell the end-of-race camera (platform 0.1.9 as shipped) set_finish_poses answers BM_CAMERA_UNAVAILABLE.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_finish_camera.c -o bm_finish_camera.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_camera.h"

static const td_host_api *s_api;
static const bm_camera_api *s_cam;
static uint32_t s_last_state;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static bm_camera_pose pose(float px, float py, float pz, float ax, float ay, float az, float fov)
{
    bm_camera_pose p;
    memset(&p, 0, sizeof p);
    p.struct_size = (uint32_t)sizeof p;
    p.pos_m[0] = px; p.pos_m[1] = py; p.pos_m[2] = pz;
    p.at_m[0] = ax; p.at_m[1] = ay; p.at_m[2] = az;
    p.fov_scale = fov;
    p.hold_s = 2.5f;
    return p;
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_camera_pose p[1];
    int32_t rc;
    char line[120];
    (void)user;
    if (!s_cam || snap->state == s_last_state)
        return;
    s_last_state = snap->state;
    if (snap->state != TD_RACE_RACING)
        return;
    p[0] = pose(6.0f, 2.0f, 0.0f, 0.0f, 0.0f, 25.0f, 0.9f);     /* relative to the game's outro camera */
    rc = s_cam->set_finish_poses(s_api->host, p, 1);
    snprintf(line, sizeof line, "finish camera example: a finish pose for this race: rc %d%s", (int)rc,
             rc == BM_CAMERA_UNAVAILABLE ? " (not available on this host build)" : "");
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("finish camera example: an authored end-of-race pose (bmashup.camera 2 set_finish_poses)");
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