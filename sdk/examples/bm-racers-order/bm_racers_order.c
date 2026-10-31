/*
 * bm_racers_order.c - SDK 0.5.0 example for bmashup.racers version 2: once a second of race time it logs the running order
 * (order()) with each racer's place / laps / race time / phase, and the session. Read only. Rival values are PARTIAL
 * (bmashup_racers.h): compare with the results screen.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_racers_order.c -o bm_racers_order.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_racers.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static float s_next;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    uint32_t ord[BM_RACERS_MAX], n = BM_RACERS_MAX;
    char line[600];
    size_t at;
    bm_racers_session ss;
    (void)user;
    if (!s_rc || snap->state != TD_RACE_RACING) {
        s_next = 0.0f;
        return;
    }
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 1.0f;
    memset(&ss, 0, sizeof ss);
    ss.struct_size = (uint32_t)sizeof ss;
    s_rc->session(s_api->host, &ss);
    if (s_rc->order(s_api->host, ord, &n) != BM_RACERS_OK)
        return;
    at = (size_t)snprintf(line, sizeof line, "t %.0f s, %u racers, %u player(s):", snap->race_time_s, (unsigned)ss.racers,
                          (unsigned)ss.players);
    for (uint32_t k = 0; k < n && at < sizeof line; k++) {
        bm_racer_info r;
        memset(&r, 0, sizeof r);
        r.struct_size = (uint32_t)sizeof r;
        if (s_rc->get(s_api->host, ord[k], &r) != BM_RACERS_OK || r.struct_size < sizeof r)
            continue;
        at += (size_t)snprintf(line + at, sizeof line - at, " [P%d #%u%s lap %u %.1fs ph%u]", (int)r.place, (unsigned)r.index,
                               r.player == 0 ? " YOU" : "", (unsigned)r.laps_done, r.race_time_s, (unsigned)r.phase);
    }
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("racers order example: the running order once a second (bmashup.racers 2)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 2 || rc->struct_size < sizeof *rc || !rc->order || !rc->session)
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
