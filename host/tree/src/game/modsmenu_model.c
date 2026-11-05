/*
 * modsmenu_model.c - the mods' states for the overlay's MODS page (gp main20m patch 62; modsmenu_model.h).
 */
#include "modsmenu_model.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "modfs.h"
#include "plugins.h"

#ifndef MMM_MUT
#define MMM_MUT 0      /* tests only (tests/modsmenu2): 1 the approval added before the mod list, 2 no roll-back, 3 off keeps
                          the approval, 4 a changed module shown as approved */
#endif

static unsigned char s_next[BO3_MODFS_MAX_MODS];        /* the mod list: on from the next start */
static unsigned char s_appr_next[BO3_MODFS_MAX_MODS];   /* its plugin approved for the bytes known */
static unsigned char s_entry[BO3_MODFS_MAX_MODS];       /* the approval file names it */
static char s_sha[BO3_MODFS_MAX_MODS][65];              /* its module as hashed here ("" not yet: as this start hashed it) */
static char s_start_sha[BO3_MODFS_MAX_MODS][65];
static bo3_approvals_state s_appr;
static int (*s_live)(const char *id, int on);           /* td030: mm_set_live */
static signed char s_live_on[BO3_MODFS_MAX_MODS];       /* 0 not asked; 1 in use off, 2 in use on */

void mm_set_live(int (*fn)(const char *id, int on)) { s_live = fn; }

int mm_live_now(int i)
{
    return i >= 0 && i < BO3_MODFS_MAX_MODS && s_live_on[i] && s_live_on[i] - 1 == s_next[i];
}

static void ask_live(int i, const bo3_mod *m, int on)
{
    if (i < BO3_MODFS_MAX_MODS && s_live && s_live(m->manifest.id, on))
        s_live_on[i] = (signed char)(on + 1);
}

static int nmods(void)
{
    int n = bo3_modfs_mod_count();
    return n < BO3_MODFS_MAX_MODS ? n : BO3_MODFS_MAX_MODS;
}

int mm_count(void) { return nmods(); }

int mm_has_plugin(int i)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    return m && m->usable && m->manifest.plugin && m->manifest.plugin_path[0];
}

int mm_approval_writable(void)
{
    return s_appr == BO3_APPROVALS_ABSENT || s_appr == BO3_APPROVALS_OK;
}

static const char *known_sha(int i)
{
    return s_sha[i][0] ? s_sha[i] : s_start_sha[i];
}

void mm_refresh(void)
{
    s_appr = bo3_plugins_approvals();
    for (int i = 0; i < nmods(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        const char *sha;
        s_next[i] = (unsigned char)(m->usable ? bo3_modfs_enabled_next(m->manifest.id) : m->enabled);
        s_appr_next[i] = s_entry[i] = 0;
        s_start_sha[i][0] = 0;
        if (!mm_has_plugin(i))
            continue;
        bo3_plugins_state(i, NULL, 0, s_start_sha[i], sizeof s_start_sha[i]);
        sha = known_sha(i);
        s_entry[i] = (unsigned char)(bo3_plugins_approvals_of(m->manifest.id, NULL, 0) > 0);
        s_appr_next[i] = (unsigned char)(sha[0] ? bo3_plugins_approved_for(m->manifest.id, sha) : 0);
#if MMM_MUT == 4
        s_appr_next[i] = s_entry[i];
#endif
    }
}

mm_status mm_status_of(int i)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m)
        return MM_UNUSABLE;
    if (!m->usable)
        return m->needs ? MM_NEEDS_MOD : m->conflict ? MM_CONFLICT : MM_UNUSABLE;
    if (!mm_has_plugin(i))
        return mm_live_now(i) ? (s_next[i] ? MM_ON : MM_OFF)
             : s_next[i] == m->enabled ? (m->enabled ? MM_ON : MM_OFF) : (s_next[i] ? MM_ON_RESTART : MM_OFF_RESTART);
    if (bo3_plugins_off())
        return MM_PLUGINS_OFF;
    {
        const int was = bo3_plugins_was_approved(i);              /* approved (so loaded) at this start */
        const bo3_plugin_state st = bo3_plugins_state(i, NULL, 0, NULL, 0);
        if (!s_next[i])
            return m->enabled ? MM_OFF_RESTART : MM_OFF;
        if (!s_appr_next[i])
            return s_entry[i] && known_sha(i)[0] ? MM_CODE_CHANGED : MM_NEEDS_APPROVAL;
        if (!was || !m->enabled)
            return MM_ON_RESTART;                                  /* approved (and on) from the next start */
        return st == BO3_PLUGIN_RUNNING ? MM_ON : MM_PLUGIN_NOT_LOADED;
    }
}

const char *mm_chip(mm_status st)
{
    static const char *const t[MM_STATUS_COUNT] = {
        "ON", "OFF", "ON AFTER RESTART", "OFF AFTER RESTART", "NEEDS APPROVAL", "CHANGED - APPROVE AGAIN",
        "PLUGIN NOT LOADED", "PLUGINS OFF", "NEEDS ANOTHER MOD", "CONFLICT", "CAN'T BE USED"
    };
    return st >= 0 && st < MM_STATUS_COUNT ? t[st] : "";
}

int mm_tone(mm_status st)
{
    switch (st) {
    case MM_ON: return MM_TONE_GOOD;
    case MM_OFF: case MM_PLUGINS_OFF: return MM_TONE_DIM;
    case MM_ON_RESTART: case MM_OFF_RESTART: case MM_NEEDS_APPROVAL: case MM_CODE_CHANGED: return MM_TONE_ATTN;
    default: return MM_TONE_BAD;
    }
}

mm_toggle mm_toggle_of(int i)
{
    const mm_status st = mm_status_of(i);
    if (st == MM_NEEDS_MOD || st == MM_CONFLICT || st == MM_UNUSABLE || st == MM_PLUGINS_OFF)
        return MM_TOGGLE_NONE;
    if (!mm_has_plugin(i))
        return s_next[i] ? MM_TOGGLE_OFF : MM_TOGGLE_ON;
    if (s_next[i] && s_appr_next[i])
        return mm_approval_writable() || !s_entry[i] ? MM_TOGGLE_OFF : MM_TOGGLE_NONE;
    if (s_next[i] && !mm_approval_writable())
        return MM_TOGGLE_OFF;                                      /* on without its code: off is still possible */
    return mm_approval_writable() ? MM_TOGGLE_APPROVE : MM_TOGGLE_NONE;
}

int mm_count_status(mm_status st)
{
    int k = 0;
    for (int i = 0; i < nmods(); i++)
        k += mm_status_of(i) == st;
    return k;
}

/* ---- texts ---- */

static void clean(char *out, size_t n, const char *s)
{
    size_t k = 0;
    if (!n)
        return;
    for (; s && *s && k + 1 < n; s++)
        out[k++] = (unsigned char)*s < 0x20 || *s == 0x7F ? ' ' : *s;
    while (k && (out[k - 1] & 0xC0) == 0x80 && k + 1 >= n)
        k--;                                                       /* never a cut UTF-8 character at the end */
    out[k] = 0;
}

static const char *leaf(const char *p)
{
    const char *a = strrchr(p, '/'), *b = strrchr(p, '\\');
    const char *f = a > b ? a : b;
    return f ? f + 1 : p;
}

void mm_name(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    clean(out, n, !m ? "" : m->manifest.name[0] ? m->manifest.name : leaf(m->folder));
}

void mm_byline(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    char v[BO3_MOD_VERSION_MAX + 1], a[BO3_MOD_AUTHOR_MAX + 1];
    if (!m) {
        if (n) out[0] = 0;
        return;
    }
    clean(v, sizeof v, m->manifest.version);
    clean(a, sizeof a, m->manifest.author);
    snprintf(out, n, "%s%s  %s%s", v[0] ? "v" : "version ", v[0] ? v : "-", a[0] ? "by " : "author unknown", a);
}

void mm_kind(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    snprintf(out, n, "%s", m && m->manifest.plugin ? "plugin (native code)" : "data mod");
}

void mm_about(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m) {
        if (n) out[0] = 0;
        return;
    }
    if (m->gameplay[0]) {
        /* "CHANGES GAMEPLAY: BOOST, SCORING" -> "Changes gameplay: boost, scoring" (bm_admit.c writes it in capitals) */
        size_t k = 0;
        if (!n)
            return;
        for (const char *p = m->gameplay; *p && k + 1 < n; p++, k++)
            out[k] = k && *p >= 'A' && *p <= 'Z' ? (char)(*p + 32) : *p;
        out[k] = 0;
        for (char *w = out; (w = strstr(w, "ai")) != NULL; w += 2)    /* the word AI stays in capitals */
            if ((w == out || w[-1] == ' ') && (w[2] == 0 || w[2] == ',' || w[2] == ' '))
                w[0] = 'A', w[1] = 'I';
        return;
    }
    clean(out, n, m->manifest.description);
}

/* The admission's reason, readable: ">=" as "at least". */
static void reason(const char *in, char *out, size_t n)
{
    size_t k = 0;
    for (const char *p = in ? in : ""; *p && k + 10 < n; p++) {
        if (p[0] == '>' && p[1] == '=') {
            memcpy(out + k, "at least ", 9);
            k += 9;
            p++;
            while (p[1] == ' ')
                p++;
        } else {
            out[k++] = (unsigned char)*p < 0x20 ? ' ' : *p;
        }
    }
    if (n) out[k < n ? k : n - 1] = 0;
}

static const bo3_mod *shared_id(const bo3_mod *m)
{
    if (m->usable || !m->manifest.id[0])
        return NULL;
    for (int i = 0; i < nmods(); i++) {
        const bo3_mod *o = bo3_modfs_mod(i);
        if (o != m && !strcmp(o->manifest.id, m->manifest.id))
            return o;
    }
    return NULL;
}

void mm_why(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    char r[400], w[200] = "";
    const char *off;
    if (!m) {
        if (n) out[0] = 0;
        return;
    }
    switch (mm_status_of(i)) {
    case MM_ON:
        snprintf(out, n, mm_has_plugin(i) ? "On. Its plugin is approved and running." : "On.");
        return;
    case MM_OFF:
        snprintf(out, n, "Off.");
        return;
    case MM_ON_RESTART:
        snprintf(out, n, "%s", mm_has_plugin(i) ? "On from the next start: restart the game to start its plugin."
                                                : "On from the next start: restart the game to use it.");
        return;
    case MM_OFF_RESTART:
        snprintf(out, n, "%s", mm_has_plugin(i) ? "Off from the next start (its plugin runs until the game is closed)."
                                                : "Off from the next start: restart the game.");
        return;
    case MM_NEEDS_APPROVAL:
        snprintf(out, n, "%s", mm_approval_writable()
                 ? "This mod includes a plugin (native code) that is not approved yet, so it cannot run. Choose Approve "
                   "and turn on to review it."
                 : "This mod includes a plugin that is not approved, and approvals are kept by hand in "
                   "plugin-approvals.toml here (the log says why). Add it there, or fix the file.");
        return;
    case MM_CODE_CHANGED:
        snprintf(out, n, "Its plugin file has changed since you approved it (an update, or a different file). Approve "
                 "the new file to use it again.");
        return;
    case MM_PLUGIN_NOT_LOADED:
        bo3_plugins_state(i, w, sizeof w, NULL, 0);
        snprintf(out, n, "Approved, but its plugin did not start this time%s%s. The game's log has the details.",
                 w[0] ? ": " : "", w);
        return;
    case MM_PLUGINS_OFF:
        off = bo3_plugins_off();
        snprintf(out, n, "%s", off && !strcmp(off, "TAKEDAWN_PLUGINS=0")
                 ? "Plugins are switched off for this game (TAKEDAWN_PLUGINS=0), so its plugin cannot run."
                 : off && strstr(off, "macOS") ? "Plugins do not run on macOS unless TAKEDAWN_PLUGINS=1 is set."
                 : "Plugins cannot run on this system.");
        return;
    case MM_NEEDS_MOD:
    case MM_CONFLICT:
    case MM_UNUSABLE:
        if (shared_id(m)) {
            snprintf(out, n, "Another folder (%s) has a mod with the same id. Remove one of the two folders.",
                     leaf(shared_id(m)->folder));
            return;
        }
        reason(m->problem, r, sizeof r);
        snprintf(out, n, "%s%s", r[0] ? r : "Its mod.toml could not be read.", r[0] && r[strlen(r) - 1] != '.' ? "." : "");
        if (r[0] >= 'a' && r[0] <= 'z' && n)
            out[0] = (char)(out[0] - 32);
        return;
    default:
        if (n) out[0] = 0;
    }
}

void mm_module(int i, char *file, size_t fn, long *bytes)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    char path[BO3_MODFS_PATH_MAX];
    struct stat st;
    *bytes = -1;
    if (!m || !m->manifest.plugin_path[0]) {
        if (fn) file[0] = 0;
        return;
    }
    clean(file, fn, leaf(m->manifest.plugin_path));
    if (bo3_modfs_mod_file(m, m->manifest.plugin_path, path, sizeof path) && !stat(path, &st))
        *bytes = (long)st.st_size;
}

void mm_files(int i, char *out, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m || m->wins + m->loses == 0) {
        if (n) out[0] = 0;
        return;
    }
    snprintf(out, n, "%d file%s used over earlier mods' or the game's, %d replaced by later mods", m->wins,
             m->wins == 1 ? "" : "s", m->loses);
}

void mm_summary(char *out, size_t n)
{
    const int nm = nmods();
    int on = 0, appr = 0, bad = 0, rs = 0;
    size_t k;
    if (!nm) {
        snprintf(out, n, "No mods installed");
        return;
    }
    for (int i = 0; i < nm; i++) {
        mm_status st = mm_status_of(i);
        on += st == MM_ON || st == MM_OFF_RESTART || st == MM_PLUGIN_NOT_LOADED;
        appr += st == MM_NEEDS_APPROVAL || st == MM_CODE_CHANGED;
        bad += st == MM_NEEDS_MOD || st == MM_CONFLICT || st == MM_UNUSABLE || st == MM_PLUGIN_NOT_LOADED;
        rs += st == MM_ON_RESTART || st == MM_OFF_RESTART;
    }
    k = (size_t)snprintf(out, n, "%d mod%s  \xC2\xB7  %d on", nm, nm == 1 ? "" : "s", on);
    if (appr && k < n)
        k += (size_t)snprintf(out + k, n - k, "  \xC2\xB7  %d need%s approval", appr, appr == 1 ? "s" : "");
    if (rs && k < n)
        k += (size_t)snprintf(out + k, n - k, "  \xC2\xB7  %d after restart", rs);
    if (bad && k < n)
        snprintf(out + k, n - k, "  \xC2\xB7  %d can't be used", bad);
}

/* ---- actions ---- */

int mm_turn_on(int i, char *why, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m || !m->usable || mm_has_plugin(i)) {
        snprintf(why, n, "%s", mm_has_plugin(i) ? "A mod with a plugin is turned on by approving it." : "This mod can't be used.");
        return 0;
    }
    if (!bo3_modfs_set_enabled(m->manifest.id, 1)) {
        snprintf(why, n, "Not saved: the mod list could not be written (the log says why).");
        return 0;
    }
    fprintf(stderr, "[MODS] %s: on from the next start (MODS page)\n", m->manifest.id);
    mm_refresh();
    ask_live(i, m, 1);
    return 1;
}

int mm_turn_off(int i, char *why, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m || !m->usable) {
        snprintf(why, n, "This mod can't be used.");
        return 0;
    }
#if MMM_MUT != 3
    if (mm_has_plugin(i) && (s_entry[i] || s_appr == BO3_APPROVALS_BAD)) {
        if (!bo3_plugins_set_approval(m->manifest.id, NULL)) {          /* the approval first: never more code than chosen */
            snprintf(why, n, "Not saved: the plugin approval could not be removed (the log says why). Nothing was changed.");
            mm_refresh();
            return 0;
        }
    }
#endif
    if (!bo3_modfs_set_enabled(m->manifest.id, 0)) {
        snprintf(why, n, "Not saved: the mod list could not be written (the log says why).");
        mm_refresh();
        return 0;
    }
    fprintf(stderr, "[MODS] %s: off from the next start%s (MODS page)\n", m->manifest.id,
            mm_has_plugin(i) ? ", its approval removed" : "");
    mm_refresh();
    if (!mm_has_plugin(i))
        ask_live(i, m, 0);
    return 1;
}

int mm_hash(int i, char sha[65], char *why, size_t n)
{
    char w[200] = "";
    sha[0] = 0;
    if (!mm_has_plugin(i)) {
        snprintf(why, n, "This mod has no plugin for this system.");
        return 0;
    }
    if (!bo3_plugins_hash_module(i, sha, w, sizeof w)) {
        snprintf(why, n, "Its plugin file could not be read: %s.", w);
        return 0;
    }
    memcpy(s_sha[i], sha, 65);                                      /* the bytes as last seen here */
    fprintf(stderr, "[MODS] %s: approval screen for %s (sha256 %s)\n", bo3_modfs_mod(i)->manifest.id,
            bo3_modfs_mod(i)->manifest.plugin_path, sha);
    return 1;
}

int mm_approve_and_on(int i, const char *sha, char *why, size_t n)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    int was_on;
    if (!mm_has_plugin(i) || !sha || strlen(sha) != 64 || strcmp(sha, s_sha[i])) {
        snprintf(why, n, "Nothing was approved: the plugin file was not checked on this screen.");
        return 0;
    }
    if (!mm_approval_writable()) {
        snprintf(why, n, "Approvals are kept by hand in plugin-approvals.toml here (the log says why): nothing was changed.");
        return 0;
    }
    was_on = bo3_modfs_enabled_next(m->manifest.id);
#if MMM_MUT == 1
    bo3_plugins_set_approval(m->manifest.id, sha);
#endif
    if (!bo3_modfs_set_enabled(m->manifest.id, 1)) {
        snprintf(why, n, "Not saved: the mod list could not be written (the log says why). Nothing was changed.");
        mm_refresh();
        return 0;
    }
    if (!bo3_plugins_set_approval(m->manifest.id, sha)) {
#if MMM_MUT != 2
        if (!was_on)
            bo3_modfs_set_enabled(m->manifest.id, 0);              /* back as it was: no mod on without what was chosen */
#endif
        snprintf(why, n, "Not saved: the approval could not be written (the log says why). Nothing was changed.");
        mm_refresh();
        return 0;
    }
    fprintf(stderr, "[MODS] %s: plugin approved (sha256 %s) and on from the next start (MODS page)\n", m->manifest.id, sha);
    mm_refresh();
    return 1;
}

int mm_restart_count(char *why, size_t n)
{
    int k = 0;
    for (int i = 0; i < nmods(); i++) {
        mm_status st = mm_status_of(i);
        k += st == MM_ON_RESTART || st == MM_OFF_RESTART;
    }
    if (why && n) {
        why[0] = 0;
        if (k)
            snprintf(why, n, "Mods: %d mod%s change%s at the next start.", k, k == 1 ? "" : "s", k == 1 ? "s" : "");
    }
    return k;
}
