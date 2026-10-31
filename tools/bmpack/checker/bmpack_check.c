/* bmpack validate: a mod set's declarations through the host's REAL parsers and rules, in the game's boot order. Compiled by
 * bmpack.py from the tree's own sources (modmanifest.c, bm_admit.c, bm_tracks.c, bm_tracks_progress.c, bm_regions.c,
 * bm_names.c, bm_wtour.c, bm_xevents.c, bm_progress*.c, bm_guest.c, recomp_cfg.c) + the game's PrgData relocation
 * (sub_00159710 / sub_001596B0, extracted unchanged from the tree's generated code by g8_limits\l4\scripts\extract_fns.py).
 *   bmpack_check TLIST.BIN DEFAULT.XBE PRGDATA.BIN STAGEHED.BIN ROOT=<i> MODDIR [ROOT=<i> MODDIR ...]
 * The mods are given as (root index, folder); the checker orders them as modfs does (root, then manifest id; a shared id
 * makes every copy unusable). Steps (the game's): manifests (bo3_manifest_parse) + the platform gate -> P3: the two-phase
 * admission (bo3_admit_run over the usable mods in the mod list's order, as modfs.c list_mods: the later mod of a clash is
 * refused ALONE, before any service sees it) -> every admitted mod's [bmashup.regions] -> per mod [bmashup.tracks] (parse,
 * append to the retail tlist.bin image with the files check, register, the track's progress shadow) and its names -> every
 * mod's [bmashup.extra_events] (P3: their name / help texts join the text table) -> the text table's install over the
 * language file (Data\Globalus.bin, BMPACK_LANG) -> W1's resolve on the guest image -> for each event: W2 / W3 / W7 (its
 * list row and help-bar text as the game resolves them), the stage record (W5), the Gamedata record (W8).
 * Mod kit (platform 0.1.0 / 0.1.1): the platform gate (bo3_manifest_platform_check) runs where modfs.c runs it.
 * BMPACK_MUT=9 (tests only): the gate is not called; BMPACK_MUT=11: the admission is not called (p2's behaviour).
 * bmpack 1.3 (GP-DEPS1, platform 0.1.2): after modfs's order, the host's dependency order (bo3_admit_order over every listed mod,
 * the usable mods' mod.toml) as bm_admit.c's game glue applies it; the admission is bo3_admit_run_deps with the listed mods that
 * take no part (not usable) as "known"; the reason is kept as the game keeps it (BO3_ADMIT_WHY - 1 = 699 characters).
 * BMPACK_MUT=13 (tests only): the dependency order is not applied.
 * BMPACK_SAVE_DIR (optional): the progress sidecar is opened there as the game opens it (<dir>\UDATA\4541005b\<save>\Profile
 * 1 must exist); BMASHUP_PROGRESS_DIR as in the game.
 * Output: one JSON object on stdout (P3: + admission, labels, event row / help texts, guest_fnv64 = FNV-1a 64 of the whole
 * guest image after every step, tlist_fnv64). Exit 0 = every declaration accepted, 1 = refusals, 2 = usage / input error. */
/* bmpack 1.5.0 (mod kit 0.7.0, main19): main19 readers (platform 0.1.9), no checker change.
 * bmpack 1.4.0 (mod kit 0.5.0, main18): the loader's mod cap mirrored (BO3_ADMIT_MAX).
 * bmpack 1.3.4 (mod kit 0.4.1): compiled from the kit's host-readers SOURCE package (tools\bmpack\host_readers: the p4.4 host's
 * own readers / admission code + xboxrecomp's recomp_cfg.c, both MIT). No generated game code: the PrgData relocation is
 * re-implemented below (prg_relocate) from the loader's documented behaviour. BMPACK_DEV_GENRELOC (developer differential test
 * only, never in the kit) links the extracted original routine instead, to prove both give the same guest image. */
#ifdef BMPACK_DEV_GENRELOC
#include "recomp_types.h"
#else
#include <stddef.h>
#include <stdint.h>
#endif
#include "bm_admit.h"
#include "bm_guest.h"
#include "bm_names.h"
#include "bm_progress.h"
#include "bm_regions.h"
#include "bm_tracks.h"
#include "bm_wtour.h"
#include "bm_xevents.h"
#ifdef BMPACK_WT4
#include "bm_wt4.h"
#endif
#include "modmanifest.h"

#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#ifndef BMPACK_MUT
#define BMPACK_MUT 0
#endif

ptrdiff_t g_xbox_mem_offset;          /* the host readers reach guest memory through this offset */
#ifdef BMPACK_DEV_GENRELOC
/* the generated code's runtime state (developer differential build only) */
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp, g_seh_ebp, g_fs_base, g_eflags;
RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7;
RECOMP_TLS uint64_t g_mm0, g_mm1, g_mm2, g_mm3;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top, g_df, g_fp_cmp;
RECOMP_TLS uint16_t g_fp_control_word, g_fp_cc;
uint32_t g_xbox_code_lo, g_xbox_code_hi;
volatile uint32_t g_icall_trace[ICALL_TRACE_SIZE];
volatile uint32_t g_icall_trace_idx;
volatile uint64_t g_icall_count;
recomp_func_t recomp_lookup_manual(uint32_t va) { (void)va; return NULL; }
recomp_func_t recomp_lookup(uint32_t va) { (void)va; return NULL; }
recomp_func_t recomp_lookup_kernel(uint32_t va) { (void)va; return NULL; }
void recomp_icall_fail_log(uint32_t va) { (void)va; }
void recomp_icall_not_code_log(uint32_t va) { (void)va; }
void recomp_abi_violation_log(uint32_t va, uint32_t b, uint32_t s, uint32_t d, uint32_t p) { (void)va; (void)b; (void)s; (void)d; (void)p; }
void ck_sub_00159710(void);
#endif

#define COMMIT   0x04000000u
size_t xbox_GetMappedSize(void) { return COMMIT; }
uint32_t xbox_ContiguousBlockSize(uint32_t va) { (void)va; return 0; }

#define STACKTOP 0x03F00000u
#define PRG      0x01000000u
#define STG      0x01100000u
#define GDH      0x01200000u
#define LANG     0x01300000u
#define ESPX     0x03E80000u             /* W3's stack frame stand-in (text at +0x18) */
#define MENU     0x0054FFA0u             /* the World Tour menu object */
#define HEAP0    0x02800000u
#define HEAPEND  0x03800000u
static uint8_t *mem;
static uint32_t s_heap = HEAP0;
#define G32(va) (*(uint32_t *)(mem + (uint32_t)(va)))
#define G16(va) (*(uint16_t *)(mem + (uint32_t)(va)))
#define G8(va)  (*(uint8_t *)(mem + (uint32_t)(va)))

#ifndef BMPACK_DEV_GENRELOC
/* The game loader's PrgData relocation (its effect on the image; the kit's own code). PrgData.bin loaded at base B:
 *   +4 groups pointer, +8 group count (signed), +0xC a pointer: both pointers += B;
 *   group g (8 bytes at groups + 8 g): +0 records pointer += B, +4 record count (signed);
 *   record r (0x18 bytes): +0x10 items pointer += B, +0x14 item count (signed); item k (0x40 bytes): +0x34 pointer += B.
 * Counts are read after the enclosing pointer is relocated, in this order, as the loader does. */
static void prg_relocate(uint32_t b)
{
    G32(b + 4u) += b;
    for (int32_t i = 0; i < (int32_t)G32(b + 8u); i++) {
        uint32_t g = G32(b + 4u) + 8u * (uint32_t)i;
        G32(g) += b;
        for (int32_t j = 0; j < (int32_t)G32(g + 4u); j++) {
            uint32_t r = G32(g) + 0x18u * (uint32_t)j;
            G32(r + 0x10u) += b;
            for (int32_t k = 0; k < (int32_t)G32(r + 0x14u); k++)
                G32(G32(r + 0x10u) + 0x40u * (uint32_t)k + 0x34u) += b;
        }
    }
    G32(b + 0xCu) += b;
}
#endif

/* bmpack 1.4.0: the loader takes at most BO3_ADMIT_MAX (= BO3_MODFS_MAX_MODS) mods (modfs.c find_mods,
 * in the order the roots / names give); the rest are reported, not silently dropped. */
#define MAXM (BO3_ADMIT_MAX + 1)
typedef struct modrec {
    int root, usable, gate, admit;         /* gate: refused by the platform gate; admit: refused by the P3 admission */
    int needs;                             /* 1.3: refused for [bmashup] requires_mods (admit is 1 too) */
    char need[96];
    const char *dir;
    char *text;
    size_t len;
    bo3_manifest man;
    char problem[1200];
    char label[BO3_ADMIT_LABEL];
} modrec;
static modrec s_m[MAXM];
static int s_nm, s_moved;
static modrec *s_ord[MAXM];
static uint32_t s_gd_off[BO3_WT_MAX], s_gd_alias[BO3_WT_MAX];   /* per event: the Gamedata record a launch reads, alias (0 = own) */
static uint32_t s_row_id[BO3_WT_MAX], s_help_id[BO3_WT_MAX];
static int s_ui_ok[BO3_WT_MAX];

/* JSON output */
static int s_nref;
static void jstr(const char *s)
{
    putchar('"');
    for (; s && *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\')
            printf("\\%c", c);
        else if (c < 0x20)
            printf("\\u%04x", c);
        else
            putchar(c);
    }
    putchar('"');
}
static char s_refs[64 * 1024];
static size_t s_refs_n;
static void refusal(const char *service, const char *mod, const char *why)
{
    char *o = s_refs + s_refs_n;
    size_t room = sizeof s_refs - s_refs_n;
    int n;
    n = snprintf(o, room, "%s\x1f%s\x1f%s\x1e", service, mod ? mod : "", why ? why : "");
    if (n > 0 && (size_t)n < room)
        s_refs_n += (size_t)n;
    s_nref++;
    fprintf(stderr, "refused [%s] %s: %s\n", service, mod ? mod : "", why ? why : "");
}

static char *slurp(const char *path, size_t *n)
{
    FILE *f = fopen(path, "rb");
    char *b;
    long l;
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    l = ftell(f);
    fseek(f, 0, SEEK_SET);
    b = malloc((size_t)l + 1);
    if (!b || fread(b, 1, (size_t)l, f) != (size_t)l) {
        fclose(f);
        free(b);
        return NULL;
    }
    fclose(f);
    b[l] = 0;
    *n = (size_t)l;
    return b;
}

static int files_fn(void *user, int mod, const char *rel)
{
    char p[1400];
    FILE *f;
    (void)user;
    snprintf(p, sizeof p, "%s\\files\\%s", s_ord[mod]->dir, rel);
    if (!(f = fopen(p, "rb")))
        return 0;
    fclose(f);
    return 1;
}

static uint32_t halloc(uint32_t size, uint32_t align)
{
    uint32_t va = (s_heap + align - 1u) & ~(align - 1u);
    if (va + size > HEAPEND)
        return 0;
    s_heap = va + size;
    memset(mem + va, 0, size);
    return va;
}

/* the text table's guest access (bm_names.c bo3_nm_guest) */
static uint32_t n_rd32(void *u, uint32_t va) { (void)u; return va < COMMIT - 4 ? G32(va) : 0; }
static void n_wr32(void *u, uint32_t va, uint32_t v) { (void)u; if (va < COMMIT - 4) G32(va) = v; }
static void n_wr16(void *u, uint32_t va, uint16_t v) { (void)u; if (va < COMMIT - 2) G16(va) = v; }
static uint32_t n_alloc(void *u, uint32_t size) { (void)u; return halloc(size, 16u); }

/* the string the game shows for text ID id: [[0x4D532C] + 0xC][id] (UTF-16, ASCII here) */
static void text_of(uint32_t id, char *out, size_t n)
{
    uint32_t blob = G32(0x4D532Cu), arr, p;
    size_t k = 0;
    out[0] = 0;
    if (!blob || blob >= COMMIT)
        return;
    arr = G32(blob + 0xCu);
    if (!arr || arr + 4u * id >= COMMIT)
        return;
    p = G32(arr + 4u * id);
    while (p && p < COMMIT - 2 && G16(p) && k + 1 < n) {
        uint16_t c = G16(p);
        out[k++] = c < 0x80 ? (char)c : '?';
        p += 2;
    }
    out[k] = 0;
}

static uint64_t fnv64(const uint8_t *p, size_t n)
{
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; i++)
        h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

static jmp_buf s_jb;
static int s_wt_code;
static char s_wt_why[800];
static void on_wt_fail(int code, const char *why)
{
    s_wt_code = code;
    snprintf(s_wt_why, sizeof s_wt_why, "%s", why);
    longjmp(s_jb, 1);
}

static void load_xbe(const char *path)
{
    size_t n;
    uint32_t base, sh, cnt;
    uint8_t *x = (uint8_t *)slurp(path, &n);
    if (!x) {
        printf("{\"error\": \"cannot read default.xbe\"}\n");
        exit(2);
    }
    memcpy(&base, x + 0x104, 4);
    memcpy(&cnt, x + 0x11C, 4);
    memcpy(&sh, x + 0x120, 4);
    for (uint32_t i = 0; i < cnt; i++) {
        uint32_t h = sh - base + 0x38u * i, va, vsz, raw, rsz;
        memcpy(&va, x + h + 4, 4);
        memcpy(&vsz, x + h + 8, 4);
        memcpy(&raw, x + h + 12, 4);
        memcpy(&rsz, x + h + 16, 4);
        if (va + vsz < COMMIT && raw + rsz <= n)
            memcpy(mem + va, x + raw, rsz < vsz ? rsz : vsz);
    }
    free(x);
}

static int by_root_then_id(const void *a, const void *b)
{
    const modrec *x = *(modrec *const *)a, *y = *(modrec *const *)b;
    if (x->root != y->root)
        return x->root - y->root;
    if (x->usable != y->usable)
        return y->usable - x->usable;
    return x->usable ? strcmp(x->man.id, y->man.id) : strcmp(x->dir, y->dir);
}

/* W2 / W3 / W7 for event i: the location's list built (W2), its host row made (W3), the help bar asked with the cursor on
 * that row (W7) and on the location's first retail row (the game's own ID must come back unchanged) */
static void ui_event(uint32_t i)
{
    static const uint32_t base[3] = {0, 6, 0xE}, nl[3] = {6, 8, 4};
    char loc[13];
    uint64_t lv = 0;
    uint32_t region, value = 0, row, item;
    int retail;
    snprintf(loc, sizeof loc, "%s", bo3_wt_location_at(i));
    region = !strncmp(loc, "US", 2) ? 0 : !strncmp(loc, "EU", 2) ? 1 : 2;
    bo3_cc_encode(loc, &lv);
    while (value < nl[region] && memcmp(mem + 0x39E798u + 8 * (base[region] + value), &lv, 8))
        value++;
    retail = bo3_wt_location_events(region, value);
    if (retail < 0)
        return;
    G32(MENU + 0x78Cu + 4u * value) = (uint32_t)retail;      /* sub_000D80E0's counts before W2 (location index = value) */
    G32(MENU + 0x71Cu + 4u * value) = 0;
    G32(MENU + 0x7FCu + 4u * value) = 0;
    bo3_wt_gen_loc(MENU, region, value, value);
    G8(0x550886u) = 0;                                       /* the event list, first build */
    G8(0x550887u) = 0;
    G32(0x5501F4u) = region;
    G32(0x550204u) = value;
    if (bo3_wt_row_at(i) < 0)
        return;
    row = (uint32_t)bo3_wt_row_at(i);
    item = 0x550044u + 0x10u * row;
    G32(ESPX + 0x18u) = 0;
    if (!bo3_wt_gen_row(item, row, ESPX))
        return;
    s_row_id[i] = G32(ESPX + 0x18u);
    G16(0x5501F0u) = (uint16_t)row;                          /* the cursor on the host row */
    s_help_id[i] = bo3_wt_gen_help(0x21u);
    G16(0x5501F0u) = 0;                                      /* a retail row: the game's own ID unchanged */
    G32(0x550044u + 0xCu) = 0;
    s_ui_ok[i] = bo3_wt_gen_help(0x21u) == 0x21u;
}

int main(int argc, char **argv)
{
    static uint8_t tl[BO3_CC_TLIST_SIZE];
    char why[800], name[13];
    size_t len;
    char *t;
    uint32_t ntl;
    bo3_admit_res *ares = NULL;
    int nadm = 0, amap[MAXM];
    if (argc == 6 && argv[5][0] == '@') {     /* 1.4.0: "@FILE": the ROOT=i / DIR pairs, one "ROOT=i<TAB>DIR" a line */
        size_t rn;
        char *rt = slurp(argv[5] + 1, &rn), *ln, *nx;
        static char *av[5 + 2 * (MAXM + 64)];
        int ac = 5;
        if (!rt) {
            printf("{\"error\": \"the mod list file cannot be read\"}\n");
            return 2;
        }
        for (int k = 0; k < 5; k++)
            av[k] = argv[k];
        for (ln = rt; ln && *ln && ac + 2 <= (int)(sizeof av / sizeof av[0]); ln = nx) {
            char *tab;
            nx = strchr(ln, '\n');
            if (nx)
                *nx++ = 0;
            if (*ln && ln[strlen(ln) - 1] == '\r')
                ln[strlen(ln) - 1] = 0;
            if (!*ln || !(tab = strchr(ln, '\t')))
                continue;
            *tab = 0;
            av[ac++] = ln;
            av[ac++] = tab + 1;
        }
        argc = ac;
        argv = av;
    }
    if (argc < 5 || (argc - 5) % 2) {
        printf("{\"error\": \"usage: bmpack_check TLIST XBE PRGDATA STAGEHED ROOT=i DIR ...\"}\n");
        return 2;
    }
    setvbuf(stdout, NULL, _IOFBF, 1 << 20);
    if (!(t = slurp(argv[1], &len)) || len < sizeof tl) {
        printf("{\"error\": \"cannot read tlist.bin\"}\n");
        return 2;
    }
    memcpy(tl, t, sizeof tl);
    free(t);
    /* the guest image first (P3: the tracks' progress shadows live there, as in the game) */
    mem = (uint8_t *)VirtualAlloc(NULL, COMMIT, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    g_xbox_mem_offset = (ptrdiff_t)(uintptr_t)mem;
    load_xbe(argv[2]);
    /* 0. the manifests (modmanifest.c) and modfs's order / shared-id rule */
    for (int i = 5; i + 1 < argc; i += 2) {
        modrec *m;
        if (s_nm >= (int)BO3_ADMIT_MAX) {         /* 1.4.0: past the loader's cap */
            char w[96];
            snprintf(w, sizeof w, "more than %u mods: the loader ignores it", (unsigned)BO3_ADMIT_MAX);
            refusal("modfs", argv[i + 1], w);
            continue;
        }
        m = &s_m[s_nm++];
        char p[1400], err[300];
        m->root = atoi(argv[i] + 5);
        m->dir = argv[i + 1];
        snprintf(p, sizeof p, "%s\\mod.toml", m->dir);
        m->text = slurp(p, &m->len);
        if (!m->text)
            snprintf(m->problem, sizeof m->problem, "no mod.toml");
        else if (!bo3_manifest_parse(m->text, m->len, &m->man, err, sizeof err))
            snprintf(m->problem, sizeof m->problem, "mod.toml: %s", err);
#if BMPACK_MUT != 9
        else if (!bo3_manifest_platform_check(m->text, m->len, err, sizeof err)) {
            snprintf(m->problem, sizeof m->problem, "mod %.64s%s%.32s refused, the game starts without it: %.400s (this host: "
                     "Burnout Mashup platform %s)", m->man.id, m->man.version[0] ? " " : "", m->man.version, err,
                     bo3_manifest_platform_version());
            m->gate = 1;
        }
#endif
        else
            m->usable = 1;
    }
    for (int i = 0; i < s_nm; i++)
        for (int j = i + 1; j < s_nm; j++)
            if (s_m[i].man.id[0] && !strcmp(s_m[i].man.id, s_m[j].man.id)) {
                if (s_m[i].usable)
                    snprintf(s_m[i].problem, sizeof s_m[i].problem, "id %.64s is also used by %.200s", s_m[i].man.id, s_m[j].dir);
                if (s_m[j].usable)
                    snprintf(s_m[j].problem, sizeof s_m[j].problem, "id %.64s is also used by %.200s", s_m[j].man.id, s_m[i].dir);
                s_m[i].usable = s_m[j].usable = 0;
            }
    for (int i = 0; i < s_nm; i++) {
        s_ord[i] = &s_m[i];
        if (!s_m[i].usable)
            refusal(s_m[i].gate ? "platform" : "modfs", s_m[i].man.id[0] ? s_m[i].man.id : s_m[i].dir, s_m[i].problem);
    }
    qsort(s_ord, (size_t)s_nm, sizeof s_ord[0], by_root_then_id);
    /* 1.3: the dependency order (bm_admit.c order_cb: every listed mod, the usable mods' mod.toml) */
#if BMPACK_MUT != 13
    {
        static bo3_admit_mod all[MAXM];
        static int perm[MAXM];
        static modrec *tmp[MAXM];
        for (int i = 0; i < s_nm; i++) {
            all[i].id = s_ord[i]->man.id[0] ? s_ord[i]->man.id : NULL;
            all[i].version = s_ord[i]->man.version;
            all[i].folder = s_ord[i]->dir;
            all[i].text = s_ord[i]->usable ? s_ord[i]->text : NULL;
            all[i].n = s_ord[i]->usable ? s_ord[i]->len : 0;
        }
        s_moved = bo3_admit_order(all, s_nm, perm);
        if (s_moved > 0) {
            for (int i = 0; i < s_nm; i++)
                tmp[i] = s_ord[perm[i]];
            memcpy(s_ord, tmp, (size_t)s_nm * sizeof s_ord[0]);
        }
    }
#endif
    /* P3: the two-phase admission over the usable mods in the mod list's order (modfs.c list_mods) */
    {
        static bo3_admit_mod in[BO3_ADMIT_MAX];
        static bo3_admit_known kn[MAXM];
        int nk = 0;
        for (int i = 0; i < s_nm; i++)            /* 1.3: the listed mods that take no part (named in a dependant's reason) */
            if (!s_ord[i]->usable && s_ord[i]->man.id[0]) {
                kn[nk].id = s_ord[i]->man.id;
                kn[nk].version = s_ord[i]->man.version;
                kn[nk].folder = s_ord[i]->dir;
                kn[nk++].state = s_ord[i]->problem;
            }
        for (int i = 0; i < s_nm && nadm < (int)BO3_ADMIT_MAX; i++)
            if (s_ord[i]->usable) {
                in[nadm].id = s_ord[i]->man.id;
                in[nadm].version = s_ord[i]->man.version;
                in[nadm].folder = s_ord[i]->dir;
                in[nadm].text = s_ord[i]->text;
                in[nadm].n = s_ord[i]->len;
                amap[nadm++] = i;
            }
        ares = (bo3_admit_res *)calloc((size_t)(nadm ? nadm : 1), sizeof *ares);
#if BMPACK_MUT != 11
        if (nadm && ares && bo3_admit_run_deps(in, nadm, kn, nk, ares) < 0) {
            printf("{\"error\": \"the admission ran out of memory\"}\n");
            return 2;
        }
#endif
        for (int j = 0; ares && j < nadm; j++) {
            modrec *m = s_ord[amap[j]];
            if (ares[j].refused) {
                m->usable = 0;
                m->admit = 1;
                if (ares[j].kind == BO3_AK_NEEDS_MOD || ares[j].kind == BO3_AK_MOD_CYCLE) {
                    m->needs = 1;
                    snprintf(m->need, sizeof m->need, "%s", ares[j].need);
                }
                snprintf(m->problem, sizeof m->problem, "mod %.64s%s%.32s (%.400s) refused, the game starts without it: %.699s",
                         m->man.id, m->man.version[0] ? " " : "", m->man.version, m->dir, ares[j].why);
                refusal("admission", m->man.id, m->problem);
            } else if (ares[j].gameplay) {
                snprintf(m->label, sizeof m->label, "%s", ares[j].label);
            }
        }
    }

    /* 1. regions (every usable mod), 2. tracks + names + progress shadows per mod */
    bo3_cc_regions_reset();
    bo3_rg_reset();
    bo3_cc_flags_reset();
    bo3_wt_reset();
    bo3_xe_reset();
    if (getenv("BMPACK_SAVE_DIR"))
        bo3_cc_set_save_dir(getenv("BMPACK_SAVE_DIR"));
    for (int i = 0; i < s_nm; i++)
        if (s_ord[i]->usable && !bo3_cc_regions_parse(s_ord[i]->text, s_ord[i]->len, why, sizeof why))
            refusal("regions", s_ord[i]->man.id, why);
    for (int i = 0; i < s_nm; i++) {
        bo3_cc_decl d;
        if (!s_ord[i]->usable)
            continue;
        if (!bo3_cc_parse(s_ord[i]->text, s_ord[i]->len, &d, why, sizeof why) ||
            (d.present && !bo3_cc_append(tl, &d, i, files_fn, NULL, why, sizeof why))) {
            refusal("tracks", s_ord[i]->man.id, why);
            continue;
        }
        for (uint32_t k = 0; k < d.n; k++) {
            uint32_t sva = halloc(BO3_CC_RECORD_SIZE, 16u);
            bo3_cc_decode(d.id[k], name);
            bo3_cc_progress_add(s_ord[i]->man.id, s_ord[i]->man.version, d.id[k], name, sva);
            bo3_rg_register(d.id[k]);
        }
        if (!bo3_nm_parse(s_ord[i]->text, s_ord[i]->len, why, sizeof why))
            refusal("names", s_ord[i]->man.id, why);
    }
    bo3_cc_progress_start();
    bo3_xe_set_store(bo3_cc_progress_store);
    /* 3. World Tour events: every mod's declaration (P3: their texts join the text table), the text table's install over
     * the language file, then W1's resolve on the guest image */
    {
        uint8_t *p = (uint8_t *)slurp(argv[3], &len), *s;
        size_t sl;
        if (!p || !(s = (uint8_t *)slurp(argv[4], &sl))) {
            printf("{\"error\": \"cannot read PrgData.bin / stagehed.bin\"}\n");
            return 2;
        }
        memcpy(mem + PRG, p, len);
        memcpy(mem + STG, s, sl);
        free(p);
        free(s);
        G32(0x4D41D4u) = STG;
        G32(0x4D1FE8u) = PRG;
#ifdef BMPACK_DEV_GENRELOC
        g_eax = g_esi = PRG;                         /* developer build: the loader's original routine (extracted) */
        g_esp = STACKTOP;
        g_ebp = g_seh_ebp = 0x03E00000u;
        g_esp -= 4;
        G32(g_esp) = 0x00DEAD00u;
        ck_sub_00159710();
        memset(mem + STACKTOP - 0x100u, 0, 0x100u);  /* its scratch stack: not part of the relocated image */
#else
        prg_relocate(PRG);                           /* the loader's relocation, re-implemented (no generated code) */
#endif
        {
            uint32_t groups = G32(PRG + 4);
            if ((int32_t)G32(groups + 4) >= 7)       /* the loader's 7 -> 6 cut (loc_00016183) */
                G32(groups + 4) -= 1;
        }
    }
#if defined(BMPACK_WT4) && BMPACK_MUT != 14
    /* bmpack 1.3.3: [bmashup.world_tour] of every usable mod through the host's own reader, before the events (the game:
     * bo3_wt4_game_declare before the events' declarations), so the events' resolve knows a declared 4th-region location */
    bo3_wt4_reset();
    bo3_wt4_set_alloc(halloc);
    for (int i = 0; i < s_nm; i++)
        if (s_ord[i]->usable && !bo3_wt4_parse(s_ord[i]->man.id, s_ord[i]->text, s_ord[i]->len, why, sizeof why))
            refusal("world_tour", s_ord[i]->man.id, why);
#endif
    bo3_wt_set_alloc(halloc);
    bo3_wt_set_fail(on_wt_fail);
    for (int i = 0; i < s_nm; i++)
        if (s_ord[i]->usable && !bo3_wt_parse(s_ord[i]->man.id, s_ord[i]->man.version, s_ord[i]->text, s_ord[i]->len, why, sizeof why))
            refusal("events", s_ord[i]->man.id, why);
    if (getenv("BMPACK_LANG")) {                     /* the language file, relocated as sub_00020930 does */
        size_t ll;
        uint8_t *lb = (uint8_t *)slurp(getenv("BMPACK_LANG"), &ll);
        if (lb && ll < 0x100000u) {
            static const bo3_nm_guest ng = {n_rd32, n_wr32, n_wr16, n_alloc, NULL};
            uint32_t cnt;
            memcpy(mem + LANG, lb, ll);
            G32(LANG + 0xCu) += LANG;
            cnt = G32(LANG + 8u);
            for (uint32_t k = 0; k < cnt && k < 0x10000u; k++)
                if (G32(G32(LANG + 0xCu) + 4u * k))
                    G32(G32(LANG + 0xCu) + 4u * k) += LANG;
            G32(0x4D532Cu) = LANG;
            bo3_nm_set_guest(&ng);
            bo3_nm_gen_table_ready();
        }
        free(lb);
    }
    if (bo3_wt_count()) {
        if (setjmp(s_jb) == 0)
            bo3_wt_gen_prg_loaded();
        else {
            char w[900];
            snprintf(w, sizeof w, "%s (the game stops with exit %d)", s_wt_why, s_wt_code);
            refusal("events-resolve", "", w);
        }
    }
    /* 4. per event: W2 / W3 / W7, the stage record (W5) and the Gamedata record (W8) a launch would read */
    for (uint32_t i = 0; bo3_wt_installed() && i < bo3_wt_count(); i++) {
        uint32_t ev = bo3_wt_event_va_at(i), race = G32(ev + 0x34), st;
        const char *key = bo3_wt_key_at(i);
        ui_event(i);
        s_wt_code = 0;
        if (setjmp(s_jb) == 0) {
            st = bo3_wt_gen_stage(race);
            if (!st)
                refusal("events-stage", key, "no stage record (W5 returned none)");
        } else {
            refusal("events-stage", key, s_wt_why);
        }
        {   /* the track's Gamedata.bgd header (0x800 bytes) from the mod that adds the track */
            char tr[13], p[1400];
            uint64_t tid;
            uint8_t *h = NULL;
            size_t hl = 0;
            memcpy(&tid, mem + race, 8);
            bo3_cc_decode(tid, tr);
            for (int m = 0; m < s_nm && !h; m++) {
                if (!s_ord[m]->usable)
                    continue;
                snprintf(p, sizeof p, "%s\\files\\Tracks\\%c%c\\%c%c_%c%c\\Gamedata.bgd", s_ord[m]->dir, tr[0], tr[1], tr[3], tr[4],
                         tr[6], tr[7]);
                h = (uint8_t *)slurp(p, &hl);
            }
            if (!h || hl < 0x800) {
                refusal("events-gamedata", key, "the track's Gamedata.bgd is not in any mod of the set");
            } else {
                uint64_t id = bo3_wt_race_id_at(i);
                uint32_t n = 0, off = 0, found = 0;
                memcpy(mem + GDH, h, 0x800);
                memcpy(&n, h + 0x260, 4);
                for (uint32_t k = 0; k < n && k < 50u; k++) {
                    uint64_t v;
                    memcpy(&v, h + 8 + 8 * k, 8);
                    if (v == id) {
                        memcpy(&off, h + 0x198 + 4 * k, 4);
                        found = 1;
                    }
                }
                s_wt_code = 0;
                if (!found) {
                    if (setjmp(s_jb) == 0) {
                        off = bo3_wt_gen_gd_key(GDH, (uint32_t)id, (uint32_t)(id >> 32), 0);
                        s_gd_alias[i] = bo3_wt_gd_alias();
                    } else {
                        refusal("events-gamedata", key, s_wt_why);
                    }
                }
                s_gd_off[i] = off;
            }
            free(h);
        }
    }

    /* the report */
    memcpy(&ntl, tl + 4, 4);
    printf("{\"mods\": [");
    for (int i = 0; i < s_nm; i++) {
        printf("%s{\"order\": %d, \"root\": %d, \"dir\": ", i ? ", " : "", i, s_ord[i]->root);
        jstr(s_ord[i]->dir);
        printf(", \"id\": ");
        jstr(s_ord[i]->man.id);
        printf(", \"version\": ");
        jstr(s_ord[i]->man.version);
        printf(", \"name\": ");
        jstr(s_ord[i]->man.name);
        printf(", \"usable\": %d, \"platform_refused\": %d, \"admission_refused\": %d, \"needs\": ", s_ord[i]->usable,
               s_ord[i]->gate, s_ord[i]->admit);
        jstr(s_ord[i]->needs ? s_ord[i]->need : "");
        printf(", \"label\": ");
        jstr(s_ord[i]->label);
        printf("}");
    }
    printf("], \"admission\": [");
    for (int j = 0; ares && j < nadm; j++) {
        printf("%s{\"id\": ", j ? ", " : "");
        jstr(s_ord[amap[j]]->man.id);
        printf(", \"refused\": %d, \"kind\": ", ares[j].refused);
        jstr(ares[j].refused ? bo3_admit_kind_name(ares[j].kind) : "");
        printf(", \"key\": ");
        jstr(ares[j].key);
        printf(", \"other\": ");
        jstr(ares[j].refused && ares[j].other >= 0 ? s_ord[amap[ares[j].other]]->man.id : "");
        printf(", \"clashes\": %d, \"why\": ", ares[j].nclash);
        jstr(ares[j].why);
        printf(", \"undecided\": %u, \"tables\": %u, \"label\": ", ares[j].undecided, ares[j].tables);
        jstr(ares[j].label);
        printf(", \"page\": ");
        jstr(ares[j].page);
        printf("}");
    }
    printf("], \"dependency_moved\": %d, \"tlist_count\": %u, \"added_tracks\": [", s_moved, (unsigned)ntl);
    for (uint32_t i = BO3_CC_RETAIL; i < ntl && i < BO3_CC_CAP; i++) {
        uint64_t v;
        const char *s;
        memcpy(&v, tl + BO3_CC_OFF_ID + 8u * i, 8);
        bo3_cc_decode(v, name);
        printf("%s{\"entry\": %u, \"id\": ", i > BO3_CC_RETAIL ? ", " : "", (unsigned)i);
        jstr(name);
        printf(", \"region\": %d, \"p2p\": %u, \"name\": ", bo3_rg_region_of(v), (unsigned)bo3_cc_flag(tl, i, 0));
        s = bo3_nm_get(v, BO3_NM_NAME);
        if (s) jstr(s); else printf("null");
        printf(", \"upper\": ");
        s = bo3_nm_get(v, BO3_NM_UPPER);
        if (s) jstr(s); else printf("null");
        printf(", \"location\": ");
        s = bo3_nm_get(v, BO3_NM_LOCATION);
        if (s) jstr(s); else printf("null");
        printf("}");
    }
    printf("], \"regions\": [");
    for (uint32_t k = 0; k < bo3_cc_region_count(); k++) {
        const bo3_cc_region *r = bo3_cc_region_at(k);
        char l[2] = {r->letter, 0};
        printf("%s{\"letter\": ", k ? ", " : "");
        jstr(l);
        printf(", \"code\": %u, \"text\": ", (unsigned)(BO3_RG4_CODE0 + k));
        jstr(r->text);
        printf(", \"dj\": %u}", (unsigned)r->dj);
    }
    printf("], \"events\": [");
    for (uint32_t i = 0; bo3_wt_installed() && i < bo3_wt_count(); i++) {
        char id[13], loc[13], rt[200], ht[200];
        uint32_t rank = 0, region, value = 0;
        int retail;
        uint64_t lv = 0;
        static const uint32_t base[3] = {0, 6, 0xE}, nl[3] = {6, 8, 4};
        snprintf(loc, sizeof loc, "%s", bo3_wt_location_at(i));
        region = !strncmp(loc, "US", 2) ? 0 : !strncmp(loc, "EU", 2) ? 1 : 2;
        bo3_cc_encode(loc, &lv);
        while (value < nl[region] && memcmp(mem + 0x39E798u + 8 * (base[region] + value), &lv, 8))
            value++;
        retail = bo3_wt_location_events(region, value);
        for (uint32_t j = 0; j < i; j++)
            rank += !strcmp(bo3_wt_location_at(j), loc);
        bo3_cc_decode(bo3_wt_race_id_at(i), id);
        printf("%s{\"key\": ", i ? ", " : "");
        jstr(bo3_wt_key_at(i));
        printf(", \"location\": ");
        jstr(loc);
        {
            char tr[13];
            uint64_t tid;
            memcpy(&tid, mem + G32(bo3_wt_event_va_at(i) + 0x34), 8);
            bo3_cc_decode(tid, tr);
            printf(", \"track\": ");
            jstr(tr);
        }
        printf(", \"race_id\": ");
        jstr(id);
        printf(", \"retail_rows\": %d, \"row\": %d, \"gamedata_record\": %u, \"gamedata_alias\": %u", retail, retail + (int)rank,
               (unsigned)s_gd_off[i], (unsigned)s_gd_alias[i]);
        printf(", \"name\": ");
        jstr(bo3_wt_name_at(i));
        printf(", \"help\": ");
        jstr(bo3_wt_help_at(i));
        text_of(s_row_id[i], rt, sizeof rt);
        text_of(s_help_id[i], ht, sizeof ht);
        printf(", \"row_text_id\": %u, \"row_text\": ", (unsigned)s_row_id[i]);
        jstr(s_row_id[i] ? rt : "");
        printf(", \"help_text_id\": %u, \"help_text\": ", (unsigned)s_help_id[i]);
        jstr(s_help_id[i] ? ht : "");
        printf(", \"retail_row_help_unchanged\": %d}", s_ui_ok[i]);
    }
    printf("], \"refusals\": [");
    {
        char *p = s_refs;
        int first = 1;
        while (p < s_refs + s_refs_n) {
            char *e = strchr(p, '\x1e'), *a = strchr(p, '\x1f'), *b;
            if (!e || !a)
                break;
            *e = 0;
            *a = 0;
            b = strchr(a + 1, '\x1f');
            if (!b)
                break;
            *b = 0;
            printf("%s{\"service\": ", first ? "" : ", ");
            jstr(p);
            printf(", \"mod\": ");
            jstr(a + 1);
            printf(", \"why\": ");
            jstr(b + 1);
            printf("}");
            first = 0;
            p = e + 1;
        }
    }
    printf("], \"guest_fnv64\": \"%016llx\", \"tlist_fnv64\": \"%016llx\", \"heap_used\": %u, \"guest_refusals\": %u, \"ok\": %s}\n",
           (unsigned long long)fnv64(mem, COMMIT), (unsigned long long)fnv64(tl, sizeof tl), (unsigned)(s_heap - HEAP0),
           (unsigned)bo3_guest_refusals(), s_nref ? "false" : "true");
    fflush(stdout);
    return s_nref ? 1 : 0;
}
