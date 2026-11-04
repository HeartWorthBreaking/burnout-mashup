"""build_exe.py - builds "Burnout Mashup.exe" (the launcher starter, bmstart.c) with llvm-mingw, deterministic (no timestamp,
stripped), with the Burnout Mashup icon (host/tree/assets/icon/bmashup.ico).

    py -3 -B build_exe.py OUT.exe [--cc PATH_TO x86_64-w64-mingw32-clang.exe]   (default: llvm-mingw on PATH)

Writes OUT.exe and prints its sha256. Two builds of the same source give the same bytes (checked by tests\\test_exe.py)."""
import hashlib
import os
import subprocess
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_CC = "x86_64-w64-mingw32-clang.exe"         # llvm-mingw on PATH, or --cc FULL_PATH
# the program icon: host/tree/assets/icon/bmashup.ico, the same picture as the host's (a rendered picture, no font and no game art)
ICO = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "host", "tree", "assets", "icon", "bmashup.ico"))


def main():
    out = os.path.abspath(sys.argv[1])
    cc = sys.argv[sys.argv.index("--cc") + 1] if "--cc" in sys.argv else DEF_CC
    if not os.path.isabs(cc):
        cc = shutil.which(cc) or cc
    windres = os.path.join(os.path.dirname(cc), "llvm-windres.exe")
    with tempfile.TemporaryDirectory(prefix="bmstart_") as t:
        icof = os.path.join(t, "bm.ico")
        shutil.copyfile(ICO, icof)
        rc = os.path.join(t, "bmstart.rc")
        open(rc, "w", encoding="ascii").write(
            '1 ICON "bm.ico"\n'
            '1 VERSIONINFO FILEVERSION 1,2,0,0 PRODUCTVERSION 1,2,0,0\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n'
            '  BLOCK "040904B0"\n  BEGIN\n   VALUE "FileDescription", "Burnout Mashup launcher"\n'
            '   VALUE "ProductName", "Burnout Mashup"\n   VALUE "FileVersion", "1.2.0"\n   VALUE "OriginalFilename", '
            '"Burnout Mashup.exe"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
        res = os.path.join(t, "bmstart.res.o")
        subprocess.run([windres, rc, "-O", "coff", "-o", res], check=True, cwd=t)
        subprocess.run([cc, "-O2", "-municode", "-mwindows", "-s", "-Wall", "-Wextra", "-Werror", "-Wl,--no-insert-timestamp",
                        "-ffile-prefix-map=%s=." % HERE, os.path.join(HERE, "bmstart.c"), res, "-o", out,
                        "-lshell32"], check=True)
    print("built %s sha256 %s" % (out, hashlib.sha256(open(out, "rb").read()).hexdigest()))


if __name__ == "__main__":
    main()
