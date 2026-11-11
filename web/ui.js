export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
let timer;
export function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.classList.add('visible');clearTimeout(timer);timer=setTimeout(()=>el.classList.remove('visible'),6000);}
// A whole-number field (no step, or a whole step) at or over its max shows the max while typing.
export function capWholeNumber(el){
 if(el?.tagName!=='INPUT'||el.type!=='number'||el.max==='')return false;
 const step=el.getAttribute('step');
 if(step!==null&&!Number.isInteger(Number(step)))return false;
 const max=Number(el.max);
 if(!Number.isFinite(max)||!(el.valueAsNumber>max))return false;
 el.value=String(max);
 return true;
}
// Runs before each field's own input handlers, so they only ever see the capped value.
export function capNumbersWhileTyping(root=document){root.addEventListener('input',e=>capWholeNumber(e.target),true);}
