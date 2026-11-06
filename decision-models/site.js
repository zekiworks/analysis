'use strict';

/* A latency in seconds, the site's one format, as build_page.seconds: three decimals below 1 s (0.223), two from 1 s to
   under 10 s (7.10), one from 10 s (53.7). v3.js and compare.js load after this file and use it; sorting stays on the
   raw values. */
function secondsText(value) {
  return value.toFixed(value < 1 ? 3 : value < 10 ? 2 : 1);
}

/* Every page: the cost unit, one choice for the whole site: costs per 1,000 questions or per 1M questions. The choice
   comes from ?cost-unit= (1k or 1m), else localStorage ("costUnit"), and sits in <html data-cost-unit>, which a line in
   each page's <head> sets before it renders. A page's own values carry both units (site.py cost_value) and v3.css shows
   the chosen one; v3.js and compare.js write theirs with costScale and costNumber and redraw on the "costunit" event.
   A key with data-cost-unit-choice (site.py cost_switch) changes it everywhere, keeps it in localStorage and in the
   address (the rest of the address and its history state stay). Without JavaScript costs read per 1,000 questions. */
const COST_UNITS = { '1k': { label: 'per 1,000 questions', scale: 1 }, '1m': { label: 'per 1M questions', scale: 1000 } };
const costUnit = () => (document.documentElement.dataset.costUnit === '1m' ? '1m' : '1k');
/* A cost per 1,000 questions times costScale() is the cost in the chosen unit. */
const costScale = () => COST_UNITS[costUnit()].scale;
const costLabel = () => COST_UNITS[costUnit()].label;
/* A cost in the chosen unit, without its $, as site.py cost_text writes it: per 1,000 questions with three decimals (two
   significant figures where that reads 0.000); per 1M questions with cents below 100, whole dollars from there. */
function costNumber(value) {
  if (costUnit() === '1m') return value.toLocaleString('en-US', value < 100 ? { minimumFractionDigits: 2, maximumFractionDigits: 2 } : { maximumFractionDigits: 0 });
  const text = value.toFixed(3);
  return text === '0.000' && value ? value.toPrecision(2) : text;
}
/* The cost unit's keys for a script's own markup, the chosen one pressed (site.py cost_switch). */
const costSwitch = () =>
  `<span class="cost-unit" role="group" aria-label="Cost unit">${Object.entries(COST_UNITS).map(([unit, { label }]) =>
    `<button type="button" class="key" data-cost-unit-choice="${unit}" aria-pressed="${unit === costUnit()}">${label}</button>`).join('')}</span>`;
(function setupCostUnit() {
  const root = document.documentElement;
  const press = () => document.querySelectorAll('[data-cost-unit-choice]').forEach(key => {
    key.setAttribute('aria-pressed', String(key.dataset.costUnitChoice === costUnit()));
  });
  const keep = unit => {
    try {
      localStorage.setItem('costUnit', unit);
    } catch (error) {
      /* Storage may be unavailable; the address still carries the choice. */
    }
  };
  const asked = new URLSearchParams(window.location.search).get('cost-unit');
  if (asked in COST_UNITS) {
    root.dataset.costUnit = asked;
    keep(asked);
  }
  press();
  document.addEventListener('click', event => {
    const key = event.target.closest('[data-cost-unit-choice]');
    if (!key || key.dataset.costUnitChoice === costUnit()) return;
    const unit = key.dataset.costUnitChoice;
    root.dataset.costUnit = unit;
    keep(unit);
    const url = new URL(window.location.href);
    url.searchParams.set('cost-unit', unit);
    history.replaceState(history.state, '', url);
    press();
    document.dispatchEvent(new CustomEvent('costunit'));
  });
})();

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

/* Every page: the view bar's group, from ?models= (all, decision or chat; missing or unknown means all; trailing dots,
   punctuation or spaces are dropped, so "all." reads as all). The bar marks its row 2 choice, the row 1 links and the top
   bar's benchmark links keep the group, and each element whose data-models lists other groups only is
   hidden (and shown again when it lists this one), before the page's own scripts run. <html data-models-view> carries
   the group for them. The bar's height is kept in --view-bar-h, so the page scrolls links and parts below it. */
(function setupViewBar() {
  const asked = (new URLSearchParams(window.location.search).get('models') ?? '').replace(/[^a-z]+$/i, '');
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
  // Links marked data-keep-group (the top bar's Page images, Hallucination, Web grounding and PWS-Decisions, the
  // experiments line) keep the group too,
  // so no press loses it.
  document.querySelectorAll('a[data-keep-group]').forEach(link => {
    const [path, fragment] = link.getAttribute('href').split('#');
    link.setAttribute('href', `${path.split('?')[0]}?models=${group}${fragment ? `#${fragment}` : ''}`);
  });
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${bar.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(bar);
})();

/* Every page: the view bar's row 3, the measure. A key whose part (#accuracy, #non-hallucination, #cost, #latency) is on
   the page links to it (the query, so the group, stays): the three test pages, and any other page with a part of that
   id, as Web grounding's Cost; the others open the home page's part with the group in view. The key of the part in
   view is marked: the part that crosses a line a quarter of the way down the window below the bar, or the key just
   pressed until the reader scrolls on, as a part at the end of the page may not reach that line. Between parts no key
   is marked. A page opened without a part in the address marks no key until the reader scrolls or presses a key; with
   one, its key is marked. The marked key pressed opens Home in its default state (the view bar's data-home), as every
   marked key of the view bar and the navigation bar does. */
(function setupMeasureRow() {
  const bar = document.querySelector('.view-bar');
  if (!bar) return;
  const group = document.documentElement.dataset.modelsView;
  const links = [...bar.querySelectorAll('a[data-view-measure]')];
  const parts = [];
  links.forEach(link => {
    const key = link.dataset.viewMeasure;
    const part = document.getElementById(key);
    if (part) {
      link.setAttribute('href', `#${key}`);
      parts.push({ link, part });
    } else {
      link.setAttribute('href', `${link.getAttribute('href').split(/[?#]/)[0]}?models=${group}#${key}`);
    }
  });
  if (!parts.length) return;
  const mark = key => links.forEach(link => {
    if (link.dataset.viewMeasure === key) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  });
  let pressed = null;
  let pressedAt = 0;
  const inView = () => {
    const top = bar.offsetHeight;
    const line = top + (window.innerHeight - top) / 4;
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
    requestAnimationFrame(() => { pressedAt = window.scrollY; });
  };
  let queued = false;
  window.addEventListener('scroll', () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (pressed && Math.abs(window.scrollY - pressedAt) < 48) return;
      pressed = null;
      mark(inView());
    });
  }, { passive: true });
  bar.addEventListener('click', event => {
    const link = event.target.closest('a[data-view-measure]');
    const key = link?.dataset.viewMeasure;
    if (!key || !parts.some(found => found.link.dataset.viewMeasure === key)) return;
    if (link.hasAttribute('aria-current')) {
      link.href = bar.dataset.home;
      return;
    }
    press(key);
  });
  const fromHash = opening => {
    const key = decodeURIComponent(window.location.hash.slice(1));
    if (parts.some(({ link }) => link.dataset.viewMeasure === key)) press(key);
    else mark(opening ? null : inView());
  };
  window.addEventListener('hashchange', () => fromHash(false));
  // A page opened without a part in the address marks no key until the reader scrolls or presses a key.
  fromHash(true);
})();

/* Every page: a row 2 key keeps the view. Pressed, it opens its group with the cost unit (?cost-unit=) and the part of
   row 3's marked key (#cost), so Decision pressed at a page's #cost opens that page's #cost for decision models, in the
   same unit. With no key marked (between parts) it opens the top of the page. The marked group pressed opens Home in
   its default state (the view bar's data-home). */
(function keepViewOnGroup() {
  const bar = document.querySelector('.view-bar');
  if (!bar) return;
  bar.addEventListener('click', event => {
    const link = event.target.closest('a[data-view-group]');
    if (!link) return;
    if (link.hasAttribute('aria-current')) {
      link.href = bar.dataset.home;
      return;
    }
    const url = new URL(link.href);
    url.searchParams.set('cost-unit', costUnit());
    url.hash = bar.querySelector('a[data-view-measure][aria-current]')?.dataset.viewMeasure ?? '';
    link.href = url.href;
  });
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
