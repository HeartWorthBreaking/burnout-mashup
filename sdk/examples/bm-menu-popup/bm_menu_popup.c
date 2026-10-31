/*
 * bm_menu_popup.c - Burnout Mashup SDK 0.6.0 example for "bmashup.menu" v1 (popup): declares a PER_PLAYER BOOL setting
 * "assist" (MOD SETTINGS shows it) and asks the host to put it as a YES / NO question after a player confirms a car in Single
 * Event. Platform 0.1.9 (main19 patch 45) shows it when the player presses A on the car-select page in the Single Event flow
 * (that A does not confirm the car; the next one does); the setting also works on the MOD SETTINGS page.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_menu_popup.c -o bm_menu_popup.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_menu.h"
#include "bmashup_settings.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_settings_api *s_set;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
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
    if (!strcmp(name, BM_SETTINGS_SERVICE)) {      /* offered before bmashup.menu (registration order) */
        const bm_settings_api *st = (const bm_settings_api *)table;
        bm_setting_decl d;
        int32_t v = 0;
        if (version < 2 || st->struct_size < sizeof *st)
            return 1;
        memset(&d, 0, sizeof d);
        d.struct_size = (uint32_t)sizeof d;
        d.kind = BM_SETTING_BOOL;
        d.key = "assist";
        d.label = "STEER ASSIST";
        d.def = 0;
        d.scope = BM_SETTING_SCOPE_PER_PLAYER;
        if (st->declare(s_api->host, &d, &v) != BM_SETTINGS_OK)
            return 1;
        s_set = st;
        return TD_OK;
    }
    if (!strcmp(name, BM_MENU_SERVICE) && s_set) {
        const bm_menu_api *m = (const bm_menu_api *)table;
        bm_menu_popup_decl p;
        char line[96];
        int32_t r;
        if (version < 1 || m->struct_size < sizeof *m)
            return 1;
        memset(&p, 0, sizeof p);
        p.struct_size = (uint32_t)sizeof p;
        p.setting_key = "assist";
        p.title = "STEER ASSIST?";
        p.contexts = BM_MENU_CTX_SINGLE_EVENT;
        r = m->declare_popup(s_api->host, &p);
        snprintf(line, sizeof line, "menu popup: declared (%d) (feature_available() is answered after the plugins' start)",
                 (int)r);
        say(line);
        return TD_OK;
    }
    return 1;
}
