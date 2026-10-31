/*
 * bm_contact.c - main19 (hook request P2, item 26; IMPLEMENTATION_PLAN patch 26, FEASIBILITY F1 / F2 / F3): bmashup.hooks v3
 *   10 TRAFFIC_CONTACT  MODIFY CONTACT_OUTCOME at the fatal decision of the vehicle-contact response sub_00112E70
 *                       (bo3_contact_gen.h): a plugin's NO_CRASH takes the game's own non-fatal branch;
 *   11 WRECK_CAUSE      OBSERVE at sub_00198E60's count step (aggressor, victim).
 * Sites: gp\hookreq\p23\SITES_VERIFIED.md s5 + tests\p23\STEP0_B.md (every byte re-checked on XBE 9f497acd).
 *
 * TRAFFIC_CONTACT is dispatched only when the game is about to make the contact fatal: the closing metric is above the threshold
 * (the mark's own compare), the class pair is fatal in the game's matrix ([esp+0x1A]), the forced path (P + 0x212 with
 * P + 0x215 != 3) does not apply, car A is a racer of the race list and car B is NOT a racer (racer vs racer is never offered).
 * The values given: the racer index, an opaque per-occurrence handle, the closing speed (the game's metric / 2.23693633 = m/s)
 * and same_dir (dot of the game's own velocity vectors vA = [[P+0x204]+0x20] x [P+0xBC], vB = [Bb+0x90] x [Bb+0xC4] > 0).
 * The framework (bm_hooks.c) accepts NO_CRASH only for same_dir == 1 and closing < BM_HOOK_CONTACT_MAX_MPS (main21 patch 116:
 * 60 m/s; the threshold [P + 0x1534] x [0x3EBE44] / [0x3EBE48] = 75 in a race, i.e. every offered contact closes at > 33.5 m/s).
 *
 * WRECK_CAUSE credit (MODIFY WRECK_CREDIT; item 39, probe PR-H: READY): asked when a racer WRECKS (bm_takedown.c's wreck mark,
 * through bo3_e6_wreck_tap; cause_victim = it, cause_aggressor = the racer holding the game's newest live claim on the
 * victim (item 52; BM_HOOK_NO_RACER when none), and out->credit_racer is prefilled with it). An accepted
 * credit_racer becomes a CLAIM the game's own claim processor sub_00197040 handles (within ~0.5 s): in the credited racer's score
 * object S = R + 0x10D0, the claim time S + 0x4D8 + 4 i = that racer's race time R + 0x10DC and the mark S + 0x4F6 + i = 1, i =
 * the victim's race-list index (the natural claim PR-H observed; the processor reads S + 0x4D8 + 4 i against S + 0xC + 1.0 s).
 * The game decides: a competing claim may win; nothing is counted by the host. Refused (the item's check): a racer outside the
 * list, the victim itself, an index >= 6 (the claim arrays), a victim already credited (victim + 0x15D6 set). Observers still
 * see WRECK_CAUSE at the game's count step (with the aggressor the game chose).
 * BO3_HOOKREQ_P23 == 0: the marks are not in the generated code and bo3_hk_offer_point refuses (both points UNAVAILABLE).
 * MUT=n (tests only): 201 racer vs racer dispatched, 202 the forced fatal path dispatched, 203 same_dir from speeds only (no
 * direction), 204 the census skipped, 205 NO_CRASH answered without the dispatcher's verdict; item 39: 206 credit to the victim
 * accepted (equivalent: the framework's bound refuses it first; not in the mutant list), 207 the victim + 0x15D6 guard skipped, 208 the claim time not the claimant's race time, 209 a victim index >= 6
 * accepted; item 52: 210 an expired / empty claim taken as the toucher.
 * main21 patch 79 (open item 7, contact push scaling): with NO_CRASH, out->push_scale (0 .. 1, bounded by bm_hooks.c) is kept
 * for THAT contact record; the mark after sub_00112E70's push force (0x1134BB mulss: min(mass, 2000) x 100, the magnitude of the
 * force sub_001205E0 adds to the car's force accumulator + 0xF0 at the contact point) multiplies it (bo3_ct_gen_push). Own census
 * (2 rows). BO3_HOOKREQ_P9C == 0: no mark, the factor is accepted but not applied. MUT 221 the factor applied to any contact,
 * 222 kept after its contact, 223 the push census skipped.
 */
#include "bm_contact.h"

#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "bm_hooks.h"
#include "bm_takedown.h"

#ifndef BO3_HOOKREQ_P9C
#define BO3_HOOKREQ_P9C 1           /* unit tests: the CMake option is not there */
#endif
#ifndef MUT
#define MUT 0
#endif

/* PR-A / PR-H: 1 = the game's claim path (S + 0x4D8 / + 0x4F6) is verified -> WRECK_CAUSE also offers MODIFY (item 39: PR-H READY). */
#ifndef BM_P23_WRECK_CREDIT_VERIFIED
#define BM_P23_WRECK_CREDIT_VERIFIED 1
#endif
#define CT_S          0x10D0u           /* R -> its score object S */
#define CT_RTIME      0x10DCu           /* R: race time (float) */
#define CT_CLAIM_T    0x4D8u            /* S: claim times, 4 bytes per victim index */
#define CT_CLAIM_MARK 0x4F6u            /* S: claim marks, 1 byte per victim index */
#define CT_CLAIMS     6u                /* the claim arrays' entries */
#define CT_CREDITED   0x15D6u           /* victim R: credited (the game's once-per-wreck latch) */

#define CT_RACE_COUNT 0x0073A19Cu
#define CT_RACE_LIST  0x0073A1A8u
#define CT_MAX_RACERS 16u
#define CT_MPH        2.23693633f

static const struct {
    uint32_t va;
    const char *hex;
} k_census[] = {
    /* sub_00112E70: the velocity reads (0x1132B4..0x1132FD) and the fatal decision (0x1133B2..0x1133E9) */
    {0x001132B4u, "8b9304020000f30f1083bc00000083c2208d8424a0000000e83fe3efff508d8424840000008d4c2474e8bee3efff8b442464"
                  "f30f1080c40000008d90900000008d842480000000e810e3"},
    {0x001133B2u, "f30f108b34150000f30f590d44be3e00f30f108424800000000f57dbf30f10642468f30f106c246c0f2fc10f284424507605"
                  "c644241b00"},
    /* sub_00198E60: entry to the count step */
    {0x00198E60u, "8a87fa1800005333db84c074068d9fd81300008a87d615000084c00f85000100008b86c80000008987dc150000c687d615"},
};

static int s_ok;
static uint32_t s_seq;
static bo3_contact_stats s_st;

static int hexbyte(const char *h)
{
    int v = 0;
    for (int i = 0; i < 2; i++) {
        char c = h[i];
        v = v * 16 + (c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : 0);
    }
    return v;
}

static int census(void)
{
#if MUT == 204
    return 1;
#endif
    for (size_t k = 0; k < sizeof k_census / sizeof k_census[0]; k++) {
        uint8_t cur[128];
        size_t n = strlen(k_census[k].hex) / 2;
        if (n > sizeof cur || !bo3_guest_read(k_census[k].va, cur, (uint32_t)n))
            return 0;
        for (size_t i = 0; i < n; i++)
            if (cur[i] != (uint8_t)hexbyte(k_census[k].hex + 2 * i))
                return 0;
    }
    return 1;
}

static uint32_t rd32(uint32_t va)
{
    uint32_t v = 0;
    return bo3_guest_rd32(va, &v) ? v : 0;
}

static float rdf(uint32_t va)
{
    float f = 0.0f;
    uint32_t v;
    if (bo3_guest_rd32(va, &v))
        memcpy(&f, &v, 4);
    return f;
}

/* the racer's index in the race list, or BM_HOOK_NO_RACER */
static uint32_t racer_index(uint32_t r)
{
    uint32_t n = rd32(CT_RACE_COUNT);
    if (!r)
        return BM_HOOK_NO_RACER;
    if (n > CT_MAX_RACERS)
        n = CT_MAX_RACERS;
    for (uint32_t i = 0; i < n; i++)
        if (rd32(CT_RACE_LIST + 4u * i) == r)
            return i;
    return BM_HOOK_NO_RACER;
}

/* patch 79: the push site (default.xbe 9f497acd)
 * BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } s_push_rows[] = {
    { 0x001134BBu, 24, { 0xf3,0x0f,0x59,0x05,0x6c,0xbe,0x3e,0x00,0x8d,0x84,0x24,0xa0,0x00,0x00,0x00,0x8d,0x4c,0x24,0x50,0xe8,0xed,0xe0,
                         0xef,0xff } },                     /* x 100; scale the normal (sub_000115C0) */
    { 0x001134D3u, 16, { 0x8d,0x44,0x24,0x70,0x50,0x8d,0x7c,0x24,0x54,0x8b,0xc3,0xe8,0xfd,0xd0,0x00,0x00 } },  /* force at the point */
};
/* END-CENSUS */
/* main21 patch 86 (diagnostics, probe S4c): bounded [DIAG] lines per race (the counters reset at each race exit / load). The
 * game thread only (the marks and the lifecycle delivery). */
#define CT_DIAG_LINES 48u
static uint32_t s_dg_lines, s_dg_calls, s_dg_a_not_racer, s_dg_b_racer_only, s_dg_forced, s_dg_racers, s_dg_dispatched,
                s_dg_no_crash, s_dg_pushed, s_dg_wrecks;

static int dg_line(void) { return s_dg_lines < CT_DIAG_LINES ? (s_dg_lines++, 1) : 0; }

static uint32_t s_push_rec;
static uint32_t s_push_clock;      /* the game clock (0x60EA20) of the decision: the same frame only (records are reused) */
static float s_push_scale = 1.0f;
static uint32_t s_pushed;
static int s_push_ok = -1;

static int push_census(void)
{
#if MUT == 223
    return 1;
#endif
    if (s_push_ok != 1) {
        s_push_ok = 1;
        for (size_t k = 0; k < sizeof s_push_rows / sizeof s_push_rows[0]; k++) {
            uint8_t x[24];
            if (!bo3_guest_read(s_push_rows[k].va, x, s_push_rows[k].n) || memcmp(x, s_push_rows[k].b, s_push_rows[k].n))
                s_push_ok = 0;
        }
    }
    return s_push_ok;
}

/* patch 79 mark (generated code, sub_00112E70 after 0x1134BB): rec = [ebp + 0xC], f = the push force magnitude */
float bo3_ct_gen_push(uint32_t rec, float f)
{
#if MUT == 221
    if (!s_push_rec)
#else
    if (!rec || rec != s_push_rec || rd32(0x0060EA20u) != s_push_clock)
#endif
        return f;
#if MUT != 222
    s_push_rec = 0;                                      /* this contact only */
#endif
    s_pushed++;
    s_dg_pushed++;
    if (dg_line())
        fprintf(stderr, "[DIAG] contact push scaled x%.2f: force %.0f -> %.0f\n", (double)s_push_scale, (double)f,
                (double)(f * s_push_scale));
    return f * s_push_scale;
}

uint32_t bo3_ct_pushed(void) { return s_pushed; }

/* main21 patch 110 (probe R20 "NO_CRASH still crashed", static root cause): in sub_00112E70 the crash itself is gated by the class
 * pair byte [esp + 0x1A] (table 0x39AE50) at 0x11350D (je 0x1135D4 = the clean exit, else the crash decider sub_0010DCA0 /
 * sub_0010E580 and the wreck conversion sub_00114910); the closing threshold (patch 26's mark) only chooses the push ([esp + 0x1B]).
 * So NO_CRASH kept the push but never stopped the crash. The second mark at loc_001133E9 (after the threshold branch, before the
 * forced-path test) clears [esp + 0x1A] for the ONE contact the dispatcher just answered NO_CRASH (record + game clock), so the
 * game's own code takes its clean exit after the push response. Own census (2 rows). BO3_HOOKREQ_ZNC == 0: no mark (the main19 ..
 * main21 behaviour). MUT 224 cleared for any contact, 225 the census skipped. */
#ifndef BO3_HOOKREQ_ZNC
#define BO3_HOOKREQ_ZNC 1           /* unit tests: the CMake option is not there */
#endif
/* BEGIN-CENSUS */
static const struct { uint32_t va; uint8_t n; uint8_t b[12]; } s_nc_rows[] = {
    { 0x001133E9u, 12, { 0x8a,0x83,0x12,0x02,0x00,0x00,0x84,0xc0,0x74,0x0d,0x80,0xbb } },   /* the forced-path test after the mark */
    { 0x0011350Du, 12, { 0x8a,0x44,0x24,0x1a,0x84,0xc0,0x0f,0x84,0xbb,0x00,0x00,0x00 } },   /* [esp + 0x1A] -> je 0x1135D4 */
};
/* END-CENSUS */
static uint32_t s_nc_rec, s_nc_clock, s_nc_cleared;
static int s_nc_ok = -1;

static int nc_census(void)
{
#if MUT == 225
    return 1;
#endif
    if (s_nc_ok != 1) {
        s_nc_ok = 1;
        for (size_t k = 0; k < sizeof s_nc_rows / sizeof s_nc_rows[0]; k++) {
            uint8_t x[12];
            if (!bo3_guest_read(s_nc_rows[k].va, x, s_nc_rows[k].n) || memcmp(x, s_nc_rows[k].b, s_nc_rows[k].n))
                s_nc_ok = 0;
        }
    }
    return s_nc_ok;
}

/* patch 110 mark (sub_00112E70 loc_001133E9): rec = [ebp + 0xC], sp = the generated code's esp */
void bo3_ct_gen_nocrash(uint32_t rec, uint32_t sp)
{
    uint8_t z = 0;
#if MUT == 224
    if (!rec || !BO3_HOOKREQ_ZNC || (s_nc_rec == 0xFFFFFFFFu && s_nc_clock == 1u))   /* defect: any contact */
#else
    if (!rec || rec != s_nc_rec || rd32(0x0060EA20u) != s_nc_clock || !BO3_HOOKREQ_ZNC)
#endif
        return;
    s_nc_rec = 0;                                        /* this contact only */
    if (nc_census() != 1)
        return;
    bo3_guest_write(sp + 0x1Au, &z, 1);
    s_nc_cleared++;
    if (dg_line())
        fprintf(stderr, "[DIAG] contact NO_CRASH: the class-pair crash skipped (the game's clean exit 0x1135D4)\n");
}

uint32_t bo3_ct_nocrash_cleared(void) { return s_nc_cleared; }

void bo3_ct_diag_lifecycle(uint32_t kind)
{
    if (s_dg_calls || s_dg_wrecks)
        fprintf(stderr, "[DIAG] contact summary (%s): marks %u, A not a racer %u (B a racer %u), forced %u, racer vs racer %u, "
                "dispatched %u, NO_CRASH %u, pushes scaled %u, wrecks %u\n", kind == 2u ? "race exit" : "load",
                (unsigned)s_dg_calls, (unsigned)s_dg_a_not_racer, (unsigned)s_dg_b_racer_only, (unsigned)s_dg_forced,
                (unsigned)s_dg_racers, (unsigned)s_dg_dispatched, (unsigned)s_dg_no_crash, (unsigned)s_dg_pushed,
                (unsigned)s_dg_wrecks);
    s_dg_lines = s_dg_calls = s_dg_a_not_racer = s_dg_b_racer_only = s_dg_forced = s_dg_racers = s_dg_dispatched = 0;
    s_dg_no_crash = s_dg_pushed = s_dg_wrecks = 0;
}

int bo3_ct_gen_contact(uint32_t rec, uint32_t body_a, double metric, double threshold)
{
    bm_hook_ctx c;
    bm_hook_out o;
    uint32_t ia, ib, bb, b, ma;
    float va[3], vb[3], sa, sb, dot;
    s_nc_rec = 0;                                        /* patch 110: a new decision forgets the last NO_CRASH */
    if (!s_ok || !rec || !body_a)
        return 0;
    s_dg_calls++;
#if MUT != 202
    if (((rd32(body_a + 0x210u) >> 16) & 0xFFu) != 0 && ((rd32(body_a + 0x214u) >> 8) & 0xFFu) != 3u) {
        s_dg_forced++;
        if (dg_line())
            fprintf(stderr, "[DIAG] contact forced fatal path (P + 0x212 set): A %08x racer %d, metric %.1f > %.1f\n",
                    (unsigned)body_a, (int)racer_index(rd32(body_a + 0x13F4u)), metric, threshold);
        s_st.skipped_forced++;                           /* P + 0x212 set and P + 0x215 != 3: the game crashes it anyway */
        return 0;
    }
#endif
    ia = racer_index(rd32(body_a + 0x13F4u));
    b = rd32(rec + 0x28u);
    bb = b ? rd32(b + 0xCu) : 0;
    ib = bb ? racer_index(rd32(bb + 0x13F4u)) : BM_HOOK_NO_RACER;
    if (ia == BM_HOOK_NO_RACER) {
        s_dg_a_not_racer++;
        if (ib != BM_HOOK_NO_RACER) {
            s_dg_b_racer_only++;
            if (dg_line())
                fprintf(stderr, "[DIAG] contact A is traffic, B is racer %u (not offered): metric %.1f > %.1f (%.1f m/s)\n",
                        (unsigned)ib, metric, threshold, metric / CT_MPH);
        }
        return 0;                                        /* car A is not a racer: not a racer-vs-traffic contact */
    }
#if MUT != 201
    if (ib != BM_HOOK_NO_RACER) {
        s_st.skipped_racers++;                           /* racer vs racer: never offered */
        s_dg_racers++;
        return 0;
    }
#endif
    s_st.decisions++;
    if (!bo3_hk_point_wanted(BM_HOOK_TRAFFIC_CONTACT))
        return 0;
    ma = rd32(body_a + 0x204u);
    sa = rdf(body_a + 0xBCu);
    sb = bb ? rdf(bb + 0xC4u) : 0.0f;
    for (int k = 0; k < 3; k++) {
        va[k] = ma ? rdf(ma + 0x20u + 4u * (uint32_t)k) * sa : 0.0f;
        vb[k] = bb ? rdf(bb + 0x90u + 4u * (uint32_t)k) * sb : 0.0f;
    }
    dot = va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2];
    bo3_hk_ctx_v3(&c, BM_HOOK_TRAFFIC_CONTACT);
    c.contact_racer = ia;
    c.contact_traffic = ++s_seq;
    c.contact_closing_mps = (float)(metric / CT_MPH);
#if MUT == 203
    c.contact_same_dir = sa > 0.0f && sb > 0.0f;
#else
    c.contact_same_dir = dot > 0.0f;
#endif
    memset(&o, 0, sizeof o);
    o.output = BM_HOOK_OUT_CONTACT_OUTCOME;
    o.outcome = BM_CONTACT_GAME;
    o.push_scale = 1.0f;
    s_push_rec = 0;
    (void)threshold;
#if MUT == 205
    bo3_hk_dispatch_v3(BM_HOOK_TRAFFIC_CONTACT, &c, &o);
    return 1;
#else
    {
        int dr = bo3_hk_dispatch_v3(BM_HOOK_TRAFFIC_CONTACT, &c, &o);
        s_dg_dispatched++;
        if (dg_line())
            fprintf(stderr, "[DIAG] contact racer %u: closing %.1f m/s (metric %.1f > %.1f), same_dir %d (dot %.1f, speeds %.1f / %.1f)"
                    " -> dispatch %d outcome %u push %.2f\n", (unsigned)ia, (double)c.contact_closing_mps, metric, threshold,
                    (int)c.contact_same_dir, (double)dot, (double)sa, (double)sb, dr, (unsigned)o.outcome, (double)o.push_scale);
        if (!(dr && o.outcome == BM_CONTACT_NO_CRASH))
            return 0;
    }
    {
        s_st.no_crash++;
        s_dg_no_crash++;
        s_nc_rec = rec;                                  /* patch 110: the crash of this contact is skipped at loc_001133E9 */
        s_nc_clock = rd32(0x0060EA20u);
        if (BO3_HOOKREQ_P9C && push_census() && o.push_scale != 1.0f && o.push_scale >= 0.0f && o.push_scale <= 1.0f) {
            s_push_rec = rec;                            /* patch 79: for this contact's non-fatal response */
            s_push_clock = rd32(0x0060EA20u);
            s_push_scale = o.push_scale;
        }
        return 1;
    }
#endif
}

static uint8_t rd8(uint32_t va)
{
    uint8_t v = 0;
    return bo3_guest_read(va, &v, 1) ? v : 0;
}

static uint32_t racer_at(uint32_t i)
{
    uint32_t n = rd32(CT_RACE_COUNT);
    return i < n && i < CT_MAX_RACERS ? rd32(CT_RACE_LIST + 4u * i) : 0;
}

/* item 39: the credit proposal's check (after the framework's bounds) */
static int credit_valid(const bm_hook_ctx *c, const bm_hook_out *o)
{
    uint32_t vr;
    if (o->credit_racer == BM_HOOK_NO_RACER)
        return 1;
#if MUT != 209
    if (c->cause_victim >= CT_CLAIMS)
        return 0;
#endif
#if MUT != 206
    if (o->credit_racer == c->cause_victim)
        return 0;
#endif
    vr = racer_at(c->cause_victim);
    if (!vr || !racer_at(o->credit_racer))
        return 0;
#if MUT != 207
    if (rd8(vr + CT_CREDITED))
        return 0;                                        /* already credited for this wreck */
#endif
    return 1;
}

/* item 52: the game's best-known toucher at wreck time = the racer holding the newest live claim on this victim (the claim
 * processor's own test: time > 0 and the claimant's S + 0xC < time + 1.0 s), else BM_HOOK_NO_RACER */
static uint32_t pending_claimant(uint32_t idx)
{
    uint32_t n = rd32(CT_RACE_COUNT), best = BM_HOOK_NO_RACER;
    float bt = 0.0f;
    if (idx >= CT_CLAIMS)
        return BM_HOOK_NO_RACER;
    if (n > CT_MAX_RACERS)
        n = CT_MAX_RACERS;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = rd32(CT_RACE_LIST + 4u * i);
        float tc, now;
        if (!r || i == idx)
            continue;
        tc = rdf(r + CT_S + CT_CLAIM_T + 4u * idx);
        now = rdf(r + CT_S + 0xCu);
#if MUT != 210
        if (!(tc > 0.0f) || !(now < tc + 1.0f))
            continue;                                    /* no claim, or expired */
#endif
        if (best == BM_HOOK_NO_RACER || tc > bt) {
            best = i;
            bt = tc;
        }
    }
    return best;
}

/* item 39: a racer wrecked -> the credit MODIFY; an accepted credit is written as the game's own claim */
static uint32_t s_claims;
static void wreck_tap(uint32_t car, uint32_t idx)
{
    bm_hook_ctx c;
    bm_hook_out o;
    uint32_t cr, s;
    float tm;
    (void)car;
    if (!s_ok || idx == BM_HOOK_NO_RACER || !bo3_hk_point_modifiers(BM_HOOK_WRECK_CAUSE))
        return;
    bo3_hk_ctx_v3(&c, BM_HOOK_WRECK_CAUSE);
    c.cause_victim = idx;
    c.cause_aggressor = pending_claimant(idx);           /* item 52: the game's pending claimant (runtime m19_r2a: was always -1) */
    memset(&o, 0, sizeof o);
    o.output = BM_HOOK_OUT_WRECK_CREDIT;
    o.credit_racer = c.cause_aggressor;                  /* the value so far = the game's own choice */
    if (!bo3_hk_modify_v3(BM_HOOK_WRECK_CAUSE, &c, &o) || o.credit_racer == BM_HOOK_NO_RACER ||
        o.credit_racer == c.cause_aggressor)
        return;                                          /* unchanged: the game's own claim stands */
    if (!credit_valid(&c, &o) || !(cr = racer_at(o.credit_racer)))
        return;                                          /* checked again: the state may have moved during the callbacks */
    s = cr + CT_S;
    tm = rdf(cr + CT_RTIME);
#if MUT == 208
    tm = 0.0f;
#endif
    {
        uint8_t one = 1;
        if (bo3_guest_write(s + CT_CLAIM_T + 4u * idx, &tm, 4) && bo3_guest_write(s + CT_CLAIM_MARK + idx, &one, 1))
            s_claims++;
    }
}

uint32_t bo3_contact_claims(void)
{
    return s_claims;
}

void bo3_ct_gen_wreck_cause(uint32_t victim, uint32_t aggressor)
{
    bm_hook_ctx c;
    if (!s_ok)
        return;
    s_st.wreck_causes++;
    s_dg_wrecks++;
    if (dg_line())
        fprintf(stderr, "[DIAG] wreck: victim racer %d, aggressor racer %d\n", (int)racer_index(victim), (int)racer_index(aggressor));
    if (!bo3_hk_point_wanted(BM_HOOK_WRECK_CAUSE))
        return;
    bo3_hk_ctx_v3(&c, BM_HOOK_WRECK_CAUSE);
    c.cause_victim = racer_index(victim);
    c.cause_aggressor = racer_index(aggressor);
    bo3_hk_dispatch_v3(BM_HOOK_WRECK_CAUSE, &c, NULL);
}

void bo3_contact_init(void)
{
    s_push_ok = -1;                                      /* patch 79: re-check the push site */
    s_push_rec = 0;
    const uint32_t obs = 1u << BM_HOOK_OBSERVE, mod = 1u << BM_HOOK_MODIFY;
    s_ok = 0;
#if BO3_HOOKREQ_P23
    if (!census()) {
        fprintf(stderr, "[HOOKS] TRAFFIC_CONTACT / WRECK_CAUSE: the game's bytes at the marks differ from this build's census: "
                        "both UNAVAILABLE\n");
        return;
    }
    s_ok = bo3_hk_offer_point(BM_HOOK_TRAFFIC_CONTACT, obs | mod, NULL) == 0;
    if (bo3_hk_offer_point(BM_HOOK_WRECK_CAUSE, BM_P23_WRECK_CREDIT_VERIFIED ? (obs | mod) : obs,
                           BM_P23_WRECK_CREDIT_VERIFIED ? credit_valid : NULL) != 0)
        s_ok = 0;
    if (s_ok && BM_P23_WRECK_CREDIT_VERIFIED)
        bo3_e6_wreck_tap = wreck_tap;                    /* item 39: the credit window opens at each new wreck */
#else
    (void)obs;
    (void)mod;
    (void)census;
    (void)credit_valid;
    (void)wreck_tap;
#endif
}

int bo3_contact_available(void)
{
    return s_ok;
}

void bo3_contact_get_stats(bo3_contact_stats *out)
{
    if (out)
        *out = s_st;
}
