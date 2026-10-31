/*
 * bm_hudv2.c - main19 (hook request P2, item 30; IMPLEMENTATION_PLAN patch 30, FEASIBILITY B2): bmashup.hud version 2 (the
 * draw list) and bmashup.hooks v3 point 8 HUD_PASS (+ bmashup.events v7 event 8).
 *
 * HUD_PASS: once a picture, at the end of bmashup.hud's render (main.c's "uw_stage_render" mark, the one bm_hud.c v1 uses; no
 * new generated-code mark), while the title draws player 0's race HUD scenes (the HUD byte 0x4D61D3, the scene's layers and
 * the players' count: bm_hud.c's own test). OBSERVE only; frame_dt_s = host time since the last HUD_PASS.
 *
 * The draw list: draw() inside a HUD_PASS callback collects validated commands (copies) into this picture's list; the EXECUTOR
 * submits it inside the title's HUD pass, at the end of the boost bar's render callback sub_0004AE40 (item 44's mark
 * BO3_HUDX_DRAW, after its last render-state call 0x4B1B4; probe PR-F ran rects there), once a picture, only while the HUD byte
 * 0x4D61D3 is set, with the title's own rect primitive sub_001C7430 in its retail call shape (0x4B00E): EAX = the rect list
 * (x0 y0 x1 y1 floats), ECX = the colour float4 (RGBA 0..1, 16-byte aligned), stack origin float2 *, count, uv list *; the caller
 * removes the 12 bytes. Coordinates: 640 x 480 HUD units with origin (0, 0) (the title applies its own widescreen mapping).
 * Before the list the texture of stage 0 is unbound (sub_0034DE60: push raster 0, push stage 0) and the title's bound-texture
 * cache 0x4A1B78 is reset to 0 after it (the title binds its own again at its next draw). The buffers (16 KiB, the colour words
 * 16-byte aligned) are ONE block in mem256's high zone (xbox_ContiguousAllocHigh), taken at the first draw; a refusal leaves the
 * list unserved (draw_available 0, one log line), never a fail-fast exit.
 * PLATFORM 0.1.9 (item 44, BM_P23_HUD_DRAW_LIVE 1): QUAD commands are drawn (solid colour, rotation 0 only: UNSUPPORTED
 * otherwise); TEXT answers UNAVAILABLE (glyph rects: BM_P23_HUD_TEXT_LIVE 0); SPRITE / texture_info answer UNKNOWN_TEXTURE
 * because [bmashup.hud] textures are not loaded (BM_P23_HUD_TEXTURES_LIVE 0: the fetex path + budgets are a later item). If the
 * boost bar is not drawn in a picture (a mode without it), that picture's list is not drawn either.
 * Item 46 (fork F, after PR-F): the title's texture state is used the way its own 2D draws use it (FACT, offline: the boost
 * bar's sub_0004AE40 0x4AEE8..0x4AF19 + the deferred-state commit sub_001D7040 that the flush sub_001C69C0 -> sub_001D7D50
 * runs): a texture T is "bound" by flushing the pending vertices (sub_001C69C0 while [0x4A1B9C] > 0), setting T's palette
 * MEM32(T + 0x14) with sub_0034DE60 (= the device's SetPalette: push palette, push stage 0; ret 8) and writing T into
 * 0x75DB70 (stage 0's texture, committed with SetTexture sub_0034DCA0 at the next flush) and the cache 0x4A1B78. A QUAD binds
 * no texture (0x75DB70 = 0, a retail value: sub_000324A0 / sub_00033130); before item 46 the quads were drawn with whatever
 * texture the title had bound (the PR-F shots: "tint + the bound texture"). After the list the vertices are flushed, the
 * title's 0x75DB70 and stage-0 palette are put back and the cache is reset (the title binds its own again).
 * TEXT (BM_P23_HUD_TEXT_LIVE 1): glyph rects through the same primitive with the host glyph atlas bm_hud_font.h (a 5 x 7
 * dot font drawn by tests\p23\hudfont\make_hud_font.py, P8 TXD of the fetex format, copied into the draw block and fixed up
 * with the game's TXD rules at the first draw); <= BM_HUD_GLYPHS_PER_PICTURE glyphs a picture (FULL).
 * SPRITE / texture_info (BM_P23_HUD_TEXTURES_LIVE 1): the texture is an entry of an admitted [bmashup.textures] TXD (fetex
 * registry, pool in mem256's high zone, its limits: 256 entries a mod, 768 / 12 MiB in all): "<entry>" = the plugin's own
 * mod, "<mod-id>/<entry>" any mod. P8 entries only (the format the title's HUD uses; DXT answers UNSUPPORTED). No new mod.toml
 * table: [bmashup.hud] is NOT read (a mod declaring it is refused by the platform check, as in item 44).
 * Item 30 (before the probe) had no executor (draw UNAVAILABLE); BM_P23_HUD_DRAW_LIVE 0 restores exactly that.
 * BO3_HOOKREQ_P23 == 0: HUD_PASS is not offered and the ops are not registered (v2 calls UNAVAILABLE).
 * MUT=n (tests only): 241 draw outside HUD_PASS accepted, 242 the per-plugin limit not enforced, 243 a bad text character
 * accepted, 244 HUD_PASS dispatched while the HUD is hidden, 245 the list not cleared between pictures; item 44: 246 the list
 * drawn twice in a picture, 247 drawn while the HUD byte is clear, 248 the colour block not 16-byte aligned, 249 the bound-texture
 * cache not reset, 250 the census skipped; item 46: 251 a non-P8 texture accepted, 252 the glyph limit not enforced, 253 the
 * title's bound texture (0x75DB70) not put back, 254 no flush before a bind, 255 the title's palette not put back; item 51: 256
 * the texture pool not installed by the HUD (a registered entry of a never-installed pool stays UNKNOWN_TEXTURE).
 */
#include "bm_hud.h"

#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "bm_fetex.h"
#include "bm_guest.h"
#include "bm_hooks.h"
#include "bm_hud_font.h"
#include "bo3_hudx_gen.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif

/* item 44 (probe PR-F): 1 = the executor draws the list (QUADs); 0 = item 30's form (draw UNAVAILABLE). */
#ifndef BM_P23_HUD_DRAW_LIVE
#define BM_P23_HUD_DRAW_LIVE 1
#endif
/* item 46: TEXT = glyph rects (host atlas); 0 = item 44's form (TEXT UNAVAILABLE) */
#ifndef BM_P23_HUD_TEXT_LIVE
#define BM_P23_HUD_TEXT_LIVE 1
#endif
/* item 46: SPRITE / texture_info = [bmashup.textures] P8 entries; 0 = item 44's form (UNKNOWN_TEXTURE) */
#ifndef BM_P23_HUD_TEXTURES_LIVE
#define BM_P23_HUD_TEXTURES_LIVE 1
#endif

#define HX_HUD_ON     0x004D61D3u       /* the HUD byte (bm_hud.h BO3_HUD_ON) */
#define HX_TEX_CACHE  0x004A1B78u       /* the title's bound-texture cache (texture object of its last bind) */
#define HX_TEX_STAGE0 0x0075DB70u       /* stage 0's texture, committed by sub_001D7040 at the next flush */
#define HX_PENDING    0x004A1B9Cu       /* vertices waiting in the immediate buffer 0x752F78 */
#define HX_DEVICE     0x0035FB48u       /* the D3D device; + 0xF98 = stage 0's palette (sub_0034DE60) */
#define HX_RET_SITE   0x0004B013u       /* a retail return address of a sub_001C7430 call in sub_0004AE40 */
#define HX_BLOCK      0x10000u          /* item 46: cmds 0x0000, glyph rects 0x3000, glyph uvs 0x7000, font 0xC000, origin 0xFFF0 */
#define HX_GLYPH_R    0x3000u
#define HX_GLYPH_UV   0x7000u
#define HX_FONT       0xC000u
#define HX_ORIGIN     0xFFF0u
_Static_assert(BM_HUD_GLYPHS_PER_PICTURE * 16u <= HX_GLYPH_UV - HX_GLYPH_R && HX_GLYPH_UV + BM_HUD_GLYPHS_PER_PICTURE * 16u <= HX_FONT,
               "glyph areas");
_Static_assert(HX_FONT + BM_HUD_FONT_TXD_BYTES <= HX_ORIGIN && BM_HUD_CMDS_PER_PICTURE * 48u <= HX_GLYPH_R, "draw block layout");

typedef struct bo3_hud_item {
    const td_host *owner;
    bm_hud_cmd cmd;                     /* the pointers below point into this item */
    uint32_t tex_va;                    /* item 46: SPRITE = the entry's guest VA (resolved at draw()) */
    char texture[64];
    char text[BM_HUD_TEXT_MAX + 1];
} bo3_hud_item;
typedef void (*bo3_hud_exec_fn)(const bo3_hud_item *items, uint32_t n);

static bo3_hud_item s_items[BM_HUD_CMDS_PER_PICTURE];
static uint32_t s_n;
static struct { const td_host *host; uint32_t n; } s_per[32];
static int s_nper;
static RECOMP_TLS int t_in_pass;
static bo3_hud_exec_fn s_exec;          /* platform 0.1.9: none */
static uint32_t s_passes, s_executed;
static double s_last_t;
static double (*s_clock)(void);
static int s_pending;                   /* item 44: a list waits for this picture's executor call */
static uint32_t s_block;                /* item 44: the guest buffers (high zone), 0 = not yet / refused */
static int s_block_refused, s_census_ok;
static uint32_t (*s_alloc)(uint32_t size);
static uint32_t s_drawn_pictures, s_drawn_cmds;
static uint32_t s_glyphs;               /* item 46: glyphs in this picture's list */
static uint32_t s_font_va;              /* item 46: the atlas entry (texture object) in the draw block, 0 = not installed */
static int (*s_tex_find)(const char *canonical, bo3_fetex_info *out) = bo3_fetex_find;
static int (*s_tex_install)(void) = bo3_fetex_install;          /* item 51 */
static int (*s_tex_installed)(void) = bo3_fetex_installed;

static double now_s(void)
{
    struct timespec ts;
    if (s_clock)
        return s_clock();
    timespec_get(&ts, TIME_UTC);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int fin(float v)
{
    return v == v && v - v == 0.0f;
}

static int text_ok(const char *s)
{
    size_t n;
    if (!s)
        return 0;
    n = strnlen(s, BM_HUD_TEXT_MAX + 1);
    if (n == 0 || n > BM_HUD_TEXT_MAX)
        return 0;
    for (size_t i = 0; i < n; i++) {
        char c = s[i];
#if MUT == 243
        continue;
#endif
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || strchr(" .,:!?-+/%'\"", c)))
            return 0;
    }
    return 1;
}

static uint32_t *per_count(const td_host *h)
{
    for (int k = 0; k < s_nper; k++)
        if (s_per[k].host == h)
            return &s_per[k].n;
    if (s_nper == (int)(sizeof s_per / sizeof s_per[0]))
        return NULL;
    s_per[s_nper].host = h;
    s_per[s_nper].n = 0;
    return &s_per[s_nper++].n;
}

/* ---- item 44: the live executor ---- */
extern void sub_001C7430(void);
extern void sub_0034DE60(void);
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
static uint32_t game_alloc(uint32_t size) { return xbox_ContiguousAllocHigh(size, 0x1000u); }
#else
extern uint32_t xbox_ContiguousAlloc(uint32_t size, uint32_t alignment);
static uint32_t game_alloc(uint32_t size) { return xbox_ContiguousAlloc(size, 0x1000u); }
#endif

static int hx_hud_on(void)
{
    uint8_t v = 0;
    return bo3_guest_read(HX_HUD_ON, &v, 1) && v != 0;
}
static int (*s_exec_hud_on)(void) = hx_hud_on;

typedef struct { uint32_t gpr[8]; RecompXmm x[8]; int top; } hx_regs;
static void hx_save(hx_regs *r)
{
    r->gpr[0] = g_eax; r->gpr[1] = g_ebx; r->gpr[2] = g_ecx; r->gpr[3] = g_edx;
    r->gpr[4] = g_esi; r->gpr[5] = g_edi; r->gpr[6] = g_ebp; r->gpr[7] = g_esp;
    r->x[0] = g_xmm0; r->x[1] = g_xmm1; r->x[2] = g_xmm2; r->x[3] = g_xmm3;
    r->x[4] = g_xmm4; r->x[5] = g_xmm5; r->x[6] = g_xmm6; r->x[7] = g_xmm7;
    r->top = g_fp_top;
}
static void hx_restore(const hx_regs *r)
{
    g_eax = r->gpr[0]; g_ebx = r->gpr[1]; g_ecx = r->gpr[2]; g_edx = r->gpr[3];
    g_esi = r->gpr[4]; g_edi = r->gpr[5]; g_ebp = r->gpr[6]; g_esp = r->gpr[7];
    g_xmm0 = r->x[0]; g_xmm1 = r->x[1]; g_xmm2 = r->x[2]; g_xmm3 = r->x[3];
    g_xmm4 = r->x[4]; g_xmm5 = r->x[5]; g_xmm6 = r->x[6]; g_xmm7 = r->x[7];
    g_fp_top = r->top;
}

extern void sub_001C69C0(void);

/* item 46: the title's own sequence (sub_0004AE40 0x4AEF6..0x4AF19): vertices of the previous texture go out first */
static void hx_flush(void)
{
    uint32_t pending = 0;
    hx_regs r;
#if MUT == 254
    return;
#endif
    if (!bo3_guest_read(HX_PENDING, &pending, 4) || pending == 0)
        return;
    hx_save(&r);
    PUSH32(g_esp, HX_RET_SITE);
    sub_001C69C0();
    hx_restore(&r);
}

/* stage 0's palette (sub_0034DE60 = the device's SetPalette: push palette, push stage 0; ret 8) */
static void hx_palette(uint32_t pal)
{
    hx_regs r;
    hx_save(&r);
    PUSH32(g_esp, pal);
    PUSH32(g_esp, 0u);                       /* stage 0 */
    PUSH32(g_esp, HX_RET_SITE);
    sub_0034DE60();
    hx_restore(&r);
}

static uint32_t hx_rd32(uint32_t va)
{
    uint32_t v = 0;
    return bo3_guest_read(va, &v, 4) ? v : 0;
}

/* bind texture object T (0 = none: a solid colour), as the title's own 2D draws do */
static int s_pal_changed;
static void hx_bind(uint32_t t)
{
    uint32_t pal = t ? hx_rd32(t + 0x14u) : 0;
    hx_flush();
    if (pal) {
        hx_palette(pal);
        s_pal_changed = 1;
    }
    bo3_guest_write(HX_TEX_STAGE0, &t, 4);
    bo3_guest_write(HX_TEX_CACHE, &t, 4);
}

/* one call of the rect primitive in the retail shape (n rects, one colour) */
static void hx_rects(uint32_t rects, uint32_t colour, uint32_t origin, uint32_t n, uint32_t uvs)
{
    hx_regs r;
    hx_save(&r);
    g_eax = rects;
    g_ecx = colour;
    PUSH32(g_esp, uvs);
    PUSH32(g_esp, n);
    PUSH32(g_esp, origin);
    PUSH32(g_esp, HX_RET_SITE);
    sub_001C7430();
    hx_restore(&r);
}

/* item 46: the glyph atlas into the draw block, with the game's TXD fix-ups (bm_fetex.c fixup(): sub_001BEEF0 / sub_001C8E20
 * rules) -> the entry VA (a texture object), 0 when the TXD is not the expected one */
static uint32_t rd_le(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr_le(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t font_install(uint32_t va)
{
    uint8_t p[BM_HUD_FONT_TXD_BYTES];
    uint32_t off, e, data;
    memcpy(p, k_bm_hud_font_txd, sizeof p);
    if (rd_le(p + 8) != 1u)
        return 0;
    wr_le(p + 12, rd_le(p + 12) + va);
    off = rd_le(p + 0x10 + 8);
    if (off + 0x70u > sizeof p || p[off + 0x69] != 1u)
        return 0;
    e = va + off;
    wr_le(p + 0x10 + 8, e);
    data = rd_le(p + off + 4) + e;
    if ((rd_le(p + off) & 0x70000u) != 0x20000u)
        data &= 0x0FFFFFFFu;
    wr_le(p + off + 4, data);
    {
        uint32_t po = rd_le(p + off + 0x14), pd;
        if (off + po + 8u > sizeof p)
            return 0;
        wr_le(p + off + 0x14, po + e);
        pd = rd_le(p + off + po + 4) + e;
        if ((rd_le(p + off + po) & 0x70000u) != 0x20000u)
            pd &= 0x0FFFFFFFu;
        wr_le(p + off + po + 4, pd);
    }
    if (!bo3_guest_write(va, p, (uint32_t)sizeof p))
        return 0;
    return e;
}

static void exec_live(const bo3_hud_item *items, uint32_t n)
{
    uint32_t base, k = 0, g = 0, saved_tex, saved_pal, dev;
    const float origin[2] = {0.0f, 0.0f};
    if (!s_block) {
        if (s_block_refused)
            return;
        s_block = (s_alloc ? s_alloc : game_alloc)(HX_BLOCK);
        if (!s_block || (s_block & 0xFFFu)) {
            s_block = 0;
            s_block_refused = 1;
            fprintf(stderr, "[HUD] draw list: the guest buffers (%u bytes, high zone) were refused: nothing is drawn\n",
                    (unsigned)HX_BLOCK);
            return;
        }
        s_font_va = font_install(s_block + HX_FONT);
        if (!s_font_va)
            fprintf(stderr, "[HUD] draw list: the glyph atlas did not install: TEXT is not drawn\n");
    }
    base = s_block;
#if MUT == 248
    base += 4u;
#endif
    dev = hx_rd32(HX_DEVICE);
    saved_tex = hx_rd32(HX_TEX_STAGE0);
    saved_pal = dev ? hx_rd32(dev + 0xF98u) : 0;
    s_pal_changed = 0;
    bo3_guest_write(base + HX_ORIGIN, origin, sizeof origin);
    for (uint32_t i = 0; i < n; i++) {
        const bm_hud_cmd *c = &items[i].cmd;
        float col[4];
        uint32_t cb = base + 48u * k, rb = cb + 16u, ub = cb + 32u;
        col[0] = (float)((c->rgba >> 24) & 0xFFu) / 255.0f;
        col[1] = (float)((c->rgba >> 16) & 0xFFu) / 255.0f;
        col[2] = (float)((c->rgba >> 8) & 0xFFu) / 255.0f;
        col[3] = (float)(c->rgba & 0xFFu) / 255.0f;
        bo3_guest_write(cb, col, sizeof col);
        if (c->kind == BM_HUD_CMD_QUAD || c->kind == BM_HUD_CMD_SPRITE) {
            float rect[4], uv[4] = {0.0f, 0.0f, 1.0f, 1.0f};
            if (c->kind == BM_HUD_CMD_SPRITE) {
                if (!items[i].tex_va)
                    continue;
                uv[0] = c->u0; uv[1] = c->v0; uv[2] = c->u1; uv[3] = c->v1;
            }
            rect[0] = c->x; rect[1] = c->y; rect[2] = c->x + c->w; rect[3] = c->y + c->h;
            bo3_guest_write(rb, rect, sizeof rect);
            bo3_guest_write(ub, uv, sizeof uv);
            hx_bind(c->kind == BM_HUD_CMD_SPRITE ? items[i].tex_va : 0u);
            hx_rects(rb, cb, base + HX_ORIGIN, 1u, ub);
            k++;
        } else if (c->kind == BM_HUD_CMD_TEXT && items[i].cmd.text && s_font_va) {
            const char *s = items[i].cmd.text, *chars = BM_HUD_FONT_CHARS;
            float sc = c->text_size / (float)BM_HUD_FONT_GLYPH_H, x = c->x;
            uint32_t g0 = g, cells = BM_HUD_FONT_W / BM_HUD_FONT_CELL;
            for (; *s && g < BM_HUD_GLYPHS_PER_PICTURE; s++, x += 6.0f * sc) {
                const char *p = strchr(chars, *s);
                float rect[4], uv[4];
                uint32_t idx, cx, cy;
                if (*s == ' ' || !p)
                    continue;
                idx = (uint32_t)(p - chars);
                cx = (idx % cells) * BM_HUD_FONT_CELL;
                cy = (idx / cells) * BM_HUD_FONT_CELL;
                rect[0] = x; rect[1] = c->y; rect[2] = x + 5.0f * sc; rect[3] = c->y + 7.0f * sc;
                uv[0] = (float)cx / BM_HUD_FONT_W; uv[1] = (float)cy / BM_HUD_FONT_H;
                uv[2] = (float)(cx + BM_HUD_FONT_GLYPH_W) / BM_HUD_FONT_W; uv[3] = (float)(cy + BM_HUD_FONT_GLYPH_H) / BM_HUD_FONT_H;
                bo3_guest_write(base + HX_GLYPH_R + 16u * g, rect, sizeof rect);
                bo3_guest_write(base + HX_GLYPH_UV + 16u * g, uv, sizeof uv);
                g++;
            }
            if (g > g0) {
                hx_bind(s_font_va);
                hx_rects(base + HX_GLYPH_R + 16u * g0, cb, base + HX_ORIGIN, g - g0, base + HX_GLYPH_UV + 16u * g0);
            }
            k++;
        }
    }
    /* our vertices out with our state, then the title's state back (its next draw binds its own again: cache reset) */
    hx_flush();
#if MUT != 253
    bo3_guest_write(HX_TEX_STAGE0, &saved_tex, 4);
#endif
#if MUT != 249
    {
        uint32_t zero = 0;
        bo3_guest_write(HX_TEX_CACHE, &zero, 4);
    }
#endif
#if MUT != 255
    if (s_pal_changed && dev && hx_rd32(dev + 0xF98u) != saved_pal)
        hx_palette(saved_pal);
#endif
    s_drawn_pictures++;
    s_drawn_cmds += k;
}

/* item 47: the executor for a host-made list outside the race HUD (bmashup.menu's car-select bars, drawn from a front-end 2D
 * render callback): QUAD / TEXT only, <= 16 commands; 1 drawn, 0 not (P23 off, census / BM_P23_HUD_DRAW_LIVE, bad command) */
int bo3_hudx_draw_cmds(const bm_hud_cmd *cmds, uint32_t n)
{
    static bo3_hud_item it[16];
    if (!BO3_HOOKREQ_P23 || s_exec != exec_live || !cmds || n == 0 || n > 16u)
        return 0;
    for (uint32_t i = 0; i < n; i++) {
        memset(&it[i], 0, sizeof it[i]);
        it[i].cmd = cmds[i];
        it[i].cmd.texture = NULL;
        it[i].cmd.text = NULL;
        if (cmds[i].kind == BM_HUD_CMD_TEXT) {
            if (!text_ok(cmds[i].text))
                return 0;
            snprintf(it[i].text, sizeof it[i].text, "%s", cmds[i].text);
            it[i].cmd.text = it[i].text;
        } else if (cmds[i].kind != BM_HUD_CMD_QUAD) {
            return 0;
        }
    }
    exec_live(it, n);
    return 1;
}

static int32_t sprite_entry(const td_host *host, const char *texture, uint32_t *va, uint32_t *w, uint32_t *h)
{
    bo3_fetex_info fi;
    char canon[128];
    if (!texture || !texture[0] || strlen(texture) > 96)
        return BM_HUD_BAD_ARG;
    if (!BM_P23_HUD_TEXTURES_LIVE || !s_tex_find)
        return BM_HUD_UNKNOWN_TEXTURE;
    if (strchr(texture, '/'))
        snprintf(canon, sizeof canon, "%s", texture);
    else
        snprintf(canon, sizeof canon, "%s/%s", bo3_plugins_host_id(host), texture);
    if (!s_tex_find(canon, &fi))
        return BM_HUD_UNKNOWN_TEXTURE;          /* not registered */
    /* item 51 (runtime m19_r2a): the pool is installed lazily at the first front-end lookup that needs it (bm_fetex.c ready());
     * a mod whose texture no front-end binding asks for (a photo this host does not serve, a HUD-only TXD) left it uninstalled
     * for the whole run -> every SPRITE answered UNKNOWN_TEXTURE. The HUD installs it itself (game thread; once). */
#if MUT != 256
    if (!fi.va && s_tex_install && s_tex_installed && s_tex_installed() == 0 && s_tex_install() && !s_tex_find(canon, &fi))
        return BM_HUD_UNKNOWN_TEXTURE;
#endif
    if (!fi.va)
        return BM_HUD_UNKNOWN_TEXTURE;          /* the pool install failed (logged by bm_fetex.c) */
#if MUT != 251
    if (fi.fmt != BO3_FETEX_P8 || fi.palettes < 1)
        return BM_HUD_UNSUPPORTED;              /* DXT: not the format the title's HUD binds (palette at +0x14) */
#endif
    if (va)
        *va = fi.va;
    if (w)
        *w = fi.w;
    if (h)
        *h = fi.h;
    return BM_HUD_OK;
}
static int32_t v2_draw(td_host *host, uint32_t player, const bm_hud_cmd *c)
{
    uint32_t *pc, tex_va = 0, nglyph = 0;
    bo3_hud_item *it;
    if (!c || c->struct_size < sizeof(bm_hud_cmd))
        return BM_HUD_BAD_ARG;
    if (!s_exec || s_block_refused)
        return BM_HUD_UNAVAILABLE;                       /* no executor (BM_P23_HUD_DRAW_LIVE 0 / census), or no buffers */
    if (player == 1)
        return BM_HUD_UNSUPPORTED;
    if (player != 0)
        return BM_HUD_BAD_ARG;
#if MUT != 241
    if (!t_in_pass)
        return BM_HUD_NOT_IN_PASS;
#endif
    if (c->kind < BM_HUD_CMD_QUAD || c->kind > BM_HUD_CMD_TEXT)
        return BM_HUD_BAD_ARG;
    if (!fin(c->x) || !fin(c->y) || c->x < -64.0f || c->x > 704.0f || c->y < -64.0f || c->y > 544.0f)
        return BM_HUD_OUT_OF_RANGE;
    if (c->kind != BM_HUD_CMD_TEXT &&
        (!fin(c->w) || !fin(c->h) || c->w < 0.0f || c->h < 0.0f || c->w > 768.0f || c->h > 768.0f ||
         !fin(c->rotation_rad) || fabsf(c->rotation_rad) > 6.2831853f))
        return BM_HUD_OUT_OF_RANGE;
    if (c->kind != BM_HUD_CMD_TEXT && c->rotation_rad != 0.0f)
        return BM_HUD_UNSUPPORTED;                       /* item 44: the title's rect primitive draws axis-aligned rects */
    if (c->kind == BM_HUD_CMD_SPRITE) {
        if (!fin(c->u0) || !fin(c->v0) || !fin(c->u1) || !fin(c->v1) || c->u0 < 0 || c->u0 > 1 || c->v0 < 0 || c->v0 > 1 ||
            c->u1 < 0 || c->u1 > 1 || c->v1 < 0 || c->v1 > 1)
            return BM_HUD_OUT_OF_RANGE;
        if (!c->texture)
            return BM_HUD_BAD_ARG;
        {
            int32_t rc = sprite_entry(host, c->texture, &tex_va, NULL, NULL);   /* item 46: a [bmashup.textures] P8 entry */
            if (rc != BM_HUD_OK)
                return rc;
        }
    }
    if (c->kind == BM_HUD_CMD_TEXT) {
        if (!fin(c->text_size) || c->text_size < 8.0f || c->text_size > 64.0f)
            return BM_HUD_OUT_OF_RANGE;
        if (!text_ok(c->text))
            return BM_HUD_BAD_TEXT;
        if (s_exec == exec_live && (!BM_P23_HUD_TEXT_LIVE || (s_block && !s_font_va)))
            return BM_HUD_UNAVAILABLE;                   /* item 46 off (item 44's form), or the atlas did not install */
        for (const char *s = c->text; *s; s++)
            nglyph += *s != ' ';
#if MUT != 252
        if (s_glyphs + nglyph > BM_HUD_GLYPHS_PER_PICTURE)
            return BM_HUD_FULL;
#endif
    }
    if (s_n == BM_HUD_CMDS_PER_PICTURE || !(pc = per_count(host)))
        return BM_HUD_FULL;
#if MUT != 242
    if (*pc >= BM_HUD_CMDS_PER_PLUGIN)
        return BM_HUD_FULL;
#endif
    it = &s_items[s_n++];
    (*pc)++;
    memset(it, 0, sizeof *it);
    it->owner = host;
    it->cmd = *c;
    it->cmd.struct_size = (uint32_t)sizeof it->cmd;
    it->cmd.texture = NULL;
    it->cmd.text = NULL;
    it->tex_va = tex_va;
    s_glyphs += nglyph;
    if (c->kind == BM_HUD_CMD_SPRITE) {
        snprintf(it->texture, sizeof it->texture, "%s", c->texture);
        it->cmd.texture = it->texture;
    }
    if (c->kind == BM_HUD_CMD_TEXT) {
        snprintf(it->text, sizeof it->text, "%s", c->text);
        it->cmd.text = it->text;
    }
    return BM_HUD_OK;
}

static int32_t v2_texture_info(td_host *host, const char *texture, uint32_t *w, uint32_t *h)
{
    if (!w || !h)
        return BM_HUD_BAD_ARG;
    *w = *h = 0;
    if (!s_exec)
        return BM_HUD_UNAVAILABLE;
    return sprite_entry(host, texture, NULL, w, h);                 /* item 46: [bmashup.textures] P8 entries */
}

static uint32_t v2_draw_available(void)
{
    return s_exec != NULL && !s_block_refused;
}

static void v2_pass(int hud_drawn)
{
    double now = now_s();
    bm_hook_ctx c;
#if MUT != 245
    s_n = 0;
    s_nper = 0;
    s_glyphs = 0;
#endif
#if MUT != 244
    if (!hud_drawn)
        return;
#endif
    s_passes++;
    if (bo3_hk_point_wanted(BM_HOOK_HUD_PASS)) {
        bo3_hk_ctx_v3(&c, BM_HOOK_HUD_PASS);
        c.player = 0;
        c.hud_visible = (uint32_t)(hud_drawn != 0);
        c.frame_dt_s = s_last_t > 0.0 && now > s_last_t && now - s_last_t < 1.0 ? (float)(now - s_last_t) : 0.0f;
        t_in_pass = 1;
        bo3_hk_dispatch_v3(BM_HOOK_HUD_PASS, &c, NULL);
        t_in_pass = 0;
    }
    s_last_t = now;
    s_pending = s_exec && s_n;               /* item 44: drawn by the executor mark inside the title's HUD pass */
}

/* item 44: the executor mark (the title's HUD pass, the boost bar's callback end): this picture's list, once */
void bo3_hudx_gen_draw(void)
{
    if (!s_pending)
        return;
#if MUT != 247
    if (!s_exec_hud_on())
        return;
#endif
#if MUT != 246
    s_pending = 0;
#endif
    s_exec(s_items, s_n);
    s_executed += s_n;
}

static const bo3_hud_v2_ops k_ops = {v2_draw, v2_texture_info, v2_draw_available, v2_pass};

/* item 44: the executor's sites in guest memory (XBE 9f497acd): the mark's place at the end of sub_0004AE40, the rect
 * primitive's and the bind routine's entries */
static const struct { uint32_t va; const char *hex; } k_census[] = {
    {0x0004B1AFu, "83c40c33f6e827d117005f5e5b8be55d"},
    {0x001C7430u, "558bec83ec205356578bf8833d601b4a00020f8470010000e8d3f4ffff33f689"},
    {0x0034DE60u, "538b5c2408568b3548fb35008b849e980f000085c0577425"},
    /* item 46: the title's bind sequence this executor repeats (boost bar 0x4AEE8..0x4AF1F: cache, pending flush, palette at
     * +0x14, stage-0 texture 0x75DB70), the flush, and the commit of 0x75DB70 by SetTexture sub_0034DCA0 */
    {0x0004AEE8u, "8b35380946003b35781b4a007429a19c1b4a0085c07605e8bcba17008b461485c07408506a00e84d2f3000893570db75008935781b4a00"},
    {0x001C69C0u, "f605a8d6350010"},
    {0x001D7100u, "8b04b570db75003904b534aa4100740e50568904b534aa4100e8826b170046"},
};

static int census(void)
{
#if MUT == 250
    return 1;
#endif
    for (size_t r = 0; r < sizeof k_census / sizeof k_census[0]; r++) {
        uint8_t cur[64];
        size_t n = strlen(k_census[r].hex) / 2;
        if (n > sizeof cur || !bo3_guest_read(k_census[r].va, cur, (uint32_t)n))
            return 0;
        for (size_t i = 0; i < n; i++) {
            unsigned v = 0;
            for (int k = 0; k < 2; k++) {
                char ch = k_census[r].hex[2 * i + (size_t)k];
                v = v * 16u + (unsigned)(ch >= '0' && ch <= '9' ? ch - '0' : ch - 'a' + 10);
            }
            if (cur[i] != (uint8_t)v)
                return 0;
        }
    }
    return 1;
}

void bo3_hudv2_init(void)
{
#if BO3_HOOKREQ_P23
    bo3_bm_hud_set_v2(&k_ops);
    bo3_hk_offer_point(BM_HOOK_HUD_PASS, 1u << BM_HOOK_OBSERVE, NULL);
    s_census_ok = census();
    if (BM_P23_HUD_DRAW_LIVE && s_census_ok)
        s_exec = exec_live;
    fprintf(stderr, "[HUD] version 2: HUD_PASS offered; the draw list %s\n",
            s_exec == exec_live ? (BM_P23_HUD_TEXT_LIVE && BM_P23_HUD_TEXTURES_LIVE ? "is drawn (QUAD, TEXT, SPRITE of [bmashup.textures] P8 entries)" : "is drawn (QUADs; TEXT / SPRITE per BM_P23_HUD_TEXT_LIVE / _TEXTURES_LIVE)")
                                : "is UNAVAILABLE (BM_P23_HUD_DRAW_LIVE 0 or the game's bytes differ from the census)");
#else
    (void)k_ops;
    (void)census;
    (void)exec_live;
#endif
}

/* tests */
void bo3_hudv2_test_live(uint32_t (*alloc)(uint32_t size), int (*hud_on)(void))
{
    s_alloc = alloc;
    if (hud_on)
        s_exec_hud_on = hud_on;
    s_block = 0;
    s_block_refused = 0;
    s_font_va = 0;
}

/* tests: the texture registry stand-in (item 46) */
void bo3_hudv2_test_tex(int (*find)(const char *canonical, bo3_fetex_info *out))
{
    s_tex_find = find;
}

uint32_t bo3_hudv2_font_va(void)
{
    return s_font_va;
}

uint32_t bo3_hudv2_drawn(uint32_t *cmds)
{
    if (cmds)
        *cmds = s_drawn_cmds;
    return s_drawn_pictures;
}

int bo3_hudv2_live(void)
{
    return s_exec == exec_live;
}

void bo3_hudv2_test_setup(void (*exec)(const void *items, uint32_t n), double (*clock_fn)(void))
{
    s_pending = 0;
    s_exec = (bo3_hud_exec_fn)(void (*)(void))exec;
    s_clock = clock_fn;
    s_n = 0;
    s_nper = 0;
    s_passes = s_executed = 0;
    s_last_t = 0.0;
}

uint32_t bo3_hudv2_passes(void)
{
    return s_passes;
}

uint32_t bo3_hudv2_items(const void **items)
{
    if (items)
        *items = s_items;
    return s_n;
}
