/*
 * bm_zdiag.c - main21 patch 107: DEV-ONLY diagnostics for the combined run (BO3_HOOKREQ_ZDIAG=ON builds only; a default build
 * compiles nothing of it; never a release). Nothing is written to guest memory. Logs go to stderr (the run's tee).
 *  1. zackypoo 11 (Single Event DJ silent?): the DJ state machine sub_00154800 forces state 0x0D (off) at its entry when any of
 *     obj + 0x62C != 0, [0x73A1C0] > 1, byte [0x5A3759] != 0, [0x463AF4] != 0. The mark at the entry (EBX = obj) logs the four
 *     values and the state obj + 0x5F4 whenever they change ("[DIAG] dj gate"; <= 24 lines a load) + a summary at load / race exit.
 *  2. zackypoo 04 (a) crash camera / (b) Air Ram data routes: both groups are registered tuning variables inside objects, not at
 *     fixed addresses - the crash camera block = [0x3FA644] + 0x2C30 (sub_00167220 -> sub_00160B90), the Air Ram object = the
 *     argument of sub_0010C5F0 (mark at its entry). Logged: the object addresses at each load (a new object per race or one for
 *     the session?) and every ValueDB copy (the tune mark at sub_001AF040) that lands in either object (the boot copy reaches
 *     them or not) -> decides whether a late-bound tune row can hold a plugin's value.
 */
#include <stdint.h>
#include <stdio.h>

#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
#include "bm_guest.h"
#include "bm_lifecycle.h"

static uint32_t rd32(uint32_t va) { uint32_t v = 0; bo3_guest_rd32(va, &v); return v; }
static uint8_t rd8(uint32_t va) { uint8_t v = 0; bo3_guest_read(va, &v, 1); return v; }

static uint32_t s_dj_last[5] = { 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu };
static uint32_t s_dj_calls, s_dj_off, s_dj_lines;
static uint32_t s_air_obj, s_air_calls, s_cam_hits, s_air_hits, s_copy_lines;

void bo3_zdiag_dj(uint32_t obj)
{
    uint32_t v[5];
    if (!obj)
        return;
    v[0] = rd8(obj + 0x62Cu);
    v[1] = rd32(0x0073A1C0u);
    v[2] = rd8(0x005A3759u);
    v[3] = rd32(0x00463AF4u);
    v[4] = rd32(obj + 0x5F4u);
    s_dj_calls++;
    if (v[0] || v[1] > 1u || v[2] || v[3])
        s_dj_off++;
    if ((v[0] != s_dj_last[0] || v[1] != s_dj_last[1] || v[2] != s_dj_last[2] || v[3] != s_dj_last[3] || v[4] != s_dj_last[4]) &&
        s_dj_lines < 24u) {
        s_dj_lines++;
        fprintf(stderr, "[DIAG] dj gate: obj %08x  +0x62C %u  [0x73A1C0] %u  [0x5A3759] %u  [0x463AF4] %u  -> %s  state %u\n",
                (unsigned)obj, (unsigned)v[0], (unsigned)v[1], (unsigned)v[2], (unsigned)v[3],
                (v[0] || v[1] > 1u || v[2] || v[3]) ? "OFF (forced 0x0D)" : "open", (unsigned)v[4]);
    }
    for (int i = 0; i < 5; i++)
        s_dj_last[i] = v[i];
}

void bo3_zdiag_airram(uint32_t obj)
{
    s_air_calls++;
    if (obj != s_air_obj)
        fprintf(stderr, "[DIAG] air ram: sub_0010C5F0 object %08x (was %08x), call %u\n", (unsigned)obj, (unsigned)s_air_obj,
                (unsigned)s_air_calls);
    s_air_obj = obj;
}

/* bm_tune.c: every 32-bit ValueDB copy the tune mark sees */
void bo3_zdiag_copy(uint32_t var_va)
{
    uint32_t cam = rd32(0x003FA644u), lo = cam ? cam + 0x2C30u : 0;
    const char *what = NULL;
    if (lo && var_va >= lo && var_va < lo + 0x400u) {
        what = "crash camera block";
        s_cam_hits++;
    } else if (s_air_obj && var_va >= s_air_obj && var_va < s_air_obj + 0x1000u) {
        what = "Air Ram object";
        s_air_hits++;
    }
    if (what && s_copy_lines++ < 48u)
        fprintf(stderr, "[DIAG] vdb copy into the %s: %08x (+0x%X) = %08x\n", what, (unsigned)var_va,
                (unsigned)(var_va - (what[0] == 'c' ? lo : s_air_obj)), (unsigned)rd32(var_va));
}

void bo3_zdiag_lifecycle(uint32_t kind)
{
    uint32_t cam;
    if (kind != BO3_LC_EV_LOAD_DONE && kind != BO3_LC_EV_RACE_EXIT)
        return;
    cam = rd32(0x003FA644u);
    fprintf(stderr, "[DIAG] zdiag (%s): dj calls %u (gate off %u); crash camera [0x3FA644] %08x block %08x first floats %08x %08x "
            "%08x %08x; Air Ram object %08x (calls %u); vdb copies into them: camera %u, Air Ram %u\n",
            kind == BO3_LC_EV_LOAD_DONE ? "load" : "race exit", (unsigned)s_dj_calls, (unsigned)s_dj_off, (unsigned)cam,
            (unsigned)(cam ? cam + 0x2C30u : 0), (unsigned)(cam ? rd32(cam + 0x2C30u) : 0), (unsigned)(cam ? rd32(cam + 0x2C34u) : 0),
            (unsigned)(cam ? rd32(cam + 0x2C38u) : 0), (unsigned)(cam ? rd32(cam + 0x2C3Cu) : 0), (unsigned)s_air_obj,
            (unsigned)s_air_calls, (unsigned)s_cam_hits, (unsigned)s_air_hits);
    s_dj_calls = s_dj_off = s_dj_lines = 0;
}
#else
void bo3_zdiag_lifecycle(uint32_t kind) { (void)kind; }
void bo3_zdiag_copy(uint32_t var_va) { (void)var_va; }
#endif
