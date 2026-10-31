/*
 * bmashup_vphysics.h - the "bmashup.vphysics" service: Burnout Mashup's private, experimental per-car physics query
 * and one bounded, reversible control (docs/bmashup-vphysics.md). Not a Takedawn service: offered only by Burnout
 * Mashup's own builds, through the optional export of takedawn_services.h; it may change or go away.
 *
 * What a car's physics values are (research: gp\atlas\PHYSICS.md):
 *   - each vehicle has a ValueDB file "../Export/ValueDB/VehiclePhysics/<car>.cfg" in Data/vdb.xml; when a car is set
 *     up for a race, the game registers 64 values of that file into a per-vehicle block (sub_00132D10) and COPIES all
 *     64 into the car object (two as cosines, two revs as rad/s) (sub_00134710); the car's physics step reads the car's copy;
 *   - so a value here has two readings: game_value (the vehicle's own ValueDB value, from the block) and current (the
 *     car's copy, the one the physics uses). Both are given in the ValueDB's units (a copy the game scales, e.g. revs
 *     to rad/s, is converted back).
 *
 * Query: any racer of the race in play (index as bmashup.racers: the game's racer list), any catalogue value.
 * Control (v1): set_scale() makes player 1's car use game_value x scale for one WRITABLE value, from player 1's next
 * car update on, in every race, until reset(); the scale is bounded per value (info().scale_min .. scale_max). Other
 * cars, the vehicle's ValueDB block and the game's data are never written. At each car update the service checks the
 * car's copy: still the game's value (the game copied it again, e.g. a reset) -> the scaled value is written again;
 * already the scaled value -> nothing; anything else (another writer) -> left alone and counted as contested. When a
 * race is left, or on reset(), the car's copy goes back to the game's value (only if it still holds the scaled one).
 * The writable values (catalogue names = the ValueDB keys, kept as the identifiers; GP-P4.2 documentation correction):
 *   "Physics/Race Car/Misc | Drag Coef"           drag coefficient, scale 0.25 .. 4;
 *   "Physics/Race Car/Misc | Max Speed In Boost"  the car's TOP-SPEED LIMIT, scale 0.5 .. 2: despite its ValueDB name it
 *                                                 caps the top speed in normal driving AND while boosting (runtime r2,
 *                                                 gp_p41g_2: x0.5 held the car at 80 mph with and without boost; the
 *                                                 retail value is above the unboosted top speed, so retail never shows
 *                                                 the cap outside a boost). A scale < 1 lowers the car's top speed.
 *
 * Ownership: one owner (plugin) per value; another plugin's set_scale / reset of it is refused (CONFLICT).
 * Threads: every call from any thread. get() reads single aligned words from the game while it runs: each value is
 * whole, two values are not from the same step. Writes happen only on the game's thread (the car update, or after an
 * update when a race is left).
 * Fail closed: an unknown game build, a car whose structure check fails (its block does not belong to its vehicle, or
 * the block's ValueDB file name is not a VehiclePhysics file) -> nothing is written, the status says why.
 *
 * Version 2 (platform 0.1.8, hook request P1 "handling outside a race" = the queued garage query; append-only, v1
 * unchanged): a READ-ONLY VEHICLE QUERY over the game's ValueDB as the game loaded it at boot (Data/vdb.xml, sub_001AF200),
 * in or out of a race, any thread, nothing written:
 *   vehicle_count / vehicle_info / vehicle_find   the vehicles that have a "../Export/ValueDB/VehiclePhysics/<NAME>.cfg"
 *       file in the loaded ValueDB's file table, NAME = <class>CAR<n> (class COMP CUPE HEVY HSPC MSCL SPRT SUPR TSPC TRAF,
 *       n 0..99), listed class by class, n ascending (NOT the garage's order). Retail: 100 vehicles.
 *   vehicle_value(vehicle, catalogue index)       the vehicle file's record for that catalogue value, looked up exactly as
 *       the game does (key = the game's hash of name + group + "/" + file, the game's signed binary search); game_value =
 *       the record; value = the same, in the ValueDB's units (the units of v1's get()); have = 0 when the file has no record
 *       for it (33 of the 100 files hold only mass + suspension: the game then keeps the block's previous content).
 *   Not in this version: [bmashup.cars] added cars (they use their donor's file: query the donor by name), scales of
 *   bmashup.tune / physics_scale (scaled = 0 always), the open / locked state (open = BM_VEH_OPEN_UNKNOWN always), and the
 *   gearbox controls of the draft (phase 2).
 *   UNAVAILABLE before the boot load or when the loaded ValueDB fails the structure check (registry object's apply
 *   function, record count / pointer, key table): nothing is guessed.
 *
 * Version 3 (platform 0.1.9, hook request P2 item A "gearbox"; append-only, v1 / v2 unchanged): the GEARBOX of player 1's car.
 *   CHANGES GAMEPLAY (label).
 *   set_gearbox(player, AUTO / MANUAL): the gearbox's own mode word (retail Xbox never sets MANUAL: the word has no writer in
 *     the build) is held at MANUAL from the car's next update in a race while the plugin owns it; the game's own manual path
 *     then shifts on the car's shift inputs. AUTO gives it back (the word goes back to 0 at the next car update).
 *   request_gear(player, gear): one shift toward `gear` per car update through the game's own up / down shift routines (never
 *     a raw gear write: the routines keep the shift timer and flag consistent); 1 .. max_gear only - neutral and reverse stay
 *     the game's: in MANUAL the car stops in N and reverse is the brake-hold path, as in AUTO. The request stays until the gear
 *     is reached, a new request replaces it, or the race ends.
 *   The host carries one mark in the gearbox update (active only while a plugin owns MANUAL on that car): the game's idle
 *     re-shift to neutral is skipped when the gear is already neutral (else the re-armed shift flag blocks reverse by brake -
 *     the PS2 mod's fix, here a host mark). idle_fix_skips counts it.
 *   Player 1's car only (`player` 0; 1 = split screen: UNSUPPORTED, R6). One owner (CONFLICT). Applied at the car update
 *   ("ap_update"); held again after a car reset; the owner and the request are dropped and the word goes back to AUTO when a
 *   race is left or restarted (set it again for the next race; a set before the race applies from its first car update).
 *   set_gearbox / request_gear may be called from any thread (they are carried out at the car update); gearbox_status any
 *   thread. UNSUPPORTED also when the build's gearbox sites fail the byte census at start (available = 0).
 */
#ifndef BMASHUP_VPHYSICS_H
#define BMASHUP_VPHYSICS_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_VPHYS_SERVICE "bmashup.vphysics"
#define BM_VPHYS_VERSION 3u         /* 1: catalogue / get / set_scale; 2 (platform 0.1.8): + the vehicle query;
                                     * 3 (platform 0.1.9): + the gearbox */

/* results */
enum {
    BM_VPHYS_OK           = 0,
    BM_VPHYS_BAD_ARG      = 1,      /* no host / out, out->struct_size below 8, an index out of range, a NaN */
    BM_VPHYS_UNAVAILABLE  = 2,      /* no race in play, or the racer's car is not readable now */
    BM_VPHYS_NOT_FOUND    = 3,      /* find(): no such name */
    BM_VPHYS_READ_ONLY    = 4,      /* set_scale / reset of a value that is not writable */
    BM_VPHYS_OUT_OF_RANGE = 5,      /* scale outside info().scale_min .. scale_max */
    BM_VPHYS_CONFLICT     = 6,      /* another plugin owns the value (set_scale / reset) or you do not (reset) */
    BM_VPHYS_NO_RACER     = 7,      /* get(): no such racer in the race in play */
    BM_VPHYS_UNSUPPORTED  = 8,      /* a game build or a car this service does not know: nothing read / written */
    BM_VPHYS_DEBUG_AUTOPILOT = 9,   /* RECOMP_DEBUG=autopilot holds the car update: the control stays off */
    /* v2 (appended) */
    BM_VPHYS_NO_VEHICLE   = 10,     /* vehicle_info / vehicle_value: no such vehicle index; vehicle_find: no such name */
    BM_VPHYS_NO_VALUE     = 11,     /* vehicle_value: the vehicle's file has no record for it (out filled, have = 0) */
    /* v3 (appended) */
    BM_VPHYS_NOT_PLAYER   = 12,     /* set_gearbox / request_gear / gearbox_status: player > 1 */
    BM_VPHYS_WRONG_MODE   = 13,     /* request_gear: the gearbox is not MANUAL by you */
    BM_VPHYS_WRONG_THREAD = 14,     /* (reserved; the v3 calls are accepted on any thread) */
    BM_VPHYS_BUSY_SHIFT   = 15      /* request_gear: a shift is in progress now: ask again */
};

/* v3: set_gearbox mode / bm_vphys_gearbox_status.mode */
enum { BM_GEARBOX_AUTO = 0, BM_GEARBOX_MANUAL = 1 };

/* v2: bm_vphys_vehicle_info.open */
enum { BM_VEH_OPEN_UNKNOWN = 0, BM_VEH_OPEN = 1, BM_VEH_LOCKED = 2 };
/* v2: bm_vphys_vehicle_info.series_class = the class of the file name (the index in this list) */
enum { BM_VEH_CLASS_COMP = 0, BM_VEH_CLASS_CUPE = 1, BM_VEH_CLASS_HEVY = 2, BM_VEH_CLASS_HSPC = 3, BM_VEH_CLASS_MSCL = 4,
       BM_VEH_CLASS_SPRT = 5, BM_VEH_CLASS_SUPR = 6, BM_VEH_CLASS_TSPC = 7, BM_VEH_CLASS_TRAF = 8 };
#define BM_VPHYS_VEHICLES_MAX 256u  /* the list's capacity (retail: 100) */

/* bm_vphys_status.state */
enum {
    BM_VPHYS_STATE_IDLE      = 0,   /* nothing owned */
    BM_VPHYS_STATE_SET       = 1,   /* a scale is set; it applies at player 1's next car update in a race */
    BM_VPHYS_STATE_APPLIED   = 2,   /* player 1's car uses every set scale (as of its last car update) */
    BM_VPHYS_STATE_REFUSED   = 3    /* the last car update could not apply (reason) */
};

typedef struct bm_vphys_info {
    uint32_t struct_size;           /* in: the caller's size; out: the size filled in */
    uint32_t index;
    uint32_t writable;              /* 1: set_scale() may scale it */
    float    scale_min, scale_max;  /* the bounds of a scale (0 / 0 when not writable) */
    char     name[96];              /* "Group | Name", the ValueDB's own (e.g. "Physics/Race Car/Misc | Drag Coef") */
    char     unit[8];               /* the ValueDB value's unit when known ("kg", "mph", "rpm", "deg", "s"), else "" */
} bm_vphys_info;

typedef struct bm_vphys_value {
    uint32_t struct_size;           /* in: the caller's size; out: the size filled in */
    uint32_t racer;                 /* the racer index asked for */
    uint32_t is_player1;            /* 1: player 1's car */
    uint32_t param;                 /* the catalogue index asked for */
    float    current;               /* the car's copy (what its physics uses), ValueDB units */
    float    game_value;            /* the vehicle's own ValueDB value (its block) */
    uint32_t scaled;                /* 1: this service has the car's copy at game_value x scale */
    float    scale;                 /* the scale set for this value (1 when none) */
    char     vehicle[32];           /* the vehicle's ValueDB file stem, e.g. "COMPCAR1" */
} bm_vphys_value;

typedef struct bm_vphys_status {
    uint32_t struct_size;
    uint32_t state;                 /* BM_VPHYS_STATE_* */
    uint32_t reason;                /* BM_VPHYS_* when REFUSED */
    uint32_t race;                  /* changes with each race the service sees */
    uint32_t applied;               /* scaled values written (first write in a race) since the start */
    uint32_t reapplied;             /* written again after the game copied its value back (same race) */
    uint32_t restored;              /* car copies put back to the game's value (race left / reset) */
    uint32_t contested;             /* car updates that found a third value (left alone) */
} bm_vphys_status;

/* v2: one vehicle of the ValueDB's vehicle list */
typedef struct bm_vphys_vehicle_info {
    uint32_t struct_size;           /* in: the caller's size; out: the size filled in */
    uint32_t index;                 /* 0 .. vehicle_count-1 */
    char     name[16];              /* the file stem, e.g. "COMPCAR1" */
    uint32_t series_class;          /* BM_VEH_CLASS_* (from the name) */
    uint32_t added;                 /* 0 (added cars are not listed in this version) */
    uint32_t open;                  /* BM_VEH_OPEN_UNKNOWN (not verified yet) */
    uint32_t race_vehicle;          /* 1: the file has the race-car handling records ("Drag Coef" present) */
} bm_vphys_vehicle_info;            /* 40 bytes */

/* v2: one value of one vehicle */
typedef struct bm_vphys_vehicle_value {
    uint32_t struct_size;           /* in: the caller's size; out: the size filled in */
    uint32_t have;                  /* 1: the vehicle's file has the record */
    double   value;                 /* what the next race copies for it, in the ValueDB's units (= game_value here) */
    double   game_value;            /* the ValueDB record */
    uint32_t scaled;                /* 0 in this version */
    uint32_t vehicle, param;        /* the indices asked for */
} bm_vphys_vehicle_value;           /* 40 bytes */

/* v3: the gearbox of a player's car */
typedef struct bm_vphys_gearbox_status {
    uint32_t struct_size;           /* in: room; out: filled */
    uint32_t available;             /* 1: this build's gearbox sites passed the byte census at start */
    uint32_t mode;                  /* BM_GEARBOX_* the car runs now (the game's mode word; 0 outside a race) */
    int32_t  gear;                  /* -1 R, 0 N, 1 .. max_gear (0 outside a race) */
    int32_t  max_gear;              /* the car's gear count (the game's upshift bound; 0 outside a race) */
    int32_t  requested;             /* the pending request, 0 = none */
    uint32_t shifting;              /* 1 while the game's shift flag is set */
    uint32_t owned, yours;          /* MANUAL owned by a plugin / by you */
    uint32_t idle_fix_skips;        /* times the host mark skipped the idle re-shift (this race) */
} bm_vphys_gearbox_status;          /* 40 bytes */

typedef struct bm_vphys_api {
    uint32_t struct_size;
    uint32_t version;               /* BM_VPHYS_VERSION */
    uint32_t (TD_CALL *count)(td_host *host);                                       /* catalogue size (0 without host) */
    int32_t  (TD_CALL *info)(td_host *host, uint32_t index, bm_vphys_info *out);
    int32_t  (TD_CALL *find)(td_host *host, const char *name, uint32_t *index);
    uint32_t (TD_CALL *racers)(td_host *host);                                      /* cars racing now (0 outside a race) */
    int32_t  (TD_CALL *get)(td_host *host, uint32_t racer, uint32_t index, bm_vphys_value *out);
    int32_t  (TD_CALL *set_scale)(td_host *host, uint32_t index, double scale);
    int32_t  (TD_CALL *reset)(td_host *host, uint32_t index);
    int32_t  (TD_CALL *status)(td_host *host, bm_vphys_status *out);
    /* ---- version 2: the vehicle query (read only when version >= 2 and struct_size covers them). Any thread. ---- */
    uint32_t (TD_CALL *vehicle_count)(td_host *host);                                   /* 0 while UNAVAILABLE */
    int32_t  (TD_CALL *vehicle_info)(td_host *host, uint32_t vehicle, bm_vphys_vehicle_info *out);
    int32_t  (TD_CALL *vehicle_find)(td_host *host, const char *name, uint32_t *vehicle);
    int32_t  (TD_CALL *vehicle_value)(td_host *host, uint32_t vehicle, uint32_t index, bm_vphys_vehicle_value *out);
    /* ---- version 3: the gearbox (read only when version >= 3 and struct_size covers them) ---- */
    /* BM_VPHYS_OK, NOT_PLAYER (player > 1), UNSUPPORTED (player 1 = split screen, or the census failed), BAD_ARG (mode),
     * CONFLICT (another plugin owns it; AUTO by a non-owner), DEBUG_AUTOPILOT. */
    int32_t  (TD_CALL *set_gearbox)(td_host *host, uint32_t player, uint32_t mode);
    /* BM_VPHYS_OK (recorded), NOT_PLAYER, UNSUPPORTED, WRONG_MODE (not MANUAL by you), UNAVAILABLE (no car in a race now),
     * BAD_ARG (gear outside 1 .. max_gear), BUSY_SHIFT (the game's shift flag is set now: ask again). */
    int32_t  (TD_CALL *request_gear)(td_host *host, uint32_t player, int32_t gear);
    /* BM_VPHYS_OK (out filled; zeros outside a race), BAD_ARG, NOT_PLAYER, UNSUPPORTED (player 1). */
    int32_t  (TD_CALL *gearbox_status)(td_host *host, uint32_t player, bm_vphys_gearbox_status *out);
} bm_vphys_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_VPHYSICS_H */
