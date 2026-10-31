/*
 * bmashup_settings.h - the "bmashup.settings" service: Burnout Mashup's private, experimental plugin settings
 * (gp slice camset1). Not a Takedawn service: offered only by Burnout Mashup's own builds, through the same optional
 * export as Takedawn's (takedawn_services.h); it may change or go away.
 *
 * A plugin declares a few BOUNDED settings while Takedawn starts the plugins. The player sees and changes them on the
 * MODS page (Driver Details > Settings > MODS > MOD SETTINGS), in the title's own menu, with A; nothing else edits
 * them. Each change is saved at once to the player's plugin-settings file and handed to the plugin's callback on the
 * game's thread. The plugin decides what a value does; the host only keeps it inside the declared bounds.
 *
 * Version 1:
 *   kinds      BOOL (0 / 1), INT (min..max in steps of `step`, at most BM_SETTINGS_INT_STEPS values), ENUM (0..n-1 of
 *              2..BM_SETTINGS_CHOICES_MAX named choices).
 *   limits     BM_SETTINGS_PER_PLUGIN settings per plugin, BM_SETTINGS_TOTAL in all; key 1..24 of [a-z0-9_]; label
 *              1..16 and unit 0..3 and each choice 1..10 printable ASCII characters (shown upper case, the title's
 *              font); INT values within +-BM_SETTINGS_INT_LIMIT.
 *   ownership  a setting belongs to the plugin that declared it (its mod id is the namespace): no plugin reads or
 *              changes another's. Keys are unique per plugin. There is no undeclare: plugins are never unloaded.
 *   when       declare and subscribe while the plugins start only (takedawn_plugin_init, takedawn_plugin_service,
 *              takedawn_plugin_services_done); afterwards BM_SETTINGS_CLOSED. get: any thread, any time.
 *   values     the stored value when the file has one that fits the declaration; otherwise the default (the log says
 *              why; the stored text is kept until the player changes that setting). A stored value is never clamped:
 *              out of bounds means the default.
 *   callback   on the game's thread, never while the plugin is starting: once per setting with BM_SETTING_INITIAL at
 *              the first front-end or stage set-up after the start (before any race), then BM_SETTING_CHANGED after
 *              each change on the page (the value is already saved). Keep it short. A callback must not call
 *              declare / subscribe (closed). One callback per plugin.
 *   file       plugin-settings.toml beside the mod list (or BMASHUP_PLUGIN_SETTINGS; "" = none: values live for the
 *              session only). `values = ["<mod id>/<key> = <value>", ...]`; bool on / off, int decimal, enum the
 *              choice's text. Entries of other mods (or this mod's undeclared keys) are kept as they are.
 *   cleanup    nothing to free: the host owns every copy; the plugin's strings are copied at declare.
 *
 * Nothing here is an address; nothing touches the game's memory.
 *
 * main21 patch 130 (host side only, no API change): the page also lists a DATA mod's [bmashup.tune] sliders (mod.toml) under
 * that mod's id, stored in the same file ("<mod id>/<key> = 1.05": a slider's value may carry a decimal point; on / off for a
 * switch). A plugin's declarations, values and file entries are unchanged.
 *
 * Version 2 (platform 0.1.8; append-only, every v1 rule unchanged):
 *   scope      bm_setting_decl grows `scope` (read only when decl->struct_size covers it; a v1-sized decl is GLOBAL).
 *              BM_SETTING_SCOPE_PER_PLAYER: one value per player, P1 and P2 (players 0 / 1). The MODS page shows two
 *              lines ("LABEL P1", "LABEL P2"); the file keeps "<mod id>/<key>#p1 = <value>" and "...#p2 = ..." (keys have no
 *              '#', so a v1 entry never collides). Split screen is NOT tested on the platform: P2's value is stored and
 *              delivered, its in-game use is the plugin's and unverified.
 *   subscribe2 one callback with the player (bm_setting_fn2): for a PER_PLAYER setting once per player, for a GLOBAL one
 *              player = BM_SETTING_ALL_PLAYERS. A plugin has ONE callback: subscribe or subscribe2 (the other: DUPLICATE).
 *              A v1 callback (subscribe) of a PER_PLAYER setting gets P1's value only (player 0's changes).
 *   get_player the value of `key` for `player` (0 / 1; a GLOBAL setting answers its one value for both). v1 get() of a
 *              PER_PLAYER setting answers P1's value.
 *   limits     BM_SETTINGS_PER_PLUGIN_V2 settings per plugin, BM_SETTINGS_TOTAL_V2 in all (v1 hosts: 6 / 32; raised for every
 *              caller - a capacity, not a meaning). The page shows at most 6 lines per page: a plugin with more lines gets
 *              more pages (NEXT MOD SETTINGS steps through them).
 *   pause menu NOT in version 2: the race pause menu's 7th slot is not free in every mode (the title's own items + Takedawn's
 *              TAKEDAWN SETTINGS line fill all 7 in events with RESTART and the extra line; the other layout has 7 fixed
 *              lines), so - per the owner's condition - MOD SETTINGS is not added there. Settings change on the MODS page.
 */
#ifndef BMASHUP_SETTINGS_H
#define BMASHUP_SETTINGS_H

#include <stddef.h>

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_SETTINGS_SERVICE "bmashup.settings"
#define BM_SETTINGS_VERSION 2u          /* 1: GLOBAL settings; 2: + PER_PLAYER scope, subscribe2, get_player, 8 / 128 */
#define BM_SETTINGS_VERSION_1 1u
#define BM_SETTINGS_VERSION_2 2u

#define BM_SETTINGS_PER_PLUGIN   6u        /* version 1's limit (and the lines of one MOD SETTINGS page) */
#define BM_SETTINGS_TOTAL        32u       /* version 1's limit */
#define BM_SETTINGS_PER_PLUGIN_V2 8u       /* version 2 hosts: settings per plugin */
#define BM_SETTINGS_TOTAL_V2     128u      /* version 2 hosts: settings in all */
#define BM_SETTING_ALL_PLAYERS   0xFFFFFFFFu   /* subscribe2's player for a GLOBAL setting */
#define BM_SETTINGS_KEY_MAX      24u
#define BM_SETTINGS_LABEL_MAX    16u
#define BM_SETTINGS_UNIT_MAX     3u
#define BM_SETTINGS_CHOICE_MAX   10u
#define BM_SETTINGS_CHOICES_MAX  8u
#define BM_SETTINGS_INT_LIMIT    1000000
#define BM_SETTINGS_INT_STEPS    64u       /* (max - min) / step + 1: A steps through them, so few */

enum { BM_SETTING_BOOL = 1, BM_SETTING_INT = 2, BM_SETTING_ENUM = 3 };

/* reason (callback) */
enum { BM_SETTING_INITIAL = 1, BM_SETTING_CHANGED = 2 };

/* Results. */
enum {
    BM_SETTINGS_OK        = 0,
    BM_SETTINGS_BAD_ARG   = 1,     /* no host / decl / out, decl->struct_size too small, an unknown kind */
    BM_SETTINGS_CLOSED    = 2,     /* the plugins' start is over */
    BM_SETTINGS_FULL      = 3,     /* the per-plugin or total limit reached (v2 hosts: _PER_PLUGIN_V2 / _TOTAL_V2) */
    BM_SETTINGS_DUPLICATE = 4,     /* this plugin has a setting with that key (or a callback already) */
    BM_SETTINGS_BAD_TEXT  = 5,     /* key / label / unit / a choice: empty, too long or a character not allowed */
    BM_SETTINGS_BAD_RANGE = 6,     /* min > max, step < 1, too many values, beyond the limit, default not a value */
    BM_SETTINGS_UNKNOWN   = 7,     /* get: no such key for this plugin */
    BM_SETTINGS_BAD_SCOPE = 8      /* v2: decl->scope is not a BM_SETTING_SCOPE_*; get_player: a player other than 0 / 1 */
};

enum { BM_SETTING_SCOPE_GLOBAL = 0, BM_SETTING_SCOPE_PER_PLAYER = 1 };   /* v2: decl->scope */

/* A declaration (the plugin's; copied). */
typedef struct bm_setting_decl {
    uint32_t struct_size;          /* sizeof (bm_setting_decl) as the plugin built it (at least the v1 size) */
    uint32_t kind;                 /* BM_SETTING_* */
    const char *key;               /* the file's key: [a-z0-9_], 1..24 */
    const char *label;             /* the page's text, 1..16 printable ASCII */
    const char *unit;              /* INT: shown after the value (e.g. "%"), NULL or 0..3 characters; else ignored */
    int32_t min, max, step;        /* INT only (BOOL: 0, 1, 1; ENUM: 0, n - 1, 1 are implied) */
    int32_t def;                   /* the default: a value of the setting */
    const char *const *choices;    /* ENUM: n texts, 1..10 printable ASCII each */
    uint32_t nchoices;             /* ENUM: 2..8 */
    /* ---- version 2 (read only when struct_size covers it) ---- */
    uint32_t reserved_v1;          /* 0; ignored. Version 1's struct ended with padding here (64-bit builds): a field in
                                    * it could not be told from a v1 plugin's padding, so `scope` starts after it */
    uint32_t scope;                /* BM_SETTING_SCOPE_GLOBAL (0) / BM_SETTING_SCOPE_PER_PLAYER */
} bm_setting_decl;

typedef void (TD_CALL *bm_setting_fn)(const char *key, int32_t value, uint32_t reason, void *user);
/* v2: player = 0 / 1 for a PER_PLAYER setting, BM_SETTING_ALL_PLAYERS for a GLOBAL one */
typedef void (TD_CALL *bm_setting_fn2)(const char *key, uint32_t player, int32_t value, uint32_t reason, void *user);

typedef struct bm_settings_api {
    uint32_t struct_size;          /* sizeof (bm_settings_api) as built */
    uint32_t version;              /* BM_SETTINGS_VERSION */
    /* Declare one setting; *value (may be NULL) = its value now (stored or default). While the plugins start only. */
    int32_t (TD_CALL *declare)(td_host *host, const bm_setting_decl *decl, int32_t *value);
    /* The plugin's one callback (see above). While the plugins start only. */
    int32_t (TD_CALL *subscribe)(td_host *host, bm_setting_fn fn, void *user);
    /* The value now of this plugin's setting `key`. Any thread. */
    int32_t (TD_CALL *get)(td_host *host, const char *key, int32_t *value);
    /* ---- version 2 (present when struct_size covers it) ---- */
    /* The plugin's one callback, with the player (see above). While the plugins start only. */
    int32_t (TD_CALL *subscribe2)(td_host *host, bm_setting_fn2 fn, void *user);
    /* The value now of this plugin's setting `key` for player 0 / 1. Any thread. */
    int32_t (TD_CALL *get_player)(td_host *host, const char *key, uint32_t player, int32_t *value);
} bm_settings_api;

/* The smallest declaration a host takes (version 1's fields); `scope` is read only when struct_size reaches
 * BM_SETTING_DECL_V2_SIZE (a v1 plugin's sizeof never does: its settings are GLOBAL). */
#define BM_SETTING_DECL_V1_SIZE ((uint32_t)(offsetof(bm_setting_decl, nchoices) + sizeof(uint32_t)))
#define BM_SETTING_DECL_V2_SIZE ((uint32_t)(offsetof(bm_setting_decl, scope) + sizeof(uint32_t)))

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_SETTINGS_H */
