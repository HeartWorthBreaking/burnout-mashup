/* G8-CC1 EXPERIMENTAL: additional track entries declared by mods (bm_tracks.h). MUT=n (test builds only) compiles one
 * deliberate defect. G8-TL: MUT 7 the flags of entry 128 written into the buffer (flag B's entry 0), MUT 8 one track more
 * than the format holds, MUT 9 the region letter range off by one (Z refused), MUT 10 a mod's 384th declaration accepted.
 * cand2 (D2): MUT 45 a host guest-memory failure reported as a mod's bad declaration (the old game_fail("(host)")). */
#include "bm_tracks.h"

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "recomp_cfg.h"
#include "bm_regions.h"          /* G8-RG1: the region of an added track from its ID */

#ifndef MUT
#define MUT 0
#endif

#define CC_PREFIX "bmashup.tracks"
static const char k_al[] = " -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_";

int bo3_cc_encode(const char *s, uint64_t *out)
{
    uint64_t v = 0;
    size_t n = strlen(s);
    if (n == 0 || n > 12)
        return 0;
    for (size_t i = 0; i < 12; i++) {
        char c = i < n ? s[i] : ' ';
        const char *p = c ? strchr(k_al, c) : NULL;
        if (!p)
            return 0;
        v = v * 40u + (uint64_t)(p - k_al);
    }
    *out = v;
    return 1;
}

void bo3_cc_decode(uint64_t v, char out[13])
{
    for (int i = 11; i >= 0; i--) {
        out[i] = k_al[v % 40u];
        v /= 40u;
    }
    out[12] = 0;
    for (int i = 11; i >= 0 && out[i] == ' '; i--)
        out[i] = 0;
}

int bo3_cc_id_ok(const char *s, char *why, size_t wn)
{
    uint64_t v;
    if (strlen(s) != 8 || s[2] != '_' || s[5] != '_' || !bo3_cc_encode(s, &v)) {
        snprintf(why, wn, "\"%s\" is not a track ID of the form RR_NN_VN (upper-case letters and digits)", s);
        return 0;
    }
    for (int i = 0; i < 8; i++)
        if (i != 2 && i != 5 && !((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9'))) {
            snprintf(why, wn, "\"%s\" is not a track ID of the form RR_NN_VN (upper-case letters and digits)", s);
            return 0;
        }
#if MUT != 1
    if (strncmp(s, "US", 2) && strncmp(s, "EU", 2) && strncmp(s, "AS", 2) && bo3_cc_region_of_letter(s[0]) < 0) {
        snprintf(why, wn, "\"%s\": region %.2s is not one the game has (US, EU, AS), and no mod declares the letter %c as an "
                 "added region (a fourth region or later, [bmashup.regions])", s, s, s[0]);
        return 0;
    }
#endif
    return 1;
}

/* ---- G8-RG4: declared fourth regions ([bmashup.regions]) ---- */
#define RG_PREFIX "bmashup.regions"
static bo3_cc_region s_reg[BO3_CC_REGIONS_MAX];
static uint32_t s_nreg;

static int rg_char_ok(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' ||
           c == '\'' || c == '.' || c == '&';
}

/* "A = B" (spaces around trimmed): 1 with a / b, else 0 */
static int rg_split(const char *s, char *a, size_t an, char *b, size_t bn)
{
    char line[160], *eq, *x, *y;
    if (!s || strlen(s) >= sizeof line)
        return 0;
    strcpy(line, s);
    if (!(eq = strchr(line, '=')))
        return 0;
    *eq = 0;
    for (x = line; *x == ' '; x++)
        ;
    for (char *e = x + strlen(x); e > x && e[-1] == ' ';)
        *--e = 0;
    for (y = eq + 1; *y == ' '; y++)
        ;
    for (char *e = y + strlen(y); e > y && e[-1] == ' ';)
        *--e = 0;
    if (strlen(x) >= an || strlen(y) >= bn)
        return 0;
    strcpy(a, x);
    strcpy(b, y);
    return 1;
}

int bo3_cc_regions_parse(const char *text, size_t n, char *why, size_t wn)
{
    char err[200], a[64], b[64];
    size_t plen = strlen(RG_PREFIX), na = 0, nd = 0;
    bo3_cc_region add[BO3_CC_REGIONS_MAX + 1];
    uint32_t nadd = 0, nnew = 0;
    recomp_cfg *cfg;
    char *buf;
    int ok = 1, present = 0;

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
        if (strncmp(k, RG_PREFIX, plen) != 0 || (k[plen] != 0 && k[plen] != '.'))
            continue;
        present = 1;
        if (k[plen] == 0 || (strcmp(k, RG_PREFIX ".version") && strcmp(k, RG_PREFIX ".add") && strcmp(k, RG_PREFIX ".dj"))) {
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, add, dj)", k, RG_PREFIX);
            ok = 0;
        }
    }
    if (ok && present) {
        if (recomp_cfg_type_of(cfg, RG_PREFIX ".version") != RCFG_INT || recomp_cfg_int(cfg, RG_PREFIX ".version", 0) != 1) {
            snprintf(why, wn, "%s.version must be 1 (the only version this build reads)", RG_PREFIX);
            ok = 0;
        } else if (recomp_cfg_type_of(cfg, RG_PREFIX ".add") != RCFG_ARRAY || !(na = recomp_cfg_array_len(cfg, RG_PREFIX ".add"))) {
            snprintf(why, wn, "%s.add must be a list of \"LETTER = TEXT\" (at least one)", RG_PREFIX);
            ok = 0;
        } else if (na > BO3_CC_REGIONS_MAX) {
            snprintf(why, wn, "%s.add lists %u regions; at most %u can exist (one per letter A-Z other than U, E, A)",
                     RG_PREFIX, (unsigned)na, (unsigned)BO3_CC_REGIONS_MAX);
            ok = 0;
        }
    }
    for (size_t i = 0; ok && present && i < na; i++) {
        const char *s = recomp_cfg_array_type(cfg, RG_PREFIX ".add", i) == RCFG_STRING ?
                        recomp_cfg_array_string(cfg, RG_PREFIX ".add", i, NULL) : NULL;
        size_t len;
        if (!rg_split(s, a, sizeof a, b, sizeof b)) {
            snprintf(why, wn, "%s.add[%u] is not \"LETTER = TEXT\"", RG_PREFIX, (unsigned)i);
            ok = 0;
            break;
        }
#if MUT != 9
        if (strlen(a) != 1 || a[0] < 'A' || a[0] > 'Z' || a[0] == 'U' || a[0] == 'E' || a[0] == 'A') {
#else
        if (strlen(a) != 1 || a[0] < 'A' || a[0] >= 'Z' || a[0] == 'U' || a[0] == 'E' || a[0] == 'A') {   /* defect: no Z */
#endif
            snprintf(why, wn, "%s.add: \"%s\" is not a region letter (one of A-Z other than U, E, A, the game's own "
                     "regions)", RG_PREFIX, a);
            ok = 0;
            break;
        }
        len = strlen(b);
        if (len == 0 || len > BO3_CC_REGION_TEXT_MAX) {
            snprintf(why, wn, "%s.add: the text for %s has %u characters; 1 .. %u fit the game's menus", RG_PREFIX, a,
                     (unsigned)len, (unsigned)BO3_CC_REGION_TEXT_MAX);
            ok = 0;
            break;
        }
        for (size_t k = 0; ok && k < len; k++)
            if (!rg_char_ok(b[k])) {
                snprintf(why, wn, "%s.add: the text for %s has the character '%c'; use A-Z a-z 0-9, space and - ' . &",
                         RG_PREFIX, a, b[k]);
                ok = 0;
            }
        for (uint32_t k = 0; ok && k < nadd; k++)
            if (add[k].letter == a[0]) {
                snprintf(why, wn, "%s.add lists the letter %c twice", RG_PREFIX, a[0]);
                ok = 0;
            }
        if (!ok)
            break;
        memset(&add[nadd], 0, sizeof add[nadd]);
        add[nadd].letter = a[0];
        memcpy(add[nadd].text, b, len + 1);
        add[nadd].dj = 0;                       /* default: DJUS (PLACEHOLDER) */
        nadd++;
    }
    if (ok && present && recomp_cfg_type_of(cfg, RG_PREFIX ".dj") != RCFG_NONE) {
        if (recomp_cfg_type_of(cfg, RG_PREFIX ".dj") != RCFG_ARRAY) {
            snprintf(why, wn, "%s.dj must be a list of \"LETTER = BANK\"", RG_PREFIX);
            ok = 0;
        } else {
            nd = recomp_cfg_array_len(cfg, RG_PREFIX ".dj");
        }
        for (size_t i = 0; ok && i < nd; i++) {
            const char *s = recomp_cfg_array_type(cfg, RG_PREFIX ".dj", i) == RCFG_STRING ?
                            recomp_cfg_array_string(cfg, RG_PREFIX ".dj", i, NULL) : NULL;
            uint32_t k, bank;
            if (!rg_split(s, a, sizeof a, b, sizeof b)) {
                snprintf(why, wn, "%s.dj[%u] is not \"LETTER = BANK\"", RG_PREFIX, (unsigned)i);
                ok = 0;
                break;
            }
            for (k = 0; k < nadd && !(strlen(a) == 1 && add[k].letter == a[0]); k++)
                ;
            if (k == nadd) {
                snprintf(why, wn, "%s.dj names \"%s\", which is not in this mod's add list", RG_PREFIX, a);
                ok = 0;
                break;
            }
            bank = !strcmp(b, "DJUS") ? 0u : !strcmp(b, "DJEU") ? 1u : !strcmp(b, "DJAS") ? 2u : 3u;
            if (bank == 3u) {
                snprintf(why, wn, "%s.dj: \"%s\" is not one of the game's banks DJUS, DJEU, DJAS (phase 1: a retail bank "
                         "only)", RG_PREFIX, b);
                ok = 0;
                break;
            }
            add[k].dj = bank;
        }
    }
    recomp_cfg_free(cfg);
    if (!ok)
        return 0;
    /* merge: the same letter from another mod must say the same; check everything before keeping anything */
    for (uint32_t i = 0; i < nadd; i++) {
        int k = bo3_cc_region_of_letter(add[i].letter);
        if (k >= 0) {
            if (strcmp(s_reg[k].text, add[i].text) || s_reg[k].dj != add[i].dj) {
                snprintf(why, wn, "%s.add: the letter %c is already declared by another mod as \"%s\" (bank %u)", RG_PREFIX,
                         add[i].letter, s_reg[k].text, (unsigned)s_reg[k].dj);
                return 0;
            }
        } else {
            nnew++;
        }
    }
    if (s_nreg + nnew > BO3_CC_REGIONS_MAX) {      /* (defensive: 23 letters can be declared, the table holds 23) */
        snprintf(why, wn, "%s.add: %u regions are declared already and this mod adds %u; at most %u can exist", RG_PREFIX,
                 (unsigned)s_nreg, (unsigned)nnew, (unsigned)BO3_CC_REGIONS_MAX);
        return 0;
    }
    for (uint32_t i = 0; i < nadd; i++)
        if (bo3_cc_region_of_letter(add[i].letter) < 0)
            s_reg[s_nreg++] = add[i];
    return 1;
}

uint32_t bo3_cc_region_count(void)
{
    return s_nreg;
}

const bo3_cc_region *bo3_cc_region_at(uint32_t k)
{
    return k < s_nreg ? &s_reg[k] : NULL;
}

int bo3_cc_region_of_letter(char c)
{
    for (uint32_t k = 0; k < s_nreg; k++)
        if (s_reg[k].letter == c)
            return (int)k;
    return -1;
}

void bo3_cc_regions_reset(void)
{
    s_nreg = 0;
    memset(s_reg, 0, sizeof s_reg);
}

int bo3_cc_parse(const char *text, size_t n, bo3_cc_decl *out, char *why, size_t wn)
{
    char err[200], key[96];
    size_t plen = strlen(CC_PREFIX);
    recomp_cfg *cfg;
    char *buf;
    int ok = 1;

    memset(out, 0, sizeof *out);
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
        if (strncmp(k, CC_PREFIX, plen) != 0 || (k[plen] != 0 && k[plen] != '.'))
            continue;
        out->present = 1;
        if (k[plen] == 0 || (strcmp(k, CC_PREFIX ".version") && strcmp(k, CC_PREFIX ".add") &&
                             strcmp(k, CC_PREFIX ".point_to_point") && strcmp(k, CC_PREFIX ".names") &&
                             strcmp(k, CC_PREFIX ".locations"))) {   /* G8-NM1: names / locations (bm_names.c) */
            snprintf(why, wn, "%s is not a key this build reads ([%s] version 1: version, add, point_to_point, names, "
                     "locations)", k, CC_PREFIX);
            ok = 0;
        }
    }
    if (ok && out->present) {
        if (recomp_cfg_type_of(cfg, CC_PREFIX ".version") != RCFG_INT || recomp_cfg_int(cfg, CC_PREFIX ".version", 0) != 1) {
            snprintf(why, wn, "%s.version must be 1 (the only version this build reads)", CC_PREFIX);
            ok = 0;
        } else if (recomp_cfg_type_of(cfg, CC_PREFIX ".add") != RCFG_ARRAY) {
            snprintf(why, wn, "%s.add must be a list of track IDs", CC_PREFIX);
            ok = 0;
        }
    }
    if (ok && out->present) {
        size_t na = recomp_cfg_array_len(cfg, CC_PREFIX ".add");
#if MUT != 10
        if (na > BO3_CC_MAX_DECL) {
#else
        if (na > BO3_CC_MAX_DECL + 1u) {        /* defect: one declaration more than the table holds */
#endif
            snprintf(why, wn, "%s.add lists %u tracks; one mod may add at most %u", CC_PREFIX, (unsigned)na,
                     (unsigned)BO3_CC_MAX_DECL);
            ok = 0;
        }
        for (size_t i = 0; ok && i < na; i++) {
            const char *s = recomp_cfg_array_type(cfg, CC_PREFIX ".add", i) == RCFG_STRING ?
                            recomp_cfg_array_string(cfg, CC_PREFIX ".add", i, "") : NULL;
            if (!s) {
                snprintf(why, wn, "%s.add[%u] is not a string", CC_PREFIX, (unsigned)i);
                ok = 0;
            } else if (bo3_cc_id_ok(s, why, wn)) {
                bo3_cc_encode(s, &out->id[i]);
                for (size_t j = 0; j < i; j++)
                    if (out->id[j] == out->id[i]) {
                        snprintf(why, wn, "%s.add lists %s twice", CC_PREFIX, s);
                        ok = 0;
                    }
                out->n = (uint32_t)(i + 1);
            } else {
                ok = 0;
            }
        }
        if (ok && recomp_cfg_type_of(cfg, CC_PREFIX ".point_to_point") != RCFG_NONE) {
            size_t np = recomp_cfg_array_len(cfg, CC_PREFIX ".point_to_point");
            if (recomp_cfg_type_of(cfg, CC_PREFIX ".point_to_point") != RCFG_ARRAY)
                np = 0, ok = 0, snprintf(why, wn, "%s.point_to_point must be a list of track IDs", CC_PREFIX);
            for (size_t i = 0; ok && i < np; i++) {
                const char *s = recomp_cfg_array_type(cfg, CC_PREFIX ".point_to_point", i) == RCFG_STRING ?
                                recomp_cfg_array_string(cfg, CC_PREFIX ".point_to_point", i, "") : "";
                uint64_t v = 0;
                uint32_t j;
                bo3_cc_encode(s, &v);
                for (j = 0; j < out->n && out->id[j] != v; j++)
                    ;
                if (j == out->n || !*s) {
                    snprintf(key, sizeof key, "%s", s);
                    snprintf(why, wn, "%s.point_to_point names \"%s\", which is not in add", CC_PREFIX, key);
                    ok = 0;
                } else {
                    out->p2p[j] = 1;
                }
            }
        }
    }
    recomp_cfg_free(cfg);
    if (!ok)
        out->n = 0;
    return ok;
}

static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }

/* G8-TL: the flags of entries BO3_CC_FLAG_CAP .. BO3_CC_CAP - 1 (the buffer's flag arrays end at 128) */
static uint32_t s_xflag[2][BO3_CC_CAP - BO3_CC_FLAG_CAP];

uint32_t bo3_cc_flag_ext(uint32_t i, uint32_t which)
{
    return i >= BO3_CC_FLAG_CAP && i < BO3_CC_CAP && which < 2u ? s_xflag[which][i - BO3_CC_FLAG_CAP] : 0u;
}

uint32_t bo3_cc_flag(const uint8_t *t, uint32_t i, uint32_t which)
{
    if (which > 1u)
        return 0;
    if (i < BO3_CC_FLAG_CAP)
        return rd32(t + (which ? BO3_CC_OFF_B : BO3_CC_OFF_A) + 4u * i);
    return bo3_cc_flag_ext(i, which);
}

void bo3_cc_flags_reset(void)
{
    memset(s_xflag, 0, sizeof s_xflag);
}

int bo3_cc_append(uint8_t *t, const bo3_cc_decl *d, int mod, bo3_cc_files_fn files, void *user, char *why, size_t wn)
{
    static const char *const k_files[4] = {"Gamedata.bgd", "static.dat", "streamed.dat", "enviro.dat"};
    uint32_t n = rd32(t + 4);
    char name[13], rel[64];

    if (n > BO3_CC_CAP) {
        snprintf(why, wn, "the game's track list says %u tracks, above its format's %u", (unsigned)n, (unsigned)BO3_CC_CAP);
        return 0;
    }
#if MUT != 2
#if MUT != 8
    if (n + d->n > BO3_CC_CAP) {
#else
    if (n + d->n > BO3_CC_CAP + 1u) {           /* defect: one entry past the buffer */
#endif
        snprintf(why, wn, "%u more tracks would exceed the track list's %u (it has %u; the IDs fill the game's 0x1000-byte "
                 "buffer)", (unsigned)d->n, (unsigned)BO3_CC_CAP, (unsigned)n);
        return 0;
    }
#endif
    /* check everything first: nothing is written unless every declared track can be taken */
    for (uint32_t i = 0; i < d->n; i++) {
        uint32_t in_region = 0;
        bo3_cc_decode(d->id[i], name);
        for (uint32_t k = 0; k < n; k++) {
            char other[13];
            uint64_t have = (uint64_t)rd32(t + BO3_CC_OFF_ID + 8u * k) | (uint64_t)rd32(t + BO3_CC_OFF_ID + 8u * k + 4u) << 32;
            bo3_cc_decode(have, other);
            in_region += other[0] == name[0];
        }
        for (uint32_t k = 0; k < i; k++) {
            char other[13];
            bo3_cc_decode(d->id[k], other);
            in_region += other[0] == name[0];
        }
#if MUT != 5
        if (in_region + 1 > BO3_CC_REGION_LIST) {
            snprintf(why, wn, "%s: region %.2s would have %u tracks; the Single Event track list holds %u (+ Random)", name,
                     name, (unsigned)(in_region + 1), (unsigned)BO3_CC_REGION_LIST);
            return 0;
        }
#else
        (void)in_region;                        /* defect: the Single Event list is not checked */
#endif
#if MUT != 3
        for (uint32_t k = 0; k < n; k++) {
            uint64_t have = (uint64_t)rd32(t + BO3_CC_OFF_ID + 8u * k) | (uint64_t)rd32(t + BO3_CC_OFF_ID + 8u * k + 4u) << 32;
            if (have == d->id[i]) {
                snprintf(why, wn, "%s is already a track (entry %u): a track mod adds a new ID, it does not replace one",
                         name, (unsigned)k);
                return 0;
            }
        }
#endif
        for (int f = 0; f < 4; f++) {
            snprintf(rel, sizeof rel, "Tracks\\%.2s\\%.2s_%.2s\\%s", name, name + 3, name + 6, k_files[f]);
            if (!files || !files(user, mod, rel)) {
                snprintf(why, wn, "%s: its files folder has no %s", name, rel);
                return 0;
            }
        }
    }
    for (uint32_t i = 0; i < d->n; i++, n++) {
        uint32_t fa, fb;
        bo3_cc_decode(d->id[i], name);
        fa = d->p2p[i] ? 1u : 0u;
        fb = strncmp(name, "AS", 2) ? 1u : 0u;  /* as retail: 0 for AS, 1 for US / EU (and the declared regions) */
#if MUT != 7
        if (n < BO3_CC_FLAG_CAP) {
#else
        if (n <= BO3_CC_FLAG_CAP) {             /* defect: entry 128's flags land on flag B's / the IDs' first entry */
#endif
            wr32(t + BO3_CC_OFF_A + 4u * n, fa);
            wr32(t + BO3_CC_OFF_B + 4u * n, fb);
        } else if (n < BO3_CC_CAP) {            /* G8-TL: the buffer's flag arrays end at 128 */
            s_xflag[0][n - BO3_CC_FLAG_CAP] = fa;
            s_xflag[1][n - BO3_CC_FLAG_CAP] = fb;
        }
        wr32(t + BO3_CC_OFF_ID + 8u * n, (uint32_t)d->id[i]);
        wr32(t + BO3_CC_OFF_ID + 8u * n + 4u, (uint32_t)(d->id[i] >> 32));
    }
    wr32(t + 4, n);
    return 1;
}

static _Atomic uint32_t s_skips[BO3_CC_SITES];

int bo3_cc_gen_skip(uint32_t site, uint32_t index)
{
#if MUT == 4
    (void)site; (void)index;
    return 0;                                   /* defect: the guard never skips */
#else
    static const char *const k_site[BO3_CC_SITES] = {"per-track best (sub_0001BA00)", "per-track best 2 (sub_0001BAF0)",
                                                     "per-track records (sub_0001EE80)"};
    if ((int32_t)index >= 0 || site >= BO3_CC_SITES)
        return 0;
    if (atomic_fetch_add(&s_skips[site], 1) == 0)
        fprintf(stderr, "[TRACKS] %s: the track is not in the game's 36-entry table (an added track): not recorded, "
                "nothing written\n", k_site[site]);
    return 1;
#endif
}

uint32_t bo3_cc_skips(uint32_t site)
{
    return site < BO3_CC_SITES ? atomic_load(&s_skips[site]) : 0;
}

/* G8-CC1.1 F1: the records panel's stand-in for record -1 */
static uint32_t s_empty_va;
static _Atomic uint32_t s_redirects;

void bo3_cc_fill_empty_record(uint8_t *rec)
{
    bo3_cc_fresh_record(rec, 0x7F7FFFFFu);     /* G8-CC1.2: a fresh record as the game makes one (owners 0xFF, no time) */
}

void bo3_cc_set_empty_record_va(uint32_t va)
{
    s_empty_va = va;
}

uint32_t bo3_cc_gen_record(uint32_t rec_va)
{
#if MUT == 6
    (void)s_empty_va;
    return rec_va;                              /* defect: record -1 is used as it is */
#else
    if (rec_va == BO3_CC_RECORD_MINUS1) {      /* G8-CC1.2: the raced added track's own shadow record */
        uint32_t s = bo3_cc_current_shadow();
        if (s)
            return s;
    }
    if (rec_va != BO3_CC_RECORD_MINUS1 || !s_empty_va)
        return rec_va;
    if (atomic_fetch_add(&s_redirects, 1) == 0)
        fprintf(stderr, "[TRACKS] records panel (sub_000EAC60): an added track has no records: an empty stand-in record "
                "at 0x%08X is shown instead of 0x%08X\n", (unsigned)s_empty_va, (unsigned)rec_va);
    return s_empty_va;
#endif
}

uint32_t bo3_cc_record_redirects(void)
{
    return atomic_load(&s_redirects);
}
#ifdef BO3_TRACKS_GAME
#include "modfs.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t align);
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

static void game_fail(const char *mod_id, const char *why)
{
    fprintf(stderr, "[TRACKS] FATAL: mod %s declares a track this build cannot add: %s\n", mod_id, why);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: a mod's track cannot be added",
              "The mod \"%s\" declares in its mod.toml ([bmashup.tracks]) a track this build cannot add:\n%s\n\n"
              "Turn the mod off, or fix its declaration.", mod_id, why);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(92);
}

/* cand2 (D2): the host itself is out of guest memory (xbox_HeapAlloc returned 0). Not a mod's declaration: say so, which
 * service and how many bytes. Same exit (92) and the same FATAL line / drain / box / drain order as game_fail. */
static void host_fail(const char *what, uint32_t size)
{
#if MUT == 45
    char why[400];
    snprintf(why, sizeof why, "no guest memory for %s (%u bytes)", what, (unsigned)size);
    game_fail("(host)", why);                   /* defect: blames a mod "(host)" and tells the player to turn it off */
#else
    fprintf(stderr, "[TRACKS] FATAL: host out of guest memory: no guest memory for %s (%u bytes requested by the track "
            "list service bm_tracks); not caused by a mod's declaration (code 92)\n", what, (unsigned)size);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: out of guest memory",
              "The host ran out of guest memory while adding the mods' tracks: the track list service (bm_tracks) "
              "could not allocate %u bytes for %s.\n\nThis is not an error in a mod's declaration. Starting with fewer "
              "mods that add tracks or regions may help.", (unsigned)size, what);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(92);
#endif
}

/* rel inside mod m's files folder (the folder modfs serves the mod's files from) */
static int game_files(void *user, int mod, const char *rel)
{
    const bo3_mod *m = bo3_modfs_mod(mod);
    char path[BO3_MODFS_PATH_MAX + 80];
    FILE *f;
    (void)user;
    if (!m)
        return 0;
    snprintf(path, sizeof path, "%s\\files\\%s", m->folder, rel);
    f = fopen(path, "rb");
    if (!f)
        return 0;
    fclose(f);
    return 1;
}

/* G8-RG4: every usable, enabled mod's [bmashup.regions], once, before any track ID is checked */
void bo3_cc_regions_game_load(void)
{
    static int done;
    if (done)
        return;
    done = 1;
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[300];
        char *text = NULL;
        size_t n = 0;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_cc_regions_parse(text, n, why, sizeof why)) {
            free(text);
            fprintf(stderr, "[REGION4] FATAL: mod %s declares a region this build cannot add: %s\n", m->manifest.id, why);
            game_fail(m->manifest.id, why);
        }
        free(text);
    }
    for (uint32_t k = 0; k < s_nreg; k++)
        fprintf(stderr, "[REGION4] declared region %c = %s: code %u, DJ bank %s (PLACEHOLDER: a retail bank)\n", s_reg[k].letter,
                s_reg[k].text, (unsigned)(BO3_RG4_CODE0 + k), s_reg[k].dj == 1 ? "DJEU" : s_reg[k].dj == 2 ? "DJAS" : "DJUS");
    if (s_nreg) {                               /* G8-TL: one line naming every region, in code order */
        char all[BO3_CC_REGIONS_MAX * (BO3_CC_REGION_TEXT_MAX + 12u) + 1u] = "";
        for (uint32_t k = 0; k < s_nreg; k++)
            snprintf(all + strlen(all), sizeof all - strlen(all), "%s%u %c %s", k ? ", " : "", (unsigned)(BO3_RG4_CODE0 + k),
                     s_reg[k].letter, s_reg[k].text);
        fprintf(stderr, "[REGION4] %u declared region(s) of at most %u (codes by declaration order, never saved): %s\n",
                (unsigned)s_nreg, (unsigned)BO3_CC_REGIONS_MAX, all);
    }
}

void bo3_cc_gen_tlist_loaded(void)
{
    uint8_t *t;
    int added = 0;
    if (!g_xbox_mem_offset)
        return;
    bo3_cc_regions_game_load();                 /* G8-RG4: the declared letters before any ID is checked */
    t = (uint8_t *)((uintptr_t)g_xbox_mem_offset + BO3_CC_TLIST_VA);
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[300], name[13];
        char *text = NULL;
        size_t n = 0;
        bo3_cc_decl d;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_cc_parse(text, n, &d, why, sizeof why)) {
            free(text);
            game_fail(m->manifest.id, why);
        }
        free(text);
        if (!d.present || !d.n)
            continue;
        if (!bo3_cc_append(t, &d, i, game_files, NULL, why, sizeof why))
            game_fail(m->manifest.id, why);
        for (uint32_t k = 0; k < d.n; k++) {
            uint32_t sva = xbox_HeapAlloc(BO3_CC_RECORD_SIZE, 16u);   /* G8-CC1.2: the track's shadow record */
            bo3_cc_decode(d.id[k], name);
            if (!sva) {                          /* cand2 (D2): the host's failure, not the mod's */
                char what[200];
                snprintf(what, sizeof what, "the added track's records of %s (declared by mod %s)", name, m->manifest.id);
                host_fail(what, BO3_CC_RECORD_SIZE);
            }
            bo3_cc_progress_add(m->manifest.id, m->manifest.version, d.id[k], name, sva);
            bo3_rg_register(d.id[k]);    /* G8-RG1: its region, from its ID (bm_regions.c) */
            fprintf(stderr, "[TRACKS] mod %s adds track %s (entry %u%s): no name, map data or progress slot of its own\n",
                    m->manifest.id, name, (unsigned)(rd32(t + 4) - d.n + k), d.p2p[k] ? ", point-to-point" : "");
        }
        added += (int)d.n;
    }
    if (s_nreg)                                 /* G8-RG4: the region row's host blocks (nothing when none is declared) */
        bo3_rg4_prepare(xbox_HeapAlloc);
    if (!bo3_tl_prepare(xbox_HeapAlloc)) {      /* G8-TL: the Single Event list block, when a region's list passes 20 */
        char what[200];                         /* cand2 (D2): the host's failure; the limits as they are since G8-TL */
        snprintf(what, sizeof what, "the Single Event track list block (needed when a region lists more than the game's "
                 "own %u rows; it holds Random + up to %u tracks per region)", (unsigned)BO3_TL_GAME_ROWS,
                 (unsigned)BO3_CC_REGION_LIST);
        host_fail(what, BO3_TL_BLOCK);
    }
    if (added) {                                /* G8-CC1.1 F1: the records panel's stand-in, reserved before any race */
        uint32_t va = xbox_HeapAlloc(BO3_CC_RECORD_SIZE, 16u);
        if (!va)
            host_fail("the records panel's stand-in record", BO3_CC_RECORD_SIZE);   /* cand2 (D2) */
        bo3_cc_fill_empty_record((uint8_t *)((uintptr_t)g_xbox_mem_offset + va));
        bo3_cc_set_empty_record_va(va);
        bo3_cc_progress_start();                 /* G8-CC1.2: the progress sidecar, the saved results into the shadows */
    }
    fprintf(stderr, "[TRACKS] track list: %u tracks (%d added by mods; capacity %u, flags of entries %u+ in the host "
            "table)\n", (unsigned)rd32(t + 4), added, (unsigned)BO3_CC_CAP, (unsigned)BO3_CC_FLAG_CAP);
}
#endif
