import { potentialMarkup } from './potential.js';
import { createEquipmentTooltip } from './equipment_tooltip.js';

export function createPotentialTooltip(root, getItem) {
  return createEquipmentTooltip(root, getItem, {
    markup: potentialMarkup,
    className: 'ce-potential-tooltip',
    rank: item => ['Rare','Epic','Unique','Legendary'].includes(item.potential?.rank) ? item.potential.rank.toLowerCase() : '',
  });
}
