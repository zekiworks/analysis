"""Accuracy, confidence and run-comparison metrics for the benchmark report.

Pure functions over per-question outcomes, with no database or file access. A scored outcome is a
(score, correct) pair: the score is the model's confidence in its answer (the probability of the
chosen option, or the confidence the model states) and correct is 1 or 0. Answers with equal scores
are tied; a metric that cuts through a tie takes the expected value over the order within the tie.
"""

from __future__ import annotations

import bisect
import itertools
import math
import random
import statistics
import string
from collections import defaultdict
from typing import Any, Callable, Sequence

# Intervals of the report's confidence table. Each includes its lower bound; the last also includes 1.0.
CONFIDENCE_BINS = ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.0))
COVERAGES = (0.2, 0.5, 0.8)
CALIBRATION_BINS = 10
CURVE_POINTS = 50
# Scores that count as very sure, and below which an answer counts as doubtful.
SURE_SCORE = 0.99
DOUBTFUL_SCORE = 0.70
BOOTSTRAP_RESAMPLES = 1000


def tie_groups(scored: Sequence[tuple[float, int]]) -> list[tuple[float, int, int]]:
    """(score, answers, correct answers) per distinct score, highest score first."""
    groups: dict[float, list[int]] = {}
    for value, correct in scored:
        group = groups.setdefault(value, [0, 0])
        group[0] += 1
        group[1] += correct
    return [(value, count, correct) for value, (count, correct) in sorted(groups.items(), reverse=True)]


def expected_correct(groups: Sequence[tuple[float, int, int]], taken: float) -> float:
    """Expected correct answers among the `taken` most confident ones (fractional within a tie)."""
    total = 0.0
    remaining = taken
    for _, count, correct in groups:
        take = min(count, remaining)
        if take <= 0:
            break
        total += take * correct / count
        remaining -= take
    return total


def accuracy_at_coverage(groups: Sequence[tuple[float, int, int]], coverage: float) -> float:
    """Accuracy of the most confident `coverage` share of the answers."""
    taken = coverage * sum(count for _, count, _ in groups)
    return expected_correct(groups, taken) / taken


def risk_coverage(groups: Sequence[tuple[float, int, int]]) -> tuple[float, list[list[float]]]:
    """Area under the risk–coverage curve, and the curve at CURVE_POINTS even coverages.

    Risk is the error rate of the k most confident answers; the area is its mean over k = 1 … n.
    """
    n = sum(count for _, count, _ in groups)
    area = 0.0
    taken = correct_before = 0
    for _, count, correct in groups:
        for k in range(1, count + 1):
            area += 1 - (correct_before + k * correct / count) / (taken + k)
        taken += count
        correct_before += correct
    curve = [
        [round(point / CURVE_POINTS, 4), round(1 - accuracy_at_coverage(groups, point / CURVE_POINTS), 4)]
        for point in range(1, CURVE_POINTS + 1)
    ]
    return area / n, curve


def auroc(scored: Sequence[tuple[float, int]]) -> float | None:
    """Probability that a correct answer outscores a wrong one (ties count half); None without both."""
    positives = sum(correct for _, correct in scored)
    negatives = len(scored) - positives
    if not positives or not negatives:
        return None
    rank_sum = 0.0
    rank = 1
    for _, count, correct in reversed(tie_groups(scored)):  # lowest score first
        rank_sum += correct * (rank + (count - 1) / 2)
        rank += count
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def ranking_metrics(scored: Sequence[tuple[float, int]]) -> dict[str, Any]:
    """How well the scores order the answers from right to wrong."""
    groups = tie_groups(scored)
    area, curve = risk_coverage(groups)
    return {
        "auroc": auroc(scored),
        "aurc": area,
        "coverage_accuracy": {f"{coverage:.2f}": accuracy_at_coverage(groups, coverage) for coverage in COVERAGES},
        "risk_coverage": curve,
    }


def calibration(scored: Sequence[tuple[float, int]]) -> dict[str, Any]:
    """Expected calibration error over CALIBRATION_BINS equal bins, Brier score, and the bins themselves."""
    bins = [[0, 0.0, 0] for _ in range(CALIBRATION_BINS)]  # answers, summed score, correct answers
    for value, correct in scored:
        value = min(max(value, 0.0), 1.0)
        index = min(int(value * CALIBRATION_BINS), CALIBRATION_BINS - 1)
        bins[index][0] += 1
        bins[index][1] += value
        bins[index][2] += correct
    n = len(scored)
    ece = sum(abs(correct / count - total / count) * count / n for count, total, correct in bins if count)
    brier = sum((min(max(value, 0.0), 1.0) - correct) ** 2 for value, correct in scored) / n
    reliability = [
        {
            "low": index / CALIBRATION_BINS,
            "high": (index + 1) / CALIBRATION_BINS,
            "questions": count,
            "mean_confidence": total / count if count else None,
            "accuracy": correct / count if count else None,
        }
        for index, (count, total, correct) in enumerate(bins)
    ]
    return {"ece": ece, "brier": brier, "reliability": reliability}


def confidence_bin(value: float) -> int:
    """The index of the CONFIDENCE_BINS interval a score falls in."""
    return sum(value >= low for low, _ in CONFIDENCE_BINS[1:])


def binned_accuracy(scored: Sequence[tuple[float, int]]) -> list[dict[str, Any]]:
    """Answers and correct answers per CONFIDENCE_BINS interval."""
    bins = [{"low": low, "high": high, "questions": 0, "correct": 0} for low, high in CONFIDENCE_BINS]
    for value, correct in scored:
        interval = bins[confidence_bin(value)]
        interval["questions"] += 1
        interval["correct"] += correct
    return bins


def sign_test(first: int, second: int) -> float:
    """Exact two-sided p-value that two counts arose with equal chances (the sign test)."""
    total = first + second
    if not total:
        return 1.0
    return min(1.0, 2 * sum(math.comb(total, i) for i in range(min(first, second) + 1)) / 2**total)


def wilson_interval(correct: int, total: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval of a proportion; None without answers."""
    if not total:
        return None
    share = correct / total
    denominator = 1 + z * z / total
    centre = (share + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def score_extremes(scored: Sequence[tuple[float, int]]) -> dict[str, Any]:
    """Median score of right and of wrong answers, and the answers scored at least SURE_SCORE and below
    DOUBTFUL_SCORE with how many of each are right and the Wilson interval of that share."""
    right = [score for score, correct in scored if correct]
    wrong = [score for score, correct in scored if not correct]
    sure = [correct for score, correct in scored if score >= SURE_SCORE]
    doubtful = [correct for score, correct in scored if score < DOUBTFUL_SCORE]
    return {
        "median_right": statistics.median(right) if right else None,
        "median_wrong": statistics.median(wrong) if wrong else None,
        "sure": {"questions": len(sure), "correct": sum(sure), "interval": wilson_interval(sum(sure), len(sure))},
        "doubtful": {
            "questions": len(doubtful),
            "correct": sum(doubtful),
            "interval": wilson_interval(sum(doubtful), len(doubtful)),
        },
    }


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-adjusted p-values for one family of tests, in the input order."""
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def tied_groups(count: int, separated: Callable[[int, int], bool]) -> list[str]:
    """Letters for `count` runs in rank order, a complete compact letter display: two runs share a letter
    exactly when `separated(i, j)` does not tell them apart, so a letter can skip runs in between.

    Piepho's insert-and-absorb method: start with one letter for every run; for each separated pair,
    split every letter that holds both into one without the first run and one without the second, then
    drop any letter whose runs another letter also holds. Letters are named in the order of their
    best-ranked run."""
    columns: list[frozenset[int]] = [frozenset(range(count))] if count else []
    for first, second in itertools.combinations(range(count), 2):
        if not separated(first, second):
            continue
        split: list[frozenset[int]] = []
        for column in columns:
            split.extend([column - {first}, column - {second}] if first in column and second in column else [column])
        unique = list(dict.fromkeys(split))
        columns = [column for column in unique if not any(column < other for other in unique)]
    # One character per letter, so a run's letters can be read back from their string.
    alphabet = string.ascii_lowercase + string.ascii_uppercase
    ordered = sorted(columns, key=lambda column: sorted(column))
    if len(ordered) > len(alphabet):
        raise ValueError(f"{len(ordered)} letters needed, more than the {len(alphabet)} available")
    letters = [""] * count
    for letter, column in zip(alphabet, ordered):
        for run in sorted(column):
            letters[run] += letter
    return letters


def bootstrap_ranking(
    scored: Sequence[tuple[float, int]], clusters: Sequence[Any], resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 0
) -> dict[str, Any]:
    """95% percentile intervals of AUROC and of the accuracy at each COVERAGES share.

    Each seeded resample draws clusters with replacement, as many as there are, where answers to
    questions that share a passage form one cluster. Ties count as in auroc and accuracy_at_coverage.
    """
    levels = sorted({score for score, _ in scored}, reverse=True)
    level_of = {score: index for index, score in enumerate(levels)}
    members: dict[Any, list[tuple[int, int]]] = defaultdict(list)
    for (score, correct), cluster in zip(scored, clusters, strict=True):
        members[cluster].append((level_of[score], correct))
    groups = list(members.values())
    rng = random.Random(seed)
    aurocs: list[float] = []
    accuracies: dict[float, list[float]] = {coverage: [] for coverage in COVERAGES}
    for _ in range(resamples):
        right, count = [0] * len(levels), [0] * len(levels)
        for group in rng.choices(groups, k=len(groups)):
            for level, correct in group:
                right[level] += correct
                count[level] += 1
        total, total_right = sum(count), sum(right)
        total_wrong = total - total_right
        # One pass from the highest score down: AUROC pairs and the cumulative counts for the coverages.
        wrong_below, pairs = total_wrong, 0.0
        cumulative_count, cumulative_right = [], []
        seen = seen_right = 0
        for level in range(len(levels)):
            wrong = count[level] - right[level]
            wrong_below -= wrong
            pairs += right[level] * (wrong_below + wrong / 2)
            seen += count[level]
            seen_right += right[level]
            cumulative_count.append(seen)
            cumulative_right.append(seen_right)
        if total_right and total_wrong:
            aurocs.append(pairs / (total_right * total_wrong))
        for coverage in COVERAGES:
            taken = coverage * total
            level = bisect.bisect_left(cumulative_count, taken)
            before, before_right = (cumulative_count[level - 1], cumulative_right[level - 1]) if level else (0, 0)
            gained = before_right + right[level] * (taken - before) / count[level]
            accuracies[coverage].append(gained / taken)

    def interval(values: list[float]) -> list[float] | None:
        if not values:
            return None
        values.sort()
        return [values[int(0.025 * (len(values) - 1))], values[math.ceil(0.975 * (len(values) - 1))]]

    return {
        "resamples": resamples,
        "auroc": interval(aurocs),
        "coverage_accuracy": {f"{coverage:.2f}": interval(values) for coverage, values in accuracies.items()},
    }


def entropy_bits(probabilities: Sequence[float]) -> float:
    """Shannon entropy in bits: 0 when one option has all the probability."""
    return -sum(p * math.log2(p) for p in probabilities if p > 0)


def average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks from 1, with tied values sharing their average rank."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def spearman(
    first: Sequence[float], second: Sequence[float], groups: Sequence[Any], shuffles: int = 200, seed: int = 0
) -> dict[str, float | None]:
    """Spearman rank correlation, and the one-sided p-value of shuffling `second` within each group.

    A within-group shuffle keeps every group's values, so a correlation that only separates easy groups
    from hard ones survives every shuffle and gets p = 1. p counts the observed order as one shuffle.
    rho and p are None when either sequence is constant.
    """
    rank_first, rank_second = average_ranks(first), average_ranks(second)
    middle = (len(first) + 1) / 2  # the mean rank of both sequences
    centered = [rank - middle for rank in rank_first]
    spread = math.sqrt(sum(c * c for c in centered) * sum((rank - middle) ** 2 for rank in rank_second))
    if not spread:
        return {"rho": None, "p": None}

    def correlation(ranks: Sequence[float]) -> float:
        # Shuffling permutes the second ranks, so their mean and spread stay the same.
        return sum(c * rank for c, rank in zip(centered, ranks)) / spread

    observed = correlation(rank_second)
    members: dict[Any, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        members[group].append(index)
    rng = random.Random(seed)
    shuffled = list(rank_second)
    reached = 0
    for _ in range(shuffles):
        for indices in members.values():
            values = [rank_second[index] for index in indices]
            rng.shuffle(values)
            for index, value in zip(indices, values):
                shuffled[index] = value
        reached += correlation(shuffled) >= observed - 1e-12
    return {"rho": observed, "p": (reached + 1) / (shuffles + 1)}


def paired_comparison(first: Sequence[int], second: Sequence[int]) -> dict[str, Any]:
    """Accuracy difference of two runs on the same questions: exact McNemar test and paired 95% interval."""
    if len(first) != len(second) or not first:
        raise ValueError("paired runs need the same, non-empty question list")
    first_only = sum(1 for a, b in zip(first, second) if a and not b)
    second_only = sum(1 for a, b in zip(first, second) if b and not a)
    n = len(first)
    discordant = first_only + second_only
    p = sign_test(first_only, second_only)
    difference = (first_only - second_only) / n
    error = math.sqrt(discordant - (first_only - second_only) ** 2 / n) / n
    return {
        "questions": n,
        "first_only": first_only,
        "second_only": second_only,
        "difference": difference,
        "low": difference - 1.96 * error,
        "high": difference + 1.96 * error,
        "p": p,
    }


def version_change(older: dict[int, tuple[int, Any, Any]], newer: dict[int, tuple[int, Any, Any]]) -> dict[str, Any]:
    """How one configuration's answers moved between two versions of a question bank.

    Each argument maps question IDs to (correct, text, answer), where text is whatever identifies the
    question as asked (its prompt and key) and answer the option chosen. Questions whose text changed
    show what the edits did; questions asked identically show the run-to-run variation: answers that
    flipped between right and wrong, answers that changed at all, and the newer run's wrong answers that
    repeat the older run's choice (mistakes that asking again would not have revealed).
    """
    common = sorted(set(older) & set(newer))
    changed = [question for question in common if older[question][1] != newer[question][1]]
    unchanged = [question for question in common if older[question][1] == newer[question][1]]
    added = [question for question in newer if question not in older]

    def part(questions: list[int]) -> dict[str, Any]:
        if not questions:
            return {"questions": 0}
        test = paired_comparison([newer[q][0] for q in questions], [older[q][0] for q in questions])
        wrong = [q for q in questions if not newer[q][0]]
        return {
            "questions": len(questions),
            "older_correct": sum(older[q][0] for q in questions),
            "newer_correct": sum(newer[q][0] for q in questions),
            "flipped": test["first_only"] + test["second_only"],
            "changed_answer": sum(older[q][2] != newer[q][2] for q in questions),
            "newer_wrong": len(wrong),
            "repeated_mistakes": sum(older[q][2] == newer[q][2] for q in wrong),
            "p": test["p"],
        }

    return {
        "changed": part(changed),
        "unchanged": part(unchanged),
        "added": {"questions": len(added), "newer_correct": sum(newer[q][0] for q in added)},
        "removed": len(set(older) - set(newer)),
    }


def repeat_stability(runs: Sequence[dict[int, tuple[int, Any, float | None]]]) -> dict[str, Any]:
    """How repeated runs of one configuration agree, on the questions every run answered.

    Each run maps question IDs to (correct, chosen option, score). Changed answer: questions on which the
    runs did not all choose the same option. Wrong in every run, same option: questions every run got
    wrong with the same option, mistakes no repeat would reveal. Score spread: per question, the largest
    minus the smallest score of the chosen options, over the questions every run scored.
    """
    questions = sorted(set.intersection(*(set(run) for run in runs))) if runs else []
    if not questions:
        return {"runs": len(runs), "questions": 0}
    choices = {question: {run[question][1] for run in runs} for question in questions}
    wrong_any = [question for question in questions if any(not run[question][0] for run in runs)]
    spreads = [
        max(scores) - min(scores)
        for question in questions
        if None not in (scores := [run[question][2] for run in runs])
    ]
    sure_wrong = [
        [question for question in questions if not run[question][0] and (run[question][2] or 0.0) >= SURE_SCORE]
        for run in runs
    ]
    return {
        "runs": len(runs),
        "questions": len(questions),
        "accuracy": [sum(run[question][0] for question in questions) / len(questions) for run in runs],
        "changed_answer": sum(len(choices[question]) > 1 for question in questions),
        "wrong_any": len(wrong_any),
        "wrong_every_run_same": sum(
            all(not run[question][0] for run in runs) and len(choices[question]) == 1 for question in wrong_any
        ),
        "scored": len(spreads),
        "score_spread_median": statistics.median(spreads) if spreads else None,
        "score_identical": sum(spread == 0 for spread in spreads),
        "sure_wrong": [len(questions_wrong) for questions_wrong in sure_wrong],
        "sure_wrong_every_run": len(set.intersection(*(set(questions_wrong) for questions_wrong in sure_wrong))),
    }


def cascade(
    decision_scores: Sequence[float],
    decision_correct: Sequence[int],
    frontier_correct: Sequence[int],
    splits: int = 300,
    seed: int = 0,
    clusters: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """A decision model answers when its score is at or above a threshold; a frontier run answers the rest.

    A threshold keeps the frontier run's accuracy when the decision model is right at least as often as
    the frontier run on the questions it answers. In sample, the lowest such threshold (the most
    questions answered by the decision model) is chosen and scored on all questions. Held out, it is
    chosen among the scores of a random half of the questions and scored on the other half, over
    `splits` seeded splits; questions in one cluster (sharing a passage) always fall in the same half.
    The sequences are aligned by question.
    """
    n = len(decision_scores)
    if not n or n != len(decision_correct) or n != len(frontier_correct):
        raise ValueError("cascade runs need the same, non-empty question list")
    thresholds = sorted(set(decision_scores), reverse=True)
    rank = {value: index for index, value in enumerate(thresholds)}
    level = [rank[value] for value in decision_scores]  # index into thresholds; 0 is the highest score

    def totals(items: Sequence[int]) -> tuple[list[int], list[int]]:
        """Questions and the decision model's net correct answers over the frontier run's, per level."""
        count, gain = [0] * len(thresholds), [0] * len(thresholds)
        for item in items:
            count[level[item]] += 1
            gain[level[item]] += decision_correct[item] - frontier_correct[item]
        return count, gain

    def lowest_threshold(items: Sequence[int]) -> int:
        """The level of the lowest threshold, among the scores of `items`, that keeps the frontier run's
        accuracy on them; -1 when none does."""
        count, gain = totals(items)
        chosen, net = -1, 0
        for index in range(len(thresholds)):
            if count[index]:
                net += gain[index]
                if net >= 0:
                    chosen = index
        return chosen

    frontier_total = sum(frontier_correct)
    count, gain = totals(range(n))
    curve = [[0.0, frontier_total / n]]
    answered = net = 0
    for index in range(len(thresholds)):
        answered += count[index]
        net += gain[index]
        curve.append([answered / n, (frontier_total + net) / n])
    chosen = lowest_threshold(range(n))

    members: dict[Any, list[int]] = defaultdict(list)
    for item, cluster in enumerate(range(n) if clusters is None else clusters):
        members[cluster].append(item)
    units = list(members.values())
    rng = random.Random(seed)
    half = len(units) // 2
    shares = differences = 0.0
    worse = 0
    for _ in range(splits):
        order = list(range(len(units)))
        rng.shuffle(order)
        test = [item for unit in order[half:] for item in units[unit]]
        chosen_level = lowest_threshold([item for unit in order[:half] for item in units[unit]])
        taken = [item for item in test if level[item] <= chosen_level]
        difference = sum(decision_correct[item] - frontier_correct[item] for item in taken) / len(test)
        shares += len(taken) / len(test)
        differences += difference
        worse += difference < 0
    return {
        "questions": n,
        "frontier_accuracy": frontier_total / n,
        "decision_accuracy": sum(decision_correct) / n,
        "in_sample": {
            "threshold": thresholds[chosen] if chosen >= 0 else None,
            "answered": sum(count[: chosen + 1]) / n,
            "accuracy": (frontier_total + sum(gain[: chosen + 1])) / n,
        },
        "held_out": {
            "splits": splits,
            "answered": shares / splits,
            "difference": differences / splits,
            "worse": worse / splits,
        },
        "curve": thin_curve(curve),
    }


def thin_curve(curve: list[list[float]], step: float = 0.01) -> list[list[float]]:
    """Keep a point at most every `step` of the x axis, plus the last point."""
    kept: list[list[float]] = []
    for point in curve:
        if not kept or point[0] - kept[-1][0] >= step:
            kept.append([round(point[0], 4), round(point[1], 4)])
    if kept[-1][0] != round(curve[-1][0], 4):
        kept.append([round(curve[-1][0], 4), round(curve[-1][1], 4)])
    return kept
