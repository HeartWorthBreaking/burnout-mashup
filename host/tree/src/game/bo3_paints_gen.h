/* bo3_paints_gen.h - gp slice paints1: the one call the generated code makes for the garage paint cap (bm_paints.c), in
 * sub_000BE140 (paint button: (paint + 1) mod min(model palettes, CAP)) and sub_000BE1B0 (photo mirror: paint mod
 * min(photo palettes, CAP)). Retail CAP = the constant 6. Included into every generated file through BO3_GEN_OPT (-include). */
#ifndef BO3_PAINTS_GEN_H
#define BO3_PAINTS_GEN_H
#include <stdint.h>
/* retail: the game's constant (6); photo_va: the selected row's garage photo texture (Frontend.txd entry, guest VA).
 * Returns the cap the game then min()s with its own palette count: min(configured cap, photo palette count), never below 1;
 * the retail constant when the photo cannot be read. */
uint32_t bo3_paint_gen_cap(uint32_t retail, uint32_t photo_va);
#endif
