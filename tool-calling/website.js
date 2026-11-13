
(() => {
  'use strict';
  const buttons=[...document.querySelectorAll('[data-theme-choice]')];
  const setTheme=theme=>{document.documentElement.dataset.theme=theme;for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.themeChoice===theme));};
  for(const button of buttons)button.addEventListener('click',()=>{const theme=button.dataset.themeChoice;setTheme(theme);try{localStorage.setItem('toolbench-theme',theme);}catch(_){}});
  try{const theme=localStorage.getItem('toolbench-theme');if(theme==='dark'||theme==='light')setTheme(theme);}catch(_){}
})();
