// ---------------------------------------------------------------- rta: Retail-style authoring panel (Workbench 0.33 retail-style authoring, 2026-11-02)
const RTA = {job: null, pv: null, pts: [], ctr: [-6000, 20, -6000], ax: null};
const rL = (r, op) => (r.summary_lines || []).join('\n') || (r.ok ? 'ok' : 'REFUSED (nothing changed): ' + r.error);
async function rtaOp(body) { return api('/api/layout', body); }
function rtaOut(id, txt, cls) { const o = $(id); o.style.display = 'block'; o.textContent = txt; o.className = 'note ' + (cls || ''); }
async function rtaWait(r, outId) {          // poll a background job: progress bar, message, cancel button
  if (!r.ok) { rtaOut(outId, 'REFUSED (nothing changed): ' + r.error, 'bad'); return null; }
  RTA.job = r.job; $('rtacatx').disabled = false;
  for (;;) {
    const s = await rtaOp({op: 'rta_job_status', job: r.job, wait: 2});
    $('rtaprog').value = s.progress || 0; $('rtajobmsg').textContent = `${s.kind}: ${s.message || ''}`;
    if (s.job_state !== 'running') { $('rtacatx').disabled = true; RTA.job = null;
      if (s.job_state !== 'done') { rtaOut(outId, `${s.job_state.toUpperCase()} (nothing changed): ${s.error}`, 'bad'); return null; }
      $('rtajobmsg').textContent = `${s.kind}: done in ${s.seconds} s`; return s; }
  }
}
async function rtaCatStatus() {
  const r = await rtaOp({op: 'rta_catalogue_status'}); if (!r.ok) { $('rtacat').textContent = r.error; return r; }
  const done = r.tracks.filter(t => t.catalogued).map(t => t.track);
  $('rtacat').textContent = rL(r) + (r.not_supported.length ? `; not supported: ${r.not_supported.map(x => x.track + ' (' + x.why + ')').join('; ')}` : '')
    + (done.length ? '' : ' - press "Create" (about 5 minutes the first time, seconds afterwards; your game data is only read)');
  for (const id of ['rtatrk', 'rtadtrk', 'rtaxtrk']) { const s = $(id), keep = s.value, first = id === 'rtatrk' ? '<option value="">all tracks</option>' : '';
    s.innerHTML = first + (id === 'rtaxtrk' ? r.tracks : r.tracks.filter(t => t.catalogued)).map(t => `<option>${t.track}</option>`).join(''); if (keep) s.value = keep; }
  return r;
}
async function rtaStyles() {
  const r = await rtaOp({op: 'rta_styles'}); if (!r.ok) return r;
  $('rtasty').innerHTML = r.styles.map(s => `<option value="${s.id}"${s.usable ? '' : ' disabled'}>${s.title}${s.usable ? '' : ' (' + (s.why_not || s.problems.join('; ')) + ')'}</option>`).join('');
  return r;
}
function rtaTable(o) { return '<table style="font-size:11px">' + Object.entries(o).map(([k, v]) => `<tr><td>${k}</td><td>${typeof v === 'object' ? JSON.stringify(v).slice(0, 220) : v}</td></tr>`).join('') + '</table>'; }
async function rtaStyleShow() {
  const r = await rtaOp({op: 'rta_style_show', style: $('rtasty').value}); if (!r.ok) { $('rtastyout').textContent = r.error; return r; }
  const s = r.style; $('rtaw').value = s.defaults.road_width_m;
  $('rtastyout').innerHTML = `<b>${s.title}</b> - kind <b>${s.kind}</b>: ${s.kind_evidence}${s.name_note ? '<br>' + s.name_note : ''}`
    + `<br><b>Measured</b> (read only, from ${s.source.track || 'no game data'}):` + rtaTable(s.measured)
    + `<b>Palette</b> (why: ${Object.values(s.palette_why).join('; ').slice(0, 300)}):` + rtaTable(s.palette)
    + '<b>Artistic defaults</b> (editable, not measured):' + rtaTable(s.defaults) + '<b>Builder limits</b><br>' + s.builder_limits.map(x => '- ' + x).join('<br>');
  return r;
}
// route sketch: x right, z down (plan view), centred on the current route / template origin
function rtaSk() { const c = $('rtasketch'), g = c.getContext('2d'), S = +$('rtascale').value, k = c.width / S;
  g.clearRect(0, 0, c.width, c.height); g.strokeStyle = '#e2e2dc'; g.lineWidth = 1;
  for (let m = -S; m <= S; m += 50) { const x = c.width / 2 + m * k, y = c.height / 2 + m * k; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, c.height); g.stroke(); g.beginPath(); g.moveTo(0, y); g.lineTo(c.width, y); g.stroke(); }
  const P = RTA.pts.map(p => [c.width / 2 + (p[0] - RTA.ctr[0]) * k, c.height / 2 + (p[2] - RTA.ctr[2]) * k]);
  if (P.length) { g.strokeStyle = '#3a6ea5'; g.lineWidth = 2; g.beginPath(); P.forEach((p, i) => i ? g.lineTo(...p) : g.moveTo(...p)); if (P.length > 2) g.closePath(); g.stroke();
    P.forEach((p, i) => { g.fillStyle = i ? '#3a6ea5' : '#c0392b'; g.beginPath(); g.arc(p[0], p[1], 4, 0, 7); g.fill(); }); }
  g.fillStyle = '#555'; g.font = '10px sans-serif'; g.fillText(`grid 50 m; ${RTA.pts.length} point(s); red = point 0 (start, keep it on a straight)`, 4, c.height - 4);
  $('rtapts').value = RTA.pts.map(p => p.map(v => +v.toFixed(1)).join(' ')).join('\n'); }
function rtaPtsFromText() { RTA.pts = $('rtapts').value.split('\n').map(l => l.trim().split(/[\s,;]+/).map(Number)).filter(a => a.length >= 2 && a.every(isFinite))
  .map(a => a.length === 2 ? [a[0], +$('rtay').value, a[1]] : a); rtaSk(); }
async function rtaCurrent() { const r = await rtaOp({op: 'rta_route_current'}); if (r.ok) { RTA.ctr = r.centre; if (r.points) RTA.pts = r.points.map(p => p.slice()); rtaSk(); } return r; }
function rtaBody() {
  const ex = $('rtaex').value.split(';').map(s => s.trim().split(/[\s,]+/).map(Number)).filter(a => a.length === 4 && a.every(isFinite));
  const posts = $('rtaposts').value.split(';').map(s => s.trim().split(/\s+/)).filter(a => a.length >= 2 && a[0])
    .map(a => Object.assign({track: a[0], model: a[1], side: a[2] || 'both'}, a[3] ? {spacing_m: +a[3]} : {}, a[4] ? {start: +a[4]} : {}));
  const prm = {road_width_m: +$('rtaw').value, building_density: +$('rtabd').value, tree_density: +$('rtatd').value, lamp_density: +$('rtald').value};
  if (posts.length) prm.posts = posts;
  return {op: 'rta_generate_preview', style: $('rtasty').value, points: RTA.pts, seed: +$('rtaseed').value, exclude: ex, params: prm,
    parts: {lamps: $('rtapl').checked, buildings: $('rtapb').checked, trees: $('rtapt').checked}};
}
function rtaShowGen(s) {
  const R = s.result, L = ['PREVIEW (the project is unchanged):', ...R.summary_lines, 'steps: ' + R.steps.join(' -> '),
    `capacity: worst unit mesh ${R.worst_mesh_slot_pct} % / LOD ${R.worst_lod_slot_pct} % of the game's slot (capacity ${R.capacity_mode || 'game'}); ${R.rows} material rows (<= 83)`];
  for (const p of R.problems) L.push('PROBLEM: ' + p);
  for (const n of (R.capacity_info || [])) L.push('INFO: ' + n);
  if (R.capacity_declare && Object.keys(R.capacity_declare).length) L.push('INFO: the package will declare ' + Object.entries(R.capacity_declare).map(([k, v]) => `${k} = ${v}`).join(', ') + ' in mod.toml [bmashup.capacity]: ' + (R.capacity_requires || []).join('; '));
  rtaOut('rtagenout', L.join('\n'), R.problems.length ? 'bad' : 'warn');
  const all = R.skipped || [], sk = all.filter(x => x.at), notes = all.filter(x => !x.at); const by = {}; sk.forEach(x => { by[x.skipped] = (by[x.skipped] || 0) + 1; });
  $('rtaskip').innerHTML = notes.map(x => `<div class="warn">${x.part}: ${x.skipped}</div>`).join('') + (sk.length ? `<b>${sk.length} placement(s) skipped</b> (click a reason to see where): ` + Object.entries(by).map(([w, n], i) =>
    `<div><a href="#" data-i="${i}">${n} x ${w}</a></div>`).join('') : 'no placement skipped');
  $('rtaskip').querySelectorAll('a').forEach(a => a.onclick = e => { e.preventDefault(); const w = Object.keys(by)[+a.dataset.i];
    const pts = sk.filter(x => x.skipped === w && x.at).map(x => x.at.length === 2 ? [x.at[0], (RTA.pts[0] || [0, 20])[1] + 1, x.at[1]] : x.at);
    layoutOverlay({markers: pts}); $('editmsg').textContent = `${pts.length} marker(s): ${w}`; });
}
async function rtaGenerate() {
  RTA.pv = null; $('rtaapply').disabled = true; rtaOut('rtagenout', 'generation preview running in the background (cancel with "Cancel")...', 'warn');
  const s = await rtaWait(await rtaOp(rtaBody()), 'rtagenout'); if (!s) return null;
  RTA.pv = {job: s.id, key: s.result.preview_key}; rtaShowGen(s); $('rtaapply').disabled = !!s.result.problems.length; return s;
}
async function rtaApply() { if (!RTA.pv) return null; const r = await rtaOp({op: 'rta_generate', job: RTA.pv.job, preview_key: RTA.pv.key});
  rtaOut('rtagenout', rL(r), r.ok ? 'ok' : 'bad'); if (r.ok) { RTA.pv = null; $('rtaapply').disabled = true; layoutOverlay({}); await refresh(false); await rtaParts(); } return r; }
async function rtaParts() {
  const r = await rtaOp({op: 'rta_parts'}); if (!r.ok) { $('rtapartlist').textContent = r.error; return r; }
  $('rtapartlist').innerHTML = r.parts.length ? r.parts.map(p => `<div><b>${p.id}</b> ${p.items} item(s), seed ${p.seed}${p.locked ? ' LOCKED' : ''}${p.manually_edited ? ' <span class="warn">edited by hand</span>' : ''}
    <button data-a="lock" data-p="${p.id}">${p.locked ? 'Unlock' : 'Lock'}</button> new seed <input type="number" value="${p.seed + 1}" style="width:55px" id="rtaps_${p.id}">
    <button data-a="regen" data-p="${p.id}">Regenerate this part only</button></div>`).join('') : 'no generated parts in this project';
  $('rtapartlist').querySelectorAll('button').forEach(b => b.onclick = async () => { const p = r.parts.find(x => x.id === b.dataset.p);
    const q = b.dataset.a === 'lock' ? await rtaOp({op: 'rta_part_lock', part: p.id, locked: !p.locked})
      : await rtaOp({op: 'rta_part_regenerate', part: p.id, seed: +$('rtaps_' + p.id).value, confirm: $('rtaconf').checked});
    $('editmsg').textContent = rL(q); $('editmsg').className = q.ok ? 'note' : 'bad'; if (q.ok) { await refresh(false); await rtaParts(); } });
  return r;
}
function rtaAttachBody(op) { const [w, d, h] = $('rtaxsz').value.split(/\s+/).map(Number);
  return {op, dest: $('rtaxdir').value, unit: +$('rtaxu').value, side: +$('rtaxside').value, setback: +$('rtaxsb').value, along: +$('rtaxal').value,
    width: w, depth: d, height: h, texture: $('rtaxtex').value, roof_texture: $('rtaxroof').value}; }
async function rtaUnit() { const r = await rtaOp({op: 'rta_ext_unit', dest: $('rtaxdir').value, unit: +$('rtaxu').value});
  if (!r.ok) { rtaOut('rtaxout2', r.error, 'bad'); return r; }
  for (const id of ['rtaxtex', 'rtaxroof']) $(id).innerHTML = r.textures.map(t => `<option>${t}</option>`).join('');
  rtaOut('rtaxout2', `unit ${r.unit.unit}: ${r.unit.records} records (${r.unit.records_free} free), ${r.unit.vertices} vertices, mesh block ${r.unit.mesh_size} B (${r.unit.mesh_free_bytes} B free to the slot); materials it draws: ${r.textures.length}`, ''); return r; }
async function rtaAttachPreview() { RTA.ax = null; $('rtaxadd').disabled = true; const r = await rtaOp(rtaAttachBody('rta_ext_attach_preview'));
  if (!r.ok) { rtaOut('rtaxout2', 'REFUSED (nothing changed): ' + r.error, 'bad'); $('rtaxsvg').innerHTML = ''; return r; }
  RTA.ax = r.preview_key; $('rtaxsvg').innerHTML = r.svg; const R = r.report;
  rtaOut('rtaxout2', [rL(r), `size ${R.width_m} x ${R.depth_m} x ${R.height_m} m at base y ${R.base_y} (route ${R.route_y_here}); ground ${R.ground.map(g => g.y + ' ' + g.surface).join(', ')}`,
    `budget: ~${R.estimated_bytes} B of ${R.mesh_free_bytes} B free`, 'LOD: ' + R.lod, 'visibility: ' + R.visibility, 'collision: ' + R.collision, 'changes: ' + R.changes.join('; ')].join('\n'), R.fits ? 'warn' : 'bad');
  $('rtaxadd').disabled = !R.fits; return r; }
async function rtaExtJob(op, body) { rtaOut('rtaxout2', `${op} running...`, 'warn'); const s = await rtaWait(await rtaOp(Object.assign({op}, body)), 'rtaxout2');
  if (s) rtaOut('rtaxout2', [rL(s.result), JSON.stringify(s.result.files ? Object.fromEntries(Object.entries(s.result.files).map(([k, v]) => [k, v.identical !== undefined ? v.identical : (v.changed ? 'CHANGED' : 'unchanged')])) : {})].join('\n'), 'ok'); return s; }
function rtaShareBody(op) { return {op, kind: $('rtashk').value, dest: $('rtaxdir').value, author: $('rtaauth').value, licence: $('rtalic').value, out: $('rtashout').value}; }
function rtaSetup() {
  $('rtacatb').onclick = async () => { const s = await rtaWait(await rtaOp({op: 'rta_catalogue_build'}), 'rtagenout'); if (s) { $('rtacat').textContent = rL(s.result); await rtaCatStatus(); await rtaStyles(); } };
  $('rtacatx').onclick = () => RTA.job && rtaOp({op: 'rta_job_cancel', job: RTA.job});
  $('rtasearch').onclick = async () => { const r = await rtaOp({op: 'rta_catalogue_search', query: $('rtaq').value, kind: $('rtakind').value || null, track: $('rtatrk').value || null, limit: 150});
    if (!r.ok) { $('rtares').textContent = r.error; return; }
    $('rtares').innerHTML = r.rows.map((a, i) => `<div><a href="#" data-i="${i}">${a.track} ${a.id}</a> ${a.role || ''} ${a.area_m2 ? a.area_m2 + ' m2' : ''}${a.placements ? ' x' + a.placements : ''}</div>`).join('') || 'nothing found';
    $('rtares').querySelectorAll('a').forEach(el => el.onclick = async e => { e.preventDefault(); const a = r.rows[+el.dataset.i];
      const d = await rtaOp({op: 'rta_asset', track: a.track, id: a.id}); if (!d.ok) { $('rtaasset').textContent = d.error; return; }
      const A = d.asset; $('rtaasset').innerHTML = (d.thumbnail ? `<img src="${d.thumbnail}" style="float:left;margin:0 6px 4px 0;image-rendering:pixelated">` : '')
        + `<b>${a.track} ${A.id}</b> ${A.texture || ''} - ${A.role || A.kind}<br>` + rtaTable(Object.fromEntries(Object.entries(A).filter(([k]) => !['thumbnail', 'id', 'role'].includes(k))))
        + `<div class="note">${d.thumbnail_note}; LOCAL ONLY</div><div style="clear:both"></div>`
        + (/^[BSIP]/.test(A.id) ? `<div>Place in this project at x z <input type="text" id="rtaplpos" style="width:110px" value="${RTA.pts.length ? (RTA.pts[0][0] + 30).toFixed(0) + ' ' + (RTA.pts[0][2] + 30).toFixed(0) : ''}">
           turn <input type="number" id="rtaplang" value="0" style="width:50px"> collision <select id="rtaplcol"><option>keep</option><option>none</option></select>
           <button id="rtaplpv">Preview</button> <button id="rtaplgo" disabled>Place (one undo step)</button></div><div id="rtaplmsg" class="note"></div>` : '');
      const body = () => ({track: a.track, id: A.id, position: $('rtaplpos').value.trim().split(/\s+/).map(Number), angle: +$('rtaplang').value, collision: $('rtaplcol').value});
      if ($('rtaplpv')) { $('rtaplpv').onclick = async () => { const r = await rtaOp(Object.assign({op: 'rta_place_preview'}, body()));
          $('rtaplmsg').textContent = rL(r); RTA.plk = r.ok ? r.preview_key : null; $('rtaplgo').disabled = !r.ok; if (r.ok) layoutOverlay({new_faces: r.new_faces}); };
        $('rtaplgo').onclick = async () => { const r = await rtaOp(Object.assign({op: 'rta_place', preview_key: RTA.plk}, body()));
          $('rtaplmsg').textContent = rL(r); $('rtaplgo').disabled = true; if (r.ok) { layoutOverlay({}); await refresh(false); } }; }
    }); };
  $('rtastyshow').onclick = rtaStyleShow; $('rtasty').onchange = rtaStyleShow;
  $('rtaderive').onclick = async () => { const r = await rtaOp({op: 'rta_style_derive', track: $('rtadtrk').value, id: $('rtadid').value}); $('rtastyout').textContent = rL(r); if (r.ok) { await rtaStyles(); $('rtasty').value = r.style; } };
  const c = $('rtasketch');
  c.onclick = e => { const S = +$('rtascale').value, k = c.width / S, b = c.getBoundingClientRect();
    RTA.pts.push([RTA.ctr[0] + (e.clientX - b.left - c.width / 2) / k, +$('rtay').value, RTA.ctr[2] + (e.clientY - b.top - c.height / 2) / k]); rtaSk(); };
  c.oncontextmenu = e => { e.preventDefault(); RTA.pts.pop(); rtaSk(); };
  $('rtaclear').onclick = () => { RTA.pts = []; rtaSk(); }; $('rtacur').onclick = rtaCurrent; $('rtascale').onchange = rtaSk; $('rtapts').onchange = rtaPtsFromText;
  $('rtaptypes').onclick = async () => { const r = await rtaOp({op: 'rta_post_types'}); if (!r.ok) { $('rtaptlist').textContent = r.error; return; }
    $('rtaptlist').innerHTML = `<div class="note">${r.note}</div>` + r.posts.map((p, i) => `<div><a href="#" data-i="${i}">add</a> ${p.track} ${p.model} ${p.texture} ${p.size_m[1]} m tall, every ${p.spacing_m} m, setback ${p.setback_m} m (x${p.placements})</div>`).join('');
    $('rtaptlist').querySelectorAll('a').forEach(a => a.onclick = e => { e.preventDefault(); const p = r.posts[+a.dataset.i];
      $('rtaposts').value = ($('rtaposts').value.trim() ? $('rtaposts').value.trim() + '; ' : '') + `${p.track} ${p.model} both`; }); };
  $('rtagen').onclick = rtaGenerate; $('rtaapply').onclick = rtaApply; $('rtaparts').onclick = rtaParts;
  $('rtart').onclick = () => rtaExtJob('rta_ext_roundtrip', {track: $('rtaxtrk').value});
  $('rtaxnew').onclick = async () => { const r = await rtaOp({op: 'rta_ext_create', track: $('rtaxtrk').value, dest: $('rtaxdir').value}); rtaOut('rtaxout2', rL(r), r.ok ? 'ok' : 'bad'); if (r.ok) await rtaUnit(); };
  $('rtaxopen').onclick = async () => { const r = await rtaOp({op: 'rta_ext_open', dest: $('rtaxdir').value}); rtaOut('rtaxout2', rL(r), r.ok && !r.source_problem ? 'ok' : 'bad'); if (r.ok) await rtaUnit(); };
  $('rtaxunit').onclick = rtaUnit; $('rtaxpv').onclick = rtaAttachPreview;
  $('rtaxfind').onclick = async () => { const b = rtaAttachBody('rta_ext_attach_find'); delete b.setback; const r = await rtaOp(b);
    if (!r.ok) { rtaOut('rtaxout2', 'NOT FOUND: ' + r.error, 'bad'); return; }
    $('rtaxside').value = String(r.side); $('rtaxsb').value = r.report.setback_m; $('rtaxal').value = r.report.along; await rtaAttachPreview(); };
  $('rtaxadd').onclick = async () => { const r = await rtaOp(Object.assign(rtaAttachBody('rta_ext_attach_add'), {preview_key: RTA.ax})); rtaOut('rtaxout2', rL(r), r.ok ? 'ok' : 'bad'); $('rtaxadd').disabled = true; };
  $('rtaxundo').onclick = async () => { const r = await rtaOp({op: 'rta_ext_undo', dest: $('rtaxdir').value}); rtaOut('rtaxout2', rL(r), r.ok ? 'ok' : 'bad'); };
  $('rtaxbuild').onclick = () => rtaExtJob('rta_ext_build', {dest: $('rtaxdir').value, out: $('rtaxout').value});
  $('rtashpv').onclick = async () => { const r = await rtaOp(rtaShareBody('rta_recipe_preview')); rtaOut('rtashout2', r.ok ? [rL(r), 'excluded: ' + r.excluded.join(', '), r.sharing_md || ''].join('\n') : r.error, r.ok && !r.problems.length ? 'ok' : 'bad'); };
  $('rtashex').onclick = async () => { const r = await rtaOp(rtaShareBody('rta_recipe_export')); rtaOut('rtashout2', rL(r), r.ok ? 'ok' : 'bad'); };
  $('rtarchk').onclick = async () => { const r = await rtaOp({op: 'rta_recipe_check', path: $('rtarin').value}); rtaOut('rtashout2', rL(r), r.ok && r.can_rebuild ? 'ok' : 'bad'); };
  $('rtarreb').onclick = async () => { const r = await rtaOp({op: 'rta_recipe_rebuild', path: $('rtarin').value, dest: $('rtaxdir').value});
    if (r.ok && r.job) { const s = await rtaWait(r, 'rtagenout'); if (s) { RTA.pv = {job: s.id, key: s.result.preview_key}; rtaShowGen(s); $('rtaapply').disabled = !!s.result.problems.length; } }
    else rtaOut('rtashout2', rL(r), r.ok ? 'ok' : 'bad'); };
}
async function rtaInit() { if (ST.retail) { $('rtabox').style.display = 'none'; return; } rtaSetup(); await rtaCatStatus(); await rtaStyles(); await rtaCurrent();
  if (Q.get('panel') === 'rta') { $('rtabox').open = true; $('rtabox').scrollIntoView(); } }
// self test section 'rta' (only when asked: needs your game data + catalogue; ~1 minute)
async function selftestRta(ok, C0) {
  $('rtabox').open = true;
  const st = await rtaCatStatus(); ok('rta: catalogue status', st.ok && st.tracks.some(t => t.catalogued), $('rtacat').textContent.slice(0, 160));
  const sy = await rtaStyles(); ok('rta: styles listed, waterfront usable', sy.ok && sy.styles.some(s => s.id === 'waterfront_us_c1' && s.usable), sy.summary_lines && sy.summary_lines[0]);
  $('rtasty').value = 'waterfront_us_c1'; const ss = await rtaStyleShow(); ok('rta: style shows measured / palette / defaults separately', ss.ok && /Measured/.test($('rtastyout').innerHTML) && /Artistic defaults/.test($('rtastyout').innerHTML), '');
  $('rtaq').value = 'WF_Road2'; $('rtatrk').value = 'US/C1_V1'; await $('rtasearch').onclick(); const a = $('rtares').querySelector('a');
  ok('rta: asset search', !!a, $('rtares').textContent.slice(0, 120)); if (a) { await a.onclick({preventDefault() {}}); }
  ok('rta: asset detail with thumbnail', /<img/.test($('rtaasset').innerHTML), $('rtaasset').textContent.slice(0, 120));
  await rtaCurrent(); ok('rta: route from the current race layout', RTA.pts.length >= 4, RTA.pts.length);
  $('rtatd').value = 0.5; $('rtabd').value = 0.6; const g = await rtaGenerate();
  ok('rta: generation preview job (project unchanged)', g && g.job_state === 'done' && (await api('/api/state')).content_sha256 === C0, g ? g.result.summary_lines[0] : $('rtagenout').textContent);
  const sk = $('rtaskip').querySelector('a'); if (sk) sk.onclick({preventDefault() {}});
  ok('rta: skipped placements clickable (markers)', !sk || (ST.lay && ST.lay.points && ST.lay.points.length > 0), sk ? sk.textContent : 'none skipped');
  const ap = await rtaApply(); ok('rta: apply = one undo step', ap && ap.ok, ap && rL(ap));
  const pr = await rtaParts(); ok('rta: parts listed', pr.ok && pr.parts.length >= 1, $('rtapartlist').textContent.slice(0, 160));
  const u = await api('/api/undo', {}); const s2 = await api('/api/state'); ok('rta: one undo restores the project', u.ok && s2.content_sha256 === C0, u.undone);
  await refresh(false);
}
