# Updates - "Check for updates" in the launcher

The launcher can update Burnout Mashup to a newer **published release** of its own update channel: it downloads the new **source**,
verifies it, builds it on your PC with BUILD MASHUP (`docs\BUILD_MASHUP.md`, the same build as always, with your own game) and
installs the result, keeping the version you used before. Help tab -> **Check for updates...** opens the Updates window; the same
steps run from the command line as `launcher\update.cmd` (`update.cmd help`).

## What it does - and never does

| it does (only when you press the button / give the command) | it never does |
|---|---|
| fetch the channel's signed release manifest (`check`) | check by itself: no check at start, in the background, on a schedule, or from the game (the host's own update row stays off) |
| show what is new, the download size and every step that will follow | download, build or install anything silently |
| download the source archive into `%LOCALAPPDATA%\BurnoutMashup\updates` (sha256 + size from the signed manifest; an interrupted download continues) | use any channel other than the one in `launcher\update_channel.json`; use an upstream Takedawn repository or release |
| unpack it into a **new** folder beside your current source (`BurnoutMashup-<version>`), verify every file | unpack over your current source, or change it |
| build it with BUILD MASHUP (its build folder, cache and pinned tools); the exe must be identical to the release's reference build | install a build that is not identical, or replace Mashup with another host |
| install it into `launcher\host-local`; the build in use becomes `host-local.prev`; **Switch back to previous version** restores the previous build **and** source | touch your profile, saves, settings, mods, plugin approvals or game data (new plugin bytes still need your approval in the game) |

## No channel configured (this release)

`launcher\update_channel.json` ships **empty**: no channel and no trusted signing key. The Updates window then says **"No update channel
configured"**, every step is disabled and nothing is contacted. The maintainers fill the file for published releases
(`docs\OWNER_UPDATE_CHANNEL.md`). Until then, get new versions by hand and use **Bring my data from an older Burnout Mashup folder**.

## The steps

| button / command | what happens | if it fails |
|---|---|---|
| Check for updates / `update.cmd check` | downloads `bmashup-release.json` + `.sig` from the channel; the signature is verified **before any field is read**; then the rules below | nothing changed; the reason and what to do are shown |
| Download / `download` | the archive -> `updates\downloads\<sha>-<name>.part`, then sha256 + size; a wrong file is deleted | run Download again: a kept part continues (HTTP Range) or starts again |
| Prepare / `prepare` | checks the archive's paths (no `..`, drives, links, device names; one top folder), unpacks into `BurnoutMashup-<version>.partial`, compares the tree with the signed SHA256SUMS digest, checks that it is a Burnout Mashup source (`host\PINS.json`) whose `build\EXPECTED.json` is the manifest's, renames to `BurnoutMashup-<version>` | the partial folder is removed; your source is untouched |
| Build and install / `build [BUILD OPTIONS]` | re-verifies the unpacked tree, runs `bmbuild.py build --repo <new source> --launcher <this launcher>` (release profile; your game and the upstream source as in the last build unless given), whose verify step compares the exe with the new source's `EXPECTED.json` (= the manifest's reference), installs atomically; the updater checks the installed exe against the manifest once more | the version in use is unchanged (BUILD MASHUP keeps the previous build); fix the shown reason and press Build again (completed steps are reused) |
| Switch back to previous version / `switch-back` | the previous build and the previous source become the ones in use; pressed again = forward | refused when the builds in `host-local` / `host-local.prev` are not the recorded ones; then use **Previous build** in the Setup tab |
| Install an older version... / `install-older VERSION --yes` | the same steps for an older signed release of the channel (`releases/<VERSION>/` or the GitHub release `v<VERSION>`), only on your explicit choice | as above |
| Discard pending update / `discard --yes` | forgets the pending update, deletes its download and its unpacked folder (never the version in use or the previous one) | - |
| Cancel / `cancel` | stops a download (the part is kept) or a build (BUILD MASHUP keeps the completed steps) | - |

After an update, **Build Mashup** (Setup tab) builds the source in use (`update-state\STATE.json` in the launcher folder records it);
**Previous build** keeps build and source together. The launcher program you started stays the one in this folder: the update replaces the
host program it starts. A newer launcher program arrives with a fresh folder of the new release (move your data with **Bring my data from
an older Burnout Mashup folder**).

## Refused, with nothing changed

- a manifest signed by a key that is not in `update_channel.json`, a bad or missing signature, another namespace (`bmashup-update`)
- another product or channel name, an upstream Takedawn repository / owner / URL in the channel or the manifest, a source that is not a
  Burnout Mashup source
- a version **older** than the one in use (unless you chose **Install an older version**); the same version = "up to date"
- a manifest with a **lower serial** than one already seen here, or the same serial with other bytes (a replayed or stale file)
- a release that needs a newer launcher (`requires.launcher`) or provides a lower launcher / kit / platform than `update_channel.json`'s
  `minimum`
- plain `http://` (only `https://`; `http://127.0.0.1` for tests), a channel without a trusted key

Exit codes of `update.cmd`: 0 done (also "up to date"), 1 usage, 2 refused, 3 failed (the version in use unchanged), 5 cancelled, 6 no
update channel configured, 7 the channel cannot be reached (offline).

## The release manifest (bm-release-manifest 1, MIT)

`bmashup-release.json` (UTF-8 JSON) and `bmashup-release.json.sig` (an OpenSSH signature: `ssh-keygen -Y sign -n bmashup-update`, Ed25519,
verified by `tools\launcher\bmed25519.py`, standard library only). Fields (all required unless noted):

| field | meaning |
|---|---|
| `format` | `bm-release-manifest 1` |
| `product`, `channel` | `BurnoutMashup`; the channel id of `update_channel.json` |
| `version`, `serial`, `created` | the release version (= `launcher\VERSION.json` `release` of its source); a whole number that grows with every manifest the channel publishes (replay protection); UTC time `2026-11-01T12:00:00Z` |
| `source.tag`, `source.commit` | the git tag and the 40-hex commit the archive was made from |
| `source.archive` | `name` (.zip), `urls` (one or more; relative to the manifest allowed), `sha256`, `size` |
| `source.top_folder`, `source.files`, `source.tree_sha256` | the archive's single top folder, its file count, and sha256 of its SHA256SUMS text (`<sha256>  <path>` lines sorted by path) |
| `expected` | `expected_json_sha256` (sha256 of the source's `build/EXPECTED.json`), `exe` (`BurnoutMashup.exe`), `exe_sha256`, `identity` (`bmp-...`), `profile` (`release`): the reference build the rebuilt exe must equal |
| `provides` | `release`, `launcher`, `kit`, `platform` versions of this release |
| `requires` | `launcher`: the oldest launcher that may install it |
| `notes_url`, `notes` | (optional) the release notes |

Versions compare by up to four numbers; `-pre` ranks below the same numbers; `+build` is ignored.

## Where things are

| | |
|---|---|
| `launcher\update_channel.json` | the channel (`id` + `github_repo` OWNER/NAME **or** `url` https://...), `trusted_keys` (`ssh-ed25519 AAAA...` lines), `minimum`, `namespace` |
| `launcher\VERSION.json` | this source's release version and the launcher version |
| `launcher\update-state\STATE.json` | the source in use and the previous one, the pending update, the newest serial seen (local, not shared) |
| `%LOCALAPPDATA%\BurnoutMashup\updates` | checked manifests and downloads (`--updates DIR` chooses another folder) |
| `..\BurnoutMashup-<version>` | the unpacked new source (`--sources-dir DIR` chooses another parent folder) |
