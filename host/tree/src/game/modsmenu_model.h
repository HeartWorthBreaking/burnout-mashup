/*
 * modsmenu_model.h - the mods' states for the overlay's MODS page (gp main20m patch 62, modsmenu_ov.c).
 *
 * What each installed mod is now and from the next start, in the words a player reads, and the page's actions, saved
 * at once. No guest memory, no drawing: the mod list (modfs.h), the approval file and this start's plugins (plugins.h)
 * only. One caller at a time (modsmenu_ov.c holds its lock); the native page (modsmenu.c) is not used in the same
 * process (modsmenu_ov.c decides at the start).
 *
 * The rules kept from the native page: a plugin runs only for exactly the bytes approved; turning a plugin mod off
 * removes its approval first; turning it on approves it in the same action (one explicit confirmation, its file's
 * SHA-256 shown), the mod list first and the approval after, and a failed approval puts the mod list back: what is saved
 * never allows more code than was chosen. Nothing changes this start's mods or plugins: changes wait for a restart.
 */
#ifndef BO3_MODSMENU_MODEL_H
#define BO3_MODSMENU_MODEL_H

#include <stddef.h>

typedef enum {
    MM_ON = 0,              /* on now and from the next start */
    MM_OFF,                 /* off now and from the next start */
    MM_ON_RESTART,          /* on from the next start, not now (or its plugin starts then) */
    MM_OFF_RESTART,         /* off from the next start, on now */
    MM_NEEDS_APPROVAL,      /* on, but its plugin is not approved: it would run without its code */
    MM_CODE_CHANGED,        /* approved for other bytes than its plugin file has now */
    MM_PLUGIN_NOT_LOADED,   /* approved, but this start refused it or its start failed */
    MM_PLUGINS_OFF,         /* has a plugin, and plugins do not run in this game (TAKEDAWN_PLUGINS=0, the system) */
    MM_NEEDS_MOD,           /* refused: requires a mod that is not there (or not on) */
    MM_CONFLICT,            /* refused: clashes with an earlier mod */
    MM_UNUSABLE,            /* refused: invalid mod.toml, another folder with its id, a platform it needs ... */
    MM_STATUS_COUNT
} mm_status;

enum { MM_TONE_PLAIN = 0, MM_TONE_DIM, MM_TONE_ATTN, MM_TONE_BAD, MM_TONE_GOOD };   /* = XBOX_PT_* */

/* What turning a mod on / off does (the list's left / right). */
typedef enum {
    MM_TOGGLE_NONE = 0,     /* nothing (refused, plugins off, approvals kept by hand) */
    MM_TOGGLE_ON,           /* turns it on (a data mod) */
    MM_TOGGLE_OFF,          /* turns it off (a plugin mod: its approval goes too) */
    MM_TOGGLE_APPROVE       /* a plugin mod: the approval screen (approve and turn on) */
} mm_toggle;

/* Read the mod list and the approval file again (at a view's start and after each action). */
void mm_refresh(void);
int  mm_count(void);
mm_status mm_status_of(int i);
const char *mm_chip(mm_status st);          /* "ON", "NEEDS APPROVAL" ... */
int  mm_tone(mm_status st);
int  mm_has_plugin(int i);                  /* usable, with a module for this system */
int  mm_approval_writable(void);            /* the approval file may be written here (absent or read and plain) */
mm_toggle mm_toggle_of(int i);

/* Texts (UTF-8, as the mod wrote them; control characters as spaces). */
void mm_name(int i, char *out, size_t n);
void mm_byline(int i, char *out, size_t n);  /* "v1.4.0  by Jo Modder" ("version -" / "author unknown") */
void mm_kind(int i, char *out, size_t n);    /* "data mod" / "plugin (native code)" */
void mm_about(int i, char *out, size_t n);   /* the gameplay label ("Changes gameplay: ..."), else the description */
void mm_why(int i, char *out, size_t n);     /* the state in a sentence, with what to do (every status) */
void mm_module(int i, char *file, size_t fn, long *bytes);   /* its plugin's file name (never a path), its size (-1 ?) */
void mm_files(int i, char *out, size_t n);   /* "3 files used over others, 1 replaced by later mods" / "" */
void mm_summary(char *out, size_t n);        /* "12 mods  ·  8 on  ·  1 needs approval  ·  1 can't be used" */
int  mm_count_status(mm_status st);

/* Actions, saved at once; 1 done, 0 not (why: a sentence). */
int mm_turn_on(int i, char *why, size_t n);                 /* a data mod (or a plugin mod with plugins off: never) */
int mm_turn_off(int i, char *why, size_t n);                /* approval removed first, then the mod list */
/* The approval screen: the module hashed now (never loaded); sha 64 hex digits. */
int mm_hash(int i, char sha[65], char *why, size_t n);
int mm_approve_and_on(int i, const char *sha, char *why, size_t n);

/* The mods whose next start differs from this one (counted in the overlay's "Restart now to apply N changes"). */
int mm_restart_count(char *why, size_t n);
/* td030: a mod the game can put to use at once (upstream's bo3_upscale_mods_live: the pack made on this computer): the hook is
 * asked after a turn on / off is saved; 1 = in use now, no restart for it. */
void mm_set_live(int (*fn)(const char *id, int on));
int  mm_live_now(int i);                     /* mod i's saved choice is already in use through the hook */

#endif
