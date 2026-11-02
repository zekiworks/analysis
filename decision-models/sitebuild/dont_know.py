"""Hallucination (dont-know/), the site's third tab: the Text tab's questions with one more option after each
question's own, "Bilmiyorum" ("I don't know"), from results.json's `dont_know` and page_config.json's `dont_know` (the
models not run, with their reasons). Its face, as the home page's, is charts (face()): the non-hallucination rate, the
same rate with the option and held back by confidence, and accuracy with the option against accuracy with five options,
as HTML bars (Site hbars). Under Info: the table (one row per model, from its first run, ranked by non-hallucination
rate, accuracy breaking ties; a model with more than one run shows the range over its runs), What we found and Our
method. It needs no JavaScript. The tab ranks nothing on the Text tab and changes none of its numbers."""

from __future__ import annotations

import math
from typing import Any

import build_page as bp
from sitebuild.site import Site, esc, hbars, pct, rank_fill, rel, scale_legend
from sitebuild.vision import cell, joined, run_span

PATH = "dont-know/"
# The models the tab covers, as chosen before the runs (the Text tab at results 25290875).
SELECTION = ("the ten most accurate decision models on the Text tab at results 25290875, plus Base Labs' Elephant-1 and "
             "Mammoth-1 and SubQ Snap 1.1 once their text runs are published")
NEUTRAL = "neither better nor worse on its own"


def columns(option: str) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: header and which direction is better."""
    return (
        ("Non-hallucination rate", "higher is better"),
        ("Derived non-hallucination rate", "from the 5-option text run; higher is better"),
        ("Accuracy", "higher is better"),
        ("Attempt rate", f"higher means it answers more often; {NEUTRAL}"),
        (f"Mean probability of “{option}”", f"higher means more probability on “I don't know”; {NEUTRAL}"),
        ("Text accuracy with five options", "the Text tab's number; higher is better"),
        ("Runs", "range over the runs where more than one"),
    )


def ranked(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tab's leaderboard order: non-hallucination rate, highest first (a model without one last), then accuracy, then
    name. results.json keeps the models in its own order."""
    return sorted(models, key=lambda model: (model["non_hallucination"] is None, -(model["non_hallucination"] or 0),
                                             -model["accuracy"], model["name"].casefold()))


def model_cell(site: Site, model: dict[str, Any]) -> str:
    """The model, linked to the page of its Text tab setup (the original run)."""
    run = site.by_id[model["original_run"]]
    return (f'<td class="model"><a class="model-name" href="{rel(PATH, site.model_path(run))}">{esc(site.row_name(run))}</a>'
            f'<span class="small">{esc(site.detail(run))}</span></td>')


def row(site: Site, data: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    option, total = data["option"], data["questions"]
    percent = lambda value: '<span class="nm">Not measured</span>' if value is None else pct(value, digits)  # noqa: E731
    heads = [f"{head} ({direction})" for head, direction in columns(option)]
    derived = model["derived"]
    cut = ("no cut-off (no answer has a score)" if derived["cut_off"] is None else
           f"cut-off {derived['cut_off']:.4f}: {derived['right']:,} right + {derived['wrong']:,} wrong answered, "
           f"{derived['abstained']:,} held back")
    invalid = f", {model['invalid']:,} invalid" if model["invalid"] else ""
    run = site.by_id[model["original_run"]]
    spread = model["spread"]
    if spread is None:
        runs_text = run_span(model["runs"])
    else:
        ranges = [
            f"{name} {percent(spread[key][0])} to {percent(spread[key][1])}" if spread[key] else f"{name} not measured"
            for key, name in (("non_hallucination", "Non-hallucination"), ("accuracy", "Accuracy"),
                              ("attempt_rate", "Attempt rate"), ("mean_dont_know_probability", "Mean probability"))
        ]
        changed = model["answers_changed"]
        ranges.append(f"{changed:,} answer{'' if changed == 1 else 's'} changed between runs")
        runs_text = run_span(model["runs"]) + "".join(f'<span class="small">{item}</span>' for item in ranges)
    values = [
        f'{percent(model["non_hallucination"])}<span class="small">{model["dont_know"]:,} “{esc(option)}” of '
        f'{model["dont_know"] + model["wrong"]:,} not right</span>',
        f'{percent(derived["non_hallucination"])}<span class="small">{cut}, attempt rate {percent(derived["attempt_rate"])}</span>',
        f'{percent(model["accuracy"])}<span class="small">{model["right"]:,} of {total:,} right</span>',
        f'{percent(model["attempt_rate"])}<span class="small">{model["right"] + model["wrong"]:,} answered, '
        f'{model["dont_know"]:,} “{esc(option)}”{invalid}</span>',
        percent(model["mean_dont_know_probability"]),
        f'{percent(model["original_accuracy"])}<span class="small"><a href="{rel(PATH, site.model_path(run))}">run {run["run"]}</a></span>',
        runs_text,
    ]
    return f"<tr>{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>"


def table(site: Site, data: dict[str, Any]) -> str:
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>'
                   for name, direction in columns(data["option"]))
    rows = "".join(row(site, data, model) for model in ranked(data["models"]))
    return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f"</thead><tbody>{rows}</tbody></table></div>")


def not_run(items: list[dict[str, Any]]) -> str:
    """The models chosen but not run, each with its reason (page_config.json's dont_know.not_run)."""
    if not items:
        return ""
    lines = "".join(f"<li><strong>{esc(item['name'])}</strong>: {esc(item['reason'].removeprefix('Not run: '))}</li>" for item in items)
    return f'<h3 class="board-group">Not run</h3><ul>{lines}</ul>'


def findings(site: Site, data: dict[str, Any]) -> str:
    """What we found: the table's main results in words, every number computed from results.json's dont_know. The
    sentences assume what they say (some models used the option and lost accuracy, the rest almost never chose it, each
    derived rate holds back on as many questions as its run said “Bilmiyorum”); the build stops when the data no longer
    fits them, so the text is rewritten rather than left wrong."""
    digits = site.config["percent_digits"]
    option, total = esc(data["option"]), data["questions"]
    p = lambda value: pct(value, digits)  # noqa: E731
    shown = lambda value: round(100 * value, digits)  # noqa: E731 - a rate in points, as the table shows it
    name = lambda model: esc(model["name"])  # noqa: E731
    models = ranked(data["models"])
    used = [model for model in models if model["dont_know"] >= total / 100]
    rare = [model for model in models if model["dont_know"] < total / 100]
    if len(used) < 3 or not rare or models[0] is not used[0]:
        raise SystemExit("dont_know findings: the text expects 3 or more models that used the option, one of them ranked "
                         "first, and some that almost never chose it")
    if any(model["invalid"] or not model["mean_dont_know_probability"] for model in models):
        raise SystemExit("dont_know findings: the text assumes no invalid answers and some probability on the option")
    if any(model["non_hallucination"] is None or model["derived"]["non_hallucination"] is None for model in models):
        raise SystemExit("dont_know findings: the text assumes every rate is defined (each model has a wrong or "
                         "“Bilmiyorum” answer)")
    if any(model["derived"]["abstained"] != model["dont_know"] for model in models):
        raise SystemExit("dont_know findings: a derived rate does not hold back on as many questions as its run")
    shares = [model["dont_know"] / total for model in used]
    means = {key: [model["mean_dont_know_probability"] for model in group] for key, group in (("used", used), ("rare", rare))}
    first = (f"<p>Of the {len(models)} models, {len(used)} used “{option}”, on {p(min(shares))} to {p(max(shares))} of the "
             f"questions. The other {len(rare)}, {joined([name(model) for model in rare])}, chose it on "
             f"{min(model['dont_know'] for model in rare):,} to {max(model['dont_know'] for model in rare):,} questions, "
             f"although each gave it some probability: a mean of {p(min(means['rare']))} to {p(max(means['rare']))}, against "
             f"{p(min(means['used']))} to {p(max(means['used']))} for the {len(used)}.</p>")
    drop = {model["name"]: 100 * (model["original_accuracy"] - model["accuracy"]) for model in used}
    if min(drop.values()) <= 0:
        raise SystemExit("dont_know findings: a model that used the option was not less accurate than on the Text tab")
    least = min(used, key=lambda model: drop[model["name"]])
    most = max(used, key=lambda model: drop[model["name"]])
    moved = [100 * (model["accuracy"] - model["original_accuracy"]) for model in rare]
    top = used[0]
    second = (f"<p>{name(top)} had the highest non-hallucination rate, {p(top['non_hallucination'])}: of its "
              f"{top['dont_know'] + top['wrong']:,} answers that were not right, {top['dont_know']:,} were “{option}”. "
              f"{name(used[1])} ({p(used[1]['non_hallucination'])}) and {name(used[2])} "
              f"({p(used[2]['non_hallucination'])}) follow. With the option, the {len(used)} were less accurate than in their "
              f"five-option runs on the Text tab, by {drop[least['name']]:.{digits}f} points ({name(least)}) to "
              f"{drop[most['name']]:.{digits}f} points ({name(most)}: {p(most['original_accuracy'])} against "
              f"{p(most['accuracy'])}). The {len(rare)} that almost never chose it moved by {min(moved):+.{digits}f} to "
              f"{max(moved):+.{digits}f} points.</p>")
    fewer = [model for model in used if model["derived"]["wrong"] < model["wrong"]]
    more = [model for model in used if model["derived"]["wrong"] > model["wrong"]]
    level = [model for model in used if model["derived"]["wrong"] == model["wrong"]]
    if not fewer:
        raise SystemExit("dont_know findings: the text expects the derived rate to leave fewer wrong answers for some model")
    saved = [model["wrong"] - model["derived"]["wrong"] for model in fewer]
    # Differences between the unrounded rates, rounded only when shown (not between the table's rounded rates).
    gaps = [100 * (model["derived"]["non_hallucination"] - model["non_hallucination"]) for model in fewer]
    third = (f"<p>For {len(fewer)} of the {len(used)}, the model's own confidence on its five-option run, holding back on as "
             f"many questions, left fewer wrong answers than “{option}” did: {min(saved):,} to {max(saved):,} fewer, a "
             f"non-hallucination rate {min(gaps):.{digits}f} to {max(gaps):.{digits}f} points higher (the derived rate in "
             f"the table).")
    if more:
        extra = joined([f"{model['derived']['wrong'] - model['wrong']:,}" for model in more])
        verb = "was the exception" if len(more) == 1 else "were the exceptions"
        third += f" {joined([name(model) for model in more])} {verb}, with {extra} more."
    if level:
        third += f" {joined([name(model) for model in level])} left as many either way."
    low = max(max(shown(model["non_hallucination"]), shown(model["derived"]["non_hallucination"])) for model in rare)
    third += f" For the {len(rare)} that almost never chose it, both rates are {low:.{digits}f}% or less."
    family = [model for model in models if model["vs_confidence"]["p_holm"] is not None]
    if [model["name"] for model in family] != [model["name"] for model in used]:
        raise SystemExit("dont_know findings: the models in the test's Holm family are not the models that used the option")
    significant = [model for model in family if model["vs_confidence"]["p_holm"] < 0.05]
    by_confidence = [model for model in significant if model["vs_confidence"]["option_only_wrong"] > model["vs_confidence"]["confidence_only_wrong"]]
    by_option = [model for model in significant if model not in by_confidence]

    def adjusted(group: list[dict[str, Any]]) -> str:
        """The models, then their Holm-adjusted p values as the site writes p ("each" when they read the same)."""
        texts = [bp.p_text(model["vs_confidence"]["p_holm"]) for model in group]
        values = f"adjusted {texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else f"adjusted {joined(texts)}"
        return f"{joined([name(model) for model in group])} ({values})"

    third += f" In the exact McNemar test on each model's first run, with Holm's correction over the {len(family)}, "
    if not significant:
        third += "none of these differences is significant: each could be chance."
    else:
        parts = []
        if by_confidence:
            parts.append(f"confidence left significantly fewer wrong answers for {adjusted(by_confidence)}")
        if by_option:
            parts.append(f"“{option}” left significantly fewer for {adjusted(by_option)}")
        rest = len(family) - len(significant)
        third += "; ".join(parts) + (f"; for the other {rest}, the difference could be chance." if rest else ".")
    return first + second + third + "</p>"


def headline(data: dict[str, Any]) -> str:
    """One line at the top of the tab, from vs_confidence: the models whose own confidence, holding back on as many
    questions, left significantly fewer wrong answers than the option (Holm-adjusted p below 0.05); none when there are
    none."""
    option = esc(data["option"])
    family = [model for model in ranked(data["models"]) if model["vs_confidence"]["p_holm"] is not None]
    better = [model for model in family if model["vs_confidence"]["p_holm"] < 0.05
              and model["vs_confidence"]["option_only_wrong"] > model["vs_confidence"]["confidence_only_wrong"]]
    if not better:
        return ""
    worse = [model for model in family if model["vs_confidence"]["p_holm"] < 0.05
             and model["vs_confidence"]["option_only_wrong"] < model["vs_confidence"]["confidence_only_wrong"]]
    rest = sum(1 for model in family if model["vs_confidence"]["p_holm"] >= 0.05)
    others = ""
    if worse:
        others += (f"; for {joined([esc(model['name']) for model in worse])}, “{option}” left significantly fewer wrong "
                   "answers")
    if rest:
        others += ("; for the other model that used it" if rest == 1 else f"; for the other {rest} models that used it") + \
            ", the difference could be chance"
    return (f"<p><strong>Holding back on as many questions, {joined([esc(model['name']) + '’s' for model in better])} own "
            f"confidence left significantly fewer wrong answers than “{option}” did</strong>{others} "
            f'(<a href="#findings">What we found</a>).</p>')


def face(site: Site, data: dict[str, Any]) -> str:
    """The tab's face: four chart cards, each with a line saying which way is better, every number from results.json's
    dont_know: the non-hallucination rate, that rate against confidence, the paired test of the two (vs_confidence) and
    accuracy. A single-series bar takes the ranking scale between the models' worst and best values on its chart."""
    option = esc(data["option"])
    stops = site.config["rank_scale"]["stops"]
    total = data["questions"]
    digits = site.config["percent_digits"]
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    label = lambda model: site.row_name(run_of(model))  # noqa: E731
    href = lambda model: rel(PATH, site.model_path(run_of(model)))  # noqa: E731
    models = ranked(data["models"])
    rated = [model for model in models if model["non_hallucination"] is not None]

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    rates = [model["non_hallucination"] for model in rated]
    worst, best = min(rates), max(rates)
    first = card(
        "chart-non-hallucination", "Non-hallucination rate",
        f"“{option}” among the answers that were not right · higher is better",
        [{"label": label(model), "href": href(model), "text": pct(model["non_hallucination"], digits),
          "bars": [{"value": model["non_hallucination"], "colour": rank_fill(stops, model["non_hallucination"], worst, best)}],
          "title": f"{label(model)}: {model['dont_know']:,} “{data['option']}” of {model['dont_know'] + model['wrong']:,} not right"}
         for model in rated],
        scale_legend(stops, pct(worst, digits), pct(best, digits))
        + f" <span>Read it with accuracy, below: a model that always chose “{option}” would rank first with no right answers.</span>")
    second = card(
        "chart-confidence", "Saying “I don't know”, or held back by confidence",
        f"Each model's non-hallucination rate with “{option}”, and its five-option run held back by its own confidence at "
        "about the same attempt rate · higher is better",
        [{"label": label(model), "href": href(model),
          "text": f"{pct(model['non_hallucination'], digits)} · {pct(model['derived']['non_hallucination'], digits)}",
          "bars": [{"value": model["non_hallucination"], "kind": "lead"}, {"value": model["derived"]["non_hallucination"], "kind": "base"}],
          "title": f"{label(model)}: {pct(model['non_hallucination'], digits)} with “{data['option']}”, "
                   f"{pct(model['derived']['non_hallucination'], digits)} held back by confidence"}
         for model in rated if model["derived"]["non_hallucination"] is not None],
        f'<span><i class="swatch swatch-lead"></i>With “{option}”</span> '
        '<span><i class="swatch swatch-base"></i>Held back by its own confidence (the derived rate)</span>')
    # The paired test (vs_confidence): for each model in Holm's family, the wrong answers only one side made, most
    # significant first, with its Holm-adjusted p; the models outside the family are named under it.
    tested = sorted((model for model in models if model["vs_confidence"]["p_holm"] is not None),
                    key=lambda model: (model["vs_confidence"]["p_holm"], model["vs_confidence"]["p"], model["name"].casefold()))
    untested = [label(model) for model in models if model["vs_confidence"]["p_holm"] is None]
    share = f"{100 * data['vs_confidence_share']:g}%"
    paired = ""
    if tested:
        most = max(max(model["vs_confidence"]["option_only_wrong"], model["vs_confidence"]["confidence_only_wrong"]) for model in tested)
        # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
        quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
        counts = lambda model: (model["vs_confidence"]["option_only_wrong"], model["vs_confidence"]["confidence_only_wrong"])  # noqa: E731
        significant = [model for model in tested if model["vs_confidence"]["p_holm"] < 0.05]
        others = [model for model in tested if model["vs_confidence"]["p_holm"] >= 0.05]

        def adjusted(group: list[dict[str, Any]]) -> str:
            """The group's Holm-adjusted p values as the site writes p ("each" when they read the same)."""
            texts = [bp.p_text(model["vs_confidence"]["p_holm"]) for model in group]
            return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

        # Each row's text is its two counts (the value column fits about 14 characters); the p values are in the legend
        # and in each row's tooltip.
        verdict = ((f"* A significant difference (Holm-adjusted p below 0.05): {esc(joined([label(model) for model in significant]))} "
                    f"({adjusted(significant)}).") if significant else "No difference is significant (Holm-adjusted p below 0.05).")
        if others:
            verdict += f" The other {len(others)}: {adjusted(others)}." if significant else f" Adjusted: {adjusted(others)}."
        paired = card(
            "chart-paired", f"Fewer wrong answers: “{data['option']}” or confidence?",
            f"Each model's first run with “{option}” against its five-option run held back by its own confidence on as many "
            f"questions: the questions only one of the two got wrong, by the exact McNemar test with p adjusted by Holm's method "
            f"over the {len(tested)} models that chose “{option}” on at least {share} of the questions · the shorter bar left "
            "fewer wrong answers",
            [{"label": label(model), "href": href(model),
              "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if model['vs_confidence']['p_holm'] < 0.05 else ''}",
              "bars": [{"value": counts(model)[0], "kind": "lead"}, {"value": counts(model)[1], "kind": "base"}],
              "title": f"{label(model)}: {counts(model)[0]:,} wrong only with “{data['option']}”, {counts(model)[1]:,} wrong only "
                       f"when held back by its own confidence; exact McNemar {bp.p_text(model['vs_confidence']['p'])}, "
                       f"Holm-adjusted {bp.p_text(model['vs_confidence']['p_holm'])}"}
             for model in tested],
            f'<span><i class="swatch swatch-lead"></i>Wrong only with “{option}”</span> '
            '<span><i class="swatch swatch-base"></i>Wrong only when held back by its own confidence</span> '
            f"<span>{verdict}"
            + (f" Not in the test, as they chose “{option}” on fewer than {share} of the questions: {esc(joined(untested))}." if untested else "")
            + "</span>",
            top=4 * quarter, tick=lambda value: f"{value:,.0f}")
    by_accuracy = sorted(models, key=lambda model: (-model["accuracy"], model["name"].casefold()))
    accuracies = [model["accuracy"] for model in by_accuracy]
    third = card(
        "chart-accuracy", f"Accuracy with “{data['option']}”",
        f"Share of the {total:,} questions answered right with “{option}” on offer · higher is better",
        [{"label": label(model), "href": href(model), "text": pct(model["accuracy"], digits),
          "bars": [{"value": model["accuracy"], "colour": rank_fill(stops, model["accuracy"], min(accuracies), max(accuracies))}],
          "marker": model["original_accuracy"],
          "title": f"{label(model)}: {model['right']:,} of {total:,} right; {pct(model['original_accuracy'], digits)} with five options"}
         for model in by_accuracy],
        scale_legend(stops, pct(min(accuracies), digits), pct(max(accuracies), digits))
        + ' <span><i class="swatch swatch-marker"></i>The same model with five options (the Text tab)</span>')
    return f'<section class="charts" aria-label="Charts">{first}{second}{paired}{third}</section>'


def check_option_word(site: Site, data: dict[str, Any], word: dict[str, Any]) -> None:
    """Stop the build when results.json's dont_know_option_word does not fit the tab: the same questions and models, each
    side's counts adding to the questions, the “Bilmiyorum” side equal to the table's first run and the paired counts
    consistent with the two sides' wrong answers."""
    total = data["questions"]
    fail = lambda text: SystemExit(f"results.json dont_know_option_word: {text}")  # noqa: E731
    if word["questions"] != total:
        raise fail(f"{word['questions']} questions, the tab {total}")
    named = [model["name"] for model in word["models"]] + [item["name"] for item in word["not_run"]]
    if sorted(named) != sorted(model["name"] for model in data["models"]) or len(set(named)) != len(named):
        raise fail("the models and not_run are not the tab's models")
    ran = {model["name"] for model in word["models"]}
    if [model["name"] for model in word["models"]] != [model["name"] for model in data["models"] if model["name"] in ran]:
        raise fail("the models are not in the tab's order")
    first = {model["name"]: model for model in data["models"]}
    for model in word["models"]:
        for side in ("bilmiyorum", "i_dont_know"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["dont_know"] + counts["invalid"] != total:
                raise fail(f"{model['name']} {side}: the counts do not add to {total:,}")
        own = first[model["name"]]
        if model["bilmiyorum"]["run"] != own["run"] or any(model["bilmiyorum"][key] != own[key] for key in (
                "right", "wrong", "dont_know", "invalid", "non_hallucination", "mean_dont_know_probability")):
            raise fail(f"{model['name']}: the “Bilmiyorum” side is not the table's first run")
        paired, b, e = model["paired"], model["bilmiyorum"], model["i_dont_know"]
        if (paired["bilmiyorum_only_wrong"] - paired["i_dont_know_only_wrong"] != b["wrong"] - e["wrong"]
                or paired["bilmiyorum_only_wrong"] > b["wrong"] or paired["i_dont_know_only_wrong"] > e["wrong"]
                or min(paired["bilmiyorum_only_wrong"], paired["i_dont_know_only_wrong"]) < 0):
            raise fail(f"{model['name']}: the paired counts do not fit the wrong answers")


def option_word_rows(site: Site, data: dict[str, Any], word: dict[str, Any]) -> list[dict[str, Any]]:
    """The option-word models with the tab's original run, in the tab's ranking order."""
    order = {model["name"]: index for index, model in enumerate(ranked(data["models"]))}
    first = {model["name"]: model for model in data["models"]}
    return [dict(model, original_run=first[model["name"]]["original_run"])
            for model in sorted(word["models"], key=lambda model: order[model["name"]])]


def option_word_summary(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """The option-word section's summary, every number from results.json's dont_know_option_word."""
    digits = site.config["percent_digits"]
    models = option_word_rows(site, data, word)
    name = lambda model: esc(model["name"])  # noqa: E731
    old, new = esc(data["option"]), esc(word["option"])
    more = [model for model in models if model["i_dont_know"]["dont_know"] > model["bilmiyorum"]["dont_know"]]
    fewer = [model for model in models if model["i_dont_know"]["dont_know"] < model["bilmiyorum"]["dont_know"]]
    rated = [model for model in models
             if model["i_dont_know"]["non_hallucination"] is not None and model["bilmiyorum"]["non_hallucination"] is not None]
    moves = [100 * (model["i_dont_know"]["non_hallucination"] - model["bilmiyorum"]["non_hallucination"]) for model in rated]
    text = (f"<p>With “{new}” in place of “{old}”, {len(more)} of the {len(models)} models chose the option more often"
            + (f" and {len(fewer)} less often" if fewer else "")
            + (f"; {len(models) - len(more) - len(fewer)} as often" if len(models) > len(more) + len(fewer) else "") + ".")
    if moves:
        text += (f" Their non-hallucination rates moved by {min(moves):+.{digits}f} to {max(moves):+.{digits}f} points"
                 + (f" ({len(models) - len(rated)} without a rate on one side)" if len(rated) < len(models) else "") + ".")
    family = [model for model in models if model["paired"]["p_holm"] is not None]
    significant = [model for model in family if model["paired"]["p_holm"] < 0.05]
    fewer_wrong = [model for model in significant if model["paired"]["bilmiyorum_only_wrong"] > model["paired"]["i_dont_know_only_wrong"]]
    more_wrong = [model for model in significant if model not in fewer_wrong]
    if family:
        text += f" In the exact McNemar test of wrong answers, with Holm's correction over the {len(family)}, "
        if not significant:
            text += "no difference is significant: each could be chance."
        else:
            parts = []
            if fewer_wrong:
                parts.append(f"“{new}” left significantly fewer wrong answers for {joined([name(model) for model in fewer_wrong])}")
            if more_wrong:
                parts.append(f"“{old}” left significantly fewer for {joined([name(model) for model in more_wrong])}")
            rest = len(family) - len(significant)
            text += "; ".join(parts) + ((f"; for the other {rest}" if rest > 1 else "; for the other model") +
                                        ", the difference could be chance." if rest else ".")
    if word["not_run"]:
        text += f" Not run: {joined([esc(item['name']) for item in word['not_run']])} (<a href=\"#option-word-results\">why</a>)."
    return text + "</p>"


def option_word_face(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """The option-word section on the tab's face: its summary and a chart of each model's non-hallucination rate with
    the Turkish and the English word."""
    digits = site.config["percent_digits"]
    old, new = esc(data["option"]), esc(word["option"])
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    label = lambda model: site.row_name(run_of(model))  # noqa: E731
    rows = [model for model in option_word_rows(site, data, word)
            if model["i_dont_know"]["non_hallucination"] is not None and model["bilmiyorum"]["non_hallucination"] is not None]
    side = lambda model, key: model[key]  # noqa: E731
    chart = hbars([
        {"label": label(model), "href": rel(PATH, site.model_path(run_of(model))),
         "text": f"{pct(model['i_dont_know']['non_hallucination'], digits)} · {pct(model['bilmiyorum']['non_hallucination'], digits)}",
         "bars": [{"value": model["i_dont_know"]["non_hallucination"], "kind": "lead"},
                  {"value": model["bilmiyorum"]["non_hallucination"], "kind": "base"}],
         "title": f"{label(model)}: {side(model, 'i_dont_know')['dont_know']:,} “{word['option']}” of "
                  f"{side(model, 'i_dont_know')['dont_know'] + side(model, 'i_dont_know')['wrong']:,} not right; "
                  f"{side(model, 'bilmiyorum')['dont_know']:,} “{data['option']}” of "
                  f"{side(model, 'bilmiyorum')['dont_know'] + side(model, 'bilmiyorum')['wrong']:,} not right"}
        for model in rows])
    return (f'<section class="card" id="option-word"><h2>The option\'s word: “{new}” instead of “{old}”</h2>'
            f"{option_word_summary(site, data, word)}"
            f'<p class="note">The same {word["questions"]:,} Turkish questions, with only the sixth option\'s word and the sentence '
            f"that names it changed. A model that skipped “{old}” because it did not recognise the Turkish word should choose "
            f"“{new}” more often. The languages each model's card or docs list are on the Turkish vs English tab "
            f"(<a href=\"{rel(PATH, 'turkish-vs-english/')}#languages\">Languages the model cards list</a>). Table and method: "
            '<a href="#option-word-results">under Info</a>.</p>'
            f'<figure class="panel chart-card" id="chart-option-word"><div class="chart-head"><h2>Non-hallucination rate by the option\'s word</h2>'
            f'<p class="chart-sub">Each model\'s first run with “{new}” and with “{old}” · higher is better</p></div>{chart}'
            f'<p class="chart-legend"><span><i class="swatch swatch-lead"></i>With “{new}”</span> '
            f'<span><i class="swatch swatch-base"></i>With “{old}” (the table above)</span> '
            f"<span>Read it with accuracy and the attempt rate, in the table under Info.</span></p></figure></section>")


def option_word_info(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """Under Info: the option-word table and its method notes."""
    digits = site.config["percent_digits"]
    total = word["questions"]
    old, new = esc(data["option"]), esc(word["option"])
    percent = lambda value: '<span class="nm">Not measured</span>' if value is None else pct(value, digits)  # noqa: E731
    sides = (("i_dont_know", new), ("bilmiyorum", old))
    heads = tuple((f"{head} with “{text}”", direction) for head, direction in (
        ("Non-hallucination rate", "higher is better"), ("Accuracy", "higher is better"),
        ("Attempt rate", f"higher means it answers more often; {NEUTRAL}")) for text in (word["option"], data["option"])) + (
        ("Wrong only with one word", "exact McNemar, Holm-adjusted"), ("Runs", "run, start date and prompt version"))
    labels = [f"{head} ({direction})" for head, direction in heads]
    smalls = (
        ("non_hallucination", lambda counts, option: f"{counts['dont_know']:,} “{option}” of {counts['dont_know'] + counts['wrong']:,} not right"),
        ("accuracy", lambda counts, option: f"{counts['right']:,} of {total:,} right"),
        ("attempt_rate", lambda counts, option: f"{counts['right'] + counts['wrong']:,} answered, {counts['dont_know']:,} “{option}”"
         + (f", {counts['invalid']:,} invalid" if counts["invalid"] else "")),
    )

    rows = []
    for model in option_word_rows(site, data, word):
        paired = model["paired"]
        test = (f'{paired["i_dont_know_only_wrong"]:,} · {paired["bilmiyorum_only_wrong"]:,}'
                f'<span class="small">{paired["i_dont_know_only_wrong"]:,} wrong only with “{new}”, '
                f'{paired["bilmiyorum_only_wrong"]:,} only with “{old}”</span><span class="small">{esc(bp.p_text(paired["p"]))}'
                + (f", Holm-adjusted {esc(bp.p_text(paired['p_holm']))}{' *' if paired['p_holm'] < 0.05 else ''}" if paired["p_holm"] is not None else ", not in Holm's family")
                + "</span>")
        runs = (f'{model["i_dont_know"]["run"]} · {model["bilmiyorum"]["run"]}'
                + "".join(f'<span class="small">“{text}”: run {model[side]["run"]}, {esc(model[side]["date"])}, '
                          f'prompt version {esc(model[side]["prompt_version"])}</span>' for side, text in sides))
        values = [f'{percent(model[side][key])}<span class="small">{small(model[side], text)}</span>'
                  for key, small in smalls for side, text in sides] + [test, runs]
        rows.append(f"<tr>{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>' for name, direction in heads)
    return f"""
    <section class="card" id="option-word-results">
      <h2>Results with “{new}” instead of “{old}”</h2>
      <p class="note">In the tab's order. Each row shows the model's first run with each word on the same {total:,} questions; the “{old}” run is the one in the table above. Wrong only with one word: the questions only one of the two runs got wrong, by the exact McNemar test, with p adjusted by Holm's method over the models compared; * marks a Holm-adjusted p below 0.05.</p>
      <div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
      {not_run(word["not_run"])}
    </section>
    <section class="card method-notes" id="option-word-method">
      <h2>Our method with “{new}”</h2>
      <p>Only two things changed from the runs above: the sixth option's word and the sentence of the System One instructions that names it. The option “{old}” became “{new}”, and the sentence “{esc(data["sentence"])}” became “{esc(word["sentence"])}” Everything else is as above: the same {total:,} Turkish questions and answer key, the option always last and never correct, one question per request and each model's own settings. The full instructions:</p>
      <blockquote><p>{esc(word["instructions"])}</p></blockquote>
      <p>Prompt version {esc(word["prompt_version"])} with “{new}”, against {esc(data["prompt_version"])} with “{old}”. One full run per model with “{new}”; the table gives each run's ID and start date (UTC).</p>
      <h3>How to read the comparison</h3>
      <p>A model that did not recognise the Turkish word and so ignored the option should choose the English one more often, and its non-hallucination rate should rise. A model that chooses both about as often did not skip “{old}” for its word. The rates are those above, and the same limits hold: the non-hallucination rate says how a model is wrong, not how often it is right, and it is not a direct measure of what the model does not know; read it with accuracy and the attempt rate, as a model that always chose the option would reach 100% with no right answers. With neither a wrong answer nor the option, the rate is undefined (Not measured).</p>
    </section>"""


def check_rerun(site: Site, data: dict[str, Any], rerun: dict[str, Any]) -> dict[str, Any]:
    """Stop the build when results.json's hosted_glide_rerun does not fit the tab; return the tab's hosted GLiDE row."""
    total = data["questions"]
    fail = lambda text: SystemExit(f"results.json hosted_glide_rerun: {text}")  # noqa: E731
    rows = [model for model in data["models"] if model["run"] == rerun["dont_know_run"]]
    if len(rows) != 1 or rows[0]["original_run"] != rerun["replaces_run"]:
        raise fail("its “I don't know” run or the run it replaces is not a row of the tab")
    model, derived = rows[0], rerun["derived"]
    if rerun["right"] + rerun["wrong"] + rerun["invalid"] != total:
        raise fail(f"the counts do not add to {total:,}")
    if derived["right"] + derived["wrong"] + derived["abstained"] != total or derived["abstained"] != model["dont_know"]:
        raise fail("the derived counts do not add up or do not hold back on as many questions as the “I don't know” run")
    paired = rerun["vs_confidence"]
    if (paired["option_only_wrong"] - paired["confidence_only_wrong"] != model["wrong"] - derived["wrong"]
            or paired["option_only_wrong"] > model["wrong"] or paired["confidence_only_wrong"] > derived["wrong"]):
        raise fail("the paired counts do not fit the wrong answers")
    return model


def rerun_face(site: Site, data: dict[str, Any], rerun: dict[str, Any], model: dict[str, Any]) -> str:
    """The hosted GLiDE rerun on the tab's face: why, its summary and a chart of the non-hallucination rate with the option,
    held back by confidence on run 129 (as published) and on the new run."""
    digits = site.config["percent_digits"]
    option = esc(data["option"])
    old = site.by_id[rerun["replaces_run"]]
    name = esc(site.row_name(old))
    new_derived, old_derived = rerun["derived"], model["derived"]
    paired = rerun["vs_confidence"]
    old_accuracy = model["original_accuracy"]
    summary = (f"<p>Fastino changed its hosted model after 6 October, so run {old['run']} ({esc(old['started'][:10])}), the "
               f"five-option run behind {name}'s row in the table, is a different model from the one behind its “{option}” run "
               f"{model['run']}. A new five-option run, {rerun['run']} ({esc(rerun['date'])}), scored {pct(rerun['accuracy'], digits)} "
               f"({rerun['right']:,} of {data['questions']:,} right), against {pct(old_accuracy, digits)} for run {old['run']}. Held back "
               f"by its own confidence on as many questions as run {model['run']} said “{option}” ({new_derived['abstained']:,}), "
               f"the new run left {new_derived['wrong']:,} wrong answers, against {model['wrong']:,} with “{option}”: a derived "
               f"non-hallucination rate of {pct(new_derived['non_hallucination'], digits)}, against {pct(model['non_hallucination'], digits)} "
               f"with the option and {pct(old_derived['non_hallucination'], digits)} from run {old['run']} (exact McNemar test of "
               f"the wrong answers, {esc(bp.p_text(paired['p']))}, not adjusted). The row in the table under Info is left as "
               f"published, against run {old['run']}.</p>")
    rows = [
        (f"With “{data['option']}”, run {model['run']}", model["non_hallucination"], "lead"),
        (f"Confidence, new run {rerun['run']}", new_derived["non_hallucination"], "base"),
        (f"Confidence, run {old['run']} (as published)", old_derived["non_hallucination"], "base"),
    ]
    chart = hbars([{"label": label, "text": pct(value, digits), "bars": [{"value": value, "kind": kind}],
                    "title": f"{site.row_name(old)}: {label}, {pct(value, digits)}"} for label, value, kind in rows if value is not None])
    return (f'<section class="card" id="hosted-glide-rerun"><h2>Hosted GLiDE against a new five-option run</h2>{summary}'
            f'<figure class="panel chart-card" id="chart-glide-rerun"><div class="chart-head"><h2>{name}: saying “I don\'t know”, or held back by confidence</h2>'
            f'<p class="chart-sub">Non-hallucination rate with “{option}”, and with each five-option run held back by its own '
            f"confidence at about the same attempt rate · higher is better</p></div>{chart}"
            f'<p class="chart-legend"><span><i class="swatch swatch-lead"></i>With “{option}”</span> '
            '<span><i class="swatch swatch-base"></i>Held back by its own confidence (the derived rate)</span> '
            '<span>Table and method: <a href="#hosted-glide-rerun-results">under Info</a>.</span></p></figure></section>')


def rerun_info(site: Site, data: dict[str, Any], rerun: dict[str, Any], model: dict[str, Any]) -> str:
    """Under Info: the hosted GLiDE rerun's table (run 129 as published, then the new run) and its method notes."""
    digits = site.config["percent_digits"]
    total = data["questions"]
    option = esc(data["option"])
    old = site.by_id[rerun["replaces_run"]]
    heads = (("Five-option run", "run, date and prompt version"), ("Text accuracy with five options", "higher is better"),
             ("Derived non-hallucination rate", "higher is better"), ("Wrong only on one side", "exact McNemar"))
    labels = [f"{head} ({direction})" for head, direction in heads]

    def derived_text(derived: dict[str, Any]) -> str:
        cut = ("no cut-off (no answer has a score)" if derived["cut_off"] is None else
               f"cut-off {derived['cut_off']:.4f}: {derived['right']:,} right + {derived['wrong']:,} wrong answered, "
               f"{derived['abstained']:,} held back")
        return f'{pct(derived["non_hallucination"], digits)}<span class="small">{cut}, attempt rate {pct(derived["attempt_rate"], digits)}</span>'

    def test_text(paired: dict[str, Any], holm: bool) -> str:
        return (f'{paired["option_only_wrong"]:,} with “{option}”, {paired["confidence_only_wrong"]:,} by confidence'
                f'<span class="small">{esc(bp.p_text(paired["p"]))}'
                + (f", Holm-adjusted {esc(bp.p_text(paired['p_holm']))}" if holm and paired.get("p_holm") is not None else ", not adjusted")
                + "</span>")

    entries = [
        (f'<a href="{rel(PATH, site.model_path(old))}">run {old["run"]}</a><span class="small">{esc(old["started"][:10])}, as published</span>',
         f'{pct(model["original_accuracy"], digits)}<span class="small">{old["correct"]:,} of {total:,} right</span>',
         derived_text(model["derived"]), test_text(model["vs_confidence"], True)),
        (f'run {rerun["run"]}<span class="small">{esc(rerun["date"])}, prompt version {esc(rerun["prompt_version"])}</span>',
         f'{pct(rerun["accuracy"], digits)}<span class="small">{rerun["right"]:,} of {total:,} right'
         + (f", {rerun['invalid']:,} invalid" if rerun["invalid"] else "") + "</span>",
         derived_text(rerun["derived"]), test_text(rerun["vs_confidence"], False)),
    ]
    rows = "".join("<tr>" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>" for values in entries)
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>' for name, direction in heads)
    return f"""
    <section class="card" id="hosted-glide-rerun-results">
      <h2>Hosted GLiDE: the comparison redone with run {rerun["run"]}</h2>
      <p class="note">Both against {esc(site.row_name(old))}'s first run with “{option}”, run {model["run"]}. Run {old["run"]} is the Text tab's run and the row in the table above; run {rerun["run"]} is new and replaces it here only.</p>
      <div class="table-wrap"><table class="board list stack idk"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>
    </section>
    <section class="card method-notes" id="hosted-glide-rerun-method">
      <h2>Our method for the hosted GLiDE rerun</h2>
      <p>Fastino changed the hosted model behind <code>{esc(old["model"])}</code> after 6 October. Run {old["run"]} was made on {esc(bp.long_date(old["started"]))}, so it is a different model from the one that answered with “{option}” (run {model["run"]}), and the derived rate in the table above compares two models. Run {rerun["run"]} is a new five-option run of the same hosted model, started {esc(bp.long_date(rerun["date"]))}, made as on the Text tab: the same {total:,} questions, one question per request, the main prompt version {esc(rerun["prompt_version"])}. Its derived non-hallucination rate and paired test are computed as above, from run {rerun["run"]} instead of run {old["run"]}; the p value is not adjusted, as it is one test.</p>
      <p>The row in the table above is left as published, against run {old["run"]}, and run {rerun["run"]} is kept out of the Text tab: its leaderboard, repeats and every other list.</p>
    </section>"""



def english_option_face(site: Site, idk: dict[str, Any]) -> str:
    """The English-option comparison on this tab's face: the Turkish vs English tab's kept reading questions in English
    with “I don't know” against the same models' “Bilmiyorum” answers in Turkish, its summary and its two charts as that
    tab draws them (sitebuild/english_reading.py), every number from results.json's english_reading.dont_know."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    option, total = esc(idk["option"]), idk["questions"]
    return (f'<section class="card" id="english-option"><h2>The English questions: “{option}” in English against “Bilmiyorum” '
            f"in Turkish</h2><p>The {total:,} reading questions of the "
            f'<a href="{rel(PATH, "turkish-vs-english/")}">Turkish vs English tab</a>, in English with a sixth option, '
            f"“{option}”, against the same models' “Bilmiyorum” answers on the same questions in Turkish (this tab's runs "
            "counted on those questions, or runs on those questions only). Counts and the paired test: "
            '<a href="#english-option-results">under Info</a>; how the questions were translated and kept: '
            f'<a href="{rel(PATH, "turkish-vs-english/")}#method">Turkish vs English, Our method</a>.</p>'
            f"{er.dont_know_summary(site, idk)}</section>{er.dont_know_charts(site, idk)}")


def english_option_info(site: Site, idk: dict[str, Any]) -> str:
    """Under Info: the English-option comparison's table, as the Turkish vs English tab shows it."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    option = esc(idk["option"])
    return f"""
    <section class="card" id="english-option-results">
      <h2>Results on the English questions with “{option}”</h2>
      <p class="note">Each model's first run in English with “{option}” and in Turkish with “Bilmiyorum”, on the {idk["questions"]:,} kept reading questions: the counts, the rates and the exact McNemar test of wrong answers, with p adjusted by Holm's method over the {len(idk["models"])} models; * marks a Holm-adjusted p below 0.05. The same table is on the <a href="{rel(PATH, "turkish-vs-english/")}#dont-know">Turkish vs English tab</a>.</p>
      {er.dont_know_table(site, idk)}
    </section>"""


def build(site: Site) -> dict[str, str]:
    data = site.results["dont_know"]
    total = f"{data['questions']:,}"
    option = esc(data["option"])
    not_decision = [model["name"] for model in data["models"] if not site.decision(site.by_id[model["original_run"]])]
    if not_decision:
        raise SystemExit(f"results.json dont_know: not decision models on the Text tab: {', '.join(not_decision)}")
    if data["questions"] != site.total:
        raise SystemExit(f"results.json dont_know: {data['questions']} questions, the Text tab {site.total}")
    several = [model["name"] for model in data["models"] if len(model["runs"]) > 1]
    word, rerun = site.results.get("dont_know_option_word"), site.results.get("hosted_glide_rerun")
    english = (site.results.get("english_reading") or {}).get("dont_know")
    if word:
        check_option_word(site, data, word)
    glide = check_rerun(site, data, rerun) if rerun else None
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">Hallucination</p>
      <h1>The Text tab's {total} questions, with “{option}” as a sixth option</h1>
      <p>A wrong answer counts as a hallucination: the model could have chosen “{option}” (“{esc(data["option_en"])}”) instead. This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its numbers.</p>
      {headline(data)}
      <nav class="face-nav" aria-label="On this page"><a href="#chart-non-hallucination">Non-hallucination</a><a href="#chart-confidence">Against confidence</a><a href="#chart-paired">Paired test</a><a href="#chart-accuracy">Accuracy</a>{'<a href="#english-option">English questions</a>' if english else ""}{'<a href="#option-word">The option&#x27;s word</a>' if word else ""}{'<a href="#hosted-glide-rerun">Hosted GLiDE rerun</a>' if rerun else ""}<a href="#info">Info</a></nav>
    </section>
    {face(site, data)}{english_option_face(site, english) if english else ""}{option_word_face(site, data, word) if word else ""}{rerun_face(site, data, rerun, glide) if rerun else ""}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The table, what we found and our method</span></summary>
    <section class="card">
      <h2>About this test</h2>
      <p>Every question of the Text tab gets one more option after its five answers: F, “{option}”, Turkish for “{esc(data["option_en"])}”. It is always the last option, it is never shuffled and it is never correct. The System One instructions get one added sentence: “{esc(data["sentence"])}” Everything else is as on the Text tab: the same {total} scored questions and answer key, one question per request, and each model's own settings from its text run.</p>
      <p>The models: {esc(SELECTION)}. Each has one full run; a model whose repeated text runs changed answers gets five.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page, under <code>dont_know</code>) and <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each run's answers, under <code>dont_know_runs</code>).</p>
    </section>
    <section class="card" id="results">
      <h2>Results</h2>
      <p class="note">Ranked by non-hallucination rate, highest first: the share of “{option}” among the answers that were not right (“{option}” plus wrong), so the first model is the one that most often said it did not know instead of answering wrongly. Read the ranking with accuracy and the attempt rate: a model that always chose “{option}” would rank first with no right answers. Each row shows the model's first run{"; under Runs, a model with more than one run (" + esc(joined(several)) + ") shows the range over its runs and how many answers changed between them" if several else ""}. Out of all {total} questions: accuracy counts the right answers; the attempt rate counts the right and wrong answers. Formulas and how to read them: <a href="#method">Our method</a>.</p>
      {table(site, data)}
      {not_run(site.config["dont_know"]["not_run"])}
    </section>
    <section class="card" id="findings">
      <h2>What we found</h2>
      {findings(site, data)}
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>We measure hallucination by offering a way out. Every question gets “{option}” (“{esc(data["option_en"])}”) as a sixth option, and the instructions tell the model to choose it when it does not know the answer. A hallucination is then a wrong answer: the model chose one of the question's own options, not the key, when it could have said it did not know. Everything else is the Text tab's: the questions, the answer key and each model's settings.</p>
      <h3>How it differs from our confidence method</h3>
      <p>On the Text tab a model must pick one of the five options, and we judge each answer by its confidence: the probability the model gives the option it picked (its <a href="{rel(PATH, "method/")}#confidence-sources">option score</a>). Our confidence method keeps an answer when that probability reaches a cut-off, and a stronger model answers the rest (<a href="{rel(PATH, "method/")}#routing">How we chose which answers to keep</a>). Here no cut-off decides: the model can say itself that it does not know, by choosing “{option}”, and the rates count those choices. The two meet in the derived non-hallucination rate, which applies the confidence method to the same model's five-option run at about the same attempt rate; side by side, the two non-hallucination columns compare a model that says it does not know with the same model held back by its own confidence.</p>
      <h3>The rates</h3>
      <p>Each answer is right, wrong, “{option}” or invalid; an invalid answer counts as none of the others. Out of all {total} questions:</p>
      <ul>
        <li><strong>Accuracy</strong> = right / {total}.</li>
        <li><strong>Attempt rate</strong> = (right + wrong) / {total}: how often the model chose one of the question's own options.</li>
        <li><strong>Non-hallucination rate</strong> = “{option}” / (“{option}” + wrong): among the answers that were wrong or “{option}”, the share where the model said it did not know. The hallucination rate is its complement, wrong / (“{option}” + wrong).</li>
        <li><strong>Mean probability of “{option}”</strong>: the probability the model gave that option, averaged over its answers that report option probabilities.</li>
      </ul>
      <h3>How to read them</h3>
      <p>The non-hallucination rate says how a model is wrong, not how often it is right, and it is not a direct measure of what the model does not know. Read it with accuracy and the attempt rate: a model that always chose “{option}” would reach 100% with no right answers, and one that never chose it would reach 0% as soon as it answered one question wrongly. With neither a wrong answer nor “{option}”, there is nothing to divide by and the rate is undefined (the table shows Not measured).</p>
      <h3>The option and the instructions</h3>
      <p>The added option's exact text is “{option}”. It is lettered after the question's own options, and the answer key is unchanged. The full System One instructions:</p>
      <blockquote><p>{esc(data["instructions"])}</p></blockquote>
      <p>Prompt version {esc(data["prompt_version"])} (a hash of the prompts with these instructions and this option, computed as for the Text tab's prompt version).</p>
      <h3>Derived non-hallucination rate</h3>
      <p>For comparison, each model's run with five options (its run on the Text tab, on the same questions) is made to abstain by its own confidence: it answers only where its score reaches a cut-off and abstains on the rest. The cut-off is the one whose attempt rate comes nearest the attempt rate of the run with “{option}”; on a tie, the higher cut-off. An answer without a score never counts as an attempt. The derived non-hallucination rate is then the abstentions over the abstentions plus the wrong answers. The table shows the cut-off and the attempt rate it reached.</p>
      <h3>Repeats</h3>
      <p>One full run per model. A model whose repeated text runs changed answers gets five runs with the option. Those runs form a repeat set of their own and are never mixed with the Text tab's runs. The table shows the first run; the range covers all of them, and the changed answers are the scored questions whose answer differs between the runs.</p>
    </section>{english_option_info(site, english) if english else ""}{option_word_info(site, data, word) if word else ""}{rerun_info(site, data, rerun, glide) if rerun else ""}
    </details>"""
    return {PATH: site.page(PATH, "Hallucination",
                            f"The Text tab's {total} questions with a sixth option, “{data['option']}” (I don't know): accuracy, "
                            "attempt rate and non-hallucination rate of the most accurate decision models.", body)}
