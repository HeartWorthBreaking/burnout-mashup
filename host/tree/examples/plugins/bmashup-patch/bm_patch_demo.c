/*
 * bm_patch_demo.c - Burnout Mashup's private example of the "bmashup.patch" service (include/bmashup_patch.h; contract
 * research\native_gameplay_api\platform\hooks\CONTRACTS.md). Built twice:
 *
 *   demo (default)           mod "bmashup.patch-demo": the published site "game.byte_fade_rate" (shipped 510.0, bounds
 *                            127.5 .. 2040.0) set to 255.0; through bmashup.hooks it logs the patch's state at the first
 *                            LOAD_DONE (APPLIED, and whether anything wrote over it).
 *   rival (BM_PATCH_DEMO_RIVAL)  mod "bmashup.patch-rival": the EXPERIMENTAL address form on the same four bytes (the build
 *                            signature it was made for + the expected 510.0 + 1020.0) -> refused CONFLICT while the demo
 *                            holds them (the log names the owner); a site value out of bounds -> OUT_OF_BOUNDS; a code
 *                            address -> NOT_DATA. It changes nothing.
 *
 * Requests are made only while Takedawn starts the plugins; nothing is written before the start ends.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_patch_demo.c -o bm_patch_demo.asi
 *                            clang -shared -Iinclude -DBM_PATCH_DEMO_RIVAL bm_patch_demo.c -o bm_patch_rival.asi
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bmashup_hooks.h"
#include "bmashup_patch.h"
#include "takedawn_plugin.h"
#include "takedawn_services.h"

#ifdef BM_PATCH_DEMO_RIVAL
#define TAG "patch rival"
#else
#define TAG "patch demo"
#endif

/* The build this example was made for: Burnout 3: Takedown (USA) default.xbe as Takedawn installs it (FNV-1a 64 of its
 * 2988-byte image header; research\native_gameplay_api\platform\hooks\logs\build_signature.json). */
#define BM_PATCH_DEMO_BUILD 0xD0FC2EF4E9B2A86Full

static const td_host_api *s_api;
#ifndef BM_PATCH_DEMO_RIVAL
static const bm_patch_api *s_pt;
static uint32_t s_handle;
#endif

static void say(const char *text)
{
    s_api->log(s_api->host, TD_LOG_INFO, text);
}

#ifndef BM_PATCH_DEMO_RIVAL
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
        snprintf(line, sizeof line, TAG ": game.byte_fade_rate: state %u (2 = applied), reason %s, overwritten %u",
                 (unsigned)st.state, s_pt->result_text(st.reason), (unsigned)st.overwritten);
    else
        snprintf(line, sizeof line, TAG ": no status");
    say(line);
    return BM_HOOK_KEEP;
}
#endif

static void use_patch(const bm_patch_api *pt)
{
    char line[200];
    uint32_t idx = 0;
    int32_t rc;
#ifndef BM_PATCH_DEMO_RIVAL
    s_pt = pt;
    {
        bm_patch_site_info si;
        rc = pt->find_site(s_api->host, "game.byte_fade_rate", &idx);
        memset(&si, 0, sizeof si);
        si.struct_size = sizeof si;
        if (rc == BM_PATCH_OK)
            rc = pt->site_info(s_api->host, idx, &si);
        if (rc == BM_PATCH_OK) {
            snprintf(line, sizeof line, TAG ": site %s: shipped %g, bounds %g .. %g, verified %u", si.name, si.original, si.min,
                     si.max, (unsigned)si.verified);
            say(line);
            rc = pt->request_site(s_api->host, idx, 255.0, &s_handle);
        }
        snprintf(line, sizeof line, TAG ": request game.byte_fade_rate = 255: %s", pt->result_text(rc));
        say(line);
    }
#else
    {
        static const uint8_t expected[4] = {0x00, 0x00, 0xFF, 0x43};   /* 510.0f */
        static const uint8_t bytes[4] = {0x00, 0x00, 0x7F, 0x44};      /* 1020.0f */
        static const uint8_t code[4] = {0, 0, 0, 0};
        bm_patch_bytes b;
        uint64_t sig = 0;
        uint32_t h = 0;
        pt->build_signature(s_api->host, &sig);
        snprintf(line, sizeof line, TAG ": this build %016llX, made for %016llX", (unsigned long long)sig,
                 (unsigned long long)BM_PATCH_DEMO_BUILD);
        say(line);
        memset(&b, 0, sizeof b);
        b.struct_size = sizeof b;
        b.size = 4;
        b.build_signature = BM_PATCH_DEMO_BUILD;
        b.va = 0x003B1840u;
        b.expected = expected;
        b.bytes = bytes;
        rc = pt->request_bytes(s_api->host, &b, &h);
        snprintf(line, sizeof line, TAG ": bytes at the fade rate = 1020: %s", pt->result_text(rc));
        say(line);
        rc = pt->find_site(s_api->host, "game.racer_proximity_sq", &idx);
        if (rc == BM_PATCH_OK)
            rc = pt->request_site(s_api->host, idx, 1.0e9, &h);
        snprintf(line, sizeof line, TAG ": game.racer_proximity_sq = 1e9: %s", pt->result_text(rc));
        say(line);
        b.va = 0x00011000u;                                            /* .text: code is never patched */
        b.expected = code;
        b.bytes = code;
        rc = pt->request_bytes(s_api->host, &b, &h);
        snprintf(line, sizeof line, TAG ": bytes in the code section: %s", pt->result_text(rc));
        say(line);
    }
#endif
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
    (void)api;
    if (!strcmp(name, BM_PATCH_SERVICE) && version >= 1 && table &&
        ((const bm_patch_api *)table)->struct_size >= offsetof(bm_patch_api, result_text) + sizeof(void *)) {
        use_patch((const bm_patch_api *)table);
        return TD_OK;
    }
#ifndef BM_PATCH_DEMO_RIVAL
    if (!strcmp(name, BM_HOOKS_SERVICE) && version >= 1 && table &&
        ((const bm_hooks_api *)table)->struct_size >= offsetof(bm_hooks_api, result_text) + sizeof(void *)) {
        const bm_hooks_api *hk = (const bm_hooks_api *)table;
        bm_hook_reg r;
        uint32_t id;
        memset(&r, 0, sizeof r);
        r.struct_size = sizeof r;
        r.point = BM_HOOK_LOAD_DONE;
        r.role = BM_HOOK_OBSERVE;
        r.fn = on_load_done;
        return hk->register_hook(s_api->host, &r, &id) == BM_HOOKS_OK ? TD_OK : 1;
    }
#endif
    return 1;
}
