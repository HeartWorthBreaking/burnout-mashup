# carimport design: interchange choice, slice scope, format mapping (worker carimp, 2026-10-27)

Labels: **SRC** read in code (default.xbe / p4.2 generated code), **OFF** offline-tested, **RT** runtime-observed, **HYP** not proven.
Format base: s6 atlas `gp\atlas\CARS.md` s1.2 and the strict reader `atlas\scripts\cars\bgvlib.py` (sha256 b5df11b9...0a61, used
read-only for donor parsing and as the independent strict check of every written file).

## 1. Interchange format: glTF 2.0 (not OBJ)
| need | glTF 2.0 | OBJ |
|---|---|---|
| units / axes | defined: metres, +Y up, +Z front, right-handed | undefined (tool-dependent) |
| hierarchy / part naming | node tree with names and TRS (body, wheel, LOD nodes) | flat groups / objects only |
| UVs, normals | typed accessors | yes (no tangent space, no strictness) |
| vertex colours | COLOR_0 explicit -> can be REFUSED precisely | non-standard extensions |
| materials | per primitive, PBR + `extras` (our class tag) | MTL, loosely specified |
| skins / morphs / animation | explicit -> refused clearly in slice 1, usable in later slices | absent |
| tooling | Blender / Maya / 3ds Max exporters, validators, binary .glb | ubiquitous but lossy |
Decision: glTF 2.0 (.gltf + .bin or .glb), PNG images. The strictness requirement ("reject, never drop") needs a format whose
unsupported features are explicit; glTF names every one (skins, morph targets, extensions, extra attributes).

## 2. Scope of slice 1 (what is AUTHORED, what is NEUTRAL / DONOR, what is REFUSED)
| element | slice 1 | basis |
|---|---|---|
| body geometry, all 4 LODs | AUTHORED (LOD 3 = `body`; LOD 0..2 = `body_lod0..2` or reuse of LOD 3) | OFF + RT |
| vertex layout VB0 (pos f32x3, NORMPACKED3, uv f32x2) | written; normals packed 11:11:10 (x, y *1023, z *511) | OFF (T2, T5, mutants) + RT |
| index layout | u16 D3D triangle STRIPS (primitive 6), degenerate joins, edge continuation; odd triangles reversed by the GPU | SRC sub_00031AB0 (draw 6) + OFF T1 / T5 |
| winding | CCW-front in the car frame (retail: 146426 of 146580 non-degenerate even-order triangles agree with their stored normals) | OFF + RT (faces visible) |
| coordinate system | glTF frame == car frame: +X LEFT, +Y up, +Z front, metres. Evidence: retail roof sponsor text reads un-mirrored in a right-handed render (rotated 180 deg = readable from the front); runtime: the AUTHORED fin modelled on +X appears on the car's left in the chase camera (gp_carimp_2 / _3) | OFF + RT |
| scale | metres (retail compact 2.03 x 1.27 x 4.15 m) | OFF |
| UVs | glTF TEXCOORD_0 unchanged (top-left origin both sides); PNG row 0 = texture row 0 | OFF T5 + RT (decals in place) |
| materials | class -> draw record: paint = flags 1 / slot 0 (paint shader), plain = flags 2 / slot 0, glass = flags 0x100 / slot 2 / alpha 0.4118 (retail values); draws ordered paint, plain, glass; list aux = glass draw index | SRC sub_00031AB0 / 000300A0 + RT |
| texture | ONE 512x256 P8 NV2A-swizzled texture in-file + 1..8 palettes; exact colours when <= free entries, else median cut | OFF T3 / T5 + RT |
| paints | paint mask -> 64-entry luminance ramp at palette 64..127; palette p = paint colour p x level; other entries identical | OFF T4 + RT (teal / orange / violet cycled in the garage) |
| bounds | +0xE80 AABB (max xyz 0, min xyz maxz - retail pattern) from LOD 3; +0x14 radius = max(authored, donor radius x authored / donor geometry radius) | OFF; HYP: consumers of +0xE80 not all traced |
| deformation VB1 (u16 boneA*3, u16 boneB*3, u16 wA, u16 wB, sum 255; 8 crush bones) | NEUTRAL: `transfer` = nearest donor LOD 3 body vertex after AABB mapping; `rigid` = all on bone 3 (index 9, donor mid-body); wheels bone 0 / 255 as retail | SRC sub_00031E70 (8 / 2 matrices) + RT: both cars crashed and rendered in the damaged path (shape quality not judged) |
| wheels | AUTHORED `wheel` node, or GENERATED neutral cylinder (radius = donor +0x18, width 0.22 m); drawn by the game at the donor's wheel matrices (+0xB80) for lists L7 / L8 / L9 | SRC 0x30C83..0x30E09 + RT |
| detachable parts L1..L<locators> | NEUTRAL: one zero-area draw each (the game still runs its part logic; nothing visible detaches) | SRC (null list would crash 0x30AD8) |
| glass break | NEUTRAL zero-area glass draw when the body has no glass (whole list aux stays valid, as in all 67 retail cars) | SRC 0x300A0 |
| extra lists +0x64 / +0x68 | omitted (retail COMP/Car5 and CUPE/Car1 have none) | OFF |
| collision hull (+0x1060), header matrices, wheel / locator / crush tables, emitters (lights, exhaust, smoke points), engine-sound descriptors (+0x16DC / +0x16E0), engine audio .hwd / .lwd | DONOR (copied; local-only labels) - the authored body must fit the donor envelope (+-30 % per axis, refused otherwise) | RT: drives, contact with rivals, crash junctions |
| physics, garage photo, career index, name | cars2 host (donor's ValueDB file, donor's photo, host text) | cars2 |
| lights (draw flags 0x4..0x80), second texture slot (0x10002), vertex colours, skin from the source, morphs, animation, extra parts, attachments | REFUSED with a message | OFF T6 (28 negatives) |
| slot budget | file <= 0x9D800 (645,120 B), multiple of 0x800 - refused above | SRC (STREAMING_POOL_MAP) + OFF (retail LOD3 x4 refused) |

## 3. Render path facts used (SRC, default.xbe; disassembly via atlas scripts\cars\cdis.py)
- `sub_000303D0` (model draw): LOD head from model +0x4C..; stream 0 = VB0 stride 0x18, stream 1 = VB1 stride 8
  (`sub_000315C0`); undamaged (+0x101B == 0) -> whole list (LOD +0x60) with vertex shader [0x4D6540]; damaged -> L0 with
  [0x4D6544] and 8 crush matrices from car +0x500 (`sub_00031E70`, ecx 8), parts L1..L<+0xC> each with 2 matrices
  (state car +0x4B2+i: 3 = own matrix, 4 = not drawn); wheels: for i < +0xD, list L7 / L8 / L9 picked by |spin| at car
  +0x4E8+4i against [0x3B16B8] / [0x3A795C], drawn at car +0x20+0x40i; attachments: L10+ (HEVY/Car27 only).
- `sub_00031AB0` (draw record): +0x1A selects the texture slot (ctx +0x334 + slot*4; slot 0 = the model's texture), flags & 2 ->
  pixel shader [0x4D6558] with +0x14 as a constant; flags & mask & 0xFC -> [0x4D655C] (light groups); flags 1 -> paint shader
  [0x4D6550] / [0x4D6554] (kind != 0); 0x100 -> glass [0x4D6548] with +4 as alpha; DrawIndexed(6 = strip, u16 count +0x10, +0xC).
- `sub_000300A0`: glass state of list aux (2 / 3 / 4 = intact / cracked / broken alpha).

## 4. Validation
- Offline: `tests\run_tests.py` 48 / 48 (logs\tests.json): T5 CONTROL = retail COMP/Car1 exported to glTF and rebuilt: all 4
  LODs give the same triangles (by position), orientation, normals (<= 0.002) and UVs per class, texel colours identical; T7
  mutants (normal z sign, x/y swap, reversed winding, truncated strip, paint written as plain, unswizzled texels) all caught.
- Runtime (p4.2 exe 4fd86d1066ae, no host change): see `runtime\CARIMP_RUN_REPORT.md`.
