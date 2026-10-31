const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const scouter=fs.readFileSync(path.join(__dirname,'../../web/pages/scouter.js'),'utf8');
const table=JSON.parse(fs.readFileSync(path.join(__dirname,'../../src/hyperstats/data/hyper_stats.json'),'utf8'));
const stat=key=>table.stats.find(s=>s.key===key);
const hyper=()=>import('../../web/pages/scouter-hyper.js');

test('the Hyper stats tab sits after Item swap and is wired like it',()=>{
 assert.match(scouter,/data-sc-tab="swap">Item swap<\/button><button class="btn" id="sc-tab-hyper" role="tab" aria-controls="sc-panel-hyper" data-sc-tab="hyper">Hyper stats</);
 assert.match(scouter,/<section id="sc-panel-hyper" role="tabpanel" aria-labelledby="sc-tab-hyper">/);
 for(const call of ['hyper.update(profile,selectedResult)','hyper.setBusy(!!calc.active)','hyper.dispose()'])assert.ok(scouter.includes(call),call);
 assert.match(scouter,/\/hyper\/verify`,\{result_id:resultId,settings\}/);
});

test('a pending preview is dropped, not run, once the baseline calculation is gone',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../../web/pages/scouter-hyper.js'),'utf8');
 assert.match(source,/if\(!baseline\)\{previewing=false;return;\}\s*const mine=\+\+serial/);
 assert.ok(source.includes('if(!baseline){clearTimeout(timer);serial++;previewing=false;}'));
});

test('level boxes take whole numbers within the in-game maximum and are never clamped',async()=>{
 const {parseLevel}=await hyper();
 assert.deepEqual(parseLevel('0',stat('luk')),{level:0});
 assert.deepEqual(parseLevel(' 15 ',stat('luk')),{level:15});
 assert.deepEqual(parseLevel('10',stat('df_tf')),{level:10});
 for(const raw of ['','16','-1','1.5','abc',null])assert.match(parseLevel(raw,stat('luk')).error,/LUK must be a whole number from 0 to 15/);
 assert.match(parseLevel('11',stat('df_tf')).error,/0 to 10/);
});

test('effects and points follow the in-game table',async()=>{
 const {effectText,pointsUsed}=await hyper();
 assert.equal(effectText(stat('str'),10),'+300');
 assert.equal(effectText(stat('crit_rate'),6),'+7%');
 assert.equal(effectText(stat('exp'),1),'+0.5%');
 assert.equal(effectText(stat('ied'),0),'');
 assert.equal(pointsUsed({luk:15,ied:0},table.costs),550);
 assert.equal(pointsUsed({luk:10,crit_damage:5},table.costs),150+25);
});

test('settings start from the saved allocation, else blank with the class default Keep',async()=>{
 const {initialSettings,sameSettings}=await hyper();
 const data={stats:table.stats,keep:['int','hp'],settings:null};
 const blank=initialSettings(data);
 assert.equal(Object.keys(blank.levels).length,17);
 assert.ok(Object.values(blank.levels).every(v=>v===0));
 assert.deepEqual(blank.keep,['int','hp']);
 assert.equal(blank.defense,'380');assert.equal(blank.crit_rate,null);
 const saved=initialSettings({...data,settings:{levels:{luk:10},keep:['crit_rate'],defense:'300',crit_rate:120}});
 assert.equal(saved.levels.luk,10);assert.equal(saved.levels.dex,0);
 assert.deepEqual(saved.keep,['crit_rate']);assert.equal(saved.defense,'300');assert.equal(saved.crit_rate,120);
 const reordered={...saved,levels:Object.fromEntries(Object.entries(saved.levels).reverse()),keep:[...saved.keep]};
 assert.ok(sameSettings(saved,reordered));
 assert.ok(!sameSettings(saved,{...saved,crit_rate:null}));
});
