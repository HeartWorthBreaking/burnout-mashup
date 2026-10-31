/*
 * bm_patch.c - PLATFORM-HK EXPERIMENTAL: "bmashup.patch" v1 (include/bmashup_patch.h, bm_patch.h).
 *
 * Requests are only recorded while the plugins start; nothing is written until bo3_bm_patch_close (before the guest's
 * first instruction). Every guest byte is read and written through bm_guest.c (the runtime's own mappings: main RAM up to
 * xbox_GetMappedSize, never folded or capped). The build is identified by the XBE image header the runtime copied to
 * 0x10000 (xbox_memory_layout.c: the SizeOfHeaders bytes of the file); its section table gives .rdata, the only region a
 * patch may touch (the initialised part: min(virtual size, raw size)). MUT=n (tests only) compiles one deliberate defect.
 *
 * main18 (v2): the byte-index switch tables of bm_patch_tables_gen.h (the census of THIS build) are a second writable class:
 * at start every listed table's index bytes and jump words are compared with the census in guest memory (a table that differs
 * is not offered); a request may write an index byte with a value < its switch's jump entries; the jump tables are
 * HOST_OWNED; other .text bytes are NOT_INDEX_TABLE. TABLE sites (bm_patch_sites.h) are bytes of verified tables.
 */
#include "bm_patch.h"

#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_hooks.h"
#include "bm_patch_sites.h"
#include "bm_patch_tables_gen.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0   /* 111 overlap not detected, 112 expected bytes not compared, 113 mapped range not checked, 114 no restore
                   when a plugin's later patch fails, 115 build signature not checked, 116 late request accepted;
                   main18 (v2): 121 the table census check skipped at start (every listed table offered), 122 a jump table
                   writable, 123 an index byte >= the switch's entries accepted (address form), 124 a TABLE site value
                   outside its bounds or not whole accepted (the address bound still refuses >= entries), 125 a site pair not all-or-nothing (the first kept when the second fails) */
#endif

#define PT_MAX       ((int)BM_PATCH_MAX_PATCHES)
#define PT_HDR_VA    0x00010000u
#define PT_HDR_MAX   0x00010000u                 /* as the runtime: a SizeOfHeaders above 64 KB is not used */
#define PT_HDR_FALLB 0x00001000u

extern ptrdiff_t g_xbox_mem_offset;

typedef struct {
    td_host *host;
    uint32_t va, size;
    uint8_t expected[BM_PATCH_MAX_BYTES], bytes[BM_PATCH_MAX_BYTES];
    uint32_t state;
    int32_t reason;
    int site;                                    /* index into k_bm_patch_sites, or -1 (address patch) */
    double value;
    int pair;                                    /* v2: the other patch of a site pair, or -1 */
    _Atomic uint32_t overwritten;
} pt_t;

static pt_t s_pt[PT_MAX];
static int s_npt;
static int s_open = 1, s_avail, s_site_ok[BM_PATCH_NSITES ? BM_PATCH_NSITES : 1];
static int s_tab_ok[BM_PATCH_NTABLES ? BM_PATCH_NTABLES : 1];   /* v2: the listed table matched the census in guest memory */
static uint32_t s_ntab_ok;
static uint64_t s_sig;
static uint32_t s_rd_lo, s_rd_hi;                 /* .rdata's initialised bytes [lo, hi) */
static uint32_t s_tx_lo, s_tx_hi;                 /* v2: .text's initialised bytes [lo, hi) */
static uint32_t s_thunk_lo, s_thunk_hi;           /* the kernel thunk table (entries + terminator): the runtime's */
static uint32_t s_applied, s_refused;

/* ---- guest access ---- */

static int g_read(uint32_t va, void *out, uint32_t n)
{
#if MUT == 113
    if (!g_xbox_mem_offset)
        return 0;
    memcpy(out, (const void *)((uintptr_t)g_xbox_mem_offset + va), n);   /* defect: no mapping check */
    return 1;
#else
    return bo3_guest_read(va, out, n);
#endif
}

static int mapped(uint32_t va, uint32_t n)
{
#if MUT == 113
    (void)va; (void)n;
    return 1;
#else
    return bo3_guest_window(va, n) == BO3_GUEST_RAM;
#endif
}

static int in_rdata(uint32_t va, uint32_t n)
{
    return va >= s_rd_lo && (uint64_t)va + n <= s_rd_hi;
}

/* ---- the build ---- */

static int identify(char *why, size_t wn)
{
    uint32_t base = 0, hsz = 0, nsec = 0, shva = 0;
    uint8_t buf[256];
    char magic[4] = {0};
    uint64_t h = 1469598103934665603ull;          /* FNV-1a 64 */
    if (!g_read(PT_HDR_VA, magic, 4) || memcmp(magic, "XBEH", 4) || !g_read(PT_HDR_VA + 0x104, &base, 4) ||
        !g_read(PT_HDR_VA + 0x108, &hsz, 4) || !g_read(PT_HDR_VA + 0x11C, &nsec, 4) || !g_read(PT_HDR_VA + 0x120, &shva, 4)) {
        snprintf(why, wn, "no XBE image header at 0x%08X", (unsigned)PT_HDR_VA);
        return 0;
    }
    if (base != PT_HDR_VA) {
        snprintf(why, wn, "the image base is 0x%08X, not 0x%08X", (unsigned)base, (unsigned)PT_HDR_VA);
        return 0;
    }
    if (hsz == 0 || hsz > PT_HDR_MAX)
        hsz = PT_HDR_FALLB;
    for (uint32_t off = 0; off < hsz; off += (uint32_t)sizeof buf) {
        uint32_t n = hsz - off < sizeof buf ? hsz - off : (uint32_t)sizeof buf;
        if (!g_read(PT_HDR_VA + off, buf, n)) {
            snprintf(why, wn, "the image header (%u bytes) is not mapped", (unsigned)hsz);
            return 0;
        }
        for (uint32_t k = 0; k < n; k++) {
            h ^= buf[k];
            h *= 1099511628211ull;
        }
    }
    {
        /* the kernel thunk table, decoded as the runtime does (xbox_memory_layout.c: retail key, else debug key) */
        uint32_t raw = 0, va, e = 1, cnt = 0;
        if (g_read(PT_HDR_VA + 0x158, &raw, 4)) {
            va = raw ^ 0x5B6D40B6u;
            if (va < PT_HDR_VA || va >= 0x04000000u)
                va = raw ^ 0xEFB1F152u;
            while (cnt < 378u && g_read(va + 4u * cnt, &e, 4) && e)
                cnt++;
            if (cnt) {
                s_thunk_lo = va;
                s_thunk_hi = va + 4u * (cnt + 1u);
            }
        }
    }
    if (nsec == 0 || nsec > 64 || shva < PT_HDR_VA || (uint64_t)shva + 56u * nsec > (uint64_t)PT_HDR_VA + hsz) {
        snprintf(why, wn, "the section table (%u at 0x%08X) is not inside the header", (unsigned)nsec, (unsigned)shva);
        return 0;
    }
    s_tx_lo = s_tx_hi = 0;
    for (uint32_t i = 0; i < nsec; i++) {                 /* v2: .text first (the section order of the image is not assumed) */
        uint32_t sh[6];
        char name[8] = {0};
        if (!g_read(shva + 56u * i, sh, sizeof sh))
            break;
        if (sh[5] < PT_HDR_VA || (uint64_t)sh[5] + 6u > (uint64_t)PT_HDR_VA + hsz || !g_read(sh[5], name, 6))
            continue;
        if (!memcmp(name, ".text", 6)) {
            uint32_t n = sh[2] < sh[4] ? sh[2] : sh[4];
            s_tx_lo = sh[1];
            s_tx_hi = sh[1] + n;
        }
    }
    for (uint32_t i = 0; i < nsec; i++) {
        uint32_t sh[6];
        char name[8] = {0};
        if (!g_read(shva + 56u * i, sh, sizeof sh))
            break;
        if (sh[5] < PT_HDR_VA || (uint64_t)sh[5] + 7u > (uint64_t)PT_HDR_VA + hsz || !g_read(sh[5], name, 7))
            continue;
        if (!memcmp(name, ".rdata", 7)) {
            uint32_t n = sh[2] < sh[4] ? sh[2] : sh[4];   /* min(virtual size, raw size): the bytes the XBE gives */
            s_rd_lo = sh[1];
            s_rd_hi = sh[1] + n;
            s_sig = h;
            return n > 0;
        }
    }
    snprintf(why, wn, "the XBE has no .rdata section");
    return 0;
}

/* ---- v2: the listed index tables ---- */

static int in_text(uint32_t va, uint32_t n)
{
    return s_tx_hi > s_tx_lo && va >= s_tx_lo && (uint64_t)va + n <= s_tx_hi;
}

/* the listed table whose INDEX bytes hold [va, va + n) wholly, or -1 */
static int table_of(uint32_t va, uint32_t n)
{
    for (uint32_t t = 0; t < BM_PATCH_NTABLES; t++)
        if (va >= k_bm_patch_tables[t].va && (uint64_t)va + n <= (uint64_t)k_bm_patch_tables[t].va + k_bm_patch_tables[t].len)
            return (int)t;
    return -1;
}

/* 1 when [va, va + n) overlaps a listed JUMP table */
static int touches_jumps(uint32_t va, uint32_t n)
{
    for (uint32_t t = 0; t < BM_PATCH_NTABLES; t++) {
        uint32_t lo = k_bm_patch_tables[t].jt, hi = lo + 4u * k_bm_patch_tables[t].entries;
        if (va < hi && lo < va + n)
            return 1;
    }
    return 0;
}

/* at start: a listed table is offered only when its index bytes and jump words in guest memory are the census's (this
 * build), inside .text */
static int table_verify(uint32_t t)
{
    const bm_patch_table *b = &k_bm_patch_tables[t];
    uint8_t cur[BM_PATCH_TABLE_MAX_LEN];
    uint32_t w[BM_PATCH_TABLE_MAX_ENTRIES];
#if MUT == 121
    (void)b; (void)cur; (void)w;
    return 1;                                            /* defect: the census is not checked against the running build */
#else
    if (b->len == 0 || b->len > BM_PATCH_TABLE_MAX_LEN || b->entries < 2 || b->entries > BM_PATCH_TABLE_MAX_ENTRIES)
        return 0;
    if (!in_text(b->va, b->len) || !in_text(b->jt, 4u * b->entries) || !mapped(b->va, b->len) || !mapped(b->jt, 4u * b->entries))
        return 0;
    if (!g_read(b->va, cur, b->len) || memcmp(cur, b->shipped, b->len))
        return 0;
    if (!g_read(b->jt, w, 4u * b->entries) || memcmp(w, b->jump_words, 4u * b->entries))
        return 0;
    for (uint32_t k = 0; k < b->len; k++)
        if (cur[k] >= b->entries)
            return 0;
    return 1;
#endif
}

/* ---- diagnostics ---- */

static const char *who(const td_host *host)
{
    const char *id = host ? bo3_plugins_host_id(host) : NULL;
    return id && id[0] ? id : "?";
}

static const char *TD_CALL pt_result_text(int32_t code)
{
    static const char *const k[] = {"OK", "BAD_ARG", "CLOSED", "UNKNOWN_SITE", "SITE_UNVERIFIED", "OUT_OF_BOUNDS",
                                    "BUILD_MISMATCH", "UNMAPPED", "NOT_DATA", "EXPECTED_MISMATCH", "CONFLICT",
                                    "OVERLAP_SELF", "FULL", "NOT_OWNER", "UNAVAILABLE", "RESTORED", "HOST_OWNED",
                                    "NOT_INDEX_TABLE"};
    return code >= 0 && code < (int32_t)(sizeof k / sizeof k[0]) ? k[code] : "UNKNOWN_RESULT";
}

static void what(const pt_t *p, char *out, size_t n)
{
    if (p->site >= 0)
        snprintf(out, n, "site %s = %g", k_bm_patch_sites[p->site].name, p->value);
    else
        snprintf(out, n, "bytes 0x%08X + %u", (unsigned)p->va, (unsigned)p->size);
}

/* ---- requests ---- */

/* checks a candidate patch (p: host, va, size, expected, bytes, site) against the build, the mappings and the other
 * patches; *other = the overlapped patch on CONFLICT / OVERLAP_SELF */
static int32_t check(const pt_t *p, int *other)
{
    uint8_t cur[BM_PATCH_MAX_BYTES];
    *other = -1;
    if (!mapped(p->va, p->size))
        return BM_PATCH_UNMAPPED;
    if (in_rdata(p->va, p->size)) {
        if (p->va < s_thunk_hi && s_thunk_lo < p->va + p->size)
            return BM_PATCH_HOST_OWNED;
    } else {
        /* v2: .text bytes only inside a listed, verified index table, each value < its switch's jump entries */
        int t;
        if (touches_jumps(p->va, p->size)) {
#if MUT != 122
            return BM_PATCH_HOST_OWNED;                  /* (MUT 122, defect: a jump table goes on as writable) */
#endif
        } else {
            t = table_of(p->va, p->size);
            if (t >= 0 && s_tab_ok[t]) {
#if MUT != 123
                for (uint32_t k = 0; k < p->size; k++)
                    if (p->bytes[k] >= k_bm_patch_tables[t].entries)
                        return BM_PATCH_OUT_OF_BOUNDS;
#endif
            } else if (t >= 0) {
                return BM_PATCH_NOT_INDEX_TABLE;         /* a listed table this build does not match (not offered) */
            } else {                                     /* every other byte outside .rdata: v1's answer, unchanged */
                return BM_PATCH_NOT_DATA;
            }
        }
    }
    if (!g_read(p->va, cur, p->size))
        return BM_PATCH_UNMAPPED;
#if MUT != 112
    if (memcmp(cur, p->expected, p->size))
        return BM_PATCH_EXPECTED_MISMATCH;
#endif
#if MUT != 111
    for (int k = 0; k < s_npt; k++) {
        const pt_t *q = &s_pt[k];
        if (q->state != BM_PATCH_PENDING && q->state != BM_PATCH_APPLIED)
            continue;
        if (p->va < q->va + q->size && q->va < p->va + p->size) {
            *other = k;
            return q->host == p->host ? BM_PATCH_OVERLAP_SELF : BM_PATCH_CONFLICT;
        }
    }
#endif
    if (s_npt == PT_MAX)
        return BM_PATCH_FULL;
    return BM_PATCH_OK;
}

static int32_t accept_or_refuse(const pt_t *cand, uint32_t *handle)
{
    int other;
    char w[96], ow[96];
    int32_t rc = check(cand, &other);
    what(cand, w, sizeof w);
    if (rc != BM_PATCH_OK) {
        if (other >= 0) {
            what(&s_pt[other], ow, sizeof ow);
            fprintf(stderr, "[PATCH] %s: %s refused: %s (overlaps %s's %s)\n", who(cand->host), w, pt_result_text(rc),
                    who(s_pt[other].host), ow);
        } else {
            fprintf(stderr, "[PATCH] %s: %s refused: %s\n", who(cand->host), w, pt_result_text(rc));
        }
        return rc;
    }
    s_pt[s_npt] = *cand;
    s_pt[s_npt].state = BM_PATCH_PENDING;
    s_pt[s_npt].reason = BM_PATCH_OK;
    atomic_store(&s_pt[s_npt].overwritten, 0);
    *handle = (uint32_t)++s_npt;
    fprintf(stderr, "[PATCH] %s: %s accepted (applied when the plugins' start ends)\n", who(cand->host), w);
    return BM_PATCH_OK;
}

static int32_t pre(td_host *host, const void *req, uint32_t *handle)
{
    if (handle)
        *handle = 0;
    if (!host || !req || !handle)
        return BM_PATCH_BAD_ARG;
#if MUT != 116
    if (!s_open)
        return BM_PATCH_CLOSED;
#endif
    if (!s_avail)
        return BM_PATCH_UNAVAILABLE;
    return BM_PATCH_OK;
}

static int32_t refuse_early(td_host *host, const char *w, int32_t rc)
{
    fprintf(stderr, "[PATCH] %s: %s refused: %s\n", host ? who(host) : "?", w, pt_result_text(rc));
    return rc;
}

/* a published site's candidate patch (not yet checked against the build / the other patches) */
static int32_t site_cand(td_host *host, uint32_t index, double value, pt_t *c)
{
    const bm_patch_site *s = &k_bm_patch_sites[index];
    int whole = s->type == BM_PATCH_U32 || s->type == BM_PATCH_U8_INDEX, bad;
    if (!s_site_ok[index])
        return BM_PATCH_SITE_UNVERIFIED;
    bad = !isfinite(value) || value < s->min || value > s->max || (whole && value != floor(value));
#if MUT == 124
    if (s->type == BM_PATCH_U8_INDEX)                    /* defect: any byte value, fractions truncated */
        bad = !isfinite(value) || value < 0.0 || value > 255.0;
#endif
    if (bad)
        return BM_PATCH_OUT_OF_BOUNDS;
    memset(c, 0, sizeof *c);
    c->host = host;
    c->va = s->va;
    c->site = (int)index;
    c->value = value;
    c->pair = -1;
    if (s->type == BM_PATCH_U8_INDEX) {
        c->size = 1;
        c->expected[0] = (uint8_t)s->original;
        c->bytes[0] = (uint8_t)value;
    } else {
        c->size = 4;
        memcpy(c->expected, &s->original, 4);
        if (s->type == BM_PATCH_F32) {
            float f = (float)value;
            memcpy(c->bytes, &f, 4);
        } else {
            uint32_t u = (uint32_t)value;
            memcpy(c->bytes, &u, 4);
        }
    }
    return BM_PATCH_OK;
}

static int32_t TD_CALL pt_request_site(td_host *host, uint32_t index, double value, uint32_t *handle)
{
    pt_t c;
    char w[96];
    int32_t rc = pre(host, &index, handle);
    const bm_patch_site *s = index < BM_PATCH_NSITES ? &k_bm_patch_sites[index] : NULL;
    snprintf(w, sizeof w, "site %s = %g", s ? s->name : "(unknown)", value);
    if (rc != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    if (!s)
        return refuse_early(host, w, BM_PATCH_UNKNOWN_SITE);
    if ((rc = site_cand(host, index, value, &c)) != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    return accept_or_refuse(&c, handle);
}

/* v2: two sites, one value, both or neither */
static int32_t TD_CALL pt_request_site_pair(td_host *host, uint32_t ia, uint32_t ib, double value, uint32_t *handle)
{
    pt_t a, b;
    char w[160];
    uint32_t ha = 0, hb = 0;
    int32_t rc = pre(host, &ia, handle);
    const bm_patch_site *sa = ia < BM_PATCH_NSITES ? &k_bm_patch_sites[ia] : NULL;
    const bm_patch_site *sb = ib < BM_PATCH_NSITES ? &k_bm_patch_sites[ib] : NULL;
    snprintf(w, sizeof w, "site pair %s + %s = %g", sa ? sa->name : "(unknown)", sb ? sb->name : "(unknown)", value);
    if (rc != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    if (!sa || !sb)
        return refuse_early(host, w, BM_PATCH_UNKNOWN_SITE);
    if (ia == ib)
        return refuse_early(host, w, BM_PATCH_BAD_ARG);
    if ((rc = site_cand(host, ia, value, &a)) != BM_PATCH_OK || (rc = site_cand(host, ib, value, &b)) != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    if (s_npt + 2 > PT_MAX)
        return refuse_early(host, w, BM_PATCH_FULL);
    if ((rc = accept_or_refuse(&a, &ha)) != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    if ((rc = accept_or_refuse(&b, &hb)) != BM_PATCH_OK) {
#if MUT != 125
        s_npt--;                                         /* the first of the pair is taken back: never one alone */
        memset(&s_pt[s_npt], 0, sizeof s_pt[s_npt]);
        *handle = 0;
#else
        *handle = ha;                                    /* defect: the first stays accepted */
#endif
        return refuse_early(host, w, rc);
    }
    s_pt[ha - 1].pair = (int)hb - 1;
    s_pt[hb - 1].pair = (int)ha - 1;
    *handle = ha;
    fprintf(stderr, "[PATCH] %s: %s accepted as one unit\n", who(host), w);
    return BM_PATCH_OK;
}

static int32_t TD_CALL pt_request_bytes(td_host *host, const bm_patch_bytes *req, uint32_t *handle)
{
    pt_t c;
    char w[96];
    int32_t rc = pre(host, req, handle);
    snprintf(w, sizeof w, "bytes 0x%08X + %u", req ? (unsigned)req->va : 0u, req ? (unsigned)req->size : 0u);
    if (rc != BM_PATCH_OK)
        return refuse_early(host, w, rc);
    if (req->struct_size < offsetof(bm_patch_bytes, bytes) + sizeof req->bytes || req->size == 0 ||
        req->size > BM_PATCH_MAX_BYTES || !req->expected || !req->bytes || req->reserved)
        return refuse_early(host, w, BM_PATCH_BAD_ARG);
#if MUT != 115
    if (req->build_signature != s_sig)
        return refuse_early(host, w, BM_PATCH_BUILD_MISMATCH);
#endif
    memset(&c, 0, sizeof c);
    c.host = host;
    c.va = req->va;
    c.size = req->size;
    c.site = -1;
    c.pair = -1;
    memcpy(c.expected, req->expected, req->size);
    memcpy(c.bytes, req->bytes, req->size);
    return accept_or_refuse(&c, handle);
}

static uint32_t TD_CALL pt_site_count(td_host *host)
{
    return host ? BM_PATCH_NSITES : 0;
}

static int32_t TD_CALL pt_site_info(td_host *host, uint32_t index, bm_patch_site_info *out)
{
    bm_patch_site_info s;
    uint32_t room;
    float f;
    if (!host || !out || out->struct_size < 8)
        return BM_PATCH_BAD_ARG;
    if (index >= BM_PATCH_NSITES)
        return BM_PATCH_UNKNOWN_SITE;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    snprintf(s.name, sizeof s.name, "%s", k_bm_patch_sites[index].name);
    s.type = k_bm_patch_sites[index].type;
    s.verified = (uint32_t)s_site_ok[index];
    memcpy(&f, &k_bm_patch_sites[index].original, 4);
    s.original = s.type == BM_PATCH_F32 ? (double)f : (double)k_bm_patch_sites[index].original;
    s.min = k_bm_patch_sites[index].min;
    s.max = k_bm_patch_sites[index].max;
    /* v2 */
    s.kind = k_bm_patch_sites[index].kind == BM_PATCH_SITE_TABLE ? BM_PATCH_SITE_TABLE : BM_PATCH_SITE_RDATA;
    if (s.kind == BM_PATCH_SITE_TABLE) {
        int t = table_of(k_bm_patch_sites[index].va, 1);
        s.targets = t >= 0 ? k_bm_patch_tables[t].entries : 0;
        snprintf(s.reader, sizeof s.reader, "%s", t >= 0 ? k_bm_patch_tables[t].reader : "");
    }
    snprintf(s.meaning, sizeof s.meaning, "%s", k_bm_patch_sites[index].meaning ? k_bm_patch_sites[index].meaning : "");
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_PATCH_OK;
}

static int32_t TD_CALL pt_find_site(td_host *host, const char *name, uint32_t *index)
{
    if (!host || !name || !index)
        return BM_PATCH_BAD_ARG;
    for (uint32_t i = 0; i < BM_PATCH_NSITES; i++)
        if (!strcmp(name, k_bm_patch_sites[i].name)) {
            *index = i;
            return BM_PATCH_OK;
        }
    return BM_PATCH_UNKNOWN_SITE;
}

static int32_t TD_CALL pt_build_signature(td_host *host, uint64_t *signature)
{
    if (!host || !signature)
        return BM_PATCH_BAD_ARG;
    if (!s_avail)
        return BM_PATCH_UNAVAILABLE;
    *signature = s_sig;
    return BM_PATCH_OK;
}

static int32_t TD_CALL pt_status(td_host *host, uint32_t handle, bm_patch_status *out)
{
    bm_patch_status s;
    uint32_t room;
    if (!host || !out || out->struct_size < 8 || handle == 0 || handle > (uint32_t)s_npt)
        return BM_PATCH_BAD_ARG;
    if (s_pt[handle - 1].host != host)
        return BM_PATCH_NOT_OWNER;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    s.state = s_pt[handle - 1].state;
    s.reason = s_pt[handle - 1].reason;
    s.overwritten = atomic_load(&s_pt[handle - 1].overwritten);
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_PATCH_OK;
}

static const bm_patch_api s_api = {
    (uint32_t)sizeof(bm_patch_api), BM_PATCH_VERSION, pt_site_count, pt_site_info, pt_find_site, pt_request_site,
    pt_build_signature, pt_request_bytes, pt_status, pt_result_text, pt_request_site_pair
};

const bm_patch_api *bo3_bm_patch_api(void)
{
    return &s_api;
}

/* ---- apply (once, before the guest runs) ---- */

/* one plugin's patches, all or nothing */
static void apply_owner(td_host *host)
{
    int idx[PT_MAX], n = 0, written = 0, bad = -1;
    int32_t why = BM_PATCH_OK;
    char w[96];
    for (int k = 0; k < s_npt; k++)
        if (s_pt[k].host == host && s_pt[k].state == BM_PATCH_PENDING)
            idx[n++] = k;
    for (int j = 0; j < n && bad < 0; j++) {
        pt_t *p = &s_pt[idx[j]];
        uint8_t cur[BM_PATCH_MAX_BYTES];
        if (!mapped(p->va, p->size) || !g_read(p->va, cur, p->size))
            why = BM_PATCH_UNMAPPED;
#if MUT != 112
        else if (memcmp(cur, p->expected, p->size))
            why = BM_PATCH_EXPECTED_MISMATCH;
#endif
        else if (!bo3_guest_write(p->va, p->bytes, p->size) || !g_read(p->va, cur, p->size) || memcmp(cur, p->bytes, p->size))
            why = BM_PATCH_UNMAPPED;
        if (why != BM_PATCH_OK)
            bad = j;
        else
            written = j + 1;
    }
    if (bad < 0) {
        for (int j = 0; j < n; j++) {
            s_pt[idx[j]].state = BM_PATCH_APPLIED;
            s_applied++;
            what(&s_pt[idx[j]], w, sizeof w);
            fprintf(stderr, "[PATCH] %s: %s applied\n", who(host), w);
        }
        return;
    }
#if MUT != 114
    for (int j = written - 1; j >= 0; j--)                /* put back what this plugin had written, newest first */
        bo3_guest_write(s_pt[idx[j]].va, s_pt[idx[j]].expected, s_pt[idx[j]].size);
#else
    (void)written;
#endif
    for (int j = 0; j < n; j++) {
        s_pt[idx[j]].state = BM_PATCH_REFUSED;
        s_pt[idx[j]].reason = j == bad ? why : BM_PATCH_RESTORED;
        s_refused++;
    }
    what(&s_pt[idx[bad]], w, sizeof w);
    fprintf(stderr, "[PATCH] %s: %s refused at apply time: %s; the plugin's %d patch(es) are not applied (%d restored)\n",
            who(host), w, pt_result_text(why), n, written);
}

uint32_t bo3_patch_readback(void)
{
    uint32_t changed = 0;
    for (int k = 0; k < s_npt; k++) {
        pt_t *p = &s_pt[k];
        uint8_t cur[BM_PATCH_MAX_BYTES];
        char w[96];
        if (p->state != BM_PATCH_APPLIED)
            continue;
        if (g_read(p->va, cur, p->size) && !memcmp(cur, p->bytes, p->size))
            continue;
        changed++;
        if (atomic_fetch_add(&p->overwritten, 1) == 0) {
            what(p, w, sizeof w);
            fprintf(stderr, "[PATCH] %s: %s is no longer in place (something else wrote there); counted, said once\n",
                    who(p->host), w);
        }
    }
    return changed;
}

static void on_load_done(const bm_hook_ctx *ctx, void *user)
{
    (void)ctx;
    (void)user;
    if (s_applied)
        (void)bo3_patch_readback();
}

void bo3_bm_patch_init(void)
{
    char why[160] = "";
    memset(s_site_ok, 0, sizeof s_site_ok);
    memset(s_tab_ok, 0, sizeof s_tab_ok);
    s_avail = g_xbox_mem_offset && identify(why, sizeof why);
    if (!s_avail) {
        fprintf(stderr, "[PATCH] build not identified (%s): bmashup.patch refuses every request in this run\n", why);
    } else {
        fprintf(stderr, "[PATCH] build signature %016llX, .rdata 0x%08X..0x%08X\n", (unsigned long long)s_sig,
                (unsigned)s_rd_lo, (unsigned)s_rd_hi);
        s_ntab_ok = 0;
        for (uint32_t t = 0; t < BM_PATCH_NTABLES; t++)  /* v2: the census's index tables, checked in guest memory */
            s_ntab_ok += (uint32_t)(s_tab_ok[t] = table_verify(t));
        fprintf(stderr, "[PATCH] index tables: %u of %u listed tables match this build (census %s)\n", (unsigned)s_ntab_ok,
                (unsigned)BM_PATCH_NTABLES, BM_PATCH_TABLES_CENSUS);
        for (uint32_t i = 0; i < BM_PATCH_NSITES; i++) {
            const bm_patch_site *s = &k_bm_patch_sites[i];
            uint32_t cur = 0;
            if (s->kind == BM_PATCH_SITE_TABLE) {
                int t = table_of(s->va, 1);
                uint8_t b = 0;
                s_site_ok[i] = t >= 0 && (uint32_t)t < BM_PATCH_NTABLES && k_bm_patch_tables[t].va == s->table_va &&
                               s_tab_ok[t] && s->max < (double)k_bm_patch_tables[t].entries && g_read(s->va, &b, 1) &&
                               b == (uint8_t)s->original;
                cur = b;
            } else {
                s_site_ok[i] = mapped(s->va, 4) && in_rdata(s->va, 4) && g_read(s->va, &cur, 4) && cur == s->original;
            }
            if (!s_site_ok[i])
                fprintf(stderr, "[PATCH] site %s not verified (0x%08X holds 0x%08X, shipped 0x%08X): never written\n",
                        s->name, (unsigned)s->va, (unsigned)cur, (unsigned)s->original);
        }
    }
    (void)bo3_hk_host_observe(BM_HOOK_LOAD_DONE, on_load_done, NULL);
    bo3_plugins_service(BM_PATCH_SERVICE, BM_PATCH_VERSION, &s_api);
}

void bo3_bm_patch_close(void)
{
    if (!s_open)
        return;
    s_open = 0;
    for (int k = 0; k < s_npt; k++) {                     /* plugin by plugin, in the order of their first request */
        int first = 1;
        for (int j = 0; j < k; j++)
            if (s_pt[j].host == s_pt[k].host)
                first = 0;
        if (first)
            apply_owner(s_pt[k].host);
    }
    if (s_npt)
        fprintf(stderr, "[PATCH] requests closed: %u applied, %u refused at apply time\n", (unsigned)s_applied,
                (unsigned)s_refused);
}
