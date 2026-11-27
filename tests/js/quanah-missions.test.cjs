const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../../src/quanah/data/missions.json'),'utf8'));
const model=(done=[],summary={})=>({catalog,done,summary:{points:0,permanent:0,round:0,grade:1,next:{grade:2,points:5000},completed:done.length,total:110,max_points:114650,...summary}});

test('summary shows grade, progress to the next, completed count and permanent points',async()=>{
 const {renderSummary}=await import('../../web/pages/quanah-missions.js');
 const html=renderSummary(model(['sf-5','sf-8'],{points:7500,permanent:2500,round:5000,grade:2,next:{grade:3,points:10000},completed:2}));
 assert.match(html,/<strong>2<\/strong>/);
 assert.match(html,/2,500 pts to Grade 3/);
 assert.match(html,/aria-valuenow="50"/);
 assert.match(html,/Missions completed<\/dt><dd>2 <small>\/ 110/);
 assert.match(html,/Permanent points<\/dt><dd>2,500/);
 assert.doesNotMatch(html,/data-act="reset-round" disabled/);
});

test('top grade says so, and reset is off with no round points',async()=>{
 const {renderSummary}=await import('../../web/pages/quanah-missions.js');
 const html=renderSummary(model([],{points:30000,grade:5,next:null}));
 assert.match(html,/Highest grade reached/);
 assert.match(html,/aria-valuenow="100"/);
 assert.match(html,/data-act="reset-round" disabled/);
});

test('groups render a checkmark per mission; bosses get a row each',async()=>{
 const {renderGroup}=await import('../../web/pages/quanah-missions.js');
 const [inspector,,bosses]=catalog.groups;
 const html=renderGroup(inspector,['level-5','level-10']);
 assert.equal((html.match(/type="checkbox"/g)||[]).length,20);
 assert.equal((html.match(/ checked/g)||[]).length,2);
 assert.match(html,/2\/20 · 100 \/ 20,700 pts/);
 assert.match(html,/>Round</);
 const boss=renderGroup(bosses,[]);
 assert.equal((boss.match(/<li>/g)||[]).length,16);
 assert.match(boss,/Kalos the Guardian<\/span><span class="qm-diffs">(.*?Easy.*?Normal.*?Chaos.*?Extreme)/);
 assert.match(boss,/>Permanent</);
});
