/*
 * bm_sdk_damage_panels.c - bmashup-sdk 0.5.0 example: "bmashup.patch" v2 TABLE sites (platform 0.1.8 hosts).
 *
 *   mod "bmashup-sdk.damage-panels": every car part kind 0..6 is counted AND detached by the game's per-frame part damage
 *   loop (sub_00023DE0), instead of the shipped kinds 2 and 4 only - "more panels come off" (the request's mod 15). Each kind
 *   is set with request_site_pair (count + detach as ONE unit: the damage share is divided by the counted parts, so the two
 *   stay equal). Values 0 / 1 only; the host checks the tables against THIS build at start (a different build: the sites are
 *   unverified and nothing is written). Applied when the plugins' start ends, before the game's first instruction.
 *
 * Scope: PROCESS-WIDE. Every mode that runs the damage loop sees it (Road Rage and others; which modes run it is not
 * established). Its in-game effect is NOT runtime-verified on this platform (the modder's PS2 claim is theirs).
 * Through bmashup.hooks (optional) it logs each pair's state at the first LOAD_DONE.
 *
 * Build: the SDK's build.ps1, or  clang -shared -Iinclude bm_sdk_damage_panels.c -o bm_sdk_damage_panels.asi
 */
#include "bmashup_sdk.h"

#ifndef BMSDK_PATCH_TABLE_V2
#define BMSDK_PATCH_TABLE_V2 BMSDK_FIELD_END(bm_patch_api, request_site_pair)   /* SDK 0.5.0 */
#endif

#define TAG "damage panels"
#define KINDS 7u

static const td_host_api *s_api;
static const bm_patch_api *s_pt;
static uint32_t s_handle[KINDS];
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_PATCH_SERVICE, 2, BMSDK_PATCH_TABLE_V2, 1),
    BMSDK_NEED(BM_HOOKS_SERVICE, 1, BMSDK_HOOKS_TABLE_V1, 0),     /* only for the status lines at the first load */
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

static int32_t TD_CALL on_load_done(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    static int said;
    char line[160];
    (void)ctx;
    (void)out;
    (void)user;
    if (said || !s_pt)
        return BM_HOOK_KEEP;
    said = 1;
    for (uint32_t k = 0; k < KINDS; k++) {
        bm_patch_status st;
        if (!s_handle[k])
            continue;
        memset(&st, 0, sizeof st);
        st.struct_size = sizeof st;
        if (s_pt->status(s_api->host, s_handle[k], &st) == BM_PATCH_OK)
            snprintf(line, sizeof line, TAG ": kind %u: state %u (2 = applied), reason %s, overwritten %u", (unsigned)k,
                     (unsigned)st.state, s_pt->result_text(st.reason), (unsigned)st.overwritten);
        else
            snprintf(line, sizeof line, TAG ": kind %u: no status", (unsigned)k);
        say(line);
    }
    return BM_HOOK_KEEP;
}

static void use_patch(const bm_patch_api *pt)
{
    char line[200], a_name[48], b_name[48];
    s_pt = pt;
    for (uint32_t k = 0; k < KINDS; k++) {
        uint32_t a = 0, b = 0;
        bm_patch_site_info si;
        int32_t rc;
        snprintf(a_name, sizeof a_name, "game.damage.panel_count.%u", (unsigned)k);
        snprintf(b_name, sizeof b_name, "game.damage.panel_detach.%u", (unsigned)k);
        rc = pt->find_site(s_api->host, a_name, &a);
        if (rc == BM_PATCH_OK)
            rc = pt->find_site(s_api->host, b_name, &b);
        memset(&si, 0, sizeof si);
        si.struct_size = sizeof si;
        if (rc == BM_PATCH_OK && pt->site_info(s_api->host, b, &si) == BM_PATCH_OK && BMSDK_HAS_FIELD(&si, bm_patch_site_info, meaning)) {
            if (si.original == 1.0) {                   /* shipped on: nothing to ask */
                snprintf(line, sizeof line, TAG ": kind %u already on (shipped)", (unsigned)k);
                say(line);
                continue;
            }
            rc = pt->request_site_pair(s_api->host, a, b, 1.0, &s_handle[k]);
        }
        snprintf(line, sizeof line, TAG ": kind %u count + detach = 1: %s", (unsigned)k, pt->result_text(rc));
        say(line);
    }
}

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
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
    if (!w || w->state != BMSDK_BOUND)
        return 1;
    if (w == &s_need[0]) {
        use_patch((const bm_patch_api *)w->table);
        return TD_OK;
    }
    {
        const bm_hooks_api *hk = (const bm_hooks_api *)w->table;
        bm_hook_reg r;
        uint32_t id;
        int32_t rc;
        memset(&r, 0, sizeof r);
        r.struct_size = sizeof r;
        r.point = BM_HOOK_LOAD_DONE;
        r.role = BM_HOOK_OBSERVE;
        r.fn = on_load_done;
        rc = hk->register_hook(s_api->host, &r, &id);
        if (rc != BM_HOOKS_OK) {
            bmsdk_fail(w, rc);
            return 1;
        }
        return TD_OK;
    }
}
