/*
 * bm_crash_scores.c - example plugin for bmashup.events version 6 CRASH_RESULT and bmashup.crash version 1 (Burnout Mashup
 * builds only): a Crash score keeper. Each Crash attempt is logged with its junction (number, track) and score, and the
 * plugin keeps the best score of this session per junction ("new session best!"). At start it says how many junctions the
 * game lists. A starting point for Crash leaderboards, challenges (beat a target on a junction) or telemetry. Reads only.
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_crash.h"
#include "bmashup_events.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static const bm_crash_api *s_crash;
static uint32_t s_best[100], s_tries[100];

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_crash(const bm_event *ev, void *user)
{
    char line[200];
    uint32_t j = ev->junction;
    (void)user;
    if (ev->struct_size < sizeof *ev || ev->event != BM_EVENT_CRASH_RESULT)
        return;
    if (ev->sequence == 1 && s_crash) {
        snprintf(line, sizeof line, "crash scores: the game lists %u Crash junctions", (unsigned)s_crash->junction_count(s_api->host));
        say(line);
    }
    if (j >= 100) {
        snprintf(line, sizeof line, "crash scores: a Crash result outside the game's junction list (%s): $%u", ev->junction_id,
                 (unsigned)ev->crash_score);
        say(line);
        return;
    }
    s_tries[j]++;
    snprintf(line, sizeof line, "crash scores: junction %u on %s (%s), attempt %u: $%u%s", (unsigned)j + 1u, ev->track_id,
             ev->junction_id, (unsigned)s_tries[j], (unsigned)ev->crash_score,
             ev->crash_score > s_best[j] ? (s_tries[j] > 1 ? " - new session best!" : "") : "");
    say(line);
    if (ev->crash_score > s_best[j])
        s_best[j] = ev->crash_score;
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    (void)api;
    if (!strcmp(name, BM_CRASH_SERVICE) && version >= 1 && ((const bm_crash_api *)table)->struct_size >= sizeof(bm_crash_api)) {
        s_crash = (const bm_crash_api *)table;
        return TD_OK;
    }
    if (!strcmp(name, BM_EVENTS_SERVICE) && version >= 6 && ((const bm_events_api *)table)->struct_size >= sizeof(bm_events_api))
        return ((const bm_events_api *)table)->subscribe(s_api->host, BM_EVENT_CRASH_RESULT, on_crash, NULL) == BM_EVENTS_OK
                   ? TD_OK : 1;
    return 1;
}
