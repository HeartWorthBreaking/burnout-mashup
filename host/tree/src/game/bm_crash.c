/* bm_crash.c - GP-CRASH1 EXPERIMENTAL: Crash mode for plugins (gp\atlas\CRASH.md).
 *
 * 1. "bmashup.crash" v1 (include/bmashup_crash.h): read-only queries over the game's Crash junction list, the 100 x u64
 *    base-40 IDs at 0x39D870 (.rdata, the list sub_00157720 searches). The list is checked against the build this host was
 *    made for before anything is answered: its 800 bytes' FNV-1a 64 must be the pinned value (default.xbe NTSC-U sha256
 *    9f497acd...), every entry must decode as "1G" + its own index in hex + a track, and the word after the list must not.
 * 2. bmashup.events v6 CRASH_RESULT and the H1 guard, from ONE generated line in sub_0001EE80 (the game's record step at the
 *    end of an event, called by sub_00061FC0) at loc_0001EEC1, right after the junction search returned:
 *        if (bo3_cr_gen_junction_record(eax, ebx)) { esp = esp + 8; SET_LO8(eax, 0); goto loc_0001EF07; }
 *    eax = the junction index (sub_00157720: 0..99 or -1), ebx = the results flags (only flags & 0x30, Crash types, reach
 *    this line). The game has just stored the junction ID at 0x44D678 / 0x44D67C. The score is read the way the game's
 *    record insert sub_0001EDB0 reads it for player 1 (edi = 0 there):
 *        flags & 0x10: MEM32(0x73B938)                                   (= car 1 + 0x1768, written by sub_0002A720)
 *        else (0x20):  MEM32(MEM32(0x73A1A8 + 4 * (MEM8(0x73BB8C) == 0)) + 0x1768) + MEM32(0x73B938)
 *    Returns 0 for an index 0..99 (the game goes on unchanged), 1 for anything else: the game's own code would compute the
 *    record at 0x44D680 + 0x4EC0 + index * 0x17C (index -1: inside track record 35) and insert a top-5 entry there; the
 *    generated line then leaves the function the way its own "no new record" exit does (args popped, al = 0, state 0x44D670
 *    left at 3 = nothing recorded).
 * Reads only, except that skip. MUT=n (tests only) compiles one deliberate defect. */
#include "bm_crash.h"

#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "bm_events_service.h"
#include "bm_guest.h"
#include "plugins.h"

#ifndef MUT
#define MUT 0
#endif

#define CR_TABLE      0x0039D870u
#define CR_COUNT      100u
#define CR_FNV        0x22BE231EE50D0935ull     /* FNV-1a 64 of the 800 bytes, default.xbe NTSC-U (gp\atlas\scripts) */
#define CR_ID_LO      0x0044D678u               /* the game's copy of the junction ID (sub_0001EE80 loc_0001EEA9) */
#define CR_ID_HI      0x0044D67Cu
#define CR_SCORE_P1   0x0073B938u               /* player 1's crash total (car 1 0x73A1D0 + 0x1768) */
#define CR_LIST       0x0073A1A8u               /* the race's car list */
#define CR_SEL        0x0073BB8Cu               /* player 1's byte the pair score selects the other car by */
#define CR_CAR_SCORE  0x1768u
#define CR_FLAG_SINGLE 0x10u

static const char B40[] = " -/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_";

/* the 12-character ID of a 64-bit base-40 value (trailing spaces cut) */
void bo3_cr_decode(uint64_t v, char out[16])
{
    char s[13];
    for (int i = 11; i >= 0; i--) {
#if MUT == 1
        s[11 - i] = B40[v % 40u];                /* defect: the characters reversed */
#else
        s[i] = B40[v % 40u];
#endif
        v /= 40u;
    }
    s[12] = 0;
    for (int i = 11; i >= 0 && s[i] == ' '; i--)
        s[i] = 0;
    memset(out, 0, 16);
    memcpy(out, s, strlen(s));
}

/* "1G0000USC3V1" -> "US_C3_V1"; "" when the last six characters are not region(2) + letter digit + letter digit */
void bo3_cr_track_of(const char *id, char out[16])
{
    const char *t = id;
    size_t n = strlen(id);
    memset(out, 0, 16);
    if (n != 12)
        return;
    t = id + 6;
    if (t[0] < 'A' || t[0] > 'Z' || t[1] < 'A' || t[1] > 'Z' || t[2] < 'A' || t[2] > 'Z' || t[3] < '0' || t[3] > '9' ||
        t[4] < 'A' || t[4] > 'Z' || t[5] < '0' || t[5] > '9')
        return;
    out[0] = t[0]; out[1] = t[1]; out[2] = '_'; out[3] = t[2]; out[4] = t[3]; out[5] = '_'; out[6] = t[4]; out[7] = t[5];
}

/* ------------------------------------------------------------------ the verified junction list */
static int s_state;                              /* 0 not checked, 1 verified, -1 not this build */
static char s_id[CR_COUNT][16], s_track[CR_COUNT][16];

static int verify(void)
{
    uint8_t raw[CR_COUNT * 8 + 8];
    uint64_t h = 0xCBF29CE484222325ull, v;
    char id[16], want[8];

    if (s_state)
        return s_state > 0;
    if (!bo3_guest_read(CR_TABLE, raw, sizeof raw))
        return 0;                                /* not mapped yet: asked again later */
    for (uint32_t i = 0; i < CR_COUNT * 8u; i++) {
        h ^= raw[i];
        h *= 0x100000001B3ull;
    }
    s_state = 1;
#if MUT != 2
    if (h != CR_FNV)
        s_state = -1;                            /* defect 2: the pinned hash not compared */
#endif
    for (uint32_t i = 0; i < CR_COUNT && s_state > 0; i++) {
        memcpy(&v, raw + 8u * i, 8);
        bo3_cr_decode(v, id);
        /* the game's numbering: "1G" + "0" + group 0..4 + "0" + 0..9 A..J (20 a group) */
        snprintf(want, sizeof want, "1G0%u0%c", (unsigned)(i / 20u), "0123456789ABCDEFGHIJ"[i % 20u]);
        if (strncmp(id, want, 6) != 0)
            s_state = -1;
        memcpy(s_id[i], id, 16);
        bo3_cr_track_of(id, s_track[i]);
        if (!s_track[i][0])
            s_state = -1;
    }
    memcpy(&v, raw + CR_COUNT * 8u, 8);
    bo3_cr_decode(v, id);
    if (!strncmp(id, "1G", 2))
        s_state = -1;                            /* the list goes on: not the 100-entry list of this build */
    fprintf(stderr, "[CRASH] the game's junction list: %s (%u junctions, FNV-1a %016llX)\n",
            s_state > 0 ? "verified" : "NOT the list this host was made for: bmashup.crash answers UNAVAILABLE",
            (unsigned)CR_COUNT, (unsigned long long)h);
    return s_state > 0;
}

/* ------------------------------------------------------------------ the last result (seqlock: one writer, the game's thread) */
static _Atomic uint32_t s_seq;
static bm_crash_result s_last;
static uint32_t s_results, s_skipped;

static void store_last(const bo3_bm_crash_result *cr)
{
    atomic_fetch_add(&s_seq, 1);                 /* odd: being written */
    atomic_thread_fence(memory_order_seq_cst);
    s_last.struct_size = (uint32_t)sizeof s_last;
    s_last.sequence = s_results;
    s_last.junction = cr->junction;
    s_last.score = cr->score;
    s_last.mode = cr->mode;
    memcpy(s_last.junction_id, cr->junction_id, 16);
    memcpy(s_last.track_id, cr->track_id, 16);
    atomic_thread_fence(memory_order_seq_cst);
    atomic_fetch_add(&s_seq, 1);                 /* even: complete */
}

/* ------------------------------------------------------------------ the generated line */
int bo3_cr_gen_junction_record(uint32_t index, uint32_t flags)
{
    bo3_bm_crash_result cr;
    uint32_t lo = 0, hi = 0, p1 = 0, other_car = 0, other = 0;
    uint8_t sel = 0;
    int in_list;

    memset(&cr, 0, sizeof cr);
    bo3_guest_rd32(CR_ID_LO, &lo);
    bo3_guest_rd32(CR_ID_HI, &hi);
    bo3_cr_decode(((uint64_t)hi << 32) | lo, cr.junction_id);
    bo3_cr_track_of(cr.junction_id, cr.track_id);
    bo3_guest_rd32(CR_SCORE_P1, &p1);
#if MUT == 3
    cr.mode = BM_CRASH_MODE_SINGLE;              /* defect: the pair scoring never recognised */
    cr.score = p1;
    (void)flags; (void)sel; (void)other_car; (void)other;
#else
    if (flags & CR_FLAG_SINGLE) {
        cr.mode = BM_CRASH_MODE_SINGLE;
        cr.score = p1;
    } else {
        cr.mode = BM_CRASH_MODE_PAIR;
        bo3_guest_read(CR_SEL, &sel, 1);
        if (bo3_guest_rd32(CR_LIST + 4u * (sel == 0 ? 1u : 0u), &other_car) && other_car)
            bo3_guest_rd32(other_car + CR_CAR_SCORE, &other);
        cr.score = other + p1;
    }
#endif
#if MUT == 4
    in_list = 1;                                 /* defect: the index not checked (the game's own behaviour) */
#else
    in_list = index < CR_COUNT;
#endif
    cr.junction = in_list ? index : BM_EVENT_NO_JUNCTION;
    s_results++;
    if (!in_list)
        s_skipped++;
    fprintf(stderr, "[CRASH] result %u: junction %d %s (track %s), score %u, %s scoring (flags 0x%02X)%s\n",
            (unsigned)s_results, in_list ? (int)index : -1, cr.junction_id, cr.track_id[0] ? cr.track_id : "-",
            (unsigned)cr.score, cr.mode == BM_CRASH_MODE_SINGLE ? "single" : "pair", (unsigned)(flags & 0xFFu),
            in_list ? "" : ": the ID is not in the game's junction list, its record write is skipped (H1 guard)");
    store_last(&cr);
    bo3_bm_events_deliver_crash(&cr);
    return !in_list;
}

uint32_t bo3_cr_stats(uint32_t which)
{
    return which == 0 ? s_results : s_skipped;
}

#ifdef BO3_CR_TESTING
/* tests only: forget the list check and the results (a new process, as far as this module goes) */
void bo3_cr_test_reset(void)
{
    s_state = 0;
    s_results = s_skipped = 0;
    memset(&s_last, 0, sizeof s_last);
    atomic_store(&s_seq, 0);
}
#endif

/* ------------------------------------------------------------------ the service */
static uint32_t TD_CALL c_count(td_host *host)
{
    return host && verify() ? CR_COUNT : 0;
}

static int32_t TD_CALL c_get(td_host *host, uint32_t index, bm_crash_junction *out)
{
    bm_crash_junction o;
    if (!host || !out || out->struct_size < 8)
        return BM_CRASH_BAD_ARG;
    if (!verify())
        return BM_CRASH_UNAVAILABLE;
    if (index >= CR_COUNT)
        return BM_CRASH_NOT_FOUND;
    memset(&o, 0, sizeof o);
    o.struct_size = out->struct_size < sizeof o ? out->struct_size : (uint32_t)sizeof o;
    o.index = index;
    memcpy(o.id, s_id[index], 16);
    memcpy(o.track_id, s_track[index], 16);
    memcpy(out, &o, o.struct_size);
    return BM_CRASH_OK;
}

static int32_t TD_CALL c_find(td_host *host, const char *id, uint32_t *index)
{
    size_t n;
    if (!host || !id || !index)
        return BM_CRASH_BAD_ARG;
    n = strnlen(id, 16);
    if (n == 0 || n > 12)
        return BM_CRASH_BAD_ARG;
    if (!verify())
        return BM_CRASH_UNAVAILABLE;
    for (uint32_t i = 0; i < CR_COUNT; i++)
        if (!strcmp(s_id[i], id)) {
            *index = i;
            return BM_CRASH_OK;
        }
    return BM_CRASH_NOT_FOUND;
}

static int32_t TD_CALL c_last(td_host *host, bm_crash_result *out)
{
    bm_crash_result c;
    uint32_t a, b, room;
    if (!host || !out || out->struct_size < 8)
        return BM_CRASH_BAD_ARG;
    for (int tries = 0;; tries++) {
        a = atomic_load(&s_seq);
        atomic_thread_fence(memory_order_seq_cst);
        memcpy(&c, &s_last, sizeof c);
        atomic_thread_fence(memory_order_seq_cst);
        b = atomic_load(&s_seq);
        if (a == b && !(a & 1u))
            break;
        if (tries > 1000)
            return BM_CRASH_UNAVAILABLE;
    }
    if (!c.sequence)
        return BM_CRASH_NONE_YET;
    room = out->struct_size < sizeof c ? out->struct_size : (uint32_t)sizeof c;
    c.struct_size = room;
    memcpy(out, &c, room);
    return BM_CRASH_OK;
}

static const bm_crash_api s_api = {(uint32_t)sizeof(bm_crash_api), BM_CRASH_VERSION, c_count, c_get, c_find, c_last};

const bm_crash_api *bo3_bm_crash_api(void)
{
    return &s_api;
}

void bo3_bm_crash_init(void)
{
    bo3_plugins_service(BM_CRASH_SERVICE, BM_CRASH_VERSION, &s_api);
}
