/*
 * bm_hooks_demo.c - Burnout Mashup's private example of the "bmashup.hooks" service (include/bmashup_hooks.h; contract
 * research\native_gameplay_api\platform\hooks\CONTRACTS.md). Built twice:
 *
 *   owner (default)          mod "bmashup.hooks-demo": RACE_EXIT observer, EXCLUSIVE (it owns the race summary);
 *                            TAKEDOWN observer, priority -10 (shared); BOOST_AWARD modifier: player 1's perfect-lap
 *                            award x1.25 (validated by the service: 0 .. 16 x the game's amount).
 *   rival (BM_HOOKS_DEMO_RIVAL)  mod "bmashup.hooks-rival": asks for RACE_EXIT exclusively too -> refused (CONFLICT, the
 *                            log names the owner); then a shared TAKEDOWN observer, priority 10 (called after the
 *                            owner's: lower priority first).
 *
 * Both register only while Takedawn starts them (takedawn_plugin_service); every callback runs on the game's thread with
 * the guest's registers guarded by the service; nothing here can reach game memory.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_hooks_demo.c -o bm_hooks_demo.asi
 *                            clang -shared -Iinclude -DBM_HOOKS_DEMO_RIVAL bm_hooks_demo.c -o bm_hooks_rival.asi
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_events.h"
#include "bmashup_hooks.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

#ifdef BM_HOOKS_DEMO_RIVAL
#define TAG "hooks rival"
#else
#define TAG "hooks demo"
#endif

static const td_host_api *s_api;
static const bm_hooks_api *s_hk;
static uint32_t s_takedowns, s_id_takedown;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static int32_t TD_CALL on_takedown(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    (void)out;
    (void)user;
    if (ctx->struct_size >= offsetof(bm_hook_ctx, actor_takedowns) + sizeof ctx->actor_takedowns && ctx->actor == 0) {
        s_takedowns++;                                  /* player 1 took a car down */
#ifdef BM_HOOKS_DEMO_RIVAL
        {
            char line[120];
            snprintf(line, sizeof line, TAG ": player 1's takedown %u (called after the demo's observer)", (unsigned)s_takedowns);
            say(line);
        }
#endif
    }
    return BM_HOOK_KEEP;
}

#ifndef BM_HOOKS_DEMO_RIVAL
static int32_t TD_CALL on_race_exit(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    char line[200];
    bm_hook_stats st;
    (void)out;
    (void)user;
    memset(&st, 0, sizeof st);
    st.struct_size = sizeof st;
    s_hk->stats(s_api->host, s_id_takedown, &st);
    snprintf(line, sizeof line, TAG ": race exit %u: player 1 took %u cars down (TAKEDOWN hook called %u times)",
             (unsigned)ctx->race_exits, (unsigned)s_takedowns, (unsigned)st.calls);
    say(line);
    s_takedowns = 0;
    return BM_HOOK_KEEP;
}

static int32_t TD_CALL on_boost(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    (void)user;
    if (!out || ctx->recipient != 0 || ctx->award_source != BM_BOOST_PERFECT_LAP)
        return BM_HOOK_KEEP;
    out->amount = ctx->award_amount * 1.25f;
    return BM_HOOK_CHANGE;
}
#endif

static void reg(uint32_t point, uint32_t role, uint32_t flags, int32_t priority, bm_hook_fn fn, uint32_t *id)
{
    char line[200];
    bm_hook_reg r;
    uint32_t dummy;
    int32_t rc;
    memset(&r, 0, sizeof r);
    r.struct_size = sizeof r;
    r.point = point;
    r.role = role;
    r.flags = flags;
    r.priority = priority;
    r.fn = fn;
    rc = s_hk->register_hook(s_api->host, &r, id ? id : &dummy);
    snprintf(line, sizeof line, TAG ": point %u role %u%s priority %d: %s", (unsigned)point, (unsigned)role,
             flags & BM_HOOK_EXCLUSIVE ? " exclusive" : "", (int)priority, s_hk->result_text(rc));
    say(line);
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

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                   const void *table)
{
    const bm_hooks_api *hk = (const bm_hooks_api *)table;
    (void)api;
    if (strcmp(name, BM_HOOKS_SERVICE) || version < 1 || !hk ||
        hk->struct_size < offsetof(bm_hooks_api, result_text) + sizeof hk->result_text)
        return 1;
    s_hk = hk;
#ifndef BM_HOOKS_DEMO_RIVAL
    reg(BM_HOOK_RACE_EXIT, BM_HOOK_OBSERVE, BM_HOOK_EXCLUSIVE, 0, on_race_exit, NULL);
    reg(BM_HOOK_TAKEDOWN, BM_HOOK_OBSERVE, 0, -10, on_takedown, &s_id_takedown);
    reg(BM_HOOK_BOOST_AWARD, BM_HOOK_MODIFY, 0, 0, on_boost, NULL);
#else
    reg(BM_HOOK_RACE_EXIT, BM_HOOK_OBSERVE, BM_HOOK_EXCLUSIVE, 0, on_takedown, NULL);   /* expected: CONFLICT */
    reg(BM_HOOK_TAKEDOWN, BM_HOOK_OBSERVE, 0, 10, on_takedown, &s_id_takedown);
#endif
    return TD_OK;
}
