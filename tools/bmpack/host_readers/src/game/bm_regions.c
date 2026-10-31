/* G8-RG1 EXPERIMENTAL: the region of an added track from its registered ID (bm_regions.h). G8-RG4 EXPERIMENTAL: a declared
 * fourth region (phase 1). MUT=n (test builds only) compiles one deliberate defect:
 *   1-3 (RG1): 1 a region guessed for unregistered IDs, 2 EU / AS swapped, 3 the pair read the wrong way round;
 *   4 (RG4 MUT-e): a declared letter registers as region 0; 5 (RG4 MUT-g): the region is appended without the text check;
 *   G8-TL: 6 Menu A's entry 20 written into the object (off by one), 7 the track row's widget left on the object's array,
 *   8 the other menus' lists stop at 20 (one past their last slot), 9 entries 20+ read from the object, 10 flag entry 128
 *   read from the buffer (off by one), 11 the region row block of 8 (RG4's), 12 the list block only from 22 rows (off by one),
 *   13 the list block's texts not synced (entry 0 / Random missing). */
#include "bm_regions.h"

#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "bm_guest.h"            /* G8-RG4: guest access through the runtime's mappings */
#include "bm_names.h"            /* G8-RG4: the region's host text ID (only while it resolves) */
#include "bm_tracks.h"

#ifndef MUT
#define MUT 0
#endif

static uint64_t s_id[BO3_RG_MAX];
static uint8_t s_region[BO3_RG_MAX];
static uint32_t s_n;
static _Atomic uint32_t s_stats[BO3_RG_SITES][2];

static int region_letters(const char *name)
{
    int k;
#if MUT == 2
    if (!strncmp(name, "US", 2) || !strncmp(name, "EU", 2) || !strncmp(name, "AS", 2))
        return !strncmp(name, "US", 2) ? 0 : !strncmp(name, "EU", 2) ? 2 : 1;   /* defect: EU / AS swapped */
#else
    if (!strncmp(name, "US", 2) || !strncmp(name, "EU", 2) || !strncmp(name, "AS", 2))
        return !strncmp(name, "US", 2) ? 0 : !strncmp(name, "EU", 2) ? 1 : 2;
#endif
    k = bo3_cc_region_of_letter(name[0]);       /* G8-RG4: a declared fourth-region letter */
    if (k < 0)
        return -1;
#if MUT == 4
    return 0;                                   /* defect (MUT-e): the declared letter mapped to USA */
#else
    return (int)BO3_RG4_CODE0 + k;
#endif
}

int bo3_rg_register(uint64_t id)
{
    char name[13];
    int r;
    bo3_cc_decode(id, name);
    r = region_letters(name);
    if (r < 0 || s_n == BO3_RG_MAX)
        return 0;
    for (uint32_t i = 0; i < s_n; i++)
        if (s_id[i] == id)
            return 1;
    s_id[s_n] = id;
    s_region[s_n++] = (uint8_t)r;
    return 1;
}

void bo3_rg_reset(void)
{
    s_n = 0;
    memset(s_stats, 0, sizeof s_stats);
}

int bo3_rg_region_of(uint64_t id)
{
    for (uint32_t i = 0; i < s_n; i++)
        if (s_id[i] == id)
            return s_region[i];
#if MUT == 1
    {                                           /* defect: an unregistered ID gets a region guessed from its letters */
        char name[13];
        bo3_cc_decode(id, name);
        return region_letters(name);
    }
#else
    return -1;
#endif
}

uint32_t bo3_rg_gen_code(uint32_t code, uint32_t lo, uint32_t hi, uint32_t site)
{
    static const char *const k_site[BO3_RG_SITES] = {"radio DJ bank (sub_00155060)", "random track in region (sub_0006D4C0)",
                                                     "random track in region (sub_000995F0)",
                                                     "Single Event track filter (sub_0008C920)",
                                                     "region classifier (sub_00157630)",
                                                     "random track in region: count (sub_0009ADB0)",
                                                     "random track in region: pick (sub_0009ADB0)"};
    int r;
    char name[13];
    if (code != 3u)
        return code;                            /* the game's own answer for every track it knows */
#if MUT == 3
    r = bo3_rg_region_of((uint64_t)lo << 32 | hi);   /* defect: the pair read the wrong way round */
#else
    r = bo3_rg_region_of((uint64_t)hi << 32 | lo);
#endif
    if (site >= BO3_RG_SITES)
        site = 0;
    bo3_cc_decode((uint64_t)hi << 32 | lo, name);
    if (r < 0) {
        if (atomic_fetch_add(&s_stats[site][1], 1) == 0)
            fprintf(stderr, "[REGION] %s: %s is not a registered track: region left at %u\n", k_site[site], name, (unsigned)code);
        return code;
    }
    if (atomic_fetch_add(&s_stats[site][0], 1) == 0)
        fprintf(stderr, "[REGION%s] %s: added track %s: region %u -> %d (from its ID)\n", r >= (int)BO3_RG4_CODE0 ? "4" : "",
                k_site[site], name, (unsigned)code, r);
    return (uint32_t)r;
}

uint32_t bo3_rg_stats(uint32_t site, uint32_t which)
{
    return site < BO3_RG_SITES && which < 2 ? atomic_load(&s_stats[site][which]) : 0;
}

/* ---- G8-RG4: the Single Event region row's host block, and the DJ bank of a declared region ---- */

typedef struct rg4_block {
    uint32_t obj;                               /* the menu object it belongs to (guest VA), 0 = free */
    uint32_t va;                                /* codes[8] at va, texts[8] at va + 32 (guest), 0 = none */
    uint32_t n;                                 /* entries written (the count the game's +0xEC got) */
    int reloc;                                  /* 1 while the menu's region row lives in the block */
} rg4_block;

static rg4_block s_blk[BO3_RG4_MENUS];
static _Atomic uint32_t s_r4[4];
static _Atomic uint32_t s_r4_logged[4];

static uint32_t rd(uint32_t va)
{
    uint32_t v = 0;
    bo3_guest_rd32(va, &v);                     /* refused (logged by bm_guest.c): 0 */
    return v;
}

int bo3_rg4_prepare(uint32_t (*alloc)(uint32_t size, uint32_t align))
{
    if (!bo3_cc_region_count())
        return 1;                               /* no fourth region declared: nothing (retail) */
    for (uint32_t b = 0; b < BO3_RG4_MENUS; b++) {
        uint32_t va;
        if (s_blk[b].va)
            continue;
        va = alloc ? alloc(8u * BO3_RG4_SLOTS, 16u) : 0;
        if (!va || !bo3_guest_window(va, 8u * BO3_RG4_SLOTS)) {
            fprintf(stderr, "[REGION4] no guest memory for the region row's block (%u bytes): the declared regions stay "
                    "hidden in the menus\n", (unsigned)(8u * BO3_RG4_SLOTS));
            return 0;
        }
        s_blk[b].va = va;
    }
    return 1;
}

/* a listable track of that code: a registered track of the code in the game's track list (an added track has no lock) */
static int listable(uint32_t code)
{
    uint8_t t[BO3_CC_TLIST_SIZE];
    uint32_t n;
    if (!bo3_guest_read(BO3_CC_TLIST_VA, t, sizeof t))
        return 0;
    memcpy(&n, t + 4, 4);
    if (n > BO3_CC_CAP)
        return 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t lo, hi;
        memcpy(&lo, t + BO3_CC_OFF_ID + 8u * i, 4);
        memcpy(&hi, t + BO3_CC_OFF_ID + 8u * i + 4u, 4);
        if (bo3_rg_region_of((uint64_t)hi << 32 | lo) == (int)code)
            return 1;
    }
    return 0;
}

/* the block valid for obj: it holds the region row, and +0xEC is still the count written with it */
static const rg4_block *block_of(uint32_t obj)
{
    for (uint32_t b = 0; b < BO3_RG4_MENUS; b++)
        if (s_blk[b].va && s_blk[b].obj == obj && s_blk[b].reloc)
            return rd(obj + 0xECu) == s_blk[b].n ? &s_blk[b] : NULL;
    return NULL;
}

static void log_once(uint32_t which, const char *fmt, ...)
{
    va_list ap;
    if (atomic_fetch_add(&s_r4_logged[which], 1) != 0)
        return;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

void bo3_rg_gen_menu_regions(uint32_t obj, uint32_t menu)
{
    uint32_t nreg = bo3_cc_region_count(), n, add = 0, codes[BO3_RG4_SLOTS], texts[BO3_RG4_SLOTS];
    rg4_block *b = NULL;
    (void)menu;
    if (!nreg)
        return;                                 /* no fourth region declared: retail */
    for (uint32_t i = 0; i < BO3_RG4_MENUS && !b; i++)
        if (s_blk[i].va && s_blk[i].obj == obj)
            b = &s_blk[i];
    for (uint32_t i = 0; i < BO3_RG4_MENUS && !b; i++)
        if (s_blk[i].va && !s_blk[i].obj) {
            s_blk[i].obj = obj;
            b = &s_blk[i];
        }
    if (!b) {
        atomic_fetch_add(&s_r4[3], 1);
        log_once(3, "[REGION4] menu 0x%08X: no host block (%u menus): the declared region is not shown\n", (unsigned)obj,
                 (unsigned)BO3_RG4_MENUS);
        return;
    }
    b->reloc = 0;                               /* the game just rebuilt its in-object row */
    n = rd(obj + 0xECu);
    if (n == 0 || n > BO3_RG4_GAME_ROWS) {
        atomic_fetch_add(&s_r4[3], 1);
        log_once(3, "[REGION4] menu 0x%08X: the game's region count is %u (expected 1 .. %u): not extended\n", (unsigned)obj,
                 (unsigned)n, (unsigned)BO3_RG4_GAME_ROWS);
        return;
    }
    for (uint32_t i = 0; i < n; i++) {
        codes[i] = rd(obj + 0xCCu + 4u * i);
        texts[i] = rd(obj + 0xDCu + 4u * i);
    }
#if MUT != 11
    for (uint32_t k = 0; k < nreg && n + add < BO3_RG4_SLOTS; k++) {
#else
    for (uint32_t k = 0; k < nreg && n + add < 8u; k++) {   /* defect: RG4's block of 8 (4 added regions at most) */
#endif
        uint32_t code = BO3_RG4_CODE0 + k, id;
        if (!listable(code))
            continue;                           /* no listable track: the region is not offered (as the game's own rule) */
#if MUT == 5
        id = BO3_NM_REGION_BASE + k;            /* defect (MUT-g): appended without asking whether the ID resolves */
#else
        id = bo3_nm_region_text_id(k);
#endif
        if (!id) {
            atomic_fetch_add(&s_r4[1], 1);
            log_once(1, "[REGION4] menu 0x%08X: region %u (%s) not shown: its text is not in the table the game reads "
                     "(never an unresolvable ID)\n", (unsigned)obj, (unsigned)code, bo3_cc_region_at(k)->text);
            continue;
        }
        codes[n + add] = code;
        texts[n + add] = id;
        add++;
    }
    if (!add)
        return;
    if (!bo3_guest_write(b->va, codes, 4u * (n + add)) || !bo3_guest_write(b->va + 4u * BO3_RG4_SLOTS, texts, 4u * (n + add)) ||
        !bo3_guest_wr32(obj + 0xECu, n + add))
        return;                                 /* refused (logged by bm_guest.c): the game's own row stays */
    b->n = n + add;
    b->reloc = 1;
    atomic_fetch_add(&s_r4[0], 1);
    {   /* G8-TL: the line names every appended region (code, text, text ID) */
        char all[BO3_CC_REGIONS_MAX * (BO3_CC_REGION_TEXT_MAX + 16u) + 1u] = "";
        for (uint32_t i = n; i < n + add; i++)
            snprintf(all + strlen(all), sizeof all - strlen(all), "%s%u %s 0x%X", i > n ? ", " : "", (unsigned)codes[i],
                     bo3_cc_region_at(codes[i] - BO3_RG4_CODE0)->text, (unsigned)texts[i]);
        log_once(0, "[REGION4] menu 0x%08X: %u + %u regions (%s), row block 0x%08X\n", (unsigned)obj, (unsigned)n,
                 (unsigned)add, all, (unsigned)b->va);
    }
}

uint32_t bo3_rg_gen_menu_code(uint32_t obj, uint32_t i)
{
    const rg4_block *b = block_of(obj);
    if (b && i < b->n)
        return rd(b->va + 4u * i);
    return rd(obj + 4u * i + 0xCCu);            /* the game's own read (MEM32(obj + i * 4 + 0xCC)) */
}

uint32_t bo3_rg_gen_menu_texts(uint32_t obj)
{
    const rg4_block *b = block_of(obj);
    return b ? b->va + 4u * BO3_RG4_SLOTS : obj + 0xDCu;
}

uint32_t bo3_rg_gen_dj(uint32_t code)
{
    uint32_t k = code - BO3_RG4_CODE0;
    if (code >= BO3_RG4_CODE0 && k < bo3_cc_region_count()) {
        static const char *const k_bank[3] = {"DJUS", "DJEU", "DJAS"};
        const bo3_cc_region *r = bo3_cc_region_at(k);
        uint32_t dj = r->dj < 3u ? r->dj : 0u;
        atomic_fetch_add(&s_r4[2], 1);
        log_once(2, "[REGION4] dj: region %u (%s) -> %s (PLACEHOLDER: a retail bank)\n", (unsigned)code, r->text, k_bank[dj]);
        return rd(BO3_RG4_DJ_TABLE + 4u * dj);  /* a retail bank name: its file exists */
    }
    return rd(BO3_RG4_DJ_TABLE + 4u * code);    /* the game's own read (MEM32(code * 4 + 0x3EC8EC)) */
}

uint32_t bo3_rg4_stats(uint32_t which)
{
    return which < 4 ? atomic_load(&s_r4[which]) : 0;
}

/* ---- G8-TL: the Single Event track list block, the other menus' list bound, the flags of entries 128+ ---- */

#define TL_IDS(i)    (8u * (i))                         /* ids u64 at va + 8 i */
#define TL_TEXTS(i)  (8u * BO3_TL_SLOTS + 4u * (i))     /* texts u32 at va + 8 * 384 + 4 i */
#define TL_OFF_ID    0xF0u                              /* the menu object's own list (+0xF0 u64[20], +0x190 u32[20]) */
#define TL_OFF_TEXT  0x190u

typedef struct tl_block {
    uint32_t va;                                /* ids / texts (guest), 0 = none */
    uint32_t obj;                               /* the menu object it belongs to, 0 = free */
} tl_block;

static tl_block s_tl[BO3_TL_MENUS];
static _Atomic uint32_t s_tls[5];
static _Atomic uint32_t s_tl_logged[4 + BO3_TL_SITES];

static void tl_log_once(uint32_t which, const char *fmt, ...)
{
    va_list ap;
    if (atomic_fetch_add(&s_tl_logged[which], 1) != 0)
        return;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

uint32_t bo3_tl_largest_list(char *letter)
{
    uint8_t t[BO3_CC_TLIST_SIZE];
    uint32_t n, per[26] = {0}, best = 0;
    if (letter)
        *letter = 0;
    if (!bo3_guest_read(BO3_CC_TLIST_VA, t, sizeof t))
        return 0;
    memcpy(&n, t + 4, 4);
    if (n > BO3_CC_CAP)
        n = BO3_CC_CAP;
    for (uint32_t i = 0; i < n; i++) {
        uint64_t v;
        char name[13];
        memcpy(&v, t + BO3_CC_OFF_ID + 8u * i, 8);
        bo3_cc_decode(v, name);
        if (name[0] >= 'A' && name[0] <= 'Z')
            per[name[0] - 'A']++;               /* the region is the ID's first letter (U / E / A, or a declared one) */
    }
    for (uint32_t k = 0; k < 26; k++)
        if (per[k] > best) {
            best = per[k];
            if (letter)
                *letter = (char)('A' + k);
        }
    return best ? best + 1u : 0u;               /* + Random */
}

int bo3_tl_prepare(uint32_t (*alloc)(uint32_t size, uint32_t align))
{
    char letter;
    uint32_t largest = bo3_tl_largest_list(&letter);
#if MUT != 12
    if (largest <= BO3_TL_GAME_ROWS)
#else
    if (largest <= BO3_TL_GAME_ROWS + 1u)       /* defect: a list of exactly 21 rows gets no block */
#endif
        return 1;                               /* every list fits the game's own 20 rows: nothing (as before) */
    for (uint32_t b = 0; b < BO3_TL_MENUS; b++) {
        uint32_t va;
        if (s_tl[b].va)
            continue;
        va = alloc ? alloc(BO3_TL_BLOCK, 16u) : 0;
        if (!va || !bo3_guest_window(va, BO3_TL_BLOCK)) {
            fprintf(stderr, "[TRACKLIST] no guest memory for the Single Event track list block (%u bytes)\n",
                    (unsigned)BO3_TL_BLOCK);
            return 0;
        }
        s_tl[b].va = va;
        s_tl[b].obj = 0;
    }
    fprintf(stderr, "[TRACKLIST] Single Event track lists: the largest has %u rows (region letter %c, Random + %u); the game's "
            "own list holds %u: entries %u+ in host blocks of %u rows (0x%08X, 0x%08X)\n", (unsigned)largest, letter,
            (unsigned)(largest - 1u), (unsigned)BO3_TL_GAME_ROWS, (unsigned)BO3_TL_GAME_ROWS, (unsigned)BO3_TL_SLOTS,
            (unsigned)s_tl[0].va, (unsigned)s_tl[1].va);
    return 1;
}

void bo3_tl_reset(void)
{
    memset(s_tl, 0, sizeof s_tl);
    for (uint32_t i = 0; i < 5; i++)
        atomic_store(&s_tls[i], 0);
    for (uint32_t i = 0; i < 4 + BO3_TL_SITES; i++)
        atomic_store(&s_tl_logged[i], 0);
}

/* the block of obj; claim = 1 gives a free block to a new menu object (Menu A's functions only call with claim) */
static tl_block *tl_of(uint32_t obj, int claim)
{
    for (uint32_t b = 0; b < BO3_TL_MENUS; b++)
        if (s_tl[b].va && s_tl[b].obj == obj)
            return &s_tl[b];
    if (!claim)
        return NULL;
    for (uint32_t b = 0; b < BO3_TL_MENUS; b++)
        if (s_tl[b].va && !s_tl[b].obj) {
            s_tl[b].obj = obj;
            atomic_fetch_add(&s_tls[4], 1);
            return &s_tl[b];
        }
    return NULL;
}

uint32_t bo3_tl_block_va(uint32_t obj)
{
    const tl_block *b = tl_of(obj, 0);
    return b ? b->va : 0;
}

static uint32_t tl_obj_field(uint32_t obj, uint32_t i, uint32_t which)
{
    return which == 2u ? obj + TL_OFF_TEXT + 4u * i : obj + TL_OFF_ID + 8u * i + (which ? 4u : 0u);
}

static uint32_t tl_blk_field(const tl_block *b, uint32_t i, uint32_t which)
{
    return which == 2u ? b->va + TL_TEXTS(i) : b->va + TL_IDS(i) + (which ? 4u : 0u);
}

void bo3_tl_gen_put(uint32_t obj, uint32_t i, uint32_t which, uint32_t v)
{
    tl_block *b = tl_of(obj, 1);
    if (which > 2u)
        return;
#if MUT != 6
    if (i < BO3_TL_GAME_ROWS)
#else
    if (i <= BO3_TL_GAME_ROWS)                  /* defect: entry 20 written into the object (over +0x190 / +0x1E0) */
#endif
        bo3_guest_wr32(tl_obj_field(obj, i, which), v);   /* the game's own write (MEM32(obj + i * 8 + 0xF0) / ...) */
    if (b && i < BO3_TL_SLOTS) {
        bo3_guest_wr32(tl_blk_field(b, i, which), v);
        if (i >= BO3_TL_GAME_ROWS && which == 2u)
            atomic_fetch_add(&s_tls[0], 1);
    } else if (i >= BO3_TL_GAME_ROWS) {
        atomic_fetch_add(&s_tls[1], 1);
        tl_log_once(0, "[TRACKLIST] menu 0x%08X: track list entry %u not stored (%s): the list stops there\n", (unsigned)obj,
                    (unsigned)i, b ? "beyond the host block" : "no host block");
    }
}

uint32_t bo3_tl_gen_get(uint32_t obj, uint32_t i, uint32_t which)
{
    const tl_block *b;
    uint32_t v = 0;
    if (which > 1u)
        return 0;
#if MUT != 9
    if (i < BO3_TL_GAME_ROWS)
#else
    if (i < BO3_TL_SLOTS)                       /* defect: entries 20+ read from the object (past its list) */
#endif
    {
        bo3_guest_rd32(tl_obj_field(obj, i, which), &v);  /* the game's own read (MEM32(obj + i * 8 + 0xF0)) */
        return v;
    }
    b = tl_of(obj, 1);
    if (b && i < BO3_TL_SLOTS) {
        bo3_guest_rd32(tl_blk_field(b, i, which), &v);
        tl_log_once(1, "[TRACKLIST] menu 0x%08X: track list entry %u read from the host block (0x%08X)\n", (unsigned)obj,
                    (unsigned)i, (unsigned)b->va);
        return v;
    }
    atomic_fetch_add(&s_tls[1], 1);
    tl_log_once(2, "[TRACKLIST] menu 0x%08X: track list entry %u has no storage: read as 0\n", (unsigned)obj, (unsigned)i);
    return 0;
}

uint32_t bo3_tl_gen_texts(uint32_t obj)
{
    tl_block *b = tl_of(obj, 1);
    if (!b)
        return obj + TL_OFF_TEXT;               /* the game's own array (edi + 0x190) */
#if MUT != 7
#if MUT != 13
    for (uint32_t i = 0; i < BO3_TL_GAME_ROWS; i++) {   /* the rows the game wrote itself (entry 0's 0x2CB "Random") */
        uint32_t v = 0;
        bo3_guest_rd32(tl_obj_field(obj, i, 2u), &v);
        bo3_guest_wr32(tl_blk_field(b, i, 2u), v);
    }
#endif
    return b->va + TL_TEXTS(0);
#else
    return obj + TL_OFF_TEXT;                   /* defect: the widget keeps the object's 20-entry array */
#endif
}

uint32_t bo3_tl_gen_list_inc(uint32_t obj, uint32_t count, uint32_t site)
{
    static const char *const k_site[BO3_TL_SITES] = {
        "Single Event builder (sub_0008C920)", "Single Event left / right (sub_0008D020)", "twin builder (sub_00078DD0)",
        "twin left / right (sub_00079590)", "menu B builder (sub_0009A3A0)", "menu B left / right (sub_0009BF20)",
        "menu C builder (sub_000B2520)", "menu C left / right (sub_000B2B90)"};
    uint32_t max;
    if (site >= BO3_TL_SITES)
        site = BO3_TL_SITE_TWIN_BUILD;          /* unknown: the strict bound */
    if (site <= BO3_TL_SITE_A_INPUT)            /* Menu A writes through bo3_tl_gen_put: entries past the storage drop */
        max = tl_of(obj, 0) ? BO3_TL_SLOTS : BO3_TL_GAME_ROWS;
    else
#if MUT != 8
        max = BO3_TL_GAME_ROWS - 1u;            /* the game's own writes: the next one lands at index <= 19 (in the list) */
#else
        max = BO3_TL_GAME_ROWS;                 /* defect: the next write lands at index 20 (+0x190 / the count) */
#endif
    if (count + 1u <= max)
        return count + 1u;                      /* the game's own `count + 1` */
    atomic_fetch_add(&s_tls[2], 1);
    tl_log_once(4 + site, "[TRACKLIST] %s: menu 0x%08X track list full at %u rows: further tracks are not listed there\n",
                k_site[site], (unsigned)obj, (unsigned)max);
    return count > max ? count : max;
}

uint32_t bo3_tl_gen_flag(uint32_t base, uint32_t i, uint32_t which)
{
    uint32_t v = 0, n = 0;
    which = which ? 1u : 0u;
#if MUT != 10
    if (base != BO3_CC_TLIST_VA || (int32_t)i < (int32_t)BO3_CC_FLAG_CAP)
#else
    if (base != BO3_CC_TLIST_VA || (int32_t)i <= (int32_t)BO3_CC_FLAG_CAP)   /* defect: entry 128 read from the buffer */
#endif
    {   /* the game's own read: MEM32(base + i * 4 + 8 / 0x208), also for i = -1 (an ID not in the list) */
        bo3_guest_rd32(base + (which ? BO3_CC_OFF_B : BO3_CC_OFF_A) + 4u * i, &v);
        return v;
    }
    bo3_guest_rd32(BO3_CC_TLIST_VA + 4u, &n);
    atomic_fetch_add(&s_tls[3], 1);
    tl_log_once(3, "[TRACKLIST] track list entry %u (of %u): flag %c from the host table (the buffer's flag arrays end at "
                "%u)\n", (unsigned)i, (unsigned)n, which ? 'B' : 'A', (unsigned)BO3_CC_FLAG_CAP);
    return i < n ? bo3_cc_flag_ext(i, which) : 0u;
}

uint32_t bo3_tl_stats(uint32_t which)
{
    return which < 5 ? atomic_load(&s_tls[which]) : 0;
}
