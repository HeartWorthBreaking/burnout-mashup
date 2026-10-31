/*
 * bmashup_camera.h - the "bmashup.camera" service: Burnout Mashup's private, experimental camera control (gp slice
 * camset1). Not a Takedawn service: offered only by Burnout Mashup's own builds, through the same optional export as
 * Takedawn's (takedawn_services.h); it may change or go away.
 *
 * Version 1 has one bounded control and one query.
 *
 * Field-of-view scale. The game sets each view's camera up once, when a stage (a race, Road Rage, Crash, a Restart)
 * is set up, with a field-of-view factor of its own (1.2 in 16:9, 1.0 in 4:3; display.ultrawide widens it). A plugin
 * asks for a scale of that factor in per cent, 70..140 (100 = the game's). The scale is applied at the next
 * ONE-PLAYER stage set-up only: the race being driven keeps its view until the next race or Restart, the front end
 * (menus, garage) always gets the game's own factor, and split-screen stages are not changed (version 1). Nothing is
 * written into the game's data: the factor the set-up loaded is scaled before the game stores it, so leaving the stage
 * (the front end's own set-up) restores the game's view by itself.
 *
 * Ownership. One plugin at a time owns the scale: the first one that asks for anything but 100. Another plugin's
 * request is refused (BM_CAMERA_BUSY) until the owner asks for 100 again or calls release. The owner's latest request
 * is the one used. Requests are taken on any thread after the plugins' start (and during it); the set-up reads the
 * latest one on the game's thread.
 *
 * Query. state() copies what the host knows of the camera: whether a one-player stage is set up now, how many set-ups
 * the scale saw, the game's factor and aspect at the last one, the scale applied there, the scale asked for next, and
 * the first player's crash-camera flag (the title's own byte, read when asked; 1 while a crash or takedown camera
 * runs). Nothing in it points into the game.
 *
 * Version 2 (platform 0.1.9, hook request P2 / P3; append-only, the FOV scale unchanged):
 *   Chase-camera ADJUST: set_adjust() holds a roll / pitch / yaw / offset LEVEL that the host applies to player 0's view for
 *     each picture while the chase camera is the view; never in crash / takedown cameras, look-back, replays, the front end or
 *     split screen. It is applied to the picture's COPY of the camera matrix (the matrix the game builds from its camera for
 *     the picture, before the frame, the view matrix and the frustum are made from it): the game's camera state is never
 *     written, so nothing drifts and nothing needs restoring. bmashup.hooks CAMERA_FINAL modifiers may change the level per
 *     picture (the total stays inside the bounds). One owner (BUSY), as the FOV scale; release_adjust() gives it back.
 *     The chase camera = the camera dispatch's bit 2 alone (probe PR-A2); crash, alternative, intro and outro cameras never.
 *     A build made with the slot unknown (bm_camview.c BM_P23_CAMERA_FOLLOW_BIT < 0) answers BM_CAMERA_UNAVAILABLE.
 *   FINISH POSE (P3, folded into version 2; REDUCED form, platform 0.1.9): the game's end-of-race camera is ONE STATIC pose
 *     per track (and the car is not frozen: it drives on). set_finish_poses() gives at most BM_CAMERA_FINISH_POSES_SERVED (1)
 *     authored pose for the race in play, RELATIVE TO THE GAME'S OUTRO CAMERA (x right, y up, z forward of that camera),
 *     within BM_CAMERA_FINISH_RADIUS_M (40 m) of it; when player 0's end-of-race camera starts, the host shows it instead of
 *     the game's pose for the whole outro (hold_s is checked but not used: the pose holds until the outro ends). bmashup.hooks
 *     FINISH_CAMERA modifiers may give another pose per picture (same radius around the outro camera). Applied to the
 *     picture's copy of the camera matrix, as the adjust; cleared when the race's stage ends (front end). Authored poses only
 *     (no game data). n > 1: OUT_OF_RANGE. BM_CAMERA_FINISH_POSES_MAX (16) stays the layout bound for a later host.
 *   state() grows: chase_active, applied_roll_rad, adjust_owned, adjust_yours, finish_active (version 2).
 *
 * Version 3 (main21 patch 82, hook request "zackypoo" 05 / 12; append-only, every v2 rule unchanged):
 *   FREE CAMERA: set_free_pose() gives player 0's view a camera of the plugin's own - a world position, a point to look at,
 *     an up direction and a field-of-view scale - for ANY of player 0's race views (chase, look-back / alternative, crash,
 *     intro, outro) of a one-player stage. It is written into the picture's COPY of the camera matrix, like the adjust (the
 *     game's camera state is never written), and replaces the adjust, the finish pose and CAMERA_FINAL / FINISH_CAMERA for
 *     those pictures. Bounds: finite values; pos != at; up not parallel to the view; fov_scale 0.7 .. 1.4; the position within
 *     BM_CAMERA_FREE_RADIUS_M of player 1's car (checked at the call and again every picture: the world streams around the
 *     car, so a camera farther away shows the game's camera instead). A pose is RENEWED by calling again: it applies for at
 *     most BM_CAMERA_FREE_TTL_PICTURES pictures after the last call (a plugin that stops calling gives the game's camera back
 *     by itself); release_free() ends it at once. One owner (BUSY), its own owner. Any thread. NOT_IN_RACE outside a
 *     one-player stage. Input is the plugin's (bmashup.input).
 *   state() grows: free_active (the last picture used the free pose), free_owned, free_yours, view (BM_CAMERA_VIEW_*: player
 *     0's view at the last picture, from the camera dispatch's active set - CHASE = bit 2 alone, FINISH = bit 8 alone, CRASH =
 *     the crash byte, ALT = bit 4 or 5 alone (the alternative views; which of them is the look-back camera is probe R23's
 *     question), OTHER, NONE outside a one-player race view).
 */
#ifndef BMASHUP_CAMERA_H
#define BMASHUP_CAMERA_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_CAMERA_SERVICE "bmashup.camera"
#define BM_CAMERA_VERSION 4u             /* 4 (main21 patch 96): + state()'s picture view window and pose
                                          * 1: FOV scale; 2 (platform 0.1.9): + chase-camera adjust */
#define BM_CAMERA_VERSION_1 1u
#define BM_CAMERA_VERSION_2 2u
#define BM_CAMERA_VERSION_3 3u
#define BM_CAMERA_VERSION_4 4u
#define BM_CAMERA_FREE_RADIUS_M 60.0f        /* v3: the free camera's distance bound from player 1's car */
#define BM_CAMERA_FREE_TTL_PICTURES 4u       /* v3: a free pose lives this many pictures after its last set_free_pose */
enum { BM_CAMERA_VIEW_NONE = 0, BM_CAMERA_VIEW_CHASE = 1, BM_CAMERA_VIEW_CRASH = 2, BM_CAMERA_VIEW_FINISH = 3,
       BM_CAMERA_VIEW_ALT = 4, BM_CAMERA_VIEW_OTHER = 5 };   /* v3: state().view */

#define BM_CAMERA_FOV_MIN 70u
#define BM_CAMERA_FOV_MAX 140u
#define BM_CAMERA_FOV_GAME 100u
/* version 2: the adjust bounds (= bmashup.hooks' CAMERA_ADJUST bounds) */
#define BM_CAMERA_ROLL_MAX_RAD 0.35f
#define BM_CAMERA_PITCH_YAW_MAX_RAD 0.17f
#define BM_CAMERA_OFFSET_MAX_M 2.0f
#define BM_CAMERA_FINISH_POSES_MAX 16u
#define BM_CAMERA_FINISH_POSES_SERVED 1u    /* platform 0.1.9: one static pose a race (probe PR-D) */
#define BM_CAMERA_FINISH_RADIUS_M 40.0f     /* the pose distance bound from the game's outro camera (probe PR-D) */
#define BM_CAMERA_HOLD_MIN_S 0.5f
#define BM_CAMERA_HOLD_MAX_S 10.0f

enum {
    BM_CAMERA_OK           = 0,
    BM_CAMERA_BAD_ARG      = 1,     /* no host / out, out->struct_size below 8 */
    BM_CAMERA_OUT_OF_RANGE = 2,     /* not 70..140: refused, nothing changes */
    BM_CAMERA_BUSY         = 3,     /* another plugin owns the scale */
    BM_CAMERA_NOT_OWNER    = 4,     /* release: this plugin does not own it */
    BM_CAMERA_UNAVAILABLE  = 5,     /* this build's camera set-up hook is not in the generated code (v2: or the feature) */
    /* version 2 */
    BM_CAMERA_WRONG_THREAD = 6,     /* reserved (not returned in version 2: every v2 call takes any thread) */
    BM_CAMERA_NOT_IN_RACE  = 7      /* set_finish_poses outside a one-player race stage */
};

typedef struct bm_camera_state {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t available;             /* 1: the set-up hook is in this build */
    uint32_t stage_active;          /* 1: a one-player stage was set up with the hook since the last front-end set-up */
    uint32_t setups;                /* one-player stage camera set-ups seen so far (process) */
    float    game_fov;              /* the game's factor at the last set-up (before the scale; after display.ultrawide) */
    float    game_aspect;           /* the viewport aspect the game stored at the last set-up */
    float    applied_fov;           /* the factor stored at the last stage set-up (game_fov x applied_scale / 100) */
    uint32_t applied_scale;         /* per cent used at the last stage set-up (100 when none) */
    uint32_t requested_scale;       /* per cent the next stage set-up will use */
    uint32_t owned;                 /* 1: some plugin owns the scale */
    uint32_t yours;                 /* 1: you own it */
    uint32_t crash_camera;          /* 1: player 1's crash / takedown camera is on now (0 outside a stage) */
    /* ---- version 2 (struct_size covers them on a v2 host) ---- */
    uint32_t chase_active;          /* 1: player 0's view was the chase camera at the last picture */
    float    applied_roll_rad;      /* the roll used for the last picture (0 when none) */
    uint32_t adjust_owned;          /* 1: some plugin owns the adjust */
    uint32_t adjust_yours;          /* 1: you own it */
    uint32_t finish_active;         /* 1: the host shows authored finish poses now */
    /* ---- version 3 ---- */
    uint32_t free_active;           /* 1: the last picture showed the free pose */
    uint32_t free_owned;            /* 1: some plugin owns the free camera */
    uint32_t free_yours;            /* 1: you own it */
    uint32_t view;                  /* BM_CAMERA_VIEW_* at the last picture */
    /* ---- version 4 (main21 patch 96): player 0's last race-view picture AS DRAWN (any view: chase with the adjust, the free
     * pose, a finish pose). Project a world point p with these, not with applied_fov / CAMERA_FINAL: d = p - picture_pos;
     * z = d . picture_fwd (> 0 in front); x = (d . picture_right) / (z * picture_half_w), y = (d . picture_up) / (z * picture_half_h)
     * in -1..1 (RenderWare: picture_right points to the picture's LEFT). */
    uint32_t picture_seq;           /* pictures recorded this run (0: none yet) */
    float    picture_half_w;        /* the view window's half-width at distance 1 = tan(the game's per-picture angle, boost
                                     * included) x the stage factor; 0 when none */
    float    picture_half_h;        /* half-height (picture_half_w / the stage aspect) */
    float    picture_pos[3], picture_right[3], picture_up[3], picture_fwd[3];   /* the picture's final camera, metres */
} bm_camera_state;                  /* 48 bytes (v1), 68 (v2), 84 (v3), 144 (v4) */

/* version 3: a free camera pose (world frame, metres) */
typedef struct bm_camera_free {
    uint32_t struct_size;           /* sizeof (bm_camera_free) = 44 */
    float pos[3];                   /* the camera's position; within BM_CAMERA_FREE_RADIUS_M of player 1's car */
    float at[3];                    /* a point it looks at (!= pos) */
    float up[3];                    /* an up direction (not parallel to at - pos; need not be unit) */
    float fov_scale;                /* 0.7 .. 1.4 of the game's field of view */
} bm_camera_free;

/* version 2: the chase-camera adjust level */
typedef struct bm_camera_adjust {
    uint32_t struct_size;           /* sizeof (bm_camera_adjust) = 32 */
    float roll_rad, pitch_rad, yaw_rad;   /* |roll| <= 0.35, |pitch|, |yaw| <= 0.17; roll turns the right axis toward up */
    float offset_m[3];              /* camera frame: x right, y up, z forward; |each| <= 2.0 */
    float smoothing_s;              /* 0 .. 1: host exponential smoothing of level changes (time constant; 0 = none) */
} bm_camera_adjust;

/* version 2: an authored finish pose */
typedef struct bm_camera_pose {
    uint32_t struct_size;           /* sizeof (bm_camera_pose) = 36 */
    float pos_m[3], at_m[3];        /* relative to the finishing car (x right, y up, z forward); |each| within the radius; pos != at */
    float fov_scale;                /* 0.7 .. 1.4 (of the game's field of view) */
    float hold_s;                   /* 0.5 .. 10 */
} bm_camera_pose;

typedef struct bm_camera_api {
    uint32_t struct_size;           /* sizeof (bm_camera_api) as built */
    uint32_t version;               /* BM_CAMERA_VERSION */
    /* Ask for a field-of-view scale (per cent) from the next one-player stage set-up on. */
    int32_t (TD_CALL *set_fov_scale)(td_host *host, uint32_t percent);
    /* Give the scale back: the game's own (100) from the next set-up; another plugin may take it. */
    int32_t (TD_CALL *release)(td_host *host);
    /* What the host knows of the camera into *out (set out->struct_size). Any thread. */
    int32_t (TD_CALL *state)(td_host *host, bm_camera_state *out);
    /* ---- version 2 ---- */
    /* Hold the chase-camera adjust level (any thread; taken at the next picture). The first caller owns it (others: BUSY).
     * OUT_OF_RANGE (nothing changes) outside the bounds; UNAVAILABLE where the build cannot tell the chase camera. */
    int32_t (TD_CALL *set_adjust)(td_host *host, const bm_camera_adjust *a);
    /* Give the adjust back (the level returns to 0); NOT_OWNER when another plugin owns it. */
    int32_t (TD_CALL *release_adjust)(td_host *host);
    /* The finish poses for the race in play (any thread; one owner = the adjust's rule, its own owner). n = 0 clears.
     * OUT_OF_RANGE (nothing changes) when a pose breaks a bound or n > BM_CAMERA_FINISH_POSES_MAX; NOT_IN_RACE outside a
     * one-player race stage; UNAVAILABLE where the build cannot tell the end-of-race camera. */
    int32_t (TD_CALL *set_finish_poses)(td_host *host, const bm_camera_pose *poses, uint32_t n);
    /* ---- version 3 (check version >= 3 / struct_size before calling) ---- */
    /* Take / renew the free camera (see above). OK, BAD_ARG, OUT_OF_RANGE, BUSY, NOT_IN_RACE, UNAVAILABLE. */
    int32_t (TD_CALL *set_free_pose)(td_host *host, const bm_camera_free *f);
    /* End it now (the game's camera from the next picture). NOT_OWNER when another plugin owns it. */
    int32_t (TD_CALL *release_free)(td_host *host);
} bm_camera_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_CAMERA_H */
