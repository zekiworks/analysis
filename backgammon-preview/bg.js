'use strict';

/* Home page: metric tabs (stable addresses ?tab=<name>#board), the Table / Charts switch on a phone, and the
   filters (model type, weights, runs on, reasoning setting), which hide setup rows in every table. The swipe hint
   goes once a wide table has been scrolled. Compare page: two setups of the v1 set, paired, from compare.json. */

(function tabs() {
  const tablist = document.querySelector('.modes[role="tablist"]');
  if (!tablist) return;
  const buttons = [...tablist.querySelectorAll('[data-tab]')];
  const show = name => {
    if (!buttons.some(b => b.dataset.tab === name)) name = buttons[0].dataset.tab;
    buttons.forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== name; });
    const board = document.getElementById('board');
    if (board) board.setAttribute('aria-labelledby', 'tab-' + name);
    return name;
  };
  const fromUrl = () => new URLSearchParams(location.search).get('tab');
  show(fromUrl());
  tablist.addEventListener('click', event => {
    const b = event.target.closest('[data-tab]');
    if (!b) return;
    const name = show(b.dataset.tab);
    const url = new URL(location.href);
    url.searchParams.set('tab', name);
    url.hash = 'board';
    history.replaceState(null, '', url);
  });
  document.querySelectorAll('[data-goto-tab]').forEach(a => a.addEventListener('click', event => {
    event.preventDefault();
    const name = show(a.dataset.gotoTab);
    const url = new URL(location.href);
    url.searchParams.set('tab', name);
    url.hash = 'board';
    history.replaceState(null, '', url);
    document.getElementById('board-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
})();

(function viewSwitch() {
  const panel = document.querySelector('.board-panel');
  const keys = document.querySelectorAll('[data-view]');
  if (!panel || !keys.length) return;
  const show = charts => {
    panel.classList.toggle('shows-charts', charts);
    keys.forEach(x => x.setAttribute('aria-pressed', String((x.dataset.view === 'charts') === charts)));
  };
  keys.forEach(k => k.addEventListener('click', () => show(k.dataset.view === 'charts')));
  if (location.hash.startsWith('#chart')) show(true);
})();

(function filters() {
  const box = document.getElementById('filters');
  if (!box) return;
  const groups = ['type', 'weights', 'runs', 'setting'];
  const state = Object.fromEntries(groups.map(g => [g, 'all']));
  const summary = box.querySelector('[data-summary]');
  const apply = () => {
    document.querySelectorAll('tr[data-type]').forEach(row => {
      row.hidden = groups.some(g => state[g] !== 'all' && row.dataset[g] !== state[g]);
    });
    const on = groups.filter(g => state[g] !== 'all').map(g => state[g]);
    summary.textContent = on.length ? on.join(' · ') : 'All setups';
    groups.forEach(g => box.querySelectorAll(`[data-filter-${g}]`).forEach(b =>
      b.setAttribute('aria-pressed', String(b.getAttribute(`data-filter-${g}`) === state[g]))));
  };
  groups.forEach(g => box.querySelectorAll(`[data-filter-${g}]`).forEach(b => b.addEventListener('click', () => {
    state[g] = b.getAttribute(`data-filter-${g}`);
    apply();
  })));
  box.querySelector('[data-control="reset"]').addEventListener('click', () => {
    groups.forEach(g => { state[g] = 'all'; });
    apply();
  });
  apply();
})();

(function swipeHints() {
  document.querySelectorAll('[data-swipe-hint]').forEach(hint => {
    const wrap = hint.nextElementSibling;
    if (!wrap) return;
    const done = () => { if (wrap.scrollLeft > 20) hint.classList.add('is-done'); };
    wrap.addEventListener('scroll', done, { passive: true });
  });
})();

(function compare() {
  const a = document.querySelector('[data-compare="a"]');
  const b = document.querySelector('[data-compare="b"]');
  const out = document.querySelector('[data-compare-out]');
  if (!a || !b || !out) return;
  const fmt = (x, d = 1) => (x >= 0 ? '+' : '\u2212') + Math.abs(x).toFixed(d);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const params = new URLSearchParams(location.search);
  if (params.get('a')) a.value = params.get('a');
  b.selectedIndex = Math.min(1, b.options.length - 1);
  if (params.get('b')) b.value = params.get('b');
  fetch('../data/v1/compare.json').then(r => r.json()).then(data => {
    const render = () => {
      const url = new URL(location.href);
      url.searchParams.set('a', a.value);
      url.searchParams.set('b', b.value);
      history.replaceState(null, '', url);
      if (a.value === b.value) { out.innerHTML = '<p>Pick two different setups.</p>'; return; }
      let p = data.pairs[a.value + '\u2192' + b.value];
      let flip = false;
      if (!p) { p = data.pairs[b.value + '\u2192' + a.value]; flip = true; }
      if (!p || !p.positions) { out.innerHTML = '<p>No positions in common.</p>'; return; }
      const s = flip ? -1 : 1;
      const [lo, hi] = flip ? [-p.hi, -p.lo] : [p.lo, p.hi];
      const word = hi < 0 ? 'lower error (interval entirely below zero)' : lo > 0 ? 'higher error (interval entirely above zero)'
        : 'no clear difference (the interval includes zero)';
      out.innerHTML = `<dl class="facts"><dt>Positions both answered validly</dt><dd>${p.positions.toLocaleString('en')}</dd>`
        + `<dt>Error difference, ${esc(b.value)} minus ${esc(a.value)}</dt><dd>${fmt(s * p.diff)} PR `
        + `<span class="small inline">95% interval ${fmt(lo)} to ${fmt(hi)}</span></dd>`
        + `<dt>Reading</dt><dd>${esc(b.value)}: ${word}</dd></dl>`;
    };
    a.addEventListener('change', render);
    b.addEventListener('change', render);
    render();
  });
})();
