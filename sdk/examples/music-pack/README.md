# (q) music-pack - [bmashup.music] version 1

Two data mods (no code): `tones\mod.toml` (`gp.music.tones`: soundtrack "BM Test Tones", 440 Hz and 1000 Hz) and
`remix\mod.toml` (`gp.music.tones-remix`: `requires_mods` the first and replaces its 1000 Hz track by 523.25 Hz). The audio
is NOT in the kit: make it with

    py -3 -B make_tones.py <out folder>

which writes `<out>\bmashup-test-tones\{mod.toml, music\tone_440.wav, music\tone_1000.wav}` and
`<out>\bmashup-test-tones-remix\{mod.toml, music\tone_523.wav}` - original synthetic sine tones (90 s, 44.1 kHz, 16-bit
stereo, -9 dBFS, 20 ms fades), deterministic. The result is byte-identical to the runtime-validated pack `gp_music1_set`
(runs gp_music1_3, gp_p41_2; the kit 0.4.0 release check compared it). Details: `docs\services\MUSIC.md`.
