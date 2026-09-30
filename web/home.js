import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';
export async function mountHome(root,onSelect,onDeleted){
 const data=await api.get('/api/summary');
 if(!root.isConnected)return;
 root.innerHTML=`<div class="intro home-intro"><span class="eyebrow">YOUR ROSTER</span><h1>Character overview</h1><p>Pick a character to view equipment and plan your next upgrade.${data.profiles.length>1?' Drag cards to reorder them.':''}</p></div><div class="roster-grid">${data.profiles.map(p=>`<article class="roster-tile"><button class="roster-card" data-character="${p.id}" draggable="true" title="Drag to reorder · Alt+Arrow keys also move it"><img src="/api/characters/${p.id}/portrait" alt="" width="120" height="150"><div class="roster-text"><h2>${esc(p.name)}</h2><span class="sub">${esc(p.class)}${p.level?' &middot; Lv. '+p.level:''}</span><strong class="roster-score">${p.hexa==null?'Not calculated':Number(p.hexa).toLocaleString()}</strong><span class="eyebrow roster-score-label">HEXA &middot; 380 DEF</span><small class="sub">${p.stale?'Saved result &middot; inputs changed':p.result_created?'Calculated '+new Date(p.result_created).toLocaleDateString():'Scan stats in Scouter to calculate'}</small><p class="sub">${p.stars} stars${p.fragments==null?'':` &middot; <span title="${esc(['Sol Erda Fragments spent on HEXA levels',p.fragments_partial&&'some HEXA levels are not scanned yet',p.fragments_minimum&&'completed HEXA Stat cores count at their minimum cost'].filter(Boolean).join('; ')+'.')}">${p.fragments_partial||p.fragments_minimum?'&ge; ':''}${Number(p.fragments).toLocaleString()} fragments</span>`}</p></div><span class="roster-open">View equipment &rarr;</span></button><button class="roster-delete" data-delete="${p.id}" aria-label="Delete ${esc(p.name)}" title="Delete character"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></button></article>`).join('')}</div>`;
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
   if(!sibling)return;
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
