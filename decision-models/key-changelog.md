# Answer key changelog

Every setup in this benchmark is scored on one frozen answer key. This file lists every change to that key.

**How a fix works.** A fix to the key needs a check against the book's own key, or a second person who reviews the
question and its options without seeing the models' answers. Each fix creates a new key version, adds a row to this
file (question ID, reason, date) and rescores every run. The old and new answers, like every key and each question's
place in the book, stay in the private answer files: nothing published per question may rebuild the key.

To report a wrong key, see [CONTRIBUTING.md](CONTRIBUTING.md).

**How to identify a version.** `results.json` names the key version under `answer_key`, with the SHA-256 of the
question bank and the key's fingerprint: the SHA-256 of `[[id, key, excluded], ...]` over every question in the
private `answers.json`, as compact JSON in question order (`answer_key_fingerprint` in `benchmark_metrics.py`).

`reproduce.py` recomputes the fingerprint and checks every exported answer against the key. `export_results.py` stops
when the answers are graded against a key that is not frozen there.

## Version 2 (frozen 13 October 2026)

- Question bank: `questions-v2.sqlite`, SHA-256 `797ad6c868bc1c9485bc54203f58839ad995b0443b7149f6a9e36cf0d07df4d7`.
- Key fingerprint: `cd7f998de262e355cd28f596465a51f4158211646ee0cbfbc85f5d8cdeced20a`.
- 2,210 questions with a key; 2,198 scored.

Version 2 is the key after the review of 4 October 2026. The review checked 25 disputed keys, confirmed 13 and
removed these 12 questions from scoring.

Their printed keys stay in the private data, but they count in no result. Where each stands in the book stays private,
as every question's place does.

| Question ID | Change | Reason | Date |
|---|---|---|---|
| 379 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 459 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 652 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 2473 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 3024 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3087 | Removed from scoring | The key could not be confirmed: a red mark covers the printed answer strip, so the printed key cannot be read. | 2026-10-04 |
| 3185 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3223 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3242 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 3640 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 4115 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 4206 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |

## Later fixes

None yet. Each fix adds a row here and a section for its new key version.

| Question ID | Reason | Date | Key version |
|---|---|---|---|
