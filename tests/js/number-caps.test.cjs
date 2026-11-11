const {test}=require('node:test');
const assert=require('node:assert/strict');
const field=(value,{max='20',step=null,type='number'}={})=>({tagName:'INPUT',type,max,value:String(value),get valueAsNumber(){return this.value===''?NaN:Number(this.value);},getAttribute:name=>name==='step'?step:null});
test('whole-number fields snap down to their max while typing',async()=>{
 const {capWholeNumber}=await import('../../web/ui.js');
 for(const [value,step] of [['25',null],['21','1'],['999','5']]){
  const el=field(value,{step});
  assert.equal(capWholeNumber(el),true);
  assert.equal(el.value,'20');
 }
});
test('values within the cap, blanks and non-whole fields are left alone',async()=>{
 const {capWholeNumber}=await import('../../web/ui.js');
 const cases=[field('20'),field('2'),field(''),field('25',{max:''}),field('80',{max:'75',step:'0.01'}),field('80',{max:'75',step:'any'}),field('25',{type:'text'})];
 for(const el of cases){const before=el.value;assert.equal(capWholeNumber(el),false);assert.equal(el.value,before);}
});
