"""English reading (english/): the decision models on the Text tab's kept reading questions in English, from results.json's
english_reading only. Its face, under the view bar: a short lead, then two charts in the site's static style (Site hbars
coloured by the ranking scale, as aa-decision-index/ draws them): accuracy on the kept questions and the
non-hallucination rate with "I don't know" in English (english_reading.dont_know's English sides and english_only);
then one table ranked by English accuracy. The comparison with Turkish is turkish-vs-english/. No chat model was run in
English, so the charts and the table are shown for the "all" and "decision" groups (data-models, toggled by site.js) and
a note for "chat". It needs no JavaScript and changes no number of the other pages."""

from __future__ import annotations

from typing import Any

from sitebuild.english_reading import PATH as COMPARISON, chat_note, check_dont_know, english_only
from sitebuild.site import NOT_MEASURED, Site, esc, hbars, pct, rank_fill, rel, scale_legend
from sitebuild.vision import cell, joined

PATH = "english/"
TITLE = "English reading"
# The English reading track's models: every one a decision model (results.json english_reading.models).
MODELS = 17


def check(site: Site, data: dict[str, Any]) -> None:
    """Stops the build when english_reading no longer fits what the page says: 17 decision models, each with its Text
    tab run, its counts covering the kept questions and its accuracy its counts, in order of English right answers."""
    problems = []
    models, total = data["models"], data["questions"]
    if len(models) != MODELS:
        problems.append(f"{len(models)} models, not {MODELS}")
    for model in models:
        run = site.by_id.get(model["turkish_run"])
        if run is None or not site.decision(run):
            problems.append(f"{model['name']}: Text tab run {model['turkish_run']} is not a decision model's")
        if model["runs"][0] != model["run"]:
            problems.append(f"{model['name']}: the first English run is not the one shown")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["invalid"] != total or \
                    abs(counts["accuracy"] - counts["right"] / total) > 1e-9:
                problems.append(f"{model['name']}: its {side} counts do not give its accuracy on the {total} questions")
    rights = [model["english"]["right"] for model in models]
    if rights != sorted(rights, reverse=True):
        problems.append("the models are not ordered by English right answers")
    if problems:
        raise SystemExit("english_view:\n  " + "\n  ".join(problems))


def label(site: Site, model: dict[str, Any]) -> str:
    """A model's name as the Turkish vs English tab writes it: its Text tab run's row name."""
    return site.row_name(site.by_id[model["turkish_run"]])


def href(site: Site, model: dict[str, Any]) -> str:
    return rel(PATH, site.model_path(site.by_id[model["turkish_run"]]))


def build(site: Site) -> dict[str, str]:
    if "english_reading" not in site.results:
        return {}
    data = site.results["english_reading"]
    check(site, data)
    idk = data["dont_know"]
    check_dont_know(site, data, idk)
    digits = site.config["percent_digits"]
    stops = site.config["rank_scale"]["stops"]
    total, models = data["questions"], data["models"]
    option = idk["option"]
    # English "I don't know": the English side of each paired model, and the models with an English run only.
    english_idk = [(model["text_run"], model["english"]) for model in idk["models"]] + \
                  [(model["text_run"], model["english"]) for model in english_only(idk)]
    by_run = {model["turkish_run"]: model for model in models}
    held = {run: counts for run, counts in english_idk}
    if len(held) != len(english_idk) or any(run not in by_run for run in held):
        raise SystemExit("english_view: an English “I don't know” run is not one model of the accuracy comparison")

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows)}<p class="chart-legend">{legend}</p></figure>')

    accuracies = [model["english"]["accuracy"] for model in models]
    accuracy_rows = [{"label": label(site, model), "href": href(site, model),
                      "text": f"{pct(model['english']['accuracy'], digits)} · {model['english']['right']:,}",
                      "bars": [{"value": model["english"]["accuracy"],
                                "colour": rank_fill(stops, model["english"]["accuracy"], min(accuracies), max(accuracies))}],
                      "title": f"{label(site, model)}: {model['english']['right']:,} of {total:,} right in English "
                               f"(run {model['run']})"}
                     for model in models]
    rated = sorted(((by_run[run], counts) for run, counts in english_idk if counts["non_hallucination"] is not None),
                   key=lambda pair: (-pair[1]["non_hallucination"], label(site, pair[0]).casefold()))
    rates = [counts["non_hallucination"] for _, counts in rated]
    rate_rows = [{"label": label(site, model), "href": href(site, model),
                  "text": f"{pct(counts['non_hallucination'], digits)} · {pct(counts['attempt_rate'], digits)}",
                  "bars": [{"value": counts["non_hallucination"],
                            "colour": rank_fill(stops, counts["non_hallucination"], min(rates), max(rates))}],
                  "title": f"{label(site, model)}: {counts['dont_know']:,} “{option}” of "
                           f"{counts['dont_know'] + counts['wrong']:,} not right; {counts['right'] + counts['wrong']:,} of "
                           f"{total:,} answered (run {counts['run']})"}
                 for model, counts in rated]
    unrated = [label(site, model) for model in models if model["turkish_run"] not in held]
    charts = (
        card("chart-accuracy", f"Accuracy on the {total:,} English questions",
             f"Share of the {total:,} kept reading questions answered right in English, then the right answers of {total:,}: "
             "each model's first English run · higher is better", accuracy_rows,
             scale_legend(stops, pct(min(accuracies), digits), pct(max(accuracies), digits)))
        + card("chart-non-hallucination", "Non-hallucination rate with “I don't know” in English",
               f"“{esc(option)}” among the answers that were not right, with it offered as a sixth option in English, on the "
               f"{total:,} kept questions, then the answered share (right + wrong of {total:,}): each model's first run with "
               "it · higher is better, read with the answered share",
               rate_rows,
               scale_legend(stops, pct(min(rates), digits), pct(max(rates), digits))
               + " <span>A model that always chose the option would reach 100% with no right answers.</span>"
               + f" <span>Not run with “{esc(option)}” in English: {esc(joined(unrated))}.</span>"))

    heads = [("English accuracy", "first English run; higher is better"),
             ("Turkish accuracy", f"Text tab run, same {total:,}; for context"),
             ("English non-hallucination", f"with “{option}”; higher is better")]
    labels = [f"{head} ({note})" for head, note in heads]
    rows = []
    for model in models:
        counts = held.get(model["turkish_run"])
        values = [
            f'{pct(model["english"]["accuracy"], digits)}<span class="small">{model["english"]["right"]:,} of {total:,} right</span>',
            f'{pct(model["turkish"]["accuracy"], digits)}<span class="small">{model["turkish"]["right"]:,} of {total:,} right</span>',
            NOT_MEASURED if counts is None or counts["non_hallucination"] is None else
            f'{pct(counts["non_hallucination"], digits)}<span class="small">{counts["dont_know"]:,} “{esc(option)}” of '
            f'{counts["dont_know"] + counts["wrong"]:,} not right</span>'
            f'<span class="small">answered {pct(counts["attempt_rate"], digits)}</span>',
        ]
        name = (f'<td class="model"><a class="model-name" href="{href(site, model)}">{esc(label(site, model))}</a>'
                f'<span class="small">English run {model["run"]}</span></td>')
        rows.append(f"<tr>{name}" + "".join(cell(text, value) for text, value in zip(labels, values)) + "</tr>")
    if len(rows) != MODELS:
        raise SystemExit(f"english_view: {len(rows)} table rows, not {MODELS}")
    head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{esc(note)}</span></th>' for text, note in heads)
    table = (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    comparison = rel(PATH, COMPARISON)
    body = f"""    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The reading questions in English</h1>
      <div data-models="all decision">
      <p>The Text tab's {total:,} kept reading questions, translated into English, answered by {len(models)} decision models: each model's first English run. The comparison with the same models in Turkish is <a href="{comparison}">English and Turkish</a>.</p>
      <nav class="face-nav" aria-label="On this page"><a href="#chart-accuracy">Accuracy</a><a href="#chart-non-hallucination">Non-hallucination</a><a href="#table">The table</a></nav>
      </div>
      {chat_note(PATH)}
    </section>
    <div data-models="all decision">
    <section class="charts" aria-label="Charts">{charts}</section>
    <p class="note">Cost, latency and calibration are not measured in English.</p>
    <section class="card" id="table">
      <h2>Every model in English</h2>
      {table}
      <p class="note">Ranked by English accuracy, highest first: right answers of the {total:,} kept reading questions in each model's first English run (an invalid answer counts as not right). Turkish accuracy: the model's Text tab run on the same {total:,} questions, for context; the paired comparison is on <a href="{comparison}">English and Turkish</a>. English non-hallucination: “{esc(option)}” among the answers that were not right, in the model's first English run with it offered as a sixth option; Not measured: no such run. Each model's name opens its Text tab run.</p>
    </section>
    </div>"""
    return {PATH: site.page(PATH, TITLE, f"The Text tab's {total:,} kept reading questions in English: accuracy of {len(models)} "
                            "decision models and their non-hallucination rate with “I don't know”.", body)}
