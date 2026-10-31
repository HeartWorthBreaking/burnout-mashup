# PORT_NOTES - trackbuild 0.1.6 -> 0.2.0 (rel1a, 2026-10-27)

- Version: `trackbuild.VERSION = "0.2.0"` (succeeds 0.1.6; the 0.1.6 folder in the gp tools is unchanged, kit 0.4.0 unchanged).
- Folder = exactly what goes to `<kit>\tools\trackbuild\`: `tb.py`, `tb.cmd`, `trackbuild\` (incl. `_vendor\`), `examples\`,
  `tests\`, `docs\`, `README.md`, `CHANGELOG.md`, `VENDOR.md`, `AUTHORED_FILES.json`, this file, `CHECKPOINT.md`, `SHA256SUMS.txt`.
- Self-contained: imports only the standard library and its own `trackbuild` package (vendored readers in `trackbuild\_vendor`,
  incl. the trackconv subset and a pure-Python bmpack subset). It does NOT need the kit's `_lib` / `_vendor` / bmpack and needs
  NO C compiler; it also runs outside a kit. It accepts the kit's `BMKIT_GAME_DATA`.
- CLI (unchanged positional form of 0.1.6, plus options):
  `gen-testloop SRC [--variant canyon|...]`, `build SRC DESC OUT --game-data DIR [--host RR/NN_VN] [--unpinned-donor]`,
  `validate OUT [DESC]`, `inspect OUT`, `package OUT TOML SET [--bmpack FILE]`, `check-game-data`, `selfcheck`, `version`.
- Game-data need list (read only): `Tracks\EU\M1_V1\{Gamedata.bgd, enviro.dat, SOUND.AWD, CRASH1.RWS, CRASH2.RWS, CRASH3.RWS,
  E_DJRACE.xwb, MUSIC.RWS}` (pinned sha256), `default.xbe` (checked when present); tests also `Tracks\EU\M1_V1\{static,streamed}.dat`
  and `Tracks\US\C3_V1\{static,streamed}.dat`.
- Changed vs 0.1.6: `tb.py` (rewritten CLI, errors, exit codes), `trackbuild\build.py` (vendored imports, donor from game data,
  clearer message), `validate.py` (vendored imports only), `pack.py` (vendored trackconv, optional --bmpack host check),
  `io.py` (read_png_alpha, read_desc errors), `__init__.py` (version); new `donor.py`, `preflight.py`, `accessguard.py`,
  `_vendor\`. Unchanged bytes: `blocks.py`, `dxt.py`, `lod.py`, `testloop.py`, `traffic.py`, `units.py`, `visibility.py`.
- Tests and results: see CHECKPOINT.md.
