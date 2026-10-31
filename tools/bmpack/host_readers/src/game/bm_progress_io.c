/* bm_progress_io.c - the native filesystem for bm_progress (bm_progress.h). Win32: built and tested. POSIX: written to the
 * same contract (fsync of the file, rename then fsync of the directory, flock), NOT built or tested yet. */
#include "bm_progress.h"

#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>

static int wide(const char *s, wchar_t *w, int cap)
{
    return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, cap) > 0;
}

static int w_read(void *ctx, const char *path, size_t max, uint8_t **buf, size_t *n)
{
    wchar_t w[1200];
    HANDLE h;
    LARGE_INTEGER sz;
    DWORD got = 0;
    (void)ctx;
    *buf = NULL;
    *n = 0;
    if (!wide(path, w, 1200))
        return -1;
    h = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        DWORD e = GetLastError();
        return e == ERROR_FILE_NOT_FOUND || e == ERROR_PATH_NOT_FOUND ? 0 : -1;
    }
    if (!GetFileSizeEx(h, &sz) || sz.QuadPart < 0 || (unsigned long long)sz.QuadPart > max) {
        CloseHandle(h);
        return -1;
    }
    *buf = (uint8_t *)malloc((size_t)sz.QuadPart + 1);
    if (!*buf || (sz.QuadPart && (!ReadFile(h, *buf, (DWORD)sz.QuadPart, &got, NULL) || got != (DWORD)sz.QuadPart))) {
        free(*buf);
        *buf = NULL;
        CloseHandle(h);
        return -1;
    }
    CloseHandle(h);
    *n = (size_t)sz.QuadPart;
    return 1;
}

static void *w_create(void *ctx, const char *path)
{
    wchar_t w[1200];
    HANDLE h;
    (void)ctx;
    if (!wide(path, w, 1200))
        return NULL;
    h = CreateFileW(w, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    return h == INVALID_HANDLE_VALUE ? NULL : (void *)h;
}

static int w_write(void *ctx, void *h, const void *p, size_t n)
{
    DWORD put = 0;
    (void)ctx;
    return n > 0x7FFFFFFF || !WriteFile((HANDLE)h, p, (DWORD)n, &put, NULL) || put != (DWORD)n ? -1 : 0;
}

static int w_flush(void *ctx, void *h) { (void)ctx; return FlushFileBuffers((HANDLE)h) ? 0 : -1; }
static int w_close(void *ctx, void *h) { (void)ctx; return CloseHandle((HANDLE)h) ? 0 : -1; }

static int w_rename(void *ctx, const char *from, const char *to)
{
    wchar_t a[1200], b[1200];
    (void)ctx;
    if (!wide(from, a, 1200) || !wide(to, b, 1200))
        return -1;
    return MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) ? 0 : -1;
}

static int w_remove(void *ctx, const char *path)
{
    wchar_t w[1200];
    (void)ctx;
    if (!wide(path, w, 1200))
        return -1;
    return DeleteFileW(w) || GetLastError() == ERROR_FILE_NOT_FOUND ? 0 : -1;
}

static int w_exists(void *ctx, const char *path)
{
    wchar_t w[1200];
    (void)ctx;
    return wide(path, w, 1200) && GetFileAttributesW(w) != INVALID_FILE_ATTRIBUTES;
}

/* exclusive (no sharing) and deleted on close: a second opener gets a sharing violation; the OS closes it when the
 * process ends, so a crashed writer leaves no stale lock */
static void *w_lock(void *ctx, const char *path)
{
    wchar_t w[1200];
    HANDLE h;
    (void)ctx;
    if (!wide(path, w, 1200))
        return NULL;
    h = CreateFileW(w, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_DELETE_ON_CLOSE, NULL);
    return h == INVALID_HANDLE_VALUE ? NULL : (void *)h;
}

static void w_unlock(void *ctx, void *lk) { (void)ctx; CloseHandle((HANDLE)lk); }

static const bm_prog_io k_io = {NULL, w_read, w_create, w_write, w_flush, w_close, w_rename, w_remove, w_exists, w_lock, w_unlock};

#else /* POSIX: untested */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static int x_read(void *ctx, const char *path, size_t max, uint8_t **buf, size_t *n)
{
    struct stat st;
    int fd = open(path, O_RDONLY);
    ssize_t got;
    (void)ctx;
    *buf = NULL;
    *n = 0;
    if (fd < 0)
        return errno == ENOENT ? 0 : -1;
    if (fstat(fd, &st) || st.st_size < 0 || (size_t)st.st_size > max || !(*buf = (uint8_t *)malloc((size_t)st.st_size + 1))) {
        close(fd);
        return -1;
    }
    got = read(fd, *buf, (size_t)st.st_size);
    close(fd);
    if (got != st.st_size) {
        free(*buf);
        *buf = NULL;
        return -1;
    }
    *n = (size_t)got;
    return 1;
}

static void *x_create(void *ctx, const char *path)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    (void)ctx;
    return fd < 0 ? NULL : (void *)(intptr_t)(fd + 1);
}
static int x_write(void *ctx, void *h, const void *p, size_t n) { (void)ctx; return write((int)(intptr_t)h - 1, p, n) == (ssize_t)n ? 0 : -1; }
static int x_flush(void *ctx, void *h) { (void)ctx; return fsync((int)(intptr_t)h - 1); }
static int x_close(void *ctx, void *h) { (void)ctx; return close((int)(intptr_t)h - 1); }

static int x_rename(void *ctx, const char *from, const char *to)
{
    char dir[1200];
    char *sl;
    int fd, rc;
    (void)ctx;
    if (rename(from, to))
        return -1;
    snprintf(dir, sizeof dir, "%s", to);
    sl = strrchr(dir, '/');
    if (sl)
        *sl = 0;
    fd = open(sl ? dir : ".", O_RDONLY);
    rc = fd >= 0 && fsync(fd) == 0 ? 0 : -1;   /* the rename is durable once the directory is */
    if (fd >= 0)
        close(fd);
    return rc;
}
static int x_remove(void *ctx, const char *path) { (void)ctx; return unlink(path) == 0 || errno == ENOENT ? 0 : -1; }
static int x_exists(void *ctx, const char *path) { struct stat st; (void)ctx; return stat(path, &st) == 0; }
static void *x_lock(void *ctx, const char *path)
{
    int fd = open(path, O_RDWR | O_CREAT, 0644);
    (void)ctx;
    if (fd < 0)
        return NULL;
    if (flock(fd, LOCK_EX | LOCK_NB)) {
        close(fd);
        return NULL;
    }
    return (void *)(intptr_t)(fd + 1);
}
static void x_unlock(void *ctx, void *lk) { (void)ctx; close((int)(intptr_t)lk - 1); }

static const bm_prog_io k_io = {NULL, x_read, x_create, x_write, x_flush, x_close, x_rename, x_remove, x_exists, x_lock, x_unlock};
#endif

const bm_prog_io *bm_prog_io_native(void)
{
    return &k_io;
}
