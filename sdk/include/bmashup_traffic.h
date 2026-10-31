/*
 * bmashup_traffic.h - the "bmashup.traffic" service: Burnout Mashup's private, experimental traffic query and density control
 * (Burnout Mashup builds only; may change or go away). gp slice traffic1, atlas gp\atlas\TRAFFIC.md.
 *
 * Contract (version 1):
 *  - **What it changes:** the traffic FLOW of the race's own traffic set (vehicles per minute per lane and vehicle class, the
 *    value the game's spawn timer divides 60 by and its lane population multiplies by), as density x original, for every
 *    trigger of the set. Nothing else: no pool size, no draw limit, no route, no vehicle list, no file.
 *  - **When:** at the race's traffic set-up (the game's traffic init during the race load, and the pre-race population). A
 *    change made during a race is used from the next race's set-up. The value set stays until reset() or the process ends.
 *  - **Bounds:** density is finite and 0.0 <= density <= BM_TRAFFIC_DENSITY_MAX (2.0). 0.0 = no flow at all (no spawned or
 *    pre-placed traffic); 1.0 = the game's own values (and, when nothing was ever scaled, not one byte is written).
 *  - **Fail closed:** the set is checked before any write (trigger count, flow table bounds in guest memory, every original
 *    value finite and in 0..1000 vehicles / minute). A set that does not pass is left untouched and counted in refusals.
 *  - **Idempotent:** the service remembers the original of every value it wrote; a set-up that runs again (staged init, restart,
 *    reloaded Gamedata) always ends at original x density, never compounding.
 *  - **Ownership / conflicts:** the first requester owns the density; another requester's set() is refused (CONFLICT) - no
 *    silent last-writer-wins. reset() by the owner returns to 1.0 (originals written back at the next set-up) and releases.
 *  - **Threads:** set / reset on the game's thread (plugin init, a bmashup.events callback or takedawn.race's update);
 *    status from any thread (a snapshot of plain words; read during a frame it can be one frame old).
 *  - **No addresses:** nothing here is a guest address; the counts come from the traffic system the service verified.
 *
 * Version 2 (platform 0.1.8, hook request P1 "density x3"; append-only, v1 unchanged):
 *  - set_density_v2() takes 0.0 <= density <= BM_TRAFFIC_DENSITY_MAX_V2 (3.0); set_density() (v1) keeps its 2.0 bound, so a
 *    v1 plugin sees exactly v1's behaviour. Same owner, same set-up path, same idempotence as v1.
 *  - A density above BM_TRAFFIC_DENSITY_LABELLED (2.0) is EXPERIMENTAL: logged as such at the request and at each set-up
 *    that applies it, and status().experimental = 1. The game's own limits are NOT raised: the pool (254 vehicles), the
 *    spawn refusal at active + 2, the draw cap (32 a view, 8 crashing) and the 275 m live radius stay; above 2.0 more
 *    vehicles may be refused or not drawn (the measuring launch decides whether the label goes).
 *  - Phase 2 controls (near_vehicles / wreck / clear_wrecked of the draft) are NOT in this version.
 *
 * Version 3 (platform 0.1.9, hook request P2 item F; append-only, v1 / v2 unchanged): two bounded per-vehicle controls (mods
 * 04 / 05) and the crash pool's occupancy.
 *  - status() grows 60 -> 72 bytes: wreck_slots_used (occupancy of the game's 64-slot crash pool, read now), wrecks_by_plugins
 *    and pool_refusals (this race).
 *  - near_vehicles(player): live traffic vehicles nearest to the player's car, as HANDLES (opaque, valid in this step only).
 *  - wreck(handle): the game's own induced traffic crash (the same call the game's traffic code makes at 0x19F820, with player
 *    1's car as the inducer), carried out at the next traffic update on the game's thread. The crash pool has 64 slots and NO
 *    full check of its own: the service counts the free slots first and refuses unless at least BM_TRAFFIC_WRECK_FREE_MIN are
 *    free and fewer than the game's crashing cap are crashing (POOL_FULL). A wreck may take up to 3 slots (linked vehicles).
 *    <= BM_TRAFFIC_WRECKS_PER_SECOND a second per plugin (RATE).
 *  - clear_wrecked(min_distance_m): crashed traffic farther than min_distance_m (>= 150 m) from the player's car removed by the
 *    game's own despawn, at most BM_TRAFFIC_CLEAR_PER_STEP a step.
 *  - THIS BUILD: near_vehicles and wreck answer UNAVAILABLE (the traffic vehicle record's live / position / speed / crashed
 *    fields and player 1's inducer object are not verified yet - nothing is guessed); clear_wrecked answers UNAVAILABLE until a
 *    probe shows the game's despawn frees the crash slot (else it would only hide the body). status()'s v3 counts are live.
 *  - Shared (no owner) but rate-bounded per plugin; game thread for the effects; nothing outlives the race.
 *
 * Version 4 (main21 patch 67, hook request v2 P5a: Traffic Attack seed + spawn floor; append-only, v1 / v2 / v3 unchanged):
 *  - set_seed(mode, seed): the traffic spawn generator's start state. The game resets it at every traffic set-up to ONE fixed
 *    seed (sub_001A3EA0, called by the traffic init sub_001A13F0 at 0x1A1A1A: T + 0x36348 = 0xFD462907, T + 0x3634C =
 *    0x02B9D6F8; no clock is mixed in on Xbox, unlike the PS2 build). BM_TRAFFIC_SEED_GAME (default) = the game's own seed,
 *    nothing written. BM_TRAFFIC_SEED_FIXED = after every such reset (before the first draw) the generator starts from
 *    {0xFD462907 ^ seed, 0x02B9D6F8} instead: seed 0 is exactly the game's own state. The same seed gives the same traffic for the
 *    same race inputs; a plugin that wants a new pattern each race sets a new seed before the race loads and keeps it for that
 *    race's replay (whether a replay re-runs the reset is NOT verified yet: probe P5a-R). The first requester owns the seed;
 *    another requester is refused (CONFLICT); the owner's set_seed(GAME, 0) returns to the game's seed and releases it.
 *  - set_lane_floor(cars_per_min): a FLOOR, not a multiplier, applied at the same traffic set-up as the density and after it:
 *    a lane (one flow record) whose flows (summed over the six vehicle classes, after the density) are above 0 but below the floor
 *    is scaled up to exactly the floor; lanes at or above it and lanes with no flow at all are untouched. 0 = off (default);
 *    0 < floor <= BM_TRAFFIC_LANE_FLOOR_MAX. Same owner as the density (one owner of the set's flows: set_density / reset);
 *    reset() also clears the floor. Same idempotence and fail-closed check as the density.
 *  - status() grows 72 -> 92 bytes: lane_floor, lanes_raised (last set-up), seed_mode, seed, seeds_applied (traffic resets that
 *    took the plugin's seed).
 *  - Build switch BO3_HOOKREQ_P5A=OFF: the seed mark is compiled out of the game code and both functions answer UNAVAILABLE.
 *
 * main21 patch 68 (hook request v2 P5b; no table change, v3's functions start answering):
 *  - near_vehicles(0, ...) and wreck(handle) WORK on builds with BO3_HOOKREQ_P5B (default ON; OFF = UNAVAILABLE as before). The
 *    traffic vehicle records are statically mapped in this build's code (active bitmap, position, state bits, class; census) and
 *    NOT yet runtime-verified (the combined P5 probe): treat the results as EXPERIMENTAL until a release says otherwise.
 *  - near_vehicles: the nearest live vehicles first; rel_pos_m in player 1's car frame (its own world matrix); speed_mps and
 *    same_direction are DERIVED from the vehicle's sampled positions (0 until two samples, i.e. for its first step); crashed =
 *    the game's own "do not induce" state test; vehicle_class = the record's class byte (1 car .. 11 artic trailer, PS2 map).
 *    Player 0 only (anything else BAD_ARG).
 *  - wreck: queued, carried out in the same traffic update right after the game's own induced-crash pass, with the game's own
 *    call and player 1's physics vehicle as the inducer; re-checked there (still live, still inducible, the crash pool guard).
 *    The game's fatal table may refuse the class pair: then nothing happens (no error code can report it after the call).
 *  - clear_wrecked stays UNAVAILABLE (the game frees crash slots only by its bulk reset - probe PR-B).
 *
 * Version 5 (main21 patch 69, hook request v2 P5c "Traffic Attack spread"; append-only):
 *  - The game fills a lane section with N = round(E) cars, E = section length / lane speed / 60 x the lane's flows (cars expected
 *    in the section; sub_001A6070), and gives a section with E < 0.5 NO car at all. Car i is placed at i x (rand x spacing)
 *    (spacing = length / E), which bunches the cars toward the section start.
 *  - set_section_min(cars): a section whose E is above 0 but below `cars` is filled as if E were `cars` (0 = off, the game's own
 *    rule; at most BM_TRAFFIC_SECTION_MIN_MAX). Lanes without flow stay empty.
 *  - set_spawn_spread(on): when the game draws a random offset (its usual case), car i is placed at (i + rand) x length / N:
 *    one car per slice of the section, every car inside it. Without the random offset the game's own position is kept.
 *  - Both: the same owner as the density (set_density / set_lane_floor / reset); reset() clears them; they apply when the game
 *    fills a section (race start and while driving). The random draws are the game's own (a seed still reproduces the traffic).
 *  - status() grows 92 -> 108 bytes: spawn_spread, section_min, sections_raised, cars_spread (this process).
 *  - Build switch BO3_HOOKREQ_P5C=OFF: both marks compiled out, both functions UNAVAILABLE.
 *
 * Version 6 (main21 patch 70, hook request v2 open item "K_FILL"; append-only):
 *  - set_fill_empty_lanes(on): at the traffic set-up, a lane (flow record) whose six flows are all 0 takes the rates of the first
 *    lane of the SAME road (valve) in the same trigger that has flow (the trigger's road byte array p5, +0x14), before the density
 *    and the lane floor; roads without any flowing lane stay empty (e.g. crash-junction sets, flows all 0). Same owner as the
 *    density; reset() clears it; idempotent like the density. status() grows 108 -> 116: fill_empty_lanes, lanes_filled.
 *  - NOT in this version (hook request v2 P5c, open): pre-loading the next sector, filling lane stretches no sector lists, the
 *    colour picker screen (front-end) - see gp\hookreq\HOOK_REQUEST_DESIGN.md s14.
 *
 * Version 7 (main21 patch 109, Bryan item 12 "pre-load the next sector"; append-only):
 *  - set_preload(position_units, seconds): the traffic set's triggers (sectors) start one after the other at a threshold the game
 *    sets when the previous one is done: a race-progress threshold (position triggers) or a clock threshold (timed triggers, e.g.
 *    the CRASH event). With set_preload each NEW trigger's threshold is lowered once by the amount (position: in the game's own
 *    progress units, at least 1 left; time: seconds, not below 0), so its cars are set up earlier, before the player arrives.
 *    0, 0 = off (the game's thresholds). Same owner as the density; reset() clears it. status() grows 116 -> 128 bytes.
 *    Build switch BO3_HOOKREQ_ZPL=OFF: no mark, UNAVAILABLE. The unit of the position amount is the game's (Road Rage thresholds
 *    seen 12 .. 780): probe it before choosing a value. CHANGES the traffic layout of a race.
 *
 * Version 8 (main21 C3-4, open-list item 10 "parked traffic", owner-approved; append-only; EXPERIMENTAL, probe-confirm pending):
 *  - set_parked(handle, 1): one live traffic CAR (a near_vehicles() handle of this step, the same staleness rule as wreck) stops
 *    where it is: from the next traffic update its speed is 0 and its pose (the record's world matrix, the one the game draws and
 *    the players collide with) is written back every update after the game's own vehicle pass. Its lane cursor is unlinked from
 *    its lane ONCE with the game's own unlink (so cars behind it are not held up: the game's follow law only sees the car ahead
 *    in the lane list), then held out of the list. It stays crashable: a player that hits it wrecks it the game's way, and a car
 *    that crashes, despawns or is reused is forgotten (no write after that). Recorded on any thread, carried out on the game's.
 *  - set_parked(handle, 0) RELEASES it: the game's target speed is given back and the pose is no longer written; the car drives
 *    off (outside the lane list: it does not see the car ahead) until the game's own road change re-links it or it despawns, then
 *    it is forgotten. It keeps its slot until then. The host never re-links a car itself.
 *  - Limits: at most BM_TRAFFIC_PARK_MAX cars (parked + releasing), class 1 (car) only, not crashed, not towing / linked, not in a
 *    lane change or road change, not at a road end. The cars belong to the plugin that parked them (another one: CONFLICT).
 *    reset() releases the caller's parked cars (whatever it returns); a new race load forgets every car without any write.
 *  - status() grows 128 -> 144 bytes: parked_now, parks, park_refusals, releases.
 *  - Build switch BO3_HOOKREQ_ZPK=OFF (or a census mismatch): no mark, UNAVAILABLE.
 */
#ifndef BMASHUP_TRAFFIC_H
#define BMASHUP_TRAFFIC_H

#include "takedawn_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BM_TRAFFIC_SERVICE "bmashup.traffic"
#define BM_TRAFFIC_PRELOAD_POS_MAX 400u    /* v7: set_preload position amount bound (the game's progress units) */
#define BM_TRAFFIC_PRELOAD_S_MAX 10.0f     /* v7: set_preload time amount bound (seconds) */
#define BM_TRAFFIC_PARK_MAX 8u             /* v8: cars parked (or being released) at once */
#define BM_TRAFFIC_VERSION 8u              /* 8 (main21 C3-4): + set_parked. 7 (main21 patch 109): + set_preload. 1: status / set / get / reset; 2: + set_density_v2;
                                            * 3 (platform 0.1.9): + crash pool counts, near_vehicles / wreck / clear_wrecked;
                                            * 4 (main21): + set_seed, set_lane_floor; 5 (main21): + spawn spread, section min;
                                            * 6 (main21): + fill empty lanes */
#define BM_TRAFFIC_SECTION_MIN_MAX 4.0f   /* v5: cars a lane section gets at least (the game: 0.5 expected -> none) */
#define BM_TRAFFIC_LANE_FLOOR_MAX 10.0f    /* v4: cars / minute per lane (retail lanes: 0 .. 20.1 summed over the classes) */
enum { BM_TRAFFIC_SEED_GAME = 0, BM_TRAFFIC_SEED_FIXED = 1 };   /* v4 set_seed modes */
#define BM_TRAFFIC_DENSITY_MAX 2.0         /* set_density (v1) */
#define BM_TRAFFIC_DENSITY_MAX_V2 3.0      /* set_density_v2 */
#define BM_TRAFFIC_DENSITY_LABELLED 2.0    /* above: EXPERIMENTAL */

enum {
    BM_TRAFFIC_OK = 0,
    BM_TRAFFIC_BAD_ARG = 1,          /* no host, no out, struct_size below 8 */
    BM_TRAFFIC_UNAVAILABLE = 2,      /* not in a race / no verified traffic system (status) */
    BM_TRAFFIC_OUT_OF_RANGE = 3,     /* density not finite or outside 0 .. BM_TRAFFIC_DENSITY_MAX */
    BM_TRAFFIC_CONFLICT = 4,         /* another requester owns the density; reset by a non-owner */
    /* v3 (appended) */
    BM_TRAFFIC_STALE = 5,            /* a handle from another step */
    BM_TRAFFIC_RATE = 6,
    BM_TRAFFIC_NOT_LIVE = 7,         /* the vehicle is gone or crashed already */
    BM_TRAFFIC_WRONG_THREAD = 8,     /* (reserved: calls are recorded on any thread) */
    BM_TRAFFIC_POOL_FULL = 9,        /* fewer than BM_TRAFFIC_WRECK_FREE_MIN crash slots free, or the crashing cap reached */
    BM_TRAFFIC_NOT_ALLOWED = 10,     /* the game's fatal table refuses this class pair; v8: the vehicle may not be parked */
    /* v8 (appended) */
    BM_TRAFFIC_LIMIT = 11            /* BM_TRAFFIC_PARK_MAX cars parked / being released already */
};
#define BM_TRAFFIC_NEAR_MAX 32u
#define BM_TRAFFIC_WRECKS_PER_SECOND 4u
#define BM_TRAFFIC_WRECK_FREE_MIN 4u      /* free crash slots required before a wreck (3 for a linked pair + 1) */
#define BM_TRAFFIC_WRECK_SLOTS 64u        /* the game's crash pool */
#define BM_TRAFFIC_CLEAR_PER_STEP 2u
#define BM_TRAFFIC_CLEAR_MIN_M 150.0f

enum { BM_TRAFFIC_OWNER_NONE = 0, BM_TRAFFIC_OWNER_YOU = 1, BM_TRAFFIC_OWNER_OTHER = 2 };

typedef struct bm_traffic_status {
    uint32_t struct_size;            /* in: the size you have; out: the size filled in */
    uint32_t in_race;                /* 1: a traffic system with a set is live (the counts below mean something) */
    uint32_t active;                 /* traffic vehicles alive now */
    uint32_t pool;                   /* how many the game can hold at once */
    uint32_t set_flags;              /* the set's mode bits: 1 whole track (online), 2 right-hand side, 4 crash */
    uint32_t triggers;               /* triggers (flow changes along the lap) in the set */
    uint32_t flow_entries;           /* lane flow records over all triggers */
    float flow_start_game;           /* sum of the start trigger's flows, the game's own values (vehicles / minute) */
    float flow_start_now;            /* the same sum as the game reads it now */
    float density;                   /* the density requested now */
    float density_applied;           /* the density of the last set-up (1.0 if none) */
    uint32_t applications;           /* set-ups that wrote values */
    uint32_t refusals;               /* sets refused by the check (nothing written) */
    uint32_t owner;                  /* BM_TRAFFIC_OWNER_* for the caller */
    /* ---- v2 (56 -> 60 bytes) ---- */
    uint32_t experimental;           /* 1: the density requested or last applied is above BM_TRAFFIC_DENSITY_LABELLED */
    /* ---- v3 (60 -> 72 bytes) ---- */
    uint32_t wreck_slots_used;       /* occupancy of the game's 64-slot crash pool (read now; 0 outside a race) */
    uint32_t wrecks_by_plugins;      /* this race */
    uint32_t pool_refusals;          /* wreck() refused with POOL_FULL this race */
    /* ---- v4 (72 -> 92 bytes) ---- */
    float    lane_floor;             /* the floor requested now (cars / minute per lane; 0 = off) */
    uint32_t lanes_raised;           /* lanes the last set-up raised to the floor */
    uint32_t seed_mode;              /* BM_TRAFFIC_SEED_* requested now */
    uint32_t seed;                   /* the seed requested now (FIXED) */
    uint32_t seeds_applied;          /* traffic resets that started from the plugin's seed (this process) */
    /* ---- v5 (92 -> 108 bytes) ---- */
    uint32_t spawn_spread;           /* 1: set_spawn_spread(1) requested now */
    float    section_min;            /* the section minimum requested now (cars; 0 = off) */
    uint32_t sections_raised;        /* sections filled with the minimum instead of the game's none / fewer (this process) */
    uint32_t cars_spread;            /* cars placed by the spread instead of the game's position (this process) */
    /* ---- v6 (108 -> 116 bytes) ---- */
    uint32_t fill_empty_lanes;       /* 1: set_fill_empty_lanes(1) requested now */
    uint32_t lanes_filled;           /* lanes the last set-up gave a sibling lane's rates */
    /* ---- v7 (116 -> 128 bytes) ---- */
    uint32_t preload_units;          /* set_preload's position amount now (0 = off) */
    float    preload_seconds;        /* set_preload's time amount now (0 = off) */
    uint32_t preloads;               /* trigger thresholds lowered (this process) */
    /* ---- v8 (128 -> 144 bytes) ---- */
    uint32_t parked_now;             /* cars parked now (all plugins; releasing ones not counted) */
    uint32_t parks;                  /* cars parked (unlinked and held) this process */
    uint32_t park_refusals;          /* park requests refused at the traffic update (re-check / unlink failed) this process */
    uint32_t releases;               /* parked cars given back to the game (re-linked by its road change or despawned) */
} bm_traffic_status;                 /* 144 bytes (v7: 128, v6: 116, v5: 108, v4: 92, v3: 72, v2: 60, v1: 56) */

/* v3: one vehicle of near_vehicles() */
typedef struct bm_traffic_vehicle {
    uint32_t struct_size;            /* the caller sets it in out[0]; the host writes every entry at this size */
    uint32_t handle;                 /* opaque, this step only */
    float    rel_pos_m[3];           /* in the player car's frame: x right, y up, z forward */
    float    speed_mps;
    uint32_t same_direction;         /* 1: velocity dot the player's > 0 */
    uint32_t crashed;                /* 1: already a wreck */
    uint32_t vehicle_class;          /* the game's class index (the fatal table's), informational */
} bm_traffic_vehicle;                /* 36 bytes */

/* set_fill_empty_lanes modes (main21 patch 90; a host before it answers 2 / 3 with BM_TRAFFIC_BAD_ARG):
 * 1 the same road in the same trigger (v6), 2 also an earlier trigger (the nearest first), 3 also a later one */
enum { BM_TRAFFIC_FILL_OFF = 0, BM_TRAFFIC_FILL_SAME = 1, BM_TRAFFIC_FILL_EARLIER = 2, BM_TRAFFIC_FILL_ANY = 3 };

typedef struct bm_traffic_api {
    uint32_t struct_size;
    uint32_t version;
    int32_t (TD_CALL *status)(td_host *host, bm_traffic_status *out);
    int32_t (TD_CALL *set_density)(td_host *host, double density);
    int32_t (TD_CALL *get_density)(td_host *host, double *density);
    int32_t (TD_CALL *reset)(td_host *host);
    /* ---- v2 (read only when version >= 2 and struct_size covers it) ---- */
    /* As set_density, with the bound 0 .. BM_TRAFFIC_DENSITY_MAX_V2 (3.0); above 2.0 EXPERIMENTAL (see above). */
    int32_t (TD_CALL *set_density_v2)(td_host *host, double density);
    /* ---- v3 (read only when version >= 3 and struct_size covers them) ---- */
    /* *n in = room (<= BM_TRAFFIC_NEAR_MAX), out = written. OK, BAD_ARG, UNAVAILABLE (not in a race; this build: always). */
    int32_t (TD_CALL *near_vehicles)(td_host *host, uint32_t player, bm_traffic_vehicle *out, uint32_t *n);
    /* OK (recorded for the next traffic update), BAD_ARG, STALE, NOT_LIVE, RATE, POOL_FULL, NOT_ALLOWED, UNAVAILABLE. */
    int32_t (TD_CALL *wreck)(td_host *host, uint32_t handle);
    /* OK, BAD_ARG (min_distance_m below BM_TRAFFIC_CLEAR_MIN_M or not finite), UNAVAILABLE (this build). */
    int32_t (TD_CALL *clear_wrecked)(td_host *host, float min_distance_m);
    /* ---- v4 (read only when version >= 4 and struct_size covers them) ---- */
    /* OK, BAD_ARG (no host / unknown mode / GAME with a seed other than 0), CONFLICT (another owner), UNAVAILABLE (P5A off or the
     * reset's bytes differ in this game build). Takes effect at the next traffic set-up. */
    int32_t (TD_CALL *set_seed)(td_host *host, uint32_t mode, uint32_t seed);
    /* OK, BAD_ARG (no host), OUT_OF_RANGE (not finite, < 0 or > BM_TRAFFIC_LANE_FLOOR_MAX), CONFLICT (the density's owner is
     * another plugin), UNAVAILABLE (P5A off). Takes effect at the next traffic set-up. */
    int32_t (TD_CALL *set_lane_floor)(td_host *host, float cars_per_min);
    /* ---- v5 (read only when version >= 5 and struct_size covers them) ---- */
    /* OK, BAD_ARG (no host / on not 0 or 1), CONFLICT (the density's owner is another plugin), UNAVAILABLE (P5C off / census). */
    int32_t (TD_CALL *set_spawn_spread)(td_host *host, uint32_t on);
    /* OK, BAD_ARG, OUT_OF_RANGE (not finite, < 0 or > BM_TRAFFIC_SECTION_MIN_MAX), CONFLICT, UNAVAILABLE. */
    int32_t (TD_CALL *set_section_min)(td_host *host, float cars);
    /* ---- v6 (read only when version >= 6 and struct_size covers it) ---- */
    /* OK, BAD_ARG (no host / on not 0 or 1), CONFLICT (the density's owner is another plugin), UNAVAILABLE (P5A off). */
    int32_t (TD_CALL *set_fill_empty_lanes)(td_host *host, uint32_t on);   /* 0..1; main21 patch 90: + 2 / 3 (BM_TRAFFIC_FILL_*) */
    /* ---- v7 (read only when version >= 7 and struct_size covers it) ---- */
    /* OK, BAD_ARG (no host), OUT_OF_RANGE (units > BM_TRAFFIC_PRELOAD_POS_MAX, seconds not finite / < 0 / > _S_MAX), CONFLICT (the
     * density's owner is another plugin), UNAVAILABLE (ZPL off / census). 0, 0 = off. */
    int32_t (TD_CALL *set_preload)(td_host *host, uint32_t position_units, float seconds);
    /* ---- v8 (read only when version >= 8 and struct_size covers it) ---- */
    /* on 1: OK (recorded: parked at the next traffic update; already parked: OK), BAD_ARG (no host / bad handle / on not 0..1),
     * STALE, NOT_LIVE (gone or crashed), NOT_ALLOWED (not a class-1 car, linked / towing, changing lane or road, at a road end, or
     * being released), LIMIT, CONFLICT (another plugin's car), UNAVAILABLE (ZPK off / census / not in a race).
     * on 0: OK (released, or nothing parked), CONFLICT (another plugin's car), BAD_ARG / STALE / UNAVAILABLE as above. */
    int32_t (TD_CALL *set_parked)(td_host *host, uint32_t handle, uint32_t on);
} bm_traffic_api;

#ifdef __cplusplus
}
#endif
#endif
