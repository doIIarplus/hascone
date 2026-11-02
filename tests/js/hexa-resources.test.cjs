const {test}=require('node:test');
const assert=require('node:assert/strict');

test('each HEXA resource selects its own saved route with a legacy fragment fallback',async()=>{
 const {resourceOrder}=await import('../../web/pages/scouter-hexa.js');
 const fragment={class_hexa:['fragment']},sol={class_hexa:['sol']};
 const record={order:fragment,hexa_orders:{sol_erda:{order:sol}}};
 assert.equal(resourceOrder(record,'fragments'),fragment);
 assert.equal(resourceOrder(record,'sol_erda'),sol);
 assert.equal(resourceOrder({order:fragment},'sol_erda'),null);
 assert.equal(resourceOrder(null,'sol_erda'),null);
 const updated={class_hexa:['updated fragment']};
 record.hexa_orders.fragments={order:updated};
 assert.equal(resourceOrder(record,'fragments'),updated);
 assert.equal(resourceOrder(record,'sol_erda'),sol);
});

test('Sol Erda efficiency converts the API fragment efficiency using the row costs',async()=>{
 const {resourceEfficiency}=await import('../../web/pages/scouter-hexa.js');
 const row=[];row[3]=5;row[4]=324;row[7]=0.418;
 assert.equal(resourceEfficiency(row,'fragments'),0.418);
 assert.ok(Math.abs(resourceEfficiency(row,'sol_erda')-0.90288)<1e-10);
 row[3]=0;assert.equal(resourceEfficiency(row,'sol_erda'),null);
 row[3]=null;assert.equal(resourceEfficiency(row,'sol_erda'),null);
 row[3]=5;row[4]=null;assert.equal(resourceEfficiency(row,'sol_erda'),null);
 row[7]=null;assert.equal(resourceEfficiency(row,'fragments'),null);
});

async function mountedPage(t,{lostPost=false}={}){
 const {api}=await import('../../web/api.js');
 const {mountHexa}=await import('../../web/pages/hexa.js');
 // Only the controls this test interacts with need DOM behavior; rendering stays real.
 const root={isConnected:true,controls:{},querySelector(selector){return this.controls[selector]||null;},querySelectorAll(){return [];}};
 let html='',poll;
 Object.defineProperty(root,'innerHTML',{get:()=>html,set:value=>{
  html=value;root.controls={};
  for(const id of ['hexa-resource','hexa-calculate','hexa-stop']){
   if(value.includes(`id="${id}"`))root.controls['#'+id]={addEventListener(name,callback){this[name]=callback;}};
  }
 }});
 const profile={character:{id:'character',name:'Example',class:'Hero'},fingerprint:'baseline',values:{hexa:{}},
  class_info:{cores:{}},history:[{id:'base',created:'2026-11-01T00:00:00Z',fingerprint:'baseline',order:{class_hexa:[]}}]};
 const job={active:false,status:'idle'};
 let failRead=false,posts=0;
 const endpoint='/api/scouter/characters/character';
 t.mock.method(api,'get',async path=>{
  if(path==='/api/scouter/state')return structuredClone(job);
  assert.equal(path,endpoint);
  if(failRead){failRead=false;throw new Error('Temporary read failure');}
  return structuredClone(profile);
 });
 function complete(){
  const row=[];row[3]=5;row[4]=324;row[7]=0.418;row[9]='hexaStat1';row[10]='0→20';
  profile.history[0].hexa_orders={sol_erda:{created:'2026-11-01T00:01:00Z',order:{class_hexa:[row]}}};
  job.active=false;job.status='complete';job.message='HEXA route saved.';
 }
 t.mock.method(api,'post',async(path,body)=>{
  assert.equal(path,endpoint+'/hexa-order');
  assert.deepEqual(body,{result_id:'base',resource:'sol_erda',refresh:false});
  posts++;profile.hexa_resource='sol_erda';
  Object.assign(job,{active:true,status:'calculating',kind:'hexa_order',profile:'character',baseline_id:'base',resource:'sol_erda'});
  if(lostPost){complete();throw new Error('Lost response');}
  return structuredClone(job);
 });
 t.mock.method(global,'setInterval',callback=>{poll=callback;return 1;});
 t.mock.method(global,'clearInterval',()=>{});
 const dispose=await mountHexa(root,'character');t.after(dispose);
 return {root,complete,poll:()=>poll(),failRead:()=>{failRead=true;},posts:()=>posts};
}

test('a failed profile read after route completion is retried without replaying the calculation',async t=>{
 const page=await mountedPage(t);
 await page.root.controls['#hexa-resource'].onchange({target:{value:'sol_erda'}});
 page.complete();page.failRead();
 await page.poll();
 assert.doesNotMatch(page.root.innerHTML,/0\.903% \/ Sol Erda/);
 await page.poll();
 assert.match(page.root.innerHTML,/HEXA Stat I/);
 assert.match(page.root.innerHTML,/0\.903% \/ Sol Erda/);
 assert.equal(page.posts(),1);
});

test('polling recovers a finished route after the POST response was lost',async t=>{
 const page=await mountedPage(t,{lostPost:true});
 await page.root.controls['#hexa-resource'].onchange({target:{value:'sol_erda'}});
 assert.match(page.root.innerHTML,/Lost response/);
 await page.poll();
 assert.match(page.root.innerHTML,/HEXA Stat I/);
 assert.match(page.root.innerHTML,/HEXA route saved/);
 assert.equal(page.posts(),1);
});
