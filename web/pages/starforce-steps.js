// Star Force steps toward an item's target: consecutive stars of one item's plan that sit
// next to each other in the list read as one upgrade.
const CAPPED_NOTE='Ranked no higher than the previous step, which must be done first.';
const PLAN_TOTALS=['expected_mesos','expected_rolls','expected_booms'];
// R is the next star of PREV's Star Force plan for the same item.
export const continues=(prev,r)=>prev.kind==='starforce'&&r.kind==='starforce'&&r.slot===prev.slot&&r.strategy===prev.strategy&&r.current_stars===prev.target_stars;
const isTargetStep=r=>r.kind==='starforce'&&r.steps>1;
const sum=(rows,key)=>rows.reduce((total,r)=>total+(r[key]??0),0);
const cappedNotes=r=>r.capped?[CAPPED_NOTE]:[];

// A step shown alone names its place in the climb.
function single(r){
 return {...r,notes:[...r.notes,`Step ${r.step} of ${r.steps} toward ${r.chain_target}★.`,...cappedNotes(r)]};
}
function mergeRun(run){
 if(run.length===1)return single(run[0]);
 const first=run[0],last=run[run.length-1];
 const stat_gains={};
 for(const r of run)for(const [key,value] of Object.entries(r.stat_gains||{}))stat_gains[key]=(stat_gains[key]||0)+value;
 const plan=new Map();
 for(const r of run)for(const s of r.starforce_plan||[])if(!plan.has(s.star)||plan.get(s.star).recovery)plan.set(s.star,s);
 const totals=rows=>Object.fromEntries(PLAN_TOTALS.map(key=>[key,sum(rows,key)]));
 const custom=first.custom_plan&&{...first.custom_plan,...totals(run.map(r=>r.custom_plan??{}))};
 const expected_fd=sum(run,'expected_fd'),combined=totals(run),fd_per_billion=expected_fd/combined.expected_mesos*1e9;
 const toward=first.chain_target>last.target_stars?` of ${first.steps} toward ${first.chain_target}★`:'';
 return {
  ...first,
  ...combined,
  target_stars:last.target_stars,
  stat_gains,
  expected_fd,
  custom_plan:custom,
  starforce_plan:[...plan.values()].sort((a,b)=>a.star-b.star).map(s=>({...s,recovery:s.star<first.current_stars})),
  raw_fd_per_billion:fd_per_billion,
  fd_per_billion,
  goal:`Reach ${last.target_stars} stars · ${String(first.strategy_label||'').toLowerCase()}`,
  examples:Object.entries(stat_gains).map(([key,value])=>`${key}: +${value}`),
  // Every step of one plan shares its notes; only the first step's own rank cap matters,
  // since later steps were capped by steps inside this row.
  notes:[
   `Combines steps ${first.step}–${last.step}${toward} (${run.map(r=>`${r.current_stars}→${r.target_stars}★`).join(', ')}), which rank next to each other. FD per 1B is their combined average; the position comes from the first step.`,
   ...first.notes,
   ...cappedNotes(first),
  ],
 };
}
export function mergeSequential(rows){
 const out=[];let run=[];
 const flush=()=>{if(run.length)out.push(mergeRun(run));run=[];};
 for(const r of rows){
  if(run.length&&continues(run[run.length-1],r)){run.push(r);continue;}
  flush();
  if(isTargetStep(r))run=[r];else out.push(r);
 }
 flush();
 return out;
}
