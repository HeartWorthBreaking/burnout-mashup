# The update channel - for the maintainers

The launcher's updater (`docs\UPDATES.md`) uses ONLY the channel and the signing key named in `launcher\update_channel.json`. Since
0.2.0-alpha.1 that is the project's GitHub repository with the release key below. The release gate of the source assembly refuses a
tree whose `update_channel.json` trusts a TEST key or names a channel or key the maintainers have not approved.

| | |
|---|---|
| channel id | `burnoutmashup-stable` |
| github_repo | `HeartWorthBreaking/burnout-mashup` (manifest: `https://github.com/HeartWorthBreaking/burnout-mashup/releases/latest/download/bmashup-release.json` + `.sig`) |
| trusted key | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINJLFbt4Kt843QDZPk0/nnpjoMLuGng0lcL/5VqciIpk Burnout Mashup release signing` |
| fingerprint | `SHA256:tQRHolv3k/JYwlk5b3rS8fkZ3LbHWdOfyl+5eXUHnGg` |
| namespace | `bmashup-update` |

## 1. The signing key
OpenSSH `ssh-keygen` (Windows: `C:\Windows\System32\OpenSSH\ssh-keygen.exe`), Ed25519 only. The PRIVATE key stays with the maintainer
(offline, backed up, with a passphrase: `ssh-keygen -p -f <key>`); it is never committed, uploaded or given to a tool.
`ssh-keygen -l -f <key>.pub` prints the fingerprint above.
- Changing the key: publish one release whose `update_channel.json` trusts the old AND the new key, signed with the old key; the
  next releases are signed with the new key.
- The upstream Takedawn repository / owner is refused as a channel, also a repository named `takedawn`.

## 2. Make a release (offline until step 6)
1. Set `launcher\VERSION.json` `release` (and `launcher` when the updater / layout format changed); record a verified release build
   in `build\EXPECTED.json` `build_release`; regenerate `SHIPPED_FILES.sha256` (the assembler does); commit; tag
   `git tag -a v0.2.0-alpha.1 -m "Burnout Mashup 0.2.0-alpha.1"`.
2. The source zip: one top folder `BurnoutMashup-<version>/` holding the tree byte for byte (`git archive --format=zip
   --prefix=BurnoutMashup-<version>/ v<version>`, or the assembler's packer: same files).
3. The starters: `py -3 -B launcher\tools\launcher\exe\build_exe.py "Burnout Mashup.exe" --cc <llvm-mingw clang>` and
   `py -3 -B workbench\exe\build_wbexe.py "Burnout Mashup Workbench.exe" --cc ...` (deterministic: two builds are identical).
4. The Windows package `BurnoutMashup-<version>-windows.zip`: the two exes, the empty folders `gamedata/` and `gamedata/mods/`,
   and `app/` = the tree byte for byte. Nothing else (no host exe, no SDL2.dll, no game file).
5. The manifest (reads both zips):

       launcher\update.cmd make-manifest --zip burnout-mashup-source-<version>.zip --package BurnoutMashup-<version>-windows.zip
           --version <version> --serial <N> --channel burnoutmashup-stable --tag v<version> --commit <40-hex commit of the tag>
           --url burnout-mashup-source-<version>.zip --package-url BurnoutMashup-<version>-windows.zip
           --notes-url https://github.com/HeartWorthBreaking/burnout-mashup/releases/tag/v<version> --out bmashup-release.json

   `--serial` must be higher than in every manifest published before (0.2.0-alpha.1, the first one = 1). `--package` checks that the package's
   `app/` is the source tree and sets `requires.launcher` 1.1.0.
6. Sign (writes `bmashup-release.json.sig`) and check:

       ssh-keygen -Y sign -f <private key> -n bmashup-update bmashup-release.json
       launcher\update.cmd verify-manifest bmashup-release.json bmashup-release.json.sig
       ssh-keygen -Y check-novalidate -n bmashup-update -f <key>.pub -s bmashup-release.json.sig < bmashup-release.json

7. Publish as assets of the GitHub release `v<version>`: the package zip, the source zip, `bmashup-release.json`, `.sig`, the
   tree's `SHA256SUMS` and a `SHA256SUMS.txt` of the assets. Mark it "latest" only when every file is up (the launcher reads
   `releases/latest/download/`). Never re-use a serial; never re-sign an older manifest with a higher serial unless you mean to
   re-publish that version.

## 3. Tests before publishing
The launcher tests use a local mock channel and ephemeral TEST keys (`launcher\tests\upd_testkit.py`, marked TEST-ONLY):
`test_update.py` (no build), `test_update_real.py` (real builds); the release-candidate suite of the maintainers also installs a
package over an install, undoes injected failures and crashes at every step and migrates a 0.1.0-alpha.1 folder. A TEST key must
never appear in a shipped `update_channel.json`.
