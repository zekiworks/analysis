"""Every question: the list of the scored questions, one page per question (question/?id=…, drawn by question.js)
and the compact per-question data it, the Compare page and the topic pages read (data/picks.json).

The question text is never published: the publisher owns it. A question is identified by its ID, its part and topic,
and its page and printed number in the book."""

from __future__ import annotations

import json
import math
from typing import Any

from sitebuild.site import ROOT, Site, esc, rel

PICKS = ROOT / "data" / "picks.json"


def score_text(score: float | None) -> float | None:
    """A pick's probability or score for picks.json: floored to four decimals, so a score below the 99% cutoff never
    reads as 99.00%."""
    return None if score is None else math.floor(score * 10000) / 10000


def picks(site: Site) -> dict[str, Any]:
    """Every leaderboard setup's pick and its probability or score on each scored question, in question order, with
    the question's ID, topic, page, printed number and key. A pick that matches the key is a right answer: checked
    here against answers.json's grading."""
    questions = site.answers["questions"]
    order = site.scored
    runs: list[dict[str, Any]] = []
    for run in site.ranked():
        answers = site.answer_runs[run["run"]]
        letters = []
        for index in order:
            choice = answers["choice"][index]
            letter = choice if isinstance(choice, str) and len(choice) == 1 else "-"
            if (letter == questions["key"][index]) != bool(answers["correct"][index]):
                raise ValueError(f"run {run['run']}: pick {choice!r} and its grade disagree on question {questions['id'][index]}")
            letters.append(letter)
        if sum(letter == questions["key"][index] for letter, index in zip(letters, order)) != run["correct"]:
            raise ValueError(f"run {run['run']}: picks.json would not reproduce its {run['correct']} right answers")
        runs.append({
            "run": run["run"],
            "name": run["name"],
            "detail": site.detail(run),
            "decision": site.decision(run),
            "score": run["confidence"]["label"],
            "picks": "".join(letters),
            "scores": [score_text(answers["score"][index]) for index in order],
        })
    return {
        "units": [{"number": unit["number"], "name": unit["english"], "part": site.part(unit["number"])} for unit in site.units],
        "questions": [
            [questions["id"][index], questions["unit"][index], questions["page"][index], questions["number"][index], questions["key"][index]]
            for index in order
        ],
        "runs": runs,
    }


def picks_data(site: Site) -> dict[str, Any]:
    """picks(), computed once per build: several pages read it."""
    if not hasattr(site, "_picks"):
        site._picks = picks(site)  # type: ignore[attr-defined]
    return site._picks  # type: ignore[attr-defined]


def right_counts(site: Site, data: dict[str, Any]) -> list[tuple[int, int]]:
    """For each scored question: how many setups, and how many decision models, picked the key."""
    out = []
    for position, question in enumerate(data["questions"]):
        right = [item for item in data["runs"] if item["picks"][position] == question[4]]
        out.append((len(right), sum(item["decision"] for item in right)))
    return out


def question_link(origin: str, question_id: int) -> str:
    return f'<a href="{rel(origin, "question/")}?id={question_id}">{question_id}</a>'


def every_question(site: Site, data: dict[str, Any]) -> str:
    path = "questions/"
    setups = len(site.runs)
    decision = sum(map(site.decision, site.runs))
    counts = right_counts(site, data)
    rows = []
    for question, (right, decision_right) in zip(data["questions"], counts):
        question_id, unit, page, number, key = question
        part = site.part(unit)
        rows.append(
            "<tr>"
            f'<td class="model">{question_link(path, question_id)}</td>'
            f'<td data-label="Part">{part.capitalize()}</td>'
            f'<td data-label="Topic"><a href="{rel(path, f"topics/{unit}/")}">{esc(site.unit(unit)["english"])}</a></td>'
            f'<td class="num" data-label="Page">{page}</td>'
            f'<td class="num" data-label="Number">{esc(str(number))}</td>'
            f'<td class="num" data-label="Answer key">{esc(key)}</td>'
            f'<td class="num" data-label="Setups right">{right} of {setups}</td>'
            f'<td class="num" data-label="Decision models right">{decision_right} of {decision}</td>'
            "</tr>"
        )
    body = f"""    <section class="card">
      <h1>Every question</h1>
      <p>The {len(data["questions"]):,} scored questions, in the order of the book. Their text stays unpublished: the publisher owns it; the page and printed number find each one in the book. Each ID opens the question's page, with every setup's pick.</p>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col">Part</th><th scope="col">Topic</th><th scope="col" class="num">Page</th><th scope="col" class="num">Number</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Setups right</th><th scope="col" class="num">Decision models right</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table></div>
    </section>"""
    return site.page(path, "Every question", f"The {len(data['questions']):,} scored questions, each with every setup's pick.", body)


def question_view(site: Site) -> str:
    """One page per question, by its ID in the URL; question.js fills it from picks.json. Readers without JavaScript
    get a line pointing to answers.json and the Every question page instead."""
    path = "question/"
    body = f"""    <section class="card" id="question">
      <h1>Question</h1>
      <p class="note" data-question-status hidden>Loading the question…</p>
      <noscript><p class="note">This page needs JavaScript. Without it, <a href="{rel(path, "answers.json")}" download>answers.json</a> holds every setup's answer to every question, and <a href="{rel(path, "questions/")}">Every question</a> lists each question's key and how many setups got it right.</p></noscript>
      <div data-question hidden></div>
    </section>"""
    return site.page(path, "Question", "One question: its part, topic, page, printed number, answer key and every setup's pick.", body,
                     scripts=("question.js",))


def build(site: Site) -> dict[str, str]:
    data = picks_data(site)
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    PICKS.write_text(json.dumps(data, separators=(",", ":")))
    return {"questions/": every_question(site, data), "question/": question_view(site)}
