# When should you trust a decision model?

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
and `answers.json` with `answers-repeats.json` beside it, which hold every answer of every main, repeat and routing
run (the repeat runs in `answers-repeats.json`), with its
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
version and the key version to cite.

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
  `vision.json`'s per-condition numbers and paired tests from the answers it holds, and checks its `requests`
  block (one stored answer per question and cell, answers naming an option plus refusals, the continued
  cells and runs, the lower bound on requests sent) and that its full leak scan covers every OCR output of
  every crop. Each engine check (`engine_checks`) must hold an answer for every question; its right answers,
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
  other English reading models in English), each setup's answers in selection order (`wrong_by_rank`, from which
  every curve is drawn) and the markers of the runs with the option; for answers at 95%+ confidence (`high_confidence`)
  each Text tab run's kept and wrong answers at 95%, Liquid d1-ultra's repeat runs, the three models Artificial Analysis
  ties at 65 in all their runs at six cutoffs with the check at every whole percent up to 98%, and d1-ultra's English
  runs with the questions they got wrong; and for Liquid d1-ultra against each English reading model
  (`english_reading.against_reference`) the paired counts, the exact McNemar test and Holm over the others.
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
  - **All benches** (`sitebuild/all_benches.py`, `all-benches.css`, `all-benches.js`): every Zeki Works bench on one
    page at `/analysis/all-benches/` (and its Methodology, `method/`), outside this site. The build writes it into
    the git-ignored folder `_suite/all-benches/`, self-contained (its pages, `benches.json` and copies of
    `suite-bar.css`, `v3.css`, `site.js`, `all-benches.css` and `all-benches.js`); publishing copies that folder to
    the mirror's `analysis/all-benches/`. `all-benches/` and `all-benches/method/` here are redirects to it that keep
    the query and the fragment; `all-benches/benches.json` is what the build last read from the other sites. This
    site's `bench-scores.json` feeds it three benches: Reading · Turkish (`reading-text`), Reading · English
    (`reading-english`, the kept reading questions in English) and Reading · Vision (`reading-vision`).
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
    `about/`, `method/` and `data/`. On a phone the tab row wraps to a second line, so every tab stays in view. No other
    navigation row sits under the suite strip; a page's own part links (`.face-nav`, as PWS-Decisions' steps) stay in
    the page. **Model groups**: `?models=all|decision|chat|small-chat|small-decision` (all when missing; trailing dots,
    punctuation or spaces are dropped, so `?models=all.` reads as all; the old `?models=small` reads as `small-chat`) still picks the group on every page that shows its parts by group
    (`data-models`; `site.js` shows each element only for its groups), and such a page carries its own group keys at
    the top of its body (`group_switch`, All · Decision models · Chat models · Small chat models · Small decision
    models, in the page, not in the top bar), with the group's rule under them in a small view; on the Leaderboard it
    sets the type and size keys (below). **Small chat models** and **Small decision models** (`Site.small`, `Site.in_group`,
    `v3.js` `isSmall`, `inGroup`; split by kind so the two never mix, project lead bus #3876, the three sites #3877-#3882):
    one size rule on the three sites (project lead through Zeki, bus #3812-#3816), worded per group in
    `small_models.groups` (`line`): a setup is small when its model's total parameter count, or for a mixture of experts
    every active count (DeepSeek-V4.1-Flash's 8B prefill and 16B decode keep it out), as its maker discloses it is at
    most `small_models.max_parameters` (15B); a model whose maker discloses no size never is. Small chat models holds the
    small chat models, Small decision models the small decision models. `small_models.left_out_models` are never small
    here: the six small setups only this site ran (Laya, Laya multilingual, GLiNER2.5-multi-Decide in the decision
    group's sentence; GLiNER2.5 Multi (base), Qwen3-14B, Erk-14B in the chat group's; Zeki #3805, #3818), named in each
    group's `left_out_text` and shown under All. Inkling Small is in Small chat models by its card's 12B active
    parameters. A part that covers every decision model whatever its size (a Holm family, a decision-model finding)
    is not split by size: under both small groups a note (`small_note`) stands in its
    place, as under Chat models. A group asked for in the address stays in the links marked
    `data-keep-group`. The footer of every page (`footer`): About · Method · Data · GitHub, the downloads and the
    results version. **Cost unit**: every cost reads per 1,000 questions or per
    1M questions, one choice for the whole site (the keys in each cost card's head, `cost_switch`; `site.js` keeps it in
    `?cost-unit=1k|1m` and localStorage `costUnit`, in `<html data-cost-unit>`, which each page's `<head>` sets before
    it renders). Static values and unit names carry both units (`cost_value`, `cost_per`, `cost_unit_in`, `cost_tick`
    in `sitebuild/site.py`) and `v3.css` shows the chosen one, per 1,000 without JavaScript; `v3.js` and `compare.js`
    write theirs with `costScale` and `costNumber` and redraw on the `costunit` event. The two English pages render, in
    static HTML, one copy per group of every part that depends on the setups shown (`data-models="all"`, shown without
    JavaScript; `decision` and `chat` hidden), with its counts and sentences computed for that group and its setups
    ranked by English accuracy within it, the Non-hallucination parts too (decision and chat models with "I don't know"
    runs ranked together in the all copy; a chat model's side still running reads Running with `page_config.json`'s
    `dont_know.running`); the parts about decision models only appear once (`data-models="all decision"`), as the
    option-word check is for decision models only. A setup that shares its name with another English setup is labelled with the settings
    that tell them apart, as the home page's charts do ("Gemini 3.8 Flash (low reasoning, 16/request)"). English reading
    (`sitebuild/english_view.py`) shows every English setup on the 547 kept reading questions: under a one-line lead
    and the translation check's limit in one line (`limit_line`; the full lead, `limit_note` and the experiments line
    are in About's notes on each page; neither English page has a links row of its own),
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
    setups (Turkish accuracy Not run; no Turkish reference); the Both and Turkish parts and the paired tables and tests
    of Turkish vs English leave them out, which lists them per group under its main table with their English accuracy.
    With no model page, their name links to their row on English reading (`#english-only-<run>`); their details box says
    "English only" and how they were called. A `vllm-plain` run's access text comes from its record's `request_params`
    and the model's `backend`, `precision` and `revision` in `MODELS` (`plain_access` in `export_results.py`), its
    confidence reads not measured, its cost is the GPU time as for the other local runs, and its prompt version is
    that of the answers file's `plain_prompts` (the runner's `PLAIN_PROMPTS`), published in `answers.json` with it.
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
    (the answered share, the wrong share of the answers and the non-hallucination rate together; both as below), then
    that rate against the same model held back
    by its confidence, the paired test of the two (the wrong answers only one of them made, with Holm-adjusted p and the
    models outside the test named) and accuracy with the option against accuracy with five options, then the added
    comparisons: the Turkish vs English tab's English questions with "I don't know" against "Bilmiyorum" in Turkish (that
    tab's charts and table, `dont_know_charts` and `dont_know_table` in `sitebuild/english_reading.py`), the option's
    word ("I don't know" instead of "Bilmiyorum" on the same Turkish questions) and those runs against confidence, hosted
    GLiDE against a new five-option run in place of run 129, and the same number of answers (each model's five-option run
    keeping its k most confident answers, k being Liquid d1-ultra's answered count with "I don't know", against Liquid
    d1-ultra by a paired bootstrap: in Turkish every setup of the Text tab, in English every English reading model; the
    Turkish plot draws each setup with runs with the option and the English plot every English reading model, each curve
    of wrong of answers against answered with the setup's runs with the option marked, and under Info a small plot per
    Turkish setup shows every setup's curve against Liquid d1-ultra's; inline
    SVG by `line_plot` in `sitebuild/site.py`), and answers at 95%+ confidence (each decision model's Text tab run
    keeping the answers whose chosen option has a probability of at least 95%, with the wrong ones among them; Liquid
    d1-ultra's repeat runs; the three models Artificial Analysis ties at 65 in all their runs at six cutoffs, with the
    check that d1-ultra's worst run stays below their best at every whole percent up to 98%; d1-ultra's English runs at
    95%; `high_confidence`). Every "I don't know" table leads with Answered
    ((right + wrong) / questions) and Wrong of answers (wrong / (right + wrong)), the non-hallucination rate after them.
    Turkish vs English opens with one line and the translation check's limit in one line (the lead with the headline,
    `limit_note` and the experiments line are in About's notes on each page), then its charts: accuracy
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
    one short line with "More about this page" (the line naming both setups, three runs per setting, the ranking keeping
    each setup's first run, and the run dates, is in About's notes on each page) and three result cards (the Turkish
    full bank, English reading and PWS-Decisions: mean accuracy off → with web, the
    change in points, the runs' range, the cost off vs ≤ with web). Then four charts in the
    home page's format, each in a section with the id the view bar's Measure row uses (`accuracy`,
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
    baseline as a line, labelled as theirs), Cost ("incl. search" where a web search fee is counted, ≤ where it is an
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
    knowing the facts?" (`#habits`, a decision-model part: the chat view shows a one-line note in its place) gives a
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
    - **Hero**: the question "When should you trust a decision model?" and one line of counts (`hero_counts`:
      questions, models, that is the Leaderboard's rows, setups and the last update) with "More about this page"
      (About, where the intro, `INTRO`, and How the scores work now stand; Ümit via Zeki, bus #3521).
    - **The Leaderboard** (`#leaderboard`, `sitebuild/leaderboard.py`): one row per model, a model being its model ID,
      its kind (chat or decision model) and web search (a setup with web is its own row; different version names are
      separate rows). A dated checkpoint joins its original's row only through `page_config.json`'s
      `leaderboard.dated_checkpoints` (today `deepseek-v4.1-flash-1017` under `deepseek-v4.1-flash`), never by similar
      names. **Row rule**, fixed and never the best score: the model's highest reasoning setting (none or off < minimal
      < low < medium < high < xhigh < max; "on" above off for a model with only on and off; a decision model has no
      setting; the build stops for a model with "on" and a level), then the earliest run (lowest run id); a model
      with one setup uses it. Every value of a row and of its details box is that one setup's; the row's other setups
      sit behind its expander ("N other settings"), each with its setting under its name. A row: rank, maker dot in the
      family colour and the family icon, the model's name, the main-score bar from 0 to 100% with its Wilson 95%
      interval as the whisker, and the score; from 900 px more columns. Nothing sits under the name (project lead, bus
      #3039): "maker · chat model / decision model · setting" heads the details box (the maker is the family's maker in
      `maker_colours.json`, named as on the maker's own pages, each with its source URL). The details box
      (`leaderboard.details`, `site.js` `leaderboardDetails`, as on the Backgammon site)
      opens on a tap on a phone and on hover or the keyboard focus on a desktop, focus beating the pointer, capped to
      the room on a short screen, and closes on a second tap, a tap outside or Escape; it lists the setup, its model's
      size ("Mixture of experts: 35.11B total, about 3B active per step. Size class uses 3B." for a mixture of experts,
      "Two models run together, option probabilities averaged 50/50: 57.36B in all, all used on every question." for
      two models run together, `size_sentence`, Ümit #4229; otherwise "Parameters: 26.1B dense", "Parameters: 8B dense ·
      4.5B effective" or "Parameters: not disclosed by maker", `parameters_text`; MoE or dense from the size record,
      `architecture`: MoE where it has active counts or its scope says mixture of experts, dense for a counted released
      checkpoint without them, nothing where neither holds; two models run together where its scope says "two full
      models", `combined`; the same words on the model page; Method's sizes table keeps `parameters_text`), its accuracy
      with the interval, reading and grammar, non-hallucination with "Bilmiyorum", the answers kept at 99% confidence
      (decision models), the cost with its basis and the request size, and "Open its answers →" (its model page), each
      line only where the data has it. The size shows there and on the model page (with what it covers, its
      source and the date read), and in short beside the name. **Controls** (`site.js` `leaderboard`): the part (Ümit
      #4181: Turkish, the default: the 2,198-question ranking, with reading, grammar, non-hallucination with
      "Bilmiyorum" and cost; Turkish reading and Turkish grammar: the same rows ranked on the 656 reading or the 1,542
      grammar questions, with that accuracy and its 95% interval, then the whole Turkish accuracy and the other group;
      English reading: the English setups on the 547 kept reading questions, from `english_reading`, with
      non-hallucination with "I don't know" and cost; Both: Turkish and English accuracy on the same questions, as
      `turkish-vs-english/` computes them, ranked by Turkish), the type (All · Chat models · Decision models, Decision models by default, or
      the group `?models=` names) and All setups, which shows today's full ranking in the table's place; then the Size
      keys on a row of their own (Size: All · Tiny · Small · Medium · Large · Undisclosed, Ümit #4156, combined with the
      type; `page_config.json` `size_classes`, `Site.size_class`: by the smaller of the model's total and active
      parameters as its size record gives them, Tiny below 6B, Small 6B to 15B, Medium above 15B up to 40B, Large above
      40B, Undisclosed when the maker discloses no size; `small_models.left_out_models` in no class, under Size: All
      only; the build stops unless Tiny and Small together hold exactly the small views' setups). The old addresses
      `?models=small-chat` (and `small`) and `?models=small-decision` press Tiny and Small with Chat models or Decision
      models, `small-chat` on the English reading part as before. Each row shows its model's size beside its name, as
      Logic & Math does (`size_label`, the shared form, #4229 and #4231): the total only, whole from 10B up ("26B",
      "266B"), one decimal below ("7.9B", "0.4B"), "2.8T" from 1T up, with a small superscript mark, "MoE" after a
      mixture of experts or "2×" after two models run together, none for a dense model, nothing for an undisclosed
      size; the mark takes the focus and a hover, focus or tap on it opens the row's details box. The # column numbers the rows in view: on the Turkish part their
      tier (a row joins the tier of the tier's top row when they share a tie-group letter of the full ranking's
      all-pairs test, else it starts the next tier; a thin line between tiers), on the other parts, which no all-pairs
      test covers, their rank, ties sharing a rank. Lines of text: what the score means above the table, what # shows,
      the row rule and, while a size is chosen, the size rule under it; the longer notes are on About.
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
      measure's name (`findings_checks` checks every heading against `results.json` on every build). No filter bar and
      no part keys sit on the charts; a filter in the address (`?part=`, `?topic=`, `?size=`, `?web=`, `?setups=`)
      still applies.
    - **Footer**: About · Method · Data · GitHub.
  - **About** (`about/`, `sitebuild/about.py`, built by `build_site.py` after the home page): what the test is (short,
    with the Method page for the full study) with the intro and the counters, How the scores work (`#how-scores`), the
    notes behind the full ranking (the ranks sentence, `RANKS_NOTE`, and the cost notes), the leaderboard rules
    (`leaderboard.about_text`: the row rule, the dated checkpoints, the ranks, the whiskers), Notes on each page
    (`#page-notes`, `about.page_notes`: the longer explanations moved from the top of each page and the home page's
    finding sentences, each page under its own sub-heading and anchor, `#notes-<page>`; a page calls `Site.note` and
    leaves `more_link`, "More about this page", where the text stood), the three result cards (`result_cards`, one set per group,
    the group keys showing the one in view: the highest accuracy, the most answers kept at the 99% confidence threshold
    with no observed mistakes, and the lowest cost per 1,000 questions within 1 point of the best accuracy, or the
    cheapest overall, saying so; `card_checks` tests them on this page), the summary (`about.SUMMARY`; `summary_checks`
    and `copy_checks` test it) and the links to Method and Data.
  - **Experiments** (`experiments/`, `sitebuild/experiments.py`): one card each for Page images, Hallucination
    ("Bilmiyorum"), Web grounding, PWS-Decisions and the Artificial Analysis comparison, each with one line on what it
    measures and a status from the data (setups done, not run or still running, and PWS-Decisions' setups waiting
    for an API key or credit).
  - **Highlights** (`highlights/`, `sitebuild/highlights.py`): five short cards, one finding each (GLiDE 27B (open)
    against the earlier GLiDE rows, the Vision tab's averages, holding back with "Bilmiyorum", Turkish against English,
    the best small open model in English), every number computed from `results.json` and `vision.json` at build time;
    each card's heading is a claim the build checks (`finding`), stopping when the data no longer supports it.
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
    `sitebuild/site.py` and `costMissing` in `v3.js`, on every page; Not measured for any other value nobody measured). A run's variant (its
    route or access note) shows beside its name only where it tells it apart from another setup of the same model ID
    (`shownVariant` in `v3.js`); otherwise it is on the model page only. Non-hallucination
    (`non_hallucination` in `build_site.py`, static HTML, one copy per group; the same two sides on the Hallucination tab,
    and on english/ with confidence Not measured in English and the Turkish reference apart, `sitebuild/holding_back.py`;
    on the Hallucination tab its other charts and its table also show Decision models and Chat models as separate
    blocks, the paired test being decision models only) shows two kinds of holding back side by side, each with Decision
    models and Chat models as separate blocks with their own heading and ranking (both under All models, never one mixed
    list): Holding back by confidence, each setup's Text tab run at the 99% threshold (`runs[].confidence.sure`: the
    answers kept, the bar their share of the questions, the wrong ones among them, and the ranking score
    `confidence.auroc`; no wrong answer first by answers kept, then by the share wrong; each block names its kind of
    confidence, a setup without one reads No confidence reported), and Holding back with a "Bilmiyorum" option, the
    Hallucination tab's rows of that group (`results.json`'s `dont_know`) in its order, the rate with "Bilmiyorum", then
    in columns of their own the share answered (the attempt rate, as that tab writes it) and the error rate among the
    answers (wrong / answered), bars in family colours; under the decision block the decision models that chose the
    option on fewer than `dont_know.vs_confidence_share` of the questions, with how often each did (`rare_note`), under the
    chat block the chat setups whose Turkish run is still running with their reason, a link to that tab).
    Cost; Latency; Reading vs grammar;
    accuracy against cost or latency (under All setups), with the Pareto line (the setups in view no other setup in view
    beats on both) and, shaded, the region better than the median setup in view on both; Calibration (the calibration
    gap, as shipped, on all questions). The charts draw every setup of the model group `?models=`
    names (every setup together by default, the decision models or the chat and general models), within the filters;
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
    group, whatever the filters: cheapest
    first (setups without a cost last, by accuracy), with $ per 1,000 questions as the Cost card writes it, its cost over
    the cheapest setup's (× cheapest, empty where the cost is not measured), accuracy, median latency, the answers kept at
    the 99% cutoff (right of kept, and the questions skipped: the scored total minus the kept, that is the answers below
    99% confidence plus any invalid answers, which the cell counts where there are some), the non-hallucination rate
    with its attempt rate where the Hallucination tab has the model (Not run otherwise), and a Pareto tag for the setups
    the trade-off chart's rule puts on its dotted line among all setups with a cost. No score combines these columns.
    Kept and skipped counts stand beside the cutoff figures: the full ranking's Confidence tab; the Routing tab wherever
    `results.json` stores whole counts (the fixed 99% rule and the most confident quarter in the replay and in the live
    tests, the half rule in the live tests; the half rule's replay figures are means over 300 splits, so they stay
    shares); the model pages; the Method page; and the Hallucination tab's derived cut-off (answered and held back).
    The full ranking (All setups) has four tabs: one table for the group in view, ranked by
    accuracy (in the all view decision and chat models together, each row saying which); the Routing tab opens by the
    share taken and the Stability tab by changed answers, most first, ties by the same wrong answer in all five runs,
    most first (`DEFAULT_SORTS` and a column's `tie` in `v3.js`). A model ID with runs in both groups
    gets its route after its name in each row ("GPT-6 Luna (Decisions API)", "GPT-6 Luna (chat API)"; `route_labels`
    in `sitebuild/site.py`). The full ranking's rows carry no notes: a setup's notes are on its model page (How we
    called it), which its name links to. The Reading vs grammar chart lists the setups in the full ranking's order.
    `v3.js` draws the charts and the four tabs of the full ranking in the
    browser from two compact files that `build_site.py` writes from `results.json` (`home_data`), which stays the
    published download: `data/home.json`, preloaded by the page, holds what the first draw reads (the runs, each
    run's confidence cut to the counts at the sure cutoff that the Cost table shows, and the units, prices, routing
    replays and live tests, repeats and Hallucination models), and `data/home-more.json` the runs' whole confidence
    and the cascades without their curves, which `v3.js` loads when the Calibration chart comes within a screen of
    the view or the Confidence or Routing tab opens; until a chart is drawn its box reads Loading charts…. Accuracy
    for a part or topic and its Wilson 95% interval come from the counts there. The filters and the Routing tab's four
    choices are kept in the URL (`?part=reading&topic=3&size=16&web=with&setups=145,199`), so a reload, Back or a
    shared link (Share view copies it) opens the same view.
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
  - **Page images** (`vision/`, `sitebuild/vision.py`): the 763 questions with
    underlined or numbered words, asked as text (A), as a page image (B), as both (C) and through four OCR
    models (D). Decision models and other models in separate tables; in each, the image models ranked by B,
    then the text-only models ranked by their best OCR route. A condition `vision.json` does not hold reads
    "Not available" with its reason, and a row without the result it is ranked by follows the ranked rows.
    Below: the models not run, with their reasons, and the OCR models' error rates and kept underlined and
    numbered words on the human-verified question text. A setup that is condition A there shows its row on
    its own page. Every model there is a decision model (the build stops otherwise): the models' charts, tables and
    findings carry `data-models="all decision"` and the chat view shows a note in their place; the OCR models' parts
    show in every view. Hallucination and Web grounding do the same for their parts.
  - **Other pages**: each module of `sitebuild/` (`PAGE_MODULES` in `build_site.py`) returns whole pages,
    written to `<path>index.html`: one page per setup (`models/<run>/`, opening with a summary: accuracy with its 95%
    interval, the answers kept at 99% confidence with the wrong ones among them, cost and median latency; the run
    record's harness seed, commit and prompt version folded under Settings; for a setup with an English run, an English
    section (`#english`): the first English run's right answers of the 547 kept questions, accuracy with its range over
    several runs, the English "I don't know" non-hallucination rate where measured, the first English run's cost and
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
    (picture alone), non-hallucination and attempt rates, cost per 1,000 and per 1M questions and the median latency per
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
and the hosted GLiDE rerun (`rerun_runs`), and the web grounding test's own runs (`web_grounding_runs`), with scores
and option probabilities at full precision; no run is in two lists. The sections of `ANSWER_FILES` go to files of
their own beside `answers.json` (`answers-repeats.json`: `repeat_runs`, the largest section), so that no file nears
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
and drive the details box, the model pages, Method's size table and the small views. Prices live in `PRICES` in `runner/benchmark_ollama.py`:
the export takes each run's price from the report, and stops when a paid or free-tier run has none or a
price applies to another kind of run: a self-hosted run may only take its maker's list price for the same
model (our hardware cost is not measured), and a free-tier run the list price of the model it called.
