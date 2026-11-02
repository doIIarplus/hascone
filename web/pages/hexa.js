import {api} from '../api.js';
import {escapeHtml as esc,toast} from '../ui.js';
import {coreName,levelChange,orderContext,completionChange,hexaResources,resourceOrder,resourceEfficiency} from './scouter-hexa.js';

const fmt=value=>value!=null&&Number.isFinite(Number(value))?Number(value).toLocaleString(undefined,{maximumFractionDigits:3}):'—';
const levels=profile=>Object.fromEntries(Object.entries(profile.values.hexa||{}).map(([key,value])=>['hexa.'+key,value]));

export async function mountHexa(root,character){
 let disposed=false,busy=false,profile,message='',resource='fragments',job={},timer,refreshing=false;
 const endpoint=`/api/scouter/characters/${encodeURIComponent(character)}`;
 root.className='hexa-page';
 root.innerHTML='<p role="status"><span class="scan-spinner" aria-hidden="true"></span> Loading HEXA upgrade order...</p>';
 const alive=()=>!disposed&&root.isConnected;
 const goScouter=()=>window.dispatchEvent(new CustomEvent('open-scouter'));
 const baseline=()=>{const history=[...profile.history].reverse();return history.find(row=>row.fingerprint===profile.fingerprint)||history[0];};
 const ownJob=(state=job)=>state.kind==='hexa_order'&&state.profile===character&&state.baseline_id===baseline()?.id&&state.resource===resource;
 function draw(){
  if(!alive())return;
  const result=baseline(),stale=!!result&&result.fingerprint!==profile.fingerprint;
  const order=resourceOrder(result,resource),disabled=busy||job.active;
  const unit=resource==='sol_erda'?'Sol Erda':'30 fragments';
  const routeDate=result?.hexa_orders?.[resource]?.created||result?.created;
  root.innerHTML=`<div class="page-head"><div><h1>HEXA upgrade order</h1><p class="sub">${esc(profile.character.name)} · ${esc(profile.character.class)}</p></div><button class="btn" data-scouter>Open Scouter</button></div>${!result?'<section class="card empty"><h2>Calculate in Scouter first</h2><p class="sub">Scan this character and calculate their Scouter results to see the HEXA skill upgrade order here.</p><button class="btn btn-primary" data-scouter>Go to Scouter</button></section>':`
   <div class="card hexa-resource-card"><div class="hexa-resource-controls"><label for="hexa-resource">Optimize for<select class="input" id="hexa-resource" ${disabled?'disabled':''}>${Object.entries(hexaResources).map(([key,label])=>`<option value="${key}" ${key===resource?'selected':''}>${label}</option>`).join('')}</select></label><button class="btn ${order?'':'btn-primary'}" id="hexa-calculate" ${disabled?'disabled':''}>${order?'Refresh route':'Calculate route'}</button>${ownJob()&&job.active?'<button class="btn" id="hexa-stop">Stop</button>':''}</div><p class="sub">Choose the resource limiting your upgrades. Both routes use this saved calculation’s stats and current HEXA levels.</p><p role="status" aria-live="polite" class="sub">${esc(message||(job.active?(ownJob()?job.message:'A Scouter job is running.'):''))}</p></div>
   <p class="sub">Baseline ${esc(new Date(result.created).toLocaleString())}${result.name?' · '+esc(result.name):''}${order?` · ${esc(hexaResources[resource])} route saved ${esc(new Date(routeDate).toLocaleString())}`:''}</p>
   ${stale?'<p class="sc-warning">Inputs have changed since this calculation. Calculate again in Scouter to refresh the baseline.</p>':''}
   ${resource==='fragments'&&result.order_error&&!order?`<p class="sc-warning">${esc(result.order_error)}</p>`:''}
   <p class="sub">After making an upgrade in game, mark it completed to save the new level. Calculate again in Scouter to refresh the order.</p>
   <p class="sub">${esc(orderContext(order))}</p>
   <section class="card hexa-path-card" aria-label="${esc(hexaResources[resource])} upgrade route"><div class="sc-order">${(order?.class_hexa||[]).map((row,index)=>{
    const core=profile.class_info.cores[row[9]],stat=/^hexaStat([1-3])$/.exec(row[9]);
    const icon=stat?`hexa-stat-${stat[1]}.png`:core?.url?.split('/').pop();
    const completion=completionChange(row,levels(profile),profile.class_info.cores);
    const efficiency=resourceEfficiency(row,resource);
    const title=resource==='sol_erda'?'Estimated FD per Sol Erda, converted from MapleScouter’s FD per 30 fragments.':'Normalized FD per 30 fragments, as returned by MapleScouter.';
    return `<div class="sc-order-row"><span class="sc-rank">${index+1}</span>${icon?`<img width="32" height="32" src="/api/scouter/icons/${encodeURIComponent(icon)}" alt="">`:'<span></span>'}<span>${esc(coreName(core,row[9]))}<small>${fmt(row[3])} Sol Erda · ${fmt(row[4])} fragments</small><small title="${esc(title)}">Efficiency ${fmt(efficiency)}${efficiency==null?'':`% / ${unit}`}</small></span><span class="sc-hexa-step"><strong>${esc(levelChange(row))}</strong>${completion?`<button class="btn" data-hexa-complete="${index}" ${stale||disabled?'disabled':''}>Mark completed</button>`:''}</span></div>`;
   }).join('')||`<p class="empty">${order?'No further upgrades returned.':`No ${esc(hexaResources[resource])} route saved for this calculation. Select Calculate route to fetch it.`}</p>`}</div></section>`}`;
  root.querySelectorAll('[data-scouter]').forEach(button=>button.onclick=goScouter);
  root.querySelectorAll('img').forEach(img=>img.onerror=()=>{img.hidden=true;});
  const selector=root.querySelector('#hexa-resource');
  if(selector)selector.onchange=async event=>{resource=event.target.value;await calculate(false);};
  root.querySelector('#hexa-calculate')?.addEventListener('click',()=>calculate(true));
  root.querySelector('#hexa-stop')?.addEventListener('click',async()=>{
   try{await api.post('/api/scouter/cancel');message='Stopping route calculation…';draw();}
   catch(error){if(alive()){message=error.message;draw();}}
  });
  root.querySelectorAll('[data-hexa-complete]').forEach(button=>button.onclick=async()=>{
   if(disabled||stale)return;
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
 async function calculate(refresh){
  if(busy||job.active)return;
  const result=baseline();
  busy=true;message='';draw();
  try{
   job=await api.post(endpoint+'/hexa-order',{result_id:result.id,resource,refresh});
   if(!alive())return;
   profile=await api.get(endpoint);
   message=job.active?'':job.message;
  }catch(error){if(alive())message=error.message;}
  finally{busy=false;draw();}
 }
 async function refresh(){
  if(refreshing||busy||!alive())return;refreshing=true;
  try{
   const next=await api.get('/api/scouter/state');
   if(!alive()||busy)return;
   const finished=job.active&&!next.active;
   const changed=JSON.stringify(job)!==JSON.stringify(next);
   const fresh=finished||(changed&&ownJob(next)&&!next.active)?await api.get(endpoint):null;
   if(!alive()||busy)return;
   job=next;
   if(fresh){profile=fresh;if(ownJob())message=job.message;}
   if(changed||fresh)draw();
  }catch{/* A transient polling error can be retried without replaying a calculation. */}
  finally{refreshing=false;}
 }
 async function load(){
  profile=await api.get(endpoint);
  resource=profile.hexa_resource in hexaResources?profile.hexa_resource:'fragments';
  job=await api.get('/api/scouter/state');
  if(ownJob()&&!job.active)profile=await api.get(endpoint);
  draw();
  if(!disposed&&!timer)timer=setInterval(refresh,1500);
 }
 try{await load();}
 catch(error){if(alive()){root.innerHTML=`<p class="warn" role="alert">${esc(error.message)}</p><button class="btn" data-retry>Try again</button>`;root.querySelector('[data-retry]').onclick=async()=>{try{await load();}catch(e){toast(e.message);}};}}
 return()=>{disposed=true;clearInterval(timer);};
}
