/*
 * bm_sdk_crash_hooks.c - bmashup-sdk 0.5.0 example: "bmashup.hooks" v2 point 7 CRASH_RESULT (platform 0.1.8 hosts).
 *
 *   mod "bmashup-sdk.crash-hooks": an OBSERVE registration at CRASH_RESULT. Each time the game scores a Crash junction
 *   attempt (its record step), the plugin logs the junction, its IDs, the score and the scoring mode, and keeps the best
 *   score of the session. CRASH_RESULT is OBSERVE only (no output; MODIFY is BAD_ROLE). The same occurrence reaches
 *   bmashup.events v6 subscribers first (BM_EVENT_CRASH_RESULT); a plugin uses whichever service it already has.
 *   The v2 context fields are read only when the host filled them (BMSDK_HAS_FIELD), so the plugin also runs on a v1 host
 *   (where it says that the point is not offered).
 *
 * Build: the SDK's build.ps1, or  clang -shared -Iinclude bm_sdk_crash_hooks.c -o bm_sdk_crash_hooks.asi
 */
#include "bmashup_sdk.h"

#ifndef BMSDK_HOOKS_TABLE_V2
#define BMSDK_HOOKS_TABLE_V2 BMSDK_HOOKS_TABLE_V1                                /* SDK 0.5.0: the table is unchanged */
#endif

#define TAG "crash hooks"

static const td_host_api *s_api;
static uint32_t s_best, s_results;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_HOOKS_SERVICE, 2, BMSDK_HOOKS_TABLE_V2, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static int32_t TD_CALL on_crash(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    char line[200];
    (void)out;
    (void)user;
    if (!BMSDK_HAS_FIELD(ctx, bm_hook_ctx, crash_track_id))
        return BM_HOOK_KEEP;                            /* not a v2 context (cannot happen at point 7; defensive) */
    s_results++;
    if (ctx->crash_score > s_best)
        s_best = ctx->crash_score;
    snprintf(line, sizeof line, TAG ": result %u: junction %u (%s, track %s), score %u, mode %u; best %u",
             (unsigned)ctx->sequence, (unsigned)ctx->crash_junction, ctx->crash_junction_id, ctx->crash_track_id,
             (unsigned)ctx->crash_score, (unsigned)ctx->crash_mode, (unsigned)s_best);
    say(line);
    return BM_HOOK_KEEP;
}

static void TD_CALL on_shutdown(void *user)
{
    char line[96];
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
    snprintf(line, sizeof line, TAG ": %u results this session, best %u", (unsigned)s_results, (unsigned)s_best);
    say(line);
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
    const bm_hooks_api *hk;
    bm_hook_reg r;
    uint32_t id = 0;
    int32_t rc;
    char line[120];
    (void)api;
    if (!w || w->state != BMSDK_BOUND)
        return 1;
    hk = (const bm_hooks_api *)w->table;
    memset(&r, 0, sizeof r);
    r.struct_size = sizeof r;
    r.point = BM_HOOK_CRASH_RESULT;
    r.role = BM_HOOK_OBSERVE;
    r.fn = on_crash;
    rc = hk->register_hook(s_api->host, &r, &id);
    snprintf(line, sizeof line, TAG ": CRASH_RESULT observe: %s", hk->result_text(rc));
    say(line);
    if (rc != BM_HOOKS_OK) {
        bmsdk_fail(w, rc);
        return 1;
    }
    return TD_OK;
}
