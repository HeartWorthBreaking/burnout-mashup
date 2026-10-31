/* main19 item 23 (hook request P2 A3 / A4, bmashup.racers 3 controls): force-included into the generated sources (BO3_GEN_OPT,
 * scripts\GEN_EXTRA_A.txt). Insertion (main19 patch 23_racers_v3_detach_lights, recomp_0002.c):
 *   sub_0011BE50 (the physics car update; ECX = the physics vehicle V, thiscall, 0x11BE5D mov ebx,ecx) at loc_0011BE50,
 *   first statement:
 *       #if BO3_HOOKREQ_P23
 *       BO3_RACERS_CAR_MARK(ecx);
 *       #endif
 *   The host (bm_racers.c bo3_racers_gen_car) counts the calls (does the update run for AI cars each step: probe PR-A) and,
 *   only with BM_P23_RACERS_APPLY_PER_RACER = 1, carries out an AI racer's pending detach there (registers put back). */
#ifndef BO3_RACERS_GEN_H
#define BO3_RACERS_GEN_H

#include <stdint.h>

void bo3_racers_gen_car(uint32_t v);

#define BO3_RACERS_CAR_MARK(v) bo3_racers_gen_car((uint32_t)(v))

/* main21 patch 77 (light OFF): sub_0011BE50 loc_0011BFEF, right after the light-flag OR (p = the physics car, EBX) */
void bo3_racers_gen_light_off(uint32_t p);
#define BO3_RACERS_LIGHT_OFF_MARK(p) bo3_racers_gen_light_off((uint32_t)(p))

/* main21 patch 104 (tail stand-in): sub_00187C70 0x187D74, the running-tail draw (bit 0x08) after mov edx, 1 (e = the render
 * entity E, ESI; sp = ESP: [sp] colour, [sp + 4] vector, [sp + 8] scale): returns the lamp group to draw (1, or 2 = brake group) */
uint32_t bo3_racers_gen_tail(uint32_t e, uint32_t sp);
#define BO3_RACERS_TAIL_MARK(e, sp) bo3_racers_gen_tail((uint32_t)(e), (uint32_t)(sp))

#endif
