# Tester bundle 0.1.0 - clean-folder validation (rel2, 2026-10-27)

## Artifacts
| Item | Value |
|---|---|
| validated zip | `bmashup-alpha-tester-0.1.0.zip` sha256 e9efd7f2313521a6dcf8f2058f0e919c2bc1d533315a0898b8e5f47295be1f4d |
| FINAL zip | `gp\alpha\tester_bundle\out\bmashup-alpha-tester-0.1.0.zip` sha256 **72988d546708972188c6e84ddda1d9ca4c8d1e6b6cd778e4f643ffde346035b3** (164 members, 11,435,186 B). Differs from the validated zip ONLY in `docs/FIRST_DEMO.md`, `docs/INSTALL.md` (corrections from the launch) and `BUNDLE.json` (their hashes); every host / tool / mod / script byte is the validated one |
| host | `host/burnout3_gp_p4_4.exe` fa63df57dde6 (= p4.4), SDL2 53e8fa7e9ed4; copy for launches: `build\alpha_tester_0_1_0\` |
| tools in the bundle | carimport 0.1.1 (rel1b, pre-seal `gp\alpha\ported\carimport`), trackbuild 0.2.0 (rel1a, pre-seal `ported\trackbuild`), bmdiag 0.1.0 (rel1, pre-seal `kit041\src_041`); tests folders not copied |

## Offline, clean folder (outside <workspace-root>: the session scratchpad on C:, `...\scratchpad\val1`), minimal environment
PATH = System32 / Windows / Wbem + the Python launcher only; no PYTHONPATH, RECOMP_*, TAKEDAWN_*, BO3_*, HOME, XDG_DATA_HOME.
Script `testing\scripts\validate_clean.py`; logs `testing\runs\val1\install.log|json`, `remove.log|json` (user profile path
redacted). ALL STEPS AS EXPECTED in both phases.
1. zip sha256 checked, unzipped into a NEW folder.
2. `preflight.cmd` before data: exit 1, exactly 1 FAIL = game data, with the fix printed. `play.cmd` without data: exit 3 (refuses,
   nothing started).
3. `prepare.cmd data --copy-from <workspace runtime_data\base>` (stand-in for a tester's installed Takedawn data; read only, base
   mtime unchanged): 718 files, marker manifest 81dc20fd647fb0b1, 3 s.
4. `preflight.cmd`: RESULT PASS (0 FAIL, 0 WARN): every bundle file = SHA256SUMS, exe hash + identity, SDL2 2.32.10, Windows 11 26300 x64,
   15 system DLLs, Vulkan loader 1.4.350, GPU AMD Radeon RX 9070 XT (Vulkan 1.4.355) + iGPU, game signature, xbe sha256, marker.
5. `prepare.cmd demos` (263 s): bm-coupes-series (carimport 0.1.1), bm-test-loop and bm-canyon-ring (trackbuild 0.2.0) -
   each **byte-identical to the runtime-validated reference packages** (coupe = gp_p43a_set p43-coupe-series files; loop =
   gp_trkimp_examples; canyon = gp_trkimp_canyon_set). Re-run: all three skipped (idempotent).
6. `prepare.cmd status`, `play.cmd --print-env`, `remove.cmd list`: OK.
7. After the launch: run.log / UDATA / veh sidecar of the guarded run copied into the folder's profile (EMULATED, labelled in
   `profile\EMULATED_FROM_GUARDED_RUN.txt`); `diag.cmd --bundle . --out diag\bugreport.zip`: 8 members (README, bundle sums,
   diag.json, run.log key / tail extracts, preflight result); no save / progress / game-format member; user name absent.
8. `remove.cmd backup --to <folder>` (6 files: UDATA + sidecar; the backup was then moved to the scratchpad, saves never stay
   in gp\alpha), `remove.cmd clean` without --yes: lists, deletes nothing (exit 2); `clean --yes`: gamedata, profile,
   mods\generated, mods\user, diag deleted; folder deleted: nothing left. The real `%APPDATA%\Takedawn` (25 files) and
   `%LOCALAPPDATA%\Takedawn` (137 files) unchanged (count + newest mtime 2026-10-26) between install and removal.

## Runtime: ONE guarded launch alpha_rel2_1 (lock rel2, fresh root alpha_rel2_1, prelaunch OK, Terminal tab, postrun)
Plan written before: `testing\runtime\PLAN_alpha_rel2_1.md`. Exe `build\alpha_tester_0_1_0\burnout3_gp_p4_4.exe` (bundle host
bytes); mods = byte copies of the clean folder's `mods\demo` + `mods\generated` (`runtime_data\modsets\alpha_rel2_demo` /
`alpha_rel2_gen`, tree hashes = install.json), empty mod list / approvals, fresh profile. Evidence `testing\runtime\evidence\alpha_rel2_1`.
- FACT: `[PLATFORM] host: Burnout Mashup platform 0.1.6, build bmp-0.1.6+ab3a98869d10`, 20 services; `[ADMIT] 8 admitted, 0
  refused`; `[DEPS]` order photo -> dust -> neon -> cross -> retail-paints -> coupe series -> canyon -> loop; 3 series declared
  (Dust Runners 10, Neon 11, BM Coupes 12), 14 added cars, vehicle list 121 entries; 2 tracks added (EU_T6_V1, EU_T1_V1).
- FACT (shots 04-07): Race > Europe lists **BM Test Loop** and **BM Canyon Ring**.
- FACT (shots 11-13): NEON series with Neon Dart in default magenta; **BM COUPES** with the authored BM Coupe and its AUTHORED
  garage photo (teal); after 6 X presses crimson: model AND photo red (`[VEH] palette .../crimson (model)` + `(photo)` created).
- FACT (shots 14-16): Race Training screen (new profile), then the race on BM Test Loop with the crimson coupe, 6 cars, driven to
  107 mph along the wall (RT held 15 s).
- FATAL 0 (12 "GUEST" matches = normal thread / memory start-up lines). Operator stop (taskkill; runner reports exit 1 for it).
- Postrun: no game process; root writes 3 (marker, xbox_kernel.log, `Burnout 3 Takedown\CACHE\LocalCache08.bin`); protection
  207 / 207, **0 differences** (postrun.ps1's child PowerShell failed with 0x800705af "paging file too small" - low memory at
  that moment - so protect_snapshot.ps1 was run in-process; recorded in POSTRUN.txt). Lock released.
- NOT covered in this launch: the MODS page, Dust Runners rows, the cross-mod gold paint, Canyon Ring race, paint persistence
  across a restart, removal in game (all runtime-validated earlier on p4.3 / p4.4 research launches with the same mod bytes,
  see GP_STATUS_MATRIX_P43; not re-shown from this bundle).

## Isolation - recorded honestly
- Same machine as the developers (Windows 11 26300, RX 9070 XT). No second machine, no Windows 10, no other GPU.
- The clean folder is outside <workspace-root> with a minimal environment, but Python is the developer's install and the game
  data source was the workspace's pristine copy (read only).
- `play.cmd` was exercised only offline (`--print-env`, refusal without data); the game was started by the guarded runner (the
  only permitted way), which requires the exe under `build\`, mods under `runtime_data\modsets` and the profile / shader cache /
  saves in the run folder, and adds its own RECOMP_* diagnostics (pad, frame dumps, logs). So the launch used the bundle's exact
  bytes and play.cmd's mod folders, but not play.cmd's own paths or its environment clearing.
- `prepare.cmd data --install-from` (the host's installer) was NOT exercised (it executes the exe outside the runner).
- The profile in the guarded run held sparse `Partition*.img` (emulated Xbox HDD, ~5 GB nominal): documented in INSTALL.md.

## Bundle 0.1.1 against the SEALED kit 0.4.1 (rel2, 2026-10-27, after the seal)
- Inputs: `bundle_inputs.json` now names the sealed kit (`kit041\bmashup-modkit-0.4.1.zip` f06deede0ed6..., its sha256 is checked by
  the builder) and its tool folders: carimport 0.1.1, trackbuild 0.2.0, bmdiag 0.1.0 (30da82e1dfb1). Bundle version 0.1.1.
- **0.1.1 zip: `tester_bundle\out\bmashup-alpha-tester-0.1.1.zip` sha256 0fbaf20b79eb490ba72173de4a4e3a2d13f26bc084eed3c3ba6ba5abdc0dba9d**
  (164 members, 11,435,214 B). Deterministic: a second `--force` build gave the same hash. 0.1.0 (72988d546708...) unchanged.
- Members changed vs 0.1.0 (exactly 10, none added or removed): `BUNDLE.json`, `LOCAL_ONLY.txt`, `NOTICE.txt`, `README.txt`
  (version text 0.1.0 -> 0.1.1), `docs/FIRST_DEMO.md`, `docs/INSTALL.md`, `docs/START_HERE.md`, `docs/TEST_MATRIX.md` (bundle
  version; exact tool versions in START_HERE), `host/licenses/LICENSES_TODO.txt` (bundle name), `tools/TOOLS.json` (tool
  version / source text). **Host, SDL2, every tool file (sealed = pre-seal bytes), demo mods, scripts: byte-identical.**
- Offline clean-folder validation repeated (`testing\runs\val2\`, same method): ALL STEPS AS EXPECTED in both phases; the three
  generated demos byte-identical to the runtime-validated references and equal to val1's trees; diag export 8 members, no
  forbidden member, no user name; backup (now written beside the clean folder, outside gp\alpha), clean, folder deleted; real
  Takedawn folders unchanged.
- No new launch: host bytes (fa63df57dde6) and all mod bytes (demo + generated) are unchanged from alpha_rel2_1.
