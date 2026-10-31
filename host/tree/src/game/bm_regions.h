/*
 * bm_regions.h - G8-RG1 EXPERIMENTAL: the region of an added track, from its registered track ID (content_count\regions\
 * REGION_TRACE.md, RG1_REPORT.md). G8-RG4 EXPERIMENTAL (phase 1, REGION4_PLAN.md s7): a fourth main region (code 4)
 * declared by a mod ([bmashup.regions], bm_tracks.h) for the Single Event menu.
 *
 * The game classifies a track's region in two ways: from the track's own ID (its first letter: U 0, E 1, A 2) or, at the
 * sites using sub_001586A0, from its entry in the 36-entry static table 0x39EBC0. An added track has no static entry
 * (index -1), so sub_001586A0 decodes the bytes in front of the table and answers 3 ("no region"). Three of its callers have
 * the track's ID pair at hand (they looked the index up from it one instruction before):
 *   sub_00155060 loc_0015507D   the radio DJ bank: "tracks\" + language + DJ[region] + ".xwb" (DJ[3] = "E_": no such file)
 *   sub_0006D4C0 loc_0006D81F   random track in the current track's region -> sub_0009ADB0(region)
 *   sub_000995F0 loc_00099980   the same, another screen
 * At those three, one generated line asks bo3_rg_gen_code(): for 3 and a track registered by bm_tracks.c (a declared,
 * appended track), the region of its ID; every other answer unchanged (retail tracks never reach 3 here: byte-identical
 * behaviour). An unregistered pair (missing metadata) keeps 3; sub_0009ADB0 then fails closed as in CC1.2 (exit 94 before
 * its division), and the DJ bank stays the game's own (missing file).
 * Not changed (they only filter or count, never index): sub_0001E3D0 / sub_0001E4C0 / sub_001994D0 (RG1_REPORT.md).
 *
 * G8-RG4 phase 1 (10 generated lines, REGION4_PLAN.md s7; every one returns the retail value when no fourth region is
 * declared):
 *   - a track whose ID starts with a declared letter (bm_tracks.c accepts it, e.g. OC_C1_V1) registers with code 4 + k
 *     (k = its declaration's index; phase 1: one region, code 4). The pair sites see its raw letter -> 3; four more
 *     bo3_rg_gen_code() marks turn that into 4 for a registered ID: the Single Event track filter (site 3, M3), the shared
 *     classifier sub_00157630 (site 4, M7), sub_0009ADB0's count and pick (sites 5 / 6, M8 / M9).
 *   - Menu A's region arrays (+0xCC codes[4], +0xDC texts[4], count +0xEC) are full at 4 entries (Random, USA, EUROPE,
 *     ASIA). bo3_rg_gen_menu_regions() (M1, after the game's presence loop, before its index clamp) copies them into a host
 *     guest block (codes[8], texts[8], 64 bytes, allocated at boot by bo3_rg4_prepare) and appends (4 + k, host text ID)
 *     for each declared region with a listable track (a registered track of that code in the game's track list), and only
 *     while the region's host text ID resolves in the table the game reads (bm_names.c): otherwise the region is not shown
 *     (fail closed, never an unresolvable text ID). +0xEC then holds the new count (5); the game's own clamp / wrap follow it.
 *     The in-object arrays keep their retail 4 entries; nothing is written beyond slot 3.
 *   - bo3_rg_gen_menu_code() (M2, M6) and bo3_rg_gen_menu_texts() (M4, M5) read the block while it is valid for that menu
 *     object (+0xEC still the count it wrote), else the game's own in-object arrays.
 *   - bo3_rg_gen_dj() (M10): the DJ bank name pointer of a code; for a declared region the retail bank its declaration
 *     names (phase 1: DJUS, PLACEHOLDER); every other code: the game's own table read.
 * All guest memory access goes through bm_guest.c (the runtime's own mappings).
 */
#ifndef BO3_BM_REGIONS_H
#define BO3_BM_REGIONS_H

#include <stdint.h>

#include "bm_tracks.h"           /* G8-TL: the track list's capacity */

#define BO3_RG_MAX BO3_CC_CAP    /* G8-TL: every added track can register (was 128) */
enum {
    BO3_RG_SITE_DJ = 0, BO3_RG_SITE_RANDOM_A = 1, BO3_RG_SITE_RANDOM_B = 2,
    BO3_RG_SITE_FILTER = 3,          /* G8-RG4 M3: sub_0008C920 loc_0008CC86, Single Event track filter */
    BO3_RG_SITE_CLASSIFY = 4,        /* G8-RG4 M7: sub_00157630 loc_00157657, the shared classifier */
    BO3_RG_SITE_COUNT = 5,           /* G8-RG4 M8: sub_0009ADB0 loc_0009AE13, random-in-region count */
    BO3_RG_SITE_PICK = 6,            /* G8-RG4 M9: sub_0009ADB0 loc_0009AF33, random-in-region pick */
    BO3_RG_SITES = 7
};

/* an added track's ID, at its registration (bm_tracks.c); 1, or 0 when full or not a US / EU / AS / declared-letter ID */
int bo3_rg_register(uint64_t id);
void bo3_rg_reset(void);                                     /* tests */
/* the region of a registered ID (0 / 1 / 2, or 4 + k for the k-th declared region), or -1 */
int bo3_rg_region_of(uint64_t id);
/* the generated-code mark after a classification (RG1: 3 sites after sub_001586A0; RG4: 4 pair sites) */
uint32_t bo3_rg_gen_code(uint32_t code, uint32_t lo, uint32_t hi, uint32_t site);
uint32_t bo3_rg_stats(uint32_t site, uint32_t which);        /* which 0: corrected, 1: left at 3 (unregistered) */

/* G8-RG4 */
#define BO3_RG4_CODE0     4u              /* the first declared region's code (3 = Random / "no region") */
#define BO3_RG4_MENUS     2u              /* menu objects with a host block (Menu A 0x55B6D0; later the twin) */
#define BO3_RG4_GAME_ROWS 4u              /* the in-object arrays' capacity (+0xCC / +0xDC) */
/* G8-TL: codes[32] + texts[32] per block (256 bytes): Random + USA / EUROPE / ASIA + every declarable region (23) fits */
#define BO3_RG4_SLOTS     32u
_Static_assert(BO3_RG4_SLOTS >= BO3_RG4_GAME_ROWS + BO3_CC_REGIONS_MAX, "the region row block holds every region");
#define BO3_RG4_DJ_TABLE  0x003EC8ECu     /* .rdata: DJ bank name pointers {"DJUS", "DJEU", "DJAS"}, then the language table */
/* boot (bm_tracks.c, after the tracks registered): the host blocks, only when a region is declared; 1 ok / nothing to do */
int bo3_rg4_prepare(uint32_t (*alloc)(uint32_t size, uint32_t align));
/* generated-code marks */
void bo3_rg_gen_menu_regions(uint32_t obj, uint32_t menu);   /* M1 */
uint32_t bo3_rg_gen_menu_code(uint32_t obj, uint32_t i);     /* M2, M6 */
uint32_t bo3_rg_gen_menu_texts(uint32_t obj);                /* M4, M5 */
uint32_t bo3_rg_gen_dj(uint32_t code);                       /* M10 */
/* 0 relocations, 1 regions not shown (no resolvable text), 2 DJ answers for a declared region, 3 menus refused (no block /
 * unexpected count) */
uint32_t bo3_rg4_stats(uint32_t which);

/* G8-TL EXPERIMENTAL (content_count\limits\LIMITS_REPORT.md): the Single Event track list beyond the game's 20 rows, and the
 * flags of track list entries 128 .. 382.
 *   - Menu A's track list (u64[20] +0xF0, u32[20] +0x190, count +0x1E0) is appended without a bound check by sub_0008C920 /
 *     sub_0008D020. Their six appends call bo3_tl_gen_put(), the one ID reader (sub_0008CDF0, the race start) calls
 *     bo3_tl_gen_get(), the two row widgets (sub_0008D330 / sub_0008D490) take bo3_tl_gen_texts() as the row's text array:
 *     entries below 20 are the object's own (written and read as the game does); with a host block (allocated at boot by
 *     bo3_tl_prepare only when some region's list needs more than 20 rows) every entry is also in the block (ids u64[384],
 *     texts u32[384]) and the widget reads the block. Without a block an entry 20+ is never written.
 *   - the count increments of every track list (Menu A x2, the twin x2, Menu B x2, Menu C x2) call bo3_tl_gen_list_inc():
 *     Menu A counts up to its capacity (20 without a block, 384 with); the other menus (no relocation: they never show a
 *     declared region) stop at 19, so their in-object lists can never overflow (they list the first 18 tracks + Random).
 *   - bo3_tl_gen_flag(base, i, which): the point-to-point flag (0) / flag B (1) of entry i; below 128 the game's own read,
 *     else the host table (bm_tracks.c). */
#define BO3_TL_MENUS      2u              /* menu objects with a list block (Menu A 0x55B6D0, and one spare) */
#define BO3_TL_BLOCK      (12u * BO3_TL_SLOTS)   /* ids u64[384] then texts u32[384]: 4608 bytes */
enum { BO3_TL_SITE_A_BUILD = 0, BO3_TL_SITE_A_INPUT = 1, BO3_TL_SITE_TWIN_BUILD = 2, BO3_TL_SITE_TWIN_INPUT = 3,
       BO3_TL_SITE_B_BUILD = 4, BO3_TL_SITE_B_INPUT = 5, BO3_TL_SITE_C_BUILD = 6, BO3_TL_SITE_C_INPUT = 7, BO3_TL_SITES = 8 };
/* the largest Single Event list the current track list gives (Random + the tracks of one region letter), and its letter */
uint32_t bo3_tl_largest_list(char *letter);
/* boot (bm_tracks.c, after the appends): the list blocks when a list needs more than 20 rows. 1 ok (also: not needed), 0 no
 * memory (the game build stops: exit 92) */
int bo3_tl_prepare(uint32_t (*alloc)(uint32_t size, uint32_t align));
void bo3_tl_reset(void);                                     /* tests: no blocks, statistics 0 */
/* generated-code marks */
void bo3_tl_gen_put(uint32_t obj, uint32_t i, uint32_t which, uint32_t v);   /* which 0 id lo, 1 id hi, 2 text ID */
uint32_t bo3_tl_gen_get(uint32_t obj, uint32_t i, uint32_t which);           /* which 0 id lo, 1 id hi */
uint32_t bo3_tl_gen_texts(uint32_t obj);                     /* the track row's text-ID array (guest VA) */
uint32_t bo3_tl_gen_list_inc(uint32_t obj, uint32_t count, uint32_t site);   /* the new count */
uint32_t bo3_tl_gen_flag(uint32_t base, uint32_t i, uint32_t which);
/* 0 entries stored beyond 20 (block), 1 entries dropped (no block / beyond the block), 2 saturated increments, 3 flag reads
 * from the host table, 4 list blocks in use */
uint32_t bo3_tl_stats(uint32_t which);
uint32_t bo3_tl_block_va(uint32_t obj);                      /* tests: the block of obj, 0 = none */

#endif
