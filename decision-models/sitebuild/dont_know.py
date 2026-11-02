"""Hallucination (dont-know/), the site's third tab: the Text tab's questions with one more option after each
question's own, "Bilmiyorum" ("I don't know"), from results.json's `dont_know` and page_config.json's `dont_know` (the
models not run, with their reasons). One row per model, from its first run, ranked by non-hallucination rate (accuracy
breaks ties), which is the first column; a model with more than one run shows the range over its runs. A plain HTML
table, as on the Page images tab; it needs no JavaScript. The tab ranks nothing on the Text tab and changes none of its
numbers."""

from __future__ import annotations

from typing import Any

import build_page as bp
from sitebuild.site import Site, esc, pct, rel
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
    cut = "no cut-off (no answer has a score)" if derived["cut_off"] is None else f"cut-off {derived['cut_off']:.4f}"
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
    gaps = [shown(model["derived"]["non_hallucination"]) - shown(model["non_hallucination"]) for model in fewer]
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
    several = [model for model in models if model["spread"] and model["spread"]["non_hallucination"]]
    if several:
        widest = max(several, key=lambda model: model["spread"]["non_hallucination"][1] - model["spread"]["non_hallucination"][0])
        low_run, high_run = widest["spread"]["non_hallucination"]
        third += (f" We did not test whether these differences exceed the variation between runs: {name(widest)}'s "
                  f"{len(widest['runs'])} runs with the option range from {p(low_run)} to {p(high_run)}.")
    return first + second + third + "</p>"


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
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">Hallucination</p>
      <h1>The Text tab's {total} questions, with “{option}” as a sixth option</h1>
      <p>Every question of the Text tab gets one more option after its five answers: F, “{option}”, Turkish for “{esc(data["option_en"])}”. It is always the last option, it is never shuffled and it is never correct. The System One instructions get one added sentence: “{esc(data["sentence"])}” Everything else is as on the Text tab: the same {total} scored questions and answer key, one question per request, and each model's own settings from its text run. A wrong answer counts as a hallucination, since the model could have chosen “{option}” instead. Below the table, <a href="#findings">What we found</a> puts the results in words and <a href="#method">Our method</a> gives each rate's formula and how to read it.</p>
      <p>This tab is separate from the leaderboard. It ranks nothing on the Text tab and changes none of its numbers.</p>
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
    </section>"""
    return {PATH: site.page(PATH, "Hallucination",
                            f"The Text tab's {total} questions with a sixth option, “{data['option']}” (I don't know): accuracy, "
                            "attempt rate and non-hallucination rate of the most accurate decision models.", body)}
