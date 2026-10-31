# (m) ai - bmashup.ai 1

`bm_gp_ai.c` = the gp ai1 slice's example source, unchanged. Build definitions: `GP_PACE` (0.5..1.5 asked at start; negative
= probe only), `GP_PROBE_STEPS`, `GP_SEQ=1.0,0.7,1.3,1.0` (validation: one pace per race of the process - the tool behind run
gp_p4c_2). Mods built here: `bmashup-sdk-ai-slow` (0.8) and `bmashup-sdk-ai-probe`. One owner of the pace (CONFLICT for a
second). The game's rubber band compensates part of the factor. Contract and evidence: `docs\services\AI.md`.
