"""build_wbexe.py - builds "Burnout Mashup Workbench.exe" (the Workbench starter, wbstart.c; it sits in the mod kit folder and
starts workbench\\workbench.py) with llvm-mingw, deterministic (no timestamp, stripped), with the Burnout Mashup icon
(host/tree/assets/icon/bmashup.ico). Adapted from the tester launcher's build_exe.py.

    py -3 -B build_wbexe.py OUT.exe --cc PATH_TO\\x86_64-w64-mingw32-clang.exe   (default: llvm-mingw on PATH)

Writes OUT.exe and prints its sha256. Two builds of the same source give the same bytes (tests\\test_wbexe.py)."""
import hashlib
import os
import subprocess
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_CC = "x86_64-w64-mingw32-clang.exe"         # llvm-mingw on PATH, or --cc FULL_PATH
# the program icon: host/tree/assets/icon/bmashup.ico, the same picture as the host's (a rendered picture, no font and no game art)
ICO = os.path.normpath(os.path.join(HERE, "..", "..", "host", "tree", "assets", "icon", "bmashup.ico"))


def main():
    out = os.path.abspath(sys.argv[1])
    cc = sys.argv[sys.argv.index("--cc") + 1] if "--cc" in sys.argv else DEF_CC
    if not os.path.isabs(cc):
        cc = shutil.which(cc) or cc
    windres = os.path.join(os.path.dirname(cc), "llvm-windres.exe")
    with tempfile.TemporaryDirectory(prefix="wbstart_") as t:
        icof = os.path.join(t, "wb.ico")
        shutil.copyfile(ICO, icof)
        rc = os.path.join(t, "wbstart.rc")
        open(rc, "w", encoding="ascii").write(
            '1 ICON "wb.ico"\n'
            '1 VERSIONINFO FILEVERSION 1,2,0,0 PRODUCTVERSION 1,2,0,0\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n'
            '  BLOCK "040904B0"\n  BEGIN\n   VALUE "FileDescription", "Burnout Mashup Workbench starter"\n'
            '   VALUE "ProductName", "Burnout Mashup Workbench"\n   VALUE "FileVersion", "1.2.0"\n   VALUE "OriginalFilename", '
            '"Burnout Mashup Workbench.exe"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
        res = os.path.join(t, "wbstart.res.o")
        subprocess.run([windres, rc, "-O", "coff", "-o", res], check=True, cwd=t)
        subprocess.run([cc, "-O2", "-municode", "-mwindows", "-s", "-Wall", "-Wextra", "-Werror", "-Wl,--no-insert-timestamp",
                        "-ffile-prefix-map=%s=." % HERE, os.path.join(HERE, "wbstart.c"), res, "-o", out,
                        "-lshell32"], check=True)
    print("built %s sha256 %s" % (out, hashlib.sha256(open(out, "rb").read()).hexdigest()))


if __name__ == "__main__":
    main()
