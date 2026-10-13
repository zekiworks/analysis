'use strict';

/* Accuracy 0–100 → red, amber at 50, green: the local dashboard's scale. Each cell carries its light and dark colour
   and the stylesheet shows the one for the theme, so switching themes needs no redraw. The dark colours keep light
   text and the answer counts above 4.5:1. */
const HEAT = {
  light: [[254, 226, 226], [254, 243, 199], [187, 247, 208]],
  dark: [[76, 29, 36], [74, 59, 16], [19, 78, 46]],
};
function heatStyle(accuracy) {
  const p = Math.min(100, Math.max(0, accuracy)) / 100;
  const mix = ([low, mid, high]) => {
    const [from, to, t] = p <= 0.5 ? [low, mid, p / 0.5] : [mid, high, (p - 0.5) / 0.5];
    return `rgb(${from.map((start, i) => Math.round(start + (to[i] - start) * t)).join(', ')})`;
  };
  return `--heat-light: ${mix(HEAT.light)}; --heat-dark: ${mix(HEAT.dark)}`;
}

/* ---- Wording used in more than one place (brief part 4: one source for each repeated phrase). ---- */

/* Why a cell has no value. Each case keeps its own words; no one symbol stands for all of them. */
const EMPTY = {
  notPublished: 'Not published',
  notMeasured: 'Not measured',
  noAnswers: 'No answers in this group',
  noneReach: 'No answers reach this cutoff',
  notApplicable: 'Not applicable',
  noNewCalls: 'No test with new calls recorded',
  noCutoff: 'No cutoff kept the second model’s accuracy on this question set.',
};
/* A cost cell for a run without a dollar figure, and the matching price note. */
const NO_COST = {
  local: 'No dollar estimate; see hardware and time',
  free: 'Free tier used; no paid price in this record',
};
const FREE_RATE = 'Free tier used; no paid rate in this record.';
/* What the combined cost leaves out when the first model has no dollar figure. */
const FIRST_MODEL_UNPRICED = {
  local: 'Plus the first model’s hardware cost, which we have not estimated',
  free: 'The first model used a free tier; this estimate assumes no charge for it.',
};
/* How we called each model. */
const BILLING = {
  api: 'Provider service',
  subscription: 'Subscription',
  free: 'Free tier used',
  local: 'Our own hardware',
};
const PRICE_BASIS = 'Estimated from published prices and recorded token usage.';
const SUBSCRIPTION_PRICED = 'Subscription run priced as if we had used the API.';
const INVOICE = 'Actual invoice not checked.';
const REUSE_EXPLAINED =
  'A service may save input so a later call can reuse it. It may charge one rate to save it and another to read it again.';
const COST_ESTIMATE_NOTE =
  'This estimate gives each question passed to the second model the same average cost. In a new run, the remaining questions may cost more.';
const INTERVAL_TIP =
  'A range describing sampling uncertainty in this measured rate. It does not cover every source of error or guarantee a future rate.';
const GROUP_TIP =
  'The all pairs test did not detect a difference from setups sharing a letter. This does not establish equality.';
const PARAMETERS_TIP =
  'Parameters are the stored numerical values that shape a model’s behaviour. B means billion and M means million. “Active” counts the values used for one token where the model’s design reports this.';
const TOKENS_TIP =
  'Average recorded output per question, including reasoning tokens when the service reports them. A token is a small piece of text.';
const AUROC_TIP =
  'How often a randomly chosen correct answer scores above a randomly chosen wrong one, with half credit for ties. 0.50 is chance ranking; 1.00 is perfect ranking.';
const CHANCE_BOTH = 'Evidence does not establish better than chance ranking in either category.';
const CHANGED_ANSWER_NOTE =
  'A changed answer on an unchanged question does not necessarily mean that the repair caused it.';
const OPTION_SCORES = 'Scores the supplied options';
const DECISION_GROUP = 'Decision models';
const OTHER_GROUP = 'Chat models and other comparison models';
/* Shuffles behind the uncertainty table's p values (benchmark_metrics.py, spearman_permutation); results.json does
   not store the count. */
const SHUFFLES = 200;
/* Topics 1–6 test reading; topics 7–20 test grammar (benchmark_metrics.py's split of the units). */
const isReading = unit => unit.number <= 6;

/* ---- Numbers ---- */

const integer = n => n.toLocaleString('en-US');
const percent = (correct, total) => (total ? (100 * correct) / total : null);
const formatPercent = (value, digits = 1) => `${value.toFixed(digits)}%`;
const formatScore = value => value.toFixed(2);
const formatP = p => (p < 0.0001 ? 'below 0.0001' : p.toFixed(4));
/* A signed number; a value that rounds to zero shows no sign. */
const signed = (value, digits) => {
  const text = Math.abs(value).toFixed(digits);
  return Number(text) === 0 ? text : `${value > 0 ? '+' : '−'}${text}`;
};
/* A difference between two shares, in percentage points. */
const formatPoints = (fraction, digits = 1) => signed(100 * fraction, digits);
const pointsText = (fraction, digits = 1) => `${formatPoints(fraction, digits)} points`;
const pointsRange = (low, high, digits = 1) => `${formatPoints(low, digits)} to ${formatPoints(high, digits)} points`;
const scoreRange = interval => (interval ? `${formatScore(interval[0])} to ${formatScore(interval[1])}` : null);
const percentRange = (interval, digits = 1) =>
  interval ? `${formatPercent(100 * interval[0], digits)} to ${formatPercent(100 * interval[1], digits)}` : null;
/* A confidence or cutoff as a percentage, with enough decimals to tell it from 100%: 0.99 → 99%, 0.9156852 →
   91.57%, 0.99999999 → 99.999999%. The stored value stays exact; only the display rounds. */
function cutoffText(fraction) {
  if (fraction >= 1) return '100%';
  let digits = 2;
  let text = (100 * fraction).toFixed(digits);
  while (Number(text) >= 100 && digits < 12) text = (100 * fraction).toFixed(++digits);
  return `${text.replace(/\.?0+$/, '')}%`;
}
const atCutoff = fraction => `${cutoffText(fraction)} confidence or higher`;
/* A confidence group: each includes its lower bound; the last also includes 100%. */
const binLabel = (low, high, last) => (last ? `${cutoffText(low)} to ${cutoffText(high)}` : `${cutoffText(low)} to below ${cutoffText(high)}`);
/* Dollars: cents from $0.10 up and three decimals below, so that $0.0078 does not read as $0.01 (as in build_page.py). */
const formatUsd = value => {
  if (value >= 0.1 || value === 0) return `$${value.toFixed(2)}`;
  const text = value.toFixed(3);
  return text === '0.000' ? `$${value.toPrecision(2)}` : `$${text}`;
};
/* A price per million tokens, exactly as recorded: $4, $0.20, $0.075, $12.50. */
const formatRate = value => {
  if (Number.isInteger(value)) return `$${value}`;
  const [whole, decimals] = String(value).split('.');
  return `$${whole}.${decimals.padEnd(2, '0')}`;
};
/* A parameter count: 31.3B or 287M, with the parameters active per token where the design reports them. */
const formatBillions = count => `${(count / 1e9).toFixed(1).replace(/\.0$/, '')}`;
const formatParameters = (count, active = null) => {
  const size = count >= 1e9 ? `${formatBillions(count)}B` : `${Math.round(count / 1e6)}M`;
  return active ? `${size} (${active.map(formatBillions).join(' to ')}B active)` : size;
};
/* A count below ten in words, a larger one in figures (in_words in build_page.py). */
const inWords = value => ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'][value] ?? integer(value);
const numbersText = numbers => {
  const last = numbers[numbers.length - 1];
  if (numbers.length > 1 && numbers.every((number, index) => number === numbers[0] + index)) return `${numbers[0]} to ${last}`;
  return numbers.length > 1 ? `${numbers.slice(0, -1).join(', ')} and ${last}` : String(last);
};
const dateText = iso =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
/* Times: milliseconds below one second, seconds from one second; a non-breaking space keeps the unit with its number. */
const duration = seconds =>
  seconds < 1 ? `${Math.round(1000 * seconds)}\u00a0ms` : `${seconds.toFixed(seconds < 10 ? 2 : 1)}\u00a0s`;
const minutes = seconds => `${(seconds / 60).toFixed(1)}\u00a0min`;

/* A run's cost and request time per 1,000 questions asked; the cost is null for free and self-hosted runs. */
const costPer1000 = run => (run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / run.answered_questions);
const minutesPer1000 = run => (run.request_seconds == null ? null : (1000 * run.request_seconds) / 60 / run.answered_questions);

/* ---- Prices ---- */

const priceOf = (data, run) => data.prices.find(price => price.provider === run.provider && price.model === run.model);
/* Each recorded rate that applies to the setup, as "input $4". A reuse rate equal to the input rate is no separate
   charge, so it is left out (the same rule as the recorded price text). Cache durations show only when the two
   saving rates differ. */
function rateParts(price) {
  const { rates } = price;
  const differs = key => rates[key] != null && rates[key] !== rates.input_tokens;
  const parts = [`input ${formatRate(rates.input_tokens)}`];
  if (differs('cached_input_tokens')) parts.push(`reused input ${formatRate(rates.cached_input_tokens)}`);
  const short = differs('cache_write_input_tokens');
  const long = differs('cache_write_1h_input_tokens');
  if (short && long) {
    parts.push(
      `saving input for reuse ${formatRate(rates.cache_write_input_tokens)} for 5 minutes, ${formatRate(rates.cache_write_1h_input_tokens)} for 1 hour`,
    );
  } else if (short || long) {
    parts.push(`saving input for reuse ${formatRate(short ? rates.cache_write_input_tokens : rates.cache_write_1h_input_tokens)}`);
  }
  parts.push(rates.output_tokens ? `output ${formatRate(rates.output_tokens)}` : 'output free');
  return parts;
}
const rateText = price => `Per one million tokens: ${rateParts(price).join('; ')}.`;

/* The tooltip of a cost cell. */
function costTitle(data, run) {
  if (run.billing === 'local') return `${BILLING.local}: ${run.hardware}. ${NO_COST.local}.`;
  if (run.billing === 'free') return `${NO_COST.free}.`;
  const price = priceOf(data, run);
  if (!price) return null;
  return [
    `${price.basis}, recorded ${dateText(price.date)}.`,
    rateText(price),
    PRICE_BASIS,
    run.billing === 'subscription' ? SUBSCRIPTION_PRICED : null,
    INVOICE,
  ]
    .filter(Boolean)
    .join(' ');
}

/* ---- Elements ---- */

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

const small = text => el('span', { class: 'small', text });

/* A cell; numeric cells carry their sort value in data-value ('' when missing). */
function td(content, { value, numeric = false, className = null, title = null, style = null } = {}) {
  const classes = [numeric ? 'num' : null, className].filter(Boolean).join(' ') || null;
  const cell = el('td', { class: classes, title, style }, ...[].concat(content));
  if (value !== undefined) cell.dataset.value = value ?? '';
  return cell;
}

/* A cell without a value, saying why. */
function emptyCell(reason, { numeric = true, title = null, className = null } = {}) {
  return td(el('span', { class: 'empty', text: reason }), {
    value: null,
    numeric,
    title,
    className: [className, 'no-value'].filter(Boolean).join(' '),
  });
}

/* A numeric cell showing a percentage, with an optional second line (an interval). */
function percentCell(value, { digits = 1, title = null, heat = false, detail = null, empty = EMPTY.notMeasured } = {}) {
  if (value == null) return emptyCell(empty, { title });
  return td([formatPercent(value, digits), detail ? small(detail) : null], {
    value,
    numeric: true,
    title,
    className: heat ? 'heat' : null,
    style: heat ? heatStyle(value) : null,
  });
}

/* A table note; parts are strings or [href, text] links. */
function tableNote(...parts) {
  return el('p', { class: 'table-note' }, ...parts.map(part => (Array.isArray(part) ? el('a', { href: part[0], text: part[1] }) : part)));
}

/* Notes go right after the table's scrolling box; leading notes right before it. */
const tableBox = table => table.closest('.table-wrap') ?? table;
function addNotes(table, ...notes) {
  tableBox(table).after(...notes.filter(Boolean));
}

/* The row of controls above a table, made on first use. */
function controlsFor(table) {
  const box = tableBox(table);
  const previous = box.previousElementSibling;
  if (previous?.classList.contains('table-controls')) return previous;
  const controls = el('div', { class: 'table-controls' });
  box.before(controls);
  return controls;
}

/* ---- Screen reader announcements ---- */

let liveRegion = null;
function announce(text) {
  if (!liveRegion) {
    liveRegion = el('div', { class: 'visually-hidden', role: 'status', 'aria-live': 'polite' });
    document.body.append(liveRegion);
  }
  // Clear first, so the same message read twice is announced twice.
  liveRegion.textContent = '';
  setTimeout(() => {
    liveRegion.textContent = text;
  }, 50);
}

/* A button above the table that shows or hides its columns marked extra; the table starts with them hidden. */
function addColumnToggle(table) {
  const button = el('button', {
    type: 'button',
    class: 'show-all',
    'aria-expanded': 'false',
    'aria-controls': table.id,
    text: 'Show more details',
  });
  table.classList.add('collapsed');
  button.addEventListener('click', () => {
    const expanded = !table.classList.toggle('collapsed');
    button.setAttribute('aria-expanded', String(expanded));
    button.textContent = expanded ? 'Show fewer details' : 'Show more details';
  });
  controlsFor(table).append(button);
}

/* ---- Sorting ---- */

const sorters = new WeakMap();

/* A column's plain name, for "Sort by …" and the announcement. */
const columnName = column => column.name ?? (typeof column.label === 'string' ? column.label : [].concat(column.label)[0]);

/* Each sortable heading holds a button named "Sort by <column>". Numbers sort high to low first, text A to Z first;
   missing values go last and equal values keep the original order. Each body sorts on its own, so group label rows
   stay at the top of their group. The new order is announced. */
function makeSortable(table, columns) {
  const headers = [...table.tHead.rows[0].cells];
  const sort = (index, direction, { quiet = false } = {}) => {
    const numeric = headers[index].classList.contains('num');
    headers.forEach((header, i) => {
      if (header.hasAttribute('aria-sort')) header.setAttribute('aria-sort', i === index ? direction : 'none');
    });
    const key = row => {
      const cell = row.cells[index];
      const raw = cell?.dataset.value ?? cell?.textContent.trim() ?? '';
      return numeric ? (raw === '' ? null : Number(raw)) : raw;
    };
    for (const body of table.tBodies) {
      const labels = [...body.rows].filter(row => row.classList.contains('group-label'));
      const rows = [...body.rows]
        .filter(row => !row.classList.contains('group-label'))
        .sort((a, b) => {
          const x = key(a);
          const y = key(b);
          let order;
          if (x == null || y == null) order = (x == null) - (y == null);
          else {
            order = numeric ? x - y : String(x).localeCompare(String(y), 'en', { numeric: true });
            if (direction === 'descending') order = -order;
          }
          return order || a.dataset.order - b.dataset.order;
        });
      body.append(...labels, ...rows);
    }
    if (!quiet) {
      announce(`Sorted by ${columnName(columns[index])}, ${direction === 'ascending' ? 'increasing' : 'decreasing'} order.`);
    }
  };
  headers.forEach((th, index) => {
    const column = columns[index];
    if (column.sortable === false) return;
    const button = el('button', { type: 'button', class: 'sort', 'aria-label': `Sort by ${columnName(column)}` }, ...th.childNodes);
    th.replaceChildren(button);
    if (!th.hasAttribute('aria-sort')) th.setAttribute('aria-sort', 'none');
    button.addEventListener('click', () => {
      const current = th.getAttribute('aria-sort');
      const numeric = th.classList.contains('num');
      const direction =
        current === 'descending' ? 'ascending' : current === 'ascending' ? 'descending' : numeric ? 'descending' : 'ascending';
      sort(index, direction);
    });
  });
  sorters.set(table, sort);
}

/* A row naming the group of rows below it. */
const groupLabelRow = (label, span) =>
  el('tr', { class: 'group-label' }, el('th', { scope: 'rowgroup', colspan: String(span) }, el('span', { text: label })));

/* Fills the table with this id; returns it, or null when the page has no such table. columns: [{ label, name,
   numeric, title, className, extra, sortable }]; labels may be strings or node arrays (then give a name); extra
   columns hide behind the toggle. groups: [{ label, rows }] puts each group in its own body under a label row.
   sorted: [column index, direction] the rows already follow. */
function fillTable(id, columns, rows, { groups = null, sorted = null } = {}) {
  const table = document.getElementById(id);
  if (!table) return null;
  table.classList.add('dynamic');
  const head = el('tr');
  columns.forEach((column, index) => {
    const classes = [column.numeric ? 'num' : null, column.className, column.extra ? 'extra' : null].filter(Boolean).join(' ') || null;
    const th = el('th', { scope: 'col', class: classes, title: column.title }, ...[].concat(column.label));
    if (sorted && sorted[0] === index) th.setAttribute('aria-sort', sorted[1]);
    head.append(th);
  });
  const sections = groups ?? [{ label: null, rows }];
  sections
    .flatMap(section => section.rows)
    .forEach((row, index) => {
      row.dataset.order = index;
      columns.forEach((column, i) => {
        if (column.extra) row.cells[i]?.classList.add('extra');
      });
    });
  table.replaceChildren(
    el('thead', {}, head),
    ...sections.map(section =>
      el('tbody', {}, section.label ? groupLabelRow(section.label, columns.length) : null, ...section.rows),
    ),
  );
  makeSortable(table, columns);
  return table;
}

/* ---- Models ---- */

const reasoningLabel = reasoning => (['off', 'on'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
const runLabel = run => run.variant ?? (run.reasoning ? reasoningLabel(run.reasoning) : OPTION_SCORES.toLowerCase());
const displayName = run => {
  const details = [run.variant, run.format].filter(Boolean);
  return `${run.name}${details.length ? ` (${details.join(', ')})` : ''}`;
};
const sourceText = run => `Confidence source: ${run.confidence.label.toLowerCase()}`;

/* withSetting: also name the reasoning setting, for tables without a reasoning column. withSource: add the
   confidence source badge. */
function modelCell(run, { withSetting = false, withSource = false } = {}) {
  const setting = [run.variant ?? (withSetting && run.reasoning ? reasoningLabel(run.reasoning) : null), run.format].filter(Boolean).join(' · ');
  return td(
    [
      el('span', { class: 'model-name', text: run.name }),
      setting ? el('span', { class: 'muted', text: ` · ${setting}` }) : null,
      el('code', { class: 'small', text: run.model }),
      withSource && run.confidence ? el('span', { class: 'small source', text: sourceText(run) }) : null,
      run.note ? small(run.note) : null,
    ],
    { value: `${run.name} ${run.variant ?? ''} ${run.reasoning ?? ''} ${run.format ?? ''}`, className: 'model' },
  );
}

function groupAccuracy(run, name) {
  const group = run.groups[name];
  return group ? percent(group.correct, group.questions) : null;
}

/* A dollar cell: the estimate, or why there is none. */
function costCell(data, run) {
  const cost = costPer1000(run);
  const title = costTitle(data, run);
  if (cost == null) return emptyCell(NO_COST[run.billing] ?? EMPTY.notMeasured, { title });
  return td(formatUsd(cost), { value: cost, numeric: true, title });
}

/* A run's response time, as part 4's time cell: median and 9 in 10, how many questions one request holds, where the
   times come from, and how many requests ran at a time. A batch's time is the whole request's. */
function latencyCell(run) {
  const latency = run.latency;
  if (!latency) return emptyCell(EMPTY.notMeasured, { className: 'time' });
  const notes = [`90% of requests finished within ${duration(latency.p90_request_seconds)}.`];
  notes.push(
    run.questions_per_request === 1
      ? 'One question per request.'
      : `One request contains ${integer(run.questions_per_request)} questions; the time covers the whole request.`,
  );
  if (latency.source === 'repeats') notes.push(`Times from repeats ${numbersText(latency.repeats)} of the same setup.`);
  if (latency.source === 'sample') {
    notes.push(`Times from ${inWords(latency.runs.length)} runs of the same ${integer(latency.questions)} questions.`);
  }
  notes.push(`Simultaneous requests: ${integer(latency.concurrency)}.`);
  const single = run.single_question_latency;
  if (single) {
    notes.push(
      `Separate test: one question per request, ${integer(single.questions)} questions. Median ${duration(single.median_request_seconds)}; ` +
        `90% within ${duration(single.p90_request_seconds)}.`,
    );
  }
  return td([`Median ${duration(latency.median_request_seconds)}`, ...notes.map(small)], {
    value: latency.median_request_seconds,
    numeric: true,
    className: 'time',
  });
}

/* ---- Tables ---- */

function renderLeaderboard(data, config) {
  const total = data.questions;
  const decision = run =>
    config.decision_model_providers.includes(run.provider) && !config.not_decision_models.includes(run.model);
  const examTip = `Reweights these reading and grammar scores to ${integer(data.tyt_mix.reading)} reading questions and ${inWords(data.tyt_mix.grammar)} grammar questions. It is not a score on the exam itself.`;
  const entries = data.runs.map(run => {
    const score = percent(run.correct, total);
    const tokens = run.output_tokens == null ? null : run.output_tokens / (run.answered_questions ?? total);
    const auroc = run.confidence?.auroc ?? null;
    const row = el(
      'tr',
      {},
      modelCell(run),
      run.parameters == null
        ? emptyCell(EMPTY.notPublished, { title: 'Its maker has not published the model size.' })
        : td(formatParameters(run.parameters, run.active_parameters), {
            value: run.parameters,
            numeric: true,
            title: `${integer(run.parameters)} parameters`,
          }),
      td(run.reasoning ?? OPTION_SCORES, { className: run.reasoning ? null : 'muted' }),
      td([el('span', { class: 'bar', style: `width: ${score}%` }), el('span', { class: 'value', text: formatPercent(score) })], {
        value: score,
        numeric: true,
        className: 'score',
        title: `${integer(run.correct)} of ${integer(total)} correct`,
      }),
      run.group ? td(run.group, { className: 'group', title: GROUP_TIP }) : emptyCell(EMPTY.notApplicable, { numeric: false }),
      percentCell(groupAccuracy(run, 'reading')),
      percentCell(groupAccuracy(run, 'grammar')),
      auroc == null ? emptyCell(EMPTY.notMeasured) : td(formatScore(auroc), { value: auroc, numeric: true }),
      tokens == null
        ? emptyCell(EMPTY.notMeasured)
        : td(tokens.toFixed(1), { value: tokens, numeric: true, title: `${integer(run.output_tokens)} output tokens in all` }),
      costCell(data, run),
      percentCell(run.tyt_mix == null ? null : 100 * run.tyt_mix, { title: examTip }),
      run.questions_per_minute == null
        ? emptyCell(EMPTY.notMeasured)
        : td(run.questions_per_minute.toFixed(1), {
            value: run.questions_per_minute,
            numeric: true,
            title: `Simultaneous requests: ${integer(run.concurrency)}`,
          }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
      td(integer(run.correct), { value: run.correct, numeric: true }),
      td(run.access),
    );
    return { run, row, decision: decision(run) };
  });
  const byScore = (a, b) => b.run.correct - a.run.correct;
  const groups = () => {
    const decisionRows = entries.filter(entry => entry.decision).sort(byScore);
    const otherRows = entries.filter(entry => !entry.decision).sort(byScore);
    return [
      { label: `${DECISION_GROUP} (${integer(decisionRows.length)} setups)`, rows: decisionRows.map(entry => entry.row) },
      { label: `${OTHER_GROUP} (${integer(otherRows.length)} setups)`, rows: otherRows.map(entry => entry.row) },
    ];
  };
  const scoreColumn = 3;
  const columns = [
    { label: 'Model and setup' },
    { label: 'Model size in parameters', numeric: true, title: PARAMETERS_TIP, extra: true },
    { label: 'Reasoning setting' },
    { label: 'Correct answers overall', numeric: true },
    { label: 'Comparison group', title: GROUP_TIP, extra: true },
    { label: 'Reading accuracy', numeric: true },
    { label: 'Grammar accuracy', numeric: true },
    { label: 'Confidence ranking (AUROC)', numeric: true, title: AUROC_TIP, extra: true },
    { label: 'Output tokens per question', numeric: true, title: TOKENS_TIP, extra: true },
    { label: 'Estimated cost per 1,000 questions in US dollars', numeric: true },
    { label: 'Accuracy with the exam’s reading and grammar mix', numeric: true, title: examTip, extra: true },
    { label: 'Questions per minute', numeric: true, extra: true },
    { label: 'Questions in each request', numeric: true, extra: true },
    { label: 'Number of correct answers', numeric: true, extra: true },
    { label: 'How we called the model', extra: true },
  ];
  const table = fillTable('leaderboard', columns, null, { groups: groups(), sorted: [scoreColumn, 'descending'] });
  if (!table) return;

  // Grouped view (decision models first) or one list in order of observed accuracy.
  const order = el('button', { type: 'button', class: 'show-all', 'aria-pressed': 'false', 'aria-controls': table.id, text: 'Order by observed accuracy' });
  const hint = el('span', { class: 'control-hint' });
  const GROUPED_HINT = 'Decision models first, then the other models. This is a reading order, not a rank.';
  const FLAT_HINT = 'One list, highest observed accuracy first. This mixes the two groups. A higher place does not show a real difference.';
  const layout = flat => {
    const sections = flat
      ? [{ label: null, rows: [...entries].sort(byScore).map(entry => entry.row) }]
      : groups();
    table.querySelectorAll('tbody').forEach(body => body.remove());
    for (const section of sections) {
      table.append(el('tbody', {}, section.label ? groupLabelRow(section.label, columns.length) : null, ...section.rows));
    }
    sorters.get(table)(scoreColumn, 'descending', { quiet: true });
    order.setAttribute('aria-pressed', String(flat));
    hint.textContent = flat ? FLAT_HINT : GROUPED_HINT;
  };
  order.addEventListener('click', () => {
    const flat = order.getAttribute('aria-pressed') !== 'true';
    layout(flat);
    announce(flat ? `All setups in one list. ${FLAT_HINT}` : `${GROUPED_HINT}`);
  });
  hint.textContent = GROUPED_HINT;
  const controls = controlsFor(table);
  controls.append(order, hint);
  addColumnToggle(table);
  addNotes(
    table,
    tableNote(
      'Sorting by a column sorts within each group; Order by observed accuracy puts every setup in one list. ',
      'Show more details adds the comparison group letters. ',
      GROUP_TIP,
      ' The test behind them covers all ',
      integer(data.group_pairs),
      ' pairs of setups (see ',
      ['#differences', 'how we compare scores'],
      ').',
    ),
  );
}

function renderCost(data) {
  const rows = data.runs.map(run => {
    const perThousand = minutesPer1000(run);
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      costCell(data, run),
      perThousand == null
        ? emptyCell(EMPTY.notMeasured)
        : td(perThousand.toFixed(1), { value: perThousand, numeric: true }),
      latencyCell(run),
      td(BILLING[run.billing], { title: run.access }),
      run.hardware ? td(run.hardware) : emptyCell(EMPTY.notApplicable, { numeric: false, title: 'The provider runs this model.' }),
      td(String(run.concurrency), { value: run.concurrency, numeric: true }),
    );
  });
  const table = fillTable(
    'cost',
    [
      { label: 'Model and setup' },
      {
        label: 'Estimated cost per 1,000 questions in US dollars',
        numeric: true,
        title: `${PRICE_BASIS} The price list is under the table.`,
      },
      { label: 'Minutes per 1,000 questions in this setup', numeric: true, title: 'Total time while requests were open, per 1,000 questions asked' },
      {
        label: 'Waiting time per request: median / nine out of ten',
        numeric: true,
        title: 'Time for one request, measured on our machine. A request with several questions counts as one request.',
      },
      { label: 'How we called the model' },
      { label: 'Hardware we used' },
      { label: 'Simultaneous requests', numeric: true },
    ],
    rows,
  );
  if (table) {
    addNotes(
      table,
      tableNote(
        'Waiting time: we do not divide a request’s time among its questions. Some setups use times from later runs of ',
        'the same setup, because their first run did not record the time of each request; the cell says which (see ',
        ['#accuracy-cost-latency', 'the price and speed overview'],
        ').',
      ),
    );
  }
  renderCostNotes(data);
}

/* The price list under "How we estimate the money cost": one line per recorded price, then the free tier and the
   models on our own hardware. */
function renderCostNotes(data) {
  const list = document.getElementById('cost-notes');
  if (!list) return;
  const names = runs => [...new Set(runs.map(displayName))].join(', ');
  const priced = data.prices.map(price => {
    const runs = data.runs.filter(run => run.provider === price.provider && run.model === price.model);
    return el(
      'li',
      {},
      `${names(runs) || price.model}. Prices recorded ${dateText(price.date)}. ${rateText(price)} Source: `,
      el('a', { href: price.source, text: price.basis }),
      '.',
      price.change ? ` Provider update: ${price.change}.` : null,
    );
  });
  const free = data.runs.filter(run => run.billing === 'free');
  const local = data.runs.filter(run => run.billing === 'local');
  const reuse = data.prices.some(price => rateParts(price).some(part => part.startsWith('reused') || part.startsWith('saving')));
  list.replaceChildren(
    reuse ? el('li', { text: REUSE_EXPLAINED }) : null,
    ...priced,
    free.length ? el('li', { text: `${names(free)}. ${FREE_RATE}` }) : null,
    local.length ? el('li', { text: `${names(local)}. ${NO_COST.local}.` }) : null,
  );
}

/* One row per run: the score, reading and grammar, then (behind the toggle) every topic, coloured by accuracy. */
function renderUnits(data) {
  const heatCell = (correct, questions, run, part = '') => {
    const accuracy = percent(correct, questions);
    if (accuracy == null) return emptyCell(EMPTY.noAnswers);
    return td(formatPercent(accuracy, 1), {
      value: accuracy,
      numeric: true,
      className: 'heat',
      title: `${run.name}, ${runLabel(run)}${part}: ${integer(correct)} of ${integer(questions)} correct`,
      style: heatStyle(accuracy),
    });
  };
  const sum = (values, keep) => values.reduce((total, value, index) => total + (keep(data.units[index]) ? value : 0), 0);
  const questions = data.units.map(unit => unit.questions);
  const readingUnits = data.units.filter(isReading);
  const grammarUnits = data.units.filter(unit => !isReading(unit));
  const span = units => `topics ${units[0].number} to ${units[units.length - 1].number}`;
  const readingQuestions = sum(questions, isReading);
  const grammarQuestions = sum(questions, unit => !isReading(unit));
  const rows = data.runs.map(run =>
    el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      heatCell(run.correct, data.questions, run),
      heatCell(sum(run.units, isReading), readingQuestions, run, ', reading'),
      heatCell(sum(run.units, unit => !isReading(unit)), grammarQuestions, run, ', grammar'),
      ...data.units.map((unit, index) => heatCell(run.units[index], unit.questions, run, `, topic ${unit.number}`)),
    ),
  );
  const table = fillTable(
    'units',
    [
      { label: 'Model and setup' },
      {
        label: ['Correct answers overall', small(`${integer(data.questions)} questions`)],
        name: 'Correct answers overall',
        numeric: true,
        className: 'unit',
      },
      {
        label: ['Reading accuracy', small(`${span(readingUnits)}, ${integer(readingQuestions)} questions`)],
        name: 'Reading accuracy',
        numeric: true,
        className: 'unit',
      },
      {
        label: ['Grammar accuracy', small(`${span(grammarUnits)}, ${integer(grammarQuestions)} questions`)],
        name: 'Grammar accuracy',
        numeric: true,
        className: 'unit',
      },
      ...data.units.map(unit => ({
        label: [`${unit.number}. ${unit.english}`, small(`${integer(unit.questions)} questions`)],
        name: `topic ${unit.number}, ${unit.english}`,
        numeric: true,
        className: 'unit',
        title: `${isReading(unit) ? 'Reading' : 'Grammar'} topic. Printed title: ${unit.name}`,
        extra: true,
      })),
    ],
    rows,
    { sorted: [1, 'descending'] },
  );
  if (table) addColumnToggle(table);
}

function renderConfidence(data) {
  const runs = data.runs.filter(run => run.confidence);
  const bins = runs[0]?.confidence.reliability ?? [];
  const groupCount = inWords(bins.length);
  const rows = runs.map(run =>
    el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(run.confidence.label),
      ...run.confidence.reliability.map(bin => {
        if (!bin.questions) return emptyCell(EMPTY.noAnswers, { className: 'heat' });
        const accuracy = 100 * bin.accuracy;
        const mean = bin.mean_confidence == null ? '' : ` Mean confidence ${formatPercent(100 * bin.mean_confidence, 1)}.`;
        return td([formatPercent(accuracy, 1), el('span', { class: 'count', text: ` (${integer(bin.questions)})` })], {
          value: accuracy,
          numeric: true,
          className: 'heat',
          title: `${formatPercent(accuracy, 1)} correct among ${integer(bin.questions)} answers.${mean}`,
          style: heatStyle(accuracy),
        });
      }),
    ),
  );
  fillTable(
    'confidence',
    [
      { label: 'Model and setup' },
      { label: 'Where the confidence score comes from' },
      ...bins.map((bin, index) => ({
        label: binLabel(bin.low, bin.high, index === bins.length - 1),
        numeric: true,
        title: `Accuracy of the answers with confidence in this range; the number of answers in brackets. One of ${groupCount} confidence groups.`,
      })),
    ],
    rows,
  );

  const eceTip = `Average gap between confidence and accuracy across ${groupCount} confidence groups, weighted by group size. Smaller is better. Shown in percentage points.`;
  const ranking = runs.map(run => {
    const { auroc, auroc_interval: aurocInterval, ece, coverage_accuracy: coverage, coverage_intervals: intervals } = run.confidence;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true, withSource: true }),
      td([formatScore(auroc), aurocInterval ? small(scoreRange(aurocInterval)) : null], {
        value: auroc,
        numeric: true,
        title: aurocInterval ? `95% interval: ${scoreRange(aurocInterval)}` : null,
      }),
      td(`${(100 * ece).toFixed(1)} points`, { value: ece, numeric: true }),
      ...data.coverages.map(share => {
        const key = share.toFixed(2);
        const accuracy = coverage[key];
        return percentCell(accuracy == null ? null : 100 * accuracy, {
          heat: true,
          detail: intervals ? percentRange(intervals[key]) : null,
          title: intervals?.[key] ? `95% interval: ${percentRange(intervals[key])}. ${INTERVAL_TIP}` : null,
        });
      }),
      percentCell(percent(run.correct, data.questions), { heat: true }),
    );
  });
  fillTable(
    'ranking',
    [
      { label: 'Model and setup' },
      { label: 'Confidence ranking (AUROC)', numeric: true, title: `${AUROC_TIP} The second line is the 95% interval.` },
      { label: 'Average confidence gap (ECE)', numeric: true, title: eceTip },
      ...data.coverages.map(share => ({
        label: `Accuracy among the most confident ${Math.round(100 * share)}% of answers`,
        numeric: true,
        title: `We take the ${Math.round(100 * share)}% of answers with the highest confidence and check how many are right. The second line is the 95% interval.`,
      })),
      { label: 'Accuracy on all questions', numeric: true },
    ],
    ranking,
  );

  renderSure(data, runs);
}

/* Answers at the fixed cutoff, graded after the key review and (optional columns) before it. */
function renderSure(data, runs) {
  const rule = atCutoff(data.sure_threshold);
  const notRun = 'We ran this setup after the key review, so it has no result before the review.';
  const sureCells = (sure, bank, { before = false } = {}) => {
    if (!sure) return [emptyCell(EMPTY.notApplicable, { title: notRun }), emptyCell(EMPTY.notApplicable, { title: notRun })];
    if (!sure.questions) return [emptyCell(EMPTY.noneReach), emptyCell(EMPTY.notApplicable, { title: 'No kept answers, so no accuracy.' })];
    const { questions, correct, interval } = sure;
    return [
      td([`${integer(correct)} of ${integer(questions)}`, before ? null : small(`${formatPercent(percent(questions, bank), 1)} of ${integer(bank)} questions kept`)], {
        value: questions,
        numeric: true,
      }),
      percentCell(percent(correct, questions), {
        detail: interval ? `95% interval: ${percentRange(interval)}` : null,
        title: INTERVAL_TIP,
      }),
    ];
  };
  const rows = runs.map(run =>
    el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      ...sureCells(run.confidence.sure, data.questions),
      ...sureCells(run.confidence.sure_before_audit, data.questions, { before: true }),
      td(run.confidence.label),
    ),
  );
  const table = fillTable(
    'sure-table',
    [
      { label: 'Model and setup' },
      { label: 'Correct out of kept answers after the key review', numeric: true, title: `Answers kept at ${rule}, graded with the reviewed answer key` },
      { label: 'Accuracy of kept answers after the key review', numeric: true, title: `With its 95% interval. ${INTERVAL_TIP}` },
      {
        label: 'Correct out of kept answers before the key review',
        numeric: true,
        title: `Answers kept at ${rule}, graded with the printed answer key, including the questions the review later removed`,
        extra: true,
      },
      { label: 'Accuracy of kept answers before the key review', numeric: true, title: `With its 95% interval. ${INTERVAL_TIP}`, extra: true },
      { label: 'Where the confidence score comes from' },
    ],
    rows,
  );
  if (table) {
    addColumnToggle(table);
    addNotes(table, tableNote(`We keep an answer when its confidence is ${rule}. A model’s confidence and a 95% interval are different things: the interval describes our measurement of the accuracy.`));
  }
}

const SOURCE_KINDS = {
  stated: 'The model writes a confidence estimate',
  probability: 'The model scores this fixed answer',
  votes: 'How many of ten generated answers agree with this answer',
};

/* Confidence ranking on reading and on grammar for every run with a confidence, highest on reading first. */
function renderParts(data) {
  const runs = data.runs
    .filter(run => run.confidence?.parts?.meaning && run.confidence.parts.form)
    .sort((a, b) => b.confidence.parts.meaning.auroc - a.confidence.parts.meaning.auroc);
  const aurocCell = part =>
    td([formatScore(part.auroc), part.auroc_interval ? small(scoreRange(part.auroc_interval)) : null], {
      value: part.auroc,
      numeric: true,
    });
  const rows = runs.map(run => {
    const { meaning, form } = run.confidence.parts;
    // A run whose 95% intervals reach 0.5 on both parts is not shown to beat chance on either, so its drop says
    // little. The observed scores stay visible.
    const noBetter = part => (part.auroc_interval ? part.auroc_interval[0] <= 0.5 : part.auroc <= 0.5);
    const chance = noBetter(meaning) && noBetter(form);
    const drop = meaning.auroc - form.auroc;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true, withSource: true }),
      aurocCell(meaning),
      aurocCell(form),
      td([signed(drop, 2), chance ? small(CHANCE_BOTH) : null], {
        value: drop,
        numeric: true,
        className: chance ? 'chance' : null,
        title: chance ? `${CHANCE_BOTH} An interval including 0.50 does not prove that the score equals chance.` : null,
      }),
    );
  });
  const reading = data.units.filter(isReading);
  const grammar = data.units.filter(unit => !isReading(unit));
  const topics = units => `topics ${units[0].number} to ${units[units.length - 1].number}`;
  fillTable(
    'parts',
    [
      { label: 'Model and setup' },
      { label: 'Confidence ranking on reading', numeric: true, title: `Reading questions, ${topics(reading)}. The second line is the 95% interval.` },
      { label: 'Confidence ranking on grammar', numeric: true, title: `Grammar questions, ${topics(grammar)}. The second line is the 95% interval.` },
      { label: 'Reading ranking score minus grammar ranking score', numeric: true },
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
        td([formatScore(entry.auroc), entry.auroc_interval ? small(scoreRange(entry.auroc_interval)) : null], {
          value: entry.auroc,
          numeric: true,
        }),
      ),
    ),
  );
  fillTable(
    'sources-table',
    [
      { label: 'Model supplying the score' },
      { label: 'How it supplies the score' },
      { label: 'Confidence ranking (AUROC)', numeric: true, title: `${AUROC_TIP} The second line is the 95% interval.` },
    ],
    rows,
  );
}

function renderVersions(data) {
  const runs = data.runs.filter(run => run.previous);
  const moved = part =>
    `${formatPercent(percent(part.older_correct, part.questions), 1)} → ${formatPercent(percent(part.newer_correct, part.questions), 1)}`;
  const rows = runs.map(run => {
    const { changed, unchanged } = run.previous;
    return el(
      'tr',
      {},
      modelCell(run, { withSetting: true }),
      td(moved(changed), { value: percent(changed.newer_correct - changed.older_correct, changed.questions), numeric: true }),
      td(moved(unchanged), { value: percent(unchanged.newer_correct - unchanged.older_correct, unchanged.questions), numeric: true }),
      td(
        [
          `${integer(unchanged.changed_answer)} of ${integer(unchanged.questions)}`,
          small(formatPercent(percent(unchanged.changed_answer, unchanged.questions), 1)),
        ],
        { value: percent(unchanged.changed_answer, unchanged.questions), numeric: true },
      ),
      unchanged.newer_wrong
        ? td(`${integer(unchanged.repeated_mistakes)} of ${integer(unchanged.newer_wrong)}`, {
            value: percent(unchanged.repeated_mistakes, unchanged.newer_wrong),
            numeric: true,
            title: 'Out of the wrong answers after repair on unchanged questions',
          })
        : emptyCell(EMPTY.notApplicable, { title: 'No wrong answers after repair on unchanged questions' }),
      td(String(run.questions_per_request), { value: run.questions_per_request, numeric: true }),
    );
  });
  const sample = runs[0]?.previous;
  const count = part => (sample ? ` (${integer(sample[part].questions)})` : '');
  const table = fillTable(
    'versions',
    [
      { label: 'Model and setup' },
      {
        label: `Accuracy on questions we corrected${count('changed')}`,
        name: 'Accuracy on questions we corrected',
        numeric: true,
        title: 'Before repair → after repair. Questions whose text or answer key the repair changed.',
      },
      {
        label: `Accuracy on questions we left unchanged${count('unchanged')}`,
        name: 'Accuracy on questions we left unchanged',
        numeric: true,
        title: 'Before repair → after repair. Questions asked the same way both times.',
      },
      { label: 'Unchanged questions that received a different answer', numeric: true },
      {
        label: 'Wrong answers after repair that repeat the earlier choice on unchanged questions',
        name: 'Repeated wrong answers',
        numeric: true,
      },
      { label: 'Questions in each request', numeric: true },
    ],
    rows,
  );
  if (table) addNotes(table, tableNote('Accuracy cells read before repair → after repair. ', CHANGED_ANSWER_NOTE));
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
      td(pointsRange(item.low, item.high), { value: 100 * item.low, numeric: true }),
      td(integer(item.first_only), { value: item.first_only, numeric: true }),
      td(integer(item.second_only), { value: item.second_only, numeric: true }),
      td(formatP(item.p), { value: item.p, numeric: true }),
      td(formatP(item.p_holm), { value: item.p_holm, numeric: true, className: item.p_holm >= 0.05 ? 'muted' : null }),
    ),
  );
  const table = fillTable(
    'paired',
    [
      { label: 'Model A' },
      { label: 'Model B' },
      { label: 'Accuracy of A minus accuracy of B, in percentage points', numeric: true },
      { label: '95% interval for the accuracy difference', numeric: true, title: INTERVAL_TIP },
      { label: 'Only A answered correctly', numeric: true },
      { label: 'Only B answered correctly', numeric: true },
      { label: 'p value', numeric: true, title: 'Exact McNemar test on the questions only one model answered correctly' },
      {
        label: 'p value adjusted for multiple comparisons',
        numeric: true,
        title: `Holm adjustment across the ${integer(data.paired.length)} selected comparisons in this table`,
      },
    ],
    rows,
  );
  if (!table) return;
  // The selected comparisons and the comparison letters adjust over different sets of tests; say so beside the table.
  tableBox(table).before(
    el(
      'p',
      { class: 'table-note lead-note' },
      `These rows use an adjustment across ${integer(data.paired.length)} selected comparisons. `,
      `The comparison letters in the accuracy table use all ${integer(data.group_pairs)} pairs. A pair can pass one adjustment and not the other.`,
    ),
  );
  // The order of the accuracy table, most correct first, among setups in their first format: the report pairs each
  // with the next one down and leaves format reruns (format_of) to the request format table.
  const ranked = data.runs.filter(run => run.format_of == null).sort((a, b) => b.correct - a.correct || a.run - b.run);
  const position = new Map(ranked.map((run, index) => [run.run, index]));
  const neighbours = data.paired.filter(
    item => position.has(item.first) && position.has(item.second) && Math.abs(position.get(item.first) - position.get(item.second)) === 1,
  ).length;
  const reruns = data.runs.length - ranked.length;
  addNotes(
    table,
    tableNote(
      `Rows follow the order of observed accuracy. We compare each setup with the next one down (${integer(neighbours)} pairs). ` +
        `The other ${integer(data.paired.length - neighbours)} selected comparisons sit with the higher-scoring setup of their pair.` +
        (reruns
          ? ` The ${integer(reruns)} setups we asked again with another number of questions per request are not in this order: the request format table compares each with its first run.`
          : ''),
    ),
  );
}

function renderCascade(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const rows = data.cascades.map(item => {
    const first = byRun.get(item.decision);
    const second = byRun.get(item.frontier);
    const unpriced = first.api_equivalent_usd == null;
    const alone = costPer1000(second);
    const threshold = item.in_sample.threshold;
    return el(
      'tr',
      {},
      modelCell(first),
      modelCell(second, { withSetting: true }),
      percentCell(100 * item.held_out.answered),
      td(pointsText(item.held_out.difference, 2), { value: 100 * item.held_out.difference, numeric: true }),
      percentCell(100 * item.held_out.worse, { digits: 0 }),
      td([formatUsd(item.usd_per_1000), unpriced ? small(FIRST_MODEL_UNPRICED[first.billing]) : null], {
        value: item.usd_per_1000,
        numeric: true,
        className: unpriced ? 'wrap' : null,
        title: unpriced ? costTitle(data, first) : null,
      }),
      alone == null ? emptyCell(NO_COST[second.billing] ?? EMPTY.notMeasured) : td(formatUsd(alone), { value: alone, numeric: true }),
      percentCell(100 * item.frontier_accuracy),
      threshold == null
        ? emptyCell(EMPTY.noCutoff)
        : percentCell(100 * item.in_sample.answered, { title: `Confidence cutoff: ${cutoffText(threshold)}` }),
    );
  });
  const table = fillTable(
    'cascade',
    [
      { label: 'Model answering first', title: 'This model answers every question. We keep its answer when its confidence reaches the cutoff.' },
      { label: 'Model answering the rest' },
      {
        label: 'Questions where we keep the first model’s answer',
        numeric: true,
        title: 'Average share of the test half, with the cutoff chosen on the other half',
      },
      { label: 'Accuracy change compared with the second model alone', numeric: true, title: 'Average over the test halves, in percentage points' },
      { label: 'Test splits with lower combined accuracy', numeric: true },
      { label: 'Estimated combined cost per 1,000 questions', numeric: true, title: COST_ESTIMATE_NOTE },
      { label: 'Estimated cost of the second model alone', numeric: true },
      { label: 'Accuracy of the second model alone', numeric: true },
      {
        label: 'Question share when we choose and test the cutoff on the same data',
        numeric: true,
        title: 'The lowest cutoff that keeps the second model’s accuracy, chosen and scored on all questions',
      },
    ],
    rows,
  );
  if (!table) return;
  const splits = data.cascades[0]?.held_out.splits;
  // The live tests with new calls to the second model show what the same-average-cost estimate leaves out.
  const measured = data.pipelines
    .filter(item => item.measured?.cost_usd != null)
    .map(item => {
      const { cost_usd: cost, frontier_cost_usd: alone, decision_cost_usd: first } = item.measured;
      const estimate = first + alone * (1 - item.routed / item.held_out);
      const second = byRun.get(item.frontier);
      return `${byRun.get(item.decision).name} then ${second.name} (${reasoningLabel(second.reasoning)}), ${ruleClause(item)}, ${perRequestText(item.batch_size)} to the second model, cut the cost by ${formatPercent(100 * (1 - cost / alone), 1)}; this estimate method gives ${formatPercent(100 * (1 - estimate / alone), 1)}`;
    });
  addNotes(
    table,
    tableNote(
      `Each value averages ${integer(splits)} test splits. We choose the cutoff on one half and test it on the other. `,
      'Both models’ answers come from storage. ',
      COST_ESTIMATE_NOTE,
      measured.length ? ` Live tests with new calls to the second model: ${measured.join('; ')}.` : null,
    ),
  );

  const doubts = data.doubts.map(item => {
    const tenth = item.top_tenth;
    const found = percent(tenth.with_mistake, tenth.all_with_mistake);
    const floor = Math.round(item.p * (SHUFFLES + 1)) === 1;
    return el(
      'tr',
      {},
      modelCell(byRun.get(item.decision)),
      td(formatScore(item.rho), { value: item.rho, numeric: true }),
      td([formatP(item.p), floor ? small('the smallest possible value') : null], { value: item.p, numeric: true }),
      td(formatScore(item.auroc), { value: item.auroc, numeric: true }),
      td(
        [
          `${integer(tenth.with_mistake)} of ${integer(tenth.all_with_mistake)}`,
          small(formatPercent(found, 0)),
        ],
        { value: found, numeric: true },
      ),
    );
  });
  const stronger = [...new Set(data.doubts.flatMap(item => item.frontier))].map(run => byRun.get(run).name);
  const first = data.doubts[0];
  const tenthShare = first ? formatPercent(percent(first.top_tenth.questions, first.questions), 0) : '';
  fillTable(
    'doubts',
    [
      { label: 'Model and setup' },
      {
        label: 'Does greater uncertainty go with more mistakes? (rank correlation)',
        numeric: true,
        title: `Compares the order of questions by uncertainty with their order by the number of stronger models making a mistake (${stronger.join(', ')}). Values near zero indicate little consistent relationship; a relationship does not establish a cause.`,
      },
      {
        label: 'Shuffle test p value',
        numeric: true,
        title: `Compare with ${integer(SHUFFLES)} shuffles within each topic; the smallest possible reported value is 1/${integer(SHUFFLES + 1)}.`,
      },
      { label: 'How well uncertainty ranks questions with a stronger model mistake above questions without one', numeric: true, title: 'AUROC: 0.50 is chance ranking; 1.00 is perfect ranking.' },
      {
        label: `Mistakes found in the most uncertain ${tenthShare} of questions`,
        name: 'Mistakes found in the most uncertain questions',
        numeric: true,
        title: `Questions on which at least one stronger model made a mistake that fall among the most uncertain ${tenthShare} of questions. Questions chosen at random would hold about ${tenthShare} of them.`,
      },
    ],
    doubts,
  );
}

/* Repeated runs of one setup on the same questions: the whole question set and the smaller sample stay in separate
   groups, because their counts do not compare. */
function renderRepeats(data) {
  const rows = data.repeats.map(item => {
    const mean = (100 * item.accuracy.reduce((sum, value) => sum + value, 0)) / item.accuracy.length;
    const range = `lowest ${formatPercent(100 * Math.min(...item.accuracy))}, highest ${formatPercent(100 * Math.max(...item.accuracy))}`;
    const scored = item.scored > 0;
    const noScores = 'These repeats recorded no confidence scores.';
    return {
      whole: item.whole_bank,
      row: el(
        'tr',
        {},
        modelCell(item, { withSetting: true }),
        td(String(item.questions_per_request), { value: item.questions_per_request, numeric: true }),
        td(integer(item.questions), { value: item.questions, numeric: true }),
        td(String(item.runs.length), { value: item.runs.length, numeric: true }),
        percentCell(mean, { digits: 2, detail: range }),
        td(
          [`${integer(item.changed_answer)} of ${integer(item.questions)}`, small(formatPercent(percent(item.changed_answer, item.questions), 1))],
          { value: percent(item.changed_answer, item.questions), numeric: true },
        ),
        item.wrong_any
          ? td(`${integer(item.wrong_every_run_same)} of ${integer(item.wrong_any)}`, {
              value: percent(item.wrong_every_run_same, item.wrong_any),
              numeric: true,
              title: 'Out of questions answered wrongly at least once',
            })
          : emptyCell(EMPTY.notApplicable, { title: 'No question answered wrongly in any run' }),
        scored
          ? td(`${(100 * item.score_spread_median).toFixed(2)} points`, { value: item.score_spread_median, numeric: true })
          : emptyCell(EMPTY.notMeasured, { title: noScores }),
        scored
          ? td(`${integer(item.score_identical)} of ${integer(item.scored)}`, { value: percent(item.score_identical, item.scored), numeric: true })
          : emptyCell(EMPTY.notMeasured, { title: noScores }),
        scored
          ? td(item.sure_wrong.map(integer).join(', '), { value: Math.max(...item.sure_wrong), numeric: true })
          : emptyCell(EMPTY.notMeasured, { title: noScores }),
        scored
          ? td(integer(item.sure_wrong_every_run), { value: item.sure_wrong_every_run, numeric: true })
          : emptyCell(EMPTY.notMeasured, { title: noScores }),
      ),
    };
  });
  const runCounts = [...new Set(data.repeats.map(item => item.runs.length))];
  const allRuns = runCounts.length === 1 ? `all ${inWords(runCounts[0])} runs` : 'every run';
  const rule = atCutoff(data.sure_threshold);
  const groupLabel = items => {
    const questions = [...new Set(items.map(item => item.questions))];
    const perRequest = [...new Set(items.map(item => item.questions_per_request))];
    const asked = questions.length === 1 ? `${integer(questions[0])} questions` : 'Questions';
    const batch = perRequest.length === 1
      ? perRequest[0] === 1 ? 'one question per request' : `${integer(perRequest[0])} questions per request`
      : null;
    return [asked, batch].filter(Boolean).join(', ');
  };
  const whole = data.repeats.filter(item => item.whole_bank);
  const sample = data.repeats.filter(item => !item.whole_bank);
  const groups = [
    { label: `All ${groupLabel(whole)}`, rows: rows.filter(entry => entry.whole).map(entry => entry.row) },
    { label: `The same ${groupLabel(sample)}`, rows: rows.filter(entry => !entry.whole).map(entry => entry.row) },
  ].filter(group => group.rows.length);
  const table = fillTable(
    'repeats',
    [
      { label: 'Model and setup' },
      { label: 'Questions in each request', numeric: true },
      { label: 'Questions asked', numeric: true, title: 'Asked the same way in every run' },
      { label: 'Times we repeated the test', numeric: true },
      { label: 'Average accuracy, with lowest and highest run', numeric: true },
      { label: 'Questions where the answer changed', numeric: true, title: 'Questions on which the runs did not all choose the same option' },
      {
        label: `Questions with the same wrong answer in ${allRuns}, out of questions answered wrongly at least once`,
        name: `Questions with the same wrong answer in ${allRuns}`,
        numeric: true,
        title: 'Not a share of all questions',
      },
      {
        label: 'Typical change in confidence across repeats',
        numeric: true,
        title: 'For each question, subtract its lowest chosen option score from its highest across repeats. Show the median of those differences, in percentage points.',
      },
      { label: 'Questions with identical confidence in every repeat', numeric: true },
      { label: `Wrong answers at ${rule} in each run`, numeric: true },
      { label: `Questions wrong at ${rule} in every run`, numeric: true },
    ],
    null,
    { groups },
  );
  if (table) addNotes(table, tableNote('Compare the counts within each group, not across the two groups: they use different questions.'));
}

/* The two-step setup run for real: the second model answers, with new calls, only the questions the first model
   does not keep. Rows: the lead replay's first model before the earlier one, then by how the cutoff was set, its
   batched tests before its timed ones, and the second models from the least to the most accurate alone, the order
   the page names them in. */
const PIPELINE_RULES = ['half', 'share', 'cutoff'];
function ruleText(item) {
  if (item.rule === 'share') {
    return item.share === 0.25 ? 'Its most confident quarter of these questions' : `Its most confident ${formatPercent(100 * item.share)} of these questions`;
  }
  return item.rule === 'cutoff' ? `Fixed at ${cutoffText(item.threshold)} before the test` : 'Chosen on the other half';
}
/* The rule inside a sentence: "cutoff chosen on the other half", "keeping its most confident quarter of these questions". */
function ruleClause(item) {
  const text = ruleText(item);
  return `${item.rule === 'share' ? 'keeping' : 'cutoff'} ${text.charAt(0).toLowerCase()}${text.slice(1)}`;
}
/* "1 question per request", "16 questions per request": the request format each live test names. */
function perRequestText(count) {
  return `${integer(count)} ${count === 1 ? 'question' : 'questions'} per request`;
}
function renderPipelines(data) {
  const byRun = new Map(data.runs.map(run => [run.run, run]));
  const sorted = [...data.pipelines].sort(
    (a, b) =>
      (b.decision === data.replay.decision) - (a.decision === data.replay.decision) ||
      PIPELINE_RULES.indexOf(a.rule) - PIPELINE_RULES.indexOf(b.rule) ||
      b.batch_size - a.batch_size ||
      byRun.get(a.frontier).accuracy - byRun.get(b.frontier).accuracy,
  );
  const rows = sorted.map(item => {
    const measured = item.measured;
    const perThousand = usd => formatUsd((1000 * usd) / item.held_out);
    return el(
      'tr',
      {},
      modelCell(byRun.get(item.decision)),
      modelCell(byRun.get(item.frontier), { withSetting: true }),
      td(ruleText(item), { className: 'wrap' }),
      td(integer(item.batch_size), { value: item.batch_size, numeric: true }),
      td(integer(item.held_out), { value: item.held_out, numeric: true }),
      td(cutoffText(item.threshold), { value: item.threshold, numeric: true, title: `Confidence cutoff: ${cutoffText(item.threshold)}` }),
      percentCell(percent(item.routed, item.held_out), { detail: `${integer(item.routed)} questions` }),
      percentCell(100 * item.simulated.accuracy, {
        detail: `second model alone: ${formatPercent(100 * item.simulated.frontier_accuracy)}`,
      }),
      measured
        ? percentCell(100 * measured.accuracy, { detail: `second model alone: ${formatPercent(100 * measured.frontier_accuracy)}` })
        : emptyCell(EMPTY.noNewCalls),
      measured
        ? td([pointsText(measured.difference), small(`95% interval: ${pointsRange(measured.low, measured.high)}`)], {
            value: 100 * measured.difference,
            numeric: true,
          })
        : emptyCell(EMPTY.noNewCalls),
      measured ? td(formatP(measured.p), { value: measured.p, numeric: true }) : emptyCell(EMPTY.noNewCalls),
      td(
        [
          `${item.tolerance_points.toFixed(1)} points`,
          measured
            ? small(
                measured.within_tolerance
                  ? 'Observed loss below the chosen limit. The uncertainty interval may still allow a larger loss.'
                  : 'Observed loss above the chosen limit.',
              )
            : null,
        ],
        { value: item.tolerance_points, numeric: true, className: 'wrap' },
      ),
      measured
        ? td([`Combined cost ${perThousand(measured.cost_usd)}`, small(`second model alone ${perThousand(measured.frontier_cost_usd)}`)], {
            value: (1000 * measured.cost_usd) / item.held_out,
            numeric: true,
          })
        : emptyCell(EMPTY.noNewCalls),
      measured
        ? td([`Combined ${minutes(measured.request_seconds)}`, small(`second model alone ${minutes(measured.frontier_request_seconds)}`)], {
            value: measured.request_seconds,
            numeric: true,
          })
        : emptyCell(EMPTY.noNewCalls),
    );
  });
  const table = fillTable(
    'pipelines',
    [
      { label: 'Model answering first' },
      { label: 'Model answering the rest' },
      { label: 'How we set the cutoff' },
      { label: 'Second model’s questions per request', numeric: true, title: 'The second model’s questions in each request; one question per request times each question’s wait' },
      { label: 'Questions reserved for testing', numeric: true, title: 'The half of the questions the cutoff was not chosen on', extra: true },
      { label: 'Confidence cutoff chosen before this test', numeric: true, title: 'Fixed before the test', extra: true },
      { label: 'Final answers supplied by the first model', numeric: true },
      { label: 'Accuracy using recorded answers from both models', numeric: true, extra: true },
      { label: 'Accuracy with new answers from the second model', numeric: true },
      { label: 'Accuracy change compared with the second model alone', numeric: true, title: `In percentage points, with the 95% interval. ${INTERVAL_TIP}` },
      { label: 'p value', numeric: true, title: 'Exact McNemar test' },
      { label: 'Accuracy loss allowed before the test', numeric: true, extra: true },
      { label: 'Estimated cost per 1,000 questions', numeric: true, title: PRICE_BASIS },
      { label: 'Total time: combined process / second model alone', name: 'Total time', numeric: true, extra: true },
    ],
    rows,
  );
  if (!table) return;
  addColumnToggle(table);
  // Cheaper setups run alone on the same test questions (the tests share one test half), leaving out the runs that
  // already appear as a test's second model alone.
  const secondAlone = new Set(data.pipelines.map(item => item.measured?.alone_run).filter(Boolean));
  const alternatives = new Map();
  for (const item of data.pipelines) {
    for (const alternative of item.measured?.alternatives ?? []) {
      if (!secondAlone.has(alternative.run)) alternatives.set(alternative.run, alternative);
    }
  }
  if (alternatives.size) {
    const heldOut = data.pipelines[0].held_out;
    const listed = [...alternatives.values()].map(
      item =>
        `${item.name}${item.reasoning ? ` (${reasoningLabel(item.reasoning)})` : ''}: ${formatPercent(100 * item.accuracy)} correct, ${formatUsd((1000 * item.cost_usd) / heldOut)} per 1,000 questions`,
    );
    addNotes(table, tableNote(`On the same ${integer(heldOut)} test questions, we also ran cheaper setups alone. ${listed.join('; ')}.`));
  }
}

/* The colour theme switch in the header. The script in <head> has already applied a stored choice. Storage can be
   blocked, so each access is guarded and a choice then lasts for the visit. Buttons are found by data-theme-choice,
   never by their text. */
function setUpThemeSwitch() {
  const group = document.querySelector('.theme-switch');
  if (!group) return;
  const root = document.documentElement;
  const show = theme => {
    root.dataset.theme = theme;
    for (const button of group.querySelectorAll('button[data-theme-choice]')) {
      button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme));
    }
  };
  group.addEventListener('click', event => {
    const button = event.target.closest('button[data-theme-choice]');
    if (!button) return;
    show(button.dataset.themeChoice);
    try {
      localStorage.setItem('theme', button.dataset.themeChoice);
    } catch {
      // Storage blocked: the theme applies until the page is left.
    }
  });
  show(root.dataset.theme === 'light' ? 'light' : 'dark');
  group.hidden = false;
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function showLoadError(error) {
  const message = el(
    'div',
    { class: 'load-error', role: 'alert' },
    el('p', {}, 'The detailed results did not load. Reload the page or ', el('a', { href: 'results.json', text: 'download the results file' }), '.'),
    el('details', {}, el('summary', { text: 'Technical details' }), el('code', { text: String(error?.message ?? error) })),
  );
  (document.querySelector('main') ?? document.body).prepend(message);
}

/* A setup that also ran with another number of questions per request (results.json format_of): both of its runs name
   their request size, so that every table shows which run is which. */
function markFormats(runs) {
  const bases = new Set(runs.filter(run => run.format_of != null).map(run => run.format_of));
  for (const run of runs) {
    if (run.format_of != null || bases.has(run.run)) run.format = perRequestText(run.questions_per_request);
  }
}

async function main() {
  let data;
  let config;
  try {
    // page_config.json holds which providers count as decision models, the rule build_page.py uses.
    [data, config] = await Promise.all([fetchJson('results.json'), fetchJson('page_config.json')]);
  } catch (error) {
    showLoadError(error);
    return;
  }
  markFormats(data.runs);
  renderLeaderboard(data, config);
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

setUpThemeSwitch();
main();
