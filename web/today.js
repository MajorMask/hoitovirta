// Today (coordinator): the worklist, ranked by breach risk and vulnerability, one reason per row. A panel like the EHR side panel:
// timeline, AI one-line summary, Fast-diagnosis lane, AI draft in the patient's language -> a person approves -> send log. SYNTHETIC data.
import { h, api, ls, every, clear, t, getLang, loadBench, fullName, metricStrip, notesDot, noteSrc, authFetch } from './lib.js';
import { persona } from './roles.js';

export async function today(view) {
  const meta = await api('/meta');
  const B = await loadBench();
  // role views (the role views spec): the coordinator sees everything; the admin only bookings; the specialist only people from referral received to MDT
  const mode = persona().today || 'coordinator';
  let coordinator = ls.get('coordinator', 'Laura');
  let rows = [], tasks = [], total = 0, loops = 0, selectedId = null, detail = null, draft = null, showAll = false, slotOpen = false, record = false, loaded = false, slotFree = null;
  const seen = new Set();
  const left = h('div', { 'aria-label': t('today_list_aria') }), right = h('div', { class: 'right' });
  const listTitle = h('h2', {}), toggle = h('button', { class: 'linkbtn', onclick: () => { showAll = !showAll; loadList(); } });
  const counts = h('span', { class: 'counts' });
  const coordSel = h('select', { 'aria-label': t('coordinator'), onchange: e => { coordinator = e.target.value; ls.set('coordinator', coordinator); selectedId = null; detail = null; seen.clear(); loaded = false; loadList(); } },
    Object.entries(meta.coordinators).map(([county, names]) => h('optgroup', { label: county }, names.map(n => h('option', { value: n, selected: n === coordinator }, fullName(meta, n))))));
  notesDot(mode === 'booking' ? [{ head: t('role_admin'), body: t('booking_view') }] : mode === 'specialist' ? [{ head: t('role_specialist'), body: t('specialist_view') }]
    : [{ head: t('n_risk_h'), body: t('n_risk') }, { head: t('n_assume_h'), body: [t('n_assume_risk'), t('n_assume_targets')] }]);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, t('r_today')), h('span', { class: 'sub' }, t('today_sub')), coordSel, counts),
    h('div', { class: 'split' }, h('div', { class: 'left' }, h('div', { class: 'list-head' }, listTitle, toggle), left), right));

  const statusOf = r => r.alert ? ['alert', t('st_call')] : r.slipped ? ['alert', t('st_slipped')]
    : r.open_loop ? ['alert', r.target_days ? t('day_of', { d: r.day, n: r.target_days }) : t('st_loop')] : r.new ? ['ok', t('st_new')] : ['', t('day_n', { d: r.day })];

  function renderLeft() {
    clear(left);
    listTitle.textContent = t('today_list', { n: total + tasks.length });
    toggle.textContent = showAll ? t('top_only') : t('all_patients');
    if (!rows.length && !tasks.length) left.append(h('p', { class: 'small', style: 'padding:16px' }, t('today_none')));
    (mode === 'coordinator' ? tasks : []).forEach(task => {
      const done = h('button', { class: 'btn', style: 'min-height:44px', onclick: async () => {
        done.disabled = true;
        try { await api(`/tasks/${encodeURIComponent(task.id)}/done`, { method: 'POST', body: {} }); await loadList(); }
        catch (e) { done.disabled = false; }
      } }, t('today_done'));
      const path = h('button', { class: 'linkbtn', style: 'min-height:44px', onclick: () => select(task.pathway_id) }, task.pathway_id || '');
      left.append(h('div', { class: 'wrow task', role: 'group', 'aria-label': task.kind === 'callback' ? t('voice_task_callback') : t('voice_task_triage') },
        h('span', { class: 'nm' }, task.kind === 'callback' ? t('voice_task_callback') : t('voice_task_triage')),
        h('span', { class: 'why bad' }, task.detail), path, done));
    });
    rows.forEach(r => {
      const fresh = loaded && !seen.has(r.id), [cls, txt] = statusOf(r);
      left.append(h('button', { class: 'wrow' + (fresh ? ' fresh' : ''), 'aria-pressed': r.id === selectedId ? 'true' : 'false', onclick: () => select(r.id) },
        h('span', { class: 'nm' }, r.age != null ? `${r.name} · ${r.age}` : r.name),
        h('span', { class: 'why' + (mode === 'coordinator' && (r.open_loop || r.alert) ? ' bad' : '') }, mode === 'booking' ? `${r.next_label} · ${r.language_name}${r.interpreter ? ' · ' + t('interp_word') : ''}`
          : mode === 'specialist' ? `${r.cancer_label} · ${r.step_label}` : r.reason + (r.language !== 'fi' ? ` · ${r.language_name}` : '')),
        mode === 'coordinator' ? h('span', { class: 'status ' + cls }, txt) : h('span', { class: 'small' }, r.day != null ? t('day_n', { d: r.day }) : '')));
    });
    rows.forEach(r => seen.add(r.id));
  }
  async function loadList() {
    try {
      const w = await api(`/worklist?coordinator=${encodeURIComponent(coordinator)}&limit=${showAll || mode === 'specialist' ? 50 : 6}`);
      rows = mode === 'specialist' ? w.rows.filter(r => ['T2', 'T3', 'T4', 'T5'].includes(r.step)) : w.rows; tasks = w.tasks || []; total = mode === 'specialist' ? rows.length : w.total; loops = w.open_loops;
      counts.textContent = t('today_counts', { n: w.total, k: tasks.length, m: w.open_loops });
      if (!selectedId) { selectedId = rows[0] ? rows[0].id : null; if (selectedId) selectDetail(selectedId, true); else { detail = null; renderRight(); } }
      renderLeft(); loaded = true;
    } catch (e) {}
  }
  function select(id) { selectedId = id; slotOpen = false; record = false; renderLeft(); selectDetail(id, true); }

  async function selectDetail(id, fresh) {
    if (mode === 'booking') { detail = rows.find(r => r.id === id) || null; renderRight(); return; }
    if (fresh) { detail = null; draft = null; right.replaceChildren(h('p', { class: 'muted' }, t('loading'))); }
    try {
      const d = await api('/pathways/' + id);
      if (selectedId !== id) return;
      const first = !detail || detail.id !== id;
      detail = d;
      if (first) { renderRight(); loadSummary(id); if (mode === 'coordinator') { loadDraft(id); loadSlots(); } } else updateLive();
    } catch (e) {}
  }
  async function loadSlots() {
    try { slotFree = (await api('/slots/summary?county=' + encodeURIComponent(detail.county))).free; renderLane(); } catch (e) {}
  }
  const stepLabel = s => s.label;
  function stripEl() {
    const stuck = detail.open_loop || detail.slipped || detail.alert;
    return h('div', { class: 'strip', id: 'strip', role: 'list', 'aria-label': t('strip_aria') }, detail.steps.map(s =>
      h('div', { class: `s ${s.state}${s.state === 'current' && stuck ? ' stuck' : ''}`, role: 'listitem' }, h('div', { class: 'b' }), h('div', { class: 'l' }, stepLabel(s)),
        h('div', { class: 'd' }, s.day != null ? t('day_n', { d: s.day }) : (s.booked ? t('booked') : '')))));
  }
  function bandEl() {
    const d = detail, bad = d.open_loop || d.slipped || d.alert;
    const parts = [h('span', {}, d.reason)];
    if (d.target_days && d.open_loop) parts.push(h('span', {}, ' ' + t('fit_line', { d: d.day, n: d.target_days })));
    if (bad && d.step && ['T0', 'T1', 'T2'].includes(d.step)) parts.push(' ', h('button', { class: 'linkbtn', style: 'min-height:0', onclick: () => { slotOpen = !slotOpen; renderSlots(); } }, t('book_slot')));
    return h('div', { class: 'band' + (bad ? ' warn' : ''), id: 'band' }, ...parts);
  }
  function updateLive() {
    const s = document.getElementById('strip'); if (s) s.replaceWith(stripEl());
    const b = document.getElementById('band'); if (b) b.replaceWith(bandEl());
    renderLane(); renderAsk(); renderDoNow(); renderSignals();
  }
  function laneRows() {
    const d = detail, ref = d.referral || { state: 'none' };
    const refTxt = { none: t('fdl_ref_none'), waiting: t('fdl_ref_wait', { d: ref.days, n: ref.target }), overdue: t('fdl_ref_over', { d: ref.days, n: ref.target }),
      accepted: t('fdl_ref_ok', { d: ref.days, n: ref.target }), accepted_late: t('fdl_ref_late', { d: ref.days, n: ref.target }) }[ref.state];
    const kind = { lung: 'ct', breast: 'imaging', colorectal: 'colonoscopy', prostate: 'mri', haematological: 'lab' }[d.cancer];
    const free = slotFree ? slotFree[kind] : null;
    const bk = draft && draft.booking;
    return [
      [t('fdl_slots'), free == null ? '…' : t('fdl_slots_n', { n: free, test: t('kind_' + kind) })],
      [t('fdl_chain'), bk ? t('fdl_chain_n', { test: bk.label_loc, when: bk.when_loc, reserved: bk.reserved ? t('fdl_reserved') : t('fdl_not_reserved') }) : '…'],
      [t('fdl_ref'), refTxt]];
  }
  function renderLane() {
    const el = document.getElementById('lane'); if (!el || !detail) return;
    clear(el);
    el.append(h('h3', { style: 'margin-bottom:4px' }, t('fdl_title')), ...laneRows().map(([k, v]) => h('div', { style: 'display:grid;grid-template-columns:200px minmax(0,1fr);gap:12px;padding:8px 0;border-top:1px solid var(--line)' },
      h('span', { class: 'small' }, k), h('span', {}, v))));
  }
  async function renderSlots() {
    const el = document.getElementById('slots'); if (!el) return;
    clear(el);
    if (!slotOpen) return;
    const kind = { lung: 'ct', breast: 'imaging', colorectal: 'colonoscopy', prostate: 'mri', haematological: 'lab' }[detail.cancer];
    const r = await api(`/slots?county=${encodeURIComponent(detail.county)}&kind=${kind}&limit=8`);
    el.append(h('p', { class: 'small', style: 'margin:8px 0 0' }, t('slot_pick')),
      ...(r.slots.length ? r.slots.map(s => h('button', { class: 'check row', onclick: () => { slotOpen = false; renderSlots(); loadDraft(detail.id, s.id); } }, h('input', { type: 'checkbox', tabindex: '-1', 'aria-hidden': 'true', onclick: e => e.preventDefault() }), s.when))
        : [h('p', { class: 'small' }, t('slot_none'))]));
  }
  function renderRight() {
    clear(right);
    if (!detail) { right.append(h('p', { class: 'muted' }, t('select_someone'))); return; }
    const d = detail, bits = [d.cancer_label, t('susp_recorded', { d: d.day }), d.interpreter ? t('interp_short', { lang: d.language_name }) : null].filter(Boolean).join(' · ');
    if (mode === 'booking') {                                   // admin: booking facts only, no clinical content
      const when = d.booking ? new Intl.DateTimeFormat(getLang(), { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(d.booking.due)) : t('none_yet');
      right.append(h('h1', {}, d.name), h('div', { class: 'band' }, t('booking_view')),
        h('dl', { class: 'kv' }, h('dt', {}, t('next_appt')), h('dd', {}, `${d.next_label} · ${when}`), h('dt', {}, t('slot_word')), h('dd', {}, d.booking && d.booking.slot ? t('fdl_reserved') : t('none_yet')),
          h('dt', {}, t('language')), h('dd', {}, `${d.language_name}${d.interpreter ? ' · ' + t('interp_word') : ''}`), h('dt', {}, t('owner_word')), h('dd', {}, fullName(meta, d.coordinator))));
      return;
    }
    if (mode === 'specialist') {                                // specialist: timeline and stage, no messages, Pulse or booking tools
      right.append(h('h1', {}, d.name), h('p', { class: 'muted', style: 'margin:2px 0 10px' }, `${d.age} · ${bits}`), h('p', { id: 'summary', style: 'font-size:17px;margin:0 0 4px' }, t('summarising')), stripEl(), h('div', { class: 'band' }, t('specialist_view')));
      return;
    }
    right.append(h('h1', {}, `${d.name}`), h('p', { class: 'muted', style: 'margin:2px 0 10px' }, `${d.age} · ${bits} · `, h('button', { class: 'linkbtn', style: 'min-height:0', onclick: () => { record = !record; renderRecord(); } }, t('open_record'))),
      h('div', { id: 'record' }),
      h('div', { id: 'donow' }), h('p', { id: 'summary', style: 'font-size:17px;margin:0 0 4px' }, t('summarising')), stripEl(), bandEl(), h('div', { id: 'ask-card' }), h('div', { id: 'signals' }), h('div', { id: 'slots' }),
      h('div', { id: 'lane', style: 'margin:20px 0' }), h('div', { id: 'draft-card' }, h('p', { class: 'muted' }, t('drafting'))),
      noteSrc('steps', B.step_limits));
    renderLane(); askKey = null; sigFor = null; renderAsk(); renderDoNow(); renderSignals();
  }
  // ---- "Do now": the one next action, in the order a coordinator would choose; then the patient's own signals --------------------------------
  function renderDoNow() {
    const el = document.getElementById('donow'); if (!el || !detail || mode !== 'coordinator') return;
    const d = detail, first = d.name.split(' ')[0];
    const [kind, text] = d.open_question ? ['alert', t('dn_reply', { name: first })] : d.alert ? ['alert', t('dn_call', { name: first })]
      : d.slipped ? ['alert', t('dn_slip', { name: first })] : d.open_loop ? ['warn', t('dn_book', { step: (d.next_label || '').toLowerCase() })]
      : d.risk >= 0.8 ? ['warn', t('dn_risk', { name: first })] : ['', t('dn_ok')];
    clear(el); el.append(h('div', { class: 'donow' + (kind ? ' ' + kind : '') }, h('span', { class: 'dn-label' }, t('dn_title')), h('b', {}, text)));
  }
  const NEEDS = { transport: 'need_transport', interpreter: 'need_interpreter', schedule_conflict: 'need_schedule', practical_cost: 'need_cost', caregiver_support: 'need_carer', fear_or_distress: 'need_fear', info_gap: 'need_info', other: 'need_other', callback_today: 'need_callback' };
  let sigFor = null;
  async function renderSignals() {
    const el = document.getElementById('signals'); if (!el || !detail || mode !== 'coordinator') return;
    const id = detail.id; let ev, vnow;
    try { [ev, vnow] = await Promise.all([api('/events?pathway_id=' + encodeURIComponent(id)).then(r => r.events), api('/health').then(r => new Date(r.vnow))]); } catch (e) { return; }
    if (!detail || detail.id !== id) return;
    const lastOf = type => [...ev].reverse().find(e => e.type === type);
    const ago = e => { const n = Math.floor((vnow - new Date(e.ts)) / 864e5); return n <= 0 ? t('today_word') : `${n} ${t('days_ago')}`; };
    const ans = { yes: t('sig_yes'), no: t('sig_no'), unsure: t('sig_unsure'), not_tried: t('sig_not_tried') };
    const rows = [];
    const w = lastOf('pulse:PU7'); if (w) rows.push([t('sig_worry'), `${w.value} / 10 · ${ago(w)}`, Number(w.value) >= 4 ? 'warn' : '']);
    const inf = lastOf('pulse:PU4'); if (inf) rows.push([t('sig_informed'), `${ans[inf.value] || inf.value} · ${ago(inf)}`, inf.value !== 'yes' ? 'warn' : '']);
    const r5 = lastOf('pulse:PU5'), r5a = lastOf('pulse:PU5a');
    if (r5) rows.push([t('sig_reach'), `${ans[r5.value] || r5.value} · ${ago(r5)}`, r5.value === 'no' ? 'warn' : '']); else if (r5a) rows.push([t('sig_reach'), (r5a.value === 'not_tried' ? t('sig_not_tried') : ans[r5a.value] || r5a.value) + ` · ${ago(r5a)}`, '']);
    const nps = lastOf('pulse:PU9'); if (nps) rows.push([t('sig_nps'), `${nps.value} / 10`, Number(nps.value) <= 6 ? 'warn' : '']);
    const cm = lastOf('pulse:PU9b'); if (cm && cm.value && cm.value !== 'skip') rows.push([t('sig_comment'), `“${cm.value}”`, '']);
    ev.filter(e => e.type === 'need').slice(-3).forEach(e => { let v = {}; try { v = JSON.parse(e.value); } catch (x) {} const k = NEEDS[v.need] ? t(NEEDS[v.need]) : v.need; rows.push([t('sig_needs'), `${k} · ${v.confirmed ? t('sig_conf') : v.source === 'companion' ? t('sig_safety') : ''} · ${ago(e)}`, 'warn']); });
    const extra = ev.filter(e => e.type === 'red_flag').map(e => e.value); if (extra.length) rows.push([t('sig_flags'), extra.join(', '), '']);
    const key = id + JSON.stringify(rows); if (key === sigFor) return; sigFor = key;
    clear(el); el.append(h('div', { class: 'signals' }, h('h3', {}, t('sig_title')), rows.length
      ? rows.map(([k, v, cls]) => h('div', { class: 'sig-row' + (cls ? ' ' + cls : '') }, h('span', { class: 'small' }, k), h('span', {}, v)))
      : h('p', { class: 'small', style: 'margin:4px 0 0' }, t('sig_none'))));
  }
  // a patient's open question: show it, draft a safe acknowledgement in their language, a person edits and approves
  let askKey = null, sentFor = null;
  async function renderAsk() {
    const el = document.getElementById('ask-card'); if (!el || !detail) return;
    const q = detail.open_question, key = detail.id + '|' + (q || '');
    if (key === askKey) return;                                  // keep what the coordinator is typing across polls
    askKey = key; clear(el);
    if (!q) { if (sentFor === detail.id) el.append(h('div', { class: 'band', role: 'status' }, t('ask_sent'))); return; }
    const id = detail.id;
    let r; try { r = await api('/messages/reply_draft?pathway_id=' + encodeURIComponent(id)); } catch (e) { return; }
    if (selectedId !== id || !document.getElementById('ask-card')) return;
    const ta = h('textarea', { 'aria-label': t('ask_edit_label'), dir: r.language === 'ar' ? 'rtl' : 'ltr', lang: r.language, style: 'width:100%;min-height:84px;border:1px solid var(--ink);border-radius:2px;padding:12px;font-size:1rem;line-height:1.6' }, r.text);
    const status = h('div', { role: 'status', style: 'margin-top:8px;font-weight:600' });
    const chk = r.needs_check ? h('input', { type: 'checkbox', id: 'ask-chk', onchange: e => { send.disabled = !e.target.checked; } }) : null;
    const send = h('button', { class: 'btn', disabled: !!r.needs_check }, t('ask_send'));
    send.addEventListener('click', async () => {
      send.disabled = true;
      try { await api('/messages/reply', { method: 'POST', body: { pathway_id: id, text: ta.value, language: r.language, coordinator } }); sentFor = id; status.textContent = t('ask_sent'); loadList(); selectDetail(id, false); }
      catch (e) { send.disabled = false; status.textContent = e.message; }
    });
    el.append(h('div', { class: 'band warn ask-in' }, h('b', {}, t('ask_title') + ': '), `“${q}”`),
      h('div', { class: 'box', style: 'margin-bottom:16px' }, h('p', { class: 'small help', style: 'margin:0 0 8px' }, t('ask_hint')),
        h('div', { class: 'small', style: 'margin-bottom:6px' }, `${r.language_name} · ${r.engine}`), ta,
        chk ? h('label', { class: 'check', for: 'ask-chk' }, chk, t('somali_check')) : null,
        h('div', { class: 'actions' }, send), status));
  }
  function renderRecord() {
    const el = document.getElementById('record'); if (!el) return;
    clear(el);
    if (!record) return;
    el.append(h('div', { class: 'box', style: 'margin-bottom:12px' }, h('h3', {}, t('open_record')),
      h('table', { class: 't' }, h('tr', {}, h('th', {}, t('rec_time')), h('th', {}, t('rec_event')), h('th', {}, t('rec_value')), h('th', {}, t('rec_by'))),
        detail.history.map(e => h('tr', {}, h('td', {}, e.ts.replace('T', ' ').slice(0, 16)), h('td', {}, e.type), h('td', {}, (e.value || '').slice(0, 60)), h('td', {}, e.by || ''))))));
  }
  async function loadSummary(id) {
    try { const s = await api(`/pathways/${id}/summary`); const el = document.getElementById('summary'); if (el && selectedId === id) { el.textContent = s.text; el.title = t('ai_by', { e: s.engine }); } } catch (e) {}
  }
  async function loadDraft(id, slot) {
    const c = document.getElementById('draft-card'); if (c) c.replaceChildren(h('p', { class: 'muted' }, t('drafting')));
    try {
      const dr = await api('/messages/draft', { method: 'POST', body: { pathway_id: id, slot: slot || null } });
      if (selectedId !== id) return;
      draft = dr; renderDraft(); renderLane();
    } catch (e) { const c2 = document.getElementById('draft-card'); if (c2) c2.replaceChildren(h('div', { class: 'band alert' }, t('draft_failed') + ' ' + e.message)); }
  }
  function renderDraft() {
    const c = document.getElementById('draft-card'); if (!c || !draft) return;
    const d = detail, isEn = draft.language === 'en', somali = draft.language === 'so' && !draft.local_is_english;
    const ta = h('textarea', { id: 'local', readonly: true, 'aria-label': t('patient_text'), dir: draft.language === 'ar' ? 'rtl' : 'ltr', lang: draft.language, style: 'width:100%;min-height:96px;border:1px solid var(--line);border-radius:2px;padding:12px;font-size:17px;line-height:1.6;resize:vertical;background:#fff' }, draft.text_local || draft.text_en);
    const status = h('div', { role: 'status', style: 'margin-top:10px;font-weight:600' });
    const nativeChk = somali ? h('input', { type: 'checkbox', id: 'native-chk', onchange: e => { approve.disabled = !e.target.checked; } }) : null;
    const approve = h('button', { class: 'btn primary', style: 'min-height:48px', disabled: somali }, t('approve'));
    const edit = h('button', { class: 'btn', onclick: () => { ta.readOnly = false; ta.focus(); edit.disabled = true; } }, t('edit'));
    const others = (meta.coordinators[d.county] || []).filter(n => n !== coordinator);
    const toSel = h('select', { 'aria-label': t('handover_to') }, others.map(n => h('option', { value: n }, fullName(meta, n))));
    const hand = h('button', { class: 'btn' }, t('handover'));
    const called = d.alert ? h('button', { class: 'btn' }, t('i_called', { name: d.name.split(' ')[0] })) : null;
    const listen = meta.voice ? h('button', { class: 'linkbtn', onclick: async e => {
      e.currentTarget.disabled = true;
      try {
        const r = await authFetch('/api/messages/audio', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pathway_id: d.id, text: ta.value }) });
        if (!r.ok) throw new Error('x');
        const url = URL.createObjectURL(await r.blob()); await new Audio(url).play();
      } catch (err) { status.textContent = t('no_audio'); }
      e.currentTarget.disabled = false;
    } }, t('listen_patient')) : null;
    clear(c);
    const kids = [
      h('div', { style: 'display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap' }, h('span', { style: 'font-weight:600' }, t('msg_to', { name: d.name.split(' ')[0], lang: draft.language_name })), h('span', { class: 'small' }, `${t('draft_review')} · ${draft.engine}`)),
      draft.local_is_english && !isEn ? h('div', { class: 'band warn' }, t('no_translation', { lang: draft.language_name })) : null,
      somali ? h('div', { class: 'band alert', role: 'alert' }, t('somali_warn')) : null,
      draft.needs_check ? h('div', { class: 'band alert', role: 'alert' }, t('needs_check_digits')) : null,
      ta,
      isEn || draft.staff_is_english === undefined ? null : h('div', { class: 'small', style: 'margin-top:8px' }, h('b', {}, t('you_read') + ': '), draft.text_staff),
      somali ? h('label', { class: 'check', for: 'native-chk' }, nativeChk, t('somali_check')) : null,
      h('div', { class: 'small', style: 'margin-top:8px' }, t('books', { test: draft.booking.label_loc, when: draft.booking.when_loc, interp: d.interpreter ? ' · ' + t('interp_word') : '', reserved: draft.booking.reserved ? t('fdl_reserved') : '' })),
      h('div', { class: 'actions' }, approve, edit, listen), status,
      h('div', { class: 'actions', style: 'margin-top:12px;border-top:1px solid var(--line);padding-top:12px' }, called, toSel, hand)];
    c.append(h('div', { class: 'box' }, kids.filter(Boolean)));
    approve.addEventListener('click', async () => {
      approve.disabled = true; approve.textContent = t('sending');
      try {
        await api('/messages/approve', { method: 'POST', body: { pathway_id: d.id, text: ta.value, text_en: draft.text_en, language: draft.language, engine: draft.engine,
          edited: ta.value !== (draft.text_local || draft.text_en), coordinator, booking: { step: draft.booking.step, label: draft.booking.label, due: draft.booking.due, when: draft.booking.when, slot: draft.booking.slot } } });
        status.textContent = t('sent_logged', { test: draft.booking.label_loc, when: draft.booking.when_loc });
        approve.textContent = t('sent'); ta.readOnly = true; hand.disabled = true; edit.disabled = true;
        loadList(); selectDetail(d.id, false); loadSummary(d.id); loadSlots();
      } catch (e) { approve.disabled = false; approve.textContent = t('approve'); status.textContent = e.message; if (/slot/i.test(e.message)) loadDraft(d.id); }
    });
    if (called) called.addEventListener('click', async () => {
      called.disabled = true;
      try { await api(`/pathways/${d.id}/called`, { method: 'POST', body: { coordinator } }); status.textContent = t('called_logged'); loadList(); selectDetail(d.id, false); } catch (e) { called.disabled = false; status.textContent = e.message; }
    });
    hand.addEventListener('click', async () => {
      hand.disabled = true;
      try { await api('/handover', { method: 'POST', body: { pathway_id: d.id, to: toSel.value, by: coordinator, note: 'Handed over from Today' } }); status.textContent = t('handed', { name: fullName(meta, toSel.value) }); selectedId = null; detail = null; await loadList(); }
      catch (e) { hand.disabled = false; status.textContent = e.message; }
    });
  }
  const coordCounty = () => Object.entries(meta.coordinators).find(([c, ns]) => ns.includes(coordinator))[0];
  if (mode === 'coordinator') view.children[0].after(metricStrip('coordinator', () => ({ coordinator, county: coordCounty() })));
  every(loadList, 3000);
  every(() => { if (selectedId && detail && detail.id === selectedId) selectDetail(selectedId, false); }, 3000);
}
