#!/usr/bin/env python3
"""Recompute the published numbers from answers.json and check them against results.json.

    python3 reproduce.py [--docs FOLDER]

First the answer key: answers.json's keys and exclusions must give the fingerprint of the frozen key
version results.json names (bm.answer_key_fingerprint). For every main run: the correct answers on the
scored questions (questions the key audit excluded are skipped), each following from the chosen option
and the key, AUROC, expected calibration error, the answers scored 0.99 or more with the Wilson interval
of their accuracy (the counts also before the key audit, when results.json has them), and the
leaderboard's tied groups (every pair of runs tested, exact McNemar, Holm over all pairs, alpha 0.05),
including that two runs share a letter exactly when that test does not tell them apart. Then the listed
paired comparisons: exact McNemar and Holm over the listed pairs. Then each main run's calibration after
refit (bm.refit_calibration, 5 folds by passage): the gap and Brier score after refit, the constant guess's
Brier score, the five slopes, the questions used and whether every fit converged. Then the grading of every other
exported run (repeats, routing tests, request sizes) against the same key. Then each format rerun (a
setup's later main run with another number of questions per request) against its setup's first run:
exact McNemar and Holm over those comparisons. Then the reasoning pairs (N3): each model's gains from a lower
to a higher reasoning setting on reading and on grammar, and the bootstrap interval of their difference, with
the reading units, seed and resamples results.json names. Then the repeats: each
configuration's repeated runs, recomputed from their exported answers. Then the replays: every routing
simulation (the threshold chosen in sample and its 300 held-out splits), and the Decider v1.1 replay (`replay`): the
decision run's answers kept at each cutoff and in its surest share, and what keeping them changes in
front of each second run, on all questions and on the same held-out splits; with them the answer-key
baselines (options per question, the key's most used letter and its share). Then the live tests: each
test's kept questions (the decision run's scores against its cutoff), the pair's and the second model's
accuracy, the paired change with its 95% interval and exact McNemar p and, with one question per
request, each question's wait. Then the costs: each priced run's from its token counts at the published
rates, every run without a price shown as a free tier or self-hosted, each routing simulation's and
replay's cost per 1,000 questions from its runs, and the routing tests' costs from their parts. Uses only
the standard library and benchmark_metrics.py, the metric code the benchmark report uses. Exits with
status 1 when anything differs beyond the tolerances printed.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import benchmark_metrics as bm  # noqa: E402

TIE_ALPHA = 0.05  # the report's level for telling two runs apart (TIE_ALPHA in benchmark_ollama.py)
METRIC_TOLERANCE = 1e-9  # absolute, for AUROC and ECE
P_TOLERANCE = 1e-9  # relative, for p-values
COST_TOLERANCE = 1e-9  # relative, for dollar amounts
CACHE_KINDS = ("cached_input_tokens", "cache_write_input_tokens", "cache_write_1h_input_tokens")


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


def token_cost(tokens: dict[str, int], rates: dict[str, float]) -> float:
    """Token counts at a price's rates in USD per 1M tokens: the prompt tokens outside the cache at the input
    rate, the cache reads and writes among them and the output at their own."""
    uncached = tokens["input_tokens"] - sum(tokens[kind] for kind in CACHE_KINDS)
    return (uncached * rates["input_tokens"] + sum(tokens[kind] * rates[kind] for kind in (*CACHE_KINDS, "output_tokens"))) / 1e6


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
        default=Path(__file__).resolve().parent,
        help="folder with results.json and answers.json (default: this script's folder)",
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
    # The answer key: answers.json's keys and exclusions must be the frozen key version results.json names.
    key = results.get("answer_key") or {}
    fingerprint = bm.answer_key_fingerprint(answers["questions"]["id"], keys, [value == "excluded" for value in status])
    excluded_ids = [answers["questions"]["id"][index] for index in excluded]
    if (fingerprint, excluded_ids, answers["dataset"]["graded_sha256"]) == (
        key.get("fingerprint"), key.get("excluded"), key.get("graded_sha256")
    ):
        checks.passed += 1
        print(f"Answer key version {key['version']}: fingerprint {fingerprint[:12]}, {len(excluded_ids)} questions excluded")
    else:
        checks.failed += 1
        print(f"MISMATCH: answers.json's key (fingerprint {fingerprint[:12]}) is not answer key version {key.get('version')}")
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
                # The counts, and the Wilson interval of their accuracy that the page turns into an error range.
                checks.cell(
                    (sure["questions"], sure["correct"]) == (published_sure["questions"], published_sure["correct"])
                    and (sure["interval"] is None) == (published_sure.get("interval") is None)
                    and all(
                        close(published, recomputed, METRIC_TOLERANCE)
                        for published, recomputed in zip(published_sure.get("interval") or [], sure["interval"] or [])
                    ),
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
    # The published letters must say which pairs the test tells apart: a shared letter for every pair with an
    # adjusted p of TIE_ALPHA or more, none for the others.
    letter_mismatches: list[str] = []
    for i, j in every_pair:
        first, second = published[ranked[i]], published[ranked[j]]
        shared = bool(set(first.get("group") or "") & set(second.get("group") or ""))
        tied = adjusted[i, j] >= TIE_ALPHA
        if "≠" in checks.cell(shared == tied, "shared" if shared else "none", "tied" if tied else "told apart"):
            letter_mismatches.append(
                f"  {label(first)} ({first.get('group')}) vs {label(second)} ({second.get('group')}): Holm p {adjusted[i, j]:.3g}"
            )
    print(
        f"Letters against the tests: {len(every_pair) - len(letter_mismatches)} of {len(every_pair)} pairs share a letter "
        f"exactly when Holm p ≥ {TIE_ALPHA}"
    )
    for line in letter_mismatches:
        print(line)

    # Paired comparisons: Holm within each set of pairs over the same questions (one set here).
    families: dict[int, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item in results["paired"]:
        if item["first"] not in correct or item["second"] not in correct:
            checks.failed += 1
            print(f"MISMATCH: pair {item['first']} vs {item['second']} names a run without answers")
            continue
        test = bm.paired_comparison(correct[item["first"]], correct[item["second"]])
        families[item["questions"]].append((item, test))
    position = {run_id: index for index, run_id in enumerate(ranked)}

    def all_pairs(item: dict[str, Any]) -> float:
        """A listed pair's p-value with Holm's correction over every pair, the correction the letters use."""
        first, second = sorted((position[item["first"]], position[item["second"]]))
        return adjusted[first, second]

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
                checks.cell(
                    close(item["p_holm_all"], all_pairs(item), relative=P_TOLERANCE),
                    f"Holm over all pairs {all_pairs(item):.3g}",
                    f"{item['p_holm_all']:.3g}",
                ),
            ]
            if any("≠" in cell for cell in cells):
                mismatches.append(f"  {item['first']} vs {item['second']}: " + ", ".join(cells))
    print(
        f"Paired comparisons (exact McNemar, Holm over the {listed} listed pairs and over all pairs): "
        f"{listed - len(mismatches)} of {listed} match"
    )
    for line in mismatches:
        print(line)

    before = checks.passed + checks.failed
    refit_mismatches = check_refits(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nCalibration after refit ({bm.REFIT_METHOD}, the same folds for every run, questions without a score left out; "
        f"gaps, Brier scores and slopes within {METRIC_TOLERANCE:g}): {checked - len(refit_mismatches)} of {checked} match"
    )
    for line in refit_mismatches:
        print(line)

    before = checks.passed + checks.failed
    grading_mismatches = check_grading(answers, keys, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nGrading (every repeat, routing-test and request-size run, each answer against answer key version "
        f"{key.get('version')}): {checked - len(grading_mismatches)} of {checked} runs match"
    )
    for line in grading_mismatches:
        print(line)

    before = checks.passed + checks.failed
    format_mismatches = check_formats(results, correct, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nRequest formats ({len(results.get('formats', []))} reruns against their setup's first run on the same questions; "
        f"exact McNemar, Holm over these comparisons): {checked - len(format_mismatches)} of {checked} match"
    )
    for line in format_mismatches:
        print(line)

    before = checks.passed + checks.failed
    reasoning_mismatches = check_reasoning(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nReasoning by task ({len(results.get('reasoning', {}).get('pairs', []))} pairs: the gains on reading and on grammar "
        f"and the bootstrap interval of their difference; within {METRIC_TOLERANCE:g}): {checked - len(reasoning_mismatches)} of {checked} match"
    )
    for line in reasoning_mismatches:
        print(line)

    before = checks.passed + checks.failed
    repeat_mismatches = check_repeats(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nRepeats ({len(results.get('repeats', []))} configurations, from their runs' exported answers; accuracy and "
        f"score spread within {METRIC_TOLERANCE:g}): {checked - len(repeat_mismatches)} of {checked} match"
    )
    for line in repeat_mismatches:
        print(line)

    before = checks.passed + checks.failed
    replay_mismatches = check_replays(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nReplays ({len(results['cascades'])} routing simulations, the lead replay and the answer-key baselines, from the exported answers in question "
        f"order with passages kept together; shares and accuracy within {METRIC_TOLERANCE:g}): "
        f"{checked - len(replay_mismatches)} of {checked} match"
    )
    for line in replay_mismatches:
        print(line)

    before = checks.passed + checks.failed
    live_mismatches = check_live_tests(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nLive tests ({sum(1 for item in results['pipelines'] if item.get('measured'))} tests with new calls to the "
        "second model, from the exported answers; accuracy, change, interval and waits within "
        f"{METRIC_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}): {checked - len(live_mismatches)} of {checked} match"
    )
    for line in live_mismatches:
        print(line)

    before = checks.passed + checks.failed
    cost_mismatches = check_costs(results, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nCosts (tokens at the published rates within a relative {COST_TOLERANCE:g}; routing costs from their parts): "
        f"{checked - len(cost_mismatches)} of {checked} match"
    )
    for line in cost_mismatches:
        print(line)

    print(f"\n{checks.passed} checks match, {checks.failed} differ")
    return 1 if checks.failed else 0


def check_grading(answers: dict[str, Any], keys: list[str | None], scored: list[int], checks: Checks) -> list[str]:
    """Check that every exported run besides the main ones (the main ones are checked with their accuracy) is graded on
    the published key: each answer it gave on a scored question is correct exactly when its option is the key's.
    Returns a line per run that differs."""
    mismatches = []
    for run in answers.get("repeat_runs", []) + answers.get("pipeline_runs", []) + answers.get("batching_runs", []):
        given = [index for index in scored if run["correct"][index] is not None and keys[index] is not None]
        differ = sum(1 for index in given if int(run["choice"][index] == keys[index]) != int(run["correct"][index]))
        if "≠" in checks.cell(not differ, f"{len(given)} answers", f"{differ} not from the key"):
            mismatches.append(f"  run {run['run']} ({label(run)}): {differ} of {len(given)} answers are not graded on the key")
    return mismatches


def check_refits(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute each run's calibration after refit (confidence.ece_refit, brier_refit, brier_base, refit_slopes,
    refit_questions and refit_converged) from the exported answers: bm.refit_calibration on the run's scored questions
    that have a score, in bm.refit_folds' folds of every scored question, each passage's questions one cluster and a
    question without a passage its own. Returns a line per run that differs."""
    questions = answers["questions"]
    clusters = {
        index: f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in scored
    }
    fold_of = bm.refit_folds(clusters.values())
    exported = {run["run"]: run for run in answers["runs"]}
    mismatches = []
    for run in results["runs"]:
        confidence = run.get("confidence")
        if confidence is None:
            continue
        answer = exported[run["run"]]
        kept = [index for index in scored if answer["score"][index] is not None]
        again = bm.refit_calibration(
            [(float(answer["score"][index]), int(answer["correct"][index])) for index in kept],
            [fold_of[clusters[index]] for index in kept],
        )
        published_slopes = confidence.get("refit_slopes") or []
        cells = [
            checks.metric(confidence.get("ece_refit"), again["ece_refit"]),
            checks.metric(confidence.get("brier_refit"), again["brier_refit"]),
            checks.metric(confidence.get("brier_base"), again["brier_base"]),
            checks.cell(
                len(published_slopes) == len(again["slopes"])
                and all(close(published, recomputed, METRIC_TOLERANCE) for published, recomputed in zip(published_slopes, again["slopes"])),
                "slopes " + " ".join(number(slope, 3) for slope in again["slopes"]),
                "slopes " + " ".join(number(slope, 3) for slope in published_slopes),
            ),
            checks.cell(
                (confidence.get("refit_questions"), confidence.get("refit_converged")) == (again["questions"], again["converged"]),
                f"{again['questions']} questions, converged {again['converged']}",
                f"{confidence.get('refit_questions')} questions, converged {confidence.get('refit_converged')}",
            ),
        ]
        if any("≠" in cell for cell in cells):
            mismatches.append(f"  run {run['run']} ({label(run)}): " + ", ".join(cells))
    return mismatches


def check_formats(results: dict[str, Any], correct: dict[int, list[int]], checks: Checks) -> list[str]:
    """Recompute each format rerun's comparison with its setup's first run (results.json `formats`) from the exported
    answers on the scored questions: the counts, the paired difference with its interval, the exact McNemar p and Holm's
    correction over these comparisons. Returns a line per comparison that differs."""
    items = results.get("formats", [])
    tests = [bm.paired_comparison(correct[item["run"]], correct[item["base"]]) for item in items]
    mismatches = []
    for item, test, p_holm in zip(items, tests, bm.holm([test["p"] for test in tests])):
        counts = (sum(correct[item["run"]]), sum(correct[item["base"]]), test["first_only"], test["second_only"])
        published = (item["correct"], item["base_correct"], item["first_only"], item["second_only"])
        cells = [
            checks.cell(counts == published, " ".join(map(str, counts)), " ".join(map(str, published))),
            checks.cell(
                all(close(item[key], test[key], METRIC_TOLERANCE) for key in ("difference", "low", "high")),
                f"{100 * test['difference']:+.2f}", f"{100 * item['difference']:+.2f}",
            ),
            checks.cell(
                close(item["p"], test["p"], relative=P_TOLERANCE) and close(item["p_holm"], p_holm, relative=P_TOLERANCE),
                f"p {test['p']:.3g}, Holm {p_holm:.3g}", f"p {item['p']:.3g}, Holm {item['p_holm']:.3g}",
            ),
        ]
        if any("≠" in cell for cell in cells):
            mismatches.append(f"  run {item['run']} against run {item['base']}: " + ", ".join(cells))
    return mismatches


def check_reasoning(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute each reasoning pair (results.json `reasoning`, N3) from the exported answers: the gains from the lower
    to the higher setting on reading and on grammar, and the bootstrap interval of their difference
    (bm.bootstrap_gain_difference), on the scored questions in question order with each passage's questions as one
    cluster, with the reading units, seed and resamples results.json names. Returns a line per value that differs."""
    published = results.get("reasoning")
    if not published:
        return []
    questions = answers["questions"]
    order = sorted(scored, key=lambda index: questions["id"][index])
    reading = set(published["reading_units"])
    parts = ["reading" if questions["unit"][index] in reading else "grammar" for index in order]
    clusters = [
        f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in order
    ]
    exported = {run["run"]: run for run in answers["runs"]}
    mismatches = []
    for item in published["pairs"]:
        low, high = ([int(bool(exported[run]["correct"][index])) for index in order] for run in (item["low"], item["high"]))
        test = bm.bootstrap_gain_difference(low, high, parts, clusters, of="grammar", against="reading",
                                            resamples=published["resamples"], seed=published["seed"])
        points = lambda values: " ".join(f"{100 * value:+.2f}" for value in values)  # noqa: E731
        for what, recomputed, shown in (
            ("gains and difference", (test["gains"]["reading"], test["gains"]["grammar"], test["difference"]),
             (item["reading_gain"], item["grammar_gain"], item["difference"])),
            ("interval", tuple(test["interval"]), tuple(item["interval"])),
        ):
            cell = checks.cell(all(close(a, b, METRIC_TOLERANCE) for a, b in zip(shown, recomputed)), points(recomputed), points(shown))
            if "≠" in cell:
                mismatches.append(f"  runs {item['low']} and {item['high']}, {what}: {cell}")
    return mismatches


def check_repeats(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute each repeated configuration's stability from its runs' answers, on the scored questions every
    run answered; returns a line per configuration that differs."""
    by_run = {run["run"]: run for run in answers["runs"] + answers.get("repeat_runs", [])}
    counts = ("questions", "changed_answer", "wrong_any", "wrong_every_run_same", "scored", "score_identical", "sure_wrong", "sure_wrong_every_run")
    mismatches = []
    for item in results.get("repeats", []):
        missing = [run_id for run_id in item["runs"] if run_id not in by_run]
        if missing:
            checks.failed += 1
            mismatches.append(f"  {label(item)}: runs {missing} are not in answers.json")
            continue
        outcomes = [
            {index: (run["correct"][index], run["choice"][index], run["score"][index]) for index in scored if run["correct"][index] is not None}
            for run in (by_run[run_id] for run_id in item["runs"])
        ]
        common = set.intersection(*(set(outcome) for outcome in outcomes))
        stats = bm.repeat_stability([{index: outcome[index] for index in common} for outcome in outcomes])
        cells = [checks.cell(stats.get(key) == item[key], f"{key} {stats.get(key)}", str(item[key])) for key in counts]
        accuracy_matched = len(stats["accuracy"]) == len(item["accuracy"]) and all(
            close(published, recomputed, METRIC_TOLERANCE) for published, recomputed in zip(item["accuracy"], stats["accuracy"])
        )
        cells.append(checks.cell(accuracy_matched, f"accuracy {stats['accuracy']}", str(item["accuracy"])))
        cells.append(
            checks.cell(
                close(item["score_spread_median"], stats["score_spread_median"], METRIC_TOLERANCE),
                f"score spread {number(stats['score_spread_median'])}",
                number(item["score_spread_median"]),
            )
        )
        if any("≠" in cell for cell in cells):
            mismatches.append(f"  {label(item)}: " + ", ".join(cell for cell in cells if "≠" in cell))
    return mismatches


def check_replays(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute every routing simulation (bm.cascade) and the lead replay (bm.kept_answers, bm.handoff, bm.share_rule)
    from the exported answers, on the scored questions in question order with each passage's questions as one cluster,
    as the report takes them; returns a line per mismatch."""
    questions = answers["questions"]
    order = sorted(scored, key=lambda index: questions["id"][index])
    clusters = [
        f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in order
    ]
    exported = {run["run"]: run for run in answers["runs"]}
    runs = {run["run"]: run for run in results["runs"]}
    mismatches: list[str] = []

    def outcomes(run_id: int) -> tuple[list[int], list[float]]:
        answer = exported[run_id]
        return [int(bool(answer["correct"][index])) for index in order], [answer["score"][index] or 0.0 for index in order]

    def check(what: str, published: Any, recomputed: Any, kind: str = "exact") -> None:
        if kind == "exact":
            cell = checks.cell(published == recomputed, str(recomputed), str(published))
        elif kind == "cost":
            cell = checks.cell(close(published, recomputed, relative=COST_TOLERANCE), number(recomputed, 6), number(published, 6))
        else:
            cell = checks.cell(close(published, recomputed, METRIC_TOLERANCE), number(recomputed, 6), number(published, 6))
        if "≠" in cell:
            mismatches.append(f"  {what}: {cell}")

    for item in results["cascades"]:
        name = f"routing {label(runs[item['decision']])} → {label(runs[item['frontier']])}"
        correct, scores = outcomes(item["decision"])
        second, _ = outcomes(item["frontier"])
        again = bm.cascade(scores, correct, second, clusters=clusters)
        check(f"{name}, threshold in sample", item["in_sample"]["threshold"], again["in_sample"]["threshold"])
        held = ("answered", "difference", "worse", "kept_right", "kept_wrong", "handed_off")
        for part, keys in (("in_sample", ("answered", "accuracy")), ("held_out", held)):
            for key in keys:
                check(f"{name}, {key} {part.replace('_', ' ')}", item[part][key], again[part][key], "metric")
        shares = item["held_out"]
        check(f"{name}, held-out shares add up", True,
              close(shares["kept_right"] + shares["kept_wrong"], shares["answered"], METRIC_TOLERANCE)
              and close(shares["answered"] + shares["handed_off"], 1.0, METRIC_TOLERANCE))
        check(f"{name}, curve", item["curve"], again["curve"])

    lead = results["replay"]
    decision = runs[lead["decision"]]
    correct, scores = outcomes(lead["decision"])
    check("replay, questions", lead["questions"], len(order))
    for row in lead["cutoffs"]:
        kept = bm.kept_answers(scores, correct, row["cutoff"])
        check(f"replay, kept and wrong at {row['cutoff']}", (row["kept"], row["wrong"]), (kept["kept"], kept["wrong"]))
    share = lead["share"]
    cut = bm.share_cut(scores, share["share"])
    surest = bm.kept_answers(scores, correct, cut)
    check("replay, surest share's cut", share["cut"], cut)
    check("replay, surest share kept and wrong", (share["kept"], share["wrong"]), (surest["kept"], surest["wrong"]))
    interval = bm.wilson_interval(surest["kept"] - surest["wrong"], surest["kept"]) or [None, None]
    for end, published, again in zip(("low", "high"), share["interval"] or [None, None], interval):
        check(f"replay, surest share's interval, {end}", published, again, "metric")
    first_cost = 1000 * decision["api_equivalent_usd"] / decision["answered_questions"]
    for item in lead["frontiers"]:
        frontier = runs[item["frontier"]]
        name = f"replay {label(decision)} → {label(frontier)}"
        second, _ = outcomes(item["frontier"])
        cost = 1000 * frontier["api_equivalent_usd"] / frontier["answered_questions"]
        rules = (
            ("at the sure threshold", item["sure"], bm.handoff(scores, correct, second, results["sure_threshold"])),
            ("with the surest share", item["share"], bm.share_rule(scores, correct, second, share["share"], clusters=clusters)),
        )
        for what, published, again in rules:
            check(f"{name} {what}, kept", (published["kept"], published["first_only"], published["second_only"]),
                  (again["kept"], again["first_only"], again["second_only"]))
            check(f"{name} {what}, difference", published["difference"], again["difference"], "metric")
            check(f"{name} {what}, cost", published["usd_per_1000"], first_cost + cost * (1 - again["kept"] / len(order)), "cost")
            for key in ("answered", "difference", "worse", "better") if "held_out" in again else ():
                check(f"{name} {what}, {key} held out", published["held_out"][key], again["held_out"][key], "metric")
    # The baselines: random guessing among the options of the lead run's questions, and the key's most used letter.
    letters: dict[str, int] = defaultdict(int)
    for index in scored:
        letters[questions["key"][index]] += 1
    letter, used = max(sorted(letters.items()), key=lambda item: item[1])
    probabilities = exported[lead["decision"]]["probabilities"]
    options = {len(probabilities[index]) for index in scored if probabilities[index]}
    base = results["baselines"]
    check("baselines, options per question", base["options"], options.pop() if len(options) == 1 else sorted(options))
    check("baselines, the key's most used letter", base["letter"], letter)
    check("baselines, that letter's share", base["letter_share"], used / len(scored), "metric")
    return mismatches


def check_live_tests(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute every live test (results.json `pipelines` with `measured`) from the exported answers, in question
    order as the report takes them: the held-out questions (the second model's run alone), the ones the decision
    model kept (those its new run left out, each scored at or above the cutoff), the pair's and the second model's
    accuracy, the paired change with its 95% interval and exact McNemar p and, with one question per request, each
    question's wait (the decision model's request, plus the second model's for a question passed on); returns a line
    per mismatch."""
    questions = answers["questions"]
    exported = {run["run"]: run for run in answers["runs"] + answers.get("pipeline_runs", [])}
    runs = {run["run"]: run for run in results["runs"]}
    order = sorted(scored, key=lambda index: questions["id"][index])
    mismatches: list[str] = []

    def check(what: str, published: Any, recomputed: Any, kind: str = "exact") -> None:
        if kind == "exact":
            cell = checks.cell(published == recomputed, str(recomputed), str(published))
        elif kind == "p":
            cell = checks.cell(close(published, recomputed, relative=P_TOLERANCE), number(recomputed, 6), number(published, 6))
        else:
            cell = checks.cell(close(published, recomputed, METRIC_TOLERANCE), number(recomputed, 6), number(published, 6))
        if "≠" in cell:
            mismatches.append(f"  {what}: {cell}")

    for item in results["pipelines"]:
        measured = item.get("measured")
        if not measured:
            continue
        decision, pipeline, alone = (exported[run] for run in (item["decision"], measured["pipeline_run"], measured["alone_run"]))
        name = (f"live test {label(runs[item['decision']])} → {label(runs[item['frontier']])} "
                f"({item['rule']}, {item['batch_size']} per request)")
        held = [index for index in order if alone["correct"][index] is not None]
        passed = {index for index in order if pipeline["correct"][index] is not None}
        kept = [index for index in held if index not in passed]
        check(f"{name}, questions", item["held_out"], len(held))
        check(f"{name}, kept", item["routed"], len(kept))
        check(f"{name}, passed on below the cutoff", True, passed <= set(held)
              and all(decision["score"][index] >= item["threshold"] for index in kept)
              and all(decision["score"][index] < item["threshold"] for index in passed))
        together = [int(bool((pipeline if index in passed else decision)["correct"][index])) for index in held]
        by_itself = [int(bool(alone["correct"][index])) for index in held]
        test = bm.paired_comparison(together, by_itself)
        check(f"{name}, accuracy", measured["accuracy"], sum(together) / len(held), "metric")
        check(f"{name}, second model alone", measured["frontier_accuracy"], sum(by_itself) / len(held), "metric")
        for key in ("difference", "low", "high"):
            check(f"{name}, {key}", measured[key], test[key], "metric")
        check(f"{name}, p", measured["p"], test["p"], "p")
        if "waits" not in measured:
            continue
        first, then, own = decision["request_seconds"], pipeline["request_seconds"], alone["request_seconds"]
        waits = {index: first[index] + (then[index] if index in passed else 0.0) for index in held}
        for part, values in (
            ("pipeline", [waits[index] for index in held]),
            ("kept", [waits[index] for index in kept]),
            ("passed", [waits[index] for index in held if index in passed]),
            ("alone", [own[index] for index in held]),
        ):
            published = measured["waits"][part]
            check(f"{name}, {part} waits", published["questions"], len(values))
            for key, value in (
                ("median_seconds", statistics.median(values)),
                ("p90_seconds", statistics.quantiles(values, n=10, method="inclusive")[-1] if len(values) >= 2 else None),
                ("mean_seconds", statistics.fmean(values)),
                ("max_seconds", max(values)),
                ("total_seconds", sum(values)),
            ):
                check(f"{name}, {part} {key.replace('_', ' ')}", published[key], value, "metric")
    return mismatches


# The cost basis results.json gives a priced run, by billing, and the price's applies_to it needs.
COST_BASES = {"api": ("api", "billed"), "subscription": ("subscription", "billed"), "free": ("free tier", "free tier"),
              "local": ("maker", "maker")}


def check_costs(results: dict[str, Any], checks: Checks) -> list[str]:
    """Check every cost results.json publishes against its parts; returns a line per mismatch."""
    prices = {(price["provider"], price["model"]): price for price in results["prices"]}
    runs = {run["run"]: run for run in results["runs"]}
    mismatches: list[str] = []

    def check(what: str, published: float | None, recomputed: float | None) -> None:
        cell = checks.cell(close(published, recomputed, relative=COST_TOLERANCE), number(recomputed, 6), number(published, 6))
        if "≠" in cell:
            mismatches.append(f"  {what}: {cell}")

    def tokens(record: dict[str, Any]) -> dict[str, int]:
        return {kind: record[kind] for kind in ("input_tokens", *CACHE_KINDS, "output_tokens")}

    def per_thousand(run: dict[str, Any]) -> float | None:
        cost = run["api_equivalent_usd"]
        return None if cost is None else 1000 * cost / run["answered_questions"]

    for run in results["runs"]:
        price = prices.get((run["provider"], run["model"]))
        if price is None:
            # A run without a price must say why: our own GPUs, and no maker's price for the same model.
            matched = run["api_equivalent_usd"] is None and run["billing"] == "local" and run["cost_basis"] is None
            cell = checks.cell(matched, "no price (local)", f"{run['api_equivalent_usd']} ({run['billing']}, {run['cost_basis']})")
            if "≠" in cell:
                mismatches.append(f"  run {run['run']} ({label(run)}): {cell}")
            continue
        basis, applies = COST_BASES[run["billing"]]
        cell = checks.cell(
            (run["cost_basis"], price.get("applies_to", "billed")) == (basis, applies),
            f"{basis} ({applies})",
            f"{run['cost_basis']} ({price.get('applies_to')})",
        )
        if "≠" in cell:
            mismatches.append(f"  run {run['run']} ({label(run)}), cost basis: {cell}")
        # The input tokens the provider bills per request beyond our count, as the price states.
        billed = tokens(run)
        billed["input_tokens"] += price.get("extra_input_per_request", 0) * (run["requests"] or 0)
        check(f"run {run['run']} ({label(run)})", run["api_equivalent_usd"], token_cost(billed, price["rates"]))
    for item in results["cascades"]:
        first, frontier = runs[item["decision"]], runs[item["frontier"]]
        frontier_cost = per_thousand(frontier)
        recomputed = (
            None if frontier_cost is None else (per_thousand(first) or 0.0) + frontier_cost * (1 - item["held_out"]["answered"])
        )
        check(f"routing {label(first)} → {label(frontier)}", item["usd_per_1000"], recomputed)
    for item in results["pipelines"]:
        measured = item.get("measured")
        if not measured:
            continue
        decision, frontier = runs[item["decision"]], runs[item["frontier"]]
        rates = prices[(frontier["provider"], frontier["model"])]["rates"]
        name = f"routing test {label(decision)} → {label(frontier)}"
        share = decision["api_equivalent_usd"] * item["held_out"] / decision["answered_questions"]
        check(f"{name}, decision model's share", measured["decision_cost_usd"], share)
        check(f"{name}, pipeline", measured["cost_usd"], share + token_cost(measured["pipeline_tokens"], rates))
        check(f"{name}, frontier alone", measured["frontier_cost_usd"], token_cost(measured["alone_tokens"], rates))
        for alternative in measured["alternatives"]:
            check(
                f"{name}, {alternative['name']} alone",
                alternative["cost_usd"],
                token_cost(alternative["tokens"], prices[(alternative["provider"], alternative["model"])]["rates"]),
            )
    return mismatches


if __name__ == "__main__":
    sys.exit(main())
