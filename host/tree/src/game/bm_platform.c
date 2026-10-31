/*
 * bm_platform.c - PLATFORM-P1 (game build): the platform's identity in the boot log, and the checks that keep
 * bm_platform_table.h true:
 *   - compile time: every service version in the table equals its public header's macro (_Static_assert);
 *   - start time (bo3_platform_check_registry, right before bo3_plugins_init): the services really registered equal the
 *     table (name, version, order). A difference cannot come from a mod; it is a host defect, logged as
 *     "[PLATFORM] ERROR" (requirements were checked against the table when the mod list was made).
 */
#include "bm_platform.h"

#include <stdio.h>
#include <string.h>

#include "bm_platform_table.h"
#include "bm_patch.h"
#include "plugins.h"
#include "bmashup_autopilot.h"
#include "bmashup_boost.h"
#include "bmashup_crash.h"
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
#include "bmashup_vphysics.h"   /* GP-P4: the bmashup.vphysics row */
#include "bmashup_traffic.h"
#include "bmashup_ai.h"
#include "bmashup_settings.h"   /* gp camset1 */
#include "bmashup_camera.h"
#include "bmashup_hud.h"        /* main18 */
#include "bmashup_input.h"      /* main18 */
#include "bmashup_paints.h"     /* main19 patch 31 */
#include "bmashup_menu.h"       /* main19 patch 32 */
#include "bmashup_rules.h"      /* main19 patch 35 */
#include "takedawn_race.h"

#define BO3_P1_ASSERT(name, ver, macro) _Static_assert((ver) == (macro), "bm_platform_table.h: " name " version");
BO3_PLATFORM_SERVICES(BO3_P1_ASSERT)
#undef BO3_P1_ASSERT

#define BO3_P1_ROW(name, ver, macro) { name, ver },
static const struct { const char *name; unsigned version; } s_table[] = { BO3_PLATFORM_SERVICES(BO3_P1_ROW) };
_Static_assert(sizeof s_table / sizeof s_table[0] - 1 <= BO3_PLATFORM_MAX_SERVICES,
               "GP-P4: the platform table does not fit the service registry (plugins.c)");
#undef BO3_P1_ROW
#define BO3_P1_TROW(t, ver, keys) "[bmashup." t "] v" #ver " "
static const char s_tables[] = BO3_PLATFORM_TABLES(BO3_P1_TROW);
#undef BO3_P1_TROW

void bo3_platform_boot_log(void)
{
    fprintf(stderr, "[PLATFORM] Burnout Mashup platform %s: mod.toml [bmashup] platform / requires; tables %s(a newer "
            "version or an unknown table / key refuses that mod only)\n", BO3_PLATFORM_VERSION, s_tables);
    fflush(stderr);
}

void bo3_platform_host_info(const char *build)
{
    static int tok;                              /* a requester identity for bmashup.patch (bm_capdecl.c's way) */
    const bm_patch_api *p = bo3_bm_patch_api();
    uint64_t sig = 0;
    char s[17] = "";

    if (p && p->build_signature && p->build_signature((td_host *)&tok, &sig) == BM_PATCH_OK)
        snprintf(s, sizeof s, "%016llX", (unsigned long long)sig);
    bo3_plugins_host_info(build, s);
    fprintf(stderr, "[PLATFORM] host: Burnout Mashup platform %s, build %s, game signature %s\n", BO3_PLATFORM_VERSION,
            build && *build ? build : "unknown", s[0] ? s : "(not read)");
}

int bo3_platform_check_registry(void)
{
    uint32_t n = bo3_plugins_service_count();
    int bad = 0;
    size_t want = sizeof s_table / sizeof s_table[0];

    for (uint32_t i = 0; i < n || i < want; i++) {
        const char *name = NULL;
        uint32_t ver = 0;
        int have = bo3_plugins_service_at(i, &name, &ver);
        if (i >= want || !have || strcmp(name, s_table[i].name) || ver != s_table[i].version) {
            fprintf(stderr, "[PLATFORM] ERROR: service %u is %s %u, the platform table says %s %u (host defect: mod "
                    "requirements were checked against the table)\n", (unsigned)i, have ? name : "(none)", (unsigned)ver,
                    i < want ? s_table[i].name : "(none)", i < want ? s_table[i].version : 0u);
            bad++;
        }
    }
    fprintf(stderr, "[PLATFORM] %u services offered to plugins (bmashup.host first)%s\n", (unsigned)n,
            bad ? ": DIFFERS from the platform table" : ", as the platform table says");
    fflush(stderr);
    return bad == 0;
}
