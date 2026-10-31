/*
 * bm_guest.h - G8-E4 EXPERIMENTAL: host access to guest memory, validated against the runtime's own mappings.
 *
 * The runtime (xboxrecomp, xbox_memory_layout.c) maps guest memory in separate windows, each at guest address + the
 * offset (the generated code's MEM32): main RAM from 0x10000 to xbox_GetMappedSize(), and the contiguous window at
 * XBOX_CONTIG_BASE (0x80000000, 64 MB), whose pages are only meaningful inside a block the contiguous allocator handed out
 * (xbox_ContiguousBlockSize > 0). A host module that follows a pointer it read from guest memory checks the WHOLE range
 * [va, va + n) against those mappings before touching it:
 *   - main RAM: 0x10000 <= va and va + n <= xbox_GetMappedSize();
 *   - contiguous: va inside an allocated block and n <= the bytes from va to the block's end;
 *   - anything else (unmapped, the GPU / MCPX / flash apertures, the tiled view, page 0, a range that crosses a window's
 *     end): refused.
 * No folding of high addresses onto low RAM and no "anything above 64 KB": NM1 launches 30 / 31 showed both fail (the language
 * table lives at 0x80182000, a contiguous block, which is its own storage).
 * The two runtime queries are the runtime's exported functions (xbox_memory_layout.h); tests provide their own.
 */
#ifndef BO3_BM_GUEST_H
#define BO3_BM_GUEST_H

#include <stddef.h>
#include <stdint.h>

enum { BO3_GUEST_NONE = 0, BO3_GUEST_RAM = 1, BO3_GUEST_CONTIG = 2 };

/* which window holds [va, va + n) entirely, or BO3_GUEST_NONE */
int bo3_guest_window(uint32_t va, uint32_t n);
/* reads / writes through the window check; 1 done, 0 refused (nothing read / written) */
int bo3_guest_read(uint32_t va, void *out, uint32_t n);
int bo3_guest_write(uint32_t va, const void *in, uint32_t n);
int bo3_guest_rd32(uint32_t va, uint32_t *out);
int bo3_guest_wr32(uint32_t va, uint32_t v);
uint32_t bo3_guest_refusals(void);                           /* refused accesses (logged once each kind) */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
uint32_t bo3_guest_window_bytes(void);                       /* MEM256: the contiguous window this file checks against */
#endif

#endif
