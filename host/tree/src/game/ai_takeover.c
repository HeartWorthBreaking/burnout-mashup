/*
 * ai_takeover.c - the title's takeover of a player car by its AI, as
 * RECOMP_DEBUG=autopilot has done it since BO-130 (autopilot.c says why each
 * step is there), moved here unchanged so that the private
 * "bmashup.autopilot" service (bm_autopilot.c) runs the same steps.
 */
#include "ai_takeover.h"

#include <stddef.h>

#include "recomp_types.h"

extern RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esi, g_esp;
extern ptrdiff_t g_xbox_mem_offset;
extern void sub_00179760(void);

#define AT_M8(va)  (*(uint8_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define AT_M32(va) (*(uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

void bo3_ai_takeover(uint32_t car)
{
    /* The title's takeover (sub_0018C510 at 0x18C688). The mark is on
     * the title's thread between two instructions: the registers the
     * call changes beyond its own work are put back. */
    uint32_t a = g_eax, c = g_ecx, d = g_edx, sp = g_esp;

    AT_M8(car + AP_CAR_AI) = 1;
    AT_M32(car + AP_CAR_AI_RESET + 0x0) = 0;
    AT_M32(car + AP_CAR_AI_RESET + 0x4) = 0;
    AT_M32(car + AP_CAR_AI_RESET + 0x8) = 0;
    AT_M32(car + AP_CAR_AI_RESET + 0xC) = 0;
    g_eax = car + AP_CAR_DRIVER;
    PUSH32(g_esp, 0);               /* the return address its ret takes */
    sub_00179760();
    g_eax = a; g_ecx = c; g_edx = d; g_esp = sp;
}

void bo3_ai_handback(uint32_t car)
{
    uint32_t phys = AT_M32(car + AP_CAR_PHYS);

    AT_M8(car + AP_CAR_AI) = 0;
    AT_M32(phys + AP_PHYS_BLEND) = AT_M32(AP_ONE);  /* movss: the float's bits */
    if (AT_M32(phys + AP_PHYS_MODE) == 4)
        AT_M32(phys + AP_PHYS_MODE) = 0;
}

void bo3_ai_stamp_pads(void)
{
    uint32_t k;
    for (k = 0; k < 4; k++)
        AT_M32(AP_CTLS + k * AP_CTL_SIZE + AP_CTL_ACTIVE) = AT_M32(AP_NOW);
}
