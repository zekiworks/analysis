# Results changelog

What changed in each results version that went live (`results_version` in `results.json`), newest first. It starts with results 0eb1e828, the release that added Liquid d1-2B; earlier versions are in the repository's history.

## Results 74c13f91 (1 November 2026)

- Added Base Labs' Elephant-1 and Mammoth-1 (open weights): `baselabs/elephant-1` at `b3f8a93` and `baselabs/mammoth-1` at `61cec44` on our GPU, through their model cards' loader (qev's DecisionEngine with the checkpoints' serve.patch). Text: five runs each over the 2,198 scored questions, each model's five runs identical. Mammoth-1 (runs 374, 377, 380, 383, 384): 67.1% right, 8th of 36 decision models. Elephant-1 (runs 373, 375, 376, 378, 379): 52.4% right, 26th of 36. Their loader rounds probabilities to 6 decimals, and the check before their runs allowed for it. Their cost is at Baseten's list prices for the same models. They are not on the Page images tab: their runtime reads images only through an engine without the attention the models were trained with.
- New tab, "I don't know option" (`dont-know/`): the Text tab's questions with a sixth option, "Bilmiyorum" (I don't know), always last and never correct. It covers ten decision models in 18 runs, with accuracy, attempt rate, non-hallucination rate and the mean probability of "Bilmiyorum". It sits apart from the leaderboard and changes none of its numbers.
- From the two new rows: the summary's accuracy line now names Mammoth-1 after Drex Max v1 and 1.1. SubQ Snap's places on the Routing tab move down one (tenth in front of Sonnet 5.5 high, sixteenth in front of Opus 5.5 low, fourteenth in front of Astra low). The paired tests between ranking neighbours pair each new row with the rows on either side of it, in place of two earlier neighbour pairs. 17 other comparisons have new Holm-adjusted p-values, because the correction now covers 2,556 pairs of runs instead of 2,415. No other existing number changed.

## Results 25290875 (1 November 2026)

- Liquid d1-2B (open weights): a note beside its row on how its request times were measured (one GPU with no other known work while its runs took place, not monitored throughout), and its four extra Page images passes in each of conditions B and C, identical to the table's runs 60 and 61, published in `vision-repeats.json` and described on the Page images page. No number changed.

## Results 0eb1e828 (1 November 2026)

- Added Liquid d1-2B (open weights): `LiquidAI/d1-2B` at `10e7671` on our GPU, through its model card's own call. Text: five runs over the 2,198 scored questions (runs 340 to 344), 29.4% right, 29th of 34 decision models, the five runs identical. Page images: conditions B and C over the 763 page-image questions (runs 60 and 61). Its cost is not measured (†).
