/*
 * bm_wt4.h - GP-WT4 EXPERIMENTAL (platform 0.1.5): a fourth World Tour map region declared by a mod (gp\slices\wt4,
 * gp\atlas\WORLDTOUR.md s6; plan platform\content\MAP_REGION_PLAN.md, phase 1 = P4 + a borrowed map).
 *
 *   [bmashup.world_tour]
 *   version = 1
 *   region = "O"          # a region letter of [bmashup.regions] (any mod of the set); its text is the 4th entry's name
 *   map = "USA"           # USA | EUROPE | ASIA: the retail map page the region borrows (textures, globe view, marker,
 *                         #   location panel), phase 1 = no new art
 *   location = "OC_L1"    # the region's one location, "RR_XN" (first letter = the region letter); events reach it through
 *                         #   [bmashup.extra_events] add = ["<event> = <track> @ OC_L1"] (tracks of that region, <= 6)
 *
 * Phase 1 model ("borrowed view"): the World Tour region page gets a 4th entry (cursor 3); entering it shows the donor map
 * with ONE location (the donor's first marker, a race location in all three maps) whose list holds only the mod's events.
 * The menu's own region field (+0x254) never leaves 0..2: the 4th region is the donor's index + the host's "active" flag, so
 * every [3]-sized table the game reads with +0x254 stays in range. What the host changes, one generated line each:
 *   region page (sub_00074940 / sub_00074C60 / sub_00158920): G1 the return from a race of a 4th-region event re-enters
 *     region 3; G2 the region entries (3 x 8 bytes in the state object 0x55A070, the next object follows at +0x30) are copied
 *     into a host block + the 4th entry, count 4; G3 the entry widget reads the block (both places that make it: the region page and the way back from the map); G4 the state's region = 3 on the page
 *     while the 4th entry is selected; G5 / G6 the cursor wraps over 4; G7 region 3 is available; G8 / G9 the globe object
 *     0x555C90 (sub_000C7C20 / sub_000C5B20) is given the donor (its per-region float tables are [3]).
 *   map page (sub_000D8530 and the functions it calls): M1 region 3 -> donor + active; M2 the location count (8 switches of
 *     9 / 12 / 7) -> 1 while active; M3 / M4 the retail events of the donor location are not counted (sub_000D80E0) nor
 *     listed (sub_000D6D20) while active (the platform EV marks W2 / W3 then list the mod's events); M5 the marker focus is
 *     the 4th region's location; M6 its marker state = open.
 *   textures (sub_000D8530 x3, sub_000DDCF0 x4, sub_000DE220 x1): T a region index > 2 reaching a SatMap index table is
 *     bounded to the donor (the retail read for 3 is in-range garbage at D8530 and a WILD read at DDCF0 / DE220:
 *     0x39F860 = 0x01ED0E8C -> MEM32(0x464418 + 4 * that)). With the borrowed view 3 never reaches them; T is the guard.
 * BORROWED ASSETS (the contract, docs bmashup-world-tour.md): the map art, the location's place name, the map ticker (the USA one
 * says "WELCOME TO THE USA..."), the globe view and the region page counters are the donor's; the player sees them. Only the
 * region name and the events' names / help are the mod's.
 * Fail closed: no [bmashup.world_tour] anywhere = retail (3 regions; every mark returns the game's value). A region a mod
 * declares only in [bmashup.regions] has no World Tour presence. A declaration that cannot be applied stops the start
 * (exit 92, named). The 4th entry is shown only while: the declaration resolved, the platform EV events are installed and
 * at least one is at the location, and the region's text resolves in the table the game reads (bm_names.c); else the page
 * stays retail (logged once).
 * All guest access through bm_guest.c.
 */
#ifndef BO3_BM_WT4_H
#define BO3_BM_WT4_H

#include <stddef.h>
#include <stdint.h>

#define BO3_WT4_REGION    3u               /* the 4th World Tour region's page index (state +8, the entry widget) */
#define BO3_WT4_LOCS      1u               /* phase 1: one location (the donor's first marker) */
#define BO3_WT4_STATE     0x0055A070u      /* World Tour state object: +4 page, +8 region, +0x14 cursor u16, +0x16 count u16,
                                            * +0x18 entries [3] x 8 (text pointer, locked u8, flag u8, pad) */
#define BO3_WT4_MENU      0x0054FFA0u      /* World Tour menu object: +0x254 region, +0x27C location, +0x57C values [3][0x1C] */
#define BO3_WT4_EXIT_DECL 92

/* one mod's [bmashup.world_tour] (mod.toml text): 1 (also when absent), or 0 with why (nothing kept) */
int bo3_wt4_parse(const char *mod_id, const char *text, size_t n, char *why, size_t wn);
void bo3_wt4_reset(void);                                      /* tests */
typedef uint32_t (*bo3_wt4_alloc_fn)(uint32_t size, uint32_t align);
void bo3_wt4_set_alloc(bo3_wt4_alloc_fn fn);

/* bm_wtour.c: the declared location (5 characters "RR_XN"): its index (0), or -1 */
int bo3_wt4_location_index(uint64_t loc);
int bo3_wt4_location_known(const char *loc);                  /* the text form, any time after the parse */
/* the declaration resolved against the declared regions (bm_tracks.c) and the region text (bm_names.c): 1, or 0 with why */
int bo3_wt4_resolve(char *why, size_t wn);
int bo3_wt4_declared(void);
uint32_t bo3_wt4_region_code(void);                            /* 4 + k of the declared letter (bm_regions.h), 0 none */
uint32_t bo3_wt4_donor(void);                                  /* 0 USA / 1 Europe / 2 Asia */
const char *bo3_wt4_location_text(void);
/* bm_wtour.c reports the events it installed at the location (W1) */
void bo3_wt4_set_events(uint32_t n);
/* the 4th entry is shown (declared + resolved + events + text): 1 */
int bo3_wt4_shown(void);
/* the map page currently shows the 4th region (M1) */
int bo3_wt4_active(void);
/* W6: a World Tour launch; is_wt4 = the event is one of the 4th region's (the return path then re-enters region 3) */
void bo3_wt4_note_launch(int is_wt4);

/* the generated-code marks (bo3_wt4_gen.h) */
uint32_t bo3_wt4_gen_enter(uint32_t region, uint32_t mode);      /* G1 */
void bo3_wt4_gen_regions(uint32_t state);                         /* G2 */
uint32_t bo3_wt4_gen_entries(uint32_t entries);                   /* G3 */
uint32_t bo3_wt4_gen_page_region(uint32_t region, uint32_t page); /* G4 */
uint32_t bo3_wt4_gen_right(uint32_t wrapped, uint32_t next);      /* G5 */
uint32_t bo3_wt4_gen_left(uint32_t wrapped);                      /* G6 */
int bo3_wt4_gen_avail(uint32_t region);                           /* G7: -1 = the game's own answer */
uint32_t bo3_wt4_gen_globe(uint32_t region);                      /* G8 / G9 */
uint32_t bo3_wt4_gen_map(uint32_t region);                        /* M1 */
uint32_t bo3_wt4_gen_count(uint32_t count);                       /* M2 */
int bo3_wt4_gen_suppress(void);                                   /* M3 / M4 */
int bo3_wt4_gen_focus(uint32_t menu, uint32_t arg);               /* M5: 1 = focus set, skip the game's */
uint32_t bo3_wt4_gen_marker(uint32_t state, uint32_t loc);        /* M6 */
uint32_t bo3_wt4_gen_tex(uint32_t region);                        /* T */

enum { BO3_WT4_ST_PAGES = 0, BO3_WT4_ST_MAPS = 1, BO3_WT4_ST_COUNTS = 2, BO3_WT4_ST_SUPPRESS = 3, BO3_WT4_ST_TEX = 4,
       BO3_WT4_ST_RETURNS = 5, BO3_WT4_ST_HIDDEN = 6, BO3_WT4_STATS = 7 };
uint32_t bo3_wt4_stats(uint32_t which);
uint32_t bo3_wt4_block_va(void);                                  /* tests: the entry block, 0 none */

/* the game: every usable, enabled mod's [bmashup.world_tour], once (exit 92 on a refusal) */
void bo3_wt4_game_declare(void);

#endif
