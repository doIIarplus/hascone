import { escapeHtml } from '../ui.js';

function rankMarkup(potential) {
  const rank = potential?.rank;
  return ['Rare','Epic','Unique','Legendary'].includes(rank) ? `<span class="ce-potential-rank ce-rank-${rank.toLowerCase()}">${rank}</span>` : '';
}
export function potentialMarkup(item) {
  const p = item?.potential;
  if (item?.cubeable === false) return '<p class="fl-help">This item cannot be cubed.</p>';
  if (p?.status !== 'scanned') return '<p class="fl-help">Potential not scanned yet.</p>';
  const ranks = ['Rare','Epic','Unique','Legendary'];
  const completeTiers = Array.isArray(p.line_tiers) && p.line_tiers.length === p.lines?.length && p.line_tiers.every(tier=>ranks.includes(tier));
  const primes = completeTiers ? p.line_tiers.filter(tier=>tier===p.rank).length : null;
  const primeLabel = primes === 3 ? 'Triple prime' : primes === 2 ? 'Double prime' : `${primes} prime line${primes===1?'':'s'}`;
  return `${rankMarkup(p)}${completeTiers?`<span class="ce-prime-count">${primeLabel} · ${primes}/${p.lines.length}</span>`:'<span class="fl-help">Line tiers not recorded in this older scan. Scan potentials to read them.</span>'}<ul class="ce-lines">${(p.lines || []).map((line,index)=>{
    const tier = completeTiers ? p.line_tiers[index] : null;
    const description = tier ? tier+' line'+(tier===p.rank?' · prime':'') : 'Line tier unknown';
    return `<li>${tier?`<span class="ce-line-tier ce-rank-${tier.toLowerCase()}" title="${description}" aria-label="${description}">${tier[0]}</span>`:''}<span>${escapeHtml(line)}</span></li>`;
  }).join('')}</ul>`;
}
