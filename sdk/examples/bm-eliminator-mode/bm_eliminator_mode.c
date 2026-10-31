/*
 * bm_eliminator_mode.c - Burnout Mashup SDK 0.6.0 example for "bmashup.menu" v1 (mode row) + "bmashup.rules" v1: a TIMED
 * ELIMINATOR row in Single Event's SELECT MODE with one option row (seconds between eliminations, a GLOBAL INT setting). In a
 * race that row started, the plugin claims the rules, turns the game's per-lap elimination off and eliminates one AI racer
 * every N seconds (the last index the host accepts), then end_race() when three minutes have passed. CHANGES GAMEPLAY.
 * Platform 0.1.9 (main19 patch 43): the row is shown (label only; the option row is NOT shown - set the seconds on the MOD
 * SETTINGS page) and starts the title's Eliminator logic (5 laps); claim_race() then accepts this plugin.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_eliminator_mode.c -o bm_eliminator_mode.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_menu.h"
#include "bmashup_rules.h"
#include "bmashup_settings.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_settings_api *s_set;
static const bm_rules_api *s_rules;
static const bm_menu_api *s_menu;
static int s_claimed, s_said, s_told;
static uint32_t s_updates;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_rules_status st;
    int32_t secs = 30, r;
    char line[96];
    (void)snap; (void)user;
    if (!s_rules)
        return;
    if (!s_told++ && s_menu) {                      /* the host answers feature_available() once the plugins have started */
        snprintf(line, sizeof line, "eliminator mode: row shown by this host: %u",
                 (unsigned)s_menu->feature_available(s_api->host, BM_MENU_FEATURE_MODE));
        say(line);
    }
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_rules->status(s_api->host, &st) != BM_RULES_OK || !st.eliminator_race) {
        s_claimed = 0;
        s_updates = 0;
        return;
    }
    if (s_claimed && !st.yours)
        s_claimed = 0;                              /* a restart's load released the claim: claim again */
    if (!s_claimed) {
        r = s_rules->claim_race(s_api->host);
        if (r == BM_RULES_NOT_IN_RACE)
            return;                                 /* the race is still loading: try again at a later update */
        if (r != BM_RULES_OK) {
            if (!s_said++) {
                snprintf(line, sizeof line, "eliminator mode: claim refused (%d); the game's own rules run", (int)r);
                say(line);
            }
            return;
        }
        s_claimed = 1;
        s_rules->set_lap_elimination(s_api->host, 0);
        say("eliminator mode: race claimed; the game's per-lap elimination is off");
    }
    if (s_set)
        s_set->get(s_api->host, "elim_secs", &secs);
    if (++s_updates % (uint32_t)(60 * (secs < 10 ? 10 : secs)) == 0u)
        for (uint32_t i = 7; i >= 1; i--)          /* the first racer the host accepts (never the human: LAST_PLAYER) */
            if (s_rules->eliminate(s_api->host, i) == BM_RULES_OK)
                break;
    if (s_updates == 60u * 180u)
        s_rules->end_race(s_api->host, BM_RULES_END_TIME);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_SETTINGS_SERVICE)) {
        const bm_settings_api *st = (const bm_settings_api *)table;
        bm_setting_decl d;
        int32_t v = 0;
        if (version < 2 || st->struct_size < sizeof *st)
            return 1;
        memset(&d, 0, sizeof d);
        d.struct_size = (uint32_t)sizeof d;
        d.kind = BM_SETTING_INT;
        d.key = "elim_secs";
        d.label = "ELIM EVERY";
        d.unit = "s";
        d.min = 10; d.max = 60; d.step = 5; d.def = 30;
        d.scope = BM_SETTING_SCOPE_GLOBAL;
        if (st->declare(s_api->host, &d, &v) != BM_SETTINGS_OK)
            return 1;
        s_set = st;
        return TD_OK;
    }
    if (!strcmp(name, BM_MENU_SERVICE) && s_set) {
        const bm_menu_api *m = (const bm_menu_api *)table;
        static const char *const opts[1] = { "elim_secs" };
        bm_menu_mode_decl d;
        char line[96];
        int32_t r;
        if (version < 1 || m->struct_size < sizeof *m)
            return 1;
        memset(&d, 0, sizeof d);
        d.struct_size = (uint32_t)sizeof d;
        d.id = "timed_elim";
        d.label = "TIMED ELIM";
        d.help = "One car is out every few seconds";
        d.base = BM_MENU_BASE_ELIMINATOR;
        d.contexts = BM_MENU_CTX_SINGLE_EVENT;
        d.option_keys = opts;
        d.n_options = 1;
        r = m->declare_mode(s_api->host, &d);
        snprintf(line, sizeof line, "eliminator mode: row declared (%d)", (int)r);
        say(line);
        s_menu = m;
        return TD_OK;
    }
    if (!strcmp(name, BM_RULES_SERVICE)) {
        const bm_rules_api *ru = (const bm_rules_api *)table;
        if (version < 1 || ru->struct_size < sizeof *ru)
            return 1;
        s_rules = ru;
        return TD_OK;
    }
    if (!strcmp(name, TD_RACE_SERVICE)) {
        const td_race_api *race = (const td_race_api *)table;
        if (version < 1 || race->struct_size < sizeof *race || race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
            return 1;
        return TD_OK;
    }
    return 1;
}
