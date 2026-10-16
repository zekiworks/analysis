"""Topics: the accuracy-by-topic heatmap (topics/) and one page per topic (topics/<number>/) with every setup's
result on it and its questions."""

from __future__ import annotations

from typing import Any

from v3build.questions import picks_data, question_link
from v3build.site import Site, esc, interval, pct, rel

# Accuracy 0–100% → red, amber at 50%, green: the earlier page's heat-map scale (v1/app.js heatStyle), in both themes.
HEAT = {
    "light": ((254, 226, 226), (254, 243, 199), (187, 247, 208)),
    "dark": ((76, 29, 36), (74, 59, 16), (19, 78, 46)),
}


def heat_style(fraction: float) -> str:
    share = min(1.0, max(0.0, fraction))

    def mix(stops: tuple[tuple[int, int, int], ...]) -> str:
        low, high, t = (stops[0], stops[1], share / 0.5) if share <= 0.5 else (stops[1], stops[2], (share - 0.5) / 0.5)
        return "rgb(" + ", ".join(str(round(a + (b - a) * t)) for a, b in zip(low, high)) + ")"

    return f"--heat-light: {mix(HEAT['light'])}; --heat-dark: {mix(HEAT['dark'])}"


def heatmap(site: Site) -> str:
    path = "topics/"
    units = site.units
    head = "".join(
        f'<th scope="col" class="unit num"><a href="{rel(path, f"topics/{unit["number"]}/")}">{esc(unit["english"])}</a>'
        f'<span class="small">{site.part(unit["number"]).capitalize()} · {unit["questions"]}</span></th>'
        for unit in units
    )
    rows = []
    for run in site.ranked():
        cells = []
        for position, unit in enumerate(units):
            share = run["units"][position] / unit["questions"]
            cells.append(f'<td class="heat" style="{heat_style(share)}" title="{esc(run["name"])}, {esc(unit["english"])}: '
                         f'{run["units"][position]} of {unit["questions"]}">{pct(share, 0)}</td>')
        rows.append(f"<tr>{site.model_cell(path, run)}{''.join(cells)}</tr>")
    listing = "".join(
        f'<li><a href="{rel(path, f"topics/{unit["number"]}/")}">{esc(unit["english"])}</a> '
        f'<span class="muted">{site.part(unit["number"]).capitalize()} · {unit["questions"]} questions</span></li>'
        for unit in units
    )
    body = f"""    <section class="card">
      <h1>Topics</h1>
      <p>The {site.total:,} questions fall into {len(units)} topics of the book: {sum(site.part(u["number"]) == "reading" for u in units)} test reading and {sum(site.part(u["number"]) == "grammar" for u in units)} test grammar. Each topic's page lists its questions and every setup's result on it.</p>
      <ul class="topic-list">{listing}</ul>
    </section>
    <section class="card" id="heatmap">
      <h2>Accuracy by topic</h2>
      <p class="note">Each cell: the share of the topic's questions the setup got right. Setups by accuracy on all questions; the table scrolls sideways inside its box.</p>
      <div class="table-wrap heatmap-wrap"><table class="heatmap-table"><thead><tr><th scope="col">Setup</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
    </section>"""
    return site.page(path, "Topics", f"Accuracy by topic for every setup, and a page for each of the {len(units)} topics.", body)


def topic_page(site: Site, unit: dict[str, Any], data: dict[str, Any]) -> str:
    number = unit["number"]
    path = f"topics/{number}/"
    position = site.units.index(unit)
    results = []
    for run in sorted(site.runs, key=lambda run: -run["units"][position]):
        correct = run["units"][position]
        results.append(
            f"<tr>{site.model_cell(path, run, kind=True)}"
            f'<td class="num" data-label="Accuracy">{pct(correct / unit["questions"])}<span class="small">{interval(correct, unit["questions"])}</span></td>'
            f'<td class="num" data-label="Right">{correct} of {unit["questions"]}</td></tr>'
        )
    runs = data["runs"]
    decision_total = sum(item["decision"] for item in runs)
    questions = []
    for index, (question_id, question_unit, page, printed, key) in enumerate(data["questions"]):
        if question_unit != number:
            continue
        right = [item for item in runs if item["picks"][index] == key]
        questions.append(
            "<tr>"
            f'<td class="model">{question_link(path, question_id)}</td>'
            f'<td class="num" data-label="Page">{page}</td>'
            f'<td class="num" data-label="Number">{esc(str(printed))}</td>'
            f'<td class="num" data-label="Answer key">{esc(key)}</td>'
            f'<td class="num" data-label="Setups right">{len(right)} of {len(runs)}</td>'
            f'<td class="num" data-label="Decision models right">{sum(item["decision"] for item in right)} of {decision_total}</td>'
            "</tr>"
        )
    if len(questions) != unit["questions"]:
        raise ValueError(f"topic {number}: {len(questions)} scored questions in answers.json, {unit['questions']} in results.json")
    part = site.part(number).capitalize()
    body = f"""    <section class="card">
      <p class="eyebrow">{part} · topic {number}</p>
      <h1>{esc(unit["english"])}</h1>
      <p>{unit["questions"]} scored questions. <a href="{rel(path, "topics/")}#heatmap">Accuracy by topic</a> compares this topic with the others.</p>
    </section>
    <section class="card">
      <h2>Every setup's result</h2>
      <p class="note">Accuracy on this topic's questions, with its 95% interval. Few questions make wide intervals.</p>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Setup</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Right</th></tr></thead><tbody>{"".join(results)}</tbody></table></div>
    </section>
    <section class="card">
      <h2>Its questions</h2>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col" class="num">Page</th><th scope="col" class="num">Number</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Setups right</th><th scope="col" class="num">Decision models right</th></tr></thead><tbody>{"".join(questions)}</tbody></table></div>
    </section>"""
    return site.page(path, unit["english"], f"{part} topic: {unit['english']}. Every setup's result and its {unit['questions']} questions.", body)


def build(site: Site) -> dict[str, str]:
    data = picks_data(site)
    pages = {"topics/": heatmap(site)}
    for unit in site.units:
        pages[f"topics/{unit['number']}/"] = topic_page(site, unit, data)
    return pages
