/* The logic & math site's script: the model group of the test pages (?models=, after tb-next site.js setupViewBar), the
   sticky header's height, old #anchors that moved to another page, the leaderboard's keys and details boxes (after the
   backgammon site's bg.js), the cost unit (tb-next setupCostUnit), the Dark / Light switch (tb-next setupTheme,
   unchanged) and the question index's filters. Every page works without it (the Decision copy of each test page's parts
   shows, the leaderboard shows Logic with every row and every details box in its row, costs read per 1,000 questions). */

/* The model group from ?models= (all, decision, chat, small-chat or small-decision; the old small means small-chat;
   missing or unknown means decision, the default). Each element
   whose data-models lists other groups only is hidden; the page's Models key of the group is marked; the links that
   keep the group (data-keep-group) carry it. */
(function setupModels() {
  const groups = ['all', 'decision', 'chat', 'small-chat', 'small-decision'];
  const asked = (new URLSearchParams(window.location.search).get('models') ?? '').replace(/[^a-z]+$/i, '');
  const group = asked === 'small' ? 'small-chat' : groups.includes(asked) ? asked : 'decision';
  window.modelsGroup = group;
  if (asked === 'small') {  // an old link: Small models is now Small chat and Small decision models (Ümit #3876)
    const url = new URL(window.location.href);
    url.searchParams.set('models', group);
    history.replaceState(history.state, '', url);
  }
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  document.querySelectorAll('a[data-view-group]').forEach(link => {
    if (link.dataset.viewGroup === group) {
      link.setAttribute('aria-current', 'true');
      // A second tap on the selected Models key clears the filter to All (Ümit #3923, as on backgammon #3925).
      const url = new URL(link.href);
      url.searchParams.set('models', 'all');
      link.href = url.toString();
    } else link.removeAttribute('aria-current');
  });
  window.keepGroup = value => document.querySelectorAll('a[data-keep-group]').forEach(link => {
    const [path, fragment] = link.getAttribute('href').split('#');
    link.setAttribute('href', `${path.split('?')[0]}?models=${value}${fragment ? `#${fragment}` : ''}`);
  });
  if (!document.getElementById('leaderboard')) window.keepGroup(group);
  // A test page's selected Part or Measure key (aria-current="page"): a second tap goes back to the front page with the
  // same models in view (Ümit #3923; the earlier rule "selected key → Home"). Set after keepGroup, which would undo it.
  const front = document.querySelector('.site-bar nav a');
  if (front) document.querySelectorAll('.view-keys a[aria-current="page"]').forEach(link => {
    const url = new URL(front.href);
    url.searchParams.set('models', group);
    link.href = url.toString();
  });
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

/* The leaderboard's keys (Ümit #2980 item 4): the part (Logic, Math, Both: one panel each), the models (All, Chat models,
   Decision models: rows of the other type go out of view, class hl-off; Small chat and Small decision models: the rows
   of that type whose model is small, data-small, with the group's one-line rule under the keys) and All setups (every setup its own row); the
   ranks are the places among the rows in view. The choice is kept in the address (?part=, ?models=, ?setups=all), and
   the More views links carry the models. Expander keys open a row's other settings. */
(function setupLeaderboard() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  const params = new URLSearchParams(window.location.search);
  const parts = ['logic', 'math', 'together'];
  const groups = ['all', 'chat', 'decision', 'small-chat', 'small-decision'];
  const shows = tr => state.filter === 'all'
    || (state.filter.startsWith('small-') ? tr.dataset.small === 'true' && `small-${tr.dataset.hlType}` === state.filter : tr.dataset.hlType === state.filter);
  const askedPart = params.get('part') === 'both' ? 'together' : params.get('part');
  const state = {
    part: parts.includes(askedPart) ? askedPart : 'logic',
    filter: window.modelsGroup,
    setups: params.get('setups') === 'all',
  };
  const apply = keep => {
    board.querySelectorAll('[data-lb-part]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.lbPart === state.part)));
    board.querySelectorAll('[data-lb-filter]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.lbFilter === state.filter)));
    board.querySelector('[data-lb-setups]').setAttribute('aria-pressed', String(state.setups));
    board.querySelectorAll('[data-lb-small-rule]').forEach(rule => { rule.hidden = rule.dataset.lbSmallRule !== state.filter; });
    board.querySelectorAll('[data-lb-panel]').forEach(panel => {
      panel.hidden = panel.dataset.lbPanel !== state.part;
      panel.querySelectorAll('[data-lb-view]').forEach(view => { view.hidden = (view.dataset.lbView === 'setups') !== state.setups; });
      let shown = 0;
      panel.querySelectorAll('tbody tr[data-hl-type]').forEach(tr => {
        tr.classList.toggle('hl-off', !shows(tr));
        if (!tr.classList.contains('hl-sub') && !tr.classList.contains('hl-off') && !tr.closest('[data-lb-view]').hidden) {
          shown += 1;
          tr.querySelector('.lb-rank').textContent = String(shown);
        }
      });
      panel.querySelector('.lb-empty').hidden = shown > 0;
    });
    window.keepGroup(state.filter);
    if (keep) {
      const url = new URL(window.location.href);
      url.searchParams.set('part', state.part === 'together' ? 'both' : state.part);
      url.searchParams.set('models', state.filter);
      if (state.setups) url.searchParams.set('setups', 'all'); else url.searchParams.delete('setups');
      history.replaceState(history.state, '', url);
    }
    board.dispatchEvent(new CustomEvent('lb-change'));
  };
  // A second tap on the selected key undoes it (Ümit #3923): a part back to Logic; a models filter cleared to All (as on
  // backgammon, #3925).
  board.querySelectorAll('[data-lb-part]').forEach(k => k.addEventListener('click', () => {
    state.part = state.part === k.dataset.lbPart && k.dataset.lbPart !== 'logic' ? 'logic' : k.dataset.lbPart; apply(true); }));
  board.querySelectorAll('[data-lb-filter]').forEach(k => k.addEventListener('click', () => {
    const key = k.dataset.lbFilter;
    state.filter = state.filter !== key ? key : 'all'; apply(true); }));
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

/* A leaderboard row's details box (as the backgammon site's, bg.js headlineDetails). A tap opens it and a second tap on
   the row, a tap outside it or Escape closes it; with a mouse it shows while the pointer is on the row; with the keyboard
   while the focus is in the row (the model's name, then the box's links), and focus beats the pointer. The box is placed
   under the row (above it near the bottom of the window), within the window's width, capped and scrolling inside where
   neither side has room. Without JavaScript every box is shown in its row. */
(function setupDetails() {
  const board = document.getElementById('leaderboard');
  if (!board) return;
  let open = null, pinned = false, pointer = 'mouse', quiet = false;
  const boxOf = tr => document.getElementById(tr.dataset.box);
  const place = () => {
    if (!open) return;
    const box = boxOf(open), row = open.getBoundingClientRect(), cell = open.querySelector('td.model').getBoundingClientRect();
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
  const hide = () => {
    if (!open) return;
    boxOf(open).classList.remove('open');
    open.classList.remove('hl-open');
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
    box.classList.add('open');
    place();
  };
  let pointing = false, keyed = false;
  const held = () => !!open && keyed && open.contains(document.activeElement);
  document.addEventListener('pointerdown', event => {
    pointing = true;
    if (board.contains(event.target)) pointer = event.pointerType || 'mouse';
  }, true);
  const released = () => setTimeout(() => { pointing = false; });
  document.addEventListener('pointerup', released, true);
  document.addEventListener('pointercancel', released, true);
  board.querySelectorAll('tbody tr[data-box]').forEach(tr => {
    tr.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse' && !pinned && !held()) show(tr, false); });
    tr.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse' && !pinned && open === tr && !held()) hide(); });
    tr.addEventListener('focusin', () => {
      keyed = !pointing;
      if (keyed && open !== tr && !quiet) show(tr, false);
    });
    tr.addEventListener('focusout', event => { if (open === tr && !pinned && !tr.contains(event.relatedTarget)) hide(); });
    tr.addEventListener('click', event => {
      if (pointer === 'mouse' || event.detail === 0 || boxOf(tr).contains(event.target) || event.target.closest('.hl-more')) return;
      event.preventDefault();  // a tap opens the box; its own link opens the answers
      if (open === tr && pinned) hide(); else show(tr, true);
    });
  });
  document.addEventListener('click', event => { if (open && !open.contains(event.target)) hide(); });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !open) return;
    const name = open.querySelector('.model-name');
    const inside = open.contains(document.activeElement);
    hide();
    if (inside && name) { quiet = true; name.focus(); quiet = false; }
  });
  addEventListener('scroll', place, { passive: true });
  addEventListener('resize', place);
  board.addEventListener('lb-change', () => { if (open && (open.classList.contains('hl-off') || open.closest('[hidden]'))) hide(); });
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
