"""English reading (english/): the Text tab's setups on its kept reading questions in English, from results.json's
english_reading only. Its face, under the view bar: nothing above the results but a group's empty-view line (no links
row: the view bar's row 3 links to the parts; the scope is in the first chart's heading, "Accuracy in English · 547
machine-translated questions"; the translation check's limit, limit_line(), and More about this page sit under the
charts), then the four parts row 3 links to: Accuracy (#accuracy, the language
difference first, as on turkish-vs-english/, then English accuracy), Non-hallucination (#non-hallucination), Cost (#cost)
and Latency (#latency), each chart in the
site's static style (Site hbars, each bar in its model family's colour, as the home page's charts), and one table ranked
by English accuracy with the four measures and the Decision Score (AA formula) column (english_reading.models[]
.decision_score, decision models only; a full-width table of it also sits under the two holding-back sides);
the charts and the table come once per type group of the view bar (data-models all/chat/decision,
toggled by site.js, its Class keys hiding rows and bars by data-class; the all group is the one shown without
JavaScript, every setup ranked together), counts and
sentences computed for that group. Non-hallucination holds back two ways side by side (sitebuild/holding_back.py), each
with decision and chat models in blocks of their own, never one ranking: by confidence, Not measured in English in each
block, and with "I don't know" in English (english_reading.dont_know's English sides and english_only, the rate; under
the decision block the models that almost never chose it); under the two, set apart, the Turkish reference (each setup's
Text tab run at the threshold); a
setup without an English run with the option reads Running (a chat model's run still running, page_config.json's
dont_know.running) or Not run (a decision model not run with it yet). Cost and latency are each
setup's first English run's (english_reading.models[].cost and .latency), on a log scale as on the home page. English-only
setups (english_reading.english_only: no Text tab run, Ümit's small models) are ranked with the others (english_members):
their Turkish accuracy reads Not run, they have no Turkish reference, and their name links to their row here
(only_anchor), as they have no model page. The comparison with Turkish is turkish-vs-english/. It needs no JavaScript
and changes no number of the other pages."""

from __future__ import annotations

import json
from typing import Any

from sitebuild.english_reading import (NO_OPTION, NO_RATE, NOT_RUN, PATH as COMPARISON, RECORD, RUNNING, TRANSLATORS,
                                       anchor, check_dont_know, cost_note, english_members, english_only, entry_href,
                                       experiments_note, group_models, idk_key, label, limit_line, limit_note,
                                       measure_card, measure_cell, measure_heads, missing_note, missing_side, name_html,
                                       noun, only_anchor, setup_families, setup_icon, setup_key, setup_run,
                                       turkish_running)
from sitebuild import holding_back as hold
from sitebuild.site import (GROUPS, Site, cost_per, cost_unit_in, esc, family_legend, hbars, measure_rows, more_link, pct,
                            rel, shown)
from sitebuild.vision import cell

PATH = "english/"
TITLE = "English reading"


def check(site: Site, data: dict[str, Any]) -> None:
    """Stops the build when english_reading no longer fits what the page says: each setup with its Text tab run, the
    first English run the one shown, its counts covering the kept questions and its accuracy its counts, in order of
    English right answers; the decision and chat groups adding up to every setup; each English-only setup without a Text
    tab run, in its own order of English accuracy, its group its kind's."""
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
    alone = english_only(data)
    for model in alone:
        if "turkish_run" in model or model["run"] in site.by_id or model["runs"][0] != model["run"]:
            problems.append(f"{model['name']}: English only, but with a Text tab run or not its first English run shown")
        counts = model["english"]
        if counts["right"] + counts["wrong"] + counts["invalid"] != total or abs(counts["accuracy"] - counts["right"] / total) > 1e-9:
            problems.append(f"{model['name']}: its English counts do not give its accuracy on the {total} questions")
        if model["group"] != ("decision" if site.decision(model) else "chat"):
            problems.append(f"{model['name']}: English only, its group is not its kind's")
    if [model["english"]["accuracy"] for model in alone] != sorted((model["english"]["accuracy"] for model in alone), reverse=True):
        problems.append("the English-only setups are not ordered by English accuracy")
    if problems:
        raise SystemExit("english_view:\n  " + "\n  ".join(problems))


def href(site: Site, model: dict[str, Any]) -> str:
    return entry_href(site, PATH, model)


SCORE_HEAD = "Decision Score (AA formula)"
SCORE_NOTE = "Artificial Analysis's formula applied to our questions. Not their Index."
SCORE_SCOPE = "Decision models only: chat models and the I don't know runs are excluded."


def score_cell(model: dict[str, Any]) -> str:
    """A setup's Decision Score cell: the score to 2 decimals with its Brier under it, "unavailable" with the reason
    in its title, or "not applicable" for a chat model (english_reading.models[].decision_score)."""
    if "decision_score" in model:
        found = model["decision_score"]
        return f'{found["score"]:.2f}<span class="small">chosen-answer Brier {found["brier"]:.4f}</span>'
    if "decision_score_unavailable" in model:
        return f'<span class="nm" title="{esc(model["decision_score_unavailable"])}">unavailable</span>'
    return '<span class="nm">not applicable</span>'


def score_notes(site: Site, models: list[dict[str, Any]]) -> str:
    """The Decision Score notes under a table of `models`: the formula, the two required lines, and each unavailable
    setup's reason."""
    unavailable = "".join(f" {esc(label(site, model))}: unavailable, {esc(model['decision_score_unavailable'])}."
                          for model in models if "decision_score_unavailable" in model)
    return (f'<p class="note">{esc(SCORE_HEAD)}: 50 × (1 + accuracy − chosen-answer Brier) on the first English run, '
            "the chosen-answer Brier being the mean of (p − c)², p the probability given to the chosen answer and c 1 if "
            f"it is right, else 0.{unavailable}</p><p class=\"note\">{esc(SCORE_NOTE)} {esc(SCORE_SCOPE)}</p>")


def score_table(site: Site, models: list[dict[str, Any]]) -> str:
    """The decision models' Decision Score table in the confidence section: per decision model of `models` (ranked as
    the page ranks them), its score, accuracy and chosen-answer Brier from its first English run, then the notes."""
    mine = [model for model in models if "decision_score" in model or "decision_score_unavailable" in model]
    if not mine:
        return ""
    heads = (SCORE_HEAD, "Accuracy", "Chosen-answer Brier")
    rows = []
    for model in mine:
        found = model.get("decision_score")
        values = ([score_cell(model), '<span class="nm">unavailable</span>', '<span class="nm">unavailable</span>']
                  if found is None else
                  [f'{found["score"]:.2f}', f'{100 * found["accuracy"]:.2f}%', f'{found["brier"]:.4f}'])
        rows.append(f'<tr{site.class_attribute(setup_run(site, model))}><td class="model">{setup_icon(site, model)}'
                    f'{name_html(site, setup_run(site, model), href(site, model))}</td>'
                    + "".join(cell(text, value) for text, value in zip(heads, values))
                    + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(text)}</th>' for text in heads)
    return (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>{score_notes(site, mine)}')


def build(site: Site) -> dict[str, str]:
    if "english_reading" not in site.results:
        return {}
    data = site.results["english_reading"]
    check(site, data)
    idk = data["dont_know"]
    check_dont_know(site, data, idk)
    digits = site.config["percent_digits"]
    family = lambda model: setup_families(site)[setup_key(model)]  # noqa: E731
    total, models = data["questions"], data["models"]
    option = idk["option"]
    counts = {group: len(english_members(site, data, group)) for group in GROUPS}
    # English "I don't know": the English side of each paired model, and the models with an English run only, by
    # setup_key (an English-only setup's by its English reading entry, idk_key).
    english_idk = [(model["text_run"], model["english"]) for model in idk["models"]] + \
                  [(idk_key(model), model["english"]) for model in english_only(idk)]
    by_run = {setup_key(model): model for model in models + english_only(data)}
    held = {run: counts for run, counts in english_idk}
    if len(held) != len(english_idk) or any(run not in by_run for run in held):
        raise SystemExit("english_view: an English “I don't know” run is not one setup of the accuracy comparison")
    running_reason = site.config["dont_know"]["running"]

    def card(base: str, attributes: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str,
             head: tuple[str, str]) -> str:
        return (f'<figure class="panel chart-card" id="{base}" {attributes}><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, head=head)}<p class="chart-legend">{legend}</p></figure>')

    def accuracy_card(group: str) -> str:
        members = english_members(site, data, group)
        rows = [{"label": site.title(setup_run(site, model)), "tag": site.tag(setup_run(site, model)),
                 "family": family(model)["name"], "href": href(site, model),
                 "class_key": site.model_class(setup_run(site, model)),
                 "text": f"{pct(model['english']['accuracy'], digits)} · {model['english']['right']:,}",
                 "bars": [{"value": model["english"]["accuracy"], "colour": family(model)["colour"]}],
                 "title": f"{label(site, model)}: {model['english']['right']:,} of {total:,} right in English "
                          f"(run {model['run']})"}
                for model in members]
        return card(anchor("chart-accuracy", group), shown(group), f"Accuracy in English · {total:,} machine-translated questions",
                    f"Share of the {total:,} kept reading questions answered right in English, then the right answers of "
                    f"{total:,}: each of the {len(members)} {noun(group, len(members))}' first English run · higher is better",
                    rows, family_legend([family(model) for model in members]), ("Accuracy · Right", "% · Right"))

    def rates_card(group: str) -> str:
        """A group's Non-hallucination card, held back two ways side by side (holding_back), each with decision and chat
        models as separate blocks: (A) by confidence, Not measured in English in each block (no English run has a
        confidence at the threshold), and (B) the English non-hallucination rate with the option, the setups with an
        English run with it by the rate; under each block the setups whose run is still running (chat), not run
        (decision) or not possible (NO_OPTION), and under the decision block the models that almost never chose the
        option. Under the two, set apart and smaller, the Turkish reference: each setup's Text tab run at the threshold."""
        members = english_members(site, data, group)
        provider = lambda model: setup_run(site, model)["provider"]  # noqa: E731
        confidence = hold.not_measured_side(group, "English")
        scores = score_table(site, members)
        if scores:
            scores = hold.block(f"{SCORE_HEAD}, decision models", scores, level=3)
        reference = hold.confidence_side(
            site, [(site.by_id[model["turkish_run"]], label(site, model), href(site, model)) for model in members
                   if "turkish_run" in model], group,
            ", in its Text tab run on the Turkish questions, for reference", title="Turkish reference (the Text tab runs)")

        def option_block(kind: str, heading: str) -> str:
            mine = [model for model in members if hold.kind_of(site, setup_run(site, model)) == kind]
            if not mine:
                return ""
            rated = sorted(((model, held[setup_key(model)]) for model in mine
                            if setup_key(model) in held and held[setup_key(model)]["non_hallucination"] is not None),
                           key=lambda pair: (-pair[1]["non_hallucination"], label(site, pair[0]).casefold()))
            undefined = [label(site, model) for model in mine
                         if setup_key(model) in held and held[setup_key(model)]["non_hallucination"] is None]
            no_option = [(label(site, model), NO_OPTION[provider(model)]) for model in mine
                         if setup_key(model) not in held and provider(model) in NO_OPTION]
            waiting = [label(site, model) for model in mine if setup_key(model) not in held and provider(model) not in NO_OPTION]
            rows = [{"label": site.title(setup_run(site, model)), "tag": site.tag(setup_run(site, model)),
                     "family": family(model)["name"], "href": href(site, model),
                     "class_key": site.model_class(setup_run(site, model)),
                     "texts": [pct(counts["non_hallucination"], digits), pct(counts["attempt_rate"], digits),
                               pct(hold.error_rate(counts), digits) if hold.error_rate(counts) is not None else "none"],
                     "bars": [{"value": counts["non_hallucination"], "colour": family(model)["colour"]}],
                     "title": f"{label(site, model)}: {counts['dont_know']:,} “{option}” of "
                              f"{counts['dont_know'] + counts['wrong']:,} not right; {counts['right'] + counts['wrong']:,} of "
                              f"{total:,} answered, {counts['wrong']:,} of them wrong (run {counts['run']})"}
                    for model, counts in rated]
            rare = hold.rare_note([(label(site, model), held[setup_key(model)]["dont_know"],
                                    held[setup_key(model)]["non_hallucination"]) for model in mine if setup_key(model) in held],
                                  total, site.results["dont_know"]["vs_confidence_share"], option, digits,
                                  "confidence is not measured in English; the Turkish reference below shows their Text "
                                  "tab runs at the threshold") \
                if kind == "decision" else ""
            legend = (family_legend([family(model) for model, _ in rated])
                      + (f" <span>No rate (neither a wrong answer nor “{esc(option)}”): {esc(', '.join(undefined))}.</span>"
                         if undefined else "")
                      + ((f" <span>Decision models not run with “{esc(option)}” in English yet: {esc(', '.join(waiting))}.</span>"
                          if kind == "decision" else
                          f" <span>{esc(running_reason.removesuffix('.'))}; still running in English: {esc(', '.join(waiting))}.</span>")
                         if waiting else "")
                      + "".join(f" <span>Not run, as {esc(reason)}: {esc(name)}.</span>" for name, reason in no_option))
            line = (f'<p class="hold-kind">Each of the {len(rated)} {noun(kind, len(rated))}\' first English run with it.</p>'
                    if rated else "")
            return hold.block(heading, f'{line}{hbars(rows, columns=hold.COLUMNS) if rows else ""}'
                                       f'{rare}<p class="chart-legend">{legend}</p>')

        with_option = hold.side(
            hold.option_title(option) + " in English",
            f"“{esc(option)}” among the answers that were not right, with it offered as a sixth option in English, on the "
            f"{total:,} kept questions; beside it the share answered (right + wrong of {total:,}) and the error rate among "
            "the answers (wrong of right + wrong) · higher non-hallucination is better, read with the share answered; a "
            "model that always chose the option would reach 100% with no right answers",
            "".join(option_block(kind, heading) for kind, heading in hold.kinds(group)))
        return (f'<figure class="panel chart-card" id="{anchor("chart-non-hallucination", group)}" {shown(group)}>'
                f'<div class="chart-head"><h2>Non-hallucination</h2></div>{hold.pair(confidence, with_option)}{scores}'
                f'<div class="hold-reference">{reference}</div></figure>')

    method = f"{rel(PATH, COMPARISON)}#method"

    def part(key: str, title: str, cards: str) -> str:
        # A Measure view (site.measure_rows) opens with its Measure keys; Accuracy is the Leaderboard's.
        keys = measure_rows(PATH, (PATH, key)) if key != "accuracy" else ""
        return f'<section class="measure" id="{key}" aria-label="{title}">{keys}{cards}</section>'

    charts = (part("accuracy", "Accuracy", "".join(accuracy_card(group) for group in GROUPS if counts[group]))
              + part("non-hallucination", "Non-hallucination", "".join(rates_card(group) for group in GROUPS if counts[group]))
              + "".join(part(key, title, "".join(measure_card(site, data, group, key, ("english",), href, method, english_members)
                                                 for group in GROUPS if counts[group]))
                        for key, title in (("cost", "Cost"), ("latency", "Latency"))))

    def table(group: str) -> str:
        """A group's copy of the table, ranked by English accuracy, with the English non-hallucination column."""
        heads = [("English accuracy", "first English run; higher is better"),
                 (SCORE_HEAD, "first English run; higher is better"),
                 ("Turkish accuracy", f"Text tab run, same {total:,}; for context"),
                 ("English non-hallucination",
                  f"of answers not right, % “{option}” · higher is better; answered and error rate under it")]
        heads += measure_heads("cost", ("english",)) + measure_heads("latency", ("english",))
        labels = [f"{head} ({note})" for head, note in heads]
        rows = []
        members = english_members(site, data, group)
        running = turkish_running(site, data)
        for model in members:
            values = [
                f'{pct(model["english"]["accuracy"], digits)}<span class="small">{model["english"]["right"]:,} of {total:,} right</span>',
                f'{pct(model["turkish"]["accuracy"], digits)}<span class="small">{model["turkish"]["right"]:,} of {total:,} right</span>'
                if "turkish_run" in model else
                f'{RUNNING}<span class="small">its Text tab run is still running</span>' if model["model"] in running else
                f'{NOT_RUN}<span class="small">English only, no Text tab run</span>',
            ]
            values.insert(1, score_cell(model))
            counts = held.get(setup_key(model))
            values.append(
                missing_side(site, setup_run(site, model)) if counts is None else
                f'{NO_RATE if counts["non_hallucination"] is None else pct(counts["non_hallucination"], digits)}'
                f'<span class="small">{counts["dont_know"]:,} “{esc(option)}” of '
                f'{counts["dont_know"] + counts["wrong"]:,} not right</span>'
                f'<span class="small">answered {pct(counts["attempt_rate"], digits)}</span>'
                + ("" if hold.error_rate(counts) is None else
                   f'<span class="small">error rate {pct(hold.error_rate(counts), digits)}</span>'))
            values += [measure_cell(site, model, "cost", "english"), measure_cell(site, model, "latency", "english")]
            run = setup_run(site, model)
            row_id = "" if "turkish_run" in model else f' id="{anchor(only_anchor(model), group)}"'
            name = (f'<td class="model">{setup_icon(site, model)}'
                    f'{name_html(site, run, href(site, model), " · ".join(filter(None, (site.detail(run), f"English run {model['run']}"))))}</td>')
            rows.append(f"<tr{row_id}{site.class_attribute(run)}>{name}"
                        + "".join(cell(text, value) for text, value in zip(labels, values)) + "</tr>")
        head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{cost_unit_in(esc(note))}</span></th>'
                       for text, note in heads)
        alone = [model for model in members if "turkish_run" not in model]
        rate_note = (f" English non-hallucination: “{esc(option)}” among the answers that were not right, in the setup's "
                     "first English run with it offered as a sixth option; Running: a chat model's run still running; Not "
                     "run: a decision model not run with it yet" + (", or an English-only setup" if alone else "") + ".")
        return (f'<section class="card" id="{anchor("table", group)}" {shown(group)} data-top-rows>'
                f"<h2>Every {noun(group, 1)} in English</h2>"
                f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr>'
                f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
                f'<p class="note">Ranked by English accuracy, highest first: right answers of the {total:,} kept reading '
                "questions in each setup's first English run (an invalid answer counts as not right). Turkish accuracy: the "
                f"setup's Text tab run on the same {total:,} questions, for context"
                + (" (Not run: an English-only setup, with no Text tab run"
                   + ("; Running: its Text tab run is still under way, shown when it is in"
                      if any(model["model"] in running for model in alone) else "") + ")" if alone else "")
                + f'; the paired comparison is on <a href="{comparison}">English and Turkish</a>.{rate_note} English cost: $ '
                f"{cost_per()}, with its basis under it; English latency: the median time per request, with the request "
                "size and the requests in flight under it, each from the first English run (Cost and Latency above)."
                + (" " + missing_note(site, members, ("english",))).rstrip()
                + " Each name opens its model page's English section"
                + (" (an English-only setup has no model page: its name opens its row here)" if alone else "")
                + "; its tooltip gives its settings and English run.</p>"
                f'{score_notes(site, members)}'
                f'<p class="note">{esc(cost_note(site, members, ("english",)))}</p></section>')

    def lead(group: str) -> str:
        count = counts[group]
        if not count:
            return (f"<div {shown(group)}><p>No {noun(group, 1)} has an English run yet: the setups still to run are on "
                    f'<a href="{comparison}">English and Turkish</a>.</p></div>')
        split = (f" ({counts['decision']} {noun('decision', counts['decision'])} and {counts['chat']} "
                 f"{noun('chat', counts['chat'])})") if group == "all" else ""
        alone = sum(1 for model in english_members(site, data, group) if "turkish_run" not in model)
        settings = ("with their Text tab settings" if not alone else
                    f"with their Text tab settings, {alone} of them English only (no Text tab run, with their own settings)")
        return (f"<div {shown(group)}><p>The Text tab's {total:,} kept reading questions in English, answered by {count} "
                f"{noun(group, count)}{split} {settings}. The paired comparison with Turkish is on "
                f'<a href="{comparison}">English and Turkish</a>.</p></div>')

    def empty(group: str) -> str:
        """A group's empty-view line at the top, where none of its setups has an English run (lead in the notes)."""
        return "" if counts[group] else lead(group)

    comparison = rel(PATH, COMPARISON)
    translator = TRANSLATORS[json.loads(RECORD.read_text(encoding="utf-8"))["translator"]["model"]]
    site.note(PATH, TITLE, "".join(lead(group) for group in GROUPS) + limit_note(translator, method)
              + experiments_note(site, PATH))
    body = f"""    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The reading questions in English</h1>
      {"".join(empty(group) for group in GROUPS)}
    </section>
    <div class="charts" data-top-rows>{charts}</div>
    {limit_line(method)}
    {more_link(PATH)}
    <p class="note">Calibration of holding back by confidence at the {pct(site.config["threshold"], 0)} threshold is not measured in English.</p>
    {"".join(table(group) for group in GROUPS if counts[group])}"""
    return {PATH: site.page(PATH, TITLE, f"The Text tab's {total:,} kept reading questions in English: accuracy of "
                            f"{counts['all']} setups ({counts['decision']} decision models, {counts['chat']} chat model "
                            "setups) and their non-hallucination rate with “I don't know”.", body,
                            image="english")}
