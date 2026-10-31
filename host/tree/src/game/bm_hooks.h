/*
 * bm_hooks.h - PLATFORM-HK EXPERIMENTAL: the private "bmashup.hooks" service (include/bmashup_hooks.h) over the existing,
 * verified marks: the car-update mark through the engine-point dispatcher (bm_events.h) and the lifecycle / takedown /
 * wreck / boost-award marks through bmashup.events' delivery (bm_events_service.h, one sink). Contract:
 * research\native_gameplay_api\platform\hooks\CONTRACTS.md.
 */
#ifndef BO3_BM_HOOKS_H
#define BO3_BM_HOOKS_H

#include <stdint.h>

#include "bmashup_hooks.h"

/* Offer the service (bo3_plugins_service) and attach to bmashup.events' delivery. Before bo3_plugins_init, after
 * bo3_bm_events_init (and so after bo3_bm_autopilot_init, which hooks the car update). */
void bo3_bm_hooks_init(void);
/* Right after bo3_plugins_init and BEFORE bo3_events_close: registration closes; the car-update registrations (if any) are
 * attached to the dispatcher (after every bmashup.events observer); dispatch stops when the process starts to exit. */
void bo3_bm_hooks_close(void);
const bm_hooks_api *bo3_bm_hooks_api(void);

/* Host consumers (another host service, e.g. bm_patch.c): an observer of `point` that is not a plugin registration (no
 * ownership, no exclusivity, called after the plugins' observers, same register guard). While registration is open.
 * 0 done, -1 refused. */
typedef void (*bo3_hk_host_fn)(const bm_hook_ctx *ctx, void *user);
int bo3_hk_host_observe(uint32_t point, bo3_hk_host_fn fn, void *user);

/* Stop dispatching (at exit; for the unit test). */
void bo3_hk_stop(void);

/* ---- main19: bmashup.hooks v3 (points 8..13, hook request P2 / P3) ----
 * BO3_HOOKREQ_P23 (CMake option, default ON = 1): 0 = every P2 / P3 point stays UNAVAILABLE (bo3_hk_offer_point refuses). */
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 1
#endif
/* An item's init (before bo3_plugins_init) offers its point once its mark is compiled in and its start-time check of the game's
 * bytes passed: roles = (1 << BM_HOOK_OBSERVE) | (1 << BM_HOOK_MODIFY) as offered; valid = the item's own check of a proposed
 * output after the framework's bounds (NULL: bounds only; return 1 = accept). The events twin (8, 10, 11, 12) is offered with it.
 * 0 done; -1 refused (BO3_HOOKREQ_P23 == 0, not a v3 point, a role the point does not have, registration closed). */
typedef int (*bo3_hk_valid_fn)(const bm_hook_ctx *ctx, const bm_hook_out *proposed);
int bo3_hk_offer_point(uint32_t point, uint32_t roles, bo3_hk_valid_fn valid);
int bo3_hk_point_available(uint32_t point);
/* 1 when a registration, an events twin subscriber or a host observer waits for the point (an item may skip building its ctx). */
int bo3_hk_point_wanted(uint32_t point);
/* A v3 ctx with the common fields set (struct_size, point, racer fields BM_HOOK_NO_RACER); the item fills its group. */
void bo3_hk_ctx_v3(bm_hook_ctx *ctx, uint32_t point);
/* One occurrence of a v3 point (the item's mark, the game's thread). ctx: the item's values (sequence / step / role are set
 * here); res: the game's output with res->output = the point's BM_HOOK_OUT_* (NULL for HUD_PASS). Order: MODIFY callbacks
 * (priority order, each sees the value so far; a proposal outside the framework's bounds or refused by the item's check is
 * ignored and counted), then bmashup.events v7's twin observers (with the final output), the hooks observers, the host
 * observers. Returns 1 when *res changed. Not dispatched: stopped, re-entered, or not offered (returns 0, res unchanged). */
int bo3_hk_dispatch_v3(uint32_t point, const bm_hook_ctx *ctx, bm_hook_out *res);
/* main19 (item 39): the MODIFY step of a v3 point alone (no events twin, no observers; the occurrence is not counted as one of
 * the point's occurrences): for a MODIFY whose moment is not the point's observed occurrence (WRECK_CAUSE credit: asked when the
 * victim wrecks, observed when the game counts the takedown). Returns 1 when *res changed. */
int bo3_hk_modify_v3(uint32_t point, const bm_hook_ctx *ctx, bm_hook_out *res);
int bo3_hk_point_modifiers(uint32_t point);        /* MODIFY registrations at the point (0 when not offered) */
/* The framework's bounds of a proposed output (exported for the items' tests): 1 = inside. */
int bo3_hk_out_in_bounds(uint32_t point, const bm_hook_ctx *ctx, const bm_hook_out *res);

#endif
