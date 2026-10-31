# Car, series and paint packs with vehtool 0.1.2

All three are plain data mods (a folder with `mod.toml`, optionally `files\`). The cars below reuse a retail donor's model,
audio and handling (`model = donor`), so the packs contain no game data and can be shared. A car with its own model is made
with carimport (`[bmashup.cars]` + `files\pveh\...`, DERIVED, local only).

## 1. A car pack: extra cars in a retail class
```toml
id = "my.cars"
name = "My extra cars"
version = "1.0.0"
[bmashup]
platform = ">=0.1.5"
[bmashup.cars]
version = 2
add = ["COMPMY01 = COMPCAR1"]            # new ID (class + 1..8 of A-Z 0-9) = retail race-car donor of the same class
names = ["COMPMY01 = My Compact"]        # <= 21 characters
model = ["COMPMY01 = donor"]             # use the donor's model / audio (else ship files/pveh/COMP/MY01.bgv/.hwd/.lwd)
unlock = ["COMPMY01 = cars:10"]          # optional: open | cars:N | car:<retail ID> | series:<CLASS>
ai = ["COMPMY01"]                        # optional: may race as an AI opponent
```
A class lists at most 20 cars; `vehtool inspect` shows the free rows.

## 2. A series pack: a new class with its own cars
1. A 4-letter prefix that is not a retail class (e.g. `BMNE`), declared with a name, optional unlock rule and the REQUIRED
   `ai_class` (the retail class that races a series car when none of its cars is AI-eligible):
   ```toml
   [bmashup.series]
   version = 1
   add = ["neon = BMNE"]
   names = ["neon = Neon"]
   ai_class = ["neon = SPRT"]
   ```
2. Cars whose IDs start with the prefix (`BMNEC01`), `[bmashup.cars] version = 2`, each on a retail donor.
3. Worked example: `bm-veh-neon` / `bm-veh-dust` from `examples\make_veh_packs.py`. Limits: 64 series, 20 listed cars per
   series, 917 added cars in total (1024 vehicle-list entries).

## 3. A paint pack
```toml
[bmashup.paints]
version = 1
add = ["comp-sunset = COMPCAR1 | ramp FF8800 301000",          # recolour the car's paint ramp (needs >= 2 palettes)
       "comp-chrome = COMPCAR1 | file paints/chrome.bmpal",    # an authored 256-colour palette in files/
       "dart-gold = bmashup.veh-neon/bmnec01 | ramp FFE060 403000"]   # another mod's car: list it in requires_mods
default = ["COMPCAR1 = comp-sunset"]                            # optional default paint per car
```
`vehtool inspect-car COMPCAR1 --game-data <data>` says whether ramp paints are possible; `vehtool palette OUT.bmpal --gradient
F0F4FF 202830` writes a file palette. At most 56 registered paints per car. Selections persist in the host's progress file,
never in the save.

## 4. Check and package
```
py -3 -B vehtool.py validate <mod> [<other mods in install order>] --game-data <data>
py -3 -B vehtool.py package <mod> --label AUTHORED
```
`validate` checks mods in the order given (as the host admits them): a duplicate ID, an undeclared series, a missing
required mod, a missing own-model file, too many rows or paints -> `REFUSED <mod>: <reasons>` and exit 1; the host refuses
such a mod whole and rolls it back. A mod.toml larger than 65536 bytes is ignored by the host (split the mod; `fixture`
does this automatically).

## 5. Errors you may see
| message | fix |
|---|---|
| `vehtool: CANNOT RUN: ... none was given` | pass `--game-data` or set `BMKIT_GAME_DATA` (validate / inspect need the retail vehicle list) |
| `CANNOT RUN: ... has no default.xbe` / `... not the North America (NTSC-U) retail one` | point at the prepared NTSC-U game-data folder itself |
| `CANNOT RUN: ... differs from the supported release` | prepare unmodified Burnout 3: Takedown (Xbox NTSC-U) data again |
| `CANNOT RUN: Python 3.x found; ... 3.11 or later` | install Python 3.11+ (tomllib) |
| `mod folder ... has no mod.toml` | give the mod folder itself, not the set |
| `mod.toml is not valid TOML (...)` | fix the line named |
| `--gradient 'x': two colours RRGGBB RRGGBB` | hex colours, e.g. `F0F4FF 202830` |
| `N series hold M cars, K asked` | give more `--series` or fewer `--cars` |
