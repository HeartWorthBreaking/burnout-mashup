/*
 * apu_softmusic.h -- the PS2 version's music bandwidth (host setting PS2 MUSIC, Burnout Mashup, 2026-11-05).
 *
 * This is Burnout Mashup's own file, under the project's MIT licence: three textbook biquad low-passes at 48 kHz (R. Bristow-Johnson),
 * 14 kHz Q 0.43, and 18 kHz Q 0.5412 and 1.3066. The response is fitted to what the PS2's 32 kHz streams through its interpolation give
 * against 44.1 kHz through linear interpolation, computed from tables: about -0.9 dB at 5 kHz, -1.8 at 7, -2.9 at 9, -4.4 at 11, -7.4 at 14, with its 16 kHz limit
 * approximated by -10 at 16, -17 at 18, -35 at 20. Unity at DC.
 */
#ifndef APU_SOFTMUSIC_H
#define APU_SOFTMUSIC_H

#include <math.h>

typedef struct ApuSoftMusic {
    float z[3][2];
} ApuSoftMusic;

static inline float apu_softmusic_step(ApuSoftMusic *s, float in)
{
    static const float k[3][5] = {
        {0.2964481f, 0.5928961f, 0.2964481f, 0.2438044f, -0.0580121f},
        {0.5162798f, 1.0325596f, 0.5162798f, 0.8554004f, 0.2097188f},
        {0.6717770f, 1.3435540f, 0.6717770f, 1.1130366f, 0.5740714f},
    };
    float x = in;
    for (int b = 0; b < 3; b++) {
        float out = k[b][0] * x + s->z[b][0];
        s->z[b][0] = k[b][1] * x - k[b][3] * out + s->z[b][1];
        s->z[b][1] = k[b][2] * x - k[b][4] * out;
        x = out;
    }
    return x;
}

/* A state that is no longer a number is cleared; one decayed below anything audible is set to zero (no denormals). */
static inline void apu_softmusic_tidy(ApuSoftMusic *s)
{
    for (int b = 0; b < 3; b++) {
        if (!isfinite(s->z[b][0]) || !isfinite(s->z[b][1]) || (fabsf(s->z[b][0]) < 1e-18f && fabsf(s->z[b][1]) < 1e-18f)) {
            s->z[b][0] = 0.0f;
            s->z[b][1] = 0.0f;
        }
    }
}

#endif /* APU_SOFTMUSIC_H */
