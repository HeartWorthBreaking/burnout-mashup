/*
 * modmanifest.h - a mod folder's mod.toml (docs/mod-folders.md, Manifests).
 *
 * The file is TOML, read with the toolkit's reader (recomp_cfg: UTF-8 is
 * checked, a key given twice is an error). The manifest is its top-level
 * string keys below; a known key of another type makes it invalid, and any
 * other key or table is left alone, so later versions can add some.
 */
#ifndef BO3_MODMANIFEST_H
#define BO3_MODMANIFEST_H

#include <stddef.h>

/* GP-P4.3 M3: 65536 (was 8192; veh1 found ~160 cars per mod at 8192). = MODFS_STATE_MAX: every [bmashup.*] table reader
 * already reads mod.toml through bo3_modfs_read_whole (64 KiB), so the gate, the manifest and the tables see the same
 * file; the TOML reader allocates per entry (no fixed table). Buffers sized by it: two static (platform gate, modfs) and
 * one thread-local (bo3_manifest_parse); none on a stack. */
#define BO3_MANIFEST_MAX_BYTES 65536   /* a larger mod.toml is invalid */
#define BO3_MOD_ID_MAX      64        /* field limits in bytes, without the terminator */
#define BO3_MOD_NAME_MAX    128
#define BO3_MOD_VERSION_MAX 32
#define BO3_MOD_AUTHOR_MAX  128
#define BO3_MOD_DESC_MAX    1024
#define BO3_PLUGIN_PATH_MAX 200       /* a [plugin] module path (docs/native-plugins.md) */

typedef struct bo3_manifest {
    char id[BO3_MOD_ID_MAX + 1];             /* required: [a-z0-9] then [a-z0-9._-] */
    char name[BO3_MOD_NAME_MAX + 1];         /* required */
    char version[BO3_MOD_VERSION_MAX + 1];   /* "" when absent: [0-9A-Za-z] then [0-9A-Za-z.+-] */
    char author[BO3_MOD_AUTHOR_MAX + 1];     /* "" when absent */
    char description[BO3_MOD_DESC_MAX + 1];  /* "" when absent */
    /* [plugin]: the mod holds native code. plugin_api is plugin.api (1 ..
     * 65535); plugin_path is the module for this system (plugin.windows,
     * .linux, .macos or .android), relative to the mod folder, '/' or '\'
     * between parts, never in its files folder: "" when the mod has none for
     * this system (its files are still used). Every system's key is checked,
     * so a manifest means the same everywhere. */
    int  plugin;
    int  plugin_api;
    char plugin_path[BO3_PLUGIN_PATH_MAX + 1];
} bo3_manifest;

/* Parses n bytes of a mod.toml. 1 with *out filled; 0 with *out cleared and a
 * one-line reason in err (always terminated when errn > 0). name, author and
 * description are UTF-8 without control characters: text to show, never a
 * format or markup. Reads no file. */
int bo3_manifest_parse(const char *text, size_t n, bo3_manifest *out, char *err, size_t errn);

/* 1 when id is a valid mod id (the rule above, 1 to BO3_MOD_ID_MAX bytes). */
int bo3_manifest_id_ok(const char *id);

/* The [plugin] key of this system: "windows", "linux", "macos" or "android". */
const char *bo3_manifest_platform(void);

/* PLATFORM-P1 (P-1, P-2; bm_platform_gate.inc, bm_platform_table.h): the Burnout Mashup platform gate over the
 * [bmashup] / [bmashup.*] keys of n bytes of a mod.toml whose manifest bo3_manifest_parse accepted. 1: this host can
 * serve the mod (also: no [bmashup] key at all). 0 with a one-line reason in why: the mod needs a newer platform (a
 * table or table version this host does not read, [bmashup] platform / requires not met), or names a key its table's
 * reader does not take (typo protection), or its [bmashup] keys are malformed. modfs.c then refuses that mod alone
 * (not usable: files, tables, plugin unused); the game starts without it. Reads no file. */
int bo3_manifest_platform_check(const char *text, size_t n, char *why, size_t wn);
/* This host's platform version, "MAJOR.MINOR.PATCH" (BO3_PLATFORM_VERSION, "0.1.0"). */
const char *bo3_manifest_platform_version(void);

#endif
