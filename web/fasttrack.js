// Fast-track (triage nurse): a side panel next to the call. Tap a red flag, the clock starts, a coordinator is named.
// Looks like a panel opened from the patient record (the governance notes, the design language). The clinical decision stays with the nurse.
import { h, api, ls, every, clear, t, LANG, fullName, metricStrip, notesDot } from './lib.js';

export async function fastTrack(view) {
  const meta = await api('/meta');
  let county = ls.get('county', 'Länsi-Uusimaa'), calls = [], suggestions = [], selected = null, flag = null, picked = [], started = null;
  const left = h('div', { 'aria-label': t('ft_calls') }), right = h('div', { class: 'right' });
  const countySel = h('select', { 'aria-label': t('unit'), onchange: e => { county = e.target.value; ls.set('county', county); selected = null; started = null; loadCalls(); renderRight(); } },
    meta.counties.map(c => h('option', { value: c, selected: c === county }, c)));
  notesDot([{ head: t('n_assume_h'), body: [t('n_assume_ft'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_fast')), h('span', { class: 'sub' }, t('ft_sub')), countySel),
    h('div', { class: 'split' }, h('div', { class: 'left' }, h('div', { class: 'list-head' }, h('h2', {}, t('ft_calls'))), left), right));

  const langName = c => meta.languages[c];
  function renderLeft() {
    clear(left);
    if (!calls.length && !suggestions.length) left.append(h('p', { class: 'small', style: 'padding:16px' }, t('ft_none')));
    suggestions.forEach(c => left.append(h('button', { class: 'wrow', 'aria-pressed': selected && selected.id === c.id ? 'true' : 'false',
      onclick: () => { selected = c; flag = null; picked = []; started = null; renderLeft(); renderRight(); } },
      h('span', { class: 'nm' }, `${c.name} · ${c.age}`),
      h('span', { class: 'why' }, `${t('ft_caller_mentioned')}: “${c.says}”`),
      h('span', { class: 'status warn' }, t('voice_task_triage')))));
    calls.forEach(c => left.append(h('button', { class: 'wrow', 'aria-pressed': selected && selected.id === c.id ? 'true' : 'false',
      onclick: () => { selected = c; flag = null; picked = []; started = null; renderLeft(); renderRight(); } },
      h('span', { class: 'nm' }, `${c.name} · ${c.age}`),
      h('span', { class: 'why' }, `“${c.says}”`),
      c.prior.length >= 2 ? h('span', { class: 'status warn' }, t('third_contact')) : h('span', { class: 'xs' }, langName(c.language)))));
  }
  async function loadCalls() {
    try {
      const r = await api('/calls?county=' + encodeURIComponent(county));
      const changed = r.calls.map(c => c.id).join() !== calls.map(c => c.id).join() || (r.suggestions || []).map(c => c.id).join() !== suggestions.map(c => c.id).join();
      calls = r.calls; suggestions = r.suggestions || [];
      if (selected && ![...calls, ...suggestions].find(c => c.id === selected.id) && !started) { selected = null; renderRight(); }
      if (changed) renderLeft();
    } catch (e) {}
  }

  function renderRight() {
    clear(right);
    if (started) {
      const nm = fullName(meta, started.coordinator);
      right.append(h('h2', {}, started.coordinator ? t('ft_started', { name: selected.name }) : ''),
        h('p', {}, t('ft_coord', { nurse: nm })),
        h('div', { class: 'band', role: 'status' }, t('ft_day0')),
        h('div', { class: 'actions' },
          h('a', { class: 'btn primary', href: '#/today', style: 'display:inline-flex;align-items:center;text-decoration:none', onclick: () => ls.set('coordinator', started.coordinator) }, t('ft_open_today', { nurse: started.coordinator })),
          h('button', { class: 'linkbtn', onclick: () => { selected = null; started = null; flag = null; picked = []; renderLeft(); renderRight(); } }, t('ft_next_call'))));
      return;
    }
    if (!selected) {
      right.append(h('div', { class: 'empty' }, h('h2', {}, t('ft_pick')), h('p', { class: 'muted' }, t('ft_how_h')),
        h('ol', { class: 'steps' }, ['ft_how1', 'ft_how2', 'ft_how3'].map(k => h('li', {}, t(k))))));
      return;
    }
    const c = selected;
    right.append(h('div', { class: 'xs' }, t('ft_panel')), h('h2', { style: 'font-size:24px;margin-top:2px' }, `${c.name} · ${c.age}`),
      h('p', { class: 'muted', style: 'margin:2px 0 0' }, `${t('ft_phone')}${c.interpreter ? ' · ' + t('ft_interp', { lang: langName(c.language) }) : ''} · ${langName(c.language)}`),
      h('p', { style: 'margin:6px 0' }, `${c.suspicion ? t('ft_caller_mentioned') : t('ft_says')}: “${c.says}”`));
    if (c.prior.length >= 2) right.append(h('div', { class: 'band warn', role: 'alert' }, h('b', {}, t('ft_third_b', { n: c.prior.length + 1 })), ' ', t('ft_third_rest', { s: c.prior[0].symptom })));
    if (c.prior.length) right.append(h('div', { class: 'small' }, t('ft_earlier') + ': ' + c.prior.map(p => `${p.days_ago} ${t('days_ago')} (${t('kind_' + p.kind)})`).join(', ')));
    right.append(h('p', { style: 'font-weight:600;margin:16px 0 0' }, t('ft_flags')), h('p', { class: 'xs help', style: 'margin:0 0 4px' }, t('ft_flags_note')), h('p', { class: 'xs', style: 'margin:0 0 4px' }, t('ft_multi')));
    const btn = h('button', { class: 'btn primary wide', style: 'min-height:56px;font-size:18px', disabled: true }, t('ft_start'));
    for (const cancer of Object.keys(meta.red_flags)) {
      if (c.suspicion && cancer !== c.cancer) continue;
      right.append(h('h3', { style: 'margin:14px 0 2px;font-size:15px;color:var(--muted)' }, meta.cancers[cancer]),
        h('div', {}, meta.red_flags[cancer].map(f => h('button', { class: 'check row', 'aria-pressed': 'false', 'data-key': f.key, onclick: () => {                                          // tick every flag that applies; the first one ticked sets the pathway
          picked = picked.includes(f.key) ? picked.filter(k => k !== f.key) : [...picked, f.key]; flag = picked[0] || null;
          right.querySelectorAll('.check.row').forEach(b => { const on = picked.includes(b.dataset.key); b.setAttribute('aria-pressed', on ? 'true' : 'false'); b.querySelector('input').checked = on; });
          btn.disabled = !picked.length;
        } }, h('input', { type: 'checkbox', tabindex: '-1', 'aria-hidden': 'true', onclick: e => e.preventDefault() }), f.label))));
    }
    btn.addEventListener('click', async () => {
      btn.disabled = true; btn.textContent = t('ft_starting');
      try {
        started = await api(c.suspicion ? '/fasttrack/suggested' : '/fasttrack', { method: 'POST', body: c.suspicion
          ? { pathway_id: c.pathway_id, flag, extra_flags: picked.slice(1), nurse: 'Petra' } : { call_id: c.id, flag, extra_flags: picked.slice(1), nurse: 'Petra' } });
        loadCalls(); renderLeft(); renderRight();
      } catch (e) { btn.disabled = false; btn.textContent = t('ft_start'); right.append(h('div', { class: 'band alert', role: 'alert' }, e.message)); loadCalls(); }
    });
    right.append(h('p', { class: 'small help', style: 'margin-top:16px' }, t('ft_note')), btn);
  }
  view.children[0].after(metricStrip('triage', () => ({ county })));
  every(loadCalls, 4000);
  renderRight();
}
