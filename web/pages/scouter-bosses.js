import { escapeHtml as esc } from '../ui.js';

const DIFFICULTIES = new Set(['Easy','Normal','Hard','Chaos','Extreme','Destiny','Champion']);
const number = value => Number(value).toLocaleString(undefined,{maximumFractionDigits:0});

function bossCard(boss, before) {
  const difficulty = DIFFICULTIES.has(boss.difficulty) ? boss.difficulty : 'Normal';
  const percent = Number(boss.percent);
  const minCut = boss.reference === 'party' ? `${boss.party_limit}-player min` : 'Solo min';
  const tone = !boss.can_enter ? 'locked' : percent >= 110 ? 'ready' : percent >= 90 ? 'close' : 'below';
  const tooltip = [`${boss.difficulty} ${boss.boss}`,`Boss-adjusted HEXA: ${number(boss.boss_hexa_score)}`,`Entry level: ${boss.entry_level}`,
    ...(boss.thresholds || []).map(t=>`${t.category}: ${t.percent}%`)].join('\n');
  return `<article class="sc-boss-card sc-boss-${difficulty.toLowerCase()} sc-boss-${tone}" title="${esc(tooltip)}">
    <div class="sc-boss-art"><img data-icon="${esc(boss.icon)}" alt="${esc(`${difficulty} ${boss.boss}`)}" width="80" height="80" loading="lazy"></div>
    <div class="sc-boss-name">${esc(boss.boss)}</div><span class="sc-difficulty">${esc(difficulty)}</span>
    <strong class="sc-boss-percent">${esc(boss.display_percent.replace('[Party] ',''))}</strong>
    <span class="sc-boss-category">${esc(boss.category)}</span>
    ${before?`<small class="sc-boss-before">Before ${esc(before.display_percent.replace('[Party] ',''))}${before.category!==boss.category?` · ${esc(before.category)}`:''}</small>`:''}
    <div class="sc-boss-meter" aria-hidden="true"><span style="width:${Math.max(0,Math.min(100,percent/90*100))}%"></span></div>
    <small>${esc(minCut)} · 90%</small>${boss.can_enter?'':`<small class="sc-boss-entry">Requires level ${esc(boss.entry_level)}</small>`}
  </article>`;
}

export function renderBossPanels(cuts, filter='relevant', before=null, prefix='sc') {
  const previous=new Map((before?.bosses||[]).map(b=>[b.id,b]));
  if (!cuts?.available) return `<section class="card sc-boss-section"><div class="card-head">Boss minimum cuts & Destiny liberation</div><p class="empty">${esc(cuts?.reason || 'Calculate to see boss and Destiny liberation estimates.')}</p></section>`;
  const destiny = cuts.bosses.filter(b=>b.difficulty==='Destiny').reverse();
  const bosses = cuts.bosses.filter(b=>filter==='champion' ? b.difficulty==='Champion' :
    !['Destiny','Champion'].includes(b.difficulty) && (filter==='all' || b.relevant || previous.get(b.id)?.relevant));
  return `<section class="card sc-boss-section sc-destiny-section">
    <div class="sc-boss-banner sc-destiny-banner"><div><span class="sc-eyebrow">LIBERATION</span><h2>Destiny</h2><p>Damage against each liberation boss’s clear threshold.</p></div><span class="sc-banner-tag">SOLO</span></div>
    <div class="sc-boss-grid sc-destiny-grid" id="${prefix}-destiny-grid">${destiny.map(b=>bossCard(b,previous.get(b.id))).join('') || '<p class="empty">No Destiny estimates available.</p>'}</div>
  </section>
  <section class="card sc-boss-section"><div class="sc-boss-banner"><div><span class="sc-eyebrow">BOSSING</span><h2>Minimum cuts</h2><p>Clear estimates for the stats saved in this calculation.</p></div>
    <label class="sc-boss-filter"><select class="input" id="${prefix}-boss-filter" aria-label="Bosses to display">${[['relevant','Near my range'],['all','All bosses'],['champion','Legion Champion']].map(([v,l])=>`<option value="${v}" ${filter===v?'selected':''}>${l}</option>`).join('')}</select></label></div>
    <div class="sc-boss-grid sc-boss-scroll" id="${prefix}-boss-grid">${bosses.map(b=>bossCard(b,previous.get(b.id))).join('') || '<p class="empty">No bosses in this range. Choose All bosses to see the full list.</p>'}</div>
    <details class="sc-boss-help"><summary>How to read these estimates</summary><p>These percentages compare modeled damage with Scouter’s reference, not the chance of clearing. Solo-reference bosses reach the solo minimum at 90%. Party-reference bosses use the labeled party size at 90%; hover a card for its other party thresholds. Mechanics and execution still matter.</p><p>GMS Reboot table · ${esc(cuts.snapshot)} · ${esc(cuts.minutes)}-minute potion correction. Uses the saved level, Arcane/Sacred Force, buffs and API damage.</p></details>
  </section>`;
}
