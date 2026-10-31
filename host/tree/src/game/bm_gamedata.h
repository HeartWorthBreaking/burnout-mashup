/* G8-L6a: the GAMEDATA loader guard (bm_gamedata.c). Host prerequisite; the generated loader calls it through
 * bo3_gamedata_gen.h. Guest offsets (recomp_0003.c, sub_0018B250 / sub_00018BB0; KB RESOURCE_LIMITS s2):
 *   loader +0x560 buffer (the slot's base), +0x564 event record, +0x568 header part 2 (= buffer + 0x800, :133115), +0x580
 *   variant index, +0x58B variant flag; per-variant S2 sizes at header part 2 + 0x2034 = file +0x2834
 *   descriptors 0x003FA004 (layout 1) / 0x003FA4C4 (layout 2), selected by [0x003FA644] == 2; +8 size, +0xC base */
#ifndef BM_GAMEDATA_H
#define BM_GAMEDATA_H

#include <stdint.h>
#include <stdio.h>

#define BO3_GD_LD_BUFFER  0x560u
#define BO3_GD_LD_RECORD  0x564u
#define BO3_GD_LD_HEADER  0x568u
#define BO3_GD_LD_VINDEX  0x580u
#define BO3_GD_LD_VARIANT 0x58Bu
#define BO3_GD_LAYOUT_VA  0x003FA644u
#define BO3_GD_DESC_L1    0x003FA004u
#define BO3_GD_DESC_L2    0x003FA4C4u
#define BO3_GD_FIXED      0x3800u       /* header 0x3000 + record 0x800 */
#define BO3_GD_SLOT_RETAIL 0x176000u

typedef const uint8_t *(*bo3_gd_guest_fn)(void *user, uint32_t va, uint32_t size);
typedef void (*bo3_gd_fail_fn)(void *user, uint64_t need, uint32_t slot, uint32_t base);

typedef struct bo3_gamedata {
    bo3_gd_guest_fn guest;
    bo3_gd_fail_fn fail;
    void *user;
    FILE *log;
    uint32_t checks, unchecked, failed;
    uint64_t last_need;
    uint32_t last_slot;
} bo3_gamedata;

extern bo3_gamedata g_bo3_gd;

void bo3_gd_configure(bo3_gamedata *g, bo3_gd_guest_fn guest, bo3_gd_fail_fn fail, void *user, FILE *log);
/* 1 and the need / slot / base when the loader state and the descriptor verify; 0 when they cannot be verified */
int bo3_gd_need(const bo3_gamedata *g, uint32_t loader, uint64_t *need, uint32_t *slot, uint32_t *base);
/* 1: the load may continue (fits, or not verifiable); 0: too large (the fail handler ran; the game's handler exits 88) */
int bo3_gd_check(bo3_gamedata *g, uint32_t loader);
void bo3_gd_game_init(void);

#endif
