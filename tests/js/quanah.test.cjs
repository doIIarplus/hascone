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

test('gear lists duplicates, unwearable pieces and the picked piece, escaping text',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const html=renderGear(model());
 assert.equal((html.match(/>Duplicate</g)||[]).length,2);
 assert.match(html,/Can't wear · Bowman/);
 assert.match(html,/q-piece is-picked/);
 assert.match(html,/&lt;x&gt;/);
 assert.match(html,/No bottom yet/);
 assert.doesNotMatch(html,/<x>|undefined|null/);
});

test('pieces sit hat/cape, top/gloves, bottom/shoes, unnumbered, each with edit and delete',async()=>{
 const {renderGear}=await import('../../web/pages/quanah.js');
 const html=renderGear(model(),'c');
 const order=[...html.matchAll(/<h3>([^<]+)<\/h3>/g)].map(m=>m[1]);
 assert.deepEqual(order,['Hat','Cape','Top','Gloves','Bottom','Shoes']);
 assert.doesNotMatch(html,/#\d/);
 assert.equal((html.match(/data-act="edit"/g)||[]).length,3);
 assert.match(html,/q-piece [^"]*is-unwearable is-editing"/);
 assert.match(html,/title="Read as:\nDimensional Leap Lv\. \+1"/);
 assert.match(html,/aria-label="Edit Hat: Dimensional Leap, White Hole, DMG"/);
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

test('GanDi job rule shows as one requirement of any 3 jobs',async()=>{
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
