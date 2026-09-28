import { escapeHtml as esc, toast } from '../ui.js';
import { renderBossPanels } from './scouter-bosses.js';

const fmt = v => Number(v).toLocaleString(undefined,{maximumFractionDigits:3});
const signed = v => `${Number(v)>0?'+':''}${fmt(v)}`;
const clean = changes => Object.fromEntries(Object.entries(changes).filter(([,v])=>Number(v)!==0).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k,String(Number(v))]));

export function createSimulator(view, {onRun,onBaseline,loadIcons}) {
  let profile, baseline, changes={}, key='', selected='', count=0, busy=false, filter='relevant';
  const q = s => view.querySelector(s);
  const label = f => f.label.replace('Other secondary stat',profile.class_info.sub2||'Other secondary stat')
    .replace('Secondary stat',profile.class_info.sub).replace('Main stat',profile.class_info.main);
  function pendingChanges() {
    const result=baseline?.simulations?.find(r=>r.id===selected);
    return result && JSON.stringify(clean(result.changes))!==JSON.stringify(clean(changes));
  }
  function render() {
    if(!baseline) {
      view.innerHTML='<div class="card empty">Calculate your character first, then use that saved result to simulate upgrades.</div>';
      return;
    }
    const fields=profile.simulator_fields.filter(f=>!f.key.startsWith('ssubStat')||profile.class_info.sub2);
    view.innerHTML=`<div class="sc-section-title"><h2>Simulator</h2></div>
      <div class="card sc-sim-form" data-collapsible="simulator-inputs"><h3>Stat changes</h3><div class="sc-sim-toolbar"><label>Baseline calculation<select class="input" id="sc-sim-baseline">${[...profile.history].reverse().map(r=>`<option value="${esc(r.id)}" ${r.id===baseline.id?'selected':''}>${esc(new Date(r.created).toLocaleString())} · HEXA ${fmt(r.damage?.calculatedData?.boss380_hexaStat)}</option>`).join('')}</select></label><div class="sc-actions"><button class="btn btn-ghost" id="sc-sim-reset">Reset changes</button><button class="btn btn-primary" id="sc-sim-run">Simulate</button></div></div>
      <p class="sub sc-note">Add or subtract stats from this saved baseline. +10 attack % adds 10 percentage points. Additional IED combines as an IED source. Final damage is a relative multiplier. Other character settings stay as saved.</p>
      <div class="sc-sim-fd"><label for="sc-sim-finalDmg">Custom final damage <small>Relative gain or loss (%)</small></label><input class="input" type="number" id="sc-sim-finalDmg" data-sim-field="finalDmg" min="-99.99" max="75" step="0.01" placeholder="e.g. 3" value="${esc(changes.finalDmg??'')}"><button class="btn" id="sc-sim-fd-only">Compare FD only</button><small>Simulate combines all fields; this button uses only the FD value.</small></div>
      <div class="sc-sim-groups">${['Damage','Stats','Other'].map(group=>`<fieldset><legend>${group}</legend><div class="sc-sim-fields">${fields.filter(f=>f.group===group&&f.key!=='finalDmg').map(f=>`<label for="sc-sim-${f.key}"><span>${esc(label(f))}<small>${esc(f.unit)}</small></span><input class="input" type="number" id="sc-sim-${f.key}" data-sim-field="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" placeholder="0" value="${esc(changes[f.key]??'')}"></label>`).join('')}</div></fieldset>`).join('')}</div>
      <p class="sub sc-note" id="sc-sim-message" role="status"></p></div>
      <div class="sc-section-title"><h2>Comparison</h2><select class="input" id="sc-sim-history" aria-label="Saved simulation"></select></div><div id="sc-sim-output"></div>`;
    q('#sc-sim-baseline').onchange=e=>onBaseline(e.target.value);
    q('#sc-sim-fd-only').onclick=()=>{const input=q('#sc-sim-finalDmg');if(!input.checkValidity()){input.reportValidity();return;}compareFD(input.value||'0');};
    q('#sc-sim-reset').onclick=()=>{changes={};render();};
    q('#sc-sim-run').onclick=async()=>{
      if(busy)return;
      const invalid=[...view.querySelectorAll('[data-sim-field]')].find(i=>!i.checkValidity());
      if(invalid){invalid.reportValidity();return;}
      setBusy(true);
      try {await onRun(baseline.id,clean(changes));}
      catch(e){setBusy(false);q('#sc-sim-message').textContent=e.message;toast(e.message,'danger');}
    };
    view.oninput=e=>{if(!e.target.dataset.simField)return;changes[e.target.dataset.simField]=e.target.value;q('#sc-sim-message').textContent=pendingChanges()?'Changes not simulated yet.':'';};
    const records=[...(baseline.simulations||[])].reverse();
    q('#sc-sim-history').innerHTML=records.length?records.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''}>${esc(new Date(r.created).toLocaleTimeString())} · ${esc(Object.entries(r.changes).map(([k,v])=>`${label(fields.find(f=>f.key===k)||{label:k})} ${signed(v)}`).join(', ')||'No changes')}</option>`).join(''):'<option>No simulations yet</option>';
    q('#sc-sim-history').disabled=!records.length;
    q('#sc-sim-history').onchange=e=>{selected=e.target.value;changes={...baseline.simulations.find(r=>r.id===selected).changes};render();};
    renderOutput();setBusy(busy);
  }
  function renderOutput() {
    const result=baseline.simulations?.find(r=>r.id===selected);
    if(!result){q('#sc-sim-output').innerHTML='<div class="card empty">Enter stat changes and press Simulate to compare FD, HEXA scores, and boss estimates.</div>';return;}
    q('#sc-sim-output').innerHTML=`<div class="sc-sim-score-grid">${['380','300'].map(d=>{const s=result.scores[d];return `<div class="card sc-sim-score"><span>Boss ${d} DEF</span><strong class="${s.fd_percent<0?'sc-loss':'sc-gain'}">${signed(s.fd_percent)}% FD</strong><div><span>HEXA</span><b>${fmt(s.before)} → ${fmt(s.after)}</b><small>${signed(s.after-s.before)}</small></div></div>`;}).join('')}</div>
    ${renderBossPanels(result.boss_cuts,filter,baseline.boss_cuts,'sc-sim')}`;
    const picker=q('#sc-sim-boss-filter');if(picker)picker.onchange=e=>{filter=e.target.value;renderOutput();q('#sc-sim-boss-filter')?.focus();};
    loadIcons();
    q('#sc-sim-message').textContent=pendingChanges()?'Changes not simulated yet.':'Saved comparison · character inputs are unchanged.';
  }
  function setBusy(value) {
    busy=value;
    for(const el of view.querySelectorAll('input,button,#sc-sim-baseline'))el.disabled=busy;
    if(busy&&q('#sc-sim-message'))q('#sc-sim-message').textContent='Calculating with MapleScouter…';
  }
  function update(p,id) {
    profile=p;baseline=p.history.find(r=>r.id===id);
    const nextKey=`${p.character.id}:${id}`, records=baseline?.simulations||[];
    if(key!==nextKey){key=nextKey;changes={...(records.at(-1)?.changes||{})};selected=records.at(-1)?.id||'';count=records.length;}
    else if(records.length!==count){selected=records.at(-1)?.id||'';count=records.length;}
    render();
  }
  function compareFD(value) {
    if(busy||!baseline)return;
    changes={finalDmg:value};render();q('#sc-sim-run').click();
  }
  return {update,setBusy,compareFD};
}
