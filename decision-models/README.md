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
and `answers.json`, which holds every answer of every main, repeat and routing run, with its
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
  answers, accuracy, median and 95th-percentile request time and cost (overall and, in Turkish, by group), the exact
  McNemar test of each pair, the "Bilmiyorum" pair's counts and rates and the right answers among each source check's
  questions, and checks the tokens, sources and PWS-Decisions' aggregates against `web-grounding.json`.
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
  - **Run types:** a run is a decision model when its provider is one of `page_config.json`'s
    `decision_model_providers` and its model not one of `not_decision_models`. The tables, `v3.js`'s charts
    and the graphs read these two lists. The build stops when the graphs give a run another type than the
    tables (`chart-renderer`'s `--types` output against the build's own), and when a provider that serves
    both decision and chat models (`mixed_providers`: OpenRouter) has a run of a model not listed under it,
    so that its type is decided first.
  - **Link preview:** every decision model's accuracy with its 95% interval, all drawn alike, with the
    results version, the answer key version and the page address in its footer. Drawn with headless
    Chrome in both themes (`share/`, named with the theme and a short hash of the file, for example
    `preview-dark-1a2b3c4d.png`, so that a changed image gets a new address and no link preview shows a
    cached copy); the dark one is the link preview. `share/images.json` names the current images; the home
    page's link preview reads it, and with `--no-images` the build keeps them. Earlier images are deleted
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
  - **View bar** (`topbar` in `sitebuild/site.py`, first on every page and sticky at the top): row 1 the test (English
    reading, `english/`; Turkish reading and grammar, the home page; English and Turkish, `turkish-vs-english/`), row 2
    the models (`?models=all|decision|chat`, all when missing; trailing dots, punctuation or spaces are dropped, so
    `?models=all.` reads as all), row 3 the measure (Accuracy, Non-hallucination, Cost,
    Latency). Each row 1 or row 2 choice opens its page at the top, charts first, then the table. `site.js` marks the
    current group, keeps it in row 1's links and in the top bar's Page images and Hallucination links, and shows each
    `data-models` element only for its groups; on any other
    page row 2 leads to the home page with that group. On the three test pages row 3 links to the page's parts
    `#accuracy`, `#non-hallucination`, `#cost` and `#latency` (the query, so the group, stays), each landing below the
    bar (`--view-bar-h`), and `site.js` marks the key of the part in view (or the one just pressed); on any other page
    row 3 opens that part of the home page with the group in view. The All models view always ranks decision and chat
    models together in one chart and one table per measure. The two English pages render, in
    static HTML, one copy per group of every part that depends on the setups shown (`data-models="all"`, shown without
    JavaScript; `decision` and `chat` hidden), with its counts and sentences computed for that group and its setups
    ranked by English accuracy within it; the parts about decision models only appear once
    (`data-models="all decision"`) with a note that chat models are not measured yet, as no chat model was asked with
    an "I don't know" option. A setup that shares its name with another English setup is labelled with the settings
    that tell them apart, as the home page's charts do ("Gemini 3.8 Flash (low reasoning, 16/request)"). English reading
    (`sitebuild/english_view.py`) shows every English setup on the 547 kept reading questions: accuracy per group, the
    decision models' non-hallucination with "I don't know" in English, cost per 1,000 questions and median latency per
    request of each first English run per group (`english_reading.models[].cost.english` and `.latency.english`, log
    scale, Not measured named in the note; `measure_card` in `sitebuild/english_reading.py`), then the table per group
    ranked by English accuracy with the four measures. Turkish vs English draws the same Cost and Latency cards as
    paired bars, the Text tab run (`.turkish`) and the first English run (`.english`), with both in its main table.
  - **Four tabs**: the site's four benchmarks, each with its own address and its own rankings, never combined: Text
    (the home page, 2,198 questions), Page images (`vision/`, from `vision.json`), Hallucination
    (`dont-know/`, from `results.json`'s `dont_know`, `dont_know_option_word`, `hosted_glide_rerun` and
    `english_reading.dont_know` and `page_config.json`'s `dont_know`, built by `sitebuild/dont_know.py`) and Turkish vs
    English (`turkish-vs-english/`, from `results.json`'s `english_reading`,
    `dont_know_option_word`, `english-reading.json` and `page_config.json`'s `english_reading` and `model_languages`,
    built by `sitebuild/english_reading.py`; its former address `english-reading/` redirects there, fragment kept). The
    top bar under the view bar (`topbar` in `sitebuild/site.py`) is one line where it fits: the brand, the navigation
    bar (Page images and Hallucination first, then Every question, Where models disagree, Topics, Compare, Method, Data;
    the current page underlined) and the theme switch. Text is the home page (the brand and row 1); Turkish vs English
    is row 1's English and Turkish. Each tab's face
    is charts, each card with a line saying which way is better; its tables and notes are under Info (except the Text
    tab's leaderboard, which follows its charts), a details element
    closed by default that `site.js` opens for a link into it (`dont-know/#method`). The Page images, Hallucination and
    Turkish vs English faces are HTML bars (`hbars` in `sitebuild/site.py`: one series coloured by the ranking scale; the
    Turkish vs English pairs, as English reading's bars, in each model family's colour, the English bar striped), so they need
    no script: Page images shows the picture alone against the text, the text plus the picture, the best OCR route and the
    marks each OCR model kept; Hallucination shows the non-hallucination rate, that rate against the same model held back
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
    Turkish vs English opens with its charts, accuracy in Turkish and in English with the paired test of the two (the
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
    comparing the Text tab's two hosted setups, linked from the home page's hero (the `experiments` block) and from the
    model pages of the Perplexity family. Perplexity's Decider v1.2 through its Decisions API off ("Perplexity Decider
    27B v1.2 (API)", run 633) and with web ("... (with web)", run 640) on the full bank, reading and grammar apart; the
    200-question pilot that came first (`--sample 200 --seed 0`, runs 631 and 632); the "Bilmiyorum" pairs (full bank,
    and the pilot's 634, 635); our English translations of the kept reading questions (637 and 639) and PWS-Decisions'
    100 public questions (Parallel's gated dataset: its aggregates only). Four paired charts (accuracy; non-hallucination;
    median latency; cost per 1M questions, log scale, ≤ on the costs with web), what the search returned (pages and top
    sites of each grounded run, the literal-match and source checks), the caveats, and under Info the tables and our
    method. Costs with web are upper-bound estimates (`cost_upper_bound`): every cost of such a run, on every page,
    carries `page_config.json`'s `first_cost_marks.upper` mark (≤) and its note.
  - **Home page** (`index.html`, the Text tab): the script fills its `<!-- build:… -->` blocks (the meta tags,
    with the link preview from `share/images.json`, the stats row, the leaderboard as plain tables for
    readers without JavaScript, the settings `v3.js` reads, and the static Non-hallucination part). Its face starts under
    the one-line top bar with `#accuracy`, whose head holds the Filters bar (the panel opens under the head), so the
    Accuracy chart is on the first screen (its top at 206 px at 1280 x 800, 241 px at 390 x 844); the title, the intro and the language
    of the questions follow it. The parts follow row 3 of the view bar: `#accuracy`, `#non-hallucination`, `#cost` and
    `#latency`, then the rest (no list of links to the parts: row 3 is that list); each chart card has a line saying
    which way is better, and each bar chart names its value columns above them (`COLUMN_HEADS` in `v3.js`; the static
    charts through `hbars`' head, as "Non-hallucination · Answered"): Accuracy, with each setup's cost and median
    latency beside its accuracy as the Cost and Latency cards write them ($ per 1,000 questions, § at the maker's list
    price, ≤ before an upper-bound estimate; seconds, * for a latency measured on a sample; No list price for a cost of a
    setup on our own hardware whose maker lists no price for the same model, `cost_missing` in `sitebuild/site.py` and
    `costMissing` in `v3.js`, on every page; Not measured for any other value nobody measured). A run's variant (its
    route or access note) shows beside its name only where it tells it apart from another setup of the same model ID
    (`shownVariant` in `v3.js`, `shown_variant` in `build_site.py`); otherwise it is on the model page only. Non-hallucination
    (`non_hallucination` in `build_site.py`, static HTML from `results.json`'s `dont_know`: the Hallucination tab's
    decision models in its order, the rate with "Bilmiyorum" and the attempt rate as that tab writes them, bars in family
    colours, a note that chat models are not measured yet, a link to that tab; one heading, with a note instead of the
    bars in the chat view); Cost, its chart then the table of every setup in one part; Latency;
    accuracy against cost or latency, with the Pareto line (the setups in view no other setup in view
    beats on both) and, shaded, the region better than the median setup in view on both; Calibration (the calibration
    gap, as shipped, on all questions). The charts draw every setup of the model group the view bar
    selects (every setup together, the decision models or the chat and general models), within the filters;
    each bar or dot takes its model family's colour (`page_config.json` `model_families`: a maker's line of models shares
    one colour, in every chart and both groups; `run_families` in `sitebuild/site.py` stops the build unless every run
    has exactly one family), with the families in view in the legend.
    Under the Cost chart, in the same part, the table of every setup (`#cost-table`, `costTable` in `v3.js`) holds every setup of that
    group, whatever the filters and the model selection: cheapest
    first (setups without a cost last, by accuracy), with $ per 1,000 questions as the Cost card writes it, its cost over
    the cheapest setup's (× cheapest, empty where the cost is not measured), accuracy, median latency, the answers kept at
    the 99% cutoff (right of kept, and the questions skipped: the scored total minus the kept, that is the answers below
    99% confidence plus any invalid answers, which the cell counts where there are some), the non-hallucination rate
    with its attempt rate where the Hallucination tab has the model (Not run otherwise), and a Pareto tag for the setups
    the trade-off chart's rule puts on its dotted line among all setups with a cost. No score combines these columns.
    Kept and skipped counts stand beside the cutoff figures: the leaderboard's Confidence tab; the Routing tab wherever
    `results.json` stores whole counts (the fixed 99% rule and the most confident quarter in the replay and in the live
    tests, the half rule in the live tests; the half rule's replay figures are means over 300 splits, so they stay
    shares); the model pages; the Method page; and the Hallucination tab's derived cut-off (answered and held back).
    Right after the charts comes the leaderboard with its four tabs: one table for the selected group, ranked by
    accuracy (in the all view decision and chat models together, each row saying which). Info, a details element closed
    by default and opened by a link into it (`#info`), holds the counters, the summary, the notes and the Reading vs
    grammar chart. A model ID with runs in both groups
    gets its route after its name in each row ("GPT-6 Luna (Decisions API)", "GPT-6 Luna (chat API)"; `route_labels`
    in `sitebuild/site.py`). The leaderboard rows carry no notes: a setup's notes are on its model page (How we
    called it), which its name links to. The Reading vs grammar chart lists the setups in the leaderboard's order.
    `v3.js` draws the filters, the charts and the four leaderboard tabs in the
    browser from two compact files that `build_site.py` writes from `results.json` (`home_data`), which stays the
    published download: `data/home.json`, preloaded by the page, holds what the first draw reads (the runs, each
    run's confidence cut to the counts at the sure cutoff that the Cost table shows, and the units, prices, routing
    replays and live tests, repeats and Hallucination models), and `data/home-more.json` the runs' whole confidence
    and the cascades without their curves, which `v3.js` loads when the Calibration chart comes within a screen of
    the view or the Confidence or Routing tab opens; until a chart is drawn its box reads Loading charts…. Accuracy
    for a part or topic and its Wilson 95% interval come from the counts there. The Routing tab keeps its four
    choices in the URL. The page's fixed copy quotes numbers; the
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
    its own page.
  - **Other pages**: each module of `sitebuild/` (`PAGE_MODULES` in `build_site.py`) returns whole pages,
    written to `<path>index.html`: one page per setup (`models/<run>/`; `models/` itself sends the reader to the home
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
    (`vision/`), Method (`method/`) and Data (`data/`). `sitebuild/site.py` holds the shared page shell.
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
(OpenAI), Claude, Qwen, DeepSeek, Kimi, Perplexity and Microsoft, drawn in the text colour. A family without a freely
licensed mark (Grok: Simple Icons has no xAI mark) gets its first letter on its own colour. `family_sprite` in
`sitebuild/site.py` puts every icon as an SVG symbol once on each page.

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
and option probabilities at full precision; no run is in two lists. The English reading section needs
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
model on our GPUs needs its hardware there. Prices live in `PRICES` in `runner/benchmark_ollama.py`:
the export takes each run's price from the report, and stops when a paid or free-tier run has none or a
price applies to another kind of run: a self-hosted run may only take its maker's list price for the same
model (our hardware cost is not measured), and a free-tier run the list price of the model it called.
