import {api} from './api.js';
import {createSuggestions} from './pages/scouter-suggestions.js';
import {escapeHtml as esc} from './ui.js';
export function mountProgression(view,character,page,onOptionsChanged=async()=>{}){
 const root=document.createElement('section');root.className='progression-section';view.querySelector('.gear-work').append(root);
 const help=document.createElement('div');help.className='progression-guidance';root.append(help);
 const recommendations=document.createElement('div');root.append(recommendations);
 let disposed=false,inFlight=false,signature='',timer;
 const endpoint=`/api/scouter/characters/${character.id}`;
 const scope=({potential:'cube',starforce:'starforce',flame:'flame'})[page];
 const handlers={
  scope,
  onGenerate:async()=>{try{await api.post(endpoint+'/suggestions',{});signature='';await refresh();}catch(e){help.textContent=e.message;}},
  onOptions:async value=>{await api.post(endpoint+'/starforce-options',value);await onOptionsChanged();signature='';await refresh();}
 };
 const panels=[createSuggestions(recommendations,{...handlers,showOptions:!['potential','starforce'].includes(page)})];
 let upgradeRoot;
 if(['potential','starforce'].includes(page)){
  upgradeRoot=document.createElement('section');upgradeRoot.className='upgrade-order-section';
  view.querySelector('#enhancement-panels').before(upgradeRoot);
  panels.push(createSuggestions(upgradeRoot,{...handlers,layout:'cards'}));
 }
 async function refresh(){
  if(disposed||inFlight)return;inFlight=true;
  try{
   const state=await api.post(`/api/characters/${character.id}/progression`,{});
   if(disposed)return;
   const profile=await api.get(endpoint);if(disposed)return;
   const next=JSON.stringify([profile.suggestions?.created,profile.fingerprint,profile.gear_fingerprint,profile.starforce_options,state.status]);
   if(next!==signature){signature=next;panels.forEach(panel=>panel.update(profile));}
   panels.forEach(panel=>panel.setBusy(state.active));
   const needs=['needs_calculation','needs_equipment'].includes(state.status);
   help.innerHTML=`${page==='flame'?'<p class="sub">The score ranking above uses your chosen flame weights. This comparison always uses Scouter efficiencies and ranks expected FD per meso. The order and costs can differ because the qualifying gain and ranking metric differ.</p>':''}<p class="sub">${esc(state.message||'')}${needs?' <button class="btn btn-primary" data-setup>Set up Scouter &rarr;</button>':''}</p>`;
   help.querySelector('[data-setup]')?.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('open-scouter')));
  }catch(e){if(!disposed)help.textContent='Upgrade comparison: '+e.message;}
  finally{inFlight=false;}
 }
 refresh();timer=setInterval(refresh,4500);
 return()=>{disposed=true;clearInterval(timer);panels.forEach(panel=>panel.dispose());upgradeRoot?.remove();};
}
