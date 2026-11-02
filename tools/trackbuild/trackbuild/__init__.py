"""trackbuild 0.3.0 - original Burnout 3 (Xbox) track geometry authoring: OBJ + track description -> static.dat,
streamed.dat (mesh / LOD units, collision trees, PVS rows), Gamedata (S1 grid / lap lines, S4 AI route) -> a Burnout Mashup
mod. Portable successor of 0.1.6: same outputs, no developer-workspace dependency (readers vendored in trackbuild/_vendor,
donor parts from an explicit --game-data folder). 0.3.0: routes may climb and descend (the floor follows each station's own
height; a flat route builds exactly as with 0.2.1). See README.md."""
VERSION = "0.3.4"   # 0.3.4: host capacity declarations, capacity auto / game; see CHANGELOG
SUCCEEDS = "0.1.6"
