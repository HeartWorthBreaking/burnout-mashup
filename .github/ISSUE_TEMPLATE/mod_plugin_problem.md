---
name: Mod or plugin problem
about: A data mod or plugin is refused, misbehaves, or a tool (bmpack, vehtool, carimport, trackbuild, fetex) gives a wrong result
title: "[mod] "
labels: mods, alpha
---

**Mod / plugin**: id ___ version ___ ; AUTHORED by you / demo / from another tester; built with kit ___ (tool + version):

**What the validator said** (bmpack / vehtool / tool validate output):
```
paste here
```

**What the game said** ([ADMIT] / [DEPS] / [MOD] / [PLATFORM] lines from run.log; the export has them):

**Expected**:

**Does it happen with this mod alone?** yes / no / not tried

Do NOT attach DERIVED packages (car / track packages built from game data). AUTHORED sources (glTF, OBJ, PNG, mod.toml) are fine.

## Diagnostic export (required)
Run `diag.cmd --bundle . --out diag\bugreport.zip` in the tester bundle folder, read the printed file list, and attach the zip.
- [ ] attached the diagnostic export
- [ ] I did NOT attach saves, game files, generated mods or the exe