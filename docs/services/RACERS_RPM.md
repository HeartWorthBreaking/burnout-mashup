# bmashup.racers - engine rpm (main21 patch 71, open hook-request item 2)

`bm_racer_info.have_rpm` / `engine_rpm` (racers 3 fields, no table change) now answer on main21 hosts: `have_rpm = 1` and
`engine_rpm` = the car's engine speed in rpm, for every racer whose physics vehicle is found (player and AI).

- Source: the game's own transmission state. `sub_00121560` (every full physics step) keeps the engine speed at G + 0x54
  (G = the car's transmission block, V + 0x1448) in **rad/s**; it converts Idle / Max / Change-up RPM from the car data with
  2 pi / 60. The host converts back (x 60 / 2 pi). Retail cars: idle 1000, change up 5200, redline 7600 rpm.
- The earlier probe PR-A2 had dumped this word at every shift (109 .. 850 rad/s = 1,042 .. 8,121 rpm) but looked for rpm units and
  for correlation with speed x ratio at the shift moments only, where the revs sit at the shift thresholds - so it reported none.
- Guards: its own census (the conversion site and the 2 pi / 60 constant) - a game build whose transmission code differs answers
  have_rpm 0; values outside 0 .. 20,000 rpm (or NaN) answer have_rpm 0.
- Not yet seen in the game: the probe item is a tacho comparison (rpm rising with speed in a gear, dropping at an up-shift,
  idle ~1000 standing, ~7600 at the limiter).
- Evidence: `gp\slices\main21\tests\p6\run_rpm.py` (`test_runs\rpm_final`): racers 3 regression unchanged, census gate (mutant 71),
  rpm 5000 / AI / implausible (mutants 72, 73), 8 census rows vs the XBE.
