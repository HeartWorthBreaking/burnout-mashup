/* bm_contact.h - main19 (hook request P2, item 26): bmashup.hooks v3 points 10 TRAFFIC_CONTACT (MODIFY NO_CRASH) and
 * 11 WRECK_CAUSE (OBSERVE) over two marks in the generated code (bo3_contact_gen.h). */
#ifndef BO3_BM_CONTACT_H
#define BO3_BM_CONTACT_H

#include <stdint.h>

/* After bo3_bm_hooks_init, before bo3_plugins_init: checks the marks' bytes in guest memory (the census, XBE 9f497acd) and
 * offers the two points (bo3_hk_offer_point). */
void bo3_contact_init(void);
uint32_t bo3_ct_pushed(void);           /* main21 patch 79: contacts whose push force took a plugin factor */
/* 1 when the census passed and the points were offered */
int bo3_contact_available(void);
/* counters (tests / logs) */
typedef struct bo3_contact_stats {
    uint32_t decisions;         /* fatal decisions reaching the mark (racer vs non-racer) */
    uint32_t no_crash;          /* turned non-fatal by a plugin */
    uint32_t skipped_racers;    /* racer vs racer (never dispatched) */
    uint32_t skipped_forced;    /* the game's forced fatal path (P + 0x212) */
    uint32_t wreck_causes;
} bo3_contact_stats;
void bo3_contact_get_stats(bo3_contact_stats *out);
uint32_t bo3_contact_claims(void);      /* item 39: claims written for an accepted WRECK_CAUSE credit */

#endif
