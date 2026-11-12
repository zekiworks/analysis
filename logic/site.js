/* The logic & math site's script: the model group of the test pages (?models=, after tb-next site.js setupViewBar), the
   sticky header's height, old #anchors that moved to another page, the leaderboard's keys and details boxes (after the
   backgammon site's bg.js), the cost unit (tb-next setupCostUnit), the Dark / Light switch (tb-next setupTheme,
   unchanged) and the question index's filters. Every page works without it (the Decision copy of each test page's parts
   shows, the leaderboard shows Logic with every row and every details box in its row, costs read per 1,000 questions). */

/* The Vision tab's view (condition, part, models, class, chart or table) is kept for the browser tab (sessionStorage):
   opened again without it in the address (from the site's tabs), the page takes the view last shown, before the model
   group is read. Keys the address names win. */
(function restoreVision() {
  if (!document.getElementById('vision-keys')) return;
  let saved;
  try { saved = new URLSearchParams(sessionStorage.getItem('logicVisionView') || ''); } catch (e) { return; }
  const here = new URLSearchParams(window.location.search);
  let changed = false;
  saved.forEach((value, key) => { if (!here.has(key)) { here.set(key, value); changed = true; } });
  if (changed) history.replaceState(history.state, '', `${window.location.pathname}?${here}${window.location.hash}`);
})();

/* The model group from ?models= (the type: all, decision, chat; missing or unknown means decision, the default) and
   ?class= (all, tiny, small, medium, large, efficient, workhorse, flagship; missing means all), PREVIEW Ümit #4217 (the
   Size keys of #4156/#4198 before it: an old ?size= of tiny, small, medium or large opens that class, undisclosed All,
   and the address is rewritten). An old link's small, small-chat or small-decision opens that type (chat for the oldest
   small) with every class. A page with Class keys (data-view-size) holds a copy per type and class ('decision-tiny'; the
   type alone with class All); a page without them (Vision) a copy per type. Each element whose data-models lists other
   groups only is hidden; the page's Models and Class keys in view are marked, each keeping the other choice, a class key
   hidden when the chosen type has no setup of it on the page (data-has); the links that keep the group
   (data-keep-group) carry both. */
(function setupModels() {
  const types = ['all', 'decision', 'chat'];
  const sizes = ['all', 'tiny', 'small', 'medium', 'large', 'efficient', 'workhorse', 'flagship', 'undisclosed'];
  const params = new URLSearchParams(window.location.search);
  const asked = (params.get('models') ?? '').replace(/[^a-z]+$/i, '');
  const old = { small: 'chat', 'small-chat': 'chat', 'small-decision': 'decision' };
  const type = old[asked] ?? (types.includes(asked) ? asked : 'decision');
  const askedClass = params.get('class') ?? params.get('size');
  const size = sizes.includes(askedClass) ? askedClass : 'all';
  window.modelsGroup = type;
  window.modelsSize = size;
  if (asked in old || params.has('size')) {
    const url = new URL(window.location.href);
    url.searchParams.set('models', type);
    url.searchParams.delete('size');
    if (size !== 'all') url.searchParams.set('class', size);
    history.replaceState(history.state, '', url);
  }
  const sized = document.querySelector('a[data-view-size]') !== null;
  const group = sized && size !== 'all' ? `${type}-${size}` : type;
  const query = (t, s) => `?models=${t}${s !== 'all' ? `&class=${s}` : ''}`;
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  // A second tap on the selected Models or Class key clears that filter to All (Ümit #3923, as on backgammon #3925).
  document.querySelectorAll('a[data-view-group]').forEach(link => {
    const key = link.dataset.viewGroup;
    const on = key === type;
    if (on) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current');
    link.setAttribute('href', query(on ? 'all' : key, sized ? size : 'all'));
  });
  document.querySelectorAll('a[data-view-size]').forEach(link => {
    const key = link.dataset.viewSize;
    const on = key === size;
    if (on) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current');
    link.setAttribute('href', query(type, on ? 'all' : key));
    const item = link.closest('li[data-has]');
    if (item && !on) item.hidden = !item.dataset.has.split(/\s+/).includes(type);
  });
  window.keepGroup = (t, s) => document.querySelectorAll('a[data-keep-group]').forEach(link => {
    const [path, fragment] = link.getAttribute('href').split('#');
    link.setAttribute('href', `${path.split('?')[0]}${query(t, s)}${fragment ? `#${fragment}` : ''}`);
  });
  if (!document.getElementById('leaderboard')) window.keepGroup(type, size);
  // A test page's selected key (aria-current="page"), second tap:
  // - Measure (any, Accuracy too): back to the main ranking on the front page (the Text tab's leaderboard), keeping the part
  //   and the models/class choice (Ümit via zeki #4660: the measure pages need a real way out).
  // - Part: back to its row's default, Logic, with the same models, class and measure (#4205); on Logic itself nothing.
  // Set after keepGroup, which would undo it.
  const front = document.querySelector('.site-tabs a');
  document.querySelectorAll('.view-keys a[aria-current="page"]').forEach(link => {
    const row = link.closest('.view-keys-row');
    const label = (row?.querySelector('.view-keys-label')?.textContent ?? '').trim().toLowerCase();
    if (label.startsWith('measure') && front) {
      const part = (document.querySelector('.view-keys-row a[aria-current="page"]')?.textContent ?? 'Logic').trim().toLowerCase();
      const base = front.getAttribute('href').split(/[?#]/)[0];
      link.setAttribute('href', `${base}${query(type, sized ? size : 'all')}&part=${part === 'both' ? 'both' : part}#leaderboard`);
      return;
    }
    const first = link.closest('ul').querySelector('a');
    if (first === link) link.addEventListener('click', event => event.preventDefault());
    else link.setAttribute('href', first.getAttribute('href'));
  });
})();

/* The Vision tab's keys (Ümit #5266, as Reading's Vision page): Condition (b first; a, c, d), Part (logic first; math,
   both) and Show (chart first; table) switch the panel in view in place (data-vision-panel '<condition>-<part>',
   data-vision-show); a second tap on the selected key goes back to its row's first key (as the test pages' Part keys).
   The choice is kept in the address (?condition=, ?part=, ?show=, with ?models= and ?class= always written out) and for
   the browser tab (restoreVision); the Models and Class keys, which reload with another group, carry it. */
(function setupVision() {
  const keys = document.getElementById('vision-keys');
  if (!keys) return;
  const rows = { condition: ['b', 'a', 'c', 'd'], part: ['logic', 'math', 'both'], show: ['chart', 'table'] };
  const params = new URLSearchParams(window.location.search);
  const state = {};
  Object.entries(rows).forEach(([name, values]) => {
    const asked = (params.get(name) || '').toLowerCase();
    state[name] = values.includes(asked) ? asked : values[0];
  });
  const withState = href => {
    const url = new URL(href, window.location.href);
    if (!url.searchParams.has('models')) url.searchParams.set('models', window.modelsGroup);
    if (!url.searchParams.has('class')) url.searchParams.set('class', 'all');
    Object.keys(rows).forEach(name => url.searchParams.set(name, state[name]));
    return `?${url.searchParams}${url.hash}`;
  };
  const apply = keep => {
    document.querySelectorAll('[data-vision-panel]').forEach(panel => {
      panel.hidden = panel.dataset.visionPanel !== `${state.condition}-${state.part}`;
    });
    document.querySelectorAll('[data-vision-show]').forEach(view => { view.hidden = view.dataset.visionShow !== state.show; });
    keys.querySelectorAll('a[data-vision-key]').forEach(link => {
      const [name, value] = link.dataset.visionKey.split('=');
      const on = state[name] === value;
      if (on) link.setAttribute('aria-current', 'true'); else link.removeAttribute('aria-current');
      link.setAttribute('href', `?${name}=${on ? rows[name][0] : value}`);
    });
    keys.querySelectorAll('a[data-view-group], a[data-view-size]').forEach(link => {
      link.setAttribute('href', withState(link.getAttribute('href')));
    });
    const here = withState(window.location.href);
    if (keep) history.replaceState(history.state, '', `${window.location.pathname}${here}`);
    try { sessionStorage.setItem('logicVisionView', new URL(here, window.location.href).search); } catch (e) { /* private mode */ }
  };
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-vision-key]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    const [name, value] = link.dataset.visionKey.split('=');
    const inKeys = keys.contains(link);
    state[name] = inKeys && state[name] === value ? rows[name][0] : value;
    apply(true);
    if (!inKeys) keys.scrollIntoView({ block: 'nearest' });
  });
  // The Info link under the heading opens the closed Info block it points at (also when the address names it).
  const info = document.getElementById('info');
  if (info) {
    document.querySelectorAll('a[href="#info"]').forEach(link => link.addEventListener('click', () => { info.open = true; }));
    if (window.location.hash === '#info') info.open = true;
  }
  apply(false);
})();

/* --view-bar-h holds the sticky header's height (links to a part of a page land below it). */
(function setupHeader() {
  const head = document.querySelector('.site-header');
  if (!head) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${head.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(head);
})();

/* Old #anchors of this page that now live on another page (body data-moved: {id: its new address}): a reader who
   opens one is sent there. */
(function setupMoved() {
  const moved = JSON.parse(document.body.dataset.moved || '{}');
  const go = () => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (id && moved[id] && !document.getElementById(id)) window.location.replace(moved[id]);
  };
  go();
  window.addEventListener('hashchange', go);
})();

/* The leaderboard's keys (Ümit #2980 item 4; classes and tiers, PREVIEW Ümit #4217): the part (Logic, Math, Both: one
   panel each), the models (All, Chat models, Decision models) combined with the class (All, Tiny, Small, Medium, Large,
   Efficient, Workhorse, Flagship: data-class; rows of another type or class go out of view, class hl-off; a class key
   with no row of the chosen part, type and view is hidden) and All setups (every setup its own row). The # column shows
   each tiered row's tier among the rows in view (data-tiers, computed by the build for every type and class), a line
   above the first row of each tier after the first (class lb-tier-start); a with-web or sample row (data-untiered) shows
   '–' and is passed over. The choice is kept in the address (?part=, ?models=, ?class=, ?setups=all) and carried by the
   links to the test pages. Expander keys open a row's other settings. */
(function setupLeaderboard() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  const params = new URLSearchParams(window.location.search);
  const parts = ['logic', 'math', 'together'];
  const ofType = tr => state.filter === 'all' || tr.dataset.hlType === state.filter;
  const shows = tr => ofType(tr) && (state.size === 'all' || tr.dataset.class === state.size);
  const tierOf = tr => {
    const mark = (tr.dataset.tiers || '').split(' ').find(item => item.startsWith(`${state.filter}.${state.size}=`));
    return mark ? mark.split('=')[1] : '';
  };
  const askedPart = params.get('part') === 'both' ? 'together' : params.get('part');
  const state = {
    part: parts.includes(askedPart) ? askedPart : 'logic',
    filter: window.modelsGroup,
    size: window.modelsSize,
    setups: params.get('setups') === 'all',
  };
  const apply = keep => {
    board.querySelectorAll('[data-lb-part]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.lbPart === state.part)));
    board.querySelectorAll('[data-lb-filter]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.lbFilter === state.filter)));
    board.querySelectorAll('[data-lb-class]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.lbClass === state.size)));
    board.querySelector('[data-lb-setups]').setAttribute('aria-pressed', String(state.setups));
    board.querySelector('.lb-size-rule').hidden = state.size === 'all';
    board.querySelectorAll('[data-lb-panel]').forEach(panel => {
      panel.hidden = panel.dataset.lbPanel !== state.part;
      panel.querySelectorAll('[data-lb-view]').forEach(view => { view.hidden = (view.dataset.lbView === 'setups') !== state.setups; });
      let shown = 0, last = null;
      panel.querySelectorAll('tbody tr[data-hl-type]').forEach(tr => {
        tr.classList.toggle('hl-off', !shows(tr));
        tr.classList.remove('lb-tier-start');
        if (!tr.classList.contains('hl-sub') && !tr.classList.contains('hl-off') && !tr.closest('[data-lb-view]').hidden) {
          shown += 1;
          if (tr.dataset.untiered) { tr.querySelector('.lb-rank').textContent = '–'; return; }
          const tier = tierOf(tr);
          tr.querySelector('.lb-rank').textContent = tier;
          if (last !== null && tier !== last) tr.classList.add('lb-tier-start');
          last = tier;
        }
      });
      panel.querySelector('.lb-empty').hidden = shown > 0;
      if (!panel.hidden) {
        const rows = [...panel.querySelectorAll(`[data-lb-view="${state.setups ? 'setups' : 'models'}"] tbody tr.lb-row`)].filter(ofType);
        board.querySelectorAll('[data-lb-class]').forEach(k => {
          const key = k.dataset.lbClass;
          k.hidden = key !== 'all' && key !== state.size && !rows.some(tr => tr.dataset.class === key);
        });
      }
    });
    window.keepGroup(state.filter, state.size);
    if (keep) {
      const url = new URL(window.location.href);
      url.searchParams.set('part', state.part === 'together' ? 'both' : state.part);
      url.searchParams.set('models', state.filter);
      if (state.size !== 'all') url.searchParams.set('class', state.size); else url.searchParams.delete('class');
      if (state.setups) url.searchParams.set('setups', 'all'); else url.searchParams.delete('setups');
      history.replaceState(history.state, '', url);
    }
    board.dispatchEvent(new CustomEvent('lb-change'));
  };
  // A second tap on the selected key undoes it (Ümit #3923): a part back to Logic; a models or size filter cleared to All
  // (as on backgammon, #3925).
  board.querySelectorAll('[data-lb-part]').forEach(k => k.addEventListener('click', () => {
    state.part = state.part === k.dataset.lbPart && k.dataset.lbPart !== 'logic' ? 'logic' : k.dataset.lbPart; apply(true); }));
  board.querySelectorAll('[data-lb-filter]').forEach(k => k.addEventListener('click', () => {
    const key = k.dataset.lbFilter;
    state.filter = state.filter !== key ? key : 'all'; apply(true); }));
  board.querySelectorAll('[data-lb-class]').forEach(k => k.addEventListener('click', () => {
    const key = k.dataset.lbClass;
    state.size = state.size !== key ? key : 'all'; apply(true); }));
  board.querySelector('[data-lb-setups]').addEventListener('click', () => { state.setups = !state.setups; apply(true); });
  board.querySelectorAll('.hl-more').forEach(b => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') !== 'true';
    b.setAttribute('aria-expanded', String(open));
    b.getAttribute('aria-controls').split(' ').forEach(id => { const r = document.getElementById(id); if (r) r.hidden = !open; });
  }));
  apply(false);
  // On a narrow screen the keys scroll sideways in their row: bring the models key in use into view (?models=small).
  const controls = board.querySelector('.lb-controls');
  const pressed = board.querySelector('[data-lb-filter][aria-pressed="true"]');
  const past = pressed.getBoundingClientRect().right - controls.getBoundingClientRect().right;
  if (past > 0) controls.scrollLeft += past + 12;
})();

/* A model's details box (as the backgammon site's, bg.js headlineDetails): a leaderboard row's, and on the test pages a
   chart bar's or a full-table row's (every element with data-box). A tap opens it and a second tap on
   the row, a tap outside it or Escape closes it; with a mouse it shows while the pointer is on the row; with the keyboard
   while the focus is in the row (the model's name, then the box's links), and focus beats the pointer. The box is placed
   under the row (above it near the bottom of the window), within the window's width, capped and scrolling inside where
   neither side has room. Without JavaScript every box is shown in its row. */
(function setupDetails() {
  const rows = document.querySelectorAll('#leaderboard tbody tr[data-box], main [data-box]');
  if (!rows.length) return;
  const board = document.getElementById('leaderboard');
  let open = null, pinned = false, pointer = 'mouse', quiet = false;
  const boxOf = tr => document.getElementById(tr.dataset.box);
  const place = () => {
    if (!open) return;
    const box = boxOf(open), row = open.getBoundingClientRect(), cell = open.querySelector('td.model, .hbar-label').getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const width = Math.min(400, vw - 16);
    box.style.width = `${width}px`;
    box.style.left = `${Math.max(8, Math.min(cell.left, vw - width - 8))}px`;
    box.style.maxHeight = '';
    const height = box.offsetHeight;
    const header = document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0;
    const below = row.bottom;
    const bottom = innerHeight - 8;
    const roomBelow = bottom - below, roomAbove = row.top - header - 4;
    if (height <= roomBelow) box.style.top = `${below}px`;
    else if (height <= roomAbove) box.style.top = `${row.top - height}px`;
    else if (Math.max(roomBelow, roomAbove) >= 120) {
      box.style.maxHeight = `${Math.max(roomBelow, roomAbove)}px`;
      box.style.top = `${roomBelow >= roomAbove ? below : row.top - roomAbove}px`;
    } else {
      box.style.maxHeight = `${Math.max(bottom - header - 4, 80)}px`;
      box.style.top = `${header + 4}px`;
    }
  };
  // A row's Details key (phones, zeki #4793) says whether its box is open.
  const expand = (tr, value) => tr.querySelector(':scope > td .lb-details')?.setAttribute('aria-expanded', String(value));
  const hide = () => {
    if (!open) return;
    boxOf(open).classList.remove('open');
    open.classList.remove('hl-open');
    expand(open, false);
    open = null;
    pinned = false;
  };
  const show = (tr, pin) => {
    if (open !== tr) hide();
    const box = boxOf(tr);
    if (!box) return;
    open = tr;
    pinned = pin;
    tr.classList.add('hl-open');
    expand(tr, true);
    box.classList.add('open');
    place();
  };
  let pointing = false, keyed = false;
  const held = () => !!open && keyed && open.contains(document.activeElement);
  document.addEventListener('pointerdown', event => {
    pointing = true;
    pointer = event.pointerType || 'mouse';
  }, true);
  const released = () => setTimeout(() => { pointing = false; });
  document.addEventListener('pointerup', released, true);
  document.addEventListener('pointercancel', released, true);
  rows.forEach(tr => {
    tr.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse' && !pinned && !held()) show(tr, false); });
    tr.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse' && !pinned && open === tr && !held()) hide(); });
    tr.addEventListener('focusin', () => {
      keyed = !pointing;
      if (keyed && open !== tr && !quiet) show(tr, false);
    });
    tr.addEventListener('focusout', event => { if (open === tr && !pinned && !tr.contains(event.relatedTarget)) hide(); });
    tr.addEventListener('click', event => {
      if (event.target.closest('.lb-details')) {  // the Details key opens and closes the same box: a tap, a click or the keyboard
        event.preventDefault();
        if (open === tr) hide(); else show(tr, true);
        return;
      }
      if (pointer === 'mouse' || event.detail === 0 || boxOf(tr).contains(event.target) || event.target.closest('.hl-more')) return;
      event.preventDefault();  // a tap opens the box; its own link opens the answers
      if (open === tr && pinned) hide(); else show(tr, true);
    });
  });
  document.addEventListener('click', event => { if (open && !open.contains(event.target)) hide(); });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !open) return;
    const name = open.querySelector('.model-name, a');
    const inside = open.contains(document.activeElement);
    hide();
    if (inside && name) { quiet = true; name.focus(); quiet = false; }
  });
  addEventListener('scroll', place, { passive: true });
  addEventListener('resize', place);
  board?.addEventListener('lb-change', () => { if (open && (open.classList.contains('hl-off') || open.closest('[hidden]'))) hide(); });
})();

/* The cost unit, one choice for the whole site (tb-next site.js setupCostUnit): ?cost-unit= or localStorage. */
(function setupCostUnit() {
  const root = document.documentElement;
  const unit = () => (root.dataset.costUnit === '1m' ? '1m' : '1k');
  const press = () => document.querySelectorAll('[data-cost-unit-choice]').forEach(key => {
    key.setAttribute('aria-pressed', String(key.dataset.costUnitChoice === unit()));
  });
  const keep = value => {
    try {
      localStorage.setItem('costUnit', value);
    } catch (error) {
      /* Storage may be unavailable; the address still carries the choice. */
    }
  };
  const asked = new URLSearchParams(window.location.search).get('cost-unit');
  if (asked === '1k' || asked === '1m') {
    if (asked === '1m') root.dataset.costUnit = '1m';
    else delete root.dataset.costUnit;
    keep(asked);
  }
  press();
  document.addEventListener('click', event => {
    const key = event.target.closest('[data-cost-unit-choice]');
    if (!key || key.dataset.costUnitChoice === unit()) return;
    const value = key.dataset.costUnitChoice;
    if (value === '1m') root.dataset.costUnit = '1m';
    else delete root.dataset.costUnit;
    keep(value);
    const url = new URL(window.location.href);
    url.searchParams.set('cost-unit', value);
    history.replaceState(history.state, '', url);
    press();
  });
})();

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
    else document.documentElement.dataset.theme = 'dark';
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every question: filter the rows by ID, topic, English text status and a run's outcome (a run chosen shows only its
   column); the filters live in the
   address (?topic=Decimals&run=0&outcome=wrong) so a view can be shared. */
(function setupQuestionFilters() {
  const form = document.querySelector('[data-q-filters]');
  if (!form) return;
  const rows = Array.from(document.querySelectorAll('table.q-index tbody tr'));
  const fields = Object.fromEntries(Array.from(form.querySelectorAll('[data-filter]')).map(field => [field.dataset.filter, field]));
  const counter = document.querySelector('[data-q-count]');
  const runCount = fields.run ? fields.run.options.length - 1 : 0;
  const params = new URLSearchParams(window.location.search);
  for (const [name, field] of Object.entries(fields)) {
    const value = params.get(name);
    if (value !== null) field.value = value;
  }
  const apply = () => {
    const wanted = Object.fromEntries(Object.entries(fields).map(([name, field]) => [name, field.value.trim()]));
    const id = wanted.id.toLowerCase();
    let shown = 0;
    for (const row of rows) {
      let keep = (!id || row.dataset.id.toLowerCase().includes(id))
        && (!wanted.topic || row.dataset.topic === wanted.topic)
        && (!wanted.en || row.dataset.en === wanted.en);
      if (keep && wanted.outcome) {
        if (wanted.run) keep = row.dataset['r' + wanted.run] === wanted.outcome;
        else {
          keep = false;
          for (let index = 0; index < runCount; index++) if (row.dataset['r' + index] === wanted.outcome) { keep = true; break; }
        }
      }
      row.hidden = !keep;
      shown += keep;
    }
    document.querySelectorAll('table.q-index [data-run]').forEach(cell => { cell.hidden = !!wanted.run && cell.dataset.run !== wanted.run; });
    counter.textContent = `${shown.toLocaleString('en')} of ${rows.length.toLocaleString('en')} questions`;
    const url = new URL(window.location.href);
    for (const [name, value] of Object.entries(wanted)) {
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    }
    history.replaceState(history.state, '', url);
  };
  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  form.addEventListener('submit', event => event.preventDefault());
  form.querySelector('[data-q-reset]').addEventListener('click', () => {
    for (const field of Object.values(fields)) field.value = '';
    apply();
  });
  form.hidden = false;
  document.querySelector('[data-q-note]').hidden = false;
  apply();
})();
