# `[bmashup.capacity]` - engine capacity for big tracks (platform 0.1.9, mainline host main21, mod kit 0.7.0)

*Test records below that name main19_final or an earlier host are the history of those releases.*

**EXPERIMENTAL, Windows x64.** A data mod asks the host for more engine capacity with one table. No code, no approval; the
Mods page labels the mod `CHANGES GAMEPLAY: CAPACITY`. Capacity requests never clash between mods: **the largest request of
each key wins** (logged as `[CAPACITY] mod <id> requires ...: accepted (merged <value>)`).

```toml
[bmashup]
platform = ">=0.1.7"            # needed for gamedata_bytes; older hosts then refuse the mod ALONE at the platform line

[bmashup.capacity]
version = 1
lanes = 128                     # total AI route lanes (64 retail + the lane extension)
low_unit_bytes = 0x1A000        # low-detail (LOD) unit slot
static_bytes = 0x1499000        # STATIC track pool (single view)
gamedata_bytes = 0x200000       # GAMEDATA slot (track route data / traffic / events: Gamedata.bgd) - NEW in platform 0.1.9
```

## Capacity table (host main19_final)

| key | game value | accepted request | min platform | what needs it | status |
|---|---|---|---|---|---|
| `lanes` | 64 | 1..255 total lanes (> 64 uses the host's lane extension) | 0.1.0 | a route with more than 64 AI lanes (else exit **97**) | RT 80 (p1 / p3), 126 (Motor City, lineage host), 128 declared / 76 used (USA Marathon on the experimental host mega1, gp_mega_1..6); 80 on main19_final (cm1_acc_2) |
| `low_unit_bytes` | 0x18000 | a page multiple 0x18000..0x30000 | 0.1.0 | a low-detail unit larger than the game slot (else exit **89**) | RT (lineage) |
| `static_bytes` | 0xD00000 | a page multiple above 0xA00000, at most 0x20C4000 | 0.1.0 | a static.dat larger than the game pool (else exit **90**, truncated) | RT 0xD01000 (capacity example: rc_acc_1 on capfix1, cm1_acc_2 on main19_final), 0x1499000 (USA Marathon on mega1, gp_mega_1..6) |
| `gamedata_bytes` | 0x176000 | a page multiple 0x177000..0x800000 | **0.1.7** | a Gamedata.bgd event (header 0x3000 + record 0x800 + S1..S4) larger than the game slot (else exit **88**) | RT 0x200000 on the experimental host mega1 (USA Marathon, gp_mega_3..6; the same bm_gdslot.c); on main19_final OFF, and granted at boot in cm1_acc_1 (that launch then exceeded the 64 MB window) |

Out of range: the start stops with exit **91** (`[CAPACITY] ... REFUSED` and the reason, e.g. `gamedata_bytes = 0x280800: out of
range (a page multiple above 0x176000, at most 0x800000)`).

## Raised ceilings (this release's host: main21 patches 131 + 132)
The host built from this tree raises the ceilings for detailed tracks. The platform string stays **0.1.9**, so a `platform` line
cannot tell this host from an older 0.1.9 one: an older host refuses a mod that uses `full_unit_bytes` ALONE (platform gate,
"not a key of [bmashup.capacity] version 1") and the game starts without it.

| key / limit | game value | accepted request (this host) | before | what needs it |
|---|---|---|---|---|
| `full_unit_bytes` (**new key**) | 0x28000 | a page multiple 0x28000..0x200000 (10 slots; 2 MiB each at most) | not a key | a full-detail (mesh) unit block larger than the game slot (else exit **89**, "track unit too large") |
| `low_unit_bytes` | 0x18000 | a page multiple 0x18000..0x200000 (18 slots) | ..0x30000 | a low-detail unit larger than the game slot (else exit **89**) |
| `static_bytes` | 0xD00000 | at most 0x4000000 (64 MiB) in the default 256 MB guest window build | ..0x20C4000 | a static.dat larger than the game pool |
| mesh material rows per unit (BMRX, no key) | 83 | up to **255** rows (up to 172 extension rows) | 127 | a unit whose visibility window spans many materials |
| mesh records per block (BMRC, no key) | 128 (s8 chain) | up to **255** records | 128 | a unit with many separate mesh pieces |
| renderer texture cache | Vulkan 256 / D3D11 512 entries | Vulkan 512 / D3D11 1024 | - | tracks with many textures in view |

- Slot expansion is fail-closed: the host checks that the game's slot descriptors are still the game's before it moves them, and
  logs `[UNITSLOTS] full-detail unit slots EXPANDED: 10 x 0x30000 at ...` (and the low-detail line); each loaded unit is checked
  against its slot (`[UNITSLOTS] full-detail unit 0x2D000 bytes in a slot of 0x30000`).
- BMRC: a mesh block with `BMRC` at block + 0xC70 and version 1 at + 0xC74 (the pad after the BMRX header; retail zero) chains its
  records by unsigned 8-bit indices (0xFF = none) instead of the retail signed ones; a block without it is read as retail.
- The memory budget is checked at start (`[MEMWIN] budget OK ... KB of ... KB`).
- FACT (runtime, 2026-11-02, host built from these sources' private reference, one guarded run): a restyled White Mountain track
  declaring `full_unit_bytes = 0x30000` and `low_unit_bytes = 0x22000` loaded units of 0x2D000 / 0x20000 bytes, used 6 BMRX
  extension rows, raced two laps without a fault. Not runtime-tested: the maxima, BMRC on a real track, split screen, Linux / macOS.

## The budget: one 64 MB guest memory window (read this before combining capacity requests)
Every expansion is a NEW region in the game's 64 MB contiguous memory window. The game's own pool stays reserved; it is never
freed or reused (process lifetime). The requests therefore ADD up:

| request | extra window memory |
|---|---|
| STATIC pool 0x1499000 (USA Marathon) | +21.1 MB (the game's 13 MB pool stays reserved) |
| GAMEDATA slot 0x200000 | +2 MB (the game's 1.5 MB slot stays reserved) |
| low-detail slots 0x1A000 | 18 x 0x1A000 = +1.8 MB (the game's 18 x 0x18000 stay reserved) |

FACTS (`[CONTIG]` log lines):
- The USA Marathon alone leaves about 3 MB free after start (61,220 KB in use, gp_mega_6) and runs.
- The USA Marathon plus the capacity example plugin's `low_unit_bytes = 0x1A000` uses 63,060 KB. The game's next allocations are then
  refused (`[CONTIG] refused ...`) and the game faults at start (cm1_acc_1, 2026-10-28).

So, until a host reuses the game's pools:
- a marathon-class mod and other capacity requests that add memory do not fit together;
- keep the sum of the expansions small;
- check `[CONTIG] ... in use` in the log.

## How the GAMEDATA slot works (main19_final, `bm_gdslot.c`)
- The game reads each track event (Gamedata.bgd: header 0x3000, record 0x800, S1..S4 back to back) into ONE buffer of 0x176000
  bytes, described twice (two memory layouts). After the game sets up its memory (the same moment the STATIC pool expansion runs),
  the host checks that both descriptors are still the game's, allocates one region of the requested size and points both at it.
- Fail closed: a mismatch or a refused allocation keeps the game's slot; the GAMEDATA guard then still stops a track that needs
  more (exit 88). Nothing is released (process lifetime), as the STATIC pool.
- Log: `[GAMEDATA] slot EXPANDED ...` (size and address) or `[GAMEDATA] slot: the game's ...` (no request).
- Not a plugin service: only the declaration asks for it.

## Mesh material rows above 83 per unit (BMRX, main19_final `bm_rowx.c`)
- Retail format: a streamed unit's mesh block holds at most **83 material rows**. A track composed from several retail tracks can
  need more where a unit's 17-unit visibility window spans two sources (the USA Marathon needs up to 127).
- Host main19_final reads an OPTIONAL row extension in the mesh block (magic `BMRX` at block + 0xC64, version 1, up to 127 virtual
  rows, extension rows after the retail arrays). A block without it, or with an invalid header, is drawn from the retail bytes
  (one `[ROWX] invalid ...` line); a host without the extension draws the <= 83 retail rows.
- No mod.toml key: the extension is in the track's own streamed.dat. **No kit tool writes BMRX yet** (trackbuild tracks stay
  within 83 rows); the format is described here for authors of converters.

## Marathon-class tracks (more than 64 lanes, more than 83 rows, a large Gamedata)
The host features they need are in the mainline host main19_final (platform 0.1.9): the declarations above plus BMRX. A marathon-class track ran to the finish only on the experimental host mega1 (same feature code); on main19_final it is NOT runtime-validated (out of the 0.4.4 scope) and it must fit the 64 MB budget above. Evidence: `docs\LIMITS_AND_BEHAVIOURS.md`
section 0d. Still OPEN / experimental: **U5** (stale lane data after switching from an expanded track to another track: not
observed, not accepted), split screen with a large STATIC pool (NT), online (refused for added tracks).

## On hosts without these features
- A mod with `gamedata_bytes` on a platform 0.1.6 host (capfix1 and earlier) is refused ALONE by the platform gate; the game
  starts without it. Offline evidence (bmpack 1.3.4 with the capfix1 host readers, the USA Marathon mod with and without the
  platform line): `mod ... refused, the game starts without it: bmashup.capacity.gamedata_bytes is not a key of
  [bmashup.capacity] version 1 (keys: version lanes low_unit_bytes static_bytes): misspelt, or the mod needs a newer platform
  (this host: Burnout Mashup platform 0.1.6)`. Keep `platform = ">=0.1.7"` anyway (it also covers the row extension, which has no key).
- A track that needs more than 83 rows per unit on a host without BMRX draws only its retail rows (missing surfaces), so such a
  track mod should also say `platform = ">=0.1.7"`.

## Tools
- `bmpack validate` (host readers of this release's host) accepts `gamedata_bytes` and `full_unit_bytes`; it does not check the
  RANGE (the host does at start).
- `bmpack build` (package.toml `[capacity]`) writes `lanes`, `low_unit_bytes`, `static_bytes` only: add `gamedata_bytes` to the
  generated mod.toml by hand.
