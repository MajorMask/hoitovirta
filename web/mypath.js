// My path (patient, phone layout) + Pulse questions. A Suomi.fi / Terveyskylä-style service page: white, flat, 18px text, 56px buttons.
// The patient's language is separate from the staff language. All data is synthetic.
import { h, api, ls, every, clear, t as ts, notesDot, authFetch } from './lib.js';
import { persona, personaPid } from './roles.js';
import { ps } from './patient_strings.js';

const LOCALE = { en: 'en', fi: 'fi', sv: 'sv', ar: 'ar-u-nu-latn', so: 'so', ru: 'ru' };
const NATIVE = { fi: 'Suomeksi', sv: 'Svenska', en: 'English', ar: 'العربية', ru: 'Русский', so: 'Soomaali' };
const VOICE_AGENT_ID = 'agent_2601m7dfa0c8f9d9wryrd29bez8k';
const VOICE_LANGS = ['en', 'fi', 'sv', 'ar', 'hi', 'no'];   // the languages the phone-line agent is configured for (ElevenLabs agent language presets)
const GUIDE_LABELS = {
  en: ['What to expect', 'Example text · not clinically reviewed', 'What is happening', 'Today you can', 'Questions to ask', 'Who to call', 'Myths and facts', 'Source'],
  fi: ['Mitä odottaa', 'Esimerkkiteksti · ei kliinikon tarkistama', 'Mitä tapahtuu', 'Voit tehdä tänään', 'Kysymyksiä', 'Kehen ottaa yhteyttä', 'Myyttejä ja tietoa', 'Lähde'],
  sv: ['Vad du kan vänta dig', 'Exempeltext · inte kliniskt granskad', 'Vad händer', 'Det här kan du göra i dag', 'Frågor att ställa', 'Vem du kan kontakta', 'Myter och fakta', 'Källa'],
  ar: ['ما الذي يمكن توقعه', 'نص تجريبي · لم يراجعه مختص سريريًا', 'ما الذي يحدث', 'ما يمكنك فعله اليوم', 'أسئلة يمكنك طرحها', 'بمن تتصل', 'مفاهيم شائعة ومعلومات', 'المصدر'],
  so: ['Waxa la filan karo', 'Qoraal tusaale ah · dhakhtar ma uusan dib u eegin', 'Waxa dhacaya', 'Waxaad maanta samayn karto', 'Su’aalo la weydiin karo', 'Cidda lala xiriirayo', 'Sheekooyin iyo xaqiiqooyin', 'Isha'],
  ru: ['Чего ожидать', 'Пример текста · не проверен врачом', 'Что происходит', 'Что можно сделать сегодня', 'Что спросить', 'К кому обратиться', 'Мифы и факты', 'Источник'],
};
const tick = () => { const n = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); n.setAttribute('viewBox', '0 0 48 48'); n.setAttribute('width', '44'); n.setAttribute('height', '44'); n.setAttribute('class', 'tick'); n.setAttribute('aria-hidden', 'true');
  n.innerHTML = '<circle cx="24" cy="24" r="21"/><path d="M14 25l7 7 13-15"/>'; return n; };
const fmt = (s, vars) => (s || '').replace(/\{(\w+)\}/g, (_, k) => (vars && vars[k] != null ? vars[k] : ''));
const MIC = () => { const n = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); n.setAttribute('viewBox', '0 0 24 24'); n.setAttribute('width', '18'); n.setAttribute('height', '18'); n.setAttribute('aria-hidden', 'true');
  n.innerHTML = '<rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'; return n; };

export async function myPath(view) {
  const meta = await api('/meta');
  const hashId = new URLSearchParams((location.hash.split('?')[1] || '')).get('id');
  let pid = hashId || ls.get('patient', 'PW-D1');
  { const pp = persona(); if (pp.id === 'patient' || pp.id === 'family') pid = personaPid(pp) || pid; }   // these roles only ever see their own pathway
  let lang = null, T = null, how = 'written', data = null;
  let active = null;
  const finished = new Set();
  let slipDone = false, calledNote = false, recorder = null, callWidgetOpen = false;
  let guide = null, guideOpen = false, guideLoading = false, guideLoadedKey = '', guideIsNew = false, reminderDone = ls.get('remind_' + pid, '') === '1';

  const demo = h('div', { class: 'demo-bar' });
  const phone = h('div', { class: 'phone' });
  const body = h('div', { class: 'ph-body' }), chatBox = h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', hidden: true }), askbar = h('div', { class: 'askbar' }), pulseBox = h('div', { class: 'ph-body', style: 'border-top:1px solid var(--line);display:none', id: 'pulse' });
  const head = h('div', { class: 'ph-head' });
  phone.append(head, body, pulseBox, askbar, chatBox);
  view.append(h('div', { class: 'page-head' }, h('h1', {}, ts('r_my')), h('span', { class: 'sub' }, ts('my_sub'))), demo, phone);

  async function loadStrings(l) {
    const r = await api('/i18n/' + l);
    T = r.strings; how = r.how; lang = l;
    phone.setAttribute('dir', l === 'ar' ? 'rtl' : 'ltr'); phone.setAttribute('lang', l);
  }
  async function renderDemo() {
    let list = [];
    try { list = (await api('/patients')).patients; } catch (e) {}
    if (!list.find(p => p.id === pid)) list.unshift({ id: pid, name: pid, language: '' });
    clear(demo);
    demo.append(h('label', { for: 'who' }, ts('view_as') + ' '), h('select', { id: 'who', onchange: e => { pid = e.target.value; ls.set('patient', pid); location.hash = '#/my-path?id=' + pid; location.reload(); } },
      list.map(p => h('option', { value: p.id, selected: p.id === pid }, `${p.name}${p.language ? ' · ' + p.language : ''}`))));
  }
  function dueText(due) {
    try { return new Intl.DateTimeFormat(LOCALE[lang] || 'en', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(due)); }
    catch (e) { return due; }
  }
  let guideAt = 0;
  async function loadGuide(force) {
    const guideLang = lang || data.language || 'en', key = `${pid}:${guideLang}`;
    if (guideLoading || (!force && guideLoadedKey === key && Date.now() - guideAt < 15000)) return;
    guideLoading = true;
    try {
      const g = await api(`/mypath/${pid}/journey-guide?lang=${encodeURIComponent(guideLang)}`);
      const stageChanged = !guide || guide.stage !== g.stage;
      guide = g; guideLoadedKey = key; guideAt = Date.now();
      if (g.stage) {                                            // a stage the patient has not seen yet opens by default, once
        let seen = []; try { seen = JSON.parse(ls.get('seen_' + pid, '[]')); } catch (e) {}
        guideIsNew = !seen.includes(g.stage);
        if (guideIsNew) { guideOpen = true; seen.push(g.stage); ls.set('seen_' + pid, JSON.stringify(seen)); }
      }
      if (stageChanged || !guideOpen) render();
    }
    catch (e) { guide = { error: e.message }; }
    finally { guideLoading = false; }
  }
  async function listen(what, el) {
    el.disabled = true;
    try {
      const r = await authFetch(`/api/mypath/${pid}/audio?what=${what}&lang=${lang}`);
      if (!r.ok) throw new Error('no audio');
      const url = URL.createObjectURL(await r.blob()); const a = new Audio(url);
      a.addEventListener('ended', () => URL.revokeObjectURL(url)); await a.play();
    } catch (e) { el.after(h('span', { class: 'small', role: 'status' }, ' ' + T.no_audio)); }
    el.disabled = false;
  }
  function renderHead() {
    if (T) notesDot([T.synthetic], { synth: false, label: T.notes, head: T.notes });   // patient language, in the same header slot as every other screen
    clear(head);
    head.append(h('span', { class: 'brand' }, h('img', { src: '/logo.svg', alt: '', width: '26', height: '26' }), 'Hoitovirta'), h('span', { class: 'langs' }, Object.keys(NATIVE).map(code =>
      h('a', { href: '#', lang: code, 'aria-current': code === lang ? 'true' : null, onclick: async e => { e.preventDefault(); await loadStrings(code); ls.set('plang_' + pid, code); renderHead(); render(); renderPulse(); chatBuilt = false; localNotes = []; guideLoadedKey = ''; loadThread(); loadGuide(true); } }, NATIVE[code]))));
  }
  // ---- path ribbon: five stops in plain words, no codes, no percentages ----------------------------------------------------------------
  const STOP = { T0: 0, T1: 0, T2: 0, T3: 1, T4: 2, T5: 3, T6: 4 };
  function ribbon(d, L) {
    const cur = d.done ? 5 : (d.next ? STOP[d.next.step] ?? 0 : 0), words = ['rb_referral', 'rb_tests', 'rb_diagnosis', 'rb_plan', 'rb_treatment'];
    return h('ol', { class: 'ribbon', 'aria-label': ps(L, 'next_step') }, words.map((w, i) => h('li', { class: i < cur ? 'done' : i === cur ? 'here' : '', 'aria-current': i === cur ? 'step' : null },
      h('span', { class: 'dot', 'aria-hidden': 'true' }), h('span', { class: 'wd' }, ps(L, w)), i === cur ? h('span', { class: 'you' }, ps(L, 'here_you_are')) : null)));
  }
  let shareNote = '';
  // one gentle prompt for this moment with up to three plain links; a tap opens the guide thread with the answer
  function nudge(d, L) {
    const nurse = d.nurse_full || d.nurse || '', first = (d.nurse || nurse).split(' ')[0], place = d.place ? `${d.place}${d.unit ? ', ' + (T[d.unit] || '') : ''}` : '';
    const when = () => d.next ? (d.next.booked ? `${T[d.next.key] || ''}: ${dueText(d.next.due)}` : fmt(T.arranging, { nurse })) : T.step_T6;
    const link = (label, answer) => h('button', { class: 'linkbtn', type: 'button', onclick: () => { localNotes.push({ k: 'me', t: label }, { k: 'sys', t: answer() }); chatSig = ''; openSheet(); } }, label);
    if (COMPANION()) {                                        // one gentle prompt for this moment (from the companion), then three skills as plain links
      const go = (skill, arg, label) => { openSheet(); runSkill(skill, arg, label); };
      const m = moments[0];
      return h('div', { class: 'nudge' }, m ? h('div', { class: 'moment' }, h('b', {}, m.text), h('div', { class: 'moment-actions' }, (m.actions || []).slice(0, 2).map(a => h('button', { class: 'btn', type: 'button', onclick: () => go(a.skill, a.arg, a.label) }, a.label)))) : h('p', { class: 'small', style: 'margin:0' }, ps(L, 'nudge_intro')),
        h('button', { class: 'linkbtn', type: 'button', onclick: () => go('prepare', null, ps(L, 'sk_prepare')) }, ps(L, 'sk_prepare')),
        h('button', { class: 'linkbtn', type: 'button', onclick: () => go('write_questions', null, ps(L, 'sk_questions')) }, ps(L, 'sk_questions')),
        h('button', { class: 'linkbtn', type: 'button', onclick: () => go('worried', null, ps(L, 'sk_worried')) }, ps(L, 'sk_worried')));
    }
    return h('div', { class: 'nudge' }, h('p', { class: 'small', style: 'margin:0' }, ps(L, 'nudge_intro')),
      link(ps(L, 'q_when'), when), link(ps(L, 'q_bring'), () => ps(L, 'a_bring')), link(ps(L, 'q_how'), () => place ? `${place}.` : ps(L, 'a_none', { nurse: first })));
  }
  // ---- prep checklist for the next step: what to bring, how to get there, interpreter; "Remind me" logs a simulated SMS reminder -------------
  let prepOpen = false, prepNote = '';
  function prepCard(d, L, mode) {
    const n = d.next, nurse = d.nurse_full || d.nurse || '';
    const interp = d.interpreter ? (n.booked ? ps(L, 'interp_yes') : ps(L, 'interp_arr')) : ps(L, 'interp_no');
    const place = d.place ? `${d.place}${d.unit ? ', ' + (T[d.unit] || '') : ''}` : '';
    const det = h('details', { class: 'prep', open: prepOpen }, h('summary', { style: 'min-height:44px;display:flex;align-items:center;cursor:pointer;font-size:18px;font-weight:600' }, ps(L, 'prep_one')),
      h('p', { class: 'small', style: 'margin:0 0 8px' }, ps(L, 'prep_note')),
      h('h3', { class: 'prep-h' }, ps(L, 'bring_h')),
      h('ul', { class: 'prep-list' }, ['bring_id', 'bring_meds', 'bring_q', 'bring_person'].map(k => h('li', {}, ps(L, k)))),
      h('h3', { class: 'prep-h' }, ps(L, 'how_h')),
      h('p', { style: 'margin:0 0 4px' }, place || fmt(T.arranging, { nurse })),
      d.place ? h('a', { href: 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(d.place), target: '_blank', rel: 'noopener noreferrer' }, ps(L, 'map')) : null,
      mode === 'full' ? h('div', {}, h('button', { class: 'linkbtn', type: 'button', style: 'font-size:18px', onclick: async e => {
        const b = e.currentTarget; b.disabled = true;
        try { await sendToNurse(ps(L, 'need_ride')); prepNote = ps(L, 'sent_nurse', { nurse: (d.nurse || nurse).split(' ')[0] }); loadThread(true); } catch (err) { b.disabled = false; }
        render();
      } }, ps(L, 'need_ride'))) : null,
      h('h3', { class: 'prep-h' }, ps(L, 'interp_h')), h('p', { style: 'margin:0' }, interp),
      mode === 'full' ? h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn wide', type: 'button', disabled: reminderDone, onclick: async e => {
        const b = e.currentTarget; b.disabled = true; b.classList.add('busy');
        try {
          await api('/events', { method: 'POST', body: { pathway_id: pid, type: 'contact', value: `SMS reminder (simulated) for ${T[n.key] || n.key}${n.due ? ' at ' + n.due : ''}`, unit: 'reminder', source: 'patient-app', entered_by: 'patient' } });
          reminderDone = true; ls.set('remind_' + pid, '1'); prepNote = ps(L, 'reminded');
        } catch (err) { b.disabled = false; }
        b.classList.remove('busy'); render();
      } }, ps(L, 'remind'))) : null,
      (prepNote || (reminderDone && mode === 'full' ? ps(L, 'reminded') : '')) ? h('p', { class: 'small', role: 'status', style: 'margin:8px 0 0' }, prepNote || ps(L, 'reminded')) : null);
    det.addEventListener('toggle', () => { prepOpen = det.open; });
    return det;
  }
  let entered = false, widgetBox = null;
  function render() {
    if (!data || !T) return;
    if (!entered) { entered = true; phone.classList.add('enter'); setTimeout(() => phone.classList.remove('enter'), 1500); }
    const d = data, nurse = d.nurse_full || d.nurse || '';
    clear(body);
    const mode = persona().mypath || 'full';
    const hr = new Date().getHours(), Lg = lang || d.language || 'en';
    body.append(h('div', { class: 'greet' }, ps(Lg, hr < 11 ? 'greet_morning' : hr < 18 ? 'greet_day' : 'greet_evening', { name: d.first_name })));
    if (mode === 'family') body.append(h('div', { class: 'band' }, ps(lang || d.language || 'en', 'family_line', { name: d.first_name })));
    if (mode === 'preview') body.append(h('div', { class: 'band warn' }, ps(lang || d.language || 'en', 'preview_line')));
    if (how === 'ai') body.append(h('div', { class: 'band warn' }, ts('ai_translation')));
    const L = lang || d.language || 'en', first = (d.nurse || nurse).split(' ')[0], n = d.next;
    const sentence = guide && !guide.error && guide.what_is_happening ? guide.what_is_happening.split(/(?<=[.!?])\s/)[0] : '';
    const rn = h('section', { class: 'rn', 'aria-label': ps(L, 'right_now') }, h('div', { class: 'label' }, ps(L, 'right_now')));
    if (sentence) rn.append(h('p', { class: 'rn-sentence' }, sentence));
    if (d.done) rn.append(h('div', { class: 'big' }, T.step_T6));
    else if (n) {
      rn.append(h('div', { class: 'label nextlbl', style: 'margin-top:4px' }, ps(L, 'next_step')), h('div', { class: 'big' }, T[n.key] || n.key),
        n.booked ? h('div', { class: 'when' }, dueText(n.due)) : h('div', {}, fmt(T.arranging, { nurse })),
        d.place ? h('div', { class: 'label' }, `${ps(L, 'where')}: ${d.place}${d.unit ? ', ' + (T[d.unit] || '') : ''}`) : null);
      if (n.booked) rn.append(h('div', { class: 'reassure' }, T.reassure_booked));
    }
    if (guide && !guide.error && guide.today_you_can) rn.append(h('div', { class: 'rn-today' }, h('div', { class: 'label' }, ps(L, 'today_label')), h('div', {}, guide.today_you_can.split(/(?<=[.!?])\s/)[0])));
    if (nurse && mode !== 'preview') rn.append(h('div', { class: 'rn-call' }, h('div', { style: 'display:flex;flex-direction:column' }, h('span', { class: 'small' }, ps(L, 'your_nurse')), h('span', { style: 'font-size:20px;font-weight:600' }, nurse)),
      h('button', { class: 'btn primary', onclick: () => { calledNote = true; render(); } }, fmt(T.call_nurse, { nurse: first }))));
    if (nurse && calledNote && mode !== 'preview') rn.append(h('div', { class: 'small', role: 'status' }, fmt(T.called, { nurse })));
    if (n && n.booked && d.interpreter) rn.append(h('div', { class: 'band', style: 'margin:8px 0 0' }, T.interp_band));
    body.append(rn);
    body.append(ribbon(d, L));
    if (mode === 'full') body.append(h('div', { class: 'share' }, h('button', { class: 'linkbtn', type: 'button', onclick: async () => {
      const url = location.origin + location.pathname + '#/my-path?id=' + pid + '&as=family';
      try { await navigator.clipboard.writeText(url); } catch (e) {}
      shareNote = ps(L, 'share_done'); render();
    } }, ps(L, 'share_family')), shareNote ? h('p', { class: 'small', role: 'status', style: 'margin:4px 0 0' }, shareNote) : null));
    if (mode === 'full' && !d.done) body.append(nudge(d, L));
    if (n && !d.done) body.append(prepCard(d, L, mode));
    if (!d.done) body.append(h('div', { class: 'band support' }, T.support));
    // The voice line runs in its own iframe: closing the panel removes the iframe, which ends the microphone session and the call at once
    // (the bare widget kept the call running until the page was reloaded). Languages the agent does not speak are not sent as an override.
    const callWidgetBtn = h('button', { class: 'linkbtn', style: 'font-size:18px;min-height:56px;text-align:left', 'aria-expanded': String(callWidgetOpen), onclick: () => {
      callWidgetOpen = !callWidgetOpen; if (!callWidgetOpen) widgetBox = null; render();
    } }, callWidgetOpen ? `${ps(L, 'close')} · ${T.call}` : `${T.call} · Hoitovirta`);
    if (mode === 'full') body.append(callWidgetBtn);
    if (mode === 'full' && callWidgetOpen) {
      if (!widgetBox) {                                          // built once per opening: a redraw of the page must not restart a call in progress
        const esc = x => String(x).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        const vars = esc(JSON.stringify({ pathway_id: pid, moment: d.pulse?.moment || '', language: lang }));
        const ovl = VOICE_LANGS.includes(lang) ? ` override-language="${esc(lang)}"` : '';
        const doc = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%;background:#fff}</style></head><body><elevenlabs-convai agent-id="${VOICE_AGENT_ID}"${ovl} dynamic-variables="${vars}"></elevenlabs-convai><script src="https://unpkg.com/@elevenlabs/convai-widget-embed" async type="text/javascript"><\/script></body></html>`;
        widgetBox = h('div', { class: 'voicebox' }, h('iframe', { title: `${T.call} · Hoitovirta`, allow: 'microphone', srcdoc: doc }));
      }
      body.append(widgetBox);
    }
    if (mode !== 'family' && d.message && d.message.text) {
      body.append(h('div', { class: 'card', style: 'flex-direction:column;align-items:flex-start' }, h('span', { class: 'small' }, fmt(T.message, { nurse: d.message.nurse || nurse })),
        h('div', { class: 'msgtext', dir: d.message.language === 'ar' ? 'rtl' : 'ltr', lang: d.message.language }, d.message.text),
        meta.voice ? (() => { const b = h('button', { class: 'linkbtn' }, T.listen_link); b.addEventListener('click', () => listen('message', b)); return b; })() : null));
    }
    const labels = GUIDE_LABELS[lang || d.language] || GUIDE_LABELS.en;
    const guideBody = h('div', { class: 'ph-body', style: 'padding:12px 0' });
    const guideDetails = h('details', { open: guideOpen, style: 'border-top:1px solid var(--line);padding:12px 0' },
      h('summary', { style: 'min-height:44px;display:flex;align-items:center;gap:10px;cursor:pointer;font-size:18px;font-weight:600' }, labels[0], guideIsNew ? h('span', { class: 'small', style: 'font-weight:400' }, ps(L, 'new_stage')) : null), guideBody);
    guideDetails.addEventListener('toggle', () => { guideOpen = guideDetails.open; guideIsNew = false; });
    if (guide) {
      if (guide.error) guideBody.append(h('div', { class: 'band alert' }, guide.error));
      else {
        guideBody.append(h('div', { class: 'small' }, guide.review_status || labels[1]));
        if (guide.translation_label) guideBody.append(h('div', { class: 'band warn', style: 'margin:8px 0' }, guide.translation_label));
        const blocks = [[labels[2], guide.what_is_happening], [labels[3], guide.today_you_can], [labels[4], guide.ask_these], [labels[5], guide.who_to_call], [labels[6], (guide.myths || []).map(x => `${x.myth} ${x.fact}`).join(' ' )]];
        blocks.forEach(([title, value]) => guideBody.append(h('h3', { style: 'font-size:18px;margin:12px 0 4px' }, title),
          Array.isArray(value) ? h('ul', {}, value.map(x => h('li', {}, x))) : h('p', {}, value)));
        guideBody.append(h('p', { class: 'small' }, labels[7] + ': ', h('a', { href: guide.source_url, target: '_blank', rel: 'noopener noreferrer' }, guide.source_name)));
      }
    } else if (guideLoading) guideBody.append(h('p', { class: 'small', role: 'status' }, T.wait));
    body.append(guideDetails);
    if (!d.done && mode === 'full') {
      body.append(h('button', { class: 'btn wide', disabled: slipDone || d.slipped, onclick: async e => {
        e.currentTarget.disabled = true;
        try { await api(`/mypath/${pid}/slip`, { method: 'POST' }); slipDone = true; render(); } catch (err) { e.currentTarget.disabled = false; }
      } }, T.slipped));
      if (slipDone || d.slipped) body.append(h('div', { class: 'band', role: 'status' }, fmt(T.slip_done, { nurse })));
    }
  }


  // ---- Ask your nurse: a written thread with the nurse. The AI never answers; a person reads and replies. -------------------------------
  let shown = 0, chat = { items: [], waiting: false }, chatSig = '', composer = null, localNotes = [], urgentShown = false, chatBuilt = false;
  let moments = [], momentsAt = 0, pendingWord = false, urgentEl = null;
  // ---- companion skills: guided taps (prepare, plain words, my questions, tell my family, I am worried, my notes, after the visit) ------------------
  const SKILLS = [['prepare', 'sk_prepare'], ['explain_word', 'sk_words'], ['write_questions', 'sk_questions'], ['tell_family', 'sk_family'], ['worried', 'sk_worried'], ['notes', 'sk_notes']];
  async function runSkill(skill, arg, label) {
    const L = lang || data.language || 'en';
    if (skill === 'family_link') {                                // the family link is made in the browser: it only carries the pathway id and the role
      const url = location.origin + location.pathname + '#/my-path?id=' + pid + '&as=family';
      try { await navigator.clipboard.writeText(url); } catch (e) {}
      localNotes.push({ k: 'sys', t: ps(L, 'share_done') }); chatSig = ''; renderThread(); return;
    }
    if (skill === 'explain_word' && !arg) {                       // ask which word, then the next message is the word
      pendingWord = true; localNotes.push({ k: 'me', t: label || ps(L, 'sk_words') }, { k: 'sys', t: ps(L, 'words_prompt') });
      if (composer) composer.placeholder = ps(L, 'words_ph'); chatSig = ''; renderThread(); if (composer) composer.focus(); return;
    }
    if (label) localNotes.push({ k: 'me', t: label });
    localNotes.push({ k: 'sys', t: ps(L, 'waiting_ai') }); chatSig = ''; renderThread();
    const pending = localNotes[localNotes.length - 1];
    try {
      const r = await api(`/mypath/${pid}/companion`, { method: 'POST', body: { skill, arg: arg || undefined, language: L } });
      localNotes.splice(localNotes.indexOf(pending), 1);
      if (r.escalate === 'emergency' && urgentEl) urgentEl.style.display = '';
      localNotes.push({ k: 'ai', t: r.reply, q: label || arg || skill, need: r.need_suggestion || null, call: (r.offer_buttons || []).includes('call_nurse'), cards: r.cards || [], follow: r.follow_ups || [], saveNote: r.save_note || null, mt: r.language_note || null, advisory: !!r.advisory });
    } catch (e) { localNotes.splice(localNotes.indexOf(pending), 1); localNotes.push({ k: 'sys', t: e.message }); }
    chatSig = ''; renderThread();
  }
  async function loadMoments() {
    if (!COMPANION() || Date.now() - momentsAt < 15000) return;
    momentsAt = Date.now();
    try {
      const r = await api(`/mypath/${pid}/companion/moments?language=${encodeURIComponent(lang || data.language || 'en')}`), next = (r.cards || []).filter(c => c.kind !== 'quiet');
      if (JSON.stringify(next) !== JSON.stringify(moments)) { moments = next; render(); }
    } catch (e) {}
  }
  function skillCards(n, L) {                                   // cards from a skill: checklist, questions, draft to share, steps, definition
    const box = h('div', { class: 'skillcards' });
    (n.cards || []).forEach(c => {
      const body = c.kind === 'draft' ? h('p', { class: 'draft', dir: 'auto' }, (c.items || [])[0] || '')
        : c.kind === 'definition' ? h('p', {}, (c.items || [])[0] || '')
        : h(c.kind === 'questions' ? 'ol' : 'ul', {}, (c.items || []).map(x => h('li', { dir: 'auto' }, x)));
      const card = h('div', { class: 'skillcard ' + c.kind }, h('div', { class: 'sc-title' }, c.title), body);
      if (c.kind === 'draft') card.append(h('button', { class: 'linkbtn', type: 'button', onclick: async e => { try { await navigator.clipboard.writeText((c.items || [])[0] || ''); e.currentTarget.textContent = ps(L, 'copied'); } catch (x) {} } }, ps(L, 'copy')));
      box.append(card);
    });
    return box;
  }
  const stamp = iso => { try { return new Intl.DateTimeFormat(LOCALE[lang] || 'en', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(iso)); } catch (e) { return ''; } };
  const MARK = () => { const n = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); n.setAttribute('viewBox', '0 0 24 12'); n.setAttribute('width', '24'); n.setAttribute('height', '12'); n.setAttribute('class', 'pathmark'); n.setAttribute('aria-hidden', 'true');
    n.innerHTML = '<path d="M2 8c4-6 8 4 12-2s6-2 8-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'; return n; };
  function bubble(kind, text, meta2) {
    const L = lang || (data && data.language) || 'en';
    const who = kind === 'me' ? T.chat_you : kind === 'nurse' ? h('span', {}, (meta2 && meta2.name) || '', h('span', { class: 'tag' }, ps(L, 'nurse_tag'))) : kind === 'ai' ? MARK() : '';
    return h('div', { class: 'bubble ' + kind }, h('div', { class: 'who' }, who), h('div', { class: 'txt', dir: 'auto' }, text), meta2 && meta2.when ? h('div', { class: 'when' }, meta2.when) : null, meta2 && meta2.actions ? meta2.actions : null);
  }
  function renderThread() {
    const list = chatBox.querySelector('.thread'); if (!list) return;
    const nurse = (data.nurse_full || data.nurse || '');
    const sig = JSON.stringify([chat.items.map(i => i.ts + i.who), chat.waiting, localNotes.length, lang]);
    if (sig === chatSig) return; chatSig = sig;
    const nearEnd = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    clear(list); const prevShown = shown;
    if (!chat.items.length && !localNotes.length) list.append(h('p', { class: 'small', style: 'margin:0' }, T.chat_empty));
    chat.items.forEach(i => list.append(bubble(i.who === 'patient' ? 'me' : 'nurse', i.text, { name: i.nurse ? (nurse && nurse.split(' ')[0] === i.nurse ? nurse : i.nurse) : nurse, when: stamp(i.ts) })));
    const L2 = lang || data.language || 'en';
    localNotes.forEach(n => {
      if (n.k !== 'ai') return list.append(bubble(n.k, n.t));
      const first2 = (data.nurse || '').split(' ')[0], sent = () => { n.sent = true; localNotes.push({ k: 'sys', t: ps(L2, 'sent_nurse', { nurse: first2 }) }); chatSig = ''; return loadThread(true); };
      const acts = h('div', { class: 'ai-actions' });
      if (n.need && !n.sent) {                                  // the companion thinks a person should help: only the patient's tap creates the task
        acts.append(h('button', { class: 'btn', type: 'button', onclick: async e => {
          e.currentTarget.disabled = true;
          try { await api(`/mypath/${pid}/companion/confirm`, { method: 'POST', body: { need: n.need } }); await sent(); }
          catch (err) { try { await sendToNurse(n.q); await sent(); } catch (e2) { e.currentTarget.disabled = false; } }   // confirm not available: the question still reaches the nurse
        } }, ps(L2, 'yes_ask_nurse')));
      } else if (!n.sent) {
        acts.append(h('button', { class: 'linkbtn', type: 'button', onclick: async e => { e.currentTarget.disabled = true; try { await sendToNurse(n.q); await sent(); } catch (err) { e.currentTarget.disabled = false; } } }, ps(L2, 'send_nurse')));
      }
      if (n.call) acts.append(h('span', { class: 'small' }, ' ' + fmt(T.call_nurse, { nurse: first2 })));
      if (n.saveNote && !n.saved) acts.append(h('button', { class: 'linkbtn', type: 'button', onclick: async e => { e.currentTarget.disabled = true; try { await api(`/mypath/${pid}/notes`, { method: 'POST', body: { text: n.saveNote.text, share: false } }); n.saved = true; localNotes.push({ k: 'sys', t: ps(L2, 'note_saved') }); chatSig = ''; renderThread(); } catch (err) { e.currentTarget.disabled = false; } } }, ps(L2, 'save_note')));
      (n.follow || []).slice(0, 3).forEach(f => acts.append(h('button', { class: 'skillbtn small', type: 'button', onclick: () => runSkill(f.skill, f.arg, f.label) }, f.label)));
      const extra = h('div', {}, n.cards && n.cards.length ? skillCards(n, L2) : null, n.advisory ? h('div', { class: 'band warn', role: 'status' }, ps(L2, 'advisory_note')) : null, n.mt ? h('p', { class: 'small', style: 'margin:4px 0 0' }, ps(L2, 'mt_machine')) : null, acts);
      list.append(bubble('ai', n.t, { actions: extra }));
    });
    [...list.querySelectorAll('.bubble:not(.waiting)')].forEach((b, i) => { if (i >= prevShown && prevShown > 0) b.classList.add('new'); });
    shown = list.querySelectorAll('.bubble:not(.waiting)').length;
    if (chat.waiting) list.append(h('div', { class: 'bubble sys waiting', role: 'status' }, h('span', {}, fmt(T.chat_waiting, { nurse: (data.nurse || nurse).split(' ')[0] })), h('span', { class: 'dots', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'))));
    const lastAi = [...list.querySelectorAll('.bubble.ai')].pop(), lastNote = localNotes[localNotes.length - 1];
    if (lastAi && lastNote && lastNote.k === 'ai') list.scrollTop = Math.max(0, lastAi.offsetTop - list.offsetTop - 6);   // a fresh answer: start reading at its top
    else if (nearEnd || chat.items.length) list.scrollTop = list.scrollHeight;
  }
  // One Ask panel. With the AI companion online (meta.companion), its short answer comes first with a "Send to my nurse" button; without it, the
  // text goes straight to the nurse. Human replies always arrive in the same thread. The AI never replaces a person.
  const COMPANION = () => meta.companion === true || ls.get('companion', '') === '1';   // the localStorage switch is for testing the UI before the backend is up
  async function sendToNurse(text) { return api(`/mypath/${pid}/question`, { method: 'POST', body: { text } }); }
  let barFor = '';
  function renderBar() {
    const mode = persona().mypath || 'full';
    if (mode !== 'full' || !T || !data) { askbar.style.display = 'none'; return; }
    const L = lang || data.language || 'en', key = L + (data.nurse || '');
    askbar.style.display = '';
    if (key === barFor) return; barFor = key; clear(askbar);
    askbar.append(h('button', { class: 'askbar-field', type: 'button', 'aria-haspopup': 'dialog', onclick: () => openSheet() }, ps(L, 'ask_bar')));
  }
  function openSheet() {
    if (!chatBuilt) buildChat();
    chatBox.hidden = false; document.body.classList.add('noscroll'); chatSig = ''; renderThread();
    setTimeout(() => { if (composer) composer.focus(); }, 30);
  }
  function closeSheet() { chatBox.hidden = true; document.body.classList.remove('noscroll'); const f = askbar.querySelector('.askbar-field'); if (f) f.focus(); }
  chatBox.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeSheet(); } });
  function buildChat() {
    const mode = persona().mypath || 'full';
    if (!T || !data) return;
    if (mode !== 'full') { clear(chatBox); chatBuilt = true; return; }   // family and preview: no writing
    const L = lang || data.language || 'en', nurse = data.nurse_full || data.nurse || '', first = (data.nurse || nurse).split(' ')[0];
    clear(chatBox); chatBuilt = true; chatSig = ''; shown = 0;
    const ta = h('textarea', { id: 'chat-in', 'aria-label': ps(L, 'ask_bar'), placeholder: T.chat_ph, maxlength: '500', rows: '3', class: 'chat-in' });
    const urgent = h('div', { class: 'band alert', role: 'alert', style: 'display:none' }, T.chat_urgent); urgentEl = urgent;
    const send = h('button', { class: 'btn primary wide', type: 'button' }, T.chat_send);
    async function submit() {
      const text = ta.value.trim(); if (!text) return;
      if (pendingWord) { pendingWord = false; ta.value = ''; ta.placeholder = T.chat_ph; await runSkill('explain_word', text, text); return; }
      send.disabled = true; send.classList.add('busy');
      try {
        if (COMPANION()) {
          localNotes.push({ k: 'me', t: text }); chatSig = ''; renderThread(); ta.value = '';
          try {
            const r = await api(`/mypath/${pid}/companion`, { method: 'POST', body: { text, language: L } });
            if (r.escalate === 'emergency') urgent.style.display = '';          // red band with 112; the reply itself is the fixed safety redirect
            localNotes.push({ k: 'ai', t: r.reply, q: text, need: r.need_suggestion || null, call: (r.offer_buttons || []).includes('call_nurse') });
          } catch (e) {                                          // companion offline: the question goes to the nurse, as before
            const q = await sendToNurse(text); if (q.urgent) urgent.style.display = '';
            localNotes.push({ k: 'sys', t: fmt(T.chat_received, { nurse: first }) }); await loadThread(true);
          }
          chatSig = ''; renderThread();
        } else {
          const r = await sendToNurse(text);
          ta.value = ''; localNotes.push({ k: 'sys', t: fmt(T.chat_received, { nurse: first }) });
          if (r.urgent) urgent.style.display = '';
          await loadThread(true);
        }
      } catch (e) { localNotes.push({ k: 'sys', t: e.message }); chatSig = ''; renderThread(); }
      send.disabled = false; send.classList.remove('busy');
    }
    send.addEventListener('click', submit);
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); } });
    composer = ta;
    chatBox.setAttribute('aria-label', ps(L, 'guide_title'));
    chatBox.append(h('div', { class: 'sheet-head' }, h('div', {}, h('h2', {}, ps(L, 'guide_title')), COMPANION() ? h('span', { class: 'aichip' }, ps(L, 'ai_chip')) : null),
        h('button', { class: 'btn', type: 'button', onclick: closeSheet }, ps(L, 'close'))),
      h('div', { class: 'sheet-nurse' }, h('div', { style: 'display:flex;flex-direction:column' }, h('span', { class: 'small' }, ps(L, 'your_nurse')), h('b', {}, nurse)),
        h('button', { class: 'btn primary', type: 'button', onclick: () => { calledNote = true; closeSheet(); render(); } }, fmt(T.call_nurse, { nurse: first }))),
      COMPANION() ? h('div', { class: 'skills', role: 'group', 'aria-label': ps(L, 'skills_h') }, [...SKILLS, ...(moments.some(m => (m.actions || []).some(a => a.skill === 'after_visit')) ? [['after_visit', 'sk_after']] : [])].map(([sk, key]) => h('button', { class: 'skillbtn', type: 'button', onclick: () => runSkill(sk, null, ps(L, key)) }, ps(L, key)))) : null,
      h('div', { class: 'thread', role: 'log', 'aria-live': 'polite', 'aria-label': ps(L, 'guide_title') }), urgent, ta, send, h('p', { class: 'small', style: 'margin:0' }, T.chat_urgent));
    if (COMPANION()) notesDot([T.synthetic, ps(L, 'ask_ai')], { synth: false, label: T.notes, head: T.notes });
    renderThread();
  }
  async function loadThread(force) {
    try { chat = await api(`/mypath/${pid}/thread`); } catch (e) { return; }
    if (!chatBuilt) buildChat(); else renderThread();
    renderBar();
  }

  // ---- Pulse (the check-in): two questions, tap or voice, AI converts, the patient confirms ----------------------------------
  function optLabel(item, key) { return /^PU(7|9)$/.test(item) ? key : (T[`opt_${item}_${key}`] || key); }
  async function answer(item, value, channel, confidence) {
    active.stage = 'saving'; renderPulse();
    try {
      await api('/pulse', { method: 'POST', body: { pathway_id: pid, item, value, language: lang, channel, moment: active.moment, confidence: confidence ?? null } });
      if (item === 'PU7' && Number(value) >= 4) active.worry = true;
      const followUp = active.conditional?.[item]?.[value];
      if (followUp) active.items.splice(active.i + 1, 0, { item: followUp, kind: 'choice', options: ['yes', 'no'] });
      active.i += 1; active.stage = active.i >= active.items.length ? 'done' : 'ask'; active.proposal = null;
      if (active.stage === 'done') { finished.add(active.moment); poll(); }
    } catch (e) { active.stage = 'ask'; }
    renderPulse();
  }
  async function toggleRecord(it) {
    if (recorder) { recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [], rec = new MediaRecorder(stream);
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach(x => x.stop()); recorder = null; active.stage = 'hearing'; renderPulse();
        try {
          const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
          const r = await authFetch(`/api/pulse/voice?pathway_id=${pid}&item=${it.item}&lang=${lang}`, { method: 'POST', headers: { 'Content-Type': blob.type }, body: blob });
          const j = await r.json();
          if (!r.ok || !j.value) { active.stage = 'ask'; active.note = T.try_tap; } else { active.stage = 'confirm'; active.proposal = j; }
        } catch (e) { active.stage = 'ask'; active.note = T.try_tap; }
        renderPulse();
      };
      recorder = rec; rec.start(); active.stage = 'listening'; renderPulse();
      setTimeout(() => { if (recorder === rec) rec.stop(); }, 12000);
    } catch (e) { active.note = T.try_tap; renderPulse(); }
  }
  function renderPulse() {
    clear(pulseBox);
    if (!active || !T) { pulseBox.style.display = 'none'; return; }
    pulseBox.style.display = '';
    if (active.stage === 'done') {
      pulseBox.append(tick(), h('div', { class: 'qtext', role: 'status' }, T.thanks), h('div', {}, fmt(active.worry ? T.thanks_worry : T.thanks_sub, { nurse: (data.nurse || '').split(' ')[0] })),
        h('button', { class: 'btn wide', onclick: () => { active = null; renderPulse(); } }, T.done));
      return;
    }
    const it = active.items[active.i];
    pulseBox.append(h('div', { class: 'label' }, fmt(T.q_progress, { a: active.i + 1, b: active.items.length })), h('div', { class: 'qtext', id: 'pq' }, T['q_' + it.item]));
    if (active.stage === 'confirm') {
      const p = active.proposal;
      pulseBox.append(h('div', { class: 'heard' }, fmt(T.heard, { heard: p.transcript })), h('div', { style: 'font-size:22px;font-weight:700' }, optLabel(it.item, p.value)), h('div', {}, T.is_right),
        h('div', { class: 'opts' }, h('button', { class: 'btn primary', style: 'text-align:center', onclick: () => answer(it.item, p.value, 'voice', p.confidence) }, T.yes),
          h('button', { class: 'btn', onclick: () => { active.stage = 'ask'; active.proposal = null; renderPulse(); } }, T.no)));
    } else if (active.stage === 'saving' || active.stage === 'hearing') {
      pulseBox.append(h('div', { role: 'status' }, T.wait));
    } else if (it.kind === 'text') {
      const input = h('textarea', { class: 'input', maxlength: '500', rows: '3', placeholder: T.pulse_text_ph, 'aria-label': T['q_' + it.item] });
      pulseBox.append(input,
        h('button', { class: 'btn primary wide', onclick: () => { if (input.value.trim()) answer(it.item, input.value.trim(), 'app', null); } }, T.pulse_submit),
        h('button', { class: 'btn wide', onclick: () => answer(it.item, 'skip', 'app', null) }, T['opt_' + it.item + '_skip']));
      if (meta.voice) {
        const a = h('button', { class: 'linkbtn', style: 'display:flex;align-items:center;gap:8px;font-size:18px', 'aria-pressed': active.stage === 'listening' ? 'true' : 'false' }, MIC(), active.stage === 'listening' ? T.listening : T.speak_link);
        a.addEventListener('click', () => toggleRecord(it)); pulseBox.append(a);
      }
    } else {
      pulseBox.append(h('div', { class: it.kind === 'scale' ? 'opts scale' : 'opts' }, it.options.map(k => h('button', { class: 'btn', onclick: () => answer(it.item, k, 'app', null) }, optLabel(it.item, k)))));
      if (meta.voice) {
        const a = h('button', { class: 'linkbtn', style: 'display:flex;align-items:center;gap:8px;font-size:18px', 'aria-pressed': active.stage === 'listening' ? 'true' : 'false' }, MIC(), active.stage === 'listening' ? T.listening : T.speak_link);
        a.addEventListener('click', () => toggleRecord(it)); pulseBox.append(a);
      }
      if (active.note) pulseBox.append(h('div', { class: 'small', role: 'status' }, active.note));
      pulseBox.append(h('div', { class: 'small' }, T.privacy));
    }
  }
  let lastSig = '';
  async function poll() {
    try {
      const nd = await api('/mypath/' + pid), sig = JSON.stringify(nd), changed = sig !== lastSig; lastSig = sig; data = nd;
      if (!T) { await loadStrings(ls.get('plang_' + pid, data.language)); renderHead(); }
      if (changed || !body.firstChild) render();                  // redraw only when something changed: the voice widget and the reader's place stay put
      const pm = persona().mypath || 'full';
      if (pm === 'full') loadThread();                             // thread: patient only (the server refuses it to other roles)
      if (pm !== 'family') loadGuide();
      if (pm === 'full') loadMoments();                            // family gets the reduced next-step view only
      if ((persona().mypath || 'full') === 'full' && !active && data.pulse && !finished.has(data.pulse.moment)) { active = { moment: data.pulse.moment, items: data.pulse.items, conditional: data.pulse.conditional || {}, i: 0, stage: 'ask', proposal: null, note: null }; renderPulse(); }
    } catch (e) { clear(body); body.append(h('div', { class: 'band alert' }, ts('load_failed') + ' ' + e.message)); }
  }
  renderDemo();
  every(poll, 3000);
}
