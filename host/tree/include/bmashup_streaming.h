/*
 * bmashup_streaming.h - the "bmashup.streaming" service: Burnout Mashup's
 * private, experimental streaming limits for native plugins. Not a Takedawn
 * service: offered only by Burnout Mashup's own builds, through the same
 * optional export as Takedawn's (takedawn_services.h); it may change or go away.
 *
 * Version 1 has one limit: the size of a low-detail track unit (the block that
 * also carries the unit's collision). The game streams these into 18 slots of
 * 0x18000 bytes (96 KiB) in a one-view race; a Burnout Mashup build that
 * carries the slot extension can give the 18 slots a larger size. Split screen
 * keeps the game's slots. Every build with this service also checks each unit
 * read: a unit larger than its slot stops the game with a message instead of
 * overwriting the next slot.
 *
 * Request while Takedawn starts the plugins only (takedawn_plugin_init, or
 * takedawn_plugin_service). When the plugins have started, the size is the
 * largest of every accepted request and the game's, and it is FIXED for the
 * rest of the process. The memory (18 x size, contiguous) is taken once, when
 * the game sets up its memory, before any track; if it cannot be had the
 * game's slots stay and lowslot_info says so.
 *
 * Version 2 (G8-L9) adds the STATIC track pool: the whole static.dat of a
 * track is read in one piece into it (one view 0xD00000, split screen
 * 0xA00000). A larger file is cut short by the game; every build with version
 * 2 checks each load: complete loads are logged, a truncated load stops the
 * game in a one-view race (code 90) and is reported in split screen. A plugin
 * may ask for a larger pool: one region of that size, used by one view when
 * larger than 0xD00000 and by split screen when larger than 0xA00000. The same
 * rules as the slots: while starting only, largest wins, fixed afterwards,
 * taken once when the game sets up its memory; refused memory keeps the game's
 * pools. Version 1's functions are unchanged; the table only grew.
 *
 * Nothing here is an address, and nothing writes the game's data directly.
 */
#ifndef BMASHUP_STREAMING_H
#define BMASHUP_STREAMING_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_STREAMING_SERVICE "bmashup.streaming"
#define BM_STREAMING_VERSION 2u

#define BM_STREAMING_STATIC_ONE_VIEW_GAME 0xD00000u  /* the game's STATIC pools */
#define BM_STREAMING_STATIC_SPLIT_GAME    0xA00000u
/* The largest region the contiguous window could ever hold: 64 MiB less the GPU instance (128 KiB), the 1 MiB low
 * reserve and the game's own memory blocks. Not a promise: the memory is the allocator's answer at boot.
 * patch 131: this is the 64 MiB-window build's ceiling; a 256 MiB-window host (the default) accepts up to 0x4000000
 * (64 MiB, its high zone; the boot budget gate decides). The value is unchanged so a plugin's check stays valid on both. */
#define BM_STREAMING_STATIC_MAX           0x20C4000u

#define BM_STREAMING_LOW_GAME 0x18000u  /* the game's low-detail slot size */
#define BM_STREAMING_LOW_MAX  0x200000u /* the ceiling (patch 131: was 0x30000) */
#define BM_STREAMING_PAGE     0x1000u   /* sizes are whole 4 KiB pages */

/* Results. */
enum {
    BM_STREAMING_OK           = 0,
    BM_STREAMING_BAD_ARG      = 1,  /* no host, or no out / out->struct_size below 8 */
    BM_STREAMING_OUT_OF_RANGE = 2,  /* not a page multiple, below the game's or above the ceiling: nothing recorded */
    BM_STREAMING_CLOSED       = 3,  /* the plugins' start is over: the size is fixed */
    BM_STREAMING_UNSUPPORTED  = 4   /* this game build is not one the slot extension is verified for */
};

/* lowslot_info: the extension's state. */
enum {
    BM_STREAMING_PLANNED  = 0,      /* the game has not set up its memory yet */
    BM_STREAMING_GAME     = 1,      /* the game's slots (nothing larger was asked) */
    BM_STREAMING_EXPANDED = 2,      /* the slots have frozen_bytes each */
    BM_STREAMING_FAILED   = 3       /* asked, but refused or no memory: the game's slots */
};

/* A copy (yours); nothing in it points into the game. */
typedef struct bm_streaming_lowslot {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t open;                  /* 1 while requests are taken, 0 once the size is fixed */
    uint32_t requested_bytes;       /* the largest accepted request so far, or the game's */
    uint32_t frozen_bytes;          /* the fixed size (0 while open) */
    uint32_t state;                 /* BM_STREAMING_* (PLANNED .. FAILED) */
    uint32_t effective_bytes;       /* what a low-detail unit may have now */
    uint32_t low_checks;            /* low-detail unit reads checked so far */
    uint32_t low_largest;           /* the largest low-detail unit read so far */
    uint32_t full_checks;           /* full-detail unit reads checked so far */
    uint32_t full_largest;          /* the largest full-detail unit read so far */
    uint32_t unchecked;             /* reads whose slot could not be identified (not checked) */
    uint32_t your_request;          /* this plugin's largest accepted request (0: none) */
} bm_streaming_lowslot;             /* 48 bytes */

/* static_info (version 2): the STATIC pool. A copy (yours). */
enum {
    BM_STREAMING_STATIC_PLANNED  = 0,   /* the game has not set up its memory yet */
    BM_STREAMING_STATIC_GAME     = 1,   /* the game's pools */
    BM_STREAMING_STATIC_EXPANDED = 2,   /* one region of frozen_bytes backs the pools it is larger than */
    BM_STREAMING_STATIC_FAILED   = 3    /* asked, refused (memory / table / build): the game's pools */
};
typedef struct bm_streaming_static {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t open;                  /* 1 while requests are taken */
    uint32_t requested_bytes;       /* the largest accepted request so far (0: none) */
    uint32_t frozen_bytes;          /* the fixed size (0 while open, 0 when nobody asked) */
    uint32_t state;                 /* BM_STREAMING_STATIC_* */
    uint32_t one_view_bytes;        /* the one-view pool in force */
    uint32_t split_bytes;           /* the split-screen pool in force */
    uint32_t loads;                 /* static loads checked */
    uint32_t complete;              /* ... loaded completely */
    uint32_t truncated;             /* ... cut short (split screen; a one-view one stops the game) */
    uint32_t largest;               /* the largest complete static.dat so far */
    uint32_t your_request;          /* this plugin's largest accepted request (0: none) */
} bm_streaming_static;              /* 48 bytes */

/* The service's table: valid until the process ends. */
typedef struct bm_streaming_api {
    uint32_t struct_size;           /* sizeof (bm_streaming_api) as built */
    uint32_t version;               /* BM_STREAMING_VERSION */
    /* Ask for low-detail unit slots of at least `bytes` (a page multiple,
     * BM_STREAMING_LOW_GAME..BM_STREAMING_LOW_MAX). While the plugins start
     * only. merged_bytes (may be NULL): the size as merged so far. */
    int32_t (TD_CALL *request_low_unit_bytes)(td_host *host, uint32_t bytes, uint32_t *merged_bytes);
    /* The slot size and the extension's state into *out (set out->struct_size). Any thread. */
    int32_t (TD_CALL *lowslot_info)(td_host *host, bm_streaming_lowslot *out);
    /* Version 2 (present when struct_size covers it). Ask for a STATIC pool of
     * at least `bytes` (a page multiple, above BM_STREAMING_STATIC_SPLIT_GAME, at
     * most BM_STREAMING_STATIC_MAX). While the plugins start only. */
    int32_t (TD_CALL *request_static_bytes)(td_host *host, uint32_t bytes, uint32_t *merged_bytes);
    /* The STATIC pool's state into *out (set out->struct_size). Any thread. */
    int32_t (TD_CALL *static_info)(td_host *host, bm_streaming_static *out);
} bm_streaming_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_STREAMING_H */
