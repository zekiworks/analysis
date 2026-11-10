'use strict';

/* Every page: the Dark / Light switch, with one memory for the whole site: the choice is kept in localStorage ("theme")
   and applied by a line in each page's <head> before it renders, as data-theme="light" or "dark" on <html>; without
   JavaScript the page stays dark. */
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
    // Always named, light or dark: the suite strip (suite-bar.css) follows data-theme, and without it the reader's system.
    document.documentElement.dataset.theme = choice === 'light' ? 'light' : 'dark';
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every page: More options in the top bar opens the page export (the colour theme has its own keys beside it). Escape
   closes it and gives the focus back to its key; a click outside it or the focus leaving it closes it too. The page
   export closes it first, so the PNG shows the page without the open menu (this listener runs before png.js's). */
(function moreOptions() {
  const toggle = document.querySelector('[data-more-toggle]');
  if (!toggle) return;
  const menu = toggle.parentElement;
  const pop = document.getElementById(toggle.getAttribute('aria-controls'));
  const set = open => {
    toggle.setAttribute('aria-expanded', String(open));
    pop.hidden = !open;
  };
  toggle.addEventListener('click', () => set(pop.hidden));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || pop.hidden) return;
    const inside = menu.contains(document.activeElement) || document.activeElement === document.body;
    set(false);
    if (inside) toggle.focus();
  });
  menu.addEventListener('focusout', event => {
    if (!pop.hidden && event.relatedTarget && !menu.contains(event.relatedTarget)) set(false);
  });
  document.addEventListener('click', event => {
    if (!pop.hidden && !menu.contains(event.target)) set(false);
  });
  const pagePng = pop.querySelector('[data-page-png]');
  if (pagePng) pagePng.addEventListener('click', () => { set(false); toggle.focus(); });
})();

/* If the tab row is ever wider than the window (it wraps on a phone), the current tab starts in the middle of the row,
   and a tab that takes the keyboard focus is brought fully into view. */
(function keepNavLinksInView() {
  const bar = document.querySelector('.site-tabs ul');
  if (!bar) return;
  const current = bar.querySelector('[aria-current]');
  if (current && bar.scrollWidth > bar.clientWidth) {
    const a = current.getBoundingClientRect(), b = bar.getBoundingClientRect();
    bar.scrollLeft += a.left - b.left - (b.width - a.width) / 2;
  }
  bar.addEventListener('focusin', event => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
})();

/* Every page: the cost unit, one choice for the whole site, as on the sibling site: costs per 1,000 decisions or per 1M
   decisions. The choice comes from ?cost-unit= (1k or 1m), else localStorage ("costUnit"), and sits in
   <html data-cost-unit>, which a line in each page's <head> sets before it renders; site.css shows the chosen unit. The
   page carries each cost per 1,000 decisions as printed (a stored value); the per-1M text is written here from the
   cost's data-usd (per 1,000 decisions), so the page itself holds no number that is not in a data file: the values, a
   cost chart's axis ticks (data-tick: whole dollars) and the tooltips of its rows (li[data-usd]). Without JavaScript
   costs read per 1,000 decisions. */
(function setupCostUnit() {
  const root = document.documentElement;
  const unit = () => (root.dataset.costUnit === '1m' ? '1m' : '1k');
  const perMillion = (usd, tick) => {
    const v = Number(usd) * 1000;
    return `$${v.toLocaleString('en-US', tick || v >= 100 ? { maximumFractionDigits: v < 1 ? 2 : 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };
  document.querySelectorAll('.cost-1m[data-usd]').forEach(el => {
    el.textContent = `${el.dataset.prefix || ''}${perMillion(el.dataset.usd, el.hasAttribute('data-tick'))}`;
  });
  // A cost row's tooltip names its cost in the chosen unit.
  const tips = () => document.querySelectorAll('li.hbar[data-usd]').forEach(li => {
    if (!li.dataset.tip1k) li.dataset.tip1k = li.title;
    li.title = unit() === '1m'
      ? li.dataset.tip1k.replace(/\$[\d.,]+ per 1,000 decisions/, `${perMillion(li.dataset.usd, false)} per 1M decisions`)
      : li.dataset.tip1k;
  });
  tips();
  const press = () => document.querySelectorAll('[data-cost-unit-choice]').forEach(key => {
    key.setAttribute('aria-pressed', String(key.dataset.costUnitChoice === unit()));
  });
  const keep = choice => {
    try {
      localStorage.setItem('costUnit', choice);
    } catch (error) {
      /* Storage may be unavailable; the address still carries the choice. */
    }
  };
  const asked = new URLSearchParams(location.search).get('cost-unit');
  if (asked === '1k' || asked === '1m') {
    if (asked === '1m') root.dataset.costUnit = '1m'; else delete root.dataset.costUnit;
    keep(asked);
  }
  press();
  document.addEventListener('click', event => {
    const key = event.target.closest('[data-cost-unit-choice]');
    if (!key || key.dataset.costUnitChoice === unit()) return;
    const choice = key.dataset.costUnitChoice;
    if (choice === '1m') root.dataset.costUnit = '1m'; else delete root.dataset.costUnit;
    keep(choice);
    const url = new URL(location.href);
    url.searchParams.set('cost-unit', choice);
    history.replaceState(history.state, '', url);
    press();
    tips();
  });
})();

/* Every page: the sticky header (the suite strip and the site's bar with its tabs, Ümit #2901). Its height is kept in
   --view-bar-h, so links to a part of a page land below it. */
(function setupViewBar() {
  const bar = document.querySelector('.site-header');
  if (!bar) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${bar.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(bar);
})();

/* Did they improve?: the results table's filter (Ümit/Zeki #3710), the leaderboard's (bg.js headlineFilter): a type
   row (All, Chat models, Decision models; rows' data-group) and a Size row (Ümit #4156; rows' data-size), combined; a
   second click on a pressed key returns its row to All (Ümit #3923); a selected size shows its rule under the keys;
   ?models=chat|decision and ?size=<class> open on them, the old ?models=small-chat / small-decision (small: Small
   chat) on that type with Tiny and Small. */
(function improveFilter() {
  const table = document.getElementById('improve-results-table');
  const keys = [...document.querySelectorAll('[data-improve-filter]')];
  const sizeKeys = [...document.querySelectorAll('.improve-size [data-size-key]')];
  const notes = [...document.querySelectorAll('[data-size-note]')];
  if (!table || !keys.length) return;
  let type = 'all', sizes = new Set();
  const apply = () => {
    keys.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.improveFilter === type)));
    sizeKeys.forEach(x => x.setAttribute('aria-pressed', String(sizes.size ? sizes.has(x.dataset.sizeKey) : x.dataset.sizeKey === 'all')));
    table.querySelectorAll('tbody tr[data-group]').forEach(tr => {
      tr.hidden = (type !== 'all' && tr.dataset.group !== type) || (sizes.size > 0 && !sizes.has(tr.dataset.size));
    });
    notes.forEach(n => { n.hidden = !sizes.has(n.dataset.sizeNote); });
  };
  keys.forEach(k => k.addEventListener('click', () => {
    const t = k.dataset.improveFilter;
    type = t !== 'all' && t === type ? 'all' : t;
    apply();
  }));
  sizeKeys.forEach(k => k.addEventListener('click', () => {
    const s = k.dataset.sizeKey;
    sizes = s === 'all' || k.getAttribute('aria-pressed') === 'true' ? new Set() : new Set([s]);
    apply();
  }));
  const q = new URLSearchParams(location.search);
  const asked = q.get('models') === 'small' ? 'small-chat' : q.get('models');
  const small = asked && asked.startsWith('small-');
  const t = small ? asked.slice(6) : asked;
  if (keys.some(k => k.dataset.improveFilter === t)) type = t;
  if (small) sizes = new Set(['tiny', 'small']);
  if (sizeKeys.some(k => k.dataset.sizeKey === q.get('size') && q.get('size') !== 'all')) sizes = new Set([q.get('size')]);
  if (type !== 'all' || sizes.size) apply();
})();
