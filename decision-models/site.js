'use strict';

/* A latency in seconds, the site's one format, as build_page.seconds: three decimals below 1 s (0.223), two from 1 s to
   under 10 s (7.10), one from 10 s (53.7). v3.js and compare.js load after this file and use it; sorting stays on the
   raw values. */
function secondsText(value) {
  return value.toFixed(value < 1 ? 3 : value < 10 ? 2 : 1);
}

/* Every page: the Dark / Light switch, with one memory for the whole site: the choice is kept in localStorage ("theme")
   and applied by a line in each page's <head> before it renders; without JavaScript the page stays dark. */
(function setupTheme() {
  const control = document.querySelector('.theme-switch');
  if (!control) return;
  const buttons = control.querySelectorAll('button');
  const show = () => {
    const light = document.documentElement.dataset.theme === 'light';
    buttons.forEach(button => button.setAttribute('aria-pressed', String((button.dataset.themeChoice === 'light') === light)));
  };
  control.hidden = false;
  show();
  control.addEventListener('click', event => {
    const choice = event.target.closest('button')?.dataset.themeChoice;
    if (!choice) return;
    if (choice === 'light') document.documentElement.dataset.theme = 'light';
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every page: the view bar's group, from ?models= (all, decision or chat; missing or unknown means all). The bar marks
   its row 2 choice, the row 1 links keep the group, and each element whose data-models lists other groups only is
   hidden (and shown again when it lists this one), before the page's own scripts run. <html data-models-view> carries
   the group for them. The bar's height is kept in --view-bar-h, so the page scrolls links and parts below it. */
(function setupViewBar() {
  const asked = new URLSearchParams(window.location.search).get('models');
  const group = ['all', 'decision', 'chat'].includes(asked) ? asked : 'all';
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  const bar = document.querySelector('.view-bar');
  if (!bar) return;
  bar.querySelectorAll('a[data-view-group]').forEach(link => {
    if (link.dataset.viewGroup === group) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  });
  bar.querySelectorAll('a[data-view-test]').forEach(link => {
    link.setAttribute('href', `${link.getAttribute('href').split('?')[0]}?models=${group}`);
  });
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${bar.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(bar);
})();

/* On a phone the navigation bar scrolls sideways; a link that takes the keyboard focus is brought fully into view. */
(function keepFocusedLinkInView() {
  const bar = document.querySelector('.nav ul');
  if (!bar) return;
  bar.addEventListener('focusin', event => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
})();

/* Pages that keep their details under a closed Info (a details element): a link to a part inside it, in the address or
   followed later, opens Info first, so the browser can scroll there. */
(function openInfoForLink() {
  const open = () => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    const target = id && document.getElementById(id);
    const details = target && (target.closest('details') ?? target.querySelector(':scope > details'));
    if (!details || details.open) return;
    details.open = true;
    target.scrollIntoView();
  };
  open();
  window.addEventListener('hashchange', open);
})();
