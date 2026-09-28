import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';
const fields=['STR','DEX','INT','LUK','Attack Power','Magic Attack','All Stats','Damage','Boss Damage','Max HP','Max MP','Defense','Speed','Jump','Reduced level requirement'];
const percentages=new Set(['All Stats','Damage','Boss Damage']);
export function openFlameEditor(profile,slot,onSaved){
 let item=profile.equipment[slot],queue=Promise.resolve(),failed=false;
 const values=Object.fromEntries(fields.map(name=>[name,Math.abs(item.stats?.find(s=>s.name===name)?.value||0)]));
 const dialog=document.createElement('dialog');dialog.className='flame-editor';
 dialog.innerHTML=`<h2>Edit flame stats</h2><p>${esc(item.name)}</p><p class="sub">Enter bonus stats only, not total item stats. Changes save as you edit. A new scan replaces these values.</p><div class="flame-edit-grid">${fields.map(name=>`<label>${esc(name)}${percentages.has(name)?' (%)':''}<input class="input" type="number" min="0" max="${percentages.has(name)?100:999999}" step="1" value="${values[name]}" data-flame-stat="${esc(name)}"></label>`).join('')}</div><p class="sub" role="status" aria-live="polite">Saved</p><div class="actions"><button class="btn" data-close>Done</button></div>`;
 document.body.append(dialog);dialog.showModal();
 const status=dialog.querySelector('[role=status]');
 dialog.querySelectorAll('input').forEach(input=>{
  input.onfocus=()=>input.select();
  input.onchange=()=>{
   if(input.value==='')input.value='0';
   if(!input.reportValidity()){status.textContent='Enter a nonnegative whole number.';failed=true;return;}
   values[input.dataset.flameStat]=Number(input.value);
   const snapshot={...values};status.textContent='Saving...';
   queue=queue.then(async()=>{
    try{
     const fresh=await api.post(`/api/characters/${profile.id}/equipment/${slot}/flame`,{item:item.name,updated:item.updated,values:snapshot});
     item=fresh.equipment[slot];failed=false;status.textContent='Saved';await onSaved(fresh);
    }catch(e){failed=true;status.textContent=e.message;}
   });
  };
 });
 async function close(){await queue;if(failed)toast("Some changes were not saved. Reopen Edit flame stats to retry.");dialog.close();dialog.remove();}
 dialog.querySelector('[data-close]').onclick=close;
 dialog.addEventListener('cancel',e=>{e.preventDefault();document.activeElement?.blur();close();});
}
