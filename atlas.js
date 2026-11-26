'use strict';
const dates=[]; // data/index.json's snapshots, its default first (init)
// All benches last, after the five benches (Ümit #11580).
const sections=['Reading & Grammar','Logic & Math','Backgammon','Answer Check','Toolbench','Science','All benches'];
const pages=['decision-models/','logic/','backgammon/','grading/','tool-calling/','science/results.json','all-benches/'];
const initialTracks=['English Reading','Logic','Risk judgement ranking','Grading','Candidate setups','Maths','Combined'];
const sourceViews=new Map(), guides=new Map();
const data=new Map(), records=new Map(), commits=new Map();
const originSite='https://zekiworks.github.io/analysis/';
const repo='https://github.com/zekiworks/analysis/blob/';
const storeName='hilde.research.atlas.v1';
const $=s=>document.querySelector(s);
const safe=v=>String(v??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const fmtNum=(x,n=1)=>Number(x).toLocaleString(s.ui==='tr'?'tr-TR':'en-US',{maximumFractionDigits:n,minimumFractionDigits:0});
const timed=/^(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})(\d{2})?Z$/; // to the second where two commits share a minute
const dateLabel=v=>timed.test(v||'')?(m=>new Intl.DateTimeFormat(s.ui==='tr'?'tr-TR':'en-GB',{day:'numeric',month:s.ui==='tr'?'long':'short',year:'numeric',timeZone:'UTC'}).format(new Date(m[1]+'T12:00:00Z'))+' · '+m[2]+':'+m[3]+(m[4]?':'+m[4]:'')+' UTC')(timed.exec(v)):v==='2026-11-15'?(s.ui==='tr'?'15 Kasım 2026 · sabah':'15 Nov 2026 · morning'):dates.includes(v)?new Intl.DateTimeFormat(s.ui==='tr'?'tr-TR':'en-US',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(v+'T12:00:00Z')):v;
const has=v=>v!==undefined&&v!==null&&v!=='';
const uniq=a=>Array.from(new Set(a));
const iconShapes={
 check:'<path d="m3 12 5 5L20 5"/><path d="M20 13v7H3V4h10"/>',
 tools:'<path d="M9 7 4 12l5 5m6-10 5 5-5 5"/>',
 book:'<path d="M3 5c3-1 6 0 9 2 3-2 6-3 9-2v14c-3-1-6 0-9 2-3-2-6-3-9-2zM12 7v14"/>',
 layers:'<path d="m12 3 10 5-10 5L2 8zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
 geometry:'<path d="m3 19 8-15 9 15zM7.5 11h8M11 4l2 15"/><circle cx="18" cy="8" r="3"/>',
 board:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18M5 5l2 7 2-7M15 19l2-7 2 7"/>',
 library:'<path d="M3 4h3v16H3zM9 4h3v16H9zM15 5l3-1 4 15-3 1z"/>',
 filters:'<path d="M3 6h5m4 0h9M3 12h11m4 0h3M3 18h2m4 0h12"/><circle cx="10" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',link:'<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1" transform="translate(1 0) scale(.91)"/>',
 table:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 9v11"/>',
 chart:'<path d="M4 3v17h17M8 15v-5m5 5V5m5 10V8"/>',external:'<path d="M13 3h8v8m-1-7-10 10M9 5H4v15h15v-5"/>',
 close:'<path d="m5 5 14 14M19 5 5 19"/>',right:'<path d="m9 5 7 7-7 7"/>',left:'<path d="m15 5-7 7 7 7"/>',
 compare:'<rect x="2" y="5" width="8" height="14" rx="1"/><rect x="14" y="5" width="8" height="14" rx="1"/>',
 copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',down:'<path d="m6 9 6 6 6-6"/>',eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'
};
function ic(name){return '<svg class="icon" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">'+(iconShapes[name]||'')+'</svg>'}
function renderField(title,key,values,allLabel){
 const list=allLabel?['',...values]:values;
 return '<label class="field"><span class="fieldTitle">'+title+'</span><select data-filter="'+key+'">'+list.map(v=>'<option value="'+safe(v)+'" '+(s[key]===v?'selected':'')+'>'+safe(v?(key==='snapshot'?dateLabel(v):v):allLabel)+'</option>').join('')+'</select></label>';
}
function blank(){return {ui:'en',section:sections[0],panel:'Results',track:initialTracks[0],model:'',models:'all',size:'all',language:'',mode:'',status:'',snapshot:dates[0],view:'results',layout:'table',sort:'',page:1,ids:[],detail:'',pa:'',dd:'',ds:'',dp:1,dr:'all',dc:'all',db:'all',dk:'all'}}
const legacyLabels={"T\u00fcrk\u00e7e \u00b7 Genel":"Turkish Reading & Grammar","Metin":"Text","Yay\u0131mlanm\u0131\u015f":"Published","T\u00fcrk\u00e7e":"Turkish","T\u00fcrk\u00e7e \u00b7 Okuma":"Turkish Reading","T\u00fcrk\u00e7e \u00b7 Dil bilgisi":"Turkish Grammar","English reading":"English Reading","\u0130ngilizce":"English","Bilmiyorum \u00b7 T\u00fcrk\u00e7e":"Turkish abstention option","Se\u00e7enek dili \u00b7 T\u00fcrk\u00e7e":"Turkish option wording","\u00c7al\u0131\u015ft\u0131r\u0131lmad\u0131":"Not run","I don\u2019t know \u00b7 English":"English abstention option","Sayfa deneyi \u00b7 Metin":"Page input \u00b7 Text","Sayfa deneyi \u00b7 Yaln\u0131z g\u00f6r\u00fcnt\u00fc":"Page input \u00b7 Image only","Yaln\u0131z g\u00f6r\u00fcnt\u00fc":"Image only","Sayfa deneyi \u00b7 Metin + g\u00f6r\u00fcnt\u00fc":"Page input \u00b7 Text and image","Metin + g\u00f6r\u00fcnt\u00fc":"Text and image","Sayfa deneyi \u00b7 D chandra-ocr-2":"Page input \u00b7 D chandra-ocr-2","OCR metni":"OCR text","Sayfa deneyi \u00b7 D dots-mocr":"Page input \u00b7 D dots-mocr","Sayfa deneyi \u00b7 D surya-ocr-2":"Page input \u00b7 D surya-ocr-2","Sayfa deneyi \u00b7 D unlimited-ocr-2":"Page input \u00b7 D unlimited-ocr-2","Sayfa deneyi \u00b7 \u00c7al\u0131\u015ft\u0131r\u0131lmad\u0131":"Page input \u00b7 Not run","G\u00f6rsel deney":"Board image experiment","Lig 1":"League 1","Belirtilmemi\u015f":"Unspecified","Lig 2":"League 2","Lig 3":"League 3","Ge\u00e7 kat\u0131l\u0131m \u00b7 Lig 3":"Late entry \u00b7 League 3","Ge\u00e7 kat\u0131l\u0131m \u00b7 Lig 1":"Late entry \u00b7 League 1","v1 pozisyonlar\u0131":"v1 position set","K\u0131sa test \u00b7 Part A":"Smoke test \u00b7 Part A","Nackgammon \u00b7 \u0130lk bak\u0131\u015f \u00b7 standard":"Nackgammon \u00b7 First look \u00b7 standard","Nackgammon \u00b7 \u0130lk bak\u0131\u015f \u00b7 nackgammon":"Nackgammon \u00b7 First look \u00b7 nackgammon","Nackgammon \u00b7 Son bak\u0131\u015f \u00b7 standard":"Nackgammon \u00b7 Final look \u00b7 standard","Nackgammon \u00b7 Son bak\u0131\u015f \u00b7 nackgammon":"Nackgammon \u00b7 Final look \u00b7 nackgammon","Nackgammon \u00b7 Ge\u00e7 kat\u0131l\u0131m \u00b7 \u0130lk bak\u0131\u015f \u00b7 standard":"Nackgammon \u00b7 Late entry \u00b7 First look \u00b7 standard","Nackgammon \u00b7 Ge\u00e7 kat\u0131l\u0131m \u00b7 \u0130lk bak\u0131\u015f \u00b7 nackgammon":"Nackgammon \u00b7 Late entry \u00b7 First look \u00b7 nackgammon","Nackgammon \u00b7 Ge\u00e7 kat\u0131l\u0131m \u00b7 Son bak\u0131\u015f \u00b7 standard":"Nackgammon \u00b7 Late entry \u00b7 Final look \u00b7 standard","Nackgammon \u00b7 Ge\u00e7 kat\u0131l\u0131m \u00b7 Son bak\u0131\u015f \u00b7 nackgammon":"Nackgammon \u00b7 Late entry \u00b7 Final look \u00b7 nackgammon","Analiz durumu":"Analysis status","Analiz bekliyor":"Analysis pending","\u00d6l\u00e7\u00fclmedi":"Not measured","Tahta g\u00f6r\u00fcnt\u00fcs\u00fc":"Board image","Birle\u015fik kaynak puan\u0131":"Published combined score","Karma":"Mixed","Kapsam eksik":"Incomplete coverage","Web grounding \u00b7 turkish":"Web grounding \u00b7 Turkish","Web grounding \u00b7 english":"Web grounding \u00b7 English","Engellendi":"Blocked","Sayfa tekrar\u0131 \u00b7 B":"Page repeat \u00b7 B","Sayfa tekrar\u0131 \u00b7 C":"Page repeat \u00b7 C"};
function fromURL(){
 let params=new URLSearchParams(location.search);
 if(!params.size){try{params=new URLSearchParams(localStorage.getItem(storeName)||'');params.delete('snapshot')}catch{}} // a return visit opens the newest snapshot; a shared link keeps its own
 const st=blank();
 if(!location.search&&!params.has('ui')){try{st.ui=localStorage.getItem('hilde.language')||'en'}catch{}}
 for(const k of Object.keys(st))if(k!=='ids'&&params.has(k))st[k]=params.get(k);
 // No filter panel (Ümit #13474): always the newest snapshot, every language, input condition and run status, and no
 // model search, whatever an old link or a saved visit holds, since nothing on the page could undo them
 st.snapshot=dates[0];st.language='';st.mode='';st.status='';st.model='';
 for(const key of ['track','language','mode','status'])st[key]=legacyLabels[st[key]]||st[key];
 st.ids=uniq(params.getAll('pick').filter(x=>dates.includes(x.split(':')[0])&&/^[a-f\d]{14}$/.test(x.split(':')[1]||'')));
 if(st.ui!=='tr')st.ui='en';
 if(!sections.includes(st.section))st.section=sections[0];
 if(!dates.includes(st.snapshot))st.snapshot=dates[0];
 if(!['results','compare','drafts'].includes(st.view))st.view='results';
 if(!['chart','table','metrics','resources'].includes(st.layout))st.layout='table';
 if(!['','cost','latency'].includes(st.sort))st.sort='';
 st.page=Math.max(1,parseInt(st.page,10)||1);st.dp=Math.max(1,parseInt(st.dp,10)||1);return st
}
let s=fromURL();
function serialize(){
 // The snapshot only when it is not the newest: an address the page wrote for the newest must not pin it once a newer
 // one is out (Ümit #11706 reopened a 14:04 address at 17:22 and saw old rows); a chosen older one stays in the link.
 const p=new URLSearchParams({v:'2',ui:s.ui});
 if(s.snapshot&&s.snapshot!==dates[0])p.set('snapshot',s.snapshot);
 for(const key of Object.keys(blank()))if(key!=='ids'&&s[key]!==''&&s[key]!==blank()[key]&&(isDecisionPanel()||!decKeys.includes(key)))p.set(key,s[key]);
 for(const id of s.ids)p.append('pick',id);
 return p.toString();
}
function persist(push=false){
 const q=serialize();
 // a decision's #d<id> stays in the address until the reader moves on (Every decision)
 if(location.search!=='?'+q)history[push?'pushState':'replaceState'](null,'',location.pathname+'?'+q+(!push&&isDecisionPanel()?location.hash:''));
 try{localStorage.setItem(storeName,q)}catch{}
}
const closeModal=()=>{if($('#modal').open)$('#modal').close()};
function toast(message){const t=$('#toast');t.textContent=s.ui==='tr'?HildeI18n.translate(message):message;t.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.hidden=true,2400)}
function ext(href,label){return '<a href="'+safe(href)+'" target="_blank" rel="noopener noreferrer">'+safe(label)+' '+ic('external')+'</a>'}
function snap(r){return r.id.split(':')[0]}
function fileURL(r,path=r.file){return repo+commits.get(snap(r))+'/'+path}
function sourcePage(r){return originSite+(r.page||pages[sections.indexOf(r.section)])}
function renderNav(){
 document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===s.view);b.setAttribute('aria-pressed',b.dataset.view===s.view)});
 document.querySelectorAll('.navCount').forEach(n=>n.textContent=s.ids.length||'');
 $('#sectionTabs').innerHTML=sections.map((name,index)=>{
  const selected=name===s.section;
  return '<button type="button" class="sectionTab" data-section="'+index+'" aria-pressed="'+selected+'">'+safe(name)+'</button>';
 }).join('');
 // on a phone the tabs are one sideways row (Ümit #16331): keep the chosen bench in view
 const nav=$('#sectionTabs'),on=nav.querySelector('[aria-pressed=true]');
 if(on&&nav.scrollWidth>nav.clientWidth){nav.scrollLeft=Math.max(0,on.offsetLeft-nav.offsetLeft-(nav.clientWidth-on.offsetWidth)/2);nav.classList.toggle('atEnd',nav.scrollLeft+nav.clientWidth>=nav.scrollWidth-2)}
}
function filtered(){
 const base=(data.get(s.snapshot)||[]).filter(r=>r.section===s.section&&inPanel(r));
 const q=s.model.trim().toLocaleLowerCase('en-US');
 const rows=base.filter(r=>(s.models==='all'||(r.modelType||'unclassified')===s.models)&&(s.size==='all'||(r.modelClass||'unclassified')===s.size)&&(!s.language||r.lang===s.language)&&(!s.mode||r.mode===s.mode)&&(!s.status||r.status===s.status)&&(!q||[r.name,r.tag,r.setup,r.ref].join(' ').toLocaleLowerCase('en-US').includes(q)));
 const tracks=uniq(base.map(r=>r.track));
 const chosen=tracks.includes(s.track)?s.track:tracks.includes(initialTracks[sections.indexOf(s.section)])?initialTracks[sections.indexOf(s.section)]:tracks[0]||'';
 return {base,tracks,chosen,rows:rows.filter(r=>r.track===chosen),total:rows.length}
}
const typeTitles={all:'All models',decision:'Decision models',chat:'Chat models',program:'Programs',model:'Bare models',agent:'Agents',unclassified:'Unclassified'};
const sizeTitles={all:'All classes',tiny:'Tiny',small:'Small',medium:'Medium',large:'Large',efficient:'Efficient',workhorse:'Workhorse',flagship:'Flagship',undisclosed:'Undisclosed',unverified:'Unverified',unclassified:'Unclassified'};
const titles=(t,v)=>t[v]||v;
function cohortTabs(f){
 function line(field,label,titles,values){
  return '<div class="cohortTabs" role="group" aria-label="'+label+'">'+values.map(v=>'<button data-cohort="'+field+'" data-value="'+v+'" aria-pressed="'+(s[field]===v)+'" class="'+(s[field]===v?'on':'')+'">'+safe(titles[v]||v)+'</button>').join('')+'</div>';
 }
 const types=Object.keys(typeTitles).filter(v=>v==='all'||v===s.models||f.base.some(r=>(r.modelType||'unclassified')===v));
 const available=f.base.filter(r=>s.models==='all'||(r.modelType||'unclassified')===s.models);
 const sizes=Object.keys(sizeTitles).filter(v=>v==='all'||v===s.size||['tiny','small','medium','large','efficient','workhorse','flagship','undisclosed'].includes(v)||available.some(r=>(r.modelClass||'unclassified')===v));
 // One line (Model Atlas plan, #15323; Ümit #16227): the model type as a small menu, the size classes stay visible as
 // buttons, scrolling sideways inside their own row on a phone, so the first results show without scrolling the page
 const typePick='<label class="typePick"><span class="fieldTitle">Model type</span><select data-filter="models" aria-label="Model type">'+types.map(v=>'<option value="'+v+'"'+(s.models===v?' selected':'')+'>'+safe(titles(typeTitles,v))+'</option>').join('')+'</select></label>';
 return '<div class="cohorts"><div class="cohortLine">'+typePick+'<span class="fieldTitle">Model class</span>'+line('size','Model class',sizeTitles,sizes)+'</div></div>';
}
function inPanel(r){
 if(s.panel==='Learning')return r.track.startsWith('Learning ·');
 if(s.panel==='Learning pilot')return r.track.startsWith('Learning pilot ·');
 if(s.panel==='Vision')return /^(Vision ·|Page input ·|Page repeat ·|Board image)/.test(r.track);
 if(s.panel==='Nackgammon')return r.track.startsWith('Nackgammon');
 if(s.panel==='Close choices')return r.track.startsWith('Close choices');
 return true;
}
function pageMap(){return guides.get(s.snapshot)?.[s.section]||{}}
function panelNames(){
 const names=Object.keys(sourceViews.get(s.snapshot)?.[s.section]||{});
 if(s.section==='Backgammon'){
  for(const v of ['Learning pilot','Clear risk','Close choices','Nackgammon','Disagreements','Phases','Compare plays','Leagues','Matches'])if(pageMap()[v]||(v==='Close choices'&&(data.get(s.snapshot)||[]).some(r=>r.track.startsWith('Close choices'))))names.push(v);
 }
 return ['Results',...new Set(names)];
}
function isRecordPanel(){return ['Results','Vision','Learning','Learning pilot','Close choices','Nackgammon'].includes(s.panel)}
function publicationTabs(){
 const primary=['Results','Vision','Learning','Learning pilot','Decisions','Questions','Highlights','Experiments','About','Methodology','Preparation','Method'];
 const names=panelNames();
 const buttons=items=>items.map(label=>'<button class="'+(s.panel===label?'on':'')+'" aria-pressed="'+(s.panel===label)+'" data-panel="'+safe(label)+'">'+safe(label)+'</button>').join('');
 const main=names.filter(v=>primary.includes(v)),more=names.filter(v=>!primary.includes(v));
 return '<nav class="publicationTabs" aria-label="'+safe(s.section)+' sections">'+buttons(main)+(more.length?'<details class="moreTabs" '+(more.includes(s.panel)?'open':'')+'><summary>More sections</summary><div>'+buttons(more)+'</div></details>':'')+'</nav>';
}
// Old pages read again by the exporter (data/pages/, Ümit #16874 'no loss of information'): loaded when a panel opens;
// a section's contents are drawn when it is opened, so a page of thousands of blocks stays light on a phone
const pageFiles=new Map();
function pageFile(name){
 if(!pageFiles.has(name))pageFiles.set(name,fetch('data/'+name).then(r=>{if(!r.ok)throw Error(name);return r.json()}).catch(()=>({groups:[],error:true})).then(p=>{pageFiles.set(name,p);if(s.view==='results'&&pageMap()[s.panel]?.page===name)render();return p}));
 const p=pageFiles.get(name);return p instanceof Promise?null:p;
}
function pageBlocks(blocks){
 let out='',list=[];
 const end=()=>{if(list.length){out+='<ul>'+list.map(t=>'<li>'+safe(t)+'</li>').join('')+'</ul>';list=[]}};
 for(const b of blocks){
  if('li' in b){list.push(b.li);continue}
  end();
  if('h' in b)out+='<h3 class="pageHead">'+safe(b.h)+'</h3>';
  else if('pre' in b)out+='<pre class="pagePre">'+safe(b.pre)+'</pre>';
  else if('table' in b){const t=b.table;out+='<div class="tableScroll"><table class="pageTable">'+(t.caption?'<caption>'+safe(t.caption)+'</caption>':'')+(t.head.length?'<thead>'+t.head.map(r=>'<tr>'+r.map(c=>'<th scope="col">'+safe(c)+'</th>').join('')+'</tr>').join('')+'</thead>':'')+'<tbody>'+t.rows.map(r=>'<tr>'+r.map(c=>'<td>'+safe(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}
  else out+='<p>'+safe(b.p)+'</p>';
 }
 end();return out;
}
function pageGroup(g,internal){
 const inside=url=>{const [base,hash='']=url.split('#');return internal.has(url)?[internal.get(url),'']:internal.has(base)?[internal.get(base),hash]:null};
 const items=g.links.map(([text,url])=>{const to=inside(url);return to?'<button class="textLink" data-panel="'+safe(to[0])+'"'+(to[1]?' data-anchor="'+safe(to[1])+'"':'')+'>'+safe(text)+'</button>':ext(url,text)}).join('');
 return (g.blocks?pageBlocks(g.blocks):g.text.map(t=>'<p>'+safe(t)+'</p>').join(''))+(items?'<div class="guideLinks">'+items+'</div>':'');
}
document.addEventListener('toggle',e=>{
 const d=e.target;if(!(d instanceof HTMLDetailsElement)||!d.open||!d.dataset.pageGroup||d.dataset.drawn)return;
 const res=pageMap()[s.panel],p=res?.page&&pageFile(res.page),g=p?.groups[+d.dataset.pageGroup];if(!g)return;
 d.dataset.drawn='1';d.querySelector('.pageGroupBody').innerHTML=pageGroup(g,new Map(Object.entries(pageMap()).map(([k,v])=>[v.url,k])));
 if(s.ui==='tr')HildeI18n.localize(d,s.ui);
},true);
// a setup's own old page (models/<id>/), read in by the exporter, in its row's details (Ümit #16874)
function modelPageBox(r){return r.modelPage?'<details class="guideItem modelPageBox" data-model-page="'+safe(r.modelPage)+'"><summary>Setup page</summary><div class="pageGroupBody" data-verbatim lang="en"><p class="sourceNote">Loading…</p></div></details>':''}
document.addEventListener('toggle',async e=>{
 const d=e.target;if(!(d instanceof HTMLDetailsElement)||!d.open||!d.dataset.modelPage||d.dataset.drawn)return;
 d.dataset.drawn='1';pageFile(d.dataset.modelPage);const p=await pageFiles.get(d.dataset.modelPage),internal=new Map(Object.entries(pageMap()).map(([k,v])=>[v.url,k]));
 d.querySelector('.pageGroupBody').innerHTML=p.error?'<p class="sourceNote">This page could not be loaded.</p>':p.groups.map(g=>(g.title?'<h3 class="pageHead">'+safe(g.title)+'</h3>':'')+pageGroup(g,internal)).join('');
 if(s.ui==='tr')HildeI18n.localize(d,s.ui);
},true);
// a link to an old page's #id (s.pa) opens the section holding it and scrolls there once (jevgammon #16944)
let anchorShown='';
function showAnchor(){
 const key=s.section+'|'+s.panel+'|'+s.pa,t=s.pa&&document.querySelector('details[data-anchor-target]');
 if(!t||anchorShown===key)return;anchorShown=key;t.scrollIntoView({block:'start'});
}
function reader(){
 const resource=pageMap()[s.panel], url=resource?.url||sourceViews.get(s.snapshot)?.[s.section]?.[s.panel];
 if(!url)return '';
 const links=ext(url,'Open published page')+(resource?.file?ext(repo+commits.get(s.snapshot)+'/'+resource.file,'Pinned source'):'');
 const page=resource?.page?pageFile(resource.page):null;
 const groups=(page?page.groups:resource?.groups||[]).filter(g=>g.title||(g.blocks||g.text).length||g.links.length);
 const internal=new Map(Object.entries(pageMap()).map(([k,v])=>[v.url,k]));
 const target=s.pa&&page?.anchors?.[s.pa];
 const body=resource?.page&&!page?'<p class="sourceNote">Loading…</p>':page?.error?'<p class="sourceNote">This page could not be loaded.</p>':groups.map((g,i)=>{
  const first=target===undefined||target===''||target===null?i===0:i===target;
  if(!g.title)return pageGroup(g,internal);
  return page?'<details class="guideItem" data-page-group="'+i+'" '+(first?'open data-drawn="1"':'')+(first&&s.pa&&i===target?' data-anchor-target':'')+'><summary>'+safe(g.title)+'</summary><div class="pageGroupBody">'+(first?pageGroup(g,internal):'')+'</div></details>':'<details class="guideItem" '+(first?'open':'')+'><summary>'+safe(g.title)+'</summary>'+pageGroup(g,internal)+'</details>';
 }).join('');
 return '<article class="panel guide"><div class="eyelabel">'+safe(s.section)+' · '+safe(dateLabel(s.snapshot))+'</div><h2>'+safe(resource?.title||s.panel)+'</h2><div class="guideLinks">'+links+'</div>'+(s.ui==='tr'?'<p class="sourceNote">Yayımlanmış kaynaktan alıntılar İngilizcedir.</p>':'')+'<div data-verbatim lang="en">'+body+'</div></article>';
}
// Toolbench's first results were labelled a pilot; the bench is no longer called one, in any snapshot (Ümit #11253).
function trackLabel(t){return {'Pilot results':'Our bench','Results':'Our bench','Tool choice (decision models)':'Tool choice','Risk judgement ranking':'Risk judgement'}[t]||t}
function resultNote(f){
 // Toolbench: one small link to what each tab measures, on Toolbench's page, its Methodology (#method); no explanation on the tabs (Ümit #12107, #12121).
 const what=s.section==='Toolbench'&&['Results','Tool choice (decision models)'].includes(f?.chosen)?'<p class="whatLink"><a href="/analysis/tool-calling/#method">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('What this measures →'))+'</a></p>':'';
 // Science: one line on what the chosen experiment is (Ümit #16331: 'exact answers must explain what they are')
 const sciAbout={'Maths':'50 university maths problems, five options; every number changed from the source book, the answer computed again.',
  'Physics':'50 university physics problems, five options; every number changed from the source book, the answer computed again.',
  'High-school maths':'32 high-school maths questions (a national olympiad\'s first stage, 2026), five options.',
  'Maths: write the number, no options':'The same 50 maths problems without options: the model writes the number, counted right within 0.1% (or rounded as the question asks).',
  'Physics: write the number, no options':'The same 50 physics problems without options: the model writes the number, counted right within 0.1% (or rounded as the question asks).',
  'Maths: spot the broken questions':'The 50 maths problems plus copies with one number changed so that no option is right; option F says the question is flawed. Decision models are here too: choose Decision models under Model type.',
  'Physics: spot the broken questions':'The 50 physics problems plus copies with one number changed so that no option is right; option F says the question is flawed. Decision models are here too: choose Decision models under Model type.',
  'Earlier set: maths (25)':'The first 25 of the 50 maths problems, as asked before 24 November; kept for the models not asked the full 50 yet.',
  'Earlier set: physics (25)':'The first 25 of the 50 physics problems, as asked before 24 November; kept for the models not asked the full 50 yet.',
  'Earlier set: maths, write the number (25)':'The first 25 maths problems without options, as asked before 24 November.',
  'Earlier set: physics, write the number (25)':'The first 25 physics problems without options, as asked before 24 November.',
  'Earlier set: maths, broken questions':'The first 25 maths problems plus 21 broken copies, as asked before 24 November.',
  'Earlier set: physics, broken questions':'The first 25 physics problems plus 21 broken copies, as asked before 24 November.',
  'Chemistry':'50 chemistry problems from university chemistry exams and course notes and LYS question banks, five options; every number changed, the answer computed again.',
  'Biology':'50 biology problems that need a calculation (crosses, probabilities, Hardy–Weinberg, cell division, DNA counts), five options; every number changed, the answer computed again.',
  'Geometry':'50 geometry problems, mostly from LYS exams, stated without figures, five options; every number changed, the answer computed again.',
  'Logic':'50 numerical logic puzzles from public-sector exam books, five options; names and numbers changed, the answer found by checking every arrangement.',
  'Chemistry: write the number, no options':'The same 50 chemistry problems without options: the model writes the number, counted right within 0.1% (or rounded as the question asks).',
  'Biology: write the number, no options':'The same 50 biology problems without options: the model writes the number, counted right within 0.1% (or rounded as the question asks).',
  'Geometry: write the number, no options':'The same 50 geometry problems without options: the model writes the number, counted right within 0.1% (or rounded as the question asks).',
  'Logic: write the number, no options':'The same 50 logic puzzles without options: the model writes the number, counted right within 0.1%.',
  'Chemistry: spot the broken questions':'The 50 chemistry problems plus copies with one number changed so that no option is right; option F says the question is flawed.',
  'Biology: spot the broken questions':'The 50 biology problems plus copies with one number changed so that no option is right; option F says the question is flawed.',
  'Geometry: spot the broken questions':'The 50 geometry problems plus copies with one number changed so that no option is right; option F says the question is flawed.',
  'Logic: spot the broken questions':'The 50 logic puzzles plus copies with one number changed so that no option is right; option F says the question is flawed.',
  "Humanity's First Exam (text)":"Google DeepMind's Humanity's First Exam, the public text part: 48 easy prompts in 12 families of 4 slightly changed versions, each asked 6 times at the maker's settings. The score is the share of right answers; the family score (Family pass^4, in the details) counts a family only if all 4 tries are right on all 4 versions. A judge model (Gemini 4 Neon, temperature 0, HFE's own judge prompt) decides right or wrong."};
 const sciKey=s.section==='Science'?(f?.chosen||'').replace(/ \(Turkish\)$/,''):'';
 const about=sciAbout[sciKey]?'<p class="whatLink">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)(sciAbout[sciKey]))+'</p>':'';
 // An older snapshot than the newest: say so, with the way to the newest (Ümit #11253 looked at an old one).
 const old=dates.length&&s.snapshot!==dates[0]?'<div class="notice neutral">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('You are looking at an older snapshot:'))+' '+safe(dateLabel(s.snapshot))+'. <button class="textLink" data-newest="1">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('Show the newest'))+'</button> ('+safe(dateLabel(dates[0]))+')</div>':'';
 // A track the snapshot did not re-read keeps its rows from an earlier snapshot: say from when (Zeki #9682)
 const from=uniq((f?.rows||[]).map(r=>r.carriedFrom).filter(Boolean));
 return what+about+old+(from.length?'<div class="notice neutral">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('Copied unchanged from an earlier snapshot; its source files were not read again for this one:'))+' '+safe(from.map(dateLabel).join(', '))+'</div>':'')+resultNoteText();
}
function resultNoteText(){
 if(s.panel==='Learning')return '<div class="notice neutral">The source gives each setup its own improvement verdict. Before and after refer to empty context and the final lessons evaluation. A paused or running setup has no final verdict.</div>';
 if(s.panel==='Learning pilot')return '<div class="notice neutral">Gemma 4 31B with reasoning off. T0 is one shared baseline across arms. Each later checkpoint keeps its own context condition.</div>';
 // Only an old snapshot from before Toolbench's first runs holds just the candidate roster (Ümit #12020).
 if(s.section==='Toolbench'&&!(data.get(s.snapshot)||[]).some(r=>r.section==='Toolbench'&&['Results','Pilot results'].includes(r.track)))return '<div class="notice neutral">The source records zero model runs in this snapshot. Candidates appear with their preparation status.</div>';
 return '';
}
function readerSources(){
 const url=pageMap()[s.panel]?.url||sourceViews.get(s.snapshot)?.[s.section]?.[s.panel];
 return url?'<p class="guideLinks">'+ext(url,'Open published page')+'</p>':'';
}
function modelLogo(r){
 const color=/^#[0-9a-f]{6}$/i.test(r.color||'')?r.color:'#64748b';
 const logo=/^fi-[a-z0-9-]+$/.test(r.logo||'')?'<svg class="familyLogo" aria-hidden="true"><use href="model-logos.svg#'+r.logo+'"></use></svg>':'<span class="initials" aria-hidden="true">'+safe(r.name.split(/[^a-zA-Z0-9]+/).filter(Boolean).slice(0,2).map(n=>n[0]).join('').toUpperCase())+'</span>';
 return '<span class="logoChip" style="--family:'+color+'" aria-hidden="true">'+logo+'</span>';
}
function branded(r,text){
 const color=/^#[0-9a-f]{6}$/i.test(r.color||'')?r.color:'#64748b';
 return '<span class="modelLabel" style="--family:'+color+'">'+modelLogo(r)+'<span class="modelText">'+text+'</span></span>';
}
const nil='<span class="nil" aria-label="Not reported">—</span>';
// Backgammon Learning in plain words (Ümit #14294, jevgammon #14297): the data keys keep '(pp)'; headers and details say
// what the change is, with a hover that explains it
const HEAD_HELP={"Change in risks found (percentage points, after − before)": "How much more often the model took a worthwhile risk after its own lessons than before: the share of positions where the risk pays that it took, after minus before, in percentage points. Negative means less often."};
const LEARN_LABELS={"Risks found change (pp)": ["Change in risks found (percentage points, after − before)", "How much more often the model took a worthwhile risk after its own lessons than before: the share of positions where the risk pays that it took, after minus before, in percentage points. Negative means less often."], "Right safety change (pp)": ["Change in right safety plays (percentage points, after − before)", "How much more often the model correctly played safe after its own lessons than before: the share of positions where safety pays that it played safe, after minus before, in percentage points. Negative means less often."], "Risks found change · 95% interval (pp)": ["Change in risks found · 95% interval (percentage points)", null], "Right safety change · 95% interval (pp)": ["Change in right safety plays · 95% interval (percentage points)", null], "Threshold (pp)": ["Threshold (percentage points)", null], "Empty run range (pp)": ["Empty run range (percentage points)", null]};
function metric(r){
 if(r.verdict&&has(r.learningMetrics?.['Risks found change (pp)']))return ['Change in risks found (percentage points, after − before)',r.learningMetrics['Risks found change (pp)'],' pp'];
 if(has(r.acc))return ['Raw accuracy',r.acc*100,'%'];
 if(has(r.risk))return ['Risk judgement',r.risk,'/100'];
 if(has(r.err))return ['Error rate',r.err,' PR'];
 if(r.lowMetric)return [r.lowMetric.label,r.lowMetric.value,r.lowMetric.unit||''];
 if(has(r.norm))return ['Normalized score',r.norm,'/100'];
 if(has(r.exact))return ['Exact match',r.exact*100,'%'];
 return ['Outcome',null,''];
}
function val(v,n=2){return has(v)?safe(fmtNum(v,n)):nil}
function ciValue(r){
 if(r.ciText)return r.ciText;
 if(r.ci){const k=r.ciScale==='fraction'?100:1;return r.ci.map(x=>fmtNum(x*k,2)+(k===100?'%':'')).join(' – ')}
 return ''
}
function numCell(v,n=1){return '<span class="value">'+val(v,n)+'</span>'}
function duration(seconds){
 return seconds<1?fmtNum(seconds*1000,2)+' ms':fmtNum(seconds,2)+' s';
}
function money(amount,upper){
 const precision=amount>0&&amount<0.001?Math.min(16,Math.ceil(-Math.log10(amount))+2):4;
 return (upper?'≤ ':'')+'$'+fmtNum(amount,precision);
}
function unavailable(r){
 if(r.status==='Not run')return 'Not run';
 if(r.section==='All benches'&&r.track==='Combined')return 'No combined measure';
 return 'Not reported';
}
function priceBasis(basis){
 const t=(basis||'').toLowerCase();
 if(!t)return 'Pricing basis unspecified';
 if(t.includes('local compute cost not estimated'))return 'API spend only';
 // A subscription run's tokens at the API list price: an estimate, not a charge (Ümit #11858).
 if(t.includes('subscription')&&/(list|equivalent|priced as the api|estimate)/.test(t))return 'Estimated: subscription at API list price';
 if(t.includes('subscription'))return 'Subscription';
 if(/gpu|nvidia|runpod/.test(t))return 'Estimated GPU cost';
 if(/provider price × reported usage/.test(t))return 'Price × reported usage';
 if(/list price|list-price/.test(t))return 'API list price';
 if(/billed total/.test(t))return 'Reported billed total';
 return basis.length<=65?basis:'Published cost basis';
}
function usage(r){
 const ref=r.setupReference;
 const rate=r.unitCost||ref?.unitCost;
 const amount=rate?.value??r.cost;
 const basis=rate?.basis||r.costBasis||'';
 const seconds=r.latency??ref?.latency;
 const latBasis=r.latBasis&&has(r.latency)?r.latBasis:ref?.latBasis;
 return {
  // A subscription run has no per-use charge: its 0 is not a cost, so it reads as such until its owner estimates one
  // from its tokens at list price (Ümit #11858).
  cost:{value:has(amount)?(amount===0&&/subscription/i.test(basis)?'Subscription · not estimated':money(amount,rate?.upper??r.costUpper)):null,unit:rate?.unit||r.costUnit,basis,summary:priceBasis(basis),scope:(!r.unitCost&&ref?.unitCost)?ref.scope:null},
  time:{value:has(seconds)?duration(seconds):null,basis:latBasis,total:r.totalRequestTime,scope:!has(r.latency)&&has(ref?.latency)?ref.scope:null}
 };
}
function usageCell(r,m,extended=false){
 if(!m.value)return '<td class="usageCell"><span class="missingUsage">'+safe(unavailable(r))+'</span>'+(extended&&m.total?'<span>Summed request time</span><span>'+safe(duration(m.total.seconds))+'</span><span>'+safe(m.total.scope)+'</span>':'')+'</td>';
 const notes=[m.unit,m.scope,m.summary||m.basis?.split(' · ')[0]].filter(Boolean);
 if(extended&&m.basis&&!notes.includes(m.basis))notes.push(m.basis);
 return '<td class="usageCell"><strong>'+safe(m.value)+'</strong>'+notes.map(n=>'<span>'+safe(n)+'</span>').join('')+'</td>';
}
function usageColumns(r,extended=false){
 const m=usage(r);
 return usageCell(r,m.cost,extended)+usageCell(r,m.time,extended);
}
function usageTable(rows){
 const table=rows.map(r=>'<tr><td>'+checkbox(r)+'</td><td>'+recButton(r)+(r.status!=='Published'?statusTag(r):'')+'</td>'+usageColumns(r,true)+'</tr>').join('');
 return '<div class="tableScroll resourceTable"><table><thead class="tableHead"><tr><th class="checkCol"><span class="sr">Select</span></th><th>Model and setup</th><th>Cost</th><th>Latency</th></tr></thead><tbody>'+table+'</tbody></table></div>';
}
function checkbox(r){return '<input type="checkbox" aria-label="'+safe(r.name)+' select for comparison" data-pick="'+safe(r.id)+'" '+(s.ids.includes(r.id)?'checked':'')+'>'}
// A setup note in brackets after the name ('Turion Jev 31B (decision model, plain vLLM)') goes to the setup line, so the
// bold name stays short on a phone (codex #16245); the record keeps its full name
function splitName(r){const m=/^(.+?) \(([^()]+)\)$/.exec(r.name||'');return m&&!/^(open|closed)$/i.test(m[2])?[m[1],m[2]]:[r.name,null]}
function recButton(r){const [name,note]=splitName(r);return '<button class="rowName" data-detail="'+r.id+'" aria-label="'+safe(r.name)+'">'+branded(r,safe(name))+'</button><span class="sub">'+safe([note,r.setup||r.tag||r.ref||r.track, r.seeds?r.seeds.length+' run average':null].filter(Boolean).join(' · '))+'</span>'}
function headingActions(){return '<div class="actions">'+(s.section==='Backgammon'?'<button class="outline" data-dec-open="">'+ic('board')+' '+safe(L('Every decision'))+'</button>':'')+'<button class="outline" data-act="share">'+ic('link')+' Copy link</button>'+(s.ids.length?'<button class="primary" data-goto="compare">'+ic('compare')+' Selected ('+s.ids.length+')</button>':'')+'</div>'}
// Every table in one order (Ümit #12794): its main measure first (best first; an error rate lowest first), or, after a
// click on Cost or Latency, the cheapest or fastest first; rows without the value go last, in the main order.
function costValue(r){const rate=r.unitCost||r.setupReference?.unitCost;const v=rate?.value??r.cost;const basis=rate?.basis||r.costBasis||'';return has(v)&&!(v===0&&/subscription/i.test(basis))?v:null}
function latencyValue(r){const v=r.latency??r.setupReference?.latency;return has(v)?v:null}
function ordered(rows){
 const main=r=>{const [label,v]=metric(r);return v===null?null:(label==='Error rate'||r.lowMetric?-v:v)};
 const byMain=(a,b)=>{const x=main(a),y=main(b);return x===null&&y===null?0:x===null?1:y===null?-1:y-x};
 const key=s.sort==='cost'?costValue:s.sort==='latency'?latencyValue:null;
 return rows.map((r,i)=>[r,i]).sort(([a,i],[b,j])=>{
  if(key){const x=key(a),y=key(b);if(x!==null||y!==null){if(x===null)return 1;if(y===null)return -1;if(x!==y)return x-y}}
  return byMain(a,b)||i-j}).map(([r])=>r);
}
function resultSurface(f){
 f={...f,rows:ordered(f.rows)};
 const n=f.rows.length, pageSize=10;const last=Math.max(1,Math.ceil(n/pageSize));s.page=Math.min(s.page,last);if(f.chosen)s.track=f.chosen;
 const rows=f.rows.slice((s.page-1)*pageSize,s.page*pageSize);
 const one=rows.find(r=>metric(r)[1]!==null)||rows[0];
 const measure=one?metric(one)[0]:'Outcome';
 const popular={'Reading & Grammar':['English Reading','English abstention option','Dated facts · Parallel','Web grounding · English','d1-2B serving engines','Turkish Reading & Grammar','Turkish Reading','Turkish Grammar'], 'Logic & Math':['Logic','Math','Logic and Math'],Backgammon:['Risk judgement ranking','League 1','League 2','League 3'], 'All benches':['Combined','Decision Index','Turkish Reading','Turkish Grammar','English Reading','Logic','Math','Backgammon','Answer Check'], Toolbench:['Results','Tool choice (decision models)'], Science:['Maths','Physics','High-school maths','Chemistry','Biology','Geometry','Logic','Maths: write the number, no options','Physics: write the number, no options','Chemistry: write the number, no options','Biology: write the number, no options','Geometry: write the number, no options','Logic: write the number, no options','Maths: spot the broken questions','Physics: spot the broken questions','Chemistry: spot the broken questions','Biology: spot the broken questions','Geometry: spot the broken questions','Logic: spot the broken questions','Maths (Turkish)','Physics (Turkish)','High-school maths (Turkish)','Chemistry (Turkish)','Biology (Turkish)','Geometry (Turkish)','Logic (Turkish)','Maths: write the number, no options (Turkish)','Physics: write the number, no options (Turkish)','Chemistry: write the number, no options (Turkish)','Biology: write the number, no options (Turkish)','Geometry: write the number, no options (Turkish)','Logic: write the number, no options (Turkish)','Maths: spot the broken questions (Turkish)','Physics: spot the broken questions (Turkish)','Chemistry: spot the broken questions (Turkish)','Biology: spot the broken questions (Turkish)','Geometry: spot the broken questions (Turkish)','Logic: spot the broken questions (Turkish)']};
 const visibleTracks=(['Learning','Learning pilot','Vision'].includes(s.panel)?f.tracks:popular[s.section]||[]).filter(t=>f.tracks.includes(t));
 // Backgammon as its own page has it (Ümit #11706, #11710): Risk judgement and Learning first, the leagues after;
 // Learning is its own panel, so its tab switches panels and the others come back to Results.
 const bgTabs=s.section==='Backgammon'&&['Results','Learning'].includes(s.panel)&&(data.get(s.snapshot)||[]).some(r=>r.section==='Backgammon'&&r.track.startsWith('Learning ·'));
 // One way to switch experiments, not a menu beside tabs that list the same ones (Ümit #12548, #12549): the section's
 // main experiments as tabs, the rest behind 'More experiments', opened while one of them is shown.
 const main=bgTabs?popular.Backgammon.filter(t=>f.tracks.includes(t)):visibleTracks;
 const extra=f.tracks.filter(t=>!main.includes(t)&&!(bgTabs&&t.startsWith('Learning ·')));
 const tabFor=t=>bgTabs?'<button data-bg-track="'+safe(t)+'" aria-pressed="'+(s.panel==='Results'&&t===f.chosen)+'">'+safe(trackLabel(t))+'</button>'
  :'<button data-track="'+safe(t)+'" aria-pressed="'+(t===f.chosen)+'">'+safe(trackLabel(t))+'</button>';
 const more=extra.length?'<details class="moreTracks"'+(extra.includes(f.chosen)&&s.panel==='Results'||!bgTabs&&extra.includes(f.chosen)?' open':'')+'><summary>'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('More experiments'))+' <span class="count">'+extra.length+'</span></summary><div class="trackTabs" role="group" aria-label="More experiments">'+extra.map(tabFor).join('')+'</div></details>':'';
 // Many experiments (Science's English and Turkish sets, its subjects) are one dropdown, not a wall of tabs (Ümit #16227)
 // Backgammon's own tabs stay tabs, on the Table row, and its other experiments are one menu (Model Atlas plan #15323)
 const bgPick=bgTabs?'<div class="trackTabs inline" role="group" aria-label="Experiment tabs">'+main.flatMap((t,i)=>i===0?[tabFor(t),'<button data-panel="Learning" aria-pressed="'+(s.panel==='Learning')+'">'+safe(trackLabel('Learning'))+'</button>']:[tabFor(t)]).join('')+'</div>'+(extra.length?'<div class="trackPick"><select data-filter="track" aria-label="More experiments"><option value=""'+(extra.includes(f.chosen)?'':' selected')+' disabled>'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('More experiments'))+' ('+extra.length+')</option>'+extra.map(t=>'<option value="'+safe(t)+'"'+(t===f.chosen?' selected':'')+'>'+safe(trackLabel(t))+'</option>').join('')+'</select></div>':''):'';
 const pick=bgPick||(!bgTabs&&main.length+extra.length>4?'<div class="trackPick"><label><span>'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('Experiment'))+'</span> <select data-filter="track" aria-label="Experiment">'+[...main,...extra].map(t=>'<option value="'+safe(t)+'"'+(t===f.chosen?' selected':'')+'>'+safe(trackLabel(t))+'</option>').join('')+'</select></label></div>':'');
 const trackTabs=pick||(main.length+extra.length>1?'<div class="trackTabs" role="group" aria-label="Experiment tabs">'+main.flatMap((t,i)=>bgTabs&&i===0?[tabFor(t),'<button data-panel="Learning" aria-pressed="'+(s.panel==='Learning')+'">'+safe(trackLabel('Learning'))+'</button>']:[tabFor(t)]).join('')+'</div>'+more:'');
 const dims=key=>uniq(f.rows.map(r=>r[key]).filter(v=>v!==undefined));
 const labels=[s.section,...['lang','mode'].map(k=>dims(k).length===1?dims(k)[0]:null),dims('n').length===1&&dims('unit').length===1&&f.rows.every(r=>has(r.n))?fmtNum(dims('n')[0])+' '+(one?.unit||''):null].filter(Boolean);
 const radio=(layout,label,icon)=>'<button aria-pressed="'+(s.layout===layout)+'" class="'+(s.layout===layout?'active':'')+'" data-layout="'+layout+'">'+ic(icon)+label+'</button>';
 let content='';
 const roster=s.section==='Toolbench'&&rows.some(r=>r.track==='Candidate setups'); // the pre-run roster's own table
 if(!n)content='<div class="empty"><strong>No records match these filters.</strong>Choose another source snapshot or reset your filters.<br><button class="textLink" data-act="reset">Reset filters</button></div>';
 else if(s.layout==='resources')content=usageTable(rows);
 else if(s.layout==='chart'&&!roster){
  const primary=metric(one);
  const signed=primary[2]===' pp';
  const scale=signed?Math.max(1,...f.rows.map(r=>Math.abs(metric(r)[1]||0))):primary[2]===' PR'?Math.max(1,...f.rows.map(r=>Number(r.err)||0)):100;
  content='<p class="smallnote chartHint">'+safe(measure)+' · '+(primary[2]===' PR'?'lower is better':'published scale')+'</p>'+rows.map(r=>{const [label,v,u]=metric(r);const width=v===null||label!==measure?0:Math.min(signed?50:100,Math.abs(v)/scale*(signed?50:100));const pos=signed?(v<0?'right:50%;':'left:50%;'):'';return '<div class="chartRow"><div>'+recButton(r)+'</div><div class="miniBar '+(signed?'signedBar':'')+'"><span style="'+pos+'width:'+width+'%"></span></div><span class="value">'+(v===null?nil:val(v,1)+safe(u===' pp'?' points':u))+'</span>'+checkbox(r)+'</div>'}).join('')
 }else{
  const md=s.layout==='metrics';
  const candidates=roster;
  const heads=candidates?['Candidate and setup','Run status','Cost','Latency','Model type','Size verification']:md?['Model and setup','Cost','Latency','ECE','Invalid','Abstained']:['Rank¹','Model and setup',measure,s.panel==='Learning'?'Verdict':measure==='Normalized score'?'Raw accuracy':'Norm. score','Cost','Latency'];
  const sortKey={Cost:'cost',Latency:'latency'};
  const head=h=>{const k=sortKey[h]??(h===measure?'':null);const tip=HEAD_HELP[h]?' title="'+safe(HEAD_HELP[h])+'"':'';if(k===null||candidates)return '<th scope="col"'+tip+'>'+safe(h)+'</th>';
   const on=s.sort===k;return '<th scope="col"'+tip+' aria-sort="'+(on?(k?'ascending':'descending'):'none')+'"><button class="sortHead'+(on?' on':'')+'" data-sort="'+k+'">'+safe(h)+(on?'<span aria-hidden="true"> '+(k?'↑':'↓')+'</span>':'')+'</button></th>'};
  content='<div class="tableScroll"><table><thead class="tableHead"><tr><th class="checkCol"><span class="sr">Select</span></th>'+heads.map(head).join('')+'<th><span class="sr">Details</span></th></tr></thead><tbody>'+rows.map(r=>{
    const [label,m,u]=metric(r);
    if(candidates)return '<tr><td class="checkCol">'+checkbox(r)+'</td><td>'+recButton(r)+'</td><td>'+statusTag(r)+'</td>'+usageColumns(r)+'<td>'+safe(typeTitles[r.modelType]||'Unclassified')+'</td><td>'+safe(sizeTitles[r.modelClass]||'Unverified')+'</td><td><button class="rowDetails" data-detail="'+r.id+'" aria-label="'+safe(r.name)+' details">'+ic('right')+'</button></td></tr>';
    let main='<td class="checkCol">'+checkbox(r)+'</td>';
    if(!md)main+='<td class="rankCol" title="Published rank or statistical tier">'+(has(r.rank)?safe(r.rank):nil)+'</td>';
    main+='<td>'+recButton(r)+(r.status!=='Published'?'<span class="pill mutedPill">'+safe(r.status)+'</span>':'')+'</td>';
    if(md)main+=usageColumns(r)+'<td>'+numCell(has(r.ece)?r.ece*100:null)+'<span class="sub">'+(has(r.ece)?'points':'')+'</span></td><td>'+numCell(r.invalid)+'</td><td>'+numCell(r.abst)+'</td>';
    else main+='<td><div class="measure"><span class="value">'+(m===null?nil:val(m,r.lowMetric?.digits??1)+(u==='%'?'%':u===' pp'?' points':''))+'</span>'+(m!==null&&u!==' PR'&&u!==' pp'&&!r.lowMetric?'<div class="miniBar"><span style="width:'+Math.max(0,Math.min(100,m))+'%"></span></div>':'')+'</div>'+(label!==measure&&m!==null?'<span class="sub">'+safe(label)+'</span>':'')+'</td><td>'+(s.panel==='Learning'?(r.verdict?safe(r.verdict):nil):numCell(measure==='Normalized score'?(has(r.acc)?r.acc*100:null):r.norm))+'</td>'+usageColumns(r);
    return '<tr class="'+(s.ids.includes(r.id)?'selectedRow':'')+'">'+main+'<td><button class="rowDetails" data-detail="'+r.id+'" aria-label="'+safe(r.name)+' details">'+ic('right')+'</button></td></tr>'
  }).join('')+'</tbody></table></div>'
 }
 const heading=s.section==='Toolbench'?(roster?'Candidate setups':'Results'):s.panel==='Learning'?'Learning results':s.panel==='Learning pilot'?'Learning pilot results':'Experiment results';
 return '<div class="topline"><h2>'+heading+' <span class="count">'+fmtNum(n,0)+'</span></h2>'+headingActions()+'</div><div class="panel"><div class="panelTools"><div class="toggleGroup">'+radio('table','Table','table')+radio('resources','Cost & latency','clock')+(s.section==='Toolbench'?'':radio('chart','Chart','chart')+radio('metrics','Metrics','filters'))+'</div>'+(pick||'')+'</div>'+(pick?'':trackTabs)+'<div class="contextStrip"><span class="dot"></span>'+labels.map(safe).join('<span class="divider">/</span>')+'</div>'+content+(n?'<div class="pager"><span>'+((s.page-1)*pageSize+1)+'–'+Math.min(s.page*pageSize,n)+' / '+fmtNum(n,0)+' records</span><div class="actions"><button class="square" data-page="-1" aria-label="Previous page" '+(s.page===1?'disabled':'')+'>'+ic('left')+'</button><span>'+s.page+' / '+last+'</span><button class="square" data-page="1" aria-label="Next page" '+(s.page===last?'disabled':'')+'>'+ic('right')+'</button></div></div>':'')+'</div><p class="smallnote">'+(roster?'Select a candidate to inspect its eligibility and source.':'¹ Published rank or statistical tier. A dash means no value is reported. Select a model to inspect its method and units.')+'</p>'
}
function selected(){return s.ids.map(id=>records.get(id)).filter(Boolean)}
function statusTag(r){return '<span class="pill '+(r.status==='Published'?'':'mutedPill')+'">'+safe(r.status)+'</span>'}
function metricEntries(r){
 const p=v=>has(v)?fmtNum(v*100,2)+'%':null;
 const entry=(label,value,hint)=>({label,value,hint});
 const m=usage(r);
 const hint=(...items)=>items.filter(Boolean).join(' · ');
 return [
 entry('Raw accuracy',p(r.acc),has(r.right)&&has(r.n)?fmtNum(r.right,2)+' / '+fmtNum(r.n,0):null),
 entry('Normalized score',has(r.norm)?fmtNum(r.norm,2):null,r.normLabel||'0 = chance, 100 = every answer right; below chance is negative'),
 entry(r.rankType||'Published rank',r.rank),entry('Confidence interval',ciValue(r),r.ciType),
 entry('Cost',m.cost.value,hint(m.cost.scope,m.cost.unit,m.cost.basis)),
 entry('Latency',m.time.value,hint(m.time.scope,m.time.basis)),
 ...(r.unitCost&&has(r.cost)?[entry('Full run cost',money(r.cost,r.costUpper),hint(r.costUnit,r.costBasis))]:[]),
 ...(r.totalRequestTime?[entry('Summed request time',duration(r.totalRequestTime.seconds),r.totalRequestTime.scope)]:[]),
 ...(has(r.timingP90)?[entry('P90 request latency',duration(r.timingP90),'Per request')]:[]),
 entry('Calibration · ECE',has(r.ece)?fmtNum(r.ece*100,2)+' points':null),
 entry('Confidence',p(r.confidence),[r.confType,r.confSource].filter(Boolean).join(' · ')),
 entry('Invalid responses',r.invalid,'responses'),entry('Abstentions',r.abst,'responses'),entry('Risk judgement',has(r.risk)?fmtNum(r.risk,2)+' / 100':null,has(r.riskN)?fmtNum(r.riskN)+' decisions with a risk or safety tradeoff':null),
 entry('Error rate',has(r.err)?fmtNum(r.err,3)+' PR':null),...(r.lowMetric?[entry(r.lowMetric.label,has(r.lowMetric.value)?fmtNum(r.lowMetric.value,r.lowMetric.digits??2)+(r.lowMetric.unit||''):null,'lower is better')]:[]),entry('Risk interval',r.riskCI?.map(x=>fmtNum(x,2)).join(' – ')),
 entry(r.section==='Backgammon'?'Brier':'Chosen-answer Brier',has(r.brier)?fmtNum(r.brier,4):null),entry('AUROC',has(r.auroc)?fmtNum(r.auroc,4):null),
 entry('Decision Score',has(r.decisionScore)?fmtNum(r.decisionScore,2):null),entry('Exact match',p(r.exact)),...Object.entries(r.extraMetrics||{}).map(([k,v])=>{const labels={wrong_answer_recall:'Wrong answer recall',false_alarm_rate:'False alarm rate',gpu_seconds_per_1000:'GPU seconds / 1,000 requests',latency_s_p90:'P90 latency (s)',non_hallucination:'Non-hallucination (abstained of answers not right)',seed_min:'Lowest run accuracy',seed_max:'Highest run accuracy',run_cost_usd:'Modeled GPU cost of the whole run (not an invoice)'};return entry(labels[k]||k,typeof v==='string'?v:k==='run_cost_usd'?'$'+fmtNum(v,4)+' USD':k.endsWith('recall')||k.endsWith('rate')||['non_hallucination','seed_min','seed_max'].includes(k)?p(v):fmtNum(v,3))}),...Object.entries(r.learningMetrics||{}).map(([label,v])=>entry(LEARN_LABELS[label]?.[0]??label,typeof v==='number'?fmtNum(v,3):v,LEARN_LABELS[label]?.[1])),entry('Published improvement verdict',r.verdict),entry('Confidence ≥ 0.99',r.sure?fmtNum(r.sure.answers)+' answers · '+fmtNum(r.sure.wrong)+' incorrect':null)
 ]}
function sourceLinks(r){return '<div class="sourceLinks">'+ext(sourcePage(r),'Benchmark page')+ext(fileURL(r),'Pinned source')+(r.additionalSource?ext(fileURL(r,r.additionalSource),'Metric source'):'')+(r.normSource&&has(r.norm)?ext(fileURL(r,r.normSource),'Score source'):'')+(r.rankSource?ext(fileURL(r,r.rankSource),'Source table'):'')+uniq([...(r.performanceSources||[]),r.unitCost?.file,r.setupReference?.unitCost?.file,r.setupReference?.file].filter(f=>f&&![r.file,r.rankSource,r.additionalSource].includes(f))).map(f=>ext(fileURL(r,f),'Cost and timing source')).join('')+'</div>'}
function detailsDl(r){
 const missing=metricEntries(r).filter(e=>!has(e.value)).map(e=>e.label);
 const [,m,u]=metric(r);
 const fields=[
 ['Model type',typeTitles[r.modelType]||'Unclassified'],['Model class',sizeTitles[r.modelClass]||'Unclassified'], ['Method',r.method||'The source does not specify a method for this record.'],['Sample',has(r.n)?fmtNum(r.n)+' '+r.unit:r.components?'Reading, Logic & Math and Backgammon use separate samples.':'Not specified by the source.'],
 [r.when||'Experiment date',r.date||'Not specified by the source.'],['Run status',r.status+(r.why?' · '+r.why:'')],
 ['Verified findings',r.status!=='Published'?'This status has no confirmed finding.':r.verdict?'Published improvement verdict: '+r.verdict+'.':m!==null?metric(r)[0]+' '+fmtNum(m,3)+u+'. Observation reported by the source.':'No numeric outcome is published for this record.'],
 ['Unknown fields',missing.length?missing.join(', '):'All displayed measures are present in the source.'],['Tentative findings and source notes',r.status==='Provisional'?'The source marks this result as provisional.':r.tent||'The source does not flag a tentative finding.'],
 ['Method limitations',r.limit||'The source gives no additional method limitation for this record.'],
 ['Version and record',[dateLabel(snap(r)),r.version,r.ref].filter(Boolean).join(' · ')]
 ];
 if(r.seeds)fields.push(['Repeat records',r.seeds.map(v=>'Seed '+v.seed+' · '+v.right+' / '+v.n+' · '+v.run_id).join(' | ')]);
 if(r.components)fields.push(['Published components',Object.entries(r.components).map(([key,v])=>key+' '+(v?fmtNum(v[0],2)+' / 100 · n='+fmtNum(v[1]):'no record')).join(' | ')]);
 return '<dl class="detailDl">'+fields.map(([k,v])=>'<dt>'+safe(k)+'</dt><dd>'+safe(v)+'</dd>').join('')+'</dl>'
}
function metricGrid(r,full){const entries=metricEntries(r);return '<div class="metricGrid">'+entries.filter(e=>full||has(e.value)||['Cost','Latency'].includes(e.label)).map(e=>'<div class="metricBlock"><div class="metricLabel">'+safe(e.label)+'</div><div class="metricData">'+(has(e.value)?safe(e.value):['Cost','Latency'].includes(e.label)?safe(unavailable(r)):nil)+(e.hint&&has(e.value)?'<span class="sub">'+safe(e.hint)+'</span>':'')+'</div></div>').join('')+'</div>'}
function earlier(r){return [...records.values()].filter(x=>x.match===r.match&&x.id!==r.id).sort((a,b)=>a.id.localeCompare(b.id))}
function historyButtons(r){const list=earlier(r);return '<p class="fieldTitle">Other snapshots of this record</p><div class="historyList">'+(list.length?list.map(x=>'<button class="outline" data-history="'+x.id+'" data-origin="'+r.id+'">'+ic('compare')+safe(dateLabel(snap(x)))+'</button>').join(''):'<span class="unavailable">No matching record was found in the other snapshots.</span>')+'</div>'}
function showDetail(r,open=true){
 s.detail=r.id;persist();
 const body=$('.dialogBody'),kept=!open&&body.querySelector('details.modelPageBox')?.open; // a redraw (other snapshots loaded) keeps an opened setup page open
 body.innerHTML='<div class="drawerHead"><div><span class="eyelabel">'+safe(r.section)+'</span><h2>'+branded(r,safe(r.name))+'</h2></div><button class="square" data-act="close" aria-label="Close">'+ic('close')+'</button></div><div class="tagLine">'+statusTag(r)+'<span class="pill">'+safe(r.lang)+'</span><span class="pill">'+safe(r.mode)+'</span></div><p class="drawerMeta">'+[r.track,r.setup||r.tag,dateLabel(snap(r))].map(safe).join(' / ')+'</p>'+metricGrid(r,false)+detailsDl(r)+sourceLinks(r)+historyButtons(r)+'<div class="modalFooter"><button class="primary" data-toggle-detail="'+r.id+'">'+ic('compare')+(s.ids.includes(r.id)?'Remove from selection':'Add to comparison')+'</button><button class="outline" data-act="share">'+ic('link')+' Copy record link</button></div>';
 body.querySelector('.modalFooter')?.insertAdjacentHTML('afterbegin',decEntry(r));
 body.querySelector('.modalFooter')?.insertAdjacentHTML('beforebegin',modelPageBox(r));
 if(kept){const d=body.querySelector('details.modelPageBox');if(d)d.open=true}
 HildeI18n.localize(body,s.ui);
 if(open&&!$('#modal').open)$('#modal').showModal();
 // the record's other snapshots: load them once, then redraw the box if it still shows this record
 const missing=dates.filter(v=>!data.has(v));
 const had=data.size;
 if(missing.length)Promise.all(missing.map(v=>loadSnapshot(v).catch(()=>{}))).then(()=>{if(data.size>had&&$('#modal').open&&s.detail===r.id)showDetail(r,false)});
}
function comparable(list){
 if(list.length<2)return 'single';
 if(list.every(r=>r.match===list[0].match&&r.ref===list[0].ref&&r.file===list[0].file))return 'history';
 return list.every(r=>r.status==='Published'&&r.sig&&r.sig===list[0].sig&&r.track===list[0].track&&r.section===list[0].section&&r.n===list[0].n&&snap(r)===snap(list[0]))?'aligned':'separate'
}
function compareNotice(list){
 const code=comparable(list);
 const messages={single:'Select another record or an earlier version of this record for a side by side view.',history:'These are snapshots of the same source record. Its presence in both snapshots does not establish a rerun.',aligned:'Samples and recorded input conditions match. Statistical significance and equivalent cost or latency conditions have not been established.',separate:'Direct comparability is unverified. Samples, inputs, protocols, versions or run status may differ. Each record is shown separately.'};
 return '<div class="notice '+(code==='aligned'||code==='single'?'neutral':'')+'">'+ic('info')+' '+messages[code]+'</div>'
}
function emptySelection(what){return '<div class="panel empty"><strong>'+what+' needs at least one selected record.</strong>Use the checkboxes beside model names in the results table.<br><button class="textLink" data-goto="results">Browse results '+ic('arrow')+'</button></div>'}
function compareView(){
 const list=selected();return '<div class="topline"><h2>Compare <span class="count">'+list.length+'</span></h2><div class="actions"><button class="outline" data-act="share">'+ic('link')+' Copy link</button><button class="outline" data-goto="results">'+ic('table')+' Select records</button></div></div>'+(list.length?compareNotice(list)+'<div class="board">'+list.map(r=>'<article class="recCard"><div class="compareHead"><span class="eyelabel">'+safe(dateLabel(snap(r)))+'</span><button class="square" data-remove="'+r.id+'" aria-label="'+safe(r.name)+' remove from selection">'+ic('close')+'</button></div><h3>'+branded(r,safe(r.name))+'</h3><p class="smallnote">'+[r.section,r.track,r.setup||r.tag].filter(Boolean).map(safe).join(' / ')+'</p>'+statusTag(r)+'<p class="drawerMeta">'+safe(r.lang)+' / '+safe(r.mode)+' / '+(has(r.n)?fmtNum(r.n)+' '+safe(r.unit):'Sample unspecified')+'</p>'+metricGrid(r,true)+'<details><summary class="textLink">Method, findings and limitations</summary>'+detailsDl(r)+'</details>'+sourceLinks(r)+historyButtons(r)+'</article>').join('')+'</div><p><button class="primary" data-goto="drafts">Open drafts '+ic('arrow')+'</button></p>':emptySelection('Compare'))
}
const englishTrack=r=>r.track;
function englishConfig(r){const value=r.setup||r.tag||'';return value===r.track||value===r.name?'':value}
const englishName=r=>r.name;
function primaryClaim(r){
 if(r.status!=='Published')return r.status.toLowerCase();
 if(r.verdict)return 'published improvement verdict: '+r.verdict;
 if(has(r.acc))return (r.acc*100).toFixed(1)+'% accuracy';
 if(has(r.risk))return r.risk.toFixed(1)+'/100 risk judgement';
 if(has(r.norm))return r.norm.toFixed(1)+'/100 normalized score';
 if(has(r.err))return r.err.toFixed(2)+' PR';
 if(r.lowMetric&&has(r.lowMetric.value))return r.lowMetric.label.toLowerCase()+' '+fmtNum(r.lowMetric.value,r.lowMetric.digits??2)+(r.lowMetric.unit||'');
 if(has(r.exact))return (r.exact*100).toFixed(1)+'% exact match';
 return 'no numeric outcome reported';
}
function xLength(t){return Array.from(t.replace(/https?:\/\/\S+/g,'x'.repeat(23))).length}
function draftText(list){
 const scope=comparable(list);
 const caution=scope==='history'?'These are source snapshots of the same record. They do not establish a rerun.':scope==='aligned'?'The recorded sample and input conditions match. A difference alone does not establish a significant lead.':list.length===1?'This observation applies only to the published setup and sample.':'The records have different or unverified conditions. A direct ranking is unsupported.';
 const claims=list.map(r=>{
   const sample=has(r.n)?' (n = '+r.n.toLocaleString('en-US')+')':'';
   const config=englishConfig(r);
   return englishName(r)+(config&&config!==r.name?' ['+config.replace('questions/request','questions/request')+']':'')+' on '+englishTrack(r)+sample+' — '+primaryClaim(r)+'. Snapshot '+snap(r)+'. '+fileURL(r);
 });
 const xs=list.map(r=>{
   const warn=scope==='history'?'Same source record. A rerun is unconfirmed.':scope==='aligned'?'Matched input conditions. Significance untested here.':'Results apply to this setup. Direct comparison unverified.';
   let setup=englishConfig(r);
   if(setup===r.name||setup===r.track)setup='';
   const fixed=' '+warn+' '+fileURL(r);
   const record=[englishName(r)+(setup?' ('+setup+')':''),englishTrack(r),primaryClaim(r),has(r.n)?'n='+r.n:null,snap(r)].filter(Boolean);
   let statement=record.join(' · ')+'.';
   if(xLength(statement+fixed)>280){record[0]=r.name;statement=record.join(' · ')+'.'}
   if(xLength(statement+fixed)>280){const remaining=280-xLength(fixed)-xLength(record.slice(1).join(' · '))-7;record[0]=Array.from(r.name).slice(0,Math.max(5,remaining)).join('')+'…';statement=record.join(' · ')+'.'}
   return statement+fixed
 });
 if(list.length>1){
   const sameFile=uniq(list.map(r=>fileURL(r))).length===1;
   const sameTrack=uniq(list.map(r=>r.track)).length===1;
   const shared=sameTrack?englishTrack(list[0])+' · ':'';
   const parts=list.map(r=>(sameTrack?'':englishTrack(r)+' · ')+englishName(r)+(englishConfig(r)?' ('+englishConfig(r)+')':'')+' '+primaryClaim(r)+(sameFile?'':' ['+snap(r)+'] '+fileURL(r)));
   const note=scope==='history'?'Same record across snapshots. A rerun is unconfirmed.':scope==='aligned'?'Matched input conditions. No significance claim.':'Direct comparability is unverified.';
   const joint=shared+parts.join('. ')+'. '+note+(sameFile?' '+fileURL(list[0]):'');
   if(xLength(joint)<=280)xs.splice(0,xs.length,joint);
 }
 return {summary:claims.join('\n\n')+'\n\n'+caution,posts:xs}
}
const edited=new Map();
function draftView(){
 const list=selected();
 if(!list.length)return '<div class="topline"><h2>Research drafts</h2></div>'+emptySelection('Drafting');
 const drafts=draftText(list);const key=s.ids.join(',');
 function editor(id,title,content,post){
 const txt=edited.get(key+'#'+id)??content;
 return '<article class="noteCard"><div class="noteHead"><h3>'+safe(title)+'</h3><button class="outline" data-copy="'+id+'">'+ic('copy')+' Copy</button></div><textarea class="editor" id="'+id+'" aria-label="'+safe(title)+'" data-edit="'+safe(key+'#'+id)+'" lang="en">'+safe(txt)+'</textarea>'+(post?'<span class="sub" id="len'+id+'">'+xLength(txt)+' / 280</span>':'')+'</article>'
 }
 return '<div class="topline"><h2>Research drafts</h2><button class="outline" data-goto="compare">'+ic('compare')+' Selected records ('+list.length+')</button></div>'+compareNotice(list)+'<div class="stack">'+editor('summary','Finding summary',drafts.summary,false)+drafts.posts.map((t,i)=>editor('post'+i,'X draft'+(drafts.posts.length>1?' · '+(i+1)+' / '+drafts.posts.length:''),t,true)).join('')+'</div>'
}
// Every decision (Ümit #16874, #16875; jevgammon #16940): Backgammon's decision browser, with the fields, filters and
// wording of the old page (backgammon/decisions/, its decisions.js), read on demand from jevgammon's export in
// backgammon/decisions/: index.json, <dataset>/<setup>/<page>.json.gz (50 decisions each) and, for the filters,
// <dataset>/<setup>/risk.json.gz. It is Backgammon's Decisions panel; the address keeps dd (dataset), ds (setup slug),
// dp (page), dr (position class), dc (risk call), db (stake band) and dk (close choice), and #d<id> scrolls to a decision.
const decKeys=['dd','ds','dp','dr','dc','db','dk'];
const decRoot='backgammon/'; // decisions/ (the browser's files) and data/manifest.json (the footer line)
let decLast=null, decShown=new Map(); // the view and decisions on screen, for the PNG exports
const decFiles=new Map(), decWaiting=new Map(), decContexts=new Map(), decContextText=new Map();
let decReturn=null, decHash=decodeURIComponent(location.hash.slice(1)), decTop=false; // the results the reader came from; where to scroll
function isDecisionPanel(){return s.section==='Backgammon'&&s.panel==='Decisions'}
// its words in Turkish (locales/tr.js, hildeTurkishDecisions); L for text, Lh for HTML whose {0}, {1}… are HTML already
const decWord=m=>s.ui==='tr'&&window.hildeTurkishDecisions?.[m]||m;
const L=(m,...a)=>decWord(m).replace(/\{(\d)\}/g,(_,i)=>a[i]);
const Lh=(m,...a)=>safe(decWord(m)).replace(/\{(\d)\}/g,(_,i)=>a[i]);
const decNum=(x,d)=>{const t=Math.abs(x).toFixed(d);return s.ui==='tr'?t.replace('.',','):t};
const decSigned=(x,d)=>(x>0?'+':x<0?'\u2212':'')+decNum(x,d);
const decFixed=(x,d)=>(x<0?'\u2212':'')+decNum(x,d);
const decCount=n=>Number(n).toLocaleString(s.ui==='tr'?'tr-TR':'en-US');
const decPlural=(n,word)=>L('{0} '+word+(n===1?'':'s'),decCount(n));
const decNm=text=>'<span class="nil">'+safe(text)+'</span>';
const decKind={risk:'Risk pays',safety:'Safety pays',none:'No trade-off'};
const decCall={right_risk:'right risk',wrong_risk:'wrong risk',needless:'needless risk',missed:'missed risk',right_safety:'right safety'};
const decCallCode={right_risk:'rr',wrong_risk:'wr',needless:'nr',missed:'mr',right_safety:'rs'};
const decBand={s:'small (below 0.02)',m:'medium (0.02 to 0.08)',b:'big (above 0.08)'};
const decSources={decision:'decision-model probability',logprobs:'letter probability',choice_only:'none (the model names one play)'};
const decCloseLabel='Probabilities over plays, not sampled reasoning.';
// GitHub Pages hands a .gz file over as it is; a server that sends it with Content-Encoding: gzip hands over the JSON
async function decFetch(url){
 const res=await fetch(url);if(!res.ok)throw Error(url+': HTTP '+res.status);
 const bytes=new Uint8Array(await res.arrayBuffer());
 const text=bytes[0]===0x1f&&bytes[1]===0x8b?await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text():new TextDecoder().decode(bytes);
 return url.endsWith('.txt')?text:JSON.parse(text);
}
// a file once loaded, kept; its error is shown once, then it is tried again; while it loads, done() runs when it arrives
function decGet(path,done=decRedraw){
 const url=decRoot+path,v=decFiles.get(url);
 if(v===undefined){decFiles.set(url,null);decWaiting.set(url,new Set());decFetch(url).catch(e=>({error:e.message})).then(x=>{decFiles.set(url,x);const w=decWaiting.get(url);decWaiting.delete(url);w.forEach(f=>f())})}
 if(!v){decWaiting.get(url).add(done);return null}
 if(v.error)decFiles.delete(url);
 return v;
}
function decRedraw(){if(s.view==='results'&&isDecisionPanel()){render();persist()}}
function decContext(hash){
 if(!decContexts.has(hash))decContexts.set(hash,decFetch(decRoot+'decisions/contexts/'+encodeURIComponent(hash)+'.txt').then(t=>{decContextText.set(hash,t);return t},e=>{decContexts.delete(hash);throw e}));
 return decContexts.get(hash);
}
// the board from the mover's side: the mover at the bottom, moving 24 -> 1 (top right, along the top to the left, down,
// along the bottom to the right) and bearing off on the right
const decBoard=(()=>{
 const P=32,R=15,BAR=30,FRAME=8,TRAY=40,BAND=18,H=150,GAP=34,LEFT=FRAME,MID=FRAME+6*P,RIGHT=MID+BAR,EDGE=RIGHT+6*P,WIDTH=EDGE+FRAME+TRAY,TOP=BAND+6,BOTTOM=TOP+2*H+GAP,HEIGHT=BOTTOM+6+BAND;
 const pointX=p=>p<=6?EDGE-(p-.5)*P:p<=12?MID-(p-6.5)*P:p<=18?LEFT+(p-12.5)*P:RIGHT+(p-18.5)*P;
 function checkers(x,n,mine,fromTop,base){
  const cls=mine?'ck-me':'ck-opp',shown=Math.min(n,5);let out='';
  for(let k=0;k<shown;k++){const y=fromTop?base+R+k*2*R:base-R-k*2*R;out+='<circle class="ck '+cls+'" cx="'+x+'" cy="'+y+'" r="'+(R-1)+'"/>';if(k===shown-1&&n>5)out+='<text class="ck-count '+cls+'-text" x="'+x+'" y="'+(y+4)+'">'+n+'</text>'}
  return out;
 }
 function die(x,y,value){
  const size=26,q=size/4,spots={1:[[2,2]],2:[[1,1],[3,3]],3:[[1,1],[2,2],[3,3]],4:[[1,1],[3,1],[1,3],[3,3]],5:[[1,1],[3,1],[2,2],[1,3],[3,3]],6:[[1,1],[3,1],[1,2],[3,2],[1,3],[3,3]]}[value]||[];
  return '<rect class="die" x="'+x+'" y="'+y+'" width="'+size+'" height="'+size+'" rx="4"/>'+spots.map(([i,j])=>'<circle class="pip" cx="'+(x+i*q)+'" cy="'+(y+j*q)+'" r="2.6"/>').join('');
 }
 return d=>{
  const {points,bar,off}=d.board,barX=MID+BAR/2,midY=TOP+H+GAP/2,trayX=EDGE+FRAME+4,trayW=TRAY-4,dx=RIGHT+3*P;
  let g='<rect class="bd-frame" x="0" y="'+BAND+'" width="'+(EDGE+FRAME)+'" height="'+(BOTTOM-BAND+6)+'" rx="6"/><rect class="bd-felt" x="'+LEFT+'" y="'+TOP+'" width="'+6*P+'" height="'+(BOTTOM-TOP)+'"/><rect class="bd-felt" x="'+RIGHT+'" y="'+TOP+'" width="'+6*P+'" height="'+(BOTTOM-TOP)+'"/><rect class="bd-tray" x="'+trayX+'" y="'+BAND+'" width="'+trayW+'" height="'+(BOTTOM-BAND+6)+'" rx="4"/>';
  for(let p=1;p<=24;p++){
   const x=pointX(p),top=p>=13,tip=top?TOP+H:BOTTOM-H,base=top?TOP:BOTTOM,n=points[p-1];
   g+='<path class="bd-point '+(p%2?'bd-a':'bd-b')+'" d="M'+(x-P/2)+' '+base+'L'+(x+P/2)+' '+base+'L'+x+' '+tip+'Z"/><text class="bd-num" x="'+x+'" y="'+(top?BAND-5:HEIGHT-4)+'">'+p+'</text>';
   if(n)g+=checkers(x,Math.abs(n),n>0,top,base);
  }
  if(bar[1])g+=checkers(barX,bar[1],false,false,midY-4);
  if(bar[0])g+=checkers(barX,bar[0],true,true,midY+4);
  for(let k=0;k<off[1];k++)g+='<rect class="ck-off ck-opp" x="'+(trayX+5)+'" y="'+(TOP+2+k*7)+'" width="'+(trayW-10)+'" height="6" rx="1.5"/>';
  for(let k=0;k<off[0];k++)g+='<rect class="ck-off ck-me" x="'+(trayX+5)+'" y="'+(BOTTOM-8-k*7)+'" width="'+(trayW-10)+'" height="6" rx="1.5"/>';
  if(off[1])g+='<text class="bd-label" x="'+(trayX+trayW/2)+'" y="'+(midY-10)+'">'+off[1]+'</text>';
  g+='<text class="bd-label" x="'+(trayX+trayW/2)+'" y="'+(midY+4)+'">'+safe(L('off'))+'</text>';
  if(off[0])g+='<text class="bd-label" x="'+(trayX+trayW/2)+'" y="'+(midY+18)+'">'+off[0]+'</text>';
  g+=die(dx-30,midY-13,d.dice[0])+die(dx+4,midY-13,d.dice[1])+'<text class="bd-label bd-side" x="'+(LEFT+3*P)+'" y="'+(midY+4)+'">'+safe(L('you move 24 \u2192 1'))+'</text>';
  const label=L("Board from the mover's side, the mover at the bottom: dice {0}; on the bar: you {1}, opponent {2}; borne off: you {3}, opponent {4}; pip count: you {5}, opponent {6}.",d.dice.join('-'),bar[0],bar[1],off[0],off[1],d.pips[0],d.pips[1]);
  return '<svg class="bd" viewBox="0 0 '+WIDTH+' '+HEIGHT+'" role="img" aria-label="'+safe(label)+'">'+g+'</svg>';
 };
})();
function decPlays(d){
 const tag=(cls,text)=>'<span class="decTag '+cls+'">'+safe(L(text))+'</span>';
 const num=(x,html)=>'<td class="num" data-v="'+(x===null?'':x)+'">'+html+'</td>';
 const rows=d.plays.map((p,k)=>{
  const marks=[];
  if(k===d.chosen)marks.push(d.invalid?tag('decTagRandom','random play (invalid answer)'):tag('decTagChosen',d.program?'played':"model's choice"));
  if(p.loss===0||k===d.best)marks.push(tag('decTagBest',"engine's best"));
  if(d.close&&(k===d.close.c1||k===d.close.c2))marks.push(tag('decTagClose',k===d.close.c1?'most likely':'second most likely'));
  const cls=[k===d.chosen?'isChosen':'',k===d.best?'isBest':''].filter(Boolean).join(' ');
  return '<tr data-order="'+k+'"'+(cls?' class="'+cls+'"':'')+'><td class="decLetter">'+(p.letter===null?'':safe(p.letter))+'</td><td class="decPlay" data-t="'+safe(p.notation)+'"><code>'+safe(p.notation)+'</code>'+(marks.length?'<span class="decMarks">'+marks.join(' ')+'</span>':'')+'</td>'+num(p.equity,p.equity===null?decNm(L('not scored')):decSigned(p.equity,3))+num(p.loss,p.loss===null?decNm(L('not scored')):decFixed(p.loss,3))+num(p.probability,p.probability===null?decNm('\u2014'):decNum(100*p.probability,1)+'%')+num(p.hitting_rolls,p.hitting_rolls===null?'':p.hitting_rolls)+'<td class="decDesc" lang="en">'+safe(p.description)+'</td></tr>';
 }).join('');
 const probNote=d.program?'This player is a program and gives no probabilities.':d.probability_source==='choice_only'?'This setup names one play and gives no probability; its recorded 1.0 is not a confidence.':d.probability_source===null?'No probabilities were recorded for this decision.':d.group_size?'A dash: the play was not in the request that decided.':'';
 const groupNote=!d.group_size||d.program?'':L(d.prompt&&d.prompt.format==='letters'?' The plays were sent in groups of {0}, each lettered from A in its own request, and the group winners were then compared in a further request.':' The plays were sent in groups of {0}, and the group winners were then compared in a further request.',decCount(d.group_size));
 const th=(label,n)=>'<th scope="col" aria-sort="none"'+(n?' class="num"':'')+'><button class="sortHead" data-dec-sort title="'+safe(L('Sort by this column'))+'">'+safe(L(label))+'</button></th>';
 return '<p class="decSwipe">'+safe(L('Swipe for more columns \u2192'))+'</p><div class="decPlaysWrap"><table class="decPlays"><caption>'+safe(L(d.program?'{0}, in the order shown to the player':'{0}, in the order shown to the model',decPlural(d.plays.length,'legal play')))+'</caption><thead class="tableHead"><tr>'+th('Letter')+th('Play')+th('Engine equity',1)+th('Equity lost',1)+th('Model probability',1)+th('Opponent hits (of 36)',1)+th('Consequences, as shown')+'</tr></thead><tbody>'+rows+'</tbody></table></div><p class="decPngLine"><button class="outline" data-dec-png>'+safe(L('Download PNG'))+'</button></p><p class="decNote">'+safe(L("Engine equity: GNUbg 2-ply, cubeless, for the side to move. Equity lost: the best play's equity minus this play's.")+groupNote+(probNote?' '+L(probNote):''))+'</p>';
}
// a play table's head sorts it: ascending, descending, then the order shown to the model
function decSort(b){
 const th=b.closest('th'),body=th.closest('table').tBodies[0],col=[...th.parentNode.children].indexOf(th),state=th.getAttribute('aria-sort');
 const next=state==='ascending'?'descending':state==='descending'?'none':'ascending',sign=next==='ascending'?1:-1;
 th.parentNode.querySelectorAll('th').forEach(h=>h.setAttribute('aria-sort','none'));th.setAttribute('aria-sort',next);
 const key=r=>{const c=r.cells[col];return c.dataset.v===undefined?(c.dataset.t??c.textContent).trim().toLowerCase():c.dataset.v===''?null:Number(c.dataset.v)};
 [...body.rows].sort((a,b)=>{
  if(next==='none')return a.dataset.order-b.dataset.order;
  const x=key(a),y=key(b);if(x===null||y===null)return x===y?0:x===null?1:-1;
  return sign*(typeof x==='number'?x-y:x.localeCompare(y,'en',{numeric:true}))||a.dataset.order-b.dataset.order;
 }).forEach(r=>body.append(r));
}
function decPrompt(d){
 if(d.program)return '<p class="decSmall">'+safe(L('This player is a program; it gets no prompt.'))+'</p>';
 const prompt=d.prompt;
 if(!prompt)return '<p class="decSmall">'+decNm(L('Not recorded'))+' '+safe(L('The prompt of this decision is not in the prompt store yet.'))+'</p>';
 const pre=text=>'<pre class="decPre" lang="en">'+safe(text)+'</pre>',label=text=>'<p class="decLabel">'+safe(text)+'</p>';
 let h='<p class="decSmall">'+safe(L(prompt.format==='letters'?'Chat request: a system prompt and one user message with lettered options.':'Decision request: the state text and the options as a list of choices.'))+(s.ui==='tr'?' '+safe(L('The texts are in English, as sent.')):'')+'</p>';
 if(prompt.context){const text=decContextText.get(prompt.context);h+='<details class="decContext" data-hash="'+safe(prompt.context)+'"'+(text?' data-loaded="1"':'')+'><summary>'+safe(L('Rules text shared by every prompt (shown above the turn text)'))+'</summary>'+pre(text||L('Loading…'))+'</details>'}
 const n=prompt.requests.length;
 prompt.requests.forEach((r,i)=>{
  if(n>1)h+='<h5 class="decRequest">'+safe(L('Request {0} of {1}',i+1,n))+'</h5>';
  (r.system_prefix||[]).forEach((block,j)=>{h+='<details class="decSystem"><summary>'+safe(L('System block {0}, sent before the system prompt',j+1))+'</summary>'+pre(block)+'</details>'});
  if(r.system)h+='<details class="decSystem"><summary>'+safe(L('System prompt'))+'</summary>'+pre(r.system)+'</details>';
  h+=label(L(prompt.format==='letters'?'User message, after the rules text':'State, after the rules text'))+pre(r.text);
  if(r.instructions)h+=label(L('Instructions'))+pre(r.instructions);
  if(r.options)h+=label(L('Options sent, in this order ({0})',decCount(r.options.length)))+'<ol class="decOptions" lang="en">'+r.options.map(([notation,description])=>'<li><code>'+safe(notation)+'</code> '+safe(description)+'</li>').join('')+'</ol>';
 });
 return h;
}
function decRiskText(d){
 if(!d.risk)return decNm(L(d.invalid?'invalid answer: not classified':'not scored'));
 const kind='<span class="decTag decKind-'+safe(d.risk.class)+'">'+safe(L(decKind[d.risk.class]))+'</span>';
 if(d.risk.class==='none')return kind+' '+safe(L('every legal play leaves the same number of hitting rolls'));
 const band=d.risk.band?L(d.risk.class==='risk'?' ({0} stake)':' ({0} equity lost)',L(d.risk.band)):'';
 const robust=d.risk.call_robust!==d.risk.call?L('; at the 0.02 margin: {0}',L(decCall[d.risk.call_robust]||'No trade-off')):'';
 return kind+' '+safe(L(decCall[d.risk.call]||'')+', '+L('stake {0}',decFixed(d.risk.stake,3))+band+robust);
}
// Close choices (Method spec 2026-10-24 §9): p1, p2 and both candidate plays of an eligible decision
function decCloseText(d){
 if(!d.close)return decNm(L('N/A: no full probability distribution for this decision'));
 const c=d.close,play=p=>(p.letter?safe(p.letter)+': ':'')+'<code>'+safe(p.notation)+'</code>';
 return (c.close?'<strong>'+safe(L('yes'))+'</strong>':safe(L('no')))+': p1 '+decFixed(c.p1,4)+' ('+play(d.plays[c.c1])+'), p2 '+decFixed(c.p2,4)+' ('+play(d.plays[c.c2])+'); p1 + p2 '+decFixed(c.p1+c.p2,4)+'. <span class="decSmall">'+safe(L(decCloseLabel))+'</span>';
}
function decFacts(d,dataset){
 const rows=[],add=(term,html)=>rows.push('<dt>'+safe(L(term))+'</dt><dd>'+html+'</dd>');
 const play=p=>(p.letter?safe(p.letter)+': ':'')+'<code>'+safe(p.notation)+'</code>',lost=p=>p.loss===null?'':safe(L(', equity lost {0}',decFixed(p.loss,3)));
 add('Dice',safe(d.dice.join('-')));
 add('Pip count',safe(L('you {0}, opponent {1}',decCount(d.pips[0]),decCount(d.pips[1]))));
 add('Phase',safe(d.tag?L(d.phase)+' \u00b7 '+L(d.tag):L(d.phase)));
 add('Side',safe(L(d.side)));
 const chosen=d.chosen===null?null:d.plays[d.chosen];
 if(d.invalid)add('Answer',safe(L('invalid'))+(chosen?Lh('; the runner played {0} at random','<code>'+safe(chosen.notation)+'</code>'):''));
 else if(chosen)add(d.program?'Played':"Model's choice",play(chosen)+lost(chosen));
 if(d.best!==null)add("Engine's best",'<code>'+safe(d.plays[d.best].notation)+'</code>');
 if(d.risk&&has(d.risk.best_safe)){const p=d.plays[d.risk.best_safe];add('Best safe play',Lh('{0}, {1} hitting rolls','<code>'+safe(p.notation)+'</code>',decCount(p.hitting_rolls))+lost(p))}
 add('Risk call',decRiskText(d));
 if(!d.program&&d.league!==null)add('Close choice',decCloseText(d));
 if(!d.program){
  add('Option groups',safe(d.group_size?L('split into groups of {0}; the group winners were compared',decCount(d.group_size)):L('all plays in one request')));
  add('Probability',safe(d.probability_source?L(decSources[d.probability_source]||d.probability_source):L('none recorded')));
 }
 if(has(d.request_seconds))add('Request time',safe(decNum(d.request_seconds,1)+' s'));
 if(d.retry_seconds)add('Retry and wait time',safe(decNum(d.retry_seconds,1)+' s'));
 if(has(d.cost_usd))add('Cost',safe('$'+decNum(d.cost_usd,4)));
 add('Version',safe(dataset.version));
 return '<dl class="decFacts">'+rows.join('')+'</dl>';
}
function decLink(changes){const keep=s;s={...s,...changes};const q=serialize();s=keep;return '?'+q}
function decCard(d,v){
 const where=[L(v.dataset.label),d.league===null?L('position {0}',d.id):L('game {0}',d.game),L('turn {0}',d.turn_no)].join(' \u00b7 ');
 const link=decLink({dp:d._page||v.p,dr:'all',dc:'all',db:'all',dk:'all'})+'#d'+encodeURIComponent(d.id);
 const flag=d.invalid?'<p class="decFlag">'+safe(L(d.chosen===null?"Invalid answer: no play was chosen; it does not count as the model's choice.":"Invalid answer: the runner played a random legal play; it does not count as the model's choice."))+'</p>':'';
 return '<article class="decCard" id="d'+safe(d.id)+'"><div class="decCardHead"><h3><a href="'+safe(link)+'" data-dec-link>'+safe(L('Decision {0}',d.id))+'</a></h3><p class="sub">'+safe(where)+'</p></div>'+flag+'<div class="decTopRow"><figure class="decBoard">'+decBoard(d)+'</figure>'+decFacts(d,v.dataset)+'</div><section><h4>'+safe(L('Legal plays'))+'</h4>'+decPlays(d)+'</section><details class="decSeen"><summary>'+safe(L('Position as the model saw it'))+'</summary>'+decPrompt(d)+'</details></article>';
}
function decResolve(idx){
 const dataset=idx.datasets.find(x=>x.id===s.dd)||idx.datasets[0];
 const setup=dataset.setups.find(x=>x.slug===s.ds)||dataset.setups.find(x=>x.decisions>0)||dataset.setups[0];
 const r=['risk','safety','none'].includes(s.dr)?s.dr:'all',cc=setup?.risk?.close;
 const v={d:dataset.id,s:setup?setup.slug:'',p:Math.max(1,s.dp||1),r,c:r!=='none'&&Object.values(decCallCode).includes(s.dc)?s.dc:'all',b:r!=='none'&&['s','m','b'].includes(s.db)?s.db:'all',k:cc&&cc.close+cc.other>0&&['close','other'].includes(s.dk)?s.dk:'all',dataset,setup,total:0,pages:0};
 Object.assign(s,{dd:v.d,ds:v.s,dr:v.r,dc:v.c,db:v.b,dk:v.k});
 return v;
}
const decFiltered=v=>v.r!=='all'||v.c!=='all'||v.b!=='all'||v.k!=='all';
// the risk marks of every decision of a setup, [page, id, class r/s/n, call rr/wr/nr/mr/rs, band s/m/b, close 1/0]:
// the band is the stake for Risk pays decisions and the equity lost for needless risks (B6.3)
function decMatches(rows,v){
 const code={risk:'r',safety:'s',none:'n'}[v.r],close={close:1,other:0}[v.k];
 return rows.filter(([,,cls,call,band,cc])=>cls!==null&&(!code||cls===code)&&(v.c==='all'||call===v.c)&&(v.b==='all'||band===v.b)&&(close===undefined||cc===close));
}
function decPager(v,size){
 if(!v.pages)return '';
 const first=(v.p-1)*size+1,last=Math.min(v.p*size,v.total);
 return '<nav class="decPager" aria-label="'+safe(L('Pages'))+'"><button class="outline" data-dec-step="-1"'+(v.p<=1?' disabled':'')+'>'+safe(L('\u2190 Previous'))+'</button><label class="decPage">'+safe(L('Page'))+' <input type="number" inputmode="numeric" min="1" max="'+v.pages+'" value="'+v.p+'" data-dec="dp" aria-label="'+safe(L('Page number'))+'"> '+safe(L('of {0}',decCount(v.pages)))+'</label><button class="outline" data-dec-step="1"'+(v.p>=v.pages?' disabled':'')+'>'+safe(L('Next \u2192'))+'</button><span class="decInView">'+safe(L('decisions {0}\u2013{1} of {2}',decCount(first),decCount(last),decCount(v.total))+(decFiltered(v)?L(' (filtered)'):''))+'</span></nav>';
}
function decControls(v,idx){
 const opt=(list,cur)=>list.map(([k,l])=>'<option value="'+safe(k)+'"'+(k===cur?' selected':'')+'>'+safe(l)+'</option>').join('');
 const field=(title,key,options,off)=>'<label class="field"><span class="fieldTitle">'+safe(L(title))+'</span><select data-dec="'+key+'"'+(off?' disabled':'')+'>'+options+'</select></label>';
 const rc=v.setup?.risk||{},calls=rc.calls||{},cc=rc.close||{close:0,other:0},hasClose=cc.close+cc.other>0,n=x=>' ('+decCount(x||0)+')';
 const method='<button class="textLink" data-panel="Method" data-anchor="risk">'+safe(L('Method'))+'</button>',closeMethod='<button class="textLink" data-panel="Method" data-anchor="close-choices">'+safe(L('Method'))+'</button>';
 return '<div class="decControls">'+field('Dataset','dd',opt(idx.datasets.map(x=>[x.id,L(x.label)]),v.d))
  +field('Setup','ds',opt(v.dataset.setups.map(x=>[x.slug,x.name+' ('+(x.decisions?decPlural(x.decisions,'decision'):L('none scored yet'))+')']),v.s))
  +field('Position class','dr',opt([['all',L('All decisions')],...Object.entries(decKind).map(([k,l])=>[k,L(l)+n(rc[k])])],v.r))
  +field('Risk call','dc',opt([['all',L('Any risk call')],...Object.entries(decCallCode).map(([k,c])=>[c,L(decCall[k])+n(calls[k])])],v.c),v.r==='none')
  +field('Stake, or equity lost by a needless risk','db',opt([['all',L('Any size')],...Object.entries(decBand).map(([k,l])=>[k,L(l)])],v.b),v.r==='none')
  +field('Close choice','dk',opt(hasClose?[['all',L('All decisions')],['close',L('Close choices ({0})',decCount(cc.close))],['other',L('Not close choices ({0})',decCount(cc.other))]]:[['all',L('N/A: no full probability distribution')]],v.k),!hasClose)
  +'</div><p class="decNote"><span class="pill">'+safe(L(v.dataset.badge))+'</span></p>'+(v.dataset.note?'<p class="decNote">'+safe(L(v.dataset.note))+'</p>':'')
  +'<p class="decNote">'+Lh('Position class, stake and risk call as defined in {0}; hit risk only: gammon risk and priming are not in it.',method)+'</p>'
  +(v.k!=='all'?'<p class="decNote">'+Lh('Close choice: the second most likely play has at least half the probability of the first ({0}). Each decision shows p1, p2 and both plays.',closeMethod)+' '+safe(L(decCloseLabel))+'</p>':'');
}
function decisionsView(){
 const links=[['Disagreements','Where models disagree'],['Phases','Phases'],['Compare plays','Compare']].filter(([p])=>panelNames().includes(p));
 const head='<div class="topline"><div><span class="eyelabel">'+safe(L('Every decision'))+'</span><h2>'+safe(L('What did each model see, and what did it play?'))+'</h2></div><div class="actions"><button class="outline" data-dec-page-png>'+safe(L('Export page as PNG'))+'</button><button class="outline" data-dec-back>'+ic('left')+' '+safe(L('Back to results'))+'</button></div></div>'+(links.length?'<nav class="decLinks" aria-label="'+safe(L('More on decisions'))+'">'+links.map(([p,t])=>'<button class="textLink" data-panel="'+safe(p)+'">'+safe(L(t))+'</button>').join('')+'</nav>':'');
 const about='<details class="decAbout"><summary>'+safe(L('About this page'))+'</summary><p>'+safe(L("Every scored decision, 50 to a page: the board, the position exactly as the model saw it, every legal play with its consequences, the engine's equity for each play, the equity the chosen play lost and the model's probability where it gives one. Click a column header to sort a play table."))+'</p></details>';
 // the whole view is in the reader's language already: the page-wide translation (HildeI18n) leaves it alone
 const version=decVersionText(),wrap=body=>'<div class="decView" data-verbatim>'+head+body+about+(version?'<p class="decVersion">'+safe(version)+'</p>':'')+'</div>',status=html=>'<p class="decStatus" role="status">'+html+'</p>';
 const idx=decGet('decisions/index.json');
 if(!idx)return wrap(status('<span class="decLoading">'+safe(L('Loading…'))+'</span>'));
 if(idx.error)return wrap(status('<span class="decError">'+safe(L('Could not load the list of decisions ({0}).',idx.error))+'</span>'));
 if(!idx.datasets.length)return wrap(status(decNm(L('Analysis pending'))));
 const v=decResolve(idx),size=idx.page_size;
 const panel=(line,list='')=>wrap('<section class="panel decPanel">'+decControls(v,idx)+decPager(v,size)+'</section>'+status(line)+list+(list?'<div class="decPagerBottom">'+decPager(v,size)+'</div>':''));
 if(!v.setup||!v.setup.decisions)return panel(decNm(L('Analysis pending'))+' '+safe(L('No decision of this setup has been scored yet.')));
 const page=pg=>decGet('decisions/'+encodeURIComponent(v.d)+'/'+encodeURIComponent(v.s)+'/'+pg+'.json.gz');
 let decisions=null,fail=null;
 if(decFiltered(v)){
  const rows=decGet('decisions/'+encodeURIComponent(v.d)+'/'+encodeURIComponent(v.s)+'/risk.json.gz');
  if(rows?.error)fail=rows.error;
  else if(rows){
   const hits=decMatches(rows,v);v.total=hits.length;v.pages=Math.ceil(hits.length/size);v.p=Math.min(v.p,Math.max(1,v.pages));
   const slice=hits.slice((v.p-1)*size,v.p*size),wanted=uniq(slice.map(([pg])=>pg)),docs=wanted.map(page);
   fail=docs.find(x=>x?.error)?.error||null;
   if(!fail&&docs.every(Boolean)){const byId=new Map(docs.flatMap((doc,k)=>doc.decisions.map(d=>[String(d.id),{...d,_page:wanted[k]}])));decisions=slice.map(([,id])=>byId.get(String(id))).filter(Boolean)}
  }
 }else{
  v.total=v.setup.decisions;v.pages=v.setup.pages;v.p=Math.min(v.p,Math.max(1,v.pages));
  const doc=page(v.p);if(doc?.error)fail=doc.error;else if(doc)decisions=doc.decisions;
 }
 s.dp=v.p;
 if(fail)return panel('<span class="decError">'+safe(L('Could not load this page of decisions ({0}).',fail))+'</span>');
 if(!decisions)return panel('<span class="decLoading">'+safe(L('Loading…'))+'</span>');
 decLast=v;decShown=new Map(decisions.map(d=>[String(d.id),d]));
 const invalid=decisions.filter(d=>d.invalid).length;
 return panel(safe(v.total===0?L('{0}: no decision matches these filters.',v.setup.name):L('{0}: page {1} of {2}, {3}, {4} on this page ({5} in all {6}).',v.setup.name,decCount(v.p),decCount(v.pages),decPlural(decisions.length,'decision'),decPlural(invalid,'invalid answer'),decPlural(v.setup.invalid,'invalid answer'),decCount(v.setup.decisions))),'<div class="decList">'+decisions.map(d=>decCard(d,v)).join('')+'</div>');
}
// after a redraw: to the decision the address names once it is in, else to the top of what the reader asked for
function decAfter(){
 const target=decHash&&document.getElementById(decHash);
 if(target){decHash='';decTop=false;target.scrollIntoView();return}
 if(decTop==='entry')scrollTo(0,0);else if(decTop==='page')$('.decPanel')?.scrollIntoView({block:'start'});
 if(!$('.decLoading'))decTop=false; // once more when the page is in
}
// a results row's drawer: 'Every decision' when the row's setup has its decisions in the export
function decEntry(r){
 const m=/^backgammon\/models\/([^/]+)\/([^/]+)\/$/.exec(r.page||'');if(!m)return '';
 const idx=decGet('decisions/index.json',()=>{if($('#modal').open&&s.detail===r.id)showDetail(r,false)});
 return idx?.datasets?.some(x=>x.id===m[1]&&x.setups.some(y=>y.slug===m[2]))?'<button class="outline" data-dec-open="'+safe(m[1])+'" data-dec-slug="'+safe(m[2])+'">'+ic('board')+' '+safe(L('Every decision'))+'</button>':'';
}
function decOpen(dataset,slug){
 if(!isDecisionPanel())decReturn={state:{...s},y:scrollY};
 closeModal();
 const league=/^League (\d+)$/.exec(s.track); // from the table's own button: the league in view
 Object.assign(s,{view:'results',section:'Backgammon',panel:'Decisions',detail:'',dd:dataset||(league?'league-'+league[1]:''),ds:slug||'',dp:1,dr:'all',dc:'all',db:'all',dk:'all'});
 decHash='';decTop='entry';render();persist(true);
}
function decBack(){
 const back=decReturn;decReturn=null;
 s=back?{...back.state,ui:s.ui}:{...s,panel:'Results',track:'',page:1};
 Object.assign(s,{dd:'',ds:'',dp:1,dr:'all',dc:'all',db:'all',dk:'all'});
 decHash='';render();persist(true);scrollTo(0,back?back.y:0);
 if(back?.state.detail&&records.has(back.state.detail))showDetail(records.get(back.state.detail));
}
function decGo(next){Object.assign(s,next);decHash='';decTop='page';render();persist(true)}
function decSet(key,value){
 if(key!=='dp')return decGo({[key]:value,dp:1,...(key==='dd'?{ds:''}:{})});
 const p=parseInt(value,10);if(p)decGo({dp:p});
}
function decClick(b){
 const d=b.dataset;
 if(d.decOpen!==undefined)decOpen(d.decOpen,d.decSlug);
 else if(d.decStep)decGo({dp:s.dp+Number(d.decStep)});
 else if(d.decBack!==undefined)decBack();
 else if(d.decSort!==undefined)decSort(b);
 else if(d.decPng!==undefined)decPng.run(b,()=>decPng.table(b.closest('.decCard')));
 else if(d.decPagePng!==undefined)decPng.run(b,decPng.page);
 else return false;
 return true;
}
// a decision's own link (its page, no filters, #d<id>) stays in the page
document.addEventListener('click',e=>{
 const a=e.target.closest('a[data-dec-link]');if(!a||e.button||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
 e.preventDefault();history.pushState(null,'',a.href);s=fromURL();decHash=decodeURIComponent(location.hash.slice(1));render();persist();
});
document.addEventListener('toggle',e=>{
 const box=e.target;if(!box.matches?.('details.decContext')||!box.open||box.dataset.loaded)return;
 const out=box.querySelector('pre');
 decContext(box.dataset.hash).then(t=>{out.textContent=t;box.dataset.loaded='1'},err=>{out.textContent=L('Could not load the rules text ({0}).',err.message)});
},true);
window.addEventListener('popstate',()=>{decHash=decodeURIComponent(location.hash.slice(1))});
window.addEventListener('hashchange',()=>{if(isDecisionPanel()){decHash=decodeURIComponent(location.hash.slice(1));decAfter()}});
// PNG exports as on the old page (its png.js, Can, 23 Oct 2026): 'Download PNG' under each decision's plays table, the table
// with every column and row, the headings above it and its note under it; 'Export page as PNG', the whole page, its
// scrolling boxes opened, in parts of at most 16,000 pixels. In small type under each: league, rows shown, filters and
// sort, the results version, theme and address. No library: the page is read box by box (background, borders, rounding,
// inset rules) and line by line (each line of text where the browser placed it, in its font and colour); SVG is drawn as
// an image.
const decPng=(()=>{
 const LIMIT=16000,PAD=16,px=v=>parseFloat(v)||0;
 const clear=c=>!c||c==='transparent'||/^rgba\(.*,\s*0\)$/.test(c)||/\/\s*0\)$/.test(c);
 const ALIGN={right:'right',end:'right','-webkit-right':'right',center:'center','-webkit-center':'center'};
 const SVG_PROPS=['fill','stroke','stroke-width','stroke-dasharray','stroke-linecap','stroke-linejoin','opacity','fill-opacity','stroke-opacity','font-family','font-size','font-weight','font-style','text-anchor','dominant-baseline','display','visibility','paint-order','letter-spacing'];
 const fontOf=cs=>cs.fontStyle+' '+cs.fontWeight+' '+cs.fontSize+' '+cs.fontFamily;
 const transform=(t,cs)=>cs.textTransform==='uppercase'?t.toUpperCase():cs.textTransform==='lowercase'?t.toLowerCase():cs.textTransform==='capitalize'?t.replace(/(^|\s)(\S)/g,(_,a,b)=>a+b.toUpperCase()):t;
 function splitTop(v){const out=[];let depth=0,from=0;for(let i=0;i<v.length;i++){if(v[i]==='(')depth++;else if(v[i]===')')depth--;else if(v[i]===','&&!depth){out.push(v.slice(from,i).trim());from=i+1}}out.push(v.slice(from).trim());return out}
 // the first linear gradient of a background-image: {angle, stops: [[colour, 0..1]]}; a repeating one in its first colour
 function gradient(value){
  const m=value.match(/(repeating-)?linear-gradient\(/);if(!m)return null;
  let i=m.index+m[0].length,depth=0;const start=i;
  for(;i<value.length;i++){if(value[i]==='(')depth++;else if(value[i]===')'){if(!depth)break;depth--}}
  const parts=splitTop(value.slice(start,i)),SIDES={'to top':0,'to right':90,'to bottom':180,'to left':270};let angle=180;
  if(parts[0] in SIDES)angle=SIDES[parts.shift()];else if(/^-?[\d.]+deg$/.test(parts[0]))angle=parseFloat(parts.shift());else if(/^-?[\d.]+turn$/.test(parts[0]))angle=360*parseFloat(parts.shift());else if(/^to /.test(parts[0]))parts.shift();
  const stops=parts.map(p=>{const x=p.match(/^(.*?\)|[#\w-]+)(?:\s+(-?[\d.]+)%)?/);return x?[x[1],x[2]===undefined?null:Number(x[2])/100]:null}).filter(Boolean);
  if(!stops.length)return null;
  const rad=angle*Math.PI/180;
  if(m[1])return {angle:rad,stops:[[stops[0][0],0],[stops[0][0],1]]};
  stops.forEach((x,k)=>{if(x[1]===null)x[1]=stops.length===1?0:k/(stops.length-1)});
  return {angle:rad,stops};
 }
 // drawing steps for an element and everything in it, in viewport coordinates, read in one go
 function read(root){
  const ops=[],range=document.createRange(),rectOf=(node,a,b)=>{range.setStart(node,a);range.setEnd(node,b);return range.getBoundingClientRect()};
  function box(el,cs,st){
   if(cs.visibility==='hidden')return;
   for(const r of cs.display==='inline'?[...el.getClientRects()]:[el.getBoundingClientRect()]){
    if(r.width<=0||r.height<=0)continue;
    const rr=cs.borderTopLeftRadius,rad=Math.min(rr.endsWith('%')?px(rr)/100*Math.min(r.width,r.height):px(rr),r.width/2,r.height/2);
    const at={x:r.left,y:r.top,w:r.width,h:r.height,rad,clip:st.clip,alpha:st.alpha};
    if(!clear(cs.backgroundColor))ops.push({k:'box',fill:cs.backgroundColor,...at});
    if(cs.backgroundImage!=='none'){const g=gradient(cs.backgroundImage);if(g)ops.push({k:'grad',g,...at})}
    if(cs.boxShadow!=='none')splitTop(cs.boxShadow).filter(x=>/\binset\b/.test(x)).forEach(x=>{
     const colour=(x.match(/(rgba?\([^)]*\)|color\([^)]*\)|#[0-9a-f]+)/i)||[])[1];
     const [ox=0,oy=0,blur=0,spread=0]=(x.replace(/(rgba?|color)\([^)]*\)/g,'').match(/-?[\d.]+px/g)||[]).map(px);
     if(!colour||clear(colour)||blur)return;
     const strip=(x,y,w,h)=>ops.push({k:'box',fill:colour,x,y,w,h,rad:0,clip:st.clip,alpha:st.alpha});
     if(ox>0)strip(r.left,r.top,ox,r.height);if(ox<0)strip(r.right+ox,r.top,-ox,r.height);if(oy>0)strip(r.left,r.top,r.width,oy);if(oy<0)strip(r.left,r.bottom+oy,r.width,-oy);
     if(!ox&&!oy&&spread>0)ops.push({k:'ring',colour,lw:spread,...at,x:r.left+spread/2,y:r.top+spread/2,w:r.width-spread,h:r.height-spread});
    });
    const sides=['Top','Right','Bottom','Left'].map(x=>({w:cs['border'+x+'Style']==='none'||cs['border'+x+'Style']==='hidden'?0:px(cs['border'+x+'Width']),c:cs['border'+x+'Color']}));
    if(rad>0&&sides.every(x=>x.w===sides[0].w&&x.c===sides[0].c)&&sides[0].w>0&&!clear(sides[0].c)){const lw=sides[0].w;ops.push({k:'ring',colour:sides[0].c,lw,...at,x:r.left+lw/2,y:r.top+lw/2,w:r.width-lw,h:r.height-lw,rad:Math.max(0,rad-lw/2)})}
    else{
     const [t,rt,b,l]=sides,strip=(x,X,y,w,h)=>{if(x.w>0&&!clear(x.c))ops.push({k:'box',fill:x.c,x:X,y,w,h,rad:0,clip:st.clip,alpha:st.alpha})};
     strip(t,r.left,r.top,r.width,t.w);strip(b,r.left,r.bottom-b.w,r.width,b.w);strip(l,r.left,r.top,l.w,r.height);strip(rt,r.right-rt.w,r.top,rt.w,r.height);
    }
   }
  }
  function text(node,cs,st){
   const data=node.data,first=data.search(/\S/);
   if(first<0||cs.visibility==='hidden')return;
   const end=data.trimEnd().length;range.setStart(node,first);range.setEnd(node,end);
   const lines=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0);if(!lines.length)return;
   // where each line starts: the first character whose box sits on that line (a binary search per line break); line
   // boxes may overlap when the line height is tight, so a line is told by its top, half-way to the next one
   const starts=[first],topAt=k=>{for(let j=k;j<end;j++){const r=rectOf(node,j,j+1);if(r.width>0||r.height>0)return r.top}return Infinity};
   let prev=lines[0].top;
   for(let i=1;i<lines.length;i++){
    if(lines[i].top<=prev+1)continue;
    const cut=(prev+lines[i].top)/2;prev=lines[i].top;
    let lo=starts[starts.length-1]+1,hi=end;
    while(lo<hi){const mid=(lo+hi)>>1;if(topAt(mid)>cut)hi=mid;else lo=mid+1}
    if(lo<end&&lo>starts[starts.length-1])starts.push(lo);
   }
   starts.push(end);
   const pre=/^(pre|pre-wrap|break-spaces)$/.test(cs.whiteSpace),align=ALIGN[cs.textAlign]||'left',font=fontOf(cs);
   for(let i=0;i+1<starts.length;i++){
    const seg=data.slice(starts[i],starts[i+1]),lead=seg.search(/\S/);if(lead<0)continue;
    const a=starts[i]+lead,z=starts[i]+seg.trimEnd().length,r0=rectOf(node,a,a+1),r1=rectOf(node,z-1,z);
    let t=data.slice(a,z);t=pre?t.replace(/\t/g,'    '):t.replace(/\s+/g,' ');
    ops.push({k:'text',text:transform(t,cs),x0:r0.left,x1:Math.max(r1.right,r0.right),top:r0.top,h:r0.height,font,colour:cs.color,align,ls:cs.letterSpacing,under:st.under,clip:st.clip,alpha:st.alpha});
   }
  }
  function pseudo(el,cs,which,st){
   const ps=getComputedStyle(el,which),m=ps.content&&ps.content.match(/^"((?:[^"\\]|\\.)*)"$/);
   if(!m||!m[1].trim()||ps.display==='none'||/absolute|fixed/.test(ps.position)||ps.visibility==='hidden')return;
   range.selectNodeContents(el);
   const rects=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0),r=el.getBoundingClientRect(),ref=which==='::after'?rects[rects.length-1]:rects[0];
   const x=which==='::after'?(ref?ref.right:r.right-px(cs.paddingRight)):r.left+px(cs.borderLeftWidth)+px(cs.paddingLeft);
   ops.push({k:'text',text:transform(m[1].replace(/\\(.)/g,'$1'),ps),x0:x,x1:null,top:ref?ref.top:r.top,h:ref?ref.height:r.height,font:fontOf(ps),colour:ps.color,align:'left',ls:ps.letterSpacing,under:null,clip:st.clip,alpha:st.alpha});
  }
  function control(el,cs,st){
   const r=el.getBoundingClientRect();if(!r.width||!r.height||cs.visibility==='hidden')return;
   const type=(el.type||'').toLowerCase();
   if(type==='checkbox'||type==='radio'){
    const sz=Math.min(r.width,r.height);
    ops.push({k:'ring',colour:cs.color,lw:1,x:r.left+.5,y:r.top+.5,w:sz-1,h:sz-1,rad:type==='radio'?sz/2:3,clip:st.clip,alpha:st.alpha});
    if(el.checked)ops.push({k:'box',fill:cs.accentColor==='auto'?cs.color:cs.accentColor,x:r.left+3,y:r.top+3,w:sz-6,h:sz-6,rad:type==='radio'?sz/2:2,clip:st.clip,alpha:st.alpha});
    return;
   }
   const value=el.tagName==='SELECT'?(el.selectedOptions[0]?.text||''):(el.value||el.placeholder||'');if(!value)return;
   const left=r.left+px(cs.borderLeftWidth)+px(cs.paddingLeft),size=px(cs.fontSize),right=r.right-px(cs.borderRightWidth)-px(cs.paddingRight)-(el.tagName==='SELECT'?size:0);
   ops.push({k:'text',text:value.replace(/\s+/g,' ').trim(),x0:left,x1:right,top:r.top+(r.height-size*1.2)/2,h:size*1.2,font:fontOf(cs),colour:cs.color,align:'left',ls:cs.letterSpacing,under:null,clip:{x1:left,y1:r.top,x2:right,y2:r.bottom},alpha:st.alpha,fit:false});
   if(el.tagName==='SELECT')ops.push({k:'text',text:'\u25BE',x0:right+size*.2,x1:null,top:r.top+(r.height-size*1.2)/2,h:size*1.2,font:fontOf(cs),colour:cs.color,align:'left',ls:'normal',under:null,clip:st.clip,alpha:st.alpha});
  }
  function svg(el,cs,st){
   const r=el.getBoundingClientRect();if(!r.width||!r.height||cs.visibility==='hidden')return;
   const clone=el.cloneNode(true),from=[el,...el.querySelectorAll('*')];
   [clone,...clone.querySelectorAll('*')].forEach((c,i)=>{const x=getComputedStyle(from[i]);SVG_PROPS.forEach(p=>c.style.setProperty(p,x.getPropertyValue(p)))});
   clone.setAttribute('width',r.width);clone.setAttribute('height',r.height);clone.style.setProperty('display','block');
   ops.push({k:'svg',markup:new XMLSerializer().serializeToString(clone),x:r.left,y:r.top,w:r.width,h:r.height,clip:st.clip,alpha:st.alpha});
  }
  function walk(el,st){
   const cs=getComputedStyle(el);if(cs.display==='none')return;
   const alpha=st.alpha*px(cs.opacity===''?'1':cs.opacity);if(alpha<=0)return;
   st={...st,alpha};box(el,cs,st);
   const tag=el.tagName;
   if(tag==='svg'){svg(el,cs,st);return}
   if(tag==='IMG'||tag==='CANVAS'){
    const r=el.getBoundingClientRect(),ok=tag==='CANVAS'||(el.complete&&el.naturalWidth&&new URL(el.currentSrc||el.src,location.href).origin===location.origin);
    if(ok&&r.width&&r.height&&cs.visibility!=='hidden')ops.push({k:'img',el,x:r.left,y:r.top,w:r.width,h:r.height,clip:st.clip,alpha});
    return;
   }
   if(tag==='SELECT'||tag==='INPUT'||tag==='TEXTAREA'){control(el,cs,st);return}
   if(/^(SCRIPT|STYLE|TEMPLATE|NOSCRIPT|OPTION)$/.test(tag))return;
   if(/underline/.test(cs.textDecorationLine))st={...st,under:clear(cs.textDecorationColor)?cs.color:cs.textDecorationColor};
   if(el!==root&&(cs.overflowX!=='visible'||cs.overflowY!=='visible')){
    const r=el.getBoundingClientRect(),c={x1:r.left+px(cs.borderLeftWidth),y1:r.top+px(cs.borderTopWidth),x2:r.right-px(cs.borderRightWidth),y2:r.bottom-px(cs.borderBottomWidth)};
    st={...st,clip:st.clip?{x1:Math.max(c.x1,st.clip.x1),y1:Math.max(c.y1,st.clip.y1),x2:Math.min(c.x2,st.clip.x2),y2:Math.min(c.y2,st.clip.y2)}:c};
    if(st.clip.x2<=st.clip.x1||st.clip.y2<=st.clip.y1)return;
   }
   pseudo(el,cs,'::before',st);
   for(const n of tag==='DETAILS'&&!el.open?[el.querySelector(':scope > summary')].filter(Boolean):el.childNodes){if(n.nodeType===Node.ELEMENT_NODE)walk(n,st);else if(n.nodeType===Node.TEXT_NODE)text(n,cs,st)}
   pseudo(el,cs,'::after',st);
  }
  walk(root,{clip:null,alpha:1,under:null});range.detach();return ops;
 }
 async function images(ops){
  await Promise.all(ops.filter(o=>o.k==='svg').map(o=>new Promise(resolve=>{const url=URL.createObjectURL(new Blob([o.markup],{type:'image/svg+xml'})),img=new Image();img.onload=()=>{o.img=img;resolve()};img.onerror=()=>resolve();img.src=url;o.url=url})));
 }
 function draw(ctx,ops,dx,dy){
  for(const o of ops){
   ctx.save();ctx.globalAlpha=o.alpha;
   if(o.clip){ctx.beginPath();ctx.rect(o.clip.x1+dx,o.clip.y1+dy,o.clip.x2-o.clip.x1,o.clip.y2-o.clip.y1);ctx.clip()}
   if(o.k==='box'||o.k==='grad'){
    if(o.k==='box')ctx.fillStyle=o.fill;
    else{
     const cx=o.x+dx+o.w/2,cy=o.y+dy+o.h/2,sx=Math.sin(o.g.angle),sy=-Math.cos(o.g.angle),half=(Math.abs(o.w*sx)+Math.abs(o.h*sy))/2;
     const g=ctx.createLinearGradient(cx-sx*half,cy-sy*half,cx+sx*half,cy+sy*half);
     try{o.g.stops.forEach(([c,p])=>g.addColorStop(Math.min(1,Math.max(0,p)),c))}catch{ctx.restore();continue}
     ctx.fillStyle=g;
    }
    ctx.beginPath();if(o.rad>0)ctx.roundRect(o.x+dx,o.y+dy,o.w,o.h,o.rad);else ctx.rect(o.x+dx,o.y+dy,o.w,o.h);ctx.fill();
   }else if(o.k==='ring'){
    ctx.strokeStyle=o.colour;ctx.lineWidth=o.lw;ctx.beginPath();if(o.rad>0)ctx.roundRect(o.x+dx,o.y+dy,o.w,o.h,o.rad);else ctx.rect(o.x+dx,o.y+dy,o.w,o.h);ctx.stroke();
   }else if(o.k==='text'){
    ctx.font=o.font;ctx.letterSpacing=o.ls==='normal'?'0px':o.ls;ctx.fillStyle=o.colour;
    const m=ctx.measureText(o.text),asc=m.fontBoundingBoxAscent,desc=m.fontBoundingBoxDescent,base=o.top+dy+(o.h-asc-desc)/2+asc,room=o.x1===null?Infinity:o.x1-o.x0;
    let x=o.x0+dx,w=m.width;
    if(w>room+1&&o.fit!==false)w=room+1;
    else if(Math.abs(w-room)>1&&room!==Infinity){if(o.align==='right')x=o.x1+dx-w;else if(o.align==='center')x=o.x0+dx+(room-w)/2}
    ctx.textAlign='left';ctx.textBaseline='alphabetic';
    if(w<m.width)ctx.fillText(o.text,x,base,w);else ctx.fillText(o.text,x,base);
    if(o.under){ctx.fillStyle=o.under;ctx.fillRect(x,base+Math.max(1,desc*.35),w,Math.max(1,Math.round(asc/14)))}
   }else if(o.k==='svg'||o.k==='img'){const img=o.k==='svg'?o.img:o.el;if(img)ctx.drawImage(img,o.x+dx,o.y+dy,o.w,o.h)}
   ctx.restore();
  }
 }
 function wrapLines(ctx,text,width){const out=[];let line='';for(const word of text.split(/\s+/).filter(Boolean)){const next=line?line+' '+word:word;if(line&&ctx.measureText(next).width>width){out.push(line);line=word}else line=next}if(line)out.push(line);return out}
 // one image (or several, split at LIMIT pixels): a heading, the region read from the page, notes, then the small-type lines
 async function compose({ops,region,bg,head=[],notes=[],foot=[],pad=PAD,scale=2,minWidth=560}){
  const root=getComputedStyle(document.documentElement),colour={text:root.getPropertyValue('--ink').trim(),text2:root.getPropertyValue('--dim').trim(),edge:root.getPropertyValue('--line').trim()};
  const sans=getComputedStyle(document.body).fontFamily,width=Math.ceil(Math.max(region.w+2*pad,minWidth)),measure=document.createElement('canvas').getContext('2d');
  const block=(lines,font,size,step,c)=>{measure.font=font+' '+size+'px '+sans;const rows=lines.flatMap(l=>wrapLines(measure,l,width-2*PAD));return {rows,font:font+' '+size+'px '+sans,step,colour:c,height:rows.length*step}};
  const blocks={head:block(head,'700',15,21,colour.text),notes:block(notes,'400',12.5,18,colour.text2),foot:block(foot,'400',11.5,16,colour.text2)};
  const headH=blocks.head.rows.length?PAD+blocks.head.height+6:pad,notesH=blocks.notes.rows.length?10+blocks.notes.height:0,footH=blocks.foot.rows.length?14+blocks.foot.height+PAD:pad;
  const height=Math.ceil(headH+region.h+notesH+footH);
  scale=Math.min(scale,32000/width);
  await images(ops);
  const slice=Math.floor(Math.min(LIMIT,2e8/(width*scale))/scale),parts=Math.max(1,Math.ceil(height/slice)),canvases=[];
  for(let p=0;p<parts;p++){
   const top=p*slice,h=Math.min(slice,height-top),canvas=document.createElement('canvas');
   canvas.width=Math.round(width*scale);canvas.height=Math.round(h*scale);
   const ctx=canvas.getContext('2d');ctx.scale(scale,scale);ctx.translate(0,-top);ctx.fillStyle=bg;ctx.fillRect(0,top,width,h);
   const text=(b,y)=>{ctx.font=b.font;ctx.fillStyle=b.colour;ctx.textBaseline='alphabetic';b.rows.forEach((row,i)=>ctx.fillText(row,PAD,y+(i+1)*b.step-b.step*.3))};
   if(blocks.head.rows.length)text(blocks.head,PAD-2);
   draw(ctx,ops,pad-region.x,headH-region.y);
   let y=headH+region.h;
   if(blocks.notes.rows.length){text(blocks.notes,y+6);y+=notesH}
   if(blocks.foot.rows.length){ctx.fillStyle=colour.edge;ctx.fillRect(PAD,y+7,width-2*PAD,1);text(blocks.foot,y+12)}
   canvases.push(canvas);
  }
  ops.forEach(o=>o.url&&URL.revokeObjectURL(o.url));
  return canvases;
 }
 async function save(canvases,name){
  for(let i=0;i<canvases.length;i++){
   const blob=await new Promise(resolve=>canvases[i].toBlob(resolve,'image/png')),a=document.createElement('a');
   a.href=URL.createObjectURL(blob);a.download=canvases.length>1?name+'-part-'+(i+1)+'-of-'+canvases.length+'.png':name+'.png';
   document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
   if(i+1<canvases.length)await new Promise(resolve=>setTimeout(resolve,400));
  }
 }
 const slug=t=>String(t).toLowerCase().normalize('NFKD').replace(/[^\w.]+/g,'-').replace(/^-+|-+$/g,'').slice(0,60);
 const clean=t=>String(t).replace(/\s+/g,' ').trim();
 const theme=()=>L(document.documentElement.dataset.theme==='light'?'Light background':'Dark background');
 const site=()=>L('Model Atlas · Backgammon'),title=()=>L('What did each model see, and what did it play?');
 const version=()=>decVersionText().replace(/\.$/,'');
 function backgroundOf(el){for(let x=el;x;x=x.parentElement){const c=getComputedStyle(x).backgroundColor;if(!clear(c))return c}return getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()||'#fff'}
 // the dataset, setup, filters and page in view (the old page's pngView)
 function filters(){
  const v=decLast;if(!v)return [];
  const call=Object.keys(decCallCode).find(k=>decCallCode[k]===v.c);
  return [L('Setup: {0}',v.setup?v.setup.name:''),v.r!=='all'&&L('Position class: {0}',L(decKind[v.r])),call&&L('Risk call: {0}',L(decCall[call])),v.b!=='all'&&L('Stake, or equity lost by a needless risk: {0}',L(decBand[v.b])),v.k!=='all'&&L('Close choice: {0}',L({close:'close choices',other:'not close choices (full distribution)'}[v.k])),v.pages&&L('page {0} of {1}',decCount(v.p),decCount(v.pages))].filter(Boolean);
 }
 const filterLine=()=>{const f=filters();return L('Filters: {0}',f.length?f.join(' · '):L('none'))};
 // one decision's plays table; the file is named as on the old page: backgammon-decisions-decision-<id>-<league>-game-<n>-turn-<n>-legal-plays
 async function table(card){
  const t=card.querySelector('table.decPlays'),d=decShown.get(card.id.slice(1)),v=decLast;
  t.classList.add('decPngCapture');let ops,region;
  try{
   const rects=[t.getBoundingClientRect(),t.caption?.getBoundingClientRect()].filter(r=>r&&r.width),x1=Math.min(...rects.map(r=>r.left)),y1=Math.min(...rects.map(r=>r.top));
   region={x:x1,y:y1,w:Math.max(...rects.map(r=>r.right))-x1,h:Math.max(...rects.map(r=>r.bottom))-y1};ops=read(t);
  }finally{t.classList.remove('decPngCapture')}
  const th=t.querySelector('thead th[aria-sort="ascending"],thead th[aria-sort="descending"]');
  const sort=th?L('sorted by "{0}", {1}',clean(th.textContent),L(th.getAttribute('aria-sort'))):L("rows in the page's order");
  const head=[site(),[title(),clean(card.querySelector('.decCardHead h3').textContent)+' · '+clean(card.querySelector('.decCardHead .sub').textContent),L('Legal plays')].join(' · ')];
  const foot=[L(v.dataset.label)+' · '+L('{0} rows shown',decCount(t.tBodies[0].rows.length)),filterLine()+' · '+sort,[version(),theme()].filter(Boolean).join(' · '),location.origin+location.pathname+location.search+'#'+card.id];
  const canvases=await compose({ops,region,bg:backgroundOf(t.closest('.decPlaysWrap')),head,notes:[clean(card.querySelector('.decNote').innerText)],foot});
  await save(canvases,'backgammon-decisions-'+slug('Decision '+d.id+' · '+v.dataset.label+' · '+(d.league===null?'position '+d.id:'game '+d.game)+' · turn '+d.turn_no+' Legal plays'));
 }
 // the whole page as shown, its scrolling boxes opened to their full height
 async function page(){
  const doc=document.documentElement,sx=scrollX,sy=scrollY,wraps=[...document.querySelectorAll('.decPlaysWrap')].map(w=>[w,w.scrollLeft]);
  doc.classList.add('decPngPage');let ops,region;
  try{wraps.forEach(([w])=>{w.scrollLeft=0});const top=doc.getBoundingClientRect();region={x:top.left,y:top.top,w:doc.clientWidth,h:doc.scrollHeight};ops=read(document.body)}
  finally{doc.classList.remove('decPngPage');wraps.forEach(([w,left])=>{w.scrollLeft=left});scrollTo(sx,sy)}
  const foot=[L('{0} · the page as shown at {1} px wide · {2}',title(),doc.clientWidth,theme()),filterLine(),version(),location.href].filter(Boolean);
  const canvases=await compose({ops,region,bg:backgroundOf(document.body),head:[site()],foot,pad:0,minWidth:0,scale:doc.clientWidth<=800?2:1.5});
  await save(canvases,'backgammon-page-decisions-'+(doc.dataset.theme==='light'?'light':'dark')+'-'+doc.clientWidth+'px');
 }
 async function run(button,job){
  if(button.getAttribute('aria-busy')==='true')return;
  button.setAttribute('aria-busy','true');
  try{await job()}catch(error){console.warn('PNG export failed:',error)}finally{button.removeAttribute('aria-busy')}
 }
 return {table,page,run};
})();
// the old page's footer line, from Backgammon's own manifest (backgammon/data/manifest.json: results hash, data time);
// the engine and its depth are the old build's own words (jevgammon tools/site/pages.py version_line)
function decVersionText(){
 const m=decGet('data/manifest.json'),t=/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})Z$/.exec(m?.data_as_of||'');
 if(!t||!m.results)return '';
 const day=new Intl.DateTimeFormat(s.ui==='tr'?'tr-TR':'en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(t[1]+'T12:00:00Z'));
 return L('Results {0}, updated {1}; scored by GNU Backgammon 1.08, 2-ply.',m.results,day+', '+t[2]+':'+t[3]+' UTC');
}
function render(){
 if(dates.length&&!data.has(s.snapshot)){loadSnapshot(s.snapshot).then(()=>render());return} // chosen before it arrived
 renderNav();
 if(!panelNames().includes(s.panel))s.panel='Results';
 const f=filtered();
 $('#publicationTabs').innerHTML=s.view==='results'?publicationTabs():'';
 if(!isDecisionPanel())decReturn=null;
 else if(s.view==='results'){$('#workspace').innerHTML=decisionsView();applyLanguage();decAfter();return}
 $('#workspace').innerHTML=s.view==='results'?'<div class="workgrid'+(isRecordPanel()?' single':'')+'">'+(isRecordPanel()?'':'<aside class="sidebar guideSide"><h2>Source</h2>'+renderField('Source snapshot','snapshot',dates,null)+'<button class="outline" data-act="share">'+ic('link')+' Copy link</button></aside>')+'<div class="mainCol">'+(isRecordPanel()?cohortTabs(f)+resultNote(f)+resultSurface(f)+readerSources():reader())+'</div></div>':s.view==='compare'?compareView():draftView();
 applyLanguage();
 if(s.view==='results'&&!isRecordPanel())showAnchor();
}
function sourceDialog(){
 const list=dates.map(v=>'<li><span>'+dateLabel(v)+'</span><span>'+ext('data/'+v+'.json','Atlas JSON')+' · '+ext('https://github.com/zekiworks/analysis/tree/'+commits.get(v),'Source revision')+'</span></li>').join('');
 $('.dialogBody').innerHTML='<div class="drawerHead"><div><span class="eyelabel">Hilde Research</span><h2>Sources</h2></div><button class="square" data-act="close" aria-label="Close">'+ic('close')+'</button></div><p class="sourceNote">Each observation links to an immutable source file and the published benchmark. Dates identify source snapshots.</p><ul class="sourceList">'+sections.map((v,i)=>'<li><strong>'+safe(v)+'</strong>'+ext(originSite+pages[i],'Benchmark page')+'</li>').join('')+'</ul><h3>Source snapshots</h3><p class="sourceNote"><a href="data/index.json" target="_blank">Public JSON index for agents</a></p><ul class="sourceList">'+list+'</ul><p class="sourceNote">Snapshot coverage varies by date. Select a snapshot to see its published records.</p>';
 HildeI18n.localize($('.dialogBody'),s.ui);
 $('#modal').showModal()
}
function openView(view){closeModal();s.detail='';s.view=view;render();persist(true)}
function togglePick(id){if(!records.has(id))return;s.ids=s.ids.includes(id)?s.ids.filter(v=>v!==id):[...s.ids,id]}
async function copy(t){
 try{await navigator.clipboard.writeText(t);toast('Copied.')}catch{
 const el=document.createElement('textarea');el.value=t;($('#modal').open?$('.dialogBody'):document.body).append(el);el.select();let ok=false;try{ok=document.execCommand('copy')}catch{}if(ok){el.remove();toast('Copied.')}else{el.setAttribute('aria-label','Text to copy');toast('Text selected. Use your device’s copy command.')}
 }
}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 const d=b.dataset;
 if(decClick(b))return;
 if(d.view||d.goto)return openView(d.view||d.goto);
 if(d.panel){s.panel=d.panel;s.pa=d.anchor||'';s.track='';s.page=1;openView('results');return}
 if(d.newest){const sel=$('select[data-filter="snapshot"]');if(sel){sel.value=dates[0];sel.dispatchEvent(new Event('change',{bubbles:true}))}return}
 if(has(d.section)){s.panel='Results';s.pa='';s.section=sections[+d.section];s.track=initialTracks[+d.section];s.models='all';s.size='all';s.page=1;openView('results');return} // a type or class chosen on another bench need not exist here
 if(d.ui){
  if(d.ui===s.ui)return;
  s.ui=d.ui==='tr'?'tr':'en';
  try{localStorage.setItem('hilde.language',s.ui)}catch{}
  render();persist(true);return
 }
 if(d.theme){chooseTheme(d.theme);return}
 if(d.cohort){s[d.cohort]=d.value;s.page=1;render();persist(true);return}
 if(d.track){s.track=d.track;s.page=1;render();persist(true);return}
 if(d.bgTrack){s.panel='Results';s.track=d.bgTrack;s.page=1;openView('results');return}
 if(d.act==='share'){persist();copy(location.href);return}
 if(d.act==='reset'){const keep={ui:s.ui,ids:s.ids,section:s.section,view:s.view,panel:s.panel};Object.assign(s,blank(),keep);s.track=initialTracks[sections.indexOf(s.section)];render();persist(true);return}
 if(d.act==='close'){closeModal();return}
 if(b.id==='sourcesBtn'){sourceDialog();return}
 if(d.detail){const r=records.get(d.detail);if(r)showDetail(r);return}
 if(d.toggleDetail){togglePick(d.toggleDetail);render();showDetail(records.get(d.toggleDetail),false);return}
 if(d.history){s.ids=uniq([...s.ids,d.origin,d.history]);openView('compare');return}
 if(d.remove){togglePick(d.remove);render();persist();return}
 if(d.sort!==undefined&&b.classList.contains('sortHead')){s.sort=d.sort;s.page=1;render();persist(true);return}
 if(d.layout){s.layout=d.layout;render();persist(true);return}
 if(d.page){s.page+=Number(d.page);render();persist(true);return}
 if(d.copy)copy(document.getElementById(d.copy).value)
});
document.addEventListener('change',e=>{
 const el=e.target;
 if(el.dataset.dec){decSet(el.dataset.dec,el.value);return}
 if(el.dataset.filter){s[el.dataset.filter]=el.value;s.page=1;render();persist(true)}
 if(el.dataset.pick){togglePick(el.dataset.pick);render();persist()}
});
document.addEventListener('input',e=>{
 const el=e.target;
 if(el.dataset.edit){edited.set(el.dataset.edit,el.value);const length=document.getElementById('len'+el.id);if(length)length.textContent=xLength(el.value)+' / 280'}
});
$('#modal').addEventListener('close',()=>{if(s.detail){s.detail='';persist()}});
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const q=e.target.getBoundingClientRect();if(e.clientX<q.left||e.clientX>q.right||e.clientY<q.top||e.clientY>q.bottom)closeModal()}});
window.addEventListener('popstate',()=>{const next=fromURL();if($('#modal').open)$('#modal').close();s=next;render();if(records.has(s.detail))showDetail(records.get(s.detail))});
function applyLanguage(){
 document.documentElement.lang=s.ui;
 document.title=s.ui==='tr'?'Model Atlası':'Model Atlas';  // Ümit #12533-#12538: the site is Model Atlas
 document.querySelectorAll('[data-ui]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.ui===s.ui));
 HildeI18n.localize(document.body,s.ui);
}
function chooseTheme(theme){
 document.documentElement.dataset.theme=theme;
 try{localStorage.setItem('hilde.atlas.theme',theme)}catch{}
 document.querySelectorAll('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.theme===theme));
}
const loading=new Map();
function loadSnapshot(day){
 if(!loading.has(day))loading.set(day,(async()=>{const res=await fetch('data/'+day+'.json');if(!res.ok)throw Error(day);const json=await res.json();const views=await fetch('data/views/'+day+'.json');if(views.ok)guides.set(day,await views.json());sourceViews.set(day,json.sourceViews||{});commits.set(day,json.commit);json.rows.forEach(r=>records.set(r.id,r));data.set(day,json.rows)})());
 return loading.get(day);
}
async function init(){
 chooseTheme(document.documentElement.dataset.theme||'light');
 document.querySelectorAll('i[data-icon]').forEach(i=>i.outerHTML=ic(i.dataset.icon));
 applyLanguage();
 try{
 const index=await (await fetch('data/index.json',{cache:'no-cache'})).json();
 dates.push(index.defaultSnapshot,...index.snapshots.map(x=>x.version).filter(v=>v!==index.defaultSnapshot));
 s=fromURL(); // again, now that the snapshot list is known (a link's snapshot and picks are checked against it)
 // The shown snapshot (and those a shared link's picks name) first, the rest after the first render: each is ~4 MB.
 const wanted=uniq([s.snapshot,...[...s.ids,s.detail].filter(Boolean).map(id=>id.split(':')[0])].filter(v=>dates.includes(v)));
 await Promise.all(wanted.map(loadSnapshot));
 s.ids=s.ids.filter(id=>records.has(id));if(!records.has(s.detail))s.detail='';render();persist();if(s.detail)showDetail(records.get(s.detail));
 // The others load only when wanted: a snapshot chosen in the list (render) or a record's history (showDetail). With
 // a snapshot after each publication, loading them all up front fetched over 100 MB on every visit.
 }catch{$('#workspace').innerHTML='<div class="panel empty"><strong>Source snapshots could not be loaded.</strong><p>Check your connection and try again.</p><button class="outline" id="retry">Reload</button></div>';HildeI18n.localize($('#workspace'),s.ui);$('#retry').onclick=()=>location.reload()}
}
init();
// the size-class strip loses its edge fade once scrolled to its end (codex #16245)
document.addEventListener('scroll',e=>{const t=e.target;if(t instanceof Element&&t.matches('.cohorts .cohortTabs,.panelTools .trackTabs.inline,.sectionTabs'))t.classList.toggle('atEnd',t.scrollLeft+t.clientWidth>=t.scrollWidth-2)},true);
