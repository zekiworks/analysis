# Understanding Under Thin Training: A Turkish Exam Benchmark

Results page for language models on 2,198 multiple-choice questions from a TYT Türkçe question bank, in
its second version with the lost markup repaired: scores, accuracy by unit, confidence with bootstrap
intervals, the effect of the repair, paired comparisons, decision models as a first pass for frontier
models, speed, output tokens, cost and hardware.

The site is the `docs/` folder, served by GitHub Pages from the `main` branch. It is static:
`docs/app.js` renders the tables from `docs/results.json`. `docs/answers.json` holds every run's
answer to every question without the questions' text, and `benchmark_metrics.py` is a copy of the
benchmark's metric code, so the tables can be rebuilt from the published data.

## Updating the results

`export_results.py` rebuilds `docs/results.json` from the report the benchmark script writes
(`benchmark-results.md`). Its leaderboard holds the runs over a full question set that are graded
against the same question bank as the newest such run, whichever version of the bank they ran on. It
leaves out repeats, runs on listed questions and runs whose correct option was replaced (a memorization
test, not an accuracy run), and exports only aggregate numbers: no question text, prompts, answers or
local paths. The comparisons between runs come from the report's `benchmark-analysis` record:

- paired tests with Holm-adjusted p-values;
- cascades simulated and run as pipelines;
- decision-model doubt;
- confidence sources scored on the same answers;
- each run's change from the previous question bank;
- the run-to-run variation of repeated runs.

With `--answers`, it also writes `docs/answers.json` from the benchmark's per-question export, keeping
the same runs:

```bash
./benchmark_ollama.py --export-answers /tmp/benchmark-answers.json   # in the benchmark folder
./export_results.py /path/to/benchmark-results.md --answers /tmp/benchmark-answers.json
cp /path/to/benchmark_metrics.py .                                     # when the metrics change
```

A new provider needs an entry in `PROVIDERS` (its access route, how it is paid for and its cost basis);
the script stops until it has one. A new model is shown by its ID unless `MODELS` gives it a display
name; a Claude or OpenAI model with a cost needs its list price there, and a model on our GPUs its
hardware.

## Graphs

`charts/` is a Rust crate that draws the page's graphs from `docs/results.json`. It uses ratatui's
`Chart`, `BarChart` and `Canvas` widgets, rendered into ratatui's test backend, so each graph is a
buffer of terminal cells. The page shows them as SVGs next to their tables in `docs/charts/`.

- **SVG output:** a small writer (`charts/src/svg.rs`) turns each buffer into an SVG on a fixed grid of
  8 × 16 px cells. It draws braille dots, box lines, bar blocks and dots as shapes, so a graph looks
  the same whatever fonts the reader has.
- **Snapshots:** the same buffer, as text, is the graph's insta snapshot in `charts/tests/snapshots/`.
  When the data changes, the snapshot diff shows how each graph changed.

```bash
cargo run --release --manifest-path charts/Cargo.toml -- docs/results.json docs/charts   # write the SVGs
cargo test --manifest-path charts/Cargo.toml   # compare each graph with its snapshot
INSTA_UPDATE=always cargo test --manifest-path charts/Cargo.toml   # accept the new graphs
```

`cargo insta review` (from `cargo install cargo-insta`) shows the changed snapshots one by one instead.

## Preview

```bash
python3 -m http.server 8000 --directory docs
```

Then open <http://127.0.0.1:8000/>. Opening `docs/index.html` directly from disk does not work,
because browsers block loading `results.json` from a `file://` page.
