/*
 * bm_admit.h - PLATFORM-P3 EXPERIMENTAL: the mods' [bmashup.*] declarations admitted TOGETHER before any service sees one
 * (backlog P-9), and the gameplay-change labels of data mods (backlog P-4). research\native_gameplay_api\platform\host3\
 * HOST_P3_REPORT.md.
 *
 * Two-phase admission (when the mod list is made, modfs.c list_mods, before any file of a mod is served, before any
 * [bmashup.*] reader, service or plugin runs, before the guest starts):
 *   1. VALIDATE (bo3_admit_run, pure): every usable, enabled mod's mod.toml is read once; its [bmashup.regions],
 *      [bmashup.tracks] (add / names / locations), [bmashup.extra_events], [bmashup.tune] and [bmashup.capacity] are
 *      collected into this module's own memory (host heap, freed before it returns). The keys that two mods cannot both
 *      hold are compared in the mod list's order (TAKEDAWN_MODS folders, then manifest id - modfs.h): the LATER mod of a
 *      clash is refused as a whole; a mod that needs content only a refused mod declares (an event on its track, a track
 *      in its region letter) is refused too. Nothing else is called: no service, no guest memory, no file write.
 *   2. COMMIT: the refused mods are made "not usable" (modfs's own state, with the reason) before the mod list is logged
 *      and before any source / service / plugin reads it; the services then register the admitted mods exactly as before
 *      (their own refusals and exit codes 91 / 92 / 93 stay for what this module cannot decide: a mod's own invalid
 *      declaration, a guest-dependent check, a host failure).
 * Clash kinds (the earlier mod keeps the key; the later mod is refused): a track ID two mods add; a track's name or location
 * text given twice (only possible with the same track); a region letter declared with another text or DJ bank (the same
 * text and bank is shared, as before); an event key (mod/event) twice; an event location whose 6-row list the earlier mods'
 * events already fill (retail events + added events <= 6, the free rows of bm_wtour.h); more added tracks than the track
 * list holds (347 = 383 - 36 retail); a tuning value ([bmashup.tune] set) another mod sets. [bmashup.capacity] cannot clash
 * (the services take the largest request of all mods, whatever the order).
 *
 * GP-DEPS1 (platform 0.1.2) - mod-to-mod dependencies ([bmashup] requires_mods, bm_modreq.h):
 *   ORDER (bo3_admit_order, pure): before the admission, the mod list is put in dependency order: every mod comes after the
 *      mods it requires; otherwise the list keeps its order (TAKEDAWN_MODS folders, then manifest id) - with no requires_mods
 *      anywhere the order is exactly the old one. Deterministic: among the mods that may come next, the earliest in the old
 *      order is taken; a cycle is broken at its earliest mod (and refused below). The admission, the services, the plugins
 *      and the Mods page follow this order; file lookups keep their rule (TAKEDAWN_MODS folder first, then the earlier mod in
 *      the list), so inside one folder a dependency's files are found before its dependent's.
 *   REFUSAL (in bo3_admit_run_deps' fixpoint, with the clashes): a mod is refused as a whole when a required mod is not
 *      installed, switched off, not usable (its own manifest / platform problem, a shared id), older than required, of a
 *      version that cannot be compared, refused itself (a clash, or its own unmet dependency - transitively), or when the
 *      requirements form a cycle (every mod of the cycle). The reason names the required mod, its version and folder.
 *      A refused mod never holds a clash key, so a later mod that clashed only with it is admitted (as K11).
 * GP-MUSIC1 - [bmashup.music] (bm_music.h, read by the same reader, bm_music_parse.inc): a mod whose declaration is invalid
 * (or replaces a track of a mod not in its requires_mods) is refused as a whole (MUSIC_DECL); a soundtrack name an earlier
 * mod uses (case-insensitive: MUSIC_SOUNDTRACK); more than 16 soundtracks or 256 tracks (MUSIC_CAPACITY); a replace of a
 * track no admitted earlier mod adds, one another mod already replaced, or a title the target's soundtrack already has
 * (MUSIC_TRACK). The later mod is refused, as for every clash.
 * GP-FETEX1 - [bmashup.textures], [bmashup.wt_map_art], [bmashup.cars] photos (bm_fetex.h, the same reader and registry,
 * bm_fetex_parse.inc): the mod's TXD file is read from its folder and checked here (structure, front-end capability list,
 * names, binding requirements: TEX_DECL); against the earlier admitted mods (bounds 256 textures / 8 MiB pool / 16 mods,
 * a car photo / map slot / region text another mod binds, a target no earlier mod of requires_mods registers: TEX_REG).
 * Nothing of a refused mod is registered; the service later registers exactly the admitted mods.
 * Labels (P-4): an admitted mod that declares [bmashup.tune] or [bmashup.capacity] values gets a label naming the systems
 * and values it changes, logged at the start ("[MODS] <id> <version> changes gameplay: ...") and shown, short, on the Mods
 * page's information line. Informational only: no prompt, nothing stored, nothing asked again (native-code approval is
 * separate and unchanged: plugins.c, per sha256).
 */
#ifndef BO3_BM_ADMIT_H
#define BO3_BM_ADMIT_H

#include <stddef.h>
#include <stdint.h>

#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BO3_ADMIT_MAX     64u             /* = BO3_MODFS_MAX_MODS (legacy limits) */
#else
#define BO3_ADMIT_MAX     256u            /* = BO3_MODFS_MAX_MODS (main18) */
#endif
#define BO3_ADMIT_WHY     700u
#define BO3_ADMIT_LABEL   700u
#define BO3_ADMIT_PAGE    48u             /* the Mods page's label: 47 characters + NUL (modsmenu.c LABEL_CH) */
#define BO3_ADMIT_TRACKS  347u            /* added tracks the track list holds: BO3_CC_CAP 383 - BO3_CC_RETAIL 36 */

enum {
    BO3_AK_NONE = 0,
    BO3_AK_TRACK_ID,                      /* [bmashup.tracks] add: an ID another mod adds */
    BO3_AK_TRACK_NAME,                    /* [bmashup.tracks] names: a second name for a track */
    BO3_AK_TRACK_LOCATION,                /* [bmashup.tracks] locations: a second location text */
    BO3_AK_REGION,                        /* [bmashup.regions] add / dj: a letter with another text or bank */
    BO3_AK_EVENT_KEY,                     /* [bmashup.extra_events] add: mod/event twice */
    BO3_AK_EVENT_LOCATION,                /* [bmashup.extra_events] add: the location's list is full with earlier mods' events */
    BO3_AK_TRACK_CAPACITY,                /* [bmashup.tracks] add: more than BO3_ADMIT_TRACKS added tracks in all mods */
    BO3_AK_TUNE,                          /* [bmashup.tune] set: a value another mod sets */
    BO3_AK_NEEDS_TRACK,                   /* an event on a track only a refused mod adds */
    BO3_AK_NEEDS_REGION,                  /* a track in a region letter only a refused mod declares */
    BO3_AK_NEEDS_MOD,                     /* GP-DEPS1: [bmashup] requires_mods not met (absent / off / unusable / older / refused) */
    BO3_AK_MOD_CYCLE,                     /* GP-DEPS1: the mods' requires_mods form a cycle */
    BO3_AK_MUSIC_DECL,                    /* GP-MUSIC1: the mod's own [bmashup.music] is invalid (bm_music.h's reader) */
    BO3_AK_MUSIC_SOUNDTRACK,              /* GP-MUSIC1: a soundtrack name an earlier mod uses */
    BO3_AK_MUSIC_TRACK,                   /* GP-MUSIC1: a replace of a track no earlier mod adds / already replaced / a title
                                           * twice in the target's soundtrack */
    BO3_AK_MUSIC_CAPACITY,                /* GP-MUSIC1: more than 16 music soundtracks / 256 tracks in all mods */
    BO3_AK_TEX_DECL,                      /* GP-FETEX1: the mod's own [bmashup.textures] / [bmashup.wt_map_art] / photos are
                                           * invalid (TXD structure, capability list, names, binding requirements, file) */
    BO3_AK_TEX_REG,                       /* GP-FETEX1: against the earlier mods: bounds (textures / pool), a binding key they
                                           * hold (car photo, map slot, region texts), a target no earlier mod registers */
    BO3_AK_COUNT
};

/* bits of bo3_admit_res.undecided: a table this module could not read the way its reader does (the reader decides at commit,
 * with its own refusal and exit code - fail closed) */
enum { BO3_AT_REGIONS = 1u, BO3_AT_TRACKS = 2u, BO3_AT_NAMES = 4u, BO3_AT_EVENTS = 8u, BO3_AT_TUNE = 16u, BO3_AT_CAPACITY = 32u,
       BO3_AT_MODS = 64u /* GP-DEPS1: [bmashup] requires_mods */, BO3_AT_MUSIC = 128u /* GP-MUSIC1: [bmashup.music] */,
       BO3_AT_TEXTURES = 256u /* GP-FETEX1: [bmashup.textures] / [bmashup.wt_map_art] / [bmashup.cars] photos */ };

typedef struct bo3_admit_mod {            /* input: one usable, enabled mod, in the mod list's order */
    const char *id, *version, *folder;
    const char *text;                     /* its mod.toml (NULL: not readable now - it declares nothing here) */
    size_t n;
} bo3_admit_mod;

typedef struct bo3_admit_res {            /* output, one per input mod */
    int refused;                          /* 1: refused as a whole */
    int other;                            /* the mod (input index) that keeps the key, -1 none */
    int kind;                             /* the first clash (BO3_AK_*) */
    int nclash;                           /* clashes found (all are named in why) */
    char key[80];                         /* the first clashing key */
    char why[BO3_ADMIT_WHY];              /* "<kind> <key> ... mod <id> <version> (<folder>)[; ...]" */
    unsigned undecided;                   /* BO3_AT_* */
    unsigned tables;                      /* BO3_AT_* the mod declares */
    int gameplay;                         /* 1: tune / capacity values (the label) */
    char label[BO3_ADMIT_LABEL];          /* "changes gameplay: boost (...), capacity (...)", "" none */
    char page[BO3_ADMIT_PAGE];            /* "CHANGES GAMEPLAY: BOOST, CAPACITY", "" none */
    char need[96];                        /* GP-DEPS1, kind NEEDS_MOD / MOD_CYCLE: the short reason for the Mods page
                                           * ("needs gp.base >= 1.0.2: not installed"), "" otherwise */
} bo3_admit_res;

/* Phase 1 (pure): reads m[0..n-1] (n <= BO3_ADMIT_MAX), writes r[0..n-1] only; the number of refused mods (-1: bad
 * arguments / out of host memory: nothing decided, every mod admitted - the services' own checks stay in force). */
int bo3_admit_run(const bo3_admit_mod *m, int n, bo3_admit_res *r);
const char *bo3_admit_kind_name(int kind);

/* GP-DEPS1: a listed mod that does not take part (switched off, or not usable), for the dependency reasons */
typedef struct bo3_admit_known {
    const char *id, *version, *folder;
    const char *state;                    /* "switched off", or why it is not usable (modfs's problem text) */
} bo3_admit_known;
/* bo3_admit_run + the dependency rules; k[0..nk-1] (nk <= BO3_ADMIT_MAX * 4) are the listed mods that are not in m.
 * bo3_admit_run(m, n, r) = bo3_admit_run_deps(m, n, NULL, 0, r): a required mod that is not in m is "not installed". */
int bo3_admit_run_deps(const bo3_admit_mod *m, int n, const bo3_admit_known *k, int nk, bo3_admit_res *r);
/* The dependency order (pure): m[0..n-1] in the mod list's order (every listed mod; text NULL = declares nothing, e.g. not
 * usable); perm[0..n-1] receives the new order (perm[j] = the old index placed j-th). Returns the number of mods placed
 * elsewhere than before (0: the old order), -1 bad arguments / out of host memory (perm = identity). */
int bo3_admit_order(const bo3_admit_mod *m, int n, int *perm);
/* the free rows of a race location ("US_C3") for added events (6 - its retail events), -1 when it is no race location */
int bo3_admit_location_free(const char *loc);

#ifdef BO3_ADMIT_GAME
/* main.c, before bo3_modfs_init: the admission joins modfs's list_mods (bo3_modfs_set_admit) */
void bo3_admit_game_install(void);
#endif

#endif
