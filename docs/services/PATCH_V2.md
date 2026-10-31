# bmashup.patch 2 - verified index-table sites (platform 0.1.8)

Header: `sdk\include\bmashup_patch.h` (`BM_PATCH_VERSION 2`). Example: `sdk\examples\damage-panels`.
Status: **OFFLINE-TESTED** on the main18 host (`bmp-0.1.8+fcf55c586f78`) incl. the real XBE image; the in-game effect is **not
runtime-verified**. Address form: EXPERIMENTAL as in version 1. **CHANGES GAMEPLAY.**

## Why it works
The recompiled game reads a two-level switch's BYTE INDEX TABLE from guest memory at every use, although the table lies in
`.text`: writing an index byte selects another EXISTING target of that switch. A jump table, or an index value at or above the
switch's number of targets, is never written (it would reach a code address that was never translated).

## What version 2 adds
- Site type `BM_PATCH_U8_INDEX` (3) in a new site class TABLE; `bm_patch_site_info` grows (`BMSDK_PATCH_SITE_INFO_V2`): `kind`
  (RDATA / TABLE), `targets`, `reader` (diagnostic text), `meaning`.
- 14 published TABLE sites, values 0 / 1 only (whole numbers):

| site | byte | meaning |
|---|---|---|
| `game.damage.panel_count.<k>` (k = 0..6) | count filter of part kind k | 1: a part of kind k is counted by the damage loop |
| `game.damage.panel_detach.<k>` (k = 0..6) | detach filter of part kind k | 1: a part of kind k can come off (the game's own detach routine) |

  Shipped bytes `00 00 01 00 01 00 00` (kinds 2 and 4 on). Reader: the per-frame part damage loop (sub_00023DE0), the only
  reader. Its two callers are, per the modder's answers (not probed by us), the Road Rage mode logics: "effective in Road Rage";
  the scope is PROCESS-WIDE (every mode that runs the loop).
- Appended (`BMSDK_PATCH_TABLE_V2`): `request_site_pair(a, b, value, &handle)` - both sites or neither (recommended for count +
  detach of one kind: the damage share divides by the counted parts).
- Result code appended: 17 `NOT_INDEX_TABLE` (a listed table that did not verify in this build).
- Patches in all: 256 (was 64).
- Address form: bytes wholly inside a verified index table, each value < its targets, are accepted (expected bytes + build
  signature as version 1). A jump table answers `HOST_OWNED`. Every other byte outside `.rdata` keeps version 1's `NOT_DATA`.

## Verification
Offline census of the generated code + XBE (`census_tables.py`, deterministic): 112 byte-index switch sites, 92 listed, 65 compiled
into the host (`bm_patch_tables_gen.h`). At start every compiled table's bytes and jump words are compared with the census in
guest memory; a table that differs is not offered (its sites `SITE_UNVERIFIED`). Apply at the plugins' close, read-back at
LOAD_DONE, all-or-nothing per plugin, first owner wins: as version 1.

## Deviations from the design draft
- `NOT_INDEX_TABLE` is used only for a listed table that did not verify; other `.text` bytes keep `NOT_DATA` (the version 1 rival
  example's log is unchanged). Jump tables answer `HOST_OWNED` (version 1 said `NOT_DATA`; both refuse).
- `request_site_pair` returns the first patch's handle.

## Evidence
`gp\slices\main18\test_runs\svc_b_t3`: 77 / 77 (with hooks v2), 8 / 8 mutants; real `default.xbe` (read only) 26 / 26, 65 / 65
tables match, all 16 sites verify; the PLATFORM-HK suite 221 / 221 on the new tree.
</content>
