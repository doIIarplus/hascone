import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

// A slim, permanent roster rail: one avatar per character, with details in its tooltip.
// It docks beside the page and can be hidden, then shown again from the edge tab.
export function mountRoster(onSelect){
 const rail=document.querySelector('#roster');
 rail.innerHTML=`<div class="roster-head"><span class="eyebrow">Roster <strong class="roster-total"></strong></span><span class="roster-actions"><button class="roster-add" type="button" aria-label="Add character" title="Add character"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button><button class="roster-hide" type="button" aria-label="Hide roster" title="Hide roster"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m11 17-5-5 5-5M18 17l-5-5 5-5"/></svg></button></span></div>
  <div class="roster-list" role="list"></div>`;
 const list=rail.querySelector('.roster-list');
 const tab=document.createElement('button');
 tab.className='roster-tab';tab.type='button';tab.setAttribute('aria-controls','roster');tab.title='Show roster';tab.setAttribute('aria-label','Show roster');
 tab.innerHTML='<span class="roster-arrow" aria-hidden="true"></span><span class="roster-count"></span>';
 document.body.append(tab);
 let characters=[],stats={},selected=null,queues={},previous='',statsTimer=0,hidden=false;
 try{hidden=localStorage.getItem('hascone.roster.hidden')==='1';}catch{}
 const label=key=>key.replaceAll('_',' ').replaceAll(':',' / ');
 function setHidden(value){
  hidden=value;document.body.classList.toggle('roster-hidden',value);tab.setAttribute('aria-expanded',String(!value));
  try{localStorage.setItem('hascone.roster.hidden',value?'1':'0');}catch{}
 }
 setHidden(hidden);
 // Name, class, level, headline numbers and any scan progress, for the avatar's tooltip.
 function details(c){
  const s=stats[c.id]||{},q=queues[c.id],busy=!!q?.pending.length,lines=[c.name,`${c.class}${s.level?' · Lv. '+s.level:''}`];
  const numbers=[s.hexa!=null&&`HEXA ${Number(s.hexa).toLocaleString()}`,s.fragments!=null&&`${s.fragments_partial||s.fragments_minimum?'≥ ':''}${Number(s.fragments).toLocaleString()} fragments`].filter(Boolean);
  if(numbers.length)lines.push(numbers.join(' · '));
  if(q&&(busy||q.done.length))lines.push(`${q.done.length} saved · ${q.pending.length} processing${busy?q.active?' · Reading '+label(q.active)+' · '+q.elapsed+'s':' · Queued':''}`);
  for(const [step,error] of Object.entries(q?.failed||{}))lines.push(`${label(step)}: ${error} Rescan this step.`);
  return lines.join('\n');
 }
 function row(c){
  const q=queues[c.id],busy=!!q?.pending.length,failed=Object.keys(q?.failed||{}).length,current=c.id===selected;
  return `<div class="roster-row ${current?'is-selected':''}" role="listitem"><button class="roster-item" type="button" data-character="${esc(c.id)}" title="${esc(details(c))}" aria-label="${esc(details(c))}" ${current?'aria-current="true"':''}>
   <img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt="" loading="lazy">
   ${busy?'<span class="scan-spinner roster-state" aria-hidden="true"></span>':failed?`<span class="roster-state roster-alert" aria-hidden="true">${failed}</span>`:''}
  </button></div>`;
 }
 function draw(){
  const focused=document.activeElement?.dataset?.character;
  const pending=Object.values(queues).reduce((sum,q)=>sum+q.pending.length,0);
  const failures=Object.values(queues).reduce((sum,q)=>sum+Object.keys(q.failed).length,0);
  tab.querySelector('.roster-count').innerHTML=pending?`<span class="scan-spinner" aria-label="Processing"></span>${pending}`:failures?'!':'';
  rail.querySelector('.roster-total').textContent=characters.length?String(characters.length):'';
  list.innerHTML=characters.map(row).join('')||'<p class="roster-empty">Add a character to begin.</p>';
  list.querySelectorAll('[data-character]').forEach(b=>b.onclick=()=>onSelect(b.dataset.character).catch(toast));
  if(focused)list.querySelector(`[data-character="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
 }
 async function refreshStats(){
  try{const data=await api.get('/api/summary');stats=Object.fromEntries(data.profiles.map(p=>[p.id,p]));draw();}catch{}
 }
 const scheduleStats=()=>{clearTimeout(statsTimer);statsTimer=setTimeout(refreshStats,250);};
 async function poll(){
  try{
   const next=await api.get('/api/scan/queues'),encoded=JSON.stringify(next);
   if(encoded!==previous){
    for(const [id,q] of Object.entries(next))if(queues[id]?.pending.length&&!q.pending.length){toast(`${characters.find(c=>c.id===id)?.name||'Character'}: processing finished${Object.keys(q.failed).length?' with readings to rescan':''}.`);scheduleStats();}
    queues=next;previous=encoded;draw();
   }
  }catch{previous='';tab.querySelector('.roster-count').innerHTML='<span title="Scanner offline" aria-label="Scanner offline">!</span>';}
  setTimeout(poll,1000);
 }
 poll();
 rail.querySelector('.roster-add').onclick=()=>document.querySelector('#add-character').click();
 rail.querySelector('.roster-hide').onclick=()=>setHidden(true);
 tab.onclick=()=>setHidden(false);
 // Arrow keys move between characters, like a list.
 list.addEventListener('keydown',e=>{
  if(!['ArrowDown','ArrowUp'].includes(e.key))return;
  const items=[...list.querySelectorAll('[data-character]')],index=items.indexOf(document.activeElement);
  if(index<0)return;
  e.preventDefault();items[Math.max(0,Math.min(items.length-1,index+(e.key==='ArrowDown'?1:-1)))].focus();
 });
 return {update(rows,id){
  const moved=id!==selected;characters=rows;selected=id;draw();scheduleStats();
  // Keep the current character in view when it changes elsewhere, e.g. the header picker.
  if(moved)list.querySelector('.is-selected')?.scrollIntoView({block:'nearest'});
 }};
}
