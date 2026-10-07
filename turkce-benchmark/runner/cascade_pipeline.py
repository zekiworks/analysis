#!/usr/bin/env python3
"""Plan a cascade pipeline: split the questions, fix the threshold, and write the question lists.

    ./cascade_pipeline.py NAME --decision RUN_ID --frontier RUN_ID [--seed 1] [--tolerance 0.5]

The questions both stored runs answered, graded against the current question bank, are split into two
halves at random; questions that share a passage stay together. On the calibration half the threshold is
fixed with the Cascade table's rule (the lowest decision-model score that keeps the frontier run's
accuracy). On the held-out half, the questions scored at or above it are routed to the decision model and
the rest passed on to the frontier model.

Writes pipeline/NAME.json, the plan the report reads, and two question lists for
`benchmark_ollama.py --questions`: pipeline/NAME-passed.txt (the frontier configuration's pipeline run)
and pipeline/NAME-held-out.txt (the same configuration on every held-out question, for comparison).
The tolerance is the accuracy loss, in percentage points, accepted before the runs are made.
"""

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

import benchmark_metrics as bm
import benchmark_ollama as bo

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", help="the plan's name, used for its files")
    parser.add_argument("--decision", type=int, required=True, help="run ID of the decision model's stored run")
    parser.add_argument("--frontier", type=int, required=True, help="run ID of the frontier model's stored run")
    parser.add_argument("--seed", type=int, default=1, help="seed of the split (default 1)")
    parser.add_argument("--tolerance", type=float, default=0.5, help="accepted accuracy loss in points (default 0.5)")
    parser.add_argument("--report", type=Path, default=HERE / "benchmark-results.md")
    parser.add_argument("--database", type=Path, default=HERE / "benchmark-results.sqlite")
    args = parser.parse_args()

    results = {item["run_id"]: item for item in bo.read_results(args.report).values()}
    missing = [run_id for run_id in (args.decision, args.frontier) if run_id not in results]
    if missing:
        parser.error(f"runs not in the report: {missing}")
    decision, frontier = results[args.decision], results[args.frontier]
    connection = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    decided = bo.run_outcomes(connection, decision, args.report.parent, with_scores=True)
    answered = bo.run_outcomes(connection, frontier, args.report.parent)
    questions = sorted(set(decided) & set(answered))
    if any(decided[question][1] is None for question in questions):
        parser.error(f"run {args.decision} has answers without a score")

    clusters = bo.passage_clusters(decision["dataset"], str(args.report.parent))
    members: dict[str, list[int]] = {}
    for question in questions:
        members.setdefault(clusters.get(question, f"question {question}"), []).append(question)
    units = sorted(members.values())
    random.Random(args.seed).shuffle(units)
    calibration = sorted(question for unit in units[: len(units) // 2] for question in unit)
    held_out = sorted(question for unit in units[len(units) // 2 :] for question in unit)

    fitted = bm.cascade(
        [decided[question][1] for question in calibration],
        [decided[question][0] for question in calibration],
        [answered[question][0] for question in calibration],
        splits=1,
    )["in_sample"]
    threshold = fitted["threshold"]
    if threshold is None:
        print("No threshold keeps the frontier run's accuracy on the calibration half.", file=sys.stderr)
        return 1
    routed = [question for question in held_out if decided[question][1] >= threshold]
    passed = [question for question in held_out if decided[question][1] < threshold]

    folder = args.report.parent / "pipeline"
    folder.mkdir(exist_ok=True)
    plan = {
        "name": args.name,
        "decision": decision["run_key"],
        "frontier": frontier["run_key"],
        "seed": args.seed,
        "tolerance_points": args.tolerance,
        "threshold": threshold,
        "calibration": calibration,
        "held_out": held_out,
        "routed": routed,
        "passed": passed,
    }
    (folder / f"{args.name}.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    for suffix, listed in (("passed", passed), ("held-out", held_out)):
        (folder / f"{args.name}-{suffix}.txt").write_text("".join(f"{question}\n" for question in listed), encoding="utf-8")
    print(
        f"{args.name}: threshold {threshold:.4f} (calibration: {len(calibration)} questions, "
        f"{100 * fitted['answered']:.1f}% answered by the decision model); held out: {len(held_out)} questions, "
        f"{len(routed)} routed to the decision model, {len(passed)} passed on"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
