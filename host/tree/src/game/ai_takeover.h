/*
 * ai_takeover.h - the title's own takeover of a player car by its AI, and
 * the controller stamp that keeps an idle race from pausing (ai_takeover.c).
 * Shared by RECOMP_DEBUG=autopilot (autopilot.c) and the private
 * "bmashup.autopilot" service (bm_autopilot.c); both call it only from the
 * "ap_update" mark, on the game's thread, inside the player car's update.
 */
#ifndef BO3_AI_TAKEOVER_H
#define BO3_AI_TAKEOVER_H

#include <stdint.h>

#define AP_CAR1         0x0073A1D0u     /* the world (0x60EA00) + 0x12B7D0: player 1's CB3PlayerCar */
#define AP_CAR_AI       0x27D8u         /* byte: the AI drives this player car */
#define AP_CAR_PLAYER   0x27D0u         /* the player index */
#define AP_CAR_PHASE    0x134Cu         /* 1 before the GO, 2 in play, 3 finished */
#define AP_CAR_AI_RESET 0x19D0u         /* four words the title zeroes on a takeover */
#define AP_CAR_DRIVER   0x1A00u         /* sub_00179760's eax */
#define AP_CAR_PLACE    0x10D0u         /* int16: the placing, 1 = first */
#define AP_CAR_TIME     0x10DCu         /* float: the race time, s */
#define AP_CAR_LAPS     0x10E4u         /* the laps done */
#define AP_CAR_BEST     0x110Cu         /* float: the best lap, s */
#define AP_RACERS       0x0073A19Cu     /* the number of cars racing */
#define AP_CTLS         0x004AE724u     /* the four controller records */
#define AP_CTL_SIZE     0x188u
#define AP_CTL_ACTIVE   0x184u          /* float: the time of its last input */
#define AP_NOW          0x004AE200u     /* float: the clock sub_00019A10 stamps it with */
#define AP_MODULE       0x004D5370u     /* the current module */
#define AP_VT_GAME      0x003A9ACCu     /* the game module's vtable */
#define AP_PAUSED_BY    0x004D537Cu     /* -1 while not paused */
#define AP_MODULE_STEP  0x004D53B4u     /* 6: the module is being left */
#define AP_CAR_PHYS     0x2440u         /* the car's physics object (its + 0x1580 points back at the car) */
#define AP_PHYS_CAR     0x1580u         /* physics: its car (sub_00117870 at 0x1178A6 reads the AI byte through it) */
#define AP_PHYS_MODE    0x1524u         /* physics: 4 is reset to 0 by the hand-back */
#define AP_PHYS_BLEND   0x1534u         /* physics: float, set to [AP_ONE] by the hand-back */
#define AP_ONE          0x003B168Cu     /* .rdata float 1.0 (0x3F800000) the hand-back reads */

/* The title's takeover of `car` (sub_0018C510 at 0x18C688): its AI byte set,
 * the four words at + 0x19D0 zeroed, sub_00179760 with eax = car + 0x1A00.
 * Only from the "ap_update" mark (esi the car): the registers the call
 * changes beyond its own work are put back. Never writes 0 to the byte. */
void bo3_ai_takeover(uint32_t car);
/* The title's hand-back of `car` to its pad: CB3PlayerCar::SetAIControlled
 * with 0 (sub_0018CB60 at 0x18CB86), the same three steps the title does at
 * the end of a rolling start (sub_001935F0 at 0x193892) and in sub_000279C0:
 * the AI byte 0, the physics object's (car + 0x2440) float + 0x1534 set to
 * [0x3B168C] (1.0), its + 0x1524 set to 0 when it is 4. No call, no register
 * changed. The caller has checked the car, the physics link and the build. */
void bo3_ai_handback(uint32_t car);
/* Each controller record's last-input time set to the clock, so the title
 * does not pause a race nobody touches the pad in. */
void bo3_ai_stamp_pads(void);

#endif
