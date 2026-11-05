"""English reading (english/): the Text tab's setups on its kept reading questions in English, from results.json's
english_reading only. Its face, under the view bar: a short lead, the accuracy chart in the site's static style (Site
hbars, each bar in its model family's colour, as the home page's charts) and one table ranked by English accuracy, each
once per group of the view bar (data-models, toggled by site.js; the all group is the one shown without JavaScript),
its counts and sentences computed for that group. The decision models' non-hallucination rate with "I don't know" in
English (english_reading.dont_know's English sides and english_only) is charted once, for the all and decision groups,
with one note for the chat group: no chat model was asked with the option. The comparison with Turkish is
turkish-vs-english/. It needs no JavaScript and changes no number of the other pages."""

from __future__ import annotations

from typing import Any

from sitebuild.english_reading import (DECISION_ONLY, GROUPS, PATH as COMPARISON, anchor, chat_note, check_dont_know,
                                       english_only, group_models, label, noun, shown)
from sitebuild.site import NOT_MEASURED, Site, esc, family_legend, hbars, pct, rel
from sitebuild.vision import cell, joined

PATH = "english/"
TITLE = "English reading"


def check(site: Site, data: dict[str, Any]) -> None:
    """Stops the build when english_reading no longer fits what the page says: each setup with its Text tab run, the
    first English run the one shown, its counts covering the kept questions and its accuracy its counts, in order of
    English right answers; the decision and chat groups adding up to every setup."""
    problems = []
    models, total = data["models"], data["questions"]
    for model in models:
        if model["turkish_run"] not in site.by_id:
            problems.append(f"{model['name']}: Text tab run {model['turkish_run']} is not on the Text tab")
        if model["runs"][0] != model["run"]:
            problems.append(f"{model['name']}: the first English run is not the one shown")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["invalid"] != total or \
                    abs(counts["accuracy"] - counts["right"] / total) > 1e-9:
                problems.append(f"{model['name']}: its {side} counts do not give its accuracy on the {total} questions")
    if problems:
        raise SystemExit("english_view:\n  " + "\n  ".join(problems))
    rights = [model["english"]["right"] for model in models]
    if rights != sorted(rights, reverse=True):
        problems.append("the setups are not ordered by English right answers")
    if len(group_models(site, data, "decision")) + len(group_models(site, data, "chat")) != len(models):
        problems.append("the decision and chat groups do not add up to every setup")
    if problems:
        raise SystemExit("english_view:\n  " + "\n  ".join(problems))


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
    family = lambda model: site.families[model["turkish_run"]]  # noqa: E731
    total, models = data["questions"], data["models"]
    option = idk["option"]
    counts = {group: len(group_models(site, data, group)) for group in GROUPS}
    # English "I don't know": the English side of each paired model, and the models with an English run only.
    english_idk = [(model["text_run"], model["english"]) for model in idk["models"]] + \
                  [(model["text_run"], model["english"]) for model in english_only(idk)]
    by_run = {model["turkish_run"]: model for model in models}
    held = {run: counts for run, counts in english_idk}
    if len(held) != len(english_idk) or any(run not in by_run for run in held):
        raise SystemExit("english_view: an English “I don't know” run is not one setup of the accuracy comparison")
    if any(not site.decision(site.by_id[run]) for run in held):
        raise SystemExit("english_view: a chat model has an English “I don't know” run, which the page charts for "
                         "decision models only")

    def card(base: str, attributes: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str) -> str:
        return (f'<figure class="panel chart-card" id="{base}" {attributes}><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows)}<p class="chart-legend">{legend}</p></figure>')

    def accuracy_card(group: str) -> str:
        members = group_models(site, data, group)
        rows = [{"label": label(site, model), "href": href(site, model),
                 "text": f"{pct(model['english']['accuracy'], digits)} · {model['english']['right']:,}",
                 "bars": [{"value": model["english"]["accuracy"], "colour": family(model)["colour"]}],
                 "title": f"{label(site, model)}: {model['english']['right']:,} of {total:,} right in English "
                          f"(run {model['run']})"}
                for model in members]
        return card(anchor("chart-accuracy", group), shown(group), f"Accuracy on the {total:,} English questions",
                    f"Share of the {total:,} kept reading questions answered right in English, then the right answers of "
                    f"{total:,}: each of the {len(members)} {noun(group, len(members))}' first English run · higher is better",
                    rows, family_legend([family(model) for model in members]))

    rated = sorted(((by_run[run], counts) for run, counts in english_idk if counts["non_hallucination"] is not None),
                   key=lambda pair: (-pair[1]["non_hallucination"], label(site, pair[0]).casefold()))
    rate_rows = [{"label": label(site, model), "href": href(site, model),
                  "text": f"{pct(counts['non_hallucination'], digits)} · {pct(counts['attempt_rate'], digits)}",
                  "bars": [{"value": counts["non_hallucination"], "colour": family(model)["colour"]}],
                  "title": f"{label(site, model)}: {counts['dont_know']:,} “{option}” of "
                           f"{counts['dont_know'] + counts['wrong']:,} not right; {counts['right'] + counts['wrong']:,} of "
                           f"{total:,} answered (run {counts['run']})"}
                 for model, counts in rated]
    unrated = [label(site, model) for model in group_models(site, data, "decision") if model["turkish_run"] not in held]
    rates = card(
        "chart-non-hallucination", DECISION_ONLY, "Non-hallucination rate with “I don't know” in English",
        f"“{esc(option)}” among the answers that were not right, with it offered as a sixth option in English, on the "
        f"{total:,} kept questions, then the answered share (right + wrong of {total:,}): each decision model's first run "
        "with it · higher is better, read with the answered share",
        rate_rows,
        family_legend([family(model) for model, _ in rated])
        + " <span>A model that always chose the option would reach 100% with no right answers.</span>"
        + (f" <span>Decision models not run with “{esc(option)}” in English: {esc(joined(unrated))}.</span>" if unrated else ""))
    note = chat_note(f"Chat models were asked without an “{esc(option)}” option, so the non-hallucination chart and column "
                     "are for decision models only.")
    charts = "".join(accuracy_card(group) for group in GROUPS if counts[group]) + rates + note

    def table(group: str) -> str:
        """A group's copy of the table, ranked by English accuracy; the non-hallucination column but for the chat group."""
        with_rate = group != "chat"
        heads = [("English accuracy", "first English run; higher is better"),
                 ("Turkish accuracy", f"Text tab run, same {total:,}; for context")]
        if with_rate:
            heads.append(("English non-hallucination", f"with “{option}”; higher is better"))
        labels = [f"{head} ({note})" for head, note in heads]
        rows = []
        for model in group_models(site, data, group):
            values = [
                f'{pct(model["english"]["accuracy"], digits)}<span class="small">{model["english"]["right"]:,} of {total:,} right</span>',
                f'{pct(model["turkish"]["accuracy"], digits)}<span class="small">{model["turkish"]["right"]:,} of {total:,} right</span>',
            ]
            counts = held.get(model["turkish_run"])
            if with_rate:
                values.append(
                    NOT_MEASURED if counts is None or counts["non_hallucination"] is None else
                    f'{pct(counts["non_hallucination"], digits)}<span class="small">{counts["dont_know"]:,} “{esc(option)}” of '
                    f'{counts["dont_know"] + counts["wrong"]:,} not right</span>'
                    f'<span class="small">answered {pct(counts["attempt_rate"], digits)}</span>')
            run = site.by_id[model["turkish_run"]]
            name = (f'<td class="model"><a class="model-name" href="{href(site, model)}">{esc(label(site, model))}</a>'
                    f'<span class="small">{esc(site.detail(run))} · English run {model["run"]}</span></td>')
            rows.append(f"<tr>{name}" + "".join(cell(text, value) for text, value in zip(labels, values)) + "</tr>")
        head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{esc(note)}</span></th>' for text, note in heads)
        rate_note = (f" English non-hallucination: “{esc(option)}” among the answers that were not right, in the decision "
                     "model's first English run with it offered as a sixth option; Not measured: no such run"
                     + (", as for every chat model, asked without the option." if group == "all" else ".")) if with_rate else ""
        return (f'<section class="card" id="{anchor("table", group)}" {shown(group)}>'
                f"<h2>Every {noun(group, 1)} in English</h2>"
                f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr>'
                f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
                f'<p class="note">Ranked by English accuracy, highest first: right answers of the {total:,} kept reading '
                "questions in each setup's first English run (an invalid answer counts as not right). Turkish accuracy: the "
                f"setup's Text tab run on the same {total:,} questions, for context; the paired comparison is on "
                f'<a href="{comparison}">English and Turkish</a>.{rate_note} Each name opens its Text tab run; under it, '
                "its settings and English run.</p></section>")

    def lead(group: str) -> str:
        count = counts[group]
        if not count:
            return (f"<div {shown(group)}><p>No {noun(group, 1)} has an English run yet: the comparison with Turkish, and "
                    f'which setups are still to run, are on <a href="{comparison}">English and Turkish</a>.</p></div>')
        split = (f" ({counts['decision']} {noun('decision', counts['decision'])} and {counts['chat']} "
                 f"{noun('chat', counts['chat'])})") if group == "all" else ""
        links = [(anchor("chart-accuracy", group), "Accuracy")]
        if group != "chat":
            links.append(("chart-non-hallucination", "Non-hallucination"))
        links.append((anchor("table", group), "The table"))
        nav = "".join(f'<a href="#{target}">{text}</a>' for target, text in links)
        return (f"<div {shown(group)}><p>The Text tab's {total:,} kept reading questions, translated into English, answered "
                f"by {count} {noun(group, count)}{split}: each one's first English run, with its Text tab settings. The "
                f'comparison with the same setups in Turkish, and the setups still to run, are on <a href="{comparison}">'
                f'English and Turkish</a>.</p><nav class="face-nav" aria-label="On this page">{nav}</nav></div>')

    comparison = rel(PATH, COMPARISON)
    body = f"""    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The reading questions in English</h1>
      {"".join(lead(group) for group in GROUPS)}
    </section>
    <section class="charts" aria-label="Charts">{charts}</section>
    <p class="note">Cost, latency and calibration are not measured in English.</p>
    {"".join(table(group) for group in GROUPS if counts[group])}"""
    return {PATH: site.page(PATH, TITLE, f"The Text tab's {total:,} kept reading questions in English: accuracy of "
                            f"{len(models)} setups ({counts['decision']} decision models, {counts['chat']} chat model "
                            "setups) and the decision models' non-hallucination rate with “I don't know”.", body)}
