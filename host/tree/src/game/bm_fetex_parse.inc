/* bm_fetex_parse.inc - GP-FETEX1: the pure reader of one mod's [bmashup.textures], [bmashup.wt_map_art] and
 * [bmashup.cars] photos, and the strict TXD check (bm_fetex.h). Included by bm_fetex.c (the service) and bm_admit.c (the
 * admission), so both decide with the same code. No guest memory, no service, no global state. FX_MUT=n compiles one
 * deliberate defect (test builds only):
 *   1 the capability list does not check the format      2 a slot binding's size is not compared with the retail slot
 *   3 a duplicate entry name is accepted                  4 a nonzero byte outside the typed regions is accepted
 *   5 a cross-mod target is accepted without requires_mods     6 a refused mod keeps textures registered before
 *   7 the pool bound is not checked                                 the failing check
 *   8 (main21 patch 121) a class "global" texture name outside the replaceable list is accepted
 *   9 (main21 patch 121) a second mod may replace the same Global.txd entry */
#ifndef BM_FETEX_PARSE_INC
#define BM_FETEX_PARSE_INC

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_fetex.h"
#include "recomp_cfg.h"

#ifndef FX_MUT
#define FX_MUT 0
#endif

#define FX_TARGET 96
#define FX_MAX_PHOTOS 256u   /* GP-P4.3 M2: photos per car mod (was 32) */

typedef struct fx_tex {
    char name[BO3_FETEX_NAME_MAX + 1];
    uint32_t off, fmt, w, h, npal, bytes;   /* off: the entry's offset in the TXD file */
} fx_tex;

typedef struct fx_decl {
    int has_tex, has_map, has_photos;
    int global;                             /* main21 patch 121: class "global" = the textures replace Global.txd entries */
    char txd[160];
    uint32_t ntex, txd_bytes;
    fx_tex tex[BO3_FETEX_MAX_PER_MOD];
    char region;
    uint32_t nslot;
    struct { int slot; char target[FX_TARGET]; } slotb[BO3_FETEX_MAX_SLOTB];
    uint32_t nphoto;
    struct { char car[13]; char target[FX_TARGET]; } photo[FX_MAX_PHOTOS];
    char place[BO3_FETEX_PLACE_MAX + 1], ticker[BO3_FETEX_TICKER_MAX + 1];
} fx_decl;

/* the retail slots a [bmashup.wt_map_art] binding may name: the three donor maps' textures and the map markers, with the
 * retail format / size (pinned Frontend.txd b5d4dd9b..., names = the slot list 0x38A280; TRACE.md s3) */
typedef struct fx_slot { int slot; const char *name; uint32_t fmt, w, h; } fx_slot;
static const fx_slot k_fx_slots[] = {
    { 47, "RaceIcon", 0x0F, 64, 64}, { 48, "RacePulse", 0x0F, 256, 256}, { 49, "RaceHollow", 0x0F, 64, 64},
    { 50, "CrashIcon", 0x0F, 64, 64}, { 51, "CrashPulse", 0x0F, 64, 64}, { 52, "CrashHollow", 0x0F, 256, 256},
    { 53, "GPIcon", 0x0F, 64, 64}, { 54, "GPPulse", 0x0F, 256, 256}, { 55, "StartFlag", 0x0C, 64, 64},
    { 66, "USA1", 0x0C, 512, 512}, { 67, "US_LSat", 0x0C, 256, 256}, { 68, "SatMapU_L1", 0x0C, 64, 32},
    { 69, "SatMapU_L2", 0x0C, 128, 64}, { 70, "SatMapU_L3", 0x0C, 256, 128}, { 71, "SatMapU_L4", 0x0C, 512, 256},
    { 72, "SatMapU1_1", 0x0C, 256, 256}, { 73, "SatMapU2_1", 0x0C, 256, 256}, { 74, "SatMapU3_1", 0x0C, 256, 256},
    { 75, "SatMapU1_2", 0x0C, 256, 256}, { 76, "SatMapU2_2", 0x0C, 256, 256}, { 77, "SatMapU3_2", 0x0C, 256, 256},
    { 78, "Europe1", 0x0C, 256, 256}, { 79, "EU_LSat", 0x0C, 256, 256}, { 80, "SatMapE_L1", 0x0C, 64, 32},
    { 81, "SatMapE_L2", 0x0C, 128, 64}, { 82, "SatMapE_L3", 0x0C, 256, 128}, { 83, "SatMapE_L4", 0x0C, 512, 256},
    { 84, "SatMapE1_1", 0x0C, 256, 256}, { 85, "SatMapE2_1", 0x0C, 256, 256}, { 86, "SatMapE3_1", 0x0C, 256, 256},
    { 87, "SatMapE1_2", 0x0C, 256, 256}, { 88, "SatMapE2_2", 0x0C, 256, 256}, { 89, "SatMapE3_2", 0x0C, 256, 256},
    { 90, "ASIA1", 0x0C, 512, 512}, { 91, "AU_LSat", 0x0C, 256, 256}, { 92, "SatMapA_L1", 0x0C, 64, 32},
    { 93, "SatMapA_L2", 0x0C, 128, 64}, { 94, "SatMapA_L3", 0x0C, 256, 128}, { 95, "SatMapA_L4", 0x0C, 512, 256},
    { 96, "SatMapA1_1", 0x0C, 256, 256}, { 97, "SatMapA2_1", 0x0C, 256, 256}, { 98, "SatMapA3_1", 0x0C, 256, 256},
    { 99, "SatMapA1_2", 0x0C, 256, 256}, {100, "SatMapA2_2", 0x0C, 256, 256}, {101, "SatMapA3_2", 0x0C, 256, 256},
};
#define FX_NSLOTS (sizeof k_fx_slots / sizeof k_fx_slots[0])

static const fx_slot *fx_slot_by_name(const char *s)
{
    for (size_t i = 0; i < FX_NSLOTS; i++) {
        const char *a = k_fx_slots[i].name, *b = s;
        while (*a && *b && tolower((unsigned char)*a) == tolower((unsigned char)*b))
            a++, b++;
        if (!*a && !*b)
            return &k_fx_slots[i];
    }
    return NULL;
}

static const fx_slot *fx_slot_by_index(int slot)
{
    for (size_t i = 0; i < FX_NSLOTS; i++)
        if (k_fx_slots[i].slot == slot)
            return &k_fx_slots[i];
    return NULL;
}

static uint32_t fx_rd32(const uint8_t *b, size_t o)
{
    return (uint32_t)b[o] | (uint32_t)b[o + 1] << 8 | (uint32_t)b[o + 2] << 16 | (uint32_t)b[o + 3] << 24;
}

static int fx_pow2(uint32_t v)
{
    return v && !(v & (v - 1));
}

static uint32_t fx_log2(uint32_t v)
{
    uint32_t r = 0;
    while (v > 1)
        v >>= 1, r++;
    return r;
}

static uint32_t fx_texel_bytes(uint32_t fmt, uint32_t w, uint32_t h)
{
    uint32_t bw = w / 4 ? w / 4 : 1, bh = h / 4 ? h / 4 : 1;
    return fmt == BO3_FETEX_P8 ? w * h : fmt == BO3_FETEX_ARGB ? w * h * 4u : fmt == BO3_FETEX_DXT1 ? bw * bh * 8u : bw * bh * 16u;
}

static int fx_name_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > BO3_FETEX_NAME_MAX)
        return 0;
    for (; *s; s++)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '.' || *s == '-'))
            return 0;
    return 1;
}

/* the strict TXD check (the layout of gp\tools\fetex\fetexlib\txd.py, proven by a byte-identical rebuild of the retail
 * Frontend.txd) + the front-end capability list v1. Fills d->tex / ntex / txd_bytes when d != NULL. */
static int fx_check_txd(const uint8_t *b, size_t n, fx_decl *d, char *why, size_t wn)
{
    uint32_t cnt, first, prev = 0;
    uint8_t *cov;
    int ok = 1;
    if (!b || n < 0x10 || n > (size_t)BO3_FETEX_POOL_MAX) {
        snprintf(why, wn, "the TXD has %u bytes (16 .. %u)", (unsigned)n, (unsigned)BO3_FETEX_POOL_MAX);
        return 0;
    }
    if (fx_rd32(b, 0) != 0x543C0000u || fx_rd32(b, 12) != 0x10u) {
        snprintf(why, wn, "not a Criterion texture dictionary (magic %08X)", (unsigned)fx_rd32(b, 0));
        return 0;
    }
    cnt = fx_rd32(b, 8);
    if (cnt == 0 || cnt > BO3_FETEX_MAX_PER_MOD) {
        snprintf(why, wn, "the TXD holds %u textures (1 .. %u per mod)", (unsigned)cnt, (unsigned)BO3_FETEX_MAX_PER_MOD);
        return 0;
    }
    first = 0x10u + 16u * cnt;
    if (first > n) {
        snprintf(why, wn, "the TXD's table runs past the file");
        return 0;
    }
    cov = (uint8_t *)calloc(n, 1);
    if (!cov) {
        snprintf(why, wn, "no host memory");
        return 0;
    }
    memset(cov, 1, first);
    for (uint32_t i = 0; ok && i < cnt; i++) {
        const uint8_t *t = b + 0x10 + 16u * i;
        uint32_t off = fx_rd32(t, 8), fmt, w, h, bits, npal, tb, end, pblk;
        char name[BO3_FETEX_NAME_MAX + 2];
        size_t nl;
        if (fx_rd32(t, 0) != i + 1u || fx_rd32(t, 4) || fx_rd32(t, 12) || (off & 0x7Fu) || (i && off <= prev) ||
            off < first || (size_t)off + 0x80u > n) {
            snprintf(why, wn, "TXD table row %u is malformed", (unsigned)i);
            ok = 0;
            break;
        }
        prev = off;
        fmt = fx_rd32(b, off + 0x34);
        w = fx_rd32(b, off + 0x38);
        h = fx_rd32(b, off + 0x3C);
        bits = fx_rd32(b, off + 0x40);
        npal = b[off + 0x69];
        memcpy(name, b + off + 0x48, 32);
        name[32] = 0;
        nl = strlen(name);
        if (fx_rd32(b, off) != 0x00040001u || fx_rd32(b, off + 4) != 0x80u || fx_rd32(b, off + 8) || fx_rd32(b, off + 0x10) ||
            fx_rd32(b, off + 0x44) || b[off + 0x68] != 1u) {
            snprintf(why, wn, "TXD entry %u: the texture header is off the layout", (unsigned)i);
            ok = 0;
            break;
        }
#if FX_MUT != 1
        if (fmt != BO3_FETEX_P8 && fmt != BO3_FETEX_DXT1 && fmt != BO3_FETEX_DXT5 &&
            !(fmt == BO3_FETEX_ARGB && d && d->global)) {   /* main21 patch 128: A8R8G8B8 for class "global" only */
            snprintf(why, wn, "TXD entry %u: format 0x%02X is not in the front-end list (P8 0x0B, DXT1 0x0C, DXT5 0x0F; "
                     "class \"global\" also A8R8G8B8 0x06)", (unsigned)i, (unsigned)fmt);
            ok = 0;
            break;
        }
#endif
        if (!fx_pow2(w) || !fx_pow2(h) || w < 4 || h < 4 || w > 1024 || h > 1024) {
            snprintf(why, wn, "TXD entry %u: %ux%u is not 4 .. 1024 powers of two", (unsigned)i, (unsigned)w, (unsigned)h);
            ok = 0;
            break;
        }
        if (fx_rd32(b, off + 0x0C) != (0x29u | fmt << 8 | 1u << 16 | fx_log2(w) << 20 | fx_log2(h) << 24)) {
            snprintf(why, wn, "TXD entry %u: the D3D format word is not a 2D, 1-mip %ux%u texture of format 0x%02X",
                     (unsigned)i, (unsigned)w, (unsigned)h, (unsigned)fmt);
            ok = 0;
            break;
        }
        if ((fmt == BO3_FETEX_P8 && (bits != 8u || npal < 1u || npal > 8u)) || (fmt != BO3_FETEX_P8 && (bits != 32u || npal))) {
            snprintf(why, wn, "TXD entry %u: palettes %u / bits %u (P8: 1 .. 8 palettes of 256 colours; DXT: none)", (unsigned)i,
                     (unsigned)npal, (unsigned)bits);
            ok = 0;
            break;
        }
        if (!fx_name_ok(name) || nl >= 32u) {
            snprintf(why, wn, "TXD entry %u: the name \"%.31s\" is not [a-z0-9_.-]{1,31}", (unsigned)i, name);
            ok = 0;
            break;
        }
        for (size_t k = 0x48 + nl; k < 0x68 && ok; k++)
            if (b[off + k]) {
                snprintf(why, wn, "TXD entry %s: bytes after the name are not zero", name);
                ok = 0;
            }
        for (size_t k = 0x6A; k < 0x80 && ok; k++)
            if (b[off + k]) {
                snprintf(why, wn, "TXD entry %s: the reserved header tail is not zero", name);
                ok = 0;
            }
        tb = fx_texel_bytes(fmt, w, h);
        pblk = 0x480u;
        end = 0x80u + tb + (fmt == BO3_FETEX_P8 ? npal * pblk : 0u);
        if (!ok)
            break;
        if ((size_t)off + end > n || end > BO3_FETEX_MAX_ENTRY) {
            snprintf(why, wn, "TXD entry %s: %u bytes run past the file or the %u-byte entry limit", name, (unsigned)end,
                     (unsigned)BO3_FETEX_MAX_ENTRY);
            ok = 0;
            break;
        }
        for (uint32_t k = 0; k < 8u && ok; k++) {
            uint32_t po = fx_rd32(b, off + 0x14 + 4u * k);
            if (k >= npal || fmt != BO3_FETEX_P8) {
                if (po) {
                    snprintf(why, wn, "TXD entry %s: palette offset %u set beyond the palette count", name, (unsigned)k);
                    ok = 0;
                }
                continue;
            }
            if (po != 0x80u + tb + k * pblk || fx_rd32(b, off + po) != 0x00030001u || fx_rd32(b, off + po + 4) != po + 0x40u) {
                snprintf(why, wn, "TXD entry %s: palette %u is off the layout", name, (unsigned)k);
                ok = 0;
            }
            for (uint32_t z = 8; z < 0x40 && ok; z++)
                if (b[off + po + z]) {
                    snprintf(why, wn, "TXD entry %s: palette %u header bytes are not zero", name, (unsigned)k);
                    ok = 0;
                }
        }
        for (uint32_t k = 0; ok && k < end; k++) {
            if (cov[off + k]) {
                snprintf(why, wn, "TXD entry %s overlaps another region", name);
                ok = 0;
            }
            cov[off + k] = 1;
        }
        if (!ok)
            break;
        if (fmt == BO3_FETEX_P8)       /* the 0x40 bytes after each palette's 0x400 are padding: they must be zero */
            for (uint32_t k = 0; k < npal; k++)
                memset(cov + off + 0x80u + tb + k * pblk + 0x440u, 0, 0x40u);
        for (uint32_t j = 0; d && j < i; j++)
#if FX_MUT != 3
            if (!strcmp(d->tex[j].name, name)) {
                snprintf(why, wn, "the TXD holds the name %s twice", name);
                ok = 0;
            }
#else
            (void)j;
#endif
        if (d && ok) {
            fx_tex *e = &d->tex[i];
            memcpy(e->name, name, nl + 1);
            e->off = off;
            e->fmt = fmt;
            e->w = w;
            e->h = h;
            e->npal = npal;
            e->bytes = (end + 0x7Fu) & ~0x7Fu;
            d->ntex = i + 1u;
        }
    }
#if FX_MUT != 4
    for (size_t k = 0; ok && k < n; k++)
        if (!cov[k] && b[k]) {
            snprintf(why, wn, "the TXD has a nonzero byte at 0x%X outside every texture, palette and header", (unsigned)k);
            ok = 0;
        }
#endif
    free(cov);
    if (ok && d)
        d->txd_bytes = (uint32_t)n;
    return ok;
}

static void fx_trim(char *s)
{
    char *a = s, *e;
    while (*a == ' ')
        a++;
    memmove(s, a, strlen(a) + 1);
    for (e = s + strlen(s); e > s && e[-1] == ' ';)
        *--e = 0;
}

static int fx_split(const char *s, char *a, size_t an, char *b, size_t bn)
{
    const char *p = s ? strchr(s, '=') : NULL;
    if (!p || (size_t)(p - s) >= an || strlen(p + 1) >= bn)
        return 0;
    memcpy(a, s, (size_t)(p - s));
    a[p - s] = 0;
    strcpy(b, p + 1);
    fx_trim(a);
    fx_trim(b);
    return *a && *b;
}

static const char *fx_arr(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

/* the keys of [prefix]: 1 present and all known, 0 absent, -1 an unknown key (named in bad) */
static int fx_keys(recomp_cfg *cfg, const char *prefix, const char *const *keys, char *bad, size_t bn)
{
    size_t pl = strlen(prefix);
    int present = 0;
    for (size_t i = 0; i < recomp_cfg_count(cfg); i++) {
        const char *k = recomp_cfg_key_at(cfg, i);
        int known = 0;
        if (strncmp(k, prefix, pl) != 0 || (k[pl] != 0 && k[pl] != '.'))
            continue;
        present = 1;
        for (const char *const *q = keys; *q && k[pl]; q++)
            known |= !strcmp(k + pl + 1, *q);
        if (!known) {
            snprintf(bad, bn, "%s", k);
            return -1;
        }
    }
    return present;
}

/* a binding target -> canonical "<mod>/<name>"; 0 when malformed or the mod is neither this one nor in requires */
static int fx_target(const char *mod_id, const char *const *req, int nreq, const char *t, char *out, size_t on)
{
    const char *sl = strchr(t, '/');
    if (!sl) {
        if (!fx_name_ok(t))
            return 0;
        snprintf(out, on, "%s/%s", mod_id, t);
        return 1;
    }
    if (!fx_name_ok(sl + 1) || sl == t || (size_t)(sl - t) >= 64u)
        return 0;
    if ((size_t)(sl - t) == strlen(mod_id) && !strncmp(t, mod_id, (size_t)(sl - t))) {
        snprintf(out, on, "%s", t);
        return 1;
    }
#if FX_MUT != 5
    for (int k = 0; k < nreq; k++)
        if (req[k] && strlen(req[k]) == (size_t)(sl - t) && !strncmp(req[k], t, (size_t)(sl - t))) {
            snprintf(out, on, "%s", t);
            return 1;
        }
    return 0;
#else
    snprintf(out, on, "%s", t);
    return 1;
#endif
}

static int fx_text_ok(const char *s, size_t max, int ticker)
{
    size_t n = strlen(s);
    if (!n || n > max)
        return 0;
    for (; *s; s++)
        if (!((*s >= 'A' && *s <= 'Z') || (*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == ' ' || *s == '-' ||
              *s == '\'' || *s == '.' || *s == '&' || (ticker && (*s == '!' || *s == ','))))
            return 0;
    return 1;
}

static int fx_car_id_ok(const char *s)
{
    /* GP-P4.3 M8: the vehicle-ID syntax only - 4 class / series letters (a retail class literal OR a veh1 [bmashup.series]
     * prefix) + 1 .. 8 of A-Z 0-9; bm_cars.c refuses an ID that is not a car of this mod's add list (veh1 class rules) */
    size_t n = strlen(s);
    if (n < 5 || n > 12)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= 'A' && s[i] <= 'Z') || (i >= 4 && s[i] >= '0' && s[i] <= '9')))
            return 0;
    return 1;
}

/* this mod's own texture by canonical name (NULL: another mod's, resolved by the caller's registry) */
static const fx_tex *fx_own(const fx_decl *d, const char *mod_id, const char *canonical)
{
    size_t ml = strlen(mod_id);
    if (strncmp(canonical, mod_id, ml) || canonical[ml] != '/')
        return NULL;
    for (uint32_t k = 0; k < d->ntex; k++)
        if (!strcmp(d->tex[k].name, canonical + ml + 1))
            return &d->tex[k];
    return NULL;
}

/* a binding's requirement against a texture: 1 ok, 0 with why */
static int fx_fits_slot(const fx_slot *s, uint32_t fmt, uint32_t w, uint32_t h, const char *what, char *why, size_t wn)
{
#if FX_MUT != 2
    if (fmt != s->fmt || w != s->w || h != s->h) {
#else
    if (fmt != s->fmt) {
#endif
        snprintf(why, wn, "%s: the slot %s draws a %ux%u texture of format 0x%02X; the bound texture is %ux%u 0x%02X", what,
                 s->name, (unsigned)s->w, (unsigned)s->h, (unsigned)s->fmt, (unsigned)w, (unsigned)h, (unsigned)fmt);
        return 0;
    }
    return 1;
}

static int fx_fits_photo(uint32_t fmt, uint32_t w, uint32_t h, uint32_t npal, const char *what, char *why, size_t wn)
{
    if (fmt != BO3_FETEX_P8 || w != 128u || h != 64u || npal < 1u) {
        snprintf(why, wn, "%s: a garage photo is a P8 128x64 texture with 1 .. 8 palettes (the retail photo layout); the "
                 "bound texture is %ux%u 0x%02X with %u palettes", what, (unsigned)w, (unsigned)h, (unsigned)fmt, (unsigned)npal);
        return 0;
    }
    return 1;
}

/* main21 patch 121: the Global.txd entries a class "global" texture may replace (the shadow and spark art; the PS2-look mod) */
static int fx_global_ok(const char *name)
{
    static const char *const k[] = {"blobbyshadow", "fxspark", "fxscrape", "fxpopcornspark"};
    for (size_t i = 0; i < sizeof k / sizeof k[0]; i++)
        if (!strcmp(name, k[i]))
            return 1;
    return 0;
}

/* one mod's declarations. txd: its file's bytes when [bmashup.textures] names one (the caller reads it; NULL -> "missing").
 * Targets in this mod are checked here; targets in other mods are left to the caller's registry (fx_own == NULL). */
static int fx_parse(const char *mod_id, const char *const *req, int nreq, const char *text, size_t n, const uint8_t *txd,
                    size_t txd_n, int txd_read, fx_decl *d, char *why, size_t wn)
{
    static const char *const k_tex[] = {"version", "txd", "class", NULL};
    static const char *const k_map[] = {"version", "region", "art", "place", "ticker", NULL};
    char err[200], bad[120];
    recomp_cfg *cfg;
    char *buf;
    int ok = 1, r;
    memset(d, 0, sizeof *d);
    if (!text || !n || (!strstr(text, "bmashup.textures") && !strstr(text, "bmashup.wt_map_art") && !strstr(text, "photos")))
        return 1;
    buf = (char *)malloc(n + 1);
    if (!buf) {
        snprintf(why, wn, "no host memory");
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
    /* [bmashup.textures] */
    r = fx_keys(cfg, "bmashup.textures", k_tex, bad, sizeof bad);
    if (r < 0) {
        snprintf(why, wn, "%s is not a key this build reads ([bmashup.textures] version 1: version, txd, class)", bad);
        ok = 0;
    } else if (r > 0) {
        const char *p = recomp_cfg_type_of(cfg, "bmashup.textures.txd") == RCFG_STRING ?
                        recomp_cfg_string(cfg, "bmashup.textures.txd", NULL) : NULL;
        const char *c = recomp_cfg_type_of(cfg, "bmashup.textures.class") == RCFG_STRING ?
                        recomp_cfg_string(cfg, "bmashup.textures.class", NULL) : NULL;
        d->has_tex = 1;
        if (recomp_cfg_type_of(cfg, "bmashup.textures.version") != RCFG_INT ||
            recomp_cfg_int(cfg, "bmashup.textures.version", 0) != 1) {
            snprintf(why, wn, "bmashup.textures.version must be 1 (the only version this build reads)");
            ok = 0;
        } else if (!c || (strcmp(c, "frontend") && strcmp(c, "global"))) {
            snprintf(why, wn, "bmashup.textures.class must be \"frontend\" or \"global\" (car and track textures stay in their "
                     "model / track files in v1; got \"%s\")", c ? c : "");
            ok = 0;
        } else if (!p || !*p || strlen(p) >= sizeof d->txd || strstr(p, "..") || p[0] == '/' || p[0] == '\\' ||
                   strchr(p, ':')) {
            snprintf(why, wn, "bmashup.textures.txd must be a relative path inside the mod folder");
            ok = 0;
        } else {
            snprintf(d->txd, sizeof d->txd, "%s", p);
            d->global = !strcmp(c, "global");      /* main21 patch 128: the format list depends on the class */
            if (!txd_read || !txd) {
                snprintf(why, wn, "bmashup.textures.txd: the file %s is missing or cannot be read", p);
                ok = 0;
            } else if (!fx_check_txd(txd, txd_n, d, err, sizeof err)) {
                snprintf(why, wn, "bmashup.textures.txd %s: %s", p, err);
                ok = 0;
            } else if (!strcmp(c, "global")) {
                d->global = 1;
                for (uint32_t k = 0; ok && k < d->ntex; k++)   /* main21 patch 128 (C3 run m21_c3_r2v2: P8 drew with a stray palette) */
                    if (d->tex[k].fmt == BO3_FETEX_P8) {
                        snprintf(why, wn, "bmashup.textures class \"global\": %s is P8; these entries are drawn without binding a "
                                 "palette - use A8R8G8B8 (lossless), DXT5 or DXT1", d->tex[k].name);
                        ok = 0;
                    }
#if FX_MUT != 8
                for (uint32_t k = 0; ok && k < d->ntex; k++)
                    if (!fx_global_ok(d->tex[k].name)) {
                        snprintf(why, wn, "bmashup.textures class \"global\": %s is not a Global.txd entry this build replaces "
                                 "(blobbyshadow, fxspark, fxscrape, fxpopcornspark)", d->tex[k].name);
                        ok = 0;
                    }
#else
                (void)fx_global_ok;                 /* defect: the list not checked */
#endif
            }
        }
    }
    /* [bmashup.wt_map_art] */
    if (ok) {
        r = fx_keys(cfg, "bmashup.wt_map_art", k_map, bad, sizeof bad);
        if (r < 0) {
            snprintf(why, wn, "%s is not a key this build reads ([bmashup.wt_map_art] version 1: version, region, art, place, "
                     "ticker)", bad);
            ok = 0;
        } else if (r > 0) {
            const char *rg = recomp_cfg_type_of(cfg, "bmashup.wt_map_art.region") == RCFG_STRING ?
                             recomp_cfg_string(cfg, "bmashup.wt_map_art.region", NULL) : NULL;
            d->has_map = 1;
            if (recomp_cfg_type_of(cfg, "bmashup.wt_map_art.version") != RCFG_INT ||
                recomp_cfg_int(cfg, "bmashup.wt_map_art.version", 0) != 1) {
                snprintf(why, wn, "bmashup.wt_map_art.version must be 1");
                ok = 0;
            } else if (!rg || strlen(rg) != 1 || rg[0] < 'A' || rg[0] > 'Z') {
                snprintf(why, wn, "bmashup.wt_map_art.region must be one region letter A-Z");
                ok = 0;
            } else
                d->region = rg[0];
            if (ok && recomp_cfg_type_of(cfg, "bmashup.wt_map_art.art") != RCFG_NONE) {
                size_t na = recomp_cfg_type_of(cfg, "bmashup.wt_map_art.art") == RCFG_ARRAY ?
                            recomp_cfg_array_len(cfg, "bmashup.wt_map_art.art") : (size_t)-1;
                if (na == (size_t)-1 || na > BO3_FETEX_MAX_SLOTB) {
                    snprintf(why, wn, "bmashup.wt_map_art.art must be a list of at most %u \"SLOT = texture\"",
                             (unsigned)BO3_FETEX_MAX_SLOTB);
                    ok = 0;
                }
                for (size_t i = 0; ok && i < na; i++) {
                    char a[64], b[FX_TARGET], canon[FX_TARGET];
                    const fx_slot *s;
                    const fx_tex *t;
                    if (!fx_split(fx_arr(cfg, "bmashup.wt_map_art.art", i), a, sizeof a, b, sizeof b)) {
                        snprintf(why, wn, "bmashup.wt_map_art.art[%u] is not \"SLOT = texture\"", (unsigned)i);
                        ok = 0;
                    } else if (!(s = fx_slot_by_name(a))) {
                        snprintf(why, wn, "bmashup.wt_map_art.art: %s is not a map / marker slot this build binds", a);
                        ok = 0;
                    } else if (!fx_target(mod_id, req, nreq, b, canon, sizeof canon)) {
                        snprintf(why, wn, "bmashup.wt_map_art.art: %s = %s: not a texture name of this mod or of a mod in its "
                                 "[bmashup] requires_mods", a, b);
                        ok = 0;
                    } else {
                        for (uint32_t k = 0; k < d->nslot; k++)
                            if (d->slotb[k].slot == s->slot) {
                                snprintf(why, wn, "bmashup.wt_map_art.art binds the slot %s twice", s->name);
                                ok = 0;
                            }
                        if (ok && (t = fx_own(d, mod_id, canon)) == NULL && !strncmp(canon, mod_id, strlen(mod_id)) &&
                            canon[strlen(mod_id)] == '/') {
                            snprintf(why, wn, "bmashup.wt_map_art.art: %s = %s: this mod's TXD has no such texture", a, b);
                            ok = 0;
                        } else if (ok && t && !fx_fits_slot(s, t->fmt, t->w, t->h, "bmashup.wt_map_art.art", why, wn))
                            ok = 0;
                        if (ok) {
                            d->slotb[d->nslot].slot = s->slot;
                            snprintf(d->slotb[d->nslot].target, FX_TARGET, "%s", canon);
                            d->nslot++;
                        }
                    }
                }
            }
            if (ok && recomp_cfg_type_of(cfg, "bmashup.wt_map_art.place") != RCFG_NONE) {
                const char *s = recomp_cfg_type_of(cfg, "bmashup.wt_map_art.place") == RCFG_STRING ?
                                recomp_cfg_string(cfg, "bmashup.wt_map_art.place", NULL) : NULL;
                if (!s || !fx_text_ok(s, BO3_FETEX_PLACE_MAX, 0)) {
                    snprintf(why, wn, "bmashup.wt_map_art.place must be 1 .. %u characters of A-Z a-z 0-9, space and - ' . &",
                             (unsigned)BO3_FETEX_PLACE_MAX);
                    ok = 0;
                } else
                    snprintf(d->place, sizeof d->place, "%s", s);
            }
            if (ok && recomp_cfg_type_of(cfg, "bmashup.wt_map_art.ticker") != RCFG_NONE) {
                const char *s = recomp_cfg_type_of(cfg, "bmashup.wt_map_art.ticker") == RCFG_STRING ?
                                recomp_cfg_string(cfg, "bmashup.wt_map_art.ticker", NULL) : NULL;
                if (!s || !fx_text_ok(s, BO3_FETEX_TICKER_MAX, 1)) {
                    snprintf(why, wn, "bmashup.wt_map_art.ticker must be 1 .. %u characters of A-Z a-z 0-9, space and - ' . & ! ,",
                             (unsigned)BO3_FETEX_TICKER_MAX);
                    ok = 0;
                } else
                    snprintf(d->ticker, sizeof d->ticker, "%s", s);
            }
            if (ok && !d->nslot && !d->place[0] && !d->ticker[0]) {
                snprintf(why, wn, "[bmashup.wt_map_art] binds nothing (art, place or ticker)");
                ok = 0;
            }
        }
    }
    /* [bmashup.cars] photos (the rest of [bmashup.cars] is bm_cars.c's) */
    if (ok && recomp_cfg_type_of(cfg, "bmashup.cars.photos") != RCFG_NONE) {
        size_t np = recomp_cfg_type_of(cfg, "bmashup.cars.photos") == RCFG_ARRAY ?
                    recomp_cfg_array_len(cfg, "bmashup.cars.photos") : (size_t)-1;
        d->has_photos = 1;
        if (np == (size_t)-1 || np == 0 || np > FX_MAX_PHOTOS) {
            snprintf(why, wn, "bmashup.cars.photos must be a list of 1 .. %u \"CAR ID = texture\"", (unsigned)FX_MAX_PHOTOS);
            ok = 0;
        }
        for (size_t i = 0; ok && i < np; i++) {
            char a[64], b[FX_TARGET], canon[FX_TARGET];
            const fx_tex *t;
            if (!fx_split(fx_arr(cfg, "bmashup.cars.photos", i), a, sizeof a, b, sizeof b) || !fx_car_id_ok(a)) {
                snprintf(why, wn, "bmashup.cars.photos[%u] is not \"CAR ID = texture\" (4 class / series letters "
                         "+ 1 .. 8 of A-Z 0-9; GP-P4.3 M8)", (unsigned)i);
                ok = 0;
            } else if (!fx_target(mod_id, req, nreq, b, canon, sizeof canon)) {
                snprintf(why, wn, "bmashup.cars.photos: %s = %s: not a texture name of this mod or of a mod in its [bmashup] "
                         "requires_mods", a, b);
                ok = 0;
            } else {
                for (uint32_t k = 0; k < d->nphoto; k++)
                    if (!strcmp(d->photo[k].car, a)) {
                        snprintf(why, wn, "bmashup.cars.photos gives %s two photos", a);
                        ok = 0;
                    }
                t = fx_own(d, mod_id, canon);
                if (ok && !t && !strncmp(canon, mod_id, strlen(mod_id)) && canon[strlen(mod_id)] == '/') {
                    snprintf(why, wn, "bmashup.cars.photos: %s = %s: this mod's TXD has no such texture", a, b);
                    ok = 0;
                } else if (ok && t && !fx_fits_photo(t->fmt, t->w, t->h, t->npal, "bmashup.cars.photos", why, wn))
                    ok = 0;
                if (ok) {
                    snprintf(d->photo[d->nphoto].car, sizeof d->photo[0].car, "%s", a);
                    snprintf(d->photo[d->nphoto].target, FX_TARGET, "%s", canon);
                    d->nphoto++;
                }
            }
        }
    }
    recomp_cfg_free(cfg);
    if (!ok)
        memset(d, 0, sizeof *d);
    return ok;
}

/* ---- the registry of admitted declarations (the service's global one; the admission's per pass) ---- */
typedef struct fx_rtex {
    char canonical[FX_TARGET];
    uint32_t mod, off, fmt, w, h, npal, bytes;
} fx_rtex;

typedef struct fx_reg {
    uint32_t nmod, ntex, pool_bytes;
    char mod_id[BO3_FETEX_MAX_MODS][64];
    uint32_t mod_off[BO3_FETEX_MAX_MODS], mod_bytes[BO3_FETEX_MAX_MODS];
    fx_rtex tex[BO3_FETEX_MAX];
    uint32_t nname;
    struct { char car[13]; uint32_t tex; char owner[64]; } name[BO3_FETEX_MAX_NAMEB];
    int slot[BO3_FETEX_NSLOTS];                  /* texture index + 1, 0 none */
    char slot_owner[BO3_FETEX_NSLOTS][64];
    uint32_t nslot;
    char region, place[BO3_FETEX_PLACE_MAX + 1], ticker[BO3_FETEX_TICKER_MAX + 1], map_owner[64];
    uint32_t nglob;                              /* main21 patch 121: Global.txd entries replaced (class "global") */
    struct { char name[BO3_FETEX_NAME_MAX + 1]; uint32_t tex; char owner[64]; } glob[8];
} fx_reg;

static int fx_reg_find(const fx_reg *r, const char *canonical)
{
    for (uint32_t i = 0; i < r->ntex; i++)
        if (!strcmp(r->tex[i].canonical, canonical))
            return (int)i;
    return -1;
}

/* one mod's parsed declaration joins the registry: every check first, then the commit (all or nothing). 1 ok, 0 with why
 * (the registry unchanged). FX_MUT 6: a refused mod keeps the textures registered before the failing check. */
static int fx_reg_add(fx_reg *r, const char *mod_id, const fx_decl *d, char *why, size_t wn)
{
    uint32_t need = (d->txd_bytes + 0xFFFu) & ~0xFFFu, base = r->ntex;
    int slot_tex[BO3_FETEX_MAX_SLOTB], photo_tex[FX_MAX_PHOTOS];
    fx_rtex pend[BO3_FETEX_MAX_PER_MOD];
    if (!d->has_tex && !d->has_map && !d->has_photos)
        return 1;
    if (d->has_tex) {
        if (r->nmod >= BO3_FETEX_MAX_MODS) {
            snprintf(why, wn, "more than %u mods with [bmashup.textures]", (unsigned)BO3_FETEX_MAX_MODS);
            return 0;
        }
        if (r->ntex + d->ntex > BO3_FETEX_MAX) {
            snprintf(why, wn, "the textures of all mods would be %u (at most %u); the earlier mods hold %u",
                     (unsigned)(r->ntex + d->ntex), (unsigned)BO3_FETEX_MAX, (unsigned)r->ntex);
            return 0;
        }
#if FX_MUT != 7
        if (r->pool_bytes + need > BO3_FETEX_POOL_MAX) {
            snprintf(why, wn, "the texture pool would need %u bytes (at most %u); the earlier mods hold %u",
                     (unsigned)(r->pool_bytes + need), (unsigned)BO3_FETEX_POOL_MAX, (unsigned)r->pool_bytes);
            return 0;
        }
#endif
        for (uint32_t k = 0; k < d->ntex; k++) {
            fx_rtex *t = &pend[k];
            snprintf(t->canonical, sizeof t->canonical, "%s/%s", mod_id, d->tex[k].name);
            if (fx_reg_find(r, t->canonical) >= 0) {
                snprintf(why, wn, "%s is already registered (the mod id twice?)", t->canonical);
                return 0;
            }
            t->mod = r->nmod;
            t->off = d->tex[k].off;
            t->fmt = d->tex[k].fmt;
            t->w = d->tex[k].w;
            t->h = d->tex[k].h;
            t->npal = d->tex[k].npal;
            t->bytes = d->tex[k].bytes;
#if FX_MUT == 6
            r->tex[r->ntex++] = *t;                    /* defect: entries installed before every check passed */
#endif
        }
    }
#if FX_MUT == 6
    base = r->ntex - (d->has_tex ? d->ntex : 0);
#endif
    for (uint32_t k = 0; k < d->nslot; k++) {
        const fx_slot *s = fx_slot_by_index(d->slotb[k].slot);
        int ti = fx_reg_find(r, d->slotb[k].target);
        const fx_rtex *t = NULL;
        for (uint32_t q = 0; ti < 0 && d->has_tex && q < d->ntex; q++)
            if (!strcmp(pend[q].canonical, d->slotb[k].target))
                ti = (int)(base + q), t = &pend[q];
        if (ti >= 0 && !t)
            t = &r->tex[ti];
        if (!t) {
            snprintf(why, wn, "bmashup.wt_map_art.art: %s = %s: no such texture is registered (an earlier mod of requires_mods "
                     "must declare it)", s->name, d->slotb[k].target);
            return 0;
        }
        if (!fx_fits_slot(s, t->fmt, t->w, t->h, "bmashup.wt_map_art.art", why, wn))
            return 0;
        if (r->slot[s->slot]) {
            snprintf(why, wn, "bmashup.wt_map_art.art: the slot %s is already bound by the mod %s", s->name,
                     r->slot_owner[s->slot]);
            return 0;
        }
        slot_tex[k] = ti;
    }
    if (d->has_map) {
        if (r->region && r->region != d->region) {
            snprintf(why, wn, "[bmashup.wt_map_art] region %c: the mod %s already binds the map art of region %c (one 4th "
                     "region)", d->region, r->map_owner, r->region);
            return 0;
        }
        if ((d->place[0] && r->place[0]) || (d->ticker[0] && r->ticker[0])) {
            snprintf(why, wn, "[bmashup.wt_map_art]: the place name / ticker is already given by the mod %s", r->map_owner);
            return 0;
        }
    }
    if (r->nname + d->nphoto > BO3_FETEX_MAX_NAMEB) {
        snprintf(why, wn, "more than %u garage photos in all mods", (unsigned)BO3_FETEX_MAX_NAMEB);
        return 0;
    }
    for (uint32_t k = 0; k < d->nphoto; k++) {
        int ti = fx_reg_find(r, d->photo[k].target);
        const fx_rtex *t = NULL;
        for (uint32_t q = 0; ti < 0 && d->has_tex && q < d->ntex; q++)
            if (!strcmp(pend[q].canonical, d->photo[k].target))
                ti = (int)(base + q), t = &pend[q];
        if (ti >= 0 && !t)
            t = &r->tex[ti];
        if (!t) {
            snprintf(why, wn, "bmashup.cars.photos: %s = %s: no such texture is registered", d->photo[k].car, d->photo[k].target);
            return 0;
        }
        if (!fx_fits_photo(t->fmt, t->w, t->h, t->npal, "bmashup.cars.photos", why, wn))
            return 0;
        for (uint32_t q = 0; q < r->nname; q++)
            if (!strcmp(r->name[q].car, d->photo[k].car)) {
                snprintf(why, wn, "bmashup.cars.photos: %s already has a photo from the mod %s", d->photo[k].car, r->name[q].owner);
                return 0;
            }
        photo_tex[k] = ti;
    }
    if (d->global) {                             /* main21 patch 121: one replacement per Global.txd entry */
        if (r->nglob + d->ntex > 8u) {
            snprintf(why, wn, "class \"global\": more than 8 Global.txd replacements in all mods");
            return 0;
        }
#if FX_MUT != 9
        for (uint32_t k = 0; k < d->ntex; k++)
            for (uint32_t q = 0; q < r->nglob; q++)
                if (!strcmp(r->glob[q].name, d->tex[k].name)) {
                    snprintf(why, wn, "class \"global\": %s is already replaced by the mod %s", d->tex[k].name, r->glob[q].owner);
                    return 0;
                }
#endif
    }
    /* commit */
    if (d->global)
        for (uint32_t k = 0; k < d->ntex; k++) {
            snprintf(r->glob[r->nglob].name, sizeof r->glob[0].name, "%s", d->tex[k].name);
            snprintf(r->glob[r->nglob].owner, sizeof r->glob[0].owner, "%s", mod_id);
            r->glob[r->nglob++].tex = base + k;
        }
    if (d->has_tex) {
        snprintf(r->mod_id[r->nmod], sizeof r->mod_id[0], "%s", mod_id);
        r->mod_off[r->nmod] = r->pool_bytes;
        r->mod_bytes[r->nmod] = d->txd_bytes;
        r->pool_bytes += need;
#if FX_MUT != 6
        memcpy(&r->tex[r->ntex], pend, d->ntex * sizeof pend[0]);
        r->ntex += d->ntex;
#endif
        r->nmod++;
    }
    for (uint32_t k = 0; k < d->nslot; k++) {
        r->slot[d->slotb[k].slot] = slot_tex[k] + 1;
        snprintf(r->slot_owner[d->slotb[k].slot], sizeof r->slot_owner[0], "%s", mod_id);
        r->nslot++;
    }
    for (uint32_t k = 0; k < d->nphoto; k++) {
        snprintf(r->name[r->nname].car, sizeof r->name[0].car, "%s", d->photo[k].car);
        snprintf(r->name[r->nname].owner, sizeof r->name[0].owner, "%s", mod_id);
        r->name[r->nname++].tex = (uint32_t)photo_tex[k];
    }
    if (d->has_map) {
        r->region = d->region;
        if (d->place[0])
            snprintf(r->place, sizeof r->place, "%s", d->place);
        if (d->ticker[0])
            snprintf(r->ticker, sizeof r->ticker, "%s", d->ticker);
        snprintf(r->map_owner, sizeof r->map_owner, "%s", mod_id);
    }
    return 1;
}

/* the [bmashup.textures] txd value as the reader takes it (""), for the callers that read the file */
#ifdef __GNUC__
__attribute__((unused))
#endif
static void fx_txd_path(const char *text, size_t n, char *out, size_t on)
{
    char err[200];
    char *buf;
    recomp_cfg *cfg;
    out[0] = 0;
    if (!text || !n || !strstr(text, "bmashup.textures") || !(buf = (char *)malloc(n + 1)))
        return;
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg)
        return;
    if (recomp_cfg_type_of(cfg, "bmashup.textures.txd") == RCFG_STRING)
        snprintf(out, on, "%s", recomp_cfg_string(cfg, "bmashup.textures.txd", NULL));
    recomp_cfg_free(cfg);
}

#endif
