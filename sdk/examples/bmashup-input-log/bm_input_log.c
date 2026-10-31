/*
 * bm_input_log.c - Burnout Mashup SDK 0.5.0 example for "bmashup.input" v1: logs every button press and release of the
 * first host pad, with who has the pad (the game, a host page, the overlay) and where the title is (race, pause, front
 * end, loading). Read only: the title still gets every press. A press made on the MODS / MOD SETTINGS page or in the
 * overlay never shows here (the service reports 0 there), which is the rule a plugin acting on combos must rely on.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_input_log.c -o bm_input_log.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_input.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_input_api *s_in;
static uint32_t s_last_owner, s_last_frame = 0xFFFFFFFFu;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static void names(uint32_t bits, char *out, size_t n)
{
    static const char *const nm[16] = { "A", "B", "X", "Y", "BLACK", "WHITE", "START", "BACK", "L3", "R3", "UP", "DOWN",
                                        "LEFT", "RIGHT", "LT", "RT" };
    size_t k = 0;
    out[0] = 0;
    for (int i = 0; i < 16; i++)
        if (bits & (1u << i))
            k += (size_t)snprintf(out + k, k < n ? n - k : 0, "%s%s", k ? "+" : "", nm[i]);
}

/* takedawn.race's update runs on the game's thread every update, in a race and in the menus. */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_input_pad p;
    char line[200], dn[96], up[96];
    static const char *const owner[] = { "?", "game", "host page", "overlay" };
    static const char *const ctx[] = { "?", "race", "pause", "garage", "front end", "loading" };
    (void)snap; (void)user;
    if (!s_in)
        return;
    memset(&p, 0, sizeof p);
    p.struct_size = (uint32_t)sizeof p;
    if (s_in->pad(s_api->host, 0, &p) != BM_INPUT_OK || p.frame == s_last_frame)
        return;                                 /* no pad, or this frame's snapshot was already read */
    s_last_frame = p.frame;
    if (p.owner != s_last_owner) {
        snprintf(line, sizeof line, "input log: pad 0 now owned by the %s", p.owner < 4 ? owner[p.owner] : "?");
        say(line);
        s_last_owner = p.owner;
    }
    if (!p.pressed && !p.released)
        return;
    names(p.pressed, dn, sizeof dn);
    names(p.released, up, sizeof up);
    snprintf(line, sizeof line, "input log: frame %u (%s): down [%s] up [%s] sticks %.2f %.2f", (unsigned)p.frame,
             p.context < 6 ? ctx[p.context] : "?", dn, up, p.lx, p.ly);
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("input log: started; pad 0's presses go to the log");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_INPUT_SERVICE)) {
        const bm_input_api *in = (const bm_input_api *)table;
        if (version < 1 || in->struct_size < sizeof *in)
            return 1;
        s_in = in;
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
