/* bm_evsound.h - main19 (hook request P2, item 27): bmashup.hooks v3 point 12 EVENT_SOUND (MODIFY SOUND_LEVEL) at the
 * takedown-sign sound's two pitch calls (bo3_evsound_gen.h). */
#ifndef BO3_BM_EVSOUND_H
#define BO3_BM_EVSOUND_H

#include <stdint.h>

/* After bo3_bm_hooks_init, before bo3_plugins_init: census of the site bytes (XBE 9f497acd), then the point is offered. */
void bo3_evsound_init(void);
int bo3_evsound_available(void);
uint32_t bo3_evsound_changed(void);     /* sounds whose level a plugin changed */
uint32_t bo3_evsound_pitched(void);     /* main21 patch 78: plays whose pitch slot took a plugin's factor */

#endif
