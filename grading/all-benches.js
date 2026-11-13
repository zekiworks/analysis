'use strict';

/* All benches, /analysis/all-benches/ (sitebuild/all_benches.py). The page comes built: every view's chart, charts and
   tables are in it, every model's bar, row and dot with its kind and class (data-kind, data-class), the default
   view and the decision models shown. This script runs the ranking's three key rows (Ümit #4234, #4239): the type
   (All, Chat models, Decision models; Decision models first) and the class (All and the Reading site's Leaderboard's
   classes, Site.model_class), combined, which choose the models in view on the chart, the table under it, Head to head's choices, Full
   results and the charts, a second tap on a pressed key going back to All (the three sites' rule, as the Reading
   site's Leaderboard: site.js); and the score (Combined, then each bench), which picks what the chart ranks by and the
   table sorts by. A head of the table sorts by its column (again: the other way); a score column's head picks that
   score for the chart too. The address keeps the choice: ?models=all|chat (the Reading site's form), class=<class>,
   view=, sort= (Model or Size), order= (the other way), a=, b=, tab=, so Back from a model's page returns to the same
   view; the earlier ?board=vision opens Vision. ?model=<name> (or its slug or repo) shows that model's page instead.
   "tied" on the chart and in Head to head follows the page's one rule (Methodology #tied): apart only by at least
   100 / sqrt(n) points, n the smaller question count; on the combined score sqrt(sum of the three margins squared) / 3.
   The table's Rank is the place by the score in view among the rows in view, 1, 2, 3 without repeats (rows with the same
   score keep the table's order; Zeki #4630); the notes under it on
   models whose benches ran different setups follow the keys too. */
(function allBenches() {
  const DATA = JSON.parse(document.getElementById('ab-data')?.textContent || 'null');
  if (!DATA) return;
  const params = new URLSearchParams(window.location.search);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = text =>
    String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const number = value => {
    const text = Math.abs(value).toFixed(1);
    return (value < 0 && Number(text) !== 0 ? '\u2212' : '') + text;
  };
  // A cell without a score: its status, the reason on hover and focus (sitebuild/all_benches.py missing).
  const status = (word, reason) => `<span class="nm hint" tabindex="0" data-tip="${esc(reason)}">${word}</span>`;
  const models = new Map(DATA.models.map(model => [model.key, model]));
  const published = Object.fromEntries(DATA.benches.map(bench => [bench.key, bench.published]));

  /* ?model=: one model's page, the rest of the page hidden. */
  const asked = params.get('model');
  if (asked) {
    const wanted = asked.trim().toLowerCase();
    const page = $$('.ab-model').find(section =>
      [section.dataset.abModelName, section.dataset.abModel, (models.get(section.dataset.abModelKey) || {}).repo]
        .some(value => value && value.toLowerCase() === wanted));
    if (page) {
      $$('[data-ab-main]').forEach(part => { part.hidden = true; });
      page.hidden = false;
      document.title = `${page.dataset.abModelName} · ${document.title}`;
      const back = page.querySelector('[data-ab-back]');
      back?.addEventListener('click', event => {
        if (document.referrer && new URL(document.referrer).pathname === window.location.pathname && history.length > 1) {
          event.preventDefault();
          history.back();
        }
      });
      window.scrollTo(0, 0);
      return;
    }
  }

  const views = $$('[data-ab-view]').map(key => key.dataset.abView);
  const types = $$('[data-ab-type]').map(key => key.dataset.abType);
  const classes = $$('[data-ab-class]').map(key => key.dataset.abClass);
  const askedType = (params.get('models') ?? '').replace(/[^a-z]+$/i, '');
  const askedView = params.get('view') || (params.get('board') === 'vision' ? 'reading-vision' : DATA.default);
  const state = {
    type: types.includes(askedType) ? askedType : DATA.type,
    class: classes.includes(params.get('class')) ? params.get('class') : 'all',
    view: views.includes(askedView) ? askedView : DATA.default,
    sort: ['model', 'size'].includes(params.get('sort')) ? params.get('sort') : null,
    reversed: params.get('order') === 'reversed',
    tab: null,
  };

  function save() {
    const next = new URLSearchParams();
    if (state.type !== DATA.type) next.set('models', state.type);
    if (state.class !== 'all') next.set('class', state.class);
    if (state.view !== DATA.default) next.set('view', state.view);
    if (state.sort) next.set('sort', state.sort);
    if (state.reversed) next.set('order', 'reversed');
    if (state.a) next.set('a', state.a);
    if (state.b) next.set('b', state.b);
    if (state.tab) next.set('tab', state.tab);
    const query = next.toString();
    history.replaceState(history.state, '', (query ? `?${query}` : window.location.pathname) + window.location.hash);
  }

  const fits = item => (state.type === 'all' || item.kind === state.type) && (state.class === 'all' || item.class === state.class);
  const inView = element => fits({ kind: element.dataset.kind, class: element.dataset.class });
  const score = (model, view) => (view === 'combined' ? model.combined : (model.scores[view] || [null])[0]);
  function margin(view, a, b) {
    if (view === 'combined') return Math.sqrt(DATA.combined.reduce((sum, key) => sum + margin(key, a, b) ** 2, 0)) / 3;
    return 100 / Math.sqrt(Math.min(a.scores[view][1], b.scores[view][1]));
  }
  const tied = (view, a, b) => Math.abs(score(a, view) - score(b, view)) < margin(view, a, b);

  /* The chart of each view: the bars in view, "tied" against the bar in view before, the makers in view. */
  function drawBars() {
    $$('.ab-view[data-view]').forEach(panel => {
      const view = panel.dataset.view;
      const bars = $$('.ab-bar', panel);
      if (!bars.length) return;
      let previous = null;
      const makers = new Set();
      bars.forEach(bar => {
        const on = inView(bar);
        bar.classList.toggle('ab-off', !on);
        if (!on) return;
        const model = models.get(bar.dataset.key);
        bar.querySelector('.ab-tied').hidden = !(previous && tied(view, previous, model));
        previous = model;
        makers.add(bar.dataset.maker);
      });
      const none = panel.querySelector('.ab-none');
      if (none) none.hidden = previous !== null;
      $$('.ab-legend [data-maker]', panel).forEach(item => item.classList.toggle('ab-off', !makers.has(item.dataset.maker)));
    });
  }

  /* The table under the chart: rows in view, sorted, ranked by the score in view. */
  const table = document.querySelector('table.ab-main');
  const heads = table ? $$('thead th[data-ab-col]', table) : [];
  const columns = heads.map(head => head.dataset.abCol);
  // A column whose head says lower is better (data-ab-low: calibration error, latency, cost) sorts lowest first.
  const low = new Set(heads.filter(head => head.dataset.abLow !== undefined).map(head => head.dataset.abCol));
  const cellOf = (row, column) => row.children[1 + columns.indexOf(column)];
  const valueOf = (row, column) => {
    if (column === 'model') return row.dataset.name;
    if (column === 'size') return row.dataset.size === '' ? null : Number(row.dataset.size);
    const value = cellOf(row, column)?.dataset.v;
    return value === undefined ? null : Number(value);
  };
  function drawTable() {
    if (!table) return;
    const column = state.sort || state.view;
    const natural = column === 'model' || low.has(column) ? 1 : -1; // names A to Z; numbers highest first, or lowest
    const direction = state.reversed ? -natural : natural;
    const body = table.tBodies[0];
    const rows = Array.from(body.rows);
    rows.forEach(row => row.classList.toggle('ab-off', !inView(row)));
    $$('.ab-setup-note').forEach(note => note.classList.toggle('ab-off', !inView(note)));
    rows.sort((first, second) => {
      const a = valueOf(first, column);
      const b = valueOf(second, column);
      if (a === null || b === null) return a === b ? first.dataset.name.localeCompare(second.dataset.name) : a === null ? 1 : -1;
      if (a !== b) return (a < b ? -1 : 1) * direction;
      return first.dataset.name.localeCompare(second.dataset.name);
    });
    body.append(...rows);
    const scored = rows.filter(row => !row.classList.contains('ab-off') && valueOf(row, state.view) !== null)
      .sort((first, second) => valueOf(second, state.view) - valueOf(first, state.view));
    // Places 1, 2, 3 without repeats; the sort keeps rows with the same score in the table's order (Zeki #4630).
    const rank = new Map(scored.map((row, index) => [row, index + 1]));
    rows.forEach(row => { row.querySelector('.ab-rank').textContent = rank.has(row) ? String(rank.get(row)) : ''; });
    $$('thead th[data-ab-col]', table).forEach(head => {
      if (head.dataset.abCol === column) head.setAttribute('aria-sort', direction > 0 ? 'ascending' : 'descending');
      else head.removeAttribute('aria-sort');
    });
  }

  /* Full results: the rows in view, each kind's table shown while it has one. */
  function drawResults() {
    $$('.ab-kind-table').forEach(wrap => {
      const rows = $$('tbody tr', wrap);
      rows.forEach(row => row.classList.toggle('ab-off', !inView(row)));
      wrap.classList.toggle('ab-off', !rows.some(row => !row.classList.contains('ab-off')));
    });
  }

  /* The charts: the dots and names in view, and the count under each chart's title. */
  const noun = count => {
    const plural = state.type === 'all' ? 'models' : DATA.types[state.type].toLowerCase();
    return count === 1 ? plural.replace(/s$/, '') : plural;
  };
  function drawCharts() {
    $$('.ab-scatter [data-kind]').forEach(item => item.classList.toggle('ab-off', !inView(item)));
    $$('.ab-charts').forEach(panel => {
      const ranked = $$(`.ab-view[data-view="${panel.dataset.view}"] .ab-bar:not(.ab-off)`).length;
      $$('.ab-chart', panel).forEach(chart => {
        const sub = chart.querySelector('[data-ab-sub]');
        if (!sub) return;
        const dots = $$('a[data-kind]:not(.ab-off)', chart).length;
        const left = ranked - dots;
        sub.textContent = `${sub.dataset.abSub}: ${dots} ${noun(dots)}${left > 0 ? `; ${left} left out (${sub.dataset.rule})` : ''}`;
      });
    });
  }

  /* Head to head: the choices follow the keys; a choice out of view gives way to the first models in view. */
  const pickers = $$('[data-ab-pick]');
  const pickA = document.querySelector('[data-ab-pick="a"]');
  const pickB = document.querySelector('[data-ab-pick="b"]');
  function headToHead() {
    const a = models.get(pickA.value);
    const b = models.get(pickB.value);
    if (!a || !b) return;
    document.querySelector('[data-ab-name="a"]').textContent = a.label;
    document.querySelector('[data-ab-name="b"]').textContent = b.label;
    const rows = [['combined', 'Combined'], ...DATA.benches.map(bench => [bench.key, bench.label])].map(([key, label]) => {
      const first = score(a, key);
      const second = score(b, key);
      const open = key === 'combined' || published[key];
      let verdict;
      if (!open) verdict = '<span class="nm">not published yet</span>';
      else if (key === 'combined' && (a.nc || b.nc)) {
        verdict = `<span class="nm">no combined score for ${esc((a.nc ? a : b).label)}: one model did not answer every bench</span>`;
      } else if (first === null && second === null) verdict = '<span class="nm">neither ran it</span>';
      else if (first === null || second === null) verdict = `<span class="nm">only ${esc((second === null ? a : b).label)} ran it</span>`;
      else if (tied(key, a, b)) verdict = `tied (${number(first - second)})`;
      else verdict = `${esc((first > second ? a : b).label)} ahead by ${number(Math.abs(first - second))}`;
      const cell = (model, value) => {
        if (value !== null) return number(value);
        if (key === 'combined') return status('Not applicable', model.na);
        return open ? status('Not run', `No ${label} run for this model: it is not in that bench's file`)
          : status('Not applicable', `${label}: not published yet`);
      };
      return `<tr><th scope="row">${esc(label)} \u2191</th><td class="num">${cell(a, first)}</td><td class="num">${cell(b, second)}</td><td>${verdict}</td></tr>`;
    });
    document.querySelector('[data-ab-h2h]').innerHTML = rows.join('');
  }
  function fillPickers() {
    if (!pickA || !pickB) return;
    const choices = DATA.models.filter(fits);
    const order = [...choices].sort((first, second) =>
      (score(second, DATA.default) ?? -Infinity) - (score(first, DATA.default) ?? -Infinity) || first.label.localeCompare(second.label));
    const keep = (wanted, other) => (choices.some(model => model.key === wanted) ? wanted : order.find(model => model.key !== other)?.key);
    const a = keep(state.a || pickA.value, null);
    const b = keep(state.b || pickB.value, a);
    const options = chosen => Object.entries(DATA.kinds).map(([kind, label]) => {
      const group = choices.filter(model => model.kind === kind).sort((first, second) => first.label.toLowerCase().localeCompare(second.label.toLowerCase()));
      return group.length ? `<optgroup label="${esc(label)}">${group.map(model =>
        `<option value="${esc(model.key)}"${model.key === chosen ? ' selected' : ''}>${esc(model.label)}</option>`).join('')}</optgroup>` : '';
    }).join('');
    pickA.innerHTML = options(a);
    pickB.innerHTML = options(b);
    if (state.a && state.a !== a) state.a = null;
    if (state.b && state.b !== b) state.b = null;
    headToHead();
  }
  pickers.forEach(select => select.addEventListener('change', () => {
    state[select.dataset.abPick] = select.value;
    headToHead();
    save();
  }));
  state.a = models.has(params.get('a')) ? params.get('a') : null;
  state.b = models.has(params.get('b')) ? params.get('b') : null;

  /* The keys and the table's heads. */
  function apply() {
    $$('[data-ab-type]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.abType === state.type)));
    $$('[data-ab-class]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.abClass === state.class)));
    $$('[data-ab-view]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.abView === state.view)));
    $$('.ab-view[data-view]').forEach(part => { part.hidden = part.dataset.view !== state.view; });
    drawBars();
    drawTable();
    drawResults();
    drawCharts();
    fillPickers();
    save();
  }
  document.addEventListener('click', event => {
    const key = event.target.closest('button');
    if (!key) return;
    if (key.dataset.abType) state.type = key.dataset.abType !== state.type ? key.dataset.abType : 'all';
    else if (key.dataset.abClass) state.class = key.dataset.abClass !== state.class ? key.dataset.abClass : 'all';
    else if (key.dataset.abView) {
      state.view = key.dataset.abView;
      state.sort = null;
      state.reversed = false;
    } else if (key.dataset.abSort) {
      const column = key.dataset.abSort;
      if (column === (state.sort || state.view)) state.reversed = !state.reversed;
      else {
        state.reversed = false;
        if (views.includes(column)) {
          state.view = column;
          state.sort = null;
        } else state.sort = column;
      }
    } else return;
    apply();
  });

  /* One tab per bench. */
  const tabs = $$('[data-ab-tab]');
  function showTab(key) {
    if (!tabs.some(tab => tab.dataset.abTab === key)) key = tabs[0]?.dataset.abTab;
    tabs.forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.abTab === key)));
    $$('[data-ab-panel]').forEach(panel => { panel.hidden = panel.dataset.abPanel !== key; });
    state.tab = key === tabs[0]?.dataset.abTab ? null : key;
  }
  tabs.forEach(tab => tab.addEventListener('click', () => { showTab(tab.dataset.abTab); save(); }));

  showTab(params.get('tab'));
  apply();
})();
