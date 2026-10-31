/*
 * bm_platform_gate.inc - PLATFORM-P1 (P-1, P-2): the platform gate, compiled as part of modmanifest.c (#include at its
 * end) so that every program that links modmanifest.c (the game, modfs's tests, the SDK test hosts, bmpack's checker)
 * gets it without a new source file. modfs.c calls bo3_manifest_platform_check for every mod whose manifest is valid,
 * when the mod list is made: before any file of a mod is served, before any [bmashup.*] reader, service or plugin sees
 * it, before the guest starts. A refused mod is "not usable" exactly like a mod with a broken manifest: its files,
 * its tables and its plugin are not used, and the game starts without it.
 *
 * Checks, in this order (the first failure is the reason):
 *   1. keys: "bmashup" must be a table; [bmashup] takes only platform / requires; every other "bmashup.<t>" must be a
 *      table this host reads (bm_platform_table.h). An unknown table: "needs a newer platform".
 *   2. P-2 forward compatibility: a table whose integer version is newer than its reader takes -> "needs a newer
 *      platform" (checked for every table before step 3, so a newer table's new keys never read as typos).
 *   3. P-2 typo protection: at a version the host reads, a key the reader does not take refuses the mod (no longer the
 *      start: the readers' own refusal of the same key, exit 91 / 92 / 93, is now unreachable for a mod that passed
 *      here, and stays as the defence in depth).
 *   4. P-1 [bmashup] platform = ">=MAJOR.MINOR[.PATCH]": the host's BO3_PLATFORM_VERSION must be at least that.
 *   5. P-1 [bmashup] requires = ["name", "name>=N", ...]: each name is a service (bmashup.events, takedawn.race, ...)
 *      or a table ("bmashup.tracks"); the host must offer it at version N or newer.
 *   6. GP-DEPS1 (platform 0.1.2) [bmashup] requires_mods = ["<mod id>", "<mod id> >= X.Y[.Z]", ...]: the FORM only (a list of
 *      at most BO3_PLATFORM_MAX_REQUIRES_MODS strings, each read by bm_modreq.h, no id twice, never the mod's own id). Whether
 *      the other mods are there, on, usable, new enough and admitted is decided with the whole mod list (bm_admit.c).
 * Everything else (a missing or non-integer version, an out-of-range value, a conflict between mods) stays with the
 * table's own reader and keeps its exit code: those are declarations this host understands and cannot apply.
 * A mod without any [bmashup] key behaves as before.
 */
#include <stdlib.h>   /* strtoll */

#include "bm_modreq.h"
#include "bm_platform_table.h"

#define PX_MODS_HINT " (requires names services and tables; another mod goes in [bmashup] requires_mods)"

#define PX_SVC(name, ver, macro) { name, ver },
static const struct { const char *name; unsigned version; } s_px_services[] = { BO3_PLATFORM_SERVICES(PX_SVC) };
#undef PX_SVC
#define PX_TAB(t, ver, keys) { t, ver, keys },
static const struct { const char *name; int version; const char *keys; } s_px_tables[] = { BO3_PLATFORM_TABLES(PX_TAB) };
#undef PX_TAB
#define PX_NTAB ((int)(sizeof s_px_tables / sizeof s_px_tables[0]))

#ifndef P1_MUT
#define P1_MUT 0     /* tests only: one deliberate defect (tests\test_p1_platform.c) */
#endif

const char *bo3_manifest_platform_version(void)
{
    return BO3_PLATFORM_VERSION;
}

/* w (n bytes) is one of the space-separated words of list */
static int px_word_in(const char *list, const char *w, size_t n)
{
    const char *p = list;
    while (*p) {
        size_t k = strcspn(p, " ");
        if (k == n && !strncmp(p, w, n))
            return 1;
        p += k;
        while (*p == ' ')
            p++;
    }
    return 0;
}

static int px_table(const char *t, size_t n)
{
    for (int i = 0; i < PX_NTAB; i++)
        if (strlen(s_px_tables[i].name) == n && !strncmp(s_px_tables[i].name, t, n))
            return i;
    return -1;
}

/* "MAJOR.MINOR[.PATCH]", decimal parts 0..65535 */
static int px_version(const char *s, unsigned v[3])
{
    int parts = 0;
    v[0] = v[1] = v[2] = 0;
    for (;;) {
        unsigned long x = 0;
        int d = 0;
        while (*s >= '0' && *s <= '9' && d < 6) {
            x = x * 10 + (unsigned)(*s - '0');
            s++;
            d++;
        }
        if (!d || x > 65535 || parts == 3)
            return 0;
        v[parts++] = (unsigned)x;
        if (*s == 0)
            return parts >= 2;
        if (*s != '.')
            return 0;
        s++;
    }
}

static int px_cmp(const unsigned a[3], const unsigned b[3])
{
    for (int i = 0; i < 3; i++)
        if (a[i] != b[i])
            return a[i] < b[i] ? -1 : 1;
    return 0;
}

/* The version this host offers under name (a service, or "bmashup.<table>"), 0 when it offers none. */
static unsigned px_offered(const char *name)
{
    for (size_t i = 0; i < sizeof s_px_services / sizeof s_px_services[0]; i++)
        if (!strcmp(s_px_services[i].name, name))
            return s_px_services[i].version;
    if (!strncmp(name, "bmashup.", 8)) {
        int t = px_table(name + 8, strlen(name + 8));
        if (t >= 0)
            return (unsigned)s_px_tables[t].version;
    }
    return 0;
}

/* One requires entry: "name" or "name>=N" (spaces around ">=" allowed). 1 met; 0 with why. */
static int px_require(const char *e, char *why, size_t wn)
{
    char name[65];
    const char *ge = strstr(e, ">=");
    size_t n = ge ? (size_t)(ge - e) : strlen(e);
    long long need = 1;
    unsigned have;

    while (n && e[n - 1] == ' ')
        n--;
    if (!n || n >= sizeof name) {
        snprintf(why, wn, "bmashup.requires: \"%.40s\" is not \"name\" or \"name>=VERSION\"", e);
        return 0;
    }
    memcpy(name, e, n);
    name[n] = 0;
    for (size_t k = 0; k < n; k++)
        if (!((name[k] >= 'a' && name[k] <= 'z') || (name[k] >= '0' && name[k] <= '9') || name[k] == '.' ||
              name[k] == '_' || name[k] == '-')) {
            snprintf(why, wn, "bmashup.requires: \"%.40s\" is not \"name\" or \"name>=VERSION\"", e);
            return 0;
        }
    if (ge) {
        const char *s = ge + 2;
        char *end;
        while (*s == ' ')
            s++;
        need = strtoll(s, &end, 10);
        while (*end == ' ')
            end++;
        if (end == s || *end || need < 1 || need > 0x7FFFFFFF) {
            snprintf(why, wn, "bmashup.requires: \"%.40s\": the version must be a whole number from 1%s", e,
                     strchr(s, '.') ? PX_MODS_HINT : "");
            return 0;
        }
    }
    have = px_offered(name);
    if (!have) {
        snprintf(why, wn, "needs %s, which this host (platform %s) does not offer%s", name, BO3_PLATFORM_VERSION, PX_MODS_HINT);
        return 0;
    }
#if P1_MUT != 3
    if ((long long)have < need) {
#else
    if (0) {                                    /* defect: the required version is not compared */
#endif
        snprintf(why, wn, "needs %s >= %lld; this host (platform %s) offers version %u", name, need, BO3_PLATFORM_VERSION,
                 have);
        return 0;
    }
    return 1;
}

int bo3_manifest_platform_check(const char *text, size_t n, char *why, size_t wn)
{
    static char buf[BO3_MANIFEST_MAX_BYTES + 1];   /* one caller at a time (the mod list is made on one thread) */
    char err[160], key[96];
    recomp_cfg *cfg;
    unsigned present = 0;
    int ok = 1;

    if (wn)
        why[0] = 0;
    if (!text || n == 0 || n > BO3_MANIFEST_MAX_BYTES) {
        snprintf(why, wn, "mod.toml: not checked (empty or larger than %d bytes)", BO3_MANIFEST_MAX_BYTES);
        return 0;
    }
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    if (!cfg) {
        snprintf(why, wn, "mod.toml: %s", err);
        return 0;
    }
    /* 1. tables and [bmashup]'s own keys */
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i), *t, *dot;
        size_t tn;
        int ti;
        if (strncmp(k, "bmashup", 7) != 0 || (k[7] != 0 && k[7] != '.'))
            continue;
        if (k[7] == 0) {
            snprintf(why, wn, "bmashup must be a table ([bmashup])");
            ok = 0;
            break;
        }
        t = k + 8;
        dot = strchr(t, '.');
        tn = dot ? (size_t)(dot - t) : strlen(t);
        ti = px_table(t, tn);
        if (!dot && px_word_in(BO3_PLATFORM_OWN_KEYS, t, tn))
            continue;
        if (!dot && ti >= 0) {
            snprintf(why, wn, "bmashup.%s must be a table ([bmashup.%s])", s_px_tables[ti].name, s_px_tables[ti].name);
            ok = 0;
        } else if (ti < 0) {
#if P1_MUT != 1
            snprintf(why, wn, "needs a newer platform: [bmashup] has %.*s, which platform %s does not read", (int)(tn > 40 ? 40 : tn),
                     t, BO3_PLATFORM_VERSION);
            ok = 0;
#endif                                          /* P1_MUT 1, defect: an unknown table is ignored */
        } else {
            present |= 1u << ti;
        }
    }
    /* 2. a newer version of a table this host reads */
    for (int ti = 0; ok && ti < PX_NTAB; ti++) {
        long long v;
        if (!(present & (1u << ti)))
            continue;
        snprintf(key, sizeof key, "bmashup.%s.version", s_px_tables[ti].name);
        if (recomp_cfg_type_of(cfg, key) != RCFG_INT)
            continue;                           /* missing / not a whole number: the reader's refusal */
        v = recomp_cfg_int(cfg, key, 0);
#if P1_MUT != 2
        if (v > s_px_tables[ti].version) {
#else
        if (0) {                                /* defect: a newer version is taken as the host's own */
#endif
            snprintf(why, wn, "needs a newer platform: [bmashup.%s] version %lld; platform %s reads version %d",
                     s_px_tables[ti].name, v, BO3_PLATFORM_VERSION, s_px_tables[ti].version);
            ok = 0;
        }
    }
    /* 3. a key a table's reader does not take */
    for (size_t i = 0; ok && i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i), *sub;
        int ti;
        if (strncmp(k, "bmashup.", 8) != 0 || !strchr(k + 8, '.'))
            continue;
        ti = px_table(k + 8, (size_t)(strchr(k + 8, '.') - (k + 8)));
        if (ti < 0)
            continue;
        sub = strchr(k + 8, '.') + 1;
#if P1_MUT != 4
        if (!px_word_in(s_px_tables[ti].keys, sub, strlen(sub))) {
#else
        if (0) {                                /* defect: an unknown key is left to the reader (the start stops there) */
#endif
            snprintf(why, wn, "%.60s is not a key of [bmashup.%s] version %d (keys: %s): misspelt, or the mod needs a newer "
                     "platform", k, s_px_tables[ti].name, s_px_tables[ti].version, s_px_tables[ti].keys);
            ok = 0;
        }
    }
    /* 4. platform = ">=X.Y[.Z]" */
    if (ok && recomp_cfg_type_of(cfg, "bmashup.platform") != RCFG_NONE) {
        const char *s = recomp_cfg_type_of(cfg, "bmashup.platform") == RCFG_STRING ?
                        recomp_cfg_string(cfg, "bmashup.platform", "") : NULL;
        const unsigned host[3] = { BO3_PLATFORM_MAJOR, BO3_PLATFORM_MINOR, BO3_PLATFORM_PATCH };
        unsigned need[3];
        const char *v = s && !strncmp(s, ">=", 2) ? s + 2 : NULL;
        while (v && *v == ' ')
            v++;
        if (!v || !px_version(v, need)) {
            snprintf(why, wn, "bmashup.platform must be a string \">=MAJOR.MINOR[.PATCH]\" (this host is platform %s)",
                     BO3_PLATFORM_VERSION);
            ok = 0;
#if P1_MUT != 5
        } else if (px_cmp(host, need) < 0) {
#else
        } else if (px_cmp(host, need) < 0 && need[0] != host[0]) {   /* defect: only the major part is compared */
#endif
            snprintf(why, wn, "needs platform >=%s; this host is platform %s", v, BO3_PLATFORM_VERSION);
            ok = 0;
        }
    }
    /* 5. requires = ["name", "name>=N", ...] */
    if (ok && recomp_cfg_type_of(cfg, "bmashup.requires") != RCFG_NONE) {
        size_t cnt;
        if (recomp_cfg_type_of(cfg, "bmashup.requires") != RCFG_ARRAY) {
            snprintf(why, wn, "bmashup.requires must be a list of \"name\" or \"name>=VERSION\"");
            ok = 0;
        }
        cnt = ok ? recomp_cfg_array_len(cfg, "bmashup.requires") : 0;
        for (size_t i = 0; ok && i < cnt; i++) {
            if (recomp_cfg_array_type(cfg, "bmashup.requires", i) != RCFG_STRING) {
                snprintf(why, wn, "bmashup.requires[%u] must be a string", (unsigned)i);
                ok = 0;
            } else {
                ok = px_require(recomp_cfg_array_string(cfg, "bmashup.requires", i, ""), why, wn);
            }
        }
    }
    /* 6. GP-DEPS1: requires_mods = ["<mod id>", "<mod id> >= X.Y[.Z]", ...] - the form only (DEPS_MUT 1, tests only: not
     * checked - a malformed entry would then reach the admission, which refuses it there with its own reason) */
#if !defined(DEPS_MUT) || DEPS_MUT != 1
    if (ok && recomp_cfg_type_of(cfg, "bmashup.requires_mods") != RCFG_NONE) {
#else
    if (0) {
#endif
        size_t cnt = 0;
        const char *self = recomp_cfg_type_of(cfg, "id") == RCFG_STRING ? recomp_cfg_string(cfg, "id", "") : "";
        static bo3_modreq q[BO3_PLATFORM_MAX_REQUIRES_MODS];
        if (recomp_cfg_type_of(cfg, "bmashup.requires_mods") != RCFG_ARRAY) {
            snprintf(why, wn, "bmashup.requires_mods must be a list of \"<mod id>\" or \"<mod id> >= X.Y[.Z]\"");
            ok = 0;
        } else if ((cnt = recomp_cfg_array_len(cfg, "bmashup.requires_mods")) > BO3_PLATFORM_MAX_REQUIRES_MODS) {
            snprintf(why, wn, "bmashup.requires_mods names %u mods; at most %d", (unsigned)cnt, BO3_PLATFORM_MAX_REQUIRES_MODS);
            ok = 0;
        }
        for (size_t i = 0; ok && i < cnt; i++) {
            if (recomp_cfg_array_type(cfg, "bmashup.requires_mods", i) != RCFG_STRING) {
                snprintf(why, wn, "bmashup.requires_mods[%u] must be a string", (unsigned)i);
                ok = 0;
            } else if (!bo3_modreq_parse(recomp_cfg_array_string(cfg, "bmashup.requires_mods", i, ""), &q[i], why, wn)) {
                ok = 0;
            } else if (!strcmp(q[i].id, self)) {
                snprintf(why, wn, "bmashup.requires_mods: the mod requires itself (%.64s)", self);
                ok = 0;
            } else {
                for (size_t j = 0; ok && j < i; j++)
                    if (!strcmp(q[j].id, q[i].id)) {
                        snprintf(why, wn, "bmashup.requires_mods names %.64s twice", q[i].id);
                        ok = 0;
                    }
            }
        }
    }
    recomp_cfg_free(cfg);
    return ok;
}
