/* bmstart.c - "Burnout Mashup.exe": the friendly starter of the Burnout Mashup launcher (Windows; no console window).
 *
 * It opens the launcher window (tools\launcher\bmlauncher.pyw beside this exe) with Python 3.11+ - the Python launcher pyw.exe
 * ("pyw -3"), else pythonw.exe on PATH. Files or folders dropped onto the exe are passed on (game data, a mod folder / .zip),
 * exactly like dropping them onto "Burnout Mashup.cmd". Without Python a normal Windows message says what to install.
 * Test hook: BMASHUP_PYW = the full path of a pythonw stand-in (used instead of the search).
 * Built by build_exe.py (llvm-mingw, deterministic, no timestamp); source shipped with the bundle. */
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

#define CMD_MAX 32768

static void append(wchar_t *dst, size_t cap, const wchar_t *s)
{
    size_t n = wcslen(dst);
    while (*s && n + 1 < cap)
        dst[n++] = *s++;
    dst[n] = 0;
}

/* Windows command-line quoting of one argument (backslashes before a quote doubled; the whole argument in quotes) */
static void append_arg(wchar_t *dst, size_t cap, const wchar_t *a)
{
    size_t n = wcslen(dst);
    if (n + 2 >= cap)
        return;
    dst[n++] = L' ';
    dst[n++] = L'"';
    for (const wchar_t *p = a; *p && n + 4 < cap; p++) {
        size_t bs = 0;
        while (*p == L'\\') {
            bs++;
            p++;
        }
        if (!*p) {
            for (size_t k = 0; k < 2 * bs && n + 2 < cap; k++)
                dst[n++] = L'\\';
            break;
        }
        if (*p == L'"') {
            for (size_t k = 0; k < 2 * bs + 1 && n + 3 < cap; k++)
                dst[n++] = L'\\';
        } else {
            for (size_t k = 0; k < bs && n + 2 < cap; k++)
                dst[n++] = L'\\';
        }
        dst[n++] = *p;
    }
    if (n + 1 < cap)
        dst[n++] = L'"';
    dst[n] = 0;
}

static int find_exe(const wchar_t *name, wchar_t *out, DWORD cap)
{
    return SearchPathW(NULL, name, NULL, cap, out, NULL) > 0;
}

int WINAPI wWinMain(HINSTANCE h, HINSTANCE prev, PWSTR cmdline, int show)
{
    static wchar_t self[MAX_PATH], dir[MAX_PATH], script[MAX_PATH], py[MAX_PATH], cmd[CMD_MAX], env[MAX_PATH];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    int argc = 0, use_py_launcher = 0;
    LPWSTR *argv;
    wchar_t *slash;
    (void)h; (void)prev; (void)cmdline; (void)show;

    GetModuleFileNameW(NULL, self, MAX_PATH);
    wcscpy(dir, self);
    slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = 0;
    wcscpy(script, dir);
    append(script, MAX_PATH, L"\\tools\\launcher\\bmlauncher.pyw");
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"The launcher files are missing (tools\\launcher\\bmlauncher.pyw).\n\n"
                    L"Unpack the whole Burnout Mashup package again and start Burnout Mashup.exe from its folder.",
                    L"Burnout Mashup", MB_ICONERROR | MB_OK);
        return 2;
    }
    if (GetEnvironmentVariableW(L"BMASHUP_PYW", env, MAX_PATH) > 0 && GetFileAttributesW(env) != INVALID_FILE_ATTRIBUTES) {
        wcscpy(py, env);
    } else if (find_exe(L"pyw.exe", py, MAX_PATH)) {
        use_py_launcher = 1;
    } else if (!find_exe(L"pythonw.exe", py, MAX_PATH)) {
        int r = MessageBoxW(NULL, L"Burnout Mashup needs Python 3.11 or newer (free, from python.org).\n\n"
                            L"Install it with \"Add python.exe to PATH\" ticked, then start Burnout Mashup.exe again.\n\n"
                            L"Open the Python download page now?", L"Burnout Mashup", MB_ICONINFORMATION | MB_YESNO);
        if (r == IDYES)
            ShellExecuteW(NULL, L"open", L"https://www.python.org/downloads/", NULL, NULL, SW_SHOWNORMAL);
        return 9;
    }
    cmd[0] = 0;
    append(cmd, CMD_MAX, L"\"");
    append(cmd, CMD_MAX, py);
    append(cmd, CMD_MAX, L"\"");
    if (use_py_launcher)
        append(cmd, CMD_MAX, L" -3");
    append_arg(cmd, CMD_MAX, script);
    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    for (int i = 1; argv && i < argc; i++)
        append_arg(cmd, CMD_MAX, argv[i]);         /* dropped files / folders */
    if (argv)
        LocalFree(argv);
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Python was found but could not be started. Reinstall Python 3.11+ from python.org.",
                    L"Burnout Mashup", MB_ICONERROR | MB_OK);
        return 3;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
