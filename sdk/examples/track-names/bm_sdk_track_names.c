/*
 * bm_sdk_track_names.c - bmashup-sdk example (c): memory-backed track names on "bmashup.memory" + "bmashup.names".
 * Adapted from the runtime-validated G8-E4 demo bm_track_names_demo.c (launch 35: "Harbour Bay" shown in the selector).
 * Names a track a mod ADDS without naming it ([bmashup.tracks] add, no names / locations): the plugin owns blocks of the
 * game's memory, writes the UTF-16LE text into them through the memory service (never through a pointer: it has none),
 * and hands each block to the names service, which validates and freezes it. The two services may be offered in either
 * order; the plugin acts once it has both, during the start (set_text is refused afterwards: BM_NAMES_CLOSED).
 *
 * The track and the texts are build-time values (-DTRACK_ID=\"US_C6_V1\" -DTRACK_NAME=\"Harbour Bay\"
 * -DTRACK_LOCATION=\"HARBOUR\"); an empty TRACK_LOCATION ("") sets the name only. Texts: name 1..27 characters, location
 * 1..17, from A-Z a-z 0-9, space and - ' . & (the retail font); the plugin checks this before it allocates anything.
 * First plugin wins per track and kind; a mod that names the track itself wins over every plugin (the host logs it).
 */
#include "bmashup_sdk.h"

#ifndef TRACK_ID
#define TRACK_ID       "US_C6_V1"
#endif
#ifndef TRACK_NAME
#define TRACK_NAME     "Harbour Bay"
#endif
#ifndef TRACK_LOCATION
#define TRACK_LOCATION "HARBOUR"
#endif

static const td_host_api *s_api;
static bmsdk_need s_need[] = {
    BMSDK_NEED(BM_MEMORY_SERVICE, 1, BMSDK_MEMORY_TABLE_V1, 1),
    BMSDK_NEED(BM_NAMES_SERVICE, 1, BMSDK_NAMES_TABLE_V1, 1),
};
#define NNEED (sizeof s_need / sizeof s_need[0])
static int s_reported, s_done;

static const char *names_rc(int32_t rc)
{
    switch (rc) {
    case BM_NAMES_OK: return "ok";
    case BM_NAMES_BAD_ARG: return "bad argument (track ID or kind)";
    case BM_NAMES_BAD_TEXT: return "text refused (length or characters)";
    case BM_NAMES_NOT_OWNER: return "not this plugin's block";
    case BM_NAMES_CLOSED: return "too late (after the start)";
    case BM_NAMES_CONFLICT: return "another plugin named it first";
    default: return "unknown answer";
    }
}

/* the retail font's set, 1..max characters */
static int text_ok(const char *t, size_t max)
{
    size_t n = 0;
    for (; t[n]; n++) {
        char c = t[n];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' ||
              c == '\'' || c == '.' || c == '&'))
            return 0;
    }
    return n >= 1 && n <= max;
}

/* one text: a block of the game's memory (16-byte multiple, zero-filled), the UTF-16LE text, set_text (freezes it) */
static int32_t name_one(const bm_memory_api *mem, const bm_names_api *nm, uint32_t kind, const char *text, size_t max)
{
    uint16_t w[32];
    uint32_t i = 0, bytes;
    bm_mem_handle h = 0;
    int32_t rc;
    if (!text_ok(text, max)) {
        bmsdk_log(s_api, TD_LOG_ERROR, "track names: \"%s\" is not a valid %s (1..%u characters A-Z a-z 0-9 space - ' . &)",
                  text, kind == BM_NAMES_LOCATION ? "location" : "name", (unsigned)max);
        return BM_NAMES_BAD_TEXT;
    }
    for (; text[i]; i++)
        w[i] = (uint8_t)text[i];
    w[i] = 0;
    bytes = 2u * (i + 1u);
    rc = mem->alloc(s_api->host, bytes, &h);
    if (rc == BM_MEM_OK)
        rc = mem->write(s_api->host, h, 0, w, bytes);
    if (rc != BM_MEM_OK) {
        bmsdk_log(s_api, TD_LOG_ERROR, "track names: no block of game memory for \"%s\" (bmashup.memory answered %d)", text,
                  (int)rc);
        return -1;
    }
    rc = nm->set_text(s_api->host, TRACK_ID, kind, h);
    bmsdk_log(s_api, rc == BM_NAMES_OK ? TD_LOG_INFO : TD_LOG_WARN, "track names: %s %s of " TRACK_ID " = \"%s\": %s",
              rc == BM_NAMES_OK ? "set" : "NOT set", kind == BM_NAMES_LOCATION ? "location" : "name", text, names_rc(rc));
    return rc;
}

static void try_name(void)
{
    const bm_memory_api *mem;
    const bm_names_api *nm;
    if (s_done || s_need[0].state != BMSDK_BOUND || s_need[1].state != BMSDK_BOUND)
        return;                                     /* both are needed; they may come in either order */
    s_done = 1;
    mem = (const bm_memory_api *)s_need[0].table;
    nm = (const bm_names_api *)s_need[1].table;
    name_one(mem, nm, BM_NAMES_NAME, TRACK_NAME, 27);
    if (TRACK_LOCATION[0])
        name_one(mem, nm, BM_NAMES_LOCATION, TRACK_LOCATION, 17);
}

static void TD_CALL on_shutdown(void *user)
{
    (void)user;
    bmsdk_report_once(s_api, s_need, NNEED, &s_reported);       /* a missing service is only known after the start */
}

BMSDK_DEFINE_API_VERSION()
/* 0.2.0: platform hosts call this once after the last offer: a missing service is said during the start */
BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    s_api = api;
    if (info->struct_size >= BMSDK_FIELD_END(td_plugin_info, user)) {
        info->on_shutdown = on_shutdown;
        info->user = NULL;
    }
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, NNEED, name, version, table);
    if (!w)
        return 1;
    if (w->state != BMSDK_BOUND) {
        bmsdk_log_need(api, w);
        return 1;
    }
    try_name();
    return TD_OK;
}
