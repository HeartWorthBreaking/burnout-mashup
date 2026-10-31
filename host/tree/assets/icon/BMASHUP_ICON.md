# assets/icon/bmashup.ico - the Burnout Mashup icon (pfid1)

Provenance: ORIGINAL art, drawn in code, no image file and no upstream (Takedawn) art. `make_bmashup_ico.py` beside this file
is a copy of `icon_pixels()` / `ico()` of the Burnout Mashup tester launcher's starter builder
(`gp\release_readiness\candidate\tester\tools\launcher\exe\build_exe.py`, written for Burnout Mashup: a rounded blue tile
#1A6BDF with two white speed chevrons; sizes 16 / 32 / 48 / 256, 32-bit BGRA). `py -3 -B make_bmashup_ico.py OUT.ico` writes
the same bytes as `bmashup.ico` (sha256 pinned in the pfid1 slice's assets\ASSETS.json; the pfid1 test suite regenerates and
compares). Licence / author line of the icon: OWNER DECISION D3 (QMATRIX Q3), not set here.
The upstream icon files (takedawn*.svg) stay in this folder for the upstream build (BMASHUP_IDENTITY=OFF / BO3_RELEASE) only.
