/*
 * bm_car_colour.c - Burnout Mashup SDK 0.6.0 example for "bmashup.paints" v1: in a race, player 1's car (service player 0)
 * cycles through four body colours, one every two seconds. It claims the dynamic paint at its first update on the game's
 * thread (takedawn.race's update), then calls set_colour(BODY) every 120 updates. A refusal is logged once and the plugin
 * stays quiet (UNAVAILABLE: a host without the feature; UNSUPPORTED: a car with one palette; CONFLICT: another plugin owns it).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_car_colour.c -o bm_car_colour.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_paints.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_paints_api *s_paints;
static int s_claimed, s_said;
static uint32_t s_updates;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    static const uint32_t colours[4] = { 0xE01010u, 0x10C030u, 0x1040E0u, 0xF0C000u };
    char line[96];
    int32_t r;
    (void)snap; (void)user;
    if (!s_paints)
        return;
    if (!s_claimed) {
        r = s_paints->claim_dynamic(s_api->host, 0);
        if (r != BM_PAINTS_OK) {
            if (!s_said++) {
                snprintf(line, sizeof line, "car colour: claim refused (%d); nothing changes", (int)r);
                say(line);
            }
            return;
        }
        s_claimed = 1;
        say("car colour: dynamic paint claimed");
    }
    if (s_updates++ % 120u == 0u) {
        r = s_paints->set_colour(s_api->host, 0, BM_PAINT_LAYER_BODY, colours[(s_updates / 120u) % 4u]);
        if (r != BM_PAINTS_OK && r != BM_PAINTS_RATE) {
            snprintf(line, sizeof line, "car colour: set_colour refused (%d)", (int)r);
            say(line);
        }
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("car colour: started");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_PAINTS_SERVICE)) {
        const bm_paints_api *p = (const bm_paints_api *)table;
        if (version < 1 || p->struct_size < sizeof *p)
            return 1;
        s_paints = p;
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
