'use strict';

/* Accuracy 0–100 → red (#fee2e2), amber (#fef3c7) at 50, green (#bbf7d0); the local dashboard's scale. */
function heatColor(accuracy) {
  const p = Math.min(100, Math.max(0, accuracy)) / 100;
  const [from, to, t] = p <= 0.5
    ? [[254, 226, 226], [254, 243, 199], p / 0.5]
    : [[254, 243, 199], [187, 247, 208], (p - 0.5) / 0.5];
  const [r, g, b] = from.map((start, i) => Math.round(start + (to[i] - start) * t));
  return `rgb(${r}, ${g}, ${b})`;
}

const integer = n => n.toLocaleString('en-US');
const percent = (correct, total) => (total ? (100 * correct) / total : null);
const formatPercent = (value, digits = 2) => (value == null ? '—' : `${value.toFixed(digits)}%`);
const EXCLUSIONS = {
  unanswered: 'with no answer in the key',
  incomplete: 'incomplete',
  malformed_choices: 'with malformed options',
};

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'style') node.style.cssText = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter(child => child != null));
  return node;
}

/* A cell; numeric cells carry their sort value in data-value ('' when missing). */
function td(content, { value, numeric = false, className = null, title = null, style = null } = {}) {
  const classes = [numeric ? 'num' : null, className].filter(Boolean).join(' ') || null;
  const cell = el('td', { class: classes, title, style }, ...[].concat(content));
  if (value !== undefined) cell.dataset.value = value ?? '';
  return cell;
}

/* Click or press Enter on a heading to sort; numbers sort high to low first, missing values last. */
function makeSortable(table) {
  const headers = [...table.tHead.rows[0].cells];
  const body = table.tBodies[0];
  headers.forEach((th, index) => {
    const sort = () => {
      const numeric = th.classList.contains('num');
      const current = th.getAttribute('aria-sort');
      const descending = current ? current === 'ascending' : numeric;
      headers.forEach(header => header.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', descending ? 'descending' : 'ascending');
      const key = row => {
        const cell = row.cells[index];
        const raw = cell.dataset.value ?? cell.textContent.trim();
        return numeric ? (raw === '' ? null : Number(raw)) : raw;
      };
      const rows = [...body.rows].sort((a, b) => {
        const x = key(a);
        const y = key(b);
        if (x == null || y == null) return (x == null) - (y == null);
        const order = numeric ? x - y : String(x).localeCompare(String(y), 'tr', { numeric: true });
        return descending ? -order : order;
      });
      body.append(...rows);
    };
    th.tabIndex = 0;
    th.addEventListener('click', sort);
    th.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        sort();
      }
    });
  });
}

/* columns: [{ label, numeric, title, className }]; header labels may be strings or node arrays. */
function fillTable(table, columns, rows, footer = null) {
  const head = el('tr');
  for (const column of columns) {
    const classes = [column.numeric ? 'num' : null, column.className].filter(Boolean).join(' ') || null;
    head.append(el('th', { scope: 'col', class: classes, title: column.title }, ...[].concat(column.label)));
  }
  table.replaceChildren(el('thead', {}, head), el('tbody', {}, ...rows));
  if (footer) table.append(el('tfoot', {}, footer));
  makeSortable(table);
}

const reasoningLabel = reasoning => (reasoning === 'off' ? 'reasoning off' : `${reasoning} reasoning`);

function runLabel(run) {
  return run.variant ?? (run.reasoning ? reasoningLabel(run.reasoning) : 'option scoring');
}

/* withSetting: also name the reasoning setting, for tables without a Reasoning column. */
function modelCell(run, { withSetting = false } = {}) {
  const setting = run.variant ?? (withSetting && run.reasoning ? reasoningLabel(run.reasoning) : null);
  return td(
    [
      el('span', { class: 'model-name', text: run.name }),
      setting ? el('span', { class: 'muted', text: ` · ${setting}` }) : null,
      el('code', { class: 'small', text: run.model }),
      run.note ? el('span', { class: 'small', text: run.note }) : null,
    ],
    { value: `${run.name} ${run.variant ?? ''} ${run.reasoning ?? ''}` },
  );
}

function renderLeaderboard(data) {
  const total = data.questions;
  const rows = data.runs.map(run => {
    const score = percent(run.correct, total);
    const rank = 1 + data.runs.filter(other => other.correct > run.correct).length;
    return el(
      'tr',
      {},
      td(String(rank), { value: rank, numeric: true }),
      modelCell(run),
      td(run.access),
      td(run.reasoning ?? '—', { title: run.reasoning ? null : 'Scores the supplied options; no reasoning setting' }),
      td(
        [el('span', { class: 'bar', style: `width: ${score}%` }), el('span', { class: 'value', text: formatPercent(score) })],
        { value: score, numeric: true, className: 'score' },
      ),
      td(integer(run.correct), { value: run.correct, numeric: true }),
      td(run.questions_per_minute == null ? '—' : run.questions_per_minute.toFixed(1), {
        value: run.questions_per_minute,
        numeric: true,
      }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
      td(run.cost_usd == null ? '—' : `$${run.cost_usd.toFixed(2)}`, {
        value: run.cost_usd,
        numeric: true,
        title: run.cost_basis,
      }),
    );
  });
  const table = document.getElementById('leaderboard');
  fillTable(
    table,
    [
      { label: '#', numeric: true, title: 'Rank by score' },
      { label: 'Model' },
      { label: 'Access' },
      { label: 'Reasoning', title: 'Thinking or effort setting' },
      { label: 'Score', numeric: true },
      { label: 'Correct', numeric: true },
      { label: 'Questions/min', numeric: true, title: 'Answered questions per minute of request time' },
      { label: 'Per request', numeric: true, title: 'Questions sent in one request' },
      { label: 'Cost (USD)', numeric: true, title: 'Estimate; see the cost basis below' },
    ],
    rows,
  );
  table.tHead.rows[0].cells[4].setAttribute('aria-sort', 'descending');

  const notes = new Set(
    data.runs.filter(run => run.cost_basis).map(run => `${run.name}: ${run.cost_basis}.`),
  );
  document.getElementById('cost-notes').replaceChildren(
    ...[...notes].map(text => el('li', { text })),
    el('li', { text: 'Ollama runs: no token counts, so no estimate.' }),
  );
}

function renderUnits(data) {
  const rows = data.units.map((unit, index) =>
    el(
      'tr',
      {},
      td([el('span', { text: `${unit.number}. ${unit.name}` }), el('span', { class: 'small', text: unit.english })], {
        value: String(unit.number),
      }),
      td(integer(unit.questions), { value: unit.questions, numeric: true }),
      ...data.runs.map(run => {
        const accuracy = percent(run.units[index], unit.questions);
        return td(formatPercent(accuracy, 1), {
          value: accuracy,
          className: 'heat',
          title: `${run.name}, ${runLabel(run)}: ${run.units[index]} of ${unit.questions} correct`,
          style: `background: ${heatColor(accuracy)}`,
        });
      }),
    ),
  );
  const footer = el(
    'tr',
    {},
    td('All units'),
    td(integer(data.questions), { numeric: true }),
    ...data.runs.map(run => {
      const score = percent(run.correct, data.questions);
      return td(formatPercent(score, 1), {
        className: 'heat',
        title: `${run.name}, ${runLabel(run)}: ${integer(run.correct)} of ${integer(data.questions)} correct`,
        style: `background: ${heatColor(score)}`,
      });
    }),
  );
  fillTable(
    document.getElementById('units'),
    [
      { label: 'Unit' },
      { label: 'Questions', numeric: true },
      ...data.runs.map(run => ({
        label: [run.name, el('span', { class: 'small', text: runLabel(run) })],
        numeric: true,
        className: 'run',
      })),
    ],
    rows,
    footer,
  );
}

function renderConfidence(data) {
  const runs = data.runs.filter(run => run.confidence);
  const bins = data.confidence_bins.map(([low, high]) => `${low.toFixed(2)}–${high.toFixed(2)}`);
  const rows = runs.map(run =>
    el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(run.confidence.source),
      ...run.confidence.bins.map(interval => {
        if (!interval.questions) return td('—', { value: null, className: 'heat muted' });
        const accuracy = percent(interval.correct, interval.questions);
        return td([formatPercent(accuracy, 1), el('span', { class: 'count', text: ` (${integer(interval.questions)})` })], {
          value: accuracy,
          className: 'heat',
          title: `${interval.correct} of ${interval.questions} correct`,
          style: `background: ${heatColor(accuracy)}`,
        });
      }),
    ),
  );
  fillTable(
    document.getElementById('confidence'),
    [{ label: 'Model' }, { label: 'Confidence' }, ...bins.map(label => ({ label, numeric: true }))],
    rows,
  );

  const selective = runs.map(run => {
    const { questions, correct } = run.confidence.above_mean;
    const accuracy = percent(correct, questions);
    const blankScore = percent(correct, data.questions);
    const fullScore = percent(run.correct, data.questions);
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(run.confidence.mean.toFixed(3), { value: run.confidence.mean, numeric: true }),
      td(integer(questions), { value: questions, numeric: true }),
      td(formatPercent(accuracy), { value: accuracy, numeric: true }),
      td(formatPercent(blankScore), { value: blankScore, numeric: true }),
      td(formatPercent(fullScore), { value: fullScore, numeric: true }),
    );
  });
  fillTable(
    document.getElementById('selective'),
    [
      { label: 'Model' },
      { label: 'Mean confidence', numeric: true },
      { label: 'Answered', numeric: true, title: 'Questions at or above the mean confidence' },
      { label: 'Accuracy', numeric: true, title: 'Correct share of the answered questions' },
      { label: 'Score, rest blank', numeric: true },
      { label: 'Score, all answered', numeric: true },
    ],
    selective,
  );
}

function renderSummary(data) {
  const date = new Date(data.updated).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
  document.getElementById('summary').textContent =
    `${integer(data.questions)} TYT Türkçe multiple-choice questions in ${data.units.length} units · ` +
    `${data.runs.length} runs · last run ${date}`;
  const excluded = Object.entries(data.excluded);
  const left = excluded.reduce((sum, [, count]) => sum + count, 0);
  const reasons = excluded.map(([reason, count]) => `${count} ${EXCLUSIONS[reason] ?? reason.replaceAll('_', ' ')}`);
  document.getElementById('question-count').textContent =
    `${integer(data.questions)} questions in ${data.units.length} units are used` +
    (left ? `; ${left} were left out (${reasons.join(', ')}).` : '.');
}

async function main() {
  let data;
  try {
    const response = await fetch('results.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
  } catch (error) {
    document.getElementById('summary').textContent = `Could not load results.json: ${error.message}`;
    return;
  }
  renderSummary(data);
  renderLeaderboard(data);
  renderUnits(data);
  renderConfidence(data);
}

main();
