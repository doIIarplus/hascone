const {test}=require('node:test');
const assert=require('node:assert/strict');
test('HEXA completion accepts only a matching saved level',async()=>{
 const {completionChange}=await import('../../web/pages/scouter-hexa.js');
 const row=[];row[9]='masteryCore1';row[10]='4\u21925';
 const cores={masteryCore1:{url:'icon.png'}};
 assert.deepEqual(completionChange(row,{'hexa.masteryCore1':'4'},cores),{path:'hexa.masteryCore1',value:5,stat:false});
 assert.equal(completionChange(row,{'hexa.masteryCore1':'3'},cores),null);
 row[10]='unrecognized';assert.equal(completionChange(row,{'hexa.masteryCore1':'4'},cores),null);
 row[10]='4\u219231';assert.equal(completionChange(row,{'hexa.masteryCore1':'4'},cores),null);
});
test('HEXA Stat completion advances core count, not level 20',async()=>{
 const {completionChange}=await import('../../web/pages/scouter-hexa.js');
 const row=[];row[9]='hexaStat2';row[10]='HEXA Stat II 0\u219220';
 assert.deepEqual(completionChange(row,{'hexa.hexaStat':1},{}),{path:'hexa.hexaStat',value:2,stat:true});
 assert.equal(completionChange(row,{'hexa.hexaStat':0},{}),null);
 assert.equal(completionChange(row,{'hexa.hexaStat':2},{}),null);
});
test('equipment scan action is separate from static help',async()=>{
 const {scanPrompt}=await import('../../web/guide.js');
 const prompt=scanPrompt({mode:'hover:hat',label:'Hat',instruction:'old text'});
 assert.equal(prompt.action,'Hover your Hat');assert.match(prompt.help,/tooltip/);
});
