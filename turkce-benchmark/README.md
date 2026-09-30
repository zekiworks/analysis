# Turkish Question Bank Benchmark

Results page for language models on 2,198 multiple-choice questions from a TYT Türkçe question bank:
scores, accuracy by unit, confidence, speed and cost.

The site is the `docs/` folder, served by GitHub Pages from the `main` branch. It is static:
`docs/app.js` renders the tables from `docs/results.json`.

## Updating the results

`export_results.py` rebuilds `docs/results.json` from the report the benchmark script writes
(`benchmark-results.md`). It keeps the runs over the full question set and only aggregate numbers: no
question text, prompts, answers or local paths.

```bash
./export_results.py /path/to/benchmark-results.md
```

A new provider needs an entry in `PROVIDERS` (its access route, confidence source and cost basis);
the script stops until it has one. A new model is shown by its ID unless `MODELS` gives it a display
name, and a Claude or OpenAI model with a cost needs its list price there.

## Preview

```bash
python3 -m http.server 8000 --directory docs
```

Then open <http://127.0.0.1:8000/>. Opening `docs/index.html` directly from disk does not work,
because browsers block loading `results.json` from a `file://` page.
