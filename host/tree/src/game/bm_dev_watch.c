/*
 * bm_dev_watch.c - main21 patch 84: DEV-ONLY guest-memory access log (BO3_DEV_WATCH=ON builds only; a default build compiles
 * nothing of it). Purpose: find the code that sets the race list's racer count 0x73A19C (hook request "zackypoo" 09 rival count):
 * it is written through a pointer, so no static reader / writer table names it.
 *
 * With BO3_DEV_WATCH the generated code's XBOX_PTR (recomp_types.h: every MEMx access, the rep movs / stos block copies, the XMM
 * loads / stores) first compares the guest address with the window BO3_DEV_WATCH_LO .. + BO3_DEV_WATCH_SPAN (0x73A100 .. 0x73A1A3:
 * the count and the 0xA0 bytes below it, so a block copy that starts lower is seen) and calls bo3_dev_watch_hit() on a hit. Each
 * distinct site (generated file + line, the host return address = inside the generated function; the DEV build writes a linker
 * map burnout3.map next to the exe) is logged ONCE as "[WATCH] site ..."; every change of the count's value is logged with the
 * site of the access before it ("[WATCH] count A -> B after <site>") - a write is executed after its own XBOX_PTR, so the change
 * shows at the next access and names the writer. At exit a summary of every site (hits, changes after it). Logs go to stderr
 * (the run's tee). Nothing is written to guest memory; the game behaves as the default build, only slower.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(BO3_DEV_WATCH) && BO3_DEV_WATCH
#include <stddef.h>

extern ptrdiff_t g_xbox_mem_offset;
void bo3_dev_watch_hit(const char *file, int line, uint32_t addr);

#define WATCH_COUNT 0x0073A19Cu
#define SITES 512
typedef struct { const char *file; int line; uint32_t addr; void *ret; uint32_t hits, changes; } site;
static site s_site[SITES];
static int s_n, s_prev = -1, s_full, s_registered;
static uint32_t s_last = 0xFFFFFFFFu, s_changes;

static const char *base_name(const char *p)
{
    const char *b = p;
    for (; *p; p++)
        if (*p == '/' || *p == '\\')
            b = p + 1;
    return b;
}

static void summary(void)
{
    fprintf(stderr, "[WATCH] summary: %d sites, %u count changes\n", s_n, (unsigned)s_changes);
    for (int i = 0; i < s_n; i++)
        fprintf(stderr, "[WATCH]   %s:%d addr %08X host %p hits %u changes-after %u\n", base_name(s_site[i].file), s_site[i].line,
                (unsigned)s_site[i].addr, s_site[i].ret, (unsigned)s_site[i].hits, (unsigned)s_site[i].changes);
    fflush(stderr);
}

__attribute__((noinline)) void bo3_dev_watch_hit(const char *file, int line, uint32_t addr)
{
    void *ret = __builtin_return_address(0);
    uint32_t cur;
    int i;
    if (!g_xbox_mem_offset)
        return;
    if (!s_registered) {
        s_registered = 1;
        atexit(summary);
        fprintf(stderr, "[WATCH] DEV-ONLY access log on: window %08X .. %08X (racer count %08X)\n", 0x0073A100u, 0x0073A1A3u,
                WATCH_COUNT);
    }
    memcpy(&cur, (const void *)((uintptr_t)WATCH_COUNT + (uintptr_t)g_xbox_mem_offset), 4);
    if (cur != s_last) {
        if (s_prev >= 0) {
            s_site[s_prev].changes++;
            fprintf(stderr, "[WATCH] count %u -> %u after %s:%d (addr %08X, host %p)\n", (unsigned)s_last, (unsigned)cur,
                    base_name(s_site[s_prev].file), s_site[s_prev].line, (unsigned)s_site[s_prev].addr, s_site[s_prev].ret);
            fflush(stderr);
        }
        s_changes++;
        s_last = cur;
    }
    for (i = 0; i < s_n; i++)
        if (s_site[i].line == line && s_site[i].file == file && s_site[i].ret == ret)
            break;
    if (i == s_n) {
        if (s_n == SITES) {
            if (!s_full)
                fprintf(stderr, "[WATCH] site table full (%d)\n", SITES);
            s_full = 1;
            s_prev = -1;
            return;
        }
        s_site[s_n].file = file;
        s_site[s_n].line = line;
        s_site[s_n].addr = addr;
        s_site[s_n].ret = ret;
        fprintf(stderr, "[WATCH] site %s:%d addr %08X host %p\n", base_name(file), line, (unsigned)addr, ret);
        s_n++;
    }
    s_site[i].hits++;
    s_prev = i;
}
#else
typedef int bm_dev_watch_off;            /* a default build: nothing here */
#endif
