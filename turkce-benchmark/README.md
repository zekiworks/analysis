# Turkish Question Bank Benchmark

Results page for language models on 2,210 multiple-choice questions from a TYT Türkçe question bank, in
its second version with the lost markup repaired: scores, accuracy by unit, confidence with bootstrap
intervals, the effect of the repair, paired comparisons, decision models as a first pass for frontier
models, speed, output tokens, cost and hardware.

The site is the `docs/` folder, served by GitHub Pages from the `main` branch. It is static:
`docs/app.js` renders the tables from `docs/results.json`. `docs/answers.json` holds every run's
answer to every question without the questions' text, and `benchmark_metrics.py` is a copy of the
benchmark's metric code, so the tables can be rebuilt from the published data.

## Updating the results

`export_results.py` rebuilds `docs/results.json` from the report the benchmark script writes
(`benchmark-results.md`). It keeps the runs over the full question set of the newest question bank,
leaves out runs whose correct option was replaced (a memorization test, not an accuracy run), and
exports only aggregate numbers: no question text, prompts, answers or local paths. The comparisons
between runs (paired tests with Holm-adjusted p-values, cascades, decision-model doubt, confidence
sources scored on the same answers and each run's change from the previous question bank) come from
the report's `benchmark-analysis` record.

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

## Preview

```bash
python3 -m http.server 8000 --directory docs
```

Then open <http://127.0.0.1:8000/>. Opening `docs/index.html` directly from disk does not work,
because browsers block loading `results.json` from a `file://` page.
