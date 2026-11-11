import {continues,mergeSequential} from './starforce-steps.js';
export const filters = [
 ['best','Best per item - meso plan','One recommendation per equipment slot, ranked by FD per meso. Star Force uses its least-meso plan; steps toward an item’s target that rank together are shown as one row.'],
 ['best-booms','Best per item - low-boom plan','One recommendation per equipment slot. Star Force uses its fewest-booms plan; steps toward an item’s target that rank together are shown as one row.'],
 ['all-mesos','All targets - meso optimized','Every flame/cube target, plus the least-meso Star Force plan for each item. Multiple recommendations per slot are shown.'],
 ['all-booms','All targets - boom optimized','Every flame/cube target, plus the fewest-booms Star Force plan for each item. Multiple recommendations per slot are shown.'],
 ['all','All options','Every modeled target and both Star Force strategies. Several entries may refer to the same equipment slot.'],
 ['Black Flame','Black Flames','Only improving flames, evaluated with Scouter stat efficiencies.'],
 ['Bright','Bright cubes','Only Bright cube targets.'],['Glowing','Glowing cubes','Only Glowing cube targets.'],
 ['Star Force','Star Force','The next star, or every star up to the item\'s target, including least-meso and fewest-booms plans.']
];
export function selectSuggestionRows(rows,filter,scope=null){
 const best=['best','best-booms'].includes(filter);
 const strategy=['best-booms','all-booms'].includes(filter)?'booms':'mesos';
 const restrictPlan=best||['all-mesos','all-booms'].includes(filter);
 let selected=rows.filter(r=>(!scope||r.kind===scope)&&(best||filter.startsWith('all')||r.method===filter)&&(!restrictPlan||r.kind!=='starforce'||r.strategy===strategy||r.strategy==='custom'));
 // One row per item: its top-ranked upgrade, plus any target steps that directly follow it,
 // so another item never lands between two of one item's rows.
 if(best){
  const seen=new Set(),kept=[];
  for(const r of selected){
   if(!seen.has(r.slot)){seen.add(r.slot);kept.push(r);}
   else if(kept.length&&continues(kept[kept.length-1],r))kept.push(r);
  }
  selected=kept;
 }
 return mergeSequential(selected);
}

