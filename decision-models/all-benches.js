'use strict';

/* All benches, /analysis/all-benches/ (sitebuild/all_benches.py). The page comes built: every view's ranking, charts and
   table are in it, the default view shown; this script switches between them (the score switch: Combined, Reading ·
   Turkish, Reading · English, Reading · Vision, Logic & Math, Backgammon) and keeps the reader's choice in the address
   (?view=, size=, a=, b=, tab=), so Back from a model's page returns to the same view; the earlier ?board=vision opens
   Reading · Vision. ?model=<name>
   (or its slug or repo) shows that model's page instead of the rest. Head to head is redrawn here from ab-data, with the
   page's one rule for "tied" (Methodology #tied): apart only by at least 100 / sqrt(n) points, n the smaller question
   count; on the combined score sqrt(sum of the three margins squared) / 3. */
(function allBenches() {
  const DATA = JSON.parse(document.getElementById('ab-data')?.textContent || 'null');
  if (!DATA) return;
  const params = new URLSearchParams(window.location.search);
  const $$ = selector => Array.from(document.querySelectorAll(selector));
  const esc = text =>
    String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const number = value => {
    const text = Math.abs(value).toFixed(1);
    return (value < 0 && Number(text) !== 0 ? '\u2212' : '') + text;
  };
  const models = new Map(DATA.models.map(model => [model.key, model]));
  const benchLabel = Object.fromEntries(DATA.benches.map(bench => [bench.key, bench.label]));
  const published = Object.fromEntries(DATA.benches.map(bench => [bench.key, bench.published]));
  const state = {};

  function save() {
    const next = new URLSearchParams();
    for (const [key, value] of Object.entries(state)) if (value !== null && value !== undefined && value !== '') next.set(key, value);
    const query = next.toString();
    history.replaceState(history.state, '', (query ? `?${query}` : window.location.pathname) + window.location.hash);
  }

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

  /* The score in view: the ranking, the charts and their score against ours follow it. */
  const views = $$('[data-ab-view]').map(key => key.dataset.abView);
  function showView(view) {
    if (!views.includes(view)) view = DATA.default;
    $$('[data-ab-view]').forEach(key => key.setAttribute('aria-pressed', String(key.dataset.abView === view)));
    $$('.ab-view[data-view]').forEach(part => { part.hidden = part.dataset.view !== view; });
    state.view = view === DATA.default ? null : view;
    applySize();
  }
  $$('[data-ab-view]').forEach(key => key.addEventListener('click', () => { showView(key.dataset.abView); save(); }));

  /* The size slider: bars up to the size chosen; models of undisclosed size only at its top (all sizes). */
  const slider = document.getElementById('ab-size');
  const steps = slider ? slider.dataset.steps.split(',').filter(Boolean).map(Number) : [];
  const out = document.querySelector('.ab-size-out');
  function applySize() {
    if (!slider) return;
    const index = Number(slider.value);
    const limit = index >= steps.length ? Infinity : steps[index];
    $$('.ab-bar').forEach(bar => {
      const size = bar.dataset.size === '' ? null : Number(bar.dataset.size);
      bar.hidden = limit !== Infinity && (size === null || size > limit);
    });
    out.textContent = limit === Infinity ? 'all sizes, with undisclosed ones' : `${limit < 1 ? `${Math.round(limit * 1000)}M` : `${limit}B`} parameters (disclosed sizes only)`;
    state.size = limit === Infinity ? null : String(limit);
  }
  if (slider) {
    const asked = Number(params.get('size'));
    if (params.has('size') && steps.includes(asked)) slider.value = String(steps.indexOf(asked));
    slider.addEventListener('input', () => { applySize(); save(); });
  }

  /* Head to head. */
  function margin(view, a, b) {
    if (view === 'combined') return Math.sqrt(DATA.combined.reduce((sum, key) => sum + margin(key, a, b) ** 2, 0)) / 3;
    return 100 / Math.sqrt(Math.min(a.scores[view][1], b.scores[view][1]));
  }
  const score = (model, view) => (view === 'combined' ? model.combined : (model.scores[view] || [null])[0]);
  function headToHead() {
    const a = models.get(document.querySelector('[data-ab-pick="a"]').value);
    const b = models.get(document.querySelector('[data-ab-pick="b"]').value);
    if (!a || !b) return;
    document.querySelector('[data-ab-name="a"]').textContent = a.name;
    document.querySelector('[data-ab-name="b"]').textContent = b.name;
    const rows = [['combined', 'Combined'], ...DATA.benches.map(bench => [bench.key, bench.label])].map(([key, label]) => {
      const first = score(a, key);
      const second = score(b, key);
      const open = key === 'combined' || published[key];
      let verdict;
      if (!open) verdict = '<span class="nm">not published yet</span>';
      else if (key === 'combined' && (a.nc || b.nc)) {
        verdict = `<span class="nm">no combined score for ${esc((a.nc ? a : b).name)}: one model did not answer every bench</span>`;
      } else if (first === null && second === null) verdict = '<span class="nm">neither ran it</span>';
      else if (first === null || second === null) verdict = `<span class="nm">only ${esc((second === null ? a : b).name)} ran it</span>`;
      else if (Math.abs(first - second) < margin(key, a, b)) verdict = `tied (${number(first - second)})`;
      else verdict = `${esc((first > second ? a : b).name)} ahead by ${number(Math.abs(first - second))}`;
      const cell = value => (value === null ? '–' : number(value));
      return `<tr><th scope="row">${esc(label)} \u2191</th><td class="num">${cell(first)}</td><td class="num">${cell(second)}</td><td>${verdict}</td></tr>`;
    });
    document.querySelector('[data-ab-h2h]').innerHTML = rows.join('');
    state.a = a.key;
    state.b = b.key;
  }
  $$('[data-ab-pick]').forEach(select => {
    const wanted = params.get(select.dataset.abPick);
    if (wanted && models.has(wanted)) select.value = wanted;
    select.addEventListener('change', () => { headToHead(); save(); });
  });
  if (params.has('a') || params.has('b')) headToHead();

  /* One tab per bench. */
  const tabs = $$('[data-ab-tab]');
  function showTab(key) {
    if (!tabs.some(tab => tab.dataset.abTab === key)) key = tabs[0]?.dataset.abTab;
    tabs.forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.abTab === key)));
    $$('[data-ab-panel]').forEach(panel => { panel.hidden = panel.dataset.abPanel !== key; });
    state.tab = key === tabs[0]?.dataset.abTab ? null : key;
  }
  tabs.forEach(tab => tab.addEventListener('click', () => { showTab(tab.dataset.abTab); save(); }));

  showView(params.get('view') || (params.get('board') === 'vision' ? 'reading-vision' : DATA.default));
  showTab(params.get('tab'));
  save();
})();
