"""wb_capacity - RTA5 (2026-11-02): the Workbench / track editor view of the kit's capacity table (trackbuild 0.3.4
trackbuild.capacity: the game's default sizes, the Burnout Mashup host's ceilings, the mod.toml [bmashup.capacity] keys).

Nothing here hard-codes a limit: the numbers come from the bound kit's trackbuild.capacity (hash-checked with the other kit
modules by wb_trackedit.kit_trackbuild). A kit without trackbuild.capacity (trackbuild <= 0.3.3) is treated as capacity
"game" with the game's defaults (the 0.3.3 slots read from its build module).

Project setting: the track description's "capacity" key ("auto" = default: declare what the track needs, up to the host's
ceilings; "game" = refuse above the game's defaults, for hosts without capacity declarations). The editor sets it with the
Streaming settings tool (wb_te_author.streaming_settings capacity=...)."""

FALLBACK_GAME = {'full_unit_bytes': 0x28000, 'low_unit_bytes': 0x18000, 'static_bytes': 0xD00000, 'gamedata_bytes': 0x176000,
                 'lanes': 64}


def cap_module(K):
    """the kit's trackbuild.capacity (or None for a 0.3.3 kit)"""
    return (K or {}).get('capacity')


def mode_of(K, d):
    C = cap_module(K)
    if C is None:
        return 'game'
    m = (d or {}).get('capacity', C.DEFAULT_MODE)
    return m if m in C.MODES else C.DEFAULT_MODE


def limits(K, mode):
    """{key: {'game', 'ceiling', 'limit'}} for the mode"""
    C = cap_module(K)
    out = {}
    for k, g in FALLBACK_GAME.items():
        t = C.TABLE[k] if C else {'game': g, 'ceiling': g}
        out[k] = {'game': t['game'], 'ceiling': t['ceiling'], 'limit': t['ceiling'] if mode == 'auto' else t['game']}
    return out


def unit_rows(K, unit_infos, d):
    """the kit's per-unit build info -> the editor's capacity rows. mesh_slot_pct / lod_slot_pct stay relative to the GAME's
    default slot (as before); *_limit_pct are relative to the effective limit (auto: the host ceiling); *_state is ok |
    declared (above the game, within the host ceiling: mod.toml declares it) | over; notes explain each non-ok value."""
    mode = mode_of(K, d)
    L = limits(K, mode)
    C = cap_module(K)
    rows = []
    for x in unit_infos:
        r = {'unit': x['unit'], 'vertices': x['vertices'], 'records': x['records'], 'mesh_bytes': x['mesh_bytes'],
             'lod_bytes': x['lod_bytes'],
             'mesh_slot_pct': round(100.0 * x['mesh_bytes'] / L['full_unit_bytes']['game'], 1),
             'lod_slot_pct': round(100.0 * x['lod_bytes'] / L['low_unit_bytes']['game'], 1),
             'vertex_pct': round(100.0 * x['vertices'] / 65536, 1), 'record_pct': round(100.0 * x['records'] / 127, 1),
             'mesh_limit_pct': round(100.0 * x['mesh_bytes'] / L['full_unit_bytes']['limit'], 1),
             'lod_limit_pct': round(100.0 * x['lod_bytes'] / L['low_unit_bytes']['limit'], 1)}
        notes = []
        for key, f, tag, word in (('full_unit_bytes', 'mesh_bytes', 'mesh', 'mesh'), ('low_unit_bytes', 'lod_bytes', 'lod', 'LOD')):
            v = x[f]
            st = 'ok' if v <= L[key]['game'] else ('over' if v > L[key]['limit'] else 'declared')
            r[tag + '_state'] = st
            if st != 'ok':
                notes.append(C.explain(key, v, 'unit %d %s' % (x['unit'], word), mode) if C else
                             'unit %d %s 0x%X - above the slot 0x%X' % (x['unit'], word, v, L[key]['game']))
        if notes:
            r['capacity_notes'] = notes
        rows.append(r)
    return rows


def regen_extra(K, rows, d):
    """the regenerate() additions: mode, limits, info lines (declared blocks), the declaration the unit blocks need"""
    mode = mode_of(K, d)
    L = limits(K, mode)
    C = cap_module(K)
    info = [n for r in rows for n in r.get('capacity_notes', []) if r['mesh_state'] == 'declared' or r['lod_state'] == 'declared']
    need = {}
    if rows:
        need = {'full_unit_bytes': max(r['mesh_bytes'] for r in rows), 'low_unit_bytes': max(r['lod_bytes'] for r in rows)}
    decl, req = {}, []
    if C and mode == 'auto':
        n2 = {k: C.page(v) for k, v in need.items()}
        decl = {k: v for k, v in n2.items() if v > C.TABLE[k]['game'] and v <= C.TABLE[k]['ceiling']}
        req, _overall = C.requires(decl)
    return {'capacity_mode': mode,
            'capacity_limits': {'mesh': L['full_unit_bytes'], 'lod': L['low_unit_bytes']},
            'capacity_info': info,
            'capacity_declare': {k: ('0x%X' % v) for k, v in decl.items()}, 'capacity_requires': req,
            'capacity_worst_limit_pct': max((max(r['mesh_limit_pct'], r['lod_limit_pct'], r['vertex_pct'], r['record_pct'])
                                             for r in rows), default=0)}


def limit_rows(K, d):
    """streaming report LIMITS rows for the host-capacity limits, from the kit table"""
    C = cap_module(K)
    mode = mode_of(K, d)
    out = []
    names = {'full_unit_bytes': 'mesh block per unit', 'low_unit_bytes': 'LOD block per unit', 'static_bytes': 'static.dat',
             'gamedata_bytes': 'Gamedata need', 'lanes': 'AI route lanes'}
    for k in ('full_unit_bytes', 'low_unit_bytes', 'static_bytes', 'gamedata_bytes', 'lanes'):
        if C is None:
            g = FALLBACK_GAME[k]
            out.append((names[k], ('%d' % g) if k == 'lanes' else '0x%X bytes' % g, 'HOST ceiling (game default)',
                        'kit build.py (trackbuild <= 0.3.3, no capacity table)', 'a kit with trackbuild 0.3.4+ (capacity auto)'))
            continue
        t = C.TABLE[k]
        tiers = '; '.join('<= %s: %s' % (C.fmt(k, top), host) for top, host in t['tiers'])
        out.append((names[k], 'game %s, host ceiling %s (capacity %s: limit %s)' % (
            C.fmt(k, t['game']), C.fmt(k, t['ceiling']), mode, C.fmt(k, t['ceiling'] if mode == 'auto' else t['game'])),
            'HOST ceiling (declared capacity)', 'kit trackbuild.capacity TABLE (main21 host %s); validate.py V6_budgets' % k,
            'capacity auto declares mod.toml [bmashup.capacity] %s; %s' % (k, tiers)))
    if C is not None and hasattr(C, 'RECORDS'):
        R = C.RECORDS
        out.append(('records per block (capacity)', '%d (%d with host patch 132; block flag BMRC)' % (R['enforced'], R['host_planned']),
                    'HOST ceiling (info)', 'kit trackbuild.capacity RECORDS',
                    '127 stays enforced: trackbuild 0.3.4 writes no BMRC flag (writer + validators are s8)'))
    if C is not None and hasattr(C, 'ROWS'):
        R = C.ROWS
        n = len((d or {}).get('rows') or [])
        out.append(('material rows per centre block', 'game %d, host %d with the BMRX row extension (this track: %s)' % (
            R['game'], R['ceiling'], C.rows_note(n)), 'HOST ceiling (row extension, info)',
            'kit trackbuild.capacity ROWS (host bm_rowx.c; Workbench tools\\wm_rowx.py)',
            'trackbuild writes no row extension: 83 in every capacity mode; the host reads up to %d rows (%s)' % (R['ceiling'], R['host'])))
    return out
