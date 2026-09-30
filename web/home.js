import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';
import {refreshButton} from './portrait.js';
import {compactCost} from './format.js';
// Gear values last shown, kept between visits so returning to the overview doesn't blank them.
const known=new Map();
const VALUE_NOTE='Expected mesos to rebuild this gear: Star Force from 0, flames and the cheaper of Bright or Glowing cubes.';
export async function mountHome(root,onSelect,onDeleted){
 const data=await api.get('/api/summary');
 if(!root.isConnected)return;
 const lower=p=>p.fragments_partial||p.fragments_minimum;
 const fragmentNote=p=>esc(['Sol Erda Fragments spent on HEXA levels',p.fragments_partial&&'some HEXA levels are not scanned yet',p.fragments_minimum&&'completed HEXA Stat cores count at their minimum cost'].filter(Boolean).join('; ')+'.');
 // An account overview: each character's headline numbers, with roster totals pinned to the bottom of the window.
 root.classList.add('home-page');
 root.innerHTML=`<div class="intro home-intro"><span class="eyebrow">YOUR ROSTER</span><h1>Account overview</h1><p>Pick a character to view equipment and plan your next upgrade.${data.profiles.length>1?' Drag cards to reorder them.':''}</p></div><div class="roster-grid">${data.profiles.map(p=>`<article class="roster-tile"><button class="roster-card" data-character="${p.id}" draggable="true" title="Drag to reorder · Alt+Arrow keys also move it"><img src="/api/characters/${p.id}/portrait" alt="" width="120" height="150"><div class="roster-text"><h2>${esc(p.name)}</h2><span class="sub">${esc(p.class)}${p.level?' &middot; Lv. '+p.level:''}</span>${p.cp?`<span class="roster-cp" title="Combat Power from the latest Character Info scan">CP ${Number(p.cp).toLocaleString()}</span>`:''}<strong class="roster-score">${p.hexa==null?'Not calculated':Number(p.hexa).toLocaleString()}</strong><span class="eyebrow roster-score-label">HEXA &middot; 380 DEF</span><span class="roster-value">${p.fragments==null?'':`<span class="roster-stat" title="${fragmentNote(p)}"><img src="/static/sol-erda-fragment.png" alt="Sol Erda Fragments" width="20" height="20">${lower(p)?'&ge; ':''}${Number(p.fragments).toLocaleString()}</span>`}<span class="roster-stat"><img src="/static/meso.png" alt="Mesos" width="20" height="20"><span data-meso="${p.id}">&hellip;</span></span></span></div></button>${refreshButton(p.id,p.name)}<button class="roster-delete" data-delete="${p.id}" aria-label="Delete ${esc(p.name)}" title="Delete character"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></button></article>`).join('')}<button class="roster-new" type="button" aria-label="Add character" title="Add character"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 4v16M4 12h16"/></svg></button></div>${data.profiles.length?'<div class="home-totals" role="region" aria-label="Account totals"><span class="eyebrow">Account total</span><span class="roster-stat"><img src="/static/sol-erda-fragment.png" alt="Sol Erda Fragments" width="20" height="20"><span id="home-fragments"></span></span><span class="roster-stat"><img src="/static/meso.png" alt="Mesos" width="20" height="20"><span id="home-mesos"></span></span><span class="home-zoom">Zoom: Ctrl + mouse wheel &middot; Reset: Ctrl + 0</span></div>':''}`;
 const fragments=data.profiles.reduce((sum,p)=>sum+(p.fragments||0),0),fragmentsLower=data.profiles.some(p=>p.fragments==null||lower(p));
 function drawTotals(){
  const f=root.querySelector('#home-fragments'),m=root.querySelector('#home-mesos');if(!f)return;
  f.textContent=`${fragmentsLower?'≥ ':''}${fragments.toLocaleString()}`;
  f.title=fragmentsLower?'Some characters have unscanned or unsupported HEXA, so this is a minimum.':'Sol Erda Fragments spent on HEXA across the roster.';
  const values=data.profiles.map(p=>known.get(p.id)),pending=values.filter(v=>!v).length;
  const total=values.reduce((sum,v)=>sum+(v?.mesos||0),0),lower=values.some(v=>v&&(v.partial||v.failed));
  m.textContent=pending?`${compactCost(total)} · valuing ${data.profiles.length-pending+1} of ${data.profiles.length}…`:`${lower?'≥ ':''}${compactCost(total)}`;
  m.title=VALUE_NOTE.replace('this gear','every character\'s current gear')+(lower?' Some items are not priced yet, so this is a minimum.':'');
 }
 function drawValue(p){
  const cell=root.querySelector(`[data-meso="${CSS.escape(p.id)}"]`),value=known.get(p.id);
  if(!cell||!value)return;
  if(value.failed){cell.textContent='Value unavailable';return;}
  cell.textContent=`${value.partial?'≥ ':''}${compactCost(value.mesos)}`;
  cell.title=VALUE_NOTE+(value.partial?' Some items are not priced yet, so this is a minimum.':'');
 }
 // Show the last known values at once, then refresh each quietly; unchanged gear is answered from the server's cache.
 async function loadValues(){
  for(const p of data.profiles){
   if(!root.isConnected)return;
   try{known.set(p.id,await api.get(`/api/characters/${encodeURIComponent(p.id)}/gear-value`));}
   catch{if(!known.has(p.id))known.set(p.id,{failed:true});}
   drawValue(p);drawTotals();
  }
 }
 data.profiles.forEach(drawValue);drawTotals();loadValues();
 root.querySelectorAll('[data-delete]').forEach(button=>button.onclick=()=>{
  const character=data.profiles.find(p=>p.id===button.dataset.delete);
  const dialog=document.createElement('dialog');dialog.className='delete-character-dialog';
  dialog.setAttribute('aria-label','Delete '+character.name);
  dialog.innerHTML=`<h2>Delete ${esc(character.name)}?</h2><p>This removes their equipment scans, saved stats, Scouter snapshots, and settings from Hascone. It does not affect your character in MapleStory.</p><p class="sub">This cannot be undone. Adding them again starts a new profile.</p><p class="warn" role="alert"></p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn delete-confirm">Delete character</button></footer>`;
  document.body.append(dialog);dialog.showModal();
  dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
  dialog.querySelector('.delete-confirm').onclick=async e=>{
   const confirm=e.currentTarget;confirm.disabled=true;confirm.textContent='Deleting...';
   try{await api.delete('/api/characters/'+character.id);dialog.close();await onDeleted();toast(character.name+' deleted.');}
   catch(error){dialog.querySelector('[role="alert"]').textContent=error.message;confirm.disabled=false;confirm.textContent='Delete character';}
  };
 });
 const grid=root.querySelector('.roster-grid');
 grid.querySelector('.roster-new').onclick=()=>document.querySelector('#add-dialog').showModal();
 let dragged=null,moved=false;
 const order=()=>[...grid.querySelectorAll('[data-character]')].map(b=>b.dataset.character);
 let saved=order().join();
 async function persist(){
  const next=order();if(next.join()===saved)return;
  try{await api.post('/api/characters/order',{order:next});saved=next.join();}
  catch(e){toast(e.message,'danger');}
 }
 // The card under the pointer, and whether to drop before or after it.
 function target(x,y){
  let best=null,distance=Infinity;
  for(const card of grid.querySelectorAll('.roster-tile')){
   if(card===dragged)continue;
   const r=card.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2,d=(x-cx)**2+(y-cy)**2;
   if(d<distance){distance=d;best={card,after:y>r.bottom||(y>=r.top&&x>cx)};}
  }
  return best;
 }
 grid.querySelectorAll('[data-character]').forEach(b=>{
  const tile=b.closest('.roster-tile');
  b.onclick=()=>{if(!moved)onSelect(b.dataset.character);};
  b.ondragstart=e=>{dragged=tile;moved=false;tile.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',b.dataset.character);};
  b.ondragend=()=>{tile.classList.remove('dragging');dragged=null;persist();setTimeout(()=>{moved=false;},0);};
  b.onkeydown=e=>{
   if(!e.altKey||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
   e.preventDefault();
   const back=['ArrowLeft','ArrowUp'].includes(e.key),sibling=back?tile.previousElementSibling:tile.nextElementSibling;
   if(!sibling?.classList.contains('roster-tile'))return;
   back?sibling.before(tile):sibling.after(tile);b.focus();persist();
  };
 });
 grid.ondragover=e=>{
  if(!dragged)return;e.preventDefault();e.dataTransfer.dropEffect='move';
  const t=target(e.clientX,e.clientY);if(!t)return;
  const before=t.after?t.card.nextElementSibling:t.card;
  if(before!==dragged&&before!==dragged.nextElementSibling||!before){grid.insertBefore(dragged,before);moved=true;}
 };
 grid.ondrop=e=>e.preventDefault();
}
