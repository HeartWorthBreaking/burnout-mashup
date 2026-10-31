# bmpack 1.3.4 patch note (mod kit 0.4.1, 2026-10-27)

Portable: no developer-workspace path, no generated game code.
- validate compiles the checker from `host_readers\` (the p4.4 host's readers, 37 files, `HOST_READERS.json`) instead of a host
  tree; 1.3.3's force-included generated headers and the extracted PrgData relocation routine are gone.
- `checker\bmpack_check.c`: the PrgData relocation (base +4 / +0xC pointers, groups of 8 B, records of 0x18 B, items of 0x40 B at
  +0x34) is the kit's own code (`prg_relocate`). A developer build flag `BMPACK_DEV_GENRELOC` links the original routine
  instead; it is used only by the developer-side equivalence test and never by the kit.
- Equivalence (developer side, `gp\alpha\kit041\tests\test_bmpack_equiv.py`): 7 mod-set combinations (BM Test Loop 0.1.3,
  BM Canyon Ring, the World Tour region, the deps fixtures with 3 refusals, the BM Coupes series, combinations): the kit
  checker's JSON = the original-routine build's JSON byte for byte INCLUDING `guest_fnv64` (the whole 64 MB guest image), and =
  bmpack 1.3.3's JSON in every field except `guest_fnv64` (1.3.3 leaves the routine's scratch stack words in the image).
- Configuration through `tools\_lib\bmkit_env.py`: `--game-data`, `--cc`, `--cache`, `--host-readers`; `configure()` for callers.
  The spec's track IDs are checked before the game data is needed. A missing prerequisite -> exit 3 with the fix.
- The summary line names the host readers (`host readers: bmp-0.1.6+ab3a98869d10 (exe fa63df57dde6) (bmpack 1.3.4)`) instead of
  a tree path. `build` outputs are byte-identical to 1.3.3 (T12 pins the 1.1 mod.toml by sha256).
- Tests ported (`tests\test_bmpack.py`): game data and compiler given explicitly; the independent base-40 decoder is the test's
  own; T15 builds the region example from your data; T10 / T14e read the p4.4 readers' texts (platform 0.1.6, autopilot 2: the
  capability refusal now asks for `bmashup.autopilot >= 3`). Result: 96 / 96, mutants 14 / 14 caught.
