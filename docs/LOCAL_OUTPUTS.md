# Outputs built from your game stay local

The tools in this repository (Workbench export / stage, carimport, trackbuild, fetex, vehtool, ps2look, the launcher's demo
build) read **your own copy** of the game and build mods, textures, meshes, packs and previews from it. Those outputs
contain data derived from the game. Project policy:

- They are for **your PC only**. Do not upload, share, attach to issues or commit them. Do not put them in this repository.
- Owning a copy of the game does not by itself permit redistributing anything derived from it.
- Only sources and assets that are marked AUTHORED (our own, procedurally made, listed in an `AUTHORED_FILES.json` with a
  sha256) are meant to be shared.
- The generated game-code files and the host built from them are outputs of the same kind.
This is a project rule, not a legal opinion.
