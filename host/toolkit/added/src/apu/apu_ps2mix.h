/*
 * apu_ps2mix.h -- event sounds at the PS2 version's level in the stereo fold (host setting PS2 SOUND, Burnout Mashup, 2026-11-05).
 *
 * This is Burnout Mashup's own file, under the project's MIT licence. The game sends boost and takedown sounds to the centre, and some of them to the
 * surrounds too, at the volume of the fronts. The fold (centre and surrounds at -3 dB) adds those copies of one signal: +4.6 dB with the centre, +7.7 dB
 * with the surrounds. Against slams, three PCSX2 recordings put them near 1:1, and a drive with this fold 3.4 to 5.3 dB above that.
 * A voice with a centre send gets its centre and surround sends lowered by APU_PS2MIX_LOWER (1/64 dB): each then folds at 0.15 instead of 0.7071, giving
 * 1.15 with the centre and 1.30 with the surrounds. The value is fitted to those measurements, not read from PS2 code.
 * The same voices also send to bins 17 and 18, the image's drive stage for the engines (amplified, folded, clipped, returned to the fronts). That path is
 * about two thirds of a boost's level here and the PS2 version has no such stage, so those sends are closed as well.
 * Voices without a centre send (music, engines, slams) are left alone.
 */
#ifndef APU_PS2MIX_H
#define APU_PS2MIX_H

#include <stdint.h>

#define APU_PS2MIX_LOWER 0x35E

static inline void apu_ps2mix_vols(const int bin[8], uint16_t vol[8])
{
    int centre = 0;
    for (int b = 0; b < 8; b++)
        if (bin[b] == 2 && vol[b] < 0xFFF)
            centre = 1;
    if (!centre)
        return;
    for (int b = 0; b < 8; b++)
        if (bin[b] == 17 || bin[b] == 18)
            vol[b] = 0xFFF;
    for (int b = 0; b < 8; b++) {
        if ((bin[b] == 2 || bin[b] == 4 || bin[b] == 5) && vol[b] < 0xFFF) {
            int x = vol[b] + APU_PS2MIX_LOWER;
            vol[b] = (uint16_t)(x > 0xFFF ? 0xFFF : x);
        }
    }
}

#endif /* APU_PS2MIX_H */
