/*
 * bm_takedown_pitch.c - SDK 0.6.0 example: bmashup.hooks version 3 point 12 EVENT_SOUND (MODIFY SOUND_LEVEL).
 * CHANGES GAMEPLAY AUDIO: every takedown-sign sound is played one step higher on the game's own five-step pitch ladder
 * (level 0..4 = 1.0 .. 1.414 x), capped at 4. No new sound is played. A level outside 0..4 would be ignored by the host.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_takedown_pitch.c -o bm_takedown_pitch.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_services.h"
#include "bmashup_hooks.h"

static const td_host_api *s_api;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static int32_t TD_CALL on_sound(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    (void)user;
    if (ctx->struct_size < sizeof *ctx || out->output != BM_HOOK_OUT_SOUND_LEVEL || ctx->sound != BM_SOUND_TAKEDOWN)
        return BM_HOOK_KEEP;
    out->sound_level = out->sound_level < 4u ? out->sound_level + 1u : 4u;
    return BM_HOOK_CHANGE;
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("takedown pitch example: takedown signs one ladder step higher (bmashup.hooks 3 EVENT_SOUND)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    const bm_hooks_api *hk = (const bm_hooks_api *)table;
    bm_hook_reg r;
    uint32_t id = 0;
    int32_t rc;
    char line[160];
    (void)api;
    if (strcmp(name, BM_HOOKS_SERVICE) || version < BM_HOOKS_VERSION_3 || hk->struct_size < sizeof *hk)
        return 1;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    r.point = BM_HOOK_EVENT_SOUND;
    r.role = BM_HOOK_MODIFY;
    r.fn = on_sound;
    rc = hk->register_hook(s_api->host, &r, &id);
    snprintf(line, sizeof line, "takedown pitch example: EVENT_SOUND modify: %s", hk->result_text(rc));
    say(line);
    return rc == BM_HOOKS_OK ? TD_OK : 1;
}