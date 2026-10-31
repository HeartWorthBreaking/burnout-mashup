/*
 * bmashup_racers.h - the "bmashup.racers" service: Burnout Mashup's private, experimental READ-ONLY queries about the racers
 * of the race in play (Burnout Mashup builds only; may change or go away). Every field is one the game's own code was
 * verified to use that way (G8-E6 / E2 / E2M evidence, cited in docs); nothing else is exposed, and no address.
 *
 *   racer index  - the race's list (count 0x73A19C, list 0x73A1A8; at most 8), as bmashup.events / bmashup.route
 *   takedowns    - the racer's takedowns this race (the counter the game increments in sub_00198E60; launch 27: equal to
 *                  the results screen's TAKEDOWNS)
 *   wrecked      - 1 while the game marks the car wrecked (set by sub_0018C7D0 / sub_0018E010, cleared by sub_0018C820 /
 *                  sub_0018E040)
 *   boost / boost_max - the boost bar and its maximum (the game's boost add sub_0017A530 adds to the bar and caps it at the
 *                  maximum; the meter is the car's + 0x119C at every award site seen at runtime)
 *
 * Call on the game's thread (a bmashup.events callback, or takedawn.race's update); outside a race `count` is 0.
 *
 * Version 2 (platform 0.1.8, hook request P1; append-only, v1 unchanged - still READ ONLY):
 *   bm_racer_info grows: place, laps_done, race_time_s, phase, player, eliminated (read when your struct_size covers them);
 *   order() lists the racer indices in place order; session() the race's racer / player counts.
 *   Sources: the racer object R (the list entry): place = int16 R + 0x10D0, race time = float R + 0x10DC, laps done = R +
 *   0x10E4, phase = R + 0x134C (0 / 1 before the GO, 2 racing, 3 finished). These are takedawn.race's own player-1 fields
 *   (RUNTIME-VALIDATED for player 1); rivals are the same CB3PlayerCar class (the AI follower at R + 0x1A00 for every racer,
 *   bmashup.ai) but their values are PARTIAL until a census compares them with the results screen. A value outside its
 *   range is reported as 0 (place 0 = not ranked; phase 0xFFFFFFFF = unknown).
 *   player: 0 for player 1's car; 0xFFFFFFFF otherwise (split screen is not tested on the platform, so a second human car
 *   is not told apart from AI: R6). eliminated: always 0 in this version (bmashup.rules, phase 3).
 *   session(): mode and context are BM_MODE_UNKNOWN / BM_CONTEXT_UNKNOWN in this version (the event-type readers are RE
 *   items, phase 2); laps_total 0 = unknown.
 *
 * Version 3 (platform 0.1.9, hook request P2 item A; append-only, v1 / v2 unchanged):
 *   READS (bm_racer_info grows 52 -> 160 bytes; read when your struct_size covers them):
 *     gear          the gearbox's own gear (physics vehicle + 0x1448 + 0x80): -1 R, 0 N, 1 .. 6
 *     speed_mps     HOST-DERIVED for every racer: the distance the car's world position moved between two simulation steps /
 *                   1/60 s. (The speedometer's own HUD object read 0 at runtime: not used.)
 *     yaw_rate_rps, lat_accel_mps2, long_accel_mps2   HOST-DERIVED from the car's world matrix at successive steps (not game
 *                   fields): yaw + = turning left, lateral + = to the left, longitudinal + = forward. have_dynamics = 0 until
 *                   three successive steps were seen (after the race start, a respawn or a jump of more than 50 m).
 *     have_rpm / engine_rpm   main21 (patch 71): have_rpm = 1 and engine_rpm = the car's engine speed in rpm (the game's own
 *                             transmission state, kept in rad / s and converted by the host; idle ~1000, redline 7600 on the
 *                             retail cars), for every racer whose physics vehicle is found; 0 on hosts before main21, when the
 *                             game build's transmission code differs (census) or the value is implausible. Not yet seen in game.
 *     parts / part_kind / part_state   the car model's damage parts (count <= 32): kind 0..6 (names in the docs, PS2-derived),
 *                   state 0 intact, 1 damaged, 2 hanging, 3 flying, 4 removed (the game's byte).
 *     lights        bit (1 << BM_LIGHT_*) of what the car update set this step (the light flags the renderer tests: 0x04 / 0x02
 *                   head, 0x08 tail, 0x10 brake, 0x20 indicator left (group 5), 0x40 indicator right (group 6), 0x80 reverse
 *                   (REVERSE, main21 patch 95); a blinking
 *                   indicator reads on / off with its blink phase).
 *     controls_owned  bit (1 << BM_RACER_CTL_*) held by any plugin for this racer (the v3 controls).
 *   The dynamics are sampled once per simulation step at player 1's car update (the game's thread); get() returns the last
 *   sample. Everything here is read only.
 *   CONTROLS (separate functions; the v1 / v2 calls stay read only; each family has ONE owner per racer; everything is given
 *     back when a race is left or restarted; a call is recorded on any thread and carried out at player 1's next car update,
 *     on the game's thread):
 *     detach_part   the game's DetachBodyPart (sub_00125A50) for a part that is HANGING (state 2) - the game's own path, as the
 *                   Road Rage update does; any other state: NOT_HANGING (nothing called). Once per part per race (ALREADY).
 *                   Any racer: player 1's car at its next car update, an AI racer at the start of its own car update.
 *     set_light     ON / GAME / OFF per lamp, applied right after the game rebuilds the car's light flags each update, before
 *                   the draw (main21 patch 103: ON is ORed in there too; the racer byte the game ORs is cleared by the game's
 *                   own car update, so it is no longer written). OFF (main21 patch 77): the lamp stays dark whatever the game
 *                   sets (head = both beams, tail, brake, an indicator, HAZARD = both); OFF wins over ON. ON and OFF are
 *                   UNSUPPORTED on a host built with BO3_HOOKREQ_P7L=OFF or whose site differs (GAME is always accepted). ON / GAME / OFF of one lamp replace each other. Indicators IND_LEFT / IND_RIGHT / HAZARD (both): the host BLINKS them (about 1.5 Hz:
 *                   the bit is ORed in during the on phase, the host's own bit taken out in the off phase); accepted on any
 *                   racer, but LAMPS SHOW ONLY ON MODELS WITH LIGHT-GROUP 5 / 6 POINTS (lamp_counts(); the tested Compact
 *                   Type 1 has none). Left = group 5 (0x20), right = group 6 (0x40): the side is the renderer's group order.
 *                   <= BM_RACERS_LIGHT_CHANGES_PER_SECOND changes a second per racer (RATE; the host's blinking is not counted).
 *     light_available  bit (1 << BM_LIGHT_*) a racer's model can show: head / tail / brake, and IND_LEFT / IND_RIGHT when
 *                   the model has group 5 / 6 lamp points.
 *     lamp_counts   read only: the car model's indicator-lamp point counts (groups 5 / 6) - 0 = no lamp will show.
 *     award_score   CHANGES GAMEPLAY: adds to player 1's score total (the word the HUD SCORE counts up to and the results'
 *                   BURNOUT POINTS show): 1 .. BM_RACERS_SCORE_AWARD_MAX per award, per plugin 8 awards a second and 512 a
 *                   race (RATE), added at player 1's next car update; pending awards do not cross a race. Takedown counts and
 *                   takedown points are not changed.
 *     release       gives one family back now (lights go back to the game's own value at the next car update).
 *     result_text   a short name of a BM_RACERS_* code.
 *   (Light OFF: main21 patch 77, above.)
 *
 * Version 5 (main21 patch 98, open item 17; BO3_HOOKREQ_P28W - a host built without it answers version 4 and wreck UNSUPPORTED):
 *   wreck(racer, cause)  CHANGES GAMEPLAY: crashes the racer's car through the game's own crash entry (the physics vehicle's
 *                   class function that every contact crash ends in: the crash flag, the "crashed by" byte, the crash effects
 *                   and the racer's "enter wrecked" with its crash camera / respawn - all the game's code). Recorded on any
 *                   thread and carried out at player 1's next car update on the game's thread, only while the race is RACING,
 *                   the car is not already crashed or wrecked and the class's crash slot is the verified function.
 *                   cause BM_WRECK_CAUSE_NONE (or the racer itself) = nobody caused it (the game's own convention: the racer's
 *                   own index, as for a wall or a traffic crash); another racer index = that racer caused it (the game then
 *                   treats it like a takedown by that racer, including its takedown credit). One pending wreck per racer;
 *                   at most one wreck per racer every BM_RACERS_WRECK_GAP_STEPS steps (RATE). Not yet seen in game (probe).
 *                   main21 patch 101: the crash goes through the game's crash decider (as the game's own "nobody caused it"
 *                   crash), so the game mode, the crash record and a human racer's crash camera / respawn see it; a wreck caused
 *                   by another racer stages that racer's takedown as the game's blame does (the game's confirm counts it about
 *                   1 s later, unless the attacker is finished, crashed or wrecked by then).
 *
 * Version 6 (main21 patch 104, tail lamps option b; BO3_HOOKREQ_P8T - a host built without it answers version 5, or 4 without
 * wreck, and set_tail_stand_in is absent):
 *   set_tail_stand_in(racer, factor_permille)  LIGHTS family (the same owner as set_light). Some car models have no running-tail
 *                   lamp group (light group 1 empty, e.g. Compact Type 3), so set_light(TAIL, ON) shows nothing on them. With a
 *                   stand-in set, the running tail of such a model is drawn with its brake-lamp group (group 2) at the tail's
 *                   colour and the tail scale x factor (0.25 .. 1.0 of the tail size: about half the brake glow at 1.0). Only
 *                   when the tail is lit (set_light TAIL ON, or the game's) and not braking; models WITH a group 1 and the brake
 *                   lamp are unchanged; traffic is never touched. factor_permille 0 = off, 250 .. 1000 = on, else OUT_OF_RANGE.
 *                   Given back with the LIGHTS family (release / a new race). Counts as a light change (RATE).
 */
#ifndef BMASHUP_RACERS_H
#define BMASHUP_RACERS_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_RACERS_SERVICE "bmashup.racers"
#define BM_RACERS_VERSION 6u        /* 1: count / get; 2 (platform 0.1.8): + info place..eliminated, order, session;
                                     * 3 (platform 0.1.9): + dynamics / parts / lights reads, the controls;
                                     * 4 (main21 patch 81): + get_pose (world position and axes); 5 (main21 patch 98): + wreck;
                                     * 6 (main21 patch 104): + set_tail_stand_in */
#define BM_RACERS_VERSION_3 3u
#define BM_RACERS_VERSION_4 4u
#define BM_RACERS_VERSION_5 5u
#define BM_TAIL_STAND_IN_MIN 250u           /* set_tail_stand_in: factor in permille of the tail size (0 = off) */
#define BM_TAIL_STAND_IN_MAX 1000u
#define BM_WRECK_CAUSE_NONE (-1)            /* wreck(): nobody caused it */
#define BM_RACERS_WRECK_GAP_STEPS 180u      /* wreck(): one per racer in any 3 s (60 steps a second) */
#define BM_RACERS_MAX     8u        /* the race's list holds at most 8 */

enum { BM_RACERS_OK = 0, BM_RACERS_BAD_ARG = 1, BM_RACERS_NO_RACER = 2, BM_RACERS_UNAVAILABLE = 3,
       /* v2 (appended) */ BM_RACERS_NOT_IN_RACE = 4,
       /* v3 (appended) */ BM_RACERS_OUT_OF_RANGE = 5, BM_RACERS_CONFLICT = 6, BM_RACERS_NOT_OWNER = 7, BM_RACERS_UNSUPPORTED = 8,
       BM_RACERS_WRONG_THREAD = 9, BM_RACERS_RATE = 10, BM_RACERS_ALREADY = 11, BM_RACERS_NOT_HANGING = 12,
       BM_RACERS_NOT_PLAYER = 13 };

/* v3 */
enum { BM_LIGHT_GAME = 0, BM_LIGHT_OFF = 1, BM_LIGHT_ON = 2 };                            /* set_light state */
enum { BM_LIGHT_HEAD = 1, BM_LIGHT_TAIL = 2, BM_LIGHT_BRAKE = 3, BM_LIGHT_IND_LEFT = 4, BM_LIGHT_IND_RIGHT = 5,
       BM_LIGHT_HAZARD = 6 /* set_light only: both indicators */,
       BM_LIGHT_REVERSE = 7 /* main21 patch 95: the reverse lamp (flag 0x80, lit by the game in reverse gear); a host
                             * without it answers OUT_OF_RANGE / UNSUPPORTED and leaves bit 7 out of light_available */ };
#define BM_RACERS_BLINK_STEPS 40u     /* the host's indicator blink period in simulation steps (60 / s): 1.5 Hz, on 20, off 20 */
enum { BM_RACER_CTL_DAMAGE = 1, BM_RACER_CTL_LIGHTS = 2, BM_RACER_CTL_SCORE = 3 };       /* release(family), controls_owned */
#define BM_RACERS_PARTS_MAX 32u
#define BM_RACER_PART_NONE  0xFFu
#define BM_RACERS_LIGHT_CHANGES_PER_SECOND 10u
#define BM_RACERS_SCORE_AWARD_MAX 100000      /* per award; per plugin 8 / s, 512 / race (boost v2's model) */

/* v2: bm_racers_session.mode / .context (only UNKNOWN in platform 0.1.8; values reserved for the readers to come) */
enum { BM_MODE_UNKNOWN = 0, BM_MODE_RACE = 1, BM_MODE_ROAD_RAGE = 2, BM_MODE_ELIMINATOR = 3, BM_MODE_BURNING_LAP = 4,
       BM_MODE_FACE_OFF = 5, BM_MODE_CRASH = 6, BM_MODE_OTHER = 7 };
enum { BM_CONTEXT_UNKNOWN = 0, BM_CONTEXT_SINGLE_EVENT = 1, BM_CONTEXT_WORLD_TOUR = 2, BM_CONTEXT_MULTIPLAYER = 3,
       BM_CONTEXT_OTHER = 4 };
#define BM_RACER_NO_PLAYER 0xFFFFFFFFu
#define BM_RACER_PHASE_UNKNOWN 0xFFFFFFFFu

typedef struct bm_racer_info {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t index;                 /* the racer index asked for */
    uint32_t is_player1;            /* 1 for player 1's car */
    uint32_t takedowns;             /* this race */
    uint32_t wrecked;               /* 0 / 1 */
    float boost;                    /* the bar */
    float boost_max;                /* its maximum */
    /* ---- v2 (28 -> 52 bytes) ---- */
    int32_t  place;                 /* 1 = leading as the game ranks (1 .. 8); 0 = not ranked */
    uint32_t laps_done;
    float    race_time_s;           /* the racer's race time (0 when not finite / negative) */
    uint32_t phase;                 /* 0 / 1 before the GO, 2 racing, 3 finished; BM_RACER_PHASE_UNKNOWN otherwise */
    uint32_t player;                /* 0 = player 1's car; BM_RACER_NO_PLAYER otherwise (AI; split screen: R6) */
    uint32_t eliminated;            /* 0 (reserved for bmashup.rules) */
    /* ---- v3 (52 -> 160 bytes) ---- */
    uint32_t have_dynamics;         /* 1: speed / derived values valid (three successive steps seen) */
    int32_t  gear;                  /* -1 R, 0 N, 1..6 (the gearbox's own field) */
    float    speed_mps;             /* host-derived for every racer (see the header comment) */
    float    yaw_rate_rps;          /* host-derived, + = turning left */
    float    lat_accel_mps2;        /* host-derived, car frame, + = to the left */
    float    long_accel_mps2;       /* host-derived, + = forward */
    uint32_t have_rpm;              /* 1: engine_rpm is the engine speed (main21 patch 71; 0 on earlier hosts) */
    float    engine_rpm;
    uint32_t parts;                 /* damage parts of the car's model (<= BM_RACERS_PARTS_MAX) */
    uint8_t  part_kind[32];         /* 0..6 game kinds, BM_RACER_PART_NONE past `parts` */
    uint8_t  part_state[32];        /* 0 intact, 1 damaged, 2 hanging, 3 flying, 4 removed; BM_RACER_PART_NONE past `parts` */
    uint32_t lights;                /* bit (1 << BM_LIGHT_*) the car shows this step */
    uint32_t controls_owned;        /* bit (1 << BM_RACER_CTL_*) held by any plugin for this racer */
} bm_racer_info;                    /* 160 bytes */

/* v4: a racer's pose (get_pose) */
typedef struct bm_racer_pose {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t index;                 /* the racer asked for */
    float    pos[3];                /* the car's position (its matrix + 0x30), metres */
    float    fwd[3];                /* its forward axis (matrix + 0x20), unit */
    float    up[3];                 /* its up axis (+ 0x10) */
    float    right[3];              /* its right axis (+ 0x00; RenderWare's handedness: probe R22 checks the side) */
} bm_racer_pose;                    /* 56 bytes */
typedef struct bm_racers_session {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t in_race;               /* 1: the race's list has racers (the rest means something) */
    uint32_t mode;                  /* BM_MODE_* (UNKNOWN in platform 0.1.8) */
    uint32_t context;               /* BM_CONTEXT_* (UNKNOWN in platform 0.1.8) */
    uint32_t players;               /* human players: 1 when player 1's car is in the list (split screen: R6), else 0 */
    uint32_t racers;                /* = count() */
    uint32_t laps_total;            /* 0 = unknown (no verified reader yet) */
} bm_racers_session;                /* 28 bytes */

typedef struct bm_racers_api {
    uint32_t struct_size;
    uint32_t version;
    uint32_t (TD_CALL *count)(td_host *host);                                  /* racers in the race's list, 0 outside */
    int32_t (TD_CALL *get)(td_host *host, uint32_t index, bm_racer_info *out);
    /* ---- v2 (read only when version >= 2 and struct_size covers them) ---- */
    /* The racer indices in place order, leader first (ranked racers by place, then unranked ones by index). *n in = the
     * room of order[], out = indices written (at most count()). BM_RACERS_OK, BAD_ARG, NOT_IN_RACE (count() is 0),
     * UNAVAILABLE (a racer's car not readable). */
    int32_t (TD_CALL *order)(td_host *host, uint32_t *order, uint32_t *n);
    /* The race's session (set out->struct_size first). BM_RACERS_OK (in_race 0 outside a race) or BAD_ARG. */
    int32_t (TD_CALL *session)(td_host *host, bm_racers_session *out);
    /* ---- v3 (read only when version >= 3 and struct_size covers them) ---- */
    /* detach_part: OK (recorded), BAD_ARG, NOT_IN_RACE, NO_RACER, OUT_OF_RANGE (part), NOT_HANGING, ALREADY, CONFLICT (another
     *   plugin owns DAMAGE of this racer), UNSUPPORTED (the build's sites differ). */
    int32_t (TD_CALL *detach_part)(td_host *host, uint32_t racer, uint32_t part);
    /* set_light: OK, BAD_ARG, OUT_OF_RANGE (light / state), UNSUPPORTED (ON / OFF without the patch-77 site, the sites differ), CONFLICT, RATE,
     *   NOT_IN_RACE, NO_RACER. Indicators (IND_LEFT / IND_RIGHT / HAZARD) blink; see lamp_counts(). */
    int32_t (TD_CALL *set_light)(td_host *host, uint32_t racer, uint32_t light, uint32_t state);
    uint32_t (TD_CALL *light_available)(td_host *host, uint32_t racer);
    /* award_score(player, amount): NOT_PLAYER, UNSUPPORTED (player 1 = split screen), OUT_OF_RANGE (amount outside
     *   1 .. BM_RACERS_SCORE_AWARD_MAX), RATE, NOT_IN_RACE (no race / player 1 not in the list). */
    int32_t (TD_CALL *award_score)(td_host *host, uint32_t player, int32_t amount);
    /* release: OK, NOT_OWNER, OUT_OF_RANGE (family), NO_RACER. */
    int32_t (TD_CALL *release)(td_host *host, uint32_t racer, uint32_t family);
    const char *(TD_CALL *result_text)(int32_t code);
    /* lamp_counts (main19 patch 49, appended): the racer's model's light-group 5 / 6 point counts (the renderer's indicator
     * lamps; 0 = that lamp will not show). OK, BAD_ARG, NO_RACER, UNAVAILABLE (the model is not readable now). Any thread. */
    int32_t (TD_CALL *lamp_counts)(td_host *host, uint32_t racer, uint32_t *group5, uint32_t *group6);
    /* ---- v4 (main21 patch 81; read only when version >= 4 and struct_size covers it) ---- */
    /* the racer's car in the race world (the game's frame, metres): position and unit axes from its world matrix, as the game
     * last wrote it (about once a picture). Any thread; a copy. NO_RACER / UNAVAILABLE (not finite / unreadable). For labels
     * over cars: project with bmashup.hooks CAMERA_FINAL's cam_pos / cam_right / cam_up / cam_fwd and bmashup.camera state()'s
     * applied_fov / game_aspect (the factor is the horizontal view-window half-width, the vertical one factor / aspect;
     * HUD x = 320 - 320 x (d.right / d.fwd) / factor, y = 240 - 240 x (d.up / d.fwd) / (factor / aspect): cam_right points
     * to the picture's LEFT (RenderWare; main21 probe S4 showed labels mirrored with +), y's sign: probe R22). Example:
     * kitdocs\examples\bm-ai-names. */
    int32_t (TD_CALL *get_pose)(td_host *host, uint32_t racer, bm_racer_pose *out);
    /* ---- v5 (main21 patch 98; call only when version >= 5) ---- */
    /* wreck: OK (recorded), BAD_ARG, NOT_IN_RACE (no race / not RACING), NO_RACER, OUT_OF_RANGE (cause not NONE and not a racer
     *   index), ALREADY (a wreck of this racer is pending, or the car is crashed / wrecked now), RATE, UNSUPPORTED (a host without
     *   it, or the build's crash sites differ). The apply re-checks everything; a refusal there is logged ([RACERS] wreck). */
    int32_t (TD_CALL *wreck)(td_host *host, uint32_t racer, int32_t cause);
    /* ---- v6 (main21 patch 104; call only when version >= 6) ---- */
    /* set_tail_stand_in: OK, BAD_ARG, OUT_OF_RANGE (factor not 0 and not 250 .. 1000), UNSUPPORTED (a host without the mark, or its
     *   site differs), CONFLICT (another plugin owns LIGHTS of this racer), RATE, NOT_IN_RACE, NO_RACER. OK also on a model that has
     *   a group 1 (nothing changes there). */
    int32_t (TD_CALL *set_tail_stand_in)(td_host *host, uint32_t racer, uint32_t factor_permille);
} bm_racers_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_RACERS_H */
