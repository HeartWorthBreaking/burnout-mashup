/*
 * bm_sdk_player_settings.c - bmashup-sdk 0.5.0 example: "bmashup.settings" v2 (platform 0.1.8 hosts).
 *
 *   mod "bmashup-sdk.player-settings": two settings on MODS > MOD SETTINGS -
 *     "unit"   PER_PLAYER ENUM KMH / MPH: one value for P1 and one for P2 (the page shows "SPEED UNIT P1" and "... P2";
 *              the file keeps bmashup-sdk.player-settings/unit#p1 and #p2) - the request's "MOD SETTINGS enum per player";
 *     "banner" GLOBAL BOOL: one value for both players.
 *   One callback through subscribe2: it gets the player (0 / 1) for the PER_PLAYER setting and BM_SETTING_ALL_PLAYERS for
 *   the GLOBAL one, first INITIAL (before any race), then CHANGED after each step on the page. get_player reads a value at
 *   any time. Split screen is not tested on the platform: P2's value is kept and delivered, using it is the mod's business.
 *   This example only logs the values (it changes nothing in the game).
 *
 * Build: the SDK's build.ps1, or  clang -shared -Iinclude bm_sdk_player_settings.c -o bm_sdk_player_settings.asi
 */
#include "bmashup_sdk.h"

#ifndef BMSDK_SETTINGS_TABLE_V2
#define BMSDK_SETTINGS_TABLE_V2 BMSDK_FIELD_END(bm_settings_api, get_player)      /* SDK 0.5.0 */
#endif

#define TAG "player settings"

static const td_host_api *s_api;
static const bm_settings_api *s_set;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_SETTINGS_SERVICE, 2, BMSDK_SETTINGS_TABLE_V2, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;
static const char *const k_units[] = {"KMH", "MPH"};

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static void TD_CALL on_setting(const char *key, uint32_t player, int32_t value, uint32_t reason, void *user)
{
    char line[160];
    (void)user;
    if (player == BM_SETTING_ALL_PLAYERS)
        snprintf(line, sizeof line, TAG ": %s = %ld (both players, %s)", key, (long)value,
                 reason == BM_SETTING_INITIAL ? "initial" : "changed");
    else
        snprintf(line, sizeof line, TAG ": %s = %s for P%u (%s)", key,
                 !strcmp(key, "unit") && value >= 0 && value < 2 ? k_units[value] : "?", (unsigned)player + 1u,
                 reason == BM_SETTING_INITIAL ? "initial" : "changed");
    say(line);
}

static void use_settings(const bm_settings_api *st)
{
    bm_setting_decl d;
    int32_t v = 0, v2 = 0, rc;
    char line[160];
    s_set = st;
    memset(&d, 0, sizeof d);
    d.struct_size = sizeof d;                  /* the v2 size: `scope` is read */
    d.kind = BM_SETTING_ENUM;
    d.key = "unit";
    d.label = "SPEED UNIT";
    d.choices = k_units;
    d.nchoices = 2;
    d.def = 0;
    d.scope = BM_SETTING_SCOPE_PER_PLAYER;
    rc = st->declare(s_api->host, &d, &v);
    if (rc == BM_SETTINGS_OK)
        rc = st->get_player(s_api->host, "unit", 1, &v2);
    snprintf(line, sizeof line, TAG ": unit (per player): %ld / %ld: rc %ld", (long)v, (long)v2, (long)rc);
    say(line);
    memset(&d, 0, sizeof d);
    d.struct_size = sizeof d;
    d.kind = BM_SETTING_BOOL;
    d.key = "banner";
    d.label = "SPEED BANNER";
    d.def = 1;
    d.scope = BM_SETTING_SCOPE_GLOBAL;
    rc = st->declare(s_api->host, &d, &v);
    snprintf(line, sizeof line, TAG ": banner (global): %ld: rc %ld", (long)v, (long)rc);
    say(line);
    rc = st->subscribe2(s_api->host, on_setting, NULL);
    snprintf(line, sizeof line, TAG ": subscribe2: rc %ld", (long)rc);
    say(line);
}

static void TD_CALL on_shutdown(void *user)
{
    int32_t a = -1, b = -1;
    char line[96];
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
    if (s_set && s_set->get_player(s_api->host, "unit", 0, &a) == BM_SETTINGS_OK &&
        s_set->get_player(s_api->host, "unit", 1, &b) == BM_SETTINGS_OK) {
        snprintf(line, sizeof line, TAG ": at exit: P1 %s, P2 %s", k_units[a & 1], k_units[b & 1]);
        say(line);
    }
}

BMSDK_DEFINE_API_VERSION()
BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    s_api = api;
    if (info && info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {
        info->on_shutdown = on_shutdown;
        info->user = NULL;
    }
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                   const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    (void)api;
    if (!w || w->state != BMSDK_BOUND)
        return 1;
    use_settings((const bm_settings_api *)w->table);
    return TD_OK;
}
