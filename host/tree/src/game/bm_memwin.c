/* bm_memwin.c - gp slice mem256: the guest window budget gate + the fail-fast for a refused title allocation (bm_memwin.h).
 * MUT=n (tests only) compiles one deliberate defect. */
#include "bm_memwin.h"

#include <stdio.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

static uint64_t pages(uint32_t b)
{
#if MUT == 2
    return b;                                   /* defect: no page rounding */
#else
    return ((uint64_t)b + BM_MEMWIN_PAGE - 1) / BM_MEMWIN_PAGE * BM_MEMWIN_PAGE;
#endif
}

uint64_t bm_memwin_total(const bm_memwin_plan *p)
{
    return pages(p->static_bytes) + pages(p->gamedata_bytes) + pages(p->lod_bytes) + pages(p->full_bytes) + pages(p->fetex_reserve) +
           pages(p->paint_reserve) + pages(p->stress_bytes);
}

int bm_memwin_check(const bm_memwin_plan *p, uint32_t window_rt, uint32_t window_guest, uint32_t zone, uint32_t zone_in_use,
                    char *why, size_t wn)
{
    uint64_t need = bm_memwin_total(p), free_ = zone > zone_in_use ? (uint64_t)zone - zone_in_use : 0;
#if MUT == 1
    free_ = zone;                               /* defect: what is already in use is ignored */
#endif
#if MUT != 3
    if (window_rt != window_guest) {
        snprintf(why, wn, "the runtime's contiguous window is %u MB but the host's guest-access checks assume %u MB "
                 "(a mixed build: toolkit and game built with different BO3_GUEST_WINDOW_MB)",
                 (unsigned)(window_rt >> 20), (unsigned)(window_guest >> 20));
        return BM_MEMWIN_MISMATCH;
    }
#endif
    snprintf(why, wn, "STATIC 0x%X + GAMEDATA 0x%X + LOD 0x%X + FULL 0x%X + front-end textures 0x%X (reserve) + paints 0x%X"
             " (reserve) + dev stress 0x%X = %llu KB; high zone %u KB, %u KB in use, %llu KB free",
             (unsigned)p->static_bytes, (unsigned)p->gamedata_bytes, (unsigned)p->lod_bytes, (unsigned)p->full_bytes,
             (unsigned)p->fetex_reserve,
             (unsigned)p->paint_reserve, (unsigned)p->stress_bytes, (unsigned long long)(need >> 10), (unsigned)(zone >> 10),
             (unsigned)(zone_in_use >> 10), (unsigned long long)(free_ >> 10));
    return need <= free_ ? BM_MEMWIN_OK : BM_MEMWIN_OVER;
}

/* The one way out of both FATAL paths: drain the log tee (fds 1 / 2 go through the runtime's tee thread and _Exit skips its
 * drain - memory note "Exit drains log tee"), show the message, drain again, exit. Testable with stand-in ops. */
void bm_memwin_stop_with(const bm_memwin_stop_ops *ops, int code, const char *title, const char *text)
{
    fflush(stdout);
    fflush(stderr);
#if MUT != 4
    ops->flush();                               /* MUT 4 defect: the message and exit before the first drain */
#endif
    ops->fatal(title, text);
    fflush(stdout);
    fflush(stderr);
    ops->flush();
    ops->exit(code);
}

#ifdef BO3_MEMWIN_GAME
#include <stdlib.h>

#include "bm_gdslot.h"
#include "bm_guest.h"
#include "bm_static.h"
#include "bm_unitslots.h"
#include "kernel/xbox_memory_layout.h"

extern void xbox_crash_log_flush(unsigned max_ms);     /* xboxrecomp kernel/xbox_crash.h: drain the stdio tee */
extern void bo3_fatal(const char *title, const char *fmt, ...);

static void g_flush(void) { xbox_crash_log_flush(1000); }
static void g_fatal(const char *title, const char *text) { bo3_fatal(title, "%s", text); }
static void g_exit(int code) { _Exit(code); }
static const bm_memwin_stop_ops s_ops = { g_flush, g_fatal, g_exit };

static void stop(int code, const char *title, const char *text)
{
    bm_memwin_stop_with(&s_ops, code, title, text);
}

static void on_refused(uint32_t caller, uint32_t size, uint32_t low, uint32_t high, uint32_t align)
{
    static char text[768];
    uint32_t in_use = xbox_ContiguousInUseBytes(), hi = xbox_ContiguousHighInUseBytes();
    fprintf(stderr, "[MEMWIN] FATAL: the game's contiguous memory request was refused: %u bytes (caller 0x%08X, range "
            "0x%08X..0x%08X, align %u); the title's 64 MB of the guest window hold %u KB in use (the high zone %u KB). The game "
            "has no recovery for this (it would use address 0x80000000), so it stops here (code %d).\n", (unsigned)size,
            (unsigned)caller, (unsigned)low, (unsigned)high, (unsigned)align, (unsigned)((in_use - hi) >> 10),
            (unsigned)(hi >> 10), BM_MEMWIN_EXIT_REFUSED);
    snprintf(text, sizeof text, "The game asked for %u bytes of its graphics memory (caller 0x%08X) and none was left: its 64 MB "
             "are full (%u KB in use).\n\nThe game cannot continue without it, so it stops here instead of corrupting memory. "
             "Turn off some content mods and try again; the log names the request.", (unsigned)size, (unsigned)caller,
             (unsigned)((in_use - hi) >> 10));
    stop(BM_MEMWIN_EXIT_REFUSED, "Takedawn: out of game graphics memory", text);
}

void bm_memwin_init(void)
{
    static int done;
    if (done)
        return;
    done = 1;
    xbox_SetContiguousRefusalHandler(on_refused);
    fprintf(stderr, "[MEMWIN] guest contiguous window %u MB (title 64 MB + high zone %u MB for host expansions); a refused "
            "title allocation stops the game (code %d)\n", (unsigned)(xbox_ContiguousWindowBytes() >> 20),
            (unsigned)(xbox_ContiguousHighZoneBytes() >> 20), BM_MEMWIN_EXIT_REFUSED);
}

#if !defined(BO3_RELEASE_BUILD)
/* DEV ONLY (patch 08; never in a release build): BMASHUP_DEV_MEMWIN_STRESS_MB=N (1..160) places one N MB block at the bottom
 * of the high zone before any expansion, so the expansions land N MB higher - a forced placement above 128 MB for the
 * stress launch (the 28-bit compares, the APU / dma_resolve paths). The block is zero-filled and never used or freed. */
static uint32_t dev_stress_bytes(void)
{
    const char *e = getenv("BMASHUP_DEV_MEMWIN_STRESS_MB");
    long mb = e ? strtol(e, NULL, 10) : 0;
    if (mb <= 0)
        return 0;
    if (mb > 160) {
        fprintf(stderr, "[MEMWIN] DEV STRESS: BMASHUP_DEV_MEMWIN_STRESS_MB=%s ignored (1..160)\n", e);
        return 0;
    }
    return (uint32_t)mb << 20;
}

static void dev_stress_place(uint32_t bytes)
{
    uint32_t va;
    if (!bytes)
        return;
    va = xbox_ContiguousAllocHigh(bytes, BM_MEMWIN_PAGE);
    fprintf(stderr, "[MEMWIN] DEV STRESS: %u MB block at 0x%08X; the expansions start at window offset %u MB\n",
            (unsigned)(bytes >> 20), (unsigned)va, (unsigned)((va - 0x80000000u + bytes) >> 20));
}
#else
static uint32_t dev_stress_bytes(void) { return 0; }
static void dev_stress_place(uint32_t bytes) { (void)bytes; }
#endif

void bm_memwin_gate(void)
{
    static int done;
    static char why[512], text[900];
    bm_memwin_plan p;
    uint32_t gd = 0;
    int rc;

    if (done)
        return;
    done = 1;
    memset(&p, 0, sizeof p);
    p.static_bytes = g_bo3_st.bytes;
    (void)bo3_gds_request(0, &gd);             /* bytes 0: no change, answers the merged request */
    p.gamedata_bytes = gd > BO3_GDS_GAME ? gd : 0;
    p.lod_bytes = g_bo3_us.low_bytes * BO3_US_LOW1_N;
    p.full_bytes = g_bo3_us.full_bytes * BO3_US_FULL1_N;   /* patch 131 */
    p.fetex_reserve = BM_MEMWIN_FETEX_RESERVE;
    p.paint_reserve = BM_MEMWIN_PAINT_RESERVE;
    p.stress_bytes = dev_stress_bytes();
    rc = bm_memwin_check(&p, xbox_ContiguousWindowBytes(), bo3_guest_window_bytes(), xbox_ContiguousHighZoneBytes(),
                         xbox_ContiguousHighInUseBytes(), why, sizeof why);
    fprintf(stderr, "[MEMWIN] budget gate: %s: %s\n", rc == BM_MEMWIN_OK ? "OK" : "REFUSED", why);
    if (rc == BM_MEMWIN_OK) {
        dev_stress_place(p.stress_bytes);
        return;
    }
    fprintf(stderr, "[MEMWIN] FATAL: the capacity expansions do not fit the guest window; the game stops before allocating "
            "them (code %d)\n", BM_MEMWIN_EXIT_BUDGET);
    snprintf(text, sizeof text, "The installed mods ask for more game memory than this build has.\n\n%s\n\nTurn off some "
             "capacity mods (their mod.toml [bmashup.capacity]) and try again.", why);
    stop(BM_MEMWIN_EXIT_BUDGET, rc == BM_MEMWIN_MISMATCH ? "Takedawn: inconsistent build" : "Takedawn: mods need too much memory",
         text);
}
#endif
