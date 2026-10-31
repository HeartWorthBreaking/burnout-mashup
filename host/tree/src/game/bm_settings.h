/*
 * bm_settings.h - "bmashup.settings" (include/bmashup_settings.h), version 1: the host side (gp slice camset1).
 *
 * The registry of the plugins' declared settings, their values, the plugin-settings file and the delivery to the
 * plugins' callbacks; the MODS page (modsmenu.c) reads and steps the values through the bo3_ps_* calls below, on the
 * game's thread. No guest memory is touched here.
 */
#ifndef BO3_BM_SETTINGS_H
#define BO3_BM_SETTINGS_H

#include <stddef.h>
#include <stdint.h>

#include "bmashup_settings.h"

/* The file, before bo3_bm_settings_init's first declaration: NULL or "" = none (values for the session only). */
void bo3_ps_file(const char *path);
/* Offer the service (before bo3_plugins_init). */
void bo3_bm_settings_init(void);
/* Right after bo3_plugins_init: no more declarations or callbacks. */
void bo3_bm_settings_close(void);
const bm_settings_api *bo3_bm_settings_api(void);

/* A game point (the first front-end or stage set-up after the start; game thread): the initial values are delivered
 * once. Later calls do nothing. */
void bo3_ps_game_point(void);

/* ---- the MODS page (game thread) ----
 * main18 (v2): p numbers PAGES (a plugin's lines in groups of at most BM_SETTINGS_PER_PLUGIN = 6; a PER_PLAYER setting is two
 * lines, P1 and P2, never split over two pages) and i a LINE of the page. A plugin with only GLOBAL settings and at most 6 of
 * them has one page: then a page is exactly v1's plugin (the MODS page is unchanged for v1 content). */
int  bo3_ps_plugin_count(void);                              /* pages (v1: plugins with at least one setting) */
int  bo3_ps_mod_count(void);                                 /* main18: plugins (and the host) with at least one setting */
const char *bo3_ps_plugin_mod(int p);                        /* the page's mod id ("" outside the range) */
int  bo3_ps_count(int p);                                    /* the page's lines (0 outside the range) */
/* "LABEL  VALUE[UNIT]" as the page shows it (plain ASCII; the page upper-cases it). */
void bo3_ps_line(int p, int i, char *out, size_t n);
/* The details line for setting i of plugin p ("A: 70 TO 140 % IN 5  DEFAULT 100"). */
void bo3_ps_detail(int p, int i, char *out, size_t n);
/* A on the line: the next value (wraps). Saved, then delivered (BM_SETTING_CHANGED). 1 changed (the save may have
 * failed: bo3_ps_save_failed), 0 not (no such setting). */
int  bo3_ps_step(int p, int i);
int  bo3_ps_save_failed(void);                               /* the last save did not happen (the log says why) */

/* ---- main20m patch 61: the overlay's MOD SETTINGS page (any thread for these five; bo3_ps_flush on the game thread) ----
 * The label ("Laps", "Boost colour (player 2)") and the value ("5", "90 deg", "blue") apart, with a queued change shown. */
void bo3_ps_line2(int p, int i, char *label, size_t ln, char *value, size_t vn);
void bo3_ps_detail2(int p, int i, char *out, size_t n);       /* "From 60 to 110 deg, in steps of 5. Default: 75 deg." */
int  bo3_ps_is_default(int p, int i);
/* op 1 the next value, -1 the one before (both wrap), 0 the default: queued (1), 0 no such line / the queue is full. */
int  bo3_ps_request(int p, int i, int op);
int  bo3_ps_pending(void);                                   /* 1 while a change waits for bo3_ps_flush */
/* The game thread (the title's flip): the queued changes made as bo3_ps_step makes them (stored, saved, delivered). */
void bo3_ps_flush(void);

/* ---- GP-P4.1: host settings ----
 * A host service declares its own setting (before the plugins start, as a plugin would) under the pseudo mod id
 * BO3_PS_HOST_MOD: listed on MOD SETTINGS (BURNOUT MASHUP), stored in the same file ("bmashup.host/<key> = <value>"),
 * no callback (the host reads the value when it needs it: get is an atomic read, any thread). */
#define BO3_PS_HOST_MOD "bmashup.host"
int32_t bo3_ps_host_declare(const bm_setting_decl *decl, int32_t *value);
int32_t bo3_ps_host_get(const char *key, int32_t *value);

/* ---- main21 patch 130: data-mod sliders ----
 * A DATA mod (no plugin) declares player-adjustable tuning rows in its mod.toml ([bmashup.tune] version 3 sliders, bm_tune.h); the
 * host declares each as a setting here under the mod's own id with the mod's tune token `who` (never a plugin's host). On the
 * page and in the file it is a setting like a plugin's ("<mod id>/<key> = <value>"; BOOL on / off). An INT slider's value is in
 * units of 10^-decimals: shown and stored with a decimal point ("1.05"), read back exactly (at most `decimals` decimals). Its
 * default may lie off the min + k * step grid (a set = [...] value of the mod); it stays a value (stepping leaves it for the grid
 * value above / below; the overlay's DEFAULT goes back to it). No plugin callback: fn(user, value) on the game thread after each
 * change (already saved), never for the initial value (the start applied it). when (BO3_PS_WHEN_*) = the page's hint.
 * Declared before the plugins start (BM_SETTINGS_CLOSED after); every v1 / v2 limit and text rule applies (8 a mod, 128 in all,
 * key [a-z0-9_] 1..24, label 1..16, at most BM_SETTINGS_INT_STEPS grid values, |value| <= BM_SETTINGS_INT_LIMIT units). */
#define BO3_PS_DATA_DECIMALS_MAX 6u
#define BO3_PS_DETAIL_FIT 46u                 /* the title page's details line: about 46 characters (deps1_1 shot 10) */
enum { BO3_PS_WHEN_NONE = 0, BO3_PS_WHEN_AT_ONCE = 1, BO3_PS_WHEN_NEXT_RACE = 2 };
typedef void (*bo3_ps_data_fn)(void *user, int32_t value);
typedef struct bo3_ps_data_ext {
    uint32_t decimals;                        /* INT: 0..BO3_PS_DATA_DECIMALS_MAX; BOOL: ignored */
    uint32_t when;                            /* BO3_PS_WHEN_* */
    bo3_ps_data_fn fn;                        /* required */
    void *user;
} bo3_ps_data_ext;
/* BM_SETTINGS_* (BAD_ARG: no token / mod id / handler, a kind other than BOOL / INT, too many decimals, the token is a plugin's
 * or already another mod's); *value = the stored value when it fits, else the default */
int32_t bo3_ps_data_declare(td_host *who, const char *mod_id, const bm_setting_decl *d, const bo3_ps_data_ext *x, int32_t *value);

/* ---- tests ---- */
typedef void (*bo3_ps_guard_fn)(bm_setting_fn fn, const char *key, int32_t value, uint32_t reason, void *user);
void bo3_ps_set_guard(bo3_ps_guard_fn fn);                   /* the game build guards the guest registers */
/* main18 (v2): the same guard for subscribe2's callbacks */
typedef void (*bo3_ps_guard2_fn)(bm_setting_fn2 fn, const char *key, uint32_t player, int32_t value, uint32_t reason,
                                 void *user);
void bo3_ps_set_guard2(bo3_ps_guard2_fn fn);
void bo3_ps_reset_for_tests(void);
/* main19 (patch 32, bmashup.menu): what `host` declared under `key`: 1 and its kind (BM_SETTING_*), scope
 * (BM_SETTING_SCOPE_*), choice count and (choice2 != NULL) its first two choice texts ("" when absent); 0 when that plugin
 * declared no such setting. Any thread after the declarations. */
int bo3_ps_set_player(const td_host *host, const char *key, uint32_t player, int32_t value);
int bo3_ps_value_text(const td_host *host, const char *key, char *out, size_t n);   /* main21 patch 88: "LABEL: value", 0 unknown */   /* main19 patch 45 */
int bo3_ps_query(const td_host *host, const char *key, uint32_t *kind, uint32_t *scope, uint32_t *nchoices,
                 char choice2[2][BM_SETTINGS_CHOICE_MAX + 1]);
/* Link-level inputs (the game build: plugins.c, modfs.c, the toolkit's recomp_cfg; tests give their own):
 * bo3_plugins_host_id (the declaring plugin's mod id), bo3_modfs_read_whole / bo3_modfs_write_whole (the file). */

#endif
