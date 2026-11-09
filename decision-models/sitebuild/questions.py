"""Every question: the list of the scored questions, one page per question (question/?id=…, drawn by question.js)
and the compact per-question data it, the Compare page and the topic pages read (data/picks.json). The question page
also shows, for each reading question kept on the Turkish vs English tab, every compared model's answer in Turkish and
in English (picks.json's `english`), and for a flagged reading question the flag's reasons.

The question text is never published, Turkish or English: the publisher owns it. A question is identified by its ID,
its part and topic, and its page and printed number in the book."""

from __future__ import annotations

import json
import math
from typing import Any

from sitebuild.site import ROOT, Site, esc, more_link, rel

PICKS = ROOT / "data" / "picks.json"


def score_text(score: float | None) -> float | None:
    """A pick's probability or score for picks.json: floored to four decimals, so a score below the 99% cutoff never
    reads as 99.00%."""
    return None if score is None else math.floor(score * 10000) / 10000


def pick_letters(answers: dict[str, Any], indices: list[int], keys: list[str], label: str, ids: list[int]) -> str:
    """A run's picks on the given question indices, one letter each, "-" where it gave no valid answer. A pick that
    matches the key is a right answer: checked here against answers.json's grading."""
    letters = []
    for index in indices:
        choice = answers["choice"][index]
        letter = choice if isinstance(choice, str) and len(choice) == 1 else "-"
        if (letter == keys[index]) != bool(answers["correct"][index]):
            raise ValueError(f"{label}: pick {choice!r} and its grade disagree on question {ids[index]}")
        letters.append(letter)
    return "".join(letters)


def english(site: Site) -> dict[str, Any] | None:
    """The Turkish vs English tab's answers for the question page: the kept questions' IDs, the flagged questions'
    reasons, and for each compared model (results.json english_reading.models, in its order) its first English run's
    picks and probabilities on the kept questions. Its Turkish side is its Text tab run (turkish_run), already among
    picks.json's runs. Each side's right, wrong and invalid counts are checked against results.json."""
    if "english_reading" not in site.results:
        return None
    # Imported here: sitebuild.english_reading imports sitebuild.data, which imports this module.
    from sitebuild.english_reading import RECORD, reason_name

    data = site.results["english_reading"]
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    questions = site.answers["questions"]
    ids, keys = questions["id"], questions["key"]
    position = {question_id: index for index, question_id in enumerate(ids)}
    kept = [question["question_id"] for question in record["questions"] if question["kept"]]
    indices = [position[question_id] for question_id in kept]
    english_runs = {item["run"]: item for item in site.answers["english_runs"]}
    runs = []
    for model in data["models"]:
        answers = english_runs[model["run"]]
        if [index for index, grade in enumerate(answers["correct"]) if grade is not None] != sorted(indices):
            raise ValueError(f"English run {model['run']}: its questions are not the kept questions")
        letters = pick_letters(answers, indices, keys, f"English run {model['run']}", ids)
        turkish = pick_letters(site.answer_runs[model["turkish_run"]], indices, keys, f"run {model['turkish_run']}", ids)
        for side, side_letters in (("english", letters), ("turkish", turkish)):
            right = sum(letter == keys[index] for letter, index in zip(side_letters, indices))
            invalid = side_letters.count("-")
            counts = model[side]
            if (right, len(indices) - right - invalid, invalid) != (counts["right"], counts["wrong"], counts["invalid"]):
                raise ValueError(f"{model['name']}: picks.json would not reproduce its {side} counts")
        runs.append({
            "run": model["run"],
            "turkish_run": model["turkish_run"],
            "name": site.row_name(site.by_id[model["turkish_run"]]),
            "picks": letters,
            "scores": [score_text(answers["score"][index]) for index in indices],
        })
    return {
        "questions": kept,
        "flagged": [[question["question_id"], [reason_name(reason) for reason in question["reasons"]]]
                    for question in record["questions"] if not question["kept"]],
        "runs": runs,
    }


def picks(site: Site) -> dict[str, Any]:
    """Every leaderboard setup's pick and its probability or score on each scored question, in question order, with
    the question's ID, topic, page, printed number and key, then the Turkish vs English tab's answers (english())."""
    questions = site.answers["questions"]
    order = site.scored
    runs: list[dict[str, Any]] = []
    shown = site.names(site.runs)
    for run in site.ranked():
        answers = site.answer_runs[run["run"]]
        letters = pick_letters(answers, order, questions["key"], f"run {run['run']}", questions["id"])
        if sum(letter == questions["key"][index] for letter, index in zip(letters, order)) != run["correct"]:
            raise ValueError(f"run {run['run']}: picks.json would not reproduce its {run['correct']} right answers")
        runs.append({
            "run": run["run"],
            "name": shown[run["run"]],
            "detail": site.detail(run),
            "decision": site.decision(run),
            "score": run["confidence"]["label"],
            "picks": letters,
            "scores": [score_text(answers["score"][index]) for index in order],
        })
    out = {
        "units": [{"number": unit["number"], "name": unit["english"], "part": site.part(unit["number"])} for unit in site.units],
        "questions": [
            [questions["id"][index], questions["unit"][index], questions["page"][index], questions["number"][index], questions["key"][index]]
            for index in order
        ],
        "runs": runs,
    }
    comparison = english(site)
    if comparison:
        out["english"] = comparison
    return out


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


# The Every question page's difficulty bands, by the share of all setups that got a question right: (key in the URL
# and the rows' data-difficulty, label). questions.js filters on them.
DIFFICULTY = (("hard", "Hard: under a third right"), ("medium", "Medium: a third to two thirds right"),
              ("easy", "Easy: over two thirds right"))
# Rows the Every question page shows at a time (questions.js reads data-rows).
ROWS_SHOWN = 100


def difficulty(right: int, setups: int) -> str:
    return "hard" if 3 * right < setups else "easy" if 3 * right > 2 * setups else "medium"


def every_question(site: Site, data: dict[str, Any]) -> str:
    """The list of every scored question, all rows in the page; questions.js adds the filters (question ID, book page,
    topic, difficulty) and shows the rows ROWS_SHOWN at a time, keeping both in the URL. Without JavaScript every row
    shows."""
    path = "questions/"
    setups = len(site.runs)
    decision = sum(map(site.decision, site.runs))
    counts = right_counts(site, data)
    rows = []
    bands = {key: 0 for key, _ in DIFFICULTY}
    for question, (right, decision_right) in zip(data["questions"], counts):
        question_id, unit, page, number, key = question
        part = site.part(unit)
        band = difficulty(right, setups)
        bands[band] += 1
        rows.append(
            f'<tr data-id="{question_id}" data-page="{page}" data-topic="{unit}" data-difficulty="{band}">'
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
    topics = "".join(
        f'<optgroup label="{label}">' + "".join(
            f'<option value="{unit["number"]}">{esc(unit["english"])} ({unit["questions"]})</option>'
            for unit in site.units if site.part(unit["number"]) == part) + "</optgroup>"
        for part, label in (("reading", "Reading"), ("grammar", "Grammar")))
    levels = "".join(f'<option value="{key}">{label} ({bands[key]:,})</option>' for key, label in DIFFICULTY)
    pager = ('<nav class="q-pager" data-q-pager aria-label="Rows of the list" hidden>'
             f'<button type="button" class="key" data-step="-1">Previous {ROWS_SHOWN}</button>'
             '<span class="q-where" data-q-where></span>'
             f'<button type="button" class="key" data-step="1">Next {ROWS_SHOWN}</button></nav>')
    site.note(path, "Every question", f"<p>The {len(data['questions']):,} scored questions, in the order of the book. Their "
              "text stays unpublished: the publisher owns it; the page and printed number find each one in the book. Each "
              "ID opens the question's page, with every setup's pick.</p>")
    body = f"""    <section class="card" id="questions" data-rows="{ROWS_SHOWN}">
      <h1>Every question</h1>
      <p>The {len(data["questions"]):,} scored questions, in the order of the book; each ID opens its page.</p>
      {more_link(path)}
      <nav class="face-nav" aria-label="More on the questions"><a href="{rel(path, "disagreements/")}">Where models disagree</a><a href="{rel(path, "topics/")}">Topics</a><a href="{rel(path, "compare/")}">Compare</a></nav>
      <form class="q-filters" data-q-filters role="search" aria-label="Filter the questions" hidden>
        <label class="control">Question ID <input type="search" inputmode="numeric" autocomplete="off" size="6" data-filter="id"></label>
        <label class="control">Book page <input type="search" inputmode="numeric" autocomplete="off" size="5" data-filter="book-page"></label>
        <label class="control">Topic <select data-filter="topic"><option value="">All topics</option>{topics}</select></label>
        <label class="control">Difficulty <select data-filter="difficulty"><option value="">All</option>{levels}</select></label>
        <button type="button" class="key" data-q-reset>Reset</button>
      </form>
      <p class="note" data-q-note hidden>Difficulty: the share of the {setups} setups that got the question right. The filters and the rows shown stay in the address, so a view can be shared.</p>
      <p class="q-count" data-q-count aria-live="polite"></p>
      {pager}
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col">Part</th><th scope="col">Topic</th><th scope="col" class="num">Page</th><th scope="col" class="num">Number</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Setups right</th><th scope="col" class="num">Decision models right</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table></div>
      {pager.replace("data-q-pager", "data-q-pager data-q-bottom")}
    </section>"""
    return site.page(path, "Every question", f"The {len(data['questions']):,} scored questions, each with every setup's pick.", body,
                     scripts=("questions.js",))


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
