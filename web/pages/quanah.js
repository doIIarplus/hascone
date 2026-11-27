import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';
import {mountMissions} from './quanah-missions.js';

// Quanah: farm event pieces, scan or add them, and see the best 18-line set for a build.
const QUEUE='quanah';

export const lineName=(catalog,key)=>key==='other'?'Other':catalog.lines.find(l=>l.key===key)?.name||key;
const slotName=(catalog,key)=>catalog.slots.find(s=>s.key===key)?.name||key;
const className=(catalog,key)=>catalog.classes.find(c=>c.key===key)?.name||key;
const chip=(catalog,key,extra='')=>`<span class="q-chip q-${esc(key)} ${extra}">${esc(lineName(catalog,key))}</span>`;
const plural=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
// A piece for another class still counts: its lines can be orbed onto your own piece of the slot.
const classFlag=({catalog,class:mine},item)=>{
 const theirs=esc(className(catalog,item.item_class));
 return `<span class="q-flag is-warn" title="This piece is for ${theirs}. Orb its lines onto a ${esc(className(catalog,mine))} ${esc(slotName(catalog,item.slot).toLowerCase())} to use them.">${theirs}</span>`;
};

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

// The combo after stepping STEP (-1 or 1) from COMBO through COUNT combos, wrapping round.
export const stepCombo=(combo,step,count)=>(combo+step+count)%count;
// The request that flips a piece's mark from a toggle button: [path, body].
const MARK={prefer:'preferred',worn:'worn',disabled:'disabled'};
export function markRequest(act,item){
 const flag=MARK[act];
 return ['/api/quanah/items/'+encodeURIComponent(item.id)+'/'+flag,{[flag]:!item[flag]}];
}

// The winning combo on show: COMBO indexes solution.combos, which a complete set lists.
const shown=(s,combo=0)=>s?.combos?.[combo]||s;

export function renderBest(model,combo=0){
 const {catalog,solution:s}=model,{picks,used,orbs}=shown(s,combo);
 if(!s.goal)return `<section class="card q-best" aria-label="Best set"><header><h2>Best set</h2></header><p class="sub">Set at least one line target to see the best set.</p></section>`;
 const byId=Object.fromEntries(model.items.map(i=>[i.id,i]));
 const orbSlots=catalog.slots.filter(slot=>byId[picks[slot.key]]?.transfer).map(slot=>slot.name);
 const done=s.score>=s.goal;
 const reqs=requirementRows(model).map(r=>`<div class="q-req ${r.have<r.target?'is-missing':''}"><span>${esc(r.label)}${r.jobs?` <small>any ${r.target}</small>`:''}</span><span class="q-pips" title="${r.have} of ${r.target}">${Array.from({length:r.target},(_,i)=>`<i class="${i<r.have?'on':''}"></i>`).join('')}</span></div>`).join('');
 const wasted=Object.values(used).some(flags=>flags.includes(false));
 const set=catalog.slots.map(slot=>{
  const item=byId[picks[slot.key]];
  return `<li><span class="q-slot">${esc(slot.name)}</span>${item?`<span class="q-pick"><span class="q-lines">${item.lines.map((k,i)=>chip(catalog,k,used[slot.key][i]?'':'is-wasted')).join('')}</span>${item.wearable?'':classFlag(model,item)}${item.wearable&&item.transfer?'<span class="q-flag is-warn" title="You wear another piece in this slot: orb these lines onto it">Orb</span>':''}${item.preferred?'<span class="q-flag is-pref" title="You prefer this piece, so the set is built around it">Preferred</span>':''}</span>`:`<span class="sub">${model.items.some(i=>i.slot===slot.key&&i.worn)?'Keep wearing yours (disabled)':'Nothing yet'}</span>`}</li>`;
 }).join('');
 let next='';
 if(!done){
  next=s.hunt.length
   ?`<div class="q-hunt"><span class="eyebrow">One drop finishes it</span><ul>${s.hunt.slice(0,8).map(h=>`<li><strong>${esc(slotName(catalog,h.slot))}</strong>${h.need.map(k=>chip(catalog,k)).join('')}${model.items.some(i=>i.slot===h.slot&&i.worn)?'<span class="sub" title="You wear a piece in this slot, so the drop&#39;s lines must be orbed onto it">+ 1 orb</span>':''}</li>`).join('')}</ul>${s.hunt.length>8?`<p class="sub">and ${s.hunt.length-8} more options</p>`:''}</div>`
   :`<div class="q-hunt"><span class="eyebrow">Still missing</span><p class="q-lines">${s.missing.map(k=>chip(catalog,k)).join('')}</p><p class="sub">More than one piece away. Keep farming.</p></div>`;
 }
 return `<section class="card q-best" aria-label="Best set">
  <header><h2>Best set</h2><span class="q-pill ${done?'is-ok':''}">${done?'Complete':plural(s.goal-s.score,'line')+' short'}</span></header>
  <p class="q-score"><strong>${s.score}</strong> <span class="sub">of ${s.goal} lines${done?` · ${plural(s.ways,'winning combo')}`:''}</span></p>
  <div class="q-reqs">${reqs}</div>
  <div class="q-equip"><span class="eyebrow">Equip these</span>${s.combos?.length>1?`<span class="q-combos"><button class="q-icon" data-act="combo" data-step="-1" aria-label="Previous winning combo" title="Previous combo">&lsaquo;</button><span aria-live="polite">Combo ${combo+1} of ${s.combos.length}${s.ways>s.combos.length?'+':''}</span><button class="q-icon" data-act="combo" data-step="1" aria-label="Next winning combo" title="Next combo">&rsaquo;</button></span>`:''}</div><ul class="q-set">${set}</ul>
  ${orbs?`<p class="q-orbs"><strong>${plural(orbs,'orb')}</strong> <span class="sub">needed: ${esc(orbSlots.join(', '))}</span></p>`:''}
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
const ban='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M6.5 6.5l11 11"/></svg>';
const shirt='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M8 3l4 2 4-2 5 4-3 3-2-1v12H8V9l-2 1-3-3z"/></svg>';
const star=on=>`<svg width="13" height="13" viewBox="0 0 24 24" fill="${on?'currentColor':'none'}" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg>`;
const pencil='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>';

// MENU is the id of the piece whose "..." menu (edit, delete) is open.
export function renderGear(model,editing=null,combo=0,menu=null){
 const {catalog,solution:s}=model;
 const picked=new Set(Object.values(shown(s,combo)?.picks||{}).filter(Boolean));
 const slots=[...catalog.slots].sort((a,b)=>GEAR_ORDER.indexOf(a.key)-GEAR_ORDER.indexOf(b.key));
 return slots.map(slot=>{
  const pieces=model.items.filter(i=>i.slot===slot.key);
  const rows=pieces.map(item=>{
   const flags=[!item.wearable&&classFlag(model,item),
    item.duplicate&&'<span class="q-flag is-warn" title="Another piece in this slot has the same lines">Duplicate</span>'].filter(Boolean).join('');
   const read=item.raw?.length?`Read as:\n${item.raw.join('\n')}`:'';
   const label=`${slot.name}: ${item.lines.map(k=>lineName(catalog,k)).join(', ')}`;
   return `<li class="q-piece ${picked.has(item.id)?'is-picked':''} ${item.disabled?'is-disabled':''} ${item.id===editing?'is-editing':''}"${read?` title="${esc(read)}"`:''}><span class="q-lines">${item.lines.map(k=>chip(catalog,k)).join('')}</span>${flags}<span class="q-actions"><button class="q-icon q-mark q-worn ${item.worn?'is-on':''}" data-act="worn" data-id="${esc(item.id)}" aria-pressed="${!!item.worn}" aria-label="${item.worn?'Not wearing':'Wearing'} ${esc(label)}" title="${item.worn?'You wear this piece now; other pieces are orbed onto it. Click to unmark.':`I'm wearing this ${esc(slot.name.toLowerCase())}: count an orb for using any other piece here`}">${shirt}</button><button class="q-icon q-mark q-prefer ${item.preferred?'is-on':''}" data-act="prefer" data-id="${esc(item.id)}" aria-pressed="${!!item.preferred}" aria-label="${item.preferred?'Stop preferring':'Prefer'} ${esc(label)}" title="${item.preferred?'Preferred: always in the best set. Click to stop preferring.':`Prefer: always build the set with this ${esc(slot.name.toLowerCase())}`}">${star(item.preferred)}</button><button class="q-icon q-mark ${item.disabled?'is-on':''}" data-act="disabled" data-id="${esc(item.id)}" aria-pressed="${!!item.disabled}" aria-label="${item.disabled?'Enable':'Disable'} ${esc(label)}" title="${item.disabled?'Disabled: left out of every combo. Click to use it again.':'Disable: leave this piece out of every combo'}">${ban}</button><span class="q-more"><button class="q-icon" data-act="menu" data-id="${esc(item.id)}" aria-haspopup="menu" aria-expanded="${item.id===menu}" aria-label="More for ${esc(label)}" title="More">&hellip;</button>${item.id===menu?`<span class="q-menu" role="menu"><button role="menuitem" data-act="edit" data-id="${esc(item.id)}" aria-label="Edit ${esc(label)}">${pencil} Edit</button><button role="menuitem" class="q-delete" data-act="delete" data-id="${esc(item.id)}" aria-label="Delete ${esc(label)}">&times; Delete</button></span>`:''}</span></span></li>`;
  }).join('');
  return `<section class="q-gear-slot"><header><h3>${esc(slot.name)}</h3><span class="sub">${plural(pieces.length,'piece')}</span></header>${rows?`<ul>${rows}</ul>`:`<p class="sub">No ${esc(slot.name.toLowerCase())} yet</p>`}</section>`;
 }).join('');
}

async function mountSolver(root){
 // EDITING is the id of a saved piece loaded into the hand-entry panel, or null when adding.
 // COMBO is the winning combo on show; any change to the pieces or build starts again at the first.
 let model,disposed=false,slot='hat',pending=[],confirmClear=false,editing=null,combo=0,menu=null;
 let scanning=false,windows=[],selectedWindow=null,timer=0,known=new Set(),scanState=null,queue=null;
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading Quanah...</p>';
 const alive=()=>!disposed&&root.isConnected;
 async function save(request){
  try{model=await request;combo=0;remember();if(alive())draw();}
  catch(error){toast(error.message);}
 }
 // Note once each newly scanned piece for another class.
 function remember(announce=false){
  for(const item of model.items){
   if(known.has(item.id))continue;
   known.add(item.id);
   if(announce&&!item.wearable)toast(`${item.name||'That piece'} is a ${className(model.catalog,item.item_class)} item. It still counts if you orb its lines onto your own ${slotName(model.catalog,item.slot).toLowerCase()}.`);
  }
 }

 function classPicker(){
  return `<section class="card q-class"><h2>Choose your class</h2><p class="sub">Event pieces are class-locked. Pieces for another class still count toward the best set and are tagged with that class: orb their lines onto your own piece of the same slot.</p><div class="q-class-choices">${model.catalog.classes.map(c=>`<button class="btn ${model.class===c.key?'btn-primary':''}" data-act="class" data-class="${c.key}">${esc(c.name)}</button>`).join('')}</div></section>`;
 }

 function buildPanel(){
  const {catalog,build}=model;
  const tabs=catalog.builds.map(b=>`<button class="btn ${build.preset===b.key?'btn-primary':''}" data-act="preset" data-preset="${b.key}" aria-pressed="${build.preset===b.key}">${esc(b.name)}</button>`).join('');
  let options='';
  if(build.preset==='hybrid'){
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
 // Close the "..." menu in place; returns its button, so focus can go back to it.
 function closeMenu(){
  const button=root.querySelector(`[data-act="menu"][data-id="${CSS.escape(menu)}"]`);
  root.querySelector('.q-menu')?.remove();
  button?.setAttribute('aria-expanded','false');
  menu=null;
  return button;
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
  if(!model.class){root.innerHTML=classPicker();return;}
  if(editing&&!model.items.some(i=>i.id===editing))stopEdit();
  const total=model.items.length,dupes=model.items.filter(i=>i.duplicate).length,offclass=model.items.filter(i=>!i.wearable).length;
  root.innerHTML=`<div class="q-layout"><div class="q-main">${buildPanel()}${scanPanel()}${addPanel()}
   <section class="card q-gear"><header><h2>Your pieces <span class="sub">(${total})</span></h2>${total?`<button class="btn ${confirmClear?'btn-danger':''}" data-act="clear">${confirmClear?'Click again to delete every piece':'Delete all'}</button>`:''}</header>
    ${dupes||offclass?`<p class="sub">${[dupes&&plural(dupes,'duplicate'),offclass&&`${offclass} for another class`].filter(Boolean).join(' · ')}. Fix a misread or delete a piece from its &hellip; menu.</p>`:''}
    <div class="q-gear-slots">${renderGear(model,editing,combo,menu)}</div></section></div>
   <div class="q-side">${renderBest(model,combo)}</div></div>`;
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
   if(finished){model=await api.get('/api/quanah');combo=0;remember(true);}
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
  const b=e.target.closest('[data-act]'),act=b?.dataset.act;
  if(act==='menu'){menu=menu===b.dataset.id?null:b.dataset.id;draw();if(menu)root.querySelector('.q-menu [role="menuitem"]')?.focus();return;}
  // Any other click closes the "..." menu, without a redraw so a dropdown clicked still opens.
  if(menu)closeMenu();
  if(!b||b.tagName==='SELECT')return;
  const build=model.build;
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
  else if(act==='combo'){combo=stepCombo(combo,Number(b.dataset.step),model.solution.combos.length);draw();}
  else if(act in MARK){const item=model.items.find(i=>i.id===b.dataset.id);if(item)save(api.put(...markRequest(act,item)));}
  else if(act==='delete')save(api.delete('/api/quanah/items/'+encodeURIComponent(b.dataset.id)));
  else if(act==='clear'){if(confirmClear){confirmClear=false;save(api.delete('/api/quanah/items'));}else{confirmClear=true;draw();}}
  else if(act==='scan')startScan();
  else if(act==='stop')stopScan();
  else if(act==='windows')loadWindows().then(draw);
 });
 root.addEventListener('keydown',e=>{
  if(e.key!=='Escape'||!menu)return;
  closeMenu()?.focus();
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

// Two views: the set solver and the Dimensional mission tracker. Both stay mounted, so a scan
// keeps running while you tick off missions.
const VIEWS={solver:'Set solver',missions:'Dimensional missions'};
const SUBTITLE={solver:"Seasonal event equipment. Find the one-per-slot set that completes your build's 18 skill lines.",
 missions:'Check off Dimensional missions. Reaching a level, floor, boss difficulty or star force completes every one before it.'};
export async function mountQuanah(root){
 let view='solver';
 try{view=VIEWS[localStorage.getItem('hascone.quanah.view')]?localStorage.getItem('hascone.quanah.view'):'solver';}catch{}
 root.className='quanah-page';
 root.innerHTML=`<div class="page-head"><h1>Quanah</h1><p class="sub" data-subtitle></p></div>
  <nav class="fl-subtabs" role="tablist" aria-label="Quanah view">${Object.entries(VIEWS).map(([key,label])=>`<button class="btn" role="tab" id="q-tab-${key}" aria-controls="q-panel-${key}" data-view="${key}">${label}</button>`).join('')}</nav>
  ${Object.keys(VIEWS).map(key=>`<div id="q-panel-${key}" role="tabpanel" aria-labelledby="q-tab-${key}"></div>`).join('')}`;
 const cleanups={},panel=key=>root.querySelector('#q-panel-'+key);
 async function show(key){
  view=key;
  try{localStorage.setItem('hascone.quanah.view',key);}catch{}
  root.querySelector('[data-subtitle]').textContent=SUBTITLE[key];
  for(const k of Object.keys(VIEWS)){panel(k).hidden=k!==key;root.querySelector('#q-tab-'+k).setAttribute('aria-selected',String(k===key));}
  // Kept as a promise from the start, so a tab clicked again while loading isn't mounted twice.
  // A mount that fails is forgotten, so clicking the tab again retries it.
  cleanups[key]??=(key==='solver'?mountSolver:mountMissions)(panel(key)).catch(error=>{delete cleanups[key];throw error;});
  await cleanups[key];
 }
 root.querySelector('[role="tablist"]').addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b&&b.dataset.view!==view)show(b.dataset.view).catch(error=>toast(error.message));});
 await show(view);
 return ()=>{for(const mounting of Object.values(cleanups))mounting.then(cleanup=>cleanup?.(),()=>{});};
}
