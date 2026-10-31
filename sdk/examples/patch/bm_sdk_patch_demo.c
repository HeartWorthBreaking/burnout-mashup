/*
 * bm_sdk_patch_demo.c - bmashup-sdk example (g): a verified patch of a PUBLISHED SITE on "bmashup.patch" v1 (the portable
 * form: a site name + a value inside the site's bounds; no address in either direction).
 *
 *   mod "bmashup-sdk.patch-demo": the published site "game.byte_fade_rate" (f32, shipped 510.0, bounds 127.5 .. 2040.0)
 *   set to 255.0. The request is checked at once (site known, verified on this build, value finite and in bounds, no
 *   overlap with another plugin's patch) and APPLIED when the plugins' start ends, before the game's first instruction.
 *   Through bmashup.hooks (optional) it logs the patch's state at the first LOAD_DONE (applied, and whether something
 *   wrote over it).
 *
 * The logic and log texts are those of the platform's runtime-validated example (tree_p1 examples\plugins\bmashup-patch,
 * launch 51: "game.byte_fade_rate = 255 applied"); this version uses bmashup_sdk.h discovery. The EXPERIMENTAL address
 * form (request_bytes: build signature + expected bytes) is not used here; see the platform's patch rival example.
 * What the site does in the game is a hypothesis (a byte channel's fade rate); its in-game effect was not observed.
 *
 * Build: the SDK's build.ps1, or  clang -shared -Iinclude bm_sdk_patch_demo.c -o bm_sdk_patch_demo.asi
 */
#include "bmashup_sdk.h"

#define TAG "patch demo"
#define SITE "game.byte_fade_rate"
#define VALUE 255.0

static const td_host_api *s_api;
static const bm_patch_api *s_pt;
static uint32_t s_handle;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_PATCH_SERVICE, 1, BMSDK_PATCH_TABLE_V1, 1),
    BMSDK_NEED(BM_HOOKS_SERVICE, 1, BMSDK_HOOKS_TABLE_V1, 0),     /* only for the status line at the first load */
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
    bm_patch_status st;
    (void)ctx;
    (void)out;
    (void)user;
    if (said || !s_pt || !s_handle)
        return BM_HOOK_KEEP;
    said = 1;
    memset(&st, 0, sizeof st);
    st.struct_size = sizeof st;
    if (s_pt->status(s_api->host, s_handle, &st) == BM_PATCH_OK)
        snprintf(line, sizeof line, TAG ": " SITE ": state %u (2 = applied), reason %s, overwritten %u",
                 (unsigned)st.state, s_pt->result_text(st.reason), (unsigned)st.overwritten);
    else
        snprintf(line, sizeof line, TAG ": no status");
    say(line);
    return BM_HOOK_KEEP;
}

static void use_patch(const bm_patch_api *pt)
{
    char line[200];
    uint32_t idx = 0;
    bm_patch_site_info si;
    int32_t rc;
    s_pt = pt;
    rc = pt->find_site(s_api->host, SITE, &idx);
    memset(&si, 0, sizeof si);
    si.struct_size = sizeof si;
    if (rc == BM_PATCH_OK)
        rc = pt->site_info(s_api->host, idx, &si);
    if (rc == BM_PATCH_OK) {
        snprintf(line, sizeof line, TAG ": site %s: shipped %g, bounds %g .. %g, verified %u", si.name, si.original, si.min,
                 si.max, (unsigned)si.verified);
        say(line);
        rc = pt->request_site(s_api->host, idx, VALUE, &s_handle);
    }
    snprintf(line, sizeof line, TAG ": request " SITE " = %g: %s", VALUE, pt->result_text(rc));
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
    if (!w || w->state != BMSDK_BOUND)
        return 1;                       /* not wanted, or too old: said once at the end of the offers / at shutdown */
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
