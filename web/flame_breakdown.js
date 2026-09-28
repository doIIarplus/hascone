import {api} from './api.js';
import {escapeHtml as esc} from './ui.js';

export function mountFlameBreakdown(host,character,slot){
 const summed=host.parentElement.querySelector('[data-flame-summary]');
 if(!summed)return;
 const cards=document.createElement('div');cards.className='flame-cards';
 summed.before(cards);cards.append(summed,host);
 host.className='slot-lines flame-tier-card';
 host.innerHTML='<strong>Flame tiers</strong><div data-tiers></div>';
 const body=host.querySelector('[data-tiers]');
 async function draw(){
  body.innerHTML='<p role="status"><span class="scan-spinner"></span> Finding tiers...</p>';
  try{
   const result=await api.get(`/api/characters/${character}/equipment/${slot}/flame-tiers`);
   if(!host.isConnected)return;
   body.innerHTML=`${result.options.map((lines,i)=>`<div class="flame-tier-option">${result.options.length>1?`<p class="sub">Possible breakdown ${i+1}</p>`:''}${lines.map(line=>`<p class="flame-tier-line"><span>${esc(line.stats.join(' + '))} <strong>${line.value>0?'+':''}${line.value}${line.percent?'%':''}</strong></span><strong class="flame-tier-badge">T${line.tier}</strong></p>`).join('')}</div>`).join('')}<p class="sub flame-tier-note">${esc(result.message)}</p>`;
  }catch(e){body.textContent=e.message;}
 }
 draw();
}
