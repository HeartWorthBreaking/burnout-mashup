# Cars, series and paints as data mods (platform 0.1.6): `[bmashup.cars]` 1 / 2, `[bmashup.series]` 1, `[bmashup.paints]` 1

Data only, no approval. Contracts: the veh1 and cars2 interfaces (summarised here), `CONTRACTS_CONTENT` s1 / s3. Tools:
`tools\vehtool` (validate / fixtures / palettes / package), `tools\carimport` (authored car models), `tools\fetex` (photos).
Examples: `examples\authored\veh-series` (Neon, Dust Runners, retail-car paints, a cross-mod paint: `make_veh_packs.py`),
`examples\authored\bm-coupes` (a new series with the AUTHORED carimport coupe, its AUTHORED photo and registered paints),
`examples\content\added-car` (cars2's COMPBM01, built from your data).

## `[bmashup.cars]` version 2 (version 1 files keep working)
```toml
[bmashup.cars]
version = 2
add = ["BMNEC01 = SPRTCAR1"]          # NEW vehicle ID = DONOR (a retail race car)
names = ["BMNEC01 = Neon Dart"]       # 1..21 chars A-Z a-z 0-9 space - ' . &
physics_scale = ["BMNEC01 | Drag Coef = 0.9"]   # Drag Coef 0.25..4, "Max Speed In Boost" (= top-speed limit) 0.5..2
model = ["BMNEC01 = donor"]           # use the donor's model / audio (nothing shipped); default: own pveh\<PREFIX>\<REST>.bgv/.hwd/.lwd
unlock = ["BMNEC01 = cars:30"]        # open | cars:N | car:<RETAIL ID> | series:<CLASS>  (overrides the series rule)
ai = ["BMNEC01"]                      # AI-eligible (validated: retail race-car donor, model resolvable)
photos = ["BMNEC01 = <texture>"]      # own garage photo: P8 128 x 64, 1..8 palettes (TEXTURES.md); else the donor's photo
```
- Vehicle ID = 5..12 characters A-Z 0-9; its first 4 are the class: a retail class (COMP MSCL CUPE SPRT SUPR HSPC HEVY: the car
  joins that series, cars2 rule) or a prefix declared in `[bmashup.series]`. Canonical ID `<mod-id>/<id in lower case>`.
- Own model files: `pveh\<PREFIX>\<REST>.bgv` (<= 0x9D800 bytes), `.hwd`, `.lwd` (carimport builds them from an AUTHORED glTF).

## `[bmashup.series]` version 1
```toml
[bmashup.series]
version = 1
add = ["neon = BMNE"]          # local name = 4-letter prefix (A-Z, not a retail class, unique across mods)
names = ["neon = Neon"]        # the garage header, 1..21 chars
unlock = ["neon = cars:10"]    # default rule of the series' cars (default open)
ai_class = ["neon = SPRT"]     # REQUIRED: the retail class whose cars race a car of this series when none of its cars is AI-eligible
```
Game-facing class code = 10 + admission index (never saved).

## `[bmashup.paints]` version 1
```toml
[bmashup.paints]
version = 1
add = ["sunset = COMPCAR1 | ramp FF8800 301000",                 # recolour the car's own paint ramp (authored colours only)
       "chrome = bmashup.veh-neon/bmnec01 | file paints/chrome.bmpal"]   # an authored 256 x BGRA palette (1024 B)
default = ["BMNEC01 = sunset"]
```
Paint index of a car: retail palettes 0..n-1, then registered paints in (admission order, name) order. Texel liveries per paint
are NOT supported (v1 refuses them). The garage photo follows the paint: palette k for retail paint k; a ramp paint = the same
ramp on the photo's palettes (p4.3 fix 1); a `file` paint = photo palette 0.

## Limits (configured; SCALE_TARGETS)
| limit | value | runtime-demonstrated |
|---|---|---|
| vehicle list | **1024 entries** (917 addable; retail 107) | 1024 (veh1 R2d, entry 1023 raced); p4.3: 633 / capacity 640 with the 512 fixture as ONE mod (gp_p43_5) |
| series | 64 | 46 fixture + 2 authored (veh1); "BM COUPES" class 10 (p4.3) |
| listed cars per series | 20 | 20 (fixture rows) |
| paints per car | 64 (56 registered) | crimson / gold on the BM Coupe (p4.3) |
| paint declarations | 4096 | - |
| resident host palettes | 1024 (first use; beyond: paint 0, logged) | - |
| mod.toml size | **65536 bytes** (p4.3 M3; ~4,500 short car declarations) | 22,785 B, 512 cars in one mod (gp_p43_5) |

## Behaviour
- Admission is transactional per mod (`[VEH] REFUSED`): a duplicate vehicle ID, missing files, a bad reference -> the WHOLE mod is
  refused and rolled back; other mods continue (veh1 R1 runtime).
- Cars are player-selectable; `ai` cars appear as rivals (validated rule); a series without AI cars falls back to its
  `ai_class` (fixes the game's divide-by-zero for a class without candidates).
- Nothing is written to the game save: unlock state is derived each time; the chosen paint is kept in `Profile 1 veh.bmprog`
  (sidecar, canonical paint ID); removal -> the profile loads, retail garage; reinstall -> the saved paint back (veh1 R3 / R4,
  p4.3 gp_p43_3 / 4). Saves scanned: 0 added IDs.
- Physics are the donor's (`physics_scale` adjusts the car's own block). Collision hull, wheels, engine audio, emitters: the
  donor's (also for carimport models).

## Evidence (individual vs combined)
Individual: cars2 (gp_cars2_1 / 2), veh1 (7 launches: series, paints, AI, 1024 scale, removal / reinstall, sidecar), carimport
(gp_carimp_2 / 3: authored coupe / wedge raced and crashed). Combined p4.3: gp_p43_5 (BM COUPES with the authored coupe + photo,
paints, AI rivals from the series, the 512 fixture), gp_p43_2 (COMPACT MASHUP with its own photo in World Tour), gp_p43_3 / 4
(removal / reinstall). Not tried at runtime: the 917-car tier as a single mod (512 used), a texture allocation failure.
Final candidate p4.4 (gp_p44_1): registered paints recolour the own photo (fix 1, RT); the list-photo cap follows the photo's
palettes (fix 2, offline only); two visible rows sharing ONE photo texture with different registered paints show the last row's
paint (known limit). Cosmetic: unnamed added cars show "UNKNOWN TRACK" as their name text; locked added cars the generic "ADDED BY A MOD".
