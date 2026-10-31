/*
 * bm_rowx.c - gp slice mega1 EXPERIMENTAL: the mesh-block material row extension ("BMRX").
 *
 * Retail format: a mesh block holds at most 83 material rows (+0x84 s16[83]; every PVS chunk rowsA / rowsB [83]). A track
 * composed from several retail tracks needs more rows where a unit's 17-unit window spans two sources (gp mega: up to 127).
 * A data mod keeps <= 83 rows in the retail arrays (what a host without this extension draws) and puts the complete row list
 * in an extension the generated draw code reads through bo3_rowx_gen.h:
 *
 *   block + 0xC64  'B' 'M' 'R' 'X'    (retail: 0xC64..0xC8F is zero padding after the 17 chunks)
 *   block + 0xC68  u32 ext offset (block-relative)
 *   block + 0xC6C  u8 version (1), u8 nv (virtual rows, 1..127), u8 p1v (virtual pass-1 rows, <= nv), u8 E (extension rows)
 *   ext            u8 vmap[nv] (virtual row -> physical row: < 83 the retail arrays, 83 + i extension row i) | pad to 2 |
 *                  s16 mats[E] | s8 rowsA[17][E] | s8 rowsB[17][E]
 *
 * Validation (every read; a few compares): magic, version 1, 1 <= nv <= 127, p1v <= nv, E <= 127, the whole extension inside
 * the block (size at +0x08 <= 0x30000), every vmap entry either < min(83, legacy rows) or 83..83+E-1 (checked once per block
 * address + content stamp). An invalid header -> the retail bytes (as without the extension) and one log line.
 * Thread: the game's render path only (the callers); no state but counters.
 */
#include <stdint.h>
#include <stdio.h>

#include "bo3_rowx_gen.h"

#define RX_MAGIC 0x58524D42u        /* "BMRX" little-endian */
#define RX_HDR 0xC64u
#define RX_LEGACY 83u
#define RX_CHUNKS 17u
#define RX_CHUNK 0xA9u

#ifndef MUT
#define MUT 0
#endif

/* guest reads (game: the generated code's MEM macros; tests: bm_rowx_test_mem) */
#ifdef BO3_ROWX_GAME
#include "recomp_types.h"
static uint8_t rd8(uint32_t va) { return MEM8(va); }
#else
extern uint8_t bm_rowx_test_rd8(uint32_t va);
static uint8_t rd8(uint32_t va) { return bm_rowx_test_rd8(va); }
#endif

static uint32_t rd16(uint32_t va) { return (uint32_t)rd8(va) | ((uint32_t)rd8(va + 1u) << 8); }
static uint32_t rd32(uint32_t va) { return rd16(va) | (rd16(va + 2u) << 16); }

/* counters (diagnostics; read by tests and the first-use log line) */
volatile uint32_t bm_rowx_ext_blocks_seen, bm_rowx_invalid, bm_rowx_reads;
static uint32_t s_last_blk, s_last_unit, s_last_ext, s_last_ok, s_logged_ok, s_logged_bad;

typedef struct {
    uint32_t ext, nv, p1v, e;
} rx_hdr;

static int header(uint32_t blk, rx_hdr *h)
{
    if (rd32(blk + RX_HDR) != RX_MAGIC)
        return 0;
    uint32_t size = rd32(blk + 8u);
    h->ext = rd32(blk + RX_HDR + 4u);
    uint32_t ver = rd8(blk + RX_HDR + 8u);
    h->nv = rd8(blk + RX_HDR + 9u);
    h->p1v = rd8(blk + RX_HDR + 10u);
    h->e = rd8(blk + RX_HDR + 11u);
    uint32_t legacy = rd8(blk + 0x71u);
    uint32_t need = h->nv + (h->nv & 1u) + 2u * h->e + 2u * RX_CHUNKS * h->e;
    int ok = ver == 1u && h->nv >= 1u && h->nv <= 127u && h->p1v <= h->nv && h->e <= 127u && legacy <= RX_LEGACY &&
             size <= 0x30000u && h->ext >= 0xC90u && h->ext <= size && need <= size - h->ext;
#if MUT == 1
    ok = ver == 1u;                 /* mutant: no bounds checks */
#endif
    uint32_t unit = rd32(blk + 4u);
    if (ok && (blk != s_last_blk || unit != s_last_unit || h->ext != s_last_ext || !s_last_ok)) {   /* vmap check once per loaded block */
        for (uint32_t v = 0; v < h->nv && ok; v++) {
            uint32_t p = rd8(blk + h->ext + v);
            ok = p < legacy || (p >= RX_LEGACY && p < RX_LEGACY + h->e);
        }
        s_last_blk = blk;
        s_last_unit = unit;
        s_last_ext = h->ext;
        s_last_ok = ok;
        if (ok) {
            bm_rowx_ext_blocks_seen++;
            if (!s_logged_ok) {
                s_logged_ok = 1;
                fprintf(stderr, "[ROWX] mesh row extension in use: unit block 0x%08X, %u rows (%u pass-1, %u extension, %u "
                        "retail)\n", (unsigned)blk, (unsigned)h->nv, (unsigned)h->p1v, (unsigned)h->e, (unsigned)legacy);
            }
        }
    }
    if (!ok) {
        bm_rowx_invalid++;
        if (!s_logged_bad) {
            s_logged_bad = 1;
            fprintf(stderr, "[ROWX] invalid row extension header in unit block 0x%08X: the retail rows are used\n",
                    (unsigned)blk);
        }
        return 0;
    }
    return 1;
}

#ifdef BO3_ROWX_GAME
/* STREAM TRACE (diagnostic, read only, off unless BMASHUP_STREAM_TRACE=1): at most every 250 ms of draw calls, view 0
 * (0x7397C8, KB STREAMING s1): low-ring centre / camera slots (+0x04 / +0x4C), the units in the 18 low slots (+0x17C) and the
 * 10 full slots (+0x154) read from each block's +0x04 (0xFFFF = empty / not a unit block). Lets the runtime report measure
 * the units resident ahead of the camera unit. Changes nothing. */
#include <stdlib.h>
#include <string.h>
#include <windows.h>
static int s_trace = -1;
static ULONGLONG s_trace_t;
static uint32_t s_trace_n;

static uint32_t unit_of_block(uint32_t b)
{
    /* a unit block: +0x00 = 1, +0x04 = unit index (< 0x8000), +0x08 = block size (KB MESH_AND_COLLISION s1) */
    if (b < 0x00010000u)
        return 0xFFFFu;
    if (rd32(b + 4u) < 0x8000u && rd32(b + 8u) >= 0x1000u && rd32(b + 8u) <= 0x30000u)
        return rd32(b + 4u);
    return 0xFFFEu;
}

static void raw_once(uint32_t v)
{
    static int done;
    if (done)
        return;
    done = 1;
    for (uint32_t i = 0; i < 3u; i++) {
        uint32_t p = rd32(v + 0x17Cu + 4u * i);
        fprintf(stderr, "[STREAMX] raw low slot %u: ptr 0x%08X words %08X %08X %08X %08X\n", (unsigned)i, (unsigned)p,
                p >= 0x10000u ? (unsigned)rd32(p) : 0u, p >= 0x10000u ? (unsigned)rd32(p + 4u) : 0u,
                p >= 0x10000u ? (unsigned)rd32(p + 8u) : 0u, p >= 0x10000u ? (unsigned)rd32(p + 0xCu) : 0u);
    }
}

static void trace_tick(void)
{
    if (s_trace < 0) {
        const char *e = getenv("BMASHUP_STREAM_TRACE");
        s_trace = e && strcmp(e, "1") == 0;
        if (s_trace)
            fprintf(stderr, "[STREAMX] stream trace on (view 0, every 250 ms of drawing)\n");
    }
    if (!s_trace)
        return;
    ULONGLONG now = GetTickCount64();
    if (now - s_trace_t < 250u)
        return;
    s_trace_t = now;
    const uint32_t v = 0x7397C8u;
    raw_once(v);
    char line[512];
    int k = snprintf(line, sizeof line, "[STREAMX] n %u t %llu lc %u fc %u cam %u low", (unsigned)s_trace_n++,
                     (unsigned long long)now, (unsigned)rd32(v + 4u), (unsigned)rd32(v + 0u), (unsigned)rd32(v + 0x4Cu));
    for (uint32_t i = 0; i < 18u && k < (int)sizeof line - 8; i++)
        k += snprintf(line + k, sizeof line - k, " %u", (unsigned)unit_of_block(rd32(v + 0x17Cu + 4u * i)));
    k += snprintf(line + k, sizeof line - k, " full");
    for (uint32_t i = 0; i < 10u && k < (int)sizeof line - 8; i++)
        k += snprintf(line + k, sizeof line - k, " %u", (unsigned)unit_of_block(rd32(v + 0x154u + 4u * i)));
    fprintf(stderr, "%s\n", line);
}
#else
static void trace_tick(void) {}
#endif

uint32_t bo3_rowx_gen_count(uint32_t blk, uint32_t field)
{
    rx_hdr h;
    if (field == 0x71u)
        trace_tick();
    if (header(blk, &h))
        return field == 0x73u ? h.p1v : h.nv;
    return (uint32_t)(int32_t)(int8_t)rd8(blk + field);
}

uint32_t bo3_rowx_gen_row(uint32_t blk, uint32_t lin, uint32_t row, uint32_t off)
{
    rx_hdr h;
    if (!header(blk, &h))
        return rd8(lin + blk + off);                 /* the retail read, byte for byte */
    bm_rowx_reads++;
    uint32_t slot = (lin - row) / RX_CHUNK;
    if (row >= h.nv || slot >= RX_CHUNKS)
        return 0xFFu;                                /* outside the list: an empty row */
    uint32_t p = rd8(blk + h.ext + row);
    if (p < RX_LEGACY)
        return rd8(blk + off + slot * RX_CHUNK + p);
    uint32_t i = p - RX_LEGACY;
    uint32_t base = blk + h.ext + h.nv + (h.nv & 1u) + 2u * h.e;      /* rowsA[17][E] */
    if (off == 0x180u)
        base += RX_CHUNKS * h.e;                                     /* rowsB[17][E] */
    return rd8(base + slot * h.e + i);
}

uint32_t bo3_rowx_gen_mat(uint32_t blk, uint32_t row)
{
    rx_hdr h;
    if (!header(blk, &h))
        return (uint32_t)(int32_t)(int16_t)rd16(blk + row * 2u + 0x84u);
    if (row >= h.nv)
        return 0;
    uint32_t p = rd8(blk + h.ext + row);
    if (p < RX_LEGACY)
        return (uint32_t)(int32_t)(int16_t)rd16(blk + p * 2u + 0x84u);
    return (uint32_t)(int32_t)(int16_t)rd16(blk + h.ext + h.nv + (h.nv & 1u) + 2u * (p - RX_LEGACY));
}
