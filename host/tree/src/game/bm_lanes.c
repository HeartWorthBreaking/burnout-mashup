/* Burnout Mashup private engine extension (G8-L5a EXPERIMENTAL + lane lifetime design "C"): see bm_lanes.h. From the
 * G8-L5a resolver (rule, compat / x8 forms, run-time entry count unchanged) with the extension's +4 never cleared again:
 * retired extension lanes are snapshotted into host-owned guest-heap blocks at the race exit (bo3_lanes_retain;
 * content_count\cross_track\LANE_LIFETIME_DESIGN.md sections 4.2 - 4.6). MUT=n (test builds only) compiles one
 * deliberate defect for the negative controls: 1..10 the L4 / L5a ones (4 is now the base behaviour: no clear),
 * 21..27 the design's lifetime mutants M1..M7. */
#include "bm_lanes.h"

#include <stddef.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

_Static_assert(sizeof(uint32_t) == 4, "guest addresses are 32-bit");
_Static_assert(BO3_LANE_NONE_VA == 0x0060F224u, "no-lane address");
_Static_assert(BO3_LANE_TABLE_VA + 8u * BO3_LANE_LEGACY_MAX == 0x0060EC2Cu, "table ends where the next one starts");
_Static_assert(BO3_LANE_EXT_COUNT >= 1u && BO3_LANE_EXT_COUNT <= BO3_LANE_EXT_MAX, "extension size");
_Static_assert(BO3_LANE_TOTAL_MAX == BO3_LANE_NONE, "the last usable lane is 254: 255 is NONE");
_Static_assert(BO3_LR_KINDS <= 32, "kinds fit the log mask");

bo3_lanes g_bo3_lanes;

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int overlaps(uint32_t a, uint32_t a_end, uint32_t b, uint32_t b_end)
{
    return a < b_end && b < a_end;
}

void bo3_lanes_configure(bo3_lanes *l, bo3_guest_ptr_fn guest, bo3_guest_alloc_fn alloc, bo3_build_check_fn check,
                         void *user, FILE *log)
{
    if (!l || l->configured)
        return;
    l->guest = guest;
    l->alloc = alloc;
    l->build_check = check;
    l->user = user;
    l->log = log;
    l->configured = guest && alloc && check;
}

void bo3_lanes_configure_span(bo3_lanes *l, bo3_guest_ptr_fn span)
{
    if (l && !l->span)
        l->span = span;
}

#ifndef P1_MUT
#define P1_MUT 0     /* tests only: one deliberate defect (tests\test_p1_lanes.c) */
#endif

void bo3_lanes_configure_fail(bo3_lanes *l, void (*fail)(void *user, uint32_t count, uint32_t cap, int alloc_result))
{
    if (l && !l->fail)
        l->fail = fail;
}

int bo3_lanes_init(bo3_lanes *l, bo3_guest_ptr_fn guest, void *user, uint32_t ext_va, uint32_t count, int build_ok)
{
    uint32_t end;
    uint8_t *p;

    if (!l)
        return BO3_LANES_BAD_ARG;
#if !BO3_LANES_EXT_ENABLED
    (void)guest; (void)user; (void)ext_va; (void)count; (void)build_ok; (void)put32; (void)overlaps; (void)end; (void)p;
    return BO3_LANES_DISABLED;
#else
    if (l->state == BO3_LANES_EXTENDED)
        return BO3_LANES_ALREADY;
    if (!build_ok)
        return BO3_LANES_UNSUPPORTED;
    if (!guest || count == 0 || count > BO3_LANE_EXT_MAX || (ext_va & 7u))
        return BO3_LANES_BAD_ARG;
    if (ext_va > 0xFFFFFFFFu - 8u * count)
        return BO3_LANES_BAD_ARG;
    end = ext_va + 8u * count;
#if MUT != 6
    if (ext_va < BO3_GUEST_HEAP_LO || end > BO3_GUEST_HEAP_HI ||
        overlaps(ext_va, end, BO3_RACE_WORLD_VA, BO3_RACE_WORLD_END))
        return BO3_LANES_OVERLAP;
#else
    (void)overlaps; (void)end;
#endif
    p = guest(user, ext_va, 8u * count);
    if (!p)
        return BO3_LANES_UNMAPPED;
    for (uint32_t k = 0; k < count; k++) {
#if MUT == 5
        put32(p + 8u * k, 0);
#else
        put32(p + 8u * k, BO3_LANE_LEGACY_MAX + k);     /* +0: the lane's own number, as sub_001A9C50 for 0..63 */
#endif
        put32(p + 8u * k + 4u, 0);                      /* +4: no lane record until a track installs it */
    }
    l->guest = guest;
    l->user = user;
    l->ext_va = ext_va;
    l->ext_count = count;
    l->installed = 0;
    l->state = BO3_LANES_EXTENDED;
    return BO3_LANES_OK;
#endif
}

int bo3_lanes_set_entries(bo3_lanes *l, uint32_t entries)
{
    if (!l || entries == 0 || entries > BO3_LANE_EXT_MAX)
        return BO3_LANES_BAD_ARG;
#if MUT != 10
    if (l->alloc_tried || l->state == BO3_LANES_EXTENDED)
        return BO3_LANES_ALREADY;               /* allocated (or tried): racers may hold its address; fixed */
#endif
    l->entries = entries;
    return BO3_LANES_OK;
}

uint32_t bo3_lanes_entries(const bo3_lanes *l)
{
    if (!l)
        return 0;
    if (l->state == BO3_LANES_EXTENDED)
        return l->ext_count;
    return l->entries ? l->entries : BO3_LANE_EXT_COUNT;
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* Lane lifetime (design C)                                                                                            */

static const char *const s_kind_name[BO3_LR_KINDS] = {
    "no track buffer at route + 0x560",
    "the record or an array lies outside the track slot [buf, buf + 0x176000)",
    "the record or an array is not inside mapped guest memory (E4 window rule)",
    "the lane has no segments (n = 0)",
    "the guest heap refused the snapshot block",
    "the snapshot block failed validation",
};

#if MUT == 25
static uint32_t s_m5_sa[BO3_LANE_EXT_MAX][3];        /* M5 only: the first copy's source array addresses */
#endif

static uint32_t a16(uint32_t x)
{
    return (x + 15u) & ~15u;
}

static void retain_fallback(bo3_lanes *l, uint32_t k, uint32_t r, int kind)
{
    l->ret_fallback++;
    l->ret_kind[kind]++;
    if (kind == BO3_LR_NO_MEMORY || kind == BO3_LR_BAD_BLOCK)
        l->ret_alloc_fail++;
    else
        l->ret_refused++;
    if (!(l->ret_logged & (1u << kind))) {
        l->ret_logged |= 1u << kind;
        if (l->log)
            fprintf(l->log, "[LANES] lane lifetime: lane %u NOT snapshotted (%s): its +4 is kept at 0x%08X (the old "
                    "address, retail's stale-entry class; never 0); further failures of this kind are counted only\n",
                    (unsigned)(BO3_LANE_LEGACY_MAX + k), s_kind_name[kind], (unsigned)r);
    }
}

/* [va, va + n) inside the track slot */
static int in_slot(uint32_t buf, uint32_t va, uint32_t n)
{
    return va >= buf && (uint64_t)va + n <= (uint64_t)buf + BO3_LANE_SLOT_SIZE;
}

/* a validated source range: inside the slot and mapped (span); NULL with *kind set otherwise */
static const uint8_t *src_range(bo3_lanes *l, uint32_t buf, uint32_t va, uint32_t n, int *kind)
{
#if MUT == 26
    extern ptrdiff_t g_xbox_mem_offset;          /* defect (M6): no source validation at all */
    (void)l; (void)buf; (void)n; (void)kind; (void)in_slot;
    return (const uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
#else
    const uint8_t *p;
    if (!in_slot(buf, va, n)) {
        *kind = BO3_LR_OUTSIDE_SLOT;
        return NULL;
    }
    p = l->span ? l->span(l->user, va, n) : NULL;
    if (!p)
        *kind = BO3_LR_UNMAPPED;
    return p;
#endif
}

/* a usable snapshot block of need bytes for entry k (reused while its capacity suffices); 0 with *kind set otherwise */
static uint32_t snapshot_block(bo3_lanes *l, uint32_t k, uint32_t need, uint32_t buf, int *kind)
{
    uint32_t va = l->blk[k];
    if (!va || l->cap[k] < need) {
        va = l->alloc(l->user, need, 16u);
        if (!va) {
            *kind = BO3_LR_NO_MEMORY;
            return 0;
        }
        if ((va & 15u) || va < BO3_GUEST_HEAP_LO || va > BO3_GUEST_HEAP_HI - need ||
            overlaps(va, va + need, BO3_RACE_WORLD_VA, BO3_RACE_WORLD_END) ||
            overlaps(va, va + need, l->ext_va, l->ext_va + 8u * l->ext_count) || !l->guest(l->user, va, need)) {
            *kind = BO3_LR_BAD_BLOCK;                /* the old block (if any) stays as it was */
            return 0;
        }
        l->blk[k] = va;                              /* the old block is never freed (no HeapFree): it stays mapped */
        l->cap[k] = need;
        l->blk_allocs++;
        l->blk_bytes += need;
    }
    if ((uint64_t)va + l->cap[k] > buf && (uint64_t)buf + BO3_LANE_SLOT_SIZE > va) {
        *kind = BO3_LR_BAD_BLOCK;                    /* never inside the slot the next load overwrites */
        return 0;
    }
    return va;
}

/* copy entry k's live lane (record r) into its block and re-point the wrapper; 1 done, 0 fell back (+4 unchanged) */
static int snapshot_lane(bo3_lanes *l, uint32_t k, uint8_t *w, uint32_t r, uint32_t buf)
{
    const uint8_t *rec, *sr, *sd, *ss;
    uint32_t n, o_d, o_s, need, blk;
    uint8_t *d;
    int kind = BO3_LR_OUTSIDE_SLOT;

    if (!(rec = src_range(l, buf, r, 16u, &kind)))
        goto fail;
    n = get32(rec + 0xC) & 0xFFFFu;
    if (n == 0) {
        kind = BO3_LR_BAD_COUNT;
        goto fail;
    }
    if (!(sr = src_range(l, buf, get32(rec + 0), 4u * (n + 1u), &kind)) ||
        !(sd = src_range(l, buf, get32(rec + 4), 8u * n, &kind)) ||
        !(ss = src_range(l, buf, get32(rec + 8), 10u * n, &kind)))
        goto fail;
    o_d = 16u + a16(4u * (n + 1u));
    o_s = o_d + a16(8u * n);
    need = o_s + a16(10u * n);
    if (!(blk = snapshot_block(l, k, need, buf, &kind)))
        goto fail;
    d = l->guest(l->user, blk, need);
    memmove(d + 16u, sr, 4u * (n + 1u));
    memmove(d + o_d, sd, 8u * n);
    memmove(d + o_s, ss, 10u * n);
#if MUT == 23
    memmove(d, rec, 16u);                            /* defect (M3): the record copied verbatim, pointers not fixed up */
#else
    put32(d + 0, blk + 16u);
    put32(d + 4, blk + o_d);
    put32(d + 8, blk + o_s);
    put32(d + 0xC, get32(rec + 0xC));                /* n and flags, verbatim */
#endif
    put32(w + 4, blk);                               /* re-point: the wrapper names the snapshot */
#if MUT == 25
    s_m5_sa[k][0] = get32(rec + 0); s_m5_sa[k][1] = get32(rec + 4); s_m5_sa[k][2] = get32(rec + 8);
#endif
    l->retained[k] = 1;
    l->src[k] = r;
    l->ret_copied++;
    return 1;
fail:
    retain_fallback(l, k, r, kind);                  /* +4 stays r: never 0 */
    return 0;
}

#if MUT == 25
/* defect (M5): a retained snapshot re-copied at the next exit from the array addresses it was first copied from */
static void recopy_retained(bo3_lanes *l, uint32_t k, uint32_t buf)
{
    uint8_t *d = l->guest(l->user, l->blk[k], l->cap[k]);
    const uint8_t *sr, *sd, *ss;
    uint32_t n, o_d, o_s;
    int kind;
    if (!d)
        return;
    n = get32(d + 0xC) & 0xFFFFu;
    o_d = 16u + a16(4u * (n + 1u));
    o_s = o_d + a16(8u * n);
    sr = src_range(l, buf, s_m5_sa[k][0], 4u * (n + 1u), &kind);
    sd = src_range(l, buf, s_m5_sa[k][1], 8u * n, &kind);
    ss = src_range(l, buf, s_m5_sa[k][2], 10u * n, &kind);
    if (sr && sd && ss) {
        memmove(d + 16u, sr, 4u * (n + 1u));
        memmove(d + o_d, sd, 8u * n);
        memmove(d + o_s, ss, 10u * n);
    }
}
#endif

static uint32_t retain_core(bo3_lanes *l, uint32_t route)
{
    const uint8_t *pb;
    uint8_t *wt;
    uint32_t buf, done = 0, fb0 = l->ret_fallback, sk0 = l->ret_skipped;

    l->last_route = route;
    pb = l->span ? l->span(l->user, route + BO3_ROUTE_BUF_OFF, 4u) : NULL;
    buf = pb ? get32(pb) : 0;
    if (!buf) {
        retain_fallback(l, 0, 0, BO3_LR_NO_BUFFER);   /* nothing copied; the backup mark may still act */
        return 0;
    }
    wt = l->guest(l->user, l->ext_va, 8u * l->ext_count);
    for (uint32_t k = 0; wt && k < l->ext_count; k++) {
        uint8_t *w = wt + 8u * k;
        uint32_t r = get32(w + 4);
        if (l->retained[k]) {
#if MUT == 25
            recopy_retained(l, k, buf);
#endif
            l->ret_skipped++;                        /* names the host block already: never re-copied */
            continue;
        }
        if (!r)
            continue;                                /* never installed: no holder can name it */
        if (k >= l->installed) {
            l->ret_stale++;                          /* an earlier fallback's old address: left (A1) */
            continue;
        }
        done += (uint32_t)snapshot_lane(l, k, w, r, buf);
    }
    l->gen_retained = l->gen_published;
    if (l->log && (done || l->ret_fallback != fb0))
        fprintf(l->log, "[LANES] lane lifetime: route 0x%08X, slot 0x%08X: %u extension lane(s) snapshotted, %u already "
                "retained, %u fell back (+4 kept); %u retained in all; %u block(s) allocated so far (%u bytes)\n",
                (unsigned)route, (unsigned)buf, (unsigned)done, (unsigned)(l->ret_skipped - sk0),
                (unsigned)(l->ret_fallback - fb0), (unsigned)bo3_lanes_retained(l), (unsigned)l->blk_allocs,
                (unsigned)l->blk_bytes);
    return done;
}

uint32_t bo3_lanes_retain(bo3_lanes *l, uint32_t route, int backup)
{
    if (!l || !l->configured)
        return 0;
    if (backup) {
        const uint8_t *pb;
        l->ret_acq_calls++;
        if (l->gen_retained == l->gen_published)
            return 0;                                /* the exit was seen (or nothing was published since) */
        pb = l->span ? l->span(l->user, route + BO3_ROUTE_BUF_OFF, 4u) : NULL;
        if (!pb || !get32(pb))
            return 0;                                /* the acquire failed: the loader retries; so does this */
        l->ret_acq_acted++;
        if (l->log && l->ret_acq_acted == 1)
            fprintf(l->log, "[LANES] lane lifetime: the race exit was not seen for the published route; snapshot at "
                    "the next load's ACQUIRE (before the file read)\n");
    } else {
        l->ret_exit_calls++;
    }
#if MUT == 21 || MUT == 27
    l->last_route = route;
    (void)retain_core;
    return 0;                                        /* defect (M1 / M7): no snapshot at the mark */
#else
    if (l->state != BO3_LANES_EXTENDED) {
        l->gen_retained = l->gen_published;          /* retail-only process: nothing to keep, nothing allocated */
        return 0;
    }
    {
        uint32_t done = retain_core(l, route);
        if (!backup && l->log)                  /* P3 (U5 G8): the reads served from snapshots so far */
            fprintf(l->log, "[LANES] lane lifetime at race exit (exit %u): served from retained snapshots %u (compat "
                    "reads since the start)\n", (unsigned)l->ret_exit_calls, (unsigned)l->served_retained);
        return done;
    }
#endif
}

uint32_t bo3_lanes_retained(const bo3_lanes *l)
{
    uint32_t n = 0;
    if (!l || l->state != BO3_LANES_EXTENDED)
        return 0;
    for (uint32_t k = 0; k < l->ext_count; k++)
        n += l->retained[k];
    return n;
}

static int names_retained(const bo3_lanes *l, uint32_t v)
{
    uint32_t k;
    if (l->state != BO3_LANES_EXTENDED || v < l->ext_va || ((v - l->ext_va) & 7u))
        return 0;
    k = (v - l->ext_va) >> 3;
    return k < l->ext_count && l->retained[k];
}

#define LD_LIST_COUNT 0x0012B79Cu      /* race world + : the racer list (probe v6 bm_ordprobe.c) */
#define LD_LIST       0x0012B7A8u
#define LD_LIST_MAX   6u
#define LD_NO_F_FROM  0x0013BDC0u      /* racer objects from here have no AI sub-object (+0x1BD4) */
#define LD_STAGE_OFF  0x00144384u
#define LD_COPY       0x0056781Cu      /* the copy holder */

static int rd32s(bo3_lanes *l, uint32_t va, uint32_t *v)
{
    const uint8_t *p = l->span ? l->span(l->user, va, 4u) : NULL;
    if (!p)
        return 0;
    *v = get32(p);
    return 1;
}

uint32_t bo3_lanes_holder_check(bo3_lanes *l, uint32_t world, uint32_t *checked, uint32_t *listed)
{
    uint32_t n = 0, hits = 0, seen = 0, v;
    if (checked) *checked = 0;
    if (listed) *listed = 0;
    if (!l || !l->span)
        return 0;
    if (!rd32s(l, world + LD_LIST_COUNT, &n) || n > LD_LIST_MAX)
        n = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t rc;
        if (!rd32s(l, world + LD_LIST + 4u * i, &rc) || !rc || rc < world || rc - world >= LD_STAGE_OFF || (rc & 3u))
            continue;
        if (rd32s(l, rc + 0x18C4u, &v)) { seen++; hits += (uint32_t)names_retained(l, v); }
        if (rc - world < LD_NO_F_FROM && rd32s(l, rc + 0x1BD4u, &v)) { seen++; hits += (uint32_t)names_retained(l, v); }
    }
    if (rd32s(l, LD_COPY, &v)) { seen++; hits += (uint32_t)names_retained(l, v); }
    if (checked) *checked = seen;
    if (listed) *listed = n;
    return hits;
}

void bo3_lanes_loaded_diag(bo3_lanes *l, uint32_t world)
{
    uint32_t checked, listed, hits;
    if (!l || l->state != BO3_LANES_EXTENDED || l->gen_diag == l->gen_published)
        return;
    l->gen_diag = l->gen_published;
    hits = bo3_lanes_holder_check(l, world, &checked, &listed);
    if (l->log)
        fprintf(l->log, "[LANES] lane lifetime at LOADED (load %u, %u lanes): %u extension wrapper(s) retained "
                "(snapshots), %u installed; holders naming a retained wrapper: %u of %u read (racer list %u, copy "
                "0x56781C)%s; snapshots %u, fallbacks %u (refused %u, allocation %u), %u block(s) %u bytes; served from "
                "retained snapshots %u\n",
                (unsigned)l->loads, (unsigned)l->last_count, (unsigned)bo3_lanes_retained(l), (unsigned)l->installed,
                (unsigned)hits, (unsigned)checked, (unsigned)listed, hits ? " - STALE HOLDERS (read the old lane's "
                "snapshot, in bounds)" : "", (unsigned)l->ret_copied, (unsigned)l->ret_fallback, (unsigned)l->ret_refused,
                (unsigned)l->ret_alloc_fail, (unsigned)l->blk_allocs, (unsigned)l->blk_bytes,
                (unsigned)l->served_retained);   /* P3 (U5 G8) */
}

void bo3_lanes_exit_summary(const bo3_lanes *l)
{
    if (!l || l->state != BO3_LANES_EXTENDED || !l->log)
        return;
    fprintf(l->log, "[LANES] lane lifetime at process exit: served from retained snapshots %u; %u race exit(s), %u "
            "snapshot(s), %u fallback(s), %u retained now\n", (unsigned)l->served_retained, (unsigned)l->ret_exit_calls,
            (unsigned)l->ret_copied, (unsigned)l->ret_fallback, (unsigned)bo3_lanes_retained(l));
    fflush(l->log);
}

/* ------------------------------------------------------------------------------------------------------------------ */

#if BO3_LANES_EXT_ENABLED
/* The one allocation attempt: after the build check, xbox_HeapAlloc for N wrappers, validated by bo3_lanes_init. */
static void ensure_extension(bo3_lanes *l)
{
    uint32_t va;
#if MUT == 9
    uint32_t n = BO3_LANE_EXT_COUNT;            /* defect: the requested entry count is ignored */
#else
    uint32_t n = bo3_lanes_entries(l);
#endif

#if MUT != 7
    if (l->alloc_tried)
        return;
#endif
    l->alloc_tried = 1;
    if (!l->build_check(l->user)) {
        l->alloc_result = BO3_LANES_UNSUPPORTED;
    } else if (!(va = l->alloc(l->user, 8u * n, 16u))) {
        l->alloc_result = BO3_LANES_NO_MEMORY;
    } else {
        l->alloc_result = bo3_lanes_init(l, l->guest, l->user, va, n, 1);
    }
    if (l->log)
        fprintf(l->log, "[LANES] lane extension: %s (%u entr%s = %u total lanes, at 0x%08X)\n",
                l->alloc_result == BO3_LANES_OK ? "allocated" :
                l->alloc_result == BO3_LANES_UNSUPPORTED ? "NOT allocated: unsupported game build" :
                l->alloc_result == BO3_LANES_NO_MEMORY ? "NOT allocated: the guest heap refused" :
                "NOT allocated: the allocation failed validation",
                (unsigned)n, n == 1 ? "y" : "ies", (unsigned)(BO3_LANE_LEGACY_MAX + n),
                (unsigned)(l->state == BO3_LANES_EXTENDED ? l->ext_va : 0));
}

static void begin_load(bo3_lanes *l, uint32_t count)
{
    uint32_t cap;

    l->loads++;
    l->gen_published++;                     /* design C 4.2 (3): the publish counter */
    l->last_count = count;
#if MUT != 3
    l->installed = 0;
#endif
    l->load_refused = 0;
    /* design C 4.4: NO store to +4 here. An extension wrapper keeps its retained snapshot (or, after a fallback, its old
       address) until the loader reinstalls the lane (bo3_lane_load below; the loader's own store follows). */
#if MUT == 22
    if (l->state == BO3_LANES_EXTENDED) {   /* defect (M2): released too early (the L5a clearing) */
        uint8_t *p = l->guest(l->user, l->ext_va, 8u * l->ext_count);
        for (uint32_t k = 0; p && k < l->ext_count; k++) {
            put32(p + 8u * k + 4u, 0);
            l->retained[k] = 0;
        }
    }
#endif
#if MUT == 27
    if (l->state == BO3_LANES_EXTENDED && l->last_route && l->gen_retained != l->gen_published)
        retain_core(l, l->last_route);      /* defect (M7): the snapshot taken at begin_load, after the file read */
#endif
    if ((int32_t)count > (int32_t)BO3_LANE_LEGACY_MAX) {
        if (l->state != BO3_LANES_EXTENDED)
            ensure_extension(l);
        cap = BO3_LANE_LEGACY_MAX + (l->state == BO3_LANES_EXTENDED ? l->ext_count : 0);
        if (count > cap) {
            if (l->log)
                fprintf(l->log, "[LANES] ERROR: the track has %u lanes, capacity %u total: lanes %u..%u are NOT installed "
                        "(their stores are refused; links to them are invalid; the track is unsupported)\n",
                        (unsigned)count, (unsigned)cap, (unsigned)cap, (unsigned)(count - 1));
#if P1_MUT != 11
            if (l->fail)                    /* PLATFORM-P1 (P-3): the game stops here (code 97), before any lane store */
                l->fail(l->user, count, cap, l->alloc_result);
#endif
        } else if (l->log && count == 65)
            fprintf(l->log, "[LANES] the track has 65 lanes: lane 64 on the extension\n");
        else if (l->log)
            fprintf(l->log, "[LANES] the track has %u lanes: lanes 64..%u on the extension (capacity %u total)\n",
                    (unsigned)count, (unsigned)(count - 1), (unsigned)cap);
    }
}
#endif

uint32_t bo3_lane_load(bo3_lanes *l, uint32_t index, uint32_t lane_count)
{
#if !BO3_LANES_EXT_ENABLED
    (void)l; (void)lane_count;
    return BO3_LANE_TABLE_VA + 8u * index;          /* the G8-L3b behaviour: the original store, every index */
#else
    uint32_t k;

    if (!l || !l->configured)
        return BO3_LANE_TABLE_VA + 8u * index;      /* not set up: the original store */
    if (index == 0)
        begin_load(l, lane_count);
#if MUT == 2
    if (index <= BO3_LANE_LEGACY_MAX)
#else
    if (index < BO3_LANE_LEGACY_MAX)
#endif
        return BO3_LANE_TABLE_VA + 8u * index;      /* lanes 0..63: the original store, byte for byte */
    k = index - BO3_LANE_LEGACY_MAX;
    if (l->state == BO3_LANES_EXTENDED && k < l->ext_count) {
        if (l->installed < k + 1u)
            l->installed = k + 1u;
        l->retained[k] = 0;                         /* reinstalled: the loader's store follows in this same call */
        return l->ext_va + 8u * k;
    }
    l->load_refused++;
#if MUT == 1
    return BO3_LANE_TABLE_VA + 8u * index;          /* defect: the original overflow store into the next table */
#else
    return 0;
#endif
#endif
}

uint32_t bo3_lane_wrapper(bo3_lanes *l, uint32_t index)
{
    if (index < BO3_LANE_LEGACY_MAX)
        return BO3_LANE_TABLE_VA + 8u * index;
    if (index == BO3_LANE_NONE)
        return BO3_LANE_NONE_VA;
#if MUT == 8
    if (l && l->state == BO3_LANES_EXTENDED && index - BO3_LANE_LEGACY_MAX < l->ext_count)
#else
    if (l && l->state == BO3_LANES_EXTENDED && index - BO3_LANE_LEGACY_MAX < l->installed)
#endif
        return l->ext_va + 8u * (index - BO3_LANE_LEGACY_MAX);
    if (l)
        l->refused++;
    return 0;
}

uint32_t bo3_lane_wrapper_compat(bo3_lanes *l, uint32_t index)
{
    uint32_t w = bo3_lane_wrapper(l, index);

    if (w)
        return w;
#if MUT != 24
    /* design C 4.5: a stale link byte naming a retained lane resolves to its wrapper (the old lane's snapshot), not to
       the overflow arithmetic. The API (bo3_lane_wrapper) still refuses it. */
    if (l && l->state == BO3_LANES_EXTENDED && index >= BO3_LANE_LEGACY_MAX && index < BO3_LANE_NONE &&
        index - BO3_LANE_LEGACY_MAX < l->ext_count && l->retained[index - BO3_LANE_LEGACY_MAX]) {
        l->served_retained++;
        return l->ext_va + 8u * (index - BO3_LANE_LEGACY_MAX);
    }
#endif
    return BO3_LANE_TABLE_VA + 8u * index;
}

uint32_t bo3_lane_wrapper_x8(bo3_lanes *l, uint32_t x)
{
    if (x & 7u)
        return BO3_LANE_TABLE_VA + x;
    return bo3_lane_wrapper_compat(l, x >> 3);
}

uint32_t bo3_lane_w(uint32_t index)
{
    return bo3_lane_wrapper_compat(&g_bo3_lanes, index);
}

uint32_t bo3_lane_w8(uint32_t x)
{
    return bo3_lane_wrapper_x8(&g_bo3_lanes, x);
}

uint32_t bo3_lane_load_gen(uint32_t index, uint32_t lane_count)
{
    return bo3_lane_load(&g_bo3_lanes, index, lane_count);
}

void bo3_lane_retain_gen(uint32_t route)
{
    (void)bo3_lanes_retain(&g_bo3_lanes, route, 0);
}

void bo3_lane_retain_acq_gen(uint32_t route)
{
    (void)bo3_lanes_retain(&g_bo3_lanes, route, 1);
}

#if defined(BO3_LANES_GAME) || defined(BO3_LANES_E4_SPAN)
/* The E4 window rule (bm_guest.c, runtime-validated in G8-E4): main RAM 0x10000 .. xbox_GetMappedSize(), or inside an
 * allocated contiguous block (xbox_ContiguousBlockSize). The track slot lives in the contiguous window (0x8xxxxxxx). */
#include "bm_guest.h"
extern ptrdiff_t g_xbox_mem_offset;

uint8_t *bo3_lanes_e4_span(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!bo3_guest_window(va, size))
        return NULL;
    return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}
#endif

#if defined(BO3_LANES_GAME) || defined(BO3_LANES_FAIL_TEST)
#include <stdlib.h>   /* _Exit */
/* PLATFORM-P1 (P-3): a track with more AI route lanes than this start's capacity. Before P1 the start continued: the
 * lanes past the capacity were not installed (bo3_lane_load returned 0 for their stores) while the track's links still
 * named them, and the generated consumers (bo3_lane_wrapper_compat / _x8) resolve such an index with the original
 * arithmetic 0x0060EA2C + 8 * index - for index >= 64 that is inside the race world (0x0060EA00 .. 0x00752E00), not a
 * lane wrapper. Like the GAMEDATA / unit-slot / STATIC guards (88 / 89 / 90): stop with a named reason instead. */
extern void xbox_crash_log_flush(unsigned max_ms);
extern void bo3_fatal(const char *title, const char *fmt, ...);

void bo3_lanes_game_fail(void *user, uint32_t count, uint32_t cap, int alloc_result)
{
    const char *why = count > BO3_LANE_TOTAL_MAX ? "more than the 255 lanes the track format can name" :
                      alloc_result == BO3_LANES_OK ? "the capacity the mods and plugins asked for" :
                      alloc_result == BO3_LANES_UNSUPPORTED ? "the lane extension is not verified for this game build" :
                      alloc_result == BO3_LANES_NO_MEMORY ? "the guest heap refused the lane extension" :
                      "the lane extension failed validation";
    (void)user;
    fprintf(stderr, "[LANES] FATAL: the track has %u AI route lanes; this start's lane capacity is %u total (%s). Lanes "
            "%u..%u cannot be installed and the track's links to them would be invalid, so the game stops here (code "
            "97). A mod that adds such a track declares [bmashup.capacity] lanes = %u (at most %u).\n", (unsigned)count,
            (unsigned)cap, why, (unsigned)cap, (unsigned)(count - 1), (unsigned)count, (unsigned)BO3_LANE_TOTAL_MAX);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    bo3_fatal("Takedawn: track has too many AI lanes",
              "The track being loaded has %u AI route lanes, but this start can hold %u (%s). Its links to the other "
              "lanes would be invalid, so the game will close.\n\nA mod that adds this track must declare "
              "[bmashup.capacity] lanes = %u in its mod.toml; or remove the track mod.", (unsigned)count, (unsigned)cap,
              why, (unsigned)count);
    fflush(stdout);
    fflush(stderr);
    xbox_crash_log_flush(1000);
    _Exit(97);
}
#endif

#ifdef BO3_LANES_GAME   /* the game build (CMake); tests use bo3_lanes_configure with stand-ins */
#include "recomp_types.h"
#include "kernel/xbox_memory_layout.h"

/* The retail NTSC-U default.xbe (title 0x4541005B): the same .rdata words bmashup.autopilot checks (bm_autopilot.c). */
static const struct { uint32_t va, word; } s_sig[] = {
    { 0x003B11A0u, 0x0018C470u },
    { 0x003B11A4u, 0x0018C510u },
    { 0x003A9ACCu, 0x00019FE0u },
    { 0x003A9AD0u, 0x0001A000u },
};

static uint8_t *game_guest(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!g_xbox_mem_offset || va < 0x00010000u || va >= BO3_GUEST_HEAP_HI || size > BO3_GUEST_HEAP_HI - va)
        return NULL;
    return (uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}

static uint32_t game_alloc(void *user, uint32_t size, uint32_t align)
{
    (void)user;
    return xbox_HeapAlloc(size, align);
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

static void lanes_exit_summary(void)
{
    bo3_lanes_exit_summary(&g_bo3_lanes);
}

void bo3_lanes_game_init(void)
{
    bo3_lanes_configure(&g_bo3_lanes, game_guest, game_alloc, game_build_ok, NULL, stderr);
    bo3_lanes_configure_span(&g_bo3_lanes, bo3_lanes_e4_span);
    bo3_lanes_configure_fail(&g_bo3_lanes, bo3_lanes_game_fail);   /* PLATFORM-P1 (P-3): overflow stops (97) */
    atexit(lanes_exit_summary);                 /* P3 (U5 G8): a normal exit (not the _Exit stops) */
}

/* The LOADED-time diagnostic, polled from the host frame hook (race_service.c, game thread): once per published track,
 * at the first update in the game module's running state with a stage (0x4D53B4 == 5, module vtable 0x3A9ACC, +0x1B8),
 * i.e. after the load's stage 0x17 (LOADED). Read only. */
void bo3_lanes_after_update(void)
{
    bo3_lanes *l = &g_bo3_lanes;
    uint32_t st, mod, vt, stage;
    if (l->state != BO3_LANES_EXTENDED || l->gen_diag == l->gen_published || !l->span)
        return;
    if (!rd32s(l, 0x004D53B4u, &st) || st != 5 || !rd32s(l, 0x004D5370u, &mod) || !rd32s(l, mod, &vt) ||
        vt != 0x003A9ACCu || !rd32s(l, mod + 0x1B8u, &stage) || !stage)
        return;
    bo3_lanes_loaded_diag(l, BO3_RACE_WORLD_VA);
}
#else
void bo3_lanes_game_init(void)
{
}

void bo3_lanes_after_update(void)
{
}
#endif
