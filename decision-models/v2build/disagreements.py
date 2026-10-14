"""Where models disagree with the answer key. First the questions where at least page_config.json's
key_disagreement["agree"] of its runs, the most accurate chat models at one question per request, chose the same answer
and it is not the key, each with the key's status from answers.json and a link to the "Answer key correction" issue
template; then the questions most setups got wrong, with the pick most of them chose instead."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote

import build_page as bp
from v2build.questions import picks_data, question_link
from v2build.site import ISSUE_URL, Site, esc, rel

PATH = "disagreements/"
CORRECTION_URL = f"{ISSUE_URL}answer-key-correction.md"
# The issue template's own title ends where the question's ID goes; each row's link fills it in.
CORRECTION_TITLE = "Answer key: question "


def strongest(site: Site) -> list[dict[str, Any]]:
    """page_config.json's key_disagreement runs, in its order. The build stops unless they are the most accurate chat
    setups at one question per request, as the page says, and unless agreeing takes more than half of them, so that at
    most one answer qualifies."""
    spec = site.config["key_disagreement"]
    runs = [bp.pick(site.runs, site.config["named_runs"][key], f"named run {key}") for key in spec["runs"]]
    found = [run for run in runs if run is not None]
    single = sorted((run for run in site.runs if not site.decision(run) and run["questions_per_request"] == 1),
                    key=lambda run: -run["correct"])
    if sorted(run["run"] for run in found) != sorted(run["run"] for run in single[:len(runs)]):
        raise ValueError("key_disagreement's runs are no longer the most accurate chat setups at one question per request")
    if not len(found) < 2 * spec["agree"] <= 2 * len(found):
        raise ValueError("key_disagreement's agree must be more than half of its runs")
    return found


def agreed(site: Site, data: dict[str, Any], runs: list[dict[str, Any]]) -> list[tuple[int, int, int, str, str, str]]:
    """The scored questions where at least key_disagreement's agree of the runs chose one answer other than the key:
    (how many chose it, question ID, topic, key, their answer, the key's status in answers.json or "none"), the widest
    agreement first."""
    picks = {item["run"]: item["picks"] for item in data["runs"]}
    chosen = [picks[run["run"]] for run in runs]
    status = site.answers["questions"]["status"]
    rows = []
    for position, (question_id, unit, _page, _number, key) in enumerate(data["questions"]):
        counts = Counter(letters[position] for letters in chosen if letters[position] != "-")
        if not counts:
            continue
        answer, agreeing = counts.most_common(1)[0]
        if agreeing >= site.config["key_disagreement"]["agree"] and answer != key:
            rows.append((agreeing, question_id, unit, key, answer, status[site.scored[position]] or "none"))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return rows


def correction_link(question_id: int) -> str:
    url = f"{CORRECTION_URL}&title={quote(CORRECTION_TITLE + str(question_id))}"
    return f'<a href="{esc(url)}" aria-label="Report the key of question {question_id}">Report</a>'


def topic_cells(site: Site, unit: int) -> str:
    return (f'<td data-label="Part">{site.part(unit).capitalize()}</td>'
            f'<td data-label="Topic"><a href="{rel(PATH, f"topics/{unit}/")}">{esc(site.unit(unit)["english"])}</a></td>')


def build(site: Site) -> dict[str, str]:
    data = picks_data(site)
    runs = data["runs"]
    five = strongest(site)
    strict = agreed(site, data, five)
    links = [f'<a href="{rel(PATH, site.model_path(run))}">{esc(run["name"])}</a>' for run in five]
    names = ", ".join(links[:-1]) + " and " + links[-1]
    strict_rows = "".join(
        "<tr>"
        f'<td class="model">{question_link(PATH, question_id)}</td>{topic_cells(site, unit)}'
        f'<td class="num" data-label="Answer key">{esc(key)}</td>'
        f'<td class="num" data-label="Models\' answer">{esc(answer)}</td>'
        f'<td class="num" data-label="Agree">{agreeing} of {len(five)}</td>'
        f'<td data-label="Key status">{esc(status)}</td>'
        f'<td data-label="Key correction">{correction_link(question_id)}</td>'
        "</tr>"
        for agreeing, question_id, unit, key, answer, status in strict
    )
    rows = []
    chat = [item for item in runs if not item["decision"]]
    for position, (question_id, unit, _page, _number, key) in enumerate(data["questions"]):
        picks = [item["picks"][position] for item in runs]
        wrong = sum(pick != key for pick in picks)
        if 2 * wrong <= len(runs):
            continue
        others = Counter(pick for pick in picks if pick not in (key, "-"))
        common, common_count = others.most_common(1)[0] if others else ("—", 0)
        chat_right = sum(item["picks"][position] == key for item in chat)
        rows.append((wrong, common_count, question_id, unit, key, common, chat_right))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    wrong_rows = "".join(
        "<tr>"
        f'<td class="model">{question_link(PATH, question_id)}</td>{topic_cells(site, unit)}'
        f'<td class="num" data-label="Answer key">{esc(key)}</td>'
        f'<td class="num" data-label="Setups wrong">{wrong} of {len(runs)}</td>'
        f'<td class="num" data-label="Most common other pick">{esc(common)}{f" ({common_count})" if common_count else ""}</td>'
        f'<td class="num" data-label="Chat models right">{chat_right} of {len(chat)}</td>'
        "</tr>"
        for wrong, common_count, question_id, unit, key, common, chat_right in rows
    )
    body = f"""    <section class="card">
      <h1>Where models disagree with the answer key</h1>
      <p>On these {len(strict)} questions, at least {site.config["key_disagreement"]["agree"]} of the {len(five)} most accurate chat models asked one question per request ({names}) chose the same answer, and it is not the key. All {len(five)} agreed on {sum(row[0] == len(five) for row in strict)}. Key status is the label from the key review: verified, suspect (still marked uncertain) or none.</p>
      <p>Think a key is wrong? <a href="{CORRECTION_URL}">Report an answer key correction</a>. The <a href="{rel(PATH, "data/")}#key-changelog">key changelog</a> lists every change and how a fix works.</p>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col">Part</th><th scope="col">Topic</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Models' answer</th><th scope="col" class="num">Agree</th><th scope="col">Key status</th><th scope="col">Key correction</th></tr></thead>
      <tbody>{strict_rows}</tbody></table></div>
    </section>
    <section class="card" id="most-wrong">
      <h2>Questions most setups got wrong</h2>
      <p>These {len(rows):,} questions were answered wrongly by more than half of the {len(runs)} setups. Most are simply hard. Where many setups agree on another answer, the key may be wrong.</p>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col">Part</th><th scope="col">Topic</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Setups wrong</th><th scope="col" class="num">Most common other pick</th><th scope="col" class="num">Chat models right</th></tr></thead>
      <tbody>{wrong_rows}</tbody></table></div>
    </section>"""
    return {PATH: site.page(PATH, "Where models disagree with the answer key",
                            "Questions where the most accurate chat models agree on an answer that is not the key, and the questions most setups got wrong.",
                            body)}
