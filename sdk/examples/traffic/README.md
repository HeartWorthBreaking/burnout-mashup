# (l) traffic - bmashup.traffic 1

`bm_gp_traffic.c` = the gp traffic1 slice's example source, unchanged. Build definitions: `GP_DENSITY` (0.0..2.0 asked at
start; negative = probe only), `GP_PROBE` (1 = log every `GP_PROBE_STEPS` steps), `GP_SEQ=1.0,0.0,0.5,1.0` (validation: one
density per race of the process, the next one when a race is left - the tool behind run gp_p4c_1).
Mods built here: `bmashup-sdk-traffic-half` (0.5) and `bmashup-sdk-traffic-probe` (query only). Only one plugin may own the
density (CONFLICT for a second): do not install two density mods. Contract and evidence: `docs\services\TRAFFIC.md`.
