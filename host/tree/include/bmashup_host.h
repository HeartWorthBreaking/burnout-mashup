/*
 * bmashup_host.h - PLATFORM-P1: the Burnout Mashup host's identity for native plugins (Burnout Mashup private; plain C).
 *
 * 1. Service "bmashup.host" version 1: offered to every running plugin FIRST, before any other service (a plugin
 *    without takedawn_plugin_service is never asked anything, as before). The table says which platform this is and
 *    which services the host offers, so a plugin can tell a Burnout Mashup host from plain Takedawn and check its
 *    needs at once instead of waiting for offers that may never come.
 * 2. Optional plugin export takedawn_plugin_services_done: called once, on the main thread, right after the LAST service
 *    was offered to that plugin (also when the host offers none). From then on no service is offered to it: a service
 *    the plugin still lacks is missing on this host. Plain Takedawn hosts never call it (they know only
 *    takedawn_plugin_service): a plugin must still work without the call (bmsdk_report_once).
 *
 * Rules as takedawn_services.h: the table and every string it names are the host's, valid until the process ends; the
 * table only grows at its end (read only the fields struct_size covers).
 */
#ifndef BMASHUP_HOST_H
#define BMASHUP_HOST_H

#include <stdint.h>

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_HOST_SERVICE "bmashup.host"
#define BM_HOST_VERSION 1u

typedef struct bm_host_api {
    uint32_t struct_size;            /* sizeof (bm_host_api) as the host built it */
    uint32_t version;                /* BM_HOST_VERSION */
    /* The Burnout Mashup platform version ("0.1.0"; mod.toml [bmashup] platform = ">=0.1" is checked against it) and
     * its parts. */
    const char *platform_version;
    uint32_t platform_major, platform_minor, platform_patch;
    /* Takedawn's version (td_host_api.host_version) and the build ("<commit>[-label]"; "unknown" when not built from a
     * checkout). */
    const char *host_version;
    const char *build;
    /* The game image the host runs: bmashup.patch's build signature as 16 upper-case hex digits (FNV-1a 64 of the
     * mapped XBE header; retail NTSC-U "D0FC2EF4E9B2A86F"), "" when it could not be read. */
    const char *game_signature;
    /* The services this host offers to plugins, bmashup.host included (index 0), in offer order. service_at: 1 with
     * *name / *version set, 0 for an index past the end (or NULL arguments). service_version: the version offered under
     * that name, 0 when not offered. Any thread. */
    uint32_t (TD_CALL *service_count)(void);
    int32_t (TD_CALL *service_at)(uint32_t index, const char **name, uint32_t *version);
    uint32_t (TD_CALL *service_version)(const char *name);
} bm_host_api;

/* Optional plugin export: the end of the offers (above). offered = the services offered to this plugin (bmashup.host
 * included). */
typedef void (TD_CALL *td_plugin_services_done_fn)(const td_host_api *api, uint32_t offered);
#define TD_PLUGIN_SERVICES_DONE_SYMBOL "takedawn_plugin_services_done"

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_HOST_H */
