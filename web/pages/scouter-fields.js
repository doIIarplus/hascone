// Explicit GMS manual-form controls, in website order. Never enumerate API keys.
// https://maplescouter.com/en/input — inspected 2026-09-15.
export const rings = [
  ['restraintRing','Ring of Restraint','restraint'],
  ['weaponRing','Weapon Jump Ring','weapon'],
  ['continuosRing','Continuous Ring','continuos'],
];
export const buffs = [
  ['sayram','Sayram’s Elixir','sayram'], ['collector','Collector’s Elixir','collector'],
  ['buff275','Honor Elixir','buff300'], ['heroesHawl','Echo of Hero','hero'],
  ['unionsPower','Legion’s Might','union'], ['urus','Ursus buff','urus'],
  ['extreme','Extreme potion','extreme'], ['superPower','Super Power','superpower'],
  ['additional1','VIP Buff','vipbuff'], ['genePass','Genesis Pass · Adversary’s Power','genepass'],
  ['moonshine','Moonshine','moonshine'], ['candy','Candied Apple','candy'],
  ['house','Caretaker’s Support','house'], ['shiningRed','Sparkling Red Star Potion','shiningred'],
  ['bigHero','Advanced Great Hero Potion','bighero'], ['legendHero','Legendary Hero Potion','legendhero'],
  ['jangBi','Advanced Weapon Tempering','jangbi'], ['shiningBlue','Sparkling Blue Star Potion','shiningblue'],
  ['fish','Fish buff','fish'], ['apple','Onyx Apple','apple'], ['tengu','Tengu’s Judgement','tengu'],
  ['authenticDmg','Max-level Sacred Symbols · damage +20%','authentic'],
];
export const guildSkills = [
  ['noblessBoss','Guild skill · boss damage','noblessboss',0],
  ['noblessIgnore','Guild skill · ignore defense','noblessignore',3],
  ['noblessDmg','Guild skill · damage','noblessdam',1],
  ['noblessCriDmg','Guild skill · critical damage','noblesscridam',2],
];
export const champions = [
  ['championAll','All stat / HP level'], ['championAtk','Attack / M.Attack level'],
  ['championBoss','Boss damage level'], ['championCriDmg','Critical damage level'],
  ['championIgnore','Ignore defense level'],
];
export const links = [
  ['kadena','Cadena',3], ['illium','Illium',3], ['ark','Ark',3], ['kain','Kain',3],
  ['magician','Explorer Magician',9], ['thief','Explorer Thief',9], ['angel','Angelic Buster',3],
  ['kanna','Kanna',3], ['mukhyun','Mo Xuan',3], ['mihile','Mihile',3,'Mihile'],
  ['kaiser','Kaiser',3,'Kaiser'], ['hoyoung','Hoyoung',3],
];
export const hexaOrder = ['masteryCore1','masteryCore2','masteryCore3','masteryCore4',
  'skillCore1','skillCore2','skillCore3','reinCore1','reinCore2','reinCore3','reinCore4','generalCore2','generalCore3'];
export const exclusiveBuffs = [
  ['bigHero','legendHero','legendHp','jangBi','shiningBlue'],
  ['fish','rebootAtkPotion','dragonsMeal','cake','apple','tengu','whiteBear'],
];

// The site's all-select preset chooses compatible buffs, not every checkbox.
export function buffPreset(enabled, demonAvenger) {
  const result = {};
  for (const [key] of buffs) result[`doping.${key}`] = false;
  for (const group of exclusiveBuffs) for (const key of group) result[`doping.${key}`] = false;
  for (const [key,,,index] of guildSkills) {
    result[`doping.${key}`] = enabled;
    result[`doping.nobless.${index}`] = enabled ? '15' : '0';
  }
  for (const [key] of champions) result[`doping.${key}`] = enabled ? '5' : '0';
  result['doping.statPotion'] = enabled;
  result['doping.stat'] = enabled ? '30' : '0';
  result['doping.additional2'] = enabled; // Included by the site's preset; no separate control.
  if (enabled) for (const key of ['sayram','collector','buff275','extreme','superPower','unionsPower',
    'urus','heroesHawl','additional1','shiningRed','authenticDmg','apple','candy','house',demonAvenger?'legendHp':'jangBi']) result[`doping.${key}`] = true;
  return result;
}
