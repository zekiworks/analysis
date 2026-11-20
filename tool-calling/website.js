
(() => {
  'use strict';
  const buttons=[...document.querySelectorAll('[data-theme-choice]')];
  const setTheme=theme=>{document.documentElement.dataset.theme=theme;for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.themeChoice===theme));};
  for(const button of buttons)button.addEventListener('click',()=>{const theme=button.dataset.themeChoice;setTheme(theme);try{localStorage.setItem('toolbench-theme',theme);}catch(_){}});
  try{const theme=localStorage.getItem('toolbench-theme');if(theme==='dark'||theme==='light')setTheme(theme);}catch(_){}
  // Views (Ümit #12054/#12107, zeki #12069/#12087): 'Our Toolbench' (its results and blocked runs), 'Tool choice' (its
  // table) or 'Tasks' (the task description), one at a time, each with only its own table. #tool-choice and #tasks select
  // their view; #method and the Methodology heading it holds (#our-toolbench-vs-tool-choice) keep the view they were
  // reached from and open Methodology; any other hash selects Our Toolbench. Each history entry remembers its view
  // (history.state.tbView), so Back and Forward restore it; a fresh page opened at a Methodology hash shows Our Toolbench.
  // The shown view's header tab carries aria-current. Without JavaScript every view stays on the page.
  const views={ours:[...document.querySelectorAll('#ours-what, .tb-notice, #tb-results, #blocked, #confidence')],
               choice:[document.getElementById('tool-choice')].filter(Boolean),
               tasks:[document.getElementById('tasks')].filter(Boolean)};
  const tabs=[...document.querySelectorAll('header a')];
  const tabFor={ours:tabs.find(a=>(a.getAttribute('href')||'').startsWith('./')),
                choice:tabs.find(a=>a.getAttribute('href')==='#tool-choice'),tasks:tabs.find(a=>a.getAttribute('href')==='#tasks')};
  const method=document.getElementById('method');
  const methodHashes=['#method','#our-toolbench-vs-tool-choice'];
  const hashView={'#tool-choice':'choice','#tool-choice-consistency':'choice','#tasks':'tasks'};
  let current='ours';
  const remembered=()=>history.state&&views[history.state.tbView]?history.state.tbView:null;
  const render=()=>{
    if(!views.choice.length)return;
    for(const [name,els] of Object.entries(views))for(const el of els)el.hidden=name!==current;
    for(const [name,a] of Object.entries(tabFor)){if(!a)continue;if(name===current)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');}
  };
  const remember=()=>history.replaceState({...(history.state||{}),tbView:current},'',location.href);
  const route=fromHistory=>{
    const saved=remembered();
    if(fromHistory&&saved)current=saved;
    else if(hashView[location.hash])current=hashView[location.hash];
    else if(!methodHashes.includes(location.hash))current='ours';
    render();remember();
    if(methodHashes.includes(location.hash)&&method){method.open=true;
      if(fromHistory||location.hash!=='#method')(document.getElementById(location.hash.slice(1))||method).scrollIntoView();}
  };
  if(tabFor.ours&&views.choice.length)tabFor.ours.addEventListener('click',e=>{if(current!=='ours'){e.preventDefault();current='ours';
    history.pushState({tbView:'ours'},'',tabFor.ours.getAttribute('href'));render();window.scrollTo(0,0);}});
  for(const link of document.querySelectorAll('a[href="#method"], a[href="#our-toolbench-vs-tool-choice"]'))link.addEventListener('click',()=>{if(method)method.open=true;});
  window.addEventListener('hashchange',()=>route(false));window.addEventListener('popstate',()=>route(true));
  const saved=remembered();current=saved||hashView[location.hash]||'ours';route(false);
})();
