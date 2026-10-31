/*
 * bm_fetex.h - GP-FETEX1 EXPERIMENTAL: additive front-end textures declared by data mods (gp\slices\fetex1: INTERFACE.md,
 * TRACE.md; contract gp\CONTRACTS_CONTENT.md s2 / s4).
 *
 *   [bmashup.textures]
 *   version = 1
 *   txd = "art/oceania.txd"      # one Criterion texture dictionary in the mod folder (gp\tools\fetex pack)
 *   class = "frontend"           # v1: the only usage class with external textures
 *
 *   [bmashup.wt_map_art]         # bindings of the 4th World Tour region's map page (wt4 borrowed view)
 *   version = 1
 *   region = "O"                 # the [bmashup.world_tour] region letter
 *   art = ["SatMapU1_1 = oceania_1_1", ...]   # retail slot name = texture (local name or "<mod-id>/<name>")
 *   place = "HARBOUR CITY"       # optional: the location's place name on that map page (1..17 characters)
 *   ticker = "WELCOME TO OCEANIA...    PLEASE SELECT A LOCATION"   # optional: the map ticker (1..60 characters)
 *
 *   [bmashup.cars]
 *   photos = ["COMPBM01 = compbm01_photo"]    # garage photo of an added car (veh's table; read here, see INTERFACE.md)
 *
 * Registration = presence: every TXD entry is "<mod-id>/<entry name>". A texture is used only where a binding names it:
 *   NAME binding  - the game looks a name up in Data/Frontend.txd (sub_0002DDF0) and retail has no such entry: the bound
 *                   texture answers (before cars2's donor-photo fallback). Retail names are never shadowed.
 *   SLOT binding  - while the wt4 4th-region map page is shown (bo3_wt4_active), a read of the front-end slot table
 *                   (0x464418, the 143 names sub_00062D60 resolves) at a bound retail slot answers the bound texture.
 *   TEXT binding  - while that page is shown, the location's place name / the map ticker text IDs answer host texts.
 * Admission (bm_admit.c, per mod, before anything is installed): structure + capability list + names + bounds + binding
 * targets + binding keys another mod holds; a failure refuses the WHOLE mod (made "not usable", reason on the Mods page).
 * Install: one guest contiguous block for every admitted texture, allocated + filled + fixed up (the game's own rules,
 * sub_001BEEF0 / sub_001C8E20) at the first hook call; never freed. A failure there -> every binding answers the retail /
 * donor value (logged once, counted).
 */
#ifndef BO3_BM_FETEX_H
#define BO3_BM_FETEX_H

#include <stddef.h>
#include <stdint.h>

#define BO3_FETEX_VERSION        1u
/* GP-P4.3 M2 (P4_3_REPORT s3.2): the configured limits from memory + consumers. Pool = the ceiling of ONE contiguous block
 * (allocated = the admitted TXDs, not the ceiling) in the 64 MiB contiguous window: game peak ~38 MiB (fetex1 TRACE, RT) +
 * 12 MiB + veh1 palettes <= 1.06 MiB = ~51 MiB, ~13 MiB headroom. Photos: veh1 SCALE_TARGETS addendum - 512 garage photos
 * of 128 x 64 P8 x 8 palettes (~16.5 KiB each, ~8.3 MiB) + 256 other entries (map art, markers) within the 12 MiB pool.
 * Per mod 256 (one photo pack for a 64 KiB mod.toml car mod). Format ceiling (TXD table rows) 4096: not the limit. */
#define BO3_FETEX_MAX_PER_MOD    256u          /* GP-P4.3 M2: was 64 */
#define BO3_FETEX_MAX            768u          /* GP-P4.3 M2: was 256 */
#define BO3_FETEX_MAX_ENTRY      (1u << 20)
#define BO3_FETEX_POOL_MAX       (12u << 20)   /* GP-P4.3 M2: was 8 MiB */
/* main18: mods with [bmashup.textures] 16 -> 64. Not tied to a game pool: the guest memory is the ONE pool block above
 * (BO3_FETEX_POOL_MAX, allocated = the admitted TXDs) and its entry limits, unchanged; per mod only host memory (a TXD
 * copy pointer and an admission row). The engine-side ceiling stays the 12 MiB pool / 768 entries. */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BO3_FETEX_MAX_MODS       16u           /* mods with [bmashup.textures] (legacy limits) */
#else
#define BO3_FETEX_MAX_MODS       64u           /* mods with [bmashup.textures] */
#endif
#define BO3_FETEX_MAX_NAMEB      512u          /* name bindings (garage photos); GP-P4.3 M2: was 64 (veh1 photo ceiling) */
#define BO3_FETEX_MAX_SLOTB      48u           /* slot bindings */
/* GP-P4.3 M5 (decision, fetex finding "photo palettes vs model paints"): a garage photo's colours follow veh1's paint
 * definitions - photo palette k = the car's retail-index paint k (k < the photo's palette count: retail rule); a registered
 * paint ([bmashup.paints] ramp) = the SAME ramp applied to the photo's palettes 0 / 1 (bm_vpaint.c G3); a `file` paint =
 * photo palette 0. An authored photo therefore carries its model's in-file paints as palettes 0..n-1 (>= 2, differing in
 * the paint-ramp entries). */
#define BO3_FETEX_NAME_MAX       31u
#define BO3_FETEX_PLACE_MAX      17u           /* = BO3_NM_LOC_MAX (the longest retail location) */
#define BO3_FETEX_TICKER_MAX     60u
#define BO3_FETEX_FE_DICT        0x004D41D0u   /* [0x4D41D0] = the loaded Data/Frontend.txd (front-end object + 0x1C8) */
#define BO3_FETEX_SLOTS          0x00464418u   /* u32[143] texture pointers resolved by sub_00062D60 */
#define BO3_FETEX_NSLOTS         143u
#define BO3_FETEX_EXIT_DECL      92

enum { BO3_FETEX_P8 = 0x0B, BO3_FETEX_DXT1 = 0x0C, BO3_FETEX_DXT5 = 0x0F,
       BO3_FETEX_ARGB = 0x06 };   /* main21 patch 128: swizzled A8R8G8B8, class "global" only (lossless, no palette) */
enum { BO3_FETEX_TEXT_PLACE = 0, BO3_FETEX_TEXT_TICKER = 1 };

typedef struct bo3_fetex_info {
    char canonical[96];                 /* "<mod-id>/<name>" */
    uint32_t fmt, w, h, palettes, bytes;
    uint32_t va;                        /* guest VA of the texture header, 0 before the install / after a failure */
} bo3_fetex_info;

/* ---- pure parts (tests, bm_admit.c through bm_fetex_parse.inc) ---- */
/* strict TXD check of one mod's file against the front-end capability list; 1 ok, 0 with why */
int bo3_fetex_check_txd(const uint8_t *b, size_t n, char *why, size_t wn);

/* ---- registry (host; bo3_fetex_declare_mod is called per admitted mod in the mod list's order) ---- */
void bo3_fetex_reset(void);                                     /* tests */
/* one admitted mod: its mod.toml text + its TXD bytes (NULL when it has no [bmashup.textures]); 1 ok, 0 with why and
 * nothing of the mod kept (transactional) */
int bo3_fetex_declare_mod(const char *mod_id, const char *const *requires, int nreq, const char *text, size_t n,
                          const uint8_t *txd, size_t txd_n, char *why, size_t wn);
uint32_t bo3_fetex_count(void);
int bo3_fetex_find(const char *canonical, bo3_fetex_info *out); /* 1 found */
/* the wt4 region letter the map-art bindings belong to ('\0' none) */
char bo3_fetex_map_region(void);
const char *bo3_fetex_map_text(uint32_t kind);                  /* place / ticker, NULL none */

/* guest access + allocation (tests give their own memory; the game build bm_guest.c + xbox_ContiguousAlloc) */
typedef struct bo3_fetex_guest {
    uint8_t *(*ptr)(void *u, uint32_t va, uint32_t size);       /* host pointer of a guest range, NULL refused */
    uint32_t (*alloc)(void *u, uint32_t size);                  /* guest VA (contiguous memory), 0 failure */
    int (*active)(void *u);                                     /* the wt4 4th-region map is shown */
    uint32_t (*text_id)(void *u, uint32_t kind, uint32_t dflt); /* bm_names: a host text ID, else dflt */
    uint32_t (*car_photo)(void *u, uint32_t dict, uint32_t name_va);   /* cars2's donor fallback (0 none) */
    void *user;
} bo3_fetex_guest;
void bo3_fetex_set_guest(const bo3_fetex_guest *g);

/* the install (normally done by the first hook call): 1 installed (or nothing to install), 0 failed (bindings inert) */
int bo3_fetex_install(void);
int bo3_fetex_installed(void);                                  /* 1 installed, 0 not yet, -1 failed */

/* generated-code marks (bo3_fetex_gen.h) */
uint32_t bo3_fetex_gen_miss(uint32_t dict, uint32_t name_va);   /* sub_0002DDF0 miss: texture VA or 0 */
uint32_t bo3_fetex_gen_slot(uint32_t slot, uint32_t retail);    /* a 0x464418 slot read */
uint32_t bo3_fetex_gen_text(uint32_t kind, uint32_t dflt);      /* place / ticker text ID */

enum { BO3_FETEX_ST_NAME_HITS = 0, BO3_FETEX_ST_SLOT_HITS = 1, BO3_FETEX_ST_TEXT_HITS = 2, BO3_FETEX_ST_FALLBACKS = 3,
       BO3_FETEX_ST_INSTALLS = 4, BO3_FETEX_ST_INSTALL_FAIL = 5, BO3_FETEX_ST_GLOBAL = 6, BO3_FETEX_STATS = 7 };
/* main21 patch 121: class "global" - right after the game fixed up a loaded Data/Global.txd (sub_00015F10 loc_00015FD5, EBP + 0x2AE40
 * = the dictionary = [0x4D1FE0]) each replaced entry's texture header (+0 .. +0x47: the D3D resource words, palette pointers,
 * format / size / bits) and palette count (+0x69) are taken from the mod's pool entry; the name stays. Every pointer the game
 * cached to the entry then draws the mod's texture. Returns the number replaced. */
#define BO3_FETEX_GLOBAL_DICT    0x004D1FE0u
uint32_t bo3_fetex_gen_global(uint32_t dict);
/* main21 patch 127 (C3 run finding: the game loads Data/Global.txd at boot, BEFORE the mods' textures are declared, so the load
 * mark saw no replacement): right after the declarations, the replacements are applied to the Global.txd already loaded (the
 * dictionary at [BO3_FETEX_GLOBAL_DICT], 0 = not loaded yet -> the load mark does it). Shadows / sparks are drawn only in a race,
 * after this. Returns the number replaced. */
uint32_t bo3_fetex_late_global(void);
uint32_t bo3_fetex_stats(uint32_t which);
uint32_t bo3_fetex_pool_va(void);
uint32_t bo3_fetex_pool_bytes(void);

/* the game: every usable, enabled mod's declarations (bm_names.c bo3_nm_game_load, after the cars); exit 92 on a
 * declaration the admission let through but that cannot be applied now (a changed file) */
void bo3_fetex_game_declare(void);

#endif
