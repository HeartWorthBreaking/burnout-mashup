/*
 * bm_platform_table.h - PLATFORM-P1: what this Burnout Mashup platform host offers, as data (no code, no public header
 * needed): the platform version, the services a plugin can be offered, and the mod.toml [bmashup.*] tables with the
 * schema version and keys each reader takes. Used by:
 *   - modmanifest.c bo3_manifest_platform_check (P-1 / P-2: a mod's [bmashup] platform / requires and every
 *     [bmashup.*] table are checked when the mod list is made, so a mod this host cannot serve is refused alone);
 *   - bm_platform.c (game build): the boot log line, a compile-time check of every service version against its public
 *     header (_Static_assert), and a start-time check of the table against the real service registry;
 *   - plugins.c: "bmashup.host" (include/bmashup_host.h) gives plugins the platform version.
 * Change a reader's keys or version, or a service's version: change this table too (bm_platform.c's static asserts
 * catch a service version; tests\test_p1_platform.c checks every table's keys against the readers).
 */
#ifndef BO3_BM_PLATFORM_TABLE_H
#define BO3_BM_PLATFORM_TABLE_H

#define BO3_PLATFORM_MAJOR 0
#define BO3_PLATFORM_MINOR 1
#define BO3_PLATFORM_PATCH 9
#define BO3_PLATFORM_VERSION "0.1.9"   /* main19 (combined mainline): main18 + mem256 (256 MB guest window,
                                        * BO3_GUEST_WINDOW_MB 64|256, budget gate) + hook request P2 / P3
                                        * (BO3_HOOKREQ_P23): bmashup.racers 3, bmashup.vphysics 3 (gearbox), bmashup.traffic 3,
                                        * bmashup.hooks 3 (points 8..13), bmashup.events 7, bmashup.camera 2, bmashup.hud 2, new
                                        * bmashup.paints 1, bmashup.menu 1, bmashup.rules 1 (25 services). Functions waiting for a
                                        * runtime probe answer UNAVAILABLE (BM_P23_* constants). No new mod.toml key.
                                        * 0.1.8 = main18: mod limits (mods / folders 256 + TAKEDAWN_MODS_FILE, texture /
                                        * music mods 64, switched-off ids 1024) + hook request P1: bmashup.patch 2 (index-table
                                        * sites), bmashup.racers 2, bmashup.boost 2 (award), bmashup.hud 1 (new), bmashup.settings 2
                                        * (per player), bmashup.input 1 (new), bmashup.vphysics 2 (vehicle query), bmashup.traffic 2
                                        * (density 3.0, EXPERIMENTAL above 2.0), bmashup.hooks 2 (CRASH_RESULT point). No mod.toml key.
                                        * 0.1.7 = GP-CAPMEGA1: [bmashup.capacity] gamedata_bytes (GAMEDATA slot
                                        * expansion, bm_gdslot.c) + the BMRX mesh row extension (bm_rowx.c; no mod.toml key).
                                        * 0.1.6 = GP-P4.3: content expansion - [bmashup.textures] 1, [bmashup.wt_map_art] 1 and the
                                        * [bmashup.cars] photos key (fetex1), [bmashup.cars] 2, [bmashup.series] 1,
                                        * [bmashup.paints] 1 (veh1), mod.toml up to 65536 bytes (was 8192).
                                        * 0.1.5 = GP-P4.2: [bmashup.cars] 1 (cars2: added cars) and [bmashup.world_tour] 1
                                        * (wt4: a fourth World Tour region). 0.1.4 = GP-P4.1: [bmashup.music] 1 (music1), [bmashup.tune] 2 + bmashup.tune 3
                                        * (aitune1), bmashup.vphysics 1.0.2 serves AI racers, the garage paint cap (MOD
                                        * SETTINGS host setting). 0.1.3 = GP-P4: the integration of the gp slices (0.1.2 was declared by
                                        * two different slice hosts, crash1 and deps1; p4 holds both + the registry of
                                        * BO3_PLATFORM_MAX_SERVICES). Before:
                                        * GP-CRASH1 (0.1.2): bmashup.events 6 (CRASH_RESULT), bmashup.crash 1;
                                        * GP-DEPS1: [bmashup] requires_mods (mod-to-mod dependencies), dependency order;
                                        * 0.1.1: PLATFORM-P3 [bmashup.extra_events] version 2, the two-phase admission */

/* X(name, version, the public header's version macro): every service the host registers (bo3_plugins_service), in
 * registration order, and bmashup.host (plugins.c, offered first to every plugin). */
#define BO3_PLATFORM_SERVICES(X)                                    \
    X("bmashup.host",      1, BM_HOST_VERSION)                      \
    X("takedawn.race",     1, TD_RACE_VERSION)                      \
    X("bmashup.autopilot", 2, BM_AUTOPILOT_VERSION)   /* gp I4 */  \
    X("bmashup.boost",     2, BM_BOOST_VERSION)     /* main18: + award */ \
    X("bmashup.vphysics",  3, BM_VPHYS_VERSION)      /* GP-P4 (physics1); main18: + vehicle query; main19: + gearbox */ \
    X("bmashup.events",    7, BM_EVENTS_VERSION)    /* main19: + HUD_PASS / TRAFFIC_CONTACT / WRECK_CAUSE / EVENT_SOUND twins */ \
    X("bmashup.hooks",     3, BM_HOOKS_VERSION)     /* main18: + point 7 CRASH_RESULT; main19: + points 8..13 */ \
    X("bmashup.patch",     2, BM_PATCH_VERSION)     /* main18: + TABLE sites, request_site_pair */ \
    X("bmashup.memory",    1, BM_MEMORY_VERSION)                    \
    X("bmashup.names",     1, BM_NAMES_VERSION)                     \
    X("bmashup.racers",    6, BM_RACERS_VERSION)    /* main18: + place / order / session; main19: + dynamics / controls; main21: + pose; patch 98: + wreck (4 with BO3_HOOKREQ_P28W OFF); patch 104: + tail stand-in (5 with P8T OFF) */ \
    X("bmashup.crash",     1, BM_CRASH_VERSION)                     \
    X("bmashup.engine",    1, BM_ENGINE_VERSION)                    \
    X("bmashup.streaming", 2, BM_STREAMING_VERSION)                 \
    X("bmashup.route",     2, BM_ROUTE_VERSION)                     \
    X("bmashup.tune",      3, BM_TUNE_VERSION)   /* GP-AITUNE1 */   \
    X("bmashup.traffic",   8, BM_TRAFFIC_VERSION)   /* GP-TRAFFIC1; main18: + set_density_v2 (3.0); main19: + crash pool, wreck; main21: + seed, lane floor (4), spread, section min (5), fill empty lanes (6), pre-load (7, patch 109), parked cars (8, C3-4) */ \
    X("bmashup.ai",        1, BM_AI_VERSION)        /* GP-AI1 */      \
    X("bmashup.settings",  2, BM_SETTINGS_VERSION)   /* gp camset1; main18: PER_PLAYER, subscribe2, get_player */ \
    X("bmashup.camera",    4, BM_CAMERA_VERSION)     /* gp camset1; main19: + chase-camera adjust (v2); main21: + free camera (v3); main21 patch 96: + the picture view (v4; 3 with BO3_HOOKREQ_P27C OFF) */ \
    X("bmashup.hud",       2, BM_HUD_VERSION)        /* main18 hook request P1; main19: + draw list (UNAVAILABLE in 0.1.9) */ \
    X("bmashup.input",     1, BM_INPUT_VERSION)      /* main18 hook request P1 */ \
    X("bmashup.paints",    1, BM_PAINTS_VERSION)     /* main19 hook request P2 I (patch 31) */ \
    X("bmashup.menu",      1, BM_MENU_VERSION)       /* main19 hook request P3 D (patches 32..34) */ \
    X("bmashup.rules",     6, BM_RULES_VERSION)      /* main19 hook request P3 E1 (patch 35); 2: main21 patch 80; 3: patch 83; 4: patch 105; 5: patch 106; 6: patch 113 */ \
    /* main18: the end of the list (each row above ends in a backslash) */

/* T(table, newest version the reader takes, its keys separated by single spaces): the mod.toml tables
 * [bmashup.<table>] this host reads (bm_capdecl.c, bm_tune.c, bm_tracks.c regions / tracks, bm_wtour.c, bm_music.c). The keys are
 * the exact keys each reader accepts ("bmashup.<table>.<key>"). [bmashup] itself takes BO3_PLATFORM_OWN_KEYS. */
#define BO3_PLATFORM_TABLES(T)                                                      \
    T("capacity",     1, "version lanes low_unit_bytes static_bytes gamedata_bytes full_unit_bytes")   /* main21 patch 131: + full_unit_bytes */ \
    T("tune",         3, "version set sliders")   /* GP-AITUNE1: 2 = + AI values, signed; main21 patch 130: 3 = + sliders (MODS page) */  \
    T("regions",      1, "version add dj")                                         \
    T("tracks",       1, "version add point_to_point names locations")             \
    T("extra_events", 2, "version add stage names help")   /* P3 (P-11): version 2 = + names, help */ \
    T("music",        1, "version soundtrack add replace")  /* GP-MUSIC1: music packs (bm_music.c) */ \
    T("cars",         2, "version add names physics_scale photos model unlock ai")  /* gp cars2 (1) + veh1 (2); GP-FETEX1: photos (bm_fetex.c) */ \
    T("series",       1, "version add names unlock ai_class")  /* gp veh1: new car series (bm_veh.c) */ \
    T("paints",       1, "version add default")  /* gp veh1: the paint registry (bm_vpaint.c) */ \
    T("world_tour",   1, "version region map location")   /* GP-WT4: a fourth World Tour region (bm_wt4.c) */ \
    T("textures",     1, "version txd class")              /* GP-FETEX1: front-end textures (bm_fetex.c) */ \
    T("wt_map_art",   1, "version region art place ticker")  /* GP-FETEX1: 4th-region map art / texts (bm_fetex.c) */

/* [bmashup] own keys: platform = ">=X.Y[.Z]"; requires = capabilities (services / tables, "name>=N"); GP-DEPS1 (platform
 * 0.1.2): requires_mods = other mods ("<mod id>" or "<mod id> >= X.Y[.Z]"), checked together with the mod list (bm_admit.c) */
#define BO3_PLATFORM_OWN_KEYS "platform requires requires_mods"

/* GP-P4: the service registry's capacity (plugins.c), bmashup.host not counted. p3 had 16 (13 used); p4 registers 19.
 * bm_platform.c checks at compile time that BO3_PLATFORM_SERVICES fits; plugins.c logs a registration it refuses. */
#define BO3_PLATFORM_MAX_SERVICES 32
#define BO3_PLATFORM_MAX_REQUIRES_MODS 16

#endif
