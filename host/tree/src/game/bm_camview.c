/*
 * bm_camview.c - main19 (hook request P2 / P3; IMPLEMENTATION_PLAN patch 28 camera_v2_adjust, FEASIBILITY C1): bmashup.camera
 * version 2's chase-camera ADJUST and bmashup.hooks v3 point 9 CAMERA_FINAL, over ONE mark in sub_001C8A60 (bo3_camview_gen.h):
 * the picture's view build. sub_00013E50 builds the picture's camera matrix from the game camera (view + 0x68, + 0x20) into a
 * stack COPY; sub_001C8A60 then copies it into the camera frame (view + 0x58 -> RwCamera, + 4 -> frame, + 0x10 the modelling
 * matrix), and the view matrix (sub_001C8870) and the frustum are made from that frame. The adjust is written into the COPY
 * only: the game's camera object is never written, the next picture starts again from the game's own camera (no drift, no
 * put-back), and the frame, the view matrix, the frustum and the high-refresh blend all see the same adjusted matrix.
 * Sites: SITES_VERIFIED s4 (the site; X-5: downstream of the low-speed overwrite) + tests\p23\STEP0_B.md.
 *
 * When: player 0's race view only (view == 0x4D6200, the race's view object), a one-player stage (bmashup.camera's stage
 * state: never the front end, never split screen), not while player 1's crash camera byte is set, and only while the camera
 * dispatch's active set (PC 0x4CFB20: 64-bit mask at + 0xC20 / + 0xC24, sub_00167940) is exactly the follow camera's bit.
 * WHICH bit that is: probe PR-A2 (item 40): driving = bit 2 only (slot PC + 0x2A0 + 8 = 0x4CFE90, vtable 0x3A9C28, the follow
 * update table); crash = bit 6 (+ the crash byte), alternative views 4 / 5, intro 18 / 19, pre-race 10, outro 8 -> chase_active =
 * (active set == 0x4) (BM_P23_CAMERA_FOLLOW_BIT 2). The picture's matrix copy lives on the guest stack: the main stack
 * (XBOX_STACK_BASE) and the threads' stacks (xbox_AllocThreadStack = the guest heap) are both inside main RAM, the window
 * bo3_guest_read / _write accept (xbox_memory_layout.h / .c; checked offline, item 40).
 *
 * The level: the owner's set_adjust (smoothed per picture by smoothing_s), then CAMERA_FINAL modifiers (bm_hooks.c bounds).
 * Matrix rows (RwMatrix order): right, up, at, pos. Rotation in the camera frame: roll about at (right toward up), pitch about
 * right (up toward at), yaw about up (at toward right); the offset is along the rotated camera axes.
 * BO3_HOOKREQ_P23 == 0: the mark is not in the generated code; the ops are not registered (bmashup.camera v2 calls
 * UNAVAILABLE).
 *
 * Item 29 + item 40 (FEASIBILITY C2, probe PR-D: REDUCED form): FINISH POSE + bmashup.hooks v3 point 13 FINISH_CAMERA on the
 * same copy, while the camera dispatch's active set is exactly the end-of-race camera's bit (PR-D: bit 8, slot 0x4D0680 vtable
 * 0x3A9AB8; BM_P23_CAMERA_FINISH_BIT 8). PR-D found ONE STATIC game camera pose for the whole outro (dispatch output PC + 0x250:
 * position + 0x30 = PC + 0x280, per track) and the car NOT frozen (the AI drives on): the anchor is therefore the game's own outro
 * camera - the picture's matrix copy taken at the outro's first picture (= the PC + 0x280 pose) - not the car. One authored pose
 * a race (n <= BM_CAMERA_FINISH_POSES_SERVED = 1, relative to that camera: x right, y up, z forward) replaces the game's pose
 * for the whole outro (hold_s is validated, not used); then the game's camera again at the next race. A pose's field-of-view
 * scale reaches the game through the second mark (BO3_CAM_FOV_SCALE, the angle before its tangent). The distance bound
 * BM_CAMERA_FINISH_RADIUS_M (40 m: the measured camera-to-car distance at the finish, 37.6 / 42.2 m, keeps the finish area
 * streamed) holds for the host's pose and for every FINISH_CAMERA proposal (the item's check). The pose is cleared when the
 * race's stage ends.
 * MUT=n (tests only): 221 set_adjust bounds unchecked, 222 applied while the crash camera byte is set, 223 applied with another
 * camera bit active too, 224 the game's camera object written instead of the copy, 225 ownership not enforced, 226 applied
 * outside a one-player stage, 227 the census skipped; item 29: 228 a pose beyond the radius accepted (host poses and
 * FINISH_CAMERA proposals), 229 the poses not cleared at the stage's end, 230 the fov scale left in force after the picture.
 */
#include "bm_camera.h"

#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "bm_guest.h"
#include "bm_hooks.h"
#include "bo3_camview_gen.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

/* PR-A: the camera dispatch bit (0..63) of the follow (chase) camera; -1 = not known -> the adjust is UNAVAILABLE. */
#ifndef BM_P23_CAMERA_FOLLOW_BIT
#define BM_P23_CAMERA_FOLLOW_BIT 2      /* item 40: PR-A2 (chase = bit 2 only) */
#endif

/* PR-D: the camera dispatch bit of player 0's end-of-race camera; -1 = not known -> the finish poses are UNAVAILABLE. */
#ifndef BM_P23_CAMERA_FINISH_BIT
#define BM_P23_CAMERA_FINISH_BIT 8      /* item 40: PR-D (outro = bit 8 only) */
#endif

#define CV_VIEW_RACE0  0x004D6200u      /* the race's view object (player 0), hirefresh.c */
#define CV_PC0         0x004CFB20u      /* player 0's controller (cameras at + 0x2A0, active mask + 0xC20 / + 0xC24) */
static const struct {
    uint32_t va;
    const char *hex;
} k_census[] = {
    {0x001C8A60u, "558bec83e4f081ec9800000053568d442460508b476883c020e8d2b3e4ff0f28008b4f588b59040f294424200f284010"},
    {0x001C8B47u, "8b5768f30f104210f30f1144241cf30f590584163b00f30f590548123a0083c408f30f11442418d9442418d9f2dd"},   /* item 29 */
};

static int s_ok;                        /* census passed, ops registered */
/* main21 patch 96 (bmashup.camera 4): player 0's last race-view picture as drawn. view_copy notes this picture's view object and
 * matrix copy; fov_scale (later in the same view build, after every write to the copy) reads the final matrix and the window
 * factors and publishes them (game thread; state() copies them under s_pic_seq: odd while written). */
#ifndef BO3_HOOKREQ_P27C
#define BO3_HOOKREQ_P27C 0          /* unit tests without the option: as before; the game: CMake ON */
#endif
static uint32_t s_rec_view, s_rec_mat;
static _Atomic uint32_t s_pic_seq;
static float s_pic_w, s_pic_h, s_pic_m[16];
static atomic_flag s_lock = ATOMIC_FLAG_INIT;
static _Atomic(td_host *) s_owner;
static bm_camera_adjust s_target;       /* under s_lock */
static float s_cur[6];                  /* the smoothed level (game thread) */
static double s_last_t;
static uint32_t s_chase;                /* last picture */
static float s_applied_roll;
static uint32_t s_written;
static double (*s_clock)(void);
/* item 29: the finish poses (under s_lock), the finish state (game thread) */
static _Atomic(td_host *) s_fin_owner;
static bm_camera_pose s_poses[BM_CAMERA_FINISH_POSES_MAX];
static uint32_t s_nposes;
static uint32_t s_finish;               /* the end-of-race camera ran at the last picture */
static double s_fin_t0;
static float s_car[16];                 /* item 40: the anchor = the game's outro camera (its first outro picture's copy) */
static float s_pic_fov = 1.0f;          /* this picture's field-of-view scale (a finish pose), else 1 */
static uint32_t s_finish_shown;
/* main21 patch 82 (version 3): the free camera. MUT (tests): 231 the radius not re-checked at the picture, 232 the TTL ignored,
 * 233 ownership not enforced, 234 applied to another view than player 0's race view, 235 the radius unchecked at the call */
#define CV_CAR1_POS (0x0073A1D0u + 0x10u + 0x30u)   /* player 1's car R + 0x10 matrix, position row (racers RC_MAT) */
static _Atomic(td_host *) s_free_owner;
static bm_camera_free s_free;           /* under s_lock */
static uint32_t s_free_pic, s_free_set; /* picture counter at the last set (s_free_set: 1 = a pose is held) */
static uint32_t s_pics;                 /* player 0's race-view pictures */
static uint32_t s_free_shown, s_view;

static double now_s(void)
{
    struct timespec ts;
    if (s_clock)
        return s_clock();
    timespec_get(&ts, TIME_UTC);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static const char *who(td_host *h)
{
    const char *id = h ? bo3_plugins_host_id(h) : NULL;
    return id && *id ? id : "(none)";
}

static int finite_f(float f)
{
    return f == f && f - f == 0.0f;
}

static int in_bounds(const bm_camera_adjust *a)
{
#if MUT == 221
    (void)a;
    return 1;
#endif
    for (int k = 0; k < 3; k++)
        if (!finite_f(a->offset_m[k]) || fabsf(a->offset_m[k]) > BM_CAMERA_OFFSET_MAX_M)
            return 0;
    return finite_f(a->roll_rad) && finite_f(a->pitch_rad) && finite_f(a->yaw_rad) && finite_f(a->smoothing_s) &&
           fabsf(a->roll_rad) <= BM_CAMERA_ROLL_MAX_RAD && fabsf(a->pitch_rad) <= BM_CAMERA_PITCH_YAW_MAX_RAD &&
           fabsf(a->yaw_rad) <= BM_CAMERA_PITCH_YAW_MAX_RAD && a->smoothing_s >= 0.0f && a->smoothing_s <= 1.0f;
}

static int follow_known(void)
{
    return BM_P23_CAMERA_FOLLOW_BIT >= 0 && BM_P23_CAMERA_FOLLOW_BIT < 64;
}

static int32_t cv_set_adjust(td_host *host, const bm_camera_adjust *a)
{
    td_host *none = NULL;
    if (a->struct_size < sizeof(bm_camera_adjust))
        return BM_CAMERA_BAD_ARG;
    if (!s_ok || !follow_known())
        return BM_CAMERA_UNAVAILABLE;
    if (!in_bounds(a)) {
        fprintf(stderr, "[CAMERA] mod %s: chase-camera adjust refused: out of the bounds (roll 0.35, pitch / yaw 0.17 rad, "
                        "offset 2 m, smoothing 0..1 s)\n", who(host));
        return BM_CAMERA_OUT_OF_RANGE;
    }
#if MUT == 225
    atomic_store(&s_owner, host);
#else
    if (!atomic_compare_exchange_strong(&s_owner, &none, host) && none != host)
        return BM_CAMERA_BUSY;
#endif
    while (atomic_flag_test_and_set(&s_lock))
        ;
    s_target = *a;
    s_target.struct_size = (uint32_t)sizeof s_target;
    atomic_flag_clear(&s_lock);
    return BM_CAMERA_OK;
}

static int32_t cv_release_adjust(td_host *host)
{
    td_host *me = host;
    if (!s_ok || !follow_known())
        return BM_CAMERA_UNAVAILABLE;
    if (!atomic_compare_exchange_strong(&s_owner, &me, NULL))
        return BM_CAMERA_NOT_OWNER;
    while (atomic_flag_test_and_set(&s_lock))
        ;
    memset(&s_target, 0, sizeof s_target);
    atomic_flag_clear(&s_lock);
    return BM_CAMERA_OK;
}

static void cv_fill_state(td_host *host, bm_camera_state *s)
{
    td_host *o = atomic_load(&s_owner);
    s->chase_active = s_chase;
    s->applied_roll_rad = s_applied_roll;
    s->adjust_owned = o != NULL;
    s->adjust_yours = o != NULL && o == host;
    s->finish_active = s_finish && s_finish_shown;
    {
        td_host *fo = atomic_load(&s_free_owner);       /* main21 patch 82 (v3) */
        s->free_active = s_free_shown;
        s->free_owned = fo != NULL;
        s->free_yours = fo != NULL && fo == host;
        s->view = s_view;
    }
    if (BO3_HOOKREQ_P27C) {                              /* main21 patch 96 (v4) */
        for (int tries = 0; tries < 8; tries++) {
            uint32_t a = atomic_load(&s_pic_seq), b;
            float w = s_pic_w, h = s_pic_h, m[16];
            if (a & 1u)
                continue;
            memcpy(m, s_pic_m, sizeof m);
            b = atomic_load(&s_pic_seq);
            if (a != b)
                continue;
            s->picture_seq = a / 2u;
            s->picture_half_w = w;
            s->picture_half_h = h;
            for (int k = 0; k < 3; k++) {
                s->picture_right[k] = m[k];
                s->picture_up[k] = m[4 + k];
                s->picture_fwd[k] = m[8 + k];
                s->picture_pos[k] = m[12 + k];
            }
            break;
        }
    }
}

static int finish_known(void)
{
    return BM_P23_CAMERA_FINISH_BIT >= 0 && BM_P23_CAMERA_FINISH_BIT < 64;
}

static float len3(const float *v)
{
    return sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

static int pose_ok(const bm_camera_pose *p)
{
    for (int k = 0; k < 3; k++)
        if (!finite_f(p->pos_m[k]) || !finite_f(p->at_m[k]))
            return 0;
    if (!finite_f(p->fov_scale) || !finite_f(p->hold_s) || p->fov_scale < 0.7f || p->fov_scale > 1.4f ||
        p->hold_s < BM_CAMERA_HOLD_MIN_S || p->hold_s > BM_CAMERA_HOLD_MAX_S)
        return 0;
    if (p->pos_m[0] == p->at_m[0] && p->pos_m[1] == p->at_m[1] && p->pos_m[2] == p->at_m[2])
        return 0;
#if MUT != 228
    if (len3(p->pos_m) > BM_CAMERA_FINISH_RADIUS_M || len3(p->at_m) > BM_CAMERA_FINISH_RADIUS_M)
        return 0;
#endif
    return 1;
}

static int32_t cv_set_finish_poses(td_host *host, const bm_camera_pose *p, uint32_t n)
{
    td_host *none = NULL;
    if (!s_ok || !finish_known())
        return BM_CAMERA_UNAVAILABLE;
    if (n > BM_CAMERA_FINISH_POSES_SERVED)
        return BM_CAMERA_OUT_OF_RANGE;                   /* item 40: one static pose a race (PR-D) */
    for (uint32_t i = 0; i < n; i++) {
        if (p[i].struct_size < sizeof(bm_camera_pose))
            return BM_CAMERA_BAD_ARG;
        if (!pose_ok(&p[i]))
            return BM_CAMERA_OUT_OF_RANGE;
    }
    if (!bo3_cam_stage_active())
        return BM_CAMERA_NOT_IN_RACE;
    if (!atomic_compare_exchange_strong(&s_fin_owner, &none, host) && none != host)
        return BM_CAMERA_BUSY;
    while (atomic_flag_test_and_set(&s_lock))
        ;
    for (uint32_t i = 0; i < n; i++) {
        s_poses[i] = p[i];
        s_poses[i].struct_size = (uint32_t)sizeof s_poses[i];
    }
    s_nposes = n;
    atomic_flag_clear(&s_lock);
    if (n == 0)
        atomic_store(&s_fin_owner, NULL);                /* cleared: the poses' owner gives them up */
    fprintf(stderr, "[CAMERA] mod %s: %u finish pose(s) for this race\n", who(host), (unsigned)n);
    return BM_CAMERA_OK;
}

static int look_at(float m[16], const float pos[3], const float at[3], const float up[3]);   /* patch 82: defined below */
static uint64_t cam_mask(void);
static int car_pos(float p[3])
{
    if (!bo3_guest_read(CV_CAR1_POS, p, 12))
        return 0;
    return finite_f(p[0]) && finite_f(p[1]) && finite_f(p[2]);
}

static int free_near(const float pos[3])
{
    float c[3], d[3];
    if (!car_pos(c))
        return 0;
    for (int k = 0; k < 3; k++)
        d[k] = pos[k] - c[k];
    return len3(d) <= BM_CAMERA_FREE_RADIUS_M;
}

static int free_ok(const bm_camera_free *f)
{
    float d[3], x[3];
    for (int k = 0; k < 3; k++)
        if (!finite_f(f->pos[k]) || !finite_f(f->at[k]) || !finite_f(f->up[k]))
            return 0;
    if (!finite_f(f->fov_scale) || f->fov_scale < 0.7f || f->fov_scale > 1.4f)
        return 0;
    for (int k = 0; k < 3; k++)
        d[k] = f->at[k] - f->pos[k];
    if (!(len3(d) > 0.05f))
        return 0;
    x[0] = f->up[1] * d[2] - f->up[2] * d[1];
    x[1] = f->up[2] * d[0] - f->up[0] * d[2];
    x[2] = f->up[0] * d[1] - f->up[1] * d[0];
    return len3(x) > 1e-3f * len3(d) * (len3(f->up) > 0.0f ? len3(f->up) : 1.0f) && len3(f->up) > 1e-3f;
}

static int32_t cv_set_free_pose(td_host *host, const bm_camera_free *f)
{
    td_host *none = NULL;
    if (!s_ok)
        return BM_CAMERA_UNAVAILABLE;
    if (!bo3_cam_stage_active())
        return BM_CAMERA_NOT_IN_RACE;
    if (!free_ok(f))
        return BM_CAMERA_OUT_OF_RANGE;
#if MUT != 235
    if (!free_near(f->pos))
        return BM_CAMERA_OUT_OF_RANGE;
#endif
#if MUT != 233
    if (!atomic_compare_exchange_strong(&s_free_owner, &none, host) && none != host)
        return BM_CAMERA_BUSY;
#else
    atomic_store(&s_free_owner, host);
#endif
    while (atomic_flag_test_and_set(&s_lock))
        ;
    s_free = *f;
    s_free_pic = s_pics;
    s_free_set = 1;
    atomic_flag_clear(&s_lock);
    return BM_CAMERA_OK;
}

static int32_t cv_release_free(td_host *host)
{
    td_host *o = atomic_load(&s_free_owner);
    if (o && o != host)
        return BM_CAMERA_NOT_OWNER;
    while (atomic_flag_test_and_set(&s_lock))
        ;
    s_free_set = 0;
    atomic_flag_clear(&s_lock);
    atomic_store(&s_free_owner, NULL);
    return BM_CAMERA_OK;
}

/* player 0's view kind now (v3 state().view) */
static uint32_t view_kind(uint32_t view)
{
    uint64_t m;
    if (view != CV_VIEW_RACE0 || !bo3_cam_stage_active())
        return BM_CAMERA_VIEW_NONE;
    if (bo3_cam_crash_camera())
        return BM_CAMERA_VIEW_CRASH;
    m = cam_mask();
    if (m == (1ull << 2))
        return BM_CAMERA_VIEW_CHASE;
    if (m == (1ull << 8))
        return BM_CAMERA_VIEW_FINISH;
    if (m == (1ull << 4) || m == (1ull << 5))
        return BM_CAMERA_VIEW_ALT;
    return BM_CAMERA_VIEW_OTHER;
}

/* the free pose for this picture; 1 = written */
static int free_picture(uint32_t view, uint32_t mat)
{
    bm_camera_free f;
    float m[16];
    int held;
#if MUT != 234
    if (view != CV_VIEW_RACE0 || !bo3_cam_stage_active())
        return 0;
#endif
    while (atomic_flag_test_and_set(&s_lock))
        ;
    held = s_free_set;
#if MUT != 232
    if (held && s_pics - s_free_pic > BM_CAMERA_FREE_TTL_PICTURES) {
        s_free_set = held = 0;                           /* not renewed: the game's camera again */
        atomic_store(&s_free_owner, NULL);
    }
#endif
    f = s_free;
    atomic_flag_clear(&s_lock);
    if (!held)
        return 0;
#if MUT != 231
    if (!free_near(f.pos))
        return 0;                                        /* the car went too far: the game's camera this picture */
#endif
    if (!bo3_guest_read(mat, m, (uint32_t)sizeof m) || !look_at(m, f.pos, f.at, f.up))
        return 0;
    if (!bo3_guest_write(mat, m, (uint32_t)sizeof m))
        return 0;
    s_written++;
    s_pic_fov = f.fov_scale;
    return 1;
}

static const bo3_cam_v2_ops k_ops = {cv_set_adjust, cv_release_adjust, cv_fill_state, cv_set_finish_poses, cv_set_free_pose,
                                     cv_release_free};

static uint32_t rd32(uint32_t va)
{
    uint32_t v = 0;
    return bo3_guest_rd32(va, &v) ? v : 0;
}

static uint64_t cam_mask(void)
{
    return (uint64_t)rd32(CV_PC0 + 0xC20u) | ((uint64_t)rd32(CV_PC0 + 0xC24u) << 32);
}

/* item 29: player 0's view is the end-of-race camera now */
static int finish_now(uint32_t view)
{
    return finish_known() && view == CV_VIEW_RACE0 && bo3_cam_stage_active() &&
           cam_mask() == (1ull << (BM_P23_CAMERA_FINISH_BIT & 63));
}

/* player 0's view is the chase camera now */
static int chase_now(uint32_t view)
{
    uint64_t mask;
    if (!follow_known() || view != CV_VIEW_RACE0)
        return 0;
#if MUT != 226
    if (!bo3_cam_stage_active())
        return 0;
#endif
#if MUT != 222
    if (bo3_cam_crash_camera())
        return 0;
#endif
    mask = cam_mask();
#if MUT == 223
    return (mask >> (BM_P23_CAMERA_FOLLOW_BIT & 63)) & 1u;
#else
    return mask == (1ull << (BM_P23_CAMERA_FOLLOW_BIT & 63));
#endif
}

/* rows r[0] right, r[1] up, r[2] at (3 floats each), p = pos: rotate in the camera frame, then offset along the new axes */
void bo3_camview_apply(float m[16], float roll, float pitch, float yaw, const float off[3])
{
    float r[3][3], n[3][3], cr = cosf(roll), sr = sinf(roll), cp = cosf(pitch), sp = sinf(pitch), cy = cosf(yaw),
          sy = sinf(yaw);
    float a[3][3];
    for (int i = 0; i < 3; i++)
        for (int k = 0; k < 3; k++)
            r[i][k] = m[i * 4 + k];
    /* local rotation (rows = new axes in old-axis coordinates) = roll (about at) x pitch (about right) x yaw (about up) */
    {
        const float rz[3][3] = {{cr, sr, 0.0f}, {-sr, cr, 0.0f}, {0.0f, 0.0f, 1.0f}};
        const float rx[3][3] = {{1.0f, 0.0f, 0.0f}, {0.0f, cp, sp}, {0.0f, -sp, cp}};
        const float ry[3][3] = {{cy, 0.0f, -sy}, {0.0f, 1.0f, 0.0f}, {sy, 0.0f, cy}};
        float t[3][3];
        for (int i = 0; i < 3; i++)
            for (int k = 0; k < 3; k++)
                t[i][k] = rz[i][0] * rx[0][k] + rz[i][1] * rx[1][k] + rz[i][2] * rx[2][k];
        for (int i = 0; i < 3; i++)
            for (int k = 0; k < 3; k++)
                a[i][k] = t[i][0] * ry[0][k] + t[i][1] * ry[1][k] + t[i][2] * ry[2][k];
    }
    for (int i = 0; i < 3; i++)
        for (int k = 0; k < 3; k++)
            n[i][k] = a[i][0] * r[0][k] + a[i][1] * r[1][k] + a[i][2] * r[2][k];
    for (int i = 0; i < 3; i++)
        for (int k = 0; k < 3; k++)
            m[i * 4 + k] = n[i][k];
    for (int k = 0; k < 3; k++)
        m[12 + k] += off[0] * n[0][k] + off[1] * n[1][k] + off[2] * n[2][k];
}

/* a camera matrix at `pos` looking at `at`, the car's up as the up hint (rows right, up, at, pos); 0 when degenerate */
static int look_at(float m[16], const float pos[3], const float at[3], const float up[3])
{
    float f[3] = {at[0] - pos[0], at[1] - pos[1], at[2] - pos[2]}, r[3], u[3], l;
    l = len3(f);
    if (!(l > 1e-4f))
        return 0;
    for (int k = 0; k < 3; k++)
        f[k] /= l;
    r[0] = up[1] * f[2] - up[2] * f[1];
    r[1] = up[2] * f[0] - up[0] * f[2];
    r[2] = up[0] * f[1] - up[1] * f[0];
    l = len3(r);
    if (!(l > 1e-4f))
        return 0;
    for (int k = 0; k < 3; k++)
        r[k] /= l;
    u[0] = f[1] * r[2] - f[2] * r[1];
    u[1] = f[2] * r[0] - f[0] * r[2];
    u[2] = f[0] * r[1] - f[1] * r[0];
    for (int k = 0; k < 3; k++) {
        m[k] = r[k];
        m[4 + k] = u[k];
        m[8 + k] = f[k];
        m[12 + k] = pos[k];
    }
    return 1;
}

static void car_point(const float *rel, float *w)
{
    for (int k = 0; k < 3; k++)
        w[k] = s_car[12 + k] + rel[0] * s_car[k] + rel[1] * s_car[4 + k] + rel[2] * s_car[8 + k];
}

/* item 29's own check of a FINISH_CAMERA proposal: within the radius of the anchor (item 40: the game's outro camera) */
static int finish_valid(const bm_hook_ctx *c, const bm_hook_out *o)
{
    float d[3], e[3];
    (void)c;
    if (o->finish_camera != BM_FINISH_CAMERA_POSE)
        return 1;
    for (int k = 0; k < 3; k++) {
        d[k] = o->pose_pos[k] - s_car[12 + k];
        e[k] = o->pose_at[k] - s_car[12 + k];
    }
#if MUT == 228
    return 1;
#endif
    return len3(d) <= BM_CAMERA_FINISH_RADIUS_M && len3(e) <= BM_CAMERA_FINISH_RADIUS_M;
}

static void finish_picture(uint32_t mat)
{
    float m[16];
    bm_camera_pose pose;
    int have = 0;
    double now = now_s(), at;
    bm_hook_out o;
    if (!bo3_guest_read(mat, m, (uint32_t)sizeof m))
        return;
    if (!s_finish) {
        s_finish = 1;
        s_fin_t0 = now;
        memcpy(s_car, m, sizeof s_car);                  /* item 40: the anchor = the game's static outro camera */
    }
    at = now - s_fin_t0;
    (void)at;
    while (atomic_flag_test_and_set(&s_lock))
        ;
    if (s_nposes) {
        pose = s_poses[0];                               /* item 40: the one pose, for the whole outro */
        have = 1;
    }
    atomic_flag_clear(&s_lock);
    memset(&o, 0, sizeof o);
    o.output = BM_HOOK_OUT_FINISH_CAMERA;
    o.finish_camera = BM_FINISH_CAMERA_GAME;
    o.pose_fov_scale = 1.0f;
    if (have) {
        o.finish_camera = BM_FINISH_CAMERA_POSE;
        car_point(pose.pos_m, o.pose_pos);
        car_point(pose.at_m, o.pose_at);
        o.pose_fov_scale = pose.fov_scale;
    }
    if (bo3_hk_point_wanted(BM_HOOK_FINISH_CAMERA)) {
        bm_hook_ctx c;
        bo3_hk_ctx_v3(&c, BM_HOOK_FINISH_CAMERA);
        for (int k = 0; k < 3; k++) {
            c.cam_right[k] = m[k];
            c.cam_up[k] = m[4 + k];
            c.cam_fwd[k] = m[8 + k];
            c.cam_pos[k] = m[12 + k];
        }
        c.finish_time_s = (float)(now - s_fin_t0);
        bo3_hk_dispatch_v3(BM_HOOK_FINISH_CAMERA, &c, &o);
    }
    s_finish_shown = o.finish_camera == BM_FINISH_CAMERA_POSE;
    if (!s_finish_shown || !look_at(m, o.pose_pos, o.pose_at, s_car + 4)) {
        s_finish_shown = 0;
        return;                                          /* the game's own end-of-race camera */
    }
    if (bo3_guest_write(mat, m, (uint32_t)sizeof m)) {
        s_written++;
        s_pic_fov = o.pose_fov_scale;
    }
}

/* main21 patch 96: publish this picture's window (from the angle the game is about to take the tangent of) and final pose */
static void picture_record(float angle)
{
    float m[16], f70 = 0.0f, f74 = 0.0f, w, h;
    uint32_t q;
#if MUT == 242
    uint32_t src = s_rec_view ? s_rec_view + 0x68u : 0u;   /* defect: the game camera's pointer, not the picture's copy */
    if (src && !bo3_guest_rd32(src, &src))
        src = 0;
#else
    uint32_t src = s_rec_mat;
#endif
    if (!src || !bo3_guest_read(src, m, (uint32_t)sizeof m) || !bo3_guest_read(s_rec_view + 0x70u, &f70, 4) ||
        !bo3_guest_read(s_rec_view + 0x74u, &f74, 4))
        return;
#if MUT == 240
    w = f70;                                             /* defect: tan(angle) omitted */
#else
    w = tanf(angle) * f70;
#endif
    h = f74 > 0.0f ? w / f74 : 0.0f;
    if (!finite_f(w) || !finite_f(h) || w <= 0.0f || h <= 0.0f)
        return;
    q = atomic_load(&s_pic_seq);
    atomic_store(&s_pic_seq, q | 1u);                    /* odd: being written */
    s_pic_w = w;
    s_pic_h = h;
    memcpy(s_pic_m, m, sizeof m);
    atomic_store(&s_pic_seq, (q | 1u) + 1u);
}

float bo3_cam_gen_fov_scale(float angle)
{
    float s = s_pic_fov, out;
#if MUT != 230
    s_pic_fov = 1.0f;                                    /* this picture only */
#endif
    out = angle;
    if (!(s == 1.0f || !finite_f(s) || s < 0.7f || s > 1.4f)) {
        out = angle * s;
        if (!finite_f(out))
            out = angle;
    }
    if (BO3_HOOKREQ_P27C && s_rec_view)
        picture_record(out);
#if MUT != 241
    s_rec_view = s_rec_mat = 0;                          /* this picture only */
#endif
    return out;
}

void bo3_cam_gen_view_copy(uint32_t view, uint32_t mat)
{
    float m[16], lv[6], tgt[6], sm;
    bm_camera_adjust t;
    double now, dt;
    s_pic_fov = 1.0f;
#if MUT != 241
    s_rec_view = s_rec_mat = 0;
#endif
    if (!s_ok || !mat)
        return;
    if (view == CV_VIEW_RACE0 && bo3_cam_stage_active()) {
        s_rec_view = view;                               /* main21 patch 96: recorded at this picture's fov_scale */
        s_rec_mat = mat;
    }
    if (view == CV_VIEW_RACE0) {                         /* main21 patch 82 (v3): the view kind, the free camera */
        s_pics++;
        s_view = view_kind(view);
    }
    s_free_shown = 0;
    if (free_picture(view, mat)) {
        s_free_shown = 1;
        s_chase = 0;
        s_applied_roll = 0.0f;
        return;
    }
#if MUT != 229
    if (!bo3_cam_stage_active() && (s_nposes || atomic_load(&s_fin_owner))) {
        while (atomic_flag_test_and_set(&s_lock))
            ;
        s_nposes = 0;                                    /* the race's stage ended: its poses go */
        atomic_flag_clear(&s_lock);
        atomic_store(&s_fin_owner, NULL);
    }
#endif
    if (finish_now(view)) {
        s_chase = 0;
        s_applied_roll = 0.0f;
        finish_picture(mat);
        return;
    }
    if (view == CV_VIEW_RACE0) {
        s_finish = 0;
        s_finish_shown = 0;
    }
    if (!chase_now(view)) {
        s_chase = 0;
        s_applied_roll = 0.0f;
        memset(s_cur, 0, sizeof s_cur);                 /* a chase view starts again from the owner's level */
        s_last_t = 0.0;
        return;
    }
    while (atomic_flag_test_and_set(&s_lock))
        ;
    t = s_target;
    atomic_flag_clear(&s_lock);
    tgt[0] = t.roll_rad; tgt[1] = t.pitch_rad; tgt[2] = t.yaw_rad;
    tgt[3] = t.offset_m[0]; tgt[4] = t.offset_m[1]; tgt[5] = t.offset_m[2];
    now = now_s();
    dt = s_chase && s_last_t > 0.0 ? now - s_last_t : 0.0;
    s_last_t = now;
    sm = (!s_chase || t.smoothing_s <= 0.0f || dt <= 0.0) ? 1.0f : (float)(1.0 - exp(-dt / (double)t.smoothing_s));
    if (!s_chase)
        sm = 1.0f;
    for (int k = 0; k < 6; k++)
        lv[k] = s_cur[k] = s_cur[k] + (tgt[k] - s_cur[k]) * sm;
    s_chase = 1;
    if (!bo3_guest_read(mat, m, (uint32_t)sizeof m))
        return;
    if (bo3_hk_point_wanted(BM_HOOK_CAMERA_FINAL)) {
        bm_hook_ctx c;
        bm_hook_out o;
        bo3_hk_ctx_v3(&c, BM_HOOK_CAMERA_FINAL);
        for (int k = 0; k < 3; k++) {
            c.cam_right[k] = m[k];
            c.cam_up[k] = m[4 + k];
            c.cam_fwd[k] = m[8 + k];
            c.cam_pos[k] = m[12 + k];
        }
        memset(&o, 0, sizeof o);
        o.output = BM_HOOK_OUT_CAMERA_ADJUST;
        o.roll_rad = lv[0]; o.pitch_rad = lv[1]; o.yaw_rad = lv[2];
        o.offset_m[0] = lv[3]; o.offset_m[1] = lv[4]; o.offset_m[2] = lv[5];
        if (bo3_hk_dispatch_v3(BM_HOOK_CAMERA_FINAL, &c, &o)) {
            lv[0] = o.roll_rad; lv[1] = o.pitch_rad; lv[2] = o.yaw_rad;
            lv[3] = o.offset_m[0]; lv[4] = o.offset_m[1]; lv[5] = o.offset_m[2];
        }
    }
    s_applied_roll = lv[0];
    if (lv[0] == 0.0f && lv[1] == 0.0f && lv[2] == 0.0f && lv[3] == 0.0f && lv[4] == 0.0f && lv[5] == 0.0f)
        return;                                          /* nothing to change: the game's matrix as built */
    bo3_camview_apply(m, lv[0], lv[1], lv[2], lv + 3);
#if MUT == 224
    {
        uint32_t cam = rd32(view + 0x68u);
        if (cam)
            bo3_guest_write(cam + 0x20u, m, (uint32_t)sizeof m);   /* defect: the game's camera object */
        return;
    }
#endif
    if (bo3_guest_write(mat, m, (uint32_t)sizeof m))
        s_written++;
}

static int census(void)
{
#if MUT == 227
    return 1;
#endif
    for (size_t r = 0; r < sizeof k_census / sizeof k_census[0]; r++) {
        uint8_t cur[64];
        size_t n = strlen(k_census[r].hex) / 2;
        if (n > sizeof cur || !bo3_guest_read(k_census[r].va, cur, (uint32_t)n))
            return 0;
        for (size_t i = 0; i < n; i++) {
            unsigned v = 0;
            for (int k = 0; k < 2; k++) {
                char c = k_census[r].hex[2 * i + (size_t)k];
                v = v * 16u + (unsigned)(c >= '0' && c <= '9' ? c - '0' : c - 'a' + 10);
            }
            if (cur[i] != (uint8_t)v)
                return 0;
        }
    }
    return 1;
}

void bo3_camview_init(void)
{
    s_ok = 0;
#if BO3_HOOKREQ_P23
    if (!census()) {
        fprintf(stderr, "[CAMERA] chase-camera adjust: the game's bytes at the view build differ from this build's census: "
                        "UNAVAILABLE\n");
        return;
    }
    s_ok = 1;
    bo3_cam_set_v2(&k_ops);
    if (follow_known())
        bo3_hk_offer_point(BM_HOOK_CAMERA_FINAL, (1u << BM_HOOK_OBSERVE) | (1u << BM_HOOK_MODIFY), NULL);
    else
        fprintf(stderr, "[CAMERA] chase-camera adjust / CAMERA_FINAL: UNAVAILABLE in this build (the follow camera's slot is "
                        "not known: BM_P23_CAMERA_FOLLOW_BIT)\n");
    if (finish_known())
        bo3_hk_offer_point(BM_HOOK_FINISH_CAMERA, (1u << BM_HOOK_OBSERVE) | (1u << BM_HOOK_MODIFY), finish_valid);
    else
        fprintf(stderr, "[CAMERA] finish poses / FINISH_CAMERA: UNAVAILABLE in this build (the end-of-race camera's slot is "
                        "not known: BM_P23_CAMERA_FINISH_BIT)\n");
#else
    (void)census;
    (void)k_ops;
    (void)finish_valid;
#endif
}

/* tests */
void bo3_camview_reset_for_tests(double (*clock_fn)(void))
{
    s_ok = 0;
    atomic_store(&s_owner, NULL);
    memset(&s_target, 0, sizeof s_target);
    memset(s_cur, 0, sizeof s_cur);
    s_last_t = 0.0;
    s_chase = 0;
    s_applied_roll = 0.0f;
    s_written = 0;
    s_clock = clock_fn;
    atomic_store(&s_fin_owner, NULL);
    memset(s_poses, 0, sizeof s_poses);
    s_nposes = 0;
    s_finish = s_finish_shown = 0;
    s_fin_t0 = 0.0;
    memset(s_car, 0, sizeof s_car);
    s_pic_fov = 1.0f;
    atomic_store(&s_free_owner, NULL);
    memset(&s_free, 0, sizeof s_free);
    s_free_pic = s_free_set = s_pics = s_free_shown = s_view = 0;
}

uint32_t bo3_camview_written(void)
{
    return s_written;
}
