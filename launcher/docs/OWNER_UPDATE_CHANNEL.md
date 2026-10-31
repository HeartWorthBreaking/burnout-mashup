# The update channel - for the maintainers

The launcher's updater (`docs\UPDATES.md`) uses ONLY the channel and the signing key named in `launcher\update_channel.json`. In this
release that file is empty on purpose: no channel, no key. This page says how to set one up. **Nothing here has been done yet**; it
needs the public repository and a signing key of the maintainers. The release gate of the source assembly refuses a tree whose
`update_channel.json` trusts a TEST key or names a channel other than the one the maintainers approved.

## 1. Create the signing key (once, offline)

Use OpenSSH's `ssh-keygen` (part of Windows 10 / 11: `C:\Windows\System32\OpenSSH\ssh-keygen.exe`; also on Linux / macOS). Ed25519 only.

    ssh-keygen -t ed25519 -C "Burnout Mashup release signing" -f bmashup-release-key

This writes `bmashup-release-key` (the PRIVATE key: keep it offline, backed up, with a passphrase; never commit or upload it) and
`bmashup-release-key.pub` (the public key line `ssh-ed25519 AAAA... comment`). `ssh-keygen -l -f bmashup-release-key.pub` prints its
fingerprint (`SHA256:...`), the one the launcher shows. Consider a second key kept elsewhere as a backup and list both.

## 2. Fill launcher\update_channel.json (then commit it with the release)

    {
     "format": "bm-update-channel 1",
     "channel": {"id": "burnoutmashup-stable", "github_repo": "OWNER/REPOSITORY", "url": ""},
     "trusted_keys": [{"key": "ssh-ed25519 AAAA... Burnout Mashup release signing", "label": "release key 1"}],
     "minimum": {"launcher": "1.0.0", "kit": "0.7.0", "platform": "0.1.9"},
     "namespace": "bmashup-update"
    }

- `github_repo`: the manifest is read from `https://github.com/OWNER/REPOSITORY/releases/latest/download/bmashup-release.json`
  (+ `.sig`); an older version from `.../releases/download/v<VERSION>/bmashup-release.json`. Or `url` (https://...): `<url>bmashup-release.json`,
  older ones from `<url>releases/<VERSION>/bmashup-release.json`. Give one of the two.
- The upstream Takedawn repository / owner is refused, also a repository named `takedawn`; a channel id must not contain `takedawn`.
- `minimum`: what an update must provide at least (a release with a lower launcher / kit / platform version is refused).
- Changing the key later: publish one release whose `update_channel.json` trusts the old AND the new key, signed with the old key; the
  next releases are signed with the new key.

## 3. Make a release

1. Set `launcher\VERSION.json` `release` to the new version (and `launcher` if the launcher / updater format changed); commit; tag:
   `git tag -a v0.2.0 -m "Burnout Mashup 0.2.0"`.
2. The source archive (byte-exact: the repository's `.gitattributes` keeps line ends as they are):

       git archive --format=zip --prefix=BurnoutMashup-0.2.0/ -o BurnoutMashup-0.2.0-source.zip v0.2.0

3. The manifest (offline; reads the zip; `--url` is where the zip will be published, relative to the manifest is fine for GitHub
   release assets):

       launcher\update.cmd make-manifest --zip BurnoutMashup-0.2.0-source.zip --version 0.2.0 --serial 2 --channel burnoutmashup-stable
           --tag v0.2.0 --commit <full 40-hex commit of v0.2.0> --url BurnoutMashup-0.2.0-source.zip
           --notes-url https://github.com/OWNER/REPOSITORY/releases/tag/v0.2.0 --out bmashup-release.json --sums SHA256SUMS

   `--serial` must be higher than in every manifest published before (1, 2, 3, ...). The reference build (`expected`) is taken from
   the zip's `build\EXPECTED.json` `build_release`: record it there (a verified release build) before tagging.
4. Sign it (this writes `bmashup-release.json.sig`):

       ssh-keygen -Y sign -f bmashup-release-key -n bmashup-update bmashup-release.json

5. Check before publishing (no network; uses `update_channel.json` of your checkout):

       launcher\update.cmd verify-manifest bmashup-release.json bmashup-release.json.sig
       ssh-keygen -Y check-novalidate -n bmashup-update -f bmashup-release-key.pub -s bmashup-release.json.sig < bmashup-release.json

6. Publish as assets of the GitHub release `v0.2.0`: the zip, `bmashup-release.json`, `bmashup-release.json.sig`, `SHA256SUMS`
   (the tree's file list; its sha256 is `source.tree_sha256` in the signed manifest). Mark the release "latest" only when the files are
   complete. Never re-use a serial; never re-sign an older manifest with a higher serial unless you mean to re-publish that version.

## 4. Test before the first public channel

The launcher tests use a local mock channel and TEST keys (`launcher\tests\upd_testkit.py`, marked TEST-ONLY): `test_update.py` (no
build) and `test_update_real.py` (real builds). A TEST key must never appear in a shipped `update_channel.json`.
