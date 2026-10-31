# Vendored code, provenance and licences (trackbuild 0.2.0)

trackbuild 0.1.6 imported its independent readers / writers from the developer workspace through `sys.path`. 0.2.0 carries
copies of exactly the modules it uses in `trackbuild\_vendor` and imports them package-relative. **All vendored code is
Burnout Mashup project code** (same owner and licence as trackbuild itself); there is **no third-party code** and no
generated game code. Per-file source path (workspace-relative), source sha256, vendored sha256 and every edit:
`trackbuild\_vendor\VENDOR.json` (`tb.py selfcheck` verifies the vendored hashes).

| Vendored | From (project module) | Used for | Edits |
|---|---|---|---|
| `bolib\` (collision, gtid, lanes, routes, traffic) | PS2 project `tools\bolib` | collision tree parse / check, base-40 IDs, traffic S2 / S3 build checks | `__init__`: workspace folder constants set to None |
| `xbmesh.py`, `xbtopo.py` | CUSTOM-TRACK-1 readers | V1 layout identity, mesh decode, winding | retail / output folder constants removed; sys.path -> relative imports |
| `ct2_s4.py`, `ct2_route.py`, `ct2_gamedata.py` | CUSTOM-TRACK-2 route / Gamedata models | S4 route model + writer, Gamedata model / check | retail folder constant removed; sys.path -> relative import |
| `trackconv\` (common, b3static, streamed, package) | gp tools trackconv 0.1.0 | strict STATIC writer / parser, streamed strict rules, packaging | `deps` (workspace discovery) replaced by the vendored bolib / bmpack_min |
| `bmpack_min.py` | host3 tools bmpack 1.2 (functions copied verbatim) | base-40 IDs, Gamedata rename rule, manifest verify | only the pure-Python functions; the compiled host-reader checker is not vendored (use `--bmpack`) |
| `ctnav_min.py` | tools ctnav camera / grid + the route geometry class of the steering model (verbatim) | V5 camera / planner hazards, start-grid search model | functions extracted; the geometry class renamed `_Geo` |

Comment / docstring sanitising: references to generated-code file names and absolute workspace paths in comments were
replaced by `<generated code>` / `<workspace>` (counted per file in VENDOR.json); no code line changed by it.
Research-only entry points of the copied modules that read a retail folder (identity surveys, probes) are inert in the
vendored copies (their folder constant is None); trackbuild never calls them.

Game data: none is included. The donor files are read at build time from the user's own `--game-data` folder and copied
into the user's own output (local only).
