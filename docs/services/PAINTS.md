# bmashup.paints 1 - player 0's run-time car colour (NEW, platform 0.1.9)

Header: `sdk\include\bmashup_paints.h` (`BM_PAINTS_VERSION 1`). Example: `sdk\examples\bm-car-colour`.
Status: **BUILT, offline-tested and confirmed in the retail game** (main19 patches 31 + 41: 41 checks, 9 / 9 mutants killed, in-place and
re-bind variants). The first validation launch (patch 31) showed no colour change; with patch 41 the body colour changed in a race
(blue, then gold, in screenshots).
Hook request P2 item I. CHANGES THE LOOK of the player's car only (no gameplay value).

## Why a new service
It is the plugin face of the paint registry (`[bmashup.paints]` declarations): the same index rule (an index above the car's
retail palette count selects a host palette) and the same palette resources. No other service changes looks.

## API (`bm_paints_api`)
`claim_dynamic(player)`, `set_colour(player, layer, 0xRRGGBB)`, `factory(player)`, `release(player)` (game thread: an events /
hooks / takedawn.race callback), `status(player, &s)` (any thread). Results: 0 OK, 1 BAD_ARG, 2 CONFLICT, 3 NOT_OWNER,
4 NO_LAYER, 5 RATE, 6 UNSUPPORTED, 7 NO_MEMORY, 8 UNAVAILABLE, 9 WRONG_THREAD.

- Player 0 only (`player` 1 = UNSUPPORTED: split screen not validated). One owner (CONFLICT); release() hands it back.
- The car shows the dynamic paint **in a race** from its next draw until `factory()` (the paint the player chose comes back at
  the next car update; ownership kept) or `release()`. A new `set_colour` after `factory()` shows it again.
- Layers in platform 0.1.9: **BODY** only = the palette entries that differ between the car's retail palettes 0 and 1 (the
  registry's ramp rule), recoloured by brightness from 30 % of the colour to the colour (alpha kept). DECALS / WHEELS answer
  NO_LAYER (no verified per-car tables); NITRO is reserved (the Xbox reader of the boost-flame colour is not located).
- `<= 30` set_colour calls a second (counted in race updates; RATE above).
- `status()`: owned / yours, active (the renderer used the dynamic palette in the last 2 updates), layers (bit 1 << BODY when
  the current car has a ramp), published (palette writes, process), vehicle (the car's ValueDB file stem).

## How it works (host)
The renderer reads the render entity's signed palette index E + 0x59 and asks the registry's mark for any index >= the
texture's palette count; the registry asks this service first for index 127. Player 0's render entity is E = racer 0x73A1D0 +
0x10 (probe PR-A2; E + 0x59 = the racer's paint byte + 0x69). The host writes 127 there at each car update while the paint is
wanted (AI / traffic never reach 127) and puts the saved index back after factory / release and at every load end / race exit
(only if it still reads 127 - else the next load would reduce 127 into the chosen paint). The palette unit (0x440 B; 2 units
reserved) is in the guest high zone (256 MB window) and is edited IN PLACE (probe PR-A2: an edited palette at the same address
is shown at once; constant `BM_P23_PAINTS_LIVE_INPLACE` 1; 0 = the two-unit re-bind path).

## Limits and refusals
- Garage / photo / car-select previews keep the chosen paint (race only in 0.1.9).
- A car whose texture has one palette (no ramp): the registry's palette 0 is shown, status().active 0 (UNSUPPORTED car).
- NO_MEMORY when the high zone has no 0x880 bytes; UNAVAILABLE on a host built with `BO3_HOOKREQ_P23=OFF` or when this build's
  renderer bytes differ from the census (0x3053D / 0x3054C).
- The game save never holds the dynamic paint.
