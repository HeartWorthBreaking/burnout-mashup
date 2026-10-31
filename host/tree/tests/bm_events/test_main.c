/* tests/bm_events - the engine-point dispatcher (src/game/bm_events.c) and
 * Burnout Mashup's private "bmashup.events" service over it
 * (bm_events_service.c), with the real bmashup.autopilot / bmashup.boost as
 * its writers (bm_autopilot.c, bm_boost.c, ai_takeover.c, race_service.c),
 * against a stand-in for the game's memory. The toolkit's mark table is played
 * here (one handler per name, the first wins, as recomp_patch.c), so a mark
 * "runs" by calling the handler the dispatcher registered. No game data. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bm_autopilot.h"
#include "bm_boost.h"
#include "bm_events.h"
#include "bm_events_service.h"
#include "race_service.h"
#include "recomp_types.h"

ptrdiff_t g_xbox_mem_offset;
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp;
RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top;

#define GMEM 0x00800000u
static uint8_t *s_mem;
#define M8(va)  (*(uint8_t *)(s_mem + (uint32_t)(va)))
#define M32(va) (*(uint32_t *)(s_mem + (uint32_t)(va)))
#define MF(va)  (*(float *)(s_mem + (uint32_t)(va)))

#define STATE    0x004D53B4u
#define MODULE   0x004D5370u
#define MODOBJ   0x00200000u
#define VT_GAME  0x003A9ACCu
#define PAUSED   0x004D537Cu
#define STEP     0x004A1EB4u
#define CARS     0x0073A19Cu
#define CAR      0x0073A1D0u
#define CAR2     0x0073C9B0u
#define VT_CAR   0x003B11A0u
#define PLAYER   0x27D0u
#define PHASE    0x134Cu
#define AI       0x27D8u
#define TIME     0x10DCu
#define STACK    0x00100000u

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

/* plugins.c's, played here */
static const void *s_ev_table;
static const char *s_ev_name;
static uint32_t s_ev_version;
int bo3_plugins_service(const char *name, uint32_t version, const void *table)
{
    if (!strcmp(name, "bmashup.events")) {
        s_ev_name = name;
        s_ev_version = version;
        s_ev_table = table;
    }
    return 1;
}

/* recomp_patch.c's mark table, played here: the first handler of a name wins */
static struct { const char *name; void (*fn)(void); } s_marks[16];
static int s_nmarks;
void recomp_patch_on_mark(const char *name, void (*fn)(void))
{
    for (int k = 0; k < s_nmarks; k++)
        if (!strcmp(s_marks[k].name, name))
            return;
    s_marks[s_nmarks].name = name;
    s_marks[s_nmarks].fn = fn;
    s_nmarks++;
}
static void run_mark(const char *name)
{
    for (int k = 0; k < s_nmarks; k++)
        if (!strcmp(s_marks[k].name, name)) {
            s_marks[k].fn();
            return;
        }
}

/* the title's routines the writers call, played here */
static int s_takeovers, s_boosts;
void sub_00179760(void)
{
    s_takeovers++;
    g_esp += 4;
}
void sub_0017A530(void)
{
    s_boosts++;
    g_esp += 8;
}

/* ---- subscribers of the core's own marks ---- */
static char s_order[64];
static int s_norder;
static void rec(void *user) { s_order[s_norder++] = *(const char *)user; }
static void reenter_core(void *user) { (void)user; s_order[s_norder++] = 'R'; run_mark("t.core"); }
static void clobber_obs(void *user) { (void)user; g_ebx = 0xBAD; g_xmm1.f[0] = 9.0f; }
static void clobber_wr(void *user) { (void)user; g_eax = 0xBAD; g_fp_top = (g_fp_top + 1) & 7; }
static uint32_t s_seen_ebx, s_seen_eax;
static void see(void *user) { (void)user; s_seen_ebx = g_ebx; s_seen_eax = g_eax; }

/* ---- plugins of the service ---- */
static int s_plug_a, s_plug_b, s_plug_bad, s_plug_late, s_plug_race;
#define HOST(p) ((td_host *)(void *)&(p))
static const bm_events_api *s_api;
static struct got { int n; uint32_t seq, step, phase; float t; uint8_t ai_seen; } s_got_a, s_got_b;
static void TD_CALL plug_rec(const bm_event *ev, void *user)
{
    struct got *g = (struct got *)user;
    g->n++;
    g->seq = ev->sequence;
    g->step = ev->step;
    g->t = ev->race_time_s;
    g->phase = ev->car_phase;
    g->ai_seen = M8(CAR + AI);
}
static int s_bad_calls;
static void TD_CALL plug_bad(const bm_event *ev, void *user)
{
    (void)ev;
    (void)user;
    s_bad_calls++;
    g_esi = 0x1234;                                 /* an observer that breaks the rules */
    g_esp -= 64;
}
static void TD_CALL plug_none(const bm_event *ev, void *user) { (void)ev; (void)user; }

static void sig(void)
{
    M32(0x003B11A0u) = 0x0018C470u;
    M32(0x003B11A4u) = 0x0018C510u;
    M32(0x003A9ACCu) = 0x00019FE0u;
    M32(0x003A9AD0u) = 0x0001A000u;
}
static void game(uint32_t phase)
{
    M32(STATE) = 5;
    M32(MODULE) = MODOBJ;
    M32(MODOBJ) = VT_GAME;
    M32(MODOBJ + 0x1B8u) = 0x00300000u;
    M32(PAUSED) = 0xFFFFFFFFu;
    M32(CAR) = VT_CAR;
    M32(CAR + PLAYER) = 0;
    M32(CAR + PHASE) = phase;
    M32(CARS) = 6;
    MF(CAR + 0x10u + 15 * 4) = 1.0f;
}

/* one game update: the car updates (player 2's, then player 1's), then the
 * snapshot and its on_update calls (where a plugin asks a service), then the
 * services' after-updates */
static int s_want_ap;
static int32_t s_ap_rc = -1;
static void TD_CALL on_update(const td_race_snapshot *snap, void *user)
{
    (void)snap;
    (void)user;
    if (s_want_ap) {
        s_want_ap = 0;
        s_ap_rc = bo3_bm_autopilot_api()->engage(HOST(s_plug_race));
    }
}
static void tick(int car)
{
    M32(STEP) += 1;
    if (car) {
        g_esi = CAR2;
        run_mark("ap_update");
        g_esi = CAR;
        run_mark("ap_update");
    }
    bo3_race_after_update();
    bo3_bm_autopilot_after_update();
    bo3_bm_boost_after_update();
}

int main(void)
{
    static const char a = 'a', b = 'b', c = 'c', d = 'd';
    bo3_events_counts cnt;
    bm_events_stats st;
    int core, m, ok;

    setvbuf(stdout, NULL, _IONBF, 0);
    s_mem = calloc(1, GMEM);
    if (!s_mem)
        return 2;
    g_xbox_mem_offset = (ptrdiff_t)s_mem;
    g_esp = STACK;
    sig();

    /* ---- the core, on marks of its own ---- */
    core = bo3_events_hook("t.core");
    CHECK(core == 0 && bo3_events_hook("t.core") == core && s_nmarks == 1, "a mark hooked once; the same name, the same id");
    CHECK(bo3_events_hook("t.m1") == 1 && bo3_events_hook("t.m2") == 2 && bo3_events_hook("t.m3") == 3
          && bo3_events_hook("t.m4") == -1 && bo3_events_hook(NULL) == -1, "four marks at most; no name refused");
    CHECK(bo3_events_subscribe(core, BO3_EVENT_WRITER, rec, (void *)&a, "w-a") == 0
          && bo3_events_subscribe(core, BO3_EVENT_OBSERVER, rec, (void *)&b, "o-b") == 0
          && bo3_events_subscribe(core, BO3_EVENT_WRITER, rec, (void *)&c, "w-c") == 0
          && bo3_events_subscribe(core, BO3_EVENT_OBSERVER, rec, (void *)&d, "o-d") == 0, "four subscribers");
    CHECK(bo3_events_subscribe(core, 7, rec, NULL, "x") == -1 && bo3_events_subscribe(core, BO3_EVENT_WRITER, NULL, NULL, "x") == -1
          && bo3_events_subscribe(9, BO3_EVENT_WRITER, rec, NULL, "x") == -1, "a bad kind, no fn, a bad id: refused");
    s_norder = 0;
    run_mark("t.core");
    CHECK(s_norder == 4 && !memcmp(s_order, "bdac", 4), "the order: observers first, then writers, each by registration (%.*s)",
          s_norder, s_order);
    run_mark("t.core");
    bo3_events_mark_counts(core, &cnt);
    CHECK(cnt.dispatched == 2 && bo3_events_calls(core, 0) == 2 && bo3_events_calls(core, 3) == 2, "each once a dispatch, counted");

    /* another mark reached from inside a dispatch runs; the same one does not */
    bo3_events_subscribe(1, BO3_EVENT_OBSERVER, reenter_core, NULL, "m1-to-core");
    s_norder = 0;
    run_mark("t.m1");
    bo3_events_mark_counts(1, &cnt);
    CHECK(s_norder == 5 && cnt.dispatched == 1, "another mark from inside a dispatch runs its own list (%d)", s_norder);
    bo3_events_subscribe(core, BO3_EVENT_WRITER, reenter_core, NULL, "core-to-core");
    s_norder = 0;
    run_mark("t.core");
    bo3_events_mark_counts(core, &cnt);
    CHECK(cnt.reentered == 1 && s_norder == 5, "a mark reached from inside its own dispatch: not run again (%u, %d)",
          cnt.reentered, s_norder);

    /* register state */
    bo3_events_subscribe(2, BO3_EVENT_OBSERVER, rec, (void *)&a, "m2-rec");
    bo3_events_subscribe(2, BO3_EVENT_OBSERVER, clobber_obs, NULL, "clobber-obs");
    bo3_events_subscribe(2, BO3_EVENT_WRITER, clobber_wr, NULL, "clobber-wr");
    bo3_events_subscribe(2, BO3_EVENT_WRITER, see, NULL, "see");
    g_ebx = 0x55;
    g_eax = 0x66;
    g_xmm1.f[0] = 1.5f;
    g_fp_top = 3;
    run_mark("t.m2");
    CHECK(g_ebx == 0x55 && g_eax == 0x66 && g_xmm1.f[0] == 1.5f && g_fp_top == 3 && s_seen_ebx == 0x55 && s_seen_eax == 0x66,
          "a subscriber's register changes are put back before the next one runs, and at the end");
    CHECK(bo3_events_faults(2, 0) == 0 && bo3_events_faults(2, 1) == 1 && bo3_events_faults(2, 2) == 1 && bo3_events_faults(2, 3) == 0,
          "and counted for the subscriber that made them (observer and writer), no one else");

    /* capacity */
    ok = 1;
    for (int k = 0; k < BO3_EVENTS_SUBSCRIBERS; k++)
        ok &= bo3_events_subscribe(3, BO3_EVENT_OBSERVER, rec, (void *)&c, "fill") == 0;
    CHECK(ok && bo3_events_subscribe(3, BO3_EVENT_OBSERVER, rec, (void *)&c, "over") == -1, "24 subscribers a mark: the 25th refused");

    /* closed, then stopped */
    bo3_events_close();
    CHECK(!bo3_events_open() && bo3_events_subscribe(2, BO3_EVENT_OBSERVER, rec, (void *)&a, "late") == -1
          && bo3_events_hook("t.late") == -1, "closed: no subscriber, no mark");
    s_norder = 0;
    run_mark("t.core");
    CHECK(s_norder == 5, "closed: the lists still run");
    bo3_events_stop();
    s_norder = 0;
    run_mark("t.core");
    bo3_events_mark_counts(core, &cnt);
    CHECK(s_norder == 0 && cnt.after_stop == 1, "after the stop: nothing called, counted");

    /* ---- the service, on the real car-update mark ---- */
    bo3_events_reset_for_test();
    s_api = bo3_bm_events_api();
    bo3_race_init();
    bo3_bm_autopilot_init(1);                       /* RECOMP_DEBUG=autopilot: the point is not hooked */
    bo3_bm_boost_init(1);
    bo3_bm_events_init();
    CHECK(s_ev_name && !strcmp(s_ev_name, "bmashup.events") && s_ev_version == 1 && s_ev_table == s_api
          && s_api->struct_size == sizeof(bm_events_api) && s_api->subscribe && s_api->stats
          && sizeof(bm_event) == 24 && sizeof(bm_events_stats) == 16, "offered as bmashup.events 1; the sizes");
    CHECK(s_api->subscribe(HOST(s_plug_a), BM_EVENT_PLAYER_CAR_UPDATE, plug_rec, &s_got_a) == BM_EVENTS_UNAVAILABLE,
          "debug autopilot on: the point is not hooked, unavailable");
    bo3_bm_autopilot_init(0);
    bo3_bm_boost_init(0);
    m = bo3_bm_car_update_mark();
    CHECK(m >= 0 && !bo3_events_user_at(m, 0) && !bo3_events_user_at(m, 1) && !bo3_events_user_at(m, 2),
          "the car update hooked, with its two writers");
    CHECK(s_api->subscribe(NULL, 1, plug_rec, NULL) == BM_EVENTS_BAD_ARG && s_api->subscribe(HOST(s_plug_a), 1, NULL, NULL) == BM_EVENTS_BAD_ARG
          && s_api->subscribe(HOST(s_plug_a), 2, plug_rec, NULL) == BM_EVENTS_UNKNOWN_EVENT, "bad arguments; an unknown event");
    CHECK(s_api->subscribe(HOST(s_plug_a), BM_EVENT_PLAYER_CAR_UPDATE, plug_rec, &s_got_a) == BM_EVENTS_OK
          && s_api->subscribe(HOST(s_plug_b), BM_EVENT_PLAYER_CAR_UPDATE, plug_rec, &s_got_b) == BM_EVENTS_OK
          && s_api->subscribe(HOST(s_plug_bad), BM_EVENT_PLAYER_CAR_UPDATE, plug_bad, NULL) == BM_EVENTS_OK,
          "three plugins subscribe to the same event");
    CHECK(s_api->subscribe(HOST(s_plug_a), BM_EVENT_PLAYER_CAR_UPDATE, plug_rec, &s_got_a) == BM_EVENTS_ALREADY,
          "the same plugin again: already");
    CHECK(bo3_events_user_at(m, 0) && bo3_events_user_at(m, 1) && bo3_events_user_at(m, 2) && !bo3_events_user_at(m, 3)
          && !bo3_events_user_at(m, 4), "the order at the point: the plugins first, then the two writers");
    bo3_events_close();
    CHECK(s_api->subscribe(HOST(s_plug_late), BM_EVENT_PLAYER_CAR_UPDATE, plug_none, NULL) == BM_EVENTS_CLOSED,
          "after the plugins' start: closed");

    /* each plugin sees each player-1 car update once, with the same copy */
    game(2);
    M32(STEP) = 500;
    MF(CAR + TIME) = 12.5f;
    tick(1);
    CHECK(s_got_a.n == 1 && s_got_b.n == 1 && s_bad_calls == 1 && s_got_a.seq == s_got_b.seq && s_got_a.step == 501
          && s_got_b.step == 501 && s_got_a.t == 12.5f && s_got_a.phase == 2,
          "one event each for player 1's car update; the same sequence, step, time, phase");
    bo3_events_mark_counts(m, &cnt);
    CHECK(cnt.dispatched == 2, "player 2's update reached the point too (2 occurrences) but was not delivered");
    for (int k = 0; k < 99; k++)
        tick(1);
    st.struct_size = (uint32_t)sizeof st;
    CHECK(s_api->stats(HOST(s_plug_a), 1, &st) == BM_EVENTS_OK && st.delivered == 100 && st.occurrences == 200
          && st.register_faults == 0 && s_got_b.n == 100, "100 updates: 100 events each, 200 occurrences, no faults");
    st.struct_size = (uint32_t)sizeof st;
    CHECK(s_api->stats(HOST(s_plug_bad), 1, &st) == BM_EVENTS_OK && st.register_faults == 100 && g_esi == CAR && g_esp == STACK,
          "the rule-breaking observer: every change put back and counted (%u)", st.register_faults);
    st.struct_size = 4;
    CHECK(s_api->stats(HOST(s_plug_a), 1, &st) == BM_EVENTS_BAD_ARG && s_api->stats(NULL, 1, &st) == BM_EVENTS_BAD_ARG,
          "stats: bad arguments");

    /* observers run before the writers: in the takeover's car update they still
     * see the byte at 0, and the writer works although an observer broke the rules */
    bo3_race_api()->on_update(HOST(s_plug_race), on_update, NULL);
    M8(CAR + AI) = 0;
    s_want_ap = 1;
    tick(0);
    CHECK(s_ap_rc == BM_AP_OK, "an autopilot request staged");
    g_esp = STACK;
    tick(1);
    CHECK(s_takeovers == 1 && s_got_a.ai_seen == 0 && M8(CAR + AI) == 1 && g_esp == STACK,
          "in the takeover's car update the observers saw the byte at 0; the writer set it after them, on the right car");

    /* stop: nothing delivered any more */
    {
        int na = s_got_a.n, nb = s_got_b.n;
        bo3_events_stop();
        tick(1);
        CHECK(s_got_a.n == na && s_got_b.n == nb, "after the stop: no events");
    }
    CHECK(s_boosts == 0, "no top-up was asked: the boost writer called nothing (%d)", s_boosts);
    printf("bm_events: %d passed, %d failed\n", s_pass, s_fail);
    free(s_mem);
    return s_fail ? 1 : 0;
}
