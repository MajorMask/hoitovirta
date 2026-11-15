// Demo roles ("View as"): who the viewer is acting as. 11 roles from the role views spec, plus "All (demo)".
// The role narrows the tabs and hides what the role should not see. It is a browser-side demo switch, not sign-in;
// the server scopes enforce the same table (see engine/scopes.py).
import { ls, t } from './lib.js';

export const PERSONAS = [
  { id: 'all', screens: null },
  { id: 'patient', name: 'Amina H.', who: 'role_patient', screens: ['my-path'], home: '#/my-path?id=PW-D1', mypath: 'full' },
  { id: 'family', name: 'Amina H.', who: 'role_family', screens: ['my-path'], home: '#/my-path?id=PW-D1', mypath: 'family' },
  { id: 'triage', name: 'Petra Virtanen', who: 'role_triage', screens: ['fast-track'] },
  { id: 'coordinator', name: 'Laura Niemi', who: 'role_coordinator', screens: ['today', 'fast-track', 'reports', 'my-path'], mypath: 'preview', today: 'coordinator' },
  { id: 'admin', who: 'role_admin', screens: ['today'], today: 'booking' },
  { id: 'diagnostics', who: 'role_diagnostics', screens: ['reports'] },
  { id: 'specialist', who: 'role_specialist', screens: ['today'], today: 'specialist' },
  { id: 'screening', who: 'role_screening', screens: ['outreach'] },
  { id: 'county', name: 'Petri Laine', who: 'role_county', screens: ['control-tower', 'board', 'national'] },
  { id: 'national', who: 'role_national', screens: ['national'] },
  { id: 'steward', who: 'role_steward', screens: ['reports'] },
];
const fromUrl = () => new URLSearchParams(location.hash.split('?')[1] || '').get('as');
export function persona() {
  const asParam = fromUrl();
  if (asParam && PERSONAS.some(p => p.id === asParam)) ls.set('persona', asParam);   // a link with ?as= opens the same view
  const id = ls.get('persona', 'all');
  return PERSONAS.find(p => p.id === id) || PERSONAS[0];
}
export const personaLabel = p => p.id === 'all' ? t('p_all') : (p.name ? `${p.name} · ${t(p.who)}` : t(p.who));
export const allowed = id => { const p = persona(); return !p.screens || p.screens.includes(id); };
export const homeOf = p => p.home || '#/' + (p.screens ? p.screens[0] : 'fast-track');
// keep ?as= in every in-app link so the URL itself carries the role
export function withAs(hash, p = persona()) {
  if (p.id === 'all') return hash.split('?').length > 1 ? hash.replace(/([?&])as=[^&]*&?/, '$1').replace(/[?&]$/, '') : hash;
  const [path, q] = hash.split('?'); const sp = new URLSearchParams(q || ''); sp.set('as', p.id);
  return path + '?' + sp.toString();
}

// patient and family tokens are only ever issued for the persona's own pathway
export const personaPid = p => ((p.home || '').match(/id=([^&]+)/) || [])[1] || null;
