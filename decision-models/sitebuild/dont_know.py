"""Hallucination (dont-know/), the site's third tab: the Text tab's questions with one more option after each
question's own, "Bilmiyorum" ("I don't know"), from results.json's `dont_know` and page_config.json's `dont_know` (the
models not run, with their reasons, and the reason of a chat model's run still running). Its face, as the home page's,
is charts (face()): first holding back two ways side by side (sitebuild/holding_back.py), by confidence at the threshold
(each model's Text tab run) and with the option (the non-hallucination rate, the answered share and the error rate
among the answers together, holding_back.COLUMNS); then the non-hallucination rate with the option and held back by
confidence, and accuracy with the option against accuracy with five options, as HTML bars (Site hbars). The charts and
the table (one row per model, from its first run, the non-hallucination rate, Answered and Error rate first, as on Logic
& Math, ranked by non-hallucination rate, accuracy breaking
ties; a model with more than one run shows the range over its runs) come once per group of the view bar (all, decision,
chat; data-models, toggled by site.js; the all group shown without JavaScript; a row's group by Site.in_group of its
Text tab run, group_models; every model's row and bar also carries its Class key, data-class, filtered by site.js), each chart and the table with decision and chat models in blocks of their own, each its own
ranking under its heading (holding_back.kinds: both under all, else the group's kind), never one mixed list; each row's kind by its
`group` field, which must be the Text tab's (Site.decision). The chat setups whose Turkish run with the option is still
running are listed with their reason for each group they are in (running_setups). The parts about decision models only
come for the all and decision groups (DECISION_ONLY): the headline, the paired test against confidence, the English questions, the
option's word, the hosted GLiDE rerun, the same number of answers (risk-coverage plots on the face, tables under Info)
and the answers at 95%+ confidence, each from the decision models' rows. Under Info: the tables, What we found and Our
method, with both kinds' added sentence and prompt version. It needs no JavaScript. The tab ranks nothing on the Text
tab and changes none of its numbers."""

from __future__ import annotations

import json
import itertools
import math
from typing import Any, Callable

import build_page as bp
from sitebuild import holding_back as hold
from sitebuild.site import (DECISION_ONLY, GROUPS, NO_ANSWERS, Site, esc, hbars, legend_mark, line_plot, marker_path,
                            measure_rows, more_link, pct, rank_fill, rel, scale_legend, shown)
from sitebuild.names import entry as shared_entry, tag_html
from sitebuild.vision import cell, joined, run_span

PATH = "dont-know/"
# The models the tab covers, as chosen before the runs (the Text tab at results 25290875).
SELECTION = ("the ten most accurate decision models on the Text tab at results 25290875, plus Base Labs' Elephant-1 and "
             "Mammoth-1 and SubQ Snap 1.1 once their text runs are published")
NEUTRAL = "neither better nor worse on its own"


def shown_option(option: str) -> str:
    """The option as labels show it (leaderboard.OPTION_SHOWN: “Bilmiyorum” as “I don't know”)."""
    from sitebuild.leaderboard import OPTION_SHOWN  # here, not at the top: leaderboard imports english_reading, which imports this module
    return OPTION_SHOWN.get(option, option)


def columns(option: str, total: int) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: header and what it is or which direction is better; the three measures of
    the run with the option first (holding_back.measures, as on Logic & Math)."""
    option = shown_option(option)
    rate, answered, error = hold.measures(option, total)
    return (
        (rate[0], f"{rate[1]} · higher is better"),
        (answered[0], answered[1]),
        (error[0], f"{error[1]} · lower is better"),
        ("Derived non-hallucination rate", "from the 5-option text run; higher is better"),
        ("Accuracy", "higher is better"),
        (f"Mean probability of “{option}”", f"higher means more probability on the option; {NEUTRAL}"),
        ("Text accuracy with five options", "the Text tab's number; higher is better"),
        ("Runs", "range over the runs where more than one"),
    )


def answered_cell(counts: dict[str, Any], total: int, digits: int, extra: str = "") -> str:
    """The Answered cell: (right + wrong) / questions, with its counts and anything after them (extra)."""
    answered = counts["right"] + counts["wrong"]
    return f'{pct(answered / total, digits)}<span class="small">{answered:,} of {total:,} answered{extra}</span>'


def wrong_cell(counts: dict[str, Any], digits: int) -> str:
    """The Error rate cell: wrong / (right + wrong) with its counts; No answers (undefined) without an answer."""
    answered = counts["right"] + counts["wrong"]
    if not answered:
        return '<span class="nm">No answers</span>'
    return f'{pct(counts["wrong"] / answered, digits)}<span class="small">{counts["wrong"]:,} of {answered:,}</span>'


def ranked(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tab's leaderboard order: non-hallucination rate, highest first (a model without one last), then accuracy, then
    name. results.json keeps the models in its own order."""
    return sorted(models, key=lambda model: (model["non_hallucination"] is None, -(model["non_hallucination"] or 0),
                                             -model["accuracy"], model["name"].casefold()))


def model_cell(site: Site, model: dict[str, Any]) -> str:
    """The model, linked to the page of its Text tab setup (the original run): its official name, its small tag beside
    the link, its settings in the tooltip."""
    run = site.by_id[model["original_run"]]
    detail = site.detail(run)
    tip = f' title="{esc(detail)}"' if detail else ""
    return (f'<td class="model"{tip}>{site.icon(run)}<a class="model-name" href="{rel(PATH, site.model_path(run))}">'
            f'{esc(site.title(run))}</a>{tag_html(site.tag(run))} {site.label(run)}</td>')


def model_tr(site: Site, model: dict[str, Any]) -> str:
    """The opening <tr> of the model's row, with its Class key (site.class_attribute of the original run)."""
    return f"<tr{site.class_attribute(site.by_id[model['original_run']])}>"


def row(site: Site, data: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    option, total = shown_option(data["option"]), data["questions"]
    percent = lambda value: '<span class="nm">Undefined</span>' if value is None else pct(value, digits)  # noqa: E731
    heads = [f"{head} ({direction})" for head, direction in columns(option, total)]
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
            f"{name} {percent(spread[key][0])} to {percent(spread[key][1])}" if spread[key] else f"{name} undefined in a run"
            for key, name in (("attempt_rate", "Answered"), ("non_hallucination", "Non-hallucination"),
                              ("accuracy", "Accuracy"), ("mean_dont_know_probability", "Mean probability"))
        ]
        changed = model["answers_changed"]
        ranges.append(f"{changed:,} answer{'' if changed == 1 else 's'} changed between runs")
        runs_text = run_span(model["runs"]) + "".join(f'<span class="small">{item}</span>' for item in ranges)
    values = [
        f'{percent(model["non_hallucination"])}<span class="small">{model["dont_know"]:,} “{esc(option)}” of '
        f'{model["dont_know"] + model["wrong"]:,} not right</span>',
        answered_cell(model, total, digits, f', {model["dont_know"]:,} “{esc(option)}”{invalid}'),
        wrong_cell(model, digits),
        f'{percent(derived["non_hallucination"])}<span class="small">{cut}, attempt rate {percent(derived["attempt_rate"])}</span>',
        f'{percent(model["accuracy"])}<span class="small">{model["right"]:,} of {total:,} right</span>',
        percent(model["mean_dont_know_probability"]) if model["group"] == "decision" else
        '<span class="nm">No probabilities</span><span class="small">a chat model states a confidence, not option probabilities</span>',
        f'{percent(model["original_accuracy"])}<span class="small"><a href="{rel(PATH, site.model_path(run))}">run {run["run"]}</a></span>',
        runs_text,
    ]
    return f"{model_tr(site, model)}{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>"


def table(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the table: a decision and a chat block (holding_back.kinds: both under all, else the group's kind), each with
    its heading and its rows ranked (ranked)."""
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>'
                   for name, direction in columns(data["option"], data["questions"]))
    models = ranked(group_models(site, data, group))
    blocks = "".join(
        hold.block(heading, '<div class="table-wrap"><table class="board list stack idk idk-lead"><thead><tr><th scope="col">Model</th>'
                   f'{head}</tr></thead><tbody>{"".join(row(site, data, model) for model in mine)}</tbody></table></div>', 3)
        for kind, heading in hold.kinds(group) if (mine := [model for model in models if model["group"] == kind]))
    return f"<div {shown(group)}>{blocks}</div>"


def not_run(items: list[dict[str, Any]]) -> str:
    """The models chosen but not run, each with its reason (page_config.json's dont_know.not_run)."""
    if not items:
        return ""
    lines = "".join(f"<li><strong>{esc((shared_entry(item['name']) or {}).get('name') or item['name'])}</strong>: "
                    f"{esc(item['reason'].removeprefix('Not run: '))}</li>" for item in items)
    return f'<h3 class="board-group">Not run</h3><ul>{lines}</ul>'


def running_setups(site: Site) -> list[dict[str, Any]]:
    """The Text tab runs of the chat setups whose English run with the option is published and whose Turkish one is still
    running (results.json english_reading.dont_know.english_only, running), in that order."""
    idk = (site.results.get("english_reading") or {}).get("dont_know") or {}
    return [site.by_id[model["text_run"]] for model in idk.get("english_only", []) if model.get("running")]


def running_list(site: Site, group: str) -> str:
    """A group's list of the chat setups still running in Turkish (running_setups), with page_config.json's reason."""
    runs = [run for run in running_setups(site) if site.in_group(run, group)]
    if not runs:
        return ""
    lines = "".join(f'<li><a href="{rel(PATH, site.model_path(run))}">{esc(site.title(run))}</a>{tag_html(site.tag(run))}</li>'
                    for run in runs)
    return (f'<h3 class="board-group">Running</h3><p class="note">{esc(site.config["dont_know"]["running"])} The English run '
            f"of each is on the Turkish vs English tab.</p><ul>{lines}</ul>")


def group_data(data: dict[str, Any], kind: str) -> dict[str, Any]:
    """The section with the rows of one kind of model (decision or chat), as the parts about one kind read it."""
    return {**data, "models": [model for model in data["models"] if model["group"] == kind]}


def group_models(site: Site, data: dict[str, Any], group: str) -> list[dict[str, Any]]:
    """The rows of one group of the view bar: those whose Text tab run is in it (Site.in_group; all: every row)."""
    return [model for model in data["models"] if site.in_group(site.by_id[model["original_run"]], group)]


def findings(site: Site, data: dict[str, Any], word: dict[str, Any] | None = None) -> str:
    """What we found: the table's main results in words, every number computed from results.json's dont_know. The
    sentences assume what they say (some models used the option and lost accuracy, the rest almost never chose it, each
    derived rate holds back on as many questions as its run said “Bilmiyorum”, or, where tied scores at the cut-off
    allow no such count, on the nearest count, named with both counts); the build stops when the data no longer fits
    them, so the text is rewritten rather than left wrong."""
    digits = site.config["percent_digits"]
    option, total = esc(shown_option(data["option"])), data["questions"]
    p = lambda value: pct(value, digits)  # noqa: E731
    shown = lambda value: round(100 * value, digits)  # noqa: E731 - a rate in points, as the table shows it
    name = lambda model: esc(site.plain(site.by_id[model["original_run"]]))  # noqa: E731
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
    # Where tied scores allow no cut-off with the run's count, derived_abstention takes the nearest; the text names it.
    apart = [model for model in models if model["derived"]["abstained"] != model["dont_know"]]
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
              f"{top['dont_know'] + top['wrong']:,} answers that were not right, {top['dont_know']:,} were “{option}”. It "
              f"answered {p(top['attempt_rate'])} of the questions, with an error rate of {p(hold.error_rate(top))} among "
              "those answers. "
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
    nearest = [model for model in fewer if model in apart]
    note = (f" (for {joined([name(model) for model in nearest])}, {joined([format(model['derived']['abstained'], ',') for model in nearest])} "
            f"against {joined([format(model['dont_know'], ',') for model in nearest])}: tied scores at the cut-off allow "
            "no nearer count)" if nearest else "")
    third = (f"<p>For {len(fewer)} of the {len(used)}, the model's own confidence on its five-option run, holding back on as "
             f"many questions{note}, left fewer wrong answers than “{option}” did: {min(saved):,} to {max(saved):,} fewer, a "
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


def headline(site: Site, data: dict[str, Any], word: dict[str, Any] | None = None) -> str:
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

    option = esc(shown_option(data["option"]))
    run_of = {model["name"]: site.by_id[model["original_run"]] for model in data["models"]}
    family = [dict(model["vs_confidence"], name=site.plain(run_of[model["name"]])) for model in ranked(data["models"])
              if model["vs_confidence"]["p_holm"] is not None]
    texts = [sentence("Holding back on as many questions, ", option, family, True)]
    vs = (word or {}).get("vs_confidence")
    if vs:
        order = {model["name"]: index for index, model in enumerate(ranked(data["models"]))}
        new = esc(word["option"])
        others_family = [dict(model, name=site.plain(run_of[model["name"]]))
                         for model in sorted((model for model in vs["models"] if model["p_holm"] is not None),
                                             key=lambda model: order[model["name"]])]
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


def anchor(base: str, group: str) -> str:
    """A part's id in its group's copy: the all group keeps the plain id, the one links use."""
    return base if group == GROUPS[0] else f"{base}-{group}"


def face(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the tab's face: four chart cards, each with a line saying which way is better, every number
    from results.json: holding back by confidence (each model's Text tab run at the threshold, runs[].confidence) beside
    holding back with the option (dont_know: the answered share, the wrong share of the answers and the non-hallucination
    rate together), each in a decision and a chat block (holding_back; under the decision block the models that almost
    never chose the option), then that rate against confidence, the paired test of the two (vs_confidence, the decision
    models only: for every group with one, its rows the group's, Holm's family every decision model's) and accuracy. A
    single-series bar takes the ranking scale between the models' worst and best values on its chart."""
    option = esc(shown_option(data["option"]))
    shown_word = shown_option(data["option"])
    stops = site.config["rank_scale"]["stops"]
    total = data["questions"]
    digits = site.config["percent_digits"]
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    label = lambda model: site.plain(run_of(model))  # noqa: E731
    title = lambda model: site.title(run_of(model))  # noqa: E731
    tag = lambda model: site.tag(run_of(model))  # noqa: E731
    href = lambda model: rel(PATH, site.model_path(run_of(model)))  # noqa: E731
    models = ranked(group_models(site, data, group))
    rated = [model for model in models if model["non_hallucination"] is not None]

    def card(base: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor(base, group)}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    def split_card(base: str, title: str, sub: str, picked: list[dict[str, Any]],
                   rows_of: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
                   legend_of: Callable[[list[dict[str, Any]], str], str], **axis: Any) -> str:
        """A chart card whose models (picked, in the card's order) show as a decision and a chat block, each its own
        ranking under its heading (holding_back.kinds: both under all); a kind without a model has no block."""
        blocks = "".join(hold.block(heading, f'{hbars(rows_of(mine), **axis)}<p class="chart-legend">{legend_of(mine, heading)}</p>', 3)
                         for kind, heading in hold.kinds(group)
                         if (mine := [model for model in picked if model["group"] == kind]))
        return (f'<figure class="panel chart-card" id="{anchor(base, group)}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{blocks}</figure>')

    def shown_rate(value: float | None) -> str:
        return "undefined" if value is None else pct(value, digits)

    # The three measures in Logic & Math's order (holding_back.COLUMNS), each with its bar's kind.
    measures = (("Non-hallucination", "lead", lambda model: model["non_hallucination"]),
                ("Answered", "base", lambda model: model["attempt_rate"]), ("Error rate", "wrong", hold.error_rate))

    def option_block(who: str, heading: str) -> str:
        """(B)'s block of one kind of model (who: decision or chat): its rows in the table's order, each its three
        measures as bars with their values under named columns, the measures' legend and, for the decision models, the
        ones that almost never chose the option (holding_back.rare_note)."""
        mine = [model for model in models if model["group"] == who]
        if not mine:
            return ""
        rows = [{"label": title(model), "tag": tag(model), "family": site.families[model["original_run"]]["name"], "href": href(model),
                 "class_key": site.model_class(run_of(model)),
                 "texts": [shown_rate(value(model)) for _, _, value in measures],
                 "bars": [{"value": value(model) or 0.0, "kind": kind} for _, kind, value in measures],
                 "title": f"{label(model)}: {model['dont_know']:,} “{shown_word}” of {model['dont_know'] + model['wrong']:,} "
                          f"not right; {model['right'] + model['wrong']:,} of {total:,} answered, {model['wrong']:,} of them wrong"}
                for model in mine]
        rare = hold.rare_note([(label(model), model["dont_know"], model["non_hallucination"]) for model in mine], total,
                              data["vs_confidence_share"], shown_word, digits) if who == "decision" else ""
        return hold.block(heading, hbars(rows, columns=hold.COLUMNS) + rare + '<p class="chart-legend">'
                          + "".join(f'<span><i class="swatch swatch-{kind}"></i>{name}</span> ' for name, kind, _ in measures)
                          + "</p>")

    with_option = hold.side(
        hold.option_title(shown_word),
        f"“{option}” among the answers that were not right, with it offered as a sixth option on the {total:,} questions; "
        f"beside it the share answered (right + wrong of {total:,}) and the error rate among the answers (wrong of right + "
        "wrong), in the table's order · higher non-hallucination is better, read with the share answered; a model that "
        f"always chose “{option}” would reach 100% with no right answers",
        "".join(option_block(who, heading) for who, heading in hold.kinds(group)))
    confidence = hold.confidence_side(site, [(run_of(model), label(model), href(model)) for model in models], group,
                                      ", in its five-option run on the Text tab")
    first = (f'<figure class="panel chart-card" id="{anchor("chart-non-hallucination", group)}"><div class="chart-head">'
             f'<h2>Non-hallucination, answered and error rate</h2></div>{hold.pair(confidence, with_option)}</figure>')
    second = split_card(
        "chart-confidence", "Saying “I don't know”, or held back by confidence",
        f"Each model's non-hallucination rate with “{option}”, and its five-option run held back by its own confidence at "
        "about the same attempt rate · higher is better; beside them the run with the option's share answered and error "
        "rate among the answers",
        [model for model in rated if model["derived"]["non_hallucination"] is not None],
        lambda mine: [{"label": title(model), "tag": tag(model), "family": site.families[model["original_run"]]["name"], "href": href(model),
                       "class_key": site.model_class(run_of(model)),
                       "texts": [pct(model["non_hallucination"], digits), pct(model["derived"]["non_hallucination"], digits),
                                 pct(model["attempt_rate"], digits), shown_rate(hold.error_rate(model))],
                       "bars": [{"value": model["non_hallucination"], "kind": "lead"},
                                {"value": model["derived"]["non_hallucination"], "kind": "base"}],
                       "title": f"{label(model)}: {pct(model['non_hallucination'], digits)} with “{shown_word}”, "
                                f"{pct(model['derived']['non_hallucination'], digits)} held back by confidence"}
                      for model in mine],
        lambda mine, heading: f'<span><i class="swatch swatch-lead"></i>With “{option}”</span> '
                              '<span><i class="swatch swatch-base"></i>Held back by its own confidence (the derived rate)</span>',
        columns=[(f"Non-hallucination with “{shown_option(data['option'])}”", "With"), ("Held back by confidence", "Held back"),
                 ("Answered", "Ans."), ("Error rate (wrong / answered)", "Error")])
    # The paired test (vs_confidence, decision models only): for each of the group's models in Holm's family (every
    # decision model's, whatever the group shows: family), the wrong answers only one side made, most significant first,
    # with its Holm-adjusted p; the group's decision models outside the family are named under it.
    family = [model for model in data["models"] if model["vs_confidence"] is not None and model["vs_confidence"]["p_holm"] is not None]
    decision = [model for model in models if model["vs_confidence"] is not None]
    tested = sorted((model for model in decision if model["vs_confidence"]["p_holm"] is not None),
                    key=lambda model: (model["vs_confidence"]["p_holm"], model["vs_confidence"]["p"], model["name"].casefold()))
    untested = [label(model) for model in decision if model["vs_confidence"]["p_holm"] is None]
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
            "chart-paired", f"Fewer wrong answers: “{shown_word}” or confidence?",
            f"Each decision model's first run with “{option}” against its five-option run held back by its own confidence on as many "
            f"questions: the questions only one of the two got wrong, by the exact McNemar test with p adjusted by Holm's method "
            f"over the {len(family)} decision models that chose “{option}” on at least {share} of the questions · the shorter bar left "
            "fewer wrong answers",
            [{"label": title(model), "tag": tag(model), "family": site.families[model["original_run"]]["name"], "href": href(model),
              "class_key": site.model_class(run_of(model)),
              "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if model['vs_confidence']['p_holm'] < 0.05 else ''}",
              "bars": [{"value": counts(model)[0], "kind": "lead"}, {"value": counts(model)[1], "kind": "base"}],
              "title": f"{label(model)}: {counts(model)[0]:,} wrong only with “{shown_word}”, {counts(model)[1]:,} wrong only "
                       f"when held back by its own confidence; exact McNemar {bp.p_text(model['vs_confidence']['p'])}, "
                       f"Holm-adjusted {bp.p_text(model['vs_confidence']['p_holm'])}"}
             for model in tested],
            f'<span><i class="swatch swatch-lead"></i>Wrong only with “{option}”</span> '
            '<span><i class="swatch swatch-base"></i>Wrong only when held back by its own confidence</span> '
            f"<span>{verdict}"
            + (f" Not in the test, as they chose “{option}” on fewer than {share} of the questions: {esc(joined(untested))}." if untested else "")
            + (" Chat models are not in this test." if any(model["group"] == "chat" for model in models) else "")
            + "</span>",
            top=4 * quarter, tick=lambda value: f"{value:,.0f}")
    by_accuracy = sorted(models, key=lambda model: (-model["accuracy"], model["name"].casefold()))

    def accuracy_rows(mine: list[dict[str, Any]]) -> list[dict[str, Any]]:
        accuracies = [model["accuracy"] for model in mine]
        return [{"label": title(model), "tag": tag(model), "family": site.families[model["original_run"]]["name"], "href": href(model),
                 "class_key": site.model_class(run_of(model)),
                 "text": pct(model["accuracy"], digits),
                 "bars": [{"value": model["accuracy"], "colour": rank_fill(stops, model["accuracy"], min(accuracies), max(accuracies))}],
                 "marker": model["original_accuracy"],
                 "title": f"{label(model)}: {model['right']:,} of {total:,} right; {pct(model['original_accuracy'], digits)} with five options"}
                for model in mine]

    def accuracy_legend(mine: list[dict[str, Any]], heading: str) -> str:
        accuracies = [model["accuracy"] for model in mine]
        return (scale_legend(stops, pct(min(accuracies), digits), pct(max(accuracies), digits), who=heading)
                + ' <span><i class="swatch swatch-marker"></i>The same model with five options (the Text tab)</span>')

    third = split_card("chart-accuracy", f"Accuracy with “{shown_word}”",
                       f"Share of the {total:,} questions answered right with “{option}” on offer · higher is better",
                       by_accuracy, accuracy_rows, accuracy_legend)
    return f'<section class="charts" aria-label="Charts" {shown(group)}>{first}{second}{paired}{third}</section>'


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
    label = lambda model: site.plain(run_of(model))  # noqa: E731
    rows = [model for model in option_word_rows(site, data, word)
            if model["i_dont_know"]["non_hallucination"] is not None and model["bilmiyorum"]["non_hallucination"] is not None]
    side = lambda model, key: model[key]  # noqa: E731
    chart = hbars([
        {"label": site.title(run_of(model)), "tag": site.tag(run_of(model)), "family": site.families[model["original_run"]]["name"],
         "href": rel(PATH, site.model_path(run_of(model))),
         "class_key": site.model_class(run_of(model)),
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
    percent = lambda value: '<span class="nm">Undefined</span>' if value is None else pct(value, digits)  # noqa: E731
    sides = (("i_dont_know", new), ("bilmiyorum", old))
    words = (word["option"], data["option"])
    # Each word's three measures side by side, “I don't know” first, so a phone's first view of the frame shows them
    # with the model (Ümit #4665).
    heads = (tuple(head for text in words for head in (
                (f"Non-hallucination with “{text}”", f"of answers not right, % “{text}” · higher is better"),
                (f"Answered with “{text}”", f"not “{text}”: (right + wrong) / {total:,}"),
                (f"Error rate with “{text}”", "of its answers: wrong / (right + wrong) · lower is better")))
             + tuple((f"Accuracy with “{text}”", "higher is better") for text in words)
             + (("Wrong only with one word", "exact McNemar, Holm-adjusted"), ("Runs", "run, start date and prompt version")))
    labels = [f"{head} ({direction})" for head, direction in heads]
    rate = lambda counts, option: (f'{percent(counts["non_hallucination"])}<span class="small">{counts["dont_know"]:,} '  # noqa: E731
                                   f'“{option}” of {counts["dont_know"] + counts["wrong"]:,} not right</span>')
    right = lambda counts: f'{percent(counts["accuracy"])}<span class="small">{counts["right"]:,} of {total:,} right</span>'  # noqa: E731
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
        values = ([item for side, text in sides for item in (rate(model[side], text), answered(model[side], text),
                                                              wrong_cell(model[side], digits))]
                  + [right(model[side]) for side, _ in sides]
                  + [test, runs])
        rows.append(f"{model_tr(site, model)}{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>' for name, direction in heads)
    return f"""
    <section class="card" id="option-word-results">
      <h2>Results with “{new}” instead of “{old}”</h2>
      <p class="note">In the tab's order. Each row shows the model's first run with each word on the same {total:,} questions; the “{old}” run is the one in the table above. With “{new}”, then with “{old}”: the non-hallucination rate (the option / (the option + wrong)), Answered = (right + wrong) / {total:,} and the error rate = wrong / (right + wrong); then accuracy with each. Wrong only with one word: the questions only one of the two runs got wrong, by the exact McNemar test, with p adjusted by Holm's method over the models compared; * marks a Holm-adjusted p below 0.05.</p>
      <div class="table-wrap"><table class="board list stack idk idk-lead"><thead><tr><th scope="col">Model</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
      {not_run(word["not_run"])}
    </section>
    <section class="card method-notes" id="option-word-method">
      <h2>Our method with “{new}”</h2>
      <p>Only two things changed from the runs above: the sixth option's word and the sentence of the System One instructions that names it. The option “{old}” became “{new}”, and the sentence “{esc(data["sentence"])}” became “{esc(word["sentence"])}” Everything else is as above: the same {total:,} Turkish questions and answer key, the option always last and never correct, one question per request and each model's own settings. The full instructions:</p>
      <blockquote><p>{esc(word["instructions"])}</p></blockquote>
      <p>Prompt version {esc(word["prompt_version"])} with “{new}”, against {esc(data["prompt_version"])} with “{old}”. One full run per model with “{new}”; the table gives each run's ID and start date (UTC).</p>
      <h3>How to read the comparison</h3>
      <p>A model that did not recognise the Turkish word and so ignored the option should choose the English one more often, and its non-hallucination rate should rise. A model that chooses both about as often did not skip “{old}” for its word. The rates are those above, and the same limits hold: the non-hallucination rate says how a model is wrong, not how often it is right, and it is not a direct measure of what the model does not know; read it with accuracy and the attempt rate, as a model that always chose the option would reach 100% with no right answers. With neither a wrong answer nor the option, the rate is undefined.</p>
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
                                                          if model["vs_confidence"]["p_holm"] is not None and model["name"] in own):
        raise fail("Holm's family is not the option-word models of the tab's own comparison with confidence")


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
    label = lambda model: site.plain(run_of(model))  # noqa: E731
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
        [{"label": site.title(run_of(model)), "tag": site.tag(run_of(model)), "family": site.families[model["original_run"]]["name"],
          "href": rel(PATH, site.model_path(run_of(model))),
          "class_key": site.model_class(run_of(model)),
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
        rows.append(f"{model_tr(site, model)}{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
    family = word["vs_confidence"]["family"]
    outside = [site.plain(site.by_id[model["original_run"]]) for model in vs_confidence_rows(site, data, word) if model["p_holm"] is None]
    glide = [model for model in word["vs_confidence"]["models"] if model["replaces_run"] is not None]
    glide_text = "".join(
        f" For {esc(site.plain(site.by_id[model['replaces_run']]))}, the five-option run is {model['five_option_run']}, not the Text tab's run "
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
    option = esc(shown_option(data["option"]))
    old = site.by_id[rerun["replaces_run"]]
    name = esc(site.plain(old))
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
        (f"With “{shown_option(data['option'])}”, run {model['run']}", model["non_hallucination"], "lead"),
        (f"Confidence, new run {rerun['run']}", new_derived["non_hallucination"], "base"),
        (f"Confidence, run {old['run']} (as published)", old_derived["non_hallucination"], "base"),
    ]
    chart = hbars([{"label": label, "text": pct(value, digits), "bars": [{"value": value, "kind": kind}],
                    "title": f"{site.plain(old)}: {label}, {pct(value, digits)}"} for label, value, kind in rows if value is not None])
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
    option = esc(shown_option(data["option"]))
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
      <p class="note">Both against {esc(site.plain(old))}'s first run with “{option}”, run {model["run"]}. Run {old["run"]} is the Text tab's run and the row in the table above; run {rerun["run"]} is new and replaces it here only.</p>
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
    # Each language's three measures side by side, English (the section's runs) first, so a phone's first view of the
    # frame shows them with the model (Ümit #4665).
    heads = (("English non-hallucination", f"of answers not right, % “{option}” · higher is better; right / wrong / option"),
             ("Answered in English", f"not “{option}”: (right + wrong) / {total:,}"),
             ("Error rate in English", f"with “{option}”, of its answers: wrong / (right + wrong) · lower is better"),
             ("Turkish non-hallucination", "of answers not right, % the Turkish option · higher is better; right / wrong / option"),
             ("Answered in Turkish", f"not the Turkish option: (right + wrong) / {total:,}"),
             ("Error rate in Turkish", "with the Turkish option, of its answers: wrong / (right + wrong) · lower is better"),
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
        values = [rate(entry["english"]), answered_cell(entry["english"], total, digits), wrong_cell(entry["english"], digits),
                  rate(entry["turkish"]), answered_cell(entry["turkish"], total, digits), wrong_cell(entry["turkish"], digits),
                  f"{model['english_only_wrong']:,}",
                  f"{model['turkish_only_wrong']:,}", p(model["p"]),
                  p(model["p_holm"]) + (" *" if model["p_holm"] < 0.05 else "")]
        detail = site.detail(run)
        tip = f' title="{esc(detail)}"' if detail else ""
        rows += (f'<tr{site.class_attribute(run)}><td class="model"{tip}>{site.icon(run)}<a class="model-name" href="{er.idk_href(site, entry)}">{esc(site.title(run))}</a>{tag_html(site.tag(run))} {site.label(run)}</td>'
                 + "".join(cell(f"{head} ({note})", item) for (head, note), item in zip(heads, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
    significant = [entry for model, entry in pairs if model["p_holm"] < 0.05]
    smallest = min(pairs, key=lambda pair: (pair[0]["p_holm"], pair[0]["p"]))
    words = bp.in_words(count)
    if significant:
        verdict = (f"{bp.in_words(len(significant)).capitalize()} of the {words} differences in wrong answers "
                   f"{'is' if len(significant) == 1 else 'are'} significant with Holm's correction over the {words} "
                   f"(adjusted p below 0.05): {joined([esc(site.plain(site.by_id[entry['text_run']])) for entry in significant])}.")
    else:
        verdict = (f"None of the {words} differences in wrong answers is significant with Holm's correction over the "
                   f"{words} (adjusted p below 0.05); the smallest adjusted p is "
                   f"{esc(site.plain(site.by_id[smallest[1]['text_run']]))}'s, {esc(bp.p_text(smallest[0]['p_holm']))}.")
    return (f'<section class="card" id="english-option-four"><h2>The four models of the request: Holm\'s correction over '
            f"the four</h2><p>{joined([esc(site.plain(site.by_id[entry['text_run']])) for _, entry in pairs])}, as Ümit's follow-up of "
            f"2 November 2026 asked: each model's first run in English and in Turkish, each with the “{esc(option)}” option in "
            f"its language, on the {four['questions']:,} kept questions, and the exact McNemar test of wrong answers, with p "
            f"adjusted by Holm's method over these {words}. {verdict} The charts below and the "
            f'<a href="{rel(PATH, "turkish-vs-english/")}#dont-know">Turkish vs English tab</a> correct over all '
            f"{len(idk['models'])} compared models.</p>"
            f'<div class="table-wrap"><table class="board list stack idk idk-lead"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f'</thead><tbody>{rows}</tbody></table></div><p class="note">In English, then in Turkish: the non-hallucination '
            f"rate with its counts (right / wrong / option), Answered = (right + wrong) / {total:,} and the error rate = "
            f"wrong / (right + wrong). * marks a Holm-adjusted p below 0.05 over the {words}.</p></section>")


def english_option_face(site: Site, idk: dict[str, Any], four: dict[str, Any] | None) -> str:
    """The English-option comparison on this tab's face: the Turkish vs English tab's kept reading questions in English
    with “I don't know” against the same models' “Bilmiyorum” answers in Turkish, its summary, the four models of Ümit's
    follow-up with Holm over the four (when results.json has dont_know_english_option) and its two charts as that tab
    draws them (sitebuild/english_reading.py), every number from results.json."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    option, total = esc(idk["option"]), idk["questions"]
    return (f'<section class="card" id="english-option"><h2>The English questions: the English option against the Turkish '
            f"option</h2><p>The {total:,} reading questions of the "
            f'<a href="{rel(PATH, "turkish-vs-english/")}">Turkish vs English tab</a>, in English with a sixth option, '
            f"“{option}”, against the same models' answers with the Turkish option on the same questions in Turkish (this tab's runs "
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
      <p class="note">Each model's first run in English and in Turkish, each with the “{option}” option in its language, on the {idk["questions"]:,} kept reading questions: the counts, the rates and the exact McNemar test of wrong answers, with p adjusted by Holm's method over the {len(idk["models"])} models; * marks a Holm-adjusted p below 0.05. The same table is on the <a href="{rel(PATH, "turkish-vs-english/")}#dont-know">Turkish vs English tab</a>.</p>
      {er.dont_know_table(site, idk)}
    </section>"""


# The same number of answers (results.json dont_know_same_answers): one colour per setup in both plots, by Text tab run,
# the Turkish vs English tab's colours for its setups (english_reading model_colours), then these for the models only
# in the Turkish family, whose lines are dashed (SAME_EXTRA_DASH) to tell them from the English reading setups;
# mid lightness, readable on both themes' panels.
SAME_EXTRA_COLOURS = ("#a1478f", "#b04a4a", "#2a8f8f")
SAME_EXTRA_DASH = "6 3"
# The drawn polyline skips vertices closer than this share of coverage to the previous one drawn.
SAME_MIN_STEP = 0.0025
# The summary names the models of a verdict up to this many (otherwise it counts them), and the models that keep fewer
# wrong answers than the reference without a significant difference up to SAME_NAMED_FEWER.
SAME_NAMED = 6
SAME_NAMED_FEWER = 3
# The small plots of every setup's curve (same_curves): each one's size and margins in SVG units (width, height, left,
# right, top, bottom), the one colour of every setup's line and markers there (the reference's line is dashed grey),
# and their thinning step, one vertex per 1% of coverage.
SAME_SMALL = (240, 160, 34, 8, 8, 22)
SAME_SMALL_COLOUR = "#d9622b"
SAME_SMALL_STEP = 0.01


def same_wrong_text(wrong: float) -> str:
    """A wrong count of the k answers, a whole number (check_same_answers stops the build otherwise)."""
    return f"{wrong:,.0f}"


def same_short(model: dict[str, Any]) -> bool:
    """Whether a model is left out of its family's test: a five-option run other than the reference's with fewer than k
    scored answers keeps no k answers (check_same_answers allows it only so, every number null)."""
    return model["wrong"] is None and not model["reference"]


def same_left_out(site: Site, family: dict[str, Any]) -> str:
    """The family's left-out models (same_short), each named once with its scored answers and k; empty when none."""
    return "; ".join(f"{esc(same_label(site, model, family))} is left out: its run has {len(model['wrong_by_rank']):,} "
                     f"scored answers, fewer than k = {family['k']:,}" for model in family["models"] if same_short(model))


def same_families(site: Site, same: dict[str, Any]) -> list[dict[str, Any]]:
    """dont_know_same_answers' two families with their language, each model marked as the reference or not and with its
    curve as (answered, wrong) points, one per k from 1 to the run's scored answers, from its wrong_by_rank (one
    character per answer in selection order, "1" wrong): the point at k counts the "1" in the first k. The Turkish
    reference is the setup of the tab's row named as the reference; the English one, the model of that name."""
    tab = {model["name"]: model["original_run"] for model in site.results["dont_know"]["models"]}
    families = []
    for key, language in (("turkish", "Turkish"), ("english", "English")):
        family = dict(same[key], key=key, language=language, models=[])
        for model in same[key]["models"]:
            reference = (model["text_run"] == tab.get(same["reference"]) if key == "turkish"
                         else model["name"] == same["reference"])
            curve = list(enumerate(itertools.accumulate(int(mark == "1") for mark in model["wrong_by_rank"]), 1))
            family["models"].append(dict(model, reference=reference, curve=curve, points=model.get("points"),
                                         replaces_run=model.get("replaces_run")))
        families.append(family)
    return families


def check_same_answers(site: Site, data: dict[str, Any], word: dict[str, Any] | None, families: list[dict[str, Any]],
                       reference: str) -> None:
    """Stop the build when dont_know_same_answers does not fit the tab: the Turkish family is every main run of the Text
    tab in results.json's order, each through that run (hosted GLiDE too), with markers exactly for the tab's models;
    the English family is its section's models, each through its first English run; k is the reference's run with the
    option's answered count there; the markers are those sections' counts; every count is whole; each wrong_by_rank has
    one 0 or 1 per scored answer of its run and counts the published wrong in its first k; and the differences and p
    values fit. A run other than the reference's with fewer than k scored answers has every number null (same_short).
    """
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    fail = lambda text: SystemExit(f"results.json dont_know_same_answers: {text}")  # noqa: E731
    english = site.results["english_reading"]
    idk = english["dont_know"]
    # The decision models' runs with the option are the markers; the chat models' stay out of this comparison.
    by_text = {model["text_run"]: model for model in idk["models"] + er.english_only(idk) if model["group"] == "decision"}
    tab = {model["original_run"]: model for model in data["models"]}
    own = {model["name"]: model for model in (word or {}).get("models", [])}
    runs = {item["run"]: item for value in site.answers.values() if isinstance(value, list)
            for item in value if isinstance(item, dict) and "score" in item and "run" in item}
    kept_ids = {question["question_id"] for question in json.loads(er.RECORD.read_text())["questions"] if question["kept"]}
    positions = {"turkish": site.scored,
                 "english": [index for index, value in enumerate(site.answers["questions"]["id"]) if value in kept_ids]}
    for family in families:
        key, models, k = family["key"], family["models"], family["k"]
        if key == "turkish":
            if [model["text_run"] for model in models] != [run["run"] for run in site.runs]:
                raise fail("turkish: the models are not the Text tab's main runs, in results.json's order")
            if any(model["name"] != site.by_id[model["text_run"]]["name"] for model in models if model["text_run"] not in tab):
                raise fail("turkish: a name is not its Text tab run's")
            questions = data["questions"]
            ref = own.get(reference, {}).get("i_dont_know")
            wording = word["option"] if word else None
        else:
            if [model["name"] for model in models] != [model["name"] for model in english["models"]]:
                raise fail("english: the models are not its section's, in its order")
            questions = idk["questions"]
            ref_text = next((model["text_run"] for model in models if model["reference"]), None)
            ref = by_text.get(ref_text, {}).get("english")
            wording = idk["option"]
        refs = [model for model in models if model["reference"]]
        if len(refs) != 1 or refs[0]["name"] != reference:
            raise fail(f"{key}: not exactly one row of {reference}")
        if family["questions"] != questions or len(positions[key]) != questions:
            raise fail(f"{key}: {family['questions']} questions, its section {questions}")
        if not ref or ref["run"] != family["k_run"] or ref["right"] + ref["wrong"] != k or family["k_wording"] != wording:
            raise fail(f"{key}: k is not the answered count of {reference}'s run {family['k_run']} with “{wording}”")
        for position, model in enumerate(models):
            name = model["name"]
            if key == "turkish":
                row = tab.get(model["text_run"])
                if (model["points"] is None) != (row is None):
                    raise fail(f"{name}: markers belong to the tab's models only")
                if row and name != row["name"]:
                    raise fail(f"{name}: not the tab's name {row['name']} for run {model['text_run']}")
                if model["replaces_run"] is not None or model["five_option_run"] != model["text_run"]:
                    raise fail(f"{name}: the five-option run is not the Text tab's run {model['text_run']}")
                sides = [] if row is None else \
                    [(data["option"], row)] + ([(word["option"], own[name]["i_dont_know"])] if name in own else [])
            else:
                section = english["models"][position]
                if model["five_option_run"] != section["run"]:
                    raise fail(f"{name}: the five-option run is not the first English run {section['run']}")
                entry = by_text.get(model["text_run"])
                sides = [] if entry is None else [(wording, entry["english"])]
            points = [{"wording": text, "run": counts["run"], "answered": counts["right"] + counts["wrong"],
                       "wrong": counts["wrong"]} for text, counts in sides]
            if (model["points"] or []) != points:
                raise fail(f"{name}: the markers are not its runs with the option")
            run = runs.get(model["five_option_run"])
            scored = None if run is None else sum(1 for index in positions[key]
                                                  if run["score"][index] is not None and run["choice"][index] is not None)
            if scored is None:
                raise fail(f"{name} {key}: run {model['five_option_run']} is not in answers.json")
            if scored < k:
                if model["reference"] or any(model[field] is not None for field in
                                             ("wrong", "wrong_of_answers", "difference", "interval", "p", "p_holm")):
                    raise fail(f"{name} {key}: run {model['five_option_run']} has fewer than k = {k:,} scored answers, "
                               "yet it is the reference or has a number")
                ranks = model["wrong_by_rank"]
                if len(ranks) != scored or set(ranks) - {"0", "1"}:
                    raise fail(f"{name} {key}: wrong_by_rank is not one 0 or 1 per scored answer of run "
                               f"{model['five_option_run']} ({scored:,})")
                continue
            if not float(model["wrong"]).is_integer() or not 0 <= model["wrong"] <= k \
                    or abs(model["wrong"] / k - model["wrong_of_answers"]) > 1e-12:
                raise fail(f"{name} {key}: the wrong count is not a whole number of the k, or the rate not wrong / k")
            ranks = model["wrong_by_rank"]
            if len(ranks) != scored or set(ranks) - {"0", "1"}:
                raise fail(f"{name} {key}: wrong_by_rank is not one 0 or 1 per scored answer of run "
                           f"{model['five_option_run']} ({scored:,})")
            if ranks[:k].count("1") != model["wrong"]:
                raise fail(f"{name} {key}: wrong_by_rank's count at k = {k:,} is not the published wrong count")
            if model["reference"]:
                if any(model[field] is not None for field in ("difference", "interval", "p", "p_holm")):
                    raise fail(f"{key}: the reference row has a difference or p")
                continue
            if model["difference"] is None or abs(model["difference"] - (model["wrong_of_answers"] - refs[0]["wrong_of_answers"])) > 1e-12:
                raise fail(f"{name} {key}: the difference is not its rate minus {reference}'s")
            if model["p"] is None or model["p_holm"] is None or not 0 <= model["p"] <= model["p_holm"] <= 1 \
                    or not model["interval"] or model["interval"][0] > model["interval"][1]:
                raise fail(f"{name} {key}: p {model['p']}, Holm p {model['p_holm']} or the interval do not fit")


def same_label(site: Site, model: dict[str, Any], family: dict[str, Any] | None = None) -> str:
    """A model's name and tag as plain text (Site.plain of its Text tab run); within a family where another entry reads
    the same, with its run, so setups of one model stay apart in the prose (the tables give each setup's detail)."""
    label = site.plain(site.by_id[model["text_run"]])
    if family and sum(1 for other in family["models"] if site.plain(site.by_id[other["text_run"]]) == label) > 1:
        label += f" (run {model['text_run']})"
    return label


def same_unit(family: dict[str, Any], count: int) -> str:
    """What a family's entries are: the Turkish family is the Text tab's setups, the English one models."""
    noun = "setup" if family["key"] == "turkish" else "model"
    return noun if count == 1 else noun + "s"


def same_groups(site: Site, family: dict[str, Any]) -> list[tuple[list[dict[str, Any]], str, str, bool]]:
    """The family's other models in the groups its verdicts are told by: in Turkish the Text tab's leaderboard groups
    (decision models, then chat and general models, by site.decision), in English one group. Each: the members other
    than the reference and those left out (same_short), the noun for one and for several, and whether the reference belongs to it."""
    others = [model for model in family["models"] if not model["reference"] and not same_short(model)]
    if family["key"] != "turkish":
        return [(others, "model", "models", True)]
    decision = lambda model: site.decision(site.by_id[model["text_run"]])  # noqa: E731
    ref = next(model for model in family["models"] if model["reference"])
    groups = [([model for model in others if decision(model)], "decision model", "decision models", decision(ref)),
              ([model for model in others if not decision(model)], "chat and general model", "chat and general models",
               not decision(ref))]
    return [group for group in groups if group[0]]


def same_split(models: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The models with significantly fewer wrong answers than the reference after Holm, with significantly more, and
    the rest."""
    better = [model for model in models if model["p_holm"] < 0.05 and model["difference"] < 0]
    worse = [model for model in models if model["p_holm"] < 0.05 and model["difference"] > 0]
    return better, worse, [model for model in models if model not in better and model not in worse]


def same_group_text(site: Site, family: dict[str, Any], group: tuple[list[dict[str, Any]], str, str, bool],
                    ref: dict[str, Any], reference: str, lead: bool) -> str:
    """One group's verdict for the summary: how many keep significantly fewer or more wrong answers than the reference,
    by how many points, named when few, and the rest that could be chance; lead names the group first (when a family
    has more than one)."""
    digits = site.config["percent_digits"]
    members, one, many, own = group
    count = len(members)
    noun = f"{'other ' if own else ''}{one if count == 1 else many}"
    label = lambda model: esc(same_label(site, model, family))  # noqa: E731
    names = lambda models: f" ({joined([label(model) for model in models])})" if len(models) <= SAME_NAMED else ""  # noqa: E731
    points = lambda values: (f"{min(values):.{digits}f} to {max(values):.{digits}f} points" if len(values) > 1  # noqa: E731
                             else f"{values[0]:.{digits}f} points")
    keep = lambda models: "keeps" if len(models) == 1 else "keep"  # noqa: E731
    better, worse, rest = same_split(members)
    if len(worse) == count:
        closest = min(members, key=lambda model: model["wrong_of_answers"])
        return (f"{'the' if count == 1 else f'all {count}'} {noun} {keep(members)} significantly more wrong answers, "
                f"{points([100 * model['difference'] for model in worse])} more (the closest, {label(closest)}, "
                f"{pct(closest['wrong_of_answers'], digits)})" + (f", so {esc(reference)} keeps the fewest of the {many}"
                                                                 if own else ""))
    if not better and not worse:
        return f"none of the {count} {noun} differs significantly"
    parts = []
    if better:
        parts.append(f"{len(better)}{names(better)} {keep(better)} significantly fewer, "
                     f"{points([-100 * model['difference'] for model in better])} fewer")
    if worse:
        parts.append(f"{len(worse)}{names(worse)} {keep(worse)} significantly more, "
                     f"{points([100 * model['difference'] for model in worse])} more")
    if rest:
        fewer = [model for model in rest if model["difference"] < 0]
        than = f"fewer than {same_wrong_text(ref['wrong'])} but not significantly"
        listed, aside = "", ""
        if len(rest) <= SAME_NAMED:
            # The rest named, each with its wrong count; then how many of them keep fewer than the reference.
            listed = " (" + joined([f"{label(model)} with {same_wrong_text(model['wrong'])}" for model in rest]) + ")"
            if fewer and len(fewer) == len(rest):
                aside = f", {'it keeps' if len(rest) == 1 else 'both keep' if len(rest) == 2 else 'all keep'} {than}"
            elif fewer:
                aside = f", {len(fewer)} of them keeping {than}"
        elif fewer and len(fewer) <= SAME_NAMED_FEWER:
            aside = "; " + joined([f"{label(model)} keeps {same_wrong_text(model['wrong'])}, {than}" for model in fewer])
        elif fewer:
            aside = f"; {len(fewer)} of them keep {than}"
        parts.append(f"for {len(rest)}{listed} the difference could be chance{aside}")
    return (f"of the {count} {noun}, " if lead else "") + joined(parts)


def same_summary(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """The section's summary from dont_know_same_answers: for each family, k and where it comes from, the reference's
    wrong of answers and, group by group, how many models differ significantly from it after Holm, the rest chance."""
    digits = site.config["percent_digits"]
    reference = same["reference"]
    texts = []
    for family in families:
        k, models = family["k"], family["models"]
        ref = next(model for model in models if model["reference"])
        count = sum(1 for model in models if not model["reference"] and not same_short(model))
        left_out = same_left_out(site, family)
        where = (f"the {family['questions']:,} questions" if family["key"] == "turkish" else
                 f"the {family['questions']:,} kept reading questions")
        text = (f"In {family['language']}, k = {k:,}, the answers of {esc(reference)}'s run {family['k_run']} with "
                f"“{esc(family['k_wording'])}” on {where}: {esc(reference)}'s five-option run (run {ref['five_option_run']}) "
                f"keeps {same_wrong_text(ref['wrong'])} wrong of {k:,} ({pct(ref['wrong_of_answers'], digits)})")
        grouped = same_groups(site, family)
        groups = [same_group_text(site, family, group, ref, reference, len(grouped) > 1) for group in grouped]
        texts.append(f"{text}; after Holm's correction over the other {count} {same_unit(family, count)}, "
                     + "; ".join(groups) + "." + (f" {left_out[0].upper()}{left_out[1:]}." if left_out else ""))
    return (f"<p>Each model's five-option run keeps only its k most confident answers, k being the number of questions "
            f"{esc(reference)} answered with “I don't know” on offer, and we count the wrong ones among them. "
            + " ".join(texts) + "</p>")


def same_colours(site: Site, families: list[dict[str, Any]]) -> dict[int, tuple[str, str | None]]:
    """One colour per setup across both plots, by Text tab run, with its line's dash: the Turkish vs English tab's
    colours for its setups (solid), then the extra ones (dashed)."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    colours: dict[int, tuple[str, str | None]] = {run: (colour, None) for run, colour in er.model_colours(site).items()}
    extra = iter(SAME_EXTRA_COLOURS)
    for family in families:
        for model in same_plotted(family):
            if model["text_run"] not in colours:
                colour = next(extra, None)
                if colour is None:
                    raise SystemExit("results.json dont_know_same_answers: more models than colours")
                colours[model["text_run"]] = (colour, SAME_EXTRA_DASH)
    return colours


def same_plotted(family: dict[str, Any]) -> list[dict[str, Any]]:
    """The family's models drawn in its plot: in Turkish the tab's models (those with runs with the option), in English
    all."""
    return [model for model in family["models"] if family["key"] != "turkish" or model["points"] is not None]


def same_drawn(curve: list[tuple[int, int]], k: int, total: int, step: float) -> list[tuple[int, int]]:
    """The curve's vertices to draw: the first, the last and the point at k (when the curve reaches k), and between them each point at least step
    of coverage (a share of total) past the previous one drawn; every vertex is a curve point."""
    at_k = next((index for index, (answered, _) in enumerate(curve) if answered >= k), None)
    drawn, last = [0], curve[0][0]
    for index in range(1, len(curve)):
        if index in (at_k, len(curve) - 1) or (curve[index][0] - last) / total >= step:
            drawn.append(index)
            last = curve[index][0]
    return [curve[index] for index in drawn]


def same_engine(site: Site, family: dict[str, Any], model: dict[str, Any]) -> str:
    """For hosted GLiDE in Turkish (hosted_glide_rerun's replaced run), where its runs with the option and its five-option
    run come from different engines, the words that say so; otherwise empty."""
    rerun = site.results.get("hosted_glide_rerun")
    if family["key"] != "turkish" or not rerun or model["text_run"] != rerun["replaces_run"]:
        return ""
    return f"made with Fastino's engine glide_v2, not run {model['five_option_run']}'s glide"


def same_plot(site: Site, same: dict[str, Any], family: dict[str, Any], colours: dict[int, tuple[str, str | None]]) -> str:
    """One family's risk-coverage plot: each model's five-option curve as a line from its first point (1 answer) to its
    last (its run's scored answers), its own runs with the option as markers and a dashed guide at k."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    digits = site.config["percent_digits"]
    total, k, language, reference = family["questions"], family["k"], family["language"], same["reference"]
    guide = f"k = {k:,}: {reference}'s answers with “{family['k_wording']}”"
    plotted = same_plotted(family)
    values = [point["wrong"] / point["answered"] for model in plotted for point in model["points"] if point["answered"]]
    values += [wrong / answered for model in plotted for answered, wrong in model["curve"] if answered / total >= 0.01]
    y_top = max(0.04, math.ceil(100 * max(values, default=0.04) / 4 - 1e-9) * 4 / 100)
    series, legend = [], []
    for model in plotted:
        (colour, dash), name, curve = colours[model["text_run"]], same_label(site, model, family), model["curve"]
        line = [(answered / total, wrong / answered, "") for answered, wrong in same_drawn(curve, k, total, SAME_MIN_STEP)]
        series.append({"colour": colour, "dash": dash, "line": True, "points": line,
                       "title": f"{name}: five options, run {model['five_option_run']}, held back by confidence, from 1 to "
                                f"{curve[-1][0]:,} answers; "
                                + (f"left out: fewer than k = {k:,} scored answers" if same_short(model) else
                                   f"its {k:,} most confident answers: "
                                   f"{same_wrong_text(model['wrong'])} wrong ({pct(model['wrong_of_answers'], digits)})")})
        keys = [f"{legend_mark(colour, dash=dash)} five options, run {model['five_option_run']}"]
        engine = same_engine(site, family, model)
        engine = f"; {engine}" if engine else ""
        for point in model["points"]:
            shape = er.SHAPES[point["wording"]]
            tip = (f"{name}: “{point['wording']}”, run {point['run']}: {point['answered']:,} answered "
                   f"({pct(point['answered'] / total, digits)}), {point['wrong']:,} wrong "
                   f"({'undefined, no answers' if not point['answered'] else pct(point['wrong'] / point['answered'], digits)}){engine}")
            series.append({"colour": colour, "shape": shape, "title": tip,
                           "points": [(point["answered"] / total, point["wrong"] / point["answered"] if point["answered"] else 0, tip)]})
            keys.append(f"{legend_mark(colour, shape)} “{esc(point['wording'])}”, run {point['run']}")
        legend.append(f"<li><b>{esc(name)}</b>: {' · '.join(keys)}"
                      + (f" (runs {joined([str(point['run']) for point in model['points']])}{esc(engine.removeprefix(';'))})"
                         if engine else "") + "</li>")
    shapes = " ".join(f"{legend_mark('var(--text-2)', er.SHAPES[wording])} “{esc(wording)}”"
                      for wording in dict.fromkeys(point["wording"] for model in plotted for point in model["points"]))
    dash = ('<svg width="20" height="14" viewBox="0 0 20 14" aria-hidden="true" style="vertical-align:middle">'
            '<line x1="10" y1="1" x2="10" y2="13" stroke="var(--text-2)" stroke-width="1.5" stroke-dasharray="3 2"/></svg>')
    title = f"The same number of answers in {language}"
    where = "questions" if family["key"] == "turkish" else "kept reading questions"
    return (f'<figure class="panel chart-card" id="chart-same-answers-{family["key"]}"><div class="chart-head">'
            f'<h2>{esc(title)}</h2><p class="chart-sub">The {total:,} {where} in {language}: each model\'s five-option run '
            f"answering only its most confident answers (the line), and its own runs with the option (the marker: {shapes})"
            + (f"; the table under Info has all {len(family['models'])} {same_unit(family, len(family['models']))}, the plot "
               f"the {len(plotted)} with runs with the option (<a href=\"#same-answers-curves\">every setup's curve under "
               "Info</a>)" if len(plotted) < len(family["models"]) else "")
            + " · lower is better at the same coverage</p></div>"
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
        ref = next(model for model in family["models"] if model["reference"])
        verdicts = []
        for members, one, many, own in same_groups(site, family):
            count = len(members)
            noun = f"{'other ' if own else ''}{one if count == 1 else many}"
            better, worse, rest = same_split(members)
            if len(worse) == count:
                verdicts.append(f"{'the' if count == 1 else f'all {count}'} {noun} had significantly more wrong answers")
            elif not better and not worse:
                verdicts.append(f"none of the {count} {noun} differed significantly")
            else:
                items = [f"{len(better)} had significantly fewer"] if better else []
                if worse:
                    items.append(f"{len(worse)} {'' if items else 'had '}significantly more")
                if rest:
                    items.append(f"{len(rest)} could be chance")
                verdicts.append(f"of the {count} {noun}, {joined(items)}")
        left_out = same_left_out(site, family)
        parts.append(f"in {family['language']}, " + ", while ".join(verdicts) + (f" ({left_out})" if left_out else ""))
        levels.append(f"{pct(ref['wrong_of_answers'], digits)}{'' if levels else ' of its k answers wrong'} in {family['language']}")
        ks.append(f"{family['k']:,} in {family['language']}")
    return (f"<p>Held to {esc(reference)}'s number of answers with “I don't know” (k = {joined(ks)}), each model keeping "
            f"its k most confident five-option answers, {esc(reference)}'s five-option run got {joined(levels)}; by "
            f"a paired bootstrap with Holm's correction, {'; '.join(parts)} "
            '(<a href="#same-answers">The same number of answers</a>).</p>')


def same_board_groups(site: Site, family: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The family's models as its table and small plots show them: in Turkish grouped as the Text tab's leaderboard
    groups its setups (decision models, then chat and general models), in English one group without a title; each by
    wrong of the k answers, fewest first, those left out (same_short) last."""
    def order(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(models, key=lambda model: (same_short(model), model["wrong_of_answers"] or 0, same_label(site, model).casefold(), model["text_run"]))

    if family["key"] != "turkish":
        return [("", order(family["models"]))]
    groups = []
    for title, decision in (("Decision models", True), ("Other models: chat and general models", False)):
        members = [model for model in family["models"] if site.decision(site.by_id[model["text_run"]]) == decision]
        if members:
            groups.append((title, order(members)))
    return groups


def same_curves(site: Site, same: dict[str, Any], family: dict[str, Any]) -> str:
    """Under Info: one small static plot per setup of the family, on the same axes, each with its curve (thinned to one
    vertex per SAME_SMALL_STEP of coverage, every vertex a curve point), the reference's curve dashed (one polyline
    defined once and reused), the guide at k and its runs with the option as markers, with a caption of its numbers."""
    from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
    digits = site.config["percent_digits"]
    width, height, left, right, top, bottom = SAME_SMALL
    plot_w, plot_h = width - left - right, height - top - bottom
    total, k, key, reference = family["questions"], family["k"], family["key"], same["reference"]
    ref = next(model for model in family["models"] if model["reference"])
    values = [wrong / answered for model in family["models"] for answered, wrong in model["curve"] if answered / total >= 0.01]
    values += [point["wrong"] / point["answered"] for model in family["models"] for point in model["points"] or []
               if point["answered"]]
    # The same y axis in every small plot: up to the largest share wrong shown, rounded up to a multiple of 4 points.
    y_top = max(0.04, math.ceil(100 * max(values) / 4 - 1e-9) * 4 / 100)
    px = lambda x: left + plot_w * min(max(x, 0.0), 1.0)  # noqa: E731
    py = lambda y: top + plot_h * (1 - min(max(y, 0.0), y_top) / y_top)  # noqa: E731
    points = lambda curve: " ".join(f"{px(answered / total):.1f},{py(wrong / answered):.1f}"  # noqa: E731
                                    for answered, wrong in same_drawn(curve, k, total, SAME_SMALL_STEP))
    text = 'style="font:10px var(--sans);fill:var(--text-2)"'
    frame = "".join(
        f'<line x1="{px(x):.1f}" y1="{top}" x2="{px(x):.1f}" y2="{top + plot_h}" stroke="var(--edge)"/>'
        f'<text x="{px(x):.1f}" y="{height - 6}" text-anchor="{anchor}" {text}>{100 * x:.0f}%</text>'
        for x, anchor in ((0.0, "start"), (0.5, "middle"), (1.0, "end")))
    frame += "".join(
        f'<line x1="{left}" y1="{py(y):.1f}" x2="{left + plot_w}" y2="{py(y):.1f}" stroke="var(--edge)"/>'
        f'<text x="{left - 4}" y="{py(y) + 3.5:.1f}" text-anchor="end" {text}>{100 * y:.4g}%</text>'
        for y in (0.0, y_top / 2, y_top))
    frame += (f'<line x1="{px(k / total):.1f}" y1="{top}" x2="{px(k / total):.1f}" y2="{top + plot_h}" stroke="var(--text-2)" '
              'stroke-width="1" stroke-dasharray="4 3"/>')
    defs = (f'<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
            f'<g id="same-frame-{key}">{frame}</g><polyline id="same-ref-{key}" points="{points(ref["curve"])}"/></defs></svg>')
    shapes = " ".join(f"{legend_mark('var(--text-2)', er.SHAPES[wording])} “{esc(wording)}”"
                      for wording in dict.fromkeys(point["wording"] for model in family["models"] for point in model["points"] or []))
    shown = {model["text_run"]: site.plain(site.by_id[model["text_run"]]) for model in family["models"]}

    def card(model: dict[str, Any]) -> str:
        run = site.by_id[model["text_run"]]
        name = shown[run["run"]]
        engine = same_engine(site, family, model)
        marks = ""
        for point in model["points"] or []:
            tip = (f"{name}: “{point['wording']}”, run {point['run']}: {point['answered']:,} answered, {point['wrong']:,} wrong"
                   + (f"; {engine}" if engine else ""))
            share = point["wrong"] / point["answered"] if point["answered"] else 0
            marks += (f'<g><title>{esc(tip)}</title>'
                      f'{marker_path(er.SHAPES[point["wording"]], px(point["answered"] / total), py(share))}</g>')
        short = same_short(model)
        wrong = ("— (left out: its run has "
                 f"{len(model['wrong_by_rank']):,} scored answers, fewer than k)" if short else
                 f"{same_wrong_text(model['wrong'])} ({pct(model['wrong_of_answers'], digits)})")
        versus = ("the reference, dashed in every plot" if model["reference"] else "not tested" if short else
                  f"{100 * model['difference']:+.{digits}f} points against {esc(reference)}, Holm "
                  f"{esc(bp.p_text(model['p_holm']))}{' *' if model['p_holm'] < 0.05 else ''}")
        if model["points"]:
            option = ("Runs with the option: " + joined([
                f"“{esc(point['wording'])}” run {point['run']}, "
                + (f"{pct(point['wrong'] / point['answered'], digits)} wrong of {point['answered']:,}" if point["answered"]
                   else "no answer") for point in model["points"]]) + (f" ({esc(engine)})" if engine else ""))
        else:
            reason = {item["name"]: item["reason"] for item in site.config["dont_know"]["not_run"]}.get(model["name"])
            option = "Runs with the option: " + (esc(reason) if reason else "No run with the option yet")
        svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{esc(name)}: wrong of answers '
               f'against answered, with {esc(reference)}\'s curve dashed"><use href="#same-frame-{key}"/>'
               f'<use href="#same-ref-{key}" fill="none" stroke="var(--text-2)" stroke-width="1.3" stroke-dasharray="4 3"/>'
               f'<polyline fill="none" stroke="{SAME_SMALL_COLOUR}" stroke-width="1.6" stroke-linejoin="round" '
               f'points="{points(model["curve"])}"><title>{esc(name)}: five options, run {model["five_option_run"]}, from 1 to '
               f'{model["curve"][-1][0]:,} answers; '
               + (f'left out: fewer than k = {k:,} scored answers' if short else
                  f'{same_wrong_text(model["wrong"])} wrong of its {k:,} most confident') + '</title>'
               f'</polyline><g fill="{SAME_SMALL_COLOUR}" stroke="var(--panel)" stroke-width="1">{marks}</g></svg>')
        return (f'<li{site.class_attribute(run)}><figure style="margin:0">{svg}<figcaption class="note" style="margin:.25rem 0 0">'
                f'{site.icon(run)}<a class="model-name" href="{rel(PATH, site.model_path(run))}" title="{esc(site.detail(run))}">{esc(site.title(run))}</a>{tag_html(site.tag(run))} {site.label(run)} '
                f'Wrong of the {k:,} answers: {wrong}, {versus}<br>'
                f"{option}</figcaption></figure></li>")

    grid = ('<ul style="list-style:none;padding:0;margin:0 0 1rem;display:grid;'
            'grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem 1.25rem">')
    groups = "".join((f'<h3 class="board-group">{title}</h3>' if title else "") + grid + "".join(card(model) for model in models)
                     + "</ul>" for title, models in same_board_groups(site, family))
    count = len(family["models"])
    return (f'<section class="card" id="same-answers-curves"><h2>Every setup\'s curve in {family["language"]}</h2>'
            f'<p class="note">One small plot per setup, all {count}, grouped and ordered as the {family["language"]} table above, '
            f"on the same axes: answered across (0 to 100% of the {total:,} questions), wrong of answers up (0 to "
            f"{100 * y_top:.4g}%; anything higher is drawn at the top edge). The line is the setup's five-option run held back "
            f"by its own confidence, from 1 answer to its scored answers; the dashed line is {esc(reference)}'s (run "
            f"{ref['five_option_run']}) in every plot, and the dashed vertical line is k = {k:,}. The markers are the setup's "
            f"runs with the option ({shapes}). Each line is thinned to one vertex per {100 * SAME_SMALL_STEP:g}% of coverage, "
            f"always keeping the first, the last and the point at k; every vertex is a curve point.</p>{defs}{groups}</section>")



def same_info(site: Site, same: dict[str, Any], families: list[dict[str, Any]]) -> str:
    """Under Info: one table per family and the method notes."""
    digits = site.config["percent_digits"]
    reference = same["reference"]
    p_text = lambda value: esc(bp.p_text(value).removeprefix("p = ").removeprefix("p "))  # noqa: E731
    tables = ""
    for family in families:
        k, total = family["k"], family["questions"]
        count = sum(1 for model in family["models"] if not model["reference"] and not same_short(model))
        heads = (("Five-option run", "the run whose k answers are kept"),
                 ("Wrong of the k answers", f"wrong / {k:,}; lower is better"),
                 (f"Difference from {reference}", "points, with its 95% interval; positive = more wrong answers"),
                 ("p", "paired bootstrap, two-sided"), ("Holm p", f"adjusted over the {count}"),
                 ("Runs with the option", "for context: answered, wrong of answers"))
        labels = [f"{head} ({note})" for head, note in heads]
        head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)

        def row(model: dict[str, Any]) -> str:
            five = f"{model['five_option_run']}"
            short = same_short(model)
            wrong = (f'—<span class="small">left out: its run has {len(model["wrong_by_rank"]):,} scored answers, fewer '
                     f"than k = {k:,}</span>" if short else
                     f'{pct(model["wrong_of_answers"], digits)}<span class="small">{same_wrong_text(model["wrong"])} of '
                     f"{k:,}</span>")
            if not model["points"]:
                context = 'none<span class="small">no run with the option</span>'
            else:
                context = (" · ".join(str(point["run"]) for point in model["points"])
                           + "".join(f'<span class="small">“{esc(point["wording"])}”, run {point["run"]}: {point["answered"]:,} '
                                     f"answered ({pct(point['answered'] / total, digits)}), "
                                     + (f"{pct(point['wrong'] / point['answered'], digits)} wrong ({point['wrong']:,})"
                                        if point["answered"] else "no answers, so wrong of answers undefined") + "</span>"
                                     for point in model["points"]))
                engine = same_engine(site, family, model)
                if engine:
                    context += f'<span class="small">{esc(engine[0].upper() + engine[1:])}</span>'
            if model["reference"]:
                own = next(point for point in model["points"] if point["run"] == family["k_run"])
                values = [five, wrong,
                          f'reference<span class="small">its own run {own["run"]} with “{esc(own["wording"])}”: '
                          f'{own["wrong"]:,} wrong of {own["answered"]:,} ({pct(own["wrong"] / own["answered"], digits)}), '
                          "not part of the test</span>", "reference", "reference", context]
            elif short:
                values = [five, wrong, '—<span class="small">left out, fewer than k scored answers</span>', "—", "—", context]
            else:
                low, high = model["interval"]
                values = [five, wrong,
                          f'{100 * model["difference"]:+.{digits}f}<span class="small">{100 * low:+.{digits}f} to '
                          f"{100 * high:+.{digits}f}</span>",
                          p_text(model["p"]), p_text(model["p_holm"]) + (" *" if model["p_holm"] < 0.05 else ""), context]
            text = {'original_run': model['text_run']}
            return (f"{model_tr(site, text)}{model_cell(site, text)}"
                    + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")

        def board(models: list[dict[str, Any]]) -> str:
            """The models' table, in the order same_board_groups gives."""
            return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}'
                    f'</tr></thead><tbody>{"".join(row(model) for model in models)}</tbody></table></div>')

        where = "questions" if family["key"] == "turkish" else "kept reading questions"
        tables += f"<h3>{family['language']}: k = {k:,} of the {total:,} {where}</h3>"
        if family["key"] == "turkish":
            tables += ('<p class="note">Each setup\'s curve over every number of answers: '
                       '<a href="#same-answers-curves">Every setup\'s curve in Turkish</a>, below.</p>')
        for title, models in same_board_groups(site, family):
            tables += (f'<h4 class="board-group">{title}</h4>' if title else "") + board(models)
    turkish, english = families
    resamples = same["resamples"]
    tail = round(0.025 * resamples)
    glide = [model for model in turkish["models"] if same_engine(site, turkish, model)]
    glide_text = "".join(
        f" For {esc(same_label(site, model))}, the Turkish five-option run is the Text tab's run {model['five_option_run']}, "
        f"made with Fastino's engine glide; its runs with the option, {joined([str(point['run']) for point in model['points']])}, "
        "answered with glide_v2, a different hosted model "
        '(<a href="#hosted-glide-rerun-method">Our method for the hosted GLiDE rerun</a>), so its line and its markers '
        "come from two models, as the legend and the table say." for model in glide)
    refs = {family["key"]: next(model for model in family["models"] if model["reference"]) for family in families}
    short_text = (" A run with fewer than k scored answers keeps no k answers: it is left out of the bootstrap and of "
                  "Holm's adjustment, and its line ends before k." if any(same_short(model) for family in families
                                                                          for model in family["models"]) else "")
    compared = lambda family: sum(1 for model in family["models"] if not model["reference"] and not same_short(model))  # noqa: E731
    plotted = len(same_plotted(turkish))
    owns = {key: next(point for point in model["points"] if point["run"] == families[index]["k_run"])
            for index, (key, model) in enumerate(refs.items())}
    return f"""
    <section class="card" id="same-answers-results">
      <h2>Results: the same number of answers</h2>
      <p class="note">One table per language, ordered by wrong of the k answers, fewest first; the Turkish one has every main run of the Text tab ({len(turkish["models"])} setups), grouped as its leaderboard groups them and labelled as it labels them. Each row: the model's five-option run held to its k most confident answers, its wrong answers among them, the difference from {esc(reference)} in points with its 95% bootstrap interval, p and Holm p (* marks a Holm-adjusted p below 0.05), and for context the model's own runs with the option (answered = right + wrong, and wrong of answers = wrong / answered), which are not part of the test; a setup without one reads none.</p>
      {tables}
    </section>
    {same_curves(site, same, turkish)}
    <section class="card method-notes" id="same-answers-method">
      <h2>Our method for the same number of answers</h2>
      <p>Each model's five-option run answers only its k most confident questions, by its score (the probability it gave the option it picked), and holds back on the rest; we count its wrong answers among the k. Wrong of the k answers = wrong / k. k is the number of questions {esc(reference)} answered (right + wrong) with the option on offer: {turkish["k"]:,} in its run {turkish["k_run"]} with “{esc(turkish["k_wording"])}” on the {turkish["questions"]:,} Turkish questions (the option's word, above), and {english["k"]:,} in its run {english["k_run"]}, its first English run with “{esc(english["k_wording"])}”, on the {english["questions"]:,} kept reading questions. Every model in a language is held to the same k.</p>
      <p>The answers are ranked by score, highest first, and equal scores by question ID, lowest first (never by whether the answer is right); the first k are kept, so the wrong count is always a whole number. An answer without a score or a valid choice is never kept.</p>
      <p>The difference is a model's wrong of the k answers minus {esc(reference)}'s, in points. Its uncertainty comes from a paired bootstrap over questions: {resamples:,} resamples of the questions with replacement, from a new random generator with the numeric seed {same["seed"]} for each language, the same resample for every model, a question drawn twice counting twice and k fixed. In each resample every run's drawn answers are ranked again by score and question ID, the copies of a drawn question sitting together, and the first k kept, so the count stays whole. Two-sided p = min(1, 2 × min(1 + #{{d ≤ 0}}, 1 + #{{d ≥ 0}}) / {resamples + 1:,}), where #{{d ≤ 0}} is the number of resamples whose difference d is 0 or less and #{{d ≥ 0}} the number whose difference is 0 or more. Its floor is 2/{resamples + 1:,} (p = {esc(bp.p_text(2 / (resamples + 1)).removeprefix("p = "))}), when no resample falls on the other side of zero: a p at the floor says the difference held in every resample, not that p is exactly that value. The 95% interval is the percentile interval: from the {tail:,}th smallest to the {tail:,}th largest of the {resamples:,} resampled differences.</p>
      <p>Holm's method adjusts p over the other {compared(turkish)} setups in Turkish (every main run of the Text tab, decision models and chat and general models alike) and the other {compared(english)} models in English, each language a family of its own, separate from the tab's other comparisons. The resamples do not depend on which models are compared, so a model's p is the same in any family; only Holm's adjustment grows with the family.{short_text}{glide_text}</p>
      <p>The plots show every number of answers, not only k. Each line is a five-option run under the same selection, one point per number of answers from 1 to the run's scored answers: answered / questions across, wrong / answered up. There is no point at 0 answers, where the share wrong is undefined, and a line ends at its run's scored answers, without being extended to 100%. The Turkish plot draws the {plotted} setups with runs with the option; the English curves come from this comparison too, so they can differ slightly from those of the Turkish vs English tab (<a href="{rel(PATH, "turkish-vs-english/")}#coverage">Risk and coverage</a>), where answers with equal scores enter together. A line skips vertices closer than {100 * SAME_MIN_STEP:g}% of coverage to the previous one drawn, always keeping the first, the last and the point at k, so every vertex drawn is a curve point; the y axis fits the markers and every curve point at 1% coverage or more, and anything higher (the first few answers, where one wrong answer is a large share) is drawn at the top edge. The markers are each model's own runs with the option: in Turkish its first run with “{esc(site.results["dont_know"]["option"])}” (the table above) and its run with “{esc(turkish["k_wording"])}” (the option's word); in English its first English run with “{esc(english["k_wording"])}”.</p>
      <p>Limits: k comes from one model, {esc(reference)}, and a different k gives different numbers (the plots show them all). The k answers kept are each model's own most confident ones, so the models are counted on different questions. {esc(reference)}'s own runs with the option made {owns["turkish"]["wrong"]:,} wrong of {owns["turkish"]["answered"]:,} in Turkish and {owns["english"]["wrong"]:,} of {owns["english"]["answered"]:,} in English, against {same_wrong_text(refs["turkish"]["wrong"])} and {same_wrong_text(refs["english"]["wrong"])} for its five-option run held to the same k: the comparison is between five-option runs held back by confidence, not between runs with the option.</p>
    </section>"""


def high_rate(kept: int, wrong: int, digits: int) -> str:
    """% wrong of the answers kept, with "wrong of kept" small; NO_ANSWERS, muted, with none kept."""
    if not kept:
        return f'<span class="nm">{NO_ANSWERS}</span>'
    return f'{pct(wrong / kept, digits)}<span class="small">{wrong:,} of {kept:,}</span>'


def kept_cells(kept: int, wrong: int, digits: int) -> list[str]:
    """Answers kept, Wrong and % wrong: with none kept, NO_ANSWERS and dashes, muted, never "0 wrong"."""
    if not kept:
        return [f'<span class="nm">{NO_ANSWERS}</span>', '<span class="nm">–</span>', '<span class="nm">–</span>']
    return [f"{kept:,}", f"{wrong:,}", high_rate(kept, wrong, digits)]


def high_check_text(site: Site, high: dict[str, Any], digits: int) -> str:
    """The sentence under the cutoff table, from `check` and the table: whether Liquid d1-ultra's worst run stays below
    the best run of each other model at every whole-percent cutoff up to 98%, and where it does not."""
    cuts, (ref, *others) = high["cutoffs"]["cutoffs"], high["cutoffs"]["models"]
    rates = lambda model, index: [run["wrong"][index] / run["kept"][index] for run in model["runs"]]  # noqa: E731
    name = lambda model: esc(site.plain(site.by_id[model["text_run"]]))  # noqa: E731
    names = " and of ".join(name(model) for model in others)
    top = cuts.index(0.99)
    highest = max(rate for model in high["cutoffs"]["models"] for rate in rates(model, top))
    if high["cutoffs"]["check"]["holds"]:
        return (f"At every cutoff up to 98% (each whole percent), {name(ref)}'s worst run has a lower % wrong than "
                f"the best run of {names}; at 99%, all three are at or near 0 (highest: {pct(highest, digits)}).")
    failing = [f"{100 * cut:g}%" for index, cut in enumerate(cuts) if cut < 0.99
               and not all(max(rates(ref, index)) < min(rates(model, index)) for model in others)]
    where = (f"in the table it fails at {joined(failing)}" if failing
             else "it fails at one or more whole-percent cutoffs between the table's columns")
    return (f"Not at every cutoff up to 98% (each whole percent) does {name(ref)}'s worst run have a lower % wrong "
            f"than the best run of {names}: {where}.")


def check_high_confidence(site: Site, high: dict[str, Any]) -> None:
    """Stop the build when high_confidence does not fit: wrong above kept, a cutoff table whose runs are not the repeat
    sets, d1-ultra's repeats not its repeat set, an English wrong-question list of another length, or a check that the
    table's own columns contradict."""
    def fail(text: str) -> SystemExit:
        return SystemExit(f"results.json high_confidence: {text}")

    pairs = [(model["name"], model["kept"], model["wrong"]) for model in high["models"]]
    pairs += [(f"run {run['run']}", run["kept"], run["wrong"]) for entry in high["repeats"] for run in entry["runs"]]
    pairs += [(f"English run {run['run']}", run["kept"], run["wrong"]) for run in high["english"]["runs"]]
    pairs += [(f"run {run['run']} at {cut:g}", kept, wrong) for model in high["cutoffs"]["models"] for run in model["runs"]
              for cut, kept, wrong in zip(high["cutoffs"]["cutoffs"], run["kept"], run["wrong"], strict=True)]
    for name, kept, wrong in pairs:
        if not 0 <= wrong <= kept:
            raise fail(f"{name}: {wrong} wrong of {kept} kept")
    if high["threshold"] not in high["cutoffs"]["cutoffs"] or 0.99 not in high["cutoffs"]["cutoffs"]:
        raise fail("the cutoff table has no column at the threshold or at 99%")
    sets = {entry["name"]: entry["runs"] for entry in site.results["repeats"] if entry["variant"] is None}
    for model in high["cutoffs"]["models"]:
        runs = [run["run"] for run in model["runs"]]
        if sets.get(model["name"]) != runs or runs[0] != model["text_run"]:
            raise fail(f"{model['name']}: cutoff table runs {runs} are not its repeat set {sets.get(model['name'])}")
    for entry in high["repeats"]:
        if [entry["text_run"]] + [run["run"] for run in entry["runs"]] != sets.get(entry["name"]):
            raise fail(f"{entry['name']}: repeats are not its repeat set")
    for run in high["english"]["runs"]:
        if len(run["wrong_questions"]) != run["wrong"] or run["wrong_questions"] != sorted(run["wrong_questions"]):
            raise fail(f"English run {run['run']}: wrong_questions do not fit the wrong count")
    if high["cutoffs"]["check"]["holds"] and "Not at every" in high_check_text(site, high, 1):
        raise fail("check holds, but the table's columns say otherwise")
    if not high["cutoffs"]["check"]["holds"] and "Not at every" not in high_check_text(site, high, 1):
        raise fail("the sentence does not match check")


def high_face(site: Site, high: dict[str, Any]) -> str:
    """The section on the tab's face: the rule, every decision setup's answers at the threshold, d1-ultra's repeats, the
    three models Artificial Analysis ties at 65 across cutoffs, and d1-ultra in English."""
    from sitebuild.questions import question_link
    digits = site.config["percent_digits"]
    threshold = f"{100 * high['threshold']:g}%"

    def board(heads: tuple[str, ...], rows: list[tuple[int, str, list[str]]]) -> str:
        head = "".join(f'<th scope="col" class="num">{esc(name)}</th>' for name in heads[1:])
        body = "".join(f"<tr{site.class_attribute(site.by_id[run_id])}>{first}"
                       + "".join(cell(label, value) for label, value in zip(heads[1:], values)) + "</tr>"
                       for run_id, first, values in rows)
        return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">{esc(heads[0])}</th>'
                f"{head}</tr></thead><tbody>{body}</tbody></table></div>")

    def name_cell(run_id: int, note: str) -> str:
        run = site.by_id[run_id]
        return (f'<td class="model">{site.icon(run)}<a class="model-name" href="{rel(PATH, site.model_path(run))}">{esc(site.title(run))}</a>'
                f'{tag_html(site.tag(run))} {site.label(run)}'
                f'<span class="small">{esc(note)}</span></td>')

    run_note = lambda run, text_run: f"run {run}, " + ("Text tab run" if run == text_run else "repeat run")  # noqa: E731
    decision = [model for model in high["models"] if site.decision(site.by_id[model["text_run"]])]
    decision.sort(key=lambda model: (not model["kept"], model["wrong"] / model["kept"] if model["kept"] else 0,
                                     -model["kept"], model["name"]))
    heads = ("Model", "Run", f"Answers kept (at {threshold}+)", "Wrong", "% wrong")
    main = board(heads, [(model["text_run"], model_cell(site, {"original_run": model["text_run"]}),
                          [str(model["text_run"]), *kept_cells(model["kept"], model["wrong"], digits)])
                         for model in decision])
    repeats = ""
    for entry in high["repeats"]:
        first = next(model for model in high["models"] if model["text_run"] == entry["text_run"])
        runs = [{"run": entry["text_run"], "kept": first["kept"], "wrong": first["wrong"]}] + entry["runs"]
        repeats += (f"<h3>{site.shown(site.by_id[entry['text_run']])}'s repeat runs</h3>"
                    f'<p class="note">The same questions and settings, run again; run {entry["text_run"]} is the Text tab '
                    "run above, shown for context.</p>"
                    + board(("Run", "Answers kept", "Wrong", "% wrong"),
                            [(entry["text_run"], name_cell(entry["text_run"], run_note(run["run"], entry["text_run"])),
                              kept_cells(run["kept"], run["wrong"], digits))
                             for run in runs]))
    cuts = high["cutoffs"]["cutoffs"]
    cut_heads = ("Model and run",) + tuple(f"{100 * cut:g}%" for cut in cuts)
    cut_rows = [(model["text_run"], name_cell(model["text_run"], run_note(run["run"], model["text_run"])),
                 [high_rate(kept, wrong, digits) for kept, wrong in zip(run["kept"], run["wrong"])])
                for model in high["cutoffs"]["models"] for run in model["runs"]]
    english = high["english"]
    english_name = site.plain(next(run for run in site.runs if run["name"] == english["name"]))
    eruns = english["runs"]
    count = len(eruns)
    kept = sorted(run["kept"] for run in eruns)
    kept_text = f"{kept[0]:,}" if kept[0] == kept[-1] else f"{kept[0]:,} to {kept[-1]:,}"
    links = lambda ids: joined([question_link(PATH, qid) for qid in ids])  # noqa: E731
    if all(run["wrong"] == eruns[0]["wrong"] and run["wrong_questions"] == eruns[0]["wrong_questions"] for run in eruns):
        wrong = eruns[0]["wrong"]
        noun = "answer" if wrong == 1 else "answers"
        tail = (f", always question {links(eruns[0]['wrong_questions'])}" if wrong == 1
                else f", always questions {links(eruns[0]['wrong_questions'])}" if wrong else "")
        result = f"has {wrong:,} wrong {noun} in each of its {count} runs{tail}"
    else:
        result = f"has, over its {count} runs, " + joined(
            [f"{run['wrong']:,} wrong in run {run['run']}" + (f" (question {links(run['wrong_questions'])})" if run["wrong"] else "")
             for run in eruns])
    note = (f'<p class="note">In English (the {english["questions"]:,} kept reading questions of the '
            f'<a href="{rel(PATH, "turkish-vs-english/")}">Turkish vs English tab</a>), at {threshold}, {esc(english_name)} '
            f"{result}; each run keeps {kept_text} answers (runs {joined([str(run['run']) for run in eruns])}).</p>")
    return (f'<section class="card" id="high-confidence"><h2>Answers at {threshold}+ confidence</h2>'
            f"<p>{esc(high['rule'])} Each decision model is counted on its Text tab run (its first five-option Turkish run, "
            f"the run the site already uses), on the Text tab's {site.total:,} questions, keeping the answers whose chosen "
            f"option has a probability of at least {threshold}. These runs have no “I don't know” option.</p>"
            f"<h3>Every decision setup</h3>"
            f'<p class="note">Ordered by % wrong (wrong / answers kept), then by answers kept, more first; a setup that '
            f"keeps no answers is last ({NO_ANSWERS}: its % wrong is undefined).</p>"
            f"{main}{repeats}"
            f"<h3>The three models Artificial Analysis ties at 65</h3>"
            f'<p class="note">The three models its Decision Index v1.0 puts level at 65 (<a href="'
            f'{esc(site.config["aa_decision_index"]["post"])}">its post</a>), each with its Text tab run and its repeat runs, '
            "one row per run. Each column is a cutoff: % wrong of the answers kept at that probability or higher, with "
            "wrong of kept below.</p>"
            f"{board(cut_heads, cut_rows)}"
            f"<p>{high_check_text(site, high, digits)}</p>{note}</section>")


def chat_findings(site: Site, data: dict[str, Any]) -> str:
    """What we found about the chat models (shown for the all and chat groups): how many setups have a run with the
    option, the range of their non-hallucination rates against the decision models', and how many are still running."""
    digits = site.config["percent_digits"]
    models = ranked(data["models"])
    chat = [model for model in models if model["group"] == "chat" and model["non_hallucination"] is not None]
    decision = [model for model in models if model["group"] == "decision" and model["non_hallucination"] is not None]
    running = [run for run in running_setups(site) if not site.decision(run)]
    if not chat:
        return ""
    name = lambda model: esc(site.plain(site.by_id[model["original_run"]]))  # noqa: E731
    spread = (f"from {pct(chat[-1]['non_hallucination'], digits)} ({name(chat[-1])}) to "
              f"{pct(chat[0]['non_hallucination'], digits)} ({name(chat[0])})") if len(chat) > 1 else \
        f"{pct(chat[0]['non_hallucination'], digits)} ({name(chat[0])})"
    against = (f", against {pct(decision[-1]['non_hallucination'], digits)} to {pct(decision[0]['non_hallucination'], digits)} "
               f"for the {len(decision)} decision models") if decision else ""
    still = (f" {bp.opening_count(len(running))} more chat model setup{'' if len(running) == 1 else 's'} "
             f"{'is' if len(running) == 1 else 'are'} still running in Turkish (Running, under Results).") if running else ""
    return (f'<p data-models="all chat">Chat models: {bp.in_words(len(chat))} setup{"" if len(chat) == 1 else "s"} '
            f"{'has' if len(chat) == 1 else 'have'} a run with “{esc(shown_option(data['option']))}” so far, with a non-hallucination rate "
            f"{spread}{against}.{still}</p>")


def build(site: Site) -> dict[str, str]:
    data = site.results["dont_know"]
    total = f"{data['questions']:,}"
    option = esc(shown_option(data["option"]))
    literal = esc(data["option"])  # the option's own text, where the prompts are quoted
    misgrouped = [model["name"] for model in data["models"]
                  if model["group"] != ("decision" if site.decision(site.by_id[model["original_run"]]) else "chat")]
    if misgrouped:
        raise SystemExit(f"results.json dont_know: rows whose group is not their Text tab run's: {', '.join(misgrouped)}")
    if data["questions"] != site.total:
        raise SystemExit(f"results.json dont_know: {data['questions']} questions, the Text tab {site.total}")
    chat_rows = [model for model in data["models"] if model["group"] == "chat"]
    if chat_rows and not data.get("chat"):
        raise SystemExit("results.json dont_know: chat models' rows without the chat models' prompts")
    if any(site.by_id[model["original_run"]]["questions_per_request"] != 1 for model in data["models"] if model["group"] == "decision"):
        raise SystemExit("results.json dont_know: a decision model's Text tab run asks more than one question per request")
    # The parts about decision models only read the decision models' rows.
    decision = group_data(data, "decision")
    several = [model["name"] for model in data["models"] if len(model["runs"]) > 1]
    word, rerun = site.results.get("dont_know_option_word"), site.results.get("hosted_glide_rerun")
    english = (site.results.get("english_reading") or {}).get("dont_know")
    if english:
        from sitebuild import english_reading as er  # here, not at the top: english_reading imports this module
        english = er.idk_group(site, english, "decision")
    if word:
        check_option_word(site, decision, word)
    glide = check_rerun(site, decision, rerun) if rerun else None
    against = word if word and word.get("vs_confidence") else None
    if against:
        check_vs_confidence(site, decision, against, rerun)
    same = site.results.get("dont_know_same_answers")
    families = same_families(site, same) if same else []
    if same:
        check_same_answers(site, decision, word, families, same["reference"])
    high = site.results.get("high_confidence")
    if high:
        check_high_confidence(site, high)
    chat = data.get("chat")
    counts = {group: len(group_models(site, data, group)) for group in GROUPS}
    running = [run for run in running_setups(site) if not site.decision(run)]
    chat_sentence = (f" A chat model's instructions end with its own sentence instead: “{esc(chat['sentence'])}”"
                     if chat else "")
    chat_models = (f" With them, every chat model setup of the Text tab as its run finishes: {bp.in_words(counts['chat'])} so far"
                   + (f", {bp.in_words(len(running))} still running in Turkish" if running else "") + ".") if chat_rows or running else ""
    chat_prompts = (f"<p>A chat model is asked as on the Text tab, with the option after each question's own and one sentence "
                    f"added at the end of each instruction of its prompts: “{esc(chat['sentence'])}” Its system prompt and "
                    f"instruction when it states a confidence, in full:</p><blockquote><p>{esc(chat['confidence_system'])}</p>"
                    f"<p>{esc(chat['confidence_instruction'])}</p></blockquote><p>Prompt version {esc(chat['prompt_version'])} "
                    "(the chat models' prompts with the sentence and the option, hashed the same way).</p>") if chat else ""
    site.note(PATH, "Hallucination",
              f"<p>A wrong answer counts as a hallucination: the model could have chosen “{option}” "
              "instead. This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its "
              f"numbers.</p><div {DECISION_ONLY}>{headline(site, decision, against)}</div>")
    body = f"""    <section class="card">
      <p class="eyebrow">Hallucination</p>
      <h1>The Text tab's {total} questions, with “{option}” as a sixth option</h1>
      <div {DECISION_ONLY}>
      <nav class="face-nav" aria-label="On this page"><a href="#chart-non-hallucination">Non-hallucination and answered</a><a href="#chart-confidence">Against confidence</a><a href="#chart-paired">Paired test</a><a href="#chart-accuracy">Accuracy</a>{'<a href="#english-option">English questions</a>' if english else ""}{'<a href="#option-word">The option&#x27;s word</a>' if word else ""}{'<a href="#option-word-confidence">“I don&#x27;t know” against confidence</a>' if against else ""}{'<a href="#hosted-glide-rerun">Hosted GLiDE rerun</a>' if rerun else ""}{'<a href="#same-answers">The same number of answers</a>' if same else ""}{'<a href="#high-confidence">Answers at 95%+ confidence</a>' if high else ""}<a href="#info">Info</a></nav></div>
    </section>
    {"".join(face(site, data, group) for group in GROUPS if counts[group])}
    <p class="note">A wrong answer counts as a hallucination: the model could have chosen “{option}” instead.</p>
    {more_link(PATH)}
    <div {DECISION_ONLY}>
    {english_option_face(site, english, site.results.get("dont_know_english_option")) if english else ""}{option_word_face(site, decision, word) if word else ""}{vs_confidence_face(site, decision, against) if against else ""}{rerun_face(site, decision, rerun, glide) if rerun else ""}{same_face(site, same, families) if same else ""}{high_face(site, high) if high else ""}
    </div>
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The table, what we found and our method</span></summary>
    <section class="card">
      <h2>About this test</h2>
      <p>Every question of the Text tab gets one more option after its five answers: F, “{option}”, written in Turkish in the prompt (“{literal}”). It is always the last option, it is never shuffled and it is never correct. The System One instructions get one added sentence: “{esc(data["sentence"])}”{chat_sentence} Everything else is as on the Text tab: the same {total} scored questions and answer key, and each model's own settings from its text run, its questions per request too (one for every decision model).</p>
      <p>The models: {esc(SELECTION)}.{chat_models} Each has one full run; a model whose repeated text runs changed answers gets five.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page, under <code>dont_know</code>) and <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each run's answers, under <code>dont_know_runs</code>).</p>
    </section>
    <section class="card" id="results">
      <h2>Results</h2>{measure_rows(PATH, (PATH, "results"))}
      <p class="note">The rows are ranked by the first column, the non-hallucination rate, highest first: the share of “{option}” among the answers that were not right (“{option}” / (“{option}” + wrong)), so the first model is the one that most often said it did not know instead of answering wrongly. Beside it: Answered, how often the model chose one of the question's own options (right + wrong, out of all {total} questions), and the error rate, the share of those answers that were wrong (wrong / (right + wrong)). Read the ranking with Answered, the error rate and accuracy: a model that always chose “{option}” would rank first with no right answers. Each row shows the model's first run{"; under Runs, a model with more than one run (" + esc(joined(several)) + ") shows the range over its runs and how many answers changed between them" if several else ""}. Out of all {total} questions: accuracy counts the right answers; Answered (the attempt rate) counts the right and wrong answers. Formulas and how to read them: <a href="#method">Our method</a>.</p>
      {"".join(table(site, data, group) for group in GROUPS if counts[group])}
      <div {DECISION_ONLY}>{not_run(site.config["dont_know"]["not_run"])}</div>
      {"".join(f'<div {shown(group)}>{running_list(site, group)}</div>' for group in GROUPS if running_list(site, group))}
    </section>
    <section class="card" id="findings">
      <h2>What we found</h2>
      <div {DECISION_ONLY}>{findings(site, decision, against)}{same_finding(site, same, families) if same else ""}</div>
      {chat_findings(site, data)}
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>We measure hallucination by offering a way out. Every question gets “{option}” as a sixth option, and the instructions tell the model to choose it when it does not know the answer. A hallucination is then a wrong answer: the model chose one of the question's own options, not the key, when it could have said it did not know. Everything else is the Text tab's: the questions, the answer key and each model's settings.</p>
      <h3>How it differs from our confidence method</h3>
      <p>On the Text tab a model must pick one of the five options, and we judge each answer by its confidence: the probability the model gives the option it picked (its <a href="{rel(PATH, "method/")}#confidence-sources">option score</a>), or for a chat model the confidence it states. Our confidence method keeps an answer when that confidence reaches a cut-off, and a stronger model answers the rest (<a href="{rel(PATH, "method/")}#routing">How we chose which answers to keep</a>). Here no cut-off decides: the model can say itself that it does not know, by choosing “{option}”, and the rates count those choices. The two meet in the derived non-hallucination rate, which applies the confidence method to the same model's five-option run at about the same attempt rate; side by side, the two non-hallucination columns compare a model that says it does not know with the same model held back by its own confidence.</p>
      <h3>The rates</h3>
      <p>Each answer is right, wrong, “{option}” or invalid; an invalid answer counts as none of the others. Out of all {total} questions:</p>
      <ul>
        <li><strong>Accuracy</strong> = right / {total}.</li>
        <li><strong>Answered</strong> (the attempt rate) = (right + wrong) / {total}: how often the model chose one of the question's own options.</li>
        <li><strong>Error rate</strong> = wrong / (right + wrong): among the answers the model gave, the share that were wrong. With no answer it is undefined.</li>
        <li><strong>Non-hallucination rate</strong> = “{option}” / (“{option}” + wrong): among the answers that were wrong or “{option}”, the share where the model said it did not know. The hallucination rate is its complement, wrong / (“{option}” + wrong).</li>
        <li><strong>Mean probability of “{option}”</strong>: the probability the model gave that option, averaged over its answers that report option probabilities. A chat model states a confidence and reports no option probabilities.</li>
      </ul>
      <h3>How to read them</h3>
      <p>The non-hallucination rate says how a model is wrong, not how often it is right, and it is not a direct measure of what the model does not know. Read it with accuracy and the attempt rate: a model that always chose “{option}” would reach 100% with no right answers, and one that never chose it would reach 0% as soon as it answered one question wrongly. With neither a wrong answer nor “{option}”, there is nothing to divide by and the rate is undefined (the table shows Undefined).</p>
      <h3>The option and the instructions</h3>
      <p>The added option's exact text in the prompt is “{literal}”. It is lettered after the question's own options, and the answer key is unchanged. The full System One instructions of a decision model:</p>
      <blockquote><p>{esc(data["instructions"])}</p></blockquote>
      <p>Prompt version {esc(data["prompt_version"])} (a hash of the prompts with these instructions and this option, computed as for the Text tab's prompt version).</p>
      {chat_prompts}
      <h3>Derived non-hallucination rate</h3>
      <p>For comparison, each model's run with five options (its run on the Text tab, on the same questions) is made to abstain by its own confidence: it answers only where its score (a decision model's option score, a chat model's stated confidence) reaches a cut-off and abstains on the rest. The cut-off is the one whose attempt rate comes nearest the attempt rate of the run with “{option}”; on a tie, the higher cut-off. An answer without a score never counts as an attempt. The derived non-hallucination rate is then the abstentions over the abstentions plus the wrong answers. The table shows the cut-off and the attempt rate it reached. The paired test of the two is among the decision models.</p>
      <h3>Repeats</h3>
      <p>One full run per model. A model whose repeated text runs changed answers gets five runs with the option. Those runs form a repeat set of their own and are never mixed with the Text tab's runs. The table shows the first run; the range covers all of them, and the changed answers are the scored questions whose answer differs between the runs.</p>
    </section><div {DECISION_ONLY}>{english_option_info(site, english) if english else ""}{option_word_info(site, decision, word) if word else ""}{vs_confidence_info(site, decision, against) if against else ""}{rerun_info(site, decision, rerun, glide) if rerun else ""}{same_info(site, same, families) if same else ""}</div>
    </details>"""
    return {PATH: site.page(PATH, "Hallucination",
                            f"The Text tab's {total} questions with a sixth option, “{shown_option(data['option'])}”: accuracy, "
                            "attempt rate and non-hallucination rate of the most accurate decision models and the chat models.", body)}
