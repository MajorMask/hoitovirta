// Upcoming free screening tests: plain information (each with its source) and a longer check-in. Mock, synthetic, DEMO ids only.
(function(){
  const $=id=>document.getElementById(id), esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
  const caseId='DEMO-SCREEN-01';
  async function draw(language){
    const root=$('screening-view'); root.innerHTML='<p class="intro">…</p>';
    let d; try{ const r=await fetch(`api/screening?language=${language}`); d=await r.json(); }catch(e){ root.innerHTML='<p class="intro">Not available.</p>'; return; }
    const c=d.copy, link=id=>`<a href="${esc(d.sources[id].url)}" target="_blank" rel="noopener noreferrer">${esc(d.sources[id].label)}</a>`;
    const choice=(name,opts)=>Object.entries(opts).map(([v,l])=>`<label class="choice"><input type="radio" name="${name}" value="${v}" required><span>${esc(l)}</span></label>`).join('');
    root.innerHTML=`<h1>${esc(c.title)}</h1><p class="intro">${esc(c.lead)}</p>
      <div class="cards">${d.programmes.map(p=>`<article class="card"><h2>${esc(p.name)}</h2><p><strong>${esc(p.who)}</strong></p><p>${esc(p.how)}</p><p class="source-note">${p.sources.map(link).join(' · ')}</p></article>`).join('')}</div>
      <p class="band">${esc(c.cost_note)}</p>
      <article class="card"><h2>${esc(c.after_h)}</h2><p>${esc(c.after)}</p><p class="source-note">${link('relander')}</p></article>
      <h2>${esc(c.check)}</h2>
      <form id="screening-form"><fieldset><legend>${esc(c.q3)}</legend><div class="choices">${choice('PU3',c.o3)}</div></fieldset>
        <fieldset><legend>${esc(c.q4)}</legend><div class="choices">${choice('PU4',c.o4)}</div></fieldset>
        <fieldset><legend>${esc(c.sx1)}</legend><div class="choices">${choice('SX1',c.o_sx1)}</div></fieldset>
        <fieldset><legend>${esc(c.sx2)}</legend><div class="choices">${choice('SX2',c.o_sx2)}</div></fieldset>
        <p class="hint">${esc(c.mock)}</p><button class="primary" type="submit">${esc(c.send)}</button></form>
      <div id="screening-result" class="result" hidden></div>
      <p class="source-note">${esc(c.src)}: ${Object.keys(d.sources).map(link).join(' · ')}</p>`;
    $('screening-form').addEventListener('submit',async e=>{
      e.preventDefault(); const form=e.currentTarget, f=new FormData(form), btn=form.querySelector('button'); btn.disabled=true;
      try{
        const res=await fetch('api/responses',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({demo_case:caseId,language,moment:'screening',channel:'app',answers:{PU3:f.get('PU3'),PU4:f.get('PU4'),SX1:f.get('SX1'),SX2:f.get('SX2')}})});
        const out=await res.json(); if(!res.ok) throw new Error(JSON.stringify(out.detail));
        form.hidden=true; const box=$('screening-result'); box.hidden=false; box.classList.toggle('alert',out.response.signals.length>0);
        box.innerHTML=`<strong>${esc(out.feedback.message)}</strong><p>${esc(out.feedback.follow_up)}</p>`;
      }catch(err){ btn.disabled=false; const box=$('screening-result'); box.hidden=false; box.classList.add('alert'); box.textContent=(language==='fi'?'Lähetys ei onnistunut. Yritä uudelleen.':language==='sv'?'Det gick inte att skicka. Försök igen.':'Could not send. Please try again.'); }
    });
  }
  window.drawScreening=draw;
})();
