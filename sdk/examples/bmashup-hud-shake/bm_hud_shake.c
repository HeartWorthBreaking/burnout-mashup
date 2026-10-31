/*
 * bm_hud_shake.c - Burnout Mashup SDK 0.5.0 example for "bmashup.hud" v1 (hook request mod 08, "Boost Bar Shake"): while
 * player 1 boosts, the boost bar shakes (a small offset that changes every update) and grows a little; when the boost
 * ends the bar is given back at once. It reads the boost state through "bmashup.boost" (status().boosting) and the race
 * through "takedawn.race"; it draws nothing itself and changes no game value: the host applies the transform to the
 * title's own boost bar for each picture and puts the title's values back after it.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_hud_shake.c -o bm_hud_shake.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_boost.h"
#include "bmashup_hud.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#define SHAKE_UNITS 3.0f                    /* HUD units, well inside the service's 64 */
#define SHAKE_SCALE 1.08f

static const td_host_api *s_api;
static const bm_boost_api *s_bb;
static const bm_hud_api *s_hud;
static uint32_t s_rng = 0x2545F491u, s_owned;
static int32_t s_last_rc = -1;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static float jitter(void)                   /* -1 .. 1 */
{
    s_rng ^= s_rng << 13; s_rng ^= s_rng >> 17; s_rng ^= s_rng << 5;
    return (float)(s_rng & 0xFFFFu) / 32767.5f - 1.0f;
}

/* On the game's thread after each of its updates. */
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_boost_status st;
    (void)user;
    if (!s_bb || !s_hud || snap->struct_size < sizeof *snap)
        return;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (snap->state == TD_RACE_RACING && s_bb->status(s_api->host, &st) == BM_BOOST_OK && st.have_meter && st.boosting) {
        bm_hud_transform t;
        int32_t rc;
        t.struct_size = (uint32_t)sizeof t;
        t.dx = SHAKE_UNITS * jitter();
        t.dy = SHAKE_UNITS * jitter();
        t.scale = SHAKE_SCALE;
        t.alpha = 1.0f;
        rc = s_hud->set_transform(s_api->host, 0, BM_HUD_BOOST_BAR, &t);
        s_owned = rc == BM_HUD_OK;
        if (rc != s_last_rc) {
            char line[96];
            snprintf(line, sizeof line, "hud shake: set_transform -> %d", (int)rc);
            say(line);
            s_last_rc = rc;
        }
    } else if (s_owned) {
        s_hud->release(s_api->host, 0, BM_HUD_BOOST_BAR);     /* back at once (else it expires after 4 pictures) */
        s_owned = 0;
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
    say("hud shake: started; the boost bar shakes while player 1 boosts");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_HUD_SERVICE)) {
        const bm_hud_api *h = (const bm_hud_api *)table;
        if (version < 1 || h->struct_size < sizeof *h || !h->element_available(s_api->host, BM_HUD_BOOST_BAR))
            return 1;
        s_hud = h;
        return TD_OK;
    }
    if (!strcmp(name, BM_BOOST_SERVICE)) {
        const bm_boost_api *bb = (const bm_boost_api *)table;
        if (version < 1 || bb->struct_size < 16)        /* v1's fill / status are enough */
            return 1;
        s_bb = bb;
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
