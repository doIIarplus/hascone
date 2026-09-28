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
