/* Burnout Mashup private engine extension (G8-L7 EXPERIMENTAL): see bm_unitslots.h. MUT=n (test builds only) compiles one
 * deliberate defect for the negative controls. */
#include "bm_unitslots.h"

#include <string.h>

#ifndef MUT
#define MUT 0
#endif

_Static_assert(BO3_US_DESC_VA + 16u * BO3_US_LOW1_FIRST == 0x003F9EE4u, "sub_0019DB30's layout-1 base");
_Static_assert(BO3_US_DESC_VA + 16u * 52u == 0x003FA004u, "descriptor 52 (GAMEDATA) follows the low slots");
_Static_assert(BO3_US_LOW_MAX % BO3_US_PAGE == 0 && BO3_US_LOW_RETAIL % BO3_US_PAGE == 0, "page sizes");
_Static_assert(BO3_US_FULL_MAX % BO3_US_PAGE == 0 && BO3_US_FULL_RETAIL % BO3_US_PAGE == 0 &&
               BO3_US_FULL_MAX > BO3_US_FULL_RETAIL, "full-detail page sizes (patch 131)");
_Static_assert(BO3_US_DESC_VA + 16u * BO3_US_FULL1_FIRST == 0x003F9E44u &&
               BO3_US_FULL1_FIRST + BO3_US_FULL1_N == BO3_US_LOW1_FIRST, "descriptors 24-33 end where the low slots start");

bo3_us g_bo3_us;

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

void bo3_us_configure(bo3_us *u, bo3_us_guest_fn guest, bo3_us_alloc_fn alloc, bo3_us_build_fn check, bo3_us_fail_fn fail,
                      void *user, FILE *log)
{
    if (!u || u->configured)
        return;
    u->guest = guest;
    u->alloc = alloc;
    u->build_check = check;
    u->fail = fail;
    u->user = user;
    u->log = log;
    u->configured = guest && alloc && check && fail;
}

int bo3_us_set_low_bytes(bo3_us *u, uint32_t bytes)
{
    if (!u)
        return BO3_US_BAD_ARG;
    if (u->state != BO3_US_ST_PLANNED)
        return BO3_US_ALREADY;              /* applied: slots may be taken at the size they have; fixed */
    if (bytes == 0 || bytes == BO3_US_LOW_RETAIL) {
        u->low_bytes = 0;
        return BO3_US_OK;
    }
    if ((bytes % BO3_US_PAGE) || bytes < BO3_US_LOW_RETAIL || bytes > BO3_US_LOW_MAX)
        return BO3_US_BAD_ARG;
    u->low_bytes = bytes;
    return BO3_US_OK;
}

int bo3_us_validate(const bo3_us *u, uint32_t *base)
{
    const uint8_t *d;
    uint32_t b;

    if (!u || !u->guest)
        return BO3_US_UNMAPPED;
    d = u->guest(u->user, BO3_US_DESC_VA + 16u * BO3_US_LOW1_FIRST, 16u * BO3_US_LOW1_N);
    if (!d)
        return BO3_US_UNMAPPED;
    b = get32(d + 0xC);
    if (!b || (b % BO3_US_PAGE))
        return BO3_US_MISMATCH;
    for (uint32_t i = 0; i < BO3_US_LOW1_N; i++) {
        const uint8_t *e = d + 16u * i;
#if MUT != 4
        if (get32(e) != 0 || get32(e + 4) != 1u || get32(e + 8) != BO3_US_LOW_RETAIL ||
            get32(e + 0xC) != b + BO3_US_LOW_RETAIL * i)
            return BO3_US_MISMATCH;
#else
        (void)e;                            /* defect: any table is taken for the retail one */
#endif
    }
    if (base)
        *base = b;
    return BO3_US_OK;
}

static int apply_low(bo3_us *u)
{
    uint32_t base = 0, va = 0, s;
    uint8_t *d;
    int rc;

    if (!u || !u->configured)
        return BO3_US_BAD_ARG;
    if (u->state != BO3_US_ST_PLANNED)
        return BO3_US_ALREADY;
    s = u->low_bytes;
    if (!s) {
        u->state = BO3_US_ST_RETAIL;
        u->apply_result = BO3_US_OK;
        if (u->log)
            fprintf(u->log, "[UNITSLOTS] low-detail unit slots: the game's (18 x 0x%X); unit reads are checked\n",
                    (unsigned)BO3_US_LOW_RETAIL);
        return BO3_US_OK;
    }
    if (!u->build_check(u->user))
        rc = BO3_US_UNSUPPORTED;
    else if ((rc = bo3_us_validate(u, &base)) != BO3_US_OK)
        ;
    else if (!(va = u->alloc(u->user, BO3_US_LOW1_N * s, BO3_US_PAGE)) || (va % BO3_US_PAGE))
        rc = BO3_US_NO_MEMORY;
    else if (!(d = u->guest(u->user, BO3_US_DESC_VA + 16u * BO3_US_LOW1_FIRST, 16u * BO3_US_LOW1_N)))
        rc = BO3_US_UNMAPPED;
    else {
        for (uint32_t i = 0; i < BO3_US_LOW1_N; i++) {
#if MUT != 3
            put32(d + 16u * i + 8u, s);
#endif
#if MUT == 5
            put32(d + 16u * i + 0xCu, va + BO3_US_LOW_RETAIL * i);     /* defect: the retail stride (slots overlap) */
#else
            put32(d + 16u * i + 0xCu, va + s * i);
#endif
        }
        rc = BO3_US_OK;
    }
    u->apply_result = rc;
    u->old_base = base;
    if (rc == BO3_US_OK) {
        u->state = BO3_US_ST_EXPANDED;
        u->region_va = va;
    } else {
        u->state = BO3_US_ST_FAILED;
    }
    if (u->log) {
        if (rc == BO3_US_OK)
            fprintf(u->log, "[UNITSLOTS] low-detail unit slots EXPANDED: 18 x 0x%X at 0x%08X (were 18 x 0x%X at 0x%08X; "
                    "layout 1 only)\n", (unsigned)s, (unsigned)va, (unsigned)BO3_US_LOW_RETAIL, (unsigned)base);
        else
            fprintf(u->log, "[UNITSLOTS] low-detail unit slots NOT expanded to 0x%X: %s; the game's 18 x 0x%X stay "
                    "(unit reads are checked)\n", (unsigned)s,
                    rc == BO3_US_UNSUPPORTED ? "unsupported game build" :
                    rc == BO3_US_MISMATCH ? "descriptors 34-51 are not the expected table" :
                    rc == BO3_US_NO_MEMORY ? "the contiguous allocation was refused" : "the descriptor table is unmapped",
                    (unsigned)BO3_US_LOW_RETAIL);
    }
    return rc;
}

/* ---------------- patch 131: the full-detail ring (descriptors 24-33) */
int bo3_us_set_full_bytes(bo3_us *u, uint32_t bytes)
{
    if (!u)
        return BO3_US_BAD_ARG;
    if (u->full_state != BO3_US_ST_PLANNED)
        return BO3_US_ALREADY;
    if (bytes == 0 || bytes == BO3_US_FULL_RETAIL) {
        u->full_bytes = 0;
        return BO3_US_OK;
    }
    if ((bytes % BO3_US_PAGE) || bytes < BO3_US_FULL_RETAIL || bytes > BO3_US_FULL_MAX)
        return BO3_US_BAD_ARG;
    u->full_bytes = bytes;
    return BO3_US_OK;
}

int bo3_us_validate_full(const bo3_us *u, uint32_t *base)
{
    const uint8_t *d;
    uint32_t b;

    if (!u || !u->guest)
        return BO3_US_UNMAPPED;
    d = u->guest(u->user, BO3_US_DESC_VA + 16u * BO3_US_FULL1_FIRST, 16u * BO3_US_FULL1_N);
    if (!d)
        return BO3_US_UNMAPPED;
    b = get32(d + 0xC);
    if (!b || (b % BO3_US_PAGE))
        return BO3_US_MISMATCH;
    for (uint32_t i = 0; i < BO3_US_FULL1_N; i++) {
        const uint8_t *e = d + 16u * i;
#if MUT != 7
        if (get32(e) != 0 || get32(e + 4) != 1u || get32(e + 8) != BO3_US_FULL_RETAIL ||
            get32(e + 0xC) != b + BO3_US_FULL_RETAIL * i)
            return BO3_US_MISMATCH;
#else
        (void)e;                            /* defect: any table is taken for the retail one */
#endif
    }
    if (base)
        *base = b;
    return BO3_US_OK;
}

static int apply_full(bo3_us *u)
{
    uint32_t base = 0, va = 0, s;
    uint8_t *d;
    int rc;

    if (u->full_state != BO3_US_ST_PLANNED)
        return BO3_US_ALREADY;
    s = u->full_bytes;
    if (!s) {
        u->full_state = BO3_US_ST_RETAIL;
        u->full_result = BO3_US_OK;
        if (u->log)
            fprintf(u->log, "[UNITSLOTS] full-detail unit slots: the game's (10 x 0x%X); unit reads are checked\n",
                    (unsigned)BO3_US_FULL_RETAIL);
        return BO3_US_OK;
    }
    if (!u->build_check(u->user))
        rc = BO3_US_UNSUPPORTED;
    else if ((rc = bo3_us_validate_full(u, &base)) != BO3_US_OK)
        ;
    else if (!(va = u->alloc(u->user, BO3_US_FULL1_N * s, BO3_US_PAGE)) || (va % BO3_US_PAGE))
        rc = BO3_US_NO_MEMORY;
    else if (!(d = u->guest(u->user, BO3_US_DESC_VA + 16u * BO3_US_FULL1_FIRST, 16u * BO3_US_FULL1_N)))
        rc = BO3_US_UNMAPPED;
    else {
        for (uint32_t i = 0; i < BO3_US_FULL1_N; i++) {
#if MUT != 8
            put32(d + 16u * i + 8u, s);
#endif
#if MUT == 9
            put32(d + 16u * i + 0xCu, va + BO3_US_FULL_RETAIL * i);    /* defect: the retail stride (slots overlap) */
#else
            put32(d + 16u * i + 0xCu, va + s * i);
#endif
        }
        rc = BO3_US_OK;
    }
    u->full_result = rc;
    u->full_old_base = base;
    if (rc == BO3_US_OK) {
        u->full_state = BO3_US_ST_EXPANDED;
        u->full_region_va = va;
    } else {
        u->full_state = BO3_US_ST_FAILED;
    }
    if (u->log) {
        if (rc == BO3_US_OK)
            fprintf(u->log, "[UNITSLOTS] full-detail unit slots EXPANDED: 10 x 0x%X at 0x%08X (were 10 x 0x%X at 0x%08X; "
                    "layout 1 only)\n", (unsigned)s, (unsigned)va, (unsigned)BO3_US_FULL_RETAIL, (unsigned)base);
        else
            fprintf(u->log, "[UNITSLOTS] full-detail unit slots NOT expanded to 0x%X: %s; the game's 10 x 0x%X stay "
                    "(unit reads are checked)\n", (unsigned)s,
                    rc == BO3_US_UNSUPPORTED ? "unsupported game build" :
                    rc == BO3_US_MISMATCH ? "descriptors 24-33 are not the expected table" :
                    rc == BO3_US_NO_MEMORY ? "the contiguous allocation was refused" : "the descriptor table is unmapped",
                    (unsigned)BO3_US_FULL_RETAIL);
    }
    return rc;
}

int bo3_us_apply(bo3_us *u)
{
    int rc;

    if (!u || !u->configured)
        return BO3_US_BAD_ARG;
    rc = apply_low(u);
#if MUT != 10
    (void)apply_full(u);                    /* independent of the low result; it keeps its own state */
#endif
    return rc;
}

static int scan(const bo3_us *u, uint32_t va, uint32_t n, uint32_t buf, uint32_t layout, uint32_t *cap, int found)
{
    const uint8_t *d = u->guest(u->user, va, 16u * n);

    if (!d)
        return found;
    for (uint32_t i = 0; i < n; i++) {
        const uint8_t *e = d + 16u * i;
        uint32_t owner = get32(e + 4);

        if (get32(e + 0xC) != buf)
            continue;
#if MUT != 6
        if (get32(e) != BO3_US_TAKEN || (owner != BO3_US_ANY_LAYOUT && owner != layout))
            continue;
#else
        (void)owner; (void)layout;          /* defect: free / other-layout descriptors count */
#endif
        if (!found || get32(e + 8) < *cap)
            *cap = get32(e + 8);            /* more than one: the smallest (never seen; conservative) */
        found = 1;
    }
    return found;
}

int bo3_us_capacity(const bo3_us *u, uint32_t buf, uint32_t *cap)
{
    const uint8_t *l;
    uint32_t layout;
    int found;

    if (!u || !u->guest || !cap || !buf)
        return 0;
    l = u->guest(u->user, BO3_US_LAYOUT_VA, 4);
    if (!l)
        return 0;
    layout = get32(l);
    found = scan(u, BO3_US_DESC_VA, BO3_US_DESC_N, buf, layout, cap, 0);
    return scan(u, BO3_US_EXTRA_VA, BO3_US_EXTRA_N, buf, layout, cap, found);
}

int bo3_us_check(bo3_us *u, int kind, uint32_t buf, uint32_t size)
{
    uint32_t cap = 0;
    int k = kind == BO3_US_FULL ? 1 : 0;
    const char *name = k ? "full-detail" : "low-detail";

    if (!u)
        return BO3_US_UNKNOWN;
    u->checks[k]++;
#if MUT == 2
    cap = k ? BO3_US_FULL_RETAIL : BO3_US_LOW_RETAIL;  /* defect: the retail size, not the slot's */
    if (!buf) {
#else
    if (!bo3_us_capacity(u, buf, &cap)) {
#endif
        if (u->unknown[k]++ < 4 && u->log)
            fprintf(u->log, "[UNITSLOTS] %s unit read of 0x%X bytes into 0x%08X: no taken slot descriptor has that "
                    "pointer; NOT CHECKED\n", name, (unsigned)size, (unsigned)buf);
        return BO3_US_UNKNOWN;
    }
#if MUT == 1
    if (size >= cap) {                      /* defect: an exact fit refused */
#else
    if (size > cap) {
#endif
        u->over[k]++;
        if (u->log)
            fprintf(u->log, "[UNITSLOTS] FATAL: a %s unit of 0x%X bytes does not fit its slot of 0x%X at 0x%08X; the read "
                    "is stopped\n", name, (unsigned)size, (unsigned)cap, (unsigned)buf);
        if (u->fail)
            u->fail(u->user, kind, buf, size, cap);
        return BO3_US_OVER;
    }
    if (size > u->max_size[k]) {            /* a new largest unit: a few lines per track */
        u->max_size[k] = size;
        u->max_cap[k] = cap;
        if (u->log)
            fprintf(u->log, "[UNITSLOTS] %s unit 0x%X bytes in a slot of 0x%X (largest so far)\n", name, (unsigned)size,
                    (unsigned)cap);
    }
    return BO3_US_FIT;
}

#ifdef BO3_UNITSLOTS_GAME   /* the game build (CMake); tests use bo3_us_configure with stand-ins */
#include <stdlib.h>

#include "recomp_types.h"
#include "kernel/xbox_memory_layout.h"

extern void bo3_fatal(const char *title, const char *fmt, ...);
extern void xbox_crash_log_flush(unsigned max_ms);     /* xboxrecomp kernel/xbox_crash.h: drain the stdio tee */

/* The retail NTSC-U default.xbe (title 0x4541005B): the .rdata words bm_lanes.c / bm_autopilot.c check. */
static const struct { uint32_t va, word; } s_sig[] = {
    { 0x003B11A0u, 0x0018C470u },
    { 0x003B11A4u, 0x0018C510u },
    { 0x003A9ACCu, 0x00019FE0u },
    { 0x003A9AD0u, 0x0001A000u },
};

static uint8_t *game_guest(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!g_xbox_mem_offset || va < 0x00010000u || va >= 0x04000000u || size > 0x04000000u - va)
        return NULL;
    return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}

#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
extern uint32_t xbox_ContiguousAllocHigh(uint32_t size, uint32_t alignment);   /* MEM256: the high zone */
#endif
static uint32_t game_alloc(void *user, uint32_t size, uint32_t align)
{
    (void)user;
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    return xbox_ContiguousAllocHigh(size, align);                 /* MEM256: the high zone */
#else
    return xbox_ContiguousAllocEx(size, align, 0, 0xFFFFFFFFu);   /* as XPhysicalAlloc: anywhere in the window */
#endif
}

static int game_build_ok(void *user)
{
    (void)user;
    if (!g_xbox_mem_offset)
        return 0;
    for (size_t k = 0; k < sizeof s_sig / sizeof s_sig[0]; k++)
        if (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + s_sig[k].va) != s_sig[k].word)
            return 0;
    return 1;
}

static void game_fail(void *user, int kind, uint32_t buf, uint32_t size, uint32_t cap)
{
    (void)user;
    fflush(stderr);
    xbox_crash_log_flush(1000);     /* fds 1 / 2 go through the runtime's tee; _Exit skips its atexit drain (G8-L6a D-L6a-1) */
    bo3_fatal("Takedawn: track unit too large",
              "A %s track unit of 0x%X bytes does not fit its streaming slot of 0x%X bytes (at 0x%08X).\n\n"
              "The track is not supported by this build. The game stops here instead of overwriting the next slot.",
              kind == BO3_US_FULL ? "full-detail" : "low-detail", (unsigned)size, (unsigned)cap, (unsigned)buf);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(89);
}

void bo3_us_game_init(void)
{
    bo3_us_configure(&g_bo3_us, game_guest, game_alloc, game_build_ok, game_fail, NULL, stderr);
}

/* bo3_unitslots_gen.h */
void bo3_us_gen_apply(void)
{
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    extern void bm_memwin_gate(void);
    bm_memwin_gate();           /* MEM256 layer 0: the budget gate (whichever apply comes first runs it) */
#endif
    bo3_us_apply(&g_bo3_us);
}

void bo3_us_gen_check(int kind, uint32_t buf, uint32_t size)
{
    bo3_us_check(&g_bo3_us, kind, buf, size);
}
#endif
