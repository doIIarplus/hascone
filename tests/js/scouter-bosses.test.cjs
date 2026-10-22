const {test}=require('node:test');
const assert=require('node:assert/strict');

test('API boss cards render the returned rates and identify their source',async()=>{
 const {renderBossPanels}=await import('../../web/pages/scouter-bosses.js');
 const boss={id:'seren_destiny',boss:'Seren',difficulty:'Destiny',percent:123.4,display_percent:'123.4%',
  category:'Possible',reference:'solo',party_limit:1,boss_hexa_score:100000,can_enter:true,
  entry_level:260,icon:'boss_destiny_seren.png',thresholds:[],relevant:true};
 const html=renderBossPanels({available:true,source:'maplescouter_api',minutes:20,bosses:[boss]});
 assert.match(html,/123\.4%/);
 assert.match(html,/MapleScouter estimates returned with this calculation/);
 assert.doesNotMatch(html,/potion correction|null|undefined/);
});

test('a new API boss renders without an unavailable portrait or invented entry level',async()=>{
 const {renderBossPanels}=await import('../../web/pages/scouter-bosses.js');
 const boss={id:'new',boss:'New <boss>',difficulty:'Hard',percent:100,display_percent:'100%',
  category:'Possible',reference:'solo',party_limit:6,boss_hexa_score:90000,can_enter:true,
  entry_level:null,icon:null,thresholds:[],relevant:true};
 const html=renderBossPanels({available:true,source:'maplescouter_api',minutes:20,bosses:[boss]});
 assert.match(html,/New &lt;boss&gt;/);
 assert.doesNotMatch(html,/data-icon|Entry level|null|undefined/);
});
