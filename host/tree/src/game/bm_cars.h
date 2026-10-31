/*
 * bm_cars.h - GP-CARS2 + GP-VEH1 EXPERIMENTAL: cars ADDED by data mods (atlas gp\atlas\CARS.md s7, CARS_FEASIBILITY.md kind E;
 * veh1: slices\veh1\INTERFACE.md, SCALE_TARGETS.md). Contract [bmashup.cars] version 1 (cars2) and version 2 (veh1):
 *
 *   [bmashup.cars]
 *   version = 2                                   # 1 accepts only add / names / physics_scale (the cars2 contract)
 *   add = ["BMNECAR1 = SPRTCAR1"]                 # "<NEW ID> = <DONOR ID>": NEW ID = 5..12 of A-Z 0-9 whose first four
 *                                                 # characters are the donor's retail class (COMP MSCL CUPE SPRT SUPR HSPC
 *                                                 # HEVY: the car joins that series) or (v2) the prefix of a series declared
 *                                                 # in [bmashup.series] (bm_veh.h) by this mod or one it requires;
 *                                                 # DONOR = a retail race car (in the game's 67-car table)
 *   names = ["BMNECAR1 = Neon Dart"]              # optional: 1 .. 21 characters A-Z a-z 0-9 space - ' . &
 *   physics_scale = ["BMNECAR1 | Drag Coef = 0.9"]  # optional (Drag Coef 0.25 .. 4, Max Speed In Boost 0.5 .. 2; the latter
 *                                                 # is the car's TOP-SPEED LIMIT: it caps normal AND boost top speed)
 *   model = ["BMNECAR1 = donor"]                  # v2 optional: the car uses its DONOR's model / audio files (no pveh files)
 *   unlock = ["BMNECAR1 = cars:20"]               # v2 optional: open | cars:N | car:<RETAIL ID> | series:<retail class>
 *   ai = ["BMNECAR1"]                             # v2 optional: the car may be chosen for AI opponents (bm_veh.h)
 *   photos = ["BMNECAR1 = mytex"]                 # v1 / v2 optional (fetex1 INTERFACE s2): the garage photo, a front-end texture
 *                                                 # registered by fetex ([bmashup.textures]); checked here, bound by fetex. On a
 *                                                 # host without fetex (this slice host) the donor's photo is shown (logged)
 *
 * Files the mod ships unless model = donor: pveh\<PREFIX>\<REST>.bgv (<= 0x9D800 bytes, a multiple of 0x800), .hwd, .lwd.
 *
 * What the host does (all in the game's own data, nothing in the save):
 *   - after the game read pveh\vlist.bin (boot loader, loc_000160EE) the host builds the RELOCATED vehicle list (bm_veh.c,
 *     vlist2: the same SoA shape with capacity C, guest heap, allocated once) holding the retail entries unchanged and every
 *     admitted mod's cars (flag A 1, flag B / word C / value D copied from the donor). Without car mods nothing is relocated.
 *   - the car has no entry in the game's 67-car career table: the game treats it as OPEN unless a veh1 unlock rule says
 *     otherwise (bm_veh.c marks at the -1 sites); the AI picker never chooses it unless it is declared ai (bm_veh.c).
 *   - physics: the ValueDB file of the car is the DONOR's (sub_00132D10, sub_000C0080); declared scales on its own block.
 *   - garage photo: the donor's Frontend.txd entry (sub_0002DDF0 miss) until fe's texture interface is consumed.
 *   - text: garage name / award text from host text IDs (bm_names.h).
 *   - career index -1 consumers that read past their tables or store -1 get the DONOR's index (bo3_car_gen_sidx).
 * Admission (veh1, contracts v0.1 s4): per mod, transactional. Stage 1 (bo3_car_game_declare: parse, IDs, files, sizes, series
 * references, totals) and stage 2 (the vehicle-list append: the ID is new to the list, the donor is a race car in it, rows per
 * series <= 20, capacity) refuse the WHOLE mod with a logged reason ([VEH] REFUSED); everything of that mod is rolled back
 * (cars, texts, series, paints) and the game continues with the other mods. (cars2 exited with 92: changed in veh1.)
 * Removing the mod: no added entry, no text, no alias, nothing in the save: the profile loads as retail.
 * Thread: game thread (boot loader, front end, race set-up). Lifetime: process (declarations fixed at boot).
 */
#ifndef BO3_BM_CARS_H
#define BO3_BM_CARS_H

#include <stddef.h>
#include <stdint.h>

#define BO3_CAR_VLIST_VA    0x004D2000u
#define BO3_CAR_VLIST_SIZE  0x1000u
#define BO3_CAR_CAP         128u          /* the RETAIL image's capacity (loops cmp 0x80: sub_001A2860, sub_0017D980) */
#define BO3_VEH_CAP         1024u         /* veh1: the configured registry capacity (SCALE_TARGETS.md s2) */
#define BO3_CAR_RETAIL_N    107u
/* the SoA layout of a vehicle-list image of capacity c (c = 128: the retail file) */
#define BO3_VL_SIZE(c)      (8u + 24u * (uint32_t)(c))
#define BO3_VL_OFF_A(c)     (8u)
#define BO3_VL_OFF_B(c)     (8u + 4u * (uint32_t)(c))
#define BO3_VL_OFF_ID(c)    (8u + 8u * (uint32_t)(c))
#define BO3_VL_OFF_C(c)     (8u + 16u * (uint32_t)(c))
#define BO3_VL_OFF_D(c)     (8u + 20u * (uint32_t)(c))
#define BO3_CAR_OFF_A       BO3_VL_OFF_A(128)    /* 0x008 */
#define BO3_CAR_OFF_B       BO3_VL_OFF_B(128)    /* 0x208 */
#define BO3_CAR_OFF_ID      BO3_VL_OFF_ID(128)   /* 0x408 */
#define BO3_CAR_OFF_C       BO3_VL_OFF_C(128)    /* 0x808 */
#define BO3_CAR_OFF_D       BO3_VL_OFF_D(128)    /* 0xA08 */
#define BO3_CAR_STATIC_VA   0x0039FC90u   /* .rdata u64[67]: the career table (sub_00158A60) */
#define BO3_CAR_STATIC_N    67u
#define BO3_CAR_ROWS        20u           /* garage rows per list (list object 0x5560F0, sub_000BE250) */
#define BO3_CAR_HIDDEN_NTH  9u            /* sub_000BE250 skips a class's 10th entry unless the list's +0x265 flag */
#define BO3_CAR_MODEL_MAX   0x9D800u      /* race-car model slot (STREAMING_POOL_MAP s1.4) */
#define BO3_CAR_MAX_DECL    (BO3_VEH_CAP - BO3_CAR_RETAIL_N)   /* 917 added cars (all mods) */
#define BO3_CAR_NAME_MAX    21u
#define BO3_CAR_SCALES      2u

/* veh1 unlock rule (bm_veh.c evaluates it from the game's derived open-car bytes 0x44CFC8) */
enum { BO3_RULE_OPEN = 0, BO3_RULE_CARS = 1, BO3_RULE_CAR = 2, BO3_RULE_SERIES = 3 };
typedef struct bo3_veh_rule {
    uint8_t kind;
    uint8_t cls;                          /* SERIES: the retail class 0..6 */
    uint16_t n;                           /* CARS: open retail cars needed (1..67) */
    uint64_t id;                          /* CAR: the retail car */
} bo3_veh_rule;

typedef struct bo3_car_scale {
    uint16_t block_off;                   /* ValueDB block offset (bm_vphys_catalog.h) */
    float scale;
} bo3_car_scale;

typedef struct bo3_car_entry {
    uint64_t id, donor;
    char name[BO3_CAR_NAME_MAX + 1];      /* "" = none (the game's fallback text) */
    uint32_t nscale;
    bo3_car_scale scale[BO3_CAR_SCALES];
    uint8_t model_donor;                  /* v2 model = donor */
    uint8_t ai;                           /* v2 ai */
    uint8_t has_rule;                     /* v2 unlock (else the series' rule, else open) */
    uint8_t series_prefix;                /* the ID's prefix is not a retail class (a [bmashup.series] prefix) */
    uint8_t photo;                        /* fetex1 s2: photos binds a garage photo (served by fetex; this host keeps the donor's) */
    bo3_veh_rule rule;
} bo3_car_entry;

typedef struct bo3_car_decl {
    int present;
    int version;
    uint32_t n, cap;
    bo3_car_entry *e;                     /* malloc'ed by bo3_car_parse; bo3_car_decl_free */
} bo3_car_decl;

/* the class code 0..6 of a 4-character retail prefix (COMP MSCL CUPE SPRT SUPR HSPC HEVY), else -1 */
int bo3_car_class_of(const char *id);
/* base-40 vehicle IDs */
int bo3_car_enc(const char *s, uint64_t *out);
void bo3_car_dec(uint64_t v, char out[13]);
/* one mod.toml's [bmashup.cars] (n bytes): 1 with *out (present 0 when absent), or 0 with why */
int bo3_car_parse(const char *text, size_t n, bo3_car_decl *out, char *why, size_t wn);
void bo3_car_decl_free(bo3_car_decl *d);

/* append one mod's declarations to a vehicle-list image of capacity cap (the guest image or a test's). static_ids = the career
 * table (67 x u64); files(user, mod, rel, size) = 1 when the mod ships rel. 1, or 0 with why (nothing written, nothing
 * registered). Registered cars are what the generated-code calls answer for. */
typedef int (*bo3_car_files_fn)(void *user, int mod, const char *rel, uint32_t *size);
int bo3_car_append(uint8_t *vlist, uint32_t cap, const uint8_t *static_ids, const bo3_car_decl *d, int mod,
                   bo3_car_files_fn files, void *user, char *why, size_t wn);
/* veh1: the retail image (0x1000 B) in the layout of capacity cap (img: BO3_VL_SIZE(cap) bytes) */
void bo3_vl_relayout(uint8_t *img, uint32_t cap, const uint8_t *retail);
uint32_t bo3_car_count(void);
const bo3_car_entry *bo3_car_at(uint32_t k);
int bo3_car_find(uint64_t id);            /* k, or -1 (hashed) */
int bo3_car_donor_sidx(uint32_t k);       /* the donor's career index (0..66) */
int bo3_car_mod_of(uint32_t k);           /* the declaring mod index */
void bo3_car_set_mod_name(int mod, const char *id);   /* the mod index -> its manifest id (canonical IDs) */
const char *bo3_car_mod_name(int mod);
void bo3_cars_reset(void);                /* tests */

/* the generated-code calls (bo3_cars_gen.h) */
#include "bo3_cars_gen.h"

/* stats: 0 appended, 1 physics aliases, 2 block scales applied, 3 photo fallbacks, 4 index maps, 5 text swaps,
 * 6 mods refused (stage 1 + 2), 7 model aliases */
uint32_t bo3_car_stats(uint32_t which);
void bo3_car_stat_add(uint32_t which);

#ifdef BO3_CARS_GAME
void bo3_car_game_declare(void);          /* bm_names.c bo3_nm_game_load: parse every mod's declarations (stage 1) */
#endif

#endif
