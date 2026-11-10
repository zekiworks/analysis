'use strict';

/* The Compare page, compare/?a=…&b=…: two setups' measures side by side from results.json (one folder up), and on the
   same questions (../data/picks.json) how many each got right that the other got wrong, the paired difference with its
   95% interval and the exact McNemar test, as benchmark_metrics.paired_comparison computes them. The difference on all
   questions, its interval and what it means lead the page. compare-settings (sitebuild/compare.py) gives each run's cost
   basis and list price in the model page's words, and the upper-bound mark. */

/* The data's addresses as the page gives them, each with its content's version (Site asset in sitebuild/site.py), so a
   cached file of another build is never paired with this page. A page cached from before versioned addresses gives none
   and loads this script unversioned; it gets the plain addresses. */
const RESULTS_URL = document.getElementById('compare').dataset.results || '../results.json';
const PICKS_URL = document.getElementById('compare').dataset.picks || '../data/picks.json';
const SETTINGS = JSON.parse(document.getElementById('compare-settings')?.textContent || '{"costs":{}}');

const esc = text =>
  String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
const pct = (fraction, digits = 1) => `${(100 * fraction).toFixed(digits)}%`;
const points = fraction => {
  const text = Math.abs(100 * fraction).toFixed(2);
  return Number(text) === 0 ? text : `${fraction > 0 ? '+' : '−'}${text}`;
};
const duration = seconds => `${secondsText(seconds)}\u00a0s`;
const NOT_MEASURED = '<span class="hint" tabindex="0" data-tip="Not measured">—</span>';
/* A cost with no estimate on our own hardware whose maker lists no price reads "No list price" (site.py cost_missing). */
const costMissing = run => (run.billing === 'local' ? '<span class="nm">No list price</span>' : NOT_MEASURED);
const upperMark = run => (run.cost_upper_bound && SETTINGS.upper ? `<span class="mark">${esc(SETTINGS.upper.mark)}</span> ` : '');
const costBasis = run => {
  const item = SETTINGS.costs[run.run];
  if (!item) return NOT_MEASURED;
  const price = item.price ? `<span class="small">${esc(item.price.text)} (<a href="${esc(item.price.source)}">source</a>, ${esc(item.price.date)})</span>` : '';
  return `${esc(item.basis)}${price}`;
};
const pText = p => (p < 0.0001 ? 'below 0.0001' : p.toPrecision(2));

function wilson(correct, total, z = 1.96) {
  const share = correct / total;
  const denominator = 1 + (z * z) / total;
  const centre = (share + (z * z) / (2 * total)) / denominator;
  const margin = (z * Math.sqrt((share * (1 - share)) / total + (z * z) / (4 * total * total))) / denominator;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

/* Exact two-sided sign test on the discordant pairs (benchmark_metrics.sign_test), summed in log space. */
const logFactorial = (() => {
  const table = [0];
  return n => {
    for (let i = table.length; i <= n; i++) table[i] = table[i - 1] + Math.log(i);
    return table[n];
  };
})();
function signTest(first, second) {
  const total = first + second;
  if (!total) return 1;
  const terms = [];
  for (let i = 0; i <= Math.min(first, second); i++) {
    terms.push(logFactorial(total) - logFactorial(i) - logFactorial(total - i) - total * Math.LN2);
  }
  const top = Math.max(...terms);
  const sum = terms.reduce((acc, term) => acc + Math.exp(term - top), 0);
  return Math.min(1, 2 * Math.exp(top) * sum);
}
function paired(a, b) {
  const n = a.length;
  let firstOnly = 0;
  let secondOnly = 0;
  for (let i = 0; i < n; i++) {
    if (a[i] && !b[i]) firstOnly++;
    else if (b[i] && !a[i]) secondOnly++;
  }
  const difference = (firstOnly - secondOnly) / n;
  const error = Math.sqrt(firstOnly + secondOnly - (firstOnly - secondOnly) ** 2 / n) / n;
  return { n, firstOnly, secondOnly, difference, low: difference - 1.96 * error, high: difference + 1.96 * error, p: signTest(firstOnly, secondOnly) };
}

const reasoningLabel = reasoning => (['off', 'on', 'none'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
const detail = run =>
  [run.variant, run.reasoning && reasoningLabel(run.reasoning), `${run.questions_per_request} question${run.questions_per_request === 1 ? '' : 's'} per request`]
    .filter(Boolean)
    .join(' · ');
const costPer1000 = run => (run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / run.answered_questions);
const share = item => item.correct / item.questions;
const total = run => ({
  correct: run.groups.reading.correct + run.groups.grammar.correct,
  questions: run.groups.reading.questions + run.groups.grammar.questions,
});

/* Each row: label (or a function that writes it, as the cost's unit follows the reader's choice, site.js), then the value
   for one run as HTML. */
const MEASURES = [
  ['Accuracy', run => `${pct(share(total(run)))}<span class="small">${wilson(total(run).correct, total(run).questions).map(v => pct(v)).join(' to ')}</span>`],
  ['Reading', run => pct(share(run.groups.reading))],
  ['Grammar', run => pct(share(run.groups.grammar))],
  ['Median latency per request', run => (run.latency ? duration(run.latency.median_request_seconds) : NOT_MEASURED)],
  [() => `$ ${costLabel()} ${costSwitch()}`, run => (costPer1000(run) == null ? costMissing(run) : `${upperMark(run)}$${costNumber(costPer1000(run) * costScale())}`)],
  ['Cost basis', costBasis],
  ['Kept at 99% (wrong)', run => `${run.confidence.sure.questions.toLocaleString('en-US')} (${run.confidence.sure.questions - run.confidence.sure.correct})`],
  ['Calibration gap', run => `${(100 * run.confidence.ece).toFixed(1)} points`],
  ['AUROC reading', run => run.confidence.parts.meaning.auroc.toFixed(2)],
  ['AUROC grammar', run => run.confidence.parts.form.auroc.toFixed(2)],
];

let results;
let picks;

function rightAnswers(runId, scope) {
  const item = picks.runs.find(entry => entry.run === runId);
  const parts = new Map(picks.units.map(unit => [unit.number, unit.part]));
  return picks.questions
    .map((question, index) => ({ part: parts.get(question[1]), right: item.picks[index] === question[4] }))
    .filter(entry => scope === 'all' || entry.part === scope)
    .map(entry => entry.right);
}

/* The page's lead: the accuracy difference on all questions, the leader first, its 95% interval in the same direction,
   and one sentence on what the interval says. */
function verdict(a, b, label) {
  if (a.run === b.run) return '<div class="compare-verdict"><p>Both choices are the same setup.</p></div>';
  const test = paired(rightAnswers(a.run, 'all'), rightAnswers(b.run, 'all'));
  const ahead = test.difference >= 0;
  const [more, less] = ahead ? [a, b] : [b, a];
  const [low, high] = ahead ? [test.low, test.high] : [-test.high, -test.low];
  const n = test.n.toLocaleString('en-US');
  const head = test.firstOnly === test.secondOnly
    ? `<strong>${esc(label(a))}</strong> and <strong>${esc(label(b))}</strong> got the same number of the ${n} questions right.`
    : `<strong>${esc(label(more))}</strong> is ${Math.abs(100 * test.difference).toFixed(2)} points more accurate than <strong>${esc(label(less))}</strong> on the same ${n} questions.`;
  const meaning = low > 0
    ? `The whole interval is above zero, so ${esc(label(more))} is more accurate on this test.`
    : 'The interval includes zero, so this test cannot tell the two setups apart.';
  return `<div class="compare-verdict"><p class="verdict-head">${head}</p><p class="verdict-interval">95% interval: ${points(low)} to ${points(high)} points</p><p>${meaning}</p></div>`;
}

function render() {
  const params = new URLSearchParams(window.location.search);
  const box = document.getElementById('compare');
  const ids = ['a', 'b'].map(key => Number(params.get(key)) || Number(box.dataset[`default${key.toUpperCase()}`]));
  const [a, b] = ids.map(id => results.runs.find(run => run.run === id));
  if (!a || !b) {
    document.querySelector('[data-compare-status]').textContent = 'One of the setups in the address does not exist.';
    return;
  }
  document.querySelector('[data-pick="a"]').value = String(a.run);
  document.querySelector('[data-pick="b"]').value = String(b.run);
  /* Each setup's official name and its tag (compare-settings names, from Site.title and Site.tag; results.json keeps
     the setup names): the two always read apart. The settings go in the tooltip. */
  const named = run => SETTINGS.names[run.run];
  const label = run => (named(run).tag ? `${named(run).name} · ${named(run).tag}` : named(run).name);
  const head = run =>
    `<th scope="col" class="num" title="${esc(detail(run))}"><a href="../models/${run.run}/">${esc(named(run).name)}</a>` +
    `${named(run).tag ? ` <span class="name-tag">${esc(named(run).tag)}</span>` : ''}</th>`;
  const measures = MEASURES.map(([label, cell]) => {
    const kind = label === 'Cost basis' ? 'basis' : 'num';
    return `<tr><th scope="row">${typeof label === 'function' ? label() : label}</th><td class="${kind}">${cell(a)}</td><td class="${kind}">${cell(b)}</td></tr>`;
  }).join('');
  /* Each scope is its own row group: on a phone, a label row above the numbers (the inline label is hidden there), so no
     label sits over a number while the table scrolls. */
  const scopes = [['all', 'All questions'], ['reading', 'Reading'], ['grammar', 'Grammar']]
    .map(([scope, label]) => {
      const test = paired(rightAnswers(a.run, scope), rightAnswers(b.run, scope));
      return (
        `<tbody><tr class="label-row" aria-hidden="true"><th colspan="5">${label}</th></tr>` +
        `<tr><th scope="row">${label}</th><td class="num" data-label="Questions">${test.n.toLocaleString('en-US')}</td>` +
        `<td class="num" data-label="First right, second wrong">${test.firstOnly}</td><td class="num" data-label="Second right, first wrong">${test.secondOnly}</td>` +
        `<td class="num" data-label="Difference">${points(test.difference)} points<span class="small">${points(test.low)} to ${points(test.high)}</span></td>` +
        `<td class="num" data-label="Exact McNemar p">${pText(test.p)}</td></tr></tbody>`
      );
    })
    .join('');
  const upper = [a, b].some(run => run.cost_upper_bound) && SETTINGS.upper ? `<p class="note">${esc(SETTINGS.upper.mark)} ${esc(SETTINGS.upper.note)}</p>` : '';
  document.querySelector('[data-compare]').innerHTML =
    verdict(a, b, label) +
    `<div class="table-wrap"><table class="compare-table"><thead><tr><th scope="col">Measure</th>${head(a)}${head(b)}</tr></thead><tbody>${measures}</tbody></table></div>` +
    upper +
    '<h2>On the same questions</h2>' +
    '<p class="note">Only the questions one got right and the other wrong tell two setups apart. The exact McNemar test asks whether that split could be chance. Each p-value and interval is for this one pair, with no correction for testing many pairs.</p>' +
    '<div class="table-wrap"><table class="board list paired"><thead><tr><th scope="col">Questions</th><th scope="col" class="num">Questions</th><th scope="col" class="num">First right, second wrong</th><th scope="col" class="num">Second right, first wrong</th><th scope="col" class="num">Difference, 95% interval</th><th scope="col" class="num">Exact McNemar p</th></tr></thead>' +
    `${scopes}</table></div>`;
  document.querySelector('[data-compare-status]')?.remove();
  document.querySelector('[data-compare]').hidden = false;
  document.title = `${label(a)} against ${label(b)} · Hilde`;
}

function choose() {
  const params = new URLSearchParams(window.location.search);
  params.set('a', document.querySelector('[data-pick="a"]').value);
  params.set('b', document.querySelector('[data-pick="b"]').value);
  window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
  render();
}

async function start() {
  try {
    const [first, second] = await Promise.all([RESULTS_URL, PICKS_URL].map(url => fetch(url)));
    if (!first.ok || !second.ok) throw new Error(`${first.ok ? PICKS_URL : RESULTS_URL}: ${first.ok ? second.status : first.status}`);
    [results, picks] = await Promise.all([first.json(), second.json()]);
  } catch (error) {
    document.querySelector('[data-compare-status]').textContent = `Could not load the results (${error.message}).`;
    return;
  }
  document.querySelectorAll('[data-pick]').forEach(select => select.addEventListener('change', choose));
  render();
  document.addEventListener('costunit', render);
}

start();
