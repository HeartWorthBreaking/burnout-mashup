/*
 * bmashup_names.h - the "bmashup.names" service: Burnout Mashup's private, experimental names for tracks ADDED by mods,
 * supplied by a native plugin (Burnout Mashup builds only; may change or go away). A mod can name its tracks in mod.toml
 * ([bmashup.tracks] names / locations, no code); a plugin can name an added track the same way at start, from a
 * bmashup.memory block it filled with the text.
 *
 * set_text: while Takedawn starts the plugins only. The block must hold UTF-16LE text with its terminating 0 inside the block:
 * 1 .. 27 characters (BM_NAMES_NAME / BM_NAMES_UPPER), 1 .. 17 (BM_NAMES_LOCATION), from A-Z a-z 0-9, space and - ' . &.
 * On success the block is frozen (read-only from then on: the game reads it). The text is used if `track_id` ("RR_NN_VN")
 * is a track a mod adds and that mod did not name this kind itself; otherwise it is ignored at the game's start (logged).
 * First plugin wins per track and kind.
 */
#ifndef BMASHUP_NAMES_H
#define BMASHUP_NAMES_H

#include "bmashup_memory.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_NAMES_SERVICE "bmashup.names"
#define BM_NAMES_VERSION 1u

enum { BM_NAMES_NAME = 0, BM_NAMES_UPPER = 1, BM_NAMES_LOCATION = 2 };

enum {
    BM_NAMES_OK          = 0,
    BM_NAMES_BAD_ARG     = 1,   /* no host, a malformed track ID, an unknown kind */
    BM_NAMES_BAD_TEXT    = 2,   /* not terminated in the block, empty, too long, or a character outside the set */
    BM_NAMES_NOT_OWNER   = 3,   /* not this plugin's block */
    BM_NAMES_CLOSED      = 4,   /* after the plugins' start */
    BM_NAMES_CONFLICT    = 5    /* another plugin named this track and kind first */
};

typedef struct bm_names_api {
    uint32_t struct_size;
    uint32_t version;           /* BM_NAMES_VERSION */
    int32_t (TD_CALL *set_text)(td_host *host, const char *track_id, uint32_t kind, bm_mem_handle block);
} bm_names_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_NAMES_H */
