# Contributing

This folder holds a benchmark of decision models on a reading and grammar test in native Turkish (not translated).
You can help in three ways.

## Report a wrong answer key

Open an [answer key correction](https://github.com/zekiworks/analysis/issues/new?template=answer-key-correction.md)
issue. Give:

- the question ID from `answers.json` (`questions.id`), with its topic, page and printed number;
- the printed key and the answer you think is right;
- your evidence: a grammar rule, a reference or your reading of the page.

Please do not paste the question text or a photo of the page: the publisher owns them. The ID, page and number are
enough for us to find the question.

We check each report against the book's own key, or a second person reviews it. The reviewer sees the question and its
options, but not the models' answers. If the fix holds, it creates a new answer key version: we add a row to
[key-changelog.md](key-changelog.md) (question ID, old answer, new answer, reason, date), score every run again on the
new key and publish the results with the new key version.

## Ask us to test a model

Open a [test a model](https://github.com/zekiworks/analysis/issues/new?template=test-a-model.md) issue. Tell us the
model, how to call it (a hosted API, or released weights and the server they need), what it costs, and whether it
returns a probability for each answer option. We read every request, but we cannot promise to run each one.

## Send a dataset or suggest a task

Open a [suggest a task](https://github.com/zekiworks/analysis/issues/new?template=suggest-a-task.md) issue. We test
tasks where a model chooses from given options and the right answers are known in advance. We are looking for public
financial datasets in particular.

## Cite the results

Use [CITATION.cff](CITATION.cff). Cite the results version, the answer key version and the commit you used. The page
shows the first two under "Download the data and check our calculations".
