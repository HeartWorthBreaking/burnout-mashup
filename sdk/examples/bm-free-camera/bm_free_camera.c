/*
 * bm_free_camera.c - example for bmashup.camera version 3 (main21 patch 82): the free camera, two ways (hook request
 * "zackypoo" 05 "Right-Stick Orbit Camera" and 12 "Third person when looking behind").
 *   - ORBIT: pad 0's right stick turns the camera around player 1's car (full turn of yaw, pitch BM_FC_PITCH_MIN .. MAX,
 *     BM_FC_DIST metres away, looking at a point BM_FC_LOOK_H above the car); 1.5 s after the stick is let go the game's chase
 *     camera comes back (release_free).
 *   - LOOK BACK: while player 0's view is an alternative view (state().view == BM_CAMERA_VIEW_ALT, the look-back camera is
 *     expected there: probe R23) the camera sits in front of the car, above it, looking back at it - a third-person look-back.
 * Every update (takedawn.race on_update, the game's thread) renews the pose (bmashup.camera keeps a free pose
 * BM_CAMERA_FREE_TTL_PICTURES pictures). The car's pose comes from bmashup.racers 4 get_pose (racer 0 = player 1's car).
 * Nothing in the game's state changes; only the picture's camera.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_free_camera.c -o bm_free_camera.asi
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_camera.h"
#include "bmashup_input.h"
#include "bmashup_racers.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef BM_FC_DIST
#define BM_FC_DIST 7.0f
#endif
#ifndef BM_FC_LOOK_H
#define BM_FC_LOOK_H 1.0f
#endif
#ifndef BM_FC_PITCH_MIN
#define BM_FC_PITCH_MIN -0.15f
#endif
#ifndef BM_FC_PITCH_MAX
#define BM_FC_PITCH_MAX 0.9f
#endif
#ifndef BM_FC_RATE
#define BM_FC_RATE 2.5f          /* rad / s at full stick */
#endif

static const td_host_api *s_api;
static const bm_camera_api *s_cam;
static const bm_racers_api *s_rc;
static const bm_input_api *s_in;
static float s_yaw, s_pitch = 0.25f, s_idle = 2.0f, s_last_t;    /* idle at start: no orbit before the stick moves */
static int s_holding;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void let_go(void)
{
    if (s_holding)
        s_cam->release_free(s_api->host);
    s_holding = 0;
}

static void hold(const float pos[3], const float at[3], const float up[3])
{
    bm_camera_free f;
    memset(&f, 0, sizeof f);
    f.struct_size = (uint32_t)sizeof f;
    memcpy(f.pos, pos, sizeof f.pos);
    memcpy(f.at, at, sizeof f.at);
    memcpy(f.up, up, sizeof f.up);
    f.fov_scale = 1.0f;
    s_holding = s_cam->set_free_pose(s_api->host, &f) == BM_CAMERA_OK;
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_camera_state cs;
    bm_racer_pose p;
    bm_input_pad pad;
    float dt, pos[3], at[3], fx, fz, fl;
    (void)user;
    if (!s_cam || !s_rc || snap->state != TD_RACE_RACING) {
        let_go();
        s_last_t = 0.0f;
        s_idle = 2.0f;                                   /* the next race starts with the game's camera */
        return;
    }
    dt = s_last_t > 0.0f ? snap->race_time_s - s_last_t : 0.0f;
    s_last_t = snap->race_time_s;
    if (dt < 0.0f || dt > 0.25f)
        dt = 0.0f;
    memset(&p, 0, sizeof p);
    p.struct_size = (uint32_t)sizeof p;
    memset(&cs, 0, sizeof cs);
    cs.struct_size = (uint32_t)sizeof cs;
    if (s_rc->get_pose(s_api->host, 0, &p) != BM_RACERS_OK || s_cam->state(s_api->host, &cs) != BM_CAMERA_OK) {
        let_go();
        return;
    }
    fl = sqrtf(p.fwd[0] * p.fwd[0] + p.fwd[2] * p.fwd[2]);
    fx = fl > 1e-3f ? p.fwd[0] / fl : 0.0f;
    fz = fl > 1e-3f ? p.fwd[2] / fl : 1.0f;
    at[0] = p.pos[0]; at[1] = p.pos[1] + BM_FC_LOOK_H; at[2] = p.pos[2];
    if (cs.view == BM_CAMERA_VIEW_ALT) {                 /* 12: third person while looking back */
        pos[0] = p.pos[0] + fx * 6.0f; pos[1] = p.pos[1] + 2.4f; pos[2] = p.pos[2] + fz * 6.0f;
        hold(pos, at, (const float[3]){0.0f, 1.0f, 0.0f});
        return;
    }
    memset(&pad, 0, sizeof pad);
    pad.struct_size = (uint32_t)sizeof pad;
    if (s_in && s_in->pad(s_api->host, 0, &pad) == BM_INPUT_OK && (fabsf(pad.rx) > 0.2f || fabsf(pad.ry) > 0.2f)) {
        s_yaw += pad.rx * BM_FC_RATE * dt;               /* 05: orbit, full turn */
        s_pitch += pad.ry * BM_FC_RATE * 0.5f * dt;
        s_pitch = s_pitch < BM_FC_PITCH_MIN ? BM_FC_PITCH_MIN : s_pitch > BM_FC_PITCH_MAX ? BM_FC_PITCH_MAX : s_pitch;
        s_idle = 0.0f;
    } else {
        s_idle += dt;
    }
    if (s_idle > 1.5f || cs.view != BM_CAMERA_VIEW_CHASE) {
        let_go();                                        /* the game's chase camera (and every other view) again */
        s_yaw = 0.0f;
        return;
    }
    {
        /* behind the car (yaw 0), turned by s_yaw about the vertical, raised by s_pitch */
        float c = cosf(s_yaw), s = sinf(s_yaw), bx = -(fx * c - fz * s), bz = -(fz * c + fx * s);
        float h = cosf(s_pitch) * BM_FC_DIST;
        pos[0] = at[0] + bx * h; pos[1] = at[1] + sinf(s_pitch) * BM_FC_DIST; pos[2] = at[2] + bz * h;
        hold(pos, at, (const float[3]){0.0f, 1.0f, 0.0f});
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("free camera example: right-stick orbit + third-person look-back (bmashup.camera 3)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_CAMERA_SERVICE)) {
        const bm_camera_api *c = (const bm_camera_api *)table;
        if (version < 3 || c->struct_size < sizeof *c || !c->set_free_pose) {
            say("free camera example: this host's bmashup.camera has no free camera (needs version 3)");
            return 1;
        }
        s_cam = c;
        return TD_OK;
    }
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *r = (const bm_racers_api *)table;
        if (version < 4 || r->struct_size < sizeof *r || !r->get_pose)
            return 1;
        s_rc = r;
        return TD_OK;
    }
    if (!strcmp(name, BM_INPUT_SERVICE)) {
        const bm_input_api *in = (const bm_input_api *)table;
        if (version < 1 || in->struct_size < sizeof *in)
            return 1;
        s_in = in;
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
