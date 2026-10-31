# Modding guide - Burnout Mashup platform 0.1.9 (EXPERIMENTAL Windows x64 mod kit 0.7.0; sections 1-7 from kits 0.2.1 / 0.3.x, 8 from 0.4.0, 9 from 0.4.4, 10 from 0.5.0, 11 from 0.6.0, 12 from 0.7.0)

**Experimental, local, not published. Windows x64 only.** Host `burnout3_bmp_p3.exe` (sha256 `6f008b218400...`, build
identity `bmp-0.1.1+b56e33b66dc3`, platform 0.1.1; runtime evidence on p3: launches bmp_p3_1 / bmp_p3_2, earlier hosts as
named in COMPATIBILITY.md). Platform 0.1.1 and kit 0.2.1 are different version domains (VERSIONING.md). Mods need this host: on a retail / upstream Takedawn exe the `bmashup.*` services and
`[bmashup.*]` tables do not exist (INSTALL.md s1). Every
`bmashup.*` surface is private and experimental: it may change in a later platform version (mods state what they need,
section 1). Install and refusals: `INSTALL.md`; what was tested where: `COMPATIBILITY.md`.

Two kinds of mods, often combined in one mod set:

| kind | what it is | needs approval | tool |
|---|---|---|---|
| content-only (data) | `mod.toml` with `[bmashup.*]` declarations + `files\` (track files) | no | `tools\bmpack` (build / validate / verify) |
| code | `mod.toml` with `[plugin]` + a native module (`.asi`) | yes, per exact sha256 | `sdk\` (bmashup-sdk 0.3.0) |

## 1. What every mod says it needs: `[bmashup]`

```
[bmashup]
platform = ">=0.1"                                   # lower bound, MAJOR.MINOR[.PATCH]
requires = ["bmashup.events>=5", "bmashup.tracks"]   # services or tables ("bmashup.<table>"), optional >=N
```

The platform host checks every mod when it makes the mod list, before anything of the mod is used. A mod it cannot serve
is refused ALONE and the game starts without it (one `[PLATFORM] mod <id> <ver> refused, the game starts without it:
<need> (this host: Burnout Mashup platform 0.1.1)` line). Also refused alone (P-2 forward compatibility): a
`[bmashup.<table>]` the host does not know, a table `version` newer than the host reads, and a key the host's reader does
not take at a version it reads (typo protection). Platform 0.1.1 reads: `capacity` 1, `tune` 1, `regions` 1, `tracks` 1,
`extra_events` **2** (1 still reads as before), and offers 14 services (`sdk\README.md`). Platform 0.1.0 (p2) reads
`extra_events` 1 only: a mod with version 2 is refused alone there. Older hosts ignore `[bmashup]` (no diagnostic).

**Conflicts between mods (platform 0.1.1): the later mod is refused alone.** After the platform gate and before ANY
`[bmashup.*]` declaration is used, the host reads every enabled mod's tables together (the two-phase admission). When two
mods clash - the same track id, track name or track location (for the same track), a region letter with another text /
bank, the same World Tour event key, a location's 6 event rows overfilled, the track list's capacity (347 added), the same
tuning value - the LATER mod (`BMASHUP_MODS` folder order, then mod id) is refused ALONE, with every mod that needs content
only it declares. Its files, tables and plugin are never used; the EARLIER mod is unaffected; the game starts. The log names
BOTH mods and folders (RT-p3 bmp_p3_2):

```
[ADMIT] mod bmashup.bmp-p3-late 1.0.0 (<folder>) refused, the game starts without it: track id US_C8_V1: already added by mod bmashup.bmp-p3-early 1.0.0 (<folder>); track name US_C8_V1: already named by mod bmashup.bmp-p3-early 1.0.0 (<folder>); ...
[ADMIT] 3 mods' [bmashup.*] declarations checked together before any is used (platform 0.1.1): 2 admitted, 1 refused
[MOD] mod ignored (conflict with bmashup.bmp-p3-early: track id US_C8_V1): <folder>
```

The Mods page shows the refused mod as `CONFLICT` with that reason. Capacity declarations never clash (the largest wins).
Plugin registrations at runtime are not part of the admission (each service answers a second plugin with CONFLICT).

What still stops the start (exit codes in INSTALL.md s6): **a mod's OWN invalid table** - a declaration the host
understands but cannot APPLY (a capacity out of range: 91; a malformed track / region / name / event entry, a name / help
text out of its limits: 92; a tune value above 16 x: 93) - deliberately unchanged (the author's error); a guest-dependent
check at launch (a non-race location, the stage donor, Gamedata: 92 / 95 / 96); **host integrity** (out of guest memory:
92); and the host's own guards (88 / 89 / 90 / 94 / 97). The game writes the reason to the log, shows a message box and
exits with the code.

**Gameplay labels (platform 0.1.1).** A data mod with `[bmashup.tune]` (scoring / boost values, up to 16 x) or
`[bmashup.capacity]` (lanes, low-detail unit slot, STATIC pool) is LABELLED - it needs no approval, but the player is told:

```
[MODS] bmashup.bmp-p3-tune 1.0.0 changes gameplay: boost (Trading Paint Boost value (Boost units) 3 -> 6), scoring (Takedown BP 1000 -> 2000), capacity (AI route lanes 80)
[MODS] 1 data mod changes gameplay values (informational: no approval is asked; native code approval is separate, per sha256)
```

and on the Mods page the mod's information line reads `CHANGES GAMEPLAY: BOOST, SCORING, CAPACITY` (instead of its
description). Values: the catalogue's value -> the declared value; systems: boost = Boost Bar / Score/Boost/* / Tailgating /
Grinding, scoring = Burnout Points / BP Categories / Distance. No prompt, no acknowledgement, nothing stored: an unchanged
mod is never asked anything. A refused mod gets no label. Tracks / regions / events add content and change no existing
value: no label. **Code approval is separate and unchanged: per exact sha256 of the module** (INSTALL.md s4). (RT-p3 bmp_p3_2.)

## 2. Content-only mods with bmpack

`tools\bmpack\bmpack.py` builds a content mod from one declarative spec, validates any set of mods with the HOST'S OWN
readers (compiled from the host tree, tree_p3) plus the platform gate and the two-phase admission, and verifies a built
mod's hashes (bmpack 1.2).

```
py -3 -B tools\bmpack\bmpack.py build SPEC.toml OUT_SET [--with ROOT ...] [--no-validate]
py -3 -B tools\bmpack\bmpack.py validate ROOT [ROOT ...] [--json]      (ROOTs in BMASHUP_MODS order)
py -3 -B tools\bmpack\bmpack.py verify MOD_DIR
```

Spec (`examples\mods\*\*.toml` are the three launched ones: content-pack, track-pack on p1; events-pack on p3):

```
[mod]      id, version, name, description?, folder?
[[region]] letter, text, dj?                              -> [bmashup.regions]       (a new main region, Single Event)
[[track]]  id, donor, name?, location?, point_to_point?   -> [bmashup.tracks]        (a track under a new ID)
[[event]]  id, track, location, stage?, type?, name?, help?  -> [bmashup.extra_events]  (a World Tour race event;
                                                             name / help -> version 2)
[tune]     set = ["Group | Name = value", ...]            -> [bmashup.tune] version 1     (labelled)
[capacity] lanes?, low_unit_bytes?, static_bytes?         -> [bmashup.capacity] version 1 (labelled)
```

**World Tour event names and help texts (`[bmashup.extra_events] version 2`, platform 0.1.1):**

```toml
[bmashup.extra_events]
version = 2                                   # 1 still reads as before; names / help need 2
add = ["harbour-night = US_C8_V1 @ US_C3", "harbour-sprint = US_C8_V1 @ US_C3"]
stage = ["harbour-sprint = 020006USC1V1"]     # optional, as before
names = ["harbour-night = Harbour Night"]     # optional: the event list row (default: the track's name)
help = ["harbour-night = Race the harbour loop after dark. Added by a mod."]   # optional: the help bar
```

| key | shows | limit | characters | default |
|---|---|---|---|---|
| `names` | the event's row in its location's event list | **1..19** (the longest retail text of that row widget, "COMPACT GRAND PRIX ") | `A-Z a-z 0-9 space - ' . &` | the track's name |
| `help` | the help bar while the row is selected | **1..97** (the longest retail help-bar text) | the same + `!`; stored and shown UPPER CASE | `AN EVENT ADDED BY A MOD.` |

Refusals (exit 92, the event and the reason named): an id not in `add`, a second text for one event, a length outside the
limits, a character outside the set, `names` / `help` at version 1 (unknown keys at version 1 are refused alone by the gate),
a version other than 1 / 2. Declare `[bmashup] platform = ">=0.1.1"` with them (the SDK example `sdk\examples\events-v2`).
`bmpack validate` prints each event's row and help text as the game resolves them. Seen in the game on p3 (bmp_p3_1).

- **Donor data stays local.** `build` copies a RETAIL track folder of YOUR OWN game data (`--game-data`, docs\GAME_DATA.md) under the
  new ID, renaming only documented fields of `Gamedata.bgd`. The result contains game data: never upload or share it. The
  kit ships specs only (no game files). A shareable track needs your own track files (your own geometry, route, data).
- Output = f(spec bytes, donor bytes): rebuilding gives identical bytes; `bmpack.json` records every file's sha256.
- `validate` follows the game's boot order (manifests and modfs's rules incl. duplicate ids and the platform gate ->
  regions -> tracks + names per mod -> World Tour events -> the PrgData resolve, stage record and Gamedata record a launch
  reads) and lists EVERY refusal with the host's own reason (the game stops at the first). A gate refusal is reported as
  `[platform] <mod>: mod <id> <ver> refused, the game starts without it: ...` - byte-identical to the real p3 gate (39
  cases). It then runs the two-phase admission: a refused later mod is `[admission] <mod>: mod <id> <ver> (<folder>) refused,
  the game starts without it: <kind> <key>: ... mod <earlier id> <ver> (<folder>)` - the text of the game's `[ADMIT]` line
  (checked against launch bmp_p3_2 and the real p3 mod list in both orders; bmpack keeps up to 640 characters of a long
  reason - fewer when the mod id / version / folder are very long - and the game keeps up to 699, so a very long reason can
  read shorter in bmpack; verdict and refused mod agree). It shows each data mod's gameplay label.
- Limits on platform 0.1.1 (p3; the same as 0.1.0 except the event texts): 383 track list entries (36 retail, so 347 added); 23 declared regions (letters other than U / E / A,
  Single Event only); 35 added World Tour events over the 18 race locations (a location's list shows 6 rows, retail +
  added), race-type events on tracks a mod adds, in a retail region; names <= 27 characters, locations <= 17 (A-Z a-z 0-9
  space - ' . &).
- A track with more than 64 AI route lanes declares `[bmashup.capacity] lanes = N` (<= 255), else the start stops with 97.

Hand-written content mods are fine too: the SDK's `examples\content-template\mod.toml` shows every table; validate it with
bmpack before use.

## 3. Code mods with the SDK

`sdk\` is bmashup-sdk 0.3.0: the host's 16 public headers (byte copies of host p3 = p2's), `bmashup_sdk.h` (discovery
helper, catalogue, diagnostics, reference host p3), 8 example plugins + 3 data examples, one CMake / `build.ps1` build
(`sdk\BUILD.md`).

A plugin exports `takedawn_plugin_api_version`, `takedawn_plugin_init` and `takedawn_plugin_service`; the host calls the
last once per service right after init: **bmashup.host first**, then the 13 registered services; then (platform hosts)
the optional `takedawn_plugin_services_done`. Use the helper:

```c
static bmsdk_need s_need[] = { BMSDK_NEED(BM_EVENTS_SERVICE, 5, BMSDK_EVENTS_TABLE_V5, 1) };
static int s_reported;
BMSDK_DEFINE_API_VERSION()
BMSDK_DEFINE_SERVICES_DONE(s_need, s_reported)          /* "missing" said during the start on a platform host */
TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    bmsdk_need *w = bmsdk_offer(s_need, 1, name, version, table);
    if (!w) return 1;                                      /* not wanted: the host logs "not used" */
    if (w->state != BMSDK_BOUND) { bmsdk_log_need(api, w); s_reported = 1; return 1; }    /* too old */
    /* use the table; return TD_OK only when really used (the log's used / not used is then true) */
    return TD_OK;
}
```

and `bmsdk_report_once(api, s_need, 1, &s_reported)` from `on_shutdown` for older hosts. Build deterministically
(`-Wl,--no-insert-timestamp`) so an approval survives a rebuild; keep DllMain / constructors empty. To use the plugin in the game: Settings > MODS > select the mod > Approve and turn on > Restart now (INSTALL.md s4).

| example | service(s) | shows |
|---|---|---|
| events-observer | bmashup.events 2..5 | degrade by version, field checks on append-only structs |
| boost-modifier | bmashup.events 5 | BOOST_AWARD modifier with per-award / per-race caps (changes gameplay) |
| track-names | bmashup.memory 1 + bmashup.names 1 | plugin-owned guest memory, names for an added track |
| capacity (plugin + declaration-only) | bmashup.engine 1 + bmashup.streaming 2 / `[bmashup.capacity]` | capacity requests; prefer the declaration (no code) |
| content-template | (data) | every `[bmashup.*]` table + `[bmashup]` needs |
| events-v2 | (data, platform >=0.1.1) | `[bmashup.extra_events] version 2` names / help |
| hooks (owner + rival) | bmashup.hooks 1 | exclusive / shared registrations, priorities, CONFLICT, a MODIFY output |
| patch | bmashup.patch 1 (+ hooks for status) | a published-site patch with bounds |
| host-info | bmashup.host 1 | platform version, build, game signature, the service list, end of offers |

## 4. Hooks and patches - the contract in short (full text: platform `hooks\CONTRACTS.md`)

- **Hook points exist only where the host build carries a mark.** The game is statically recompiled C: no code address
  can be hooked, none is accepted or returned. bmashup.hooks v1 publishes six points: 1 PLAYER_CAR_UPDATE (player 1), 2
  LOAD_DONE, 3 RACE_EXIT, 4 TAKEDOWN, 5 WRECK, 6 BOOST_AWARD (OBSERVE; BOOST_AWARD also MODIFY of the amount).
- Register only while the plugins start; afterwards `CLOSED`. Callbacks run on the game's thread that hits the mark.
- Order per occurrence: bmashup.events modifiers -> hooks MODIFY -> events observers -> hooks OBSERVE -> host observers;
  within a role ascending priority (-1000..1000), ties in plugin start order.
- Each callback gets a fresh COPY of typed values (no game pointer); its only effect is the declared output (BOOST_AWARD:
  `out->amount`, accepted 0..16 x the game's amount, else ignored and counted; HOST awards never reach MODIFY). The guest
  registers / flags / x87 / mmx are saved and put back; a change is counted and logged once.
- Ownership: one registration per plugin, point and role (`ALREADY`); shared up to 16 (`FULL`); `EXCLUSIVE` refuses others
  both ways with `CONFLICT`, the log naming the owner. No unregister (plugins are never unloaded); nothing is dispatched
  once the process exits. Re-entry from inside a callback is not dispatched (counted).
- **Patches never touch code.** bmashup.patch v1 writes only the XBE's read-only data (`.rdata`) that the generated code
  reads at each use. Portable form: a published SITE (`game.byte_fade_rate` 510.0, bounds 127.5..2040.0;
  `game.racer_proximity_sq` 25600.0, 6400..102400) and a value in bounds, verified per build. Experimental form:
  `request_bytes` with this build's signature (retail `D0FC2EF4E9B2A86F`), the expected original bytes, mapped / .rdata /
  not the kernel thunk table. Overlaps: the first accepted owner keeps the bytes (`CONFLICT`). Nothing is written at
  request time; patches are applied all-or-nothing per plugin when the plugins' start ends (before the game's first
  instruction), read back, and checked at every LOAD_DONE. Neither service ever ends the process (no exit code).
- Result codes and log lines: `sdk\include\bmashup_hooks.h`, `bmashup_patch.h`; `result_text(code)` gives the names.

## 5. The host / mod boundary: what needs a new host build

A new host build gets a new build identity (`bmp-<platform>+<digest>`); a new platform version only when the mod-facing
surface changes (services, tables, keys).

A mod (data or plugin) can only use what the host exe was BUILT with. These need a new host build (anchored generated-code
marks, a relocation audit, tests), not a mod:

- a new hook point or a new hook output (a mark in the generated code that calls the host / takes its return value);
- any change to code or to constants compiled into the C (control flow, function bodies, folded constants): regenerate
  and rebuild; `.data` / ValueDB values need writer analysis and a re-apply point (as bmashup.tune);
- raising an engine limit (lanes past 255, slot / pool sizes past their ceilings, track list past 383, more than 35 World
  Tour events, more declared regions), relocating a game array, new menu rows / pages;
- a new `[bmashup.*]` table or key, a new service or service version (also bumps the platform version);
- a 4th World Tour MAP region (`ROADMAP.md`: MAP_REGION_PLAN P1..P10);
- Linux / macOS hosts (not built).

What a mod CAN do on p3 (platform 0.1.1): add tracks / names / regions / up to 35 World Tour events with their own row
names and help texts, ask for capacity (lanes, low-detail slots, STATIC pool), tune the 85 catalogued scoring / boost
values (<= 16 x; labelled), observe and modify through the published
services (events v5, hooks v1, autopilot, boost, route, racers, memory + names, takedawn.race), patch the two published
sites, and read the host's identity (bmashup.host).


## 6. New in mod kit 0.3.0 (platform 0.1.2 - 0.1.4)
Sections 1-5 above are kit 0.2.1's text and still hold on p4.1 (read "platform 0.1.1" there as "the platform version your
mod needs"). New:

### 6.1 Declarations (data mods, no approval)
| Declaration | Page | Example |
|---|---|---|
| `[bmashup] requires_mods = ["<id> >= X.Y.Z"]` | `docs\services\REQUIRES_MODS.md` | `examples\mods\deps-*` (bmpack specs) |
| `[bmashup.music] version = 1` (soundtrack, add, replace) | `docs\services\MUSIC.md` | `sdk\examples\music-pack` |
| `[bmashup.tune] version = 2` (AI values, signed) | `docs\services\TUNE_V3_AI.md` | `sdk\examples\tune-ai` |
bmpack 1.3 builds `platform` / `requires` / `requires_mods` from a spec's `[mod]` table (`tools\bmpack\BMPACK_1_3_PATCH_NOTE.md`);
music and tune tables are written by hand in mod.toml (bmpack validates them).

### 6.2 Services (approved plugins)
| Service | Page | Example |
|---|---|---|
| `bmashup.autopilot` 2 | `docs\services\AUTOPILOT.md` | `sdk\examples\autopilot-demo` |
| `bmashup.vphysics` 1 | `docs\services\VPHYSICS.md` | `sdk\examples\vphysics-demo` |
| `bmashup.traffic` 1 | `docs\services\TRAFFIC.md` | `sdk\examples\traffic` |
| `bmashup.ai` 1 | `docs\services\AI.md` | `sdk\examples\ai` |
| `bmashup.crash` 1 + `bmashup.events` 6 | `docs\services\CRASH_EVENTS_V6.md` | `sdk\examples\crash-scores` |
| `bmashup.settings` 1 | `docs\services\SETTINGS.md` | `sdk\examples\camera-fov` |
| `bmashup.camera` 1 | `docs\services\CAMERA.md` | `sdk\examples\camera-fov` |

### 6.3 Ownership rules in one place
Every control has ONE owner and refuses a second requester with a CONFLICT code - no silent last-writer-wins: traffic
density, AI pace, camera FOV scale (BUSY), each vphysics value, each tune entry (a mod's declaration owns it before plugins
start). Install at most one mod per control. On the car update the writers run in a fixed order: autopilot, boost, vphysics.

### 6.4 Player settings
`bmashup.settings` gives a plugin bounded settings on MODS > MOD SETTINGS; the host's own group BURNOUT MASHUP holds GARAGE
PAINT 7-8 (`docs\services\GARAGE_PAINTS.md`).


## 7. New in mod kit 0.3.1 (platform 0.1.5)
| Declaration | Page | Example |
|---|---|---|
| `[bmashup.cars] version = 1` (add / names / physics_scale) | `docs\services\CARS.md` | `examples\content\added-car` (generator from your own data) |
| `[bmashup.world_tour] version = 1` (region / map / location) | `docs\services\WORLD_TOUR.md` | `examples\content\wt-region` (generator from your own data) |
Content that copies or modifies retail files (models, tracks, audio) is retail-derived: build it locally from your own data, never
ship it. bmpack 1.5.0 validates the tables (with the shipped reference-host readers of this kit); it does not build them.

`bmashup.vphysics` correction: "Max Speed In Boost" (the ValueDB key and catalogue name, unchanged) is the car's top-speed limit -
it caps normal AND boost speed (`docs\services\VPHYSICS.md`).


## 8. New in mod kit 0.4.0 (platform 0.1.6): content authoring
| Want | Declare | Tool | Example | Page |
|---|---|---|---|---|
| an added texture (front end) | `[bmashup.textures]` | fetex `pack` | `examples\authored\fetex-art` | `docs\services\TEXTURES.md` |
| own 4th-region map art / texts | `[bmashup.wt_map_art]` (+ the region's `[bmashup.world_tour]`) | fetex | `fetex-art\fetex-oceania-art` | `WT_MAP_ART.md` |
| a new car series, more cars, paints, own photos, AI rivals | `[bmashup.series]`, `[bmashup.cars] version = 2`, `[bmashup.paints]` | vehtool `validate / package / palette` | `examples\authored\veh-series`, `bm-coupes` | `CARS.md` |
| a car with NEW geometry | `[bmashup.cars]` + own `pveh\...` files | carimport `validate / build / package` | `examples\authored\carimport` | `AUTHORING_TOOLS.md`, `tools\carimport\README.md` |
| a track with NEW geometry | `[bmashup.tracks]` + its files | trackbuild `build / validate / package` | `examples\authored\trackbuild` | `tools\trackbuild\README.md` |
Rules shared by all (CONTRACTS_CONTENT): content IDs `<mod-id>/<name>`; cross-mod references need `requires_mods`; admission is
transactional per mod; nothing is written to the game save (sidecars only); labels AUTHORED / CONTROL / DERIVED / DONOR / FIXTURE,
and anything carrying retail-derived bytes stays local. Limits: `docs\services\LIMITS.md`.

## 9. New in mod kit 0.4.4 (platform 0.1.7): big tracks on the mainline host

- The reference host is now the MAINLINE host **capmega1** (`bmp-0.1.7+9c6131448f9b`): capfix1 + the mesh row extension + the GAMEDATA slot
  expansion. Content should target the mainline host; side hosts exist only for experiments.
- **`[bmashup.capacity] gamedata_bytes`** (new key, table version unchanged): a larger GAMEDATA slot for a track whose Gamedata.bgd
  event does not fit the game's 0x176000 bytes (else the start stops with 88). Page multiple 0x177000..0x800000; the largest
  request of all mods wins. Say `platform = ">=0.1.7"` so that older hosts refuse the mod alone.
- **More than 83 material rows per unit** (the BMRX row extension in streamed.dat): read by capmega1; no kit tool writes it yet.
- The full capacity table (lanes, low-detail slot, STATIC pool, GAMEDATA slot), limits and evidence: `docs\services\CAPACITY.md`.
- bmpack: `validate` knows the new key (host readers capmega1); `build` does not write it (add it to mod.toml by hand).

## 10. New in mod kit 0.5.0 (platform 0.1.8): bigger mod sets and hook request phase 1

### 10.1 Bigger mod sets
- Up to **256 mods** in up to **256 mod folders**; 64 of them may declare `[bmashup.textures]` and 64 may be music packs.
- More folders than one environment value holds (32,767 characters): `BMASHUP_MODS_FILE=C:\path\mods-folders.txt` with one
  folder per line (`#` comments and blank lines skipped). Order = `BMASHUP_MODS` first, then the file; the first folder that
  has a file wins, as always.
- Validate a big set with `bmpack 1.4.0 validate ROOT [ROOT ...]`: a mod past 256 is reported ("the loader ignores it").

### 10.2 New and extended services (approved plugins; say `platform = ">=0.1.8"` and require the version)
| Service | What you can do | Page / example |
|---|---|---|
| bmashup.patch 2 | switch the damage loop's per-kind count / detach filters (0 / 1; process-wide, effective in Road Rage) | `PATCH_V2.md`, `damage-panels` |
| bmashup.racers 2 | each racer's place, laps, race time, phase; the place order; the session | `RACERS_V2.md`, `bm-racers-order` |
| bmashup.boost 2 | award an amount of boost to player 1 (bounded, rate-limited) | `BOOST_V2.md`, `bm-boost-award` |
| bmashup.hud 1 (new) | move / scale / fade the boost bar, boost message, award texts, score board for a few pictures | `HUD.md`, `bmashup-hud-shake` |
| bmashup.settings 2 | per-player settings (P1 / P2) on MOD SETTINGS; 8 a plugin | `SETTINGS_V2.md`, `per-player-settings` |
| bmashup.input 1 (new) | read the pad (buttons, edges, sticks, triggers) - never while a host page has it | `INPUT.md`, `bmashup-input-log` |
| bmashup.vphysics 2 | read any vehicle's handling values outside a race (garage stats) | `VPHYSICS_V2.md`, `bm-vphysics-garage` |
| bmashup.traffic 2 | traffic density up to 3.0 (EXPERIMENTAL above 2.0) | `TRAFFIC_V2.md`, `bm-traffic-x3` |
| bmashup.hooks 2 | observe each scored Crash junction (point 7 CRASH_RESULT) | `HOOKS_V2.md`, `crash-hooks` |

Rules that stay: no guest address ever reaches a plugin; outputs are bounded and refused (never clamped) when invalid; controls
have one owner; nothing outlives a race; player 1 (split screen) answers UNSUPPORTED until split screen is tested.
Status: offline-tested on the reference host; the in-game acceptance is pending at the time of writing.

## 11. New in mod kit 0.6.0 (platform 0.1.9): the 256 MB window and hook request phases 2 + 3

### 11.1 Memory
- The guest memory window is 256 MB: the game keeps its own 64 MB, the host's expansions (`[bmashup.capacity]`, front-end
  textures, paints, the new pools) use the 192 MB above it. Content no longer competes with the game's own 64 MB.
- The start checks the expansions' total against the free high zone; too much stops the start with a message (exit 86).

### 11.2 New and extended services (approved plugins; say `platform = ">=0.1.9"` and require the version)
| Service | What you can do on 0.1.9 | Page / example |
|---|---|---|
| bmashup.vphysics 3 | MANUAL gearbox for player 0, request gears, gearbox status | `VPHYSICS_V3.md`, `bm-gearbox-toggle` |
| bmashup.racers 3 | read gear / speed / yaw rate / accelerations / damage parts / lights; detach a hanging part (any racer); lights ON (head / tail / brake, indicators LEFT / RIGHT / HAZARD, `lamp_counts`); `award_score` (HUD / results points) | `RACERS_V3.md`, `bm-racers-dynamics`, `bm-detach-parts`, `bm-lights-blinkers` |
| bmashup.traffic 3 | the crash pool's occupancy (wreck / near_vehicles / clear_wrecked UNAVAILABLE on 0.1.9) | `TRAFFIC_V3.md`, `bm-traffic-check`, `bm-kamikaze` |
| bmashup.hooks 3 | HUD_PASS (8), CAMERA_FINAL (9), TRAFFIC_CONTACT NO_CRASH (10), WRECK_CAUSE observe + re-credit (11), EVENT_SOUND level (12), FINISH_CAMERA (13) | `HOOKS_V3.md`, `bm-contact-no-crash`, `bm-takedown-pitch` |
| bmashup.events 7 | observe-only twins of points 8, 10, 11, 12 | `EVENTS_V7.md` |
| bmashup.camera 2 | chase-camera adjust; one finish pose per race (within 40 m of the end-of-race camera) | `CAMERA_V2.md`, `bm-camera-roll`, `bm-finish-camera` |
| bmashup.hud 2 | draw list: quads, text, sprites from `[bmashup.textures]` P8 entries (drawn inside the HUD_PASS callback) | `HUD_V2.md`, `bm-hud-rpm-meter` |
| bmashup.paints 1 (new) | player 0's body colour in races (confirmed in the retail game) | `PAINTS.md`, `bm-car-colour` |
| bmashup.menu 1 (new) | declare a popup (Single Event car select), an Eliminator mode row (Single Event list); stat bars (car select) are declared but UNAVAILABLE on 0.1.9 (`feature_available` 0) | `MENU.md`, `bm-menu-popup`, `bm-garage-stats` |
| bmashup.rules 1 (new) | Eliminator race rules for a race started from your mode row | `RULES.md`, `bm-eliminator-mode` |

- There is no `[bmashup.hud]` table on 0.1.9: a mod declaring it is refused ("needs a newer platform"). HUD sprites use the pictures of
  your `[bmashup.textures]` table.
- Limits: stat bars are UNAVAILABLE on 0.1.9 and the indicator blink is not confirmed in still screenshots (see `docs\services\README.md`).
- Rules that stay: no guest address ever reaches a plugin; outputs are bounded and refused (never clamped) when invalid;
  controls have one owner; nothing outlives a race; player 1 (split screen) answers UNSUPPORTED.
- Status: offline-tested and run in the retail game (three validation rounds and an exclusive acceptance race with 137 mods and 38 plugins on the tested build).

## 12. New in mod kit 0.7.0 (platform 0.1.9, host main21): more services, tuning rows and tools

The platform version is still 0.1.9; what grew are the SERVICE versions. State the versions you need (`requires = [...]`, see
`MIGRATION.md`) and check every optional feature at run time.

### 12.1 Services
Declared by the 0.7.0 headers: racers 6, rules 6, traffic 8, camera 4, hooks 3, events 7, settings 2, tune 3. Details are in the comments of `sdk\include\bmashup_*.h` and in `docs\services\`.

| Service | Added in the main21 host |
|---|---|
| bmashup.racers | pose (world position and axes), wreck a racer on request, headlights and light ON, light OFF and a reverse lamp, a tail-lamp stand-in, AI name labels |
| bmashup.traffic | seed and lane floor, spread and section fill, fill empty lanes, sector pre-load (parked cars exist but are OFF in the default host) |
| bmashup.rules | Road Rage props, END SESSION in every mode, Crash Breaker in every mode, rival count and rival cars, Single Event DJ |
| bmashup.camera | a free camera for player 0 (set_free_pose), the picture-view window in state() |
| bmashup.hooks | sound pitch and push scale in the outputs; NO_CRASH really skips the crash; its closing-speed bound is 60 m/s |
| bmashup.paints | decals, wheels, nitro tint and glow |
| bmashup.hud | the elements POSITION, LAP, SPEED, TAKEDOWNS and CENTRE_MESSAGE |
| bmashup.menu | help text and option values for a mode row; Multiplayer mode rows |

New examples in `sdk\examples\`: bm-ai-names, bm-free-camera, bm-headlights, bm-traffic-attack, bm-traffic-kamikaze.

### 12.2 Data mods
- `[bmashup.textures]` class `global` replaces the shadow and spark entries of `Global.txd` (`docs\services\TEXTURES.md`).
  `tools\ps2look` builds such a mod from your own PS2 disc.
- `[bmashup.tune]` (version 3) accepts `sliders`: rows the player changes on the MODS page inside the range your mod declares.
  Every tuning key with its game value and limits is in `docs\TUNING_CATALOGUE.md`.
- Compatibility: `HOST_INFO.json` describes the host this kit was made for; the launcher of the tester package uses the same
  rules to give each mod an OK / WARN / BLOCKED verdict.

### 12.3 Tools
- trackbuild 0.3.0 builds sloped routes. The Workbench 0.30 (`workbench\`, or `Burnout Mashup Workbench.exe`) has a "New data mod"
  tab, uses the kit's trackbuild, and its Developer workflow window has task templates, a searchable tuning editor and
  "Test this project" (`workbench\DEVELOPER_WORKFLOW.md`).
- bmpack 1.5.0 is unchanged.
