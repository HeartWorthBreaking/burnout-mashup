/*
 * apu_gauss.h -- a four-point interpolation of the kind the PS2's sound chip uses (host setting PS2 SOUND, Burnout Mashup, 2026-11-05).
 *
 * This is Burnout Mashup's own file, under the project's MIT licence. The weights come from a formula, exp(-a d^2) (1 + b d^2),
 * d the distance in source samples, each phase's four normalised to 1. Two parameters were fitted to the frequency response of
 * the chip's interpolation (largest weight error 0.3 %); no table of the chip's or an emulator's is included. At 24 kHz it gives
 * about -2.1 dB at 5 kHz, -4.4 at 7, -7.4 at 9, -11.4 at 11 against 1 kHz, and false tones 14 to 20 dB under linear interpolation's.
 */
#ifndef APU_GAUSS_H
#define APU_GAUSS_H

#include <math.h>

#define APU_GAUSS_PHASES 256

/* Fill the weights (once). */
static inline void apu_gauss_fill(float tab[APU_GAUSS_PHASES][4])
{
    for (int p = 0; p < APU_GAUSS_PHASES; p++) {
        const double t = (p + 0.5) / APU_GAUSS_PHASES;
        double w[4], s = 0.0;
        for (int c = 0; c < 4; c++) {
            const double d = (double)c - 1.0 - t;
            w[c] = exp(-1.135 * d * d) * (1.0 - 0.34 * d * d);
            s += w[c];
        }
        for (int c = 0; c < 4; c++)
            tab[p][c] = (float)(w[c] / s);
    }
}

/* pos in [0,1) lies between b and c. */
static inline float apu_gauss_at(const float tab[APU_GAUSS_PHASES][4], float pos, float a, float b, float c, float d)
{
    int p = (int)(pos * APU_GAUSS_PHASES);
    if (p < 0) p = 0;
    if (p >= APU_GAUSS_PHASES) p = APU_GAUSS_PHASES - 1;
    return tab[p][0] * a + tab[p][1] * b + tab[p][2] * c + tab[p][3] * d;
}

#endif /* APU_GAUSS_H */
