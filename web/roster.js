import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

const HEXAGON='<svg width="11" height="11" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.6" stroke-linejoin="round" d="M12 2.5 20.5 7.25v9.5L12 21.5l-8.5-4.75v-9.5z"/></svg>';
const compact=value=>Number(value).toLocaleString(undefined,{notation:'compact',maximumFractionDigits:1});

// A permanent, scrollable roster: every character with their headline numbers and scan progress.
// Narrow windows turn it into a slide-out drawer with an edge tab.
export function mountRoster(onSelect){
 const rail=document.querySelector('#roster');
 rail.innerHTML=`<div class="roster-head"><div><span class="eyebrow">Roster</span><strong class="roster-total"></strong></div><span class="roster-actions"><button class="roster-add" type="button" aria-label="Add character" title="Add character"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button><button class="roster-hide" type="button" aria-label="Hide roster" title="Hide roster"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m11 17-5-5 5-5M18 17l-5-5 5-5"/></svg></button></span></div>
  <label class="roster-search" hidden><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="search" placeholder="Search name or class" aria-label="Search characters" autocomplete="off"></label>
  <div class="roster-list" role="list"></div><div class="roster-foot" aria-label="Roster totals"></div>`;
 const list=rail.querySelector('.roster-list'),search=rail.querySelector('.roster-search input');
 const tab=document.createElement('button');
 tab.className='roster-tab';tab.type='button';tab.setAttribute('aria-controls','roster');tab.setAttribute('aria-label','Characters');
 tab.innerHTML='<span class="roster-arrow" aria-hidden="true"></span><span class="roster-count"></span>';
 document.body.append(tab);
 let characters=[],stats={},selected=null,queues={},previous='',filter='',statsTimer=0;
 const label=key=>key.replaceAll('_',' ').replaceAll(':',' / ');
 // Wide windows dock the roster beside the page; it can be hidden and shown again from the edge tab.
 // Narrow windows slide it over the page instead.
 const narrow=()=>matchMedia('(max-width:950px)').matches;
 let collapsed=false;
 try{collapsed=localStorage.getItem('hascone.roster.hidden')==='1';}catch{}
 // The tab reports whether the roster is visible in the current mode.
 const syncTab=()=>{const shown=narrow()?rail.classList.contains('is-open'):!collapsed;tab.setAttribute('aria-expanded',String(shown));tab.title=shown?'Characters':'Show roster';};
 const setOpen=open=>{rail.classList.toggle('is-open',open);syncTab();};
 function setHidden(hidden){
  collapsed=hidden;document.body.classList.toggle('roster-hidden',hidden);syncTab();
  try{localStorage.setItem('hascone.roster.hidden',hidden?'1':'0');}catch{}
 }
 setHidden(collapsed);
 matchMedia('(max-width:950px)').addEventListener('change',()=>{setOpen(false);syncTab();});
 function status(q){
  const busy=!!q?.pending.length;
  const progress=q&&(busy||q.done.length)?`<p class="roster-progress" role="status">${q.done.length} saved · ${q.pending.length} processing${busy?q.active?' · Reading '+esc(label(q.active))+' · '+q.elapsed+'s'+(q.elapsed>=30?' (first use loads the model)':''):' · Queued':''}</p>`:'';
  return progress+Object.entries(q?.failed||{}).map(([step,error])=>`<p class="roster-failure">${esc(label(step))}: ${esc(error)} Rescan this step.</p>`).join('');
 }
 function row(c){
  const s=stats[c.id]||{},q=queues[c.id],busy=!!q?.pending.length,failed=Object.keys(q?.failed||{}).length,current=c.id===selected;
  const fragments=s.fragments==null?'':`<span class="roster-chip" title="Sol Erda Fragments on HEXA${s.fragments_partial||s.fragments_minimum?' (at least)':''}">${HEXAGON}${s.fragments_partial||s.fragments_minimum?'≥':''}${compact(s.fragments)}</span>`;
  return `<div class="roster-row ${current?'is-selected':''} ${busy?'is-busy':''}" role="listitem"><button class="roster-item" type="button" data-character="${esc(c.id)}" ${current?'aria-current="true"':''}>
   <span class="roster-avatar"><img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt="" loading="lazy"></span>
   <span class="roster-info"><span class="roster-name">${esc(c.name)}</span><span class="roster-meta">${esc(c.class)}${s.level?' · Lv. '+esc(s.level):''}</span>
    <span class="roster-chips">${s.hexa!=null?`<span class="roster-chip is-hexa" title="HEXA score · 380 DEF${s.stale?' · inputs changed since':''}">${compact(s.hexa)}</span>`:''}${fragments}</span></span>
   ${busy?'<span class="scan-spinner roster-state" aria-label="Processing"></span>':failed?`<span class="roster-state roster-alert" title="${failed} reading${failed>1?'s':''} to rescan">${failed}</span>`:''}
  </button>${status(q)}</div>`;
 }
 function draw(){
  const focused=document.activeElement?.dataset?.character;
  const pending=Object.values(queues).reduce((sum,q)=>sum+q.pending.length,0);
  const failures=Object.values(queues).reduce((sum,q)=>sum+Object.keys(q.failed).length,0);
  tab.querySelector('.roster-count').innerHTML=pending?`<span class="scan-spinner" aria-label="Processing"></span>${pending}`:failures?'!':'';
  rail.querySelector('.roster-total').textContent=characters.length?String(characters.length):'';
  rail.querySelector('.roster-search').hidden=characters.length<6;
  const shown=characters.filter(c=>!filter||`${c.name} ${c.class}`.toLowerCase().includes(filter));
  list.innerHTML=shown.map(row).join('')||`<p class="roster-empty">${characters.length?'No characters match.':'Add a character to begin.'}</p>`;
  // Roster totals; fragments are a lower bound when any character's HEXA is partial or unsupported.
  const rows=characters.map(c=>stats[c.id]).filter(Boolean),fragments=rows.reduce((n,s)=>n+(s.fragments||0),0);
  const lower=rows.some(s=>s.fragments==null||s.fragments_partial||s.fragments_minimum);
  rail.querySelector('.roster-foot').innerHTML=fragments?`<span class="eyebrow">Total</span><span class="roster-chip" title="Sol Erda Fragments on HEXA across the roster${lower?' (at least)':''}">${HEXAGON}${lower?'≥':''}${compact(fragments)}</span>`:'';
  list.querySelectorAll('[data-character]').forEach(b=>b.onclick=()=>{setOpen(false);onSelect(b.dataset.character).catch(toast);});
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
 rail.querySelector('.roster-add').onclick=()=>{setOpen(false);document.querySelector('#add-character').click();};
 search.oninput=()=>{filter=search.value.trim().toLowerCase();draw();};
 // Arrow keys move between characters, like a list.
 list.addEventListener('keydown',e=>{
  if(!['ArrowDown','ArrowUp'].includes(e.key))return;
  const items=[...list.querySelectorAll('[data-character]')],index=items.indexOf(document.activeElement);
  if(index<0)return;
  e.preventDefault();items[Math.max(0,Math.min(items.length-1,index+(e.key==='ArrowDown'?1:-1)))].focus();
 });
 tab.onclick=()=>narrow()?setOpen(!rail.classList.contains('is-open')):setHidden(false);
 rail.querySelector('.roster-hide').onclick=()=>narrow()?setOpen(false):setHidden(true);
 document.addEventListener('pointerdown',e=>{if(rail.classList.contains('is-open')&&!rail.contains(e.target)&&!tab.contains(e.target))setOpen(false);});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false);});
 return {update(rows,id){
  const moved=id!==selected;characters=rows;selected=id;draw();scheduleStats();
  // Keep the current character in view when it changes elsewhere, e.g. the header picker.
  if(moved)list.querySelector('.is-selected')?.scrollIntoView({block:'nearest'});
 }};
}
