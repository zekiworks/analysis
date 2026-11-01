"""I don't know option (dont-know/), the site's third tab: the Text tab's questions with one more option after each
question's own, "Bilmiyorum" ("I don't know"), from results.json's `dont_know` and page_config.json's `dont_know` (the
models not run, with their reasons). One row per model, from its first run, ranked by accuracy; a model with more than
one run shows the range over its runs. A plain HTML table, as on the Page images tab; it needs no JavaScript. The tab
ranks nothing on the Text tab and changes none of its numbers."""

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
        ("Accuracy", "higher is better"),
        ("Attempt rate", f"higher means it answers more often; {NEUTRAL}"),
        ("Non-hallucination rate", "higher is better"),
        ("Derived non-hallucination rate", "from the 5-option text run; higher is better"),
        (f"Mean probability of “{option}”", f"higher means more probability on “I don't know”; {NEUTRAL}"),
        ("Text accuracy with five options", "the Text tab's number; higher is better"),
        ("Runs", "range over the runs where more than one"),
    )


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
            for key, name in (("accuracy", "Accuracy"), ("attempt_rate", "Attempt rate"),
                              ("non_hallucination", "Non-hallucination"), ("mean_dont_know_probability", "Mean probability"))
        ]
        changed = model["answers_changed"]
        ranges.append(f"{changed:,} answer{'' if changed == 1 else 's'} changed between runs")
        runs_text = run_span(model["runs"]) + "".join(f'<span class="small">{item}</span>' for item in ranges)
    values = [
        f'{percent(model["accuracy"])}<span class="small">{model["right"]:,} of {total:,} right</span>',
        f'{percent(model["attempt_rate"])}<span class="small">{model["right"] + model["wrong"]:,} answered, '
        f'{model["dont_know"]:,} “{esc(option)}”{invalid}</span>',
        f'{percent(model["non_hallucination"])}<span class="small">{model["dont_know"]:,} “{esc(option)}” of '
        f'{model["dont_know"] + model["wrong"]:,} not right</span>',
        f'{percent(derived["non_hallucination"])}<span class="small">{cut}, attempt rate {percent(derived["attempt_rate"])}</span>',
        percent(model["mean_dont_know_probability"]),
        f'{percent(model["original_accuracy"])}<span class="small"><a href="{rel(PATH, site.model_path(run))}">run {run["run"]}</a></span>',
        runs_text,
    ]
    return f"<tr>{model_cell(site, model)}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>"


def table(site: Site, data: dict[str, Any]) -> str:
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(direction)}</span></th>'
                   for name, direction in columns(data["option"]))
    rows = "".join(row(site, data, model) for model in data["models"])
    return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f"</thead><tbody>{rows}</tbody></table></div>")


def not_run(items: list[dict[str, Any]]) -> str:
    """The models chosen but not run, each with its reason (page_config.json's dont_know.not_run)."""
    if not items:
        return ""
    lines = "".join(f"<li><strong>{esc(item['name'])}</strong>: {esc(item['reason'].removeprefix('Not run: '))}</li>" for item in items)
    return f'<h3 class="board-group">Not run</h3><ul>{lines}</ul>'


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
      <p class="eyebrow">I don't know option</p>
      <h1>The Text tab's {total} questions, with “{option}” as a sixth option</h1>
      <p>Every question of the Text tab gets one more option after its five answers: F, “{option}”, Turkish for “{esc(data["option_en"])}”. It is always the last option, it is never shuffled and it is never correct. The System One instructions get one added sentence: “{esc(data["sentence"])}” Everything else is as on the Text tab: the same {total} scored questions and answer key, one question per request, and each model's own settings from its text run.</p>
      <p>This tab is separate from the leaderboard. It ranks nothing on the Text tab and changes none of its numbers.</p>
      <p>The models: {esc(SELECTION)}. Each has one full run; a model whose repeated text runs changed answers gets five.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page, under <code>dont_know</code>) and <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each run's answers, under <code>dont_know_runs</code>).</p>
    </section>
    <section class="card" id="results">
      <h2>Results</h2>
      <p class="note">Ranked by accuracy, highest first. Each row shows the model's first run{"; under Runs, a model with more than one run (" + esc(joined(several)) + ") shows the range over its runs and how many answers changed between them" if several else ""}. Out of all {total} questions: accuracy counts the right answers; the attempt rate counts the right and wrong answers; the non-hallucination rate is the share of “{option}” among the answers that were not right (“{option}” plus wrong).</p>
      {table(site, data)}
      {not_run(site.config["dont_know"]["not_run"])}
    </section>
    <section class="card method-notes">
      <h2>How it was run</h2>
      <h3>The option and the instructions</h3>
      <p>The added option's exact text is “{option}”. It is lettered after the question's own options, and the answer key is unchanged. The full System One instructions:</p>
      <blockquote><p>{esc(data["instructions"])}</p></blockquote>
      <p>Prompt version {esc(data["prompt_version"])} (a hash of the prompts with these instructions and this option, computed as for the Text tab's prompt version).</p>
      <h3>Counts</h3>
      <p>An answer is right, wrong, “{option}” or invalid. An invalid answer counts as neither right, wrong nor “{option}”. The mean probability of “{option}” is the probability the model gave that option, averaged over its answers that report option probabilities.</p>
      <h3>Derived non-hallucination rate</h3>
      <p>For comparison, each model's run with five options (its run on the Text tab, on the same questions) is made to abstain by its own confidence: it answers only where its score reaches a cut-off and abstains on the rest. The cut-off is the one whose attempt rate comes nearest the attempt rate of the run with “{option}”; on a tie, the higher cut-off. An answer without a score never counts as an attempt. The derived non-hallucination rate is then the abstentions over the abstentions plus the wrong answers. The table shows the cut-off and the attempt rate it reached.</p>
      <h3>Repeats</h3>
      <p>One full run per model. A model whose repeated text runs changed answers gets five runs with the option. Those runs form a repeat set of their own and are never mixed with the Text tab's runs. The table shows the first run; the range covers all of them, and the changed answers are the scored questions whose answer differs between the runs.</p>
    </section>"""
    return {PATH: site.page(PATH, "I don't know option",
                            f"The Text tab's {total} questions with a sixth option, “{data['option']}” (I don't know): accuracy, "
                            "attempt rate and non-hallucination rate of the most accurate decision models.", body)}
