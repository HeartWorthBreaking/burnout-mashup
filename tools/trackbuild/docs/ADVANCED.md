# trackbuild 0.2.0 - advanced guide

## 1. Commands and options
```
py -3 -B tb.py gen-testloop SRC_DIR [--variant crash|bright_b|zeroed|lod_tint|canyon]
py -3 -B tb.py check-game-data [--game-data DIR] [--host RR/NN_VN] [--unpinned-donor]
py -3 -B tb.py build SRC_DIR DESC.json OUT_DIR [--game-data DIR] [--host RR/NN_VN] [--unpinned-donor]
py -3 -B tb.py validate OUT_DIR [DESC.json]
py -3 -B tb.py inspect OUT_DIR
py -3 -B tb.py package OUT_DIR PACKAGE.toml SET_ROOT [--bmpack FILE]
py -3 -B tb.py selfcheck | version
```
- Output folders (`SRC_DIR` of gen-testloop, `OUT_DIR`, the package's set folder) must be new or empty: nothing is overwritten.
- `DESC.json` is relative to `SRC_DIR` (or absolute). `validate` finds the description through `BUILD_REPORT.json`; give it
  explicitly when the source folder moved.
- `package` requires a passing `validate` of exactly the current track files (`VALIDATION.json` records their sha256).
- `--bmpack FILE`: after writing the set, run `FILE validate SET` (the mod kit's bmpack: the host's real readers, compiled with
  the kit's toolchain) and fail on a refusal. Without it the package is only verified structurally (bmpack.json hashes).
- Exit codes: 0 ok, 1 a gate / host check failed, 2 usage or path error, 3 missing prerequisite, 4 unsupported input.

Configuration variables (all optional; nothing else is read from the environment):
| Variable | Meaning |
|---|---|
| `TRACKBUILD_GAME_DATA` | the game-data folder when `--game-data` is not given |
| `BMKIT_GAME_DATA` | the mod kit 0.4.1 setting, used when neither of the above is set |
| `TRACKBUILD_ACCESS_LOG`, `TRACKBUILD_FORBID` | the isolation monitor (section 6); off unless set |

## 2. Game data
trackbuild reads YOUR OWN prepared Burnout 3: Takedown **North America (NTSC-U)** Xbox data (the folder with `Tracks` and
`default.xbe`, as Takedawn installs / the mod kit's `docs\GAME_DATA.md` prepares it). It never searches for it: the folder
comes from `--game-data`, else `TRACKBUILD_GAME_DATA`, else `BMKIT_GAME_DATA`; otherwise the command stops (exit 3).
Files read (read only):

| File | Use | Check |
|---|---|---|
| `default.xbe` (if present) | version identity | sha256 9f497acd82ad... (NTSC-U retail) |
| `Tracks\EU\M1_V1\Gamedata.bgd` | DONOR header + event records (+ S2 / S3 when no authored traffic) | pinned sha256 + size |
| `Tracks\EU\M1_V1\enviro.dat`, `SOUND.AWD`, `CRASH1.RWS`, `CRASH2.RWS`, `CRASH3.RWS`, `E_DJRACE.xwb`, `MUSIC.RWS` | DONOR, copied unchanged | pinned sha256 + size |
| `Tracks\US\C3_V1\static.dat` / `streamed.dat`, `Tracks\EU\M1_V1\static.dat` / `streamed.dat` | tests only (retail controls) | pinned |

The pins are in `trackbuild\donor.py`. A mismatch names the file, its hash and the expected hash (exit 3): use unmodified
data (no mod or patch written into that folder). Another host track: `--host RR/NN_VN --unpinned-donor` (its files are then
unchecked; `BUILD_REPORT.json` records `donor_pinned: false`; the host must have one S1 page for all its events).

## 3. Source format
- **OBJ**: `v x y z [r g b]` (the colour = baked vertex light; 0.2 is the neutral brightness of the demo), `vt`, `vn`, `usemtl`,
  `mtllib`, `o`, `g`, `s`, faces `v/vt/vn` with 3 or 4 vertices. Refused: lines, curves / free-form, n-gons, faces without uv
  or normal, negative / zero indices, zero-area faces, materials without a description row. Coordinates are the game frame:
  metres, Y up; faces wound so that cross(b - a, c - a) points along the normal (back faces are culled; floors face up).
- **Textures**: 8-bit RGB or fully opaque RGBA PNG, non-interlaced, power of two 4..1024 per side -> DXT1 + full mip chain.
  Transparent pixels, grey / palette PNGs and other sizes are refused.
- **Description** (`format: trackbuild.track/1`, `closed: true`):
  - `materials` {name: {`texture`, `surface` (retail collision word, hex: 0x0001 tarmac, 0x0002 concrete, 0x000F grass,
    0x0018 road-facing wall, 0x1018 back face), `collide`, `car_solid`}}. Any other material key (alpha, shader, animated, ...)
    is refused. Words with flag 0x10 (0x1xxx) are not solid for cars: car-solid materials with it are refused.
  - `rows` (render order, <= 83), `obj`, `stations` (centre-line points `p`, tangents `t`, lane-boundary `offsets` along
    n+ = (-tz, tx)), `stations_per_slice`, `units` (cut station pairs + lateral bounds), `route` (`lanes` types, `corners`),
    `grid` (exactly 6 slots), `start_line`, `checkpoints` (1..12), optional `traffic`, `lod`, `pvs`, `wall_gaps`,
    `gamedata_header` ("zeroed" = experiment). The generated demo description is the reference example.

## 4. Pipelines and status (newly AUTHORED geometry)
| Pipeline | What trackbuild does | Status (0.1.6 evidence, same bytes) |
|---|---|---|
| render / materials / textures | OBJ -> per-unit clipped polygons -> one strip per material row; PNG -> DXT1 mips | runtime-validated (demo tracks) |
| streamed units | cut lines + lateral bounds -> region quads, culling prisms, unit table | runtime-validated (17 and 30 units) |
| collision | KD trees per unit, retail surface words | runtime-validated (floor, walls) |
| LOD | identity, or bounded decimation (e_max 0.3 m) | runtime-validated (decimation) |
| visibility / PVS | `all` (<= 17 units) or `computed` (conservative, <= 162 units) | runtime-validated (30-unit canyon) |
| route / AI | S4 v3 (5 cyclic lanes, corners, 8 zones) | runtime-validated (5 rivals finish) |
| start grid / respawn | 6 slots (+0x40 = start unit); respawn on the main lane | grid + crash respawn runtime-validated |
| off-track reset | - | **UNTESTED** |
| traffic | authored S2 / S3 (one road, whole-track set) or donor | authored runtime-validated (start flow) |
| Gamedata header / events, enviro, audio | DONOR copies | DONOR |

Retail constants without a known reader are listed in `BUILD_REPORT.json` `retail_constants`.

## 5. Validation gates (`tb.py validate`)
| Gate | Checks (independent readers, never trackbuild's own writers) |
|---|---|
| V1_streamed_layout, V1_header_decoded | every mesh / LOD block re-serialises byte-identically (xbtopo), decodes fully (xbmesh), passes the strict rules |
| V2_tree_check, V2_drivable_coverage, V2_walls_hold | collision trees well-formed; every drivable sample in exactly one unit with a floor under it within 0.05 m of the ROUTE height there (0.3.0: the stations' own y, interpolated; 0.2.1: station 0's height everywhere) - report: max_floor_dy, max_route_grade_pct; wall probes 0.7 m above each station hit car-solid walls |
| V3_winding, V3_pvs_walk | front faces agree with normals; the PVS walk reaches every record once |
| V4_static_identity, V4_unit_table_tiles_streamed | static.dat strict parse -> identical rebuild; the unit table tiles streamed.dat |
| V5_gamedata, V5_route, V5_grid_on_main_lane, V5_grid_in_regions | Gamedata model identity / check; route identity / check / lint / camera + planner hazards; grid slots on the main lane and in their start unit |
| V6_budgets | slot / pool budgets: mesh / LOD block, static.dat, Gamedata need, route lanes against the game's defaults; 0.3.4 capacity auto: against the capacity the build report declares (trackbuild.capacity), never above the host ceiling |
| V7_traffic (authored traffic), V8_lod (decimate), V9_pvs_computed (computed PVS) | traffic structure + nodes on the floor; LOD error bound; stored PVS vs a denser recomputation |
A failing gate: exit 1, the gate is named and `VALIDATION.json` has the details; such a build is never packaged.

## 6. Isolation check (how 0.2.0 was validated)
`trackbuild\accessguard.py` records every path the process touches (Python audit events: open, listdir, scandir, mkdir,
remove, rename, import, subprocess...; plus wrapped os.stat / lstat / os.path.exists / isfile / isdir). Enable it with
`TRACKBUILD_ACCESS_LOG=<log file>` and `TRACKBUILD_FORBID=<folder>[;<folder>...]`; the log ends with SUMMARY lines (accesses,
forbidden accesses, sys.path entries and loaded modules under a forbidden folder). It never blocks. The 0.2.0 release check ran
the whole test set from a clean folder with a minimal environment and the developer tree as the forbidden folder: 0 forbidden
accesses (CHECKPOINT.md). That is same-machine isolation, not a second machine.

## 7. Packaging details
0.3.4 capacity: `[package] capacity = "auto"` (default) writes mod.toml `[bmashup.capacity]` (`version = 1`, then `lanes`,
`low_unit_bytes`, `full_unit_bytes`, `static_bytes`, `gamedata_bytes`; bytes as hex page multiples) for every need above the
game's default, merged (largest value per key) with the package's own `lanes` and `[package.capacity_keys]` (e.g.
`lanes = 80`). `"game"` refuses a build that needs more than the game's defaults unless the package's own keys cover it.
LABELS.json gets a `capacity` section (keys, per-key minimum host, overall minimum host) only when something is declared.
`package` writes `SET_ROOT\<set>\<folder>\` (mod.toml, bmpack.json, `files\Tracks\RR\NN_VN\` with the 10 track files, the
Gamedata donor ID renamed to the new track ID by the documented bmpack rule), `SET_ROOT\SHA256SUMS.txt` and
`SET_ROOT\LABELS.json`. The two example TOMLs are the 0.1.6 package descriptions, unchanged (their text still says 0.1.6 and
the canyon description repeats the loop's wording) because the regression requires identical inputs; use
`examples\my_track_package.toml` for your own track.
