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
   address (the rest of the address and its history state stay); a second tap on the pressed key goes back to the
   default, per 1,000 questions (our reading of the project lead's "undo", bus #3923; her word on it is pending, #3945).
   Without JavaScript costs read per 1,000 questions. */
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
    if (!key) return;
    const unit = key.dataset.costUnitChoice !== costUnit() ? key.dataset.costUnitChoice : costUnit() !== '1k' ? '1k' : null;
    if (!unit) return;
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
    // The theme is always explicit on <html> (data-theme "light" or "dark"), so the suite strip (suite-bar.css), which
    // follows the system setting without it, matches the page.
    document.documentElement.dataset.theme = choice === 'light' ? 'light' : 'dark';
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every page: the model type and class, from ?models= (all, decision or chat; missing or unknown means all; trailing
   dots, punctuation or spaces are dropped, so "all." reads as all) and ?class= (one or more class keys, comma-separated;
   unknown ones are dropped). The old small addresses (?models=small-chat, small-decision, and small, read as
   small-chat) read as the type with Tiny and Small pressed, the nearest view to the old small ones, unless ?class= says
   otherwise. Each element whose data-models lists other types only is hidden (and shown again when it lists this one),
   before the page's own scripts run; <html data-models-view> carries the type for them, and a page's type keys
   (.group-switch) mark it; the marked key leads to All models, so a second tap clears the type (the three sites' rule
   for the model keys, bus #3937, #3953). The type and class asked for stay in the links marked data-keep-group and in
   every link to another page with the model keys (MODEL_PAGES: the home page's Leaderboard reads them too). The
   sticky header's height (the suite strip and the site's bar) is kept in --view-bar-h, so the page scrolls links and
   parts below it. */
const GROUP_KEYS = ['all', 'decision', 'chat'];
const ADDRESS = new URLSearchParams(window.location.search);
const ASKED_GROUP = (asked => (asked === 'small' ? 'small-chat' : asked))((ADDRESS.get('models') ?? '').replace(/[^a-z]+$/i, ''));
const OLD_SMALL = ['small-chat', 'small-decision'].includes(ASKED_GROUP);
const ASKED_TYPE = OLD_SMALL ? ASKED_GROUP.slice(6) : (GROUP_KEYS.includes(ASKED_GROUP) ? ASKED_GROUP : null);
const ASKED_CLASSES = ADDRESS.has('class')
  ? [...new Set(ADDRESS.get('class').split(/[\s,]+/).map(key => key.replace(/[^a-z]+$/i, '').toLowerCase()).filter(Boolean))]
  : (OLD_SMALL ? ['tiny', 'small'] : []);
/* The address of a page with a type (null: none asked) and classes, its hash kept apart. */
const modelsQuery = (type, classes) => [type ? `models=${type}` : '', classes.length ? `class=${classes.join(',')}` : '']
  .filter(Boolean).join('&');
/* The pages with model keys, inside the site (its root: the top bar's title link). */
const MODEL_PAGES = ['', 'english/', 'turkish-vs-english/', 'dont-know/', 'web-grounding/', 'pws-decisions/', 'vision/'];
const keepModels = (type, classes) => {
  const root = document.querySelector('.site-title')?.href;
  const pages = root ? MODEL_PAGES.map(page => new URL(page, root).pathname) : [];
  document.querySelectorAll('a[href]:not([data-group-key])').forEach(link => {
    const href = link.getAttribute('href');
    if (href.startsWith('#')) return;
    const target = new URL(href, window.location.href);
    if (!link.hasAttribute('data-keep-group') && (target.origin !== window.location.origin
        || target.pathname === window.location.pathname || !pages.includes(target.pathname))) return;
    // The link's own query (as the home page's ?tab=) stays; the type and class are set or dropped.
    const [path, fragment] = href.split('#');
    const [base, own] = path.split('?');
    const query = new URLSearchParams(own ?? '');
    query.delete('models');
    query.delete('class');
    const kept = [query.toString(), modelsQuery(type, classes)].filter(Boolean).join('&');
    link.setAttribute('href', `${base}${kept ? `?${kept}` : ''}${fragment ? `#${fragment}` : ''}`);
  });
};
(function setupGroup() {
  const group = ASKED_TYPE ?? 'all';
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  document.querySelectorAll('.group-switch a[data-group-key]').forEach(link => {
    if (link.dataset.groupKey === group) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  });
  if (ASKED_TYPE || ASKED_CLASSES.length) keepModels(ASKED_TYPE, ASKED_CLASSES);
  const header = document.querySelector('.site-header');
  if (!header) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${header.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(header);
})();

/* Every page with model rows besides the home page: the Class keys under the type keys (sitebuild/site.py
   group_switch; the Leaderboard's keys and rule, Ümit #4217), combined with the type in view. A class key with no row
   of the type in view hides (and lets go if it was pressed); a second tap on the pressed key, or All, clears it; a key
   pressed while two are (an old small address) keeps only itself. While a class is chosen each element of a model
   (data-class: a table row or a bar; empty for a setup only this site ran, shown under Class: All only) of another
   class goes out of view (class-off), a bar chart's heading with no bar left goes with its bars, a table or chart left
   with no row says so in its place, and the class rule shows under the keys. The choice is kept in the address
   (?class=, the old small address read as its type), so Back from a model page returns to the same view, and in the
   type keys and the links marked data-keep-group. */
(function classPages() {
  const switcher = document.querySelector('.class-switch');
  const group = ASKED_TYPE ?? 'all';
  const typeLinks = [...document.querySelectorAll('.group-switch a[data-group-key]')];
  const marked = [...document.querySelectorAll('[data-class]')];
  const present = new Set(marked.filter(element => !element.closest('[data-models][hidden]')).map(element => element.dataset.class));
  let classes = switcher ? ASKED_CLASSES.filter(key => key && present.has(key)) : ASKED_CLASSES;
  const links = () => {
    typeLinks.forEach(link => {
      const url = new URL(window.location.href);
      url.hash = '';
      url.search = modelsQuery(link.dataset.groupKey === group ? null : link.dataset.groupKey, classes);
      link.href = url.href;
    });
    if (switcher) keepModels(ASKED_TYPE, classes);
  };
  links();
  if (!switcher) return;
  // A type with no model row of any class (a page whose rows are all of the other type) has no class to pick.
  switcher.classList.toggle('class-off', ![...present].some(Boolean));
  const line = document.querySelector('.class-line');
  // Each list or table of model rows: its rows, the part that goes out of view when none is left, and the note that
  // then stands in its place (added once, after it).
  const holders = [...new Set(marked.map(element => element.parentElement))].map(holder => {
    const table = holder.closest('table');
    const box = table ? (table.closest('.table-wrap') ?? table) : holder;
    const note = document.createElement('p');
    note.className = 'note class-empty';
    note.hidden = true;
    note.textContent = 'No model of the chosen class here.';
    box.after(note);
    const axis = holder.matches('ol.hbars') && holder.previousElementSibling?.matches('.hbar-axis') ? holder.previousElementSibling : null;
    return { holder, box, axis, note };
  });
  const apply = () => {
    switcher.querySelectorAll('button[data-class-key]').forEach(key => {
      const found = key.dataset.classKey;
      key.hidden = found !== 'all' && !present.has(found);
      key.setAttribute('aria-pressed', String(found === 'all' ? !classes.length : classes.includes(found)));
    });
    marked.forEach(element => element.classList.toggle('class-off', classes.length > 0 && !classes.includes(element.dataset.class)));
    holders.forEach(({ holder, box, axis, note }) => {
      const rows = [...holder.children].filter(child => child.hasAttribute('data-class'));
      const empty = rows.every(row => row.classList.contains('class-off'));
      [box, axis].forEach(part => part?.classList.toggle('class-off', empty));
      note.hidden = !empty;
      let heading = null;
      let seen = false;
      const close = () => heading?.classList.toggle('class-off', !seen);
      [...holder.children].forEach(child => {
        if (child.matches('.hbar-group')) {
          close();
          heading = child;
          seen = false;
        } else if (!child.classList.contains('class-off')) seen = true;
      });
      close();
    });
    if (line) line.hidden = !classes.length;
  };
  switcher.addEventListener('click', event => {
    const key = event.target.closest('button[data-class-key]');
    if (!key) return;
    const chosen = key.dataset.classKey;
    classes = chosen === 'all' || (classes.length === 1 && classes[0] === chosen) ? [] : [chosen];
    apply();
    links();
    const url = new URL(window.location.href);
    url.search = modelsQuery(ASKED_TYPE, classes);
    history.replaceState(history.state, '', url.href);
  });
  apply();
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

/* In-page tab rows (.face-nav): in each row the tab of the part in view is marked, by a line a quarter of the way down
   the window below the header, or the tab just pressed until the reader scrolls on, as a part at the end of the page
   may not reach that line. A part that is a heading runs to the next part of any row after it in its section, so a
   section's tab gives way to a step's tab inside it. Between parts no tab is marked, and a page opened without a part
   in the address marks none until the reader scrolls or presses a tab. */
(function markFaceNav() {
  const header = document.querySelector('.site-header');
  const rows = [...document.querySelectorAll('.face-nav')]
    .map(row => [...row.querySelectorAll('a[href^="#"]')]
      .map(link => ({ link, part: document.getElementById(decodeURIComponent(link.getAttribute('href').slice(1))) }))
      .filter(({ part }) => part))
    .filter(row => row.length);
  if (!rows.length) return;
  const parts = [...new Set(rows.flat().map(({ part }) => part))];
  const span = part => {
    const box = part.getBoundingClientRect();
    if (!/^H[1-6]$/.test(part.tagName)) return [box.top, box.bottom];
    const section = part.parentElement;
    let end = section.getBoundingClientRect().bottom;
    parts.forEach(other => {
      if (other !== part && section.contains(other) && part.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING) {
        end = Math.min(end, other.getBoundingClientRect().top);
      }
    });
    return [box.top, end];
  };
  const inView = () => {
    const top = header ? header.offsetHeight : 0;
    const line = top + (window.innerHeight - top) / 4;
    return rows.map(row => {
      let best = null;
      let bestTop = -Infinity;
      row.forEach(entry => {
        if (!entry.part.offsetParent) return;
        const [start, end] = span(entry.part);
        if (start <= line && end > line && start > bestTop) {
          best = entry;
          bestTop = start;
        }
      });
      return best;
    });
  };
  const show = chosen => rows.forEach((row, i) => row.forEach(entry => {
    if (entry === chosen[i]) entry.link.setAttribute('aria-current', 'location');
    else entry.link.removeAttribute('aria-current');
  }));
  let pressed = false;
  let pressedAt = 0;
  const press = part => requestAnimationFrame(() => {
    const now = inView();
    show(rows.map((row, i) => row.find(entry => entry.part === part) ?? now[i]));
    pressed = true;
    pressedAt = window.scrollY;
  });
  let queued = false;
  window.addEventListener('scroll', () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (pressed && Math.abs(window.scrollY - pressedAt) < 48) return;
      pressed = false;
      show(inView());
    });
  }, { passive: true });
  const fromHash = opening => {
    const part = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (part && parts.includes(part)) press(part);
    else show(opening ? [] : inView());
  };
  window.addEventListener('hashchange', () => fromHash(false));
  fromHash(true);
})();

/* Home page: the Leaderboard (sitebuild/leaderboard.py). Its controls: the part (Turkish, Turkish reading, Turkish
   grammar, English reading or Both, Turkish first; Ümit #4181), the type (All, Chat models or Decision models; Decision models unless ?models= asks for another) and All
   setups, which shows today's full ranking with its tabs (#all-setups, v3.js) in place of the one-row-per-model table;
   then the Class keys (All, Tiny, Small, Medium, Large, Efficient, Workhorse, Flagship; Ümit #4217), combined with the
   type; a class key with no row of the part in view under the type pressed hides (and lets go if it was pressed). A row
   outside the keys (its data-kind, its data-class; a row with no class, a setup only this site ran, shows under Class:
   All only) and its other-setting rows go out of view (lb-off). The first cell numbers the rows in view: on a table whose
   rows carry tie-group letters (the Turkish part, head Tier) the tier (leaderboard.py tiers(): a row joins the tier of
   the tier's top row when they share a letter, else it starts the next tier, marked lb-tier-start for the line between
   tiers), elsewhere (head Rank) the row's place, 1, 2, 3 without repeats, rows with the same score keeping the table's
   order (Zeki #4630); a row with web search (data-unranked) is numbered in neither and keeps its dash. While a class is
   chosen the class rule shows under the table; a part with no row in view says so. The type
   and classes asked for in the address (ASKED_TYPE, ASKED_CLASSES: ?models=, ?class=, as the other pages keep them in
   their links) are pressed first; the old small addresses (?models=small-chat, small, small-decision) press Tiny and
   Small together; small-chat opens on English, as before (the small open models ran in English only). Each row's
   expander shows or hides its other setups. Old addresses keep working: #headline lands on the Leaderboard; #board,
   #all-setups, #cost-table and #chart-tradeoff open All setups first; on the home page itself, #info, whose summary and
   notes moved, and #how-scores, which moved, open About (MOVED; the About page has its own #leaderboard). Without
   JavaScript the Turkish table, every row numbered among all, and the full ranking both show. */
(function leaderboard() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  const hash = decodeURIComponent(window.location.hash.slice(1));
  const MOVED = { info: 'about/#summary', 'how-scores': 'about/#how-scores' };
  if (document.body.classList.contains('home') && Object.hasOwn(MOVED, hash)) {
    window.location.replace(MOVED[hash]);
    return;
  }
  // A second tap on a pressed key undoes it: a type or class clears to All and All stays (the three sites' rule, bus
  // #3937, #3953); a part goes back to Turkish (our reading of "undo", #3923, #3945). A class key pressed while two are
  // (an old small address) keeps only itself.
  const DEFAULT_PART = 'turkish';
  const DEFAULT_TYPE = 'decision';
  const state = {
    part: ASKED_GROUP === 'small-chat' ? 'english' : DEFAULT_PART,
    type: ASKED_TYPE ?? DEFAULT_TYPE,
    classes: ASKED_CLASSES,
    all: false,
  };
  const allPanel = document.getElementById('all-setups');
  const classLine = board.querySelector('.lb-size-line');
  const number = table => {
    let top = null;
    let count = 0;
    let seen = 0;
    const tiered = table.dataset.part === 'turkish';
    table.querySelectorAll('tbody tr[data-score]:not(.lb-off)').forEach(row => {
      if (row.hasAttribute('data-unranked')) {
        row.classList.remove('lb-tier-start');
        return;
      }
      seen += 1;
      let starts = false;
      if (tiered) {
        const letters = row.dataset.letters;
        starts = top === null || ![...letters].some(letter => top.includes(letter));
        if (starts) { top = letters; count += 1; }
      } else count = seen;
      row.classList.toggle('lb-tier-start', tiered && starts && seen > 1);
      row.querySelector('td.rank').textContent = String(count);
    });
    table.closest('.lb-part').querySelector('.lb-empty').hidden = table.querySelector('tbody tr[data-score]:not(.lb-off)') !== null;
  };
  const apply = () => {
    board.querySelectorAll('[data-lb-part]').forEach(key => {
      if (key.tagName === 'BUTTON') key.setAttribute('aria-pressed', String(key.dataset.lbPart === state.part));
      else key.hidden = key.dataset.lbPart !== state.part;
    });
    board.querySelectorAll('button[data-lb-type]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.lbType === state.type)));
    // The class keys of the part in view: a class with no row under the type pressed hides, and lets go if pressed.
    const rows = [...board.querySelectorAll(`.lb-table[data-part="${state.part}"] tbody tr[data-score]`)];
    const present = new Set(rows.filter(row => state.type === 'all' || row.dataset.kind === state.type).map(row => row.dataset.class));
    state.classes = state.classes.filter(found => present.has(found));
    board.querySelectorAll('button[data-lb-class]').forEach(key => {
      const found = key.dataset.lbClass;
      key.hidden = found !== 'all' && !present.has(found);
      key.setAttribute('aria-pressed', String(found === 'all' ? !state.classes.length : state.classes.includes(found)));
    });
    board.querySelectorAll('tbody tr[data-kind]').forEach(row => {
      const off = (state.type !== 'all' && row.dataset.kind !== state.type)
        || (state.classes.length > 0 && !state.classes.includes(row.dataset.class));
      row.classList.toggle('lb-off', off);
    });
    board.querySelectorAll('.lb-table').forEach(number);
    if (classLine) classLine.hidden = !state.classes.length;
    board.querySelector('[data-lb-all]')?.setAttribute('aria-pressed', String(state.all));
    board.classList.toggle('all-open', state.all);
    allPanel?.classList.toggle('is-open', state.all);
    reveal();
  };
  // On a phone the controls are one strip that scrolls sideways: the pressed keys (the part, the filter) are brought
  // into view together where they fit, else the last pressed one.
  const strip = board.querySelector('.lb-controls');
  const reveal = () => {
    if (!strip || strip.scrollWidth <= strip.clientWidth) return;
    const base = strip.getBoundingClientRect().left - strip.scrollLeft;
    const keys = [...strip.querySelectorAll('[aria-pressed="true"]')].filter(key => key.offsetParent)
      .map(key => { const box = key.getBoundingClientRect(); return [box.left - base, box.right - base]; });
    if (!keys.length) return;
    const left = Math.min(...keys.map(([start]) => start));
    const right = Math.max(...keys.map(([, end]) => end));
    strip.scrollLeft = right - left + 16 <= strip.clientWidth ? Math.max(0, right - strip.clientWidth + 8) : Math.max(0, keys[keys.length - 1][0] - 8);
  };
  const openAll = open => {
    if (state.all === open) return;
    state.all = open;
    apply();
    document.dispatchEvent(new CustomEvent('leaderboard-view'));
  };
  board.addEventListener('click', event => {
    const key = event.target.closest('button');
    if (!key) return;
    if (key.dataset.lbPart) state.part = key.dataset.lbPart === state.part ? DEFAULT_PART : key.dataset.lbPart;
    else if (key.dataset.lbType) state.type = key.dataset.lbType !== state.type ? key.dataset.lbType : 'all';
    else if (key.dataset.lbClass) {
      const chosen = key.dataset.lbClass;
      state.classes = chosen === 'all' || (state.classes.length === 1 && state.classes[0] === chosen) ? [] : [chosen];
    } else if (key.hasAttribute('data-lb-all')) {
      openAll(!state.all);
      return;
    } else if (key.classList.contains('lb-more')) {
      const open = key.getAttribute('aria-expanded') !== 'true';
      key.setAttribute('aria-expanded', String(open));
      key.getAttribute('aria-controls').split(' ').forEach(id => {
        const row = document.getElementById(id);
        if (row) row.hidden = !open;
      });
      return;
    } else return;
    apply();
    board.dispatchEvent(new CustomEvent('lb-change'));
  });
  document.addEventListener('open-all-setups', () => openAll(true));
  apply();
  const INTO_ALL = ['board', 'all-setups', 'cost-table', 'chart-tradeoff', 'tab-accuracy', 'tab-confidence', 'tab-routing', 'tab-stability'];
  const land = (id, opening) => {
    if (id === 'headline') {
      history.replaceState(history.state, '', `${window.location.pathname}${window.location.search}#leaderboard`);
      if (!opening) board.scrollIntoView();
    } else if (INTO_ALL.includes(id)) {
      openAll(true);
      if (!opening) document.getElementById(id)?.scrollIntoView();
    }
  };
  land(hash, true);
  window.addEventListener('hashchange', () => land(decodeURIComponent(window.location.hash.slice(1)), false));
  // A link to a part of All setups on this page opens it before the browser scrolls there.
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link && INTO_ALL.includes(link.getAttribute('href').slice(1)) && !link.dataset.gotoTab) openAll(true);
  }, true);
  if (hash === 'headline') board.scrollIntoView();
})();

/* Home page: a Leaderboard row's details box, as on the Backgammon site. A tap on a phone opens it and a second tap on
   the row, a tap outside it or Escape closes it; with a mouse it shows while the pointer is on the row; with the
   keyboard while the focus is in the row (the model's name, then the box's link). Focus beats the pointer. The box is
   placed under the row (above it near the bottom of the window), within the window's width, and capped to the room
   there on a short screen, scrolling inside. Without JavaScript every box shows in its row. */
(function leaderboardDetails() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  let open = null;
  let pinned = false;
  let pointer = 'mouse';
  let quiet = false;
  const boxOf = row => document.getElementById(row.dataset.box);
  const place = () => {
    if (!open) return;
    const box = boxOf(open);
    const row = open.getBoundingClientRect();
    const cell = open.querySelector('td.model').getBoundingClientRect();
    const width = Math.min(380, document.documentElement.clientWidth - 16);
    box.style.width = `${width}px`;
    box.style.left = `${Math.max(8, Math.min(cell.left, document.documentElement.clientWidth - width - 8))}px`;
    box.style.maxHeight = '';
    const height = box.offsetHeight;
    const header = document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0;
    const bottom = window.innerHeight - 8;
    const roomBelow = bottom - row.bottom;
    const roomAbove = row.top - header - 4;
    if (height <= roomBelow) box.style.top = `${row.bottom}px`;
    else if (height <= roomAbove) box.style.top = `${row.top - height}px`;
    else if (Math.max(roomBelow, roomAbove) >= 120) {
      box.style.maxHeight = `${Math.max(roomBelow, roomAbove)}px`;
      box.style.top = `${roomBelow >= roomAbove ? row.bottom : row.top - roomAbove}px`;
    } else {
      box.style.maxHeight = `${Math.max(bottom - header - 4, 80)}px`;
      box.style.top = `${header + 4}px`;
    }
  };
  const hide = () => {
    if (!open) return;
    boxOf(open).classList.remove('open');
    open.classList.remove('lb-open');
    open = null;
    pinned = false;
  };
  const show = (row, pin) => {
    if (open !== row) hide();
    const box = boxOf(row);
    if (!box) return;
    open = row;
    pinned = pin;
    row.classList.add('lb-open');
    box.classList.add('open');
    place();
  };
  // Keyboard focus in the open row (its name or its box) keeps the box: the pointer leaving the row or entering another
  // row does not take it away until the focus leaves the row, Escape, a second tap or a click outside. Focus that a
  // press of the pointer gives neither opens a box nor holds one: the press itself decides.
  let pointing = false;
  let keyed = false;
  const held = () => !!open && keyed && open.contains(document.activeElement);
  document.addEventListener('pointerdown', event => {
    pointing = true;
    if (board.contains(event.target)) pointer = event.pointerType || 'mouse';
  }, true);
  const released = () => setTimeout(() => { pointing = false; });
  document.addEventListener('pointerup', released, true);
  document.addEventListener('pointercancel', released, true);
  board.querySelectorAll('tbody tr[data-box]').forEach(row => {
    row.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse' && !pinned && !held()) show(row, false); });
    row.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse' && !pinned && open === row && !held()) hide(); });
    row.addEventListener('focusin', () => {
      keyed = !pointing;
      if (keyed && open !== row && !quiet) show(row, false);
    });
    row.addEventListener('focusout', event => { if (open === row && !pinned && !row.contains(event.relatedTarget)) hide(); });
    row.addEventListener('click', event => {
      // A mouse click or a key (detail 0) follows the link; a link in the box or the expander does its own job.
      if (pointer === 'mouse' || event.detail === 0 || boxOf(row).contains(event.target) || event.target.closest('.lb-more')) return;
      event.preventDefault(); // a tap opens the box; its own link opens the answers
      if (open === row && pinned) hide();
      else show(row, true);
    });
  });
  document.addEventListener('click', event => { if (open && !open.contains(event.target)) hide(); });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !open) return;
    const name = open.querySelector('.model-name');
    const inside = open.contains(document.activeElement);
    hide();
    if (inside && name) {
      quiet = true;
      name.focus();
      quiet = false;
    }
  });
  window.addEventListener('scroll', place, { passive: true });
  window.addEventListener('resize', place);
  board.addEventListener('lb-change', () => { if (open && (open.classList.contains('lb-off') || !open.offsetParent)) hide(); });
})();
