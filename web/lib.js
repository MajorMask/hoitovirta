// Shared helpers for the web screens: DOM builder, API client (sends the staff language), language state, source links.
import { t, getLang, setLang, LANGS } from './i18n.js';

export { t, getLang, setLang, LANGS };

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'text') el.textContent = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(k));
  return el;
}
// ---- persona token (server scopes, R1): a signed token for the role chosen in "View as", sent as X-Persona-Token on every /api request.
// Patient and family tokens are bound to their own pathway. Renewed on every role change and at least hourly. It is a demo view-as mechanism, not sign-in.
let scopeOf = () => ({ role: 'all', pid: null });
export const setScopeProvider = fn => { scopeOf = fn; };
const tok = { value: null, role: null, pid: null, at: 0 };
export async function ensureToken(force) {
  const { role, pid } = scopeOf();
  if (!force && tok.value && tok.role === role && tok.pid === pid && Date.now() - tok.at < 50 * 60 * 1000) return tok.value;
  try {
    const r = await fetch('/api/persona-token', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role, pathway_id: pid || undefined }) });
    if (r.ok) { const j = await r.json(); Object.assign(tok, { value: j.token, role, pid, at: Date.now() }); }
    else { tok.value = null; }                                   // tokens disabled on this server: requests go out without one
  } catch (e) { tok.value = null; }
  return tok.value;
}
export const authHeaders = () => (tok.value ? { 'X-Persona-Token': tok.value } : {});
export const authFetch = (url, opts = {}) => fetch(url, { ...opts, headers: { ...(opts.headers || {}), ...authHeaders() } });
export async function api(path, opts = {}, retried = false) {
  const r = await fetch('/api' + path, { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json', 'X-Lang': getLang(), ...authHeaders() },
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (r.status === 401 && !retried && path !== '/persona-token') { await ensureToken(true); return api(path, opts, true); }   // expired token: renew once
  if (!r.ok) {
    let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {}
    if (r.status === 401 || r.status === 403) window.dispatchEvent(new CustomEvent('hv-denied', { detail: { status: r.status, message: m } }));
    throw new Error(m);
  }
  return r.json();
}
export const ls = {
  get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};
let timers = [];
export function every(fn, ms) { fn(); timers.push(setInterval(fn, ms)); }
export function stopPolling() { timers.forEach(clearInterval); timers = []; }
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
export const LANG = { fi: 'Finnish', sv: 'Swedish', ar: 'Arabic', so: 'Somali', ru: 'Russian', en: 'English' };

// ---- evidence: sources are small underlined links under the number they support; status is written in words -------------
const BENCH = {};
export async function loadBench() {
  if (!Object.keys(BENCH).length) Object.assign(BENCH, await api('/benchmarks'));
  return BENCH;
}
export function srcLink(e) {
  if (!e) return null;
  const word = t('st_' + e.status);
  const label = `${e.short || e.source} · ${word}`;
  const title = e.source + (e.claim ? ': ' + e.claim : '');
  return e.url ? h('a', { href: e.url, target: '_blank', rel: 'noopener', title }, label) : h('span', { title }, label);
}
export const srcs = (...es) => h('span', { class: 'srcs' }, es.filter(Boolean).filter((e, i, a) => a.findIndex(x => x.short === e.short && x.status === e.status && x.url === e.url) === i).map(srcLink));
export const synthNote = (txt) => h('span', { class: 'xs' }, txt || t('synthetic_data'));
export const fmtNum = (v, unit = '') => (v == null ? null : (Number.isInteger(v) ? v : v.toFixed(1)) + unit);
export const suppressed = () => h('span', { class: 'supp', title: t('suppressed_hint') }, t('too_few'));
export const fullName = (meta, n) => (meta.fullnames && meta.fullnames[n]) || n;

// ---- NotesDot: ONE small notes button per screen. Holds "Synthetic data", the source links that would crowd the working area,
// assumptions, and (where a risk score is shown) how it is worked out. Content: strings, DOM nodes or {head, body}. ----------------------
let notesState = null;
function renderNotes() {
  const n = notesState; if (!n) return;
  clear(n.body);
  n.sections.forEach(s => n.body.append(h('section', {}, h('h3', {}, s.head), ...[].concat(s.body).map(b => b && b.nodeType ? b : h('p', {}, b)))));
  if (n.src.size) n.body.append(h('section', {}, h('h3', {}, t('n_sources_h')), srcs(...[...n.src.values()].flat())));
}
export function noteSrc(key, ...es) {                       // register evidence for this screen's notes; shows nothing inline
  const none = document.createDocumentFragment();           // appends nothing, safe for both h() and native append()
  if (!notesState) return none;
  const list = es.filter(Boolean), sig = list.map(e => e.short + e.status + e.url).join('|'), old = notesState.src.get(key);
  if (old && old.sig === sig) return none;                  // unchanged: do not rebuild the open panel on every poll
  const arr = list.slice(); arr.sig = sig; notesState.src.set(key, arr); renderNotes(); return none;
}
export function notesDot(lines = [], opts = {}) {
  const label = opts.label || t('notes_label'), id = 'notes-' + Math.random().toString(36).slice(2, 7);
  const body = h('div', { class: 'notes-body' });
  const sections = [...(opts.synth === false ? [] : [{ head: t('n_synth_h'), body: t('n_synth') }]), ...lines.map(l => (l && l.head) ? l : { head: opts.head || label, body: l })];
  notesState = { body, sections, src: new Map() };
  const panel = h('div', { class: 'notes-panel', id, hidden: true }, body);
  const btn = h('button', { class: 'notes-btn', type: 'button', 'aria-label': label, 'aria-expanded': 'false', 'aria-controls': id, onclick: () => {
    const open = btn.getAttribute('aria-expanded') !== 'true';
    btn.setAttribute('aria-expanded', String(open)); panel.hidden = !open;
  }, onkeydown: e => { if (e.key === 'Escape') { btn.setAttribute('aria-expanded', 'false'); panel.hidden = true; } } }, h('span', { 'aria-hidden': 'true' }, 'i'));
  panel.addEventListener('keydown', e => { if (e.key === 'Escape') { btn.setAttribute('aria-expanded', 'false'); panel.hidden = true; btn.focus(); } });
  renderNotes();
  const el = h('div', { class: 'notes' + (opts.inline ? ' inline' : '') }, btn, panel);
  const slot = opts.inline ? null : document.getElementById('notes-slot');
  if (slot) { clear(slot); slot.append(el); return null; }   // lives in the header, same place on every screen
  return el;
}

// ---- role metric strip (process playbook section B): value, target, and whether it is met. Refreshes itself. ---------------------------------
export function metricStrip(role, getParams) {
  const el = h('div', { class: 'mstrip', role: 'group', 'aria-label': t('metrics_label') });
  const prev = {};
  async function load() {
    try {
      const d = await api('/rolemetrics?' + new URLSearchParams({ role, ...(getParams ? getParams() : {}) }));
      clear(el);
      d.metrics.forEach(m => {
        const val = m.id === 'top_barrier' ? (m.text ? t('bar_' + m.text) : null) : (m.value == null ? null : fmtNum(m.value, m.unit === 'd' ? ' d' : m.unit === 'pp' ? ' pp' : m.unit));
        const changed = prev[m.id] !== undefined && prev[m.id] !== val; prev[m.id] = val;
        el.append(h('div', { class: 'mcell' + (changed ? ' flash' : '') }, h('span', { class: 'mn' }, val == null ? suppressed() : val), h('span', { class: 'ml' }, t('rm_' + m.id)),
          m.target != null ? h('span', { class: 'mt ' + (m.met == null ? '' : m.met ? 'ok' : 'warn') }, `${t('target')} ${m.dir === 'ge' ? '≥' : '≤'} ${m.target}${m.unit === '%' ? ' %' : ''}${m.met == null ? '' : ' · ' + (m.met ? t('met') : t('not_met'))}`) : null,
          null));
        if (m.source) noteSrc('m_' + role + '_' + m.id, m.source);
      });
    } catch (e) {}
  }
  every(load, 6000);
  return el;
}
