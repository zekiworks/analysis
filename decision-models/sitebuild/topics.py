"""Topics: the accuracy-by-topic heatmap (topics/) and one page per topic (topics/<number>/) with every setup's
result on it. No page lists a topic's questions: their IDs, pages, numbers and keys stay private (publish_projection.py)."""

from __future__ import annotations

from typing import Any

import build_page as bp
from sitebuild.site import Site, esc, interval, pct, rel

# The heat map's colours: the ranking scale (page_config.json rank_scale: dark blue, turquoise, green, yellow) over
# accuracy from 0% to 100%, as tints that keep the cell text readable: mixed with the panel colour of each theme.
TINT = {"light": ((247, 246, 242), 0.32), "dark": ((26, 26, 24), 0.38)}


def heat_style(stops: list[str], fraction: float) -> str:
    colour = bp.rank_colour(stops, fraction)

    def tint(theme: str) -> str:
        base, weight = TINT[theme]
        return "rgb(" + ", ".join(str(round(weight * c + (1 - weight) * b)) for c, b in zip(colour, base)) + ")"

    return f"--heat-light: {tint('light')}; --heat-dark: {tint('dark')}"


def heatmap(site: Site) -> str:
    """The heat map: one row per setup (data-run), one column per topic, the colour scale's legend, and the setup choice
    that topics.js wires (?setups= in the URL); without JavaScript every setup shows and the choice stays hidden."""
    path = "topics/"
    units = site.units
    head = "".join(
        f'<th scope="col" class="unit num"><a href="{rel(path, f"topics/{unit["number"]}/")}">{esc(unit["english"])}</a>'
        f'<span class="small">{site.part(unit["number"]).capitalize()} · {unit["questions"]}</span></th>'
        for unit in units
    )
    stops = site.config["rank_scale"]["stops"]
    rows = []
    ranked = site.ranked()
    for run in ranked:
        cells = []
        for position, unit in enumerate(units):
            share = run["units"][position] / unit["questions"]
            cells.append(f'<td class="heat" style="{heat_style(stops, share)}" title="{esc(site.plain(run))}, {esc(unit["english"])}: '
                         f'{run["units"][position]} of {unit["questions"]}">{pct(share, 0)}</td>')
        rows.append(f'<tr data-run="{run["run"]}">{site.model_cell(path, run)}{"".join(cells)}</tr>')
    listing = "".join(
        f'<li><a href="{rel(path, f"topics/{unit["number"]}/")}">{esc(unit["english"])}</a> '
        f'<span class="muted">{site.part(unit["number"]).capitalize()} · {unit["questions"]} questions</span></li>'
        for unit in units
    )
    scale = "".join(f'<li class="heat" style="{heat_style(stops, step / 10)}">{step * 10}%</li>' for step in range(11))
    choices = "".join(f'<label><input type="checkbox" value="{run["run"]}" checked> {site.shown(run)}</label>' for run in ranked)
    body = f"""    <section class="card">
      <h1>Topics</h1>
      <ul class="topic-list">{listing}</ul>
      <p class="note">The {site.total:,} questions fall into {len(units)} topics of the book: {sum(site.part(u["number"]) == "reading" for u in units)} test reading and {sum(site.part(u["number"]) == "grammar" for u in units)} test grammar.</p>
    </section>
    <section class="card" id="heatmap">
      <h2>Accuracy by topic</h2>
      <figure class="heat-legend">
        <figcaption>Colour: accuracy on the topic, from dark blue at 0% to yellow at 100%. It does not show the model family.</figcaption>
        <ol class="heat-scale">{scale}</ol>
      </figure>
      <details class="setup-choice" data-setup-choice hidden>
        <summary>Choose setups <span class="muted" data-setup-count></span></summary>
        <div class="keys"><button type="button" class="key" data-setups="all">Show all</button><button type="button" class="key" data-setups="none">Clear</button></div>
        <fieldset class="setup-list"><legend class="visually-hidden">Setups shown in the heat map</legend>{choices}</fieldset>
      </details>
      <p class="note" data-setup-none hidden>No setup chosen. Choose at least one above, or press Show all.</p>
      <div class="table-wrap heatmap-wrap" tabindex="0" role="region" aria-label="Accuracy by topic, scrollable"><table class="heatmap-table"><thead><tr><th scope="col">Setup</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
      <p class="note">Each cell: the share of the topic's questions the setup got right. Setups by accuracy on all questions.</p>
    </section>"""
    return site.page(path, "Topics", f"Accuracy by topic for every setup, and a page for each of the {len(units)} topics.", body,
                     scripts=("topics.js",))


def topic_page(site: Site, unit: dict[str, Any]) -> str:
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
    questions = site.answers["questions"]["unit"]
    scored = sum(questions[index] == number for index in site.scored)
    if scored != unit["questions"]:
        raise ValueError(f"topic {number}: {scored} scored questions in answers.json, {unit['questions']} in results.json")
    part = site.part(number).capitalize()
    body = f"""    <section class="card">
      <p class="eyebrow">{part} · topic {number}</p>
      <h1>{esc(unit["english"])}</h1>
    </section>
    <section class="card">
      <h2>Every setup's result · {unit["questions"]} scored questions</h2>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Setup</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Right</th></tr></thead><tbody>{"".join(results)}</tbody></table></div>
      <p class="note">Accuracy on this topic's questions, with its 95% interval. Few questions make wide intervals. <a href="{rel(path, "topics/")}#heatmap">Accuracy by topic</a> compares this topic with the others.</p>
    </section>"""
    return site.page(path, unit["english"], f"{part} topic: {unit['english']}. Every setup's result on its {unit['questions']} questions.", body)


def build(site: Site) -> dict[str, str]:
    pages = {"topics/": heatmap(site)}
    for unit in site.units:
        pages[f"topics/{unit['number']}/"] = topic_page(site, unit)
    return pages
