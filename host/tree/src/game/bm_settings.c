/*
 * bm_settings.c - "bmashup.settings" (include/bmashup_settings.h), version 1 (gp slice camset1).
 *
 * Declarations come on the main thread while the plugins start; bo3_bm_settings_close ends that before the guest
 * runs. From then on the registry's shape is fixed: the MODS page (game thread) steps values, get (any thread) reads
 * them (atomic 32-bit loads). The file is read once, at the first declaration, and written whole (bo3_modfs_write_whole:
 * path.tmp, then renamed over) after each change; a file that is not a settings file is never written over.
 */
#include "bm_settings.h"

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "modfs.h"
#include "modmanifest.h"
#include "plugins.h"
#include "recomp_cfg.h"

#ifndef MUT
#define MUT 0   /* 1..9 (camset1, version 1); main18 (v2): 21 P2's value saved under P1's key, 22 the scope field read from
                   a v1-sized declaration, 23 version 1's per-plugin limit (6) kept, 24 a v1 callback given P2's changes,
                   25 get_player answers P1's value for P2; main21 patch 130 (data-mod sliders): 31 a decimal stored value read
                   as a whole number (the scale lost), 32 an off-grid stored value taken (not only the default), 33 a slider's
                   change not handed to its owner */
#endif

#define MAX_SUBS      BO3_MODFS_MAX_MODS
#define MAX_ENTRIES   512                /* main18: 256 -> 512 (128 settings x 2 players + other mods' entries) */
#define ENTRY_MAX     (BO3_MOD_ID_MAX + 1 + BM_SETTINGS_KEY_MAX + 3 + 3 + 16)   /* "<id>/<key>[#pN] = <value>" */
#define FILE_MAX      (64 * 1024)
#define NPLAYERS      2u
#define PAGE_LINES    ((int)BM_SETTINGS_PER_PLUGIN)       /* the MOD SETTINGS page: 1 + 6 + 2 = 9 lines */

typedef struct {
    td_host *host;
    char mod[BO3_MOD_ID_MAX + 1];
    uint32_t kind;
    char key[BM_SETTINGS_KEY_MAX + 1], label[BM_SETTINGS_LABEL_MAX + 1], unit[BM_SETTINGS_UNIT_MAX + 1];
    int32_t min, max, step, def;
    char choices[BM_SETTINGS_CHOICES_MAX][BM_SETTINGS_CHOICE_MAX + 1];
    uint32_t nchoices;
    _Atomic int32_t value;              /* GLOBAL: the value; PER_PLAYER: P1's (player 0) */
    int plugin;                         /* index into s_plug */
    uint32_t scope;                     /* main18: BM_SETTING_SCOPE_* */
    _Atomic int32_t value2;             /* main18: PER_PLAYER: P2's (player 1) */
    /* main21 patch 130: a data mod's slider (bo3_ps_data_declare); all 0 for a plugin's or the host's setting */
    uint32_t dec;                       /* INT: the value is in units of 10^-dec (shown and stored with a decimal point) */
    int offdef;                         /* the default may lie off the min + k * step grid (it stays a value) */
    uint32_t when;                      /* BO3_PS_WHEN_*: the page's hint */
    bo3_ps_data_fn dfn;                 /* the owner's change handler (no plugin callback) */
    void *duser;
} setting;

typedef struct {
    td_host *host;
    char mod[BO3_MOD_ID_MAX + 1];
    int first, count;                   /* its settings: s_set[first .. first + count - 1] are NOT contiguous in
                                         * general; idx[] lists them */
    int idx[BM_SETTINGS_PER_PLUGIN_V2];
    bm_setting_fn fn;
    void *user;
    bm_setting_fn2 fn2;                 /* main18: subscribe2 (fn and fn2 never both) */
} plugin;

static setting s_set[BM_SETTINGS_TOTAL_V2];
static int s_nset;
static plugin s_plug[MAX_SUBS];
static int s_nplug;
static int s_open = 1;
static int s_initial_done;
static bo3_ps_guard_fn s_guard;
static bo3_ps_guard2_fn s_guard2;

/* main18: a value of setting s for player (0 / 1; a GLOBAL setting has one value for both) */
static _Atomic int32_t *slot(setting *s, uint32_t player)
{
    return s->scope == BM_SETTING_SCOPE_PER_PLAYER && player == 1 ? &s->value2 : &s->value;
}

/* main18: the file key of setting s for player: "<key>" (GLOBAL), "<key>#p1" / "<key>#p2" (PER_PLAYER) */
static void file_key(const setting *s, uint32_t player, char *out, size_t n)
{
#if MUT == 21
    player = 0;                                          /* defect: P2 saved under P1's key */
#endif
    if (s->scope == BM_SETTING_SCOPE_PER_PLAYER)
        snprintf(out, n, "%s#p%u", s->key, (unsigned)player + 1u);
    else
        snprintf(out, n, "%s", s->key);
}

/* the file */
static char s_path[1100];
static int s_file_read;                 /* read once */
static int s_file_bad;                  /* there but not a settings file: never written */
static char (*s_entries)[ENTRY_MAX + 1];
static int s_nentries;
static int s_save_failed;

/* GP-P4.1: host settings - the host token stands for "bmashup.host" (no plugin td_host is ever this address). */
static int s_host_tag;
#define HOST_TOKEN ((td_host *)(void *)&s_host_tag)

/* main21 patch 130: data mods' tokens (no plugin host): their mod ids */
static struct { td_host *host; char mod[BO3_MOD_ID_MAX + 1]; } s_data[MAX_SUBS];
static int s_ndata;

static const char *pid(td_host *host)
{
    if (host == HOST_TOKEN)
        return BO3_PS_HOST_MOD;   /* GP-P4.1 */
    for (int i = 0; i < s_ndata; i++)
        if (s_data[i].host == host)
            return s_data[i].mod;
    const char *id = bo3_plugins_host_id(host);
    return id ? id : "";
}

/* ---- text rules ---- */

static int key_ok(const char *k)
{
    size_t n;
    if (!k)
        return 0;
    n = strlen(k);
    if (n < 1 || n > BM_SETTINGS_KEY_MAX)
        return 0;
#if MUT != 8
    for (size_t i = 0; i < n; i++)
        if (!((k[i] >= 'a' && k[i] <= 'z') || (k[i] >= '0' && k[i] <= '9') || k[i] == '_'))
            return 0;
#endif
    return 1;
}

/* printable ASCII without " and \ (the file's strings stay plain), lo..hi characters */
static int text_ok(const char *t, size_t lo, size_t hi)
{
    size_t n;
    if (!t)
        return lo == 0;
    n = strlen(t);
    if (n < lo || n > hi)
        return 0;
    for (size_t i = 0; i < n; i++)
        if ((unsigned char)t[i] < 0x20 || (unsigned char)t[i] > 0x7E || t[i] == '"' || t[i] == '\\')
            return 0;
    return 1;
}

static int ieq(const char *a, const char *b)
{
    for (; *a && *b; a++, b++) {
        char x = (char)(*a >= 'A' && *a <= 'Z' ? *a + 32 : *a), y = (char)(*b >= 'A' && *b <= 'Z' ? *b + 32 : *b);
        if (x != y)
            return 0;
    }
    return *a == *b;
}

/* ---- values ---- */

static int value_ok(const setting *s, int32_t v)
{
    if (v < s->min || v > s->max)
        return 0;
    if (s->kind == BM_SETTING_INT && ((int64_t)v - s->min) % s->step != 0)
        return s->offdef && v == s->def;     /* main21 patch 130: a slider's off-grid default (never for a plugin's) */
    return 1;
}

/* main21 patch 130: an INT number as the page and the file show it: "%ld" (dec 0, every plugin setting), else with dec decimals,
 * trailing zeros dropped but one kept ("1.05", "0.703", "1.0", "-0.5") */
static void num_text(const setting *s, int32_t v, char *out, size_t n)
{
    long long a = v < 0 ? -(long long)v : (long long)v, p = 1;
    char frac[16];
    size_t k;
    if (!s->dec) {
        snprintf(out, n, "%ld", (long)v);
        return;
    }
    for (uint32_t d = 0; d < s->dec; d++)
        p *= 10;
    snprintf(frac, sizeof frac, "%0*lld", (int)s->dec, a % p);
    for (k = strlen(frac); k > 1 && frac[k - 1] == '0'; k--)
        frac[k - 1] = 0;
    snprintf(out, n, "%s%lld.%s", v < 0 ? "-" : "", a / p, frac);
}

static void value_text(const setting *s, int32_t v, char *out, size_t n)
{
    if (s->kind == BM_SETTING_BOOL)
        snprintf(out, n, "%s", v ? "on" : "off");
    else if (s->kind == BM_SETTING_ENUM)
        snprintf(out, n, "%s", v >= 0 && (uint32_t)v < s->nchoices ? s->choices[v] : "?");
    else
        num_text(s, v, out, n);
}

/* main21 patch 130: "[-]D[.D]" with at most dec decimals -> units of 10^-dec, exactly (no floating point); 1 ok */
static int dec_parse(const char *t, uint32_t dec, long long *out)
{
    long long w = 0, f = 0;
    uint32_t fd = 0;
    int neg = *t == '-', digits = 0;
    if (neg)
        t++;
    for (; *t >= '0' && *t <= '9'; t++, digits++)
        if ((w = w * 10 + (*t - '0')) > 100000000LL)
            return 0;
    if (*t == '.') {
        t++;
        for (; *t >= '0' && *t <= '9'; t++, fd++) {
            if (fd >= dec)
                return 0;                    /* more decimals than the setting has */
            f = f * 10 + (*t - '0');
        }
        if (!fd)
            return 0;
    }
    if (*t || !digits)
        return 0;
    for (; fd < dec; fd++)
        f *= 10;
    for (uint32_t d = 0; d < dec; d++)
        w *= 10;
    *out = neg ? -(w + f) : w + f;
    return 1;
}

/* the stored text for setting s: 1 with *v, 0 not a value of s (why says) */
static int value_parse(const setting *s, const char *t, int32_t *v, const char **why)
{
    if (s->kind == BM_SETTING_BOOL) {
        if (!strcmp(t, "on")) { *v = 1; return 1; }
        if (!strcmp(t, "off")) { *v = 0; return 1; }
        *why = "not on / off";
        return 0;
    }
    if (s->kind == BM_SETTING_ENUM) {
        for (uint32_t c = 0; c < s->nchoices; c++)
            if (ieq(t, s->choices[c])) { *v = (int32_t)c; return 1; }
        *why = "not one of the choices";
        return 0;
    }
    if (s->dec) {                                    /* main21 patch 130: a slider's decimal value */
        long long x;
#if MUT == 31
        if (!dec_parse(t, 0, &x)) {                  /* defect: the scale lost (whole numbers only, unscaled) */
#else
        if (!dec_parse(t, s->dec, &x)) {
#endif
            *why = "not a number with at most the setting's decimals";
            return 0;
        }
        if (x < s->min || x > s->max) {
            *why = "outside the declared range";
            return 0;
        }
#if MUT != 32
        if ((x - s->min) % s->step && x != s->def) {
            *why = "not a step of the declared range";
            return 0;
        }
#endif
        *v = (int32_t)x;
        return 1;
    }
    {
        char *end;
        long long x;
        if (!*t || (!(*t >= '0' && *t <= '9') && *t != '-')) {
            *why = "not a whole number";
            return 0;
        }
        x = strtoll(t, &end, 10);
        if (*end) {
            *why = "not a whole number";
            return 0;
        }
#if MUT == 1
        if (x < s->min) x = s->min;                 /* defect: clamped instead of the default */
        if (x > s->max) x = s->max;
#endif
        if (x < s->min || x > s->max) {
            *why = "outside the declared range";
            return 0;
        }
#if MUT != 9
        if ((x - s->min) % s->step) {
            *why = "not a step of the declared range";
            return 0;
        }
#endif
        *v = (int32_t)x;
        return 1;
    }
}

/* ---- the file ---- */

/* "<id>/<key> = <value>": 1 with the parts (pointers into buf) */
static int entry_split(const char *e, char *buf, size_t n, char **id, char **key, char **val)
{
    char *sl, *eq;
    if (strlen(e) >= n)
        return 0;
    strcpy(buf, e);
    sl = strchr(buf, '/');
    eq = strstr(buf, " = ");
    if (!sl || !eq || eq < sl)
        return 0;
    *sl = 0;
    *eq = 0;
    *id = buf;
    *key = sl + 1;
    *val = eq + 3;
    return 1;
}

static void file_read(void)
{
    char why[200] = "";
    char *text = NULL;
    size_t len = 0;
    recomp_cfg *cfg = NULL;
    int r;

    if (s_file_read)
        return;
    s_file_read = 1;
    if (!s_entries)
        s_entries = calloc(MAX_ENTRIES, sizeof *s_entries);
    if (!s_path[0] || !s_entries)
        return;
    r = bo3_modfs_read_whole(s_path, &text, &len);
    if (r == 0) {
        free(text);
        fprintf(stderr, "[SETTINGS] plugin settings file: none yet (%s): every setting starts at its default\n", s_path);
        return;
    }
    if (r < 0)
        snprintf(why, sizeof why, r == -1 ? "it cannot be read now" : "not a file, or larger than 64 KiB");
    else if (memchr(text, 0, len))
        snprintf(why, sizeof why, "a NUL byte");
    else if (!(cfg = recomp_cfg_load_string(text, s_path, why, sizeof why)))
        ;
    else if (recomp_cfg_type_of(cfg, "values") != RCFG_ARRAY && recomp_cfg_type_of(cfg, "values") != RCFG_NONE)
        snprintf(why, sizeof why, "values must be a list of strings");
    else {
        size_t n = recomp_cfg_array_len(cfg, "values");
        for (size_t i = 0; i < n; i++) {
            const char *e = recomp_cfg_array_string(cfg, "values", i, NULL);
            if (recomp_cfg_array_type(cfg, "values", i) != RCFG_STRING || !e || !text_ok(e, 1, ENTRY_MAX)) {
                snprintf(why, sizeof why, "entry %u is not a plain string of at most %u characters", (unsigned)i + 1,
                         (unsigned)ENTRY_MAX);
                break;
            }
            if (s_nentries == MAX_ENTRIES) {
                snprintf(why, sizeof why, "more than %d entries", MAX_ENTRIES);
                break;
            }
            strcpy(s_entries[s_nentries++], e);
        }
    }
    free(text);
    recomp_cfg_free(cfg);
    if (why[0]) {
        s_file_bad = 1;
        s_nentries = 0;
        fprintf(stderr, "[SETTINGS] plugin settings file not used and never written over (%s): %s - every setting "
                "starts at its default, changes last for this session\n", why, s_path);
        return;
    }
    fprintf(stderr, "[SETTINGS] plugin settings file: %d entr%s (%s)\n", s_nentries, s_nentries == 1 ? "y" : "ies",
            s_path);
}

static int entry_of(const char *mod, const char *key)
{
    char buf[ENTRY_MAX + 1], *id, *k, *v;
    for (int i = 0; i < s_nentries; i++)
        if (entry_split(s_entries[i], buf, sizeof buf, &id, &k, &v) && !strcmp(id, mod) && !strcmp(k, key))
            return i;
    return -1;
}

static int file_write(void)
{
    size_t cap = (size_t)s_nentries * (ENTRY_MAX + 8) + 256, n = 0;
    char *text;
    int ok;

    if (!s_path[0] || s_file_bad || !s_entries)
        return 0;
    if (!(text = malloc(cap)))
        return 0;
    n += (size_t)snprintf(text + n, cap - n, "# Burnout Mashup plugin settings (bmashup.settings): written by the MODS "
                          "page.\nvalues = [\n");
    for (int i = 0; i < s_nentries; i++)
        n += (size_t)snprintf(text + n, cap - n, "    \"%s\",\n", s_entries[i]);
    n += (size_t)snprintf(text + n, cap - n, "]\n");
    ok = n < cap && n <= FILE_MAX && bo3_modfs_write_whole(s_path, text, n);
    free(text);
    return ok;
}

/* setting k's value (player's, main18) into the entries (in place, or appended), then the whole file */
static int save(int k, uint32_t player)
{
    setting *s = &s_set[k];
    char vt[BM_SETTINGS_CHOICE_MAX + 16], e[ENTRY_MAX + 1], fk[BM_SETTINGS_KEY_MAX + 4];
    int i;

    if (!s_path[0]) {
        s_save_failed = 0;
        return 1;                                    /* none: the session only, by choice */
    }
    if (s_file_bad || !s_entries) {
        s_save_failed = 1;
        fprintf(stderr, "[SETTINGS] %s/%s not saved: the plugin settings file is not used (above)\n", s->mod, s->key);
        return 0;
    }
    value_text(s, atomic_load(slot(s, player)), vt, sizeof vt);
    file_key(s, player, fk, sizeof fk);
    snprintf(e, sizeof e, "%s/%s = %s", s->mod, fk, vt);
#if MUT == 5
    s_nentries = 0;                                  /* defect: other mods' entries dropped */
#endif
    i = entry_of(s->mod, fk);
    if (i < 0) {
        if (s_nentries == MAX_ENTRIES) {
            s_save_failed = 1;
            fprintf(stderr, "[SETTINGS] %s/%s not saved: the file holds %d entries\n", s->mod, s->key, MAX_ENTRIES);
            return 0;
        }
        i = s_nentries++;
    }
    strcpy(s_entries[i], e);
    if (!file_write()) {
        s_save_failed = 1;
        fprintf(stderr, "[SETTINGS] %s/%s not saved: %s could not be written (it is as it was)\n", s->mod, s->key, s_path);
        return 0;
    }
    s_save_failed = 0;
    return 1;
}

/* ---- the service ---- */

static int plugin_of(td_host *host, int make)
{
    for (int p = 0; p < s_nplug; p++)
        if (s_plug[p].host == host)
            return p;
    if (!make || s_nplug == MAX_SUBS)
        return -1;
    memset(&s_plug[s_nplug], 0, sizeof s_plug[s_nplug]);
    s_plug[s_nplug].host = host;
    snprintf(s_plug[s_nplug].mod, sizeof s_plug[s_nplug].mod, "%s", pid(host));
    return s_nplug++;
}

static const char *kind_name(uint32_t k)
{
    return k == BM_SETTING_BOOL ? "BOOL" : k == BM_SETTING_INT ? "INT" : "ENUM";
}

/* x: main21 patch 130, a data mod's slider (bo3_ps_data_declare); NULL for a plugin's or the host's setting */
static int32_t ps_declare_x(td_host *host, const bm_setting_decl *d, int32_t *value, const bo3_ps_data_ext *x)
{
    setting s;
    int p, k;
    const char *why = NULL;
    int32_t v;

    uint32_t scope = BM_SETTING_SCOPE_GLOBAL;
    if (!host || !d || d->struct_size < BM_SETTING_DECL_V1_SIZE
            || (d->kind != BM_SETTING_BOOL && d->kind != BM_SETTING_INT && d->kind != BM_SETTING_ENUM))
        return BM_SETTINGS_BAD_ARG;
#if MUT == 22
    scope = d->scope;                                    /* defect: read from a v1-sized declaration too */
#else
    if (d->struct_size >= BM_SETTING_DECL_V2_SIZE)       /* main18: a v1 plugin's struct never reaches it */
        scope = d->scope;
#endif
    if (scope != BM_SETTING_SCOPE_GLOBAL && scope != BM_SETTING_SCOPE_PER_PLAYER) {
        fprintf(stderr, "[SETTINGS] mod %s: setting refused: scope %u is not GLOBAL (0) or PER_PLAYER (1)\n", pid(host),
                (unsigned)scope);
        return BM_SETTINGS_BAD_SCOPE;
    }
#if MUT != 2
    if (!s_open) {
        fprintf(stderr, "[SETTINGS] mod %s: setting refused: the plugins have started (declare while starting)\n",
                pid(host));
        return BM_SETTINGS_CLOSED;
    }
#endif
    memset(&s, 0, sizeof s);
    if (x) {                                             /* main21 patch 130 */
        s.dec = d->kind == BM_SETTING_INT ? x->decimals : 0;
        s.offdef = d->kind == BM_SETTING_INT;
        s.def = d->def;                                  /* value_ok's off-grid default (below) */
        s.when = x->when;
        s.dfn = x->fn;
        s.duser = x->user;
    }
    if (!key_ok(d->key) || !text_ok(d->label, 1, BM_SETTINGS_LABEL_MAX)
            || (d->kind == BM_SETTING_INT && !text_ok(d->unit, 0, BM_SETTINGS_UNIT_MAX))) {
        fprintf(stderr, "[SETTINGS] mod %s: setting refused: key [a-z0-9_] 1..%u, label 1..%u and unit 0..%u printable "
                "characters (no \" or \\)\n", pid(host), BM_SETTINGS_KEY_MAX, BM_SETTINGS_LABEL_MAX, BM_SETTINGS_UNIT_MAX);
        return BM_SETTINGS_BAD_TEXT;
    }
    s.kind = d->kind;
    if (d->kind == BM_SETTING_BOOL) {
        s.min = 0; s.max = 1; s.step = 1;
    } else if (d->kind == BM_SETTING_ENUM) {
        if (!d->choices || d->nchoices < 2 || d->nchoices > BM_SETTINGS_CHOICES_MAX) {
            fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: 2..%u choices\n", pid(host), d->key,
                    BM_SETTINGS_CHOICES_MAX);
            return BM_SETTINGS_BAD_RANGE;
        }
        for (uint32_t c = 0; c < d->nchoices; c++) {
            if (!text_ok(d->choices[c], 1, BM_SETTINGS_CHOICE_MAX)) {
                fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: choice %u: 1..%u printable characters\n",
                        pid(host), d->key, (unsigned)c + 1, BM_SETTINGS_CHOICE_MAX);
                return BM_SETTINGS_BAD_TEXT;
            }
            for (uint32_t o = 0; o < c; o++)
                if (ieq(d->choices[o], d->choices[c])) {
                    fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: choice %u repeats choice %u\n", pid(host),
                            d->key, (unsigned)c + 1, (unsigned)o + 1);
                    return BM_SETTINGS_BAD_TEXT;
                }
            snprintf(s.choices[c], sizeof s.choices[c], "%s", d->choices[c]);
        }
        s.nchoices = d->nchoices;
        s.min = 0; s.max = (int32_t)d->nchoices - 1; s.step = 1;
    } else {
        int64_t span;
        if (d->step < 1 || d->min > d->max || d->min < -BM_SETTINGS_INT_LIMIT || d->max > BM_SETTINGS_INT_LIMIT) {
            fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: min <= max within +-%d, step >= 1\n", pid(host),
                    d->key, BM_SETTINGS_INT_LIMIT);
            return BM_SETTINGS_BAD_RANGE;
        }
        span = ((int64_t)d->max - d->min) / d->step + 1;
        if (span > BM_SETTINGS_INT_STEPS || ((int64_t)d->max - d->min) % d->step) {
            fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: max must be min + a whole number of steps, at most "
                    "%u values\n", pid(host), d->key, BM_SETTINGS_INT_STEPS);
            return BM_SETTINGS_BAD_RANGE;
        }
        s.min = d->min; s.max = d->max; s.step = d->step;
        if (d->unit)
            snprintf(s.unit, sizeof s.unit, "%s", d->unit);
    }
    if (!value_ok(&s, d->def)) {
        fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: the default %ld is not one of its values\n", pid(host),
                d->key, (long)d->def);
        return BM_SETTINGS_BAD_RANGE;
    }
    s.def = d->def;
    snprintf(s.key, sizeof s.key, "%s", d->key);
    snprintf(s.label, sizeof s.label, "%s", d->label);
    p = plugin_of(host, 0);
    if (p >= 0) {
        for (int i = 0; i < s_plug[p].count; i++)
            if (!strcmp(s_set[s_plug[p].idx[i]].key, d->key)) {
                fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: declared already\n", pid(host), d->key);
                return BM_SETTINGS_DUPLICATE;
            }
#if MUT != 23
        if (s_plug[p].count == (int)BM_SETTINGS_PER_PLUGIN_V2) {
#else
        if (s_plug[p].count == (int)BM_SETTINGS_PER_PLUGIN) {         /* defect: still version 1's limit */
#endif
            fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: %u settings a plugin\n", pid(host), d->key,
                    BM_SETTINGS_PER_PLUGIN_V2);
            return BM_SETTINGS_FULL;
        }
    }
    if (s_nset == (int)BM_SETTINGS_TOTAL_V2 || (p < 0 && (p = plugin_of(host, 1)) < 0)) {
        fprintf(stderr, "[SETTINGS] mod %s: setting %s refused: %u settings in all\n", pid(host), d->key,
                BM_SETTINGS_TOTAL_V2);
        return BM_SETTINGS_FULL;
    }
    s.host = host;
    s.scope = scope;
    snprintf(s.mod, sizeof s.mod, "%s", s_plug[p].mod);
    s.plugin = p;
    file_read();
    k = s_nset++;
    memcpy(&s_set[k], &s, sizeof s);
    for (uint32_t pl = 0; pl < (scope == BM_SETTING_SCOPE_PER_PLAYER ? NPLAYERS : 1u); pl++) {
        char fk[BM_SETTINGS_KEY_MAX + 4];
        int e;
        char buf[ENTRY_MAX + 1], *id, *key, *val;
        int32_t sv;
        file_key(&s_set[k], pl, fk, sizeof fk);
        e = entry_of(s.mod, fk);
        v = s.def;
        if (e >= 0 && entry_split(s_entries[e], buf, sizeof buf, &id, &key, &val)) {
            if (value_parse(&s, val, &sv, &why))
                v = sv;
            else
                fprintf(stderr, "[SETTINGS] mod %s: setting %s: stored value \"%s\" not used (%s): the default\n",
                        s.mod, fk, val, why);
        }
        atomic_store(slot(&s_set[k], pl), v);
    }
    if (scope != BM_SETTING_SCOPE_PER_PLAYER)
        atomic_store(&s_set[k].value2, atomic_load(&s_set[k].value));
    v = atomic_load(&s_set[k].value);
    s_plug[p].idx[s_plug[p].count++] = k;
    {
        char vt[BM_SETTINGS_CHOICE_MAX + 16], vt2[BM_SETTINGS_CHOICE_MAX + 24] = "";
        value_text(&s, v, vt, sizeof vt);
        if (scope == BM_SETTING_SCOPE_PER_PLAYER) {
            char t2[BM_SETTINGS_CHOICE_MAX + 16];
            value_text(&s, atomic_load(&s_set[k].value2), t2, sizeof t2);
            snprintf(vt2, sizeof vt2, " (P1) / %s (P2), per player", t2);
        }
        if (s.kind == BM_SETTING_INT && s.dec) {         /* main21 patch 130: a data mod's slider */
            char a[24], b[24], c[24], e[24];
            num_text(&s, s.min, a, sizeof a);
            num_text(&s, s.max, b, sizeof b);
            num_text(&s, s.step, c, sizeof c);
            num_text(&s, s.def, e, sizeof e);
            fprintf(stderr, "[SETTINGS] mod %s: slider %s \"%s\" (%s..%s step %s, default %s): %s\n", s.mod, s.key, s.label, a, b,
                    c, e, vt);
        } else if (s.kind == BM_SETTING_INT)
            fprintf(stderr, "[SETTINGS] mod %s: setting %s \"%s\" (INT %ld..%ld step %ld%s%s, default %ld): %s%s\n", s.mod,
                    s.key, s.label, (long)s.min, (long)s.max, (long)s.step, s.unit[0] ? " " : "", s.unit,
                    (long)s.def, vt, vt2);
        else
            fprintf(stderr, "[SETTINGS] mod %s: setting %s \"%s\" (%s, %u values, default %ld): %s%s\n", s.mod, s.key,
                    s.label, kind_name(s.kind), (unsigned)(s.max + 1), (long)s.def, vt, vt2);
    }
    if (value)
        *value = v;
    return BM_SETTINGS_OK;
}

static int32_t TD_CALL ps_declare(td_host *host, const bm_setting_decl *d, int32_t *value)
{
    return ps_declare_x(host, d, value, NULL);
}

/* main21 patch 130: a data mod's slider (bm_settings.h) */
int32_t bo3_ps_data_declare(td_host *who, const char *mod_id, const bm_setting_decl *d, const bo3_ps_data_ext *x, int32_t *value)
{
    int i;
    if (!who || who == HOST_TOKEN || !mod_id || !mod_id[0] || strlen(mod_id) > BO3_MOD_ID_MAX || !x || !x->fn || !d ||
            (d->kind != BM_SETTING_BOOL && d->kind != BM_SETTING_INT) || x->decimals > BO3_PS_DATA_DECIMALS_MAX)
        return BM_SETTINGS_BAD_ARG;
    if (!s_open)
        return BM_SETTINGS_CLOSED;
    for (i = 0; i < s_ndata && s_data[i].host != who; i++)
        ;
    if (i < s_ndata && strcmp(s_data[i].mod, mod_id))
        return BM_SETTINGS_BAD_ARG;                      /* one token, one mod */
    if (i == s_ndata) {
        if (plugin_of(who, 0) >= 0 || s_ndata == MAX_SUBS)
            return plugin_of(who, 0) >= 0 ? BM_SETTINGS_BAD_ARG : BM_SETTINGS_FULL;   /* a plugin's host is no data token */
        s_data[s_ndata].host = who;
        snprintf(s_data[s_ndata++].mod, sizeof s_data[0].mod, "%s", mod_id);
    }
    return ps_declare_x(who, d, value, x);
}

static int32_t TD_CALL ps_subscribe(td_host *host, bm_setting_fn fn, void *user)
{
    int p;
    if (!host || !fn)
        return BM_SETTINGS_BAD_ARG;
    if (!s_open)
        return BM_SETTINGS_CLOSED;
    p = plugin_of(host, 1);
    if (p < 0)
        return BM_SETTINGS_FULL;
    if (s_plug[p].fn || s_plug[p].fn2)
        return BM_SETTINGS_DUPLICATE;
    s_plug[p].fn = fn;
    s_plug[p].user = user;
    return BM_SETTINGS_OK;
}

/* main18 (v2) */
static int32_t TD_CALL ps_subscribe2(td_host *host, bm_setting_fn2 fn, void *user)
{
    int p;
    if (!host || !fn)
        return BM_SETTINGS_BAD_ARG;
    if (!s_open)
        return BM_SETTINGS_CLOSED;
    p = plugin_of(host, 1);
    if (p < 0)
        return BM_SETTINGS_FULL;
    if (s_plug[p].fn || s_plug[p].fn2)
        return BM_SETTINGS_DUPLICATE;
    s_plug[p].fn2 = fn;
    s_plug[p].user = user;
    return BM_SETTINGS_OK;
}

static setting *find(td_host *host, const char *key)
{
    int p = plugin_of(host, 0);          /* reads only: the plugin table is fixed after the start */
    for (int i = 0; p >= 0 && i < s_plug[p].count; i++)
        if (!strcmp(s_set[s_plug[p].idx[i]].key, key))
            return &s_set[s_plug[p].idx[i]];
    return NULL;
}

static int32_t TD_CALL ps_get(td_host *host, const char *key, int32_t *value)
{
    setting *s;
    if (!host || !key || !value)
        return BM_SETTINGS_BAD_ARG;
    if (!(s = find(host, key)))
        return BM_SETTINGS_UNKNOWN;
    *value = atomic_load(&s->value);     /* PER_PLAYER: P1's */
    return BM_SETTINGS_OK;
}

static int32_t TD_CALL ps_get_player(td_host *host, const char *key, uint32_t player, int32_t *value)
{
    setting *s;
    if (!host || !key || !value)
        return BM_SETTINGS_BAD_ARG;
    if (player >= NPLAYERS)
        return BM_SETTINGS_BAD_SCOPE;
    if (!(s = find(host, key)))
        return BM_SETTINGS_UNKNOWN;
#if MUT == 25
    player = 0;                          /* defect: P1's value for P2 */
#endif
    *value = atomic_load(slot(s, player));
    return BM_SETTINGS_OK;
}

static const bm_settings_api s_api = {
    (uint32_t)sizeof(bm_settings_api), BM_SETTINGS_VERSION, ps_declare, ps_subscribe, ps_get, ps_subscribe2,
    ps_get_player
};

const bm_settings_api *bo3_bm_settings_api(void) { return &s_api; }

void bo3_ps_file(const char *path)
{
    snprintf(s_path, sizeof s_path, "%s", path && strlen(path) < sizeof s_path ? path : "");
}

#ifdef BO3_SETTINGS_GAME   /* the game build (CMake): callbacks run inside a guest mark, so the guest's registers are
                            * kept across them (bm_events_service.c's rule; a plugin cannot reach them, this is
                            * defence in depth) */
#include "recomp_types.h"
extern RECOMP_TLS uint32_t g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_esp, g_ebp;
static unsigned s_reg_faults;
static void game_guard(bm_setting_fn fn, const char *key, int32_t value, uint32_t reason, void *user)
{
    uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
    fn(key, value, reason, user);
    if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
        g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
        fprintf(stderr, "[SETTINGS] a callback changed the guest's registers (%u): put back\n", ++s_reg_faults);
    }
}
static void game_guard2(bm_setting_fn2 fn, const char *key, uint32_t player, int32_t value, uint32_t reason, void *user)
{
    uint32_t r[8] = {g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_ebp, g_esp};
    fn(key, player, value, reason, user);
    if (r[0] != g_eax || r[1] != g_ebx || r[2] != g_ecx || r[3] != g_edx || r[4] != g_esi || r[5] != g_edi ||
            r[6] != g_ebp || r[7] != g_esp) {
        g_eax = r[0]; g_ebx = r[1]; g_ecx = r[2]; g_edx = r[3]; g_esi = r[4]; g_edi = r[5]; g_ebp = r[6]; g_esp = r[7];
        fprintf(stderr, "[SETTINGS] a callback changed the guest's registers (%u): put back\n", ++s_reg_faults);
    }
}
#endif

void bo3_bm_settings_init(void)
{
#ifdef BO3_SETTINGS_GAME
    s_guard = game_guard;
    s_guard2 = game_guard2;
#endif
    bo3_plugins_service(BM_SETTINGS_SERVICE, BM_SETTINGS_VERSION, &s_api);
}

void bo3_bm_settings_close(void)
{
    int subs = 0;
    if (!s_open)
        return;
    s_open = 0;
    for (int p = 0; p < s_nplug; p++)
        subs += s_plug[p].fn != NULL || s_plug[p].fn2 != NULL;
    fprintf(stderr, "[SETTINGS] declarations closed: %d setting(s) of %d plugin(s), %d callback(s); file %s\n", s_nset,
            bo3_ps_mod_count(), subs, s_path[0] ? s_path : "(none: values for this session only)");
}

/* ---- delivery ---- */

/* setting s's value for player to its plugin's callback. fn2 (subscribe2): every player (GLOBAL: BM_SETTING_ALL_PLAYERS);
 * fn (v1 subscribe): GLOBAL, or a PER_PLAYER setting's P1 (player 0) only. */
static void deliver(int p, setting *s, uint32_t player, uint32_t reason)
{
    const plugin *pl;
    if (s->dfn) {                                    /* main21 patch 130: a data mod's slider: its owner (bm_tune), changes only
                                                      * (the start applied the initial value already) */
#if MUT != 33
        if (reason == BM_SETTING_CHANGED)
            s->dfn(s->duser, atomic_load(&s->value));
#endif
        return;
    }
#if MUT == 6
    p = 0;                                           /* defect: the first plugin's callback for everyone */
#endif
    pl = &s_plug[p];
    if (pl->fn2) {
        uint32_t who = s->scope == BM_SETTING_SCOPE_PER_PLAYER ? player : BM_SETTING_ALL_PLAYERS;
        if (s_guard2)
            s_guard2(pl->fn2, s->key, who, atomic_load(slot(s, player)), reason, pl->user);
        else
            pl->fn2(s->key, who, atomic_load(slot(s, player)), reason, pl->user);
        return;
    }
    if (!pl->fn)
        return;
#if MUT != 24
    if (s->scope == BM_SETTING_SCOPE_PER_PLAYER && player != 0)
        return;                                      /* a v1 callback knows no players: P1's value only */
#endif
    if (s_guard)
        s_guard(pl->fn, s->key, atomic_load(slot(s, player)), reason, pl->user);
    else
        pl->fn(s->key, atomic_load(slot(s, player)), reason, pl->user);
}

void bo3_ps_game_point(void)
{
    int n = 0;
#if MUT != 7
    if (s_initial_done)
        return;
#endif
    s_initial_done = 1;
    if (s_open)
        bo3_bm_settings_close();                     /* never before the start ended (main.c order makes it so) */
    for (int k = 0; k < s_nset; k++) {
        deliver(s_set[k].plugin, &s_set[k], 0, BM_SETTING_INITIAL);
        if (s_set[k].scope == BM_SETTING_SCOPE_PER_PLAYER)
            deliver(s_set[k].plugin, &s_set[k], 1, BM_SETTING_INITIAL);
        n++;
    }
    if (n)
        fprintf(stderr, "[SETTINGS] initial values delivered: %d setting(s)\n", n);
}

/* ---- the MODS page ----
 * main18: pages. A plugin's lines (GLOBAL: one, PER_PLAYER: two, "P1" / "P2") are cut into pages of at most PAGE_LINES;
 * the two lines of one setting stay on one page. Content of version 1 (GLOBAL only, <= 6 a plugin) = one page a plugin. */

typedef struct { int k; uint32_t player; int per; } ps_line_ref;   /* per: 1 when the line is one player's */

/* the q-th plugin's lines; returns the count (at most 2 x BM_SETTINGS_PER_PLUGIN_V2) */
static int plugin_lines(int q, ps_line_ref *out)
{
    int n = 0;
    for (int i = 0; i < s_plug[q].count; i++) {
        int k = s_plug[q].idx[i];
        if (s_set[k].scope == BM_SETTING_SCOPE_PER_PLAYER) {
            out[n].k = k; out[n].player = 0; out[n].per = 1; n++;
            out[n].k = k; out[n].player = 1; out[n].per = 1; n++;
        } else {
            out[n].k = k; out[n].player = 0; out[n].per = 0; n++;
        }
    }
    return n;
}

/* page boundaries of the q-th plugin: first line of each page into first[], the page count returned */
static int plugin_pages(int q, int *first, int room)
{
    ps_line_ref l[2 * BM_SETTINGS_PER_PLUGIN_V2];
    int n = plugin_lines(q, l), pages = 0, used = 0;
    for (int i = 0; i < n; i++) {
        int need = l[i].per && l[i].player == 0 ? 2 : 1;         /* a P1 line brings its P2 line */
        if (l[i].per && l[i].player == 1)
            need = 0;                                            /* placed with its P1 line */
        if (i == 0 || (need && used + need > PAGE_LINES)) {
            if (pages < room)
                first[pages] = i;
            pages++;
            used = 0;
        }
        used += need;
    }
    return n ? pages : 0;
}

int bo3_ps_mod_count(void)
{
    int n = 0;
    for (int p = 0; p < s_nplug; p++)
        n += s_plug[p].count > 0;
    return n;
}

int bo3_ps_plugin_count(void)
{
    int n = 0, f[2 * BM_SETTINGS_PER_PLUGIN_V2];
    for (int q = 0; q < s_nplug; q++)
        if (s_plug[q].count > 0)
            n += plugin_pages(q, f, (int)(sizeof f / sizeof f[0]));
    return n;
}

/* page p -> its plugin q, its first line and line count; 0 when there is no page p */
static int page_of(int p, int *q_out, int *first, int *count)
{
    int f[2 * BM_SETTINGS_PER_PLUGIN_V2 + 1];
    ps_line_ref l[2 * BM_SETTINGS_PER_PLUGIN_V2];
    if (p < 0)
        return 0;
    for (int q = 0; q < s_nplug; q++) {
        int np, n;
        if (s_plug[q].count <= 0)
            continue;
        np = plugin_pages(q, f, (int)(sizeof f / sizeof f[0]) - 1);
        if (p >= np) {
            p -= np;
            continue;
        }
        n = plugin_lines(q, l);
        f[np] = n;
        *q_out = q;
        *first = f[p];
        *count = f[p + 1] - f[p];
        return 1;
    }
    return 0;
}

static int at_line(int p, int i, ps_line_ref *out)
{
    int q, first, count;
    ps_line_ref l[2 * BM_SETTINGS_PER_PLUGIN_V2];
    if (!page_of(p, &q, &first, &count) || i < 0 || i >= count)
        return 0;
    plugin_lines(q, l);
    *out = l[first + i];
    return 1;
}

const char *bo3_ps_plugin_mod(int p)
{
    int q, first, count;
    return page_of(p, &q, &first, &count) ? s_plug[q].mod : "";
}

int bo3_ps_count(int p)
{
    int q, first, count;
    return page_of(p, &q, &first, &count) ? count : 0;
}

void bo3_ps_line(int p, int i, char *out, size_t n)
{
    ps_line_ref r;
    setting *s;
    char vt[BM_SETTINGS_CHOICE_MAX + 16];
    if (!at_line(p, i, &r)) {
        if (n) out[0] = 0;
        return;
    }
    s = &s_set[r.k];
    value_text(s, atomic_load(slot(s, r.player)), vt, sizeof vt);
    snprintf(out, n, "%s%s  %s%s%s", s->label, r.per ? (r.player ? " P2" : " P1") : "", vt,
             s->kind == BM_SETTING_INT && s->unit[0] ? " " : "", s->kind == BM_SETTING_INT ? s->unit : "");
}

void bo3_ps_detail(int p, int i, char *out, size_t n)
{
    ps_line_ref r;
    const setting *s;
    char dt[BM_SETTINGS_CHOICE_MAX + 16];
    if (!at_line(p, i, &r)) {
        if (n) out[0] = 0;
        return;
    }
    s = &s_set[r.k];
    value_text(s, s->def, dt, sizeof dt);
    if (s->kind == BM_SETTING_INT && s->dec) {       /* main21 patch 130: a slider: "A: 0.5 TO 2.0 BY 0.05  DEFAULT 1.0" */
        char a[24], b[24], c[24];
        num_text(s, s->min, a, sizeof a);
        num_text(s, s->max, b, sizeof b);
        num_text(s, s->step, c, sizeof c);
        snprintf(out, n, "A: %s TO %s BY %s  DEFAULT %s", a, b, c, dt);
    } else if (s->kind == BM_SETTING_INT)
        snprintf(out, n, "A: %ld TO %ld%s%s BY %ld  DEFAULT %s", (long)s->min, (long)s->max, s->unit[0] ? " " : "",
                 s->unit, (long)s->step, dt);
    else if (s->kind == BM_SETTING_BOOL)
        snprintf(out, n, "A: ON / OFF  DEFAULT %s", dt);
    else
        snprintf(out, n, "A: NEXT OF %u CHOICES  DEFAULT %s", (unsigned)s->nchoices, dt);
    if (s->when) {                                   /* main21 patch 130: when a slider takes effect, when the line has room */
        const char *h = s->when == BO3_PS_WHEN_NEXT_RACE ? "  NEXT RACE" : "  AT ONCE";
        size_t k = strlen(out);
        if (k + strlen(h) <= BO3_PS_DETAIL_FIT && k + strlen(h) < n)
            snprintf(out + k, n - k, "%s", h);
    }
}

int bo3_ps_step(int p, int i)
{
    ps_line_ref r;
    setting *s;
    int32_t v, nv;
    char vt[BM_SETTINGS_CHOICE_MAX + 16], fk[BM_SETTINGS_KEY_MAX + 4];
    if (!at_line(p, i, &r))
        return 0;
    s = &s_set[r.k];
    v = atomic_load(slot(s, r.player));
    nv = v + s->step;
    if (((int64_t)v - s->min) % s->step)             /* main21 patch 130: from a slider's off-grid default: the next grid value */
        nv = s->min + (int32_t)(((int64_t)v - s->min) / s->step + 1) * s->step;
#if MUT != 3
    if (nv > s->max)
        nv = s->min;                                 /* wraps */
#endif
    atomic_store(slot(s, r.player), nv);
    if (s->scope != BM_SETTING_SCOPE_PER_PLAYER)
        atomic_store(&s->value2, nv);                /* a GLOBAL setting answers its one value for both players */
#if MUT != 4
    save(r.k, r.player);
#endif
    value_text(s, nv, vt, sizeof vt);
    file_key(s, r.player, fk, sizeof fk);
    fprintf(stderr, "[SETTINGS] %s/%s = %s (MODS page)%s\n", s->mod, fk, vt,
            !s_path[0] ? ", this session only" : s_save_failed ? ", NOT saved" : ", saved");
    deliver(s->plugin, s, r.player, BM_SETTING_CHANGED);
    return 1;
}

int bo3_ps_save_failed(void) { return s_save_failed; }

/* ---- main20m patch 61: the overlay's MOD SETTINGS page ----
 * The overlay draws on its own thread; a change is queued here and made on the game thread (bo3_ps_flush, at the title's
 * next flip: stored, saved, delivered as bo3_ps_step does), so plugins' callbacks and the file stay on the game thread.
 * Until then the line shows the queued value. A spin lock (an atomic flag) guards the queue only. */
#define PS_QUEUE 64
typedef struct { int k; uint32_t player; int32_t value; } ps_req;
static ps_req s_q[PS_QUEUE];
static int s_nq;
static atomic_flag s_q_lock = ATOMIC_FLAG_INIT;
static _Atomic int s_q_any;

static void q_lock(void) { while (atomic_flag_test_and_set(&s_q_lock)) ; }
static void q_unlock(void) { atomic_flag_clear(&s_q_lock); }

/* the value setting k shows for player: the last queued one, else the stored one */
static int32_t shown_value(int k, uint32_t player)
{
    int32_t v = atomic_load(slot(&s_set[k], player));
    q_lock();
    for (int j = 0; j < s_nq; j++)
        if (s_q[j].k == k && (s_q[j].player == player || s_set[k].scope != BM_SETTING_SCOPE_PER_PLAYER))
            v = s_q[j].value;
    q_unlock();
    return v;
}

/* op 1 the next value, -1 the one before (both wrap), 0 the default */
static int32_t op_value(const setting *s, int32_t v, int op)
{
    const int32_t st = s->kind == BM_SETTING_INT && s->step > 0 ? s->step : 1;
    const int32_t top = s->min + (int32_t)(((int64_t)s->max - s->min) / st * st);
    if (op == 0)
        return s->def;
    if (((int64_t)v - s->min) % st) {                /* main21 patch 130: a slider's off-grid default: the grid value above / below */
        int32_t below = s->min + (int32_t)(((int64_t)v - s->min) / st) * st;
        if (op > 0)
            return below + st > s->max ? s->min : below + st;
        return below < s->min ? top : below;
    }
    if (op > 0)
        return v + st > s->max ? s->min : v + st;
    return v - st < s->min ? top : v - st;
}

void bo3_ps_line2(int p, int i, char *label, size_t ln, char *value, size_t vn)
{
    ps_line_ref r;
    setting *s;
    char vt[BM_SETTINGS_CHOICE_MAX + 16];
    if (!at_line(p, i, &r)) {
        if (ln) label[0] = 0;
        if (vn) value[0] = 0;
        return;
    }
    s = &s_set[r.k];
    value_text(s, shown_value(r.k, r.player), vt, sizeof vt);
    if (s->kind == BM_SETTING_BOOL)
        snprintf(vt, sizeof vt, "%s", shown_value(r.k, r.player) ? "On" : "Off");   /* as the overlay's own switches */
    snprintf(label, ln, "%s%s", s->label, r.per ? (r.player ? " (player 2)" : " (player 1)") : "");
    snprintf(value, vn, "%s%s%s", vt, s->kind == BM_SETTING_INT && s->unit[0] ? " " : "",
             s->kind == BM_SETTING_INT ? s->unit : "");
}

void bo3_ps_detail2(int p, int i, char *out, size_t n)
{
    ps_line_ref r;
    const setting *s;
    char dt[BM_SETTINGS_CHOICE_MAX + 16];
    if (!at_line(p, i, &r)) {
        if (n) out[0] = 0;
        return;
    }
    s = &s_set[r.k];
    value_text(s, s->def, dt, sizeof dt);
    if (s->kind == BM_SETTING_INT && s->dec) {       /* main21 patch 130: a slider */
        char a[24], b[24], c[24];
        num_text(s, s->min, a, sizeof a);
        num_text(s, s->max, b, sizeof b);
        num_text(s, s->step, c, sizeof c);
        snprintf(out, n, "From %s to %s, in steps of %s. Default: %s.", a, b, c, dt);
    } else if (s->kind == BM_SETTING_INT)
        snprintf(out, n, "From %ld to %ld%s%s, in steps of %ld. Default: %s%s%s.", (long)s->min, (long)s->max,
                 s->unit[0] ? " " : "", s->unit, (long)s->step, dt, s->unit[0] ? " " : "", s->unit);
    else if (s->kind == BM_SETTING_BOOL)
        snprintf(out, n, "On or off. Default: %s.", dt);
    else
        snprintf(out, n, "One of %u choices. Default: %s.", (unsigned)s->nchoices, dt);
    if (s->when) {                                   /* main21 patch 130 */
        size_t k = strlen(out);
        if (k < n)
            snprintf(out + k, n - k, "%s", s->when == BO3_PS_WHEN_NEXT_RACE ? " Takes effect from the next race." :
                                               " Takes effect at once.");
    }
}

int bo3_ps_is_default(int p, int i)
{
    ps_line_ref r;
    if (!at_line(p, i, &r))
        return 1;
    return shown_value(r.k, r.player) == s_set[r.k].def;
}

int bo3_ps_request(int p, int i, int op)
{
    ps_line_ref r;
    setting *s;
    int32_t nv;
    int ok = 0;
    if (!at_line(p, i, &r))
        return 0;
    s = &s_set[r.k];
    nv = op_value(s, shown_value(r.k, r.player), op);
    if (!value_ok(s, nv))
        return 0;
    q_lock();
    for (int j = 0; j < s_nq && !ok; j++)
        if (s_q[j].k == r.k && s_q[j].player == r.player) {
            s_q[j].value = nv;                       /* a later change replaces a queued one */
            ok = 1;
        }
    if (!ok && s_nq < PS_QUEUE) {
        s_q[s_nq].k = r.k;
        s_q[s_nq].player = r.player;
        s_q[s_nq++].value = nv;
        ok = 1;
    }
    if (ok)
        atomic_store(&s_q_any, 1);
    q_unlock();
    return ok;
}

int bo3_ps_pending(void) { return atomic_load(&s_q_any); }

void bo3_ps_flush(void)
{
    ps_req q[PS_QUEUE];
    int nq;
    if (!atomic_load(&s_q_any))
        return;
    q_lock();
    nq = s_nq;
    memcpy(q, s_q, (size_t)nq * sizeof q[0]);
    s_nq = 0;
    atomic_store(&s_q_any, 0);
    q_unlock();
    for (int j = 0; j < nq; j++) {
        setting *s = &s_set[q[j].k];
        char vt[BM_SETTINGS_CHOICE_MAX + 16], fk[BM_SETTINGS_KEY_MAX + 4];
        if (atomic_load(slot(s, q[j].player)) == q[j].value)
            continue;                                /* stepped back to what it was: nothing changed */
        atomic_store(slot(s, q[j].player), q[j].value);
        if (s->scope != BM_SETTING_SCOPE_PER_PLAYER)
            atomic_store(&s->value2, q[j].value);
        save(q[j].k, q[j].player);
        value_text(s, q[j].value, vt, sizeof vt);
        file_key(s, q[j].player, fk, sizeof fk);
        fprintf(stderr, "[SETTINGS] %s/%s = %s (MOD SETTINGS)%s\n", s->mod, fk, vt,
                !s_path[0] ? ", this session only" : s_save_failed ? ", NOT saved" : ", saved");
        deliver(s->plugin, s, q[j].player, BM_SETTING_CHANGED);
    }
}

/* GP-P4.1: host settings (bm_settings.h) */
int32_t bo3_ps_host_declare(const bm_setting_decl *decl, int32_t *value) { return ps_declare(HOST_TOKEN, decl, value); }
int32_t bo3_ps_host_get(const char *key, int32_t *value) { return ps_get(HOST_TOKEN, key, value); }

void bo3_ps_set_guard(bo3_ps_guard_fn fn) { s_guard = fn; }
void bo3_ps_set_guard2(bo3_ps_guard2_fn fn) { s_guard2 = fn; }

void bo3_ps_reset_for_tests(void)
{
    memset(s_set, 0, sizeof s_set);
    memset(s_plug, 0, sizeof s_plug);
    s_nset = s_nplug = 0;
    memset(s_data, 0, sizeof s_data);                /* main21 patch 130 */
    s_ndata = 0;
    s_open = 1;
    s_initial_done = 0;
    s_guard = NULL;
    s_guard2 = NULL;
    s_path[0] = 0;
    s_file_read = s_file_bad = 0;
    s_nentries = 0;
    s_save_failed = 0;
}

int bo3_ps_query(const td_host *host, const char *key, uint32_t *kind, uint32_t *scope, uint32_t *nchoices,
                 char choice2[2][BM_SETTINGS_CHOICE_MAX + 1])
{
    if (!host || !key)
        return 0;
    for (int i = 0; i < s_nset; i++)
        if (s_set[i].host == host && !strcmp(s_set[i].key, key)) {
            if (kind)
                *kind = s_set[i].kind;
            if (scope)
                *scope = s_set[i].scope;
            if (nchoices)
                *nchoices = s_set[i].nchoices;
            if (choice2)
                for (uint32_t c = 0; c < 2u; c++)
                    snprintf(choice2[c], BM_SETTINGS_CHOICE_MAX + 1, "%s", c < s_set[i].nchoices ? s_set[i].choices[c] : "");
            return 1;
        }
    return 0;
}

/* main19 patch 45 (bmashup.menu popup answers): set the plugin's own setting for player as a MODS-page change does (stored,
 * saved, delivered with BM_SETTING_CHANGED). Refused (0): unknown setting, player >= 2, value outside the setting's range. */
/* main21 patch 88 (bmashup.menu mode option rows): a plugin's setting as "LABEL: value" (ENUM: the choice; BOOL: ON / OFF; INT:
 * the number and the unit). Any thread (the value is atomic; the declaration is fixed after the close). 0 = no such setting. */
int bo3_ps_value_text(const td_host *host, const char *key, char *out, size_t n)
{
    if (!host || !key || !out || !n)
        return 0;
    for (int i = 0; i < s_nset; i++)
        if (s_set[i].host == host && !strcmp(s_set[i].key, key)) {
            int32_t v = atomic_load(&s_set[i].value);
            if (s_set[i].kind == BM_SETTING_ENUM && v >= 0 && (uint32_t)v < s_set[i].nchoices)
                snprintf(out, n, "%s: %s", s_set[i].label, s_set[i].choices[v]);
            else if (s_set[i].kind == BM_SETTING_BOOL)
                snprintf(out, n, "%s: %s", s_set[i].label, v ? "ON" : "OFF");
            else if (s_set[i].dec) {                 /* main21 patch 130: a data mod's slider (no plugin asks; kept exact) */
                char t[24];
                num_text(&s_set[i], v, t, sizeof t);
                snprintf(out, n, "%s: %s", s_set[i].label, t);
            } else
                snprintf(out, n, "%s: %d%s%s", s_set[i].label, (int)v, s_set[i].unit[0] ? " " : "", s_set[i].unit);
            return 1;
        }
    return 0;
}

int bo3_ps_set_player(const td_host *host, const char *key, uint32_t player, int32_t value)
{
    setting *s;
    char vt[BM_SETTINGS_CHOICE_MAX + 16], fk[BM_SETTINGS_KEY_MAX + 4];
    if (!host || !key || player >= NPLAYERS || !(s = find((td_host *)host, key)) || !value_ok(s, value))
        return 0;
    atomic_store(slot(s, player), value);
    if (s->scope != BM_SETTING_SCOPE_PER_PLAYER)
        atomic_store(&s->value2, value);
    save((int)(s - s_set), player);
    value_text(s, value, vt, sizeof vt);
    file_key(s, player, fk, sizeof fk);
    fprintf(stderr, "[SETTINGS] %s/%s = %s (menu popup)%s\n", s->mod, fk, vt,
            !s_path[0] ? ", this session only" : s_save_failed ? ", NOT saved" : ", saved");
    deliver(s->plugin, s, player, BM_SETTING_CHANGED);
    return 1;
}
