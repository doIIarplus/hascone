import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

function recoveryHint(message){
 if(/fresh screenshot|capture timeout|capture.*closed/i.test(message))return 'Restore the game window and keep it open. If frames still do not arrive, restart Hascone to recreate capture.';
 if(/capture.*not.*start|Graphics Capture/i.test(message))return 'Keep MapleStory restored, select its main window, and retry. Include this message and Hascone-data/logs/native.log when reporting the issue.';
 if(/1920|1366|resolution/i.test(message))return 'In MapleStory options, choose 1920 x 1080 or 1366 x 768 at native UI scale, then refresh the window list.';
 if(/clipped|bottom edge|incomplete|truncated/i.test(message))return 'Keep all stat and potential lines visible. Move overlapping windows aside and hover the item again.';
 if(/not clear|confiden|unobstructed/i.test(message))return 'Hold the cursor still over the requested item or stat row. Move other panels away from its text, then try again.';
 if(/Disk|permission|denied|write|read.only/i.test(message))return 'Move Hascone and its data folder to a writable location, check free disk space, then rescan to save the image.';
 return '';
}
const human=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export function scanPrompt(step){
 const instruction=step.instruction||'';
 if(step.mode==='hover:any')return {action:'Hover any highlighted item',help:'Items are captured the moment their tooltip appears, in any order. Keep the complete tooltip visible.'};
 if(step.mode?.startsWith('hover:'))return {action:`Hover your ${step.label}`,help:'Keep the complete tooltip visible. It is captured as soon as it appears; move on when the next item is highlighted.'};
 if(step.mode==='equipment')return {action:'Open your Equipment window',help:'Select the Equipment tab, uncover every slot, and move the cursor away from the grid.'};
 const [action,...rest]=instruction.split(/\.\s+/);
 return {action:action||step.label,help:rest.join('. ')};
}
export function openEquipmentGuide(character,onSaved){
 return openGuide(character,[{mode:'equipment',label:'Find equipped items',instruction:'Open Equipment using its hotkey or the equipment icon at the bottom of the game. Select the Equipment tab and move your cursor off the grid. Keep all slots visible.'}],onSaved,true);
}

export async function openGuide(character,steps,onSaved,equipmentFlow=false){
 const session=crypto.randomUUID();
 const dialog=document.querySelector('#scan-dialog'),content=document.querySelector('#scan-content');
 let profile=await api.get('/api/characters/'+character);
 const registry=await api.get('/api/characters'),layout=registry.layout;
 let windows=await api.get('/api/windows');
 let index=0,timer=null,epoch=0,changed=false,disposed=false,exclude=null,selectedWindow=windows[0]?.id,paused=false;
 const completed=[],skipped=[];let skippedSlots=[];
 await api.post('/api/scan/cancel');
 dialog.showModal();
 function clear(){epoch++;if(timer)clearTimeout(timer);timer=null;}
 async function stop(){clear();await api.post('/api/scan/cancel');}
 async function close(){disposed=true;await stop();dialog.close();dialog.oncancel=null;if(changed)await onSaved();}
 dialog.oncancel=e=>{e.preventDefault();close().catch(toast);};
 function fail(e){if(disposed)return;clear();content.querySelector('.scan-spinner')?.setAttribute('hidden','');content.querySelector('#scan-status').textContent=e.message;const b=content.querySelector('#watch');if(b){b.disabled=false;b.textContent='Try again';}}
 function miniGrid(step){
  if(!equipmentFlow)return '';
  return `<div class="scan-gear"><div class="equip-grid"><img class="portrait" src="/api/characters/${character}/portrait" alt="">${Object.entries(layout.slots).map(([key,box])=>`<div class="equip-slot ${step.slot===key||step.slots?.includes(key)?'selected':''} ${profile.equipment[key]?.hover_scanned||step.done?.includes(key)?'scanned':''}" style="left:${box.x}px;top:${box.y}px" title="${esc(human(key))}">${profile.equipment[key]?.occupied?`<img src="/api/characters/${character}/equipment/${key}/icon?t=${profile.equipment_captured}" alt="${esc(human(key))}">`:esc(human(key))}</div>`).join('')}</div><p class="sub">${step.slots?step.slots.length+' left - highlighted in orange.':step.slot?'Next: '+human(step.slot)+' - highlighted in orange.':'Open Equipment to fill the grid.'}</p></div>`;
 }
 function draw(){
  const step=steps[index];paused=false;const prompt=scanPrompt(step);
  content.innerHTML=`<p class="sub">${esc(profile.name)} · ${equipmentFlow?(index===0?'1. Capture equipment':`2. Hover items · ${step.done?.length||0} of ${step.total||0}`):`Step ${index+1} of ${steps.length}`} · ${esc(step.label)}</p><progress class="scan-progress" max="${steps.length}" value="${index}"></progress><div class="guide-body">${miniGrid(step)}<div class="guide-main"><p class="scan-instruction scan-action" aria-live="polite">${esc(prompt.action)}</p><p class="sub scan-static-help">${esc(prompt.help)}</p><p class="sub">${step.mode?.startsWith('hover:')?'Captured the moment the tooltip appears. Reading continues in the background.':'Hold still while the panel is captured. Reading continues in the background.'}</p><div class="scan-toolbar"><label>Game window<select id="scan-window" class="input">${windows.length?windows.map(w=>`<option value="${w.id}" ${Number(selectedWindow)===w.id?'selected':''}>${esc(w.title)} · ${w.width} × ${w.height}</option>`).join(''):'<option value="">No game found</option>'}</select></label></div><div class="actions"><button id="watch" class="btn">Pause watching</button><button id="refresh-windows" class="btn">Refresh windows</button><label class="btn" ${step.mode==='hover:any'?'hidden':''}>Use screenshot<input id="upload" type="file" accept="image/png,image/jpeg" hidden></label></div><p id="scan-help" class="sub"></p><p class="scan-activity"><span class="scan-spinner" aria-hidden="true"></span><span id="scan-elapsed"></span></p><p id="scan-status" role="status">Preparing the scanner…</p>${completed.length?`<p class="scan-recent">✓ ${esc(completed.at(-1))} captured</p>`:''}</div></div><p id="scan-queue-status" class="sub" role="status"></p><div id="scan-result"></div><footer><button id="scan-close" class="btn">Finish later</button><button id="skip" class="btn">Skip this item / step</button><button id="save" class="btn btn-primary" hidden>Confirm & next</button></footer>`;
  content.querySelector('#scan-close').onclick=()=>close().catch(toast);
  content.querySelector('#skip').onclick=async()=>{await stop();if(step.slots){skipped.push(...step.slots.map(human));skippedSlots.push(...step.slots);step.slots=[];}else skipped.push(step.label);await next();};
  content.querySelector('#scan-window').onchange=async e=>{selectedWindow=Number(e.target.value);await stop();watch().catch(fail);};
  content.querySelector('#refresh-windows').onclick=async()=>{await stop();windows=await api.get('/api/windows');selectedWindow=windows[0]?.id;draw();};
  content.querySelector('#watch').onclick=async()=>{if(paused){watch().catch(fail);}else{await stop();paused=true;content.querySelector('#watch').textContent='Resume watching';content.querySelector('.scan-spinner').hidden=true;content.querySelector('#scan-status').textContent='Paused. Your saved readings are kept.';}};
  content.querySelector('#save').onclick=async()=>{try{const state=await api.get('/api/scan');await api.post('/api/scan/save');exclude=state.signature;changed=true;completed.push(step.label);await next(state.result);}catch(e){fail(e);}};
  content.querySelector('#upload').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>10*1024*1024){fail(new Error('Screenshot must be smaller than 10 MB.'));return;}await stop();const r=new FileReader();r.onload=()=>watch(String(r.result).split(',')[1]).catch(fail);r.readAsDataURL(file);};
  if(windows.length)watch().catch(fail);else {paused=true;content.querySelector('#watch').textContent='Start watching';content.querySelector('#scan-status').textContent='Waiting for MapleStory in a 1920 × 1080 or 1366 × 768 window…';findWindow(epoch);}
 }
 // Poll for the game window until it appears, then start watching.
 function findWindow(version){
  timer=setTimeout(async()=>{
   if(disposed||epoch!==version)return;
   try{windows=await api.get('/api/windows');}catch{windows=[];}
   if(disposed||epoch!==version)return;
   if(windows.length){selectedWindow=windows[0].id;draw();}else findWindow(version);
  },2000);
 }
 async function next(result){
  if(result?.values){steps=steps.filter((s,i)=>i<=index||!s.mode.startsWith("hexa_hover:")||!result.values[(s.mode.endsWith(":solJanus")?"huntSkill.solJanus":"hexa."+s.mode.split(":")[1])]);}
  if(equipmentFlow && index===0){
   profile=await api.get('/api/characters/'+character);
   const order=['hat','top','bottom','gloves','shoes','cape','shoulder','weapon','secondary','emblem','face','eye','earring','pendant_1','pendant_2','belt','ring_1','ring_2','ring_3','ring_4','heart','pocket','badge','medal','android'];
   const slots=order.filter(slot=>profile.equipment[slot]?.occupied);
   steps.splice(1,steps.length,...(slots.length?[{mode:'hover:any',label:'Equipment items',slots,done:[],total:slots.length}]:[]));
  }
  index++;
  if(index>=steps.length){await finish();return;}
  if(equipmentFlow)profile=await api.get('/api/characters/'+character);
  draw();
 }
 async function finish(){
  clear();
  const reads=await api.get('/api/scan/queue/'+character);
  if(reads.pending.length){
   changed=true;
   content.innerHTML=`<h3>Captures complete</h3><p>${reads.pending.length} readings are processing in the background. You can add or scan another character now. Progress and any failures appear in the roster.</p><footer><button class="btn btn-primary" id="background-done">Continue in background</button>${equipmentFlow?'<button class="btn" id="background-stats">Scan character stats</button>':''}</footer>`;
   content.querySelector('#background-done').onclick=()=>close().catch(toast);
   content.querySelector('#background-stats')?.addEventListener('click',async()=>{await close();window.dispatchEvent(new CustomEvent('scouter-guide',{detail:character}));});
   return;
  }
  if(disposed)return;
  const failed=Object.entries(reads?.failed||{});
  const rescan=[...new Set([...failed.map(([slot])=>slot),...skippedSlots])].filter(slot=>layout.slots[slot]);
  for(const [slot] of failed){const label=human(slot);const i=completed.indexOf(label);if(i>=0)completed.splice(i,1);if(!skipped.includes(label))skipped.push(label);}
  content.innerHTML=`<h3>Scan complete</h3><p>${completed.length} steps captured${skipped.length?`; ${skipped.length} skipped`:''}.</p>${skipped.length?`<p class="warn">Still to scan: ${esc(skipped.join(', '))}</p>`:''}${failed.map(([slot,msg])=>`<p class="warn">${esc(human(slot))}: ${esc(msg)}</p>`).join('')}<p class="sub">${equipmentFlow?'Your equipment now feeds Flames, Potentials and Scouter. If a tooltip could not be read, select that item and use its Scan button.':'Check the saved inputs and fill any remaining fields before calculating.'}</p><footer><button class="btn" id="done">Done</button>${rescan.length?`<button class="btn" id="rescan">Rescan ${rescan.length} item${rescan.length===1?'':'s'}</button>`:''}${equipmentFlow?'<button class="btn btn-primary" id="scouter-next">3. Scan character stats</button>':''}</footer>`;
  content.querySelector('#done').onclick=()=>close().catch(toast);
  content.querySelector('#rescan')?.addEventListener('click',async()=>{
   try{
    for(const slot of rescan){const i=skipped.indexOf(human(slot));if(i>=0)skipped.splice(i,1);}
    skippedSlots=[];
    steps.push({mode:'hover:any',label:'Equipment items',slots:[...rescan],done:[],total:rescan.length});
    index=steps.length-1;profile=await api.get('/api/characters/'+character);draw();
   }catch(e){toast(e.message,'danger');}
  });
  if(equipmentFlow)content.querySelector('#scouter-next').onclick=async()=>{await close();window.dispatchEvent(new CustomEvent('scouter-guide',{detail:character}));};
 }
 async function watch(image){
  clear();paused=false;const version=epoch,step=steps[index];
  content.querySelector('#save').hidden=true;content.querySelector('#scan-result').innerHTML='';
  content.querySelector('#watch').textContent='Pause watching';
  await api.post('/api/scan',{character,session,mode:step.mode,slot:step.slot,slots:step.slots,window:Number(selectedWindow),delay:0,watch:!image,background:true,exclude,...(image?{image}:{})});
  if(disposed||epoch!==version)return;
  const started=Date.now();
  async function tick(){
   if(disposed||epoch!==version)return;
   try{
    const [state,queue]=await Promise.all([api.get('/api/scan'),api.get('/api/scan/queue/'+character)]);if(disposed||epoch!==version)return;
    content.querySelector('#scan-queue-status').textContent=`Background readings: ${queue.done.length} saved, ${queue.pending.length} processing, ${Object.keys(queue.failed).length} need a rescan.`;
    content.querySelector('#scan-status').textContent=state.message;
    content.querySelector('.scan-spinner').hidden=!state.active;
    content.querySelector('#scan-elapsed').textContent=state.active?`${state.status==='reading'?'Reading captured image':'Watching for panel'} · ${Math.floor((Date.now()-started)/1000)}s`:'';
    content.querySelector('#scan-help').textContent=recoveryHint(state.message||'');
    if(state.active){timer=setTimeout(tick,500);return;}
    if(state.status==='captured'){
     changed=true;
     if(step.slots){
      step.slots=step.slots.filter(s=>s!==state.slot);step.done.push(state.slot);completed.push(human(state.slot));
      if(step.slots.length){draw();return;}
     }else completed.push(step.label);
     await next();return;
    }
    if(state.status==='saved'){exclude=state.signature;changed=true;completed.push(step.label);await next(state.result);return;}
    if(state.status==='review'){
     paused=true;content.querySelector('#watch').textContent='Scan again';
     const r=state.result,rows=[];
     if(r.item)rows.push(['Item',r.item]);
     const pot=r.potential||r;if(pot.rank){rows.push(['Tier',pot.rank]);pot.lines.forEach((s,i)=>rows.push([pot.line_tiers[i],s]));}
     (r.stats||[]).forEach(s=>rows.push([s.name,s.value+(s.percent?'%':'')]));
     if(r.values)Object.entries(r.values).forEach(([k,v])=>rows.push([k,v.value]));
     if(r.required_level)rows.push(['Level',r.required_level]);
     if(r.starforce?.status==='scanned')rows.push(['Stars',r.starforce.stars]);
     content.querySelector('#scan-result').innerHTML=`<img class="scan-preview" src="/api/scan/image?t=${Date.now()}" alt="Captured reading"><div class="reading-list">${rows.map(([k,v])=>`<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div>${(r.errors||[]).map(e=>`<p class="warn">${esc(e)}</p>`).join('')}<p class="sub">Confirm the correct item or stat is shown. Only these readings will be saved.</p>`;
     content.querySelector('#save').hidden=false;
    }else {paused=true;content.querySelector('#watch').textContent='Try again';}
   }catch(e){fail(e);}
  }
  await tick();
 }
 draw();
}
