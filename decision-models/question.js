'use strict';

/* One question's page, question/?id=…: its ID, part, topic, page, printed number, answer key and every setup's pick
   with its probability or score, then, from the Turkish vs English tab, each compared model's answer in Turkish and in
   English, all from ../data/picks.json. Never the question's text, Turkish or English: the publisher owns it. */

const PICKS_URL = '../data/picks.json';
const TAB_URL = '../turkish-vs-english/';
const CORRECTION_URL = 'https://github.com/zekiworks/analysis/issues/new?template=answer-key-correction.md';

const esc = text =>
  String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
/* A stored score is floored to four decimals by the build, so 99.00% means at least 99%. The tooltip names the
   score's source (a probability, a written estimate, a vote share…). */
const scoreCell = (score, source) =>
  score == null
    ? '<span class="hint" tabindex="0" data-tip="Not measured">—</span>'
    : `<span class="hint" tabindex="0" data-tip="${esc(source)}">${(100 * score).toFixed(2)}%</span>`;

/* A pick with its right mark, as in Every setup's pick; "Invalid" where the run gave no valid answer. */
const pickCell = (pick, key) =>
  pick === '-'
    ? '<span class="hint" tabindex="0" data-tip="No valid answer; counts as wrong">Invalid</span>'
    : `${esc(pick)}${pick === key ? ' <span class="small inline">right</span>' : ''}`;

/* The Turkish and English panel: for a reading question kept on the Turkish vs English tab, each compared model's
   answer and its probability in Turkish (its Text tab run, among data.runs) and in English (its first English run);
   for a flagged reading question, the flag's reasons; for a grammar question, why it is not compared. */
function englishPanel(data, id, key, unit) {
  const english = data.english;
  if (!english) return '';
  const head = '<h2 id="turkish-and-english">Turkish and English</h2>';
  const tab = `<a href="${TAB_URL}">Turkish vs English</a>`;
  if (unit.part !== 'reading')
    return `${head}<p class="note">Not in the ${tab} comparison: it is a grammar question, and the comparison asks the reading questions only.</p>`;
  const position = english.questions.indexOf(id);
  if (position < 0) {
    const flag = english.flagged.find(([flagged]) => flagged === id);
    const reasons = flag ? ` (reasons: ${flag[1].map(esc).join(', ')})` : '';
    return (
      `${head}<p class="note">Not in the ${tab} comparison: the model that translated the reading questions flagged it as depending on Turkish wording${reasons}. ` +
      `Flagged questions are left out (<a href="${TAB_URL}#method">how the flags were made</a>).</p>`
    );
  }
  const turkishRuns = new Map(data.runs.map(run => [run.run, run]));
  const turkishPosition = data.questions.findIndex(question => question[0] === id);
  const rows = english.runs.map(model => {
    const turkish = turkishRuns.get(model.turkish_run);
    return {
      model,
      source: turkish.score,
      turkish: { pick: turkish.picks[turkishPosition], score: turkish.scores[turkishPosition] },
      english: { pick: model.picks[position], score: model.scores[position] },
    };
  });
  const right = side => rows.filter(row => row[side].pick === key).length;
  const table = rows
    .map(
      ({ model, source, turkish, english: answer }) =>
        `<tr><td class="model"><a class="model-name" href="../models/${model.turkish_run}/">${esc(model.name)}</a></td>` +
        `<td class="num" data-label="Turkish">${pickCell(turkish.pick, key)}</td>` +
        `<td class="num" data-label="Turkish probability">${scoreCell(turkish.score, source)}</td>` +
        `<td class="num" data-label="English">${pickCell(answer.pick, key)}</td>` +
        `<td class="num" data-label="English probability">${scoreCell(answer.score, source)}</td></tr>`,
    )
    .join('');
  return (
    head +
    `<p class="note">One of the ${english.questions.length} reading questions kept on the ${tab} tab. Each compared model’s answer in Turkish (its Text tab run) and in English (its first English run, on a model translation), with its probability or score for that answer; the tooltip names its source. Models by accuracy in English, highest first. Right in Turkish: ${right('turkish')} of ${rows.length}; in English: ${right('english')} of ${rows.length}.</p>` +
    `<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th><th scope="col" class="num">Turkish</th><th scope="col" class="num">Probability</th><th scope="col" class="num">English</th><th scope="col" class="num">Probability</th></tr></thead><tbody>${table}</tbody></table></div>`
  );
}

async function start() {
  const status = document.querySelector('[data-question-status]');
  const box = document.querySelector('[data-question]');
  status.hidden = false;
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
  document.title = `Question ${id} · Hilde`;
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
    englishPanel(data, id, key, unit) +
    '<h2>Every setup’s pick</h2>' +
    '<p class="note">Setups by accuracy on all questions. Probability: the setup’s probability or score for its own pick; the tooltip names its source.</p>' +
    `<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Setup</th><th scope="col" class="num">Pick</th><th scope="col" class="num">Probability</th></tr></thead><tbody>${table}</tbody></table></div>`;
  document.querySelector('#question h1').textContent = `Question ${id}`;
  status.remove();
  box.hidden = false;
}

start();
