#!/usr/bin/env python3
"""Recompute the published numbers from answers.json and check them against results.json.

    python3 reproduce.py [--docs FOLDER] [--report BENCHMARK_RESULTS_MD]

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
replay's cost per 1,000 questions from its runs, and the routing tests' costs from their parts. After the
page-image track, the "I don't know" option (`dont_know`): each model's counts, rates and mean probability of the
option from its runs' answers (dont_know_runs), their range and changed answers, and the derived abstention from its
original run. Then the English reading track (`english_reading`): the English prompts and their version, every
English run's translations and kept questions (english-reading.json), each model's English runs and Text tab runs,
both sides' counts on the kept questions, their difference, ranges and changed answers, and the paired test with
Holm's correction. Then the English reading track with the "I don't know" option (`english_reading.dont_know`): its
prompts and their version, every run's prompt version and kept questions, each model's English runs with the option
and its Turkish runs with the option (on the kept questions, or its full-bank runs counted on them), both sides' counts,
rates and mean probability of the option, their ranges, and the paired test of wrong answers with Holm's correction.
Then the option-word check (`dont_know_option_word`): its prompts and their version, every run's setup and prompt
version, each model's counts, rates and mean probability of the option with "Bilmiyorum" and with "I don't know",
and the paired test of wrong answers with Holm's correction. Then the hosted GLiDE rerun (`hosted_glide_rerun`): its
setup and prompt version, its counts, and the derived abstention and comparison with confidence redone with it as
the original run. Then the four models of Ümit's English "I don't know" comparison (`dont_know_english_option`): their
counts and paired tests from the first runs, with Holm's correction over the four. Then the confidence cut-off against
the option written "I don't know" (`dont_know_option_word.vs_confidence`): each option-word run's target attempt rate,
its five-option run's derived cut-off with the neighbouring cut-offs and their answered counts, the achieved counts,
the paired test of wrong answers and Holm's correction over the eligible family. Then Turkish and English coverage and
risk on the kept reading questions (`english_reading.coverage`): every native abstention point and every point of every
confidence curve. Then "I don't know" in both languages (`english_reading.dont_know_word`): per English reading model
the English first run with the option and the Turkish option-word run on the kept questions, their counts, rates and
mean probability of the option, and where both exist the paired test of wrong answers with Holm's correction over
those models. Then the same number of answers (`dont_know_same_answers`, Turkish: every main run; English: the
English reading models): k from the reference's run with "I don't know", each model's wrong answers among exactly its
first k (equal scores by question id), the difference from the reference with its paired bootstrap interval, p
and Holm's p (the published seed and resamples), every entry's answers in the selection order (wrong_by_rank) and the
runs with the option of each Hallucination tab and English model. Then Perplexity's web grounding test (`web_grounding`):
each pair's runs (grounding off and on: the 200-question sample, with "Bilmiyorum", and in English), their right answers,
accuracy, median and 95th-percentile request time and cost overall and by group, the paired counts and tests, the
repeats of the full bank's and the English pair's first runs (each repeat's runs, paired counts and source checks, and
each arm's mean with its lowest and highest run), the "Bilmiyorum" counts, the source checks' right answers, and the
tokens, sources and PWS-Decisions' aggregates of web-grounding.json.
Last the footer date (`updated`, when results with this content first went out): never older than a published run's
date, and with --report never older than the newest
`updated` of the runs answers.json publishes. Uses only the standard library and benchmark_metrics.py, the metric code
the benchmark report uses. Exits with status 1 when anything differs beyond the tolerances printed.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

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
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="the benchmark report (benchmark-results.md), to check the footer date exactly (default: only its lower bound)",
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
        f"\nGrading (every repeat, routing-test, request-size, \"I don't know\" and English run, each answer against answer key version "
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

    before = checks.passed + checks.failed
    vision_mismatches = check_vision(args.docs, answers, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nPage-image track (vision.json: each condition's right answers, ECE, Brier score, AUROC and answers at 0.99 from "
        f"its answers, condition A against answers.json, each paired test's counts and exact McNemar p, and the stored "
        f"answers, refusals, continued cells and runs, the requests' lower bound, the full leak scan's coverage and each "
        f"engine check's right answers, paired test and differing picks; vision-repeats.json: each repeat pass's right "
        f"answers and its picks and option probabilities against the table's cell): "
        f"{checked - len(vision_mismatches)} of {checked} match"
    )
    for line in vision_mismatches:
        print(line)

    before = checks.passed + checks.failed
    dont_know_mismatches = check_dont_know(args.docs, results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    models = len((results.get("dont_know") or {}).get("models", []))
    print(
        f"\nHallucination tab ({models} model{'' if models == 1 else 's'}, from their runs' exported "
        f"answers: counts exact, rates, mean probabilities and the derived abstention within {METRIC_TOLERANCE:g}): "
        f"{checked - len(dont_know_mismatches)} of {checked} match"
    )
    for line in dont_know_mismatches:
        print(line)

    before = checks.passed + checks.failed
    option_word_mismatches = check_option_word(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    models = len((results.get("dont_know_option_word") or {}).get("models", []))
    print(
        f"\nOption word, \"I don't know\" instead of \"Bilmiyorum\" ({models} model{'' if models == 1 else 's'}, from both runs' "
        f"exported answers: counts exact, rates and mean probabilities within {METRIC_TOLERANCE:g}, p-values within a "
        f"relative {P_TOLERANCE:g}): {checked - len(option_word_mismatches)} of {checked} match"
    )
    for line in option_word_mismatches:
        print(line)

    before = checks.passed + checks.failed
    rerun_mismatches = check_rerun(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nHosted GLiDE rerun (from its and the \"I don't know\" run's exported answers: counts exact, rates and the cut-off "
        f"within {METRIC_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}): {checked - len(rerun_mismatches)} of {checked} match"
    )
    for line in rerun_mismatches:
        print(line)

    before = checks.passed + checks.failed
    english_mismatches = check_english_reading(args.docs, results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    models = len((results.get("english_reading") or {}).get("models", []))
    print(
        f"\nEnglish reading ({models} model{'' if models == 1 else 's'}, from their English runs' and Text tab runs' exported "
        f"answers on english-reading.json's kept questions: counts exact, accuracies, differences and ranges within "
        f"{METRIC_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}): {checked - len(english_mismatches)} of {checked} match"
    )
    for line in english_mismatches:
        print(line)

    before = checks.passed + checks.failed
    tests_by_text_run: dict[int, dict[str, Any]] = {}
    english_dont_know_mismatches = check_english_dont_know(args.docs, results, answers, scored, checks, tests_by_text_run)
    checked = checks.passed + checks.failed - before
    english_idk = (results.get("english_reading") or {}).get("dont_know") or {}
    models, alone = len(english_idk.get("models", [])), len(english_idk.get("english_only", []))
    print(
        f"\nEnglish reading with \"I don't know\" ({models} model{'' if models == 1 else 's'}"
        f"{f' and {alone} in English only' if alone else ''}, from their English and Turkish "
        f"runs' exported answers on english-reading.json's kept questions: counts exact, rates, mean probabilities and "
        f"ranges within {METRIC_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}): "
        f"{checked - len(english_dont_know_mismatches)} of {checked} match"
    )
    for line in english_dont_know_mismatches:
        print(line)

    before = checks.passed + checks.failed
    four_mismatches = check_english_option_four(results, tests_by_text_run, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nEnglish \"I don't know\", the four models of Ümit's request with Holm's correction over the four (from the first "
        f"runs' exported answers: counts exact, p-values within a relative {P_TOLERANCE:g}): "
        f"{checked - len(four_mismatches)} of {checked} match"
    )
    for line in four_mismatches:
        print(line)

    before = checks.passed + checks.failed
    vs_mismatches = check_vs_confidence(results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nConfidence cut-off against the option written \"I don't know\" (from the option-word and five-option runs' "
        f"exported answers: counts exact, cut-offs and rates within {METRIC_TOLERANCE:g}, p-values within a relative "
        f"{P_TOLERANCE:g}): {checked - len(vs_mismatches)} of {checked} match"
    )
    for line in vs_mismatches:
        print(line)

    before = checks.passed + checks.failed
    coverage_mismatches = check_coverage(args.docs, results, answers, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nTurkish and English coverage and risk on the kept reading questions (native points and every curve point, from "
        f"the runs' exported answers: counts exact, coverage and risk within {METRIC_TOLERANCE:g}): "
        f"{checked - len(coverage_mismatches)} of {checked} match"
    )
    for line in coverage_mismatches:
        print(line)

    before = checks.passed + checks.failed
    word_mismatches = check_dont_know_word(args.docs, results, answers, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\n\"I don't know\" in both languages on the kept reading questions (the English first run with the option and "
        f"the Turkish option-word run, from their exported answers: counts exact, rates and mean probabilities within "
        f"{METRIC_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}, Holm over the models with both): "
        f"{checked - len(word_mismatches)} of {checked} match"
    )
    for line in word_mismatches:
        print(line)

    before = checks.passed + checks.failed
    same_mismatches = check_same_answers(args.docs, results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nThe same number of answers (exactly k answers per model, equal scores by question id, from the five-option "
        f"and option runs' exported answers: k, wrong answers, differences, wrong_by_rank and option points exact, "
        f"bootstrap p and Holm's p within a relative {P_TOLERANCE:g}, intervals within {INTERVAL_TOLERANCE:g}): "
        f"{checked - len(same_mismatches)} of {checked} match"
    )
    for line in same_mismatches:
        print(line)

    before = checks.passed + checks.failed
    high_mismatches = check_high_confidence(args.docs, results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nAnswers at 95%+ confidence (every main run, d1-ultra's repeats, the three models' runs at each cutoff, the check "
        f"over every whole percent to 98% and d1-ultra's English runs, from their exported answers: counts exact): "
        f"{checked - len(high_mismatches)} of {checked} match"
    )
    for line in high_mismatches:
        print(line)

    before = checks.passed + checks.failed
    against_mismatches = check_against_reference(args.docs, results, answers, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nLiquid d1-ultra against each model in English (first English runs on the kept questions: counts exact, p and "
        f"Holm's p within a relative {P_TOLERANCE:g}): {checked - len(against_mismatches)} of {checked} match"
    )
    for line in against_mismatches:
        print(line)

    before = checks.passed + checks.failed
    grounding_mismatches = check_web_grounding(args.docs, results, answers, scored, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nPerplexity web grounding (each pair's runs from their exported answers, tokens, sources and PWS-Decisions' "
        f"aggregates from web-grounding.json: counts exact, rates and request times within {METRIC_TOLERANCE:g}, costs "
        f"within a relative {COST_TOLERANCE:g}, p-values within a relative {P_TOLERANCE:g}): "
        f"{checked - len(grounding_mismatches)} of {checked} match"
    )
    for line in grounding_mismatches:
        print(line)

    before = checks.passed + checks.failed
    updated_mismatches = check_updated(args.report, results, answers, checks)
    checked = checks.passed + checks.failed - before
    print(
        f"\nFooter date {results['updated']} ({'lower bound from the report' if args.report else 'lower bound from results.json; --report for every published run'}): "
        f"{checked - len(updated_mismatches)} of {checked} match"
    )
    for line in updated_mismatches:
        print(line)

    print(f"\n{checks.passed} checks match, {checks.failed} differ")
    return 1 if checks.failed else 0


def check_vision(docs: Path, answers: dict[str, Any], checks: Checks) -> list[str]:
    """Recompute vision.json's per-condition numbers from its answers (pick, option probabilities, right or not): right
    answers exactly; ECE, Brier score and AUROC within METRIC_TOLERANCE; the answers at SURE_SCORE or more, right and
    wrong, exactly. Condition A's answers must be its run's in answers.json, and each paired test's counts and exact
    McNemar p must follow from the two conditions' answers. The bootstrap intervals are not recomputed. Returns a line
    per condition or pair that differs."""
    path = docs / "vision.json"
    if not path.exists():
        return []
    vision = json.loads(path.read_text(encoding="utf-8"))
    ids = vision["subset"]["question_ids"]
    position = {question_id: index for index, question_id in enumerate(answers["questions"]["id"])}
    runs = {run["run"]: run for run in answers["runs"]}
    mismatches = []
    for model in vision["models"]:
        rights: dict[str, list[int]] = {}
        for label, published in model["conditions"].items():
            given = vision["answers"][f"{model['provider']}|{model['model']}|{label}"]
            right = [int(given[str(question_id)][2]) for question_id in ids]
            rights[label] = right
            scored = []
            for question_id in ids:
                choice, probabilities, correct = given[str(question_id)]
                if choice is not None and choice in probabilities:
                    scored.append((probabilities[choice], int(correct)))
            calibration = bm.calibration(scored)
            sure = [correct for score, correct in scored if score >= bm.SURE_SCORE]
            cells = [
                checks.cell(sum(right) == published["correct"], f"{sum(right)} right", str(published["correct"])),
                checks.metric(published["ece"], calibration["ece"]),
                checks.metric(published["brier"], calibration["brier"]),
                checks.metric(published["auroc"], bm.auroc(scored)),
                checks.cell([len(sure), sum(sure)] == [published["at_0_99"]["answers"], published["at_0_99"]["right"]],
                            f"{len(sure)} at 0.99, {sum(sure)} right",
                            f"{published['at_0_99']['answers']}, {published['at_0_99']['right']} right"),
            ]
            # Condition A against its run in answers.json, for the runs the text results hold; a run not on the text
            # leaderboard is checked from vision.json alone.
            run = runs.get(model["a_run"]) if label == "A" else None
            if run is not None:
                same = all(int(run["correct"][position[question_id]]) == value for question_id, value in zip(ids, right))
                cells.append(checks.cell(same, "A as in answers.json", f"run {model['a_run']} in answers.json"))
            if any("≠" in cell for cell in cells):
                mismatches.append(f"  {model['name']} {label}: " + ", ".join(cells))
        for item in model["paired"]:
            test = bm.paired_comparison(rights[item["first"]], rights[item["second"]])
            published = item["accuracy"]
            cells = [
                checks.cell([test["first_only"], test["second_only"]] == [published["first_only"], published["second_only"]],
                            f"{test['first_only']} / {test['second_only']}", f"{published['first_only']} / {published['second_only']}"),
                checks.cell(close(published["mcnemar_p"], test["p"], relative=P_TOLERANCE), f"p {test['p']:.3g}",
                            f"p {published['mcnemar_p']:.3g}"),
            ]
            if any("≠" in cell for cell in cells):
                mismatches.append(f"  {model['name']} {item['first']} vs {item['second']}: " + ", ".join(cells))
    mismatches += check_vision_requests(vision, checks)
    mismatches += check_vision_engines(vision, checks)
    mismatches += check_vision_repeats(docs, vision, checks)
    return mismatches


def check_vision_repeats(docs: Path, vision: dict[str, Any], checks: Checks) -> list[str]:
    """vision-repeats.json against vision.json: each cell's first pass is the table's (its runs and right answers), and
    each repeat pass covers the subset, has the right answers its answers give, and differs from the table's answers in
    the picks, option-probability sets and largest probability difference it states. Returns a line per pass that
    differs."""
    path = docs / "vision-repeats.json"
    if not path.exists():
        return []
    repeats = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(question_id) for question_id in vision["subset"]["question_ids"]]
    mismatches = []
    for cell in repeats["cells"]:
        model = next(item for item in vision["models"] if item["provider"] == cell["provider"] and item["model"] == cell["model"])
        table = model["conditions"][cell["condition"]]
        first = vision["answers"][f"{cell['provider']}|{cell['model']}|{cell['condition']}"]
        same = cell["first_pass"]["runs"] == table["runs"] and cell["first_pass"]["right"] == table["correct"]
        first_pass = checks.cell(same, f"runs {table['runs']}, {table['correct']} right",
                                 f"runs {cell['first_pass']['runs']}, {cell['first_pass']['right']} right")
        if "≠" in first_pass:
            mismatches.append(f"  {cell['name']} {cell['condition']} first pass: {first_pass}")
        for passed in cell["passes"]:
            given = passed["answers"]
            covers = sorted(given) == sorted(ids)
            right = sum(int(given[qid][2]) for qid in ids if qid in given)
            picks = sum(given[qid][0] != first[qid][0] for qid in ids if qid in given)
            sets = sum(given[qid][1] != first[qid][1] for qid in ids if qid in given)
            largest = max((abs(given[qid][1].get(label, 0.0) - value) for qid in ids if qid in given
                           for label, value in first[qid][1].items()), default=0.0)
            cells = [
                checks.cell(covers, f"{len(given)} questions", f"{len(ids)}"),
                checks.cell(right == passed["right"], f"{right} right", str(passed["right"])),
                checks.cell([picks, sets] == [passed["picks_differ"], passed["probabilities_differ"]],
                            f"{picks} picks, {sets} sets differ", f"{passed['picks_differ']}, {passed['probabilities_differ']}"),
                checks.metric(passed["largest_difference"], largest),
            ]
            if any("≠" in item for item in cells):
                mismatches.append(f"  {cell['name']} {cell['condition']} pass {passed['pass']}: " + ", ".join(cells))
    return mismatches


def check_vision_engines(vision: dict[str, Any], checks: Checks) -> list[str]:
    """Each engine check of vision.json against its own answers: the check's answers cover every subset question, its
    right answers are theirs, the table run's right answers are those of the condition's answers in vision.json, and
    the paired counts, exact McNemar p and the picks that differ follow from the two answer sets (first: the check,
    second: the table's run). Returns a line per check that differs."""
    ids = vision["subset"]["question_ids"]
    mismatches = []
    for item in vision.get("engine_checks", []):
        given = item["answers"]
        table = vision["answers"][f"{item['row']['provider']}|{item['model']}|{item['condition']}"]
        covered = sorted(given, key=int) == sorted((str(question_id) for question_id in ids), key=int)
        cells = [checks.cell(covered and len(given) == len(ids), f"{len(given)} answers", f"{len(ids)} subset questions")]
        if covered:
            first = [int(given[str(question_id)][2]) for question_id in ids]
            second = [int(table[str(question_id)][2]) for question_id in ids]
            test = bm.paired_comparison(first, second)
            paired = item["paired"]
            differ = sum(1 for question_id in ids if given[str(question_id)][0] != table[str(question_id)][0])
            cells += [
                checks.cell(sum(first) == item["check"]["correct"], f"check {sum(first)} right", str(item["check"]["correct"])),
                checks.cell(sum(second) == item["row"]["correct"], f"table run {sum(second)} right", str(item["row"]["correct"])),
                checks.cell([test["first_only"], test["second_only"]] == [paired["first_only"], paired["second_only"]],
                            f"{test['first_only']} / {test['second_only']}", f"{paired['first_only']} / {paired['second_only']}"),
                checks.cell(close(paired["p"], test["p"], relative=P_TOLERANCE), f"p {test['p']:.3g}", f"p {paired['p']:.3g}"),
                checks.cell(differ == item["picks_differ"], f"{differ} picks differ", str(item["picks_differ"])),
            ]
        if any("≠" in cell for cell in cells):
            mismatches.append(f"  engine check {item['name']} {item['condition']}: " + ", ".join(cells))
    return mismatches


def check_vision_requests(vision: dict[str, Any], checks: Checks) -> list[str]:
    """vision.json's requests and full leak scan against its own stored answers: one stored answer per question in each
    cell besides A (requests.retained_answers), split into answers that name an option and refusals (an answer without
    an option of its own probabilities); the continued cells exactly the cells whose condition lists two runs; the runs
    those cells name; the lower bound on requests sent, the stored answers plus the logs' retries; and a full scan of
    every OCR model's output for every crop, none missing or extra. Returns a line per check that differs."""
    requests = vision["requests"]
    ids = vision["subset"]["question_ids"]
    cells = [(model, label) for model in vision["models"] for label in model["conditions"] if label != "A"]
    stored = [vision["answers"][f"{model['provider']}|{model['model']}|{label}"] for model, label in cells]
    given = [answer[str(question_id)] for answer in stored for question_id in ids]
    valid = sum(1 for choice, probabilities, _ in given if choice is not None and choice in probabilities)
    extra = sum(len(answer) for answer in stored) - len(given)
    continued = sorted((f"{model['name']} {label}", list(model["conditions"][label]["runs"])) for model, label in cells
                       if len(model["conditions"][label].get("runs", [])) == 2)
    named = sorted((item["cell"], list(item["runs"])) for item in requests["continued_cells"])
    runs = {run for model, label in cells for run in model["conditions"][label].get("runs", [])}
    retries = requests["recorded_client_retries"]
    scan = vision["crops"]["leak_check"]["full_scan"]
    inventories = scan["inventories"]
    crops = vision["crops"]["images"]
    lines = {
        "retained answers": checks.cell(requests["retained_answers"] == len(ids) * len(cells) == len(given) and not extra,
                                        f"{len(ids)} × {len(cells)} cells = {len(given)} stored", str(requests["retained_answers"])),
        "cells": checks.cell(requests["cells"] == len(cells), f"{len(cells)} cells", str(requests["cells"])),
        "valid and refusals": checks.cell([requests["valid_choices"], requests["refusals"]] == [valid, len(given) - valid]
                                          and requests["valid_choices"] + requests["refusals"] == requests["retained_answers"],
                                          f"{valid} valid, {len(given) - valid} refusals",
                                          f"{requests['valid_choices']} valid, {requests['refusals']} refusals"),
        "continued cells": checks.cell(continued == named, f"{len(continued)} cells with two runs", f"{len(named)} listed"),
        "runs": checks.cell(requests["runs"] == len(runs), f"{len(runs)} runs", str(requests["runs"])),
        "lower bound": checks.cell(requests["requests_lower_bound"] == requests["retained_answers"] + retries["total"]
                                   and retries["total"] == sum(retries["by_run"].values()),
                                   f"{requests['retained_answers']} + {retries['total']} retries", str(requests["requests_lower_bound"])),
        "full scan": checks.cell(scan["complete"] and sorted(inventories) == sorted(vision["ocr"]["models"])
                                 and all(item["outputs"] == crops and not item["missing"] and not item["extra"] for item in inventories.values())
                                 and sum(item["outputs"] for item in inventories.values()) == len(vision["ocr"]["models"]) * crops,
                                 f"{len(vision['ocr']['models'])} × {crops} outputs",
                                 f"{sum(item['outputs'] for item in inventories.values())} scanned"),
        "scan hits": checks.cell(scan["key_text_hits"] + scan["lone_pair_hits"] == len(scan["hits"])
                                 and scan["lone_pair_hits"] == sum(hit["kind"] == "lone pair" for hit in scan["hits"]),
                                 f"{len(scan['hits'])} hits", f"{scan['key_text_hits']} key text, {scan['lone_pair_hits']} lone pairs"),
    }
    return [f"  requests, {name}: {cell}" for name, cell in lines.items() if "≠" in cell]


def check_grading(answers: dict[str, Any], keys: list[str | None], scored: list[int], checks: Checks) -> list[str]:
    """Check that every exported run besides the main ones (the main ones are checked with their accuracy) is graded on
    the published key: each answer it gave on a scored question is correct exactly when its option is the key's.
    Returns a line per run that differs."""
    mismatches = []
    for run in (answers.get("repeat_runs", []) + answers.get("pipeline_runs", []) + answers.get("batching_runs", [])
                + answers.get("dont_know_runs", []) + answers.get("english_runs", []) + answers.get("english_dont_know_runs", [])
                + answers.get("english_dont_know_turkish_runs", []) + answers.get("dont_know_word_runs", [])
                + answers.get("rerun_runs", []) + answers.get("web_grounding_runs", [])):
        given = [index for index in scored if run["correct"][index] is not None and keys[index] is not None]
        differ = sum(1 for index in given if int(run["choice"][index] == keys[index]) != int(run["correct"][index]))
        if "≠" in checks.cell(not differ, f"{len(given)} answers", f"{differ} not from the key"):
            mismatches.append(f"  run {run['run']} ({label(run)}): {differ} of {len(given)} answers are not graded on the key")
    return mismatches


# The "I don't know" option's letter: it follows each question's five options (DONT_KNOW_OPTION in benchmark_ollama.py).
DONT_KNOW_LETTER = "F"


def derived_abstention(answers: list[tuple[float | None, int]], target: float) -> dict[str, Any]:
    """Answer only where the score reaches the cut-off whose attempt rate comes nearest `target` (the higher cut-off on a
    tie; an answer without a score is never an attempt) and abstain on the rest; `answers` holds (score, correct)."""
    total = len(answers)
    ranked = sorted((score for score, _ in answers if score is not None), reverse=True)
    best: tuple[float, float | None] = (target, None)
    for index, score in enumerate(ranked):
        if index + 1 < len(ranked) and ranked[index + 1] == score:
            continue
        distance = abs((index + 1) / total - target)
        if distance < best[0]:
            best = (distance, score)
    cut_off = best[1]
    attempted = [right for score, right in answers if cut_off is not None and score is not None and score >= cut_off]
    right, wrong = sum(attempted), len(attempted) - sum(attempted)
    abstained = total - len(attempted)
    return {
        "cut_off": cut_off,
        "right": right,
        "wrong": wrong,
        "abstained": abstained,
        "attempt_rate": len(attempted) / total,
        "non_hallucination": abstained / (abstained + wrong) if abstained + wrong else None,
    }


# The runner's providers asked with the System One instructions (DECISION_PROVIDERS in benchmark_ollama.py): those of
# page_config.json's decision_model_providers and vLLM's yes/no scoring; every other provider is asked with the chat
# prompts.
SYSTEM_ONE_EXTRA = ("vllm-yes-no",)


def system_one(docs: Path, provider: str) -> bool:
    """Whether the runner asks a provider with the System One instructions (decision prompts), not the chat prompts."""
    config = json.loads((docs / "page_config.json").read_text(encoding="utf-8"))
    return provider in config["decision_model_providers"] or provider in SYSTEM_ONE_EXTRA


def group_of(docs: Path, provider: str, model: str) -> str:
    """A setup's view bar group by page_config.json's rule (Site.decision): "decision" when its provider is one of
    decision_model_providers and its model not one of not_decision_models, else "chat"."""
    config = json.loads((docs / "page_config.json").read_text(encoding="utf-8"))
    decision = provider in config["decision_model_providers"] and model not in config["not_decision_models"]
    return "decision" if decision else "chat"


def check_chat_prompts(published: dict[str, Any] | None, prompts: dict[str, Any] | None, base: dict[str, Any], option: str,
                       check: Callable[[str, Any, Any], None]) -> str | None:
    """Check a section's chat prompts with the "I don't know" option (`chat`) against answers.json's (`prompts`): the
    option, each instruction the five-option chat prompts' (`base`) plus the sentence, each system prompt the base
    one, and the published sentence, confidence system prompt and instruction and version (the prompts hashed).
    Returns that version, or None without such prompts."""
    if prompts is None:
        check("chat prompts", published, None)
        return None
    sentence = prompts.get("dont_know_sentence")
    check("chat option", prompts.get("dont_know_option"), option)
    for field in ("answer_instruction", "confidence_instruction", "verbal_instruction"):
        check(f"chat {field}", prompts.get(field), f"{base.get(field)} {sentence}")
    for field in ("answer_system", "confidence_system", "verbal_system"):
        check(f"chat {field}", prompts.get(field), base.get(field))
    version = hashed(prompts)
    check("chat prompts", published, {"sentence": sentence, "confidence_system": prompts.get("confidence_system"),
                                      "confidence_instruction": prompts.get("confidence_instruction"), "prompt_version": version})
    return version


def check_dont_know(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute results.json's `dont_know` from answers.json's `dont_know_runs` on the scored questions: each model's
    group (group_of), right, wrong, "Bilmiyorum" (the letter DONT_KNOW_LETTER, which must be the last label of every
    answer's option probabilities) and invalid answers, accuracy, attempt rate, non-hallucination rate and mean
    probability of the option, from its first run; the range of the rates over its runs and the answers that differ
    between them; a chat model's original run, the main run of its setup (provider, model, reasoning, questions per
    request, Perplexity mode); its original run's accuracy; the derived abstention on that run at the first run's attempt
    rate; and for a decision model the first run against the original run held back at that cut-off, as wrong answers in
    each (exact McNemar, Holm over the decision models that chose the option on at least vs_confidence_share of the
    questions; none for a chat model). The prompts: the decision models' version (dont_know_prompts hashed) and the chat
    models' prompts (check_chat_prompts), each run with its kind's version (a run that reports option probabilities
    answered with the System One instructions, any other with the chat prompts). Every run must be listed once and in
    no other list. Returns a line per model that differs."""
    section = results.get("dont_know")
    runs = {run["run"]: run for run in answers.get("dont_know_runs", [])}
    listed = [run_id for model in (section or {}).get("models", []) for run_id in model["runs"]]
    others = {run["run"] for key in ("runs", "repeat_runs", "pipeline_runs", "batching_runs", "english_runs",
                                     "english_dont_know_runs", "english_dont_know_turkish_runs", "dont_know_word_runs",
                                     "rerun_runs", "web_grounding_runs") for run in answers.get(key, [])}
    if sorted(listed) != sorted(runs) or set(listed) & others or (section is not None and section["questions"] != len(scored)):
        checks.failed += 1
        return [f"  runs: results.json lists {sorted(listed)}, answers.json's dont_know_runs {sorted(runs)}, also elsewhere "
                f"{sorted(set(listed) & others)}"]
    if section is None:
        return []
    main = {run["run"]: run for run in answers["runs"]}
    total = len(scored)
    rates = ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability")
    mismatches = []

    def check(name: str, published: Any, recomputed: Any) -> None:
        if "≠" in checks.cell(published == recomputed, f"{name} {recomputed}", str(published)):
            mismatches.append(f"  {name}: {published} against {recomputed}")

    prompts = answers.get("dont_know_prompts") or {}
    option = prompts.get("dont_know_option")
    sentence = f"If you do not know the answer, choose {option}."
    check("option", section["option"], option)
    check("sentence", section["sentence"], sentence)
    check("instructions", [section["instructions"], prompts.get("system_one_instructions")],
          [f"{answers['prompts']['system_one_instructions']} {sentence}"] * 2)
    check("prompt version", section["prompt_version"], hashed(prompts))
    chat_version = check_chat_prompts(section.get("chat"), answers.get("dont_know_chat_prompts"), answers["prompts"], option, check)
    for run_id, run in sorted(runs.items()):
        decision = system_one(docs, run["provider"])
        check(f"run {run_id} prompt version", run["prompt_version"], section["prompt_version"] if decision else chat_version)
    tests = []
    for model in section["models"]:
        cells = []
        found = []
        group = group_of(docs, model["provider"], model["model"])
        cells.append(checks.cell(model.get("group") == group, f"group {group}", str(model.get("group"))))
        for run_id in model["runs"]:
            run = runs[run_id]
            counts = {"right": 0, "wrong": 0, "dont_know": 0, "invalid": 0}
            shown, unlabelled = [], 0
            for index in scored:
                choice, probabilities = run["choice"][index], run["probabilities"][index]
                if probabilities:
                    last, value = option_last(run, probabilities)
                    unlabelled += not last
                    if value is not None:
                        shown.append(value)
                if choice is None:
                    counts["invalid"] += 1
                elif choice == DONT_KNOW_LETTER:
                    counts["dont_know"] += 1
                elif run["correct"][index]:
                    counts["right"] += 1
                else:
                    counts["wrong"] += 1
            cells.append(checks.cell(not unlabelled and run["repeat_set"] == model["runs"], f"run {run_id}",
                                     f"{unlabelled} answers without {DONT_KNOW_LETTER} last, repeat set {run['repeat_set']}"))
            found.append({
                **counts,
                "accuracy": counts["right"] / total,
                "attempt_rate": (counts["right"] + counts["wrong"]) / total,
                "non_hallucination": counts["dont_know"] / (counts["dont_know"] + counts["wrong"]) if counts["dont_know"] + counts["wrong"] else None,
                "mean_dont_know_probability": sum(shown) / len(shown) if shown else None,
            })
        first = found[0]
        cells += [checks.cell(first[key] == model[key], f"{key} {first[key]}", str(model[key])) for key in ("right", "wrong", "dont_know", "invalid")]
        cells += [checks.cell(close(model[key], first[key], METRIC_TOLERANCE), f"{key} {number(first[key])}", number(model[key])) for key in rates]
        if len(found) == 1:
            cells.append(checks.cell(model["spread"] is None and model["answers_changed"] is None, "one run", "a spread"))
        else:
            for key in rates:
                values = [item[key] for item in found]
                spread = None if None in values else [min(values), max(values)]
                published = model["spread"][key]
                matched = (spread is None) == (published is None) and all(close(a, b, METRIC_TOLERANCE) for a, b in zip(spread or [], published or []))
                cells.append(checks.cell(matched, f"{key} range {spread}", str(published)))
            choices = [runs[run_id]["choice"] for run_id in model["runs"]]
            changed = sum(1 for index in scored if all(choice[index] is not None for choice in choices)
                          and len({choice[index] for choice in choices}) > 1)
            cells.append(checks.cell(changed == model["answers_changed"], f"answers changed {changed}", str(model["answers_changed"])))
        if group == "chat":
            head = runs[model["runs"][0]]
            setup = [run["run"] for run in answers["runs"] if [run["provider"], run["model"], run["thinking"], run["questions_per_request"],
                                                               run.get("perplexity_mode")]
                     == [head["provider"], head["model"], head["thinking"], head["questions_per_request"], head.get("perplexity_mode")]]
            cells.append(checks.cell(setup == [model["original_run"]], f"the setup's main runs {setup}", str(model["original_run"])))
        original = main.get(model["original_run"])
        if original is None:
            checks.failed += 1
            mismatches.append(f"  {label(model)}: its original run {model['original_run']} is not a main run")
            continue
        accuracy = sum(int(original["correct"][index]) for index in scored) / total
        cells.append(checks.cell(close(model["original_accuracy"], accuracy, METRIC_TOLERANCE), f"original accuracy {number(accuracy)}", number(model["original_accuracy"])))
        derived = derived_abstention(
            [(None if original["score"][index] is None else float(original["score"][index]), int(original["correct"][index])) for index in scored],
            first["attempt_rate"],
        )
        for key, value in derived.items():
            published = model["derived"][key]
            matched = published == value if key in ("right", "wrong", "abstained") else close(published, value, METRIC_TOLERANCE)
            cells.append(checks.cell(matched, f"derived {key} {value}", str(published)))
        if group == "chat":
            cells.append(checks.cell(model.get("vs_confidence") is None, "no comparison with confidence", str(model.get("vs_confidence"))))
        else:
            first_run = runs[model["runs"][0]]
            option_wrong = [int(first_run["choice"][index] not in (None, DONT_KNOW_LETTER) and not first_run["correct"][index]) for index in scored]
            cut_off = derived["cut_off"]
            confidence_wrong = [int(cut_off is not None and original["score"][index] is not None and float(original["score"][index]) >= cut_off
                                    and not original["correct"][index]) for index in scored]
            test = bm.paired_comparison(option_wrong, confidence_wrong)
            published = model.get("vs_confidence") or {}
            counts = [test["first_only"], test["second_only"]]
            cells.append(checks.cell(counts == [published.get("option_only_wrong"), published.get("confidence_only_wrong")],
                                     f"wrong only with the option, only with confidence {counts}",
                                     str([published.get("option_only_wrong"), published.get("confidence_only_wrong")])))
            cells.append(checks.cell(published.get("p") is not None and close(published["p"], test["p"], METRIC_TOLERANCE), f"p {number(test['p'])}", str(published.get("p"))))
            tests.append((model, test))
        if any("≠" in cell for cell in cells):
            mismatches.append(f"  {label(model)}: " + ", ".join(cell for cell in cells if "≠" in cell))
    family = [(model, test) for model, test in tests if model["dont_know"] >= section["vs_confidence_share"] * total]
    adjusted = dict(zip((id(model) for model, _ in family), bm.holm([test["p"] for _, test in family])))
    for model, _ in tests:
        expected = adjusted.get(id(model))
        published = (model.get("vs_confidence") or {}).get("p_holm")
        matched = published is None if expected is None else published is not None and close(published, expected, METRIC_TOLERANCE)
        if "≠" in checks.cell(matched, f"{label(model)} p_holm {number(expected) if expected is not None else None}", str(published)):
            mismatches.append(f"  {label(model)}: Holm-adjusted p {expected} against {published}")
    return mismatches


def hashed(value: dict[str, Any]) -> str:
    """A prompt set's version, as the runner computes it: SHA-256 of its JSON with sorted keys, first 12 hex digits."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


# The runner's providers whose answer "probabilities" are vote shares (VOTE_PROVIDERS in benchmark_ollama.py): the share
# of the samples that chose each letter, listing only the letters some sample chose, in the order they were first sampled.
VOTE_PROVIDERS = ("vllm-vote",)


def option_last(run: dict[str, Any], probabilities: dict[str, float]) -> tuple[bool, float | None]:
    """For an answer's option probabilities in a run with the option: whether they fit the option lettered last
    (DONT_KNOW_LETTER the last label: a full distribution ends with it; vote shares name no letter after it) and the
    option's probability where the answer reports it (as the runner and the export average it)."""
    if run["provider"] in VOTE_PROVIDERS:
        return max(probabilities) <= DONT_KNOW_LETTER, probabilities.get(DONT_KNOW_LETTER)
    last = max(probabilities) == DONT_KNOW_LETTER
    return last, probabilities[DONT_KNOW_LETTER] if last else None


def counted_dont_know(run: dict[str, Any], scored: list[int]) -> dict[str, Any]:
    """A run with the "I don't know" option on the scored questions: right, wrong, option (DONT_KNOW_LETTER) and invalid
    answers, the rates, the mean probability of the option, the answers whose probabilities do not fit the option
    lettered last (`unlabelled`, option_last) and each question's wrong answer (`wrong_answers`)."""
    total = len(scored)
    counts = {"right": 0, "wrong": 0, "dont_know": 0, "invalid": 0}
    shown, unlabelled = [], 0
    for index in scored:
        choice, probabilities = run["choice"][index], run["probabilities"][index]
        if probabilities:
            last, value = option_last(run, probabilities)
            unlabelled += not last
            if value is not None:
                shown.append(value)
        if choice is None:
            counts["invalid"] += 1
        elif choice == DONT_KNOW_LETTER:
            counts["dont_know"] += 1
        elif run["correct"][index]:
            counts["right"] += 1
        else:
            counts["wrong"] += 1
    return {
        **counts,
        "accuracy": counts["right"] / total,
        "attempt_rate": (counts["right"] + counts["wrong"]) / total,
        "non_hallucination": counts["dont_know"] / (counts["dont_know"] + counts["wrong"]) if counts["dont_know"] + counts["wrong"] else None,
        "mean_dont_know_probability": sum(shown) / len(shown) if shown else None,
        "unlabelled": unlabelled,
        "wrong_answers": [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index]) for index in scored],
    }


def listed_elsewhere(answers: dict[str, Any], own: str) -> set[int]:
    """The runs of every answers.json list but `own`."""
    keys = ("runs", "repeat_runs", "pipeline_runs", "batching_runs", "dont_know_runs", "english_runs", "english_dont_know_runs",
            "english_dont_know_turkish_runs", "dont_know_word_runs", "rerun_runs", "web_grounding_runs")
    return {run["run"] for key in keys if key != own for run in answers.get(key, [])}


def check_option_word(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute results.json's `dont_know_option_word` from answers.json's `dont_know_word_runs` and `dont_know_runs`
    on the scored questions: the option ("I don't know"), its sentence, the instructions (the System One instructions
    plus the sentence) and the prompt version (dont_know_word_prompts hashed, the main prompts otherwise); the models,
    the Hallucination tab's decision models in its order with those in not_run left out; per model its Hallucination tab first run with
    "Bilmiyorum" and one run of the same setup with "I don't know" over every scored question, with their prompt versions,
    counts, rates and mean probability of the option, and the paired test of wrong answers (exact McNemar, first
    "Bilmiyorum") with Holm's correction over the models compared. Every option-word run must be listed once and in no
    other list. Returns a line per mismatch."""
    section = results.get("dont_know_option_word")
    runs = {run["run"]: run for run in answers.get("dont_know_word_runs", [])}
    listed = [model["i_dont_know"]["run"] for model in (section or {}).get("models", [])]
    elsewhere = set(listed) & listed_elsewhere(answers, "dont_know_word_runs")
    if sorted(listed) != sorted(runs) or len(set(listed)) != len(listed) or elsewhere:
        checks.failed += 1
        return [f"  runs: results.json lists {sorted(listed)}, answers.json's dont_know_word_runs {sorted(runs)}, also elsewhere "
                f"{sorted(elsewhere)}"]
    if section is None:
        return []
    checks.passed += 1
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    prompts = answers.get("dont_know_word_prompts") or {}
    option = prompts.get("dont_know_option")
    sentence = f"If you do not know the answer, choose {option}."
    version = hashed(prompts)
    check("option", section["option"], option)
    check("option is I don't know", "I don't know", option)
    check("sentence", section["sentence"], sentence)
    check("instructions", section["instructions"], f"{answers['prompts']['system_one_instructions']} {sentence}")
    check("instructions in dont_know_word_prompts", section["instructions"], prompts.get("system_one_instructions"))
    check("the other prompts", {key: value for key, value in answers["prompts"].items() if key != "system_one_instructions"},
          {key: value for key, value in prompts.items() if key not in ("system_one_instructions", "dont_know_option")})
    check("prompt version", section["prompt_version"], version)
    check("questions", section["questions"], len(scored))
    # The Hallucination tab's decision models (each row's group, checked by check_dont_know).
    rows = [row for row in (results.get("dont_know") or {}).get("models", []) if row["group"] == "decision"]
    skipped = [item["name"] for item in section["not_run"]]
    check("not run, all Hallucination tab models", True, set(skipped) <= {row["name"] for row in rows})
    expected = [row for row in rows if row["name"] not in skipped]
    check("models", [(row["name"], row["model"], row["provider"]) for row in expected],
          [(model["name"], model["model"], model["provider"]) for model in section["models"]])
    if len(expected) != len(section["models"]):
        return mismatches
    turkish = {run["run"]: run for run in answers.get("dont_know_runs", [])}
    keys = ("right", "wrong", "dont_know", "invalid")
    rates = ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability")
    tests = []
    for row, model in zip(expected, section["models"]):
        name = model["name"]
        check(f"{name}, Bilmiyorum run", model["bilmiyorum"]["run"], row["run"])
        first, second = turkish.get(row["run"]), runs[model["i_dont_know"]["run"]]
        if first is None:
            check(f"{name}, Bilmiyorum run in dont_know_runs", True, False)
            continue
        setup = ("provider", "model", "thinking", "questions_per_request")
        check(f"{name}, setup", [first[key] for key in setup], [second[key] for key in setup])
        check(f"{name}, I don't know run kind", [True, "english", None, None, None, None, None, len(scored)],
              [bool(second.get("dont_know")), second.get("dont_know_word"), second.get("english"), second.get("rerun"),
               second.get("repeat"), second.get("question_list"), second.get("replace_key_text"),
               sum(1 for index in scored if second["correct"][index] is not None)])
        check(f"{name}, prompt versions", [model["bilmiyorum"]["prompt_version"], model["i_dont_know"]["prompt_version"]],
              [first["prompt_version"], version])
        check(f"{name}, Bilmiyorum prompt version is the Hallucination tab's", results["dont_know"]["prompt_version"], first["prompt_version"])
        found = {}
        for side, run in (("bilmiyorum", first), ("i_dont_know", second)):
            found[side] = counted_dont_know(run, scored)
            check(f"{name}, {side} answers without {DONT_KNOW_LETTER} last", 0, found[side]["unlabelled"])
            check(f"{name}, {side} counts", [model[side][key] for key in keys], [found[side][key] for key in keys])
            for key in rates:
                check(f"{name}, {side} {key}", model[side][key], found[side][key], metric=True)
        test = bm.paired_comparison(found["bilmiyorum"]["wrong_answers"], found["i_dont_know"]["wrong_answers"])
        paired = model["paired"]
        check(f"{name}, wrong only with Bilmiyorum, only with I don't know", [paired["bilmiyorum_only_wrong"], paired["i_dont_know_only_wrong"]],
              [test["first_only"], test["second_only"]])
        check(f"{name}, p", paired["p"], test["p"], p=True)
        tests.append((model, test))
    for (model, _), adjusted in zip(tests, bm.holm([test["p"] for _, test in tests])):
        check(f"{model['name']}, Holm-adjusted p", model["paired"]["p_holm"], adjusted, p=True)
    return mismatches


def check_rerun(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute results.json's `hosted_glide_rerun` from answers.json's `rerun_runs` on the scored questions: the run
    has the setup of the run it replaces (provider, model, reasoning, questions per request), which is a main run and
    the original run of the Hallucination tab row named as its "I don't know" run, is a five-option run over every scored
    question with the main prompts' version, and has the published counts and accuracy; then, with it as that row's
    original run, the derived abstention at the "I don't know" run's attempt rate and the comparison with confidence
    (wrong answers with the option against wrong answers held back at the cut-off, exact McNemar). The rerun must be
    listed once and in no other list. Returns a line per mismatch."""
    section = results.get("hosted_glide_rerun")
    runs = {run["run"]: run for run in answers.get("rerun_runs", [])}
    listed = [section["run"]] if section else []
    elsewhere = set(listed) & listed_elsewhere(answers, "rerun_runs")
    if sorted(listed) != sorted(runs) or elsewhere:
        checks.failed += 1
        return [f"  runs: results.json lists {listed}, answers.json's rerun_runs {sorted(runs)}, also elsewhere {sorted(elsewhere)}"]
    if section is None:
        return []
    checks.passed += 1
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    run = runs[section["run"]]
    total = len(scored)
    main = {item["run"]: item for item in answers["runs"]}
    replaced = main.get(section["replaces_run"])
    rows = [row for row in (results.get("dont_know") or {}).get("models", []) if row["original_run"] == section["replaces_run"]]
    check("replaced run is a main run and one Hallucination tab row's original run", [True, 1], [replaced is not None, len(rows)])
    if replaced is None or len(rows) != 1:
        return mismatches
    row = rows[0]
    setup = ("provider", "model", "thinking", "questions_per_request")
    check("setup of the replaced run", [replaced[key] for key in setup], [run[key] for key in setup])
    check("the Hallucination tab row's model", [replaced["provider"], replaced["model"]], [row["provider"], row["model"]])
    check("dont_know_run", section["dont_know_run"], row["run"])
    check("run kind", [section["rerun"], None, None, None, None, None, None, None, total],
          [run.get("rerun"), run.get("dont_know"), run.get("dont_know_word"), run.get("english"), run.get("repeat"),
           run.get("question_list"), run.get("replace_key_text"), run.get("shuffle_options"),
           sum(1 for index in scored if run["correct"][index] is not None)])
    check("prompt version", [section["prompt_version"], section["prompt_version"]], [run["prompt_version"], hashed(answers["prompts"])])
    right = sum(int(run["correct"][index]) for index in scored)
    invalid = sum(1 for index in scored if run["choice"][index] is None)
    check("counts", [section["right"], section["wrong"], section["invalid"]], [right, total - right - invalid, invalid])
    check("accuracy", section["accuracy"], right / total, metric=True)
    option_run = next((item for item in answers.get("dont_know_runs", []) if item["run"] == row["run"]), None)
    if option_run is None:
        check("the \"I don't know\" run in dont_know_runs", True, False)
        return mismatches
    option = counted_dont_know(option_run, scored)
    derived = derived_abstention(
        [(None if run["score"][index] is None else float(run["score"][index]), int(run["correct"][index])) for index in scored],
        option["attempt_rate"],
    )
    for key, value in derived.items():
        check(f"derived {key}", section["derived"][key], value, metric=key not in ("right", "wrong", "abstained"))
    cut_off = derived["cut_off"]
    confidence_wrong = [int(cut_off is not None and run["score"][index] is not None and float(run["score"][index]) >= cut_off
                            and not run["correct"][index]) for index in scored]
    test = bm.paired_comparison(option["wrong_answers"], confidence_wrong)
    published = section["vs_confidence"]
    check("wrong only with the option, only with confidence", [published["option_only_wrong"], published["confidence_only_wrong"]],
          [test["first_only"], test["second_only"]])
    check("p", published["p"], test["p"], p=True)
    return mismatches


def check_vs_confidence(results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute `dont_know_option_word.vs_confidence` from answers.json: per option-word model, its option-word run
    (dont_know_word_runs) against its five-option run (the Hallucination tab row's original run, or the hosted GLiDE
    rerun where that run is the one it replaces) held back by confidence at the derived cut-off on the scored questions:
    the target (the option run's answered count and attempt rate), the cut-off and its neighbouring distinct scores with
    their answered counts, the achieved answered count and rate, right, wrong and abstained, the wrong answers only with
    the option and only with confidence, exact McNemar p, and Holm's correction over the models whose option run chose
    the option on at least `share` of the scored questions (which must be the Hallucination tab's family). Returns a line
    per mismatch."""
    section = (results.get("dont_know_option_word") or {}).get("vs_confidence")
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    total = len(scored)
    words = {run["run"]: run for run in answers.get("dont_know_word_runs", [])}
    main = {run["run"]: run for run in answers["runs"]}
    reruns = {run["run"]: run for run in answers.get("rerun_runs", [])}
    rerun = results.get("hosted_glide_rerun") or {}
    rows = {row["run"]: row for row in results["dont_know"]["models"]}
    sections = results["dont_know_option_word"]["models"]
    check("share", section["share"], 0.01)
    check("models", [entry["name"] for entry in section["models"]], [model["name"] for model in sections])
    family = []
    for model, entry in zip(sections, section["models"]):
        name = model["name"]
        row = rows[model["bilmiyorum"]["run"]]
        replaces = row["original_run"] if row["original_run"] == rerun.get("replaces_run") else None
        five_id = rerun["run"] if replaces is not None else row["original_run"]
        check(f"{name} runs", [entry["option_run"], entry["five_option_run"], entry["replaces_run"]],
              [model["i_dont_know"]["run"], five_id, replaces])
        option_run, five = words.get(entry["option_run"]), (reruns if replaces is not None else main).get(five_id)
        if option_run is None or five is None:
            check(f"{name} runs in answers.json", True, False)
            continue
        option = counted_dont_know(option_run, scored)
        answered = option["right"] + option["wrong"]
        check(f"{name} target", [entry["option"][key] for key in ("answered", "right", "wrong", "dont_know")],
              [answered, option["right"], option["wrong"], option["dont_know"]])
        check(f"{name} target attempt rate", entry["option"]["attempt_rate"], answered / total, metric=True)
        pairs = [(None if five["score"][index] is None else float(five["score"][index]), int(five["correct"][index])) for index in scored]
        derived = derived_abstention(pairs, answered / total)
        cut_off = derived["cut_off"]
        published = entry["derived"]
        check(f"{name} cut-off", published["cut_off"], cut_off, metric=True)
        if cut_off is None:
            continue
        scores = [score for score, _ in pairs if score is not None]
        lower = max((score for score in scores if score < cut_off), default=None)
        higher = min((score for score in scores if score > cut_off), default=None)
        for side, value in (("below", lower), ("above", higher)):
            check(f"{name} {side} cut-off", published[side]["cut_off"], value, metric=True)
            check(f"{name} {side} answered", published[side]["answered"],
                  None if value is None else sum(1 for score in scores if score >= value))
        check(f"{name} achieved", [published[key] for key in ("answered", "right", "wrong", "abstained")],
              [derived["right"] + derived["wrong"], derived["right"], derived["wrong"], derived["abstained"]])
        check(f"{name} achieved attempt rate", published["attempt_rate"], derived["attempt_rate"], metric=True)
        confidence_wrong = [int(score is not None and score >= cut_off and not correct) for score, correct in pairs]
        test = bm.paired_comparison(option["wrong_answers"], confidence_wrong)
        check(f"{name} wrong only with the option, only with confidence", [entry["option_only_wrong"], entry["confidence_only_wrong"]],
              [test["first_only"], test["second_only"]])
        check(f"{name} p", entry["p"], test["p"], p=True)
        if option["dont_know"] >= section["share"] * total:
            family.append((entry, test["p"]))
    check("family", section["family"], [entry["name"] for entry, _ in family])
    check("family is the Hallucination tab's among the option-word models", sorted(section["family"]),
          sorted(row["name"] for row in results["dont_know"]["models"] if row["vs_confidence"] and row["vs_confidence"]["p_holm"] is not None
                 and row["name"] in {model["name"] for model in sections}))
    adjusted = dict(zip((id(entry) for entry, _ in family), bm.holm([p for _, p in family])))
    for entry in section["models"]:
        check(f"{entry['name']} p_holm", entry["p_holm"], adjusted.get(id(entry)), p=True)
    return mismatches


def check_coverage(docs: Path, results: dict[str, Any], answers: dict[str, Any], checks: Checks) -> list[str]:
    """Recompute `english_reading.coverage` from answers.json on english-reading.json's kept questions: per English
    reading model, its native points (Turkish "Bilmiyorum": `english_reading.dont_know`'s Turkish first run, or for a
    model outside that comparison its Hallucination tab first run; Turkish "I
    don't know": the option-word run of its Hallucination tab row; English "I don't know": the English first run, also
    in english_only; run null where there is none) with right, wrong, abstained (the option), invalid, coverage and risk,
    and its two curves (the Text tab run and the first English run): for every distinct score s among answered kept
    questions, the answers with a score of at least s, as [coverage, risk, answered, wrong], ordered by coverage.
    Returns a line per mismatch."""
    section = (results.get("english_reading") or {}).get("coverage")
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False) -> None:
        matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    position = {question: index for index, question in enumerate(answers["questions"]["id"])}
    kept = [position[item["question_id"]] for item in public["questions"] if item["kept"]]
    total = len(kept)
    check("questions", [section["questions"], public["kept"]], [total, total])
    runs = {run["run"]: run for key, found in answers.items() if key.endswith("runs") for run in found}
    reading = results["english_reading"]
    idk = reading.get("dont_know") or {}
    turkish = {model["text_run"]: model["turkish"]["run"] for model in idk.get("models", [])}
    hallucination = {row["original_run"]: row["run"] for row in (results.get("dont_know") or {}).get("models", [])}
    english = {model["text_run"]: model["english"]["run"] for model in idk.get("models", []) + idk.get("english_only", [])}
    original = {row["run"]: row["original_run"] for row in (results.get("dont_know") or {}).get("models", [])}
    word = {original[model["bilmiyorum"]["run"]]: model["i_dont_know"]["run"]
            for model in (results.get("dont_know_option_word") or {}).get("models", [])}
    full_bank = {run["run"] for key in ("dont_know_runs", "dont_know_word_runs") for run in answers.get(key, [])}
    check("models", [model["name"] for model in section["models"]], [model["name"] for model in reading["models"]])
    for model, entry in zip(reading["models"], section["models"]):
        name, text_run = model["name"], model["turkish_run"]
        check(f"{name} text_run", entry["text_run"], text_run)
        expected = [("Turkish", "Bilmiyorum", turkish.get(text_run, hallucination.get(text_run))),
                    ("Turkish", "I don't know", word.get(text_run)),
                    ("English", "I don't know", english.get(text_run))]
        check(f"{name} native series", [(item["language"], item["wording"], item["run"]) for item in entry["native"]], expected)
        for (language, wording, run_id), item in zip(expected, entry["native"]):
            label = f"{name} {language} {wording}"
            if run_id is None:
                check(f"{label} not measured", item, {"language": language, "wording": wording, "run": None})
                continue
            run = runs[run_id]
            choices = [run["choice"][index] for index in kept]
            check(f"{label} asked every kept question", True, all(run["correct"][index] is not None for index in kept))
            right = sum(1 for index in kept if run["choice"][index] not in (None, DONT_KNOW_LETTER) and run["correct"][index])
            wrong = sum(1 for index in kept if run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index])
            counts = [right, wrong, choices.count(DONT_KNOW_LETTER), choices.count(None), run_id in full_bank]
            check(f"{label} counts", [item.get(key) for key in ("right", "wrong", "abstained", "invalid", "full_bank_restricted")], counts)
            check(f"{label} coverage", item.get("coverage"), (right + wrong) / total, metric=True)
            check(f"{label} risk", item.get("risk"), wrong / (right + wrong) if right + wrong else None, metric=True)
        for language, run_id, curve in zip(("Turkish", "English"), (text_run, model["run"]), entry["curves"]):
            label = f"{name} {language} curve"
            check(f"{label} series", [curve["language"], curve["run"]], [language, run_id])
            run = runs[run_id]
            check(f"{label} asked every kept question", True, all(run["correct"][index] is not None for index in kept))
            answerable = [(float(run["score"][index]), bool(run["correct"][index])) for index in kept
                          if run["choice"][index] is not None and run["score"][index] is not None]
            expected_points = []
            for threshold in sorted({score for score, _ in answerable}, reverse=True):
                taken = [correct for score, correct in answerable if score >= threshold]
                errors = taken.count(False)
                expected_points.append([len(taken) / total, errors / len(taken), len(taken), errors])
            check(f"{label} points", len(curve["points"]), len(expected_points))
            for index, (published, recomputed) in enumerate(zip(curve["points"], expected_points)):
                matched = (published[2:] == recomputed[2:] and close(published[0], recomputed[0], METRIC_TOLERANCE)
                           and close(published[1], recomputed[1], METRIC_TOLERANCE))
                if "≠" in checks.cell(matched, str(recomputed), str(published)):
                    mismatches.append(f"  {label} point {index}: {recomputed} ≠ {published}")
    return mismatches


def check_dont_know_word(docs: Path, results: dict[str, Any], answers: dict[str, Any], checks: Checks) -> list[str]:
    """Recompute `english_reading.dont_know_word` ("I don't know" in both languages) from answers.json on
    english-reading.json's kept questions: per English reading model, in that order, the English side (the first
    English run with "I don't know" of `english_reading.dont_know`, also in english_only) and the Turkish side (the
    option-word run of its Hallucination tab row, from dont_know_word_runs), null where there is none, each with right,
    wrong, "I don't know", invalid (adding to the kept questions), accuracy, attempt rate, non-hallucination rate (null
    without "I don't know" or wrong answers) and mean probability of the option; paired exactly where both sides exist:
    wrong answers only in English and only in Turkish, exact McNemar p and Holm's correction over those models.
    Returns a line per mismatch."""
    section = (results.get("english_reading") or {}).get("dont_know_word")
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    position = {question: index for index, question in enumerate(answers["questions"]["id"])}
    kept = [position[item["question_id"]] for item in public["questions"] if item["kept"]]
    total = len(kept)
    check("questions", [section["questions"], public["kept"]], [total, total])
    option = "I don't know"
    check("option and sentence", [section.get("option"), section.get("sentence")],
          [option, f"If you do not know the answer, choose {option}."])
    reading = results["english_reading"]
    idk = reading.get("dont_know") or {}
    english_run = {model["text_run"]: model["english"]["run"] for model in idk.get("models", []) + idk.get("english_only", [])}
    original = {row["run"]: row["original_run"] for row in (results.get("dont_know") or {}).get("models", [])}
    word_run = {original[model["bilmiyorum"]["run"]]: model["i_dont_know"]["run"]
                for model in (results.get("dont_know_option_word") or {}).get("models", [])}
    lists = {"english": {run["run"]: run for run in answers.get("english_dont_know_runs", [])},
             "turkish": {run["run"]: run for run in answers.get("dont_know_word_runs", [])}}
    check("models", [(model["name"], model["text_run"]) for model in section["models"]],
          [(model["name"], model["turkish_run"]) for model in reading["models"]])
    tests = []
    for model, entry in zip(reading["models"], section["models"]):
        name, text_run = model["name"], model["turkish_run"]
        wrong_answers = {}
        for side, run_id in (("english", english_run.get(text_run)), ("turkish", word_run.get(text_run))):
            label, item = f"{name} {side}", entry.get(side)
            if run_id is None:
                check(f"{label} not measured", item, None)
                continue
            if item is None:
                check(f"{label} measured", None, run_id)
                continue
            run = lists[side][run_id]
            check(f"{label} asked every kept question", True, all(run["correct"][index] is not None for index in kept))
            found = counted_dont_know(run, kept)
            counts = [run_id, found["right"], found["wrong"], found["dont_know"], found["invalid"]]
            check(f"{label} run and counts", [item.get(key) for key in ("run", "right", "wrong", "dont_know", "invalid")], counts)
            check(f"{label} counts add to {total}", sum(counts[1:]), total)
            for key in ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability"):
                check(f"{label} {key}", item.get(key), found[key], metric=True)
            wrong_answers[side] = found["wrong_answers"]
        if len(wrong_answers) == 2:
            test = bm.paired_comparison(wrong_answers["english"], wrong_answers["turkish"])
            tests.append((name, entry.get("paired"), test))
        else:
            check(f"{name} paired", entry.get("paired"), None)
    adjusted = bm.holm([test["p"] for _, _, test in tests])
    for (name, paired, test), p_holm in zip(tests, adjusted):
        if paired is None:
            check(f"{name} paired", None, "present")
            continue
        check(f"{name} paired counts", [paired.get("english_only_wrong"), paired.get("turkish_only_wrong")],
              [test["first_only"], test["second_only"]])
        check(f"{name} p", paired.get("p"), test["p"], p=True)
        check(f"{name} p_holm", paired.get("p_holm"), p_holm, p=True)
    return mismatches


# The same number of answers (results.json `dont_know_same_answers`): its reference, bootstrap resamples and seed, the
# interval's tail (the 250th smallest and largest resampled difference) and the interval's tolerance (absolute).
SAME_ANSWERS = {"reference": "Liquid d1-ultra", "resamples": 10000, "seed": 20261103}
SAME_ANSWERS_TAIL = 250
INTERVAL_TOLERANCE = 1e-12


def kept_ranking(run: dict[str, Any], positions: list[int], ids: list[int]) -> tuple[list[int], list[int]]:
    """A run's scored answers (score and choice not null) on the questions at `positions` (whose question ids are `ids`),
    by score, highest first, equal scores by question id ascending: the question positions (indices into `positions`)
    and 1 for a wrong answer, 0 for a right one."""
    ranked = sorted((-float(run["score"][index]), ids[index], position, int(not run["correct"][index]))
                    for position, index in enumerate(positions) if run["score"][index] is not None and run["choice"][index] is not None)
    return [item[2] for item in ranked], [item[3] for item in ranked]


def selected_wrong(ranking: tuple[list[int], list[int]], weights: list[int], k: int) -> int | None:
    """The wrong answers among exactly the first k of a ranking (kept_ranking), each answer counting `weights` of its
    question position times, only as many copies of the boundary answer as k needs; None when the weighted answers are
    fewer than k."""
    order, wrong = ranking
    counts = list(map(weights.__getitem__, order))
    taken = list(itertools.accumulate(counts))
    if not taken or taken[-1] < k:
        return None
    errors = list(itertools.accumulate(map(int.__mul__, counts, wrong)))
    at = bisect.bisect_left(taken, k)
    return (errors[at - 1] if at else 0) + (k - (taken[at - 1] if at else 0)) * wrong[at]


def check_same_answers(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int], checks: Checks) -> list[str]:
    """Recompute `dont_know_same_answers` from answers.json: per family (Turkish: every main run in `runs` order on the
    scored questions, each its own five-option run; English: the English reading models on english-reading.json's kept
    questions in answers.json order, each with its first English run) k and its run (the reference's answered count
    with "I don't know"), each model's wrong answers among exactly its first k (by score, highest first, equal scores by
    question id ascending; a whole number), wrong of answers and difference from the reference (exact), the paired
    bootstrap over questions with the published seed and resamples (p within a relative P_TOLERANCE, interval within
    INTERVAL_TOLERANCE), Holm's correction over the non-reference models, each entry's wrong_by_rank (its scored answers
    in the selection order, "1" wrong and "0" right: rebuilt exactly, as long as the run's scored answers, with wrong the
    "1"s among its first k characters), no curve pairs, and the runs with the option of each Hallucination tab model and
    each English model (and no points for any other main run). Returns a line per mismatch."""
    section = results.get("dont_know_same_answers")
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, p: bool = False, interval: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        elif interval:
            matched = (published is None and recomputed is None) or (
                published is not None and recomputed is not None and len(published) == len(recomputed) == 2
                and all(close(a, b, INTERVAL_TOLERANCE) for a, b in zip(published, recomputed)))
        else:
            matched = published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    check("reference, resamples, seed", [section.get(key) for key in SAME_ANSWERS], list(SAME_ANSWERS.values()))
    reference, resamples = SAME_ANSWERS["reference"], SAME_ANSWERS["resamples"]
    lists = {key: {run["run"]: run for run in found} for key, found in answers.items() if key.endswith("runs")}

    def option_counts(run: dict[str, Any] | None, positions: list[int]) -> tuple[int, int] | None:
        if run is None or any(run["correct"][index] is None for index in positions):
            return None
        answered = [index for index in positions if run["choice"][index] not in (None, DONT_KNOW_LETTER)]
        return len(answered), sum(1 for index in answered if not run["correct"][index])

    def family(label: str, published: dict[str, Any], positions: list[int], expected: list[dict[str, Any]]) -> None:
        """`expected`: per model its name, text_run, five-option run, the list its five-option run is in, whether it is
        the reference, whether it has points (`option`: a Hallucination tab model or an English model; other main runs
        have none) and its runs with the option as (wording, list, run)."""
        check(f"{label} questions", published["questions"], len(positions))
        check(f"{label} models", [[model["name"], model["text_run"]] for model in published["models"]],
              [[item["name"], item["text_run"]] for item in expected])
        points = []
        for item in expected:
            found = []
            for wording, key, run_id in item["points"]:
                counts = option_counts(lists.get(key, {}).get(run_id), positions)
                found.append(None if counts is None else {"wording": wording, "run": run_id, "answered": counts[0], "wrong": counts[1]})
            points.append(found)
        references = [index for index, item in enumerate(expected) if item["reference"]]
        if len(references) != 1 or len(published["models"]) != len(expected):
            check(f"{label} one reference among the models, as many models as expected", True, False)
            return
        at = references[0]
        k_point = next((point for point in points[at] if point is not None and point["wording"] == "I don't know"), None)
        k, k_run = (None, None) if k_point is None else (k_point["answered"], k_point["run"])
        check(f"{label} k, k_run, k_wording", [published["k"], published["k_run"], published["k_wording"]], [k, k_run, "I don't know"])
        if k is None:
            return
        rankings = []
        for item, model, found in zip(expected, published["models"], points):
            name = f"{label} {item['name']} (run {item['text_run']})"
            check(f"{name} runs", [model.get("text_run"), model.get("five_option_run"), "replaces_run" in model],
                  [item["text_run"], item["five_option_run"], False])
            run = lists.get(item["list"], {}).get(item["five_option_run"])
            if run is None or any(run["correct"][index] is None for index in positions):
                check(f"{name} five-option run in answers.json, asked every question", True, False)
                return
            ranking = kept_ranking(run, positions, ids)
            rankings.append(ranking)
            wrong = selected_wrong(ranking, [1] * len(positions), k)
            check(f"{name} wrong, a whole number", [model["wrong"], isinstance(model["wrong"], int)], [wrong, True])
            check(f"{name} wrong_of_answers", model["wrong_of_answers"], None if wrong is None else wrong / k)
            if wrong is None:
                return
            ranks = model.get("wrong_by_rank")
            scored_answers = sum(1 for index in positions if run["score"][index] is not None and run["choice"][index] is not None)
            check(f"{name} wrong_by_rank", ranks, "".join(map(str, ranking[1])))
            check(f"{name} wrong_by_rank length, wrong among its first k, no curve pairs",
                  [len(ranks) if isinstance(ranks, str) else None, ranks[:k].count("1") if isinstance(ranks, str) else None,
                   "curve" in model], [scored_answers, model["wrong"], False])
            if item["option"]:
                check(f"{name} points", model.get("points"), found)
            else:
                check(f"{name} no points", "points" in model, False)
        reference_rate = published["models"][at]["wrong_of_answers"]
        rng = random.Random(SAME_ANSWERS["seed"])
        drawn: list[list[float]] = [[] for _ in rankings]
        short = None
        for resample in range(resamples):
            times = Counter(rng.choices(range(len(positions)), k=len(positions)))
            weights = [times[position] for position in range(len(positions))]
            rates = [selected_wrong(ranking, weights, k) for ranking in rankings]
            if None in rates:
                short = resample + 1
                break
            for index, rate in enumerate(rates):
                drawn[index].append(rate / k - rates[at] / k)
        check(f"{label} every resample keeps k answers of every model", short, None)
        if short is not None:
            return
        others = [index for index in range(len(rankings)) if index != at]
        p_values = {}
        for index in range(len(rankings)):
            model, name = published["models"][index], f"{label} {expected[index]['name']} (run {expected[index]['text_run']})"
            if index == at:
                check(f"{name} (reference) difference, interval, p, p_holm",
                      [model["difference"], model["interval"], model["p"], model["p_holm"]], [None, None, None, None])
                continue
            differences = sorted(drawn[index])
            check(f"{name} difference", model["difference"], model["wrong_of_answers"] - reference_rate)
            check(f"{name} interval", model["interval"],
                  [differences[SAME_ANSWERS_TAIL - 1], differences[resamples - SAME_ANSWERS_TAIL]], interval=True)
            low = sum(1 for value in differences if value <= 0)
            high = sum(1 for value in differences if value >= 0)
            p_values[index] = min(1, 2 * min(1 + low, 1 + high) / (resamples + 1))
            check(f"{name} p", model["p"], p_values[index], p=True)
        for index, adjusted in zip(others, bm.holm([p_values[index] for index in others])):
            check(f"{label} {expected[index]['name']} (run {expected[index]['text_run']}) p_holm",
                  published["models"][index]["p_holm"], adjusted, p=True)

    ids = answers["questions"]["id"]
    words = {model["bilmiyorum"]["run"]: model["i_dont_know"]["run"]
             for model in (results.get("dont_know_option_word") or {}).get("models", [])}
    # The decision models' rows (each row's group, checked by check_dont_know): chat models' runs with the option stay out.
    option_rows = {row["original_run"]: row for row in results["dont_know"]["models"] if row["group"] == "decision"}
    check("Turkish: every Hallucination tab model is a main run", sorted(set(option_rows) - {run["run"] for run in results["runs"]}), [])
    turkish = []
    for main_run in results["runs"]:
        text_run = main_run["run"]
        row = option_rows.get(text_run)
        option_runs = []
        if row is not None:
            option_runs.append(("Bilmiyorum", "dont_know_runs", row["run"]))
            if row["run"] in words:
                option_runs.append(("I don't know", "dont_know_word_runs", words[row["run"]]))
        turkish.append({"name": main_run["name"], "text_run": text_run, "five_option_run": text_run, "list": "runs",
                        "reference": row is not None and row["name"] == reference, "option": row is not None,
                        "points": option_runs})
    family("Turkish", section["turkish"], scored, turkish)

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    position = {question: index for index, question in enumerate(ids)}
    kept = sorted(position[item["question_id"]] for item in public["questions"] if item["kept"])
    reading = results["english_reading"]
    idk = reading.get("dont_know") or {}
    first_english = {model["text_run"]: model["english"]["run"] for model in idk.get("models", []) + idk.get("english_only", [])
                     if model["group"] == "decision"}
    english = []
    for model in reading["models"]:
        text_run = model["turkish_run"]
        option_runs = [("I don't know", "english_dont_know_runs", first_english[text_run])] if text_run in first_english else []
        english.append({"name": model["name"], "text_run": text_run, "five_option_run": model["run"], "list": "english_runs",
                        "reference": model["name"] == reference, "option": True, "points": option_runs})
    family("English", section["english"], kept, english)
    return mismatches


def nearest_rank(values: list[float], share: float) -> float:
    """The `share` percentile of `values` by nearest rank (export_results.nearest_rank)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def check_web_grounding(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int],
                        checks: Checks) -> list[str]:
    """Recompute results.json's `web_grounding` (Perplexity's web grounding test) from answers.json and
    web-grounding.json: the pilots' runs and the repeats are answers.json's `web_grounding_runs`, in no other list; the
    full-bank pair's runs are main runs, the English pair's `english_runs` runs and the "Bilmiyorum" pair's
    `dont_know_runs` runs; each repeat has its first run's setup, mode, language, questions and settings; every
    run's setup (the section's provider and model, one question per request) and kind (grounding on only in the on runs,
    "Bilmiyorum" only in its pairs, English only in the English pair, the sample's seed); each pair asked the same
    questions, and both pilots the same ones; per arm its questions, right answers and accuracy, median and nearest-rank
    percentile request time, its input tokens (web-grounding.json) and its cost at the section's price (input tokens plus
    the fee per search, one search per grounded request), overall and for the Turkish runs by group; the paired counts
    and tests (exact McNemar), for each repeat too, and each arm's mean, lowest and highest run; the "Bilmiyorum" pairs'
    counts and rates; per grounded run what the search returned
    (web-grounding.json) and the right answers off and on among each check's questions; PWS-Decisions' aggregates
    (web-grounding.json), costs at the same price and its paired test. Returns a line per mismatch."""
    section = results.get("web_grounding")
    own = {run["run"]: run for run in answers.get("web_grounding_runs", [])}
    if section is None:
        if own:
            checks.failed += 1
            return [f"  runs: answers.json's web_grounding_runs {sorted(own)} without a web_grounding section"]
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False, cost: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        elif cost:
            matched = close(published, recomputed, relative=COST_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    inputs = json.loads((docs / "web-grounding.json").read_text(encoding="utf-8"))
    tokens = {item["run"]: item for item in inputs["runs"]}
    lists = {"turkish": "runs", "english": "english_runs", "dont_know": "dont_know_runs", "pilot": "web_grounding_runs",
             "pilot_dont_know": "web_grounding_runs", "english_dont_know": "english_dont_know_runs"}
    parts = {part: (section[part]["off"]["run"], section[part]["on"]["run"]) for part in lists}
    # The repeats of the full bank's and the English pair's first runs, (part, repeat number, off run, on run).
    repeats = [(part, entry["repeat"], entry["off"]["run"], entry["on"]["run"]) for part in ("turkish", "english")
               for entry in section[part].get("repeats", [])]
    listed = {*parts["pilot"], *parts["pilot_dont_know"], *(run for _, _, off, on in repeats for run in (off, on))}
    check("own runs, none elsewhere", [sorted(listed), []], [sorted(own), sorted(set(own) & listed_elsewhere(answers, "web_grounding_runs"))])
    in_lists = {part: all(run in {item["run"] for item in answers.get(name, [])} for run in parts[part]) for part, name in lists.items()}
    check("each pair in its answers.json list", {part: True for part in lists}, in_lists)
    if not all(in_lists.values()):
        return mismatches
    exported = {run["run"]: run for name in set(lists.values()) for run in answers.get(name, [])}
    price = section["price"]
    reading = set(section["reading_units"])
    questions = answers["questions"]
    position = {question: index for index, question in enumerate(questions["id"])}

    def asked(run: int) -> list[int]:
        return [index for index in scored if exported[run]["correct"][index] is not None]

    for part, (off, on) in parts.items():
        for arm, run in (("off", off), ("on", on)):
            got = exported[run]
            check(f"{part} {arm} run {run}: setup and kind",
                  [section["provider"], section["model"], 1, "web_grounding" if arm == "on" else None,
                   part in ("dont_know", "pilot_dont_know", "english_dont_know"), part in ("english", "english_dont_know"), None],
                  [got["provider"], got["model"], got["questions_per_request"], got.get("perplexity_mode"), bool(got.get("dont_know")),
                   bool(got.get("english")), got.get("repeat")])
        check(f"{part}: both runs asked the same questions", True, asked(off) == asked(on))
    for part, number, off, on in repeats:
        first = parts[part]
        for arm, run, base in (("off", off, first[0]), ("on", on, first[1])):
            got, ref = exported[run], exported[base]
            check(f"{part} repeat {number} {arm} run {run}: setup, kind and settings of run {base}",
                  [section["provider"], section["model"], 1, ref.get("perplexity_mode"), False, ref.get("english"),
                   ref.get("question_list"), ref["seed"], ref["thinking"], ref["dataset_sha256"], number],
                  [got["provider"], got["model"], got["questions_per_request"], got.get("perplexity_mode"),
                   bool(got.get("dont_know")), got.get("english"), got.get("question_list"), got["seed"], got["thinking"],
                   got["dataset_sha256"], got.get("repeat")])
    sample = asked(parts["pilot"][0])
    check("the sample: size, seed, the same questions in both pilots", [section["sample"]["questions"], section["sample"]["seed"],
          section["sample"]["seed"], True], [len(sample), exported[parts["pilot"][0]]["seed"], exported[parts["pilot_dont_know"][0]]["seed"],
          asked(parts["pilot_dont_know"][0]) == sample])
    check("Text tab runs", [section["text_runs"]["off"], section["text_runs"]["on"]], list(parts["turkish"]))

    def measures(name: str, published: dict[str, Any], run: int, indices: list[int], input_tokens: int) -> None:
        got = exported[run]
        seconds = [got["request_seconds"][index] for index in indices]
        correct = sum(int(got["correct"][index]) for index in indices)
        searches = len(indices) if got.get("perplexity_mode") is not None else 0
        cost = input_tokens * price["input_per_million"] / 1e6 + searches * price["per_search"]
        check(f"{name}: questions, right answers, input tokens, searches",
              [published["questions"], published["correct"], published["input_tokens"], published["searches"]],
              [len(indices), correct, input_tokens, searches])
        check(f"{name}: accuracy", published["accuracy"], correct / len(indices), metric=True)
        check(f"{name}: median request seconds", published["median_request_seconds"], statistics.median(seconds), metric=True)
        check(f"{name}: p95 request seconds", published["p95_request_seconds"], nearest_rank(seconds, section["percentile"]), metric=True)
        check(f"{name}: cost", published["cost_usd"], cost, cost=True)
        check(f"{name}: cost per 1M questions", published["cost_per_million_questions"], cost / len(indices) * 1e6, cost=True)

    def arm(name: str, published: dict[str, Any], by_group: bool) -> None:
        run = published["run"]
        groups = tokens[run]["groups"]
        indices = asked(run)
        measures(name, published, run, indices, sum(item["input_tokens"] for item in groups.values()))
        check(f"{name}: groups", sorted(published.get("groups", {})), ["grammar", "reading"] if by_group else [])
        for group in published.get("groups", {}):
            measures(f"{name}, {group}", published["groups"][group], run,
                     [index for index in indices if (questions["unit"][index] in reading) == (group == "reading")],
                     groups[group]["input_tokens"])

    def paired(name: str, published: dict[str, Any], off: int, on: int, indices: list[int]) -> None:
        runs = {"off": off, "on": on}
        both = [index for index in indices if all(exported[run]["correct"][index] is not None for run in runs.values())]
        right = [[int(exported[run]["correct"][index]) for index in both] for run in (off, on)]
        test = bm.paired_comparison(*right)
        check(f"{name}: questions, both right, right off only, on only, both wrong",
              [published[key] for key in ("questions", "both_right", "off_only", "on_only", "both_wrong")],
              [test["questions"], sum(a and b for a, b in zip(*right)), test["first_only"], test["second_only"],
               sum(not a and not b for a, b in zip(*right))])
        check(f"{name}: errors, missing", [published["errors"], published["missing"]],
              [{side: sum(exported[run]["correct"][index] is not None and exported[run]["choice"][index] is None
                          for index in indices) for side, run in runs.items()},
               {side: sum(exported[run]["correct"][index] is None for index in indices) for side, run in runs.items()}])
        check(f"{name}: p", published["p"], test["p"], p=True)

    def search(name: str, published: dict[str, Any] | None, off: int, on: int) -> None:
        found = tokens[on]["search"]
        # A run that returned no page has no source checks (None), not zeros.
        check(f"{name}: no source checks without pages", published is None, not found["pages"])
        if published is None or not found["pages"]:
            return
        check(f"{name}: run, pages, pages per question, sites, top domains",
              [published["run"], published["pages"], published["pages_per_question"], published["sites"], published["top_domains"]],
              [on, found["pages"], found["pages_per_question"], found["sites"], found["top_domains"]])
        for key in ("shared_words", "publisher", "source_book"):
            ids = found[key]
            right = [[int(exported[run]["correct"][position[question]]) for question in ids] for run in (off, on)]
            item = published[key]
            check(f"{name}, {key}: ids, questions, right off, right on, right only off, only on",
                  [item["ids"], item["questions"], item["right_off"], item["right_on"], item["off_only"], item["on_only"]],
                  [ids, len(ids), sum(right[0]), sum(right[1]), sum(a and not b for a, b in zip(*right)),
                   sum(b and not a for a, b in zip(*right))])

    def compared(name: str, published: dict[str, Any], off: int, on: int, indices: list[int], by_group: bool) -> None:
        """A pair of runs: each arm, the paired counts on the first runs' questions (by group too) and the source checks."""
        check(f"{name}: runs", [published["off"]["run"], published["on"]["run"]], [off, on])
        arm(f"{name} off", published["off"], by_group)
        arm(f"{name} on", published["on"], by_group)
        paired(f"{name} paired", published["paired"], off, on, indices)
        if by_group:
            for group, item in published["paired_groups"].items():
                paired(f"{name} paired, {group}", item, off, on,
                       [index for index in indices if (questions["unit"][index] in reading) == (group == "reading")])
        search(f"{name} search", published["search"], off, on)

    def spread(values: list[float]) -> dict[str, float]:
        return {"mean": statistics.mean(values), "min": min(values), "max": max(values)}

    for part in ("turkish", "english", "pilot"):
        off, on = parts[part]
        published = section[part]
        by_group = part != "english"
        check(f"{part}: questions", published["questions"], len(asked(off)))
        compared(part, published, off, on, asked(off), by_group)
        if part == "pilot":
            check("pilot: no repeats", "repeats" in published or "mean" in published, False)
            continue
        numbers = [entry["repeat"] for entry in published.get("repeats", [])]
        check(f"{part}: repeat numbers, after the first run's 1", numbers, sorted(set(numbers) - {1}))
        for entry in published.get("repeats", []):
            compared(f"{part} repeat {entry['repeat']}", entry, entry["off"]["run"], entry["on"]["run"], asked(off), by_group)
        keys = ("correct", "accuracy", "median_request_seconds", "p95_request_seconds", "cost_per_million_questions")
        for side in ("off", "on"):
            items = [published[side], *(entry[side] for entry in published.get("repeats", []))]
            mean = published["mean"][side]
            check(f"{part} mean {side}: runs, questions", [mean["runs"], mean["questions"]],
                  [[item["run"] for item in items], items[0]["questions"]])
            check(f"{part} mean {side}: one count of questions", len({item["questions"] for item in items}), 1)
            for key in keys:
                found = spread([item[key] for item in items])
                for stat in found:
                    check(f"{part} mean {side}: {key} {stat}", mean[key][stat], found[stat],
                          cost=key == "cost_per_million_questions", metric=key != "cost_per_million_questions")
            for group in mean.get("groups", {}):
                for key in keys:
                    found = spread([item["groups"][group][key] for item in items])
                    for stat in found:
                        check(f"{part} mean {side}, {group}: {key} {stat}", mean["groups"][group][key][stat], found[stat],
                              cost=key == "cost_per_million_questions", metric=key != "cost_per_million_questions")
            check(f"{part} mean {side}: groups", sorted(mean.get("groups", {})), ["grammar", "reading"] if by_group else [])
    for part in ("dont_know", "pilot_dont_know", "english_dont_know"):
        check(f"{part}: questions", section[part]["questions"], len(asked(parts[part][0])))
        for arm_name, run in zip(("off", "on"), parts[part]):
            counted = counted_dont_know(exported[run], asked(run))
            published = section[part][arm_name]
            check(f"{part} {arm_name}: right, wrong, Bilmiyorum, invalid",
                  [published[key] for key in ("right", "wrong", "dont_know", "invalid")],
                  [counted[key] for key in ("right", "wrong", "dont_know", "invalid")])
            answered = counted["right"] + counted["wrong"]
            for key, value in (("accuracy", counted["accuracy"]), ("non_hallucination", counted["non_hallucination"]),
                               ("answered", counted["attempt_rate"]), ("wrong_of_answers", counted["wrong"] / answered if answered else None)):
                check(f"{part} {arm_name}: {key}", published[key], value, metric=True)
    pws, found = section["pws"], inputs["pws"]
    check("PWS-Decisions: name, version, questions", [pws["name"], pws["version"], pws["questions_sha256"], pws["language"]],
          [found[key] for key in ("name", "version", "questions_sha256", "language")])
    for arm_name in ("off", "on"):
        published, got = pws[arm_name], found[arm_name]
        check(f"PWS-Decisions {arm_name}: aggregates", [published.get(key) for key in got], list(got.values()))
        searches = got["questions"] if arm_name == "on" else 0
        cost = got["input_tokens"] * price["input_per_million"] / 1e6 + searches * price["per_search"]
        check(f"PWS-Decisions {arm_name}: accuracy", published["accuracy"], got["correct"] / got["questions"], metric=True)
        check(f"PWS-Decisions {arm_name}: searches", published["searches"], searches)
        check(f"PWS-Decisions {arm_name}: cost", published["cost_usd"], cost, cost=True)
        check(f"PWS-Decisions {arm_name}: cost per 1M questions", published["cost_per_million_questions"],
              cost / got["questions"] * 1e6, cost=True)
    check("PWS-Decisions paired: questions, off only, on only", [pws["paired"][key] for key in ("questions", "off_only", "on_only")],
          [found["on"]["questions"], found["off_only"], found["on_only"]])
    check("PWS-Decisions paired: p", pws["paired"]["p"], bm.sign_test(found["off_only"], found["on_only"]), p=True)
    return mismatches


def check_updated(report: Path | None, results: dict[str, Any], answers: dict[str, Any], checks: Checks) -> list[str]:
    """The footer date (results.json `updated`, when results with this content first went out): never older than any
    main run's `updated` or any published run date; with the benchmark report (--report), never older than the newest
    `updated` of the report's records of the runs answers.json publishes. Returns a line per mismatch."""
    mismatches = []
    updated = results["updated"]
    dates = [run["updated"] for run in results["runs"]]
    dates += [model[side]["date"] + "T00:00:00Z" for model in (results.get("dont_know_option_word") or {}).get("models", [])
              for side in ("bilmiyorum", "i_dont_know")]
    if results.get("hosted_glide_rerun"):
        dates.append(results["hosted_glide_rerun"]["date"] + "T00:00:00Z")
    if "≠" in checks.cell(updated >= max(dates), f"at least {max(dates)}", updated):
        mismatches.append(f"  updated {updated} is older than {max(dates)}")
    if report is not None:
        records = {}
        for match in re.finditer(r"<!-- benchmark-result: (\{.*?\}) -->", report.read_text(encoding="utf-8")):
            record = json.loads(match.group(1))
            records[record["run_id"]] = record
        published = {run["run"] for key, found in answers.items() if key.endswith("runs") for run in found}
        missing = sorted(published - set(records))
        newest = max((records[run]["updated"] for run in published if run in records), default=None)
        if "≠" in checks.cell(not missing and newest is not None and updated >= newest, f"at least {newest}", updated):
            mismatches.append(f"  updated {updated} is older than the newest published run's {newest}, or runs lack a record: {missing}")
    return mismatches


HIGH_CONFIDENCE = {"Liquid d1-ultra": [199, 200, 201, 202, 203], "SubQ Snap 1.1": [346, 387, 388, 389, 390],
                   "Elephant-1": [373, 375, 376, 378, 379]}  # the three models AA's Decision Index v1.0 ties at 65
HIGH_CONFIDENCE_CUTOFFS = [0.5, 0.7, 0.8, 0.9, 0.95, 0.99]


def kept_at(run: dict[str, Any], positions: list[int], cutoff: float) -> tuple[int, list[int]]:
    """Answers on `positions` with a valid choice and a score at least `cutoff`: how many, and the positions not right."""
    kept = [index for index in positions
            if run["choice"][index] is not None and run["score"][index] is not None and run["score"][index] >= cutoff]
    return len(kept), [index for index in kept if run["correct"][index] != 1]


def check_high_confidence(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int],
                          checks: Checks) -> list[str]:
    """Recompute results.json's `high_confidence` from answers.json: per main run (results.json runs order) the answers
    kept at the threshold on the scored questions and the wrong ones; d1-ultra's repeat runs; the three models' runs
    (HIGH_CONFIDENCE, equal to their results.json repeat sets) at each cutoff and the check over k/100, k = 0..98; and
    d1-ultra's English runs on english-reading.json's kept questions with the wrong question ids. Returns a line per
    mismatch."""
    section = results.get("high_confidence")
    if section is None:
        checks.failed += 1
        return ["  high_confidence: missing"]
    mismatches = []

    def check(name: str, published: Any, recomputed: Any) -> None:
        if "≠" in checks.cell(published == recomputed, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    by_run = {run["run"]: run for run in answers["runs"] + answers.get("repeat_runs", [])}
    threshold = 0.95
    check("threshold", section["threshold"], threshold)
    expected = []
    for run in results["runs"]:
        kept, wrong = kept_at(by_run[run["run"]], scored, threshold)
        expected.append({"name": run["name"], "text_run": run["run"], "kept": kept, "wrong": len(wrong)})
    check("models, count and order", [(m["name"], m["text_run"]) for m in section["models"]],
          [(m["name"], m["text_run"]) for m in expected])
    for published, found in zip(section["models"], expected):
        check(f"{found['name']} (run {found['text_run']}) kept, wrong", [published["kept"], published["wrong"]],
              [found["kept"], found["wrong"]])
    repeat_sets = {tuple(item["runs"]) for item in results["repeats"] if item["variant"] is None}
    for name, runs in HIGH_CONFIDENCE.items():
        check(f"{name} runs are a results.json repeat set", True, tuple(runs) in repeat_sets)
    d1 = HIGH_CONFIDENCE["Liquid d1-ultra"]
    repeats = [{"run": run, "kept": kept_at(by_run[run], scored, threshold)[0],
                "wrong": len(kept_at(by_run[run], scored, threshold)[1])} for run in d1[1:]]
    check("repeats", section["repeats"], [{"name": "Liquid d1-ultra", "text_run": d1[0], "runs": repeats}])
    cutoffs = section["cutoffs"]
    check("cutoffs", cutoffs["cutoffs"], HIGH_CONFIDENCE_CUTOFFS)
    check("cutoff models", [(m["name"], m["text_run"]) for m in cutoffs["models"]],
          [(name, runs[0]) for name, runs in HIGH_CONFIDENCE.items()])
    for published, (name, runs) in zip(cutoffs["models"], HIGH_CONFIDENCE.items()):
        check(f"{name} cutoff runs", [row["run"] for row in published["runs"]], runs)
        for row, run in zip(published["runs"], runs):
            counts = [kept_at(by_run[run], scored, cutoff) for cutoff in HIGH_CONFIDENCE_CUTOFFS]
            check(f"{name} run {run} kept per cutoff", row["kept"], [kept for kept, _ in counts])
            check(f"{name} run {run} wrong per cutoff", row["wrong"], [len(wrong) for _, wrong in counts])

    def share(run: int, cutoff: float) -> float:
        kept, wrong = kept_at(by_run[run], scored, cutoff)
        return len(wrong) / kept if kept else float("nan")

    holds = True
    for k in range(99):
        worst = max(share(run, k / 100) for run in d1)
        best = [min(share(run, k / 100) for run in runs) for name, runs in HIGH_CONFIDENCE.items() if name != "Liquid d1-ultra"]
        holds = holds and all(worst < value for value in best)
    check("check", cutoffs["check"], {"cutoffs": "every whole percent from 0% to 98%", "holds": holds})
    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    ids = answers["questions"]["id"]
    position = {question: index for index, question in enumerate(ids)}
    kept_positions = sorted(position[item["question_id"]] for item in public["questions"] if item["kept"])
    english = {run["run"]: run for run in answers.get("english_runs", [])}
    reference = next(m for m in results["english_reading"]["models"] if m["name"] == "Liquid d1-ultra")
    rows = []
    for run in reference["runs"]:
        kept, wrong = kept_at(english[run], kept_positions, threshold)
        rows.append({"run": run, "kept": kept, "wrong": len(wrong), "wrong_questions": sorted(ids[index] for index in wrong)})
    check("english", section["english"], {"name": "Liquid d1-ultra", "questions": len(kept_positions), "runs": rows})
    return mismatches


def check_against_reference(docs: Path, results: dict[str, Any], answers: dict[str, Any], checks: Checks) -> list[str]:
    """Recompute `english_reading.against_reference`: Liquid d1-ultra's first English run against each other decision
    model's first English run (english_reading.models order; decision models by page_config.json's rule on their Text
    tab runs) on english-reading.json's kept questions, right answers only one of the two gave (exact McNemar, d1-ultra
    first), p within a relative P_TOLERANCE, Holm over the others."""
    section = (results.get("english_reading") or {}).get("against_reference")
    if section is None:
        checks.failed += 1
        return ["  english_reading.against_reference: missing"]
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, p: bool = False) -> None:
        matched = close(published, recomputed, relative=P_TOLERANCE) if p else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    position = {question: index for index, question in enumerate(answers["questions"]["id"])}
    kept = sorted(position[item["question_id"]] for item in public["questions"] if item["kept"])
    english = {run["run"]: run for run in answers.get("english_runs", [])}
    models = results["english_reading"]["models"]
    reference = next(m for m in models if m["name"] == "Liquid d1-ultra")
    check("reference", [section["reference"], section["reference_run"], section["questions"]],
          ["Liquid d1-ultra", reference["run"], len(kept)])
    # The family: the other decision models (page_config.json's rule, Site.decision, on each model's Text tab run).
    config = json.loads((docs / "page_config.json").read_text(encoding="utf-8"))
    text_runs = {run["run"]: run for run in results["runs"]}
    others = [m for m in models if m is not reference
              and text_runs[m["turkish_run"]]["provider"] in config["decision_model_providers"]
              and text_runs[m["turkish_run"]]["model"] not in config["not_decision_models"]]
    check("models", [(m["name"], m["run"]) for m in section["models"]], [(m["name"], m["run"]) for m in others])

    def right(run: int) -> list[int]:
        return [int(english[run]["correct"][index] == 1) for index in kept]

    tests = [bm.paired_comparison(right(reference["run"]), right(m["run"])) for m in others]
    for published, model, test in zip(section["models"], others, tests):
        check(f"{model['name']} only d1-ultra right, only other right",
              [published["reference_only_right"], published["other_only_right"]], [test["first_only"], test["second_only"]])
        check(f"{model['name']} p", published["p"], test["p"], p=True)
    for published, model, adjusted in zip(section["models"], others, bm.holm([test["p"] for test in tests])):
        check(f"{model['name']} p_holm", published["p_holm"], adjusted, p=True)
    return mismatches


# The Text tab model of an English run's model where the names differ, by (provider, model): Liquid's API no longer
# serves the d1:free name of d1, so d1's English runs asked for d1 and its Text tab run for d1:free.
ENGLISH_TEXT_MODEL = {("liquid", "d1"): "d1:free"}


def check_english_reading(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int],
                          checks: Checks) -> list[str]:
    """Recompute results.json's `english_reading` from answers.json's `english_runs`, its Text tab runs and their
    repeats, and english-reading.json: the English prompts (the System One instructions naming English, hashed with
    sorted keys into the prompt version every decision model's English run carries, and the chat models' prompts in
    English, english_chat_prompts, into the version of every English run that reports no option probabilities), the
    translations every English run carries, the question counts, every English run asked exactly the kept questions,
    and per model: its English runs (one setup of provider, model, reasoning and questions per request, the first run
    without a repeat number first), its Text tab run (the main run of the same provider, model as ENGLISH_TEXT_MODEL
    maps it, reasoning and questions per request, without shuffled options) and that run's repeat set, its name, both
    sides' right, wrong and invalid
    answers and accuracy on the kept questions, the difference, the ranges and the answers that differ over each
    side's runs, and the right answers only the first English run or only the Text tab run gave (exact McNemar, Holm
    over every model); the models in order of English accuracy, then name. Every English run must be listed once and
    in no other list. Returns a line per mismatch."""
    section = results.get("english_reading")
    runs = {run["run"]: run for run in answers.get("english_runs", [])}
    listed = [run_id for model in (section or {}).get("models", []) for run_id in model["runs"]]
    others = {run["run"] for key in ("runs", "repeat_runs", "pipeline_runs", "batching_runs", "dont_know_runs",
                                     "english_dont_know_runs", "english_dont_know_turkish_runs", "dont_know_word_runs",
                                     "rerun_runs", "web_grounding_runs") for run in answers.get(key, [])}
    if sorted(listed) != sorted(runs) or set(listed) & others:
        checks.failed += 1
        return [f"  runs: results.json lists {sorted(listed)}, answers.json's english_runs {sorted(runs)}, also elsewhere "
                f"{sorted(set(listed) & others)}"]
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    prompts = answers.get("english_prompts") or {}
    version = hashlib.sha256(
        json.dumps(prompts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    check("instructions", section["instructions"], answers["prompts"]["system_one_instructions"].replace("Turkish", "English"))
    check("instructions in english_prompts", section["instructions"], prompts.get("system_one_instructions"))
    check("options heading", section["options_heading"], (prompts.get("options_heading") or "").strip())
    check("prompt version", section["prompt_version"], version)
    # The chat models' prompts in English (english_chat_prompts): a run of a System One provider (system_one) answered
    # with the System One instructions in English, any other with these.
    chat_prompts = answers.get("english_chat_prompts")
    chat_version = None if chat_prompts is None else hashed(chat_prompts)
    check("chat prompts", [section.get("chat_prompts"), section.get("chat_prompt_version")], [chat_prompts, chat_version])
    check("translations", section["translations_sha256"], public["translations_sha256"])
    ids = answers["questions"]["id"]
    position = {question: index for index, question in enumerate(ids)}
    kept = sorted(position[item["question_id"]] for item in public["questions"] if item["kept"] and item["question_id"] in position)
    flagged = sum(1 for item in public["questions"] if not item["kept"])
    check("reading questions", section["reading_questions"], len(public["questions"]))
    check("kept questions", [section["questions"], public["kept"]], [len(kept), len(kept)])
    check("flagged questions", [section["flagged"], public["flagged"]], [flagged, flagged])
    check("kept questions scored", True, set(kept) <= set(scored))
    for run_id, run in sorted(runs.items()):
        english = run.get("english") or {}
        asked = [index for index, value in enumerate(run["correct"]) if value is not None]
        expected = version if system_one(docs, run["provider"]) else chat_version
        check(f"English run {run_id}", [expected, public["translations_sha256"], len(kept), kept],
              [run["prompt_version"] if run["prompt_version"] == english.get("prompt_version") else None,
               english.get("translations_sha256"), english.get("questions"), asked])

    main = {run["run"]: run for run in answers["runs"]}
    named = {run["run"]: run for run in results["runs"]}
    repeat_sets = {run["repeat_set"][0]: run["repeat_set"] for run in answers.get("repeat_runs", [])}
    exported = {**main, **{run["run"]: run for run in answers.get("repeat_runs", [])}}
    setups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for run in runs.values():
        setups[(run["provider"], run["model"], run["thinking"], run["questions_per_request"], run.get("perplexity_mode"))].append(run)
    total = len(kept)

    def counts(run: dict[str, Any]) -> dict[str, Any]:
        right = sum(1 for index in kept if run["correct"][index] == 1)
        invalid = sum(1 for index in kept if run["choice"][index] is None)
        return {"right": right, "wrong": total - right - invalid, "invalid": invalid, "accuracy": right / total}

    expected = []
    for (provider, model, thinking, size, mode), group in setups.items():
        group.sort(key=lambda run: (run["repeat"] or 1, run["run"]))
        name = f"{model} ({provider})"
        check(f"{name}, English runs without a repeat number", 1, sum(1 for run in group if run["repeat"] is None))
        text_model = ENGLISH_TEXT_MODEL.get((provider, model), model)
        found = sorted(run["run"] for run in main.values()
                       if (run["provider"], run["model"], run["thinking"], run["questions_per_request"], run["shuffle_options"],
                           run.get("perplexity_mode")) == (provider, text_model, thinking, size, None, mode))
        check(f"{name}, Text tab run", 1, len(found))
        if len(found) != 1:
            continue
        turkish_run = found[0]
        expected.append({
            "name": named[turkish_run]["name"], "model": model, "provider": provider,
            "runs": [run["run"] for run in group], "turkish_run": turkish_run,
            "turkish_runs": repeat_sets.get(turkish_run, [turkish_run]),
        })
    by_run = {model["run"]: model for model in section["models"]}
    tests = []
    for item in expected:
        name = f"{item['name']} (English run {item['runs'][0]})"
        model = by_run.get(item["runs"][0])
        if model is None:
            checks.failed += 1
            mismatches.append(f"  {name}: not in results.json")
            continue
        check(f"{name}, identity", {key: model.get(key) for key in (*item, "run")}, {**item, "run": item["runs"][0]})
        sides = {"english": [runs[run_id] for run_id in item["runs"]],
                 "turkish": [exported[run_id] for run_id in item["turkish_runs"] if run_id in exported]}
        check(f"{name}, Text tab runs exported", len(item["turkish_runs"]), len(sides["turkish"]))
        check(f"{name}, repeat sets", [item["runs"]] * len(item["runs"]), [run["repeat_set"] for run in sides["english"]])
        found = {side: [counts(run) for run in group] for side, group in sides.items()}
        for side in sides:
            first = found[side][0]
            check(f"{name}, {side} counts", [model[side][key] for key in ("right", "wrong", "invalid")],
                  [first[key] for key in ("right", "wrong", "invalid")])
            check(f"{name}, {side} accuracy", model[side]["accuracy"], first["accuracy"], metric=True)
        check(f"{name}, difference", model["difference"], found["english"][0]["accuracy"] - found["turkish"][0]["accuracy"], metric=True)
        spread, changed = {}, {}
        for side, group in sides.items():
            values = [value["accuracy"] for value in found[side]]
            spread[side] = None if len(values) == 1 else (min(values), max(values))
            changed[side] = None if len(group) == 1 else sum(
                1 for index in kept if all(run["choice"][index] is not None for run in group)
                and len({run["choice"][index] for run in group}) > 1)
        published = model["spread"]
        for side in sides:
            given = None if published is None or published[side] is None else (published[side]["low"], published[side]["high"])
            matched = (given is None) == (spread[side] is None) and all(close(a, b, METRIC_TOLERANCE) for a, b in zip(given or (), spread[side] or ()))
            if "≠" in checks.cell(matched, str(spread[side]), str(given)):
                mismatches.append(f"  {name}, {side} range: {spread[side]} ≠ {given}")
        check(f"{name}, spread null", published is None, all(value is None for value in spread.values()))
        check(f"{name}, answers changed", model["answers_changed"],
              None if all(value is None for value in changed.values()) else changed)
        english_right = [int(sides["english"][0]["correct"][index] == 1) for index in kept]
        turkish_right = [int(sides["turkish"][0]["correct"][index] == 1) for index in kept]
        test = bm.paired_comparison(english_right, turkish_right)
        paired = model.get("paired") or {}
        check(f"{name}, only right in English, only in Turkish", [paired.get("english_only_right"), paired.get("turkish_only_right")],
              [test["first_only"], test["second_only"]])
        check(f"{name}, p", paired.get("p"), test["p"], p=True)
        tests.append((model, test["p"]))
    for (model, _), adjusted in zip(tests, bm.holm([p for _, p in tests])):
        check(f"{model['name']}, p_holm", model["paired"]["p_holm"], adjusted, p=True)
    order = [model["run"] for model in sorted(section["models"], key=lambda item: (-item["english"]["accuracy"], item["name"].casefold(), item["run"]))]
    check("model order", [model["run"] for model in section["models"]], order)
    return mismatches


def check_english_dont_know(docs: Path, results: dict[str, Any], answers: dict[str, Any], scored: list[int],
                            checks: Checks, tests_by_text_run: dict[int, dict[str, Any]] | None = None) -> list[str]:
    """Recompute results.json's `english_reading.dont_know` from answers.json's `english_dont_know_runs`,
    `english_dont_know_turkish_runs` and `dont_know_runs`, and english-reading.json: the option, its sentence, the
    instructions (the English instructions plus the sentence) and the prompt version (english_dont_know_prompts, the
    English prompts besides the instructions and the option, hashed with sorted keys); every English run with the option
    carries that version and the translations and was asked exactly the kept questions, every Turkish run on the kept
    questions carries the Turkish "I don't know" version (dont_know_prompts hashed), has a question list and was asked
    exactly the kept questions. Per setup of English runs (provider, model, reasoning, one question per request; the
    first run without a repeat number first): its name and Text tab run (as the English reading check finds them), its
    Turkish side (the same setup's runs on the kept questions in the same order, or else its full-bank runs with the
    option, the first run without a repeat number first), and on the kept questions per side from the first run: right,
    wrong, "I don't know" and invalid answers, accuracy, attempt rate, non-hallucination rate (None without "I don't
    know" or wrong answers) and mean probability of the option (DONT_KNOW_LETTER, the last label of every answer's
    option probabilities); the ranges over each side's runs (null rules as published); the wrong answers only one first
    last), then name. Every run must be listed once and in no other list. Each setup's recomputed paired test goes into
    `tests_by_text_run` under its Text tab run. Returns a line per mismatch."""
    section = (results.get("english_reading") or {}).get("dont_know")
    english_runs = {run["run"]: run for run in answers.get("english_dont_know_runs", [])}
    subset_runs = {run["run"]: run for run in answers.get("english_dont_know_turkish_runs", [])}
    full_runs = {run["run"]: run for run in answers.get("dont_know_runs", [])}
    models = (section or {}).get("models", [])
    english_only = (section or {}).get("english_only", [])
    listed_english = [run_id for model in models + english_only for run_id in model["english"]["runs"]]
    listed_subset = [run_id for model in models if model["turkish"]["subset"] for run_id in model["turkish"]["runs"]]
    listed_full = [run_id for model in models if not model["turkish"]["subset"] for run_id in model["turkish"]["runs"]]
    others = {run["run"] for key in ("runs", "repeat_runs", "pipeline_runs", "batching_runs", "dont_know_runs", "english_runs",
                                     "dont_know_word_runs", "rerun_runs", "web_grounding_runs")
              for run in answers.get(key, [])}
    if (sorted(listed_english) != sorted(english_runs) or sorted(listed_subset) != sorted(subset_runs)
            or (set(listed_english) | set(listed_subset)) & others or not set(listed_full) <= set(full_runs)
            or set(english_runs) & set(subset_runs)):
        checks.failed += 1
        return [f"  runs: results.json lists English {sorted(listed_english)} and Turkish on the kept questions "
                f"{sorted(listed_subset)}, answers.json {sorted(english_runs)} and {sorted(subset_runs)}, also elsewhere "
                f"{sorted((set(listed_english) | set(listed_subset)) & others)}; full-bank runs not in dont_know_runs "
                f"{sorted(set(listed_full) - set(full_runs))}"]
    if section is None:
        return []
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, metric: bool = False, p: bool = False) -> None:
        if p:
            matched = close(published, recomputed, relative=P_TOLERANCE)
        else:
            matched = close(published, recomputed, METRIC_TOLERANCE) if metric else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    def hashed(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]

    public = json.loads((docs / "english-reading.json").read_text(encoding="utf-8"))
    prompts = answers.get("english_dont_know_prompts") or {}
    english_prompts = answers.get("english_prompts") or {}
    option = prompts.get("dont_know_option")
    sentence = f"If you do not know the answer, choose {option}."
    version, turkish_version = hashed(prompts), hashed(answers.get("dont_know_prompts") or {})
    check("option", section["option"], option)
    check("sentence", section["sentence"], sentence)
    check("instructions", section["instructions"], f"{english_prompts.get('system_one_instructions')} {sentence}")
    check("instructions in english_dont_know_prompts", section["instructions"], prompts.get("system_one_instructions"))
    check("the other English prompts", {key: value for key, value in english_prompts.items() if key != "system_one_instructions"},
          {key: value for key, value in prompts.items() if key not in ("system_one_instructions", "dont_know_option")})
    check("prompt version", section["prompt_version"], version)
    chat_version = check_chat_prompts(section.get("chat"), answers.get("english_dont_know_chat_prompts"),
                                      answers.get("english_chat_prompts") or {}, option, check)
    position = {question: index for index, question in enumerate(answers["questions"]["id"])}
    kept = sorted(position[item["question_id"]] for item in public["questions"] if item["kept"] and item["question_id"] in position)
    total = len(kept)
    check("questions", [section["questions"], public["kept"]], [total, total])
    check("kept questions scored", True, set(kept) <= set(scored))
    for run_id, run in sorted(english_runs.items()):
        english = run.get("english") or {}
        asked = [index for index, value in enumerate(run["correct"]) if value is not None]
        # A run of a System One provider (system_one) answered with the System One instructions, any other with the chat prompts.
        expected_version = version if system_one(docs, run["provider"]) else chat_version
        check(f"English \"I don't know\" run {run_id} (option, versions, translations, questions, asked the kept ones)",
              [True, expected_version, expected_version, public["translations_sha256"], total, True],
              [bool(run.get("dont_know")), run["prompt_version"], english.get("prompt_version"),
               english.get("translations_sha256"), english.get("questions"), asked == kept])
    for run_id, run in sorted(subset_runs.items()):
        asked = [index for index, value in enumerate(run["correct"]) if value is not None]
        check(f"Turkish \"I don't know\" run {run_id} on the kept questions (option, English, list, version, asked the kept ones)",
              [True, None, True, turkish_version, True],
              [bool(run.get("dont_know")), run.get("english"), bool(run.get("question_list")), run["prompt_version"], asked == kept])

    def setups(runs: dict[int, dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for run in runs.values():
            grouped[(run["provider"], run["model"], run["thinking"], run["questions_per_request"], run.get("perplexity_mode"))].append(run)
        return grouped

    main = {run["run"]: run for run in answers["runs"]}
    named = {run["run"]: run for run in results["runs"]}
    subsets = setups(subset_runs)
    fulls = setups({run_id: run for run_id, run in full_runs.items() if not run.get("question_list")})
    expected = []
    expected_only = []
    only_runs = {item["text_run"] for item in english_only}
    reason = json.loads((docs / "page_config.json").read_text(encoding="utf-8"))["dont_know"]["running"]
    for (provider, model, thinking, size, mode), group in setups(english_runs).items():
        group.sort(key=lambda run: (run["repeat"] or 1, run["run"]))
        name = f"{model} ({provider})"
        check(f"{name}, English \"I don't know\" runs without a repeat number", 1, sum(1 for run in group if run["repeat"] is None))
        text_model = ENGLISH_TEXT_MODEL.get((provider, model), model)
        found = sorted(run["run"] for run in main.values()
                       if (run["provider"], run["model"], run["thinking"], run["questions_per_request"], run["shuffle_options"],
                           run.get("perplexity_mode")) == (provider, text_model, thinking, size, None, mode))
        check(f"{name}, Text tab run", 1, len(found))
        kind = group_of(docs, provider, model)
        subset, full = subsets.pop((provider, model, thinking, size, mode), None), fulls.get((provider, model, thinking, size, mode))
        alone = bool(found) and found[0] in only_runs
        # The Turkish side: the runs on the kept questions where the setup has them, else its full-bank runs.
        check(f"{name}, Turkish sides{' (published without one)' if alone else ''}", 0 if alone else 1,
              int(subset is not None or full is not None))
        if len(found) == 1 and alone and subset is None and full is None:
            expected_only.append(({"name": named[found[0]]["name"], "model": model, "provider": provider, "group": kind,
                                   "text_run": found[0], "running": kind == "chat",
                                   "english": {"run": group[0]["run"], "runs": [run["run"] for run in group]}}, group))
            continue
        if len(found) != 1 or alone or (subset is None and full is None):
            continue
        if subset is not None:
            subset.sort(key=lambda run: (run["repeat"] or 1, run["run"]))
            check(f"{name}, Turkish runs on the kept questions", 1, sum(1 for run in subset if run["repeat"] is None))
        else:
            full.sort(key=lambda run: (run["repeat"] is not None, run["run"]))
        turkish = subset or full
        expected.append((
            {"name": named[found[0]]["name"], "model": model, "provider": provider, "group": kind, "text_run": found[0],
             "english": {"run": group[0]["run"], "runs": [run["run"] for run in group]},
             "turkish": {"run": turkish[0]["run"], "runs": [run["run"] for run in turkish], "subset": subset is not None}},
            {"english": group, "turkish": turkish},
        ))
    check("Turkish runs on the kept questions without English runs", [], sorted(run["run"] for group in subsets.values() for run in group))
    rates = ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability")

    def counted(run: dict[str, Any]) -> dict[str, Any]:
        found = {"right": 0, "wrong": 0, "dont_know": 0, "invalid": 0}
        shown, unlabelled = [], 0
        for index in kept:
            choice, probabilities = run["choice"][index], run["probabilities"][index]
            if probabilities:
                last, value = option_last(run, probabilities)
                unlabelled += not last
                if value is not None:
                    shown.append(value)
            if choice is None:
                found["invalid"] += 1
            elif choice == DONT_KNOW_LETTER:
                found["dont_know"] += 1
            elif run["correct"][index] == 1:
                found["right"] += 1
            else:
                found["wrong"] += 1
        check(f"run {run['run']}, answers without {DONT_KNOW_LETTER} last", 0, unlabelled)
        return {
            **found,
            "accuracy": found["right"] / total,
            "attempt_rate": (found["right"] + found["wrong"]) / total,
            "non_hallucination": found["dont_know"] / (found["dont_know"] + found["wrong"]) if found["dont_know"] + found["wrong"] else None,
            "mean_dont_know_probability": sum(shown) / len(shown) if shown else None,
        }

    def wrong(run: dict[str, Any]) -> list[int]:
        return [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and run["correct"][index] != 1) for index in kept]

    by_run = {model["english"]["run"]: model for model in models}
    check("models", sorted(by_run), sorted(item["english"]["run"] for item, _ in expected))
    tests = []
    for item, sides in expected:
        name = f"{item['name']} (English \"I don't know\" run {item['english']['run']})"
        test = bm.paired_comparison(wrong(sides["english"][0]), wrong(sides["turkish"][0]))
        if tests_by_text_run is not None:
            tests_by_text_run[item["text_run"]] = test
        model = by_run.get(item["english"]["run"])
        if model is None:
            continue
        check(f"{name}, identity",
              {**{key: model.get(key) for key in ("name", "model", "provider", "group", "text_run")},
               "english": {key: model["english"].get(key) for key in ("run", "runs")},
               "turkish": {key: model["turkish"].get(key) for key in ("run", "runs", "subset")}}, item)
        for side in ("english", "turkish"):
            check(f"{name}, {side} repeat sets", [item[side]["runs"]] * len(sides[side]), [run["repeat_set"] for run in sides[side]])
        values = {side: [counted(run) for run in group] for side, group in sides.items()}
        for side in ("english", "turkish"):
            first, published = values[side][0], model[side]
            check(f"{name}, {side} counts", [published.get(key) for key in ("right", "wrong", "dont_know", "invalid")],
                  [first[key] for key in ("right", "wrong", "dont_know", "invalid")])
            check(f"{name}, {side} counts add up", total, sum(published.get(key, 0) for key in ("right", "wrong", "dont_know", "invalid")))
            for key in rates:
                check(f"{name}, {side} {key}", published.get(key), first[key], metric=True)
        spread = {
            side: None if len(found) == 1 else {
                key: None if any(value[key] is None for value in found) else [min(value[key] for value in found), max(value[key] for value in found)]
                for key in rates
            }
            for side, found in values.items()
        }
        published = model["spread"]
        check(f"{name}, spread null", published is None, all(value is None for value in spread.values()))
        for side in ("english", "turkish"):
            given = None if published is None else published.get(side)
            check(f"{name}, {side} range sides", given is None, spread[side] is None)
            for key in rates:
                low_high = None if given is None else given.get(key)
                computed = None if spread[side] is None else spread[side][key]
                matched = (low_high is None) == (computed is None) and all(
                    close(a, b, METRIC_TOLERANCE) for a, b in zip(low_high or [], computed or []))
                if "≠" in checks.cell(matched, str(computed), str(low_high)):
                    mismatches.append(f"  {name}, {side} {key} range: {computed} ≠ {low_high}")
        paired = model.get("paired") or {}
        check(f"{name}, wrong only in English, only in Turkish", [paired.get("english_only_wrong"), paired.get("turkish_only_wrong")],
              [test["first_only"], test["second_only"]])
        check(f"{name}, p", paired.get("p"), test["p"], p=True)
        tests.append((model, test["p"], item["group"]))
    # Holm's correction within each group: the decision models' family and the chat models'.
    for kind in ("decision", "chat"):
        family = [(model, p) for model, p, group in tests if group == kind]
        for (model, _), adjusted in zip(family, bm.holm([p for _, p in family])):
            check(f"{model['name']}, p_holm", model["paired"]["p_holm"], adjusted, p=True)
    order = [model["english"]["run"] for model in sorted(models, key=lambda item: (
        item["english"]["non_hallucination"] is None, -(item["english"]["non_hallucination"] or 0), item["name"].casefold(), item["english"]["run"]))]
    check("model order", [model["english"]["run"] for model in models], order)
    # English-only entries: the English first run's numbers, no Turkish run, in no Holm family.
    by_only = {model["english"]["run"]: model for model in english_only}
    check("English-only models", sorted(by_only), sorted(item["english"]["run"] for item, _ in expected_only))
    check("English-only models not among the paired ones", [], sorted(set(by_only) & set(by_run)))
    four = {item["text_run"] for item in (results.get("dont_know_english_option") or {}).get("models", [])}
    for item, group in expected_only:
        model = by_only.get(item["english"]["run"])
        if model is None:
            continue
        name = f"{item['name']} (English \"I don't know\" run {item['english']['run']}, English only)"
        check(f"{name}, identity",
              {**{key: model.get(key) for key in ("name", "model", "provider", "group", "text_run", "running")},
               "english": {key: model["english"].get(key) for key in ("run", "runs")}}, item)
        check(f"{name}, reason given", True, bool(model.get("reason")) and (not item["running"] or model["reason"] == reason))
        check(f"{name}, no Turkish side, no test, in no Holm family", [None, None, None, False],
              [model.get("turkish"), model.get("paired"), model.get("spread"), item["text_run"] in four])
        check(f"{name}, repeat sets", [item["english"]["runs"]] * len(group), [run["repeat_set"] for run in group])
        first, published = counted(group[0]), model["english"]
        check(f"{name}, counts", [published.get(key) for key in ("right", "wrong", "dont_know", "invalid")],
              [first[key] for key in ("right", "wrong", "dont_know", "invalid")])
        check(f"{name}, counts add up", total, sum(published.get(key, 0) for key in ("right", "wrong", "dont_know", "invalid")))
        for key in rates:
            check(f"{name}, {key}", published.get(key), first[key], metric=True)
    order = [model["english"]["run"] for model in sorted(english_only, key=lambda item: (
        item["english"]["non_hallucination"] is None, -(item["english"]["non_hallucination"] or 0), item["name"].casefold(), item["english"]["run"]))]
    check("English-only model order", [model["english"]["run"] for model in english_only], order)
    # Turkish-only entries: a chat model's Hallucination tab row of an English reading model's Text tab run whose English
    # run with the option is still running, its first run counted on the kept questions, in no Holm family.
    reading = {model["turkish_run"]: model for model in (results.get("english_reading") or {}).get("models", [])}
    # A chat row counts as paired when its setup's model has an English side, whether its Turkish side is that row or
    # its runs on the kept questions.
    paired_full = {model["turkish"]["run"] for model in models if not model["turkish"]["subset"]}
    paired_subset = {(model["text_run"], model["provider"], model["model"]) for model in models if model["turkish"]["subset"]}
    expected_turkish = [row for row in (results.get("dont_know") or {}).get("models", [])
                        if group_of(docs, row["provider"], row["model"]) == "chat" and row["original_run"] in reading
                        and row["run"] not in paired_full
                        and (row["original_run"], row["provider"], row["model"]) not in paired_subset]
    turkish_only = section.get("turkish_only", [])
    check("Turkish-only models", sorted(model["turkish"]["run"] for model in turkish_only), sorted(row["run"] for row in expected_turkish))
    by_turkish = {model["turkish"]["run"]: model for model in turkish_only}
    for row in expected_turkish:
        model = by_turkish.get(row["run"])
        if model is None:
            continue
        name = f"{row['name']} (Turkish run {row['run']}, Turkish only)"
        check(f"{name}, identity", {key: model.get(key) for key in ("name", "model", "provider", "group", "text_run", "running", "reason")},
              {"name": reading[row["original_run"]]["name"], "model": row["model"], "provider": row["provider"], "group": "chat",
               "text_run": row["original_run"], "running": True, "reason": reason})
        check(f"{name}, runs", {key: model["turkish"].get(key) for key in ("run", "runs", "subset")},
              {"run": row["run"], "runs": row["runs"], "subset": False})
        first, published = counted(full_runs[row["run"]]), model["turkish"]
        check(f"{name}, counts", [published.get(key) for key in ("right", "wrong", "dont_know", "invalid")],
              [first[key] for key in ("right", "wrong", "dont_know", "invalid")])
        for key in rates:
            check(f"{name}, {key}", published.get(key), first[key], metric=True)
    order = [model["turkish"]["run"] for model in sorted(turkish_only, key=lambda item: (
        item["turkish"]["non_hallucination"] is None, -(item["turkish"]["non_hallucination"] or 0), item["name"].casefold(), item["turkish"]["run"]))]
    check("Turkish-only model order", [model["turkish"]["run"] for model in turkish_only], order)
    return mismatches


ENGLISH_OPTION_FOUR = (199, 346, 373, 374)


def check_english_option_four(results: dict[str, Any], tests_by_text_run: dict[int, dict[str, Any]], checks: Checks) -> list[str]:
    """Recompute results.json's `dont_know_english_option`, Ümit's four-model English "I don't know" comparison: the
    Text tab runs ENGLISH_OPTION_FOUR in that order with their Text tab names, the kept questions, and per model the
    wrong answers only in English and only in Turkish of the first runs and the exact McNemar p (as recomputed by
    check_english_dont_know from the answers), with Holm's correction over these four. Returns a line per mismatch."""
    section = results.get("dont_know_english_option")
    if section is None:
        checks.failed += 1
        return ["  dont_know_english_option: missing from results.json"]
    mismatches = []

    def check(name: str, published: Any, recomputed: Any, p: bool = False) -> None:
        matched = close(published, recomputed, relative=P_TOLERANCE) if p else published == recomputed
        if "≠" in checks.cell(matched, str(recomputed), str(published)):
            mismatches.append(f"  {name}: {recomputed} ≠ {published}")

    named = {run["run"]: run["name"] for run in results["runs"]}
    models = section.get("models", [])
    check("models", [model.get("text_run") for model in models], list(ENGLISH_OPTION_FOUR))
    check("questions", section.get("questions"), ((results.get("english_reading") or {}).get("dont_know") or {}).get("questions"))
    check("Text tab runs recomputed", sorted(set(ENGLISH_OPTION_FOUR) - set(tests_by_text_run)), [])
    tests = [(model, tests_by_text_run.get(model.get("text_run"))) for model in models]
    for model, test in tests:
        name = f"{model.get('name')} (Text tab run {model.get('text_run')})"
        check(f"{name}, name", model.get("name"), named.get(model.get("text_run")))
        if test is None:
            continue
        check(f"{name}, wrong only in English, only in Turkish", [model.get("english_only_wrong"), model.get("turkish_only_wrong")],
              [test["first_only"], test["second_only"]])
        check(f"{name}, p", model.get("p"), test["p"], p=True)
    if all(test is not None for _, test in tests):
        for (model, _), adjusted in zip(tests, bm.holm([test["p"] for _, test in tests])):
            check(f"{model.get('name')}, p_holm over the four", model.get("p_holm"), adjusted, p=True)
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


# The cost bases results.json may give a priced run, by billing, keyed by the price's applies_to.
COST_BASES = {"api": {"billed": "api"}, "subscription": {"billed": "subscription"}, "free": {"free tier": "free tier"},
              "local": {"maker": "maker", "weights": "weights", "gpu": "gpu"}}


def gpu_cost(seconds: float, price: dict[str, Any]) -> float:
    """A GPU-time estimate (applies_to "gpu"): the request time on the price's GPUs at its rate per GPU-hour."""
    return seconds / 3600 * price["gpus"] * price["usd_per_gpu_hour"]


def billed_cost(price: dict[str, Any], tokens: dict[str, int], requests: int, seconds: float | None) -> float:
    """A cost from its parts: a GPU-time estimate from its request time, otherwise the tokens at the price's rates, with
    the input tokens the provider bills per request beyond our count and its fee per request (web grounding's search,
    counted for every request: the cost is then an upper bound)."""
    if price.get("applies_to") == "gpu":
        return gpu_cost(seconds, price)
    billed = dict(tokens)
    billed["input_tokens"] += price.get("extra_input_per_request", 0) * requests
    return token_cost(billed, price["rates"]) + price.get("per_request", 0) * requests


def check_costs(results: dict[str, Any], checks: Checks) -> list[str]:
    """Check every cost results.json publishes against its parts; returns a line per mismatch."""
    prices = {(price["provider"], price["model"], price.get("perplexity_mode")): price for price in results["prices"]}
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
        price = prices.get((run["provider"], run["model"], run.get("perplexity_mode")))
        if price is None:
            # A run without a price must say why: our own GPUs, and no request time to estimate its GPU time from.
            matched = (run["api_equivalent_usd"] is None and run["billing"] == "local" and run["cost_basis"] is None
                       and not run["request_seconds"])
            cell = checks.cell(matched, "no price (local, no request time)",
                               f"{run['api_equivalent_usd']} ({run['billing']}, {run['cost_basis']})")
            if "≠" in cell:
                mismatches.append(f"  run {run['run']} ({label(run)}): {cell}")
            continue
        applies = price.get("applies_to", "billed")
        basis = COST_BASES[run["billing"]].get(applies)
        cell = checks.cell(basis is not None and run["cost_basis"] == basis, f"{basis} ({applies})",
                           f"{run['cost_basis']} ({applies})")
        if "≠" in cell:
            mismatches.append(f"  run {run['run']} ({label(run)}), cost basis: {cell}")
        check(f"run {run['run']} ({label(run)})", run["api_equivalent_usd"],
              billed_cost(price, tokens(run), run["requests"] or 0, run["request_seconds"]))
        check(f"run {run['run']} ({label(run)}), upper bound", float(run.get("cost_upper_bound", False)),
              float(run.get("perplexity_mode") == "web_grounding" and bool(price.get("per_request"))))
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
        rates = prices[(frontier["provider"], frontier["model"], frontier.get("perplexity_mode"))]["rates"]
        name = f"routing test {label(decision)} → {label(frontier)}"
        share = decision["api_equivalent_usd"] * item["held_out"] / decision["answered_questions"]
        check(f"{name}, decision model's share", measured["decision_cost_usd"], share)
        check(f"{name}, pipeline", measured["cost_usd"], share + token_cost(measured["pipeline_tokens"], rates))
        check(f"{name}, frontier alone", measured["frontier_cost_usd"], token_cost(measured["alone_tokens"], rates))
        for alternative in measured["alternatives"]:
            check(
                f"{name}, {alternative['name']} alone",
                alternative["cost_usd"],
                billed_cost(prices[(alternative["provider"], alternative["model"], alternative.get("perplexity_mode"))],
                            alternative["tokens"], 0, alternative["request_seconds"]),
            )
    # The English reading track's costs and times (english_reading.models[].cost and .latency, Ümit via Zeki #1189):
    # the first English run's tokens at the price it carries, its cost per 1,000 of the kept questions and its basis for
    # its billing; the Text tab side as its main run publishes it.
    english = results.get("english_reading") or {}
    for model in english.get("models", []):
        run = runs[model["turkish_run"]]
        name = f"English run {model['run']} ({model['name']})"
        side = model["cost"]["english"]
        if side is not None:
            price = side["price"]
            check(f"{name}, cost", side["usd"], billed_cost(price, side["tokens"], side["requests"] or 0, side.get("request_seconds")))
            check(f"{name}, cost per 1,000 questions", side["per_1000"], 1000 * side["usd"] / english["questions"])
            applies = price.get("applies_to", "billed")
            basis = COST_BASES[side["billing"]].get(applies)
            cell = checks.cell(basis is not None and side["basis"] == basis, f"{basis} ({applies})", f"{side['basis']} ({applies})")
            if "≠" in cell:
                mismatches.append(f"  {name}, cost basis: {cell}")
        expected = None if run["api_equivalent_usd"] is None else {
            "usd": run["api_equivalent_usd"], "per_1000": per_thousand(run), "basis": run["cost_basis"],
            "upper_bound": run["cost_upper_bound"]}
        latency = run.get("latency")
        expected_latency = None if latency is None else {
            "median_request_seconds": latency["median_request_seconds"], "p90_request_seconds": latency["p90_request_seconds"],
            "concurrency": latency["concurrency"], "questions_per_request": run["questions_per_request"], "source": latency["source"]}
        cell = checks.cell([model["cost"]["turkish"], model["latency"]["turkish"]] == [expected, expected_latency],
                           "the Text tab run's cost and time", "a different cost or time")
        if "≠" in cell:
            mismatches.append(f"  {name}, Text tab side: {cell}")
    return mismatches


if __name__ == "__main__":
    sys.exit(main())
