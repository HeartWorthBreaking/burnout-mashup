/*
 * modsmenu_ov.c - the MODS and MOD SETTINGS pages in the Takedawn overlay (gp main20m patch 63;
 * gp\modsmenu\MODSMENU_DESIGN.md).
 *
 * Driver Details > Settings > MODS opens the overlay on the MODS page (modsmenu.c asks for it), and both pages are tabs
 * of the overlay whenever it is open (the hotkey, the race's pause menu). The overlay draws them in its own look (the
 * title's fonts, sprites and sounds) with no row limit; the states and actions are modsmenu_model.c's, the plugin
 * settings bm_settings.c's (bo3_ps_request: queued, made on the game thread at the next flip).
 *
 * MODS: a summary line, "Approve N plugins" while some wait, then every mod in load order: its name as written, a status
 * chip, its version, author and description under the rows. Left / right turns a mod on or off; for a mod with a plugin
 * that is not approved it opens the approval screen: the plugin's file, its size and full SHA-256, the warning, and ONE
 * action that approves exactly those bytes AND turns the mod on (also offered with "and restart now"). A opens a mod's
 * details (every field, the reason in full, the actions). Saved at once; "Restart now to apply N changes" at the foot.
 *
 * Every callback runs on the overlay's thread with its lock held; the model is touched only here in this process (the
 * native page is not used when this one is: bo3_mmov_start decides at the start), so no lock of its own is needed.
 * BMASHUP_MODS_UI=native keeps the native page (modsmenu.c) instead.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "modsmenu_model.h"
#include "modfs.h"
#include "bm_env.h"   /* pfid1: BM_GETENV */
#include "bm_settings.h"
#ifdef XBOXRECOMP_HAVE_OVERLAY
#include "xbox_settings.h"
#include "install.h"
#include "upscale.h"
#include "platform/recomp_exe_dir.h"
#include "platform/recomp_save_dir.h"
#endif

#ifdef XBOXRECOMP_HAVE_OVERLAY

enum { PG_MODS = 0, PG_SET = 1, PG_N = 2 };
enum { V_LIST = 0, V_DETAIL, V_APPROVE };
enum { R_NONE = 0, R_REVIEW, R_MOD, R_ACT_APPROVE, R_ACT_APPROVE_RESTART, R_ACT_ON, R_ACT_OFF, R_ACT_SETTINGS, R_ACT_BACK,
       R_ACT_CANCEL, R_SET, R_MSG, R_WHERE, R_EXTRA, R_ALL_ON, R_AI_HEAD, R_AI };

#define MAXR XBOX_PORT_ROWS
typedef struct {
    int kind, tone, what, mod, sp, si;           /* what R_*; mod index; settings page / line */
    unsigned flags;
} mrow;

static mrow s_r[PG_N][MAXR];
static int s_n[PG_N];
static int s_view = V_LIST, s_mod = -1, s_cursor = -1, s_from_review;
static char s_sha[65], s_hash_why[300], s_msg[400];
static int s_was_open, s_ready;

static const char *ps_owner_name(const char *id, char *buf, size_t n)
{
    if (!strcmp(id, BO3_PS_HOST_MOD))
        return "Burnout Mashup";
    for (int i = 0; i < mm_count(); i++)
        if (!strcmp(bo3_modfs_mod(i)->manifest.id, id)) {
            mm_name(i, buf, n);
            return buf;
        }
    return id;
}

static int first_settings_row(int mod)
{
    char id[BO3_MOD_ID_MAX + 1];
    snprintf(id, sizeof id, "%s", bo3_modfs_mod(mod)->manifest.id);
    for (int k = 0; k < s_n[PG_SET]; k++)
        if (s_r[PG_SET][k].what == R_SET && !strcmp(bo3_ps_plugin_mod(s_r[PG_SET][k].sp), id))
            return k;
    return -1;
}

static int has_settings(int mod)
{
    for (int p = 0; p < bo3_ps_plugin_count(); p++)
        if (!strcmp(bo3_ps_plugin_mod(p), bo3_modfs_mod(mod)->manifest.id))
            return 1;
    return 0;
}

static int add(int pg, int kind, int what, int mod, unsigned flags, int tone)
{
    if (s_n[pg] >= MAXR)
        return -1;
    s_r[pg][s_n[pg]] = (mrow){ kind, tone, what, mod, -1, -1, flags };
    return s_n[pg]++;
}

/* td030: the lines of upstream's Mods tab (modstab.c, BO-316, BO-327), which this page replaces: the mods folder (the default
 * one modfs scans, whether it exists yet or not) and the folders TAKEDAWN_MODS adds. */
static char s_where[420], s_extra[420];

static void make_where(void)
{
    char dir[1024], root[1024];
    const char *env = BM_GETENV("MODS");
    const char *def = bo3_modfs_default_dir_name();
    int portable = recomp_portable_root(root, sizeof root);

    s_extra[0] = 0;
    if (env && *env) {
        const size_t n = strcspn(env, ";");
        snprintf(s_extra, sizeof s_extra, "Also read: %.*s%s (TAKEDAWN_MODS).", (int)(n < 300 ? n : 300), env,
                 strchr(env, ';') ? " and the other folders named" : "");
    }
    if (def && *def)
        snprintf(dir, sizeof dir, "%s", def);
    else if (portable)
        snprintf(dir, sizeof dir, "%s/mods", root);
    else if (recomp_user_dir(RECOMP_DIR_DATA, BO3_USER_DIR, root, sizeof root))
        snprintf(dir, sizeof dir, "%s/mods", root);
    else
        snprintf(dir, sizeof dir, "mods");
    if (env && !*env)
        snprintf(s_where, sizeof s_where, "Mods folder: %.380s (off: TAKEDAWN_MODS is set empty)", dir);
    else
        snprintf(s_where, sizeof s_where, "Mods folder: %.380s%s", dir, portable ? " (portable mode)" : "");
}

static void build_mods(void)
{
    const int nm = mm_count();
    s_n[PG_MODS] = 0;
    if (s_view == V_LIST) {
        int wait = mm_count_status(MM_NEEDS_APPROVAL) + mm_count_status(MM_CODE_CHANGED);
        if (s_msg[0])
            add(PG_MODS, XBOX_PR_INFO, R_MSG, -1, 0, XBOX_PT_ATTN);      /* the last action's result, above the summary */
        add(PG_MODS, XBOX_PR_INFO, R_NONE, -1, 0, XBOX_PT_PLAIN);
        if (!s_where[0])
            make_where();
        add(PG_MODS, XBOX_PR_INFO, R_WHERE, -1, XBOX_PRF_NOCAPS, XBOX_PT_DIM);
        if (s_extra[0])
            add(PG_MODS, XBOX_PR_INFO, R_EXTRA, -1, XBOX_PRF_NOCAPS, XBOX_PT_DIM);
        if (wait && mm_approval_writable())
            add(PG_MODS, XBOX_PR_ITEM, R_REVIEW, -1, XBOX_PRF_ACTION, XBOX_PT_ATTN);
        if (!nm)
            add(PG_MODS, XBOX_PR_TEXT, R_NONE, -1, 0, 0);
        for (int i = 0; i < nm; i++)
            add(PG_MODS, XBOX_PR_ITEM, R_MOD, i, XBOX_PRF_NOCAPS, mm_tone(mm_status_of(i)));
        {
            int off = 0, ai = 0;
            for (int i = 0; i < nm; i++)
                off += mm_toggle_of(i) == MM_TOGGLE_ON;
            if (off)
                add(PG_MODS, XBOX_PR_ITEM, R_ALL_ON, -1, XBOX_PRF_ACTION, 0);
            for (int k = 0, t = bo3_upscale_row_count(); k < t; k++) {
                const char *x = bo3_upscale_row(k, 0);      /* a row with no text is not there now */
                int at;
                if (!x || !*x)
                    continue;
                if (!ai++)
                    add(PG_MODS, XBOX_PR_HEADER, R_AI_HEAD, -1, 0, 0);
                at = add(PG_MODS, XBOX_PR_ITEM, R_AI, -1, XBOX_PRF_ACTION, 0);
                if (at >= 0)
                    s_r[PG_MODS][at].sp = k;
            }
        }
        return;
    }
    if (s_view == V_DETAIL) {
        const mm_toggle t = mm_toggle_of(s_mod);
        add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, 0);          /* 0 its name */
        add(PG_MODS, XBOX_PR_INFO, R_NONE, s_mod, 0, 0);          /* 1 version, author, kind */
        add(PG_MODS, XBOX_PR_INFO, R_NONE, s_mod, 0, mm_tone(mm_status_of(s_mod)));   /* 2 status */
        add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, 0);          /* 3 why */
        add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, XBOX_PT_DIM);   /* 4 about */
        add(PG_MODS, XBOX_PR_INFO, R_NONE, s_mod, 0, 0);          /* 5 files / plugin */
        if (t == MM_TOGGLE_APPROVE)
            add(PG_MODS, XBOX_PR_ITEM, R_ACT_APPROVE, s_mod, XBOX_PRF_ACTION, 0);
        if (t == MM_TOGGLE_ON)
            add(PG_MODS, XBOX_PR_ITEM, R_ACT_ON, s_mod, XBOX_PRF_ACTION, 0);
        if (t == MM_TOGGLE_OFF || (t == MM_TOGGLE_APPROVE && mm_status_of(s_mod) == MM_NEEDS_APPROVAL))
            add(PG_MODS, XBOX_PR_ITEM, R_ACT_OFF, s_mod, XBOX_PRF_ACTION, 0);
        if (has_settings(s_mod))
            add(PG_MODS, XBOX_PR_ITEM, R_ACT_SETTINGS, s_mod, XBOX_PRF_ACTION, 0);
        add(PG_MODS, XBOX_PR_ITEM, R_ACT_BACK, s_mod, XBOX_PRF_ACTION, 0);
        return;
    }
    /* V_APPROVE */
    add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, 0);              /* name, by (the page's name says Approve plugin) */
    add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, s_sha[0] ? 0 : XBOX_PT_BAD);    /* the warning, or why not */
    if (s_sha[0]) {
        add(PG_MODS, XBOX_PR_INFO, R_NONE, s_mod, 0, 0);          /* program, size */
        add(PG_MODS, XBOX_PR_INFO, R_NONE, s_mod, 0, 0);          /* SHA-256, one line */
        add(PG_MODS, XBOX_PR_TEXT, R_NONE, s_mod, 0, XBOX_PT_DIM);
        if (xbox_OverlayCanRestart())
            add(PG_MODS, XBOX_PR_ITEM, R_ACT_APPROVE_RESTART, s_mod, XBOX_PRF_ACTION, XBOX_PT_ATTN);
        add(PG_MODS, XBOX_PR_ITEM, R_ACT_APPROVE, s_mod, XBOX_PRF_ACTION, 0);
    }
    add(PG_MODS, XBOX_PR_ITEM, R_ACT_CANCEL, s_mod, XBOX_PRF_ACTION, 0);
}

static void build_settings(void)
{
    const char *last = NULL;
    s_n[PG_SET] = 0;
    if (!bo3_ps_plugin_count()) {
        add(PG_SET, XBOX_PR_TEXT, R_NONE, -1, 0, 0);
        return;
    }
    if (bo3_ps_save_failed())
        add(PG_SET, XBOX_PR_INFO, R_NONE, -1, 0, XBOX_PT_ATTN);
    for (int p = 0; p < bo3_ps_plugin_count(); p++) {
        const char *id = bo3_ps_plugin_mod(p);
        int k;
        if (!last || strcmp(last, id)) {
            k = add(PG_SET, XBOX_PR_HEADER, R_NONE, -1, 0, 0);
            if (k >= 0)
                s_r[PG_SET][k].sp = p;
            last = id;
        }
        for (int i = 0; i < bo3_ps_count(p); i++) {
            k = add(PG_SET, XBOX_PR_ITEM, R_SET, -1, XBOX_PRF_CHOICE, 0);
            if (k >= 0) {
                s_r[PG_SET][k].sp = p;
                s_r[PG_SET][k].si = i;
            }
        }
    }
}

static void rebuild(void)
{
    if (s_mod >= mm_count())
        s_view = V_LIST, s_mod = -1;
    build_mods();
    build_settings();
}

/* The model read again when the overlay opens (it may have been closed for a while). */
static void ensure_fresh(void)
{
    const int open = xbox_OverlayIsOpen();
    if (!s_ready || (open && !s_was_open)) {
        mm_refresh();
        s_ready = 1;
        if (!s_was_open)
            s_msg[0] = 0;
    }
    s_was_open = open;
}

static int ov_rows(int page)
{
    ensure_fresh();
    rebuild();
    return page >= 0 && page < PG_N ? s_n[page] : 0;
}

static void hint_for_mod(int i, char *out, size_t n)
{
    char by[300], kind[40], about[1024];
    const mm_toggle t = mm_toggle_of(i);
    mm_byline(i, by, sizeof by);
    mm_kind(i, kind, sizeof kind);
    mm_about(i, about, sizeof about);
    if (strlen(about) > 220) {
        size_t k = 217;
        while (k && (about[k] & 0xC0) == 0x80)
            k--;
        memcpy(about + k, "\xE2\x80\xA6", 4);
    }
    snprintf(out, n, "%s  \xC2\xB7  %s\n%s%s", by, kind,
             t == MM_TOGGLE_APPROVE ? "Its plugin needs your approval: press right to review it. " : "", about);
    if (mm_status_of(i) >= MM_PLUGIN_NOT_LOADED || mm_status_of(i) == MM_CODE_CHANGED) {
        char w[600];
        size_t k = strlen(out);
        mm_why(i, w, sizeof w);
        snprintf(out + k, n > k ? n - k : 0, "%s%s", about[0] ? "\n" : "", w);
    }
}

/* "SHA-256  xxxxxxxxxxxxxxxx xxxxxxxxxxxxxxxx xxxxxxxxxxxxxxxx xxxxxxxxxxxxxxxx" (one line: no column to align) */
static void sha_line(const char *sha, char *out, size_t n)
{
    snprintf(out, n, "SHA-256  %.16s %.16s %.16s %.16s", sha, sha + 16, sha + 32, sha + 48);
}

static void ov_row(int page, int i, xbox_port_row *o)
{
    const mrow *r;
    char a[1024], b[600];
    if (page < 0 || page >= PG_N || i < 0 || i >= s_n[page])
        return;
    r = &s_r[page][i];
    o->kind = r->kind;
    o->flags = r->flags;
    o->tone = r->tone;
    if (page == PG_SET) {
        if (r->what == R_SET) {
            bo3_ps_line2(r->sp, r->si, o->label, sizeof o->label, o->value, sizeof o->value);
            bo3_ps_detail2(r->sp, r->si, a, sizeof a);
            snprintf(o->hint, sizeof o->hint, "%s%s", a, bo3_ps_pending() ? " Saved when you close this menu." : "");
        } else if (r->kind == XBOX_PR_HEADER) {
            snprintf(o->label, sizeof o->label, "%s", ps_owner_name(bo3_ps_plugin_mod(r->sp), a, sizeof a));
        } else if (r->kind == XBOX_PR_INFO) {
            snprintf(o->label, sizeof o->label, "A setting could not be saved: the game's log says why.");
        } else {
            snprintf(o->label, sizeof o->label, "No mod settings. Mods with a plugin, and mods with sliders in their "
                     "mod.toml, add their settings here.");   /* main21 patch 130 */
        }
        return;
    }
    if (s_view == V_LIST) {
        if (r->what == R_MOD) {
            mm_name(r->mod, o->label, sizeof o->label);
            snprintf(o->value, sizeof o->value, "%s", mm_chip(mm_status_of(r->mod)));
            hint_for_mod(r->mod, o->hint, sizeof o->hint);
        } else if (r->what == R_REVIEW) {
            const int w = mm_count_status(MM_NEEDS_APPROVAL) + mm_count_status(MM_CODE_CHANGED);
            snprintf(o->label, sizeof o->label, "Approve %d plugin%s waiting", w, w == 1 ? "" : "s");
            snprintf(o->hint, sizeof o->hint, "%d mod%s include%s a plugin (native code) that is not approved yet. "
                     "Select to review %s, one at a time.", w, w == 1 ? "" : "s", w == 1 ? "s" : "", w == 1 ? "it" : "them");
        } else if (r->what == R_MSG) {
            snprintf(o->label, sizeof o->label, "%s", s_msg);
        } else if (r->what == R_WHERE) {
            snprintf(o->label, sizeof o->label, "%s", s_where);
            snprintf(o->hint, sizeof o->hint, "Each mod goes in a folder of its own here, with its mod.toml.");
        } else if (r->what == R_EXTRA) {
            snprintf(o->label, sizeof o->label, "%s", s_extra);
        } else if (r->what == R_ALL_ON) {
            snprintf(o->label, sizeof o->label, "Turn every mod on");
            snprintf(o->hint, sizeof o->hint, "Saved at once and used from the next start. A mod with a plugin stays as it is: "
                     "it needs its approval.");
        } else if (r->what == R_AI_HEAD) {
            snprintf(o->label, sizeof o->label, "Sharper menu pictures");
        } else if (r->what == R_AI) {
            const char *x = bo3_upscale_row(r->sp, 0);
            snprintf(o->label, sizeof o->label, "%s", x ? x : "");
            snprintf(o->hint, sizeof o->hint, "%s", r->sp % 2 == 0
                     ? "Makes the game's menu pictures and loading screens sharper with an AI upscaler, here on this computer, "
                       "as a mod of their own that is switched on. It is in the mod list from the next start."
                     : "Deletes the sharper menu pictures this computer made; the game's own are back.");
        } else if (r->kind == XBOX_PR_INFO) {
            mm_summary(o->label, sizeof o->label);
        } else {
            snprintf(o->label, sizeof o->label, "No mods installed. Put a mod's folder (with its mod.toml) in your mods "
                     "folder, then start the game again.");
        }
        return;
    }
    if (s_view == V_DETAIL) {
        switch (i) {
        case 0: mm_name(r->mod, o->label, sizeof o->label); return;
        case 1:
            mm_byline(r->mod, a, sizeof a);
            mm_kind(r->mod, b, sizeof b);
            snprintf(o->label, sizeof o->label, "%s  \xC2\xB7  %s  \xC2\xB7  folder %s", a, b,
                     strrchr(bo3_modfs_mod(r->mod)->folder, '\\') ? strrchr(bo3_modfs_mod(r->mod)->folder, '\\') + 1
                     : strrchr(bo3_modfs_mod(r->mod)->folder, '/') ? strrchr(bo3_modfs_mod(r->mod)->folder, '/') + 1
                     : bo3_modfs_mod(r->mod)->folder);
            return;
        case 2: snprintf(o->label, sizeof o->label, "Status: %s", mm_chip(mm_status_of(r->mod))); return;
        case 3: mm_why(r->mod, o->label, sizeof o->label); return;
        case 4:
            mm_about(r->mod, o->label, sizeof o->label);
            if (!o->label[0])
                snprintf(o->label, sizeof o->label, "(no description)");
            return;
        case 5:
            if (mm_has_plugin(r->mod)) {
                long sz;
                mm_module(r->mod, a, sizeof a, &sz);
                snprintf(o->label, sizeof o->label, "Plugin file: %s%s", a, sz >= 0 ? "" : " (not found)");
                if (sz >= 0) {
                    size_t k = strlen(o->label);
                    snprintf(o->label + k, sizeof o->label - k, " (%ld KB)", (sz + 1023) / 1024);
                }
            } else {
                mm_files(r->mod, o->label, sizeof o->label);
                if (!o->label[0])
                    snprintf(o->label, sizeof o->label, "No files shared with other mods.");
            }
            return;
        default: break;
        }
    } else if (i < 5 && r->kind != XBOX_PR_ITEM) {    /* V_APPROVE */
        long sz;
        switch (i) {
        case 0:
            mm_name(r->mod, a, sizeof a);
            mm_byline(r->mod, b, sizeof b);
            snprintf(o->label, sizeof o->label, "%s    %s", a, b);
            return;
        case 1:
            if (!s_sha[0])
                snprintf(o->label, sizeof o->label, "%s Nothing can be approved.", s_hash_why);
            else
                snprintf(o->label, sizeof o->label, "This mod includes a program that runs inside the game with the same "
                         "permissions as you: it can read and change your files. Only approve mods from people you trust.");
            return;
        case 2:
            mm_module(r->mod, a, sizeof a, &sz);
            snprintf(o->label, sizeof o->label, "Program  %s  (%ld KB)", a, sz >= 0 ? (sz + 1023) / 1024 : 0L);
            return;
        case 3: sha_line(s_sha, o->label, sizeof o->label); return;
        case 4:
            snprintf(o->label, sizeof o->label, "Approving allows exactly this file. If it ever changes, you will be "
                     "asked again. The mod is turned on, and its plugin starts when the game starts again.");
            return;
        default: break;
        }
    }
    switch (r->what) {
    case R_ACT_APPROVE:
        snprintf(o->label, sizeof o->label, s_view == V_APPROVE && xbox_OverlayCanRestart()
                 ? "Approve and turn on (restart later)" : "Approve and turn on");
        snprintf(o->hint, sizeof o->hint, "%s", s_view == V_APPROVE
                 ? "Approves exactly the file above and turns the mod on. It starts at the next start of the game."
                 : "Shows the plugin's file and its fingerprint (SHA-256) first; nothing is approved until you confirm.");
        break;
    case R_ACT_APPROVE_RESTART:
        snprintf(o->label, sizeof o->label, "Approve, turn on and restart now");
        snprintf(o->hint, sizeof o->hint, "Approves exactly the file above, turns the mod on and restarts the game "
                 "now, so the plugin runs straight away.");
        break;
    case R_ACT_ON:
        snprintf(o->label, sizeof o->label, "Turn on");
        snprintf(o->hint, sizeof o->hint, "Used from the next start of the game.");
        break;
    case R_ACT_OFF:
        snprintf(o->label, sizeof o->label, "Turn off");
        snprintf(o->hint, sizeof o->hint, "%s", mm_has_plugin(r->mod)
                 ? "Turns the mod off and removes its plugin's approval (you can approve it again later)."
                 : "Not used from the next start of the game.");
        break;
    case R_ACT_SETTINGS:
        snprintf(o->label, sizeof o->label, "Settings of this mod");
        break;
    case R_ACT_BACK:
        snprintf(o->label, sizeof o->label, "Back to the mods");
        break;
    case R_ACT_CANCEL:
        snprintf(o->label, sizeof o->label, "Cancel");
        snprintf(o->hint, sizeof o->hint, "Nothing is approved or changed.");
        break;
    default: break;
    }
}

static int row_of_mod(int mod)
{
    for (int k = 0; k < s_n[PG_MODS]; k++)
        if (s_r[PG_MODS][k].what == R_MOD && s_r[PG_MODS][k].mod == mod)
            return k;
    return -1;
}

static int row_of_what(int what)
{
    for (int k = 0; k < s_n[PG_MODS]; k++)
        if (s_r[PG_MODS][k].what == what)
            return k;
    return -1;
}

static unsigned go(int view, int mod, int cursor_what)
{
    s_view = view;
    s_mod = mod;
    rebuild();
    s_cursor = cursor_what >= 0 ? row_of_what(cursor_what) : view == V_LIST ? row_of_mod(mod) : -1;   /* -1: the first action */
    return XBOX_PI_VIEW;
}

static unsigned open_approval(int mod, int from_review)
{
    s_from_review = from_review;
    if (!mm_hash(mod, s_sha, s_hash_why, sizeof s_hash_why))
        s_sha[0] = 0;
    return go(V_APPROVE, mod, xbox_OverlayCanRestart() ? R_ACT_APPROVE_RESTART : R_ACT_APPROVE) | XBOX_PI_ASK;
}

static unsigned back_to_list(int mod)
{
    s_view = V_LIST;
    rebuild();
    s_cursor = mod >= 0 ? row_of_mod(mod) : -1;
    s_view = V_LIST;
    return XBOX_PI_VIEW;
}

static unsigned toggle(int mod)
{
    char why[300];
    char name[256];
    mm_name(mod, name, sizeof name);
    switch (mm_toggle_of(mod)) {
    case MM_TOGGLE_ON:
        if (mm_turn_on(mod, why, sizeof why))
            snprintf(s_msg, sizeof s_msg, mm_live_now(mod) ? "%s: on now." : "%s: on after a restart.", name);
        else
            snprintf(s_msg, sizeof s_msg, "%s", why);
        return XBOX_PI_DONE;
    case MM_TOGGLE_OFF:
        if (mm_turn_off(mod, why, sizeof why))
            snprintf(s_msg, sizeof s_msg, mm_live_now(mod) ? "%s: off now." : "%s: off after a restart.", name);
        else
            snprintf(s_msg, sizeof s_msg, "%s", why);
        return XBOX_PI_DONE;
    case MM_TOGGLE_APPROVE:
        return open_approval(mod, 0);
    default:
        return XBOX_PI_NONE;
    }
}

static unsigned approve(int mod, int restart)
{
    char why[300], name[256];
    mm_name(mod, name, sizeof name);
    if (!mm_approve_and_on(mod, s_sha, why, sizeof why)) {
        snprintf(s_msg, sizeof s_msg, "%s", why);
        return back_to_list(mod);
    }
    if (restart && xbox_OverlayRestartNow())
        return XBOX_PI_DONE;
    snprintf(s_msg, sizeof s_msg, "%s: approved and on. Its plugin starts when you restart the game.", name);
    if (s_from_review) {                              /* the next one waiting, if any */
        for (int i = 0; i < mm_count(); i++) {
            mm_status st = mm_status_of(i);
            if ((st == MM_NEEDS_APPROVAL || st == MM_CODE_CHANGED) && mm_toggle_of(i) == MM_TOGGLE_APPROVE)
                return open_approval(i, 1);
        }
    }
    return back_to_list(mod);
}

static unsigned ov_input(int page, int i, int act)
{
    const mrow *r;
    if (act == XBOX_PA_OPEN) {                        /* from Settings > MODS: the list, from the top */
        if (page == PG_MODS) {
            s_view = V_LIST;
            s_mod = -1;
            s_msg[0] = 0;
            mm_refresh();
            s_ready = 1;
            rebuild();
            s_cursor = -1;
        }
        return XBOX_PI_VIEW;
    }
    if (page < 0 || page >= PG_N)
        return 0;
    if (page == PG_SET) {
        if (act == XBOX_PA_BACK || i < 0 || i >= s_n[PG_SET] || s_r[PG_SET][i].what != R_SET)
            return 0;
        r = &s_r[PG_SET][i];
        if (act == XBOX_PA_X)
            return XBOX_PI_NONE;
        if (act == XBOX_PA_DEFAULT && bo3_ps_is_default(r->sp, r->si))
            return XBOX_PI_NONE;
        return bo3_ps_request(r->sp, r->si, act == XBOX_PA_LEFT ? -1 : act == XBOX_PA_DEFAULT ? 0 : 1)
               ? XBOX_PI_DONE : XBOX_PI_NONE;
    }
    if (act == XBOX_PA_BACK) {
        if (s_view == V_APPROVE) {
            snprintf(s_msg, sizeof s_msg, "Nothing was approved.");
            fprintf(stderr, "[MODS] %s: approval cancelled\n", bo3_modfs_mod(s_mod)->manifest.id);
            return s_from_review ? back_to_list(s_mod) : go(V_DETAIL, s_mod, -1);
        }
        if (s_view == V_DETAIL)
            return back_to_list(s_mod);
        return 0;                                     /* the list: the overlay closes */
    }
    if (i < 0 || i >= s_n[PG_MODS])
        return XBOX_PI_NONE;
    r = &s_r[PG_MODS][i];
    if (r->what == R_MOD) {
        s_msg[0] = 0;
        if (act == XBOX_PA_SELECT)
            return go(V_DETAIL, r->mod, -1);
        if (act == XBOX_PA_LEFT || act == XBOX_PA_RIGHT)
            return toggle(r->mod);
        if (act == XBOX_PA_X && has_settings(r->mod)) {
            rebuild();
            xbox_OverlayShowPortPage(PG_SET, first_settings_row(r->mod));
            return XBOX_PI_DONE;
        }
        return XBOX_PI_NONE;
    }
    if (act != XBOX_PA_SELECT)
        return XBOX_PI_NONE;
    switch (r->what) {
    case R_REVIEW:
        for (int k = 0; k < mm_count(); k++)
            if (mm_toggle_of(k) == MM_TOGGLE_APPROVE
                    && (mm_status_of(k) == MM_NEEDS_APPROVAL || mm_status_of(k) == MM_CODE_CHANGED))
                return open_approval(k, 1);
        return XBOX_PI_NONE;
    case R_ACT_APPROVE:
        return s_view == V_APPROVE ? approve(r->mod, 0) : open_approval(r->mod, 0);
    case R_ACT_APPROVE_RESTART:
        return approve(r->mod, 1);
    case R_ACT_ON:
    case R_ACT_OFF: {
        const unsigned u = toggle(r->mod);
        return (u & XBOX_PI_VIEW) ? u : back_to_list(r->mod);
    }
    case R_ACT_SETTINGS:
        rebuild();
        xbox_OverlayShowPortPage(PG_SET, first_settings_row(r->mod));
        return XBOX_PI_DONE;
    case R_ACT_BACK:
        return back_to_list(r->mod);
    case R_ALL_ON: {
        char why[300];
        int done = 0, failed = 0;
        for (int k = 0; k < mm_count(); k++)
            if (mm_toggle_of(k) == MM_TOGGLE_ON) {
                if (mm_turn_on(k, why, sizeof why))
                    done++;
                else
                    failed++;
            }
        if (failed)
            snprintf(s_msg, sizeof s_msg, "%d turned on; %d not saved: the log says why.", done, failed);
        else
            snprintf(s_msg, sizeof s_msg, "%d mod%s on after a restart.", done, done == 1 ? "" : "s");
        return XBOX_PI_DONE;
    }
    case R_AI:
        bo3_upscale_row(r->sp, 1);
        return XBOX_PI_DONE;
    case R_ACT_CANCEL:
        snprintf(s_msg, sizeof s_msg, "Nothing was approved.");
        fprintf(stderr, "[MODS] %s: approval cancelled\n", bo3_modfs_mod(r->mod)->manifest.id);
        return s_from_review ? back_to_list(r->mod) : go(V_DETAIL, r->mod, -1);
    default:
        return XBOX_PI_NONE;
    }
}

static int ov_cursor(int page)
{
    int c = s_cursor;
    s_cursor = -1;
    if (page != PG_MODS)
        return -1;
    if (c == -1 && s_view == V_DETAIL) {
        for (int k = 0; k < s_n[PG_MODS]; k++)
            if (s_r[PG_MODS][k].kind == XBOX_PR_ITEM)
                return k;                             /* the first action */
    }
    return c;
}

static const char *ov_name(int page)
{
    return page == PG_SET ? "Mod settings" : "Mods";
}

static const char *ov_crumb(int page)
{
    if (page == PG_SET)
        return "Mod settings";
    return s_view == V_APPROVE ? "Approve plugin" : s_view == V_DETAIL ? "Mod details" : "Mods";
}

static const char *ov_prompt(int page, int i, int b)
{
    const mrow *r;
    if (page == PG_SET) {
        if (b == XBOX_PB_B) return "Back";
        if (i < 0 || i >= s_n[PG_SET] || s_r[PG_SET][i].what != R_SET) return NULL;
        return b == XBOX_PB_DPAD ? "Change" : b == XBOX_PB_Y ? "Default" : b == XBOX_PB_A ? "Next value" : NULL;
    }
    if (b == XBOX_PB_B)
        return s_view == V_LIST ? "Close" : s_view == V_APPROVE ? "Cancel" : "Back";
    if (i < 0 || i >= s_n[PG_MODS])
        return NULL;
    r = &s_r[PG_MODS][i];
    if (r->what != R_MOD)
        return b == XBOX_PB_A && r->kind == XBOX_PR_ITEM ? "Select" : NULL;
    switch (b) {
    case XBOX_PB_A: return "Details";
    case XBOX_PB_DPAD:
        switch (mm_toggle_of(r->mod)) {
        case MM_TOGGLE_ON: return "Turn on";
        case MM_TOGGLE_OFF: return "Turn off";
        case MM_TOGGLE_APPROVE: return "Approve and turn on";
        default: return NULL;
        }
    case XBOX_PB_X: return has_settings(r->mod) ? "Settings" : NULL;
    default: return NULL;
    }
}

static int ov_restart(char *why, unsigned n)
{
    if (!s_ready)
        return 0;
    return mm_restart_count(why, n);
}

static const xbox_port_page_ops k_ops = {
    ov_rows, ov_row, ov_input, ov_cursor, ov_name, ov_crumb, ov_prompt, ov_restart
};

static int s_on;

extern void bo3_modsmenu_set_overlay(int (*open)(void));   /* modsmenu.c */

/* A on Settings > MODS (modsmenu.c): 1 the overlay opens on the MODS page; 0 there is no overlay to open (headless,
 * RECOMP_OVERLAY=0): the native page then, as before. */
static int mmov_open(void)
{
    return s_on && xbox_OverlayRequestOpenPage(PG_MODS);
}

/* At the start, after bo3_modsmenu_start: with a mod folder in use (as the MODS line), unless TAKEDAWN_MODS_MENU=0 or
 * BMASHUP_MODS_UI=native. The overlay may not exist yet (its window comes later): each A asks it then. */
/* main21 patch 93: the pause menu's MOD SETTINGS row opens the overlay on the MOD SETTINGS page (the title is paused by it) */
static int mmov_open_settings(void)
{
    return s_on && xbox_OverlayRequestOpenPage(PG_SET);
}

int bo3_mmov_start(void)
{
    const char *e = getenv("BMASHUP_MODS_UI"), *h = BM_GETENV("MODS_MENU");
    s_on = 0;
    if (h && h[0] == '0' && !h[1])
        return 0;
    if (e && !strcmp(e, "native")) {
        fprintf(stderr, "[MODS] BMASHUP_MODS_UI=native: the native MODS page\n");
        return 0;
    }
    xbox_OverlaySetPortPages(PG_N, &k_ops);
    bo3_modsmenu_set_overlay(mmov_open);
    {
        extern void bo3_modsmenu_set_overlay_live(int (*live)(void));
        bo3_modsmenu_set_overlay_live(xbox_OverlayAvailable);   /* main21 patch 134: no MODS line while the overlay has the page */
    }
    {
        extern void bo3_menu_set_pause_open(int (*open_settings)(void));
        bo3_menu_set_pause_open(mmov_open_settings);   /* main21 patch 93: the pause menu's MOD SETTINGS row */
    }
    s_on = 1;
    fprintf(stderr, "[MODS] MODS and MOD SETTINGS are pages of the overlay (BMASHUP_MODS_UI=native: the native page)\n");
    return 1;
}

#else

int bo3_mmov_start(void) { return 0; }

#endif
