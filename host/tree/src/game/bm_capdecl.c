/* G8-MCAP EXPERIMENTAL: mod capacity declarations (bm_capdecl.h). MUT=n (test builds only) compiles one deliberate defect. */
#include "bm_capdecl.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_engine_service.h"
#include "bm_gdslot.h"
#include "bm_static.h"            /* patch 131: BO3_ST_MAX / BO3_US_LOW_MAX in the refusal texts */
#include "bm_streaming_service.h"
#include "bm_unitslots.h"
#include "modfs.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0
#endif

#define CD_PREFIX "bmashup.capacity"

static const struct { const char *key; uint32_t bit; } s_fields[] = {
    {CD_PREFIX ".lanes", BO3_CAPDECL_LANES},
    {CD_PREFIX ".low_unit_bytes", BO3_CAPDECL_LOW},
    {CD_PREFIX ".static_bytes", BO3_CAPDECL_STATIC},
    {CD_PREFIX ".gamedata_bytes", 0x80u},   /* GP-MEGA1 */
    {CD_PREFIX ".full_unit_bytes", BO3_CAPDECL_FULL},   /* patch 131 */
};

int bo3_capdecl_parse(const char *text, size_t n, bo3_capdecl *out, char *why, size_t wn)
{
    char err[200];
    recomp_cfg *cfg;
    char *buf;
    size_t plen = strlen(CD_PREFIX);
    int ok = 1;

    memset(out, 0, sizeof *out);
    if (why && wn)
        why[0] = 0;
    buf = (char *)malloc(n + 1);
    if (!buf) {
        snprintf(why, wn, "no memory");
        return 0;
    }
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg) {
        snprintf(why, wn, "mod.toml: %s", err);
        return 0;
    }
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i);
        if (strncmp(k, CD_PREFIX, plen) != 0 || (k[plen] != 0 && k[plen] != '.'))
            continue;                                   /* another key (Takedawn's own, or another table) */
        out->present = 1;
        if (k[plen] == 0) {
            snprintf(why, wn, "%s must be a table ([%s])", CD_PREFIX, CD_PREFIX);
            ok = 0;
            break;
        }
        if (!strcmp(k, CD_PREFIX ".version"))
            continue;
        int known = 0;
        for (size_t f = 0; f < sizeof s_fields / sizeof s_fields[0]; f++) {
            if (strcmp(k, s_fields[f].key) != 0)
                continue;
            known = 1;
            long long v = recomp_cfg_int(cfg, k, -1);
            if (recomp_cfg_type_of(cfg, k) != RCFG_INT || v < 0 || v > 0xFFFFFFFFll) {
                snprintf(why, wn, "%s must be a whole number from 0 to 0xFFFFFFFF", k);
                ok = 0;
                break;
            }
            out->have |= s_fields[f].bit;
            if (s_fields[f].bit == BO3_CAPDECL_LANES)
                out->lanes = (uint32_t)v;
            else if (s_fields[f].bit == BO3_CAPDECL_LOW)
                out->low_unit_bytes = (uint32_t)v;
            else if (s_fields[f].bit == 0x80u)
                out->gamedata_bytes = (uint32_t)v;
            else if (s_fields[f].bit == BO3_CAPDECL_FULL)
                out->full_unit_bytes = (uint32_t)v;
            else
                out->static_bytes = (uint32_t)v;
        }
#if MUT != 1
        if (ok && !known) {
            snprintf(why, wn, "%s is not a requirement this build knows (it reads %s version %d: lanes, low_unit_bytes, "
                     "static_bytes, gamedata_bytes, full_unit_bytes)", k, CD_PREFIX, BO3_CAPDECL_VERSION);
            ok = 0;
        }
#else
        (void)known;                                    /* defect: an unknown requirement is ignored */
#endif
    }
    if (ok && out->present) {
        long long ver = recomp_cfg_int(cfg, CD_PREFIX ".version", -1);
        if (recomp_cfg_type_of(cfg, CD_PREFIX ".version") != RCFG_INT) {
            snprintf(why, wn, "%s.version is missing or not a whole number (this build reads version %d)", CD_PREFIX,
                     BO3_CAPDECL_VERSION);
            ok = 0;
        }
#if MUT != 2
        else if (ver != BO3_CAPDECL_VERSION) {
            snprintf(why, wn, "%s.version %lld is not one this build reads (version %d)", CD_PREFIX, ver, BO3_CAPDECL_VERSION);
            ok = 0;
        }
#else
        (void)ver;                                      /* defect: the version is not checked */
#endif
    }
    recomp_cfg_free(cfg);
    if (!ok) {
        out->have = 0;
        out->lanes = out->low_unit_bytes = out->static_bytes = out->gamedata_bytes = out->full_unit_bytes = 0;
    }
    return ok;
}

static const char *engine_why(int32_t rc)
{
    return rc == BM_ENGINE_OUT_OF_RANGE ? "out of range (1..255 total lanes)" :
           rc == BM_ENGINE_UNSUPPORTED ? "this game build is not one the lane extension is verified for" :
           rc == BM_ENGINE_CLOSED ? "too late: the capacity is fixed" : "refused";
}

static const char *streaming_why(int32_t rc, int stat)
{
    static char s_why[96];      /* patch 131: the ceilings are the services' (build-dependent STATIC), printed from them */
    if (rc == BM_STREAMING_OUT_OF_RANGE) {
        snprintf(s_why, sizeof s_why, stat ? "out of range (a page multiple above 0xA00000, at most 0x%X)" :
                 "out of range (a page multiple from 0x18000 to 0x%X)", stat ? (unsigned)BO3_ST_MAX : (unsigned)BO3_US_LOW_MAX);
        return s_why;
    }
    return rc == BM_STREAMING_UNSUPPORTED ? "this game build is not one the extension is verified for" :
           rc == BM_STREAMING_CLOSED ? "too late: the size is fixed" : "refused";
}

#if MUT == 4
#define CD_FAIL(id, w) fail(id, w)                      /* defect: a refusal does not stop the remaining mods */
#else
#define CD_FAIL(id, w) do { fail(id, w); return declared; } while (0)
#endif

static int s_tok[BO3_MODFS_MAX_MODS];                   /* one requester identity per mod (the services key requests by it) */

int bo3_capdecl_apply(bo3_capdecl_fail_fn fail)
{
    const bm_engine_api *eng = bo3_bm_engine_api();
    const bm_streaming_api *str = bo3_bm_streaming_api();
    int declared = 0;

    for (int i = 0; i < bo3_modfs_mod_count() && i < BO3_MODFS_MAX_MODS; i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[300], msg[400];
        char *text = NULL;
        size_t n = 0;
        bo3_capdecl d;
        td_host *host = (td_host *)&s_tok[i];
        uint32_t merged;
        int32_t rc;

#if MUT == 3
        if (!m)                                         /* defect: mods that are off or unusable are read too */
#else
        if (!m || !m->usable || !m->enabled)
#endif
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;                                   /* modfs read it moments ago; a vanished file declares nothing */
        }
        rc = bo3_capdecl_parse(text, n, &d, why, sizeof why);
        free(text);
        if (!rc) {
            CD_FAIL(m->manifest.id, why);
            continue;
        }
        if (!d.present)
            continue;
        declared++;
        /* each field through its service; a refused field stops the start, so the game never runs with part of a
         * mod's requirement */
        if (d.have & BO3_CAPDECL_LANES) {
            rc = eng->request_lanes(host, d.lanes, &merged);
            fprintf(stderr, "[CAPACITY] mod %s requires %u total lanes: %s (merged %u)\n", m->manifest.id,
                    (unsigned)d.lanes, rc == BM_ENGINE_OK ? "accepted" : "REFUSED", (unsigned)merged);
            if (rc != BM_ENGINE_OK) {
                snprintf(msg, sizeof msg, "lanes = %u: %s", (unsigned)d.lanes, engine_why(rc));
                CD_FAIL(m->manifest.id, msg);
            }
        }
        if (d.have & BO3_CAPDECL_LOW) {
            rc = str->request_low_unit_bytes(host, d.low_unit_bytes, &merged);
            fprintf(stderr, "[CAPACITY] mod %s requires low-detail unit slots of 0x%X bytes: %s (merged 0x%X)\n",
                    m->manifest.id, (unsigned)d.low_unit_bytes, rc == BM_STREAMING_OK ? "accepted" : "REFUSED",
                    (unsigned)merged);
            if (rc != BM_STREAMING_OK) {
                snprintf(msg, sizeof msg, "low_unit_bytes = 0x%X: %s", (unsigned)d.low_unit_bytes, streaming_why(rc, 0));
                CD_FAIL(m->manifest.id, msg);
            }
        }
        if (d.have & BO3_CAPDECL_FULL) {   /* patch 131 */
            rc = bo3_bm_streaming_request_full(host, d.full_unit_bytes, &merged);
            fprintf(stderr, "[CAPACITY] mod %s requires full-detail unit slots of 0x%X bytes: %s (merged 0x%X)\n",
                    m->manifest.id, (unsigned)d.full_unit_bytes, rc == BM_STREAMING_OK ? "accepted" : "REFUSED",
                    (unsigned)merged);
            if (rc != BM_STREAMING_OK) {
                if (rc == BM_STREAMING_OUT_OF_RANGE)
                    snprintf(msg, sizeof msg, "full_unit_bytes = 0x%X: out of range (a page multiple from 0x%X to 0x%X)",
                             (unsigned)d.full_unit_bytes, (unsigned)BO3_US_FULL_RETAIL, (unsigned)BO3_US_FULL_MAX);
                else
                    snprintf(msg, sizeof msg, "full_unit_bytes = 0x%X: %s", (unsigned)d.full_unit_bytes, streaming_why(rc, 0));
                CD_FAIL(m->manifest.id, msg);
            }
        }
        if (d.have & BO3_CAPDECL_STATIC) {
            rc = str->request_static_bytes(host, d.static_bytes, &merged);
            fprintf(stderr, "[CAPACITY] mod %s requires a STATIC track pool of 0x%X bytes: %s (merged 0x%X)\n",
                    m->manifest.id, (unsigned)d.static_bytes, rc == BM_STREAMING_OK ? "accepted" : "REFUSED",
                    (unsigned)merged);
            if (rc != BM_STREAMING_OK) {
                snprintf(msg, sizeof msg, "static_bytes = 0x%X: %s", (unsigned)d.static_bytes, streaming_why(rc, 1));
                CD_FAIL(m->manifest.id, msg);
            }
        }
        if (d.have & 0x80u) {   /* GP-MEGA1: the GAMEDATA slot (bm_gdslot.c) */
            rc = bo3_gds_request(d.gamedata_bytes, &merged);
            fprintf(stderr, "[CAPACITY] mod %s requires a GAMEDATA slot of 0x%X bytes: %s (merged 0x%X)\n",
                    m->manifest.id, (unsigned)d.gamedata_bytes, rc == BO3_GDS_OK ? "accepted" : "REFUSED", (unsigned)merged);
            if (rc != BO3_GDS_OK) {
                snprintf(msg, sizeof msg, "gamedata_bytes = 0x%X: %s", (unsigned)d.gamedata_bytes, rc == BO3_GDS_OUT_OF_RANGE ?
                         "out of range (a page multiple above 0x176000, at most 0x800000)" : "too late: the size is fixed");
                CD_FAIL(m->manifest.id, msg);
            }
        }
    }
    return declared;
}

#ifdef BO3_CAPDECL_GAME
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

static void game_fail(const char *mod_id, const char *why)
{
    fprintf(stderr, "[CAPACITY] FATAL: mod %s declares a capacity requirement this build cannot meet: %s\n", mod_id, why);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: a mod needs more than this build supports",
              "The mod \"%s\" declares in its mod.toml ([bmashup.capacity]) a requirement this build cannot meet:\n%s\n\n"
              "Turn the mod off, or use a build that supports it.", mod_id, why);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(91);
}

void bo3_capdecl_game_apply(void)
{
    int n = bo3_capdecl_apply(game_fail);
    fprintf(stderr, "[CAPACITY] %d mod%s declared capacity requirements (mod.toml [bmashup.capacity] version %d)\n", n,
            n == 1 ? "" : "s", BO3_CAPDECL_VERSION);
}
#endif
