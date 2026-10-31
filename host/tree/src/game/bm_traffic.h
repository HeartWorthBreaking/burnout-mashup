/* bm_traffic.h - gp slice traffic1 EXPERIMENTAL: "bmashup.traffic" (include/bmashup_traffic.h), the host side. The core works
 * through a guest-access interface so the offline tests run it over real traffic sets; the game build (BO3_TRAFFIC_GAME) binds
 * it to bm_guest.c. */
#ifndef BO3_BM_TRAFFIC_H
#define BO3_BM_TRAFFIC_H

#include <stdint.h>

#include "bmashup_traffic.h"

/* the traffic system object and the fields the service uses (atlas TRAFFIC.md s1; recomp_0003.c) */
#define BO3_TR_SYSTEM      0x006137E0u   /* T: world 0x60EA00 + 0x4DE0; the code's own constant (sub_001A6B40 ...) */
#define BO3_TR_SET         0x0u          /* T+0: the loaded set (sub_0018B250 writes it) */
#define BO3_TR_POOL        0x363ABu      /* u8: pool size (0xFE once set up) */
#define BO3_TR_ACTIVE      0x363ACu      /* u8: vehicles alive (sub_001A38F0 ++, sub_001A41A0 --) */
#define BO3_TR_SET_TRIG    0x4Cu         /* set: trigger table pointer, count at +0x50 */
#define BO3_TR_SET_FLAGS   0xB4u         /* set: mode byte */
#define BO3_TR_TRIG_SIZE   0x58u
#define BO3_TR_TRIG_FLOWP  0x10u         /* trigger: p4, the flow records */
#define BO3_TR_TRIG_FLOWN  0x44u         /* trigger: flow record count */
#define BO3_TR_TRIG_ROADS  0x14u         /* trigger: p5, the road (valve) byte of each flow record (main21 v6; trackbuild traffic.py) */
#define BO3_TR_FLOW_REC    28u           /* {u32, six floats: vehicles per minute per class} */
#define BO3_TR_MAX_TRIG    128u          /* retail max 64 */
#define BO3_TR_MAX_FLOWS   1024u         /* per trigger; retail max 332 */
#define BO3_TR_MAX_VALUES  262144u       /* floats tracked at most */
#define BO3_TR_MAX_FLOW    1000.0f       /* vehicles / minute; retail max 20.1 */
/* v4 (main21 patch 67): the spawn generator T + 0x36348 / + 0x3634C (= 0x649B28 / 0x649B2C) and the game's fixed seed, written
 * by the traffic reset sub_001A3EA0 (the only constant writer; every other write is a draw x = (x << 16) + hi16(x) + y, y += x) */
#define BO3_TR_SEED_LO     0x36348u
#define BO3_TR_SEED_HI     0x3634Cu
#define BO3_TR_GAME_SEED_LO 0xFD462907u
#define BO3_TR_GAME_SEED_HI 0x02B9D6F8u

typedef struct bo3_tr_guest {
    int (*read)(void *user, uint32_t va, void *out, uint32_t n);          /* 1 done, 0 refused */
    int (*write)(void *user, uint32_t va, const void *in, uint32_t n);
    void *user;
} bo3_tr_guest;

/* main21 patch 68 (P5b): binds the game's own induced traffic crash sub_00111750 (EBX = the inducing physics vehicle, ESI = the
 * physics manager 0x64B310, stack: the traffic vehicle record, 1); fn returns its EAX (the wreck body, 0 = none). NULL (default)
 * = no wreck possible. Called only on the game's thread (the traffic update mark). Kept apart from bo3_tr_guest so the earlier
 * tests' initialisers stay valid. */
void bo3_tr_set_induce(uint32_t (*fn)(void *user, uint32_t inducer_vehicle, uint32_t record), void *user);

/* P5b: the traffic vehicle records (statically verified in this build's code; census rows in bm_traffic.c) */
#define BO3_TR_BITMAP      0x362E0u      /* u32 words, bit i = vehicle i alive (sub_001A20F0 0x1A2567) */
#define BO3_TR_RECS        0x127D0u      /* records T + 0x127D0 + 0x180 i (= 0x625FB0 + 0x180 i, sub_0019F560 0x19F576) */
#define BO3_TR_REC_SIZE    0x180u
#define BO3_TR_REC_POS     0xA0u         /* vec4 world position (sub_001A6B40 0x1A6B89, the live-radius test) */
#define BO3_TR_REC_CLASS   0x173u        /* u8 vehicle class (the modder's PS2 map; read by the kamikaze pass 0x19F593) */
#define BO3_TR_REC_FLAGS   0x174u        /* u8 state bits; & 6 = the game's own "do not induce" test (0x19F65A) */
#define BO3_TR_NOT_INDUCIBLE 6u
#define BO3_TR_MAX_VEH     254u

/* binds the guest access; verified = the build check (the game's own constants) passed. Resets every state. */
void bo3_tr_configure(const bo3_tr_guest *g, int verified);
/* the marks (generated code, through bo3_traffic_gen.h): the traffic system at its set-up */
void bo3_tr_gen_init(uint32_t traffic);
/* v4: right after the traffic reset sub_001A3EA0 returns into the traffic init (loc_001A1A1F, esi = T), before the first draw */
void bo3_tr_gen_seed(uint32_t traffic);
/* P5b: in the traffic update sub_001A20F0 right after the game's own kamikaze / induce pass (loc_001A2567, ebx = T): samples the
 * vehicle positions (host-derived speeds) and carries out the queued wreck() calls */
void bo3_tr_gen_update(uint32_t traffic);
/* P5c (patch 69): the lane section fill sub_001A6070 - e = the cars the game expects in the section (loc_001A61C1, after its
 * product; returns the e it continues with), and each car's position (loc_001A62A4: i, rand x spacing, spacing, the game's own
 * position; returns the position it uses) */
float bo3_tr_gen_section(float e);
float bo3_tr_gen_place(float game_pos, float i, float rand_spacing, float spacing);
const bm_traffic_api *bo3_bm_traffic_api(void);
/* test / log counters: 0 applications, 1 refusals, 2 values written (total), 3 marks seen */
uint32_t bo3_tr_stat(uint32_t which);
/* optional log sink (the game build: stderr) */
void bo3_tr_set_log(void (*fn)(const char *line));

#endif
