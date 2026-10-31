/*
 * bmashup_tune.h - the "bmashup.tune" service: Burnout Mashup's private, experimental access to the game's OWN tuning
 * values (the named, typed variables the game registers in its tuning registry, e.g. "Score/Boost/Lap | Perfect Lap Boost
 * value (Boost units)" = 120.0). Not a Takedawn service; offered only by Burnout Mashup builds; it may change or go away.
 *
 * Contract:
 *  - **What it changes:** the value of a catalogued game variable that the game itself reads each time it uses it (guest
 *    .data, never written by the game's code: checked for every catalogued entry). It does NOT change constants compiled
 *    into the generated code, array sizes, pools or any engine limit.
 *  - **No addresses:** entries are named "Group | Name" exactly as the game names them; the service holds the guest
 *    address. Nothing here is an address.
 *  - **Build verification:** at start-up every entry is checked against the running game: its name string at the
 *    catalogued place in the game's read-only data, and its current value equal to the shipped value. An entry that does
 *    not match is UNSUPPORTED (listed, never written). A different game build therefore disables the service's entries
 *    instead of writing into unknown data.
 *  - **Bounds:** a value must be finite, >= 0 and <= 16 x max(shipped value, the game's value, 1) (integers: whole numbers).
 *    Version 2: the game copies its value database (Data/vdb.xml) into these variables at the end of its boot, so its OWN
 *    value can differ from the program's (e.g. trading paint 3.0 in the program, 90 in the database). Until that copy only
 *    a sanity cap (BM_TUNE_PROVISIONAL_MAX) applies; at the copy every owned value is checked against the full bound: a mod
 *    declaration above it stops the start (exit 93, named), a plugin's value above it is dropped (the game's value stays,
 *    logged). info() reports game_value once known. The bound is the service's policy, not the game's.
 *  - **Version 3 (GP-AITUNE1):** the catalogue also holds the 73 AI ValueDB values ("AI/Car | Top speed mps", "AI/Aggressive
 *    Driving | ...", "AI/Avoidance | ...", appended after the scoring / boost entries). A SIGNED entry (a negative default or
 *    ValueDB value, or read by the game as a signed integer) takes -bound .. +bound, bound = 16 x max(|shipped|, |game|, 1).
 *    info() also says min, is_signed and applies (next use / next race / never). The three AI values the game never reads
 *    are UNSUPPORTED. A mod.toml declaration of an AI value or a negative value needs [bmashup.tune] version = 2 (an older
 *    host then refuses that mod alone: "needs a newer platform").
 *  - **Ownership / conflicts:** the first requester of an entry owns it (a mod's mod.toml declaration, applied before the
 *    plugins start, or a plugin); another requester's set is refused (CONFLICT) - no silent last-writer-wins. reset() by
 *    the owner restores the game's value (the shipped value before the game's copy) and releases the entry.
 *  - **Threads / phases:** set / reset / get on the game's thread (plugin init, or inside a bmashup.events callback). The
 *    value is one aligned 32-bit store; the game sees it at its next use. Values are not persisted anywhere; the game's
 *    save is not touched.
 *  - **Approval:** a plugin using it is an ordinary approved native plugin (exact-hash approval); a mod.toml declaration
 *    needs no plugin.
 *  - **Sliders (main21 patch 130; mod.toml [bmashup.tune] version 3, no API change):** a DATA mod may declare `sliders`, rows
 *    the player changes on the MODS page (MOD SETTINGS) inside the mod's own range; the player's value is kept in
 *    plugin-settings.toml (the one place a tune value persists) and applied as the mod's declaration (the mod owns the row: a
 *    plugin's set of it is CONFLICT, as for any declared row). Rules: the host's bm_tune.h.
 */
#ifndef BMASHUP_TUNE_H
#define BMASHUP_TUNE_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_TUNE_SERVICE "bmashup.tune"
#define BM_TUNE_VERSION 3u          /* 3 (GP-AITUNE1): + the 73 AI ValueDB values, signed entries, info min / is_signed /
                                     * applies; 2: the game's own (ValueDB) value is the default and the bound's base */
#define BM_TUNE_PROVISIONAL_MAX 1.0e6

enum {
    BM_TUNE_OK = 0,
    BM_TUNE_BAD_ARG = 1,                /* no host, no out, struct_size below 8, index past the catalogue */
    BM_TUNE_NOT_FOUND = 2,              /* find(): no entry of that name */
    BM_TUNE_UNSUPPORTED = 3,            /* the entry did not verify against this game build */
    BM_TUNE_OUT_OF_RANGE = 4,           /* not finite, negative, above the bound, or not whole for an integer */
    BM_TUNE_CONFLICT = 5                /* another requester owns the entry */
};

enum { BM_TUNE_FLOAT = 2, BM_TUNE_INT = 1 };          /* the game's registry type codes */
enum { BM_TUNE_OWNER_NONE = 0, BM_TUNE_OWNER_YOU = 1, BM_TUNE_OWNER_OTHER = 2 };
/* version 3: when the game reads a value (static scan of its code: atlas AI.md, scripts\s7_ai_readers.py) */
enum { BM_TUNE_APPLIES_NEXT_USE = 0,    /* re-read at every use: a set value counts from the next frame / decision */
       BM_TUNE_APPLIES_NEXT_RACE = 1,   /* read once per racer at the race set-up (AI reset): from the next race */
       BM_TUNE_APPLIES_NEVER = 2 };     /* never read by this build: the entry is UNSUPPORTED */

typedef struct bm_tune_info {
    uint32_t struct_size;               /* in: the size you have; out: the size filled in */
    uint32_t type;                      /* BM_TUNE_FLOAT / BM_TUNE_INT */
    uint32_t verified;                  /* 1: usable on this build; 0: UNSUPPORTED */
    uint32_t owner;                     /* BM_TUNE_OWNER_* */
    double shipped;                     /* the value the game ships with */
    double current;
    double max;                         /* the service's bound (min is 0) */
    char name[128];                     /* "Group | Name", as the game names it (Group may be empty: "Name") */
    /* version 2 */
    double game_value;                  /* the game's own value (its value database), once known; else 0 */
    uint32_t game_value_known;          /* 1 after the game's copy at the end of its boot */
    uint32_t reserved;
    /* version 3 (GP-AITUNE1) */
    double min;                         /* the lower bound: 0, or -max for a signed entry */
    uint32_t is_signed;                 /* 1: negative values allowed (|value| <= max) */
    uint32_t applies;                   /* BM_TUNE_APPLIES_*: when the game reads a set value */
} bm_tune_info;                         /* 200 bytes (version 2: 184; a smaller struct_size gets its prefix) */

typedef struct bm_tune_api {
    uint32_t struct_size;
    uint32_t version;
    uint32_t (TD_CALL *count)(td_host *host);
    int32_t (TD_CALL *info)(td_host *host, uint32_t index, bm_tune_info *out);
    int32_t (TD_CALL *find)(td_host *host, const char *name, uint32_t *index);   /* exact "Group | Name" */
    int32_t (TD_CALL *get)(td_host *host, uint32_t index, double *value);
    int32_t (TD_CALL *set)(td_host *host, uint32_t index, double value);
    int32_t (TD_CALL *reset)(td_host *host, uint32_t index);                       /* owner only */
} bm_tune_api;

#ifdef __cplusplus
}
#endif
#endif
