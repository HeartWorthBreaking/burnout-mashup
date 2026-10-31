# PROVENANCE - how this tree was made

- **Fresh history.** This repository starts as a new history from an assembled tree. The material was developed in a private
  workspace and a private repository (2026-10-26 .. 2026-10-31; git author HeartWorthBreaking; AI-assisted: every commit carried
  a `Co-Authored-By: Claude` trailer). The private history stays private (it holds early workspace paths); nothing is hidden
  about its existence. `AUTHORS` records the facts.
- **Assembled deterministically** by a script from pinned inputs (`PUBLIC_MANIFEST.json` lists every file with its sha256,
  size, origin, licence and provenance row; running the assembler twice gives the identical manifest).
- **Upstream pins.** The host is stored against Takedawn `4f074e211822` and xboxrecomp `e3756d1b2fef` (`host/PINS.json`); upstream files
  keep their MIT licence and headers; the LGPL-2.1-or-later hunks are kept apart (`host/toolkit/lgpl/`).
- **Provenance inventory.** Every file of the private tree was inventoried (1060 rows: origin, licence, evidence, decision).
  Result: INCLUDE 983, INCLUDE as patch hunks 27, INCLUDE_AFTER_FIX 3, EXCLUDE_PENDING_OWNER 39, EXCLUDE 8 (1060 rows). The inventory decisions applied here are listed in the assembly report; this tree carries a
  record per file in `PUBLIC_MANIFEST.json`.
- **Generated code policy.** The recompiler of upstream turns the user's own game executable into C files. No such file and no
  line of them is in this tree (checked by a scan against the full pristine generated tree). The hooks that the host puts into
  those files are expressed as address anchors + the sha256 of every deleted generated line + Mashup text (`host/marks/`,
  "bm-anchors 1"): a representation change that does **not** decide any copyright question. The marks edit the user's own
  generated output of the user's own game; applying them refuses on any mismatch.
- **Excluded on purpose:** the host exe and any exe / dll, the three verbatim-generated test fixtures, the translated-code mark
  forms and patch series of earlier private packages, built launcher / Workbench exes, retail-derived demo outputs
  (`photo.txd` and similar), private bookkeeping notes, and the reverse-engineering research notes (`docs/platform-research`,
  37 files; held back pending the owner's decision on the RE-notes question). Some documents and headers still mention guest
  addresses or function names as interface documentation; the open question is listed in `docs/PUBLIC_STATUS.md`.
- **Text layers.** Recorded edits were applied to copies of private files while assembling (identity names and paths, comment
  descriptions in place of quoted generated store statements, machine-specific protected paths in the Workbench, local-only output
  notices, a status banner, version data read from the host readers in the bmpack tests); each is listed with exact counts in the
  assembly report and marked per file in `PUBLIC_MANIFEST.json`.
- Not legal advice and not a clearance: see `docs/PUBLIC_STATUS.md`.
