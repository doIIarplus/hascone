import { escapeHtml as esc } from '../ui.js';
import { coreName } from './scouter-hexa.js';
import { buffs, guildSkills, champions, links, rings, hexaOrder } from './scouter-fields.js';

const fmt = v => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined,{maximumFractionDigits:2});
const icon = name => `<img data-icon="${esc(name)}" alt="" width="32" height="32">`;

// Values displayed beside the form. These are the website's baseline
// display formulas, not the HEXA / efficiency calculation (which still uses API).
export function displayStats(values, info) {
  const n = path => values[path] == null || values[path] === '' ? null : Number(values[path]);
  const total = (base,per,abs) => [base,per,abs].some(k=>n(`stat.${k}`)==null) ? null
    : Math.floor(Number((n(`stat.${base}`)*(1+n(`stat.${per}`)/100)+n(`stat.${abs}`)).toFixed(10)));
  const attack = total('atkBase','atkPercent','atkAbs');
  const c = info.input_display;
  if (!c || n('stat.level') == null) return {attack,finalDamage:null,range:null};
  const fd = values['stat.passiveSkillLevelUp'] ? c.finalDamage2 : c.finalDamage;
  const shield = ['Demon Slayer','Demon Avenger'].includes(info.name) && values['special.useRuinForceShild'];
  const finalDamage = Number((100*((1+fd/100)*(values['special.genesis']?1.1:1)*(shield?1.1:1)
    *(values['special.isReboot']?(n('stat.level')<250?1.35:1.45):1)-1)).toFixed(10));
  const main = total('mainStatBase','mainStatPer','mainStatAbs');
  const sub = total('subStatBase','subStatPer','subStatAbs');
  const sub2 = info.sub2 ? total('ssubStatBase','ssubStatPer','ssubStatAbs') : 0;
  if ([main,sub,sub2,attack,n('stat.dmg')].some(v=>v==null)) return {attack,finalDamage,range:null};
  const hpBase = 90*n('stat.level')+545;
  const stat = info.name==='Demon Avenger' ? (Math.floor(hpBase/3.5)+.8*Math.floor((main-hpBase)/3.5)+sub)/100
    : info.name==='Xenon' ? (main+sub+sub2)*4/100 : (main*4+sub+sub2)/100;
  const weapon = values['special.oneHandSword'] && ['Hero','Paladin','Dawn Warrior'].includes(info.name)
    ? (info.name==='Hero'?1.34:1.24) : c.weaponConstant;
  return {attack,finalDamage,range:Math.floor(Math.round(attack*weapon*stat)*(1+n('stat.dmg')/100)*(1+finalDamage/100))};
}

export function renderInputs(profile, values, draft) {
  const c = profile.class_info, da = c.name==='Demon Avenger';
  function source(path) {
    const reading = profile.scanned[path];
    return Object.hasOwn(draft,path) ? 'Saving…'
      : reading && String(reading.value)===String(values[path]) ? `Scanned · ${Math.round(reading.confidence*100)}% confidence` : values[path]==null ? 'Needs input' : 'Saved value';
  }
  function input(path,label,{max,step='any',unit='',compact=false}={}) {
    return `<input class="input" type="number" id="sc-${esc(path)}" data-path="${esc(path)}" aria-label="${esc(label)}${unit?' '+esc(unit):''}" ${compact?'':`title="${esc(label)} · ${esc(source(path))}"`} min="${path==='stat.level'?1:0}" ${max!=null?`max="${max}"`:''} step="${step}" value="${esc(values[path]??'')}" placeholder="—"${compact?' inputmode="numeric"':''}>`;
  }
  function field(path,label,unit='',max) {
    return `<div class="sc-field sc-site-stat ${values[path]==null?'sc-missing':''}"><label for="sc-${esc(path)}">${esc(label)}</label><div class="sc-site-number">${input(path,label,{unit,max})}${unit?`<span>${esc(unit)}</span>`:''}</div></div>`;
  }
  function check(path,label,disabled=false) {
    return `<label class="sc-site-check" title="${esc(label)}${disabled?' · fixed for this profile':''}"><input class="sc-checkbox" type="checkbox" ${disabled?'disabled':`data-path="${esc(path)}"`} ${values[path]?'checked':''}><span>${esc(label)}</span></label>`;
  }
  function tile(path,label,image,{toggle,max=30,checkOnly=false}={}) {
    const on = checkOnly ? values[path] : toggle ? values[toggle] : Number(values[path])>0;
    return `<div class="sc-field sc-site-tile ${on?'is-on':''} ${values[path]==null?'sc-missing':''}" data-sc-tooltip="${esc(label)}">
      ${toggle?`<label class="sc-site-tile-image">${icon(image)}<input class="sc-checkbox" type="checkbox" data-path="${esc(toggle)}" aria-label="Enable ${esc(label)}" ${values[toggle]?'checked':''}></label>`:
      checkOnly?`<label class="sc-site-tile-image" for="sc-${esc(path)}">${icon(image)}</label>`:icon(image)}
      ${checkOnly?`<input class="sc-checkbox" id="sc-${esc(path)}" type="checkbox" data-path="${esc(path)}" aria-label="${esc(label)}" ${values[path]?'checked':''}>`:input(path,label,{max,step:1,compact:true})}</div>`;
  }
  const readonly = (label,key,unit='') => `<div class="sc-site-stat sc-site-readonly"><span>${esc(label)}</span><output data-display="${key}" data-unit="${unit}"></output></div>`;
  const row = (prefix,name) => `<div class="sc-site-stat-row"><span>${esc(name)}</span>${['Base','Per','Abs'].map((suffix,i)=>`<div class="sc-field ${values[`stat.${prefix}${suffix}`]==null?'sc-missing':''}">${input(`stat.${prefix}${suffix}`,`${name} · ${['base value','% value','% not applied'][i]}`)}</div>`).join('')}</div>`;
  const cycle = (path,label,choices) => `<button class="btn btn-sm sc-site-cycle ${String(values[path])!=='0'?'is-on':''}" data-cycle="${esc(path)}" data-choices="${esc(choices.join(','))}" aria-label="${esc(label)}" title="Click to cycle ${esc(choices.join(' / '))}">${esc(label)} <strong>${String(values[path])==='0'?'Off':esc(values[path])}</strong></button>`;
  const weaponChoice = ['Hero','Paladin','Dawn Warrior'].includes(c.name) ? `<div class="sc-site-choice" role="group" aria-label="Weapon type">${[true,false].map(one=>`<label><input type="radio" class="sc-checkbox" name="sc-weapon" data-weapon="${one}" ${!!values['special.oneHandSword']===one?'checked':''}>${one?'One-handed':'Two-handed'}</label>`).join('')}</div>` : '';
  const ability = values['stat.passiveSkillLevelUp'] ? 'passiveSkillLevelUp' : values['stat.increaseTarget'] ? 'increaseTarget' : 'none';
  return `<div class="sc-site-form">
    <section class="card sc-site-stats" aria-label="Character stats"><h3>Direct input</h3>
      <div class="sc-site-pair">${field('stat.level','Level','',300)}<div class="sc-site-stat"><span>Class</span><select class="input" disabled aria-label="Class"><option>${esc(c.name)}</option></select></div></div>
      <p class="sc-site-prep">Prepare your bossing preset with 100% critical rate. Hover a stat in game for its base, %, and % not applied values. <a href="#" id="sc-form-prep">Preparation guide ↗</a></p>
      <div class="sc-site-options">${check('special.isReboot','Reboot',true)}${check('special.genesis','Liberated',true)}${check('special.destiny2ndSkill','First Legacy')}${cycle('special.mugongSoul','Mu Gong Soul',['0','1','2'])}
        ${da?cycle('special.epiSoul','Epinephrine',['0','1','2','C']):''}${['Demon Slayer','Demon Avenger'].includes(c.name)?check('special.useRuinForceShild','Ruin Force Shield'):''}${weaponChoice}</div>
      <div class="sc-site-stat-table"><div class="sc-site-stat-head"><span>Stat</span><span>Base value</span><span>% value</span><span>% not applied</span></div>
        ${row('mainStat',c.main)}${row('subStat',c.sub)}${c.sub2?row('ssubStat',c.sub2):''}
        <div class="sc-site-stat-row"><span>${c.main==='INT'?'M.Attack':'Attack'}</span>${['atkBase','atkPercent','atkAbs'].map((key,i)=>`<div class="sc-field ${values[`stat.${key}`]==null?'sc-missing':''}">${input(`stat.${key}`,`Attack · ${['base value','% value','% not applied'][i]}`)}</div>`).join('')}</div></div>
      <div class="sc-site-stat-pairs">
        ${readonly('General range','range')}${field('stat.dmg','Damage','%')}
        ${readonly('Final damage','finalDamage','%')}${field('stat.bossDmg','Boss damage','%',750)}
        ${field('stat.ignoreDef','Ignore defense','%',99.9999)}${readonly('Normal enemy damage','normalDmg','%')}
        ${readonly('Attack','attack')}${field('stat.critical','Critical rate','%')}
        ${readonly('M.Attack','attack')}${field('stat.criticalDmg','Critical damage','%',250)}
        <div class="sc-site-stat sc-site-cooldown"><span>Cooldown reduction</span><div class="sc-site-number">${input('stat.coolTimeReduce','Cooldown reduction',{unit:'seconds',max:9})}<span>s</span>${input('stat.coolTimeReducePercent','Cooldown reduction',{unit:'percent',max:6})}<span>%</span></div></div>${field('stat.buffDuration','Buff duration','%',400)}
        ${field('stat.resetCoolDown','Cooldown skip','%',27.5)}${field('stat.ignoreElementalResist','Ignore elemental resistance','%',15)}
        ${field('stat.statusAdditionalDmg','Abnormal status damage','%',30)}${field('stat.summonPersistTime','Summon duration','%',42)}
        ${field('stat.arcaneForce','Arcane Force')}${field('stat.authenticForce','Sacred Force')}
        ${c.name==='Zero'?field('stat.classForce','Time Force'):''}
      </div>
    </section>
    <aside class="card sc-site-sidebar" aria-label="Buffs and skills">
      <section class="sc-site-section" data-group="Buffs"><div class="sc-site-heading"><h3>Buffs</h3><label class="sc-site-check"><input class="sc-checkbox" type="checkbox" id="sc-all-buffs">Select all</label></div>
        <div class="sc-site-tiles">${guildSkills.map(([,l,img,i])=>tile(`doping.nobless.${i}`,l,`doping_v2_${img}.png`,{max:15})).join('')}
        ${tile('doping.stat','Stat potion amount','doping_v2_statpotion.png',{toggle:'doping.statPotion',max:30})}
        ${buffs.map(([key,label,img])=>tile(`doping.${da&&key==='legendHero'?'legendHp':key}`,da&&key==='legendHero'?'Legendary HP Potion':label,`doping_v2_${img}.png`,{checkOnly:true})).join('')}
        ${champions.map(([key,label])=>tile(`doping.${key}`,`Legion Champion · ${label}`,'doping_v2_champion.png',{max:5})).join('')}</div>
      </section>
      <section class="sc-site-section" data-group="Links and HEXA"><div class="sc-site-heading"><h3>Links / Legion</h3></div>
        <div class="sc-site-tiles">${links.filter(([,,,only])=>!only||only===c.name).map(([key,label,max])=>tile(`linkSkill.${key}`,`${label} link`, `linkskill_${key}.png`,{max})).join('')}</div>
        ${field('stat.wildhunterUnion','Wild Hunter Legion')}</section>
      <section class="sc-site-section" data-group="HEXA"><h3>HEXA enhancement</h3><div class="sc-hexa-stat-input"><label for="sc-hexa.hexaStat">HEXA Stat cores completed (level 20)<select class="input" id="sc-hexa.hexaStat" data-path="hexa.hexaStat" aria-label="Completed HEXA Stat cores">${[0,1,2,3].map(n=>`<option value="${n}" ${Number(values['hexa.hexaStat']||0)===n?'selected':''}>${n}</option>`).join('')}</select></label><p class="sub">Enter this manually. Scouter models completed cores rather than individual main/additional line levels. After upgrading HEXA Stats, rescan your character stats before calculating.</p></div><div class="sc-site-tiles">${hexaOrder.filter(key=>c.cores[key]?.url).map(key=>tile(`hexa.${key}`,coreName(c.cores[key],key),c.cores[key].url.split('/').pop())).join('')}
        ${tile('huntSkill.erdaShower','Erda Shower','erda.png')}${tile('huntSkill.solJanus','Sol Janus','General_1_0.png')}</div>
      </section>
      <div class="sc-site-bottom"><div><section class="sc-site-section"><h3>Artifact</h3>${check('stat.artifact_increaseTarget','Additional EXP (+1 target)')}${field('stat.artifact_finalAttack','Final attack')}</section>
        <section class="sc-site-section"><h3>Special Inner Ability</h3><div class="sc-site-ability" role="radiogroup" aria-label="Special Inner Ability">${[['none','None'],['passiveSkillLevelUp','Passive skill level +1'],['increaseTarget','Targets hit +1']].map(([key,label])=>`<label><input type="radio" class="sc-checkbox" name="sc-ability" data-ability="${key}" ${ability===key?'checked':''} ${key!=='none'&&Number(values['stat.resetCoolDown'])>17.5?'disabled':''}>${label}</label>`).join('')}</div></section></div>
        <section class="sc-site-section"><h3>Oz rings</h3><div class="sc-site-tiles">${rings.map(([key,label,img])=>tile(`special.${key}`,label,`seedring_${img}.png`,{max:6})).join('')}</div></section>
      </div>
    </aside>
  </div>`;
}

export function updateDisplayStats(root, values, info) {
  const display = {...displayStats(values,info),normalDmg:values['stat.normalDmg']==null?null:Number(values['stat.normalDmg'])};
  for (const el of root.querySelectorAll('[data-display]')) {
    const v = display[el.dataset.display];
    el.textContent = fmt(v)+(v!=null&&Number.isFinite(v)?el.dataset.unit:'');
  }
}

// A visible tooltip replaces native title delays and works on keyboard focus too.
export function attachInputTooltips(root) {
  const tip=document.createElement('div');
  tip.id='sc-input-tooltip';tip.className='sc-input-tooltip';tip.role='tooltip';tip.hidden=true;
  document.body.append(tip);
  let active=null;
  function hide() {
    active?.querySelectorAll('[aria-describedby="sc-input-tooltip"]').forEach(el=>el.removeAttribute('aria-describedby'));
    active=null;tip.hidden=true;
  }
  function show(tile) {
    if(!tile || !root.contains(tile)) {hide();return;}
    if(active===tile && !tip.hidden)return;
    const box=tile.getBoundingClientRect();
    if(!box.width || box.bottom<=0 || box.top>=window.innerHeight){hide();return;}
    hide();active=tile;tip.textContent=tile.dataset.scTooltip;tip.hidden=false;
    tile.querySelectorAll('input').forEach(el=>el.setAttribute('aria-describedby',tip.id));
    const rect=tip.getBoundingClientRect();
    tip.style.left=`${Math.max(8,Math.min(window.innerWidth-rect.width-8,box.left+(box.width-rect.width)/2))}px`;
    const above=box.top-rect.height-8;
    tip.style.top=`${Math.max(8,Math.min(window.innerHeight-rect.height-8,above>=8?above:box.bottom+8))}px`;
  }
  const over=e=>show(e.target.closest('[data-sc-tooltip]'));
  const out=e=>{
    if(active?.contains(e.relatedTarget))return;
    show(e.relatedTarget?.closest?.('[data-sc-tooltip]'));
  };
  const key=e=>{if(e.key==='Escape')hide();};
  const scroll=()=>{
    const focused=active?.contains(document.activeElement)?active:null;
    hide();if(focused)show(focused);
  };
  root.addEventListener('pointerover',over);root.addEventListener('pointerout',out);
  root.addEventListener('focusin',over);root.addEventListener('focusout',out);
  root.addEventListener('keydown',key);
  window.addEventListener('scroll',scroll,true);window.addEventListener('resize',scroll);
  const observer=new MutationObserver(()=>{if(active&&!root.contains(active))hide();});
  observer.observe(root,{childList:true,subtree:true});
  return ()=>{
    hide();observer.disconnect();tip.remove();
    root.removeEventListener('pointerover',over);root.removeEventListener('pointerout',out);
    root.removeEventListener('focusin',over);root.removeEventListener('focusout',out);root.removeEventListener('keydown',key);
    window.removeEventListener('scroll',scroll,true);window.removeEventListener('resize',scroll);
  };
}
