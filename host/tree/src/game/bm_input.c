/*
 * bm_input.c - main18 (platform 0.1.8, hook request P1 "input v1"): "bmashup.input" (include/bmashup_input.h), a
 * read-only per-frame pad snapshot. Design gp\hookreq\HOOK_REQUEST_DESIGN.md s1 I (pad), rules R0-R6.
 *
 * Where: the title polls its four pad records (0x4AE20C, 0x20 each: state, handle, XINPUT_STATE) once a frame in
 * sub_001B57E0; controls.c's "ctl_pad" mark runs right after each port's XInputGetState, and after input.control_scheme
 * rewrote the state, it hands the bytes the title will read to bo3_bm_input_note. So a snapshot is what the title got for
 * the frame, made once per frame and port, identical for every plugin that asks before the next read. Nothing is written.
 * Pad numbering (bmashup_input.h): service pad k = title port (k + 2) & 3 (the host's pads sit on the title's last two
 * ports, controls.c).
 * Owner: the overlay (the toolkit makes the title read neutral pads then) or a host page (MODS / MOD SETTINGS on the title's
 * Settings page, modsmenu.c) -> buttons / sticks / triggers reported as 0; a button held when the GAME gets the pad back
 * reads released until let go (a latch, as the toolkit's own after the overlay closes).
 * Context from the title's own words at the same instant (controls.c's evidence): module switch 0x4D53B4 (5 running, 0 before
 * the game object), the module's vtable (game 0x3A9ACC, front end 0x3A9E7C), the pausing player 0x4D537C.
 * MUT=n (tests) compiles one defect.
 */
#include "bm_input.h"

#include <string.h>

#include "bm_guest.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif

#define I_HELD 30u                          /* XBOX_ANALOG_BUTTON_THRESHOLD */

typedef struct {
    int seen;                               /* a read of this port happened */
    bm_input_pad snap;                      /* as reported */
    uint32_t raw_prev;                      /* the reported buttons of the previous read */
    uint32_t latch;                         /* held across a hand-back to the GAME: reads released until let go */
} port_state;

static port_state s_port[4];
static bo3_input_cfg s_cfg;
static RECOMP_TLS int t_game;

static uint32_t rd(uint32_t va)
{
    uint32_t v = 0;
    if (bo3_guest_window(va, 4) != BO3_GUEST_NONE)
        bo3_guest_read(va, &v, 4);
    return v;
}

static uint32_t context_now(void)
{
    uint32_t step = rd(BO3_INPUT_STEP), mod = rd(BO3_INPUT_MODULE), vt;
    if (step != 5 && step != 0)
        return BM_INPUT_CTX_LOADING;
    if (mod < 0x10000u || mod >= 0x04000000u)
        return 0;
    vt = rd(mod);
    if (vt == BO3_INPUT_VT_GAME)
        return rd(BO3_INPUT_PAUSED_BY) != 0xFFFFFFFFu ? BM_INPUT_CTX_PAUSE : BM_INPUT_CTX_RACE;
    if (vt == BO3_INPUT_VT_FE)
        return BM_INPUT_CTX_FRONT_END;
    return 0;
}

static float axis(int16_t v)
{
    float f = (float)v / 32767.0f;
    return f < -1.0f ? -1.0f : f > 1.0f ? 1.0f : f;
}

static uint32_t buttons_of(const uint8_t *g)
{
    uint16_t w = (uint16_t)(g[0] | g[1] << 8);
    const uint8_t *a = g + 2;
    uint32_t b = 0;
    static const uint32_t ab[8] = { BM_PAD_A, BM_PAD_B, BM_PAD_X, BM_PAD_Y, BM_PAD_BLACK, BM_PAD_WHITE, BM_PAD_LT, BM_PAD_RT };
    for (int i = 0; i < 8; i++)
        if (a[i] > I_HELD)
            b |= ab[i];
    if (w & 0x0001u) b |= BM_PAD_UP;
    if (w & 0x0002u) b |= BM_PAD_DOWN;
    if (w & 0x0004u) b |= BM_PAD_LEFT;
    if (w & 0x0008u) b |= BM_PAD_RIGHT;
    if (w & 0x0010u) b |= BM_PAD_START;
    if (w & 0x0020u) b |= BM_PAD_BACK;
    if (w & 0x0040u) b |= BM_PAD_LTHUMB;
    if (w & 0x0080u) b |= BM_PAD_RTHUMB;
    return b;
}

void bo3_bm_input_note(uint32_t title_port, const uint8_t *g)
{
    port_state *p;
    bm_input_pad s;
    uint32_t owner, raw, rep;

    t_game = 1;
    if (title_port > 3u)
        return;
    p = &s_port[(title_port + 2u) & 3u];        /* service pad = (title port + 2) & 3 */
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.frame = s_cfg.pictures ? s_cfg.pictures() : 0;
    s.context = context_now();
    owner = (s_cfg.overlay_open && s_cfg.overlay_open()) ? BM_INPUT_OVERLAY
          : (s_cfg.host_page && s_cfg.host_page()) ? BM_INPUT_HOST_PAGE : BM_INPUT_GAME;
    s.owner = owner;
    p->seen = 1;
    if (!g) {
        p->raw_prev = 0;
        p->latch = 0;
        p->snap = s;                            /* connected 0 */
        return;
    }
    s.connected = 1;
    raw = buttons_of(g);
#if MUT == 1
    owner = BM_INPUT_GAME;                      /* defect: no owner masking */
#endif
    if (owner != BM_INPUT_GAME) {
        p->latch = raw;                         /* everything held now stays released for the GAME until let go */
        rep = 0;
    } else {
#if MUT == 2
        p->latch = 0;                           /* defect: no latch: a held button is a press on the hand-back */
#endif
        p->latch &= raw;
        rep = raw & ~p->latch;
        s.lx = axis((int16_t)(g[10] | g[11] << 8));
        s.ly = axis((int16_t)(g[12] | g[13] << 8));
        s.rx = axis((int16_t)(g[14] | g[15] << 8));
        s.ry = axis((int16_t)(g[16] | g[17] << 8));
        s.lt = g[2 + 6] / 255.0f;
        s.rt = g[2 + 7] / 255.0f;
    }
    s.buttons = rep;
    if (owner != BM_INPUT_GAME) {               /* nothing went down or up for a plugin while the pad is not the game's */
        p->raw_prev = 0;
        p->snap = s;
        return;
    }
#if MUT == 3
    s.pressed = rep;                            /* defect: held reported as pressed every frame */
#else
    s.pressed = rep & ~p->raw_prev;
#endif
    s.released = p->raw_prev & ~rep;
    p->raw_prev = rep;
    p->snap = s;
}

static int32_t TD_CALL i_pad(td_host *host, uint32_t pad, bm_input_pad *out)
{
    bm_input_pad s;
    uint32_t room;
    if (!host || !out || out->struct_size < 8 || pad >= BM_INPUT_PADS)
        return BM_INPUT_BAD_ARG;
#if MUT != 4
    if (!t_game)
        return BM_INPUT_WRONG_THREAD;           /* MUT 4: defect: any thread */
#endif
    if (!s_port[pad].seen)
        return BM_INPUT_UNAVAILABLE;
    s = s_port[pad].snap;
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    s.struct_size = room;
    memcpy(out, &s, room);
    return s.connected ? BM_INPUT_OK : BM_INPUT_NO_PAD;
}

static const bm_input_api s_api = { (uint32_t)sizeof(bm_input_api), BM_INPUT_VERSION, i_pad };

const bm_input_api *bo3_bm_input_api(void) { return &s_api; }

void bo3_bm_input_configure(const bo3_input_cfg *cfg)
{
    if (cfg)
        s_cfg = *cfg;
    else
        memset(&s_cfg, 0, sizeof s_cfg);
}

void bo3_bm_input_reset(void)
{
    memset(s_port, 0, sizeof s_port);
    memset(&s_cfg, 0, sizeof s_cfg);
}

void bo3_bm_input_init(void)
{
    memset(s_port, 0, sizeof s_port);
    bo3_plugins_service(BM_INPUT_SERVICE, BM_INPUT_VERSION, &s_api);
}
