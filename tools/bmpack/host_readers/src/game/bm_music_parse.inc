/* bm_music_parse.inc - GP-MUSIC1: the [bmashup.music] reader (bm_music.h), compiled into bm_music.c and bm_admit.c
 * (#include), so the admission reads a declaration exactly as the game does, with no new link dependency (the pattern of
 * bm_platform_gate.inc). Pure: recomp_cfg only. MUSIC_MUT=n (tests only): see bm_music.c. */
#ifndef MUSIC_MUT
#define MUSIC_MUT 0
#endif
#if defined(__GNUC__)
#define MU_FN static __attribute__((unused))
#else
#define MU_FN static
#endif

#define MU_PREFIX "bmashup.music"

MU_FN int mu_lower(int c)
{
    return c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c;
}

MU_FN int mu_eq_nocase(const char *a, const char *b)
{
    for (; *a && *b; a++, b++)
        if (mu_lower((unsigned char)*a) != mu_lower((unsigned char)*b))
            return 0;
    return *a == *b;
}

MU_FN void mu_trim(char *s)
{
    size_t n = strlen(s), a = 0;
    while (n && (s[n - 1] == ' ' || s[n - 1] == '\t'))
        s[--n] = 0;
    while (s[a] == ' ' || s[a] == '\t')
        a++;
    memmove(s, s + a, strlen(s + a) + 1);
}

/* CON, PRN, AUX, NUL, CLOCK$, CONIN$, CONOUT$, COM1-9, LPT1-9 as a name (up to its first dot), any case */
MU_FN int mu_device_name(const char *p, size_t len)
{
    static const char *const names[] = {"con", "prn", "aux", "nul", "clock$", "conin$", "conout$"};
    char low[8];
    size_t b = 0;
    while (b < len && p[b] != '.')
        b++;
    while (b && p[b - 1] == ' ')
        b--;
    if (b == 0 || b >= sizeof low)
        return 0;
    for (size_t i = 0; i < b; i++)
        low[i] = (char)mu_lower((unsigned char)p[i]);
    low[b] = 0;
    for (size_t i = 0; i < sizeof names / sizeof names[0]; i++)
        if (!strcmp(low, names[i]))
            return 1;
    return b == 4 && (!strncmp(low, "com", 3) || !strncmp(low, "lpt", 3)) && low[3] >= '1' && low[3] <= '9';
}

MU_FN int mu_text_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > BO3_MUSIC_TEXT_MAX || s[0] == ' ' || s[n - 1] == ' ')
        return 0;
    for (size_t i = 0; i < n; i++)
        if ((unsigned char)s[i] < 0x20 || (unsigned char)s[i] > 0x7E)
            return 0;
    return 1;
}

MU_FN int mu_title_ok(const char *s)
{
    size_t n;
    if (!s || !mu_text_ok(s))
        return 0;
    n = strlen(s);
    if (s[0] == '.' || s[n - 1] == '.' || mu_device_name(s, n))
        return 0;
#if MUSIC_MUT != 2
    for (size_t i = 0; i < n; i++)
        if (strchr("\\/:*?\"<>|", s[i]))
            return 0;
#endif
    return 1;
}

MU_FN int mu_id_ok(const char *s, size_t max)
{
    size_t n = strlen(s);
    if (!n || n > max)
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '_' || s[i] == '-'))
            return 0;
    return 1;
}

/* a mod id (modmanifest.c's rule): a-z 0-9 . _ -, starting with a letter or digit */
MU_FN int mu_mod_id_ok(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > BO3_MUSIC_MODID_MAX || !((s[0] >= 'a' && s[0] <= 'z') || (s[0] >= '0' && s[0] <= '9')))
        return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == '_' || s[i] == '-'))
            return 0;
    return 1;
}

MU_FN const char *mu_ext_of(const char *f)
{
    const char *d = strrchr(f, '.'), *s = strrchr(f, '/');
    return d && (!s || d > s) ? d : "";
}

/* a relative path of plain parts inside the mod's folder, not in files, ending as a song the host plays */
MU_FN int mu_file_ok(const char *v)
{
    static const char *const ends[] = {".wav", ".mp3", ".flac", ".ogg"};
    size_t n = strlen(v), start = 0;
    int part = 0, end_ok = 0;
    if (!n || n > BO3_MUSIC_FILE_MAX)
        return 0;
    for (size_t i = 0; i <= n; i++) {
        size_t len;
        if (v[i] != '/' && v[i])
            continue;
        len = i - start;
        if (len == 0)
            return 0;
#if MUSIC_MUT != 1
        if ((len == 1 && v[start] == '.') || (len == 2 && v[start] == '.' && v[start + 1] == '.') || v[i - 1] == '.' ||
            v[i - 1] == ' ' || v[start] == ' ')
            return 0;
#endif
        for (size_t k = start; k < i; k++)
            if (!((v[k] >= 'A' && v[k] <= 'Z') || (v[k] >= 'a' && v[k] <= 'z') || (v[k] >= '0' && v[k] <= '9') || v[k] == '.' ||
                  v[k] == '_' || v[k] == '-' || v[k] == ' '))
                return 0;
        if (mu_device_name(v + start, len))
            return 0;
        if (part++ == 0 && i < n && len == 5 && mu_lower((unsigned char)v[start]) == 'f' && mu_lower((unsigned char)v[start + 1]) == 'i' &&
            mu_lower((unsigned char)v[start + 2]) == 'l' && mu_lower((unsigned char)v[start + 3]) == 'e' &&
            mu_lower((unsigned char)v[start + 4]) == 's')
            return 0;                                    /* the files folder is the disc's (modfs) */
        start = i + 1;
    }
    for (size_t e = 0; e < sizeof ends / sizeof ends[0]; e++)
        end_ok |= mu_eq_nocase(mu_ext_of(v), ends[e]);
    return end_ok;
}

/* "<lhs> = <file> | <title> | <artist> [| <album>]" into e (lhs returned in lhs) */
MU_FN int mu_entry(const char *s, char *lhs, size_t ln, bo3_music_entry *e, char *why, size_t wn, const char *what, unsigned k)
{
    char line[400], *eq, *f[5];
    int nf = 0;
    if (!s || strlen(s) >= sizeof line) {
        snprintf(why, wn, "%s entry %u is not a string of at most %u bytes", what, k, (unsigned)sizeof line - 1);
        return 0;
    }
    strcpy(line, s);
    if (!(eq = strchr(line, '='))) {
        snprintf(why, wn, "%s entry %u is not \"<id> = <file> | <title> | <artist> [| <album>]\"", what, k);
        return 0;
    }
    *eq = 0;
    f[nf++] = eq + 1;
    for (char *p = eq + 1; *p; p++)
        if (*p == '|') {
            *p = 0;
            if (nf == 5)
                break;
            f[nf++] = p + 1;
        }
    if (nf < 3 || nf > 4) {
        snprintf(why, wn, "%s entry %u: \"<id> = <file> | <title> | <artist> [| <album>]\" (3 or 4 fields after =)", what, k);
        return 0;
    }
    mu_trim(line);
    for (int i = 0; i < nf; i++)
        mu_trim(f[i]);
    if (strlen(line) >= ln) {
        snprintf(why, wn, "%s entry %u: \"%.40s\" is too long", what, k, line);
        return 0;
    }
    strcpy(lhs, line);
    memset(e, 0, sizeof *e);
    if (!mu_file_ok(f[0])) {
        snprintf(why, wn, "%s entry %u: file \"%.60s\" is not a relative path of plain names (A-Z a-z 0-9 . _ - space; no "
                 ". or .., not in files) ending .wav .mp3 .flac or .ogg, at most %u bytes", what, k, f[0], BO3_MUSIC_FILE_MAX);
        return 0;
    }
    if (!mu_title_ok(f[1])) {
        snprintf(why, wn, "%s entry %u: title \"%.40s\" must be 1..%u printable ASCII characters, no \\ / : * ? \" < > |, no "
                 "space or dot at either end (it is also the file name)", what, k, f[1], BO3_MUSIC_TEXT_MAX);
        return 0;
    }
    if (!mu_text_ok(f[2]) || (nf == 4 && !mu_text_ok(f[3]))) {
        snprintf(why, wn, "%s entry %u: artist and album must be 1..%u printable ASCII characters, no space at either end",
                 what, k, BO3_MUSIC_TEXT_MAX);
        return 0;
    }
    strcpy(e->file, f[0]);
    strcpy(e->title, f[1]);
    strcpy(e->artist, f[2]);
    if (nf == 4)
        strcpy(e->album, f[3]);
    return 1;
}

MU_FN const char *mu_arr_str(recomp_cfg *cfg, const char *key, size_t i)
{
    return recomp_cfg_array_type(cfg, key, i) == RCFG_STRING ? recomp_cfg_array_string(cfg, key, i, NULL) : NULL;
}

MU_FN int mu_parse(const char *text, size_t n, const char *mod_id, bo3_music_decl *out, char *why, size_t wn)
{
    char err[200], *buf;
    recomp_cfg *cfg;
    int ok = 1, any = 0;
    size_t na = 0, nr = 0;
    if (why && wn)
        why[0] = 0;
    memset(out, 0, sizeof *out);
    if (!text || !n)
        return 1;
    if (!mod_id || !mu_mod_id_ok(mod_id)) {
        snprintf(why, wn, "the mod's id is not valid");
        return 0;
    }
    buf = (char *)malloc(n + 1);
    if (!buf) {
        snprintf(why, wn, "no memory");
        return 0;
    }
    memcpy(buf, text, n);
    buf[n] = 0;
    cfg = recomp_cfg_load_string(buf, "mod.toml", err, sizeof err);
    free(buf);
    if (!cfg) {
        snprintf(why, wn, "mod.toml: %s", err);
        return 0;
    }
    for (size_t k = 0; ok && k < recomp_cfg_count(cfg); k++) {
        const char *key = recomp_cfg_key_at(cfg, k);
        if (strncmp(key, MU_PREFIX, 13) != 0 || (key[13] && key[13] != '.'))
            continue;
        any = 1;
        if (strcmp(key, MU_PREFIX ".version") && strcmp(key, MU_PREFIX ".soundtrack") && strcmp(key, MU_PREFIX ".add") &&
            strcmp(key, MU_PREFIX ".replace")) {
            snprintf(why, wn, "%.60s is not a key this build reads ([bmashup.music] version 1: version soundtrack add replace)",
                     key);
            ok = 0;
        }
    }
    if (!any || !ok) {
        recomp_cfg_free(cfg);
        return ok;
    }
    out->present = 1;
    if (recomp_cfg_type_of(cfg, MU_PREFIX ".version") != RCFG_INT || recomp_cfg_int(cfg, MU_PREFIX ".version", 0) != 1) {
        snprintf(why, wn, "bmashup.music.version must be 1");
        ok = 0;
    }
    if (ok && recomp_cfg_type_of(cfg, MU_PREFIX ".add") != RCFG_NONE) {
        if (recomp_cfg_type_of(cfg, MU_PREFIX ".add") != RCFG_ARRAY) {
            snprintf(why, wn, "bmashup.music.add must be a list of strings");
            ok = 0;
        } else {
            na = recomp_cfg_array_len(cfg, MU_PREFIX ".add");
        }
    }
    if (ok && recomp_cfg_type_of(cfg, MU_PREFIX ".replace") != RCFG_NONE) {
        if (recomp_cfg_type_of(cfg, MU_PREFIX ".replace") != RCFG_ARRAY) {
            snprintf(why, wn, "bmashup.music.replace must be a list of strings");
            ok = 0;
        } else {
            nr = recomp_cfg_array_len(cfg, MU_PREFIX ".replace");
        }
    }
#if MUSIC_MUT != 3
    if (ok && na + nr > BO3_MUSIC_MAX_ENTRIES) {
        snprintf(why, wn, "bmashup.music declares %u entries; at most %u (add + replace)", (unsigned)(na + nr),
                 BO3_MUSIC_MAX_ENTRIES);
        ok = 0;
    }
#else
    if (na + nr > BO3_MUSIC_MAX_ENTRIES) {          /* defect: the bound is not refused (the array is still not overrun) */
        if (na > BO3_MUSIC_MAX_ENTRIES)
            na = BO3_MUSIC_MAX_ENTRIES;
        nr = BO3_MUSIC_MAX_ENTRIES - na;
    }
#endif
    if (ok && !na && !nr) {
        snprintf(why, wn, "bmashup.music has no add or replace entry");
        ok = 0;
    }
    if (ok) {
        const char *st = recomp_cfg_type_of(cfg, MU_PREFIX ".soundtrack") == RCFG_STRING ?
                         recomp_cfg_string(cfg, MU_PREFIX ".soundtrack", "") : NULL;
        if (recomp_cfg_type_of(cfg, MU_PREFIX ".soundtrack") != RCFG_NONE && !st) {
            snprintf(why, wn, "bmashup.music.soundtrack must be a string");
            ok = 0;
        } else if (na && !st) {
            snprintf(why, wn, "bmashup.music.soundtrack is missing: the added tracks need a soundtrack name");
            ok = 0;
        } else if (!na && st) {
            snprintf(why, wn, "bmashup.music.soundtrack names a soundtrack, but the mod adds no track");
            ok = 0;
        } else if (st && !mu_title_ok(st)) {
            snprintf(why, wn, "bmashup.music.soundtrack \"%.40s\" must be 1..%u printable ASCII characters, no \\ / : * ? \" < > "
                     "|, no space or dot at either end", st, BO3_MUSIC_TEXT_MAX);
            ok = 0;
        } else if (st) {
            snprintf(out->soundtrack, sizeof out->soundtrack, "%s", st);
        }
    }
    for (size_t k = 0; ok && k < na + nr; k++) {
        int rep = k >= na;
        size_t i = rep ? k - na : k;
        char lhs[BO3_MUSIC_MODID_MAX + 1 + BO3_MUSIC_ID_MAX + 2], *slash;
        bo3_music_entry *e = &out->e[out->n];
        if (!mu_entry(mu_arr_str(cfg, rep ? MU_PREFIX ".replace" : MU_PREFIX ".add", i), lhs, sizeof lhs, e, why, wn,
                   rep ? "bmashup.music.replace" : "bmashup.music.add", (unsigned)i)) {
            ok = 0;
            break;
        }
        e->replace = rep;
        if (!rep) {
            if (!mu_id_ok(lhs, BO3_MUSIC_ID_MAX)) {
                snprintf(why, wn, "bmashup.music.add entry %u: id \"%.30s\" must be 1..%u of a-z 0-9 _ -", (unsigned)i, lhs,
                         BO3_MUSIC_ID_MAX);
                ok = 0;
                break;
            }
            snprintf(e->key, sizeof e->key, "%s/%s", mod_id, lhs);
        } else {
            slash = strchr(lhs, '/');
            if (!slash || (*slash = 0, !mu_mod_id_ok(lhs)) || !mu_id_ok(slash + 1, BO3_MUSIC_ID_MAX)) {
                snprintf(why, wn, "bmashup.music.replace entry %u: the track must be named \"<mod id>/<id>\"", (unsigned)i);
                ok = 0;
                break;
            }
            if (!strcmp(lhs, mod_id)) {
                snprintf(why, wn, "bmashup.music.replace entry %u: a mod does not replace its own track (%s/%s)", (unsigned)i, lhs,
                         slash + 1);
                ok = 0;
                break;
            }
            snprintf(e->key, sizeof e->key, "%s/%s", lhs, slash + 1);
        }
        for (uint32_t j = 0; ok && j < out->n; j++) {
            if (!strcmp(out->e[j].key, e->key)) {
                snprintf(why, wn, "bmashup.music: %s is declared twice", e->key);
                ok = 0;
            } else if (!rep && !out->e[j].replace && mu_eq_nocase(out->e[j].title, e->title)) {
                snprintf(why, wn, "bmashup.music.add: two tracks have the title \"%s\" (a soundtrack's titles are its file names)",
                         e->title);
                ok = 0;
            }
        }
        if (ok)
            out->n++;
    }
    recomp_cfg_free(cfg);
    if (!ok)
        memset(out, 0, sizeof *out), out->present = 1;
    return ok;
}

MU_FN int mu_replace_listed(const char *key, const char *const *ids, int nids)
{
    const char *slash = key ? strchr(key, '/') : NULL;
    if (!slash)
        return 0;
    for (int i = 0; i < nids; i++)
        if (ids[i] && strlen(ids[i]) == (size_t)(slash - key) && !strncmp(ids[i], key, (size_t)(slash - key)))
            return 1;
    return 0;
}

