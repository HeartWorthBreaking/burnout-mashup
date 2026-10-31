/*
 * bm_wtour.h - G8-WT1 EXPERIMENTAL, platform EV (content\tree_ev): race events added by mods to the World Tour (USA /
 * Europe / Asia career) lists of existing race locations, on tracks mods add (content_count\events\WORLD_TOUR_TRACE.md,
 * the design; WT_REPORT.md; platform\content\CONTENT_REPORT.md s3, the N-event generalisation).
 *
 *   [bmashup.extra_events]
 *   version = 1
 *   add = ["harbour-sprint = US_C6_V1 @ US_C3",        # "<event id> = <track> @ <location> [: race | roadrage | faceoff | eliminator | burninglap]" (patch 124; crash refused)
 *          "harbour-night = US_C6_V1 @ US_C3"]
 *   stage = ["harbour-sprint = 020006USC1V1"]          # optional, per event: the retail race whose stage record
 *                                                      #   (Data\stagehed.bin) the event uses (default: the location's first
 *                                                      #   type-A retail race; none there: the region's first)
 *
 * PLATFORM-P3 (P-11), version = 2 adds two optional lists (each entry names an event of this mod's add list once):
 *   names = ["harbour-night = Harbour Night"]         # the list row's text (default: the track's name);
 *                                                     #   1..19 characters (the longest retail row text)
 *   help  = ["harbour-night = Race the harbour at night."]   # the help bar (default: "AN EVENT ADDED BY A MOD.");
 *                                                     #   1..97 characters (the longest retail help-bar text),
 *                                                     #   shown in upper case as the game's own help texts
 * Characters: A-Z a-z 0-9, space and - ' . & (help also !). Texts are host text IDs (bm_names.c, NM1 table);
 * W7 (sub_00074750 loc_0007486A) gives the help bar the cursor row's event help.
 *
 * Identity: the event id ([A-Za-z0-9_-], 1..32) with the mod's id is the event's stable, namespaced key ("mod/event"; its
 * sidecar EVENT record: best medal, attempts). The race ID is HOST-ASSIGNED per start and never saved: "0A07" NN + the
 * track's six characters, NN = the first value the game's tables (slots + Grand Prix lists, junctions, every PrgData race)
 * and every earlier added event do not use; events are taken in key order (mod id, then event id), so the assignment does
 * not depend on the mod list's order.
 *
 * Limits (each a refusal that stops the start, exit 92, with the event and the reason named):
 *  - a location's list shows 6 rows (rows >= 6 get no widgets; event lists do not scroll): retail events + added events
 *    at one location <= 6. The 18 retail race locations have 35 free rows in total (USA 11, Europe 18, Asia 6; US_C2 and
 *    EU_C4 are full) - BO3_WT_MAX = 35 is that structural bound;
 *  - race-type events only (Crash: sub_0001EE80's unchecked junction index); the track a mod adds, in the location's region;
 *    the stage donor a race-type race of the game; a key used once; at most BO3_WT_MAX events in all mods together.
 *
 * How (guest memory from the title's heap through bm_guest.c; Data files unchanged on disk):
 *  W1 after PrgData's load and the loader's 7 -> 6 cut (sub_00015F10 loc_00016196): group 0 is pointed at a host copy of
 *     its 6 runtime elements + ONE host element holding every added event (1 race each), count 7; the cell 0x39DF30
 *     (= 0x39DF38[-1]) gets the first event's race ID after the append; the events are registered with XE1. Per load.
 *  W2 sub_000D80E0 (a location's counts): at every location holding added events, item -1 rows after the retail rows
 *     (+0x304) in key order, count / open count + k, gold count + the events whose sidecar best medal is gold.
 *  W3 sub_000D6D20 when the slot walk is exhausted on a host row: item -1, the event's track name (NM1 host text, else
 *     "Unknown Track").
 *  W4 sub_000D6D20's icon for a host row: that event's sidecar best medal (0 open, 1..3) instead of the game's fixed gold.
 *  W5 sub_0005EBE0 (stage record search) for an added race ID: a host copy of that event's donor record with the track /
 *     race keys replaced (built at the first search, again when the stage file buffer changes).
 *  W6 sub_00066C40 after the list's race ID: an added ID without the host element in the walked PrgData stops the game
 *     (exit 95) instead of the walk's out-of-array read.
 *  W8 sub_0018B250 state 5 (the track Gamedata header): for an added race ID only, the miss path takes that event's alias
 *     ((1) donor ID with the track's characters, (2) donor ID, (3) OFFSGRCF), none -> a named stop (exit 96).
 *  W9 (EV) sub_000E27E0 loc_000E280B, the list's race-ID read 0x39DF38[item]: every host row is item -1 and reads the one
 *     cell, so before that read the host writes the cell with the race ID of the host row under the cursor
 *     (MEM16(0x5501F0)); any other item / list: nothing. One generated line; the preview readers (sub_000DAED0 / DB4E0 /
 *     E0250 / E0740) read the cell too: for an added track they show the game's defaults whichever event it holds.
 * Without a declaration every function returns at once: retail behaviour byte-identical.
 * GP-WT4 (platform 0.1.5): a location may also be the one of a fourth World Tour region ([bmashup.world_tour], bm_wt4.h):
 * its events are listed (W2 / W3) while the map page shows that region (the borrowed view), with no retail rows; the
 * track must be of that region (its first letter); W6 tells bm_wt4.c whether the launched event is one of them.
 */
#ifndef BO3_BM_WTOUR_H
#define BO3_BM_WTOUR_H

#include <stddef.h>
#include <stdint.h>

#define BO3_WT_CELL        0x0039DF30u      /* 0x39DF38[-1]: unreferenced constant-pool bytes (500.0f, 1000.0f) */
#define BO3_WT_ROOT_PTR    0x004D1FE8u      /* the PrgData root (0x4A71A0 + 0x2AE48) */
#define BO3_WT_EXIT_DECL   92
#define BO3_WT_EXIT_LAUNCH 95
#define BO3_WT_EXIT_GAMEDATA 96
#define BO3_WT_ROWS        6u               /* a location's event list: rows 0..5 have widgets (sub_000DC3E0) */
#define BO3_WT_MAX         35u              /* EV: the 18 retail race locations' free rows (6 - retail events, summed) */
#define BO3_WT_NAME_MAX    19u              /* P3: the longest retail text of that row widget ("COMPACT GRAND PRIX ") */
#define BO3_WT_HELP_MAX    97u              /* P3: the longest retail text of the event list's help bar */

enum { BO3_WT_ST_INSTALLS = 0, BO3_WT_ST_ROWS = 1, BO3_WT_ST_STAGE = 2, BO3_WT_ST_LOCS = 3, BO3_WT_ST_ICONS = 4,
       BO3_WT_ST_REFUSED = 5, BO3_WT_ST_GD = 6, BO3_WT_ST_CELL = 7, BO3_WT_STATS = 8 };

/* one mod's [bmashup.extra_events] (mod.toml text): 1 (also when absent; its events are kept), or 0 with why (nothing of
 * that mod kept). Call once per mod, in any order */
int bo3_wt_parse(const char *mod_id, const char *mod_version, const char *text, size_t n, char *why, size_t wn);
void bo3_wt_reset(void);                                         /* tests */

typedef uint32_t (*bo3_wt_alloc_fn)(uint32_t size, uint32_t align);   /* guest VA or 0 (the game: xbox_HeapAlloc) */
void bo3_wt_set_alloc(bo3_wt_alloc_fn fn);
typedef void (*bo3_wt_fail_fn)(int code, const char *why);       /* the game: a named stop (exit code); tests: recorded */
void bo3_wt_set_fail(bo3_wt_fail_fn fn);

/* the game's tables (slot table + Grand Prix lists, junction table, every PrgData race): 1 = the game knows the ID or it
 * cannot be checked */
int bo3_wt_known(uint64_t race_id);
/* the retail events of a race location (the slot rule of sub_00158080): count, or -1 (unknown location) */
int bo3_wt_location_events(uint32_t region, uint32_t value);

/* state, for tests and the log. The single-event getters answer for event 0 (the first in key order) */
uint64_t bo3_wt_race_id(void);
uint32_t bo3_wt_event_va(void);
uint32_t bo3_wt_stage_va(void);
uint32_t bo3_wt_elements_va(void);
int bo3_wt_installed(void);
uint32_t bo3_wt_stats(uint32_t which);
/* EV: every added event, in key order (index 0 .. bo3_wt_count() - 1) */
uint32_t bo3_wt_count(void);                                     /* declared (after the parse), resolved after W1 */
uint64_t bo3_wt_race_id_at(uint32_t i);
uint32_t bo3_wt_event_va_at(uint32_t i);
uint32_t bo3_wt_stage_va_at(uint32_t i);
/* "mod/event", its location ("US_C3") and its row in that location's list (retail count + rank; -1 before W2 listed it) */
const char *bo3_wt_key_at(uint32_t i);
const char *bo3_wt_location_at(uint32_t i);
int bo3_wt_row_at(uint32_t i);

/* the generated-code marks (bo3_wtour_gen.h) */
void bo3_wt_gen_prg_loaded(void);
void bo3_wt_gen_loc(uint32_t menu, uint32_t region, uint32_t loc, uint32_t value);
int bo3_wt_gen_row(uint32_t item, uint32_t row, uint32_t esp);
uint32_t bo3_wt_gen_icon(uint32_t item, uint32_t medal);
uint32_t bo3_wt_gen_stage(uint32_t race);
void bo3_wt_gen_launch(uint32_t lo, uint32_t hi);
uint32_t bo3_wt_gen_gd_key(uint32_t hdr, uint32_t lo, uint32_t hi, uint32_t off);
void bo3_wt_gen_cell(uint32_t item);                             /* W9 (EV) */
uint32_t bo3_wt_gen_help(uint32_t text);                         /* W7 (P3): the help bar's text ID */
uint32_t bo3_wt_help_count(void);                                /* W7 answers for a host row */
const char *bo3_wt_name_at(uint32_t i);                          /* P3: an event's row name ("" none) */
const char *bo3_wt_help_at(uint32_t i);                          /* P3: its help text, upper case ("" none) */
void bo3_wt_game_declare(void);                                  /* the game: every mod's declaration, once */
/* G8-WT2: which alias W8 used last (1..3), 0 none */
uint32_t bo3_wt_gd_alias(void);

#endif
