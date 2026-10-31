/* bm_rules.h - main19 (platform 0.1.9, hook request P3 E1, patch 35): "bmashup.rules" v1 (include/bmashup_rules.h), the host side. */
#ifndef BO3_BM_RULES_H
#define BO3_BM_RULES_H

#include <stdint.h>

#include "bmashup_rules.h"

#ifndef BM_P23_RULES_AVAILABLE
#define BM_P23_RULES_AVAILABLE 1   /* PR-E (E1) DECIDED READY (p23_e1r / p23_e2r): the Eliminator logic runs from a routed SE row,
                                    * host eliminate / lap switch / end by eliminations validated. (A race still has to come from a
                                    * bmashup.menu ELIMINATOR row: without one, claim_race answers WRONG_MODE.) */
#endif

/* the game (FACT: SITES_VERIFIED s8.4 + tests\p23\step0_c_out.txt) */
#define BO3_RULES_VT_ELIM   0x003A9D50u   /* the Eliminator rules' vtable (+0x68 = sub_00024E30, the per-lap callback) */
#define BO3_RULES_ELIM_LOGIC 0x004D4BD8u  /* patch 42 (FACT PR-C / PR-E): THE Eliminator logic object (container 0x4A71A0 + 0x2DA38) */
#define BO3_RULES_NOT_OUT   0xFFFFu       /* patch 42 (FACT PR-E): R + 0x10D2 of a racer still in the race; R + 0x16C8 = -1 then */
#define BO3_RULES_RACERS    0x0073A19Cu   /* count */
#define BO3_RULES_LIST      0x0073A1A8u   /* MEM32(list + 4 i) = racer R */
#define BO3_RULES_CAR1      0x0073A1D0u   /* player 0's racer */
#define BO3_RULES_CAR2      0x0073C640u   /* main21 C3-5: player 2's racer in the 2-player stage (0x73A1D0 + 0x2470; HYPOTHESIS) */
#define BO3_RULES_MP_STAGE  0x004D4798u   /* main21 C3-5: the 2-player stage object (vt 0x3A939C; logic at + 0x1B8 = 0x4D4950) */
#define BO3_RULES_R_CTRL    0x134Cu       /* main21 C3-5: u32 control type (2 = human: HYPOTHESIS, the Eliminator results' test) */
#define BO3_RULES_MODULE    0x004D5370u   /* MEM32(MEM32(module) + 0x1B8) = the current race logic (0x140953's compare) */
#define BO3_RULES_LOGIC     0x1B8u
#define BO3_RULES_R_ORDER   0x10D2u       /* u16: elimination order (sub_00024F10 writes it) */
#define BO3_RULES_R_PROG    0x10E4u       /* i32: the per-lap rule's "last" metric (lowest = out) */
#define BO3_RULES_R_RACING  0x19A8u       /* u8: taking part (the per-lap rule skips 0) */
#define BO3_RULES_R_ALIVE   0x16C8u       /* sub_00024F10 clears it */

void bo3_bm_rules_init(void);
const bm_rules_api *bo3_bm_rules_api(void);
void bo3_rules_tick(void *user);              /* the ap_update writer (game thread): queued eliminations, end_race */
void bo3_rules_lifecycle(uint32_t kind);      /* bm_lifecycle.c */
void bo3_rules_mode_race(const td_host *owner);   /* bmashup.menu: the race in play was started from owner's mode row */
typedef void (*bo3_rules_elim_fn)(uint32_t rules, uint32_t racer);   /* the game's eliminate (sub_00024F10 shape) */
void bo3_rules_set_elim(bo3_rules_elim_fn fn);
/* main21 patch 105: the Crash Breaker blast's AI wrecks (bm_racers.c bo3_racers_blast; set by the game build, tests set a stand-in) */
typedef uint32_t (*bo3_rules_blast_fn)(uint32_t v, uint32_t radius_m);
void bo3_rules_set_blast(bo3_rules_blast_fn fn);
/* main21 patch 117: the push of the AI racers after the game's blast routine (bm_racers.c bo3_racers_push; tests set a stand-in) */
void bo3_rules_set_push(bo3_rules_blast_fn fn);
uint32_t bo3_rules_cb_pushed(void);
uint32_t bo3_rules_cb_blasts(void);
uint32_t bo3_rules_cb_rearms(void);
int bo3_rules_census(void);
void bo3_rules_reset(void);                   /* tests */
uint32_t bo3_rules_props_used(void);          /* main21 patch 80: prop checks answered "not Road Rage" (tests) */
uint32_t bo3_rules_end_session_used(void);    /* main21 patch 83: pause menus given END SESSION (tests) */
uint32_t bo3_rules_seconds(void);             /* tests: car updates per second used for the rate (60) */

#endif
