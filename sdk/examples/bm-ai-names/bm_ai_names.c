/*
 * bm_ai_names.c - example for bmashup.racers version 4 (main21 patch 81, hook request "zackypoo" 01 "AI names above drivers"):
 * a name label over every AI racer's car, drawn by the plugin itself. The game keeps no AI driver names, so the names are the
 * plugin's (BM_AN_NAMES, build time).
 *   - bmashup.hooks CAMERA_FINAL (OBSERVE): the chase camera's position and axes of the picture, kept;
 *   - bmashup.hooks HUD_PASS (OBSERVE): for each AI racer, racers 4 get_pose(), the point BM_AN_HEIGHT metres above the car
 *     projected with the camera (bmashup.camera state(): applied_fov = the horizontal view-window half-width, the vertical one
 *     applied_fov / game_aspect), and bmashup.hud 2 draw() of a TEXT label centred there (the host's dot font).
 *   Labels only in front of the camera and within BM_AN_RANGE metres; the text shrinks with distance.
 * The camera's right axis points to the picture's LEFT (RenderWare; S4 showed the labels mirrored with +1), hence
 * BM_AN_RIGHT_SIGN -1; the HUD's y sign is still this example's reading (probe R22).
 * Draws only what the plugin draws; nothing in the game changes.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_ai_names.c -o bm_ai_names.asi
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_camera.h"
#include "bmashup_hooks.h"
#include "bmashup_hud.h"
#include "bmashup_racers.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

#ifndef BM_AN_HEIGHT
#define BM_AN_HEIGHT 1.6f
#endif
#ifndef BM_AN_RANGE
#define BM_AN_RANGE 150.0f
#endif
#ifndef BM_AN_RIGHT_SIGN
#define BM_AN_RIGHT_SIGN -1.0f   /* RenderWare: the camera matrix's right axis points to the picture's left (probe R22, S4) */
#endif
#ifndef BM_AN_UP_SIGN
#define BM_AN_UP_SIGN 1.0f
#endif

#ifndef BM_AN_DIAG
#define BM_AN_DIAG 0             /* 1: one [ANDIAG] log line about every 60 HUD passes (probe S4c builds it with 1) */
#endif

static const char *const k_names[BM_RACERS_MAX] = { "", "VIPER", "BLADE", "NOVA", "RAZOR", "FLINT", "ECHO", "COMET" };

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static const bm_hud_api *s_hud;
static const bm_camera_api *s_cam;
static const bm_hooks_api *s_hk;
static float s_cpos[3], s_cright[3], s_cup[3], s_cfwd[3];
static int s_have_cam;
#if BM_AN_DIAG
static unsigned s_diag_n;
#endif

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }
static float dot3(const float *a, const float *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static int32_t TD_CALL on_camera(const bm_hook_ctx *c, bm_hook_out *o, void *u)
{
    (void)o; (void)u;
    memcpy(s_cpos, c->cam_pos, sizeof s_cpos);
    memcpy(s_cright, c->cam_right, sizeof s_cright);
    memcpy(s_cup, c->cam_up, sizeof s_cup);
    memcpy(s_cfwd, c->cam_fwd, sizeof s_cfwd);
    s_have_cam = 1;
    return BM_HOOK_KEEP;
}

static int32_t TD_CALL on_hud(const bm_hook_ctx *c, bm_hook_out *o, void *u)
{
    bm_camera_state cs;
    float fx, fy, cpos[3], cright[3], cup[3], cfwd[3];
    uint32_t n;
    (void)c; (void)o; (void)u;
    if (!s_rc || !s_hud || !s_cam)
        return BM_HOOK_KEEP;
    memset(&cs, 0, sizeof cs);
    cs.struct_size = (uint32_t)sizeof cs;
    if (s_cam->state(s_api->host, &cs) != BM_CAMERA_OK)
        return BM_HOOK_KEEP;
    if (cs.struct_size >= (uint32_t)sizeof cs && cs.picture_seq && cs.picture_half_w > 0.0f && cs.picture_half_h > 0.0f) {
        /* bmashup.camera 4: the picture as drawn - the game's per-picture angle (boost) and the pose of any view (free camera) */
        fx = cs.picture_half_w;
        fy = cs.picture_half_h;
        memcpy(cpos, cs.picture_pos, sizeof cpos);
        memcpy(cright, cs.picture_right, sizeof cright);
        memcpy(cup, cs.picture_up, sizeof cup);
        memcpy(cfwd, cs.picture_fwd, sizeof cfwd);
    } else {
        /* older hosts: CAMERA_FINAL (chase view only) and the stage factor (drifts in boost and with the free camera) */
        if (!s_have_cam || !(cs.applied_fov > 0.0f) || !(cs.game_aspect > 0.0f))
            return BM_HOOK_KEEP;
        fx = cs.applied_fov;
        fy = cs.applied_fov / cs.game_aspect;
        memcpy(cpos, s_cpos, sizeof cpos);
        memcpy(cright, s_cright, sizeof cright);
        memcpy(cup, s_cup, sizeof cup);
        memcpy(cfwd, s_cfwd, sizeof cfwd);
    }
    n = s_rc->count(s_api->host);
#if BM_AN_DIAG
    if (++s_diag_n % 60u == 0u) {
        char t[300];
        snprintf(t, sizeof t, "[ANDIAG] cam pos %.1f %.1f %.1f right %.2f %.2f %.2f up %.2f %.2f %.2f fwd %.2f %.2f %.2f fov %.3f aspect %.3f racers %u",
                 (double)cpos[0], (double)cpos[1], (double)cpos[2], (double)cright[0], (double)cright[1], (double)cright[2],
                 (double)cup[0], (double)cup[1], (double)cup[2], (double)cfwd[0], (double)cfwd[1], (double)cfwd[2],
                 (double)fx, (double)cs.game_aspect, (unsigned)n);
        say(t);
    }
#endif
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++) {
        bm_racer_info ri;
        bm_racer_pose p;
        bm_hud_cmd cmd;
        float d[3], z, x, y, size, w;
        memset(&ri, 0, sizeof ri);
        ri.struct_size = (uint32_t)sizeof ri;
        if (s_rc->get(s_api->host, k, &ri) != BM_RACERS_OK || ri.is_player1 || ri.wrecked)
            continue;
        memset(&p, 0, sizeof p);
        p.struct_size = (uint32_t)sizeof p;
        if (s_rc->get_pose(s_api->host, k, &p) != BM_RACERS_OK)
            continue;
        for (int i = 0; i < 3; i++)
            d[i] = p.pos[i] + p.up[i] * BM_AN_HEIGHT - cpos[i];
        z = dot3(d, cfwd);
        if (z < 2.0f || z > BM_AN_RANGE)
            continue;                                    /* behind the camera, too close or too far */
        x = 320.0f + 320.0f * BM_AN_RIGHT_SIGN * dot3(d, cright) / z / fx;
        y = 240.0f - 240.0f * BM_AN_UP_SIGN * dot3(d, cup) / z / fy;
#if BM_AN_DIAG
        if (s_diag_n % 60u == 0u) {
            char t[240];
            snprintf(t, sizeof t, "[ANDIAG]   racer %u %s pos %.1f %.1f %.1f  d.right %.2f d.up %.2f z %.2f -> HUD %.0f %.0f", (unsigned)k,
                     k_names[k], (double)p.pos[0], (double)p.pos[1], (double)p.pos[2], (double)dot3(d, cright), (double)dot3(d, cup),
                     (double)z, (double)x, (double)y);
            say(t);
        }
#endif
        size = 14.0f * 30.0f / z;
        size = size < 8.0f ? 8.0f : size > 20.0f ? 20.0f : size;
        w = (float)strlen(k_names[k]) * size * 6.0f / 7.0f;
        if (x - w / 2.0f < -64.0f || x + w / 2.0f > 704.0f || y < -64.0f || y > 544.0f)
            continue;
        memset(&cmd, 0, sizeof cmd);
        cmd.struct_size = (uint32_t)sizeof cmd;
        cmd.kind = BM_HUD_CMD_TEXT;
        cmd.x = x - w / 2.0f;
        cmd.y = y - size;
        cmd.rgba = 0xFFE040FFu;
        cmd.text = k_names[k];
        cmd.text_size = size;
        s_hud->draw(s_api->host, 0, &cmd);
    }
    return BM_HOOK_KEEP;
}

static void try_register(void)
{
    bm_hook_reg r;
    uint32_t id = 0;
    char line[120];
    if (!s_hk || !s_rc || !s_hud || !s_cam)
        return;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    r.point = BM_HOOK_CAMERA_FINAL;
    r.role = BM_HOOK_OBSERVE;
    r.fn = on_camera;
    snprintf(line, sizeof line, "register CAMERA_FINAL -> %d", (int)s_hk->register_hook(s_api->host, &r, &id));
    say(line);
    r.point = BM_HOOK_HUD_PASS;
    r.fn = on_hud;
    snprintf(line, sizeof line, "register HUD_PASS -> %d", (int)s_hk->register_hook(s_api->host, &r, &id));
    say(line);
    s_hk = NULL;                                         /* once */
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("AI names example: labels over the AI racers (bmashup.racers 4 get_pose + bmashup.hud 2 TEXT)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 4 || rc->struct_size < sizeof *rc || !rc->get_pose) {
            say("AI names example: this host's bmashup.racers has no get_pose (needs version 4)");
            return 1;
        }
        s_rc = rc;
    } else if (!strcmp(name, BM_HUD_SERVICE)) {
        const bm_hud_api *h = (const bm_hud_api *)table;
        if (version < 2 || h->struct_size < sizeof *h || !h->draw || !h->draw_available(s_api->host))
            return 1;
        s_hud = h;
    } else if (!strcmp(name, BM_CAMERA_SERVICE)) {
        const bm_camera_api *c = (const bm_camera_api *)table;
        if (version < 1 || c->struct_size < sizeof *c || !c->state)
            return 1;
        s_cam = c;
    } else if (!strcmp(name, BM_HOOKS_SERVICE)) {
        const bm_hooks_api *h = (const bm_hooks_api *)table;
        if (version < 3 || h->struct_size < sizeof *h || !h->register_hook)
            return 1;
        s_hk = h;
    } else {
        return 1;
    }
    try_register();
    return TD_OK;
}
