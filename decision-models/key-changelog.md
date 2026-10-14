# Answer key changelog

Every setup in this benchmark is scored on one frozen answer key. This file lists every change to that key.

**How a fix works.** A fix to the key needs a check against the book's own key, or a second person who reviews the
question and its options without seeing the models' answers. Each fix creates a new key version, adds a row to this
file (question ID, old answer, new answer, reason, date) and rescores every run. To report a wrong key, see
[CONTRIBUTING.md](CONTRIBUTING.md).

**How to identify a version.** `results.json` names the key version under `answer_key`, with the SHA-256 of the
question bank and the key's fingerprint: the SHA-256 of `[[id, key, excluded], ...]` over every question in
`answers.json`, as compact JSON in question order (`answer_key_fingerprint` in `benchmark_metrics.py`).
`reproduce.py` recomputes the fingerprint and checks every exported answer against the key. `export_results.py`
stops when the answers are graded against a key that is not frozen there.

## Version 2 (frozen 13 October 2026)

- Question bank: `questions-v2.sqlite`, SHA-256 `797ad6c868bc1c9485bc54203f58839ad995b0443b7149f6a9e36cf0d07df4d7`.
- Key fingerprint: `cd7f998de262e355cd28f596465a51f4158211646ee0cbfbc85f5d8cdeced20a`.
- 2,210 questions with a key; 2,198 scored.

Version 2 is the key after the review of 4 October 2026. The review checked 25 disputed keys, confirmed 13 and
removed these 12 questions from scoring.

Their printed keys stay in the data, but they count in no result. Topic, page, test and number locate each question
in the book.

| Question ID | Topic | Page | Test | Number | Change | Reason | Date |
|---|---|---|---|---|---|---|---|
| 379 | 4, Topic and main point of a paragraph | 88 | 3 | 7 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 459 | 4, Topic and main point of a paragraph | 108 | 13 | 8 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 652 | 6, Details that support a paragraph's main point | 160 | 11 | 6 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 2473 | 16, Questions combining several grammar topics | 331 | 16 | 5 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 3024 | 1, Word and phrase meanings | 9 | 1 | 4 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3087 | 1, Word and phrase meanings | 21 | 7 | 6 | Removed from scoring | The key could not be confirmed: a red mark covers the printed answer strip, so the printed key cannot be read. | 2026-10-04 |
| 3185 | 3, How a writer explains and develops ideas | 80 | 7 | 8 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3223 | 5, How a paragraph fits together | 121 | 7 | 2 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 3242 | 5, How a paragraph fits together | 135 | 14 | 2 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 3640 | 12, How words are built | 240 | 1 | 7 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |
| 4115 | 18, Spelling | 366 | 8 | 11 | Removed from scoring | The key could not be confirmed: the page image did not settle the answer. No question-specific note was recorded at review time (4 October); the group reason applies. | 2026-10-04 |
| 4206 | 20, Problems in sentence wording | 418 | 1 | 22 | Removed from scoring | The printed key could not be established against the other reading: both are defensible. Removed on the reviewer's decision. | 2026-10-04 |

## Later fixes

None yet. Each fix adds a row here and a section for its new key version.

| Question ID | Old answer | New answer | Reason | Date | Key version |
|---|---|---|---|---|---|
