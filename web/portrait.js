import {api} from './api.js';
import {escapeHtml as esc,toast} from './ui.js';

const ICON='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/></svg>';

// A small button at a sprite's bottom-left that fetches the latest character image from Nexon.
export const refreshButton=(id,name)=>`<button class="portrait-refresh" type="button" data-refresh-portrait="${esc(id)}" title="Refresh character image from Nexon" aria-label="Refresh ${esc(name)}'s character image">${ICON}</button>`;

async function refresh(button){
 const id=button.dataset.refreshPortrait,path=`/api/characters/${encodeURIComponent(id)}/portrait`;
 button.disabled=true;button.classList.add('is-busy');
 try{
  await api.post(path);
  // Reload every copy of this sprite on the page, bypassing the cached image.
  const fresh=`${path}?v=${Date.now()}`;
  document.querySelectorAll('img').forEach(img=>{if(img.getAttribute('src')?.split('?')[0]===path)img.src=fresh;});
  window.dispatchEvent(new CustomEvent('portrait-refreshed',{detail:id}));
  toast('Character image updated from Nexon.');
 }catch(error){toast(error.message);}
 finally{button.disabled=false;button.classList.remove('is-busy');}
}

document.addEventListener('click',e=>{
 const button=e.target.closest('[data-refresh-portrait]');
 if(!button)return;
 e.preventDefault();e.stopPropagation();
 refresh(button);
});
