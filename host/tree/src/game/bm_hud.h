/* bm_hud.h - main18 (platform 0.1.8, hook request P1): "bmashup.hud" v1 (include/bmashup_hud.h), the host side.
 * main.c calls, on the title's thread:
 *   uw_stage_render: bo3_bm_hud_restore(); bo3_score_board_render(); bo3_bm_hud_render();
 *   uw_flip:         bo3_bm_hud_flip(); ... bo3_score_board_flip();
 * so this service's writes are put back before display.score_board's (it writes first, this one multiplies on top). */
#ifndef BO3_BM_HUD_H
#define BO3_BM_HUD_H

#include <stdint.h>

#include "bmashup_hud.h"

/* guest layout (scoreboard.c / docs/widescreen-hud.md / sub_001C6500 / sub_001C1670 / sub_001C17A0) */
#define BO3_HUD_MANAGER   0x0054F900u   /* the HUD object; scenes at + 0x14 + 0x70 p, players at + 0x170 */
#define BO3_HUD_ON        0x004D61D3u   /* byte: sub_000536C0 draws the HUD scenes */
#define BO3_HUD_BOARD_P0  0x003FDC00u   /* the score board component of player 1 (sub_00056DB0's esi); its frame at + 8 */
#define BO3_HUD_CB_BOOST  0x0004AE40u   /* stored only by sub_00048800 (the boost bar's build) */
#define BO3_HUD_CB_BMSG   0x0004B4D0u   /* stored only by sub_0004B1C0 (the boost messages) */
#define BO3_HUD_CB_AWARD  0x0005AC20u   /* HUD use: sub_0005AA60 (award texts); front-end users are other scenes */
#define BO3_HUD_CB_PLATE  0x00048430u   /* plates: POS / LAP / takedowns / score board (shared: not an element alone) */
#define BO3_HUD_CB_DIGITS 0x000F6DC0u   /* POS / LAP digits, score board texts (shared) */
/* main21 patch 108 (open item 3, probe R14 + statics): player 1's race HUD components, each with its frame at + 8 (the board's
 * layout); an element = the objects drawn on that frame (only plates / digits / texts, <= 8 objects) */
#define BO3_HUD_CB_TEXT   0x000F7C20u   /* texts: the speedometer and the centre message (shared) */
#define BO3_HUD_C_POS     0x003FD4A0u   /* POSITION (sub_00053ED0 loads text 2002 "POS") */
#define BO3_HUD_C_LAP     0x003FD4F8u   /* LAP (sub_00051650 loads text 2003 "LAP") */
#define BO3_HUD_C_SPEED   0x003FDD48u   /* SPEED (R14: 3 objects) */
#define BO3_HUD_C_TD      0x003FDE70u   /* TAKEDOWNS (R14: 3 objects) */
/* main21 patch 119 (batch C3-7): the centre message is the score board component's message slot (notes\C3_7_CENTRE_MESSAGE_RE.md,
 * FACT): sub_00057040 runs it at board + 0x2C (the message object = a list node + 8, 0 when none), its own frame M at board + 0x30
 * (sub_00056DB0 0x56FBC, a child of the board frame; sub_000583B0 rewrites M's local x / y / scale every update -> never written) */
#define BO3_HUD_CMSG_OBJ   0x003FDC2Cu
#define BO3_HUD_CMSG_FRAME 0x003FDC30u

void bo3_bm_hud_init(void);             /* registers the service (bo3_plugins_service) */
const bm_hud_api *bo3_bm_hud_api(void);
void bo3_bm_hud_restore(void);          /* put back what the last render wrote (if the title did not write it since) */
void bo3_bm_hud_render(void);           /* apply the live transforms to player 0's HUD scene */
void bo3_bm_hud_flip(void);             /* the picture ends: put back, count the picture */
/* main19 (version 2): bm_hudv2.c serves the v2 calls and HUD_PASS; its ops are registered at its init. Without them (a unit
 * test of this file, BO3_HOOKREQ_P23=0) draw / texture_info answer UNAVAILABLE, draw_available 0, and no HUD_PASS runs.
 * pass(hud_drawn) is called at the end of every bo3_bm_hud_render (hud_drawn = the title draws player 0's HUD scenes). */
typedef struct bo3_hud_v2_ops {
    int32_t (*draw)(td_host *host, uint32_t player, const bm_hud_cmd *cmd);
    int32_t (*texture_info)(td_host *host, const char *texture, uint32_t *w, uint32_t *h);
    uint32_t (*draw_available)(void);
    void (*pass)(int hud_drawn);
} bo3_hud_v2_ops;
void bo3_bm_hud_set_v2(const bo3_hud_v2_ops *ops);
void bo3_hudv2_init(void);              /* bm_hudv2.c: after bo3_bm_hud_init and bo3_bm_hooks_init */
/* tests / diagnostics */
uint32_t bo3_bm_hud_pictures(void);
uint32_t bo3_bm_hud_writes(void);       /* words written by the last render */
/* main21 patch 72: DEV-only builds with BO3_HUD_IDPROBE=1: the "[HUDID]" lines go to fn (default stderr) */
void bo3_bm_hud_idprobe_log(void (*fn)(const char *line));
void bo3_bm_hud_reset(void);            /* tests: forget everything */

#endif
