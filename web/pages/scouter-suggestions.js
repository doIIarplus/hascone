import {keepViewport} from '../viewport.js';
import {filters,selectSuggestionRows} from './suggestion-filters.js';
import { api } from '../api.js';
import { escapeHtml as esc } from '../ui.js';

const number = (v, digits=3) => v>0&&v<10**(-digits) ? Number(v).toExponential(2) : Number(v).toLocaleString(undefined,{maximumFractionDigits:digits});
const money = v => {
  const unit = [[1e15,'Q'],[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'K']].find(([n])=>v>=n);
  return unit ? `${number(v/unit[0],2)}${unit[1]}` : number(v,0);
};
const sfOptions = p => {
  const o=p?.starforce_options||{};
  return {mode_15_17:o.mode_15_17??(o.safeguard?'safeguard':1),mode_18_21:o.mode_18_21??1,discount:o.discount??false,boom_reduction:o.boom_reduction??false};
};
const date = value => value ? new Date(value).toLocaleString() : 'Unknown';

const modeLabel = mode => mode==='safeguard'?'Safeguard':mode==null?'Standard':`Mode ${mode}`;
function starforceDetails(row) {
  if(!row.starforce_plan)return '';
  const custom=row.custom_plan;
  return `<details class="sc-suggest-plan"><summary>Enhancement plan · includes recovery steps</summary><table><thead><tr><th>Attempt</th><th>Protection</th><th>Success</th><th>Destruction</th><th>Tap cost</th></tr></thead><tbody>${row.starforce_plan.map(s=>`<tr><td>${s.star} → ${s.star+1}${s.recovery?' (recovery)':''}</td><td>${modeLabel(s.mode)}</td><td>${number(s.success*100,3)}%</td><td>${number(s.boom*100,3)}%</td><td>${money(s.tap_cost)}</td></tr>`).join('')}</tbody></table></details>${custom?`<p class="sub">Custom plan · 15–17★ ${modeLabel(custom.options.mode_15_17)}, 18–21★ ${modeLabel(custom.options.mode_18_21)}: <strong>${money(custom.expected_mesos)}</strong> expected · <strong>${number(custom.expected_booms,2)}</strong> expected booms</p>`:''}`;
}
function flameDetails(row) {
  if(!row.flame_examples?.length)return '';
  return `<section class="sc-flame-outcomes"><h3>Example improving flames</h3><p class="sub">${money(row.expected_mesos)} buys the first modeled FD improvement on average. It is not the cost to hit any specific example. The +${number(row.expected_fd,4)}% shown above averages all qualifying results.</p><div class="sc-flame-examples">${row.flame_examples.map(example=>`<div><strong>${esc(example.label)}</strong><div class="sc-flame-gain">+${number(example.fd_gain,4)}% FD</div>${example.stats.map(stat=>`<div class="sub">${esc(stat)}</div>`).join('')}</div>`).join('')}</div></section>`;
}

export function createSuggestions(root, {onGenerate, onOptions=async()=>{}, scope=null, layout='list',showOptions=true}) {
  let profile, dirty=false, busy=false, disposed=false, filter='best', savingOptions=false;
  const urls=new Map();
  const prefix=layout==='cards'?'upgrade':'sc';
  root.dataset.collapsible='recommendations-'+layout;
  if(layout==='cards')root.classList.add('analysis-panel','upgrade-cards-panel');
  root.innerHTML=`<div class="sc-section-title"><div><h2>${scope==='cube'?(layout==='cards'?'Potential upgrade order':'Potential gains by FD / meso'):scope==='starforce'?(layout==='cards'?'Star Force upgrade order':'Star Force gains by FD / meso'):scope==='flame'?'Flame gains by FD / meso':'Upgrade recommendations'}</h2><p class="sub">More damage for your mesos · ranked by estimated FD per 1B</p></div><button class="btn btn-primary" id="${prefix}-suggest">Compare upgrades</button></div>${scope==='cube'?'<p class="sub sc-scouter-basis"><strong>Follows your potential weight setting</strong> (Scouter or manual, above). This order ranks all positive FD gains per meso, including tiny gains; open Details to see qualifying rolls.</p>':''}<fieldset class="card sc-starforce-options" ${!showOptions||(scope&&scope!=='starforce')?'hidden':''}><legend>Star Force</legend>${[['mode_15_17','15–17★',[[1,'Mode 1'],[2,'Mode 2'],[3,'Mode 3'],['safeguard','Safeguard · no destruction']]],['mode_18_21','18–21★',[[1,'Mode 1'],[2,'Mode 2'],[3,'Mode 3'],[4,'Mode 4 · no destruction']]]].map(([key,label,choices])=>`<label title="Custom plan used for comparison inside each Star Force recommendation">${label}<select class="input" data-sf-option="${key}">${choices.map(([value,name])=>`<option value="${value}">${name}</option>`).join('')}</select></label>`).join('')}${[['discount','30% meso discount','Discounts the entire mode fee; excludes the Safeguard surcharge at 15–17★.'],['boom_reduction','30% destruction reduction','Applies to all modes through 21★.']].map(([key,label,hint])=>`<label title="${hint}"><input type="checkbox" data-sf-option="${key}"> ${label}</label>`).join('')}<span class="sub sc-starforce-hint">Ranking compares all modes for least mesos and fewest booms. Select a custom plan above to compare in the details. 22★+ uses standard rates.</span></fieldset><div id="${prefix}-suggestion-body"></div>`;
  const button=root.querySelector(`#${prefix}-suggest`), body=root.querySelector(`#${prefix}-suggestion-body`);
  button.onclick=()=>onGenerate();
  const switches=[...root.querySelectorAll('[data-sf-option]')];
  switches.forEach(input=>input.onchange=async()=>{
    const value={...sfOptions(profile),[input.dataset.sfOption]:input.tagName==='SELECT'?(input.value==='safeguard'?input.value:Number(input.value)):input.checked};
    savingOptions=true;enabled();
    try {await onOptions(value);} finally {savingOptions=false;render();}
  });
  function enabled() {
    switches.forEach(input=>{input.disabled=busy||savingOptions||!profile;});
    button.disabled=busy||savingOptions||dirty||!profile?.gear_fingerprint||!profile.history.some(r=>r.fingerprint===profile.fingerprint);
    button.textContent=busy?'Comparing…':'Compare upgrades';
  }
  function render() {return keepViewport(body,renderContents);}
  function renderContents() {
    if(!profile)return;
    enabled();
    if(!savingOptions)switches.forEach(input=>{const value=sfOptions(profile)[input.dataset.sfOption];if(input.tagName==='SELECT')input.value=String(value);else input.checked=value;});
    const result=profile.suggestions;
    button.title='Recompute after equipment or event settings change. Recommendations also refresh in the background.';
    const ready=!dirty&&profile.history.some(r=>r.fingerprint===profile.fingerprint);
    const oldModel=result&&result.model_version!==5;
    const stale=result&&(oldModel||JSON.stringify(sfOptions(result))!==JSON.stringify(sfOptions(profile))||dirty||result.fingerprint!==profile.fingerprint||result.gear_fingerprint!==profile.gear_fingerprint);
    if(!result) {
      body.innerHTML=`<div class="card empty">${!ready?'Calculate Scouter with your current inputs first.':!profile.gear_fingerprint?'Scan this character’s equipment in Equipment first.':'Compare your saved flames, potentials and stars to find the best estimated FD gains per meso.'}<p class="sub">Use the same equipment preset for your equipment scans and Scouter calculation.</p></div>`;
      return;
    }
    const rows=selectSuggestionRows(result.rows,filter,scope);
    body.innerHTML=`${stale?`<p class="sc-warning">Saved comparison · ${!ready?'inputs changed. Calculate Scouter again, then compare upgrades.':oldModel?'Star Force strategies and flame examples updated. Compare upgrades again to refresh.':'equipment, targets or Star Force options changed. Compare upgrades again to refresh.'}</p>`:''}
      <div class="card sc-suggest-intro"><strong>Estimated gains · 380 DEF</strong><p class="sub">${esc(result.model)}</p><p class="sub">${esc(result.basis)}</p>
        <details><summary class="sub">Data used · ${esc(date(result.created))}</summary><p class="sub">Scouter: ${esc(date(result.baseline_created))}<br>Equipment: ${esc(date(result.equipment_scanned))}<br>Potentials: ${esc(date(result.potential_scanned))}</p></details></div>
      <div class="sc-suggest-toolbar"><label for="${prefix}-suggest-filter">Show</label><select class="input" id="${prefix}-suggest-filter">${filters.map(([value,label])=>`<option value="${value}" ${value===filter?'selected':''}>${label}</option>`).join('')}</select><span class="sub">${rows.length} of ${result.rows.filter(r=>!scope||r.kind===scope).length} options &middot; highest FD / meso first</span></div>
      <p class="sub filter-description">${esc(filters.find(([value])=>value===filter)?.[2]||'')}</p><div class="sc-suggest-list">${rows.map((r,i)=>`<details class="card sc-suggest-row" data-suggestion="${esc(r.slot)}" data-method="${esc(r.method)}"><summary>
        <div class="sc-suggest-item"><span class="sc-rank">${i+1}</span><img data-equip="${esc(r.slot)}" width="36" height="36" alt="" hidden><span class="sc-suggest-placeholder" aria-hidden="true">&#9671;</span><span><strong>${esc(r.name)}</strong><small><span aria-hidden="true">${({flame:"&#128293;",starforce:"&#11088;",cube:"&#129482;"})[r.kind]||""}</span> ${esc(r.method)} · ${esc(r.slot.replaceAll('_',' '))}${r.kind==='starforce'?` · ${r.current_stars} → ${r.target_stars}★${r.strategy_label?' · '+esc(r.strategy_label):''}`:''}${r.cooldown_seconds!=null?` · ${r.cooldown_seconds>0?'−':''}${number(r.cooldown_seconds)}s cooldown`:''}</small></span></div>
        <div class="sc-suggest-metric"><small>${r.kind==='starforce'?'FD gain':'Avg FD gain'}</small><strong>+${number(r.expected_fd,4)}%</strong></div><div class="sc-suggest-metric"><small>${r.kind==='flame'?'First improving flame':'Expected cost'}</small><strong>${money(r.expected_mesos)}</strong>${r.kind==='starforce'&&r.expected_booms!=null?`<small class="sc-suggest-booms">${number(r.expected_booms,2)} expected booms</small>`:''}</div><div class="sc-suggest-metric sc-suggest-value"><small>FD per 1B</small><strong>+${number(r.fd_per_billion,4)}%</strong></div>
        </summary><div class="sc-suggest-detail"><p>${esc(r.goal)}</p><div class="sc-suggest-details-grid"><div><strong>Current</strong>${r.current.map(s=>`<div class="sub">${esc(s)}</div>`).join('')}</div><div><strong>Odds & cost</strong>${r.kind==='starforce'?`<div class="sub">${number(r.expected_rolls,1)} taps on average, including recovery</div>`:`<div class="sub">${number(r.probability*100,5)}% per roll · ${number(r.expected_rolls,1)} rolls on average</div><div class="sub">${money(r.cost_90)} for a 90% chance</div>`}</div>${r.examples.length?`<div><strong>${r.kind==='starforce'?'Stats gained':'Example qualifying roll'}</strong>${r.examples.map(s=>`<div class="sub">${esc(s)}</div>`).join('')}</div>`:''}${r.protected.length?`<div><strong>Preserved lines</strong>${r.protected.map(s=>`<div class="sub">${esc(s)}</div>`).join('')}</div>`:''}</div>${starforceDetails(r)}${flameDetails(r)}${r.notes.map(s=>`<p class="sub">${esc(s)}</p>`).join('')}<p class="sub">Expected cost is an average. ${r.kind==='starforce'?'FD gain is the estimated change at the target stars.':'Avg FD gain is the average improvement among qualifying results.'}</p></div></details>`).join('')||'<div class="card empty">No qualifying upgrades for this selection.</div>'}</div>
      ${result.skipped.length?`<details class="card sc-suggest-intro"><summary>Not ranked · ${result.skipped.length}</summary>${result.skipped.map(r=>`<p class="sub"><strong>${esc(r.name)} · ${esc(r.kind)}</strong><br>${esc(r.reason)}</p>`).join('')}</details>`:''}`;
    if(layout==='cards'){
      const list=body.querySelector('.sc-suggest-list');
      list.classList.add('suggestion-cards','upgrade-order');
      list.querySelectorAll(':scope > .sc-suggest-row').forEach((tile,index)=>{
        const r=rows[index],sf=r.kind==='starforce';
        const summary=tile.querySelector(':scope > summary');
        summary.classList.add('enhancement-item');
        summary.title=r.goal+' - click for details';
        summary.innerHTML=`<span class="sub upgrade-position">${index+1} &middot; ${esc(sf?r.strategy_label||'Star Force':r.method)}</span><img data-equip="${esc(r.slot)}" width="36" height="36" alt="" hidden><span class="sc-suggest-placeholder" aria-hidden="true">&#9671;</span><span class="enhancement-name">${esc(r.name)}</span>${sf?`<strong>${r.current_stars} &rarr; ${r.target_stars}&#9733;</strong>`:`<strong>${number(r.probability*100,3)}% per roll</strong>`}<strong class="enhancement-price">${money(r.expected_mesos)}</strong><span class="sub">+${number(r.expected_fd,3)}% FD${sf?'':' avg.'}</span>${sf&&r.expected_booms!=null?`<span class="sub">${number(r.expected_booms,2)} expected booms</span>`:''}<span class="sub upgrade-details-hint">Details</span>`;
        if(index<rows.length-1){const arrow=document.createElement('span');arrow.className='upgrade-arrow';arrow.setAttribute('aria-hidden','true');arrow.innerHTML='&rarr;';summary.append(arrow);}
      });
      const intro=body.querySelector('.sc-suggest-intro');
      if(intro&&!intro.matches('details')){
        const details=document.createElement('details');details.className='sc-suggest-intro upgrade-model';
        details.innerHTML='<summary class="sub">Calculation details</summary>'+intro.innerHTML;
        intro.replaceWith(details);
      }
      const allowed=scope==='cube'?['best','all','Bright','Glowing']:['best','best-booms','all'];
      body.querySelectorAll(`#${prefix}-suggest-filter option`).forEach(option=>{if(!allowed.includes(option.value))option.remove();});
    }
    body.querySelector(`#${prefix}-suggest-filter`).onchange=e=>{filter=e.target.value;render();body.querySelector(`#${prefix}-suggest-filter`).focus({preventScroll:true});};
    const id=profile.character.id;
    for(const img of body.querySelectorAll('[data-equip]')) {
      const path=`/api/characters/${encodeURIComponent(id)}/equipment/${encodeURIComponent(img.dataset.equip)}/icon?v=${encodeURIComponent(profile.gear_fingerprint||result.gear_fingerprint||'')}`;
      if(!urls.has(path)) urls.set(path,api.blobUrl(path).catch(()=>{urls.delete(path);return null;}));
      urls.get(path).then(url=>{
        // Routes finish mounting before app.js attaches them to the document.
        // Keep images belonging to this render, including during that mount.
        if(disposed||!root.contains(img))return;
        if(url){
          img.onload=()=>{if(!disposed&&root.contains(img)){img.hidden=false;img.nextElementSibling.hidden=true;}};
          img.onerror=()=>{img.hidden=true;img.nextElementSibling.hidden=false;};
          img.src=url;
        }
      });
    }
  }
  return {
    update(data,edited=false){profile=data;dirty=edited;render();},
    setBusy(value){busy=value;enabled();},
    dispose(){disposed=true;for(const promise of urls.values())promise.then(url=>{if(url)URL.revokeObjectURL(url);});urls.clear();},
  };
}
