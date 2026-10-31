# bmashup.hud 2 - the draw list (platform 0.1.9, hook request P2 B2)

Header: `sdk\include\bmashup_hud.h` (`BM_HUD_VERSION 2`). Example: `bm-hud-rpm-meter`.
Status: **HUD_PASS available; the draw list LIVE for QUAD, TEXT and SPRITE** (axis-aligned) on 0.1.9 (main19 items 44 + 46).
Runtime (validation rounds): TEXT draws in the retail HUD; SPRITE draws the P8 pictures of `[bmashup.textures]` entries (the coupe photo was drawn in the
retail game). Always check the result of `draw()` and look at the result on screen.

## What version 2 adds (append-only; the v1 transforms are unchanged)
- `draw(host, player, bm_hud_cmd *)`: a QUAD, a textured SPRITE or TEXT into this picture's list; only inside a bmashup.hooks 3
  HUD_PASS callback (`BM_HUD_NOT_IN_PASS`), player 0 (`UNSUPPORTED` for player 1). Bounds: x -64..704, y -64..544, w / h 0..768,
  |rotation| <= 2 pi, uv 0..1, text 1..63 characters of A-Z 0-9 space . , : ! ? - + / % ' ", size 8..64; 64 commands a plugin,
  256 a picture, 1024 text glyphs a picture (`BM_HUD_GLYPHS_PER_PICTURE`; `FULL`).
- `texture_info(host, texture, &w, &h)`, `draw_available(host)`.
- Results 9 NOT_IN_PASS, 10 FULL, 11 UNKNOWN_TEXTURE, 12 BAD_TEXT, 13 UNSUPPORTED, 15 NO_MEMORY.

## On platform 0.1.9
- The list is drawn with the title's own rect primitive inside its HUD pass (at the end of the boost bar's draw: a picture without
  the boost bar draws no list), once a picture, only while the HUD is shown, in 640 x 480 HUD units (the title's widescreen mapping
  applies). Rotation must be 0 (`UNSUPPORTED` otherwise). Colour / tint = `rgba` (0xRRGGBBAA).
- QUAD: a solid colour (no texture bound).
- TEXT: the host's own 5 x 7 dot font (not the title's font): a glyph is `text_size` high and 5/7 of it wide, advance 6/7 of
  `text_size`; drawn in `rgba`.
- SPRITE: `texture` names an entry of a TXD that a mod declares with **`[bmashup.textures]`** (the front-end texture table; pack it
  with the fetex tool): `"<entry>"` = the plugin's own mod, `"<mod-id>/<entry>"` = any admitted mod. P8 entries only (DXT answers
  `BM_HUD_UNSUPPORTED`); an unknown name, or the texture pool before the front end first ran, answers `BM_HUD_UNKNOWN_TEXTURE`.
  Limits = that table's (256 entries a mod, 1 MiB an entry, 768 entries / 12 MiB in all). `texture_info()` answers the same way.
- The design's `[bmashup.hud]` table is **not** read on 0.1.9: a mod declaring it is refused ("needs a newer platform").
- After the list the title's texture, palette and bind cache are put back, so the title's own HUD draws as before.
- The host's buffers are one 64 KiB block in the guest memory's high zone (with the font); if it is refused, `draw_available()`
  turns 0.

## Evidence
`tests\p23\hooks\test_hudv2.c`: live form (45 checks with stand-ins of the title's routines: call shape, 16-byte colour, the bind
sequence - flush before a texture change, palette, stage-0 texture - the title's state put back, glyph rects / uv / limit, SPRITE
names and formats, registers, once a picture, HUD byte, limits, buffers refused, real-XBE census + tamper; mutants 241..255),
test-executor form (22 checks), unavailable form (15 checks). Runtime: see the status line.
