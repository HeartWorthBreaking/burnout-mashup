/*
 * bmashup_memory.h - the "bmashup.memory" service: Burnout Mashup's private, experimental guest-memory blocks for native
 * plugins (Burnout Mashup builds only; may change or go away).
 *
 * A plugin may own small blocks of the GAME's memory (the guest heap) to hand to another Burnout Mashup service that the game
 * reads from - e.g. a track name for bmashup.names. The plugin never gets an address: it gets a handle and writes / reads
 * through the service, bounds-checked. A block reaches the game only through a host service that validates its contents and
 * then FREEZES it (no more writes: the game may read it at any time from then on).
 *
 * Contract (version 1):
 *   - size 16 .. 65536 bytes, 16-byte aligned, zero-filled; at most 1 MiB per plugin, 4 MiB in all; from the guest heap.
 *   - allocate only while Takedawn starts the plugins (takedawn_plugin_init / takedawn_plugin_service): the game has not
 *     started, so no game structure can point at a block that is not complete yet.
 *   - write / read: the owner only, on the plugin-start thread or the game thread; never after freeze (write) - reads stay.
 *   - lifetime: until the process ends; never freed, never moved (the game may hold the address).
 *   - errors are codes, never a crash; nothing of another plugin's blocks is reachable.
 */
#ifndef BMASHUP_MEMORY_H
#define BMASHUP_MEMORY_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_MEMORY_SERVICE "bmashup.memory"
#define BM_MEMORY_VERSION 1u

enum {
    BM_MEM_OK          = 0,
    BM_MEM_BAD_ARG     = 1,     /* no host / out, size out of 16 .. 65536, offset / length outside the block */
    BM_MEM_CLOSED      = 2,     /* allocation after the plugins' start */
    BM_MEM_NO_MEMORY   = 3,     /* the per-plugin / total budget or the guest heap is exhausted */
    BM_MEM_NOT_OWNER   = 4,     /* not this plugin's block (or no such handle) */
    BM_MEM_FROZEN      = 5,     /* handed to the game: read-only from now on */
    BM_MEM_UNAVAILABLE = 6      /* this build has no guest heap for plugins */
};

typedef uint32_t bm_mem_handle;     /* 0 = none */

typedef struct bm_mem_info {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t size;                  /* the block's bytes */
    uint32_t frozen;                /* 1 once a host service handed it to the game */
    uint32_t owner_used;            /* this plugin's bytes in all its blocks */
} bm_mem_info;

typedef struct bm_memory_api {
    uint32_t struct_size;
    uint32_t version;               /* BM_MEMORY_VERSION */
    int32_t (TD_CALL *alloc)(td_host *host, uint32_t size, bm_mem_handle *out);
    int32_t (TD_CALL *write)(td_host *host, bm_mem_handle h, uint32_t offset, const void *src, uint32_t n);
    int32_t (TD_CALL *read)(td_host *host, bm_mem_handle h, uint32_t offset, void *dst, uint32_t n);
    int32_t (TD_CALL *info)(td_host *host, bm_mem_handle h, bm_mem_info *out);
} bm_memory_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_MEMORY_H */
