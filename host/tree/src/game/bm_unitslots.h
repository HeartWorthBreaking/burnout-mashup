/* Burnout Mashup private engine extension (G8-L7 EXPERIMENTAL): the streamed track units' slot sizes.
 *
 * The game streams each track unit into ring slots taken from the memory manager 0x3F9CC0 (B3-PC-3 pools map):
 * layout 1 (one view) has 10 full-detail slots of 0x28000 (descriptors 24-33) and 18 low-detail slots of 0x18000
 * (descriptors 34-51; low detail carries the unit's collision). The unit loaders (sub_0019CC60 full, sub_0019CBB0 low)
 * read the unit-table size into the slot with NO bound: a larger block writes into the next slot.
 *
 *   guard   bo3_us_check, at both reads: the size against the capacity of the descriptor the slot was taken from (found
 *           by pointer among the taken descriptors of the current layout). Over -> the fail handler (the game: a fatal
 *           message and exit 89, before the read). No descriptor found -> not checked, the read goes on (logged).
 *   expand  bo3_us_apply, once, right after the manager's init sub_00022F60: when a low-detail size above 0x18000 was
 *           set (bo3_us_set_low_bytes, from the "bmashup.streaming" service), a new contiguous region of 18 x size is
 *           allocated and descriptors 34-51 are pointed at it (+8 size, +0xC pointer). Only after the 18 descriptors
 *           are verified to be the retail table (owner 1, size 0x18000, free, consecutive). Layout 2 (split screen)
 *           and the full-detail slots are not changed. Fails closed: refused / no memory -> the retail table.
 *
 * MUT=n (test builds only) compiles one deliberate defect for the negative controls. */
#ifndef BM_UNITSLOTS_H
#define BM_UNITSLOTS_H

#include <stdint.h>
#include <stdio.h>

#define BO3_US_DESC_VA      0x003F9CC4u     /* 152 descriptors, 16 bytes: +0 state, +4 owner layout, +8 size, +0xC ptr */
#define BO3_US_DESC_N       152u
#define BO3_US_EXTRA_VA     0x003FA64Cu     /* mgr + 0x98C: 6 more descriptors */
#define BO3_US_EXTRA_N      6u
#define BO3_US_LAYOUT_VA    0x003FA644u     /* the current layout (mgr + 0x984) */
#define BO3_US_LOW1_FIRST   34u             /* layout 1's low-detail slots: descriptors 34..51 (0x3F9EE4) */
#define BO3_US_LOW1_N       18u
#define BO3_US_LOW_RETAIL   0x18000u
#define BO3_US_FULL_RETAIL  0x28000u
#define BO3_US_LOW_MAX      0x30000u        /* the service's ceiling: twice the retail size (18 x = 3.375 MiB) */
#define BO3_US_PAGE         0x1000u
#define BO3_US_TAKEN        0xFFFFFFFFu
#define BO3_US_ANY_LAYOUT   0xFFFFFFFFu

enum { BO3_US_LOW = 0, BO3_US_FULL = 1 };

enum {      /* results */
    BO3_US_OK = 0,
    BO3_US_BAD_ARG = 1,         /* size not a page multiple, below retail or above the ceiling */
    BO3_US_ALREADY = 2,         /* applied (or tried): the size is fixed */
    BO3_US_MISMATCH = 3,        /* descriptors 34-51 are not the retail table: nothing written */
    BO3_US_NO_MEMORY = 4,       /* the contiguous allocation was refused: the retail table */
    BO3_US_UNMAPPED = 5,        /* the descriptor table could not be read */
    BO3_US_UNSUPPORTED = 6      /* not the game build this is verified for */
};

enum {      /* state */
    BO3_US_ST_PLANNED = 0,      /* not applied yet */
    BO3_US_ST_RETAIL = 1,       /* applied: no change asked (or asked size == retail) */
    BO3_US_ST_EXPANDED = 2,     /* applied: descriptors 34-51 point at the new region */
    BO3_US_ST_FAILED = 3        /* applied: refused or no memory; the retail table stays */
};

enum { BO3_US_FIT = 0, BO3_US_OVER = 1, BO3_US_UNKNOWN = 2 };   /* bo3_us_check */

typedef uint8_t *(*bo3_us_guest_fn)(void *user, uint32_t va, uint32_t size);
typedef uint32_t (*bo3_us_alloc_fn)(void *user, uint32_t size, uint32_t align);   /* contiguous; 0 = refused */
typedef int (*bo3_us_build_fn)(void *user);
typedef void (*bo3_us_fail_fn)(void *user, int kind, uint32_t buf, uint32_t size, uint32_t capacity);

typedef struct bo3_us {
    int configured;
    bo3_us_guest_fn guest;
    bo3_us_alloc_fn alloc;
    bo3_us_build_fn build_check;
    bo3_us_fail_fn fail;
    void *user;
    FILE *log;
    uint32_t low_bytes;         /* the requested low-detail size; 0 = retail */
    int state;                  /* BO3_US_ST_* */
    int apply_result;           /* BO3_US_* of the one apply */
    uint32_t region_va;         /* the new region (EXPANDED) */
    uint32_t old_base;          /* descriptor 34's retail pointer */
    uint32_t checks[2], over[2], unknown[2], max_size[2], max_cap[2];
} bo3_us;

extern bo3_us g_bo3_us;

void bo3_us_configure(bo3_us *u, bo3_us_guest_fn guest, bo3_us_alloc_fn alloc, bo3_us_build_fn check, bo3_us_fail_fn fail,
                      void *user, FILE *log);
/* Before the apply: 0 or BO3_US_LOW_RETAIL = no change; else a page multiple in (0x18000, BO3_US_LOW_MAX]. */
int bo3_us_set_low_bytes(bo3_us *u, uint32_t bytes);
/* Descriptors 34-51 are the retail table: owner 1, size 0x18000, free, pointers consecutive from a page-aligned base
 * (stored in *base). BO3_US_OK / MISMATCH / UNMAPPED. Reads only. */
int bo3_us_validate(const bo3_us *u, uint32_t *base);
/* Once, after sub_00022F60. Returns the result (also kept in apply_result). */
int bo3_us_apply(bo3_us *u);
/* The capacity of the taken descriptor (current layout, or every layout) whose pointer is buf: 1 and *cap, or 0. */
int bo3_us_capacity(const bo3_us *u, uint32_t buf, uint32_t *cap);
/* At a unit read: BO3_US_FIT / OVER (the fail handler was called) / UNKNOWN (not checked). */
int bo3_us_check(bo3_us *u, int kind, uint32_t buf, uint32_t size);

#endif
