// National view (FICAN / THL): counties side by side, aggregates only, n<5 suppressed, benchmark lines with source links. SYNTHETIC data.
import { h, api, ls, every, clear, t, loadBench, srcs, fmtNum, suppressed, metricStrip, notesDot, noteSrc } from './lib.js';

export async function national(view) {
  const meta = await api('/meta');
  const B = await loadBench();
  let cancer = ls.get('nat_cancer', ''), since = 0, tally = { events: 0, pulse: 0, new_fasttracks: 0 };
  const prev = {};
  const box = h('div', { class: 'scrollx' }), bench = h('div', { class: 'block', style: 'margin-top:24px' });
  const liveLine = h('p', { class: 'small', role: 'status' });
  const cancerSel = h('select', { 'aria-label': t('cancer'), onchange: e => { cancer = e.target.value; ls.set('nat_cancer', cancer); refresh(); } },
    [h('option', { value: '' }, t('all_cancers')), ...Object.entries(meta.cancers).map(([k, n]) => h('option', { value: k, selected: k === cancer }, n))]);
  notesDot([{ head: t('n_assume_h'), body: [t('n_assume_synth'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_nat')), cancerSel, h('span', { class: 'sub' }, t('nat_sub'))), box, bench, liveLine);

  const COLS = [['nat_c_n', 'n_pathways', '', null, null], ['nat_c_dx', 'c1_to_dx_median', '', null, null], ['nat_c_w6', 'within_6wk_pct', '%', 'no_target_70', 'low'],
    ['nat_c_s12', 'stage12_pct', '%', 'stage_target', 'low'], ['nat_c_loops', 'open_loops_per100', '', null, null], ['nat_c_inf', 'informed_pct', '%', null, null], ['nat_c_reach', 'reached_1wd_pct', '%', null, null],
    ['nat_c_dist', 'distress_pct', '%', null, null], ['nat_c_nps', 'nps', '', 'nps_target', 'low']];
  function cell(k, col) {
    const [, key, unit, bid, dir] = col;
    const v = k[key], id = `${k.county}:${key}`, changed = prev[id] !== undefined && prev[id] !== v;
    prev[id] = v;
    const bad = bid && dir === 'low' && v != null && v < B[bid].value;
    return h('td', { class: 'num' + (bad ? ' bad' : '') + (changed ? ' flash' : '') }, v == null ? suppressed() : fmtNum(v, unit));
  }
  function render(d) {
    const tb = h('table', { class: 't' });
    tb.append(h('tr', {}, h('th', {}, t('county')), COLS.map(c => h('th', {}, t(c[0])))));
    tb.append(h('tr', { class: 'bench' }, h('td', {}, t('benchmark')), COLS.map(c => h('td', {}, c[3] ? [`${B[c[3]].value}${c[2]}`, noteSrc('n_' + c[3], B[c[3]])] : (c[1] === 'distress_pct' ? [`${t('cutoff')} ${B.distress_cutoff.value}`, noteSrc('n_dc', B.distress_cutoff)] : '')))));
    tb.append(h('tr', { class: 'tot' }, h('td', {}, t('nat_total')), COLS.map(c => cell(d.national, c))));
    d.counties.forEach(k => tb.append(h('tr', {}, h('td', {}, h('a', { href: '#/control-tower', onclick: () => ls.set('ct_county', k.county) }, k.county)), COLS.map(c => cell(k, c)))));
    clear(box); box.append(tb);
    clear(bench);
    bench.append(h('h2', {}, t('benchmarks')), h('p', { class: 'hint' }, t('bench_hint')),
      h('div', { class: 'cols', style: 'margin:0' }, h('div', {}, [
        h('p', {}, h('b', {}, t('b_dk', { dk: B.lung_path_dk.value, fi: B.lung_path_fi.value })), ' ', t('b_dk_rest'), srcs(B.lung_path_dk, B.lung_path_fi)),
        h('p', {}, t('b_6wk', { n: B.thl_6wk.value }), srcs(B.thl_6wk)),
        h('p', {}, t('b_dkfast', { n: B.dk_cpp.value }), srcs(B.dk_cpp))]),
      h('div', {}, [
        h('p', {}, t('b_no', { n: B.no_target_70.value }), srcs(B.no_target_70)),
        h('p', {}, t('b_se', { n: B.se_target_80.value }), srcs(B.se_target_80)),
        h('p', {}, t('b_strategy', { s: B.stage_target.value, p: B.screen_target.value }), srcs(B.stage_target, B.screen_target))])));
  }
  async function refresh() {
    try { render(await api('/national' + (cancer ? '?cancer=' + cancer : ''))); } catch (e) { clear(box); box.append(h('div', { class: 'band alert' }, t('load_failed') + ' ' + e.message)); }
  }
  async function activity() {
    try {
      const a = await api(`/activity?since_id=${since}`);
      if (since) for (const k of Object.keys(tally)) tally[k] += a.counts[k] || 0;
      since = a.last_id;
      liveLine.textContent = t('live_line_nat', { e: tally.events, p: tally.pulse, f: tally.new_fasttracks });
    } catch (e) {}
  }
  view.children[0].after(metricStrip('national'));
  every(refresh, 3000); every(activity, 3000);
}
