"""English reading (english/): the Text tab's setups on its kept reading questions in English, from results.json's
english_reading only. Its face, under the view bar: a one-sentence lead and the translation check's limit (no links row:
the view bar's row 3 links to the parts), then the four parts row 3 links to: Accuracy (#accuracy, the language
difference first, as on turkish-vs-english/, then English accuracy), Non-hallucination (#non-hallucination), Cost (#cost)
and Latency (#latency), each chart in the
site's static style (Site hbars, each bar in its model family's colour, as the home page's charts), and one table ranked
by English accuracy with the four measures; the charts and the table come once per group of the view bar (data-models,
toggled by site.js; the all group is the one shown without JavaScript, every setup ranked together), counts and
sentences computed for that group. The non-hallucination rate with "I don't know" in English (english_reading.dont_know's
English sides and english_only) is charted for each group, decision and chat models ranked together in the all group; a
setup without an English run with the option reads Running (a chat model's run still running, page_config.json's
dont_know.running) or Not run (a decision model not run with it yet). Cost and latency are each
setup's first English run's (english_reading.models[].cost and .latency), on a log scale as on the home page. The
comparison with Turkish is turkish-vs-english/. It needs no JavaScript and changes no number of the other pages."""

from __future__ import annotations

import json
from typing import Any

from sitebuild.english_reading import (NO_RATE, NOT_RUN, PATH as COMPARISON, RECORD, RUNNING, TRANSLATORS, anchor,
                                       check_dont_know, cost_note, english_only, experiments_note, group_models, label,
                                       limit_note, measure_card, measure_cell, measure_heads, missing_note, noun,
                                       setup_href)
from sitebuild.site import GROUPS, Site, cost_per, cost_unit_in, esc, family_legend, hbars, pct, rel, shown
from sitebuild.vision import cell

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
    return setup_href(site, PATH, model["turkish_run"])


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
    running_reason = site.config["dont_know"]["running"]

    def card(base: str, attributes: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str,
             head: tuple[str, str]) -> str:
        return (f'<figure class="panel chart-card" id="{base}" {attributes}><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, head=head)}<p class="chart-legend">{legend}</p></figure>')

    def accuracy_card(group: str) -> str:
        members = group_models(site, data, group)
        rows = [{"label": label(site, model), "family": family(model)["name"], "href": href(site, model),
                 "text": f"{pct(model['english']['accuracy'], digits)} · {model['english']['right']:,}",
                 "bars": [{"value": model["english"]["accuracy"], "colour": family(model)["colour"]}],
                 "title": f"{label(site, model)}: {model['english']['right']:,} of {total:,} right in English "
                          f"(run {model['run']})"}
                for model in members]
        return card(anchor("chart-accuracy", group), shown(group), f"Accuracy on the {total:,} English questions",
                    f"Share of the {total:,} kept reading questions answered right in English, then the right answers of "
                    f"{total:,}: each of the {len(members)} {noun(group, len(members))}' first English run · higher is better",
                    rows, family_legend([family(model) for model in members]), ("Accuracy · Right", "% · Right"))

    def rates_card(group: str) -> str:
        """A group's chart of the English non-hallucination rate: its setups with an English run with the option, by
        the rate; under it the setups whose run is still running (chat) or not run (decision)."""
        members = group_models(site, data, group)
        rated = sorted(((model, held[model["turkish_run"]]) for model in members
                        if model["turkish_run"] in held and held[model["turkish_run"]]["non_hallucination"] is not None),
                       key=lambda pair: (-pair[1]["non_hallucination"], label(site, pair[0]).casefold()))
        undefined = [label(site, model) for model in members
                     if model["turkish_run"] in held and held[model["turkish_run"]]["non_hallucination"] is None]
        running = [label(site, model) for model in members if model["turkish_run"] not in held
                   and not site.decision(site.by_id[model["turkish_run"]])]
        unrun = [label(site, model) for model in members if model["turkish_run"] not in held
                 and site.decision(site.by_id[model["turkish_run"]])]
        rows = [{"label": label(site, model), "family": family(model)["name"], "href": href(site, model),
                 "text": f"{pct(counts['non_hallucination'], digits)} · {pct(counts['attempt_rate'], digits)}",
                 "bars": [{"value": counts["non_hallucination"], "colour": family(model)["colour"]}],
                 "title": f"{label(site, model)}: {counts['dont_know']:,} “{option}” of "
                          f"{counts['dont_know'] + counts['wrong']:,} not right; {counts['right'] + counts['wrong']:,} of "
                          f"{total:,} answered (run {counts['run']})"}
                for model, counts in rated]
        legend = (family_legend([family(model) for model, _ in rated])
                  + " <span>A model that always chose the option would reach 100% with no right answers.</span>"
                  + (f" <span>No rate (neither a wrong answer nor “{esc(option)}”): {esc(', '.join(undefined))}.</span>"
                     if undefined else "")
                  + (f" <span>{esc(running_reason.removesuffix('.'))}; still running in English: {esc(', '.join(running))}.</span>"
                     if running else "")
                  + (f" <span>Decision models not run with “{esc(option)}” in English yet: {esc(', '.join(unrun))}.</span>"
                     if unrun else ""))
        return card(
            anchor("chart-non-hallucination", group), shown(group), "Non-hallucination rate with “I don't know” in English",
            f"“{esc(option)}” among the answers that were not right, with it offered as a sixth option in English, on the "
            f"{total:,} kept questions, then the answered share (right + wrong of {total:,}): each of the {len(rated)} "
            f"{noun(group, len(rated))}' first run with it · higher is better, read with the answered share",
            rows, legend, ("Non-hallucination · Answered", "Rate · Ans."))

    method = f"{rel(PATH, COMPARISON)}#method"

    def part(key: str, title: str, cards: str) -> str:
        return f'<section class="measure" id="{key}" aria-label="{title}">{cards}</section>'

    charts = (part("accuracy", "Accuracy", "".join(accuracy_card(group) for group in GROUPS if counts[group]))
              + part("non-hallucination", "Non-hallucination", "".join(rates_card(group) for group in GROUPS if counts[group]))
              + "".join(part(key, title, "".join(measure_card(site, data, group, key, ("english",), href, method)
                                                 for group in GROUPS if counts[group]))
                        for key, title in (("cost", "Cost"), ("latency", "Latency"))))

    def table(group: str) -> str:
        """A group's copy of the table, ranked by English accuracy, with the English non-hallucination column."""
        heads = [("English accuracy", "first English run; higher is better"),
                 ("Turkish accuracy", f"Text tab run, same {total:,}; for context"),
                 ("English non-hallucination", f"with “{option}”; higher is better")]
        heads += measure_heads("cost", ("english",)) + measure_heads("latency", ("english",))
        labels = [f"{head} ({note})" for head, note in heads]
        rows = []
        for model in group_models(site, data, group):
            values = [
                f'{pct(model["english"]["accuracy"], digits)}<span class="small">{model["english"]["right"]:,} of {total:,} right</span>',
                f'{pct(model["turkish"]["accuracy"], digits)}<span class="small">{model["turkish"]["right"]:,} of {total:,} right</span>',
            ]
            counts = held.get(model["turkish_run"])
            values.append(
                (RUNNING if not site.decision(site.by_id[model["turkish_run"]]) else NOT_RUN) if counts is None else
                f'{NO_RATE if counts["non_hallucination"] is None else pct(counts["non_hallucination"], digits)}'
                f'<span class="small">{counts["dont_know"]:,} “{esc(option)}” of '
                f'{counts["dont_know"] + counts["wrong"]:,} not right</span>'
                f'<span class="small">answered {pct(counts["attempt_rate"], digits)}</span>')
            values += [measure_cell(site, model, "cost", "english"), measure_cell(site, model, "latency", "english")]
            run = site.by_id[model["turkish_run"]]
            name = (f'<td class="model">{site.icon(run)}<a class="model-name" href="{href(site, model)}" '
                    f'title="{esc(" · ".join(filter(None, (site.detail(run), f"English run {model['run']}"))))}">'
                    f'{esc(label(site, model))}</a></td>')
            rows.append(f"<tr>{name}" + "".join(cell(text, value) for text, value in zip(labels, values)) + "</tr>")
        head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{cost_unit_in(esc(note))}</span></th>'
                       for text, note in heads)
        rate_note = (f" English non-hallucination: “{esc(option)}” among the answers that were not right, in the setup's "
                     "first English run with it offered as a sixth option; Running: a chat model's run still running; Not "
                     "run: a decision model not run with it yet.")
        return (f'<section class="card" id="{anchor("table", group)}" {shown(group)}>'
                f"<h2>Every {noun(group, 1)} in English</h2>"
                f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr>'
                f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
                f'<p class="note">Ranked by English accuracy, highest first: right answers of the {total:,} kept reading '
                "questions in each setup's first English run (an invalid answer counts as not right). Turkish accuracy: the "
                f"setup's Text tab run on the same {total:,} questions, for context; the paired comparison is on "
                f'<a href="{comparison}">English and Turkish</a>.{rate_note} English cost: $ {cost_per()}, with its '
                "basis under it; English latency: the median time per request, with the request size and "
                "the requests in flight under it, each from the first English run (Cost and Latency above)."
                + (" " + missing_note(site, group_models(site, data, group), ("english",))).rstrip()
                + " Each name opens its model page's English section; its tooltip gives its settings and English run.</p>"
                f'<p class="note">{esc(cost_note(site, group_models(site, data, group), ("english",)))}</p></section>')

    def lead(group: str) -> str:
        count = counts[group]
        if not count:
            return (f"<div {shown(group)}><p>No {noun(group, 1)} has an English run yet: the setups still to run are on "
                    f'<a href="{comparison}">English and Turkish</a>.</p></div>')
        split = (f" ({counts['decision']} {noun('decision', counts['decision'])} and {counts['chat']} "
                 f"{noun('chat', counts['chat'])})") if group == "all" else ""
        return (f"<div {shown(group)}><p>The Text tab's {total:,} kept reading questions in English, answered by {count} "
                f"{noun(group, count)}{split} with their Text tab settings. The paired comparison with Turkish is on "
                f'<a href="{comparison}">English and Turkish</a>.</p></div>')

    comparison = rel(PATH, COMPARISON)
    translator = TRANSLATORS[json.loads(RECORD.read_text(encoding="utf-8"))["translator"]["model"]]
    body = f"""    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The reading questions in English</h1>
      {"".join(lead(group) for group in GROUPS)}
      {limit_note(translator, method)}{experiments_note(site, PATH)}
    </section>
    <div class="charts">{charts}</div>
    <p class="note">Calibration is not measured in English.</p>
    {"".join(table(group) for group in GROUPS if counts[group])}"""
    return {PATH: site.page(PATH, TITLE, f"The Text tab's {total:,} kept reading questions in English: accuracy of "
                            f"{len(models)} setups ({counts['decision']} decision models, {counts['chat']} chat model "
                            "setups) and their non-hallucination rate with “I don't know”.", body,
                            image="english")}
