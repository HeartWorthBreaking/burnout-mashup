# Example (e): data-only content mod template

`mod.toml` declares content the Burnout Mashup host adds to the game, with no code and nothing to approve:

| table | what | limits in the reference host (p3; the same as p2) |
|---|---|---|
| `[bmashup]` | `platform = ">=0.1"`, `requires = [...]`: what the mod needs | an unmet need refuses this mod alone (`[PLATFORM]` line) |
| `[bmashup.regions]` | a new main region (`"O = OCEANIA"`), its announcer bank | up to 23 regions (letters other than U / E / A) |
| `[bmashup.tracks] add` | added track entries `RR_NN_VN` | 383 tracks in the list (36 retail) |
| `[bmashup.tracks] names / locations` | the texts the menus show | 27 / 17 characters, `A-Z a-z 0-9 space - ' . &` |
| `[bmashup.extra_events]` | added World Tour race events on added tracks (retail regions) | 35 in all mods; a location's list shows 6 rows (retail + added) |
| `[bmashup.capacity]` | engine capacity the tracks need | see `../capacity/` |

Every table has `version = 1`. On a platform host (p1 / p2 / p3) an unknown table, a newer table version or an unknown key refuses
THIS mod alone when the mod list is made (`[PLATFORM] mod ... refused, the game starts without it: ...`); a malformed
entry, a text the menus cannot show, or a clash with another mod (a track ID two mods add) still stops the start (exit 92,
the mod named). Plain Takedawn reads only `id / name / version / author / description`. Check a mod offline with the kit's
`tools\bmpack\bmpack.py validate` (the host's real readers and the platform gate).

## The files (NOT included: never copy game data into a mod you share)
Each added track needs its own folder beside `mod.toml`:

```
<your mod>\
  mod.toml
  files\Tracks\US\C6_V1\Gamedata.bgd   static.dat   streamed.dat   enviro.dat   (required: the host checks these four)
                        + the audio / crash files your track uses (the research fixtures carry CRASH1..3.RWS,
                          E_DJRACE.xwb, MUSIC.RWS, SOUND.AWD)
  files\Tracks\OC\C1_V1\...
```

They come from YOUR track build (your own geometry, route and data tools). The Burnout Mashup research fixtures were
copies of retail tracks with renamed IDs, made locally from the owner's own game files; such copies contain the game's
data and must stay on your machine. The SDK ships no game file of any kind.

A track's Gamedata.bgd must carry its own race records (or the host's documented fallbacks apply: World Tour
WT_REPORT; Single Event OFFSGRCF); a route with more than 64 AI lanes needs a `[bmashup.capacity] lanes` declaration.

Offline evidence: `verify_sdk.py` part 5 reads this file with the host's real readers (manifest, regions, tracks, names,
extra events, capacity) and checks 10 one-line variants are refused with the reader's own reason.
