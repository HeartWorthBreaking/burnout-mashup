/*
 * bmashup_menu.h - the "bmashup.menu" service (platform 0.1.9, hook request P3 items D1 popup / D2 mode row / D3 bars):
 * final draft gp\hookreq\p23\drafts_p23\bmashup_menu.h. Platform 0.1.9 status: the declarations are checked and kept;
 * POPUP is served (main19 patch 45): Single Event flow only, player 0, triggered by the player's A on the car-select page (the
 * press does not confirm the car; after the answers the next A does). MODE is served (main19 patch 43): each SINGLE_EVENT
 * ELIMINATOR mode is an extra row of the Single Event SELECT MODE list (label only: help and option rows are not shown) that
 * starts the title's Eliminator logic (5 laps) on the chosen track; active_mode() names it and bmashup.rules claim_race accepts
 * the declaring plugin. BARS (main19 item 47, reduced form): the declared bars are drawn on car select with bmashup.hud 2's
 * primitives (label + track + fill at x 48..248, y 300 + 40 i), the value from the callback for player 0's chosen car (its ValueDB
 * name, e.g. "COMPCAR1"); the draw site is the best candidate found offline and is confirmed by a car-select screenshot. Declaring is still useful: a later host that offers a feature shows it without a
 * plugin change.
 * Justification (R0): bmashup.settings owns the host's MODS / MOD SETTINGS pages and bounded values; a popup in the title's flow,
 * a row in the title's SELECT MODE lists, option rows in its options page and bars on car select are new title-UI objects with
 * their own lifecycle (one dialog owner, list capacity, a mode dispatch). Folding them into settings would change what a setting
 * declaration means. Values still ARE settings: a popup / option row edits a PER_PLAYER (popup) or GLOBAL (option) setting of the
 * same plugin, so MOD SETTINGS shows and saves them (plugin-settings.toml; never the game save).
 *
 * bmashup_menu.h - Burnout Mashup's private, experimental front-end additions. Declare while the plugins start only (CLOSED after).
 *   POPUP     after a player confirms a car (Single Event / Multiplayer; never World Tour), the title's own dialog asks the
 *             declared question (2 choices: the setting's first two ENUM texts, or YES / NO for a BOOL) and stores the answer in the
 *             plugin's PER_PLAYER setting. One popup at a time; <= BM_MENU_POPUPS_MAX popups after one confirmation (queued in
 *             plugin start order); the dialog is used only when nothing else owns it.
 *   MODE ROW  an extra row in SELECT MODE (Single Event and / or Multiplayer) that starts a RETAIL event type with this plugin as the
 *             race's rules owner (bmashup.rules); option rows before the track list show up to 2 of the plugin's GLOBAL INT / ENUM
 *             settings. <= BM_MENU_MODES_MAX rows over all plugins; the title's lists hold 10 rows (Single Event 4 + rows,
 *             Multiplayer 5 + rows). base ELIMINATOR is the only base in v1 (others answer UNAVAILABLE).
 *   BARS      up to BM_MENU_BARS_MAX extra bars on car select, value 0..1 per vehicle from the plugin's callback (it may read
 *             bmashup.vphysics vehicle_value). Labels <= 12 characters of the title's font.
 *             main21 C3-5: a MULTIPLAYER mode is a row of the Multiplayer list after its 5 retail rows (greyed with <= 1 pad, as
 *             the 2-player rows) and starts the 2-player race with the ELIMINATOR logic (feature MODE_MP); the game's own HUD /
 *             results of that logic in split screen are not proven (probe), services that refuse player 2 stay as they are.
 *   active_mode() names the added mode the race in play was started from ("" for a retail mode).
 *   Texts are copied at declare into host memory (the guest high zone, UTF-16 for the title) and live for the process.
 *   Availability: each feature reports UNAVAILABLE when its sites failed this build's census at start (feature_available()).
 */
#ifndef BMASHUP_MENU_H
#define BMASHUP_MENU_H
#include "takedawn_plugin.h"
#ifdef __cplusplus
extern "C" {
#endif
#define BM_MENU_SERVICE "bmashup.menu"
#define BM_MENU_VERSION 1u
#define BM_MENU_POPUPS_MAX 2u           /* after one confirmation */
#define BM_MENU_POPUPS_DECL_MAX 8u      /* declared, all plugins */
#define BM_MENU_MODES_MAX 4u
#define BM_MENU_MODE_OPTIONS_MAX 2u
#define BM_MENU_BARS_MAX 2u
#define BM_MENU_LABEL_MAX 16u
#define BM_MENU_TITLE_MAX 24u
#define BM_MENU_HELP_MAX 96u

enum { BM_MENU_OK = 0, BM_MENU_BAD_ARG = 1, BM_MENU_CLOSED = 2, BM_MENU_FULL = 3, BM_MENU_DUPLICATE = 4,
       BM_MENU_BAD_TEXT = 5, BM_MENU_CONFLICT = 6, BM_MENU_UNAVAILABLE = 7, BM_MENU_UNKNOWN_SETTING = 8,
       BM_MENU_WRONG_SETTING = 9 /* not PER_PLAYER ENUM / BOOL (popup) or not GLOBAL INT / ENUM (option) */ };
enum { BM_MENU_CTX_SINGLE_EVENT = 1, BM_MENU_CTX_MULTIPLAYER = 4 };      /* bits (WORLD_TOUR = 2 is never accepted) */
enum { BM_MENU_BASE_ELIMINATOR = 1 };
enum { BM_MENU_FEATURE_POPUP = 1, BM_MENU_FEATURE_MODE = 2, BM_MENU_FEATURE_BARS = 3,
       BM_MENU_FEATURE_HELP = 4 /* main21: a mode row's help + option values shown while the row is selected */,
       BM_MENU_FEATURE_MODE_MP = 5 /* main21 C3-5: MULTIPLAYER mode rows on the Multiplayer list (2-player race) */ };

typedef struct bm_menu_popup_decl {
    uint32_t struct_size;
    const char *setting_key;        /* this plugin's PER_PLAYER ENUM (first 2 choices used) or BOOL setting */
    const char *title;              /* <= 24 */
    uint32_t contexts;              /* BM_MENU_CTX_* bits */
} bm_menu_popup_decl;

typedef struct bm_menu_mode_decl {
    uint32_t struct_size;
    const char *id;                 /* [a-z0-9_] 1..24, unique per plugin */
    const char *label;              /* <= 16, the row */
    const char *help;               /* <= 96, the help bar */
    uint32_t base;                  /* BM_MENU_BASE_* */
    uint32_t contexts;
    const char *const *option_keys; /* this plugin's GLOBAL INT / ENUM settings shown as option rows */
    uint32_t n_options;             /* 0..2 */
} bm_menu_mode_decl;

typedef float (TD_CALL *bm_menu_bar_fn)(const char *vehicle_name, void *user);   /* 0..1; outside: the bar is not drawn */
typedef struct bm_menu_bar_decl {
    uint32_t struct_size;
    const char *label;              /* <= 12 */
    bm_menu_bar_fn fn;
    void *user;
} bm_menu_bar_decl;

typedef struct bm_menu_api {
    uint32_t struct_size;
    uint32_t version;
    int32_t (TD_CALL *declare_popup)(td_host *host, const bm_menu_popup_decl *d);
    int32_t (TD_CALL *declare_mode)(td_host *host, const bm_menu_mode_decl *d);
    int32_t (TD_CALL *declare_bar)(td_host *host, const bm_menu_bar_decl *d);
    int32_t (TD_CALL *active_mode)(td_host *host, char *id, uint32_t room);              /* any thread */
    uint32_t (TD_CALL *feature_available)(td_host *host, uint32_t feature);              /* any thread */
} bm_menu_api;
#ifdef __cplusplus
}
#endif
#endif
