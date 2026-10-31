/*
 * bm_events_demo.c - Burnout Mashup's private example of an engine-event
 * observer (docs/bmashup-events.md). It subscribes to "bmashup.events"'s
 * player-car-update event while Takedawn starts it, counts the events, and
 * once a second of race time logs its count with the event's sequence, step
 * and race time. It only observes: nothing in the game changes.
 *
 * Built twice (BM_EVENTS_DEMO_TAG "A" and "B") as two independently loaded
 * plugins: both see the same updates, so their lines carry the same sequence
 * numbers.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude -DBM_EVENTS_DEMO_TAG=\"A\" bm_events_demo.c -o bm_events_demo_a.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_events.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

#ifndef BM_EVENTS_DEMO_TAG
#define BM_EVENTS_DEMO_TAG "A"
#endif

static const td_host_api *s_api;
static uint32_t s_count;                    /* events seen */
static float s_next;                        /* the race time of the next line */

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

/* On the game's thread inside player 1's car update: keep it short. */
static void TD_CALL on_event(const bm_event *ev, void *user)
{
    char line[160];
    (void)user;
    if (ev->struct_size < sizeof *ev || ev->event != BM_EVENT_PLAYER_CAR_UPDATE)
        return;
    s_count++;
    if (ev->car_phase != 2) {
        s_next = 0.0f;                      /* not racing: the next race starts its lines again */
        return;
    }
    if (ev->race_time_s >= s_next) {
        snprintf(line, sizeof line, "events demo " BM_EVENTS_DEMO_TAG ": %u car updates; sequence %u step %u race %.1f s",
                 (unsigned)s_count, (unsigned)ev->sequence, (unsigned)ev->step, ev->race_time_s);
        say(line);
        s_next = ev->race_time_s + 1.0f;
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
    say("events demo " BM_EVENTS_DEMO_TAG ": started; observes player 1's car updates");
    return TD_OK;
}

/* The services, one call each, right after init: the moment to subscribe. */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    const bm_events_api *ev = (const bm_events_api *)table;
    char line[120];
    int32_t rc;
    (void)api;
    if (strcmp(name, BM_EVENTS_SERVICE) != 0 || version < 1 || ev->struct_size < sizeof *ev)
        return 1;                           /* not one this plugin uses */
    rc = ev->subscribe(s_api->host, BM_EVENT_PLAYER_CAR_UPDATE, on_event, NULL);
    snprintf(line, sizeof line, "events demo " BM_EVENTS_DEMO_TAG ": subscribed to player car updates: %d", (int)rc);
    say(line);
    return rc == BM_EVENTS_OK ? TD_OK : 1;
}
