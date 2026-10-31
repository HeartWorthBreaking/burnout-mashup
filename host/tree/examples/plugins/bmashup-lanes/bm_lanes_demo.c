/*
 * bm_lanes_demo.c - Burnout Mashup's private example of an engine-limit
 * request (include/bmashup_engine.h): while Takedawn starts it, it asks
 * "bmashup.engine" for a total AI route-lane capacity of 80 (16 lanes beyond
 * the game's 64), so a track mod with up to 80 lanes can load. It logs the
 * answer and the merged capacity. It changes nothing else, and takes no memory
 * itself: the game's lane extension does, only when such a track loads.
 *
 * BM_LANES_DEMO_TOTAL sets another total (the unit test builds a second one).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_lanes_demo.c -o bm_lanes_demo.asi
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_engine.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

#ifndef BM_LANES_DEMO_TOTAL
#define BM_LANES_DEMO_TOTAL 80u
#endif

static const td_host_api *s_api;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    return TD_OK;
}

/* The services, one call each, right after init: the moment to request. */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    const bm_engine_api *en = (const bm_engine_api *)table;
    char line[160];
    uint32_t merged = 0;
    int32_t rc;
    (void)api;
    if (strcmp(name, BM_ENGINE_SERVICE) != 0 || version < 1 || en->struct_size < sizeof *en)
        return 1;                           /* not one this plugin uses */
    rc = en->request_lanes(s_api->host, BM_LANES_DEMO_TOTAL, &merged);
    snprintf(line, sizeof line, "lanes demo: asked for %u total lanes (%u extension entries): %d; merged so far %u",
             (unsigned)BM_LANES_DEMO_TOTAL, (unsigned)(BM_LANES_DEMO_TOTAL - BM_ENGINE_LANES_GAME), (int)rc,
             (unsigned)merged);
    say(line);
    return rc == BM_ENGINE_OK ? TD_OK : 1;
}
