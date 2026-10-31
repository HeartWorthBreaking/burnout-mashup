/*
 * bm_paints.c - gp slice paints1 EXPERIMENTAL: garage paint cap (the generated calls in bo3_paints_gen.h).
 * GP-P4.1: the cap is a player setting (bmashup.settings host setting, MODS > MOD SETTINGS), not an environment variable.
 *
 * Retail: the car-select paint button cycles (paint + 1) mod min(model palettes, 6) (sub_000BE140) and mirrors paint mod
 * min(photo palettes, 6) into the photo widget (sub_000BE1B0), so paints 7 / 8 (palette indices 6 / 7) of the 57 cars that
 * carry 8 palettes are never selectable. Facts (atlas CARS_FEASIBILITY.md s5): the chosen paint flows as a u32 through the race
 * set-up table 0x463BB0[player] into the vehicle record +0x69, which the model loader reduces mod the model's palette count
 * (sub_0018D0E0) and the renderer bounds by it (sub_000303D0); the photo widget indexes the photo's palette slots
 * (+0x14[paint], 8 slots, no bound: sub_000F9410), so the cap must never exceed the PHOTO's palette count; the paint is not part
 * of the saved profile (0x44CB20, 0x49C bytes) - no save-format limit. Palettes 7 / 8 are the team colours of the online team
 * modes (sub_0006DAC0 sets 6 / 7 from a team flag) - selecting them offline only changes the look.
 *
 * The configured cap, at every call (the page can change it while the garage is open):
 *   1. BMASHUP_GARAGE_PAINT_CAP=1..8 - a DEVELOPER override (tests, measurements): wins over the setting, logged once as such;
 *      anything else is ignored (logged once) and the setting decides;
 *   2. the host setting "bmashup.host/garage_paints_78" (BOOL "GARAGE PAINT 7-8", default OFF): ON -> 8, OFF -> 6 (retail);
 *   3. no setting (not declared: a test build, the settings registry full) -> 6 (retail).
 * Default OFF (P4_1_REPORT s4): palettes 7 / 8 are the game's online team colours (red / blue), not liveries the game offers
 * in the garage; the retail garage stays the default, the player opts in on the page, and turning it off is retail again.
 * The cap is then bounded by the photo's palette count read from guest memory through bm_guest (window-checked); when the photo
 * is not readable or has 0 palettes the game's constant is returned (retail behaviour).
 * Thread: the game thread (front end); the setting value is an atomic read. Lifetime: process. MUT=n (tests): one defect.
 */
#include "bo3_paints_gen.h"
#include "bm_guest.h"

#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

#define BM_PAINTS_MAX    8u                 /* palette slots of the D3D texture header (+0x14 .. +0x33) */
#define BM_PAINTS_RETAIL 6u

static int s_env = -2;                      /* -2 not read; -1 none / ignored; 1..8 the developer override */
static int (*s_setting)(int32_t *on);       /* the host setting's reader (bo3_bm_paints_init), NULL = none */
static int s_last = -1;                     /* the last cap logged */
static _Atomic uint32_t s_calls, s_retail, s_raised;

static int env_cap(void)
{
    if (s_env == -2) {
        const char *e = getenv("BMASHUP_GARAGE_PAINT_CAP");
        s_env = -1;
        if (e && *e) {
            char *end = NULL;
            long l = strtol(e, &end, 10);
            if (end && !*end && l >= 1 && l <= (long)BM_PAINTS_MAX) {
                s_env = (int)l;
                fprintf(stderr, "[PAINTS] developer override BMASHUP_GARAGE_PAINT_CAP=%d: the MOD SETTINGS value is not "
                        "used\n", s_env);
            } else {
                fprintf(stderr, "[PAINTS] BMASHUP_GARAGE_PAINT_CAP=\"%s\" ignored (not 1..8): the MOD SETTINGS value "
                        "decides\n", e);
            }
        }
    }
    return s_env;
}

static uint32_t configured_cap(void)
{
    int32_t on = 0;
    int c = env_cap();
    uint32_t cap;
#if MUT == 6
    c = -1;                                             /* defect: the developer override ignored */
#endif
    if (c > 0)
        cap = (uint32_t)c;
#if MUT == 5
    else if (0)                                         /* defect: the setting ignored */
#else
    else if (s_setting && s_setting(&on))
#endif
        cap = on ? BM_PAINTS_MAX : BM_PAINTS_RETAIL;
    else
        cap = BM_PAINTS_RETAIL;
    if ((int)cap != s_last) {
        s_last = (int)cap;
        fprintf(stderr, "[PAINTS] garage paint cap %u (%s; retail 6; bounded per car by its photo's palette count)\n",
                (unsigned)cap, c > 0 ? "developer override" : s_setting ? "MOD SETTINGS: GARAGE PAINT 7-8" : "no setting");
    }
    return cap;
}

uint32_t bo3_paint_gen_cap(uint32_t retail, uint32_t photo_va)
{
    uint8_t n = 0;
    uint32_t cap;
    atomic_fetch_add(&s_calls, 1);
#if MUT == 4
    cap = BM_PAINTS_MAX; (void)configured_cap;          /* defect: the configured cap (negative control 6) ignored */
#else
    cap = configured_cap();
#endif
#if MUT == 1
    (void)photo_va;
    atomic_fetch_add(&s_raised, 1);
    return cap;                                         /* defect: the photo's palette count not applied */
#else
    if (!photo_va || !bo3_guest_read(photo_va + 0x69u, &n, 1) || n == 0) {
        atomic_fetch_add(&s_retail, 1);
#if MUT == 2
        return cap;                                     /* defect: unreadable photo -> the raised cap */
#else
        return retail;                                  /* the game's own constant */
#endif
    }
#endif
#if MUT == 3
    if (n > cap) cap = n;                               /* defect: max instead of min */
#else
    if (n < cap) cap = n;
#endif
    if (cap < 1) cap = 1;
    if (cap > BM_PAINTS_MAX) cap = BM_PAINTS_MAX;
    if (cap > retail) atomic_fetch_add(&s_raised, 1);
    return cap;
}

/* The setting's reader (tests give their own; the game build: bo3_bm_paints_init). 1 = *on set, 0 = no setting. */
void bo3_paints_set_setting_reader(int (*fn)(int32_t *on))
{
    s_setting = fn;
}

#ifdef BO3_PAINTS_GAME   /* the game build (CMake): the host setting through bmashup.settings (bm_settings.c) */
#include "bm_settings.h"

static int host_setting(int32_t *on)
{
    return bo3_ps_host_get("garage_paints_78", on) == BM_SETTINGS_OK;
}

/* main.c, after bo3_bm_settings_init / bo3_ps_file and before the plugins start (host settings come first on the page). */
void bo3_bm_paints_init(void)
{
    bm_setting_decl d;
    int32_t v = 0, rc;
    memset(&d, 0, sizeof d);
    d.struct_size = (uint32_t)sizeof d;
    d.kind = BM_SETTING_BOOL;
    d.key = "garage_paints_78";
    d.label = "GARAGE PAINT 7-8";                       /* 16 = BM_SETTINGS_LABEL_MAX */
    d.def = 0;                                          /* OFF: retail (header comment) */
    rc = bo3_ps_host_declare(&d, &v);
    if (rc == BM_SETTINGS_OK)
        bo3_paints_set_setting_reader(host_setting);
    fprintf(stderr, "[PAINTS] garage paints 7 / 8 (the team colours): %s (MODS > MOD SETTINGS, BURNOUT MASHUP: GARAGE "
            "PAINT 7-8; developer override BMASHUP_GARAGE_PAINT_CAP)\n",
            rc != BM_SETTINGS_OK ? "setting not available: retail 6" : v ? "ON" : "OFF (retail 6)");
}
#endif

/* tests / diagnostics */
void bo3_paints_stats(uint32_t *calls, uint32_t *retail_returns, uint32_t *raised)
{
    if (calls) *calls = atomic_load(&s_calls);
    if (retail_returns) *retail_returns = atomic_load(&s_retail);
    if (raised) *raised = atomic_load(&s_raised);
}

void bo3_paints_reset_for_tests(void)
{
    s_env = -2;
    s_last = -1;
    s_setting = NULL;
    atomic_store(&s_calls, 0);
    atomic_store(&s_retail, 0);
    atomic_store(&s_raised, 0);
}
