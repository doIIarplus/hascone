import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

export function mountRoster(onSelect){
 const panel=document.createElement('details');panel.className='roster-sidebar';
 panel.innerHTML='<summary aria-label="Toggle character roster" title="Character roster"><span class="roster-arrow" aria-hidden="true"></span><span class="roster-count"></span></summary><div class="roster-body"><strong>Characters</strong><div class="roster-characters"></div></div>';
 document.body.append(panel);
 let characters=[],selected=null,queues={},previous='';
 const label=key=>key.replaceAll('_',' ').replaceAll(':',' / ');
 function draw(){
  const focused=document.activeElement?.dataset.character;
  const pending=Object.values(queues).reduce((sum,q)=>sum+q.pending.length,0);
  const failures=Object.values(queues).reduce((sum,q)=>sum+Object.keys(q.failed).length,0);
  panel.querySelector('.roster-count').innerHTML=pending?`<span class="scan-spinner" aria-label="Processing"></span>${pending}`:failures?' !':'';
  panel.querySelector('.roster-characters').innerHTML=characters.map(c=>{
   const q=queues[c.id],busy=!!q?.pending.length;
   return `<div class="roster-entry ${busy?'processing':''}"><button class="btn ${c.id===selected?'btn-primary':''}" data-character="${esc(c.id)}" ${c.id===selected?'aria-current="true"':''}><img src="/api/characters/${encodeURIComponent(c.id)}/portrait" alt=""><span>${esc(c.name)}<small>${esc(c.class)}</small></span>${busy?'<span class="scan-spinner" aria-label="Processing"></span>':''}</button>${q&&(busy||q.done.length||Object.keys(q.failed).length)?`<p class="sub" role="status">${q.done.length} saved · ${q.pending.length} processing${busy?q.active?' · Reading '+esc(label(q.active))+' · '+q.elapsed+'s'+(q.elapsed>=30?' (taking longer; first use loads the model)':''):' · Queued for OCR':''}</p>`:''}${Object.entries(q?.failed||{}).map(([step,error])=>`<p class="warn">${esc(label(step))}: ${esc(error)} Rescan this step.</p>`).join('')}</div>`;
  }).join('')||'<p class="sub">Add a character to begin.</p>';
  panel.querySelectorAll('[data-character]').forEach(b=>b.onclick=()=>{panel.open=false;onSelect(b.dataset.character).catch(toast);});
  if(focused)panel.querySelector(`[data-character="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
 }
 async function poll(){
  try{
   const next=await api.get('/api/scan/queues'),encoded=JSON.stringify(next);
   if(encoded!==previous){
    for(const [id,q] of Object.entries(next))if(queues[id]?.pending.length&&!q.pending.length){toast(`${characters.find(c=>c.id===id)?.name||'Character'}: processing finished${Object.keys(q.failed).length?' with readings to rescan':''}.`);}
    queues=next;previous=encoded;draw();
   }
  }catch{previous='';panel.querySelector('.roster-count').innerHTML='<span title="Scanner offline" aria-label="Scanner offline">!</span>';}
  setTimeout(poll,1000);
 }
 poll();
 document.addEventListener('pointerdown',e=>{if(panel.open&&!panel.contains(e.target))panel.open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')panel.open=false;});
 return {update(rows,id){characters=rows;selected=id;draw();}};
}
