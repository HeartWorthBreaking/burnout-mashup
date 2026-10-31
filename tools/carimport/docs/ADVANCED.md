# carimport 0.1.1 - advanced guide

Quick start: `..\README.md`. Format mapping and evidence: `DESIGN.md`.

## 1. AUTHORED vs DONOR, element by element
| element | source | notes |
|---|---|---|
| body geometry, LOD 3 (`body`, `body.*` merged) | AUTHORED | the nearest LOD; also used for LOD 0..2 unless you give `body_lod0..2` (reported) |
| lower LODs (`body_lod0`, `body_lod1`, `body_lod2`) | AUTHORED (optional) | LOD 0 = farthest |
| UVs (TEXCOORD_0) | AUTHORED | top-left origin, unchanged |
| normals | AUTHORED (glTF NORMAL) or computed | packed 11:11:10 in the file |
| materials | AUTHORED class per primitive | `paint.*` = game paint shader (recoloured), `plain.*` = opaque textured, `glass.*` = game glass pass (global glass texture, retail alpha) |
| texture + paints | AUTHORED | ONE 512 x 256 PNG; quantised to P8; paint mask -> a 64-entry luminance ramp at palette 64..127; 1..8 paints = palettes |
| wheel | AUTHORED `wheel` node (one wheel, wheel-local, axle = X, centred) or GENERATED neutral cylinder | drawn by the game at the DONOR's wheel positions; the cylinder uses the donor wheel radius and `wheel_uv` |
| bounds (AABB, radius) | AUTHORED | from LOD 3 |
| crush skin (deformation weights, VB1) | NEUTRAL, derived from the donor | `deform = "transfer"`: each vertex takes the bone weights of the nearest donor LOD 3 body vertex after mapping the bounding boxes; `rigid`: all on one mid-body bone (no crush shape). Visual crush quality is not assessed |
| collision hull | DONOR | the authored body must fit the donor's extents (+-30 % per axis, refused otherwise) |
| wheel positions, locators, crush tables, header matrices | DONOR | |
| emitters (head / tail lights, exhaust, smoke points) | DONOR | their positions follow the donor, not your body |
| engine-sound descriptors + engine audio (`.hwd` / `.lwd`) | DONOR (byte copies) | |
| physics / handling, garage photo, career index | DONOR via the host (`[bmashup.cars]` add = "ID = DONOR") | a garage photo of your own needs fetex (`[bmashup.textures]` + `photos`) |
| detachable panels, light geometry (draw flags 0x4..0x80), glass-break visuals of your own parts | NOT SUPPORTED | neutral stand-ins (zero-area draws); lights stay the donor's emitters |
Consequence: a package embeds donor structural bytes and audio. It is DERIVED and LOCAL ONLY; share the source (glTF, PNG,
car.toml), never the built `.bgv` / package. Users rebuild it with their own game data.

## 2. car.toml reference
```toml
[car]
id = "COMPCIC1"          # class (COMP MSCL CUPE SPRT SUPR HSPC HEVY) + 1..8 of A-Z 0-9
donor = "COMPCAR1"       # retail race car of the same class
name = "Compact Coupe BM"  # garage name, 1..21 ASCII
model = "coupe.gltf"     # .gltf (+ .bin) or .glb, relative to this file
paint_mask = "paint_mask.png"   # optional; required for more than one paint
texture_name = "cicoupe"        # <= 23 ASCII
deform = "transfer"             # transfer | rigid
mod_id = "bmashup.carimp-coupe"   # optional (default bmashup.carimp-<id>); the package folder = its last dot part
mod_name = "carimport demo: Compact Coupe BM"   # optional
mod_version = "1.0.0"                           # optional
wheel_uv = [0.0, 0.0, 0.0625, 0.125]  # texture box of the GENERATED wheel (only without a 'wheel' node)
[[paint]]                       # 1..8, in order = palette index (the garage offers the first min(n, 6))
name = "teal"                   # [a-z0-9_.-]{1,40}
color = "#1FA8A0"
```
Unknown keys / tables are refused (typos never pass silently).

## 3. glTF rules
- glTF 2.0 `.gltf` (+ external or data-URI buffers) or `.glb`; triangles only; one scene.
- Mesh nodes: `body` / `body.*`, `body_lod0..2`, `wheel`; anything else carrying a mesh is refused.
- Material class: `extras.bm_class` or the name prefix; white baseColorFactor; every material samples the SAME PNG.
- Refused: COLOR_0, TEXCOORD_1, TANGENT, JOINTS / WEIGHTS, skins, morph targets, animations, cameras, any extension,
  non-triangle modes, emissive / normal / occlusion / metallic-roughness textures, JPEG, a second image.
- Reported (not representable): metallic / roughness factors, doubleSided, LOD reuse, generated wheel, zero-area triangles,
  negative-scale transforms baked.

## 4. Limits
Model slot 0x9D800 bytes (645,120; the coupe uses 56 %); <= 65535 vertices per LOD; <= 255 draws per list; 1..8 paints;
texture 512 x 256 P8; body within +-30 % of the donor's extents.

## 5. Pipeline for scripting
`import` writes the car IR (JSON, game frame) - you may transform it and `build --ir` it; `build` re-reads every output with the
strict reader (`carimp\bgvlib.py`) and decodes it back against the IR (positions / UVs exact, normals within packing error,
triangle orientation per class). `--json` gives machine-readable reports (refusals as `{"refused": [...]}`).

## 6. Troubleshooting (exit code -> what to do)
| message | meaning / fix |
|---|---|
| `CANNOT RUN: ... none was given` (3) | pass `--game-data` or set `BMKIT_GAME_DATA` (kit: or `bmkit.toml`) |
| `CANNOT RUN: ... has no default.xbe` (3) | point at the prepared game-data folder itself (the message names a subfolder when you gave its parent) |
| `CANNOT RUN: ... not the North America (NTSC-U) retail one` (3) | only the NTSC-U release is supported (as by Takedawn) |
| `CANNOT RUN: game data file ... differs from the supported release` (3) | the file is modified: prepare the data again; never install mods into the game data |
| `CANNOT RUN: installation incomplete` (3) | copy the whole carimport folder (SHA256SUMS.txt lists every file) |
| `CANNOT RUN: Python 3.x found; ... 3.11 or later` (3) | install Python 3.11+ |
| `REFUSED: ... no such file` / `folder ... does not exist` (1) | fix the path; outputs need an existing parent folder |
| `REFUSED: ... extension ...` / `COLOR_0` / `skins` (1) | remove the unsupported glTF feature in your exporter |
| `body extent ... differs from the donor by more than 30 %` (1) | scale the model or choose a donor of matching size |
| `exists: ... (packages are never overwritten)` (1) | remove the old package folder yourself or package into a new set |
| `INTERNAL ERROR` (4) | a bug: report the command line and the printed text |
