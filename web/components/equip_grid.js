import {escapeHtml as esc} from '../ui.js';

export const slotLabel=s=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());

// The in-game equipment window: portrait plus one button per slot at its layout position.
// Pages add their own slot classes, badges and disabled slots; markup and CSS stay shared.
export function equipGrid({characterId,name,slots,equipment,captured,selected,portraitExtra='',slotClass=()=>'',badge=()=>'',disabled=()=>''}){
 return `<div class="equip-grid"><img class="portrait" src="/api/characters/${characterId}/portrait" alt="${esc(name)}">${portraitExtra}${Object.entries(slots).map(([key,pos])=>{const saved=equipment[key],off=disabled(key);return `<button class="equip-slot ${key===selected?'selected':''} ${slotClass(key,saved)}" data-slot="${key}" style="left:${pos.x}px;top:${pos.y}px" aria-label="${esc(slotLabel(key))}"${off?` aria-disabled="true" title="${esc(off)}"`:''}>${saved?.name||saved?.occupied?`<img src="/api/characters/${characterId}/equipment/${key}/icon?t=${encodeURIComponent(saved?.updated||captured||'')}" alt="${esc(slotLabel(key))}">`:esc(slotLabel(key))}${badge(key,saved)}</button>`}).join('')}</div>`;
}
