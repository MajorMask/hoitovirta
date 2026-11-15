// County Control Tower: live KPIs, where the days go, equity gap, 14-day breach forecast, board decisions with owner and date. SYNTHETIC data.
// Also the one-page board pack (printable) opened from here.
import { h, api, ls, every, clear, t, loadBench, srcs, srcLink, fmtNum, suppressed, metricStrip, notesDot, noteSrc } from './lib.js';

const cache = {};
async function evidence(id, B) {
  if (B[id]) return B[id];
  if (!cache[id]) { try { cache[id] = await api('/evidence/' + id); } catch (e) { cache[id] = null; } }
  return cache[id];
}
const synth = () => ({ status: 'synthetic', short: t('new_metric'), source: t('synthetic_data'), url: '' });
const ans = n => (n ? t('cnt_answers', { n }) : t('cnt_none')), ppl = n => (n ? t('cnt_people', { n }) : t('cnt_none'));
const OWNERS = ['owner_cmo', 'owner_chief', 'owner_coord', 'owner_screen', 'owner_it'];

export async function controlTower(view) {
  const meta = await api('/meta');
  const B = await loadBench();
  let county = ls.get('ct_county', 'Länsi-Uusimaa'), cancer = ls.get('ct_cancer', '');
  let data = null, since = 0, tally = { events: 0, pulse: 0, new_fasttracks: 0, open_loops: 0 };
  const prev = {};
  const metricsBox = h('div', { class: 'metrics' }), mid = h('div', { class: 'cols' }), bottom = h('div', { class: 'cols' });
  const liveLine = h('p', { class: 'small', role: 'status' });
  const countySel = h('select', { 'aria-label': t('county'), onchange: e => { county = e.target.value; ls.set('ct_county', county); refresh(); } }, meta.counties.map(c => h('option', { value: c, selected: c === county }, c)));
  const cancerSel = h('select', { 'aria-label': t('cancer'), onchange: e => { cancer = e.target.value; ls.set('ct_cancer', cancer); refresh(); } },
    [h('option', { value: '' }, t('all_cancers')), ...Object.entries(meta.cancers).map(([k, n]) => h('option', { value: k, selected: k === cancer }, n))]);
  notesDot([{ head: t('n_risk_h'), body: t('n_risk') }, { head: t('n_assume_h'), body: [t('n_assume_synth'), t('n_assume_risk'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_ct')), h('span', { class: 'sub' }, t('ct_sub')), countySel, cancerSel), metricsBox, mid, bottom, liveLine, h('p', { class: 'small' }, t('pulse_lab_line') + ' ', h('a', { href: '/pulse-lab/' }, t('pulse_lab_link'))));

  function metric(id, value, label, sub, bad, ...es) {
    const changed = prev[id] !== undefined && prev[id] !== value; prev[id] = value;
    return h('div', { class: 'metric' + (changed ? ' flash' : '') }, h('span', { class: 'n' + (bad ? ' bad' : '') }, value == null ? suppressed() : value), h('span', { class: 'lab' }, label),
      sub ? h('span', { class: 'xs' }, sub) : null, noteSrc('k_' + id, ...es));
  }
  function renderMetrics() {
    const k = data.kpis, norway = B.no_target_70.value, stageT = B.stage_target.value, dc = B.distress_cutoff.value;
    clear(metricsBox);
    metricsBox.append(
      metric('dx', fmtNum(k.c1_to_dx_median, ' d'), t('m_dx'), t('m_dx_sub', { n: ppl(k.n_dx), s: fmtNum(k.t0_to_dx_median) ?? '–' }), false, synth(), B.no_delay_data),
      metric('w6', fmtNum(k.within_6wk_pct, '%'), t('m_w6'), t('m_w6_sub', { t: norway, n: ppl(k.n_tx) }), k.within_6wk_pct != null && k.within_6wk_pct < norway, B.thl_6wk, B.no_target_70),
      metric('s12', fmtNum(k.stage12_pct, '%'), t('m_s12'), t('m_s12_sub', { t: stageT, k: fmtNum(k.stage_known_pct, '%') || t('too_few') }), k.stage12_pct != null && k.stage12_pct < stageT, B.stage_target),
      metric('loops', String(k.open_loops), t('m_loops'), k.open_loops_per100 != null ? t('m_loops_sub', { n: k.open_loops_per100 }) : '', k.open_loops > 0, { status: 'synthetic', short: t('live_count'), source: t('synthetic_data'), url: '' }),
      metric('dist', fmtNum(k.distress_pct, '%'), t('m_dist'), t('m_dist_sub', { c: dc, n: ans(k.n_pu7) }), false, B.distress_cutoff),
      metric('inf', fmtNum(k.informed_pct, '%'), t('m_inf'), t('m_inf_sub', { n: ans(k.n_pu4) }), false, { status: 'synthetic', short: 'Pulse PU4', source: t('synthetic_data'), url: '' }),
      metric('reach', fmtNum(k.reached_1wd_pct, '%'), t('m_reach'), t('m_reach_sub', { n: ans(k.n_pu5) }), false, { status: 'synthetic', short: 'Pulse PU5', source: t('synthetic_data'), url: '' }),
      metric('voicecalls', String(data.voice_metrics.calls_week), t('voice_calls_week'), t('synthetic_data'), false, synth()),
      metric('voicepu4', String(data.voice_metrics.pu4_no), t('voice_pu4_no'), t('synthetic_data'), false, synth()));
  }
  function renderMid() {
    const s = data.segments, lung = cancer === 'lung';
    const rows = [[t('seg_patient'), 'patient', 'lung_seg_patient'], [t('seg_primary'), 'primary', 'lung_seg_primary'], [t('seg_specialist'), 'specialist', 'lung_seg_specialist']];
    const mx = Math.max(60, ...rows.map(r => s[r[1]] || 0), ...(lung ? rows.map(r => B[r[2]].value) : [0])) * 1.1;
    const seg = h('div', { class: 'block' }, h('h2', {}, t('days_go')), h('p', { class: 'hint' }, t('days_go_hint') + (cancer ? ` · ${meta.cancers[cancer]}` : ` · ${t('all_cancers').toLowerCase()}`)));
    rows.forEach(([lab, key, bid]) => seg.append(h('div', { class: 'brow' }, h('span', {}, lab),
      h('div', { class: 'bar', 'aria-hidden': 'true' }, s[key] != null ? h('i', { class: key === 'patient' ? 'grey' : 'bad', style: `width:${(s[key] / mx) * 100}%` }) : null,
        lung ? h('b', { style: `left:${(B[bid].value / mx) * 100}%`, title: `Yle MOT ${B[bid].value} d` }) : null),
      h('span', { class: 'v' }, s[key] != null ? fmtNum(s[key], ' d') : suppressed()))));
    seg.append(h('p', { class: 'small', style: 'margin-top:10px' }, t('bench_lung', { a: B.lung_seg_patient.value, b: B.lung_seg_primary.value, c: B.lung_seg_specialist.value, dk: B.lung_path_dk.value }), lung ? ' ' + t('black_marks') : ''),
      noteSrc('seg', B.lung_seg_primary, B.lung_path_dk));
    const eq = data.equity, flagged = eq.rows.find(r => r.flagged);
    const eqb = h('div', { class: 'block' }, h('h2', {}, t('equity')), h('p', { class: 'hint' }, t('equity_hint', { n: eq.flag_days })));
    if (flagged) eqb.append(h('div', { class: 'band warn' }, t('equity_band', { lang: flagged.name, d: fmtNum(flagged.gap) })));
    const mxg = Math.max(20, ...eq.rows.map(r => Math.abs(r.gap || 0))) * 1.05;
    eq.rows.forEach(r => eqb.append(h('div', { class: 'brow', style: 'grid-template-columns:100px minmax(0,1fr) auto' }, h('span', {}, r.name),
      h('div', { class: 'bar', 'aria-hidden': 'true' }, r.gap != null ? h('i', { class: r.flagged ? 'bad' : '', style: `width:${(Math.max(r.gap, 0) / mxg) * 100}%` }) : null),
      r.gap == null ? h('span', { class: 'supp' }, t('suppressed_small')) : h('span', { class: 'v', style: 'text-align:right' }, `${r.gap > 0 ? '+' : ''}${fmtNum(r.gap)} ${t('days_word')} `, h('span', { class: 'small', style: 'font-weight:400;display:block' }, t('eq_range', { lo: fmtNum(r.lo), hi: fmtNum(r.hi), n: r.n }))))));
    eqb.append(h('p', { class: 'small' }, t('equity_note') + ' '), noteSrc('eq', B.equity_flag));
    const pe = data.pulse_equity;
    if (pe) {
      const pb = h('div', { class: 'block', style: 'margin-top:16px' }, h('h3', {}, t('pulse_equity_title')),
        h('p', { class: 'hint' }, t('pulse_equity_hint', { days: pe.window_days })),
        h('p', { class: 'small' }, t('pulse_phone_share') + ': ' + (pe.phone_share_pct == null ? t('suppressed_small') : `${fmtNum(pe.phone_share_pct)}%`)));
      const table = h('table', { class: 't' }, h('thead', {}, h('tr', {}, h('th', {}, t('pulse_lang')), h('th', {}, t('pulse_channel')), h('th', {}, t('pulse_rate')))));
      const body = h('tbody');
      pe.rows.filter(r => r.responses !== null || r.eligible !== null).forEach(r => body.append(h('tr', {},
        h('td', {}, meta.languages[r.language] || r.language), h('td', {}, t('channel_' + r.channel)),
        h('td', {}, r.rate_pct == null ? t('suppressed_small') : `${fmtNum(r.rate_pct)}% (${r.responses}/${r.eligible})`))));
      table.append(body); pb.append(table); eqb.append(pb);
    }
    clear(mid); mid.append(seg, eqb);
  }
  let dpEl = null, dsig = '';
  const openForms = new Set(), formVals = {};
  function renderBottom() {
    const f = data.forecast, mx = Math.max(1, ...f.series, ...f.series_if_loops_closed);
    const fp = h('div', { class: 'block' }, h('h2', {}, t('next14')), h('p', { class: 'hint' }, t('fc_head', { n: fmtNum(f.expected_14d), o: f.already_over })),
      h('div', { class: 'fc', role: 'img', 'aria-label': t('fc_aria', { n: fmtNum(f.expected_14d) }) }, f.series.map((x, i) => h('div', { class: 'col', title: `${i}: ${fmtNum(x)}` }, h('i', { style: `height:${(x / mx) * 100}%` }), h('u', { style: `height:${(f.series_if_loops_closed[i] / mx) * 100}%` })))),
      h('div', { class: 'fc-axis' }, h('span', {}, t('today_word')), h('span', {}, '+7 ' + t('days_word')), h('span', {}, '+14 ' + t('days_word'))),
      h('p', { class: 'small', style: 'margin-top:8px' }, t('fc_note', { c: fmtNum(f.expected_14d_if_closed), a: f.with_open_loop, b: f.pathways_reaching_6wk_in_window })),
      h('p', { class: 'small' }, f.method + ' '), noteSrc('fc', B.forecast_loop_days));
    // the decisions panel is only rebuilt when a decision changed: a redraw every 3 s used to close the owner/date form right after "Accept"
    const sig = JSON.stringify(data.decisions);
    if (!dpEl || sig !== dsig) {
      dsig = sig; dpEl = h('div', { class: 'block' }, h('h2', {}, t('board_title')), h('p', { class: 'hint' }, t('board_hint')));
      data.decisions.forEach(d => dpEl.append(decisionEl(d)));
      dpEl.append(h('p', { style: 'margin-top:12px' }, h('a', { href: '#/board' }, t('board_pack_link'))));
    }
    clear(bottom); bottom.append(fp, dpEl);
  }
  function decisionEl(d) {
    const st = d.state;
    const owner = h('select', { 'aria-label': t('owner') }, OWNERS.map(o => h('option', { value: o }, t(o))));
    const due = h('input', { type: 'date', 'aria-label': t('due'), value: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10), style: 'min-height:44px;border:1px solid var(--ink);padding:0 8px' });
    const fv = formVals[d.key] || (formVals[d.key] = {});
    if (fv.owner) owner.value = fv.owner; if (fv.due) due.value = fv.due;
    owner.addEventListener('change', () => { fv.owner = owner.value; }); due.addEventListener('change', () => { fv.due = due.value; });
    const form = h('div', { class: 'actions', style: 'display:' + (openForms.has(d.key) ? 'flex' : 'none') }, h('label', {}, t('owner') + ' ', owner), h('label', {}, t('due') + ' ', due),
      h('button', { class: 'btn primary', onclick: () => decide(d, 'accepted', `${owner.value}|${due.value}`) }, t('confirm_accept')));
    const info = st ? (() => { const [o, dd] = (st.note || '').split('|'); return `${st.decision === 'accepted' ? t('accepted') : t('deferred')} · ${st.decided_by}${o ? ` · ${t('owner')}: ${t(o)}` : ''}${dd ? ` · ${t('due')}: ${dd}` : ''}`; })() : null;
    const el = h('div', { class: 'dec' }, h('h3', {}, d.title), h('ul', {}, d.why.map(w => h('li', {}, w))), h('div', { class: 'evi', 'data-ev': d.evidence.join(',') }),
      h('div', { class: 'actions', style: 'margin-top:8px' }, h('button', { class: 'btn', onclick: () => { const open = form.style.display === 'none'; form.style.display = open ? 'flex' : 'none'; open ? openForms.add(d.key) : openForms.delete(d.key); } }, t('accept')),
        h('button', { class: 'btn', onclick: () => decide(d, 'deferred', '') }, t('defer'))), form,
      info ? h('p', { class: 'small', role: 'status', style: 'font-weight:600;margin:6px 0 0' }, info) : null);
    Promise.all(d.evidence.map(id => evidence(id, B))).then(es => el.querySelector('.evi').replaceChildren(srcs(...es.filter(Boolean)), h('span', { class: 'xs' }, ` · ${t('roadmap')} ${d.measure}`)));
    return el;
  }
  async function decide(d, decision, note) {
    try { await api('/board', { method: 'POST', body: { county, key: d.key, title: d.title, decision, by: 'County board', note } }); refresh(); } catch (e) {}
  }
  async function refresh() {
    try { data = await api(`/controltower?county=${encodeURIComponent(county)}${cancer ? '&cancer=' + cancer : ''}`); renderMetrics(); renderMid(); renderBottom(); }
    catch (e) { clear(metricsBox); metricsBox.append(h('div', { class: 'band alert' }, t('load_failed') + ' ' + e.message)); }
  }
  async function activity() {
    try {
      const a = await api(`/activity?since_id=${since}&county=${encodeURIComponent(county)}`);
      if (since) for (const k of Object.keys(tally)) tally[k] += a.counts[k] || 0;
      since = a.last_id;
      liveLine.textContent = t('live_line', { e: tally.events, p: tally.pulse, f: tally.new_fasttracks, l: tally.open_loops });
    } catch (e) {}
  }
  every(refresh, 3000); every(activity, 3000);
}

// ---- one-page board pack (printable) ----------------------------------------------------------------------------------------
export async function boardPack(view) {
  const B = await loadBench();
  const county = ls.get('ct_county', 'Länsi-Uusimaa');
  const [d, log] = await Promise.all([api(`/controltower?county=${encodeURIComponent(county)}`), api(`/board?county=${encodeURIComponent(county)}`)]);
  const k = d.kpis;
  const row = (a, b, es) => h('tr', {}, h('td', {}, a), h('td', { class: 'num' }, b == null ? suppressed() : b), h('td', {}, es ? srcs(...es) : ''));
  view.append(h('div', { class: 'page-head no-print' }, h('h1', {}, t('pack_title')), h('button', { class: 'btn primary', onclick: () => window.print() }, t('print')), h('a', { href: '#/control-tower' }, t('back'))),
    h('div', { class: 'pack' },
      h('img', { src: '/logo.svg', alt: '', width: '40', height: '40', style: 'display:block;margin-bottom:8px' }), h('h1', { style: 'font-size:24px' }, `${t('pack_title')} · ${county}`), h('p', { class: 'small' }, t('proto_footer')),
      h('h2', { style: 'margin-top:16px' }, t('pack_numbers')),
      h('table', { class: 't' }, row(t('m_dx'), fmtNum(k.c1_to_dx_median, ' d'), [synth()]), row(t('m_w6'), fmtNum(k.within_6wk_pct, '%'), [B.thl_6wk, B.no_target_70]),
        row(t('m_s12'), fmtNum(k.stage12_pct, '%'), [B.stage_target]), row(t('m_loops'), String(k.open_loops), null), row(t('m_dist'), fmtNum(k.distress_pct, '%'), [B.distress_cutoff]),
        row(t('m_inf'), fmtNum(k.informed_pct, '%'), null), row(t('m_reach'), fmtNum(k.reached_1wd_pct, '%'), null)),
      h('h2', { style: 'margin-top:16px' }, t('next14')), h('p', {}, t('fc_head', { n: fmtNum(d.forecast.expected_14d), o: d.forecast.already_over }) + ' ' + t('fc_note', { c: fmtNum(d.forecast.expected_14d_if_closed), a: d.forecast.with_open_loop, b: d.forecast.pathways_reaching_6wk_in_window })),
      h('h2', { style: 'margin-top:16px' }, t('equity')), d.equity.rows.filter(r => r.flagged).length
        ? d.equity.rows.filter(r => r.flagged).map(r => h('p', {}, t('equity_band', { lang: r.name, d: fmtNum(r.gap) }))) : h('p', {}, t('pack_no_gap', { n: d.equity.flag_days })),
      h('h2', { style: 'margin-top:16px' }, t('pack_decisions')),
      h('table', { class: 't' }, h('tr', {}, h('th', {}, t('pack_decision')), h('th', {}, t('pack_status')), h('th', {}, t('owner')), h('th', {}, t('due'))),
        d.decisions.map(x => { const st = x.state, [o, dd] = ((st && st.note) || '').split('|'); return h('tr', {}, h('td', {}, x.title), h('td', {}, st ? (st.decision === 'accepted' ? t('accepted') : t('deferred')) : t('pack_open')), h('td', {}, o ? t(o) : ''), h('td', {}, dd || '')); })),
      h('p', { class: 'xs', style: 'margin-top:16px' }, t('pack_note'))));
}
