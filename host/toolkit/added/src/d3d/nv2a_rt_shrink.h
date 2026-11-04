/*
 * nv2a_rt_shrink.h - a scaled render target read by a smaller one (main21 patch 133, takedawn issue 78).
 *
 * A title shrinks a surface by reading a few texels per target pixel at offsets it worked out for the guest size: Burnout 3's
 * bloom takes four samples of the 640x480 frame for each pixel of a 320x240 target. Those samples cover every guest texel, but
 * at render.scale 3 they land on a few of the host texels only, so a small bright spot glows or misses by where it falls. Such
 * a read goes through a copy of the source reduced to its guest size, so the title's samples see what they see at 1x.
 *
 * The reduction steps at most 2:1 per axis, which a linear blit reads completely: an exact 2:1 step averages each 2x2 block.
 * No graphics here, so tests\p55 can check the rules.
 */
#ifndef NV2A_RT_SHRINK_H
#define NV2A_RT_SHRINK_H

#include <stdint.h>

#define NV2A_RT_SHRINK_STEPS 4      /* to 16x; a bigger scale reads the target as before */

/* Does a draw into a dst_w x dst_h target read this source through the reduced copy? Only a scaled source and a target smaller
 * than it on both axes in guest pixels: at 1x, a same-size copy or an enlargement nothing changes. */
static inline int nv2a_rt_shrink_wanted(uint32_t src_w, uint32_t src_h, uint32_t src_hw, uint32_t src_hh,
                                        uint32_t dst_w, uint32_t dst_h)
{
    return src_hw > src_w && src_hh > src_h && dst_w < src_w && dst_h < src_h;
}

/* The sizes to blit through, largest first, the last = w x h; each is at most 2:1 from the one before (the first from
 * hw x hh). Returns how many, 0 when it takes more than NV2A_RT_SHRINK_STEPS. */
static inline int nv2a_rt_shrink_plan(uint32_t w, uint32_t h, uint32_t hw, uint32_t hh,
                                      uint32_t out_w[NV2A_RT_SHRINK_STEPS], uint32_t out_h[NV2A_RT_SHRINK_STEPS])
{
    int n = 1, i;
    if (!w || !h)
        return 0;
    while (n <= NV2A_RT_SHRINK_STEPS && ((uint64_t)hw > (uint64_t)w << n || (uint64_t)hh > (uint64_t)h << n))
        n++;
    if (n > NV2A_RT_SHRINK_STEPS)
        return 0;
    for (i = 0; i < n; i++) {
        out_w[i] = w << (n - 1 - i);
        out_h[i] = h << (n - 1 - i);
    }
    return n;
}

#endif
