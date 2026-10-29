import { api } from '../api.js';
import { escapeHtml as esc, toast } from '../ui.js';
import { equipGrid, slotLabel } from '../components/equip_grid.js';
import { renderBossPanels } from './scouter-bosses.js';

const fmt = v => Number(v).toLocaleString(undefined,{maximumFractionDigits:3});
const signed = v => `${Number(v)>0?'+':''}${fmt(v)}`;
const clone = v => JSON.parse(JSON.stringify(v));
const part = slot => slot.split('_')[0];
// Earlier builds kept unsimulated edits here; only simulated runs are saved now.
const legacyDraftKey = id => `hascone.scouter.swap.${id}`;
const STATS = ['str','dex','int','luk'];
const POTENTIAL = ['mainStatPer','subStatPer','ssubStatPer','allStatPer','atkPer','bossDmg','damage','ignoreGuard','criDmg','coolTimeReduce'];
const NOTE = 'For accurate results, make sure your gear is scanned up to date with your calculated Scouter profile.';

// Which slots a run sends: enabled ones only. Exported for tests.
export function enabledSlots(config){return Object.entries(config?.slots||{}).filter(([,e])=>e.enabled).map(([s])=>s).sort();}

const canonical = v => JSON.stringify(v,(k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0)):x);
export function sameConfig(a,b){return canonical(a)===canonical(b);}

export function freshConfig(data){
  return {slots:Object.fromEntries(data.slots.map(s=>[s,{enabled:false,current:clone(data.current[s]||{item:null}),candidate:{}}])),groups:[]};
}

// A saved run keeps its inputs; slots added since then start from the scan.
export function restoreConfig(saved,data){
  const config=freshConfig(data);
  if(!saved||typeof saved!=='object')return config;
  for(const [slot,entry] of Object.entries(saved.slots||{}))if(config.slots[slot])config.slots[slot]=clone(entry);
  // Swaps saved before groups took signed values carried a Gain/Lose mode; fold it into the signs.
  config.groups=(Array.isArray(saved.groups)?clone(saved.groups):[]).map(({mode,...g})=>mode!=='lose'?g:
    {...g,fields:Object.fromEntries(Object.entries(g.fields||{}).map(([k,v])=>[k,Number(v)?String(-Number(v)):v]))});
  return config;
}

// "Copy from current": upgrades always; add-ons, stage and custom base only when it is the same item.
export function copiedCandidate(current={},candidate={}){
  const item=candidate?.item||current?.item||null;
  const keys=['stars','flame','potential','other',...(item===current?.item?['addons','variant','custom_base','custom_level']:[])];
  return {item,...clone(Object.fromEntries(keys.filter(k=>current?.[k]!==undefined).map(k=>[k,current[k]])))};
}

export function createSwap(view,{onRun,onBaseline,onDeleteRun,loadIcons}) {
  let profile, baseline, data=null, dataKey='', loading='', config=null, focus='', preview=null, previewing=false;
  let selected='', count=0, busy=false, timer=0, serial=0, filter='relevant', runKey='';
  const openOther=new Set(), openGroups=new Set();
  const q = s => view.querySelector(s);
  const cls = () => data.class;
  const att = () => cls().magic?'MATT':'ATT';
  const short = k => ({mainStat:cls().main,subStat:cls().sub,ssubStat:cls().sub2,mainStatPer:`${cls().main} %`,subStatPer:`${cls().sub} %`,
    ssubStatPer:`${cls().sub2} %`,allStatPer:'All stat %',atk:att(),atkPer:`${att()} %`,bossDmg:'Boss %',damage:'Damage %',ignoreGuard:'IED %',
    criDmg:'Crit dmg %',coolTimeReduce:'Cooldown (s)',buffDuration:'Buff duration %',resetCoolDown:'Cooldown skip %',criRate:'Crit rate %',
    finalDmg:'Final damage %'}[k]||k);
  const ORDER = ['mainStat','subStat','ssubStat','atk','mainStatPer','subStatPer','ssubStatPer','allStatPer','atkPer','bossDmg','damage','ignoreGuard','criDmg','coolTimeReduce'];
  const rank = k => ORDER.includes(k)?ORDER.indexOf(k):ORDER.length;
  const describe = d => Object.entries(d||{}).sort(([a],[b])=>rank(a)-rank(b)).map(([k,v])=>`${short(k)} ${signed(v)}`).join(', ')||'No change';
  const fieldLabel = f => f.label.replace('Other secondary stat',cls().sub2||'Other secondary stat').replace('Secondary stat',cls().sub).replace('Main stat',cls().main);
  const simFields = () => profile.simulator_fields.filter(f=>!f.key.startsWith('ssubStat')||cls().sub2);
  const items = () => Object.fromEntries(data.items.map(i=>[i.id,i]));
  const characterId = () => profile.character.id;
  const runs = () => [...(baseline?.swap_runs||[])];
  // Saved runs come back with keys sorted, so compare key-order independently.
  const pendingChanges = () => {const run=runs().find(r=>r.id===selected);return !run||sameConfig(restoreConfig(run.config,data),config)===false;};

  function variantOf(record,side){
    if(!record?.variants)return null;
    const want=side.variant||{};
    return record.variants.find(v=>v.stage===want.stage&&v.version===(want.version||1))||record.variants.reduce((a,b)=>b.stage>a.stage||(b.stage===a.stage&&b.version<a.version)?b:a);
  }
  function capOf(record,side){
    if(!record)return 50;
    if(!record.starforce)return 0;
    return variantOf(record,side)?.max_stars??record.star_cap;
  }
  const BASE_ORDER=['str','dex','int','luk','att','matt','bossDmg','ignoreGuard','criDmg','finalDmg'];
  const addonText = per => [per.allstat?`+${per.allstat} all stat`:'',per.att?`+${per.att} ${att()}`:'',per.finalDmg?`+${per.finalDmg}% final damage`:''].filter(Boolean).join(', ');
  // "19★ Total Control": stars only where the item can have them.
  function itemLabel(side){
    if(!side?.item)return 'Empty';
    const record=items()[side.item], variant=variantOf(record,side);
    const name=record?record.name:(side.scanned_name||'Custom item');
    const stage=variant?` (Stage ${variant.stage}${new Set(record.variants.map(v=>v.version)).size>1?`, version ${variant.version}`:''})`:'';
    const starred=record?capOf(record,side)>0:!!side.custom_level;
    return `${starred?`${Number(side.stars)||0}★ `:''}${name}${stage}`;
  }
  function baseText(base){
    return BASE_ORDER.filter(k=>base?.[k]&&k!==(cls().magic?'att':'matt')).map(k=>[k,base[k]]).map(([k,v])=>`${{str:'STR',dex:'DEX',int:'INT',luk:'LUK',att:'ATT',matt:'MATT',bossDmg:'Boss',ignoreGuard:'IED',criDmg:'Crit dmg',finalDmg:'Final damage'}[k]||k} +${v}${['bossDmg','ignoreGuard','criDmg','finalDmg'].includes(k)?'%':''}`).join(' · ')||'No stats';
  }
  const box = (which,path,text,value,attrs='step="any"') => `<label><span>${esc(text)}</span><input class="input" type="number" data-side="${which}" data-path="${path}" value="${esc(value??'')}" placeholder="0" ${attrs}></label>`;

  function sideHtml(slot,which){
    const side=config.slots[slot][which]||{}, record=items()[side.item], list=data.items.filter(i=>i.slot===part(slot));
    const custom=side.item==='custom', key=`${slot}:${which}`;
    const options=`<option value="">${which==='current'?'Empty slot':'Choose an item…'}</option>${list.map(i=>`<option value="${esc(i.id)}" ${i.id===side.item?'selected':''}>${esc(i.name)}${i.level?` · Lv ${i.level}`:''}</option>`).join('')}<option value="custom" ${custom?'selected':''}>Custom item</option>`;
    const copy=which==='candidate'&&config.slots[slot].current?.item?'<button class="btn btn-sm" type="button" data-copy-current title="Copy stars, flames, potential and other bonuses from the current item. Picks the same item if no candidate is chosen.">Copy from current</button>':'';
    let html=`<section class="sc-swap-side" data-which="${which}"><div class="sc-swap-side-head"><h4>${which==='current'?'Current item':'Candidate'}</h4>${copy}</div>
      ${which==='current'&&side.scanned_name?`<p class="sub">Scanned: ${esc(side.scanned_name)}</p>`:''}
      <label class="sc-swap-pick"><span>Item</span><select class="input" data-item="${which}" aria-label="${which==='current'?'Current':'Candidate'} item for ${esc(slotLabel(slot))}">${options}</select></label>`;
    if(!side.item)return html+`<p class="sub">${which==='current'?'Nothing equipped here. A candidate counts in full.':'Pick the item you would wear instead.'}</p></section>`;
    if(record){
      const variant=variantOf(record,side), cap=capOf(record,side);
      if(record.variants){
        const stages=[...new Set(record.variants.map(v=>v.stage))], versions=[...new Set(record.variants.map(v=>v.version))];
        html+=`<div class="sc-swap-variant"><label><span>Stage</span><select class="input" data-variant="stage" data-side="${which}">${stages.map(s=>`<option value="${s}" ${s===variant.stage?'selected':''}>Stage ${s}</option>`).join('')}</select></label>${versions.length>1?`<label><span>Version</span><select class="input" data-variant="version" data-side="${which}">${versions.map(v=>`<option value="${v}" ${v===variant.version?'selected':''}>Version ${v}</option>`).join('')}</select></label>`:''}</div>${side.pick_variant?'<p class="sc-warning">Pick the stage'+(versions.length>1?' and version':'')+'; the scan cannot read it.</p>':''}`;
      }
      html+=`<div class="sc-swap-base"><strong>${esc(baseText(variant?.base||record.base))}</strong><small>${[record.level?`Lv ${record.level}`:'',record.set_label||'',cap?`Max ${cap}★`:'No Star Force'].filter(Boolean).map(esc).join(' · ')}</small>${record.note?`<small>${esc(record.note)}</small>`:''}</div>`;
      if(record.unmodifiable)return html+`<p class="sub">This item cannot be flamed, cubed, Star Forced or scrolled.</p>${totalLine(slot,which)}</section>`;
    } else if(custom){
      html+=`${side.unlisted?`<p class="sc-warning">${esc(side.scanned_name||'This item')} is not in the item list. Enter its base stats from the tooltip (white numbers, before flames and stars).</p><label class="sc-swap-check"><input type="checkbox" data-side="${which}" data-path="no_base" ${side.no_base?'checked':''}> Continue without base stats</label>`:''}
        <fieldset class="sc-swap-boxes"><legend>Base stats</legend>${['str','dex','int','luk'].map(k=>box(which,`custom_base.${k}`,k.toUpperCase(),side.custom_base?.[k])).join('')}${box(which,'custom_base.att',att(),side.custom_base?.att)}${box(which,'custom_base.bossDmg','Boss %',side.custom_base?.bossDmg)}${box(which,'custom_base.ignoreGuard','IED %',side.custom_base?.ignoreGuard)}${box(which,'custom_base.criDmg','Crit dmg %',side.custom_base?.criDmg)}${box(which,'custom_level','Level',side.custom_level,'min="1" max="300" step="1"')}</fieldset>`;
    }
    const cap=capOf(record,side), parts=preview?.slots?.[slot]?.parts?.[which];
    if(cap||custom)html+=`<div class="sc-swap-stars">${box(which,'stars','Stars',side.stars,`min="0" max="${cap||30}" step="1"`)}<small data-parts="${which}:starforce">${parts?.starforce?esc(describe(parts.starforce)):''}</small></div>`;
    if(!record||record.flame)html+=`<fieldset class="sc-swap-boxes"><legend>Flame</legend>${STATS.map(k=>box(which,`flame.${k}`,k.toUpperCase(),side.flame?.[k])).join('')}${box(which,'flame.att','ATT',side.flame?.att)}${box(which,'flame.matt','MATT',side.flame?.matt)}${box(which,'flame.allStatPer','All stat %',side.flame?.allStatPer)}</fieldset>`;
    if(!record||record.potential)html+=`<fieldset class="sc-swap-boxes"><legend>Potential <small>main + bonus, summed; IED lines combine (40% and 40% make 64%)</small></legend>${POTENTIAL.filter(k=>k!=='ssubStatPer'||cls().sub2).map(k=>box(which,`potential.${k}`,short(k),side.potential?.[k])).join('')}</fieldset>`;
    for(const addon of record?.addons||[])html+=addon.max===1
      ?`<label class="sc-swap-check"><input type="checkbox" data-side="${which}" data-path="addons.${esc(addon.id)}" ${Number(side.addons?.[addon.id])?'checked':''}> ${esc(addon.label)} <small>${esc(addonText(addon.per))}${which==='current'?' · tick if your current item has it':''}</small></label>`
      :`<div class="sc-swap-boxes">${box(which,`addons.${addon.id}`,`${addon.label} (0–${addon.max})`,side.addons?.[addon.id],`min="0" max="${addon.max}" step="1"`)}<small>Each ${esc(addonText(addon.per))}${which==='current'?' · enter what your current item has':''}</small></div>`;
    html+=`<details class="sc-swap-other" data-other="${esc(key)}" ${openOther.has(key)?'open':''}><summary>Other bonuses <small>scrolls, spell trace, enchants: anything the scan cannot see</small></summary><div class="sc-sim-fields">${simFields().map(f=>box(which,`other.${f.key}`,`${fieldLabel(f)} (${f.unit})`,side.other?.[f.key],`step="${f.step}"`)).join('')}</div></details>`;
    return html+totalLine(slot,which)+'</section>';
  }
  function totalLine(slot,which){
    const total=preview?.slots?.[slot]?.[which];
    return `<p class="sub sc-swap-total" data-total="${which}">${total?`From this item: ${esc(describe(total))}`:''}</p>`;
  }

  function renderEditor(){
    const host=q('#sc-swap-editor');if(!host)return;
    const entry=config.slots[focus];
    if(!entry){host.innerHTML='<p class="sub">Select a slot to compare items.</p>';return;}
    const notes=(data.notes[focus]||[]).filter(n=>!n.startsWith('Pick the stage'));
    host.innerHTML=`<div class="sc-swap-editor-head"><h3>${esc(slotLabel(focus))}</h3><label class="sc-swap-check"><input type="checkbox" id="sc-swap-enabled" ${entry.enabled?'checked':''} ${entry.candidate?.item?'':'disabled'}> Swap this slot</label></div>
      ${notes.map(n=>`<p class="sub">${esc(n)}</p>`).join('')}
      <div class="sc-swap-sides">${sideHtml(focus,'current')}${sideHtml(focus,'candidate')}</div>
      <p class="sc-swap-slot-delta" id="sc-swap-slot-delta" role="status">${slotDeltaText()}</p>`;
  }
  function slotDeltaText(){
    const row=preview?.slots?.[focus], error=preview?.errors?.[focus];
    if(error)return `<span class="sc-loss">${esc(error)}</span>`;
    if(!row?.candidate)return '';
    return `Change: <strong>${esc(describe(row.delta))}</strong>${row.enabled?'':' <small>(swap is off)</small>'}`;
  }
  function renderGrid(){
    const host=q('#sc-swap-grid');if(!host)return;
    host.innerHTML=equipGrid({characterId:characterId(),name:profile.character.name,slots:data.layout,equipment:data.equipment,captured:data.captured,selected:focus,
      slotClass:key=>config.slots[key]?.enabled?'sc-swap-on':'',
      badge:key=>{const e=config.slots[key];if(!e)return '';const stars=Number(e.current?.stars)||0;return `${e.enabled?'<span class="sc-swap-mark" title="Swap on">⇄</span>':''}${stars?`<span class="score">${stars}*</span>`:''}`;},
      disabled:key=>data.unswappable.includes(part(key))?`${slotLabel(key)} cannot be swapped`:''});
  }
  const groupSummary = g => `${g.enabled?'':'Off · '}${Object.entries(g.fields||{}).filter(([,v])=>Number(v)).map(([k,v])=>`${short(k)} ${signed(v)}`).join(', ')||'nothing yet'}`;
  function groupHtml(g){
    const fields=simFields();
    return `<details class="card sc-swap-group" data-group="${esc(g.id)}" ${openGroups.has(g.id)?'open':''}><summary><strong>${esc(g.name||'Untitled group')}</strong> <small>${esc(groupSummary(g))}</small></summary>
      <div class="sc-swap-group-head"><label><span>Name</span><input class="input" data-gpath="name" maxlength="80" placeholder="e.g. Pitched Boss 3 → 2 pieces" value="${esc(g.name||'')}"></label>
      <label class="sc-swap-check"><input type="checkbox" data-gpath="enabled" ${g.enabled?'checked':''}> Count this group</label>
      <span class="sc-actions"><button class="btn btn-sm" data-gaction="duplicate">Duplicate</button><button class="btn btn-sm btn-ghost" data-gaction="delete">Delete</button></span></div>
      <p class="sub">Enter bonuses you gain as positive numbers and bonuses you lose as negative ones (for example −10 boss damage for a set effect you give up). A negative IED or final damage value removes that source, so −10 IED is sent as about −11.1%.</p>
      <div class="sc-sim-groups">${['Damage','Stats','Other'].map(group=>`<fieldset><legend>${group}</legend><div class="sc-sim-fields">${fields.filter(f=>f.group===group).map(f=>`<label><span>${esc(fieldLabel(f))}<small>${esc(f.unit)}</small></span><input class="input" type="number" data-gfield="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" placeholder="0" value="${esc(g.fields?.[f.key]??'')}"></label>`).join('')}</div></fieldset>`).join('')}</div></details>`;
  }
  function renderGroups(){
    const host=q('#sc-swap-groups');if(!host)return;
    host.innerHTML=config.groups.map(groupHtml).join('')||'<p class="sub">No custom stat groups. Add one for set effects you gain or lose.</p>';
  }
  function renderSummary(){
    const host=q('#sc-swap-summary');if(!host)return;
    const p=preview, rows=[];
    if(p){
      for(const [slot,row] of Object.entries(p.slots))if(row.enabled){const e=config.slots[slot]||{};rows.push(`<li><span>${esc(slotLabel(slot))}: ${esc(itemLabel(e.current))} → ${esc(itemLabel(e.candidate))}</span><strong>${esc(describe(row.delta))}</strong></li>`);}
      for(const g of p.groups)if(g.enabled)rows.push(`<li><span>${esc(g.name||'Untitled group')}</span><strong>${esc(describe(g.delta))}</strong></li>`);
    }
    const hints=(p?.set_hint||[]).map(h=>`${h.set} pieces ${h.before} → ${h.after}`);
    const blockers=p?.blockers||[];
    host.innerHTML=`<h3>Swap total</h3>${rows.length?`<ul class="sc-swap-rows">${rows.join('')}</ul>`:'<p class="sub">Turn on a slot swap or a custom stat group.</p>'}
      ${config.groups.some(g=>g.enabled)?`<p class="sub">Custom groups total: ${esc(describe(p?.group_total))}</p>`:''}
      <p class="sc-swap-grand">Sent to MapleScouter: <strong>${p?esc(describe(p.delta)):'…'}</strong></p>
      ${hints.length?`<p class="sub">Set pieces (hint): ${esc(hints.join(' · '))}. Add a custom group for any set effect that changes.</p>`:''}
      ${(p?.warnings||[]).map(w=>`<p class="sc-warning">${esc(w)}</p>`).join('')}
      ${blockers.map(b=>`<p class="sc-loss" role="alert">${esc(b)}</p>`).join('')}
      <div class="sc-actions"><button class="btn btn-primary" id="sc-swap-run">Simulate</button></div>
      <p class="sub sc-swap-small">${esc(NOTE)}</p><p class="sub sc-note" id="sc-swap-message" role="status"></p>`;
    q('#sc-swap-run').disabled=busy||previewing||!p||blockers.length>0;
    q('#sc-swap-run').onclick=run;
    message();
  }
  function message(){
    const el=q('#sc-swap-message');if(!el)return;
    el.textContent=busy?'Calculating with MapleScouter…':runs().length&&pendingChanges()?'Changes not simulated yet.':'';
  }
  function renderOutput(){
    const host=q('#sc-swap-output');if(!host)return;
    const result=runs().find(r=>r.id===selected);
    if(!result){host.innerHTML='<div class="card empty">Set up a swap and press Simulate to see the final damage difference.</div>';return;}
    host.innerHTML=`<div class="sc-sim-score-grid">${['380','300'].map(d=>{const s=result.scores[d];return `<div class="card sc-sim-score"><span>Boss ${d} DEF</span><strong class="${s.fd_percent<0?'sc-loss':'sc-gain'}">${signed(s.fd_percent)}% FD</strong><div><span>HEXA</span><b>${fmt(s.before)} → ${fmt(s.after)}</b><small>${signed(s.after-s.before)}</small></div></div>`;}).join('')}</div>
      ${renderBossPanels(result.boss_cuts,filter,baseline.boss_cuts,'sc-swap')}`;
    const picker=q('#sc-swap-boss-filter');if(picker)picker.onchange=e=>{filter=e.target.value;renderOutput();q('#sc-swap-boss-filter')?.focus();};
    loadIcons();
  }
  function renderHistory(){
    const el=q('#sc-swap-history');if(!el)return;
    const records=runs().reverse();
    el.innerHTML=records.length?records.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(new Date(r.created).toLocaleTimeString())} · ${esc(r.enabled_slots.map(slotLabel).join(', ')||'Custom stats only')}</option>`).join(''):'<option>No item swaps yet</option>';
    el.disabled=busy||!records.length;
    const remove=q('#sc-swap-delete');if(remove){remove.hidden=!records.some(r=>r.id===selected);remove.disabled=busy;}
  }
  // Same confirmation as deleting a calculation; the editor keeps what is on screen.
  function confirmDelete(){
    const run=runs().find(r=>r.id===selected);if(!run||busy)return;
    const dialog=document.createElement('dialog');dialog.className='delete-character-dialog';
    dialog.setAttribute('aria-label','Delete saved item swap');
    dialog.innerHTML=`<h2>Delete this item swap?</h2><p>${esc(new Date(run.created).toLocaleString())} · ${esc(run.enabled_slots.map(slotLabel).join(', ')||'Custom stats only')}</p><p class="sub">Its result is removed. Your calculation, other swaps and the inputs on screen stay. This cannot be undone.</p><p class="warn" role="alert"></p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn delete-confirm">Delete item swap</button></footer>`;
    document.body.append(dialog);dialog.showModal();
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
    dialog.querySelector('.delete-confirm').onclick=async e=>{
      const button=e.currentTarget;button.disabled=true;button.textContent='Deleting…';
      try{await onDeleteRun(baseline.id,run.id);dialog.close();toast('Item swap deleted.');}
      catch(error){dialog.querySelector('[role="alert"]').textContent=error.message;button.disabled=false;button.textContent='Delete item swap';}
    };
  }
  function render(){
    if(!baseline){view.innerHTML='<div class="card empty">Calculate your character first, then use that saved result to compare item swaps.</div>';return;}
    if(!data){view.innerHTML=`<div class="card empty">${loading==='error'?'Could not load the item list.':'Loading the item list…'}</div>`;return;}
    if(data.blocked){view.innerHTML=`<div class="sc-section-title"><h2>Item swap</h2></div><div class="card sc-swap-blocked" role="note">${esc(data.blocked)}</div>`;return;}
    view.innerHTML=`<div class="sc-section-title"><h2>Item swap</h2></div>
      <div class="card sc-sim-form"><div class="sc-sim-toolbar"><label>Baseline calculation<select class="input" id="sc-swap-baseline">${[...profile.history].reverse().map(r=>`<option value="${esc(r.id)}" ${r.id===baseline.id?'selected':''}>${esc(new Date(r.created).toLocaleString())} · HEXA ${fmt(r.damage?.calculatedData?.boss380_hexaStat)}</option>`).join('')}</select></label><label>Saved swaps<select class="input" id="sc-swap-history" aria-label="Saved item swap"></select></label><button class="btn sc-delete-snapshot" id="sc-swap-delete" type="button">Delete swap</button><div class="sc-actions"><button class="btn btn-ghost" id="sc-swap-reset">Reset to scanned gear</button></div></div>
      <p class="sub sc-note">Pick a slot, choose the item you would wear instead and fill in its stars, flames and potential. Your current item is filled from the scan; check it, since the scan cannot see scrolls, bonus potential or add-ons. Turn on every slot you want to swap; Simulate sends them together as one change.</p></div>
      <div class="sc-swap-layout"><section class="card sc-swap-gear"><div id="sc-swap-grid"></div><p class="sub">⇄ marks slots that are swapped. Weapon and Android cannot be swapped.</p></section><section class="card sc-swap-editor" id="sc-swap-editor"></section></div>
      <div class="sc-section-title"><h2>Custom stat groups</h2><button class="btn" id="sc-swap-add-group">Add group</button></div><div id="sc-swap-groups"></div>
      <div class="card sc-swap-summary" id="sc-swap-summary"></div>
      <div class="sc-section-title"><h2>Comparison</h2></div><div id="sc-swap-output"></div>`;
    q('#sc-swap-baseline').onchange=e=>onBaseline(e.target.value);
    q('#sc-swap-history').onchange=e=>{selected=e.target.value;const run=runs().find(r=>r.id===selected);if(run)config=restoreConfig(run.config,data);render();schedulePreview(0);};
    q('#sc-swap-delete').onclick=confirmDelete;
    q('#sc-swap-reset').onclick=()=>{if(!confirm('Reset every slot to your scanned gear and remove all custom stat groups?'))return;config=freshConfig(data);render();schedulePreview(0);};
    q('#sc-swap-add-group').onclick=()=>{const id=globalThis.crypto?.randomUUID?.()||String(Date.now()+Math.random());config.groups.push({id,name:'',enabled:true,fields:{}});openGroups.add(id);changed(true);};
    renderGrid();renderEditor();renderGroups();renderHistory();renderSummary();renderOutput();setBusy(busy);
  }
  function changed(structural){
    if(structural){renderGrid();renderEditor();renderGroups();}
    previewing=true;renderSummary();schedulePreview();
  }
  function schedulePreview(delay=250){
    clearTimeout(timer);previewing=true;
    timer=setTimeout(async()=>{
      const mine=++serial, target=characterId();
      try{
        const result=await api.post(`/api/scouter/characters/${encodeURIComponent(target)}/swap/preview`,config);
        if(mine!==serial||target!==characterId())return;
        preview=result;previewing=false;
        renderSummary();
        const delta=q('#sc-swap-slot-delta');if(delta)delta.innerHTML=slotDeltaText();
        for(const which of ['current','candidate']){
          const total=q(`[data-total="${which}"]`), row=preview.slots?.[focus];
          if(total)total.textContent=row?.[which]?`From this item: ${describe(row[which])}`:'';
          const sf=q(`[data-parts="${which}:starforce"]`);if(sf)sf.textContent=row?.parts?.[which]?.starforce?describe(row.parts[which].starforce):'';
        }
      }catch(e){if(mine===serial){previewing=false;renderSummary();q('#sc-swap-message').textContent=e.message;}}
    },delay);
  }
  function setPath(target,path,value){
    const keys=path.split('.');let node=target;
    for(const k of keys.slice(0,-1))node=node[k]&&typeof node[k]==='object'?node[k]:(node[k]={});
    if(value===''||value===false)delete node[keys.at(-1)];else node[keys.at(-1)]=value;
  }
  async function run(){
    if(busy||!baseline)return;
    const invalid=[...view.querySelectorAll('input[type=number]')].find(i=>!i.checkValidity());
    if(invalid){invalid.closest('details')?.setAttribute('open','');invalid.reportValidity();return;}
    setBusy(true);
    try{await onRun(baseline.id,clone(config));}
    catch(e){setBusy(false);q('#sc-swap-message').textContent=e.message;toast(e.message,'danger');}
  }
  view.addEventListener('click',e=>{
    const slot=e.target.closest('[data-slot]');
    if(slot&&view.contains(slot)){if(slot.getAttribute('aria-disabled')==='true')return;focus=slot.dataset.slot;renderGrid();renderEditor();return;}
    if(e.target.closest('[data-copy-current]')){copyCurrent();return;}
    const action=e.target.closest('[data-gaction]');
    if(action){
      e.preventDefault();
      const id=action.closest('[data-group]').dataset.group, index=config.groups.findIndex(g=>g.id===id);
      if(action.dataset.gaction==='delete')config.groups.splice(index,1);
      else{const copy=clone(config.groups[index]);copy.id=globalThis.crypto?.randomUUID?.()||String(Date.now()+Math.random());copy.name=`${copy.name||'Untitled group'} (copy)`;config.groups.splice(index+1,0,copy);openGroups.add(copy.id);}
      changed(true);
    }
  });
  view.addEventListener('toggle',e=>{
    const other=e.target.dataset?.other, group=e.target.dataset?.group;
    if(other)(e.target.open?openOther.add(other):openOther.delete(other));
    if(group)(e.target.open?openGroups.add(group):openGroups.delete(group));
  },true);
  view.addEventListener('input',e=>{
    const t=e.target;
    if(t.dataset.path&&t.dataset.side&&t.type!=='checkbox'){setPath(config.slots[focus][t.dataset.side],t.dataset.path,t.value);changed(false);}
    else if(t.dataset.gfield||t.dataset.gpath==='name'){
      const g=config.groups.find(x=>x.id===t.closest('[data-group]').dataset.group);
      if(t.dataset.gfield)setPath(g,`fields.${t.dataset.gfield}`,t.value);else g.name=t.value;
      const card=t.closest('[data-group]');
      card.querySelector('summary strong').textContent=g.name||'Untitled group';
      card.querySelector('summary small').textContent=groupSummary(g);
      changed(false);
    }
  });
  view.addEventListener('change',e=>{
    const t=e.target, entry=config.slots[focus];
    if(t.id==='sc-swap-enabled'){entry.enabled=t.checked;changed(true);return;}
    if(t.dataset.item){
      // Keep the upgrades typed so far (handy to compare items with the same potential); add-ons
      // and stages belong to the old item. Boxes the new item cannot have are ignored.
      const which=t.dataset.item, old=entry[which]||{};
      entry[which]={item:t.value||null,...Object.fromEntries(['stars','flame','potential','other'].filter(k=>old[k]!==undefined).map(k=>[k,old[k]]))};
      if(which==='current'&&old.scanned_name)entry[which].scanned_name=old.scanned_name;
      if(which==='candidate')entry.enabled=!!t.value;
      changed(true);return;
    }
    if(t.dataset.variant){
      const side=entry[t.dataset.side], record=items()[side.item], v=variantOf(record,side);
      side.variant={stage:v.stage,version:v.version,[t.dataset.variant]:Number(t.value)};
      if(!record.variants.some(x=>x.stage===side.variant.stage&&x.version===side.variant.version))side.variant.version=record.variants.find(x=>x.stage===side.variant.stage).version;
      delete side.pick_variant;changed(true);return;
    }
    if(t.type==='checkbox'&&t.dataset.path){setPath(entry[t.dataset.side],t.dataset.path,t.dataset.path.startsWith('addons.')?(t.checked?1:''):t.checked);changed(true);return;}
    if(t.dataset.gpath==='enabled'){
      const g=config.groups.find(x=>x.id===t.closest('[data-group]').dataset.group);
      g.enabled=t.checked;
      changed(true);
    }
  });
  // For "same item, a few more stars" or "same item, better potential" comparisons.
  function copyCurrent(){
    const entry=config.slots[focus];
    entry.candidate=copiedCandidate(entry.current,entry.candidate);
    entry.enabled=!!entry.candidate.item;
    changed(true);
  }
  function setBusy(value){
    busy=value;
    if(q('#sc-swap-run'))q('#sc-swap-run').disabled=busy||previewing||!preview||(preview.blockers||[]).length>0;
    for(const el of view.querySelectorAll('#sc-swap-history,#sc-swap-baseline,#sc-swap-reset,#sc-swap-delete'))el.disabled=busy||(el.id==='sc-swap-history'&&!runs().length);
    message();
  }
  async function loadData(){
    const key=`${characterId()}:${profile.gear_fingerprint||''}`;
    if(dataKey===key||loading===key)return;
    loading=key;data=null;
    try{
      const fresh=await api.get(`/api/scouter/characters/${encodeURIComponent(characterId())}/swap/catalog`);
      if(loading!==key)return;
      data=fresh;dataKey=key;loading='';
      try{localStorage.removeItem(legacyDraftKey(characterId()));}catch{}
      config=restoreConfig(runs().at(-1)?.config,data);
      if(!config.slots[focus])focus=enabledSlots(config)[0]||(data.slots.includes('hat')?'hat':data.slots[0]);
      render();schedulePreview(0);
    }catch(e){if(loading===key){loading='error';render();toast(e.message,'danger');}}
  }
  function update(p,id){
    const characterChanged=profile?.character.id!==p.character.id;
    profile=p;baseline=p.history.find(r=>r.id===id);
    if(characterChanged){data=null;dataKey='';preview=null;}
    const nextKey=`${p.character.id}:${id}`, records=baseline?.swap_runs||[];
    // A new baseline shows its own latest run, so the editor must hold that run's inputs too.
    const switched=runKey!==nextKey;
    if(switched){runKey=nextKey;selected=records.at(-1)?.id||'';count=records.length;}
    else if(records.length!==count){selected=records.at(-1)?.id||'';count=records.length;}
    if(baseline&&!data){render();loadData();return;}
    if(baseline&&data&&dataKey!==`${p.character.id}:${p.gear_fingerprint||''}`){loadData();}
    if(switched&&baseline&&data){config=restoreConfig(records.at(-1)?.config,data);preview=null;render();schedulePreview(0);return;}
    render();
  }
  function dispose(){clearTimeout(timer);serial++;}
  return {update,setBusy,dispose};
}
