// Hoitovirta web shell: header strip with roles and language links, hash routing, status, demo controls. All data is synthetic.
import { h, api, ls, clear, stopPolling, t, getLang, setLang, LANGS, setScopeProvider, ensureToken } from './lib.js';
import { fastTrack } from './fasttrack.js';
import { today } from './today.js';
import { myPath } from './mypath.js';
import { controlTower, boardPack } from './controltower.js';
import { national } from './national.js';
import { reports } from './reports.js';
import { outreach } from './outreach.js';
import { PERSONAS, persona, personaLabel, allowed, homeOf, withAs, personaPid } from './roles.js';
setScopeProvider(() => { const p = persona(); return { role: p.id, pid: p.id === 'patient' || p.id === 'family' ? personaPid(p) : null }; });

const view = document.getElementById('view');
const ROLES = [
  { id: 'fast-track', label: 'r_fast', who: 'r_fast_who', run: () => fastTrack(view) },
  { id: 'today', label: 'r_today', who: 'r_today_who', run: () => today(view) },
  { id: 'reports', label: 'r_reports', who: 'r_reports_who', run: () => reports(view) },
  { id: 'my-path', label: 'r_my', who: 'r_my_who', run: () => myPath(view) },
  { id: 'outreach', label: 'r_out', who: 'r_out_who', run: () => outreach(view) },
  { id: 'control-tower', label: 'r_ct', who: 'r_ct_who', run: () => controlTower(view) },
  { id: 'national', label: 'r_nat', who: 'r_nat_who', run: () => national(view) },
  { id: 'board', label: null, run: () => boardPack(view) },   // one-page board pack, opened from the Control Tower
];

// ---- expert view: a denser, quieter, keyboard-driven layout for people who already know the workflow. The default stays the accessible one.
const expert = () => ls.get('expert', '0') === '1';
function setExpert(on) { ls.set('expert', on ? '1' : '0'); document.body.classList.toggle('expert', on); }
document.body.classList.toggle('expert', expert());
const typing = el => el && (el.matches('input,textarea,select') || el.isContentEditable);
function closeShortcuts() { const d = document.getElementById('shortcuts'); if (d) { d.remove(); return true; } return false; }
function openShortcuts() {
  if (closeShortcuts()) return;
  const close = h('button', { class: 'btn primary', onclick: closeShortcuts }, t('sc_close'));
  document.body.append(h('div', { id: 'shortcuts', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('shortcuts_title') },
    h('div', { class: 'panel' }, h('h2', {}, t('shortcuts_title')), h('ul', { class: 'plain' }, ['sc_roles', 'sc_jk', 'sc_edit', 'sc_approve', 'sc_search', 'sc_help'].map(k => h('li', {}, t(k)))), close)));
  close.focus();
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && closeShortcuts()) return;
  if (!expert()) return;
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {            // approve and send, only when the button is enabled (so the Somali check still applies)
    const ok = document.querySelector('#draft-card .btn.primary:not(:disabled)');
    if (ok) { e.preventDefault(); ok.click(); }
    return;
  }
  if (typing(document.activeElement) || e.ctrlKey || e.metaKey || e.altKey) return;
  const rolesList = ROLES.filter(r => r.label && allowed(r.id));
  if (/^[1-7]$/.test(e.key)) { const r = rolesList[+e.key - 1]; if (r) { location.hash = '#/' + r.id; e.preventDefault(); } }
  else if (e.key === '?') { openShortcuts(); e.preventDefault(); }
  else if (e.key === '/') { const i = view.querySelector('input[type=text]'); if (i) { i.focus(); e.preventDefault(); } }
  else if (e.key === 'e') { const b = [...document.querySelectorAll('#draft-card button')].find(x => x.textContent.trim() === t('edit') && !x.disabled); if (b) { b.click(); e.preventDefault(); } }
  else if (e.key === 'j' || e.key === 'k') {
    const rows = [...view.querySelectorAll('.split > .left .wrow:not(.task)')];
    if (!rows.length) return;
    const cur = rows.findIndex(r => r.getAttribute('aria-pressed') === 'true');
    const next = rows[Math.max(0, Math.min(rows.length - 1, cur + (e.key === 'j' ? 1 : -1)))];
    if (next) { next.click(); next.scrollIntoView({ block: 'nearest' }); e.preventDefault(); }
  }
});

function renderSkip() {
  const old = document.getElementById('skip'); if (old) old.remove();
  document.body.prepend(h('a', { id: 'skip', class: 'skip', href: '#', onclick: e => { e.preventDefault(); view.focus(); view.scrollIntoView(); } }, t('skip_main')));
}
function renderHeader(active) {
  renderSkip();
  const hdr = document.getElementById('hdr');
  clear(hdr);
  document.documentElement.lang = getLang();
  const nav = h('nav', { class: 'roles', 'aria-label': t('roles_label') }, ROLES.filter(r => r.label && allowed(r.id)).map(r =>
    h('a', { href: withAs('#/' + r.id), 'aria-current': (r.id === active || (active === 'board' && r.id === 'control-tower')) ? 'page' : null }, t(r.label), h('small', {}, t(r.who)))));
  const langs = h('span', { class: 'langs', role: 'group', 'aria-label': t('language') }, LANGS.map(([code, name]) =>
    h('a', { href: '#', 'aria-current': code === getLang() ? 'true' : null, lang: code, onclick: e => { e.preventDefault(); setLang(code); route(); } }, name)));
  const expertBtn = h('button', { class: 'linkbtn', style: 'font-size:.8125rem;color:var(--muted)', 'aria-pressed': expert() ? 'true' : 'false', title: t('expert_note'),
    onclick: () => { setExpert(!expert()); renderHeader(active); renderFooter(); } }, `${t('expert_label')}: ${expert() ? t('expert_on') : t('expert_off')}`);
  const actAs = h('label', { class: 'actas', title: t('act_as_note') }, h('span', {}, t('act_as') + ':'),
    h('select', { 'aria-label': t('act_as'), onchange: e => { const p = PERSONAS.find(x => x.id === e.target.value) || PERSONAS[0]; ls.set('persona', p.id); const h2 = withAs(homeOf(p), p); if (location.hash === h2) route(); else location.hash = h2; } },
      PERSONAS.map(p => h('option', { value: p.id, selected: p.id === persona().id }, personaLabel(p)))));
  hdr.append(h('div', { class: 'hdr-top' },
    h('a', { class: 'brand', href: '#/fast-track', 'aria-label': 'Hoitovirta' }, h('img', { src: '/logo.svg', alt: '', width: '32', height: '32' }), 'Hoitovirta'),
    h('div', { class: 'right' }, h('span', { id: 'status', role: 'status', 'aria-live': 'polite' }), actAs, langs, expertBtn, h('span', { id: 'notes-slot' }))), nav);
  pollStatus();
}
async function pollStatus() {
  const el = document.getElementById('status');
  if (!el) return;
  try {
    const s = await api('/health');
    el.textContent = `${s.sim.clock === 'paused' ? t('time_paused') : t('live')} · ${t('events_n', { n: s.events.toLocaleString(getLang()) })} · ${s.backend}`;
  } catch (e) { el.textContent = t('offline'); }
}

function renderFooter() {
  const f = document.getElementById('foot');
  clear(f);
  const panel = h('details', { class: 'demo' }, h('summary', {}, t('demo_controls')));
  const out = h('div', { role: 'status', class: 'xs', style: 'margin-top:8px' });
  const clk = m => async () => { try { await api('/sim', { method: 'POST', body: { clock: m } }); out.textContent = t('clock_set', { m: t('clock_' + m) }); pollStatus(); } catch (e) { out.textContent = e.message; } };
  panel.append(h('div', { style: 'margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;align-items:center' },
    h('span', {}, t('clock') + ':'), ...['paused', 'normal', 'fast'].map(m => h('button', { class: 'linkbtn', onclick: clk(m) }, t('clock_' + m))),
    h('button', { class: 'linkbtn', onclick: async () => {
      if (!confirm(t('reset_confirm'))) return;
      out.textContent = t('reset_running');
      try { await api('/demo/reset', { method: 'POST', body: { confirm: 'reset' } }); out.textContent = t('reset_done'); route(); } catch (e) { out.textContent = e.message; }
    } }, t('reset'))), out);
  f.append(h('span', {}, t('proto_footer')), ...(expert() ? [h('button', { class: 'linkbtn', type: 'button', onclick: openShortcuts }, t('shortcuts_link'))] : []), h('a', { href: '/pulse-lab/' }, t('pulse_lab_link')), panel);
}

async function route() {
  stopPolling();
  const old = document.getElementById('denied'); if (old) old.remove();
  const id = (location.hash.replace('#/', '').split('?')[0] || 'fast-track');
  let role = ROLES.find(r => r.id === id) || ROLES[0], denied = false;
  if (!allowed(role.id)) { denied = true; const p = persona(); history.replaceState(null, '', withAs(homeOf(p))); role = ROLES.find(r => r.id === homeOf(p).replace('#/', '').split('?')[0]) || ROLES[0]; }
  document.body.dataset.as = persona().id;
  renderHeader(role.id);
  renderFooter();
  clear(view);
  await ensureToken();                                          // the first request of a screen already carries the role's token
  role.run();
  if (denied) view.before(h('div', { id: 'denied', class: 'band warn', role: 'alert' }, t('access_denied')));   // outside #view, so screens that insert after their first child keep their order
  view.focus({ preventScroll: true });
}
window.addEventListener('hv-denied', () => {                    // a 401 or 403 from the server: same quiet band as a blocked screen
  if (document.getElementById('denied')) return;
  view.before(h('div', { id: 'denied', class: 'band warn', role: 'alert' }, t('access_denied')));
});
setInterval(() => ensureToken(true), 30 * 60 * 1000);           // tokens last one hour: renew every 30 minutes
window.addEventListener('hashchange', route);
setInterval(pollStatus, 3000);
route();
