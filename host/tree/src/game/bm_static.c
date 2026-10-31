/* Burnout Mashup private engine extension (G8-L9 EXPERIMENTAL; G8-G7: strict truncation, validated guest access): see
 * bm_static.h. MUT=n (test builds only) compiles one deliberate defect for the negative controls. */
#include "bm_static.h"

#include <string.h>

#ifndef MUT
#define MUT 0
#endif

_Static_assert(BO3_ST_MAX == 0x20C4000u, "the derived ceiling (STATIC_ANALYSIS.md s5)");
_Static_assert(BO3_ST_DESC_L1 == 0x003F9CC4u + 16u * 23u && BO3_ST_DESC_L2 == 0x003F9CC4u + 16u * 73u &&
               BO3_ST_DESC_L0 == 0x003F9CC4u + 16u * 147u, "descriptor indices 23 / 73 / 147");

bo3_static g_bo3_st;

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

void bo3_st_configure(bo3_static *s, bo3_st_guest_fn guest, bo3_st_alloc_fn alloc, bo3_st_build_fn check, bo3_st_fail_fn fail,
                      void *user, FILE *log)
{
    if (!s || s->configured)
        return;
    s->guest = guest;
    s->alloc = alloc;
    s->build_check = check;
    s->fail = fail;
    s->user = user;
    s->log = log;
    s->l1_bytes = BO3_ST_L1_GAME;
    s->l2_bytes = BO3_ST_L2_GAME;
    s->configured = guest && alloc && check && fail;
}

int bo3_st_set_bytes(bo3_static *s, uint32_t bytes)
{
    if (!s)
        return BO3_ST_BAD_ARG;
    if (s->state != BO3_ST_ST_PLANNED)
        return BO3_ST_ALREADY;
    if (bytes == 0) {
        s->bytes = 0;
        return BO3_ST_OK;
    }
    if ((bytes % BO3_ST_PAGE) || bytes <= BO3_ST_L2_GAME || bytes > BO3_ST_MAX)
        return BO3_ST_BAD_ARG;
    s->bytes = bytes;
    return BO3_ST_OK;
}

int bo3_st_validate(const bo3_static *s, uint32_t *base)
{
    const uint8_t *d1, *d2;
    uint32_t b;

    if (!s || !s->guest)
        return BO3_ST_UNMAPPED;
    d1 = s->guest(s->user, BO3_ST_DESC_L1, 16);
    d2 = s->guest(s->user, BO3_ST_DESC_L2, 16);
    if (!d1 || !d2)
        return BO3_ST_UNMAPPED;
    b = get32(d1 + 0xC);
#if MUT != 4
    if (!b || (b % BO3_ST_PAGE) || get32(d2 + 0xC) != b ||
        get32(d1) != 0 || get32(d1 + 4) != 1u || get32(d1 + 8) != BO3_ST_L1_GAME ||
        get32(d2) != 0 || get32(d2 + 4) != 2u || get32(d2 + 8) != BO3_ST_L2_GAME)
        return BO3_ST_MISMATCH;
#endif
    if (base)
        *base = b;
    return BO3_ST_OK;
}

int bo3_st_apply(bo3_static *s)
{
    uint32_t base = 0, va = 0, n = 0;
    uint8_t *d1, *d2;
    int rc;

    if (!s || !s->configured)
        return BO3_ST_BAD_ARG;
    if (s->state != BO3_ST_ST_PLANNED)
        return BO3_ST_ALREADY;
    if (!s->bytes) {
        s->state = BO3_ST_ST_GAME;
        s->apply_result = BO3_ST_OK;
        if (s->log)
            fprintf(s->log, "[STATIC] track pools: the game's (one view 0x%X, split screen 0x%X); loads are checked for "
                    "truncation\n", (unsigned)BO3_ST_L1_GAME, (unsigned)BO3_ST_L2_GAME);
        return BO3_ST_OK;
    }
    if (!s->build_check(s->user))
        rc = BO3_ST_UNSUPPORTED;
    else if ((rc = bo3_st_validate(s, &base)) != BO3_ST_OK)
        ;
    else if (!(va = s->alloc(s->user, s->bytes, BO3_ST_PAGE)) || (va % BO3_ST_PAGE))
        rc = BO3_ST_NO_MEMORY;
    else if (!(d1 = s->guest(s->user, BO3_ST_DESC_L1, 16)) || !(d2 = s->guest(s->user, BO3_ST_DESC_L2, 16)))
        rc = BO3_ST_UNMAPPED;
    else {
        if (s->bytes > BO3_ST_L1_GAME) {
            put32(d1 + 8, s->bytes);
#if MUT != 3
            put32(d1 + 0xC, va);
#endif
            s->l1_bytes = s->bytes;
            n++;
        }
#if MUT == 5
        if (s->bytes > BO3_ST_L1_GAME) {        /* defect: split screen only follows when one view grows */
#else
        if (s->bytes > BO3_ST_L2_GAME) {
#endif
            put32(d2 + 8, s->bytes);
            put32(d2 + 0xC, va);
            s->l2_bytes = s->bytes;
            n++;
        }
        rc = BO3_ST_OK;
    }
    s->apply_result = rc;
    s->base_game = base;
    s->state = rc == BO3_ST_OK ? BO3_ST_ST_EXPANDED : BO3_ST_ST_FAILED;
    if (rc == BO3_ST_OK)
        s->region_va = va;
    if (s->log) {
        if (rc == BO3_ST_OK)
            fprintf(s->log, "[STATIC] track pools EXPANDED: one region of 0x%X at 0x%08X; one view 0x%X%s, split screen 0x%X%s "
                    "(the game's were at 0x%08X)\n", (unsigned)s->bytes, (unsigned)va, (unsigned)s->l1_bytes,
                    s->l1_bytes == BO3_ST_L1_GAME ? " (the game's)" : "", (unsigned)s->l2_bytes,
                    s->l2_bytes == BO3_ST_L2_GAME ? " (the game's)" : "", (unsigned)base);
        else
            fprintf(s->log, "[STATIC] track pools NOT expanded to 0x%X: %s; the game's pools stay (loads are checked for "
                    "truncation)\n", (unsigned)s->bytes,
                    rc == BO3_ST_UNSUPPORTED ? "unsupported game build" :
                    rc == BO3_ST_MISMATCH ? "descriptors 23 / 73 are not the expected table" :
                    rc == BO3_ST_NO_MEMORY ? "the contiguous allocation was refused" : "the descriptor table is unmapped");
    }
    (void)n;
    return rc;
}

/* The taken STATIC descriptor of the current layout whose pointer is buf: 1 and its capacity, or 0. */
static int capacity(const bo3_static *s, uint32_t buf, uint32_t *layout, uint32_t *cap)
{
    const uint8_t *l = s->guest(s->user, BO3_ST_LAYOUT_VA, 4), *d;
    uint32_t va;

    if (!l)
        return 0;
    *layout = get32(l);
    va = *layout == 0 ? BO3_ST_DESC_L0 : *layout == 2 ? BO3_ST_DESC_L2 : BO3_ST_DESC_L1;   /* as sub_0019AE10 */
    d = s->guest(s->user, va, 16);
#if MUT == 6
    if (!d || get32(d + 0xC) != buf)            /* defect: a free descriptor counts */
#else
    if (!d || get32(d + 0xC) != buf || get32(d) != BO3_ST_TAKEN)
#endif
        return 0;
    *cap = get32(d + 8);
    return 1;
}

int bo3_st_check(bo3_static *s, uint32_t buf)
{
    uint32_t layout = 0, cap = 0, declared, def;
    const uint8_t *h;

    if (!s || !s->guest)
        return BO3_ST_UNKNOWN;
    s->loads++;
    h = s->guest(s->user, buf, BO3_ST_HDR_MIN);
#if MUT == 2
    cap = BO3_ST_L1_GAME;                       /* defect: the game's size, not the pool the load used */
    (void)capacity;
    if (h) { const uint8_t *l = s->guest(s->user, BO3_ST_LAYOUT_VA, 4); layout = l ? get32(l) : 1; }
    if (!h) {
#else
    if (!h || !capacity(s, buf, &layout, &cap)) {
#endif
        s->unknown++;
        if (s->log)
            fprintf(s->log, "[STATIC] static load into 0x%08X: no taken STATIC descriptor of this layout has that pointer; NOT "
                    "CHECKED\n", (unsigned)buf);
        return BO3_ST_UNKNOWN;
    }
    declared = get32(h + 4);
    if (declared < BO3_ST_HDR_MIN) {
        s->unknown++;
        if (s->log)
            fprintf(s->log, "[STATIC] static load into 0x%08X: header size field 0x%X implausible; NOT CHECKED\n", (unsigned)buf,
                    (unsigned)declared);
        return BO3_ST_UNKNOWN;
    }
    s->last_declared = declared;
    s->last_capacity = cap;
    def = layout == 0 ? BO3_ST_L0_GAME : layout == 2 ? BO3_ST_L2_GAME : BO3_ST_L1_GAME;
#if MUT == 32
    if (declared <= cap && !(s->strict && layout == 2)) {   /* defect: strict also stops a complete split-screen load */
#elif MUT == 1
    if (declared < cap) {                       /* defect: an exact fit counts as truncated */
#else
    if (declared <= cap) {
#endif
        s->complete++;
        if (declared > s->largest)
            s->largest = declared;
        if (declared > def)
            s->beyond++;
        if (s->log)
            fprintf(s->log, "[STATIC] static.dat complete: 0x%X bytes in the pool's 0x%X (layout %u)%s\n", (unsigned)declared,
                    (unsigned)cap, (unsigned)layout, declared > def ? "; beyond the game's pool" : "");
        if (s->log && declared > def)
            fprintf(s->log, "[STATIC] 0x%X bytes were loaded past the game's 0x%X\n", (unsigned)(declared - def), (unsigned)def);
        return BO3_ST_COMPLETE;
    }
    s->truncated++;
#if MUT == 7
    if (layout != 0xFFFFFFFFu) {                /* defect: one view truncation diagnosed only, never stopped */
#elif MUT == 31
    if (layout == 2) {                          /* defect: strict ignored */
#else
    if (layout == 2 && !s->strict) {
#endif
        if (s->log)
            fprintf(s->log, "[STATIC] TRUNCATED: static.dat declares 0x%X bytes, the split-screen pool holds 0x%X: 0x%X bytes "
                    "were NOT loaded; the game goes on as it would (split-screen truncation is diagnosed, not stopped)\n",
                    (unsigned)declared, (unsigned)cap, (unsigned)(declared - cap));
        return BO3_ST_TRUNCATED;
    }
    if (layout == 2) {                          /* only reached with strict on */
#if MUT != 36
        s->strict_stops++;
#endif
        if (s->log)
            fprintf(s->log, "[STATIC] FATAL: static.dat declares 0x%X bytes, the split-screen pool (layout 2) holds 0x%X: the load "
                    "was truncated by 0x%X bytes; the game stops before using it (strict; set by %s)\n", (unsigned)declared,
                    (unsigned)cap, (unsigned)(declared - cap), s->strict_source[0] ? s->strict_source : "host");
    } else if (s->log)
        fprintf(s->log, "[STATIC] FATAL: static.dat declares 0x%X bytes, the pool (layout %u) holds 0x%X: the load was "
                "truncated by 0x%X bytes; the game stops before using it\n", (unsigned)declared, (unsigned)layout, (unsigned)cap,
                (unsigned)(declared - cap));
    if (s->fail)
        s->fail(s->user, layout, declared, cap, buf);
    return BO3_ST_FATAL;
}

/* G8-G7: strict truncation */
static void copy_source(char *dst, size_t n, const char *src)
{
    size_t i = 0;

    for (; src[i] && i + 4 < n; i++)            /* printable ASCII only; the rest shown as '?' */
        dst[i] = src[i] >= 0x20 && src[i] < 0x7F ? src[i] : '?';
    if (src[i]) {
        memcpy(dst + i, "...", 3);
        i += 3;
    }
    dst[i] = 0;
}

int bo3_st_set_strict(bo3_static *s, int on, const char *source)
{
    char src[sizeof s->strict_source];

    if (!s)
        return BO3_ST_BAD_ARG;
    copy_source(src, sizeof src, source ? source : "host");
#if MUT != 34
    if (s->state != BO3_ST_ST_PLANNED) {
        if (s->log)
            fprintf(s->log, "[STATIC] strict truncation %s (%s) refused: the track pools are already set up; strict stays %s\n",
                    on ? "on" : "off", src, s->strict ? "on" : "off");
        return BO3_ST_ALREADY;
    }
#endif
    on = on ? 1 : 0;
    memcpy(s->strict_source, src, sizeof src);
    if (on && !s->strict_logged) {
        s->strict_logged = 1;
        if (s->log)
            fprintf(s->log, "[STATIC] strict truncation: on (%s): a truncated split-screen static.dat stops the game as a "
                    "one-view one does\n", src);
    } else if (!on && s->strict && s->log)
        fprintf(s->log, "[STATIC] strict truncation: off (%s)\n", src);
    s->strict = on;
    return BO3_ST_OK;
}

int bo3_st_strict_from_env(bo3_static *s, const char *value)
{
    char v[28];

    if (!s)
        return 0;
    if (!value) {
        if (s->log)
            fprintf(s->log, "[STATIC] strict truncation: off (default; " BO3_ST_STRICT_ENV " not set)\n");
        return s->strict;
    }
#if MUT == 35
    if (strcmp(value, "0")) {                   /* defect: any value but "0" turns it on */
#else
    if (!strcmp(value, "1")) {
#endif
        bo3_st_set_strict(s, 1, BO3_ST_STRICT_ENV "=1");
        return s->strict;
    }
    copy_source(v, sizeof v, value);
    if (s->log) {
        if (!strcmp(value, "0"))
            fprintf(s->log, "[STATIC] strict truncation: off (" BO3_ST_STRICT_ENV "=0)\n");
        else
            fprintf(s->log, "[STATIC] " BO3_ST_STRICT_ENV "=\"%s\" not recognised (only 1 turns it on): strict truncation: %s\n",
                    v, s->strict ? "on" : "off");
    }
    return s->strict;
}

#if defined(BO3_STATIC_GAME) || defined(BO3_ST_GUEST_TEST)
#include "bm_guest.h"
extern ptrdiff_t g_xbox_mem_offset;                 /* recomp_types.h (the game build) / the test */

/* G8-G7: every range through bm_guest.c's check of the runtime's mappings (G8-E4); no fixed windows. */
uint8_t *bo3_st_mapped_guest(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!g_xbox_mem_offset)
        return NULL;
#if MUT == 33
    {                                           /* defect: L9's fixed windows (an unmapped address is accepted) */
        uint64_t end = (uint64_t)va + size;
        if ((va >= 0x00010000u && end <= 0x04000000u) || (va >= 0x80000000u && end <= 0x84000000u))
            return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
    }
#endif
#if MUT == 37
    (void)size;
    if (bo3_guest_window(va, 1) == BO3_GUEST_NONE)   /* defect: only the first byte is checked */
#else
    if (bo3_guest_window(va, size) == BO3_GUEST_NONE)
#endif
        return NULL;
    return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}
#endif

#ifdef BO3_STATIC_GAME   /* the game build (CMake); tests use bo3_st_configure with stand-ins */
#include <stdlib.h>

#include "recomp_types.h"
#include "kernel/xbox_memory_layout.h"

extern void bo3_fatal(const char *title, const char *fmt, ...);
extern void xbox_crash_log_flush(unsigned max_ms);     /* xboxrecomp kernel/xbox_crash.h: drain the stdio tee */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
#endif

static const struct { uint32_t va, word; } s_sig[] = {   /* the retail NTSC-U default.xbe, as bm_lanes.c / bm_unitslots.c */
    { 0x003B11A0u, 0x0018C470u },
    { 0x003B11A4u, 0x0018C510u },
    { 0x003A9ACCu, 0x00019FE0u },
    { 0x003A9AD0u, 0x0001A000u },
};

static uint32_t game_alloc(void *user, uint32_t size, uint32_t align)
{
    uint32_t va;
    (void)user;
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    va = xbox_ContiguousAllocHigh(size, align);   /* MEM256: expansions live in the high zone (64 MB .. 256 MB) */
#else
    va = xbox_ContiguousAllocEx(size, align, 0, 0xFFFFFFFFu);
#endif
    if (!va)
        fprintf(stderr, "[STATIC] the contiguous window refused 0x%X bytes (in use 0x%X, high-water 0x%X)\n", (unsigned)size,
                (unsigned)xbox_ContiguousInUseBytes(), (unsigned)xbox_ContiguousAllocatedBytes());
    return va;
}

static int game_build_ok(void *user)
{
    (void)user;
    if (!g_xbox_mem_offset)
        return 0;
    for (size_t k = 0; k < sizeof s_sig / sizeof s_sig[0]; k++) {
        uint32_t w = 0;
        if (!bo3_guest_rd32(s_sig[k].va, &w) || w != s_sig[k].word)   /* G8-G7: through the mapping check */
            return 0;
    }
    return 1;
}

static void game_fail(void *user, uint32_t layout, uint32_t declared, uint32_t cap, uint32_t buf)
{
    (void)user;
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: track data too large",
              "The track's static data (static.dat) is 0x%X bytes, but the game's track pool (layout %u, at 0x%08X) holds 0x%X. "
              "It was loaded only in part, so the game stops here instead of using it. Remove or fix the track mod, or add a "
              "plugin that asks bmashup.streaming for a larger STATIC pool.%s",
              (unsigned)declared, (unsigned)layout, (unsigned)buf, (unsigned)cap,
              layout == 2 ? " (Split screen stops here because strict truncation is on: " BO3_ST_STRICT_ENV ".)" : "");
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(90);
}

void bo3_st_game_init(void)
{
    static int done;

    if (done)
        return;
    done = 1;
    bo3_st_configure(&g_bo3_st, bo3_st_mapped_guest, game_alloc, game_build_ok, game_fail, NULL, stderr);
    bo3_st_strict_from_env(&g_bo3_st, getenv(BO3_ST_STRICT_ENV));   /* G8-G7: read once, before the plugins start */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    {
        extern void bm_memwin_init(void);
        bm_memwin_init();       /* MEM256 layer 0: a refused title allocation stops the game (bm_memwin.c) */
    }
#endif
}

/* bo3_static_gen.h */
void bo3_gds_apply(void);   /* GP-MEGA1: the GAMEDATA slot expansion (bm_gdslot.c), the same moment */
void bo3_st_gen_apply(void)
{
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    extern void bm_memwin_gate(void);
    bm_memwin_gate();           /* MEM256 layer 0: the budget gate, before the first expansion is allocated */
#endif
    bo3_st_apply(&g_bo3_st);
    bo3_gds_apply();
}

void bo3_st_gen_check(uint32_t buf)
{
    bo3_st_check(&g_bo3_st, buf);
}
#endif
