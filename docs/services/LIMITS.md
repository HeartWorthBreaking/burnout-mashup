# Host limits for content mods (platform 0.1.9, mainline host main19 `bmp-0.1.9+0620fe316156`; content limits as capmega1 / p4.4, plus the main18 mod-limit rows and the main19 memory / service rows)

Distinguished as the owner asked: **format ceiling** (what the encoding can represent) / **configured** (the host's limit) /
**offline-tested** / **runtime-demonstrated**.

| limit | format ceiling | configured | offline-tested | runtime-demonstrated |
|---|---|---|---|---|
| mod.toml size | - | **65536 bytes** (p4.3 M3; = the mod file layer's state size every reader already uses) | 65,536 accepted / 65,537 refused by parse, gate, mod list; 900 cars in 65,536 B | 22,785 B (512 cars, gp_p43_5) |
| vehicle list | 2^31-1 signed count; practical: host text IDs (~13.7k) (veh SCALE_TARGETS) | **1024** (917 addable) | 128 / 129 / 1024 / 1025 | 1024 (veh1 R2d), 633 / 640 (gp_p43_5) |
| series | 118 (class 10..127, signed byte) | **64** | yes | 2 authored + 46 fixture (veh1); 1 on p4.3 |
| cars listed per series | 20 (list object rows, not relocated) | **20** | 20 / 21 | 20 |
| paints per car | 127 (signed byte) | **64** (incl. retail) | 64 / 65 (SCALE_TARGETS) | 8 on the BM Coupe |
| paint declarations / resident palettes | - | 4096 / 1024 | budget 1024 | - |
| texture pool | 64 MiB window (game peak ~38 MB) | **12 MiB** contiguous | filled + one more mod refused | 561,152 B (gp_p43_2) |
| texture entries all / per mod | TXD table 4096 rows (fetex) | **768 / 256** | yes | 17 |
| texture mods / bytes per entry | the texture pool above (the mods count is host memory only) | **64** (0.1.7: 16) / 1 MiB | admission 64 / 65 (bmpack 1.4.0) | 3 |
| photo bindings all / per car mod | - | **512 / 256** | 256 / 257, 512 / 513 | 2 |
| map slot bindings | slots of the 3 donor maps | 48 (one 4th region) | yes | 15 |
| World Tour 4th region | one region, one location | 1 / 1 / 6 events | yes | OCEANIA, 2 events |
| AI route lanes (`[bmashup.capacity] lanes`) | 255 | **1..255** (64 retail + extension) | yes | 80 (p1 / p3), 126 (lineage), 76 used of 128 declared (USA Marathon, mega1) |
| STATIC pool (`static_bytes`) | 0x20C4000 | game 0xD00000; request a page multiple above 0xA00000 | yes | 0xD01000 (rc_acc_1), 0x1499000 (USA Marathon, mega1); 64 MB window budget: CAPACITY.md |
| GAMEDATA slot (`gamedata_bytes`, platform 0.1.7) | 0x800000 | game 0x176000; request a page multiple 0x177000..0x800000 | 20 checks + 3 mutants (bm_gdslot) | 0x200000 (USA Marathon, mega1) |
| installed mods (platform 0.1.8) | none (host memory) | **256** (0.1.7: 64; `BO3_MOD_LIMITS=legacy`: 64) | 64 / 65 / 256 / 257 (loader + bmpack 1.4.0) | pending (acceptance > 64 mods) |
| mod folders (platform 0.1.8) | `BMASHUP_MODS` one environment value, 32,767 characters; `BMASHUP_MODS_FILE` 1 MiB | **256** (0.1.7: 8) | 8 / 9 / 256 / 257 both ways; 55,552 characters through the file | pending |
| music mods (platform 0.1.8) | 100 soundtracks (ST.DB) | **64** (0.1.7: 16); 256 tracks in all (unchanged) | 64 / 65 (admission) | pending |
| switched-off ids (mod list) | - | **1024** (0.1.7: 256) | 1024 / 1025 (file 69,760 B) | - |
| plugin approvals | 64 KiB file | **448** (0.1.7: 256) | sizes | - |
| plugin settings | - | **8 a plugin / 128 in all** (0.1.7: 6 / 32) | settings v2 suite (svc_b_t3) | - |
| bmashup.patch patches in all | - | **256** (0.1.7: 64) | yes | - |
| mesh material rows per unit (BMRX, platform 0.1.7) | 127 virtual rows | 83 retail rows + extension | 1,134,260 checks (240 blocks) + mutant | up to 127 (USA Marathon on mega1, 63 units with extension) |

Failure behaviour: a declaration beyond a limit refuses its WHOLE mod at admission (logged, Mods page reason, rolled back);
first-use failures (palette / texture memory) fall back to retail / donor / paint 0, logged and counted. Not tried at runtime: a
texture allocation failure, the 917-car tier as one mod, a language switch.

Platform 0.1.8 build option: `BO3_MOD_LIMITS=legacy` (CMake) gives capmega1's values for the mods / folders / music / texture / off-id /
approval rows above (the unmodified capmega1 mod-folder test passes on it). Loose files of a mod folder are listed at the start
(`LIMITS_AND_BEHAVIOURS.md` 0e).

## Platform 0.1.9 rows (main19)
| limit | format ceiling | configured | offline-tested | runtime-demonstrated |
|---|---|---|---|---|
| guest contiguous window | 256 MB (the game masks addresses to 28 bits) | **256 MB** (0.1.8: 64 MB; `BO3_GUEST_WINDOW_MB=64`) | 64 checks at 64 MB-1 .. 256 MB, 13 compare mutants | mem256 host: expansions at 160-180 MB (m256_stress) |
| high zone for host expansions | 192 MB | everything above the game's 64 MB | budget gate unit tests + 4 mutants | 123,316 KB peak (incl. a 96 MB test block) |
| hook points | - | **13** (0.1.8: 7; all offered on 0.1.9) | framework 77 checks | RT (validation rounds) |
| racers 3 light changes | - | 10 a second per racer | yes | RT |
| traffic crash pool | 64 slots (no full check in the game) | wreck needs >= 4 free, < 8 crashing; 4 a second per plugin | pool guard 17 checks + mutants | RT pool peak 8 / 64 at density 3.0; wreck UNAVAILABLE |
| hud 2 draw commands | - | 64 a plugin / 256 a picture, 1024 text glyphs a picture | yes | RT quads / text; RT sprites |
| HUD sprites (`[bmashup.textures]`; there is no `[bmashup.hud]` table on 0.1.9) | high zone | the textures table's limits: 256 entries a mod, 768 entries / 12 MiB in all; 64 KiB draw block | yes | RT (see HUD_V2.md) |
| camera 2 finish poses | - | ONE pose a race, within 40 m of the end-of-race camera | yes | RT accepted |
| paints dynamic palettes | signed palette index (127) | index 127 for player 0; 2 units x 0x440 B; 30 changes a second | 41 checks | RT (colour changed in a race) |
| menu declarations | title lists 10 rows | 8 popups / 4 mode rows / 2 bars; texts 16 KiB | 58 checks | RT popup + mode row; bars UNAVAILABLE |
| rules eliminations | - | 1 a second | 34 checks | RT |
| services | 32 (registry) | **25** (0.1.8: 22) | registry checks | RT (log: 25 services offered) |
