/* wbstart.c - "Burnout Mashup Workbench.exe": the starter of the Burnout Mashup Workbench (Windows; no console window).
 *
 * Layout 2 (the Windows package, 0.2.0): this exe sits in the install folder beside "Burnout Mashup.exe", gamedata\ and app\.
 * It opens the Workbench window (app\workbench\workbench.py) with Python 3.11+ - the Python launcher pyw.exe ("pyw -3"), else
 * pythonw.exe on PATH. Files or folders dropped onto the exe are passed on as arguments. If an update or a migration was
 * interrupted (app\.update\JOURNAL.json exists), it first runs app\.update\bmapply.py recover, which finishes or undoes that
 * change and then opens the Workbench. The working folder is the install folder. Without Python a normal Windows message says what
 * to install. Same code as bmstart.c (the launcher's starter) except the target and the texts.
 * Test hooks: BMASHUP_PYW = the full path of a pythonw stand-in (used instead of the search); BMASHUP_NO_DIALOG = 1 returns the
 * exit code without showing a message box. Built by build_wbexe.py (llvm-mingw, deterministic, no timestamp); source in the tree. */
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
#define TITLE L"Burnout Mashup Workbench"
#define SCRIPT L"\\app\\workbench\\workbench.py"
#define THEN L"workbench"

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

static int no_dialog(void)
{
    wchar_t v[8];
    return GetEnvironmentVariableW(L"BMASHUP_NO_DIALOG", v, 8) > 0;
}

static int exists(const wchar_t *p)
{
    return GetFileAttributesW(p) != INVALID_FILE_ATTRIBUTES;
}

static int find_exe(const wchar_t *name, wchar_t *out, DWORD cap)
{
    return SearchPathW(NULL, name, NULL, cap, out, NULL) > 0;
}

int WINAPI wWinMain(HINSTANCE h, HINSTANCE prev, PWSTR cmdline, int show)
{
    static wchar_t self[MAX_PATH], dir[MAX_PATH], script[MAX_PATH], journal[MAX_PATH], helper[MAX_PATH], py[MAX_PATH],
        cmd[CMD_MAX], env[MAX_PATH];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    int argc = 0, use_py_launcher = 0, recover = 0;
    LPWSTR *argv;
    wchar_t *slash;
    (void)h; (void)prev; (void)cmdline; (void)show;

    GetModuleFileNameW(NULL, self, MAX_PATH);
    wcscpy(dir, self);
    slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = 0;
    wcscpy(script, dir);
    append(script, MAX_PATH, SCRIPT);
    wcscpy(journal, dir);
    append(journal, MAX_PATH, L"\\app\\.update\\JOURNAL.json");
    wcscpy(helper, dir);
    append(helper, MAX_PATH, L"\\app\\.update\\bmapply.py");
    recover = exists(journal) && exists(helper);
    if (!recover && !exists(script)) {
        if (!no_dialog())
            MessageBoxW(NULL, L"The program folder \"app\" is missing or incomplete beside Burnout Mashup Workbench.exe.\n\n"
                        L"Unpack the whole Burnout Mashup package (both exes, the gamedata folder and the app folder) into one "
                        L"folder and start Burnout Mashup Workbench.exe from there.", TITLE, MB_ICONERROR | MB_OK);
        return 2;
    }
    if (GetEnvironmentVariableW(L"BMASHUP_PYW", env, MAX_PATH) > 0 && exists(env)) {
        wcscpy(py, env);
    } else if (find_exe(L"pyw.exe", py, MAX_PATH)) {
        use_py_launcher = 1;
    } else if (!find_exe(L"pythonw.exe", py, MAX_PATH)) {
        int r = no_dialog() ? IDNO :
                MessageBoxW(NULL, L"The Burnout Mashup Workbench needs Python 3.11 or newer (free, from python.org).\n\n"
                            L"Install it with \"Add python.exe to PATH\" ticked, then start Burnout Mashup Workbench.exe again.\n\n"
                            L"Open the Python download page now?", TITLE, MB_ICONINFORMATION | MB_YESNO);
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
    if (recover) {
        /* an interrupted update / migration: finish or undo it first, then the window opens (bmapply.py --then) */
        append_arg(cmd, CMD_MAX, helper);
        append_arg(cmd, CMD_MAX, L"recover");
        append_arg(cmd, CMD_MAX, L"--root");
        append_arg(cmd, CMD_MAX, dir);
        append_arg(cmd, CMD_MAX, L"--then");
        append_arg(cmd, CMD_MAX, THEN);
    } else {
        append_arg(cmd, CMD_MAX, script);
        argv = CommandLineToArgvW(GetCommandLineW(), &argc);
        for (int i = 1; argv && i < argc; i++)
            append_arg(cmd, CMD_MAX, argv[i]);         /* dropped files / folders */
        if (argv)
            LocalFree(argv);
    }
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        if (!no_dialog())
            MessageBoxW(NULL, L"Python was found but could not be started. Reinstall Python 3.11+ from python.org.", TITLE,
                        MB_ICONERROR | MB_OK);
        return 3;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
