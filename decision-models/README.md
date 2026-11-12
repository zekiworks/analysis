# Reading bench

*A decision model answers first; a stronger model answers the rest. Accuracy, confidence and cost on
Turkish exam questions.*

The results site of a benchmark of language models and decision models on 2,198 scored multiple-choice
questions from a question bank for the Turkish section of the TYT, the first stage of Turkey's university
entrance exam. The home page ranks every setup, 20 decision models among them, in four tabs (accuracy,
confidence, routing and stability) with two charts. Each setup, topic and question has its own page,
Compare tests two setups against each other, and the Method page holds the full study.

Site: <https://zekiworks.github.io/analysis/decision-models/>

The site is this folder, served by GitHub Pages from the `main` branch. It is static. `build_site.py`
writes the home page's generated parts and every other page from `results.json`, the aggregate results,
and `answers.json` with `answers-repeats.json` and `answers-english.json` beside it, which hold every answer of every
main, repeat and routing run (the repeat runs in `answers-repeats.json`, the English reading runs in
`answers-english.json`), with its
full-precision score and option probabilities but without the questions' text. `v3.js` draws the home
page's tabs and charts in the browser; without JavaScript the home page shows the leaderboard as a plain
table. `benchmark_metrics.py` is the benchmark's metric code, and `runner/` the code that ran the
benchmark. `v1/` keeps the earlier page as it was on 14 October 2026, with its own copies of the data it
shows. The preview addresses, `v2/` and `v3/`, and the page's first address,
`/analysis/turkce-benchmark/docs/`, redirect here.

## Contributing and citing

`CONTRIBUTING.md` says how to report a wrong answer key, ask us to test a model or send a dataset.
`key-changelog.md` lists every change to the answer key, and `results.json` names the key version every run is
scored on (`answer_key`). `results-changelog.md` says what changed in each results version that went live, from
results 0eb1e828 on; add a section for every new one. `CITATION.cff`, which `build_site.py` writes, gives the results
version and the key version to cite. `quality-manifest-<date>.json` lists scored questions found after publication to
lack the source context their stem points at (metadata only: ID, part, a hash of the stored source, the bank status,
which sets hold it); the Method page discloses them (`method.quality_manifests`) while every score and the uncertain
filter stay as first published (the project lead via Zeki #5392).

## From a clean copy

None of these commands needs a private file:

```bash
python3 reproduce.py                                       # recompute the published numbers
cargo test --manifest-path chart-renderer/Cargo.toml       # compare each graph with its snapshot
python3 build_site.py                                      # graphs, link preview image, CITATION.cff, every page
python3 -m http.server 8000                                # preview at http://127.0.0.1:8000/
```

- **`reproduce.py`** (Python 3.10 or newer, standard library and `benchmark_metrics.py`) recomputes,
  from `answers.json`, each main run's correct answers on the scored questions (the 12 the key
  audit excluded are skipped), AUROC, expected calibration error and the answers scored 0.99 or more,
  before and after the key audit, and the calibration after refit (5 folds by passage: gap, Brier
  scores, slopes); the leaderboard's comparison groups (every pair of runs, exact
  McNemar, Holm over all pairs, alpha 0.05), including that two runs share a letter exactly when that
  test does not tell them apart; the listed paired comparisons (exact McNemar, Holm over the listed
  pairs and over all pairs); each format rerun against its setup's first run on the same questions (exact
  McNemar, Holm over these comparisons); each reasoning pair's gains on reading and on grammar and the
  bootstrap interval of their difference, with the seed and resamples in `results.json`'s `reasoning`;
  each repeated configuration's answer stability statistics, from its runs'
  answers; every routing simulation (the cutoff chosen in sample and its 300 held-out splits); the
  Decider v1.1 replay (its answers kept at each cutoff and in its most confident quarter, and
  what keeping them changes in front of each second model, on all questions and on the same splits);
  the answer-key baselines; every live test (the questions the first model kept, against its cutoff,
  the pair's and the second model's accuracy, the paired change with its 95% interval and exact McNemar
  p and, with one question per request, each question's wait); and the costs: each priced run's from its
  token counts at the rates in `results.json`'s `prices` (with any input tokens a provider bills per request
  beyond our count) and its cost basis against its billing, every run without a price shown as self-hosted,
  each routing simulation's and replay's cost per 1,000 questions from its runs, and the
  routing tests' costs from their parts. It prints one row per run and exits with status 1 when a value
  differs from
  `results.json`: counts and group letters must match exactly, AUROC, ECE, the refit's gaps, Brier scores and slopes, shares and accuracies within
  10⁻⁹, p-values and costs within a relative 10⁻⁹. The bootstrap intervals of AUROC and of the kept
  answers' accuracy, and the other tables, are not recomputed. For the Page images tab it also recomputes
  `vision.json`'s per-condition numbers and paired tests from the answers it holds (a chat model's cell, without
  option probabilities, must have every probability measure null), and checks its `requests`
  block (one stored answer per question and cell, answers naming an option plus refusals, a chat cell's answer naming
  one when it has a choice, the continued cells and runs, the lower bound on requests sent) and that its full leak scan
  covers every OCR output of every crop. Each engine check (`engine_checks`) must hold an answer for every question; its right answers,
  the table run's, the paired exact McNemar test and the picks that differ are recomputed from the two answer sets.
  `vision-repeats.json` holds repeat passes kept outside the table: each pass's first-pass runs must be its cell's,
  and its right answers and the picks and option probabilities that differ from the cell are recomputed.
  For the Hallucination tab it recomputes each run's right, wrong, "Bilmiyorum" and invalid answers, its
  rates and mean "Bilmiyorum" probability, the derived abstention from its Text tab run, the answers changed
  across a model's runs, and the exact McNemar test of its wrong answers with "Bilmiyorum" against its Text tab run
  held back by confidence (Holm over the models that chose it on at least 1% of the questions), from `answers.json`'s
  `dont_know_runs`. For the English reading tab it recomputes, on the kept questions of `english-reading.json`, each
  model's right, wrong and invalid answers in its first English run and its Text tab run, the difference, the range
  and the answers changed over each side's runs, and the exact McNemar test of the two (Holm over the compared
  models), from `answers.json`'s `english_runs`, after checking each pairing against the Text tab's runs and repeats.
  For its "I don't know" section it recomputes, on the same kept questions, each model's right, wrong, "I don't know"
  and invalid answers in English and their "Bilmiyorum" counterparts in Turkish (a published full-bank run counted on
  the kept questions, or a run on the kept questions only), the rates, the mean probability of the option, the ranges
  and the exact McNemar test of wrong answers (Holm over the models), from `english_dont_know_runs` and
  `english_dont_know_turkish_runs`, and the same with "I don't know" in both languages
  (`english_reading.dont_know_word`: the English runs against the option-word runs counted on the kept questions,
  Holm over the models with both). For the option-word check (`dont_know_option_word`) it recomputes each model's
  right, wrong, option and invalid answers, rates and mean option probability with "Bilmiyorum" (its Hallucination
  tab run) and with "I don't know" (its run in `dont_know_word_runs`, prompt version fb17d583a3af), and the exact
  McNemar test of their wrong answers (Holm over the models). For the hosted GLiDE rerun (`hosted_glide_rerun`, from
  `rerun_runs`) it checks the run's setup against the run it replaces, recomputes its counts, and redoes the derived
  abstention and the comparison with confidence of the model's "I don't know" run with the rerun as its original run.
  For Perplexity's web grounding test (`web_grounding`, from `web_grounding_runs` with the setup's Text tab run in `runs`
  and its English run in `english_runs`) it checks each pair's setup, kind and questions, recomputes each arm's right
  answers, accuracy, median and 95th-percentile request time and cost (overall and, in Turkish, by group), each pair's
  paired counts (both right, right only off, only on, both wrong, errors, missing) and exact McNemar test, each repeat
  of the full bank's and the English pair's first runs (its setup, mode, language and settings against the first run,
  then the same measures, paired counts and source checks) and each arm's mean with its lowest and highest run, the
  "Bilmiyorum" pair's counts and rates and the right answers among each source check's questions, and checks the
  tokens, sources and PWS-Decisions' aggregates against `web-grounding.json`.
  For the option-word runs against confidence (`dont_know_option_word.vs_confidence`) it redoes each derived cut-off
  with its neighbouring cut-offs and the paired test of wrong answers, with Holm over the eligible family; for risk and
  coverage on the kept reading questions (`english_reading.coverage`) every native point and every curve point; and
  for the same number of answers (`dont_know_same_answers`) each model's wrong answers among exactly its k most
  confident five-option answers (equal scores taken in question-id order), the differences from Liquid d1-ultra with
  the paired bootstrap (10,000 resamples, seed 20261103) and Holm (over every other Text tab setup in Turkish, the
  other English reading models in English, each over the models that keep k answers), each setup's answers in selection
  order (`wrong_by_rank`, from which every curve is drawn) and the markers of the runs with the option; a five-option
  run other than Liquid d1-ultra's with fewer than k scored answers keeps every number null and is left out of the
  bootstrap and of Holm; for answers at 95%+ confidence (`high_confidence`)
  each Text tab run's kept and wrong answers at 95%, Liquid d1-ultra's repeat runs, the three models Artificial Analysis
  ties at 65 in all their runs at six cutoffs with the check at every whole percent up to 98%, and d1-ultra's English
  runs with the questions they got wrong; and for Liquid d1-ultra against each English reading model
  (`english_reading.against_reference`) the paired counts, the exact McNemar test and Holm over the others. For the
  repeat checks (`repeat_checks`) it follows `page_config.json`'s manifest: each first run's and repeat's right answers
  from the answers (the scored questions, the kept questions, or `vision.json` and `vision-repeats.json`), a retained
  entry's repeats as its Stability tab set, and every other repeat in `repeat_check_runs` only, as a repeat of its
  first run's setup.
- **The graphs** are drawn by `chart-renderer/`, a Rust crate, from `results.json`, with the decision model
  lists of `page_config.json` (see below).
- **The build** (`build_site.py`, one step) runs `reproduce.py` first and stops unless every check
  matches. With the constants in `page_config.json` (the 99% cutoff, the runs the copy names, display
  precision and the image size), it draws the graphs with `chart-renderer/`, the link preview image and
  `CITATION.cff` with `build_page.py`, and writes the pages. `build_page.py`'s `Snapshot`, `values()` and
  table and figure code also build the Method page.
  - **`--fast`:** `reproduce.py` takes about five minutes, the rest of the build seconds. A passing run stores
    its check count outside the site (`~/.cache/decision-models/reproduce/`, or under `XDG_CACHE_HOME`), keyed by
    a SHA-256 over everything it reads: `reproduce.py`, `benchmark_metrics.py`, every JSON file beside them and
    the files `answers.json` lists, with the Python version. `--fast` reuses the count stored for the same key
    and runs `reproduce.py` when there is none; every page and every copy check is still built and run. A
    page-only change (pages, scripts, styles, `sitebuild/`) keeps the key; a full build stays the default.
  - **Run types:** a run is a decision model when its provider is one of `page_config.json`'s
    `decision_model_providers` and its model not one of `not_decision_models`. The tables, `v3.js`'s charts
    and the graphs read these two lists. The build stops when the graphs give a run another type than the
    tables (`chart-renderer`'s `--types` output against the build's own), and when a provider that serves
    both decision and chat models (`mixed_providers`: OpenRouter) has a run of a model not listed under it,
    so that its type is decided first.
  - **Link previews:** the home page's (Turkish reading and grammar), the English reading page's and the
    Page images page's (picture alone): each the ten most accurate setups of its page in large type, so that it
    reads on a phone, a line pointing to the full ranking, and the results version, the answer key version and
    the page address in its footer. Drawn with headless
    Chrome in both themes (`share/`, named with the theme and a short hash of the file, for example
    `preview-dark-1a2b3c4d.png`, `preview-english-dark-…` and `preview-vision-dark-…`, so that a changed
    image gets a new address and no link preview shows a cached copy); the dark one is the link preview. `share/images.json` names the current images; the three
    pages' link previews read it, and with `--no-images` the build keeps them. Earlier images are deleted
    until `announced` holds the date of the first public post; from then on they are kept, so posted link
    previews keep working.
  - **Generated sentences:** every sentence that compares models or states a trend checks that its
    wording still fits the numbers and stops the build otherwise. A configuration's time per request is
    its own run's, or, when that run predates per-request timing, the pooled times of its later runs of
    the same setup (`latency` in `results.json`); a batch's time is never divided among its questions.
    Numbers recorded outside the published data (the question repairs, the exam and copy checks, the key
    review, a recalibration experiment) are in `page_config.json`'s `method_records`, each with its
    source.
  - **Chrome:** `--no-images` skips it, and `CHROME` names another Chrome or Chromium binary.
- **Themes:** the site is dark by default, also without JavaScript; `v3.css` keeps both palettes, and
  a reader's Dark / Light choice (the keys' labels say Dark background and Light background) is stored in `localStorage` and applied by a
  line in `<head>` before the page renders. Printing always uses the light theme.

  Every page's footer gives the results snapshot (a hash of `results.json`), its update date (when results with that
  content first went out: set at export, kept by a re-export that changes nothing, never older than the newest
  published run) and the answer key version.
- **Versioned addresses:** every page links its stylesheet and scripts, and the scripts fetch their data files
  (`data/home.json`, `data/home-more.json`, `results.json`, `data/picks.json`), with the file's content version in the query (`v3.js?v=1a2b3c4d`, the start of its SHA-256;
  `asset` in `sitebuild/site.py`). Browsers and the CDN cache each file for 10 minutes on its own, so unversioned
  links could pair a new page with an old cached script for a while after a release; with the version, a page always
  gets the files it was built with.
- **The local preview** needs a server: opening `index.html` from disk does not work, because browsers
  block loading the data files from a `file://` page.
- **The pages**: built from `results.json`, `answers.json` and `page_config.json`. Each page's head names
  its canonical address on the site.
  - **Suite strip** (`suite-bar.css`, `suite-bar.html`, published with the site as they are; `suite_bar` in
    `sitebuild/site.py` inlines the snippet with this site's link marked `aria-current="page"`): four links, All
    benches first (`/analysis/all-benches/`), then the three benchmark sites, English & Turkish Reading
    (`/analysis/decision-models/`), Logic & Math (`/analysis/logic/`) and Backgammon (`/analysis/backgammon/`), the
    current one filled; one centred line on a desktop, two centred lines where one no longer fits (a phone), every
    label whole, never scrolling sideways; the first row of the sticky header on every page, identical on the three
    sites, which copy both files, and on All benches. Its stylesheet is self-contained (its own `--suite-*` colours,
    light and dark by `data-theme` on `<html>`, else the system setting); our pages always set `data-theme` ("light" or
    "dark") so it matches the page.
  - **All benches** (`sitebuild/all_benches.py`, `all-benches.css`, `all-benches.js`): every bench of the three sites on one
    page at `/analysis/all-benches/` (and its Methodology, `method/`), outside this site. The build writes it into
    the git-ignored folder `_suite/all-benches/`, self-contained (its pages, `benches.json` and copies of
    `suite-bar.css`, `v3.css`, `site.js`, `all-benches.css` and `all-benches.js`, and its link preview in `share/`);
    publishing copies that folder to the mirror's `analysis/all-benches/`. Its titles end "· Hilde", as this site's
    ("All benches · Hilde"), and both pages carry a share card (`og:*`, `twitter:card`): `share_images` draws the
    preview, the top 10 decision models of the view the page opens with (Combined), at every build (`--no-images` and
    `--fast` too, with headless Chrome through `build_page.screenshot`, in the layout of this site's
    `share/preview-*.png`), into `_suite/all-benches/share/preview-<theme>-<hash>.png`, published with the folder.
    `all-benches/` and `all-benches/method/` here are redirects to it that keep
    the query and the fragment; `all-benches/benches.json` is what the build last read from the other sites (one file
    per bench: Logic, Math, the pooled Logic & Math and Backgammon; Logic & Math shows in place of Logic and Math until
    both are live, and Combined uses it either way). This site's `bench-scores.json` feeds it five benches, each row
    with `name` (the model's official name), `tag` (how the row's setup ran, `''` for none) and `model_key`, the three
    sites' join key (unchanged: rows join by repo and `model_key`, never because their names match; a dated checkpoint,
    such as DeepSeek-V4.1-Flash 1017, is a row of its own, not its original's): Reading · Turkish (`reading-text`, all 2,198 questions, in Combined
    only), Turkish Reading (`turkish-reading`), Turkish Grammar (`turkish-grammar`), English Reading
    (`reading-english`, the kept reading questions in English) and Vision (`reading-vision`). The page's type and class
    keys (the Leaderboard's, `?models=` and `?class=`) choose the models in view; the score keys pick what the chart
    ranks by and the table under it, every model on every bench, sorts by. Nothing stands between the keys and the
    chart: the line on what Combined averages sits under the chart, and each bench tab's line (questions per model,
    update date, the scale and the feed) under its tables. The chart is a row per model (mark and name, then the bar and
    score, Ümit #4665). Every score's head names its unit, "Score 0–100, chance = 0" (a score never takes a % sign; raw
    accuracy keeps its %); Combined carries the label "3 benchmark groups" and, under each row's value, its three parts
    (TR = Reading · Turkish, L&M = Logic & Math pooled, BG = Backgammon); a cell without a score reads Not run or Not
    applicable, the reason on hover and focus, and sorts last.
  - **Top bar** (`topbar` in `sitebuild/site.py`, under the suite strip in the one sticky header `.site-header` on
    every page, as on the Backgammon site; `--view-bar-h` is the header's height, kept by `site.js`): the Hilde leaf
    (`hilde-leaf.svg`) and the site's name, "Reading bench" (`SITE_NAME`), linking the home page, with the Dark /
    Light switch at the right; under them one row of six tabs (`TABS`), starting "Text · Vision" as on the other two
    benchmark sites (project lead through Zeki, bus #4039; agreed #4042-#4049): Text (the home page, with the
    Leaderboard), Vision (`vision/`, the Page images board), Questions, Highlights, Experiments and About. The tab a page
    sits under (`tab_of`, `SECTION`) is underlined in the accent colour: Text for the home page, `english/`,
    `turkish-vs-english/` and `models/*`; Vision for `vision/`; Questions for `questions/`, `question/`,
    `disagreements/`, `topics/` and `compare/`; Highlights for `highlights/`; Experiments for `experiments/`,
    `dont-know/`, `web-grounding/`, `pws-decisions/` and `aa-decision-index/`; About for
    `about/`, `method/` and `data/`. On a phone the tab row stays on one line and scrolls sideways, its scrollbar hidden,
    as on Logic & Math, and a current tab past the right edge is scrolled into view (`site.js` `currentTab`). No other
    navigation row sits under the suite strip; a page's own part links (`.face-nav`, as PWS-Decisions' steps) stay in
    the page. **Model keys**: `?models=all|decision|chat` (all when missing; trailing dots, punctuation or spaces are
    dropped, so `?models=all.` reads as all) picks the type on every page that shows its parts by group (`data-models`;
    `site.js` shows each element only for its type), and such a page carries its own type keys at the top of its body
    (`group_switch`, All models · Chat models · Decision models, in the page, not in the top bar); on the Leaderboard
    it sets the type key (below). Under them, on every such page with model rows (English reading, Turkish vs English,
    Hallucination, Web grounding, PWS-Decisions, Vision; About has none), the Leaderboard's **Class keys** (Class: All ·
    Tiny · Small · Medium · Large · Efficient · Workhorse · Flagship · Undisclosed, `Site.model_classes`; Ümit #4217),
    combined with the type: each table row and bar of one model carries its class (`Site.class_attribute`, hbars'
    `class_key`; empty for `small_models.left_out_models`, the setups only this site ran, which show under Class: All
    only), and `site.js` (`classPages`) takes the rows of other classes out of view, hides a class key with no row of the
    type in view (the whole Class row where the type has no model row, as Chat models on Web grounding and Vision),
    says so where a table or chart is left with no row, and shows the class
    rule (`leaderboard.class_line`, then `CLASS_PAGE_LINE`: the sentences, counts, tests and line plots stay those of
    the type) while a class is chosen; a second tap on the pressed key goes back to All. Each table row names its model
    with the Leaderboard's size label (`Site.label`). The choice is kept in `?class=` (comma-separated keys), so Back
    from a model page returns to the same view. The old small views gave way to the classes: `?models=small-chat` (and
    the older `small`) and `?models=small-decision` read as Chat models or Decision models with Tiny and Small pressed,
    as on the Leaderboard. The type and class asked for stay in the links marked `data-keep-group` and in every link to
    another page with model keys (`MODEL_PAGES` in `site.js`, the home page included, whose Leaderboard reads both).
    The footer of every page (`footer`): About · Method · Data · GitHub, the downloads and the
    results version. **Cost unit**: every cost reads per 1,000 questions or per
    1M questions, one choice for the whole site (the keys in each cost card's head, `cost_switch`; `site.js` keeps it in
    `?cost-unit=1k|1m` and localStorage `costUnit`, in `<html data-cost-unit>`, which each page's `<head>` sets before
    it renders). Static values and unit names carry both units (`cost_value`, `cost_per`, `cost_unit_in`, `cost_tick`
    in `sitebuild/site.py`) and `v3.css` shows the chosen one, per 1,000 without JavaScript; `v3.js` and `compare.js`
    write theirs with `costScale` and `costNumber` and redraw on the `costunit` event. The two English pages render, in
    static HTML, one copy per group of every part that depends on the setups shown (`data-models="all"`, shown without
    JavaScript; `decision` and `chat` hidden), with its counts and sentences computed for that group and its setups
    ranked by English accuracy within it, the Non-hallucination parts too (decision and chat models with "I don't know"
    runs ranked together in the all copy; a missing side reads Queued or Running as `page_config.json`'s
    `dont_know.under_way` gives it per model and side, Zeki #4956, else a chat model's side still running reads Running
    with `dont_know.running`, everywhere a side with the option is missing: `missing_side` in `sitebuild/english_reading.py`);
    the parts about decision models only appear once (`data-models="all decision"`), as the
    option-word check is for decision models only. A setup that shares its name with another English setup is labelled with the settings
    that tell them apart, as the home page's charts do ("Gemini 3.8 Flash (low reasoning, 16/request)"). English reading
    (`sitebuild/english_view.py`) shows every English setup on the 547 kept reading questions: nothing above the
    results but the title (the scope is in the first chart's heading, "Accuracy in English · 547 machine-translated
    questions"; the translation check's limit in one line, `limit_line`, and "More about this page" sit under the
    charts; the full lead, `limit_note` and the experiments line are in About's notes on each page; neither English
    page has a links row of its own),
    accuracy per group first (ranked by English accuracy), the
    Non-hallucination part (holding back by confidence, which reads Not measured in English in each block, beside holding
    back with "I don't know" in English, as below; under them, set apart, the Turkish reference: each setup's Text tab run
    at the threshold), cost per 1,000 questions and median latency per
    request of each first English run per group (`english_reading.models[].cost.english` and `.latency.english`, log
    scale, Not measured named in the note; `measure_card` in `sitebuild/english_reading.py`), then the table per group
    ranked by English accuracy with the four measures and the Decision Score (AA formula) column. Each decision model's
    first English run carries `english_reading.models[].decision_score` ({score, accuracy, brier, n, run}: Artificial
    Analysis's formula, the mean of 50 × (1 + c − (p − c)²) with p the chosen answer's probability, asserted equal to
    50 × (1 + accuracy − chosen-answer Brier) within 1e-9 in `export_results.py`) or `decision_score_unavailable` (the
    reason, when any kept question lacks a finite chosen-answer probability in [0, 1]); chat models and the "I don't
    know" runs carry neither. The same scores sit in a full-width table under the two holding-back sides of Non-hallucination.
    Every bar list and table of the page (the charts and the table per group, marked `data-top-rows`; PWS-Decisions
    marks its charts, habits steps and table the same way) shows its first 10 setups in view under each of its headings
    (a row of a setup carries `data-class`; a Class or type key counts only the rows it leaves; a row of no setup, as
    the answer key, always shows), with a "Show all N setups" key under it that opens every row in place and closes
    them again (`topRows` in `site.js`, Ümit #4665); the open lists stay in the address (`?all=chart-accuracy,table`,
    each list named by its part's id, numbered from a part's second list on), so a reload or Back from a model page
    opens the same view, and a link to a row past the first 10 (`#english-only-<run>`) opens its list. Without
    JavaScript every row shows.
    Tests: `test_decision_score.py`. Turkish vs English draws the same Cost and Latency cards as
    paired bars, the Text tab run (`.turkish`) and the first English run (`.english`), with both in its main table.
    Every setup name on both English pages links to its model page's English section (`#english`, `setup_href` in
    `sitebuild/english_reading.py`; a setup without an English run links to its model page).
    **English-only setups** (`english_reading.english_only`; Ümit's small models, provider `vllm-plain`): an English
    standard run whose setup has no Text tab run (same provider, model as `ENGLISH_TEXT_MODEL` maps it, reasoning,
    variant, questions per request and Perplexity mode) is exported as an English-only entry with its name, settings,
    size record, group, access text, billing, hardware, note, the first English run's cost and latency and its English
    counts: no Turkish side, no paired test, in no Holm family. Its English "I don't know" runs join
    `english_reading.dont_know.english_only` by rule (`text_run` null, `reading_run` its entry's first run, reason "no
    Turkish run: an English-only setup"). English reading and the Leaderboard's English part rank them with the paired
    setups (Turkish accuracy Not run; no Turkish reference; a setup listed in `page_config.json`'s
    `english_reading.turkish_running`, whose Text tab run is still under way, reads Running instead, or Paused with the
    reason its `paused` map gives while that run is stopped for now (Zeki #4987), and the build stops
    once a listed setup has its Text tab run published); the Both and Turkish parts and the paired tables and tests
    of Turkish vs English leave them out, which lists them per group under its main table with their English accuracy.
    With no model page, their name links to their row on English reading (`#english-only-<run>`); their details box says
    "English only" and how they were called. A `vllm-plain` run's access text comes from its record's `request_params`
    and the model's `backend`, `precision` and `revision` in `MODELS` (`plain_access` in `export_results.py`), its
    confidence reads not measured, its cost is the GPU time as for the other local runs, and its prompt version is
    that of the answers file's `plain_prompts` (the runner's `PLAIN_PROMPTS`), published in `answers.json` with it.
    **`vllm-plain` setups with Turkish runs**: once such a setup has its Turkish Text run (2,198 questions, plain answer
    line "CEVAP: X", `plain_prompts`' `turkish`) and its Turkish "Bilmiyorum" run (`turkish_dont_know`), it is a setup
    like any chat setup: on the Text tab, the Leaderboard, its model page, the Hallucination tab, Turkish vs English
    (paired, in the chat Holm families) and the English page with its Turkish side. Its runs carry no confidence, so
    the measures a plain answer line cannot give are left out or read the site's words, never 0 or blank:
    `runs[].confidence` is null (no refit, no calibration gap, no ranking score; the model page's Confidence reads Not
    measured, the Leaderboard's details box "Confidence: not measured", the home page's Confidence tab and Compare
    "Not measured · a plain answer line, no confidence", `NOT_MEASURED_CONFIDENCE` and `PLAIN_PROVIDERS` in
    `sitebuild/site.py`); `high_confidence.models[]` has `kept` and `wrong` null; its Hallucination-tab row has
    `derived` and `vs_confidence` null (Not measured in the table, named under the held-back chart) and its mean
    probability of the option reads Not measured; `dont_know.plain` gives its instruction, sentence and prompt version
    (checked against `plain_prompts`, `plain_dont_know_prompts`); the same number of answers and the risk-coverage plots
    leave it out as not measured (no score to rank by, no line); the chat-view calibration claim counts only the chat
    setups with a confidence and says so. The export checks each such run's prompt version against `plain_prompts`
    (Text and repeats `turkish`, "Bilmiyorum" `turkish_dont_know`, English as above), its access text names the
    language's answer line (ANSWER: X in English, CEVAP: X in Turkish), and `reproduce.py` rechecks them the same way.
  - **The benchmarks**: each with its own address and its own rankings, never combined: Turkish reading and grammar
    (the Leaderboard, 2,198 questions), Page images (`vision/`, from `vision.json`), Hallucination
    (`dont-know/`, from `results.json`'s `dont_know`, `dont_know_option_word`, `hosted_glide_rerun` and
    `english_reading.dont_know` and `page_config.json`'s `dont_know`, built by `sitebuild/dont_know.py`) and Turkish vs
    English (`turkish-vs-english/`, from `results.json`'s `english_reading`,
    `dont_know_option_word`, `english-reading.json` and `page_config.json`'s `english_reading` and `model_languages`,
    built by `sitebuild/english_reading.py`; its former address `english-reading/` redirects there, fragment kept).
    Page images and Hallucination sit under the Experiments tab with Web grounding, PWS-Decisions and the Artificial
    Analysis comparison. The in-page link rows that work as tabs (`.face-nav`: a page's own parts, the habits steps)
    are tinted keys. Each benchmark page's face
    is charts, each card with a line saying which way is better; its tables and notes are under Info (except the Page
    images tables, which follow their charts), a details element
    closed by default that `site.js` opens for a link into it (`dont-know/#method`). The Page images, Hallucination and
    Turkish vs English faces are HTML bars (`hbars` in `sitebuild/site.py`: one series coloured by the ranking scale; the
    Turkish vs English pairs, as English reading's bars, in each model family's colour, the English bar striped), so they need
    no script: Page images first draws its four inputs on a sample question written for the page (never one of the
    bank's; `inputs_sample`), then shows the picture alone against the text, the text plus the picture, the best OCR
    route (both coloured by accuracy, with a legend saying the colour is accuracy, not the model family) and the
    marks each OCR model kept; Hallucination first shows holding back by confidence beside holding back with the option
    (the non-hallucination rate, the answered share and the error rate among the answers together, under named
    columns as on Logic & Math; both as below), then
    that rate against the same model held back (with the run's answered share and error rate beside it)
    by its confidence, the paired test of the two (the wrong answers only one of them made, with Holm-adjusted p and the
    models outside the test named) and accuracy with the option against accuracy with five options, then the added
    comparisons: the Turkish vs English tab's English questions with "I don't know" against "Bilmiyorum" in Turkish (that
    tab's charts and table, `dont_know_charts` and `dont_know_table` in `sitebuild/english_reading.py`), the option's
    word ("I don't know" instead of "Bilmiyorum" on the same Turkish questions) and those runs against confidence, hosted
    GLiDE against a new five-option run in place of run 129, and the same number of answers (each model's five-option run
    keeping its k most confident answers, k being Liquid d1-ultra's answered count with "I don't know", against Liquid
    d1-ultra by a paired bootstrap: in Turkish every setup of the Text tab, in English every English reading model, a run
    with fewer than k scored answers left out of the test and named as such in the summary, its curve still drawn; the
    Turkish plot draws each setup with runs with the option and the English plot every English reading model, each curve
    of wrong of answers against answered with the setup's runs with the option marked, and under Info a small plot per
    Turkish setup shows every setup's curve against Liquid d1-ultra's; inline
    SVG by `line_plot` in `sitebuild/site.py`), and answers at 95%+ confidence (each decision model's Text tab run
    keeping the answers whose chosen option has a probability of at least 95%, with the wrong ones among them, a setup
    that keeps none reading "No answers at this threshold", muted and last; Liquid
    d1-ultra's repeat runs; the three models Artificial Analysis ties at 65 in all their runs at six cutoffs, with the
    check that d1-ultra's worst run stays below their best at every whole percent up to 98%; d1-ultra's English runs at
    95%; `high_confidence`). Ümit #4665: wherever a setup's non-hallucination rate shows, its answered share and the error
    rate among its answers show beside it at the same size, with Logic & Math's labels, order and wording (bus #4685,
    `holding_back.measures` and `COLUMNS`): Non-hallucination ("of answers not right, % “I don't know”"), Answered (not
    "I don't know": (right + wrong) / questions) and Error rate (of its answers: wrong / (right + wrong)); the tab's
    tables lead with the three in that order, right after the model (with two words or languages, each one's three
    together: “I don't know” then “Bilmiyorum”, English then Turkish, also in the English-option table the Turkish vs
    English tab shares), and on a phone those tables (`.idk-lead`) narrow the model column and the three so the frame's
    first view shows them, the other columns inside its scroll. A setup with no answers at a confidence threshold reads "No answers at this
    threshold" (`NO_ANSWERS` in `sitebuild/site.py`), muted, after the setups that keep answers, and is in no "fewest
    wrong" or "no observed mistakes" claim.
    Turkish vs English opens with its charts, its scope in the first chart's heading (the translation check's limit in
    one line and "More about this page" under the accuracy charts; the lead with the headline, `limit_note` and the
    experiments line are in About's notes on each page): accuracy
    in Turkish and in English first (ranked by English accuracy), then the paired test of the two (the
    questions only one of them got right, with p adjusted by Holm over every English setup), then its main table (ordered
    by English accuracy: accuracy in Turkish and in English with the difference; for decision models, with "I don't
    know" written the same in both languages, the Turkish runs being the option-word check's, Answered, Wrong of answers
    and non-hallucination with the difference, then the Turkish "Bilmiyorum" runs in a column of their own; the rank in
    each language within the group and the languages each model card lists, Not checked without a
    `model_languages` entry; Holm-significant differences marked), each per group; then, for decision models only,
    Liquid d1-ultra against each other decision model in English (the questions only one of the two got right, the exact
    McNemar test with Holm over the others and a verdict; `english_reading.against_reference`), the non-hallucination
    rate with an "I don't know" option in English against "Bilmiyorum" in Turkish with the answered shares and the paired
    test of wrong answers, the same with "I don't know" in both languages (only the language differs;
    `english_reading.dont_know_word`) and the option-word check; then risk and coverage on the kept questions (the
    decision models' native points once, confidence curves per language and group; a chat model's score is the
    confidence it stated). Under Info: the Results table per group, the Text tab setups without an English run with
    their reasons, Our method (with the decision models' System One instructions and the chat models' confidence prompt
    in English, with its version) and every kind of run's instructions. Since 5 November 2026 every Text tab setup also
    runs in English: `page_config.json`'s `english_reading.not_run` gives the reason of each setup still without an
    English run, by provider (`providers`) or by run (`runs`, which takes a setup over from its provider's entry), and the
    build stops when a Text tab setup has neither an English run nor a reason, or when an entry is stale (a run listed
    that has an English run, a provider with no setup left to run). The build writes
    `turkish-vs-english/kept-question-ids.txt` (the 547 kept IDs) from `english-reading.json`, the track's public
    record, written by
    `runner/translate_reading.py publish`: the translator, both prompts, each reading question's flag reasons, whether it
    is kept and the SHA-256 of its English text. Like every file here, it holds no question text. The question page
    (`question/?id=`) shows, for each kept reading question, every compared model's answer and its probability in Turkish
    and in English side by side (`picks.json`'s `english`).
  - **Web grounding** (`web-grounding/`, from `results.json`'s `web_grounding`, built by `sitebuild/web_grounding.py`):
    comparing the Text tab's two hosted setups, linked from the experiments line in About's notes on both English pages
    (`experiments` in `sitebuild/site.py`, its links keeping the group) and from the
    model pages of the Perplexity family. Perplexity's Decider v1.2 through its Decisions API off ("Perplexity Decider
    27B v1.2 (API)", run 633) and with web ("... (API, with web)", run 640; the checkpoint on our hardware is "... (local
    GPU)", run 217) on the full bank, reading and grammar apart; the
    200-question pilot that came first (`--sample 200 --seed 0`, runs 631 and 632); the "Bilmiyorum" pairs (full bank,
    and the pilot's 634, 635); our English translations of the kept reading questions (637 and 639) and PWS-Decisions'
    100 public questions (Parallel's gated dataset: its aggregates only). The full bank and the English questions have
    three runs per mode: the first runs (the ranking's runs, unchanged everywhere else) and their repeats 2 and 3
    (`--repeat`, the same questions in the same order, key, runner and settings), which enter only `web_grounding`
    (`repeats`: each repeat's runs, paired counts and source checks; `mean`: each arm's mean with the lowest and highest
    run) and answers.json's `web_grounding_runs`. PWS-Decisions' rows are the mean of our three runs of the two setups
    in `pws-decisions.json`, the same numbers as its page, labelled "mean of 3 runs"; its "I don't know" runs
    (`pws-decisions.json`'s `dont_know`, when present) join the Non-hallucination chart and table. The first screen:
    three result cards under the title (the Turkish
    full bank, English reading and PWS-Decisions: mean accuracy off → with web, the
    change in points, the runs' range, the cost off vs ≤ with web). Then four charts in the
    home page's format, with one short line and "More about this page" under them (the line naming both setups, three
    runs per setting, the ranking keeping each setup's first run, and the run dates, is in About's notes on each page),
    each chart in a section with the id the view bar's Measure row uses (`accuracy`,
    `non-hallucination`, `latency`, `cost`): each set of questions a small heading (hbars' row `group`) over its two
    setups with their family icon and full name, web off a clear grey and with web one accent (`v3.css` `.web-off`,
    `.web-on`). Accuracy shows the three main sets (each a mean of its runs, the lowest to highest run under it) with the
    change in points, the full bank by part under them and the pilot folded; Non-hallucination each row's option count,
    answered share and wrong share of answers; Latency the median with the 95th percentile as a line; Cost on a log
    scale, ≤ with web. Then PWS-Decisions' Accuracy, Cost and Latency charts of its decision models
    (`sitebuild/pws_decisions.py`, with its framing and provenance; the chat rows stay on its page), what the search
    returned (a short summary of the full bank's source checks, the pages and top sites of each first grounded run, then
    each grounded run's checks, N/A for a run that returned no page), the caveats, and under Detailed results the tables
    (a row per setup, icon and full name, with the pilot, the answers right only one way and the exact McNemar p), Each
    run (every run, and per repeat number both right, right only off, only with web, both wrong, errors, missing and the
    exact McNemar p) and our method. Costs with web are
    upper-bound estimates (`cost_upper_bound`): every cost of such a run, on every page, carries `page_config.json`'s
    `first_cost_marks.upper` mark (≤) and its note.
  - **PWS-Decisions** (`pws-decisions/`, from `pws-decisions.json`, built by `sitebuild/pws_decisions.py`): Parallel Web
    Systems' 100 public questions, three runs per setup (totals only). Three cards open it (among the decision models:
    the best with web search, the same model without, the best without search); one sentence frames it (an end-to-end
    comparison of setups with and without web search on questions Parallel chose for difficulty and its customers'
    web-fact needs, not a general ranking); the count of setups above the chance line; a provenance list gives the
    dataset and scorer revisions (`DATASET_REVISION`, `SCORER_REVISION`, from `~/vision-track/pws-grounding/AUDIT.md`),
    the runs and their dates. Charts, each in its Measure section (`accuracy`, `cost`, `latency`), rows grouped "With web
    search" then "Without search": Accuracy (with cost and median · p95 beside it, Parallel's 44.67% random-guess
    baseline as a line, labelled as theirs, and, with the `habits` block, the 68% of always picking the first option,
    `habits.lazy.always_first` (the right answer is the first choice on 68 of the 100 questions, `pws/bench.py`), as a
    labelled line of long dashes in the secondary text colour through every row (red stays for wrong and warning
    marks), hbars' `reference`; Ümit #4665); each chart, habits step and the table show their first 10 setups per
    heading with "Show all N setups" (`data-top-rows`, as on English reading); then the habits section below, then Cost
    ("incl. search" where a web search fee is counted, ≤ where it is an
    upper bound, "≥ … tokens only" where `cost_lower_bound` says the API reports no search count) and Latency; one bar
    per setup in its family's colour, with web striped, chat models' names ending in
    "(chat)" and a named host in "(on Baseten)" (setups' `group`, `web`, `host` and `run`, optional). The table gives each
    accuracy's run-to-run range and, from the summary step's `accuracy_ci95` (`bootstrap`: questions resampled, seed
    fixed), its 95% interval from the question sample; "Wrong when sure" as integer totals over the runs. With the
    summary step's `dont_know` block (Perplexity Decider v1.2's "I don't know" runs off and with web, three each; an arm
    is null until its runs are done), a section gives each arm's mean right, wrong and "I don't know" answers, accuracy,
    answered share, wrong share of answers, non-hallucination rate and errors, with the lowest and highest run; without
    it the page has no such section. With the summary step's `habits` block (answer-key position and yes/no totals, the
    scores of strategies that never read the question, the hard-question count, the first-choice/accuracy correlation,
    the public dates; each decision setup's own `habits`: position, "yes"/"true" and other-question first-choice
    shares, habit baseline, points above it, exploratory p and Holm-adjusted p, `explained` when at most
    `explained_margin` above, hard-question counts per run, the chosen choice's probability on right and wrong answers,
    `weights` dates for the open setups, and `reversed`: the run with the choices reversed from `runs/reversed/` against
    published runs 1 and 2, or `not_run` with the reason), a section "Can a model score here without
    knowing the facts?" (`#habits`, right after the Accuracy chart and before Cost, Ümit #4665; a decision-model part:
    the chat view shows a one-line note in its place) gives a
    two-sentence summary, a link row to the steps (`#habits-1` to `#habits-6`), and per step a table, step 5 with its
    computed sentences and chart (`reversed_step`: run 1 and the reversed run per setup), steps 1 to 4 and
    6 each with an hbars chart before it (`habits_charts`: the no-reading strategies against uniform guessing and the
    best decision setup without search; accuracy beside the habit baseline, the marked setups with a line under their
    name; hard questions right against uniform guessing; the chosen choice's probability on right and wrong answers
    with the answers at the sure threshold; days from each open setup's weights revision to the questions' earliest
    public record, a revision committed after it shown as its days after with no bar, and the note's dates sentence
    computed from the days). The page's link row has "Without the facts" (`#habits`) and "Answering habits" (`#habits-2`),
    and the experiments line beside the ranking (`experiments`) links "Answering habits" too. Each explained
    setup gets a small second line in the Accuracy chart (hbars' row `note`) and the table: "picks the first choice in
    N of 10 questions; always picking the first choice scores X%"; without the block neither appears. The method notes
    compute the chance line from `choice_counts`. Row labels add a
    setup's `interface` (CLI or API) beside its other marks, so two rows of one model never read the same. The group
    keys filter the page in place: each chart row (hbars' row `models`) and table row carries
    `data-models` ("all decision" or "all chat"), the three cards sit under a "Decision models" heading in the all and
    decision views, and the "I don't know" section is a decision-model part. Waiting lists the chat setups without
    three complete runs (`pending.chat_unfinished`, and setups with `failed_attempts` but no setup yet); the method notes
    give the attempts set aside whole with their counts.
  - **Leaderboard** (the home page, `index.html`): the script fills its `<!-- build:… -->` blocks (the meta tags, with
    the link preview from `share/images.json`, the Leaderboard, the full ranking as plain tables for readers without
    JavaScript, the settings `v3.js` reads, the finding headings and the static Non-hallucination part). In this order:
    - **No title line**: the page opens with the Leaderboard. The question "When should you trust a decision model?",
      once the page's title, is gone from every page, the browser tab and the citation (Ümit via Zeki, #5300, #5301);
      a heading only screen readers read names the page ("Reading bench: Text"). The line of counts (`site_counts`:
      questions, models, that is the Leaderboard's rows, setups and the last update) with "More about this page"
      (About, where the intro, `INTRO`, and How the scores work now stand; Ümit via Zeki, bus #3521) closes the
      Leaderboard, under All setups.
    - **Names** (`sitebuild/names.py`, `Site.title`, `Site.tag`; the project lead's rule, Ümit #4445, the three sites'
      scheme #4449, #4484): every page shows a model by its official name only, in the maker's spelling (a maker's
      display title over its repo slug), with a small tag beside it for how that setup ran, setting · route · snapshot
      ("high · chat", "API · with web", "DGX Spark", "Decisions API", "reasoning on · chat · 1017", "v1.2"), "1 per
      request" added where a model's setups differ only in that; a decision model with one setup has no tag.
      `results.json` keeps every setup name, run id and model id unchanged. Names come from the three sites' shared table,
      `model_names.json` at the root (kept by the Logic & Math site, copied byte for byte), by `model_key`, or by a row's
      `source_model_key` where Reading's key differs (that one alias also joins the row on All benches): each with its
      source status, "maker", "inferred", "openrouter-only" or "unverified" (not every name is maker-proven; the Method
      page lists them), its snapshot and its base model (shown in the details box only). `page_config.json`
      `display_names` keeps only Reading's tag rules and what the table lacks: `routes` names a decision model's route by
      run where two of its setups differ by it (never inferred), `pending` and `snapshots` any name or release the table
      lacks. The build stops where two setups would show the same name and the same tag. `data/home.json` and
      `data/names.json` (chart-renderer's labels) carry the name and tag by run; `bench-scores.json` carries `name` and
      `tag`, its `model_key` unchanged. Fixed text written with setup names (the changelogs) reads them through
      `Site.in_prose`.
    - **The Leaderboard** (`#leaderboard`, `sitebuild/leaderboard.py`): one row per model, a model being its model ID,
      its kind (chat or decision model) and web search (a setup with web is its own row; different version names are
      separate rows). A dated checkpoint joins its original's row only through `page_config.json`'s
      `leaderboard.dated_checkpoints` (today `deepseek-v4.1-flash-1017` under `deepseek-v4.1-flash`), never by similar
      names. **Row rule**, fixed and never the best score: the model's highest reasoning setting (none or off < minimal
      < low < medium < high < xhigh < max; "on" above off for a model with only on and off; a decision model has no
      setting; the build stops for a model with "on" and a level), then the earliest run (lowest run id); a model
      with one setup uses it. Every value of a row and of its details box is that one setup's; the row's other setups
      sit behind its expander ("N other settings"), each with its own tag beside its name. A row, as on Logic & Math's
      table (the project lead via Zeki #4606): rank, maker dot in the family colour and the family icon (the icon not
      on a phone), the model's official name with the chosen setup's tag and its class label beside it, the main-score
      bar from 0 to 100% with its Wilson 95% interval as the whisker, the score and that interval under it; from 900 px
      the other columns, below 900 px they are in the details box. The Turkish runs' option "Bilmiyorum" is named by
      its meaning in the board's labels ('with “I don't know”', `leaderboard.OPTION_SHOWN`). Nothing sits under the name (project lead, bus
      #3039): "name tag · maker · chat model / decision model" heads the details box (the maker is the family's maker in
      `maker_colours.json`, named as on the maker's own pages, each with its source URL). The details box
      (`leaderboard.details`, `site.js` `leaderboardDetails`, as on the Backgammon site)
      opens on a tap on the model's name (or its row) on a phone and on hover or the keyboard focus on a desktop, focus
      beating the pointer, capped to the room on a short screen, and closes on a second tap, a tap outside or Escape (the
      focus back on the name); no separate Details key sits under the name (Ümit via Zeki #5462, replacing Ümit #4665
      item 10's key); it lists the setup, its model's
      size ("Mixture of experts: 35.11B total, about 3B active per step. Size class uses 3B." for a mixture of experts,
      "Two models run together, option probabilities averaged 50/50: 57.36B in all, all used on every question." for
      two models run together, `size_sentence`, Ümit #4229; otherwise "Parameters: 26.1B dense", "Parameters: 8B dense ·
      4.5B effective" or "Parameters: not disclosed by maker", `parameters_text`; MoE or dense from the size record,
      `architecture`: MoE where it has active counts or its scope says mixture of experts, dense for a counted released
      checkpoint without them, nothing where neither holds; two models run together where its scope says "two full
      models", `combined`; the same words on the model page; Method's sizes table keeps `parameters_text`), its accuracy
      with the interval, reading and grammar, non-hallucination with "Bilmiyorum" with the share answered and the error
      rate (`held_line`), the answers kept at 99% confidence, No answers at this threshold where none
      (decision models), the cost with its basis and the request size, and "Open its answers →" (its model page), each
      line only where the data has it. The size shows there and on the model page (with what it covers, its
      source and the date read), and in short beside the name. **Controls** (`site.js` `leaderboard`): the part (Ümit
      #4181: Turkish, the default: the 2,198-question ranking, with reading, grammar, non-hallucination with
      "Bilmiyorum" (the share answered as a small second line, "answered 6%", as the score's interval line and as Logic &
      Math's, `held_cell`; Queued or Running instead of Not run while a side's run with the option is not in, as
      `page_config.json`'s `dont_know.under_way` gives it per model and side, Zeki #4748, and the build stops when a
      listed side's run is in) and cost; Turkish reading and Turkish grammar: the same rows ranked on the 656 reading or the 1,542
      grammar questions, with that accuracy and its 95% interval, then the whole Turkish accuracy and the other group;
      English reading: the English setups on the 547 kept reading questions, from `english_reading`, with
      non-hallucination with "I don't know" and cost; Both: Turkish and English accuracy on the same questions, as
      `turkish-vs-english/` computes them, ranked by Turkish), the type (All · Chat models · Decision models, Decision models by default, or
      the group `?models=` names) and All setups, which shows today's full ranking in the table's place; then the Class
      keys on a row of their own (Class: All · Tiny · Small · Medium · Large · Efficient · Workhorse · Flagship, Ümit
      #4217, one scale with the Logic & Math and Backgammon sites, combined with the type; `page_config.json`
      `model_classes`, `Site.model_class`: an open model with a disclosed size by its TOTAL parameters (#4245, the three
      sites' #4260-#4262: the maker's stated total, from its card or page or the size in its official name, as
      `stated_sizes` gives it, else a hosted model's record; `stated_total`; an open model whose maker states no total,
      GLM-5.3, has an undisclosed size and is priced; our count of the checkpoint shows only in the details box), Tiny below 6B, Small 6B to 15B, Medium above 15B up to 40B, Large above 40B (Gemma's
      E models by their total with embeddings); a
      closed model, or an open one whose maker discloses no size, by its standard list price per 1M input tokens, never
      an introductory or promotional one (#4238; `Site.list_price`: `model_classes.prices`, else results.json prices),
      Efficient $0.50 or less, Workhorse above $0.50 up to $3, Flagship above $3, "provisional" where only a
      promotional price is published; `small_models.left_out_models` in no class, under Class: All only; a class key
      with no row of the part and type in view hides). The old addresses `?models=small-chat` (and `small`) and
      `?models=small-decision` press Tiny and Small with Chat models or Decision models, `small-chat` on the English
      reading part as before; the class rule under the table is `model_classes.line`, the project lead's words. Each row
      shows a class label beside its name and tag, always starting "Open" or "Closed" (`Site.label`, #4229, #4231,
      #4245, Ümit #4445): an open model's total, "Open · 27B",
      whole from 10B up ("26B", "276B"), one decimal below ("7.9B", "0.4B"), "2.8T" from 1T up; a mixture of experts
      with a space, a small superscript "MoE" and its active count ("Open · 309B MoE · 15B active", "Open · 753B MoE" where none is
      stated), the number only for a dense model and for two models run together (REAX 1.3 "Open · 57B", #4269; its details
      box explains), a space and a .5rem gap between the name and the label; the mark takes the focus and a hover,
      focus or tap on it opens the row's details box, which ends "Size class uses the total (276B)."; a closed model
      "Closed · Workhorse" ("(provisional)" after a class from a promotional price only), an open one of undisclosed
      size "Open · Workhorse" (#4265); the details box of a priced model gives its class, the kind of price
      (standard list price, or introductory price, the only one published) and its source (`Site.price_note`). The #
      column numbers the rows in view: on the Turkish part their
      tier (a row joins the tier of the tier's top row when they share a tie-group letter of the full ranking's
      all-pairs test, else it starts the next tier; a thin line between tiers), on the other parts, which no all-pairs
      test covers, their rank, ties sharing a rank; a setup with web search is in neither (# shows a dash). Lines of
      text, all under the table: what the score means, what # shows, the row rule and, while a class is chosen, the class
      rule under it; the longer notes are on About. Every other page with model keys has the same Class row
      (`group_switch`, `site.js` `classPages`, under Site chrome above) and labels. **One view for the whole page**
      (Ümit #4665, `homeView` in `site.js`): the part, type and class keys govern every chart and table under the
      Leaderboard. The Non-hallucination chart shows the type's blocks and the classes' bars (`showGroup`,
      `classFilter`); `v3.js` draws its charts, the full ranking, the cost of every setup and the trade-off chart for
      the type and classes (`SETTINGS.classes`, each run's class from `page_settings`) and, on Turkish reading or
      Turkish grammar, for that part where the chart has its data (Accuracy, the trade-off chart, the full ranking's
      Accuracy, Confidence and Stability tabs; `syncView`). Each of them carries a scope line under its heading
      (`renderScopes`, `SCOPES` in `site.js`, `.chart-scope`): the part it shows, the type and the classes ("Turkish
      reading · Decision models · Class: Small"), and where it has no data for the part chosen its own named against
      it ("Turkish, all questions (not English reading)": Calibration, Cost, Latency, Non-hallucination and the cost of
      every setup are on all Turkish questions; Reading vs grammar shows both parts; English reading and Both have no
      chart here). **Address**: the view is written with `history.replaceState`, defaults left out, with Logic &
      Math's names: `?part=turkish-reading|turkish-grammar|english|both`, `?models=all|chat`, `?class=`, `?setups=all`
      for All setups open, and while it is open `?tab=`, `?sort=<column>&order=asc|desc` where the sort is not the
      tab's own, `?across=latency` and the Routing tab's keys; a reload, Back from another page or a pasted link opens
      the same view, and the type and classes go into the links to the other pages with model keys (`keepModels`).
      Old addresses keep working: `?models=small-chat`, `small`, `small-decision` (above), `?part=reading|grammar`
      (Turkish reading or grammar), `?tab=` or the Routing keys (open All setups at that tab), the hashes below.
      **Measure keys** (Ümit #4797, the project lead via Zeki #4798; Logic & Math's markup, order and behaviour, bus
      #4802; `site.measure_keys`, `site.measure_rows`, `site.js` `measureKeys`): above each part's table, Accuracy ·
      Non-hallucination · Cost · Latency · I don't know · Confidence (`div.lb-keys.lb-measures`). Accuracy is the
      Leaderboard, a pressed key; each other key links to that measure's view for the part in view, the chart or table
      further down that shows it (`MEASURE_VIEWS`), never another language's or another test's. Turkish, Turkish
      reading and Turkish grammar: the home page's `#non-hallucination` (holding back by confidence and with
      "Bilmiyorum"), `#cost`, `#latency` and `#calibration` (Confidence: the calibration gap, as shipped), on all Turkish
      questions as their scope lines say, and I don't know: the Hallucination tab's results with "Bilmiyorum"
      (`dont-know/#results`). English reading: `english/#non-hallucination` (the English "I don't know" run), `#cost`
      and `#latency`; I don't know: `turkish-vs-english/#dont-know-results` (the English option's runs); Confidence:
      `turkish-vs-english/#coverage` (risk and coverage from the five-option runs' confidence scores). Both:
      `turkish-vs-english/`'s `#non-hallucination`, `#cost`, `#latency`, `#dont-know-results` and `#coverage`, Turkish
      and English side by side. Each view opens with the same row (one per group of parts with a view on its page, all
      groups on the home page; the part in view shows), its measure's key current (`aria-current="page"`); a second tap
      on it, as Accuracy, returns to the Leaderboard in the same view (#4660). Every link carries the part (`?part=`),
      the type and the classes in view, each left out at the opened page's default, so the address keeps the measure's
      view and Back returns to it. **Look** (as Logic & Math's, #4796): a pressed or current key of the Leaderboard's
      rows, the pages' type and Class rows and the Measure rows is filled (`--view-current-*`); the score's value is
      monospaced at normal weight.
    - **In progress** (`#in-progress`, `leaderboard.in_progress`, under the Leaderboard; the project lead via Zeki
      #5064, #5065, #5071, Ümit #5067): the models joining Reading, each with the state of its English, Turkish and
      Page images sides (Queued, Running, Blocked, Done, or – where a side does not apply, with an optional note) from
      `page_config.json`'s `in_progress`, so a model shows before its results do and never as a 0. A side is Done
      exactly when that setup (provider and model id) has a published run of it, a Page images side when `vision.json`
      holds every one of its cells, and the build stops otherwise; a model leaves the table once all its sides are in.
      Page images publish cell by cell (Zeki #5177): while a model's Page images side is Running here, the Page images
      tab's cells it has not finished read Running with how many of the 763 questions are asked, or Queued, never a
      partial number (`vision.unavailable_cell`), and its charts show each condition once that cell is complete; its
      best OCR route reads Running with the routes done until all four are in (`vision.route_ready`), so it is never the
      best of a partial set.
    - **Turkish support** (Ümit #5067 item 3, confirmed by Zeki #5085): on the Leaderboard's Turkish parts (Turkish,
      Turkish reading, Turkish grammar) a model whose own card or maker docs do not list Turkish carries ‡ beside its
      name (`leaderboard.TR_MARK`), its details box says "Turkish not officially supported" and why (it lists other
      languages, or names none) with the source and the date read, and the legend under the table names the models
      that do list it. The evidence is `turkish-support.json` (status listed, not listed or not stated, source, quote,
      date read, by setup's provider and model; `Site.turkish_support`); the build stops when a Text tab setup has no
      entry.
    - **All setups** (`#all-setups`): the full ranking with its four tabs (Accuracy, Confidence, Routing, Stability),
      then the cost of every setup (`#cost-table`) and accuracy against cost or latency (`#chart-tradeoff`). A link to
      `#board`, `#all-setups`, `#cost-table` or `#chart-tradeoff` opens it first; `#headline` lands on the Leaderboard;
      `#info` opens About's summary and `#how-scores` About's How the scores work (`MOVED` in `site.js`).
    - **Finding sections**, each a heading that states its finding, one chart and one link, with "More about this
      finding" to its sentences in About's notes (`#notes-home-<part>`; `findings`, `finding_html` and `finding_notes`
      in `build_site.py`): `#accuracy` (the best chat setup against the best decision
      model; Share view and Download PNG stay in its head), `#non-hallucination` ("Bilmiyorum"), `#cost`, `#latency`,
      `#reading-grammar` and `#calibration` (the decision model with the smallest calibration gap as shipped, with
      its own check worded as it computes it). A heading shows its claim only while the claim holds, else the
      measure's name (`findings_checks` checks every heading against `results.json` on every build). Each heading
      follows the Leaderboard's type and class keys (`variant_headings`, carried in `data-variants`, shown by
      `site.js`): for every type (All models, Decision models, Chat models) with Class: All, each class, or Tiny and
      Small together, the build writes the heading for those setups from the same figures; under All models with both
      types the comparison (a claim only while it holds), with one type in view the sentence about it and the other
      type's figure as a "not shown here" clause ("The best decision model gets 8.2 in 10 questions right; the best
      chat setup, not shown here, 9.8"); Reading vs grammar counts the setups in view, Calibration names the smallest
      gap among the decision models (the chat setups under Chat models) of the classes in view; a view with no claim
      shows the measure's name. `variant_checks` recomputes every view's heading on every build. No filter bar and
      no part keys sit on the charts; the Leaderboard's keys choose what they show (above), and a filter in the
      address (`?topic=`, `?size=`, `?web=`, `?setups=` with the run ids picked) still applies.
    - **Footer**: About · Method · Data · GitHub.
  - **About** (`about/`, `sitebuild/about.py`, built by `build_site.py` after the home page): what the test is (short,
    with the Method page for the full study) with the intro and the counters, How the scores work (`#how-scores`), the
    notes behind the full ranking (the ranks sentence, `RANKS_NOTE`, and the cost notes), the leaderboard rules
    (`leaderboard.about_text`: the row rule, the dated checkpoints, the ranks, the whiskers), Notes on each page
    (`#page-notes`, `about.page_notes`: the longer explanations moved from the top of each page and the home page's
    finding sentences, each page under its own sub-heading and anchor, `#notes-<page>`; a page calls `Site.note` and
    leaves `more_link`, "More about this page", under its results), the summary (`about.SUMMARY`; `summary_checks`
    and `copy_checks` test it) and the links to Method and Data. No leader cards (highest accuracy, most answers kept,
    lowest cost): the project lead wants no leader summaries ahead of the results (via Zeki #4663).
  - **Experiments** (`experiments/`, `sitebuild/experiments.py`): first, right under the page title, Repeat checks
    (`#repeat-checks`, results.json `repeat_checks`; the project lead via Zeki #4831, #4838, #4844): one table per area,
    stacked, each under its own heading with its scope (Turkish Text, English reading, Vision with the picture only), in
    the Leaderboard's compact layout (`.lb-table`, no tier): Rank · Model (the maker dot in the family's colour, the
    official name with its tag, linked to its model page) · Run 2 · First run (each as the share right over its right
    answers / the area's questions) · Questions · Status (Done, Retained, Running, Queued). Run 2 is the area's second
    full run, the entry's first repeat (repeat 2, Vision's pass 2), never the best repeat or a mean. The rows with a Run 2
    come first, highest Run 2 first, ranked 1, 2, 3 without repeats (equal scores keep the area's order); the rows
    without one follow unranked (`–`), in the area's order, with `–` for Run 2, never 0. Below 900 px Questions is in the
    heading's scope and Status is a line under the name, so a phone keeps four columns. Every run (repeats 3 to 5 too)
    with its ids, dates, picks that differ, hardware or access and cost, the questions and the entry's note are in the
    row's details box, opened as the Leaderboard's (`site.js` `leaderboardDetails`): a tap on the model's name or row,
    the pointer or the focus (Escape closes). Under the tables, the line that
    the published scores stay the first run's. Then, under "Tests beside the ranking", one card each for Page images,
    Hallucination ("Bilmiyorum"), Web grounding, PWS-Decisions and the Artificial Analysis comparison, each with one line
    on what it measures and a status from the data (setups done, not run or still running, and PWS-Decisions' setups
    waiting for an API key or credit).
  - **Highlights** (`highlights/`, `sitebuild/highlights.py`): about English reading, one finding per card: the best
    decision model in English with its paired test against the other decision models, the best chat models against it
    (counted, not tested), the decision model that holds back most with "I don't know" in English, decision against chat
    models with that option, and the best small open model run in English only; then one short card pointing to the
    Vision tab (the page's only mention of the questions' original Turkish). Every setup is named by its official name
    and tag (`Site.plain` / `Site.shown`). Every number is computed from `results.json` and `vision.json` at build
    time; each card's heading is a claim the build checks (`finding`), stopping when the data no longer supports it.
  - **Questions** is Every question (`questions/`), with links to Where models disagree, Topics and Compare.
  - **The home page's charts**: each chart card has a line saying
    which way is better, and each bar chart names its value columns above them (`COLUMN_HEADS` in `v3.js`; the static
    charts through `hbars`' head or columns): Accuracy, each bar with its Wilson 95% interval as a whisker (`wilson` in
    `v3.js`) and a line at chance (1 / `baselines.options`), its value cell "77.9% (76%–80%) lm" (accuracy, the interval
    in whole percents, and on all questions the setup's tie-group letters `runs[].group`), with each setup's cost and median
    latency beside its accuracy as the Cost and Latency cards write them (on a phone at the right of the name's line, over
    the bar) ($ in the chosen cost unit, ≤ before an
    upper-bound estimate, each estimate's basis in its tooltip and the note under the chart; seconds, * for a latency
    measured on a sample; No list price for a cost of a setup on our own hardware with no estimate, `cost_missing` in
    `sitebuild/site.py` and `costMissing` in `v3.js`, on every page; Not measured for any other value nobody measured).
    How a setup ran is its tag beside its name, a smaller second line in a chart (`chartLabels` in `v3.js`); its
    settings in words are in the tooltips and on the model page. Non-hallucination
    (`non_hallucination` in `build_site.py`, static HTML, one copy per group; the same two sides on the Hallucination tab,
    and on english/ with confidence Not measured in English and the Turkish reference apart, `sitebuild/holding_back.py`;
    on the Hallucination tab its other charts and its table also show Decision models and Chat models as separate
    blocks, the paired test being decision models only) shows two kinds of holding back side by side, each with Decision
    models and Chat models as separate blocks with their own heading and ranking (both under All models, never one mixed
    list): Holding back by confidence, each setup's Text tab run at the 99% threshold (`runs[].confidence.sure`: the
    answers kept, the bar their share of the questions, the wrong ones among them, and the ranking score
    `confidence.auroc`; no wrong answer first by answers kept, then by the share wrong, a setup with none kept last,
    muted, reading No answers at this threshold; each block names its kind of
    confidence, a setup without one reads No confidence reported), and Holding back with a "Bilmiyorum" option, the
    Hallucination tab's rows of that group (`results.json`'s `dont_know`) in its order, the rate with "Bilmiyorum", then
    in columns of their own the share answered (the attempt rate, as that tab writes it) and the error rate among the
    answers (wrong / answered), bars in family colours; under the decision block the decision models that chose the
    option on fewer than `dont_know.vs_confidence_share` of the questions, with how often each did (`rare_note`), under the
    chat block the chat setups whose Turkish run is still running with their reason, a link to that tab).
    Cost; Latency; Reading vs grammar;
    accuracy against cost or latency (under All setups), with the Pareto line (the setups in view no other setup in view
    beats on both) and, shaded, the region better than the median setup in view on both; Calibration (the calibration
    gap, as shipped, on all questions). The charts draw every setup of the Leaderboard's type and classes (the
    decision models by default, every setup together or the chat and general models), within the filters;
    each bar or dot takes its model family's colour (`page_config.json` `model_families` puts each run in a family by
    provider and model; `maker_colours.json` gives each family its maker and colour, a maker's line of models sharing one
    colour, in every chart and both groups; `run_families` in `sitebuild/site.py` stops the build unless every run
    has exactly one family and `model_families` unless exactly one maker lists each family), with the families shown
    in the legend, on one compact line of their own that wraps
    (`.families`, on every page). Nothing scrolls inside a chart box: each bar chart, Reading vs grammar and the table
    under Cost show their first 10 rows, with a "Show all N setups" key that opens every row in place and closes them
    again (`topRows` in `v3.js`); a highlighted setup ranked below them is added after them, set apart by a dotted line.
    The trade-off chart has a fixed height. A downloaded PNG has every row of the view.
    Under All setups, the table of every setup (`#cost-table`, `costTable` in `v3.js`) holds every setup of that
    type and classes, whatever the other filters: cheapest
    first (setups without a cost last, by accuracy), with $ per 1,000 questions as the Cost card writes it, its cost over
    the cheapest setup's (× cheapest, empty where the cost is not measured), accuracy, median latency, the answers kept at
    the 99% cutoff (right of kept, and the questions skipped: the scored total minus the kept, that is the answers below
    99% confidence plus any invalid answers, which the cell counts where there are some; No answers at this threshold
    where none is kept, as in the Confidence tab, which sorts it last), the non-hallucination rate
    with the share answered and the error rate where the Hallucination tab has the model (Not run otherwise), and a Pareto tag for the setups
    the trade-off chart's rule puts on its dotted line among all setups with a cost. No score combines these columns.
    Kept and skipped counts stand beside the cutoff figures: the full ranking's Confidence tab; the Routing tab wherever
    `results.json` stores whole counts (the fixed 99% rule and the most confident quarter in the replay and in the live
    tests, the half rule in the live tests; the half rule's replay figures are means over 300 splits, so they stay
    shares); the model pages; the Method page; and the Hallucination tab's derived cut-off (answered and held back).
    The full ranking (All setups) has four tabs: one table for the group in view, ranked by
    accuracy (in the all view decision and chat models together, each row saying which); the Routing tab opens by the
    share taken and the Stability tab by changed answers, most first, ties by the same wrong answer in all five runs,
    most first (`DEFAULT_SORTS` and a column's `tie` in `v3.js`). A model ID with runs in both groups
    reads the same name in each row, its tag telling the routes apart ("GPT-6 Luna" with "Decisions API" and with
    "low · chat"; `sitebuild/names.py`). The full ranking's rows carry no notes: a setup's notes are on its model page (How we
    called it), which its name links to. The Reading vs grammar chart lists the setups in the full ranking's order.
    `v3.js` draws the charts and the four tabs of the full ranking in the
    browser from two compact files that `build_site.py` writes from `results.json` (`home_data`), which stays the
    published download: `data/home.json`, preloaded by the page, holds what the first draw reads (the runs, each
    run's confidence cut to the counts at the sure cutoff that the Cost table shows, and the units, prices, routing
    replays and live tests, repeats and Hallucination models), and `data/home-more.json` the runs' whole confidence
    and the cascades without their curves, which `v3.js` loads when the Calibration chart comes within a screen of
    the view or the Confidence or Routing tab opens; until a chart is drawn its box reads Loading charts…. Accuracy
    for a part or topic and its Wilson 95% interval come from the counts there. The filters, the full ranking's tab,
    sort and the Routing tab's four choices are kept in the URL (`?topic=3&size=16&web=with&setups=145,199`; the
    Leaderboard's keys above), so a reload, Back or a shared link (Share view copies it) opens the same view.
    The Routing tab's scope line names the questions its numbers cover: a live test's held-out questions
    (`pipelines[].held_out`), the half rule's held-out half, or all questions. The page's fixed copy quotes numbers; the
    script checks each against `results.json`, prints every claim that differs and then exits with status 1,
    after writing the pages.
  - **Routing LLMs** (`ROUTE_LLMS` in `sitebuild/site.py`, each a key of `page_config.json`'s `named_runs`): Opus 5.5
    low, Sonnet 5.5 high, Astra low, Sol low and Gemini Flash low at 1 and 16 questions per request; Opus 5.5 high,
    Astra high, Sol high, Terra high, Terra low and Gemini Flash high at 16 only. The request-size control offers
    only the sizes the chosen LLM has, so a 16-only LLM (picked, or asked for at 1 per request in the URL) shows 16.
    Copy and charts about the routing LLMs at 1 question per request cover only the first five; the estimated
    saving's claim covers all 16 LLM setups. Each LLM's model page links its Routing view.
  - **Latencies**, everywhere they are shown (tables, tooltips, charts, model pages, Method page, Compare,
    `chart-renderer`): three decimals below 1 s (0.223), two from 1 s to under 10 s (7.10), one from 10 s (53.7);
    `build_page.seconds` in Python, `secondsText` in `site.js`, `seconds` in `chart-renderer`. Tables sort on the
    raw values.
  - **Reasoning levels**: a level is printed as its provider writes it ("xhigh reasoning", "max reasoning"),
    never capitalized or rewritten. `page_config.json`'s `reasoning_levels` lists each model's documented levels,
    default and top level, with its source and the date we read it; each run of such a model shows them in its
    model page's Settings, with the run's own level.
  - **No text above the results** (project lead via Zeki, #4663, #4666): on every page with results, nothing but the
    title, eyebrow, keys, filters and the "On this page" links stands between the top of the page and its first chart,
    table or card list; About and Method are the explanation pages. A scope goes into the first chart's or table's own
    heading (English and Turkish vs English: "· 547 … machine-translated"; Vision's first three charts: "· 763 Turkish
    questions"; a topic's table: "· 131 scored questions"); a definition or warning goes to a note under the results,
    with "More about this page" (`more_link`) beside it: the Leaderboard's meaning line under its table, the counts
    line under the Leaderboard, the All setups tabs' definitions and the Confidence guide under the board, English's
    and Turkish vs English's limit under the accuracy charts, Hallucination's definition under its first charts, Web
    grounding's and PWS-Decisions' lines under their charts, Vision's note (no longer starred: nothing links to it),
    Every question's scope and Difficulty lines, Topics' scope and cell lines, Disagreements' definitions, AA's line
    and the reply cards' label, and Data's line, each under its table or cards. Only an empty view's line may stand
    above.
  - **Page images** (`vision/`, `sitebuild/vision.py`): the 763 questions with
    underlined or numbered words, asked as text (A), as a page image (B), as both (C) and through four OCR
    models (D). Decision models and other models in separate tables; in each, the image models ranked by B,
    then the text-only models ranked by their best OCR route. A condition `vision.json` does not hold reads
    "Not available" with its reason, and a row without the result it is ranked by follows the ranked rows.
    Below: the models not run, with their reasons, and the OCR models' error rates and kept underlined and
    numbered words on the human-verified question text. A setup that is condition A there shows its row on
    its own page. While every model there is a decision model, the models' charts, tables and findings carry
    `data-models="all decision"` and the chat view shows a note in their place; the OCR models' parts show in every
    view. Hallucination and Web grounding do the same for their parts. Once a chat model (`Site.decision` false) has a
    result, the face's model charts come once per view-bar group (`data-models` all, chat, decision; the all group
    keeps the plain ids, the others `-chat` and `-decision`, as on English reading): the decision group's charts and
    table are as before, the chat group shows the chat models' charts and the "Other models: chat and general models"
    table (shown for the all and chat groups), the all group every model. What we found, the summary's averages and
    Highlights' Vision card stay computed over the decision models only (`vision.decision_only`), each with a line
    saying so. The method then says how a chat model is asked, from `vision.json`'s `chat_conditions` (B, C and D one
    question per request with a plain answer line, the crops as image parts after the text, D the same OCR text with
    no images; A its Turkish Text run's answers; no option probabilities, so accuracy only), and names a chat model
    whose condition A run was asked otherwise (more than one question per request, a stated confidence) there, under
    the other models' table and on its model page; the build stops when `chat_conditions` no longer states this or a
    chat cell holds probabilities. In `bench-scores.json` a chat model's question has as many options as the largest
    option-probability map any model gave it, and its `calibration_error` is null.
  - **Other pages**: each module of `sitebuild/` (`PAGE_MODULES` in `build_site.py`) returns whole pages,
    written to `<path>index.html`: one page per setup (`models/<run>/`, opening with a summary: accuracy with its 95%
    interval, the answers kept at 99% confidence with the wrong ones among them, No answers at this threshold where
    none is kept, cost and median latency; the run
    record's harness seed, commit and prompt version folded under Settings; for a setup with an English run, an English
    section (`#english`): the first English run's right answers of the 547 kept questions, accuracy with its range over
    several runs, the English "I don't know" non-hallucination rate where measured with the share answered and the
    error rate beside it, the first English run's cost and
    median latency, and the English runs' ids, dates (`english_reading.models[].dates`), request size, reasoning,
    prompt version and translations' SHA-256 from their records in `answers.json`; `models/` itself sends the reader to the home
    page's All models view, which replaced its list of every setup; query and fragment kept), every question
    (`questions/`, with `questions.js`: filters on question ID, book page, topic and difficulty, 100 rows at a time,
    all kept in the URL; every row shows without JavaScript), one page per question (`question/?id=…`, drawn by
    `question.js`, with a line for readers without JavaScript), where models disagree with the key (`disagreements/`:
    the questions where the chat setups in `page_config.json`'s `key_disagreement` agree on another answer, then the
    questions most setups got wrong), topics with the accuracy-by-topic heat map (its colour scale's legend, headers
    that stay in view while it scrolls, and a setup choice kept in `?setups=` by `topics.js`) and one page per topic
    (`topics/`), Compare (`compare/`, drawn by `compare.js`: the accuracy difference on all questions with its 95%
    interval and one sentence on what it means first, exact McNemar test as in `benchmark_metrics.py`, and each cost
    with its basis in the model page's words, `Site.cost_basis_text`, passed in `compare-settings`), Page images
    (`vision/`), Method (`method/`: the tests, the view bar's rows and the top links, then the Turkish test's method)
    and Data (`data/`: the downloads and both changelogs). `sitebuild/site.py` holds the shared page shell.
  - **Artificial Analysis's Decision Index models** (`aa-decision-index/`, `sitebuild/aa_index.py`): our numbers
    for the models of Artificial Analysis's Decision Index v1.0 as its post of 22 October 2026 lists them
    (`page_config.json`'s `aa_decision_index`, by run id; a run that is missing or not a decision model stops the
    build): charts of accuracy, the non-hallucination rate, cost in US dollars per 1M questions (`hbars` with a dollar
    axis) and the median latency per request (a seconds axis, with how many requests each model had in flight), and one
    table with accuracy, reading, grammar, page images
    (picture alone), non-hallucination with the share answered and the error rate, cost per 1,000 and per 1M questions and the median latency per
    request, every value from
    `results.json` and `vision.json`. It opens with the cards of our thread on X, as made for the thread and never
    redrawn (PNG files in `aa-decision-index/`), in the thread's order, each with its alt text from the thread, the
    thread's results version and a note (`page_config.json`'s `aa_decision_index.thread`); the build stops when a
    card's file is missing or not a PNG, or its alt text is empty. Nothing links the page from the navigation bar.
  - **`data/picks.json`**: each leaderboard setup's pick and score on each scored question, written from
    `answers.json` by `sitebuild/questions.py`, which checks every pick against its grade. Scores are floored
    to four decimals, so a score below the 99% cutoff never reads as 99.00%.
- **The earlier page** (`v1/`): the page as it was on 14 October 2026 (results 84d533b4), with its own
  copies of `results.json`, `page_config.json`, `style.css`, the charts and the sharing images it links
  to; its answer export link points to `answers.json` at commit 77f40bc. Nothing rebuilds it.
- **Redirects** (`v2/index.html`, `v3/index.html`): send the preview addresses here, keeping the URL's query
  and section.

## Running the benchmark

`runner/` holds the runner, the run script of every published configuration, and the scripts that
built the question bank. [`runner/README.md`](runner/README.md) gives the setup, the question-bank
format, how someone who owns the book rebuilds the bank, and how to run each family of
configurations: hosted APIs, subscription command-line tools, vLLM and SGLang servers and self-hosted
decision servers. The questions themselves cannot be shared.

## Graphs

`chart-renderer/` draws the graphs from `results.json`, and takes which runs are decision models from
`page_config.json`. It uses ratatui's `Chart`, `BarChart`
and `Canvas` widgets, rendered into ratatui's test backend, so each graph is a buffer of terminal cells.
The Method page shows some of them as SVGs next to their tables, from `charts/`: `<name>.svg` in the light
theme and `<name>-dark.svg` in the dark one, written from the same buffer. `v1/charts/` keeps the copies the
earlier page shows.

- **SVG output:** a small writer (`chart-renderer/src/svg.rs`) turns each buffer into an SVG on a fixed grid of
  8 × 16 px cells. It draws braille dots, box lines, bar blocks and dots as shapes, so a graph looks
  the same whatever fonts the reader has. The dark version maps every colour through the `DARK` table,
  whose entries keep at least 4.5:1 against the dark card; a colour missing from it stops the build.
- **Snapshots:** the same buffer, as text, is the graph's insta snapshot in `chart-renderer/tests/snapshots/`.
  When the data changes, the snapshot diff shows how each graph changed.

```bash
INSTA_UPDATE=always cargo test --manifest-path chart-renderer/Cargo.toml   # accept the new graphs
```

`cargo insta review` (from `cargo install cargo-insta`) shows the changed snapshots one by one instead.

### Model family icons

On the web pages (not the Rust graphs in `charts/`, which keep text labels), every model name has its family's icon
on its left, 14 px and hidden from screen readers. A family in `page_config.json` `model_families` names its icon by
Simple Icons slug; its SVG path is vendored in `sitebuild/family_icons.py` from
[Simple Icons](https://simpleicons.org) 16.36.0, whose icon data is CC0 1.0 (the marks stay their owners'
trademarks, used here only to name their models). Official marks: Gemini (Google Gemini), Gemma (Google), GPT
(OpenAI), Claude, Qwen, DeepSeek, Kimi, MiMo (Xiaomi), MiniMax, Perplexity, Microsoft, vLLM-SR (vLLM), Ministral (Mistral AI)
and VibeThinker (Sina Weibo, for Weibo AI), drawn in the text colour.
Simple Icons has no mark for xAI, Z.ai or Liquid AI, so Grok (xAI), GLM (Z.ai) and Liquid (Liquid AI) use the
public-domain logos on Wikimedia Commons, scaled to one 24 x 24 path; each MARKS entry names its source and date read.
A family with no findable vector mark (Inception, Fastino, Inkling and the rest) gets a plain shape (circle, diamond, triangle
or ring) on its own colour, never a letter. `family_sprite` in
`sitebuild/site.py` puts every icon as an SVG symbol once on each page.

### Maker colours

`maker_colours.json` is the one colour map of the three benchmark sites (English & Turkish Reading, Logic & Math,
Backgammon), kept by the Logic & Math site (`work/maker_colours.json` there) and copied here byte for byte: each maker
with its colour, the families it makes, the page that names it (`maker_source`) and its lowest contrast against the
sites' four backgrounds. A colour belongs to the maker, never to the provider that serves the model. The project
lead fixed seven makers' colours (OpenAI, Google, Anthropic, xAI, DeepSeek, Moonshot, Liquid AI; `fixed_by_umit`);
the file's checks keep every pair of colours at least 12 apart (CIEDE2000) and every colour at a contrast of at
least 2 against the light and dark panels and pages. To change a colour, change it there and copy the new file here;
the build reads nothing else for makers or colours.

## Updating the results (maintainer)

This needs the benchmark's private files: the report the benchmark script writes
(`benchmark-results.md`) and the per-question export from its answer store.

`export_results.py` rebuilds `results.json` from the report. Its leaderboard holds the runs over
a full question set that are graded against the same question bank as the newest such run, whichever
version of the bank they ran on. It leaves out repeats, runs on listed questions and runs whose correct
option was replaced (a memorization test, not an accuracy run), and exports only aggregate numbers: no
question text, prompts, answers or local paths. The comparisons between runs come from the report's
`benchmark-analysis` record:

- paired tests with Holm-adjusted p-values;
- cascades simulated and run as pipelines;
- decision-model doubt;
- confidence sources scored on the same answers;
- each run's change from the previous question bank;
- the run-to-run variation of repeated runs, with the request times pooled over the runs that recorded them.

`--answers` names the benchmark's per-question export. The export takes from it the Decider v1.1 replay
(`replay`), each listed comparison's Holm p-value over all pairs (`p_holm_all`) and the
answer-key baselines (`baselines`), and writes `answers.json`: the main runs, the repeats of each
repeated configuration (`repeat_runs`), the runs of each measured live test (`pipeline_runs`; a run
that serves several tests, such as a second model alone on the shared test half, lists every role it
has), the runs with the "I don't know" option (`dont_know_runs`), the English reading runs (`english_runs`), the
English "I don't know" runs with their Turkish counterparts on the kept questions (`english_dont_know_runs`,
`english_dont_know_turkish_runs`), the option-word check's runs (`dont_know_word_runs`, with `dont_know_word_prompts`)
and the hosted GLiDE rerun (`rerun_runs`), the web grounding test's own runs (`web_grounding_runs`) and the repeat
checks' Text and English repeat runs (`repeat_check_runs`, each with its first run as `repeat_check`), with scores
and option probabilities at full precision; no run is in two lists. The sections of `ANSWER_FILES` go to files of
their own beside `answers.json` (`answers-repeats.json`: `repeat_runs`, the largest section, and `repeat_check_runs`;
`answers-english.json`: `english_runs`, `english_dont_know_runs` and `english_dont_know_turkish_runs`, moved out on
12 November 2026 when `answers.json` reached the limit), so that no file nears
GitHub's 100 MiB limit: each repeats `answers.json`'s `schema_version` and `dataset`, and `answers.json` lists them
under `files`. The export stops when a file would pass `ANSWERS_LIMIT` (80 MB); then move another section to a file
of its own. `reproduce.py` (`load_answers`), `build_page.py` and the pages read them merged; the Data page lists each
file with its size and what it holds. The English reading section needs
`english-reading.json` in this folder and the web grounding section `web-grounding.json` (each run's input tokens by
group, what the grounded searches returned and PWS-Decisions' aggregates; written by `web_grounding_inputs.py` from the
benchmark database and PWS-Decisions' run folder, and committed with the site). The export stops unless every English
run carries its translations hash and was asked exactly its kept
questions. Then refresh `runner/` and
the metric code, and check the result:

```bash
./benchmark_ollama.py --export-answers /tmp/benchmark-answers.json   # in the benchmark folder
./export_results.py /path/to/benchmark-results.md --answers /tmp/benchmark-answers.json
./sync_runner.sh /path/to/benchmark-folder   # runner/ and benchmark_metrics.py
python3 reproduce.py
python3 build_site.py   # set "published" in page_config.json first
grep -r -I -E '/(home|Volumes)|T[7]' --exclude-dir=.git --exclude-dir=target .

The last command must find nothing; its pattern is written so that it does not match itself.
`sync_runner.sh` refuses to copy a file that contains a local path; it copies every `run_*.sh` script
except those listed in it as behind no published run, and prints the list.

**Repeat checks** (results.json `repeat_checks`, the Experiments page): `page_config.json`'s `repeat_checks` lists
the areas and one entry per area and model: `area`, `name` (as published), `runs` (the first run; a Vision entry its
first pass's runs, with `first_dates`), `repeats` (Text and English: the repeat run ids; Vision: pass numbers in
`vision-repeats.json`; empty until done), `status` (`retained`: repeats already on the Stability tab; `queued`;
`running`; `done`) and a `note` on where it runs. A Text or English repeat is a runner run of the first run's
configuration with `--repeat N`; the export reads it from the report it is given and holds it out of every other
section (the main runs, the English reading models, the Stability tab's `repeats`), so no published score changes,
and stops when a named repeat is missing from the report, has another setup, or would join a configuration that
already has repeats on the Stability tab. Vision rows read `vision.json` and `vision-repeats.json`
(`vision_track.py repeats`). To add a finished repeat: put its run id (or pass number) in the entry's `repeats`, set
`status` to `done`, then export with the repeat's report among the records and its run id among the runs (or copy the
new `vision-repeats.json`), and run `reproduce.py`, which recomputes every first run and repeat from the answers.

A new provider needs an entry in `PROVIDERS` (its access route and how it is paid for); the script
stops until it has one. A decision model's provider also goes in `page_config.json`'s
`decision_model_providers`, and a new model of a provider in its `mixed_providers` stops the build until it
is listed there. A new model is shown by its ID unless `MODELS` gives it a display name, and a
model on our GPUs needs its hardware there. Every exported model needs a size record in `MODELS` (the export stops
without one): `parameters` (the total, or `None` when the maker publishes no size: "not disclosed by maker"),
`active_parameters` for a mixture of experts (DeepSeek's two figures, prefill and decode, kept apart),
`effective_parameters` only where the maker states one, `parameters_scope` (what the count covers: language model,
vision encoder, scoring head), `parameters_source` (the maker's official pages, or the checkpoint counted as
`repo@revision` from its safetensors headers' logical tensor shapes, never quantized storage, scales or an adapter
file alone; for an undisclosed size, every official page checked) and `parameters_read` (the date read). A size is
never guessed from a name or taken from an open sibling of a hosted model. The records reach `results.json` per run
and drive the details box, the model pages, Method's size table and the size labels and classes. Prices live in `PRICES` in `runner/benchmark_ollama.py`:
the export takes each run's price from the report, and stops when a paid or free-tier run has none or a
price applies to another kind of run: a self-hosted run may only take its maker's list price for the same
model (our hardware cost is not measured), and a free-tier run the list price of the model it called.
