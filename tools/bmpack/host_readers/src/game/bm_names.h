/*
 * bm_names.h - G8-NM1 EXPERIMENTAL: names and location names for tracks added by mods (bm_tracks.h), shown by the game's
 * own menus (content_count\names\TEXT_LOOKUP_TRACE.md, B1_SITES.md).
 *
 *   [bmashup.tracks]
 *   version = 1
 *   add = ["US_C6_V1"]
 *   names = ["US_C6_V1 = Harbour Loop"]          # optional; "ID = name", ID one of add; at most 27 characters
 *   locations = ["US_C6_V1 = HARBOUR"]           # optional; at most 17 characters
 *
 * Characters: A-Z a-z 0-9, space and - ' . & (the retail font's text). The upper-case name the game shows on some pages
 * is the name in upper case. A track without a name keeps the game's "Unknown Track".
 *
 * How (no language file changes): the game resolves every text ID inline as [[0x4D532C] + 0xC][id] (a UTF-16 string
 * pointer). After each load of the language table (boot, sub_00020930; language switch, sub_00077430)
 * bo3_nm_gen_table_ready() points [blob + 0xC] at a larger copy of the pointer array (guest memory, allocated once):
 * the game's entries unchanged, IDs up to BO3_NM_BASE answering with the game's own "Unknown Track", then the host strings
 * at BO3_NM_BASE + 3 * track + kind. Where the game falls back to its constant for a track it does not know (11 name
 * sites, the location in sub_00081BB0), bo3_nm_gen_text() swaps in the host ID of that track and kind - only while the
 * host array is the one the game reads, so an unresolvable ID is never produced.
 */
#ifndef BO3_BM_NAMES_H
#define BO3_BM_NAMES_H

#include <stddef.h>
#include <stdint.h>

#define BO3_NM_TABLE_PTR 0x004D532Cu       /* [[0x4D532C] + 0xC] = the string pointers; [+8] = count */
#define BO3_NM_BASE      0x1000u           /* first host text ID (retail: 3985 strings) */
/* G8-TL: every track the track list can hold may be named (bm_tracks.h BO3_CC_CAP, 383; was 64). The host text IDs:
 * BO3_NM_BASE + 3 * named-track + kind for the named tracks, then the declared regions' texts from BO3_NM_REGION_BASE,
 * which follows the last named-track slot whatever BO3_NM_MAX is (bm_names.c checks the layout at compile time). */
#define BO3_NM_MAX       383u              /* named tracks (= BO3_CC_CAP) */
#define BO3_NM_NAME_MAX  27u               /* the longest retail track name */
#define BO3_NM_LOC_MAX   17u               /* the longest retail location */
#define BO3_NM_UNKNOWN   0x4E9u            /* "Unknown Track" */
/* G8-RG4: the text of the k-th declared region (bm_tracks.h [bmashup.regions]) at host ID BO3_NM_REGION_BASE + k */
#define BO3_NM_REGION_BASE (BO3_NM_BASE + 3u * BO3_NM_MAX)   /* G8-TL: 0x147D (RG4: 0x10C0 with 64 named tracks) */

enum { BO3_NM_NAME = 0, BO3_NM_UPPER = 1, BO3_NM_LOCATION = 2, BO3_NM_KINDS = 3 };

/* one mod's names / locations (mod.toml text): checked against its own add list; 1 (also when none), 0 with why */
int bo3_nm_parse(const char *text, size_t n, char *why, size_t wn);
uint32_t bo3_nm_count(void);
const char *bo3_nm_get(uint64_t id, uint32_t kind);          /* the host text, or NULL */

/* guest access: tests give their own memory, the game build g_xbox_mem_offset and the title's heap */
typedef struct bo3_nm_guest {
    uint32_t (*rd32)(void *u, uint32_t va);
    void (*wr32)(void *u, uint32_t va, uint32_t v);
    void (*wr16)(void *u, uint32_t va, uint16_t v);
    uint32_t (*alloc)(void *u, uint32_t size);              /* guest VA, 0 on failure */
    void *user;
} bo3_nm_guest;
void bo3_nm_set_guest(const bo3_nm_guest *g);
/* a guest address as the generated code's MEM32 uses it (the full 32 bits), or 0xFFFFFFFF for the first 64 KB; the game
 * build's accessors use it */
uint32_t bo3_nm_guest_va(uint32_t va);

/* generated-code marks */
void bo3_nm_gen_table_ready(void);
uint32_t bo3_nm_gen_text(uint32_t dflt, uint32_t kind, uint32_t lo, uint32_t hi);
void bo3_nm_gen_note(uint32_t lo, uint32_t hi);
uint32_t bo3_nm_gen_text_noted(uint32_t id, uint32_t kind);
uint32_t bo3_nm_stats(uint32_t which);                       /* 0 installs, 1 swaps, 2 refusals */
/* G8-RG4: the host text ID of the k-th declared region while it resolves in the table the game reads (the host array is
 * installed and holds that string), else 0 (bm_regions.c then does not show the region) */
uint32_t bo3_nm_region_text_id(uint32_t k);

/* the game build: every usable, enabled mod's names (exit 92 on a refusal, as bm_tracks.c) */
void bo3_nm_game_load(void);

/* G8-E4: a plugin's text in its bmashup.memory block (va, size): 0 ok (applied at the table install if the track is a
 * declared added track and no mod named that kind), 1 bad text / argument, 2 closed (installed), 3 conflict */
int bo3_nm_plugin_text(const void *owner, uint64_t id, uint32_t kind, uint32_t va, uint32_t size);

/* PLATFORM-P3 (P-11): World Tour event texts ([bmashup.extra_events] version 2 names / help, bm_wtour.c). Host IDs:
 * BO3_NM_EVENT_BASE = the generic help of an added event, then BO3_NM_EVENT_BASE + 1 + 2 * event + kind (event = the
 * registration order, never saved). bm_wtour.c registers EVERY declared event (texts or not) before the first table
 * install; registration closes at that install (the array is sized once). */
#define BO3_NM_EVENTS_MAX  35u                           /* = BO3_WT_MAX (bm_wtour.c checks) */
#define BO3_NM_EVENT_BASE  (BO3_NM_REGION_BASE + 23u)    /* 0x1494: after the 23 region texts */
#define BO3_NM_EVENT_TEXT  100u                          /* bytes per text (help <= 97 characters) */
#define BO3_NM_EVENT_HELP_DEFAULT "AN EVENT ADDED BY A MOD."
enum { BO3_NM_EV_NAME = 0, BO3_NM_EV_HELP = 1 };
/* 0 ok, 1 bad argument / key twice, 2 closed (the table is installed), 3 full */
int bo3_nm_event_texts(const char *key, const char *name, const char *help);
/* the host ID of an event's name / help (help: else the generic help) while the host array is the one the game reads,
 * else dflt */
uint32_t bo3_nm_event_text_id(const char *key, uint32_t kind, uint32_t dflt);
void bo3_nm_event_texts_reset(void);                      /* tests (bo3_wt_reset calls it) */

/* GP-CARS2 (bm_cars.h [bmashup.cars] names): texts of cars added by mods. Host IDs: BO3_NM_CAR_BASE = the generic award text
 * (BO3_NM_CAR_AWARD, shown where the game names how a car is won), then BO3_NM_CAR_BASE + 1 + 2 * car + kind (kind 0 the
 * upper-case name, 1 the name as written; car = the registration order, never saved). bm_cars.c registers EVERY declared car
 * (named or not) before the first table install; registration closes at that install (the array is sized once). */
#define BO3_NM_CARS_MAX   1024u                          /* GP-VEH1: >= BO3_CAR_MAX_DECL (917; bm_cars.c checks); cars2 had 21 */
#define BO3_NM_CAR_BASE   (BO3_NM_EVENT_BASE + 1u + 2u * BO3_NM_EVENTS_MAX)   /* 0x14DB: after the event texts */
#define BO3_NM_CAR_TEXT   22u                            /* bytes per name (21 characters + NUL) */
#define BO3_NM_CAR_AWARD  "ADDED BY A MOD"
enum { BO3_NM_CAR_UPPER = 0, BO3_NM_CAR_MIXED = 1, BO3_NM_CAR_AWARD_KIND = 2 };
/* 0 ok, 1 bad argument / ID twice, 2 closed (the table is installed), 3 full; name NULL or "" = no name (award text only) */
int bo3_nm_car_texts(uint64_t id, const char *name);
/* GP-VEH1 rollback: a refused mod's car: its texts are no longer answered (the strings stay allocated, unused) */
void bo3_nm_car_texts_drop(uint64_t id);
/* the host ID of an added car's text of kind while the host array is the one the game reads and holds it, else dflt */
uint32_t bo3_nm_car_text_id(uint64_t id, uint32_t kind, uint32_t dflt);
void bo3_nm_car_texts_reset(void);                         /* tests */

/* GP-VEH1: series titles ([bmashup.series] names, bm_veh.h). Host IDs BO3_NM_SERIES_BASE + k (k = the series' registration
 * index). Registration closes at the first table install. */
#define BO3_NM_SERIES_MAX  64u                           /* = BO3_VEH_SERIES_MAX */
#define BO3_NM_SERIES_BASE (BO3_NM_CAR_BASE + 1u + 2u * BO3_NM_CARS_MAX)   /* 0x1CDC */
/* 0 ok, 1 bad argument, 2 closed, 3 full */
int bo3_nm_series_texts(uint32_t k, const char *title);
uint32_t bo3_nm_series_text_id(uint32_t k, uint32_t dflt);

/* GP-FETEX1 ([bmashup.wt_map_art] place / ticker, bm_fetex.h): the 4th World Tour region's map-page texts. Host IDs:
 * BO3_NM_MAP_BASE + kind (0 the place name, 1 the ticker), after the series titles (GP-P4.3 R1: fetex1 placed them after the
 * car texts, veh1 its series titles there too; integration moves the map texts after the series range). Registered once
 * before the first table install (bm_fetex.c bo3_fetex_game_declare); the array is sized then. */
#define BO3_NM_MAP_BASE   (BO3_NM_SERIES_BASE + BO3_NM_SERIES_MAX)   /* 0x1D1C */
#define BO3_NM_MAP_TEXT   64u
/* 0 ok, 1 bad argument, 2 closed (the table is installed), 3 already given */
int bo3_nm_map_texts(const char *place, const char *ticker);
/* the host ID of a map text while the host array is the one the game reads and holds it, else dflt */
uint32_t bo3_nm_map_text_id(uint32_t kind, uint32_t dflt);
void bo3_nm_map_texts_reset(void);                         /* tests */

#endif
