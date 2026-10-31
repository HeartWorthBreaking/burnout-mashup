/*
 * bmashup_hud.h - the "bmashup.hud" service (platform 0.1.8, hook request P1 item "hud v1"): Burnout Mashup's private,
 * experimental per-picture TRANSFORMS of named retail HUD elements (Burnout Mashup builds only; may change or go away).
 * Design: gp\hookreq\HOOK_REQUEST_DESIGN.md capability B (B1); draft gp\hookreq\drafts\bmashup_hud.h.
 *
 * What it does: a plugin asks that a named HUD element of player 0's race HUD be drawn moved (dx, dy), scaled and / or
 * faded. The host applies it to the element's objects in guest memory just before the title draws the HUD scenes (the
 * "uw_stage_render" mark) and puts the title's values back when the picture ends ("uw_flip"), unless the title wrote them
 * in between (the display.score_board pattern, scoreboard.c). The title's own update therefore never sees a host value,
 * and nothing outlives the picture: a request lasts BM_HUD_TTL_PICTURES pictures unless the plugin asks again.
 *
 * Elements are named; no guest address, object or frame is ever handed out. The host tells an element by the render
 * callback its objects carry in the HUD scenes (a code address the plugin never sees) or by its component's frame:
 *   BM_HUD_BOOST_BAR       available: objects made by the boost bar's build (callback set only in sub_00048800)
 *   BM_HUD_BOOST_MESSAGE   available: AIR / ONCOMING / DRIFT / NEAR MISS / TAILGATING (callback set only in sub_0004B1C0)
 *   BM_HUD_SCORE_BOARD     available: the score board's frame (the component sub_00056DB0 sets up, as display.score_board)
 *   BM_HUD_AWARD           available: the award texts in the middle (callback set by sub_0005AA60; icons not included)
 *   BM_HUD_POSITION, BM_HUD_LAP, BM_HUD_SPEED, BM_HUD_TAKEDOWNS, BM_HUD_CENTRE_MESSAGE
 *                          UNAVAILABLE in this build: their objects share render callbacks with other elements (plates and
 *                          digits of POS / LAP / the takedowns counter / the score board; speed digits and the sliding centre
 *                          message) and their frames are not identified yet. They answer BM_HUD_UNAVAILABLE; a later version
 *                          enables them without a table change (element_available() says which are served).
 *   main21 patch 108 (Burnout Mashup hosts built with BO3_HOOKREQ_ZHUD, the default): BM_HUD_POSITION, BM_HUD_LAP,
 *                          BM_HUD_SPEED and BM_HUD_TAKEDOWNS are available - each by its own component's frame (probe R14 +
 *                          statics), counted only while 1..8 plates / digits / texts are drawn on it; BM_HUD_CENTRE_MESSAGE
 *                          stays UNAVAILABLE (not identified). No version change: element_available() answers 1 for them.
 *   main21 patch 119 (same switch): BM_HUD_CENTRE_MESSAGE is available - the score board's sliding message slot (gap to the car
 *                          ahead, laps, distance ...) by the slot's own frame, shown only while the slot holds a message
 *                          (else BM_HUD_NOT_SHOWN). Messages drawn as award texts in that slot now belong to CENTRE_MESSAGE, not
 *                          BM_HUD_AWARD. The countdown / GO is drawn outside the HUD scenes and is not part of any element.
 *
 * The transform (all values finite; an invalid request is refused, never clamped):
 *   dx, dy   HUD units, |d| <= 64 (the title's 640 x 480 layout). Applied in the element's own frame BEFORE the widescreen
 *            squeeze of display.hud_fix: 10 units move the element as far as 10 columns of the 4:3 layout would, and the
 *            squeeze then applies to the result like to every HUD object.
 *   scale    0.5 .. 2.0, about the centre of the element's drawn box (all its objects together).
 *   alpha    0 .. 1, multiplies the title's alpha (and display.score_board's, which is applied first).
 *
 * Rules:
 *   - player 0 only: player 1 (split screen) answers BM_HUD_UNSUPPORTED until split screen is tested (design rule R6);
 *   - one owner per (element, player): another plugin gets BM_HUD_CONFLICT. The ownership lasts while the plugin's request
 *     is live (it asks again at least once every BM_HUD_TTL_PICTURES pictures) or until release(); an expired request frees
 *     the element;
 *   - set_transform / release on the game's thread (an events / hooks callback, takedawn.race's update) during a stage (a
 *     race / event is drawing): BM_HUD_WRONG_THREAD / BM_HUD_NOT_IN_STAGE otherwise;
 *   - nothing is drawn by the host: while the title hides its HUD (crash / takedown cameras) nothing is written either;
 *   - element_rect: any thread; the element's box as the title laid it out in the last picture (640 x 480 columns of the
 *     picture, after the squeeze, before this service's transform).
 *
 * Version 2 (platform 0.1.9, hook request P2 B2; append-only, v1 unchanged): a per-picture DRAW LIST for player 0's race HUD.
 *   draw() is taken only inside a bmashup.hooks v3 HUD_PASS callback (NOT_IN_PASS otherwise). Commands: a solid QUAD, a
 *   textured SPRITE (a texture by name from the mod's declared HUD textures) and TEXT in the title's font, in 640 x 480 HUD
 *   units, drawn after the title's HUD scenes and only when the title draws its HUD; the list is cleared every picture.
 *   Bounds: <= BM_HUD_CMDS_PER_PLUGIN a plugin and BM_HUD_CMDS_PER_PICTURE a picture (FULL); coordinates -64 .. 704 x
 *   -64 .. 544, size 0 .. 768; rotation finite, |r| <= 2 pi; text <= 63 characters of the title's font (upper case, digits,
 *   space, . , : ! ? - + / % ' "), size 8 .. 64.
 *   PLATFORM 0.1.9: the list is drawn with the title's own rect primitive inside its HUD pass (at the boost bar's draw; a
 *   picture without the boost bar draws no list); QUAD / SPRITE axis-aligned only (rotation must be 0, else
 *   BM_HUD_UNSUPPORTED). QUAD = a solid colour. TEXT = the host's own 5 x 7 dot font (the characters above; advance 6 / 7 of
 *   text_size), <= BM_HUD_GLYPHS_PER_PICTURE glyphs a picture (FULL). SPRITE textures: an entry of a TXD a mod declares with
 *   [bmashup.textures] (the front-end texture table): `texture` = "<entry name>" of the plugin's own mod or
 *   "<mod-id>/<entry name>"; P8 entries only (DXT answers BM_HUD_UNSUPPORTED); an unknown name, or the pool before the front
 *   end first ran, answers BM_HUD_UNKNOWN_TEXTURE. The limits are that table's (bm_fetex: 256 entries a mod, 1 MiB an entry,
 *   768 / 12 MiB in all). The [bmashup.hud] table of the design is NOT read (a mod declaring it is refused by the platform
 *   check). HUD_PASS (bmashup.hooks v3 point 8 / bmashup.events v7 event 8): once a picture while player 0's race HUD is
 *   drawn. draw_available() = 1 when this host draws the list.
 */
#ifndef BMASHUP_HUD_H
#define BMASHUP_HUD_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_HUD_SERVICE      "bmashup.hud"
#define BM_HUD_VERSION      2u              /* 1: transforms; 2 (platform 0.1.9): + the draw list (QUADs in 0.1.9) */
#define BM_HUD_VERSION_1    1u
#define BM_HUD_VERSION_2    2u
#define BM_HUD_TTL_PICTURES 4u              /* a request applies to at most this many pictures after it was made */
#define BM_HUD_D_MAX        64.0f
#define BM_HUD_SCALE_MIN    0.5f
#define BM_HUD_SCALE_MAX    2.0f
/* version 2: the draw list */
#define BM_HUD_CMDS_PER_PLUGIN   64u
#define BM_HUD_CMDS_PER_PICTURE  256u
#define BM_HUD_TEXT_MAX          63u
#define BM_HUD_TEXTURES_PER_MOD  16u
#define BM_HUD_TEXTURE_MAX_BYTES (256u * 1024u)
#define BM_HUD_TEXTURE_BUDGET    (16u * 1024u * 1024u)   /* design value; 0.1.9 uses [bmashup.textures]' limits (see above) */
#define BM_HUD_GLYPHS_PER_PICTURE 1024u                  /* TEXT glyphs (non-space characters) a picture */

/* Results. 9 .. 12 are reserved for version 2 (NOT_IN_PASS, FULL, UNKNOWN_TEXTURE, BAD_TEXT). */
enum {
    BM_HUD_OK              = 0,
    BM_HUD_BAD_ARG         = 1,     /* no host, no transform / rect, struct_size too small */
    BM_HUD_OUT_OF_RANGE    = 2,     /* a value outside its bounds or not finite */
    BM_HUD_CONFLICT        = 3,     /* another plugin owns the element */
    BM_HUD_NOT_OWNER       = 4,     /* release of an element this plugin does not own */
    BM_HUD_UNKNOWN_ELEMENT = 5,     /* not a BM_HUD_* element */
    BM_HUD_NOT_IN_STAGE    = 6,     /* no race / event is drawing (front end, loading) */
    BM_HUD_WRONG_THREAD    = 7,
    BM_HUD_UNAVAILABLE     = 8,     /* the element is not served by this build (see above), or the host is not running */
    BM_HUD_UNSUPPORTED     = 13,    /* player 1 (split screen untested) */
    BM_HUD_NOT_SHOWN       = 14,    /* element_rect: the element was not drawn in the last picture */
    /* version 2 */
    BM_HUD_NOT_IN_PASS     = 9,     /* draw() outside a HUD_PASS callback */
    BM_HUD_FULL            = 10,    /* the plugin's or the picture's command limit */
    BM_HUD_UNKNOWN_TEXTURE = 11,    /* not one of the mod's loaded HUD textures */
    BM_HUD_BAD_TEXT        = 12,    /* too long, or a character the title's font has not */
    BM_HUD_NO_MEMORY       = 15     /* a HUD texture did not fit its budget (at load) */
};
enum { BM_HUD_CMD_QUAD = 1, BM_HUD_CMD_SPRITE = 2, BM_HUD_CMD_TEXT = 3 };   /* version 2 */

enum {                              /* named elements; more are appended as they are identified */
    BM_HUD_BOOST_BAR = 1, BM_HUD_BOOST_MESSAGE = 2, BM_HUD_POSITION = 3, BM_HUD_LAP = 4, BM_HUD_SPEED = 5,
    BM_HUD_TAKEDOWNS = 6, BM_HUD_SCORE_BOARD = 7, BM_HUD_AWARD = 8, BM_HUD_CENTRE_MESSAGE = 9,
    BM_HUD_ELEMENTS = 9             /* the highest element of this version */
};

typedef struct bm_hud_transform {
    uint32_t struct_size;           /* sizeof (bm_hud_transform): 20 in version 1 */
    float dx, dy;                   /* HUD units, |d| <= BM_HUD_D_MAX */
    float scale;                    /* BM_HUD_SCALE_MIN .. BM_HUD_SCALE_MAX, about the element's centre */
    float alpha;                    /* 0 .. 1, multiplies the title's alpha */
} bm_hud_transform;

/* version 2: one draw command (copied at draw(): the pointers need to live for the call only) */
typedef struct bm_hud_cmd {
    uint32_t struct_size;           /* sizeof (bm_hud_cmd) */
    uint32_t kind;                  /* BM_HUD_CMD_* */
    float x, y, w, h;               /* HUD units, top-left; TEXT: x, y = the text's top-left, w / h ignored */
    float u0, v0, u1, v1;           /* SPRITE: 0 .. 1 */
    float rotation_rad;             /* QUAD / SPRITE about the centre */
    uint32_t rgba;                  /* 0xRRGGBBAA tint / colour */
    const char *texture;            /* SPRITE: "<entry>" (own mod) or "<mod-id>/<entry>" of a [bmashup.textures] TXD (P8) */
    const char *text;               /* TEXT */
    float text_size;                /* TEXT: 8 .. 64 (HUD units, cap height) */
} bm_hud_cmd;

typedef struct bm_hud_api {
    uint32_t struct_size;
    uint32_t version;               /* BM_HUD_VERSION */
    /* Ask for (or renew) the element's transform from the next picture on. Game thread, during a stage. */
    int32_t (TD_CALL *set_transform)(td_host *host, uint32_t player, uint32_t element, const bm_hud_transform *t);
    /* Give the element back now (the title's values from the next picture). Game thread. */
    int32_t (TD_CALL *release)(td_host *host, uint32_t player, uint32_t element);
    /* rect = { x, y, w, h } of the element as drawn in the last picture (see above). Any thread. */
    int32_t (TD_CALL *element_rect)(td_host *host, uint32_t player, uint32_t element, float rect[4]);
    /* 1 when this build serves the element (it may still be absent from a given picture), else 0. Any thread. */
    uint32_t (TD_CALL *element_available)(td_host *host, uint32_t element);
    /* ---- version 2 ---- */
    /* One command into this picture's list: inside a HUD_PASS callback only, player 0. */
    int32_t (TD_CALL *draw)(td_host *host, uint32_t player, const bm_hud_cmd *cmd);
    /* A SPRITE texture's size (the names above). Any thread. */
    int32_t (TD_CALL *texture_info)(td_host *host, const char *texture, uint32_t *w, uint32_t *h);
    /* 1 when this host draws the list. Any thread. */
    uint32_t (TD_CALL *draw_available)(td_host *host);
} bm_hud_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_HUD_H */
