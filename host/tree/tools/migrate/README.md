# tools/migrate - copy Takedawn saves to Burnout Mashup (explicit, optional, reversible)

Burnout Mashup uses its own folders and never touches Takedawn's:

| | Takedawn (never changed) | Burnout Mashup |
|---|---|---|
| saves, settings, mod list, plugin approvals, logs, crash | `%APPDATA%\Takedawn` | `%APPDATA%\BurnoutMashup` |
| game data root, data-folder.txt, shader cache | `%LOCALAPPDATA%\Takedawn` | `%LOCALAPPDATA%\BurnoutMashup` |

Nothing moves on its own. To bring saves over, with both games closed:

    py -3 bmashup_migrate.py plan                 what would be copied (sizes, sha256); nothing written
    py -3 bmashup_migrate.py apply                copy into the empty Burnout Mashup folder + a manifest
    py -3 bmashup_migrate.py revert --manifest "%APPDATA%\BurnoutMashup\migrate-manifest-<stamp>.json"

`--no-approvals` leaves `plugin-approvals.toml` out; `--game-data` makes Burnout Mashup use the existing Takedawn game data
(writes `%LOCALAPPDATA%\BurnoutMashup\data-folder.txt`, read only, no copy); `--from burnout3` copies from the port's earlier
`%APPDATA%\Burnout3` folder. Copy only, never move, never overwrite; revert deletes only the files it copied that are unchanged.
Full guide: the pfid1 MIGRATION_GUIDE.md.
