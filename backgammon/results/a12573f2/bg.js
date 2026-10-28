'use strict';

/* Home page (brief v12 B4): one league at a time (?league=, default League 1, never merged), the Risk tab first
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

/* The anchors of the page that was live here before the switch (B2) open where that content lives now. */
(function oldAnchors() {
  if (!document.body.classList.contains('home')) return;
  const MOVED = {
    v3: 'leagues/', 'v3-title': 'leagues/', 'v3-l1': 'leagues/#league-1', 'v3-league1': 'leagues/#league-1',
    'v3-l2': 'leagues/#league-2', 'v3-league2': 'leagues/#league-2', 'v3-l3': 'leagues/#league-3',
    'v3-league3': 'leagues/#league-3', 'v3-anchor': 'method/#v3-anchor', 'v3-dice': 'method/#exp-dice',
    'v3-changes': 'method/#v3-changes', setup: 'leagues/#v1-setup', models: 'leagues/#v1-models',
    prompt: 'method/#v1-prompt', changes: 'method/#v1-why', 'error-rate': 'leagues/#v1-error-rate',
    results: 'leagues/#v1-results', allstar: 'leagues/#v1-allstar', 'speed-cost': 'leagues/#v1-speed-cost',
    limits: 'leagues/#v1-limits',
  };
  const go = () => {
    const id = decodeURIComponent(location.hash.slice(1)).replace(/-title$/, '');
    if (id && !document.getElementById(id) && MOVED[id]) location.replace(MOVED[id]);
  };
  go();
  window.addEventListener('hashchange', go);
})();

function rowShown(el) {
  const f = HOME.filters;
  return el.dataset.kind === 'reference' || Object.keys(f).every(g => f[g] === 'all' || el.dataset[g] === f[g]);
}

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

function applyHome() {
  const lg = HOME.league;
  document.querySelectorAll('[data-league-view]').forEach(v => v.toggleAttribute('data-off', v.dataset.leagueView !== lg));
  document.querySelectorAll('[data-league-pick]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.leaguePick === lg)));
  document.querySelectorAll('tr[data-kind]').forEach(tr => { tr.hidden = !rowShown(tr); });
  document.querySelectorAll('svg.chart-svg').forEach(layoutChart);
  document.querySelectorAll('.phase-all').forEach(p => { p.hidden = HOME.phase === 'all'; });
  const box = document.getElementById('filters');
  if (!box) return;
  Object.keys(HOME.filters).forEach(g => box.querySelectorAll(`[data-filter-${g}]`).forEach(b =>
    b.setAttribute('aria-pressed', String(b.getAttribute(`data-filter-${g}`) === HOME.filters[g]))));
  const count = box.querySelector('[data-setups]');
  const totals = JSON.parse(count.dataset.totals);
  const view = document.querySelector(`#panel-quality [data-league-view="${lg}"]`);
  const shown = view ? view.querySelectorAll('tbody tr[data-kind]:not([hidden])').length : 0;
  count.textContent = lg in totals ? `${shown.toLocaleString('en')} of ${totals[lg].toLocaleString('en')} setups` : 'Shared positions: Analysis pending';
  const idle = HOME.league === HOME.defaultLeague && HOME.phase === 'all' && Object.values(HOME.filters).every(v => v === 'all');
  const reset = box.querySelector('[data-control="reset"]');
  reset.setAttribute('aria-disabled', String(idle));
  box.querySelector('[data-reset-why]').hidden = !idle;
  showFold(box);
  const url = new URL(location.href);
  if (lg === HOME.defaultLeague) url.searchParams.delete('league'); else url.searchParams.set('league', lg);
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
      const res = await fetch(`fragments/${ds}-${phase}.html`);
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
  const wanted = new URLSearchParams(location.search).get('league');
  HOME.league = picks.some(b => b.dataset.leaguePick === wanted) ? wanted : HOME.defaultLeague;
  picks.forEach(b => b.addEventListener('click', () => { HOME.league = b.dataset.leaguePick; applyHome(); }));
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
  const league = document.querySelector(`[data-league-pick="${HOME.league}"]`)?.textContent.trim() || '';
  const title = panel.querySelector('h2').textContent.trim() + ': ' + (panel.querySelector('[data-chart-tab][aria-pressed="true"]')?.textContent.trim() || '');
  const filters = activeFilters();
  const lines = [
    `${league} · margin ${margin} · ${Number(svg.dataset.shown || svg.dataset.decisions).toLocaleString('en')} decisions behind the rows shown`,
    `Filters: ${filters.length ? filters.join(' · ') : 'none (all setups, all phases)'}${HOME.showAll ? '' : ` · first ${TOP_N} model setups`}`,
    versionLine,
    location.origin + location.pathname,
  ];
  if (svg.dataset.note) lines.unshift(...svg.dataset.note.split(' | '));
  await savePng(panel, svg, title, lines, `backgammon-${panel.id}-${HOME.league}-${margin}.png`);
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
