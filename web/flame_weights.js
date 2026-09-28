import {keepViewport} from './viewport.js';
import {api} from './api.js';
import {escapeHtml as esc} from './ui.js';

export function mountFlameWeights(root,profile,onSaved) {
 const info=profile.flame_scoring,checked=info.source==='scouter';
 const n=v=>Number(v).toLocaleString(undefined,{maximumFractionDigits:4});
 const label=k=>({'Attack Power':'1 ATT','Magic Attack':'1 MATT','All Stats':'1% All Stat','Damage':'1% Damage','Boss Damage':'1% Boss Damage'}[k]||'1 '+k);
 root.innerHTML=`<h3>Flame weights</h3><label class="score-toggle"><input id="flame-weight-source" type="checkbox" role="switch" ${checked?'checked':''} ${!checked&&!info.scouter_weights?'disabled':''}>Use Scouter flame weights</label><p class="sub">${info.scouter_weights?'Saved per character. Based on your latest Scouter calculation'+(info.calculated_at?' ('+esc(new Date(info.calculated_at).toLocaleDateString())+')':'')+'.':'Calculate Scouter for this character first.'}${checked&&info.effective_source!=='scouter'?' Using default weights until a complete result is available.':''}</p>${checked&&info.effective_source==='scouter'?`<table class="cf-weight-table"><caption>Flame score per stat</caption><thead><tr><th>Stat</th><th>Default</th><th>Scouter</th></tr></thead><tbody>${info.stat_order.map(k=>`<tr><th>${esc(label(k))}</th><td>${n(info.default_weights[k])}</td><td>${n(info.weights[k])}</td></tr>`).join('')}</tbody></table><p class="sub">Relative to ${esc(info.primary_stat)}. Damage weights apply to bosses. Based on saved stats and buffs.</p>`:''}<p class="sub" role="status"></p>`;
 const toggle=root.querySelector('input');
 toggle.onchange=async()=>{
  toggle.disabled=true;
  try {await api.post(`/api/characters/${profile.id}/scoring`,{source:toggle.checked?'scouter':'default'});await onSaved();if(root.isConnected)keepViewport(root,()=>mountFlameWeights(root,profile,onSaved));}
  catch(error){toggle.checked=checked;root.querySelector('[role="status"]').textContent=error.message;}
  finally{toggle.disabled=false;}
 };
}
