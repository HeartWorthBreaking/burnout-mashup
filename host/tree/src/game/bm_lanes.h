/* Burnout Mashup private engine extension (Layer 2, build-specific; G8-L5a EXPERIMENTAL + lane lifetime design "C",
 * not for release): the AI route-lane wrapper table grown from 64 entries to a TOTAL LANE CAPACITY of 64 + N, where N is
 * the number of EXTENSION ENTRIES (lanes 64..64+N-1; e.g. 80 total = 16 entries). Split:
 *
 *   index 0..63      -> 0x0060EA2C + 8*index   (the original table, never moved)
 *   index 255        -> 0x0060F224             (the original "no lane" address)
 *   index 64..64+N-1 -> ext_va + 8*(index-64), while the loaded track installed that lane (bo3_lane_wrapper, the API);
 *                       the generated code's forms (compat / x8) ALSO serve a RETAINED wrapper (see below)
 *   anything else    -> refused by bo3_lane_wrapper; the consumer forms (compat / x8) keep the original arithmetic
 *
 * N: BO3_LANE_EXT_COUNT (1, the G8-L4 behaviour) unless bo3_lanes_set_entries set it first (G8-L5a: the frozen
 * capacity plugins requested through "bmashup.engine", bm_engine_service.c). 1 <= N <= 191: lane numbers are u8 and
 * 255 means "no lane", so 255 total is the format's ceiling. N is fixed once the extension is allocated.
 *
 * Lifecycle (bo3_lane_load, called by the transformed loader sub_0018B250 once per lane, i = 0..count-1):
 *   i == 0: a new track: the extension's lanes are uninstalled (installed = 0) and the publish counter advances; their
 *           +4 is NOT cleared (design C, LANE_LIFETIME_DESIGN.md 4.4); when count > 64 the extension (N entries) is
 *           allocated now if it never was (lazily, once per process, xbox_HeapAlloc, after the build check);
 *   i < 64: the original address (the loader's original store, byte for byte);
 *   i in 64..64+N-1 with the extension present: installs that lane (the loader then stores its +4) and ends its
 *           retention;
 *   otherwise: 0 = the store is refused and logged: never a write past the original table.
 *
 * Lane lifetime (design C): at the race-exit route teardown (sub_0018BD60, mark BO3_LANE_RETAIN, before the route's
 * +0x560 is cleared) and as a backup at the next load's ACQUIRE (sub_0018B250, mark BO3_LANE_RETAIN_ACQ, only when the
 * exit was not seen), every installed, not yet retained extension lane's 16-byte record and its rungs / dims / segments
 * arrays are copied into a grow-only guest-heap block (xbox_HeapAlloc; never freed), the copy's +0 / +4 / +8 fixed up to
 * name its own arrays, and the extension wrapper's +4 re-pointed at the copy (RETAINED). A stale holder of that wrapper
 * then reads the old lane's own bytes, in bounds, until the loader reinstalls the lane. +4 is never set to 0 again; when
 * the source fails validation (outside the track slot [route+0x560, +0x176000), not inside mapped guest memory by the E4
 * window rule, count 0) or the heap refuses, +4 is left as it was (the old address: retail's own stale-entry class) and
 * the failure is counted and logged once per kind.
 * A track of 64 or fewer lanes never allocates and never touches the extension: its behaviour and the guest
 * heap layout are the original ones. All values are 32-bit guest VAs; no host pointer reaches guest memory. */
#ifndef BM_LANES_H
#define BM_LANES_H

#include <stdint.h>
#include <stdio.h>

#ifndef BO3_LANES_EXT_ENABLED
#define BO3_LANES_EXT_ENABLED 1   /* G8-L4 experimental build: the extension exists (0 = the G8-L3b behaviour) */
#endif
#ifndef BO3_LANE_EXT_COUNT
#define BO3_LANE_EXT_COUNT 1u     /* the default entry count (G8-L4: lane 64) when nothing set another */
#endif

#define BO3_LANE_TABLE_VA    0x0060EA2Cu
#define BO3_LANE_LEGACY_MAX  64u
#define BO3_LANE_NONE        255u
#define BO3_LANE_NONE_VA     (BO3_LANE_TABLE_VA + 8u * BO3_LANE_NONE)
#define BO3_LANE_EXT_MAX     191u                  /* entries: lanes 64..254 (255 = NONE) */
#define BO3_LANE_TOTAL_MAX   (BO3_LANE_LEGACY_MAX + BO3_LANE_EXT_MAX)   /* 255 total */
#define BO3_GUEST_HEAP_LO    0x01000000u
#define BO3_GUEST_HEAP_HI    0x04000000u
#define BO3_RACE_WORLD_VA    0x0060EA00u
#define BO3_RACE_WORLD_END   0x00752E00u
#define BO3_ROUTE_BUF_OFF    0x560u                /* route + 0x560: the track-data slot buffer (ACQUIRE / race exit) */
#define BO3_LANE_SLOT_SIZE   0x00176000u           /* the GAMEDATA slot (L6a.1 guard): every record / array lies inside */

typedef uint8_t *(*bo3_guest_ptr_fn)(void *user, uint32_t va, uint32_t size);
typedef uint32_t (*bo3_guest_alloc_fn)(void *user, uint32_t size, uint32_t align);   /* guest VA or 0 */
typedef int (*bo3_build_check_fn)(void *user);                                       /* 1 = supported */

enum bo3_lanes_state { BO3_LANES_LEGACY_ONLY = 0, BO3_LANES_EXTENDED = 1 };

enum bo3_lanes_result {
    BO3_LANES_OK = 0,
    BO3_LANES_BAD_ARG = -1,
    BO3_LANES_OVERLAP = -2,
    BO3_LANES_UNMAPPED = -3,
    BO3_LANES_UNSUPPORTED = -4,
    BO3_LANES_ALREADY = -5,
    BO3_LANES_REFUSED = -6,
    BO3_LANES_DISABLED = -7,
    BO3_LANES_NO_MEMORY = -8,
};

/* the retain fallback kinds (each logged once per process, all counted) */
enum bo3_lanes_retain_kind {
    BO3_LR_NO_BUFFER = 0,     /* route + 0x560 unreadable or 0 */
    BO3_LR_OUTSIDE_SLOT,      /* the record or an array lies outside [buf, buf + BO3_LANE_SLOT_SIZE) */
    BO3_LR_UNMAPPED,          /* ... or is not inside mapped guest memory (E4 window rule) */
    BO3_LR_BAD_COUNT,         /* n = 0 */
    BO3_LR_NO_MEMORY,         /* the guest heap refused the snapshot block */
    BO3_LR_BAD_BLOCK,         /* the block failed validation (heap range, race world, extension, slot, unmapped) */
    BO3_LR_KINDS
};

typedef struct bo3_lanes {
    int state;                      /* LEGACY_ONLY until the extension is allocated and initialised */
    int configured;                 /* bo3_lanes_configure was called */
    uint32_t ext_va, ext_count;     /* the extension (guest VA, entries) once EXTENDED */
    uint32_t installed;             /* extension lanes the CURRENT track installed (0..ext_count) */
    bo3_guest_ptr_fn guest;
    bo3_guest_alloc_fn alloc;
    bo3_build_check_fn build_check;
    void *user;
    FILE *log;
    int alloc_tried, alloc_result;  /* the one allocation attempt and its result (bo3_lanes_result) */
    uint32_t loads, last_count;     /* track loads seen (i == 0) and that track's lane count */
    uint32_t load_refused;          /* lanes of the current track refused (beyond capacity / no extension) */
    uint32_t refused;               /* lookups refused by bo3_lane_wrapper since start */
    uint32_t entries;               /* extension entries to allocate (0 = BO3_LANE_EXT_COUNT); see bo3_lanes_set_entries */
    /* --- lane lifetime (design C) --- */
    bo3_guest_ptr_fn span;          /* source reads: a host pointer only when [va, va + n) is inside mapped guest memory */
    uint32_t blk[BO3_LANE_EXT_MAX]; /* entry k's snapshot block (guest VA), 0 = none; grow-only, never freed */
    uint32_t cap[BO3_LANE_EXT_MAX]; /* its bytes */
    uint32_t src[BO3_LANE_EXT_MAX]; /* the record it was copied from (diagnostics only) */
    uint8_t retained[BO3_LANE_EXT_MAX];   /* W + 4 names blk[k] */
    uint32_t gen_published, gen_retained, gen_diag;   /* publish counter; generation retained; generation diagnosed */
    uint32_t ret_exit_calls, ret_acq_calls, ret_acq_acted;
    uint32_t ret_copied;            /* snapshots taken (lane copies) */
    uint32_t ret_skipped;           /* already retained: not re-copied */
    uint32_t ret_stale;             /* not installed by the current track but +4 != 0 (an earlier fallback): left */
    uint32_t ret_fallback;          /* +4 left as it was (all kinds) */
    uint32_t ret_refused;           /* ... of which the source failed validation */
    uint32_t ret_alloc_fail;        /* ... of which the block could not be had */
    uint32_t ret_kind[BO3_LR_KINDS];
    uint32_t ret_logged;            /* kinds already logged (bit mask) */
    uint32_t blk_allocs, blk_bytes; /* snapshot blocks allocated, their bytes */
    uint32_t served_retained;       /* compat lookups served from a retained wrapper */
    uint32_t last_route;            /* the route the last mark named */
    /* PLATFORM-P1 (P-3): a track with more lanes than the capacity (count > 64 + entries, after the one allocation
     * attempt): called at that track's first lane, before any lane is stored. The game's (bo3_lanes_game_fail) stops
     * the start (code 97). NULL (the default; the unit tests): logged and continued as before. */
    void (*fail)(void *user, uint32_t count, uint32_t cap, int alloc_result);
} bo3_lanes;

extern bo3_lanes g_bo3_lanes;

/* Accessor, allocator and build check; allocates nothing. */
void bo3_lanes_configure(bo3_lanes *l, bo3_guest_ptr_fn guest, bo3_guest_alloc_fn alloc, bo3_build_check_fn check,
                         void *user, FILE *log);
/* The source accessor of the lane lifetime (E4 window rule in the game). Without it RETAIN copies nothing (fallback). */
void bo3_lanes_configure_span(bo3_lanes *l, bo3_guest_ptr_fn span);
/* PLATFORM-P1 (P-3): the overflow handler (above); set once. bo3_lanes_game_fail: the game's (FATAL line, box,
 * _Exit(97)); compiled in the game build and with BO3_LANES_FAIL_TEST. */
void bo3_lanes_configure_fail(bo3_lanes *l, void (*fail)(void *user, uint32_t count, uint32_t cap, int alloc_result));
void bo3_lanes_game_fail(void *user, uint32_t count, uint32_t cap, int alloc_result);
/* Claims [ext_va, ext_va + 8*count) as the extension (validated: heap range, alignment, no overlap with the race world,
 * mapped) and writes each wrapper's +0 = its lane index, +4 = 0. Used by the lazy allocation; exposed for tests. */
int bo3_lanes_init(bo3_lanes *l, bo3_guest_ptr_fn guest, void *user, uint32_t ext_va, uint32_t count, int build_ok);

/* The extension's entry count (1..BO3_LANE_EXT_MAX) before its allocation: OK, BAD_ARG out of range, ALREADY once the
 * allocation was attempted (the size is then fixed). bo3_lanes_entries: the count that applies (allocated or planned). */
int bo3_lanes_set_entries(bo3_lanes *l, uint32_t entries);
uint32_t bo3_lanes_entries(const bo3_lanes *l);

uint32_t bo3_lane_load(bo3_lanes *l, uint32_t index, uint32_t lane_count);   /* the loader's store address, or 0 */
uint32_t bo3_lane_wrapper(bo3_lanes *l, uint32_t index);                       /* fail closed: 0 when not served */
uint32_t bo3_lane_wrapper_compat(bo3_lanes *l, uint32_t index);                /* consumers: retained, else the original */
uint32_t bo3_lane_wrapper_x8(bo3_lanes *l, uint32_t x);                        /* consumers holding 8*index */

/* Lane lifetime. backup = 0: the race exit (always acts); 1: ACQUIRE (acts only when the published route was not
 * retained). Returns the lanes snapshotted now. bo3_lanes_retained: the wrappers whose +4 names a snapshot. */
uint32_t bo3_lanes_retain(bo3_lanes *l, uint32_t route, int backup);
uint32_t bo3_lanes_retained(const bo3_lanes *l);
/* Read-only holder check (racer list of the race world, racer +0x18C4 / +0x1BD4, copy 0x56781C): how many name a
 * retained wrapper; *checked = holders read. Through span only. */
uint32_t bo3_lanes_holder_check(bo3_lanes *l, uint32_t world, uint32_t *checked, uint32_t *listed);
/* The LOADED-time diagnostic: one log line per published track (retained count, holders naming a retained wrapper). */
void bo3_lanes_loaded_diag(bo3_lanes *l, uint32_t world);
/* PLATFORM-P3 (U5 G8): "[LANES] lane lifetime at process exit: served from retained snapshots N ..." (extension only;
 * the game: atexit from bo3_lanes_game_init) */
void bo3_lanes_exit_summary(const bo3_lanes *l);

/* What the transformed generated code calls (bo3_lanes_gen.h, bo3_lanelife_gen.h) and the game's one-time set-up. */
uint32_t bo3_lane_w(uint32_t index);
uint32_t bo3_lane_w8(uint32_t x);
uint32_t bo3_lane_load_gen(uint32_t index, uint32_t lane_count);
void bo3_lane_retain_gen(uint32_t route);
void bo3_lane_retain_acq_gen(uint32_t route);
void bo3_lanes_game_init(void);
void bo3_lanes_after_update(void);   /* host frame hook (race_service.c): the LOADED-time diagnostic, game build only */

#endif
