/* Burnout Mashup host hardening (capdbg T1, slice capfix1): the chevron draw's set-index guard. See bm_chevron.h.
 * MUT=n (test builds only) compiles one deliberate defect for the negative controls. */
#include "bm_chevron.h"

#include <stdio.h>

#include "bm_guest.h"

#ifndef MUT
#define MUT 0
#endif

static struct {
    uint32_t skips, last_st;
    int32_t last_z, last_n;
    int logged;
} s_chev;

uint32_t bo3_chev_skips(void)
{
    return s_chev.skips;
}

int bo3_chev_skip(uint32_t st, int32_t z)
{
    uint8_t b[2];
    int32_t n;

#if MUT == 4
    if (!bo3_guest_read(st + 0x1Eu, b, 2))      /* defect: an unreadable STATIC header lets the draw go on */
        return 0;
#else
    if (!bo3_guest_read(st + BO3_CHEV_COUNT_OFF, b, 2)) {
        s_chev.skips++;
        return 1;                                 /* fail closed: no chevron draw from an unreadable STATIC */
    }
#endif
#if MUT == 3
    (void)b;
    if (!bo3_guest_read(st + 0x1Cu, b, 2)) return 1;   /* defect: the backdrop count (+0x1C), not the chevron set's */
#endif
    n = (int16_t)(uint16_t)(b[0] | b[1] << 8);
#if MUT == 1
    if (z > n || z < 0) {                         /* defect: an index equal to the count passes */
#elif MUT == 2
    if (0) {                                      /* defect: no guard */
#else
    if (z < 0 || z >= n) {
#endif
        s_chev.skips++;
        if (!s_chev.logged || s_chev.last_st != st || s_chev.last_z != z || s_chev.last_n != n) {
            s_chev.logged = 1;
            s_chev.last_st = st;
            s_chev.last_z = z;
            s_chev.last_n = n;
            fprintf(stderr, "[CHEVRON] unit chevron index %d is outside the track's chevron set (%d entries, STATIC 0x%08X): "
                    "chevron draw skipped (track built without a chevron set, e.g. trackbuild <= 0.2.0)\n", (int)z, (int)n,
                    (unsigned)st);
        }
        return 1;
    }
    return 0;
}

/* bo3_chevron_gen.h */
int bo3_chev_gen_skip(uint32_t st, uint32_t z)
{
    return bo3_chev_skip(st, (int32_t)z);
}
