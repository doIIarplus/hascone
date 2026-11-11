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
const targetStep=r=>r.kind==='starforce'&&r.steps>1;
// R is the next star of PREV's Star Force plan for the same item.
const continues=(prev,r)=>prev.kind==='starforce'&&r.kind==='starforce'&&r.slot===prev.slot&&r.strategy===prev.strategy&&r.current_stars===prev.target_stars;
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
   else if(targetStep(r)&&kept.length&&continues(kept[kept.length-1],r))kept.push(r);
  }
  selected=kept;
 }
 return mergeSequential(selected);
}

const sum=(rows,key)=>rows.reduce((total,r)=>total+(r[key]??0),0);
function mergeRun(run){
 if(run.length===1)return run[0];
 const first=run[0],last=run[run.length-1];
 const stat_gains={};
 for(const r of run)for(const [key,value] of Object.entries(r.stat_gains||{}))stat_gains[key]=(stat_gains[key]||0)+value;
 const plan=new Map();
 for(const r of run)for(const s of r.starforce_plan||[])if(!plan.has(s.star)||plan.get(s.star).recovery)plan.set(s.star,s);
 const custom=first.custom_plan&&{...first.custom_plan,...Object.fromEntries(['expected_mesos','expected_rolls','expected_booms'].map(key=>[key,run.reduce((t,r)=>t+(r.custom_plan?.[key]??0),0)]))};
 const expected_fd=sum(run,'expected_fd'),expected_mesos=sum(run,'expected_mesos');
 const toward=first.chain_target>last.target_stars?` of ${first.steps} toward ${first.chain_target}★`:'';
 return {
  ...first,
  target_stars:last.target_stars,
  merged_steps:run.map(r=>`${r.current_stars}→${r.target_stars}`),
  step_range:[first.step,last.step],
  stat_gains,
  expected_fd,
  expected_mesos,
  expected_rolls:sum(run,'expected_rolls'),
  expected_booms:sum(run,'expected_booms'),
  custom_plan:custom,
  starforce_plan:[...plan.values()].sort((a,b)=>a.star-b.star).map(s=>({...s,recovery:s.star<first.current_stars})),
  raw_fd_per_billion:expected_fd/expected_mesos*1e9,
  fd_per_billion:expected_fd/expected_mesos*1e9,
  goal:`Reach ${last.target_stars} stars · ${String(first.strategy_label||'').toLowerCase()}`,
  examples:Object.entries(stat_gains).map(([key,value])=>`${key}: +${value}`),
  notes:[
   `Combines steps ${first.step}–${last.step}${toward} (${run.map(r=>`${r.current_stars}→${r.target_stars}★`).join(', ')}), which rank next to each other. FD per 1B is their combined average; the position comes from the first step.`,
   // Only the first step's own rank cap matters; later steps were capped by steps inside this row.
   ...new Set([...first.notes,...run.slice(1).flatMap(r=>r.notes).filter(note=>!note.startsWith('Ranked no higher than the previous step'))].filter(note=>!/^Step \d+ of \d+ toward/.test(note))),
  ],
 };
}
// Consecutive stars of one item and plan that sit next to each other in the list read as one upgrade.
export function mergeSequential(rows){
 const out=[];let run=[];
 for(const r of rows){
  const prev=run[run.length-1];
  if(prev&&continues(prev,r))run.push(r);
  else{if(run.length)out.push(mergeRun(run));run=r.kind==='starforce'&&r.steps>1?[r]:[];if(!run.length)out.push(r);}
 }
 if(run.length)out.push(mergeRun(run));
 return out;
}
