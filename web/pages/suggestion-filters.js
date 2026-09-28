export const filters = [
 ['best','Best per item - meso plan','One recommendation per equipment slot, ranked by FD per meso. Star Force uses its least-meso plan; other targets for that slot are hidden.'],
 ['best-booms','Best per item - low-boom plan','One recommendation per equipment slot. Star Force uses its fewest-booms plan; other targets for that slot are hidden.'],
 ['all-mesos','All targets - meso optimized','Every flame/cube target, plus the least-meso Star Force plan for each item. Multiple recommendations per slot are shown.'],
 ['all-booms','All targets - boom optimized','Every flame/cube target, plus the fewest-booms Star Force plan for each item. Multiple recommendations per slot are shown.'],
 ['all','All options','Every modeled target and both Star Force strategies. Several entries may refer to the same equipment slot.'],
 ['Black Flame','Black Flames','Only improving flames, evaluated with Scouter stat efficiencies.'],
 ['Bright','Bright cubes','Only Bright cube targets.'],['Glowing','Glowing cubes','Only Glowing cube targets.'],
 ['Star Force','Star Force','Next-star upgrades only, including least-meso and fewest-booms plans.']
];
export function selectSuggestionRows(rows,filter,scope=null){
 const best=['best','best-booms'].includes(filter);
 const strategy=['best-booms','all-booms'].includes(filter)?'booms':'mesos';
 const restrictPlan=best||['all-mesos','all-booms'].includes(filter);
 let selected=rows.filter(r=>(!scope||r.kind===scope)&&(best||filter.startsWith('all')||r.method===filter)&&(!restrictPlan||r.kind!=='starforce'||r.strategy===strategy||r.strategy==='custom'));
 if(best){const seen=new Set();selected=selected.filter(r=>!seen.has(r.slot)&&seen.add(r.slot));}
 return selected;
}
