/* main19 (hook request P2 B2, item 44): the mark of bm_hudv2.c's draw-list executor, force-included into the generated sources
 * (BO3_GEN_OPT via scripts\\GEN_EXTRA_B.txt). Insertion in sub_0004AE40 (the boost bar's HUD render callback; recomp_0000.c), wrapped
 * in #if BO3_HOOKREQ_P23: after the call of sub_001C82E0 (the bar's last render-state call, 0x4B1B4), before the label
 * loc_0004B1B9 (so only the callback's full draw path reaches it, not its early exits to that label):
 *     BO3_HUDX_DRAW();
 * = this picture's plugin draw list submitted with the title's rect primitive sub_001C7430 inside the title's HUD pass (probe PR-F:
 * the retail call shape of 0x4B00E). Once a picture. */
#ifndef BO3_HUDX_GEN_H
#define BO3_HUDX_GEN_H

void bo3_hudx_gen_draw(void);

#define BO3_HUDX_DRAW() bo3_hudx_gen_draw()

#endif
