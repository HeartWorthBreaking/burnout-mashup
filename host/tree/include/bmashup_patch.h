/*
 * bmashup_patch.h - the "bmashup.patch" service: Burnout Mashup's private, experimental verified data patches for native
 * plugins (Burnout Mashup builds only; may change or go away). Contract: research\native_gameplay_api\platform\hooks\
 * CONTRACTS.md.
 *
 * What it changes: bytes of the game's READ-ONLY DATA (the XBE's .rdata) that the generated code reads at each use
 * (MEMF(constant address)), so a new value takes effect. It never changes code: the game is statically recompiled C, its code
 * bytes in guest memory are never executed, and constants compiled into the C cannot be changed at run time.
 *
 * Two ways in:
 *   - a PUBLISHED SITE (portable layer): a name this build verified at start (expected original bytes in mapped .rdata, a
 *     reference census of the generated code: reads only, no writer), with a type and bounds; the plugin gives a value;
 *   - a VALIDATED ADDRESS (experimental layer): the plugin gives the build signature it was made for, a guest address, the
 *     expected original bytes and the new bytes (1 .. 64); refused unless the signature is this build's, the whole range
 *     is mapped guest memory (bm_guest) inside the .rdata bytes the XBE initialises, and the bytes there are the expected
 *     ones. No address is ever handed TO a plugin.
 *
 * Rules (version 1):
 *   - request only while Takedawn starts the plugins; then CLOSED;
 *   - nothing is written at request time: all accepted patches are applied when the plugins' start ends, before the game's
 *     first instruction (so before the game uses the bytes), plugin by plugin in the order of their first request;
 *   - at apply time each patch is checked again (expected bytes, mapping) and read back; if one patch of a plugin fails,
 *     every patch of that plugin already written is restored and all of them are REFUSED (all or nothing per plugin);
 *   - ownership: a patch belongs to the requesting plugin; a range overlapping another plugin's accepted patch is refused
 *     (CONFLICT, the log names the owner), overlapping the plugin's own (OVERLAP_SELF) too - first accepted owner wins;
 *   - lifetime: an applied patch stays for the process (no withdraw, no restore at exit); at each LOAD_DONE the bytes are
 *     read back and a change by anything else is counted (status.overwritten) and logged once;
 *   - every refusal is a code here and one "[PATCH]" log line; the game never stops because of a patch request.
 *
 * Version 2 (platform 0.1.8; append-only: every v1 call, struct and code keeps its meaning) - CODE-EMBEDDED INDEX TABLES:
 *   - why it works: the recompiler emits a two-level switch as `idx = ZX8(MEM8(reg + TABLE)); jt = MEM32(idx * 4 + JUMPS);
 *     if (jt == A) goto ..; ..; else ITAIL(jt)`, so a switch's BYTE INDEX TABLE is read from guest memory at every use even
 *     though it lies in .text. Writing an index byte selects another of the switch's EXISTING targets. Writing the jump table,
 *     or an index >= the switch's jump entries, would reach RECOMP_ITAIL with an address that is not a lifted entry: refused,
 *     never written;
 *   - the host lists the index tables of THIS build (a census of the generated code + the XBE: one reader, no writer, no host
 *     reference, jump words = the switch's targets; 92 of the 112 byte-index switches) and at start checks every listed table's
 *     bytes and jump words in guest memory (a different build: nothing listed is offered);
 *   - site class TABLE (bm_patch_site_info.kind), site type BM_PATCH_U8_INDEX: one index byte, value 0 .. targets - 1, whole;
 *     the first published family: "game.damage.panel_count.<k>" and "game.damage.panel_detach.<k>", k = 0..6 (the car part
 *     kind), the two tables sub_00023DE0 reads in its per-frame damage loop (count filter / detach filter; shipped
 *     00 00 01 00 01 00 00 = kinds 2 and 4 on). Value 1 = the kind is counted / detached, 0 = skipped. The damage share is
 *     divided by the counted parts: request_site_pair keeps a kind's count and detach equal (recommended);
 *   - the EXPERIMENTAL address form (request_bytes) may name bytes inside a listed index table (each byte < that switch's jump
 *     entries, else OUT_OF_BOUNDS); a listed jump table is HOST_OWNED; a listed table that did not match this build at
 *     start is NOT_INDEX_TABLE; every other byte outside .rdata stays NOT_DATA (v1's answer, unchanged for v1 plugins);
 *   - scope: an index byte is PROCESS-WIDE - every mode running that function sees it (documented, not enforced);
 *   - limits: 256 patches in all (v1: 64).
 */
#ifndef BMASHUP_PATCH_H
#define BMASHUP_PATCH_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_PATCH_SERVICE "bmashup.patch"
#define BM_PATCH_VERSION 2u         /* 1: .rdata sites + address form; 2: + TABLE sites, index-table bytes, request_site_pair */
#define BM_PATCH_VERSION_1 1u
#define BM_PATCH_VERSION_2 2u

#define BM_PATCH_MAX_BYTES 64u      /* bytes per address patch */
#define BM_PATCH_MAX_PATCHES 256u   /* patches in all (v2; v1 hosts: 64) */

enum {
    BM_PATCH_OK                = 0,
    BM_PATCH_BAD_ARG           = 1,     /* no host / req / handle / out, struct_size too small, size 0 or > 64 */
    BM_PATCH_CLOSED            = 2,     /* the plugins' start is over */
    BM_PATCH_UNKNOWN_SITE      = 3,
    BM_PATCH_SITE_UNVERIFIED   = 4,     /* the site did not verify against the running build at start: never written */
    BM_PATCH_OUT_OF_BOUNDS     = 5,     /* the value is not finite, outside the site's bounds, or not whole for an integer */
    BM_PATCH_BUILD_MISMATCH    = 6,     /* the request's build signature is not this build's */
    BM_PATCH_UNMAPPED          = 7,     /* the range is not wholly inside mapped guest memory */
    BM_PATCH_NOT_DATA          = 8,     /* the range is not wholly inside the .rdata bytes the XBE initialises */
    BM_PATCH_EXPECTED_MISMATCH = 9,     /* the bytes there are not the expected ones */
    BM_PATCH_CONFLICT          = 10,    /* overlaps another plugin's accepted patch */
    BM_PATCH_OVERLAP_SELF      = 11,    /* overlaps this plugin's own accepted patch */
    BM_PATCH_FULL              = 12,    /* BM_PATCH_MAX_PATCHES patches in all */
    BM_PATCH_NOT_OWNER         = 13,    /* the handle is another plugin's */
    BM_PATCH_UNAVAILABLE       = 14,    /* this run could not identify the build (no XBE header / .rdata): nothing is offered */
    BM_PATCH_RESTORED          = 15,    /* status reason: refused at apply time because another patch of the plugin failed */
    BM_PATCH_HOST_OWNED        = 16,    /* the range is the runtime's (the kernel thunk table the runtime resolves); v2: or a
                                           listed switch's JUMP table (never writable) */
    BM_PATCH_NOT_INDEX_TABLE   = 17     /* v2: the address form names a listed index table that this build did not match at
                                           start (not offered); other bytes outside .rdata stay NOT_DATA */
};

enum { BM_PATCH_PENDING = 1, BM_PATCH_APPLIED = 2, BM_PATCH_REFUSED = 3 };   /* status.state */
enum { BM_PATCH_F32 = 1, BM_PATCH_U32 = 2, BM_PATCH_U8_INDEX = 3 };          /* site types (U8_INDEX: v2) */
enum { BM_PATCH_SITE_RDATA = 1, BM_PATCH_SITE_TABLE = 2 };                    /* site classes (v2: site_info.kind) */

typedef struct bm_patch_site_info {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    char     name[48];              /* e.g. "game.byte_fade_rate" */
    uint32_t type;                  /* BM_PATCH_F32 / BM_PATCH_U32 / (v2) BM_PATCH_U8_INDEX */
    uint32_t verified;              /* 1 when the site verified at start (else requests are SITE_UNVERIFIED) */
    double   original;              /* the shipped value */
    double   min, max;              /* the bounds a value must keep */
    /* v2 (filled when struct_size covers them) */
    uint32_t kind;                  /* BM_PATCH_SITE_RDATA / BM_PATCH_SITE_TABLE */
    uint32_t targets;               /* TABLE: the switch's jump entries (values 0 .. targets - 1); RDATA: 0 */
    char     reader[24];            /* TABLE: the reading function, e.g. "sub_00023DE0" (diagnostic text only) */
    char     meaning[64];           /* what the value does, as the reading code shows it */
} bm_patch_site_info;

/* EXPERIMENTAL: a validated address patch. */
typedef struct bm_patch_bytes {
    uint32_t       struct_size;     /* sizeof (bm_patch_bytes) as the plugin built it */
    uint32_t       size;            /* 1 .. BM_PATCH_MAX_BYTES */
    uint64_t       build_signature; /* what build_signature() returns in the build the plugin was made for */
    uint32_t       va;              /* guest address (an input only) */
    uint32_t       reserved;        /* 0 */
    const uint8_t *expected;        /* size bytes: what must be there now */
    const uint8_t *bytes;           /* size bytes: what to write */
} bm_patch_bytes;

typedef struct bm_patch_status {
    uint32_t struct_size;           /* in: the size the caller has; out: the size filled in */
    uint32_t state;                 /* BM_PATCH_PENDING / APPLIED / REFUSED */
    int32_t  reason;                /* REFUSED: why (a BM_PATCH_* code); else BM_PATCH_OK */
    uint32_t overwritten;           /* APPLIED: read-backs that found other bytes there */
} bm_patch_status;

typedef struct bm_patch_api {
    uint32_t struct_size;           /* sizeof (bm_patch_api) as built */
    uint32_t version;               /* BM_PATCH_VERSION */
    uint32_t (TD_CALL *site_count)(td_host *host);
    int32_t  (TD_CALL *site_info)(td_host *host, uint32_t index, bm_patch_site_info *out);
    int32_t  (TD_CALL *find_site)(td_host *host, const char *name, uint32_t *index);
    /* A published site set to value. While the plugins start only. *handle: this patch (> 0). */
    int32_t  (TD_CALL *request_site)(td_host *host, uint32_t index, double value, uint32_t *handle);
    /* This build's signature (FNV-1a 64 of the XBE image header the runtime mapped at 0x10000). */
    int32_t  (TD_CALL *build_signature)(td_host *host, uint64_t *signature);
    /* EXPERIMENTAL: a validated address patch. While the plugins start only. */
    int32_t  (TD_CALL *request_bytes)(td_host *host, const bm_patch_bytes *req, uint32_t *handle);
    /* The patch's state. Any thread. */
    int32_t  (TD_CALL *status)(td_host *host, uint32_t handle, bm_patch_status *out);
    const char *(TD_CALL *result_text)(int32_t code);
    /* ---- version 2 (present when struct_size covers it) ----
     * Two published sites set to the same value as ONE unit: both accepted or both refused (the first refusal's code), never
     * one alone; applied / refused together. While the plugins start only. *handle: the pair (status covers both). */
    int32_t  (TD_CALL *request_site_pair)(td_host *host, uint32_t index_a, uint32_t index_b, double value, uint32_t *handle);
} bm_patch_api;

#ifdef __cplusplus
}
#endif

#endif /* BMASHUP_PATCH_H */
