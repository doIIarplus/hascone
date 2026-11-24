import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';

// Quanah: farm event pieces, scan or add them, and see the best 18-line set for a build.
const QUEUE='quanah';

export const lineName=(catalog,key)=>key==='other'?'Other':catalog.lines.find(l=>l.key===key)?.name||key;
const slotName=(catalog,key)=>catalog.slots.find(s=>s.key===key)?.name||key;
const className=(catalog,key)=>catalog.classes.find(c=>c.key===key)?.name||key;
const chip=(catalog,key,extra='')=>`<span class="q-chip q-${esc(key)} ${extra}">${esc(lineName(catalog,key))}</span>`;
const plural=(n,word)=>`${n} ${word}${n===1?'':'s'}`;

// The lines this build targets, with their counts toward the goal, for the pips.
export function requirementRows(model){
 const {catalog,solution:s}=model,rows=Object.entries(s.targets).map(([key,target])=>({label:lineName(catalog,key),have:Math.min(s.counts[key]||0,target),target}));
 if(s.jobs){
  const have=Math.min(s.jobs.count,s.jobs.keys.filter(k=>!(k in s.targets)&&s.counts[k]).length);
  // "any" only when there are more jobs to pick from than the build needs.
  rows.push({label:s.jobs.keys.map(k=>lineName(catalog,k)).join(' · '),have,target:s.jobs.count,jobs:s.jobs.keys.length>s.jobs.count});
 }
 // Most lines needed first; ties keep the catalog's order (the server sorts target keys alphabetically).
 const order=label=>{const i=catalog.lines.findIndex(l=>l.name===label);return i<0?catalog.lines.length:i;};
 return rows.sort((a,b)=>b.target-a.target||order(a.label)-order(b.label));
}

export function renderBest(model){
 const {catalog,solution:s}=model;
 if(!s.goal)return `<section class="card q-best" aria-label="Best set"><header><h2>Best set</h2></header><p class="sub">Set at least one line target to see the best set.</p></section>`;
 const byId=Object.fromEntries(model.items.map(i=>[i.id,i]));
 const done=s.score>=s.goal;
 const reqs=requirementRows(model).map(r=>`<div class="q-req ${r.have<r.target?'is-missing':''}"><span>${esc(r.label)}${r.jobs?` <small>any ${r.target}</small>`:''}</span><span class="q-pips" title="${r.have} of ${r.target}">${Array.from({length:r.target},(_,i)=>`<i class="${i<r.have?'on':''}"></i>`).join('')}</span></div>`).join('');
 const wasted=Object.values(s.used).some(flags=>flags.includes(false));
 const set=catalog.slots.map(slot=>{
  const item=byId[s.picks[slot.key]];
  return `<li><span class="q-slot">${esc(slot.name)}</span>${item?`<span class="q-lines">${item.lines.map((k,i)=>chip(catalog,k,s.used[slot.key][i]?'':'is-wasted')).join('')}</span>`:'<span class="sub">Nothing yet</span>'}</li>`;
 }).join('');
 let next='';
 if(!done){
  next=s.hunt.length
   ?`<div class="q-hunt"><span class="eyebrow">One drop finishes it</span><ul>${s.hunt.slice(0,8).map(h=>`<li><strong>${esc(slotName(catalog,h.slot))}</strong>${h.need.map(k=>chip(catalog,k)).join('')}</li>`).join('')}</ul>${s.hunt.length>8?`<p class="sub">and ${s.hunt.length-8} more options</p>`:''}</div>`
   :`<div class="q-hunt"><span class="eyebrow">Still missing</span><p class="q-lines">${s.missing.map(k=>chip(catalog,k)).join('')}</p><p class="sub">More than one piece away. Keep farming.</p></div>`;
 }
 return `<section class="card q-best" aria-label="Best set">
  <header><h2>Best set</h2><span class="q-pill ${done?'is-ok':''}">${done?'Complete':plural(s.goal-s.score,'line')+' short'}</span></header>
  <p class="q-score"><strong>${s.score}</strong> <span class="sub">of ${s.goal} lines${done?` · ${plural(s.ways,'winning combo')}`:''}</span></p>
  <div class="q-reqs">${reqs}</div>
  <span class="eyebrow">Equip these</span><ul class="q-set">${set}</ul>
  ${wasted?'<p class="sub">Struck-through lines do not count toward this build.</p>':''}
  ${next}
 </section>`;
}

// Background reads: items that aren't Quanah pieces ("Skipped …") are listed apart from real failures.
export function scanSummary(queue){
 if(!queue)return {counts:'',skipped:[],failed:[]};
 const messages=Object.values(queue.failed||{});
 const skipped=messages.filter(m=>m.startsWith('Skipped ')).map(m=>m.slice(8).replace(/: not a Quanah piece$/,''));
 const failed=messages.filter(m=>!m.startsWith('Skipped '));
 const counts=[`${queue.done.length} saved`,`${queue.pending.length} processing`,skipped.length&&`${skipped.length} skipped`,failed.length&&`${failed.length} failed`].filter(Boolean).join(' · ');
 return {counts,skipped,failed};
}

// Two columns, paired as the slots sit in the game: hat and cape, top and gloves, bottom and shoes.
export const GEAR_ORDER=['hat','cape','top','gloves','bottom','shoes'];
const pencil='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>';

export function renderGear(model,editing=null){
 const {catalog,solution:s}=model;
 const picked=new Set(Object.values(s?.picks||{}).filter(Boolean));
 const slots=[...catalog.slots].sort((a,b)=>GEAR_ORDER.indexOf(a.key)-GEAR_ORDER.indexOf(b.key));
 return slots.map(slot=>{
  const pieces=model.items.filter(i=>i.slot===slot.key);
  const rows=pieces.map(item=>{
   const flags=[!item.wearable&&`<span class="q-flag is-danger" title="This piece is for ${esc(className(catalog,item.item_class))}. You can't wear it.">Can't wear · ${esc(className(catalog,item.item_class))}</span>`,
    item.duplicate&&'<span class="q-flag is-warn" title="Another piece in this slot has the same lines">Duplicate</span>'].filter(Boolean).join('');
   const read=item.raw?.length?`Read as:\n${item.raw.join('\n')}`:'';
   const label=`${slot.name}: ${item.lines.map(k=>lineName(catalog,k)).join(', ')}`;
   const source=item.source==='scan'?(item.edited?'Scanned, edited':'Scanned'):'Manual';
   return `<li class="q-piece ${picked.has(item.id)?'is-picked':''} ${item.wearable?'':'is-unwearable'} ${item.id===editing?'is-editing':''}"${read?` title="${esc(read)}"`:''}><span class="q-lines">${item.lines.map(k=>chip(catalog,k)).join('')}</span>${flags}<span class="q-source">${source}</span><button class="q-icon" data-act="edit" data-id="${esc(item.id)}" aria-label="Edit ${esc(label)}" title="Edit">${pencil}</button><button class="q-icon q-delete" data-act="delete" data-id="${esc(item.id)}" aria-label="Delete ${esc(label)}" title="Delete">&times;</button></li>`;
  }).join('');
  return `<section class="q-gear-slot"><header><h3>${esc(slot.name)}</h3><span class="sub">${plural(pieces.length,'piece')}</span></header>${rows?`<ul>${rows}</ul>`:`<p class="sub">No ${esc(slot.name.toLowerCase())} yet</p>`}</section>`;
 }).join('');
}

export async function mountQuanah(root){
 // EDITING is the id of a saved piece loaded into the hand-entry panel, or null when adding.
 let model,disposed=false,slot='hat',pending=[],confirmClear=false,editing=null;
 let scanning=false,windows=[],selectedWindow=null,timer=0,known=new Set(),scanState=null,queue=null;
 root.className='quanah-page';
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading Quanah...</p>';
 const alive=()=>!disposed&&root.isConnected;
 async function save(request){
  try{model=await request;remember();if(alive())draw();}
  catch(error){toast(error.message);}
 }
 // Warn once about each newly scanned piece the player can't wear.
 function remember(announce=false){
  for(const item of model.items){
   if(known.has(item.id))continue;
   known.add(item.id);
   if(announce&&!item.wearable)toast(`${item.name||'That piece'} is a ${className(model.catalog,item.item_class)} item. You can't wear it; don't spend resources on it.`);
  }
 }

 function classPicker(){
  return `<section class="card q-class"><h2>Choose your class</h2><p class="sub">Event pieces are class-locked. Scanned pieces for another class are flagged so you don't spend resources on them.</p><div class="q-class-choices">${model.catalog.classes.map(c=>`<button class="btn ${model.class===c.key?'btn-primary':''}" data-act="class" data-class="${c.key}">${esc(c.name)}</button>`).join('')}</div></section>`;
 }

 function buildPanel(){
  const {catalog,build}=model;
  const tabs=catalog.builds.map(b=>`<button class="btn ${build.preset===b.key?'btn-primary':''}" data-act="preset" data-preset="${b.key}" aria-pressed="${build.preset===b.key}">${esc(b.name)}</button>`).join('');
  let options='';
  if(build.preset==='gandi'){
   const jobs=catalog.lines.filter(l=>l.job);
   options=`<div class="q-build-options"><div class="q-toggle"><button class="btn ${build.job_mode==='custom'?'btn-primary':''}" data-act="job-mode" data-mode="custom">Choose my 3 jobs</button><button class="btn ${build.job_mode==='any'?'btn-primary':''}" data-act="job-mode" data-mode="any">Any 3 of 5 jobs</button></div>
    ${build.job_mode==='custom'?`<div class="q-toggle">${jobs.map(j=>{const on=build.jobs.includes(j.key);return `<button class="btn ${on?'btn-primary':''}" data-act="job" data-job="${j.key}" ${!on&&build.jobs.length>=3?'disabled':''}>${esc(j.name)}${on?' ✓':''}</button>`;}).join('')}</div><p class="sub">${build.jobs.length}/3 selected. Each needs 1 line.${build.jobs.length!==3?' Until 3 are chosen, Magician, Thief and Bowman are used.':''}</p>`:'<p class="sub">Any 3 different job lines count, 1 each.</p>'}</div>`;
  }else if(build.preset==='custom'){
   const total=Object.values(build.targets).reduce((a,b)=>a+b,0);
   options=`<div class="q-build-options"><div class="q-steppers">${catalog.lines.map(l=>{const v=build.targets[l.key]||0;return `<div class="q-stepper"><span>${esc(l.name)}</span><span class="boss-stepper"><button class="btn" data-act="target" data-key="${l.key}" data-step="-1" aria-label="One fewer ${esc(l.name)}" ${v?'':'disabled'}>&minus;</button><span aria-live="polite">${v}</span><button class="btn" data-act="target" data-key="${l.key}" data-step="1" aria-label="One more ${esc(l.name)}" ${v<catalog.max_per_line&&total<catalog.goal?'':'disabled'}>+</button></span></div>`;}).join('')}</div><p class="${total===catalog.goal?'sub':'sc-warning'}">${total} of ${catalog.goal} lines targeted${total===catalog.goal?' (six pieces hold no more)':'.'}</p></div>`;
  }
  return `<section class="card q-build"><header><h2>Build</h2><label class="q-class-select">Class <select class="input" data-act="class-select">${model.catalog.classes.map(c=>`<option value="${c.key}" ${model.class===c.key?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label></header><div class="q-toggle">${tabs}</div>${options}</section>`;
 }

 function scanPanel(){
  const captured=scanState?.mode==='quanah'?scanState.captured||0:0;
  const {counts:reads,skipped,failed}=scanSummary(queue);
  const list=(items,cls)=>items.length?`<ul class="q-failures ${cls}">${items.slice(-3).map(m=>`<li>${esc(m)}</li>`).join('')}</ul>`:'';
  const failures=list(skipped,'is-skipped')+list(failed,'')+(failed.length?'<p class="sub q-note">Failed captures are kept in logs/quanah-failed.</p>':'');
  return `<section class="card q-scan"><header><h2>Scan pieces</h2>${scanning?'<span class="scan-spinner" aria-hidden="true"></span>':''}</header>
   <p class="sub">Hover each event piece in your inventory or Equipment. Every new tooltip is captured; reading happens in the background.</p>
   <div class="q-scan-row"><label>Game window <select class="input" data-act="window" ${scanning?'disabled':''}>${windows.length?windows.map(w=>`<option value="${w.id}" ${w.id===selectedWindow?'selected':''}>${esc(w.title)} · ${w.width} × ${w.height}</option>`).join(''):'<option value="">No game found</option>'}</select></label>
    <button class="btn" data-act="windows" ${scanning?'disabled':''}>Refresh</button>
    <button class="btn ${scanning?'':'btn-primary'}" data-act="${scanning?'stop':'scan'}" ${!scanning&&!windows.length?'disabled':''}>${scanning?'Stop scanning':'Start scanning'}</button></div>
   <p role="status" class="q-scan-status">${esc(scanState?.message||'')}${scanning||captured?` <span class="sub">· ${plural(captured,'capture')}</span>`:''}</p>
   ${reads?`<p class="sub">${reads}</p>`:''}${failures}
  </section>`;
 }

 function addPanel(){
  const {catalog}=model,max=catalog.max_lines;
  const buttons=[...catalog.lines.map(l=>l.key),'other'].map(k=>`<button class="q-chip q-${k} is-button" data-act="line" data-key="${k}" ${k!=='other'&&pending.includes(k)||pending.length>=max?'disabled':''}>${esc(lineName(catalog,k))}</button>`).join('');
  const slots=catalog.slots.map(s=>`<button class="btn ${slot===s.key?'btn-primary':''}" data-act="slot" data-slot="${s.key}" aria-pressed="${slot===s.key}">${esc(s.name)} <small>${model.items.filter(i=>i.slot===s.key).length}</small></button>`).join('');
  const picked=Array.from({length:max},(_,i)=>pending[i]?chip(catalog,pending[i]):`<span class="q-chip is-empty">line ${i+1}</span>`).join('');
  const piece=editing&&model.items.find(i=>i.id===editing);
  const read=piece?.raw?.length?`<p class="sub q-read">Scanner read: ${piece.raw.map(esc).join(' · ')}</p>`:'';
  return `<section class="card q-add ${editing?'is-editing':''}"><header><h2>${editing?'Edit piece':'Add a piece by hand'}</h2></header>${read}<div class="q-toggle">${slots}</div><div class="q-line-buttons">${buttons}</div>
   <div class="q-pending"><span class="eyebrow">${editing?'Editing':'New'} ${esc(slotName(catalog,slot))}</span>${picked}
    ${pending.length?'<button class="btn" data-act="undo">Undo line</button>':''}
    ${editing?`<button class="btn" data-act="cancel-edit">Cancel</button><button class="btn btn-primary" data-act="save-edit" ${pending.length?'':'disabled'}>Save changes</button>`
     :`<button class="btn btn-primary" data-act="add" ${pending.length?'':'disabled'}>Add piece</button>`}</div></section>`;
 }
 function startEdit(id){
  const item=model.items.find(i=>i.id===id);if(!item)return;
  editing=id;slot=item.slot;pending=[...item.lines];draw();
  const panel=root.querySelector('.q-add');
  panel?.scrollIntoView({block:'nearest',behavior:'smooth'});
  panel?.querySelector('[data-act="save-edit"]')?.focus({preventScroll:true});
 }
 function stopEdit(){editing=null;pending=[];}

 function draw(){
  if(!alive())return;
  // Keep keyboard focus on the same control across redraws.
  const sig=el=>JSON.stringify(el.dataset),active=document.activeElement;
  const focus=active&&root.contains(active)&&active.dataset.act?sig(active):null;
  const head=`<div class="page-head"><h1>Quanah</h1><p class="sub">Seasonal event equipment. Find the one-per-slot set that completes your build's 18 skill lines.</p></div>`;
  if(!model.class){root.innerHTML=head+classPicker();return;}
  if(editing&&!model.items.some(i=>i.id===editing))stopEdit();
  const total=model.items.length,dupes=model.items.filter(i=>i.duplicate).length,unwearable=model.items.filter(i=>!i.wearable).length;
  root.innerHTML=`${head}<div class="q-layout"><div class="q-main">${buildPanel()}${scanPanel()}${addPanel()}
   <section class="card q-gear"><header><h2>Your pieces <span class="sub">(${total})</span></h2>${total?`<button class="btn ${confirmClear?'btn-danger':''}" data-act="clear">${confirmClear?'Click again to delete every piece':'Delete all'}</button>`:''}</header>
    ${dupes||unwearable?`<p class="sub">${[dupes&&plural(dupes,'duplicate'),unwearable&&`${unwearable} you can't wear`].filter(Boolean).join(' · ')}. Fix a misread with the pencil, or delete with ×.</p>`:''}
    <div class="q-gear-slots">${renderGear(model,editing)}</div></section></div>
   <div class="q-side">${renderBest(model)}</div></div>`;
  if(focus)[...root.querySelectorAll('[data-act]')].find(el=>sig(el)===focus)?.focus({preventScroll:true});
 }

 const setBuild=build=>save(api.put('/api/quanah/settings',{build}));

 async function loadWindows(){
  try{windows=await api.get('/api/windows');}catch{windows=[];}
  if(!windows.some(w=>w.id===selectedWindow))selectedWindow=windows[0]?.id??null;
 }

 async function poll(){
  clearTimeout(timer);
  if(!alive())return;
  try{
   const [state,reads]=await Promise.all([api.get('/api/scan'),api.get('/api/scan/queue/'+QUEUE)]);
   if(!alive())return;
   const finished=reads.done.length!==(queue?.done.length??0);
   scanState=state;queue=reads;
   if(scanning&&!state.active){scanning=false;if(state.status==='error')toast(state.message);}
   if(finished){model=await api.get('/api/quanah');remember(true);}
   draw();
   if(scanning||reads.pending.length)timer=setTimeout(poll,700);
  }catch(error){if(alive())timer=setTimeout(poll,2000);}
 }

 async function startScan(){
  try{
   scanState=await api.post('/api/quanah/scan',{window:Number(selectedWindow)});
   scanning=true;draw();poll();
  }catch(error){toast(error.message);}
 }
 async function stopScan(){
  scanning=false;
  try{scanState=await api.post('/api/scan/cancel',{release:true});}catch{}
  poll();
 }

 root.addEventListener('click',e=>{
  const b=e.target.closest('[data-act]');if(!b||b.tagName==='SELECT')return;
  const act=b.dataset.act,build=model.build;
  if(act!=='clear')confirmClear=false;
  if(act==='class')save(api.put('/api/quanah/settings',{class:b.dataset.class}));
  else if(act==='preset')setBuild({preset:b.dataset.preset});
  else if(act==='job-mode')setBuild({job_mode:b.dataset.mode});
  else if(act==='job'){const k=b.dataset.job;setBuild({jobs:build.jobs.includes(k)?build.jobs.filter(j=>j!==k):[...build.jobs,k]});}
  else if(act==='target'){const k=b.dataset.key,v=Math.max(0,Math.min(model.catalog.max_per_line,(build.targets[k]||0)+Number(b.dataset.step)));setBuild({targets:{...build.targets,[k]:v}});}
  // Moving a piece being edited to another slot keeps its lines.
  else if(act==='slot'){slot=b.dataset.slot;if(!editing)pending=[];draw();}
  else if(act==='line'){pending.push(b.dataset.key);draw();}
  else if(act==='undo'){pending.pop();draw();}
  else if(act==='add'){const lines=pending;pending=[];save(api.post('/api/quanah/items',{slot,lines}));}
  else if(act==='edit')startEdit(b.dataset.id);
  else if(act==='cancel-edit'){stopEdit();draw();}
  else if(act==='save-edit'){const id=editing,lines=pending;stopEdit();save(api.put('/api/quanah/items/'+encodeURIComponent(id),{slot,lines}));}
  else if(act==='delete')save(api.delete('/api/quanah/items/'+encodeURIComponent(b.dataset.id)));
  else if(act==='clear'){if(confirmClear){confirmClear=false;save(api.delete('/api/quanah/items'));}else{confirmClear=true;draw();}}
  else if(act==='scan')startScan();
  else if(act==='stop')stopScan();
  else if(act==='windows')loadWindows().then(draw);
 });
 root.addEventListener('change',e=>{
  const act=e.target.dataset.act;
  if(act==='class-select')save(api.put('/api/quanah/settings',{class:e.target.value}));
  else if(act==='window')selectedWindow=Number(e.target.value);
 });

 try{
  [model]=await Promise.all([api.get('/api/quanah'),loadWindows()]);
  remember();
  // Pick up a scan still running from before this page was opened.
  const state=await api.get('/api/scan');
  if(state.active&&state.mode==='quanah')scanning=true;
  draw();poll();
 }catch(error){root.innerHTML=`<p class="sc-warning">${esc(error.message)}</p>`;}

 return ()=>{
  disposed=true;clearTimeout(timer);
  // Leaving the page stops watching the game; captured pieces keep reading in the background.
  if(scanning)api.post('/api/scan/cancel',{release:true}).catch(()=>{});
 };
}
