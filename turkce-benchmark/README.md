# Turkish Question Bank Benchmark

Results page for language models on 2,210 multiple-choice questions from a TYT Türkçe question bank, in
its second version with the lost markup repaired: scores, accuracy by unit, confidence, the effect of
the repair, paired comparisons, decision models as a first pass for frontier models, speed, output
tokens and cost.

The site is the `docs/` folder, served by GitHub Pages from the `main` branch. It is static:
`docs/app.js` renders the tables from `docs/results.json`.

## Updating the results

`export_results.py` rebuilds `docs/results.json` from the report the benchmark script writes
(`benchmark-results.md`). It keeps the runs over the full question set of the newest question bank,
leaves out runs whose correct option was replaced (a memorization test, not an accuracy run), and
exports only aggregate numbers: no question text, prompts, answers or local paths. The comparisons
between runs (paired tests, cascades, decision-model doubt and each run's change from the previous
question bank) come from the report's `benchmark-analysis` record.

```bash
./export_results.py /path/to/benchmark-results.md
```

A new provider needs an entry in `PROVIDERS` (its access route and cost basis); the script stops until
it has one. A new model is shown by its ID unless `MODELS` gives it a display name, and a Claude or
OpenAI model with a cost needs its list price there.

## Preview

```bash
python3 -m http.server 8000 --directory docs
```

Then open <http://127.0.0.1:8000/>. Opening `docs/index.html` directly from disk does not work,
because browsers block loading `results.json` from a `file://` page.
