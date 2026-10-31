/*
 * bm_traffic_attack.c - example for bmashup.traffic version 4 (main21, hook request v2 P5a): a traffic SEED chosen once per
 * game session (so every race of the session, and a replay that runs the traffic reset again, start the spawn generator from
 * the same state) and a lane FLOOR of 2 cars / minute (a lane with some flow but less than 2 / min is raised to 2; busier lanes
 * and lanes without flow are untouched). With bmashup.traffic 5 also: every lane section with some flow gets at least one car and
 * the cars of a section are spread along it (BM_TA_SPREAD). Logs the status every 5 s of race time. CHANGES GAMEPLAY.
 * Build-time options: BM_TA_SEED (0 = derive one from the plugin's start time), BM_TA_FLOOR (0 .. 10 cars / minute),
 * BM_TA_SECTION_MIN (0 .. 4 cars), BM_TA_SPREAD (0 / 1), BM_TA_FILL (0 .. 3: empty lanes take a sibling lane's rates, traffic 6;
 * 2 / 3 = also earlier / any trigger, main21 patch 90), BM_TA_FILL_ALT (1: the fill mode alternates 2 / 3 from race to race -
 * probe R29; the mode is set for the NEXT race when a race is left, the set-up reads it at the next load).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_traffic_attack.c -o bm_traffic_attack.asi
 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "bmashup_traffic.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef BM_TA_SEED
#define BM_TA_SEED 0u
#endif
#ifndef BM_TA_FLOOR
#define BM_TA_FLOOR 2.0f
#endif
#ifndef BM_TA_SECTION_MIN
#define BM_TA_SECTION_MIN 1.0f
#endif
#ifndef BM_TA_SPREAD
#define BM_TA_SPREAD 1u
#endif
#ifndef BM_TA_FILL
#define BM_TA_FILL 0u
#endif
#ifndef BM_TA_FILL_ALT
#define BM_TA_FILL_ALT 0u
#endif

static const td_host_api *s_api;
static const bm_traffic_api *s_tr;
static float s_next;
static uint32_t s_fill = BM_TA_FILL, s_raced;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_traffic_status st;
    char line[260];
    (void)user;
    if (!s_tr || snap->state != TD_RACE_RACING) {
        if (BM_TA_FILL_ALT && s_raced && (snap->state == TD_RACE_LEAVING || snap->state == TD_RACE_FRONTEND) && s_tr) {
            s_raced = 0;
            s_fill = s_fill == 2u ? 3u : 2u;              /* R29: the next race's set-up takes the other mode */
            snprintf(line, sizeof line, "fill mode for the next race: set_fill_empty_lanes(%u) -> %d", (unsigned)s_fill,
                     (int)s_tr->set_fill_empty_lanes(s_api->host, s_fill));
            say(line);
        }
        s_next = 0.0f;
        return;
    }
    s_raced = 1;
    if (snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 5.0f;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_tr->status(s_api->host, &st) != BM_TRAFFIC_OK)
        return;
    snprintf(line, sizeof line, "t %.0f s: active %u of %u, lane floor %.1f (%u lanes raised), seed %08x %s (%u resets seeded), "
             "section min %.1f (%u sections), spread %u (%u cars), fill %u (%u lanes filled)", snap->race_time_s, (unsigned)st.active, (unsigned)st.pool,
             st.lane_floor, (unsigned)st.lanes_raised, (unsigned)st.seed, st.seed_mode == BM_TRAFFIC_SEED_FIXED ? "FIXED" : "GAME",
             (unsigned)st.seeds_applied, st.section_min, (unsigned)st.sections_raised, (unsigned)st.spawn_spread,
             (unsigned)st.cars_spread, (unsigned)st.fill_empty_lanes, (unsigned)st.lanes_filled);
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("traffic attack example: session seed + lane floor (bmashup.traffic 4)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_TRAFFIC_SERVICE)) {
        const bm_traffic_api *tr = (const bm_traffic_api *)table;
        uint32_t seed = BM_TA_SEED ? BM_TA_SEED : (uint32_t)time(NULL) * 2654435761u;
        char line[160];
        int32_t r1, r2;
        if (version < 4 || tr->struct_size < sizeof *tr || !tr->set_seed || !tr->set_lane_floor) {
            say("traffic attack example: this host's bmashup.traffic has no set_seed / set_lane_floor (needs version 4)");
            return 1;
        }
        s_tr = tr;
        r1 = tr->set_seed(s_api->host, BM_TRAFFIC_SEED_FIXED, seed);
        r2 = tr->set_lane_floor(s_api->host, BM_TA_FLOOR);
        snprintf(line, sizeof line, "set_seed(FIXED, %08x) -> %d, set_lane_floor(%.1f) -> %d (UNAVAILABLE = %d)", (unsigned)seed,
                 (int)r1, (double)BM_TA_FLOOR, (int)r2, (int)BM_TRAFFIC_UNAVAILABLE);
        say(line);
        if (version >= 5 && tr->set_section_min && tr->set_spawn_spread) {
            int32_t r3 = tr->set_section_min(s_api->host, BM_TA_SECTION_MIN), r4 = tr->set_spawn_spread(s_api->host, BM_TA_SPREAD);
            snprintf(line, sizeof line, "set_section_min(%.1f) -> %d, set_spawn_spread(%u) -> %d", (double)BM_TA_SECTION_MIN,
                     (int)r3, (unsigned)BM_TA_SPREAD, (int)r4);
            say(line);
        }
        if (version >= 6 && tr->set_fill_empty_lanes && s_fill) {
            snprintf(line, sizeof line, "set_fill_empty_lanes(%u) -> %d", (unsigned)s_fill, (int)tr->set_fill_empty_lanes(s_api->host, s_fill));
            say(line);
        }
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
