const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const scouter=fs.readFileSync(path.join(__dirname,'../../web/pages/scouter.js'),'utf8');

test('the Item swap tab is registered everywhere the Scouter tabs are listed',()=>{
 assert.match(scouter,/\['results','simulator','swap','suggestions','efficiencies'\]\.includes\(/);
 assert.equal(scouter.match(/\['inputs','results','simulator','swap','suggestions','efficiencies'\]/g).length,2);
 assert.match(scouter,/id="sc-tab-swap" role="tab" aria-controls="sc-panel-swap" data-sc-tab="swap">Item swap</);
 assert.match(scouter,/<section id="sc-panel-swap" role="tabpanel" aria-labelledby="sc-tab-swap">/);
 assert.match(scouter,/swap\.setBusy\(!!calc\.active\)/);
 assert.match(scouter,/swap\.update\(profile,selectedResult\)/);
});

// The markup app.js produced before the grid moved into a shared component.
function legacyGrid({selected,profile,slots,slot,page,flameIcon,refresh,esc,human}){
 return `<div class="equip-grid"><img class="portrait" src="/api/characters/${selected}/portrait" alt="${esc(profile.name)}">${refresh}${Object.entries(slots).map(([key,pos])=>{const saved=profile.equipment[key],scanned=page==='flame'?saved?.stats:saved?.potential;return `<button class="equip-slot ${key===slot?'selected':''} ${page!=='flame'?esc(saved?.potential?.rank||''):''}" data-slot="${key}" style="left:${pos.x}px;top:${pos.y}px" aria-label="${esc(human(key))}">${saved?.name||saved?.occupied?`<img src="/api/characters/${selected}/equipment/${key}/icon?t=${encodeURIComponent(saved?.updated||profile.equipment_captured||'')}" alt="${esc(human(key))}">`:esc(human(key))}${page==='flame'&&scanned?`<span class="score with-flame">${flameIcon}${saved.flame_score?.toFixed(1)||'0.0'}</span>`:['equipment','starforce'].includes(page)&&saved?.starforce?.status==='scanned'?`<span class="score">${saved.starforce.stars}*</span>`:''}</button>`}).join('')}</div>`;
}

test('the shared equipment grid renders the existing pages unchanged',async()=>{
 const {equipGrid,slotLabel}=await import('../../web/components/equip_grid.js');
 const {escapeHtml:esc}=await import('../../web/ui.js');
 const slots={ring_1:{x:0,y:0},hat:{x:225,y:0},pendant_2:{x:45,y:180},medal:{x:270,y:225}};
 const profile={name:'Tekky <ru>',equipment_captured:'2026-10-24',equipment:{
  ring_1:{name:'Endless Terror',updated:'u1',potential:{rank:'Legendary'},starforce:{status:'scanned',stars:23}},
  hat:{name:'Eternal Knight Helm',stats:[{name:'STR'}],flame_score:151.25,potential:{rank:'Unique'},starforce:{status:'scanned',stars:19}},
  pendant_2:{occupied:true},
 }};
 const flameIcon='<svg class="flame-icon"></svg>', refresh='<button class="portrait-refresh"></button>';
 for(const page of ['equipment','flame','starforce','potential'])for(const slot of ['hat','medal']){
  const expected=legacyGrid({selected:'abc',profile,slots,slot,page,flameIcon,refresh,esc,human:slotLabel});
  const actual=equipGrid({characterId:'abc',name:profile.name,slots,equipment:profile.equipment,captured:profile.equipment_captured,selected:slot,portraitExtra:refresh,
   slotClass:(key,saved)=>page!=='flame'?esc(saved?.potential?.rank||''):'',
   badge:(key,saved)=>page==='flame'&&saved?.stats?`<span class="score with-flame">${flameIcon}${saved.flame_score?.toFixed(1)||'0.0'}</span>`:['equipment','starforce'].includes(page)&&saved?.starforce?.status==='scanned'?`<span class="score">${saved.starforce.stars}*</span>`:''});
  assert.equal(actual,expected,`${page}/${slot}`);
 }
});

test('weapon, android and pocket slots render disabled with a reason',async()=>{
 const {equipGrid}=await import('../../web/components/equip_grid.js');
 const html=equipGrid({characterId:'abc',name:'x',slots:{weapon:{x:0,y:0},hat:{x:1,y:1}},equipment:{},selected:'hat',
  disabled:key=>key==='weapon'?'Weapon cannot be swapped':''});
 assert.match(html,/data-slot="weapon"[^>]*aria-disabled="true" title="Weapon cannot be swapped"/);
 assert.doesNotMatch(html,/data-slot="hat"[^>]*aria-disabled/);
});

const data={slots:['hat','ring_1','ring_2'],current:{hat:{item:'warrior:eternal-warrior-hat',stars:19},ring_1:{item:'giant-fear'},ring_2:{item:null}}};

test('a turned-off slot keeps its inputs and only enabled slots are swapped',async()=>{
 const {freshConfig,enabledSlots}=await import('../../web/pages/scouter-swap.js');
 const config=freshConfig(data);
 assert.deepEqual(enabledSlots(config),[]);
 config.slots.ring_1.candidate={item:'whisper-of-the-source',stars:22};
 config.slots.ring_1.enabled=true;config.slots.hat.enabled=true;
 assert.deepEqual(enabledSlots(config),['hat','ring_1']);
 config.slots.ring_1.enabled=false;
 assert.deepEqual(enabledSlots(config),['hat']);
 assert.deepEqual(config.slots.ring_1.candidate,{item:'whisper-of-the-source',stars:22});
 assert.equal(data.current.hat.stars,19);config.slots.hat.current.stars=22;assert.equal(data.current.hat.stars,19);
});

test('restoring a saved run brings back every slot and group, and fills new slots from the scan',async()=>{
 const {restoreConfig}=await import('../../web/pages/scouter-swap.js');
 const saved={slots:{ring_1:{enabled:false,current:{item:'giant-fear'},candidate:{item:'whisper-of-the-source'}},weapon:{enabled:true}},
  groups:[{id:'g',name:'Lose set',enabled:false,fields:{bossDmg:'-10'}}]};
 const config=restoreConfig(saved,data);
 assert.deepEqual(config.slots.ring_1,saved.slots.ring_1);
 assert.equal(config.slots.weapon,undefined);
 assert.deepEqual(config.slots.hat,{enabled:false,current:{item:'warrior:eternal-warrior-hat',stars:19},candidate:{}});
 assert.deepEqual(config.groups,saved.groups);
 config.groups[0].fields.bossDmg='5';assert.equal(saved.groups[0].fields.bossDmg,'-10');
 assert.deepEqual(restoreConfig(null,data).groups,[]);
});

test('only a simulation saves a swap: the tab keeps no draft in browser storage, and swaps can be deleted',()=>{
 const tab=fs.readFileSync(path.join(__dirname,'../../web/pages/scouter-swap.js'),'utf8');
 assert.doesNotMatch(tab,/localStorage\.setItem/);
 assert.match(tab,/id="sc-swap-delete"/);
 assert.match(scouter,/api\.delete\(`\$\{endpoint\(\)\}\/history\/\$\{encodeURIComponent\(resultId\)\}\/swaps\/\$\{encodeURIComponent\(runId\)\}`\)/);
});

test('a reopened saved swap is not reported as changed when the server sorted its keys',async()=>{
 const {restoreConfig,sameConfig}=await import('../../web/pages/scouter-swap.js');
 const onScreen=restoreConfig({slots:{ring_1:{enabled:true,current:{item:'giant-fear'},candidate:{stars:22,item:'whisper-of-the-source'}}},groups:[]},data);
 const fromServer={groups:[],slots:{ring_1:{candidate:{item:'whisper-of-the-source',stars:22},current:{item:'giant-fear'},enabled:true}}};
 assert.ok(sameConfig(restoreConfig(fromServer,data),onScreen));
 onScreen.slots.ring_1.candidate.stars=21;
 assert.ok(!sameConfig(restoreConfig(fromServer,data),onScreen));
});

test('swaps saved with a Lose group reopen as negative values; Gain groups keep their values',async()=>{
 const {restoreConfig}=await import('../../web/pages/scouter-swap.js');
 const config=restoreConfig({slots:{},groups:[
  {id:'a',name:'Lose',enabled:true,mode:'lose',fields:{bossDmg:'10',atk:'',criDmg:'-2'}},
  {id:'b',name:'Gain',enabled:true,mode:'gain',fields:{bossDmg:'5'}},
  {id:'c',name:'New',enabled:true,fields:{bossDmg:'-3'}}]},data);
 assert.deepEqual(config.groups,[
  {id:'a',name:'Lose',enabled:true,fields:{bossDmg:'-10',atk:'',criDmg:'2'}},
  {id:'b',name:'Gain',enabled:true,fields:{bossDmg:'5'}},
  {id:'c',name:'New',enabled:true,fields:{bossDmg:'-3'}}]);
});

test('copy from current brings over stars, flames and potential, and item extras only for the same item',async()=>{
 const {copiedCandidate}=await import('../../web/pages/scouter-swap.js');
 const current={item:'warrior:astra-force-shield',scanned_name:'Astra Force Shield',stars:18,flame:{str:1},potential:{atkPer:33},
  variant:{stage:2,version:1},addons:{rfs_infused:1},pick_variant:true};
 const same=copiedCandidate(current,{});
 assert.deepEqual(same,{item:'warrior:astra-force-shield',stars:18,flame:{str:1},potential:{atkPer:33},addons:{rfs_infused:1},variant:{stage:2,version:1}});
 same.potential.atkPer=36;assert.equal(current.potential.atkPer,33);
 assert.deepEqual(copiedCandidate(current,{item:'warrior:ruin-force-shield',stars:5}),
  {item:'warrior:ruin-force-shield',stars:18,flame:{str:1},potential:{atkPer:33}});
 assert.deepEqual(copiedCandidate({item:null},{}),{item:null});
});
