# Example packs (bmpack specs only - NO game data)

| folder | spec | mod id | content | launched |
|---|---|---|---|---|
| `content-pack\` | `bmp_content_pack.toml` | bmashup.bmp-content-pack 1.0.0 | US_C8_V1 "Harbour Lights" (donor US_C1_V1), World Tour events at US_C3 Silver Lake | p1 51-54, p2 55 / 56 |
| `track-pack\` | `bmp_track_pack.toml` | bmashup.bmp-track-pack 1.0.0 | EU_C8_V1 "Canal Lights" (donor EU_C3_V1), World Tour event canal-dash at EU_C1 | p1 51-54, p2 55 |
| `events-pack\` | `bmp_p3_events_pack.toml` | bmashup.bmp-p3-events 1.0.0 | US_C8_V1 + two Silver Lake events with their own row names / help texts (`[bmashup.extra_events] version 2`) | p3 bmp_p3_1 |
| `deps-base\` | `gp_deps1_base.toml` | gp.deps-base 1.0.2 | no content; tune Takedown BP 1500 - the dependency | deps1_1, gp_p4c_1 |
| `deps-addon\` | `gp_deps1_addon.toml` | gp.deps-addon 1.0.0 | `requires_mods = ["gp.deps-base >= 1.0.2"]`, platform >= 0.1.2, events >= 5; tune Trading Paint 6 | deps1_1, gp_p4c_1 (admitted) |
| `deps-newer\` | `gp_deps1_newer.toml` | gp.deps-newer 1.0.0 | `requires_mods = ["gp.deps-base >= 1.1"]` - NEGATIVE: refused alone (NEEDS MOD, has 1.0.2) | deps1_1, gp_p4c_1 (refused) |

`expected_mod.toml` is what bmpack 1.3 / 1.3.1 builds: byte-identical to the launched sets' mod.toml (`bmp_content_set`,
`bmp_track_set`, `bmp_p3_events_set`, `gp_deps1_set`); the kit's release check rebuilt every pack and compared every file (kit 0.4.0).
content-pack and events-pack both add US_C8_V1: installed together the later one is refused alone. The deps specs are the
bmpack 1.3 tool's own fixtures (`tools\bmpack\specs\gp_deps1_*.toml`, byte copies). Build (local only - the track packs copy
YOUR retail track data under a new ID and must never be shared):

```
rem bmpack 1.5.0: no host tree needed; give your game data with --game-data "<game data>"
py -3 -B tools\bmpack\bmpack.py build examples\mods\deps-base\gp_deps1_base.toml <new set folder>
py -3 -B tools\bmpack\bmpack.py build examples\mods\deps-addon\gp_deps1_addon.toml <another new folder> --with <new set folder>\deps-base
py -3 -B tools\bmpack\bmpack.py build examples\mods\deps-newer\gp_deps1_newer.toml <a third folder> --no-validate
```
A dependant is validated together with its dependency (`--with`); the negative fixture is refused by design, so it is built
without validation (`--no-validate`), exactly as the launched set `gp_deps1_set` was.

These are research fixtures, not shareable content.
