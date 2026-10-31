/*
 * bm_camera.c - "bmashup.camera" (include/bmashup_camera.h), version 1 (gp slice camset1). See bm_camera.h for where
 * the generated code calls in.
 *
 * The request (per cent) and its owner are atomics: set / release on any thread; the set-up reads them on the game's
 * thread. The set-up's own values (game factor, aspect, the scale used) are written on the game's thread only and read
 * by state() as plain 32-bit fields.
 */
#include "bm_camera.h"

#include <math.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif
/* main21 patch 96: version 4 (state()'s picture fields, bm_camview.c) behind BO3_HOOKREQ_P27C */
#ifndef BO3_HOOKREQ_P27C
#define BO3_HOOKREQ_P27C 0          /* unit tests without the option: version 3, as before; the game: CMake ON */
#endif
#define CAM_VERSION (BO3_HOOKREQ_P27C ? BM_CAMERA_VERSION : BM_CAMERA_VERSION_3)
#define CAM_STATE_SIZE (BO3_HOOKREQ_P27C ? (uint32_t)sizeof(bm_camera_state) : (uint32_t)offsetof(bm_camera_state, picture_seq))

static _Atomic uint32_t s_req = BM_CAMERA_FOV_GAME;    /* the next stage set-up's scale */
static _Atomic(td_host *) s_owner;
static int s_available;
static volatile uint32_t s_stage;                      /* a one-player stage set-up began, no front-end set-up since */
static volatile uint32_t s_setups, s_fe_calls;
static volatile float s_game_fov, s_game_aspect, s_applied_fov;
static volatile uint32_t s_applied = BM_CAMERA_FOV_GAME;
static int (*s_crash)(void);
static const bo3_cam_v2_ops *s_v2;                     /* main19 (v2): bm_camview.c's operations, NULL = UNAVAILABLE */

_Static_assert(offsetof(bm_camera_state, chase_active) == 48, "bm_camera_state: the v1 layout (48 bytes) is kept");
_Static_assert(sizeof(bm_camera_adjust) == 32, "bm_camera_adjust layout");
_Static_assert(sizeof(bm_camera_pose) == 36, "bm_camera_pose layout");

static const char *who(td_host *h)
{
    const char *id = h ? bo3_plugins_host_id(h) : NULL;
    return id && *id ? id : "(none)";
}

static int32_t TD_CALL cam_set(td_host *host, uint32_t pct)
{
    td_host *none = NULL;
    if (!host)
        return BM_CAMERA_BAD_ARG;
    if (!s_available)
        return BM_CAMERA_UNAVAILABLE;
#if MUT != 2
    if (pct < BM_CAMERA_FOV_MIN || pct > BM_CAMERA_FOV_MAX) {
        fprintf(stderr, "[CAMERA] mod %s: field-of-view scale %u%% refused: %u..%u\n", who(host), (unsigned)pct,
                BM_CAMERA_FOV_MIN, BM_CAMERA_FOV_MAX);
        return BM_CAMERA_OUT_OF_RANGE;
    }
#endif
    if (pct == BM_CAMERA_FOV_GAME) {
        td_host *me = host;
        if (atomic_compare_exchange_strong(&s_owner, &me, NULL)) {
            atomic_store(&s_req, BM_CAMERA_FOV_GAME);
            fprintf(stderr, "[CAMERA] mod %s: field-of-view scale 100%% (the game's) from the next stage set-up; "
                    "released\n", who(host));
            return BM_CAMERA_OK;
        }
        if (me == NULL)
            return BM_CAMERA_OK;                       /* nobody owns it: the game's already */
#if MUT != 3
        return BM_CAMERA_BUSY;
#endif
    }
#if MUT == 3
    atomic_store(&s_owner, host);                      /* defect: the last caller takes it */
#else
    if (!atomic_compare_exchange_strong(&s_owner, &none, host) && none != host) {
        fprintf(stderr, "[CAMERA] mod %s: field-of-view scale %u%% refused: owned by mod %s\n", who(host), (unsigned)pct,
                who(none));
        return BM_CAMERA_BUSY;
    }
#endif
    atomic_store(&s_req, pct);
    fprintf(stderr, "[CAMERA] mod %s: field-of-view scale %u%% from the next one-player stage set-up\n", who(host),
            (unsigned)pct);
    return BM_CAMERA_OK;
}

static int32_t TD_CALL cam_release(td_host *host)
{
    td_host *me = host;
    if (!host)
        return BM_CAMERA_BAD_ARG;
#if MUT == 6
    atomic_store(&s_owner, NULL);                      /* defect: anyone frees it */
    atomic_store(&s_req, BM_CAMERA_FOV_GAME);
    return BM_CAMERA_OK;
#endif
    if (!atomic_compare_exchange_strong(&s_owner, &me, NULL))
        return BM_CAMERA_NOT_OWNER;
    atomic_store(&s_req, BM_CAMERA_FOV_GAME);
    fprintf(stderr, "[CAMERA] mod %s: field-of-view scale released (the game's from the next stage set-up)\n",
            who(host));
    return BM_CAMERA_OK;
}

static int32_t TD_CALL cam_state(td_host *host, bm_camera_state *out)
{
    bm_camera_state s;
    uint32_t room;
    td_host *o;
    if (!host || !out || out->struct_size < 8)
        return BM_CAMERA_BAD_ARG;
    memset(&s, 0, sizeof s);
    s.struct_size = CAM_STATE_SIZE;
    s.available = (uint32_t)s_available;
    s.stage_active = s_stage;
    s.setups = s_setups;
    s.game_fov = s_game_fov;
    s.game_aspect = s_game_aspect;
    s.applied_fov = s_applied_fov;
    s.applied_scale = s_applied;
    s.requested_scale = atomic_load(&s_req);
    o = atomic_load(&s_owner);
    s.owned = o != NULL;
    s.yours = o == host;
    s.crash_camera = s_stage && s_crash ? (uint32_t)(s_crash() != 0) : 0;
    if (s_v2 && s_v2->fill_state)
        s_v2->fill_state(host, &s);                    /* main19 (v2) */
    room = out->struct_size < CAM_STATE_SIZE ? out->struct_size : CAM_STATE_SIZE;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_CAMERA_OK;
}

/* main19 (version 2): forwarded to bm_camview.c */
static int32_t TD_CALL cam_set_adjust(td_host *host, const bm_camera_adjust *a)
{
    if (!host || !a)
        return BM_CAMERA_BAD_ARG;
    return s_v2 && s_v2->set_adjust ? s_v2->set_adjust(host, a) : BM_CAMERA_UNAVAILABLE;
}

static int32_t TD_CALL cam_release_adjust(td_host *host)
{
    if (!host)
        return BM_CAMERA_BAD_ARG;
    return s_v2 && s_v2->release_adjust ? s_v2->release_adjust(host) : BM_CAMERA_UNAVAILABLE;
}

static int32_t TD_CALL cam_set_finish_poses(td_host *host, const bm_camera_pose *p, uint32_t n)
{
    if (!host || (n && !p))
        return BM_CAMERA_BAD_ARG;
    return s_v2 && s_v2->set_finish_poses ? s_v2->set_finish_poses(host, p, n) : BM_CAMERA_UNAVAILABLE;
}

/* main21 patch 82 (version 3): the free camera, forwarded to bm_camview.c */
static int32_t TD_CALL cam_set_free_pose(td_host *host, const bm_camera_free *f)
{
    if (!host || !f || f->struct_size < (uint32_t)sizeof *f)
        return BM_CAMERA_BAD_ARG;
    return s_v2 && s_v2->set_free_pose ? s_v2->set_free_pose(host, f) : BM_CAMERA_UNAVAILABLE;
}

static int32_t TD_CALL cam_release_free(td_host *host)
{
    if (!host)
        return BM_CAMERA_BAD_ARG;
    return s_v2 && s_v2->release_free ? s_v2->release_free(host) : BM_CAMERA_UNAVAILABLE;
}

static const bm_camera_api s_api = {
    (uint32_t)sizeof(bm_camera_api), CAM_VERSION, cam_set, cam_release, cam_state, cam_set_adjust, cam_release_adjust,
    cam_set_finish_poses, cam_set_free_pose, cam_release_free
};

void bo3_cam_set_v2(const bo3_cam_v2_ops *ops)
{
    s_v2 = ops;
}

int bo3_cam_stage_active(void)
{
    return s_stage != 0;
}

int bo3_cam_crash_camera(void)
{
    return s_stage && s_crash ? s_crash() != 0 : 0;
}

const bm_camera_api *bo3_bm_camera_api(void) { return &s_api; }

void bo3_cam_stage_setup(void)
{
    s_stage = 1;
    s_applied = BM_CAMERA_FOV_GAME;                    /* until this stage's camera set-up (none in split screen) */
}

void bo3_cam_fe_setup(void)
{
#if MUT != 4
    if (s_stage)
        fprintf(stderr, "[CAMERA] front-end set-up: the game's field of view (stage scale %u%% ends)\n",
                (unsigned)s_applied);
    s_stage = 0;
    s_applied = BM_CAMERA_FOV_GAME;
#endif
}

float bo3_cam_gen_fov(float fov, float aspect, uint32_t wide)
{
    uint32_t pct;
    float out;
#if MUT != 1
    if (!s_stage) {
        s_fe_calls++;
        return fov;                                    /* the front end: the game's own */
    }
#endif
    pct = atomic_load(&s_req);
    out = fov;
    if (pct != BM_CAMERA_FOV_GAME) {
#if MUT == 5
        out = (float)pct / 100.0f;                     /* defect: the scale replaces the factor */
#else
        out = (float)((double)fov * pct / 100.0);
#endif
        if (!isfinite(out) || out <= 0.0f)
            out = fov;                                 /* never a broken view: the game's */
    }
    s_setups++;
    s_game_fov = fov;
    s_game_aspect = aspect;
    s_applied_fov = out;
    s_applied = out == fov ? BM_CAMERA_FOV_GAME : pct;
    fprintf(stderr, "[CAMERA] stage camera set-up %u (%s): field of view %.4f x %u%% = %.4f, aspect %.4f\n",
            (unsigned)s_setups, (wide & 0xFFu) ? "16:9" : "4:3", (double)fov, (unsigned)s_applied, (double)out,
            (double)aspect);
    return out;
}

#ifdef BO3_CAMERA_GAME     /* the game build: player 1's crash-camera byte (docs/crash60.md: MEM8(0x73BACA)) */
#include <stddef.h>
extern ptrdiff_t g_xbox_mem_offset;
static int game_crash(void)
{
    return g_xbox_mem_offset ? *(volatile uint8_t *)((uintptr_t)g_xbox_mem_offset + 0x73BACAu) : 0;
}
#endif

void bo3_bm_camera_init(void)
{
#ifdef BO3_CAMERA_GAME
    s_available = 1;                                   /* the generated line is audited into this build */
    s_crash = game_crash;
#endif
    bo3_plugins_service(BM_CAMERA_SERVICE, CAM_VERSION, &s_api);
}

void bo3_cam_reset_for_tests(int available)
{
    atomic_store(&s_req, BM_CAMERA_FOV_GAME);
    atomic_store(&s_owner, NULL);
    s_available = available;
    s_stage = s_setups = s_fe_calls = 0;
    s_game_fov = s_game_aspect = s_applied_fov = 0.0f;
    s_applied = BM_CAMERA_FOV_GAME;
    s_crash = NULL;
    s_v2 = NULL;
}

void bo3_cam_set_crash_reader(int (*fn)(void)) { s_crash = fn; }
