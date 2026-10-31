/*
 * bm_events.c - the engine-point dispatcher (bm_events.h). The toolkit runs
 * only the first handler registered for a mark (recomp_patch.c), so the
 * dispatcher is that handler: a fixed trampoline per owned mark calls the
 * mark's list in order. Lists are written only while registration is open
 * (the single-threaded start) and read by the game's thread afterwards, so
 * the dispatch itself takes no lock; the counters are atomics, read from any
 * thread.
 */
#include "bm_events.h"

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "platform/recomp_patch.h"
#include "recomp_types.h"

typedef struct {
    void (*fn)(void *user);
    void *user;
    const char *who;
    int kind;
    _Atomic uint32_t calls;
    _Atomic uint32_t faults;
} sub_t;

static struct {
    const char *name;
    sub_t sub[BO3_EVENTS_SUBSCRIBERS];  /* in call order: observers, then writers */
    int nsub, nobs;
    int depth;                          /* game thread only */
    _Atomic uint32_t dispatched, reentered, after_stop;
} s_mark[BO3_EVENTS_MARKS];
static int s_nmark;
static int s_closed;
static _Atomic int s_stopped;
static int s_atexit;

/* The guest's register state as a subscriber must leave it. */
typedef struct {
    uint32_t eax, ebx, ecx, edx, esi, edi, ebp, esp;
    RecompXmm x[8];
    int top;
} regs_t;

static void save(regs_t *r)
{
    r->eax = g_eax; r->ebx = g_ebx; r->ecx = g_ecx; r->edx = g_edx;
    r->esi = g_esi; r->edi = g_edi; r->ebp = g_ebp; r->esp = g_esp;
    r->x[0] = g_xmm0; r->x[1] = g_xmm1; r->x[2] = g_xmm2; r->x[3] = g_xmm3;
    r->x[4] = g_xmm4; r->x[5] = g_xmm5; r->x[6] = g_xmm6; r->x[7] = g_xmm7;
    r->top = g_fp_top;
}

static int same(const regs_t *a, const regs_t *b)
{
    return a->eax == b->eax && a->ebx == b->ebx && a->ecx == b->ecx && a->edx == b->edx && a->esi == b->esi
        && a->edi == b->edi && a->ebp == b->ebp && a->esp == b->esp && a->top == b->top
        && !memcmp(a->x, b->x, sizeof a->x);
}

static void restore(const regs_t *r)
{
    g_eax = r->eax; g_ebx = r->ebx; g_ecx = r->ecx; g_edx = r->edx;
    g_esi = r->esi; g_edi = r->edi; g_ebp = r->ebp; g_esp = r->esp;
    g_xmm0 = r->x[0]; g_xmm1 = r->x[1]; g_xmm2 = r->x[2]; g_xmm3 = r->x[3];
    g_xmm4 = r->x[4]; g_xmm5 = r->x[5]; g_xmm6 = r->x[6]; g_xmm7 = r->x[7];
    g_fp_top = r->top;
}

static void dispatch(int id)
{
    regs_t before, after;
    if (atomic_load(&s_stopped)) {
        atomic_fetch_add(&s_mark[id].after_stop, 1);
        return;
    }
    if (s_mark[id].depth) {
        atomic_fetch_add(&s_mark[id].reentered, 1);
        return;
    }
    s_mark[id].depth = 1;
    atomic_fetch_add(&s_mark[id].dispatched, 1);
    for (int k = 0; k < s_mark[id].nsub; k++) {
        sub_t *s = &s_mark[id].sub[k];
        save(&before);
        s->fn(s->user);
        atomic_fetch_add(&s->calls, 1);
        save(&after);
        if (!same(&before, &after)) {
            /* Put back for everyone. A writer may call a game routine that
             * uses volatile registers (xmm, eax ...) and is only counted; an
             * observer has no business with guest state: said once. */
            restore(&before);
            if (atomic_fetch_add(&s->faults, 1) == 0 && s->kind == BO3_EVENT_OBSERVER)
                fprintf(stderr, "[AUTOPILOT] events: %s at mark %s changed a guest register; put back "
                                "(said once)\n", s->who ? s->who : "?", s_mark[id].name);
        }
    }
    s_mark[id].depth = 0;
}

/* One trampoline a mark: the toolkit's handlers take no argument. */
static void t0(void) { dispatch(0); }
static void t1(void) { dispatch(1); }
static void t2(void) { dispatch(2); }
static void t3(void) { dispatch(3); }
static void (*const s_tramp[BO3_EVENTS_MARKS])(void) = { t0, t1, t2, t3 };
_Static_assert(BO3_EVENTS_MARKS == 4, "one trampoline a mark");

int bo3_events_hook(const char *name)
{
    int k;
    if (!name || s_closed)
        return -1;
    for (k = 0; k < s_nmark; k++)
        if (!strcmp(s_mark[k].name, name))
            return k;
    if (s_nmark == BO3_EVENTS_MARKS)
        return -1;
    s_mark[s_nmark].name = name;
    recomp_patch_on_mark(name, s_tramp[s_nmark]);
    return s_nmark++;
}

int bo3_events_subscribe(int id, int kind, void (*fn)(void *user), void *user, const char *who)
{
    sub_t *s;
    int at;
    if (s_closed || id < 0 || id >= s_nmark || !fn || (kind != BO3_EVENT_OBSERVER && kind != BO3_EVENT_WRITER)
            || s_mark[id].nsub == BO3_EVENTS_SUBSCRIBERS)
        return -1;
    /* observers before writers, each in registration order */
    at = kind == BO3_EVENT_OBSERVER ? s_mark[id].nobs : s_mark[id].nsub;
    memmove(&s_mark[id].sub[at + 1], &s_mark[id].sub[at], (size_t)(s_mark[id].nsub - at) * sizeof(sub_t));
    s = &s_mark[id].sub[at];
    memset(s, 0, sizeof *s);
    s->fn = fn;
    s->user = user;
    s->who = who;
    s->kind = kind;
    s_mark[id].nsub++;
    if (kind == BO3_EVENT_OBSERVER)
        s_mark[id].nobs++;
    return 0;
}

void bo3_events_stop(void)
{
    atomic_store(&s_stopped, 1);
}

static void stop_at_exit(void)
{
    bo3_events_stop();
}

void bo3_events_close(void)
{
    s_closed = 1;
    if (!s_atexit) {
        s_atexit = 1;
        atexit(stop_at_exit);
    }
}

int bo3_events_open(void)
{
    return !s_closed;
}

void bo3_events_mark_counts(int id, bo3_events_counts *out)
{
    if (!out)
        return;
    memset(out, 0, sizeof *out);
    if (id < 0 || id >= s_nmark)
        return;
    out->dispatched = atomic_load(&s_mark[id].dispatched);
    out->reentered = atomic_load(&s_mark[id].reentered);
    out->after_stop = atomic_load(&s_mark[id].after_stop);
}

static sub_t *at(int id, int pos)
{
    if (id < 0 || id >= s_nmark || pos < 0 || pos >= s_mark[id].nsub)
        return NULL;
    return &s_mark[id].sub[pos];
}

uint32_t bo3_events_calls(int id, int pos)
{
    sub_t *s = at(id, pos);
    return s ? atomic_load(&s->calls) : 0;
}

uint32_t bo3_events_faults(int id, int pos)
{
    sub_t *s = at(id, pos);
    return s ? atomic_load(&s->faults) : 0;
}

void *bo3_events_user_at(int id, int pos)
{
    sub_t *s = at(id, pos);
    return s ? s->user : NULL;
}

void bo3_events_reset_for_test(void)
{
    for (int k = 0; k < s_nmark; k++) {
        s_mark[k].nsub = s_mark[k].nobs = s_mark[k].depth = 0;
        atomic_store(&s_mark[k].dispatched, 0);
        atomic_store(&s_mark[k].reentered, 0);
        atomic_store(&s_mark[k].after_stop, 0);
    }
    s_nmark = 0;
    s_closed = 0;
    atomic_store(&s_stopped, 0);
}
