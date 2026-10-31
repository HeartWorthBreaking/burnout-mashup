/*
 * bm_hud_rpm_meter.c - SDK 0.6.0 example: bmashup.hooks version 3 HUD_PASS + bmashup.hud version 2 draw().
 * Visual only. Inside each HUD_PASS it draws a bar (a QUAD) and a "SPEED" label (TEXT) in the top-right corner (640 x 480 HUD
 * units). Platform 0.1.9 draws the QUAD; TEXT answers BM_HUD_UNAVAILABLE there (no glyphs yet) and the example ignores that.
 * On a host without the draw list (draw_available() = 0) it only counts HUD passes. It never calls draw() outside HUD_PASS.
 *
 * Windows (clang or MinGW):  clang -shared -Iinclude bm_hud_rpm_meter.c -o bm_hud_rpm_meter.asi
 */
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_services.h"
#include "bmashup_hooks.h"
#include "bmashup_hud.h"

static const td_host_api *s_api;
static const bm_hud_api *s_hud;
static const bm_hooks_api *s_hk;
static uint32_t s_passes;
static int s_said;

static void say(const char *t) { s_api->log(s_api->host, TD_LOG_INFO, t); }

static int32_t TD_CALL on_pass(const bm_hook_ctx *ctx, bm_hook_out *out, void *user)
{
    bm_hud_cmd c;
    float level;
    (void)out;
    (void)user;
    s_passes++;
    if (!s_hud || !s_hud->draw_available(s_api->host)) {
        if (!s_said) {
            s_said = 1;
            say("hud meter example: HUD_PASS runs; the HUD draw list is not available on this host build");
        }
        return BM_HOOK_KEEP;
    }
    level = (float)(s_passes % 120u) / 120.0f;                  /* a demo level; a real meter reads bmashup.racers */
    (void)ctx;
    memset(&c, 0, sizeof c);
    c.struct_size = (uint32_t)sizeof c;
    c.kind = BM_HUD_CMD_QUAD;
    c.x = 520.0f; c.y = 40.0f; c.w = 100.0f * level; c.h = 8.0f;
    c.rgba = 0xFFC020E0u;
    s_hud->draw(s_api->host, 0, &c);
    c.kind = BM_HUD_CMD_TEXT;
    c.y = 26.0f;
    c.text = "SPEED";
    c.text_size = 10.0f;
    c.rgba = 0xFFFFFFFFu;
    s_hud->draw(s_api->host, 0, &c);
    return BM_HOOK_KEEP;
}

static void bind_pass(void)
{
    bm_hook_reg r;
    uint32_t id = 0;
    char line[120];
    if (!s_hk || !s_hud)
        return;
    memset(&r, 0, sizeof r);
    r.struct_size = (uint32_t)sizeof r;
    r.point = BM_HOOK_HUD_PASS;
    r.role = BM_HOOK_OBSERVE;
    r.fn = on_pass;
    snprintf(line, sizeof line, "hud meter example: HUD_PASS observe: %s", s_hk->result_text(s_hk->register_hook(s_api->host, &r, &id)));
    say(line);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("hud meter example: a bar and a label in the HUD (bmashup.hooks 3 HUD_PASS + bmashup.hud 2 draw)");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                  const void *table)
{
    (void)api;
    if (!strcmp(name, BM_HUD_SERVICE)) {
        const bm_hud_api *h = (const bm_hud_api *)table;
        if (version < BM_HUD_VERSION_2 || h->struct_size < sizeof *h)
            return 1;
        s_hud = h;
        bind_pass();
        return TD_OK;
    }
    if (!strcmp(name, BM_HOOKS_SERVICE)) {
        const bm_hooks_api *hk = (const bm_hooks_api *)table;
        if (version < BM_HOOKS_VERSION_3 || hk->struct_size < sizeof *hk)
            return 1;
        s_hk = hk;
        bind_pass();
        return TD_OK;
    }
    return 1;
}