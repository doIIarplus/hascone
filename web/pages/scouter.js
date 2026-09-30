import {downloadScouterPreset} from '../scouter_export.js';
import {revealSection} from '../sections.js';
import {renderEfficiencies} from './scouter-efficiencies.js';
import { api } from '../api.js';
import { escapeHtml as esc, toast } from '../ui.js';
import { efficiencySummary } from './scouter-efficiency.js';
import { createSuggestions } from './scouter-suggestions.js';
import { createSimulator } from './scouter-simulator.js';
import { renderBossPanels } from './scouter-bosses.js';
import { buffPreset, exclusiveBuffs, guildSkills } from './scouter-fields.js';
import { renderInputs, updateDisplayStats, attachInputTooltips } from './scouter-inputs.js';

const PREP = 'Prepare your character using MapleScouter’s class instructions. Use a bossing preset with 100% critical rate for HEXA calculation. Let temporary buffs settle. The guided scanner asks you to open each panel and hover relevant values yourself. Use a 2560 × 1440 game client with Default Ratio (Filter Applied), or 1920 × 1080 or 1366 × 768. Review buffs, rings and Legion manually before calculating.';
const human = s => s.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
const fmt = v => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
const flat = (obj, p = '') => Object.fromEntries(Object.entries(obj).flatMap(([k,v]) => {
  const path = p ? `${p}.${k}` : k;
  return v !== null && typeof v === 'object' ? Object.entries(flat(v,path)) : [[path,v]];
}));
const EFF = {dmgeff1:'Damage +1%', atkeff1:'Attack +1', atkPereff1:'Attack +1%', cridmgeff1:'Critical damage +1%',
  igreff1_380:'IED +1% · 380 DEF', mainStateff1:'Main stat +1', mainStatPereff1:'Main stat +1%',
  subStateff1:'Secondary stat +1', subStatPereff1:'Secondary stat +1%', allStatEff:'All stat +1%'};

export async function mountScouter(view) {
  view.classList.add('scouter');
  let profile, draft = {}, dirty = false, disposed = false, pending = false, selectedResult = '', polling = false;
  let activeTab = ['results','simulator','suggestions','efficiencies'].includes(localStorage.getItem('hascone.scouter.tab')) ? localStorage.getItem('hascone.scouter.tab') : 'inputs';
  let lastSimulation=false, lastSuggestions=false, pollGeneration=0;
  let bossFilter = 'relevant';
  let lastCalculation = false, portrait = null;
  const urls = new Map();
  let saveTimer=null, saveFlight=null, editSerial=0;
  const edits=new Map();
  const cacheKey = target => `hascone.scouter.pending.${target}`;
  function cacheDraft() {
    if(dirty) localStorage.setItem(cacheKey(profile.character.id),JSON.stringify(draft));
    else localStorage.removeItem(cacheKey(profile.character.id));
  }
  view.beforeLeave=async()=>{
    try { await save();return true; }
    catch(e) { status(`Could not save: ${e.message}`);return false; }
  };
  const all = await api.get('/api/characters');
  const selected = localStorage.getItem('hascone.scouter.character') || all.default_character;
  const characters = all.profiles || [];
  view.innerHTML = `<div class="page-head"><h1>Scouter</h1><div class="sc-scope"><span>GMS</span><span>Reboot</span><span class="sc-liberated">Liberated</span></div></div>
    <section class="card sc-profile"><div class="card-body sc-toolbar"><img id="sc-portrait" alt="" hidden>
      <div class="sc-identity"><strong>${esc(characters.find(c=>c.id===selected)?.name||'')}</strong><select class="input" id="sc-character" hidden>${characters.map(c => `<option value="${esc(c.id)}" ${c.id===selected?'selected':''}>${esc(c.name)} · ${esc(human(c.class))}</option>`).join('')}</select><div class="sub" id="sc-scan-date">No scan yet</div></div>
      <div class="sc-actions"><button class="btn btn-primary" id="sc-scan" title="Use your bossing preset with 100% critical rate. Follow the panel and hover prompts, then review buffs, rings and Legion before calculating.">Scan stats from game</button><button class="btn" id="sc-preset-export">Export to MapleScouter</button><button class="btn btn-ghost sc-help" id="sc-prep" title="${esc(PREP)}" aria-label="How to prepare for scanning">?</button><button class="btn btn-danger" id="sc-stop">Stop</button></div>
    </div><div id="sc-progress" role="status" aria-live="polite"></div></section>
    <div id="sc-problem" class="sc-problem" role="alert"></div><nav class="fl-subtabs sc-tabs" role="tablist" aria-label="Scouter view"><button class="btn" id="sc-tab-inputs" role="tab" aria-controls="sc-panel-inputs" data-sc-tab="inputs">Inputs</button><button class="btn" id="sc-tab-results" role="tab" aria-controls="sc-panel-results" data-sc-tab="results">Results</button><button class="btn" id="sc-tab-simulator" role="tab" aria-controls="sc-panel-simulator" data-sc-tab="simulator">Simulator</button><button class="btn" id="sc-tab-suggestions" role="tab" aria-controls="sc-panel-suggestions" data-sc-tab="suggestions">Compare upgrades</button><button class="btn" id="sc-tab-efficiencies" role="tab" aria-controls="sc-panel-efficiencies" data-sc-tab="efficiencies">Efficiencies</button></nav><div class="sc-layout"><section class="sc-inputs" id="sc-panel-inputs" role="tabpanel" aria-labelledby="sc-tab-inputs"><div class="sc-section-title"><h2>Inputs</h2><span class="sub" id="sc-missing"></span><span class="sub sc-save-status" id="sc-save-status" role="status" aria-live="polite">Saved</span></div>
      <div id="sc-missing-links" class="sc-missing-links"></div><div id="sc-fields"></div></section><section class="sc-results" id="sc-panel-results" role="tabpanel" aria-labelledby="sc-tab-results"><div class="sc-section-title"><h2>Results</h2></div>
      <div class="sub sc-note">Scores come directly from MapleScouter. Calculations save a snapshot of these inputs.</div>
      <div class="sc-snapshot-toolbar"><select class="input" id="sc-history" aria-label="Saved calculation"></select><form id="sc-name-form"><input class="input" id="sc-snapshot-name" aria-label="Snapshot name" maxlength="80" placeholder="Snapshot name (optional)"><button class="btn" type="submit">Save name</button></form><button class="btn sc-delete-snapshot" id="sc-delete-snapshot" type="button">Delete</button></div><div id="sc-output"></div></section><section id="sc-panel-simulator" role="tabpanel" aria-labelledby="sc-tab-simulator"></section><section id="sc-panel-suggestions" role="tabpanel" aria-labelledby="sc-tab-suggestions"></section><section id="sc-panel-efficiencies" role="tabpanel" aria-labelledby="sc-tab-efficiencies"></section></div>
    <div class="page-footer" role="region" aria-label="Calculate"><span class="sub" id="sc-footer-status"></span><button class="btn btn-primary" id="sc-calculate">Calculate</button></div>`;
  const q = s => view.querySelector(s);
  const disposeTooltips=attachInputTooltips(q('#sc-fields'));
  function showTab(name) {
    activeTab = name;
    localStorage.setItem('hascone.scouter.tab',name);
    for (const tab of ['inputs','results','simulator','suggestions','efficiencies']) {
      q(`#sc-panel-${tab}`).hidden = tab !== name;
      q(`#sc-tab-${tab}`).setAttribute('aria-selected',String(tab===name));
      q(`#sc-tab-${tab}`).tabIndex = tab === name ? 0 : -1;
    }
    loadIcons();
  }
  q('.sc-tabs').onclick = e => { const tab = e.target.closest('[data-sc-tab]'); if(tab) showTab(tab.dataset.scTab); };
  q('.sc-tabs').onkeydown = e => {
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
    e.preventDefault();const tabs=['inputs','results','simulator','suggestions','efficiencies'];showTab(e.key==='Home'?tabs[0]:e.key==='End'?tabs.at(-1):tabs[(tabs.indexOf(activeTab)+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length]);
    q(`#sc-tab-${activeTab}`).focus({preventScroll:true});
  };
  const id = () => q('#sc-character').value;
  const endpoint = () => `/api/scouter/characters/${encodeURIComponent(id())}`;
  const status = message => {
    if(disposed)return;
    q('#sc-progress').textContent=message;
    const text=String(message||'');
    const target=/critical/i.test(text)?'stat.critical':/HEXA.*(invalid|input)|invalid.*HEXA/i.test(text)?'hexa.hexaStat':null;
    const error=/failed|error|invalid|rejected|impossible|could not|unavailable|requires.*100|100% critical|timed out|timeout|connection|HTTP [45]/i.test(text);
    const network=/HTTP|network|connect|timed out|API|client configuration/i.test(text);
    q('#sc-problem').innerHTML=error?`<strong>Check this before retrying</strong><p>${esc(text)}</p>${network?'<p>Check your connection and whether MapleScouter opens in your browser. Retry Calculate after the service is available.</p><a class="btn" href="https://maplescouter.com/en/input" target="_blank" rel="noopener noreferrer">Open MapleScouter</a>':''}<button class="btn" id="sc-fix-input">${target?'Go to '+esc(target==='stat.critical'?'Critical Rate':'HEXA inputs'):'Review inputs and highlighted fields'}</button>`:'';
    q('#sc-fix-input')?.addEventListener('click',()=>{showTab('inputs');const field=target?(q(`[data-path="${target}"]`)||(target.startsWith('hexa.')?q('[data-path^="hexa."]'):null)):q('[aria-invalid="true"]');revealSection(field);field?.scrollIntoView({block:'center'});field?.focus({preventScroll:true});});
  };
  const simulator=createSimulator(q('#sc-panel-simulator'),{
    loadIcons,
    onBaseline:resultId=>{selectedResult=resultId;renderResults();},
    onRun:async(resultId,changes)=>{
      const state=await api.post(`${endpoint()}/simulate`,{result_id:resultId,changes});
      lastSimulation=state.active;status(state.message);
    },
  });

  const suggestions=createSuggestions(q('#sc-panel-suggestions'),{onGenerate:()=>action(async()=>{
    await save();const state=await api.post(`${endpoint()}/suggestions`,{});
    lastSuggestions=state.active;suggestions.setBusy(state.active);status(state.message);
    if(!state.active)await load();
  }),onOptions:async options=>{
    await action(async()=>{await save();await api.post(`${endpoint()}/starforce-options`,options);await load();});
  }});

  const currentValues = () => ({...flat(profile.values), ...draft});
  const asset = name => `<img data-icon="${esc(name)}" alt="" width="28" height="28" loading="lazy">`;
  function renderFields() {
    q('#sc-fields').innerHTML = renderInputs(profile,currentValues(),draft);
    updateDisplayStats(q('#sc-fields'),currentValues(),profile.class_info);
    loadIcons(); refreshMissing();
  }
  function missingCount() {
    const values=currentValues();
    return [...q('#sc-fields').querySelectorAll('[data-path]')].filter(el=>el.value===''||!el.validity.valid).length
      + [...q('#sc-fields').querySelectorAll('[data-cycle]')].filter(el=>values[el.dataset.cycle]==null).length;
  }
  function refreshMissing() {
    q('#sc-fields').querySelectorAll('[data-path]').forEach(el=>{
      const invalid=el.type==='number'&&(el.value===''||!el.validity.valid);
      el.closest('.sc-field')?.classList.toggle('sc-missing',invalid);
      if(el.type==='number')el.setAttribute('aria-invalid',String(invalid));
    });
    const count = missingCount();
    const missing=[...q('#sc-fields').querySelectorAll('[aria-invalid="true"]')];
    q('#sc-missing-links').innerHTML=missing.slice(0,8).map(el=>`<button class="btn btn-sm" data-jump="${esc(el.dataset.path)}">${esc(el.getAttribute('aria-label')||human(el.dataset.path))}</button>`).join('');
    q('#sc-missing-links').querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>{const el=q(`[data-path="${b.dataset.jump}"]`);revealSection(el);el?.scrollIntoView({block:'center'});el?.focus({preventScroll:true});});
    q('#sc-missing').textContent = count ? `${count} missing or invalid` : 'Ready to calculate';
    q('#sc-footer-status').textContent = q('#sc-missing').textContent;
    q('#sc-save-status').textContent = dirty ? 'Saving…' : 'Saved';
    q('#sc-calculate').disabled = pending || count>0;
  }
  async function loadIcons() {
    for (const img of view.querySelectorAll('img[data-icon]')) {
      const name = img.dataset.icon;
      try {
        if (!urls.has(name)) urls.set(name, await api.blobUrl(`/api/scouter/icons/${encodeURIComponent(name)}`));
        if (disposed) { URL.revokeObjectURL(urls.get(name)); continue; }
        img.src = urls.get(name);
      } catch { img.hidden = true; }
    }
  }
  function renderResults() {
    const history = [...profile.history].reverse();
    q('#sc-history').innerHTML = history.length ? history.map(r=>`<option value="${esc(r.id)}">${esc(new Date(r.created).toLocaleString())}${r.name?" · "+esc(r.name):""}</option>`).join('') : '<option>No calculations yet</option>';
    if (!history.some(r=>r.id===selectedResult)) selectedResult = history[0]?.id || '';
    q('#sc-history').value = selectedResult;
    simulator.update(profile,selectedResult);
    suggestions.update(profile,dirty);
    const result = history.find(r=>r.id===selectedResult);
    q('#sc-name-form').hidden=!result;
    q('#sc-delete-snapshot').hidden=!result;
    q('#sc-snapshot-name').value=result?.name||'';
    renderEfficiencies(q('#sc-panel-efficiencies'),result,dirty||result?.fingerprint!==profile.fingerprint);
    q('#sc-eff-preset')?.addEventListener('click',exportPreset);
    q('#sc-eff-results')?.addEventListener('click',()=>showTab('results'));
    if (!result) { q('#sc-output').innerHTML = '<div class="card empty">Scan your character, review the inputs, then calculate your HEXA score and upgrade order.</div>'; return; }
    const d = result.damage?.calculatedData || {};
    const stale = dirty || result.fingerprint !== profile.fingerprint;
    q('#sc-output').innerHTML = `${stale?'<p class="sc-warning">Saved result · inputs have changed. Calculate again to refresh.</p>':''}
      <div class="sc-score-grid">${[['HEXA score · 380 DEF',d.boss380_hexaStat],['HEXA score · 300 DEF',d.boss300_hexaStat],['Stat score · 380 DEF',d.boss380_stat]].map(([l,v])=>`<div class="card sc-score"><span>${esc(l)}</span><strong>${fmt(v)}</strong></div>`).join('')}</div>
      ${efficiencySummary(d.specEfficiency)}
      ${renderBossPanels(result.boss_cuts,bossFilter)}
      <details class="card sc-group"><summary>Stat efficiencies</summary><div class="sc-eff">${Object.entries(EFF).filter(([k])=>d.specEfficiency?.[k]!==undefined).map(([k,l])=>`<div><span>${esc(l)}</span><strong>${Number(d.specEfficiency[k]*100).toLocaleString(undefined,{maximumFractionDigits:3})}% FD</strong></div>`).join('')}</div></details>
      <button class="btn" id="sc-open-hexa">View HEXA upgrade order</button>
      <button class="btn btn-ghost btn-sm" id="sc-export">Export saved inputs & result</button>`;
    q('#sc-open-hexa').onclick=()=>window.dispatchEvent(new CustomEvent('open-hexa'));
    q('#sc-quick-fd-run').onclick=()=>{const input=q('#sc-quick-fd-value');if(!input.checkValidity()){input.reportValidity();return;}showTab('simulator');simulator.compareFD(input.value||'0');};
    if(q('#sc-boss-filter')) q('#sc-boss-filter').onchange = e => { bossFilter=e.target.value; renderResults();q('#sc-boss-filter')?.focus({preventScroll:true}); };
    q('#sc-export').onclick = async () => {
      try {
        const record = await api.get(`${endpoint()}/history/${encodeURIComponent(selectedResult)}`);
        const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
        const a=document.createElement('a');a.href=url;a.download=`scouter-${id()}-${record.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      } catch(e) { toast(e.message,'danger'); }
    };
    loadIcons();
  }
  async function exportPreset(){
    const identifier=id();
    await action(async()=>{
      await save();
      const preset=await api.get(`/api/characters/${encodeURIComponent(identifier)}/scouter-preset`);
      if(!disposed)downloadScouterPreset(preset);
    });
  }
  async function load() {
    const target = id();
    const data = await api.get(endpoint());
    if (disposed || id()!==target) return;
    if(profile?.character.id===target && data.revision<profile.revision)return;
    profile=data;
    try { draft=JSON.parse(localStorage.getItem(cacheKey(target))||'{}'); } catch { draft={}; }
    dirty=Object.keys(draft).length>0;
    for(const path of Object.keys(draft)) edits.set(path,++editSerial);
    q('#sc-scan-date').textContent=data.scan?`Scanned ${new Date(data.scan.finished).toLocaleString()}`:'No scan yet';
    renderFields();renderResults();
    if(dirty) scheduleSave();
    status(data.scan?.errors?.join(' · ')||'Hover the ? for preparation instructions.');
    if (portrait) URL.revokeObjectURL(portrait);
    portrait=null;q('#sc-portrait').hidden=true;
    try {
      const url = await api.blobUrl(`/api/characters/${encodeURIComponent(target)}/portrait`);
      if (disposed || id()!==target) { URL.revokeObjectURL(url);return; }
      portrait=url;q('#sc-portrait').src=url;q('#sc-portrait').hidden=false;
    } catch { /* Portrait failure must never block stat entry. */ }
  }
  function scheduleSave(delay=350) {
    clearTimeout(saveTimer);
    saveTimer=setTimeout(()=>save().catch(e=>{
      if(disposed)return;
      q('#sc-save-status').textContent='Not saved · '+e.message;
      // Keep edits locally across navigation/reload and retry temporary failures.
      if(!e.status || e.status>=500) scheduleSave(2000);
    }),delay);
  }
  async function save() {
    clearTimeout(saveTimer);
    if(saveFlight) { await saveFlight; if(dirty)return save(); return; }
    if(!dirty)return;
    const target=profile.character.id;
    const url=`/api/scouter/characters/${encodeURIComponent(target)}`;
    saveFlight=(async()=>{
      while(dirty) {
        const changes={...draft}, versions=new Map(edits);
        let result;
        try { result=await api.post(url,{revision:profile.revision,changes}); }
        catch(e) {
          if(e.status!==409)throw e;
          // Rebase only changed fields, never send a stale copy of the whole form.
          const fresh=await api.get(url);
          result=await api.post(url,{revision:fresh.revision,changes});
        }
        profile=result;
        for(const path of Object.keys(changes)) if(edits.get(path)===versions.get(path)) {
          delete draft[path];edits.delete(path);
        }
        dirty=Object.keys(draft).length>0;cacheDraft();
        if(!disposed) {
          refreshMissing();renderResults();
          // Keep the focused numeric control and in-progress typing intact.
          const savedValues=flat(result.values);
          for(const el of q('#sc-fields').querySelectorAll('[data-path]')) if(!Object.hasOwn(draft,el.dataset.path)) {
            if(!el.closest('[data-sc-tooltip]'))el.title=(el.getAttribute('aria-label')||'')+' · Saved';
            if(el!==document.activeElement) {
              if(el.type==='checkbox')el.checked=!!savedValues[el.dataset.path];
              else el.value=savedValues[el.dataset.path]??'';
            }
          }
          updateDisplayStats(q('#sc-fields'),currentValues(),profile.class_info);
        }
      }
    })();
    try { await saveFlight; } finally { saveFlight=null; }
  }
  async function action(fn) {
    if (pending) return;
    pollGeneration++;
    pending=true;q('#sc-character').disabled=true;q('#sc-scan').disabled=true;q('#sc-fields').inert=true;
    refreshMissing();
    try { await fn(); } catch(e) { status(e.message);toast(e.message,'danger'); }
    finally { if (!disposed) {pending=false;q('#sc-character').disabled=false;q('#sc-scan').disabled=false;q('#sc-fields').inert=false;refreshMissing();} }
  }
  function markEdited() {
    dirty=Object.keys(draft).length>0;
    for(const path of Object.keys(draft)) edits.set(path,++editSerial);
    cacheDraft();refreshMissing();scheduleSave();suggestions.update(profile,dirty);
    updateDisplayStats(q('#sc-fields'),currentValues(),profile.class_info);
    if (profile.history.length && !q('#sc-output .sc-warning')) q('#sc-output').insertAdjacentHTML('afterbegin','<p class="sc-warning">Inputs changed. Calculate again to refresh.</p>');
  }
  const numericField = el => el.matches?.('input[type="number"][data-path]');
  q('#sc-fields').addEventListener('focusin',e=>{
    const el=e.target;if(!numericField(el))return;
    el.dataset.numberEditing=el.value!==''?'true':'false';
    if(el.value!==''&&Number(el.value)===0)el.value='';
    else el.select();
  });
  q('#sc-fields').addEventListener('focusout',e=>{
    const el=e.target;if(!numericField(el))return;
    if(el.value===''&&el.dataset.numberEditing==='true'&&!el.validity.badInput){
      el.value='0';
      if(String(currentValues()[el.dataset.path])!=='0')el.dispatchEvent(new Event('input',{bubbles:true}));
    }
    delete el.dataset.numberEditing;
  });
  q('#sc-fields').addEventListener('input',e=>{
    if(e.target.id==='sc-all-buffs') {
      const enabled=e.target.checked;
      for(const [path,value] of Object.entries(currentValues())) {
        if(path.startsWith('doping.')) draft[path]=typeof value==='boolean'?false:'0';
      }
      Object.assign(draft,buffPreset(enabled,profile.class_info.name==='Demon Avenger'));
      markEdited();renderFields();q('#sc-all-buffs').checked=enabled;return;
    }
    if(e.target.dataset.ability) {
      draft['stat.passiveSkillLevelUp']=e.target.dataset.ability==='passiveSkillLevelUp';
      draft['stat.increaseTarget']=e.target.dataset.ability==='increaseTarget';
      markEdited();return;
    }
    if(e.target.dataset.weapon) {
      draft['special.oneHandSword']=e.target.dataset.weapon==='true';markEdited();return;
    }
    const path=e.target.dataset.path;if(!path)return;
    if(numericField(e.target)){
      // Empty while replacing a number is an edit buffer, not a missing scan.
      if(e.target.value==='')return;
      // Cap typed values at the field's in-game maximum (HEXA 30, guild skills 15, ...).
      if(e.target.max!==''&&Number(e.target.value)>Number(e.target.max))e.target.value=e.target.max;
      e.target.dataset.numberEditing='true';
    }
    draft[path]=e.target.type==='checkbox'?e.target.checked:(e.target.value===''?null:e.target.value);
    if(path.startsWith('doping.')) {
      const group=exclusiveBuffs.find(keys=>keys.includes(path.slice(7)));
      if(group && e.target.checked) for(const key of group) if(`doping.${key}`!==path) draft[`doping.${key}`]=false;
      if(path==='doping.stat') draft['doping.statPotion']=Number(e.target.value)>0;
      const guild=guildSkills.find(([,,,index])=>path===`doping.nobless.${index}`);
      if(guild)draft[`doping.${guild[0]}`]=Number(e.target.value)>0;
      for(const el of q('#sc-fields').querySelectorAll('input[type=checkbox][data-path]')) el.checked=!!currentValues()[el.dataset.path];
      q('#sc-all-buffs').checked=false;
    }
    if(path==='stat.resetCoolDown') {
      const disabled=Number(e.target.value)>17.5;
      if(disabled){draft['stat.passiveSkillLevelUp']=false;draft['stat.increaseTarget']=false;}
      for(const el of q('#sc-fields').querySelectorAll('[data-ability]')) {
        el.disabled=disabled&&el.dataset.ability!=='none';
        if(disabled)el.checked=el.dataset.ability==='none';
      }
    }
    for(const tile of q('#sc-fields').querySelectorAll('.sc-site-tile')) {
      const checkbox=tile.querySelector('input[type=checkbox]');
      tile.classList.toggle('is-on',checkbox?checkbox.checked:Number(tile.querySelector('input').value)>0);
    }
    e.target.closest('.sc-field')?.classList.toggle('sc-missing',e.target.value==='');
    if(!e.target.closest('[data-sc-tooltip]'))e.target.title=e.target.getAttribute('aria-label')+' · Saving…';
    markEdited();
  });
  q('#sc-fields').addEventListener('click',e=>{
    if(e.target.closest('#sc-form-prep')){e.preventDefault();q('#sc-prep').click();return;}
    const cycle=e.target.closest('[data-cycle]');
    if(cycle){
      const choices=cycle.dataset.choices.split(','),path=cycle.dataset.cycle;
      draft[path]=choices[(choices.indexOf(String(currentValues()[path]))+1)%choices.length];
      markEdited();renderFields();return;
    }

  });
  q('#sc-character').onchange=()=>action(async()=>{
    const next=id();q('#sc-character').value=profile.character.id;
    await save();q('#sc-character').value=next;
    localStorage.setItem('hascone.scouter.character',next);window.dispatchEvent(new CustomEvent('character-selected',{detail:next}));selectedResult='';lastSimulation=false;lastSuggestions=false;await load();
  });
  q('#sc-scan').onclick=()=>action(async()=>{await save();window.dispatchEvent(new CustomEvent('scouter-guide',{detail:id()}));});
  q('#sc-calculate').onclick=()=>action(async()=>{await save();showTab('results');const s=await api.post(`${endpoint()}/calculate`,{});lastCalculation=s.active;status(s.message);if(!s.active)await load();});
  q('#sc-stop').onclick=async()=>{try {await api.post('/api/scouter/cancel',{});status('Stop requested.');}catch(e){toast(e.message,'danger');}};
  q('#sc-preset-export').onclick=exportPreset;
  q('#sc-prep').onclick=()=>window.open('https://maplescouter.com/en/input','_blank','noopener,noreferrer');
  q('#sc-name-form').onsubmit=e=>{e.preventDefault();action(async()=>{const record=selectedResult;const saved=await api.post(`${endpoint()}/history/${encodeURIComponent(record)}/name`,{name:q('#sc-snapshot-name').value});profile.history.find(r=>r.id===record).name=saved.name;renderResults();});};
  q('#sc-history').onchange=()=>{selectedResult=q('#sc-history').value;renderResults();};
  // Delete the selected saved calculation, with its simulations, after confirmation.
  q('#sc-delete-snapshot').onclick=()=>{
    const record=profile.history.find(r=>r.id===selectedResult);if(!record)return;
    const dialog=document.createElement('dialog');dialog.className='delete-character-dialog';
    dialog.setAttribute('aria-label','Delete calculation');
    dialog.innerHTML=`<h2>Delete this calculation?</h2><p>${esc(new Date(record.created).toLocaleString())}${record.name?' · '+esc(record.name):''}</p><p class="sub">Its results and simulations are removed. Your inputs and other calculations stay. This cannot be undone.</p><p class="warn" role="alert"></p><footer><button class="btn" data-cancel autofocus>Cancel</button><button class="btn delete-confirm">Delete calculation</button></footer>`;
    document.body.append(dialog);dialog.showModal();
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
    dialog.querySelector('.delete-confirm').onclick=async e=>{
      const button=e.currentTarget;button.disabled=true;button.textContent='Deleting…';
      try{await api.delete(`${endpoint()}/history/${encodeURIComponent(record.id)}`);dialog.close();selectedResult='';await load();toast('Calculation deleted.');}
      catch(error){dialog.querySelector('[role="alert"]').textContent=error.message;button.disabled=false;button.textContent='Delete calculation';}
    };
  };
  async function tick() {
    if (disposed || polling || pending || saveFlight) return;polling=true;
    const generation=pollGeneration;
    try {
      const calc=await api.get('/api/scouter/state');
      if(disposed||generation!==pollGeneration)return;
      const simulating=calc.active&&calc.kind==='simulation'&&calc.profile===id();
      const suggesting=calc.active&&calc.kind==='suggestions'&&calc.profile===id();
      const calculating=calc.active&&!['simulation','suggestions'].includes(calc.kind)&&calc.profile===id();
      suggestions.setBusy(!!calc.active);
      simulator.setBusy(!!calc.active);
      if(q('#sc-quick-fd-run'))q('#sc-quick-fd-run').disabled=!!calc.active;
      if(simulating||suggesting)status(calc.message);
      if(lastSuggestions&&!suggesting){await save();await load();status(calc.message);}
      lastSuggestions=suggesting;
      if(lastSimulation&&!simulating){
        const target=id(), fresh=await api.get(endpoint());
        if(disposed||target!==id())return;
        profile=fresh;renderResults();status(calc.message);
      }
      lastSimulation=simulating;
      if(calculating)status(calc.message);
      if(lastCalculation&&!calculating){
        await save();await load();status(calc.message);
      }
      lastCalculation=calculating;
      q('#sc-calculate').disabled=!!calc.active||missingCount()>0;
      if(!calc.active&&!dirty&&!pending)await api.post(`/api/characters/${id()}/progression`,{});
    }catch(e){if(!disposed)status(e.message);}finally{polling=false;}
  }
  if(!characters.length){status('Add a character profile first.');q('#sc-scan').disabled=true;q('#sc-calculate').disabled=true;return ()=>{disposed=true;suggestions.dispose();disposeTooltips();};}
  await load();
  showTab(activeTab);
  const timer=setInterval(tick,1200);tick();
  return ()=>{disposed=true;suggestions.dispose();disposeTooltips();clearInterval(timer);clearTimeout(saveTimer);if(dirty)void save().catch(()=>{});if(portrait)URL.revokeObjectURL(portrait);for(const u of urls.values())URL.revokeObjectURL(u);};
}
