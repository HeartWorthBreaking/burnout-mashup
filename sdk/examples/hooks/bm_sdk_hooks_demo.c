/*
 * bm_sdk_hooks_demo.c - bmashup-sdk example (f): coordinated hooks on "bmashup.hooks" v1 (contract: the platform's
 * hooks\CONTRACTS.md, summarised in the mod kit's docs\MODDING_GUIDE.md). Built twice from this one file:
 *
 *   owner (default)               mod "bmashup-sdk.hooks-demo": RACE_EXIT observer, EXCLUSIVE (it owns the race summary);
 *                                 TAKEDOWN observer, priority -10 (shared); BOOST_AWARD modifier: player 1's perfect-lap
 *                                 award x1.25 (validated by the service: 0 .. 16 x the game's amount).
 *   rival (-DBM_HOOKS_DEMO_RIVAL) mod "bmashup-sdk.hooks-rival": asks for RACE_EXIT exclusively too -> refused (CONFLICT, the
 *                                 host's log names the owner); then a shared TAKEDOWN observer, priority 10 (called after
 *                                 the owner's: lower priority first).
 *
 * The logic and log texts are those of the platform's runtime-validated example (tree_p1 examples\plugins\bmashup-hooks,
 * launch 51); this version discovers the service through bmashup_sdk.h (bmsdk_need) and reports a missing / too old
 * service at the end of the offers (BMSDK_DEFINE_SERVICES_DONE), else at shutdown.
 * Hook points exist only where the host build has a mark: 1 PLAYER_CAR_UPDATE, 2 LOAD_DONE, 3 RACE_EXIT, 4 TAKEDOWN,
 * 5 WRECK, 6 BOOST_AWARD. Registration only while the plugins start; every callback gets a fresh copy of typed values
 * (no game pointer); the guest's registers are guarded by the service.
 *
 * Build: the SDK's build.ps1 (both modules), or
 *   clang -shared -Iinclude bm_sdk_hooks_demo.c -o bm_sdk_hooks_demo.asi
 *   clang -shared -Iinclude -DBM_HOOKS_DEMO_RIVAL bm_sdk_hooks_demo.c -o bm_sdk_hooks_rival.asi
 */
#include "bmashup_sdk.h"

#ifdef BM_HOOKS_DEMO_RIVAL
#define TAG "hooks rival"
#else
#define TAG "hooks demo"
#endif

static const td_host_api *s_api;
static const bm_hooks_api *s_hk;
static uint32_t s_takedowns, s_id_takedown;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_HOOKS_SERVICE, 1, BMSDK_HOOKS_TABLE_V1, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static int32_t TD_CALL on_takedown(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    (void)out;
    (void)user;
    if (BMSDK_HAS_FIELD(ctx, bm_hook_ctx, actor_takedowns) && ctx->actor == 0) {
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
    out->amount = ctx->award_amount * 1.25f;            /* the service accepts 0 .. 16 x the game's amount */
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

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);       /* older hosts: a missing service is said here */
}

BMSDK_DEFINE_API_VERSION()
BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    s_api = api;
    if (info && info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {
        info->on_shutdown = on_shutdown;
        info->user = NULL;
    }
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                   const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    (void)api;
    if (!w)
        return 1;                                       /* not one this plugin uses */
    if (w->state != BMSDK_BOUND) {
        bmsdk_log_need(s_api, w);                       /* too old: said now */
        s_reported = 1;
        return 1;
    }
    s_hk = (const bm_hooks_api *)w->table;
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
