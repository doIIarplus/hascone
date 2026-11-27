const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const web=path.join(__dirname,'../../web');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../../src/quanah/data/lines.json'),'utf8'));

function model(extra={}){
 const items=[
  {id:'a',slot:'hat',lines:['dl','wh','dmg'],wearable:true,duplicate:true,item_class:'warrior',source:'scan',raw:['Dimensional Leap Lv. +1']},
  {id:'b',slot:'hat',lines:['dmg','dl','wh'],wearable:true,duplicate:true,item_class:'warrior',source:'manual'},
  {id:'c',slot:'top',lines:['reg','<x>'],wearable:false,duplicate:false,item_class:'bowman',source:'scan',name:'Libae <Top>'},
 ];
 const solution={score:3,goal:18,ways:1,targets:{dl:3,wh:3,dmg:3},counts:{dl:1,wh:1,dmg:1},jobs:null,
  picks:{hat:'a',top:null,bottom:null,gloves:null,shoes:null,cape:null},
  used:{hat:[true,true,true],top:[],bottom:[],gloves:[],shoes:[],cape:[]},missing:['dl','dl','wh','wh','dmg','dmg'],hunt:[]};
 return {catalog,class:'warrior',build:{preset:'eu',job_mode:'custom',jobs:[],targets:{}},items,solution,...extra};
}

test('gear lists duplicates, other-class pieces and the picked piece, escaping text',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const html=renderGear(model());
 assert.equal((html.match(/>Duplicate</g)||[]).length,2);
 assert.match(html,/title="This piece is for Bowman\. Orb its lines onto a Warrior top to use them\.">Bowman</);
 assert.doesNotMatch(html,/Orb ·|Scanned|Manual/);
 assert.match(html,/q-piece is-picked/);
 assert.match(html,/&lt;x&gt;/);
 assert.match(html,/No bottom yet/);
 assert.doesNotMatch(html,/<x>|undefined|null/);
});

test('pieces sit hat/cape, top/gloves, bottom/shoes, unnumbered, each with a ... menu',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const html=renderGear(model(),'c');
 const order=[...html.matchAll(/<h3>([^<]+)<\/h3>/g)].map(m=>m[1]);
 assert.deepEqual(order,['Hat','Cape','Top','Gloves','Bottom','Shoes']);
 assert.doesNotMatch(html,/#\d/);
 assert.equal((html.match(/data-act="menu"/g)||[]).length,3);
 assert.doesNotMatch(html,/data-act="(edit|delete)"/);
 assert.match(html,/q-piece [^"]*is-editing"/);
 assert.match(html,/title="Read as:\nDimensional Leap Lv\. \+1"/);
 assert.match(html,/aria-label="More for Hat: Dimensional Leap, White Hole, DMG"/);
 // The open menu holds edit and delete for that piece only.
 const open=renderGear(model(),null,0,'a');
 assert.match(open,/data-id="a" aria-haspopup="menu" aria-expanded="true"/);
 assert.match(open,/role="menu"><button role="menuitem" data-act="edit" data-id="a" aria-label="Edit Hat: Dimensional Leap, White Hole, DMG">/);
 assert.match(open,/data-act="delete" data-id="a"/);
 assert.equal((open.match(/role="menu"/g)||[]).length,1);
});

test('best set shows the score, what is still missing and struck-through waste',async()=>{
 const {renderBest}=await import('../../web/pages/quanah.js');
 let html=renderBest(model());
 assert.match(html,/15 lines short/);
 assert.match(html,/Still missing/);
 const wasted=model();wasted.solution.used.hat=[true,false,true];
 html=renderBest(wasted);
 assert.match(html,/is-wasted/);
 assert.match(html,/Struck-through/);
});

test('best set tags a picked piece of another class and counts the orbs needed',async()=>{
 const {renderBest}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[2]={...m.items[2],transfer:true};
 m.solution={...m.solution,orbs:1,picks:{...m.solution.picks,top:'c'},used:{...m.solution.used,top:[true,false]}};
 const html=renderBest(m);
 assert.match(html,/>Bowman</);
 assert.match(html,/<strong>1 orb<\/strong> <span class="sub">needed: Top</);
 assert.doesNotMatch(renderBest(model()),/needed:/);
});

test('each piece has a disable toggle, and a disabled piece is dimmed',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[0]={...m.items[0],disabled:true};
 const html=renderGear(m);
 assert.equal((html.match(/data-act="disabled"/g)||[]).length,3);
 assert.match(html,/q-piece [^"]*is-disabled/);
 assert.match(html,/aria-label="Enable Hat: Dimensional Leap/);
});

test('a worn slot notes the orb on one-drop hints and its disabled worn piece in the set',async()=>{
 const {renderBest}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[0]={...m.items[0],worn:true,disabled:true};
 m.solution={...m.solution,picks:{...m.solution.picks,hat:null},used:{...m.solution.used,hat:[]},hunt:[{slot:'hat',need:['dl']},{slot:'top',need:['wh']}]};
 const html=renderBest(m);
 assert.match(html,/Keep wearing yours \(disabled\)/);
 assert.equal((html.match(/\+ 1 orb/g)||[]).length,1);
 assert.match(html,/<strong>Hat<\/strong><span class="q-chip q-dl ">Dimensional Leap<\/span><span class="sub"/);
});

test('combo arrows wrap round both ways',async()=>{
 const {stepCombo}=await import('../../web/pages/quanah.js');
 assert.equal(stepCombo(0,-1,3),2);
 assert.equal(stepCombo(2,1,3),0);
 assert.equal(stepCombo(1,1,3),2);
});

test('mark toggles flip the piece\'s current mark',async()=>{
 const {markRequest}=await import('../../web/pages/quanah.js');
 assert.deepEqual(markRequest('prefer',{id:'a b',preferred:true}),['/api/quanah/items/a%20b/preferred',{preferred:false}]);
 assert.deepEqual(markRequest('worn',{id:'a'}),['/api/quanah/items/a/worn',{worn:true}]);
 assert.deepEqual(markRequest('disabled',{id:'a',disabled:false}),['/api/quanah/items/a/disabled',{disabled:true}]);
});

test('an on-class pick that needs an orb is tagged Orb; an off-class one shows its class',async()=>{
 const {renderBest}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[0]={...m.items[0],transfer:true};
 m.items[2]={...m.items[2],transfer:true};
 m.solution={...m.solution,picks:{...m.solution.picks,top:'c'},used:{...m.solution.used,top:[true,false]}};
 const html=renderBest(m);
 assert.equal((html.match(/>Orb</g)||[]).length,1);
 assert.match(html,/>Bowman</);
});

test('each piece has a wearing toggle',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[1]={...m.items[1],worn:true};
 const html=renderGear(m);
 assert.equal((html.match(/data-act="worn"/g)||[]).length,3);
 assert.match(html,/q-worn is-on" data-act="worn" data-id="b" aria-pressed="true" aria-label="Not wearing Hat/);
});

test('each piece has a prefer star, and a preferred pick is tagged in the best set',async()=>{
 const {renderGear,renderBest}=await import('../../web/pages/quanah.js');
 const m=model();
 m.items[0]={...m.items[0],preferred:true};
 const html=renderGear(m);
 assert.equal((html.match(/data-act="prefer"/g)||[]).length,3);
 assert.equal((html.match(/aria-pressed="true"/g)||[]).length,1);
 assert.match(html,/aria-label="Stop preferring Hat: Dimensional Leap/);
 assert.match(renderBest(m),/>Preferred</);
 assert.doesNotMatch(renderBest(model()),/>Preferred</);
});

test('several winning combos get arrows, and the shown combo drives both lists',async()=>{
 const {renderBest,renderGear}=await import('../../web/pages/quanah.js');
 const m=model();
 const empty={top:[],bottom:[],gloves:[],shoes:[],cape:[]};
 const nulls={top:null,bottom:null,gloves:null,shoes:null,cape:null};
 m.solution={...m.solution,score:3,goal:3,ways:2,targets:{dl:1,wh:1,dmg:1},
  combos:[{picks:{hat:'a',...nulls},used:{hat:[true,true,true],...empty}},{picks:{hat:'b',...nulls},used:{hat:[true,true,true],...empty}}]};
 let html=renderBest(m,1);
 assert.match(html,/Combo 2 of 2</);
 assert.equal((html.match(/data-act="combo"/g)||[]).length,2);
 assert.match(html,/q-chip q-dmg[^"]*">DMG<\/span><span class="q-chip q-dl/);
 const gear=renderGear(m,null,1);
 assert.match(gear,/q-piece is-picked[^>]*><span class="q-lines"><span class="q-chip q-dmg/);
 m.solution.ways=150;
 assert.match(renderBest(m,0),/Combo 1 of 2\+/);
 m.solution.combos=m.solution.combos.slice(0,1);
 assert.doesNotMatch(renderBest(m),/data-act="combo"/);
});

test('Hybrid job rule shows as one requirement of any 3 jobs',async()=>{
 const {requirementRows}=await import('../../web/pages/quanah.js');
 const m=model();
 m.solution={...m.solution,targets:{dl:3},counts:{dl:3,magician:1,thief:1,bowman:0},jobs:{count:3,keys:['magician','thief','bowman']}};
 const rows=requirementRows(m);
 assert.deepEqual(rows.at(-1),{label:'Magician · Thief · Bowman',have:2,target:3,jobs:false});
 m.solution.jobs={count:3,keys:['warrior','magician','bowman','thief','pirate']};
 assert.equal(requirementRows(m).at(-1).jobs,true);
});

test('requirements are listed by lines needed, then in catalog order',async()=>{
 const {requirementRows}=await import('../../web/pages/quanah.js');
 const m=model();
 // As the server sends them: keys sorted alphabetically.
 m.solution={...m.solution,jobs:null,counts:{},targets:{atk:3,bowman:1,crit:1,dl:3,magician:1,pirate:1,reg:3,thief:1,warrior:1,wh:3}};
 assert.deepEqual(requirementRows(m).map(r=>r.label),
  ['Dimensional Leap','White Hole','Registry','ATK','Crit DMG','Warrior','Magician','Bowman','Thief','Pirate']);
 m.solution={...m.solution,targets:{dl:3,crit:3},jobs:{count:3,keys:['magician','thief','bowman']}};
 assert.deepEqual(requirementRows(m).map(r=>r.label),['Dimensional Leap','Crit DMG','Magician · Thief · Bowman']);
});

test('items that are not Quanah pieces are counted as skipped, not failed',async()=>{
 const {scanSummary}=await import('../../web/pages/quanah.js');
 const s=scanSummary({done:['a'],pending:[],failed:{x:'Skipped HYPER BURNING MAX: not a Quanah piece',y:'Skill lines cut off'}});
 assert.equal(s.counts,'1 saved · 0 processing · 1 skipped · 1 failed');
 assert.deepEqual(s.skipped,['HYPER BURNING MAX']);
 assert.deepEqual(s.failed,['Skill lines cut off']);
 assert.equal(scanSummary({done:[],pending:['p'],failed:{}}).counts,'0 saved · 1 processing');
});

test('a custom build with no targets asks for one instead of claiming a win',async()=>{
 const {renderBest}=await import('../../web/pages/quanah.js');
 const m=model();m.solution={...m.solution,goal:0,score:0,targets:{}};
 const html=renderBest(m);
 assert.match(html,/Set at least one line target/);
 assert.doesNotMatch(html,/Complete/);
});

test('Quanah opens from a pinned roster tile without a character',()=>{
 const app=fs.readFileSync(path.join(web,'app.js'),'utf8');
 const roster=fs.readFileSync(path.join(web,'roster.js'),'utf8');
 assert.match(app,/import \{mountQuanah\} from '\.\/pages\/quanah\.js'/);
 // The Quanah branch runs before the no-character early return.
 assert.ok(app.indexOf("page==='quanah'){")<app.indexOf('if(!selected){'));
 assert.match(app,/mountRoster\([^)]*\)[^;]*navigate\('quanah'\)/);
 assert.match(roster,/data-seasonal="quanah"/);
 assert.match(roster,/id===QUANAH\?'Quanah'/);
});
