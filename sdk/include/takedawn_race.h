/*
 * takedawn_race.h - the "takedawn.race" service (docs/native-plugins.md, The
 * race): what the race is doing, for a plugin to read. Plain C, MIT.
 *
 * Offered through takedawn_plugin_service (takedawn_services.h). Read only:
 * nothing here changes the game. Everything is a copy made by Takedawn after
 * each game update; no pointer into the game, no address, no game structure
 * is part of it.
 */
#ifndef TAKEDAWN_RACE_H
#define TAKEDAWN_RACE_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TD_RACE_SERVICE "takedawn.race"
#define TD_RACE_VERSION 1u

/* td_race_snapshot.state: where the game is. */
enum {
    TD_RACE_NONE     = 0,    /* no game yet, or a game this Takedawn does not read */
    TD_RACE_LOADING  = 1,    /* a load, or a stage's set-up or hand-over */
    TD_RACE_FRONTEND = 2,    /* the menus: no stage */
    TD_RACE_PRESTART = 3,    /* in a stage, before the GO */
    TD_RACE_RACING   = 4,    /* in a stage, from the GO, not paused */
    TD_RACE_PAUSED   = 5,    /* in a stage, paused */
    TD_RACE_FINISHED = 6,    /* player 1's event is over (the results may still show) */
    TD_RACE_LEAVING  = 7     /* the stage is being left */
};

/* td_race_snapshot.valid: which fields mean something. */
enum {
    TD_RACE_HAVE_CAR   = 1u << 0,   /* cars, place, lap, race_time_s, best_lap_s, position, forward */
    TD_RACE_HAVE_SPEED = 1u << 1    /* speed_mps */
};

/* Return values. */
enum {
    TD_RACE_OK          = 0,
    TD_RACE_UNAVAILABLE = 1,        /* no snapshot yet: the game has not updated */
    TD_RACE_BAD_ARG     = 2
};

/* Player 1 and the event, as of the game's last update. A field outside
 * valid is 0. */
typedef struct td_race_snapshot {
    uint32_t struct_size;           /* in: the size the caller has; out: the size Takedawn filled in */
    uint32_t state;                 /* TD_RACE_* */
    uint32_t valid;                 /* TD_RACE_HAVE_* */
    uint32_t step;                  /* the game's simulation step: 60 a second, held while paused */
    uint32_t cars;                  /* cars in the event */
    int32_t  place;                 /* player 1's place, 1 = first */
    uint32_t lap;                   /* laps player 1 has done */
    float    race_time_s;           /* player 1's race time */
    float    best_lap_s;            /* player 1's best lap (0 before the first) */
    float    speed_mps;             /* player 1's speed over the ground, metres a second */
    float    position[3];           /* player 1's car, metres, in the game's world axes */
    float    forward[3];            /* the way player 1's car points (unit length) */
} td_race_snapshot;

typedef void (TD_CALL *td_race_update_fn)(const td_race_snapshot *snapshot, void *user);

/* The service's table. Takedawn's, valid until the process ends. */
typedef struct td_race_api {
    uint32_t struct_size;           /* sizeof (td_race_api) as Takedawn built it */
    uint32_t version;               /* TD_RACE_VERSION */
    /* The latest snapshot into *out: at most out->struct_size bytes (set it
     * first), and out->struct_size becomes what was filled in. Any thread;
     * the copy is always whole (never half of two updates). TD_RACE_OK,
     * TD_RACE_UNAVAILABLE before the game's first update, TD_RACE_BAD_ARG
     * for a missing host or out, or out->struct_size below 8. */
    int32_t (TD_CALL *get)(td_host *host, td_race_snapshot *out);
    /* fn(snapshot, user) once per game update (about 60 a second; fewer
     * while loading), on the game's thread, right after the update: it holds
     * up the game while it runs, so keep it short. One per plugin: a new fn
     * replaces it, NULL removes it. The snapshot is Takedawn's, for the
     * call's length only, and Takedawn's size (read its struct_size). */
    int32_t (TD_CALL *on_update)(td_host *host, td_race_update_fn fn, void *user);
} td_race_api;

#ifdef __cplusplus
}
#endif

#endif /* TAKEDAWN_RACE_H */
