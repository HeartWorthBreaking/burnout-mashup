# Burnout Mashup

**A modding platform for Burnout 3: Takedown on PC, built on the Takedawn native port. Experimental alpha, source code only.**

> **Unofficial.** Burnout Mashup is an unofficial fan project. It is not affiliated with, authorised by or endorsed by Electronic Arts, Criterion Games, Microsoft or the Takedawn project. "Burnout" is a trademark of its owner. Whether the working name "Burnout Mashup" may be used has NOT been cleared (a disclaimer is not a permission); the name may change.
>
> Burnout Mashup is an independently maintained fork of [Takedawn](https://github.com/xenophobentx/takedawn). It is not an official Takedawn release, so please
> don't report Burnout Mashup problems to the Takedawn project.

## What it does
Takedawn runs Burnout 3: Takedown natively on Windows. Burnout Mashup adds a layer on top for mods:

- **Data mods**: new car series and paints, garage photos, your own cars and tracks, World Tour events, and tuning for AI,
  traffic and physics. They are plain folders with a `mod.toml`.
- **Native plugins** written in C against a versioned SDK. Each plugin runs only after you approve it in the game.
- **Tools** to build and check content: trackbuild, carimport, bmpack, fetex, vehtool and more.
- **A launcher** that walks you through setup, builds the game on your PC ("Build Mashup"), manages your mods and starts the game.
- **A Workbench** for mod authors: create a project from a template, tune values, then build, validate and stage it.

## What you need
- Windows 10 or 11 (64-bit), a graphics driver with Vulkan 1.3, and Python 3.11 or newer.
- **Your own copy of Burnout 3: Takedown** for the original Xbox, North American (NTSC-U) version.

There is no game in this repository: no game data, no game files, no executable and no prebuilt package. The launcher builds
the game on your PC from your own copy, using the upstream recompiler. Everything that build produces, and everything the
tools make from your game data, stays on your PC (`docs/LOCAL_OUTPUTS.md`). Please never share it.

## Getting started
1. Get this source: clone the repository (keep line endings unchanged, see `.gitattributes`) or download the source zip of a
   release, into a new folder.
2. Start `launcher\Burnout Mashup.cmd`.
3. On the Setup tab: drop your game folder on the window, press **Build Mashup...** and follow it. The launcher checks your
   copy, offers the build tools it needs (each download is pinned to an exact version and checked), builds, verifies the result
   against the reference build and installs it. Then **Check this PC**, and Play.

The full walk-through is `launcher/docs/QUICKSTART.md`. Developers can use the command-line build described in `docs/BUILDING.md`.

## Status
This is an **experimental alpha**. It has been tested by its authors on one Windows 11 PC: automated test suites, rebuilds
from a clean source download that reproduce the reference executables, and automated runs of the launcher, the Workbench and
the game. It has not been tested by other people or on other machines yet, so expect rough edges and please report them.

Some questions are still open and are not answered by anything in this repository: the use of the "Burnout" name, the legal
status of building the game from your own copy, the licensing of translated game code, and how reverse-engineering notes and
the small byte checks the host uses to find its hook sites should be treated. They are listed in `docs/PUBLIC_STATUS.md`.
Nothing here is legal advice, and nothing here claims legal clearance.

## How the source is organised
| folder | what is inside |
|---|---|
| `host/` | the Mashup host, stored as changes on top of pinned upstream commits (Takedawn `4f074e211822`, xboxrecomp `e3756d1b2fef`) |
| `sdk/` | the plugin SDK: headers, examples and CMake helpers |
| `launcher/` | the launcher, including Build Mashup and an updater (no update channel is set up yet, so it never checks anything) |
| `workbench/` | the Workbench |
| `tools/` | content tools: bmpack, trackbuild, carimport, fetex, vehtool, bmdiag, ps2look, migrate |
| `examples/` | original example mods and small original assets |
| `build/` | the build scripts Build Mashup runs, and the reference hashes it checks against |
| `docs/` | documentation; `docs/upstream/` holds the upstream README, credited |

## Licences
Our own code, SDK and tools are MIT; our documentation is CC-BY-4.0; our original example assets are CC0-1.0. Upstream and
third-party material keeps its own licence. One upstream file, the audio code `src/apu/apu_core.c` from xemu, is under the
GNU Lesser General Public License; our changes to it are offered under the same terms (LGPL-2.1-or-later, as xboxrecomp
distributes it; details in `host/toolkit/lgpl/NOTICE`). See `LICENSE`, `LICENSES/`, `REUSE.toml` and `NOTICE.md`.

## Credits
Takedawn and xboxrecomp are by sp00nz, xenophobentx and their contributors; the xemu audio code is by espes, Jannik Vogel and
Matt Borgerson; ADPCM-XQ is by David Bryant. Thank you. Full credits: `CREDITS.md`, `NOTICE.md` and `docs/upstream/`.
Burnout Mashup was developed with the help of Claude (Anthropic); see `AUTHORS` and `PROVENANCE.md`.

## Contributing
Bug reports and contributions are welcome. See `CONTRIBUTING.md` (contributions are signed off under the DCO) and `SECURITY.md`.
Native plugins run with your permissions, so only approve plugins you trust.
