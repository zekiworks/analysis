# What Does a Correct Answer Tell Us About Understanding?

*Accuracy, confidence and cost across reading and grammar tasks in Turkish.*

The results page of a benchmark of language models and decision models on 2,198 scored
multiple-choice questions from a TYT Türkçe question bank: how accuracy holds on reading and breaks on
grammar, whether a model's confidence points at its mistakes, what a right answer costs, and what
routing questions from a cheap model to an expensive one saves.

The site is the `docs/` folder, served by GitHub Pages from the `main` branch. It is static. The page
opens with an overview for readers who build, choose or review AI tools (confidence, accuracy, answer
stability and cost), followed by the full study. `build_page.py` writes the overview's numbers, tables
and bars into `docs/index.html` from `docs/results.json`, the aggregate results, so they read without
JavaScript; `docs/app.js` renders the full study's tables from the same file. `docs/answers.json`
holds every answer of every main, repeat and routing run, with its full-precision score and option
probabilities but without the questions' text. `benchmark_metrics.py` is the benchmark's metric code,
and `runner/` the code that ran the benchmark.

## From a clean copy

None of these commands needs a private file:

```bash
python3 reproduce.py                                       # recompute the published numbers
cargo run --release --manifest-path charts/Cargo.toml -- docs/results.json docs/charts   # the graphs
cargo test --manifest-path charts/Cargo.toml               # compare each graph with its snapshot
python3 build_page.py                                      # the overview, the sharing images, the X posts
python3 -m http.server 8000 --directory docs               # preview at http://127.0.0.1:8000/
```

- **`reproduce.py`** (Python 3.10 or newer, standard library and `benchmark_metrics.py`) recomputes,
  from `docs/answers.json`, each main run's correct answers on the scored questions (the 12 the key
  audit excluded are skipped), AUROC, expected calibration error and the answers scored 0.99 or more,
  before and after the key audit; the leaderboard's tied groups (every pair of runs, exact McNemar,
  Holm over all pairs, alpha 0.05); the listed paired comparisons (exact McNemar, Holm over the
  listed pairs); and the costs: each priced run's from its token counts at the rates in
  `docs/results.json`'s `prices`, every run without a price shown as a free tier or self-hosted, each
  routing simulation's cost per 1,000 questions from its runs, and the routing tests' costs from their
  parts. It prints one row per run and exits with status 1 when a value differs from
  `docs/results.json`: counts and group letters must match exactly, AUROC and ECE within 10⁻⁹,
  p-values and costs within a relative 10⁻⁹. The bootstrap intervals, the routing simulations'
  accuracy, the repeats and the other tables are not recomputed.
- **The graphs** are drawn by `charts/`, a Rust crate, from `docs/results.json` (see below).
- **The page build** `build_page.py` runs `reproduce.py` first and stops unless every check matches.
  It fills the page's `<span data-value="…">` elements and `<!-- build:… -->` blocks from
  `docs/results.json`, with the constants in `page_config.json`: the 0.99 threshold, the configurations
  each overview figure shows, display precision and image sizes. Each section orders its rows by its own
  measure: confidence rows by answers accepted (the two preview rows first), task rows by overall accuracy
  (the reference row last), stability rows by changed answers. It draws the sharing images with
  headless Chrome from the same rows (`docs/share/`, named with the results version) and writes the
  announcement text to `share/x-posts.md`; `--no-images` skips Chrome, and `CHROME` names another
  Chrome or Chromium binary. The dataset version, the results version (a hash of `results.json`) and
  the publication date in `page_config.json` are shown separately.
- **The preview** needs a server: opening `docs/index.html` from disk does not work, because browsers
  block loading `results.json` from a `file://` page.

## Running the benchmark

`runner/` holds the runner, the run script of every published configuration, and the scripts that
built the question bank. [`runner/README.md`](runner/README.md) gives the setup, the question-bank
format, how someone who owns the book rebuilds the bank, and how to run each family of
configurations: hosted APIs, subscription command-line tools, vLLM and SGLang servers and self-hosted
decision servers. The questions themselves cannot be shared.

## Graphs

`charts/` draws the page's graphs from `docs/results.json`. It uses ratatui's `Chart`, `BarChart` and
`Canvas` widgets, rendered into ratatui's test backend, so each graph is a buffer of terminal cells.
The page shows them as SVGs next to their tables in `docs/charts/`.

- **SVG output:** a small writer (`charts/src/svg.rs`) turns each buffer into an SVG on a fixed grid of
  8 × 16 px cells. It draws braille dots, box lines, bar blocks and dots as shapes, so a graph looks
  the same whatever fonts the reader has.
- **Snapshots:** the same buffer, as text, is the graph's insta snapshot in `charts/tests/snapshots/`.
  When the data changes, the snapshot diff shows how each graph changed.

```bash
INSTA_UPDATE=always cargo test --manifest-path charts/Cargo.toml   # accept the new graphs
```

`cargo insta review` (from `cargo install cargo-insta`) shows the changed snapshots one by one instead.

## Updating the results (maintainer)

This needs the benchmark's private files: the report the benchmark script writes
(`benchmark-results.md`) and the per-question export from its answer store.

`export_results.py` rebuilds `docs/results.json` from the report. Its leaderboard holds the runs over
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
- the run-to-run variation of repeated runs.

With `--answers`, it also writes `docs/answers.json` from the benchmark's per-question export: the
main runs, the repeats of each repeated configuration (`repeat_runs`) and the two runs of each measured
routing pipeline (`pipeline_runs`), with scores and option probabilities at full precision. Then
refresh `runner/` and the metric code, and check the result:

```bash
./benchmark_ollama.py --export-answers /tmp/benchmark-answers.json   # in the benchmark folder
./export_results.py /path/to/benchmark-results.md --answers /tmp/benchmark-answers.json
./sync_runner.sh /path/to/benchmark-folder   # runner/ and benchmark_metrics.py
python3 reproduce.py
cargo run --release --manifest-path charts/Cargo.toml -- docs/results.json docs/charts
python3 build_page.py   # set "published" in page_config.json first
grep -r -I -E '/(home|Volumes)|T[7]' README.md reproduce.py build_page.py sync_runner.sh export_results.py runner docs charts/src charts/tests share

The last command must find nothing; its pattern is written so that it does not match itself.
`sync_runner.sh` refuses to copy a file that contains a local path; it copies every `run_*.sh` script
except those listed in it as behind no published run, and prints the list.

A new provider needs an entry in `PROVIDERS` (its access route and how it is paid for); the script
stops until it has one. A new model is shown by its ID unless `MODELS` gives it a display name, and a
model on our GPUs needs its hardware there. Prices live in `PRICES` in `runner/benchmark_ollama.py`:
the export takes each run's price from the report, and stops when a paid run has none or a free or
self-hosted run has one.
