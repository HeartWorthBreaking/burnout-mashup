"""isolation_ops.py - the launcher's in-process mod operations, run by test_isolation.py under audited.py.

    py -3 -B audited.py isolation_ops.py BUNDLE_ROOT SOURCE_MOD_FOLDER SOURCE_MOD_ZIP

prepare the mod list, preview / import (folder and zip, with replace), list, stale-profile check, results, turn a mod off and on.
Prints one JSON object (what the operations returned). It never writes anything outside the bundle."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pubfix  # noqa: E402,F401  (only to find the launcher; the sandboxed environment is set by the caller)
sys.path.insert(0, os.path.join(pubfix.SRC, "tools", "launcher"))
import bmmods  # noqa: E402


def main():
    root, folder, zpath = sys.argv[1:4]
    b = bmmods.Bundle(root)
    out = {"approvals_path": b.approvals, "settings_dir": b.settings_dir}
    out["preview_folder"] = b.preview(folder)
    out["preview_zip"] = b.preview(zpath)
    out["import_folder"] = os.path.relpath(b.import_mod(folder), root)
    out["import_zip_replace"] = os.path.relpath(b.import_mod(zpath, replace=True), root)
    out["mods"] = [{k: r.get(k) for k in ("id", "level", "enabled", "native_code", "source")} for r in b.mods()]
    out["stale"] = b.stale()
    out["results"] = b.results()
    out["off"] = b.set_enabled("a.plug", False)
    out["on"] = b.set_enabled("a.plug", True)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
