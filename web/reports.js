// Reports (diagnostics): paste a report, the AI extracts fields with a confidence score, doubtful ones go to a "needs check" queue.
// A suspicious finding with no next step is flagged for the coordinator. Stage and diagnosis are only saved after a person confirms. SYNTHETIC data.
import { h, api, ls, every, clear, t, metricStrip, notesDot } from './lib.js';

const KINDS = ['imaging', 'lab', 'pathology', 'other'], STAGES = ['unknown', 'I', 'II', 'III', 'IV'];

export async function reports(view) {
  const meta = await api('/meta');
  const ex = (await api('/reports/examples')).examples;
  let county = ls.get('rep_county', 'Länsi-Uusimaa'), patient = null, searchTimer = null;
  const resultBox = h('div'), lists = h('div', { class: 'cols', style: 'margin-top:24px' });
  const picked = h('div', { class: 'small', style: 'margin-top:6px' }), pickList = h('div', { class: 'pick' });
  const ta = h('textarea', { id: 'rtext', placeholder: t('rep_paste') });
  const go = h('button', { class: 'btn primary', style: 'min-height:48px', disabled: true }, t('rep_structure'));
  const countySel = h('select', { 'aria-label': t('unit'), onchange: e => { county = e.target.value; ls.set('rep_county', county); patient = null; clear(picked); search(''); refreshState(); } },
    meta.counties.map(c => h('option', { value: c, selected: c === county }, c)));
  const exSel = h('select', { id: 'rex', onchange: e => { if (e.target.value !== '') { ta.value = ex[+e.target.value].text; refreshState(); } } },
    [h('option', { value: '' }, t('rep_example_ph')), ...ex.map((x, i) => h('option', { value: i }, x.label))]);
  const file = h('input', { type: 'file', accept: '.txt,text/plain', id: 'rfile', onchange: e => { const f = e.target.files[0]; if (f) f.text().then(x => { ta.value = x.slice(0, 8000); refreshState(); }); } });
  const q = h('input', { type: 'text', id: 'rq', placeholder: t('rep_search_ph'), autocomplete: 'off', oninput: e => { clearTimeout(searchTimer); searchTimer = setTimeout(() => search(e.target.value), 250); } });
  const form = h('div', {},
    h('h2', {}, t('rep_new')),
    h('div', { class: 'field' }, h('label', { for: 'rq' }, t('rep_patient')), q, pickList, picked),
    h('div', { class: 'field' }, h('label', { for: 'rtext' }, t('rep_text')), ta),
    h('div', { style: 'display:flex;gap:16px;flex-wrap:wrap' }, h('div', { class: 'field', style: 'flex:1;margin:0' }, h('label', { for: 'rex' }, t('rep_example')), exSel),
      h('div', { class: 'field', style: 'margin:0' }, h('label', { for: 'rfile' }, t('rep_upload')), file)),
    h('div', { class: 'actions' }, go, h('span', { class: 'small' }, t('rep_note'))));
  ta.addEventListener('input', refreshState);
  notesDot([{ head: t('n_assume_h'), body: [t('n_assume_rep'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_reports')), h('span', { class: 'sub' }, t('rep_sub')), countySel),
    h('div', { class: 'cols' }, form, resultBox), lists);

  function refreshState() { go.disabled = !(patient && ta.value.trim().length >= 3); }
  async function search(text) {
    try {
      const r = await api(`/pathways/search?q=${encodeURIComponent(text)}&county=${encodeURIComponent(county)}&limit=6`);
      clear(pickList);
      r.rows.forEach(p => pickList.append(h('button', { onclick: () => choose(p) }, `${p.id} · ${p.name} · ${meta.cancers[p.cancer]} · ${p.age}`)));
    } catch (e) {}
  }
  function choose(p) {
    patient = p; clear(pickList); clear(picked);
    picked.append(h('b', {}, `${p.name} (${p.id})`), `, ${meta.cancers[p.cancer]}, ${t('coordinator').toLowerCase()} ${p.coordinator || t('rep_no_coord')}`);
    refreshState();
  }
  const yn = b => (b ? t('yes') : t('no'));

  function renderResult(r, who) {
    clear(resultBox);
    const f = r.fields, low = r.status === 'needs_check';
    const card = h('div', { class: 'box', role: 'region', 'aria-label': t('rep_structured') });
    card.append(h('h2', {}, who || t('rep_structured')), h('span', { class: 'status ' + (low ? 'warn' : 'ok'), style: 'margin:6px 0' }, low ? t('rep_needs_check') : (r.status === 'confirmed' ? t('rep_confirmed') : t('rep_saved'))),
      h('div', { class: 'small' }, h('span', { class: 'meter' }, h('i', { class: low ? 'low' : '', style: `width:${Math.round(r.confidence * 100)}%` })), `${t('rep_conf')} ${Math.round(r.confidence * 100)}% · ${r.engine}`,
        r.agreement && (!r.agreement.suspicious || !r.agreement.next_step) ? ' · ' + t('rep_disagree') : ''));
    if (low) {
      const inp = (id, label, val) => h('div', { class: 'field' }, h('label', { for: id }, label), h('input', { type: 'text', id, value: val ?? '' }));
      const sel = (id, label, opts, val) => h('div', { class: 'field' }, h('label', { for: id }, label), h('select', { id }, opts.map(o => h('option', { value: o, selected: o === val }, o))));
      const chk = (id, label, val) => h('label', { class: 'check', for: id }, h('input', { type: 'checkbox', id, checked: val }), label);
      card.append(inp('f-test', t('rep_test'), f.test), inp('f-finding', t('rep_finding'), f.finding), sel('f-kind', t('rep_kind'), KINDS, f.kind), sel('f-stage', t('rep_stage_in'), STAGES, f.stage),
        chk('f-sus', t('rep_suspicious'), f.suspicious), chk('f-next', t('rep_next_stated'), f.next_step_stated), inp('f-nexttxt', t('rep_next'), f.next_step),
        chk('f-st', t('rep_also_stage'), false), chk('f-dx', t('rep_also_dx'), false));
      const ok = h('button', { class: 'btn primary', style: 'min-height:48px' }, t('rep_confirm_save'));
      ok.addEventListener('click', async () => {
        ok.disabled = true;
        const g = id => document.getElementById(id);
        const include = [...(g('f-st').checked ? ['stage'] : []), ...(g('f-dx').checked ? ['T4'] : [])];
        try {
          const res = await api(`/reports/${r.report_id}/confirm`, { method: 'POST', body: { by: 'Diagnostics', include, fields: {
            test: g('f-test').value, finding: g('f-finding').value, kind: g('f-kind').value, stage: g('f-stage').value,
            suspicious: g('f-sus').checked, next_step_stated: g('f-next').checked, next_step: g('f-nexttxt').value || null } } });
          renderResult({ ...r, status: 'confirmed', confidence: 1, engine: 'human-checked', saved: res.saved, propose: {} }, who); loadLists();
        } catch (e) { ok.disabled = false; card.append(h('div', { class: 'band alert' }, e.message)); }
      });
      card.append(h('div', { class: 'actions' }, ok), h('p', { class: 'small' }, t('rep_nothing_saved')));
    } else {
      card.append(h('dl', { class: 'kv' }, h('dt', {}, t('rep_kind')), h('dd', {}, f.kind), h('dt', {}, t('rep_test')), h('dd', {}, f.test || '-'), h('dt', {}, t('rep_finding')), h('dd', {}, f.finding || '-'),
        h('dt', {}, t('rep_suspicious')), h('dd', {}, yn(f.suspicious)), h('dt', {}, t('rep_next_stated')), h('dd', {}, f.next_step_stated ? (f.next_step || t('yes')) : t('no')), h('dt', {}, t('rep_stage_in')), h('dd', {}, f.stage)));
      if (r.saved && r.saved.length) card.append(h('ul', { class: 'plain' }, r.saved.map(s => h('li', {}, s)))); else card.append(h('p', { class: 'small' }, t('rep_logged')));
      const p = r.propose || {};
      if (p.diagnosis || p.stage) {
        const ok = h('button', { class: 'btn' }, t('rep_confirm_dx'));
        ok.addEventListener('click', async () => {
          ok.disabled = true;
          try {
            const res = await api(`/reports/${r.report_id}/confirm`, { method: 'POST', body: { by: 'Diagnostics', include: [...(p.stage ? ['stage'] : []), ...(p.diagnosis ? ['T4'] : [])], fields: {} } });
            renderResult({ ...r, status: 'confirmed', saved: [...(r.saved || []), ...res.saved], propose: {} }, who); loadLists();
          } catch (e) { ok.disabled = false; }
        });
        card.append(h('div', { class: 'actions' }, ok));
      }
    }
    resultBox.append(card);
  }
  go.addEventListener('click', async () => {
    go.disabled = true; go.textContent = t('rep_structuring');
    try { const r = await api('/reports/ingest', { method: 'POST', body: { pathway_id: patient.id, text: ta.value, by: 'Diagnostics' } }); renderResult(r, patient.name); loadLists(); }
    catch (e) { clear(resultBox); resultBox.append(h('div', { class: 'band alert' }, e.message)); }
    go.textContent = t('rep_structure'); refreshState();
  });

  function item(i, review) {
    return h('div', { class: 'qitem' }, h('div', { class: 't' }, `${i.name} · ${meta.cancers[i.cancer]}`, i.flag ? h('span', { class: 'status warn', style: 'margin-left:8px' }, t('rep_no_next')) : null),
      h('div', { class: 'x' }, i.fields.finding || i.excerpt.slice(0, 90)),
      h('div', { class: 'x' }, review ? `${t('rep_conf')} ${Math.round(i.confidence * 100)}%` : t('rep_in_today', { nurse: i.coordinator || '-' })),
      review ? h('div', { style: 'margin-top:4px' }, h('button', { class: 'linkbtn', onclick: () => renderResult({ report_id: i.report_id, status: 'needs_check', fields: i.fields, confidence: i.confidence, engine: i.engine, saved: [], agreement: null }, i.name) }, t('rep_review'))) : null);
  }
  async function loadLists() {
    try {
      const d = await api('/reports?county=' + encodeURIComponent(county));
      clear(lists);
      lists.append(
        h('div', { class: 'block' }, h('h2', {}, t('rep_queue', { n: d.queue.length })), h('p', { class: 'hint' }, t('rep_queue_hint')), d.queue.length ? d.queue.map(i => item(i, true)) : h('p', { class: 'small' }, t('rep_nothing_waiting'))),
        h('div', { class: 'block' }, h('h2', {}, t('rep_flagged', { n: d.flagged.length })), h('p', { class: 'hint' }, t('rep_flagged_hint')), d.flagged.length ? d.flagged.map(i => item(i, false)) : h('p', { class: 'small' }, t('rep_nothing_flagged'))));
    } catch (e) {}
  }
  search('');
  view.children[0].after(metricStrip('diagnostics', () => ({ county })));
  every(loadLists, 4000);
}
