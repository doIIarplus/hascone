import {escapeHtml as esc} from './ui.js';

export function mountUpdates(){
 const bridge=window.chrome?.webview;
 if(!bridge)return;
 const menu=document.querySelector('#settings-menu');
 const check=document.createElement('button');check.className='btn';check.textContent='Check for updates';
 menu.querySelector('summary + div').prepend(check);
 const badge=document.createElement('button');badge.className='btn update-badge';badge.hidden=true;
 document.body.append(badge);
 const dialog=document.createElement('dialog');dialog.className='update-dialog';document.body.append(dialog);
 let state={state:'checking'},openWhenChecked=false;
 function show(){draw();if(!dialog.open)dialog.showModal();}
 function draw(){
  const s=state.state,busy=['checking','downloading','installing'].includes(s);
  const title={checking:'Checking for updates…',current:'You’re up to date',available:`Update available: v${state.version}`,downloading:`Downloading v${state.version}`,ready:`Ready to install v${state.version}`,installing:'Restarting to update…',error:'Update check or download failed'}[s];
  dialog.innerHTML=`<h2>${esc(title)}</h2><p class="sub">Installed version: ${esc(state.current||'…')}</p>${state.message?`<p role="status">${esc(state.message)}</p>`:''}${state.version?`<h3>What’s new</h3><div class="update-notes">${esc(state.notes||'No patch notes were provided for this version.')}</div>`:''}${s==='downloading'?`<progress max="100" value="${Number(state.percent)||0}"></progress><p role="status">${Number(state.percent)||0}% downloaded</p>`:''}${s==='ready'?'<p>Finish any scans and save your changes before restarting. Your characters and settings will be kept.</p>':''}<footer><button class="btn" data-close>${busy?'Hide':'Close'}</button>${s==='available'?'<button class="btn btn-primary" data-action="download-update">Download update</button>':s==='ready'?'<button class="btn btn-primary" data-action="install-update">Restart and update</button>':['error','current'].includes(s)?'<button class="btn" data-action="check-updates">Check again</button>':''}</footer>`;
  dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.querySelector('[data-action]')?.addEventListener('click',async e=>{
   const command=e.currentTarget.dataset.action;
   if(command==='install-update'){
    const view=document.querySelector('#view');
    if(view.beforeLeave&&!(await view.beforeLeave()))return;
   }
   e.currentTarget.disabled=true;bridge.postMessage(command);
  });
 }
 check.onclick=()=>{menu.open=false;openWhenChecked=true;bridge.postMessage('check-updates');show();};
 badge.onclick=show;
 bridge.addEventListener('message',event=>{
  if(event.data?.type!=='update')return;
  state=event.data;
  badge.hidden=!state.version;
  badge.textContent=state.state==='ready'?'Update ready':state.state==='downloading'?`Downloading update ${state.percent}%`:'Update available';
  if(dialog.open)draw();
  if(openWhenChecked){openWhenChecked=false;show();}
 });
}
