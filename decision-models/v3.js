'use strict';

/* The home page: filters, the four leaderboard tabs, the routing diagram and the two charts, drawn from data/home.json
   and data/home-more.json, which build_site.py writes from results.json (home_data). Every number is read from them:
   accuracy for a part or topic and its 95% interval from the counts they store, with the Wilson formula, and the routing
   numbers from the same replays and live tests. The open tab and the
   Routing choices live in the URL; the filters, the highlighted setup and the chart choices live in the browser's
   history entry, so Back returns to them. Without JavaScript the page keeps the plain table build_site.py writes. */

const SETTINGS = JSON.parse(document.getElementById('v3-settings').textContent);
/* The data files' addresses as the page gives them, with their content's version (Site asset in sitebuild/site.py), so
   a cached file of another build is never paired with this page: HOME_URL, preloaded by the page, holds what the first
   draw reads; MORE_URL the runs' whole confidence and the cascades, loaded when a part needs them (loadMore). A page
   cached from before these files gives neither; it gets their plain addresses. */
const HOME_URL = SETTINGS.homeUrl || 'data/home.json';
const MORE_URL = SETTINGS.moreUrl || 'data/home-more.json';
/* What a chart box shows until it is drawn (index.html's chart boxes start with it), and what a tab waiting for
   MORE_URL shows, as the Cost table's box starts with. */
const LOADING = '<p class="note" role="status">Loading charts…</p>';
const LOADING_TABLE = '<p class="note" role="status">Loading the table…</p>';

/* Why a cell has no value. A cost is missing only for a setup on our own hardware with no estimate (billing 'local',
   no request time): it reads No list price; a value nobody measured reads Not measured. */
const EMPTY = {
  notMeasured: 'Not measured',
  noListPrice: 'No list price',
  allOnly: 'Computed on all questions only',
};
const INTERVAL_TIP = 'To test two setups against each other, use Compare.';
const LATENCY_TIP =
  'Latency: the time from sending one request to receiving its answer, measured from our computer, network and any retries within the request included. Median request. Local setups ran on our own hardware.';
const COST_TIP =
  'Estimated from list prices and recorded token use. A setup on our own hardware is estimated at its maker’s list price for the same model, else a public host’s for the same weights, else from its GPU time at a public cloud price; these are estimates, not measured spending.';
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
/* A first model's cost basis in the Routing tab (page_config.json first_cost_marks): its maker's list price for the
   same model (no mark beside the saving: its tooltip and the note say so), or † where it ran on our hardware without
   one; each with its tooltip and note. */
const FIRST_COST_MARKS = SETTINGS.firstCostMarks;
const firstCostMark = run => (run.cost_basis === 'maker' ? FIRST_COST_MARKS.maker : run.api_equivalent_usd == null ? FIRST_COST_MARKS[run.billing] ?? null : null);
/* What a setup on our hardware says in its cost's tooltip: the maker's list price for the same model or a host's for
   the same weights (named), or its GPU-time estimate (page_config.json first_cost_marks); null for any other cost. */
const basisCostTip = run => {
  const price = data.prices.find(item => item.provider === run.provider && item.model === run.model);
  if (run.cost_basis === 'maker') return `Estimated at ${price?.basis ?? 'its maker’s list price for the same model'}; our hardware cost is not measured.`;
  if (run.cost_basis === 'weights') return `${FIRST_COST_MARKS.weights.tip} Price: ${price.basis}, read ${price.date}.`;
  return run.cost_basis === 'gpu' ? FIRST_COST_MARKS.gpu.tip : null;
};
/* A cost that is an upper-bound estimate (cost_upper_bound: web grounding's search fee counted for every request): ≤
   before the value, with its tooltip and note (page_config.json first_cost_marks.upper). */
const UPPER_MARK = FIRST_COST_MARKS.upper;
const upperPrefix = run => (run.cost_upper_bound ? `${UPPER_MARK.mark} ` : '');
/* How a cost was counted, for its tooltip, where it is not plain API list price (Site.cost_tip in sitebuild/site.py). */
const costTip = run => [basisCostTip(run), run.cost_upper_bound ? UPPER_MARK.tip : null].filter(Boolean).join(' ') || null;
/* The one line on how the costs were counted, under a chart or table with costs, for the setups it shows: values carry
   no basis mark, so the line names the bases (Site.cost_note in sitebuild/site.py). */
const costNote = runs => [
  'Costs: API list prices and recorded token use.',
  runs.some(run => run.cost_basis === 'maker' && costPer1000(run) != null) ? 'Setups on our own GPUs: the maker’s list price for the same model (each value’s tooltip names it); our hardware cost is not measured.' : '',
  ...['weights', 'gpu'].map(basis => (runs.some(run => run.cost_basis === basis) ? FIRST_COST_MARKS[basis].note : '')),
  runs.some(run => costPer1000(run) == null && run.billing === 'local') ? 'No list price: on our own GPUs, with no estimate.' : '',
  runs.some(run => run.cost_upper_bound && costPer1000(run) != null) ? `${UPPER_MARK.mark} ${UPPER_MARK.note}` : '',
].filter(Boolean).join(' ');
const CONFIDENCE_NOTE = [
  'Every decision model that ranks its answers better than chance ranks them less well on grammar than on reading. A probability from an API is not calibrated by itself. Luna’s two setups also differ in request format (1 against 16 questions).',
];
const ROUTING_NOTES = [
  'Replay: both models’ recorded answers. Live: the decision model’s recorded answers, with new calls to the LLM. Savings are estimates from API prices, and larger at 1 question per request: each question the LLM skips costs more.',
  'In a live test with Sonnet at 1 question per request, accuracy fell 4.73 points: Decider v1.1 kept 51%, with a cutoff chosen at 16 per request. A cutoff chosen at 1 per request keeps 29%, and accuracy falls 0.16 points (replay). Choose the cutoff in the format you will run.',
  'SubQ Snap Preview’s place depends on the LLM: thirteenth among decision models in front of Sonnet 5.5 high (16 per request), twentieth in front of Opus 5.5 low, eighteenth in front of Astra low. Its most confident fifth of answers was 98.6% right; Decider v1.1’s was 99.3%, the hosted GLiDE’s 99.5%.',
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
const costMissing = run => (run.billing === 'local' ? EMPTY.noListPrice : EMPTY.notMeasured);
const MISSING = tip(EMPTY.allOnly);

/* ---- Runs ---- */

const reasoningLabel = reasoning => (['off', 'on', 'none'].includes(reasoning) ? `reasoning ${reasoning}` : `${reasoning} reasoning`);
const requestSize = size => `${integer(size)} question${size === 1 ? '' : 's'} per request`;
/* A setup's settings, for its tooltips: variant, reasoning and request size. Names in charts and tables carry only what
   tells two setups apart (chartLabels); the settings stay in tooltips and on the model page. */
const runDetail = run =>
  [run.variant, run.reasoning && reasoningLabel(run.reasoning), requestSize(run.questions_per_request)].filter(Boolean).join(' · ');
/* A setup's name in a row, with its route where the same model ID runs as both kinds of model (page_config.json's lists,
   build_site.py route_labels): "GPT-6 Luna (Decisions API)" and "GPT-6 Luna (chat API)". */
const routed = (run, name) => (SETTINGS.routeLabels[run.run] ? `${name} (${SETTINGS.routeLabels[run.run]})` : name);
const rowName = run => routed(run, run.name);
const isDecision = run => SETTINGS.decisionProviders.includes(run.provider) && !SETTINGS.notDecisionModels.includes(run.model);
const costPer1000 = run => (run.api_equivalent_usd == null ? null : (1000 * run.api_equivalent_usd) / run.answered_questions);
/* A cost in the reader's unit (site.js: per 1,000 or per 1M questions), for the charts and cells that show it; sorting
   and ratios stay on costPer1000. */
const costShown = run => {
  const value = costPer1000(run);
  return value == null ? null : value * costScale();
};
const latencyOf = run => run.latency?.median_request_seconds ?? null;

let data;
let byId;
/* The parts marked `more` (the Calibration chart, the Confidence and Routing tabs) read MORE_URL's runs' confidence or
   cascades: until it is in they show LOADING, or the error that stopped it. It loads once, when such a tab opens or the
   Calibration chart comes within a screen of the view (nearView), then the page draws again. When the Calibration
   chart is above the view, what is in view stays put as the chart takes its height, as browsers with scroll anchoring
   keep it; this does the same in those without. */
const more = { promise: null, ready: false, error: null };
function loadMore() {
  more.promise ??= fetch(MORE_URL)
    .then(response => {
      if (!response.ok) throw new Error(`${MORE_URL}: ${response.status}`);
      return response.json();
    })
    .then(extra => {
      data.runs.forEach(run => {
        run.confidence = extra.confidence[run.run];
      });
      data.cascades = extra.cascades;
      more.ready = true;
    }, error => {
      more.error = error;
    })
    .then(() => {
      const box = document.querySelector('[data-chart="gap"]');
      const before = box.getBoundingClientRect();
      renderKeepingFocus();
      const after = box.getBoundingClientRect();
      if (before.bottom <= 0 && after.top === before.top) window.scrollBy(0, after.height - before.height);
    });
  return more.promise;
}
const waitingForMore = (loading = LOADING) =>
  more.error ? `<p class="note" role="alert">${esc(`Could not load this part (${more.error.message}).`)}</p>` : loading;
const nearView = new IntersectionObserver(entries => {
  if (!entries.some(entry => entry.isIntersecting)) return;
  nearView.disconnect();
  loadMore();
}, { rootMargin: '100% 0px' });

/* Names where setups show together (a chart, a table): each setup's full name (rowName) and, only where two of them
   would read the same, what tells them apart: the variant, the reasoning setting, the request size ("high reasoning,
   16 per request"), as detail, a smaller second line in a chart. Site.names in sitebuild/site.py writes the same. */
function chartLabels(runs) {
  const labels = new Map();
  runs.forEach(run => {
    const name = rowName(run);
    const same = runs.filter(other => rowName(other) === name);
    const differs = field => new Set(same.map(other => other[field])).size > 1;
    const detail = [
      differs('variant') && run.variant,
      differs('reasoning') && run.reasoning && reasoningLabel(run.reasoning),
      differs('questions_per_request') && `${integer(run.questions_per_request)} per request`,
    ].filter(Boolean).join(', ');
    labels.set(run, { name, detail, text: detail ? `${name} (${detail})` : name });
  });
  return labels;
}

/* The filters, each also a key in the page URL (readUrl, writeUrl). web: every setup ('all'), those that searched the
   web before answering ('with', perplexity_mode) or the others ('without'). */
const DEFAULT_FILTERS = { part: 'all', topic: null, qpr: 'all', web: 'all' };
const state = {
  ...DEFAULT_FILTERS,
  picked: new Set(),
  selected: null,
  /* The model group the charts and the full ranking show, from the URL's ?models= (site.js): every setup ('all',
     decision and chat models ranked together), the decision models ('decision'), the chat and general models ('chat')
     or the small models ('small', chat and decision models of at most SETTINGS.smallModels parameters in total). */
  models: 'all',
  tab: 'accuracy',
  sort: { key: 'accuracy', descending: true },
  route: { llm: 'opus', qpr: 1, rule: 'half', mode: 'replay' },
  across: 'cost',
};
/* Each tab's order when it opens: the Routing tab by the share of the LLM's questions taken, the Stability tab by
   changed answers, most first (ties by the same wrong answer in all five runs, the column's tie, most first), the
   others by accuracy. */
const DEFAULT_SORTS = { routing: { key: 'share', descending: true }, stability: { key: 'changed', descending: true } };
const defaultSort = tab => ({ ...(DEFAULT_SORTS[tab] ?? { key: 'accuracy', descending: true }) });
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

/* The model groups of ?models=: each one's table heading, and its setups in words for the chart notes. */
const MODEL_GROUPS = {
  all: { title: 'All models', every: 'every setup, decision and chat models together', of: count => `the ${count} setups, decision and chat models together` },
  decision: { title: 'Decision models', every: 'every decision model', of: count => `the ${count} decision models` },
  chat: { title: 'Chat models', every: 'every chat and general model', of: count => `the ${count} chat and general models` },
  small: { title: 'Small models', every: 'every small model setup, decision and chat models together', of: count => `the ${count} small model setups` },
};
/* A setup of a small model: its maker's disclosed total (a mixture of experts by its total) at most the threshold
   (page_config.json small_models), or one of the setups it holds by name (SETTINGS.smallByName, "provider|model"); a
   model whose maker discloses no size never is otherwise. As Site.small. */
const isSmall = run => (SETTINGS.smallByName || []).includes(`${run.provider}|${run.model}`)
  || (run.parameters != null && run.parameters <= SETTINGS.smallModels);
const inGroup = run => state.models === 'all' || (state.models === 'small' ? isSmall(run) : isDecision(run) === (state.models === 'decision'));
/* Every setup of the group in view, whatever the filters. */
const groupRuns = () => data.runs.filter(inGroup);

/* A setup that searched the web before answering (perplexity_mode), and the small badge beside its displayed name in a
   list, left out where that name already says "with web". */
const usesWeb = run => Boolean(run.perplexity_mode);
const saysWeb = name => /with web/i.test(name);
const webBadge = (run, name) => (usesWeb(run) && !saysWeb(name) ? ' <span class="web-badge">with web</span>' : '');

/* The group's setups under the request-size and web filters and the models picked: the table's rows and the charts'
   setups. */
function visibleRuns() {
  return groupRuns().filter(
    run =>
      (state.qpr === 'all' || run.questions_per_request === state.qpr) &&
      (state.web === 'all' || usesWeb(run) === (state.web === 'with')) &&
      (!state.picked.size || state.picked.has(run.run)),
  );
}

/* ---- Leaderboard ---- */

/* A setup's name cell: its name with what tells it apart from the other rows (chartLabels); its settings and kind in
   the link's tooltip and on its model page. */
function modelCell(run, labels) {
  const { text } = labels.get(run);
  const about = `${runDetail(run)} · ${isDecision(run) ? 'Decision model' : 'Chat model'}`;
  return `<td class="model"><div class="who"><button type="button" class="pick" data-select="${run.run}" aria-pressed="${state.selected === run.run}" ` +
    `aria-label="Highlight ${esc(text)} in the charts"><span class="lamp" aria-hidden="true"></span></button>` +
    `<span class="names">${familyIcon(run)}<a class="model-name" href="models/${run.run}/" title="${esc(about)}">${esc(text)}</a>${webBadge(run, text)}</span></div></td>`;
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
/* A run's answers at the sure threshold: how many were right, how many it kept (answered at that confidence or more)
   and how many it skipped (the other scored questions; confidence counts only the scored ones, not those excluded since
   a run); null without confidence scores. */
const sureCounts = run => {
  const sure = run.confidence?.sure;
  return sure ? { right: sure.correct, kept: sure.questions, skipped: data.questions - sure.questions, invalid: run.invalid || 0 } : null;
};

/* The Confidence tab's guide above the table: each term, then what it means. */
const CONFIDENCE_GUIDE = [
  ['Confidence', 'the probability a model gives to its own answer.'],
  ['Calibration', 'whether that probability matches how often the model is right. Of 100 answers scored 80%, about 80 should be right.'],
  [
    `Correct answers at ${pct(SETTINGS.threshold, 0)}`,
    `answers scored ${pct(SETTINGS.threshold, 0)} or more that were right: the score a model would get if it answered only those questions. Kept: the questions it answered at that confidence; skipped: the questions not kept, answered with less than ${pct(SETTINGS.threshold, 0)} confidence or without a valid answer.`,
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
    columns: [
      { key: 'accuracy', label: 'Accuracy (%)', tip: INTERVAL_TIP, value: accuracyOf, cell: accuracyCell },
      partColumn('reading', 'Reading (%)'),
      partColumn('grammar', 'Grammar (%)'),
      {
        key: 'latency', label: 'Median latency per request (s)', className: 'unit-long', tip: LATENCY_TIP, low: true, value: latencyOf,
        cell: run => latencyCell(run),
      },
      {
        key: 'cost', get label() { return `$ ${costLabel()}`; }, className: 'unit-long', tip: COST_TIP, low: true, value: costPer1000,
        cell: run => costCell(run),
      },
    ],
  },
  confidence: {
    more: true,
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
        cell: run => {
          if (filtered()) return MISSING;
          const sure = sureCounts(run);
          return `${integer(sure.right)} of ${integer(sure.kept)} kept<span class="small">${integer(sure.skipped)} skipped${sure.invalid ? `, ${integer(sure.invalid)} without a valid answer` : ''}</span>`;
        },
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
  routing: { more: true, rows: () => routingRows(), notes: ROUTING_NOTES },
  stability: {
    rows: () => {
      const shown = new Set(visibleRuns());
      return data.repeats.map(item => ({ item, run: repeatRun(item) })).filter(({ run }) => run && shown.has(run));
    },
    note: STABILITY_NOTE,
    columns: [
      {
        key: 'changed', label: 'Answers changed in 5 runs', low: true, tie: 'same-wrong',
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
  /* Object.create keeps a getter, as the cost column's label (its unit follows the reader's choice). */
  TABS[name].columns = TABS[name].columns.map(column => Object.assign(Object.create(column), { value: row => column.value(row.run), cell: row => column.cell(row.run) }));
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
/* The request sizes we ran an LLM at, smallest first: [1, 16], or [16] for the LLMs run at 16 questions per request only. */
const routeSizes = llm => Object.keys(llm.runs).map(Number).sort((a, b) => a - b);
/* An LLM without a run at the chosen request size takes its largest: picking a 16-only LLM on 1 per request moves to 16. */
const fitRouteSize = () => {
  const sizes = routeSizes(routeLlm());
  if (!sizes.includes(state.route.qpr)) state.route.qpr = sizes[sizes.length - 1];
};

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
      taken: { kept: test.routed, total: test.held_out },
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
      numbers = { share: item.kept / total, taken: { kept: item.kept, total }, change: item.difference, perThousand: item.usd_per_1000 };
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

/* The chosen LLM's run as the Routing tab names it: its name with its reasoning level ("Claude Opus 5.5, high
   reasoning"), as the same model runs at two levels. */
const routeLlmName = run => (run.reasoning ? `${run.name}, ${reasoningLabel(run.reasoning)}` : run.name);
function routeTitle() {
  const llm = byId.get(routeLlm().runs[state.route.qpr]);
  return [routeLlmName(llm), requestSize(state.route.qpr), routeRule().label, state.route.mode].join(' · ');
}

/* The questions the shown numbers cover: a live test's held-out questions (pipelines[].held_out, the chosen LLM, size
   and rule first); the half rule's replay, the held-out half of each random split (passages stay whole, so its size
   varies about half the questions); a fixed rule's replay, every question. */
function routeScope() {
  if (state.route.mode === 'live') {
    const llm = routeLlm();
    const measured = data.pipelines.filter(item => item.measured);
    const test = measured.find(item => item.frontier === llm.runs['16'] && item.batch_size === state.route.qpr && item.rule === routeRule().live) ?? measured[0];
    return { count: test.held_out, text: `${integer(test.held_out)} questions: the live test’s held-out half` };
  }
  if (state.route.rule === 'half') {
    const half = Math.floor(data.questions / 2);
    const splits = data.cascades?.[0]?.held_out.splits;
    return { count: half, about: true, text: `About ${integer(half)} questions: the held-out half of the ${integer(data.questions)}${splits ? `, means over ${integer(splits)} random splits` : ''}` };
  }
  return { count: data.questions, text: `All ${integer(data.questions)} questions` };
}

const ROUTING_COLUMNS = [
  { key: 'share', label: 'Share of the LLM’s questions taken (%)', tip: SHARE_TIP, value: row => row.numbers?.share ?? null,
    cell: row => shareCell(row) },
  { key: 'change', label: 'Accuracy change (points)', value: row => row.numbers?.change ?? null,
    cell: row => (row.numbers ? signed(100 * row.numbers.change, 2) : NM) },
  { key: 'saving', label: 'Saving (%)', value: row => row.numbers?.saving ?? null, cell: row => savingCell(row, n => minus(percent(n.saving, 0))) },
  { key: 'saving-usd', get label() { return `Saving ($ ${costLabel()})`; }, value: row => row.numbers?.savingUsd ?? null,
    cell: row => savingCell(row, n => minus((n.savingUsd < 0 ? '-' : '') + costNumber(Math.abs(n.savingUsd) * costScale()))) },
];
TABS.routing.columns = ROUTING_COLUMNS;

function savingCell(row, format) {
  if (!row.numbers || row.numbers.saving == null) return NM;
  const mark = firstCostMark(row.run);
  if (!mark) return format(row.numbers);
  return mark === FIRST_COST_MARKS.maker ? tip(mark.tip, format(row.numbers)) : `${tip(mark.tip, format(row.numbers))}<span class="mark">${mark.mark}</span>`;
}

/* A setup's cost in the reader's unit: the value alone (≤ before an upper bound), its basis in its tooltip. */
function costCell(run) {
  const value = costShown(run);
  if (value == null) return `<span class="nm">${costMissing(run)}</span>`;
  const text = costTip(run) ? tip(costTip(run), costNumber(value)) : costNumber(value);
  return run.cost_upper_bound ? `<span class="mark">${UPPER_MARK.mark}</span> ${text}` : text;
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
  return label ? `${tip(label, secondsText(value))}<span class="mark">${SAMPLE_MARK}</span>` : secondsText(value);
}

/* The share taken, with where every question goes under it: a bar of three parts with their values printed, green for
   kept and right, hatched red for kept but wrong, grey for sent to the LLM. A gap keeps green and red apart; "Not
   recorded" where no split was stored. The bar sits in the space the column's heading leaves, so the table keeps its
   width. */
function shareCell(row) {
  if (!row.numbers) return NM;
  const { share, split, taken } = row.numbers;
  /* Where the share is a whole count of questions over a stored total (all but the replay's half rule, a mean over
     its splits), the count is given under it. */
  const count = taken ? `<span class="small">${integer(taken.kept)} of ${integer(taken.total)} kept · ${integer(taken.total - taken.kept)} to the LLM</span>` : '';
  if (!split) return `<span class="share-cell">${percent(share)}${tip(SPLIT_NA_TIP, '<span class="nm">Not recorded</span>')}${count}</span>`;
  const parts = [['right', split.right, 'kept and right'], ['wrong', split.wrong, 'kept but wrong'], ['rest', split.rest, 'sent to the LLM']];
  const scope = split.splits ? `means over the replay’s ${integer(split.splits)} splits` : 'shares of all questions';
  const spoken = `${parts.map(([, value, name]) => `${name} ${percent(value)}%`).join(', ')}; ${scope}`;
  return `<span class="share-cell">${percent(share)}<span class="split" role="img" aria-label="${esc(spoken)}">` +
    `<span class="split-bar" aria-hidden="true">${parts.map(([key, value]) => `<span class="split-${key}" style="flex-grow:${value.toFixed(5)}"></span>`).join('')}</span>` +
    `<span class="split-values" aria-hidden="true">${parts.map(([, value]) => percent(value)).join(' · ')}</span></span>${count}</span>`;
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
    `<span class="rm-branch"><span class="rm-node">Send the question to the LLM</span>${choice(routeLlmName(llm))}${choice(requestSize(state.route.qpr))}` +
    `${choice(test)}</span></span></figure>`
  );
}

/* ---- Rendering the leaderboard ---- */

/* Rows by the sorted column's value; rows it ties ranked by its tie column (its key) in the same direction. */
function sortRows(rows, columns) {
  const { key, descending } = state.sort;
  const column = columns.find(item => item.key === key);
  const tie = column?.tie && columns.find(item => item.key === column.tie);
  /* The Routing tab ignores the part and topic filters, so it orders by accuracy on all questions. */
  const fallback = state.tab === 'routing' ? overallAccuracy : accuracyOf;
  const value = column ? row => column.value(row) : row => fallback(row.run);
  const order = (x, y) => {
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    return descending ? y - x : x - y;
  };
  return [...rows].sort((a, b) => order(value(a), value(b)) || (tie ? order(tie.value(a), tie.value(b)) : 0));
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
    const size = state.qpr === 'all' || state.web !== 'all' ? null : `ran at ${requestSize(state.qpr)}`;
    if (state.picked.size) return `None of the models you picked ${size ?? 'matches these filters'}.`;
    return `No setup ${size ?? 'matches these filters'}.`;
  }
  if (state.tab === 'routing' && state.models === 'chat') return 'Only decision models went first in front of an LLM: the Routing tab has no chat model.';
  if (state.tab === 'routing') return 'The Routing tab lists only the setups we put in front of an LLM; none of them matches these filters.';
  if (state.tab === 'stability') return 'The Stability tab lists only the setups we repeated; none of them matches these filters.';
  return 'No setup matches these filters.';
}

/* The tab's rows as one table, ranked together: the group of ?models= (every setup, the decision models or the chat
   models). */
function renderBoard() {
  const tab = TABS[state.tab];
  if (tab.more && !more.ready) {
    const board = document.getElementById('board');
    board.innerHTML = waitingForMore(LOADING_TABLE);
    board.setAttribute('aria-labelledby', `tab-${state.tab}`);
    loadMore();
    return;
  }
  const rows = sortRows(tab.rows(), tab.columns);
  const labels = chartLabels(rows.map(row => row.run));
  const table = rows.length
    ? `<h3 class="board-group">${esc(MODEL_GROUPS[state.models].title)}</h3><div class="table-frame"><div class="table-wrap"><table class="board${tab.wrapHeaders ? ' wrap-headers' : ''}"><thead><tr><th scope="col">Model</th>` +
      `${tab.columns.map(column => header(column, tab.directions)).join('')}</tr></thead><tbody>` +
      rows.map(row => `<tr data-run="${row.run.run}"${state.selected === row.run.run ? ' class="is-selected"' : ''}>${modelCell(row.run, labels)}` +
        `${tab.columns.map(column => `<td class="num">${column.cell(row)}</td>`).join('')}</tr>`).join('') +
      '</tbody></table></div></div>'
    : `<div class="empty-state" role="status"><p><span class="icon" aria-hidden="true">⚠</span> ${esc(emptyReason())}</p>` +
      `${state.tab === 'routing' && state.models === 'chat' ? '' : '<button type="button" class="key" data-control="reset">Reset filters</button>'}</div>`;
  const routing =
    state.tab === 'routing'
      ? `<h3 class="tab-title">Can a cheap model go first?</h3>${routingControls()}${routeMap()}<p class="table-title">${esc(routeTitle())}</p>` +
        `<p class="scope">${esc(routeScope().text)}</p>`
      : '';
  /* The note for a first model's cost basis († or the maker's list price), each only when such a saving is in the table;
     a maker's list price has no mark. */
  const marked = new Set(rows.filter(row => row.numbers?.saving != null).map(row => firstCostMark(row.run)).filter(Boolean));
  const marks = Object.values(FIRST_COST_MARKS)
    .filter(item => marked.has(item))
    .map(item => `<p class="table-note">${esc(item === FIRST_COST_MARKS.maker ? item.note : `${item.mark} ${item.note}`)}</p>`)
    .join('');
  /* The Accuracy tab's cost column: the cost note for its rows, then what is not measured. */
  const tabNotes = state.tab === 'accuracy' ? [SETTINGS.ranksNote, costNote(rows.map(row => row.run)), SETTINGS.notMeasuredNote].filter(Boolean) : tab.notes ?? tab.note ?? [];
  const notes = tabNotes.map(text => `<p>${esc(text)}</p>`).join('');
  const guide = tab.guide
    ? `<div class="tab-guide"><h3>How to read this tab</h3><ul>${tab.guide.map(([term, text]) => `<li><strong>${esc(term)}</strong>: ${esc(text)}</li>`).join('')}</ul></div>`
    : '';
  const board = document.getElementById('board');
  const split = state.tab === 'routing' ? splitNote(rows) : '';
  board.innerHTML = routing + guide + table + (split ? `<p class="table-note">${esc(split)}</p>` : '') + marks + (notes ? `<div class="tab-notes">${notes}</div>` : '');
  board.setAttribute('aria-labelledby', `tab-${state.tab}`);
  board.querySelectorAll('.table-wrap').forEach(wrap => wrap.addEventListener('scroll', onTableScroll, { passive: true }));
  document.querySelectorAll('[data-setups]').forEach(count => {
    count.textContent = `${integer(rows.length)} of ${integer(groupRuns().length)} setups`;
  });
}

/* On a phone the table scrolls sideways inside its frame: a fade on the right edge while columns are hidden there, and a
   label above the table until the reader first scrolls it (remembered for the session). */
let swiped = document.documentElement.classList.contains('swiped');
function edgeFade(wrap) {
  wrap.parentElement.classList.toggle('more-right', wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 1);
}
function updateSwipe() {
  const wraps = [...document.querySelectorAll('#board .table-wrap')];
  const hint = document.querySelector('[data-swipe-hint]');
  hint.classList.remove('is-done');
  hint.hidden = swiped || !wraps.some(wrap => wrap.scrollWidth - wrap.clientWidth > 1);
  wraps.forEach(edgeFade);
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
    `<div class="keys" role="group" aria-label="Questions per request">${keys('route-qpr', routeSizes(routeLlm()).map(size => [size, `${size} per request`]), qpr)}</div>` +
    `<label>Rule <select data-control="route-rule">${ROUTE_RULES.map(item => `<option value="${item.key}"${item.key === rule ? ' selected' : ''}>${esc(item.label)}</option>`).join('')}</select></label>` +
    `<div class="keys" role="group" aria-label="Test">${keys('route-mode', [['replay', 'Replay'], ['live', 'Live']], mode)}</div>` +
    '</div>'
  );
}

/* ---- Filters ---- */

function filterSummary() {
  const parts = [];
  if (state.topic != null) parts.push(units().find(unit => unit.number === state.topic).english);
  else if (state.part !== 'all') parts.push(state.part === 'reading' ? 'Reading' : 'Grammar');
  if (state.qpr !== 'all') parts.push(requestSize(state.qpr));
  if (state.web !== 'all') parts.push(state.web === 'with' ? 'With web' : 'Without web');
  if (state.picked.size) parts.push(`${integer(state.picked.size)} picked`);
  return parts.join(' · ') || 'All setups';
}

/* The full ranking's question count above its table. The filters themselves come from the address only (readUrl): the
   home page shows no filter controls. */
function renderFilters() {
  /* The Routing tab ignores the part and topic filters: its table covers the questions of the test shown (routeScope). */
  const route = state.tab === 'routing' ? routeScope() : null;
  document.querySelector('[data-count]').textContent = route ? `${route.about ? 'about ' : ''}${integer(route.count)} questions` : `${integer(questionsInFilter())} questions`;
}

/* ---- Charts ---- */

/* Which setups a chart shows, in words: the group, then any filter that narrows it. */
function chartScope(runs) {
  const head = `${integer(runs.length)} setup${runs.length === 1 ? '' : 's'}`;
  const group = MODEL_GROUPS[state.models];
  const web = { all: '', with: 'with web grounding', without: 'without web grounding' }[state.web];
  const narrowed = [state.qpr === 'all' ? '' : `at ${requestSize(state.qpr)}`, web, state.picked.size ? 'the models you picked' : ''].filter(Boolean);
  if (!narrowed.length) return `${head}: ${group.every}.`;
  return `${head} of ${group.of(integer(groupRuns().length))}: ${narrowed.join(', ')}.`;
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
  /* As in the Confidence tab: on all questions only, in points. */
  gap: {
    more: true,
    label: 'Calibration gap', axis: 'Calibration gap, as shipped (points)', value: run => (filtered() ? null : run.confidence?.ece ?? null),
    log: false, points: true, allOnly: true, text: value => (100 * value).toFixed(1), higher: false,
  },
  latency: { label: 'Latency', axis: 'Median latency per request (s), log scale', value: latencyOf, log: true, text: secondsText, higher: false },
  cost: { label: 'Cost', get axis() { return `$ ${costLabel()}, log scale`; }, value: costShown, log: true, text: costNumber, higher: false },
};
/* The bar charts on the page, one finding section each: accuracy, latency, cost and calibration. */
const FACE_MEASURES = ['accuracy', 'gap', 'latency', 'cost'];
const NEEDS = { latency: 'latency', cost: 'cost estimate' };
/* The name above each value column of a bar chart, in full and on a phone, as the static charts' headers ("Turkish ·
   English", "TR · EN"): each chart's own value (accuracy's as accuracyHead), then the accuracy chart's cost and latency
   columns. */
const COLUMN_HEADS = {
  get accuracy() { return accuracyHead(); },
  gap: ['Gap (points)', 'Gap'],
  latency: ['Median latency', 'Median'],
  get cost() { return costUnit() === '1m' ? ['Cost / 1M', '$/1M'] : ['Cost / 1k', '$/1k']; },
  get price() { return this.cost; },
  speed: ['Latency', 'Latency'],
};
/* A setup's cost as the Cost chart writes it, with its $: in the reader's unit, ≤ before an upper-bound estimate, or No
   list price where there is no estimate (never a zero). The accuracy chart gives it beside each setup's accuracy. */
const priceText = run => {
  const value = costShown(run);
  return value == null ? costMissing(run) : `${upperPrefix(run)}$${MEASURES.cost.text(value)}`;
};
const priceNote = () => `Beside each bar: accuracy with its interval${lettersShown() ? ' and tie group' : ''}, then cost in $ ${costLabel()}, estimated from list prices and recorded token use, as in the Cost chart, then the median latency per request, as in the Latency chart.`;
/* The accuracy chart's latency column: the median seconds per request, marked when measured on a sample; Not measured
   where there is none (never a zero). */
const latencyText = run => {
  const value = latencyOf(run);
  return value == null ? EMPTY.notMeasured : `${secondsText(value)} s${sampleLabel(run) ? ` ${SAMPLE_MARK}` : ''}`;
};
/* The accuracy chart's value cell, as on the Logic & Math pages: the accuracy, its Wilson 95% interval (wilson(), as each
   setup's page gives it) in whole percents and, on all questions, the setup's tie-group letters (results.json
   runs[].group, from the all-pairs test over every setup on the whole test); under a part or topic filter no letters. */
const lettersShown = () => !filtered();
function accuracyParts(run) {
  const { correct, questions } = counts(run);
  const [low, high] = wilson(correct, questions);
  return { value: pct(correct / questions), low, high, interval: `(${pct(low, 0)}–${pct(high, 0)})`, letters: lettersShown() ? run.group ?? '' : '' };
}
const accuracyText = run => {
  const { value, interval, letters } = accuracyParts(run);
  return [value, interval, letters].filter(Boolean).join(' ');
};
const accuracyValue = run => {
  const { value, interval, letters } = accuracyParts(run);
  return `${esc(value)} <tspan class="value-sub">${esc(interval)}</tspan>${letters ? ` <tspan class="letters">${esc(letters)}</tspan>` : ''}`;
};
const accuracyHead = () => (lettersShown() ? ['Accuracy (95% interval) · tie group', 'Acc. · group'] : ['Accuracy (95% interval)', 'Acc. (95%)']);
/* Chance: the accuracy of a uniform guess among each question's options (results.json baselines.options), a line across
   the accuracy chart. */
const chance = () => 1 / data.baselines.options;
const chanceNote = () => `The line is chance (${pct(chance(), 0)}): a uniform guess among ${data.baselines.options} options.`;
/* The line under the accuracy chart: what its whiskers and letters are, in the words of each setup's page. */
const WHISKER_NOTE = 'Whiskers: Wilson 95% intervals, the 95% interval each setup’s page gives.';
const LETTERS_NOTE = 'Letters: tie groups on all questions; the all-pairs test did not detect a difference between setups that share a letter. This does not establish equality.';

/* Model families. In the accuracy, calibration, latency and cost charts and the small chart, each setup's bar or dot
   takes its model family's colour (page_config.json model_families, given by run id in SETTINGS.families): a maker's
   line of models shares one colour, the families differ, and a setup keeps its colour in every chart and in both model
   groups. */
const familyOf = run => SETTINGS.families[run.run];
const familyColour = run => SETTINGS.familyColours[familyOf(run)];
/* The families among a chart's setups, in the chart's order. */
const familiesIn = runs => [...new Set(runs.map(familyOf))];
/* A family's icon (the page's family sprite, sitebuild/site.py family_sprite), left of a setup's name: the maker's
   mark or the family's letter, hidden from screen readers, so the name stays the accessible text. */
const familyIconId = name => `fi-${name.toLowerCase().replace(/[^a-z0-9]/g, '')}`;
const familyIconOf = name => `<svg class="fam-icon" aria-hidden="true" focusable="false"><use href="#${familyIconId(name)}"/></svg>`;
const familyIcon = run => familyIconOf(familyOf(run));
/* The same icon inside a chart's SVG, 14 px with its top-left corner at (x, y). */
const chartIcon = (run, x, y) =>
  `<use class="fam-icon" href="#${familyIconId(familyOf(run))}" x="${x}" y="${y}" width="14" height="14" aria-hidden="true"/>`;
/* The legend of a chart's colours: each of its families with its colour and icon, on one compact line of its own that
   wraps (v3.css .families). */
const familyLegend = families =>
  `<span class="families">${families.map(name => `<span><i class="swatch" style="background:${SETTINGS.familyColours[name]}"></i>${familyIconOf(name)}${esc(name)}</span>`).join(' ')}</span>`;

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
function textWidth(text, weight = 400, size = 12, family = getComputedStyle(document.body).fontFamily) {
  measurer.font = `${weight} ${size}px ${family}`;
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

/* The charts never scroll inside their box. A list of setups (a bar chart, Reading vs grammar, the cost table) shows its
   first TOP_ROWS by default, and its Show all key (showAllKey) opens every row in place and closes them again; the
   highlighted setup is added after the first TOP_ROWS when it ranks below them. A downloaded image has every row. */
const TOP_ROWS = 10;
const expanded = new Set();
function topRows(name, ordered) {
  if (expanded.has(name) || ordered.length <= TOP_ROWS) return { rows: ordered, apart: false };
  const rows = ordered.slice(0, TOP_ROWS);
  const chosen = ordered.find(run => run.run === state.selected);
  if (!chosen || rows.includes(chosen)) return { rows, apart: false };
  return { rows: [...rows, chosen], apart: ordered.indexOf(chosen) > TOP_ROWS };
}
const showAllKey = (name, total) => {
  if (total <= TOP_ROWS) return '';
  const open = expanded.has(name);
  return `<button type="button" class="key show-all" data-chart-all="${name}" aria-expanded="${open}">` +
    `${open ? `Show the top ${TOP_ROWS}` : `Show all ${integer(total)} setups`}</button>`;
};
/* What a list shows of its setups, for its notes: the first TOP_ROWS of how many, and where the highlighted one ranks. */
function shownNote(name, ordered, rows) {
  if (rows.length === ordered.length) return '';
  const chosen = rows.length > TOP_ROWS ? rows[TOP_ROWS] : null;
  return `Showing the top ${TOP_ROWS} of ${integer(ordered.length)}${chosen ? `, then the highlighted setup, ranked ${integer(ordered.indexOf(chosen) + 1)}` : ''}.`;
}
/* The space and dotted line between the top rows and a highlighted setup that ranks below them. */
const APART = 12;
const apartLine = (y, width) => `<line class="row-apart" x1="4" x2="${width - 4}" y1="${y}" y2="${y}"/>`;

const legend = (families, text) => `<p class="chart-legend">${familyLegend(families)} <span>${esc(text)}</span></p>`;
/* The home parts' one caveat line under each chart on the page; the rest of their notes is on the Method page
   (METHOD_NOTES), and a downloaded image keeps every note. */
const METHOD_NOTES = 'method/#home-notes';
const PAGE_CAVEATS = {
  accuracy: 'Beside each bar its cost and latency, as in their charts.',
  cost: 'Log scale. Estimates, not bills: each value’s tooltip says how it was counted.',
  latency: 'Log scale. Times from our machine; API times include the network.',
};
const caveatLine = text => `<p class="caveat">${esc(text)} ` +
  `<a href="${METHOD_NOTES.replace('#', `?models=${state.models}#`)}">More in the method</a>.</p>`;
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
  /* The family's icon (chartIcon) goes left of the name, 18 px with its gap, so the name has 18 px less. */
  if (PHONE.matches) {
    const first = truncate(name, width - 22, weight);
    const rest = detail ? truncate(` · ${detail}`, width - 22 - textWidth(first, weight), weight, 12) : '';
    return `${chartIcon(run, 2, y + 2)}<text class="${labelClass}" x="20" y="${y + 13}"><title>${esc(full)}</title>${esc(first)}${rest ? `<tspan class="detail">${esc(rest)}</tspan>` : ''}</text>`;
  }
  const shown = truncate(name, labelWidth - 18, weight);
  const firstY = detail ? y + 15 : y + row / 2 + 4;
  const first = `<tspan x="${labelWidth}" y="${firstY}">${esc(shown)}</tspan>`;
  const second = detail ? `<tspan class="detail" x="${labelWidth}" y="${y + 28}">${esc(truncate(detail, labelWidth, weight, 12))}</tspan>` : '';
  return `${chartIcon(run, Math.round(labelWidth - textWidth(shown, weight) - 18), firstY - 11)}` +
    `<text class="${labelClass}" text-anchor="end"><title>${esc(full)}</title>${first}${second}</text>`;
}

/* One measure (MEASURES) as horizontal bars, one card on the page: accuracy, the calibration gap, latency or cost. */
function barChart(box, name) {
  const measure = MEASURES[name];
  const runs = visibleRuns();
  if (!runs.length) {
    box.innerHTML = `<p class="note">${esc(emptyReason())}</p>`;
    return;
  }
  if (measure.allOnly && filtered()) {
    box.innerHTML = `<p class="note">${esc(`${EMPTY.allOnly}: clear the part and topic filters to see it.`)}</p>`;
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
  const width = box.clientWidth;
  const labelWidth = phone ? 0 : Math.min(300, Math.round(width * 0.36));
  /* Each value column is named above it, right-aligned on the column's edge as the values are (COLUMN_HEADS: in full,
     on a phone); a column is as wide as its longest entry or its name. */
  const pick = ([long, short]) => (phone ? short : long);
  const headWidth = text => Math.ceil(textWidth(text, 600, 12));
  const mono = getComputedStyle(document.documentElement).getPropertyValue('--mono').trim() || 'monospace';
  const widest = (text, size = 12) => Math.ceil(Math.max(0, ...ordered.map(run => textWidth(text(run), 400, size, mono))));
  /* The accuracy chart's value is its cell (accuracyText: accuracy, interval, letters), as wide as its longest. */
  const lettered = name === 'accuracy';
  const valueWidth = Math.max(phone ? 62 : 70, headWidth(pick(COLUMN_HEADS[name])) + 8, lettered ? widest(accuracyText, phone ? 11 : 12) + 8 : 0);
  /* The accuracy chart also gives each setup's cost (priceText) and median latency (latencyText): in columns of their own
     at the right, or on a phone at the right of the name's line, over the value (sideText), so nothing scrolls sideways. */
  const priced = name === 'accuracy';
  const columnWidth = (text, head) => Math.max(widest(text), headWidth(pick(head))) + 24;
  const priceWidth = priced && !phone ? columnWidth(priceText, COLUMN_HEADS.price) : 0;
  const latencyWidth = priced && !phone ? columnWidth(latencyText, COLUMN_HEADS.speed) : 0;
  const sideText = run => `${priceText(run)} · ${latencyText(run)}`;
  const sideWidth = run => (priced && phone ? Math.ceil(textWidth(sideText(run), 400, 11, mono)) + 10 : 0);
  const values = known.map(measure.value);
  /* Accuracy runs from 0 to 100%; the calibration gap from 0 to the next 5 points above the largest; latency and cost on
     a log scale around their values. */
  const gapTop = values.length ? Math.max(0.05, Math.ceil(Math.max(...values) / 0.05 - 1e-9) * 0.05) : 0.05;
  const domain = measure.log ? (values.length ? [Math.min(...values) / 1.5, Math.max(...values) * 1.5] : [0.01, 1]) : measure.points ? [0, gapTop] : [0, 1];
  const left = phone ? 2 : labelWidth + 10;
  const right = width - valueWidth - priceWidth - latencyWidth - 8;
  const x = scale(domain, [left, right], measure.log);
  const step = domain[1] <= 0.2 + 1e-9 ? 0.05 : 0.1;
  const ticks = measure.log ? ticksLog(...domain)
    : measure.points ? Array.from({ length: Math.round(domain[1] / step) + 1 }, (_, index) => index * step) : [0, 0.25, 0.5, 0.75, 1];
  /* The chart drawn for rows (the shown ones on the page, every one in its image): its SVG. */
  const draw = (rows, apart) => {
    const yOf = index => top + index * row + (apart && index >= TOP_ROWS ? APART : 0);
    const base = yOf(rows.length);
    const height = base + axis;
    const parts = ticks.map(value =>
      `<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${top}" y2="${base}"/>` +
      `<text class="tick" x="${x(value)}" y="${base + 14}" text-anchor="middle">${measure.log ? logTick(value) : percent(value, 0)}</text>`);
    parts.push(`<line class="axis" x1="${x(domain[0])}" x2="${right}" y1="${base}" y2="${base}"/>`);
    parts.push(`<text class="axis-title" x="${(left + right) / 2}" y="${base + 32}" text-anchor="middle">${esc(measure.axis)}</text>`);
    if (apart) parts.push(apartLine(yOf(TOP_ROWS) - APART / 2, width));
    const bands = [];
    rows.forEach((run, index) => {
      const y = yOf(index);
      const value = measure.value(run);
      const maker = name === 'cost' && value != null && basisCostTip(run);
      const sample = name === 'latency' && value != null && sampleLabel(run);
      const priceMaker = priced && costPer1000(run) != null && basisCostTip(run);
      const price = priced ? `; cost ${costLabel()}: ${priceText(run)}${priceMaker ? ` (${basisCostTip(run)})` : ''}` : '';
      const latencyValue = priced ? latencyOf(run) : null;
      const latency = !priced ? '' : latencyValue == null ? `; median latency per request: ${EMPTY.notMeasured}`
        : `; median latency per request: ${secondsText(latencyValue)} s${sampleLabel(run) ? ` (${sampleLabel(run)})` : ''}`;
      const missing = name === 'cost' ? costMissing(run) : EMPTY.notMeasured;
      const cell = lettered ? accuracyParts(run) : null;
      const shown = value == null ? missing : cell
        ? `${cell.value}, Wilson 95% interval ${pct(cell.low)} to ${pct(cell.high)}${cell.letters ? `, tie group ${cell.letters}` : ''}`
        : measure.text(value);
      const full = `${run.name} · ${runDetail(run)}: ${shown}${maker ? ` (${basisCostTip(run)})` : ''}${sample ? ` (${sample})` : ''}${price}${latency}`;
      const barTop = phone ? y + 18 : y + (row - 16) / 2;
      const barHeight = phone ? 14 : 16;
      const mid = barTop + barHeight / 2;
      const label = rowLabel(labels, run, y, row, width - sideWidth(run), labelWidth, full);
      /* The ring spans the row: it shows the focus, and it shades the selected setup's row. */
      const inner = [`<rect class="ring" x="1" y="${y + 1}" width="${width - 2}" height="${row - 2}" rx="3"/>`, label];
      if (value == null) {
        inner.push(`<text class="value nm" x="${width - 4 - priceWidth - latencyWidth}" y="${mid + 4}" text-anchor="end">${missing}</text>`);
      } else {
        const start = x(domain[0]);
        inner.push(`<rect class="bar-${isDecision(run) ? 'decision' : 'chat'}" style="fill:${familyColour(run)}" x="${start}" y="${barTop}" width="${Math.max(1, x(value) - start)}" height="${barHeight}" rx="2"><title>${esc(full)}</title></rect>`);
        if (cell) {
          /* A casing in the panel colour keeps the line apart from the bar it crosses, in both themes. */
          const path = `M${x(cell.low)} ${mid - 3}v6M${x(cell.low)} ${mid}H${x(cell.high)}M${x(cell.high)} ${mid - 3}v6`;
          inner.push(`<path class="whisker-case" d="${path}"/><path class="whisker" d="${path}"/>`);
        }
        inner.push(`<text class="value${cell ? ' cell' : ''}" x="${width - 4 - priceWidth - latencyWidth}" y="${mid + 4}" text-anchor="end">${cell ? accuracyValue(run) : `${name === 'cost' ? upperPrefix(run) : ''}${measure.text(value)}${sample ? ` ${SAMPLE_MARK}` : ''}`}</text>`);
      }
      if (priced && phone) {
        inner.push(`<text class="value side" x="${width - 4}" y="${y + 13}" text-anchor="end">${esc(sideText(run))}</text>`);
      } else if (priced) {
        inner.push(`<text class="value${costPer1000(run) == null ? ' nm' : ''}" x="${width - 4 - latencyWidth}" y="${mid + 4}" text-anchor="end">${esc(priceText(run))}</text>`);
        inner.push(`<text class="value${latencyValue == null ? ' nm' : ''}" x="${width - 4}" y="${mid + 4}" text-anchor="end">${esc(latencyText(run))}</text>`);
      }
      parts.push(`<g ${markAttributes(run, full)}>${inner.join('')}</g>`);
      bands.push([barTop - 1, barTop + barHeight + 1]);
    });
    /* Chance, over the bars it crosses: one line down the plot beside the names, and on a phone, where each name sits
       above its bar, a piece across each bar's band only, so it never crosses a name. */
    const at = x(chance());
    if (name === 'accuracy') {
      parts.push(...(phone ? bands : [[top - 3, base]]).map(([y1, y2]) => `<line class="chance" x1="${at}" x2="${at}" y1="${y1}" y2="${y2}"/>`));
    }
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Bar chart of ${measure.label.toLowerCase()} for ${rows.length} of ${ordered.length} setups.`)}">${parts.join('')}</svg>`;
  };
  const { rows, apart } = topRows(name, ordered);
  const selection = runs.some(run => run.run === state.selected);
  box.classList.toggle('has-selection', selection);
  const where = name === 'accuracy' ? ` on ${integer(questionsInFilter())} questions` : name === 'gap' ? ' on all questions, as shipped' : '';
  const latencyNote = name === 'latency' || priced ? ['Local setups ran on our hardware, listed on each setup’s page; API latency includes the network, and via OpenRouter, OpenRouter’s time.'] : [];
  const costNotes = name === 'cost' || priced ? [costNote(ordered)] : [];
  const sampleNote = name === 'latency' || priced ? sampleNotes(ordered) : [];
  const scaleNote = measure.log ? 'Log scale.' : '';
  const intervalNotes = name === 'accuracy' ? [WHISKER_NOTE, chanceNote(), lettersShown() ? LETTERS_NOTE : ''].filter(Boolean) : [];
  /* The image has every row, so its notes and legend cover them all; the page's legend names the families shown. */
  chartNotes[name] = {
    notes: [`${measure.label}${where}.`, scaleNote, ...intervalNotes, priced ? priceNote() : '', ...latencyNote, ...costNotes, ...sampleNote].filter(Boolean),
    unlabelled: [], families: familiesIn(ordered), full: () => draw(ordered, false),
  };
  /* Each column's name over it; on a phone the accuracy chart's cost and latency, at the right of each name's line, are
     named on a line above its value's name. */
  const heads = priced && phone
    ? [[`${pick(COLUMN_HEADS.price)} · ${pick(COLUMN_HEADS.speed)}`, width - 4, 13], [pick(COLUMN_HEADS[name]), width - 4, 29]]
    : [[pick(COLUMN_HEADS[name]), width - 4 - priceWidth - latencyWidth, 13],
      ...(priced ? [[pick(COLUMN_HEADS.price), width - 4 - latencyWidth, 13], [pick(COLUMN_HEADS.speed), width - 4, 13]] : [])];
  const headHeight = priced && phone ? 34 : 18;
  if (name === 'accuracy') document.querySelectorAll('[data-chance]').forEach(item => { item.textContent = pct(chance(), 0); });
  box.innerHTML =
    `<svg class="column-heads" width="${width}" height="${headHeight}" viewBox="0 0 ${width} ${headHeight}" aria-hidden="true">` +
    `${heads.map(([text, at, y]) => `<text class="column-head" x="${at}" y="${y}" text-anchor="end">${esc(text)}</text>`).join('')}</svg>` +
    draw(rows, apart) + showAllKey(name, ordered.length) +
    (PAGE_CAVEATS[name]
      ? legend(familiesIn(rows), [chartScope(runs), shownNote(name, ordered, rows), ...sampleNote].filter(Boolean).join(' ')) +
        (name === 'accuracy' ? `<p class="caveat">${esc([WHISKER_NOTE, lettersShown() ? LETTERS_NOTE : ''].filter(Boolean).join(' '))}</p>` : '') +
        caveatLine(PAGE_CAVEATS[name])
      : legend(familiesIn(rows), [...chartNotes[name].notes, chartScope(runs), shownNote(name, ordered, rows)].filter(Boolean).join(' ')));
}

function scatterChart(box) {
  const across = MEASURES[state.across];
  const runs = visibleRuns();
  const known = runs.filter(run => across.value(run) != null);
  if (!known.length) {
    box.innerHTML = `<p class="note">${esc(runs.length ? `No setup in view has a ${NEEDS[state.across]}.` : emptyReason())}</p>`;
    return;
  }
  const labels = chartLabels(runs);
  const phone = PHONE.matches;
  const pad = { left: 52, right: 14, top: 12, bottom: 46 };
  /* A fixed height that never scrolls inside the box; labels that would overlap are left out (each point's tooltip
     names it, and the image lists them). */
  const height = phone ? 360 : 440;
  const width = box.clientWidth;
  const xs = known.map(across.value);
  const ys = known.map(accuracyOf);
  const xDomain = [Math.min(...xs) / 1.6, Math.max(...xs) * 1.6];
  /* Up runs from 5 points below the lowest setup to 5 points above the highest, each end on a 10% line. */
  const yDomain = [Math.max(0, Math.floor((Math.min(...ys) - 0.05) * 10) / 10), Math.min(1, Math.ceil((Math.max(...ys) + 0.05) * 10) / 10)];
  const x = scale(xDomain, [pad.left, width - pad.right], true);
  const y = scale(yDomain, [height - pad.bottom, pad.top], false);
  const parts = [];
  /* The shaded region: setups in view better than their median on both, cheaper or faster and more accurate. */
  const middle = list => {
    const sorted = [...list].sort((a, b) => a - b);
    const half = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[half] : (sorted[half - 1] + sorted[half]) / 2;
  };
  const [medianAcross, medianAccuracy] = [middle(xs), middle(ys)];
  parts.push(`<rect class="quadrant" x="${pad.left}" y="${pad.top}" width="${Math.max(0, x(medianAcross) - pad.left)}" height="${Math.max(0, y(medianAccuracy) - pad.top)}"/>`);
  /* The Pareto line: the setups in view that no other setup in view beats on both accuracy and the measure across (lower
     is better across), joined as steps from the cheapest or fastest. Labels keep off it. */
  const frontier = [];
  [...known].sort((a, b) => across.value(a) - across.value(b) || accuracyOf(b) - accuracyOf(a)).forEach(run => {
    if (!frontier.length || accuracyOf(run) > accuracyOf(frontier[frontier.length - 1])) frontier.push(run);
  });
  const steps = frontier.slice(1).flatMap((run, index) => {
    const previous = frontier[index];
    const [x0, y0, x1, y1] = [x(across.value(previous)), y(accuracyOf(previous)), x(across.value(run)), y(accuracyOf(run))];
    return [[x0, y0, x1, y0], [x1, y0, x1, y1]];
  });
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
  const fresh = () => ({ taken: [...dots], lines: [...steps], placed: new Map() });
  const byAccuracy = [...points].sort((a, b) => a.cy - b.cy);
  const chosen = points.find(point => point.run.run === state.selected);
  const layout = fresh();
  byAccuracy.forEach(point => fit(layout, point));
  /* A selected setup's label takes a place left free, over dimmed points if it must; where none is left, the legend names
     the setup, so selecting never takes another label away. */
  if (chosen && !layout.placed.has(chosen.run) && !fit(layout, chosen)) fit(layout, chosen, true);
  const { placed } = layout;
  /* The selected point is drawn larger and last, so no neighbour covers it; the Pareto line goes under the points. */
  if (steps.length) parts.push(`<path class="pareto" d="${steps.map(([x0, y0, x1, y1]) => `M${x0} ${y0}L${x1} ${y1}`).join('')}"/>`);
  [...points].sort((a, b) => (a === chosen) - (b === chosen)).forEach(({ run, cx, cy }) => {
    const maker = state.across === 'cost' && basisCostTip(run);
    const sample = state.across === 'latency' && sampleLabel(run);
    const tooltip = `${run.name} · ${runDetail(run)}: ${percent(accuracyOf(run))}% right, ${state.across === 'cost' ? `${upperPrefix(run)}$${across.text(across.value(run))} ${costLabel()}` : `${across.text(across.value(run))} s per request`}${maker ? ` (${basisCostTip(run)})` : ''}${state.across === 'cost' && run.cost_upper_bound ? ` (${UPPER_MARK.tip})` : ''}${sample ? ` (${sample})` : ''}`;
    parts.push(`<g ${markAttributes(run, tooltip)}><circle class="ring" cx="${cx}" cy="${cy}" r="9"/>` +
      `<circle class="dot-${isDecision(run) ? 'decision' : 'chat'}" style="fill:${familyColour(run)}" cx="${cx}" cy="${cy}" r="${run === chosen?.run ? 6 : 4.5}"><title>${esc(tooltip)}</title></circle></g>`);
  });
  placed.forEach(({ first, second, spot: [tx, ty], line }, run) => {
    const selected = state.selected === run.run ? ' is-selected' : '';
    if (line) parts.push(`<line class="leader${selected}" x1="${line[0]}" y1="${line[1]}" x2="${line[2]}" y2="${line[3]}"/>`);
    parts.push(`<text class="label${selected}" x="${tx}" y="${ty + 12}">${esc(first)}${second ? `<tspan class="detail" x="${tx}" y="${ty + 27}">${esc(second)}</tspan>` : ''}</text>`);
  });
  box.classList.toggle('has-selection', Boolean(chosen));
  const missing = runs.length - known.length;
  const unlabelled = byAccuracy.filter(({ run }) => !placed.has(run)).map(({ run }) => labels.get(run).text);
  const better = state.across === 'cost' ? 'cheaper' : 'faster';
  const regionText = `Shaded: ${better} and more accurate than the median setup in view.`;
  const what = state.across === 'cost' ? 'cost' : 'latency';
  /* With one setup on the line (the cheapest or fastest is also the most accurate), there is no line to draw: the note
     names it. */
  const paretoText = frontier.length > 1
    ? `Dotted line (Pareto line): the setups no other setup in view beats on both accuracy and ${what}.`
    : `Pareto line: ${labels.get(frontier[0]).text} alone, as no other setup in view is ${better} or more accurate.`;
  const notes = [
    `Up: accuracy (%) on ${integer(questionsInFilter())} questions. Across: ${state.across === 'cost' ? `$ ${costLabel()}` : 'median latency per request (s)'}, log scale.`,
    regionText,
    paretoText,
    missing ? `${missing} without a ${NEEDS[state.across]} not shown.` : '',
    state.across === 'cost' ? costNote(known) : '',
    ...(state.across === 'latency' ? sampleNotes(known) : []),
  ].filter(Boolean);
  const families = familiesIn([...known].sort((a, b) => accuracyOf(b) - accuracyOf(a)));
  chartNotes.tradeoff = { notes, unlabelled, families };
  const hidden = unlabelled.length;
  const crowded = chosen && !placed.has(chosen.run) ? `Selected: ${labels.get(chosen.run).text}, its label left out so that none overlaps.` : '';
  box.innerHTML =
    `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Scatter chart: accuracy against ${state.across} for ${known.length} setups. Log scale across.`)}">${parts.join('')}</svg>` +
    `<p class="chart-legend">${familyLegend(families)} <span><i class="swatch swatch-quadrant"></i>${esc(`${better[0].toUpperCase()}${better.slice(1)} and more accurate than the median`)}</span> ` +
    `${steps.length ? '<span><i class="swatch swatch-pareto"></i>Pareto line</span> ' : ''}` +
    `<span>${esc([notes[0], chartScope(runs), ...notes.slice(1), hidden ? `${hidden} label${hidden === 1 ? '' : 's'} left out so that none overlaps; each point's tooltip names it.` : '', crowded].filter(Boolean).join(' '))}</span></p>`;
}

/* Reading against grammar: every setup the leaderboard lists, in its order (the one table of the group in view), with
   its accuracy on all the reading and all the grammar
   questions (each part's correct answers over its questions, from results.json) as two bars on one 0–100% axis, each
   bar with its value; the first TOP_ROWS until its Show all key opens the rest (topRows). */
function readingGrammarChart(box) {
  const tab = TABS[state.tab];
  if (tab.more && !more.ready) {
    box.innerHTML = waitingForMore();
    return;
  }
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
  const { rows, apart } = topRows('reading-grammar', runs);
  const yOf = index => top + index * row + (apart && index >= TOP_ROWS ? APART : 0);
  const base = yOf(rows.length);
  const height = base + 4;
  const width = box.clientWidth;
  const labelWidth = phone ? 0 : Math.min(300, Math.round(width * 0.36));
  const left = phone ? 2 : labelWidth + 10;
  const right = width - (phone ? 50 : 56) - 8;
  const x = scale([0, 1], [left, right], false);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const parts = ticks.map(value => `<line class="grid" x1="${x(value)}" x2="${x(value)}" y1="${top}" y2="${base}"/>`);
  if (apart) parts.push(apartLine(yOf(TOP_ROWS) - APART / 2, width));
  const axis = ticks.map(value => `<text class="tick" x="${x(value)}" y="14" text-anchor="middle">${percent(value, 0)}</text>`).join('');
  rows.forEach((run, index) => {
    const y = yOf(index);
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
  const note = `Accuracy (%) on all ${integer(reading)} reading and all ${integer(grammar)} grammar questions. ${integer(runs.length)} setup${runs.length === 1 ? '' : 's'}: the table’s, in its order. ${shownNote('reading-grammar', runs, rows)}`.trim();
  box.innerHTML =
    `<svg width="${width}" height="20" viewBox="0 0 ${width} 20" aria-hidden="true">${axis}</svg>` +
    `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(`Bar chart of reading and grammar accuracy for ${rows.length} of ${runs.length} setups.`)}">${parts.join('')}</svg>` +
    showAllKey('reading-grammar', runs.length) +
    `<p class="chart-legend"><span><i class="swatch swatch-reading"></i>Reading</span> <span><i class="swatch swatch-grammar"></i>Grammar</span> <span>${esc(note)}</span></p>`;
}

function renderCharts() {
  const press = (name, current) =>
    document.querySelectorAll(`[data-control="${name}"] [data-${name}]`).forEach(button => button.setAttribute('aria-pressed', String(button.dataset[name] === current)));
  press('across', state.across);
  FACE_MEASURES.forEach(name => {
    const box = document.querySelector(`[data-chart="${name}"]`);
    if (!MEASURES[name].more || more.ready) barChart(box, name);
    else {
      box.innerHTML = waitingForMore();
      if (!more.error) nearView.observe(box);
    }
  });
  scatterChart(document.querySelector('[data-chart="tradeoff"]'));
  readingGrammarChart(document.querySelector('[data-chart="reading-grammar"]'));
}

/* The cost of every setup: one table of every setup of the group in view (?models=), whatever the filters and the model
   selection, so cheap alternatives sit beside accuracy and latency. Cheapest first by costPer1000, ties by higher
   accuracy; setups without a cost last, by accuracy. "× cheapest" is a cost over the cheapest priced setup's in the
   table, from the unrounded values, to 2 significant figures. Pareto: the trade-off chart's rule over every priced setup
   in the table, on accuracy on all questions. The first TOP_ROWS rows until its Show all key opens the rest. Drawn once,
   and again when that key is pressed, as nothing else on the page changes it. */
const timesText = ratio => `×${ratio.toLocaleString('en-US', { maximumSignificantDigits: 2 })}`;
function costTable(box) {
  const runs = groupRuns();
  const labels = chartLabels(runs);
  const priced = runs.filter(run => costPer1000(run) != null)
    .sort((a, b) => costPer1000(a) - costPer1000(b) || overallAccuracy(b) - overallAccuracy(a));
  const unpriced = runs.filter(run => costPer1000(run) == null).sort((a, b) => overallAccuracy(b) - overallAccuracy(a));
  const pareto = new Set();
  let best = -Infinity;
  priced.forEach(run => {
    if (overallAccuracy(run) > best) {
      pareto.add(run);
      best = overallAccuracy(run);
    }
  });
  const cheapest = priced[0];
  const sure = pct(SETTINGS.threshold, 0);
  const idk = new Map(data.dont_know.models.map(item => [item.original_run, item]));
  const row = run => {
    const cost = costPer1000(run);
    const counts = sureCounts(run);
    const held = idk.get(run.run);
    /* With both kinds in one table, a chat model says so. */
    const chat = ['all', 'small'].includes(state.models) && !isDecision(run) ? '<span class="small">Chat model</span>' : '';
    const tag = pareto.has(run) ? ' <span class="pareto-tag">Pareto</span>' : '';
    return `<tr><td class="model">${familyIcon(run)}<a class="model-name" href="models/${run.run}/">${esc(labels.get(run).text)}</a>${tag}${chat}</td>` +
      `<td class="num">${cost == null ? `<span class="nm">${costMissing(run)}</span>` : esc(priceText(run))}</td>` +
      `<td class="num">${cost == null ? '' : timesText(cost / costPer1000(cheapest))}</td>` +
      `<td class="num">${percent(overallAccuracy(run))}</td>` +
      `<td class="num">${latencyOf(run) == null ? NM : esc(latencyText(run))}</td>` +
      `<td class="num">${counts ? `${integer(counts.right)} right of ${integer(counts.kept)} kept, ${integer(counts.skipped)} skipped${counts.invalid ? ` (${integer(counts.invalid)} without a valid answer)` : ''}` : NM}</td>` +
      `<td class="num">${held ? `<a href="dont-know/">${pct(held.non_hallucination)}, attempt rate ${pct(held.attempt_rate)}</a>` : 'Not run'}</td></tr>`;
  };
  /* The section's one caveat line is under the Cost chart; the columns (× cheapest, Pareto, Kept at, Non-hallucination)
     are explained on the Method page with the cost bases. */
  const notes = [`${integer(runs.length)} setups, ${integer(priced.length)} with a cost.`];
  const all = [...priced, ...unpriced];
  const shown = expanded.has('cost-table') ? all : all.slice(0, TOP_ROWS);
  box.innerHTML =
    '<div class="table-frame"><div class="table-wrap cost-scroll" tabindex="0"><table class="board wrap-headers cost-table"><thead><tr>' +
    ['Setup', `$ ${costLabel()}`, '× cheapest', 'Accuracy (%)', 'Median latency per request', `Kept at ${sure}`, 'Non-hallucination']
      .map((label, index) => `<th scope="col"${index ? ' class="num"' : ''}>${esc(label)}</th>`).join('') +
    `</tr></thead><tbody>${shown.map(row).join('')}</tbody></table></div></div>` +
    showAllKey('cost-table', all.length) +
    [shownNote('cost-table', all, shown), ...notes].filter(Boolean).map(note => `<p class="chart-legend">${esc(note)}</p>`).join('');
  const group = MODEL_GROUPS[state.models].every;
  document.querySelector('[data-cost-sub]').textContent = `${group[0].toUpperCase()}${group.slice(1)}, whatever the filters or the model selection · ` +
    'cheapest first, with accuracy, latency, the confidence cutoff and hallucination beside the cost · lower cost is better';
}

/* The family icons a chart's labels use, as symbols to go with it: a downloaded image has no page sprite. */
const usedIcons = svg =>
  `<defs>${[...new Set([...svg.querySelectorAll('use.fam-icon')].map(use => use.getAttribute('href')))]
    .map(href => document.querySelector(href)?.outerHTML ?? '').join('')}</defs>`;

/* A chart as a PNG that keeps what it shows: the condition (measure and filters), the setups, the chart's notes with any
   setup it could not label, and the results version, with the page's address. A bar chart's image has every row of the
   view, shown or not (chartNotes full): drawn out of sight inside its box, so the page's styles apply. Text is wrapped to
   the chart's width; colours and type are copied from the page, so it matches the theme in view. */
async function downloadChart(name) {
  const box = document.querySelector(`[data-chart="${name}"]`);
  const full = box.querySelector('svg:not(.column-heads)') && chartNotes[name]?.full;
  const stage = full ? document.createElement('div') : null;
  if (stage) {
    stage.setAttribute('aria-hidden', 'true');
    stage.style.cssText = 'position:absolute;left:-100000px;top:0;visibility:hidden';
    stage.innerHTML = full();
    box.append(stage);
  }
  const svg = (stage ?? box).querySelector('svg:not(.column-heads)');
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
  stage?.remove();
  const root = getComputedStyle(document.documentElement);
  const colour = token => root.getPropertyValue(token).trim();
  const font = esc(getComputedStyle(document.body).fontFamily);
  const { notes, unlabelled, families } = chartNotes[name];
  const texts = [];
  let y = 0;
  const write = (content, size, weight, fill) => wrap(content, width - 20, weight, size).forEach(line => {
    y += Math.round(size * 1.4);
    texts.push(`<text x="10" y="${y}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${fill}">${esc(line)}</text>`);
  });
  write(name === 'tradeoff' ? `Trade-off: accuracy against ${state.across} · ${chartCondition()}` : `${MEASURES[name].label} · ${chartCondition()}`, 14, 700, colour('--text'));
  write(chartScope(visibleRuns()), 12, 400, colour('--text-2'));
  const head = y + 12;
  y = head + height + 20;
  /* The legend, as on the page: each family among the chart's setups with its colour; an item that does not fit on the
     row starts the next one. */
  let x = 10;
  families.forEach(family => {
    const itemWidth = 14 + textWidth(family);
    if (x > 10 && x + itemWidth > width - 10) {
      x = 10;
      y += 18;
    }
    texts.push(`<rect x="${x}" y="${y - 10}" width="10" height="10" rx="2" fill="${SETTINGS.familyColours[family]}" stroke="${colour('--mark-edge')}"/>` +
      `<text x="${x + 14}" y="${y}" font-family="${font}" font-size="12" fill="${colour('--text-2')}">${esc(family)}</text>`);
    x += itemWidth + 8;
  });
  const left = unlabelled.length;
  write([...notes, left ? `${left} label${left === 1 ? '' : 's'} left out so that none overlaps: ${unlabelled.join('; ')}.` : ''].filter(Boolean).join(' '), 12, 400, colour('--text-2'));
  y += 6;
  write(`Results ${data.results_version} · answer key version ${SETTINGS.keyVersion} · ${SETTINGS.siteAddress}`, 12, 400, colour('--text-2'));
  const total = y + 12;
  const markup =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${total}" viewBox="0 0 ${width} ${total}">` +
    `<rect width="100%" height="100%" fill="${getComputedStyle(box.closest('.panel')).backgroundColor}"/>` +
    `<g transform="translate(0 ${head})">${clone.innerHTML}</g>${texts.join('')}${usedIcons(clone)}</svg>`;
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
    link.download = `decision-models-${name === 'tradeoff' ? `accuracy-${state.across}` : name}-${data.results_version}.png`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/* A Show all key: its list opens or closes in place, redrawn alone. On closing, the page scrolls only as far as keeps the
   key in view, so the reader stays at the list. */
function toggleRows(name) {
  const closing = expanded.delete(name);
  if (!closing) expanded.add(name);
  if (name === 'cost-table') costTable(document.querySelector('[data-cost-table]'));
  else if (name === 'reading-grammar') readingGrammarChart(document.querySelector('[data-chart="reading-grammar"]'));
  else barChart(document.querySelector(`[data-chart="${name}"]`), name);
  const key = document.querySelector(`button[data-chart-all="${name}"]`);
  key?.focus({ preventScroll: true });
  if (closing) key?.scrollIntoView({ block: 'nearest' });
}

/* ---- Page address and history ---- */

/* The open tab, the filters and, on the Routing tab, its four choices live in the page URL, so a link, a reload or Back
   opens that exact view: ?part=reading&topic=3&size=16&web=with&setups=145,199 for the filters (size, not Routing's
   per-request; setups, the models picked), ?tab=routing&llm=astra&per-request=16&rule=half&test=replay for Routing. A
   key at its default is left out; an unknown value is ignored. */
const llmSlug = llm => llm.slug;
const FILTER_KEYS = ['part', 'topic', 'size', 'web', 'setups'];

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const llm = SETTINGS.routeLlms.find(item => llmSlug(item) === params.get('llm'));
  const rule = ROUTE_RULES.find(item => item.slug === params.get('rule'));
  const size = Number(params.get('per-request'));
  if (llm) state.route.llm = llm.key;
  if (rule) state.route.rule = rule.key;
  if ([1, 16].includes(size)) state.route.qpr = size;
  fitRouteSize();
  if (ROUTE_TESTS.includes(params.get('test'))) state.route.mode = params.get('test');
  const routed = llm || rule || params.has('per-request') || params.has('test');
  if (TABS[params.get('tab')]) state.tab = params.get('tab');
  else if (routed) state.tab = 'routing';
  /* The model group from ?models=, as site.js reads it; missing or unknown means all. */
  const models = document.documentElement.dataset.modelsView;
  state.models = Object.hasOwn(MODEL_GROUPS, models ?? '') ? models : 'all';
  /* The filters: a topic keeps the part it belongs to; the models picked stay those of the group in view. */
  if (['reading', 'grammar'].includes(params.get('part'))) state.part = params.get('part');
  const topic = units().find(unit => String(unit.number) === params.get('topic'));
  if (topic) {
    state.topic = topic.number;
    if (state.part !== 'all' && state.part !== unitPart(topic)) state.part = unitPart(topic);
  }
  const qpr = Number(params.get('size'));
  if (data.runs.some(run => run.questions_per_request === qpr)) state.qpr = qpr;
  if (['with', 'without'].includes(params.get('web'))) state.web = params.get('web');
  state.picked = new Set((params.get('setups') ?? '').split(',').map(Number).filter(id => byId.get(id) && inGroup(byId.get(id))));
}

/* The highlighted setup, the sort and the chart choice, kept with the browser's history entry rather than the URL, so
   Back from a model's page returns to the same view. */
function remembered() {
  const { selected, sort, across } = state;
  return { selected, sort, across };
}

/* Only the keys remembered() writes come back, so an entry saved by an earlier version of the page sets nothing else
   (the filters come from the URL). */
function restore() {
  const saved = window.history.state?.v3;
  if (!saved) return;
  ['selected', 'sort', 'across'].forEach(key => {
    if (saved[key] !== undefined) state[key] = saved[key];
  });
}

function writeUrl() {
  const params = new URLSearchParams(window.location.search);
  ['tab', 'llm', 'per-request', 'rule', 'test', ...FILTER_KEYS].forEach(key => params.delete(key));
  if (state.part !== 'all') params.set('part', state.part);
  if (state.topic != null) params.set('topic', String(state.topic));
  if (state.qpr !== 'all') params.set('size', String(state.qpr));
  if (state.web !== 'all') params.set('web', state.web);
  if (state.picked.size) params.set('setups', [...state.picked].sort((a, b) => a - b).join(','));
  if (state.tab !== 'accuracy') params.set('tab', state.tab);
  if (state.tab === 'routing') {
    params.set('llm', llmSlug(routeLlm()));
    params.set('per-request', String(state.route.qpr));
    params.set('rule', routeRule().slug);
    params.set('test', state.route.mode);
  }
  /* The list of setups keeps its commas readable. */
  const query = params.toString().replace(/%2C/g, ',');
  window.history.replaceState({ ...(window.history.state ?? {}), v3: remembered() }, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

function render() {
  document.querySelectorAll('[role="tab"]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.tab === state.tab)));
  const definition = document.querySelector('[data-definition]');
  definition.textContent = DEFINITIONS[state.tab] ?? '';
  definition.hidden = !DEFINITIONS[state.tab];
  renderFilters();
  renderBoard();
  updateSwipe();
  renderCharts();
  writeUrl();
}

/* ---- Events ---- */

/* Rendering replaces the table and the charts; the control that had the focus gets it back. */
const FOCUS_KEYS = ['select', 'sort', 'routeLlm', 'routeQpr', 'routeMode', 'control', 'download', 'chartAll'];
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

/* A link into the full ranking (a finding's link) opens All setups (site.js, 'open-all-setups') at its tab and brings
   it into view, with the tab's key focused. */
function openTab(tab) {
  document.dispatchEvent(new CustomEvent('open-all-setups'));
  state.tab = tab;
  state.sort = defaultSort(tab);
  render();
  document.getElementById(`tab-${tab}`).focus({ preventScroll: true });
  loadMore().then(() => document.querySelector('.board-panel').scrollIntoView({ behavior: REDUCED_MOTION.matches ? 'auto' : 'smooth', block: 'start' }));
}

/* Share view: copies the page URL, which holds the view (writeUrl), and says so on the key for two seconds. Where the
   clipboard API is missing (a page not served over https), a hidden text field is copied instead. */
let shareTimer = null;
async function shareView(button) {
  const url = window.location.href;
  let copied = true;
  try {
    await navigator.clipboard.writeText(url);
  } catch (error) {
    const field = Object.assign(document.createElement('textarea'), { value: url, readOnly: true });
    field.className = 'visually-hidden';
    document.body.append(field);
    field.select();
    copied = document.execCommand('copy');
    field.remove();
    button.focus();
  }
  button.textContent = copied ? 'Link copied' : 'Copy failed';
  clearTimeout(shareTimer);
  shareTimer = setTimeout(() => {
    button.textContent = 'Share view';
  }, 2000);
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
  else if (dataset.tab) {
    state.tab = dataset.tab;
    state.sort = defaultSort(state.tab);
  } else if (dataset.sort) {
    const column = TABS[state.tab].columns.find(item => item.key === dataset.sort);
    state.sort = state.sort.key === column.key ? { key: column.key, descending: !state.sort.descending } : { key: column.key, descending: !column.low };
  } else if (dataset.routeLlm) {
    state.route.llm = dataset.routeLlm;
    fitRouteSize();
  } else if (dataset.routeQpr) state.route.qpr = Number(dataset.routeQpr);
  else if (dataset.routeMode) state.route.mode = dataset.routeMode;
  else if (dataset.across) state.across = dataset.across;
  else if (dataset.control === 'share') {
    shareView(button);
    return;
  } else if (dataset.chartAll) {
    toggleRows(dataset.chartAll);
    return;
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
  if (event.target.dataset.control !== 'route-rule') return;
  state.route.rule = event.target.value;
  renderKeepingFocus();
}

/* The page's own text paints before the charts draw: the browser's first contentful paint and one frame more, or
   300 ms where that paint is not reported (a background tab, or a browser without paint timing). */
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
  /* HOME_URL loads meanwhile (the page preloads it; this fetch takes the preload); an error waits for the paint too. */
  const home = fetch(HOME_URL).then(response => {
    if (!response.ok) throw new Error(`${HOME_URL}: ${response.status}`);
    return response.json();
  });
  home.catch(() => {});
  await afterFirstPaint();
  try {
    data = await home;
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
  readUrl();
  costTable(document.querySelector('[data-cost-table]'));
  /* The cost unit changed (site.js): the cost table, the charts and the table redraw in it. */
  document.addEventListener('costunit', () => {
    costTable(document.querySelector('[data-cost-table]'));
    render();
  });
  state.sort = defaultSort(state.tab);
  restore();
  render();
  /* The page opens at its top; a link into it (#board, a chart) lands on its target once the charts and the table
     above it have their height, with a tab that waits for MORE_URL drawn first. Back and Forward keep the browser's own
     scroll position. */
  const arrival = performance.getEntriesByType('navigation')[0]?.type;
  if (window.location.hash.length > 1 && arrival !== 'back_forward') {
    const land = () => document.getElementById(decodeURIComponent(window.location.hash.slice(1)))?.scrollIntoView({ block: 'start' });
    if (TABS[state.tab].more) loadMore().then(land);
    else land();
  }
  document.addEventListener('click', onClick);
  /* All setups opened (site.js): the full ranking, the cost table and the chart under it draw at the width they now have. */
  document.addEventListener('leaderboard-view', () => {
    costTable(document.querySelector('[data-cost-table]'));
    updateSwipe();
    renderCharts();
  });
  document.addEventListener('keydown', onKeydown);
  document.addEventListener('change', onChange);
  let width = window.innerWidth;
  new ResizeObserver(() => {
    if (window.innerWidth === width) return;
    width = window.innerWidth;
    updateSwipe();
    renderCharts();
  }).observe(document.body);
  PHONE.addEventListener('change', render);
}

start();
