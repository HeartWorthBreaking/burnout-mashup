/*
 * bm_modreq.h - GP-DEPS1 (platform 0.1.2): one entry of a mod.toml's [bmashup] requires_mods, and the comparison of a mod
 * version with a required one. Header-only (static functions) so that the platform gate (modmanifest.c via
 * bm_platform_gate.inc) and the admission (bm_admit.c) read an entry the SAME way without a new link dependency.
 *
 * Entry: "<mod id>" (any version) or "<mod id> >= X.Y[.Z[.W]]" (spaces around ">=" allowed). The id follows the mod id rule
 * (modmanifest.h: [a-z0-9] then [a-z0-9._-], 1..64 bytes). Only ">=" exists: no upper bounds, no ranges, no "==" (a later
 * platform can add operators; an entry with another operator is refused, never misread).
 * Installed versions (bo3_manifest.version, free text "[0-9A-Za-z] then [0-9A-Za-z.+-]") compare by their leading numeric
 * dotted parts (missing parts = 0); "+build" is ignored; a "-prerelease" ranks BELOW the same numbers (1.0.2-rc1 < 1.0.2), so a
 * prerelease meets ">= V" only when its numbers are strictly greater than V. A version that does not start with a number
 * (or is absent) cannot be compared: it meets only an entry without a version.
 */
#ifndef BO3_BM_MODREQ_H
#define BO3_BM_MODREQ_H

#include <stdio.h>
#include <string.h>

#define BO3_MODREQ_ID_MAX 64

typedef struct bo3_modreq {
    char id[BO3_MODREQ_ID_MAX + 1];
    int has_ver;                       /* 0: any version */
    unsigned ver[4];
    char text[24];                     /* the version as written ("1.0.2"), "" when none */
} bo3_modreq;

static inline int bo3_modreq_id_ok(const char *s, size_t n)
{
    if (!n || n > BO3_MODREQ_ID_MAX)
        return 0;
    for (size_t i = 0; i < n; i++) {
        char c = s[i];
        int alnum = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
        if (!(alnum || (i && (c == '.' || c == '_' || c == '-'))))
            return 0;
    }
    return 1;
}

/* "X[.Y[.Z[.W]]]" (1..4 parts, each 0..65535). *end = the first character after the numbers. 1 ok. */
static inline int bo3_modreq_nums(const char *s, unsigned v[4], int *parts, const char **end)
{
    int p = 0;
    v[0] = v[1] = v[2] = v[3] = 0;
    for (;;) {
        unsigned long x = 0;
        int d = 0;
        while (*s >= '0' && *s <= '9' && d < 6) {
            x = x * 10 + (unsigned)(*s - '0');
            s++;
            d++;
        }
        if (!d || x > 65535 || p == 4)
            return 0;
        v[p++] = (unsigned)x;
        if (*s != '.' || !(s[1] >= '0' && s[1] <= '9'))
            break;
        s++;
    }
    *parts = p;
    *end = s;
    return 1;
}

/* Parses one entry. 1 with *q filled; 0 with a one-line reason in why. */
static inline int bo3_modreq_parse(const char *e, bo3_modreq *q, char *why, size_t wn)
{
    const char *ge, *s, *end;
    size_t n;
    int parts;
    memset(q, 0, sizeof *q);
    if (!e) {
        snprintf(why, wn, "bmashup.requires_mods: an entry is not a string");
        return 0;
    }
    while (*e == ' ')
        e++;
    ge = strstr(e, ">=");
    n = ge ? (size_t)(ge - e) : strcspn(e, " <>=!~^");
    {
        size_t k = n;
        while (k && e[k - 1] == ' ')
            k--;
        if (!bo3_modreq_id_ok(e, k)) {
            snprintf(why, wn, "bmashup.requires_mods: \"%.48s\" is not \"<mod id>\" or \"<mod id> >= X.Y[.Z]\" (a mod id is "
                     "[a-z0-9] then [a-z0-9._-], at most 64 characters)", e);
            return 0;
        }
        memcpy(q->id, e, k);
        q->id[k] = 0;
    }
    if (!ge) {
        s = e + n;
        while (*s == ' ')
            s++;
        if (*s) {
            snprintf(why, wn, "bmashup.requires_mods: \"%.48s\": the only version condition is \">= X.Y[.Z]\"", e);
            return 0;
        }
        return 1;
    }
    s = ge + 2;
    while (*s == ' ')
        s++;
    if (!bo3_modreq_nums(s, q->ver, &parts, &end)) {
        snprintf(why, wn, "bmashup.requires_mods: \"%.48s\": the version must be X.Y[.Z] (numbers 0..65535)", e);
        return 0;
    }
    {
        const char *t = end;
        while (*t == ' ')
            t++;
        if (*t) {
            snprintf(why, wn, "bmashup.requires_mods: \"%.48s\": the version must be X.Y[.Z] (numbers 0..65535), nothing after it",
                     e);
            return 0;
        }
        if ((size_t)(end - s) >= sizeof q->text) {
            snprintf(why, wn, "bmashup.requires_mods: \"%.48s\": the version is too long", e);
            return 0;
        }
        memcpy(q->text, s, (size_t)(end - s));
        q->text[end - s] = 0;
    }
    q->has_ver = 1;
    return 1;
}

/* 1: the installed version meets q; 0: older; -1: it cannot be compared (no leading number) */
static inline int bo3_modreq_met(const bo3_modreq *q, const char *installed)
{
    unsigned v[4];
    int parts, c = 0;
    const char *end;
    if (!q->has_ver)
        return 1;
    if (!installed || !bo3_modreq_nums(installed, v, &parts, &end))
        return -1;
    if (*end && *end != '-' && *end != '+')
        return -1;
    for (int i = 0; i < 4 && !c; i++)
        c = v[i] < q->ver[i] ? -1 : v[i] > q->ver[i] ? 1 : 0;
    if (c == 0 && *end == '-')
        c = -1;                        /* a prerelease of exactly the required numbers is older than it */
    return c >= 0;
}

#endif
