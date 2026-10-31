/*
 * race_telemetry.c - a native plugin that reads the race through the
 * "takedawn.race" service (docs/native-plugins.md, The race) and logs it:
 * each change of state, and once a second of race time while racing,
 * player 1's race time, lap, place, speed and position. It reads only: it
 * changes nothing in the game.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude race_telemetry.c -o race_telemetry.asi
 * Windows (MSVC):            cl /LD /Iinclude race_telemetry.c /Fe:race_telemetry.asi
 * Linux:                     cc -shared -fPIC -fvisibility=hidden -Iinclude race_telemetry.c -o librace_telemetry.so
 * macOS:                     cc -dynamiclib -fvisibility=hidden -Iinclude race_telemetry.c -o librace_telemetry.dylib
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

static const td_host_api *s_api;
static uint32_t s_state = 0xFFFFFFFFu;    /* the last state logged */
static float s_next;                       /* the race time of the next line */

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static const char *state_name(uint32_t state)
{
    static const char *const names[] = { "NONE", "LOADING", "FRONTEND", "PRESTART", "RACING", "PAUSED", "FINISHED",
                                         "LEAVING" };
    return state < sizeof names / sizeof names[0] ? names[state] : "?";
}

/* On the game's thread after each of its updates: keep it short. */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    char line[256];
    (void)user;
    if (snap->struct_size < sizeof *snap)
        return;                            /* a snapshot without the fields this plugin reads */
    if (snap->state != s_state) {
        snprintf(line, sizeof line, "state %s", state_name(snap->state));
        say(line);
        if (snap->state == TD_RACE_FINISHED && (snap->valid & TD_RACE_HAVE_CAR)) {
            snprintf(line, sizeof line, "finished: place %d/%u  time %.3f s  best lap %.3f s  laps %u", (int)snap->place,
                     (unsigned)snap->cars, snap->race_time_s, snap->best_lap_s, (unsigned)snap->lap);
            say(line);
        }
        s_state = snap->state;
        s_next = 0.0f;
    }
    if (snap->state == TD_RACE_RACING && (snap->valid & TD_RACE_HAVE_CAR) && snap->race_time_s >= s_next) {
        char speed[64] = "speed -";
        if (snap->valid & TD_RACE_HAVE_SPEED)
            snprintf(speed, sizeof speed, "speed %.1f m/s (%.0f mph)", snap->speed_mps, snap->speed_mps * 2.23694f);
        snprintf(line, sizeof line, "race %.1f s  lap %u  place %d/%u  %s  pos %.1f %.1f %.1f", snap->race_time_s,
                 (unsigned)snap->lap, (int)snap->place, (unsigned)snap->cars, speed, snap->position[0],
                 snap->position[1], snap->position[2]);
        say(line);
        s_next = snap->race_time_s + 1.0f;
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
    say("race telemetry: started, waiting for the takedawn.race service");
    return TD_OK;
}

/* Takedawn's services, one call each, right after init. */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    const td_race_api *race = (const td_race_api *)table;
    (void)api;
    if (strcmp(name, TD_RACE_SERVICE) != 0 || version < 1 || race->struct_size < sizeof *race)
        return 1;                          /* not one this plugin uses */
    if (race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
        return 1;
    say("race telemetry: reading the race (takedawn.race)");
    return TD_OK;
}
