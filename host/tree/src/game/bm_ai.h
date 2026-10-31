/* bm_ai.h - gp slice ai1 EXPERIMENTAL: "bmashup.ai" (include/bmashup_ai.h), host side. The core works through a guest-access
 * interface (offline tests); the game build (BO3_AI_GAME) binds it to bm_guest.c. */
#ifndef BO3_BM_AI_H
#define BO3_BM_AI_H

#include <stdint.h>

#include "bmashup_ai.h"

/* fields (atlas AI.md s1-s2; recomp_0003.c sub_00170820 / sub_00171A10 / sub_00173690 / sub_00176150) */
#define BO3_AI_LIST_COUNT 0x0073A19Cu
#define BO3_AI_LIST       0x0073A1A8u
#define BO3_AI_PLAYER1    0x0073A1D0u      /* player objects: 0x73A1D0, + 0x27E0 */
#define BO3_AI_PLAYER_STRIDE 0x27E0u
#define BO3_AI_F          0x1A00u          /* controller F = R + 0x1A00 (sub_00170820: eax = esi + 0x1A00) */
#define BO3_AI_F_SELF     0x7A0u           /* F+0x7A0 -> R */
#define BO3_AI_F_TARGET   0x1D0u           /* F+0x1D0 target speed */
#define BO3_AI_F_SCHED    0xA04u           /* F+0xA04 schedule offset (s) */
#define BO3_AI_F_CAP      0xA08u           /* F+0xA08 speed cap (= R+0x2408) */
#define BO3_AI_R_CAR      0x2440u          /* [R+0x2440] physics car; speed +0xBC */
#define BO3_AI_CAR_SPEED  0xBCu
#define BO3_AI_R_COLUMN   0x10E4u          /* schedule column (s32; clamped 0..7 where used) */
#define BO3_AI_R_ZONE     0x245Cu          /* zone (s8) */

typedef struct bo3_ai_guest {
    int (*read)(void *user, uint32_t va, void *out, uint32_t n);
    int (*write)(void *user, uint32_t va, const void *in, uint32_t n);
    void *user;
} bo3_ai_guest;

void bo3_ai_configure(const bo3_ai_guest *g, int verified);
/* the mark: after sub_00173690 wrote F+0xA08 (sub_00171A10, esi = F) */
void bo3_ai_gen_cap(uint32_t f);
const bm_ai_api *bo3_bm_ai_api(void);
/* counters: 0 caps scaled, 1 players skipped, 2 inconsistent controllers skipped, 3 marks seen */
uint32_t bo3_ai_stat(uint32_t which);

#endif
