#!/usr/bin/env python3
"""Recompute the published numbers from docs/answers.json and check them against docs/results.json.

    python3 reproduce.py [--docs DOCS]

For every main run: the correct answers on the scored questions (questions the key audit excluded are
skipped), AUROC, expected calibration error, the answers scored 0.99 or more (also before the key audit,
when results.json has those counts), and the leaderboard's tied groups (every pair of runs tested,
exact McNemar, Holm over all pairs, alpha 0.05). Then the listed paired comparisons: exact McNemar
and Holm over the listed pairs. Uses only the standard library and benchmark_metrics.py, the metric code
the benchmark report uses. Exits with status 1 when anything differs beyond the tolerances printed.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import benchmark_metrics as bm  # noqa: E402

TIE_ALPHA = 0.05  # the report's level for telling two runs apart (TIE_ALPHA in benchmark_ollama.py)
METRIC_TOLERANCE = 1e-9  # absolute, for AUROC and ECE
P_TOLERANCE = 1e-9  # relative, for p-values


def close(published: Any, recomputed: Any, absolute: float = 0.0, relative: float = 0.0) -> bool:
    if published is None or recomputed is None:
        return published is None and recomputed is None
    return math.isclose(published, recomputed, rel_tol=relative, abs_tol=absolute)


def number(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def sure_text(sure: dict[str, Any] | None) -> str:
    return "-" if sure is None else f"{sure['correct']}/{sure['questions']}"


def label(run: dict[str, Any]) -> str:
    text = run.get("name") or run.get("model") or str(run["run"])
    if run.get("variant"):
        text += f", {run['variant']}"
    if run.get("reasoning"):
        text += f" ({run['reasoning']})"
    return text if len(text) <= 36 else text[:35] + "…"


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def cell(self, matched: bool, recomputed: str, published: str) -> str:
        """The recomputed value, with the published one after it when they differ."""
        if matched:
            self.passed += 1
            return recomputed
        self.failed += 1
        return f"{recomputed} ≠ {published}"

    def metric(self, published: float | None, recomputed: float | None) -> str:
        """An AUROC or ECE cell: four decimals, six when the values differ."""
        matched = close(published, recomputed, METRIC_TOLERANCE)
        digits = 4 if matched else 6
        return self.cell(matched, number(recomputed, digits), number(published, digits))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--docs",
        type=Path,
        default=Path(__file__).resolve().parent / "docs",
        help="folder with results.json and answers.json (default: docs next to this script)",
    )
    args = parser.parse_args()
    results = json.loads((args.docs / "results.json").read_text(encoding="utf-8"))
    answers = json.loads((args.docs / "answers.json").read_text(encoding="utf-8"))
    checks = Checks()

    status = answers["questions"]["status"]
    keys = answers["questions"]["key"]
    scored = [index for index, value in enumerate(status) if value != "excluded"]
    excluded = [index for index, value in enumerate(status) if value == "excluded"]
    print(f"{args.docs / 'answers.json'}: {len(status)} questions, {len(excluded)} excluded by the key audit, {len(scored)} scored")
    if len(scored) != results["questions"]:
        checks.failed += 1
        print(f"MISMATCH: results.json scores {results['questions']} questions, answers.json {len(scored)}")
    else:
        checks.passed += 1
    extra = [f"{len(answers[name])} {name}" for name in ("repeat_runs", "pipeline_runs") if answers.get(name)]
    if extra:
        print(f"Not checked here: {', '.join(extra)}")
    print(
        f"Tolerances: counts and group letters exact; AUROC and ECE within {METRIC_TOLERANCE:g}; "
        f"p-values within a relative {P_TOLERANCE:g}. A cell shows the recomputed value, then '≠' and the "
        "published value when they differ."
    )

    published = {run["run"]: run for run in results["runs"]}
    exported = {run["run"]: run for run in answers["runs"]}
    for run_id in sorted(published.keys() ^ exported.keys()):
        checks.failed += 1
        where = "results.json" if run_id in published else "answers.json"
        print(f"MISMATCH: run {run_id} is only in {where}")
    runs = [run_id for run_id in published if run_id in exported]

    correct: dict[int, list[int]] = {}
    rows: list[list[str]] = []
    for run_id in runs:
        run, answer = published[run_id], exported[run_id]
        outcomes = [int(answer["correct"][index]) for index in scored]
        correct[run_id] = outcomes
        # Each outcome must follow from the chosen option and the key, where the export has the key.
        inconsistent = sum(
            1
            for index in scored
            if keys[index] is not None and int(answer["choice"][index] == keys[index]) != int(answer["correct"][index])
        )
        total = sum(outcomes)
        cells = [
            str(run_id),
            label(run),
            checks.cell(
                total == run["correct"] and not inconsistent,
                f"{total} {100 * total / len(scored):.2f}%" + (f" ({inconsistent} not from the key)" if inconsistent else ""),
                str(run["correct"]),
            ),
        ]
        pairs = [
            (float(answer["score"][index]), int(answer["correct"][index]))
            for index in scored
            if answer["score"][index] is not None
        ]
        confidence = run.get("confidence")
        if confidence is None or not pairs:
            matched = confidence is None and not pairs
            cells += [checks.cell(matched, "-", "confidence" if confidence else "none")] + ["-"] * 3
        else:
            auroc = bm.auroc(pairs)
            ece = bm.calibration(pairs)["ece"]
            sure = bm.score_extremes(pairs)["sure"]
            published_sure = confidence["sure"]
            cells += [
                checks.metric(confidence["auroc"], auroc),
                checks.metric(confidence["ece"], ece),
                checks.cell(
                    (sure["questions"], sure["correct"]) == (published_sure["questions"], published_sure["correct"]),
                    sure_text(sure),
                    sure_text(published_sure),
                ),
            ]
            if "sure_before_audit" in confidence:
                # Counted only for runs that answered the excluded questions, graded with the printed key.
                before = None
                if any(answer["choice"][index] is not None for index in excluded):
                    before = bm.score_extremes(
                        [(float(score), int(right)) for score, right in zip(answer["score"], answer["correct"]) if score is not None]
                    )["sure"]
                published_before = confidence["sure_before_audit"]
                matched = (before is None and published_before is None) or (
                    before is not None
                    and published_before is not None
                    and (before["questions"], before["correct"]) == (published_before["questions"], published_before["correct"])
                )
                cells.append(checks.cell(matched, sure_text(before), sure_text(published_before)))
            else:
                cells.append("not in results")
        rows.append(cells)

    # Tied groups: the runs in rank order (more correct first, then the older run), every pair tested,
    # Holm-adjusted over all pairs.
    ranked = sorted(runs, key=lambda run_id: (-sum(correct[run_id]), run_id))
    every_pair = list(itertools.combinations(range(len(ranked)), 2))
    adjusted = dict(
        zip(every_pair, bm.holm([bm.paired_comparison(correct[ranked[i]], correct[ranked[j]])["p"] for i, j in every_pair]))
    )
    letters = dict(zip(ranked, bm.tied_groups(len(ranked), lambda i, j: adjusted[min(i, j), max(i, j)] < TIE_ALPHA)))
    for cells, run_id in zip(rows, runs):
        group = published[run_id].get("group")
        cells.append(checks.cell(letters[run_id] == group, letters[run_id], str(group)))
    group_pairs = results.get("group_pairs")
    group_pairs_cell = checks.cell(group_pairs == len(every_pair), str(len(every_pair)), str(group_pairs))

    header = ["run", "configuration", "correct", "AUROC", "ECE", "≥ 0.99", "≥ 0.99 before audit", "group"]
    widths = [max(len(row[column]) for row in [header, *rows]) for column in range(len(header))]
    print()
    for row in [header, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    print(f"\nTied groups: {group_pairs_cell} pairs, Holm over all of them, alpha {TIE_ALPHA}")

    # Paired comparisons: Holm within each set of pairs over the same questions (one set here).
    families: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item in results["paired"]:
        if item["first"] not in correct or item["second"] not in correct:
            checks.failed += 1
            print(f"MISMATCH: pair {item['first']} vs {item['second']} names a run without answers")
            continue
        test = bm.paired_comparison(correct[item["first"]], correct[item["second"]])
        families[item["questions"]].append((item, test))
    mismatches: list[str] = []
    listed = 0
    for family in families.values():
        for (item, test), p_holm in zip(family, bm.holm([test["p"] for _, test in family])):
            listed += 1
            cells = [
                checks.cell(item["questions"] == test["questions"], str(test["questions"]), str(item["questions"])),
                checks.cell(
                    (item["first_only"], item["second_only"]) == (test["first_only"], test["second_only"]),
                    f"{test['first_only']} vs {test['second_only']}",
                    f"{item['first_only']} vs {item['second_only']}",
                ),
                checks.cell(close(item["p"], test["p"], relative=P_TOLERANCE), f"p {test['p']:.3g}", f"{item['p']:.3g}"),
                checks.cell(
                    close(item["p_holm"], p_holm, relative=P_TOLERANCE), f"Holm {p_holm:.3g}", f"{item['p_holm']:.3g}"
                ),
            ]
            if any("≠" in cell for cell in cells):
                mismatches.append(f"  {item['first']} vs {item['second']}: " + ", ".join(cells))
    print(
        f"Paired comparisons (exact McNemar, Holm over the {listed} listed pairs): "
        f"{listed - len(mismatches)} of {listed} match"
    )
    for line in mismatches:
        print(line)

    print(f"\n{checks.passed} checks match, {checks.failed} differ")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
