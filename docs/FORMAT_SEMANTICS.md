# trackconv format-semantics table (Burnout Revenge Xbox -> Burnout 3 Xbox track data, and B3 authoring)

Date 2026-10-27. Sources: whitemountain `FORMAT_COMPARE.md`, `CONVERSION_PLAYBOOK.md`, WM1..WM6B reports, `wm5\DIAG_REPORT.md`,
`motorcity\MC_REPORT.md`, this toolkit's tests. Labels: **FACT** measured or read in code (cited); **HYP** hypothesis.

**The rule this table exists for: a file that parses strictly and rebuilds byte for byte is NOT proven to render or collide
correctly.** The strict readers prove layout (every byte claimed, every pointer recomputed, the host's own readers / guards
accept it). They say nothing about how B3's renderer, physics or AI treat a VALUE that retail B3 data never contains. White
Mountain 1.0.0 passed every offline gate and still drew a black slab in the sky (WM-5 cause 1). Every row below says what is
known about the game's behaviour separately from what is known about the bytes.

Columns: **Rev** = what the Revenge data carries; **B3** = what B3 supports; **trackconv** = what the toolkit does;
**Layout** = byte-level status (OFFLINE-VALIDATED = strict reader + round trip + negatives); **Behaviour** = render /
collision / gameplay status in the game.

## 1. Geometry, visibility, LOD (streamed.dat, static.dat units)

| Item | Rev | B3 | trackconv | Layout | Behaviour |
|---|---|---|---|---|---|
| Mesh block header, vertex buffer, records | +0x5C 0xC50 (records 0xCA0), rows +0x70..+0x7E, 22-B constant at +0x12A | records 0xC90, rows +0x71..+0x7F | re-laid out (`streamed.rev_mesh_to_b3`); inverse `b3_mesh_to_rev` | OFFLINE-VALIDATED: 2,838 / 2,838 retail units round trip (WM1 gate 4); 206 RevX blocks | RUNTIME-OBSERVED drawn (WM_RUN1, MC rev_1b) |
| PVS (17 x 0xA9 chunks) | at +0x140 | at +0x12A | moved verbatim | chain rule 2,331 / 2,331 (WM), 4,164 / 4,164 (MC) | drawn as retail (WM_RUN1) |
| Vertex stride 0x1C (xyz, 11:11:10 normal, ARGB, uv) | same | same | copied | byte copy | drawn |
| **Vertex alpha** | graded: 252 distinct values on WM (70-98 % of vertices) | retail is **binary 0 / 255 on every material type** (5 tracks; even opaque type 0, 59 % zeros) - a flag, not an opacity (FACT, `wm5 valpha_census.py`) | kept as is (no rule knows the B3 meaning) | byte copy | **UNKNOWN** (WM-5 HYP-B, secondary). Not a confirmed defect; quantising is an untested A/B |
| Vertex colour (RGB) | Revenge light / card colours (e.g. cloud 0x404040, god light 0x20201F) | modulates the texture (HYP: 2x; retail KS_godlight 0x7E7C77 on 74 / 74 vertices) | `fixes.vertex_rgb` / `tc.py vertex-rgb` (only exclusive records; alpha kept) | OFFLINE-VALIDATED (C4: reproduces WM-6b's file; shared-vertex / LOD / range negatives) | WM-6b fix RUNTIME-UNVERIFIED (rev_1b PARTIAL) |
| **Mesh-block object list** (Rev +0xC90 {0, A, B, N}: N x 12-B records + N x 64-B matrices) | street objects / light or sign placements (HYP) | no slot (B3 records start at +0xC90) | **dropped** (sha256 per unit in the manifest); strict rule refuses a malformed list | 3 negatives (MC-1 5a-5c; D test N+1) | absent in game (content loss) |
| Mesh slot | <= 0x28000 | **0x28000 fixed, no capacity option** | stage 1 refuses a larger block | checked | WM unit 6 fills it exactly |
| LOD slot | <= 0x18000 | 0x18000, growable to 0x30000 (`[bmashup.capacity] low_unit_bytes`) | reported | checked | - |
| LOD lighting table | at 0xC0 | at 0xB0 | moved (9-B records, length from the max quad index) | OFFLINE-VALIDATED | drawn |
| **Emitter lists** (LOD: 0x20-B header + 0x30-B records at the tree end; MC: a second list) | particle / light emitters (HYP) | none | **dropped** (351 WM; 367 + 210 MC) | strict rules | no particles (content loss) |
| LOD tail / instance arrays | nprop = STATIC +0x34 | same | copied | OFFLINE-VALIDATED | drawn |
| Instance models (0x70 records, LOD structs by flag +0x62, vertex stride 20 / 24 / 40) | same | same | copied | strict reader | **variable strides RUNTIME-UNVERIFIED** individually (the track draws) |
| Backdrop / chevron / water / reflection groups | +0x54 relative to the model | relative to the group entry | rebased by the writer | OFFLINE-VALIDATED (37 / 37) | drawn |
| Unit culling prism (+0x10..+0x4F) | same | same | copied | byte copy | drawn |

## 2. Collision and surfaces

| Item | Rev | B3 | trackconv | Layout | Behaviour |
|---|---|---|---|---|---|
| Collision tree nodes | 12 B (plane, outer f32, idx, axis, kind), tag 0x0041CB14 | 8 B, tag 0x00417831 | outer float dropped (not exactly derivable: 61 / 12,544 equal the bound) | bolib `collision.check` 0 problems; serialise identical | drivable (WM_RUN1, MC) |
| Surface word (quad +4) = `CB4CollisionTag`: low byte `EB4CollisionSurface` 0..40, high byte flags | same enum | flags read: 0x10 car query A, 0x01 audio ray, 0x02 / 0x20 AI ground, 0x04 / 0x08 camera | retail-occurring words kept; others need a **profile fallback whose target is retail**, else REFUSED | census of 2,129,291 retail quads | identity words drive as retail |
| **Kill planes** (0x27 Lava, 144 quads 176 m below WM) | kills / respawns | no retail kill-plane word | mapped to 0x21 Invisible (WM): never to a drivable floor | checked | **a car that falls is not reset by a plane** (HYP; WM ravine floor note) |
| Tall invisible walls (0x26 PointOfNoReturn) | boundary | 0x21 Invisible | fallback | checked | RUNTIME-UNVERIFIED (203 quads) |
| MC fallbacks 0x4204 / 0x430A / 0x1004 / 0x1021 | dirt / grille with flags | nearest retail word of the same class | profile fallback | checked | RUNTIME watch items (sound / grip) |
| **Static collision tree (STATIC +0x54, K tracks)** | present on Revenge K tracks | no field | the strict reader REFUSES the track (no K support) | negative D | - |

## 3. Materials and textures (static.dat, enviro.dat)

| Item | Rev | B3 | trackconv | Layout | Behaviour |
|---|---|---|---|---|---|
| Texture record (0x80 D3D + texels, linear DXT, mip chain) | tail +0x40 f32, name +0x44, +0x64 mips<<8 \| bpp | tail +0x40 = 0x20, f32 +0x44, name +0x48, +0x68 mips | tail converted; texels copied | 37 / 37 retail round trip | drawn |
| **DXT3 (0x0E)** | 76 / 133 WM, 146 / 200 MC | never in retail static.dat (DXT1 4,052 / DXT5 5,188 textures); the host decodes 0x0E on every backend (FACT, xboxrecomp-021) | KEPT; tex-replace accepts it with a note | checked | RUNTIME-OBSERVED drawn (WM_RUN1) |
| Texture sizes | - | retail max side 1,024; 273 / 9,240 partial mip chains | tex-replace: power of two, <= 1,024, 1..full mips, exact chain size | 10 negatives (C1) | replaced textures RUNTIME-UNVERIFIED |
| Material +0x24 flags | Revenge sets 0x1000 on every material, **0x2000 on two** (the light cards) | B3 state setup `sub_000393C0` reads the low byte + 0x200 (UV scroll) + 0x400 (z-write off); **never 0x1000 / 0x2000**; no flag selects an additive blend (FACT, WM-5) | 0x3000 cleared; the B3 strict reader refuses 0x3000 bits; `mat-flags` only within the 69 retail (type, flags, ntex) combinations unless `--allow-nonretail` | C3 + negatives | retail combinations behave as retail (HYP for new uses) |
| **Additive 0x2000 cards** | additive light cards (HYP, strongly supported: black-background DXT1, alpha 255) | no additive mode: alpha-blended -> **black slab** (FACT, WM-5 cause 1) | `fixes.alpha_card`: DXT1 -> DXT3 with alpha = luminance x gain, grey colour; `white_colour` + flags 0x42F for god-light cards (retail KS_godlight form); stage 2 lists every 0x2000 material | OFFLINE-VALIDATED (reproduces WM-6) | **RUNTIME-UNVERIFIED** (the rev_1b cloud frames were not reached) |
| Material 0x1240 -> 0x240 (WM m100) | - | not a retail value | kept (reported) | - | RUNTIME-UNVERIFIED |
| MC m148 type 0 flags 0x05 without a texture (18 backdrop refs); m60 type 0 0x60 | - | combinations absent from retail | kept; `inspect` flags "not a retail combination" | - | RUNTIME watch items |
| Animated materials (+0x0E / +0x10) | same | same | copied | checked | - |
| enviro.dat (clouds, envmap, gradient, P8 sun) | +0xAC 0, +0x64 tail | +0xAC file size, +0x8C stamp 0x0012FB40, P8 tail rule | converted (37 / 37 retail round trip) | OFFLINE-VALIDATED | drawn |
| Retint (DXT colour endpoints) | - | - | `retint`: endpoints scaled; DXT1 4-colour / 3-colour+transparent mode preserved by swap + index remap; alpha verified unchanged by decoding | C2 + mutants M1 / M6 | RUNTIME-UNVERIFIED |

## 4. Props, objects, traffic, AI routes (static.dat props, PropInst.dat, Gamedata.bgd)

| Item | Rev | B3 | trackconv | Layout | Behaviour |
|---|---|---|---|---|---|
| **Revenge object lists: props** (0x50-B prop records + LOD + 0xB8 physics; placements in PropInst.dat) | 18 types / 501 placements (WM), 27 types (MC) | prop types 0x70 B + placements + per-unit lists (other system) | **dropped**; B3 prop section written in the retail empty form (US/C5_V1) | strict | no props (content loss; tier A work: est. 1-1.5 weeks HYP) |
| **Parked vehicles (S2 T6)** | 17 per set on MC | B3 sets have no T6 table | profile `t6`: `refuse` (WM) or `drop` (MC: the header pair removed, records unreferenced) | negative D | no parked cars |
| Traffic vehicle lists | Revenge vehicle IDs | must name B3 models | taken from the host's set | B3 reader checks | traffic of the host's kinds |
| Trigger detour bytes (+0x53..+0x57) | detour idx / is-detour | kill / splitters / lights | reordered; a used detour byte is refused | checked | - |
| **Crossovers (S4 chunk F)** and chunk E (slice environment) | 10 crossovers | no v3 counterpart | **dropped** | S4 v3 written by ct2_route (36 / 36 retail) | AI near former crossovers may misbehave (HYP) |
| S4 ramp bytes (zone +0x80) | 0x80 0x80 | 0 on all 36 retail | set to 0 | checked | - |
| Lanes | WM 70, MC 126 | 64 in the table; more need `[bmashup.capacity] lanes` (<= 255; 80 runtime-validated) | stage 4 refuses a profile whose lanes are below the route's | checked | 126 lanes ran in rev_1b (I3) |
| S1 grid / lap lines | 6 slots, caps 4 / 4 / 13 | caps 2 / 2 / 12 | Revenge page on the host template; over-cap lines refused | checked | grids drive (MC slots 1 / 2 watch) |
| S1 Revenge trigger data (336 B), S5 camera | present | no reader | dropped | - | - |
| Crash junction events | - | host S1 pages | a host with several S1 pages is refused | negative D | none |

## 5. Audio, IDs, packaging

| Item | Rev | B3 | trackconv | Status |
|---|---|---|---|---|
| SOUND.AWD | dictionary `Sound`, Revenge prop hits | per-track bank | donor's six files byte-copied (SOUND, CRASH1-3, E_DJRACE, MUSIC) | audio unheard in headless runs |
| Track ID / Gamedata rename | - | RR_NN_VN; 11 fields on an M1 host (`bmpack.rename_gamedata`) | package stage | OFFLINE-VALIDATED (both mods identical) |
| Region letter / DJ bank | - | declared letter not U / E / A; DJ bank a retail placeholder | checked | RUNTIME-VALIDATED (WM_RUN1, rev_1b merge) |

## 6. What a passing toolkit run proves, and what it does not
- PROVES: every output byte is in B3 layout under rules that reproduce retail files; content bytes equal the source's;
  budgets fit; the host's own readers accept the mod (bmpack validate); the conversion is deterministic; the two shipped
  mods are reproduced byte for byte from the disc image.
- DOES NOT PROVE: appearance (blend modes, vertex alpha, fog, LOD distances), collision feel (surface fallbacks), AI
  quality, audio. Those need a guarded runtime check at the owner's real settings over the whole lap (playbook s7.2).
