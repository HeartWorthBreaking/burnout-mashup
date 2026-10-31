/*
 * bmashup_engine.h - the "bmashup.engine" service: Burnout Mashup's private,
 * experimental engine limits for native plugins. Not a Takedawn service:
 * offered only by Burnout Mashup's own builds, through the same optional
 * export as Takedawn's (takedawn_services.h); it may change or go away.
 *
 * Version 1 has one limit: the AI route lanes a track may have. The game
 * addresses 64; a Burnout Mashup build that carries the lane extension can
 * address more. Terms, used the same way everywhere:
 *   total lane capacity  lane numbers 0 .. total-1 a track may use
 *   extension entries    total - 64: the lanes beyond the game's own 64
 * Example: 80 total = 16 extension entries (lanes 64..79). The ceiling is 255
 * total: lane numbers are bytes in the track data and 255 means "no lane".
 *
 * Request while Takedawn starts the plugins only (takedawn_plugin_init, or
 * takedawn_plugin_service). When the plugins have started, the capacity is
 * the largest of every accepted request and the default (65 total, as builds
 * without this service had), and it is FIXED for the rest of the process: the
 * guest has not run yet, so no track was loaded with another value. Memory is
 * taken only when a track with more than 64 lanes loads; a track with 64 or
 * fewer lanes behaves exactly as in the game.
 *
 * Nothing here is an address, and nothing writes the game's data directly.
 */
#ifndef BMASHUP_ENGINE_H
#define BMASHUP_ENGINE_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_ENGINE_SERVICE "bmashup.engine"
#define BM_ENGINE_VERSION 1u

#define BM_ENGINE_LANES_GAME    64u     /* the game's own lanes */
#define BM_ENGINE_LANES_DEFAULT 65u     /* the capacity when no plugin asks for more */
#define BM_ENGINE_LANES_MAX     255u    /* the format's ceiling (255 = "no lane" is not a lane) */

/* Results. */
enum {
    BM_ENGINE_OK           = 0,
    BM_ENGINE_BAD_ARG      = 1,     /* no host, or no out / out->struct_size below 8 */
    BM_ENGINE_OUT_OF_RANGE = 2,     /* total 0 or above BM_ENGINE_LANES_MAX: refused, nothing recorded */
    BM_ENGINE_CLOSED       = 3,     /* the plugins' start is over: the capacity is fixed */
    BM_ENGINE_UNSUPPORTED  = 4      /* this game build is not one the lane extension is verified for */
};

/* lanes_info: the extension's state. */
enum {
    BM_ENGINE_LANES_PLANNED     = 0,    /* no track has needed it yet: no memory taken */
    BM_ENGINE_LANES_ALLOCATED   = 1,    /* in use: tracks may have up to `frozen_total` lanes */
    BM_ENGINE_LANES_FAILED      = 2,    /* the memory could not be had (no retry): 64 lanes */
    BM_ENGINE_LANES_UNSUPPORTED = 3     /* not this game build: 64 lanes */
};

/* A copy (yours); nothing in it points into the game. */
typedef struct bm_engine_lanes {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t open;                  /* 1 while requests are taken, 0 once the capacity is fixed */
    uint32_t requested_total;       /* the largest accepted request so far, or the default */
    uint32_t frozen_total;          /* the fixed capacity (0 while open) */
    uint32_t entries;               /* extension entries that apply: frozen_total - 64, or planned */
    uint32_t state;                 /* BM_ENGINE_LANES_* */
    uint32_t effective_total;       /* what a track can use now: 64 + entries when allocated, else 64 or planned */
    uint32_t track_loads;           /* tracks loaded so far */
    uint32_t last_track_lanes;      /* the last track's lane count */
    uint32_t installed;             /* its lanes on the extension */
    uint32_t refused;               /* its lanes refused (above capacity, or no extension) */
    uint32_t your_request;          /* this plugin's largest accepted request (0: none) */
} bm_engine_lanes;                  /* 48 bytes */

/* The service's table: valid until the process ends. */
typedef struct bm_engine_api {
    uint32_t struct_size;           /* sizeof (bm_engine_api) as built */
    uint32_t version;               /* BM_ENGINE_VERSION */
    /* Ask for a total lane capacity of at least `total` (1..255). While the
     * plugins start only. merged_total (may be NULL): the capacity as merged
     * so far. BM_ENGINE_OK, or why not (nothing is recorded then). */
    int32_t (TD_CALL *request_lanes)(td_host *host, uint32_t total, uint32_t *merged_total);
    /* The lane capacity and the extension's state into *out (set
     * out->struct_size). Any thread. */
    int32_t (TD_CALL *lanes_info)(td_host *host, bm_engine_lanes *out);
} bm_engine_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_ENGINE_H */
