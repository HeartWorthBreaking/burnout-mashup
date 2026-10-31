/* bm_input.h - main18 (platform 0.1.8, hook request P1): "bmashup.input" v1 (include/bmashup_input.h), the host side.
 * controls.c's ctl_pad (the "ctl_pad" mark, right after the title's pad read in sub_001B57E0) calls bo3_bm_input_note for
 * the title port it handled, with the pad record's XINPUT_GAMEPAD bytes as the title will read them (NULL: no pad open).
 * main.c calls bo3_bm_input_configure before the guest runs (the overlay / host-page / picture-count queries). */
#ifndef BO3_BM_INPUT_H
#define BO3_BM_INPUT_H

#include <stdint.h>

#include "bmashup_input.h"

#define BO3_INPUT_PADREC     0x004AE20Cu   /* the pad manager's four records of 0x20 ({state, handle, XINPUT_STATE}) */
#define BO3_INPUT_MODULE     0x004D5370u   /* the current module (controls.c CTL_MODULE) */
#define BO3_INPUT_VT_GAME    0x003A9ACCu   /* the game module's vtable */
#define BO3_INPUT_VT_FE      0x003A9E7Cu   /* the front end's vtable */
#define BO3_INPUT_PAUSED_BY  0x004D537Cu   /* -1 while not paused */
#define BO3_INPUT_STEP       0x004D53B4u   /* module switch: 5 running (0 before the game object) */

typedef struct bo3_input_cfg {
    int (*overlay_open)(void);             /* the toolkit overlay is open (xbox_OverlayOpen), NULL: never */
    int (*host_page)(void);                /* a host page owns the title's menu (bo3_modsmenu_mode() != 0), NULL: never */
    uint32_t (*pictures)(void);            /* the host's picture count (main.c's flips), NULL: 0 */
} bo3_input_cfg;

void bo3_bm_input_init(void);              /* registers the service */
void bo3_bm_input_configure(const bo3_input_cfg *cfg);
const bm_input_api *bo3_bm_input_api(void);
/* one title port (0..3) read; gamepad = the 18 XINPUT_GAMEPAD bytes the title reads (wButtons, 8 analog, 4 sticks), or
 * NULL when the port has no pad open. Game thread (the ctl_pad mark). */
void bo3_bm_input_note(uint32_t title_port, const uint8_t *gamepad);
void bo3_bm_input_reset(void);             /* tests */

#endif
