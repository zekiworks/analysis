# When should you trust an AI model to make a decision?

*A decision model answers first; a stronger model answers the rest. Accuracy, confidence and cost on
Turkish exam questions.*

The results page of a benchmark of language models and decision models on 2,198 scored
multiple-choice questions from a question bank for the Turkish section of the TYT, the first stage of
Turkey's university entrance exam. It opens with 18 decision models and the share of the questions each
took off three LLMs (Claude Sonnet 5.5, Claude Opus 5.5, GPT-6 Astra) when we kept its answer only when it
was confident, from a replay of recorded answers. It then explains confidence and the two-step setup, why
Perplexity's Decider v1.1, speed, the cutoff and the savings; what a fixed confidence cutoff keeps, how
accuracy holds on reading and falls on grammar, whether answers repeat, what each model costs and how long
it takes; and the full study.

Page: <https://zekiworks.github.io/analysis/decision-models/>

The site is this folder, served by GitHub Pages from the `main` branch. It is static. The page opens
with the comparison of decision models in front of three LLMs and the sections that explain it
(confidence, the two-step setup, why Decider, speed, the cutoff, the savings), then an overview (fixed
cutoff, accuracy, repeated answers, live tests, cost and time, trying it on your own task), then the full
study. `build_page.py` writes every number, the overview's
tables and bars, the chart figures and their descriptions into `index.html` from `results.json`, the
aggregate results, so they read without JavaScript; `app.js` renders the full study's tables from the
same file. `answers.json` holds every answer of every main, repeat and routing run, with its
full-precision score and option probabilities but without the questions' text. `benchmark_metrics.py`
is the benchmark's metric code, and `runner/` the code that ran the benchmark. The page used to live at
`/analysis/turkce-benchmark/docs/`; a redirect page there sends readers here.

## Contributing and citing

`CONTRIBUTING.md` says how to report a wrong answer key, ask us to test a model or send a dataset.
`key-changelog.md` lists every change to the answer key, and `results.json` names the key version every run is
scored on (`answer_key`). `CITATION.cff`, which `build_page.py` writes, gives the results version and the key
version to cite.

## From a clean copy

None of these commands needs a private file:

```bash
python3 reproduce.py                                       # recompute the published numbers
cargo run --release --manifest-path chart-renderer/Cargo.toml -- results.json charts   # the graphs
cargo test --manifest-path chart-renderer/Cargo.toml       # compare each graph with its snapshot
python3 build_page.py                                      # the overview, the sharing images, the X posts
python3 -m http.server 8000                                # preview at http://127.0.0.1:8000/
```

- **`reproduce.py`** (Python 3.10 or newer, standard library and `benchmark_metrics.py`) recomputes,
  from `answers.json`, each main run's correct answers on the scored questions (the 12 the key
  audit excluded are skipped), AUROC, expected calibration error and the answers scored 0.99 or more,
  before and after the key audit; the leaderboard's comparison groups (every pair of runs, exact
  McNemar, Holm over all pairs, alpha 0.05), including that two runs share a letter exactly when that
  test does not tell them apart; the listed paired comparisons (exact McNemar, Holm over the listed
  pairs and over all pairs); each format rerun against its setup's first run on the same questions (exact
  McNemar, Holm over these comparisons); each reasoning pair's gains on reading and on grammar and the
  bootstrap interval of their difference, with the seed and resamples in `results.json`'s `reasoning`;
  each repeated configuration's answer stability statistics, from its runs'
  answers; every routing simulation (the cutoff chosen in sample and its 300 held-out splits); the
  replay the page leads with (Decider v1.1's answers kept at each cutoff and in its most confident quarter, and
  what keeping them changes in front of each second model, on all questions and on the same splits);
  the answer-key baselines; every live test (the questions the first model kept, against its cutoff,
  the pair's and the second model's accuracy, the paired change with its 95% interval and exact McNemar
  p and, with one question per request, each question's wait); and the costs: each priced run's from its
  token counts at the rates in `results.json`'s `prices`, every run without a price shown as a free tier
  or self-hosted, each routing simulation's and replay's cost per 1,000 questions from its runs, and the
  routing tests' costs from their parts. It prints one row per run and exits with status 1 when a value
  differs from
  `results.json`: counts and group letters must match exactly, AUROC, ECE, shares and accuracies within
  10⁻⁹, p-values and costs within a relative 10⁻⁹. The bootstrap intervals of AUROC and of the kept
  answers' accuracy, and the other tables, are not recomputed.
- **The graphs** are drawn by `chart-renderer/`, a Rust crate, from `results.json` (see below).
- **The page build** `build_page.py` runs `reproduce.py` first and stops unless every check matches.
  It fills the page's `<span data-value="…">` elements and `<!-- build:… -->` blocks from
  `results.json`, with the constants in `page_config.json`: the 99% cutoff, the configurations each
  overview figure shows, the runs the copy names, display precision and image sizes. It also gives each
  chart `<img>` the width and height of its SVG, so the page keeps its layout while the charts load.
  - **`lead`** names the confidence rows the 99% figure starts with, one of `leads`; the 99% share image
    and its X post show them.
  - **Row order:** the confidence figure puts the lead rows first and the other rows in the order of
    `confidence_rows`; each entry of `leads` gives its rows and the sentence that tells readers the order
    is editorial, not a ranking. Task rows go by overall accuracy, decision models before the chat models
    shown for comparison; stability rows by changed answers.
  - **Images:** drawn with headless Chrome from the same rows, in both themes (`share/`, named with the
    theme and a short hash of the file, for example `preview-dark-1a2b3c4d.png`, so that a changed image
    gets a new address and no link preview shows a cached copy). The link preview is the cutoff chart.
    The dark images, on the page background, are the main ones: the link preview and the X posts use
    them, and "Share or download this chart" downloads the version that matches the theme being viewed.
    With `--no-images` the page keeps the images it links to. Earlier images are deleted until
    `announced` holds the date of the first public post; from then on they are kept, so posted link
    previews keep working.
  - **Generated sentences:** every sentence that compares models or states a trend (the opening, the
    savings, the fixed cutoff, accuracy, repeated answers, the live tests, cost and time, and the study's
    findings) checks that its wording still fits the numbers and stops the build otherwise. A
    configuration's time per request is its own run's, or, when that run predates per-request timing, the
    pooled times of its later runs of the same setup (`latency` in `results.json`); a batch's time is never
    divided among its questions. Numbers recorded outside the published data (the question repairs, the
    exam and copy checks, the key review, a recalibration experiment) are in `page_config.json`'s
    `method_records`, each with its source.
  - **X posts:** the announcement text goes to `share/x-posts.md`; `--no-images` skips Chrome, and
    `CHROME` names another Chrome or Chromium binary.
- **Themes:** the page is dark by default, also without JavaScript; `style.css` keeps both palettes, and
  a reader's Dark background / Light background choice is stored in `localStorage` and applied by a
  line in `<head>` before the page renders. Printing always uses the light theme, so the light charts
  load with the page.

  The question set version, the results snapshot (a hash of `results.json`), the first publication date
  in `page_config.json` and the results update date are shown separately.
- **The preview** needs a server: opening `index.html` from disk does not work, because browsers
  block loading `results.json` from a `file://` page.
- **The v2 site preview** (`v2/`, at `/analysis/decision-models/v2/`): `python3 build_v2.py` builds it from
  `results.json`, `answers.json` and `page_config.json`.
  - **Home page** (`v2/index.html`): the script fills its `<!-- build:… -->` blocks (the meta tags, the stats
    row, the leaderboard as a plain table for readers without JavaScript, the settings `v2/v2.js` reads).
    `v2/v2.js` draws the filters, the four leaderboard tabs and the two charts in the browser from
    `results.json` alone; accuracy for a part or topic and its Wilson 95% interval come from the counts
    there. The Routing tab keeps its four choices in the URL. The page's fixed copy quotes numbers; the
    script checks each against `results.json`, prints every claim that differs and then exits with status 1,
    after writing the pages.
  - **Other pages**: each module of `v2build/` (`PAGE_MODULES` in `build_v2.py`) returns whole pages,
    written to `v2/<path>index.html`: one page per setup (`models/<run>/`), every question, one page per
    question (`question/?id=…`, drawn by `v2/question.js`), where models disagree with the key, topics with
    the accuracy-by-topic heat map and one page per topic, Compare (`v2/compare.js`, exact McNemar test as
    in `benchmark_metrics.py`), Method and Data. `v2build/site.py` holds the shared page shell.
  - **`v2/data/picks.json`**: each leaderboard setup's pick and score on each scored question, written from
    `answers.json` by `v2build/questions.py`, which checks every pick against its grade. Scores are floored
    to four decimals, so a score below the 99% cutoff never reads as 99.00%.

## Running the benchmark

`runner/` holds the runner, the run script of every published configuration, and the scripts that
built the question bank. [`runner/README.md`](runner/README.md) gives the setup, the question-bank
format, how someone who owns the book rebuilds the bank, and how to run each family of
configurations: hosted APIs, subscription command-line tools, vLLM and SGLang servers and self-hosted
decision servers. The questions themselves cannot be shared.

## Graphs

`chart-renderer/` draws the page's graphs from `results.json`. It uses ratatui's `Chart`, `BarChart`
and `Canvas` widgets, rendered into ratatui's test backend, so each graph is a buffer of terminal cells.
The page shows them as SVGs next to their tables, from `charts/`: `<name>.svg` in the light theme and
`<name>-dark.svg` in the dark one, written from the same buffer.

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

`--answers` names the benchmark's per-question export. The export takes from it the replay the page
leads with (`replay`), each listed comparison's Holm p-value over all pairs (`p_holm_all`) and the
answer-key baselines (`baselines`), and writes `answers.json`: the main runs, the repeats of each
repeated configuration (`repeat_runs`) and the runs of each measured live test (`pipeline_runs`; a run
that serves several tests, such as a second model alone on the shared test half, lists every role it
has), with scores and option probabilities at full precision. Then refresh `runner/` and
the metric code, and check the result:

```bash
./benchmark_ollama.py --export-answers /tmp/benchmark-answers.json   # in the benchmark folder
./export_results.py /path/to/benchmark-results.md --answers /tmp/benchmark-answers.json
./sync_runner.sh /path/to/benchmark-folder   # runner/ and benchmark_metrics.py
python3 reproduce.py
cargo run --release --manifest-path chart-renderer/Cargo.toml -- results.json charts
python3 build_page.py   # set "published" in page_config.json first
grep -r -I -E '/(home|Volumes)|T[7]' --exclude-dir=.git --exclude-dir=target .

The last command must find nothing; its pattern is written so that it does not match itself.
`sync_runner.sh` refuses to copy a file that contains a local path; it copies every `run_*.sh` script
except those listed in it as behind no published run, and prints the list.

A new provider needs an entry in `PROVIDERS` (its access route and how it is paid for); the script
stops until it has one. A new model is shown by its ID unless `MODELS` gives it a display name, and a
model on our GPUs needs its hardware there. Prices live in `PRICES` in `runner/benchmark_ollama.py`:
the export takes each run's price from the report, and stops when a paid run has none or a free or
self-hosted run has one.
