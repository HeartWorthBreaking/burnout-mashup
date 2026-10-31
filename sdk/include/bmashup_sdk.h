/*
 * bmashup_sdk.h - Burnout Mashup modding SDK 0.6.0 (header only, plain C, Windows x64 built and tested).
 *
 * What it adds to the host's own headers (which are byte copies of the reference host's, see HEADERS_FROM_MAIN19.txt):
 *   1. the SDK's version (BMSDK_VERSION_*);
 *   2. the catalogue of the services the bundled headers describe, each with the version and table size those headers
 *      have (bmsdk_catalogue; bmashup.host first, as the host offers it);
 *   3. a discovery / capability-check helper (bmsdk_need, bmsdk_offer, bmsdk_describe, bmsdk_report) and field-presence
 *      macros for the append-only structs (BMSDK_HAS_FIELD);
 *   4. (0.2.0) the platform host's identity and end of offers: bmsdk_host, bmsdk_host_offers, bmsdk_host_missing,
 *      bmsdk_services_done and BMSDK_DEFINE_SERVICES_DONE (bmashup_host.h).
 *   5. (0.4.0) the p4 host (platform 0.1.3): six more services in the catalogue (bmashup.vphysics 1, bmashup.crash 1,
 *      bmashup.traffic 1, bmashup.ai 1, bmashup.settings 1, bmashup.camera 1), bmashup.autopilot 2, bmashup.events 6
 *      (CRASH_RESULT; bm_event grows 84 -> 128 bytes: read the v6 fields only when BMSDK_HAS_FIELD(ev, bm_event,
 *      track_id)), a registry of 32. Plugins built with 0.3.0 headers bind unchanged (append-only structs).
 *   6. (0.4.1) the p4.1 host (platform 0.1.4): bmashup.tune 3 (73 AI values, signed entries; bm_tune_info grows 184 -> 200:
 *      read min / is_signed / applies only when BMSDK_HAS_FIELD(info, bm_tune_info, applies)).
 *   7. (0.4.2) the p4.2 host (platform 0.1.5): no ABI change. bmashup_vphysics.h documents that the writable value
 *      "Max Speed In Boost" is the car's TOP-SPEED LIMIT (it caps the normal top speed as well as boost; measured).
 *   8. (0.5.0) the main18 host (platform 0.1.8; hook request phase 1 + the mod limits). Seven services grow a version
 *      (append-only: every v1 table / struct is a prefix of v2): bmashup.boost 2 (award), bmashup.racers 2 (place / order /
 *      session), bmashup.traffic 2 (set_density_v2, up to 3.0, EXPERIMENTAL above 2.0), bmashup.vphysics 2 (vehicle
 *      query), bmashup.patch 2 (TABLE sites, request_site_pair), bmashup.hooks 2 (point 7 CRASH_RESULT; bm_hook_ctx grows),
 *      bmashup.settings 2 (PER_PLAYER scope, subscribe2, get_player); two NEW services: bmashup.hud 1 (HUD element
 *      transforms) and bmashup.input 1 (read-only pad snapshot). 22 services in the catalogue. Plugins built with 0.4.x
 *      headers bind unchanged; use a v2 function only when bmsdk_has(w, 2) and the table covers it (BMSDK_*_TABLE_V2).
 *   9. (0.6.0) the main19 host (platform 0.1.9 = main18 + the 256 MB guest window (mem256) + hook request phases 2 and 3).
 *      Grown (append-only): bmashup.racers 3, bmashup.vphysics 3 (gearbox), bmashup.traffic 3, bmashup.hooks 3 (points
 *      8..13; bm_hook_ctx / bm_hook_out grow, the table does not), bmashup.events 7 (twins of the new points; bm_event grows),
 *      bmashup.camera 2, bmashup.hud 2; NEW: bmashup.paints 1, bmashup.menu 1, bmashup.rules 1 - 25 services. Several new
 *      functions answer UNAVAILABLE on the 0.1.9 host until a runtime probe verifies their site (each service page says
 *      which); always check the function's result / the service's availability call, never assume a v3 table means the
 *      feature works. Plugins built with 0.5.0 headers bind unchanged.
 *
 * DISCOVERY - the host's real mechanism, and the only one this helper uses (src/game/plugins.c offer_services):
 *   the host calls the plugin's optional export takedawn_plugin_service(api, name, version, table) once for each service
 *   it has, on the main thread, right after takedawn_plugin_init returned TD_OK; `version` is the highest version of that
 *   service the host has, `table` starts with uint32_t struct_size, uint32_t version. The return value only decides the
 *   host's log line ("[PLUGIN] <id>: service <name> <version>: used" / "not used").
 *   A Burnout Mashup platform host (0.1.0 and later, e.g. burnout3_bmp_p3.exe) also
 *     - offers "bmashup.host" FIRST (bmashup_host.h): the platform version, the build, and the list of every service it
 *       will offer (service_version(name)), so a plugin knows at the first offer what it will and will not get;
 *     - calls the optional export takedawn_plugin_services_done(api, offered) once, right after the LAST offer.
 *   Older hosts (plain Takedawn, Burnout Mashup builds before platform 0.1) do neither: there "missing" is known only
 *   after the start. So:
 *     - "too old" is known at the offer: bmsdk_offer marks it, bmsdk_log_need says it at once;
 *     - "missing" is said by bmsdk_services_done (platform hosts: during the start, at the end of the offers), else the
 *       first time the plugin runs again (its first event, its first use of a feature) and, as the last resort, from
 *       on_shutdown (bmsdk_report_once: the plugin's flag makes it once in all three places). A missing service also
 *       shows in the host's log as the absence of its "service ...: used" line for this mod.
 *
 * GRACEFUL DEGRADE pattern:
 *     static bmsdk_need s_need[] = { BMSDK_NEED(BM_EVENTS_SERVICE, 2, BMSDK_EVENTS_TABLE_V2, 1) };
 *     static int s_reported;
 *     takedawn_plugin_service(...): bmsdk_need *w = bmsdk_offer(s_need, 1, name, version, table);
 *                                   if (!w) return 1;                               not one this plugin uses
 *                                   if (w->state != BMSDK_BOUND) { bmsdk_log_need(api, w); s_reported = 1; return 1; }
 *                                   use the features of version 2; those of 3 / 4 only when bmsdk_has(w, 3) / (w, 4)
 *     BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)                                missing: said at the end of the offers
 *     each event:   read a field only when BMSDK_HAS_FIELD(ev, bm_event, field)
 *     later / on_shutdown:  bmsdk_report_once(api, s_need, 1, &s_reported)          older hosts: missing / too old, once
 *
 * DIAGNOSTIC TEXT (bmsdk_describe; logged with the prefix "bmashup-sdk: " by bmsdk_log_need / bmsdk_report) - unchanged
 * since 0.1.0:
 *   bound    "<name>: ok (version <V>, table <T> bytes)"
 *   missing  "<name>: missing: this host did not offer it; this mod needs version <M> or later" + <tail>
 *   too old  "<name>: too old: this host offers version <V> with a <T>-byte table; this mod needs version <M> or later with a
 *             table of at least <S> bytes" + <tail>
 *   failed   "<name>: offered (version <V>) but not usable: the service answered <C>" + <tail>
 *   <tail>   "; required: this mod does nothing without it" or "; optional: the features that need it are off"
 *
 * Nothing here allocates, keeps a pointer into the game, or calls the host except api->log and (when offered) the
 * bmashup.host table's functions. Not thread-safe: use it from takedawn_plugin_init / takedawn_plugin_service /
 * takedawn_plugin_services_done (the main thread) and from the plugin's own callbacks. The host-identity state is kept
 * per source file (static): call bmsdk_offer / bmsdk_services_done / bmsdk_host from ONE source file of the plugin.
 */
#ifndef BMASHUP_SDK_H
#define BMASHUP_SDK_H

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "takedawn_plugin.h"
#include "takedawn_services.h"
#include "takedawn_race.h"
#include "bmashup_autopilot.h"
#include "bmashup_boost.h"
#include "bmashup_engine.h"
#include "bmashup_events.h"
#include "bmashup_hooks.h"
#include "bmashup_host.h"
#include "bmashup_memory.h"
#include "bmashup_names.h"
#include "bmashup_patch.h"
#include "bmashup_racers.h"
#include "bmashup_route.h"
#include "bmashup_streaming.h"
#include "bmashup_tune.h"
#include "bmashup_vphysics.h"
#include "bmashup_crash.h"
#include "bmashup_traffic.h"
#include "bmashup_ai.h"
#include "bmashup_settings.h"
#include "bmashup_camera.h"
#include "bmashup_hud.h"       /* 0.5.0 */
#include "bmashup_input.h"     /* 0.5.0 */
#include "bmashup_paints.h"    /* 0.6.0 */
#include "bmashup_menu.h"      /* 0.6.0 */
#include "bmashup_rules.h"     /* 0.6.0 */

#ifdef __cplusplus
extern "C" {
#endif

/* ---- the SDK's own version (VERSIONING.md: semver; independent of the service versions) ---- */
#define BMSDK_VERSION_MAJOR  0
#define BMSDK_VERSION_MINOR  6
#define BMSDK_VERSION_PATCH  0
#define BMSDK_VERSION_STRING "0.7.0"
#define BMSDK_VERSION_NUMBER (BMSDK_VERSION_MAJOR * 10000 + BMSDK_VERSION_MINOR * 100 + BMSDK_VERSION_PATCH)
/* The host the bundled headers were copied from and the SDK was verified against (offline). */
#define BMSDK_REFERENCE_HOST "burnout3_gp_main21.exe sha256 f0b9c8a9bf3baa7ed41703569a23236efd2b7e503fdbf6a73cf8c0d3d5f27656"
/* Its build identity (bmashup.host `build`, the boot log, burnout3.exe --version): "bmp-<platform>+<12 hex of the source
 * digest>". The same sources and toolchain give the same identity and the same exe; the platform version stays the
 * compatibility contract - compare the identity only to require one exact build. */
#define BMSDK_REFERENCE_BUILD "bmp-0.1.9+2c8142e65f20"
/* The Burnout Mashup platform version of the reference host (bmashup.host platform_version; mod.toml [bmashup]). */
#define BMSDK_REFERENCE_PLATFORM "0.1.9"
/* The plugin API a mod.toml declares ([plugin] api = 1): takedawn_plugin.h's TD_PLUGIN_API_VERSION. */
#define BMSDK_PLUGIN_API     TD_PLUGIN_API_VERSION
/* The host offers at most this many REGISTERED services (plugins.c MAX_SERVICES; bmashup.host is not in the registry);
 * the reference host offers BMSDK_SERVICE_COUNT in all: bmashup.host + 19 registered (p4; p3: 16 / 14). */
#define BMSDK_HOST_MAX_SERVICES 32u
#define BMSDK_SERVICE_COUNT     25u   /* 0.5.0: + bmashup.hud, bmashup.input; 0.6.0: + bmashup.paints, .menu, .rules */

/* mod.toml capacity declarations ([bmashup.capacity], read by the host itself, no plugin; examples/capacity):
 * version = 1, lanes (1..255 total AI route lanes), low_unit_bytes (a 4 KiB multiple 0x18000..0x30000), static_bytes (a
 * 4 KiB multiple above 0xA00000, at most 0x20C4000). The same checks as the plugin requests of bmashup.engine /
 * bmashup.streaming; largest wins; a requirement the host cannot meet stops the start (exit 91) naming the mod. */
#define BMSDK_CAPACITY_TABLE   "bmashup.capacity"
#define BMSDK_CAPACITY_VERSION 1

/* ---- append-only structs: which fields the other side has ---- */
/* The byte just past `field` of `type`: a struct_size at least this large has the field. */
#define BMSDK_FIELD_END(type, field) ((uint32_t)(offsetof(type, field) + sizeof(((type *)0)->field)))
/* p->struct_size covers `field` (p: a pointer to `type`, or NULL). */
#define BMSDK_HAS_FIELD(p, type, field) ((p) != NULL && (p)->struct_size >= BMSDK_FIELD_END(type, field))

/* Table sizes by service version, for bmsdk_need.min_table (what a plugin built for that version reads). */
#define BMSDK_TABLE_MIN                8u                                              /* struct_size + version */
#define BMSDK_EVENTS_TABLE_V1          BMSDK_FIELD_END(bm_events_api, stats)           /* versions 1 .. 4: subscribe, stats */
#define BMSDK_EVENTS_TABLE_V2          BMSDK_EVENTS_TABLE_V1
#define BMSDK_EVENTS_TABLE_V5          BMSDK_FIELD_END(bm_events_api, subscribe_modifier)
#define BMSDK_EVENTS_TABLE_V6          BMSDK_EVENTS_TABLE_V5                           /* 0.4.0: the table is unchanged */
#define BMSDK_EVENT_SIZE_V6            BMSDK_FIELD_END(bm_event, track_id)             /* 0.4.0: 128 */
#define BMSDK_AUTOPILOT_TABLE_V2       ((uint32_t)sizeof(bm_autopilot_api))            /* 0.4.0 */
#define BMSDK_TUNE_INFO_V3             BMSDK_FIELD_END(bm_tune_info, applies)          /* 0.4.1: 200 */
#define BMSDK_STREAMING_TABLE_V1       BMSDK_FIELD_END(bm_streaming_api, lowslot_info)
#define BMSDK_STREAMING_TABLE_V2       BMSDK_FIELD_END(bm_streaming_api, static_info)
#define BMSDK_MEMORY_TABLE_V1          BMSDK_FIELD_END(bm_memory_api, info)
#define BMSDK_NAMES_TABLE_V1           BMSDK_FIELD_END(bm_names_api, set_text)
#define BMSDK_ENGINE_TABLE_V1          BMSDK_FIELD_END(bm_engine_api, lanes_info)
#define BMSDK_HOOKS_TABLE_V1           BMSDK_FIELD_END(bm_hooks_api, result_text)       /* 0.2.0 */
#define BMSDK_PATCH_TABLE_V1           BMSDK_FIELD_END(bm_patch_api, result_text)       /* 0.2.0 */
#define BMSDK_HOST_TABLE_V1            BMSDK_FIELD_END(bm_host_api, service_version)    /* 0.2.0 */
/* 0.5.0 (platform 0.1.8): the versions 2 and the two new services */
#define BMSDK_BOOST_TABLE_V1           BMSDK_FIELD_END(bm_boost_api, status)
#define BMSDK_BOOST_TABLE_V2           BMSDK_FIELD_END(bm_boost_api, award_status)      /* 0.5.0 */
#define BMSDK_RACERS_TABLE_V1          BMSDK_FIELD_END(bm_racers_api, get)
#define BMSDK_RACERS_TABLE_V2          BMSDK_FIELD_END(bm_racers_api, session)          /* 0.5.0 */
#define BMSDK_RACER_INFO_V2            BMSDK_FIELD_END(bm_racer_info, eliminated)       /* 0.5.0: 52 */
#define BMSDK_TRAFFIC_TABLE_V1         BMSDK_FIELD_END(bm_traffic_api, reset)
#define BMSDK_TRAFFIC_TABLE_V2         BMSDK_FIELD_END(bm_traffic_api, set_density_v2)  /* 0.5.0 */
#define BMSDK_TRAFFIC_STATUS_V2        BMSDK_FIELD_END(bm_traffic_status, experimental) /* 0.5.0: 60 */
#define BMSDK_VPHYS_TABLE_V1           BMSDK_FIELD_END(bm_vphys_api, status)
#define BMSDK_VPHYS_TABLE_V2           BMSDK_FIELD_END(bm_vphys_api, vehicle_value)     /* 0.5.0 */
#define BMSDK_HOOKS_TABLE_V2           BMSDK_HOOKS_TABLE_V1                             /* 0.5.0: the table is unchanged */
#define BMSDK_HOOK_CTX_V2              BMSDK_FIELD_END(bm_hook_ctx, crash_track_id)     /* 0.5.0 */
#define BMSDK_PATCH_TABLE_V2           BMSDK_FIELD_END(bm_patch_api, request_site_pair) /* 0.5.0 */
#define BMSDK_PATCH_SITE_INFO_V2       BMSDK_FIELD_END(bm_patch_site_info, meaning)     /* 0.5.0 */
#define BMSDK_SETTINGS_TABLE_V1        BMSDK_FIELD_END(bm_settings_api, get)
#define BMSDK_SETTINGS_TABLE_V2        BMSDK_FIELD_END(bm_settings_api, get_player)     /* 0.5.0 */
#define BMSDK_SETTING_DECL_V2          BMSDK_FIELD_END(bm_setting_decl, scope)          /* 0.5.0 */
#define BMSDK_HUD_TABLE_V1             BMSDK_FIELD_END(bm_hud_api, element_available)   /* 0.5.0: new service */
#define BMSDK_INPUT_TABLE_V1           BMSDK_FIELD_END(bm_input_api, pad)               /* 0.5.0: new service */
/* 0.6.0 (platform 0.1.9): hook request phases 2 + 3 */
#define BMSDK_RACERS_TABLE_V3          BMSDK_FIELD_END(bm_racers_api, result_text)      /* 0.6.0 */
#define BMSDK_RACER_INFO_V3            BMSDK_FIELD_END(bm_racer_info, controls_owned)   /* 0.6.0 */
#define BMSDK_VPHYS_TABLE_V3           BMSDK_FIELD_END(bm_vphys_api, gearbox_status)    /* 0.6.0 */
#define BMSDK_TRAFFIC_TABLE_V3         BMSDK_FIELD_END(bm_traffic_api, clear_wrecked)   /* 0.6.0 */
#define BMSDK_TRAFFIC_STATUS_V3        BMSDK_FIELD_END(bm_traffic_status, pool_refusals) /* 0.6.0: 72 */
#define BMSDK_HOOKS_TABLE_V3           BMSDK_HOOKS_TABLE_V1                             /* 0.6.0: the table is unchanged */
#define BMSDK_HOOK_CTX_V3              BMSDK_FIELD_END(bm_hook_ctx, sound_event)        /* 0.6.0 */
#define BMSDK_HOOK_OUT_V3              BMSDK_FIELD_END(bm_hook_out, pose_fov_scale)     /* 0.6.0 */
#define BMSDK_EVENTS_TABLE_V7          BMSDK_EVENTS_TABLE_V6                            /* 0.6.0: the table is unchanged */
#define BMSDK_EVENT_SIZE_V7            BMSDK_FIELD_END(bm_event, sound_level)           /* 0.6.0 */
#define BMSDK_CAMERA_TABLE_V1          BMSDK_FIELD_END(bm_camera_api, state)
#define BMSDK_CAMERA_TABLE_V2          BMSDK_FIELD_END(bm_camera_api, set_finish_poses) /* 0.6.0 */
#define BMSDK_HUD_TABLE_V2             BMSDK_FIELD_END(bm_hud_api, draw_available)      /* 0.6.0 */
#define BMSDK_PAINTS_TABLE_V1          BMSDK_FIELD_END(bm_paints_api, status)           /* 0.6.0: new service */
#define BMSDK_MENU_TABLE_V1            BMSDK_FIELD_END(bm_menu_api, feature_available)  /* 0.6.0: new service */
#define BMSDK_RULES_TABLE_V1           BMSDK_FIELD_END(bm_rules_api, status)            /* 0.6.0: new service */

/* ---- the catalogue: every service the bundled headers describe, in the reference host's offer order (p4) ---- */
typedef struct bmsdk_service_info {
    const char *name;           /* the service's name, as offered */
    uint32_t version;           /* the version the bundled header describes (= the reference host's) */
    uint32_t table_size;        /* sizeof its table in the bundled header */
    const char *header;         /* the header that describes it */
} bmsdk_service_info;

static inline const bmsdk_service_info *bmsdk_catalogue(uint32_t *count)
{
    static const bmsdk_service_info k[] = {
        {BM_HOST_SERVICE,      BM_HOST_VERSION,      (uint32_t)sizeof(bm_host_api),      "bmashup_host.h"},
        {TD_RACE_SERVICE,      TD_RACE_VERSION,      (uint32_t)sizeof(td_race_api),      "takedawn_race.h"},
        {BM_AUTOPILOT_SERVICE, BM_AUTOPILOT_VERSION, (uint32_t)sizeof(bm_autopilot_api), "bmashup_autopilot.h"},
        {BM_BOOST_SERVICE,     BM_BOOST_VERSION,     (uint32_t)sizeof(bm_boost_api),     "bmashup_boost.h"},
        {BM_VPHYS_SERVICE,     BM_VPHYS_VERSION,     (uint32_t)sizeof(bm_vphys_api),     "bmashup_vphysics.h"},
        {BM_EVENTS_SERVICE,    BM_EVENTS_VERSION,    (uint32_t)sizeof(bm_events_api),    "bmashup_events.h"},
        {BM_HOOKS_SERVICE,     BM_HOOKS_VERSION,     (uint32_t)sizeof(bm_hooks_api),     "bmashup_hooks.h"},
        {BM_PATCH_SERVICE,     BM_PATCH_VERSION,     (uint32_t)sizeof(bm_patch_api),     "bmashup_patch.h"},
        {BM_MEMORY_SERVICE,    BM_MEMORY_VERSION,    (uint32_t)sizeof(bm_memory_api),    "bmashup_memory.h"},
        {BM_NAMES_SERVICE,     BM_NAMES_VERSION,     (uint32_t)sizeof(bm_names_api),     "bmashup_names.h"},
        {BM_RACERS_SERVICE,    BM_RACERS_VERSION,    (uint32_t)sizeof(bm_racers_api),    "bmashup_racers.h"},
        {BM_CRASH_SERVICE,     BM_CRASH_VERSION,     (uint32_t)sizeof(bm_crash_api),     "bmashup_crash.h"},
        {BM_ENGINE_SERVICE,    BM_ENGINE_VERSION,    (uint32_t)sizeof(bm_engine_api),    "bmashup_engine.h"},
        {BM_STREAMING_SERVICE, BM_STREAMING_VERSION, (uint32_t)sizeof(bm_streaming_api), "bmashup_streaming.h"},
        {BM_ROUTE_SERVICE,     BM_ROUTE_VERSION,     (uint32_t)sizeof(bm_route_api),     "bmashup_route.h"},
        {BM_TUNE_SERVICE,      BM_TUNE_VERSION,      (uint32_t)sizeof(bm_tune_api),      "bmashup_tune.h"},
        {BM_TRAFFIC_SERVICE,   BM_TRAFFIC_VERSION,   (uint32_t)sizeof(bm_traffic_api),   "bmashup_traffic.h"},
        {BM_AI_SERVICE,        BM_AI_VERSION,        (uint32_t)sizeof(bm_ai_api),        "bmashup_ai.h"},
        {BM_SETTINGS_SERVICE,  BM_SETTINGS_VERSION,  (uint32_t)sizeof(bm_settings_api),  "bmashup_settings.h"},
        {BM_CAMERA_SERVICE,    BM_CAMERA_VERSION,    (uint32_t)sizeof(bm_camera_api),    "bmashup_camera.h"},
        {BM_HUD_SERVICE,       BM_HUD_VERSION,       (uint32_t)sizeof(bm_hud_api),       "bmashup_hud.h"},
        {BM_INPUT_SERVICE,     BM_INPUT_VERSION,     (uint32_t)sizeof(bm_input_api),     "bmashup_input.h"},
        {BM_PAINTS_SERVICE,    BM_PAINTS_VERSION,    (uint32_t)sizeof(bm_paints_api),    "bmashup_paints.h"},
        {BM_MENU_SERVICE,      BM_MENU_VERSION,      (uint32_t)sizeof(bm_menu_api),      "bmashup_menu.h"},
        {BM_RULES_SERVICE,     BM_RULES_VERSION,     (uint32_t)sizeof(bm_rules_api),     "bmashup_rules.h"},
    };
    if (count)
        *count = (uint32_t)(sizeof k / sizeof k[0]);
    return k;
}

/* The catalogue entry of `name`, or NULL (a service these headers do not describe). */
static inline const bmsdk_service_info *bmsdk_catalogue_find(const char *name)
{
    uint32_t n = 0;
    const bmsdk_service_info *k = bmsdk_catalogue(&n);
    for (uint32_t i = 0; name && i < n; i++)
        if (!strcmp(k[i].name, name))
            return &k[i];
    return NULL;
}

/* ---- discovery / capability check ---- */
enum {
    BMSDK_MISSING = 0,          /* not offered (yet: until the end of the offers, this is all the plugin can know) */
    BMSDK_BOUND   = 1,          /* offered at min_version or later with a table of at least min_table bytes: table set */
    BMSDK_TOO_OLD = 2,          /* offered, but an older version or a smaller table: table NULL */
    BMSDK_FAILED  = 3           /* bound, but the plugin's first call was refused (bmsdk_fail): table kept, code says */
};

typedef struct bmsdk_need {
    /* in */
    const char *name;           /* e.g. BM_EVENTS_SERVICE */
    uint32_t min_version;       /* the oldest version this plugin works with */
    uint32_t min_table;         /* the table bytes this plugin reads at min_version (BMSDK_*_TABLE_*; below 8 means 8) */
    int required;               /* 1: the mod does nothing without it; 0: optional features */
    /* out (bmsdk_offer / bmsdk_fail) */
    int state;                  /* BMSDK_* */
    uint32_t offered_version;   /* the version the host offered (0: not offered) */
    uint32_t offered_table;     /* the offered table's struct_size */
    const void *table;          /* the table when BOUND / FAILED, else NULL */
    int32_t code;               /* FAILED: the service's answer */
} bmsdk_need;

#define BMSDK_NEED(name, min_version, min_table, required) \
    { (name), (min_version), (min_table), (required), BMSDK_MISSING, 0u, 0u, NULL, 0 }

/* ---- 0.2.0: what this source file learnt about the host (bmashup.host, end of offers) ---- */
typedef struct bmsdk_host_state {
    const bm_host_api *host;    /* the bmashup.host table, when the host offered a usable one (else NULL) */
    uint32_t offers_seen;       /* bmsdk_offer calls so far (= offers, when the plugin passes every offer to it) */
    int offers_done;            /* 1 once takedawn_plugin_services_done ran (bmsdk_services_done) */
    uint32_t offers_said;       /* the host's count at the end of the offers */
} bmsdk_host_state;

static inline bmsdk_host_state *bmsdk_host_state_get(void)
{
    static bmsdk_host_state s;  /* per source file (static inline): use the helper from one file */
    return &s;
}

/* Call from takedawn_plugin_service with its arguments. Returns the entry of needs[] named `name` (its state set), or
 * NULL when this plugin does not want the service. Never calls the table. 0.2.0: also keeps a usable "bmashup.host"
 * table (bmsdk_host) and counts the offers, whether or not needs[] names it. */
static inline bmsdk_need *bmsdk_offer(bmsdk_need *needs, size_t n, const char *name, uint32_t version, const void *table)
{
    bmsdk_host_state *hs = bmsdk_host_state_get();
    hs->offers_seen++;
    if (name && table && version >= 1u && !strcmp(name, BM_HOST_SERVICE) &&
        ((const uint32_t *)table)[0] >= BMSDK_HOST_TABLE_V1)
        hs->host = (const bm_host_api *)table;
    for (size_t i = 0; needs && name && i < n; i++) {
        bmsdk_need *w = &needs[i];
        uint32_t want = w->min_table < BMSDK_TABLE_MIN ? BMSDK_TABLE_MIN : w->min_table;
        if (!w->name || strcmp(w->name, name))
            continue;
        w->offered_version = version;
        w->offered_table = table ? ((const uint32_t *)table)[0] : 0u;
        w->code = 0;
        if (table && version >= w->min_version && w->offered_table >= want) {
            w->state = BMSDK_BOUND;
            w->table = table;
        } else {
            w->state = BMSDK_TOO_OLD;
            w->table = NULL;
        }
        return w;
    }
    return NULL;
}

/* The bound service has `version` or later (graceful degrade: use a newer feature only then). */
static inline int bmsdk_has(const bmsdk_need *w, uint32_t version)
{
    return w && w->state == BMSDK_BOUND && w->offered_version >= version;
}

/* The bound service's first call was refused with `code` (e.g. subscribe answered BM_EVENTS_CLOSED). */
static inline void bmsdk_fail(bmsdk_need *w, int32_t code)
{
    if (w && w->state == BMSDK_BOUND) {
        w->state = BMSDK_FAILED;
        w->code = code;
    }
}

/* The diagnostic text (the forms at the top of this file) into buf; returns buf. */
static inline const char *bmsdk_describe(const bmsdk_need *w, char *buf, size_t bn)
{
    const char *tail;
    uint32_t want;
    if (!buf || !bn)
        return "";
    if (!w || !w->name) {
        snprintf(buf, bn, "(no service)");
        return buf;
    }
    tail = w->required ? "; required: this mod does nothing without it" : "; optional: the features that need it are off";
    want = w->min_table < BMSDK_TABLE_MIN ? BMSDK_TABLE_MIN : w->min_table;
    switch (w->state) {
    case BMSDK_BOUND:
        snprintf(buf, bn, "%s: ok (version %u, table %u bytes)", w->name, (unsigned)w->offered_version,
                 (unsigned)w->offered_table);
        break;
    case BMSDK_TOO_OLD:
        snprintf(buf, bn, "%s: too old: this host offers version %u with a %u-byte table; this mod needs version %u or later "
                 "with a table of at least %u bytes%s", w->name, (unsigned)w->offered_version, (unsigned)w->offered_table,
                 (unsigned)w->min_version, (unsigned)want, tail);
        break;
    case BMSDK_FAILED:
        snprintf(buf, bn, "%s: offered (version %u) but not usable: the service answered %d%s", w->name,
                 (unsigned)w->offered_version, (int)w->code, tail);
        break;
    default:
        snprintf(buf, bn, "%s: missing: this host did not offer it; this mod needs version %u or later%s", w->name,
                 (unsigned)w->min_version, tail);
        break;
    }
    return buf;
}

/* One line to the game's log through the host's own logger. */
#if defined(__GNUC__) || defined(__clang__)
__attribute__((format(printf, 3, 4)))
#endif
static inline void bmsdk_log(const td_host_api *api, int32_t level, const char *fmt, ...)
{
    char line[1024];
    va_list ap;
    if (!api || !api->log || !fmt)
        return;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    api->log(api->host, level, line);
}

/* "bmashup-sdk: " + bmsdk_describe(w), at INFO (bound), ERROR (required, not bound) or WARN (optional, not bound). */
static inline void bmsdk_log_need(const td_host_api *api, const bmsdk_need *w)
{
    char text[400];
    int32_t level = !w || w->state == BMSDK_BOUND ? TD_LOG_INFO : w->required ? TD_LOG_ERROR : TD_LOG_WARN;
    bmsdk_log(api, level, "bmashup-sdk: %s", bmsdk_describe(w, text, sizeof text));
}

/* Required needs that are not BOUND. */
static inline int bmsdk_missing_required(const bmsdk_need *needs, size_t n)
{
    int k = 0;
    for (size_t i = 0; needs && i < n; i++)
        k += needs[i].required && needs[i].state != BMSDK_BOUND;
    return k;
}

/* Logs every need that is not BOUND (bmsdk_log_need); returns bmsdk_missing_required. */
static inline int bmsdk_report(const td_host_api *api, const bmsdk_need *needs, size_t n)
{
    for (size_t i = 0; needs && i < n; i++)
        if (needs[i].state != BMSDK_BOUND)
            bmsdk_log_need(api, &needs[i]);
    return bmsdk_missing_required(needs, n);
}

/* bmsdk_report the first time only (*done: the plugin's flag, 0 at start). Returns bmsdk_missing_required. */
static inline int bmsdk_report_once(const td_host_api *api, const bmsdk_need *needs, size_t n, int *done)
{
    if (done && *done)
        return bmsdk_missing_required(needs, n);
    if (done)
        *done = 1;
    return bmsdk_report(api, needs, n);
}

/* ---- 0.2.0: the platform host's identity (bmashup.host) and the end of the offers ---- */
#define BMSDK_HOST_UNKNOWN 0xFFFFFFFFu  /* bmsdk_host_offers: no bmashup.host table (not a platform host, or not yet) */

/* The bmashup.host table this host offered (bmsdk_offer kept it), or NULL: a host before Burnout Mashup platform 0.1
 * (plain Takedawn, older Burnout Mashup builds), or the offer has not come yet. bmashup.host is offered FIRST. */
static inline const bm_host_api *bmsdk_host(void)
{
    return bmsdk_host_state_get()->host;
}

/* The version of `name` this host offers (its bmashup.host list: known at the first offer, before the others come),
 * 0 when it does not offer it, BMSDK_HOST_UNKNOWN when there is no bmashup.host table. */
static inline uint32_t bmsdk_host_offers(const char *name)
{
    const bm_host_api *h = bmsdk_host();
    if (!h)
        return BMSDK_HOST_UNKNOWN;
    return name && h->service_version ? h->service_version(name) : 0u;
}

/* With a bmashup.host table: the REQUIRED needs this host will not offer at min_version or later (by its list), known
 * at the first offer; -1 without a table (not knowable yet). A version-only check: the table size is checked at the
 * offer itself (bmsdk_offer). Logs nothing. */
static inline int bmsdk_host_missing(const bmsdk_need *needs, size_t n)
{
    int k = 0;
    if (!bmsdk_host())
        return -1;
    for (size_t i = 0; needs && i < n; i++)
        if (needs[i].required && needs[i].name && bmsdk_host_offers(needs[i].name) < needs[i].min_version)
            k++;
    return k;
}

/* Call from takedawn_plugin_services_done: the offers are over, so every need still not BOUND is final - reported now
 * (bmsdk_report_once with the plugin's flag, so the later fallbacks say nothing more). Returns bmsdk_missing_required. */
static inline int bmsdk_services_done(const td_host_api *api, const bmsdk_need *needs, size_t n, uint32_t offered, int *done)
{
    bmsdk_host_state *hs = bmsdk_host_state_get();
    hs->offers_done = 1;
    hs->offers_said = offered;
    return bmsdk_report_once(api, needs, n, done);
}

/* 1 once the host said the offers are over (a platform host); 0 on older hosts (they never say it). */
static inline int bmsdk_offers_done(void)
{
    return bmsdk_host_state_get()->offers_done;
}

/* bmsdk_offer calls so far (every offer, when the plugin passes each one to bmsdk_offer). */
static inline uint32_t bmsdk_offers_seen(void)
{
    return bmsdk_host_state_get()->offers_seen;
}

/* ---- the plugin's exports, for a plugin that wants nothing else from these macros ----
 * BMSDK_DEFINE_API_VERSION() defines takedawn_plugin_api_version (returns TD_PLUGIN_API_VERSION).
 * BMSDK_DEFINE_SERVICES_DONE(needs, reported) defines the OPTIONAL export takedawn_plugin_services_done: it calls
 * bmsdk_services_done(api, needs, count of needs[], offered, &reported) - `needs` an array (not a pointer), `reported`
 * the int flag the plugin also passes to bmsdk_report_once. Older hosts never call it; nothing else changes then. */
#define BMSDK_DEFINE_API_VERSION() \
    TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void) { return TD_PLUGIN_API_VERSION; }
#define BMSDK_DEFINE_SERVICES_DONE(needs, reported)                                                        \
    TD_EXPORT void TD_CALL takedawn_plugin_services_done(const td_host_api *api, uint32_t offered)         \
    { (void)bmsdk_services_done(api, (needs), sizeof(needs) / sizeof((needs)[0]), offered, &(reported)); }

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_SDK_H */
