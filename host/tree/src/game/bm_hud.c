/*
 * bm_hud.c - main18 (platform 0.1.8, hook request P1 "hud v1"): "bmashup.hud" (include/bmashup_hud.h), per-picture
 * transforms of named retail HUD elements. Design gp\hookreq\HOOK_REQUEST_DESIGN.md s1 B (B1), rules R0-R6.
 *
 * The title's 2D engine (docs/widescreen-hud.md; generated code):
 *   - the HUD object 0x54F900 holds a scene per player at + 0x14 + 0x70 p (0x54F914 / 0x54F984), drawn by sub_000536C0 while
 *     the byte 0x4D61D3 is set (crash / takedown cameras clear it);
 *   - a scene's root frame is [scene + 0x14] (sub_001C17A0, the root sync of a scene's render: it copies the root's local
 *     values (+0, +4 position, +8, +0xC scale, +0x10 colour) to its world values (+0x20, +0x24, +0x28, +0x2C, +0x30) - the
 *     widescreen squeeze of display.hud_fix is applied there, to the root's world x scale / origin - then sub_001C1670
 *     makes every child frame's world values from its parent's (world pos = parent pos + parent scale * local pos, world
 *     scale = parent scale * local scale, colour multiplied);
 *   - the layers at [scene + 0x2C] (count + 0x30, 16 bytes each, bit 0 of the first word: hidden) list objects from + 8,
 *     linked through their first word; sub_001C6500 draws an object at frame origin + frame scale * (x + 8, y + 0xC), size
 *     frame scale * (w + 0x10, h + 0x14), colour object (+ 0x18, alpha + 0x24) * frame (+ 0x30), through its callback
 *     (+ 0x44); its frame is + 0x40.
 * What this service writes: the x / y / w / h / alpha words of the element's objects (never a frame: the scene's render
 * recomputes frames' world values from their local ones), at the "uw_stage_render" mark (after display.score_board's own
 * writes: alpha multiplies), and puts them back at "uw_flip" or the next render - each word only if it still holds the
 * value written here (the title's write in between wins). The title's update runs after the flip and before the next
 * render, so it only ever sees its own values (scoreboard.c's pattern, design rule R3).
 * The transform in screen units: the element's drawn box B (all its objects' boxes), centre C; an object's box (X, Y, W, H)
 * becomes (C + (X - C) k + q d, W k, H k) with q = the root's world / local scale (the squeeze: 1 without display.hud_fix or
 * in 4:3), then back to the object's frame: x' = (X' - frame x) / frame scale. World values are the last render's (a frame
 * the title moved this update carries its own move through unchanged; only the scale centre lags one picture).
 * Guest memory only through bm_guest.c (the runtime's windows); a pointer that fails the check ends that walk.
 * MUT=n (tests) compiles one defect.
 */
#include "bm_hud.h"

#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif

#define H_SCENE0     (BO3_HUD_MANAGER + 0x14u)
#define H_PLAYERS    (BO3_HUD_MANAGER + 0x170u)
#define H_GUARD      500
#define H_OBJS       64                 /* objects of one element taken in one picture */
#define H_WRITES     1024
#define H_NEL        (BM_HUD_ELEMENTS + 1)

/* main21 patch 108: POSITION / LAP / SPEED / TAKEDOWNS served by their components' frames (BO3_HOOKREQ_ZHUD; CMake ON in the
 * game; unit tests without the define keep the hud v1 contract: unserved) */
#ifndef BO3_HOOKREQ_ZHUD
#define BO3_HOOKREQ_ZHUD 0
#endif
#define H_COMP_OBJS 8                   /* a component frame with more objects is not one of these elements (a stale frame) */

/* element -> how it is told apart (0: not served in this build) */
enum { HOW_NONE = 0, HOW_CB = 1, HOW_BOARD = 2, HOW_COMP = 3 };
#if BO3_HOOKREQ_ZHUD
#define HOW_C HOW_COMP
#else
#define HOW_C HOW_NONE
#endif
static const struct { uint32_t how, cb; const char *name; } k_el[H_NEL] = {
    { HOW_NONE, 0, "" },
    { HOW_CB, BO3_HUD_CB_BOOST, "BOOST_BAR" },
    { HOW_CB, BO3_HUD_CB_BMSG, "BOOST_MESSAGE" },
    { HOW_C, BO3_HUD_C_POS, "POSITION" },       /* plates 0x48430 + digits 0xF6DC0, shared with LAP / board: by its frame */
    { HOW_C, BO3_HUD_C_LAP, "LAP" },
    { HOW_C, BO3_HUD_C_SPEED, "SPEED" },        /* 0xF7C20 text, shared with the centre message: by its frame */
    { HOW_C, BO3_HUD_C_TD, "TAKEDOWNS" },
    { HOW_BOARD, 0, "SCORE_BOARD" },
    { HOW_CB, BO3_HUD_CB_AWARD, "AWARD" },
    { HOW_C, BO3_HUD_CMSG_FRAME, "CENTRE_MESSAGE" },   /* patch 119: the board's message slot frame (cmsg_frame) */
};

/* ---- guest reads (silent on a failed window check: a walk just ends) ---- */
static int ok_ptr(uint32_t va, uint32_t n) { return va && !(va & 3u) && bo3_guest_window(va, n) != BO3_GUEST_NONE; }
static uint32_t r32(uint32_t va) { uint32_t v = 0; if (ok_ptr(va, 4)) bo3_guest_read(va, &v, 4); return v; }
static float rf(uint32_t va) { float v = 0.0f; if (ok_ptr(va, 4)) bo3_guest_read(va, &v, 4); return v; }
static uint8_t r8(uint32_t va) { uint8_t v = 0; if (va && bo3_guest_window(va, 1)) bo3_guest_read(va, &v, 1); return v; }
static int fin(float v) { return v == v && v < 1e30f && v > -1e30f; }

/* ---- requests (player 0) ---- */
typedef struct { const void *owner; bm_hud_transform t; uint32_t pic; int live; } req;
static req s_req[H_NEL];
static uint32_t s_pic;                  /* pictures (flips) counted here */
static uint32_t s_render_pic;           /* s_pic at the last stage render */
static int s_rendered;                  /* a stage render was seen */
static RECOMP_TLS int t_game;
static const bo3_hud_v2_ops *s_v2;      /* main19 (v2): bm_hudv2.c */
static int s_hud_drawn;                 /* main19: the last render found player 0's HUD scenes drawn */

/* ---- writes to put back ---- */
static struct { uint32_t va, put, was; } s_w[H_WRITES];
static int s_nw, s_nw_last;

/* ---- the rects, published for any thread (sequence count, odd while written) ---- */
#define RECT_WORDS (H_NEL * 5)
static _Atomic uint32_t s_seq;
static _Atomic uint32_t s_rw[RECT_WORDS];

static void publish(const uint32_t *w)
{
    uint32_t q = atomic_load_explicit(&s_seq, memory_order_relaxed);
    atomic_store_explicit(&s_seq, q + 1, memory_order_relaxed);
    atomic_thread_fence(memory_order_release);
    for (int k = 0; k < RECT_WORDS; k++)
        atomic_store_explicit(&s_rw[k], w[k], memory_order_relaxed);
    atomic_store_explicit(&s_seq, q + 2, memory_order_release);
}

static int expired(const req *r)
{
#if MUT == 2
    return !r->live;                    /* defect: requests never expire */
#else
    return !r->live || s_pic - r->pic >= BM_HUD_TTL_PICTURES;
#endif
}

static void wr(uint32_t va, uint32_t put)
{
    uint32_t now = r32(va);
    if (now == put || !ok_ptr(va, 4) || s_nw == H_WRITES)
        return;
    s_w[s_nw].va = va;
    s_w[s_nw].put = put;
    s_w[s_nw].was = now;
    s_nw++;
    bo3_guest_write(va, &put, 4);
}

static void wrf(uint32_t va, float v)
{
    uint32_t u;
    memcpy(&u, &v, 4);
    wr(va, u);
}

void bo3_bm_hud_restore(void)
{
    t_game = 1;
    for (int i = s_nw - 1; i >= 0; i--) {
#if MUT == 5
        bo3_guest_write(s_w[i].va, &s_w[i].was, 4);     /* defect: the title's write in between is overwritten */
#else
        if (r32(s_w[i].va) == s_w[i].put)
            bo3_guest_write(s_w[i].va, &s_w[i].was, 4);
#endif
    }
    s_nw = 0;
}

/* scoreboard.c's test: the board component's frame counts only while it holds plates and texts with a plate centred at
 * the top (in a mode without a board the component keeps a stale frame the pool may have given to something else). */
static int is_board(uint32_t la, uint32_t nl, uint32_t fr)
{
    float ox = rf(fr + 0x20), oy = rf(fr + 0x24), sx = rf(fr + 0x28), sy = rf(fr + 0x2C);
    int plate = 0;
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++) {
            uint32_t cb = r32(n + 0x44);
            float cx, y;
            if (r32(n + 0x40) != fr)
                continue;
            if (cb != BO3_HUD_CB_PLATE && cb != BO3_HUD_CB_DIGITS)
                return 0;
            if (cb != BO3_HUD_CB_PLATE)
                continue;
            cx = ox + sx * (rf(n + 8) + rf(n + 16) * 0.5f);
            y = oy + sy * rf(n + 12);
            if (cx > 256.0f && cx < 384.0f && y > -40.0f && y < 120.0f)
                plate = 1;
        }
    }
    return plate;
}

/* patch 108: a component's frame counts only while 1..8 objects of the scene are drawn on it and each is a plate, digits or a
 * text (the component keeps its frame when the element is not shown; the pool may give it to something else) */
static int comp_frame_ok(uint32_t la, uint32_t nl, uint32_t fr)
{
    int c = 0;
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        if (r32(la + l * 16) & 1u)
            continue;
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++) {
            uint32_t cb;
            if (r32(n + 0x40) != fr)
                continue;
            cb = r32(n + 0x44);
#if MUT != 83
            if (cb != BO3_HUD_CB_PLATE && cb != BO3_HUD_CB_DIGITS && cb != BO3_HUD_CB_TEXT)
                return 0;
#endif
            c++;
        }
    }
    return c >= 1 && c <= H_COMP_OBJS;
}

static uint32_t s_cf[H_NEL];            /* patch 108: this picture's component frames (0: not shown / not trusted) */

/* main21 patch 119: the centre message's frame M (board + 0x30) counts only while the slot holds a message object whose node frame
 * (object + 0x38 = node + 0x40) is M and 1..8 objects of the scene are drawn on M - with ANY callback (the slot's messages use
 * texts 0xF7C20, digits 0xF6DC0, 0x20CD0, award texts 0x5AC20 or the 0x1C2xxx family). No message -> not shown, never stale.
 * MUT (tests): 85 the slot's object not checked  86 the object count not bounded */
static uint32_t cmsg_frame(uint32_t la, uint32_t nl, uint32_t bfr)
{
    uint32_t o = r32(BO3_HUD_CMSG_OBJ), m = r32(BO3_HUD_CMSG_FRAME);
    int c = 0;
#if MUT != 85
    if (!o || !ok_ptr(o - 8u, 0x48) || r32(o + 0x38) != m)
        return 0;
#endif
    if (!ok_ptr(m, 0x40) || m == bfr)
        return 0;
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        if (r32(la + l * 16) & 1u)
            continue;
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++)
            if (r32(n + 0x40) == m)
                c++;
    }
#if MUT == 86
    return c >= 1 ? m : 0;
#else
    return c >= 1 && c <= H_COMP_OBJS ? m : 0;
#endif
}

static uint32_t element_of(uint32_t cb, uint32_t fr, uint32_t bfr)
{
    if (bfr && fr == bfr)
        return BM_HUD_SCORE_BOARD;
    for (uint32_t e = 1; e < H_NEL; e++)
        if (k_el[e].how == HOW_COMP && s_cf[e] && s_cf[e] == fr)
            return e;
    for (uint32_t e = 1; e < H_NEL; e++)
        if (k_el[e].how == HOW_CB && k_el[e].cb == cb)
            return e;
    return 0;
}

typedef struct { uint32_t obj[H_OBJS]; int n; float x0, y0, x1, y1; } coll;

/* ---- main21 patch 72 (open item 3): a DEV-ONLY identification switch for the HUD components (BO3_HUD_IDPROBE=1 builds only;
 * the default build compiles none of it). The race HUD layout sub_00052D50 builds player 1's components on fixed objects; five
 * plate / digit components are POSITION / LAP / TAKEDOWNS / CENTRE_MESSAGE candidates (notes\ITEM3_HUD_COMPONENTS.md). Every
 * HID_SLOT_PICS pictures the next candidate is chosen; its frame is FOUND (the first words of the component are scanned for a
 * pointer that is the frame of objects in the scene: + 8 is only the board's known slot) and that frame's objects are drawn
 * HID_DY HUD units lower for the slot (the same put-back writes as a transform). One "[HUDID]" line per slot says which
 * component, which offset held the frame and how many objects it has; window shots name the element. Nothing else changes. */
#ifndef BO3_HUD_IDPROBE
#define BO3_HUD_IDPROBE 0
#endif
#if BO3_HUD_IDPROBE
#define HID_SLOT_PICS 240u          /* 4 s at 60 pictures a second */
#define HID_DY 60.0f
#define HID_SCAN 0x60u              /* component words scanned for the frame pointer */
static const uint32_t k_idc[] = { 0x003FD4A0u, 0x003FD4F8u, 0x003FDE70u, 0x003FDFA8u, 0x003FDD98u, 0x003FDD48u, 0x003FE460u };
#define HID_N (sizeof k_idc / sizeof k_idc[0])
static void (*s_idlog)(const char *line);
static uint32_t s_id_slot = 0xFFFFFFFFu;
void bo3_bm_hud_idprobe_log(void (*fn)(const char *line)) { s_idlog = fn; s_id_slot = 0xFFFFFFFFu; }

static int id_count(uint32_t la, uint32_t nl, uint32_t fr)
{
    int c = 0;
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        if (r32(la + l * 16) & 1u)
            continue;
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++)
            c += r32(n + 0x40) == fr;
    }
    return c;
}

static void id_probe(uint32_t la, uint32_t nl)
{
    uint32_t slot = s_pic / HID_SLOT_PICS, comp = k_idc[slot % HID_N], best_fr = 0, best_off = 0;
    int best = 0;
    char hits[200];
    size_t hl = 0;
    hits[0] = 0;
#if MUT == 81
    for (uint32_t off = 8; off <= 8; off += 4) {           /* defect: only the board's + 8 tried */
#else
    for (uint32_t off = 0; off < HID_SCAN; off += 4) {
#endif
        uint32_t v = r32(comp + off);
        int c;
        if (!ok_ptr(v, 0x40))
            continue;
        c = id_count(la, nl, v);
        if (c > 0 && hl < sizeof hits - 24)
            hl += (size_t)snprintf(hits + hl, sizeof hits - hl, " +0x%02X:%d", (unsigned)off, c);
        if (c > best)
            best = c, best_fr = v, best_off = off;
    }
    if (slot != s_id_slot) {
        char line[320];
        s_id_slot = slot;
        snprintf(line, sizeof line, "[HUDID] picture %u: candidate %u component 0x%08X %s (frame words:%s)", (unsigned)s_pic,
                 (unsigned)(slot % HID_N), (unsigned)comp, best ? "moved 60 down" : "no frame with objects in the scene",
                 hl ? hits : " none");
        if (s_idlog)
            s_idlog(line);
        else
            fprintf(stderr, "%s (frame at +0x%02X)\n", line, (unsigned)best_off);
    }
    if (!best)
        return;
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        if (r32(la + l * 16) & 1u)
            continue;
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++) {
            float sy;
            if (r32(n + 0x40) != best_fr)
                continue;
            sy = rf(best_fr + 0x2C);
            if (fin(sy) && fabsf(sy) > 1e-6f)
#if MUT == 82
                wrf(n + 12, rf(n + 12) + HID_DY);       /* defect: local units, not screen */
#else
                wrf(n + 12, rf(n + 12) + HID_DY / sy);  /* screen y + 60: local y + 60 / the frame's world y scale */
#endif
        }
    }
}
#endif

static void hud_render(void)
{
    static coll c[H_NEL];
    uint32_t words[RECT_WORDS], sc = H_SCENE0, la, nl, root, bfr;
    float qx = 1.0f, qy = 1.0f;
    int hud_on;

    t_game = 1;
    if (s_nw)
        bo3_bm_hud_restore();
    s_rendered = 1;
    s_render_pic = s_pic;
    memset(words, 0, sizeof words);
    memset(c, 0, sizeof c);
    la = r32(sc + 0x2C);
    nl = r32(sc + 0x30);
    root = r32(sc + 0x14);
    hud_on = r8(BO3_HUD_ON) != 0;
    if (!ok_ptr(la, 16) || !nl || nl > 256 || !hud_on || r32(H_PLAYERS) == 0) {
        publish(words);
        s_nw_last = 0;
        return;
    }
    s_hud_drawn = 1;
    if (ok_ptr(root, 0x30)) {             /* the squeeze: the root's world scale over its local one */
        float lx = rf(root + 8), wx = rf(root + 0x28), ly = rf(root + 0xC), wy = rf(root + 0x2C);
        if (fin(lx) && fin(wx) && lx != 0.0f && wx / lx > 0.1f && wx / lx < 4.0f)
            qx = wx / lx;
        if (fin(ly) && fin(wy) && ly != 0.0f && wy / ly > 0.1f && wy / ly < 4.0f)
            qy = wy / ly;
    }
    bfr = r32(BO3_HUD_BOARD_P0 + 8);
    if (!ok_ptr(bfr, 0x40) || !is_board(la, nl, bfr))
        bfr = 0;
    for (uint32_t e = 1; e < H_NEL; e++) {  /* patch 108 */
        uint32_t f;
        s_cf[e] = 0;
        if (k_el[e].how != HOW_COMP)
            continue;
        if (e == BM_HUD_CENTRE_MESSAGE) {       /* patch 119 */
            s_cf[e] = cmsg_frame(la, nl, bfr);
            continue;
        }
        f = r32(k_el[e].cb + 8);
        if (ok_ptr(f, 0x40) && f != bfr && comp_frame_ok(la, nl, f))
            s_cf[e] = f;
    }
#if MUT != 84
    for (uint32_t e = 1; e < H_NEL; e++)    /* two components on one frame: neither is trusted */
        for (uint32_t k = e + 1; k < H_NEL; k++)
            if (s_cf[e] && s_cf[e] == s_cf[k])
                s_cf[e] = s_cf[k] = 0;
#endif
    for (uint32_t l = 0; l < nl; l++) {
        int guard = 0;
        if (r32(la + l * 16) & 1u)
            continue;                       /* a hidden layer is not drawn */
        for (uint32_t n = r32(la + l * 16 + 8); ok_ptr(n, 0x48) && guard < H_GUARD; n = r32(n), guard++) {
            uint32_t fr = r32(n + 0x40), e = element_of(r32(n + 0x44), fr, bfr);
            float fx, fy, sx, sy, X, Y, W, H;
            if (!e || !ok_ptr(fr, 0x40) || c[e].n == H_OBJS)
                continue;
            fx = rf(fr + 0x20); fy = rf(fr + 0x24); sx = rf(fr + 0x28); sy = rf(fr + 0x2C);
            X = fx + sx * rf(n + 8); Y = fy + sy * rf(n + 12); W = sx * rf(n + 16); H = sy * rf(n + 20);
            if (!fin(X) || !fin(Y) || !fin(W) || !fin(H))
                continue;
            if (!c[e].n || X < c[e].x0) c[e].x0 = X;
            if (!c[e].n || Y < c[e].y0) c[e].y0 = Y;
            if (!c[e].n || X + W > c[e].x1) c[e].x1 = X + W;
            if (!c[e].n || Y + H > c[e].y1) c[e].y1 = Y + H;
            c[e].obj[c[e].n++] = n;
        }
    }
    for (uint32_t e = 1; e < H_NEL; e++) {
        float r[4];
        const req *q = &s_req[e];
        if (!c[e].n)
            continue;
        r[0] = c[e].x0; r[1] = c[e].y0; r[2] = c[e].x1 - c[e].x0; r[3] = c[e].y1 - c[e].y0;
        words[e * 5] = 1;
        memcpy(&words[e * 5 + 1], r, sizeof r);
        if (expired(q))
            continue;
        {
            float cx = (c[e].x0 + c[e].x1) * 0.5f, cy = (c[e].y0 + c[e].y1) * 0.5f, k = q->t.scale;
            for (int i = 0; i < c[e].n; i++) {
                uint32_t n = c[e].obj[i], fr = r32(n + 0x40);
                float fx = rf(fr + 0x20), fy = rf(fr + 0x24), sx = rf(fr + 0x28), sy = rf(fr + 0x2C);
                float X = fx + sx * rf(n + 8), Y = fy + sy * rf(n + 12);
#if MUT == 6
                float X2 = cx + (X - cx) * k + q->t.dx, Y2 = cy + (Y - cy) * k + q->t.dy;   /* defect: no squeeze */
#else
                float X2 = cx + (X - cx) * k + qx * q->t.dx, Y2 = cy + (Y - cy) * k + qy * q->t.dy;
#endif
                if (!fin(sx) || !fin(sy) || fabsf(sx) < 1e-6f || fabsf(sy) < 1e-6f)
                    continue;
                wrf(n + 8, (X2 - fx) / sx);
                wrf(n + 12, (Y2 - fy) / sy);
                wrf(n + 16, rf(n + 16) * k);
                wrf(n + 20, rf(n + 20) * k);
#if MUT == 7
                wrf(n + 0x24, q->t.alpha);      /* defect: replaces the title's alpha */
#else
                wrf(n + 0x24, rf(n + 0x24) * q->t.alpha);
#endif
            }
        }
    }
#if BO3_HUD_IDPROBE
    id_probe(la, nl);
#endif
    s_nw_last = s_nw;
    publish(words);
}

void bo3_bm_hud_flip(void)
{
    t_game = 1;
#if MUT != 1
    if (s_nw)
        bo3_bm_hud_restore();               /* MUT 1: defect: nothing put back at the picture's end */
#endif
    s_pic++;
    for (uint32_t e = 1; e < H_NEL; e++)
        if (s_req[e].live && expired(&s_req[e]))
            s_req[e].live = 0, s_req[e].owner = NULL;
}

/* ---- the table ---- */
static int in_stage(void)
{
    return s_rendered && s_pic - s_render_pic <= 2u;
}

static int32_t check_common(td_host *host, uint32_t player, uint32_t element)
{
    if (!host)
        return BM_HUD_BAD_ARG;
    if (element == 0 || element >= H_NEL)
        return BM_HUD_UNKNOWN_ELEMENT;
    if (player == 1)
        return BM_HUD_UNSUPPORTED;
    if (player != 0)
        return BM_HUD_BAD_ARG;
    if (k_el[element].how == HOW_NONE)
        return BM_HUD_UNAVAILABLE;
    return BM_HUD_OK;
}

static int32_t TD_CALL h_set(td_host *host, uint32_t player, uint32_t element, const bm_hud_transform *t)
{
    int32_t rc = check_common(host, player, element);
    req *r;
    if (rc != BM_HUD_OK)
        return rc;
    if (!t || t->struct_size < sizeof(bm_hud_transform))
        return BM_HUD_BAD_ARG;
#if MUT != 4
    if (!fin(t->dx) || !fin(t->dy) || !fin(t->scale) || !fin(t->alpha) || fabsf(t->dx) > BM_HUD_D_MAX ||
            fabsf(t->dy) > BM_HUD_D_MAX || t->scale < BM_HUD_SCALE_MIN || t->scale > BM_HUD_SCALE_MAX || t->alpha < 0.0f ||
            t->alpha > 1.0f)
        return BM_HUD_OUT_OF_RANGE;
#endif
    if (!t_game)
        return BM_HUD_WRONG_THREAD;
    if (!in_stage())
        return BM_HUD_NOT_IN_STAGE;
    r = &s_req[element];
#if MUT != 3
    if (!expired(r) && r->owner != (const void *)host)
        return BM_HUD_CONFLICT;
#endif
    r->owner = host;
    r->t = *t;
    r->t.struct_size = (uint32_t)sizeof r->t;
    r->pic = s_pic;
    r->live = 1;
    return BM_HUD_OK;
}

static int32_t TD_CALL h_release(td_host *host, uint32_t player, uint32_t element)
{
    int32_t rc = check_common(host, player, element);
    req *r;
    if (rc != BM_HUD_OK)
        return rc;
    if (!t_game)
        return BM_HUD_WRONG_THREAD;
    r = &s_req[element];
    if (expired(r) || r->owner != (const void *)host)
        return BM_HUD_NOT_OWNER;
    r->live = 0;
    r->owner = NULL;
    return BM_HUD_OK;
}

static int32_t TD_CALL h_rect(td_host *host, uint32_t player, uint32_t element, float rect[4])
{
    uint32_t w[5], a, b;
    int32_t rc = check_common(host, player, element);
    if (rc != BM_HUD_OK)
        return rc;
    if (!rect)
        return BM_HUD_BAD_ARG;
    do {
        a = atomic_load_explicit(&s_seq, memory_order_acquire);
        for (int k = 0; k < 5; k++)
            w[k] = atomic_load_explicit(&s_rw[element * 5 + k], memory_order_relaxed);
        atomic_thread_fence(memory_order_acquire);
        b = atomic_load_explicit(&s_seq, memory_order_relaxed);
    } while ((a & 1u) || a != b);
    if (!w[0])
        return BM_HUD_NOT_SHOWN;
    memcpy(rect, &w[1], 4 * sizeof(float));
    return BM_HUD_OK;
}

static uint32_t TD_CALL h_avail(td_host *host, uint32_t element)
{
    (void)host;
    return element > 0 && element < H_NEL && k_el[element].how != HOW_NONE;
}

/* main19 (version 2): forwarded to bm_hudv2.c */
void bo3_bm_hud_render(void)
{
    s_hud_drawn = 0;
    hud_render();
    if (s_v2 && s_v2->pass)
        s_v2->pass(s_hud_drawn);
}

static int32_t TD_CALL h_draw(td_host *host, uint32_t player, const bm_hud_cmd *cmd)
{
    if (!host || !cmd)
        return BM_HUD_BAD_ARG;
    return s_v2 && s_v2->draw ? s_v2->draw(host, player, cmd) : BM_HUD_UNAVAILABLE;
}

static int32_t TD_CALL h_texture_info(td_host *host, const char *texture, uint32_t *w, uint32_t *h)
{
    if (!host || !texture || !w || !h)
        return BM_HUD_BAD_ARG;
    return s_v2 && s_v2->texture_info ? s_v2->texture_info(host, texture, w, h) : BM_HUD_UNAVAILABLE;
}

static uint32_t TD_CALL h_draw_available(td_host *host)
{
    (void)host;
    return s_v2 && s_v2->draw_available ? s_v2->draw_available() : 0u;
}

static const bm_hud_api s_api = { (uint32_t)sizeof(bm_hud_api), BM_HUD_VERSION, h_set, h_release, h_rect, h_avail,
                                  h_draw, h_texture_info, h_draw_available };

void bo3_bm_hud_set_v2(const bo3_hud_v2_ops *ops)
{
    s_v2 = ops;
}

const bm_hud_api *bo3_bm_hud_api(void) { return &s_api; }
uint32_t bo3_bm_hud_pictures(void) { return s_pic; }
uint32_t bo3_bm_hud_writes(void) { return (uint32_t)s_nw_last; }

void bo3_bm_hud_reset(void)
{
    uint32_t z[RECT_WORDS];
    memset(s_req, 0, sizeof s_req);
    s_pic = s_render_pic = 0;
    s_rendered = 0;
    s_nw = s_nw_last = 0;
    memset(z, 0, sizeof z);
    publish(z);
}

void bo3_bm_hud_init(void)
{
    bo3_bm_hud_reset();
    bo3_plugins_service(BM_HUD_SERVICE, BM_HUD_VERSION, &s_api);
}
