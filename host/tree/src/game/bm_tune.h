/* bm_tune.h - G8-E3 EXPERIMENTAL: the "bmashup.tune" service (include/bmashup_tune.h) over the game's tuning registry
 * catalogue (bm_tune_catalog.h), and mod.toml declarations:
 *
 *   [bmashup.tune]
 *   version = 1
 *   set = ["Score/Boost/Lap | Perfect Lap Boost value (Boost units) = 240"]
 *
 * Declarations are applied in the mod list's order before the plugins start, each through the same set() rules as a
 * plugin (verified entry, bounds, first owner wins). A declaration this build cannot apply stops the start (exit 93) with
 * the mod, the entry and the reason: an unknown entry, an unverified entry, a value out of bounds, an entry another mod
 * already set, a malformed line, a version other than 1 .. 3 (2: AI / negative values; 3: + sliders, below). */
#ifndef BO3_BM_TUNE_H
#define BO3_BM_TUNE_H

#include <stddef.h>
#include <stdint.h>

#include "bmashup_tune.h"

/* guest access (the game build: g_xbox_mem_offset; tests: their own memory) */
typedef struct bo3_tune_guest {
    int (*read32)(void *user, uint32_t va, uint32_t *out);          /* 1 ok */
    int (*write32)(void *user, uint32_t va, uint32_t v);            /* 1 ok */
    int (*strcmp_at)(void *user, uint32_t va, const char *s);       /* 1 when the guest holds s (with its NUL) at va */
    void *user;
} bo3_tune_guest;

/* verifies every catalogue entry against the running game; returns the number verified */
uint32_t bo3_tune_configure(const bo3_tune_guest *g);
void bo3_bm_tune_init(void);                                         /* offers the service to the plugins */
const bm_tune_api *bo3_bm_tune_api(void);

/* a mod's declaration text (the whole mod.toml): applies it as requester `who`; 1 ok (or nothing declared), 0 with why */
int bo3_tune_apply_decl(const char *text, size_t n, td_host *who, char *why, size_t wn);
/* the game build: every usable, enabled mod's declaration (exit 93 on a refusal) */
void bo3_tune_game_apply(void);

/* ---- main21 patch 130: player-adjustable rows of a DATA mod (no plugin) on the MODS page ----
 *
 *   [bmashup.tune]
 *   version = 3
 *   set = ["Effects/Shadow | Alpha Test = 0"]
 *   sliders = ["Effects/Shadow | Width = 1.0 : 0.5 .. 2.0 step 0.05",
 *              "Effects/Shadow | Alpha Test = 0 : 0 .. 1 label Shadow Alpha Cut"]
 *
 * One slider: "ROW = DEFAULT : MIN .. MAX [step STEP] [label TEXT]" (numbers [-]D[.D], at most 6 decimals; step: default one unit
 * of the numbers' finest decimal; label: default the row's name after "| ", 1..16 printable characters). Fail closed (exit 93 like
 * every declaration): sliders need version = 3 (an older host refuses the mod alone: [bmashup.tune] version 3 is newer than its
 * reader); the row must exist and be verified on this build; MIN < MAX, MAX = MIN + a whole number of steps, at most
 * BO3_TUNE_SLIDER_STEPS values, MIN .. MAX inside the row's own bounds (Effects/Shadow: its own; else 0 (signed: -B) .. B, B = 16 x
 * max(|the program's value|, 1), which every later bound contains); an INT row takes whole numbers; DEFAULT in MIN .. MAX (it may lie
 * off the step grid) and equal to the mod's set = [...] value of that row when there is one; one slider a row, at most
 * BO3_TUNE_SLIDERS_PER_MOD a mod. An INT row 0 .. 1 step 1 is an ON / OFF switch. The default is applied with the declarations (the
 * mod owns the row, as a declaration: CONFLICT rules unchanged); bo3_tune_sliders_offer then declares each slider on the MODS page
 * (bm_settings.c bo3_ps_data_declare, persisted in plugin-settings.toml under the mod id) and applies a saved value; every change
 * on the page goes through bo3_tune_slider_apply (the owner's set: same bounds, CONFLICT and decl rules). */
#define BO3_TUNE_SLIDERS_MAX 64u
#define BO3_TUNE_SLIDERS_PER_MOD 8u          /* = BM_SETTINGS_PER_PLUGIN_V2 */
#define BO3_TUNE_SLIDER_STEPS 64u            /* = BM_SETTINGS_INT_STEPS */
#define BO3_TUNE_SLIDER_DECIMALS 6u
enum { BO3_TUNE_SLIDER_SWITCH = 1, BO3_TUNE_SLIDER_VALUE = 2 };
typedef struct bo3_tune_slider {
    td_host *who;                            /* the mod's declaration token */
    uint32_t index;                          /* the catalogue row */
    uint32_t kind;                           /* BO3_TUNE_SLIDER_* */
    uint32_t decimals;                       /* min / max / step / def are in units of 10^-decimals */
    uint32_t applies;                        /* BM_TUNE_APPLIES_* of the row */
    int32_t min, max, step, def;
    char key[25];                            /* the settings key: the row's name as [a-z0-9_] ("effects_shadow_width"; longer
                                              * than 24: the last group part + the name, "shadow_alpha_test"; else a cut + a hash) */
    char label[17];
} bo3_tune_slider;
uint32_t bo3_tune_slider_count(void);
const bo3_tune_slider *bo3_tune_slider_at(uint32_t k);
/* the slider's value (units) as its owner's set: BM_TUNE_* (OUT_OF_RANGE outside the slider's range) */
int32_t bo3_tune_slider_apply(uint32_t k, int32_t units);
/* the game build (BO3_TUNE_GAME; tests: BO3_TUNE_PS_GLUE): every slider declared on the MODS page under mod_of(who), a saved
 * value applied; 0 with why when the page refuses one (the game: exit 93) */
int bo3_tune_sliders_offer(const char *(*mod_of)(const td_host *who), char *why, size_t wn);
void bo3_tune_game_sliders(void);            /* main.c, after the host settings: bo3_tune_sliders_offer, exit 93 on a refusal */

/* v1.1: the generated-code mark after the game's ValueDB copy of a 32-bit value (sub_001AF040 loc_001AF09F): an owned
 * catalogue value is written again (the game's copy at boot would otherwise replace it; analysis\TUNE_RESET_TRACE.md) */
void bo3_tune_gen_applied(uint32_t var_va);
/* v1.2: 0 plugin values dropped at the copy (above the bound), 1 declarations refused there; the refusal handler (game build:
 * exit 93) */
uint32_t bo3_tune_stats(uint32_t which);
void bo3_tune_set_decl_refused(void (*fn)(uint32_t index, double value, double max));

#endif
