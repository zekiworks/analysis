'use strict';
const HildeI18n=(()=>{
 const words=window.hildeTurkish;
 // English display names that differ from the section keys in the data (Ümit #13926: one naming pattern, so
 // 'Toolbench' shows as 'Tool Calling'; links and data keep 'Toolbench')
 // Ümit #14939: the four Turkish Science tables say so beside their English versions; their track keys stay as they are
 const english={'Toolbench':'Tool Calling','Reading & Grammar':'Languages'};  // Ümit #16460: 'Languages'
 function rename(text){
  if(!text||!text.trim())return text;
  const base=text.trim();
  if(Object.hasOwn(english,base))return text.replace(base,()=>english[base]);
  for(const separator of [' | ',' · ',' / ',', ']){
   if(base.includes(separator))return text.split(separator).map(rename).join(separator);
  }
  return text;
 }
 const originals=new WeakMap();
 const attributes=new WeakMap();
 const skip='script,style,textarea,svg,datalist,[data-verbatim],.modelText,.initials,[data-ui]';
 function translate(text){
  if(!text||!text.trim())return text;
  const base=text.trim();
  if(Object.hasOwn(words,base))return text.replace(base,()=>words[base]);
  for(const separator of [' | ',' · ',' / ',', ']){
   if(base.includes(separator))return text.split(separator).map(translate).join(separator);
  }
  let m=base.match(/^(Selected records|Selected|X draft) (\(\d+\)|\d.*)$/);
  if(m)return translate(m[1])+' '+m[2];
  m=base.match(/^League (\d+)$/);if(m)return 'Lig '+m[1];
  m=base.match(/^(.*?) sections$/);if(m)return translate(m[1])+' bölümleri';
  m=base.match(/^(.*?) (select for comparison|remove from selection|details)$/);if(m)return m[1]+' '+({'select for comparison':'kaydını karşılaştırmaya seç','remove from selection':'kaydını seçimden çıkar',details:'ayrıntıları'})[m[2]];
  m=base.match(/^(.*?) (records|questions|positions|decisions|distinct test positions|matched position pairs|answer pairs|questions per repeat|points|run average)$/);if(m)return m[1]+' '+(words[m[2]]||m[2]);
  m=base.match(/^Published improvement verdict: (Yes|No)\.$/);if(m)return 'Yayımlanmış gelişim kararı: '+translate(m[1])+'.';
  m=base.match(/^(.*?) ([\d.,]+.*)\. Observation reported by the source\.$/);if(m)return translate(m[1])+' '+m[2]+'. Kaynakta bildirilen gözlem.';
  return text;
 }
 function localize(root,locale){
  if(!root)return;
  const tr=locale==='tr';
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  for(let n=walker.nextNode();n;n=walker.nextNode()){
   if(!n.textContent.trim()||n.parentElement?.closest(skip))continue;
   const prev=originals.get(n);
   const input=prev&&n.data===prev.output?prev.input:n.data;
   const output=tr?translate(input):rename(input);
   if(n.data!==output)n.data=output;
   originals.set(n,{input,output});
  }
  for(const el of root.querySelectorAll('[aria-label],[placeholder],[title]')){
   if(el.closest('[data-verbatim],svg,[data-ui]'))continue;
   const prev=attributes.get(el)||{};
   for(const key of ['aria-label','placeholder','title']){
    const current=el.getAttribute(key);if(!current)continue;
    const input=prev[key]&&prev[key].output===current?prev[key].input:current;
    const output=tr?translate(input):rename(input);
    if(current!==output)el.setAttribute(key,output);
    prev[key]={input,output};
   }
   attributes.set(el,prev);
  }
 }
 return {translate,localize};
})();
