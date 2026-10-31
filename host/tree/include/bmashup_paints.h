/*
 * bmashup_paints.h - the "bmashup.paints" service (platform 0.1.9, hook request P2 item I "player car colour"): Burnout
 * Mashup's private, experimental RUN-TIME COLOUR of a human player's own car (Burnout Mashup builds only; may change or go
 * away). Design: gp\hookreq\HOOK_REQUEST_DESIGN.md capability I; final draft gp\hookreq\p23\drafts_p23\bmashup_paints.h.
 * It is the plugin face of the paint registry ([bmashup.paints] declarations): the same index rule (an index above the car's
 * retail palette count selects a host palette resource).
 *
 *   claim_dynamic(player) gives the plugin player 0's DYNAMIC paint: a host palette whose colours the plugin sets; the car
 *   shows it from its next draw in a race, until factory() (the paint the player chose) or release(). The host builds the
 *   palette from the car's own retail palettes in a host palette unit and edits it in place (platform 0.1.9 patch 41: the
 *   renderer shows an edited palette at once). The game save never holds the dynamic paint.
 *   Layers: BODY = the palette entries that differ between the car's retail palettes 0 and 1 (the registry's ramp rule),
 *   recoloured by their brightness between a dark shade of the colour and the colour (alpha kept). DECALS / WHEELS are
 *   declared but answer NO_LAYER in platform 0.1.9 (no verified per-car layer tables yet); NITRO is reserved (the Xbox reader
 *   of the boost-flame colour is not located): NO_LAYER. status().layers says what the current car offers.
 *   main21 (patch 73): DECALS works on the 49 retail cars with a generated table (bm_paints_decals.h, from the car files: the
 *   coloured non-paint palette entries of the body half of the texture), recoloured with the same brightness rule; the car is
 *   recognised by its palette 0, so other / modified cars answer NO_LAYER. Ask for DECALS once status().layers shows it (it is
 *   known after the car's dynamic palette is first built). factory() / release() drop the decal colour.
 *   main21 (patch 74): WHEELS works on the 55 retail cars with a generated wheel table (the palette entries of the wheel lists'
 *   texels at least 48 / 255 bright on palette 0; darker = the tyre, kept): on Xbox the wheels share palette entries with the
 *   rest of the car, so the host binds a second palette (the car's dynamic one with those entries recoloured) only while the
 *   car model draw draws the wheels - shared entries change colour on the wheels only. Player 0's car only; offered like
 *   DECALS (status().layers); factory() / release() drop it. A host built with BO3_HOOKREQ_P6W=OFF never offers it, nor does
 *   a build whose wheel-loop sites failed their census.
 *   main21 (patch 75): NITRO = a TINT of the car's boost flame (corona sprites drawn with the car's own flame texture, blue on
 *   most cars, red / orange on some): the host replaces the flame colour with the plugin colour at the game's brightness, so a
 *   blue-flame car can be shifted / darkened but not turned red. Every car with player 0; offered once the car's palette is
 *   built (status().layers); factory() / release() drop it. BO3_HOOKREQ_P6W / P6N=OFF hosts never offer WHEELS / NITRO.
 *   main21 (patch 76): set_colour(NITRO, rgb | BM_PAINTS_NITRO_GLOW) draws player 0's flame with the game's neutral glow sprite
 *   (coronaglow) instead of the car's flame texture: any colour, but a round glow rather than a flame shape (it shares the glow
 *   sprites' room with headlights / traffic; a full room drops sprites, as the game does). The flag is BAD_ARG on other layers.
 *   Rules: player 0 only (player 1 UNSUPPORTED: split screen is not validated); one owner per player (CONFLICT); colours
 *   0xRRGGBB; <= BM_PAINTS_UPDATES_PER_SECOND set_colour calls a second (RATE); AI and traffic never use the dynamic paint;
 *   race only in 0.1.9 (the garage / photo keep the chosen paint); palette memory lives in the guest high zone (256 MB window) -
 *   NO_MEMORY if it cannot be had; a car whose texture has no palette ramp (one palette): UNSUPPORTED (status().active 0).
 *   UNAVAILABLE: a host built with BO3_HOOKREQ_P23=OFF, or this build's sites failed the start census.
 *   Threads: claim_dynamic / set_colour / factory / release on the game thread (an events / hooks callback); status any.
 */
#ifndef BMASHUP_PAINTS_H
#define BMASHUP_PAINTS_H
#include "takedawn_plugin.h"
#ifdef __cplusplus
extern "C" {
#endif
#define BM_PAINTS_SERVICE "bmashup.paints"
#define BM_PAINTS_VERSION 1u
#define BM_PAINTS_UPDATES_PER_SECOND 30u
#define BM_PAINTS_NITRO_GLOW 0x01000000u   /* main21 patch 76: set_colour(NITRO) flag - the neutral glow sprite, any colour */

enum { BM_PAINTS_OK = 0, BM_PAINTS_BAD_ARG = 1, BM_PAINTS_CONFLICT = 2, BM_PAINTS_NOT_OWNER = 3, BM_PAINTS_NO_LAYER = 4,
       BM_PAINTS_RATE = 5, BM_PAINTS_UNSUPPORTED = 6, BM_PAINTS_NO_MEMORY = 7, BM_PAINTS_UNAVAILABLE = 8,
       BM_PAINTS_WRONG_THREAD = 9 };
enum { BM_PAINT_LAYER_BODY = 1, BM_PAINT_LAYER_DECALS = 2, BM_PAINT_LAYER_WHEELS = 3, BM_PAINT_LAYER_NITRO = 4 };

typedef struct bm_paints_status {
    uint32_t struct_size;
    uint32_t owned, yours;
    uint32_t active;                /* 1: the car shows the dynamic paint now */
    uint32_t layers;                /* bit (1 << layer) the current car offers */
    uint32_t published;             /* palette publications (process) */
    char     vehicle[16];           /* the car's file stem, "" when no car */
} bm_paints_status;                 /* 40 bytes */

typedef struct bm_paints_api {
    uint32_t struct_size;
    uint32_t version;
    int32_t (TD_CALL *claim_dynamic)(td_host *host, uint32_t player);                         /* game thread */
    int32_t (TD_CALL *set_colour)(td_host *host, uint32_t player, uint32_t layer, uint32_t rgb);  /* game thread */
    int32_t (TD_CALL *factory)(td_host *host, uint32_t player);    /* show the chosen paint; keeps ownership */
    int32_t (TD_CALL *release)(td_host *host, uint32_t player);
    int32_t (TD_CALL *status)(td_host *host, uint32_t player, bm_paints_status *out);         /* any thread */
} bm_paints_api;
#ifdef __cplusplus
}
#endif
#endif
