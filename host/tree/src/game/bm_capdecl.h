/*
 * bm_capdecl.h - G8-MCAP EXPERIMENTAL: capacity requirements a mod declares in its mod.toml, for mods that need a larger
 * engine capacity but ship no plugin (docs/bmashup-engine-limits.md, "Mod capacity declarations"):
 *
 *   [bmashup.capacity]
 *   version = 1                  # required: the table's schema version this build reads (1)
 *   lanes = 80                   # total AI route lanes the mod's tracks need     -> bmashup.engine    request_lanes
 *   low_unit_bytes = 0x1A000     # low-detail unit slot size its tracks need      -> bmashup.streaming request_low_unit_bytes
 *   static_bytes = 0xD01000      # STATIC track pool its static.dat files need    -> bmashup.streaming request_static_bytes
 *
 * Each value is passed to the service's own request function, exactly as a plugin's request (the same range / page /
 * build checks; the largest request wins, whatever the order), with the mod as the requester, before the plugins start;
 * the services freeze the merged values right after the plugins start, as before. Takedawn's own manifest reader
 * (modmanifest.c) leaves unknown tables alone, so the table is invisible to builds without this extension, and every
 * existing mod.toml (none has the table) is read as before.
 *
 * A requirement that this build cannot meet stops the start (exit 91) with the mod, the field and the reason: a version
 * other than 1, an unknown key in the table, a value that is not a whole number, or a request the service refuses (out of
 * range, unsupported game build). The start stops at the first refusal, so the game never runs with part of a mod's
 * requirement (fields of that mod accepted before the refused one are requested but never used).
 * Only mods that are on and usable are read. Allocation happens later, where it did (lanes at the track's load, slots and
 * STATIC after the game's memory set-up); if memory is refused there, the game's capacity stays and the existing guards
 * stop content that needs more (exit 88 / 89 / 90), as for a plugin's request.
 */
#ifndef BO3_BM_CAPDECL_H
#define BO3_BM_CAPDECL_H

#include <stddef.h>
#include <stdint.h>

#define BO3_CAPDECL_VERSION 1

enum { BO3_CAPDECL_LANES = 1u, BO3_CAPDECL_LOW = 2u, BO3_CAPDECL_STATIC = 4u };

typedef struct bo3_capdecl {
    int present;                    /* the mod.toml has a [bmashup.capacity] key */
    uint32_t have;                  /* BO3_CAPDECL_* fields given */
    uint32_t lanes, low_unit_bytes, static_bytes, gamedata_bytes;   /* GP-MEGA1: gamedata_bytes */
} bo3_capdecl;

/* Reads the table from n bytes of a mod.toml. 1 with *out (present 0 when there is no table); 0 with a one-line reason. */
int bo3_capdecl_parse(const char *text, size_t n, bo3_capdecl *out, char *why, size_t wn);

typedef void (*bo3_capdecl_fail_fn)(const char *mod_id, const char *why);

/* Every usable, enabled mod's declaration into the services (bo3_bm_engine_api / bo3_bm_streaming_api), in the mod list's
 * order; after bo3_modfs_init and the services' init, before bo3_plugins_init. fail (game: exit 91) for the first refusal.
 * The number of mods that declared something. */
int bo3_capdecl_apply(bo3_capdecl_fail_fn fail);

/* The game's start: bo3_capdecl_apply with the exit-91 failure. */
void bo3_capdecl_game_apply(void);

#endif
