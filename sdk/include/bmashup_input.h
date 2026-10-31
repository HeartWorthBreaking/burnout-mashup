/*
 * bmashup_input.h - the "bmashup.input" service (platform 0.1.8, hook request P1 item "input v1"): Burnout Mashup's
 * private, experimental READ-ONLY pad snapshot (Burnout Mashup builds only; may change or go away). Design:
 * gp\hookreq\HOOK_REQUEST_DESIGN.md capability I (pad); draft gp\hookreq\drafts\bmashup_input.h.
 *
 * Source: the title reads its pads once a frame (its pad manager's poll); the host takes the snapshot right after that
 * read, with the host's own mapping applied (SDL / keyboard map, face layout, the PS2 driving layout of
 * input.control_scheme) - i.e. exactly what the TITLE received for that frame. Nothing is injected (bmashup.autopilot is the
 * injecting service) and nothing is consumed: the title sees every press as before.
 *
 * Pads: `pad` 0 .. 3 is the HOST's pad order: pad 0 = the first host controller (the title's third port), pad 1 = the
 * second; pads 2 / 3 = the title's first two ports (normally empty on a PC). Which race player a pad drives is the title's
 * choice (the pad that pressed START); this service does not map pads to players.
 *
 * Rules:
 *   - pad() on the game's thread (an events / hooks callback, takedawn.race's update, a settings callback);
 *   - one snapshot per frame and pad: every plugin calling in the same frame gets identical values (frame = the host's
 *     picture count of the read);
 *   - owner: BM_INPUT_GAME (the title has the pad: race or its menus), BM_INPUT_HOST_PAGE (a host page drawn on the title's
 *     menu: MODS / MOD SETTINGS), BM_INPUT_OVERLAY (the toolkit overlay is open). While it is not GAME, buttons / pressed /
 *     released are 0 and the sticks and triggers read 0: a plugin must never act on a press a host page took. A button
 *     still held when the pad comes back to the GAME reads released until it is let go (no press the player did not make);
 *   - context (where the title is, read from its own state at the same instant): BM_INPUT_CTX_RACE (a stage runs),
 *     _PAUSE (a stage, paused), _FRONT_END (menus), _LOADING (a module is being switched), 0 = not known. _GARAGE is
 *     reserved: car select is reported as _FRONT_END in this version;
 *   - a pad with no controller: BM_INPUT_NO_PAD, out->connected = 0.
 * Combos the title already uses (pause, change view, ...) are not blocked; a mod documents its own combos.
 */
#ifndef BMASHUP_INPUT_H
#define BMASHUP_INPUT_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_INPUT_SERVICE "bmashup.input"
#define BM_INPUT_VERSION 1u
#define BM_INPUT_PADS    4u

enum { BM_INPUT_OK = 0, BM_INPUT_BAD_ARG = 1, BM_INPUT_NO_PAD = 2, BM_INPUT_WRONG_THREAD = 3, BM_INPUT_UNAVAILABLE = 4 };
enum { BM_INPUT_GAME = 1, BM_INPUT_HOST_PAGE = 2, BM_INPUT_OVERLAY = 3 };
enum { BM_INPUT_CTX_RACE = 1, BM_INPUT_CTX_PAUSE = 2, BM_INPUT_CTX_GARAGE = 3, BM_INPUT_CTX_FRONT_END = 4,
       BM_INPUT_CTX_LOADING = 5 };

/* Buttons (Xbox names; the host's PS2 scheme maps onto these). An analog button counts as held above 30 of 255. */
#define BM_PAD_A      0x0001u
#define BM_PAD_B      0x0002u
#define BM_PAD_X      0x0004u
#define BM_PAD_Y      0x0008u
#define BM_PAD_BLACK  0x0010u
#define BM_PAD_WHITE  0x0020u
#define BM_PAD_START  0x0040u
#define BM_PAD_BACK   0x0080u
#define BM_PAD_LTHUMB 0x0100u      /* L3 */
#define BM_PAD_RTHUMB 0x0200u      /* R3 */
#define BM_PAD_UP     0x0400u
#define BM_PAD_DOWN   0x0800u
#define BM_PAD_LEFT   0x1000u
#define BM_PAD_RIGHT  0x2000u
#define BM_PAD_LT     0x4000u      /* left trigger held */
#define BM_PAD_RT     0x8000u      /* right trigger held */

typedef struct bm_input_pad {
    uint32_t struct_size;           /* in: the size you have; out: the size filled in */
    uint32_t connected;
    uint32_t owner;                 /* BM_INPUT_* */
    uint32_t context;               /* BM_INPUT_CTX_*, 0 not known */
    uint32_t frame;                 /* the host's picture count at this snapshot */
    uint32_t buttons, pressed, released;    /* held / went down / went up this frame (0 unless owner = GAME) */
    float    lx, ly, rx, ry;        /* -1 .. 1 (y up) */
    float    lt, rt;                /* 0 .. 1 */
} bm_input_pad;

typedef struct bm_input_api {
    uint32_t struct_size;
    uint32_t version;               /* BM_INPUT_VERSION */
    int32_t (TD_CALL *pad)(td_host *host, uint32_t pad, bm_input_pad *out);
} bm_input_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_INPUT_H */
