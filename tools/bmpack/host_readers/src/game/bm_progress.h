/*
 * bm_progress.h - Burnout Mashup EXPERIMENTAL progress sidecar (content_count\sidecar\SIDECAR_DESIGN.md).
 *
 * Progress for ADDED content (tracks, events, locations declared by mods) that the game's own save ("Profile 1", 0xEA00
 * bytes, version 0x10) has no slot for. The library keeps it in a separate file next to (never inside) the save:
 *
 *   <dir>\<name>.bmprog        the committed state
 *   <dir>\<name>.bmprog.bak    the previous committed state
 *   <dir>\<name>.bmprog.tmp    a commit in progress (or interrupted)
 *   <dir>\<name>.bmprog.lock   held (exclusive) by the one writer; released when its process ends
 *   <dir>\<name>.bmprog.bad-N  a damaged file kept aside (never deleted by the library)
 *
 * The library never opens, reads or writes the game's save: it is given no save path, only a directory and a base name
 * (letters, digits, ' ', '_', '-', '.'; the suffixes above are always added). The save's own checksum may be passed in as an
 * opaque 32-bit "save stamp" recorded with each commit (informational: it lets a host notice that the save was restored
 * from an older copy; the library never acts on it).
 *
 * Content keys are stable and namespaced: (kind, namespace, local id), e.g. (TRACK, "bmashup.test-track-us-c6", "US_C6_V1"):
 * the namespace is the declaring mod's id, the local id the mod's own name for the content. Keys never depend on mod-list
 * order or on positions in the game's tables. Records of mods that are not loaded stay in the file untouched (dormant).
 *
 * Format (little-endian; every field bounded; CRC32 over the header and over the body):
 *   header 96 bytes: magic "BMPROG\r\n", format version, the oldest reader version that may use the file, header size,
 *   flags, generation (u64, +1 per commit), record count, body size, body CRC32, save stamp, profile id (<= 48 bytes),
 *   header CRC32.
 *   body: records { u16 type, u16 flags, u32 length, payload }. Type 1 = CONTENT (below). Records of an unknown type are
 *   kept byte for byte and written back unchanged; an unknown type flagged CRITICAL makes the file read-only for this
 *   reader. Duplicate content keys make a file invalid.
 *
 * Threads: one bm_prog is used by one thread at a time. Processes: one writer per file (the lock); others open read-only.
 */
#ifndef BM_PROGRESS_H
#define BM_PROGRESS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BM_PROG_FORMAT_VERSION   1u
#define BM_PROG_READER_VERSION   1u      /* this library reads files whose min_reader_version <= this */
#define BM_PROG_HEADER_SIZE      96u
#define BM_PROG_MAX_RECORDS      4096u
#define BM_PROG_MAX_PAYLOAD      4096u   /* one record */
#define BM_PROG_MAX_BODY         (4u << 20)
#define BM_PROG_MAX_FILE         (BM_PROG_HEADER_SIZE + BM_PROG_MAX_BODY)
#define BM_PROG_MAX_NS           64u     /* namespace (a mod id) */
#define BM_PROG_MAX_LOCAL        32u     /* the mod's own content id */
#define BM_PROG_MAX_MODVER       32u
#define BM_PROG_MAX_PROFILE      48u
#define BM_PROG_MAX_NAME         64u
#define BM_PROG_SHADOW_SIZE      0x230u  /* the game's per-track record layout (a shadow copy for an added track) */

enum bm_prog_kind {                      /* content kinds */
    BM_PROG_TRACK    = 1,
    BM_PROG_EVENT    = 2,
    BM_PROG_LOCATION = 3,                /* an added location / region */
    BM_PROG_VEHICLE  = 4                 /* GP-VEH1: a car's chosen paint (canonical paint ID); older readers keep it opaque */
};
#define BM_PROG_LAST_KIND BM_PROG_VEHICLE

enum bm_prog_status {
    BM_PROG_OK = 0,                      /* opened the committed file / done */
    BM_PROG_NEW,                         /* no sidecar existed: empty, writable */
    BM_PROG_RECOVERED,                   /* the committed file was missing or damaged; a valid tmp / bak was loaded */
    BM_PROG_FAILED,                      /* files exist but none is valid: nothing loaded, READ-ONLY; files untouched */
    BM_PROG_LOCKED,                      /* another writer holds the file: loaded read-only */
    BM_PROG_NEWER,                       /* written by a newer, incompatible version: nothing loaded, read-only */
    BM_PROG_PROFILE_MISMATCH,            /* the file belongs to another profile: nothing loaded, read-only */
    BM_PROG_READ_ONLY,                   /* a change or commit was asked of a read-only store */
    BM_PROG_CONFLICT,                    /* the committed file changed since it was loaded: nothing written */
    BM_PROG_IO_ERROR,                    /* an I/O step failed: the previous committed state is still in place */
    BM_PROG_BAD_ARG,                     /* a malformed argument (id, name, bound) */
    BM_PROG_NOT_FOUND,
    BM_PROG_OPAQUE                       /* a record of a newer data version: kept, not readable / changeable here */
};

enum bm_prog_source { BM_PROG_SRC_NONE = 0, BM_PROG_SRC_MAIN, BM_PROG_SRC_TMP, BM_PROG_SRC_BAK };

/* per-file findings at open (bitmask per file in bm_prog_report) */
enum { BM_PROG_F_ABSENT = 1, BM_PROG_F_VALID = 2, BM_PROG_F_INVALID = 4, BM_PROG_F_NEWER = 8, BM_PROG_F_OTHER_PROFILE = 16,
       BM_PROG_F_CRITICAL_UNKNOWN = 32 };

typedef struct bm_prog_report {
    int status;                          /* bm_prog_status of the open */
    int source;                          /* bm_prog_source loaded */
    uint32_t main, tmp, bak;             /* BM_PROG_F_* per file */
    uint64_t generation;                 /* of the loaded state (0 = none) */
    uint32_t save_stamp;                 /* recorded with the loaded state */
    uint32_t records, unknown_records;   /* loaded; of them kept opaque (unknown type or newer data version) */
    char why[200];                       /* the first problem found, for the log */
} bm_prog_report;

/* ---- I/O (the filesystem; tests wrap it to inject faults). Paths are UTF-8. ---- */
typedef struct bm_prog_io {
    void *ctx;
    /* the whole file, at most max bytes: 1 read (*buf malloc'ed), 0 absent, -1 error or larger than max */
    int (*read_file)(void *ctx, const char *path, size_t max, uint8_t **buf, size_t *n);
    void *(*create)(void *ctx, const char *path);          /* create / truncate for writing; NULL on error */
    int (*write)(void *ctx, void *h, const void *p, size_t n);   /* 0 ok */
    int (*flush)(void *ctx, void *h);                     /* to stable storage; 0 ok */
    int (*close)(void *ctx, void *h);                     /* 0 ok */
    int (*rename)(void *ctx, const char *from, const char *to);  /* replaces `to`, durable on return; 0 ok */
    int (*remove)(void *ctx, const char *path);           /* 0 ok or absent */
    int (*exists)(void *ctx, const char *path);           /* 1 / 0 */
    void *(*lock)(void *ctx, const char *path);           /* exclusive; NULL when held elsewhere */
    void (*unlock)(void *ctx, void *lk);
} bm_prog_io;

const bm_prog_io *bm_prog_io_native(void);               /* Win32 (built and tested); POSIX (written, not tested) */

/* ---- content ---- */
typedef struct bm_prog_key {
    int kind;                            /* bm_prog_kind */
    char ns[BM_PROG_MAX_NS + 1];         /* [A-Za-z0-9._-], 1..64 */
    char local[BM_PROG_MAX_LOCAL + 1];   /* [A-Za-z0-9_-], 1..32 */
} bm_prog_key;

typedef struct bm_prog_track {           /* data version 1: the game's own per-track data for a track it has no slot for */
    uint32_t races;                      /* results recorded by the host for this track */
    uint32_t total_170;                  /* the game's per-track running total (profile +0x170 u32[36]; sub_0001B820) */
    float max_20c, max_2a0;              /* the game's per-track maxima (profile +0x20C / +0x2A0 f32[36]; sub_0001BA00 / BAF0) */
    uint16_t best_car;                   /* the game's car index; 0xFFFF = none */
    char location[BM_PROG_MAX_NS + 1 + BM_PROG_MAX_LOCAL + 1];  /* "ns/local" of its LOCATION, or "" (a retail region) */
    uint16_t shadow_len;                 /* 0 or BM_PROG_SHADOW_SIZE */
    uint8_t shadow[BM_PROG_SHADOW_SIZE]; /* the game-format record the host would hand the records panel */
} bm_prog_track;

typedef struct bm_prog_event {           /* data version 1 */
    uint8_t medal;                       /* 0 none, 1 bronze, 2 silver, 3 gold */
    uint8_t completed;                   /* 0 / 1 */
    uint32_t attempts;
    uint32_t best_result;                /* ms, or points for a score event; 0 = none */
    char location[BM_PROG_MAX_NS + 1 + BM_PROG_MAX_LOCAL + 1];
} bm_prog_event;

typedef struct bm_prog_location {        /* data version 1 */
    uint8_t unlocked;                    /* 0 / 1 */
    uint8_t visited;                     /* 0 / 1 */
    uint32_t events_completed;           /* the host's tally for this location's added events */
} bm_prog_location;

typedef struct bm_prog_vehicle {         /* data version 1 (GP-VEH1): u8 n, u8 0, u16 0, paint[n] */
    char paint[BM_PROG_MAX_NS + 1 + 40 + 1 + 6];   /* "<mod-id>/<paint>" or "retail/<ID>/<index>" */
} bm_prog_vehicle;

typedef struct bm_prog_info {            /* what a stored record says about itself */
    bm_prog_key key;
    uint16_t data_version;
    char mod_version[BM_PROG_MAX_MODVER + 1];   /* the declaring mod's version at the last write */
    int opaque;                          /* 1: a newer data version: kept, not readable here */
} bm_prog_info;

typedef struct bm_prog bm_prog;

/* flags for bm_prog_open */
enum { BM_PROG_OPEN_READ_ONLY = 1 };

/* Opens <dir>\<name>.bmprog for profile_id. Always returns a store in *out (read-only when status is not OK / NEW /
 * RECOVERED, or when READ_ONLY was asked) unless BAD_ARG or out of memory; *rep says what was found. */
int bm_prog_open(const bm_prog_io *io, const char *dir, const char *name, const char *profile_id, uint32_t flags,
                 bm_prog **out, bm_prog_report *rep);
int bm_prog_writable(const bm_prog *p);

int bm_prog_key_make(bm_prog_key *k, int kind, const char *ns, const char *local);   /* validates; BM_PROG_OK / BAD_ARG */

int bm_prog_get_track(const bm_prog *p, const bm_prog_key *k, bm_prog_track *out);
int bm_prog_get_event(const bm_prog *p, const bm_prog_key *k, bm_prog_event *out);
int bm_prog_get_location(const bm_prog *p, const bm_prog_key *k, bm_prog_location *out);
/* insert or replace (one record per key); mod_version = the declaring mod's version now */
int bm_prog_put_track(bm_prog *p, const bm_prog_key *k, const char *mod_version, const bm_prog_track *v);
int bm_prog_put_event(bm_prog *p, const bm_prog_key *k, const char *mod_version, const bm_prog_event *v);
int bm_prog_put_location(bm_prog *p, const bm_prog_key *k, const char *mod_version, const bm_prog_location *v);
int bm_prog_get_vehicle(const bm_prog *p, const bm_prog_key *k, bm_prog_vehicle *out);              /* GP-VEH1 */
int bm_prog_put_vehicle(bm_prog *p, const bm_prog_key *k, const char *mod_version, const bm_prog_vehicle *v);
int bm_prog_remove(bm_prog *p, const bm_prog_key *k);    /* an explicit host decision only; never automatic */

uint32_t bm_prog_count(const bm_prog *p);                /* content records (incl. opaque ones) */
int bm_prog_info_at(const bm_prog *p, uint32_t i, bm_prog_info *out);

/* Writes the store atomically (tmp -> flush -> read back -> main to bak -> tmp to main). On any failure the previous
 * committed state stays the committed file. save_stamp: the game save's checksum after its own successful save. */
int bm_prog_commit(bm_prog *p, uint32_t save_stamp);

/* After FAILED only, as an explicit host / user decision: the damaged files are kept as .bad-N (renamed, not deleted)
 * and the store becomes empty and writable. */
int bm_prog_quarantine(bm_prog *p);

void bm_prog_close(bm_prog *p);

const char *bm_prog_status_name(int status);
uint32_t bm_prog_crc32(const void *p, size_t n);

#ifdef __cplusplus
}
#endif
#endif
