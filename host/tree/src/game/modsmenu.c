/*
 * modsmenu.c - a MODS page in the title's own Settings menu (Driver Details >
 * Settings), for installed mods (modfs.h): each mod on or off from the next
 * start. Listed only when a mod folder is in use (TAKEDAWN_MODS, or Android's
 * mods folder: the player's own opt-in to mods); TAKEDAWN_MODS_MENU=0 hides
 * it. Otherwise the menu is the title's (and menuentry.c's), as before.
 *
 * Where: the Settings page object 0x55ABC4, built by sub_00085170 on the
 * Settings state's enter (menuentry.c describes it). MODS is one more line
 * of the title's list widget (sub_000F0EA0), after the title's four lines
 * and, when menuentry.c lists it, TAKEDAWN SETTINGS.
 *
 * The MODS page is the same page object, list widget, title, sounds and
 * transitions, built in a second mode:
 *   - A on MODS is the title's own A (its select sound, the page's exit),
 *     then the Settings state's event 5 (sub_000696D0), which would look the
 *     cursor up in its four-entry next-page table (0x3EAF34) and change
 *     state. The "mm_flow_sel" mark (after `push 0x65857D40`, 0x69733) makes
 *     that the state machine's own no-op (sub_000146E0 returns when the target
 *     is the current state: the pushed hash becomes the current state's, from
 *     the machine's table [0x567170 + 0xC], 16-byte entries {hash lo, hash hi,
 *     offset from the machine}) and builds the page again through
 *     sub_00085170 with the MODS lines and the title MODS: the page's own
 *     enter animation. Before the mark the title has already read the table
 *     entry for the cursor (a line past its four), but sub_000146E0 returns
 *     before using it when the target is the current state; so A is let
 *     through only when that hash is found, and on no other line from the
 *     fifth on (a line the title does not have, ours or menuentry.c's).
 *     Event 5 for line 3 (EA GAMES TRAX) does not reach the mark: the MODS
 *     page never lets A through on its line 3 either.
 *   - B on the MODS page is the title's own B (back sound, exit); event 5
 *     with result 3 would go to Driver Details: "mm_flow_back" (after
 *     `push 0xEF6E02D9`, 0x696F8) makes it the same no-op and builds the
 *     Settings list again, the cursor on MODS (where it is now: the overlay
 *     can turn menuentry.c's line on or off while the page is open).
 *   - A on a mod's line or APPLY (menuentry.c's si_select mark, after the A
 *     test, 0x853B4) is taken here, the title never starts its exit for it:
 *     the line acts and the title's select sound (sub_00141010, as at
 *     0x8542B) plays. Up, down and B stay the title's.
 * The list widget makes its line frames once, at set-up, at most 9
 * (WIDGET_MAX): six mods fit one page, more are shown four to a page with
 * PREVIOUS PAGE / NEXT PAGE, and a page change is the title's own A and exit,
 * then mm_flow_sel builds the next page.
 *
 * Choices are kept here, as chosen (whatever the mod list says later),
 * until APPLY, which saves them through bo3_modfs_set_enabled (the mod list,
 * written whole or not at all); they are used from the next start. Nothing
 * here reads or writes a file itself.
 * Every text shown, mod text included, goes through put_label: printable
 * ASCII in upper case (the title font's), anything else '?', cut to fit.
 *
 * Native code (plugins.h, docs/native-plugins.md): a mod with a module for
 * this system shows CODE (approved from the next start) or CODE? (not), and
 * A goes OFF -> ON (its files only) -> APPROVE CODE -> ON + CODE -> OFF.
 * The APPROVE step hashes the module (never loads it) and shows the warning,
 * the module and its hash on the two lines below; only A again approves those
 * bytes, moving away cancels. Nothing is written before APPLY, which removes
 * approvals first, then saves the mod list, then adds approvals: a failure
 * stops what follows, so what is saved never allows more code than was
 * chosen. A mod turned off, or on without its code, loses its approval. The
 * plugins of this start stay as they are: a change is for the next start,
 * and a running plugin runs until Takedawn exits.
 *
 * gp main20m patch 63 - with the Takedawn overlay (modsmenu_ov.c registers it: bo3_modsmenu_set_overlay), A on MODS opens the
 * overlay on its MODS page instead (scrolling, no row limit, approve and turn on in one action); this page is then never
 * built. Without an overlay (headless, RECOMP_OVERLAY=0, the D3D11 build) or with BMASHUP_MODS_UI=native, this page as
 * before.
 *
 * gp slice camset1 - MOD SETTINGS (bmashup.settings, bm_settings.h): when a
 * running plugin declared settings, the MODS page's first line is MOD
 * SETTINGS. A on it is a page change (the title's own A and exit, then
 * mm_flow_sel builds the page again in a third mode): the settings of one
 * plugin, one line each ("LABEL  VALUE"), NEXT MOD SETTINGS first when more
 * than one plugin has settings, then the details and information lines. A on
 * a setting steps its value (bo3_ps_step: saved at once, then the plugin's
 * callback, on this thread); B is the title's B and mm_flow_back builds the
 * MODS page again, the cursor on MOD SETTINGS. With the line the MODS page
 * shows five mods on one page, or three a page with PREVIOUS / NEXT, so it
 * never has more than WIDGET_MAX lines; a line that changes the page is never
 * line 3 (event 5 for line 3 does not reach mm_flow_sel).
 */
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#include "platform/recomp_patch.h"
#include "recomp_types.h"
#include "modfs.h"
#include "bm_env.h"                    /* pfid1: BM_GETENV */
#include "plugins.h"
#include "bm_settings.h"          /* gp camset1: MOD SETTINGS */

extern RECOMP_TLS uint32_t g_eax, g_ebx, g_ecx, g_edx, g_esi, g_edi, g_esp, g_ebp, g_seh_ebp;
extern ptrdiff_t g_xbox_mem_offset;
extern void sub_001D2879(void);          /* the title's heap: (size, tag), stdcall */
extern void sub_00085170(void);          /* the Settings page's set-up: eax = the page */
extern void sub_00141010(void);          /* a front-end sound, stdcall 6, eax */

#define MM8(va)  (*(uint8_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define MM16(va) (*(uint16_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define MM32(va) (*(uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

#define SP_PAGE      0x0055ABC4u
#define SP_CURSOR    (SP_PAGE + 4)
#define SP_COUNT     (SP_PAGE + 6)
#define SP_ITEMS     (SP_PAGE + 8)
#define FLOW         0x00567170u          /* the front end's state machine */
#define STRTAB       0x004D532Cu          /* [[STRTAB] + 0xC] = the string pointers */
#define TITLE_SLOT   0x6C4u               /* the Settings page's title string */
#define HEAP_TAG     0x4D4F4453u          /* "MODS" */

#define MAX_LINES    9                    /* WIDGET_MAX, and the Settings list (at most 6) */
#define LABEL_CH     48                   /* UTF-16 units per label, the terminator included */
#define WIDGET_MAX   9                    /* the list widget (0x5509F4) keeps two 9-entry arrays of line frames
                                           * (+0x14, +0x38); a tenth line would overwrite its next fields */
#define PAGE_ALL     6                    /* up to 6 mods: one page (6 + APPLY + details + info = 9) */
#define PAGE_MODS    4                    /* more: 4 a page + PREVIOUS + NEXT + 3 = 9 */
#define NAME_CH      24                   /* a longer name is cut to 22 and ".." */
#define TITLE_LINES  4                    /* the title's own Settings lines; its next-page table has 4 */

static uint32_t s_blk;                     /* items (MAX_LINES * 8), then labels, then the title */
static int s_hidden;                       /* TAKEDAWN_MODS_MENU=0, read at the start */
static int s_mode;                         /* 0 the Settings list, 1 the MODS page, 2 MOD SETTINGS (camset1) */
static int s_set_line = -1;                /* MOD SETTINGS on the MODS page */
static int s_pending_mode = -1;            /* the mode to build at the next event 5 (MOD SETTINGS / NEXT MOD) */
static int s_ps;                           /* the plugin whose settings mode 2 shows (bo3_ps_* numbering) */
static int s_nextmod_line = -1;            /* NEXT MOD SETTINGS in mode 2 */
static int s_line_set[MAX_LINES];          /* mode 2: the setting on each line, -1 none */
static int s_want_cursor = -1;             /* the cursor for the page being built */
static int s_rebuilding;                   /* sub_00085170 called from here: the page asked for */
static int s_page_built;                   /* a page change: the cursor to its first mod */
static int s_mods_line = -1;               /* MODS in the Settings list */
static int s_first;                        /* the first mod shown */
static int s_nlines, s_apply_line, s_info_line, s_prev_line, s_next_line, s_detail_line = -1;
static char s_detail[LABEL_CH], s_info[LABEL_CH];
static int s_line_mod[MAX_LINES];
static int s_page_pending = -1;            /* the first mod of the page to build at the next event 5 */
static unsigned char s_touched[BO3_MODFS_MAX_MODS]; /* the player chose for it (s_choice) */
static unsigned char s_choice[BO3_MODFS_MAX_MODS];  /* on / off as chosen, whatever the mod list says */
static unsigned char s_saved[BO3_MODFS_MAX_MODS];   /* what the mod list says (read at each build and APPLY) */
static int s_save_failed;                  /* the last APPLY could not save every choice */

/* Native code, for mods with a module for this system (has_code). */
static unsigned char s_code[BO3_MODFS_MAX_MODS];        /* with s_choice: its code approved, as chosen */
static char s_code_sha[BO3_MODFS_MAX_MODS][65];         /* its module's bytes as last hashed here ("" not yet) */
static char s_start_sha[BO3_MODFS_MAX_MODS][65];        /* as this start hashed them ("" not hashed) */
static unsigned char s_code_saved[BO3_MODFS_MAX_MODS];  /* the approval file approves it (its bytes, when known) */
static unsigned char s_code_entry[BO3_MODFS_MAX_MODS];  /* the approval file names it */
static unsigned char s_code_changed[BO3_MODFS_MAX_MODS];/* named for other bytes than the known ones */
static unsigned char s_code_missing[BO3_MODFS_MAX_MODS];/* its module could not be hashed (the log says why) */
static bo3_approvals_state s_appr;                      /* the approval file (read at each build and APPLY) */
static int s_appr_said;                                 /* "cannot be changed here" logged */
static int s_confirm = -1;                              /* the mod whose approval waits for A, the warning shown */

/* Made by the build (cmake/modsmenu_marks.cmake): 1 when the generated code
 * calls si_items, si_select, mm_flow_sel and mm_flow_back where
 * config/patches.json puts them. */
extern int bo3_modsmenu_gen_marks(void);
static int s_flow;                         /* both marks generated and reaching this file's functions */
static int (*s_ov_open)(void);             /* main20m patch 63: opens the overlay's MODS page (modsmenu_ov.c), 1 done */
static int s_probing, s_probed;            /* bo3_modsmenu_start calls each mark once: bits 1, 2 */

static int mm_on(void)
{
    return s_flow && g_xbox_mem_offset && !s_hidden && bo3_modfs_folder_count() > 0;
}

static uint32_t label_va(int i) { return s_blk + MAX_LINES * 8 + (uint32_t)i * LABEL_CH * 2; }
static uint32_t title_va(void)  { return s_blk + MAX_LINES * 8 + MAX_LINES * LABEL_CH * 2; }

/* Text for the title's font: printable ASCII in upper case; a UTF-8
 * character (or any other byte) is one '?'. At most n - 1 characters. */
static void shown(char *out, size_t n, const char *s)
{
    size_t k = 0;
    const unsigned char *p = (const unsigned char *)s;
    while (*p && k + 1 < n) {
        if (*p >= 0x20 && *p < 0x7F) {
            out[k++] = (char)(*p >= 'a' && *p <= 'z' ? *p - 'a' + 'A' : *p);
            p++;
        } else {
            out[k++] = '?';
            for (p++; (*p & 0xC0) == 0x80; p++)
                ;
        }
    }
    out[k] = 0;
}

static void put_label(uint32_t va, const char *s)
{
    char t[LABEL_CH];
    int i;
    shown(t, sizeof t, s);
    for (i = 0; t[i]; i++)
        MM16(va + (uint32_t)i * 2) = (uint8_t)t[i];
    MM16(va + (uint32_t)i * 2) = 0;
}

static uint32_t mm_block(void)
{
    if (!s_blk) {
        uint32_t a = g_eax, c = g_ecx, d = g_edx, sp = g_esp;
        uint32_t size = MAX_LINES * 8 + MAX_LINES * LABEL_CH * 2 + 16 * 2;
        PUSH32(g_esp, HEAP_TAG);
        PUSH32(g_esp, size);
        PUSH32(g_esp, 0);                   /* the return address its ret takes */
        sub_001D2879();
        s_blk = g_eax;
        g_eax = a; g_ecx = c; g_edx = d; g_esp = sp;
        if (s_blk)
            put_label(title_va(), "MODS");
    }
    return s_blk;
}

/* The title's front-end select sound: what A plays (0x85415..0x8542B). */
static void play_select(void)
{
    uint32_t a = g_eax, c = g_ecx, d = g_edx, sp = g_esp;
    PUSH32(g_esp, 0);
    PUSH32(g_esp, MM8(0x411560) ? 1u : 0u);
    PUSH32(g_esp, 0x3F800000u);
    PUSH32(g_esp, 0x3ECCCCCDu);
    PUSH32(g_esp, 0xB701A7E2u);
    PUSH32(g_esp, 0xA9E00000u);
    PUSH32(g_esp, 0);
    g_eax = 0;
    sub_00141010();
    g_eax = a; g_ecx = c; g_edx = d; g_esp = sp;
}

/* ---- the mods and the choices ---- */

static int nmods(void)
{
    int n = bo3_modfs_mod_count();
    return n < BO3_MODFS_MAX_MODS ? n : BO3_MODFS_MAX_MODS;
}

static int has_code(int i)         /* usable, with a module for this system */
{
    const bo3_mod *m = bo3_modfs_mod(i);
    return m->usable && m->manifest.plugin && m->manifest.plugin_path[0];
}

/* What the mod list and the approval file say now (either may have become
 * readable since). */
static void read_saved(void)
{
    int code = 0;
    s_appr = bo3_plugins_approvals();
    for (int i = 0; i < nmods(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        const char *sha;
        s_saved[i] = (unsigned char)(m->usable ? bo3_modfs_enabled_next(m->manifest.id) : m->enabled);
        if (!has_code(i))
            continue;
        code = 1;
        bo3_plugins_state(i, NULL, 0, s_start_sha[i], sizeof s_start_sha[i]);
        sha = s_code_sha[i][0] ? s_code_sha[i] : s_start_sha[i];       /* the bytes as last seen */
        s_code_entry[i] = (unsigned char)(bo3_plugins_approvals_of(m->manifest.id, NULL, 0) > 0);
        s_code_saved[i] = (unsigned char)(sha[0] ? bo3_plugins_approved_for(m->manifest.id, sha) : s_code_entry[i]);
        s_code_changed[i] = (unsigned char)(sha[0] && s_code_entry[i] && !s_code_saved[i]);
    }
    if (code && !s_appr_said && (s_appr == BO3_APPROVALS_KEPT || s_appr == BO3_APPROVALS_BAD)) {
        s_appr_said = 1;
        fprintf(stderr, "[MODS] the approval file is left as it is: native code cannot be approved or removed on this page "
                        "(%s; docs/native-plugins.md)\n", s_appr == BO3_APPROVALS_BAD
                        ? "it cannot be read now, or is not an approval file"
                        : "it has entries this page does not write back: edit it by hand");
    }
}

static int chosen(int i)           /* on at the next start, with the player's choice */
{
    return s_touched[i] ? s_choice[i] : s_saved[i];
}

static int code_chosen(int i)      /* its code approved from the next start, with the player's choice */
{
    return s_touched[i] ? s_code[i] : s_code_saved[i];
}

/* Its code at the next start differs from this start's: approved now vs
 * approved for the next one (and on). Nothing to compare when no plugin can
 * run in this process. */
static int code_differs(int i)
{
    return has_code(i) && !bo3_plugins_off() && (chosen(i) && code_chosen(i)) != bo3_plugins_was_approved(i);
}

/* A CODE choice can be made: plugins run here and the page may write the
 * approval file. */
static int code_possible(void)
{
    return !bo3_plugins_off() && (s_appr == BO3_APPROVALS_ABSENT || s_appr == BO3_APPROVALS_OK);
}

static int code_add(int i)         /* APPLY would approve its bytes */
{
    return s_touched[i] && has_code(i) && s_choice[i] && s_code[i]
           && !bo3_plugins_approved_for(bo3_modfs_mod(i)->manifest.id, s_code_sha[i]);
}

static int code_remove(int i)      /* APPLY would remove its approval (an unreadable file may hold one) */
{
    return s_touched[i] && has_code(i) && !(s_choice[i] && s_code[i])
           && (s_code_entry[i] || s_appr == BO3_APPROVALS_BAD);
}

static int code_adds(void)
{
    for (int i = 0; i < nmods(); i++)
        if (code_add(i))
            return 1;
    return 0;
}

static int changes_unsaved(void)   /* 1: APPLY would change the mod list or the approval file */
{
    for (int i = 0; i < nmods(); i++)
        if ((bo3_modfs_mod(i)->usable && chosen(i) != s_saved[i]) || code_add(i) || code_remove(i))
            return 1;
    return 0;
}

static int restart_needed(void)    /* 1: the mod list, or an approval, differs from what this start used */
{
    for (int i = 0; i < nmods(); i++)
        if ((bo3_modfs_mod(i)->usable && s_saved[i] != bo3_modfs_mod(i)->enabled)
                || (has_code(i) && !bo3_plugins_off() && (s_saved[i] && s_code_saved[i]) != bo3_plugins_was_approved(i)))
            return 1;
    return 0;
}

/* Another mod with the same id (both refused by modfs.c), or NULL. */
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

/* The last part of a host path (never the whole of it on screen). */
static const char *last_part(const char *path)
{
    const char *a = strrchr(path, '/'), *b = strrchr(path, '\\');
    const char *f = a > b ? a : b;
    return f ? f + 1 : path;
}

/* ON / OFF, a star when the next start differs from this one (its code
 * included); or why a mod cannot be used. */
static const char *state_word(int i)
{
    const bo3_mod *m = bo3_modfs_mod(i);
    if (!m->usable)
        return m->needs ? "NEEDS MOD" : m->conflict ? "CONFLICT" : shared_id(m) ? "SAME ID" : "INVALID";   /* P3 (P-9) /
                                                                                         * GP-DEPS1: bm_admit.c */
    if (chosen(i) == m->enabled && !code_differs(i))
        return m->enabled ? "ON" : "OFF";
    return chosen(i) ? "ON*" : "OFF*";
}

static const char *mod_name(const bo3_mod *m)
{
    const char *f;
    if (m->manifest.name[0])
        return m->manifest.name;
    f = strrchr(m->folder, '/');
    if (!f || (strrchr(m->folder, '\\') && strrchr(m->folder, '\\') > f))
        f = strrchr(m->folder, '\\');
    return f ? f + 1 : m->folder;              /* a mod whose mod.toml was not read: its folder */
}

/* Its module's file name (never a host path), at most max characters. */
static void module_name(int i, char *out, size_t n, size_t max)
{
    shown(out, n, last_part(bo3_modfs_mod(i)->manifest.plugin_path));
    if (strlen(out) > max && max > 2) {
        out[max - 2] = out[max - 1] = '.';
        out[max] = 0;
    }
}

/* A mod's line: its name and state, and for native code CODE (approved from
 * the next start) or CODE?; while its approval waits for A, APPROVE CODE (the
 * module and its hash are on the information line). The line under the
 * cursor is drawn larger and 28 characters is what fits there, so a code
 * mod's name is cut to fit its longest line: 15 + "  OFF*  CODE?", and
 * 14 + "  APPROVE CODE". */
static void mod_line(int i, char *buf, size_t bn)
{
    char name[LABEL_CH];
    size_t cut = s_confirm == i ? 14 : has_code(i) ? 15 : NAME_CH;
    shown(name, sizeof name, mod_name(bo3_modfs_mod(i)));
    if (strlen(name) > cut) {
        size_t k = cut - 2;
        while (k && name[k - 1] == ' ')
            k--;
        memcpy(name + k, "..", 3);
    }
    if (s_confirm == i) {
        snprintf(buf, bn, "%s  APPROVE CODE", name);
    } else {
        snprintf(buf, bn, "%s  %s%s", name, state_word(i), !has_code(i) ? "" : code_chosen(i) ? "  CODE" : "  CODE?");
    }
}

/* camset1: MOD SETTINGS takes one line of the MODS page when a plugin has settings. */
#ifndef MM_MUT
#define MM_MUT 0             /* tests only (test_mm_camset1.c): one deliberate defect */
#endif
static int has_settings(void) { return bo3_ps_plugin_count() > 0; }
#if MM_MUT == 1
static int page_all(void)  { return PAGE_ALL; }          /* defect: the line not counted */
static int page_mods(void) { return PAGE_MODS; }
#else
static int page_all(void)  { return PAGE_ALL - has_settings(); }
static int page_mods(void) { return PAGE_MODS - has_settings(); }
#endif

/* The MODS page's lines into the block; the count. */
static int build_mods(void)
{
    char buf[96];
    int n = 0, nm = nmods(), active = 0, per;

    read_saved();
    for (int i = 0; i < nm; i++)
        active += bo3_modfs_mod(i)->usable && bo3_modfs_mod(i)->enabled;
    per = nm <= page_all() ? page_all() : page_mods();
    if (nm <= page_all() || s_first < 0 || s_first >= nm)
        s_first = 0;
    s_prev_line = s_next_line = -1;
    s_set_line = -1;
    s_nextmod_line = -1;
    for (int k = 0; k < MAX_LINES; k++)
        s_line_set[k] = -1;
    if (has_settings()) {                    /* camset1: line 0, never line 3 */
        s_set_line = n;
        put_label(label_va(n), "MOD SETTINGS");
        s_line_mod[n++] = -1;
    }
    if (s_first > 0) {
        s_prev_line = n;
        put_label(label_va(n), "PREVIOUS PAGE");
        s_line_mod[n++] = -1;
    }
    for (int i = s_first; i < nm && i < s_first + per; i++) {
        mod_line(i, buf, sizeof buf);
        put_label(label_va(n), buf);
        s_line_mod[n++] = i;
    }
    if (s_first + per < nm) {
        s_next_line = n;
        put_label(label_va(n), "NEXT PAGE");
        s_line_mod[n++] = -1;
    }
    s_apply_line = n;
    put_label(label_va(n), s_save_failed ? "NOT SAVED - SEE THE LOG"
                         : code_adds() ? "APPLY - APPROVES CODE - RESTART REQUIRED"
                         : changes_unsaved() ? "APPLY - RESTART REQUIRED"
                         : restart_needed() ? "SAVED - RESTART REQUIRED" : "NO CHANGES");
    s_line_mod[n++] = -1;
    s_detail_line = n;                       /* about the line under the cursor (detail_refresh) */
    s_detail[0] = 0;
    put_label(label_va(n), "");
    s_line_mod[n++] = -1;
    s_info_line = n;
    if (!nm)
        snprintf(s_info, sizeof s_info, "NO MODS INSTALLED");
    else
        snprintf(s_info, sizeof s_info, "%d INSTALLED  %d ACTIVE", nm, active);
    put_label(label_va(n), s_info);
    s_line_mod[n++] = -1;
    for (int k = 0; k < n; k++) {
        MM32(s_blk + (uint32_t)k * 8) = label_va(k);
        MM32(s_blk + (uint32_t)k * 8 + 4) = 0;
    }
    s_nlines = n;                            /* at most 1 + 4 + 1 + 3 = 9 or 6 + 3 = 9: WIDGET_MAX (camset1: 1 + 1 + 3
                                              * + 1 + 3 = 9 or 1 + 5 + 3 = 9) */
    return n;
}

/* camset1: the mod whose id is `id`, or NULL. */
/* GP-P4.1: the owner of plugin-settings group p as the page names it when it is no mod (the host's own settings). */
static const char *ps_owner(int p)
{
    return !strcmp(bo3_ps_plugin_mod(p), BO3_PS_HOST_MOD) ? "BURNOUT MASHUP" : bo3_ps_plugin_mod(p);
}

static const bo3_mod *mod_by_id(const char *id)
{
    for (int i = 0; i < nmods(); i++)
        if (!strcmp(bo3_modfs_mod(i)->manifest.id, id))
            return bo3_modfs_mod(i);
    return NULL;
}

/* camset1: the MOD SETTINGS page (mode 2) into the block; the count. At most 1 + 6 + 2 = 9 lines. */
static int build_settings(void)
{
    char buf[96];
    int n = 0, np = bo3_ps_plugin_count(), ns;
    const bo3_mod *m;

    if (s_ps < 0 || s_ps >= np)
        s_ps = 0;
    s_prev_line = s_next_line = s_set_line = s_nextmod_line = -1;
    s_apply_line = -1;
    for (int k = 0; k < MAX_LINES; k++)
        s_line_set[k] = s_line_mod[k] = -1;
    if (np > 1) {                            /* line 0, never line 3 */
        s_nextmod_line = n;
        put_label(label_va(n++), "NEXT MOD SETTINGS");
    }
    ns = bo3_ps_count(s_ps);
    for (int i = 0; i < ns && i < (int)BM_SETTINGS_PER_PLUGIN; i++) {
        bo3_ps_line(s_ps, i, buf, sizeof buf);
        put_label(label_va(n), buf);
        s_line_set[n++] = i;
    }
    s_detail_line = n;
    s_detail[0] = 0;
    put_label(label_va(n++), "");
    s_info_line = n;
    m = mod_by_id(bo3_ps_plugin_mod(s_ps));
    snprintf(buf, sizeof buf, "%s  %d OF %d", m ? mod_name(m) : ps_owner(s_ps), s_ps + 1, np);   /* GP-P4.1 */
    shown(s_info, sizeof s_info, buf);
    put_label(label_va(n++), s_info);
    for (int k = 0; k < n; k++) {
        MM32(s_blk + (uint32_t)k * 8) = label_va(k);
        MM32(s_blk + (uint32_t)k * 8 + 4) = 0;
    }
    s_nlines = n;
    return n;
}

/* A native-code mod's two lines: its code now and from the next start; its
 * module and hash. While its approval waits for A: the warning. */
static void code_text(int i, char *det, size_t dn, char *info, size_t in)
{
    const char *off = bo3_plugins_off(), *sha = s_code_sha[i][0] ? s_code_sha[i] : s_start_sha[i], *t;
    bo3_plugin_state st = bo3_plugins_state(i, NULL, 0, NULL, 0);
    char mod[LABEL_CH];
    int differs = code_differs(i), next = chosen(i) && code_chosen(i);

    if (s_confirm == i) {                    /* the bytes A approves: module and hash */
        module_name(i, mod, sizeof mod, 12);
        snprintf(det, dn, "NATIVE CODE RUNS WITH YOUR PERMISSIONS");
        snprintf(info, in, "TRUSTED SOURCES ONLY: %s %.8s", mod, s_code_sha[i]);
        return;
    }
    module_name(i, mod, sizeof mod, 24);
    if (sha[0])
        snprintf(info, in, "%s  SHA256 %.8s", mod, sha);
    else
        snprintf(info, in, "%s  (HASHED WHEN APPROVED)", mod);
    if (off)
        t = !strcmp(off, "TAKEDAWN_PLUGINS=0") ? "CODE OFF (TAKEDAWN_PLUGINS=0)"
          : strstr(off, "macOS") ? "CODE OFF ON MACOS (TAKEDAWN_PLUGINS=1)" : "CODE NOT SUPPORTED HERE";
    else if (st == BO3_PLUGIN_RUNNING)
        t = next ? "CODE RUNNING" : "RUNS UNTIL TAKEDAWN EXITS - RESTART REQUIRED";
    else if (s_code_missing[i])
        t = "CODE MISSING - SEE LOG";
    else if (differs && next)
        t = "CODE FROM THE NEXT START - RESTART REQUIRED";
    else if (st == BO3_PLUGIN_REFUSED || st == BO3_PLUGIN_FAILED)
        t = "CODE NOT LOADED - SEE LOG";
    else if (s_code_changed[i] && !next)
        t = "CODE CHANGED - APPROVE AGAIN";
    else if (s_appr == BO3_APPROVALS_NONE)
        t = "CODE: NO APPROVAL FILE";
    else if (s_appr == BO3_APPROVALS_BAD)
        t = "APPROVAL FILE UNREADABLE - SEE LOG";
    else if (s_appr == BO3_APPROVALS_KEPT)
        t = "APPROVAL FILE NOT CHANGED HERE - SEE LOG";
    else if (st == BO3_PLUGIN_OFF)
        t = next ? "CODE APPROVED (MOD OFF NOW)" : "CODE NOT USED (MOD OFF)";
    else
        t = next ? "CODE APPROVED" : "CODE NOT APPROVED";
    if (differs && !strstr(t, "RESTART") && strlen(t) + sizeof " - RESTART REQUIRED" <= LABEL_CH)
        snprintf(det, dn, "%s - RESTART REQUIRED", t);
    else
        snprintf(det, dn, "%s", t);
}

/* The details line, and the information line, for the line under the cursor. */
/* GP-P4.1 (deps1 cosmetics): a refused mod's reason on the details line. The title font draws ">=" as "> =": written
 * "MIN". The line shows about 46 characters (gp deps1_1 shot 10); a reason longer than REASON_FIT is cut at its first
 * "; " (the gate's capability / platform texts), keeping the host's version in brackets, else shortened with "..". */
#define REASON_FIT 40
void bo3_mm_reason_text(const char *in, char *out, size_t n)
{
    char t[256], tail[40] = "";
    size_t k = 0;
    const char *p, *semi;
    if (!n)
        return;
    for (p = in ? in : ""; *p && k + 6 < sizeof t; p++) {
        if (p[0] == '>' && p[1] == '=') {
            if (k && t[k - 1] != ' ')
                t[k++] = ' ';
            memcpy(t + k, "MIN", 3);
            k += 3;
            p++;
            if (p[1] && p[1] != ' ')
                t[k++] = ' ';
        } else {
            t[k++] = *p;
        }
    }
    t[k] = 0;
    semi = strstr(t, "; ");
    if (strlen(t) > REASON_FIT && semi) {
        const char *v = strstr(semi, "offers version ");
        const char *h = strstr(semi, "is platform ");
        if (v)
            snprintf(tail, sizeof tail, " (HOST %.8s)", v + 15);
        else if (h)
            snprintf(tail, sizeof tail, " (HOST %.8s)", h + 12);
        t[semi - t] = 0;
        if (strlen(t) + strlen(tail) <= REASON_FIT)
            strcat(t, tail);
    }
    if (strlen(t) > REASON_FIT)
        memcpy(t + REASON_FIT - 2, "..", 3);
    snprintf(out, n, "%s", t);
}

static void detail_text(int cur, char *det, size_t dn, char *info, size_t in)
{
    int nm = nmods(), active = 0;

    if (s_mode == 2) {                       /* camset1: MOD SETTINGS */
        const bo3_mod *m = mod_by_id(bo3_ps_plugin_mod(s_ps));
        if (bo3_ps_save_failed())
            snprintf(info, in, "NOT SAVED - SEE THE LOG");
        else
            snprintf(info, in, "%s  %d OF %d", m ? mod_name(m) : ps_owner(s_ps), s_ps + 1,   /* GP-P4.1 */
                     bo3_ps_plugin_count());
        if (cur >= 0 && cur < s_nlines && s_line_set[cur] >= 0)
            bo3_ps_detail(s_ps, s_line_set[cur], det, dn);
        else if (cur == s_nextmod_line)
            snprintf(det, dn, "A: THE NEXT MOD'S SETTINGS");
        else
            snprintf(det, dn, "B: BACK TO THE MODS");
        return;
    }
    for (int i = 0; i < nm; i++)
        active += bo3_modfs_mod(i)->usable && bo3_modfs_mod(i)->enabled;
    if (nm)
        snprintf(info, in, "%d INSTALLED  %d ACTIVE", nm, active);
    else
        snprintf(info, in, "NO MODS INSTALLED");
    if (cur >= 0 && cur < s_nlines && s_line_mod[cur] >= 0) {
        const bo3_mod *m = bo3_modfs_mod(s_line_mod[cur]);
        if (shared_id(m)) {
            snprintf(det, dn, "ID ALSO USED BY %.60s", last_part(shared_id(m)->folder));   /* not the whole path */
        } else if (!m->usable) {
            bo3_mm_reason_text(m->problem, det, dn);   /* GP-P4.1 */
        } else if (has_code(s_line_mod[cur])) {
            code_text(s_line_mod[cur], det, dn, info, in);
        } else {
            char ver[BO3_MOD_VERSION_MAX + 1], by[BO3_MOD_AUTHOR_MAX + 1];
            shown(ver, sizeof ver, m->manifest.version);
            shown(by, sizeof by, m->manifest.author);
            if (m->wins + m->loses)
                snprintf(det, dn, "V%.8s  BY %.14s  %d CONFLICTS", ver[0] ? ver : "-", by[0] ? by : "UNKNOWN",
                         m->wins + m->loses);
            else
                snprintf(det, dn, "V%.10s  BY %.24s", ver[0] ? ver : "-", by[0] ? by : "UNKNOWN");
            if (m->gameplay[0])                  /* PLATFORM-P3 (P-4): a data mod's gameplay label (bm_admit.c) */
                snprintf(info, in, "%.47s", m->gameplay);
            else if (m->manifest.description[0])
                snprintf(info, in, "%.100s", m->manifest.description);   /* a line shows 47 */
        }
    } else if (cur == s_apply_line) {
        snprintf(det, dn, "%s", s_save_failed ? "A: TRY AGAIN"
                                : code_adds() ? "A: SAVE - APPROVES NATIVE CODE"
                                : changes_unsaved() ? "A: SAVE - USED AT THE NEXT START"
                                : restart_needed() ? "QUIT AND START THE GAME AGAIN" : "THE MODS IN USE ARE SAVED");
    } else if (cur == s_set_line) {          /* camset1 */
        snprintf(det, dn, "A: SETTINGS OF %d MOD%s WITH CODE", bo3_ps_mod_count(),   /* main18: mods, not pages */
                 bo3_ps_mod_count() == 1 ? "" : "S");
    } else if (cur == s_prev_line || cur == s_next_line) {
        snprintf(det, dn, "PAGE %d OF %d", s_first / page_mods() + 1, (nm + page_mods() - 1) / page_mods());
    } else if (cur == s_info_line) {
        snprintf(det, dn, "%s", nm ? "A: TURN A MOD ON OR OFF" : "ADD A MOD FOLDER WITH A MOD.TOML");
    } else {
        det[0] = 0;
    }
}

/* Every idle frame of the page: the two lines follow the cursor. A line is
 * written only when its text changes, and never the one under the cursor. */
static void detail_refresh(void)
{
    char det[LABEL_CH * 4], info[LABEL_CH * 4], a[LABEL_CH], b[LABEL_CH];
    int cur;
    if (!s_mode || s_detail_line < 0 || !s_blk)
        return;
    cur = MM16(SP_CURSOR);
    if (s_confirm >= 0 && (cur < 0 || cur >= s_nlines || s_line_mod[cur] != s_confirm)) {
        int c = s_confirm;                   /* moved away from an approval waiting for A: cancelled */
        char buf[96];
        s_confirm = -1;
        for (int k = 0; k < s_nlines; k++)
            if (s_line_mod[k] == c) {
                mod_line(c, buf, sizeof buf);
                put_label(label_va(k), buf);
            }
        fprintf(stderr, "[MODS] %s: native code not approved (cancelled)\n", bo3_modfs_mod(c)->manifest.id);
    }
    if (cur == s_detail_line || cur == s_info_line)
        return;                              /* on one of them: keep what they say */
    detail_text(cur, det, sizeof det, info, sizeof info);
    shown(a, sizeof a, det);
    shown(b, sizeof b, info);
    if (strcmp(a, s_detail)) {
        memcpy(s_detail, a, sizeof s_detail);
        put_label(label_va(s_detail_line), a);
    }
    if (strcmp(b, s_info)) {
        memcpy(s_info, b, sizeof s_info);
        put_label(label_va(s_info_line), b);
    }
}

/* ---- the title's flow ---- */

/* The current state's own hash, from the machine's table. */
static int own_hash(uint32_t *lo, uint32_t *hi)
{
    uint32_t cur = MM32(FLOW + 4), t = MM32(FLOW + 0xC);
    for (int k = 0; k < 512 && t; k++, t += 16) {
        uint32_t a = MM32(t), b = MM32(t + 4);
        if (!a && !b)
            break;
        if (FLOW + MM32(t + 8) == cur) {
            *lo = a;
            *hi = b;
            return 1;
        }
    }
    return 0;
}

/* The page built again by the title's set-up, in the mode asked. */
static void rebuild(int mode)
{
    uint32_t a = g_eax, b = g_ebx, c = g_ecx, d = g_edx, si = g_esi, di = g_edi, sp = g_esp, bp = g_ebp, sbp = g_seh_ebp;
    uint32_t slot = MM32(MM32(STRTAB) + 0xC) + TITLE_SLOT, old = MM32(slot);
    s_mode = mode;
    if (mode) {
        put_label(title_va(), mode == 2 ? "MOD SETTINGS" : "MODS");   /* camset1: 12 + 1 of the title's 16 */
        MM32(slot) = title_va();
    }
    s_rebuilding = 1;
    g_eax = SP_PAGE;
    PUSH32(g_esp, 0);
    sub_00085170();
    s_rebuilding = 0;
    MM32(slot) = old;
    g_eax = a; g_ebx = b; g_ecx = c; g_edx = d; g_esi = si; g_edi = di; g_esp = sp; g_ebp = bp; g_seh_ebp = sbp;
}

/* menuentry.c's si_items mark (0x85222), after its own: esi the page, eax
 * the items for the widget, the count in the page. */
/* ---- main21 patch 94 (hook request zackypoo 14): the game's leftover DEBUG page ----
 * STATIC facts (default.xbe 9f497acd): the front end's state handlers are one table from 0x3AC100 (sub_00064230 gives every state
 * object a "vtable" pointing at its slot); the slot 0x3AC134 = sub_00067D80, whose enter calls sub_0007ADF0: a list page with
 * "Unlock All" / "Lock All" / "Show All Race Awards" / "Show All Crash Awards" (0x3AC3A8 / 9C / 84 / 6C) - no retail path
 * enters it (the PS2 cheat 14 swaps another state's handler for it). The state machine FLOW changes state by the target's hash
 * (sub_000146E0; its table [FLOW + 0xC] = {hash lo, hash hi, offset}): with the host setting DEBUG MENU on, Settings lists a
 * DEBUG MENU line after MODS; its A is the title's own A and exit, and at mm_flow_sel the pushed hash becomes the debug state's
 * (the table entry whose object's vtable is 0x3AC134), so the game's own machine enters the page. Back: the debug page's own
 * B. The page CHANGES THE SAVE (Unlock All / Lock All): OFF by default, the setting's help says so. Census: the slot, the
 * handler's call, the first label push. Switch BO3_HOOKREQ_P25D (default ON; OFF: no setting, no line). */
#ifndef BO3_HOOKREQ_P25D
#define BO3_HOOKREQ_P25D 0
#endif
#define DBG_VT      0x003AC134u                /* the debug state's handler slot */
static int s_dbg_line = -1, s_dbg_census = -1;
static int32_t s_dbg_setting = -1;              /* -1: not declared */

static int dbg_census(void)
{
    if (s_dbg_census < 0)
        s_dbg_census = MM32(DBG_VT) == 0x00067D80u && MM8(0x00067E3Eu) == 0xE8u &&
                       (uint32_t)(0x00067E3Fu + 4u + MM32(0x00067E3Fu)) == 0x0007ADF0u && MM8(0x0007AE72u) == 0xBAu &&
                       MM32(0x0007AE73u) == 0x003AC3A8u;
    return s_dbg_census;
}

static int dbg_on(void)
{
    int32_t v = 0;
    if (!BO3_HOOKREQ_P25D || s_dbg_setting < 0 || !dbg_census())
        return 0;
    return bo3_ps_host_get("debug_menu", &v) == BM_SETTINGS_OK && v;
}

/* the debug state's hash: the machine table's entry whose state object has the debug vtable */
static int dbg_hash(uint32_t *lo, uint32_t *hi)
{
    uint32_t t = MM32(FLOW + 0xC);
    for (int k = 0; k < 512 && t; k++, t += 16) {
        uint32_t a = MM32(t), b = MM32(t + 4);
        if (!a && !b)
            break;
        if (MM32(FLOW + MM32(t + 8)) == DBG_VT) {
            *lo = a;
            *hi = b;
            return 1;
        }
    }
    return 0;
}

/* main.c, with the other host settings (after bo3_bm_settings_init, before the plugins start) */
void bo3_modsmenu_debug_init(void)
{
    bm_setting_decl d;
    int32_t v = 0;
    if (!BO3_HOOKREQ_P25D)
        return;
    memset(&d, 0, sizeof d);
    d.struct_size = (uint32_t)sizeof d;
    d.kind = BM_SETTING_BOOL;
    d.key = "debug_menu";
    d.label = "DEBUG MENU";
    d.def = 0;                                  /* OFF: Unlock All / Lock All change the save */
    s_dbg_setting = bo3_ps_host_declare(&d, &v) == BM_SETTINGS_OK ? v : -1;
    fprintf(stderr, "[MODS] DEBUG MENU (the game's leftover debug page; Unlock All / Lock All CHANGE THE SAVE): %s\n",
            s_dbg_setting < 0 ? "setting not available" : v ? "ON" : "OFF");
}

static void mm_items(void)
{
    uint32_t n, i;
    if (g_esi != SP_PAGE)
        return;
    if (!s_rebuilding)
        s_mode = 0;                          /* the title built the page itself: the Settings list */
    s_mods_line = -1;
    s_dbg_line = -1;                         /* main21 patch 94: every build, before the early returns */
    s_confirm = -1;                          /* a page built anew: an approval waiting for A is cancelled */
    if (!mm_on() || !mm_block())
        return;
    if (s_mode) {
        MM16(SP_COUNT) = (uint16_t)(s_mode == 2 ? build_settings() : build_mods());
        if (MM16(SP_CURSOR) >= s_nlines)
            MM16(SP_CURSOR) = 0;
        if (s_page_built && s_prev_line >= 0 && s_prev_line + 1 < s_nlines)
            MM16(SP_CURSOR) = (uint16_t)(s_prev_line + 1);   /* a new page: on its first mod, not on PREVIOUS PAGE */
        if (s_want_cursor >= 0 && s_want_cursor < s_nlines)
            MM16(SP_CURSOR) = (uint16_t)s_want_cursor;       /* camset1: MOD SETTINGS in / out */
        s_want_cursor = -1;
        s_page_built = 0;
        g_eax = s_blk;
        if (s_mode == 2)
            fprintf(stderr, "[MODS] mod settings: %d lines, mod %d of %d (%s)\n", s_nlines, s_ps + 1,
                    bo3_ps_plugin_count(), bo3_ps_plugin_mod(s_ps));
        else
            fprintf(stderr, "[MODS] page: %d lines, first mod %d\n", s_nlines, s_first);
        return;
    }
    n = MM16(SP_COUNT);
    if (n < 4 || n > 5 || (g_eax != SP_ITEMS && n != 5))
        return;                              /* not the list this file knows */
    for (i = 0; i < n; i++) {
        MM32(s_blk + i * 8) = MM32(g_eax + i * 8);
        MM32(s_blk + i * 8 + 4) = 0;
    }
    s_mods_line = (int)n;
    put_label(label_va((int)n), "MODS");
    MM32(s_blk + n * 8) = label_va((int)n);
    MM32(s_blk + n * 8 + 4) = 0;
    MM16(SP_COUNT) = (uint16_t)(n + 1);
    if (dbg_on() && n + 2 <= MAX_LINES) {        /* main21 patch 94: DEBUG MENU after MODS */
        uint32_t lo, hi;
        if (dbg_hash(&lo, &hi)) {
            s_dbg_line = (int)n + 1;
            put_label(label_va(s_dbg_line), "DEBUG MENU");
            MM32(s_blk + (uint32_t)s_dbg_line * 8) = label_va(s_dbg_line);
            MM32(s_blk + (uint32_t)s_dbg_line * 8 + 4) = 0;
            MM16(SP_COUNT) = (uint16_t)(n + 2);
        }
    }
    g_eax = s_blk;
    fprintf(stderr, "[MODS] Settings: MODS listed (line %d)\n", s_mods_line);
}

/* mark "mm_flow_sel": event 5, a line chosen, after `push 0x65857D40` (eax
 * the cursor). */
static void mm_flow_sel(void)
{
    uint32_t lo, hi;
    if (s_probing) {
        s_probed |= 1;
        return;
    }
    if (!mm_on())
        return;
    if (s_mode && (s_page_pending >= 0 || s_pending_mode >= 0)) {   /* a page change on the MODS page (camset1: or
                                                                      * MOD SETTINGS / NEXT MOD SETTINGS) */
        int mode = 1;
        if (!own_hash(&lo, &hi)) {           /* mm_select checked it: cannot happen */
            s_page_pending = s_pending_mode = -1;
            return;
        }
        MM32(g_esp) = lo;
        MM32(g_esp + 4) = hi;
        if (s_pending_mode >= 0) {
            mode = s_pending_mode;
            s_want_cursor = s_ps >= 0 && bo3_ps_plugin_count() > 1 ? 1 : 0;   /* the first setting */
            fprintf(stderr, "[MODS] mod settings opened\n");
        } else {
            s_first = s_page_pending;
            s_page_built = 1;
        }
        s_page_pending = s_pending_mode = -1;
        rebuild(mode);
        return;
    }
    if (!s_mode && s_dbg_line >= 0 && g_eax == (uint32_t)s_dbg_line && MM16(SP_CURSOR) == s_dbg_line) {
        if (dbg_hash(&lo, &hi)) {             /* main21 patch 94: the game's machine enters its debug state */
            MM32(g_esp) = lo;                /* pushed: 0x65857D40 */
            MM32(g_esp + 4) = hi;            /* pushed before it: 0x94413FC1 */
            fprintf(stderr, "[MODS] DEBUG MENU: entering the game's debug page (state %08x:%08x)\n", (unsigned)hi, (unsigned)lo);
        }
        return;
    }
    if (s_mode || s_mods_line < 0 || g_eax != (uint32_t)s_mods_line || MM16(SP_CURSOR) != s_mods_line)
        return;
    if (!own_hash(&lo, &hi))
        return;                              /* mm_select let A through only with the hash found */
    MM32(g_esp) = lo;                        /* pushed: 0x65857D40 */
    MM32(g_esp + 4) = hi;                    /* pushed before it: 0x94413FC1 */
    s_first = 0;
    rebuild(1);
    fprintf(stderr, "[MODS] opened\n");
}

/* mark "mm_flow_back": event 5, back (result 3), after `push 0xEF6E02D9`. */
static void mm_flow_back(void)
{
    uint32_t lo, hi;
    if (s_probing) {
        s_probed |= 2;
        return;
    }
    if (!mm_on() || !s_mode)
        return;
    if (!own_hash(&lo, &hi)) {
        s_mode = 0;                          /* the title goes back to Driver Details, as it would */
        return;
    }
    MM32(g_esp) = lo;                        /* pushed: 0xEF6E02D9 */
    MM32(g_esp + 4) = hi;                    /* pushed before it: 0x94413FD6 */
    s_page_pending = -1;
    s_pending_mode = -1;
    if (s_mode == 2 && MM_MUT != 2) {        /* camset1: MOD SETTINGS -> the MODS page, on MOD SETTINGS */
        s_want_cursor = 0;
        rebuild(1);
        fprintf(stderr, "[MODS] mod settings closed\n");
        return;
    }
    rebuild(0);
    if (s_mods_line >= 0)
        MM16(SP_CURSOR) = (uint16_t)s_mods_line;   /* MODS where it is now, never past the list */
    fprintf(stderr, "[MODS] closed\n");
}

/* The choices saved: approvals removed first, then each mod whose choice
 * differs from the mod list, then approvals added. A failure stops what
 * follows (the mod list goes on with its other mods, as before): what is
 * saved never allows more native code than was chosen. */
static void apply(void)
{
    int ok = 1, n = 0, removed;
    for (int i = 0; ok && i < nmods(); i++)
        if (code_remove(i)) {
            n++;
            ok = bo3_plugins_set_approval(bo3_modfs_mod(i)->manifest.id, NULL);
        }
    removed = ok;
    for (int i = 0; removed && i < nmods(); i++) {
        const bo3_mod *m = bo3_modfs_mod(i);
        if (!m->usable || chosen(i) == s_saved[i])
            continue;
        n++;
        if (bo3_modfs_set_enabled(m->manifest.id, chosen(i))) {
            if (!has_code(i))
                s_touched[i] = 0;            /* now what the mod list says (a code mod: once its approval is too) */
        } else {
            ok = 0;                          /* this choice stays, to try again */
        }
    }
    for (int i = 0; ok && i < nmods(); i++)
        if (code_add(i)) {
            n++;
            ok = bo3_plugins_set_approval(bo3_modfs_mod(i)->manifest.id, s_code_sha[i]);
        }
    for (int i = 0; ok && i < nmods(); i++)
        if (has_code(i))
            s_touched[i] = 0;                /* now what the mod list and the approval file say */
    s_save_failed = !ok;
    if (ok)
        fprintf(stderr, "[MODS] APPLY: %d change(s) saved\n", n);
    else
        fprintf(stderr, "[MODS] APPLY: not every change saved: no mod list file (TAKEDAWN_MOD_LIST empty), or it "
                        "or the approval file could not be read or written (lines above); nothing after it was saved\n");
}

/* menuentry.c's si_select mark (0x853B4), after its own: al = A taken. */
static void mm_select(void)
{
    int cur;
    uint32_t lo, hi;
    if (!mm_on())
        return;
    detail_refresh();                        /* every idle frame of the page reaches the A test */
    if (!(g_eax & 0xFFu))
        return;
    cur = MM16(SP_CURSOR);
    if (!s_mode) {
        /* From the fifth line on the title's next-page table has no entry:
         * A goes on only for MODS, and only when its no-op can be made.
         * (menuentry.c has taken A for its own line already.) */
        if (s_ov_open && cur == s_mods_line && s_ov_open()) {
            /* main20m patch 63: the overlay's MODS page, as TAKEDAWN SETTINGS opens the overlay: the title never
             * takes this A, its select sound is ours. No overlay to open: this page, as before. */
            g_eax &= ~0xFFu;
            play_select();
            fprintf(stderr, "[MODS] opening the overlay's MODS page\n");
            return;
        }
        if (cur == s_dbg_line && s_dbg_line >= 0 && dbg_hash(&lo, &hi))
            return;                          /* main21 patch 94: DEBUG MENU: the title's own A and exit, then mm_flow_sel */
        if (cur >= TITLE_LINES && (cur != s_mods_line || !own_hash(&lo, &hi))) {
            g_eax &= ~0xFFu;
            fprintf(stderr, "[MODS] A on Settings line %d kept from the title (%s)\n", cur,
                    cur == s_mods_line ? "the Settings state is not in the machine's table" : "not a line it has");
        }
        return;                              /* MODS: the title's own A (sound, exit), then mm_flow_sel */
    }
    g_eax &= ~0xFFu;                         /* the MODS page: never the title's exit, unless a page change */
    if (cur < 0 || cur >= s_nlines)
        return;
    if (s_mode == 2) {                       /* camset1: MOD SETTINGS */
        char buf[96];
        if (cur == s_nextmod_line) {
            if (!own_hash(&lo, &hi) || cur == TITLE_LINES - 1)
                return;
            s_ps = (s_ps + 1) % (bo3_ps_plugin_count() > 0 ? bo3_ps_plugin_count() : 1);
            s_pending_mode = 2;
            g_eax |= 1u;                     /* the title's A and exit; mm_flow_sel builds the next mod's page */
            return;
        }
        if (s_line_set[cur] < 0 || !bo3_ps_step(s_ps, s_line_set[cur]))
            return;                          /* the details and information lines */
        bo3_ps_line(s_ps, s_line_set[cur], buf, sizeof buf);
        put_label(label_va(cur), buf);       /* the same number of lines: the frames stay */
        s_info[0] = s_detail[0] = 0;
        detail_refresh();
        play_select();
        return;
    }
    if (cur == s_set_line) {                 /* camset1: MOD SETTINGS, a page change */
        if (!own_hash(&lo, &hi) || cur == TITLE_LINES - 1)
            return;
        s_ps = 0;
        s_pending_mode = 2;
        s_confirm = -1;
        g_eax |= 1u;
        return;
    }
    if (s_line_mod[cur] >= 0) {
        int i = s_line_mod[cur];
        const char *id = bo3_modfs_mod(i)->manifest.id;
        if (!bo3_modfs_mod(i)->usable)
            return;                          /* a mod that cannot be used: nothing to turn on */
        if (!has_code(i)) {
            s_choice[i] = (unsigned char)!chosen(i);
        } else if (s_confirm == i) {         /* A on APPROVE: these bytes, from the next start (at APPLY) */
            s_choice[i] = s_code[i] = 1;
            s_confirm = -1;
            fprintf(stderr, "[MODS] %s: native code approved (sha256 %s), saved at APPLY\n", id, s_code_sha[i]);
        } else if (chosen(i) && !code_chosen(i) && code_possible() && !s_code_missing[i]) {
            char why[200];                   /* ON -> APPROVE: hashed now, never loaded */
            if (bo3_plugins_hash_module(i, s_code_sha[i], why, sizeof why)) {
                s_confirm = i;
                s_choice[i] = 1;
                s_code[i] = 0;
                fprintf(stderr, "[MODS] %s: approve native code %s (sha256 %s)? A again approves it\n", id,
                        bo3_modfs_mod(i)->manifest.plugin_path, s_code_sha[i]);
            } else {
                s_code_missing[i] = 1;       /* stays ON without code; A again turns it off */
                s_choice[i] = 1;
                s_code[i] = 0;
            }
        } else if (chosen(i)) {              /* ON or ON + CODE -> OFF: its approval goes too */
            s_choice[i] = s_code[i] = 0;
            s_code_missing[i] = 0;
        } else {                             /* OFF -> ON: its files only */
            s_choice[i] = 1;
            s_code[i] = 0;
        }
        s_touched[i] = 1;
        s_save_failed = 0;
    } else if (cur == s_apply_line) {
        if (!changes_unsaved() && !s_save_failed)
            return;
        apply();
        read_saved();
    } else if (cur == s_next_line || cur == s_prev_line) {
        /* Another page has another number of lines, and the widget makes its
         * line frames once, at set-up: so a page change is the title's own A
         * (select sound, exit), and mm_flow_sel builds the next page. */
        if (!own_hash(&lo, &hi) || cur == TITLE_LINES - 1)
            return;                          /* event 5 for line 3 skips mm_flow_sel (never so laid out) */
        s_page_pending = cur == s_next_line ? s_first + page_mods() : (s_first >= page_mods() ? s_first - page_mods() : 0);
        g_eax |= 1u;
        return;
    } else {
        return;                              /* the details and information lines */
    }
    MM16(SP_COUNT) = (uint16_t)build_mods(); /* the same number of lines: the frames stay */
    if (MM16(SP_CURSOR) >= s_nlines)
        MM16(SP_CURSOR) = (uint16_t)(s_nlines - 1);
    s_info[0] = s_detail[0] = 0;
    detail_refresh();
    play_select();
}

int bo3_modsmenu_mode(void) { return s_mode; }
void bo3_modsmenu_set_overlay(int (*open)(void)) { s_ov_open = open; }   /* main20m patch 63 (modsmenu_ov.c) */
void bo3_modsmenu_items(void) { mm_items(); }
void bo3_modsmenu_select(void) { mm_select(); }

void bo3_modsmenu_start(void)
{
    const char *e = BM_GETENV("MODS_MENU");      /* pfid1: BMASHUP_MODS_MENU first (bm_env.h) */
    s_hidden = e && e[0] == '0' && !e[1];
    memset(s_touched, 0, sizeof s_touched);
    memset(s_code_sha, 0, sizeof s_code_sha);
    memset(s_code_missing, 0, sizeof s_code_missing);
    s_save_failed = 0;
    s_confirm = -1;
    s_appr_said = 0;
    recomp_patch_on_mark("mm_flow_sel", mm_flow_sel);
    recomp_patch_on_mark("mm_flow_back", mm_flow_back);
    /* MODS is listed only with its marks in the generated code and the two
     * flow marks reaching mm_flow_*: the toolkit calls the first function
     * registered for a name and drops a registration past its table (and
     * menuentry.c registers si_items and si_select before these). Without
     * them A on MODS would reach the title's four-entry next-page table. */
    s_probing = 1;
    s_probed = 0;
    recomp_patch_mark("mm_flow_sel");
    recomp_patch_mark("mm_flow_back");
    s_probing = 0;
    {
        int gen = bo3_modsmenu_gen_marks();
        s_flow = gen && s_probed == 3;
        if (!s_flow)
            fprintf(stderr, "[MODS] the MODS page is not listed: %s\n",
                    !gen ? "the generated code lacks its marks (run regen.sh and build again)"
                         : "its marks reach other functions, or the toolkit's mark table is full");
    }
}
