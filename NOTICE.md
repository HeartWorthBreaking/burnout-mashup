# NOTICE - required notices (separate from the courtesy credits in CREDITS.md)

Burnout Mashup is an unofficial fan project. It is not affiliated with, authorised by or endorsed by Electronic Arts, Criterion Games, Microsoft or the Takedawn project. "Burnout" is a trademark of its owner. Whether the working name "Burnout Mashup" may be used has NOT been cleared (a disclaimer is not a permission); the name may change.

This tree is a fork-style set of layers and original files. Material of other projects that it carries, or that its patch
files quote as context, stays under the licence of its authors. Nothing here relicenses it. These are licence requirements
(keep the copyright and permission notices); the optional credits are in `CREDITS.md`.

## 1. Takedawn (MIT)
Burnout Mashup's host patch (`host/tree.patch`) contains lines of Takedawn source files as hunk context, `host/tree/` files are
meant to be placed into a Takedawn tree, and `docs/upstream/` holds Takedawn's README. Takedawn
(https://github.com/xenophobentx/takedawn) is MIT licensed:

    Copyright (c) 2026 sp00nz
    Copyright (c) 2026 xenophobentx

The full licence text is `LICENSES/Takedawn-MIT.txt` (a verbatim copy of upstream's `LICENSE` at commit `4f074e211822`).
Takedawn's own third-party notices are in `docs/upstream/THIRD_PARTY_NOTICES.md`.

## 2. xboxrecomp (MIT)
`host/toolkit/toolkit.patch` quotes xboxrecomp (https://github.com/xenophobentx/xboxrecomp) files as context, and `tools/bmpack/host_readers/xboxrecomp/` holds two
inherited source files of it. xboxrecomp is MIT licensed, `Copyright (c) 2026 sp00nz`; the licence text is
`LICENSES/xboxrecomp-MIT.txt` (verbatim, commit `e3756d1b2fef`).

## 3. GNU Lesser General Public License: the modified file `src/apu/apu_core.c` (from xemu)
`host/toolkit/lgpl/apu_core.patch` is a set of modifications (a larger guest-memory window, "MEM256") of `src/apu/apu_core.c`,
a file that xboxrecomp extracted from xemu (<https://github.com/xemu-project/xemu>). Copyright of that file: (c) 2012 espes;
2018-2019 Jannik Vogel; 2019-2025 Matt Borgerson. Its own header says (verbatim, comment stars and line breaks joined): "This library is free software; you can
redistribute it and/or modify it under the terms of the GNU Lesser General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later version." and "WITHOUT ANY WARRANTY"; the whole header
is reproduced in `host/toolkit/lgpl/NOTICE`. The licence text shipped here is version 2.1 of the GNU Lesser General Public License
(`LICENSES/LGPL-2.1-or-later.txt`, byte-equal to <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt> and to
`LICENSES/LGPL-2.1.txt` of xboxrecomp `e3756d1b2fef`). Identifier, from the evidence: the authors' header grants "version 2 ... or any
later version" (literal SPDX form `LGPL-2.0-or-later`; xemu's own copy has the same wording and no SPDX line); xboxrecomp, from
which this tree takes the files, distributes them as `LGPL-2.1-or-later` (its NOTICE), a version selection the header permits.
The Burnout Mashup hunks are offered under the same terms as the file as received: `LGPL-2.1-or-later`, not MIT; the header is
kept verbatim; none of them is an "-only" licence (details: `host/toolkit/lgpl/NOTICE`). Change notice (LGPL-2.1 section 2(b)): the file is changed by the Burnout Mashup contributors, 2026-10-28
(`host/toolkit/lgpl/NOTICE`, and the in-file notice that the patch adds). The per-file pins (blob id and sha256) of the twelve
LGPL-marked files of xboxrecomp are in `host/toolkit/lgpl/NOTICE`; how to obtain the complete modified source and how to rebuild with
a modified copy is in `docs/BUILDING.md` section 7. A program built from this fork links that code statically; building it
requires your own game executable, see `docs/BUILDING.md` and `docs/PUBLIC_STATUS.md` (the LGPL questions for a binary are open
and no binary is distributed here).

## 4. Third-party entries of the xboxrecomp NOTICE
The build that a user makes from this fork pulls xboxrecomp (and with it the components below) from upstream. This repository
itself carries none of those components except as quoted in section 3, but their notices are reproduced in full so that
nothing that applies is lost: the NOTICE of xboxrecomp at `e3756d1b2fef` follows verbatim (LGPL-2.1-or-later xemu APU / NV2A files,
BSD-3-Clause ADPCM-XQ, MIT Dear ImGui / SMAA / Super-xBR, the CAS reference, dr_libs / stb_vorbis, DejaVu / Roboto Condensed
fonts, upscale shaders, derived algorithms). The ADPCM-XQ BSD-3-Clause text is `LICENSES/ADPCM-XQ-BSD-3-Clause.txt`.

## 5. Licence texts in `LICENSES/` (exactly these files; `REUSE.toml` uses exactly these identifiers)
| file | sha256 | text from |
|---|---|---|
| `LICENSES/ADPCM-XQ-BSD-3-Clause.txt` | `034041463fae701573c94fe56ebdc3cdaf5f7eb1e8de12730eb2de4bb15c892c` | xboxrecomp `LICENSES/ADPCM-XQ-BSD-3-Clause.txt` at `e3756d1b2fef` (carries David Bryant's own copyright line) |
| `LICENSES/CC-BY-4.0.txt` | `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744` | SPDX license-list-data `text/CC-BY-4.0.txt` (31846481de7e) |
| `LICENSES/CC0-1.0.txt` | `a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499` | SPDX license-list-data `text/CC0-1.0.txt` (31846481de7e) |
| `LICENSES/LGPL-2.1-or-later.txt` | `20e50fe7aae3e56378ebf0417d9de904f55a0e61e4df315333e632a4d3555d95` | GNU, <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt> (the LGPL version 2.1 text; also xboxrecomp `LICENSES/LGPL-2.1.txt`) |
| `LICENSES/OFL-1.1.txt` | `e794b23d9e437659ce254bd516111d75b580a75352c4446e103b72b78561f838` | Roboto Condensed `OFL.txt` at google/fonts `69d0549` (same bytes as `launcher/fonts/OFL.txt`) |
| `LICENSES/LicenseRef-BurnoutMashup-Artwork.txt` | `06853491ecaae3dbc2237e261c1c72899f3160c601037449b1fcce51be1d43c0` | written for this project |
| `LICENSES/MIT.txt` | `b05785f9f18e6716bab63424b11454513b9943a222595b70411009202fc592b5` | SPDX license-list-data `text/MIT.txt` (31846481de7e) |
| `LICENSES/Takedawn-MIT.txt` | `0de8327ee50d7638222c6590a40aed91f2d2565557a72f134061b65fe918da99` | Takedawn `LICENSE` at `4f074e211822` |
| `LICENSES/xboxrecomp-MIT.txt` | `de6601cea3a6bf2d821b6b89f59b9d6e719cc017e530bcb4bbe2fcf7306e6dda` | xboxrecomp `LICENSE` at `e3756d1b2fef` |

`LICENSES/MIT.txt`, `LICENSES/CC-BY-4.0.txt` and `LICENSES/CC0-1.0.txt` are the unmodified texts of SPDX license-list-data (commit
`31846481de7e`, 2026-10-29); the MIT text keeps its `<copyright holders>` placeholder, the copyright line of this project is in
`LICENSE`. The Developer Certificate of Origin quoted in `CONTRIBUTING.md` is the text of <https://developercertificate.org/>.
Texts that only a binary would need (Dear ImGui, SMAA, Super-xBR, FidelityFX CAS, dr_libs, stb_vorbis, DejaVu, Roboto Condensed,
SDL2, the toolchain runtimes, the upscale shaders) are not conveyed by this tree and are not in `LICENSES/`; the xboxrecomp NOTICE
below names them.

The launcher and the Workbench ship one font file: `launcher/fonts/RobotoCondensed-Medium.ttf`, Roboto Condensed Medium (a subset; Copyright 2011 The Roboto Project Authors), SIL Open Font License 1.1, with its licence beside it (`launcher/fonts/OFL.txt`, `launcher/fonts/VENDORED.txt`).
The title pictures and icons (`launcher/art/*.png`, `host/tree/assets/icon/bmashup.ico`) are finished, fixed pictures made for Burnout Mashup; the lettering was rendered once from a commercial font (Kenyan Coffee, Typodermic) whose font software is not part of this repository, and no game art is in them. They are project artwork, not under MIT or CC0: `LICENSES/LicenseRef-BurnoutMashup-Artwork.txt` (`launcher/art/*.png`, `host/tree/assets/icon/bmashup.ico`). The earlier icon published up to 0.2.0-alpha.2 stays CC0-1.0 in those releases.

## 6. SDL2, toolchain
SDL2 (zlib licence), llvm-mingw, CMake, Ninja, glslang and the Vulkan headers are pulled by the user's own build and are not
part of this tree.

---
# Verbatim: NOTICE of xboxrecomp at commit e3756d1b2fef

xboxrecomp — third-party attribution
====================================

xboxrecomp is MIT licensed (see LICENSE). The components listed below are
not, and are included here under their original licences with their original
copyright intact. They are other people's work and are credited as such.


LGPL-2.1-or-later — extracted from xemu
---------------------------------------

  https://github.com/xemu-project/xemu

  Files, with the copyright each one carries:

    src/apu/apu_core.c    MCPX APU core
                          (c) 2012 espes; 2018-2019 Jannik Vogel;
                          2019-2025 Matt Borgerson
    src/apu/apu_dsp.c     MCPX APU DSP (GP/EP)
                          (c) 2012 espes; 2019-2025 Matt Borgerson
    src/apu/apu_vp.c      MCPX APU voice processor
                          (c) 2012 espes; 2018-2019 Jannik Vogel;
                          2019-2025 Matt Borgerson
    src/apu/apu_regs.h    (c) 2012 espes; 2018-2019 Jannik Vogel;
                          2019-2021 Matt Borgerson
    src/apu/apu_state.h   (c) 2012 espes; 2018-2019 Jannik Vogel;
                          2019-2025 Matt Borgerson
    src/apu/apu_debug.h   (c) 2020-2021 Matt Borgerson
    src/apu/fpconv.h      (c) 2020-2025 Matt Borgerson
    src/apu/apu.h         the APU code's public API; the file says
                          "Extracted from xemu (LGPL v2+)" and names no
                          copyright holder, so it is listed here with the
                          files above
    src/nv2a/nv2a_regs.h  NV2A register definitions
                          (c) 2012 espes; 2015 Jannik Vogel
    src/nv2a/nv2a_core.c  NV2A register handlers, adapted from xemu's
                          hw/xbox/nv2a/nv2a.c
                          (c) 2012 espes; 2015 Jannik Vogel;
                          2018-2025 Matt Borgerson
    src/nv2a/nv2a_state.h NV2A state, adapted from xemu's
                          hw/xbox/nv2a/nv2a_int.h
                          (c) 2012 espes; 2015 Jannik Vogel;
                          2018-2025 Matt Borgerson

  src/apu/apu_state.h also holds the HRTF filter of xemu's
  hw/xbox/mcpx/apu/vp/hrtf.h ((c) 2025 Matt Borgerson, the same licence), and
  one piece that is NOT under this licence: the ADPCM decoder (see
  "BSD-3-Clause" below).

  The upstream files say "version 2 of the License, or (at your option) any
  later version" of the GNU Lesser General Public License; that wording is
  kept in each file here. src/nv2a/nv2a_core.c and nv2a_state.h carry a short
  form of it ("LGPL v2+") and build into the xbox_nv2a library, which the
  toolkit's umbrella target links; a program that calls nothing in it (the
  Burnout 3 port) ends up without that code.

  src/apu/apu_shim.h is this project's own file but is released under the
  same licence, because it exists only to host the extracted APU code.

  Licensed under the GNU Lesser General Public License, version 2.1 or (at
  your option) any later version. The full text is in LICENSES/LGPL-2.1.txt;
  the canonical copy is
  https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt

  These files keep their own licence. Linking against them from MIT or
  proprietary code is expressly permitted by the LGPL — that is what
  distinguishes it from the GPL. What the LGPL asks in return is that the
  notices stay, that the source stays available, and that a user can relink
  against a modified version. For the source, this repository is that. A
  program distributed in binary form that links these files must carry this
  notice and the licence text, and must come with the complete source of the
  release it was built from (this repository at the release's commit, and
  the build scripts of the program), so that whoever has it can change these
  files and build the program again.


BSD-3-Clause — ADPCM decoder from ADPCM-XQ (through xemu)
--------------------------------------------------------

  https://github.com/dbry/adpcm-xq

  src/apu/apu_state.h, adpcm_decode_block() and its tables: taken from xemu's
  hw/xbox/mcpx/apu/vp/adpcm.h, which is the ADPCM-XQ decoder,
  Copyright (c) David Bryant, all rights reserved. Its licence, which must be
  reproduced with binaries, is LICENSES/ADPCM-XQ-BSD-3-Clause.txt.


The voice low-pass — this project's own (replaced xemu's GPL-2.0 filter)
------------------------------------------------------------------------

  src/apu/apu_lowpass.h is xboxrecomp's own file, MIT like the rest.

  Until it was written, src/apu/apu_state.h held the state variable filter of
  xemu's hw/xbox/mcpx/apu/vp/svf.h (sv_filter, setup_svf(), run_svf()), which
  that file's header gives as "Adapted from SWH LADSPA Plugins package,
  modified for xemu ... Author: Steve Harris, andy@vellocet. License: GPLv2".
  GPL-2.0 code cannot be linked into a program that is distributed with code
  that cannot be published as source, so it was removed: no line of it is in
  this repository from this commit on (the history before it still has it).

  The replacement was not derived from that code. It is the textbook digital
  state variable filter (Hal Chamberlin, "Musical Applications of
  Microprocessors"), written from the book's description; the old filter was
  only ever run, as a compiled black box, to measure what a voice has to
  sound like: the level of its passband against the resonance setting, and
  that it answers without a sample of delay. apu_lowpass.h says how the voice
  processor's two arguments map onto the textbook's f and q, and
  tests/apu_lowpass checks it over the whole range of the registers.


The DSP processors' state — this project's own (xemu's GPL declarations removed)
--------------------------------------------------------------------------------

  Until this commit src/apu/apu_state.h declared the state of xemu's DSP56300
  core (the DSP_*_SIZE / DSP_REG_MAX constants, struct dsp_core_s, struct
  DSPState and the DMA state that points into it): about a hundred lines, the
  same as in xemu's hw/xbox/mcpx/apu/dsp/interp/dsp_cpu.h, dsp_cpu_regs.h and
  dsp/dsp.h, which are GNU General Public License, version 2 or later
  ("Copyright (c) 2015 espes ... Adapted from Hatari DSP M56001 emulation"),
  not LGPL. They were declarations only, and nothing in them was ever read:
  the toolkit runs no DSP program. They are removed, and the constants with
  them. What stands in their place (ApuDspUnit, ApuDspStandIn) is this
  project's own: a marker that a processor was set up, and nothing else.

  xemu's DSP56300 interpreter itself (hw/xbox/mcpx/apu/dsp: dsp.c, dsp_cpu.c,
  the instruction emulation, GPL-2.0-or-later) was never in this repository:
  src/apu/apu_dsp.c is a stand-in written against the LGPL apu.c, with no
  code from it.

  A comparison of every source file here against the 148 C sources and
  headers of xemu's hw/xbox (2026-10-12, exact lines) finds lines in common
  only with files that are LGPL-2.1-or-later there and with the BSD-3-Clause
  ADPCM decoder: none with a GPL file.


Derived algorithms — credited, independently implemented
--------------------------------------------------------

  src/d3d/d3d8_swizzle.h
    Implements Xbox Z-order (Morton) texture unswizzling. The
    masked-increment technique is Fabian Giesen's, published on his blog;
    xemu's hw/xbox/nv2a/pgraph/swizzle.c is cited in the file as the
    reference that pointed us at it.

  src/d3d/d3d8_combiners.h
    NV2A register-combiner translation. Cites xemu's pgraph combiner
    implementation as a reference for the hardware's behaviour.

  src/kernel/nv2a_vsh_fields.h
    The NV2A vertex-program field table, as (word, shift, bits). Cites
    xemu's hw/xbox/nv2a/pgraph/vsh.c as the reference for the layout.

  src/kernel/nv2a_combiner.h
    NV2A register-combiner field table and CPU evaluator. Cites xemu's
    hw/xbox/nv2a/pgraph/glsl/psh.c as the reference for the encoding and
    the combiner semantics.

  src/kernel/nv2a_backend_common.h
    Cube-map face selection and face stride. Cites xemu's
    hw/xbox/nv2a/pgraph texture code (texture.c) as the reference for the
    face order and the per-face layout.

  src/d3d/nv2a_vk_glsl.c
    GLSL to SPIR-V with glslang. The call sequence and input settings follow
    xemu's pgraph_vk_compile_glsl_to_spv (hw/xbox/nv2a/pgraph/vk/glsl.c,
    LGPL-2.1-or-later): preprocess, parse, link with the SPIR-V and Vulkan
    rules, generate. Those are the steps glslang's C API asks for. The code
    here is this project's own, with its own error handling, limits and
    caching.

  Algorithms and hardware behaviour are not themselves copyrightable, and
  these are our own implementations. They are listed here because the debt is
  real and should be visible even where no licence obligation attaches. If
  anyone believes any of these files crosses from "implements the same
  algorithm" into "copies the expression", raise an issue and we will rewrite
  or relicense it — getting the credit right matters more to us than the licence
  label.


MIT — Dear ImGui
-----------------

  https://github.com/ocornut/imgui

  third_party/imgui/ (release v1.92.9b, see third_party/imgui/VENDORED.txt): the
  core and the SDL2, Metal and Vulkan backends, unmodified. (c) 2014-2026 Omar
  Cornut. The licence text is third_party/imgui/LICENSE.txt. Used by the
  in-game settings overlay (src/overlay).


MIT - SMAA
-----------

  https://github.com/iryoku/smaa (reference implementation, commit 71c806a)

  third_party/smaa/: SMAA.hlsl, the area and search lookup textures
  (AreaTex.h, SearchTex.h) and LICENSE.txt, unmodified. (c) 2013 Jorge
  Jimenez, Jose I. Echevarria, Belen Masia, Fernando Navarro, Diego Gutierrez.
  The licence notice is kept in each copy of the source (src/video/
  smaa_hlsl.inc carries it); it need not accompany binaries. Used by the
  window presenters' SMAA 1x pass (src/video/smaa.c).

Also in the presenters: AMD FidelityFX CAS (MIT, the algorithm in
src/video/post_shaders.h) and FXAA (NVIDIA's FXAA 3.11 algorithm, written
here from the paper).


MIT - Super-xBR (2D art scaler)
-------------------------------

  Hyllian's Super-xBR image scaler. src/kernel/nv2a_texscale.c is a C
  version written here from the three passes of his shaders
  (super-xbr-pass0, -pass1, -pass2 as published in libretro's shader
  collections), changed to work on premultiplied colour with alpha. Used
  by graphics.ui_scale, which scales a title's 2D art before upload. The
  notice, which this file carries with every binary:

  Copyright (c) 2015 Hyllian - sergiogdb@gmail.com

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.


Public domain - dr_libs and stb_vorbis (music decoders)
-------------------------------------------------------

  https://github.com/mackron/dr_libs (commit dfe8377), David Reid:
  third_party/dr_libs/dr_mp3.h, dr_flac.h, dr_wav.h, unmodified. Public
  domain (Unlicense) or MIT No Attribution. dr_mp3 contains minimp3 (lieff,
  CC0).

  https://github.com/nothings/stb (commit 2c980bb), Sean Barrett:
  third_party/stb_vorbis/stb_vorbis.c, unmodified. Public domain (Unlicense)
  or MIT.

  Compiled into src/soundtrack/xst_decode.c, which plays a folder of the
  user's own music as Xbox custom soundtracks. Neither asks for a notice
  with binaries; they are credited here all the same.


Bitstream Vera licence - DejaVu Sans Mono (overlay font, a subset)
-------------------------------------------------------------------

  https://github.com/dejavu-fonts/dejavu-fonts (release 2.37)

  src/overlay/overlay_font_ext.h: a subset of DejaVu Sans Mono (Latin
  Extended-A and -B, Greek, Cyrillic, some punctuation), embedded in the
  settings overlay behind Dear ImGui's own font for the letters that one
  lacks. Fonts (c) 2003 Bitstream, Inc.; glyphs imported from Arev (c) 2006
  Tavmjong Bah; the DejaVu changes are in the public domain. The licence is
  third_party/dejavu/LICENSE.txt: free to use, copy, merge and distribute,
  with its copyright and permission notices in every copy. A program
  distributed in binary form with the overlay built in carries that file.


SIL Open Font License 1.1 - Roboto Condensed (overlay font, a subset)
---------------------------------------------------------------------

  https://github.com/google/fonts, ofl/robotocondensed (commit 69d0549)

  src/overlay/overlay_font_ui.h: Roboto Condensed at the Medium weight, cut
  to Latin, Latin-1, Latin Extended-A and -B, Greek, Cyrillic and some
  punctuation (third_party/roboto_condensed/make_subset.py), embedded as
  the settings overlay's text font. Copyright 2011 The Roboto Project
  Authors. Licensed under the SIL Open Font License 1.1, whose text is
  third_party/roboto_condensed/OFL.txt; a program distributed in binary form
  with the overlay built in carries that file. The font may be bundled with
  software and sold with it; it may not be sold by itself.


Reference material (no code taken)
-----------------------------------

  xemu, Cxbx-Reloaded and xboxdevwiki were used as references for hardware
  behaviour: register offsets, kernel export ordinals, structure layouts.
  Those are functional facts rather than expression, and no code was copied
  for them.


Contributors to xboxrecomp itself are credited in CONTRIBUTORS.md.


LGPL-3.0-or-later — texture upscaler shaders (third_party/upscale_shaders)
--------------------------------------------------------------------------

  FSRCNNX_x2_8-0-4-1.glsl, (c) 2017-2021 igv
  (https://github.com/igv/FSRCNN-TensorFlow, release 1.1), and
  nnedi3-nns16-win8x4.hook from bjin's NNEDI3 prescalers
  (https://github.com/bjin/mpv-prescalers, LGPL-3.0-or-later; NNEDI3 by
  tritical), with the compute wrappers generated from them. Separate files loaded at runtime by graphics.texture_upscale; not
  compiled into any binary. Provenance, hashes, changes and how to replace
  them: third_party/upscale_shaders/NOTICE.md; licence texts:
  third_party/upscale_shaders/COPYING.LESSER and COPYING.
