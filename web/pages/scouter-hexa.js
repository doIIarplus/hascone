const english = value => typeof value==='string' && /^[\x20-\x7E]+$/.test(value) ? value : '';

export const hexaResources={fragments:'Fragments',sol_erda:'Sol Erda'};

export function resourceOrder(record,resource){
  return record?.hexa_orders?.[resource]?.order||(resource==='fragments'?record?.order:null);
}

export function resourceEfficiency(row,resource){
  const efficiency=Number(row[7]);
  if(row[7]==null||!Number.isFinite(efficiency))return null;
  if(resource!=='sol_erda')return efficiency;
  // Scouter returns FD per 30 fragments even when the route optimizes Sol Erda.
  const sol=Number(row[3]),fragments=Number(row[4]);
  return sol>0&&Number.isFinite(sol)&&fragments>0&&Number.isFinite(fragments)?efficiency*fragments/30/sol:null;
}

export function coreLabel(key='') {
  const stat=/^hexaStat(\d+)$/.exec(key);
  if(stat)return `HEXA Stat ${['','I','II','III'][Number(stat[1])]||stat[1]}`;
  const core=/^(skillCore|masteryCore|reinCore|generalCore)(\d+)$/.exec(key);
  return core?`${{skillCore:'Skill',masteryCore:'Mastery',reinCore:'Boost',generalCore:'Common'}[core[1]]} ${core[2]}`:'HEXA core';
}

export function coreName(core,key) {
  return english(core?.english_title)||english(core?.title)||coreLabel(key);
}

export function levelChange(row) {
  const match=String(row[10]??'').match(/(\d+)\s*→\s*(\d+)/);
  if(match)return `${match[1]} → ${match[2]}`;
  const level=Number(row[1]);
  return Number.isFinite(level)?`Lv. ${level}`:'Upgrade';
}

export function orderContext(order) {
  if(!order)return '';
  const labels={'밸패반영':'Current balance patch','허수아비':'Training dummy','수로':'Culvert','보스':'Boss'};
  return [order.patch,order.standard].filter(Boolean).map(v=>labels[v]||english(v)||'Standard damage model').join(' · ');
}

// Only expose completion for a recognized upgrade from the currently saved level.
export function completionChange(row,values,cores){
 const key=String(row[9]||''),stat=/^hexaStat([1-3])$/.exec(key);
 const transition=String(row[10]||'').match(/(\d+)\s*\u2192\s*(\d+)/);
 if(!transition)return null;
 const from=Number(transition[1]),to=Number(transition[2]);
 if(stat){
  const count=Number(stat[1]);
  return from===0&&to===20&&Number(values['hexa.hexaStat']||0)===count-1?{path:'hexa.hexaStat',value:count,stat:true}:null;
 }
 if(!/^(skillCore|masteryCore|reinCore|generalCore)\d+$/.test(key)||!cores[key]?.url||to<=from||to>30||Number(values['hexa.'+key])!==from)return null;
 return {path:'hexa.'+key,value:to,stat:false};
}
