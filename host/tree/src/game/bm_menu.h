/* bm_menu.h - main19 (platform 0.1.9, hook request P3 items D1 / D2 / D3, patches 32..34): "bmashup.menu" v1
 * (include/bmashup_menu.h), the host side. */
#ifndef BO3_BM_MENU_H
#define BO3_BM_MENU_H

#include <stdint.h>

#include "bmashup_menu.h"

/* probe-pending constants (main19 STATE_C.md; FEASIBILITY D1 / D2 / D3). 0 = the feature answers UNAVAILABLE. */
#ifndef BM_P23_MENU_POPUP_SITE
#define BM_P23_MENU_POPUP_SITE 1   /* PR-C + PR-F (D1, PROBE_RESULTS "PR-F" p23_fa4 / p23_fb4): 1 = the car-select page's input
                                    * marks (patch 45: vt 0x3AC044 slots 0 / 4) trigger and drive the popup; 0 = UNAVAILABLE */
#endif
#ifndef BM_P23_MENU_MODE_ROUTE
#define BM_P23_MENU_MODE_ROUTE 1   /* PR-C + PR-E (D2) + patch 43's offline RE (STEP0_G.md): 1 = ELIMINATOR rows are appended to the
                                    * Single Event SELECT MODE list and routed to the Eliminator logic; 0 = UNAVAILABLE */
#endif
#ifndef BO3_HOOKREQ_P12B
#define BO3_HOOKREQ_P12B 0         /* main21 patch 87: CMake option (default ON); stand-alone compiles (tests) keep main20's 0 */
#endif
#ifndef BO3_HOOKREQ_P22M
#define BO3_HOOKREQ_P22M 0         /* main21 patch 93: CMake option (default ON): the pause menu's MOD SETTINGS row */
#endif
#define BO3_MENU_PAUSE_ACTION 6u   /* main21 patch 93: the row's action id (the game's own are 0..5; > 5 = its no-op default) */
void bo3_menu_set_pause_open(int (*open_settings)(void));   /* main21 patch 93: modsmenu_ov.c (0 = no overlay page) */
uint32_t bo3_menu_pause_stat(uint32_t which);              /* main21 patch 93: 0 rows added, 1 overlay opens */
#ifndef BO3_HOOKREQ_P13H
#define BO3_HOOKREQ_P13H 0         /* main21 patch 88: CMake option (default ON): mode-row help / option lines */
#endif
#if BO3_HOOKREQ_P12B && !defined(BM_P23_MENU_BARS_SITE)
#define BM_P23_MENU_BARS_SITE 1    /* main21 patch 87 (open-list item 8): bars drawn at the sub_000F6DC0 exit (main19 57 + 59) */
#endif
#ifndef BM_P23_MENU_BARS_SITE
#define BM_P23_MENU_BARS_SITE 0    /* main19 item 55: 0 in 0.1.9 - round 3 (m19_r3a) car-select shots show NO bars although the example logged "bars drawn: 1" (draw site sub_000B6F90 not proven); bars answer UNAVAILABLE. Was:  item 47 (D3 reduced form): 1 = bars drawn with the hud v2 executor at the end of the front-end
                                    * render callback sub_000B6F90 on the car select (best candidate; owner 2026-10-28: validated by a
                                    * car-select screenshot); 0 = BARS UNAVAILABLE (patch 34's form) */
#endif

/* the title's dialog (FACT: SITES_VERIFIED s8.1 + tests\p23\step0_c_out.txt) */
#define BO3_MENU_DIALOG   0x00550DA0u   /* D */
#define BO3_MENU_D_ACTIVE 0x0Au         /* MEM8(D + 0xA): 1 open (sub_000CBE40 0xCBE5A), 0 closed (sub_000CCC90 0xCCCA4) */
#define BO3_MENU_PENDING  15u           /* the poll's "no answer yet" (0xCD2CC) */
#define BO3_MENU_TEXT_BUDGET 0x4000u    /* UTF-16 texts of every declaration, guest high zone (16 KiB) */

/* the dialog calls (the game build: the retail call shapes of 0x86600 / 0x86800 / sub_000CCC90; tests: stand-ins) */
typedef struct bo3_menu_ops {
    void (*open)(uint32_t type, uint32_t msg, uint32_t choice1, uint32_t choice2);   /* ECX = D, AL = 0, 5 stack args */
    uint32_t (*poll)(uint32_t port);                                                  /* EDI = D, push 1, push port */
    void (*close)(void);                                                              /* ECX = D */
} bo3_menu_ops;
typedef uint32_t (*bo3_menu_alloc_fn)(uint32_t size, uint32_t align);
/* where a popup's answer goes (the plugin's PER_PLAYER setting; game build: logged until the trigger site exists) */
typedef void (*bo3_menu_answer_fn)(const td_host *host, const char *key, uint32_t player, int32_t value);

void bo3_bm_menu_init(void);
void bo3_bm_menu_close(void);                       /* after the plugins' start: no more declarations; texts copied */
const bm_menu_api *bo3_bm_menu_api(void);
void bo3_menu_set_ops(const bo3_menu_ops *ops);
void bo3_menu_set_alloc(bo3_menu_alloc_fn a);
void bo3_menu_set_answer(bo3_menu_answer_fn fn);
int bo3_menu_popup_trigger(uint32_t context, uint32_t player);   /* the car-confirm site: popups queued (0 when none) */
int bo3_menu_popup_frame(uint32_t port);            /* each front-end frame: 1 while a host popup is up */
int bo3_menu_census(void);
uint32_t bo3_menu_mode_count(void);                /* patch 33: modes declared (tests) */
int bo3_menu_bar_value(uint32_t i, const char *vehicle, float *v);   /* patch 34: the car-select draw's seam */
/* item 47: the bars on car select (bo3_mbars_gen.h mark; main.c calls bo3_menu_bars_flip once a picture) */
#define BO3_MENU_CAR_ID 0x00740B00u      /* player 0's chosen car: the 8-byte id sub_000C0080 reads (+0x2470 a player) */
void bo3_menu_bars_flip(void);
uint64_t bo3_menu_bars_car_id(void);                 /* item 59: the previewed car's id (0 none) */
void bo3_menu_gen_bars_draw(void);
int bo3_menu_census_bars(void);
struct bm_hud_cmd;
void bo3_menu_set_bars_io(int (*draw)(const struct bm_hud_cmd *cmds, uint32_t n), int (*car)(char *name, uint32_t room));   /* tests */
void bo3_menu_reset(void);                          /* tests */

/* patch 45: the live popup on the car-select page (FACT: PROBE_RESULTS PR-C / PR-F; census bo3_menu_census) */
#define BO3_MENU_FE_PHASE   0x00557A64u   /* the front end's page phase (5 = the page takes input; both handlers test it) */
#define BO3_MENU_FE_PAGE    0x00557A70u   /* the current front-end page object */
#define BO3_MENU_PG_SE_LIST 0x005595A4u   /* Single Event SELECT MODE list page (vt 0x3ABE1C) */
#define BO3_MENU_PG_SE_OPTS 0x0055B6D0u   /* Single Event options page (vt 0x3ABF1C) */
#define BO3_MENU_PG_CARSEL  0x00559648u   /* car select page (vt 0x3AC044; input slots 0 sub_00071AF0, 4 sub_00072500) */
#define BO3_MENU_PADS       0x004AE20Cu   /* the pad manager's 4 records of 0x20 {state (2 = open), handle, XINPUT_STATE} */
#define BO3_MENU_PAD_A      0x0Eu         /* record + 0xE = bAnalogButtons[0] (A), held above 30 (XBOX_ANALOG_BUTTON_THRESHOLD) */
#define BO3_MENU_ALL_PADS   0xFFFFFFFFu   /* the poll's controller -1 = every pad (sub_00017BB0; PR-F: 2 was ignored) */
/* each front-end flip (main.c uw_flip): the page tracker (the Single Event flow = the SE list page was the last list page) */
void bo3_menu_fe_flip(void);
/* the generated marks (bo3_menu_gen.h): 1 = skip the page's input this frame */
uint32_t bo3_menu_gen_page_input(uint32_t slot);
/* tests: the guest reads of the page / phase / pads go through bo3_guest_read; the state machine's phase (0 idle, 1 run, 2 drain) */
uint32_t bo3_menu_live_state(void);

/* patch 43: the Single Event SELECT MODE list page L = 0x5595A4 (FACT, XBE + Globalus.bin, tests\p23\STEP0_G.md):
 * L+4 row count (4), L+8 selected row, L+0xC title text id, L+0x10 + 4 i row text ids, L+0x38 + i / L+0x42 + i row flags,
 * L+0x4E u16 widget selection, L+0x50 u16 widget count (the down-move bound, 0x769CD), L+0x54 + 8 i rows {u32 text pointer,
 * u8 disabled, u8 0} read by the list widget 0x5509F4 (+0x10 = that array); the page ends at L+0xA4 = 0x559648 -> 10 rows. */
#define BO3_MENU_SE_LIST_ROWS 4u          /* retail rows: RACE / TIME ATTACK / ROAD RAGE / CRASH (ids 0x14A / 0x14C / 0x14B / 0x150) */
#define BO3_MENU_LIST_CAP     10u
#define BO3_MENU_SE_SETTINGS  0x00463AF0u /* the Single Event settings S (S + 8 = 0x463AF8 the selected mode row) */
#define BO3_MENU_LOGIC_SLOT   0x004D4788u /* the race logic the set-up selects */
#define BO3_MENU_LAPS         0x004D467Cu /* the lap count (the Eliminator: 5, as World Tour's set-up) */
#define BO3_MENU_ELIM_LOGIC   0x004D4BD8u
#define BO3_MENU_ELIM_LAPS    5u
#define BO3_MENU_ROW_TEXT_ID  0x14Au      /* the id written into an added row's id slot ("RACE": any lookup stays a valid text) */
int bo3_menu_census_mode(void);           /* patch 43: the mode-row sites (XBE 9f497acd) */
/* main21 C3-5 (open-list item 9, MP part; notes\C3_5_MP_ROWS_RE.md): the Multiplayer list page M = 0x55C460 (the SE layout; set-up
 * sub_0006C720 count 5 at 0x6C7B2, rows mark loc_0007A0F4 in sub_0007A030), accept sub_0006C410 loc_0006C54F (row >= 5 -> the
 * game's Race 0x463AFC = 0), route sub_0005F7B0's Race case loc_0005F846 after the MP Race logic store. Switch BO3_HOOKREQ_ZMPR. */
#ifndef BO3_HOOKREQ_ZMPR
#define BO3_HOOKREQ_ZMPR 1                /* no CMake option yet: on (the marks in the generated code use the same default) */
#endif
#define BO3_MENU_PG_MP_LIST   0x0055C460u /* Multiplayer mode list (M + 8 = 0x55C468 the accepted row) */
#define BO3_MENU_MP_LIST_ROWS 5u          /* RACE / ROAD RAGE / TEAM CRUSH / DOUBLE IMPACT / PARTY CRASH */
#define BO3_MENU_MP_LOGIC_SLOT 0x004D4950u /* the 2-player stage 0x4D4798 + 0x1B8 */
#define BO3_MENU_MP_RACE_LOGIC 0x004D4E54u /* MP Race (vt 0x3A9FB8) */
#define BO3_MENU_MP_STAGE     0x004D4798u /* the 2-player stage object (vt 0x3A939C) */
int bo3_menu_census_mp(void);             /* C3-5: the MP sites (XBE 9f497acd) */
uint32_t bo3_menu_mp_route_mode(void);    /* tests: 1 + the routed MP mode, 0 none */
uint32_t bo3_menu_route_mode(void);       /* tests: 1 + the routed mode, 0 none */
void bo3_menu_set_rules(void (*mode_race)(const td_host *owner));   /* the game build: bo3_rules_mode_race */

#endif
