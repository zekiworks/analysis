
(() => {
  'use strict';
  const buttons=[...document.querySelectorAll('[data-theme-choice]')];
  const setTheme=theme=>{document.documentElement.dataset.theme=theme;for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.themeChoice===theme));};
  for(const button of buttons)button.addEventListener('click',()=>{const theme=button.dataset.themeChoice;setTheme(theme);try{localStorage.setItem('toolbench-theme',theme);}catch(_){}});
  try{const theme=localStorage.getItem('toolbench-theme');if(theme==='dark'||theme==='light')setTheme(theme);}catch(_){}
  // Two score views (Ümit #12054, zeki #12069/#12087): 'Our bench' (tasks, results, blocked runs) or 'Tool choice', never
  // both. #tool-choice selects Tool choice; any other hash except #method selects Our bench; #method keeps the view it was
  // reached from, and each history entry remembers its view (history.state.tbView), so Back and Forward restore it. A
  // fresh page opened at #method shows Our bench. The shown view's header tab carries aria-current. Without JavaScript
  // both views stay on the page.
  const choice=document.getElementById('tool-choice');
  const ours=[...document.querySelectorAll('#tasks, .tb-notice, #tb-results, #blocked')];
  const tabs=[...document.querySelectorAll('header a')];
  const oursTab=tabs.find(a=>a.textContent.trim()==='Our bench'), choiceTab=tabs.find(a=>a.getAttribute('href')==='#tool-choice');
  const method=document.getElementById('method');
  let showChoice=false;
  const remembered=()=>history.state&&typeof history.state.tbView==='string'?history.state.tbView==='choice':null;
  const render=()=>{
    if(!choice)return;
    choice.hidden=!showChoice;for(const el of ours)el.hidden=showChoice;
    if(oursTab){if(showChoice)oursTab.removeAttribute('aria-current');else oursTab.setAttribute('aria-current','page');}
    if(choiceTab){if(showChoice)choiceTab.setAttribute('aria-current','page');else choiceTab.removeAttribute('aria-current');}
  };
  const remember=()=>history.replaceState({...(history.state||{}),tbView:showChoice?'choice':'ours'},'',location.href);
  const route=fromHistory=>{
    const saved=remembered();
    if(fromHistory&&saved!==null)showChoice=saved;
    else if(location.hash==='#tool-choice')showChoice=true;
    else if(location.hash!=='#method')showChoice=false;
    render();remember();
    if(location.hash==='#method'&&method){method.open=true;if(fromHistory)method.scrollIntoView();}
  };
  if(oursTab&&choice)oursTab.addEventListener('click',e=>{if(showChoice){e.preventDefault();showChoice=false;
    history.pushState({tbView:'ours'},'',oursTab.getAttribute('href'));render();window.scrollTo(0,0);}});
  for(const link of document.querySelectorAll('a[href="#method"]'))link.addEventListener('click',()=>{if(method)method.open=true;});
  window.addEventListener('hashchange',()=>route(false));window.addEventListener('popstate',()=>route(true));
  const saved=remembered();showChoice=saved!==null?saved:location.hash==='#tool-choice';route(false);
})();
