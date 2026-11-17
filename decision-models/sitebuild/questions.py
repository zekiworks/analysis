"""data/picks.json: each leaderboard setup's outcome on each scored question, for the Compare page's paired tests
(compare.js). An outcome only, one character per question, reading and grammar apart, in the order of the book: R right,
W wrong, N no valid answer (counted wrong). No question ID, topic, page, printed number, key, pick or score stands
beside it: no bench publishes its questions, and nothing published per question may rebuild the answer key (Ümit
#10760, #10764 via Zeki #11435; publish_projection.py projects the answer files the same way). No page lists the
questions; Topics and each setup's page give the aggregates."""

from __future__ import annotations

import json
from typing import Any

from sitebuild.site import ROOT, Site

PICKS = ROOT / "data" / "picks.json"
PARTS = ("reading", "grammar")


def outcomes(site: Site, run: dict[str, Any]) -> dict[str, str]:
    """The run's outcome on each scored question, by part. A pick that matches the key is a right answer: checked here
    against answers.json's grading, and each part's right answers and questions against results.json's groups."""
    questions = site.answers["questions"]
    answers = site.answer_runs[run["run"]]
    out: dict[str, list[str]] = {part: [] for part in PARTS}
    for index in site.scored:
        choice, correct = answers["choice"][index], answers["correct"][index]
        valid = isinstance(choice, str) and len(choice) == 1
        if (valid and choice == questions["key"][index]) != bool(correct):
            raise ValueError(f"run {run['run']}: pick {choice!r} and its grade disagree on question {questions['id'][index]}")
        out[site.part(questions["unit"][index])].append("R" if correct else "W" if valid else "N")
    for part in PARTS:
        group = run["groups"][part]
        if (out[part].count("R"), len(out[part])) != (group["correct"], group["questions"]):
            raise ValueError(f"run {run['run']}: picks.json would not reproduce its {group['correct']} right answers "
                             f"of {group['questions']} {part} questions")
    return {part: "".join(out[part]) for part in PARTS}


def picks(site: Site) -> dict[str, Any]:
    return {
        "outcome": "One character per scored question of the part, in the order of the book: R right, W wrong, "
                   "N no valid answer (counted wrong).",
        "runs": [{"run": run["run"], **outcomes(site, run)} for run in site.ranked()],
    }


def build(site: Site) -> dict[str, str]:
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    PICKS.write_text(json.dumps(picks(site), separators=(",", ":")))
    return {}
