import {keepViewport} from './viewport.js';
import {api} from './api.js';
import {escapeHtml as esc} from './ui.js';
import {compactCost} from './format.js';
import {COST_PARTS} from './components/gear_tooltip.js';

// Flame upgrade-order display.
export const flameIcon = '<svg class="flame-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="#fb923c" d="M13 2c1 5-3 6-3 10-2-1-3-3-3-5-3 3-5 7-4 10a9 9 0 0 0 18-2c0-4-3-8-8-13Z"/><path fill="#fde68a" d="M12 12c1 3 4 4 4 6a4 4 0 0 1-8 0c0-2 2-4 4-6Z"/></svg>';
const number = v => Number(v).toLocaleString(undefined,{maximumFractionDigits:1});
const score = v => Number(v).toFixed(1);
const cost = v => v == null ? 'Unavailable' : compactCost(v);
const percent = v => (v*100).toLocaleString(undefined,{maximumFractionDigits:3})+'%';
const exact = v => v == null ? 'No matching outcome in the published table' : Math.round(v).toLocaleString()+' mesos';
const MODE_STARS=[15,16,17,18,19,20,21];
const modeName=m=>m==='safeguard'?'Safeguard':'Mode '+m;
// Older saves chose one mode for 15–17★ and one for 18–21★.
const perStarModes=m=>m&&'mode_15_17' in m?Object.fromEntries(MODE_STARS.map(star=>[star,star<=17?m.mode_15_17:m.mode_18_21])):m;
// Runs of stars, e.g. "15–16★ Safeguard, 17–19★ Mode 1, 20–21★ Mode 4".
const modeSummary=m=>MODE_STARS.reduce((runs,star)=>{const last=runs.at(-1);if(last&&last.mode===m[star])last.to=star;else runs.push({from:star,to:star,mode:m[star]});return runs;},[]).map(r=>`${r.from}${r.to!==r.from?'–'+r.to:''}★ ${modeName(r.mode)}`).join(', ');
// Range presets for per-attempt modes, as on common Star Force planners.
const PRESET_STARS={low:[15,16,17],high:[18,19,20,21]};
const PRESETS={
 low:[['1,1,1','111','Mode 1 for all three attempts'],['2,2,2','222','Mode 2 for all three attempts'],['3,3,3','333','Mode 3 for all three attempts'],['safeguard,safeguard,safeguard','Safeguard','Prevents destruction for all three attempts']],
 high:[['1,1,1,1','1111','Mode 1 for all four attempts'],['1,1,4,4','1144','Mode 1 for 18★→20★, then Mode 4'],['4,4,4,4','4444','Prevents destruction for all four attempts']],
};
const chance=v=>(v*100).toLocaleString(undefined,{maximumFractionDigits:2})+'%';
const flameBasis = 'Black Flame: 3M per roll. Upgrade order uses a strictly higher Flame Score; current cost matches or exceeds the saved score. These are expected costs, not guaranteed CP gains.';
const cubeBasis = 'Bright: 22M; Glowing: 12M per cube. Match current main-stat or attack equivalent, retaining Crit Damage and cooldown. Drop, mesos, IED and other utility lines are excluded. Tier-up and reveal costs are excluded.';

export function mountEnhancement(root,{profile,page,slot,onSelect}) {
 let disposed=false,model=null,cube=localStorage.getItem('hascone.costCube')==='Glowing'?'Glowing':'Bright';
 let showScores=localStorage.getItem('hascone.flameScores')!=='false';
 const totals=root.querySelector('#enhancement-totals'),selected=root.querySelector('#enhancement-selected'),panels=root.querySelector('#enhancement-panels');
 totals.innerHTML='<p class="sub" role="status">Calculating equipment costs…</p>';
 selected.innerHTML='<p class="sub" role="status">Calculating expected costs…</p>';
 function art(row) {return `<img src="/api/characters/${profile.id}/equipment/${encodeURIComponent(row.slot)}/icon?t=${encodeURIComponent(profile.equipment_captured||'')}" alt="" loading="lazy">`;}
 function unpriced(kind) {
  const rows=model.unpriced[kind];
  return rows.length?`<details class="unpriced"><summary>${rows.length} unpriced ${kind==='flame'?'flames':kind==='starforce'?'items':'potentials'}</summary>${rows.map(r=>`<p><strong>${esc(r.name)}</strong>: ${esc(r.reason)}</p>`).join('')}</details>`:'';
 }
 function cards(rows,kind) {
  if(!rows.length)return '<p class="sub">Scan eligible equipment to see estimates.</p>';
  return `<div class="enhancement-grid ${kind==='upgrade'?'upgrade-order':''}">${rows.map((r,index)=>{
   const upgrade=kind==='upgrade',pot=kind==='cube';
   const estimate=pot?r.cubes.find(c=>c.cube===cube):r;
   const title=upgrade?`${percent(r.probability)} chance per roll; ${r.expected_rolls==null?'maximum score':number(r.expected_rolls)+' expected rolls'}`:pot?`${number(estimate.expected_cubes)} expected ${cube} cubes`:`${number(r.expected_rolls)} expected Black Flames`;
   return `<div class="enhancement-step"><button class="enhancement-item ${slot===r.slot?'selected':''} ${upgrade&&r.flame_advantaged===false?'normal-flame':''}" data-enhancement-slot="${esc(r.slot)}" title="${esc(title)}">
    ${!pot&&showScores?`<span class="flame-score">${flameIcon}${score(r.score)}</span>`:''}
    ${art(r)}<span class="enhancement-name">${esc(r.name)}</span>
    ${upgrade?`<strong>${percent(r.probability)}</strong>`:pot?`<span class="sub">${number(r.value)}% equivalent</span>`:''}
    <strong class="enhancement-price" title="${esc(exact(estimate.expected_mesos))}">${upgrade&&r.probability===0?'Max score':cost(estimate.expected_mesos)}</strong>
    ${pot?`<span class="sub">${number(estimate.expected_cubes)} cubes</span>`:''}
   </button>${upgrade&&index<rows.length-1?'<span class="upgrade-arrow" aria-hidden="true">&rarr;</span>':''}</div>`;
  }).join('')}</div>`;
 }
 function totalValue(name,value,count) {return `<div><span>${esc(name)}</span><strong title="${esc(exact(value))}">${count?cost(value):'—'}</strong></div>`;}
 function draw(selectionOnly=false) {return keepViewport(panels,()=>drawContents(selectionOnly));}
 function drawContents(selectionOnly=false) {
  if(page==='starforce'){drawStarForce(selectionOnly);return;}
  if(page==='equipment'){drawEquipment(selectionOnly);return;}

  const selected=root.querySelector('#enhancement-selected');
  const f=model.flame_costs.length,c=model.cube_costs.length;
  totals.innerHTML=`<h3>Current equipment cost</h3><div class="enhancement-totals">${page!=='potential'?totalValue('Flames',model.totals['Black Flame'],f):''}${page!=='flame'?totalValue('Bright cubes',model.totals.Bright,c)+totalValue('Glowing cubes',model.totals.Glowing,c):''}</div><p class="sub">${page==='flame'?`${f} flames`:page==='potential'?`${c} potentials`:`${f} flames · ${c} potentials`}${model.unpriced.flame.length||model.unpriced.cube.length?' · Partial estimates':''}</p><p class="sub">Expected cost to match current gear.</p>`;
  const item=model.items[slot]||{};
  let details=item.mirror?`<p class="sub">${esc(item.mirror)}</p>`:'';
  if(page!=='potential'&&item.flame_upgrade)details+=`<section><h3>${flameIcon} Flame costs</h3><p class="sub">Level ${item.catalog.level} · ${item.catalog.flame_advantaged?'Flame advantaged':'Not flame advantaged'}</p><div class="enhancement-totals">${totalValue('Match current score',item.flame_current.expected_mesos,1)}${totalValue('Improve score',item.flame_upgrade.expected_mesos,1)}</div><p class="sub">${percent(item.flame_upgrade.probability)} per roll${item.flame_upgrade.expected_rolls!=null?' · '+number(item.flame_upgrade.expected_rolls)+' expected rolls':' · Maximum modeled score'}</p></section>`;
  else if(page!=='potential'&&item.flame_error)details+=`<p class="sub">Flame cost: ${esc(item.flame_error)}</p>`;
  if(page!=='flame'&&item.cube_current)details+=`<section><h3>Current potential cost</h3><div class="enhancement-totals">${item.cube_current.map(c=>`<div><span>${c.cube}</span><strong title="${esc(exact(c.expected_mesos))}">${cost(c.expected_mesos)}</strong><small>${c.expected_cubes==null?'Unavailable':number(c.expected_cubes)+' expected cubes'}</small></div>`).join('')}</div></section>`;
  else if(page!=='flame'&&item.cube_error)details+=`<p class="sub">Potential cost: ${esc(item.cube_error)}</p>`;
  selected.innerHTML=details;
  if(selectionOnly){
   panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.classList.toggle('selected',b.dataset.enhancementSlot===slot));
   return;
  }
  if(page==='flame') {
   panels.innerHTML=`<section class="analysis-panel"><header><h2>Flame upgrade order</h2><label class="score-toggle"><input type="checkbox" role="switch" id="show-flame-scores" ${showScores?'checked':''}> Show scores</label></header><p class="sub">Best chance of a higher Flame Score first.</p>${cards(model.flame_order,'upgrade')}${unpriced('flame')}</section><section class="analysis-panel"><h2>Current flame costs</h2><p class="sub">Cost to match or exceed each saved score · Lowest cost first.</p>${cards(model.flame_costs,'flame')}<details><summary>How costs are calculated</summary><p class="sub">${flameBasis}</p></details></section>`;
   panels.querySelector('#show-flame-scores').onchange=e=>{showScores=e.target.checked;localStorage.setItem('hascone.flameScores',showScores);draw();};
  } else if(page==='potential') {
   const rows=[...model.cube_costs].sort((a,b)=>a.cubes.find(c=>c.cube===cube).expected_mesos-b.cubes.find(c=>c.cube===cube).expected_mesos);
   panels.innerHTML=`<section class="analysis-panel"><header><h2>Current potential costs</h2><label>Sort by <select id="cost-cube" class="input"><option ${cube==='Bright'?'selected':''}>Bright</option><option ${cube==='Glowing'?'selected':''}>Glowing</option></select></label></header><p class="sub">Cost to match your saved potentials · Lowest cost first.</p>${cards(rows,'cube')}${unpriced('cube')}<details><summary>How costs are calculated</summary><p class="sub">${cubeBasis}</p><p class="sub">The published tables use the calculator's level-160+ approximation. Gear under level 120 is treated as level 120; Rare/Epic costs are unavailable.</p></details></section>`;
   panels.querySelector('#cost-cube').onchange=e=>{cube=e.target.value;localStorage.setItem('hascone.costCube',cube);draw();};
  } else panels.innerHTML='';
  panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.onclick=()=>onSelect(b.dataset.enhancementSlot));
 }
 const orderedParts=combined=>COST_PARTS.filter(name=>name in combined.parts).map(name=>[name,combined.parts[name]]);
 function breakdown(combined){
  return orderedParts(combined).map(([name,mesos])=>`${name} ${cost(mesos)}`).join(' · ');
 }
 function drawEquipment(selectionOnly){
  const rows=model.combined_costs||[],t=model.totals;
  const cubes=rows.reduce((sum,r)=>sum+(r.parts.Cubes||0),0),partial=rows.some(r=>r.missing.length);
  totals.innerHTML=`<h3>Combined expected cost</h3><div class="enhancement-totals">${totalValue('Star Force',t['Star Force'],model.starforce_costs.length)}${totalValue('Flames',t['Black Flame'],model.flame_costs.length)}${totalValue('Cubes',cubes,model.cube_costs.length)}${totalValue('Total',t.Combined,rows.length)}</div><p class="sub">${rows.length} items${partial?' &middot; Partial estimate':''}</p><p class="sub">Expected cost to rebuild your current gear: Star Force from 0 stars, flames and cubes (the cheaper of Bright and Glowing) to match what you have.</p>`;
  const combined=model.items[slot]?.combined;
  root.querySelector('#enhancement-selected').innerHTML=combined?`<section><h3>Expected cost for this item</h3><div class="enhancement-totals">${orderedParts(combined).map(([name,mesos])=>totalValue(name+(name==='Cubes'&&model.items[slot].cube_cheapest?' ('+model.items[slot].cube_cheapest+')':''),mesos,1)).join('')}${totalValue('Combined',combined.expected_mesos,1)}</div>${combined.missing.map(m=>`<p class="sub">Not included &middot; ${esc(m)}</p>`).join('')}</section>`:`<p class="sub">${esc(model.items[slot]?.mirror||'Hover this item in the scan guide to price it.')}</p>`;
  if(!selectionOnly){
   panels.innerHTML=`<section class="analysis-panel"><h2>Combined cost per item</h2><p class="sub">Star Force + flames + cubes &middot; Lowest cost first.</p><div class="enhancement-grid">${rows.map(r=>`<div class="enhancement-step"><button class="enhancement-item ${slot===r.slot?'selected':''}" data-enhancement-slot="${esc(r.slot)}" title="${esc(breakdown(r))}">${art(r)}<span class="enhancement-name">${esc(r.name)}</span><strong class="enhancement-price">${cost(r.expected_mesos)}</strong><span class="sub">${esc(breakdown(r))}${r.missing.length?' &middot; partial':''}</span></button></div>`).join('')||'<p class="sub">Scan your equipment to see costs.</p>'}</div></section>`;
   panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.onclick=()=>onSelect(b.dataset.enhancementSlot));
  }else panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.classList.toggle('selected',b.dataset.enhancementSlot===slot));
 }
 // Per-item Star Force modes, one per attempt: sliders and range presets save on the item, then costs refresh.
 function bindModes(table,saved){
  const own=root.querySelector('#sf-own-modes');if(!own)return;
  const fields=root.querySelector('.sf-mode-fields'),sliders=[...root.querySelectorAll('[data-mode-star]')];
  const choice=el=>table.find(r=>r.star===Number(el.dataset.modeStar)).choices[Number(el.value)];
  function show(el){
   const row=el.closest('.sf-mode-row'),picked=choice(el);
   el.setAttribute('aria-valuetext',modeName(picked.mode));
   row.querySelectorAll('[data-stop]').forEach(stop=>stop.classList.toggle('is-on',stop.dataset.stop===el.value));
   row.querySelector('[data-success]').textContent=chance(picked.success);
   const boom=row.querySelector('[data-boom]');boom.textContent=chance(picked.boom);boom.classList.toggle('is-safe',!picked.boom);
   row.querySelector('[data-cost]').textContent=cost(picked.cost);
  }
  async function save(){
   const status=root.querySelector('#sf-modes-status');
   const chosen=Object.fromEntries(sliders.map(el=>[el.dataset.modeStar,choice(el).mode]));
   // Stars above this item's limit keep their saved choice so the full set stays valid.
   const body={modes:own.checked?Object.fromEntries(MODE_STARS.map(star=>[star,chosen[star]??saved?.[star]??1])):null};
   root.querySelectorAll('.sf-item-modes input,.sf-item-modes select').forEach(el=>el.disabled=true);status.textContent='Saving…';
   try{const fresh=await api.post(`/api/characters/${profile.id}/equipment/${encodeURIComponent(slot)}/starforce-modes`,body);Object.assign(profile,fresh);await refresh();}
   catch(e){status.textContent=e.message;root.querySelectorAll('.sf-item-modes input,.sf-item-modes select').forEach(el=>el.disabled=false);}
  }
  own.onchange=()=>{fields.hidden=!own.checked;save();};
  sliders.forEach(el=>{el.oninput=()=>show(el);el.onchange=save;});
  root.querySelectorAll('[data-stop]').forEach(stop=>stop.onclick=()=>{const el=stop.closest('.sf-mode-row').querySelector('[data-mode-star]');if(el.value===stop.dataset.stop)return;el.value=stop.dataset.stop;show(el);save();});
  root.querySelectorAll('[data-preset]').forEach(select=>select.onchange=()=>{
   const pattern=select.value.split(',');
   sliders.filter(el=>PRESET_STARS[select.dataset.preset].includes(Number(el.dataset.modeStar))).forEach(el=>{
    const star=Number(el.dataset.modeStar),mode=pattern[PRESET_STARS[select.dataset.preset].indexOf(star)];
    el.value=String(table.find(r=>r.star===star).choices.findIndex(c=>String(c.mode)===mode));show(el);
   });
   save();
  });
 }
 function drawStarForce(selectionOnly){
  const rows=model.starforce_costs||[],cfg=model.starforce_options||{};
  const basis='Expected cost from 0 stars to the scanned level, using the least-meso mode at each step and including recovery after destruction. Replacement items are excluded.';
  totals.innerHTML=`<h3>Current Star Force cost</h3><div class="enhancement-totals">${totalValue('Total',model.totals['Star Force'],rows.length)}</div><p class="sub">${rows.length} items${model.unpriced.starforce.length?' &middot; Partial estimate':''}</p><p class="sub">${cfg.discount?'30% meso discount':'No meso discount'} &middot; ${cfg.boom_reduction?'30% boom reduction':'No boom reduction'}</p>`;
  const item=model.items[slot]||{},current=item.starforce_current,gear=profile.equipment[slot]||{},modes=perStarModes(gear.starforce_modes);
  const basisText=modes?`Expected cost from 0 stars to the scanned level using this item's modes (${modeSummary(modes)}), including recovery after destruction. Replacement items are excluded.`:basis;
  const table=item.starforce_mode_table||[],picked=modes||{};
  const presetValue=range=>{const pattern=PRESET_STARS[range].map(star=>String(picked[star]??1)).join(',');return PRESETS[range].some(([value])=>value===pattern)?pattern:'custom';};
  const presetSelect=range=>table.some(r=>PRESET_STARS[range].includes(r.star))?`<label>${range==='low'?'15→18':'18→22'}<select class="input" data-preset="${range}" aria-label="${range==='low'?'15 to 18':'18 to 22'} preset">${presetValue(range)==='custom'?'<option value="custom" selected disabled>Custom</option>':''}${PRESETS[range].map(([value,label,note])=>`<option value="${value}" ${presetValue(range)===value?'selected':''} title="${esc(note)}">${label}</option>`).join('')}</select></label>`:'';
  const modeRow=r=>{
   const index=Math.max(0,r.choices.findIndex(c=>String(c.mode)===String(picked[r.star]??1))),c=r.choices[index];
   return `<div class="sf-mode-row"><span class="sf-mode-attempt">${r.star} → ${r.star+1}</span><div class="sf-mode-slider"><input class="sf-range" type="range" min="0" max="3" step="1" value="${index}" data-mode-star="${r.star}" aria-label="Strategy for ${r.star} stars" aria-valuetext="${modeName(c.mode)}"><div class="sf-mode-stops">${r.choices.map((choice,i)=>`<button type="button" data-stop="${i}" class="${i===index?'is-on':''}" style="--i:${i}" tabindex="-1">${modeName(choice.mode)}</button>`).join('')}</div></div><span class="sf-mode-num" data-success>${chance(c.success)}</span><span class="sf-mode-num is-boom ${c.boom?'':'is-safe'}" data-boom>${chance(c.boom)}</span><span class="sf-mode-num" data-cost>${cost(c.cost)}</span></div>`;
  };
  const modeControls=gear.starforce?.status==='scanned'&&!item.mirror&&table.length?`<section class="sf-item-modes"><h3>Enhancement modes for this item</h3><label class="score-toggle"><input type="checkbox" role="switch" id="sf-own-modes" ${modes?'checked':''}> Use my own modes</label><div class="sf-mode-fields" ${modes?'':'hidden'}><div class="sf-presets"><span><strong>Quick presets</strong><small>Apply a strategy to a range of stars</small></span>${presetSelect('low')}${presetSelect('high')}</div><div class="sf-modes-table"><div class="sf-mode-row is-head"><span>Attempt</span><span>Strategy</span><span>Success</span><span>Boom</span><span>Cost</span></div>${table.map(modeRow).join('')}</div><p class="sub">Safeguard (15–17★) and Mode 4 (18–21★) prevent destruction. Success, boom and cost are per attempt, with your event settings.</p></div><p class="sub" id="sf-modes-status">${modes?'The upgrade order and costs for this item use these modes.':'Off: each star uses whichever mode is cheapest, and the upgrade order also shows a fewest-booms plan.'}</p></section>`:'';
  root.querySelector('#enhancement-selected').innerHTML=(current?`<section><h3>Current Star Force cost</h3><div class="enhancement-totals">${totalValue('0 to '+current.stars+' stars',current.expected_mesos,1)}</div><p class="sub">${number(current.expected_booms)} expected booms &middot; Level ${current.level}</p><p class="sub">${basisText}</p></section>`:`<p class="sub">${esc(item.mirror||item.starforce_error||'Hover this item to scan its stars.')}</p>`)+modeControls;
  bindModes(table,modes);
  if(!selectionOnly){
   panels.innerHTML=`<section class="analysis-panel"><h2>Current Star Force costs</h2><p class="sub">Cost to reach scanned stars &middot; Lowest cost first.</p><div class="enhancement-grid">${rows.map(r=>`<div class="enhancement-step"><button class="enhancement-item ${slot===r.slot?'selected':''}" data-enhancement-slot="${esc(r.slot)}">${art(r)}<span class="enhancement-name">${esc(r.name)}</span><strong>${r.stars}&#9733;</strong><strong class="enhancement-price">${cost(r.expected_mesos)}</strong><span class="sub">${number(r.expected_booms)} expected booms</span></button></div>`).join('')||'<p class="sub">Scan Star Force equipment to see costs.</p>'}</div>${unpriced('starforce')}<details><summary>How costs are calculated</summary><p class="sub">${basis}</p><p class="sub">Uses the discount and boom-reduction options above. These are modeled costs.</p></details></section>`;
   panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.onclick=()=>onSelect(b.dataset.enhancementSlot));
  }else panels.querySelectorAll('[data-enhancement-slot]').forEach(b=>b.classList.toggle('selected',b.dataset.enhancementSlot===slot));
 }
 let revision=0;
 async function refresh(){
  const current=++revision;
  try{const data=await api.get(`/api/characters/${profile.id}/enhancement-analysis`);if(!disposed&&current===revision){model=data;draw();}}
  catch(error){if(!disposed&&current===revision){totals.textContent=error.message;root.querySelector('#enhancement-selected').textContent='Costs unavailable. Your scans are saved.';}}
 }
 refresh();
 const dispose=()=>{disposed=true;};
 dispose.refresh=refresh;
 dispose.select=key=>{slot=key;if(model&&!disposed)draw(true);};
 // undefined while loading; null when the item has no priced parts.
 dispose.combined=key=>model?(model.items[key]?.combined??null):undefined;
 return dispose;
}
