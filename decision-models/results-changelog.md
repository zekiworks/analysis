# Results changelog

What changed in each results version that went live (`results_version` in `results.json`), newest first. It starts with results 0eb1e828, the release that added Liquid d1-2B; earlier versions are in the repository's history.

## Results 25290875 (1 November 2026)

- Liquid d1-2B (open weights): a note beside its row on how its request times were measured (one GPU with no other known work while its runs took place, not monitored throughout), and its four extra Page images passes in each of conditions B and C, identical to the table's runs 60 and 61, published in `vision-repeats.json` and described on the Page images page. No number changed.

## Results 0eb1e828 (1 November 2026)

- Added Liquid d1-2B (open weights): `LiquidAI/d1-2B` at `10e7671` on our GPU, through its model card's own call. Text: five runs over the 2,198 scored questions (runs 340 to 344), 29.4% right, 29th of 34 decision models, the five runs identical. Page images: conditions B and C over the 763 page-image questions (runs 60 and 61). Its cost is not measured (†).
