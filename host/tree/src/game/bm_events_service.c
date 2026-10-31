/*
 * bm_events_service.c - "bmashup.events" (include/bmashup_events.h): plugins
 * observe player 1's car update through the engine-point dispatcher
 * (bm_events.c). Each subscribing plugin is its own observer there, so it is
 * counted, ordered (before the bmashup.* writers) and has the guest's
 * registers put back after its call; the dispatcher's own rules apply
 * (registration only while the plugins start, no re-entry, nothing after the
 * process starts to exit).
 *
 * What a plugin gets is a copy made here from player 1's car (0x73A1D0, the
 * car the mark's esi names; player index + 0x27D0 = 0): the dispatcher's
 * count of the point, the step (0x4A1EB4), the race time (+ 0x10DC) and the
 * phase (+ 0x134C), the fields race_service.c reads too. Other cars' updates
 * (player 2's in split screen) reach the point but are not delivered.
 */
#include "bm_events_service.h"

#include <stdatomic.h>
#include <stddef.h>
#include <string.h>

#include "ai_takeover.h"
#include "bm_autopilot.h"
#include "bm_events.h"
#include "bm_lifecycle.h"
#include "plugins.h"

#include <stdlib.h>
#include "recomp_types.h"

extern ptrdiff_t g_xbox_mem_offset;

#ifndef MUT
#define MUT 0       /* tests only: 11 lifecycle registers not put back, 12 lifecycle subscribe after the start;
                       main19 (v7): 17 twin registers not put back, 18 twin subscribe without its mark */
#endif

#define BE_M32(va) (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BE_MF(va)  (*(const float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define BE_STEP    0x004A1EB4u
#define BE_SLOTS   16

static struct slot {
    td_host *host;
    bm_event_fn fn;
    void *user;
    _Atomic uint32_t delivered;
} s_slot[BE_SLOTS];
static int s_nslot;

static void observer(void *user)
{
    struct slot *sl = (struct slot *)user;
    uint32_t car = g_esi;
    bo3_events_counts c;
    bm_event ev;

    if (car != AP_CAR1 || !g_xbox_mem_offset || BE_M32(car + AP_CAR_PLAYER) != 0)
        return;
    bo3_events_mark_counts(bo3_bm_car_update_mark(), &c);
    memset(&ev, 0, sizeof ev);
    ev.struct_size = (uint32_t)sizeof ev;
    ev.event = BM_EVENT_PLAYER_CAR_UPDATE;
    ev.sequence = c.dispatched;
    ev.step = BE_M32(BE_STEP);
    ev.race_time_s = BE_MF(car + AP_CAR_TIME);
    ev.car_phase = BE_M32(car + AP_CAR_PHASE);
    sl->fn(&ev, sl->user);
    atomic_fetch_add(&sl->delivered, 1);
}

/* Version 2: the lifecycle events (bm_lifecycle.c). Not dispatcher marks (the points are direct host calls from the generated
 * loader, G8-E1); the same rules here: subscribe only while registration is open, one subscription per plugin and event,
 * observers only, the guest registers put back after each call (and counted), nothing after the process starts to exit. */
#define BE_LC_EVENTS 10                 /* LOAD_DONE, RACE_EXIT, (version 3) TAKEDOWN, WRECK, (version 4) BOOST_AWARD,
                                           (version 6, GP-CRASH1) CRASH_RESULT: direct host calls; (version 7, main19)
                                           HUD_PASS, TRAFFIC_CONTACT, WRECK_CAUSE, EVENT_SOUND: from bmashup.hooks v3's
                                           dispatcher (bm_hooks.c bo3_hk_dispatch_v3), after the hooks' MODIFY step */
static struct lslot {
    td_host *host;
    bm_event_fn fn;
    void *user;
    _Atomic uint32_t delivered, faults;
} s_lslot[BE_LC_EVENTS][BE_SLOTS];
static int s_nlslot[BE_LC_EVENTS];
static _Atomic uint32_t s_lc_occurrences[BE_LC_EVENTS];
static _Atomic int s_lc_stopped;

static int lc_index(uint32_t event)
{
    return event == BM_EVENT_LOAD_DONE ? 0 : event == BM_EVENT_RACE_EXIT ? 1 : event == BM_EVENT_TAKEDOWN ? 2 :
           event == BM_EVENT_WRECK ? 3 : event == BM_EVENT_BOOST_AWARD ? 4 : event == BM_EVENT_CRASH_RESULT ? 5 :
           event == BM_EVENT_HUD_PASS ? 6 : event == BM_EVENT_TRAFFIC_CONTACT ? 7 : event == BM_EVENT_WRECK_CAUSE ? 8 :
           event == BM_EVENT_EVENT_SOUND ? 9 : -1;
}

/* main19 (version 7): an event twin is subscribable only when its hooks point was offered (its mark is in this build and its
 * start-time check passed: bm_hooks.c bo3_hk_offer_point, before the plugins start). */
static int s_v7_offered[4];

void bo3_bm_events_offer_v7(uint32_t event)
{
    int i = lc_index(event);
    if (i >= 6)
        s_v7_offered[i - 6] = 1;
}

static void lc_stop(void)
{
    atomic_store(&s_lc_stopped, 1);
}

void bo3_bm_events_lifecycle_close(void)
{
    atexit(lc_stop);    /* registered after the plugins' on_shutdown handlers, so it runs before them at exit */
}

static void events_deliver_lifecycle(const bo3_lc_event *lc)
{
    int i = lc ? lc_index(lc->kind == BO3_LC_EV_LOAD_DONE ? BM_EVENT_LOAD_DONE : BM_EVENT_RACE_EXIT) : -1;
    bm_event ev;

    if (i < 0 || atomic_load(&s_lc_stopped))
        return;
    atomic_fetch_add(&s_lc_occurrences[i], 1);
    for (int k = 0; k < s_nlslot[i]; k++) {
        struct lslot *sl = &s_lslot[i][k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        memset(&ev, 0, sizeof ev);
        ev.struct_size = (uint32_t)sizeof ev;
        ev.event = i == 0 ? BM_EVENT_LOAD_DONE : BM_EVENT_RACE_EXIT;
        ev.sequence = lc->sequence;
        ev.step = g_xbox_mem_offset ? BE_M32(BE_STEP) : 0;
        ev.load_kind = lc->load_kind;
        ev.track_loads = lc->track_loads;
        ev.race_exits = lc->race_exits;
        ev.lanes = lc->lanes;
        ev.racers = lc->racers;
        sl->fn(&ev, sl->user);
        atomic_fetch_add(&sl->delivered, 1);
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
#if MUT != 11
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
#endif
            atomic_fetch_add(&sl->faults, 1);
        }
    }
}

/* Version 3 (G8-E6): TAKEDOWN / WRECK, from bm_takedown.c (the game's thread), the same rules as the lifecycle events. */
static void events_deliver_game(uint32_t event, uint32_t actor, uint32_t victim, uint32_t kind, uint32_t actor_takedowns)
{
    int i = lc_index(event);
    bm_event ev;

    if (i < 2 || i > 3 || atomic_load(&s_lc_stopped))
        return;
    atomic_fetch_add(&s_lc_occurrences[i], 1);
    for (int k = 0; k < s_nlslot[i]; k++) {
        struct lslot *sl = &s_lslot[i][k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        memset(&ev, 0, sizeof ev);
        ev.struct_size = (uint32_t)sizeof ev;
        ev.event = event;
        ev.sequence = atomic_load(&s_lc_occurrences[i]);
        ev.step = g_xbox_mem_offset ? BE_M32(BE_STEP) : 0;
        ev.actor = actor;
        ev.victim = victim;
        ev.kind = kind;
        ev.actor_takedowns = actor_takedowns;
        sl->fn(&ev, sl->user);
        atomic_fetch_add(&sl->delivered, 1);
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
#if MUT != 13
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
#endif
            atomic_fetch_add(&sl->faults, 1);
        }
    }
}

/* Version 6 (GP-CRASH1): CRASH_RESULT, from bm_crash.c (the game's thread, the game's record step of a Crash event). The
 * same rules as TAKEDOWN / WRECK: subscribers in order, a copy each, the guest registers put back and counted, nothing once
 * the process starts to exit. main18: then passed to the bmashup.hooks sink (hooks v2 point 7 CRASH_RESULT), below. */
static void events_deliver_crash(const bo3_bm_crash_result *cr)
{
    const int i = 5;
    bm_event ev;

    if (!cr || atomic_load(&s_lc_stopped))
        return;
    atomic_fetch_add(&s_lc_occurrences[i], 1);
    for (int k = 0; k < s_nlslot[i]; k++) {
        struct lslot *sl = &s_lslot[i][k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        memset(&ev, 0, sizeof ev);
        ev.struct_size = (uint32_t)sizeof ev;
        ev.event = BM_EVENT_CRASH_RESULT;
        ev.sequence = atomic_load(&s_lc_occurrences[i]);
        ev.step = g_xbox_mem_offset ? BE_M32(BE_STEP) : 0;
        ev.actor = ev.victim = ev.recipient = BM_EVENT_NO_RACER;
        ev.junction = cr->junction;
        ev.crash_score = cr->score;
        ev.crash_mode = cr->mode;
        memcpy(ev.junction_id, cr->junction_id, sizeof ev.junction_id);
        memcpy(ev.track_id, cr->track_id, sizeof ev.track_id);
        ev.junction_id[sizeof ev.junction_id - 1] = 0;
        ev.track_id[sizeof ev.track_id - 1] = 0;
        sl->fn(&ev, sl->user);
        atomic_fetch_add(&sl->delivered, 1);
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
#if MUT != 16
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
#endif
            atomic_fetch_add(&sl->faults, 1);
        }
    }
}

/* Version 4 (G8-E2): BOOST_AWARD, from bm_boost_award.c (the game's thread, the entry of the game's boost add). The same rules,
 * and: nothing is built when no plugin subscribed (the continuous awards run hundreds of times a second); an add caused while
 * a subscriber runs (re-entry) is not delivered again, only counted. */
static int s_boost_depth;
static _Atomic uint32_t s_boost_reentries;

/* Version 5 (G8-E2M): BOOST_AWARD modifiers - subscription order, one per plugin, the same register rules. */
static struct mslot {
    td_host *host;
    bm_modifier_fn fn;
    void *user;
    _Atomic uint32_t calls, modified, rejected, faults;
} s_mslot[BE_SLOTS];
static int s_nmslot;

static int32_t mod_subscribe(td_host *host, uint32_t event, bm_modifier_fn fn, void *user)
{
    if (!host || !fn)
        return BM_EVENTS_BAD_ARG;
    if (event != BM_EVENT_BOOST_AWARD)
        return BM_EVENTS_UNKNOWN_EVENT;
    if (!bo3_events_open())
        return BM_EVENTS_CLOSED;
    for (int k = 0; k < s_nmslot; k++)
        if (s_mslot[k].host == host)
            return BM_EVENTS_ALREADY;
    if (s_nmslot == BE_SLOTS)
        return BM_EVENTS_FULL;
    memset(&s_mslot[s_nmslot], 0, sizeof s_mslot[0]);
    s_mslot[s_nmslot].host = host;
    s_mslot[s_nmslot].fn = fn;
    s_mslot[s_nmslot].user = user;
    s_nmslot++;
    return BM_EVENTS_OK;
}

static int32_t TD_CALL be_subscribe_modifier(td_host *host, uint32_t event, bm_modifier_fn fn, void *user)
{
    return mod_subscribe(host, event, fn, user);
}

static int finite_f(float f)
{
    return f == f && f - f == 0.0f;
}

/* the amount after every modifier (in order); *modified = 1 when one changed it. Not for HOST awards, not on re-entry. */
static float events_modify_boost(uint32_t recipient, uint32_t source, uint32_t site, float requested, int *modified)
{
    float amount = requested;
    bm_event ev;
    *modified = 0;
    if (!s_nmslot || source == BM_BOOST_HOST || s_boost_depth || atomic_load(&s_lc_stopped) || !finite_f(requested) ||
        requested < 0.0f)
        return requested;
    s_boost_depth = 1;                           /* an add caused inside is neither modified nor delivered */
    for (int k = 0; k < s_nmslot; k++) {
        struct mslot *sl = &s_mslot[k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        float next = amount;
        memset(&ev, 0, sizeof ev);
        ev.struct_size = (uint32_t)sizeof ev;
        ev.event = BM_EVENT_BOOST_AWARD;
        ev.sequence = atomic_load(&s_lc_occurrences[4]) + 1u;
        ev.step = g_xbox_mem_offset ? BE_M32(BE_STEP) : 0;
        ev.actor = ev.victim = BM_EVENT_NO_RACER;
        ev.recipient = recipient;
        ev.award_source = source;
        ev.award_site = site;
        ev.award_amount = amount;
        ev.award_requested = requested;
        ev.award_modified = (uint32_t)*modified;
        atomic_fetch_add(&sl->calls, 1);
        if (sl->fn(&ev, &next, sl->user)) {
#if MUT == 15
            amount = next;                       /* defect: no validation */
            *modified = 1;
#else
            if (finite_f(next) && next >= 0.0f && next <= BM_BOOST_MOD_MAX_FACTOR * requested) {
                if (next != amount) {
                    amount = next;
                    *modified = 1;
                    atomic_fetch_add(&sl->modified, 1);
                }
            } else {
                atomic_fetch_add(&sl->rejected, 1);
            }
#endif
        }
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
            atomic_fetch_add(&sl->faults, 1);
        }
    }
    s_boost_depth = 0;
    return amount;
}

static void events_deliver_boost(uint32_t recipient, uint32_t source, uint32_t site, float amount, float requested,
                                 int modified)
{
    const int i = 4;
    bm_event ev;

    if (atomic_load(&s_lc_stopped))
        return;
    atomic_fetch_add(&s_lc_occurrences[i], 1);
    if (!s_nlslot[i])
        return;
#if MUT != 14
    if (s_boost_depth) {
        atomic_fetch_add(&s_boost_reentries, 1);
        return;
    }
#else
    (void)s_boost_depth;
#endif
    s_boost_depth = 1;
    for (int k = 0; k < s_nlslot[i]; k++) {
        struct lslot *sl = &s_lslot[i][k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        memset(&ev, 0, sizeof ev);
        ev.struct_size = (uint32_t)sizeof ev;
        ev.event = BM_EVENT_BOOST_AWARD;
        ev.sequence = atomic_load(&s_lc_occurrences[i]);
        ev.step = g_xbox_mem_offset ? BE_M32(BE_STEP) : 0;
        ev.actor = ev.victim = BM_EVENT_NO_RACER;
        ev.recipient = recipient;
        ev.award_source = source;
        ev.award_site = site;
        ev.award_amount = amount;
        ev.award_requested = requested;
        ev.award_modified = (uint32_t)modified;
        sl->fn(&ev, sl->user);
        atomic_fetch_add(&sl->delivered, 1);
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
            atomic_fetch_add(&sl->faults, 1);
        }
    }
    s_boost_depth = 0;
}

/* PLATFORM-HK: the public deliveries = this service's own, then the host sink (bmashup.hooks), if one is set. */
static const bo3_bm_events_sink *s_sink;

void bo3_bm_events_set_sink(const bo3_bm_events_sink *sink)
{
    s_sink = sink;
}

void bo3_bm_events_deliver_lifecycle(const bo3_lc_event *lc)
{
    events_deliver_lifecycle(lc);
    if (s_sink && s_sink->lifecycle)
        s_sink->lifecycle(lc);
}

void bo3_bm_events_deliver_game(uint32_t event, uint32_t actor, uint32_t victim, uint32_t kind, uint32_t actor_takedowns)
{
    events_deliver_game(event, actor, victim, kind, actor_takedowns);
    if (s_sink && s_sink->game)
        s_sink->game(event, actor, victim, kind, actor_takedowns);
}

float bo3_bm_events_modify_boost(uint32_t recipient, uint32_t source, uint32_t site, float requested, int *modified)
{
    float amount = events_modify_boost(recipient, source, site, requested, modified);
    if (s_sink && s_sink->modify_boost)
        amount = s_sink->modify_boost(recipient, source, site, requested, amount, modified);
    return amount;
}

void bo3_bm_events_deliver_boost(uint32_t recipient, uint32_t source, uint32_t site, float amount, float requested,
                                 int modified)
{
    events_deliver_boost(recipient, source, site, amount, requested, modified);
    if (s_sink && s_sink->boost)
        s_sink->boost(recipient, source, site, amount, requested, modified);
}

void bo3_bm_events_deliver_crash(const bo3_bm_crash_result *cr)
{
    events_deliver_crash(cr);
    if (cr && s_sink && s_sink->crash)
        s_sink->crash(cr);
}

/* main19 (version 7): one occurrence of a twin event, from bmashup.hooks v3's dispatcher (the game's thread). proto = the
 * event's values (event, sequence, step and its group); each subscriber gets its own copy; the same register rules as the
 * other direct events; nothing once the process starts to exit. */
int bo3_bm_events_v7_wanted(uint32_t event)
{
    int i = lc_index(event);
    return i >= 6 && s_nlslot[i] > 0;
}

void bo3_bm_events_deliver_v7(const bm_event *proto)
{
    int i = proto ? lc_index(proto->event) : -1;
    bm_event ev;

    if (i < 6 || atomic_load(&s_lc_stopped))
        return;
    atomic_fetch_add(&s_lc_occurrences[i], 1);
    for (int k = 0; k < s_nlslot[i]; k++) {
        struct lslot *sl = &s_lslot[i][k];
        uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
        ev = *proto;
        ev.struct_size = (uint32_t)sizeof ev;
        sl->fn(&ev, sl->user);
        atomic_fetch_add(&sl->delivered, 1);
        if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
#if MUT != 17
            g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
#endif
            atomic_fetch_add(&sl->faults, 1);
        }
    }
}

uint32_t bo3_bm_events_boost_reentries(void)
{
    return atomic_load(&s_boost_reentries);
}

static int32_t lc_subscribe(td_host *host, uint32_t event, bm_event_fn fn, void *user)
{
    int i = lc_index(event);

#if MUT != 12
    if (!bo3_events_open())
        return BM_EVENTS_CLOSED;
#endif
#if MUT != 18
    if (i >= 6 && !s_v7_offered[i - 6])
        return BM_EVENTS_UNAVAILABLE;                    /* main19 (v7): the twin's mark is not in this run */
#endif
    for (int k = 0; k < s_nlslot[i]; k++)
        if (s_lslot[i][k].host == host)
            return BM_EVENTS_ALREADY;
    if (s_nlslot[i] == BE_SLOTS)
        return BM_EVENTS_FULL;
    memset(&s_lslot[i][s_nlslot[i]], 0, sizeof s_lslot[i][0]);
    s_lslot[i][s_nlslot[i]].host = host;
    s_lslot[i][s_nlslot[i]].fn = fn;
    s_lslot[i][s_nlslot[i]].user = user;
    s_nlslot[i]++;
    return BM_EVENTS_OK;
}

static struct slot *find(td_host *host)
{
    for (int k = 0; k < s_nslot; k++)
        if (s_slot[k].host == host)
            return &s_slot[k];
    return NULL;
}

/* The slot's position in the dispatcher's order (for its counters). */
static int position(const struct slot *sl)
{
    int mark = bo3_bm_car_update_mark();
    for (int pos = 0; pos < BO3_EVENTS_SUBSCRIBERS; pos++)
        if (bo3_events_user_at(mark, pos) == (const void *)sl)
            return pos;
    return -1;
}

static int32_t TD_CALL be_subscribe(td_host *host, uint32_t event, bm_event_fn fn, void *user)
{
    int mark = bo3_bm_car_update_mark();
    struct slot *sl;

    if (!host || !fn)
        return BM_EVENTS_BAD_ARG;
    if (lc_index(event) >= 0)
        return lc_subscribe(host, event, fn, user);
    if (event != BM_EVENT_PLAYER_CAR_UPDATE)
        return BM_EVENTS_UNKNOWN_EVENT;
    if (!bo3_events_open())
        return BM_EVENTS_CLOSED;
    if (mark < 0)
        return BM_EVENTS_UNAVAILABLE;
    if (find(host))
        return BM_EVENTS_ALREADY;
    if (s_nslot == BE_SLOTS)
        return BM_EVENTS_FULL;
    sl = &s_slot[s_nslot];
    memset(sl, 0, sizeof *sl);
    sl->host = host;
    sl->fn = fn;
    sl->user = user;
    if (bo3_events_subscribe(mark, BO3_EVENT_OBSERVER, observer, sl, "a bmashup.events plugin") != 0)
        return BM_EVENTS_FULL;
    s_nslot++;
    return BM_EVENTS_OK;
}

static int32_t TD_CALL be_stats(td_host *host, uint32_t event, bm_events_stats *out)
{
    bm_events_stats s;
    bo3_events_counts c;
    struct slot *sl;
    uint32_t room;
    int pos;

    if (!host || !out || out->struct_size < 8)
        return BM_EVENTS_BAD_ARG;
    memset(&s, 0, sizeof s);
    s.struct_size = (uint32_t)sizeof s;
    if (lc_index(event) >= 0) {
        int i = lc_index(event);
        s.occurrences = atomic_load(&s_lc_occurrences[i]);
        for (int k = 0; k < s_nlslot[i]; k++)
            if (s_lslot[i][k].host == host) {
                s.delivered = atomic_load(&s_lslot[i][k].delivered);
                s.register_faults = atomic_load(&s_lslot[i][k].faults);
            }
        if (event == BM_EVENT_BOOST_AWARD)                 /* v5: this plugin's modifier counts */
            for (int k = 0; k < s_nmslot; k++)
                if (s_mslot[k].host == host) {
                    s.modified = atomic_load(&s_mslot[k].modified);
                    s.rejected = atomic_load(&s_mslot[k].rejected);
                    s.register_faults += atomic_load(&s_mslot[k].faults);
                }
        room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
        memcpy(out, &s, room);
        out->struct_size = room;
        return BM_EVENTS_OK;
    }
    if (event != BM_EVENT_PLAYER_CAR_UPDATE)
        return BM_EVENTS_UNKNOWN_EVENT;
    bo3_events_mark_counts(bo3_bm_car_update_mark(), &c);
    s.occurrences = c.dispatched;
    sl = find(host);
    if (sl) {
        s.delivered = atomic_load(&sl->delivered);
        pos = position(sl);
        s.register_faults = pos >= 0 ? bo3_events_faults(bo3_bm_car_update_mark(), pos) : 0;
    }
    room = out->struct_size < sizeof s ? out->struct_size : (uint32_t)sizeof s;
    memcpy(out, &s, room);
    out->struct_size = room;
    return BM_EVENTS_OK;
}

static const bm_events_api s_api = {
    (uint32_t)sizeof(bm_events_api), BM_EVENTS_VERSION, be_subscribe, be_stats, be_subscribe_modifier
};

const bm_events_api *bo3_bm_events_api(void)
{
    return &s_api;
}

void bo3_bm_events_init(void)
{
    bo3_plugins_service(BM_EVENTS_SERVICE, BM_EVENTS_VERSION, &s_api);
}
