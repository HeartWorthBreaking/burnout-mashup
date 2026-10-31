/*
 * bm_music.h - GP-MUSIC1 EXPERIMENTAL: music packs as data mods (mod.toml [bmashup.music]). Atlas gp\atlas\AUDIO.md.
 *
 *   [bmashup.music]
 *   version = 1
 *   soundtrack = "BM Test Tones"                       # the soundtrack's name in EA GAMES TRAX (with add)
 *   add = ["a440 = music/a440.wav | Tone 1 - 440 Hz | BM Test Lab | Synthetic Tones"]
 *   replace = ["gp.music.base/b1000 = music/c523.wav | Tone C523 | BM Test Lab"]
 *
 * An entry is "<id> = <file> | <title> | <artist> [| <album>]"; a replace entry names "<mod id>/<id>" of a track another
 * mod adds. What the game does with it (the upstream custom-music path, docs/custom-music.md, is reused):
 *   - every admitted music mod is one soundtrack in Driver Details > Settings > EA GAMES TRAX (X steps to it), its tracks
 *     the songs; the files are copied into a host cache (GP-P4.1: <cache>\set-<hash>\<soundtrack>\<title>.<ext>, bm_music.c; not the saves) and
 *     that folder is given to the title as the custom-music folder (the host decodes mp3 / flac / ogg / wav). Only when the
 *     player has no music folder of their own (audio.custom_music_dir): the player's folder wins, the mods' music is then
 *     not offered (logged). With "custom music at start" on (the default) the first music start switches to it (BO-230).
 *   - when one of the songs starts, its title, artist and album are written into the title's own track banner (the
 *     EA GAMES TRAX pop-up: 0x45BB10 title, 0x45BB14 artist, 0x45BB18 album, 0x45BB0C 5 s), exactly as the title's
 *     sub_001530D0 does for an EA GAMES TRAX track; not while the music volume (0x4AE1D5) is 0, as the title's own rule.
 *     The banner's code (0x153149..0x15319A) and the volume test (0x153869) are checked in guest memory first: a build
 *     without them gets no banner (logged), the music still plays.
 * Bounds: 16 music mods with a soundtrack; 64 entries a mod (add + replace); 256 tracks in all; a file at most 64 MiB, all
 * files at most 512 MiB; ids [a-z0-9_-] 1..24; title / artist / album printable ASCII 1..31 (the title is also the file
 * name: no \ / : * ? " < > |, no leading / trailing space or dot); soundtrack name as a title.
 * Conflicts (bm_admit.c, the later mod of a clash refused as a whole): a soundtrack name an earlier mod uses (case-
 * insensitive); more than 16 music mods; a replace of a track no admitted earlier mod adds, or one another mod already
 * replaced; a replace whose mod is not in the mod's [bmashup] requires_mods; an invalid [bmashup.music] (the reason named).
 * Files (checked at the start, after the admission): a missing / unreadable / unplayable / too large file drops that mod's
 * whole music (and the replaces that name its tracks), logged "[MUSIC] ERROR"; the mod's other content is untouched.
 * Evidence rule (AUDIO.md): a [MUSIC] / [SOUNDTRACK] line proves loading, never that the right sound was audible.
 */
#ifndef BO3_BM_MUSIC_H
#define BO3_BM_MUSIC_H

#include <stddef.h>
#include <stdint.h>

/* main18: music mods 16 -> 64. Engine bound: every music mod is one soundtrack of the host-made ST.DB, whose format (the
 * XDK soundtrack library in the title) holds XST_MAX_SOUNDTRACKS = 100 soundtrack blocks (xbox_soundtrack.h); 64 < 100.
 * The 256 tracks in all (BO3_MUSIC_MAX_TRACKS) are unchanged. */
#if defined(BO3_MOD_LIMITS_LEGACY) && BO3_MOD_LIMITS_LEGACY
#define BO3_MUSIC_MAX_MODS     16u
#else
#define BO3_MUSIC_MAX_MODS     64u
#endif
#define BO3_MUSIC_ENGINE_SOUNDTRACKS 100u        /* the ST.DB format's soundtrack blocks (XST_MAX_SOUNDTRACKS) */
_Static_assert(BO3_MUSIC_MAX_MODS <= BO3_MUSIC_ENGINE_SOUNDTRACKS, "music mods are soundtracks of the ST.DB (100 blocks)");
#define BO3_MUSIC_MAX_ENTRIES  64u
#define BO3_MUSIC_MAX_TRACKS   256u
#define BO3_MUSIC_TEXT_MAX     31u
#define BO3_MUSIC_ID_MAX       24u
#define BO3_MUSIC_FILE_MAX     120u
#define BO3_MUSIC_MODID_MAX    64u               /* = BO3_MOD_ID_MAX */
#define BO3_MUSIC_FILE_BYTES   (64u << 20)
#define BO3_MUSIC_ALL_BYTES    (512u << 20)
#define BO3_MUSIC_BANNER_SECS  5.0f              /* the title's own (0x3B1694) */

typedef struct bo3_music_entry {
    int replace;                                 /* 0 add, 1 replace */
    char key[BO3_MUSIC_MODID_MAX + 1 + BO3_MUSIC_ID_MAX + 1];   /* "<mod id>/<id>": the track's key (replace: the target) */
    char file[BO3_MUSIC_FILE_MAX + 1];           /* relative to the mod's folder */
    char title[BO3_MUSIC_TEXT_MAX + 1], artist[BO3_MUSIC_TEXT_MAX + 1], album[BO3_MUSIC_TEXT_MAX + 1];
} bo3_music_entry;

typedef struct bo3_music_decl {
    int present;                                 /* the mod has a [bmashup.music] table */
    char soundtrack[BO3_MUSIC_TEXT_MAX + 1];     /* "" when the mod only replaces */
    uint32_t n;
    bo3_music_entry e[BO3_MUSIC_MAX_ENTRIES];
} bo3_music_decl;

/* A mod's whole mod.toml (pure): 1 = nothing declared or a valid declaration (out filled, out->present), 0 = invalid with
 * why. mod_id names the declaring mod (the add keys are "<mod_id>/<id>"). requires_mods is not checked here (the
 * admission does: bo3_music_replace_listed). */
int bo3_music_parse(const char *text, size_t n, const char *mod_id, bo3_music_decl *out, char *why, size_t wn);
/* 1 when the mod id of a replace key is one of the mod's requires_mods ids (ids[0..nids-1]) */
int bo3_music_replace_listed(const char *key, const char *const *ids, int nids);
/* The title as a file name part: 1 when it can be one (the parse already requires it) */
int bo3_music_title_ok(const char *s);

/* ---- the plan (pure): admitted declarations in mod order -> soundtracks and tracks ---- */
typedef struct bo3_music_track {
    char key[sizeof ((bo3_music_entry *)0)->key];
    int mod;                                     /* the mod (declaration index) whose file plays */
    uint32_t entry;                              /* its entry */
    int st;                                      /* the soundtrack (plan index) the track is in */
    int dropped;                                 /* its file failed (or the mod's music was dropped) */
} bo3_music_track;
typedef struct bo3_music_st {
    char name[BO3_MUSIC_TEXT_MAX + 1];
    int mod;                                     /* the declaring mod */
    int dropped;
} bo3_music_st;
typedef struct bo3_music_plan {
    uint32_t nst, ntr;
    bo3_music_st st[BO3_MUSIC_MAX_MODS];
    bo3_music_track tr[BO3_MUSIC_MAX_TRACKS];
} bo3_music_plan;
/* d[0..n-1] = the admitted mods' declarations in mod order. Returns the number of entries skipped (a replace whose target
 * is not there, capacity: the admission refuses these first; counted here as defence in depth). */
int bo3_music_plan_make(const bo3_music_decl *d, int n, bo3_music_plan *p);
/* Drop mod m's music (its soundtrack, its tracks, the replaces of its tracks by others play nothing either). */
void bo3_music_plan_drop_mod(bo3_music_plan *p, int m);
/* The track a staged song is (its soundtrack folder and file name, as the scan named them), -1 none. */
int bo3_music_plan_find(const bo3_music_plan *p, const bo3_music_decl *d, const char *folder, const char *file);

/* ---- the banner (guest memory through an interface, so the tests run it) ---- */
typedef struct bo3_music_guest {
    int (*read)(void *user, uint32_t va, void *out, uint32_t n);
    int (*write)(void *user, uint32_t va, const void *in, uint32_t n);
    uint32_t (*alloc)(void *user, uint32_t size);                  /* guest heap, 0 = none */
    void *user;
} bo3_music_guest;
/* Checks the title's banner code and the volume test in guest memory (1 = this build's, banner on). */
int bo3_music_banner_configure(const bo3_music_guest *g);
/* One of the songs starts: the banner gets its texts (1 written, 0 not: not verified, volume 0, no guest memory). */
int bo3_music_banner_show(const char *title, const char *artist, const char *album);
uint32_t bo3_music_banner_count(void);

#ifdef BO3_MUSIC_GAME
/* main.c, after the mod list (modfs init + admission) and before the guest starts: stage the admitted mods' music */
void bo3_music_game_apply(void);
/* soundtrack.c: the title opened song `song` as `handle` (any thread), and made the decoder for `handle` (game thread) */
void bo3_music_note_open(uint32_t handle, uint32_t song);
void bo3_music_song_started(uint32_t handle);
#endif

#endif
