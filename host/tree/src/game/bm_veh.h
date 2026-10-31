/*
 * bm_veh.h - GP-VEH1 EXPERIMENTAL: the scaled vehicle registry, new car series, progression, AI eligibility and the paint
 * registry (slices\veh1\INTERFACE.md, SCALE_TARGETS.md; cars: bm_cars.h).
 *
 *   [bmashup.series]
 *   version = 1
 *   add = ["neon = BMNE"]           # "<name> = <PREFIX>": name [a-z0-9_.-]{1,40}; PREFIX 4 of A-Z, not a retail class literal
 *                                   # (COMP MSCL CUPE SPRT SUPR HSPC HEVY TRAF TSPC), unique across mods
 *   names = ["neon = Neon"]         # the garage header text (1..21 chars A-Z a-z 0-9 space - ' . &); default the prefix
 *   unlock = ["neon = cars:10"]     # the series' default rule for its cars (open | cars:N | car:<RETAIL ID> | series:<CLASS>)
 *   ai_class = ["neon = SPRT"]      # REQUIRED: the retail class whose cars race against a car of this series when none of
 *                                   # its cars is AI-eligible / unlocked (the game's picker would divide by zero otherwise)
 *
 *   [bmashup.paints]
 *   version = 1
 *   add = ["sunset = COMPCAR1 | ramp FF8800 301000", "chrome = BMNECAR1 | file paints/chrome.bmpal"]
 *   default = ["BMNECAR1 = sunset"] # optional: the car's paint before the player chose one
 *
 * Series: class code 10 + k (k = admission order). The garage's all-series list (class 9) walks the retail series the game
 * allows (+0x264 / +0x265 rules) and then every active series (sub_000BDF10 / BE070 / BE0D0 marks); the header text is the
 * series name (sub_000BCEF0 mark); sub_00157300 returns the series code for an ID with a series prefix (it returned 9).
 * AI: sub_00060120 (the opponent picker) for a series code or a retail class with AI-eligible added cars picks with the
 * game's rule (unlocked first, used < 3 times, first 20, the game's RNG 0x4D1FD8 / 0x4D1FDC); a series without a candidate
 * runs the game's picker with its ai_class (never the divide-by-zero path).
 * Paints: per car, registered paints follow the car's retail palettes (index = model palette count + j); the garage cycles the
 * retail selectable paints then the registered ones. Palettes are host guest-heap resources (one per (car, paint) and per
 * (photo, car, paint)), created at first use from the car's own palette 0 (ramp) or the authored file, never freed.
 * Thread: game thread. Lifetime: process; see INTERFACE.md s4 for the three lifetimes.
 */
#ifndef BO3_BM_VEH_H
#define BO3_BM_VEH_H

#include <stddef.h>
#include <stdint.h>

#include "bm_cars.h"

#define BO3_VEH_SERIES_MAX     64u
#define BO3_VEH_SERIES_CODE0   10u      /* 9 = the game's "all series" sentinel / unknown prefix; 7 / 8 traffic */
#define BO3_VEH_TITLE_MAX      21u
#define BO3_VEH_LOCAL_MAX      40u      /* contract s1: [a-z0-9_.-]{1,40} */
#define BO3_PAINT_PER_CAR      56u      /* registered per car (+ up to 8 retail = 64, SCALE_TARGETS) */
#define BO3_PAINT_DECL_MAX     4096u
#define BO3_PAINT_RESIDENT     1024u    /* host palettes (model + photo) created at first use */
#define BO3_AI_PICK_MAX        20u      /* the game's candidate array */

/* ---- rules ---- */
int bo3_veh_rule_parse(const char *s, bo3_veh_rule *r);     /* 1 ok */
/* open: the rule evaluated on the game's derived open-car bytes (0x44CFC8, 67) and career table */
int bo3_veh_rule_open(const bo3_veh_rule *r);

/* ---- series ---- */
typedef struct bo3_series_entry {
    char name[BO3_VEH_LOCAL_MAX + 1];
    char prefix[5];
    char title[BO3_VEH_TITLE_MAX + 1];
    uint8_t has_rule;
    bo3_veh_rule rule;
    int ai_class;                       /* 0..6 */
} bo3_series_entry;
typedef struct bo3_series_decl {
    int present;
    uint32_t n;
    bo3_series_entry e[BO3_VEH_SERIES_MAX];
} bo3_series_decl;
int bo3_series_parse(const char *text, size_t n, bo3_series_decl *out, char *why, size_t wn);
/* register (stage 1): k or -1 with why (a prefix taken, the limit) */
int bo3_series_register(const bo3_series_entry *e, int mod, char *why, size_t wn);
uint32_t bo3_series_count(void);                 /* registered (active or not) */
const bo3_series_entry *bo3_series_at(uint32_t k);
int bo3_series_active(uint32_t k);
int bo3_series_mod(uint32_t k);
int bo3_series_of_prefix(uint64_t id);          /* the active series whose prefix id carries, else -1 */
void bo3_series_drop_mod(int mod);               /* rollback */
void bo3_series_set_text(uint32_t k, uint32_t text_id);   /* bm_names host text ID of its title (0 = none) */

/* host class of a vehicle ID: 0..8 retail literals, 10 + k series, else 9 (as sub_00157300 + the mark) */
uint32_t bo3_veh_class_of(uint64_t id);

/* ---- vlist2 (the relocated vehicle list) ---- */
int bo3_vl_install(uint32_t va, uint32_t cap);    /* the image at va (guest) of capacity cap is the one the game reads */
void bo3_vl_reset(void);
uint32_t bo3_vl_count(void);                      /* entries of the image the game reads */
uint64_t bo3_vl_id_at(uint32_t i);
/* the n-th listed (flag A) entry of class cls in list order (as sub_00157440), 0 when none */
uint64_t bo3_vl_nth(uint32_t cls, uint32_t n);

/* ---- paints ---- */
enum { BO3_PAINT_RAMP = 1, BO3_PAINT_FILE = 2 };
typedef struct bo3_paint_entry {
    char name[BO3_VEH_LOCAL_MAX + 1];
    char car_ref[80];                   /* as declared */
    uint64_t car;                       /* resolved vehicle ID (stage 1) */
    uint8_t kind;
    uint32_t hi, lo;                    /* RAMP: RGB 0xRRGGBB */
    char file[96];                      /* FILE: the mod-relative path */
} bo3_paint_entry;
typedef struct bo3_paint_decl {
    int present;
    uint32_t n, cap;
    bo3_paint_entry *e;                 /* malloc'ed */
    uint32_t ndef;
    struct { uint64_t car; char paint[BO3_VEH_LOCAL_MAX + 1]; } def[64];
} bo3_paint_decl;
int bo3_paint_parse(const char *text, size_t n, bo3_paint_decl *out, char *why, size_t wn);
void bo3_paint_decl_free(bo3_paint_decl *d);
/* register one paint of mod (stage 1; pal = the FILE palette 1024 B or NULL): 0 ok, else why */
int bo3_paint_register(const bo3_paint_entry *e, int mod, const char *mod_id, const uint8_t *pal, char *why, size_t wn);
/* main21 patch 91: the retail race cars a "*" paint entry expands to (count, i-th vehicle ID; 0 = skip). NULL = "*" refused. */
void bo3_paint_set_retail(uint32_t (*count)(void), uint64_t (*at)(uint32_t i));
int bo3_paint_set_default(uint64_t car, int mod, const char *paint, char *why, size_t wn);
uint32_t bo3_paint_count(void);
uint32_t bo3_paint_of_car(uint64_t car, uint32_t *first);   /* registered paints of a car (active ones) */
void bo3_paint_drop_mod(int mod);
void bo3_paint_drop_car(uint64_t car);
/* the canonical ID of paint index p of car (count = the car's retail palette count): "retail/<ID>/<p>" or "<mod>/<name>" */
int bo3_paint_canonical(uint64_t car, uint32_t count, uint32_t p, char *out, size_t n);
/* the index of a canonical paint for car (count retail palettes), -1 when unknown */
int bo3_paint_index(uint64_t car, uint32_t count, const char *canon);

/* sidecar hooks (the game build: bm_vpaint.c opens "Profile 1 veh.bmprog"; tests: a stand-in) */
typedef struct bo3_paint_store {
    int (*get)(void *u, const char *owner, uint64_t car, char *canon, size_t n);   /* 1 found */
    int (*put)(void *u, const char *owner, uint64_t car, const char *canon);       /* 1 committed */
    void *user;
} bo3_paint_store;
void bo3_paint_set_store(const bo3_paint_store *s);

/* guest allocation for palettes (game: xbox_HeapAlloc; tests: their heap). 0 = failed */
void bo3_veh_set_alloc(uint32_t (*alloc)(uint32_t size, uint32_t align));

/* stats: 0 class marks answered, 1 nav steps, 2 AI host picks, 3 AI fallbacks, 4 locked rows, 5 path aliases,
 * 6 palettes created, 7 palette fallbacks (first-use failures), 8 paint selections committed, 9 restores,
 * 10 series texts, 11 mods refused (veh stage), 12 palette renders, 13 photo palettes */
uint32_t bo3_veh_stats(uint32_t which);
void bo3_veh_reset(void);                         /* tests: series, paints, vlist2, stats */

#include "bo3_veh_gen.h"

void bo3_paint_reset_registry(void);              /* tests (bo3_veh_reset calls it) */
/* stage 1 of one mod's [bmashup.paints]: car_known(id) = a retail car or a car declared by an admitted mod; file(mod, rel,
 * buf 1024) = 1 when the mod ships rel with exactly 1024 bytes */
typedef int (*bo3_paint_car_fn)(uint64_t id);
typedef int (*bo3_paint_file_fn)(int mod, const char *rel, uint8_t *buf);
int bo3_paint_declare_mod(int mod, const char *mod_id, const char *text, size_t n, bo3_paint_car_fn car_known,
                          bo3_paint_file_fn file, int (*requires)(const char *owner_mod_id), char *why, size_t wn);

#ifdef BO3_CARS_GAME
/* bm_cars.c stage 1 calls it per mod (series + paints of that mod, parsed / validated / registered or refused) */
int bo3_veh_game_declare_mod(int mod, const char *mod_id, const char *text, size_t n, int phase, char *why, size_t wn);
int bo3_veh_requires(const char *text, size_t n, const char *mod_id);    /* [bmashup] requires_mods names mod_id */
int bo3_paint_game_declare_mod(int mod, const char *mod_id, const char *text, size_t n, char *why, size_t wn);
int bo3_car_declared(uint64_t id);                /* bm_cars.c: a car of an admitted mod (stage 1) */
int bo3_car_declared_mod(uint64_t id);            /* its mod index, else -1 */
#endif

#endif
