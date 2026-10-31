/*
 * bm_detach_parts.c - SDK 0.6.0 example: bmashup.racers version 3 (detach_part).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_detach_parts.c -o bm_detach_parts.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_racers.h"

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static float s_next;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    uint32_t n;
    char line[120];
    (void)user;
    if (!s_rc || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 1.0f;
    n = s_rc->count(s_api->host);
    for (uint32_t k = 0; k < n; k++) {
        bm_racer_info r;
        memset(&r, 0, sizeof r);
        r.struct_size = (uint32_t)sizeof r;
        if (s_rc->get(s_api->host, k, &r) != BM_RACERS_OK || r.player != 0)
            continue;
        for (uint32_t p = 0; p < r.parts; p++)
            if (r.part_state[p] == 2) {                           /* hanging */
                int32_t rc = s_rc->detach_part(s_api->host, k, p);
                snprintf(line, sizeof line, "part %u (kind %u) hanging: detach_part -> %s", (unsigned)p,
                         (unsigned)r.part_kind[p], s_rc->result_text(rc));
                say(line);
            }
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("detach example: player 1's hanging parts come off (bmashup.racers 3 detach_part)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 3 || rc->struct_size < sizeof *rc || !rc->detach_part)
            return 1;
        s_rc = rc;
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
