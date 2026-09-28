import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';
import {coreName,levelChange,orderContext,completionChange} from './scouter-hexa.js';

const fmt=value=>Number.isFinite(Number(value))?Number(value).toLocaleString(undefined,{maximumFractionDigits:2}):'—';
const levels=profile=>Object.fromEntries(Object.entries(profile.values.hexa||{}).map(([key,value])=>['hexa.'+key,value]));

export async function mountHexa(root,character){
 let disposed=false,busy=false,profile,message='';
 const endpoint=`/api/scouter/characters/${encodeURIComponent(character)}`;
 root.className='hexa-page';
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading HEXA upgrade order...</p>';
 const alive=()=>!disposed&&root.isConnected;
 const goScouter=()=>window.dispatchEvent(new CustomEvent('open-scouter'));
 function draw(){
  if(!alive())return;
  const history=[...profile.history].reverse();
  const result=history.find(row=>row.fingerprint===profile.fingerprint)||history[0];
  const stale=!!result&&result.fingerprint!==profile.fingerprint;
  const order=result?.order;
  root.innerHTML=`<div class="page-head"><div><h1>HEXA upgrade order</h1><p class="sub">${esc(profile.character.name)} · ${esc(profile.character.class)}</p></div><button class="btn" data-scouter>Open Scouter</button></div>${!result?'<section class="card empty"><h2>Calculate in Scouter first</h2><p class="sub">Scan this character and calculate their Scouter results to see the HEXA skill upgrade order here.</p><button class="btn btn-primary" data-scouter>Go to Scouter</button></section>':`
   <p class="sub">Saved ${esc(new Date(result.created).toLocaleString())}${result.name?' · '+esc(result.name):''}</p>
   ${stale?'<p class="sc-warning">Inputs have changed since this calculation. Calculate again in Scouter to refresh the upgrade order.</p>':''}
   ${result.order_error?`<p class="sc-warning">${esc(result.order_error)}</p>`:''}
   <p class="sub">After making an upgrade in game, mark it completed to save the new level. Calculate again in Scouter to refresh the order.</p>
   <p class="sub">${esc(orderContext(order))}</p>
   <p role="status" class="sub">${esc(message)}</p>
   <section class="card hexa-path-card"><div class="sc-order">${(order?.class_hexa||[]).map((row,index)=>{
    const core=profile.class_info.cores[row[9]],stat=/^hexaStat([1-3])$/.exec(row[9]);
    const icon=stat?`hexa-stat-${stat[1]}.png`:core?.url?.split('/').pop();
    const completion=completionChange(row,levels(profile),profile.class_info.cores);
    return `<div class="sc-order-row"><span class="sc-rank">${index+1}</span>${icon?`<img width="32" height="32" src="/api/scouter/icons/${encodeURIComponent(icon)}" alt="">`:'<span></span>'}<span>${esc(coreName(core,row[9]))}<small>${fmt(row[3])} Sol Erda · ${fmt(row[4])} fragments</small><small title="Normalized final-damage percentage per 30 fragments, as returned by MapleScouter. Higher is better.">Efficiency ${fmt(row[7])}% / 30 fragments</small></span><span class="sc-hexa-step"><strong>${esc(levelChange(row))}</strong>${completion?`<button class="btn" data-hexa-complete="${index}" ${stale||busy?'disabled':''}>Mark completed</button>`:''}</span></div>`;
   }).join('')||`<p class="empty">${order?'No further upgrades returned.':'No HEXA upgrade order was returned. Calculate again in Scouter.'}</p>`}</div></section>`}`;
  root.querySelectorAll('[data-scouter]').forEach(button=>button.onclick=goScouter);
  root.querySelectorAll('img').forEach(img=>img.onerror=()=>{img.hidden=true;});
  root.querySelectorAll('[data-hexa-complete]').forEach(button=>button.onclick=async()=>{
   if(busy||stale)return;
   const row=order.class_hexa[Number(button.dataset.hexaComplete)];
   busy=true;message='Saving level...';draw();
   try{
    const fresh=await api.get(endpoint);
    if(!alive())return;
    profile=fresh;
    if(fresh.fingerprint!==result.fingerprint)throw new Error('Inputs changed. Calculate again in Scouter before marking this upgrade completed.');
    const change=completionChange(row,levels(fresh),fresh.class_info.cores);
    if(!change)throw new Error('This upgrade no longer matches your saved level.');
    const saved=await api.post(endpoint,{revision:fresh.revision,changes:{[change.path]:String(change.value)}});
    if(!alive())return;
    profile=saved;
    message=change.stat?'Saved. Rescan character stats, then calculate in Scouter to refresh.':'Level saved. Calculate in Scouter to refresh the upgrade order.';
   }catch(error){if(alive()){message=error.message;toast(error.message);}}
   finally{busy=false;draw();}
  });
 }
 try{profile=await api.get(endpoint);draw();}
 catch(error){if(alive()){root.innerHTML=`<p class="warn" role="alert">${esc(error.message)}</p><button class="btn" data-retry>Try again</button>`;root.querySelector('[data-retry]').onclick=async()=>{try{profile=await api.get(endpoint);draw();}catch(e){toast(e.message);}};}}
 return()=>{disposed=true;};
}
