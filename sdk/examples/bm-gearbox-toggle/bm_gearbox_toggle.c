/*
 * bm_gearbox_toggle.c - SDK 0.6.0 example: bmashup.vphysics version 3 (the gearbox). CHANGES GAMEPLAY.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_gearbox_toggle.c -o bm_gearbox_toggle.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"
#include "bmashup_vphysics.h"

static const td_host_api *s_api;
static const bm_vphys_api *s_vp;
static float s_next;
static int s_dir = 1;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    bm_vphys_gearbox_status st;
    char line[160];
    int32_t rc;
    (void)user;
    if (!s_vp)
        return;
    if (snap->state == TD_RACE_PRESTART) {
        s_vp->set_gearbox(s_api->host, 0, BM_GEARBOX_MANUAL);      /* held from the next car update; dropped when the race ends */
        s_next = 0.0f;
        return;
    }
    if (snap->state != TD_RACE_RACING || snap->race_time_s < s_next)
        return;
    s_next = snap->race_time_s + 3.0f;
    memset(&st, 0, sizeof st);
    st.struct_size = (uint32_t)sizeof st;
    if (s_vp->gearbox_status(s_api->host, 0, &st) != BM_VPHYS_OK || !st.available || st.max_gear < 1)
        return;
    if (st.gear >= st.max_gear)
        s_dir = -1;
    else if (st.gear <= 1)
        s_dir = 1;
    rc = s_vp->request_gear(s_api->host, 0, st.gear < 1 ? 1 : st.gear + s_dir);
    snprintf(line, sizeof line, "gear %d of %d, mode %u, request rc %d, idle-fix skips %u", (int)st.gear, (int)st.max_gear,
             (unsigned)st.mode, (int)rc, (unsigned)st.idle_fix_skips);
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("gearbox example: player 1 MANUAL, a shift every 3 s (bmashup.vphysics 3; CHANGES GAMEPLAY)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_VPHYS_SERVICE)) {
        const bm_vphys_api *vp = (const bm_vphys_api *)table;
        if (version < 3 || vp->struct_size < sizeof *vp || !vp->set_gearbox)
            return 1;
        s_vp = vp;
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
