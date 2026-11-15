const $=id=>document.getElementById(id);
let language='fi', instrument=null, staffMode=false, screeningMode=false;
const demoCase='DEMO-PULSE-01';
const copyKeys=['name','title','intro','q4','q7','scale','yes','unsure','no','thanks','call','clarify','ok','submit','again','foot','staff','empty','open','closed','close','source','privacy'];

async function loadInstrument(){
  const res=await fetch(`api/instrument?language=${language}`);
  if(!res.ok) throw new Error('instrument unavailable');
  instrument=await res.json();
  draw();
}

function draw(){
  const c=instrument.copy;
  document.documentElement.lang=language;
  $('title').textContent=c.title;$('intro').textContent=c.intro;$('q4').textContent=c.q4;$('q7').textContent=c.q7;$('scale').textContent=c.scale;$('proto-tag').textContent=language==='fi'?'ESIMERKKI · SYNTEETTINEN DATA':language==='sv'?'EXEMPEL · SYNTETISKA DATA':'DEMO · SYNTHETIC DATA';$('privacy').textContent=c.privacy;$('submit').textContent=c.submit;$('footer-copy').textContent=c.foot;
  $('step-text').textContent=language==='fi'?'Kysymys 1 / 2 · noin 20 sekuntia':language==='sv'?'Fråga 1 av 2 · cirka 20 sekunder':'Question 1 of 2 · about 20 seconds';
  $('scale-low').textContent=language==='fi'?'Ei lainkaan':language==='sv'?'Inte alls':'Not at all';$('scale-high').textContent=language==='fi'?'Erittäin':language==='sv'?'Mycket':'Extremely';
  $('threshold-note').textContent=language==='fi'?`Huolipiste ${instrument.distress_cutoff} tai enemmän luo mock-pyynnön hoitajan yhteydenotosta tänään tai seuraavana arkipäivänä.`:language==='sv'?`Oropoäng ${instrument.distress_cutoff} eller högre skapar en testbegäran om kontakt från sjuksköterskan i dag eller nästa vardag.`:`A worry score of ${instrument.distress_cutoff} or higher creates a mock request for a nurse call today or the next working day.`;
  $('source-label').textContent=c.source+':';$('patient-source-link').href=instrument.distress_source;$('patient-source-link').textContent=language==='fi'?'NCCN Distress Thermometer':language==='sv'?'NCCN Distresstermometer':'NCCN Distress Thermometer';
  $('choices4').innerHTML=[['yes',c.yes],['unsure',c.unsure],['no',c.no]].map(([v,label])=>`<label class="choice"><input type="radio" name="PU4" value="${v}" required><span>${label}</span></label>`).join('');
  $('scale-options').innerHTML=Array.from({length:11},(_,i)=>`<label><input type="radio" name="PU7" value="${i}" ${i===0?'required':''}><span>${i}</span></label>`).join('');
  $('source-link').href=instrument.distress_source;$('source-link').textContent=language==='fi'?'Lähde: NCCN DT':language==='sv'?'Källa: NCCN DT':'Source: NCCN DT';
  $('staff-toggle').textContent=staffMode?c.name==='Suomi'?'Potilasnäkymä':c.name==='Svenska'?'Patientvy':'Patient view':language==='fi'?'Hoitotiimin näkymä':language==='sv'?'Vårdteamets vy':'Care-team view';
  $('patient-view').hidden=staffMode||screeningMode;$('staff-view').hidden=!staffMode;$('screening-view').hidden=staffMode||!screeningMode;
  $('screening-toggle').textContent=screeningMode?(language==='fi'?'Takaisin kyselyyn':language==='sv'?'Tillbaka till enkäten':'Back to the survey'):(language==='fi'?'Tulevat ilmaiset seulonnat':language==='sv'?'Kommande gratis screening':'Upcoming free screening');
  if(screeningMode&&!staffMode&&window.drawScreening) window.drawScreening(language);
  if(staffMode) loadQueue();
}

async function loadQueue(){
  const res=await fetch(`api/feedback?language=${language}`);const data=await res.json();
  $('staff-title').textContent=data.copy.staff;
  $('staff-subtitle').textContent=language==='fi'?`Vastauksia tässä mockissa: ${data.response_count} · avoimia pyyntöjä: ${data.open_task_count}`:language==='sv'?`Svar i testet: ${data.response_count} · öppna begäranden: ${data.open_task_count}`:`Mock responses: ${data.response_count} · open requests: ${data.open_task_count}`;
  const hiddenText=language==='fi'?'Kukin mittari näytetään vasta, kun vastauksia on vähintään viisi.':language==='sv'?'Varje mått visas först när minst fem svar finns.':'Each measure is shown only after at least five answers.';
  const metrics=data.metrics;
  const labels={
    informed_share_pct:language==='fi'?'Tietää seuraavan vaiheen':language==='sv'?'Vet vad nästa steg är':'Knows what happens next',
    distress_at_or_above_cutoff_share_pct:language==='fi'?`Huolipiste vähintään ${metrics?.distress_cutoff||4}`:language==='sv'?`Oropoäng minst ${metrics?.distress_cutoff||4}`:`Worry score at or above ${metrics?.distress_cutoff||4}`,
    nps:language==='fi'?'Suosittelisi hoitoa (pisteet -100…100)':language==='sv'?'Skulle rekommendera vården (poäng -100…100)':'Would recommend care (score -100 to 100)',
    reached_1wd_pct:language==='fi'?'Tavoitti hoitajan 1 arkipäivässä':language==='sv'?'Nådde sjuksköterskan inom 1 vardag':'Reached nurse within 1 working day'
  };
  const available=metrics?Object.keys(labels).filter(key=>metrics[key]!==null):[];
  $('metrics').innerHTML=available.length?available.map(key=>`<div class="metric"><strong>${metrics[key]}${key==='nps'?'':'%'}</strong><span>${labels[key]} · ${metrics[key==='informed_share_pct'?'informed_respondents':key==='distress_at_or_above_cutoff_share_pct'?'distress_respondents':key==='nps'?'nps_respondents':'reached_1wd_respondents']} ${language==='fi'?'vastausta':language==='sv'?'svar':'responses'}</span></div>`).join(''):`<p class="suppressed-note">${hiddenText}</p>`;
  const open=data.tasks.filter(t=>t.status==='open');
  $('queue').innerHTML=open.length?open.map(t=>`<article class="task"><div><strong>${data.copy.open}</strong><p>${t.demo_case} · ${t.language.toUpperCase()} · ${t.signals.map(s=>({distress_follow_up:'Worry follow-up',clarify_next_step:'Explain the next step',nurse_not_reached_within_1_working_day:'Contact the person',screening_barrier:'Remove a barrier to screening',explain_free_screening:'Explain that screening is free',offer_help:'Offer help to attend'}[s]||s)).join(' + ')}</p><p>${t.due==='today_or_next_working_day'?'Today or next working day':'Care-team review'} · Synthetic case</p></div><button data-task="${t.id}">${data.copy.close}</button></article>`).join(''):`<p class="empty">${data.copy.empty}</p>`;
  $('queue').querySelectorAll('[data-task]').forEach(button=>button.addEventListener('click',async()=>{await fetch(`api/feedback/${button.dataset.task}/complete`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({done:true})});await loadQueue();}));
}

$('language').addEventListener('change',async e=>{language=e.target.value;await loadInstrument();});
$('staff-toggle').addEventListener('click',()=>{staffMode=!staffMode;if(staffMode)screeningMode=false;draw();});
$('screening-toggle').addEventListener('click',()=>{screeningMode=!screeningMode;staffMode=false;draw();});
$('survey').addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget;const submit=$('submit');submit.disabled=true;
  const data=new FormData(form);
  try{
    const res=await fetch('api/responses',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({demo_case:demoCase,language,moment:'suspicion',channel:'app',PU4:data.get('PU4'),PU7:Number(data.get('PU7'))})});
    const out=await res.json();if(!res.ok)throw new Error(out.detail||'Could not save');
    $('survey').hidden=true;const result=$('result');result.hidden=false;result.classList.toggle('alert',out.response.signals.length>0);result.innerHTML=`<strong>${out.feedback.message}</strong><p>${out.feedback.follow_up}</p><p>${instrument.copy.ok}</p><button class="link-button" id="again" type="button">${instrument.copy.again}</button>`;
    $('again').addEventListener('click',()=>{form.reset();$('survey').hidden=false;result.hidden=true;submit.disabled=false;});
  }catch(err){submit.disabled=false;const rb=$('result');rb.hidden=false;rb.textContent=language==='fi'?'Lähetys ei onnistunut. Yritä uudelleen.':language==='sv'?'Det gick inte att skicka. Försök igen.':'Could not send. Please try again.';}
});

loadInstrument().catch(()=>{document.querySelector('main').textContent='Pulse mock service is unavailable.';});
