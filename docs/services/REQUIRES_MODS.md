# `[bmashup] requires_mods` - mod dependencies and capability requirements (platform 0.1.2+, kit 0.3.0)

Status: **RUNTIME-VALIDATED** on the deps1 slice build (deps1_1: order line, version / missing / transitive / capability
refusals, Mods page states) and on p4 (gp_p4c_1: 7 admitted / 3 refused; the capability requirement `bmashup.autopilot >= 2`
admitted on p4, which offers autopilot 2). On p4.1 OFFLINE-VALIDATED; p4.1 shortens the Mods-page detail text (`>=` shown as
`MIN`, a reason longer than 40 characters cut at its first `; ` keeping the host version), the log keeps the full text.
Not run at runtime: a cycle, switched-off / not-usable dependency texts, cross-folder order. Examples: `examples\mods\deps-base`,
`deps-addon`, `deps-newer` (bmpack specs; bmpack's test suite builds them and checks the refusal of `deps-newer`).

The text below is the deps1 slice's author page (`MOD_DEPENDENCIES.md`), unchanged except this header; where it says
"platform 0.1.2" read "platform 0.1.2 or later (p4.1: 0.1.4)".

A mod states what it needs in the `[bmashup]` table of its `mod.toml`. The host checks it when the mod list is made - before
any file, table or plugin of any mod is used - and refuses a mod whose needs are not met **alone**: the game starts without it,
the log says why, the Mods page shows the reason.

```toml
id = "example.harbour-addon"
name = "Harbour addon"
version = "1.0.0"

[bmashup]
platform = ">=0.1.2"                                          # the host's platform version
requires = ["bmashup.events >= 5", "bmashup.tracks"]          # capabilities: services / tables this host offers
requires_mods = ["heartworthbreaking.white-mountain >= 1.0.2", "example.harbour-base"]   # other mods
```

## The three keys
| Key | Since | Meaning | Unmet -> |
|---|---|---|---|
| `platform = ">=X.Y[.Z]"` | 0.1.0 | the host's platform version | refused by the platform gate (INVALID) |
| `requires = ["name", "name >= N"]` | 0.1.0 | **capability requirements**: a host service (`bmashup.autopilot`, `bmashup.events`, ...) or a table (`bmashup.tracks`) at integer version N or newer | refused by the platform gate (INVALID), e.g. `needs bmashup.autopilot >= 2; this host (platform 0.1.2) offers version 1` |
| `requires_mods = ["<mod id>", "<mod id> >= X.Y[.Z]"]` | **0.1.2** | other mods, optionally at least a version | refused by the admission (NEEDS MOD) |

`requires` names capabilities only. A mod id there is refused with a hint to use `requires_mods` (the two lists use different
version forms on purpose: services have whole-number versions, mods have dotted versions).

## requires_mods rules
- An entry is `"<mod id>"` (any version) or `"<mod id> >= X.Y[.Z]"`; at most 16 entries; no id twice; never the mod's own id. There
  are no upper bounds, ranges or optional dependencies (an entry with another operator is refused, never misread).
- Versions compare by their numbers (`1.0.10` is newer than `1.0.2`); `+build` is ignored; a prerelease (`1.0.2-rc1`) is older
  than `1.0.2`; a version that does not start with a number cannot be compared (it meets only an entry without a version).
- A mod is refused when a required mod is: not installed, switched off (Mods page or mod list), not usable (its own manifest /
  platform problem, a shared id), older than required, refused itself (a clash with an earlier mod, or its own unmet
  dependency - this follows chains), or when requirements form a cycle (every mod of the cycle and their dependants).
- **Order:** the host lists every mod after the mods it requires; otherwise the order is unchanged (BMASHUP_MODS folders, then
  usable mods by id, then the unusable ones). The admission, the services, the plugins and the Mods page follow this order, so
  when a dependant clashes with its dependency (same track id, same tuning value, ...) the **dependant** is refused, never the
  base. With no `requires_mods` anywhere the order is exactly the old one.
- **Files** keep their rule: in one mods folder, the file of the mod EARLIER in the list is used; across folders, the first folder
  wins. A dependant therefore cannot replace its dependency's files (no "patch mod" overrides); a file both supply is logged as
  `[MOD] conflict: <file>: mod <base> over mod <addon>`.
- `requires_mods` checks that the other mod is admitted, not that its native plugin was approved or loaded.

## What you see
Log (examples from the fixture set `gp_deps1_set`):
```
[DEPS] the mod list in dependency order (4 mods placed after the mods they require): gp.deps-base, gp.deps-addon, ...
[ADMIT] mod gp.deps-newer 1.0.0 (...\deps-newer) refused, the game starts without it: needs a mod gp.deps-base:
        requires_mods "gp.deps-base >= 1.1": the installed version 1.0.2 is older: mod gp.deps-base 1.0.2 (...\deps-base)
[MOD] mod ignored (needs gp.deps-base >= 1.1: has 1.0.2): ...\deps-newer
```
Mods page: the mod's state reads `NEEDS MOD`; the detail line under the cursor gives the short reason (`needs <id> >= <v>: not
installed / switched off / not usable / has <version> / refused`, or `dependency cycle: a -> b -> a`).

## Validate before you ship
`py -3 -B bmpack.py validate <your mods folder> [<other folders> ...]` (bmpack 1.3) runs the host's own order and rules and prints
the same decision (exit 1 with the refusals). Spec keys: `[mod] platform / requires / requires_mods`.

## Hosts that do not check
- Platform hosts before 0.1.2 refuse a mod with `requires_mods` as "needs a newer platform" (they do not read the key).
- Retail Takedawn ignores every `[bmashup]` key: there, a mod loads without its dependencies and nothing is reported.

## Evidence update (kit 0.3.1)
p4.2 (gp_p42_5): the Mods page showed the three refused fixtures as NEEDS MOD with the p4.1 texts "NEEDS GP.DEPS-BASE MIN 1.1: HAS 1.0.2", "NEEDS GP.DEPS-NEWER: REFUSED", "NEEDS GP.DEPS-ABSENT: NOT INSTALLED"; the admitted fixtures ON.
