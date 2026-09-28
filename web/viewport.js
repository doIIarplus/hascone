export const pageScroller=()=>document.querySelector('#page-scroll')||document.scrollingElement;
// Keep in-place updates from moving the viewport or scrolling a restored control.
export function keepViewport(root,update){
 const x=pageScroller().scrollLeft,y=pageScroller().scrollTop;
 const focus=root.contains(document.activeElement)?document.activeElement.id:null;
 const height=root.style.minHeight;
 root.style.minHeight=root.getBoundingClientRect().height+'px';
 try{return update();}
 finally{
  root.style.minHeight=height;
  if(focus)root.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});
  pageScroller().scrollTo({left:x,top:y,behavior:'instant'});
 }
}
