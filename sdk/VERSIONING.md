# Versioning and ABI rules - bmashup-sdk

Three independent version numbers meet in a mod:

| number | owner | where | what it means |
|---|---|---|---|
| plugin API | Takedawn | `TD_PLUGIN_API_VERSION` (1), mod.toml `[plugin] api = 1` | the three exports and `td_host_api` / `td_plugin_info`; the host refuses a module whose number it does not have |
| service versions | the host, per service | `BM_*_VERSION` / `TD_RACE_VERSION`; the `version` argument of `takedawn_plugin_service` and the table's `version` field | the highest version of that service the host has; a table only grows |
| SDK version | this SDK | `BMSDK_VERSION_*` ("0.3.0") | the bundled headers + bmashup_sdk.h + examples (the SDK package of mod kit 0.2.0; neither number is the platform version) |

## The SDK: semantic versioning
- **PATCH** (0.1.x): documentation, examples, build scripts, helper fixes that keep every function / macro / text.
- **MINOR** (0.x.0): new bundled header versions (a service grew), new helper functions or macros, new examples. Everything
  a plugin built with the previous minor used still compiles and behaves the same; diagnostic texts of existing states
  keep their wording (tools may match them).
- **MAJOR**: a helper function / macro removed or changed, a text changed, or a bundled header that is not append-only
  compatible with the previous one (a host breaking a service's ABI). While the major version is 0 (the services are
  experimental), a MINOR release may do this too, and says so in CHANGELOG.md.
- Each release names its reference host (exe sha256) and copies its headers byte for byte; a new host means a new SDK
  version, never an in-place re-sync (`scripts\sync_headers.py` refuses to replace a differing header).

## Service ABI rules (the host's, takedawn_services.h / takedawn_plugin.h)
1. **Tables and structs only grow at their end.** Every service table starts with `uint32_t struct_size; uint32_t
   version;`; every struct passed across starts with `uint32_t struct_size`. Fields keep their offsets forever.
2. **The size says what is there.** Read a field only when the other side's `struct_size` covers it
   (`BMSDK_HAS_FIELD(p, type, field)`); fill an output struct only up to the size the caller gave (the host does the same:
   `stats` / `lanes_info` / `lowslot_info` copy `min(theirs, ours)` and set `struct_size` to it).
3. **Nothing is removed or changes meaning within a service name.** A breaking change needs a new service name.
4. **A plugin asks for the version it needs** (`bmsdk_need.min_version`) **and the table size it reads at that version**
   (`min_table`), and uses newer functions only when `bmsdk_has(w, v)` and the table covers them.
5. A host never calls a plugin field past the plugin's own `td_plugin_info.struct_size`.

## How old binaries keep binding (evidence)
bmashup.events grew from version 1 to 5 by appending; the table stayed `subscribe, stats` (24 bytes) until version 5 added
`subscribe_modifier` (32 bytes), and `bm_event` grew 24 -> 44 -> 60 -> 76 -> 84 bytes:

| version | added | `sizeof(bm_events_api)` | `sizeof(bm_event)` | header checked (verify_sdk.py 2c) |
|---|---|---|---|---|
| 1 | PLAYER_CAR_UPDATE | 24 | 24 | content_count\cc1_track\tree_cc1 |
| 2 | LOAD_DONE, RACE_EXIT + 5 fields | 24 | 44 | g8_limits\e1_lifecycle\tree_e1 |
| 3 | TAKEDOWN, WRECK + 4 fields | 24 | 60 | g8_limits\e6_takedown\events\tree_e6e |
| 4 | BOOST_AWARD + 4 fields | 24 | 76 | g8_limits\e2_boost\tree_e2b |
| 5 | modifiers + 2 fields | 32 | 84 | g8_limits\e2m_modifier\tree_e2m, this SDK |

Offline binding evidence (facts): G8 consolidated cand1's interaction test (a)
(`g8_limits\consolidated\cand1\test_runs\ix_a\RESULTS.txt`) built the 7 event plugins of the v2 / v3 / v4 / v5 lineages
twice - LEGACY against their own lineage headers and REBUILT against the v5 headers - and bound all **14 / 14** binaries to
the real v5 service (`bm_events_service.c`); each was delivered its events, the v2 / v3 / v4 binaries reading only the
prefix their `struct_size` covers, and the v5 modifier chain (legacy + rebuilt) gave 4.0 -> 9.0. Candidate 2 changed none
of those files (CAND2_REPORT.md: 3 track files changed). This SDK adds (verify_sdk.py, scenario `old`) the other direction:
SDK-built plugins against a version-3 table - the observer binds and switches its v4 features off, the v5-only modifier
reports "too old" and is not used.

Not covered: a plugin built with a NEWER header than its host, for services other than events (the same rules apply; the
helper's `min_table` / `BMSDK_HAS_FIELD` checks are what protect it).

## Platform version (0.2.0; p3 since 0.3.0)
A fifth string, not a version: the host's **build identity** (`bmashup.host` `build`, `bmp-0.1.1+b56e33b66dc3` for p3,
`bmp-0.1.0+b8710764485c` for p2):
one exact build, for diagnostics or an exact-build requirement - never the compatibility contract.

A fourth number: the **Burnout Mashup platform version** of a host (`bmashup.host` `platform_version`, "0.1.0" for hosts
p1 and p2, "0.1.1" for p3; `BMSDK_REFERENCE_PLATFORM`). A mod states a lower bound in mod.toml (`[bmashup] platform = ">=0.1"`) and the services /
tables it requires (`requires = ["bmashup.events>=5", "bmashup.tracks"]`); a platform host refuses that mod alone when a
need is not met. The platform's `[bmashup.*]` tables have their own schema versions (all 1 on p1 / p2; p3 reads `[bmashup.extra_events]` 2): a table version newer
than the host reads, an unknown table, or an unknown key at a version it reads refuses the mod alone (P-2).

## 0.2.0 -> 0.3.0 compatibility
- Source: a plugin written against 0.2.0 compiles unchanged with 0.3.0 (nothing removed or changed but the version and
  reference-host constants). Code that printed or compared `BMSDK_VERSION_*` / `BMSDK_REFERENCE_*` sees the new values.
- Binaries: unchanged service ABI (headers byte-identical), so a module built with 0.2.0 binds to p3 exactly as to p2
  (offline: the kit 0.1.0 prebuilt modules through the p3 loader, scenarios `*_kit010`); a module built with 0.3.0 binds to
  p2 (same loader except the reported platform version). A module whose source does not use those macros rebuilds to the
  same bytes (six of the eight examples), so its approval stays valid.
- Data: `[bmashup.extra_events] version 2` needs platform 0.1.1; a 0.1.0 host refuses such a mod alone.

## 0.1.0 -> 0.2.0 compatibility
- Source: a plugin written against 0.1.0 compiles unchanged with 0.2.0 (every 0.1.0 function, macro, text and struct
  layout is kept). `BMSDK_SERVICE_COUNT` (11 -> 14) and the catalogue order changed: code that relied on either must be
  updated (a minor-version change while the major version is 0).
- Binaries: a module built with 0.1.0 still binds to host p1 / p2 (same loader) (offline: SDK binding 62 / 62 on the p1 loader, HOST_P1_REPORT
  s6); and ran on p1 in launch 51; it sees one more line `service bmashup.host 1: not used` and is never called at the end of the offers (it does not
  export the function), so it reports "missing" as before (next call / shutdown).
- A module built with 0.2.0 runs on older hosts: `bmsdk_host()` is NULL, `bmsdk_offers_done()` stays 0, and the 0.1.0
  report path applies (offline: the kit's verification, scenarios `missing_cand2` / `hostinfo_cand2` on cand2's loader).


## SDK 0.4.x (kit 0.3.0)
- 0.3.0 -> 0.4.0 was a MINOR step: new bundled header versions (autopilot 2, events 6) and six new service headers; every
  0.3.0 source compiles unchanged (the nine examples build against 0.4.1, `-Werror`).
- 0.4.0 -> 0.4.1 is a PATCH-level header change by content (tune 3 grows `bm_tune_info` with the struct_size prefix rule, so a
  version 2 caller is unaffected) plus new examples. The text above that says "0.3.0" describes that release.
- A plugin that needs a 0.4.x service names it with a minimum version in `bmsdk_need` (e.g. `bmashup.autopilot` 2 for
  `engage2`) and in its mod.toml `[bmashup] requires`, so an older host refuses the mod alone.
- 0.4.1 -> 0.4.2: a header comment (vphysics) and the reference host strings of `bmashup_sdk.h`; no ABI change.
