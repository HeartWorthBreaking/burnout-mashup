# (j) autopilot-demo - bmashup.autopilot 2

`bm_autopilot_demo.c` is the p4.1 host tree's demo 0.2.0, unchanged (the module that ran in gp_p4_1, gp_p4c_1 / 2 and
gp_p41_2 was built from this source in the workspace; the kit's build gives its own bytes - approve those).
About 5 s into every race it asks for the takeover with `engage2` (ONCE_PER_RACE, bound to that race) and logs the state.

Build options (`-DBMSDK_AUTOPILOT_DEFINES="A=1;B=2"`):
- `BM_AP_DEMO_EVERY_RACE=0`: once per process (the old demo);
- `BM_AP_DEMO_RELEASE_S=N` [+ `BM_AP_DEMO_RELEASE_FROM=k`]: `release` N race seconds after the takeover, from the k-th engaged race;
- `BM_AP_DEMO_PROBE=1`: logged negative controls (requests in the front end and the countdown are refused).
Contract and evidence: `docs\services\AUTOPILOT.md`.
