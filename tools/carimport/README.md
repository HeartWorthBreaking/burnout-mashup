# carimport 0.1.1 - import a simple car (quick start)

carimport turns a car you modelled (glTF 2.0: a body, optionally a wheel and lower LODs, one 512 x 256 texture + a paint mask)
into a Burnout 3 race-car model (`.bgv`) and a ready-to-install data mod that adds the car through the BurnoutMashup host's
`[bmashup.cars]` (host platform >= 0.1.5). No host code, no new executable. Advanced guide: `docs\ADVANCED.md`; format
mapping: `docs\DESIGN.md`.

**What you author vs what comes from a donor.** carimport does NOT make a complete car from scratch. You AUTHOR the body
geometry (all 4 LODs), the UVs, the materials (paint / plain / glass classes) and the paints (colours of the paint ramp). The
DONOR - a retail race car of the same class that you name in `car.toml` - provides the collision hull, the wheel positions,
locators and crush tables, the emitters (lights, exhaust, smoke points), the engine audio, the physics / handling, the
deformation weights' basis (`deform = "transfer"` copies them from the nearest donor vertex; `rigid` = no crush shape) and
the garage photo. Those donor parts are copied from YOUR game data, so a built package is DERIVED: local only, never upload it.

## 1. Prerequisites
- Windows 10/11, Python 3.11 or newer (python.org; the commands below use the `py` launcher). Standard library only.
- YOUR prepared game data: the folder of Burnout 3: Takedown, North America (NTSC-U) Xbox, as Takedawn installs it - the
  folder with `default.xbe`, `Data\` and `pveh\` (in the mod kit: `docs\GAME_DATA.md`). Its `default.xbe` must be the NTSC-U
  one; carimport then reads only the donor's `pveh\<CLASS>\<car>.bgv / .hwd / .lwd` and checks each against
  `GAMEDATA_SHA256.json` (a modified or other-release file is refused with the reason). It never writes there.
- Tell carimport where the data is: `--game-data "<game-data>"`, or set `BMKIT_GAME_DATA` once (inside the mod kit also
  `game_data` in `bmkit.toml`). There is no default and no search: without it, `validate` / `build` / `package` stop with
  `carimport: CANNOT RUN: ...` (exit 3) and say what to pass; given the parent folder, the message names the right subfolder.

## 2. Five-minute run with the demo coupe (an ORIGINAL procedural car shipped in `examples\coupe`)
```
cd <this folder>
py -3 -B carimport.py version
py -3 -B carimport.py validate examples\coupe\car.toml --game-data "<game-data>"
py -3 -B carimport.py package  examples\coupe\car.toml <mods>\my_cars --game-data "<game-data>"
```
`package` writes `<mods>\my_cars\carimp-coupe\` (mod.toml, `files\pveh\COMP\CIC1.bgv/.hwd/.lwd`, carimport.json, LABELS.txt,
SHA256SUMS.txt) and never overwrites an existing package. Put the set folder (`my_cars`) in the host's mods folder list
(`BMASHUP_MODS`, see the bundle's install guide). The car is the last row of the Compact series in SELECT CAR, with the six
paints teal, orange, violet, white, black, lime.

## 3. Your own car
1. `py -3 -B carimport.py demo wedge mycar` writes a minimal starting point (a wedge body, texture, paint mask, car.toml).
2. Model in Blender (or any glTF 2.0 exporter): metres, +Y up, +Z = car front, +X = car LEFT. One mesh node `body`; size it
   like the donor (each extent within +-30 %; the wedge / coupe are compact-sized). Materials named `paint.*`, `plain.*`,
   `glass.*`, all sampling the same 512 x 256 PNG through TEXCOORD_0.
3. Paint mask (same size): white = texels recoloured by the paints. Up to 8 `[[paint]]` entries (the garage shows 6).
4. Edit `car.toml`: `id` (class + 1..8 of A-Z 0-9, e.g. `COMPMY1`), `donor` (a retail car of the same class, e.g. `COMPCAR1`),
   `name` (<= 21 ASCII), `model`, `paint_mask`, paints.
5. `validate` until it prints `"ok": true`, then `package`. `inspect FILE` and `preview MODEL.bgv OUT.png` help to check.

Everything carimport cannot carry is REFUSED with the reason, never silently dropped (vertex colours, skins, morphs,
animations, extensions such as Draco, extra UV sets, normal / emissive maps, JPEG, unknown nodes / material classes).

## 4. Commands
| command | does |
|---|---|
| `demo {wedge\|coupe} DIR` | writes an ORIGINAL procedural test car (glTF + .bin, texture.png, paint_mask.png, car.toml) |
| `inspect FILE` | summary of a `.gltf` / `.glb` (nodes, materials, refusals) or `.bgv` / `.btv` (LODs, draws, texture, slot budget) |
| `validate CAR.toml` | the whole pipeline without writing (needs game data) |
| `import CAR.toml OUT.ir.json` | glTF -> car IR (game frame) |
| `build CAR.toml OUT.bgv [--ir IR]` | IR / glTF + donor -> `.bgv`, re-read by the strict reader and checked against the IR (needs game data) |
| `package CAR.toml OUT_SET` | the mod folder (needs game data); never overwrites |
| `export-bgv IN.bgv DIR` | CONTROL only: an existing model -> glTF (labelled local-only) |
| `preview IN.bgv OUT.png [PAINT]` | 4-view software render |
| `version` | tool version, package stamp, Python |
Options: `--game-data DIR`, `--json`. Exit codes (mod kit 0.4.1 convention): 0 ok, 1 refused (every problem listed), 2 usage,
3 cannot run (prerequisite missing: Python, tool files, game data), 4 internal error (please report). carimport 0.1.0 used
3 for refused.

## 5. Tests (run from any folder; OUT folders must be new)
```
py -3 -B tests\run_tests.py --game-data <data>            48 format / round-trip / negative / mutant / determinism checks
py -3 -B tests\test_errors.py <new out dir> --game-data <data>     actionable errors (dependencies, paths, input, data, builds)
py -3 -B tests\test_regression.py <new out dir> --game-data <data> demo + coupe / wedge packages = the content-phase bytes
```
Without game data the data-dependent checks are reported SKIPPED (never as passed).

## 6. Versions and labels
carimport 0.1.1 is the portable successor of 0.1.0 (the content-phase tool): no workspace paths, explicit hash-checked game
data (inside the mod kit through the kit's shared resolver `tools\_lib\bmkit_env.py`), actionable errors, the kit's exit-code
convention. Its outputs are byte-identical to 0.1.0's, so packages keep the stamp `carimport 0.1.0`
(`PACKAGE_STAMP`, the output-format identity). Shippable (AUTHORED): the tool, `examples\*` (listed in `AUTHORED_FILES.json`).
Built `.bgv` / packages and `export-bgv` output: DERIVED / CONTROL, local only. Provenance of vendored code: `PROVENANCE.md`.
