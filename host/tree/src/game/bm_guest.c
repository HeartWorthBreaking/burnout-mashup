/* G8-E4 EXPERIMENTAL: guest memory access validated against the runtime's mappings (bm_guest.h). MUT=n (tests) compiles one
 * deliberate defect. */
#include "bm_guest.h"

#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

#define G_RAM_LO      0x00010000u
#define G_CONTIG_BASE 0x80000000u                /* kernel.h XBOX_CONTIG_BASE */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
/* MEM256: the build switch BO3_GUEST_WINDOW_MB gives the toolkit and this file the same XBOX_CONTIG_WINDOW_MB; the boot gate
 * (bm_memwin.c) also compares bo3_guest_window_bytes() with the runtime's xbox_ContiguousWindowBytes(). */
#define G_CONTIG_SIZE ((uint32_t)XBOX_CONTIG_WINDOW_MB << 20)   /* kernel.h XBOX_CONTIG_SIZE */
#else
#define G_CONTIG_SIZE 0x04000000u                /* kernel.h XBOX_CONTIG_SIZE */
#endif

extern ptrdiff_t g_xbox_mem_offset;
extern size_t xbox_GetMappedSize(void);          /* xbox_memory_layout.h */
extern uint32_t xbox_ContiguousBlockSize(uint32_t va);

static _Atomic uint32_t s_refused;

int bo3_guest_window(uint32_t va, uint32_t n)
{
    uint64_t end = (uint64_t)va + n;
    if (!g_xbox_mem_offset || n == 0)
        return BO3_GUEST_NONE;
#if MUT == 1
    if (va >= G_RAM_LO)
        return BO3_GUEST_RAM;                   /* defect: anything above 64 KB (NM1c's rule) */
#endif
    if (va >= G_RAM_LO && end <= (uint64_t)xbox_GetMappedSize())
        return BO3_GUEST_RAM;
    if (va >= G_CONTIG_BASE && end <= (uint64_t)G_CONTIG_BASE + G_CONTIG_SIZE) {
        uint32_t left = xbox_ContiguousBlockSize(va);
#if MUT == 2
        if (left)                               /* defect: the range's length not checked against the block */
#else
        if (left >= n)
#endif
            return BO3_GUEST_CONTIG;
    }
    return BO3_GUEST_NONE;
}

static void refuse(uint32_t va, uint32_t n)
{
    if (atomic_fetch_add(&s_refused, 1) < 8)
        fprintf(stderr, "[GUEST] refused: 0x%08X + %u is not inside mapped guest memory\n", (unsigned)va, (unsigned)n);
}

int bo3_guest_read(uint32_t va, void *out, uint32_t n)
{
    if (!bo3_guest_window(va, n)) {
        refuse(va, n);
        return 0;
    }
    memcpy(out, (const void *)((uintptr_t)g_xbox_mem_offset + va), n);
    return 1;
}

int bo3_guest_write(uint32_t va, const void *in, uint32_t n)
{
    if (!bo3_guest_window(va, n)) {
        refuse(va, n);
        return 0;
    }
    memcpy((void *)((uintptr_t)g_xbox_mem_offset + va), in, n);
    return 1;
}

int bo3_guest_rd32(uint32_t va, uint32_t *out)
{
    return bo3_guest_read(va, out, 4);
}

int bo3_guest_wr32(uint32_t va, uint32_t v)
{
    return bo3_guest_write(va, &v, 4);
}

uint32_t bo3_guest_refusals(void)
{
    return atomic_load(&s_refused);
}

#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
uint32_t bo3_guest_window_bytes(void)
{
    return G_CONTIG_SIZE;
}
#endif
