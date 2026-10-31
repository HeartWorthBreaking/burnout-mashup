# Bugs and contributing

## 1. Make a diagnostic export
```
diag.cmd --bundle . --out diag\bugreport.zip
```
(`diag.cmd` = `tools\bmdiag.py`, Python 3.8+; `py -3 -B tools\bmdiag.py --help` lists the options.) It collects: bundle /
host / tool versions and hashes, Windows build, GPU + Vulkan summary, the mod list (ids, versions, labels, folder hashes),
the end of `run.log` and its `[PLATFORM]` / `[ADMIT]` / `[DEPS]` / `[MOD]` / `FATAL` lines, the preflight result.
It **excludes by default**: saves (`UDATA` / `TDATA`), mod progress (`.bmprog`), game data and any game file, the files of
generated mods (names + hashes only), your user name in paths (replaced by `<user>`), environment variables outside a short
allowlist. It prints every file it put in the export: read the list before you send it.

Never attach the host exe (prebuilt or your build), game files, generated mods or saves.

## 2. Where to send it
Use the issue tracker of the repository this source comes from, once the project has opened one (issue templates: bug, install
problem, mod / plugin problem, feature request); until then, the contact the project owner names. Do not report to the Takedawn project. One problem per issue; say what you expected, what
happened, and the exact steps (menu path, track, car, mods on).

## 3. Contributing
- Data mods and plugins: follow the service contracts in the kit's `docs\services\`; validate with bmpack / vehtool
  ([PACKAGE_AND_VALIDATE.md](PACKAGE_AND_VALIDATE.md)); label every file AUTHORED / DERIVED / CONTROL.
- Never contribute game data, extracted assets, generated (recompiled) game code, saves, or files derived from them; only
  original work. Contributions are accepted under the licences and the DCO sign-off described in the root `CONTRIBUTING.md`.
- Tools / SDK changes: keep the kit's tests passing (`py -3 -B <kit>\tools\kit_selftest.py`), no machine-specific paths,
  Python standard library only, actionable error messages.
- Testers: [TEST_CHECKLIST.md](TEST_CHECKLIST.md) says what is most useful to try first.
