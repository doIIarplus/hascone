const fmt = v => v.toLocaleString(undefined,{maximumFractionDigits:2});

export function attackBossRatio(e = {}) {
  const attack=e.atkPereff1, boss=e.dmgeff1;
  if(![attack,boss].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>0))return null;
  // Scouter's 40/45% line comparison accounts for removing an existing line.
  const equivalent=(amount,line)=>1/(1-line*attack)-1>=amount*boss && 1/(1-amount*boss)-1>=line*attack
    ? line : Math.round(amount*boss/attack*10)/10;
  return {bossPerAttack:attack/boss,attackPer40:equivalent(40,12),attackPer45:equivalent(45,13)};
}

export function efficiencySummary(e) {
  const ratio=attackBossRatio(e);
  return `<div class="sc-result-tools"><section class="card sc-ratio"><span class="sc-eyebrow">ATT / MATT ↔ BOSS DAMAGE</span>
    ${ratio?`<strong>1% ATT ≈ ${fmt(ratio.bossPerAttack)}% boss</strong><div class="sc-ratio-lines"><span>40% boss <b>≈ ${fmt(ratio.attackPer40)}% ATT</b></span><span>45% boss <b>≈ ${fmt(ratio.attackPer45)}% ATT</b></span></div>`:'<p class="sub">Attack/boss efficiency is unavailable in this saved result.</p>'}
    <small>Based on this calculation’s stats and buffs. Use Simulator for a complete item swap.</small></section>
    <section class="card sc-quick-fd"><label for="sc-quick-fd-value">Compare a custom FD gain or loss</label><div><input class="input" id="sc-quick-fd-value" type="number" min="-99.99" max="75" step="0.01" value="3" aria-label="Custom final damage change percent"><span>% FD</span><button class="btn btn-primary" id="sc-quick-fd-run">Compare FD</button></div><small>For example, +3 means 3% more damage. Opens an FD-only comparison with updated HEXA and boss cuts.</small></section></div>`;
}
