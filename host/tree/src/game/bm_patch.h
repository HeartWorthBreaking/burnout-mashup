/*
 * bm_patch.h - PLATFORM-HK EXPERIMENTAL: the private "bmashup.patch" service (include/bmashup_patch.h): verified byte
 * patches of the game's read-only data, at published sites (bm_patch_sites.h) or validated addresses, applied once when the
 * plugins' start ends. All guest access goes through bm_guest.c (the runtime's mappings). Contract:
 * research\native_gameplay_api\platform\hooks\CONTRACTS.md.
 */
#ifndef BO3_BM_PATCH_H
#define BO3_BM_PATCH_H

#include <stdint.h>

#include "bmashup_patch.h"

/* Identify the build (the XBE header the runtime mapped at 0x10000, its .rdata), verify the published sites, offer the
 * service, and ask bmashup.hooks for a LOAD_DONE host observer (the read-back). After xbox_MemoryLayoutInit and
 * bo3_bm_hooks_init, before bo3_plugins_init. */
void bo3_bm_patch_init(void);
/* Right after bo3_plugins_init (before the guest runs): requests close; the accepted patches are applied. */
void bo3_bm_patch_close(void);
const bm_patch_api *bo3_bm_patch_api(void);
/* The read-back the LOAD_DONE observer makes (for the unit test): patches found changed by this call. */
uint32_t bo3_patch_readback(void);

#endif
