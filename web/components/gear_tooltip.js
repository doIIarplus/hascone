import { escapeHtml } from '../ui.js';
import { compactCost } from '../format.js';
import { flameMarkup } from './flame_tooltip.js';
import { potentialMarkup } from './potential.js';
import { createEquipmentTooltip } from './equipment_tooltip.js';

// Star Force, flames and potential together, with the item's combined expected cost.
export const COST_PARTS = ['Star Force', 'Flames', 'Cubes'];
export function costMarkup(combined) {
  if (combined === undefined) return '<p class="fl-help">Calculating expected cost…</p>';
  if (!combined) return '';
  const parts = COST_PARTS.filter(name => name in combined.parts).map(name => [name, combined.parts[name]]).map(([name, mesos]) => `<li><span>${escapeHtml(name)}</span><strong>${compactCost(mesos)}</strong></li>`).join('');
  const missing = combined.missing.length ? `<p class="fl-help">Not included: ${combined.missing.map(escapeHtml).join('; ')}</p>` : '';
  return `<div class="gear-cost"><span class="cf-flame-heading">Expected cost</span><ul class="ce-lines cf-flame-lines">${parts}</ul><div class="cf-flame-total"><span>Combined${combined.missing.length ? ' (partial)' : ''}</span><strong>${compactCost(combined.expected_mesos)}</strong></div>${missing}</div>`;
}

export function gearMarkup(item, combined) {
  const stars = item.starforce?.status === 'scanned' ? `<span class="sub">${item.starforce.stars}★</span>` : '';
  return `${flameMarkup(item).replace('</strong>', `</strong>${stars}`)}<div class="gear-potential">${potentialMarkup(item)}</div>${costMarkup(combined)}`;
}

export function createGearTooltip(root, getItem, getCombined) {
  return createEquipmentTooltip(root, slot => {
    const item = getItem(slot);
    return item && { ...item, slot };
  }, {
    markup: item => gearMarkup(item, getCombined(item.slot)),
    className: 'ce-potential-tooltip',
    rank: item => ['Rare','Epic','Unique','Legendary'].includes(item.potential?.rank) ? item.potential.rank.toLowerCase() : '',
  });
}
