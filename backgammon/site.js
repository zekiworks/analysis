'use strict';

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

/* On a phone the navigation bar scrolls sideways: the current page's link starts in the middle of the bar, and a link
   that takes the keyboard focus is brought fully into view. */
(function keepNavLinksInView() {
  const bar = document.querySelector('.nav ul');
  if (!bar) return;
  const current = bar.querySelector('[aria-current="page"]');
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

/* Every page: the page bar, sticky at the top of the window: the pages row (Home first) and, on the home page, the view
   bar's filter and Measure rows under it (Zeki, bus #1878: Home stays in view everywhere). Its height is kept in
   --view-bar-h, so links to a part of a page land below it. On the home page the Measure row marks the part in view:
   the part that crosses a line a quarter of the way down the window below the bar, or the key just pressed until the
   reader scrolls on; between parts no key is marked. */
(function setupViewBar() {
  const bar = document.querySelector('.page-bar');
  if (!bar) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${bar.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(bar);
  const links = [...bar.querySelectorAll('a[data-view-measure]')];
  const parts = links.map(link => ({ link, part: document.getElementById(link.dataset.viewMeasure) })).filter(x => x.part);
  if (!parts.length) return;
  const mark = key => links.forEach(link => {
    if (link.dataset.viewMeasure === key) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  });
  let pressed = null;
  let pressedAt = 0;
  const inView = () => {
    const top = bar.offsetHeight;
    const line = top + (innerHeight - top) / 4;
    const found = parts.find(({ part }) => {
      if (!part.offsetParent) return false;
      const box = part.getBoundingClientRect();
      return box.top <= line && box.bottom > line;
    });
    return found ? found.link.dataset.viewMeasure : null;
  };
  const press = key => {
    pressed = key;
    mark(key);
    requestAnimationFrame(() => { pressedAt = scrollY; });
  };
  let queued = false;
  addEventListener('scroll', () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (pressed && Math.abs(scrollY - pressedAt) < 48) return;
      pressed = null;
      mark(inView());
    });
  }, { passive: true });
  bar.addEventListener('click', event => {
    const key = event.target.closest('a[data-view-measure]')?.dataset.viewMeasure;
    if (key) press(key);
  });
  const fromHash = () => {
    const key = decodeURIComponent(location.hash.slice(1));
    if (parts.some(({ link }) => link.dataset.viewMeasure === key)) press(key);
    else mark(inView());
  };
  addEventListener('hashchange', fromHash);
  fromHash();
})();
