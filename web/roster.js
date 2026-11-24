import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

// A slim, permanent roster rail: one avatar per character, with details in its tooltip.
// It docks beside the page; the tab on its edge minimises it to a strip that keeps Home.
// Seasonal pages pinned above the characters, opened like a character tile.
const QUANAH='quanah';
const quanahIcon='<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.5 14.6 9l6.9.4-5.3 4.4 1.7 6.7L12 16.8l-5.9 3.7 1.7-6.7-5.3-4.4L9.4 9Z"/></svg>';

export function mountRoster(onSelect,onQuanah=()=>Promise.resolve()){
 const rail=document.querySelector('#roster');
 rail.innerHTML=`<div class="roster-head"><span class="eyebrow">Roster <strong class="roster-total"></strong></span><span class="roster-actions"><button class="roster-home" type="button" aria-label="Home - account overview" title="Home - account overview"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M3 11 12 3l9 8M5 9.5V21h5v-6h4v6h5V9.5"/></svg></button></span><span class="roster-count"></span><button class="roster-toggle" type="button" aria-controls="roster"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="m11 17-5-5 5-5M18 17l-5-5 5-5"/></svg></button></div>
  <div class="roster-list" role="list"></div>`;
 const list=rail.querySelector('.roster-list');
 const toggle=rail.querySelector('.roster-toggle'),count=rail.querySelector('.roster-count');
 let characters=[],stats={},selected=null,queues={},previous='',statsTimer=0,hidden=false,quanahOpen=false;
 try{hidden=localStorage.getItem('hascone.roster.hidden')==='1';}catch{}
 const label=key=>key.replaceAll('_',' ').replaceAll(':',' / ');
 function setHidden(value){
  hidden=value;document.body.classList.toggle('roster-hidden',value);
  const text=value?'Show roster':'Minimise roster';toggle.title=text;toggle.setAttribute('aria-label',text);toggle.setAttribute('aria-expanded',String(!value));
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
 function quanahRow(){
  const q=queues[QUANAH],busy=!!q?.pending.length;
  const text=['Quanah · event set solver',q&&(busy||q.done.length)?`${q.done.length} saved · ${q.pending.length} processing`:''].filter(Boolean).join('\n');
  return `<div class="roster-row roster-seasonal ${quanahOpen?'is-selected':''}" role="listitem"><button class="roster-item roster-quanah" type="button" data-seasonal="quanah" title="${esc(text)}" aria-label="${esc(text)}" ${quanahOpen?'aria-current="true"':''}>
   ${quanahIcon}<span class="roster-seasonal-label">Quanah</span>
   ${busy?'<span class="scan-spinner roster-state" aria-hidden="true"></span>':''}
  </button></div>`;
 }
 function row(c){
  const q=queues[c.id],busy=!!q?.pending.length,failed=Object.keys(q?.failed||{}).length,current=!quanahOpen&&c.id===selected;
  return `<div class="roster-row ${current?'is-selected':''}" role="listitem"><button class="roster-item" type="button" data-character="${esc(c.id)}" title="${esc(details(c))}" aria-label="${esc(details(c))}" ${current?'aria-current="true"':''}>
   <img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt="" loading="lazy">
   ${busy?'<span class="scan-spinner roster-state" aria-hidden="true"></span>':failed?`<span class="roster-state roster-alert" aria-hidden="true">${failed}</span>`:''}
  </button></div>`;
 }
 function draw(){
  const focused=document.activeElement?.dataset?.character;
  const pending=Object.values(queues).reduce((sum,q)=>sum+q.pending.length,0);
  const failures=Object.values(queues).reduce((sum,q)=>sum+Object.keys(q.failed).length,0);
  count.innerHTML=pending?`<span class="scan-spinner" aria-hidden="true"></span>${pending}`:failures?'!':'';
  count.title=pending?`${pending} processing`:failures?'Some readings need a rescan':'';
  rail.querySelector('.roster-total').textContent=characters.length?String(characters.length):'';
  const seasonalFocused=document.activeElement?.dataset?.seasonal;
  list.innerHTML=quanahRow()+(characters.map(row).join('')||'<p class="roster-empty">Add a character to begin.</p>');
  list.querySelectorAll('[data-character]').forEach(b=>b.onclick=()=>onSelect(b.dataset.character).catch(toast));
  list.querySelector('[data-seasonal="quanah"]').onclick=()=>onQuanah().catch(toast);
  if(focused)list.querySelector(`[data-character="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
  if(seasonalFocused)list.querySelector(`[data-seasonal="${CSS.escape(seasonalFocused)}"]`)?.focus({preventScroll:true});
 }
 async function refreshStats(){
  try{const data=await api.get('/api/summary');stats=Object.fromEntries(data.profiles.map(p=>[p.id,p]));draw();}catch{}
 }
 const scheduleStats=()=>{clearTimeout(statsTimer);statsTimer=setTimeout(refreshStats,250);};
 async function poll(){
  try{
   const next=await api.get('/api/scan/queues'),encoded=JSON.stringify(next);
   if(encoded!==previous){
    for(const [id,q] of Object.entries(next))if(queues[id]?.pending.length&&!q.pending.length){toast(`${id===QUANAH?'Quanah':characters.find(c=>c.id===id)?.name||'Character'}: processing finished${Object.keys(q.failed).length?' with readings to rescan':''}.`);scheduleStats();}
    queues=next;previous=encoded;draw();
   }
  }catch{previous='';count.textContent='!';count.title='Scanner offline';}
  setTimeout(poll,1000);
 }
 poll();
 rail.querySelector('.roster-home').onclick=()=>document.querySelector('#home').click();
 toggle.onclick=()=>setHidden(!hidden);
 // Arrow keys move between characters, like a list.
 list.addEventListener('keydown',e=>{
  if(!['ArrowDown','ArrowUp'].includes(e.key))return;
  const items=[...list.querySelectorAll('[data-character],[data-seasonal]')],index=items.indexOf(document.activeElement);
  if(index<0)return;
  e.preventDefault();items[Math.max(0,Math.min(items.length-1,index+(e.key==='ArrowDown'?1:-1)))].focus();
 });
 return {update(rows,id,seasonal=null){
  const moved=id!==selected;characters=rows;selected=id;quanahOpen=seasonal===QUANAH;draw();scheduleStats();
  // Keep the current character in view when it changes elsewhere, e.g. the header picker.
  if(moved)list.querySelector('.is-selected')?.scrollIntoView({block:'nearest'});
 }};
}
