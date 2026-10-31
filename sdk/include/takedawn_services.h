/*
 * takedawn_services.h - services Takedawn offers a native plugin
 * (docs/native-plugins.md, Services). Plain C, MIT, like the rest of Takedawn.
 *
 * A service is a named, versioned table of functions, for example
 * "takedawn.race" (takedawn_race.h). Services do not change the plugin API
 * (takedawn_plugin.h): a plugin that wants them exports one more function,
 * takedawn_plugin_service, and keeps api = 1 in its mod.toml. A plugin
 * without it is never asked anything.
 *
 * Rules:
 *   - Names are lower case, dotted: "takedawn.*" for Takedawn's own; other
 *     prefixes are a project's own.
 *   - Every table starts with uint32_t struct_size and uint32_t version, and
 *     only grows at its end: read only the fields your size covers.
 *   - A table and what it points to are Takedawn's, valid until the process
 *     ends.
 */
#ifndef TAKEDAWN_SERVICES_H
#define TAKEDAWN_SERVICES_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Optional plugin export. Called once for each service Takedawn offers, on
 * the main thread, right after takedawn_plugin_init returned TD_OK (the
 * plugin is running), in no set order. name: the service's name; version: the
 * highest version of it this Takedawn has; table: its table (struct_size and
 * version first). Return TD_OK when the plugin uses the service, anything else
 * when not (Takedawn only logs it). */
typedef int32_t (TD_CALL *td_plugin_service_fn)(const td_host_api *api, const char *name, uint32_t version,
                                                const void *table);

#define TD_PLUGIN_SERVICE_SYMBOL "takedawn_plugin_service"

#ifdef __cplusplus
}
#endif

#endif /* TAKEDAWN_SERVICES_H */
