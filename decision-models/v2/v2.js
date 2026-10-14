'use strict';

/* The v2 home page: filters, the four leaderboard tabs and the two charts, drawn from ../results.json. Every number
   is read from it; accuracy for a part or topic and its 95% interval are computed here from the counts it stores
   (runs[].groups and runs[].units), with the Wilson formula. Without JavaScript the page keeps the plain table that
   build_v2.py writes. */

const SETTINGS = JSON.parse(document.getElementById('v2-settings').textContent);
const RESULTS_URL = '../results.json';

/* Why a cell has no value. */
const EMPTY = {
  notMeasured: 'Not measured',
  allOnly: 'Computed on all questions only',
};
const INTERVAL_TIP = 'To test two setups against each other, use Compare.';
const LATENCY_TIP =
  'Latency: the time from sending one request to receiving its answer, measured from our computer, network and retries included. Median request.';
const COST_TIP = 'Estimated from API prices and recorded token use, per 1,000 questions.';
const AUROC_TIP = 'ranking score';
const SHARE_TIP = 'Share of questions taken: at 16 questions per request, a call still goes out for the rest.';
const UNPRICED_FIRST = {
  local: 'Leaves out the first model’s hardware cost, which we have not estimated.',
  free: 'The first model used a free tier; this assumes no charge for it.',
};
const CONFIDENCE_NOTE = [
  'Every decision model that ranks its answers better than chance ranks them less well on grammar than on reading. A probability from an API is not calibrated by itself. Luna’s two setups also differ in request format (1 against 16 questions).',
];
const ROUTING_NOTES = [
  'Replay: both models’ recorded answers. Live: the decision model’s recorded answers, with new calls to the LLM. Savings are estimates from API prices, and larger at 1 question per request: each question the LLM skips costs more.',
  'In a live test with Sonnet at 1 question per request, accuracy fell 4.73 points: Decider kept 51%, with a cutoff chosen at 16 per request. A cutoff chosen at 1 per request keeps 29%, and accuracy falls 0.16 points (replay). Choose the cutoff in the format you will run.',
  'SubQ Snap’s place depends on the LLM: second among decision models in front of Sonnet (16 per request), about fifth in front of Opus and Astra. Its most confident fifth of answers was 98.6% right; Decider v1.1’s was 99.3%, GLiDE’s 99.5%.',
];
const STABILITY_NOTE = [
  'Only the setups we repeated, five times each. Decision models and two Qwen3.8-27B setups were repeated on all questions; the other chat models on a sample of 200.',
];
/* Each rule's name in the page URL ("slug"), its label, and its name among the live tests in results.json. */
const ROUTE_RULES = [
  { key: 'half', slug: 'half', label: 'cutoff chosen on half the questions', live: 'half' },
  { key: 'sure', slug: 'fixed-99', label: 'fixed 99%', live: 'cutoff' },
  { key: 'share', slug: 'quarter', label: 'most confident quarter', live: 'share' },
];
const ROUTE_TESTS = ['replay', 'live'];
const PHONE = window.matchMedia('(max-width: 640px)');

/* ---- Numbers ---- */

const integer = n => n.toLocaleString('en-US');
const pct = (fraction, digits = 1) => `${(100 * fraction).toFixed(digits)}%`;
const signedPoints = fraction => {
  const text = Math.abs(100 * fraction).toFixed(2);
  return Number(text) === 0 ? `${text} points` : `${fraction > 0 ? '+' : '−'}${text} points`;
};
const usd = value => {
  if (value >= 0.1 || value === 0) return `$${value.toFixed(2)}`;
  const text = value.toFixed(3);
  return text === '0.000' ? `$${value.toPrecision(2)}` : `$${text}`;
};
const duration = seconds =>
  seconds < 1 ? `${Math.round(1000 * seconds)}\u00a0ms` : `${seconds.toFixed(seconds < 10 ? 2 : 1)}\u00a0s`;

/* 95% Wilson score interval, as benchmark_metrics.wilson_interval. */
function wilson(correct, total, z = 1.96) {
  if (!total) return null;
  const share = correct / total;
  const denominator = 1 + (z * z) / total;
  const centre = (share + (z * z) / (2 * total)) / denominator;
  const margin = (z * Math.sqrt((share * (1 - share)) / total + (z * z) / (4 * total * total))) / denominator;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

const esc = text =>
  String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
const tip = (text, content = '—') => `<span class="hint" tabindex="0" data-tip="${esc(text)}">${content}</span>`;

/* ---- Runs ---- */

const reasoningLabel = reasoning => (['off', 'on'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
const requestSize = size => `${integer(size)} question${size === 1 ? '' : 's'} per request`;
const runDetail = run =>
  [run.variant, run.reasoning && reasoningLabel(run.reasoning), requestSize(run.questions_per_request)].filter(Boolean).join(' · ');
const isDecision = run => SETTINGS.decisionProviders.includes(run.provider) && !SETTINGS.notDecisionModels.includes(run.model);
const costPer1000 = run => (run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / run.answered_questions);
const latencyOf = run => run.latency?.median_request_seconds ?? null;

let data;
let byId;
/* Chart labels: a setup's short name (page_config.json's short_names) and variant, with its reasoning or request size
   only where another setup in the same chart has the same name, so the default chart reads "GPT-6 Astra" and
   "Show all" tells its two setups apart. */
function chartLabels(runs) {
  const name = run => SETTINGS.shortNames[run.model] ?? run.name;
  const base = run => (run.variant ? `${name(run)} (${run.variant})` : name(run));
  const labels = new Map();
  runs.forEach(run => {
    const same = runs.filter(other => base(other) === base(run));
    const differs = field => new Set(same.map(other => other[field])).size > 1;
    const details = [
      differs('reasoning') && run.reasoning && reasoningLabel(run.reasoning),
      differs('questions_per_request') && `${run.questions_per_request}/request`,
    ].filter(Boolean);
    labels.set(run, details.length ? `${base(run)} · ${details.join(', ')}` : base(run));
  });
  return labels;
}
const NO_SETUP = '<p class="note">No setup matches these filters.</p>';

const state = {
  part: 'all',
  topic: null,
  type: 'all',
  qpr: 'all',
  picked: new Set(),
  tab: 'accuracy',
  sort: { key: 'accuracy', descending: true },
  route: { llm: 'opus', qpr: 1, rule: 'half', mode: 'replay' },
  measure: 'accuracy',
  across: 'cost',
  showAll: false,
};

const units = () => data.units;
const unitPart = unit => (SETTINGS.readingUnits.includes(unit.number) ? 'reading' : 'grammar');

/* Correct answers and questions for a run under the part and topic filters. */
function counts(run) {
  if (state.topic != null) {
    const index = units().findIndex(unit => unit.number === state.topic);
    return { correct: run.units[index], questions: units()[index].questions };
  }
  if (state.part !== 'all') return run.groups[state.part];
  const { reading, grammar } = run.groups;
  return { correct: reading.correct + grammar.correct, questions: reading.questions + grammar.questions };
}
const accuracyOf = run => {
  const { correct, questions } = counts(run);
  return correct / questions;
};
const overallAccuracy = run => (run.groups.reading.correct + run.groups.grammar.correct) / (run.groups.reading.questions + run.groups.grammar.questions);
function questionsInFilter() {
  if (state.topic != null) return units().find(unit => unit.number === state.topic).questions;
  if (state.part !== 'all') return data.runs[0].groups[state.part].questions;
  return data.questions;
}
const filtered = () => state.part !== 'all' || state.topic != null;

function visibleRuns() {
  return data.runs.filter(
    run =>
      (state.type === 'all' || (state.type === 'decision') === isDecision(run)) &&
      (state.qpr === 'all' || run.questions_per_request === state.qpr) &&
      (!state.picked.size || state.picked.has(run.run)),
  );
}

/* ---- Leaderboard ---- */

const modelCell = run =>
  `<td class="model"><a class="model-name" href="models/${run.run}/">${esc(run.name)}</a><span class="small">${esc(runDetail(run))}</span></td>`;
const numCell = (label, html) => `<td class="num" data-label="${esc(label)}">${html}</td>`;

function accuracyCell(run) {
  const { correct, questions } = counts(run);
  const [low, high] = wilson(correct, questions);
  return `${pct(correct / questions)}<span class="small">${pct(low)} to ${pct(high)}</span>`;
}

/* Each tab's columns: label, header tooltip, the value it sorts by (null sorts last), and the cell. "low" marks the
   columns where a lower value is better, so their first click sorts upwards. */
const TABS = {
  accuracy: {
    rows: () => visibleRuns().map(run => ({ run })),
    columns: [
      { key: 'accuracy', label: 'Accuracy', tip: INTERVAL_TIP, value: accuracyOf, cell: accuracyCell },
      {
        key: 'reading', label: 'Reading', className: 'reading',
        value: run => run.groups.reading.correct / run.groups.reading.questions,
        cell: run => pct(run.groups.reading.correct / run.groups.reading.questions),
      },
      {
        key: 'grammar', label: 'Grammar', className: 'grammar',
        value: run => run.groups.grammar.correct / run.groups.grammar.questions,
        cell: run => pct(run.groups.grammar.correct / run.groups.grammar.questions),
      },
      {
        key: 'latency', label: 'Latency', tip: LATENCY_TIP, low: true, value: latencyOf,
        cell: run => (latencyOf(run) == null ? tip(EMPTY.notMeasured) : duration(latencyOf(run))),
      },
      {
        key: 'cost', label: '$ per 1,000', tip: COST_TIP, low: true, value: costPer1000,
        cell: run => (costPer1000(run) == null ? tip(EMPTY.notMeasured) : usd(costPer1000(run))),
      },
    ],
  },
  confidence: {
    rows: () => visibleRuns().map(run => ({ run })),
    note: CONFIDENCE_NOTE,
    columns: [
      {
        key: 'kept', label: `Kept at ${pct(SETTINGS.threshold, 0)} (wrong)`,
        value: run => (filtered() ? null : run.confidence.sure.questions),
        cell: run => {
          if (filtered()) return tip(EMPTY.allOnly);
          const { questions, correct } = run.confidence.sure;
          return `${integer(questions)} (${integer(questions - correct)})`;
        },
      },
      {
        key: 'gap', label: 'Calibration gap', low: true,
        value: run => (filtered() ? null : run.confidence.ece),
        cell: run => (filtered() ? tip(EMPTY.allOnly) : `${(100 * run.confidence.ece).toFixed(1)} points`),
      },
      aurocColumn('reading', 'meaning', 'AUROC reading'),
      aurocColumn('grammar', 'form', 'AUROC grammar'),
    ],
  },
  routing: { rows: () => routingRows(), notes: ROUTING_NOTES },
  stability: {
    rows: () => {
      const shown = new Set(visibleRuns());
      return data.repeats.map(item => ({ item, run: repeatRun(item) })).filter(({ run }) => run && shown.has(run));
    },
    note: STABILITY_NOTE,
    columns: [
      {
        key: 'changed', label: 'Answers changed in 5 runs', low: true,
        value: row => (filtered() ? null : row.item.changed_answer / row.item.questions),
        cell: row => (filtered() ? tip(EMPTY.allOnly) : `${integer(row.item.changed_answer)} of ${integer(row.item.questions)}`),
      },
      {
        key: 'same-wrong', label: 'Same wrong answer in all 5', low: true,
        value: row => (filtered() ? null : row.item.wrong_every_run_same / row.item.questions),
        cell: row => (filtered() ? tip(EMPTY.allOnly) : `${integer(row.item.wrong_every_run_same)} of ${integer(row.item.questions)}`),
      },
    ],
  },
};

/* The Accuracy and Confidence columns read a run; their rows are { run }, as in the Routing and Stability tabs. */
for (const name of ['accuracy', 'confidence']) {
  TABS[name].columns = TABS[name].columns.map(column => ({ ...column, value: row => column.value(row.run), cell: row => column.cell(row.run) }));
}

/* AUROC exists for all questions and for each part, not for a topic. */
function aurocColumn(part, stored, label) {
  const available = () => state.topic == null && (state.part === 'all' || state.part === part);
  return {
    key: `auroc-${part}`, label, tip: AUROC_TIP, className: part,
    value: run => (available() ? run.confidence.parts[stored].auroc : null),
    cell: run => (available() ? run.confidence.parts[stored].auroc.toFixed(2) : tip(EMPTY.allOnly)),
  };
}

const repeatRun = item =>
  data.runs.find(
    run =>
      run.provider === item.provider && run.model === item.model && run.reasoning === item.reasoning &&
      run.variant === item.variant && run.questions_per_request === item.questions_per_request,
  );

/* ---- Routing ---- */

const routeLlm = () => SETTINGS.routeLlms.find(llm => llm.key === state.route.llm);
const routeRule = () => ROUTE_RULES.find(rule => rule.key === state.route.rule);

/* The numbers measured for the chosen LLM, request size, rule and test, for one first model; null where that exact
   choice was not measured. */
function routeNumbers(first) {
  const { qpr, mode } = state.route;
  const llm = routeLlm();
  const frontier = byId.get(llm.runs[qpr]);
  if (mode === 'live') {
    const test = data.pipelines.find(
      item =>
        item.decision === first.run && item.frontier === llm.runs['16'] && item.batch_size === qpr &&
        item.rule === routeRule().live && item.measured,
    );
    if (!test) return null;
    const { measured } = test;
    return {
      share: test.routed / test.held_out,
      change: measured.difference,
      saving: 1 - measured.cost_usd / measured.frontier_cost_usd,
      savingUsd: (1000 * (measured.frontier_cost_usd - measured.cost_usd)) / test.held_out,
    };
  }
  const alone = costPer1000(frontier);
  let numbers = null;
  if (state.route.rule === 'half') {
    const item = data.cascades.find(cascade => cascade.decision === first.run && cascade.frontier === frontier.run);
    if (item) numbers = { share: item.held_out.answered, change: item.held_out.difference, perThousand: item.usd_per_1000 };
  } else if (first.run === data.replay.decision) {
    const item = data.replay.frontiers.find(entry => entry.frontier === frontier.run)?.[state.route.rule];
    if (item) numbers = { share: item.kept / data.replay.questions, change: item.difference, perThousand: item.usd_per_1000 };
  }
  if (!numbers || alone == null) return numbers && { ...numbers, saving: null, savingUsd: null };
  return { ...numbers, saving: 1 - numbers.perThousand / alone, savingUsd: alone - numbers.perThousand };
}

function routingRows() {
  const first = new Set(data.cascades.map(item => item.decision));
  const shown = new Set(visibleRuns());
  return data.runs.filter(run => first.has(run.run) && shown.has(run)).map(run => ({ run, numbers: routeNumbers(run) }));
}

function routeTitle() {
  const llm = byId.get(routeLlm().runs[state.route.qpr]);
  return [llm.name, requestSize(state.route.qpr), routeRule().label, state.route.mode].join(' · ');
}

const ROUTING_COLUMNS = [
  { key: 'share', label: 'Share of the LLM’s questions taken', tip: SHARE_TIP, value: row => row.numbers?.share ?? null,
    cell: row => (row.numbers ? pct(row.numbers.share) : tip(EMPTY.notMeasured)) },
  { key: 'change', label: 'Accuracy change', value: row => row.numbers?.change ?? null,
    cell: row => (row.numbers ? signedPoints(row.numbers.change) : tip(EMPTY.notMeasured)) },
  { key: 'saving', label: 'Saving %', value: row => row.numbers?.saving ?? null, cell: row => savingCell(row, n => pct(n.saving, 0)) },
  { key: 'saving-usd', label: 'Saving $ per 1,000', value: row => row.numbers?.savingUsd ?? null,
    cell: row => savingCell(row, n => usd(n.savingUsd)) },
];
TABS.routing.columns = ROUTING_COLUMNS;

function savingCell(row, format) {
  if (!row.numbers || row.numbers.saving == null) return tip(EMPTY.notMeasured);
  const caveat = UNPRICED_FIRST[row.run.billing];
  return caveat ? tip(caveat, format(row.numbers)) : format(row.numbers);
}

/* ---- Rendering the leaderboard ---- */

function sortRows(rows, columns) {
  const { key, descending } = state.sort;
  const column = columns.find(item => item.key === key);
  /* The Routing tab ignores the part and topic filters, so it orders by accuracy on all questions. */
  const fallback = state.tab === 'routing' ? overallAccuracy : accuracyOf;
  const value = column ? row => column.value(row) : row => fallback(row.run);
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    return descending ? y - x : x - y;
  });
}

function renderBoard() {
  const tab = TABS[state.tab];
  const rows = sortRows(tab.rows(), tab.columns);
  const runOf = row => row.run;
  const headers = tab.columns
    .map(column => {
      const sorted = state.sort.key === column.key;
      const aria = sorted ? ` aria-sort="${state.sort.descending ? 'descending' : 'ascending'}"` : '';
      const label = column.tip ? tip(column.tip, esc(column.label)) : esc(column.label);
      return `<th scope="col" class="num ${column.className ?? ''}"${aria}><button type="button" data-sort="${column.key}">${label}</button></th>`;
    })
    .join('');
  const body = rows
    .map(row => `<tr>${modelCell(runOf(row))}${tab.columns.map(column => numCell(column.label, column.cell(row))).join('')}</tr>`)
    .join('');
  const empty = rows.length ? '' : `<p class="note">No setup matches these filters.</p>`;
  const title =
    state.tab === 'routing'
      ? `<h3 class="tab-title">Can a cheap model go first?</h3>${routingControls()}<p class="table-title">${esc(routeTitle())}</p><p class="scope">All ${integer(data.questions)} questions</p>`
      : '';
  const notes = (tab.notes ?? tab.note ?? []).map(text => `<p>${esc(text)}</p>`).join('');
  document.getElementById('board').innerHTML =
    `${title}${sortSelect(tab.columns)}<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Model</th>${headers}</tr></thead><tbody>${body}</tbody></table></div>${empty}` +
    (notes ? `<div class="tab-notes">${notes}</div>` : '');
  document.getElementById('board').setAttribute('aria-labelledby', `tab-${state.tab}`);
}

/* Phones show the table as a list without headers; this menu sorts it instead. */
function sortSelect(columns) {
  const options = [['', 'Accuracy'], ...columns.filter(column => column.key !== 'accuracy').map(column => [column.key, column.label])]
    .map(([key, label]) => `<option value="${key}"${(state.sort.key === key || (!key && state.sort.key === 'accuracy')) ? ' selected' : ''}>${esc(label)}</option>`)
    .join('');
  return `<label class="phone-sort">Sort by <select data-control="phone-sort">${options}</select></label>`;
}

function segmented(name, options, current) {
  return options
    .map(
      ([value, label]) =>
        `<button type="button" data-${name}="${value}" aria-pressed="${String(value) === String(current)}">${esc(label)}</button>`,
    )
    .join('');
}

function routingControls() {
  const { llm, qpr, rule, mode } = state.route;
  return (
    '<div class="route-controls">' +
    `<div class="control" role="group" aria-label="LLM">${segmented('route-llm', SETTINGS.routeLlms.map(item => [item.key, item.label]), llm)}</div>` +
    `<div class="control" role="group" aria-label="Questions per request">${segmented('route-qpr', [[1, '1 per request'], [16, '16 per request']], qpr)}</div>` +
    `<label class="control">Rule <select data-control="route-rule">${ROUTE_RULES.map(item => `<option value="${item.key}"${item.key === rule ? ' selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label>` +
    `<div class="control" role="group" aria-label="Test">${segmented('route-mode', [['replay', 'Replay'], ['live', 'Live']], mode)}</div>` +
    '</div>'
  );
}

/* ---- Filters ---- */

function renderFilters() {
  const set = (name, html) => (document.querySelector(`[data-control="${name}"]`).innerHTML = html);
  set('part', segmented('part', [['all', 'All'], ['reading', 'Reading'], ['grammar', 'Grammar']], state.part));
  set('type', segmented('type', [['all', 'All models'], ['decision', 'Decision'], ['chat', 'Chat']], state.type));
  set('qpr', segmented('qpr', [['all', 'Any request size'], [1, '1 per request'], [16, '16 per request']], state.qpr));
  const topics = units().filter(unit => state.part === 'all' || unitPart(unit) === state.part);
  const group = part =>
    topics
      .filter(unit => unitPart(unit) === part)
      .map(unit => `<option value="${unit.number}"${unit.number === state.topic ? ' selected' : ''}>${esc(unit.english)}</option>`)
      .join('');
  const groups = ['reading', 'grammar']
    .map(part => [part, group(part)])
    .filter(([, html]) => html)
    .map(([part, html]) => `<optgroup label="${part === 'reading' ? 'Reading' : 'Grammar'}">${html}</optgroup>`)
    .join('');
  set('topic', `<option value="">All topics</option>${groups}`);
  const text = `${integer(questionsInFilter())} questions`;
  document.querySelectorAll('[data-count]').forEach(node => (node.textContent = text));
  const picker = document.querySelector('[data-control="picker"]');
  picker.querySelector('summary').textContent = state.picked.size ? `Models (${state.picked.size})` : 'Models';
}

function renderPicker() {
  const list = document.querySelector('.picker-list');
  const group = (title, runs) =>
    `<fieldset><legend>${title}</legend>${runs
      .map(
        run =>
          `<label><input type="checkbox" value="${run.run}"${state.picked.has(run.run) ? ' checked' : ''}> ${esc(run.name)} <span class="muted">${esc(runDetail(run))}</span></label>`,
      )
      .join('')}</fieldset>`;
  const sorted = [...data.runs].sort((a, b) => overallAccuracy(b) - overallAccuracy(a));
  list.innerHTML =
    `<button type="button" class="show-all" data-control="clear-picked">Clear</button>` +
    group('Decision models', sorted.filter(isDecision)) +
    group('Chat models', sorted.filter(run => !isDecision(run)));
}

/* ---- Charts ---- */

/* The setups the charts show: by default the decision models with the highest accuracy and the routing LLMs at one
   question per request; "Show all" and the model picker add the rest. The type and request-size filters apply. */
function chartRuns() {
  let runs;
  if (state.showAll) runs = data.runs;
  else {
    const decision = [...data.runs].filter(isDecision).sort((a, b) => overallAccuracy(b) - overallAccuracy(a));
    const llms = SETTINGS.routeLlms.map(llm => byId.get(llm.runs['1']));
    const chosen = new Set([...decision.slice(0, SETTINGS.chartDecisionModels), ...llms, ...[...state.picked].map(id => byId.get(id))]);
    runs = data.runs.filter(run => chosen.has(run));
  }
  return runs.filter(
    run =>
      (state.type === 'all' || (state.type === 'decision') === isDecision(run)) &&
      (state.qpr === 'all' || run.questions_per_request === state.qpr),
  );
}

const MEASURES = {
  accuracy: { label: 'Accuracy', value: run => accuracyOf(run), log: false, format: value => pct(value), higher: true },
  latency: { label: 'Latency', value: latencyOf, log: true, format: duration, higher: false },
  cost: { label: 'Cost', value: costPer1000, log: true, format: usd, higher: false },
};

const ticksLog = (low, high) => {
  const ticks = [];
  for (let power = Math.floor(Math.log10(low)); power <= Math.ceil(Math.log10(high)); power++) {
    const value = 10 ** power;
    if (value >= low && value <= high) ticks.push(value);
  }
  return ticks;
};
const logTick = (measure, value) => {
  if (measure === 'cost') return value < 1 ? `$${value}` : `$${integer(value)}`;
  return value < 1 ? `${Math.round(1000 * value)}\u00a0ms` : `${integer(value)}\u00a0s`;
};
/* Chart text is 12px in the page's font; labels are measured with it, so they fit their space and do not overlap. */
const measurer = document.createElement('canvas').getContext('2d');
function textWidth(text) {
  measurer.font = `12px ${getComputedStyle(document.body).fontFamily}`;
  return measurer.measureText(text).width;
}
function truncate(text, width) {
  if (textWidth(text) <= width) return text;
  let cut = text;
  while (cut.length > 1 && textWidth(`${cut}…`) > width) cut = cut.slice(0, -1);
  return `${cut.trimEnd()}…`;
}

function scale(domain, range, log) {
  const [d0, d1] = log ? domain.map(Math.log10) : domain;
  return value => range[0] + (((log ? Math.log10(value) : value) - d0) / (d1 - d0)) * (range[1] - range[0]);
}

function barChart(box) {
  const measure = MEASURES[state.measure];
  const runs = chartRuns();
  if (!runs.some(run => measure.value(run) != null)) {
    box.innerHTML = NO_SETUP;
    return;
  }
  const labels = chartLabels(runs);
  const known = runs.filter(run => measure.value(run) != null);
  const missing = runs.filter(run => measure.value(run) == null);
  known.sort((a, b) => (measure.higher ? measure.value(b) - measure.value(a) : measure.value(a) - measure.value(b)));
  const width = box.clientWidth;
  const phone = PHONE.matches;
  const row = phone ? 20 : 24;
  const labelWidth = Math.min(phone ? 150 : 230, Math.round(width * 0.42));
  const valueWidth = 64;
  const top = 6;
  const axis = 24;
  const ordered = [...known, ...missing];
  const height = top + ordered.length * row + axis;
  const values = known.map(measure.value);
  const domain = measure.log
    ? [Math.min(...values) / 1.5, Math.max(...values) * 1.5]
    : [0, 1];
  const x = scale(domain, [labelWidth + 8, width - valueWidth], measure.log);
  const ticks = measure.log ? ticksLog(...domain) : [0, 0.25, 0.5, 0.75, 1];
  const parts = ticks.map(value => {
    const position = x(value);
    return `<line class="grid" x1="${position}" x2="${position}" y1="${top}" y2="${height - axis}"/>` +
      `<text class="tick" x="${position}" y="${height - 6}" text-anchor="middle">${measure.log ? logTick(state.measure, value) : pct(value, 0)}</text>`;
  });
  ordered.forEach((run, index) => {
    const y = top + index * row;
    const name = labels.get(run);
    parts.push(`<text class="label" x="${labelWidth}" y="${y + row / 2 + 4}" text-anchor="end"><title>${esc(`${run.name} · ${runDetail(run)}`)}</title>${esc(truncate(name, labelWidth))}</text>`);
    const value = measure.value(run);
    if (value == null) {
      parts.push(`<text class="value muted" x="${labelWidth + 8}" y="${y + row / 2 + 4}">${EMPTY.notMeasured}</text>`);
      return;
    }
    const end = x(value);
    const start = x(domain[0]);
    parts.push(`<rect class="${isDecision(run) ? 'bar-decision' : 'bar-chat'}" x="${start}" y="${y + 3}" width="${Math.max(1, end - start)}" height="${row - 6}" rx="2"><title>${esc(`${run.name} · ${runDetail(run)}: ${measure.format(value)}`)}</title></rect>`);
    if (state.measure === 'accuracy') {
      const { correct, questions } = counts(run);
      const [low, high] = wilson(correct, questions);
      parts.push(`<line class="whisker" x1="${x(low)}" x2="${x(high)}" y1="${y + row / 2}" y2="${y + row / 2}"/>`);
    }
    parts.push(`<text class="value" x="${end + 6}" y="${y + row / 2 + 4}">${measure.format(value)}</text>`);
  });
  const scaleNote = measure.log ? ' Log scale.' : ' Lines: 95% interval.';
  box.innerHTML =
    `<div class="chart-scroll" style="--chart-max:${phone ? 300 : 360}px"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`Bar chart of ${measure.label.toLowerCase()} for ${ordered.length} setups.${scaleNote}`)}">${parts.join('')}</svg></div>` +
    legend(`${measure.label}${state.measure === 'cost' ? ' per 1,000 questions' : state.measure === 'latency' ? ' per request' : ` on ${integer(questionsInFilter())} questions`}.${scaleNote}`);
}

function scatterChart(box) {
  const across = MEASURES[state.across];
  const runs = chartRuns();
  if (!runs.some(run => across.value(run) != null)) {
    box.innerHTML = NO_SETUP;
    return;
  }
  const labels = chartLabels(runs);
  const known = runs.filter(run => across.value(run) != null);
  const missing = runs.length - known.length;
  const width = box.clientWidth;
  const phone = PHONE.matches;
  const pad = { left: 46, right: 12, top: 12, bottom: 30 };
  /* The box keeps its height; with more setups than fit, the chart grows taller and scrolls inside it. */
  const height = Math.max(phone ? 300 : 360, (phone ? 18 : 24) * known.length + pad.top + pad.bottom);
  const xs = known.map(across.value);
  const ys = known.map(accuracyOf);
  const xDomain = [Math.min(...xs) / 1.6, Math.max(...xs) * 1.6];
  const yDomain = [Math.max(0, Math.floor((Math.min(...ys) - 0.05) * 10) / 10), 1];
  const x = scale(xDomain, [pad.left, width - pad.right], true);
  const y = scale(yDomain, [height - pad.bottom, pad.top], false);
  const parts = [];
  ticksLog(...xDomain).forEach(value => {
    parts.push(`<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${pad.top}" y2="${height - pad.bottom}"/>`);
    parts.push(`<text class="tick" x="${x(value)}" y="${height - 10}" text-anchor="middle">${logTick(state.across, value)}</text>`);
  });
  for (let value = yDomain[0]; value <= 1.0001; value += 0.1) {
    parts.push(`<line class="grid" x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}"/>`);
    parts.push(`<text class="tick" x="${pad.left - 6}" y="${y(value) + 4}" text-anchor="end">${pct(value, 0)}</text>`);
  }
  /* Each label takes the first free place right of, left of or centred on its dot, nearest first, with a line back to
     the dot when it moved; where none is free, the place that overlaps the fewest. Most accurate first. */
  const boxes = [];
  const inside = box => box.x0 >= pad.left && box.x1 <= width - pad.right && box.y0 >= 0 && box.y1 <= height - pad.bottom;
  const overlaps = box => boxes.filter(other => box.x0 < other.x1 && box.x1 > other.x0 && box.y0 < other.y1 && box.y1 > other.y0).length;
  const points = known.map(run => ({ run, cx: x(across.value(run)), cy: y(accuracyOf(run)) })).sort((a, b) => a.cy - b.cy);
  points.forEach(({ cx, cy }) => boxes.push({ x0: cx - 5, x1: cx + 5, y0: cy - 5, y1: cy + 5 }));
  points.forEach(({ run, cx, cy }) => {
    const text = truncate(labels.get(run), phone ? 120 : 180);
    const labelWidth = textWidth(text);
    const right = cx + 8;
    const left = cx - 8 - labelWidth;
    const offsets = [0, -13, 13, -26, 26, -39, 39, -52, 52, -65, 65, -78, 78, -91, 91];
    const candidates = offsets.flatMap(dy => [[right, cy + 4 + dy], [left, cy + 4 + dy], [cx - labelWidth / 2, cy + 4 + dy]]);
    const toBox = ([tx, ty]) => ({ x0: tx, x1: tx + labelWidth, y0: ty - 11, y1: ty + 3 });
    const fitting = candidates.filter(candidate => inside(toBox(candidate)));
    const spot =
      fitting.find(candidate => !overlaps(toBox(candidate))) ??
      [...fitting].sort((a, b) => overlaps(toBox(a)) - overlaps(toBox(b)))[0] ??
      candidates[0];
    boxes.push(toBox(spot));
    const tooltip = `${run.name} · ${runDetail(run)}: ${pct(accuracyOf(run))}, ${across.format(across.value(run))}`;
    const [tx, ty] = spot;
    if (Math.abs(ty - 4 - cy) > 6) {
      /* The line ends at the label's nearest edge: its side for a label beside the dot, its top or bottom otherwise. */
      const lx = Math.min(Math.max(cx, tx - 2), tx + labelWidth + 2);
      const ly = lx === cx ? (ty - 4 > cy ? ty - 12 : ty + 3) : ty - 4;
      parts.push(`<line class="leader" x1="${cx}" y1="${cy}" x2="${lx}" y2="${ly}"/>`);
    }
    parts.push(`<circle class="${isDecision(run) ? 'dot-decision' : 'dot-chat'}" cx="${cx}" cy="${cy}" r="4.5"><title>${esc(tooltip)}</title></circle>`);
    parts.push(`<text class="label" x="${tx}" y="${ty}">${esc(text)}</text>`);
  });
  const note = missing ? ` ${missing} setup${missing === 1 ? '' : 's'} without a ${state.across === 'cost' ? 'cost estimate' : 'latency'} not shown.` : '';
  box.innerHTML =
    `<div class="chart-scroll" style="--chart-max:${phone ? 300 : 360}px"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`Scatter chart: accuracy against ${state.across} for ${known.length} setups. Log scale across.`)}">${parts.join('')}</svg></div>` +
    legend(`Up: accuracy on ${integer(questionsInFilter())} questions. Across: ${state.across === 'cost' ? 'cost per 1,000 questions' : 'latency per request'}, log scale.${note}`);
}

const legend = text =>
  `<p class="chart-legend"><span><i class="key key-decision"></i>Decision model</span> <span><i class="key key-chat"></i>Chat model</span> <span class="muted">${esc(text)}</span></p>`;

function renderCharts() {
  document.querySelector('[data-control="measure"]').innerHTML = segmented(
    'measure', [['accuracy', 'Accuracy'], ['latency', 'Latency'], ['cost', 'Cost']], state.measure);
  document.querySelector('[data-control="across"]').innerHTML = segmented('across', [['cost', 'Cost'], ['latency', 'Latency']], state.across);
  const button = document.querySelector('[data-control="show-all"]');
  button.setAttribute('aria-pressed', String(state.showAll));
  button.textContent = state.showAll ? 'Show the default setups' : `Show all ${data.runs.length}`;
  barChart(document.querySelector('[data-chart="measures"]'));
  scatterChart(document.querySelector('[data-chart="tradeoff"]'));
}

/* The open tab and, on the Routing tab, its four choices live in the page URL, so a link opens that exact view:
   ?tab=routing&llm=astra&per-request=16&rule=half&test=replay. */
const llmSlug = llm => llm.label.toLowerCase().replace(/\s+/g, '-');

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const llm = SETTINGS.routeLlms.find(item => llmSlug(item) === params.get('llm'));
  const rule = ROUTE_RULES.find(item => item.slug === params.get('rule'));
  const size = Number(params.get('per-request'));
  if (llm) state.route.llm = llm.key;
  if (rule) state.route.rule = rule.key;
  if ([1, 16].includes(size)) state.route.qpr = size;
  if (ROUTE_TESTS.includes(params.get('test'))) state.route.mode = params.get('test');
  const routed = llm || rule || params.has('per-request') || params.has('test');
  if (TABS[params.get('tab')]) state.tab = params.get('tab');
  else if (routed) state.tab = 'routing';
}

function writeUrl() {
  const params = new URLSearchParams(window.location.search);
  ['tab', 'llm', 'per-request', 'rule', 'test'].forEach(key => params.delete(key));
  if (state.tab !== 'accuracy') params.set('tab', state.tab);
  if (state.tab === 'routing') {
    params.set('llm', llmSlug(routeLlm()));
    params.set('per-request', String(state.route.qpr));
    params.set('rule', routeRule().slug);
    params.set('test', state.route.mode);
  }
  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
  if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) window.history.replaceState(null, '', url);
}

function render() {
  document.querySelectorAll('[role="tab"]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.tab === state.tab)));
  writeUrl();
  renderFilters();
  renderBoard();
  renderCharts();
}

/* ---- Events ---- */

function onClick(event) {
  const target = event.target.closest('button');
  if (!target) return;
  const { dataset } = target;
  if (dataset.part) {
    state.part = dataset.part;
    if (state.topic != null && state.part !== 'all' && unitPart(units().find(unit => unit.number === state.topic)) !== state.part) state.topic = null;
  } else if (dataset.type) state.type = dataset.type;
  else if (dataset.qpr) state.qpr = dataset.qpr === 'all' ? 'all' : Number(dataset.qpr);
  else if (dataset.tab) {
    state.tab = dataset.tab;
    state.sort = { key: 'accuracy', descending: true };
  } else if (dataset.sort) {
    const column = TABS[state.tab].columns.find(item => item.key === dataset.sort);
    state.sort = state.sort.key === column.key ? { key: column.key, descending: !state.sort.descending } : { key: column.key, descending: !column.low };
  } else if (dataset.routeLlm) state.route.llm = dataset.routeLlm;
  else if (dataset.routeQpr) state.route.qpr = Number(dataset.routeQpr);
  else if (dataset.routeMode) state.route.mode = dataset.routeMode;
  else if (dataset.measure) state.measure = dataset.measure;
  else if (dataset.across) state.across = dataset.across;
  else if (dataset.control === 'show-all') state.showAll = !state.showAll;
  else if (dataset.control === 'clear-picked') {
    state.picked.clear();
    renderPicker();
  } else if (dataset.themeChoice) return;
  else return;
  render();
}

function onChange(event) {
  const target = event.target;
  const control = target.dataset.control;
  if (control === 'topic') state.topic = target.value ? Number(target.value) : null;
  else if (control === 'route-rule') state.route.rule = target.value;
  else if (control === 'phone-sort') {
    const column = TABS[state.tab].columns.find(item => item.key === target.value);
    state.sort = column ? { key: column.key, descending: !column.low } : { key: 'accuracy', descending: true };
  } else if (target.closest('.picker-list') && target.type === 'checkbox') {
    const id = Number(target.value);
    if (target.checked) state.picked.add(id);
    else state.picked.delete(id);
  } else return;
  render();
}

async function start() {
  try {
    const response = await fetch(RESULTS_URL);
    if (!response.ok) throw new Error(`${RESULTS_URL}: ${response.status}`);
    data = await response.json();
  } catch (error) {
    const note = document.createElement('p');
    note.className = 'load-error';
    note.textContent = `Could not load the results (${error.message}). The table below shows all questions.`;
    document.getElementById('board').before(note);
    return;
  }
  byId = new Map(data.runs.map(run => [run.run, run]));
  const filters = document.getElementById('filters');
  filters.hidden = false;
  if (PHONE.matches) filters.open = false;
  document.querySelector('.tabs').hidden = false;
  document.querySelector('.charts').hidden = false;
  readUrl();
  renderPicker();
  render();
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  let width = window.innerWidth;
  new ResizeObserver(() => {
    if (window.innerWidth === width) return;
    width = window.innerWidth;
    renderCharts();
  }).observe(document.body);
}

start();
