/*
 * bm_contact_no_crash.c - SDK 0.6.0 example: bmashup.hooks version 3 points 10 TRAFFIC_CONTACT (MODIFY CONTACT_OUTCOME) and
 * 11 WRECK_CAUSE (OBSERVE). CHANGES GAMEPLAY: a racer touching same-direction traffic at a closing speed below 15 m/s does not
 * crash the traffic car (the game's own non-fatal push runs instead). The host refuses NO_CRASH for oncoming traffic and above
 * BM_HOOK_CONTACT_MAX_MPS anyway. Each counted takedown's aggressor / victim is logged (WRECK_CAUSE).
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_contact_no_crash.c -o bm_contact_no_crash.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_services.h"
#include "bmashup_hooks.h"

static const td_host_api *s_api;
static uint32_t s_spared;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static int32_t TD_CALL on_contact(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    (void)user;
    if (ctx->struct_size < sizeof *ctx || out->output != BM_HOOK_OUT_CONTACT_OUTCOME)
        return BM_HOOK_KEEP;
    if (!ctx->contact_same_dir || ctx->contact_closing_mps >= 15.0f)
        return BM_HOOK_KEEP;
    out->outcome = BM_CONTACT_NO_CRASH;
    s_spared++;
    return BM_HOOK_CHANGE;
}

static int32_t TD_CALL on_cause(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    char line[120];
    (void)out;
    (void)user;
    if (ctx->struct_size < sizeof *ctx)
        return BM_HOOK_KEEP;
    snprintf(line, sizeof line, "contact example: takedown counted: racer %d took racer %d down (%u traffic cars spared so far)",
             ctx->cause_aggressor == BM_HOOK_NO_RACER ? -1 : (int)ctx->cause_aggressor, (int)ctx->cause_victim, (unsigned)s_spared);
    say(line);
    return BM_HOOK_KEEP;
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("contact example: same-direction traffic below 15 m/s is not crashed (bmashup.hooks 3 TRAFFIC_CONTACT)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    const bm_hooks_api *hk = (const bm_hooks_api *)table;
    bm_hook_reg r;
    uint32_t id = 0;
    int32_t a, b;
    char line[160];
    (void)api;
    if (strcmp(name, BM_HOOKS_SERVICE) || version < BM_HOOKS_VERSION_3 || hk->struct_size < sizeof *hk)
        return 1;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    r.point = BM_HOOK_TRAFFIC_CONTACT;
    r.role = BM_HOOK_MODIFY;
    r.fn = on_contact;
    a = hk->register_hook(s_api->host, &r, &id);
    r.point = BM_HOOK_WRECK_CAUSE;
    r.role = BM_HOOK_OBSERVE;
    r.fn = on_cause;
    b = hk->register_hook(s_api->host, &r, &id);
    snprintf(line, sizeof line, "contact example: TRAFFIC_CONTACT modify: %s; WRECK_CAUSE observe: %s", hk->result_text(a),
             hk->result_text(b));
    say(line);
    return a == BM_HOOKS_OK || b == BM_HOOKS_OK ? TD_OK : 1;
}