/*
 * bm_xevents.h - G8-XE1 EXPERIMENTAL: medals of events ADDED by mods, kept in the progress sidecar (content_count\events\
 * EVENT_SLOT_TRACE.md, EVENT_AUDIT.md, XE1_REPORT.md). G8-WT1 (events\wt): race IDs in the World Tour form, the best medal
 * readable by the World Tour list (bm_wtour.c).
 *
 * An added event is a race-type event whose first race has a 64-bit race ID the game does not know: it is in neither the
 * 73-slot table (0x39DF38, incl. the Grand Prix lists) nor the 100-entry junction table (0x39D870). For such an ID the
 * game's race-end medal routine sub_0001DFC0 finds no slot and no junction and returns without writing anything (SRC,
 * EVENT_AUDIT C3). One generated line on that double-miss exit (loc_0001DFE6, before its `je` to the exit) calls
 * bo3_xe_gen_medal(lo, hi, medal, profile): for a REGISTERED added event the host records the medal in the sidecar's EVENT
 * record (key = the declaring mod's id / the event's local id: stable and namespaced); the game's save is never written
 * (the profile pointer is passed for checks only). An unregistered ID (a removed mod, a foreign ID) changes nothing.
 *
 * Record semantics (bm_prog_event, data version 1): attempts + 1 per finished race; medal = the best medal so far (a worse
 * replay never lowers it); completed = 1 once a medal > 0 was won. The record is never removed automatically: a removed mod
 * leaves it in place (unreachable), a reinstalled mod with the same id finds it again.
 *
 * Race IDs (G8-WT1): the World Tour menus decode the TRACK of an event from characters 6..11 of its race ID (sub_001582D0,
 * 6 menu sites) and its type from character 1 (sub_00158340), so an added World Tour event's race ID is the structured
 * base-40 string "0A07" NN + the track's six characters (e.g. "0A0700USC6V1" = 0x135DAA29_9D805394): type A (race),
 * element 07, event NN. bo3_xe_race_id_wt() builds it; the caller takes the first NN the game does not know (the same
 * refusal checks as before: bo3_xe_register asks the game's tables through `known` and refuses duplicates). The old hash
 * form (bo3_xe_race_id) is kept only for XE1's own test; the game build does not use it.
 *
 * Scope: race-type events only. Crash-type events are refused at registration: the game's race-end record writer
 * sub_0001EE80 indexes the junction records with an unchecked lookup for them (EVENT_AUDIT C9).
 * main21 C3-8 (notes\C3_8_WORLD_TOUR_TYPES_RE.md): + the Face-Off / Road Rage / Eliminator / Burning Lap types (their medal
 * path is type-blind: the same double miss in sub_0001DFC0) and bo3_xe_race_id_wt_type (the type's letter at character 1,
 * sub_00158340: A race, B Eliminator, C Road Rage, D Face-Off, E Burning Lap). Crash stays refused (its launch path, the
 * jflag-0 branch of sub_00066C40, is not audited).
 */
#ifndef BO3_BM_XEVENTS_H
#define BO3_BM_XEVENTS_H

#include <stdint.h>

#include "bm_progress.h"

#define BO3_XE_MAX 64u

enum { BO3_XE_RACE_TYPE = 1, BO3_XE_CRASH_TYPE = 2,                      /* C3-8: + the types below (Crash refused) */
       BO3_XE_FACEOFF_TYPE = 3, BO3_XE_ROADRAGE_TYPE = 4, BO3_XE_ELIMINATOR_TYPE = 5, BO3_XE_BURNINGLAP_TYPE = 6 };

/* the sidecar store the medals go to (the game build: the track store CC1.2 opened, bo3_cc_progress_store; tests: their own) */
typedef bm_prog *(*bo3_xe_store_fn)(void);
void bo3_xe_set_store(bo3_xe_store_fn fn);
/* the game's own lookups for an ID (slot + Grand Prix lists, junctions, PrgData races): 1 when the game knows it */
typedef int (*bo3_xe_known_fn)(uint64_t race_id);

/* registers an added event: 1, or 0 with why (bad key, a Crash type, an ID the game knows, a duplicate ID or key, full) */
int bo3_xe_register(const char *mod_id, const char *mod_version, const char *local_id, uint64_t race_id, int type,
                    bo3_xe_known_fn known, char *why, size_t wn);
void bo3_xe_reset(void);                                     /* tests */
/* XE1's hash form (FNV-1a 64 of "bmashup.xevent/" ns "/" local, top byte 0xB3): kept for XE1's test only */
uint64_t bo3_xe_race_id(const char *mod_id, const char *local_id);
/* G8-WT1: the World Tour form "0A07" NN + track[0,1,3,4,6,7] (track "RR_NN_VN"); nn 0 .. 1295 (two characters 0-9 A-Z).
 * 1 and *out, or 0 (malformed track / nn) */
int bo3_xe_race_id_wt(const char *track_id, uint32_t nn, uint64_t *out);
/* C3-8: the same with the type letter at character 1 ('A' race, 'B' Eliminator, 'C' Road Rage, 'D' Face-Off, 'E' Burning
 * Lap; any other letter, Crash's 'G' included: 0). bo3_xe_race_id_wt = this with 'A' */
int bo3_xe_race_id_wt_type(const char *track_id, char letter, uint32_t nn, uint64_t *out);
/* G8-WT1: the sidecar record of a registered added event: 1 with the best medal (0..3) and the attempts, 0 when the ID is
 * not registered or nothing is recorded / readable (medal 0, attempts 0) */
int bo3_xe_best(uint64_t race_id, uint32_t *medal, uint32_t *attempts);

/* the generated-code mark: sub_0001DFC0's double miss (eax = -1): edi = ID lo, local ebp = ID hi, ebx = medal 0..3,
 * esi = the profile. 1 when a registered event's medal was recorded */
int bo3_xe_gen_medal(uint32_t lo, uint32_t hi, uint32_t medal, uint32_t profile);
uint32_t bo3_xe_stats(uint32_t which);                       /* 0 recorded, 1 unregistered IDs, 2 store failures */

#endif
