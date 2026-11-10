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

/* Every page: the model group, from ?models= (all, decision, chat, small-chat or small-decision; missing or unknown
   means all; trailing dots, punctuation or spaces are dropped, so "all." reads as all; the old small reads as
   small-chat, so old links and bookmarks keep working). Each element whose data-models lists other groups only is
   hidden (and shown again when it lists this one), before the page's own scripts run; <html data-models-view> carries
   the group for them, and a page's group keys (.group-switch) mark it. A group asked for in the address stays in the
   links marked data-keep-group. The sticky header's height (the suite strip and the site's bar) is kept in
   --view-bar-h, so the page scrolls links and parts below it. */
const GROUP_KEYS = ['all', 'decision', 'chat', 'small-chat', 'small-decision'];
const ASKED_GROUP = (asked => (asked === 'small' ? 'small-chat' : asked))(
  (new URLSearchParams(window.location.search).get('models') ?? '').replace(/[^a-z]+$/i, ''));
(function setupGroup() {
  const asked = GROUP_KEYS.includes(ASKED_GROUP) ? ASKED_GROUP : null;
  const group = asked ?? 'all';
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  document.querySelectorAll('.group-switch a[data-group-key]').forEach(link => {
    if (link.dataset.groupKey === group) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
    const url = new URL(link.href);
    url.hash = '';
    link.href = url.href;
  });
  if (asked) {
    document.querySelectorAll('a[data-keep-group]').forEach(link => {
      const [path, fragment] = link.getAttribute('href').split('#');
      link.setAttribute('href', `${path.split('?')[0]}?models=${group}${fragment ? `#${fragment}` : ''}`);
    });
  }
  const header = document.querySelector('.site-header');
  if (!header) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${header.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(header);
})();

/* On a phone the tab row scrolls sideways: the tab of the page in view, and a link that takes the keyboard focus, are
   brought fully into view. */
(function keepTabInView() {
  const row = document.querySelector('.site-tabs ul');
  if (!row) return;
  const current = row.querySelector('a[aria-current]');
  if (current && row.scrollWidth > row.clientWidth) row.scrollLeft = Math.max(0, current.offsetLeft - 16);
  row.addEventListener('focusin', event => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
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

/* Home page: the Leaderboard (sitebuild/leaderboard.py). Its controls, one row: the part (English, Turkish or Both,
   Turkish first), the filter (All, Chat models, Decision models, Small chat models or Small decision models; Decision models
   unless ?models= asks for another), local to the table, and All setups, which shows today's full ranking with its tabs
   (#all-setups, v3.js) in place of the one-row-per-model table. A row outside the filter (its data-kind, and for a
   small group data-small as well) and its other-setting rows go out of view (lb-off); the rank cell shows the row's
   rank among the rows in view; under a small group its rule shows under the table (data-lb-small, the group's key). Each row's expander shows or hides its other
   setups. Old addresses keep working: #headline lands on the Leaderboard; #board, #all-setups, #cost-table and
   #chart-tradeoff open All setups first; on the home page itself, #info, whose summary and notes moved, and
   #how-scores, which moved, open About (MOVED; the About page has its own #leaderboard). Without JavaScript the
   Turkish table and the full ranking both show. */
(function leaderboard() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  const hash = decodeURIComponent(window.location.hash.slice(1));
  const MOVED = { info: 'about/#summary', 'how-scores': 'about/#how-scores' };
  if (document.body.classList.contains('home') && Object.hasOwn(MOVED, hash)) {
    window.location.replace(MOVED[hash]);
    return;
  }
  // Small chat models opens on English (leaderboard.py SMALL_PART): the small open models ran in English only. Small
  // decision models keeps the part in view.
  const state = {
    part: ASKED_GROUP === 'small-chat' ? 'english' : 'turkish',
    filter: GROUP_KEYS.includes(ASKED_GROUP) ? ASKED_GROUP : 'decision',
    all: false,
  };
  const allPanel = document.getElementById('all-setups');
  const apply = () => {
    board.querySelectorAll('[data-lb-part]').forEach(key => {
      if (key.tagName === 'BUTTON') key.setAttribute('aria-pressed', String(key.dataset.lbPart === state.part));
      else key.hidden = key.dataset.lbPart !== state.part;
    });
    board.querySelectorAll('button[data-lb-filter]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.lbFilter === state.filter)));
    board.querySelectorAll('tbody tr[data-kind]').forEach(row => {
      const small = state.filter.startsWith('small-');
      const kind = small ? state.filter.slice(6) : state.filter;
      const off = (small && !row.hasAttribute('data-small')) || (kind !== 'all' && row.dataset.kind !== kind);
      row.classList.toggle('lb-off', off);
      const rank = row.querySelector('td.rank');
      if (rank) rank.textContent = rank.dataset[`rank-${state.filter}`.replace(/-(\w)/g, (_, letter) => letter.toUpperCase())] ?? '';
    });
    board.querySelectorAll('[data-lb-small]').forEach(line => { line.hidden = line.dataset.lbSmall !== state.filter; });
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
    if (key.dataset.lbPart) state.part = key.dataset.lbPart;
    else if (key.dataset.lbFilter) {
      state.filter = key.dataset.lbFilter;
      if (state.filter === 'small-chat') state.part = 'english';
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
