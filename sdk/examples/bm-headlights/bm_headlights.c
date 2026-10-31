/*
 * bm_headlights.c - Burnout Mashup SDK example for "bmashup.racers" set_light: headlights for every car.
 *
 * The Xbox game never lights the head beams by itself (the light flags get head bits only from the racer light byte, which the
 * game only clears), so on every track the headlights are dark; the running tail lamps likewise (only the brake lamps light).
 * One MOD SETTINGS choice, HEADLIGHTS:
 *   GAME  the game's own lamps (nothing is held)
 *   ON    head beams + running tail lamps on for every racer (set_light HEAD ON, TAIL ON)
 *   OFF   both forced off for every racer (set_light HEAD OFF, TAIL OFF; a host without the light-OFF mark answers UNSUPPORTED)
 * Applied at each race update while racing, only when a racer's wanted state differs from what this plugin last set (the host
 * rate-limits light changes), and given back when the race ends.
 * v0.3.0 (bmashup.racers 6, main21 patch 104): ON also asks set_tail_stand_in(racer, 1000), so models without running-tail
 * lamps (light group 1 empty, e.g. Compact Type 3) show a dim tail glow with their brake lamps; a host below 6 is fine (skipped).
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_headlights.c -o bm_headlights.asi
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_racers.h"
#include "bmashup_settings.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

/* The lamps this plugin drives together: head beams (flag 0x04) and the running tail lamps (flag 0x08, lamp group 1). The game
 * draws the brake lamps (0x10) instead of the running tail while braking, so the tails go dim red -> bright red on the brake. */
static const uint32_t k_lamp[] = { BM_LIGHT_HEAD, BM_LIGHT_TAIL };
#define NLAMP ((uint32_t)(sizeof k_lamp / sizeof k_lamp[0]))

#define TAIL_STAND_IN 1000u                     /* the tail size x 1.0 (about half the brake glow) */

static const td_host_api *s_api;
static const bm_racers_api *s_rc;
static int s_rc6;                               /* the host has set_tail_stand_in (version >= 6, table covers it) */
static int32_t s_want;                          /* 0 GAME, 1 ON, 2 OFF (the setting's choice index) */
static int32_t s_set[BM_RACERS_MAX][NLAMP];     /* what this plugin last set per racer and lamp: -1 nothing held */
static int s_tail[BM_RACERS_MAX];               /* 1: the tail stand-in was asked for this race (OK or refused) */
static int s_racing, s_said_refused;

static int held(uint32_t k)
{
    for (uint32_t j = 0; j < NLAMP; j++)
        if (s_set[k][j] >= 0)
            return 1;
    return s_tail[k];
}

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static void refused(uint32_t k, uint32_t lamp, int32_t r)
{
    if (!s_said_refused) {
        char line[128];
        snprintf(line, sizeof line, "headlights: racer %u lamp %u refused (%s); the game's lamps stay",
                 (unsigned)k, (unsigned)lamp, s_rc->result_text(r));
        say(line);
        s_said_refused = 1;
    }
}

static void give_back(void)
{
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++) {
        if (held(k) && s_rc)
            s_rc->release(s_api->host, k, BM_RACER_CTL_LIGHTS);
        for (uint32_t j = 0; j < NLAMP; j++)
            s_set[k][j] = -1;
        s_tail[k] = 0;
    }
}

static void TD_CALL on_setting(const char *key, int32_t value, uint32_t reason, void *user)
{
    (void)reason; (void)user;
    if (!strcmp(key, "headlights") && value >= 0 && value <= 2)
        s_want = value;
}

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    uint32_t n;
    (void)user;
    if (snap->state != TD_RACE_RACING || !s_rc) {
        if (s_racing)
            give_back();
        s_racing = 0;
        return;
    }
    s_racing = 1;
    n = s_rc->count(s_api->host);
    for (uint32_t k = 0; k < n && k < BM_RACERS_MAX; k++) {
        if (s_want == 0) {
            if (held(k)) {
                s_rc->release(s_api->host, k, BM_RACER_CTL_LIGHTS);
                for (uint32_t j = 0; j < NLAMP; j++)
                    s_set[k][j] = -1;
                s_tail[k] = 0;
            }
            continue;
        }
        uint32_t j;
        for (j = 0; j < NLAMP; j++) {
            int32_t r;
            if (s_set[k][j] == s_want)
                continue;
            r = s_rc->set_light(s_api->host, k, k_lamp[j], s_want == 1 ? BM_LIGHT_ON : BM_LIGHT_OFF);
            if (r == BM_RACERS_OK)
                s_set[k][j] = s_want;
            else if (r == BM_RACERS_RATE)
                break;                          /* this racer's rest waits for the next update */
            else {
                refused(k, k_lamp[j], r);
                s_set[k][j] = s_want;           /* do not ask again this race */
            }
        }
        if (j == NLAMP && s_want == 1 && s_rc6 && !s_tail[k]) {   /* v0.3.0: after HEAD + TAIL, the tail stand-in once a race */
            int32_t r = s_rc->set_tail_stand_in(s_api->host, k, TAIL_STAND_IN);
            if (r == BM_RACERS_OK)
                s_tail[k] = 1;
            else if (r != BM_RACERS_RATE) {
                if (r != BM_RACERS_UNSUPPORTED)
                    refused(k, 0u, r);
                s_tail[k] = 1;                  /* do not ask again this race */
            }
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
    for (uint32_t k = 0; k < BM_RACERS_MAX; k++)
        for (uint32_t j = 0; j < NLAMP; j++)
            s_set[k][j] = -1;
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_RACERS_SERVICE)) {
        const bm_racers_api *rc = (const bm_racers_api *)table;
        if (version < 3 || rc->struct_size < offsetof(bm_racers_api, get_pose))   /* v3 table (lamp_counts is its last) */
            return 1;
        s_rc = rc;
        s_rc6 = version >= 6 && rc->struct_size >= offsetof(bm_racers_api, set_tail_stand_in) + sizeof rc->set_tail_stand_in;
        return TD_OK;
    }
    if (!strcmp(name, BM_SETTINGS_SERVICE)) {
        static const char *const k_choice[] = { "Game", "On", "Off" };
        const bm_settings_api *st = (const bm_settings_api *)table;
        bm_setting_decl d;
        int32_t v = 0;
        if (version < 1 || st->struct_size < sizeof *st)
            return 1;
        memset(&d, 0, sizeof d);
        d.struct_size = BM_SETTING_DECL_V1_SIZE;
        d.kind = BM_SETTING_ENUM;
        d.key = "headlights";
        d.label = "HEADLIGHTS";
        d.choices = k_choice;
        d.nchoices = 3;
        d.def = 0;
        if (st->declare(s_api->host, &d, &v) == BM_SETTINGS_OK && v >= 0 && v <= 2)
            s_want = v;
        st->subscribe(s_api->host, on_setting, NULL);
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
