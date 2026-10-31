/*
 * bm_platform.h - PLATFORM-P1 (game build): the platform's boot log line and the start-time check of the service
 * registry against bm_platform_table.h (bm_platform.c). The mod-level checks (P-1 / P-2) are in modmanifest.c
 * (bo3_manifest_platform_check), called by modfs.c for every mod.
 */
#ifndef BO3_BM_PLATFORM_H
#define BO3_BM_PLATFORM_H

/* "[PLATFORM] Burnout Mashup platform 0.1.0 ..." - before bo3_modfs_init (whose refusals follow it). */
void bo3_platform_boot_log(void);
/* After bo3_bm_patch_init, before bo3_plugins_init: bmashup.host's build string and game signature (bmashup.patch's
 * build signature), logged. */
void bo3_platform_host_info(const char *build);
/* After every service was registered, before bo3_plugins_init: 1 when the registry equals the table (logged either
 * way). */
int bo3_platform_check_registry(void);

#endif
