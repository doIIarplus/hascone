import {escapeHtml as esc} from './ui.js';
export function downloadScouterPreset(preset){
 const filename=`maplescouter-${preset.label.replace(/[^a-zA-Z0-9_-]/g,'_')}.json`;
 const url=URL.createObjectURL(new Blob([JSON.stringify(preset,null,2)],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),60000);
 const count=value=>value&&typeof value==='object'?Object.values(value).reduce((sum,v)=>sum+count(v),0):value===''?1:0;
 const missing=count(preset.data);
 const dialog=document.createElement('dialog');dialog.className='sc-export-help';
 dialog.innerHTML=`<h2>Import into MapleScouter</h2><p>Preset: <strong>${esc(filename)}</strong></p><ol><li>On MapleScouter, choose <strong>Recall Saved Preset</strong>.</li><li>Choose the JSON file import option and select the downloaded file.</li><li>Load the imported preset to fill the form.</li></ol><p class="sub">${missing?`${missing} fields are blank. Fill them in before calculating.`:'Your current saved inputs are included.'} Review the imported values and confirm GMS / Reboot before calculating.</p><div class="actions"><a class="btn btn-primary" href="https://maplescouter.com/en/input" target="_blank" rel="noopener noreferrer">Open MapleScouter</a><button class="btn" data-export-close>Done</button></div>`;
 document.body.append(dialog);dialog.showModal();
 const close=()=>{dialog.close();dialog.remove();};
 dialog.querySelector('[data-export-close]').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
 window.open('https://maplescouter.com/en/input','_blank','noopener,noreferrer');
}
