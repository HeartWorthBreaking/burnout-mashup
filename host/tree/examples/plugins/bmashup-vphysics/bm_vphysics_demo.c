/*
 * bm_vphysics_demo.c - Burnout Mashup's private per-car physics demo (docs/bmashup-vphysics.md), through
 * "bmashup.vphysics" and "takedawn.race". Private, experimental.
 *
 * What it does (VPHYS_DRAG_SCALE, a build-time choice; default 0.5):
 *   - odd races of the process (1st, 3rd, ...): player 1's car "Physics/Race Car/Misc | Drag Coef" x VPHYS_DRAG_SCALE
 *     (set when the race is seen starting; the service applies it at player 1's next car update);
 *   - even races: reset() -> player 1's car back to its own value: the same process's baseline;
 *   - VPHYS_DRAG_SCALE 1 builds a query-only plugin (never asks for a change);
 *   - logs, at each race's start, every racer's vehicle and Drag Coef (current / the game's), and twice a second of race
 *     time player 1's speed and Drag Coef, so a run compares the two halves.
 *
 * Windows (clang):  clang -shared -Iinclude bm_vphysics_demo.c -o bm_vphysics_demo.asi [-DVPHYS_DRAG_SCALE=0.5]
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_vphysics.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef VPHYS_DRAG_SCALE
#define VPHYS_DRAG_SCALE 0.5
#endif

static const td_host_api *s_api;
static const bm_vphys_api *s_vp;
static uint32_t s_drag = 0xFFFFFFFFu, s_state = 0xFFFFFFFFu, s_races;
static float s_next;
static int s_listed;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static int in_stage(uint32_t st)
{
    return st == TD_RACE_PRESTART || st == TD_RACE_RACING || st == TD_RACE_PAUSED || st == TD_RACE_FINISHED;
}

static void list_racers(void)
{
    char line[256];
    uint32_t n = s_vp->racers(s_api->host);
    for (uint32_t r = 0; r < n; r++) {
        bm_vphys_value v;
        v.struct_size = sizeof v;
        if (s_vp->get(s_api->host, r, s_drag, &v) == BM_VPHYS_OK)
            snprintf(line, sizeof line, "race %u racer %u%s %s: Drag Coef %.4g (game %.4g)%s", (unsigned)s_races, (unsigned)r,
                     v.is_player1 ? " (player 1)" : "", v.vehicle, v.current, v.game_value, v.scaled ? " scaled" : "");
        else
            snprintf(line, sizeof line, "race %u racer %u: not readable", (unsigned)s_races, (unsigned)r);
        say(line);
    }
    s_listed = n > 0;
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    char line[256];
    (void)user;
    if (snap->struct_size < sizeof *snap || !s_vp || s_drag == 0xFFFFFFFFu)
        return;
    if (in_stage(snap->state) && (!in_stage(s_state) || (snap->state == TD_RACE_PRESTART && s_state != TD_RACE_PRESTART))) {
        int32_t rc;
        s_races++;
        s_listed = 0;
        s_next = 0.0f;
        if (VPHYS_DRAG_SCALE == 1.0) {
            snprintf(line, sizeof line, "race %u: query only (this build asks for no change)", (unsigned)s_races);
        } else if (s_races % 2 == 1) {
            rc = s_vp->set_scale(s_api->host, s_drag, VPHYS_DRAG_SCALE);
            snprintf(line, sizeof line, "race %u: Drag Coef x%g for player 1: %d", (unsigned)s_races, VPHYS_DRAG_SCALE, (int)rc);
        } else {
            rc = s_vp->reset(s_api->host, s_drag);
            snprintf(line, sizeof line, "race %u: baseline (reset): %d", (unsigned)s_races, (int)rc);
        }
        say(line);
    }
    s_state = snap->state;
    if (snap->state == TD_RACE_RACING && !s_listed)
        list_racers();
    if (snap->state == TD_RACE_RACING && (snap->valid & TD_RACE_HAVE_CAR) && snap->race_time_s >= s_next) {
        bm_vphys_value v;
        char sp[48] = "speed -";
        v.struct_size = sizeof v;
        if (snap->valid & TD_RACE_HAVE_SPEED)
            snprintf(sp, sizeof sp, "speed %.2f m/s", snap->speed_mps);
        if (s_vp->get(s_api->host, 0, s_drag, &v) == BM_VPHYS_OK && v.is_player1)
            snprintf(line, sizeof line, "race %u t %.2f s %s drag %.4g (game %.4g)%s", (unsigned)s_races, snap->race_time_s, sp,
                     v.current, v.game_value, v.scaled ? " scaled" : "");
        else
            snprintf(line, sizeof line, "race %u t %.2f s %s drag -", (unsigned)s_races, snap->race_time_s, sp);
        say(line);
        s_next = snap->race_time_s + 0.5f;
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
    say("vphysics demo: started");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    (void)api;
    if (!strcmp(name, BM_VPHYS_SERVICE) && version >= 1) {
        const bm_vphys_api *vp = (const bm_vphys_api *)table;
        if (vp->struct_size < sizeof *vp || vp->find(s_api->host, "Physics/Race Car/Misc | Drag Coef", &s_drag) != BM_VPHYS_OK)
            return 1;
        s_vp = vp;
        say("vphysics demo: bmashup.vphysics found");
    } else if (!strcmp(name, TD_RACE_SERVICE) && version >= 1) {
        const td_race_api *race = (const td_race_api *)table;
        if (race->struct_size < sizeof *race || race->on_update(s_api->host, on_update, NULL) != TD_RACE_OK)
            return 1;
    } else {
        return 1;
    }
    return TD_OK;
}
