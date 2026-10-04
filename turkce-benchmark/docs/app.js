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
const formatScore = value => (value == null ? '—' : value.toFixed(3));
const formatP = p => (p < 0.0001 ? '< 0.0001' : p.toFixed(4));
const formatPoints = (fraction, digits = 1) => `${fraction >= 0 ? '+' : '−'}${Math.abs(100 * fraction).toFixed(digits)}`;
const formatUsd = value => (value == null ? '—' : `$${value.toFixed(2)}`);
const scoreRange = interval => (interval ? `${interval[0].toFixed(3)}–${interval[1].toFixed(3)}` : null);
const percentRange = (interval, digits = 1) =>
  interval ? `${(100 * interval[0]).toFixed(digits)}–${(100 * interval[1]).toFixed(digits)}%` : null;
const EXCLUSIONS = {
  unanswered: 'with no answer in the key',
  incomplete: 'incomplete',
  malformed_choices: 'with malformed options',
};
const BILLING = {
  api: 'Billed per token',
  subscription: 'Subscription',
  local: 'Self-hosted',
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

/* A numeric cell showing a percentage, with an optional second line (an interval). */
function percentCell(value, { digits = 1, title = null, heat = false, detail = null } = {}) {
  return td([formatPercent(value, digits), detail ? el('span', { class: 'small', text: detail }) : null], {
    value,
    numeric: true,
    title,
    className: heat ? 'heat' : null,
    style: heat && value != null ? `background: ${heatColor(value)}` : null,
  });
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

const reasoningLabel = reasoning => (['off', 'on'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);

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
    { value: `${run.name} ${run.variant ?? ''} ${run.reasoning ?? ''}`, className: 'model' },
  );
}

function groupAccuracy(run, name) {
  const group = run.groups[name];
  return group ? percent(group.correct, group.questions) : null;
}

function renderLeaderboard(data) {
  const total = data.questions;
  const mix = `${data.tyt_mix.reading} reading and ${data.tyt_mix.grammar} grammar questions`;
  const rows = data.runs.map(run => {
    const score = percent(run.correct, total);
    const rank = 1 + data.runs.filter(other => other.correct > run.correct).length;
    const tokens = run.output_tokens == null ? null : run.output_tokens / (run.answered_questions ?? total);
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
      percentCell(groupAccuracy(run, 'reading')),
      percentCell(groupAccuracy(run, 'grammar')),
      percentCell(run.tyt_mix == null ? null : 100 * run.tyt_mix, { title: `Reading and grammar weighted like ${mix}` }),
      td(run.questions_per_minute == null ? '—' : run.questions_per_minute.toFixed(1), {
        value: run.questions_per_minute,
        numeric: true,
        title: run.concurrency > 1 ? `${run.concurrency} requests at a time` : null,
      }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
      td(tokens == null ? '—' : tokens.toFixed(1), {
        value: tokens,
        numeric: true,
        title: run.output_tokens == null ? null : `${integer(run.output_tokens)} output tokens in all`,
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
      { label: 'Reading', numeric: true, title: 'Units 1–6' },
      { label: 'Grammar', numeric: true, title: 'Units 7–20' },
      { label: 'TYT mix', numeric: true, title: `Reading and grammar weighted like the 2026 TYT paper: ${mix}` },
      { label: 'Questions/min', numeric: true, title: 'Answered questions per minute of request time' },
      { label: 'Per request', numeric: true, title: 'Questions sent in one request' },
      { label: 'Output tokens', numeric: true, title: 'Output tokens per question, thinking included' },
    ],
    rows,
  );
  table.tHead.rows[0].cells[4].setAttribute('aria-sort', 'descending');
}

function renderCost(data) {
  const rows = data.runs.map(run => {
    const minutes = run.request_seconds == null ? null : run.request_seconds / 60;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(BILLING[run.billing]),
      td(run.billing === 'api' ? formatUsd(run.billed_usd) : '—', {
        value: run.billing === 'api' ? run.billed_usd : null,
        numeric: true,
      }),
      td(formatUsd(run.api_equivalent_usd), { value: run.api_equivalent_usd, numeric: true, title: run.cost_basis }),
      td(run.hardware ?? '—'),
      td(minutes == null ? '—' : minutes.toFixed(1), { value: minutes, numeric: true }),
      td(String(run.concurrency), { value: run.concurrency, numeric: true }),
    );
  });
  fillTable(
    document.getElementById('cost'),
    [
      { label: 'Model' },
      { label: 'Paid by' },
      { label: 'Billed (USD)', numeric: true, title: 'What the API charged for the run' },
      { label: 'API-equivalent (USD)', numeric: true, title: 'The run’s tokens at a list or assumed price; see the basis below' },
      { label: 'Local GPU' },
      { label: 'Request time (min)', numeric: true },
      { label: 'Requests at a time', numeric: true },
    ],
    rows,
  );
  const notes = new Set(data.runs.filter(run => run.cost_basis).map(run => `${run.name}: ${run.cost_basis}.`));
  const unpriced = [...new Set(data.runs.filter(run => run.api_equivalent_usd == null).map(run => run.name))];
  document.getElementById('cost-notes').replaceChildren(
    ...[...notes].map(text => el('li', { text })),
    unpriced.length ? el('li', { text: `${unpriced.join(', ')}: open weights with no price to apply.` }) : null,
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
      td(run.confidence.label),
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

  const ranking = runs.map(run => {
    const { auroc, auroc_interval: aurocInterval, ece, coverage_accuracy: coverage, coverage_intervals: intervals } = run.confidence;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td([formatScore(auroc), aurocInterval ? el('span', { class: 'small', text: scoreRange(aurocInterval) }) : null], {
        value: auroc,
        numeric: true,
      }),
      td(formatScore(ece), { value: ece, numeric: true }),
      ...data.coverages.map(share => {
        const key = share.toFixed(2);
        const accuracy = coverage[key];
        return percentCell(accuracy == null ? null : 100 * accuracy, {
          heat: true,
          detail: intervals ? percentRange(intervals[key]) : null,
        });
      }),
      percentCell(percent(run.correct, data.questions), { heat: true }),
    );
  });
  fillTable(
    document.getElementById('ranking'),
    [
      { label: 'Model' },
      { label: 'AUROC', numeric: true, title: 'Chance that a right answer has a higher confidence than a wrong one' },
      { label: 'ECE', numeric: true, title: 'Expected calibration error over 10 equal-width bins; lower is better' },
      ...data.coverages.map(share => ({
        label: `Top ${Math.round(100 * share)}%`,
        numeric: true,
        title: `Accuracy on the ${Math.round(100 * share)}% of answers with the highest confidence`,
      })),
      { label: 'All', numeric: true, title: 'Accuracy on every answer' },
    ],
    ranking,
  );

  const sure = runs
    .filter(run => run.confidence.sure.questions)
    .map(run => {
      const { questions, correct, interval } = run.confidence.sure;
      return el(
        'tr',
        {},
        modelCell(run, { withSetting: true }),
        td(run.confidence.label),
        td(`${integer(correct)} of ${integer(questions)}`, { value: questions, numeric: true }),
        percentCell(percent(correct, questions)),
        percentCell(percent(questions, data.questions), { title: 'Share of all questions answered at 0.99 or more' }),
        td(percentRange(interval) ?? '—', { value: interval ? 100 * interval[0] : null, numeric: true }),
      );
    });
  fillTable(
    document.getElementById('sure'),
    [
      { label: 'Model' },
      { label: 'Confidence' },
      { label: 'Right', numeric: true, title: 'Right answers among those at 0.99 or more' },
      { label: 'Accuracy', numeric: true },
      { label: 'Share of questions', numeric: true },
      { label: '95% interval', numeric: true, title: 'Wilson score interval on the accuracy' },
    ],
    sure,
  );
}

function renderSources(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const rows = data.sources.flatMap(item =>
    item.sources.map(entry =>
      el(
        'tr',
        {},
        modelCell(byRun.get(entry.run), { withSetting: true }),
        td(entry.stated ? 'Stated with the answer' : 'Probability of the same answer'),
        td([formatScore(entry.auroc), el('span', { class: 'small', text: scoreRange(entry.auroc_interval) ?? '' })], {
          value: entry.auroc,
          numeric: true,
        }),
      ),
    ),
  );
  fillTable(
    document.getElementById('sources'),
    [
      { label: 'Confidence from' },
      { label: 'How' },
      { label: 'AUROC', numeric: true, title: 'With the 95% bootstrap interval' },
    ],
    rows,
  );
  const item = data.sources[0];
  if (item) {
    const answers = byRun.get(item.answers);
    document.getElementById('sources-answers').textContent =
      `${answers.name}'s own answers from its stated-confidence run: ${integer(item.correct)} of ` +
      `${integer(item.questions)} right.`;
  }
}

function renderVersions(data) {
  const runs = data.runs.filter(run => run.previous);
  const moved = part => `${formatPercent(percent(part.older_correct, part.questions), 1)} → ${formatPercent(percent(part.newer_correct, part.questions), 1)}`;
  const rows = runs.map(run => {
    const { changed, unchanged } = run.previous;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(moved(changed), { value: percent(changed.newer_correct - changed.older_correct, changed.questions), numeric: true }),
      td(moved(unchanged), { value: percent(unchanged.newer_correct - unchanged.older_correct, unchanged.questions), numeric: true }),
      td(`${formatPercent(percent(unchanged.changed_answer, unchanged.questions), 1)}`, {
        value: percent(unchanged.changed_answer, unchanged.questions),
        numeric: true,
        title: `${unchanged.changed_answer} of ${unchanged.questions} answers`,
      }),
      td(unchanged.newer_wrong ? `${integer(unchanged.repeated_mistakes)} of ${integer(unchanged.newer_wrong)}` : '—', {
        value: unchanged.newer_wrong ? percent(unchanged.repeated_mistakes, unchanged.newer_wrong) : null,
        numeric: true,
      }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
    );
  });
  const sample = runs[0]?.previous;
  fillTable(
    document.getElementById('versions'),
    [
      { label: 'Model' },
      { label: `Repaired (${sample ? integer(sample.changed.questions) : '—'})`, numeric: true, title: 'Accuracy on the questions whose text or key the repair changed, v1 → v2' },
      { label: `Unchanged (${sample ? integer(sample.unchanged.questions) : '—'})`, numeric: true, title: 'Accuracy on the questions asked identically, v1 → v2' },
      { label: 'Changed answer', numeric: true, title: 'Share of the unchanged questions answered with a different option' },
      { label: 'Repeated mistakes', numeric: true, title: 'Wrong v2 answers on unchanged questions that repeat the v1 choice' },
      { label: 'Per request', numeric: true, title: 'Questions sent in one request' },
    ],
    rows,
  );
}

function renderPaired(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const rows = data.paired.map(item =>
    el(
      'tr',
      {},
      modelCell(byRun.get(item.first), { withSetting: true }),
      modelCell(byRun.get(item.second), { withSetting: true }),
      td(formatPoints(item.difference), { value: 100 * item.difference, numeric: true }),
      td(`${formatPoints(item.low)} to ${formatPoints(item.high)}`, { value: 100 * item.low, numeric: true }),
      td(integer(item.first_only), { value: item.first_only, numeric: true }),
      td(integer(item.second_only), { value: item.second_only, numeric: true }),
      td(formatP(item.p), { value: item.p, numeric: true }),
      td(formatP(item.p_holm), { value: item.p_holm, numeric: true, className: item.p_holm >= 0.05 ? 'muted' : null }),
    ),
  );
  fillTable(
    document.getElementById('paired'),
    [
      { label: 'First' },
      { label: 'Second' },
      { label: 'Difference', numeric: true, title: 'Accuracy difference in percentage points' },
      { label: '95% interval', numeric: true, title: 'Paired interval on the difference' },
      { label: 'Only first right', numeric: true },
      { label: 'Only second right', numeric: true },
      { label: 'p', numeric: true, title: 'Exact McNemar test' },
      { label: 'Holm p', numeric: true, title: 'p adjusted with Holm’s method for all the comparisons in this table' },
    ],
    rows,
  );
}

function renderCascade(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const rows = data.cascades.map(item => {
    const frontier = byRun.get(item.frontier);
    return el(
      'tr',
      {},
      modelCell(byRun.get(item.decision)),
      modelCell(frontier, { withSetting: true }),
      percentCell(100 * item.frontier_accuracy),
      percentCell(100 * item.in_sample.answered, { title: `Threshold ${item.in_sample.threshold.toFixed(3)}` }),
      td(formatUsd(item.api_equivalent_usd), { value: item.api_equivalent_usd, numeric: true }),
      td(formatUsd(frontier.api_equivalent_usd), { value: frontier.api_equivalent_usd, numeric: true }),
      percentCell(100 * item.held_out.answered),
      td(formatPoints(item.held_out.difference, 2), { value: 100 * item.held_out.difference, numeric: true }),
      percentCell(100 * item.held_out.worse, { digits: 0 }),
    );
  });
  fillTable(
    document.getElementById('cascade'),
    [
      { label: 'Decision model' },
      { label: 'Frontier run' },
      { label: 'Frontier accuracy', numeric: true },
      { label: 'Answered', numeric: true, title: 'Share the decision model answers at the lowest threshold that keeps the frontier accuracy' },
      { label: 'Cost', numeric: true, title: 'API-equivalent: the decision model run plus the frontier run on the questions passed on' },
      { label: 'Frontier cost', numeric: true, title: 'API-equivalent cost of the frontier run alone' },
      { label: 'Answered, held out', numeric: true, title: 'Threshold chosen on random halves, scored on the other halves' },
      { label: 'Difference, held out', numeric: true, title: 'Mean accuracy difference from the frontier run alone, in points' },
      { label: 'Worse, held out', numeric: true, title: 'Share of the splits where the cascade scored lower' },
    ],
    rows,
  );

  const doubts = data.doubts.map(item =>
    el(
      'tr',
      {},
      modelCell(byRun.get(item.decision)),
      td(formatScore(item.rho), { value: item.rho, numeric: true }),
      td(formatP(item.p), { value: item.p, numeric: true }),
      td(formatScore(item.auroc), { value: item.auroc, numeric: true }),
      td(
        `${integer(item.top_tenth.with_mistake)} of ${integer(item.top_tenth.all_with_mistake)} (${formatPercent(percent(item.top_tenth.with_mistake, item.top_tenth.all_with_mistake), 0)})`,
        { value: percent(item.top_tenth.with_mistake, item.top_tenth.all_with_mistake), numeric: true },
      ),
    ),
  );
  fillTable(
    document.getElementById('doubts'),
    [
      { label: 'Decision model' },
      { label: 'Spearman', numeric: true, title: 'Rank correlation of the entropy with the number of frontier runs that got the question wrong' },
      { label: 'p', numeric: true, title: '200 shuffles within each unit; the smallest possible p is 1/201' },
      { label: 'AUROC', numeric: true, title: 'Chance that a question some frontier run got wrong has the higher entropy' },
      { label: 'Most uncertain tenth', numeric: true, title: 'Questions some frontier run got wrong that fall in the most uncertain 10%; chance is 10%' },
    ],
    doubts,
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
    `${integer(data.questions)} TYT Türkçe multiple-choice questions in ${data.units.length} units (question bank v2) · ` +
    `${data.runs.length} runs · last run ${date}`;
  const excluded = Object.entries(data.excluded);
  const left = excluded.reduce((sum, [, count]) => sum + count, 0);
  const reasons = excluded.map(([reason, count]) => `${count} ${EXCLUSIONS[reason] ?? reason.replaceAll('_', ' ')}`);
  document.getElementById('question-count').textContent =
    `${integer(data.questions)} questions in ${data.units.length} units are used` +
    (left ? `; ${left} were left out (${reasons.join(', ')})` : '') +
    (data.excluded_since_run ? `; ${data.excluded_since_run} more were excluded after the runs, in a key audit` : '') +
    (data.suspect ? `; ${data.suspect} of the questions used are marked suspect.` : '.');
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
  renderCost(data);
  renderUnits(data);
  renderConfidence(data);
  renderSources(data);
  renderVersions(data);
  renderPaired(data);
  renderCascade(data);
}

main();
