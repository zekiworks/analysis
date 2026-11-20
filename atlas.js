'use strict';
const dates=[]; // data/index.json's snapshots, its default first (init)
// All benches last, after the five benches (Ümit #11580).
const sections=['Reading & Grammar','Logic & Math','Backgammon','Answer Check','Toolbench','All benches'];
const pages=['decision-models/','logic/','backgammon/','grading/','tool-calling/','all-benches/'];
const initialTracks=['Turkish Reading & Grammar','Logic','Risk judgement ranking','Grading','Candidate setups','Combined'];
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
function blank(){return {ui:'en',section:sections[0],panel:'Results',track:initialTracks[0],model:'',models:'all',size:'all',language:'',mode:'',status:'',snapshot:dates[0],view:'results',layout:'table',sort:'',page:1,ids:[],detail:''}}
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
 st.page=Math.max(1,parseInt(st.page,10)||1);return st
}
let s=fromURL();
function serialize(){
 // The snapshot only when it is not the newest: an address the page wrote for the newest must not pin it once a newer
 // one is out (Ümit #11706 reopened a 14:04 address at 17:22 and saw old rows); a chosen older one stays in the link.
 const p=new URLSearchParams({v:'2',ui:s.ui});
 if(s.snapshot&&s.snapshot!==dates[0])p.set('snapshot',s.snapshot);
 for(const key of Object.keys(blank()))if(key!=='ids'&&s[key]!==''&&s[key]!==blank()[key])p.set(key,s[key]);
 for(const id of s.ids)p.append('pick',id);
 return p.toString();
}
function persist(push=false){
 const q=serialize();
 if(location.search!=='?'+q)history[push?'pushState':'replaceState'](null,'',location.pathname+'?'+q);
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
function cohortTabs(f){
 function line(field,label,titles,values){
  return '<div class="cohortLine"><span class="fieldTitle">'+label+'</span><div class="cohortTabs" role="group" aria-label="'+label+'">'+values.map(v=>'<button data-cohort="'+field+'" data-value="'+v+'" aria-pressed="'+(s[field]===v)+'" class="'+(s[field]===v?'on':'')+'">'+safe(titles[v]||v)+'</button>').join('')+'</div></div>';
 }
 const types=Object.keys(typeTitles).filter(v=>v==='all'||v===s.models||f.base.some(r=>(r.modelType||'unclassified')===v));
 const available=f.base.filter(r=>s.models==='all'||(r.modelType||'unclassified')===s.models);
 const sizes=Object.keys(sizeTitles).filter(v=>v==='all'||v===s.size||['tiny','small','medium','large','efficient','workhorse','flagship','undisclosed'].includes(v)||available.some(r=>(r.modelClass||'unclassified')===v));
 return '<div class="cohorts">'+line('models','Model type',typeTitles,types)+line('size','Model class',sizeTitles,sizes)+'</div>';
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
function reader(){
 const resource=pageMap()[s.panel], url=resource?.url||sourceViews.get(s.snapshot)?.[s.section]?.[s.panel];
 if(!url)return '';
 const links=ext(url,'Open published page')+(resource?.file?ext(repo+commits.get(s.snapshot)+'/'+resource.file,'Pinned source'):'');
 const groups=(resource?.groups||[]).filter(g=>g.title||g.text.length||g.links.length);
 const internal=new Map(Object.entries(pageMap()).map(([k,v])=>[v.url,k]));
 const body=groups.map((g,i)=>{
  const items=g.links.map(([text,url])=>internal.has(url)?'<button class="textLink" data-panel="'+safe(internal.get(url))+'">'+safe(text)+'</button>':ext(url,text)).join('');
  const contents=g.text.map(t=>'<p>'+safe(t)+'</p>').join('')+(items?'<div class="guideLinks">'+items+'</div>':'');
  return g.title?'<details class="guideItem" '+(i===0?'open':'')+'><summary>'+safe(g.title)+'</summary>'+contents+'</details>':contents;
 }).join('');
 return '<article class="panel guide"><div class="eyelabel">'+safe(s.section)+' · '+safe(dateLabel(s.snapshot))+'</div><h2>'+safe(resource?.title||s.panel)+'</h2><div class="guideLinks">'+links+'</div>'+(s.ui==='tr'?'<p class="sourceNote">Yayımlanmış kaynaktan alıntılar İngilizcedir.</p>':'')+'<div data-verbatim lang="en">'+body+'</div></article>';
}
// Toolbench's first results were labelled a pilot; the bench is no longer called one, in any snapshot (Ümit #11253).
function trackLabel(t){return {'Pilot results':'Our bench','Results':'Our bench','Tool choice (decision models)':'Tool choice','Risk judgement ranking':'Risk judgement'}[t]||t}
function resultNote(f){
 // Toolbench: one small link to what each tab measures, on Toolbench's page, its Methodology (#method); no explanation on the tabs (Ümit #12107, #12121).
 const what=s.section==='Toolbench'&&['Results','Tool choice (decision models)'].includes(f?.chosen)?'<p class="whatLink"><a href="/analysis/tool-calling/#method">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('What this measures →'))+'</a></p>':'';
 // An older snapshot than the newest: say so, with the way to the newest (Ümit #11253 looked at an old one).
 const old=dates.length&&s.snapshot!==dates[0]?'<div class="notice neutral">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('You are looking at an older snapshot:'))+' '+safe(dateLabel(s.snapshot))+'. <button class="textLink" data-newest="1">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('Show the newest'))+'</button> ('+safe(dateLabel(dates[0]))+')</div>':'';
 // A track the snapshot did not re-read keeps its rows from an earlier snapshot: say from when (Zeki #9682)
 const from=uniq((f?.rows||[]).map(r=>r.carriedFrom).filter(Boolean));
 return what+old+(from.length?'<div class="notice neutral">'+safe((m=>s.ui==='tr'?HildeI18n.translate(m):m)('Copied unchanged from an earlier snapshot; its source files were not read again for this one:'))+' '+safe(from.map(dateLabel).join(', '))+'</div>':'')+resultNoteText();
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
function metric(r){
 if(r.verdict&&has(r.learningMetrics?.['Risks found change (pp)']))return ['Risks found change',r.learningMetrics['Risks found change (pp)'],' pp'];
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
function recButton(r){return '<button class="rowName" data-detail="'+r.id+'">'+branded(r,safe(r.name))+'</button><span class="sub">'+safe([r.setup||r.tag||r.ref||r.track, r.seeds?r.seeds.length+' run average':null].filter(Boolean).join(' · '))+'</span>'}
function headingActions(){return '<div class="actions"><button class="outline" data-act="share">'+ic('link')+' Copy link</button>'+(s.ids.length?'<button class="primary" data-goto="compare">'+ic('compare')+' Selected ('+s.ids.length+')</button>':'')+'</div>'}
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
 const popular={'Reading & Grammar':['Turkish Reading & Grammar','Turkish Reading','Turkish Grammar','English Reading'], 'Logic & Math':['Logic','Math','Logic and Math'],Backgammon:['Risk judgement ranking','League 1','League 2','League 3'], 'All benches':['Combined','Decision Index','Turkish Reading','Turkish Grammar','English Reading','Logic','Math','Backgammon','Answer Check'], Toolbench:['Results','Tool choice (decision models)']};
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
 const trackTabs=main.length+extra.length>1?'<div class="trackTabs" role="group" aria-label="Experiment tabs">'+main.flatMap((t,i)=>bgTabs&&i===0?[tabFor(t),'<button data-panel="Learning" aria-pressed="'+(s.panel==='Learning')+'">'+safe(trackLabel('Learning'))+'</button>']:[tabFor(t)]).join('')+'</div>'+more:'';
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
  content='<p class="smallnote chartHint">'+safe(measure)+' · '+(primary[2]===' PR'?'lower is better':'published scale')+'</p>'+rows.map(r=>{const [label,v,u]=metric(r);const width=v===null||label!==measure?0:Math.min(signed?50:100,Math.abs(v)/scale*(signed?50:100));const pos=signed?(v<0?'right:50%;':'left:50%;'):'';return '<div class="chartRow"><div>'+recButton(r)+'</div><div class="miniBar '+(signed?'signedBar':'')+'"><span style="'+pos+'width:'+width+'%"></span></div><span class="value">'+(v===null?nil:val(v,1)+safe(u))+'</span>'+checkbox(r)+'</div>'}).join('')
 }else{
  const md=s.layout==='metrics';
  const candidates=roster;
  const heads=candidates?['Candidate and setup','Run status','Cost','Latency','Model type','Size verification']:md?['Model and setup','Cost','Latency','ECE','Invalid','Abstained']:['Rank¹','Model and setup',measure,s.panel==='Learning'?'Verdict':measure==='Normalized score'?'Raw accuracy':'Norm. score','Cost','Latency'];
  const sortKey={Cost:'cost',Latency:'latency'};
  const head=h=>{const k=sortKey[h]??(h===measure?'':null);if(k===null||candidates)return '<th scope="col">'+safe(h)+'</th>';
   const on=s.sort===k;return '<th scope="col" aria-sort="'+(on?(k?'ascending':'descending'):'none')+'"><button class="sortHead'+(on?' on':'')+'" data-sort="'+k+'">'+safe(h)+(on?' '+(k?'↑':'↓'):'')+'</button></th>'};
  content='<div class="tableScroll"><table><thead class="tableHead"><tr><th class="checkCol"><span class="sr">Select</span></th>'+heads.map(head).join('')+'<th><span class="sr">Details</span></th></tr></thead><tbody>'+rows.map(r=>{
    const [label,m,u]=metric(r);
    if(candidates)return '<tr><td class="checkCol">'+checkbox(r)+'</td><td>'+recButton(r)+'</td><td>'+statusTag(r)+'</td>'+usageColumns(r)+'<td>'+safe(typeTitles[r.modelType]||'Unclassified')+'</td><td>'+safe(sizeTitles[r.modelClass]||'Unverified')+'</td><td><button class="rowDetails" data-detail="'+r.id+'" aria-label="'+safe(r.name)+' details">'+ic('right')+'</button></td></tr>';
    let main='<td class="checkCol">'+checkbox(r)+'</td>';
    if(!md)main+='<td class="rankCol" title="Published rank or statistical tier">'+(has(r.rank)?safe(r.rank):nil)+'</td>';
    main+='<td>'+recButton(r)+(r.status!=='Published'?'<span class="pill mutedPill">'+safe(r.status)+'</span>':'')+'</td>';
    if(md)main+=usageColumns(r)+'<td>'+numCell(has(r.ece)?r.ece*100:null)+'<span class="sub">'+(has(r.ece)?'points':'')+'</span></td><td>'+numCell(r.invalid)+'</td><td>'+numCell(r.abst)+'</td>';
    else main+='<td><div class="measure"><span class="value">'+(m===null?nil:val(m,r.lowMetric?.digits??1)+(u==='%'?'%':u===' pp'?' pp':''))+'</span>'+(m!==null&&u!==' PR'&&u!==' pp'&&!r.lowMetric?'<div class="miniBar"><span style="width:'+Math.max(0,Math.min(100,m))+'%"></span></div>':'')+'</div>'+(label!==measure&&m!==null?'<span class="sub">'+safe(label)+'</span>':'')+'</td><td>'+(s.panel==='Learning'?(r.verdict?safe(r.verdict):nil):numCell(measure==='Normalized score'?(has(r.acc)?r.acc*100:null):r.norm))+'</td>'+usageColumns(r);
    return '<tr class="'+(s.ids.includes(r.id)?'selectedRow':'')+'">'+main+'<td><button class="rowDetails" data-detail="'+r.id+'" aria-label="'+safe(r.name)+' details">'+ic('right')+'</button></td></tr>'
  }).join('')+'</tbody></table></div>'
 }
 const heading=s.section==='Toolbench'?(roster?'Candidate setups':'Results'):s.panel==='Learning'?'Learning results':s.panel==='Learning pilot'?'Learning pilot results':'Experiment results';
 return '<div class="topline"><h2>'+heading+' <span class="count">'+fmtNum(n,0)+'</span></h2>'+headingActions()+'</div><div class="panel"><div class="panelTools"><div class="toggleGroup">'+radio('table','Table','table')+radio('resources','Cost & latency','clock')+(s.section==='Toolbench'?'':radio('chart','Chart','chart')+radio('metrics','Metrics','filters'))+'</div></div>'+trackTabs+'<div class="contextStrip"><span class="dot"></span>'+labels.map(safe).join('<span class="divider">/</span>')+'</div>'+content+(n?'<div class="pager"><span>'+((s.page-1)*pageSize+1)+'–'+Math.min(s.page*pageSize,n)+' / '+fmtNum(n,0)+' records</span><div class="actions"><button class="square" data-page="-1" aria-label="Previous page" '+(s.page===1?'disabled':'')+'>'+ic('left')+'</button><span>'+s.page+' / '+last+'</span><button class="square" data-page="1" aria-label="Next page" '+(s.page===last?'disabled':'')+'>'+ic('right')+'</button></div></div>':'')+'</div><p class="smallnote">'+(roster?'Select a candidate to inspect its eligibility and source.':'¹ Published rank or statistical tier. A dash means no value is reported. Select a model to inspect its method and units.')+'</p>'
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
 entry('Decision Score',has(r.decisionScore)?fmtNum(r.decisionScore,2):null),entry('Exact match',p(r.exact)),...Object.entries(r.extraMetrics||{}).map(([k,v])=>{const labels={wrong_answer_recall:'Wrong answer recall',false_alarm_rate:'False alarm rate',gpu_seconds_per_1000:'GPU seconds / 1,000 requests',latency_s_p90:'P90 latency (s)',non_hallucination:'Non-hallucination (abstained of answers not right)',seed_min:'Lowest run accuracy',seed_max:'Highest run accuracy',run_cost_usd:'Modeled GPU cost of the whole run (not an invoice)'};return entry(labels[k]||k,typeof v==='string'?v:k==='run_cost_usd'?'$'+fmtNum(v,4)+' USD':k.endsWith('recall')||k.endsWith('rate')||['non_hallucination','seed_min','seed_max'].includes(k)?p(v):fmtNum(v,3))}),...Object.entries(r.learningMetrics||{}).map(([label,v])=>entry(label,typeof v==='number'?fmtNum(v,3):v)),entry('Published improvement verdict',r.verdict),entry('Confidence ≥ 0.99',r.sure?fmtNum(r.sure.answers)+' answers · '+fmtNum(r.sure.wrong)+' incorrect':null)
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
 const body=$('.dialogBody');
 body.innerHTML='<div class="drawerHead"><div><span class="eyelabel">'+safe(r.section)+'</span><h2>'+branded(r,safe(r.name))+'</h2></div><button class="square" data-act="close" aria-label="Close">'+ic('close')+'</button></div><div class="tagLine">'+statusTag(r)+'<span class="pill">'+safe(r.lang)+'</span><span class="pill">'+safe(r.mode)+'</span></div><p class="drawerMeta">'+[r.track,r.setup||r.tag,dateLabel(snap(r))].map(safe).join(' / ')+'</p>'+metricGrid(r,false)+detailsDl(r)+sourceLinks(r)+historyButtons(r)+'<div class="modalFooter"><button class="primary" data-toggle-detail="'+r.id+'">'+ic('compare')+(s.ids.includes(r.id)?'Remove from selection':'Add to comparison')+'</button><button class="outline" data-act="share">'+ic('link')+' Copy record link</button></div>';
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
function render(){
 if(dates.length&&!data.has(s.snapshot)){loadSnapshot(s.snapshot).then(()=>render());return} // chosen before it arrived
 renderNav();
 if(!panelNames().includes(s.panel))s.panel='Results';
 const f=filtered();
 $('#publicationTabs').innerHTML=s.view==='results'?publicationTabs():'';
 $('#workspace').innerHTML=s.view==='results'?'<div class="workgrid'+(isRecordPanel()?' single':'')+'">'+(isRecordPanel()?'':'<aside class="sidebar guideSide"><h2>Source</h2>'+renderField('Source snapshot','snapshot',dates,null)+'<button class="outline" data-act="share">'+ic('link')+' Copy link</button></aside>')+'<div class="mainCol">'+(isRecordPanel()?cohortTabs(f)+resultNote(f)+resultSurface(f)+readerSources():reader())+'</div></div>':s.view==='compare'?compareView():draftView();
 applyLanguage();
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
 if(d.view||d.goto)return openView(d.view||d.goto);
 if(d.panel){s.panel=d.panel;s.track='';s.page=1;openView('results');return}
 if(d.newest){const sel=$('select[data-filter="snapshot"]');if(sel){sel.value=dates[0];sel.dispatchEvent(new Event('change',{bubbles:true}))}return}
 if(has(d.section)){s.panel='Results';s.section=sections[+d.section];s.track=initialTracks[+d.section];s.models='all';s.size='all';s.page=1;openView('results');return} // a type or class chosen on another bench need not exist here
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
