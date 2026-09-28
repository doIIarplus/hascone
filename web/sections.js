import {api} from './api.js';
import {toast} from './ui.js';
const selector='.analysis-panel,.detail-panel,.profile-costs,.sc-site-stats,.sc-site-section,.sc-boss-section,#sc-output > .card:not(details),#sc-panel-efficiencies,[data-collapsible]';
const controllers=new WeakMap();
let saved={},writes=Promise.resolve();
function read(){return saved;}
function remember(key,collapsed){
 saved[key]=collapsed;
 writes=writes.catch(()=>{}).then(()=>api.post('/api/ui/sections',{key,collapsed})).catch(error=>toast('Section preference was not saved: '+error.message));
}
export function revealSection(element){
 for(let panel=element;panel;panel=panel.parentElement){const control=controllers.get(panel);if(control)control(false,true);}
}
export function mountSections(view){
 let scheduled=false;
 const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;queueMicrotask(refresh);}});
 function refresh(){
  scheduled=false;observer.disconnect();
  for(const panel of view.querySelectorAll(selector)){
   const heading=panel.querySelector(':scope > h2,:scope > h3,:scope > .card-head,:scope > header h2,:scope > .sc-site-heading h3,:scope > .sc-section-title h2,:scope > .sc-boss-banner h2');
   if(!heading||heading.querySelector('input,select,a'))continue;
   if(heading.querySelector(':scope > .section-toggle')){const existing=controllers.get(panel);if(existing)existing(read()[existing.key]===true);continue;}
   const title=heading.textContent.trim();if(!title)continue;
   const page=view.dataset.sectionPage||'home',tab=panel.closest('[role=tabpanel]')?.id||'';
   const identity=panel.matches('.detail-panel')?'selected-equipment':panel.dataset.collapsible||title;
   const key=[page,tab,identity].join('/');
   let head=heading;while(head.parentElement!==panel)head=head.parentElement;
   head.dataset.collapseHeading='';
   const button=document.createElement('button');button.type='button';button.className='section-toggle';
   while(heading.firstChild)button.append(heading.firstChild);
   heading.append(button);panel.classList.add('collapsible-section');
   function apply(collapsed,persist=false){
    panel.classList.toggle('section-collapsed',collapsed);
    button.setAttribute('aria-expanded',String(!collapsed));
    button.title=(collapsed?'Expand ':'Collapse ')+title;
    if(persist)remember(key,collapsed);
   }
   const control=(collapsed,persist)=>apply(collapsed,persist);control.key=key;controllers.set(panel,control);
   apply(read()[key]===true);
   button.onclick=()=>{
    const scroller=document.querySelector('#page-scroll'),top=button.getBoundingClientRect().top;
    apply(!panel.classList.contains('section-collapsed'),true);
    if(scroller)scroller.scrollTop+=button.getBoundingClientRect().top-top;
   };
  }
  observer.observe(view,{subtree:true,childList:true});
 }
 view.addEventListener('invalid',event=>revealSection(event.target),true);
 refresh();
 api.get('/api/ui/sections').then(values=>{saved={...values,...saved};refresh();}).catch(error=>toast('Could not load section preferences: '+error.message));
 return()=>observer.disconnect();
}
