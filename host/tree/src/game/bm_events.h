/*
 * bm_events.h - a host-owned dispatcher for engine points (bm_events.c): one
 * toolkit handler per mark, and behind it an ordered list of subscribers, each
 * called on the game's thread with its register state guarded. Written to be
 * general (no game names in it); Burnout Mashup's private "bmashup.events"
 * service (bm_events_service.c) and its own services sit on it.
 *
 * Rules (research\native_gameplay_api\g8\G8_HOOK_ARCHITECTURE.md):
 *   - a mark is hooked once, by this dispatcher, before the guest runs;
 *   - subscribers are added only while registration is open (the
 *     single-threaded start, up to the end of the plugins' start), then the
 *     lists are fixed;
 *   - order within a mark: observers first (they see the state before any
 *     change), then writers; each kind in registration order;
 *   - a subscriber that changes a guest register (general, esp, xmm, the x87
 *     top) has it put back and counted; for an observer it is also said once
 *     (a writer may call a game routine that uses volatile registers);
 *   - a mark reached again from inside its own dispatch (a subscriber calling
 *     a guest routine that reaches it) is not dispatched again;
 *   - once the process starts to exit, nothing is dispatched any more.
 */
#ifndef BO3_BM_EVENTS_H
#define BO3_BM_EVENTS_H

#include <stdint.h>

#define BO3_EVENTS_MARKS       4        /* marks the dispatcher can own */
#define BO3_EVENTS_SUBSCRIBERS 24       /* subscribers per mark */

enum { BO3_EVENT_OBSERVER = 0, BO3_EVENT_WRITER = 1 };

/* Own the toolkit mark `name` (recomp_patch_on_mark), once. Before the guest
 * runs. The mark's id (>= 0), or -1 (the table is full, or registration is
 * closed). The same name again returns the same id. */
int bo3_events_hook(const char *name);
/* Add fn(user) to mark `id` as kind BO3_EVENT_*; `who` names it in the log.
 * 0, or -1 (closed, full, bad id, no fn). */
int bo3_events_subscribe(int id, int kind, void (*fn)(void *user), void *user, const char *who);
/* Close registration (after the plugins have started), and arrange for
 * dispatch to stop when the process starts to exit (before the plugins'
 * on_shutdown calls, which are registered earlier). */
void bo3_events_close(void);
/* Registration still open. */
int bo3_events_open(void);
/* Stop dispatching (at exit; for the unit test). */
void bo3_events_stop(void);

/* Counters (any thread). */
typedef struct bo3_events_counts {
    uint32_t dispatched;                /* times the mark ran its list */
    uint32_t reentered;                 /* times it was reached from inside its own list (not run) */
    uint32_t after_stop;                /* times it was reached after the stop (not run) */
} bo3_events_counts;
void bo3_events_mark_counts(int id, bo3_events_counts *out);
/* A subscriber's calls and register faults, by its position in mark `id`'s
 * order (0 = first called). 0 when there is none. */
uint32_t bo3_events_calls(int id, int pos);
uint32_t bo3_events_faults(int id, int pos);
/* The subscriber at that position (its user pointer), to check the order. */
void *bo3_events_user_at(int id, int pos);
/* Back to empty: no marks, no subscribers, open (the unit test only; the
 * toolkit's own mark table keeps the handlers it was given, so a test must
 * not run a mark it hooked before the reset). */
void bo3_events_reset_for_test(void);

#endif
