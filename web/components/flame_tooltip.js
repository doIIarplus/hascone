import { escapeHtml } from '../ui.js';
import { createEquipmentTooltip } from './equipment_tooltip.js';

export function flameMarkup(item) {
  const heading=`<strong class="cf-flame-name">${escapeHtml(item.name || 'Unidentified item')}</strong><span class="cf-flame-heading">Bonus Stats</span>`;
  if(item.flameable===false)return heading+'<p class="fl-help">This item cannot be flamed.</p>';
  if(item.status!=='scanned' || !item.stats?.length)return heading+`<p class="fl-help">Flame stats not scanned yet.</p>`;
  const lines=item.stats.map(stat=>`<li><span>${escapeHtml(stat.name)}</span><strong>+${escapeHtml(stat.value)}${stat.percent?'%':''}</strong></li>`).join('');
  const score=item.flame_score!=null && String(item.flame_score).trim() && Number.isFinite(Number(item.flame_score))
    ? `<div class="cf-flame-total"><span>Flame Score</span><strong>${new Intl.NumberFormat(undefined,{minimumFractionDigits:1,maximumFractionDigits:1}).format(Number(item.flame_score))}</strong></div>` : '';
  return `${heading}<ul class="ce-lines cf-flame-lines">${lines}</ul>${score}`;
}

export function createFlameTooltip(root, getItem) {
  return createEquipmentTooltip(root, getItem, {markup:flameMarkup, className:'cf-flame-tooltip'});
}
