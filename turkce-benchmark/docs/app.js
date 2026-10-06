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
/* A parameter count: 31.3B or 287M, with the parameters active per token for a mixture of experts; NA when the
   maker publishes no size. */
const formatBillions = count => `${(count / 1e9).toFixed(1).replace(/\.0$/, '')}`;
const formatParameters = (count, active = null) => {
  if (count == null) return 'NA';
  const size = count >= 1e9 ? `${formatBillions(count)}B` : `${Math.round(count / 1e6)}M`;
  return active ? `${size} (${active.map(formatBillions).join('–')}B active)` : size;
};
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
      // Group lines follow the score order; another order would draw them in the wrong places.
      delete table.dataset.grouped;
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
  // A group starts where a run shares no letter with the run above it.
  const sharesLetter = (first, second) => [...(first ?? '')].some(letter => (second ?? '').includes(letter));
  const rows = data.runs.map((run, index) => {
    const score = percent(run.correct, total);
    const rank = 1 + data.runs.filter(other => other.correct > run.correct).length;
    const tokens = run.output_tokens == null ? null : run.output_tokens / (run.answered_questions ?? total);
    // Every request counts, so the cost is per question asked, as the output tokens are.
    const cost = run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / (run.answered_questions ?? total);
    const auroc = run.confidence?.auroc ?? null;
    return el(
      'tr',
      { class: index > 0 && !sharesLetter(run.group, data.runs[index - 1].group) ? 'group-start' : null },
      td(String(rank), { value: rank, numeric: true }),
      modelCell(run),
      td(formatParameters(run.parameters, run.active_parameters), {
        value: run.parameters,
        numeric: true,
        title: run.parameters == null ? 'Not published by its maker' : `${integer(run.parameters)} parameters`,
      }),
      td(run.reasoning ?? '—', { title: run.reasoning ? null : 'Scores the supplied options; no reasoning setting' }),
      td(
        [el('span', { class: 'bar', style: `width: ${score}%` }), el('span', { class: 'value', text: formatPercent(score) })],
        { value: score, numeric: true, className: 'score' },
      ),
      td(run.group ?? '—', {
        className: 'group',
        title: run.group ? `Tied with every run that shares a letter (${run.group})` : null,
      }),
      percentCell(groupAccuracy(run, 'reading')),
      percentCell(groupAccuracy(run, 'grammar')),
      td(formatScore(auroc), { value: auroc, numeric: true }),
      td(tokens == null ? '—' : tokens.toFixed(1), {
        value: tokens,
        numeric: true,
        title: run.output_tokens == null ? null : `${integer(run.output_tokens)} output tokens in all`,
      }),
      td(formatUsd(cost), { value: cost, numeric: true, title: run.cost_basis }),
      percentCell(run.tyt_mix == null ? null : 100 * run.tyt_mix, { title: `Meaning and form weighted like ${mix}` }),
      td(run.questions_per_minute == null ? '—' : run.questions_per_minute.toFixed(1), {
        value: run.questions_per_minute,
        numeric: true,
        title: run.concurrency > 1 ? `${run.concurrency} requests at a time` : null,
      }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
      td(integer(run.correct), { value: run.correct, numeric: true }),
      td(run.access),
    );
  });
  const table = document.getElementById('leaderboard');
  fillTable(
    table,
    [
      { label: '#', numeric: true, title: 'Rank by score' },
      { label: 'Model' },
      {
        label: 'Parameters',
        numeric: true,
        title: 'Model weights, counted from the checkpoint or as published; NA when the maker does not publish them',
      },
      { label: 'Reasoning', title: 'Reasoning or effort setting' },
      { label: 'Score', numeric: true },
      {
        label: 'Group',
        title: `Runs that share a letter are statistically tied: no paired test of all ${integer(data.group_pairs)} pairs separates them`,
      },
      { label: 'Meaning (reading)', numeric: true, title: 'Units 1–6' },
      { label: 'Form (grammar)', numeric: true, title: 'Units 7–20' },
      {
        label: 'AUROC',
        numeric: true,
        title: 'Chance that a right answer has a higher confidence than a wrong one; empty without a confidence',
      },
      { label: 'Output tokens', numeric: true, title: 'Output tokens per question, reasoning included' },
      {
        label: 'Cost per 1,000 (USD)',
        numeric: true,
        title: 'API-equivalent cost per 1,000 questions; empty for open weights with no price',
      },
      { label: 'TYT mix', numeric: true, title: `Meaning and form weighted like the 2026 TYT paper: ${mix}` },
      { label: 'Questions/min', numeric: true, title: 'Answered questions per minute of request time' },
      { label: 'Per request', numeric: true, title: 'Questions sent in one request' },
      { label: 'Correct', numeric: true },
      { label: 'Access' },
    ],
    rows,
  );
  table.tHead.rows[0].cells[4].setAttribute('aria-sort', 'descending');
  table.dataset.grouped = '';
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

/* A unit's printed title (all capitals) in Turkish sentence case: Turkish rules map I to ı and İ to i. */
const sentenceCase = title => {
  const lower = title.toLocaleLowerCase('tr');
  return lower.charAt(0).toLocaleUpperCase('tr') + lower.slice(1);
};
// Units 1–6 test meaning (reading); units 7–20 test form (grammar).
const unitPart = number => (number <= 6 ? 'Meaning' : 'Form');

function renderUnits(data) {
  const rows = data.units.map((unit, index) =>
    el(
      'tr',
      {},
      td(
        [
          el('span', { text: `${unit.number}. ${unit.english}` }),
          el('span', { class: 'small', lang: 'tr', text: sentenceCase(unit.name) }),
        ],
        { value: String(unit.number) },
      ),
      td(unitPart(unit.number)),
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
    td(''),
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
      { label: 'Part', title: 'Meaning: units 1–6, reading. Form: units 7–20, grammar.' },
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
    document.getElementById('sure-table'),
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

const SOURCE_KINDS = {
  stated: 'Stated with the answer',
  probability: 'Probability of the same answer',
  votes: 'Share of 10 samples with the same answer',
};

/* AUROC on meaning and on form for every run with a confidence, highest on meaning first. */
function renderParts(data) {
  const runs = data.runs
    .filter(run => run.confidence?.parts?.meaning && run.confidence.parts.form)
    .sort((a, b) => b.confidence.parts.meaning.auroc - a.confidence.parts.meaning.auroc);
  const aurocCell = part =>
    td([formatScore(part.auroc), el('span', { class: 'small', text: scoreRange(part.auroc_interval) ?? '' })], {
      value: part.auroc,
      numeric: true,
    });
  const rows = runs.map(run => {
    const { meaning, form } = run.confidence.parts;
    // A run whose 95% intervals reach 0.5 on both parts is no better than chance on either, so its drop means
    // nothing. A run just above chance on one part still shows its drop.
    const noBetter = part => (part.auroc_interval ? part.auroc_interval[0] <= 0.5 : part.auroc <= 0.5);
    const chance = noBetter(meaning) && noBetter(form);
    const drop = meaning.auroc - form.auroc;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      aurocCell(meaning),
      aurocCell(form),
      td(chance ? 'no better than chance on both' : drop.toFixed(2), { value: chance ? null : drop, numeric: true }),
    );
  });
  fillTable(
    document.getElementById('parts'),
    [
      { label: 'Run' },
      { label: 'AUROC, meaning', numeric: true, title: 'Reading questions, units 1–6, with the 95% bootstrap interval' },
      { label: 'AUROC, form', numeric: true, title: 'Grammar questions, units 7–20, with the 95% bootstrap interval' },
      { label: 'Drop', numeric: true, title: 'AUROC on meaning minus AUROC on form' },
    ],
    rows,
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
        td(SOURCE_KINDS[entry.kind]),
        td([formatScore(entry.auroc), el('span', { class: 'small', text: scoreRange(entry.auroc_interval) ?? '' })], {
          value: entry.auroc,
          numeric: true,
        }),
      ),
    ),
  );
  fillTable(
    document.getElementById('sources-table'),
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

/* Repeated runs of one setup on the same questions. */
function renderRepeats(data) {
  const rows = data.repeats.map(item => {
    const mean = (100 * item.accuracy.reduce((sum, value) => sum + value, 0)) / item.accuracy.length;
    const range = `${(100 * Math.min(...item.accuracy)).toFixed(1)}–${(100 * Math.max(...item.accuracy)).toFixed(1)}%`;
    return el(
      'tr',
      {},
      modelCell(item, { withSetting: true }),
      td(String(item.questions_per_request), { value: item.questions_per_request, numeric: true }),
      td(`${integer(item.questions)}${item.whole_bank ? '' : ' (sample)'}`, { value: item.questions, numeric: true }),
      td(String(item.runs.length), { value: item.runs.length, numeric: true, title: `Runs ${item.runs.join(', ')}` }),
      percentCell(mean, { digits: 2, detail: range }),
      td(`${integer(item.changed_answer)} (${formatPercent(percent(item.changed_answer, item.questions), 1)})`, {
        value: percent(item.changed_answer, item.questions),
        numeric: true,
      }),
      td(`${integer(item.wrong_every_run_same)} of ${integer(item.wrong_any)}`, {
        value: percent(item.wrong_every_run_same, item.wrong_any),
        numeric: true,
        title: formatPercent(percent(item.wrong_every_run_same, item.wrong_any), 1),
      }),
      td(formatScore(item.score_spread_median), { value: item.score_spread_median, numeric: true }),
      td(item.scored ? `${integer(item.score_identical)} of ${integer(item.scored)}` : '—', {
        value: item.scored ? percent(item.score_identical, item.scored) : null,
        numeric: true,
      }),
      td(item.scored ? item.sure_wrong.join(' / ') : '—', { value: item.scored ? Math.max(...item.sure_wrong) : null, numeric: true }),
      td(item.scored ? String(item.sure_wrong_every_run) : '—', { value: item.scored ? item.sure_wrong_every_run : null, numeric: true }),
    );
  });
  fillTable(
    document.getElementById('repeats'),
    [
      { label: 'Setup' },
      { label: 'Per request', numeric: true, title: 'Questions per request' },
      { label: 'Questions', numeric: true, title: 'Asked the same way in every run' },
      { label: 'Runs', numeric: true },
      { label: 'Accuracy', numeric: true, title: 'Mean over the runs, with the lowest and highest' },
      { label: 'Changed answer', numeric: true, title: 'Questions on which the runs did not all choose the same option' },
      { label: 'Same mistake every run', numeric: true, title: 'Wrong in every run with the same option, of the questions any run got wrong' },
      { label: 'Score spread', numeric: true, title: 'Median over the questions of the largest minus the smallest score of the chosen options' },
      { label: 'Same score', numeric: true, title: 'Questions scored the same in every run' },
      { label: 'Wrong at ≥ 0.99', numeric: true, title: 'Each run’s wrong answers at a score of 0.99 or more' },
      { label: 'In every run', numeric: true, title: 'Questions wrong at 0.99 or more in every run' },
    ],
    rows,
  );
}

/* Cascades run for real: the frontier model answers only the questions the decision model passes on. */
function renderPipelines(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const rows = data.pipelines.map(item => {
    const measured = item.measured;
    return el(
      'tr',
      {},
      modelCell(byRun.get(item.decision)),
      modelCell(byRun.get(item.frontier), { withSetting: true }),
      td(integer(item.held_out), { value: item.held_out, numeric: true }),
      td(item.threshold.toFixed(3), { value: item.threshold, numeric: true }),
      percentCell(percent(item.routed, item.held_out), { detail: `${integer(item.routed)} questions` }),
      percentCell(100 * item.simulated.accuracy, { detail: `frontier ${formatPercent(100 * item.simulated.frontier_accuracy, 1)}` }),
      measured
        ? percentCell(100 * measured.accuracy, { detail: `frontier ${formatPercent(100 * measured.frontier_accuracy, 1)}` })
        : td('not run yet'),
      measured
        ? td([formatPoints(measured.difference), el('span', { class: 'small', text: `${formatPoints(measured.low)} to ${formatPoints(measured.high)}` })], {
            value: 100 * measured.difference,
            numeric: true,
          })
        : td('—'),
      td(measured ? formatP(measured.p) : '—', { value: measured?.p, numeric: true }),
      td(
        `${item.tolerance_points.toFixed(1)} points${measured ? (measured.within_tolerance ? ', kept' : ', missed') : ''}`,
      ),
      td(measured ? `${formatUsd(measured.cost_usd)} / ${formatUsd(measured.frontier_cost_usd)}` : '—', {
        value: measured?.cost_usd,
        numeric: true,
      }),
      td(
        measured ? `${(measured.request_seconds / 60).toFixed(1)} / ${(measured.frontier_request_seconds / 60).toFixed(1)}` : '—',
        { value: measured?.request_seconds, numeric: true },
      ),
    );
  });
  fillTable(
    document.getElementById('pipelines'),
    [
      { label: 'Decision model' },
      { label: 'Frontier run' },
      { label: 'Held out', numeric: true, title: 'Questions in the half the threshold was not chosen on' },
      { label: 'Threshold', numeric: true, title: 'Chosen on the other half, before the runs' },
      { label: 'Decision model answers', numeric: true },
      { label: 'Simulated', numeric: true, title: 'The stored whole-bank runs, scored on the held-out questions' },
      { label: 'Pipeline', numeric: true, title: 'New frontier run on the questions passed on, plus the decision model’s answers' },
      { label: 'Difference', numeric: true, title: 'Pipeline minus the frontier run on all held-out questions, in points, with the paired 95% interval' },
      { label: 'p', numeric: true, title: 'Exact McNemar test' },
      { label: 'Tolerance', title: 'The accuracy loss accepted before the runs' },
      { label: 'Cost', numeric: true, title: 'API-equivalent: pipeline / frontier alone' },
      { label: 'Minutes', numeric: true, title: 'Request time: pipeline / frontier alone' },
    ],
    rows,
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
    `${integer(data.questions)} Turkish-language exam questions in ${data.units.length} units · question bank version 2 · ` +
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
  renderParts(data);
  renderPipelines(data);
  renderRepeats(data);
}

main();
