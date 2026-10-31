/*
 * bm_sdk_host_info.c - bmashup-sdk example (h): a HOST-INFO PROBE on "bmashup.host" v1 (bmashup_host.h). It changes
 * nothing in the game; it only logs what the host is:
 *
 *   at the bmashup.host offer (offered FIRST by a Burnout Mashup platform host):
 *     "host info: Burnout Mashup platform 0.1.1 (0.1.1), Takedawn <version>, build <build>, game <signature>"
 *     "host info: build identity bmp-0.1.1+b56e33b66dc3 = the SDK's reference host (burnout3_bmp_p3.exe sha256 ...)"
 *     (SDK 0.3.0: reference host p3, BMSDK_REFERENCE_BUILD / _HOST / _PLATFORM in bmashup_sdk.h; any other build is named
 *     with "not the SDK's reference build" - the platform version, not the identity, decides compatibility)
 *     "host info: 14 services: bmashup.host 1, takedawn.race 1, ..."
 *     one line per entry of its want-list, from the host's own list (bmsdk_host_offers), before any other offer:
 *     "host info: wants bmashup.events >= 5: offered 5 (ok)" / "... not offered (missing)" / "... offered 1 (too old)"
 *   at the end of the offers (takedawn_plugin_services_done, platform hosts only):
 *     "host info: offers over: the host says 14, this plugin saw 14"
 *   on an older host (no bmashup.host, no end of offers), at shutdown:
 *     "host info: no end-of-offers call: a host before Burnout Mashup platform 0.1 (plain Takedawn or an older build)"
 *     + the SDK's "bmashup-sdk: bmashup.host: missing: ..." line (optional need: WARN).
 * The want-list includes "bmashup.weather", a service no host offers, to show the "missing" answer.
 *
 * Use it to check an installation: the host's platform version and build, the game image signature, and which services
 * (and versions) your mods can count on. Build: the SDK's build.ps1, or
 *   clang -shared -Iinclude bm_sdk_host_info.c -o bm_sdk_host_info.asi
 */
#include "bmashup_sdk.h"

#define TAG "host info"

static const td_host_api *s_api;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_HOST_SERVICE, 1, BMSDK_HOST_TABLE_V1, 0),       /* optional: plain hosts do not have it */
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported;

static const struct { const char *name; uint32_t min; } k_want[] = {
    {"takedawn.race", 1}, {"bmashup.events", 5}, {"bmashup.hooks", 1}, {"bmashup.patch", 1}, {"bmashup.weather", 1},
};

static void describe(const bm_host_api *h)
{
    char list[900] = "", line[1024];
    const char *n;
    uint32_t v, cnt = h->service_count();
    for (uint32_t i = 0; h->service_at(i, &n, &v); i++) {
        char one[80];
        snprintf(one, sizeof one, "%s%s %u", i ? ", " : "", n, (unsigned)v);
        strncat(list, one, sizeof list - strlen(list) - 1);
    }
    bmsdk_log(s_api, TD_LOG_INFO, TAG ": Burnout Mashup platform %s (%u.%u.%u), Takedawn %s, build %s, game %s",
              h->platform_version, (unsigned)h->platform_major, (unsigned)h->platform_minor, (unsigned)h->platform_patch,
              h->host_version, h->build, h->game_signature && h->game_signature[0] ? h->game_signature : "(not read)");
    /* the build identity check: the platform version is the compatibility contract; the identity names one exact build */
    if (h->build && !strcmp(h->build, BMSDK_REFERENCE_BUILD))
        bmsdk_log(s_api, TD_LOG_INFO, TAG ": build identity %s = the SDK's reference host (%s)", h->build, BMSDK_REFERENCE_HOST);
    else
        bmsdk_log(s_api, TD_LOG_INFO, TAG ": build identity %s: not the SDK's reference build %s (platform %s decides compatibility)",
                  h->build ? h->build : "(none)", BMSDK_REFERENCE_BUILD, h->platform_version);
    snprintf(line, sizeof line, TAG ": %u services: %s", (unsigned)cnt, list);
    s_api->log(s_api->host, TD_LOG_INFO, line);
    for (size_t i = 0; i < sizeof k_want / sizeof k_want[0]; i++) {
        uint32_t got = bmsdk_host_offers(k_want[i].name);
        if (!got)
            bmsdk_log(s_api, TD_LOG_INFO, TAG ": wants %s >= %u: not offered (missing)", k_want[i].name, (unsigned)k_want[i].min);
        else
            bmsdk_log(s_api, TD_LOG_INFO, TAG ": wants %s >= %u: offered %u (%s)", k_want[i].name, (unsigned)k_want[i].min,
                      (unsigned)got, got >= k_want[i].min ? "ok" : "too old");
    }
}

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    if (!bmsdk_offers_done())
        bmsdk_log(s_api, TD_LOG_INFO, TAG ": no end-of-offers call: a host before Burnout Mashup platform 0.1 (plain Takedawn "
                  "or an older build)");
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);
}

BMSDK_DEFINE_API_VERSION()

TD_EXPORT void TD_CALL takedawn_plugin_services_done(const td_host_api *api, uint32_t offered)
{
    bmsdk_services_done(api, s_need, NNEED, offered, &s_reported);
    bmsdk_log(api, TD_LOG_INFO, TAG ": offers over: the host says %u, this plugin saw %u", (unsigned)offered,
              (unsigned)bmsdk_offers_seen());
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    s_api = api;
    if (info && info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {
        info->on_shutdown = on_shutdown;
        info->user = NULL;
    }
    bmsdk_log(api, TD_LOG_INFO, TAG ": bmashup-sdk %s", BMSDK_VERSION_STRING);
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version,
                                                   const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);  /* every offer: counted */
    (void)api;
    if (!w || w->state != BMSDK_BOUND)
        return 1;
    describe((const bm_host_api *)w->table);
    return TD_OK;                                   /* "used": the table was read */
}
