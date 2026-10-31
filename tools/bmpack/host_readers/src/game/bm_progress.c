/* bm_progress.c - Burnout Mashup EXPERIMENTAL progress sidecar (bm_progress.h; SIDECAR_DESIGN.md).
 * MUT=n (test builds only) compiles one deliberate defect, so the tests can show they detect unsafe persistence. */
#include "bm_progress.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MUT
#define MUT 0
#endif

static const uint8_t k_magic[8] = {'B', 'M', 'P', 'R', 'O', 'G', '\r', '\n'};
enum { REC_CONTENT = 1, RECF_CRITICAL = 1 };

typedef struct rec {
    uint16_t type, flags;
    uint32_t len;
    uint8_t *data;
} rec;

typedef struct fp {                      /* the committed file as it was seen: absent, or size + CRC of all its bytes */
    int exists;
    size_t size;
    uint32_t crc;
} fp;

struct bm_prog {
    const bm_prog_io *io;
    char path[4][1100];                  /* main, tmp, bak, lock */
    char base[1100];
    char profile[BM_PROG_MAX_PROFILE + 1];
    void *lk;
    int writable;
    int status;
    int main_damaged;                    /* the committed file is damaged (recovered from tmp / bak): kept as .bad-N first */
    uint64_t generation, max_seen_gen;
    uint32_t save_stamp;
    fp main_fp;
    rec *r;
    uint32_t n, cap;
};

enum { P_MAIN = 0, P_TMP, P_BAK, P_LOCK };

/* ---------- small helpers ---------- */
uint32_t bm_prog_crc32(const void *p, size_t n)
{
    static uint32_t t[256];
    static int init;
    const uint8_t *b = (const uint8_t *)p;
    uint32_t c = 0xFFFFFFFFu;
    if (!init) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t x = i;
            for (int k = 0; k < 8; k++)
                x = x & 1 ? 0xEDB88320u ^ (x >> 1) : x >> 1;
            t[i] = x;
        }
        init = 1;
    }
    for (size_t i = 0; i < n; i++)
        c = t[(c ^ b[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

static uint16_t g16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t g32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t g64(const uint8_t *p) { return (uint64_t)g32(p) | (uint64_t)g32(p + 4) << 32; }
static void p16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void p32(uint8_t *p, uint32_t v) { p16(p, v & 0xFFFF); p16(p + 2, v >> 16); }
static void p64(uint8_t *p, uint64_t v) { p32(p, (uint32_t)v); p32(p + 4, (uint32_t)(v >> 32)); }

static int ns_char(int c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-'; }
static int local_char(int c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-'; }
static int ver_char(int c) { return c > 0x20 && c < 0x7F; }

static int str_ok(const char *s, size_t n, size_t max, int (*ok)(int))
{
    if (n < 1 || n > max)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!ok((unsigned char)s[i]))
            return 0;
    return 1;
}

/* "ns/local" or "" */
static int ref_ok(const char *s, size_t n)
{
    const char *sl;
    if (n == 0)
        return 1;
    sl = memchr(s, '/', n);
    if (!sl)
        return 0;
    return str_ok(s, (size_t)(sl - s), BM_PROG_MAX_NS, ns_char) && str_ok(sl + 1, n - (size_t)(sl - s) - 1, BM_PROG_MAX_LOCAL, local_char);
}

const char *bm_prog_status_name(int s)
{
    static const char *const k[] = {"OK", "NEW", "RECOVERED", "FAILED", "LOCKED", "NEWER", "PROFILE_MISMATCH", "READ_ONLY",
                                    "CONFLICT", "IO_ERROR", "BAD_ARG", "NOT_FOUND", "OPAQUE"};
    return s >= 0 && s < (int)(sizeof k / sizeof k[0]) ? k[s] : "?";
}

int bm_prog_key_make(bm_prog_key *k, int kind, const char *ns, const char *local)
{
    if (!k || !ns || !local || kind < BM_PROG_TRACK || kind > BM_PROG_LAST_KIND ||
        !str_ok(ns, strlen(ns), BM_PROG_MAX_NS, ns_char) || !str_ok(local, strlen(local), BM_PROG_MAX_LOCAL, local_char))
        return BM_PROG_BAD_ARG;
    memset(k, 0, sizeof *k);
    k->kind = kind;
    memcpy(k->ns, ns, strlen(ns));
    memcpy(k->local, local, strlen(local));
    return BM_PROG_OK;
}

/* ---------- the content record ----------
 * u8 kind, u8 ns_len, u8 local_len, u8 modver_len, u16 data_version, u16 data_len, ns, local, modver, data */
typedef struct cview {
    int kind;
    const char *ns, *local, *modver;
    size_t ns_n, local_n, modver_n;
    uint16_t dver;
    const uint8_t *data;
    size_t data_n;
} cview;

static int data_ok(int kind, uint16_t dver, const uint8_t *d, size_t n)
{
    if (dver == 0)
        return 0;
    if (dver > 1 || kind > BM_PROG_LAST_KIND)
        return 1;                        /* a newer data version / an unknown kind: kept opaque, length-checked only */
    if (kind == BM_PROG_TRACK) {         /* u32 races, total; f32 max_20c, max_2a0; u16 best_car; u8 loc_n; u8 0; loc; u16 shadow_n; shadow */
        size_t ln, sn;
        if (n < 20)
            return 0;
        ln = d[18];
        if (d[19] != 0 || n < 20 + ln + 2 || !ref_ok((const char *)d + 20, ln))
            return 0;
        sn = g16(d + 20 + ln);
        return (sn == 0 || sn == BM_PROG_SHADOW_SIZE) && n == 20 + ln + 2 + sn;
    }
    if (kind == BM_PROG_EVENT) {         /* u8 medal, u8 completed, u16 0, u32 attempts, u32 best, u8 loc_n, loc */
        size_t ln;
        if (n < 13 || d[0] > 3 || d[1] > 1 || g16(d + 2) != 0)
            return 0;
        ln = d[12];
        return n == 13 + ln && ref_ok((const char *)d + 13, ln);
    }
    if (kind == BM_PROG_VEHICLE)         /* GP-VEH1: u8 n, u8 0, u16 0, paint[n] (1..111, a canonical paint ID) */
        return n >= 5 && d[0] >= 1 && d[1] == 0 && g16(d + 2) == 0 && n == 4u + d[0] && d[0] < sizeof(((bm_prog_vehicle *)0)->paint);
    /* LOCATION: u8 unlocked, u8 visited, u16 0, u32 events_completed */
    return n == 8 && d[0] <= 1 && d[1] <= 1 && g16(d + 2) == 0;
}

static int cparse(const uint8_t *p, size_t n, cview *v)
{
    size_t need;
    if (n < 8)
        return 0;
    v->kind = p[0];
    v->ns_n = p[1];
    v->local_n = p[2];
    v->modver_n = p[3];
    v->dver = g16(p + 4);
    v->data_n = g16(p + 6);
    need = 8 + v->ns_n + v->local_n + v->modver_n + v->data_n;
    if (need != n || v->kind < 1)
        return 0;
    v->ns = (const char *)p + 8;
    v->local = v->ns + v->ns_n;
    v->modver = v->local + v->local_n;
    v->data = (const uint8_t *)v->modver + v->modver_n;
    if (!str_ok(v->ns, v->ns_n, BM_PROG_MAX_NS, ns_char) || !str_ok(v->local, v->local_n, BM_PROG_MAX_LOCAL, local_char) ||
        (v->modver_n && !str_ok(v->modver, v->modver_n, BM_PROG_MAX_MODVER, ver_char)))
        return 0;
    return data_ok(v->kind, v->dver, v->data, v->data_n);
}

static int same_key(const cview *a, const cview *b)
{
    return a->kind == b->kind && a->ns_n == b->ns_n && a->local_n == b->local_n && !memcmp(a->ns, b->ns, a->ns_n) &&
           !memcmp(a->local, b->local, a->local_n);
}

static int key_is(const cview *a, const bm_prog_key *k)
{
    return a->kind == k->kind && a->ns_n == strlen(k->ns) && a->local_n == strlen(k->local) && !memcmp(a->ns, k->ns, a->ns_n) &&
           !memcmp(a->local, k->local, a->local_n);
}

/* ---------- the file image ---------- */
static void recs_free(rec *r, uint32_t n)
{
    for (uint32_t i = 0; i < n; i++)
        free(r[i].data);
    free(r);
}

typedef struct parsed {
    uint32_t flag;                       /* BM_PROG_F_* */
    uint64_t gen;
    uint32_t stamp;
    rec *r;
    uint32_t n;
    char why[160];
} parsed;

static void parse(const uint8_t *b, size_t n, const char *profile, parsed *o)
{
    uint32_t body, cnt, i, off;
    size_t pl;
    memset(o, 0, sizeof *o);
    o->flag = BM_PROG_F_INVALID;
    if (n < BM_PROG_HEADER_SIZE || memcmp(b, k_magic, 8) != 0) {
        snprintf(o->why, sizeof o->why, "not a sidecar (size %u or magic)", (unsigned)n);
        return;
    }
    if (bm_prog_crc32(b, 92) != g32(b + 92) || g16(b + 12) != BM_PROG_HEADER_SIZE || g16(b + 8) < 1) {
        snprintf(o->why, sizeof o->why, "header damaged (CRC / size / version)");
        return;
    }
#if MUT != 8
    if (g16(b + 10) > BM_PROG_READER_VERSION) {
        o->flag = BM_PROG_F_NEWER;
        snprintf(o->why, sizeof o->why, "written for readers >= %u (this is %u)", g16(b + 10), BM_PROG_READER_VERSION);
        return;
    }
#endif
    body = g32(b + 28);
    cnt = g32(b + 24);
    if (body != n - BM_PROG_HEADER_SIZE || body > BM_PROG_MAX_BODY || cnt > BM_PROG_MAX_RECORDS) {
        snprintf(o->why, sizeof o->why, "truncated or out of bounds (body %u of %u bytes, %u records)", (unsigned)(n - BM_PROG_HEADER_SIZE),
                 body, cnt);
        return;
    }
#if MUT != 3
    if (bm_prog_crc32(b + BM_PROG_HEADER_SIZE, body) != g32(b + 32)) {
        snprintf(o->why, sizeof o->why, "body CRC mismatch");
        return;
    }
#endif
    pl = g16(b + 40);
#if MUT != 9
    if (pl > BM_PROG_MAX_PROFILE || pl != strlen(profile) || memcmp(b + 42, profile, pl) != 0) {
        o->flag = BM_PROG_F_OTHER_PROFILE;
        snprintf(o->why, sizeof o->why, "belongs to another profile");
        return;
    }
#else
    (void)pl;
    (void)profile;
#endif
    o->r = (rec *)calloc(cnt ? cnt : 1, sizeof(rec));
    if (!o->r) {
        snprintf(o->why, sizeof o->why, "no memory");
        return;
    }
    for (i = 0, off = BM_PROG_HEADER_SIZE; i < cnt; i++) {
        rec *r = &o->r[i];
        if (n - off < 8) {
            snprintf(o->why, sizeof o->why, "record %u header past the end", i);
            goto bad;
        }
        r->type = g16(b + off);
        r->flags = g16(b + off + 2);
        r->len = g32(b + off + 4);
        if (r->len > BM_PROG_MAX_PAYLOAD || r->len > n - off - 8) {
            snprintf(o->why, sizeof o->why, "record %u length %u out of bounds", i, r->len);
            goto bad;
        }
        r->data = (uint8_t *)malloc(r->len ? r->len : 1);
        if (!r->data)
            goto bad;
        memcpy(r->data, b + off + 8, r->len);
        o->n = i + 1;
        off += 8 + r->len;
        if (r->type == REC_CONTENT) {
            cview v, w;
            if (!cparse(r->data, r->len, &v)) {
                snprintf(o->why, sizeof o->why, "record %u: malformed content record", i);
                goto bad;
            }
#if MUT == 7
            (void)w;
            (void)same_key;
#else
            for (uint32_t j = 0; j < i; j++)
                if (o->r[j].type == REC_CONTENT && cparse(o->r[j].data, o->r[j].len, &w) && same_key(&v, &w)) {
                    snprintf(o->why, sizeof o->why, "record %u: duplicate content key %.*s/%.*s", i, (int)v.ns_n, v.ns,
                             (int)v.local_n, v.local);
                    goto bad;
                }
#endif
        } else if (r->flags & RECF_CRITICAL) {
            o->flag |= BM_PROG_F_CRITICAL_UNKNOWN;
        }
    }
    if (off != n) {
        snprintf(o->why, sizeof o->why, "%u bytes after the last record", (unsigned)(n - off));
        goto bad;
    }
    o->gen = g64(b + 16);
    o->stamp = g32(b + 36);
    o->flag = (o->flag & BM_PROG_F_CRITICAL_UNKNOWN) | BM_PROG_F_VALID;
    return;
bad:
    recs_free(o->r, o->n);
    o->r = NULL;
    o->n = 0;
    o->flag = BM_PROG_F_INVALID;
}

static uint8_t *build(const bm_prog *p, uint64_t gen, uint32_t stamp, size_t *outn)
{
    size_t body = 0, off = BM_PROG_HEADER_SIZE;
    uint32_t cnt = 0;
    uint8_t *b;
    for (uint32_t i = 0; i < p->n; i++) {
#if MUT == 5
        if (p->r[i].type != REC_CONTENT)
            continue;                    /* defect: unknown records are dropped on rewrite */
#endif
        body += 8 + p->r[i].len;
        cnt++;
    }
    if (body > BM_PROG_MAX_BODY || cnt > BM_PROG_MAX_RECORDS)
        return NULL;
    b = (uint8_t *)calloc(1, BM_PROG_HEADER_SIZE + body);
    if (!b)
        return NULL;
    memcpy(b, k_magic, 8);
    p16(b + 8, BM_PROG_FORMAT_VERSION);
    p16(b + 10, 1);                      /* the oldest reader that may use it */
    p16(b + 12, BM_PROG_HEADER_SIZE);
    p16(b + 14, 0);
    p64(b + 16, gen);
    p32(b + 24, cnt);
    p32(b + 28, (uint32_t)body);
    p32(b + 36, stamp);
    p16(b + 40, (uint32_t)strlen(p->profile));
    memcpy(b + 42, p->profile, strlen(p->profile));
    for (uint32_t i = 0; i < p->n; i++) {
#if MUT == 5
        if (p->r[i].type != REC_CONTENT)
            continue;
#endif
        p16(b + off, p->r[i].type);
        p16(b + off + 2, p->r[i].flags);
        p32(b + off + 4, p->r[i].len);
        memcpy(b + off + 8, p->r[i].data, p->r[i].len);
        off += 8 + p->r[i].len;
    }
    p32(b + 32, bm_prog_crc32(b + BM_PROG_HEADER_SIZE, body));
    p32(b + 92, bm_prog_crc32(b, 92));
    *outn = BM_PROG_HEADER_SIZE + body;
    return b;
}

/* ---------- open ---------- */
static int name_ok(const char *s)
{
    size_t n = s ? strlen(s) : 0;
    if (n < 1 || n > BM_PROG_MAX_NAME || s[0] == '.' || s[0] == ' ')
        return 0;
    for (size_t i = 0; i < n; i++) {
        int c = (unsigned char)s[i];
        if (!(local_char(c) || c == '.' || c == ' '))
            return 0;
    }
    return 1;
}

static void look(bm_prog *p, int which, parsed *o, fp *f)
{
    uint8_t *buf = NULL;
    size_t n = 0;
    int rc = p->io->read_file(p->io->ctx, p->path[which], BM_PROG_MAX_FILE, &buf, &n);
    memset(o, 0, sizeof *o);
    if (f)
        memset(f, 0, sizeof *f);
    if (rc == 0) {
        o->flag = BM_PROG_F_ABSENT;
        return;
    }
    if (rc < 0) {
        o->flag = BM_PROG_F_INVALID;
        snprintf(o->why, sizeof o->why, "unreadable or larger than %u bytes", (unsigned)BM_PROG_MAX_FILE);
        if (f) {                         /* it exists: its identity is "unreadable" (a conflict check sees a change) */
            f->exists = 1;
            f->size = (size_t)-1;
        }
        return;
    }
    if (f) {
        f->exists = 1;
        f->size = n;
        f->crc = bm_prog_crc32(buf, n);
    }
    parse(buf, n, p->profile, o);
    free(buf);
}

static void take(bm_prog *p, parsed *o)
{
    recs_free(p->r, p->n);
    p->r = o->r;
    p->n = p->cap = o->n;
    p->generation = o->gen;
    p->save_stamp = o->stamp;
    o->r = NULL;
    o->n = 0;
}

int bm_prog_open(const bm_prog_io *io, const char *dir, const char *name, const char *profile_id, uint32_t flags,
                 bm_prog **out, bm_prog_report *rep)
{
    static const char *const sfx[4] = {".bmprog", ".bmprog.tmp", ".bmprog.bak", ".bmprog.lock"};
    bm_prog *p;
    parsed m, t, k;
    bm_prog_report dummy;
    if (!rep)
        rep = &dummy;
    memset(rep, 0, sizeof *rep);
    if (out)
        *out = NULL;
    if (!io || !out || !dir || !*dir || strlen(dir) > 1000 || !name_ok(name) || !profile_id || !*profile_id ||
        strlen(profile_id) > BM_PROG_MAX_PROFILE) {
        rep->status = BM_PROG_BAD_ARG;
        return BM_PROG_BAD_ARG;
    }
    for (const char *c = profile_id; *c; c++)
        if (!ver_char((unsigned char)*c) && *c != ' ') {
            rep->status = BM_PROG_BAD_ARG;
            return BM_PROG_BAD_ARG;
        }
    p = (bm_prog *)calloc(1, sizeof *p);
    if (!p)
        return BM_PROG_IO_ERROR;
    p->io = io;
    snprintf(p->base, sizeof p->base, "%s/%s", dir, name);
    for (int i = 0; i < 4; i++)
        snprintf(p->path[i], sizeof p->path[i], "%s%s", p->base, sfx[i]);
    memcpy(p->profile, profile_id, strlen(profile_id) + 1);
#if MUT != 6
    if (!(flags & BM_PROG_OPEN_READ_ONLY))
        p->lk = io->lock(io->ctx, p->path[P_LOCK]);
#else
    (void)flags;
    p->lk = (void *)1;                   /* defect: no lock (and no conflict check at commit) */
#endif
    look(p, P_MAIN, &m, &p->main_fp);
    look(p, P_TMP, &t, NULL);
    look(p, P_BAK, &k, NULL);
    rep->main = m.flag;
    rep->tmp = t.flag;
    rep->bak = k.flag;
    p->max_seen_gen = m.gen > t.gen ? m.gen : t.gen;
    if (k.gen > p->max_seen_gen)
        p->max_seen_gen = k.gen;

    if (m.flag & BM_PROG_F_VALID) {
        take(p, &m);
        rep->source = BM_PROG_SRC_MAIN;
        p->status = (m.flag & BM_PROG_F_CRITICAL_UNKNOWN) ? BM_PROG_NEWER : BM_PROG_OK;
        if (m.flag & BM_PROG_F_CRITICAL_UNKNOWN)
            snprintf(rep->why, sizeof rep->why, "a record type this version does not know is marked critical: read-only");
    } else if (m.flag & BM_PROG_F_NEWER) {
        p->status = BM_PROG_NEWER;
        snprintf(rep->why, sizeof rep->why, "%s", m.why);
    } else if (m.flag & BM_PROG_F_OTHER_PROFILE) {
        p->status = BM_PROG_PROFILE_MISMATCH;
        snprintf(rep->why, sizeof rep->why, "%s", m.why);
    } else {
        /* the committed file is missing or damaged: the newest valid of tmp (an interrupted commit) and bak */
        parsed *best = NULL;
        int src = BM_PROG_SRC_NONE;
        if ((t.flag & BM_PROG_F_VALID) && !(t.flag & BM_PROG_F_CRITICAL_UNKNOWN)) {
            best = &t;
            src = BM_PROG_SRC_TMP;
        }
        if ((k.flag & BM_PROG_F_VALID) && !(k.flag & BM_PROG_F_CRITICAL_UNKNOWN) && (!best || k.gen > best->gen)) {
            best = &k;
            src = BM_PROG_SRC_BAK;
        }
        if (best) {
            take(p, best);
            rep->source = src;
            p->status = BM_PROG_RECOVERED;
            p->main_damaged = (m.flag & BM_PROG_F_INVALID) != 0;
            snprintf(rep->why, sizeof rep->why, "committed file %s: loaded the %s copy (generation %llu)",
                     (m.flag & BM_PROG_F_ABSENT) ? "missing" : m.why, src == BM_PROG_SRC_TMP ? "interrupted-commit" : "backup",
                     (unsigned long long)p->generation);
        } else if ((m.flag & BM_PROG_F_ABSENT) && (t.flag & BM_PROG_F_ABSENT) && (k.flag & BM_PROG_F_ABSENT)) {
            p->status = BM_PROG_NEW;
        } else if ((t.flag | k.flag) & (BM_PROG_F_NEWER | BM_PROG_F_CRITICAL_UNKNOWN)) {
            p->status = BM_PROG_NEWER;
            snprintf(rep->why, sizeof rep->why, "only a newer version's copy is usable");
        } else {
#if MUT == 4
            p->status = BM_PROG_NEW;     /* defect: damaged progress is silently treated as none */
#else
            p->status = BM_PROG_FAILED;
            snprintf(rep->why, sizeof rep->why, "no valid copy: committed %s; tmp %s; backup %s",
                     (m.flag & BM_PROG_F_ABSENT) ? "missing" : m.why, (t.flag & BM_PROG_F_ABSENT) ? "missing" : t.why,
                     (k.flag & BM_PROG_F_ABSENT) ? "missing" : k.why);
#endif
        }
    }
    recs_free(m.r, m.n);
    recs_free(t.r, t.n);
    recs_free(k.r, k.n);
    p->writable = p->lk && !(flags & BM_PROG_OPEN_READ_ONLY) &&
                  (p->status == BM_PROG_OK || p->status == BM_PROG_NEW || p->status == BM_PROG_RECOVERED);
    if (!p->lk && !(flags & BM_PROG_OPEN_READ_ONLY) &&
        (p->status == BM_PROG_OK || p->status == BM_PROG_NEW || p->status == BM_PROG_RECOVERED))
        p->status = BM_PROG_LOCKED;
    rep->status = p->status;
    rep->generation = p->generation;
    rep->save_stamp = p->save_stamp;
    for (uint32_t i = 0; i < p->n; i++) {
        cview v;
        rep->records += p->r[i].type == REC_CONTENT;
        if (p->r[i].type != REC_CONTENT || (cparse(p->r[i].data, p->r[i].len, &v) && (v.dver > 1 || v.kind > BM_PROG_LAST_KIND)))
            rep->unknown_records++;
    }
    *out = p;
    return p->status;
}

int bm_prog_writable(const bm_prog *p)
{
    return p && p->writable;
}

/* ---------- records ---------- */
static int find(const bm_prog *p, const bm_prog_key *k, cview *v)
{
    for (uint32_t i = 0; i < p->n; i++)
        if (p->r[i].type == REC_CONTENT && cparse(p->r[i].data, p->r[i].len, v) && key_is(v, k))
            return (int)i;
    return -1;
}

static int key_valid(const bm_prog_key *k)
{
    bm_prog_key c;
    return k && bm_prog_key_make(&c, k->kind, k->ns, k->local) == BM_PROG_OK;
}

static int get_common(const bm_prog *p, const bm_prog_key *k, int kind, cview *v)
{
    if (!p || !key_valid(k) || k->kind != kind)
        return BM_PROG_BAD_ARG;
    if (find(p, k, v) < 0)
        return BM_PROG_NOT_FOUND;
    return v->dver == 1 ? BM_PROG_OK : BM_PROG_OPAQUE;
}

static void ref_out(char *dst, size_t cap, const uint8_t *s, size_t n)
{
    if (n >= cap)
        n = 0;
    memcpy(dst, s, n);
    dst[n] = 0;
}

int bm_prog_get_track(const bm_prog *p, const bm_prog_key *k, bm_prog_track *out)
{
    cview v;
    int rc = get_common(p, k, BM_PROG_TRACK, &v);
    size_t ln;
    if (rc != BM_PROG_OK || !out)
        return out ? rc : BM_PROG_BAD_ARG;
    memset(out, 0, sizeof *out);
    out->races = g32(v.data);
    out->total_170 = g32(v.data + 4);
    {
        uint32_t a = g32(v.data + 8), b = g32(v.data + 12);
        memcpy(&out->max_20c, &a, 4);
        memcpy(&out->max_2a0, &b, 4);
    }
    out->best_car = g16(v.data + 16);
    ln = v.data[18];
    ref_out(out->location, sizeof out->location, v.data + 20, ln);
    out->shadow_len = g16(v.data + 20 + ln);
    memcpy(out->shadow, v.data + 22 + ln, out->shadow_len);
    return BM_PROG_OK;
}

int bm_prog_get_event(const bm_prog *p, const bm_prog_key *k, bm_prog_event *out)
{
    cview v;
    int rc = get_common(p, k, BM_PROG_EVENT, &v);
    if (rc != BM_PROG_OK || !out)
        return out ? rc : BM_PROG_BAD_ARG;
    memset(out, 0, sizeof *out);
    out->medal = v.data[0];
    out->completed = v.data[1];
    out->attempts = g32(v.data + 4);
    out->best_result = g32(v.data + 8);
    ref_out(out->location, sizeof out->location, v.data + 13, v.data[12]);
    return BM_PROG_OK;
}

int bm_prog_get_location(const bm_prog *p, const bm_prog_key *k, bm_prog_location *out)
{
    cview v;
    int rc = get_common(p, k, BM_PROG_LOCATION, &v);
    if (rc != BM_PROG_OK || !out)
        return out ? rc : BM_PROG_BAD_ARG;
    memset(out, 0, sizeof *out);
    out->unlocked = v.data[0];
    out->visited = v.data[1];
    out->events_completed = g32(v.data + 4);
    return BM_PROG_OK;
}

static int put_raw(bm_prog *p, const bm_prog_key *k, const char *modver, const uint8_t *d, size_t dn)
{
    size_t nn, ln, vn = modver ? strlen(modver) : 0, len;
    uint8_t *buf;
    cview v;
    int at;
    if (!p || !key_valid(k) || (vn && !str_ok(modver, vn, BM_PROG_MAX_MODVER, ver_char)))
        return BM_PROG_BAD_ARG;
    if (!p->writable)
        return BM_PROG_READ_ONLY;
    nn = strlen(k->ns);
    ln = strlen(k->local);
    len = 8 + nn + ln + vn + dn;
    if (len > BM_PROG_MAX_PAYLOAD || !data_ok(k->kind, 1, d, dn))
        return BM_PROG_BAD_ARG;
    at = find(p, k, &v);
    if (at >= 0 && v.dver != 1)
        return BM_PROG_OPAQUE;          /* written by a newer version: not overwritten by an older one */
    if (at < 0 && p->n >= BM_PROG_MAX_RECORDS)
        return BM_PROG_BAD_ARG;
    buf = (uint8_t *)malloc(len);
    if (!buf)
        return BM_PROG_IO_ERROR;
    buf[0] = (uint8_t)k->kind;
    buf[1] = (uint8_t)nn;
    buf[2] = (uint8_t)ln;
    buf[3] = (uint8_t)vn;
    p16(buf + 4, 1);
    p16(buf + 6, (uint32_t)dn);
    memcpy(buf + 8, k->ns, nn);
    memcpy(buf + 8 + nn, k->local, ln);
    memcpy(buf + 8 + nn + ln, modver ? modver : "", vn);
    memcpy(buf + 8 + nn + ln + vn, d, dn);
    if (at >= 0) {
        free(p->r[at].data);
        p->r[at].data = buf;
        p->r[at].len = (uint32_t)len;
        return BM_PROG_OK;
    }
    if (p->n == p->cap) {
        uint32_t nc = p->cap ? p->cap * 2 : 16;
        rec *r = (rec *)realloc(p->r, nc * sizeof(rec));
        if (!r) {
            free(buf);
            return BM_PROG_IO_ERROR;
        }
        p->r = r;
        p->cap = nc;
    }
    p->r[p->n].type = REC_CONTENT;
    p->r[p->n].flags = 0;
    p->r[p->n].len = (uint32_t)len;
    p->r[p->n].data = buf;
    p->n++;
    return BM_PROG_OK;
}

static size_t ref_in(uint8_t *dst, const char *s)
{
    size_t n = strnlen(s, BM_PROG_MAX_NS + BM_PROG_MAX_LOCAL + 2);
    memcpy(dst, s, n);
    return n;
}

int bm_prog_put_track(bm_prog *p, const bm_prog_key *k, const char *modver, const bm_prog_track *t)
{
    uint8_t d[20 + 98 + 2 + BM_PROG_SHADOW_SIZE];
    size_t ln;
    uint32_t a, b;
    if (!t || !k || k->kind != BM_PROG_TRACK || (t->shadow_len != 0 && t->shadow_len != BM_PROG_SHADOW_SIZE))
        return BM_PROG_BAD_ARG;
    memset(d, 0, sizeof d);
    memcpy(&a, &t->max_20c, 4);
    memcpy(&b, &t->max_2a0, 4);
    p32(d, t->races);
    p32(d + 4, t->total_170);
    p32(d + 8, a);
    p32(d + 12, b);
    p16(d + 16, t->best_car);
    ln = ref_in(d + 20, t->location);
    if (ln > 97)
        return BM_PROG_BAD_ARG;
    d[18] = (uint8_t)ln;
    p16(d + 20 + ln, t->shadow_len);
    memcpy(d + 22 + ln, t->shadow, t->shadow_len);
    return put_raw(p, k, modver, d, 22 + ln + t->shadow_len);
}

int bm_prog_put_event(bm_prog *p, const bm_prog_key *k, const char *modver, const bm_prog_event *e)
{
    uint8_t d[13 + 98];
    size_t ln;
    if (!e || !k || k->kind != BM_PROG_EVENT)
        return BM_PROG_BAD_ARG;
    memset(d, 0, sizeof d);
    d[0] = e->medal;
    d[1] = e->completed;
    p32(d + 4, e->attempts);
    p32(d + 8, e->best_result);
    ln = ref_in(d + 13, e->location);
    if (ln > 97)
        return BM_PROG_BAD_ARG;
    d[12] = (uint8_t)ln;
    return put_raw(p, k, modver, d, 13 + ln);
}

int bm_prog_put_location(bm_prog *p, const bm_prog_key *k, const char *modver, const bm_prog_location *l)
{
    uint8_t d[8] = {0};
    if (!l || !k || k->kind != BM_PROG_LOCATION)
        return BM_PROG_BAD_ARG;
    d[0] = l->unlocked;
    d[1] = l->visited;
    p32(d + 4, l->events_completed);
    return put_raw(p, k, modver, d, 8);
}

/* GP-VEH1 */
int bm_prog_get_vehicle(const bm_prog *p, const bm_prog_key *k, bm_prog_vehicle *out)
{
    cview v;
    int rc = get_common(p, k, BM_PROG_VEHICLE, &v);
    if (rc != BM_PROG_OK || !out)
        return out ? rc : BM_PROG_BAD_ARG;
    memset(out, 0, sizeof *out);
    memcpy(out->paint, v.data + 4, v.data[0]);
    return BM_PROG_OK;
}

int bm_prog_put_vehicle(bm_prog *p, const bm_prog_key *k, const char *modver, const bm_prog_vehicle *e)
{
    uint8_t d[4 + sizeof e->paint];
    size_t n;
    if (!e || !k || k->kind != BM_PROG_VEHICLE)
        return BM_PROG_BAD_ARG;
    n = strnlen(e->paint, sizeof e->paint);
    if (!n || n >= sizeof e->paint)
        return BM_PROG_BAD_ARG;
    memset(d, 0, sizeof d);
    d[0] = (uint8_t)n;
    memcpy(d + 4, e->paint, n);
    return put_raw(p, k, modver, d, 4 + n);
}

int bm_prog_remove(bm_prog *p, const bm_prog_key *k)
{
    cview v;
    int at;
    if (!p || !key_valid(k))
        return BM_PROG_BAD_ARG;
    if (!p->writable)
        return BM_PROG_READ_ONLY;
    at = find(p, k, &v);
    if (at < 0)
        return BM_PROG_NOT_FOUND;
    free(p->r[at].data);
    memmove(&p->r[at], &p->r[at + 1], (p->n - (uint32_t)at - 1) * sizeof(rec));
    p->n--;
    return BM_PROG_OK;
}

uint32_t bm_prog_count(const bm_prog *p)
{
    uint32_t c = 0;
    for (uint32_t i = 0; p && i < p->n; i++)
        c += p->r[i].type == REC_CONTENT;
    return c;
}

int bm_prog_info_at(const bm_prog *p, uint32_t i, bm_prog_info *out)
{
    cview v;
    if (!p || !out)
        return BM_PROG_BAD_ARG;
    for (uint32_t j = 0; j < p->n; j++) {
        if (p->r[j].type != REC_CONTENT || i--)
            continue;
        if (!cparse(p->r[j].data, p->r[j].len, &v))
            return BM_PROG_BAD_ARG;
        memset(out, 0, sizeof *out);
        out->key.kind = v.kind;
        memcpy(out->key.ns, v.ns, v.ns_n);
        memcpy(out->key.local, v.local, v.local_n);
        memcpy(out->mod_version, v.modver, v.modver_n);
        out->data_version = v.dver;
        out->opaque = v.dver != 1 || v.kind > BM_PROG_LAST_KIND;
        return BM_PROG_OK;
    }
    return BM_PROG_NOT_FOUND;
}

/* ---------- commit ---------- */
static int write_file(bm_prog *p, const char *path, const uint8_t *img, size_t n)
{
    const bm_prog_io *io = p->io;
    void *h = io->create(io->ctx, path);
    int ok;
    if (!h)
        return 0;
    ok = io->write(io->ctx, h, img, n) == 0;
#if MUT != 1
    ok = ok && io->flush(io->ctx, h) == 0;
#endif
    ok = (io->close(io->ctx, h) == 0) && ok;
    return ok;
}

static int keep_bad(bm_prog *p, const char *path)
{
    char bad[1200];
    for (int i = 1; i < 1000; i++) {
        snprintf(bad, sizeof bad, "%s.bmprog.bad-%d", p->base, i);
        if (!p->io->exists(p->io->ctx, bad))
            return p->io->rename(p->io->ctx, path, bad) == 0;
    }
    return 0;
}

int bm_prog_commit(bm_prog *p, uint32_t save_stamp)
{
    const bm_prog_io *io;
    uint8_t *img, *back = NULL;
    size_t n, bn = 0;
    uint64_t gen;
    if (!p)
        return BM_PROG_BAD_ARG;
    if (!p->writable)
        return BM_PROG_READ_ONLY;
    io = p->io;
#if MUT != 6
    {   /* the committed file must still be the one this store was loaded against */
        parsed now;
        fp f;
        look(p, P_MAIN, &now, &f);
        recs_free(now.r, now.n);
        if (f.exists != p->main_fp.exists || (f.exists && (f.size != p->main_fp.size || f.crc != p->main_fp.crc)))
            return BM_PROG_CONFLICT;
    }
#endif
    gen = (p->max_seen_gen > p->generation ? p->max_seen_gen : p->generation) + 1;
    img = build(p, gen, save_stamp, &n);
    if (!img)
        return BM_PROG_BAD_ARG;
#if MUT == 2
    /* defect: written in place, no tmp and no backup */
    (void)io; (void)back; (void)bn;
    if (!write_file(p, p->path[P_MAIN], img, n)) {
        free(img);
        return BM_PROG_IO_ERROR;
    }
#else
    if (p->main_damaged && io->exists(io->ctx, p->path[P_MAIN]) && !keep_bad(p, p->path[P_MAIN])) {
        free(img);
        return BM_PROG_IO_ERROR;         /* the damaged file is kept aside before anything replaces it */
    }
    p->main_damaged = 0;
    if (p->main_fp.exists && !io->exists(io->ctx, p->path[P_MAIN]))
        p->main_fp.exists = 0;           /* moved to .bad-N just now */
    if (!write_file(p, p->path[P_TMP], img, n) ||
        io->read_file(io->ctx, p->path[P_TMP], BM_PROG_MAX_FILE, &back, &bn) != 1 || bn != n || memcmp(back, img, n) != 0) {
        free(back);
        free(img);
        io->remove(io->ctx, p->path[P_TMP]);
        return BM_PROG_IO_ERROR;         /* the committed file is untouched */
    }
    free(back);
    if (io->exists(io->ctx, p->path[P_MAIN]) && io->rename(io->ctx, p->path[P_MAIN], p->path[P_BAK]) != 0) {
        free(img);
        return BM_PROG_IO_ERROR;         /* main untouched; the complete tmp stays for the next open (main wins) */
    }
    if (io->rename(io->ctx, p->path[P_TMP], p->path[P_MAIN]) != 0) {
        free(img);
        p->main_fp.exists = 0;           /* main is now the backup: the next open recovers tmp or bak, both valid */
        p->writable = 0;
        return BM_PROG_IO_ERROR;
    }
#endif
    p->main_fp.exists = 1;
    p->main_fp.size = n;
    p->main_fp.crc = bm_prog_crc32(img, n);
    free(img);
    p->generation = p->max_seen_gen = gen;
    p->save_stamp = save_stamp;
    if (p->status == BM_PROG_NEW || p->status == BM_PROG_RECOVERED)
        p->status = BM_PROG_OK;
    return BM_PROG_OK;
}

int bm_prog_quarantine(bm_prog *p)
{
    if (!p || p->status != BM_PROG_FAILED || !p->lk)
        return BM_PROG_READ_ONLY;
    for (int i = P_MAIN; i <= P_BAK; i++)
        if (p->io->exists(p->io->ctx, p->path[i]) && !keep_bad(p, p->path[i]))
            return BM_PROG_IO_ERROR;
    recs_free(p->r, p->n);
    p->r = NULL;
    p->n = p->cap = 0;
    memset(&p->main_fp, 0, sizeof p->main_fp);
    p->status = BM_PROG_NEW;
    p->writable = 1;
    return BM_PROG_OK;
}

void bm_prog_close(bm_prog *p)
{
    if (!p)
        return;
#if MUT != 6
    if (p->lk)
        p->io->unlock(p->io->ctx, p->lk);
#endif
    recs_free(p->r, p->n);
    free(p);
}
