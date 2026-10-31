/*
 * bm_tracks.h - G8-CC1 EXPERIMENTAL: additional track entries declared by mods (content_count\CONTENT_COUNT_INVENTORY.md).
 *
 * The game registers its tracks in Tracks/tlist.bin (read by the boot loader sub_00015F10 into a 0x1000-byte buffer at
 * 0x4D3000): +4 count, +0x8 u32[128] point-to-point flag, +0x208 u32[128] flag B (1 for US / EU, 0 for AS), +0x408
 * u64 base-40 IDs ("US_C1_V1"). Retail has 36. The folder of a track is cut from its ID
 * (sub_001574F0: tracks/<id 0..1>/<id 3..4>_<id 6..7>/).
 *
 * G8-TL EXPERIMENTAL (content_count\limits\LIMITS_REPORT.md): the buffer is the loader's whole 0x1000-byte read (state 5:
 * 0x1000 bytes into loader object + 0x2BE60 = 0x4D3000; the next field, + 0x2CE60 = 0x4D4000, is the loader's own flag
 * byte), no generated code names an address in 0x4D3808 .. 0x4D3FFF, and every ID reader indexes +0x408 + 8 * entry, so
 * the ID array holds BO3_CC_CAP = (0x1000 - 0x408) / 8 = 383 entries. The two flag arrays are u32[128] (entry 128 of flag A
 * is flag B's entry 0): entries 128 .. 382 keep their flags in a host table, and the five generated reads of a flag
 * (sub_00078DD0 x2, sub_0009BF20, sub_001AAE30, sub_001575A0) ask bo3_tl_gen_flag() (bm_regions.c), which answers the
 * game's own read below 128.
 *
 * A mod declares tracks it adds (its files folder must hold the track's Gamedata.bgd, static.dat, streamed.dat and
 * enviro.dat):
 *
 *   [bmashup.tracks]
 *   version = 1
 *   add = ["US_C6_V1"]          # IDs "RR_NN_VN": region US / EU / AS, base-40 characters
 *   point_to_point = []         # those of `add` that are point-to-point (flag A); default: circuits
 *
 * After the game has read tlist.bin (the loader's state 6 is complete, loc_00016124) the host appends every declared
 * track, in the mod list's order, to the buffer the game reads. Flag B follows the region as in the retail file (AS 0,
 * US / EU 1). Nothing else of the file changes. A declaration this build cannot take stops the start (exit 92): a version
 * other than 1, an unknown key, a malformed ID, a region other than US / EU / AS (a fourth region is not supported: its
 * code collides with the Single Event menu's Random entry), an ID the game or another mod already has, a missing file,
 * more than BO3_CC_REGION_LIST tracks in one region (the Single Event list, G8-TL: the host block), or more than
 * BO3_CC_CAP tracks (G8-TL: 383).
 *
 * What an added track is NOT: it has no entry in the game's own 36-entry track table (.rdata 0x39EBC0), so it has no
 * name (generic text 0x4E9 / 0x4EA), no map / HUD data of its own (those reads fall on neighbouring table bytes), no
 * Single Event lock, and no progress slot: its results are not saved. The three places that would WRITE with the
 * missing index (-1) are guarded (bo3_cc_gen_skip): sub_0001BA00 / sub_0001BAF0 (per-track bests in the profile) and
 * sub_0001EE80 (per-track records), so they skip instead of writing in front of their arrays.
 */
#ifndef BO3_BM_TRACKS_H
#define BO3_BM_TRACKS_H

#include <stddef.h>
#include <stdint.h>

#define BO3_CC_TLIST_VA     0x004D3000u
#define BO3_CC_TLIST_SIZE   0x1000u
#define BO3_CC_OFF_A        0x8u
#define BO3_CC_OFF_B        0x208u
#define BO3_CC_OFF_ID       0x408u
/* G8-TL: the ID array's capacity inside the 0x1000-byte buffer (was 128, the flag arrays' size) */
#define BO3_CC_CAP          ((BO3_CC_TLIST_SIZE - BO3_CC_OFF_ID) / 8u)   /* 383 */
#define BO3_CC_FLAG_CAP     128u         /* u32[128] flag arrays in the buffer; entries 128 .. 382: host table */
#define BO3_CC_RETAIL       36u          /* the retail file's entries */
#define BO3_CC_MAX_DECL     BO3_CC_CAP   /* tracks one mod may add (G8-TL: was 16, a sanity bound; now the format's) */
/* G8-TL: the Single Event track list. The game's own list in the menu object is u64[20] at +0xF0 / u32[20] at +0x190, count
 * +0x1E0, entry 0 = Random, appended without a bound check (sub_0008C920 / sub_0008D020). The generated appends and reads of
 * Menu A go through bm_regions.c (bo3_tl_gen_put / get / texts): entries 20 and up live in a host block of BO3_TL_SLOTS. */
#define BO3_TL_GAME_ROWS    20u          /* the in-object list's capacity (Random + 19) */
#define BO3_TL_SLOTS        (BO3_CC_CAP + 1u)   /* 384: Random + every track the track list can hold */
#define BO3_CC_REGION_LIST  (BO3_TL_SLOTS - 1u) /* 383 tracks per region (was 19) */

enum { BO3_CC_SITE_BEST1 = 0, BO3_CC_SITE_BEST2 = 1, BO3_CC_SITE_RECORDS = 2, BO3_CC_SITES = 3 };

typedef struct bo3_cc_decl {
    int present;
    uint32_t n;
    uint64_t id[BO3_CC_MAX_DECL];
    uint32_t p2p[BO3_CC_MAX_DECL];
} bo3_cc_decl;

/* base-40 IDs (sub_001AECC0 / sub_001AEAA0): 1 and *out, or 0 */
int bo3_cc_encode(const char *s, uint64_t *out);
void bo3_cc_decode(uint64_t v, char out[13]);
/* "RR_NN_VN" with region US / EU / AS, or (G8-RG4) whose first letter is a declared fourth region's: 1, else 0 with why */
int bo3_cc_id_ok(const char *s, char *why, size_t wn);

/* G8-RG4 EXPERIMENTAL (content_count\regions\REGION4_PLAN.md s1): main regions declared by mods (G8-TL: up to 23).
 *
 *   [bmashup.regions]
 *   version = 1
 *   add = ["O = OCEANIA", "B = BALTIC"]  # "LETTER = TEXT": one letter A-Z other than U / E / A (the game's own); text
 *                             # 1 .. 17 characters A-Z a-z 0-9, space and - ' . & (the retail font)
 *   dj = ["O = DJUS", "B = DJEU"]  # optional, per region: the announcer bank, one of the game's DJUS / DJEU / DJAS
 *                             # (default DJUS; a retail bank only, PLACEHOLDER)
 *
 * A track whose ID starts with a declared letter (e.g. OC_C1_V1, folder Tracks\OC\C1_V1) is then accepted by
 * bo3_cc_id_ok; its region code is 4 + k (k = the declaration's index, in the mod list's order; the code is never saved).
 * The same letter from two mods must carry the same text and bank. Refused (exit 92, as a track declaration): another
 * version, an unknown key, a malformed entry, U / E / A, a text the menus cannot show. With no [bmashup.regions] anywhere
 * nothing changes (retail). G8-TL: the region identity is the ID's first letter, so 26 - 3 = 23 regions can exist. */
#define BO3_CC_REGIONS_MAX     23u       /* G8-TL: every letter A-Z other than U / E / A (was 1, phase 1) */
#define BO3_CC_REGION_TEXT_MAX 17u       /* the longest retail location / region text */
typedef struct bo3_cc_region {
    char letter;                         /* 'O' */
    char text[BO3_CC_REGION_TEXT_MAX + 1];
    uint32_t dj;                         /* the retail bank: 0 DJUS, 1 DJEU, 2 DJAS */
} bo3_cc_region;
/* one mod.toml's [bmashup.regions]: 1 (also when absent; the declarations are kept), or 0 with why (nothing kept) */
int bo3_cc_regions_parse(const char *text, size_t n, char *why, size_t wn);
uint32_t bo3_cc_region_count(void);
const bo3_cc_region *bo3_cc_region_at(uint32_t k);
int bo3_cc_region_of_letter(char c);     /* k, or -1 (also for U / E / A) */
void bo3_cc_regions_reset(void);         /* tests */
/* the game build: every usable, enabled mod's [bmashup.regions], once (exit 92 on a refusal); called before the first
 * track or name declaration is read */
void bo3_cc_regions_game_load(void);

/* the [bmashup.tracks] table of n bytes of a mod.toml: 1 with *out (present 0 when absent), or 0 with why */
int bo3_cc_parse(const char *text, size_t n, bo3_cc_decl *out, char *why, size_t wn);

/* append the declared tracks to a tlist image (the game's buffer, or a test's): 1, or 0 with why (nothing written). G8-TL:
 * the flags of entries 128 .. 382 go to the host table (one table: the game has one track list; tests reset it) */
typedef int (*bo3_cc_files_fn)(void *user, int mod, const char *rel);  /* 1 when mod's files folder holds rel */
int bo3_cc_append(uint8_t *tlist, const bo3_cc_decl *d, int mod, bo3_cc_files_fn files, void *user, char *why, size_t wn);
/* G8-TL: flag A (which 0) / B (1) of entry i: below 128 from the image, else from the host table (0 beyond what was added) */
uint32_t bo3_cc_flag(const uint8_t *tlist, uint32_t i, uint32_t which);
uint32_t bo3_cc_flag_ext(uint32_t i, uint32_t which);       /* the host table only (entries 128 .. 382), 0 otherwise */
void bo3_cc_flags_reset(void);                              /* tests */

/* guarded sites: 1 = the track index is -1 (not in the game's table): skip; counted, logged once per site */
int bo3_cc_gen_skip(uint32_t site, uint32_t index);
uint32_t bo3_cc_skips(uint32_t site);

/* G8-CC1.1 (F1, CC1_PRERUNTIME_REVIEW.md): the records panel sub_000EAC60 indexes the per-track records with the track's
 * static index unchecked; for -1 it would read 0x44D450 (unlock-array snapshots, not records) and copy its "names" with an
 * unbounded wide-string copy (sub_000EC920) into 18-byte UI slots. bo3_cc_gen_record(edi) returns the address unchanged for
 * any other record, and for 0x44D450 a stand-in record: 0x230 bytes, zero, its 20 name fields (mode * 0x8C + k * 0x1C)
 * holding the game's own empty marker L"#@|^" (.data 0x3C83D4), so the panel prints its "-" fallback. Counted, logged once. */
#define BO3_CC_RECORDS_VA    0x0044D680u
#define BO3_CC_RECORD_SIZE   0x230u
#define BO3_CC_RECORD_MINUS1 (BO3_CC_RECORDS_VA - BO3_CC_RECORD_SIZE)
void bo3_cc_fill_empty_record(uint8_t *rec);                 /* the stand-in's 0x230 bytes */
void bo3_cc_set_empty_record_va(uint32_t va);               /* where it is (guest); 0 = none */
uint32_t bo3_cc_gen_record(uint32_t rec_va);
uint32_t bo3_cc_record_redirects(void);

/* G8-CC1.2 (bm_tracks_progress.c): saved results of added tracks in the progress sidecar (content_count\sidecar) */
void bo3_cc_fresh_record(uint8_t *rec, uint32_t fresh_time_bits);
void bo3_cc_set_save_dir(const char *dir);
void bo3_cc_progress_add(const char *mod_id, const char *mod_ver, uint64_t id, const char *id_text, uint32_t shadow_va);
void bo3_cc_progress_start(void);
uint32_t bo3_cc_current_shadow(void);
int bo3_cc_gen_best(uint32_t site, uint32_t index, float v);
void bo3_cc_gen_total(uint32_t index, uint32_t add);
int bo3_cc_gen_insert_skip(uint32_t index);
void bo3_cc_gen_race_end_reset(void);
uint32_t bo3_cc_gen_insert_record(uint32_t rec_va);
uint32_t bo3_cc_gen_record_for(uint32_t rec_va, uint32_t id_lo, uint32_t id_hi);   /* G8-CC1.3: the records screen's own track */
void bo3_cc_gen_recorded(void);
void bo3_cc_gen_unsupported(uint32_t what);
/* 0 records redirected, 1 values captured, 2 commits, 3 commit errors, 4 (cand2) added tracks refused by the progress
 * table (more than BO3_CC_CAP; logged once) */
uint32_t bo3_cc_progress_stats(uint32_t which);
/* G8-WT1: the sidecar store (opened on demand; NULL when none): the store provider of bm_xevents.c */
struct bm_prog;
struct bm_prog *bo3_cc_progress_store(void);

/* the game build: every usable, enabled mod's declaration into the buffer at 0x4D3000 (exit 92 on a refusal) */
void bo3_cc_gen_tlist_loaded(void);

#endif
