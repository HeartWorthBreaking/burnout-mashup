/* Burnout Mashup private engine events (G8-E1 EXPERIMENTAL): see bm_lifecycle.h. MUT=n (test builds only) compiles one
 * deliberate defect for the negative controls. */
#include "bm_lifecycle.h"

#include <string.h>

#ifndef MUT
#define MUT 0
#endif

bo3_lifecycle g_bo3_lc;

static const char *load_name(uint32_t k)
{
    return k == BO3_LC_LD_TRACK ? "track" : k == BO3_LC_LD_FRONTEND ? "front-end" : k == BO3_LC_LD_PARTIAL ? "partial" :
           k == BO3_LC_LD_RESTART ? "restart" : "none";
}

void bo3_lc_configure(bo3_lifecycle *l, bo3_lc_guest_fn guest, bo3_lc_deliver_fn deliver, void *user, FILE *log)
{
    if (!l)
        return;
    memset(l, 0, sizeof *l);
    l->guest = guest;
    l->deliver = deliver;
    l->user = user;
    l->log = log;
}

static void emit(bo3_lifecycle *l, uint32_t kind, uint32_t load_kind, uint32_t racers)
{
    bo3_lc_event ev;
    memset(&ev, 0, sizeof ev);
    ev.kind = kind;
    ev.sequence = ++l->events[kind];
    ev.load_kind = load_kind;
    ev.open_class = l->win_class;
    ev.track_loads = l->loads[BO3_LC_LD_TRACK];
    ev.race_exits = l->classes[BO3_LC_CL_RACE_EXIT];
    ev.lanes = l->lanes;
    ev.racers = racers;
    if (l->deliver)
        l->deliver(l->user, &ev);
}

uint32_t bo3_lc_classify_open(const bo3_lifecycle *l, uint32_t racers)
{
#if MUT == 1
    (void)racers;                               /* defect: the racer list is not consulted */
    return l->last_load == BO3_LC_LD_NONE ? BO3_LC_CL_FIRST :
           l->last_load == BO3_LC_LD_TRACK || l->last_load == BO3_LC_LD_RESTART ? BO3_LC_CL_RACE_EXIT :
           l->last_load == BO3_LC_LD_FRONTEND ? BO3_LC_CL_FRONTEND_EXIT : BO3_LC_CL_INCONSISTENT;
#elif MUT == 2
    return l->last_load == BO3_LC_LD_NONE ? BO3_LC_CL_FIRST :   /* defect: a restart does not lead to a race exit */
           l->last_load == BO3_LC_LD_TRACK && racers > 0 ? BO3_LC_CL_RACE_EXIT :
           l->last_load == BO3_LC_LD_FRONTEND ? BO3_LC_CL_FRONTEND_EXIT : BO3_LC_CL_INCONSISTENT;
#else
    return l->last_load == BO3_LC_LD_NONE ? BO3_LC_CL_FIRST :
           (l->last_load == BO3_LC_LD_TRACK || l->last_load == BO3_LC_LD_RESTART) && racers > 0 ? BO3_LC_CL_RACE_EXIT :
           l->last_load == BO3_LC_LD_FRONTEND ? BO3_LC_CL_FRONTEND_EXIT : BO3_LC_CL_INCONSISTENT;
#endif
}

void bo3_lc_open(bo3_lifecycle *l, uint32_t world)
{
    uint32_t n = 0, cls;
    const uint8_t *p;

    if (!l)
        return;
    if (world != BO3_LC_WORLD) {
        l->open_arg_bad++;                      /* the OPEN argument is not the world: the list is not read */
    } else if (l->guest && (p = l->guest(l->user, world + BO3_LC_LIST_COUNT, 4)) != NULL) {
        n = (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
        if (n > BO3_LC_LIST_MAX) {
            l->list_bad++;
            n = 0;
        }
    }
    cls = bo3_lc_classify_open(l, n);
    l->opens++;
    l->classes[cls]++;
#if MUT != 5 && MUT != 6
    if (cls == BO3_LC_CL_RACE_EXIT && l->exit_capture)
        l->exit_capture(l->capture_user);       /* G8-E5s: still LOADED: the race's final route holders are copied here */
#endif
    l->phase = BO3_LC_PH_OPEN;
#if MUT == 6
    if (cls == BO3_LC_CL_RACE_EXIT && l->exit_capture)
        l->exit_capture(l->capture_user);       /* defect: captured after the phase flip */
#endif
    l->win_class = cls;                         /* (a load's acquire / publish evidence is cleared only at its end, as v6) */
    if (l->log)
        fprintf(l->log, "[LIFECYCLE] world transition %u: %s (racers %u, last load %s)\n", (unsigned)l->opens,
                cls == BO3_LC_CL_FIRST ? "first" : cls == BO3_LC_CL_RACE_EXIT ? "RACE EXIT" :
                cls == BO3_LC_CL_FRONTEND_EXIT ? "front-end exit" : "inconsistent", (unsigned)n, load_name(l->last_load));
    if (cls == BO3_LC_CL_RACE_EXIT)
        emit(l, BO3_LC_EV_RACE_EXIT, l->last_load, n);
}

void bo3_lc_set_exit_capture(bo3_lifecycle *l, bo3_lc_capture_fn fn, void *user)
{
    if (!l)
        return;
    l->exit_capture = fn;
    l->capture_user = user;
}

void bo3_lc_acquire(bo3_lifecycle *l, uint32_t buffer)
{
    (void)buffer;                               /* as v6: the point itself is the evidence */
    if (!l)
        return;
    l->acquired = 1;
}

void bo3_lc_publish(bo3_lifecycle *l, uint32_t array, uint32_t lanes)
{
    (void)array;
    if (!l)
        return;
    l->published = 1;
    l->published_lanes = lanes;
}

void bo3_lc_loaded(bo3_lifecycle *l)
{
    uint32_t kind;

    if (!l)
        return;
    kind = l->acquired && l->published ? BO3_LC_LD_TRACK :
           !l->acquired && !l->published ? BO3_LC_LD_FRONTEND : BO3_LC_LD_PARTIAL;
#if MUT != 3
    if (kind == BO3_LC_LD_FRONTEND && l->phase == BO3_LC_PH_LOADED &&
        (l->last_load == BO3_LC_LD_TRACK || l->last_load == BO3_LC_LD_RESTART))
        kind = BO3_LC_LD_RESTART;               /* the track stays resident: Race Results / pause RETRY */
#endif
#if MUT == 4
    l->published = 0;                           /* defect: the acquire is not cleared at a load end */
#else
    l->acquired = l->published = 0;
#endif
    l->last_load = kind;
    l->loads[kind]++;
    l->lanes = kind == BO3_LC_LD_TRACK || (kind == BO3_LC_LD_PARTIAL && l->published_lanes) ? l->published_lanes :
               kind == BO3_LC_LD_RESTART ? l->lanes : 0;
    l->published_lanes = 0;
    if (l->phase != BO3_LC_PH_CLOSED)
        l->phase = BO3_LC_PH_LOADED;
    if (l->log)
        fprintf(l->log, "[LIFECYCLE] load done: %s load %u (lanes %u)\n", load_name(kind), (unsigned)l->loads[kind],
                (unsigned)l->lanes);
    emit(l, BO3_LC_EV_LOAD_DONE, kind, 0);
}

#ifdef BO3_LIFECYCLE_GAME   /* the game build (CMake); tests use bo3_lc_configure with stand-ins */
#include <stddef.h>

extern ptrdiff_t g_xbox_mem_offset;
extern void bo3_bm_events_deliver_lifecycle(const bo3_lc_event *ev);    /* bm_events_service.c */
extern void bo3_bm_autopilot_lifecycle(uint32_t kind, uint32_t load_kind);  /* bm_autopilot.c (gp I4, v2) */

static const uint8_t *game_guest(void *user, uint32_t va, uint32_t size)
{
    (void)user;
    if (!g_xbox_mem_offset || va < 0x00010000u || va >= 0x04000000u || size > 0x04000000u - va)
        return NULL;
    return (const uint8_t *)((uintptr_t)g_xbox_mem_offset + va);
}

static void game_deliver(void *user, const bo3_lc_event *ev)
{
    (void)user;
    bo3_bm_autopilot_lifecycle(ev->kind, ev->load_kind);   /* the host's own service first: before any plugin sees it */
#if BO3_HOOKREQ_P23
    {
        extern void bo3_paints_svc_lifecycle(uint32_t kind);   /* main19 patch 31: bmashup.paints forgets the race's entity */
        bo3_paints_svc_lifecycle(ev->kind);
    }
#endif
    bo3_bm_events_deliver_lifecycle(ev);
#if BO3_HOOKREQ_P23
    {
        extern void bo3_rules_lifecycle(uint32_t kind);   /* main19 patch 35: bmashup.rules releases the race's claim */
        extern void bo3_ct_diag_lifecycle(uint32_t kind);         /* main21 patch 86: diagnostics summaries */
        extern void bo3_racers_diag_lifecycle(uint32_t kind);
        bo3_rules_lifecycle(ev->kind);
        bo3_ct_diag_lifecycle(ev->kind);
        bo3_racers_diag_lifecycle(ev->kind);
        {
            extern void bo3_zdiag_lifecycle(uint32_t kind);   /* main21 patch 107: DEV-only (empty in a default build) */
            bo3_zdiag_lifecycle(ev->kind);
        }
    }
#endif
}

void bo3_lc_game_init(void)
{
    bo3_lc_configure(&g_bo3_lc, game_guest, game_deliver, NULL, stderr);
}

/* bo3_lifecycle_gen.h */
void bo3_lc_gen_open(uint32_t world) { bo3_lc_open(&g_bo3_lc, world); }
void bo3_lc_gen_acquire(uint32_t buffer) { bo3_lc_acquire(&g_bo3_lc, buffer); }
void bo3_lc_gen_publish(uint32_t array, uint32_t lanes) { bo3_lc_publish(&g_bo3_lc, array, lanes); }
void bo3_lc_gen_loaded(void) { bo3_lc_loaded(&g_bo3_lc); }
#endif
