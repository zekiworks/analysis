"""PWS-Decisions (pws-decisions/): the site's decision models on Parallel Web Systems' benchmark of dated web facts, three
runs each, from pws-decisions.json (totals written by pws/bench.py's summary step). One chart (accuracy, setups ranked,
in their family's colours) and one table (accuracy with its range, request times, cost, confidence), with notes on what
was run, what was not and why, and what waits. Not part of the Turkish ranking: no other page reads these numbers. The
questions and answers are Parallel's and never published; the JSON holds totals only."""

from __future__ import annotations

import json
from typing import Any

from build_page import long_date
from sitebuild.site import ROOT, Site, esc, family_legend, hbars, pct, rel
from sitebuild.vision import cell, joined

PATH = "pws-decisions/"
TITLE = "PWS-Decisions"
DATA = ROOT / "pws-decisions.json"


def setup_run(site: Site, setup: dict[str, Any]) -> dict[str, Any]:
    """The site's decision setup of a PWS-Decisions setup (provider, model and Perplexity mode, one question per
    request); the build stops unless there is exactly one."""
    found = [run for run in site.runs if site.decision(run) and run["questions_per_request"] == 1
             and (run["provider"], run["model"], run["perplexity_mode"]) ==
             (setup["provider"], setup["model"], setup["perplexity_mode"])]
    if len(found) != 1:
        raise SystemExit(f"pws-decisions.json: {setup['provider']} {setup['model']} matches {len(found)} setups of results.json")
    return found[0]


def named(site: Site, item: dict[str, Any]) -> dict[str, Any]:
    """A not-run entry's setup in results.json (provider and model)."""
    found = [run for run in site.runs if site.decision(run) and (run["provider"], run["model"]) == (item["provider"], item["model"])]
    if len(found) != 1:
        raise SystemExit(f"pws-decisions.json not_run: {item['provider']} {item['model']} matches {len(found)} setups")
    return found[0]


def ms(seconds: float) -> str:
    return f"{1000 * seconds:,.0f}"


def dollars(value: float) -> str:
    return f"${value:,.2f}" if value < 100 else f"${value:,.0f}"


def spread(item: dict[str, float], write: Any) -> str:
    """A mean of three runs with their range, as HTML: the mean, and the lowest to the highest run under it."""
    if write(item["min"]) == write(item["max"]):
        return f'{esc(write(item["mean"]))}<span class="small">each run</span>'
    return f'{esc(write(item["mean"]))}<span class="small">{esc(write(item["min"]))} to {esc(write(item["max"]))}</span>'


def count(value: float) -> str:
    return f"{value:.0f}" if value == int(value) else f"{value:.1f}"


def accuracy_chart(site: Site, data: dict[str, Any], rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    digits = site.config["percent_digits"]
    families = [site.families[run["run"]] for _, run in rows]
    random = data["random_accuracy"]
    chart = hbars([
        {"label": site.row_name(run), "href": rel(PATH, site.model_path(run)),
         "bars": [{"value": setup["accuracy"]["mean"], "colour": family["colour"]}], "marker": random,
         "text": pct(setup["accuracy"]["mean"], digits),
         "title": f"{site.row_name(run)}: {pct(setup['accuracy']['mean'], digits)} mean of {data['runs_per_setup']} runs, "
                  f"{pct(setup['accuracy']['min'], 0)} to {pct(setup['accuracy']['max'], 0)}"}
        for (setup, run), family in zip(rows, families)])
    return (f'<figure class="panel chart-card" id="chart-accuracy"><div class="chart-head"><h2>Accuracy</h2>'
            f'<p class="chart-sub">Share of the {data["questions"]} public questions answered right, mean of '
            f'{data["runs_per_setup"]} runs · higher is better</p></div>{chart}'
            f'<p class="chart-legend">{family_legend(families)} <span>The line on each bar: uniform random guessing, '
            f'{pct(random, digits)}.</span></p></figure>')


def table(site: Site, data: dict[str, Any], rows: list[tuple[dict[str, Any], dict[str, Any]]], upper: dict[str, str]) -> str:
    digits = site.config["percent_digits"]
    sure = data["sure_threshold"]
    heads = [("Accuracy", f"mean of {data['runs_per_setup']} runs, range under it; higher is better"),
             ("Median request", "ms; lower is better"), ("95th percentile request", "ms, nearest rank; lower is better"),
             ("Cost per 1M questions", "list prices; lower is better"),
             ("Probability of the chosen answer", "mean; neither better nor worse on its own"),
             ("Wrong when sure", f"answers at {pct(sure, 0)} or more; lower is better")]
    labels = [f"{head} ({direction})" for head, direction in heads]
    body = []
    for setup, run in rows:
        cost = setup["cost_per_million_questions"]
        mark = f"{upper['mark']} " if setup["perplexity_mode"] else ""
        values = [
            spread(setup["accuracy"], lambda value: pct(value, digits)),
            spread(setup["median_request_seconds"], ms),
            spread(setup["p95_request_seconds"], ms),
            '<span class="nm">Not measured</span>' if cost is None else spread(cost, lambda value: mark + dollars(value)),
        ]
        if "mean_chosen_probability" in setup:
            wrong, held = setup["sure_wrong"], setup["sure"]
            values.append(spread(setup["mean_chosen_probability"], lambda value: f"{value:.3f}"))
            spread_text = "" if wrong["min"] == wrong["max"] else f"; {count(wrong['min'])} to {count(wrong['max'])}"
            values.append(f'{esc(count(wrong["mean"]))}<span class="small">of {esc(count(held["mean"]))} at {pct(sure, 0)} or '
                          f"more{spread_text}</span>")
        else:
            values += ['<span class="nm">No probabilities</span>'] * 2
        name = (f'<td class="model"><a class="model-name" href="{rel(PATH, site.model_path(run))}">{esc(site.row_name(run))}</a>'
                f'<span class="small">{esc(run["access"])}; <code>{esc(setup["request_model"])}</code></span></td>')
        body.append(f"<tr>{name}" + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{esc(direction)}</span></th>' for text, direction in heads)
    return (f'<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr><th scope="col">Setup</th>{head}'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def retried_note(site: Site, rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    """Which setups' requests were retried, and how often over their runs (their request times include the retries),
    and how many requests failed in the end."""
    retried = [f"{esc(site.row_name(run))} {sum(item['retries'] for item in setup['runs']):,}" for setup, run in rows
               if any(item["retries"] for item in setup["runs"])]
    failed = sum(item["errors"] for setup, _ in rows for item in setup["runs"])
    retries = (f"Retries over the three runs: {joined(retried)}; none for the other setups. Their request times include "
               "the retries." if retried else "No request was retried.")
    return f"{retries} {'No request failed.' if not failed else f'{failed:,} requests failed, each scored as wrong.'}"


def pending(site: Site, data: dict[str, Any]) -> str:
    """The setups that wait: Parallel's own API, and the decision models that run on our GPUs (results.json), with what
    Baseten's Base Labs models gave."""
    gpu = [site.row_name(run) for run in site.ranked() if site.decision(run) and run["hardware"] is not None]
    check = data["baseten_check"]
    gaps = {model: check[model] for model in ("baselabs/elephant-1", "baselabs/mammoth-1")}
    return (f'<li>{esc(data["pending"]["parallel"])}</li>'
            f'<li>{esc(data["pending"]["gpu"])} {esc(joined(gpu))}.</li>'
            f'<li>Base Labs\' Elephant-1 and Mammoth-1 are also on Baseten\'s Model API, but not shown to be the same weights: '
            f'on the first {check["questions"]} Turkish questions ({esc(long_date(check["date"]))}) Baseten\'s probabilities differed '
            f'from our runs by up to {gaps["baselabs/elephant-1"]["largest_gap"]:.2f} (Elephant-1) and '
            f'{gaps["baselabs/mammoth-1"]["largest_gap"]:.2f} (Mammoth-1, which chose differently on '
            f'{check["questions"] - gaps["baselabs/mammoth-1"]["same_choice"]} of them). They wait with the GPU setups.</li>')


def build(site: Site) -> dict[str, str]:
    if not DATA.exists():
        return {}
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rows = sorted(((setup, setup_run(site, setup)) for setup in data["setups"]),
                  key=lambda pair: (-pair[0]["accuracy"]["mean"], site.row_name(pair[1]).casefold()))
    digits = site.config["percent_digits"]
    upper = site.config["first_cost_marks"]["upper"]
    best, worst = rows[0], rows[-1]
    above = sum(setup["accuracy"]["mean"] > data["random_accuracy"] for setup, _ in rows)
    dates = data["dates"]
    when = long_date(dates[0]) if dates[0] == dates[-1] else f"{long_date(dates[0])} to {long_date(dates[-1])}"
    reported, parallel = data["reported"]["perplexity"], data["reported"]["parallel"]
    web = data["openai_web"]
    not_run = "".join(f"<li><strong>{esc(site.row_name(named(site, item)))}.</strong> {esc(item['reason'])}</li>"
                      for item in data["not_run"])
    leaderboard = "; ".join(f"{esc(row['name'])} {row['public_percent']:.2f}%" for row in parallel["rows"])
    grounded = [setup for setup, _ in rows if setup["perplexity_mode"]]
    body = f"""    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>PWS-Decisions: the decision models on dated web facts</h1>
      <p>PWS-Decisions is Parallel Web Systems' benchmark of {data['questions']} public English multiple-choice questions whose answers depend on dated facts on the public web. We asked every decision model of the site that an API still serves: {len(rows)} setups, {data['runs_per_setup']} runs each, one question per request. Each setup ran without search, except Perplexity Decider v1.2 with web. This page is not part of the Turkish ranking.</p>
      <p>{esc(site.row_name(best[1]))} got the most right ({pct(best[0]['accuracy']['mean'], digits)}), {esc(site.row_name(worst[1]))} the fewest ({pct(worst[0]['accuracy']['mean'], digits)}). {above} of the {len(rows)} setups beat uniform random guessing ({pct(data['random_accuracy'], digits)}).</p>
      <nav class="face-nav" aria-label="On this page"><a href="#chart-accuracy">Accuracy</a><a href="#results">Every number</a><a href="#not-run">Not run</a><a href="#method">Method</a></nav>
    </section>
    <section class="charts" aria-label="Charts">{accuracy_chart(site, data, rows)}</section>
    <section class="card" id="results">
      <h2>Every number, setup by setup</h2>
      <p class="note">Ranked by mean accuracy. Each value is the mean of the {data['runs_per_setup']} runs, with the lowest and highest run under it. Request times are from our machine. Probabilities: where the API returns them, the mean probability it gave the answer it chose, and how many answers given at least {pct(data['sure_threshold'], 0)} (the site's “sure” threshold) were wrong.</p>
      {table(site, data, rows, upper)}
      <ul class="note">
        <li>{esc(upper['mark'])} {esc(upper['note'])}</li>
        <li>{retried_note(site, rows)}</li>
        <li>Cost: each run's tokens at the runner's list price for the setup, the price the Text tab uses, over its {data['questions']} questions{", plus $" + format(grounded[0]['price']['per_request'], 'g') + " per request with web" if grounded else ""}.</li>
      </ul>
    </section>
    <section class="card" id="not-run">
      <h2>Not run, and why</h2>
      <ul>
        {not_run}
        <li><strong>GPT-6 Luna with web.</strong> OpenAI's Decisions API documents no web option: a request takes only {esc(joined([f"{name}" for name in web['parameters']]))} (<a href="{esc(web['guide'])}">guide</a>, <a href="{esc(web['reference'])}">reference</a>, read {esc(long_date(web['read']))}).</li>
      </ul>
      <h3>Waiting</h3>
      <ul>{pending(site, data)}</ul>
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>Runs on {esc(when)}. Each question went out as PWS-Decisions' own request (its state, and one choice question with its instructions and its choices), with the setup's model name, to the same API and endpoint as the setup's Text tab run. OpenAI's Decisions API takes the same parts under its own names. One question per request, each provider's requests one after another, the providers at the same time. Timeout {data['timeout_seconds']:g} s; the runner's retries (up to {data['retries']['max']}, on {esc(data['retries']['statuses'])}). Scored with PWS-Decisions' own scorer: a refusal, an error or an invalid answer counts as wrong.</p>
      <ul>
        <li>Request time: from sending a request to its answer, retries included, over the requests that got an answer; the median and the 95th percentile by nearest rank.</li>
        <li>Liquid d1 was asked as <code>d1</code>: Liquid's API no longer serves the <code>d1:free</code> name of its Text tab run.</li>
        <li>Perplexity's own figures: {reported['on_percent']}% with web on these questions, with {ms(reported['on_median_ms'] / 1000)} ms at the median and {ms(reported['on_p95_ms'] / 1000)} ms at the 95th percentile from Perplexity's client (<a href="{esc(reported['source'])}">{esc(reported['title'])}</a>, {esc(long_date(reported['published']))}); the {reported['off_percent']}% without is Parallel's leaderboard figure.</li>
        <li>Parallel's leaderboard (public set, mean of three runs, evaluated {esc(long_date(parallel['evaluated']))}): {leaderboard} (<a href="{esc(parallel['source'])}">the benchmark's repository</a>).</li>
        <li>The questions and answers are Parallel's: {esc(data['name'])} version {esc(data['version'])}, gated, for evaluation only. We publish totals only, never a question, an answer or a per-question result.</li>
        <li>What the runs cost us at list prices: {dollars(data['run_cost_usd'])}.</li>
      </ul>
      <p class="note">Download: <a href="{rel(PATH, "pws-decisions.json")}" download>pws-decisions.json</a> (every number on this page, per run). The adapter is <code>pws/bench.py</code> in the repository.</p>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"{len(rows)} decision models on PWS-Decisions, Parallel's benchmark of dated web facts: "
                            "accuracy over three runs, request time, cost and confidence.", body)}
