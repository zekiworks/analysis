"""Hallucination (dont-know/), the site's third tab: the Text tab's questions with one more option after each
question's own, "Bilmiyorum" ("I don't know"), from results.json's `dont_know` and page_config.json's `dont_know` (the
models not run, with their reasons). Its face, as the home page's, is charts (face()): the non-hallucination rate, the
same rate with the option and held back by confidence, and accuracy with the option against accuracy with five options,
as HTML bars (Site hbars). Under Info: the table (one row per model, from its first run, Answered and Wrong of answers
first, ranked by non-hallucination rate, accuracy breaking ties; a model with more than one run shows the range over its
runs), What we found and Our method. With results.json's `dont_know_same_answers`, a section compares the models held to
the same number of answers (risk-coverage plots on the face, tables under Info). It needs no JavaScript. The tab ranks
nothing on the Text tab and changes none of its numbers."""

from __future__ import annotations

import json
import math
from typing import Any

import build_page as bp
from sitebuild.site import Site, esc, hbars, legend_mark, line_plot, pct, rank_fill, rel, scale_legend
from sitebuild.vision import cell, joined, run_span

PATH = "dont-know/"
# The models the tab covers, as chosen before the runs (the Text tab at results 25290875).
SELECTION = ("the ten most accurate decision models on the Text tab at results 25290875, plus Base Labs' Elephant-1 and "
             "Mammoth-1 and SubQ Snap 1.1 once their text runs are published")
NEUTRAL = "neither better nor worse on its own"


def columns(option: str) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: header and which direction is better."""
    return (
        ("Answered", "(right + wrong) / questions; higher is better"),
        ("Wrong of answers", "wrong / (right + wrong); lower is better"),
        ("Non-hallucination rate", f"“{option}” / (“{option}” + wrong); higher is better"),
        ("Derived non-hallucination rate", "from the 5-option text run; higher is better"),
        ("Accuracy", "higher is better"),
        (f"Mean probability of “{option}”", f"higher means more probability on “I don't know”; {NEUTRAL}"),
        ("Text accuracy with five options", "the Text tab's number; higher is better"),
        ("Runs", "range over the runs where more than one"),
    )


def answered_cell(counts: dict[str, Any], total: int, digits: int, extra: str = "") -> str:
    """The Answered cell: (right + wrong) / questions, with its counts and anything after them (extra)."""
    answered = counts["right"] + counts["wrong"]
    return f'{pct(answered / total, digits)}<span class="small">{answered:,} of {total:,} answered{extra}</span>'


def wrong_cell(counts: dict[str, Any], digits: int) -> str:
    """The Wrong of answers cell: wrong / (right + wrong) with its counts; Not measured without an answer."""
    answered = counts["right"] + counts["wrong"]
    if not answered:
        return '<span class="nm">Not measured</span>'
    return f'{pct(counts["wrong"] / answered, digits)}<span class="small">{counts["wrong"]:,} of {answered:,}</span>'


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
            for key, name in (("attempt_rate", "Answered"), ("non_hallucination", "Non-hallucination"),
                              ("accuracy", "Accuracy"), ("mean_dont_know_probability", "Mean probability"))
        ]
        changed = model["answers_changed"]
        ranges.append(f"{changed:,} answer{'' if changed == 1 else 's'} changed between runs")
        runs_text = run_span(model["runs"]) + "".join(f'<span class="small">{item}</span>' for item in ranges)
    values = [
        answered_cell(model, total, digits, f', {model["dont_know"]:,} “{esc(option)}”{invalid}'),
        wrong_cell(model, digits),
        f'{percent(model["non_hallucination"])}<span class="small">{model["dont_know"]:,} “{esc(option)}” of '
        f'{model["dont_know"] + model["wrong"]:,} not right</span>',
        f'{percent(derived["non_hallucination"])}<span class="small">{cut}, attempt rate {percent(derived["attempt_rate"])}</span>',
        f'{percent(model["accuracy"])}<span class="small">{model["right"]:,} of {total:,} right</span>',
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


def findings(site: Site, data: dict[str, Any], word: dict[str, Any] | None = None) -> str:
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
    fourth = ""
    if word and word.get("vs_confidence"):
        # check_vs_confidence has already stopped the build unless Holm's family is this comparison's family.
        fourth = f"<p>{vs_confidence_text(site, data, word, False)}</p>"
    return first + second + third + "</p>" + fourth


def headline(data: dict[str, Any], word: dict[str, Any] | None = None) -> str:
    """One line at the top of the tab, from vs_confidence (and, when results.json has it, dont_know_option_word's
    vs_confidence, the same comparison with “I don't know”): the models whose own confidence, holding back on about as
    many questions, left significantly fewer wrong answers than the option (Holm-adjusted p below 0.05); none when there
    are none with either word."""
    def verdicts(family: list[dict[str, Any]], counts: Any) -> tuple[list[str], list[str], int]:
        """The family's names where confidence, then the option, left significantly fewer; how many could be chance."""
        better = [esc(model["name"]) for model in family if model["p_holm"] < 0.05 and counts(model)[0] > counts(model)[1]]
        worse = [esc(model["name"]) for model in family if model["p_holm"] < 0.05 and counts(model)[0] < counts(model)[1]]
        return better, worse, sum(1 for model in family if model["p_holm"] >= 0.05)

    def others(option: str, worse: list[str], rest: int) -> str:
        text = f"; for {joined(worse)}, “{option}” left significantly fewer wrong answers" if worse else ""
        if rest:
            text += ("; for the other model that used it" if rest == 1 else f"; for the other {rest} models that used it") + \
                ", the difference could be chance"
        return text

    def sentence(lead: str, option: str, family: list[dict[str, Any]], strong: bool) -> str:
        """One word's verdict, without its full stop; empty when no difference is significant."""
        better, worse, rest = verdicts(family, lambda model: (model["option_only_wrong"], model["confidence_only_wrong"]))
        if better:
            text = (f"{lead}{joined([name + '’s' for name in better])} own confidence left significantly fewer wrong answers "
                    f"than “{option}” did")
            return (f"<strong>{text}</strong>" if strong else text) + others(option, worse, rest)
        if worse:
            return f"{lead}{others(option, worse, rest).removeprefix('; ')}"
        return ""

    option = esc(data["option"])
    family = [dict(model["vs_confidence"], name=model["name"]) for model in ranked(data["models"])
              if model["vs_confidence"]["p_holm"] is not None]
    texts = [sentence("Holding back on as many questions, ", option, family, True)]
    vs = (word or {}).get("vs_confidence")
    if vs:
        order = {model["name"]: index for index, model in enumerate(ranked(data["models"]))}
        new = esc(word["option"])
        others_family = sorted((model for model in vs["models"] if model["p_holm"] is not None), key=lambda model: order[model["name"]])
        texts.append(sentence(f"With “{new}” in place of “{option}”, ", new, others_family, False))
        if not texts[0] and texts[1]:
            texts[0] = f"With “{option}”, no difference in wrong answers between the option and confidence is significant"
        elif texts[0] and not texts[1]:
            texts[1] = (f"with “{new}” in place of “{option}”, no difference is significant for the {len(others_family)} "
                        "models that used it")
            texts = [f"{texts[0]}; {texts[1]}"]
    if not any(texts):
        return ""
    return f'<p>{". ".join(text for text in texts if text)} (<a href="#findings">What we found</a>).</p>'


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
    words = (word["option"], data["option"])
    heads = (tuple((f"Answered with “{text}”", "(right + wrong) / questions; higher is better") for text in words)
             + tuple((f"Wrong of answers with “{text}”", "wrong / (right + wrong); lower is better") for text in words)
             + tuple((f"Non-hallucination rate with “{text}”", f"“{text}” / (“{text}” + wrong); higher is better") for text in words)
             + tuple((f"Accuracy with “{text}”", "higher is better") for text in words)
             + (("Wrong only with one word", "exact McNemar, Holm-adjusted"), ("Runs", "run, start date and prompt version")))
    labels = [f"{head} ({direction})" for head, direction in heads]
    smalls = (
        ("non_hallucination", lambda counts, option: f"{counts['dont_know']:,} “{option}” of {counts['dont_know'] + counts['wrong']:,} not right"),
        ("accuracy", lambda counts, option: f"{counts['right']:,} of {total:,} right"),
    )
    answered = lambda counts, option: answered_cell(  # noqa: E731
        counts, total, digits, f", {counts['dont_know']:,} “{option}”" + (f", {counts['invalid']:,} invalid" if counts["invalid"] else ""))

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
        values = ([answered(model[side], text) for side, text in sides] + [wrong_cell(model[side], digits) for side, _ in sides]
                  + [f'{percent(model[side][key])}<span class="small">{small(model[side], text)}</span>'
                     for key, small in smalls for side, text in sides] + [test, runs])
        rows.append(f"<tr>{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>' for name, direction in heads)
    return f"""
    <section class="card" id="option-word-results">
      <h2>Results with “{new}” instead of “{old}”</h2>
      <p class="note">In the tab's order. Each row shows the model's first run with each word on the same {total:,} questions; the “{old}” run is the one in the table above. Answered = (right + wrong) / {total:,} and Wrong of answers = wrong / (right + wrong) come first, then the non-hallucination rate (the option / (the option + wrong)) and accuracy, each with “{new}” and with “{old}”. Wrong only with one word: the questions only one of the two runs got wrong, by the exact McNemar test, with p adjusted by Holm's method over the models compared; * marks a Holm-adjusted p below 0.05.</p>
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


def check_vs_confidence(site: Site, data: dict[str, Any], word: dict[str, Any], rerun: dict[str, Any] | None) -> None:
    """Stop the build when results.json's dont_know_option_word.vs_confidence does not fit the tab: one entry per
    option-word model, its option side equal to that model's “I don't know” run, its five-option run the Text tab's run
    (hosted GLiDE's new run in place of the one it replaces), the derived counts adding up, the chosen cut-off between its
    neighbours, the paired counts consistent with the wrong answers and Holm's family the same models as the tab's own
    comparison with confidence."""
    total = word["questions"]
    fail = lambda text: SystemExit(f"results.json dont_know_option_word.vs_confidence: {text}")  # noqa: E731
    vs = word["vs_confidence"]
    own = {model["name"]: model for model in word["models"]}
    first = {model["name"]: model for model in data["models"]}
    if sorted(model["name"] for model in vs["models"]) != sorted(own) or len(vs["models"]) != len(own):
        raise fail("the models are not the option-word models")
    for model in vs["models"]:
        name, option, derived = model["name"], model["option"], model["derived"]
        side, original = own[name]["i_dont_know"], first[name]["original_run"]
        if model["option_run"] != side["run"] or any(option[key] != side[key] for key in ("right", "wrong", "dont_know")) \
                or option["answered"] != option["right"] + option["wrong"]:
            raise fail(f"{name}: the option side is not its run with “{word['option']}”")
        if model["replaces_run"] is None:
            if model["five_option_run"] != original:
                raise fail(f"{name}: the five-option run is not the Text tab's run {original}")
        elif model["replaces_run"] != original or not rerun or rerun["replaces_run"] != original \
                or model["five_option_run"] != rerun["run"]:
            raise fail(f"{name}: the five-option run does not replace the Text tab's run as hosted_glide_rerun does")
        if derived["right"] + derived["wrong"] != derived["answered"] or derived["answered"] + derived["abstained"] > total:
            raise fail(f"{name}: the derived counts do not add up")
        below, above = derived["below"], derived["above"]
        if derived["cut_off"] is not None and (
                (below["cut_off"] is not None and not below["cut_off"] < derived["cut_off"])
                or (above["cut_off"] is not None and not above["cut_off"] > derived["cut_off"])):
            raise fail(f"{name}: the neighbouring cut-offs are not either side of the chosen one")
        if (model["option_only_wrong"] - model["confidence_only_wrong"] != option["wrong"] - derived["wrong"]
                or model["option_only_wrong"] > option["wrong"] or model["confidence_only_wrong"] > derived["wrong"]
                or min(model["option_only_wrong"], model["confidence_only_wrong"]) < 0):
            raise fail(f"{name}: the paired counts do not fit the wrong answers")
    family = sorted(model["name"] for model in vs["models"] if model["p_holm"] is not None)
    if family != sorted(vs["family"]) or family != sorted(model["name"] for model in data["models"]
                                                          if model["vs_confidence"]["p_holm"] is not None):
        raise fail("Holm's family is not the models of the tab's own comparison with confidence")


def vs_confidence_rows(site: Site, data: dict[str, Any], word: dict[str, Any]) -> list[dict[str, Any]]:
    """vs_confidence's models with the tab's original run, in the tab's ranking order."""
    order = {model["name"]: index for index, model in enumerate(ranked(data["models"]))}
    first = {model["name"]: model for model in data["models"]}
    return [dict(model, original_run=first[model["name"]]["original_run"])
            for model in sorted(word["vs_confidence"]["models"], key=lambda model: order[model["name"]])]


def vs_confidence_text(site: Site, data: dict[str, Any], word: dict[str, Any], link: bool) -> str:
    """The option-word runs against confidence in words, every number from vs_confidence: which side left fewer wrong
    answers, how near the cut-offs came to the option runs' answered counts, and the paired test with Holm."""
    digits = site.config["percent_digits"]
    total = word["questions"]
    new, old = esc(word["option"]), esc(data["option"])
    models = vs_confidence_rows(site, data, word)
    name = lambda model: esc(model["name"])  # noqa: E731
    family = [model for model in models if model["p_holm"] is not None]
    share = f"{100 * word['vs_confidence']['share']:g}%"
    fewer = [model for model in family if model["derived"]["wrong"] < model["option"]["wrong"]]
    more = [model for model in family if model["derived"]["wrong"] > model["option"]["wrong"]]
    level = [model for model in family if model["derived"]["wrong"] == model["option"]["wrong"]]
    gaps = [100 * abs(model["derived"]["answered"] - model["option"]["answered"]) / total for model in family]
    reach = (f"at the same attempt rate (each cut-off reached the option run's answered count exactly for the {len(family)} "
             f"that chose “{new}” on at least {share} of the questions)" if not any(gaps) else
             f"at the nearest attempt rate the cut-offs allow (within {max(gaps):.{digits}f} points of the option run for the "
             f"{len(family)} that chose “{new}” on at least {share} of the questions)")
    text = (f"With “{new}” in place of “{old}”, we compared each model's first run with “{new}” against its five-option run "
            f"held back by its own confidence {reach}. ")
    if fewer:
        saved = [model["option"]["wrong"] - model["derived"]["wrong"] for model in fewer]
        text += (f"Confidence left fewer wrong answers for "
                 + (f"all {len(family)}" if len(fewer) == len(family) else f"{len(fewer)} of the {len(family)}")
                 + (f", {min(saved):,} to {max(saved):,} fewer" if len(fewer) > 1 else f", {saved[0]:,} fewer") + ".")
    if more:
        extra = [model["derived"]["wrong"] - model["option"]["wrong"] for model in more]
        text += (f" “{new}” left fewer for {joined([name(model) for model in more])} "
                 f"({joined([f'{value:,}' for value in extra])} fewer).")
    if level:
        text += f" {joined([name(model) for model in level])} left as many either way."
    significant = [model for model in family if model["p_holm"] < 0.05]
    by_confidence = [model for model in significant if model["option_only_wrong"] > model["confidence_only_wrong"]]
    by_option = [model for model in significant if model not in by_confidence]

    def adjusted(group: list[dict[str, Any]]) -> str:
        """The models with their wrong answers each way and Holm-adjusted p, as the site writes p."""
        return joined([f"{name(model)} ({model['option']['wrong']:,} wrong with “{new}”, {model['derived']['wrong']:,} by "
                       f"confidence; adjusted {esc(bp.p_text(model['p_holm']))})" for model in group])

    text += f" In the exact McNemar test of wrong answers, with Holm's correction over the {len(family)}, "
    if not significant:
        text += "none of these differences is significant: each could be chance."
    else:
        parts = []
        if by_confidence:
            parts.append(f"confidence left significantly fewer for {adjusted(by_confidence)}")
        if by_option:
            parts.append(f"“{new}” left significantly fewer for {adjusted(by_option)}")
        rest = len(family) - len(significant)
        text += "; ".join(parts) + ((f"; for the other {rest}" if rest > 1 else "; for the other model")
                                    + ", the difference could be chance." if rest else ".")
    glide = [model for model in models if model["replaces_run"] is not None]
    if glide:
        text += (f" {joined([name(model) for model in glide])} is compared with its new five-option run "
                 f"{joined([str(model['five_option_run']) for model in glide])}, not run "
                 f"{joined([str(model['replaces_run']) for model in glide])}"
                 + (' (<a href="#hosted-glide-rerun">why</a>)' if link else "") + ".")
    return text


def vs_confidence_face(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """The option-word runs against confidence on the tab's face: the summary and a chart of the wrong answers only one
    side made, drawn as the paired test's chart."""
    new, old = esc(word["option"]), esc(data["option"])
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    label = lambda model: site.row_name(run_of(model))  # noqa: E731
    models = vs_confidence_rows(site, data, word)
    tested = sorted((model for model in models if model["p_holm"] is not None),
                    key=lambda model: (model["p_holm"], model["p"], model["name"].casefold()))
    untested = [label(model) for model in models if model["p_holm"] is None]
    share = f"{100 * word['vs_confidence']['share']:g}%"
    most = max(max(model["option_only_wrong"], model["confidence_only_wrong"]) for model in tested)
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    significant = [model for model in tested if model["p_holm"] < 0.05]
    others = [model for model in tested if model["p_holm"] >= 0.05]

    def adjusted(group: list[dict[str, Any]]) -> str:
        texts = [bp.p_text(model["p_holm"]) for model in group]
        return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below 0.05): {esc(joined([label(model) for model in significant]))} "
                f"({adjusted(significant)}).") if significant else "No difference is significant (Holm-adjusted p below 0.05).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if significant else f" Adjusted: {adjusted(others)}."
    chart = hbars(
        [{"label": label(model), "href": rel(PATH, site.model_path(run_of(model))),
          "text": f"{model['option_only_wrong']:,} · {model['confidence_only_wrong']:,}{' *' if model['p_holm'] < 0.05 else ''}",
          "bars": [{"value": model["option_only_wrong"], "kind": "lead"}, {"value": model["confidence_only_wrong"], "kind": "base"}],
          "title": f"{label(model)}: {model['option_only_wrong']:,} wrong only with “{word['option']}” (run {model['option_run']}), "
                   f"{model['confidence_only_wrong']:,} wrong only when run {model['five_option_run']} is held back by its own "
                   f"confidence; exact McNemar {bp.p_text(model['p'])}, Holm-adjusted {bp.p_text(model['p_holm'])}"}
         for model in tested],
        top=4 * quarter, tick=lambda value: f"{value:,.0f}")
    return (f'<section class="card" id="option-word-confidence"><h2>“{new}” against confidence</h2>'
            f"<p>{vs_confidence_text(site, data, word, True)}</p>"
            f'<p class="note">A family of its own: the paired test with “{old}” is the chart '
            f'<a href="#chart-paired">Fewer wrong answers</a> above, and neither changes the other. Table and method: '
            '<a href="#option-word-confidence-results">under Info</a>.</p>'
            f'<figure class="panel chart-card" id="chart-option-word-confidence"><div class="chart-head">'
            f"<h2>Fewer wrong answers: “{new}” or confidence?</h2>"
            f"<p class=\"chart-sub\">Each model's first run with “{new}” against its five-option run held back by its own "
            f"confidence at about the same attempt rate: the questions only one of the two got wrong, by the exact McNemar "
            f"test with p adjusted by Holm's method over the {len(tested)} models that chose “{new}” on at least {share} of "
            f"the questions · the shorter bar left fewer wrong answers</p></div>{chart}"
            f'<p class="chart-legend"><span><i class="swatch swatch-lead"></i>Wrong only with “{new}”</span> '
            '<span><i class="swatch swatch-base"></i>Wrong only when held back by its own confidence</span> '
            f"<span>{verdict}"
            + (f" Not in the test, as they chose “{new}” on fewer than {share} of the questions: {esc(joined(untested))}." if untested else "")
            + "</span></p></figure></section>")


def vs_confidence_info(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """Under Info: the option-word runs against confidence, one row per model, and the method notes."""
    digits = site.config["percent_digits"]
    total = word["questions"]
    new, old = esc(word["option"]), esc(data["option"])
    share = f"{100 * word['vs_confidence']['share']:g}%"
    coverage = lambda answered: f"{answered:,} ({pct(answered / total, digits)})"  # noqa: E731
    cut = lambda value: "none" if value is None else f"{value:.4f}"  # noqa: E731
    heads = (("Runs", f"with “{word['option']}” · five options"),
             ("Cut-off", "and its neighbouring candidates"),
             ("Answered", "target with the option · achieved by confidence (coverage)"),
             ("Wrong", f"with “{word['option']}” · by confidence; lower is better"),
             ("Wrong only on one side", f"with “{word['option']}” · by confidence"),
             ("p", "exact McNemar"), ("Holm p", "adjusted over the family"))
    labels = [f"{head} ({note})" for head, note in heads]
    rows = []
    for model in vs_confidence_rows(site, data, word):
        option, derived = model["option"], model["derived"]
        runs = (f"{model['option_run']} · {model['five_option_run']}"
                + (f'<span class="small">run {model["five_option_run"]} in place of the Text tab\'s run {model["replaces_run"]}</span>'
                   if model["replaces_run"] is not None else ""))
        below, above = derived["below"], derived["above"]
        neighbours = (f'<span class="small">next lower {cut(below["cut_off"])}'
                      + (f": {below['answered']:,} answered" if below["cut_off"] is not None else "")
                      + f'</span><span class="small">next higher {cut(above["cut_off"])}'
                      + (f": {above['answered']:,} answered" if above["cut_off"] is not None else "") + "</span>")
        answered = (f"{option['answered']:,} · {derived['answered']:,}<span class=\"small\">target {coverage(option['answered'])}, "
                    f"{option['dont_know']:,} “{new}”</span><span class=\"small\">achieved {coverage(derived['answered'])}, "
                    f"{derived['abstained']:,} held back</span>")
        values = [runs, cut(derived["cut_off"]) + neighbours, answered,
                  f"{option['wrong']:,} · {derived['wrong']:,}",
                  f"{model['option_only_wrong']:,} · {model['confidence_only_wrong']:,}",
                  esc(bp.p_text(model["p"]).removeprefix("p = ").removeprefix("p ")),
                  "not in the family" if model["p_holm"] is None else
                  esc(bp.p_text(model["p_holm"]).removeprefix("p = ").removeprefix("p ")) + (" *" if model["p_holm"] < 0.05 else "")]
        rows.append(f"<tr>{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
    family = word["vs_confidence"]["family"]
    outside = [model["name"] for model in vs_confidence_rows(site, data, word) if model["p_holm"] is None]
    glide = [model for model in word["vs_confidence"]["models"] if model["replaces_run"] is not None]
    glide_text = "".join(
        f" For {esc(model['name'])}, the five-option run is {model['five_option_run']}, not the Text tab's run "
        f"{model['replaces_run']}: Fastino changed its hosted model after 6 October, so run {model['replaces_run']} is a "
        f"different model from the one behind run {model['option_run']}, and run {model['five_option_run']} is a new "
        f'five-option run of the same hosted model (<a href="#hosted-glide-rerun-method">Our method for the hosted GLiDE '
        "rerun</a>)." for model in glide)
    return f"""
    <section class="card" id="option-word-confidence-results">
      <h2>Results: “{new}” against confidence</h2>
      <p class="note">In the tab's order. Each row: the model's first run with “{new}” and its five-option run held back by its own confidence on the same {total:,} questions. Answered = right + wrong; coverage = answered / {total:,}. Wrong only on one side: the questions only one of the two got wrong, by the exact McNemar test, with p adjusted by Holm's method over the {len(family)} models that chose “{new}” on at least {share} of the questions; * marks a Holm-adjusted p below 0.05. Not in the family: {esc(joined(outside))}.</p>
      <div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
    </section>
    <section class="card method-notes" id="option-word-confidence-method">
      <h2>Our method for “{new}” against confidence</h2>
      <p>The derived method above, applied to the runs with “{new}”: each model's five-option run answers only where its score reaches a cut-off and abstains on the rest. The candidate cut-offs are the run's distinct scores; the one chosen is the one whose attempt rate comes nearest the attempt rate of the run with “{new}”, and on a tie the higher cut-off. An answer without a score never counts as an attempt. Answers with equal scores enter together, so the achieved answered count can differ from the target; the table shows the chosen cut-off with the next lower and next higher candidates and the answers each would give.</p>
      <p>The five-option run is each model's run on the Text tab, as in the table above.{glide_text}</p>
      <p>The paired test is the exact McNemar test of wrong answers, the run with “{new}” first and confidence second, as for “{old}”. Holm's correction runs over the models that chose “{new}” on at least {share} of the scored questions: {esc(joined(family))}. The others, {esc(joined(outside))}, chose it too rarely for the two sides to differ by more than a few answers; their p is shown and not adjusted.</p>
      <p>This is a family of its own, from runs already published: it changes none of the numbers above, and it is separate from the comparisons with Holm over 4, 13 and 11 models (the four models of the request, the English questions and the option's word).</p>
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
      <p>The evidence for “a different model” and “the same model” is the engine each response names: every answer of run {old["run"]} names Fastino's engine <code>glide</code>; every answer from 10 October on names <code>glide_v2</code>, including all of run {model["run"]} and its repeats and all of run {rerun["run"]}. Fastino publishes no version to pin, so that name is the only identity we can check: it cannot show that the weights behind <code>glide_v2</code> stayed the same between 1 and 2 November.</p>
      <p>The row in the table above is left as published, against run {old["run"]}, and run {rerun["run"]} is kept out of the Text tab: its leaderboard, repeats and every other list.</p>
    </section>"""



def check_english_four(idk: dict[str, Any], four: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Stops the build unless each of the four models' counts and p equal its entry in english_reading.dont_know; returns
    the pairs (the four's entry, the comparison's entry) in the four's order."""
    def fail(text: str) -> SystemExit:
        return SystemExit(f"results.json dont_know_english_option: {text}")

    if four["questions"] != idk["questions"]:
        raise fail(f"{four['questions']} questions, english_reading.dont_know {idk['questions']}")
    pairs = []
    for model in four["models"]:
        found = [entry for entry in idk["models"] if entry["text_run"] == model["text_run"]]
        if len(found) != 1:
            raise fail(f"text run {model['text_run']} is not exactly one entry of english_reading.dont_know")
        paired = found[0]["paired"]
        if (model["name"], model["english_only_wrong"], model["turkish_only_wrong"], model["p"]) != (
                found[0]["name"], paired["english_only_wrong"], paired["turkish_only_wrong"], paired["p"]):
            raise fail(f"{model['name']}: the counts or p differ from english_reading.dont_know")
        pairs.append((model, found[0]))
    return pairs


def english_four_card(site: Site, idk: dict[str, Any], four: dict[str, Any]) -> str:
    """The four models of Ümit's follow-up with Holm's correction over the four (results.json dont_know_english_option),
    their rates and counts from the same first runs as english_reading.dont_know."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    pairs = check_english_four(idk, four)
    digits = site.config["percent_digits"]
    option = idk["option"]
    count = len(pairs)
    total = idk["questions"]
    heads = (("Answered in Turkish", "with “Bilmiyorum”: (right + wrong) / questions; higher is better"),
             ("Answered in English", f"with “{option}”: (right + wrong) / questions; higher is better"),
             ("Wrong of answers in Turkish", "with “Bilmiyorum”: wrong / (right + wrong); lower is better"),
             ("Wrong of answers in English", f"with “{option}”: wrong / (right + wrong); lower is better"),
             ("Turkish non-hallucination rate",
              "“Bilmiyorum” / (“Bilmiyorum” + wrong); higher is better; right / wrong / option"),
             ("English non-hallucination rate", f"“{option}” / (“{option}” + wrong); higher is better; right / wrong / option"),
             ("Wrong only in English", "questions the English run got wrong and the Turkish run did not"),
             ("Wrong only in Turkish", "questions the Turkish run got wrong and the English run did not"),
             ("p", "exact McNemar"), ("Holm p", f"adjusted over the {count} models"))

    def rate(counts: dict[str, Any]) -> str:
        return (f"{er.rate_text(counts['non_hallucination'], digits)}<span class=\"small\">{counts['right']:,} / "
                f"{counts['wrong']:,} / {counts['dont_know']:,}</span>")

    def p(value: float) -> str:
        return esc(bp.p_text(value).removeprefix("p = ").removeprefix("p "))

    rows = ""
    for model, entry in pairs:
        run = site.by_id[model["text_run"]]
        values = [answered_cell(entry["turkish"], total, digits), answered_cell(entry["english"], total, digits),
                  wrong_cell(entry["turkish"], digits), wrong_cell(entry["english"], digits),
                  rate(entry["turkish"]), rate(entry["english"]), f"{model['english_only_wrong']:,}",
                  f"{model['turkish_only_wrong']:,}", p(model["p"]),
                  p(model["p_holm"]) + (" *" if model["p_holm"] < 0.05 else "")]
        rows += (f'<tr><td class="model"><a class="model-name" href="{er.idk_href(site, entry)}">{esc(er.idk_label(site, entry))}</a>'
                 f'<span class="small">{esc(site.detail(run))}</span></td>'
                 + "".join(cell(f"{head} ({note})", item) for (head, note), item in zip(heads, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
    significant = [entry for model, entry in pairs if model["p_holm"] < 0.05]
    smallest = min(pairs, key=lambda pair: (pair[0]["p_holm"], pair[0]["p"]))
    words = bp.in_words(count)
    if significant:
        verdict = (f"{bp.in_words(len(significant)).capitalize()} of the {words} differences in wrong answers "
                   f"{'is' if len(significant) == 1 else 'are'} significant with Holm's correction over the {words} "
                   f"(adjusted p below 0.05): {joined([esc(er.idk_label(site, entry)) for entry in significant])}.")
    else:
        verdict = (f"None of the {words} differences in wrong answers is significant with Holm's correction over the "
                   f"{words} (adjusted p below 0.05); the smallest adjusted p is "
                   f"{esc(er.idk_label(site, smallest[1]))}'s, {esc(bp.p_text(smallest[0]['p_holm']))}.")
    return (f'<section class="card" id="english-option-four"><h2>The four models of the request: Holm\'s correction over '
            f"the four</h2><p>{joined([esc(er.idk_label(site, entry)) for _, entry in pairs])}, as Ümit's follow-up of "
            f"2 November 2026 asked: each model's first run in English with “{esc(option)}” and in Turkish with "
            f"“Bilmiyorum” on the {four['questions']:,} kept questions, and the exact McNemar test of wrong answers, with p "
            f"adjusted by Holm's method over these {words}. {verdict} The charts below and the "
            f'<a href="{rel(PATH, "turkish-vs-english/")}#dont-know">Turkish vs English tab</a> correct over all '
            f"{len(idk['models'])} compared models.</p>"
            f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f'</thead><tbody>{rows}</tbody></table></div><p class="note">Answered = (right + wrong) / {total:,} and Wrong of '
            "answers = wrong / (right + wrong) come first, then the non-hallucination rate with its counts (right / wrong / "
            f"option). * marks a Holm-adjusted p below 0.05 over the {words}.</p></section>")


def english_option_face(site: Site, idk: dict[str, Any], four: dict[str, Any] | None) -> str:
    """The English-option comparison on this tab's face: the Turkish vs English tab's kept reading questions in English
    with “I don't know” against the same models' “Bilmiyorum” answers in Turkish, its summary, the four models of Ümit's
    follow-up with Holm over the four (when results.json has dont_know_english_option) and its two charts as that tab
    draws them (sitebuild/english_reading.py), every number from results.json."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    option, total = esc(idk["option"]), idk["questions"]
    return (f'<section class="card" id="english-option"><h2>The English questions: “{option}” in English against “Bilmiyorum” '
            f"in Turkish</h2><p>The {total:,} reading questions of the "
            f'<a href="{rel(PATH, "turkish-vs-english/")}">Turkish vs English tab</a>, in English with a sixth option, '
            f"“{option}”, against the same models' “Bilmiyorum” answers on the same questions in Turkish (this tab's runs "
            "counted on those questions, or runs on those questions only). Counts and the paired test: "
            '<a href="#english-option-results">under Info</a>; how the questions were translated and kept: '
            f'<a href="{rel(PATH, "turkish-vs-english/")}#method">Turkish vs English, Our method</a>.</p>'
            f"{er.dont_know_summary(site, idk)}</section>{english_four_card(site, idk, four) if four else ''}"
            f"{er.dont_know_charts(site, idk)}")


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


# The same number of answers (results.json dont_know_same_answers): one colour per model in both plots, the Turkish vs
# English tab's colours for its models (english_reading COLOURS, in english_reading.models' order), then these for the
# models only in the Turkish family, whose lines are dashed (SAME_EXTRA_DASH) to tell them from the first fourteen;
# mid lightness, readable on both themes' panels.
SAME_EXTRA_COLOURS = ("#a1478f", "#9bbf1f", "#e3a21a", "#5fb4f0", "#b04a4a", "#2a8f8f")
SAME_EXTRA_DASH = "6 3"
# The drawn polyline skips vertices closer than this share of coverage to the previous one drawn.
SAME_MIN_STEP = 0.0025


def same_wrong_text(wrong: float) -> str:
    """A wrong count of the k answers: whole, or with one decimal when tied scores share the k-th place."""
    return f"{wrong:,.0f}" if float(wrong).is_integer() else f"{wrong:,.1f}"


def same_wrong_at(curve: list[tuple[int, int]], k: int) -> float | None:
    """The expected wrong count of a run's k most confident answers from its curve (answered, wrong per distinct score,
    highest first), by the tie rule: wrong_above + (k - taken_above) * wrong_tied / taken_tied; None below k answers."""
    taken_above = wrong_above = 0
    for answered, wrong in curve:
        if answered >= k:
            return wrong_above + (k - taken_above) * (wrong - wrong_above) / (answered - taken_above)
        taken_above, wrong_above = answered, wrong
    return None


def same_families(site: Site, same: dict[str, Any]) -> list[dict[str, Any]]:
    """dont_know_same_answers' two families with their language, each model's curve as (answered, wrong) points: the
    Turkish ones from the key, the English ones from english_reading.coverage (the model's English curve)."""
    cov = {model["text_run"]: model for model in site.results["english_reading"]["coverage"]["models"]}
    families = []
    for key, language in (("turkish", "Turkish"), ("english", "English")):
        family = dict(same[key], key=key, language=language, models=[])
        for model in same[key]["models"]:
            if key == "turkish":
                curve, curve_run = [tuple(point) for point in model["curve"]], model["five_option_run"]
            else:
                found = [curve for curve in cov[model["text_run"]]["curves"] if curve["language"] == language] \
                    if model["text_run"] in cov else []
                if len(found) != 1:
                    raise SystemExit(f"results.json dont_know_same_answers: {model['name']} has no English curve in "
                                     "english_reading.coverage")
                curve, curve_run = [(point[2], point[3]) for point in found[0]["points"]], found[0]["run"]
            family["models"].append(dict(model, curve=curve, curve_run=curve_run))
        families.append(family)
    return families


def check_same_answers(site: Site, data: dict[str, Any], word: dict[str, Any] | None, rerun: dict[str, Any] | None,
                       families: list[dict[str, Any]], reference: str) -> None:
    """Stop the build when dont_know_same_answers does not fit the tab: each family's models are its section's, k is the
    reference's run with the option's answered count there, the markers are those sections' counts, each curve ends at
    its run's scored answers and gives the published wrong count by the tie rule, and the differences and p values fit."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    fail = lambda text: SystemExit(f"results.json dont_know_same_answers: {text}")  # noqa: E731
    english = site.results["english_reading"]
    idk = english["dont_know"]
    by_text = {model["text_run"]: model for model in idk["models"] + er.english_only(idk)}
    first = {model["name"]: model for model in data["models"]}
    own = {model["name"]: model for model in (word or {}).get("models", [])}
    runs = {item["run"]: item for value in site.answers.values() if isinstance(value, list)
            for item in value if isinstance(item, dict) and "score" in item and "run" in item}
    kept_ids = {question["question_id"] for question in json.loads(er.RECORD.read_text())["questions"] if question["kept"]}
    positions = {"turkish": site.scored,
                 "english": [index for index, value in enumerate(site.answers["questions"]["id"]) if value in kept_ids]}
    for family in families:
        key, models, k = family["key"], family["models"], family["k"]
        names = [model["name"] for model in models]
        if key == "turkish":
            expected = [model["name"] for model in data["models"]]
            questions = data["questions"]
            ref = own.get(reference, {}).get("i_dont_know")
            wording = word["option"] if word else None
        else:
            expected = [model["name"] for model in english["models"]]
            questions = idk["questions"]
            ref_text = next((model["text_run"] for model in models if model["name"] == reference), None)
            ref = by_text.get(ref_text, {}).get("english")
            wording = idk["option"]
        if names != expected or reference not in names:
            raise fail(f"{key}: the models are not its section's, in its order, with {reference}")
        if family["questions"] != questions or len(positions[key]) != questions:
            raise fail(f"{key}: {family['questions']} questions, its section {questions}")
        if not ref or ref["run"] != family["k_run"] or ref["right"] + ref["wrong"] != k or family["k_wording"] != wording:
            raise fail(f"{key}: k is not the answered count of {reference}'s run {family['k_run']} with “{wording}”")
        rates = {model["name"]: model["wrong_of_answers"] for model in models}
        for model in models:
            name = model["name"]
            if key == "turkish":
                tab = first[name]
                if model["text_run"] != tab["original_run"]:
                    raise fail(f"{name}: text run {model['text_run']}, the tab {tab['original_run']}")
                if model["replaces_run"] is None:
                    if model["five_option_run"] != tab["original_run"]:
                        raise fail(f"{name}: the five-option run is not the Text tab's run {tab['original_run']}")
                elif (model["replaces_run"] != tab["original_run"] or not rerun or rerun["replaces_run"] != tab["original_run"]
                      or model["five_option_run"] != rerun["run"]):
                    raise fail(f"{name}: the five-option run does not replace the Text tab's run as hosted_glide_rerun does")
                sides = [(data["option"], tab)] + ([(word["option"], own[name]["i_dont_know"])] if name in own else [])
            else:
                section = english["models"][names.index(name)]
                if model["five_option_run"] != section["run"] or model["curve_run"] != section["run"]:
                    raise fail(f"{name}: the five-option run or its English curve is not the first English run {section['run']}")
                entry = by_text.get(model["text_run"])
                if not entry:
                    raise fail(f"{name}: no first English run with “{wording}”")
                sides = [(wording, entry["english"])]
            points = [{"wording": text, "run": counts["run"], "answered": counts["right"] + counts["wrong"],
                       "wrong": counts["wrong"]} for text, counts in sides]
            if model["points"] != points:
                raise fail(f"{name}: the markers are not its runs with the option")
            curve = model["curve"]
            if not curve or any(b[0] <= a[0] or b[1] < a[1] for a, b in zip(curve, curve[1:])) \
                    or any(wrong > answered for answered, wrong in curve):
                raise fail(f"{name} {key}: the curve does not grow")
            run = runs.get(model["five_option_run"])
            scored = None if run is None else sum(1 for index in positions[key]
                                                  if run["score"][index] is not None and run["choice"][index] is not None)
            if curve[-1][0] != scored:
                raise fail(f"{name} {key}: the curve does not end at run {model['five_option_run']}'s scored answers")
            wrong = same_wrong_at(curve, k)
            if wrong is None or abs(wrong - model["wrong"]) > 1e-9 or abs(model["wrong"] / k - model["wrong_of_answers"]) > 1e-12:
                raise fail(f"{name} {key}: the wrong count is not the curve's at k = {k:,}")
            if name == reference:
                if any(model[field] is not None for field in ("difference", "interval", "p", "p_holm")):
                    raise fail(f"{key}: the reference row has a difference or p")
                continue
            if model["difference"] is None or abs(model["difference"] - (rates[name] - rates[reference])) > 1e-12:
                raise fail(f"{name} {key}: the difference is not its rate minus {reference}'s")
            if model["p"] is None or model["p_holm"] is None or not 0 <= model["p"] <= model["p_holm"] <= 1 \
                    or not model["interval"] or model["interval"][0] > model["interval"][1]:
                raise fail(f"{name} {key}: p {model['p']}, Holm p {model['p_holm']} or the interval do not fit")


def same_verdict(models: list[dict[str, Any]], reference: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The other models with significantly more wrong answers than the reference after Holm, with significantly fewer,
    and the rest."""
    others = [model for model in models if model["name"] != reference]
    worse = [model for model in others if model["p_holm"] < 0.05 and model["difference"] > 0]
    better = [model for model in others if model["p_holm"] < 0.05 and model["difference"] < 0]
    return worse, better, [model for model in others if model not in worse and model not in better]


def same_label(site: Site, model: dict[str, Any]) -> str:
    return site.row_name(site.by_id[model["text_run"]])


def same_summary(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """The section's summary from dont_know_same_answers: for each family, k and where it comes from, the reference's
    wrong of answers and which models differ significantly from it after Holm."""
    digits = site.config["percent_digits"]
    reference = same["reference"]
    points = lambda values: f"{min(values):.{digits}f} to {max(values):.{digits}f} points" if len(values) > 1 \
        else f"{values[0]:.{digits}f} points"  # noqa: E731
    texts = []
    for family in families:
        k, models = family["k"], family["models"]
        ref = next(model for model in models if model["name"] == reference)
        worse, better, rest = same_verdict(models, reference)
        count = len(models) - 1
        where = (f"the {family['questions']:,} questions" if family["key"] == "turkish" else
                 f"the {family['questions']:,} kept reading questions")
        text = (f"In {family['language']}, k = {k:,}, the answers of {esc(reference)}'s run {family['k_run']} with "
                f"“{esc(family['k_wording'])}” on {where}: {esc(reference)}'s five-option run (run {ref['five_option_run']}) "
                f"keeps {same_wrong_text(ref['wrong'])} wrong of {k:,} ({pct(ref['wrong_of_answers'], digits)})")
        parts = []
        if worse:
            who = f"all {count} other models" if len(worse) == count else \
                f"{len(worse)} of the {count} others ({joined([esc(same_label(site, model)) for model in worse])})"
            parts.append(f"{who} keep significantly more, {points([100 * model['difference'] for model in worse])} more")
        if better:
            parts.append(f"{joined([esc(same_label(site, model)) for model in better])} significantly fewer, "
                         f"{points([-100 * model['difference'] for model in better])} fewer")
        if not worse and not better:
            parts.append(f"none of the {count} others differs significantly")
        if rest and (worse or better):
            fewer = [model for model in rest if model["difference"] < 0]
            parts.append(("for the other model" if len(rest) == 1 else f"for the other {len(rest)}")
                         + ", the difference could be chance"
                         + (" (" + joined([f"{esc(same_label(site, model))} keeps fewer, {same_wrong_text(model['wrong'])} "
                                           f"against {same_wrong_text(ref['wrong'])}, but not significantly" for model in fewer])
                            + ")" if fewer else ""))
        texts.append(f"{text}; after Holm's correction over the {count}, " + "; ".join(parts) + ".")
    return (f"<p>Each model's five-option run keeps only its k most confident answers, k being the number of questions "
            f"{esc(reference)} answered with “I don't know” on offer, and we count the wrong ones among them. "
            + " ".join(texts) + "</p>")


def same_colours(site: Site, families: list[dict[str, Any]]) -> dict[str, tuple[str, str | None]]:
    """One colour per model name across both plots, with its line's dash: the Turkish vs English tab's colours for its
    models (solid), then the extra ones (dashed)."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    colours: dict[str, tuple[str, str | None]] = {
        model["name"]: (colour, None) for model, colour in zip(site.results["english_reading"]["models"], er.COLOURS)}
    extra = iter(SAME_EXTRA_COLOURS)
    for family in families:
        for model in family["models"]:
            if model["name"] not in colours:
                colour = next(extra, None)
                if colour is None:
                    raise SystemExit("results.json dont_know_same_answers: more models than colours")
                colours[model["name"]] = (colour, SAME_EXTRA_DASH)
    return colours


def same_plot(site: Site, same: dict[str, Any], family: dict[str, Any], colours: dict[str, tuple[str, str | None]]) -> str:
    """One family's risk-coverage plot: each model's five-option curve as a line (flat from 0% coverage to its first
    point), its own runs with the option as markers and a dashed guide at k."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    digits = site.config["percent_digits"]
    total, k, language, reference = family["questions"], family["k"], family["language"], same["reference"]
    guide = f"k = {k:,}: {reference}'s answers with “{family['k_wording']}”"
    values = [point["wrong"] / point["answered"] for model in family["models"] for point in model["points"] if point["answered"]]
    values += [wrong / answered for model in family["models"] for answered, wrong in model["curve"] if answered / total >= 0.01]
    y_top = max(0.04, math.ceil(100 * max(values, default=0.04) / 4 - 1e-9) * 4 / 100)
    series, legend = [], []
    for model in family["models"]:
        (colour, dash), name, curve = colours[model["name"]], same_label(site, model), model["curve"]
        at_k = next(index for index, (answered, _) in enumerate(curve) if answered >= k)
        drawn, last = [0], curve[0][0]
        for index in range(1, len(curve)):
            if index in (at_k, len(curve) - 1) or (curve[index][0] - last) / total >= SAME_MIN_STEP:
                drawn.append(index)
                last = curve[index][0]
        line = [(0.0, curve[0][1] / curve[0][0], "")] + [(curve[index][0] / total, curve[index][1] / curve[index][0], "")
                                                         for index in drawn]
        replaced = f", in place of run {model['replaces_run']}" if model.get("replaces_run") else ""
        series.append({"colour": colour, "dash": dash, "line": True, "points": line,
                       "title": f"{name}: five options, run {model['five_option_run']}{replaced}, held back by confidence; "
                                f"its {k:,} most confident answers: {same_wrong_text(model['wrong'])} wrong "
                                f"({pct(model['wrong_of_answers'], digits)})"})
        keys = [f"{legend_mark(colour, dash=dash)} five options, run {model['five_option_run']}"]
        for point in model["points"]:
            shape = er.SHAPES[point["wording"]]
            tip = (f"{name}: “{point['wording']}”, run {point['run']}: {point['answered']:,} answered "
                   f"({pct(point['answered'] / total, digits)}), {point['wrong']:,} wrong "
                   f"({'not measured' if not point['answered'] else pct(point['wrong'] / point['answered'], digits)})")
            series.append({"colour": colour, "shape": shape, "title": tip,
                           "points": [(point["answered"] / total, point["wrong"] / point["answered"] if point["answered"] else 0, tip)]})
            keys.append(f"{legend_mark(colour, shape)} “{esc(point['wording'])}”, run {point['run']}")
        legend.append(f"<li><b>{esc(name)}</b>: {' · '.join(keys)}</li>")
    shapes = " ".join(f"{legend_mark('var(--text-2)', er.SHAPES[wording])} “{esc(wording)}”"
                      for wording in dict.fromkeys(point["wording"] for model in family["models"] for point in model["points"]))
    dash = ('<svg width="20" height="14" viewBox="0 0 20 14" aria-hidden="true" style="vertical-align:middle">'
            '<line x1="10" y1="1" x2="10" y2="13" stroke="var(--text-2)" stroke-width="1.5" stroke-dasharray="3 2"/></svg>')
    title = f"The same number of answers in {language}"
    where = "questions" if family["key"] == "turkish" else "kept reading questions"
    return (f'<figure class="panel chart-card" id="chart-same-answers-{family["key"]}"><div class="chart-head">'
            f'<h2>{esc(title)}</h2><p class="chart-sub">The {total:,} {where} in {language}: each model\'s five-option run '
            f"answering only its most confident answers (the line), and its own runs with the option (the marker: {shapes}) "
            "· lower is better at the same coverage</p></div>"
            f'<div class="chart-box" style="min-height:0;overflow-x:auto">'
            + line_plot(series, f"Answered (coverage, of {total:,})", "Wrong of answers", y_top,
                        f"{title}: answered against wrong of answers", ((k / total, f"k = {k:,}", guide),))
            + f'</div><ul class="chart-legend" style="list-style:none;padding:0"><li>{dash} {esc(guide)}</li>'
            f'{"".join(legend)}</ul></figure>')


def same_face(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """The section on the tab's face: its summary and the two plots."""
    colours = same_colours(site, families)
    return (f'<section class="card" id="same-answers"><h2>The same number of answers</h2>'
            f"{same_summary(site, same, families)}"
            f'<p class="note">The difference from {esc(same["reference"])} is tested by a paired bootstrap over questions, '
            "with p adjusted by Holm's method in each language. Each plot shows every number of answers, not only k: the "
            "line is the five-option run held back by its own confidence, the markers the model's runs with the option. "
            'Tables and method: <a href="#same-answers-results">under Info</a>.</p></section>'
            f'<section class="charts" aria-label="The same number of answers">'
            + "".join(same_plot(site, same, family, colours) for family in families) + "</section>")


def same_finding(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """One sentence for What we found."""
    digits = site.config["percent_digits"]
    reference = same["reference"]
    parts, levels, ks = [], [], []
    for family in families:
        ref = next(model for model in family["models"] if model["name"] == reference)
        worse, better, _ = same_verdict(family["models"], reference)
        count = len(family["models"]) - 1
        if not worse and not better:
            verdict = f"none of the {count} others differed significantly"
        else:
            groups = []
            if worse:
                groups.append(f"all {count} others had significantly more wrong answers" if len(worse) == count else
                              f"{len(worse)} of the {count} others had significantly more")
            groups.append((f"{len(better)} significantly fewer" if worse else
                           f"{len(better)} of the {count} others had significantly fewer") if better else "none significantly fewer")
            verdict = groups[0] if len(worse) == count else " and ".join(groups)
        parts.append(f"in {family['language']} {verdict}")
        levels.append(f"{pct(ref['wrong_of_answers'], digits)}{'' if levels else ' of its k answers wrong'} in {family['language']}")
        ks.append(f"{family['k']:,} in {family['language']}")
    return (f"<p>Held to {esc(reference)}'s number of answers with “I don't know” (k = {joined(ks)}), each model keeping "
            f"its k most confident five-option answers, {esc(reference)}'s five-option run got {joined(levels)}; by "
            f"a paired bootstrap with Holm's correction, {joined(parts)} "
            '(<a href="#same-answers">The same number of answers</a>).</p>')


def same_info(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """Under Info: one table per family and the method notes."""
    digits = site.config["percent_digits"]
    reference = same["reference"]
    p_text = lambda value: esc(bp.p_text(value).removeprefix("p = ").removeprefix("p "))  # noqa: E731
    tables = ""
    for family in families:
        k, total, count = family["k"], family["questions"], len(family["models"]) - 1
        heads = (("Five-option run", "the run whose k answers are kept"),
                 ("Wrong of the k answers", f"wrong / {k:,}; lower is better"),
                 (f"Difference from {reference}", "points, with its 95% interval; positive = more wrong answers"),
                 ("p", "paired bootstrap, two-sided"), ("Holm p", f"adjusted over the {count}"),
                 ("Runs with the option", "for context: answered, wrong of answers"))
        labels = [f"{head} ({note})" for head, note in heads]
        rows = []
        for model in sorted(family["models"], key=lambda model: (model["wrong_of_answers"], same_label(site, model).casefold())):
            five = (f"{model['five_option_run']}"
                    + (f'<span class="small">in place of the Text tab\'s run {model["replaces_run"]}</span>'
                       if model.get("replaces_run") else ""))
            wrong = (f'{pct(model["wrong_of_answers"], digits)}<span class="small">{same_wrong_text(model["wrong"])} of '
                     f"{k:,}</span>")
            context = (" · ".join(str(point["run"]) for point in model["points"])
                       + "".join(f'<span class="small">“{esc(point["wording"])}”, run {point["run"]}: {point["answered"]:,} '
                                 f"answered ({pct(point['answered'] / total, digits)}), "
                                 + (f"{pct(point['wrong'] / point['answered'], digits)} wrong ({point['wrong']:,})"
                                    if point["answered"] else "wrong of answers not measured") + "</span>"
                                 for point in model["points"]))
            if model["name"] == reference:
                own = next(point for point in model["points"] if point["run"] == family["k_run"])
                values = [five, wrong,
                          f'reference<span class="small">its own run {own["run"]} with “{esc(own["wording"])}”: '
                          f'{own["wrong"]:,} wrong of {own["answered"]:,} ({pct(own["wrong"] / own["answered"], digits)}), '
                          "not part of the test</span>", "reference", "reference", context]
            else:
                low, high = model["interval"]
                values = [five, wrong,
                          f'{100 * model["difference"]:+.{digits}f}<span class="small">{100 * low:+.{digits}f} to '
                          f"{100 * high:+.{digits}f}</span>",
                          p_text(model["p"]), p_text(model["p_holm"]) + (" *" if model["p_holm"] < 0.05 else ""), context]
            rows.append(f"<tr>{model_cell(site, {'original_run': model['text_run']})}"
                        + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
        head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
        where = "questions" if family["key"] == "turkish" else "kept reading questions"
        tables += (f"<h3>{family['language']}: k = {k:,} of the {total:,} {where}</h3>"
                   f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}'
                   f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    turkish, english = families
    resamples = same["resamples"]
    tail = round(0.025 * resamples)
    glide = [model for model in turkish["models"] if model.get("replaces_run")]
    glide_text = "".join(
        f" For {esc(same_label(site, model))}, the Turkish five-option run is {model['five_option_run']}, not the Text "
        f"tab's run {model['replaces_run']}: Fastino changed its hosted model after 6 October, so run "
        f"{model['replaces_run']} is a different model from the one behind its runs with the option, and run "
        f"{model['five_option_run']} is a five-option run of the same hosted model "
        '(<a href="#hosted-glide-rerun-method">Our method for the hosted GLiDE rerun</a>).' for model in glide)
    refs = {family["key"]: next(model for model in family["models"] if model["name"] == reference) for family in families}
    owns = {key: next(point for point in model["points"] if point["run"] == families[index]["k_run"])
            for index, (key, model) in enumerate(refs.items())}
    return f"""
    <section class="card" id="same-answers-results">
      <h2>Results: the same number of answers</h2>
      <p class="note">One table per language, ordered by wrong of the k answers, fewest first. Each row: the model's five-option run held to its k most confident answers, its wrong answers among them (one decimal where tied scores share the k-th place), the difference from {esc(reference)} in points with its 95% bootstrap interval, p and Holm p (* marks a Holm-adjusted p below 0.05), and for context the model's own runs with the option (answered = right + wrong, and wrong of answers = wrong / answered), which are not part of the test.</p>
      {tables}
    </section>
    <section class="card method-notes" id="same-answers-method">
      <h2>Our method for the same number of answers</h2>
      <p>Each model's five-option run answers only its k most confident questions, by its score (the probability it gave the option it picked), and holds back on the rest; we count its wrong answers among the k. Wrong of the k answers = wrong / k. k is the number of questions {esc(reference)} answered (right + wrong) with the option on offer: {turkish["k"]:,} in its run {turkish["k_run"]} with “{esc(turkish["k_wording"])}” on the {turkish["questions"]:,} Turkish questions (the option's word, above), and {english["k"]:,} in its run {english["k_run"]}, its first English run with “{esc(english["k_wording"])}”, on the {english["questions"]:,} kept reading questions. Every model in a language is held to the same k.</p>
      <p>The answers are ranked by score, highest first; an answer without a score or a valid choice is never kept. When the k-th place falls inside a group of equal scores, the group counts in proportion: with taken and wrong the answers above the group, and tied and tied wrong those in it, the wrong count is wrong + (k - taken) × tied wrong / tied, the expectation over a random order of the tied answers. Without a tie at k the count is a whole number.</p>
      <p>The difference is a model's wrong of the k answers minus {esc(reference)}'s, in points. Its uncertainty comes from a paired bootstrap over questions: {resamples:,} resamples of the questions with replacement (seed {same["seed"]}, a new generator for each language), the same resample for every model, a question drawn twice counting twice and k fixed; in each resample every run's drawn answers are ranked and counted again by the same rule. Two-sided p = min(1, 2 × min(1 + the resamples with a difference of 0 or less, 1 + those with 0 or more) / {resamples + 1:,}). Its floor is 2/{resamples + 1:,} (p = {esc(bp.p_text(2 / (resamples + 1)).removeprefix("p = "))}), when no resample falls on the other side of zero: a p at the floor says the difference held in every resample, not that p is exactly that value. The 95% interval runs from the {tail:,}th smallest to the {tail:,}th largest of the {resamples:,} resampled differences.</p>
      <p>Holm's method adjusts p over the other {len(turkish["models"]) - 1} models in Turkish and the other {len(english["models"]) - 1} in English, each language a family of its own, separate from the tab's other comparisons.{glide_text}</p>
      <p>The plots show every number of answers, not only k. Each line is a five-option run's risk-coverage curve, one point per distinct score (answering where the score is at least that score): answered / questions across, wrong / answered up. The Turkish curves are those of the runs in the table; the English curves are the Turkish vs English tab's (<a href="{rel(PATH, "turkish-vs-english/")}#coverage">Risk and coverage</a>), the same first English runs. Under the tie rule, the share wrong below a curve's first point is that point's, so each line starts flat at 0% coverage. A line skips vertices closer than {100 * SAME_MIN_STEP:g}% of coverage to the previous one drawn, always keeping the first, the last and the point at k, so every vertex drawn after the flat start is a curve point; the y axis fits the markers and every curve point at 1% coverage or more, and anything higher is drawn at the top edge. The markers are each model's own runs with the option: in Turkish its first run with “{esc(site.results["dont_know"]["option"])}” (the table above) and its run with “{esc(turkish["k_wording"])}” (the option's word); in English its first English run with “{esc(english["k_wording"])}”.</p>
      <p>Limits: k comes from one model, {esc(reference)}, and a different k gives different numbers (the plots show them all). The k answers kept are each model's own most confident ones, so the models are counted on different questions. {esc(reference)}'s own runs with the option made {owns["turkish"]["wrong"]:,} wrong of {owns["turkish"]["answered"]:,} in Turkish and {owns["english"]["wrong"]:,} of {owns["english"]["answered"]:,} in English, against {same_wrong_text(refs["turkish"]["wrong"])} and {same_wrong_text(refs["english"]["wrong"])} for its five-option run held to the same k: the comparison is between five-option runs held back by confidence, not between runs with the option.</p>
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
    against = word if word and word.get("vs_confidence") else None
    if against:
        check_vs_confidence(site, data, against, rerun)
    same = site.results.get("dont_know_same_answers")
    families = same_families(site, same) if same else []
    if same:
        check_same_answers(site, data, word, rerun, families, same["reference"])
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">Hallucination</p>
      <h1>The Text tab's {total} questions, with “{option}” as a sixth option</h1>
      <p>A wrong answer counts as a hallucination: the model could have chosen “{option}” (“{esc(data["option_en"])}”) instead. This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its numbers.</p>
      {headline(data, against)}
      <nav class="face-nav" aria-label="On this page"><a href="#chart-non-hallucination">Non-hallucination</a><a href="#chart-confidence">Against confidence</a><a href="#chart-paired">Paired test</a><a href="#chart-accuracy">Accuracy</a>{'<a href="#english-option">English questions</a>' if english else ""}{'<a href="#option-word">The option&#x27;s word</a>' if word else ""}{'<a href="#option-word-confidence">“I don&#x27;t know” against confidence</a>' if against else ""}{'<a href="#hosted-glide-rerun">Hosted GLiDE rerun</a>' if rerun else ""}{'<a href="#same-answers">The same number of answers</a>' if same else ""}<a href="#info">Info</a></nav>
    </section>
    {face(site, data)}{english_option_face(site, english, site.results.get("dont_know_english_option")) if english else ""}{option_word_face(site, data, word) if word else ""}{vs_confidence_face(site, data, against) if against else ""}{rerun_face(site, data, rerun, glide) if rerun else ""}{same_face(site, same, families) if same else ""}
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
      <p class="note">The first two columns: Answered, how often the model chose one of the question's own options (right + wrong, out of all {total} questions), and Wrong of answers, the share of those answers that were wrong (wrong / (right + wrong)). The rows are ranked by the third, the non-hallucination rate, highest first: the share of “{option}” among the answers that were not right (“{option}” / (“{option}” + wrong)), so the first model is the one that most often said it did not know instead of answering wrongly. Read the ranking with Answered, Wrong of answers and accuracy: a model that always chose “{option}” would rank first with no right answers. Each row shows the model's first run{"; under Runs, a model with more than one run (" + esc(joined(several)) + ") shows the range over its runs and how many answers changed between them" if several else ""}. Out of all {total} questions: accuracy counts the right answers; Answered (the attempt rate) counts the right and wrong answers. Formulas and how to read them: <a href="#method">Our method</a>.</p>
      {table(site, data)}
      {not_run(site.config["dont_know"]["not_run"])}
    </section>
    <section class="card" id="findings">
      <h2>What we found</h2>
      {findings(site, data, against)}{same_finding(site, same, families) if same else ""}
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
        <li><strong>Answered</strong> (the attempt rate) = (right + wrong) / {total}: how often the model chose one of the question's own options.</li>
        <li><strong>Wrong of answers</strong> = wrong / (right + wrong): among the answers the model gave, the share that were wrong. With no answer it is undefined (Not measured).</li>
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
    </section>{english_option_info(site, english) if english else ""}{option_word_info(site, data, word) if word else ""}{vs_confidence_info(site, data, against) if against else ""}{rerun_info(site, data, rerun, glide) if rerun else ""}{same_info(site, same, families) if same else ""}
    </details>"""
    return {PATH: site.page(PATH, "Hallucination",
                            f"The Text tab's {total} questions with a sixth option, “{data['option']}” (I don't know): accuracy, "
                            "attempt rate and non-hallucination rate of the most accurate decision models.", body)}
