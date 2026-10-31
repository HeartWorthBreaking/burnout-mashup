/* Burnout Mashup private engine events (G8-E1 EXPERIMENTAL): the track / race lifecycle, from the four points the R3 ordering
 * probe verified at run time (R3-b..R3-d; probe v6 classification, l5a\probe_r3\v6):
 *   OPEN     sub_001AA990 after `edi = eax` (edi = the world 0x60EA00): the world is torn down for a transition
 *   ACQUIRE  sub_0018B250 after the store of EAX (the track route buffer) to +0x560 of the object in EDI
 *   PUBLISH  sub_0018B250 after the store of ECX (the lane count) to guest address 0x73A178 (0x73A168 = the published lane array)
 *   LOADED   sub_001AA100 after the store of 0x17 to +0x144384 of the object in EBP (a load's end)
 * Classification (probe v6's rules, without its holder tracking):
 *   load kind  TRACK (acquire + publish since the last load end), FRONT-END (neither), PARTIAL (one), RESTART (a front-end-
 *              type load inside a window whose track load already ended: Race Results / pause RETRY on the resident track)
 *   open class FIRST (no load yet), RACE EXIT (last load TRACK or RESTART and the world's racer list not empty), FRONT-END EXIT
 *              (last load FRONT-END), INCONSISTENT (anything else)
 * Delivered to plugins through bmashup.events v2 (bm_events_service.c): LOAD_DONE at every load end, RACE_EXIT at a RACE EXIT
 * open. Observe only, game thread, copies. MUT=n (tests only) compiles one deliberate defect. */
#ifndef BM_LIFECYCLE_H
#define BM_LIFECYCLE_H

#include <stdint.h>
#include <stdio.h>

#define BO3_LC_WORLD        0x0060EA00u
#define BO3_LC_LIST_COUNT   0x0012B79Cu     /* world + : racer count (R3 registration, verified) */
#define BO3_LC_LIST_MAX     8u

enum { BO3_LC_LD_NONE = 0, BO3_LC_LD_TRACK = 1, BO3_LC_LD_FRONTEND = 2, BO3_LC_LD_PARTIAL = 3, BO3_LC_LD_RESTART = 4 };
enum { BO3_LC_CL_FIRST = 1, BO3_LC_CL_RACE_EXIT = 2, BO3_LC_CL_FRONTEND_EXIT = 3, BO3_LC_CL_INCONSISTENT = 4 };
enum { BO3_LC_PH_CLOSED = 0, BO3_LC_PH_OPEN = 1, BO3_LC_PH_LOADED = 2 };
enum { BO3_LC_EV_LOAD_DONE = 1, BO3_LC_EV_RACE_EXIT = 2 };

typedef struct bo3_lc_event {       /* what the delivery gets (copied into bm_event by the service) */
    uint32_t kind;                  /* BO3_LC_EV_* */
    uint32_t sequence;              /* this event's count (per kind) */
    uint32_t load_kind;             /* LOAD_DONE: BO3_LC_LD_*; RACE_EXIT: the last load's */
    uint32_t open_class;            /* RACE_EXIT: BO3_LC_CL_RACE_EXIT; LOAD_DONE: the window's class (0 before any) */
    uint32_t track_loads;           /* TRACK loads so far */
    uint32_t race_exits;            /* RACE EXITs so far */
    uint32_t lanes;                 /* the resident track's published lane count (0 before any track) */
    uint32_t racers;                /* RACE_EXIT: the world's racer count; LOAD_DONE: 0 */
} bo3_lc_event;

typedef const uint8_t *(*bo3_lc_guest_fn)(void *user, uint32_t va, uint32_t size);
typedef void (*bo3_lc_deliver_fn)(void *user, const bo3_lc_event *ev);
typedef void (*bo3_lc_capture_fn)(void *user);

typedef struct bo3_lifecycle {
    bo3_lc_guest_fn guest;
    bo3_lc_deliver_fn deliver;
    void *user;
    FILE *log;
    int phase;
    int acquired, published;
    uint32_t last_load, win_class, lanes, published_lanes;
    uint32_t loads[5], classes[5], opens, events[3];
    uint32_t open_arg_bad, list_bad;
    /* G8-E5s: called at a RACE EXIT open, after the class is counted and BEFORE the phase leaves LOADED (so a reader that
     * needs a resident track still sees one) and before RACE_EXIT is delivered; the same game-thread point probe v6 read
     * the racer list and its holders at (R3-d: 6 / 6 racers valid, 12 / 12 holders registered). Copies only. */
    bo3_lc_capture_fn exit_capture;
    void *capture_user;
} bo3_lifecycle;

extern bo3_lifecycle g_bo3_lc;

void bo3_lc_configure(bo3_lifecycle *l, bo3_lc_guest_fn guest, bo3_lc_deliver_fn deliver, void *user, FILE *log);
void bo3_lc_open(bo3_lifecycle *l, uint32_t world);
void bo3_lc_acquire(bo3_lifecycle *l, uint32_t buffer);
void bo3_lc_publish(bo3_lifecycle *l, uint32_t array, uint32_t lanes);
void bo3_lc_loaded(bo3_lifecycle *l);
/* G8-E5s: the race-exit capture (after bo3_lc_configure, which clears it); NULL: none */
void bo3_lc_set_exit_capture(bo3_lifecycle *l, bo3_lc_capture_fn fn, void *user);
/* the open class bo3_lc_open would assign for a racer count (the test's replay of recorded runs uses it) */
uint32_t bo3_lc_classify_open(const bo3_lifecycle *l, uint32_t racers);

#endif
