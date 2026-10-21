const {test}=require('node:test');
const assert=require('node:assert/strict');
const flush=()=>new Promise(resolve=>setImmediate(resolve));

async function setup(t,state){
 const {api}=await import('../../web/api.js');
 const {watchScouterCompletion}=await import('../../web/scouter_completion.js');
 const storage=new Map(),events=new EventTarget();let poll;
 t.mock.method(api,'get',async path=>{assert.equal(path,'/api/scouter/state');return state;});
 t.mock.method(global,'setInterval',callback=>{poll=callback;return 1;});
 t.mock.method(global,'clearInterval',()=>{});
 const savedWindow=global.window,savedStorage=global.sessionStorage;
 global.window=events;
 global.sessionStorage={getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)};
 t.after(()=>{global.window=savedWindow;global.sessionStorage=savedStorage;});
 return {watch:watchScouterCompletion,poll:()=>poll(),events,storage};
}

test('completion opens the returned character/result once, including after a UI reload',async t=>{
 const state={active:true,status:'calculating',profile:'character'};
 const context=await setup(t,state),opened=[];
 let stop=context.watch(async(...args)=>opened.push(args));await flush();
 assert.deepEqual(opened,[]);
 Object.assign(state,{active:false,status:'complete',result_id:'new-result'});
 await context.poll();await context.poll();
 assert.deepEqual(opened,[['character','new-result']]);
 stop();stop=context.watch(async(...args)=>opened.push(args));await flush();
 assert.equal(opened.length,1,'already opened result must not steal navigation after reload');
 state.result_id='next-result';await context.poll();
 assert.deepEqual(opened.at(-1),['character','next-result']);stop();
});

test('completed calculation is found on initial load; other job types and failures do not navigate',async t=>{
 const state={active:false,status:'complete',profile:'character',result_id:'finished-while-reloading'};
 const context=await setup(t,state),opened=[];
 const stop=context.watch(async(...args)=>opened.push(args));await flush();
 assert.deepEqual(opened,[['character','finished-while-reloading']]);
 for(const kind of ['connection','simulation','suggestions']){
  Object.assign(state,{kind,result_id:kind});await context.poll();
 }
 delete state.kind;state.status='error';await context.poll();
 state.status='stopped';await context.poll();assert.equal(opened.length,1);stop();
});

test('failed saves defer navigation; cached completion events are handled without waiting for polling',async t=>{
 const state={active:false,status:'idle'};
 const context=await setup(t,state),opened=[];let saveAllowed=false;
 const stop=context.watch(async(...args)=>{if(!saveAllowed)return false;opened.push(args);});await flush();
 Object.assign(state,{status:'complete',profile:'character',result_id:'cached'});
 await context.poll();assert.equal(context.storage.size,0);
 saveAllowed=true;
 const event=new Event('scouter-calculated');event.detail={...state};context.events.dispatchEvent(event);
 await flush();assert.deepEqual(opened,[['character','cached']]);
 await context.poll();assert.equal(opened.length,1);stop();
});
