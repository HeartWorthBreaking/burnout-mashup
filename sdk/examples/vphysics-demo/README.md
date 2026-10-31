# (k) vphysics-demo - bmashup.vphysics 1

`bm_vphysics_demo.c` is the p4.1 host tree's demo, unchanged (it ran in gp_p41_2). In the 1st, 3rd, ... race of a session
player 1's car runs with `Drag Coef x VPHYS_DRAG_SCALE` (default 0.5, bounds 0.25..4); in the 2nd, 4th, ... it is reset to
its own value. It logs player 1's speed and drag twice a second and the racer list once per race.
Build option: `-DBMSDK_VPHYSICS_DEFINES="VPHYS_DRAG_SCALE=0.75"`. Contract and evidence: `docs\services\VPHYSICS.md`.
