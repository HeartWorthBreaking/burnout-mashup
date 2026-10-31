/* bm_names_service.c - G8-E4 EXPERIMENTAL: "bmashup.names" (include/bmashup_names.h): a plugin names an added track from a
 * bmashup.memory block. The block is validated by bm_names.c (bo3_nm_plugin_text) and frozen here on success. */
#include "bmashup_names.h"

#include "bm_memory.h"
#include "bm_names.h"
#include "bm_tracks.h"
#include "plugins.h"

static int s_open = 1;

void bo3_bm_names_close(void)
{
    s_open = 0;
}

static int32_t TD_CALL n_set_text(td_host *host, const char *track_id, uint32_t kind, bm_mem_handle block)
{
    char why[200];
    uint64_t id;
    uint32_t va, size;
    int r;
    if (!host || !track_id || kind > BM_NAMES_LOCATION || !bo3_cc_id_ok(track_id, why, sizeof why) || !bo3_cc_encode(track_id, &id))
        return BM_NAMES_BAD_ARG;
    if (!s_open)
        return BM_NAMES_CLOSED;
    if (!bo3_mem_block(host, block, &va, &size))
        return BM_NAMES_NOT_OWNER;
    r = bo3_nm_plugin_text(host, id, kind, va, size);
    if (r == 0) {
        bo3_mem_freeze(host, block);
        return BM_NAMES_OK;
    }
    return r == 1 ? BM_NAMES_BAD_TEXT : r == 2 ? BM_NAMES_CLOSED : BM_NAMES_CONFLICT;
}

static const bm_names_api s_api = {(uint32_t)sizeof(bm_names_api), BM_NAMES_VERSION, n_set_text};

const bm_names_api *bo3_bm_names_api(void)
{
    return &s_api;
}

void bo3_bm_names_init(void)
{
    bo3_plugins_service(BM_NAMES_SERVICE, BM_NAMES_VERSION, &s_api);
}
