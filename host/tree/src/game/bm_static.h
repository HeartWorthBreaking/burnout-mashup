/* Burnout Mashup private engine extension (G8-L9 EXPERIMENTAL): the STATIC track pool (l9_static\STATIC_ANALYSIS.md).
 *
 * The track's static.dat is read in one piece into the layout's STATIC pool: descriptor 23 (layout 1, 0xD00000) or 73
 * (layout 2, 0xA00000), both at the same base in block B; the front end's 147 (0x100000) is not changed. The load request
 * passes the pool size as the read length (sub_0019AE10 -> sub_00011240 -> sub_000110E0), so a larger file is TRUNCATED,
 * silently, and then relocated and used (sub_0019B4E0).
 *
 *   check   bo3_st_check, after the read and before the relocation: static.dat +4 (its own size, = the file length on every
 *           retail track) against the capacity of the taken STATIC descriptor of the current layout.
 *             complete   -> one line per load ("complete", and "beyond the game's pool" when it is past the default)
 *             truncated  -> layouts 1 and 0: "[STATIC] FATAL", the fail handler (the game: exit 90) before relocation;
 *                           layout 2: "[STATIC] TRUNCATED" diagnosed and counted, the load goes on as in the game
 *                           (retail split screen has six statics > 0xA00000; whether they are used there is UNT);
 *                           layout 2 with STRICT truncation on (G8-G7): "[STATIC] FATAL ... (strict)" and the fail handler,
 *                           exactly as one view (counted in strict_stops)
 *   strict  G8-G7, default OFF (the behaviour above unchanged). Set while the game starts only (state PLANNED, i.e. before
 *           bo3_st_apply at the memory manager's init): BMASHUP_STATIC_STRICT=1 read once by bo3_st_game_init (exactly "1"
 *           turns it on; "0", absent or anything else leaves it off, and an unrecognised value is logged), or the host's
 *           bo3_st_set_strict (e.g. from a host / mod configuration while the plugins start). Logged once when it turns on:
 *           "[STATIC] strict truncation: on (<source>)". Not offered to plugins through "bmashup.streaming" (v2 unchanged).
 *             not a STATIC buffer / unreadable / implausible header -> NOT CHECKED (logged), the load goes on
 *   expand  bo3_st_apply, once, after the manager's init (sub_00022F60), when a size S was set (bo3_st_set_bytes, from
 *           "bmashup.streaming" v2): one contiguous region of S bytes; descriptor 23 points at it when S > 0xD00000,
 *           descriptor 73 when S > 0xA00000 (both at the same region, as the game shares one base between them). Only
 *           after both are verified as the game's (owner, size, state free, the shared page-aligned base). Fails closed.
 *
 *   guest   the game build's accessor (bo3_st_mapped_guest, G8-G7) validates every range through bm_guest.c (G8-E4): main RAM
 *           0x10000 .. xbox_GetMappedSize(), the contiguous window only inside an allocated block for the whole length;
 *           anything else is refused (NULL: the load is NOT CHECKED and logged; the apply fails closed as UNMAPPED).
 *
 * MUT=n (test builds only) compiles one deliberate defect for the negative controls (G8-L9: 1..7; G8-G7: 31..37). */
#ifndef BM_STATIC_H
#define BM_STATIC_H

#include <stdint.h>
#include <stdio.h>

#define BO3_ST_DESC_L1      0x003F9E34u     /* idx 23: layout 1 STATIC */
#define BO3_ST_DESC_L2      0x003FA154u     /* idx 73: layout 2 STATIC */
#define BO3_ST_DESC_L0      0x003FA5F4u     /* idx 147: front-end scene (checked, never changed) */
#define BO3_ST_LAYOUT_VA    0x003FA644u
#define BO3_ST_L1_GAME      0xD00000u
#define BO3_ST_L2_GAME      0xA00000u
#define BO3_ST_L0_GAME      0x100000u
#define BO3_ST_PAGE         0x1000u
/* The largest region the contiguous window could ever hold (STATIC_ANALYSIS.md s5): the usable window (64 MiB - the
 * 128 KiB GPU instance), minus the 1 MiB low reserve a large request steps over, minus the game's blocks A / B / C as
 * allocated (page-rounded 0x3C4000 + 0x1A37000 + 0x21000). Whether S can be had is the allocator's answer at boot. */
#define BO3_ST_WINDOW_USABLE  (0x4000000u - 0x20000u)
#define BO3_ST_LOW_RESERVE    0x100000u
#define BO3_ST_GAME_BLOCKS    (0x3C4000u + 0x1A37000u + 0x21000u)
#define BO3_ST_MAX_W64        ((BO3_ST_WINDOW_USABLE - BO3_ST_LOW_RESERVE - BO3_ST_GAME_BLOCKS) & ~(BO3_ST_PAGE - 1u))
/* patch 131 (owner 2026-11-02 "safest maximum"): a 256 MiB-window build (MEM256, the default) allocates the region in the
 * high zone (64 .. 256 MiB, bm_static.c game_alloc -> xbox_ContiguousAllocHigh), not in the game's 64 MiB: the ceiling
 * there is 64 MiB; the boot budget gate (bm_memwin.c) stays the real fail-closed check of the sum. 64 MiB builds: as before. */
#if defined(XBOX_CONTIG_WINDOW_MB) && XBOX_CONTIG_WINDOW_MB != 64
#define BO3_ST_MAX            0x4000000u
#else
#define BO3_ST_MAX            BO3_ST_MAX_W64
#endif
#define BO3_ST_HDR_MIN        0x60u         /* the relocated header reaches +0x5C */
#define BO3_ST_TAKEN          0xFFFFFFFFu

enum { BO3_ST_OK = 0, BO3_ST_BAD_ARG = 1, BO3_ST_ALREADY = 2, BO3_ST_MISMATCH = 3, BO3_ST_NO_MEMORY = 4,
       BO3_ST_UNMAPPED = 5, BO3_ST_UNSUPPORTED = 6 };
enum { BO3_ST_ST_PLANNED = 0, BO3_ST_ST_GAME = 1, BO3_ST_ST_EXPANDED = 2, BO3_ST_ST_FAILED = 3 };
enum { BO3_ST_COMPLETE = 0, BO3_ST_TRUNCATED = 1, BO3_ST_FATAL = 2, BO3_ST_UNKNOWN = 3 };   /* bo3_st_check */

typedef uint8_t *(*bo3_st_guest_fn)(void *user, uint32_t va, uint32_t size);
typedef uint32_t (*bo3_st_alloc_fn)(void *user, uint32_t size, uint32_t align);   /* contiguous; 0 = refused */
typedef int (*bo3_st_build_fn)(void *user);
typedef void (*bo3_st_fail_fn)(void *user, uint32_t layout, uint32_t declared, uint32_t capacity, uint32_t buf);

typedef struct bo3_static {
    int configured;
    bo3_st_guest_fn guest;
    bo3_st_alloc_fn alloc;
    bo3_st_build_fn build_check;
    bo3_st_fail_fn fail;
    void *user;
    FILE *log;
    uint32_t bytes;             /* the requested region size; 0 = the game's pools */
    int state;                  /* BO3_ST_ST_* */
    int apply_result;
    uint32_t region_va, base_game;
    uint32_t l1_bytes, l2_bytes;   /* the capacities in force after the apply */
    uint32_t loads, complete, beyond, truncated, unknown;
    uint32_t last_declared, last_capacity, largest;
    /* G8-G7 (appended: the fields above keep their offsets) */
    int strict;                 /* 1: split-screen truncation stops the game as one view does */
    int strict_logged;          /* the "on" line was written */
    uint32_t strict_stops;      /* split-screen loads stopped because strict was on */
    char strict_source[48];     /* who turned it on / off last ("" = the default) */
} bo3_static;

extern bo3_static g_bo3_st;

void bo3_st_configure(bo3_static *s, bo3_st_guest_fn guest, bo3_st_alloc_fn alloc, bo3_st_build_fn check, bo3_st_fail_fn fail,
                      void *user, FILE *log);
/* Before the apply: 0 = no change; else a page multiple in (BO3_ST_L2_GAME, BO3_ST_MAX]. */
int bo3_st_set_bytes(bo3_static *s, uint32_t bytes);
/* Descriptors 23 and 73 are the game's (reads only); *base = their shared base. */
int bo3_st_validate(const bo3_static *s, uint32_t *base);
int bo3_st_apply(bo3_static *s);
/* After a STATIC read, before its relocation: buf = the pool pointer the load used. */
int bo3_st_check(bo3_static *s, uint32_t buf);

/* G8-G7: strict truncation. on = 0 / 1; source names the caller in the log (NULL: "host"). BO3_ST_OK, BO3_ST_ALREADY once
 * the apply ran (the option is fixed from the memory manager's init on), BO3_ST_BAD_ARG without s. */
int bo3_st_set_strict(bo3_static *s, int on, const char *source);
/* The environment rule: value = getenv("BMASHUP_STATIC_STRICT") (NULL: absent). Exactly "1" -> on; NULL / "0" -> off;
 * anything else -> off and logged as not recognised. Returns the strict state after it (1 / 0). */
int bo3_st_strict_from_env(bo3_static *s, const char *value);
#define BO3_ST_STRICT_ENV "BMASHUP_STATIC_STRICT"

#if defined(BO3_STATIC_GAME) || defined(BO3_ST_GUEST_TEST)
/* The game build's guest accessor (bm_guest.c's range check; NULL when [va, va + size) is not mapped guest memory). */
uint8_t *bo3_st_mapped_guest(void *user, uint32_t va, uint32_t size);
#endif

#endif
