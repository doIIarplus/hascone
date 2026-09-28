import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';
export async function mountHome(root,onSelect){
 const data=await api.get('/api/summary');
 if(!root.isConnected)return;
 root.innerHTML=`<div class="intro home-intro"><span class="eyebrow">YOUR ROSTER</span><h1>Character overview</h1><p>Pick a character to view equipment and plan your next upgrade.${data.profiles.length>1?' Drag cards to reorder them.':''}</p></div><div class="roster-grid">${data.profiles.map(p=>`<button class="roster-card" data-character="${p.id}" draggable="true" title="Drag to reorder · Alt+Arrow keys also move it"><img src="/api/characters/${p.id}/portrait" alt="" width="120" height="150"><div class="roster-text"><h2>${esc(p.name)}</h2><span class="sub">${esc(p.class)}${p.level?' &middot; Lv. '+p.level:''}</span><strong class="roster-score">${p.hexa==null?'Not calculated':Number(p.hexa).toLocaleString()}</strong><span class="eyebrow roster-score-label">HEXA &middot; 380 DEF</span><small class="sub">${p.stale?'Saved result &middot; inputs changed':p.result_created?'Calculated '+new Date(p.result_created).toLocaleDateString():'Scan stats in Scouter to calculate'}</small><p class="sub">${p.stars} stars</p></div><span class="roster-open">View equipment &rarr;</span></button>`).join('')}</div>`;
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
  for(const card of grid.querySelectorAll('[data-character]')){
   if(card===dragged)continue;
   const r=card.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2,d=(x-cx)**2+(y-cy)**2;
   if(d<distance){distance=d;best={card,after:y>r.bottom||(y>=r.top&&x>cx)};}
  }
  return best;
 }
 grid.querySelectorAll('[data-character]').forEach(b=>{
  b.onclick=()=>{if(!moved)onSelect(b.dataset.character);};
  b.ondragstart=e=>{dragged=b;moved=false;b.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',b.dataset.character);};
  b.ondragend=()=>{b.classList.remove('dragging');dragged=null;persist();setTimeout(()=>{moved=false;},0);};
  b.onkeydown=e=>{
   if(!e.altKey||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
   e.preventDefault();
   const back=['ArrowLeft','ArrowUp'].includes(e.key),sibling=back?b.previousElementSibling:b.nextElementSibling;
   if(!sibling)return;
   back?sibling.before(b):sibling.after(b);b.focus();persist();
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
