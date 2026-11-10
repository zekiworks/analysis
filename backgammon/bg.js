'use strict';

/* Home page (brief v12 B4): All leagues first (?league=all, the default: the Risk tab's own All leagues view, one table
   of every league's setups with their League; the other tabs and the charts show the league views one under the
   other) or one league (?league=league-1), the Risk tab first
   (?tab=), the Table / Charts switch, the filters (model type, phase, reasoning, runs on, weights; the last four folded
   behind "More filters", whose key names the active ones while closed) with the setup counter and Reset, the chart
   panels (small tabs, the margin keys, "Show all", Download PNG with the league, margin, decisions, results version,
   site address and active filters, in the theme in view). The Phase filter loads that phase's tables and Risk charts
   of the league from fragments/<league>-<phase>.html. Compare page: two setups of the v1 set, paired, from
   compare.json. */

const HOME = {
  league: null,
  phase: 'all',
  filters: { kind: 'all', setting: 'all', runs: 'all', weights: 'all' },
  showAll: false,
  original: new Map(),
};
const FILTER_LABEL = { kind: 'Model type', setting: 'Reasoning', runs: 'Runs on', weights: 'Weights' };
const FOLDED = ['setting', 'runs', 'weights'];
const TOP_N = 8;

/* Old anchors of the home page open where that content lives now: the blocks that moved to the Leagues and Nackgammon
   pages in Ümit #2938 (the map the build writes into #moved-anchors: every id of those blocks, and the old home league
   block's lg- ids), then the anchors of the page that was live here before the switch (B2). The query string goes
   along (?tab=, ?league=, ?type= work on the Leagues page too). */
(function oldAnchors() {
  if (!document.body.classList.contains('home')) return;
  const BEFORE_SWITCH = {
    v3: 'leagues/', 'v3-title': 'leagues/', 'v3-l1': 'leagues/#league-1', 'v3-league1': 'leagues/#league-1',
    'v3-l2': 'leagues/#league-2', 'v3-league2': 'leagues/#league-2', 'v3-l3': 'leagues/#league-3',
    'v3-league3': 'leagues/#league-3', 'v3-anchor': 'method/#v3-anchor', 'v3-dice': 'method/#exp-dice',
    'v3-changes': 'method/#v3-changes', setup: 'leagues/#v1-setup', models: 'leagues/#v1-models',
    prompt: 'method/#v1-prompt', changes: 'method/#v1-why', 'error-rate': 'leagues/#v1-error-rate',
    results: 'leagues/#v1-results', allstar: 'leagues/#v1-allstar', 'speed-cost': 'leagues/#v1-speed-cost',
    limits: 'leagues/#v1-limits',
  };
  const map = document.getElementById('moved-anchors');
  const MOVED = Object.assign({}, BEFORE_SWITCH, map ? JSON.parse(map.textContent) : {});
  const go = () => {
    const id = decodeURIComponent(location.hash.slice(1)).replace(/-title$/, '');
    if (!id || document.getElementById(id) || !MOVED[id]) return;
    const [path, hash] = MOVED[id].split('#');
    location.replace(path + location.search + (hash ? '#' + hash : ''));
  };
  go();
  window.addEventListener('hashchange', go);
})();

function rowShown(el) {
  const f = HOME.filters;
  return el.dataset.kind === 'reference' || Object.keys(f).every(g => f[g] === 'all' || el.dataset[g] === f[g]);
}

/* Parts of the home page the filter row does not govern (bus #2718): the leaderboard is fixed (all leagues, all phases,
   every setup) and the Nackgammon section has its own Decision / Chat / All and per-model keys. */
const OWN_SCOPE = '#leaderboard, #nackgammon-paired';

function activeFilters() {
  const on = Object.keys(HOME.filters).filter(g => HOME.filters[g] !== 'all').map(g => `${FILTER_LABEL[g]}: ${HOME.filters[g]}`);
  if (HOME.phase !== 'all') on.push(`Phase: ${HOME.phase}`);
  return on;
}

/* The folded filters that are not at their default, as shown: "Phase: Race", "Reasoning: High". */
function foldedActive(box) {
  const on = [];
  const phase = box.querySelector('[data-control="phase"]');
  if (HOME.phase !== 'all') on.push(`Phase: ${phase.selectedOptions[0].textContent.trim()}`);
  FOLDED.forEach(g => {
    if (HOME.filters[g] === 'all') return;
    const key = box.querySelector(`[data-filter-${g}="${CSS.escape(HOME.filters[g])}"]`);
    on.push(`${FILTER_LABEL[g]}: ${key ? key.textContent.trim() : HOME.filters[g]}`);
  });
  return on;
}

/* The key of the fold: closed, it names the active folded filters and counts them; open, it only counts them. */
function showFold(box) {
  const toggle = box.querySelector('[data-more-filters]');
  if (!toggle) return;
  const on = foldedActive(box);
  const count = on.length ? ` (${on.length} active)` : '';
  const open = toggle.getAttribute('aria-expanded') === 'true';
  box.querySelector('[data-more-summary]').textContent =
    open ? count : on.length ? ` · ${on.join(', ')}${count}` : ' · phase, reasoning, runs on, weights';
}

/* The filters in view, for the table and page PNGs (png.js). */
window.pngView = () => ({ filters: activeFilters() });

/* Rows of a chart: the filters decide which can show; without "Show all", the first TOP_N model setups in the chart's
   order plus the reference rows. Visible rows are stacked again so no gap is left. */
function layoutChart(svg) {
  const top = Number(svg.dataset.top), h = Number(svg.dataset.rowH);
  let i = 0, models = 0, decisions = 0;
  svg.querySelectorAll('g.row, g.pt').forEach(g => {
    let show = rowShown(g);
    if (show && g.classList.contains('row') && !HOME.showAll && g.dataset.kind !== 'reference') {
      models += 1;
      show = models <= TOP_N;
    }
    g.toggleAttribute('hidden', !show);
    if (show) decisions += Number(g.dataset.n || 0);
    if (show && g.classList.contains('row')) {
      g.setAttribute('transform', `translate(0 ${top + i * h})`);
      i += 1;
    }
  });
  if (h) {
    const height = top + i * h + 6;
    const w = svg.viewBox.baseVal.width;
    svg.setAttribute('viewBox', `0 0 ${w} ${height}`);
    svg.setAttribute('height', height);
    svg.querySelectorAll('line.vfull').forEach(l => l.setAttribute('y2', top + i * h));
  }
  svg.dataset.shown = decisions;
}

/* The view a league pick shows: its own; under All leagues the All leagues view where a part has one, else every
   league's view (with its League title). */
function viewOn(v, lg) {
  if (lg !== 'all') return v.dataset.leagueView === lg;
  return v.dataset.leagueView === 'all' || (v.dataset.leagueView.startsWith('league-')
    && !v.parentElement.querySelector(':scope > [data-league-view="all"]'));
}

function applyHome() {
  const lg = HOME.league;
  document.querySelectorAll('[data-league-view]').forEach(v => v.toggleAttribute('data-off', !viewOn(v, lg)));
  document.querySelectorAll('[data-stack-title]').forEach(h => { h.hidden = lg !== 'all'; });
  document.querySelectorAll('[data-league-pick]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.leaguePick === lg)));
  // The leaderboard (a fixed global table) and the Nackgammon section (its own keys) are outside the filters' scope.
  const filtered = el => !el.closest(OWN_SCOPE);
  document.querySelectorAll('tr[data-kind], li.hbar[data-kind]').forEach(tr => { if (filtered(tr)) tr.hidden = !rowShown(tr); });
  // A chart's group heading shows while one of its rows does.
  document.querySelectorAll('li.hbar-group').forEach(h => {
    h.hidden = !h.parentElement.querySelector(`li.hbar[data-group="${h.dataset.group}"]:not([hidden])`);
  });
  document.querySelectorAll('svg.chart-svg').forEach(svg => { if (filtered(svg)) layoutChart(svg); });
  document.querySelectorAll('.phase-all').forEach(p => { p.hidden = HOME.phase === 'all'; });
  const box = document.getElementById('filters');
  if (!box) return;
  Object.keys(HOME.filters).forEach(g => box.querySelectorAll(`[data-filter-${g}]`).forEach(b =>
    b.setAttribute('aria-pressed', String(b.getAttribute(`data-filter-${g}`) === HOME.filters[g]))));
  // Quick view: the model type across every league (League stays All leagues, never the league in view).
  box.querySelectorAll('[data-quick-view]').forEach(b =>
    b.setAttribute('aria-pressed', String(lg === 'all' && HOME.filters.kind === b.dataset.quickView)));
  const count = box.querySelector('[data-setups]');
  const totals = JSON.parse(count.dataset.totals);
  // The model setups shown: the Quality rows of the leagues in view (its programs are reference rows, never counted).
  const shown = document.querySelectorAll('#panel-quality [data-league-view]:not([data-off]) tbody tr[data-kind]:not([data-kind="reference"]):not([hidden])').length;
  count.textContent = lg in totals ? `${shown.toLocaleString('en')} of ${totals[lg].toLocaleString('en')} setups` : 'Shared positions: Analysis pending';
  const idle = HOME.league === HOME.defaultLeague && HOME.phase === 'all' && Object.values(HOME.filters).every(v => v === 'all');
  const reset = box.querySelector('[data-control="reset"]');
  reset.setAttribute('aria-disabled', String(idle));
  box.querySelector('[data-reset-why]').hidden = !idle;
  showFold(box);
  const url = new URL(location.href);
  if (lg === HOME.defaultLeague) url.searchParams.delete('league'); else url.searchParams.set('league', lg);
  if (HOME.filters.kind === 'all') url.searchParams.delete('type'); else url.searchParams.set('type', HOME.filters.kind);
  history.replaceState(null, '', url);
}

async function loadPhase(phase) {
  HOME.phase = phase;
  const slots = document.querySelectorAll('.phase-slot[data-slot]');
  slots.forEach(s => { if (!HOME.original.has(s)) HOME.original.set(s, s.innerHTML); });
  if (phase === 'all') {
    slots.forEach(s => { s.innerHTML = HOME.original.get(s); });
  } else {
    const leagues = [...new Set([...slots].map(s => s.dataset.dataset))];
    await Promise.all(leagues.map(async ds => {
      const base = document.getElementById('filters')?.dataset.fragments || 'fragments/';
      const res = await fetch(`${base}${ds}-${phase}.html`);
      if (!res.ok) throw new Error(`fragments/${ds}-${phase}.html: ${res.status}`);
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      doc.querySelectorAll('.phase-slot').forEach(src => {
        document.querySelectorAll(`.phase-slot[data-dataset="${ds}"][data-slot="${src.dataset.slot}"]`).forEach(dst => { dst.innerHTML = src.innerHTML; });
      });
    }));
  }
  document.querySelectorAll('[data-chart-panel]').forEach(showChartTab);
  applyHome();
}

(function home() {
  const picks = [...document.querySelectorAll('[data-league-pick]')];
  if (!picks.length) return;
  const pressed = picks.find(b => b.getAttribute('aria-pressed') === 'true') || picks[0];
  HOME.defaultLeague = pressed.dataset.leaguePick;
  const params = new URLSearchParams(location.search);
  const wanted = params.get('league');
  HOME.league = picks.some(b => b.dataset.leaguePick === wanted) ? wanted : HOME.defaultLeague;
  // ?type=decision (or chat, program): the Model type filter.
  if (document.querySelector(`[data-filter-kind="${CSS.escape(params.get('type') || '')}"]`)) HOME.filters.kind = params.get('type');
  picks.forEach(b => b.addEventListener('click', () => {
    HOME.league = b.dataset.leaguePick;
    applyHome();
  }));
  document.querySelectorAll('[data-quick-view]').forEach(b => b.addEventListener('click', () => {
    HOME.league = 'all';
    HOME.filters.kind = b.dataset.quickView;
    applyHome();
  }));
  const box = document.getElementById('filters');
  if (box) {
    Object.keys(HOME.filters).forEach(g => box.querySelectorAll(`[data-filter-${g}]`).forEach(b => b.addEventListener('click', () => {
      HOME.filters[g] = b.getAttribute(`data-filter-${g}`);
      applyHome();
    })));
    const phase = box.querySelector('[data-control="phase"]');
    phase.addEventListener('change', () => loadPhase(phase.value).catch(error => {
      phase.value = HOME.phase;
      alert(`Could not load this phase (${error.message}).`);
    }));
    box.querySelector('[data-control="reset"]').addEventListener('click', event => {
      if (event.currentTarget.getAttribute('aria-disabled') === 'true') return;
      Object.keys(HOME.filters).forEach(g => { HOME.filters[g] = 'all'; });
      HOME.league = HOME.defaultLeague;
      phase.value = 'all';
      loadPhase('all');
    });
    // More filters: the key opens and closes the fold; Escape inside it closes it and gives the focus back to the key.
    // The fold opens by itself when a folded filter is not at its default as the page shows: the browser keeps the
    // Phase choice on back / forward and fills it in after this script ran, so the page loads that phase then.
    const toggle = box.querySelector('[data-more-filters]');
    const fold = document.getElementById(toggle.getAttribute('aria-controls'));
    const setFold = open => {
      toggle.setAttribute('aria-expanded', String(open));
      fold.hidden = !open;
      showFold(box);
    };
    toggle.addEventListener('click', () => setFold(fold.hidden));
    fold.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      setFold(false);
      toggle.focus();
    });
    window.addEventListener('pageshow', () => {
      const kept = phase.value !== HOME.phase ? loadPhase(phase.value) : Promise.resolve();
      kept.then(() => { if (foldedActive(box).length && fold.hidden) setFold(true); })
        .catch(() => { phase.value = 'all'; loadPhase('all'); });
    });
  }
  applyHome();
})();

(function tabs() {
  const tablist = document.querySelector('.board-panel .modes[role="tablist"]');
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
  const setUrl = name => {
    const url = new URL(location.href);
    if (name === buttons[0].dataset.tab) url.searchParams.delete('tab'); else url.searchParams.set('tab', name);
    url.hash = 'board';
    history.replaceState(null, '', url);
  };
  show(new URLSearchParams(location.search).get('tab'));
  tablist.addEventListener('click', event => {
    const b = event.target.closest('[data-tab]');
    if (b) setUrl(show(b.dataset.tab));
  });
  document.querySelectorAll('[data-goto-tab]').forEach(a => a.addEventListener('click', event => {
    event.preventDefault();
    setUrl(show(a.dataset.gotoTab));
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

/* Results first: the Risk and Quality tables show their summary columns; All columns adds the advanced measures
   (bg.css hides them while the board panel has no cols-all class). Nothing is removed from the page. */
(function columnSwitch() {
  const panel = document.querySelector('.board-panel');
  const key = document.querySelector('[data-cols-all]');
  if (!panel || !key) return;
  key.addEventListener('click', () => {
    const all = !panel.classList.contains('cols-all');
    panel.classList.toggle('cols-all', all);
    key.setAttribute('aria-pressed', String(all));
  });
})();

/* Chart panels: the small tabs and margin keys pick one chart; every chart has a stable anchor (#chart-<panel>). */
function showChartTab(panel) {
  const tab = panel.querySelector('[data-chart-tab][aria-pressed="true"]');
  const margin = panel.querySelector('[data-chart-margin][aria-pressed="true"]');
  panel.querySelectorAll('.chart-view').forEach(v => {
    v.hidden = (tab && v.dataset.viewChart !== tab.dataset.chartTab) || (margin && v.dataset.viewMargin !== margin.dataset.chartMargin);
  });
}

(function chartPanels() {
  document.querySelectorAll('[data-chart-panel]').forEach(panel => {
    panel.addEventListener('click', event => {
      const b = event.target.closest('button');
      if (!b) return;
      if (b.dataset.chartTab !== undefined || b.dataset.chartMargin !== undefined) {
        const attr = b.dataset.chartTab !== undefined ? 'data-chart-tab' : 'data-chart-margin';
        panel.querySelectorAll(`[${attr}]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        showChartTab(panel);
      } else if (b.dataset.showAll !== undefined) {
        HOME.showAll = !HOME.showAll;
        document.querySelectorAll('[data-show-all]').forEach(x => {
          x.setAttribute('aria-pressed', String(HOME.showAll));
          x.querySelector('[data-show-all-label]').textContent = HOME.showAll ? 'Show the first 8' : 'Show all';
        });
        applyHome();
      } else if (b.dataset.download !== undefined) {
        downloadChart(panel);
      }
    });
    showChartTab(panel);
  });
})();

/* A chart as a PNG that makes sense away from the site (B6.5): the chart in the theme in view, then in small type the
   league, the margin, the decisions behind the rows shown, the active filters, the results version and the address. */
async function downloadChart(panel) {
  const view = [...panel.querySelectorAll('[data-league-view]')].find(v => !v.hasAttribute('data-off'));
  const svg = view && [...view.querySelectorAll('.chart-view')].find(v => !v.hidden)?.querySelector('svg');
  if (!svg) return;
  const versionLine = document.querySelector('.hero .version')?.textContent.trim() || '';
  const margin = svg.dataset.margin === 'robust' ? '0.02' : '0.001';
  // Under All leagues a chart panel shows every league's chart; the button saves the first one, named by its league.
  const lg = view.dataset.leagueView;
  const league = document.querySelector(`[data-league-pick="${lg}"]`)?.textContent.trim() || '';
  const title = panel.querySelector('h2').textContent.trim() + ': ' + (panel.querySelector('[data-chart-tab][aria-pressed="true"]')?.textContent.trim() || '');
  const filters = activeFilters();
  const lines = [
    `${league} · margin ${margin} · ${Number(svg.dataset.shown || svg.dataset.decisions).toLocaleString('en')} decisions behind the rows shown`,
    `Filters: ${filters.length ? filters.join(' · ') : 'none (all setups, all phases)'}${HOME.showAll ? '' : ` · first ${TOP_N} model setups`}`,
    versionLine,
    location.origin + location.pathname,
  ];
  if (svg.dataset.note) lines.unshift(...svg.dataset.note.split(' | '));
  await savePng(panel, svg, title, lines, `backgammon-${panel.id}-${lg}-${margin}.png`);
}

/* A chart outside the league views (Close choices, stage B): one SVG, no league, margin or filters; its note, the
   results version and the address under it. */
document.querySelectorAll('[data-static-chart]').forEach(fig => {
  fig.querySelector('[data-download-static]')?.addEventListener('click', () => {
    const svg = fig.querySelector('svg.chart-svg');
    const lines = [...(svg.dataset.note ? svg.dataset.note.split(' | ') : []),
      document.querySelector('.hero .version')?.textContent.trim() || '', location.origin + location.pathname];
    savePng(fig, svg, fig.querySelector('h2, h3').textContent.trim(), lines, `backgammon-${fig.id}.png`);
  });
});

/* The SVG in the theme in view, the site title and chart title above it, the lines in small type under it. */
async function savePng(panel, svg, title, lines, filename) {
  const box = svg.viewBox.baseVal;
  const width = box.width, height = box.height;
  const clone = svg.cloneNode(true);
  const from = svg.querySelectorAll('*');
  clone.querySelectorAll('*').forEach((el, i) => {
    const st = getComputedStyle(from[i]);
    ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-family', 'font-size', 'font-weight', 'display']
      .forEach(p => el.style.setProperty(p, st.getPropertyValue(p)));
  });
  const css = getComputedStyle(document.documentElement);
  const text = css.getPropertyValue('--text').trim(), text2 = css.getPropertyValue('--text-2').trim();
  const bg = getComputedStyle(panel).backgroundColor;
  const font = getComputedStyle(document.body).fontFamily.replace(/"/g, "'");
  const site = `${document.body.dataset.siteTitle || ''} ${document.body.dataset.siteSubtitle || ''}`.trim();
  const head = site ? 46 : 28, foot = lines.length * 16 + 12;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const markup = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height + head + foot}">` +
    `<rect width="100%" height="100%" fill="${bg}"/>` +
    (site ? `<text x="10" y="19" font-family="${font}" font-size="13" font-weight="700" fill="${text}">${esc(site)}</text>` : '') +
    `<text x="10" y="${head - 9}" font-family="${font}" font-size="14" font-weight="700" fill="${text}">${esc(title)}</text>` +
    `<g transform="translate(0 ${head})">${clone.innerHTML}</g>` +
    lines.map((l, i) => `<text x="10" y="${height + head + 16 + i * 16}" font-family="${font}" font-size="11" fill="${text2}">${esc(l)}</text>`).join('') +
    '</svg>';
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }));
  try {
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error('chart could not be drawn')); img.src = url; });
    const canvas = document.createElement('canvas');
    canvas.width = 2 * width;
    canvas.height = 2 * (height + head + foot);
    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);
    ctx.drawImage(img, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } finally {
    URL.revokeObjectURL(url);
  }
}

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

/* Leagues page tabs (Can, 31 Oct 2026): link tabs, one section shown at a time, a second level inside Starting groups
   and After league moves. The URL hash picks the tabs: a tab's own target (#starting-groups, #group-workhorse,
   #league-2, #nack-knockout …) or any anchor inside a section (#league-3-notes, #cup-qf1 …) opens every tab on its
   way and scrolls to it; a section's own id opens its first sub-tab. The Hype Cup and Nackgammon knockout tabs share
   the Cups section and each shows its part of the Cup card. Without the script nothing is hidden. */
(function leagueTabs() {
  const bar = document.querySelector('[data-league-tabs]');
  if (!bar) return;
  const tabs = [...document.querySelectorAll('a.mode[role="tab"]')];
  const controls = panel => tabs.filter(t => t.getAttribute('aria-controls') === panel.id);
  const listOf = t => t.closest('[role="tablist"]');
  const show = tab => {
    const list = [...listOf(tab).querySelectorAll('a.mode[role="tab"]')];
    list.forEach(t => { t.setAttribute('aria-selected', String(t === tab)); t.tabIndex = t === tab ? 0 : -1; });
    new Set(list.map(t => document.getElementById(t.getAttribute('aria-controls'))))
      .forEach(p => { p.hidden = !controls(p).includes(tab); });
    const panel = document.getElementById(tab.getAttribute('aria-controls'));
    panel.setAttribute('aria-labelledby', tab.id);
    if (controls(panel).length > 1) {
      panel.querySelectorAll('[data-tab-part]').forEach(p => { p.hidden = p.dataset.tabPart !== tab.dataset.tab; });
    }
  };
  // The tabs that lead to an element, outermost first (panels of other tab lists, such as the leaderboard's, are
  // skipped); a tab list on the way that the element does not choose opens its first tab.
  const route = (el, scroll) => {
    const path = [];
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const own = n.getAttribute('role') === 'tabpanel' ? controls(n) : [];
      if (!own.length) continue;
      const part = el.closest('[data-tab-part]');
      path.unshift((part && n.contains(part) && own.find(t => t.dataset.tab === part.dataset.tabPart)) || own[0]);
    }
    if (!path.length) return false;
    path.forEach(show);
    const last = document.getElementById(path[path.length - 1].getAttribute('aria-controls'));
    last.querySelectorAll('[role="tablist"]').forEach(list => {
      const inner = [...list.querySelectorAll('a.mode[role="tab"]')];
      if (!inner.some(t => document.getElementById(t.getAttribute('aria-controls')).contains(el))) show(inner[0]);
    });
    if (scroll) el.scrollIntoView();
    return true;
  };
  const fromHash = scroll => {
    const id = decodeURIComponent(location.hash.slice(1));
    const el = id && document.getElementById(id);
    if (el && route(el, scroll)) return;
    route(document.getElementById(tabs[0].getAttribute('aria-controls')), false);
    // An anchor outside the tabs (the blocks moved here from the home page, #board-panel, #risk-judgement …): the tabs
    // above it just changed height, so scroll to it again.
    if (el && scroll) el.scrollIntoView();
  };
  tabs.forEach(t => t.addEventListener('click', event => {
    event.preventDefault();
    history.replaceState(null, '', '#' + t.dataset.tab);
    route(document.getElementById(t.dataset.tab), false);
    if (bar.getBoundingClientRect().top < 0) bar.scrollIntoView({ block: 'start' });
  }));
  // Arrow keys move along a tab list, Home and End to its ends.
  tabs.forEach(t => t.addEventListener('keydown', event => {
    const list = [...listOf(t).querySelectorAll('a.mode[role="tab"]')];
    const i = list.indexOf(t);
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: list.length - 1 }[event.key];
    if (j === undefined) return;
    event.preventDefault();
    const next = list[(j + list.length) % list.length];
    next.focus();
    next.click();
  }));
  window.addEventListener('hashchange', () => fromHash(true));
  fromHash(location.hash.length > 1);
})();

/* Home page: the headline table's two views (story.py): one row per model, or every setup (the All leagues risk table);
   and each row's "other settings" expander, which shows or hides the rows it names (aria-controls). */
(function headlineViews() {
  const keys = [...document.querySelectorAll('[data-headline-view]')];
  if (!keys.length) return;
  const show = view => {
    keys.forEach(k => k.setAttribute('aria-pressed', String(k.dataset.headlineView === view)));
    document.querySelectorAll('[data-headline-panel]').forEach(p => { p.hidden = p.dataset.headlinePanel !== view; });
  };
  keys.forEach(k => k.addEventListener('click', () => show(k.dataset.headlineView)));
  document.querySelectorAll('#headline-table .hl-more').forEach(b => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') !== 'true';
    b.setAttribute('aria-expanded', String(open));
    b.getAttribute('aria-controls').split(' ').forEach(id => { const r = document.getElementById(id); if (r) r.hidden = !open; });
  }));
})();

/* Home page: the leaderboard's own filter (Ümit #2907), local to the table (the page's filters never change it): a
   type row (All, Chat models, Decision models) and a Class row (Ümit #4217: All, Tiny, Small, Medium, Large,
   Efficient, Workhorse, Flagship; rows marked data-hl-class, a model without a class none), combined: a row shows when
   it is of the type and of a selected class. A class with no model of the type in view loses its key (hidden; a
   selected one goes back to All). A second click on a pressed key returns its row to All (Ümit #3923).
   ?models=chat|decision and ?class=<class> open on them; the old ?models=small-chat / small-decision (and small: Small
   chat) open on that type with Tiny and Small. A row out of the view and its other-settings rows go out of view (class
   hl-off), whatever their expander says; the programs stay in every view; the ranks are the ranks among all models;
   the class rule (Ümit #4245) stands under the keys. */
(function headlineFilter() {
  const table = document.getElementById('headline-table');
  const keys = [...document.querySelectorAll('[data-hl-filter]')];
  const classKeys = [...document.querySelectorAll('#leaderboard [data-class-key]')];
  if (!table || !keys.length) return;
  const rows = [...table.querySelectorAll('tbody tr[data-hl-type]')];
  let type = 'all', classes = new Set();
  const apply = () => {
    const inType = rows.filter(tr => tr.dataset.hlType !== 'program' && (type === 'all' || tr.dataset.hlType === type));
    const present = new Set(inType.map(tr => tr.dataset.hlClass).filter(Boolean));
    classKeys.forEach(x => { x.hidden = x.dataset.classKey !== 'all' && !present.has(x.dataset.classKey); });
    classes = new Set([...classes].filter(c => present.has(c)));
    keys.forEach(x => x.setAttribute('aria-pressed', String(x.dataset.hlFilter === type)));
    classKeys.forEach(x => x.setAttribute('aria-pressed', String(classes.size ? classes.has(x.dataset.classKey) : x.dataset.classKey === 'all')));
    rows.forEach(tr => {
      const t = tr.dataset.hlType;
      const out = (type !== 'all' && t !== type) || (classes.size > 0 && !classes.has(tr.dataset.hlClass));
      tr.classList.toggle('hl-off', t !== 'program' && out);
    });
    table.dispatchEvent(new CustomEvent('hl-filter'));
  };
  keys.forEach(k => k.addEventListener('click', () => {
    const t = k.dataset.hlFilter;
    type = t !== 'all' && t === type ? 'all' : t;
    apply();
  }));
  classKeys.forEach(k => k.addEventListener('click', () => {
    const c = k.dataset.classKey;
    classes = c === 'all' || k.getAttribute('aria-pressed') === 'true' ? new Set() : new Set([c]);
    apply();
  }));
  const q = new URLSearchParams(location.search);
  const asked = q.get('models') === 'small' ? 'small-chat' : q.get('models');
  const small = asked && asked.startsWith('small-');
  const t = small ? asked.slice(6) : asked;
  if (keys.some(k => k.dataset.hlFilter === t)) type = t;
  if (small) classes = new Set(['tiny', 'small']);
  if (classKeys.some(k => k.dataset.classKey === q.get('class') && q.get('class') !== 'all')) classes = new Set([q.get('class')]);
  apply();
})();

/* Home page: a leaderboard row's details box (Ümit #2904, as Clocktower Bench's). A tap on a phone opens it and a
   second tap on the row, a tap outside it or Escape closes it; with a mouse it shows while the pointer is on the row or
   its box (150 ms of grace after leaving both, so the pointer can cross a corner into the box; another row takes over at
   once); with the keyboard while the focus is in the row (the model's name, then the box's links). Where the window has
   room the box stands beside its row, right of the score column (else right of the name column), from the row's top
   (from its bottom upwards near the window's foot): it never covers another row's name, so the row under the pointer
   on a name is the row whose box shows (HoverCheck, Zeki #3146). On a phone it goes under the row (above it near the
   bottom of the window). Within the window's width; capped where it does not fit. Without JavaScript every box is
   shown in its row. The same boxes on the "Did they improve?" results table (Ümit via Zeki #3803). */
(function headlineDetails() {
  const table = document.getElementById('headline-table') || document.getElementById('improve-results-table');
  if (!table) return;
  let open = null, pinned = false, pointer = 'mouse', quiet = false;
  const boxOf = tr => document.getElementById(tr.dataset.box);
  const place = () => {
    if (!open) return;
    const box = boxOf(open), row = open.getBoundingClientRect(), cell = open.querySelector('.model').getBoundingClientRect();
    const score = open.cells[2].getBoundingClientRect();
    const vw = document.documentElement.clientWidth;  // the visible width, even where something overflows the page
    const width = Math.min(380, vw - 16);
    box.style.width = `${width}px`;
    box.style.maxHeight = '';
    let height = box.offsetHeight;
    const header = document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0;
    const bottom = innerHeight - 8;
    const side = vw - 8 - score.right >= width ? score.right : vw - 8 - cell.right >= width ? cell.right : null;
    if (side !== null) {
      // Beside the row: from its top, else ending at its bottom; where neither fits, within the window as near the
      // row as it goes, capped to the window under the header (scrolling inside).
      box.style.left = `${side}px`;
      const top = header + 4;
      if (height > bottom - top) { height = Math.max(bottom - top, 80); box.style.maxHeight = `${height}px`; }
      box.style.top = `${row.top >= top && row.top + height <= bottom ? row.top
        : row.bottom - height >= top && row.bottom <= bottom ? row.bottom - height
        : Math.min(Math.max(row.top, top), bottom - height)}px`;
      return;
    }
    box.style.left = `${Math.max(8, Math.min(cell.left, vw - width - 8))}px`;
    // Height: below the row if it fits, else above it. If it fits neither way, capped to the larger side of the row,
    // scrolling inside (its links stay reachable by scrolling it or with Tab), so the row itself stays uncovered for a
    // second tap; only where neither side has 120 px does it take the window under the header.
    const below = row.bottom;  // no gap: the pointer moves from the row into its box without leaving the row
    const roomBelow = bottom - below, roomAbove = row.top - header - 4;
    if (height <= roomBelow) box.style.top = `${below}px`;
    else if (height <= roomAbove) box.style.top = `${row.top - height}px`;
    else if (Math.max(roomBelow, roomAbove) >= 120) {
      box.style.maxHeight = `${Math.max(roomBelow, roomAbove)}px`;
      box.style.top = `${roomBelow >= roomAbove ? below : row.top - roomAbove}px`;
    } else {
      const room = Math.max(bottom - header - 4, 80);
      box.style.maxHeight = `${room}px`;
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
  const rows = [...table.querySelectorAll('tbody tr[data-box]')];
  // Keyboard focus in the open row (its name or its box) keeps the box: the pointer leaving the row or entering another
  // row does not take it away until the focus leaves the row, Escape, a second tap or a click outside. Focus that a
  // press of the pointer gives (pointing) neither opens a box nor holds one: the press itself decides.
  let pointing = false, keyed = false;
  const held = () => !!open && keyed && open.contains(document.activeElement);
  document.addEventListener('pointerdown', event => {
    pointing = true;
    if (table.contains(event.target)) pointer = event.pointerType || 'mouse';
  }, true);
  const released = () => setTimeout(() => { pointing = false; });
  document.addEventListener('pointerup', released, true);
  document.addEventListener('pointercancel', released, true);
  // The pointer leaving the row and its box (the box is inside the row) closes it after a 150 ms grace; entering the row
  // or its box again keeps it, entering another row shows that row's box at once.
  let leaving = 0;
  const stay = () => { clearTimeout(leaving); leaving = 0; };
  rows.forEach(tr => {
    tr.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'mouse') return;
      stay();
      if (!pinned && !held()) show(tr, false);
    });
    tr.addEventListener('pointerleave', event => {
      if (event.pointerType !== 'mouse' || pinned || open !== tr || held()) return;
      stay();
      leaving = setTimeout(() => { leaving = 0; if (open === tr && !pinned && !held()) hide(); }, 150);
    });
    tr.addEventListener('focusin', () => {
      keyed = !pointing;
      if (keyed && open !== tr && !quiet) show(tr, false);
    });
    tr.addEventListener('focusout', event => { if (open === tr && !pinned && !tr.contains(event.relatedTarget)) hide(); });
    tr.addEventListener('click', event => {
      // A mouse click or a key (detail 0) follows the link; a link or key in the box or the expander does its own job.
      if (pointer === 'mouse' || event.detail === 0 || boxOf(tr).contains(event.target) || event.target.closest('.hl-more')) return;
      event.preventDefault();  // a tap opens the box (tables.js leaves a prevented click alone); its link opens the decisions
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
  table.addEventListener('hl-filter', () => { if (open && open.classList.contains('hl-off')) hide(); });
})();

/* Home page: the Nackgammon summary table's keys (nack_section.py; Ümit #2647, #2651): Decision / Chat / All by model
   type, and One setting per model / All settings. Programs (the yardsticks) are always shown; the notes and every
   table below the summary keep every setup. */
(function nackViews() {
  const sec = document.getElementById('nackgammon-paired');
  const table = sec && sec.querySelector('#nack-summary');
  if (!table) return;
  const kinds = JSON.parse(sec.dataset.nackKinds);
  const chosen = new Set(JSON.parse(sec.dataset.nackChosen));
  const state = { kind: 'all', view: 'model' };
  const apply = () => {
    sec.querySelectorAll('[data-nack-kind-pick]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.nackKindPick === state.kind)));
    sec.querySelectorAll('[data-nack-view]').forEach(k => k.setAttribute('aria-pressed', String(k.dataset.nackView === state.view)));
    table.querySelectorAll('tbody tr[data-row]').forEach(tr => {
      const k = kinds[tr.dataset.row];
      tr.hidden = k !== 'program' && ((state.kind !== 'all' && k !== state.kind) || (state.view === 'model' && !chosen.has(tr.dataset.row)));
    });
  };
  sec.querySelectorAll('[data-nack-kind-pick]').forEach(k => k.addEventListener('click', () => { state.kind = k.dataset.nackKindPick; apply(); }));
  sec.querySelectorAll('[data-nack-view]').forEach(k => k.addEventListener('click', () => { state.view = k.dataset.nackView; apply(); }));
  apply();
})();
