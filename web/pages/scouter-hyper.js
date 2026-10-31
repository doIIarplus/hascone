import { api } from '../api.js';
import { escapeHtml as esc, toast } from '../ui.js';
import { renderBossPanels } from './scouter-bosses.js';

const fmt = v => Number(v).toLocaleString(undefined,{maximumFractionDigits:3});
const signed = v => `${Number(v)>0?'+':''}${fmt(v)}`;
const clone = v => JSON.parse(JSON.stringify(v));
const LOCK = '<svg class="sc-hyper-lock" viewBox="0 0 16 16" width="11" height="11" aria-hidden="true"><path fill="currentColor" d="M4 7V5a4 4 0 0 1 8 0v2h1v8H3V7zm2 0h4V5a2 2 0 0 0-4 0z"/></svg>';
const ARCHER_NOTE = 'Vicious Shot turns overcapped crit into crit damage, which this optimizer doesn’t value. Keep Critical Rate (around level 7–8 is typical).';

// Exported for tests.
export function effectText(stat,level){return level?`+${fmt(stat.values[level-1])}${stat.unit}`:'';}

// A typed level box: a whole number within the stat's in-game maximum; never clamped.
export function parseLevel(raw,stat){
  const top=stat.values.length, text=String(raw??'').trim(), n=Number(text);
  if(text===''||!Number.isInteger(n)||n<0||n>top)return {error:`${stat.label} must be a whole number from 0 to ${top}`};
  return {level:n};
}

export function pointsUsed(levels,costs){
  return Object.values(levels).reduce((sum,level)=>sum+costs.slice(0,level).reduce((a,b)=>a+b,0),0);
}

// Saved settings, or a blank allocation with the class's default Keep.
export function initialSettings(data){
  const levels=Object.fromEntries(data.stats.map(s=>[s.key,0]));
  const saved=data.settings;
  if(!saved)return {levels,keep:[...data.keep],defense:'380',crit_rate:null};
  return {levels:{...levels,...saved.levels},keep:[...saved.keep],defense:saved.defense||'380',crit_rate:saved.crit_rate??null};
}

const canonical = s => JSON.stringify({levels:Object.keys(s.levels).sort().map(k=>[k,s.levels[k]]),keep:[...s.keep].sort(),defense:s.defense,crit_rate:s.crit_rate??null});
export function sameSettings(a,b){return canonical(a)===canonical(b);}

export function createHyper(view,{onRun,onBaseline,onDeleteRun,loadIcons}) {
  let profile, baseline, data=null, loading='', settings=null, typed={}, result=null, previewing=false;
  let selected='', count=0, busy=false, timer=0, serial=0, filter='relevant', runKey='', critText='', failure='';
  const q = s => view.querySelector(s);
  const characterId = () => profile.character.id;
  const endpoint = () => `/api/scouter/characters/${encodeURIComponent(characterId())}`;
  const runs = () => [...(baseline?.hyper_runs||[])];
  const stats = () => data.stats;
  const errors = () => stats().map(s=>parseLevel(typed[s.key],s).error).filter(Boolean).concat(critError()?[critError()]:[]);
  const kept = key => settings.keep.includes(key);
  function critError(){
    if(kept('crit_rate')||critText.trim()==='')return '';
    const n=Number(critText);
    return Number.isFinite(n)&&n>=0&&n<=1000?'':'In-combat Critical Rate must be a number from 0 to 1000';
  }
  const runLabel = r => {const d=r.settings.defense, s=r.scores?.[d];return `${new Date(r.created).toLocaleTimeString()} · ${s?`${signed(s.fd_percent)}% FD at ${d} DEF`:'Saved check'}`;};
  const pendingChanges = () => {const run=runs().find(r=>r.id===selected);return !run||!sameSettings(run.settings,settings);};

  function row(stat){
    const key=stat.key, level=typed[key];
    const parsed=parseLevel(level,stat), lock=kept(key);
    return `<tr data-row="${esc(key)}" class="${lock?'sc-hyper-kept':''}">
      <td><input type="checkbox" data-keep="${esc(key)}" ${lock?'checked':''} aria-label="Keep ${esc(stat.label)}"></td>
      <th scope="row">${esc(stat.label)}</th>
      <td><input class="input" type="number" min="0" max="${stat.values.length}" step="1" inputmode="numeric" data-level="${esc(key)}" value="${esc(level)}" aria-label="${esc(stat.label)} current level" aria-invalid="${!!parsed.error}" ${parsed.error?`title="${esc(parsed.error)}"`:''}></td>
      <td data-effect="current">${esc(parsed.error?'':effectText(stat,parsed.level))}</td>
      <td class="sc-hyper-sug" data-suggested></td><td class="sc-hyper-sug" data-effect="suggested"></td></tr>`;
  }
  function render(){
    if(!baseline){view.innerHTML='<div class="card empty">Calculate your character first, then use that saved result to optimize your hyper stats.</div>';return;}
    if(!data){view.innerHTML=`<div class="card empty">${loading==='error'?'Could not load hyper stats.':'Loading hyper stats…'}</div>`;return;}
    if(data.blocked){view.innerHTML=`<div class="sc-section-title"><h2>Hyper stats</h2></div><div class="card sc-swap-blocked" role="note">${esc(data.blocked)}</div>`;return;}
    view.innerHTML=`<div class="sc-section-title"><h2>Hyper stats</h2></div>
      <div class="card sc-sim-form"><div class="sc-sim-toolbar"><label>Baseline calculation<select class="input" id="sc-hyper-baseline">${[...profile.history].reverse().map(r=>`<option value="${esc(r.id)}" ${r.id===baseline.id?'selected':''}>${esc(new Date(r.created).toLocaleString())} · HEXA ${fmt(r.damage?.calculatedData?.boss380_hexaStat)}</option>`).join('')}</select></label><label>Saved checks<select class="input" id="sc-hyper-history" aria-label="Saved hyper stat check"></select></label><button class="btn sc-delete-snapshot" id="sc-hyper-delete" type="button">Delete check</button></div>
      <div class="sc-hyper-options"><fieldset class="sc-hyper-defense"><legend>Optimize for</legend><div>${['380','300'].map(d=>`<label><input type="radio" name="sc-hyper-defense" value="${d}" ${settings.defense===d?'checked':''}>${d} DEF</label>`).join('')}</div></fieldset>
      <label for="sc-hyper-crit">In-combat Critical Rate<span class="sc-hyper-crit"><input class="input" id="sc-hyper-crit" type="number" min="0" max="1000" step="any" value="${esc(critText)}"><span>%</span><button class="btn btn-ghost btn-sm" id="sc-hyper-crit-reset" type="button">Use scan</button></span><small id="sc-hyper-crit-note"></small></label></div>
      <p class="sub sc-note">Enter the levels of the hyper stat preset you scanned with, in the same order as the in-game window. Kept stats stay at their level. Critical Rate, when not kept, is set to the lowest level that keeps you at 100%.</p>
      ${data.archer?`<p class="sc-warning" role="note">${esc(ARCHER_NOTE)}</p>`:''}</div>
      <div class="card sc-hyper-card"><table class="sc-hyper-table"><thead><tr><th scope="col">Keep</th><th scope="col">Stat</th><th scope="col">Current</th><th scope="col">Effect</th><th scope="col" class="sc-hyper-sug">Suggested</th><th scope="col" class="sc-hyper-sug">Effect</th></tr></thead>
        <tbody>${stats().map(row).join('')}</tbody>
        <tfoot><tr><td></td><th scope="row">Points</th><td colspan="2" id="sc-hyper-points-current"></td><td colspan="2" class="sc-hyper-sug" id="sc-hyper-points-suggested"></td></tr></tfoot></table></div>
      <div class="card sc-swap-summary" id="sc-hyper-summary"></div>
      <div class="sc-section-title"><h2>MapleScouter check</h2></div><div id="sc-hyper-output"></div>`;
    q('#sc-hyper-baseline').onchange=e=>onBaseline(e.target.value);
    q('#sc-hyper-history').onchange=e=>{selected=e.target.value;const run=runs().find(r=>r.id===selected);if(run)restore(run.settings);};
    q('#sc-hyper-delete').onclick=confirmDelete;
    q('#sc-hyper-crit-reset').onclick=()=>{critText='';q('#sc-hyper-crit').value='';changed();};
    renderHistory();renderSuggestion();renderOutput();setBusy(busy);
  }
  function restore(saved){
    settings={...clone(saved),crit_rate:saved.crit_rate??null};
    typed=Object.fromEntries(Object.entries(settings.levels).map(([k,v])=>[k,String(v)]));
    critText=settings.crit_rate==null?'':String(settings.crit_rate);
    result=null;render();schedule(0);
  }
  // Fill the Suggested columns, points and summary from the latest local result.
  function renderSuggestion(){
    if(!q('#sc-hyper-summary'))return;
    const invalid=errors(), costs=data.costs, current=invalid.length?null:Object.fromEntries(stats().map(s=>[s.key,Number(typed[s.key])]));
    const shown=!invalid.length&&result&&!result.blockers.length?result:null;
    for(const stat of stats()){
      const tr=q(`[data-row="${stat.key}"]`), level=shown?.suggested.levels[stat.key];
      const from=Number(typed[stat.key]), moved=shown&&level!==from;
      tr.classList.toggle('sc-hyper-changed',!!moved);
      tr.querySelector('[data-suggested]').innerHTML=level==null?'<span class="sc-hyper-none">—</span>':`${kept(stat.key)?LOCK:''}<span class="${moved?level>from?'sc-gain':'sc-loss':''}">${level}</span>`;
      tr.querySelector('[data-effect="suggested"]').textContent=level==null?'':effectText(stat,level);
    }
    const budget=result?.budget;
    const of=used=>`${used.toLocaleString()}${budget!=null?` / ${budget.toLocaleString()}`:''}`;
    q('#sc-hyper-points-current').textContent=current?of(pointsUsed(current,costs)):'—';
    q('#sc-hyper-points-suggested').textContent=shown?of(shown.suggested.cost):'—';
    const scanned=result?.scanned_crit_rate;
    q('#sc-hyper-crit').placeholder=scanned!=null?fmt(scanned):'';
    q('#sc-hyper-crit').disabled=busy||kept('crit_rate');
    q('#sc-hyper-crit').setAttribute('aria-invalid',String(!!critError()));
    q('#sc-hyper-crit-reset').hidden=critText.trim()==='';
    q('#sc-hyper-crit-note').textContent=kept('crit_rate')?'Not used while Critical Rate is kept.':critText.trim()===''?(scanned!=null?`From your scan: ${fmt(scanned)}%`:'From your scan'):'Entered by you';
    const d=settings.defense, other=d==='380'?'300':'380';
    let body;
    if(invalid.length)body=`<p class="sc-loss" role="alert">Fix the highlighted boxes: ${esc(invalid[0])}.</p>`;
    else if(failure&&!previewing)body=`<p class="sc-loss" role="alert">${esc(failure)}</p>`;
    else if(!result)body=`<p class="sub">${previewing?'Finding the best allocation…':''}</p>`;
    else if(result.blockers.length)body=result.blockers.map(b=>`<p class="sc-loss" role="alert">${esc(b)}</p>`).join('');
    else if(result.already_optimized)body=`<p class="sc-swap-grand"><strong>Already optimized</strong> · no allocation beats your current one at ${d} DEF.</p>`;
    else body=`<p class="sc-swap-grand">Local estimate: <strong class="sc-gain">${signed(result.fd_percent[d])}% FD</strong> at ${d} DEF <span class="sub">· ${signed(result.fd_percent[other])}% at ${other} DEF</span></p>
      <p class="sub">From your saved calculation’s stat efficiencies. Verify runs one MapleScouter calculation with the suggested levels.</p>`;
    const verify=!invalid.length&&result&&!result.blockers.length&&!result.already_optimized;
    q('#sc-hyper-summary').innerHTML=`<h3>Suggestion</h3>${body}${(!invalid.length&&result?.warnings||[]).map(w=>`<p class="sc-warning">${esc(w)}</p>`).join('')}
      <div class="sc-actions">${verify?'<button class="btn btn-primary" id="sc-hyper-run">Verify with MapleScouter</button>':''}<span class="sub" id="sc-hyper-message" role="status" aria-live="polite"></span></div>`;
    q('#sc-hyper-run')?.addEventListener('click',run);
    setBusy(busy);
  }
  function message(){
    const el=q('#sc-hyper-message');if(!el)return;
    el.textContent=busy?'Checking with MapleScouter…':runs().length&&pendingChanges()?'Changes not verified yet.':'';
  }
  function renderOutput(){
    const host=q('#sc-hyper-output');if(!host)return;
    const run=runs().find(r=>r.id===selected);
    if(!run){host.innerHTML='<div class="card empty">Verify a suggestion to see MapleScouter’s final damage difference and boss estimates.</div>';return;}
    const d=run.settings.defense, missed=!(run.scores?.[d]?.fd_percent>0);
    host.innerHTML=`${missed?`<p class="sc-warning" role="note">Already optimized · the local suggestion didn’t verify at ${d} DEF.</p>`:''}
      <div class="sc-sim-score-grid">${['380','300'].map(def=>{const s=run.scores[def];return `<div class="card sc-sim-score"><span>Boss ${def} DEF</span><strong class="${s.fd_percent<0?'sc-loss':'sc-gain'}">${signed(s.fd_percent)}% FD</strong><div><span>HEXA</span><b>${fmt(s.before)} → ${fmt(s.after)}</b><small>${signed(s.after-s.before)}</small></div></div>`;}).join('')}</div>
      ${renderBossPanels(run.boss_cuts,filter,baseline.boss_cuts,'sc-hyper')}`;
    const picker=q('#sc-hyper-boss-filter');if(picker)picker.onchange=e=>{filter=e.target.value;renderOutput();q('#sc-hyper-boss-filter')?.focus();};
    loadIcons();
  }
  function renderHistory(){
    const el=q('#sc-hyper-history');if(!el)return;
    const records=runs().reverse();
    el.innerHTML=records.length?records.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(runLabel(r))}</option>`).join(''):'<option>No checks yet</option>';
    el.disabled=busy||!records.length;
    const remove=q('#sc-hyper-delete');if(remove){remove.hidden=!records.some(r=>r.id===selected);remove.disabled=busy;}
  }
  function confirmDelete(){
    const run=runs().find(r=>r.id===selected);if(!run||busy)return;
    const dialog=document.createElement('dialog');dialog.className='delete-character-dialog';
    dialog.setAttribute('aria-label','Delete saved hyper stat check');
    dialog.innerHTML=`<h2>Delete this hyper stat check?</h2><p>${esc(new Date(run.created).toLocaleString())}</p><p class="sub">Its result is removed. Your calculation, other checks and the levels on screen stay. This cannot be undone.</p><p class="warn" role="alert"></p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn delete-confirm">Delete check</button></footer>`;
    document.body.append(dialog);dialog.showModal();
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
    dialog.querySelector('.delete-confirm').onclick=async e=>{
      const button=e.currentTarget;button.disabled=true;button.textContent='Deleting…';
      try{await onDeleteRun(baseline.id,run.id);dialog.close();toast('Hyper stat check deleted.');}
      catch(error){dialog.querySelector('[role="alert"]').textContent=error.message;button.disabled=false;button.textContent='Delete check';}
    };
  }
  // Valid edits become the settings (saved per character by the next suggestion request).
  function changed(){
    if(!errors().length){
      settings.levels=Object.fromEntries(stats().map(s=>[s.key,Number(typed[s.key])]));
      settings.crit_rate=critText.trim()===''?null:Number(critText);
      schedule();
    }else{clearTimeout(timer);serial++;previewing=false;}
    renderSuggestion();
  }
  function schedule(delay=200){
    clearTimeout(timer);previewing=true;
    timer=setTimeout(async()=>{
      if(!baseline){previewing=false;return;}
      const mine=++serial, target=characterId(), base=baseline.id;
      try{
        const fresh=await api.post(`${endpoint()}/hyper/optimize`,{result_id:base,settings:clone(settings)});
        if(mine!==serial||target!==characterId()||base!==baseline?.id)return;
        result=fresh;failure='';previewing=false;renderSuggestion();
      }catch(e){if(mine===serial){previewing=false;result=null;failure=e.message;renderSuggestion();}}
    },delay);
  }
  async function run(){
    if(busy||!baseline||errors().length)return;
    setBusy(true);
    try{await onRun(baseline.id,clone(settings));}
    catch(e){setBusy(false);q('#sc-hyper-message').textContent=e.message;toast(e.message,'danger');}
  }
  view.addEventListener('input',e=>{
    const t=e.target;
    if(t.dataset.level){
      typed[t.dataset.level]=t.value;
      const stat=stats().find(s=>s.key===t.dataset.level), parsed=parseLevel(t.value,stat);
      t.setAttribute('aria-invalid',String(!!parsed.error));
      if(parsed.error)t.title=parsed.error;else t.removeAttribute('title');
      t.closest('tr').querySelector('[data-effect="current"]').textContent=parsed.error?'':effectText(stat,parsed.level);
      changed();
    }else if(t.id==='sc-hyper-crit'){critText=t.value;changed();}
  });
  view.addEventListener('change',e=>{
    const t=e.target;
    if(t.dataset.keep){
      const key=t.dataset.keep;
      settings.keep=t.checked?[...new Set([...settings.keep,key])]:settings.keep.filter(k=>k!==key);
      t.closest('tr').classList.toggle('sc-hyper-kept',t.checked);
      changed();
    }else if(t.name==='sc-hyper-defense'){settings.defense=t.value;changed();}
  });
  function setBusy(value){
    busy=value;
    if(q('#sc-hyper-run'))q('#sc-hyper-run').disabled=busy||previewing;
    for(const el of view.querySelectorAll('#sc-hyper-history,#sc-hyper-baseline,#sc-hyper-delete'))el.disabled=busy||(el.id==='sc-hyper-history'&&!runs().length);
    message();
  }
  async function loadData(){
    const key=characterId();
    if(loading===key)return;
    loading=key;data=null;
    try{
      const fresh=await api.get(`${endpoint()}/hyper`);
      if(loading!==key)return;
      data=fresh;loading='';
      const start=initialSettings(data);
      restore(start);
    }catch(e){if(loading===key){loading='error';render();toast(e.message,'danger');}}
  }
  function update(p,id){
    const characterChanged=profile?.character.id!==p.character.id;
    profile=p;baseline=p.history.find(r=>r.id===id);
    if(!baseline){clearTimeout(timer);serial++;previewing=false;}
    if(characterChanged){data=null;result=null;loading='';}
    const nextKey=`${p.character.id}:${id}`, records=baseline?.hyper_runs||[];
    const switched=runKey!==nextKey;
    if(switched){runKey=nextKey;selected=records.at(-1)?.id||'';count=records.length;}
    else if(records.length!==count){selected=records.at(-1)?.id||'';count=records.length;}
    if(baseline&&!data){render();loadData();return;}
    render();
    // Each calculation has its own budget and efficiencies.
    if(switched&&baseline&&data){result=null;renderSuggestion();if(!errors().length)schedule(0);}
  }
  function dispose(){clearTimeout(timer);serial++;}
  return {update,setBusy,dispose};
}
