'use strict';

/* The v3 preview's Compare page, v3/compare/?a=…&b=…: two setups' measures side by side from the site's results.json
   (two folders up), and on the same questions (the preview's ../data/picks.json) how many each got right that the other
   got wrong, the paired difference with its 95% interval and the exact McNemar test, as
   benchmark_metrics.paired_comparison computes them. */

const RESULTS_URL = '../../results.json';
const PICKS_URL = '../data/picks.json';

const esc = text =>
  String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
const pct = (fraction, digits = 1) => `${(100 * fraction).toFixed(digits)}%`;
const points = fraction => {
  const text = Math.abs(100 * fraction).toFixed(2);
  return Number(text) === 0 ? text : `${fraction > 0 ? '+' : '−'}${text}`;
};
const usd = value => {
  if (value >= 0.1 || value === 0) return `$${value.toFixed(2)}`;
  const text = value.toFixed(3);
  return text === '0.000' ? `$${value.toPrecision(2)}` : `$${text}`;
};
const duration = seconds =>
  seconds < 1 ? `${Math.round(1000 * seconds)}\u00a0ms` : `${seconds.toFixed(seconds < 10 ? 2 : 1)}\u00a0s`;
const NOT_MEASURED = '<span class="hint" tabindex="0" data-tip="Not measured">—</span>';
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

const reasoningLabel = reasoning => (['off', 'on'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
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

/* Each row: label, then the value for one run as HTML. */
const MEASURES = [
  ['Accuracy', run => `${pct(share(total(run)))}<span class="small">${wilson(total(run).correct, total(run).questions).map(v => pct(v)).join(' to ')}</span>`],
  ['Reading', run => pct(share(run.groups.reading))],
  ['Grammar', run => pct(share(run.groups.grammar))],
  ['Median latency per request', run => (run.latency ? duration(run.latency.median_request_seconds) : NOT_MEASURED)],
  ['$ per 1,000 questions', run => (costPer1000(run) == null ? NOT_MEASURED : usd(costPer1000(run)))],
  ['Kept at 99% (wrong)', run => `${run.confidence.sure.questions.toLocaleString('en-US')} (${run.confidence.sure.questions - run.confidence.sure.correct})`],
  ['Calibration gap', run => `${(100 * run.confidence.ece).toFixed(1)} points`],
  ['AUROC reading', run => run.confidence.parts.meaning.auroc.toFixed(2)],
  ['AUROC grammar', run => run.confidence.parts.form.auroc.toFixed(2)],
  ['Comparison group', run => esc(run.group)],
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
  const head = run =>
    `<th scope="col" class="num"><a href="../models/${run.run}/">${esc(run.name)}</a><span class="small">${esc(detail(run))}</span></th>`;
  const measures = MEASURES.map(([label, cell]) => `<tr><th scope="row">${label}</th><td class="num">${cell(a)}</td><td class="num">${cell(b)}</td></tr>`).join('');
  const scopes = [['all', 'All questions'], ['reading', 'Reading'], ['grammar', 'Grammar']]
    .map(([scope, label]) => {
      const test = paired(rightAnswers(a.run, scope), rightAnswers(b.run, scope));
      return (
        `<tr><th scope="row">${label}</th><td class="num" data-label="Questions">${test.n.toLocaleString('en-US')}</td>` +
        `<td class="num" data-label="First right, second wrong">${test.firstOnly}</td><td class="num" data-label="Second right, first wrong">${test.secondOnly}</td>` +
        `<td class="num" data-label="Difference">${points(test.difference)} points<span class="small">${points(test.low)} to ${points(test.high)}</span></td>` +
        `<td class="num" data-label="Exact McNemar p">${pText(test.p)}</td></tr>`
      );
    })
    .join('');
  const same = a.run === b.run ? '<p class="note">Both choices are the same setup.</p>' : '';
  document.querySelector('[data-compare]').innerHTML =
    same +
    `<div class="table-wrap"><table class="compare-table"><thead><tr><th scope="col">Measure</th>${head(a)}${head(b)}</tr></thead><tbody>${measures}</tbody></table></div>` +
    '<h2>On the same questions</h2>' +
    '<p class="note">Only the questions one got right and the other wrong tell two setups apart. The exact McNemar test asks whether that split could be chance. Its p-value is for this one pair; the comparison group letters correct for testing every pair.</p>' +
    '<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Questions</th><th scope="col" class="num">Questions</th><th scope="col" class="num">First right, second wrong</th><th scope="col" class="num">Second right, first wrong</th><th scope="col" class="num">Difference, 95% interval</th><th scope="col" class="num">Exact McNemar p</th></tr></thead>' +
    `<tbody>${scopes}</tbody></table></div>`;
  document.querySelector('[data-compare-status]')?.remove();
  document.querySelector('[data-compare]').hidden = false;
  document.title = `${a.name} against ${b.name} · Zeki Works`;
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
}

start();
