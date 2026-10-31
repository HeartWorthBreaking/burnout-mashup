/* bm_gdslot.c - gp slice mega1 EXPERIMENTAL: the GAMEDATA slot expansion (bm_gdslot.h). MUT=n: test builds only. */
#include "bm_gdslot.h"

#include <stdio.h>

#ifndef MUT
#define MUT 0
#endif

static uint32_t s_req, s_frozen = BO3_GDS_GAME, s_state;   /* 0 planned */

static uint32_t g32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void p32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }

void bo3_gds_reset_for_tests(void) { s_req = 0; s_frozen = BO3_GDS_GAME; s_state = 0; }
uint32_t bo3_gds_frozen(void) { return s_frozen; }
uint32_t bo3_gds_state(void) { return s_state; }

int bo3_gds_request(uint32_t bytes, uint32_t *merged)
{
    int rc = BO3_GDS_OK;
    if (s_state != 0)
        rc = BO3_GDS_CLOSED;
#if MUT != 1
    else if (bytes % BO3_GDS_PAGE || bytes <= BO3_GDS_GAME || bytes > BO3_GDS_MAX)
        rc = BO3_GDS_OUT_OF_RANGE;
#endif
    else if (bytes > s_req)
        s_req = bytes;
    if (merged)
        *merged = s_req ? s_req : BO3_GDS_GAME;
    return rc;
}

int bo3_gds_apply_with(bo3_gds_guest_fn guest, bo3_gds_alloc_fn alloc, int build_ok)
{
    uint8_t *d1, *d2;
    uint32_t va, base;
    int rc;
    if (s_state != 0)
        return BO3_GDS_CLOSED;
    if (!s_req) {
        s_state = 1;
        fprintf(stderr, "[GAMEDATA] slot: the game's (0x%X, both layouts); no mod asked for more\n", (unsigned)BO3_GDS_GAME);
        return BO3_GDS_OK;
    }
    d1 = guest(BO3_GDS_DESC_L1, 16);
    d2 = guest(BO3_GDS_DESC_L2, 16);
    if (!build_ok)
        rc = BO3_GDS_UNSUPPORTED;
    else if (!d1 || !d2)
        rc = BO3_GDS_MISMATCH;
#if MUT != 2
    else if (g32(d1) != 0 || g32(d1 + 4) != 1u || g32(d1 + 8) != BO3_GDS_GAME || g32(d2) != 0 || g32(d2 + 4) != 2u ||
             g32(d2 + 8) != BO3_GDS_GAME || !(base = g32(d1 + 0xC)) || base % BO3_GDS_PAGE || g32(d2 + 0xC) != base)
        rc = BO3_GDS_MISMATCH;
#endif
    else if (!(va = alloc(s_req, BO3_GDS_PAGE)) || va % BO3_GDS_PAGE)
        rc = BO3_GDS_NO_MEMORY;
    else {
        base = g32(d1 + 0xC);
        p32(d1 + 8, s_req);
        p32(d1 + 0xC, va);
#if MUT != 3
        p32(d2 + 8, s_req);
        p32(d2 + 0xC, va);
#endif
        s_frozen = s_req;
        s_state = 2;
        fprintf(stderr, "[GAMEDATA] slot EXPANDED: one region of 0x%X at 0x%08X for both layouts (the game's 0x%X at 0x%08X "
                "stays unused)\n", (unsigned)s_req, (unsigned)va, (unsigned)BO3_GDS_GAME, (unsigned)base);
        return BO3_GDS_OK;
    }
    s_state = 3;
    fprintf(stderr, "[GAMEDATA] slot NOT expanded to 0x%X: %s; the game's 0x%X stays (the guard stops a track that needs more)\n",
            (unsigned)s_req, rc == BO3_GDS_UNSUPPORTED ? "unsupported game build" : rc == BO3_GDS_MISMATCH ?
            "descriptors 52 / 128 are not the expected table" : "the contiguous allocation was refused", (unsigned)BO3_GDS_GAME);
    return rc;
}

#ifdef BO3_STATIC_GAME
#include <stddef.h>
#include "bm_guest.h"
#include "kernel/xbox_memory_layout.h"
extern uint8_t *bo3_st_mapped_guest(void *user, uint32_t va, uint32_t size);
static uint8_t *gd_guest(uint32_t va, uint32_t size) { return bo3_st_mapped_guest(NULL, va, size); }
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
#endif
static uint32_t gd_alloc(uint32_t size, uint32_t align)
{
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    uint32_t va = xbox_ContiguousAllocHigh(size, align);   /* MEM256: the high zone */
#else
    uint32_t va = xbox_ContiguousAllocEx(size, align, 0, 0xFFFFFFFFu);
#endif
    if (!va)
        fprintf(stderr, "[GAMEDATA] the contiguous window refused 0x%X bytes (in use 0x%X, high-water 0x%X)\n", (unsigned)size,
                (unsigned)xbox_ContiguousInUseBytes(), (unsigned)xbox_ContiguousAllocatedBytes());
    return va;
}
static int gd_build_ok(void)
{
    static const struct { uint32_t va, word; } sig[] = { { 0x003B11A0u, 0x0018C470u }, { 0x003B11A4u, 0x0018C510u },
                                                         { 0x003A9ACCu, 0x00019FE0u }, { 0x003A9AD0u, 0x0001A000u } };
    for (size_t k = 0; k < sizeof sig / sizeof sig[0]; k++) {
        uint32_t w = 0;
        if (!bo3_guest_rd32(sig[k].va, &w) || w != sig[k].word)
            return 0;
    }
    return 1;
}
void bo3_gds_apply(void) { (void)bo3_gds_apply_with(gd_guest, gd_alloc, gd_build_ok()); }
#endif
