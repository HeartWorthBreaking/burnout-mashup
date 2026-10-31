/* bm_memory.c - G8-E4 EXPERIMENTAL: "bmashup.memory" (include/bmashup_memory.h). Blocks come from the guest heap; every
 * access goes through bm_guest.c's mapping check as well as the block's own bounds. MUT=n (tests) compiles one defect. */
#include "bm_memory.h"

#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

#define MEM_BLOCKS     256
#define MEM_MIN        16u
#define MEM_MAX        65536u
#define MEM_PER_OWNER  (1024u * 1024u)
#define MEM_TOTAL      (4u * 1024u * 1024u)

static struct blk {
    const td_host *owner;
    uint32_t va, size;
    int frozen;
} s_b[MEM_BLOCKS];
static uint32_t s_n, s_total;
static int s_open = 1;
static bo3_mem_alloc_fn s_alloc;

void bo3_mem_configure(bo3_mem_alloc_fn alloc)
{
    s_alloc = alloc;
}

void bo3_bm_memory_close(void)
{
    s_open = 0;
}

static uint32_t used_by(const td_host *owner)
{
    uint32_t u = 0;
    for (uint32_t i = 0; i < s_n; i++)
        if (s_b[i].owner == owner)
            u += s_b[i].size;
    return u;
}

static struct blk *get(const td_host *owner, bm_mem_handle h)
{
    if (h == 0 || h > s_n)
        return NULL;
#if MUT == 1
    (void)owner;
    return &s_b[h - 1];                         /* defect: any plugin reaches any block */
#else
    return s_b[h - 1].owner == owner ? &s_b[h - 1] : NULL;
#endif
}

static int32_t TD_CALL m_alloc(td_host *host, uint32_t size, bm_mem_handle *out)
{
    uint32_t va, sz;
    if (!host || !out || size < MEM_MIN || size > MEM_MAX)
        return BM_MEM_BAD_ARG;
    *out = 0;
    if (!s_open)
        return BM_MEM_CLOSED;
    if (!s_alloc)
        return BM_MEM_UNAVAILABLE;
    sz = (size + 15u) & ~15u;
    if (s_n == MEM_BLOCKS || used_by(host) + sz > MEM_PER_OWNER || s_total + sz > MEM_TOTAL)
        return BM_MEM_NO_MEMORY;
    va = s_alloc(sz, 16u);
    if (!va || bo3_guest_window(va, sz) == BO3_GUEST_NONE)
        return BM_MEM_NO_MEMORY;
    {
        static const uint8_t zero[256];
        for (uint32_t o = 0; o < sz; o += sizeof zero)
            bo3_guest_write(va + o, zero, sz - o < sizeof zero ? sz - o : (uint32_t)sizeof zero);
    }
    s_b[s_n].owner = host;
    s_b[s_n].va = va;
    s_b[s_n].size = sz;
    s_b[s_n].frozen = 0;
    s_n++;
    s_total += sz;
    *out = s_n;
    return BM_MEM_OK;
}

static int in_bounds(const struct blk *b, uint32_t offset, uint32_t n)
{
#if MUT == 2
    (void)n;
    return offset < b->size;                    /* defect: the length not checked */
#else
    return n && offset <= b->size && n <= b->size - offset;
#endif
}

static int32_t TD_CALL m_write(td_host *host, bm_mem_handle h, uint32_t offset, const void *src, uint32_t n)
{
    struct blk *b = get(host, h);
    if (!host || !src)
        return BM_MEM_BAD_ARG;
    if (!b)
        return BM_MEM_NOT_OWNER;
#if MUT != 3
    if (b->frozen)
        return BM_MEM_FROZEN;
#endif
    if (!in_bounds(b, offset, n))
        return BM_MEM_BAD_ARG;
    return bo3_guest_write(b->va + offset, src, n) ? BM_MEM_OK : BM_MEM_BAD_ARG;
}

static int32_t TD_CALL m_read(td_host *host, bm_mem_handle h, uint32_t offset, void *dst, uint32_t n)
{
    struct blk *b = get(host, h);
    if (!host || !dst)
        return BM_MEM_BAD_ARG;
    if (!b)
        return BM_MEM_NOT_OWNER;
    if (!in_bounds(b, offset, n))
        return BM_MEM_BAD_ARG;
    return bo3_guest_read(b->va + offset, dst, n) ? BM_MEM_OK : BM_MEM_BAD_ARG;
}

static int32_t TD_CALL m_info(td_host *host, bm_mem_handle h, bm_mem_info *out)
{
    struct blk *b = get(host, h);
    bm_mem_info o;
    if (!host || !out || out->struct_size < 8)
        return BM_MEM_BAD_ARG;
    if (!b)
        return BM_MEM_NOT_OWNER;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.size = b->size;
    o.frozen = (uint32_t)b->frozen;
    o.owner_used = used_by(host);
    memcpy(out, &o, o.struct_size);
    return BM_MEM_OK;
}

static const bm_memory_api s_api = {(uint32_t)sizeof(bm_memory_api), BM_MEMORY_VERSION, m_alloc, m_write, m_read, m_info};

const bm_memory_api *bo3_bm_memory_api(void)
{
    return &s_api;
}

void bo3_bm_memory_init(void)
{
    bo3_plugins_service(BM_MEMORY_SERVICE, BM_MEMORY_VERSION, &s_api);
}

int bo3_mem_block(const td_host *owner, bm_mem_handle h, uint32_t *va, uint32_t *size)
{
    struct blk *b = get(owner, h);
    if (!b)
        return 0;
    *va = b->va;
    *size = b->size;
    return 1;
}

int bo3_mem_freeze(const td_host *owner, bm_mem_handle h)
{
    struct blk *b = get(owner, h);
    if (!b)
        return 0;
    b->frozen = 1;
    return 1;
}
