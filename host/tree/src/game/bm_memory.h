/* bm_memory.h - G8-E4 EXPERIMENTAL: the "bmashup.memory" service (include/bmashup_memory.h) and the host side other
 * Burnout Mashup services use to take a plugin's block (validate, then freeze, then hand its guest address to the game). */
#ifndef BO3_BM_MEMORY_H
#define BO3_BM_MEMORY_H

#include <stdint.h>

#include "bmashup_memory.h"

typedef uint32_t (*bo3_mem_alloc_fn)(uint32_t size, uint32_t align);   /* guest VA or 0 (the game build: xbox_HeapAlloc) */
void bo3_mem_configure(bo3_mem_alloc_fn alloc);
void bo3_bm_memory_init(void);                     /* offers the service (before bo3_plugins_init) */
void bo3_bm_memory_close(void);                    /* after bo3_plugins_init: no allocation from now on */
const bm_memory_api *bo3_bm_memory_api(void);

/* host services: the block of `h` owned by `owner`: its guest address and size; 1, or 0 (no such block / another owner) */
int bo3_mem_block(const td_host *owner, bm_mem_handle h, uint32_t *va, uint32_t *size);
/* host services: from now on the block is read-only (the game may read it); 1, or 0 */
int bo3_mem_freeze(const td_host *owner, bm_mem_handle h);

#endif
