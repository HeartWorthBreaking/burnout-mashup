/* bm_patch_sites.h - PLATFORM-HK: the published data sites of bmashup.patch (bm_patch.c). Evidence per site:
 * research\native_gameplay_api\platform\hooks\logs\site_census.json (scripts\census_sites.py): the whole generated tree and
 * the host sources searched for every reference to the site's four bytes. A site is published only when (SRC) the value
 * lies in the XBE's initialised .rdata, the XBE bytes are the original below, the generated code reads it through
 * MEMF(constant) at each use (so a new value takes effect), and nothing - generated or host code - writes it by its address.
 * The meaning column is what the reading code shows; a HYP there is not verified at runtime. Never edit by hand without
 * re-running the census.
 *
 * main18 (bmashup.patch v2): TABLE sites = one byte of a byte-index switch table listed by the index-table census
 * (bm_patch_tables_gen.h, gp\slices\main18\tests\svc_b\census_tables.py: one generated reader, no writer, no host reference,
 * jump words = the switch's targets). Each TABLE site names its table (`table`, an index into k_bm_patch_tables); bm_patch.c
 * verifies at start that the table is listed, its guest bytes / jump words are the census's, and the byte is the shipped
 * value; bounds = 0 .. the switch's jump entries - 1. */
#ifndef BO3_BM_PATCH_SITES_H
#define BO3_BM_PATCH_SITES_H

#include <stdint.h>

typedef struct bm_patch_site {
    const char *name;           /* the published name */
    uint32_t va;                /* guest address (host only: never handed to a plugin) */
    uint32_t type;              /* BM_PATCH_F32 / BM_PATCH_U32 / BM_PATCH_U8_INDEX */
    uint32_t original;          /* the shipped bits (XBE); U8_INDEX: the shipped byte */
    double min, max;            /* bounds (F32: 0.25 x .. 4 x the shipped value; U8_INDEX: 0 .. entries - 1) */
    /* main18 (v2) */
    uint32_t kind;              /* 0 / BM_PATCH_SITE_RDATA (1): .rdata; BM_PATCH_SITE_TABLE (2): an index-table byte */
    uint32_t table_va;          /* TABLE: the listed table's first byte (looked up in k_bm_patch_tables at start) */
    const char *meaning;        /* site_info.meaning */
} bm_patch_site;

#define BM_PATCH_DAMAGE_COUNT  0x00024188u   /* sub_00023DE0 loc_00023E99: kind k counted (1: ebx++) or skipped (0) */
#define BM_PATCH_DAMAGE_DETACH 0x00024198u   /* sub_00023DE0 loc_00024000: kind k detached (1: call sub_00125A50) or kept */

#define BM_PATCH_DAMAGE_SITE(fam, k, base, bit, what)                                                                    \
    {"game.damage." fam "." #k, (base) + (k), 3u /* BM_PATCH_U8_INDEX */, (bit), 0.0, 1.0, 2u /* TABLE */, (base),        \
     "part kind " #k " " what " (1) or not (0); shipped " #bit}

static const bm_patch_site k_bm_patch_sites[] = {
    /* sub_001805B0 (recomp_0003.c), 2 reads `xmm1.f[0] * MEMF(0x3B1840)`, no other reference: a byte channel (MEM8(esi))
     * moves toward its target by this rate x the step time, clamped (HYP: a fade, 255 units in 0.5 s). */
    {"game.byte_fade_rate", 0x003B1840u, 1u /* BM_PATCH_F32 */, 0x43FF0000u /* 510.0 */, 127.5, 2040.0, 1u, 0u,
     "a byte channel's fade rate per second (HYP)"},
    /* sub_00197430 (recomp_0003.c), 1 read `xmm2 = XMM_SCALAR(MEMF(0x3B1944))` at entry, no other reference: compared per
     * racer (count 0x73A19C, list 0x73A1A8) with a squared distance (HYP: a 160 m proximity radius, squared). */
    {"game.racer_proximity_sq", 0x003B1944u, 1u /* BM_PATCH_F32 */, 0x46C80000u /* 25600.0 */, 6400.0, 102400.0, 1u, 0u,
     "a racer proximity radius, squared (HYP)"},
    /* main18 (v2): sub_00023DE0 (recomp_0000.c), the per-frame part damage loop over the race's cars: part kind = MEM32
     * ((car + 0xCC0 -> +0x40) + 0xAC4 + 4i); kinds > 6 always count and detach (the `ja` before each table); else the byte
     * at table + kind picks the switch target. Shipped 00 00 01 00 01 00 00 (kinds 2 and 4). Process-wide. */
    BM_PATCH_DAMAGE_SITE("panel_count", 0, BM_PATCH_DAMAGE_COUNT, 0u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 1, BM_PATCH_DAMAGE_COUNT, 0u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 2, BM_PATCH_DAMAGE_COUNT, 1u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 3, BM_PATCH_DAMAGE_COUNT, 0u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 4, BM_PATCH_DAMAGE_COUNT, 1u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 5, BM_PATCH_DAMAGE_COUNT, 0u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_count", 6, BM_PATCH_DAMAGE_COUNT, 0u, "is counted"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 0, BM_PATCH_DAMAGE_DETACH, 0u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 1, BM_PATCH_DAMAGE_DETACH, 0u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 2, BM_PATCH_DAMAGE_DETACH, 1u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 3, BM_PATCH_DAMAGE_DETACH, 0u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 4, BM_PATCH_DAMAGE_DETACH, 1u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 5, BM_PATCH_DAMAGE_DETACH, 0u, "detaches"),
    BM_PATCH_DAMAGE_SITE("panel_detach", 6, BM_PATCH_DAMAGE_DETACH, 0u, "detaches"),
};
#define BM_PATCH_NSITES ((uint32_t)(sizeof k_bm_patch_sites / sizeof k_bm_patch_sites[0]))

#endif
