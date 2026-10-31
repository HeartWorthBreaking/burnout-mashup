/*
 * race_service.c - the "takedawn.race" service (include/takedawn_race.h):
 * what the race is doing, read from the game after each of its updates and
 * handed to plugins as a copy. Read only: nothing here writes the game.
 *
 * When: bo3_update (hirefresh.c, the host's CB3Game::Update, sub_000165F0)
 * calls bo3_race_after_update right after the title's update, on the game's
 * thread: the frame's simulation steps are done and no picture has been
 * drawn yet, so the car's matrix is the step's own (High refresh blends it
 * only at the pictures and puts it back before the next update).
 *
 * What, NTSC-U (the addresses the rest of the host uses; each where it was
 * found and checked):
 *   0x4D53B4  the game module's state: 5 running, 6 the module is being
 *             left, 0 before the game object exists, else a load or set-up
 *             (main.c texup_loading_flip; autopilot.c)
 *   0x4D5370  the current module: its vtable 0x3A9ACC is the game module's,
 *             + 0x1B8 its stage's mode object (0 in the front end)
 *             (autopilot.c ap_in_play; main.c texup_loading_flip)
 *   0x4D537C  the player who paused, -1 while not paused (autopilot.c)
 *   0x4A1EB4  the simulation step count, 60 a second (hirefresh.c)
 *   0x73A19C  the cars racing (autopilot.c, hirefresh.c)
 *   0x73A1D0  player 1's car (CB3PlayerCar, the race world 0x60EA00 +
 *             0x12B7D0): + 0x134C the event phase (0 / 1 before the GO, 2 in
 *             play, 3 finished), + 0x10D0 the place (int16), + 0x10DC the race
 *             time, + 0x10E4 the laps done, + 0x110C the best lap
 *             (autopilot.c, checked against a race's results screen), + 0x10
 *             its world matrix (an RwMatrix: the way it points at floats 8-10,
 *             its place at 12-14, in metres; hirefresh.c, rival-marker.md)
 * The car is a fixed object inside the race world; outside a stage its bytes
 * are stale, so nothing is read from it unless the game is in a stage.
 *
 * Speed is the car's move per step: |place - place at the last step| / steps
 * x 60, in metres a second (a car at 104 mph moves 0.77 units a step,
 * rival-marker.md). Not given before the second step in a stage, while
 * paused, after a jump (more than 3 units, 180 m/s, in a step: a reset after
 * a crash), or after more than 8 steps at once; between steps it holds.
 *
 * Threads: the snapshot is kept as words read and written one at a time
 * (relaxed atomics) behind a sequence count, so get() from any thread copies
 * a whole snapshot; the on_update calls are made on the game's thread, the
 * list copied under a spin lock first so a call may change it.
 */
#include "race_service.h"

#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "plugins.h"

extern ptrdiff_t g_xbox_mem_offset;

#define RS_M16(va) (*(const int16_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define RS_M32(va) (*(const uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define RS_MF(va)  (*(const float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

#define RS_STATE     0x004D53B4u
#define RS_MODULE    0x004D5370u
#define RS_VT_GAME   0x003A9ACCu
#define RS_STAGE     0x1B8u
#define RS_PAUSED_BY 0x004D537Cu
#define RS_STEP      0x004A1EB4u
#define RS_CARS      0x0073A19Cu
#define RS_CAR1      0x0073A1D0u
#define RS_PHASE     0x134Cu
#define RS_PLACE     0x10D0u
#define RS_TIME      0x10DCu
#define RS_LAPS      0x10E4u
#define RS_BEST      0x110Cu
#define RS_MATRIX    0x10u

#define RS_JUMP      3.0f              /* units a step: more is a reset, not driving */
#define RS_STEPS_MAX 8u
#define RS_CALLBACKS 64

_Static_assert(sizeof(td_race_snapshot) == 64, "td_race_snapshot is 64 bytes");
_Static_assert(sizeof(td_race_snapshot) % 4 == 0, "words");

#define RS_WORDS (sizeof(td_race_snapshot) / 4)

static _Atomic uint32_t s_seq;                     /* odd while written; 0: none yet */
static _Atomic uint32_t s_words[RS_WORDS];

static struct {
    int have;                                      /* a place at a step before */
    float pos[3];
    uint32_t step;
    int speed_ok;
    float speed;
} s_mv;

static struct cb {
    td_host *host;
    td_race_update_fn fn;
    void *user;
} s_cb[RS_CALLBACKS];
static int s_ncb;
static atomic_flag s_cb_lock = ATOMIC_FLAG_INIT;

static void cb_lock(void)
{
    while (atomic_flag_test_and_set_explicit(&s_cb_lock, memory_order_acquire))
        ;
}

static void cb_unlock(void)
{
    atomic_flag_clear_explicit(&s_cb_lock, memory_order_release);
}

static int ptr_ok(uint32_t va)
{
    return va >= 0x10000u && va < 0x04000000u;
}

static int finite3(const float *v)
{
    return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

/* Speed from the car's place at this step and the last (see the top). */
static void speed(td_race_snapshot *s, int moving)
{
    uint32_t d;
    if (!moving) {
        s_mv.speed_ok = 0;
        s_mv.have = 0;
        return;
    }
    d = s->step - s_mv.step;
    if (s_mv.have && d == 0) {
        /* no step since: the last one holds */
    } else if (s_mv.have && d <= RS_STEPS_MAX) {
        float dx = s->position[0] - s_mv.pos[0], dy = s->position[1] - s_mv.pos[1], dz = s->position[2] - s_mv.pos[2];
        float per = sqrtf(dx * dx + dy * dy + dz * dz) / (float)d;
        s_mv.speed_ok = per <= RS_JUMP;
        s_mv.speed = s_mv.speed_ok ? per * 60.0f : 0.0f;
    } else {
        s_mv.speed_ok = 0;
    }
    if (!s_mv.have || d != 0) {
        memcpy(s_mv.pos, s->position, sizeof s_mv.pos);
        s_mv.step = s->step;
        s_mv.have = 1;
    }
    if (s_mv.speed_ok) {
        s->speed_mps = s_mv.speed;
        s->valid |= TD_RACE_HAVE_SPEED;
    }
}

static void build(td_race_snapshot *s)
{
    uint32_t st, mod, phase;
    int paused;
    const float *m;

    memset(s, 0, sizeof *s);
    s->struct_size = (uint32_t)sizeof *s;
    if (!g_xbox_mem_offset) {
        speed(s, 0);
        return;                                    /* TD_RACE_NONE */
    }
    st = RS_M32(RS_STATE);
    s->step = RS_M32(RS_STEP);
    mod = RS_M32(RS_MODULE);
    if (st == 0)
        s->state = TD_RACE_NONE;
    else if (st == 6)
        s->state = TD_RACE_LEAVING;
    else if (st != 5)
        s->state = TD_RACE_LOADING;
    else if (!ptr_ok(mod) || RS_M32(mod) != RS_VT_GAME || !RS_M32(mod + RS_STAGE))
        s->state = TD_RACE_FRONTEND;
    else {
        phase = RS_M32(RS_CAR1 + RS_PHASE);
        paused = RS_M32(RS_PAUSED_BY) != 0xFFFFFFFFu;
        if (phase > 3)
            s->state = TD_RACE_LOADING;            /* not a phase this knows: nothing read */
        else if (paused && phase <= 2)
            s->state = TD_RACE_PAUSED;
        else
            s->state = phase < 2 ? TD_RACE_PRESTART : phase == 2 ? TD_RACE_RACING : TD_RACE_FINISHED;
    }
    if (s->state >= TD_RACE_PRESTART && s->state <= TD_RACE_FINISHED) {
        m = &RS_MF(RS_CAR1 + RS_MATRIX);
        s->position[0] = m[12];
        s->position[1] = m[13];
        s->position[2] = m[14];
        s->forward[0] = m[8];
        s->forward[1] = m[9];
        s->forward[2] = m[10];
        if (finite3(s->position) && finite3(s->forward)) {
            float n = sqrtf(s->forward[0] * s->forward[0] + s->forward[1] * s->forward[1] + s->forward[2] * s->forward[2]);
            uint32_t cars = RS_M32(RS_CARS);
            if (n > 1e-6f) {
                s->forward[0] /= n;
                s->forward[1] /= n;
                s->forward[2] /= n;
            } else {
                memset(s->forward, 0, sizeof s->forward);
            }
            s->cars = cars <= 64 ? cars : 0;
            s->place = RS_M16(RS_CAR1 + RS_PLACE);
            s->lap = RS_M32(RS_CAR1 + RS_LAPS);
            s->race_time_s = isfinite(RS_MF(RS_CAR1 + RS_TIME)) ? RS_MF(RS_CAR1 + RS_TIME) : 0.0f;
            s->best_lap_s = isfinite(RS_MF(RS_CAR1 + RS_BEST)) ? RS_MF(RS_CAR1 + RS_BEST) : 0.0f;
            s->valid |= TD_RACE_HAVE_CAR;
        } else {
            memset(s->position, 0, sizeof s->position);
            memset(s->forward, 0, sizeof s->forward);
        }
    }
    speed(s, (s->valid & TD_RACE_HAVE_CAR) && s->state != TD_RACE_PAUSED);
}

static void publish(const td_race_snapshot *s)
{
    uint32_t w[RS_WORDS], q = atomic_load_explicit(&s_seq, memory_order_relaxed);
    memcpy(w, s, sizeof w);
    atomic_store_explicit(&s_seq, q + 1, memory_order_relaxed);   /* odd: being written */
    atomic_thread_fence(memory_order_release);
    for (size_t k = 0; k < RS_WORDS; k++)
        atomic_store_explicit(&s_words[k], w[k], memory_order_relaxed);
    atomic_store_explicit(&s_seq, q + 2, memory_order_release);
}

static int32_t TD_CALL race_get(td_host *host, td_race_snapshot *out)
{
    uint32_t w[RS_WORDS], a, b, room;
    if (!host || !out || out->struct_size < 8)
        return TD_RACE_BAD_ARG;
    do {
        a = atomic_load_explicit(&s_seq, memory_order_acquire);
        for (size_t k = 0; k < RS_WORDS; k++)
            w[k] = atomic_load_explicit(&s_words[k], memory_order_relaxed);
        atomic_thread_fence(memory_order_acquire);
        b = atomic_load_explicit(&s_seq, memory_order_relaxed);
    } while ((a & 1u) || a != b);
    if (!a)
        return TD_RACE_UNAVAILABLE;
    room = out->struct_size < sizeof w ? out->struct_size : (uint32_t)sizeof w;
    memcpy(out, w, room);
    out->struct_size = room;
    return TD_RACE_OK;
}

static int32_t TD_CALL race_on_update(td_host *host, td_race_update_fn fn, void *user)
{
    int k, rc = TD_RACE_OK;
    if (!host)
        return TD_RACE_BAD_ARG;
    cb_lock();
    for (k = 0; k < s_ncb && s_cb[k].host != host; k++)
        ;
    if (!fn) {
        if (k < s_ncb)
            s_cb[k] = s_cb[--s_ncb];
    } else if (k == s_ncb && s_ncb == RS_CALLBACKS) {
        rc = TD_RACE_BAD_ARG;
    } else {
        s_cb[k].host = host;
        s_cb[k].fn = fn;
        s_cb[k].user = user;
        if (k == s_ncb)
            s_ncb++;
    }
    cb_unlock();
    return rc;
}

static const td_race_api s_api = {
    (uint32_t)sizeof(td_race_api), TD_RACE_VERSION, race_get, race_on_update
};

const td_race_api *bo3_race_api(void)
{
    return &s_api;
}

void bo3_race_init(void)
{
    bo3_plugins_service(TD_RACE_SERVICE, TD_RACE_VERSION, &s_api);
}

void bo3_race_after_update(void)
{
    td_race_snapshot s;
    struct cb list[RS_CALLBACKS];
    int n;
    { extern void bo3_lanes_after_update(void); bo3_lanes_after_update(); }   /* LANELIFE-C: the LOADED-time diagnostic (bm_lanes.c) */

    build(&s);
    publish(&s);
    cb_lock();
    n = s_ncb;
    memcpy(list, s_cb, (size_t)n * sizeof list[0]);
    cb_unlock();
    for (int k = 0; k < n; k++)
        list[k].fn(&s, list[k].user);
}
