import {api} from './api.js';
import {escapeHtml as esc} from './ui.js';
export async function mountPotentialWeights(root,profile,onSaved){
 root.className='profile-costs';
 let catalog;
 try{catalog=await api.get('/api/potential-weights');}catch(e){root.textContent=e.message;return;}
 if(!root.isConnected)return;
 const job=profile.class, effective=catalog.effective[job];
 root.innerHTML=`<h3>Potential equivalent weights</h3><p class="sub">These weights apply to potential equivalents, current-roll costs and the potential upgrade order.</p><label class="score-toggle"><input type="checkbox" role="switch" id="pot-scouter"> Use Scouter weights</label><p class="sub" id="pot-scouter-info"></p><div id="pot-weight-table"></div><details class="pot-manual"><summary>Adjust manual weights</summary><p class="sub">Used when Scouter is off.</p><label class="weight-toggle"><input type="checkbox" role="switch" id="pot-override" ${catalog.overrides[job]?'checked':''}> Override defaults for ${esc(job)}</label><div class="potential-weights">${[['secondary_weight','1% secondary stat to main stat %',0,10],['boss_per_attack','Boss % equal to 1% ATT / MATT',0.000001,1000]].map(([key,label,min,max])=>`<label>${label}<input class="input" type="number" data-weight="${key}" value="${effective[key]}" min="${min}" max="${max}" step="any"></label>`).join('')}<p class="sub">1% All Stat = <strong id="pot-all-stat">${effective.all_stat_weight}%</strong> main stat equivalent. Derived from this class's primary and secondary stats.</p></div><p class="sub" id="pot-weight-status">${catalog.overrides[job]?'Changes apply to every '+esc(job)+' profile.':'Editing a number changes the global defaults for classes without overrides.'} Saved when you leave the field.</p></details>`;
 let saving=false;
 const source=root.querySelector('#pot-scouter');
 function updateSource(){
  const info=profile.potential_scoring;
  source.checked=info.source==='scouter';
  source.disabled=saving||(!source.checked&&!info.scouter_weights);
  root.querySelectorAll('[data-weight],#pot-override').forEach(el=>el.disabled=saving||source.checked);
  const weights=info.scouter_weights;
  root.querySelector('#pot-scouter-info').textContent=weights?
   'Saved per character. Based on your latest Scouter calculation ('+new Date(info.calculated_at).toLocaleDateString()+').':
   (source.checked?'Scouter weights unavailable; using manual defaults. ':'')+(info.reason||'Calculate Scouter for this character first.');
  const manual=info.manual_weights;
  const n=value=>value==null?'&mdash;':Number(value).toLocaleString(undefined,{maximumFractionDigits:4});
  const scouter=weights?{...Object.fromEntries(Object.entries(weights.score.stat_weights).map(([stat,value])=>[stat+' %',value])),'All Stats %':weights.score.all_stat_weight}:{};
  const stats=[...new Set([...Object.keys(manual.stats),...Object.keys(scouter)])].sort((a,b)=>(a==='All Stats %')-(b==='All Stats %')||(manual.stats[b]??0)-(manual.stats[a]??0)||a.localeCompare(b));
  const row=(label,left,right)=>`<tr><th scope="row">${esc(label)}</th><td>${n(left)}</td><td>${n(right)}</td></tr>`;
  root.querySelector('#pot-weight-table').innerHTML=`<table class="cf-weight-table"><caption>Main stat equivalent (%)</caption><thead><tr><th>Stat</th><th>Manual</th><th>Scouter</th></tr></thead><tbody>${stats.map(stat=>row('1% '+stat.replace(/ %$/,'').replace('All Stats','All Stat'),manual.stats[stat]??0,scouter[stat])).join('')}</tbody></table><table class="cf-weight-table pot-attack-table"><caption>ATT / MATT equivalent (%)</caption><thead><tr><th>Stat</th><th>Manual</th><th>Scouter</th></tr></thead><tbody>${row('1% ATT / MATT',1,weights?1:null)}${row('1% Boss Damage',1/manual.boss_per_attack,weights?1/weights.attack_score.boss_per_attack:null)}</tbody></table><p class="sub">${info.effective_source==='scouter'?'Using Scouter weights.':'Using manual weights.'} Applied to equivalents, expected costs and the upgrade order.</p>`;

 }
 updateSource();
 source.onchange=async()=>{
  if(saving)return;
  const choice=source.checked?'scouter':'default';saving=true;source.disabled=true;
  try{
   const fresh=await api.post(`/api/characters/${profile.id}/potential-scoring`,{source:choice});
   Object.assign(profile,fresh);await onSaved();
  }catch(e){root.querySelector('#pot-weight-status').textContent=e.message;}
  finally{saving=false;if(root.isConnected)updateSource();}
 };
 async function save(){
  if(saving)return;
  const fields=[...root.querySelectorAll('[data-weight]')];
  if(fields.some(el=>!el.checkValidity()||el.value==='')){root.querySelector('#pot-weight-status').textContent='Enter a valid number in each weight field.';fields.forEach(el=>el.setAttribute('aria-invalid',String(!el.checkValidity()||el.value==='')));return;}
  saving=true;updateSource();
  const settings={version:catalog.version,defaults:{...catalog.defaults},overrides:structuredClone(catalog.overrides)};
  const override=root.querySelector('#pot-override').checked;
  if(override)settings.overrides[job]=Object.fromEntries(fields.map(el=>[el.dataset.weight,Number(el.value)]));
  else if(catalog.overrides[job])delete settings.overrides[job];
  else fields.forEach(el=>settings.defaults[el.dataset.weight]=Number(el.value));
  try{
   catalog=await api.post('/api/potential-weights',{revision:catalog.revision,settings});
   if(!root.isConnected)return;
   fields.forEach(el=>{el.value=catalog.effective[job][el.dataset.weight];el.removeAttribute('aria-invalid');});
   root.querySelector('#pot-all-stat').textContent=catalog.effective[job].all_stat_weight+'%';
   root.querySelector('#pot-weight-status').textContent=catalog.overrides[job]?'Saved for every '+job+' profile.':'Saved as the global defaults for classes without overrides.';
   await onSaved();
  }catch(e){root.querySelector('#pot-weight-status').textContent=e.message;}
  finally{saving=false;if(root.isConnected)updateSource();}
 }
 root.querySelector('#pot-override').onchange=save;
 root.querySelectorAll('[data-weight]').forEach(el=>el.onchange=save);
}
