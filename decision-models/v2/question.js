'use strict';

/* One question's page, v2/question/?id=…: its ID, part, topic, page, printed number, answer key and every setup's
   pick with its probability or score, from ../data/picks.json. Never the question's text: the publisher owns it. */

const PICKS_URL = '../data/picks.json';
const CORRECTION_URL = 'https://github.com/zekiworks/analysis/issues/new?template=answer-key-correction.md';

const esc = text =>
  String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
/* A stored score is floored to four decimals by the build, so 99.00% means at least 99%. The tooltip names the
   score's source (a probability, a written estimate, a vote share…). */
const scoreCell = (score, source) =>
  score == null
    ? '<span class="hint" tabindex="0" data-tip="Not measured">—</span>'
    : `<span class="hint" tabindex="0" data-tip="${esc(source)}">${(100 * score).toFixed(2)}%</span>`;

async function start() {
  const status = document.querySelector('[data-question-status]');
  const box = document.querySelector('[data-question]');
  const id = Number(new URLSearchParams(window.location.search).get('id'));
  let data;
  try {
    const response = await fetch(PICKS_URL);
    if (!response.ok) throw new Error(`${PICKS_URL}: ${response.status}`);
    data = await response.json();
  } catch (error) {
    status.textContent = `Could not load the answers (${error.message}).`;
    return;
  }
  const position = data.questions.findIndex(question => question[0] === id);
  if (position < 0) {
    status.innerHTML = `No scored question has the ID ${esc(id || '(none)')}. <a href="../questions/">Every question</a> lists them all.`;
    return;
  }
  const [, unitNumber, page, number, key] = data.questions[position];
  const unit = data.units.find(item => item.number === unitNumber);
  const rows = data.runs.map(run => ({ run, pick: run.picks[position], score: run.scores[position] }));
  const right = rows.filter(row => row.pick === key);
  const others = {};
  rows.filter(row => row.pick !== key && row.pick !== '-').forEach(row => (others[row.pick] = (others[row.pick] ?? 0) + 1));
  const [common, commonCount] = Object.entries(others).sort((a, b) => b[1] - a[1])[0] ?? [];
  const decisionRight = right.filter(row => row.run.decision).length;
  const decisionTotal = rows.filter(row => row.run.decision).length;
  document.title = `Question ${id} · Zeki Works`;
  const facts = [
    ['ID', id],
    ['Part', unit.part === 'reading' ? 'Reading' : 'Grammar'],
    ['Topic', `<a href="../topics/${unit.number}/">${esc(unit.name)}</a>`],
    ['Page in the book', page],
    ['Printed number', esc(number)],
    ['Answer key', esc(key)],
    ['Setups that picked the key', `${right.length} of ${rows.length}`],
    ['Decision models that picked the key', `${decisionRight} of ${decisionTotal}`],
    ['Most common other pick', common ? `${esc(common)}, by ${commonCount} setup${commonCount === 1 ? '' : 's'}` : 'None'],
  ];
  const table = rows
    .map(
      ({ run, pick, score }) =>
        `<tr${pick === key ? ' class="right"' : ''}><td class="model"><a class="model-name" href="../models/${run.run}/">${esc(run.name)}</a><span class="small">${esc(run.detail)}</span></td>` +
        `<td class="num" data-label="Pick">${pick === '-' ? '<span class="hint" tabindex="0" data-tip="No valid answer; counts as wrong">—</span>' : esc(pick)}${pick === key ? ' <span class="small inline">right</span>' : ''}</td>` +
        `<td class="num" data-label="Probability">${scoreCell(score, run.score)}</td></tr>`,
    )
    .join('');
  box.innerHTML =
    `<dl class="facts">${facts.map(([term, value]) => `<dt>${term}</dt><dd>${value}</dd>`).join('')}</dl>` +
    `<p>The question's text stays unpublished: the publisher owns it; its page and printed number find it in the book. Think the key is wrong? <a href="${CORRECTION_URL}">Report an answer key correction</a>.</p>` +
    '<h2>Every setup’s pick</h2>' +
    '<p class="note">Setups by accuracy on all questions. Probability: the setup’s probability or score for its own pick; the tooltip names its source.</p>' +
    `<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Setup</th><th scope="col" class="num">Pick</th><th scope="col" class="num">Probability</th></tr></thead><tbody>${table}</tbody></table></div>`;
  document.querySelector('#question h1').textContent = `Question ${id}`;
  status.remove();
  box.hidden = false;
}

start();
