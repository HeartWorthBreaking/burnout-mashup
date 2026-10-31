/* main19 (platform 0.1.9, hook request P3 E1, patch 35): force-included into the generated sources (BO3_GEN_OPT, listed in
 * gp\slices\main19\scripts\GEN_EXTRA_C.txt). Insertion (patch 35, recomp_0000.c):
 *   sub_00024E30 (the Eliminator rules' per-lap callback, vtable 0x3A9D50 + 0x68) at loc_00024E92, before
 *   the load of ECX from the racer list 0x73A1A8 (index EAX, 4 bytes each) (the game's own "last racer of the lap is out" call to sub_00024F10 at 0x24E9C):
 *       #if BO3_HOOKREQ_P23
 *       if (BO3_RULES_LAP_SKIP(ebp, MEM32(eax * 4 + 0x73A1A8))) goto loc_00024EA1;   (patch 42: + the lap's last racer)
 *       #endif
 *   (ebp = the rules object; loc_00024EA1 is where the game's own "no single last racer" branch at 0x24E8D goes: the same
 *   stack state, nothing pushed yet.) bm_rules.c answers 1 only for a race a plugin claimed, when lap elimination is off or
 *   (patch 42, PR-E finding) the lap's last racer is already eliminated (the game would eliminate it again). */
#ifndef BO3_RULES_GEN_H
#define BO3_RULES_GEN_H

#include <stdint.h>

int bo3_rules_gen_lap_skip(uint32_t rules, uint32_t racer);

#define BO3_RULES_LAP_SKIP(rules, racer) bo3_rules_gen_lap_skip((uint32_t)(rules), (uint32_t)(racer))

/* main21 patch 80 (props in Road Rage): sub_00110420 loc_001108EC, EAX = the mode logic's vtable + 0xB0 answer */
uint32_t bo3_rules_gen_props(uint32_t rr);
#define BO3_RULES_PROPS(rr) bo3_rules_gen_props((uint32_t)(rr))

/* main21 patch 102 (props drawn in Road Rage): sub_001ACE00 loc_001ACE2E (recomp_0003.c), EAX = the same vtable + 0xB0 answer
 * at the prop draw (called every frame: no log per call) */
uint32_t bo3_rules_gen_props_draw(uint32_t rr);
#define BO3_RULES_PROPS_DRAW(rr) bo3_rules_gen_props_draw((uint32_t)(rr))

/* main21 patch 83 (End Session in the pause menu): sub_00085F70 loc_00086196, EAX = the mode logic's vtable + 0xD4 answer */
uint32_t bo3_rules_gen_end_session(uint32_t r);
#define BO3_RULES_END_SESSION(r) bo3_rules_gen_end_session((uint32_t)(r))

/* main21 patch 105 (Crash Breaker in every mode):
 *   arm   sub_001935F0 loc_0019412D (recomp_0003.c), before the last mode compare: EAX = vt + 0x94's answer, EDI = S;
 *         1 -> loc_00194136 (the Crash Breaker checks as in Crash mode)
 *   fire  sub_00118410 loc_001188F5 (recomp_0002.c), after the read of the stored Crash-mode local: EAX's AL, ESI = V */
uint32_t bo3_rules_gen_cb_arm(uint32_t eax, uint32_t s);
uint32_t bo3_rules_gen_cb_fire(uint32_t eax, uint32_t v);
#define BO3_RULES_CB_ARM(eax, s) bo3_rules_gen_cb_arm((uint32_t)(eax), (uint32_t)(s))
#define BO3_RULES_CB_FIRE(eax, v) bo3_rules_gen_cb_fire((uint32_t)(eax), (uint32_t)(v))
/* main21 patch 117 (Crash Breaker v2, the push): sub_00120800 loc_00120876 (recomp_0002.c), right after the game's blast routine
 * sub_00115130 (traffic within its radius induced + pushed, the wreck pool pushed) returned: ESI = the blasting V. No register
 * changes. */
void bo3_rules_gen_cb_pushed(uint32_t v);
#define BO3_RULES_CB_PUSHED(v) bo3_rules_gen_cb_pushed((uint32_t)(v))

/* main21 patch 106 (rival count / cars): sub_00017450 loc_00017464 (recomp_0000.c), before the reads of S + 0xA8 / 0xAC / 0xB0;
 * ESI = the race set-up object S */
void bo3_rules_gen_rivals(uint32_t s);
#define BO3_RULES_RIVALS(s) bo3_rules_gen_rivals((uint32_t)(s))

/* main21 patch 113 (Single Event DJ): the music manager's three hub tests (recomp_0003.c), right after EAX is loaded from 0x463AF4:
 * sub_00154800 loc_0015481F (stage start), sub_001544C0 loc_00154585 (track change), sub_00154A70 loc_00154ABD (in the stage).
 * EAX = the front-end hub (0 World Tour, 1 Single Event, 2 2P, 3 online); the answer 0 takes the game's World Tour branch. */
uint32_t bo3_rules_gen_dj_hub(uint32_t hub);
#define BO3_RULES_DJ_HUB(h) bo3_rules_gen_dj_hub((uint32_t)(h))

/* main21 patch 107 (DEV-only diagnostics, bm_zdiag.c; marks only with BO3_HOOKREQ_ZDIAG=ON): the DJ state machine entry
 * sub_00154800 (EBX = the DJ object) and the Air Ram registration sub_0010C5F0 entry ([esp + 4] = its object) */
void bo3_zdiag_dj(uint32_t obj);
void bo3_zdiag_airram(uint32_t obj);
#define BO3_DIAG_DJ(o) bo3_zdiag_dj((uint32_t)(o))
#define BO3_DIAG_AIRRAM(o) bo3_zdiag_airram((uint32_t)(o))

#endif
