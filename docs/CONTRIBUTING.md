# Reporting bugs and contributing (experimental alpha; see also the root CONTRIBUTING.md)

## A bug report
1. What you did (steps, which mods, which car / track / event), what you expected, what happened.
2. Versions: host build identity from the log's `[PLATFORM]` line, kit / bundle version, tool versions (`--help` / README).
3. A diagnostic export (`tools\bmdiag`, `DEBUGGING.md`) - check its files first. Never attach saves, game files, extracted
   assets, or mods built from donor parts.
4. Use the repository's issue templates once the project has opened them (bug, install / GPU, mod / tool problem).

## A contribution (code, docs, AUTHORED examples)
- Only your own work or work under a compatible licence; say where every non-text file comes from (AUTHORED with provenance,
  listed in `examples\authored\AUTHORED_FILES.json` with its sha256).
- Never commit: game data or anything derived from it (donor parts, converted tracks, textures taken from the game), generated
  game code, saves, executables / DLLs / `.asi`, credentials, personal paths or e-mail addresses.
- Tools: keep them portable (`tools\_lib\bmkit_env.py` for every path and prerequisite; no fixed or developer paths; exit 3 with
  the fix for a missing prerequisite) and add tests, including the error paths. `tools\kit_selftest.py` must pass.
- Plugins: build clean with `-Wall -Wextra -Werror`, deterministic (`-Wl,--no-insert-timestamp`), use only the SDK headers
  (`sdk\include`); raw guest memory is not a public API.
- Mods: declare `platform = ">=0.1.6"` (or the tables you need in `requires`) and validate with bmpack before sharing.
- Everything is reviewed before it is merged; contributions follow the root `CONTRIBUTING.md` (licences, DCO sign-off).
