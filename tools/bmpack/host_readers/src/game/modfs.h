/*
 * modfs.h - the mods bo3_modfs_init found (docs/mod-folders.md, Manifests),
 * and which of them are on.
 *
 * The list is made once, by bo3_modfs_init, before the title runs, and does
 * not change afterwards: readers need no lock and the pointers stay good until
 * the next bo3_modfs_init (only the unit test calls it twice). Order: the
 * folders TAKEDAWN_MODS names, in order, then the default mods folder, then
 * the folder of mods made on this computer; in each, its usable mods by id,
 * then the ones that are not usable by folder name.
 *
 * On and off: a mod is on unless the mod list (bo3_modfs_state_file, a
 * mod-list.toml beside settings.toml) names its id as off. A change is saved
 * at once and used from the next start: this session's list stays as it is.
 */
#ifndef BO3_MODFS_H
#define BO3_MODFS_H

#include <stddef.h>
#include "modmanifest.h"

/* main18 (platform 0.1.8, owner 2026-10-28): mods 64 -> 256, mod folders 8 -> 256 (+ the mods-folders list file,
 * TAKEDAWN_MODS_FILE), switched-off ids 256 -> 1024. Every per-mod array of the host follows BO3_MODFS_MAX_MODS (host
 * memory only: no guest allocation is per mod). Build option BO3_MOD_LIMITS=legacy (CMake; -DBO3_MOD_LIMITS_LEGACY=1)
 * restores capmega1's values (64 / 8 / 256 and the texture / music mod limits 16 / 16), proven by the limit tests. */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BO3_MODFS_MAX_MODS 64
#define BO3_MODFS_MAX_OFF  256      /* ids the mod list keeps as off */
#else
#define BO3_MODFS_MAX_MODS 256
#define BO3_MODFS_MAX_OFF  1024     /* ids the mod list keeps as off */
#endif
#define BO3_MODFS_PATH_MAX 520

/* main18 (folder list item): mod folders, TAKEDAWN_MODS + TAKEDAWN_MODS_FILE (modfs.c) */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BO3_MODFS_MAX_DIRS 8
#else
#define BO3_MODFS_MAX_DIRS 256
#endif

typedef struct bo3_mod {
    bo3_manifest manifest;          /* all empty when the manifest was not read */
    char folder[BO3_MODFS_PATH_MAX];/* the mod folder's full host path */
    int  root;                      /* 0-based place of its folder in TAKEDAWN_MODS */
    int  usable;                    /* 1: valid, and no other mod has its id */
    int  enabled;                   /* 1: on in this session; its files are used when usable too */
    int  wins, loses;               /* files it supplies that another source has too: used / not used */
    char problem[160];              /* why not usable; "" when usable */
    int  conflict;                  /* PLATFORM-P3 (P-9): refused by the admission (bm_admit.c): a clash with an earlier mod */
    char gameplay[48];              /* PLATFORM-P3 (P-4): "CHANGES GAMEPLAY: ..." for the Mods page, "" none */
    int  needs;                     /* GP-DEPS1: refused by the admission for [bmashup] requires_mods (conflict is 1 too) */
} bo3_mod;

void bo3_modfs_init(void);
int bo3_modfs_folder_count(void);      /* mod folders taken (0: none, the mod loader is off) */
int bo3_modfs_mod_count(void);
const bo3_mod *bo3_modfs_mod(int i);   /* NULL outside 0 .. count - 1 */

/* The folder of mods made on this computer (the upscaled menu pictures,
 * upscale.h), before bo3_modfs_init: a mod folder after the ones TAKEDAWN_MODS
 * names, when it is there. NULL or "": none. */
void bo3_modfs_generated_dir(const char *dir);
/* The default mods folder (BO-327), before bo3_modfs_init: a mod folder after
 * the ones TAKEDAWN_MODS names, when it exists, so mods work without a
 * variable (a Steam Deck in Game Mode has no shell). NULL or "": none; an
 * empty TAKEDAWN_MODS turns it off. Android: unset means the app's files
 * folder's mods. bo3_modfs_default_dir_name gives it back ("" for none). */
void bo3_modfs_default_dir(const char *dir);
const char *bo3_modfs_default_dir_name(void);
/* A mod folder's full path as the toolkit will open it, into out (1), or 0
 * when it cannot take it. Windows: a path that is not plain ASCII becomes its
 * short 8.3 form (the toolkit reads the path in the guest's code page).
 * Elsewhere: the path itself (UTF-8 is fine), unless it holds a control
 * character or a '\'. */
int bo3_modfs_host_path(const char *full, char *out, size_t n);
/* The mod list's file, before bo3_modfs_init. NULL or "": none (every mod on,
 * nothing saved). */
void bo3_modfs_state_file(const char *path);
/* On at the next start: what the mod list says now (1 / 0; 1 when it cannot
 * be read). Reads the list first if the start did not (no mods). */
int bo3_modfs_enabled_next(const char *id);
/* Turn a mod on or off from the next start; saved at once. 1 when saved (or
 * already so), 0 when id is not a valid id, there is no mod list file, it
 * could not be read now, the list already holds BO3_MODFS_MAX_OFF ids, or it
 * could not be written; with 0 the file and the list are as they were. Saving
 * drops entries the list skipped (not ids, more than BO3_MODFS_MAX_OFF). Any
 * thread; a lookup never waits for it. */
int bo3_modfs_set_enabled(const char *id, int on);
/* Files more than one place supplies (this session; see the log for which). */
int bo3_modfs_conflicts(void);
/* main18: lookups that reached the disk since bo3_modfs_init (a source's list said it may have the file, or the source
 * has no list). Diagnostics / tests; not exact while several threads look files up. */
long bo3_modfs_lookup_walks(void);
/* The host path of rel inside mod m's own folder (beside its mod.toml, not
 * in files), found the way a lookup finds a file: every part a plain name,
 * none a link or reparse point, a regular file at the end. 1 with out set,
 * else 0. For a plugin's module (plugins.c). */
int bo3_modfs_mod_file(const bo3_mod *m, const char *rel, char *out, size_t n);
/* Another settings file (plugins.c's approval file), read and written the
 * mod list's way. read: 1 read (text NUL-terminated), 0 no such file, -1 not
 * readable now, -2 not a plain file, larger than 64 KiB, or a path too long;
 * free(*text) whatever it returns. write: the whole file to path.tmp, flushed, then renamed
 * over path; 1 done, 0 not (path as it was). No lock: one caller at a time. */
int bo3_modfs_read_whole(const char *path, char **text, size_t *n);
int bo3_modfs_write_whole(const char *path, const char *text, size_t n);
/* PLATFORM-P3 (P-9): called once by the mod list's making, after the mods' order and on / off state are known and
 * before any mod's files, tables or plugin are used (and before the [MOD] lines): it may make a mod not usable
 * (usable 0, conflict 1, problem) and set gameplay. NULL (the unit tests): none. Set before bo3_modfs_init.
 * GP-DEPS1: it may also REORDER the n mods (bm_admit.c: the dependency order of [bmashup] requires_mods - every mod after the
 * mods it requires, else the order above); the [MOD] lines, the sources and everything after follow the new order. */
typedef void (*bo3_modfs_admit_fn)(bo3_mod *mods, int n);
void bo3_modfs_set_admit(bo3_modfs_admit_fn fn);
/* Texture packs (BO-312): the textures/ folders of the places that are on, in
 * lookup order (a folder's loose textures/ first, then its mods by id): the
 * i-th one's full path into dir and a name for the log (the mod's id, or
 * "folder N") into name. 1, or 0 past the last. */
int bo3_modfs_texture_dir(int i, char *dir, size_t n, char *name, size_t nn);

#endif
