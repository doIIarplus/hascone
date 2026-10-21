import {api} from './api.js';

// Completion belongs to the app, not the currently mounted page. Remember what
// was opened so polling (or reloading later) doesn't keep stealing navigation.
export function watchScouterCompletion(openResult){
 const key='hascone.scouter.opened-result';
 let opened=sessionStorage.getItem(key),checking=false,opening=false;
 async function accept(state){
  if(opening||state.active||state.status!=='complete'||!state.profile||!state.result_id||
     ['connection','simulation','suggestions'].includes(state.kind))return;
  const identity=JSON.stringify([state.profile,state.result_id]);
  if(identity===opened)return;
  opening=true;
  try{
   if(await openResult(state.profile,state.result_id)===false)return;
   opened=identity;sessionStorage.setItem(key,identity);
  }finally{opening=false;}
 }
 async function check(){
  if(checking)return;
  checking=true;
  try{await accept(await api.get('/api/scouter/state'));}
  catch{/* Retry reads and navigation after transient failures. */}
  finally{checking=false;}
 }
 const completed=e=>{void accept(e.detail).catch(()=>{});};
 window.addEventListener('scouter-calculated',completed);
 const timer=setInterval(check,1200);void check();
 return ()=>{clearInterval(timer);window.removeEventListener('scouter-calculated',completed);};
}
