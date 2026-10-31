# Texture packs with fetex 0.2.0

A texture pack is a data mod that registers front-end textures; other mods (or the same one) bind them to places in the game.

## 1. A garage photo for a car (P8 with one palette per paint)
1. Draw the photo once per paint: 128 x 64 PNGs (any power-of-two size 4..1024 works), the SAME picture in each, only the
   paint colours differ (every pixel class of the first picture keeps one colour in each other picture).
2. Spec `photo_spec.json`:
   `{"tag": 0, "entries": [{"name": "mycar_photo", "png": "src/paint0.png", "format": "P8", "palettes": ["src/paint1.png", ...]}]}`
3. `py -3 -B fetex.py pack photo_spec.json art\photo.txd` (creates nothing on a refusal), then
   `py -3 -B fetex.py validate art\photo.txd`.
4. `mod.toml`:
   ```toml
   id = "my.photo-pack"
   name = "My car photo"
   version = "1.0.0"
   [bmashup]
   platform = ">=0.1.5"
   requires = ["bmashup.textures>=1"]
   [bmashup.textures]
   version = 1
   txd = "art/photo.txd"
   class = "frontend"
   ```
5. Bind it from the car's mod: `[bmashup.cars]` `photos = ["COMPMY1 = my.photo-pack/mycar_photo"]` and
   `requires_mods = ["my.photo-pack >= 1.0"]`. Palette i is shown for paint i.
Worked example: `examples\p43-coupe-photo` (6 paints = the carimport coupe's paints; its mod.toml expects `art\photo.txd`:
`py -3 -B fetex.py pack examples\p43-coupe-photo\photo_spec.json <mod>\art\photo.txd` after copying the folder to `<mod>`).

## 2. World Tour map art (DXT1 / DXT5) - `examples\fetex-art`
`py -3 -B examples\fetex-art\make_packs.py <new set folder>` computes the art (`gen_art.py`), packs `photo.txd` and
`oceania.txd`, and writes two mods:
- `fetex-photo` (bmashup.fetex-photo): the photo `compbm01_photo` (8 paints);
- `fetex-oceania-art` (bmashup.fetex-oceania-art): 6 map tiles, overview, area view, 4 city layers (DXT1), the map marker
  icon / pulse / hollow (DXT5), plus place name and ticker; `[bmashup.wt_map_art]` binds them to the map's texture slots
  while the OCEANIA page is shown. It `requires_mods` the World Tour region mod `bmashup.wt4-oceania` (a content example of
  the mod kit), so install both.
- optional `--cars2-files DIR`: the DERIVED `fetex-car-photo` (cars2's COMPBM01 model + this photo); needs the cars2 example's
  model files built from your game data (hash-checked); local only.
The art folder (sources + TXDs) is written beside the set as `<set>_art` (or `--art DIR`).

## 3. Choosing a format
| content | format | why |
|---|---|---|
| photo with paints | P8 + palettes | one palette per paint, the game switches palettes |
| opaque map art | DXT1 | 4 bits / pixel, no alpha |
| icons, markers with transparency | DXT5 | smooth alpha |
Encoders are deterministic range fits (not quality-optimised): `extract` the packed file to PNG to check the look.

## 4. Errors you may see
| message | fix |
|---|---|
| `format 'DXT3' is not supported. Use "P8" ..., "DXT1" ... or "DXT5"` | change `format`; DXT3 is not in the host's front-end list |
| `picture ... is 48x32; both sides must be powers of two` | resize to the suggested size |
| `picture ... cannot be read ... 8-bit, non-interlaced PNG` | re-save as 8-bit RGBA PNG (no 16-bit, no interlacing) |
| `palette picture ... does not map 1:1` | the paint pictures differ in more than colour: redraw from the same layout |
| `... outside 4..1024` / `... entries; at most 64` | split or shrink the pack |
| `INVALID texture dictionary: ...` | the .txd is not a Burnout 3 Xbox texture dictionary (or damaged) |
| `the folder ... does not exist` | create the output folder first |
