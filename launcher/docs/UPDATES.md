# Updates - "Check for updates" in the launcher

The launcher updates Burnout Mashup to a newer **published release** of its update channel: the signed releases of the project's
GitHub repository (`launcher\update_channel.json`). Help tab -> **Check for updates...** opens the Updates window; the same steps run
from the command line as `app\launcher\update.cmd` (`update.cmd help`).

## What it does - and never does

| it does (only when you press the button / give the command) | it never does |
|---|---|
| fetch the channel's signed release manifest (`check`) | check by itself: no check at start, in the background, on a schedule, or from the game |
| show what is new, the download size and every step that will follow | download or install anything silently |
| download the release's Windows package into `%LOCALAPPDATA%\BurnoutMashup\updates` (sha256 + size from the signed manifest; an interrupted download continues) | use any channel or key other than the ones in `update_channel.json`; use an upstream Takedawn repository or release |
| unpack it into `app\.update\stage\<version>` and verify every file, both exes and the program folder | unpack over the version in use |
| **Install**: replace `app\` and the two exes in ONE step that is undone on any error, carry your data over, keep the version you had, restart the launcher | delete your game copy, mods, saves, settings, plugin approvals or builds (new plugin bytes still need your approval in the game) |
| Build Mashup afterwards only when the new release has another reference host than your build | install a host build that is not identical to the release's reference build |

## The install folder (the Windows package, 0.2.0 and later)

    Burnout Mashup.exe, Burnout Mashup Workbench.exe     the starters (replaced by an update)
    gamedata\                                            your game copy + mods\user (yours) + mods\generated (demos from your game): never touched by an update
    app\                                                 the program (replaced by an update), with YOUR data inside it:
      launcher\profile\                                  saves, settings, mod list, plugin approvals, progress
      launcher\host-local\, host-local.prev\             your Build Mashup builds
      HOST_INFO.json, workbench\workbench.json, ...      written by Build Mashup / the Workbench
      .update\                                           the updater's work folder: stage, kept versions, journal, logs

**What counts as your data:** every file or folder in `app\` that the version in use did not ship (its `app\SHIPPED_FILES.sha256`)
moves to the same place in the new version - also anything you added. Shipped files you changed are not carried over (the new
version brings its own); they stay with the kept version and the install result names them.

## Update now

Help tab -> **Update now** (also the first button of the Updates window) runs every step below on one click: check, download, prepare,
install, the launcher starting again, and Build Mashup when the new release needs one. Close the game and the Workbench first.
If you are up to date it says so and stops. No question on the way: the click is your go; **Cancel** stops it and **Switch back to
previous version** undoes it. It stops at the first step that fails and says why; pressing it again goes on from there (a finished
download is not fetched again). It runs only when you press it. When a build is needed and the launcher does not know your game
yet, it asks for it in the Updates window.

## The steps

| button / command | what happens | if it fails |
|---|---|---|
| Check for updates / `update.cmd check` | downloads `bmashup-release.json` + `.sig` from the channel; the signature is verified **before any field is read**; then the rules below | nothing changed; the reason and what to do are shown |
| Download / `download` | the package -> `updates\downloads\<sha>-<name>.part`, then sha256 + size; a wrong file is deleted | run Download again: a kept part continues (HTTP Range) or starts again |
| Prepare / `prepare` | checks every path in the package (only the two exes and `app\...`; no `..`, drives, links, device names), unpacks into `app\.update\stage\<version>.partial`, compares it with the signed digest, both exes with their signed sha256, `app\` with the signed source tree (a Burnout Mashup source whose `build\EXPECTED.json` is the manifest's), renames to `stage\<version>` | the partial folder is removed; nothing in use is touched |
| **Install (restarts)** / `install` | close the game and the Workbench first. Plans every step, writes it to `app\.update\JOURNAL.json`, then only RENAMES: your data into the new program folder, the old program into `app\.update\versions\<old version>-<time>`, the new one into `app\`, the exes likewise; then the launcher starts again | any error: every step done so far is undone in reverse order - the version in use is exactly as before (a file in use: close the program holding it and press Install again). A crash or power loss: the next start of either exe finishes or undoes the change from the journal |
| Build and install / `build [BUILD OPTIONS]` | only when the new release has another reference host: BUILD MASHUP from the program in use, compared with the manifest's reference, installed (your previous build is kept as `host-local.prev`) | your build in use is unchanged; fix the reason shown and press Build again |
| Switch back to previous version / `switch-back` | the kept version becomes the one in use (the same undoable step); pressed again = forward | as Install |
| Install an older version... / `install-older VERSION --yes` | the same steps for an older signed release of the channel (`releases/download/v<VERSION>/`), only on your explicit choice | as above |
| Discard pending update / `discard --yes` | forgets the pending update, deletes its download and its stage folder (never the version in use or a kept one) | - |
| Cancel / `cancel` | stops a download (the part is kept) or a build | - |

One kept version: an update removes the version kept before it (after the new one is in place); Switch back always has the
version you came from.

## Coming from 0.1.0-alpha.1

0.1.0-alpha.1 was a source tree with everything under `launcher\` and no update channel, so it cannot update itself. Two ways:

- **In place (recommended):** unpack the newest `BurnoutMashup-0.2.0-alpha.N-windows.zip` (alpha.1 or later) INTO your 0.1.0-alpha.1 folder (all its names are
  new: nothing is overwritten) and start `Burnout Mashup.exe`. It finds the old version around `app\` and moves it into the new
  layout by itself, in one transaction like Install: `launcher\gamedata` -> `gamedata\`; `launcher\mods\user` and `mods\generated`
  -> `gamedata\mods\...`; `launcher\profile`, `host-local`, `host-local.prev`, `update-state`, `build`, `work`, `diag`, `HOST_INFO.json`,
  the Workbench's settings and data and anything else 0.1.0 did not ship -> the same place in `app\`; the 999 files 0.1.0 shipped
  (and the ones you changed) -> `app\.update\versions\0.1.0-alpha.1-<time>\tree` with `MIGRATION_REPORT.json`. Paths to the old
  folder in `workbench\workbench.json` are moved along; old source-folder entries in `update-state\STATE.json` are dropped. Your host
  build stays valid (0.2.0 has the same reference host). A file in use (the old launcher, the game): everything is undone; close it
  and start again.
- **Fresh folder:** unpack the new zip into a new folder, start it, Help -> **Bring my data from an older Burnout Mashup folder**
  and choose the old folder (or `remove.cmd upgrade --from <old folder>`): the same map, but COPIED (each file compared by sha256) -
  the old folder is only read. Refused when the new folder already has a profile.

A git clone or an unpacked source zip (no `Burnout Mashup.exe` beside it) keeps the 0.1.0 behaviour: everything under `launcher\`,
and the source update (a new source folder beside it, built with Build Mashup).

## Refused, with nothing changed

- a manifest signed by a key that is not in `update_channel.json`, a bad or missing signature, another namespace (`bmashup-update`)
- another product or channel name, an upstream Takedawn repository / owner / URL in the channel or the manifest, a source that is not a
  Burnout Mashup source, a package with other entries than the two exes and `app\...`
- a version **older** than the one in use (unless you chose **Install an older version**); the same version = "up to date"
- a manifest with a **lower serial** than one already seen here, or the same serial with other bytes (a replayed or stale file)
- a release that needs a newer launcher (`requires.launcher`) or provides a lower launcher / kit / platform than `update_channel.json`'s
  `minimum`
- plain `http://` (only `https://`; `http://127.0.0.1` for tests)

Exit codes of `update.cmd`: 0 done (also "up to date"), 1 usage, 2 refused, 3 failed (the version in use unchanged), 5 cancelled,
6 no update channel configured, 7 the channel cannot be reached (offline).

## The release manifest (bm-release-manifest 1, MIT)

`bmashup-release.json` (UTF-8 JSON) and `bmashup-release.json.sig` (an OpenSSH signature: `ssh-keygen -Y sign -n bmashup-update`, Ed25519,
verified by `tools\launcher\bmed25519.py`, standard library only). Fields (all required unless noted):

| field | meaning |
|---|---|
| `format` | `bm-release-manifest 1` |
| `product`, `channel` | `BurnoutMashup`; the channel id of `update_channel.json` (`burnoutmashup-stable`) |
| `version`, `serial`, `created` | the release version (= `launcher\VERSION.json` `release`); a whole number that grows with every manifest the channel publishes (replay protection); UTC time `2026-11-01T12:00:00Z` |
| `source.tag`, `source.commit` | the git tag and the 40-hex commit the release was made from |
| `source.archive` | the source zip: `name`, `urls` (relative to the manifest allowed), `sha256`, `size` |
| `source.top_folder`, `source.files`, `source.tree_sha256` | the source zip's single top folder, its file count, and sha256 of its SHA256SUMS text (`<sha256>  <path>` lines sorted by path) |
| `package` (launcher 1.1.0) | the Windows package: `layout` `bm-layout 2`, `app_folder` `app`, `name`, `urls`, `sha256`, `size`, `files`, `tree_sha256` (over every file of the zip, the same text form), `exes` {`Burnout Mashup.exe`, `Burnout Mashup Workbench.exe`: sha256}; its `app/` is the source tree byte for byte |
| `expected` | `expected_json_sha256` (sha256 of the source's `build/EXPECTED.json`), `exe` (`BurnoutMashup.exe`), `exe_sha256`, `identity` (`bmp-...`), `profile` (`release`): the reference host build |
| `provides` | `release`, `launcher`, `kit`, `platform` versions of this release |
| `requires` | `launcher`: the oldest launcher that may install it (`1.1.0` for a release with a package) |
| `notes_url`, `notes` | (optional) the release notes |

Versions compare by up to four numbers; `-pre` ranks below the same numbers; `+build` is ignored.

## Where things are

| | |
|---|---|
| `app\launcher\update_channel.json` | the channel (`id` + `github_repo` OWNER/NAME **or** `url` https://...), `trusted_keys` (`ssh-ed25519 AAAA...` lines), `minimum`, `namespace` |
| `app\launcher\VERSION.json` | this release's version and the launcher version |
| `app\launcher\update-state\STATE.json` | the pending update, the newest serial seen, the package installed (local, not shared; carried over) |
| `app\.update\` | `stage\` (a prepared update), `versions\` (the kept version; the 0.1.0 files after a migration), `PREVIOUS.json`, `JOURNAL.json` (only while a change runs), `logs\` (each finished change), `bmapply.py` (the recovery helper the exes run) |
| `%LOCALAPPDATA%\BurnoutMashup\updates` | checked manifests and downloads (`--updates DIR` chooses another folder) |
