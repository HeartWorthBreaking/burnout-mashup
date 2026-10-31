/*
 * bm_menu.c - main19 (platform 0.1.9, hook request P3, patches 32..34): "bmashup.menu" v1 (include/bmashup_menu.h).
 * Design gp\hookreq\HOOK_REQUEST_DESIGN.md D, sites gp\hookreq\p23\SITES_VERIFIED.md s8.1 - s8.3 (re-checked: tests\p23\
 * step0_c_out.txt: open sub_000CBE40 sets D + 0xA = 1, close sub_000CCC90 clears it, the poll sub_000CD2A0 reads it and answers
 * 15 while nothing is chosen; the retail call shapes at 0x86600 (ECX = D, AL = 0, push 5, choice2, choice1, msg, type) and at
 * 0x86800 (EDI = D, push 1, push port)).
 *
 * Patch 32 (D1 popup): declarations (checked against the plugin's own bmashup.settings declaration), UTF-16 texts in the guest
 * high zone at close, and the popup state machine (bo3_menu_popup_trigger / bo3_menu_popup_frame): opens the title's dialog
 * (type 7) only when D + 0xA == 0 (nobody else owns it), polls it once a frame, stores the answer, closes it only if it opened
 * it. Patch 45 WIRES it (PR-C / PR-F, p23_fa4 / p23_fb4): the car-select page's input handlers (vt 0x3AC044 slots 0 / 4) carry
 * the marks of bo3_menu_gen.h; see "patch 45" below. The open's stack order (5, choice 2, choice 1, message, type 7) and the
 * poll's controller -1 are PR-F facts.
 * Patch 33 (D2 mode row + option rows): declarations checked and kept (id, label, help, base ELIMINATOR only, contexts, up to 2
 * option settings = this plugin's GLOBAL INT / ENUM settings), texts copied with the popups'. NOT WIRED in 0.1.9: the SELECT MODE
 * list layout / the dispatch extension are not verified (probes PR-C, PR-E; step 0 found the option rows' record pointer at
 * O + 0x10, stride 0x14 - not codex's O + 0x28), so feature_available(MODE) answers 0 (BM_P23_MENU_MODE_ROUTE), no row is added
 * and active_mode() answers "". No mark is placed in the game code for it: a dispatch mark could only ever see the retail rows.
 * Patch 34 (D3 stat bars): declarations checked and kept (label <= 12 printable, a callback; <= 2 over all plugins);
 * bo3_menu_bar_value() is the seam a car-select draw will call (the value clamped: outside 0..1 or NaN -> not drawn). NOT WIRED in
 * 0.1.9: the car-select bar widget is not located (PR-C); the fallback (bars drawn with bmashup.hud v2's primitives on the
 * car-select page) needs the hud v2 draw path in the FRONT END, which hud v2 (patch 30) does not offer - feature_available(BARS)
 * answers 0 (BM_P23_MENU_BARS_SITE) and no callback is ever called.
 * BO3_HOOKREQ_P23 == 0: every call answers UNAVAILABLE.
 * MUT=n (tests): 1 opens over another owner's dialog (D + 0xA not checked)  2 closes a dialog it did not open
 *   3 World Tour context accepted  4 the text budget not checked  5 the answer of the second choice stored as the first
 *   6 a declaration after close accepted  7 a mode with a World Tour context / a non-ELIMINATOR base accepted
 *   8 an option that is not this plugin's GLOBAL INT / ENUM accepted  9 more than BM_MENU_MODES_MAX modes accepted
 *   10 a bar without a callback accepted  11 a third bar accepted  12 a value above 1 drawn (not clamped out)
 * main21 C3-5: MULTIPLAYER mode rows on the Multiplayer list (feature MODE_MP; see "C3-5" below; MUT 60..63).
 */
#include "bm_menu.h"

#include <stdio.h>
#include <string.h>

#include "bm_guest.h"
#include "bmashup_hud.h"
#include "bm_settings.h"
#include "plugins.h"
#include "recomp_types.h"

#ifndef MUT
#define MUT 0
#endif
#ifndef BO3_HOOKREQ_P23
#define BO3_HOOKREQ_P23 1           /* unit tests */
#endif

typedef struct {
    const td_host *host;
    char key[BM_SETTINGS_KEY_MAX + 1];
    char title[BM_MENU_TITLE_MAX + 1];
    char choice[2][BM_SETTINGS_CHOICE_MAX + 1];
    uint32_t contexts, kind;
    uint32_t va_title, va_c[2];     /* UTF-16 copies (0 until close) */
} popup_decl;

static popup_decl s_pop[BM_MENU_POPUPS_DECL_MAX];
static uint32_t s_npop;

typedef struct {                    /* patch 33 */
    const td_host *host;
    char id[25], label[BM_MENU_LABEL_MAX + 1], help[BM_MENU_HELP_MAX + 1];
    uint32_t base, contexts, n_options;
    char option[BM_MENU_MODE_OPTIONS_MAX][BM_SETTINGS_KEY_MAX + 1];
    uint32_t va_label, va_help;
} mode_decl;
static mode_decl s_mode[BM_MENU_MODES_MAX];
static uint32_t s_nmode;

typedef struct {                    /* patch 34 */
    const td_host *host;
    char label[13];
    bm_menu_bar_fn fn;
    void *user;
} bar_decl;
static bar_decl s_bar[BM_MENU_BARS_MAX];
static uint32_t s_nbar;
struct bm_hud_cmd;
static int (*s_bars_draw)(const struct bm_hud_cmd *cmds, uint32_t n);   /* item 47 (defined below) */
static int (*s_bars_car)(char *name, uint32_t room);
int bo3_menu_census_bars(void);
int bo3_menu_census_help(void);     /* main21 patch 114 (defined below) */
static uint32_t s_text_bytes;       /* the UTF-16 bytes every declaration needs */
static int s_closed, s_texts_ok;
static bo3_menu_ops s_ops;
static bo3_menu_alloc_fn s_alloc;
static bo3_menu_answer_fn s_answer;
static int s_census = -1;
static int s_census_mode = -1;     /* patch 43 */
static uint32_t s_route;           /* patch 43: 1 + the s_mode index of the accepted added row, 0 = a retail row / none */
static uint32_t s_row_mode[BO3_MENU_LIST_CAP];   /* patch 43: list row i (>= 4) -> s_mode index */
static void (*s_mode_race)(const td_host *owner);
static int s_census_mp = -1;       /* main21 C3-5 */
static uint32_t s_mp_route;        /* C3-5: 1 + the s_mode index of the accepted added MP row, 0 = a retail row / none */
static uint32_t s_mp_row_mode[BO3_MENU_LIST_CAP];   /* C3-5: MP list row i (>= 5) -> s_mode index */
static uint32_t s_mp_lines;        /* C3-5: "[MENU] MP row" lines (rate limit) */
#define MP_LINES_MAX 24u

/* the popup queue of one confirmation */
static int s_queue[BM_MENU_POPUPS_MAX];
static uint32_t s_nq, s_qpos, s_qplayer;
static int s_up;                    /* the host opened the dialog and has not closed it */

static int printable(const char *s, size_t max, int allow_empty)
{
    size_t n;
    if (!s)
        return 0;
    n = strlen(s);
    if ((!n && !allow_empty) || n > max)
        return 0;
    for (size_t i = 0; i < n; i++)
        if ((unsigned char)s[i] < 0x20 || (unsigned char)s[i] > 0x7E)
            return 0;
    return 1;
}

static uint32_t u16_bytes(const char *s) { return (uint32_t)(2u * (strlen(s) + 1u)); }

/* patch 43: the three mark sites, the retail row count store and the route's jump table / list vtable (XBE 9f497acd) */
int bo3_menu_census_mode(void)
{
    static const uint8_t rows[7] = { 0x8B, 0x4F, 0x04, 0x66, 0x8B, 0x57, 0x08 },             /* 0x766A4: the row loads from +4 / +8 of EDI */
                         accept[7] = { 0x8B, 0x15, 0xAC, 0x95, 0x55, 0x00, 0x4A },           /* 0x69F5D: the load of the count at 0x5595AC and its decrement */
                         route[19] = { 0xC7, 0x05, 0x88, 0x47, 0x4D, 0x00, 0x40, 0x4B, 0x4D, 0x00, 0x8B, 0x4E, 0x18, 0x89, 0x0D,
                                       0x7C, 0x46, 0x4D, 0x00 },                                  /* 0x5F514 the Race case */
                         count4[10] = { 0xC7, 0x05, 0xA8, 0x95, 0x55, 0x00, 0x04, 0x00, 0x00, 0x00 },  /* 0x6A04B [0x5595A8] = 4 */
                         jt0[4] = { 0x14, 0xF5, 0x05, 0x00 }, vt0[4] = { 0x40, 0x67, 0x07, 0x00 };   /* 0x5F794[0], 0x3ABE1C[0] */
    uint8_t a[7], b[7], c[19], d[10], e[4], f[4];
    if (s_census_mode < 0)
        s_census_mode = bo3_guest_read(0x000766A4u, a, 7) && !memcmp(a, rows, 7) && bo3_guest_read(0x00069F5Du, b, 7) &&
                        !memcmp(b, accept, 7) && bo3_guest_read(0x0005F514u, c, 19) && !memcmp(c, route, 19) &&
                        bo3_guest_read(0x0006A04Bu, d, 10) && !memcmp(d, count4, 10) && bo3_guest_read(0x0005F794u, e, 4) &&
                        !memcmp(e, jt0, 4) && bo3_guest_read(0x003ABE1Cu, f, 4) && !memcmp(f, vt0, 4);
    return s_census_mode;
}

/* main21 C3-5: the Multiplayer list's rows mark, accept, route, the retail count store and the jump tables (XBE 9f497acd; notes\
 * C3_5_MP_ROWS_RE.md s3.5) */
int bo3_menu_census_mp(void)
{
    static const struct { uint32_t va; uint8_t n; uint8_t b[24]; } rows[] = {
        { 0x0007A0F4u, 10, { 0x8B, 0x4F, 0x04, 0x66, 0x8B, 0x57, 0x08, 0x8D, 0x47, 0x4E } },          /* rows mark site */
        { 0x0006C54Fu, 11, { 0xA1, 0x68, 0xC4, 0x55, 0x00, 0x48, 0x83, 0xF8, 0x03, 0x77, 0x6B } },     /* accept switch */
        { 0x0005F846u, 24, { 0xC7, 0x05, 0x50, 0x49, 0x4D, 0x00, 0x54, 0x4E, 0x4D, 0x00, 0x8B, 0x4E, 0x18, 0x83, 0xF9, 0x04,
                             0x89, 0x0D, 0x44, 0x48, 0x4D, 0x00, 0x7E, 0x0B } },                            /* MP Race case */
        { 0x0006C6ECu, 16, { 0x61, 0xC5, 0x06, 0x00, 0x77, 0xC5, 0x06, 0x00, 0x7F, 0xC5, 0x06, 0x00, 0xAB, 0xC5, 0x06, 0x00 } },
        { 0x0005FB04u, 4, { 0x46, 0xF8, 0x05, 0x00 } },                                                 /* MP set-up table [0] */
        { 0x0005E9ECu, 4, { 0x0B, 0xE9, 0x05, 0x00 } },                                                 /* 0x5E9E4[2] */
        { 0x0006C7B2u, 10, { 0xC7, 0x05, 0x64, 0xC4, 0x55, 0x00, 0x05, 0x00, 0x00, 0x00 } },          /* [0x55C464] = 5 */
    };
    uint8_t a[24];
    if (s_census_mp < 0) {
        s_census_mp = 1;
        for (size_t i = 0; i < sizeof rows / sizeof rows[0]; i++)
            if (!bo3_guest_read(rows[i].va, a, rows[i].n) || memcmp(a, rows[i].b, rows[i].n))
                s_census_mp = 0;
    }
    return s_census_mp;
}

int bo3_menu_census(void)
{
    static const uint8_t open_site[16] = { 0x52, 0x57, 0x6A, 0x07, 0x32, 0xC0, 0xB9, 0xA0, 0x0D, 0x55, 0x00, 0xE8, 0x30, 0x58,
                                           0x04, 0x00 };
    static const uint8_t poll_head[5] = { 0x8A, 0x47, 0x0A, 0x84, 0xC0 }, close_clr[4] = { 0xC6, 0x46, 0x0A, 0x00 },
                         open_set[4] = { 0xC6, 0x47, 0x0A, 0x01 };
    /* patch 45: the two marked input handlers of the car-select page (vt 0x3AC044 slots 0 / 4; XBE 9f497acd) */
    static const uint8_t in0[11] = { 0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF8, 0xA1, 0x64, 0x7A, 0x55, 0x00 },
                         in4[7] = { 0x83, 0x3D, 0x64, 0x7A, 0x55, 0x00, 0x05 }, vt[8] = { 0xF0, 0x1A, 0x07, 0x00, 0x00, 0x25, 0x07, 0x00 };
    uint8_t a[16], b[5], c[4], d[4], e[11], f[7], v0[4], v4[4];
    if (s_census < 0)
        s_census = bo3_guest_read(0x00086600u, a, 16) && !memcmp(a, open_site, 16) && bo3_guest_read(0x000CD2A0u, b, 5) &&
                   !memcmp(b, poll_head, 5) && bo3_guest_read(0x000CCCA4u, c, 4) && !memcmp(c, close_clr, 4) &&
                   bo3_guest_read(0x000CBE5Au, d, 4) && !memcmp(d, open_set, 4) &&
                   bo3_guest_read(0x00071AF0u, e, 11) && !memcmp(e, in0, 11) && bo3_guest_read(0x00072500u, f, 7) &&
                   !memcmp(f, in4, 7) && bo3_guest_read(0x003AC044u, v0, 4) && !memcmp(v0, vt, 4) &&
                   bo3_guest_read(0x003AC054u, v4, 4) && !memcmp(v4, vt + 4, 4);
    return s_census;
}

static uint32_t TD_CALL m_available(td_host *host, uint32_t feature)
{
    (void)host;
    if (!BO3_HOOKREQ_P23)
        return 0;
    switch (feature) {
    case BM_MENU_FEATURE_POPUP:
        return BM_P23_MENU_POPUP_SITE && s_texts_ok && bo3_menu_census() ? 1u : 0u;
    case BM_MENU_FEATURE_MODE:
        return BM_P23_MENU_MODE_ROUTE && s_texts_ok && bo3_menu_census_mode() ? 1u : 0u;
    case BM_MENU_FEATURE_BARS:
        return BM_P23_MENU_BARS_SITE && s_bars_draw && s_bars_car && bo3_menu_census_bars() ? 1u : 0u;   /* item 47 */
    case BM_MENU_FEATURE_HELP:                      /* main21 patch 114: drawn at the list-line render site (was patch 88: the bars' site) */
#if MUT == 40
        return BO3_HOOKREQ_P13H && BM_P23_MENU_BARS_SITE && s_bars_draw && bo3_menu_census_bars() &&
               BM_P23_MENU_MODE_ROUTE && s_texts_ok && bo3_menu_census_mode() ? 1u : 0u;
#else
        return BO3_HOOKREQ_P13H && s_bars_draw && bo3_menu_census_help() &&
               BM_P23_MENU_MODE_ROUTE && s_texts_ok && bo3_menu_census_mode() ? 1u : 0u;
#endif
    case BM_MENU_FEATURE_MODE_MP:                   /* main21 C3-5 */
        return BO3_HOOKREQ_ZMPR && BM_P23_MENU_MODE_ROUTE && s_texts_ok && bo3_menu_census_mp() ? 1u : 0u;
    default:
        return 0;
    }
}

static int contexts_ok(uint32_t c)
{
#if MUT == 3
    return c != 0;
#else
    return c != 0 && !(c & ~(uint32_t)(BM_MENU_CTX_SINGLE_EVENT | BM_MENU_CTX_MULTIPLAYER));   /* never World Tour (2) */
#endif
}

static int32_t TD_CALL m_declare_popup(td_host *host, const bm_menu_popup_decl *d)
{
    popup_decl p;
    uint32_t kind = 0, scope = 0, n = 0, need;
    if (!BO3_HOOKREQ_P23)
        return BM_MENU_UNAVAILABLE;
    if (!host || !d || d->struct_size < sizeof *d)
        return BM_MENU_BAD_ARG;
#if MUT != 6
    if (s_closed)
        return BM_MENU_CLOSED;
#endif
    if (!contexts_ok(d->contexts))
        return BM_MENU_BAD_ARG;
    if (!printable(d->title, BM_MENU_TITLE_MAX, 0) || !d->setting_key)
        return BM_MENU_BAD_TEXT;
    memset(&p, 0, sizeof p);
    if (!bo3_ps_query(host, d->setting_key, &kind, &scope, &n, p.choice))
        return BM_MENU_UNKNOWN_SETTING;
    if (scope != BM_SETTING_SCOPE_PER_PLAYER || !(kind == BM_SETTING_BOOL || (kind == BM_SETTING_ENUM && n >= 2u)))
        return BM_MENU_WRONG_SETTING;
    for (uint32_t i = 0; i < s_npop; i++)
        if (s_pop[i].host == host && !strcmp(s_pop[i].key, d->setting_key))
            return BM_MENU_DUPLICATE;
    if (s_npop >= BM_MENU_POPUPS_DECL_MAX)
        return BM_MENU_FULL;
    if (kind == BM_SETTING_BOOL) {
        snprintf(p.choice[0], sizeof p.choice[0], "YES");
        snprintf(p.choice[1], sizeof p.choice[1], "NO");
    }
    if (!printable(p.choice[0], BM_SETTINGS_CHOICE_MAX, 0) || !printable(p.choice[1], BM_SETTINGS_CHOICE_MAX, 0))
        return BM_MENU_BAD_TEXT;
    need = u16_bytes(d->title) + u16_bytes(p.choice[0]) + u16_bytes(p.choice[1]);
#if MUT != 4
    if (s_text_bytes + need > BO3_MENU_TEXT_BUDGET)
        return BM_MENU_FULL;
#endif
    p.host = host;
    snprintf(p.key, sizeof p.key, "%s", d->setting_key);
    snprintf(p.title, sizeof p.title, "%s", d->title);
    p.contexts = d->contexts;
    p.kind = kind;
    s_pop[s_npop++] = p;
    s_text_bytes += need;
    return BM_MENU_OK;
}

static int id_ok(const char *s)
{
    size_t n = s ? strlen(s) : 0;
    if (!n || n > 24)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '_'))
            return 0;
    return 1;
}

static int32_t TD_CALL m_declare_mode(td_host *host, const bm_menu_mode_decl *d)
{
    mode_decl m;
    uint32_t need;
    if (!BO3_HOOKREQ_P23)
        return BM_MENU_UNAVAILABLE;
    if (!host || !d || d->struct_size < sizeof *d)
        return BM_MENU_BAD_ARG;
#if MUT != 6
    if (s_closed)
        return BM_MENU_CLOSED;
#endif
#if MUT != 7
    if (!contexts_ok(d->contexts))
        return BM_MENU_BAD_ARG;
    if (d->base != BM_MENU_BASE_ELIMINATOR)
        return BM_MENU_UNAVAILABLE;             /* v1: ELIMINATOR is the only base */
#endif
    if (!id_ok(d->id) || !printable(d->label, BM_MENU_LABEL_MAX, 0) || !printable(d->help ? d->help : "", BM_MENU_HELP_MAX, 1))
        return BM_MENU_BAD_TEXT;
    if (d->n_options > BM_MENU_MODE_OPTIONS_MAX || (d->n_options && !d->option_keys))
        return BM_MENU_BAD_ARG;
    memset(&m, 0, sizeof m);
    for (uint32_t k = 0; k < d->n_options; k++) {
        uint32_t kind = 0, scope = 0, n = 0;
        if (!d->option_keys[k] || !bo3_ps_query(host, d->option_keys[k], &kind, &scope, &n, NULL))
            return BM_MENU_UNKNOWN_SETTING;
#if MUT != 8
        if (scope != BM_SETTING_SCOPE_GLOBAL || (kind != BM_SETTING_INT && kind != BM_SETTING_ENUM))
            return BM_MENU_WRONG_SETTING;
#endif
        snprintf(m.option[k], sizeof m.option[k], "%s", d->option_keys[k]);
    }
    for (uint32_t i = 0; i < s_nmode; i++)
        if (s_mode[i].host == host && !strcmp(s_mode[i].id, d->id))
            return BM_MENU_DUPLICATE;
#if MUT != 9
    if (s_nmode >= BM_MENU_MODES_MAX)
        return BM_MENU_FULL;
#else
    if (s_nmode >= BM_MENU_MODES_MAX + 1u)
        return BM_MENU_FULL;
#endif
    need = u16_bytes(d->label) + u16_bytes(d->help ? d->help : "");
    if (s_text_bytes + need > BO3_MENU_TEXT_BUDGET)
        return BM_MENU_FULL;
    m.host = host;
    snprintf(m.id, sizeof m.id, "%s", d->id);
    snprintf(m.label, sizeof m.label, "%s", d->label);
    snprintf(m.help, sizeof m.help, "%s", d->help ? d->help : "");
    m.base = d->base;
    m.contexts = d->contexts;
    m.n_options = d->n_options;
    if (s_nmode < BM_MENU_MODES_MAX)
        s_mode[s_nmode] = m;
    s_nmode++;
    s_text_bytes += need;
    return BM_MENU_OK;
}

uint32_t bo3_menu_mode_count(void) { return s_nmode; }

static int32_t TD_CALL m_declare_bar(td_host *host, const bm_menu_bar_decl *d)
{
    if (!BO3_HOOKREQ_P23)
        return BM_MENU_UNAVAILABLE;
    if (!host || !d || d->struct_size < sizeof *d)
        return BM_MENU_BAD_ARG;
    if (s_closed)
        return BM_MENU_CLOSED;
#if MUT != 10
    if (!d->fn)
        return BM_MENU_BAD_ARG;
#endif
    if (!printable(d->label, 12, 0))
        return BM_MENU_BAD_TEXT;
    for (uint32_t i = 0; i < s_nbar && i < BM_MENU_BARS_MAX; i++)
        if (s_bar[i].host == host && !strcmp(s_bar[i].label, d->label))
            return BM_MENU_DUPLICATE;
#if MUT != 11
    if (s_nbar >= BM_MENU_BARS_MAX)
        return BM_MENU_FULL;
#endif
    if (s_nbar < BM_MENU_BARS_MAX) {
        s_bar[s_nbar].host = host;
        snprintf(s_bar[s_nbar].label, sizeof s_bar[s_nbar].label, "%s", d->label);
        s_bar[s_nbar].fn = d->fn;
        s_bar[s_nbar].user = d->user;
    }
    s_nbar++;
    return BM_MENU_OK;
}

/* the seam for the car-select draw (not called in 0.1.9): bar i's value for vehicle, 1 and *v in 0..1, or 0 (not drawn) */
int bo3_menu_bar_value(uint32_t i, const char *vehicle, float *v)
{
    float f;
    if (i >= s_nbar || i >= BM_MENU_BARS_MAX || !s_bar[i].fn || !vehicle || !v)
        return 0;
    f = s_bar[i].fn(vehicle, s_bar[i].user);
#if MUT == 12
    if (!(f >= 0.0f))
        return 0;
#else
    if (!(f >= 0.0f && f <= 1.0f))  /* also NaN */
        return 0;
#endif
    *v = f;
    return 1;
}

static uint32_t g32(uint32_t va);

/* ---- item 47 (D3 reduced form): the declared bars on car select, drawn with bmashup.hud v2's executor ----
 * Where: the end of the front-end 2D render callback sub_000B6F90 (mark bo3_mbars_gen.h; the best candidate found offline - it
 * draws with the title's rect primitive and front-end textures; owner 2026-10-28: proven by a car-select screenshot), at most
 * once a picture (main.c: bo3_menu_bars_flip), only while the front end's page is the car select (0x559648) in its input phase 5.
 * What: per declared bar (<= 2): its label (TEXT 10), a dark track and the value's fill (QUADs) at x 48..248, y 300 + 40 i
 * (640 x 480 units); the value = the plugin's callback for player 0's chosen car (the 8-byte id at 0x740B00 that sub_000C0080
 * reads, through GP-CARS2's donor map and the base-40 name, trailing spaces cut: e.g. "COMPCAR1"); a value outside 0..1 -> that
 * bar is not drawn. MUT (tests): 23 drawn on another page  24 drawn twice in a picture  25 drawn outside the input phase.
 * Item 57 (round 4: no bars on screen at sub_000B6F90): the mark moved to the exit of sub_000F6DC0 (0xF76FF), the render callback of
 * the front end's generic text elements (built by sub_000F68E0, also by the dialog code 0xCB040..0xCB5F0 whose texts were visible
 * over the car select in round 3); the guard (page 0x559648, phase 5) is the one patch 45's popup uses on that page (round 3: shown). */
static int (*s_bars_draw)(const struct bm_hud_cmd *cmds, uint32_t n);
static int (*s_bars_car)(char *name, uint32_t room);
static uint32_t s_bars_pic, s_bars_done = 0xFFFFFFFFu;
static int s_census_bars = -1;

void bo3_menu_set_bars_io(int (*draw)(const struct bm_hud_cmd *cmds, uint32_t n), int (*car)(char *name, uint32_t room))
{
    s_bars_draw = draw;
    s_bars_car = car;
}

int bo3_menu_census_bars(void)
{
    static const uint8_t site[10] = { 0x33, 0xF6, 0xE8, 0xE1, 0x0B, 0x0D, 0x00, 0x5F, 0x5E, 0x5B },        /* item 57: 0xF76F8 exit */
                         car[23] = { 0x8B, 0xB4, 0x24, 0x24, 0x01, 0x00, 0x00, 0x8B, 0xC6, 0x69, 0xC0, 0x70, 0x24, 0x00, 0x00,
                                     0x8B, 0x88, 0x04, 0x0B, 0x74, 0x00, 0x8B, 0x90 };                  /* 0xC0089 id read */
    uint8_t a[10], b[23];
    if (s_census_bars < 0)
        s_census_bars = bo3_guest_read(0x000F76F8u, a, 10) && !memcmp(a, site, 10) && bo3_guest_read(0x000C0089u, b, 23) &&
                        !memcmp(b, car, 23);
    return s_census_bars;
}

void bo3_menu_bars_flip(void) { s_bars_pic++; }

/* item 59 (DEV probe m19_bp1, FACT: the mark at sub_000F6DC0 runs on the car select, phase 5 holds, but [0x740B00] = FFFFFFFF:
 * FFFFFFFF there -> the decoded name was garbage, the callback refused it, nothing drawn): the car on show = the preview record of
 * the car-select carousel, REC0 0x73F190 + 0x2470 * (s8)[0x55609E], its 8-byte id at + 0x1970 (bm_vpaint.c's verified source: the
 * garage paint registry compares the selected row's car with it; sub_000BE140 indexes 0x73F1E0 by the same slot). 0 = none.
 * MUT 26 (tests): a negative slot accepted */
uint64_t bo3_menu_bars_car_id(void)
{
    int8_t slot = 0;
    uint32_t rec;
    uint64_t id;
    if (!bo3_guest_read(0x0055609Eu, &slot, 1))
        return 0;
#if MUT != 26
    if (slot < 0)
        return 0;
#endif
    rec = 0x0073F190u + 0x2470u * (uint32_t)(int32_t)slot;
    id = ((uint64_t)g32(rec + 0x1970u + 4u) << 32) | g32(rec + 0x1970u);
    return id == ~(uint64_t)0 ? 0 : id;
}

/* main21 patch 88 (open-list item 9): the help line and option values of an ADDED Single Event mode row. FACTS (static, XBE
 * 9f497acd): the retail SELECT MODE list (page 0x5595A4, set-up sub_000765E0) shows no per-row description - its texts are
 * SELECT MODE / RACE / TIME ATTACK / ROAD RAGE / CRASH (ids 0x149..0x150) and the set-up's only other call with a constant
 * (sub_000D4700 0x550CB0, 0x105) is the button bar every list page passes; the event descriptions 0xFF..0x10A belong to World
 * Tour's SELECT EVENT page. So the host draws them: while the list page is current in its input phase and the widget's selection
 * [L + 0x4E] (u16; the set-up writes it, the accept handler sub_00076740 reads it) is an added row, the declared help (wrapped,
 * upper case: the dot font) and each declared option as "LABEL: value" (bo3_ps_value_text; changed on the MOD SETTINGS page),
 * with bmashup.hud v2's executor at patch 87's site (sub_000F6DC0 exit), once a picture. Switch BO3_HOOKREQ_P13H.
 * MUT (tests): 27 drawn outside the input phase  28 drawn twice in a picture  29 a retail row (< 4) gets the help
 * main21 patch 114 (probe R27 FAIL in C1): FACT (C1 log, patch 111's [DIAG] fe text mark): the sub_000F6DC0 exit ran only on pages
 * 0x55CB88 / 0x559648 / 0x559F8C / 0, never while SELECT MODE was current (FACT fb_006: the page shows no help line and no ticker);
 * FACT (static): its set-up sub_000765E0 builds no generic text element (sub_000F68E0, which installs sub_000F6DC0) - its rows are
 * the list widget's (sub_000F0EA0 -> sub_000F1160, which installs the line render callback sub_000F29B0 per line, `push 0xF29B0`
 * at 0xF1228). So the help is drawn from both exits of sub_000F29B0 (marks BO3_MENU_HELP_DRAW_LL, bo3_mbars_gen.h), through
 * bo3_menu_gen_help_draw, with the same guards and once a picture; HELP no longer needs the car-select bars' site or census.
 * HYPOTHESIS until a run: sub_000F29B0 runs every picture while the list is on screen. MUT 39 census skipped  40 HELP still needs
 * the bars' site  41 the bars' site draws the help too */
#define HELP_CHARS 60u
static uint32_t s_help_done = 0xFFFFFFFFu;
static int s_census_help = -1;

int bo3_menu_census_help(void)
{
    static const uint8_t push[5] = { 0x68, 0xB0, 0x29, 0x0F, 0x00 },                         /* 0xF1228 push 0xF29B0 */
                         ex1[10] = { 0x83, 0xC4, 0x0C, 0x5F, 0x5E, 0x5B, 0x8B, 0xE5, 0x5D, 0xC3 }, /* 0xF2CB8: the function's epilogue */
                         ex2[7] = { 0x5F, 0x5E, 0x5B, 0x8B, 0xE5, 0x5D, 0xC3 };               /* 0xF2E5A pops; ret */
    uint8_t a[10], b[7], c[5];
#if MUT == 39
    return 1;
#endif
    if (s_census_help < 0)
        s_census_help = bo3_guest_read(0x000F1228u, c, 5) && !memcmp(c, push, 5) && bo3_guest_read(0x000F2CB8u, a, 10) &&
                        !memcmp(a, ex1, 10) && bo3_guest_read(0x000F2E5Au, b, 7) && !memcmp(b, ex2, 7);
    return s_census_help;
}

static void help_upper(char *d, const char *s, size_t n)
{
    size_t k = 0;
    for (; s[k] && k + 1 < n; k++)
        d[k] = (s[k] >= 'a' && s[k] <= 'z') ? (char)(s[k] - 32) : s[k];
    d[k] = 0;
}

/* 1 = the SE list page (handled here, whatever was drawn); 0 = another page */
static int help_draw(void)
{
    static char lines[4][BM_MENU_HELP_MAX + BM_SETTINGS_CHOICE_MAX + 8];
    bm_hud_cmd c[4];
    uint32_t n = 0, nh, sel, cnt, m;
    if (!BO3_HOOKREQ_P13H || g32(BO3_MENU_FE_PAGE) != BO3_MENU_PG_SE_LIST)
        return 0;
#if MUT != 27
    if (g32(BO3_MENU_FE_PHASE) != 5u)
        return 1;
#endif
    if (!m_available(NULL, BM_MENU_FEATURE_HELP))
        return 1;
#if MUT != 28
    if (s_help_done == s_bars_pic)
        return 1;
#endif
    s_help_done = s_bars_pic;
    cnt = g32(BO3_MENU_PG_SE_LIST + 4u);
    sel = g32(BO3_MENU_PG_SE_LIST + 0x4Eu) & 0xFFFFu;
#if MUT != 29
    if (sel < BO3_MENU_SE_LIST_ROWS)
        return 1;
#endif
    if (sel >= cnt || sel >= BO3_MENU_LIST_CAP || (m = s_row_mode[sel]) >= s_nmode)
        return 1;
    if (s_mode[m].help[0]) {                         /* the help: at most 2 lines, cut at a space */
        char up[BM_MENU_HELP_MAX + 1];
        const char *p = up;
        help_upper(up, s_mode[m].help, sizeof up);
        for (int l = 0; l < 2 && *p; l++) {
            size_t k = strlen(p);
            if (k > HELP_CHARS) {
                k = HELP_CHARS;
                while (k > HELP_CHARS / 2 && p[k] != ' ')
                    k--;
                if (p[k] != ' ')
                    k = HELP_CHARS;
            }
            snprintf(lines[n], sizeof lines[n], "%.*s", (int)k, p);
            p += k;
            while (*p == ' ')
                p++;
            n++;
        }
    }
    nh = n;
    for (uint32_t o = 0; o < s_mode[m].n_options && o < BM_MENU_MODE_OPTIONS_MAX && n < 4u; o++) {
        char t[sizeof lines[0]];
        if (bo3_ps_value_text(s_mode[m].host, s_mode[m].option[o], t, sizeof t)) {
            help_upper(lines[n], t, sizeof lines[n]);
            n++;
        }
    }
    if (!n)
        return 1;
    memset(c, 0, sizeof c);
    for (uint32_t i = 0; i < n; i++) {
        c[i].struct_size = (uint32_t)sizeof c[i];
        c[i].kind = BM_HUD_CMD_TEXT;
        c[i].x = 48.0f; c[i].y = 384.0f + 14.0f * (float)i; c[i].text = lines[i]; c[i].text_size = 9.0f;
        c[i].rgba = i < nh ? 0xFFFFFFFFu : 0xF0C020FFu;      /* help white, options yellow */
    }
    {
        int ok = s_bars_draw(c, n);
        static int s_said;
        if (!s_said) {
            s_said = 1;
            fprintf(stderr, "[MENU] SE list: help / options of mode \"%s\" (%u line(s)) %s\n", s_mode[m].id, (unsigned)n,
                    ok ? "drawn" : "NOT drawn (executor off)");
        }
    }
    return 1;
}

/* main21 patch 111 (probe R27 "help not seen", DEV ONLY: BO3_HOOKREQ_ZDIAG builds; a default build compiles nothing of it): no run
 * ever logged help_draw's one-time "[MENU] SE list" line, so one of its early exits holds on SELECT MODE (this mark not reached on
 * that page, the page id, phase 5, the selection < 4 or not an added row). Logs the front-end page, phase, list count / selection
 * and the help feature's availability whenever they change at this mark (<= 32 lines a process).
 * Patch 114: site 1 = the list-line mark (sub_000F29B0), its own "[DIAG] list line mark" lines and change state. */
#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
static void help_diag(int site)
{
    static uint32_t last2[2][4] = { { 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu },
                                    { 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu } }, lines2[2];
    uint32_t *last = last2[site & 1], v[4];
    v[0] = g32(BO3_MENU_FE_PAGE);
    v[1] = g32(BO3_MENU_FE_PHASE);
    v[2] = v[0] == BO3_MENU_PG_SE_LIST ? g32(BO3_MENU_PG_SE_LIST + 4u) : 0u;
    v[3] = v[0] == BO3_MENU_PG_SE_LIST ? (g32(BO3_MENU_PG_SE_LIST + 0x4Eu) & 0xFFFFu) : 0u;
    if ((v[0] != last[0] || v[1] != last[1] || v[2] != last[2] || v[3] != last[3]) && lines2[site & 1] < 32u) {
        lines2[site & 1]++;
        fprintf(stderr, "[DIAG] %s mark: page %08x%s phase %u count %u sel %u, help feature %u, modes %u\n",
                site ? "list line" : "fe text", (unsigned)v[0],
                v[0] == BO3_MENU_PG_SE_LIST ? " (SE list)" : "", (unsigned)v[1], (unsigned)v[2], (unsigned)v[3],
                (unsigned)m_available(NULL, BM_MENU_FEATURE_HELP), (unsigned)s_nmode);
    }
    for (int i = 0; i < 4; i++)
        last[i] = v[i];
}
#endif

/* main21 patch 114: the list-line render mark (sub_000F29B0's two exits): the mode-row help only (never the car-select bars) */
void bo3_menu_gen_help_draw(void)
{
#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
    help_diag(1);
#endif
    (void)help_draw();
}

void bo3_menu_gen_bars_draw(void)
{
    bm_hud_cmd c[3 * BM_MENU_BARS_MAX];
    char name[32];
    uint32_t n = 0;
#if defined(BO3_HOOKREQ_ZDIAG) && BO3_HOOKREQ_ZDIAG
    help_diag(0);
#endif
#if MUT == 41
    if (help_draw())                                 /* patch 88's call (patch 114: the list-line site draws the help) */
        return;
#endif
    if (!BO3_HOOKREQ_P23 || !BM_P23_MENU_BARS_SITE || !s_nbar || !s_bars_draw || !s_bars_car || !bo3_menu_census_bars())
        return;
#if MUT != 23
    if (g32(BO3_MENU_FE_PAGE) != BO3_MENU_PG_CARSEL)
        return;
#endif
#if MUT != 25
    if (g32(BO3_MENU_FE_PHASE) != 5u)
        return;
#endif
#if MUT != 24
    if (s_bars_done == s_bars_pic)
        return;
#endif
    s_bars_done = s_bars_pic;
    if (!s_bars_car(name, (uint32_t)sizeof name)) {
        static int s_said_car;
        if (!s_said_car) {                         /* item 59: runtime evidence when no car is known */
            s_said_car = 1;
            fprintf(stderr, "[MENU] car select: bars not drawn - no car on show (preview slot / id unreadable)\n");
        }
        return;
    }
    for (uint32_t i = 0; i < s_nbar && i < BM_MENU_BARS_MAX; i++) {
        float v, y = 300.0f + 40.0f * (float)i;
        if (!bo3_menu_bar_value(i, name, &v)) {
            /* main21 patch 87: m19_bp1 showed "bar value refused" 96 times with no line in the normal log; one line per car */
            static char s_said_name[32];
            static uint32_t s_said_n;
            if (s_said_n < 8u && strcmp(s_said_name, name)) {
                float raw = s_bar[i].fn ? s_bar[i].fn(name, s_bar[i].user) : -1.0f;
                s_said_n++;
                snprintf(s_said_name, sizeof s_said_name, "%s", name);
                fprintf(stderr, "[MENU] car select: bar %u \"%s\" not drawn for car \"%s\": the plugin's value %.3f is outside 0..1\n",
                        (unsigned)i, s_bar[i].label, name, (double)raw);
            }
            continue;
        }
        memset(&c[n], 0, 3 * sizeof c[0]);
        for (int k = 0; k < 3; k++)
            c[n + (uint32_t)k].struct_size = (uint32_t)sizeof c[0];
        c[n].kind = BM_HUD_CMD_TEXT;
        c[n].x = 48.0f; c[n].y = y; c[n].text = s_bar[i].label; c[n].text_size = 10.0f; c[n].rgba = 0xFFFFFFFFu;
        c[n + 1].kind = BM_HUD_CMD_QUAD;
        c[n + 1].x = 48.0f; c[n + 1].y = y + 14.0f; c[n + 1].w = 200.0f; c[n + 1].h = 10.0f; c[n + 1].rgba = 0x202020C0u;
        c[n + 2].kind = BM_HUD_CMD_QUAD;
        c[n + 2].x = 48.0f; c[n + 2].y = y + 14.0f; c[n + 2].w = 200.0f * v; c[n + 2].h = 10.0f; c[n + 2].rgba = 0xF0C020FFu;
        n += 3;
    }
    if (n) {
        int ok = s_bars_draw(c, n);
        static int s_said;
        if (!s_said) {                             /* item 57: one line of runtime evidence */
            s_said = 1;
            fprintf(stderr, "[MENU] car select: %u bar command(s) for %s %s\n", (unsigned)n, name, ok ? "drawn" : "NOT drawn (executor off)");
        }
    }
}

static int32_t TD_CALL m_active_mode(td_host *host, char *id, uint32_t room)
{
    uint32_t mod, logic;
    if (!host || !id || !room)
        return BM_MENU_BAD_ARG;
    id[0] = 0;
    if (!BO3_HOOKREQ_P23)
        return BM_MENU_UNAVAILABLE;
    /* patch 43: the added row the Single Event in play came from (its logic object is the Eliminator) */
    mod = g32(0x004D5370u);
    logic = mod ? g32(mod + 0x1B8u) : 0;
    if (g32(BO3_MENU_SE_SETTINGS + 4u) == 2u) {      /* main21 C3-5: a Multiplayer race ([S + 4] = 2): the MP route only */
        if (s_mp_route && s_mp_route <= s_nmode && s_mp_route <= BM_MENU_MODES_MAX && logic == BO3_MENU_ELIM_LOGIC &&
                s_mode[s_mp_route - 1u].host == host)
            snprintf(id, room, "%s", s_mode[s_mp_route - 1u].id);
        return BM_MENU_OK;
    }
    if (s_route && s_route <= s_nmode && s_route <= BM_MENU_MODES_MAX && logic == BO3_MENU_ELIM_LOGIC &&
            s_mode[s_route - 1u].host == host)
        snprintf(id, room, "%s", s_mode[s_route - 1u].id);
    return BM_MENU_OK;
}

static const bm_menu_api s_api = { (uint32_t)sizeof(bm_menu_api), BM_MENU_VERSION, m_declare_popup, m_declare_mode,
                                   m_declare_bar, m_active_mode, m_available };

const bm_menu_api *bo3_bm_menu_api(void) { return &s_api; }

/* ---- texts: UTF-16 copies in the guest high zone, made once at close ---- */
static uint32_t put_u16(uint32_t va, const char *s)
{
    uint16_t w[64];
    size_t n = strlen(s);
    for (size_t i = 0; i <= n && i < 64; i++)
        w[i] = (uint16_t)(unsigned char)s[i];
    return bo3_guest_write(va, w, (uint32_t)(2u * (n + 1u))) ? va : 0;
}

void bo3_bm_menu_close(void)
{
    uint32_t base, at;
    s_closed = 1;
    if ((!s_npop && !s_nmode) || !BO3_HOOKREQ_P23)
        return;
    base = s_alloc ? s_alloc(s_text_bytes, 16u) : 0;
    if (!base) {
        fprintf(stderr, "[MENU] bmashup.menu: no high-zone memory for %u bytes of popup texts: popups off\n", (unsigned)s_text_bytes);
        return;
    }
    at = base;
    for (uint32_t i = 0; i < s_npop; i++) {
        s_pop[i].va_title = put_u16(at, s_pop[i].title);
        at += u16_bytes(s_pop[i].title);
        for (int c = 0; c < 2; c++) {
            s_pop[i].va_c[c] = put_u16(at, s_pop[i].choice[c]);
            at += u16_bytes(s_pop[i].choice[c]);
        }
    }
    for (uint32_t i = 0; i < s_nmode && i < BM_MENU_MODES_MAX; i++) {
        s_mode[i].va_label = put_u16(at, s_mode[i].label);
        at += u16_bytes(s_mode[i].label);
        s_mode[i].va_help = put_u16(at, s_mode[i].help);
        at += u16_bytes(s_mode[i].help);
    }
    s_texts_ok = 1;
}

/* ---- the popup state machine ---- */
int bo3_menu_popup_trigger(uint32_t context, uint32_t player)
{
    if (!m_available(NULL, BM_MENU_FEATURE_POPUP) || s_nq || player > 1u || !contexts_ok(context))
        return 0;
    for (uint32_t i = 0; i < s_npop && s_nq < BM_MENU_POPUPS_MAX; i++)
        if (s_pop[i].contexts & context)
            s_queue[s_nq++] = (int)i;
    s_qpos = 0;
    s_qplayer = player;
    return (int)s_nq;
}

static uint8_t d_active(void)
{
    uint8_t a = 1;                  /* unreadable: as if someone else owned it */
    bo3_guest_read(BO3_MENU_DIALOG + BO3_MENU_D_ACTIVE, &a, 1);
    return a;
}

int bo3_menu_popup_frame(uint32_t port)
{
    popup_decl *p;
    uint32_t r;
    if (s_qpos >= s_nq) {
        s_nq = s_qpos = 0;
        return 0;
    }
    p = &s_pop[s_queue[s_qpos]];
    if (!s_up) {
#if MUT != 1
        if (d_active())
            return 0;               /* the title (or another owner) has the dialog: wait */
#endif
        if (!s_ops.open)
            return 0;
        s_ops.open(7u, p->va_title, p->va_c[0], p->va_c[1]);
        s_up = 1;
        return 1;
    }
    r = s_ops.poll ? s_ops.poll(port) : BO3_MENU_PENDING;
    if (r == BO3_MENU_PENDING)
        return 1;
    if (r == 4u || r == 5u) {       /* type 7: 4 = the first choice, 5 = the second (result table 0x3EBC98) */
#if MUT == 5
        int32_t v = 0;
#else
        int32_t v = r == 4u ? (p->kind == BM_SETTING_BOOL ? 1 : 0) : (p->kind == BM_SETTING_BOOL ? 0 : 1);
#endif
        if (s_answer)
            s_answer(p->host, p->key, s_qplayer, v);
        else
            fprintf(stderr, "[MENU] popup \"%s\": answer %d (player %u)\n", p->title, (int)v, (unsigned)s_qplayer);
    }
#if MUT == 2
    if (s_ops.close)
        s_ops.close();
#else
    if (s_up && d_active() && s_ops.close)
        s_ops.close();              /* only the dialog the host opened, and only while it is still open */
#endif
    s_up = 0;
    s_qpos++;
    return 1;
}

/* ---- patch 45: the live popup on the car-select page ----
 * Trigger: the player's A press on the car-select page (phase 5) in the Single Event flow (the SE list page was the last list
 * page shown, bo3_menu_fe_flip), once per visit of the page, when a declared popup has the SINGLE_EVENT context: that frame the
 * page does not see its input (so the press does not confirm the car), the queue starts. While the queue runs, slot 0 drives the
 * dialog once a frame (bo3_menu_popup_frame: open / poll with every pad / close) and both input slots are skipped; after the last
 * answer the page keeps being skipped until every pad's A is released (no stale press), then the page runs as before and the
 * player's next A confirms the car. The answers go to the plugin's PER_PLAYER setting (player 0; bo3_ps_set_player).
 * Not served: the Multiplayer flow (its list page is not verified -> MULTIPLAYER popups never trigger), World Tour (by design),
 * player 1 (R6). MUT (tests): 13 the trigger without the Single Event flow  14 slot 4 not skipped while the dialog is up
 * 15 no drain (the page runs while A is still held)  16 triggers twice in one visit  17 polls from slot 4 too */
enum { LV_IDLE = 0, LV_RUN = 1, LV_DRAIN = 2 };
static uint32_t s_lv, s_lv_page, s_lv_se, s_lv_done, s_lv_aprev;

static uint32_t g32(uint32_t va)
{
    uint32_t v = 0;
    return bo3_guest_read(va, &v, 4) ? v : 0;
}

static int any_a(void)
{
    for (uint32_t p = 0; p < 4u; p++) {
        uint32_t rec = BO3_MENU_PADS + 0x20u * p;
        uint8_t a = 0;
        if (g32(rec) == 2u && g32(rec + 4u) && bo3_guest_read(rec + BO3_MENU_PAD_A, &a, 1) && a > 30u)
            return 1;
    }
    return 0;
}

void bo3_menu_fe_flip(void)
{
    uint32_t pg;
    if (!BO3_HOOKREQ_P23 || !s_texts_ok)
        return;
    pg = g32(BO3_MENU_FE_PAGE);
    if (pg == s_lv_page)
        return;
    if (pg == BO3_MENU_PG_SE_LIST)
        s_mp_route = 0;                              /* main21 C3-5: the Single Event flow: no Multiplayer route survives it */
    if (pg == BO3_MENU_PG_SE_LIST)
        s_lv_se = 1;                                 /* the Single Event flow starts */
    else if (pg != BO3_MENU_PG_SE_OPTS && pg != BO3_MENU_PG_CARSEL && pg != 0u)
        s_lv_se = 0;                                 /* any other page ends it (Multiplayer / World Tour / main menu ...) */
    if (s_lv_page == BO3_MENU_PG_CARSEL && pg != BO3_MENU_PG_CARSEL)
        s_lv_done = 0;                               /* a new visit of the car select may show the popups again */
    if (pg == BO3_MENU_PG_CARSEL)
        s_lv_aprev = 1;                              /* an A still held from the page before is not a press here */
    s_lv_page = pg;
}

uint32_t bo3_menu_live_state(void) { return s_lv; }

uint32_t bo3_menu_gen_page_input(uint32_t slot)
{
    int a;
    if (!m_available(NULL, BM_MENU_FEATURE_POPUP))
        return 0;
    if (g32(BO3_MENU_FE_PAGE) != BO3_MENU_PG_CARSEL || g32(BO3_MENU_FE_PHASE) != 5u)
        return s_lv != LV_IDLE ? 1u : 0u;            /* not this page's input frame: keep owning only if we already do */
    a = any_a();
    if (s_lv == LV_IDLE) {
        if (slot != 0u)
            return 0;
#if MUT == 16
        if (a && !s_lv_aprev) {
#elif MUT == 13
        if (!s_lv_done && a && !s_lv_aprev) {
#else
        if (s_lv_se && !s_lv_done && a && !s_lv_aprev) {
#endif
            s_lv_done = 1;
            s_lv_aprev = 1;
            if (bo3_menu_popup_trigger(BM_MENU_CTX_SINGLE_EVENT, 0u) > 0) {
                s_lv = LV_RUN;
                fprintf(stderr, "[MENU] car select: %u popup(s) after the player's confirm\n", (unsigned)s_nq);
                return 1;                            /* the page does not see this A */
            }
            return 0;
        }
        s_lv_aprev = (uint32_t)a;
        return 0;
    }
    if (s_lv == LV_RUN) {
#if MUT == 17
        if (1) {
#else
        if (slot == 0u) {
#endif
            if (s_qpos >= s_nq) {                    /* the last popup was answered last frame */
                bo3_menu_popup_frame(BO3_MENU_ALL_PADS);   /* empties the queue */
                s_lv = LV_DRAIN;
            } else {
                bo3_menu_popup_frame(BO3_MENU_ALL_PADS);   /* open (when the dialog is free) / poll / close */
            }
        }
#if MUT == 14
        return slot == 0u ? 1u : 0u;
#else
        return 1;
#endif
    }
#if MUT == 15
    s_lv = LV_IDLE;
    s_lv_aprev = (uint32_t)a;
    return 0;
#else
    if (slot == 0u && !a) {                          /* drained: every pad's A released */
        s_lv = LV_IDLE;
        s_lv_aprev = 0;
        return 0;
    }
    return 1;
#endif
}

/* ---- patch 43: ELIMINATOR mode rows in the Single Event SELECT MODE list ----
 * Rows: every declared mode with the SINGLE_EVENT context (<= BM_MENU_MODES_MAX = 4, plugin start order) becomes list row 4, 5, ...
 * (the page holds 10). At the end of the list set-up's row loop (sub_000765E0, only for the SE list page with its retail count 4)
 * each row gets the host label (UTF-16, high zone), enabled, its flags cleared, its id slot = "RACE" (any id lookup stays valid),
 * and the count grows; the widget's copies (count = the down-move bound, selection) are made by the title right after. The row
 * last routed is pre-selected when the title pre-selects Race. Accept (sub_00069E40's dispatch): a row >= 4 falls to the title's
 * own Race selector (0x463AF8 = 0, XBE 0x69F6C) and the host remembers the mode; any retail row clears it. Set-up
 * (sub_0005F4A0's Race case, S = 0x463AF0 only): the remembered mode routes the race to the Eliminator logic 0x4D4BD8 with 5 laps
 * and tells bmashup.rules which plugin owns it (claim_race). Not served: help texts, option rows (declared, not shown), the
 * Multiplayer list (unverified), World Tour (by design).
 * MUT (tests): 18 rows added to a list whose count is not the retail 4  19 a retail row keeps the route  20 the route without the
 * settings check  21 rows written while MODE is unavailable  22 the logic routed without the lap count */
static void mp_rows(uint32_t page);

void bo3_menu_gen_list_rows(uint32_t page)
{
    uint32_t n, k = 0, sel;
    if (page == BO3_MENU_PG_MP_LIST) {               /* main21 C3-5: the Multiplayer list (its own mark at loc_0007A0F4) */
        mp_rows(page);
        return;
    }
    if (page != BO3_MENU_PG_SE_LIST)
        return;
#if MUT != 21
    if (!m_available(NULL, BM_MENU_FEATURE_MODE))
        return;
#endif
    n = g32(page + 4u);
#if MUT != 18
    if (n != BO3_MENU_SE_LIST_ROWS)
        return;                                      /* not the retail list (or rows added already): unchanged */
#endif
    for (uint32_t m = 0; m < s_nmode && m < BM_MENU_MODES_MAX; m++) {
        uint32_t i = BO3_MENU_SE_LIST_ROWS + k, id = BO3_MENU_ROW_TEXT_ID, zero = 0;
        uint8_t z = 0;
        if (!(s_mode[m].contexts & BM_MENU_CTX_SINGLE_EVENT) || !s_mode[m].va_label || i >= BO3_MENU_LIST_CAP)
            continue;
        if (!bo3_guest_write(page + 0x54u + 8u * i, &s_mode[m].va_label, 4) || !bo3_guest_write(page + 0x58u + 8u * i, &zero, 2) ||
                !bo3_guest_write(page + 0x38u + i, &z, 1) || !bo3_guest_write(page + 0x42u + i, &z, 1) ||
                !bo3_guest_write(page + 0x10u + 4u * i, &id, 4))
            return;
        s_row_mode[i] = m;
        k++;
    }
    if (!k)
        return;
    n = BO3_MENU_SE_LIST_ROWS + k;
    bo3_guest_write(page + 4u, &n, 4);
    sel = g32(page + 8u);
    if (s_route && sel == 0u)
        for (uint32_t i = BO3_MENU_SE_LIST_ROWS; i < n; i++)
            if (s_row_mode[i] + 1u == s_route) {
                bo3_guest_write(page + 8u, &i, 4);   /* the row routed last time, as the title pre-selects its last mode */
                break;
            }
}

void bo3_menu_gen_se_accept(uint32_t row)
{
    uint32_t n = g32(BO3_MENU_PG_SE_LIST + 4u);
    if (row >= BO3_MENU_SE_LIST_ROWS && row < n && row < BO3_MENU_LIST_CAP && m_available(NULL, BM_MENU_FEATURE_MODE)) {
        s_route = s_row_mode[row] + 1u;
        fprintf(stderr, "[MENU] SELECT MODE: added row %u \"%s\" (mode %s) -> the Race selector, routed at the set-up\n",
                (unsigned)row, s_mode[s_row_mode[row]].label, s_mode[s_row_mode[row]].id);
        return;
    }
#if MUT != 19
    s_route = 0;
#endif
}

void bo3_menu_gen_se_route(uint32_t settings)
{
    uint32_t logic = BO3_MENU_ELIM_LOGIC, laps = BO3_MENU_ELIM_LAPS;
    const mode_decl *m;
#if MUT != 20
    if (settings != BO3_MENU_SE_SETTINGS)
        return;
#endif
    if (!s_route || s_route > s_nmode || s_route > BM_MENU_MODES_MAX || !m_available(NULL, BM_MENU_FEATURE_MODE))
        return;
    m = &s_mode[s_route - 1u];
    if (!bo3_guest_write(BO3_MENU_LOGIC_SLOT, &logic, 4))
        return;
#if MUT != 22
    bo3_guest_write(BO3_MENU_LAPS, &laps, 4);
#endif
    if (s_mode_race)
        s_mode_race(m->host);
    fprintf(stderr, "[MENU] Single Event set-up: mode %s -> the Eliminator logic, %u laps\n", m->id, (unsigned)laps);
}

/* ---- main21 C3-5 (open-list item 9, MP part; notes\C3_5_MP_ROWS_RE.md): MULTIPLAYER mode rows on the Multiplayer list ----
 * Rows: every declared mode with the MULTIPLAYER context becomes row 5, 6, ... of page 0x55C460 (sub_0006C720 fills 5 rows, then
 * tail-jumps to sub_0007A030; mark at loc_0007A0F4 after the row loop, the widget's count / selection copies follow). Each row:
 * the host label, greyed = page + 0x4C (the set-up's "<= 1 pad" byte, so exactly when the 2-player rows are greyed), flag + 0x42 = 1
 * ("needs 2 pads", as rows 0..3), + 0x38 = 0, id slot "RACE", the count grows; only at the retail count 5. The row routed last is
 * pre-selected when the title pre-selects row 0. Accept (sub_0006C410 loc_0006C54F): a row >= 5 falls to the game's own Race
 * selector (0x463AFC = 0) and the host remembers the mode; any retail row clears it. Set-up (sub_0005F7B0's Race case, S =
 * 0x463AF0, [S + 4] = 2 Multiplayer, [S + 0xC] = 0 Race): the remembered mode routes the 2-player race to the Eliminator logic
 * 0x4D4BD8 ([0x4D4950], the 2-player stage + 0x1B8) and tells bmashup.rules the owner (claim_race); the rival count stays the
 * player's (the game's clamp <= 4 follows). Not served: help lines (guarded to the SE page), HUD layout id (6, single-screen
 * Eliminator: probe), player-2 services (notes s5). MUT (tests): 60 an added row never greyed  61 a retail MP row keeps the route
 * 62 the MP route without the [S + 4] / [S + 0xC] checks  63 rows added at a count other than the retail 5 */
static void mp_rows(uint32_t page)
{
    uint32_t n, k = 0, sel, id = BO3_MENU_ROW_TEXT_ID;
    uint8_t grey = 1, z = 0, one = 1;
    if (!m_available(NULL, BM_MENU_FEATURE_MODE_MP))
        return;
    n = g32(page + 4u);
#if MUT != 63
    if (n != BO3_MENU_MP_LIST_ROWS) {
        if (s_mp_lines < MP_LINES_MAX) {
            s_mp_lines++;
            fprintf(stderr, "[MENU] MP row build: list count %u is not the retail 5 - no row added\n", (unsigned)n);
        }
        return;
    }
#endif
    if (!bo3_guest_read(page + 0x4Cu, &grey, 1))
        return;
#if MUT == 60
    grey = 0;
#endif
    for (uint32_t m = 0; m < s_nmode && m < BM_MENU_MODES_MAX; m++) {
        uint32_t i = n + k;
        if (!(s_mode[m].contexts & BM_MENU_CTX_MULTIPLAYER) || !s_mode[m].va_label || i >= BO3_MENU_LIST_CAP)
            continue;
        if (!bo3_guest_write(page + 0x54u + 8u * i, &s_mode[m].va_label, 4) || !bo3_guest_write(page + 0x58u + 8u * i, &grey, 1) ||
                !bo3_guest_write(page + 0x59u + 8u * i, &z, 1) || !bo3_guest_write(page + 0x38u + i, &z, 1) ||
                !bo3_guest_write(page + 0x42u + i, &one, 1) || !bo3_guest_write(page + 0x10u + 4u * i, &id, 4))
            return;
        s_mp_row_mode[i] = m;
        k++;
    }
    if (!k)
        return;
    n += k;
    bo3_guest_write(page + 4u, &n, 4);
    sel = g32(page + 8u);
    if (s_mp_route && sel == 0u)
        for (uint32_t i = BO3_MENU_MP_LIST_ROWS; i < n; i++)
            if (s_mp_row_mode[i] + 1u == s_mp_route) {
                bo3_guest_write(page + 8u, &i, 4);
                break;
            }
    if (s_mp_lines < MP_LINES_MAX) {
        s_mp_lines++;
        fprintf(stderr, "[MENU] MP row build: + %u row(s) after the 5 retail rows (count %u, %s, selected %u)\n", (unsigned)k,
                (unsigned)n, grey ? "greyed: <= 1 pad" : "enabled", (unsigned)g32(page + 8u));
    }
}

void bo3_menu_gen_mp_accept(uint32_t row)
{
    uint32_t n = g32(BO3_MENU_PG_MP_LIST + 4u);
    if (row >= BO3_MENU_MP_LIST_ROWS && row < n && row < BO3_MENU_LIST_CAP && s_mp_row_mode[row] < s_nmode &&
            s_mp_row_mode[row] < BM_MENU_MODES_MAX && (s_mode[s_mp_row_mode[row]].contexts & BM_MENU_CTX_MULTIPLAYER) &&
            m_available(NULL, BM_MENU_FEATURE_MODE_MP)) {
        s_mp_route = s_mp_row_mode[row] + 1u;
        if (s_mp_lines < MP_LINES_MAX) {
            s_mp_lines++;
            fprintf(stderr, "[MENU] MP row accept: row %u \"%s\" (mode %s) -> the Race selector, routed at the 2-player set-up\n",
                    (unsigned)row, s_mode[s_mp_row_mode[row]].label, s_mode[s_mp_row_mode[row]].id);
        }
        return;
    }
#if MUT != 61
    if (s_mp_route && s_mp_lines < MP_LINES_MAX) {
        s_mp_lines++;
        fprintf(stderr, "[MENU] MP row accept: row %u (retail / not an added row) - the MP route cleared\n", (unsigned)row);
    }
    s_mp_route = 0;
#endif
}

void bo3_menu_gen_mp_route(uint32_t settings)
{
    uint32_t logic = BO3_MENU_ELIM_LOGIC;
    const mode_decl *m;
    if (settings != BO3_MENU_SE_SETTINGS || !s_mp_route)
        return;
#if MUT != 62
    if (g32(settings + 4u) != 2u || g32(settings + 0xCu) != 0u) {
        if (s_mp_lines < MP_LINES_MAX) {
            s_mp_lines++;
            fprintf(stderr, "[MENU] MP row route: not routed (game mode %u, MP mode %u: not the Multiplayer Race)\n",
                    (unsigned)g32(settings + 4u), (unsigned)g32(settings + 0xCu));
        }
        return;
    }
#endif
    if (s_mp_route > s_nmode || s_mp_route > BM_MENU_MODES_MAX || !m_available(NULL, BM_MENU_FEATURE_MODE_MP))
        return;
    m = &s_mode[s_mp_route - 1u];
    if (!bo3_guest_write(BO3_MENU_MP_LOGIC_SLOT, &logic, 4))
        return;
    if (s_mode_race)
        s_mode_race(m->host);
    if (s_mp_lines < MP_LINES_MAX) {
        s_mp_lines++;
        fprintf(stderr, "[MENU] MP row route: mode %s -> the Eliminator logic in the 2-player stage (rivals asked %u, the game clamps to <= 4)\n",
                m->id, (unsigned)g32(settings + 0x18u));
    }
}

uint32_t bo3_menu_mp_route_mode(void) { return s_mp_route; }

uint32_t bo3_menu_route_mode(void) { return s_route; }
void bo3_menu_set_rules(void (*mode_race)(const td_host *owner)) { s_mode_race = mode_race; }

void bo3_menu_set_ops(const bo3_menu_ops *ops)
{
    if (ops)
        s_ops = *ops;
    else
        memset(&s_ops, 0, sizeof s_ops);
}
void bo3_menu_set_alloc(bo3_menu_alloc_fn a) { s_alloc = a; }

/* ---- main21 patch 93 (open-list item 18): MOD SETTINGS in the single-player pause menu ----
 * STATIC facts (default.xbe 9f497acd): the pause build sub_00085F70 fills page P (EBX) rows at P + 8 + 8 i {u32 UTF-16 text,
 * u8, u8} and actions at P + 0x44 + 4 i; P + 6 = the row count (u16), P + 4 = the selection (u16); its online branch
 * (P + 0x60 != 0) writes 7 rows (P + 8 .. P + 0x38: the capacity, P + 0x40 follows), the single-player branch 3..6 rows; both
 * reach loc_0008621E. The input handler sub_000863F0 reads the action [P + 0x44 + 4 sel] at loc_000864D4 and dispatches 0..5
 * through the table 0x867E4; above 5 it takes its default 0x867C1 (no action). So: at loc_0008621E a single-player menu with
 * fewer than 7 rows gets a last row "MOD SETTINGS" (host UTF-16 text) with action 6, and at loc_000864D4 action 6 asks the
 * overlay to open its MOD SETTINGS page (modsmenu_ov.c); the game stays paused (the overlay pauses the title itself) and the
 * pause menu is there again when the overlay closes. No overlay (headless, RECOMP_OVERLAY=0, BMASHUP_MODS_UI=native): no row.
 * Own census of both sites. MUT (tests): 36 the row added to the online menu  37 a 7-row menu overflowed  38 another action opens */
static int (*s_pause_open)(void);
static uint32_t s_pause_label, s_pause_rows, s_pause_opens;
static int s_pause_census = -1;
void bo3_menu_set_pause_open(int (*open_settings)(void)) { s_pause_open = open_settings; }
uint32_t bo3_menu_pause_stat(uint32_t which) { return which ? s_pause_opens : s_pause_rows; }   /* 0 rows added, 1 opens */

static int pause_census(void)
{
    static const uint8_t join[12] = { 0x8B, 0x0D, 0x2C, 0x53, 0x4D, 0x00, 0x8B, 0x51, 0x0C, 0x8A, 0x4B, 0x60 },   /* 0x8621E */
                         acc[13] = { 0x8B, 0x44, 0x86, 0x44, 0x83, 0xF8, 0x05, 0x0F, 0x87, 0xE0, 0x02, 0x00, 0x00 },  /* 0x864D4 */
                         cnt[4] = { 0x66, 0x89, 0x73, 0x06 };                                                       /* 0x8621A */
    uint8_t a[12], b[13], c[4];
    if (s_pause_census < 0)
        s_pause_census = bo3_guest_read(0x0008621Eu, a, 12) && !memcmp(a, join, 12) && bo3_guest_read(0x000864D4u, b, 13) &&
                         !memcmp(b, acc, 13) && bo3_guest_read(0x0008621Au, c, 4) && !memcmp(c, cnt, 4);
    return s_pause_census;
}

void bo3_menu_gen_pause_row(uint32_t page)
{
    uint16_t n = 0;
    uint8_t online = 1, z = 0;
    uint32_t act = BO3_MENU_PAUSE_ACTION;
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P22M || !s_pause_open || !pause_census() || !page)
        return;
    if (!bo3_guest_read(page + 0x60u, &online, 1) || !bo3_guest_read(page + 6u, &n, 2))
        return;
#if MUT != 36
    if (online)
        return;                                      /* the online pause menu: 7 rows already */
#endif
#if MUT != 37
    if (n >= 7u)
        return;
#endif
    if (!s_pause_label) {
        uint32_t va = s_alloc ? s_alloc(u16_bytes("MOD SETTINGS"), 16u) : 0;
        s_pause_label = va ? put_u16(va, "MOD SETTINGS") : 0;
        if (!s_pause_label)
            return;
    }
    if (!bo3_guest_write(page + 8u + 8u * n, &s_pause_label, 4) || !bo3_guest_write(page + 12u + 8u * n, &z, 1) ||
            !bo3_guest_write(page + 13u + 8u * n, &z, 1) || !bo3_guest_write(page + 0x44u + 4u * n, &act, 4))
        return;
    n++;
    bo3_guest_write(page + 6u, &n, 2);
    if (!s_pause_rows++)
        fprintf(stderr, "[MENU] pause menu: + MOD SETTINGS (row %u, the overlay's MOD SETTINGS page)\n", (unsigned)(n - 1u));
}

void bo3_menu_gen_pause_accept(uint32_t action)
{
#if MUT == 38
    if (!BO3_HOOKREQ_P23 || !s_pause_open)
#else
    if (!BO3_HOOKREQ_P23 || !BO3_HOOKREQ_P22M || action != BO3_MENU_PAUSE_ACTION || !s_pause_open)
#endif
        return;
    if (s_pause_open())
        s_pause_opens++;
    else
        fprintf(stderr, "[MENU] pause menu: MOD SETTINGS - the overlay is not available\n");
}
void bo3_menu_set_answer(bo3_menu_answer_fn fn) { s_answer = fn; }

void bo3_menu_reset(void)
{
    memset(s_pop, 0, sizeof s_pop);
    s_npop = s_text_bytes = 0;
    memset(s_mode, 0, sizeof s_mode);
    s_nmode = 0;
    memset(s_bar, 0, sizeof s_bar);
    s_nbar = 0;
    s_bars_draw = NULL;
    s_bars_car = NULL;
    s_bars_pic = 0;
    s_bars_done = 0xFFFFFFFFu;
    s_census_bars = -1;
    s_census_help = -1;                              /* main21 patch 114 */
    s_help_done = 0xFFFFFFFFu;                       /* main21 patch 114: the picture count restarts at 0 above */
    s_closed = s_texts_ok = 0;
    s_nq = s_qpos = s_qplayer = 0;
    s_up = 0;
    s_census = -1;
    s_lv = s_lv_page = s_lv_se = s_lv_done = s_lv_aprev = 0;
    s_census_mode = -1;
    s_route = 0;
    memset(s_row_mode, 0, sizeof s_row_mode);
    s_census_mp = -1;                                /* main21 C3-5 */
    s_mp_route = s_mp_lines = 0;
    memset(s_mp_row_mode, 0, sizeof s_mp_row_mode);
    s_help_done = 0xFFFFFFFFu;
    s_pause_census = -1;                            /* main21 patch 93 */
    s_mode_race = NULL;
    memset(&s_ops, 0, sizeof s_ops);
    s_alloc = NULL;
    s_answer = NULL;
}

#ifdef BO3_MENU_GAME
#include "bm_rules.h"
/* the retail call shapes; every guest register put back (bm_boost.c's pattern) */
extern void sub_000CBE40(void);
extern void sub_000CD2A0(void);
extern void sub_000CCC90(void);

#define SAVE uint32_t a_ = g_eax, b_ = g_ebx, c_ = g_ecx, d_ = g_edx, si_ = g_esi, di_ = g_edi, sp_ = g_esp, bp_ = g_ebp; \
    RecompXmm x_[8] = { g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7 }; int top_ = g_fp_top
#define RESTORE g_eax = a_; g_ebx = b_; g_ecx = c_; g_edx = d_; g_esi = si_; g_edi = di_; g_esp = sp_; g_ebp = bp_; \
    g_xmm0 = x_[0]; g_xmm1 = x_[1]; g_xmm2 = x_[2]; g_xmm3 = x_[3]; g_xmm4 = x_[4]; g_xmm5 = x_[5]; g_xmm6 = x_[6]; \
    g_xmm7 = x_[7]; g_fp_top = top_

static void game_open(uint32_t type, uint32_t msg, uint32_t c1, uint32_t c2)
{
    SAVE;
    g_ecx = BO3_MENU_DIALOG;
    g_eax &= 0xFFFFFF00u;                       /* AL = 0 (no suppression), as 0x86604 */
    PUSH32(g_esp, 5u);
    PUSH32(g_esp, c2);
    PUSH32(g_esp, c1);
    PUSH32(g_esp, msg);
    PUSH32(g_esp, type);
    PUSH32(g_esp, 0);                           /* the return address its ret 20 takes */
    sub_000CBE40();
    RESTORE;
}

static uint32_t game_poll(uint32_t port)
{
    uint32_t r;
    SAVE;
    g_edi = BO3_MENU_DIALOG;
    PUSH32(g_esp, 1u);
    PUSH32(g_esp, port);
    PUSH32(g_esp, 0);
    sub_000CD2A0();
    r = g_eax;
    RESTORE;
    return r;
}

static void game_close(void)
{
    SAVE;
    g_ecx = BO3_MENU_DIALOG;
    PUSH32(g_esp, 0);
    sub_000CCC90();
    RESTORE;
}

static const bo3_menu_ops s_game_ops = { game_open, game_poll, game_close };

/* item 47: player 0's chosen car as its ValueDB name (sub_000C0080's own way: GP-CARS2 donor map, base-40 name, spaces cut) */
#include "bm_tracks.h"
#include "bo3_cars_gen.h"
int bo3_hudx_draw_cmds(const bm_hud_cmd *cmds, uint32_t n);
static int game_bars_car(char *name, uint32_t room)
{
    char s[13];
    size_t k;
    uint64_t id = bo3_menu_bars_car_id();          /* item 59: the previewed car, not 0x740B00 (all 0xFF on car select) */
    if (!id || room < sizeof s)
        return 0;
    id = bo3_car_gen_phys_id((uint32_t)id, (uint32_t)(id >> 32));
    bo3_cc_decode(id, s);
    s[12] = 0;
    for (k = strlen(s); k && s[k - 1] == ' '; k--)
        s[k - 1] = 0;
    snprintf(name, room, "%s", s);
    return name[0] != 0;
}
static int game_bars_draw(const struct bm_hud_cmd *cmds, uint32_t n) { return bo3_hudx_draw_cmds(cmds, n); }

/* patch 45: a popup's answer = the plugin's own PER_PLAYER setting (as a MODS-page change) */
static void answer_settings(const td_host *host, const char *key, uint32_t player, int32_t value)
{
    if (!bo3_ps_set_player(host, key, player, value))
        fprintf(stderr, "[MENU] popup answer %d for %s (player %u) refused by bmashup.settings\n", (int)value, key, (unsigned)player);
}
#endif

void bo3_bm_menu_init(void)
{
#ifdef BO3_MENU_GAME
    bo3_menu_set_ops(&s_game_ops);
    bo3_menu_set_answer(answer_settings);
    bo3_menu_set_rules(bo3_rules_mode_race);
    bo3_menu_set_bars_io(game_bars_draw, game_bars_car);   /* item 47 */
#endif
    bo3_plugins_service(BM_MENU_SERVICE, BM_MENU_VERSION, &s_api);
}
