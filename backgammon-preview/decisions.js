'use strict';

/* Every decision: one setup's decisions, a page at a time, read on demand from decisions/<dataset>/<slug>/<page>.json.gz
   (tools/site/decisions_export.py). Deep links: ?d=<dataset>&s=<setup slug>&p=<page>#d<decision id>. */
(function everyDecision() {
  const controls = document.getElementById('dec-controls');
  const list = document.getElementById('dec-list');
  const status = document.getElementById('dec-status');
  const pagerBottom = document.getElementById('dec-pager-bottom');
  if (!controls || !list) return;

  const MINUS = '\u2212';
  const pages = new Map();
  const contexts = new Map();
  let index = null;
  let view = null;

  const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const signed = (x, digits) => (x > 0 ? '+' : x < 0 ? MINUS : '') + Math.abs(x).toFixed(digits);
  const fixed = (x, digits) => (x < 0 ? MINUS : '') + Math.abs(x).toFixed(digits);
  const count = n => n.toLocaleString('en-US');
  const nm = text => `<span class="nm">${esc(text)}</span>`;
  const plural = (n, word) => `${count(n)} ${word}${n === 1 ? '' : 's'}`;

  /* GitHub Pages serves .gz files as they are; a server that sends them with Content-Encoding: gzip hands over JSON. */
  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
      return JSON.parse(await new Response(stream).text());
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function loadPage(dataset, slug, page) {
    const url = `${encodeURIComponent(dataset)}/${encodeURIComponent(slug)}/${page}.json.gz`;
    if (!pages.has(url)) {
      pages.set(url, fetchJSON(url).catch(error => {
        pages.delete(url);
        throw error;
      }));
    }
    return pages.get(url);
  }

  function loadContext(hash) {
    if (!contexts.has(hash)) {
      contexts.set(hash, fetch(`contexts/${encodeURIComponent(hash)}.txt`).then(response => {
        if (!response.ok) throw new Error(`contexts/${hash}.txt: HTTP ${response.status}`);
        return response.text();
      }).catch(error => {
        contexts.delete(hash);
        throw error;
      }));
    }
    return contexts.get(hash);
  }

  /* The board from the mover's side: the mover at the bottom, moving 24 -> 1 (top right, along the top to the left, down,
     along the bottom to the right) and bearing off on the right. */
  const P = 32, R = 15, BAR = 30, FRAME = 8, TRAY = 40, BAND = 18, H = 150, GAP = 34;
  const LEFT = FRAME, MID = FRAME + 6 * P, RIGHT = MID + BAR, EDGE = RIGHT + 6 * P;
  const WIDTH = EDGE + FRAME + TRAY;
  const TOP = BAND + 6, BOTTOM = TOP + 2 * H + GAP;
  const HEIGHT = BOTTOM + 6 + BAND;

  function pointX(p) {
    if (p <= 6) return EDGE - (p - .5) * P;
    if (p <= 12) return MID - (p - 6.5) * P;
    if (p <= 18) return LEFT + (p - 12.5) * P;
    return RIGHT + (p - 18.5) * P;
  }

  function checkers(x, n, mine, fromTop, base) {
    const cls = mine ? 'ck-me' : 'ck-opp';
    let out = '';
    const shown = Math.min(n, 5);
    for (let k = 0; k < shown; k += 1) {
      const y = fromTop ? base + R + k * 2 * R : base - R - k * 2 * R;
      out += `<circle class="ck ${cls}" cx="${x}" cy="${y}" r="${R - 1}"/>`;
      if (k === shown - 1 && n > 5) out += `<text class="ck-count ${cls}-text" x="${x}" y="${y + 4}">${n}</text>`;
    }
    return out;
  }

  function die(x, y, value) {
    const s = 26, q = s / 4;
    const spots = { 1: [[2, 2]], 2: [[1, 1], [3, 3]], 3: [[1, 1], [2, 2], [3, 3]], 4: [[1, 1], [3, 1], [1, 3], [3, 3]],
      5: [[1, 1], [3, 1], [2, 2], [1, 3], [3, 3]], 6: [[1, 1], [3, 1], [1, 2], [3, 2], [1, 3], [3, 3]] }[value] || [];
    return `<rect class="die" x="${x}" y="${y}" width="${s}" height="${s}" rx="4"/>` +
      spots.map(([i, j]) => `<circle class="pip" cx="${x + i * q}" cy="${y + j * q}" r="2.6"/>`).join('');
  }

  function boardSVG(d) {
    const { points, bar, off } = d.board;
    let s = `<rect class="bd-frame" x="0" y="${BAND}" width="${EDGE + FRAME}" height="${BOTTOM - BAND + 6}" rx="6"/>`;
    s += `<rect class="bd-felt" x="${LEFT}" y="${TOP}" width="${6 * P}" height="${BOTTOM - TOP}"/>`;
    s += `<rect class="bd-felt" x="${RIGHT}" y="${TOP}" width="${6 * P}" height="${BOTTOM - TOP}"/>`;
    s += `<rect class="bd-tray" x="${EDGE + FRAME + 4}" y="${BAND}" width="${TRAY - 4}" height="${BOTTOM - BAND + 6}" rx="4"/>`;
    for (let p = 1; p <= 24; p += 1) {
      const x = pointX(p), top = p >= 13;
      const tip = top ? TOP + H : BOTTOM - H, base = top ? TOP : BOTTOM;
      s += `<path class="bd-point ${p % 2 ? 'bd-a' : 'bd-b'}" d="M${x - P / 2} ${base}L${x + P / 2} ${base}L${x} ${tip}Z"/>`;
      s += `<text class="bd-num" x="${x}" y="${top ? BAND - 5 : HEIGHT - 4}">${p}</text>`;
      const n = points[p - 1];
      if (n) s += checkers(x, Math.abs(n), n > 0, top, base);
    }
    const barX = MID + BAR / 2, midY = TOP + H + GAP / 2;
    if (bar[1]) s += checkers(barX, bar[1], false, false, midY - 4);
    if (bar[0]) s += checkers(barX, bar[0], true, true, midY + 4);
    const trayX = EDGE + FRAME + 4, trayW = TRAY - 4;
    for (let k = 0; k < off[1]; k += 1) s += `<rect class="ck-off ck-opp" x="${trayX + 5}" y="${TOP + 2 + k * 7}" width="${trayW - 10}" height="6" rx="1.5"/>`;
    for (let k = 0; k < off[0]; k += 1) s += `<rect class="ck-off ck-me" x="${trayX + 5}" y="${BOTTOM - 8 - k * 7}" width="${trayW - 10}" height="6" rx="1.5"/>`;
    if (off[1]) s += `<text class="bd-label" x="${trayX + trayW / 2}" y="${midY - 10}">${off[1]}</text>`;
    s += `<text class="bd-label" x="${trayX + trayW / 2}" y="${midY + 4}">off</text>`;
    if (off[0]) s += `<text class="bd-label" x="${trayX + trayW / 2}" y="${midY + 18}">${off[0]}</text>`;
    const dx = RIGHT + 3 * P;
    s += die(dx - 30, midY - 13, d.dice[0]) + die(dx + 4, midY - 13, d.dice[1]);
    s += `<text class="bd-label bd-side" x="${LEFT + 3 * P}" y="${midY + 4}">you move 24 \u2192 1</text>`;
    const label = `Board from the mover's side, the mover at the bottom: dice ${d.dice.join('-')}; ` +
      `on the bar: you ${bar[0]}, opponent ${bar[1]}; borne off: you ${off[0]}, opponent ${off[1]}; ` +
      `pip count: you ${d.pips[0]}, opponent ${d.pips[1]}.`;
    return `<svg class="bd" viewBox="0 0 ${WIDTH} ${HEIGHT}" role="img" aria-label="${esc(label)}">${s}</svg>`;
  }

  const SOURCES = {
    decision: 'decision-model probability',
    logprobs: 'letter probability',
    choice_only: 'none (the model names one play)'
  };

  function playsTable(d) {
    const choiceOnly = d.probability_source === 'choice_only';
    const rows = d.plays.map((p, k) => {
      const marks = [];
      if (k === d.chosen) marks.push(d.invalid ? '<span class="dec-tag dec-tag-random">random play (invalid answer)</span>'
        : `<span class="dec-tag dec-tag-chosen">${d.program ? 'played' : "model's choice"}</span>`);
      if (p.loss === 0 || k === d.best) marks.push('<span class="dec-tag dec-tag-best">engine\'s best</span>');
      const cls = [k === d.chosen ? 'is-chosen' : '', k === d.best ? 'is-best' : ''].filter(Boolean).join(' ');
      const prob = p.probability === null ? nm('\u2014') : `${(100 * p.probability).toFixed(1)}%`;
      return `<tr${cls ? ` class="${cls}"` : ''}><td class="dec-letter">${p.letter === null ? '' : esc(p.letter)}</td>` +
        `<td class="dec-play"><code>${esc(p.notation)}</code>${marks.length ? `<span class="dec-marks">${marks.join(' ')}</span>` : ''}</td>` +
        `<td class="num">${p.equity === null ? nm('not scored') : signed(p.equity, 3)}</td>` +
        `<td class="num">${p.loss === null ? nm('not scored') : fixed(p.loss, 3)}</td>` +
        `<td class="num">${prob}</td>` +
        `<td class="num">${p.hitting_rolls === null ? '' : p.hitting_rolls}</td>` +
        `<td class="dec-desc">${esc(p.description)}</td></tr>`;
    }).join('');
    const probNote = d.program ? 'This player is a program and gives no probabilities.'
      : choiceOnly ? 'This setup names one play and gives no probability; its recorded 1.0 is not a confidence.'
      : d.probability_source === null ? 'No probabilities were recorded for this decision.'
      : d.group_size ? 'A dash: the play was not in the request that decided.' : '';
    const groupNote = !d.group_size || d.program ? ''
      : d.prompt && d.prompt.format === 'letters'
        ? ` The plays were sent in groups of ${count(d.group_size)}, each lettered from A in its own request, and the group winners were then compared in a further request.`
        : ` The plays were sent in groups of ${count(d.group_size)}, and the group winners were then compared in a further request.`;
    return `<p class="swipe-hint">Swipe for more columns \u2192</p>
<div class="table-frame"><div class="table-wrap dec-plays-wrap"><table class="dec-plays">
<caption>${plural(d.plays.length, 'legal play')}, in the order shown to the ${d.program ? 'player' : 'model'}</caption>
<thead><tr><th scope="col">Letter</th><th scope="col">Play</th><th scope="col" class="num">Engine equity</th>
<th scope="col" class="num">Equity lost</th><th scope="col" class="num">Model probability</th>
<th scope="col" class="num">Opponent hits (of 36)</th><th scope="col">Consequences, as shown</th></tr></thead>
<tbody>${rows}</tbody></table></div></div>
<p class="table-note">Engine equity: GNUbg 2-ply, cubeless, for the side to move. Equity lost: the best play's equity minus this play's.${groupNote}${probNote ? ` ${probNote}` : ''}</p>`;
  }

  function pre(text, extra) {
    return `<pre class="dec-pre${extra ? ` ${extra}` : ''}">${esc(text)}</pre>`;
  }

  function promptView(d) {
    if (d.program) return '<p class="note">This player is a program; it gets no prompt.</p>';
    const prompt = d.prompt;
    if (!prompt) return `<p class="note">${nm('Not recorded')} The prompt of this decision is not in the prompt store yet.</p>`;
    const format = prompt.format === 'letters'
      ? 'Chat request: a system prompt and one user message with lettered options.'
      : 'Decision request: the state text and the options as a list of choices.';
    let s = `<p class="small">${format}</p>`;
    if (prompt.context) {
      s += `<details class="dec-context" data-hash="${esc(prompt.context)}"><summary>Rules text shared by every prompt ` +
        `(shown above the turn text)</summary>${pre('Loading\u2026')}</details>`;
    }
    const n = prompt.requests.length;
    prompt.requests.forEach((r, i) => {
      if (n > 1) s += `<h4 class="dec-request">Request ${i + 1} of ${n}</h4>`;
      (r.system_prefix || []).forEach((block, j) => {
        s += `<details class="dec-system"><summary>System block ${j + 1}, sent before the system prompt</summary>${pre(block)}</details>`;
      });
      if (r.system) s += `<details class="dec-system"><summary>System prompt</summary>${pre(r.system)}</details>`;
      s += `<p class="dec-label">${prompt.format === 'letters' ? 'User message, after the rules text' : 'State, after the rules text'}</p>`;
      s += pre(r.text, 'dec-text');
      if (r.instructions) s += `<p class="dec-label">Instructions</p>${pre(r.instructions)}`;
      if (r.options) {
        s += `<p class="dec-label">Options sent, in this order (${count(r.options.length)})</p><ol class="dec-options">` +
          r.options.map(([notation, description]) => `<li><code>${esc(notation)}</code> ${esc(description)}</li>`).join('') + '</ol>';
      }
    });
    return s;
  }

  function facts(d, dataset) {
    const rows = [];
    const add = (term, value) => rows.push(`<dt>${esc(term)}</dt><dd>${value}</dd>`);
    add('Dice', esc(d.dice.join('-')));
    add('Pip count', `you ${count(d.pips[0])}, opponent ${count(d.pips[1])}`);
    add('Phase', d.tag ? `${esc(d.phase)} \u00b7 ${esc(d.tag)}` : esc(d.phase));
    const chosen = d.chosen === null ? null : d.plays[d.chosen];
    if (d.invalid) add('Answer', 'invalid' + (chosen ? `; the runner played <code>${esc(chosen.notation)}</code> at random` : ''));
    else if (chosen) {
      add(d.program ? 'Played' : "Model's choice", `${chosen.letter ? `${esc(chosen.letter)}: ` : ''}<code>${esc(chosen.notation)}</code>` +
        (chosen.loss === null ? '' : `, equity lost ${fixed(chosen.loss, 3)}`));
    }
    if (d.best !== null) add("Engine's best", `<code>${esc(d.plays[d.best].notation)}</code>`);
    if (!d.program) {
      add('Option groups', d.group_size
        ? `split into groups of ${count(d.group_size)}; the group winners were compared`
        : 'all plays in one request');
      add('Probability', d.probability_source ? esc(SOURCES[d.probability_source] || d.probability_source) : 'none recorded');
    }
    if (d.request_seconds !== null) add('Request time', `${d.request_seconds.toFixed(1)} s`);
    if (d.retry_seconds) add('Retry and wait time', `${d.retry_seconds.toFixed(1)} s`);
    if (d.cost_usd !== null && d.cost_usd !== undefined) add('Cost', `$${d.cost_usd.toFixed(4)}`);
    add('Version', esc(dataset.version));
    return `<dl class="facts dec-facts">${rows.join('')}</dl>`;
  }

  function card(d, dataset) {
    const where = d.league === null
      ? `${esc(dataset.label)} \u00b7 position ${esc(d.id)} \u00b7 turn ${d.turn_no}`
      : `${esc(dataset.label)} \u00b7 game ${d.game} \u00b7 turn ${d.turn_no}`;
    const link = `${linkFor(view)}#d${encodeURIComponent(d.id)}`;
    const flag = d.invalid
      ? `<p class="dec-flag">${d.chosen === null ? "Invalid answer: no play was chosen; it does not count as the model's choice."
        : "Invalid answer: the runner played a random legal play; it does not count as the model's choice."}</p>` : '';
    return `<article class="card dec-card" id="d${esc(d.id)}">
<header class="dec-head"><h2><a href="${esc(link)}">Decision ${esc(d.id)}</a></h2><p class="small">${where}</p></header>
${flag}<div class="dec-top"><figure class="dec-board">${boardSVG(d)}</figure>${facts(d, dataset)}</div>
<section class="dec-legal"><h3>Legal plays</h3>${playsTable(d)}</section>
<details class="dec-seen about"><summary>Position as the model saw it</summary>${promptView(d)}</details>
</article>`;
  }

  /* State and URL. */
  function readURL() {
    const q = new URLSearchParams(location.search);
    return { d: q.get('d'), s: q.get('s'), p: Number.parseInt(q.get('p'), 10) || 1 };
  }

  function linkFor(v) {
    return `?${new URLSearchParams({ d: v.d, s: v.s, p: String(v.p) })}`;
  }

  function resolve(wanted) {
    const dataset = index.datasets.find(x => x.id === wanted.d) || index.datasets[0];
    const setups = dataset.setups;
    const setup = setups.find(x => x.slug === wanted.s) || setups.find(x => x.decisions > 0) || setups[0];
    const p = setup ? Math.min(Math.max(1, wanted.p), Math.max(1, setup.pages)) : 1;
    return { d: dataset.id, s: setup ? setup.slug : '', p, dataset, setup };
  }

  function pager(v) {
    const total = v.setup ? v.setup.pages : 0;
    if (!total) return '';
    const first = (v.p - 1) * index.page_size + 1, last = Math.min(v.p * index.page_size, v.setup.decisions);
    return `<button type="button" class="key" data-step="-1"${v.p <= 1 ? ' aria-disabled="true"' : ''}>\u2190 Previous</button>
<label class="dec-page">Page <input type="number" inputmode="numeric" min="1" max="${total}" value="${v.p}" aria-label="Page number"> of ${count(total)}</label>
<button type="button" class="key" data-step="1"${v.p >= total ? ' aria-disabled="true"' : ''}>Next \u2192</button>
<span class="in-view">decisions ${count(first)}\u2013${count(last)} of ${count(v.setup.decisions)}</span>`;
  }

  function renderControls(v) {
    const datasetOptions = index.datasets.map(x => `<option value="${esc(x.id)}"${x.id === v.d ? ' selected' : ''}>${esc(x.label)}</option>`).join('');
    const setupOptions = v.dataset.setups.map(x => `<option value="${esc(x.slug)}"${x.slug === v.s ? ' selected' : ''}>` +
      `${esc(x.name)} (${x.decisions ? plural(x.decisions, 'decision') : 'none scored yet'})</option>`).join('');
    const statusClass = v.dataset.status.split(/[ (:]/)[0].toLowerCase();
    controls.innerHTML = `<div class="filters-bar">
<label class="group"><span class="group-label">Dataset</span><select id="dec-dataset">${datasetOptions}</select></label>
<label class="group"><span class="group-label">Setup</span><select id="dec-setup">${setupOptions}</select></label>
<span class="status status-${esc(statusClass)}">${esc(v.dataset.badge)}</span></div>
${v.dataset.note ? `<p class="note dec-note">${esc(v.dataset.note)}</p>` : ''}
<nav class="dec-pager" aria-label="Pages">${pager(v)}</nav>`;
    controls.hidden = false;
    pagerBottom.innerHTML = pager(v);
    pagerBottom.hidden = !pagerBottom.innerHTML;
  }

  async function show(wanted, how) {
    const v = resolve(wanted);
    view = v;
    if (how === 'push') history.pushState(null, '', linkFor(v));
    else if (how === 'replace') history.replaceState(null, '', linkFor(v) + location.hash);
    renderControls(v);
    if (!v.setup || !v.setup.decisions) {
      list.innerHTML = '';
      status.innerHTML = `${nm('Analysis pending')} No decision of this setup has been scored yet.`;
      return;
    }
    status.textContent = 'Loading\u2026';
    list.setAttribute('aria-busy', 'true');
    try {
      const page = await loadPage(v.d, v.s, v.p);
      if (view !== v) return;
      list.innerHTML = page.decisions.map(d => card(d, v.dataset)).join('');
      const invalid = page.decisions.filter(d => d.invalid).length;
      status.textContent = `${v.setup.name}: page ${count(v.p)} of ${count(v.setup.pages)}, ` +
        `${plural(page.decisions.length, 'decision')}, ${plural(invalid, 'invalid answer')} on this page ` +
        `(${plural(v.setup.invalid, 'invalid answer')} in all ${count(v.setup.decisions)}).`;
      updateFrames();
      const target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target) target.scrollIntoView();
      else if (how === 'push') controls.scrollIntoView({ block: 'start' });
    } catch (error) {
      if (view !== v) return;
      list.innerHTML = '';
      status.innerHTML = `<span class="load-error">Could not load this page of decisions (${esc(error.message)}).</span>`;
    } finally {
      list.removeAttribute('aria-busy');
    }
  }

  /* Wide tables: the fade on the right while columns are hidden, and the swipe hint goes once the reader scrolled. */
  function updateFrames() {
    list.querySelectorAll('.table-frame').forEach(frame => {
      const wrap = frame.firstElementChild;
      frame.classList.toggle('more-right', wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 1);
    });
  }

  list.addEventListener('scroll', event => {
    const wrap = event.target;
    if (!(wrap instanceof Element) || !wrap.classList.contains('table-wrap')) return;
    const frame = wrap.parentElement;
    frame.classList.toggle('more-right', wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 1);
    if (wrap.scrollLeft > 0) frame.previousElementSibling?.classList.add('is-done');
  }, true);
  window.addEventListener('resize', updateFrames);

  list.addEventListener('toggle', event => {
    const box = event.target;
    if (!box.matches?.('details.dec-context') || !box.open || box.dataset.loaded) return;
    const out = box.querySelector('pre');
    loadContext(box.dataset.hash).then(text => {
      out.textContent = text;
      box.dataset.loaded = '1';
    }, error => {
      out.textContent = `Could not load the rules text (${error.message}).`;
    });
  }, true);

  function onPagerClick(event) {
    const button = event.target.closest('button[data-step]');
    if (!button || button.getAttribute('aria-disabled') === 'true') return;
    show({ d: view.d, s: view.s, p: view.p + Number(button.dataset.step) }, 'push');
  }

  function onPagerChange(event) {
    if (!event.target.matches('.dec-page input')) return;
    const p = Number.parseInt(event.target.value, 10);
    if (p) show({ d: view.d, s: view.s, p }, 'push');
  }

  controls.addEventListener('click', onPagerClick);
  pagerBottom.addEventListener('click', onPagerClick);
  controls.addEventListener('change', event => {
    if (event.target.id === 'dec-dataset') show({ d: event.target.value, s: null, p: 1 }, 'push');
    else if (event.target.id === 'dec-setup') show({ d: view.d, s: event.target.value, p: 1 }, 'push');
    else onPagerChange(event);
  });
  pagerBottom.addEventListener('change', onPagerChange);
  window.addEventListener('popstate', () => show(readURL(), null));

  fetchJSON('index.json').then(data => {
    index = data;
    if (!index.datasets.length) {
      status.innerHTML = nm('Analysis pending');
      return;
    }
    show(readURL(), 'replace');
  }).catch(error => {
    status.innerHTML = `<span class="load-error">Could not load the list of decisions (${esc(error.message)}).</span>`;
  });
})();
