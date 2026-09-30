import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';
import {compactCost} from '../format.js';

// Weekly boss clears and crystal income for the roster, plus a diary of notable drops.
const CATEGORY={weekly:'Weekly',monthly:'Monthly',daily:'Daily'};
const mesos=value=>compactCost(value);
const full=value=>Number(value).toLocaleString();
const bossIcon=(icon,size=36)=>`<img class="boss-icon" src="/static/bosses/${icon}.png" alt="" width="${size}" height="${size}">`;
const itemIcon=(id,size=32,alt='')=>`<img class="boss-item-icon" src="/static/items/${id}.png" alt="${alt}" width="${size}" height="${size}">`;
let tab='tracker';
try{tab=localStorage.getItem('hascone.bossing.tab')||'tracker';}catch{}

export async function mountBossing(root,character,onSelect){
 let model,disposed=false,editing=null,timer=0;
 root.className='bossing-page';
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading bosses...</p>';
 const alive=()=>!disposed&&root.isConnected;
 const me=()=>model.characters.find(c=>c.id===character)||model.characters[0];
 const nameOf=id=>model.characters.find(c=>c.id===id)?.name||'Deleted character';
 async function save(request){
  try{model=await request;if(alive())draw();}
  catch(error){toast(error.message);}
 }
 function countdown(){
  const el=root.querySelector('[data-countdown]');if(!el||!model)return;
  let left=Math.max(0,new Date(model.reset)-Date.now());
  const days=Math.floor(left/864e5);left%=864e5;
  const hours=Math.floor(left/36e5),minutes=Math.floor(left%36e5/6e4);
  el.textContent=`${days?days+'d ':''}${hours}h ${minutes}m`;
  // The week rolled over while the page was open; reload this week's clears.
  if(new Date(model.reset)<=Date.now())api.get('/api/bossing').then(next=>{model=next;if(alive())draw();}).catch(()=>{});
 }

 function summary(){
  const earned=model.characters.reduce((s,c)=>s+c.earned,0),possible=model.characters.reduce((s,c)=>s+c.possible,0);
  const configured=model.characters.filter(c=>c.bosses.length),done=configured.filter(c=>c.done).length;
  const worlds=model.worlds.length?model.worlds.map(w=>`<span title="${w.over?`${w.over} over the weekly limit; the least valuable crystals will not sell`:'Crystals sold this week in this world'}">${esc(w.world)} <strong class="${w.over?'boss-over':''}">${w.crystals} / ${model.world_limit}</strong></span>`).join(''):'<span class="sub">None this week</span>';
  return `<section class="boss-summary" aria-label="This week">
   <div><span class="eyebrow">Earned this week</span><strong title="${full(earned)} of ${full(possible)} mesos">${mesos(earned)} <small>/ ${mesos(possible)}</small></strong><progress max="${possible||1}" value="${earned}"></progress></div>
   <div><span class="eyebrow">Crystals by world</span><p class="boss-worlds">${worlds}</p></div>
   <div><span class="eyebrow">Characters done</span><strong>${done} <small>/ ${configured.length}</small></strong></div>
   <div><span class="eyebrow">Last week</span><strong title="${full(model.history[1]?.mesos||0)} mesos">${mesos(model.history[1]?.mesos||0)}</strong></div>
  </section>`;
 }

 function bossRow(c,b,selling){
  const over=b.category==='weekly'&&!selling.has(b.name);
  const control=b.category==='daily'
   ?`<span class="boss-stepper"><button class="btn" data-count="${esc(b.name)}" data-step="-1" aria-label="One fewer ${esc(b.name)} clear" ${b.count?'':'disabled'}>&minus;</button><span aria-live="polite">${b.count}/${b.limit}</span><button class="btn" data-count="${esc(b.name)}" data-step="1" aria-label="One more ${esc(b.name)} clear" ${b.count<b.limit?'':'disabled'}>+</button></span>`
   :`<input type="checkbox" data-clear="${esc(b.name)}" ${b.count||b.cleared_this_month?'checked':''} ${b.cleared_this_month?'disabled':''} aria-label="${esc(b.name)} cleared">`;
  const parties=Array.from({length:b.party_max},(_,i)=>`<option value="${i+1}" ${i+1===b.party?'selected':''}>${i+1}</option>`).join('');
  return `<li class="boss-row ${b.count>=b.limit||b.cleared_this_month?'is-done':''}">
   ${control}
   <span class="boss-name">${bossIcon(b.icon)}<span><strong>${esc(b.name)}</strong>${b.cleared_this_month?'<small>Cleared earlier this month</small>':over?'<small>Beyond your 14 most valuable weekly crystals; it will not sell</small>':''}</span></span>
   <label class="boss-party" title="Party size">Party <select class="input" data-party="${esc(b.category+':'+b.base)}">${parties}</select></label>
   <span class="boss-value" title="${full(b.value)} mesos each${b.category==='daily'?' per clear':''}">${mesos(b.value)}</span>
  </li>`;
 }

 function characterCard(c){
  const worlds=model.world_names.map(w=>`<option ${w===c.world?'selected':''}>${w}</option>`).join('');
  // Only the most valuable weekly crystals sell; the rows arrive sorted by value.
  const selling=new Set(c.bosses.filter(b=>b.category==='weekly').slice(0,model.weekly_limit).map(b=>b.name));
  const groups=['weekly','monthly','daily'].map(cat=>{
   const rows=c.bosses.filter(b=>b.category===cat);
   return rows.length?`<h3>${CATEGORY[cat]}${cat==='weekly'?` <span class="sub">${c.weekly_cleared} / ${Math.min(c.weekly_selected,model.weekly_limit)}</span>`:''}</h3><ul class="boss-list">${rows.map(b=>bossRow(c,b,selling)).join('')}</ul>`:'';
  }).join('');
  return `<section class="card boss-character">
   <header><img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt="" width="56" height="56"><div><h2>${esc(c.name)}</h2><p class="sub">${esc(c.class)}${c.level?' · Lv. '+c.level:''}</p></div>
    <label class="boss-world">World <select class="input" data-world>${c.world?'':'<option value="" selected>Choose…</option>'}${worlds}</select></label>
    <button class="btn" data-edit>Edit bosses</button></header>
   ${c.world?'':'<p class="sc-warning">Choose this character\'s world. Heroic worlds (Kronos, Hyperion) sell crystals for five times the Interactive price.</p>'}
   ${c.bosses.length?`<p class="boss-progress"><strong title="${full(c.earned)} of ${full(c.possible)} mesos">${mesos(c.earned)}</strong> <span class="sub">of ${mesos(c.possible)} this week</span></p>`+groups+`<div class="boss-actions"><button class="btn" data-all="1">Clear all weekly</button><button class="btn" data-all="0">Uncheck weekly</button></div>`:'<div class="boss-empty"><p>No bosses yet.</p><button class="btn btn-primary" data-edit>Choose bosses</button></div>'}
  </section>`;
 }

 function rosterCard(){
  return `<section class="card boss-roster"><h2>Roster</h2><ul>${model.characters.map(c=>`<li><button class="${c.id===me().id?'is-current':''}" data-character="${esc(c.id)}"><img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt="" width="36" height="36"><span><strong>${esc(c.name)}</strong><small>${c.bosses.length?`${c.weekly_cleared} / ${Math.min(c.weekly_selected,model.weekly_limit)} weekly${c.done?' · Done':''}`:'No bosses chosen'}</small></span>${c.bosses.length?`<span class="boss-value">${mesos(c.earned)}<small>${mesos(c.possible)}</small></span>`:''}</button></li>`).join('')}</ul>
   <h3>Recent weeks</h3><ul class="boss-history">${model.history.map((w,i)=>`<li><span>${i?new Date(w.week+'T00:00:00Z').toLocaleDateString(undefined,{month:'short',day:'numeric',timeZone:'UTC'}):'This week'}</span><span title="${full(w.mesos)} mesos">${mesos(w.mesos)}</span></li>`).join('')}</ul></section>`;
 }

 const itemById=name=>model.drop_items.find(i=>i.name===name);
 // Class-locked drops (Eternal gear, Mitra's Rage, spellbooks) show only the character's job branch.
 const usable=(item,character)=>{const branches=model.characters.find(c=>c.id===character)?.branches||[];return !item.classes.length||item.classes.some(c=>branches.includes(c));};
 function itemPicker(selected,character){
  const groups={};for(const item of model.drop_items)if(item===selected||usable(item,character))(groups[item.group]||=[]).push(item);
  return `<fieldset class="boss-items"><legend>Item</legend><input type="hidden" name="item" value="${esc(selected.name)}">
   <p class="boss-item-picked" aria-live="polite">${itemIcon(selected.id,32)}<span><strong>${esc(selected.name)}</strong><small>${esc(selected.boss||'Any boss')}</small></span></p>
   ${Object.entries(groups).map(([group,items])=>`<p class="eyebrow">${esc(group)}</p><div class="boss-item-grid">${items.map(i=>`<button type="button" class="boss-item ${i.name===selected.name?'is-selected':''}" data-item="${esc(i.name)}" aria-pressed="${i.name===selected.name}" title="${esc(i.name)}${i.boss?' · '+esc(i.boss):''}">${itemIcon(i.id,32,esc(i.name))}</button>`).join('')}</div>`).join('')}
  </fieldset>`;
 }
 function diary(){
  const filter=root.dataset.diaryFilter||'';
  const drops=[...model.drops].filter(d=>!filter||d.character===filter).sort((a,b)=>b.date.localeCompare(a.date));
  const counts={};for(const d of drops)counts[d.item]=(counts[d.item]||0)+1;
  const entry=editing?model.drops.find(d=>d.id===editing):null;
  const today=new Date();const local=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  const chosen=entry?.character||me().id;
  const item=itemById(entry?.item||root.dataset.diaryItem)||model.drop_items[0];
  const pictured=(name,size)=>{const i=itemById(name);return i?itemIcon(i.id,size):'';};
  return `<div class="boss-diary">
   <form class="card boss-log" data-log><h2>${entry?'Edit drop':'Log a drop'}</h2>
    <label>Character<select class="input" name="character">${model.characters.map(c=>`<option value="${esc(c.id)}" ${c.id===chosen?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>
    ${itemPicker(item,chosen)}
    <label>Date<input class="input" type="date" name="date" value="${esc(entry?.date||local)}" required></label>
    <label>Note<input class="input" name="note" maxlength="200" value="${esc(entry?.note||'')}" placeholder="Optional"></label>
    <footer>${entry?'<button class="btn" type="button" data-cancel-edit>Cancel</button>':''}<button class="btn btn-primary">${entry?'Save changes':'Log drop'}</button></footer>
   </form>
   <section class="card boss-drops"><header><h2>Drops</h2><select class="input" data-filter aria-label="Show drops for"><option value="">All characters</option>${model.characters.map(c=>`<option value="${esc(c.id)}" ${c.id===filter?'selected':''}>${esc(c.name)}</option>`).join('')}</select></header>
    ${drops.length?`<p class="boss-counts">${Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([name,n])=>`<span title="${esc(name)}">${pictured(name,20)}${esc(name)} <strong>&times;${n}</strong></span>`).join('')}</p>
    <table class="boss-table"><thead><tr><th>Date</th><th>Character</th><th>Item</th><th>Note</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${drops.map(d=>`<tr><td>${esc(new Date(d.date+'T00:00:00').toLocaleDateString())}</td><td>${esc(nameOf(d.character))}</td><td><span class="boss-drop-item">${pictured(d.item,32)}<span><strong>${esc(d.item)}</strong>${d.boss?`<small>${esc(d.boss)}</small>`:''}</span></span></td><td>${esc(d.note)}</td><td class="boss-row-actions"><button class="btn" data-edit-drop="${esc(d.id)}">Edit</button><button class="btn" data-delete-drop="${esc(d.id)}" aria-label="Delete ${esc(d.item)} drop">Delete</button></td></tr>`).join('')}</tbody></table>`
    :'<p class="sub">No drops logged yet.</p>'}
   </section></div>`;
 }

 function editor(c){
  const dialog=document.createElement('dialog');dialog.className='boss-editor';dialog.setAttribute('aria-label','Choose bosses for '+c.name);
  // Choices are per boss and category: Zakum can be both a daily and a weekly boss.
  const chosen=Object.fromEntries(c.bosses.map(b=>[b.category+':'+b.base,{difficulty:b.difficulty,party:b.party}]));
  const bases=[];for(const b of model.catalog){const key=b.category+':'+b.base;let group=bases.find(g=>g.key===key);if(!group)bases.push(group={key,base:b.base,category:b.category,variants:[]});group.variants.push(b);}
  let category='weekly';
  const heroic=!c.world||model.heroic.includes(c.world);
  const each=(b,party)=>Math.floor(b.mesos*(heroic?model.heroic_multiplier:1)/party);
  function draw(){
   const weekly=Object.keys(chosen).filter(key=>key.startsWith('weekly:')).length;
   // Redrawing replaces the list; keep its scroll position and the focused control.
   const top=dialog.querySelector('.boss-choices')?.scrollTop||0,focused=document.activeElement;
   const focus=dialog.contains(focused)&&['base','difficulty','size'].find(k=>focused.dataset?.[k]);
   const focusKey=focus&&focused.dataset[focus];
   dialog.innerHTML=`<h2>Bosses for ${esc(c.name)}</h2><p class="sub">${weekly} weekly bosses chosen. Only the ${model.weekly_limit} most valuable weekly crystals sell each week${weekly>model.weekly_limit?', so some of these will not':''}. Values are per party member${c.world?' in '+esc(c.world):''}.</p>
    <nav class="fl-subtabs" role="tablist">${Object.entries(CATEGORY).map(([key,label])=>`<button class="btn" role="tab" aria-selected="${key===category}" data-category="${key}">${label}</button>`).join('')}</nav>
    <ul class="boss-choices">${bases.filter(g=>g.category===category).map(g=>{
     const pick=chosen[g.key],variant=g.variants.find(v=>v.difficulty===pick?.difficulty)||g.variants[g.variants.length-1],party=pick?.party||1;
     return `<li class="${pick?'is-on':''}"><label class="boss-toggle"><input type="checkbox" data-base="${esc(g.key)}" ${pick?'checked':''}>${bossIcon(g.variants[0].icon,32)} ${esc(g.base)}</label>
      <select class="input" data-difficulty="${esc(g.key)}" aria-label="${esc(g.base)} difficulty">${g.variants.map(v=>`<option ${v===variant?'selected':''}>${v.difficulty}</option>`).join('')}</select>
      <select class="input" data-size="${esc(g.key)}" aria-label="${esc(g.base)} party size">${Array.from({length:variant.party_max},(_,i)=>`<option value="${i+1}" ${i+1===party?'selected':''}>${i+1} ${i?'players':'player'}</option>`).join('')}</select>
      <span class="boss-value">${mesos(each(variant,Math.min(party,variant.party_max)))}</span></li>`;}).join('')}</ul>
    <footer><button class="btn" data-cancel>Cancel</button><button class="btn btn-primary" data-save>Save bosses</button></footer>`;
   dialog.querySelector('.boss-choices').scrollTop=top;
   if(focus)dialog.querySelector(`[data-${focus}="${CSS.escape(focusKey)}"]`)?.focus({preventScroll:true});
   dialog.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{category=b.dataset.category;draw();dialog.querySelector('.boss-choices').scrollTop=0;});
   const read=key=>{const g=bases.find(x=>x.key===key);const difficulty=dialog.querySelector(`[data-difficulty="${CSS.escape(key)}"]`).value;const v=g.variants.find(x=>x.difficulty===difficulty);return {difficulty,party:Math.min(Number(dialog.querySelector(`[data-size="${CSS.escape(key)}"]`).value),v.party_max)};};
   dialog.querySelectorAll('[data-base]').forEach(box=>box.onchange=()=>{if(box.checked)chosen[box.dataset.base]=read(box.dataset.base);else delete chosen[box.dataset.base];draw();});
   dialog.querySelectorAll('[data-difficulty],[data-size]').forEach(select=>select.onchange=()=>{const base=select.dataset.difficulty||select.dataset.size;chosen[base]=read(base);draw();});
   dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
   dialog.querySelector('[data-save]').onclick=async()=>{await save(api.put(`/api/bossing/characters/${encodeURIComponent(c.id)}`,{bosses:chosen}));dialog.close();};
  }
  draw();document.body.append(dialog);dialog.showModal();
  dialog.addEventListener('close',()=>dialog.remove(),{once:true});
 }

 function draw(){
  if(!alive())return;
  const c=me();
  root.innerHTML=`<div class="page-head"><div><h1>Bossing</h1><p class="sub">Weekly reset in <strong data-countdown></strong> (Thursday 00:00 UTC) · Black Mage resets ${esc(new Date(model.monthly_reset).toLocaleDateString(undefined,{month:'short',day:'numeric',timeZone:'UTC'}))}</p></div></div>
   <nav class="fl-subtabs" role="tablist" aria-label="Bossing view"><button class="btn" role="tab" data-tab="tracker" aria-selected="${tab==='tracker'}">Weekly bosses</button><button class="btn" role="tab" data-tab="diary" aria-selected="${tab==='diary'}">Drop diary</button></nav>
   ${!c?'<section class="card boss-empty"><p>Add a character to start tracking bosses.</p></section>':tab==='tracker'?summary()+`<div class="boss-layout">${characterCard(c)}${rosterCard()}</div>`:diary()}`;
  countdown();
  root.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;try{localStorage.setItem('hascone.bossing.tab',tab);}catch{}draw();});
  if(!c)return;
  const base=`/api/bossing/characters/${encodeURIComponent(c.id)}`;
  const bosses=()=>Object.fromEntries(c.bosses.map(b=>[b.category+':'+b.base,{difficulty:b.difficulty,party:b.party}]));
  root.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>editor(c));
  root.querySelector('[data-world]')?.addEventListener('change',e=>save(api.put(base,{world:e.target.value||null})));
  root.querySelectorAll('[data-clear]').forEach(box=>box.onchange=()=>save(api.put(base+'/clears',{boss:box.dataset.clear,count:box.checked?1:0})));
  // A click anywhere on a weekly or monthly row toggles it; the party picker and checkbox keep their own clicks.
  root.querySelectorAll('.boss-row').forEach(row=>{
   const box=row.querySelector('[data-clear]');
   if(!box||box.disabled)return;
   row.classList.add('is-toggle');
   row.onclick=e=>{if(e.target.closest('input,select,button,label'))return;box.checked=!box.checked;box.dispatchEvent(new Event('change'));};
  });
  root.querySelectorAll('[data-count]').forEach(b=>b.onclick=()=>{const boss=c.bosses.find(x=>x.name===b.dataset.count);save(api.put(base+'/clears',{boss:boss.name,count:boss.count+Number(b.dataset.step)}));});
  root.querySelectorAll('[data-party]').forEach(select=>select.onchange=()=>save(api.put(base,{bosses:{...bosses(),[select.dataset.party]:{...bosses()[select.dataset.party],party:Number(select.value)}}})));
  root.querySelectorAll('[data-all]').forEach(b=>b.onclick=async()=>{
   const targets=c.bosses.filter(x=>x.category==='weekly'&&Boolean(x.count)!==(b.dataset.all==='1'));
   for(const boss of targets){try{model=await api.put(base+'/clears',{boss:boss.name,count:Number(b.dataset.all)});}catch(error){toast(error.message);break;}}
   draw();
  });
  root.querySelectorAll('.boss-roster [data-character]').forEach(b=>b.onclick=()=>onSelect(b.dataset.character));
  const form=root.querySelector('[data-log]');
  if(form){
   // Picking an icon updates the form in place so the date and note are kept.
   const bindItems=()=>form.querySelectorAll('[data-item]').forEach(button=>button.onclick=()=>{
    const item=itemById(button.dataset.item);root.dataset.diaryItem=item.name;form.item.value=item.name;
    form.querySelectorAll('[data-item]').forEach(b=>{const on=b===button;b.classList.toggle('is-selected',on);b.setAttribute('aria-pressed',String(on));});
    form.querySelector('.boss-item-picked').innerHTML=`${itemIcon(item.id,32)}<span><strong>${esc(item.name)}</strong><small>${esc(item.boss||'Any boss')}</small></span>`;
   });
   bindItems();
   // Another character may use a different class's gear; keep the pick when it still applies.
   form.character.onchange=()=>{
    const current=itemById(form.item.value);
    const item=usable(current,form.character.value)?current:model.drop_items.find(i=>i.group===current.group&&usable(i,form.character.value))||model.drop_items[0];
    root.dataset.diaryItem=item.name;
    form.querySelector('.boss-items').outerHTML=itemPicker(item,form.character.value);
    bindItems();
   };
   form.onsubmit=async e=>{
    e.preventDefault();
    const body={character:form.character.value,item:form.item.value,date:form.date.value,note:form.note.value};
    const id=editing;editing=null;
    await save(id?api.put('/api/bossing/drops/'+id,body):api.post('/api/bossing/drops',body));
    toast(id?'Drop updated.':'Drop logged.');
   };
   form.querySelector('[data-cancel-edit]')?.addEventListener('click',()=>{editing=null;draw();});
  }
  root.querySelector('[data-filter]')?.addEventListener('change',e=>{root.dataset.diaryFilter=e.target.value;draw();});
  root.querySelectorAll('[data-edit-drop]').forEach(b=>b.onclick=()=>{editing=b.dataset.editDrop;draw();root.querySelector('[data-log]')?.scrollIntoView({block:'nearest'});});
  root.querySelectorAll('[data-delete-drop]').forEach(b=>b.onclick=()=>{
   const drop=model.drops.find(d=>d.id===b.dataset.deleteDrop);
   const dialog=document.createElement('dialog');dialog.className='delete-character-dialog';dialog.setAttribute('aria-label','Delete drop');
   dialog.innerHTML=`<h2>Delete this drop?</h2><p>${esc(drop.item)} for ${esc(nameOf(drop.character))} on ${esc(new Date(drop.date+'T00:00:00').toLocaleDateString())}.</p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn delete-confirm">Delete drop</button></footer>`;
   document.body.append(dialog);dialog.showModal();
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
   dialog.querySelector('.delete-confirm').onclick=async()=>{dialog.close();await save(api.delete('/api/bossing/drops/'+drop.id));};
  });
 }

 try{model=await api.get('/api/bossing');}
 catch(error){if(alive())root.innerHTML=`<p class="sc-warning">${esc(error.message)}</p>`;return ()=>{disposed=true;};}
 if(!alive())return ()=>{disposed=true;};
 draw();
 timer=setInterval(countdown,30000);
 return ()=>{disposed=true;clearInterval(timer);};
}
