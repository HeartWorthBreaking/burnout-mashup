# Roadmap - Burnout Mashup platform (EXPERIMENTAL Windows x64 mod kit 0.4.0, platform 0.1.6)

Nothing here is promised. Full queue: the workspace's `gp\REMAINING_WORK.md` ("After the content phase").

## Content, next
- Cars: an authored collision hull (decode +0x1060), lights, per-part panels, an own `deform`; audio / physics still the donor's.
- Tracks: an authored Gamedata header / event set (other modes), authored sky / audio, off-track reset at runtime, materials beyond
  type 0 (alpha, decals), PVS for free / replay cameras.
- Front end: the 4th region's page globe / counters, Crash junction markers.
- Scale: the 917-car tier as one mod at runtime; failure injection at runtime (texture pool, palettes); a language switch.

## Platform
A freeze of the content host; hooks v2 CRASH_RESULT; `[bmashup.traffic]` as data; a garage query; Linux / macOS builds; another
machine / GPU. Still OPEN: U5, widescreen / split screen, AI aggression, added Crash events, Revenge imports on p4.x (the White
Mountain cloud fix is not resolved).
