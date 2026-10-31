/*
 * bmashup_hooks.h - the "bmashup.hooks" service: Burnout Mashup's private, experimental coordinated hook points for native
 * plugins (Burnout Mashup builds only; may change or go away). Contract: research\native_gameplay_api\platform\hooks\
 * CONTRACTS.md.
 *
 * A hook point is a NAMED place in the game's code where this build already carries a verified mark (one generated line,
 * placed by an anchored apply script and checked by a relocation audit). The service publishes those points by number and
 * name; a plugin never gives or gets a code address. The game is statically recompiled C: there are no run-time trampolines,
 * so a point that is not in the table below cannot be hooked by any plugin - new points need a new mark in a new build.
 *
 * Rules (version 1):
 *   - register only while Takedawn starts the plugins (takedawn_plugin_init / takedawn_plugin_service); then CLOSED;
 *   - roles: OBSERVE at every point (a read-only copy of the point's values); MODIFY only where the point declares an output
 *     (BOOST_AWARD: the amount) - the plugin proposes a value, the service validates it, nothing else is writable;
 *   - order at one occurrence: MODIFY callbacks, then OBSERVE callbacks; within a role ascending `priority`
 *     (-1000 .. 1000), equal priorities in registration order; bmashup.events subscribers of the same point run first
 *     (its modifiers before these modifiers, its observers before these observers);
 *   - ownership: one registration per plugin, point and role (a second: ALREADY); BM_HOOK_EXCLUSIVE asks to be the only
 *     registration of that point and role: refused (CONFLICT) when another plugin is registered there, and every later
 *     registration there by another plugin is refused (CONFLICT, the log names the owner);
 *   - every callback has the guest's registers, the x87 state and the flag words saved before and put back after
 *     (a change is counted against the registration: register_faults);
 *   - an occurrence reached while a bmashup.hooks callback runs (re-entry) is not dispatched to the hooks (counted);
 *   - nothing is dispatched once the process starts to exit;
 *   - plugins are never unloaded (Takedawn's loader has no unload): registrations last for the process, there is no
 *     unregister.
 *
 * Version 2 (platform 0.1.8; append-only, every v1 rule unchanged):
 *   - point 7 CRASH_RESULT (OBSERVE): a Crash junction attempt was scored - the same occurrence as bmashup.events v6's
 *     BM_EVENT_CRASH_RESULT (the crash1 mark in sub_0001EE80, the game's record step), delivered after bmashup.events'
 *     subscribers (the events-first rule above). Hook points keep bmashup.events' numbering;
 *   - bm_hook_ctx grows at its end (the v2 fields below; struct_size says which a host filled): `player` and the
 *     CRASH_RESULT values; points that do not fill a field leave it 0;
 *   - a v1 plugin (built with BM_HOOK_POINTS = 6) sees no change: it never names point 7 and reads only the v1 prefix of
 *     bm_hook_ctx. BM_HOOK_POINTS keeps its v1 value; BM_HOOK_POINTS_V2 is the last point of version 2;
 *   - not in version 2 (later phases of the hook request, each with its own version): HUD_PASS, CAMERA_FINAL,
 *     TRAFFIC_CONTACT, WRECK_CAUSE, EVENT_SOUND, FINISH_CAMERA (points 8..13 are reserved for them; registering there is
 *     UNKNOWN_POINT on a v2 host).
 *
 * Version 3 (platform 0.1.9, hook request P2 / P3; append-only, every v1 / v2 rule unchanged): points 8..13. Numbers equal
 * bmashup.events' kinds where an events twin exists (8, 10, 11, 12); 9 and 13 are hooks-only (per-picture camera math). Each new
 * MODIFY point has ONE typed output (bm_hook_out grows); an invalid output is ignored (the value so far stays) and counted
 * (stats.rejected), never clamped. A MODIFY callback gets `out` prefilled with the value so far and proposes the new value.
 *   8  HUD_PASS        OBSERVE, once a picture while a race HUD is drawn (player 0). The ONLY place bmashup.hud draw() is
 *                      taken. Keep callbacks < 0.1 ms.
 *   9  CAMERA_FINAL    MODIFY CAMERA_ADJUST, once a picture, player 0's chase view only (never crash / takedown / look-back /
 *                      replay / front end / split screen). Applied to a COPY of this picture's view (nothing written back).
 *   10 TRAFFIC_CONTACT MODIFY CONTACT_OUTCOME, when a racer-vs-traffic contact is about to become a traffic crash. GAME keeps
 *                      the game's decision; NO_CRASH makes this contact non-fatal (the game's own non-fatal response runs).
 *                      main21 patch 110: before it, NO_CRASH only kept the push - the class-pair crash still ran (probe R20);
 *                      a host built with BO3_HOOKREQ_ZNC (default) now also skips that crash for the answered contact.
 *                      Accepted only for same-direction traffic below BM_HOOK_CONTACT_MAX_MPS closing speed.
 *                      main21 patch 116: the bound 25 -> 60 m/s. The game offers a contact only above its own threshold
 *                      (75 in its closing metric = about 33.5 m/s in a race), so with 25 no NO_CRASH could ever be accepted.
 *                      main21 (patch 79): + out->push_scale 0 .. 1 with NO_CRASH: x the game's push FORCE on the racer's car in
 *                      that contact's non-fatal response (the force along the contact normal at the contact point, mass-capped;
 *                      prefilled 1.0; 0 = no push; outside 0 .. 1 or NaN rejects the proposal). The traffic car's own reaction is
 *                      the traffic system's and is not changed. Not applied on a host built with BO3_HOOKREQ_P9C=OFF or whose
 *                      push site differs (NO_CRASH still is). Check out->struct_size before using the field.
 *   11 WRECK_CAUSE     OBSERVE (+ MODIFY WRECK_CREDIT only where the platform's credit path is verified; else the MODIFY role
 *                      is not offered: BAD_ROLE): a takedown is about to be counted (aggressor, victim).
 *   12 EVENT_SOUND     MODIFY SOUND_LEVEL: the takedown-sign sound's pitch LEVEL 0..4 (the game's own five-step pitch ladder,
 *                      1.0 .. 1.414 x); sound catalogue: BM_SOUND_TAKEDOWN only in this version. No new voice is played.
 *                      main21 (patch 78): + out->sound_pitch, a free factor BM_HOOK_SOUND_PITCH_MIN .. MAX on the pitch of the
 *                      level (prefilled 1.0; 0 or 1.0 = none; finite; outside the bounds the whole proposal is rejected). The host has the field
 *                      when out->struct_size covers it; on a host built with BO3_HOOKREQ_P8P=OFF, or whose pitch sites differ,
 *                      the factor is accepted but not applied (the level still is).
 *   13 FINISH_CAMERA   MODIFY FINISH_CAMERA, once a picture while player 0's end-of-race camera runs: keep the game's camera
 *                      or give a pose (bounded, near the finishing car); applied to a COPY of the view, as 9.
 *   A point whose mark is not in this build (or whose start-time check of the game's bytes failed, or a build made with
 *   BO3_HOOKREQ_P23=OFF) is UNAVAILABLE: point_info().available = 0 and registering there answers BM_HOOKS_UNAVAILABLE.
 *   point_info().roles names the roles offered in this run. BM_HOOK_POINTS and BM_HOOK_POINTS_V2 keep their values;
 *   BM_HOOK_POINTS_V3 = 13.
 */
#ifndef BMASHUP_HOOKS_H
#define BMASHUP_HOOKS_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_HOOKS_SERVICE "bmashup.hooks"
#define BM_HOOKS_VERSION 3u             /* 1: points 1..6; 2: + point 7 CRASH_RESULT, bm_hook_ctx v2 fields; 3: + points 8..13 */
#define BM_HOOKS_VERSION_1 1u
#define BM_HOOKS_VERSION_2 2u
#define BM_HOOKS_VERSION_3 3u

/* Published points (version 1). The values each point fills in are listed in CONTRACTS.md; fields a point does not fill
 * are 0 (racer fields BM_HOOK_NO_RACER). */
enum {
    BM_HOOK_PLAYER_CAR_UPDATE = 1,      /* player 1's car is about to run its update (mark "ap_update", dispatcher) */
    BM_HOOK_LOAD_DONE         = 2,      /* the game finished a load (lifecycle marks, sub_001AA100) */
    BM_HOOK_RACE_EXIT         = 3,      /* a race is being left (lifecycle marks, sub_001AA990 / sub_0018B250) */
    BM_HOOK_TAKEDOWN          = 4,      /* the game counted a takedown (sub_00198E60 marks) */
    BM_HOOK_WRECK             = 5,      /* a car became wrecked (sub_0018C7D0 / sub_0018E010 marks) */
    BM_HOOK_BOOST_AWARD       = 6,      /* the game's boost add is entered (sub_0017A530 entry mark); MODIFY: the amount */
    BM_HOOK_POINTS            = 6,      /* the last point of VERSION 1 (kept: v1 plugins were built with it) */
    /* version 2 */
    BM_HOOK_CRASH_RESULT      = 7,      /* a Crash junction attempt was scored (crash1 mark, sub_0001EE80) = bmashup.events'
                                           BM_EVENT_CRASH_RESULT. OBSERVE only */
    BM_HOOK_POINTS_V2         = 7,      /* the last point of version 2 */
    /* version 3 (each UNAVAILABLE unless point_info().available says so) */
    BM_HOOK_HUD_PASS          = 8,      /* OBSERVE: once a picture while the race HUD is drawn (player 0) = events' HUD_PASS */
    BM_HOOK_CAMERA_FINAL      = 9,      /* MODIFY CAMERA_ADJUST (+ OBSERVE): player 0's chase view, a copy per picture */
    BM_HOOK_TRAFFIC_CONTACT   = 10,     /* MODIFY CONTACT_OUTCOME (+ OBSERVE): a racer-vs-traffic contact about to be fatal */
    BM_HOOK_WRECK_CAUSE       = 11,     /* OBSERVE (+ MODIFY WRECK_CREDIT when offered): a takedown about to be counted */
    BM_HOOK_EVENT_SOUND       = 12,     /* MODIFY SOUND_LEVEL (+ OBSERVE): the takedown-sign sound's pitch level */
    BM_HOOK_FINISH_CAMERA     = 13,     /* MODIFY FINISH_CAMERA (+ OBSERVE): player 0's end-of-race camera, a copy per picture */
    BM_HOOK_POINTS_V3         = 13      /* the last point of version 3 */
};
enum { BM_SOUND_TAKEDOWN = 1 };                     /* v3: EVENT_SOUND's sound catalogue */
enum { BM_CONTACT_GAME = 0, BM_CONTACT_NO_CRASH = 1 };  /* v3: CONTACT_OUTCOME */
#define BM_HOOK_CONTACT_MAX_MPS 60.0f       /* v3: closing-speed bound (m/s) for NO_CRASH (main21 patch 116: was 25) */
#define BM_HOOK_CREDIT_WINDOW_S 3.0f        /* v3: WRECK_CREDIT: the credited racer touched the victim within this time */
#define BM_HOOK_CAM_MAX_ROLL    0.35f       /* v3: CAMERA_ADJUST bounds (radians, metres) */
#define BM_HOOK_CAM_MAX_PITCH   0.17f
#define BM_HOOK_CAM_MAX_YAW     0.17f
#define BM_HOOK_CAM_MAX_OFFSET  2.0f
#define BM_FINISH_CAMERA_GAME 0u            /* v3: FINISH_CAMERA */
#define BM_FINISH_CAMERA_POSE 1u
#define BM_HOOK_FOV_SCALE_MIN 0.7f
#define BM_HOOK_FOV_SCALE_MAX 1.4f

enum { BM_HOOK_OBSERVE = 1, BM_HOOK_MODIFY = 2 };

#define BM_HOOK_EXCLUSIVE    0x00000001u    /* reg.flags: the only registration of this point and role */
#define BM_HOOK_PRIORITY_MIN (-1000)
#define BM_HOOK_PRIORITY_MAX 1000
#define BM_HOOK_NO_RACER     0xFFFFFFFFu
#define BM_HOOK_MAX_PER_ROLE 16             /* registrations per point and role */

/* Results. */
enum {
    BM_HOOKS_OK            = 0,
    BM_HOOKS_BAD_ARG       = 1,     /* no host / reg / fn / id, reg->struct_size too small, priority out of range */
    BM_HOOKS_UNKNOWN_POINT = 2,
    BM_HOOKS_BAD_ROLE      = 3,     /* this point does not offer that role (MODIFY needs a declared output) */
    BM_HOOKS_BAD_FLAGS     = 4,     /* a flag this version does not know */
    BM_HOOKS_CLOSED        = 5,     /* the plugins' start is over: lists are fixed */
    BM_HOOKS_UNAVAILABLE   = 6,     /* the point is not hooked in this run (RECOMP_DEBUG=autopilot holds the car update) */
    BM_HOOKS_ALREADY       = 7,     /* this plugin has a registration at this point and role */
    BM_HOOKS_CONFLICT      = 8,     /* an exclusive registration of another plugin, or exclusive asked where others are */
    BM_HOOKS_FULL          = 9,     /* BM_HOOK_MAX_PER_ROLE reached */
    BM_HOOKS_NOT_OWNER     = 10     /* stats of a registration this plugin does not own */
};

/* A MODIFY callback's return. */
enum { BM_HOOK_KEEP = 0, BM_HOOK_CHANGE = 1 };

/* What a callback is given: a copy made for this call (Takedawn's, valid during the call only; writing it changes nothing). */
typedef struct bm_hook_ctx {
    uint32_t struct_size;           /* the size Takedawn filled in */
    uint32_t point;                 /* BM_HOOK_* */
    uint32_t role;                  /* BM_HOOK_OBSERVE / BM_HOOK_MODIFY */
    uint32_t sequence;              /* the point's occurrence count: the same for every callback of one occurrence */
    uint32_t step;                  /* the game's simulation step (MEM32(0x4A1EB4)), 0 before the game has one */
    /* PLAYER_CAR_UPDATE */
    float    race_time_s;           /* player 1's race time */
    uint32_t car_phase;             /* 0 / 1 before the GO, 2 racing, 3 finished */
    /* LOAD_DONE / RACE_EXIT (the bmashup.events v2 values) */
    uint32_t load_kind;             /* BM_LOAD_* of bmashup_events.h */
    uint32_t track_loads;
    uint32_t race_exits;
    uint32_t lanes;
    uint32_t racers;
    /* TAKEDOWN / WRECK */
    uint32_t actor;                 /* racer index or BM_HOOK_NO_RACER */
    uint32_t victim;
    uint32_t kind;                  /* TAKEDOWN: BM_TAKEDOWN_* of bmashup_events.h */
    uint32_t actor_takedowns;
    /* BOOST_AWARD */
    uint32_t recipient;             /* racer index or BM_HOOK_NO_RACER */
    uint32_t award_source;          /* BM_BOOST_* of bmashup_events.h */
    uint32_t award_site;            /* the game's call site (a code address naming the award; 0 = a host service's add) */
    float    award_requested;       /* what the game asked for */
    float    award_amount;          /* the amount so far (after bmashup.events modifiers and the earlier hook modifiers) */
    uint32_t award_modified;        /* 1 when a modifier changed the amount before this call */
    /* ---- version 2 (struct_size covers them on a v2 host) ---- */
    uint32_t player;                /* the player a per-view point belongs to (0 / 1); 0 for points that are not per view
                                       (CRASH_RESULT: 0 - the game's record step is one per event, also in two-player Crash
                                       where crash_mode says the two totals were added) */
    /* CRASH_RESULT (= bmashup.events v6's values) */
    uint32_t crash_junction;        /* the junction (0..99, bmashup.crash numbering) or BM_HOOK_NO_JUNCTION */
    uint32_t crash_score;           /* the total the game records for it */
    uint32_t crash_mode;            /* BM_CRASH_MODE_* of bmashup_events.h */
    char     crash_junction_id[16]; /* the junction's game ID, NUL-terminated */
    char     crash_track_id[16];    /* the track's ID, NUL-terminated */
    /* ---- version 3 (struct_size covers them on a v3 host; a point fills its group, the others are 0) ---- */
    /* HUD_PASS */
    uint32_t hud_visible;           /* 1: the title draws its HUD scenes this picture */
    float    frame_dt_s;            /* time since the last picture */
    /* CAMERA_FINAL / FINISH_CAMERA (copies; the race world frame; metres) */
    float    cam_pos[3], cam_right[3], cam_up[3], cam_fwd[3];
    float    car_speed_mps, car_yaw_rate_rps, car_lat_accel_mps2;   /* player 0's car (host-derived; 0 when not known) */
    float    finish_time_s;         /* FINISH_CAMERA: seconds since the outro camera started */
    /* TRAFFIC_CONTACT */
    uint32_t contact_racer;         /* racer index */
    uint32_t contact_traffic;       /* traffic handle (opaque, this occurrence only) */
    float    contact_closing_mps;   /* closing speed */
    uint32_t contact_same_dir;      /* 1 when the two cars move the same way */
    /* WRECK_CAUSE */
    uint32_t cause_aggressor;       /* racer index (the game's credit) or BM_HOOK_NO_RACER */
    uint32_t cause_victim;          /* racer index */
    /* EVENT_SOUND */
    uint32_t sound;                 /* BM_SOUND_* */
    uint32_t sound_level_game;      /* 0..4, the game's level */
    uint32_t sound_event;           /* the sign event (0x93, 0x9F..0xA6), for information */
} bm_hook_ctx;
#define BM_HOOK_NO_JUNCTION 0xFFFFFFFFu

/* The declared output of a MODIFY callback (BOOST_AWARD: the amount). Prefilled with the amount so far. Rules: finite,
 * 0 .. 16 x award_requested; otherwise ignored (the amount so far stays) and counted (stats.rejected). A host service's own
 * add (award_source BM_BOOST_HOST) is never modified (MODIFY callbacks are not called for it). */
typedef struct bm_hook_out {
    uint32_t struct_size;           /* the size Takedawn filled in */
    uint32_t output;                /* BM_HOOK_OUT_* */
    float    amount;
    /* ---- version 3: one group per output; the value so far is prefilled ---- */
    float    roll_rad, pitch_rad, yaw_rad;  /* CAMERA_ADJUST: |roll| <= 0.35, |pitch|, |yaw| <= 0.17 (the total) */
    float    offset_m[3];                   /* CAMERA_ADJUST: camera frame (right, up, forward), |each| <= 2.0 */
    uint32_t outcome;                       /* CONTACT_OUTCOME: BM_CONTACT_* */
    uint32_t credit_racer;                  /* WRECK_CREDIT: a racer that touched the victim within the window, or BM_HOOK_NO_RACER */
    uint32_t sound_level;                   /* SOUND_LEVEL: 0..4 */
    uint32_t finish_camera;                 /* FINISH_CAMERA: BM_FINISH_CAMERA_GAME / _POSE */
    float    pose_pos[3], pose_at[3];       /* FINISH_CAMERA POSE: world metres, near the finishing car; pos != at */
    float    pose_fov_scale;                /* FINISH_CAMERA POSE: 0.7 .. 1.4 */
    /* ---- main21 (appended): check out->struct_size before using ---- */
    float    sound_pitch;                   /* SOUND_LEVEL: x the level's pitch, BM_HOOK_SOUND_PITCH_MIN .. MAX (1.0 = none) */
    float    push_scale;                    /* CONTACT_OUTCOME NO_CRASH: x the game's push force on the racer, 0 .. 1 (patch 79) */
} bm_hook_out;
#define BM_HOOK_SOUND_PITCH_MIN 0.5f
#define BM_HOOK_SOUND_PITCH_MAX 2.0f
enum { BM_HOOK_OUT_BOOST_AMOUNT = 1, BM_HOOK_OUT_CAMERA_ADJUST = 2, BM_HOOK_OUT_CONTACT_OUTCOME = 3, BM_HOOK_OUT_WRECK_CREDIT = 4,
       BM_HOOK_OUT_SOUND_LEVEL = 5, BM_HOOK_OUT_FINISH_CAMERA = 6 };
#define BM_HOOK_MOD_MAX_FACTOR 16.0f

/* OBSERVE: out is NULL, the return is ignored. MODIFY: set out->amount and return BM_HOOK_CHANGE, or BM_HOOK_KEEP. */
typedef int32_t (TD_CALL *bm_hook_fn)(const bm_hook_ctx *ctx, bm_hook_out *out, void *user);

typedef struct bm_hook_reg {
    uint32_t   struct_size;         /* sizeof (bm_hook_reg) as the plugin built it */
    uint32_t   point;               /* BM_HOOK_* */
    uint32_t   role;                /* BM_HOOK_OBSERVE / BM_HOOK_MODIFY */
    uint32_t   flags;               /* BM_HOOK_EXCLUSIVE or 0 */
    int32_t    priority;            /* BM_HOOK_PRIORITY_MIN .. MAX; lower runs first */
    bm_hook_fn fn;
    void      *user;
} bm_hook_reg;

typedef struct bm_hook_stats {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t calls;                 /* times this registration was called */
    uint32_t changed;               /* MODIFY: times its value was used */
    uint32_t rejected;              /* MODIFY: times its value was invalid (ignored) */
    uint32_t register_faults;       /* times its call changed guest registers / flags (put back) */
} bm_hook_stats;

typedef struct bm_hook_point_info {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t point;
    char     name[32];              /* e.g. "BOOST_AWARD" */
    uint32_t roles;                 /* bit (1 << role) for each role offered */
    uint32_t available;             /* 1 when hooked in this run */
    uint32_t occurrences;           /* times the point reached the service */
    uint32_t reentered;             /* times it was reached inside a bmashup.hooks callback (not dispatched) */
    uint32_t after_stop;            /* times it was reached after the process started to exit (not dispatched) */
    uint32_t observers, modifiers;  /* registrations now */
    uint32_t exclusive_roles;       /* bit (1 << role) for each role held exclusively */
} bm_hook_point_info;

/* The service's table: valid until the process ends. */
typedef struct bm_hooks_api {
    uint32_t struct_size;           /* sizeof (bm_hooks_api) as built */
    uint32_t version;               /* BM_HOOKS_VERSION */
    /* Register reg->fn at reg->point in reg->role. While the plugins start only. *id: this registration (> 0). */
    int32_t (TD_CALL *register_hook)(td_host *host, const bm_hook_reg *reg, uint32_t *id);
    /* This plugin's counts for registration id into *out. Any thread. */
    int32_t (TD_CALL *stats)(td_host *host, uint32_t id, bm_hook_stats *out);
    /* The point's description and counters into *out. Any thread. */
    int32_t (TD_CALL *point_info)(td_host *host, uint32_t point, bm_hook_point_info *out);
    /* A result code as text ("CONFLICT", ...); Takedawn's string, valid until the process ends. */
    const char *(TD_CALL *result_text)(int32_t code);
} bm_hooks_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_HOOKS_H */
