/* main19 patch 45 (bmashup.menu v1 popup, hook request P3 D1): force-included into the generated sources (BO3_GEN_OPT, listed in
 * gp\slices\main19\scripts\GEN_EXTRA_G.txt). Two insertions in recomp_0001.c, each wrapped in #if BO3_HOOKREQ_P23:
 *   sub_00071AF0 at loc_00071AF0 (entry, before `push ebp`)  = the car-select page's (vt 0x3AC044) slot 0 input handler:
 *       if (BO3_MENU_PAGE_INPUT(0u)) { esp += 4; return; }
 *   sub_00072500 at loc_00072500 (entry, before `cmp [0x557A64], 5`) = the same page's slot 4 (also reads input):
 *       if (BO3_MENU_PAGE_INPUT(4u)) { esp += 4; return; }
 * Both handlers are thiscall (ECX = the page) with a plain `ret` (XBE 0x71F02 / 0x725F1), so `esp += 4; return;` at the entry is
 * the retail return: the page skips its input for this frame. Shape = p23probe v5d's PR-F mark (runtime p23_fa4 / p23_fb4).
 * The host function (bm_menu.c) answers 1 only while a host popup owns the pad (trigger frame, dialog up, A not yet released);
 * slot 0 also drives the dialog once a frame (open / poll with controller -1 / close). Every guest register is kept. */
#ifndef BO3_MENU_GEN_H
#define BO3_MENU_GEN_H

#include <stdint.h>

uint32_t bo3_menu_gen_page_input(uint32_t slot);

#define BO3_MENU_PAGE_INPUT(slot) bo3_menu_gen_page_input((uint32_t)(slot))

/* main19 patch 43 (bmashup.menu v1 mode rows, hook request P3 D2): three more insertions, each wrapped in #if BO3_HOOKREQ_P23:
 *   recomp_0001.c sub_000765E0 (the generic list-page set-up, EDI = the page) at loc_000766A4 (after the row loop, before the
 *       count / selection copies to the widget):            BO3_MENU_LIST_ROWS(edi);
 *   recomp_0001.c sub_00069E40 (the Single Event state handler) at loc_00069F5D (the accept dispatch, before it reads the row
 *       0x5595AC; rows >= 4 fall to the Race selector 0, XBE 0x69F6C):   BO3_MENU_SE_ACCEPT(MEM32(0x5595AC));
 *   recomp_0000.c sub_0005F4A0 (the Single Event race set-up, ESI = the settings 0x463AF0) at loc_0005F514 (the Race case) after
 *       after ECX is stored to guest address 0x4D467C:                          BO3_MENU_SE_ROUTE(esi);
 * The route's place and writes are p23probe's PR-E dev route (0x4D4788 = 0x4D4BD8 Eliminator logic, 0x4D467C = 5 laps; runs
 * p23_e1r / p23_e2r to the Eliminator results). The host functions read / write guest memory through bm_guest.c only. */
void bo3_menu_gen_list_rows(uint32_t page);
void bo3_menu_gen_se_accept(uint32_t row);
void bo3_menu_gen_se_route(uint32_t settings);

#define BO3_MENU_LIST_ROWS(page) bo3_menu_gen_list_rows((uint32_t)(page))
#define BO3_MENU_SE_ACCEPT(row) bo3_menu_gen_se_accept((uint32_t)(row))
#define BO3_MENU_SE_ROUTE(settings) bo3_menu_gen_se_route((uint32_t)(settings))

/* main21 C3-5 (open-list item 9, MP part): MULTIPLAYER mode rows, each wrapped in #if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZMPR:
 *   recomp_0001.c sub_0007A030 (the Multiplayer list set-up, EDI = the page) at loc_0007A0F4 (after the row loop):
 *       BO3_MENU_LIST_ROWS(edi);   (bo3_menu_gen_list_rows also serves the MP page 0x55C460 at its retail count 5)
 *   recomp_0001.c sub_0006C410 (the MP title's state handler) at loc_0006C54F (before `mov eax,[0x55C468]`; rows >= 5 fall to
 *       the Race selector 0x463AFC = 0, XBE 0x6C5C5):   BO3_MENU_MP_ACCEPT(MEM32(0x55C468));
 *   recomp_0000.c sub_0005F7B0 (the 2-player race set-up, ESI = the settings 0x463AF0) at loc_0005F846 (the Race case) right after
 *       after 0x4D4E54 is stored to guest address 0x4D4950:                    BO3_MENU_MP_ROUTE(esi);
 *   (the game's own rival count clamp / copy follow unchanged) */
#ifndef BO3_HOOKREQ_ZMPR
#define BO3_HOOKREQ_ZMPR 1
#endif
void bo3_menu_gen_mp_accept(uint32_t row);
void bo3_menu_gen_mp_route(uint32_t settings);
#define BO3_MENU_MP_ACCEPT(row) bo3_menu_gen_mp_accept((uint32_t)(row))
#define BO3_MENU_MP_ROUTE(settings) bo3_menu_gen_mp_route((uint32_t)(settings))

/* main21 patch 93 (open-list item 18): the pause menu's MOD SETTINGS row (bm_menu.c) */
void bo3_menu_gen_pause_row(uint32_t page);
void bo3_menu_gen_pause_accept(uint32_t action);
#endif
