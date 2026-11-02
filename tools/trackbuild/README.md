# trackbuild 0.3.0 - build a simple Burnout 3 track (EXPERIMENTAL, alpha)

**0.3.0:** routes may climb and descend. The drivable-floor gate now follows each station's own height instead of requiring one
height for the whole route (0.2.1). Flat tracks build exactly as with 0.2.1 (same files byte for byte). Demo: `tb.py gen-testloop
SRC --variant hill` + `examples\hill_package.toml` (BM Hill Loop, EU_T8_V1). Keep the start line, the grid and the rolling-start
stretch after it flat (the start grid is written level). See CHANGELOG.md.

**0.2.1:** fixes a race-start crash of tracks built with 0.2.0 or earlier when the track pool is relocated (e.g. with the SDK capacity example). Rebuild your tracks with 0.2.1; see CHANGELOG.md.

trackbuild turns an OBJ mesh, PNG textures and a track description (JSON) into a Burnout 3: Takedown track and packages it
as a Burnout Mashup data mod (an added track, `[bmashup.tracks]`). It is pure Python 3.11+ (standard library only) and runs
from any folder: it needs no developer workspace, only YOUR OWN prepared game data for the donor parts.

0.2.0 is the portable successor of 0.1.6: the same builds and packages byte for byte (see "Tests"), with the readers vendored
into `trackbuild\_vendor` (provenance: `VENDOR.md`), the donor data taken from an explicit `--game-data` folder and
hash-checked, and an actionable error for every missing prerequisite or unsupported input.

## What is AUTHORED and what is DONOR

| Part of the track | Origin |
|---|---|
| Road / scenery geometry, textures, materials (`static.dat`, `streamed.dat` render meshes) | **AUTHORED** (your OBJ + PNG) |
| Collision (floors, walls, surface words), streamed units, LOD meshes, PVS rows | **AUTHORED** (generated from your source) |
| AI route (S4: lanes, corners, zones), start grid + start / finish line + checkpoints (S1 page) | **AUTHORED** (from the description) |
| Traffic (S2 set + S3 lane network) | **AUTHORED** when the description has `traffic`, else **DONOR** |
| Gamedata header and event records (modes, laps, driver setup) | **DONOR** (retail EU/M1_V1) |
| `enviro.dat` (sky, clouds, lighting environment) | **DONOR** (retail EU/M1_V1, unchanged) |
| Audio: `SOUND.AWD`, `CRASH1..3.RWS`, `E_DJRACE.xwb`, `MUSIC.RWS` | **DONOR** (retail EU/M1_V1, unchanged) |

So trackbuild is **not** complete track authoring: sky, sound and the event header always come from a retail track. A
package therefore contains retail game data: **keep it local, never share or upload it**. `LABELS.json` and
`BUILD_REPORT.json` label every part AUTHORED or DONOR.

## Quick start: build the demo track (BM Test Loop)

You need: Windows, Python 3.11+ (`py -3 --version`), and your prepared Burnout 3: Takedown **North America (NTSC-U) Xbox**
data - the folder that holds `Tracks` and `default.xbe` (the same folder Takedawn / the mod kit use; written `<game-data>`
below). trackbuild only reads it.

```
cd <this folder>
py -3 -B tb.py selfcheck
py -3 -B tb.py check-game-data --game-data "<game-data>"
py -3 -B tb.py gen-testloop  work\src
py -3 -B tb.py build         work\src test_loop.track.json work\build --game-data "<game-data>"
py -3 -B tb.py validate      work\build
py -3 -B tb.py package       work\build examples\test_loop_package.toml work\set
```

The mod is now `work\set\gp_trkimp_examples\bm-test-loop` (track `EU_T1_V1`, "BM Test Loop", region Europe). Copy that
folder into a mod root of the Burnout Mashup host and start the game; the track appears in the Europe track list. The
canyon demo (BM Canyon Ring, 30 units, computed PVS): `gen-testloop work\src_c --variant canyon`, then the same steps with
`examples\canyon_package.toml`.

Instead of `--game-data` every time, set `TRACKBUILD_GAME_DATA=<game-data>` (or the mod kit's `BMKIT_GAME_DATA`).
`tb.cmd` does the same as `py -3 -B tb.py` and says what to install when no Python is found.

## Build your own simple track

1. Start from the demo source: `tb.py gen-testloop work\mine` writes `test_loop.obj`, `test_loop.mtl`, `textures\*.png` and
   `test_loop.track.json`. Edit the mesh in a 3-D tool (export OBJ with UVs and normals, triangles / quads, Y up, metres)
   and keep the description consistent with it (stations, units, grid, lines: `docs\ADVANCED.md`).
2. Copy `examples\my_track_package.toml`, choose a new track ID (`EU_T7_V1` style, not used by any retail or other mod
   track), name, location and mod id.
3. `build` -> `validate` (must PASS) -> `package`, as above. Optionally `package ... --bmpack <mod kit>\tools\bmpack\bmpack.py`
   also runs the host's real readers on the set (needs the mod kit's own setup).

## Limits (0.2.0, unchanged from 0.1.6)

- Closed circuits only. 4..17 units with `pvs.mode = all`; up to 162 units with `pvs.mode = computed` (every unit must stay
  visible only inside the +-8 unit ring - long open sight lines need occluders or longer units).
- LOD: identity or bounded decimation (`lod.mode = decimate`, e_max 0.3 m); mesh block <= 0x28000, LOD block <= 0x18000 bytes
  (the game's defaults; 0.3.4 capacity auto: up to the host ceilings, see "Capacity" below), <= 127 records and 65,536 vertices
  per block, <= 83 material rows.
- Materials: opaque, one DXT1 texture (power of two 4..1024, 8-bit RGB / opaque RGBA PNG), retail type 0 / flags 0. No alpha,
  additive, animated, reflective or water materials, no props / instances / backdrops.
- Traffic: authored traffic is one road with 1..4 same-way lanes and one traffic set of the whole-track shape; otherwise the
  donor's traffic (positioned ~6 km away on the retail track).
- Runtime status of the demos (0.1.6 runs, same bytes): load, render, streaming, laps, AI, grid, walls / floor, LOD, PVS,
  authored traffic and crash **respawn** were seen working in game. **Off-track reset is UNTESTED** (never triggered).
  Offline gates prove structure, not appearance, collision feel or AI behaviour: every new track needs an in-game check.

## Capacity: game defaults and Burnout Mashup host ceilings (0.3.4)

The game's default sizes (mesh block 0x28000, LOD block 0x18000, static.dat 0xD00000, Gamedata route data 0x176000, 64 AI
route lanes) are no longer hard limits. With the track description key `"capacity": "auto"` (the DEFAULT) a track may need
more, up to the Burnout Mashup host's ceilings (mesh / LOD block 0x200000, static.dat 0x4000000, Gamedata 0x800000, 255 lanes;
one table: `trackbuild\capacity.py`, `tb.py capacity`). `package` then declares exactly what the track needs (page-rounded)
in mod.toml `[bmashup.capacity]` (`version = 1`), merged with the package's own keys (`lanes`, `[package.capacity_keys]`;
largest value wins); BUILD_REPORT.json and LABELS.json list the declared keys and the minimum host for each value:
full_unit_bytes (any value), low_unit_bytes above 0x30000 and static_bytes above 0x20C4000 need a host with **patch 131+**;
the other values need a host that reads `[bmashup.capacity]` (main21+). A track within the game's defaults declares nothing
(its package is byte-identical to 0.3.3). `"capacity": "game"` (description or `[package] capacity`) keeps the old behaviour:
refused above the game's defaults (tracks for hosts without capacity declarations). The 83 material rows per block are a
format limit, not a capacity: unchanged.

## Tests

```
py -3 -B tests\run_tests.py <new folder> --game-data "<game-data>"
```
runs `selfcheck`, `tests\test_errors.py` (every actionable error: exit code + message), `tests\test_trackbuild.py` (the 0.1.6
offline suite: determinism, validators, retail controls, negatives) and `tests\test_regression.py` (BM Test Loop and BM Canyon
Ring packages byte-identical to 0.1.6, `tests\REFERENCE_0_1_6.json`). Without game data the checks that need it are SKIPPED
with a message.

## Exit codes
0 ok - 1 validation gate / host check failed - 2 usage or path error - 3 missing prerequisite (Python, package files,
game data) - 4 unsupported input (the message names the feature and what is supported).

More: `docs\ADVANCED.md` (formats, description keys, game data, validation gates, isolation check), `VENDOR.md` (vendored
code and licences), `CHANGELOG.md`.

## Local-only outputs (project policy)
Everything this tool builds from your own game data is derived from it: keep it on your PC and never upload, share or commit it. Only sources marked AUTHORED are meant to be shared. See `docs/LOCAL_OUTPUTS.md`.
