import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';

// Dimensional missions: one checkmark each. Completing a mission completes every one before it
// in its chain (levels, floors, a boss's difficulties); the server does the cascade. Star force is
// optional: an item can be tapped from 23 to 24 alone, so a toggle chooses whether it cascades.
const CASCADE_KEY='quanah-starforce-cascade';
const readCascade=()=>{try{return localStorage.getItem(CASCADE_KEY)==='1';}catch{return false;}};
const fmt=n=>Number(n).toLocaleString('en-US');
const TYPE={round:'Round',permanent:'Permanent'};

export function renderSummary(model){
 const s=model.summary,next=s.next;
 const floor=model.catalog.grades.find(g=>g.grade===s.grade).points;
 const pct=next?Math.round((s.points-floor)/(next.points-floor)*100):100;
 return `<section class="card qm-summary" aria-label="Dimensional grade">
  <div class="qm-grade"><span class="eyebrow">Dimensional grade</span><strong>${s.grade}</strong>
   <div class="qm-bar" role="progressbar" aria-label="Progress to the next grade" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
   <span class="sub">${next?`${fmt(next.points-s.points)} pts to Grade ${next.grade}`:'Highest grade reached'}</span></div>
  <dl class="qm-stats">
   <div><dt>Total points</dt><dd>${fmt(s.points)}</dd></div>
   <div><dt>Missions completed</dt><dd>${s.completed} <small>/ ${s.total}</small></dd></div>
   <div><dt>Permanent points</dt><dd>${fmt(s.permanent)}</dd></div>
   <div><dt>Round points</dt><dd>${fmt(s.round)}</dd></div>
  </dl>
  <button class="btn qm-reset" data-act="reset-round" ${s.round?'':'disabled'} title="Clear inspector level and Battlesim missions, as when your character dies">Reset round missions</button>
 </section>`;
}

const box=(m,on)=>`<label class="qm-check ${on?'is-done':''}"><input type="checkbox" data-mission="${esc(m.id)}" ${on?'checked':''}><span>${esc(m.label)}</span><small>${fmt(m.points)}</small></label>`;

export function renderGroup(group,done,cascade=false){
 const set=new Set(done),missions=group.chains.flatMap(c=>c.missions);
 const finished=missions.filter(m=>set.has(m.id));
 const points=finished.reduce((a,m)=>a+m.points,0),max=missions.reduce((a,m)=>a+m.points,0);
 // A single chain is a grid of checkmarks; bosses get a row each.
 const body=group.chains.length===1
  ?`<div class="qm-grid">${missions.map(m=>box(m,set.has(m.id))).join('')}</div>`
  :`<ul class="qm-rows">${group.chains.map(c=>`<li><span class="qm-name">${esc(c.name)}</span><span class="qm-diffs">${c.missions.map(m=>box(m,set.has(m.id))).join('')}</span></li>`).join('')}</ul>`;
 return `<section class="card qm-group" aria-label="${esc(group.name)} missions">
  <header><h2>${esc(group.name)} <span class="q-pill qm-${group.type}">${TYPE[group.type]}</span></h2><span class="sub">${finished.length}/${missions.length} · ${fmt(points)} / ${fmt(max)} pts</span></header>
  ${group.optional_cascade?`<label class="qm-cascade"><input type="checkbox" data-cascade ${cascade?'checked':''}><span>Also complete lower star levels</span></label>`:''}
  ${body}</section>`;
}

export function renderMissions(model,cascade=false){
 // Round missions in one column, permanent in the other.
 const column=type=>`<div class="qm-column">${model.catalog.groups.filter(g=>g.type===type).map(g=>renderGroup(g,model.done,cascade)).join('')}</div>`;
 return renderSummary(model)+`<div class="qm-groups">${column('round')}${column('permanent')}</div>`;
}

function confirmReset(onConfirm){
 const dialog=document.createElement('dialog');dialog.className='qm-reset-dialog';
 dialog.setAttribute('aria-label','Reset round missions');
 dialog.innerHTML=`<h2>Reset round missions?</h2><p>This clears every Inspector Level and Battlesim mission, as when your character dies. Boss and Star Force missions are permanent and stay complete.</p><p class="warn" role="alert"></p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn qm-reset-confirm">Reset round missions</button></footer>`;
 document.body.append(dialog);dialog.showModal();
 dialog.addEventListener('close',()=>dialog.remove(),{once:true});
 dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
 dialog.querySelector('.qm-reset-confirm').onclick=async e=>{
  const button=e.currentTarget;button.disabled=true;
  try{await onConfirm();dialog.close();}
  catch(error){dialog.querySelector('[role="alert"]').textContent=error.message;button.disabled=false;}
 };
}

export async function mountMissions(root){
 // Saves go out one at a time, in click order, so the server applies them in that order and a
 // slow reply can't overwrite a newer one. Redraws wait for the last queued save, so boxes ticked meanwhile don't flicker back.
 let model,cascade=readCascade(),disposed=false,queue=Promise.resolve(),pending=0;
 function send(request){
  pending++;
  const run=queue.then(request).then(next=>{model=next;}).finally(()=>{if(!--pending)draw();});
  queue=run.catch(()=>{}); // One failed save mustn't stop the ones queued after it.
  return run;
 }
 const alive=()=>!disposed&&root.isConnected;
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading missions...</p>';
 function draw(){
  if(!alive())return;
  const focused=document.activeElement?.dataset?.mission;
  root.innerHTML=renderMissions(model,cascade);
  if(focused)root.querySelector(`[data-mission="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
 }
 root.addEventListener('change',e=>{
  if(e.target.matches('[data-cascade]')){
   cascade=e.target.checked;
   try{localStorage.setItem(CASCADE_KEY,cascade?'1':'0');}catch{}
   return;
  }
  const id=e.target.dataset.mission;if(!id)return;
  const done=e.target.checked;
  const optional=model.catalog.groups.some(g=>g.optional_cascade&&g.chains.some(c=>c.missions.some(m=>m.id===id)));
  // A failed save redraws from the last saved state, unticking the box again.
  send(()=>api.put('/api/quanah/missions/'+encodeURIComponent(id),optional?{done,cascade}:{done})).catch(error=>{if(alive())toast(error.message);});
 });
 root.addEventListener('click',e=>{
  if(!e.target.closest('[data-act="reset-round"]'))return;
  confirmReset(async()=>{await send(()=>api.delete('/api/quanah/missions/round'));toast('Round missions reset.');});
 });
 try{model=await api.get('/api/quanah/missions');draw();}
 catch(error){if(alive())root.innerHTML=`<p class="sc-warning">${esc(error.message)}</p>`;}
 return ()=>{disposed=true;};
}
