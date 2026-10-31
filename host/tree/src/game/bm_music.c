/* bm_music.c - GP-MUSIC1 EXPERIMENTAL: [bmashup.music] music packs (bm_music.h). MUSIC_MUT=n (test builds only) compiles one
 * deliberate defect:
 *   1 a file part ".." is taken; 2 a title with a path character is taken; 3 the entry bound (64) is not checked;
 *   4 a replace takes the target's place but the target's original is never restored when the replacer is dropped;
 *   5 the banner is written while the music volume is 0; 6 the banner code is not verified (any build gets the banner);
 *   7 the banner strings are written without their NUL; 8 the plan does not drop the replaces of a dropped mod's tracks. */
#include "bm_music.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "recomp_cfg.h"

#include "bm_music_parse.inc"

int bo3_music_parse(const char *text, size_t n, const char *mod_id, bo3_music_decl *out, char *why, size_t wn)
{
    return mu_parse(text, n, mod_id, out, why, wn);
}

int bo3_music_replace_listed(const char *key, const char *const *ids, int nids)
{
    return mu_replace_listed(key, ids, nids);
}

int bo3_music_title_ok(const char *s)
{
    return mu_title_ok(s);
}

/* ---------------------------------------------------------------- the plan */
static int find_key(const bo3_music_plan *p, const char *key)
{
    for (uint32_t i = 0; i < p->ntr; i++)
        if (!strcmp(p->tr[i].key, key))
            return (int)i;
    return -1;
}

/* the original (adding) mod / entry of each track, kept beside the plan */
static struct { int mod; uint32_t entry; } s_orig[BO3_MUSIC_MAX_TRACKS];

static int title_used(const bo3_music_plan *p, const bo3_music_decl *d, int st, const char *title, int except)
{
    for (uint32_t i = 0; i < p->ntr; i++)
        if ((int)i != except && p->tr[i].st == st && mu_eq_nocase(d[p->tr[i].mod].e[p->tr[i].entry].title, title))
            return 1;
    return 0;
}

static const bo3_music_decl *s_plan_decl;

int bo3_music_plan_make(const bo3_music_decl *d, int n, bo3_music_plan *p)
{
    int skipped = 0;
    memset(p, 0, sizeof *p);
    s_plan_decl = d;
    for (int m = 0; m < n; m++) {
        int st = -1;
        if (!d[m].present)
            continue;
        if (d[m].soundtrack[0]) {
            int dup = 0;
            for (uint32_t s = 0; s < p->nst; s++)
                dup |= mu_eq_nocase(p->st[s].name, d[m].soundtrack);
            if (dup || p->nst >= BO3_MUSIC_MAX_MODS) {
                skipped += (int)d[m].n;
                continue;                                  /* (the admission refuses this mod first) */
            }
            st = (int)p->nst++;
            snprintf(p->st[st].name, sizeof p->st[st].name, "%s", d[m].soundtrack);
            p->st[st].mod = m;
        }
        for (uint32_t k = 0; k < d[m].n; k++) {
            const bo3_music_entry *e = &d[m].e[k];
            int t = find_key(p, e->key);
            if (!e->replace) {
                if (t >= 0 || p->ntr >= BO3_MUSIC_MAX_TRACKS || st < 0) {
                    skipped++;
                    continue;
                }
                t = (int)p->ntr++;
                snprintf(p->tr[t].key, sizeof p->tr[t].key, "%s", e->key);
                p->tr[t].mod = m;
                p->tr[t].entry = k;
                p->tr[t].st = st;
                s_orig[t].mod = m;
                s_orig[t].entry = k;
            } else {
                if (t < 0 || p->tr[t].mod != s_orig[t].mod || title_used(p, d, p->tr[t].st, e->title, t)) {
                    skipped++;                             /* no such track, already replaced, or a title twice in its list */
                    continue;
                }
                p->tr[t].mod = m;
                p->tr[t].entry = k;
            }
        }
    }
    return skipped;
}

void bo3_music_plan_drop_mod(bo3_music_plan *p, int m)
{
    for (uint32_t s = 0; s < p->nst; s++)
        if (p->st[s].mod == m)
            p->st[s].dropped = 1;
    for (uint32_t i = 0; i < p->ntr; i++) {
        if (s_orig[i].mod == m || p->st[p->tr[i].st].dropped) {
#if MUSIC_MUT != 8
            p->tr[i].dropped = 1;
#endif
        } else if (p->tr[i].mod == m) {                    /* a replace by m: the original plays again */
#if MUSIC_MUT != 4
            int clash = s_plan_decl && title_used(p, s_plan_decl, p->tr[i].st, s_plan_decl[s_orig[i].mod].e[s_orig[i].entry].title,
                                                  (int)i);
            if (clash) {
                p->tr[i].dropped = 1;
            } else {
                p->tr[i].mod = s_orig[i].mod;
                p->tr[i].entry = s_orig[i].entry;
            }
#else
            (void)s_plan_decl;
            p->tr[i].dropped = 1;
#endif
        }
    }
}

int bo3_music_plan_find(const bo3_music_plan *p, const bo3_music_decl *d, const char *folder, const char *file)
{
    const char *dot;
    size_t tl;
    if (!folder || !file || !(dot = strrchr(file, '.')))
        return -1;
    tl = (size_t)(dot - file);
    for (uint32_t i = 0; i < p->ntr; i++) {
        const bo3_music_entry *e;
        if (p->tr[i].dropped || p->st[p->tr[i].st].dropped || !mu_eq_nocase(p->st[p->tr[i].st].name, folder))
            continue;
        e = &d[p->tr[i].mod].e[p->tr[i].entry];
        if (strlen(e->title) == tl) {
            int same = 1;
            for (size_t c = 0; c < tl && same; c++)
                same = mu_lower((unsigned char)e->title[c]) == mu_lower((unsigned char)file[c]);
            if (same && mu_eq_nocase(dot, mu_ext_of(e->file)))
                return (int)i;
        }
    }
    return -1;
}

/* ---------------------------------------------------------------- the banner */
#define BN_CODE_VA   0x00153149u                 /* sub_001530D0: the EA GAMES TRAX record's three strings -> the banner */
#define BN_VOL_VA    0x00153869u                 /* sub_001537C0: no banner while the music volume is 0 */
#define BN_TITLE     0x0045BB10u
#define BN_ARTIST    0x0045BB14u
#define BN_ALBUM     0x0045BB18u
#define BN_TIME      0x0045BB0Cu
#define BN_VOLUME    0x004AE1D5u
static const uint8_t k_code[0x51] = {
    0x8b, 0x88, 0x40, 0x05, 0x00, 0x00, 0x8b, 0x15, 0x2c, 0x53, 0x4d, 0x00, 0x8b, 0x52, 0x0c, 0xf3, 0x0f, 0x10, 0x05, 0x94,
    0x16, 0x3b, 0x00, 0x56, 0x8b, 0x71, 0x0c, 0x8b, 0x34, 0xb2, 0x57, 0x8b, 0x79, 0x10, 0x8b, 0x3c, 0xba, 0x8b, 0x49, 0x08,
    0x8b, 0x14, 0x8a, 0x89, 0x3d, 0x14, 0xbb, 0x45, 0x00, 0x89, 0x35, 0x18, 0xbb, 0x45, 0x00, 0x5f, 0x89, 0x15, 0x10, 0xbb,
    0x45, 0x00, 0xf3, 0x0f, 0x11, 0x05, 0x0c, 0xbb, 0x45, 0x00, 0xc7, 0x80, 0x4c, 0x05, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,
    0x5e};
static const uint8_t k_vol[0x11] = {0x38, 0x1d, 0xd5, 0xe1, 0x4a, 0x00, 0x0f, 0x9e, 0xc0, 0x88, 0x87, 0x65, 0x05, 0x00, 0x00,
                                    0x5b, 0xc3};

static bo3_music_guest s_g;
static int s_bn_ok, s_bn_cfg;
static uint32_t s_bn_buf[2], s_bn_next, s_bn_count;

int bo3_music_banner_configure(const bo3_music_guest *g)
{
    uint8_t a[sizeof k_code], b[sizeof k_vol];
    s_g = *g;
    s_bn_cfg = 1;
    s_bn_buf[0] = s_bn_buf[1] = 0;
    s_bn_next = s_bn_count = 0;
    s_bn_ok = s_g.read(s_g.user, BN_CODE_VA, a, sizeof a) && !memcmp(a, k_code, sizeof a) &&
              s_g.read(s_g.user, BN_VOL_VA, b, sizeof b) && !memcmp(b, k_vol, sizeof b);
#if MUSIC_MUT == 6
    s_bn_ok = 1;                                         /* defect: not verified */
#endif
    return s_bn_ok;
}

static int put16(uint32_t va, const char *s)
{
    size_t n = strlen(s);
    uint16_t w[BO3_MUSIC_TEXT_MAX + 1];
    for (size_t i = 0; i <= n && i <= BO3_MUSIC_TEXT_MAX; i++)
        w[i] = (uint16_t)(unsigned char)s[i];
#if MUSIC_MUT == 7
    return s_g.write(s_g.user, va, w, (uint32_t)(2u * n));     /* defect: no NUL */
#else
    return s_g.write(s_g.user, va, w, (uint32_t)(2u * (n + 1u)));
#endif
}

int bo3_music_banner_show(const char *title, const char *artist, const char *album)
{
    int8_t vol = 0;
    uint32_t buf;
    float t = BO3_MUSIC_BANNER_SECS;
    if (!s_bn_cfg || !s_bn_ok || !title || !artist)
        return 0;
    if (!s_g.read(s_g.user, BN_VOLUME, &vol, 1))
        return 0;
#if MUSIC_MUT != 5
    if (vol <= 0)
        return 0;                                        /* the title's rule (0x153869: setle -> no banner) */
#endif
    if (!s_bn_buf[s_bn_next]) {
        s_bn_buf[s_bn_next] = s_g.alloc ? s_g.alloc(s_g.user, 3u * 64u) : 0;
        if (!s_bn_buf[s_bn_next])
            return 0;
    }
    buf = s_bn_buf[s_bn_next];
    s_bn_next ^= 1u;                                     /* two blocks: the next song's texts are new pointers */
    if (!put16(buf, title) || !put16(buf + 64u, artist) || !put16(buf + 128u, album ? album : ""))
        return 0;
    {
        uint32_t tv = buf, av = buf + 64u, lv = buf + 128u;
        if (!s_g.write(s_g.user, BN_ARTIST, &av, 4) || !s_g.write(s_g.user, BN_ALBUM, &lv, 4) ||
            !s_g.write(s_g.user, BN_TITLE, &tv, 4) || !s_g.write(s_g.user, BN_TIME, &t, 4))
            return 0;
    }
    s_bn_count++;
    return 1;
}

uint32_t bo3_music_banner_count(void)
{
    return s_bn_count;
}

/* ---------------------------------------------------------------- the game */
#ifdef BO3_MUSIC_GAME
#include <stdatomic.h>
#include <sys/stat.h>

#include "bm_guest.h"
#include "modfs.h"
#include "soundtrack/xbox_soundtrack.h"
#include "kernel.h"

extern uint32_t xbox_HeapAlloc(uint32_t size, uint32_t align);
extern void bo3_soundtrack_use_mod_music(const char *dir);   /* soundtrack.c */
extern int bo3_soundtrack_player_folder(void);                /* soundtrack.c: the player's own folder is set */

/* GP-P4.1 (integration review of music1): the admitted mods' music is staged in a HOST CACHE, never in the player's saves
 * (music1 staged in the save folder's TDATA\FFFE0000\BMMUSIC, the game's own save container area). The cache root:
 * BMASHUP_MUSIC_CACHE (a folder; guarded runs / tests) > %LOCALAPPDATA%\BurnoutMashup\music-cache (Windows) >
 * $XDG_CACHE_HOME/burnoutmashup/music-cache > $HOME/.cache/burnoutmashup/music-cache. Each set of music (the planned
 * soundtracks, titles, file types and sizes) gets its own folder "set-<16 hex FNV-1a>" - the folder given to the custom-music
 * path holds exactly this start's soundtracks (a mod turned off is not listed any more). Nothing is ever deleted: older set-*
 * folders stay until the player removes the cache folder (any of it can be deleted; it is re-made at the next start). */
static int music_cache_root(char *out, size_t n)
{
    const char *e = getenv("BMASHUP_MUSIC_CACHE");
    if (e && *e)
        return snprintf(out, n, "%s", e) < (int)n;
#if defined(_WIN32)
    e = getenv("LOCALAPPDATA");
    if (e && *e)
        return snprintf(out, n, "%s\\BurnoutMashup\\music-cache", e) < (int)n;
#else
    e = getenv("XDG_CACHE_HOME");
    if (e && *e)
        return snprintf(out, n, "%s/burnoutmashup/music-cache", e) < (int)n;
    e = getenv("HOME");
    if (e && *e)
        return snprintf(out, n, "%s/.cache/burnoutmashup/music-cache", e) < (int)n;
#endif
    return 0;
}

static bo3_music_decl *s_decl;                           /* [BO3_MODFS_MAX_MODS] */
static char s_modid[BO3_MODFS_MAX_MODS][BO3_MUSIC_MODID_MAX + 1];
static bo3_music_plan s_plan;
static int s_on;
static char s_stage[1100];

static int g_read(void *u, uint32_t va, void *out, uint32_t n)
{
    (void)u;
    return bo3_guest_read(va, out, n);
}

static int g_write(void *u, uint32_t va, const void *in, uint32_t n)
{
    (void)u;
    return bo3_guest_write(va, in, n);
}

static uint32_t g_alloc(void *u, uint32_t size)
{
    (void)u;
    return xbox_HeapAlloc(size, 16u);
}

#if defined(_WIN32)
static int to_utf8(const xbox_host_char *w, char *out, size_t n)
{
    return WideCharToMultiByte(CP_UTF8, 0, w, -1, out, (int)n, NULL, NULL) > 0;
}
static int mk(const char *p)
{
    WCHAR w[1100];
    if (!MultiByteToWideChar(CP_UTF8, 0, p, -1, w, 1100))
        return 0;
    return CreateDirectoryW(w, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
}
#else
#include <errno.h>
static int to_utf8(const xbox_host_char *w, char *out, size_t n)
{
    snprintf(out, n, "%s", w);
    return 1;
}
static int mk(const char *p)
{
    return mkdir(p, 0755) == 0 || errno == EEXIST;
}
#endif

static long long file_size(const char *p)
{
    FILE *f = fopen(p, "rb");
    long long n;
    if (!f)
        return -1;
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return -1;
    }
    n = (long long)ftell(f);
    fclose(f);
    return n;
}

/* dst gets src's bytes unless it already has them; 1 ok */
static int copy_file(const char *src, const char *dst)
{
    FILE *a = fopen(src, "rb"), *b;
    char *x = NULL, *y = NULL;
    long long n = file_size(src), m = file_size(dst);
    int ok = 0;
    if (!a || n < 0)
        goto out;
    x = (char *)malloc((size_t)n + 1);
    if (!x || fread(x, 1, (size_t)n, a) != (size_t)n)
        goto out;
    if (m == n && (b = fopen(dst, "rb")) != NULL) {
        y = (char *)malloc((size_t)n + 1);
        if (y && fread(y, 1, (size_t)n, b) == (size_t)n && !memcmp(x, y, (size_t)n)) {
            fclose(b);
            ok = 1;
            goto out;
        }
        fclose(b);
    }
    if ((b = fopen(dst, "wb")) == NULL)
        goto out;
    ok = fwrite(x, 1, (size_t)n, b) == (size_t)n;
    ok &= fclose(b) == 0;
out:
    if (a)
        fclose(a);
    free(x);
    free(y);
    return ok;
}

void bo3_music_game_apply(void)
{
    int nm = 0, map[BO3_MODFS_MAX_MODS], dropped = 0;
    unsigned long long all = 0;
    xbox_host_char hs[1100];
    s_decl = (bo3_music_decl *)calloc(BO3_MODFS_MAX_MODS, sizeof *s_decl);
    if (!s_decl)
        return;
    for (int i = 0; i < bo3_modfs_mod_count() && i < BO3_MODFS_MAX_MODS; i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        char path[BO3_MODFS_PATH_MAX + 16], why[400];
        char *text = NULL;
        size_t n = 0;
        if (!m || !m->usable || !m->enabled)
            continue;
        if (!bo3_modfs_mod_file(m, "mod.toml", path, sizeof path) || bo3_modfs_read_whole(path, &text, &n) != 1) {
            free(text);
            continue;
        }
        if (!bo3_music_parse(text, n, m->manifest.id, &s_decl[nm], why, sizeof why)) {
            /* (the admission refuses an invalid declaration first: unreachable for an admitted mod) */
            fprintf(stderr, "[MUSIC] ERROR: mod %s: %s: its music is not offered\n", m->manifest.id, why);
            memset(&s_decl[nm], 0, sizeof s_decl[nm]);
        }
        free(text);
        if (!s_decl[nm].present)
            continue;
        snprintf(s_modid[nm], sizeof s_modid[nm], "%s", m->manifest.id);
        map[nm++] = i;
    }
    if (!nm)
        return;
    {
        int skipped = bo3_music_plan_make(s_decl, nm, &s_plan);
        if (skipped)
            fprintf(stderr, "[MUSIC] %d entr%s skipped (refused by the admission rules)\n", skipped, skipped == 1 ? "y" : "ies");
    }
    /* the files: each must be in its mod's folder, a plain file, <= 64 MiB, playable; all <= 512 MiB */
    for (uint32_t t = 0; t < s_plan.ntr; t++) {
        bo3_music_track *tr = &s_plan.tr[t];
        const bo3_music_entry *e = &s_decl[tr->mod].e[tr->entry];
        const bo3_mod *m = bo3_modfs_mod(map[tr->mod]);
        char path[BO3_MODFS_PATH_MAX + 16], ttl[64];
        const char *why = NULL;
        uint32_t ms = 0;
        long long sz;
        if (tr->dropped)
            continue;
        if (!bo3_modfs_mod_file(m, e->file, path, sizeof path))
            why = "not found in the mod's folder (or not a plain file)";
        else if ((sz = file_size(path)) < 0)
            why = "not readable";
        else if (sz > (long long)BO3_MUSIC_FILE_BYTES)
            why = "larger than 64 MiB";
        else if (all + (unsigned long long)sz > BO3_MUSIC_ALL_BYTES)
            why = "the mods' music files would be larger than 512 MiB in all";
        else {
            const char *pw = NULL;                          /* xst_probe_why sets "" on success: only its 0 is a refusal */
            if (!xst_probe_why(path, &ms, ttl, sizeof ttl, &pw))
                why = pw && *pw ? pw : "not a file the host plays";
            else
                all += (unsigned long long)sz;
        }
        if (why) {
            fprintf(stderr, "[MUSIC] ERROR: mod %s: %s (%s): %s; the mod's music is not offered\n", s_modid[tr->mod], e->file,
                    tr->key, why);
            bo3_music_plan_drop_mod(&s_plan, tr->mod);
            dropped++;
            t = (uint32_t)-1;                               /* again from the start: the plan changed */
            all = 0;
        }
    }
    if (bo3_soundtrack_player_folder()) {
        fprintf(stderr, "[MUSIC] the player's own music folder is set (audio.custom_music_dir): the mods' music (%u "
                "soundtrack%s) is not offered\n", (unsigned)s_plan.nst, s_plan.nst == 1 ? "" : "s");
        return;
    }
    {
        /* GP-P4.1: the host cache (K1a), one folder per set of music */
        char root[900];
        uint64_t h = 1469598103934665603ull;
        (void)hs;
        (void)to_utf8;
        if (!music_cache_root(root, sizeof root)) {
            fprintf(stderr, "[MUSIC] ERROR: no music cache folder (BMASHUP_MUSIC_CACHE, LOCALAPPDATA, XDG_CACHE_HOME or HOME): "
                    "the mods' music is not offered\n");
            return;
        }
        for (uint32_t s = 0; s < s_plan.nst; s++)
            for (uint32_t t = 0; t < s_plan.ntr; t++) {
                const bo3_music_track *tr = &s_plan.tr[t];
                const bo3_music_entry *e = &s_decl[tr->mod].e[tr->entry];
                char src[BO3_MODFS_PATH_MAX + 16], line[400];
                long long sz = -1;
                if (s_plan.st[s].dropped || tr->st != (int)s || tr->dropped)
                    continue;
                if (bo3_modfs_mod_file(bo3_modfs_mod(map[tr->mod]), e->file, src, sizeof src))
                    sz = file_size(src);
                snprintf(line, sizeof line, "%s\n%s%s\n%lld\n", s_plan.st[s].name, e->title, mu_ext_of(e->file), sz);
                for (const char *c = line; *c; c++)
                    h = (h ^ (uint8_t)*c) * 1099511628211ull;
            }
        if (snprintf(s_stage, sizeof s_stage, "%s/set-%016llx", root, (unsigned long long)h) >= (int)sizeof s_stage) {
            fprintf(stderr, "[MUSIC] ERROR: the music cache path is too long: the mods' music is not offered\n");
            return;
        }
    }
    {
        /* GP-P4.1: the cache folder and its parents exist or are made (never the player's saves) */
        char up[1100];
        snprintf(up, sizeof up, "%s", s_stage);
        for (size_t i = 1; up[i]; i++)
            if (up[i] == '/' || up[i] == '\\') {
                char c = up[i];
                up[i] = 0;
                mk(up);
                up[i] = c;
            }
        mk(s_stage);
    }
    {
        int nst = 0, ntr = 0;
        for (uint32_t s = 0; s < s_plan.nst; s++) {
            char dir[1300];
            if (s_plan.st[s].dropped)
                continue;
            snprintf(dir, sizeof dir, "%s/%s", s_stage, s_plan.st[s].name);
            if (!mk(dir)) {
                fprintf(stderr, "[MUSIC] ERROR: %s cannot be made: soundtrack \"%s\" is not offered\n", dir, s_plan.st[s].name);
                s_plan.st[s].dropped = 1;
                continue;
            }
            nst++;
            for (uint32_t t = 0; t < s_plan.ntr; t++) {
                bo3_music_track *tr = &s_plan.tr[t];
                const bo3_music_entry *e = &s_decl[tr->mod].e[tr->entry];
                char src[BO3_MODFS_PATH_MAX + 16], dst[1400];
                if (tr->st != (int)s || tr->dropped)
                    continue;
                snprintf(dst, sizeof dst, "%s/%s%s", dir, e->title, mu_ext_of(e->file));
                if (!bo3_modfs_mod_file(bo3_modfs_mod(map[tr->mod]), e->file, src, sizeof src) || !copy_file(src, dst)) {
                    fprintf(stderr, "[MUSIC] ERROR: %s cannot be copied to %s: track %s is not offered\n", e->file, dst, tr->key);
                    tr->dropped = 1;
                    continue;
                }
                ntr++;
                fprintf(stderr, "[MUSIC] soundtrack \"%s\": \"%s\" by %s%s%s (%s, mod %s%s)\n", s_plan.st[s].name, e->title,
                        e->artist, e->album[0] ? ", " : "", e->album, tr->key, s_modid[tr->mod],
                        strcmp(s_modid[tr->mod], s_modid[s_plan.st[s].mod]) ? ": replaces the track" : "");
            }
        }
        /* GP-P4.1: this set's folder holds only this plan's soundtracks (K1a); nothing is deleted */
        if (!ntr) {
            fprintf(stderr, "[MUSIC] no track of the mods can be offered\n");
            return;
        }
        s_on = 1;
        fprintf(stderr, "[MUSIC] %d soundtrack%s, %d track%s from %d mod%s staged in %s (%d mod%s music dropped); offered "
                "as the custom-music folder (EA GAMES TRAX, X)\n", nst, nst == 1 ? "" : "s", ntr, ntr == 1 ? "" : "s", nm,
                nm == 1 ? "" : "s", s_stage, dropped, dropped == 1 ? "'s" : "s'");
    }
    {
        static const bo3_music_guest g = {g_read, g_write, g_alloc, NULL};
        int ok = bo3_music_banner_configure(&g);
        fprintf(stderr, "[MUSIC] track banner: %s\n", ok ? "the title's banner code verified (0x153149, 0x153869): the songs' "
                "title / artist / album are shown when they start" : "the title's banner code does NOT match this build: no "
                "banner (the music still plays)");
    }
    bo3_soundtrack_use_mod_music(s_stage);
}

/* handle -> song, from the title's file thread (sub_001D0554 wrap) */
#define NOTE_SLOTS 16
static struct { _Atomic uint32_t handle, song; } s_note[NOTE_SLOTS];
static _Atomic uint32_t s_note_next;

void bo3_music_note_open(uint32_t handle, uint32_t song)
{
    uint32_t i;
    if (!s_on || !handle || handle == 0xFFFFFFFFu)
        return;
    i = atomic_fetch_add(&s_note_next, 1u) % NOTE_SLOTS;
    atomic_store(&s_note[i].handle, 0u);
    atomic_store(&s_note[i].song, song);
    atomic_store(&s_note[i].handle, handle);
}

static const char *leaf(const char *p, const char **parent, size_t *plen)
{
    const char *l = p, *prev = NULL;
    for (const char *c = p; *c; c++)
        if (*c == '/' || *c == '\\') {
            prev = l;
            l = c + 1;
        }
    *parent = prev;
    *plen = prev ? (size_t)(l - 1 - prev) : 0;
    return l;
}

void bo3_music_song_started(uint32_t handle)
{
    const xst_library *lib;
    const xst_song *s;
    const char *file, *par;
    char folder[64];
    size_t pl;
    uint32_t song = 0;
    int t, found = 0;
    if (!s_on)
        return;
    for (uint32_t i = 0; i < NOTE_SLOTS && !found; i++)
        if (atomic_load(&s_note[i].handle) == handle) {
            song = atomic_load(&s_note[i].song);
            found = 1;
        }
    lib = xbox_SoundtrackLibrary();
    if (!found || !lib || !(s = xst_song_by_id(lib, song)) || !s->path)
        return;
    file = leaf(s->path, &par, &pl);
    if (!par || pl >= sizeof folder)
        return;
    memcpy(folder, par, pl);
    folder[pl] = 0;
    t = bo3_music_plan_find(&s_plan, s_decl, folder, file);
    if (t < 0)
        return;
    {
        const bo3_music_entry *e = &s_decl[s_plan.tr[t].mod].e[s_plan.tr[t].entry];
        int shown = bo3_music_banner_show(e->title, e->artist, e->album);
        fprintf(stderr, "[MUSIC] song started: \"%s\" by %s%s%s (%s): banner %s\n", e->title, e->artist, e->album[0] ? ", " : "",
                e->album, s_plan.tr[t].key, shown ? "written (title / artist / album, 5 s)" :
                "not written (not verified, music volume 0, or no guest memory)");
    }
}
#endif
