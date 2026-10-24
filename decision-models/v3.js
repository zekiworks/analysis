'use strict';

/* The home page: filters, the four leaderboard tabs, the routing diagram and the two charts, drawn from results.json,
   beside this page. Every number is read from it: accuracy for a part or topic and its 95% interval from the counts it
   stores, with the Wilson formula, and the routing numbers from the same replays and live tests. The open tab and the
   Routing choices live in the URL; the filters, the highlighted setup and the chart choices live in the browser's
   history entry, so Back returns to them. Without JavaScript the page keeps the plain table build_site.py writes. */

const SETTINGS = JSON.parse(document.getElementById('v3-settings').textContent);
const RESULTS_URL = 'results.json';

/* Why a cell has no value. */
const EMPTY = {
  notMeasured: 'Not measured',
  allOnly: 'Computed on all questions only',
};
const INTERVAL_TIP = 'To test two setups against each other, use Compare.';
const LATENCY_TIP =
  'Latency: the time from sending one request to receiving its answer, measured from our computer, network and retries included. Median request. Local setups ran on our own hardware.';
const COST_TIP =
  'Estimated from list prices and recorded token use, per 1,000 questions. § marks a setup on our own hardware, estimated at its maker’s list price for the same model; our hardware cost is not measured.';
const AUROC_TIP = 'ranking score';
const GAP_TIP =
  'How far the model’s confidence is from how often it is right, as shipped. Example: answers scored 80% that are right 70% of the time add a 10-point gap. Lower is better.';
const FLAT_TIP =
  'How much lower the probability error (Brier score) is for the refitted confidence than for a flat guess. The flat guess gives every answer the same probability: the model’s accuracy on the questions used for fitting. Measured on held-out questions. 0% means no improvement over the flat guess in this test, with this refit method; below 0% means worse. Higher is better.';
const RANKING_TIP =
  'How often a right answer receives higher confidence than a wrong answer. 0.50 is chance; 1.00 is perfect. Uses the original scores.';
const REVERSED_TIP = 'Higher confidence went with lower accuracy for this model.';
const SHARE_TIP = 'Share of questions taken: at 16 questions per request, a call still goes out for the rest.';
const SPLIT_NA_TIP = 'Live tests did not record which kept answers were right, so no bar is shown.';
/* A first model's cost marker (page_config.json first_cost_marks): § where its cost is its maker's list price for the
   same model, † where it ran on our hardware without one; each with its tooltip and note. */
const FIRST_COST_MARKS = SETTINGS.firstCostMarks;
const firstCostMark = run => (run.cost_basis === 'maker' ? FIRST_COST_MARKS.maker : run.api_equivalent_usd == null ? FIRST_COST_MARKS[run.billing] ?? null : null);
/* What a setup on our hardware priced at its maker's list price says beside its cost. */
const makerCostTip = run =>
  `Estimated at ${data.prices.find(price => price.provider === run.provider && price.model === run.model)?.basis ?? 'its maker’s list price for the same model'}; our hardware cost is not measured.`;
const MAKER_COST_NOTE = `${SETTINGS.firstCostMarks.maker.mark} Estimated at the maker’s list price for the same model; our hardware cost is not measured.`;
const CONFIDENCE_NOTE = [
  'Every decision model that ranks its answers better than chance ranks them less well on grammar than on reading. A probability from an API is not calibrated by itself. Luna’s two setups also differ in request format (1 against 16 questions).',
];
const ROUTING_NOTES = [
  'Replay: both models’ recorded answers. Live: the decision model’s recorded answers, with new calls to the LLM. Savings are estimates from API prices, and larger at 1 question per request: each question the LLM skips costs more.',
  'In a live test with Sonnet at 1 question per request, accuracy fell 4.73 points: Decider v1.1 kept 51%, with a cutoff chosen at 16 per request. A cutoff chosen at 1 per request keeps 29%, and accuracy falls 0.16 points (replay). Choose the cutoff in the format you will run.',
  'SubQ Snap’s place depends on the LLM: fifth among decision models in front of Sonnet (16 per request), tenth in front of Opus, eighth in front of Astra. Its most confident fifth of answers was 98.6% right; Decider v1.1’s was 99.3%, the hosted GLiDE’s 99.5%.',
];
const STABILITY_NOTE = [
  'Only the setups we repeated, five times each. Decision models and two Qwen3.8-27B setups were repeated on all questions; the other chat models on a sample of 200.',
];
/* One line under the tab keys for Confidence and Stability, in the Method page's terms; the Routing tab's heading and
   diagram explain it. */
const DEFINITIONS = {
  confidence: 'Whether a model’s confidence ranks right answers above wrong ones and matches its hit rate.',
  stability: 'How many answers changed when we asked the same questions five times.',
};
/* Each rule's name in the page URL ("slug"), its label, and its name among the live tests in results.json. */
const ROUTE_RULES = [
  { key: 'half', slug: 'half', label: 'cutoff chosen on half the questions', live: 'half' },
  { key: 'sure', slug: 'fixed-99', label: 'fixed 99%', live: 'cutoff' },
  { key: 'share', slug: 'quarter', label: 'most confident quarter', live: 'share' },
];
const ROUTE_TESTS = ['replay', 'live'];
const PHONE = window.matchMedia('(max-width: 640px)');
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');
const LAPTOP = window.matchMedia('(min-width: 1024px)');

/* ---- Numbers ---- */

const integer = n => n.toLocaleString('en-US');
const pct = (fraction, digits = 1) => `${(100 * fraction).toFixed(digits)}%`;
/* A share as a number of percent, for a column or axis whose label names the unit: 98.1. */
const percent = (fraction, digits = 1) => (100 * fraction).toFixed(digits);
const signed = (value, digits) => {
  const text = Math.abs(value).toFixed(digits);
  return Number(text) === 0 ? text : `${value > 0 ? '+' : '−'}${text}`;
};
/* A negative value with a true minus sign, as signed() writes it; a value that rounds to zero has no sign. */
const minus = text => (Number(text) === 0 ? text.replace(/^-/, '') : text.replace(/^-/, '−'));
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
/* A value nobody measured reads as words; one a filter leaves out is a dash with its reason; a zero is a number. */
const NM = `<span class="nm">${EMPTY.notMeasured}</span>`;
const MISSING = tip(EMPTY.allOnly);

/* ---- Runs ---- */

const reasoningLabel = reasoning => (['off', 'on'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
const requestSize = size => `${integer(size)} question${size === 1 ? '' : 's'} per request`;
const runDetail = run =>
  [run.variant, run.reasoning && reasoningLabel(run.reasoning), requestSize(run.questions_per_request)].filter(Boolean).join(' · ');
/* The settings in the short form a phone shows: "1 per request · low reasoning"; a variant keeps its part before a
   comma ("Decisions API" for "Decisions API, beta"). */
const shortDetail = run =>
  [`${integer(run.questions_per_request)} per request`, run.reasoning && reasoningLabel(run.reasoning), run.variant?.split(',')[0]]
    .filter(Boolean).join(' · ');
/* A setup's name in the table: on a phone, the charts' short name (page_config.json's short_names) where it has one. */
const tableName = run => {
  const short = SETTINGS.shortNames[run.model];
  return short && short !== run.name
    ? `<span class="name-long">${esc(run.name)}</span><span class="name-short">${esc(short)}</span>`
    : esc(run.name);
};
const isDecision = run => SETTINGS.decisionProviders.includes(run.provider) && !SETTINGS.notDecisionModels.includes(run.model);
const costPer1000 = run => (run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / run.answered_questions);
const latencyOf = run => run.latency?.median_request_seconds ?? null;

let data;
let byId;
/* Chart labels: a setup's short name (page_config.json's short_names) and, for a smaller second line, its variant and the
   reasoning or request size that tell it apart from another setup in the same chart with the same name. */
function chartLabels(runs) {
  const short = run => SETTINGS.shortNames[run.model] ?? run.name;
  // page_config.json's chart_labels name a setup outright; the tooltip keeps its full name.
  const named = run => SETTINGS.chartLabels[run.provider]?.[run.model];
  const base = run => named(run) ?? (run.variant ? `${short(run)} (${run.variant})` : short(run));
  const labels = new Map();
  runs.forEach(run => {
    const same = runs.filter(other => base(other) === base(run));
    const differs = field => new Set(same.map(other => other[field])).size > 1;
    const name = named(run) ?? short(run);
    const detail = [
      !named(run) && run.variant,
      differs('reasoning') && run.reasoning && reasoningLabel(run.reasoning),
      differs('questions_per_request') && `${run.questions_per_request}/request`,
    ].filter(Boolean).join(', ');
    labels.set(run, { name, detail, text: detail ? `${name} (${detail})` : name });
  });
  return labels;
}

const DEFAULT_FILTERS = { part: 'all', topic: null, type: 'decision', qpr: 'all' };
const state = {
  ...DEFAULT_FILTERS,
  picked: new Set(),
  search: '',
  selected: null,
  filtersOpen: false,
  tab: 'accuracy',
  sort: { key: 'accuracy', descending: true },
  route: { llm: 'opus', qpr: 1, rule: 'half', mode: 'replay' },
  measure: 'accuracy',
  across: 'cost',
  showAll: false,
  /* On a phone, the leaderboard panel shows the table or the charts; kept in the history entry, not in the URL. */
  view: 'table',
};
/* Each tab's order when it opens: the Routing tab by the share of the LLM's questions taken, the others by accuracy. */
const DEFAULT_SORTS = { routing: { key: 'share', descending: true } };
const defaultSort = tab => ({ ...(DEFAULT_SORTS[tab] ?? { key: 'accuracy', descending: true }) });
const atDefaults = () =>
  Object.entries(DEFAULT_FILTERS).every(([key, value]) => state[key] === value) && !state.picked.size;

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

/* Correct answers and questions of one part (reading or grammar) inside the part and topic filters; null when the
   filter leaves that part out. */
function partCounts(run, part) {
  if (state.topic != null) {
    const index = units().findIndex(unit => unit.number === state.topic);
    return unitPart(units()[index]) === part ? { correct: run.units[index], questions: units()[index].questions } : null;
  }
  if (state.part !== 'all' && state.part !== part) return null;
  return run.groups[part];
}

function partColumn(part, label) {
  const share = run => {
    const found = partCounts(run, part);
    return found ? found.correct / found.questions : null;
  };
  return { key: part, label, className: part, value: share, cell: run => (share(run) == null ? MISSING : percent(share(run))) };
}

function visibleRuns() {
  return data.runs.filter(
    run =>
      (state.type === 'all' || (state.type === 'decision') === isDecision(run)) &&
      (state.qpr === 'all' || run.questions_per_request === state.qpr) &&
      (!state.picked.size || state.picked.has(run.run)),
  );
}

/* ---- Leaderboard ---- */

function modelCell(run) {
  const name = `${run.name} (${runDetail(run)})`;
  return `<td class="model"><div class="who"><button type="button" class="pick" data-select="${run.run}" aria-pressed="${state.selected === run.run}" ` +
    `aria-label="Highlight ${esc(name)} in the charts"><span class="lamp" aria-hidden="true"></span></button>` +
    `<span class="names"><a class="model-name" href="models/${run.run}/">${tableName(run)}</a><span class="small settings-long">${esc(runDetail(run))}</span>` +
    `<span class="small settings-short">${esc(shortDetail(run))}</span></span></div></td>`;
}

function accuracyCell(run) {
  const { correct, questions } = counts(run);
  const [low, high] = wilson(correct, questions);
  return `${percent(correct / questions)}<span class="small">${percent(low)} to ${percent(high)}</span>`;
}

/* Better than a flat guess: how much the refitted confidence lowers the Brier score of one flat guess at the model's hit
   rate, in percent. A slope of zero or below in any fold means higher confidence went with lower accuracy, and the value
   carries a "reversed" marker. */
const flatGain = run => 100 * (1 - run.confidence.brier_refit / run.confidence.brier_base);
const reversedRefit = run => run.confidence.refit_slopes.some(slope => slope != null && slope <= 0);

/* The Confidence tab's guide above the table: each term, then what it means. */
const CONFIDENCE_GUIDE = [
  ['Confidence', 'the probability a model gives to its own answer.'],
  ['Calibration', 'whether that probability matches how often the model is right. Of 100 answers scored 80%, about 80 should be right.'],
  [
    `Correct answers at ${pct(SETTINGS.threshold, 0)}`,
    `answers scored ${pct(SETTINGS.threshold, 0)} or more that were right: the score a model would get if it answered only those questions.`,
  ],
  ['Ranking score', 'how often a right answer receives higher confidence than a wrong answer. 0.50 is chance; 1.00 is perfect. Higher is better.'],
  ['Calibration gap', 'how far the probabilities are from the real hit rate, in points, as shipped. Lower is better.'],
  [
    'Better than a flat guess (after refit)',
    'how much lower the probability error is for the refitted confidence than for the flat baseline. 0% means no improvement in this test. Higher is better.',
  ],
];

/* Each tab's columns: label (with its unit), header tooltip, the value it sorts by (null sorts last), and the cell, one
   number of decimals per column. "low" marks the columns where a lower value is better, so their first click sorts
   upwards; with a tab's "directions", "qualifier" goes before the column's direction line. A tab's "guide" goes above
   its table. */
const TABS = {
  accuracy: {
    rows: () => visibleRuns().map(run => ({ run })),
    note: [SETTINGS.notMeasuredNote],
    columns: [
      { key: 'accuracy', label: 'Accuracy (%)', tip: INTERVAL_TIP, value: accuracyOf, cell: accuracyCell },
      partColumn('reading', 'Reading (%)'),
      partColumn('grammar', 'Grammar (%)'),
      {
        key: 'latency', label: 'Median latency per request (s)', className: 'unit-long', tip: LATENCY_TIP, low: true, value: latencyOf,
        cell: run => latencyCell(run),
      },
      {
        key: 'cost', label: '$ per 1,000 questions', className: 'unit-long', tip: COST_TIP, low: true, value: costPer1000,
        cell: run => costCell(run),
      },
    ],
  },
  confidence: {
    rows: () => visibleRuns().map(run => ({ run })),
    note: CONFIDENCE_NOTE,
    guide: CONFIDENCE_GUIDE,
    /* Each header says under its label which direction is better, from the column's "low" flag. */
    directions: true,
    /* Long labels: the headers wrap on a wide screen too, so every column fits beside the names. */
    wrapHeaders: true,
    columns: [
      {
        key: 'sure-correct', label: `Correct answers at ${pct(SETTINGS.threshold, 0)}`,
        tip: `Answers scored ${pct(SETTINGS.threshold, 0)} or more that were right: the score a model would get if it answered only the questions it was ${pct(SETTINGS.threshold, 0)} sure of.`,
        value: run => (filtered() ? null : run.confidence.sure.correct),
        cell: run => (filtered() ? MISSING : integer(run.confidence.sure.correct)),
      },
      {
        key: 'auroc', label: 'Ranking score', tip: RANKING_TIP,
        value: run => (filtered() ? null : run.confidence.auroc),
        cell: run => (filtered() ? MISSING : run.confidence.auroc.toFixed(3)),
      },
      {
        key: 'gap', label: 'Calibration gap (points)', tip: GAP_TIP, low: true,
        value: run => (filtered() ? null : run.confidence.ece),
        cell: run => (filtered() ? MISSING : (100 * run.confidence.ece).toFixed(1)),
      },
      {
        key: 'flat', label: 'Better than a flat guess (%)', tip: FLAT_TIP, qualifier: 'after refit',
        value: run => (filtered() ? null : flatGain(run)),
        cell: run => {
          if (filtered()) return MISSING;
          const value = flatGain(run).toFixed(1);
          return reversedRefit(run) ? `${value}<span class="small">${tip(REVERSED_TIP, 'reversed')}</span>` : value;
        },
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
        cell: row => (filtered() ? MISSING : `${integer(row.item.changed_answer)} of ${integer(row.item.questions)}`),
      },
      {
        key: 'same-wrong', label: 'Same wrong answer in all 5', low: true,
        value: row => (filtered() ? null : row.item.wrong_every_run_same / row.item.questions),
        cell: row => (filtered() ? MISSING : `${integer(row.item.wrong_every_run_same)} of ${integer(row.item.questions)}`),
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
    cell: run => (available() ? run.confidence.parts[stored].auroc.toFixed(2) : MISSING),
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
    if (item) {
      const held = item.held_out;
      numbers = { share: held.answered, change: held.difference, perThousand: item.usd_per_1000 };
      if (held.kept_right != null) numbers.split = { right: held.kept_right, wrong: held.kept_wrong, rest: held.handed_off, splits: held.splits };
    }
  } else if (first.run === data.replay.decision) {
    const item = data.replay.frontiers.find(entry => entry.frontier === frontier.run)?.[state.route.rule];
    if (item) {
      const total = data.replay.questions;
      numbers = { share: item.kept / total, change: item.difference, perThousand: item.usd_per_1000 };
      /* The fixed rules keep the same answers in front of every LLM; their kept and wrong counts are stored once. */
      const kept = state.route.rule === 'sure' ? data.replay.cutoffs.find(entry => entry.cutoff === data.sure_threshold) : data.replay.share;
      if (kept && kept.kept === item.kept) {
        numbers.split = { right: (kept.kept - kept.wrong) / total, wrong: kept.wrong / total, rest: (total - kept.kept) / total, splits: null };
      }
    }
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
  { key: 'share', label: 'Share of the LLM’s questions taken (%)', tip: SHARE_TIP, value: row => row.numbers?.share ?? null,
    cell: row => shareCell(row) },
  { key: 'change', label: 'Accuracy change (points)', value: row => row.numbers?.change ?? null,
    cell: row => (row.numbers ? signed(100 * row.numbers.change, 2) : NM) },
  { key: 'saving', label: 'Saving (%)', value: row => row.numbers?.saving ?? null, cell: row => savingCell(row, n => minus(percent(n.saving, 0))) },
  { key: 'saving-usd', label: 'Saving ($ per 1,000 questions)', value: row => row.numbers?.savingUsd ?? null,
    cell: row => savingCell(row, n => minus(n.savingUsd.toFixed(3))) },
];
TABS.routing.columns = ROUTING_COLUMNS;

function savingCell(row, format) {
  if (!row.numbers || row.numbers.saving == null) return NM;
  const mark = firstCostMark(row.run);
  return mark ? `${tip(mark.tip, format(row.numbers))}<span class="mark">${mark.mark}</span>` : format(row.numbers);
}

/* A setup's cost per 1,000 questions; one on our hardware at its maker's list price carries § and its label. */
function costCell(run) {
  const value = costPer1000(run);
  if (value == null) return NM;
  return run.cost_basis === 'maker' ? `${tip(makerCostTip(run), value.toFixed(3))}<span class="mark">${FIRST_COST_MARKS.maker.mark}</span>` : value.toFixed(3);
}

/* A latency measured on a sample of the questions (latency.source "sample", the repeats of the setup on a fixed
   sample): its marker, its label, and the note under a chart that shows one. */
const SAMPLE_MARK = '*';
const sampleLabel = run => (run.latency?.source === 'sample' ? `Measured on a sample (${integer(run.latency.questions)} questions)` : null);
const sampleNotes = runs => [...new Set(runs.map(run => latencyOf(run) != null && sampleLabel(run)).filter(Boolean))].map(label => `${SAMPLE_MARK} ${label}.`);

function latencyCell(run) {
  const value = latencyOf(run);
  if (value == null) return NM;
  const label = sampleLabel(run);
  return label ? `${tip(label, value.toFixed(3))}<span class="mark">${SAMPLE_MARK}</span>` : value.toFixed(3);
}

/* The share taken, with where every question goes under it: a bar of three parts with their values printed, green for
   kept and right, hatched red for kept but wrong, grey for sent to the LLM. A gap keeps green and red apart; "Not
   recorded" where no split was stored. The bar sits in the space the column's heading leaves, so the table keeps its
   width. */
function shareCell(row) {
  if (!row.numbers) return NM;
  const { share, split } = row.numbers;
  if (!split) return `<span class="share-cell">${percent(share)}${tip(SPLIT_NA_TIP, '<span class="nm">Not recorded</span>')}</span>`;
  const parts = [['right', split.right, 'kept and right'], ['wrong', split.wrong, 'kept but wrong'], ['rest', split.rest, 'sent to the LLM']];
  const scope = split.splits ? `means over the replay’s ${integer(split.splits)} splits` : 'shares of all questions';
  const spoken = `${parts.map(([, value, name]) => `${name} ${percent(value)}%`).join(', ')}; ${scope}`;
  return `<span class="share-cell">${percent(share)}<span class="split" role="img" aria-label="${esc(spoken)}">` +
    `<span class="split-bar" aria-hidden="true">${parts.map(([key, value]) => `<span class="split-${key}" style="flex-grow:${value.toFixed(5)}"></span>`).join('')}</span>` +
    `<span class="split-values" aria-hidden="true">${parts.map(([, value]) => percent(value)).join(' · ')}</span></span></span>`;
}

/* The Routing table's note on the bars under each share, for the rule and test on screen. */
function splitNote(rows) {
  if (!rows.some(row => row.numbers)) return '';
  if (state.route.mode === 'live') return 'Live tests did not record which kept answers were right, so their shares have no bar.';
  const splits = rows.map(row => row.numbers?.split).filter(Boolean);
  if (!splits.length) return '';
  const bar = 'Bar under each share: kept and right (green), kept but wrong (hatched red) and sent to the LLM (grey), in %';
  const counts = [...new Set(splits.map(split => split.splits).filter(count => count != null))];
  if (counts.length) return `${bar}: means over the replay’s ${counts.map(integer).join(' or ')} random splits, each measured on the half of the questions not used to choose the cutoff.`;
  return `${bar} of all ${integer(data.replay.questions)} questions.`;
}

/* The path a question takes, drawn as a small static diagram; tags on its two branches mark the current choices. When a
   choice changes, the path is traced once; with reduced motion, not at all. */
let routeSignature = null;
function routeMap() {
  const signature = [state.route.llm, state.route.qpr, state.route.rule, state.route.mode].join('|');
  const trace = routeSignature !== null && routeSignature !== signature && !REDUCED_MOTION.matches;
  routeSignature = signature;
  const llm = byId.get(routeLlm().runs[state.route.qpr]);
  const test = state.route.mode === 'live' ? 'Live: new calls to the LLM' : 'Replay: recorded answers';
  const choice = text => `<span class="rm-choice">${esc(text)}</span>`;
  return (
    `<figure class="route-map${trace ? ' trace' : ''}">` +
    '<span class="rm-node">Question</span><span class="rm-wire" aria-hidden="true"></span><span class="rm-node">Decision model</span>' +
    `<span class="rm-fork"><span class="rm-branch"><span class="rm-node">Keep its answer</span>${choice(routeRule().label)}</span>` +
    `<span class="rm-branch"><span class="rm-node">Send the question to the LLM</span>${choice(llm.name)}${choice(requestSize(state.route.qpr))}` +
    `${choice(test)}</span></span></figure>`
  );
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

/* A sortable header: ⇅ when another column sorts the table, ▲ or ▼ when this one does. With directions, a muted line
   under the label says which way is better, from the column's "low" flag, in words, as the arrows mean sorting; a
   qualifier ("after refit") goes first. Each phrase keeps its words together, so a narrow column breaks only after "·". */
function header(column, directions = false) {
  const sorted = state.sort.key === column.key;
  const aria = sorted ? ` aria-sort="${state.sort.descending ? 'descending' : 'ascending'}"` : '';
  const mark = sorted ? (state.sort.descending ? '▼' : '▲') : '⇅';
  const hint = column.tip ? ` data-tip="${esc(column.tip)}"` : '';
  const phrases = [column.qualifier, column.low ? 'lower is better' : 'higher is better'].filter(Boolean);
  const direction = directions
    ? `<span class="small direction">${phrases.map(text => esc(text).replaceAll(' ', '\u00a0')).join('\u00a0· ')}</span>`
    : '';
  return `<th scope="col" class="num ${column.className ?? ''}"${aria}><button type="button" class="sort${directions ? ' directed' : ''}" data-sort="${column.key}"${hint}>` +
    `<span class="label">${esc(column.label)}</span><span class="sort-mark" aria-hidden="true">${mark}</span>${direction}</button></th>`;
}

/* Why no row matches, and the way back. */
function emptyReason() {
  if (!visibleRuns().length) {
    const kind = { decision: 'a decision model', chat: 'a chat model' }[state.type];
    const size = state.qpr === 'all' ? null : `ran at ${requestSize(state.qpr)}`;
    if (state.picked.size) {
      const conditions = [kind && `is ${kind}`, size].filter(Boolean).join(' that ');
      return `None of the models you picked ${conditions}.`;
    }
    return `No ${kind ? kind.slice(2) : 'setup'} ${size ?? 'matches these filters'}.`;
  }
  if (state.tab === 'routing') return 'The Routing tab lists only the setups we put in front of an LLM; none of them matches these filters.';
  if (state.tab === 'stability') return 'The Stability tab lists only the setups we repeated; none of them matches these filters.';
  return 'No setup matches these filters.';
}

function renderBoard() {
  const tab = TABS[state.tab];
  const rows = sortRows(tab.rows(), tab.columns);
  const body = rows
    .map(row => `<tr data-run="${row.run.run}"${state.selected === row.run.run ? ' class="is-selected"' : ''}>${modelCell(row.run)}` +
      `${tab.columns.map(column => `<td class="num">${column.cell(row)}</td>`).join('')}</tr>`)
    .join('');
  const table = rows.length
    ? `<div class="table-frame"><div class="table-wrap"><table class="board${tab.wrapHeaders ? ' wrap-headers' : ''}"><thead><tr><th scope="col">Model</th>${tab.columns.map(column => header(column, tab.directions)).join('')}</tr></thead><tbody>${body}</tbody></table></div></div>`
    : `<div class="empty-state" role="status"><p><span class="icon" aria-hidden="true">⚠</span> ${esc(emptyReason())}</p>` +
      '<button type="button" class="key" data-control="reset">Reset filters</button></div>';
  const routing =
    state.tab === 'routing'
      ? `<h3 class="tab-title">Can a cheap model go first?</h3>${routingControls()}${routeMap()}<p class="table-title">${esc(routeTitle())}</p>` +
        `<p class="scope">All ${integer(data.questions)} questions</p>`
      : '';
  /* The note for a † or §, each only when its marker is in the table. */
  const marked = new Set(rows.filter(row => row.numbers?.saving != null).map(row => firstCostMark(row.run)).filter(Boolean));
  const marks = Object.values(FIRST_COST_MARKS)
    .filter(item => marked.has(item))
    .map(item => `<p class="table-note">${esc(`${item.mark} ${item.note}`)}</p>`)
    .join('');
  const notes = (tab.notes ?? tab.note ?? []).map(text => `<p>${esc(text)}</p>`).join('');
  const guide = tab.guide
    ? `<div class="tab-guide"><h3>How to read this tab</h3><ul>${tab.guide.map(([term, text]) => `<li><strong>${esc(term)}</strong>: ${esc(text)}</li>`).join('')}</ul></div>`
    : '';
  const board = document.getElementById('board');
  const split = state.tab === 'routing' ? splitNote(rows) : '';
  board.innerHTML = routing + guide + table + (split ? `<p class="table-note">${esc(split)}</p>` : '') + marks + (notes ? `<div class="tab-notes">${notes}</div>` : '');
  board.setAttribute('aria-labelledby', `tab-${state.tab}`);
  board.querySelector('.table-wrap')?.addEventListener('scroll', onTableScroll, { passive: true });
  document.querySelectorAll('[data-setups]').forEach(count => {
    count.textContent = `${integer(rows.length)} of ${integer(data.runs.length)} setups`;
  });
}

/* On a phone the table scrolls sideways inside its frame: a fade on the right edge while columns are hidden there, and a
   label above the table until the reader first scrolls it (remembered for the session). */
let swiped = document.documentElement.classList.contains('swiped');
function edgeFade(wrap) {
  wrap.parentElement.classList.toggle('more-right', wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 1);
}
function updateSwipe() {
  const wrap = document.querySelector('#board .table-wrap');
  const hint = document.querySelector('[data-swipe-hint]');
  hint.classList.remove('is-done');
  hint.hidden = swiped || !wrap || wrap.scrollWidth - wrap.clientWidth <= 1;
  if (wrap) edgeFade(wrap);
}
function onTableScroll(event) {
  const wrap = event.currentTarget;
  if (!swiped && wrap.scrollLeft > 0) {
    swiped = true;
    try {
      sessionStorage.setItem('v3-swiped', '1');
    } catch (error) {
      /* Storage may be unavailable; the label then returns on the next page view. */
    }
    /* Hidden in place, so the table does not move under the reader's finger; the next render drops the line. */
    document.querySelector('[data-swipe-hint]').classList.add('is-done');
  }
  edgeFade(wrap);
}

/* On a phone, the Table · Charts switch shows the charts in the table's place, with the same filters and tab; elsewhere
   the charts stay below the leaderboard. */
function placeCharts() {
  const panel = document.querySelector('.board-panel');
  const charts = document.getElementById('charts');
  const inPanel = PHONE.matches && state.view === 'charts';
  if (inPanel && charts.parentElement !== panel) panel.querySelector('.version-below').before(charts);
  else if (!inPanel && charts.parentElement === panel) panel.after(charts);
  panel.classList.toggle('shows-charts', inPanel);
  document.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === state.view)));
}

function keys(name, options, current) {
  return options
    .map(([value, label]) =>
      `<button type="button" class="key" data-${name}="${value}" aria-pressed="${String(value) === String(current)}"><span class="lamp" aria-hidden="true"></span>${esc(label)}</button>`)
    .join('');
}

function routingControls() {
  const { llm, qpr, rule, mode } = state.route;
  return (
    '<div class="route-controls">' +
    `<div class="group" role="group" aria-label="LLM"><span class="group-label" aria-hidden="true">LLM</span><span class="keys">${keys('route-llm', SETTINGS.routeLlms.map(item => [item.key, item.label]), llm)}</span></div>` +
    `<div class="keys" role="group" aria-label="Questions per request">${keys('route-qpr', [[1, '1 per request'], [16, '16 per request']], qpr)}</div>` +
    `<label>Rule <select data-control="route-rule">${ROUTE_RULES.map(item => `<option value="${item.key}"${item.key === rule ? ' selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label>` +
    `<div class="keys" role="group" aria-label="Test">${keys('route-mode', [['replay', 'Replay'], ['live', 'Live']], mode)}</div>` +
    '</div>'
  );
}

/* ---- Filters ---- */

function filterSummary() {
  const parts = [{ all: 'All models', decision: 'Decision models', chat: 'Chat models' }[state.type]];
  if (state.topic != null) parts.push(units().find(unit => unit.number === state.topic).english);
  else if (state.part !== 'all') parts.push(state.part === 'reading' ? 'Reading' : 'Grammar');
  if (state.qpr !== 'all') parts.push(requestSize(state.qpr));
  if (state.picked.size) parts.push(`${integer(state.picked.size)} picked`);
  return parts.join(' · ');
}

function renderFilters() {
  const press = (selector, test) => document.querySelectorAll(selector).forEach(button => button.setAttribute('aria-pressed', String(test(button))));
  press('[data-control="type"] [data-type]', button => button.dataset.type === state.type);
  press('[data-control="part"] [data-part]', button => button.dataset.part === state.part);
  press('[data-control="qpr"] [data-qpr]', button => button.dataset.qpr === String(state.qpr));
  const topics = units().filter(unit => state.part === 'all' || unitPart(unit) === state.part);
  const group = part =>
    topics
      .filter(unit => unitPart(unit) === part)
      .map(unit => `<option value="${unit.number}"${unit.number === state.topic ? ' selected' : ''}>${esc(unit.english)}</option>`)
      .join('');
  document.querySelector('[data-control="topic"]').innerHTML =
    '<option value="">All topics</option>' +
    ['reading', 'grammar']
      .map(part => [part, group(part)])
      .filter(([, html]) => html)
      .map(([part, html]) => `<optgroup label="${part === 'reading' ? 'Reading' : 'Grammar'}">${html}</optgroup>`)
      .join('');
  document.querySelector('[data-summary]').textContent = filterSummary();
  /* The Routing tab ignores the part and topic filters: its table is computed on every question. */
  document.querySelector('[data-count]').textContent = `${integer(state.tab === 'routing' ? data.questions : questionsInFilter())} questions`;
  const reset = document.querySelector('.filters-bar [data-control="reset"]');
  const idle = atDefaults();
  reset.setAttribute('aria-disabled', String(idle));
  if (idle) {
    reset.dataset.tip = document.querySelector('[data-reset-why]').textContent;
    reset.setAttribute('aria-describedby', 'reset-why');
  } else {
    delete reset.dataset.tip;
    reset.removeAttribute('aria-describedby');
  }
  const filters = document.getElementById('filters');
  filters.classList.toggle('is-open', state.filtersOpen);
  filters.classList.toggle('is-closed', !state.filtersOpen);
  filters.querySelector('[data-control="filters"]').setAttribute('aria-expanded', String(state.filtersOpen));
}

function renderPicker() {
  const list = document.querySelector('[data-control="picker"]');
  const group = (title, runs) =>
    `<fieldset><legend>${title}</legend>${runs
      .map(run =>
        `<label data-name="${esc(`${run.name} ${runDetail(run)}`.toLowerCase())}"><input type="checkbox" value="${run.run}"${state.picked.has(run.run) ? ' checked' : ''}> ` +
        `<span>${esc(run.name)} <span class="detail">${esc(runDetail(run))}</span></span></label>`)
      .join('')}</fieldset>`;
  const sorted = [...data.runs].sort((a, b) => overallAccuracy(b) - overallAccuracy(a));
  list.innerHTML =
    group('Decision models', sorted.filter(isDecision)) + group('Chat models', sorted.filter(run => !isDecision(run))) +
    '<p class="none" hidden>No model matches.</p>';
  document.querySelector('[data-control="model-search"]').value = state.search;
  applySearch();
}

function applySearch() {
  const query = state.search.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll('.model-list label').forEach(label => {
    label.hidden = Boolean(query) && !label.dataset.name.includes(query);
    if (!label.hidden) shown += 1;
  });
  document.querySelectorAll('.model-list fieldset').forEach(set => {
    set.hidden = ![...set.querySelectorAll('label')].some(label => !label.hidden);
  });
  document.querySelector('.model-list .none').hidden = shown > 0;
}

function resetFilters() {
  Object.assign(state, DEFAULT_FILTERS);
  state.picked.clear();
  state.search = '';
  renderPicker();
}

/* ---- Charts ---- */

/* The setups the charts show: by default the decision models with the highest accuracy and the routing LLMs at one
   question per request, with the setups picked or highlighted; "Show all" adds the rest. The type and request-size
   filters apply. showAll asks for either set, whichever the charts show. */
function chartRuns(showAll = state.showAll) {
  let runs;
  if (showAll) runs = data.runs;
  else {
    const decision = [...data.runs].filter(isDecision).sort((a, b) => overallAccuracy(b) - overallAccuracy(a));
    const llms = SETTINGS.routeLlms.map(llm => byId.get(llm.runs['1']));
    const extra = [...state.picked, state.selected].filter(id => id != null).map(id => byId.get(id));
    const chosen = new Set([...decision.slice(0, SETTINGS.chartDecisionModels), ...llms, ...extra]);
    runs = data.runs.filter(run => chosen.has(run));
  }
  return runs.filter(
    run =>
      (state.type === 'all' || (state.type === 'decision') === isDecision(run)) &&
      (state.qpr === 'all' || run.questions_per_request === state.qpr),
  );
}

/* Which setups a chart shows, in words. */
function chartScope(runs) {
  const head = `${integer(runs.length)} setup${runs.length === 1 ? '' : 's'}`;
  if (state.showAll) return `${head}: every setup the filters allow.`;
  const parts = [];
  if (state.type !== 'chat') parts.push(`the ${SETTINGS.chartDecisionModels} most accurate decision models`);
  if (state.type !== 'decision') parts.push('the routing LLMs at 1 question per request');
  if (state.picked.size || state.selected != null) parts.push('the setups you picked or highlighted');
  return `${head}: ${parts.join(', ')}${state.qpr === 'all' ? '' : `, at ${requestSize(state.qpr)}`}.`;
}

/* The filters behind a chart, for its downloaded image. */
function chartCondition() {
  const where = state.topic != null
    ? `topic “${units().find(unit => unit.number === state.topic).english}”`
    : state.part === 'all' ? 'all questions' : `${state.part} questions`;
  return [`${integer(questionsInFilter())} questions (${where})`, filterSummary()].join(' · ');
}

const MEASURES = {
  accuracy: { label: 'Accuracy', axis: 'Accuracy (%)', value: run => accuracyOf(run), log: false, text: value => percent(value), higher: true },
  latency: { label: 'Latency', axis: 'Median latency per request (s), log scale', value: latencyOf, log: true, text: value => value.toFixed(3), higher: false },
  cost: { label: 'Cost', axis: '$ per 1,000 questions, log scale', value: costPer1000, log: true, text: value => value.toFixed(3), higher: false },
};
const NEEDS = { latency: 'latency', cost: 'cost estimate' };

/* The ranking scale. In the accuracy, latency and cost charts and the small chart, each decision model's bar or dot
   takes one colour from a fixed scale (SETTINGS.rankScale): dark blue for the worst decision model, through turquoise
   and green, to yellow for the best; chat models stay grey. A measure's ends are the worst and best decision models in
   the published results (accuracy on all questions), set once when the results load, so a filter changes which setups
   are drawn, never what a colour means; a value beyond an end (a filtered accuracy, say) takes that end's colour.
   Latency and cost run on a log scale, accuracy on a linear one; lower is better for latency and cost. */
let rankEnds;
function setRankEnds() {
  const decision = data.runs.filter(isDecision);
  const ends = (value, higher) => {
    const known = decision.map(value).filter(item => item != null);
    return higher ? [Math.min(...known), Math.max(...known)] : [Math.max(...known), Math.min(...known)];
  };
  rankEnds = { accuracy: ends(overallAccuracy, true), latency: ends(latencyOf, false), cost: ends(costPer1000, false) };
}
const channels = hex => [1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16));
function rankColor(name, value) {
  const [worst, best] = rankEnds[name];
  const at = MEASURES[name].log ? Math.log10 : item => item;
  const span = at(best) - at(worst);
  const share = span ? Math.min(1, Math.max(0, (at(value) - at(worst)) / span)) : 1;
  const stops = SETTINGS.rankScale;
  const place = share * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(place));
  const [from, to] = [channels(stops[index]), channels(stops[index + 1])];
  return `#${from.map((channel, i) => Math.round(channel + (to[i] - channel) * (place - index)).toString(16).padStart(2, '0')).join('')}`;
}
/* A scale end as a legend writes it. */
const endText = (name, value) => (name === 'accuracy' ? `${percent(value)}%` : name === 'latency' ? `${value.toFixed(3)} s` : `$${value.toFixed(3)}`);
/* The legend of a chart coloured by the scale: the decision models' colours from worst to best with each end's value and
   which way is better, then the chat models' grey. */
function scaleLegend(name) {
  const [worst, best] = rankEnds[name];
  return `<span class="scale-legend"><span>Decision models: worst ${esc(endText(name, worst))}</span>` +
    `<i class="ramp" style="background:linear-gradient(to right, ${SETTINGS.rankScale.join(', ')})" aria-hidden="true"></i>` +
    `<span>best ${esc(endText(name, best))} (${MEASURES[name].higher ? 'higher' : 'lower'} is better)</span></span> ` +
    '<span><i class="swatch swatch-chat"></i>Chat model</span>';
}

const ticksLog = (low, high) => {
  const ticks = [];
  for (let power = Math.floor(Math.log10(low)); power <= Math.ceil(Math.log10(high)); power++) {
    const value = 10 ** power;
    if (value >= low && value <= high) ticks.push(value);
  }
  return ticks;
};
const logTick = value => (value < 1 ? String(Number(value.toPrecision(1))) : integer(value));
/* Chart text, a label's settings line included, is 12px in the page's font; labels are measured with it, so they fit
   their space and never overlap. */
const measurer = document.createElement('canvas').getContext('2d');
function textWidth(text, weight = 400, size = 12) {
  measurer.font = `${weight} ${size}px ${getComputedStyle(document.body).fontFamily}`;
  return measurer.measureText(text).width;
}
function truncate(text, width, weight = 400, size = 12) {
  if (textWidth(text, weight, size) <= width) return text;
  let cut = text;
  while (cut.length > 1 && textWidth(`${cut}…`, weight, size) > width) cut = cut.slice(0, -1);
  return `${cut.trimEnd()}…`;
}
/* Words in lines no wider than the width, for a downloaded chart's title and notes. */
function wrap(text, width, weight = 400, size = 12) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const longer = line ? `${line} ${word}` : word;
    if (line && textWidth(longer, weight, size) > width) {
      lines.push(line);
      line = word;
    } else line = longer;
  }
  if (line) lines.push(line);
  return lines;
}
/* Whether the line from (x1, y1) to (x2, y2) passes through a box (Liang–Barsky clipping). */
function crosses([x1, y1, x2, y2], box) {
  let enter = 0;
  let leave = 1;
  for (const [p, q] of [[x1 - x2, x1 - box.x0], [x2 - x1, box.x1 - x1], [y1 - y2, y1 - box.y0], [y2 - y1, box.y1 - y1]]) {
    if (p === 0) {
      if (q < 0) return false;
    } else if (p < 0) enter = Math.max(enter, q / p);
    else leave = Math.min(leave, q / p);
  }
  return enter < leave;
}

function scale(domain, range, log) {
  const [d0, d1] = log ? domain.map(Math.log10) : domain;
  return value => range[0] + (((log ? Math.log10(value) : value) - d0) / (d1 - d0)) * (range[1] - range[0]);
}

/* The charts scroll inside a box of fixed height (chartMax). A chart taller than its box draws narrower by the
   scrollbar's width, or by 12 px where scrollbars float over the content, so the scrollbar never covers a value. */
const chartMax = () => (PHONE.matches ? 300 : 360);
let scrollbarWidth = null;
function drawWidth(box, height) {
  if (height <= chartMax()) return box.clientWidth;
  if (scrollbarWidth == null) {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;top:-9999px;width:100px;height:100px;overflow:scroll';
    document.body.append(probe);
    scrollbarWidth = probe.offsetWidth - probe.clientWidth;
    probe.remove();
  }
  return box.clientWidth - Math.max(scrollbarWidth, 12);
}

const legend = (name, text) => `<p class="chart-legend">${scaleLegend(name)} <span>${esc(text)}</span></p>`;
/* Each chart's notes, and the setups it could not label, kept for its downloaded image. */
const chartNotes = {};
const markAttributes = (run, text) =>
  `class="mark${state.selected === run.run ? ' is-selected' : ''}" data-select="${run.run}" tabindex="0" role="button" ` +
  `aria-pressed="${state.selected === run.run}" aria-label="${esc(text)}"`;
/* A setup's label in a horizontal bar chart: beside the bars, right-aligned in labelWidth, with its settings on a second
   line; on a phone, above its bars across the chart's width. A label is cut short only when even that is too narrow; its
   tooltip has the full name. */
function rowLabel(labels, run, y, row, width, labelWidth, full) {
  const selected = state.selected === run.run;
  const weight = selected ? 700 : 400;
  const { name, detail } = labels.get(run);
  const labelClass = `label${selected ? ' is-selected' : ''}`;
  if (PHONE.matches) {
    const first = truncate(name, width - 4, weight);
    const rest = detail ? truncate(` · ${detail}`, width - 4 - textWidth(first, weight), weight, 12) : '';
    return `<text class="${labelClass}" x="2" y="${y + 13}"><title>${esc(full)}</title>${esc(first)}${rest ? `<tspan class="detail">${esc(rest)}</tspan>` : ''}</text>`;
  }
  const first = `<tspan x="${labelWidth}" y="${detail ? y + 15 : y + row / 2 + 4}">${esc(truncate(name, labelWidth, weight))}</tspan>`;
  const second = detail ? `<tspan class="detail" x="${labelWidth}" y="${y + 28}">${esc(truncate(detail, labelWidth, weight, 12))}</tspan>` : '';
  return `<text class="${labelClass}" text-anchor="end"><title>${esc(full)}</title>${first}${second}</text>`;
}

function barChart(box) {
  const measure = MEASURES[state.measure];
  const runs = chartRuns();
  if (!runs.length) {
    box.innerHTML = `<p class="note">${esc(emptyReason())}</p>`;
    return;
  }
  const labels = chartLabels(runs);
  const known = runs.filter(run => measure.value(run) != null);
  const missing = runs.filter(run => measure.value(run) == null);
  known.sort((a, b) => (measure.higher ? measure.value(b) - measure.value(a) : measure.value(a) - measure.value(b)));
  const ordered = [...known, ...missing];
  const phone = PHONE.matches;
  /* Beside the bars, a label with settings takes two lines, as in the table; on a phone each label sits above its bar
     and takes the chart's width. A label is cut short only when even that is too narrow; its tooltip has the full name. */
  const twoLines = ordered.some(run => labels.get(run).detail);
  const row = phone ? 38 : twoLines ? 34 : 24;
  const top = 6;
  const axis = 40;
  const height = top + ordered.length * row + axis;
  const width = drawWidth(box, height);
  const labelWidth = phone ? 0 : Math.min(210, Math.round(width * 0.36));
  const valueWidth = phone ? 62 : 70;
  const values = known.map(measure.value);
  const domain = !measure.log ? [0, 1] : values.length ? [Math.min(...values) / 1.5, Math.max(...values) * 1.5] : [0.01, 1];
  const left = phone ? 2 : labelWidth + 10;
  const right = width - valueWidth - 8;
  const x = scale(domain, [left, right], measure.log);
  const ticks = measure.log ? ticksLog(...domain) : [0, 0.25, 0.5, 0.75, 1];
  const base = top + ordered.length * row;
  const parts = ticks.map(value =>
    `<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${top}" y2="${base}"/>` +
    `<text class="tick" x="${x(value)}" y="${base + 14}" text-anchor="middle">${measure.log ? logTick(value) : percent(value, 0)}</text>`);
  parts.push(`<line class="axis" x1="${x(domain[0])}" x2="${right}" y1="${base}" y2="${base}"/>`);
  parts.push(`<text class="axis-title" x="${(left + right) / 2}" y="${base + 32}" text-anchor="middle">${esc(measure.axis)}</text>`);
  ordered.forEach((run, index) => {
    const y = top + index * row;
    const value = measure.value(run);
    const maker = state.measure === 'cost' && run.cost_basis === 'maker' && value != null;
    const sample = state.measure === 'latency' && value != null && sampleLabel(run);
    const full = `${run.name} · ${runDetail(run)}: ${value == null ? EMPTY.notMeasured : measure.text(value)}${maker ? ` (${makerCostTip(run)})` : ''}${sample ? ` (${sample})` : ''}`;
    const barTop = phone ? y + 18 : y + (row - 16) / 2;
    const barHeight = phone ? 14 : 16;
    const mid = barTop + barHeight / 2;
    const label = rowLabel(labels, run, y, row, width, labelWidth, full);
    /* The ring spans the row: it shows the focus, and it shades the selected setup's row. */
    const inner = [`<rect class="ring" x="1" y="${y + 1}" width="${width - 2}" height="${row - 2}" rx="3"/>`, label];
    if (value == null) {
      inner.push(`<text class="value nm" x="${width - 4}" y="${mid + 4}" text-anchor="end">${EMPTY.notMeasured}</text>`);
    } else {
      const start = x(domain[0]);
      const colour = isDecision(run) ? ` style="fill:${rankColor(state.measure, value)}"` : '';
      inner.push(`<rect class="${isDecision(run) ? 'bar-decision' : 'bar-chat'}"${colour} x="${start}" y="${barTop}" width="${Math.max(1, x(value) - start)}" height="${barHeight}" rx="2"><title>${esc(full)}</title></rect>`);
      if (state.measure === 'accuracy') {
        const { correct, questions } = counts(run);
        const [low, high] = wilson(correct, questions);
        /* A casing in the panel colour keeps the line apart from the bar it crosses, in both themes. */
        const path = `M${x(low)} ${mid - 3}v6M${x(low)} ${mid}H${x(high)}M${x(high)} ${mid - 3}v6`;
        inner.push(`<path class="whisker-case" d="${path}"/><path class="whisker" d="${path}"/>`);
      }
      inner.push(`<text class="value" x="${width - 4}" y="${mid + 4}" text-anchor="end">${measure.text(value)}${maker ? ` ${FIRST_COST_MARKS.maker.mark}` : ''}${sample ? ` ${SAMPLE_MARK}` : ''}</text>`);
    }
    parts.push(`<g ${markAttributes(run, full)}>${inner.join('')}</g>`);
  });
  const selection = runs.some(run => run.run === state.selected);
  box.classList.toggle('has-selection', selection);
  const where = state.measure === 'accuracy' ? ` on ${integer(questionsInFilter())} questions` : '';
  const latencyNote = state.measure === 'latency' ? ['Local setups ran on our hardware, listed on each setup’s page; API latency includes the network, and via OpenRouter, OpenRouter’s time.'] : [];
  const makerNote = state.measure === 'cost' && ordered.some(run => run.cost_basis === 'maker' && costPer1000(run) != null) ? [MAKER_COST_NOTE] : [];
  const sampleNote = state.measure === 'latency' ? sampleNotes(ordered) : [];
  chartNotes.measures = { notes: [`${measure.label}${where}.`, measure.log ? 'Log scale.' : 'Lines: 95% interval.', ...latencyNote, ...makerNote, ...sampleNote], unlabelled: [] };
  box.innerHTML =
    `<div class="chart-scroll" style="--chart-max:${chartMax()}px"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Bar chart of ${measure.label.toLowerCase()} for ${ordered.length} setups.`)}">${parts.join('')}</svg></div>` +
    legend(state.measure, [...chartNotes.measures.notes, chartScope(runs)].join(' '));
}

function scatterChart(box) {
  const across = MEASURES[state.across];
  const runs = chartRuns();
  const known = runs.filter(run => across.value(run) != null);
  if (!known.length) {
    box.innerHTML = `<p class="note">${esc(runs.length ? `No setup in view has a ${NEEDS[state.across]}.` : emptyReason())}</p>`;
    return;
  }
  const labels = chartLabels(runs);
  const phone = PHONE.matches;
  const pad = { left: 52, right: 14, top: 12, bottom: 46 };
  /* The box keeps its height; with more setups than fit, the chart grows taller and scrolls inside it. */
  const height = Math.max(chartMax(), (phone ? 18 : 24) * known.length + pad.top + pad.bottom);
  const width = drawWidth(box, height);
  const xs = known.map(across.value);
  const ys = known.map(accuracyOf);
  const xDomain = [Math.min(...xs) / 1.6, Math.max(...xs) * 1.6];
  /* Up runs from 5 points below the lowest setup to 5 points above the highest, each end on a 10% line. */
  const yDomain = [Math.max(0, Math.floor((Math.min(...ys) - 0.05) * 10) / 10), Math.min(1, Math.ceil((Math.max(...ys) + 0.05) * 10) / 10)];
  const x = scale(xDomain, [pad.left, width - pad.right], true);
  const y = scale(yDomain, [height - pad.bottom, pad.top], false);
  const parts = [];
  ticksLog(...xDomain).forEach(value => {
    parts.push(`<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${pad.top}" y2="${height - pad.bottom}"/>`);
    parts.push(`<text class="tick" x="${x(value)}" y="${height - pad.bottom + 14}" text-anchor="middle">${logTick(value)}</text>`);
  });
  for (let value = yDomain[0]; value <= yDomain[1] + 0.0001; value += 0.1) {
    parts.push(`<line class="grid" x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}"/>`);
    parts.push(`<text class="tick" x="${pad.left - 6}" y="${y(value) + 4}" text-anchor="end">${percent(value, 0)}</text>`);
  }
  parts.push(`<line class="axis" x1="${pad.left}" x2="${width - pad.right}" y1="${height - pad.bottom}" y2="${height - pad.bottom}"/>`);
  parts.push(`<line class="axis" x1="${pad.left}" x2="${pad.left}" y1="${pad.top}" y2="${height - pad.bottom}"/>`);
  parts.push(`<text class="axis-title" x="${(pad.left + width - pad.right) / 2}" y="${height - 8}" text-anchor="middle">${esc(across.axis)}</text>`);
  parts.push(`<text class="axis-title" transform="translate(13 ${(pad.top + height - pad.bottom) / 2}) rotate(-90)" text-anchor="middle">Accuracy (%)</text>`);
  /* Points stay where their values put them. A label (the name, with the settings that tell same-named setups apart on a
     smaller second line) takes the first free place around its point, nearest first, with a line back to the point when
     it sits further out. A place is free when the label touches no other label, point or line and its own line crosses
     no label or point; where no place is free, the label is left out. Labels are measured bold and placed most accurate
     first, so selecting a setup moves none of them. */
  const room = phone ? 150 : 180;
  const points = known.map(run => ({ run, cx: x(across.value(run)), cy: y(accuracyOf(run)) }));
  const inside = box => box.x0 >= pad.left && box.x1 <= width - pad.right && box.y0 >= 0 && box.y1 <= height - pad.bottom;
  const meets = (a, b) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
  const sizes = new Map(points.map(({ run }) => {
    const { name, detail } = labels.get(run);
    const first = truncate(name, room, 700);
    const second = detail ? truncate(detail, room, 700, 12) : '';
    return [run, { first, second, w: Math.max(textWidth(first, 700), second ? textWidth(second, 700, 12) : 0), h: second ? 30 : 15 }];
  }));
  const dots = points.map(({ cx, cy }) => ({ x0: cx - 7, x1: cx + 7, y0: cy - 7, y1: cy + 7 }));
  /* Places one label in a layout. A lenient label (the selected setup's, when no place is free) may cover points, never
     another label. */
  const fit = (layout, point, lenient = false) => {
    const { run, cx, cy } = point;
    const { first, second, w, h } = sizes.get(run);
    const own = points.indexOf(point);
    const blocksLabel = index => !lenient || index >= points.length || index === own;
    const blocksLine = index => index !== own && (!lenient || index >= points.length);
    const boxAt = ([tx, ty]) => ({ x0: tx - 2, x1: tx + w + 2, y0: ty - 1, y1: ty + h + 1 });
    /* The nearest point of a label's box to its point: the line runs there, and places are tried nearest first. */
    const nearest = box => [Math.min(Math.max(cx, box.x0), box.x1), Math.min(Math.max(cy, box.y0), box.y1)];
    const away = box => { const [lx, ly] = nearest(box); return Math.hypot(lx - cx, ly - cy); };
    const spots = [];
    for (const distance of [0, 16, 32, 48, 64, 88, 112]) {
      const gap = 10 + distance;
      spots.push(
        [cx + 10, cy - h / 2 - distance], [cx + 10, cy - h / 2 + distance], [cx - 10 - w, cy - h / 2 - distance], [cx - 10 - w, cy - h / 2 + distance],
        [cx - w / 2, cy - gap - h], [cx - w / 2, cy + gap], [cx + 4, cy - gap - h], [cx - 4 - w, cy - gap - h], [cx + 4, cy + gap], [cx - 4 - w, cy + gap],
        [cx + gap, cy - h / 2], [cx - gap - w, cy - h / 2],
      );
    }
    spots.sort((a, b) => away(boxAt(a)) - away(boxAt(b)));
    const lineTo = box => (away(box) > 12 ? [cx, cy, ...nearest(box)] : null);
    const spot = spots.find(candidate => {
      const box = boxAt(candidate);
      if (!inside(box) || layout.taken.some((other, index) => blocksLabel(index) && meets(box, other)) || layout.lines.some(line => crosses(line, box))) return false;
      const line = lineTo(box);
      return !line || !layout.taken.some((other, index) => blocksLine(index) && crosses(line, other));
    });
    if (!spot) return false;
    const box = boxAt(spot);
    const line = lineTo(box);
    layout.taken.push(box);
    if (line) layout.lines.push(line);
    layout.placed.set(run, { first, second, spot, line });
    return true;
  };
  const fresh = () => ({ taken: [...dots], lines: [], placed: new Map() });
  const byAccuracy = [...points].sort((a, b) => a.cy - b.cy);
  const chosen = points.find(point => point.run.run === state.selected);
  const layout = fresh();
  byAccuracy.forEach(point => fit(layout, point));
  /* A selected setup's label takes a place left free, over dimmed points if it must; where none is left, the legend names
     the setup, so selecting never takes another label away. */
  if (chosen && !layout.placed.has(chosen.run) && !fit(layout, chosen)) fit(layout, chosen, true);
  const { placed } = layout;
  /* The selected point is drawn larger and last, so no neighbour covers it. */
  [...points].sort((a, b) => (a === chosen) - (b === chosen)).forEach(({ run, cx, cy }) => {
    const maker = state.across === 'cost' && run.cost_basis === 'maker';
    const sample = state.across === 'latency' && sampleLabel(run);
    const tooltip = `${run.name} · ${runDetail(run)}: ${percent(accuracyOf(run))}% right, ${state.across === 'cost' ? `$${across.text(across.value(run))} per 1,000 questions` : `${across.text(across.value(run))} s per request`}${maker ? ` (${makerCostTip(run)})` : ''}${sample ? ` (${sample})` : ''}`;
    parts.push(`<g ${markAttributes(run, tooltip)}><circle class="ring" cx="${cx}" cy="${cy}" r="9"/>` +
      `<circle class="${isDecision(run) ? 'dot-decision' : 'dot-chat'}"${isDecision(run) ? ` style="fill:${rankColor('accuracy', accuracyOf(run))}"` : ''} cx="${cx}" cy="${cy}" r="${run === chosen?.run ? 6 : 4.5}"><title>${esc(tooltip)}</title></circle></g>`);
  });
  placed.forEach(({ first, second, spot: [tx, ty], line }, run) => {
    const selected = state.selected === run.run ? ' is-selected' : '';
    if (line) parts.push(`<line class="leader${selected}" x1="${line[0]}" y1="${line[1]}" x2="${line[2]}" y2="${line[3]}"/>`);
    parts.push(`<text class="label${selected}" x="${tx}" y="${ty + 12}">${esc(first)}${second ? `<tspan class="detail" x="${tx}" y="${ty + 27}">${esc(second)}</tspan>` : ''}</text>`);
  });
  box.classList.toggle('has-selection', Boolean(chosen));
  const missing = runs.length - known.length;
  const unlabelled = byAccuracy.filter(({ run }) => !placed.has(run)).map(({ run }) => labels.get(run).text);
  const notes = [
    `Up: accuracy (%) on ${integer(questionsInFilter())} questions. Across: ${state.across === 'cost' ? '$ per 1,000 questions' : 'median latency per request (s)'}, log scale.`,
    missing ? `${missing} without a ${NEEDS[state.across]} not shown.` : '',
    state.across === 'cost' && known.some(run => run.cost_basis === 'maker') ? MAKER_COST_NOTE : '',
    ...(state.across === 'latency' ? sampleNotes(known) : []),
  ].filter(Boolean);
  chartNotes.tradeoff = { notes, unlabelled };
  const hidden = unlabelled.length;
  const crowded = chosen && !placed.has(chosen.run) ? `Selected: ${labels.get(chosen.run).text}, its label left out so that none overlaps.` : '';
  box.innerHTML =
    `<div class="chart-scroll" style="--chart-max:${chartMax()}px"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Scatter chart: accuracy against ${state.across} for ${known.length} setups. Log scale across.`)}">${parts.join('')}</svg></div>` +
    legend('accuracy', [notes[0], chartScope(runs), ...notes.slice(1), hidden ? `${hidden} label${hidden === 1 ? '' : 's'} left out so that none overlaps; each point's tooltip names it.` : '', crowded].filter(Boolean).join(' '));
}

/* Reading against grammar: every setup the table lists, in the table's order, with its accuracy on all the reading and
   all the grammar questions (each part's correct answers over its questions, from results.json) as two bars on one
   0–100% axis, each bar with its value. The axis's labels sit above the scrolling rows, so they stay in view. */
function readingGrammarChart(box) {
  const tab = TABS[state.tab];
  const runs = sortRows(tab.rows(), tab.columns).map(row => row.run);
  if (!runs.length) {
    box.innerHTML = `<p class="note">${esc(emptyReason())}</p>`;
    return;
  }
  const labels = chartLabels(runs);
  const phone = PHONE.matches;
  const twoLines = runs.some(run => labels.get(run).detail);
  const bar = 12;
  const pair = 2 * bar + 3;
  const row = phone ? 18 + pair + 6 : Math.max(twoLines ? 34 : 24, pair + 8);
  const top = 4;
  const height = top + runs.length * row + 4;
  const width = drawWidth(box, height);
  const labelWidth = phone ? 0 : Math.min(210, Math.round(width * 0.36));
  const left = phone ? 2 : labelWidth + 10;
  const right = width - (phone ? 50 : 56) - 8;
  const x = scale([0, 1], [left, right], false);
  const base = top + runs.length * row;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const parts = ticks.map(value => `<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${top}" y2="${base}"/>`);
  const axis = ticks.map(value => `<text class="tick" x="${x(value)}" y="14" text-anchor="middle">${percent(value, 0)}</text>`).join('');
  runs.forEach((run, index) => {
    const y = top + index * row;
    const shares = ['reading', 'grammar'].map(part => [part, run.groups[part].correct / run.groups[part].questions]);
    const full = `${run.name} · ${runDetail(run)}: reading ${percent(shares[0][1])}%, grammar ${percent(shares[1][1])}%`;
    const barsTop = phone ? y + 18 : y + (row - pair) / 2;
    const inner = [`<rect class="ring" x="1" y="${y + 1}" width="${width - 2}" height="${row - 2}" rx="3"/>`, rowLabel(labels, run, y, row, width, labelWidth, full)];
    shares.forEach(([part, share], at) => {
      const barY = barsTop + at * (bar + 3);
      inner.push(`<rect class="bar-${part}" x="${left}" y="${barY}" width="${Math.max(1, x(share) - left)}" height="${bar}" rx="2"><title>${esc(full)}</title></rect>`);
      inner.push(`<text class="value" x="${width - 4}" y="${barY + bar - 2}" text-anchor="end">${percent(share)}</text>`);
    });
    parts.push(`<g ${markAttributes(run, full)}>${inner.join('')}</g>`);
  });
  box.classList.toggle('has-selection', runs.some(run => run.run === state.selected));
  const [reading, grammar] = ['reading', 'grammar'].map(part => runs[0].groups[part].questions);
  const note = `Accuracy (%) on all ${integer(reading)} reading and all ${integer(grammar)} grammar questions. ${integer(runs.length)} setup${runs.length === 1 ? '' : 's'}: the table's, in its order.`;
  box.innerHTML =
    `<svg width="${width}" height="20" viewBox="0 0 ${width} 20" aria-hidden="true">${axis}</svg>` +
    `<div class="chart-scroll" style="--chart-max:${chartMax()}px"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Bar chart of reading and grammar accuracy for ${runs.length} setups.`)}">${parts.join('')}</svg></div>` +
    `<p class="chart-legend"><span><i class="swatch swatch-reading"></i>Reading</span> <span><i class="swatch swatch-grammar"></i>Grammar</span> <span>${esc(note)}</span></p>`;
}

function renderCharts() {
  const press = (name, current) =>
    document.querySelectorAll(`[data-control="${name}"] [data-${name}]`).forEach(button => button.setAttribute('aria-pressed', String(button.dataset[name] === current)));
  press('measure', state.measure);
  press('across', state.across);
  /* "Show all" names how many setups it would show under the filters, and steps aside when that adds none. */
  const button = document.querySelector('[data-control="show-all"]');
  const every = chartRuns(true).length;
  button.closest('.chart-more').hidden = every === chartRuns(false).length;
  button.setAttribute('aria-pressed', String(state.showAll));
  button.querySelector('[data-show-all-label]').textContent = state.showAll ? 'Show the default setups' : `Show all ${integer(every)}`;
  barChart(document.querySelector('[data-chart="measures"]'));
  scatterChart(document.querySelector('[data-chart="tradeoff"]'));
  readingGrammarChart(document.querySelector('[data-chart="reading-grammar"]'));
  miniChart();
}

/* On a laptop, a small chart beside the intro: accuracy with its 95% interval for the most accurate setups in view (the
   filters' setups, as the table counts them), as one link to the full charts. Its axis fits the intervals shown, each
   end on a 10% line, so short intervals stay visible; where it does not start at 0, a break on the axis and a note under
   it say so. */
const MINI_TOP = 8;
function miniChart() {
  const box = document.querySelector('[data-mini-chart]');
  if (!box || !LAPTOP.matches) return;
  const measure = MEASURES.accuracy;
  const inView = visibleRuns();
  const runs = [...inView].sort((a, b) => measure.value(b) - measure.value(a)).slice(0, MINI_TOP);
  const title = `Accuracy (%), top ${integer(runs.length)} of ${integer(inView.length)} setups in view, with 95% intervals`;
  const head = `<span class="mini-head"><span>${esc(title)}</span><span class="go">Charts ↓</span></span>`;
  box.setAttribute('aria-label', `${title}. Go to the charts.`);
  box.classList.toggle('has-selection', runs.some(run => run.run === state.selected));
  if (!runs.length) {
    box.innerHTML = `${head}<p class="mini-empty">${esc(emptyReason())}</p>`;
    return;
  }
  const labels = chartLabels(runs);
  const style = getComputedStyle(box);
  const width = Math.floor(box.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  const row = 20;
  const labelWidth = Math.min(150, Math.round(width * 0.38));
  const valueWidth = 36;
  const top = 2;
  const base = top + runs.length * row;
  const intervals = new Map(runs.map(run => {
    const { correct, questions } = counts(run);
    return [run, wilson(correct, questions)];
  }));
  const ends = [...intervals.values()];
  const domain = [Math.max(0, Math.floor((Math.min(...ends.map(end => end[0])) - 0.02) * 10) / 10),
    Math.min(1, Math.ceil((Math.max(...ends.map(end => end[1])) + 0.02) * 10) / 10)];
  /* Ticks every 10 points, or every 20 over a wider range; the axis starts on a tick. */
  const step = domain[1] - domain[0] <= 0.5 + 1e-9 ? 0.1 : 0.2;
  domain[0] = Math.floor(domain[0] / step + 1e-9) * step;
  const ticks = [];
  for (let tick = domain[0]; tick <= domain[1] + 1e-9; tick += step) ticks.push(tick);
  const broken = domain[0] > 1e-9;
  const height = base + (broken ? 36 : 20);
  const x = scale(domain, [labelWidth + 8, width - valueWidth - 6], false);
  const parts = ticks.map(value =>
    `<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${top}" y2="${base}"/>` +
    `<text class="tick" x="${x(value)}" y="${base + 14}" text-anchor="middle">${percent(value, 0)}</text>`);
  parts.push(`<line class="axis" x1="${x(domain[0])}" x2="${x(domain[1])}" y1="${base}" y2="${base}"/>`);
  if (broken) {
    const at = x(domain[0]) + 7;
    parts.push(`<path class="axis-break" d="M${at - 4} ${base + 4}l4 -8M${at} ${base + 4}l4 -8"/>`);
    parts.push(`<text class="axis-note" x="${labelWidth + 8}" y="${base + 31}">Axis starts at ${percent(domain[0], 0)}%, not 0.</text>`);
  }
  runs.forEach((run, index) => {
    const mid = top + index * row + row / 2;
    const value = measure.value(run);
    const [low, high] = intervals.get(run);
    const selected = run.run === state.selected;
    const label = `<text x="${labelWidth}" y="${mid + 4}" text-anchor="end">${esc(truncate(labels.get(run).text, labelWidth, selected ? 700 : 400, 12))}</text>`;
    const figure = `<text class="value" x="${width}" y="${mid + 4}" text-anchor="end">${measure.text(value)}</text>`;
    const whisker = `M${x(low)} ${mid - 3}v6M${x(low)} ${mid}H${x(high)}M${x(high)} ${mid - 3}v6`;
    parts.push(`<g class="row${selected ? ' is-selected' : ''}">${label}<path class="whisker" d="${whisker}"/>` +
      `<circle class="${isDecision(run) ? 'dot-decision' : 'dot-chat'}"${isDecision(run) ? ` style="fill:${rankColor('accuracy', value)}"` : ''} cx="${x(value)}" cy="${mid}" r="4"/>${figure}</g>`);
  });
  box.innerHTML = `${head}<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true" focusable="false">${parts.join('')}</svg>` +
    `<span class="mini-legend">${scaleLegend('accuracy')}</span>`;
}

/* A chart as a PNG that keeps what it shows: the condition (measure and filters), the setups, the chart's notes with any
   setup it could not label, and the results version, with the page's address. Text is wrapped to the chart's width;
   colours and type are copied from the page, so it matches the theme in view. */
async function downloadChart(name) {
  const box = document.querySelector(`[data-chart="${name}"]`);
  const svg = box.querySelector('svg');
  if (!svg) return;
  const width = Number(svg.getAttribute('width'));
  const height = Number(svg.getAttribute('height'));
  const clone = svg.cloneNode(true);
  const sources = svg.querySelectorAll('*');
  clone.querySelectorAll('*').forEach((target, index) => {
    const style = getComputedStyle(sources[index]);
    for (const property of ['fill', 'stroke', 'stroke-width', 'stroke-linejoin', 'paint-order', 'opacity', 'font-family', 'font-size', 'font-weight']) {
      target.style.setProperty(property, style.getPropertyValue(property));
    }
  });
  const root = getComputedStyle(document.documentElement);
  const colour = token => root.getPropertyValue(token).trim();
  const font = esc(getComputedStyle(document.body).fontFamily);
  const { notes, unlabelled } = chartNotes[name];
  const texts = [];
  let y = 0;
  const write = (content, size, weight, fill) => wrap(content, width - 20, weight, size).forEach(line => {
    y += Math.round(size * 1.4);
    texts.push(`<text x="10" y="${y}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${fill}">${esc(line)}</text>`);
  });
  write(name === 'measures' ? `${MEASURES[state.measure].label} · ${chartCondition()}` : `Trade-off: accuracy against ${state.across} · ${chartCondition()}`, 14, 700, colour('--text'));
  write(chartScope(chartRuns()), 12, 400, colour('--text-2'));
  const head = y + 12;
  y = head + height + 20;
  /* The legend, as on the page: the decision models' colours from worst to best with each end's value and which way is
     better, then the chat models' grey; an item that does not fit on the row starts the next one. */
  const scaleName = name === 'measures' ? state.measure : 'accuracy';
  const [worst, best] = rankEnds[scaleName];
  const stops = SETTINGS.rankScale.map((stop, index, all) => `<stop offset="${index / (all.length - 1)}" stop-color="${stop}"/>`).join('');
  texts.push(`<defs><linearGradient id="ramp">${stops}</linearGradient></defs>`);
  let x = 10;
  const place = itemWidth => {
    if (x > 10 && x + itemWidth > width - 10) {
      x = 10;
      y += 18;
    }
    const at = x;
    x += itemWidth + 8;
    return at;
  };
  const label = text => {
    const at = place(textWidth(text));
    texts.push(`<text x="${at}" y="${y}" font-family="${font}" font-size="12" fill="${colour('--text-2')}">${esc(text)}</text>`);
  };
  label(`Decision models: worst ${endText(scaleName, worst)}`);
  const rampAt = place(48);
  texts.push(`<rect x="${rampAt}" y="${y - 10}" width="48" height="10" rx="2" fill="url(#ramp)" stroke="${colour('--mark-edge')}"/>`);
  label(`best ${endText(scaleName, best)} (${MEASURES[scaleName].higher ? 'higher' : 'lower'} is better)`);
  const chatAt = place(14 + textWidth('Chat model'));
  texts.push(`<rect x="${chatAt}" y="${y - 10}" width="10" height="10" rx="2" fill="${colour('--data-chat')}"/>` +
    `<text x="${chatAt + 14}" y="${y}" font-family="${font}" font-size="12" fill="${colour('--text-2')}">Chat model</text>`);
  const left = unlabelled.length;
  write([...notes, left ? `${left} label${left === 1 ? '' : 's'} left out so that none overlaps: ${unlabelled.join('; ')}.` : ''].filter(Boolean).join(' '), 12, 400, colour('--text-2'));
  y += 6;
  write(`Results ${data.results_version} · answer key version ${SETTINGS.keyVersion} · ${SETTINGS.siteAddress}`, 12, 400, colour('--text-2'));
  const total = y + 12;
  const markup =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${total}" viewBox="0 0 ${width} ${total}">` +
    `<rect width="100%" height="100%" fill="${getComputedStyle(box.closest('.panel')).backgroundColor}"/>` +
    `<g transform="translate(0 ${head})">${clone.innerHTML}</g>${texts.join('')}</svg>`;
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }));
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('the chart could not be drawn'));
      image.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = 2 * width;
    canvas.height = 2 * total;
    const context = canvas.getContext('2d');
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `decision-models-${name === 'measures' ? state.measure : `accuracy-${state.across}`}-${data.results_version}.png`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/* ---- Page address and history ---- */

/* The open tab and, on the Routing tab, its four choices live in the page URL, so a link opens that exact view:
   ?tab=routing&llm=astra&per-request=16&rule=half&test=replay. The filters stay out of the URL. */
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

/* The filters, the highlighted setup and the chart choices, kept with the browser's history entry rather than the URL,
   so Back from a model's page returns to the same tab and filters. */
function remembered() {
  const { part, topic, type, qpr, search, selected, filtersOpen, sort, measure, across, showAll, view } = state;
  return { part, topic, type, qpr, picked: [...state.picked], search, selected, filtersOpen, sort, measure, across, showAll, view };
}

function restore() {
  const saved = window.history.state?.v3;
  if (!saved) return;
  Object.assign(state, { ...saved, picked: new Set(saved.picked) });
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
  window.history.replaceState({ ...(window.history.state ?? {}), v3: remembered() }, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

function render() {
  document.querySelectorAll('[role="tab"]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.tab === state.tab)));
  const definition = document.querySelector('[data-definition]');
  definition.textContent = DEFINITIONS[state.tab] ?? '';
  definition.hidden = !DEFINITIONS[state.tab];
  renderFilters();
  renderBoard();
  placeCharts();
  updateSwipe();
  renderCharts();
  writeUrl();
}

/* ---- Events ---- */

/* Rendering replaces the table and the charts; the control that had the focus gets it back. */
const FOCUS_KEYS = ['select', 'sort', 'routeLlm', 'routeQpr', 'routeMode', 'control', 'download'];
function focusSelector(element) {
  if (!element || element === document.body) return null;
  const key = FOCUS_KEYS.find(name => element.dataset?.[name] != null);
  if (!key) return null;
  const attribute = `data-${key.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`)}`;
  const place = element.closest('[data-chart]') ? `[data-chart="${element.closest('[data-chart]').dataset.chart}"] ` : element.closest('#board') ? '#board ' : '';
  return `${place}${element.tagName.toLowerCase()}[${attribute}="${CSS.escape(element.dataset[key])}"]`;
}
function renderKeepingFocus() {
  const selector = focusSelector(document.activeElement);
  render();
  if (selector && !document.activeElement?.matches(selector)) document.querySelector(selector)?.focus();
}

const toggleSelected = id => {
  state.selected = state.selected === id ? null : id;
};

/* A label in the summary opens its tab and brings the leaderboard into view, with the tab's key focused. */
function openTab(tab) {
  state.tab = tab;
  state.sort = defaultSort(tab);
  state.view = 'table';
  render();
  document.getElementById(`tab-${tab}`).focus({ preventScroll: true });
  document.querySelector('.board-panel').scrollIntoView({ behavior: REDUCED_MOTION.matches ? 'auto' : 'smooth', block: 'start' });
}

function onClick(event) {
  const jump = event.target.closest('a[data-goto-tab]');
  if (jump) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    openTab(jump.dataset.gotoTab);
    return;
  }
  const button = event.target.closest('button');
  if (!button) {
    const mark = event.target.closest('.chart-box .mark');
    const row = event.target.closest('#board tbody tr[data-run]');
    if (mark) toggleSelected(Number(mark.dataset.select));
    else if (row && !event.target.closest('a, .hint')) toggleSelected(Number(row.dataset.run));
    else return;
    renderKeepingFocus();
    return;
  }
  const { dataset } = button;
  if (dataset.select) toggleSelected(Number(dataset.select));
  else if (dataset.part) {
    state.part = dataset.part;
    if (state.topic != null && state.part !== 'all' && unitPart(units().find(unit => unit.number === state.topic)) !== state.part) state.topic = null;
  } else if (dataset.type) state.type = dataset.type;
  else if (dataset.qpr) state.qpr = dataset.qpr === 'all' ? 'all' : Number(dataset.qpr);
  else if (dataset.tab) {
    state.tab = dataset.tab;
    state.sort = defaultSort(state.tab);
  } else if (dataset.sort) {
    const column = TABS[state.tab].columns.find(item => item.key === dataset.sort);
    state.sort = state.sort.key === column.key ? { key: column.key, descending: !state.sort.descending } : { key: column.key, descending: !column.low };
  } else if (dataset.routeLlm) state.route.llm = dataset.routeLlm;
  else if (dataset.routeQpr) state.route.qpr = Number(dataset.routeQpr);
  else if (dataset.routeMode) state.route.mode = dataset.routeMode;
  else if (dataset.measure) state.measure = dataset.measure;
  else if (dataset.across) state.across = dataset.across;
  else if (dataset.view) state.view = dataset.view;
  else if (dataset.control === 'filters') state.filtersOpen = !state.filtersOpen;
  else if (dataset.control === 'reset') {
    if (button.getAttribute('aria-disabled') === 'true') return;
    resetFilters();
  } else if (dataset.control === 'show-all') state.showAll = !state.showAll;
  else if (dataset.control === 'clear-picked') {
    state.picked.clear();
    renderPicker();
  } else if (dataset.download) {
    downloadChart(dataset.download);
    return;
  } else return;
  renderKeepingFocus();
}

function onKeydown(event) {
  const mark = event.target.closest?.('.chart-box .mark');
  if (!mark || (event.key !== 'Enter' && event.key !== ' ')) return;
  event.preventDefault();
  toggleSelected(Number(mark.dataset.select));
  renderKeepingFocus();
}

function onChange(event) {
  const target = event.target;
  const control = target.dataset.control;
  if (control === 'topic') state.topic = target.value ? Number(target.value) : null;
  else if (control === 'route-rule') state.route.rule = target.value;
  else if (target.closest('.model-list') && target.type === 'checkbox') {
    const id = Number(target.value);
    if (target.checked) state.picked.add(id);
    else state.picked.delete(id);
  } else return;
  renderKeepingFocus();
}

function onInput(event) {
  if (event.target.dataset.control !== 'model-search') return;
  state.search = event.target.value;
  applySearch();
  writeUrl();
}

/* The page's own text paints before the results, a large file, start to load: the browser's first contentful paint and
   one frame more, or 300 ms where that paint is not reported (a background tab, or a browser without paint timing). */
const afterFirstPaint = () => new Promise(resolve => {
  const timer = setTimeout(resolve, 300);
  const done = () => {
    clearTimeout(timer);
    requestAnimationFrame(() => setTimeout(resolve));
  };
  try {
    new PerformanceObserver((list, observer) => {
      if (!list.getEntriesByName('first-contentful-paint').length) return;
      observer.disconnect();
      done();
    }).observe({ type: 'paint', buffered: true });
  } catch (error) {
    clearTimeout(timer);
    resolve();
  }
});

async function start() {
  await afterFirstPaint();
  try {
    const response = await fetch(RESULTS_URL);
    if (!response.ok) throw new Error(`${RESULTS_URL}: ${response.status}`);
    data = await response.json();
  } catch (error) {
    /* Without the results the controls cannot work: the page shows every setup, as without JavaScript. */
    document.documentElement.classList.remove('js');
    const note = document.createElement('p');
    note.className = 'load-error';
    note.setAttribute('role', 'alert');
    note.innerHTML = `<span class="icon" aria-hidden="true">⚠</span> ${esc(`Could not load the results (${error.message}). The table below shows all questions.`)}`;
    document.getElementById('board').before(note);
    return;
  }
  byId = new Map(data.runs.map(run => [run.run, run]));
  setRankEnds();
  readUrl();
  state.sort = defaultSort(state.tab);
  restore();
  renderPicker();
  render();
  document.addEventListener('click', onClick);
  document.addEventListener('keydown', onKeydown);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
  let width = window.innerWidth;
  new ResizeObserver(() => {
    if (window.innerWidth === width) return;
    width = window.innerWidth;
    updateSwipe();
    renderCharts();
  }).observe(document.body);
  PHONE.addEventListener('change', render);
  LAPTOP.addEventListener('change', renderCharts);
}

start();
