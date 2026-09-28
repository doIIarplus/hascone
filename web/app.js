import {mountSections} from './sections.js';
import {openFlameEditor} from './flame_editor.js';
import {mountHeader} from './header.js';
import {pageScroller} from './viewport.js';
import {mountHome} from './home.js';
import {mountProgression} from './progression.js';
import {mountPotentialWeights} from './potential_weights.js';
import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';
import {mountScouter} from './pages/scouter.js';
import {openGuide,openEquipmentGuide} from './guide.js';
import {mountEnhancement,flameIcon} from './enhancement.js';
import {potentialMarkup} from './components/potential.js';
import {createPotentialTooltip} from './components/potential_tooltip.js';
import {createFlameTooltip} from './components/flame_tooltip.js';
import {createGearTooltip} from './components/gear_tooltip.js';
import {mountFlameWeights} from './flame_weights.js';
let renderEpoch=0;
const view=document.querySelector('#view');
let page='home',dispose=null,slot='hat',selected=localStorage.getItem('hascone.character');
const human=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
async function render(){
 const epoch=++renderEpoch;
 view.dataset.sectionPage=page;
 if(view.beforeLeave&&!(await view.beforeLeave()))return;
 if(dispose){dispose();dispose=null;}view.beforeLeave=null;view.className='';
 const all=await api.get('/api/characters');
 if(epoch!==renderEpoch)return;
 if(!all.profiles.some(p=>p.id===selected))selected=all.default_character;
 document.querySelector('#character').innerHTML=all.profiles.map(p=>`<option value="${p.id}" ${p.id===selected?'selected':''}>${esc(p.name)} &middot; ${esc(p.class)}</option>`).join('');
 document.querySelector('#character').disabled=!all.profiles.length;
 document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('btn-primary',b.dataset.page===page));
 if(!selected){view.innerHTML='<section class="empty"><h1>Your characters, clearly measured.</h1><p class="sub">Scan flames, potentials and character stats. Compare gains with Scouter.</p><p>Add your first character to begin.</p><button class="btn btn-primary" id="first-add">+ Add character</button></section>';document.querySelector('#first-add').onclick=()=>document.querySelector('#add-character').click();return;}
 localStorage.setItem('hascone.scouter.character',selected);
 if(page==='home'){const host=document.createElement('div');view.replaceChildren(host);await mountHome(host,id=>navigate('equipment',id));return;}
 if(page==='scouter'){dispose=await mountScouter(view);return;}
 const profile=await api.get('/api/characters/'+selected);
 if(epoch!==renderEpoch)return;
 const slots=all.layout.slots;if(!slots[slot])slot=Object.keys(slots)[0];
 let item=profile.equipment[slot]||{},pot=item.potential;
 const detailMarkup=()=>`<h2>${esc(human(slot))}</h2><h3>${esc(item.name||'Not scanned yet')}</h3>${page==='equipment'?`<p class="sub">${item.flameable===false?'No flames':item.stats?'Flame score '+item.flame_score?.toFixed(1):'Flames not scanned'} / ${item.cubeable===false?'No potential':item.potential?.rank||'Potential not scanned'}</p>`:''}<p class="sub">${item.required_level?'Level '+item.required_level:'Item level unknown'}${item.starforce?.status==='scanned'?' / '+item.starforce.stars+' stars':item.starforce?.status==='not_applicable'?' / No Star Force':item.starforce?' / Stars not scanned':''}</p>${page==='equipment'&&item.stats?.length?`<div class="slot-lines"><strong>Flames / ${item.flame_score?.toFixed(1)} score</strong>${item.stats.map(s=>`<p>${esc(s.name)} +${s.value}${s.percent?'%':''}</p>`).join('')}</div>`:''}<div class="slot-lines">${page==='starforce'?`<p>Current Star Force: <strong>${item.starforce?.status==='scanned'?item.starforce.stars+' stars':'Not scanned'}</strong></p><p class="sub">Recommendations below compare the next star, expected cost and destruction risk. Event settings apply to this character.</p>`:page==='flame'?(item.stats?item.stats.map(s=>`<p>${esc(s.name)} <strong>+${s.value}${s.percent?'%':''}</strong></p>`).join('')+'<p>Flame score <strong>'+item.flame_score.toFixed(1)+'</strong></p>':'No flame saved for this slot.'):(pot?`${potentialMarkup(item)}<p>${esc(item.equivalent?.label||'Equivalent')}: <strong>${item.equivalent?.value?.toFixed(2)??'Unavailable'}%</strong></p><p class="sub">${esc(item.equivalent?.formula||'')}</p>`:'No potential saved for this slot.')}</div>${['equipment','flame'].includes(page)&&item.name&&(item.flameable??slots[slot].flameable)!==false?'<button class="btn" id="edit-flame">Edit flame stats</button>':''}<div id="enhancement-selected" class="selected-costs"></div><div class="actions"><button id="scan-level" class="btn btn-primary">Hover scan (all stats)</button></div><p class="sub">Hover the highlighted slot in Equipment to update all its readings. Keep the tooltip unobstructed.</p>${item.updated?`<p class="sub">Last saved ${esc(new Date(item.updated).toLocaleString())}</p>`:''}`;
 view.innerHTML=`<div class="intro"><h1>${page==='equipment'?'Equipment':page==='flame'?'Flame':page==='starforce'?'Star Force':'Potential'} scanner</h1><p>Capture your equipment, then hover each item. Stars, flames and potentials are saved together.</p></div><div class="gear-layout"><section class="profile-panel"><div class="equip-grid"><img class="portrait" src="/api/characters/${selected}/portrait" alt="${esc(profile.name)}">${Object.entries(slots).map(([key,pos])=>{const saved=profile.equipment[key],scanned=page==='flame'?saved?.stats:saved?.potential;return `<button class="equip-slot ${key===slot?'selected':''} ${page!=='flame'?esc(saved?.potential?.rank||''):''}" data-slot="${key}" style="left:${pos.x}px;top:${pos.y}px" aria-label="${esc(human(key))}">${saved?.name||saved?.occupied?`<img src="/api/characters/${selected}/equipment/${key}/icon?t=${encodeURIComponent(saved?.updated||profile.equipment_captured||'')}" alt="${esc(human(key))}">`:esc(human(key))}${page==='flame'&&scanned?`<span class="score with-flame">${flameIcon}${saved.flame_score?.toFixed(1)||'0.0'}</span>`:['equipment','starforce'].includes(page)&&saved?.starforce?.status==='scanned'?`<span class="score">${saved.starforce.stars}*</span>`:''}</button>`}).join('')}</div><p class="sub">${page==='flame'?'Numbers show flame score.':['equipment','starforce'].includes(page)?'Numbers show stars. Colored borders show potential tier.':'Borders show potential tier. Hover to see saved lines.'}</p><button class="btn" id="scan-all">Scan equipped gear…</button><div id="enhancement-totals" class="profile-costs"></div></section><div class="gear-work"><section class="detail-panel">${detailMarkup()}</section><div id="enhancement-panels"></div></div></div>`;
 const selectGear=key=>{
  const x=pageScroller().scrollLeft,y=pageScroller().scrollTop;
  slot=key;item=profile.equipment[slot]||{};pot=item.potential;
  view.querySelector('.detail-panel').innerHTML=detailMarkup();
  view.querySelectorAll('[data-slot]').forEach(b=>b.classList.toggle('selected',b.dataset.slot===slot));
  bindDetail();dispose?.select?.(slot);
  pageScroller().scrollTo({left:x,top:y,behavior:'instant'});
 };
 const enhancement=mountEnhancement(view,{profile,page,slot,onSelect:selectGear});
 const tooltip=page==='flame'?createFlameTooltip(view,key=>profile.equipment[key]):page==='equipment'?createGearTooltip(view,key=>profile.equipment[key]?.name?profile.equipment[key]:null,key=>enhancement.combined(key)):createPotentialTooltip(view,key=>profile.equipment[key]?.potential?profile.equipment[key]:null);
 const progression=mountProgression(view,profile,page,()=>enhancement.refresh());
 dispose=()=>{enhancement();tooltip?.dispose();progression();};dispose.select=enhancement.select;
 async function refreshWeights(){
  const fresh=await api.get('/api/characters/'+profile.id);
  if(epoch!==renderEpoch)return;
  Object.assign(profile,fresh);
  selectGear(slot);
  view.querySelectorAll('[data-slot] .score').forEach(label=>{
   const gear=profile.equipment[label.closest('[data-slot]').dataset.slot];
   if(page==='flame'&&gear?.stats)label.innerHTML=flameIcon+gear.flame_score.toFixed(1);
  });
  await enhancement.refresh();
 }
 if(page==='flame') {
  const weights=document.createElement('div');weights.className='profile-costs';weights.dataset.collapsible='flame-weights';
  view.querySelector('#enhancement-totals').before(weights);
  mountFlameWeights(weights,profile,refreshWeights);
 }
 if(page==='potential'){const weights=document.createElement('div');weights.dataset.collapsible='potential-weights';view.querySelector('#enhancement-totals').before(weights);mountPotentialWeights(weights,profile,refreshWeights);}
 view.querySelectorAll('[data-slot]').forEach(b=>b.onclick=()=>selectGear(b.dataset.slot));
 function bindDetail(){
 document.querySelector('#edit-flame')?.addEventListener('click',()=>openFlameEditor(profile,slot,refreshWeights));
 document.querySelector('#scan-all').onclick=()=>openEquipmentGuide(selected,render);
 document.querySelector('#scan-level').onclick=()=>openGuide(selected,[{mode:'hover:'+slot,slot,label:human(slot),instruction:`Hover your ${human(slot)} in Equipment. Keep the full tooltip visible; stars, flames and potentials are read together.`}],render);
 }
 bindDetail();
}
async function navigate(nextPage,nextCharacter=selected){
 if(view.beforeLeave&&!(await view.beforeLeave())){document.querySelector('#character').value=selected;return;}
 view.beforeLeave=null;selected=nextCharacter;page=nextPage;localStorage.setItem('hascone.character',selected);await render();pageScroller().scrollTo({top:0,behavior:'instant'});
}
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>navigate(b.dataset.page).catch(toast));
document.querySelector('#character').onchange=e=>navigate(page==='home'?'equipment':page,e.target.value).catch(toast);
document.querySelector('#home').onclick=()=>navigate('home').catch(toast);
const settingsMenu=document.querySelector('#settings-menu');
window.addEventListener('blur',()=>{settingsMenu.open=false;});
document.addEventListener('pointerdown',e=>{if(!settingsMenu.contains(e.target))settingsMenu.open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')settingsMenu.open=false;});
document.querySelectorAll('[data-native]').forEach(b=>{b.disabled=!window.chrome?.webview;b.onclick=()=>{settingsMenu.open=false;window.chrome.webview.postMessage(b.dataset.native);};});
window.addEventListener('open-scouter',()=>navigate('scouter').catch(toast));
document.querySelector('#add-character').onclick=()=>document.querySelector('#add-dialog').showModal();
document.querySelector('#add-cancel').onclick=()=>document.querySelector('#add-dialog').close();
document.querySelector('#add-form').onsubmit=async e=>{e.preventDefault();const b=document.querySelector('#add-submit');b.disabled=true;document.querySelector('#add-error').textContent='Looking up character…';try{const p=await api.post('/api/characters',{name:document.querySelector('#new-name').value});page='equipment';selected=p.id;localStorage.setItem('hascone.character',selected);document.querySelector('#add-dialog').close();await render();await openEquipmentGuide(selected,render);}catch(e){document.querySelector('#add-error').textContent=e.message;}finally{b.disabled=false;}};
window.addEventListener('scouter-guide',async e=>{try{page='scouter';await render();await openGuide(e.detail,await api.get('/api/characters/'+e.detail+'/steps'),render);}catch(e){toast(e.message);}});
window.addEventListener('character-selected',e=>{selected=e.detail;localStorage.setItem('hascone.character',selected);});
render().catch(toast);

mountHeader();
mountSections(view);
