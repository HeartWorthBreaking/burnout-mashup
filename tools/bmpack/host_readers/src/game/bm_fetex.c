/* bm_fetex.c - GP-FETEX1 EXPERIMENTAL: additive front-end textures (bm_fetex.h). MUT=n (test builds only) compiles one
 * deliberate defect:
 *   1 a texture's Data address is not masked to the physical offset    2 the palette pointers are not fixed up
 *   3 the miss hook answers for any dictionary (not only Frontend.txd)  4 the slot hook answers while the page is not shown
 *   5 a failed install still answers the (unfilled) texture             7 the slot hook skips the live retail-size check
 *   8 (main21 patch 121) the global replacement ignores the entry name   9 the palette pointers / count not taken over
 *  10 (main21 patch 127) no late replacement after the declarations
 * (registry / reader defects: FX_MUT in bm_fetex_parse.inc) */
#include "bm_fetex.h"

#include <ctype.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_fetex_parse.inc"

#ifndef MUT
#define MUT 0
#endif

static fx_reg s_reg;                             /* (1) the registry records: host, process lifetime */
static uint8_t *s_txd[BO3_FETEX_MAX_MODS];        /* host copies of the admitted mods' TXD files (installed into the pool) */
static uint32_t s_va[BO3_FETEX_MAX];              /* (2) entry VA in the pool after the install */
static bo3_fetex_guest s_g;
static int s_have_g;
static int s_state;                              /* 0 not installed, 1 installed, -1 failed */
static uint32_t s_pool_va;
static _Atomic uint32_t s_stat[BO3_FETEX_STATS];
static uint32_t s_slot_checked[BO3_FETEX_NSLOTS];   /* the retail VA whose format / size was checked (0 none) */
static uint8_t s_slot_ok[BO3_FETEX_NSLOTS];
static uint8_t s_logged[8];

static void log_once(uint32_t k, const char *fmt, const char *a, uint32_t v)
{
    if (k < sizeof s_logged && !s_logged[k]) {
        s_logged[k] = 1;
        fprintf(stderr, fmt, a, (unsigned)v);
        fflush(stderr);
    }
}

void bo3_fetex_reset(void)
{
    for (uint32_t i = 0; i < BO3_FETEX_MAX_MODS; i++)
        free(s_txd[i]);
    memset(s_txd, 0, sizeof s_txd);
    memset(&s_reg, 0, sizeof s_reg);
    memset(s_va, 0, sizeof s_va);
    memset(s_slot_checked, 0, sizeof s_slot_checked);
    memset(s_slot_ok, 0, sizeof s_slot_ok);
    memset(s_logged, 0, sizeof s_logged);
    s_state = 0;
    s_pool_va = 0;
    for (int k = 0; k < BO3_FETEX_STATS; k++)
        atomic_store(&s_stat[k], 0);
}

int bo3_fetex_check_txd(const uint8_t *b, size_t n, char *why, size_t wn)
{
    fx_decl *d = (fx_decl *)calloc(1, sizeof *d);
    int ok;
    if (!d) {
        snprintf(why, wn, "no host memory");
        return 0;
    }
    ok = fx_check_txd(b, n, d, why, wn);
    free(d);
    return ok;
}

int bo3_fetex_declare_mod(const char *mod_id, const char *const *req, int nreq, const char *text, size_t n,
                          const uint8_t *txd, size_t txd_n, char *why, size_t wn)
{
    fx_decl *d;
    uint8_t *copy = NULL;
    int ok = 1;
    if (!mod_id || !*mod_id || strlen(mod_id) >= sizeof s_reg.mod_id[0]) {
        snprintf(why, wn, "bad mod id");
        return 0;
    }
    if (s_state) {
        snprintf(why, wn, "the texture pool is installed: declarations are closed");
        return 0;
    }
    d = (fx_decl *)calloc(1, sizeof *d);
    if (!d) {
        snprintf(why, wn, "no host memory");
        return 0;
    }
    if (!fx_parse(mod_id, req, nreq, text, n, txd, txd_n, txd != NULL, d, why, wn))
        ok = 0;
    else if (d->has_tex && !(copy = (uint8_t *)malloc(d->txd_bytes))) {      /* reserve before the registry commit */
        snprintf(why, wn, "no host memory for the TXD copy");
        ok = 0;
    } else {
        uint32_t m = s_reg.nmod;
        if (!fx_reg_add(&s_reg, mod_id, d, why, wn))
            ok = 0;
        else if (d->has_tex) {
            memcpy(copy, txd, d->txd_bytes);
            s_txd[m] = copy;
            copy = NULL;
        }
    }
    free(copy);
    free(d);
    return ok;
}

uint32_t bo3_fetex_count(void)
{
    return s_reg.ntex;
}

int bo3_fetex_find(const char *canonical, bo3_fetex_info *out)
{
    int i = canonical ? fx_reg_find(&s_reg, canonical) : -1;
    if (i < 0)
        return 0;
    if (out) {
        memset(out, 0, sizeof *out);
        snprintf(out->canonical, sizeof out->canonical, "%s", s_reg.tex[i].canonical);
        out->fmt = s_reg.tex[i].fmt;
        out->w = s_reg.tex[i].w;
        out->h = s_reg.tex[i].h;
        out->palettes = s_reg.tex[i].npal;
        out->bytes = s_reg.tex[i].bytes;
        out->va = s_state == 1 ? s_va[i] : 0;
    }
    return 1;
}

char bo3_fetex_map_region(void)
{
    return s_reg.region;
}

const char *bo3_fetex_map_text(uint32_t kind)
{
    const char *t = kind == BO3_FETEX_TEXT_PLACE ? s_reg.place : kind == BO3_FETEX_TEXT_TICKER ? s_reg.ticker : "";
    return t[0] ? t : NULL;
}

void bo3_fetex_set_guest(const bo3_fetex_guest *g)
{
    s_g = *g;
    s_have_g = 1;
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

/* the game's own fixups, done by the host on the pool copy:
 *   sub_001BEEF0: dict +0xC = table VA; each row +8 = entry VA (the pool holds valid in-memory dictionaries);
 *   sub_001C8E20: texture +4 = (+4 + entry VA) masked to 0x0FFFFFFF unless the resource type (Common & 0x70000) is 0x20000;
 *                 palette header pointers +0x14[k] = rel + entry VA, and each palette's +4 the same rule. */
static void fixup(uint8_t *p, uint32_t va)
{
    uint32_t cnt = fx_rd32(p, 8), tbl = fx_rd32(p, 12) + va;
    put32(p + 12, tbl);
    for (uint32_t i = 0; i < cnt; i++) {
        uint32_t off = fx_rd32(p, 0x10 + 16u * i + 8), e = va + off;
        uint8_t *h = p + off;
        uint32_t data = fx_rd32(h, 4) + e;
        put32(p + 0x10 + 16u * i + 8, e);
#if MUT != 1
        if ((fx_rd32(h, 0) & 0x70000u) != 0x20000u)
            data &= 0x0FFFFFFFu;
#endif
        put32(h + 4, data);
#if MUT != 2
        for (uint32_t k = 0; k < h[0x69]; k++) {
            uint32_t po = fx_rd32(h, 0x14 + 4u * k), pd;
            uint8_t *ph = h + po;
            put32(h + 0x14 + 4u * k, po + e);
            pd = fx_rd32(ph, 4) + e;
            if ((fx_rd32(ph, 0) & 0x70000u) != 0x20000u)
                pd &= 0x0FFFFFFFu;
            put32(ph + 4, pd);
        }
#endif
    }
}

int bo3_fetex_install(void)
{
    uint8_t *base;
    if (s_state)
        return s_state > 0;
    if (!s_reg.ntex) {
        s_state = 1;
        return 1;
    }
    if (!s_have_g || !s_g.alloc || !s_g.ptr || !(s_pool_va = s_g.alloc(s_g.user, s_reg.pool_bytes)) ||
        !(base = s_g.ptr(s_g.user, s_pool_va, s_reg.pool_bytes))) {
        s_state = -1;
        s_pool_va = 0;
        atomic_fetch_add(&s_stat[BO3_FETEX_ST_INSTALL_FAIL], 1);
        fprintf(stderr, "[FETEX] no guest contiguous memory for the texture pool (%u bytes, %u textures): every binding keeps "
                "the retail / donor texture\n", (unsigned)s_reg.pool_bytes, (unsigned)s_reg.ntex);
        fflush(stderr);
        return 0;
    }
    memset(base, 0, s_reg.pool_bytes);
    for (uint32_t m = 0; m < s_reg.nmod; m++) {
        memcpy(base + s_reg.mod_off[m], s_txd[m], s_reg.mod_bytes[m]);
        fixup(base + s_reg.mod_off[m], s_pool_va + s_reg.mod_off[m]);
    }
    for (uint32_t i = 0; i < s_reg.ntex; i++)
        s_va[i] = s_pool_va + s_reg.mod_off[s_reg.tex[i].mod] + s_reg.tex[i].off;
    s_state = 1;
    atomic_fetch_add(&s_stat[BO3_FETEX_ST_INSTALLS], 1);
    fprintf(stderr, "[FETEX] texture pool 0x%08X: %u bytes, %u texture(s) of %u mod(s), %u garage photo(s), %u map slot(s)%s\n",
            (unsigned)s_pool_va, (unsigned)s_reg.pool_bytes, (unsigned)s_reg.ntex, (unsigned)s_reg.nmod, (unsigned)s_reg.nname,
            (unsigned)s_reg.nslot, s_reg.place[0] || s_reg.ticker[0] ? ", map texts" : "");
    fflush(stderr);
    return 1;
}

int bo3_fetex_installed(void)
{
    return s_state;
}

static int ready(void)
{
    if (!s_state)
        bo3_fetex_install();
#if MUT == 5
    return 1;                                       /* defect: a failed install still answers */
#else
    return s_state == 1;
#endif
}

uint32_t bo3_fetex_gen_miss(uint32_t dict, uint32_t name_va)
{
    uint32_t cars = s_have_g && s_g.car_photo ? s_g.car_photo(s_g.user, dict, name_va) : 0;
    const uint8_t *fe, *nm;
    char name[16];
    if (!s_reg.nname || !s_have_g)
        return cars;
#if MUT != 3
    if (!(fe = s_g.ptr(s_g.user, BO3_FETEX_FE_DICT, 4)) || fx_rd32(fe, 0) != dict)
        return cars;                                /* only Data/Frontend.txd lookups */
#else
    (void)fe;
#endif
    for (uint32_t k = 0; k < sizeof name; k++) {
        nm = s_g.ptr(s_g.user, name_va + k, 1);
        if (!nm)
            return cars;
        name[k] = (char)toupper(*nm);
        if (!*nm)
            break;
        if (k + 1 == sizeof name)
            return cars;
    }
    for (uint32_t q = 0; q < s_reg.nname; q++)
        if (!strcmp(s_reg.name[q].car, name)) {
            if (!ready()) {
                atomic_fetch_add(&s_stat[BO3_FETEX_ST_FALLBACKS], 1);
                return cars;
            }
            if (atomic_fetch_add(&s_stat[BO3_FETEX_ST_NAME_HITS], 1) == 0)
                log_once(0, "[FETEX] garage photo %s = a mod texture (name binding, Data/Frontend.txd miss)%.0u\n", name, 0);
            return s_va[s_reg.name[q].tex];
        }
    return cars;
}

/* main21 patch 121 (batch C3-9): class "global" replacements at the end of the Global.txd load (bm_fetex.h). The dictionary: + 8
 * count, + 0xC row table, rows of 16 bytes with the entry at + 8; an entry: + 0x48 name. */
uint32_t bo3_fetex_gen_global(uint32_t dict)
{
    const uint8_t *dh, *row, *re, *pe;
    uint8_t *ret;
    uint32_t n = 0, cnt, tbl;
    if (!s_reg.nglob || !s_have_g || !dict)
        return 0;
    if (!ready() || !(dh = s_g.ptr(s_g.user, dict, 0x10))) {
        fprintf(stderr, "[FETEX] Global.txd replacements skipped (no texture pool / no dictionary)\n");
        return 0;
    }
    cnt = fx_rd32(dh, 8);
    tbl = fx_rd32(dh, 12);
    for (uint32_t q = 0; q < s_reg.nglob; q++) {
        uint32_t ev = 0, pv = s_va[s_reg.glob[q].tex];
        for (uint32_t i = 0; i < cnt && i < 4096u && !ev; i++) {
            uint32_t e;
            if (!(row = s_g.ptr(s_g.user, tbl + 16u * i, 16)))
                break;
            e = fx_rd32(row, 8);
#if MUT != 8
            if (!(re = s_g.ptr(s_g.user, e + 0x48u, 32)) || strncmp((const char *)re, s_reg.glob[q].name, 32))
                continue;
#endif
            ev = e;
        }
        if (!ev || !(ret = s_g.ptr(s_g.user, ev, 0x80)) || !(pe = s_g.ptr(s_g.user, pv, 0x80))) {
            fprintf(stderr, "[FETEX] Global.txd: no entry %s (left as it is)\n", s_reg.glob[q].name);
            continue;
        }
#if MUT == 9
        memcpy(ret, pe, 0x14);                          /* defect: the palette pointers / count not taken over */
#else
        memcpy(ret, pe, 0x48);
        ret[0x69] = pe[0x69];
#endif
        n++;
        fprintf(stderr, "[FETEX] Global.txd %s = the mod %s's texture (%ux%u, format 0x%02X)\n", s_reg.glob[q].name,
                s_reg.glob[q].owner, (unsigned)fx_rd32(pe, 0x38), (unsigned)fx_rd32(pe, 0x3C), (unsigned)fx_rd32(pe, 0x34));
    }
    atomic_fetch_add(&s_stat[BO3_FETEX_ST_GLOBAL], n);
    fflush(stderr);
    return n;
}

uint32_t bo3_fetex_late_global(void)
{
    const uint8_t *d;
    uint32_t dict;
#if MUT == 10
    return 0;                                       /* defect: the boot-loaded Global.txd is never replaced */
#endif
    if (!s_reg.nglob || !s_have_g || !(d = s_g.ptr(s_g.user, BO3_FETEX_GLOBAL_DICT, 4)) || !(dict = fx_rd32(d, 0)))
        return 0;
    fprintf(stderr, "[FETEX] Global.txd was loaded before the mods' declarations: replacing now\n");
    return bo3_fetex_gen_global(dict);
}

uint32_t bo3_fetex_gen_slot(uint32_t slot, uint32_t retail)
{
    int ti;
    const fx_rtex *t;
    if (slot >= BO3_FETEX_NSLOTS || !(ti = s_reg.slot[slot]) || !s_have_g)
        return retail;
#if MUT != 4
    if (!s_g.active || !s_g.active(s_g.user))
        return retail;
#endif
    if (!ready()) {
        atomic_fetch_add(&s_stat[BO3_FETEX_ST_FALLBACKS], 1);
        return retail;
    }
    t = &s_reg.tex[ti - 1];
#if MUT != 7
    if (s_slot_checked[slot] != retail || !retail) {  /* the retail texture the game holds now (reloaded per front-end set-up) */
        const uint8_t *h = retail ? s_g.ptr(s_g.user, retail, 0x40) : NULL;
        s_slot_checked[slot] = retail;
        s_slot_ok[slot] = h && fx_rd32(h, 0x34) == t->fmt && fx_rd32(h, 0x38) == t->w && fx_rd32(h, 0x3C) == t->h;
        if (!s_slot_ok[slot])
            log_once(1, "[FETEX] map slot %s: the game's retail texture is not the size / format the binding was checked "
                     "against: retail kept (slot %u)\n", fx_slot_by_index((int)slot) ? fx_slot_by_index((int)slot)->name : "?",
                     slot);
    }
    if (!s_slot_ok[slot]) {
        atomic_fetch_add(&s_stat[BO3_FETEX_ST_FALLBACKS], 1);
        return retail;
    }
#endif
    if (atomic_fetch_add(&s_stat[BO3_FETEX_ST_SLOT_HITS], 1) == 0)
        log_once(2, "[FETEX] map art of region %s: first slot read answered by a mod texture (slot %u)\n",
                 (char[2]){s_reg.region, 0}, slot);
    return s_va[ti - 1];
}

uint32_t bo3_fetex_gen_text(uint32_t kind, uint32_t dflt)
{
    uint32_t id;
    if (!bo3_fetex_map_text(kind) || !s_have_g || !s_g.active || !s_g.active(s_g.user) || !s_g.text_id)
        return dflt;
    id = s_g.text_id(s_g.user, kind, dflt);
    if (id != dflt)
        atomic_fetch_add(&s_stat[BO3_FETEX_ST_TEXT_HITS], 1);
    return id;
}

uint32_t bo3_fetex_stats(uint32_t which)
{
    return which < BO3_FETEX_STATS ? atomic_load(&s_stat[which]) : 0;
}

uint32_t bo3_fetex_pool_va(void)
{
    return s_pool_va;
}

uint32_t bo3_fetex_pool_bytes(void)
{
    return s_reg.pool_bytes;
}

#ifdef BO3_FETEX_GAME
#include "bm_guest.h"
#include "bm_modreq.h"
#include "bm_names.h"
#include "bm_tracks.h"
#include "bm_wt4.h"
#include "bo3_cars_gen.h"
#include "modfs.h"

extern ptrdiff_t g_xbox_mem_offset;
extern uint32_t xbox_ContiguousAlloc(uint32_t size, uint32_t alignment);
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

static uint8_t *g_ptr(void *u, uint32_t va, uint32_t size)
{
    (void)u;
    return bo3_guest_window(va, size) ? (uint8_t *)((uintptr_t)g_xbox_mem_offset + va) : NULL;
}

#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
#endif
static uint32_t g_alloc(void *u, uint32_t size)
{
    (void)u;
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    return xbox_ContiguousAllocHigh(size, 0x1000u);   /* MEM256: the high zone */
#else
    return xbox_ContiguousAlloc(size, 0x1000u);
#endif
}

/* the wt4 4th-region map page is shown AND its declared region is the letter the map art binds (a wt_map_art for another
 * letter stays inert: logged once at the first check) */
static int g_active(void *u)
{
    static int said;
    uint32_t code;
    int k;
    (void)u;
    if (!bo3_wt4_active() || !bo3_fetex_map_region() || (code = bo3_wt4_region_code()) < 4u)
        return 0;
    k = bo3_cc_region_of_letter(bo3_fetex_map_region());
    if (k < 0 || (uint32_t)k != code - 4u) {
        if (!said++)
            fprintf(stderr, "[FETEX] map art of region %c: the shown 4th region is another one (code %u): bindings inert\n",
                    bo3_fetex_map_region(), (unsigned)code);
        return 0;
    }
    return 1;
}

static uint32_t g_text(void *u, uint32_t kind, uint32_t dflt)
{
    (void)u;
    return bo3_nm_map_text_id(kind, dflt);
}

static uint32_t g_car(void *u, uint32_t dict, uint32_t name_va)
{
    (void)u;
    return bo3_car_gen_photo(dict, name_va);
}

static void refuse(const char *id, const char *why)
{
    fprintf(stderr, "[FETEX] FATAL: mod %s: %s\n", id, why);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: a mod's front-end textures cannot be used",
              "The mod \"%s\" declares front-end textures ([bmashup.textures] / [bmashup.wt_map_art] / [bmashup.cars] photos) "
              "this build cannot use:\n%s\n\nTurn the mod off, or fix its declaration.", id, why);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(BO3_FETEX_EXIT_DECL);
}

/* [bmashup] requires_mods ids, read the admission's way (bm_modreq.h) */
static int read_reqs(const char *text, size_t n, char ids[][BO3_MODREQ_ID_MAX + 1], int max)
{
    char err[200];
    char *buf = (char *)malloc(n + 1);
    recomp_cfg *cfg;
    int k = 0;
    if (!buf)
        return 0;
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg)
        return 0;
    if (recomp_cfg_type_of(cfg, "bmashup.requires_mods") == RCFG_ARRAY)
        for (size_t i = 0; i < recomp_cfg_array_len(cfg, "bmashup.requires_mods") && k < max; i++) {
            bo3_modreq q;
            if (bo3_modreq_parse(fx_arr(cfg, "bmashup.requires_mods", i), &q, err, sizeof err))
                snprintf(ids[k++], BO3_MODREQ_ID_MAX + 1, "%s", q.id);
        }
    recomp_cfg_free(cfg);
    return k;
}

/* a TXD file (binary, up to the pool bound), at the path bo3_modfs_mod_file resolved (plain names, no links): 1 read */
static int read_bounded(const char *path, char **out, size_t *n)
{
    FILE *f = fopen(path, "rb");
    long len;
    *out = NULL;
    *n = 0;
    if (!f)
        return 0;
    if (fseek(f, 0, SEEK_END) || (len = ftell(f)) <= 0 || len > (long)BO3_FETEX_POOL_MAX || fseek(f, 0, SEEK_SET) ||
        !(*out = (char *)malloc((size_t)len)) || fread(*out, 1, (size_t)len, f) != (size_t)len) {
        fclose(f);
        free(*out);
        *out = NULL;
        return 0;
    }
    fclose(f);
    *n = (size_t)len;
    return 1;
}

void bo3_fetex_game_declare(void)
{
    static const bo3_fetex_guest g = {g_ptr, g_alloc, g_active, g_text, g_car, NULL};
    static int done;
    if (done)
        return;
    done = 1;
    bo3_fetex_set_guest(&g);
    for (int i = 0; i < bo3_modfs_mod_count(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], tpath[BO3_MODFS_PATH_MAX + 200], why[400], rel[160];
        char ids[32][BO3_MODREQ_ID_MAX + 1];
        const char *req[32];
        char *text = NULL, *tb = NULL;
        size_t n = 0, tn = 0;
        int nreq, have_txd = 0;
        uint32_t before = bo3_fetex_count();
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!strstr(text, "bmashup.textures") && !strstr(text, "bmashup.wt_map_art") && !strstr(text, "photos")) {
            free(text);
            continue;
        }
        nreq = read_reqs(text, n, ids, 32);
        for (int k = 0; k < nreq; k++)
            req[k] = ids[k];
        fx_txd_path(text, n, rel, sizeof rel);
        if (rel[0] && !strstr(rel, "..") && bo3_modfs_mod_file(m, rel, tpath, sizeof tpath) && read_bounded(tpath, &tb, &tn))
            have_txd = 1;               /* (bo3_modfs_read_whole reads text files up to 64 KiB only: gp_fetex1_1 exit 92) */
        if (!bo3_fetex_declare_mod(m->manifest.id, req, nreq, text, n, have_txd ? (const uint8_t *)tb : NULL, tn, why,
                                   sizeof why)) {
            free(text);
            free(tb);
            refuse(m->manifest.id, why);
        }
        fprintf(stderr, "[FETEX] mod %s: %u texture(s) registered\n", m->manifest.id, (unsigned)(bo3_fetex_count() - before));
        free(text);
        free(tb);
    }
    if (bo3_fetex_map_text(BO3_FETEX_TEXT_PLACE) || bo3_fetex_map_text(BO3_FETEX_TEXT_TICKER))
        bo3_nm_map_texts(bo3_fetex_map_text(BO3_FETEX_TEXT_PLACE), bo3_fetex_map_text(BO3_FETEX_TEXT_TICKER));
    if (bo3_fetex_count())
        fprintf(stderr, "[FETEX] %u texture(s), pool %u bytes reserved (installed at the first front-end use)\n",
                (unsigned)bo3_fetex_count(), (unsigned)bo3_fetex_pool_bytes());
#if BO3_HOOKREQ_ZGT
    bo3_fetex_late_global();                        /* main21 patch 127: Global.txd is loaded at boot, before these declarations */
#endif
}
#endif
