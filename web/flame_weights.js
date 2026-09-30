import {keepViewport} from './viewport.js';
import {api} from './api.js';
import {escapeHtml as esc} from './ui.js';

// The source picker lives in a sticky page footer so it stays visible while scrolling.
export function mountFlameWeights(root,profile,onSaved,footer) {
 const info=profile.flame_scoring,source=info.source;
 const n=v=>Number(v).toLocaleString(undefined,{maximumFractionDigits:4});
 const label=k=>({'Attack Power':'1 ATT','Magic Attack':'1 MATT','All Stats':'1% All Stat','Damage':'1% Damage','Boss Damage':'1% Boss Damage'}[k]||'1 '+k);
 const names={default:'Default',scouter:'Scouter',custom:'Custom'};
 // Custom weights start from the weights in effect and can model other builds or future patches.
 const custom=info.custom_weights||info.weights;
 const order=['STR','DEX','INT','LUK','Max HP','Attack Power','Magic Attack','All Stats','Boss Damage','Damage'];
 const stats=info.stat_order.length?info.stat_order:Object.keys(info.default_weights).filter(k=>Number(info.default_weights[k])||Number(custom[k])).sort((a,b)=>order.indexOf(a)-order.indexOf(b));
 footer.innerHTML=`<label>Flame weights <select class="input" id="flame-weight-source" aria-label="Flame weight source">${Object.entries(names).map(([value,name])=>`<option value="${value}" ${source===value?'selected':''} ${value==='scouter'&&!info.scouter_weights?'disabled':''}>${name}${value==='scouter'&&!info.scouter_weights?' (calculate Scouter first)':''}</option>`).join('')}</select></label>${info.effective_source!==source?`<span class="sub">Using ${names[info.effective_source]} until ${source==='scouter'?'a complete Scouter result is':'custom weights are'} available.</span>`:''}`;
 root.innerHTML=`<h3>Flame weights</h3><p class="sub">${info.scouter_weights?'Scouter weights are based on your latest calculation'+(info.calculated_at?' ('+esc(new Date(info.calculated_at).toLocaleDateString())+')':'')+'. ':'Calculate Scouter for this character to use Scouter weights. '}Choose Custom in the footer to enter your own.</p><table class="cf-weight-table"><caption>Flame score per stat</caption><thead><tr><th>Stat</th><th>Default</th><th>Scouter</th><th>Custom</th></tr></thead><tbody>${stats.map(k=>`<tr><th>${esc(label(k))}</th><td>${n(info.default_weights[k])}</td><td>${info.scouter_weights?n(info.scouter_weights[k]):'&mdash;'}</td><td><input class="input" type="number" min="0" step="any" data-custom="${esc(k)}" value="${esc(custom[k])}" aria-label="Custom weight for ${esc(label(k))}" ${source==='custom'?'':'disabled'}></td></tr>`).join('')}</tbody></table>${info.stat_order.length?`<p class="sub">Relative to ${esc(info.primary_stat)}. Damage weights apply to bosses. Scouter weights use saved stats and buffs.</p>`:''}<p class="sub" role="status"></p>`;
 const picker=footer.querySelector('select'),inputs=[...root.querySelectorAll('[data-custom]')];
 async function save(body){
  [picker,...inputs].forEach(el=>el.disabled=true);
  try {await api.post(`/api/characters/${profile.id}/scoring`,body);await onSaved();if(root.isConnected)keepViewport(root,()=>mountFlameWeights(root,profile,onSaved,footer));}
  catch(error){picker.value=source;root.querySelector('[role="status"]').textContent=error.message;picker.disabled=false;inputs.forEach(el=>el.disabled=source!=='custom');}
 }
 picker.onchange=()=>save({source:picker.value});
 inputs.forEach(el=>el.onchange=()=>{
  if(!el.checkValidity()||el.value===''){root.querySelector('[role="status"]').textContent='Enter a weight of 0 or more.';return;}
  save({source:'custom',weights:Object.fromEntries(inputs.map(input=>[input.dataset.custom,input.value]))});
 });
}
