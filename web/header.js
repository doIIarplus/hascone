// Single-row headers stay visible; narrow layouts can collapse their second row.
export function mountHeader(){
 const header=document.querySelector('.app-header');
 const scroller=document.querySelector('#page-scroll');
 const settings=document.querySelector('#settings-menu');
 let hovered=header.matches(':hover'),keyboard=false,frame=0;
 function update(){
  frame=0;
  const focused=keyboard&&header.contains(document.activeElement);
  const narrow=window.matchMedia('(max-width:1250px)').matches;
  header.classList.toggle('is-collapsed',narrow&&scroller.scrollTop>8&&!hovered&&!focused&&!settings.open);
 }
 function schedule(){if(!frame)frame=requestAnimationFrame(update);}
 function measure(){
  // Measure the expanded form on resize, even while the compact form is showing.
  const collapsed=header.classList.contains('is-collapsed');
  header.classList.remove('is-collapsed');
  document.documentElement.style.setProperty('--header-expanded-height',header.getBoundingClientRect().height+'px');
  header.classList.toggle('is-collapsed',collapsed);
  update();
 }
 header.addEventListener('pointerenter',()=>{hovered=true;update();});
 header.addEventListener('pointerleave',()=>{hovered=false;update();});
 document.addEventListener('keydown',e=>{if(e.key==='Tab'){keyboard=true;schedule();}});
 document.addEventListener('pointerdown',()=>{keyboard=false;schedule();});
 header.addEventListener('focusin',schedule);
 header.addEventListener('focusout',schedule);
 settings.addEventListener('toggle',schedule);
 scroller.addEventListener('scroll',schedule,{passive:true});
 window.addEventListener('resize',measure);
 document.fonts?.ready.then(measure);
 measure();
}
