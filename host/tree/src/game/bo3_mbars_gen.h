/* main19 (hook request P3 D3, item 47): the mark of bmashup.menu's car-select stat bars, force-included into the generated sources
 * (BO3_GEN_OPT via scripts\GEN_EXTRA_F.txt). ITEM 57: the insertion is now at the exit loc_000F76FF of sub_000F6DC0 (recomp_0002.c),
 * the render callback of the front end's generic text elements (sub_000F68E0 builds them; the dialog's texts are such elements),
 * before `pop edi`; the original site below (item 47) drew nothing on screen in round 4. Item 47's site: sub_000B6F90 (a front-end 2D render callback, installed as object + 0x3C
 * by sub_000B6ED0; it draws with the rect primitive sub_001C7430; recomp_0001.c), wrapped in #if BO3_HOOKREQ_P23: at its one exit
 * loc_000B798F, before `pop edi` (twice: the generated sub_000B71B0 is a second entry into the same retail code and carries its
 * own copy of that exit):
 *     BO3_MENU_BARS_DRAW();
 * = the declared bars drawn with bmashup.hud v2's executor (bm_hudv2.c bo3_hudx_draw_cmds), at most once a picture, only while
 * the front end's current page is the car select (0x559648) in its input phase. The site is the best candidate found offline
 * (owner decision 2026-10-28: validated by a car-select screenshot in the next launch); BM_P23_MENU_BARS_SITE 0 = off. */
#ifndef BO3_MBARS_GEN_H
#define BO3_MBARS_GEN_H

void bo3_menu_gen_bars_draw(void);

/* main21 patch 87 (open-list item 8): BO3_HOOKREQ_P12B ON = the bars are drawn from the sub_000F6DC0 exit (main19 item 57's site,
 * proven to run on the car select in phase 5 by the DEV probe m19_bp1) and item 47's old site (sub_000B6F90, recomp_0001.c, kept
 * byte-identical) does nothing, so it cannot use up a picture's one draw; OFF = main20's state (the old site, BARS_SITE 0). */
#ifndef BO3_HOOKREQ_P12B
#define BO3_HOOKREQ_P12B 0
#endif
#if BO3_HOOKREQ_P12B
#define BO3_MENU_BARS_DRAW() ((void)0)
#define BO3_MENU_BARS_DRAW_FE() bo3_menu_gen_bars_draw()
#else
#define BO3_MENU_BARS_DRAW() bo3_menu_gen_bars_draw()
#endif

/* main21 patch 114 (probe R27): the Single Event SELECT MODE page never reaches the sub_000F6DC0 exit (C1 [DIAG]; its set-up builds
 * no generic text element). Its rows are list-widget lines, rendered by sub_000F29B0 (installed per line by sub_000F1160). At both
 * exits of sub_000F29B0 (loc_000F2CB8 after the last sprite call, loc_000F2E5A), before `pop edi`, wrapped in
 * #if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZHL (recomp_0002.c):
 *     BO3_MENU_HELP_DRAW_LL();
 * = bm_menu.c's mode-row help only (page 0x5595A4, phase 5, an added row, once a picture; never the car-select bars).
 * BO3_HOOKREQ_ZHL = BO3_HOOKREQ_P13H (the help switch; no CMake option of its own), Z-named so the earlier patches' gen-mark checks
 * treat these marks as a later patch's. */
#ifndef BO3_HOOKREQ_ZHL
#if defined(BO3_HOOKREQ_P13H) && BO3_HOOKREQ_P13H
#define BO3_HOOKREQ_ZHL 1
#else
#define BO3_HOOKREQ_ZHL 0
#endif
#endif
void bo3_menu_gen_help_draw(void);
#define BO3_MENU_HELP_DRAW_LL() bo3_menu_gen_help_draw()

#endif
