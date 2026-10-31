# (p) tune-ai - AI values as data mods ([bmashup.tune] version = 2)

Two mods, no code, no approval. Both `mod.toml` files are byte copies of the runtime-validated set (`gp_aitune1_set`):
- `topspeed\mod.toml` (`gp.aitune.topspeed`): `AI/Car | Top speed mps = 40` - RUNTIME-VALIDATED (gp_aitune1_1, gp_p41_2:
  rival caps 40.0 vs 88).
- `aggression\mod.toml` (`gp.aitune.aggression`): attack waits / distances, min target speed, a NEGATIVE boost lead (-40),
  avoidance speed - OFFLINE-VALIDATED only.
They do not clash (different values). Labels: `CHANGES GAMEPLAY: AI`. Details: `docs\services\TUNE_V3_AI.md`.
