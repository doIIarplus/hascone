const {test}=require('node:test');
const assert=require('node:assert/strict');
test('all optimized targets retain multiple choices per item',async()=>{
 const {selectSuggestionRows}=await import('../../web/pages/suggestion-filters.js');
 const rows=[{slot:'hat',kind:'cube',method:'Bright'},{slot:'hat',kind:'cube',method:'Glowing'},{slot:'hat',kind:'starforce',method:'Star Force',strategy:'mesos'},{slot:'hat',kind:'starforce',method:'Star Force',strategy:'booms'},{slot:'eye',kind:'flame',method:'Black Flame'}];
 assert.equal(selectSuggestionRows(rows,'best').length,2);
 assert.equal(selectSuggestionRows(rows,'all-mesos').length,4);
 assert.equal(selectSuggestionRows(rows,'all').length,5);
 assert.equal(selectSuggestionRows(rows,'all-mesos','cube').length,2);
 assert.equal(selectSuggestionRows(rows,'all-booms','starforce')[0].strategy,'booms');
});
const step=(slot,from,stepNo,steps,strategy='mesos',extra={})=>({slot,kind:'starforce',method:'Star Force',strategy,strategy_label:strategy==='mesos'?'Least mesos':'Fewest booms',current_stars:from,target_stars:from+1,step:stepNo,steps,chain_target:19+steps,requires:stepNo>1?`${from-1}→${from}`:null,expected_fd:1,expected_mesos:100*stepNo,expected_rolls:2,expected_booms:0.1,stat_gains:{'Attack Power':stepNo},starforce_plan:[{star:from,mode:1,recovery:false}],notes:[`Step ${stepNo} of ${steps} toward your 22★ target.`],fd_per_billion:10-stepNo,raw_fd_per_billion:10-stepNo,...extra});
test('best keeps one row per item, merging the target steps that follow it',async()=>{
 const {selectSuggestionRows}=await import('../../web/pages/suggestion-filters.js');
 const rows=[step('face',19,1,3),step('face',20,2,3),{slot:'eye',kind:'flame',method:'Black Flame'},step('face',21,3,3),step('face',19,1,3,'booms'),{slot:'face',kind:'cube',method:'Bright'}];
 const best=selectSuggestionRows(rows,'best');
 assert.deepEqual(best.map(r=>[r.slot,r.kind,r.current_stars,r.target_stars]),[['face','starforce',19,21],['eye','flame',undefined,undefined]]);
 const merged=best[0];
 assert.deepEqual(merged.merged_steps,['19→20','20→21']);
 assert.deepEqual(merged.step_range,[1,2]);
 assert.equal(merged.expected_mesos,300);
 assert.equal(merged.expected_booms,0.2);
 assert.deepEqual(merged.stat_gains,{'Attack Power':3});
 assert.equal(merged.fd_per_billion,2/300*1e9);
 assert.equal(merged.requires,null);
 assert.deepEqual(merged.starforce_plan.map(s=>s.star),[19,20]);
 assert.ok(merged.notes[0].startsWith('Combines steps 1–2 of 3 toward 22★'));
 assert.ok(!merged.notes.some(n=>n.startsWith('Step ')));
});
test('best never places another item between rows of one item',async()=>{
 const {selectSuggestionRows}=await import('../../web/pages/suggestion-filters.js');
 const flameFirst=selectSuggestionRows([{slot:'face',kind:'flame',method:'Black Flame'},step('face',19,1,3),{slot:'eye',kind:'flame',method:'Black Flame'},step('face',20,2,3)],'best');
 assert.deepEqual(flameFirst.map(r=>[r.slot,r.kind]),[['face','flame'],['eye','flame']]);
 const skipped=selectSuggestionRows([step('face',19,1,3),{slot:'face',kind:'cube',method:'Bright'},step('face',20,2,3),{slot:'eye',kind:'flame',method:'Black Flame'},step('face',21,3,3)],'best');
 assert.deepEqual(skipped.map(r=>[r.slot,r.current_stars,r.target_stars]),[['face',19,21],['eye',undefined,undefined]]);
});
test('steps of different plans or items never merge',async()=>{
 const {mergeSequential}=await import('../../web/pages/suggestion-filters.js');
 const out=mergeSequential([step('face',19,1,3),step('face',20,2,3,'booms'),step('ring1',20,2,3),step('face',21,3,3)]);
 assert.equal(out.length,4);
 assert.ok(out.every(r=>!r.merged_steps));
});
test('rows without a target are untouched',async()=>{
 const {mergeSequential}=await import('../../web/pages/suggestion-filters.js');
 const a={slot:'hat',kind:'starforce',strategy:'mesos',current_stars:19,target_stars:20,steps:1};
 const b={slot:'hat',kind:'starforce',strategy:'mesos',current_stars:20,target_stars:21,steps:1};
 assert.deepEqual(mergeSequential([a,b]),[a,b]);
});
