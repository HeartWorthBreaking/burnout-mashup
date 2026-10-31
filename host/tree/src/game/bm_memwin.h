/* bm_memwin.h - gp slice mem256 (layer 0 of gp\memresearch\MEMORY_EXPANSION_RESEARCH.md s7): the guest window budget gate
 * and the fail-fast for a refused title allocation. Built only with BO3_GUEST_WINDOW_MB=256 (XBOX_CONTIG_WINDOW_MB).
 *
 * Budget gate: at the first capacity apply (bo3_st_gen_apply / bo3_us_gen_apply, after the game set up its memory and before
 * any expansion is allocated) the host sums every planned expansion - the STATIC pool, the GAMEDATA slot, the 18 low-detail
 * LOD slots, a reserve for the front-end texture pool (its 12 MiB cap) and one for the paint palettes, plus a dev-only stress
 * block (patch 08) - each rounded to 4 KB pages, and checks the sum against the free part of the high zone (window offsets
 * 64 MB .. 256 MB). Over budget -> FATAL with every term named, exit 86. It also stops (86) when the toolkit's window and
 * the game's guest-access window (bm_guest.c) disagree.
 * Fail-fast: a title MmAllocateContiguousMemory(Ex) the runtime refuses stops the game with a message (exit 87) instead of
 * returning NULL, which Burnout 3 used as window address 0x80000000 (cm1_acc_1: .bum data written over page 0, then an AV).
 * Both FATAL paths flush the stdio tee (xbox_crash_log_flush) before the dialog and again before _Exit. */
#ifndef BM_MEMWIN_H
#define BM_MEMWIN_H
#include <stddef.h>
#include <stdint.h>

#define BM_MEMWIN_EXIT_BUDGET   86
#define BM_MEMWIN_EXIT_REFUSED  87
#define BM_MEMWIN_PAGE          0x1000u
#define BM_MEMWIN_FETEX_RESERVE (12u << 20)    /* bm_fetex.h BO3_FETEX_POOL_MAX */
#define BM_MEMWIN_PAINT_RESERVE 0x110000u      /* bm_vpaint.c: 1024 palettes = 16 chunks of 64 x 0x440 */

typedef struct bm_memwin_plan {
    uint32_t static_bytes;     /* the STATIC pool expansion (0 = the game's pool) */
    uint32_t gamedata_bytes;   /* the GAMEDATA slot (0 = the game's) */
    uint32_t lod_bytes;        /* 18 x the low-detail slot size (0 = the game's) */
    uint32_t fetex_reserve;    /* the front-end texture pool (sized at first use, at most its cap) */
    uint32_t paint_reserve;    /* the paint palettes (allocated in chunks as paints register) */
    uint32_t stress_bytes;     /* dev only (patch 08): a block placed first to push expansions up */
} bm_memwin_plan;

enum { BM_MEMWIN_OK = 0, BM_MEMWIN_OVER = 1, BM_MEMWIN_MISMATCH = 2 };

/* the plan's total, each term rounded up to whole pages */
uint64_t bm_memwin_total(const bm_memwin_plan *p);
/* window_rt = the toolkit's window, window_guest = bm_guest.c's; zone / zone_in_use = the high zone's size and use.
 * Writes a one-line reason (always) and returns BM_MEMWIN_OK / _OVER / _MISMATCH. */
int bm_memwin_check(const bm_memwin_plan *p, uint32_t window_rt, uint32_t window_guest, uint32_t zone, uint32_t zone_in_use,
                    char *why, size_t wn);

/* both FATAL paths end here: flush the log tee, the message, flush again, exit (ops: stand-ins in the tests) */
typedef struct bm_memwin_stop_ops {
    void (*flush)(void);
    void (*fatal)(const char *title, const char *text);
    void (*exit)(int code);
} bm_memwin_stop_ops;
void bm_memwin_stop_with(const bm_memwin_stop_ops *ops, int code, const char *title, const char *text);

/* game build (BO3_MEMWIN_GAME) */
void bm_memwin_init(void);    /* installs the refusal handler; from bo3_st_game_init */
void bm_memwin_gate(void);    /* the boot gate; once, from the first capacity apply */
#endif
