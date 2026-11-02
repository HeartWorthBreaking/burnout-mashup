// ---------------------------------------------------------------- rta2: Environment designer + trusted asset library
const DSN = {rows: [], pv: null, styles: []};
function dsStyleOpts(sel) { return DSN.styles.map(s => `<option value="${s.id}"${s.id === sel ? ' selected' : ''}${s.usable ? '' : ' disabled'}>${s.title}</option>`).join(''); }
function dsRender() {
  $('dsseg').innerHTML = '<tr><th>from</th><th>to</th><th>style</th><th>landmark</th><th>open space</th><th>buildings</th></tr>' + DSN.rows.map((r, i) =>
    `<tr><td><input type="number" step="0.05" value="${r.from}" data-i="${i}" data-k="from" style="width:50px"></td>
     <td><input type="number" step="0.05" value="${r.to}" data-i="${i}" data-k="to" style="width:50px"></td>
     <td><select data-i="${i}" data-k="style">${dsStyleOpts(r.style)}</select></td>
     <td><input type="checkbox" data-i="${i}" data-k="landmark"${r.landmark ? ' checked' : ''}></td>
     <td><input type="checkbox" data-i="${i}" data-k="open_space"${r.open_space ? ' checked' : ''}></td>
     <td><select data-i="${i}" data-k="buildings"><option${r.buildings === 'generated' ? ' selected' : ''}>generated</option><option${r.buildings === 'retail' ? ' selected' : ''}>retail</option></select></td></tr>`).join('');
  $('dsseg').querySelectorAll('input,select').forEach(el => el.onchange = () => { const r = DSN.rows[+el.dataset.i], k = el.dataset.k;
    r[k] = el.type === 'checkbox' ? el.checked : (k === 'from' || k === 'to') ? +el.value : el.value; });
  $('dspts').textContent = RTA.pts.length; }
function dsBody(op) {
  const parts = {}; for (const c of ['buildings', 'posts', 'signs', 'trees', 'background', 'junction']) parts[c] = $('dsc_' + c).checked;
  return {op, points: RTA.pts, road_style: $('dsroad').value, segments: DSN.rows, seed: +$('dsseed').value, transition_m: +$('dstr').value,
    junction_at: $('dsjun').value.trim() === '' ? null : +$('dsjun').value, parts,
    params: Object.assign({headroom_pct: +$('dshead').value, plinths: $('dsplinth').checked, allow_open_shells: $('dsshell').checked},
      $('dsobj') && $('dsobj').value ? {objects: $('dsobj').value} : {}, $('dsprops') && $('dsprops').value !== 'none' ? {props: $('dsprops').value} : {})}; }
function dsSkips(list) { const by = {}; (list || []).forEach(x => { const k = x.part + ': ' + x.skipped.split('(')[0].trim(); (by[k] = by[k] || []).push(x); });
  $('dsskip').innerHTML = Object.keys(by).length ? '<b>Not placed (click to see where; remedy after the arrow)</b>' + Object.entries(by).map(([k, xs], i) =>
    `<div><a href="#" data-i="${i}">${xs.length} x ${k}</a> -> ${xs[0].remedy || ''}</div>`).join('') : 'everything planned was placed';
  $('dsskip').querySelectorAll('a').forEach(a => a.onclick = e => { e.preventDefault(); const xs = Object.values(by)[+a.dataset.i].filter(x => x.at);
    layoutOverlay({markers: xs.map(x => x.at.length === 2 ? [x.at[0], (RTA.pts[0] || [0, 20])[1] + 1, x.at[1]] : x.at)}); }); }
async function dsQuick() { const r = await rtaOp(dsBody('rta_design_quick'));
  if (!r.ok) { rtaOut('dsout', 'REFUSED (nothing changed): ' + r.error, 'bad'); return r; }
  const y = (RTA.pts[0] || [0, 20])[1] + 1, pts = [];
  for (const [c, ms] of Object.entries(r.markers)) for (const m of ms) if (m) pts.push([m[0], y, m[1]]);
  layoutOverlay({markers: pts});
  rtaOut('dsout', [...r.summary_lines, 'per neighbourhood: ' + JSON.stringify(r.per_segment), 'verges: outer ' + r.verges.outer_m + ' m / inner ' + r.verges.inner_m + ' m' +
    (r.verges.refused.length ? ' (stepped down: ' + r.verges.refused.join('; ') + ')' : ''), ...r.completeness_gaps.map(g => 'GAP: ' + g)].join('\n'), r.completeness_gaps.length ? 'warn' : '');
  dsSkips(r.skipped); return r; }
async function dsFull() { DSN.pv = null; $('dsapply').disabled = true; rtaOut('dsout', 'full preview running in the background (Cancel: Retail-style -> 1)...', 'warn');
  const s = await rtaWait(await rtaOp(dsBody('rta_design_preview')), 'dsout'); if (!s) return null; const R = s.result;
  DSN.pv = {job: s.id, key: R.preview_key};
  rtaOut('dsout', [...R.summary_lines, ...R.capacity_warnings.map(w => 'CAPACITY: ' + w), 'per neighbourhood: ' + JSON.stringify(R.per_segment)].join('\n'),
    R.problems.length ? 'bad' : R.capacity_warnings.length ? 'warn' : 'ok');
  dsSkips(R.skipped); $('dsapply').disabled = !!R.problems.length; return s; }
async function dsApply() { if (!DSN.pv) return null; const r = await rtaOp({op: 'rta_design_apply', job: DSN.pv.job, preview_key: DSN.pv.key});
  rtaOut('dsout', rL(r), r.ok ? 'ok' : 'bad'); if (r.ok) { DSN.pv = null; $('dsapply').disabled = true; layoutOverlay({}); await refresh(false); await dsParts(); } return r; }
async function dsParts() { const r = await rtaOp({op: 'rta_design_parts'}); if (!r.ok) return r;
  $('dspartlist').innerHTML = r.parts.length ? r.parts.map(p => `<div><b>${p.id}</b> ${p.items} item(s)${p.locked ? ' LOCKED' : ''}${p.manually_edited ? ' <span class="warn">edited by hand</span>' : ''}
    <button data-a="lock" data-p="${p.id}" data-l="${p.locked}">${p.locked ? 'Unlock' : 'Lock'}</button>
    ${['buildings', 'trees', 'posts', 'signs'].includes(p.category.replace(/[0-9]+$/, '')) ? `seed <input type="number" value="${(p.seed || 1) + 1}" style="width:55px" id="dsps_${p.id}"> <button data-a="regen" data-p="${p.id}" data-c="${p.category.replace(/[0-9]+$/, '')}">Regenerate this category</button>` : ''}</div>`).join('') : 'no design parts yet';
  $('dspartlist').querySelectorAll('button').forEach(b => b.onclick = async () => {
    const q = b.dataset.a === 'lock' ? await rtaOp({op: 'rta_design_lock', part: b.dataset.p, locked: b.dataset.l !== 'true'})
      : await rtaOp({op: 'rta_design_regenerate', category: b.dataset.c, seed: +$('dsps_' + b.dataset.p).value, confirm: $('dsconf').checked});
    $('editmsg').textContent = rL(q); $('editmsg').className = q.ok ? 'note' : 'bad'; if (q.ok) { await refresh(false); await dsParts(); } });
  return r; }
async function dsBuild() { let r = await api('/api/save', {}); if (!r.ok) { rtaOut('dsbuildout', 'SAVE REFUSED: ' + r.error, 'bad'); return r; }
  rtaOut('dsbuildout', 'building / validating / staging (kit gates)...', 'warn');
  r = await rtaOp({op: 'test_chain'}); rtaOut('dsbuildout', r.ok ? (r.summary_lines || []).join('\n') : 'FAILED: ' + r.error, r.ok && r.passed ? 'ok' : 'bad'); return r; }
async function tlSearch() { const r = await rtaOp({op: 'rta_trust_search', track: $('tlt').value || null, category: $('tlc').value || null, favourites: $('tlf').checked,
    min_confidence: +$('tlm').value, facing_road: $('tlr').checked, limit: 150});
  if (!r.ok) { $('tlres').textContent = r.error; return r; }
  $('tlres').innerHTML = `<div class="note">${rL(r)}</div>` + r.rows.map((a, i) => `<div><a href="#" data-i="${i}">${a.track} ${a.id}</a> ${a.category}
    (confidence ${a.category_confidence}${a.front_confidence !== undefined && a.front_confidence !== null ? ', front ' + a.front_confidence : ''})${a.favourite ? ' &#9733;' : ''}${(a.warnings || []).length ? ' <span class="warn">!</span>' : ''}</div>`).join('');
  $('tlres').querySelectorAll('a').forEach(el => el.onclick = e => { e.preventDefault(); return tlShow(r.rows[+el.dataset.i], 35); }); return r; }
async function tlShow(a, yaw) { const d = await rtaOp({op: 'rta_trust_asset', track: a.track, id: a.id, yaw}); if (!d.ok) { $('tldet').textContent = d.error; return d; }
  const A = d.asset, ov = A.override || {};
  $('tldet').innerHTML = (d.thumbnail ? `<img src="${d.thumbnail}" style="float:left;margin:0 6px 4px 0">` : '') +
    `<b>${a.track} ${A.id}</b> ${A.category} (confidence ${A.category_confidence})<br>front ${A.front_deg !== undefined ? A.front_deg + ' deg' : '-'} (${A.front_confidence !== undefined ? 'confidence ' + A.front_confidence : 'n/a'})
     ${A.original_road ? '- vs its original road ' + A.original_road.front_vs_road_deg + ' deg' : ''}<br>${(A.confidence_reasons || []).join('; ')}<br>
     ${(A.warnings || []).map(w => '<span class="warn">' + w + '</span>').join('<br>')}<br>
     view <button id="tlyl">&lt; 45</button> ${d.yaw} deg <button id="tlyr">45 &gt;</button><br>
     override: front <input type="number" id="tlof" value="${ov.front_deg !== undefined ? ov.front_deg : (A.front_deg || 0)}" style="width:55px"> deg,
     kind <select id="tloc"><option></option><option>intact building</option><option>building shell / facade</option><option>structure</option><option>scenery fragment</option><option>exclude</option></select>
     <label><input type="checkbox" id="tlofav"${ov.favourite ? ' checked' : ''}> favourite</label> <button id="tlsave">Save override</button> <button id="tlclr">Clear</button>
     <div class="note">${d.labels.verified}; ${d.labels.override}</div><div style="clear:both"></div>`;
  $('tlyl').onclick = () => tlShow(a, (d.yaw + 315) % 360); $('tlyr').onclick = () => tlShow(a, (d.yaw + 45) % 360);
  $('tlsave').onclick = async () => { const r = await rtaOp({op: 'rta_trust_override', track: a.track, id: A.id, front_deg: +$('tlof').value,
      category: $('tloc').value || null, favourite: $('tlofav').checked}); $('editmsg').textContent = rL(r); if (r.ok) tlShow(a, d.yaw); };
  $('tlclr').onclick = async () => { const r = await rtaOp({op: 'rta_trust_override', track: a.track, id: A.id, clear: true}); $('editmsg').textContent = rL(r); if (r.ok) tlShow(a, d.yaw); };
  return d; }
async function dsInit() {
  if (ST.retail) { $('dsbox').style.display = 'none'; return; }
  const st = await rtaOp({op: 'rta_styles'}); DSN.styles = st.ok ? st.styles : [];
  $('dsroad').innerHTML = dsStyleOpts('waterfront_us_c1');
  DSN.rows = [{from: 0, to: 0.45, style: 'waterfront_us_c1', landmark: true, open_space: false, buildings: 'generated'},
              {from: 0.45, to: 0.6, style: 'waterfront_us_c1', landmark: false, open_space: true, buildings: 'generated'},
              {from: 0.6, to: 1, style: 'city_us_c2', landmark: true, open_space: false, buildings: 'generated'}];
  dsRender();
  const cs = await rtaOp({op: 'rta_catalogue_status'});
  if (cs.ok) { $('dsdata').textContent = rL(cs); $('tlt').innerHTML = '<option value="">all</option>' + cs.tracks.filter(t => t.catalogued).map(t => `<option>${t.track}</option>`).join(''); }
  $('dsadd').onclick = () => { const last = DSN.rows[DSN.rows.length - 1]; const mid = +((last.from + last.to) / 2).toFixed(2);
    DSN.rows.push({from: mid, to: last.to, style: last.style, landmark: false, open_space: false, buildings: 'generated'}); last.to = mid; dsRender(); };
  $('dsdel').onclick = () => { if (DSN.rows.length > 1) { const r = DSN.rows.pop(); DSN.rows[DSN.rows.length - 1].to = r.to; dsRender(); } };
  $('dsquick').onclick = () => { dsRender(); return dsQuick(); }; $('dsfull').onclick = dsFull; $('dsapply').onclick = dsApply;
  $('dsparts').onclick = dsParts; $('dsbuild').onclick = dsBuild; $('tls').onclick = tlSearch;
  if (Q.get('panel') === 'design') { $('dsbox').open = true; $('dsbox').scrollIntoView(); }
}
async function selftestDesign(ok, C0) {
  $('dsbox').open = true; await rtaCurrent(); dsRender();
  ok('design: route available', RTA.pts.length >= 4, RTA.pts.length);
  const q = await dsQuick(); ok('design: quick preview (< 2 s, markers)', q.ok && q.seconds < 2 && ST.lay && ST.lay.points && ST.lay.points.length > 10, q.ok ? q.summary_lines[0] : q.error);
  const t = await tlSearch(); const a = $('tlres').querySelector('a'); ok('design: trusted search', t.ok && !!a, t.ok ? t.summary_lines[0] : t.error);
  if (a) { await a.onclick({preventDefault() {}}); }
  ok('design: asset detail with rotatable preview and override controls', /<img/.test($('tldet').innerHTML) && !!$('tlyr') && !!$('tlsave'), $('tldet').textContent.slice(0, 120));
  if ($('tlyr')) { const v0 = +($('tldet').textContent.match(/view\s*<\s*45\s+(\d+) deg/) || [0, -1])[1]; await $('tlyr').onclick(); const v1 = +($('tldet').textContent.match(/view\s*<\s*45\s+(\d+) deg/) || [0, -1])[1]; ok('design: preview rotated', v0 >= 0 && v1 === (v0 + 45) % 360 && /<img/.test($('tldet').innerHTML), v0 + ' -> ' + v1 + ' deg'); }
  const f = await dsFull(); ok('design: full preview job (project unchanged)', f && f.job_state === 'done' && (await api('/api/state')).content_sha256 === C0, f ? f.result.summary_lines[0] : $('dsout').textContent);
  const ap = await dsApply(); ok('design: apply = one undo step', ap && ap.ok, ap && rL(ap));
  const pr = await dsParts(); ok('design: categories listed', pr.ok && pr.parts.length >= 3, $('dspartlist').textContent.slice(0, 160));
  await refresh(false); const OB = (ST.scene.objects || {}).meshes || [];                    // RTA3: real retail instances (kit 0.3.2)
  ok('design: retail instances drawn (objects layer, cut-out class from the flags)', OB.length > 0 && Object.values(ST.meshes).some(m => m.obj && m.render === 'cutout'),
     JSON.stringify((ST.scene.objects || {}).counts || {}));
  const u = await api('/api/undo', {}); const s2 = await api('/api/state'); ok('design: one undo restores the project', u.ok && s2.content_sha256 === C0, u.undone);
  await refresh(false);
}
