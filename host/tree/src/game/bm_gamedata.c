/* G8-L6a: the GAMEDATA loader guard (host / generated-code prerequisite; not plugin-controlled).
 *
 * The stage-3 track loader (sub_0018B250) reads a track's GAMEDATA event into one pool buffer: header 0x3000, the event
 * record 0x800, then the sections S1, S2, S3, S4 back to back. Their sizes come from the record (+0x3BC / +0x3C4 / +0x3CC /
 * +0x3D4), S2's from the header's per-variant table (+0x2034 + 4 v) when the loader's variant flag (+0x58B) is set. The
 * buffer is pool descriptor 0x003FA004 (layout 1) or 0x003FA4C4 (layout 2: [0x003FA644] == 2), size at +8, base at +0xC.
 * The loader never compares the need with the slot (KB RESOURCE_LIMITS s2): data past the slot overwrites the next pool.
 *
 * bo3_gd_check(loader) runs once per load, right after the loader sets its section cursor (record + 0x800) and before the
 * first section read. It computes the need exactly as the loader will consume it and compares it with the slot:
 *   fits      -> one log line "[GAMEDATA] ... need N of the slot's S (headroom H)"; the load continues unchanged
 *   too large -> "[GAMEDATA] FATAL ..." on stderr (and the player's message box unless headless), then the process ends
 *                with code 88 BEFORE any section is read: fail closed instead of corrupting the next pool
 * Anything it cannot verify (a descriptor whose base is not the loader's buffer, an unreadable record) is reported and
 * treated as "not checked"; the load continues as the retail game would (the guard never makes a legal load fail). */
#include "bm_gamedata.h"

#include <stdio.h>
#include <stdlib.h>

#include "fatal.h"

#ifndef MUT
#define MUT 0     /* tests only: 1 32-bit sum, 2 variant S2 ignored, 3 need == slot refused, 4 layout 2 ignored */
#endif

bo3_gamedata g_bo3_gd;

static uint32_t rd(const bo3_gamedata *g, uint32_t va, int *ok)
{
    const uint8_t *b = g->guest ? g->guest(g->user, va, 4) : NULL;
    if (!b) { *ok = 0; return 0; }
    return (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}
static uint32_t rd8(const bo3_gamedata *g, uint32_t va, int *ok)
{
    const uint8_t *b = g->guest ? g->guest(g->user, va, 1) : NULL;
    if (!b) { *ok = 0; return 0; }
    return b[0];
}

void bo3_gd_configure(bo3_gamedata *g, bo3_gd_guest_fn guest, bo3_gd_fail_fn fail, void *user, FILE *log)
{
    g->guest = guest; g->fail = fail; g->user = user; g->log = log;
    g->checks = g->unchecked = g->failed = 0; g->last_need = g->last_slot = 0;
}

int bo3_gd_need(const bo3_gamedata *g, uint32_t loader, uint64_t *need, uint32_t *slot, uint32_t *base)
{
    int ok = 1;
    uint32_t rec = rd(g, loader + BO3_GD_LD_RECORD, &ok), hdr = rd(g, loader + BO3_GD_LD_HEADER, &ok);
    uint32_t buf = rd(g, loader + BO3_GD_LD_BUFFER, &ok), variant = rd8(g, loader + BO3_GD_LD_VARIANT, &ok);
    uint32_t layout = rd(g, BO3_GD_LAYOUT_VA, &ok);
#if MUT == 4
    uint32_t desc = BO3_GD_DESC_L1;
    (void)layout;
#else
    uint32_t desc = layout == 2 ? BO3_GD_DESC_L2 : BO3_GD_DESC_L1;
#endif
    uint32_t s1, s2, s3, s4;
    if (!ok)
        return 0;
    s1 = rd(g, rec + 0x3BC, &ok);
#if MUT == 2
    (void)hdr; (void)variant;
    s2 = rd(g, rec + 0x3C4, &ok);
#else
    s2 = variant ? rd(g, hdr + 0x2034 + 4u * rd(g, loader + BO3_GD_LD_VINDEX, &ok), &ok) : rd(g, rec + 0x3C4, &ok);
#endif
    s3 = rd(g, rec + 0x3CC, &ok);
    s4 = rd(g, rec + 0x3D4, &ok);
    *slot = rd(g, desc + 8, &ok);
    *base = rd(g, desc + 0xC, &ok);
    if (!ok || *base != buf)
        return 0;
#if MUT == 1
    *need = (uint32_t)(BO3_GD_FIXED + s1 + s2 + s3 + s4);
#else
    *need = (uint64_t)BO3_GD_FIXED + s1 + s2 + s3 + s4;     /* 64-bit: section sizes cannot wrap the sum */
#endif
    return 1;
}

int bo3_gd_check(bo3_gamedata *g, uint32_t loader)
{
    uint64_t need;
    uint32_t slot, base;
    if (!bo3_gd_need(g, loader, &need, &slot, &base)) {
        g->unchecked++;
        if (g->log)
            fprintf(g->log, "[GAMEDATA] loader 0x%08X: need NOT CHECKED (descriptor / record not verifiable); the load "
                    "continues as retail\n", (unsigned)loader);
        return 1;
    }
    g->checks++;
    g->last_need = need; g->last_slot = slot;
#if MUT == 3
    if (need < slot) {
#else
    if (need <= slot) {
#endif
        if (g->log)
            fprintf(g->log, "[GAMEDATA] route data need 0x%llX of the slot's 0x%X at 0x%08X (headroom 0x%llX, %.1f%%)\n",
                    (unsigned long long)need, (unsigned)slot, (unsigned)base, (unsigned long long)(slot - need),
                    100.0 * (double)need / (double)slot);
        return 1;
    }
    g->failed++;
    if (g->fail)
        g->fail(g->user, need, slot, base);
    return 0;
}

#ifdef BO3_GAMEDATA_GAME
#include <stddef.h>
#include "bo3_gamedata_gen.h"

extern ptrdiff_t g_xbox_mem_offset;
extern void xbox_crash_log_flush(unsigned max_ms);     /* xboxrecomp kernel/xbox_crash.h: drain the stdio tee */

static const uint8_t *game_guest(void *user, uint32_t va, uint32_t size)
{
    uint64_t end = (uint64_t)va + size;
    (void)user;
    /* main RAM or the contiguous window (the slot's base is 0x8xxxxxxx); nothing else is read */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
    /* MEM256: the expanded slot lives in the high zone (64 MB .. the window's end) */
    if (!g_xbox_mem_offset || !((va >= 0x00010000u && end <= 0x04000000u) ||
                                (va >= 0x80000000u && end <= 0x80000000ull + ((uint64_t)XBOX_CONTIG_WINDOW_MB << 20))))
#else
    if (!g_xbox_mem_offset || !((va >= 0x00010000u && end <= 0x04000000u) || (va >= 0x80000000u && end <= 0x84000000u)))
#endif
        return NULL;
    return (const uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}

static void game_fail(void *user, uint64_t need, uint32_t slot, uint32_t base)
{
    (void)user;
    fprintf(stderr, "[GAMEDATA] FATAL: the track's route data needs 0x%llX bytes; the GAMEDATA slot at 0x%08X holds 0x%X. "
            "Loading it would overwrite the next memory pool, so the game stops here (code 88).\n",
            (unsigned long long)need, (unsigned)base, (unsigned)slot);
    fflush(stderr);
    xbox_crash_log_flush(1000);     /* L6a.1 (D-L6a-1): fds 1 / 2 go through the runtime's tee thread; _Exit skips its
                                     * atexit drain, so the line above was lost. Wait for the tee before ending. */
    bo3_fatal("Takedawn: track data too large",
              "The selected track's route data (Gamedata.bgd) needs %llu bytes, but the game's GAMEDATA buffer holds %u. "
              "Loading it would corrupt memory, so the game will close. Remove or fix the track mod.",
              (unsigned long long)need, (unsigned)slot);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(88);
}

void bo3_gd_gen_check(uint32_t loader) { (void)bo3_gd_check(&g_bo3_gd, loader); }

void bo3_gd_game_init(void) { bo3_gd_configure(&g_bo3_gd, game_guest, game_fail, NULL, stderr); }
#endif
