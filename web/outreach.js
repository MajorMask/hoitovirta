// Outreach (screening unit): who has not responded, by language; what made it hard (PU3); SMS in their language (a person approves);
// a call list. In this demo nothing is really sent: replies are simulated. SYNTHETIC data.
import { h, api, ls, every, clear, t, loadBench, fmtNum, suppressed, metricStrip, notesDot, noteSrc } from './lib.js';

const BARRIERS = ['time', 'cost', 'language', 'fear', 'noappt', 'notserious'];

export async function outreach(view) {
  const meta = await api('/meta');
  const B = await loadBench();
  let county = ls.get('out_county', 'Länsi-Uusimaa'), programme = ls.get('out_prog', 'breast'), language = '';
  const selected = new Set(), prev = {};
  let lastList = [];
  const metrics = h('div', { class: 'metrics' }), mid = h('div', { class: 'cols' }), draftBox = h('div'), listBox = h('div'), callBox = h('div');
  const status = h('p', { role: 'status', style: 'font-weight:600;margin:8px 0' });
  const PROG = { breast: t('prog_breast'), colorectal: t('prog_crc') };
  const countySel = h('select', { 'aria-label': t('county'), onchange: e => { county = e.target.value; ls.set('out_county', county); selected.clear(); refresh(); } }, meta.counties.map(c => h('option', { value: c, selected: c === county }, c)));
  const progSel = h('select', { 'aria-label': t('programme'), onchange: e => { programme = e.target.value; ls.set('out_prog', programme); selected.clear(); clear(draftBox); refresh(); } },
    Object.entries(PROG).map(([k, n]) => h('option', { value: k, selected: k === programme }, n)));
  notesDot([{ head: t('n_assume_h'), body: [t('n_assume_out'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_out')), h('span', { class: 'sub' }, t('out_sub')), countySel, progSel), metrics, mid, status, draftBox, listBox, callBox);

  function metric(id, value, label, sub, bad, ...es) {
    const changed = prev[id] !== undefined && prev[id] !== value; prev[id] = value;
    return h('div', { class: 'metric' + (changed ? ' flash' : '') }, h('span', { class: 'n' + (bad ? ' bad' : '') }, value == null ? suppressed() : value), h('span', { class: 'lab' }, label), h('span', { class: 'xs' }, sub), noteSrc('o_' + id, ...es));
  }
  function render(sum) {
    const target = B.screen_target.value, nat = programme === 'breast' ? B.screen_breast : B.screen_crc;
    clear(metrics);
    metrics.append(
      metric('part', fmtNum(sum.participation, '%'), t('o_part', { p: PROG[programme].toLowerCase() }), t('o_part_sub', { t: target, n: nat.value }), sum.participation != null && sum.participation < target, B.screen_target, nat),
      metric('inv', String(sum.invited), t('o_invited'), t('o_invited_sub', { n: sum.pending })),
      metric('non', String(sum.non_responders), t('o_non'), t('o_non_sub'), sum.non_responders > 0),
      metric('con', String(sum.contacted), t('o_con'), t('o_con_sub')),
      metric('call', String(sum.call_list), t('o_call'), t('o_call_sub')));
    const lang = h('div', { class: 'block' }, h('h2', {}, t('o_by_lang')), h('p', { class: 'hint' }, t('o_by_lang_hint')));
    sum.rows.forEach(r => lang.append(h('div', { class: 'brow' }, h('span', {}, meta.languages[r.language]),
      h('div', { class: 'bar', 'aria-hidden': 'true' }, r.participation != null ? h('i', { class: r.participation < target ? 'bad' : '', style: `width:${r.participation}%` }) : null, h('b', { style: `left:${target}%`, title: `${t('target')} ${target}%` })),
      h('span', { class: 'v' }, r.participation != null ? fmtNum(r.participation, '%') : suppressed()))));
    lang.append(h('p', { class: 'small', style: 'margin-top:8px' }, t('o_national_gap', { a: B.eq_lang_dom.value, b: B.eq_lang_oth.value }), noteSrc('o_gap', B.eq_lang_oth)));
    const bar = h('div', { class: 'block' }, h('h2', {}, t('o_hard')), h('p', { class: 'hint' }, t('o_hard_hint')));
    bar.append(h('select', { 'aria-label': t('o_filter'), onchange: e => { language = e.target.value; selected.clear(); refresh(); } },
      [h('option', { value: '' }, t('o_all_langs')), ...Object.entries(meta.languages).map(([k, n]) => h('option', { value: k, selected: k === language }, n))]));
    const b = sum.barriers;
    if (!b.mix) bar.append(h('p', { class: 'small', style: 'margin-top:12px' }, t('o_few', { n: b.n })));
    else {
      const mx = Math.max(...b.mix.map(m => m.pct || 0), 1);
      b.mix.forEach(m => bar.append(h('div', { class: 'brow', style: 'grid-template-columns:170px minmax(0,1fr) 56px' }, h('span', {}, t('bar_' + m.key)),
        h('div', { class: 'bar', 'aria-hidden': 'true' }, h('i', { style: `width:${((m.pct || 0) / mx) * 100}%` })), h('span', { class: 'v' }, m.pct != null ? fmtNum(m.pct, '%') : suppressed()))));
      bar.append(h('p', { class: 'small' }, t('o_replies', { n: b.n })));
    }
    clear(mid); mid.append(lang, bar);
  }
  function renderList(d) {
    lastList = d.rows;
    const all = h('input', { type: 'checkbox', 'aria-label': t('o_select_all'), checked: d.rows.length > 0 && d.rows.every(r => selected.has(r.id)),
      onchange: e => { d.rows.forEach(r => (e.target.checked ? selected.add(r.id) : selected.delete(r.id))); renderList(d); } });
    const sms = h('button', { class: 'btn primary', style: 'min-height:48px', disabled: selected.size === 0, onclick: openDraft }, t('o_send_sms', { n: selected.size }));
    const call = h('button', { class: 'btn', disabled: selected.size === 0, onclick: addCalls }, t('o_add_calls'));
    const tbl = h('table', { class: 't' }, h('tr', {}, h('th', {}, all), h('th', {}, t('o_name')), h('th', {}, t('o_age')), h('th', {}, t('o_language')), h('th', {}, t('o_days')), h('th', {}, t('o_status'))),
      d.rows.map(r => h('tr', {}, h('td', {}, h('input', { type: 'checkbox', 'aria-label': r.name, checked: selected.has(r.id), onchange: e => { e.target.checked ? selected.add(r.id) : selected.delete(r.id); renderList(d); } })),
        h('td', {}, r.name), h('td', {}, String(r.age)), h('td', {}, meta.languages[r.language]), h('td', {}, String(r.days)),
        h('td', {}, [r.contacted ? h('span', { class: 'status ok', style: 'margin-right:6px' }, t('o_sms_sent')) : null, r.on_call_list ? h('span', { class: 'status warn', style: 'margin-right:6px' }, t('o_on_calls')) : null, r.barrier ? h('span', { class: 'xs' }, t('bar_' + r.barrier)) : null]))));
    clear(listBox);
    listBox.append(h('div', { class: 'block', style: 'margin-top:16px' }, h('h2', {}, t('o_list', { n: d.total })), h('p', { class: 'hint' }, t('o_list_hint') + (language ? ` ${meta.languages[language]}.` : '')),
      h('div', { class: 'scrollx' }, tbl), h('div', { class: 'actions' }, sms, call)));
  }
  async function openDraft() {
    const langs = [...new Set(lastList.filter(r => selected.has(r.id)).map(r => r.language))];
    clear(draftBox);
    const box = h('div', { class: 'box', style: 'margin-top:16px', role: 'region', 'aria-label': t('o_preview') }, h('h2', {}, t('o_preview')), h('p', { class: 'small' }, t('o_preview_hint')));
    draftBox.append(box);
    const areas = {}, checks = {};
    const ok = h('button', { class: 'btn primary', style: 'min-height:48px', disabled: true }, t('approve'));
    const gate = () => { ok.disabled = !Object.values(checks).every(c => c.checked); };
    for (const l of langs) {
      const d = await api('/outreach/draft', { method: 'POST', body: { programme, language: l } });
      const n = lastList.filter(r => selected.has(r.id) && r.language === l).length;
      const ta = h('textarea', { 'aria-label': `SMS ${d.language_name}`, dir: l === 'ar' ? 'rtl' : 'ltr', style: 'min-height:90px' }, d.text);
      areas[l] = ta;
      const note = l === 'so' ? t('somali_warn_sms') : (d.translated ? '' : t('o_not_translated'));
      box.append(h('div', { class: 'field' }, h('label', {}, `${meta.languages[l]} · ${t('o_people', { n })} · ${d.engine}`), ta, note ? h('div', { class: 'band alert', style: 'margin:4px 0' }, note) : null));
      if (l !== 'en') {
        const c = h('input', { type: 'checkbox', id: 'chk-' + l, onchange: gate }); checks[l] = c;
        box.append(h('label', { class: 'check', for: 'chk-' + l }, c, t('o_checked', { lang: meta.languages[l] })));
      }
    }
    gate();
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      try {
        const messages = Object.fromEntries(Object.entries(areas).map(([l, ta]) => [l, ta.value]));
        const r = await api('/outreach/send', { method: 'POST', body: { invite_ids: [...selected], messages, by: 'Screening unit' } });
        status.textContent = t('o_sent', { n: r.sent }); selected.clear(); clear(draftBox); refresh();
      } catch (e) { ok.disabled = false; box.append(h('div', { class: 'band alert' }, e.message)); }
    });
    box.append(h('div', { class: 'actions' }, ok, h('button', { class: 'btn', onclick: () => clear(draftBox) }, t('cancel'))));
  }
  async function addCalls() {
    try { const r = await api('/outreach/calllist', { method: 'POST', body: { invite_ids: [...selected], by: 'Screening unit' } }); status.textContent = t('o_listed', { n: r.listed }); selected.clear(); refresh(); }
    catch (e) { status.textContent = e.message; }
  }
  function renderCalls(d) {
    clear(callBox);
    if (!d.rows.length) return;
    callBox.append(h('div', { class: 'block', style: 'margin-top:16px' }, h('h2', {}, t('o_call_list', { n: d.rows.length })),
      d.rows.map(r => h('div', { class: 'qitem' }, h('div', { class: 't' }, `${r.name} · ${meta.languages[r.language]} · ${r.age}`),
        h('div', { class: 'x' }, t('o_call_line', { d: r.days }) + (r.barrier ? ` · ${t('o_barrier')}: ${t('bar_' + r.barrier)}` : '') + (['ar', 'so', 'ru'].includes(r.language) ? ' · ' + t('o_interp') : '')),
        h('button', { class: 'linkbtn', onclick: async () => { await api('/outreach/called', { method: 'POST', body: { invite_id: r.id, by: 'Screening unit' } }); refresh(); } }, t('o_mark_called'))))));
  }
  async function refresh() {
    const q = `county=${encodeURIComponent(county)}&programme=${programme}${language ? '&language=' + language : ''}`;
    try {
      const [s, l, c] = await Promise.all([api('/outreach/summary?' + q), api('/outreach/list?' + q), api(`/outreach/calls?county=${encodeURIComponent(county)}&programme=${programme}`)]);
      render(s); renderList(l); renderCalls(c);
    } catch (e) { clear(metrics); metrics.append(h('div', { class: 'band alert' }, t('load_failed') + ' ' + e.message)); }
  }
  view.children[0].after(metricStrip('screening', () => ({ county, programme })));
  every(refresh, 3000);
}
