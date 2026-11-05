"""PWS-Decisions (pws-decisions/): the site's models on Parallel Web Systems' benchmark of dated web facts, three runs
each, from pws-decisions.json (totals written by pws/bench.py's summary step). Three charts in the home page's format
(accuracy with cost and request time beside it, cost, latency: one bar per setup in its family's colour, with web
striped) and one table, with the framing, the provenance, what was not run and why, and what waits. The charts, the
framing and the provenance also show on web-grounding/ (charts, framing, provenance). Not part of the Turkish ranking.
The questions and answers are Parallel's and never published; the JSON holds totals only."""

from __future__ import annotations

import json
from typing import Any

from build_page import long_date
from sitebuild.site import (ROOT, Site, cost_per, cost_switch, cost_tick, cost_words, cost_value, esc, family_legend,
                            hbars, log_axis, pct, rel, seconds_tick)
from sitebuild.vision import cell, joined

PATH = "pws-decisions/"
TITLE = "PWS-Decisions"
DATA = ROOT / "pws-decisions.json"
# The pinned revisions of the runs (~/vision-track/pws-grounding/AUDIT.md section 1): the dataset's Hugging Face commit
# and the commit of Parallel's repository whose scorer (python -m pws_decisions score) scored every run unchanged.
DATASET = "parallel-web/pws-decisions-benchmark"
DATASET_REVISION = "64da0d8a4ec075769abc2b3dc68142fbabb54485"
REPOSITORY = "https://github.com/parallel-web/pws-decisions-benchmark"
SCORER_REVISION = "0f403cf99856ac601c168df171af7ed0020ba222"
# Where Parallel states the random-guess baseline, and how it chose the questions (the README and methodology lines).
BASELINE_SOURCE = f"{REPOSITORY}/blob/{SCORER_REVISION}/README.md#L19"
METHODOLOGY_SOURCE = f"{REPOSITORY}/blob/{SCORER_REVISION}/docs/methodology.md#L13"


def setup_run(site: Site, setup: dict[str, Any]) -> dict[str, Any]:
    """The site's run of a PWS-Decisions setup: the Text tab run it names (run; the same provider and model unless the
    setup names another host of the model, as Baseten's Mammoth-1), else its decision setup (provider, model and
    Perplexity mode, one question per request); the build stops unless there is exactly one."""
    if "run" in setup:
        run = site.by_id.get(setup["run"])
        if run is None or ("host" not in setup and (run["provider"], run["model"]) != (setup["provider"], setup["model"])):
            raise SystemExit(f"pws-decisions.json: run {setup['run']} is not {setup['provider']} {setup['model']}")
        return run
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


def web(setup: dict[str, Any]) -> bool:
    """Whether a setup searched the web (its web flag; rows written before the flag: a Perplexity mode)."""
    return setup.get("web", setup["perplexity_mode"] is not None)


def chat(setup: dict[str, Any]) -> bool:
    return setup.get("group", "decision") == "chat"


def entries(site: Site, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Each setup with its run, family and chart label: its full name, with "chat" for a chat model, its host where the
    setup names one (Baseten, our GPU) and "with web" for a setup that searched where the name does not say so. Ranked by
    mean accuracy."""
    out = []
    for setup in data["setups"]:
        run = setup_run(site, setup)
        name = site.row_name(run)
        marks = ((["chat"] if chat(setup) else []) + ([f"on {setup['host']}"] if setup.get("host") else [])
                 + (["with web"] if web(setup) and "with web" not in name else []))
        out.append({"setup": setup, "run": run, "family": site.families[run["run"]],
                    "label": f"{name} ({', '.join(marks)})" if marks else name})
    return sorted(out, key=lambda item: (-item["setup"]["accuracy"]["mean"], item["label"].casefold()))


def condition(item: dict[str, Any]) -> str:
    """The heading of a setup's rows in the charts: with web search or without."""
    return "With web search" if web(item["setup"]) else "Without search"


def by_condition(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The setups with web search first, then those without, each in the order given (a stable sort), so the charts
    show the two conditions apart under their headings."""
    return sorted(items, key=lambda item: not web(item["setup"]))


def interval(setup: dict[str, Any], digits: int) -> str | None:
    """The 95% bootstrap interval of a setup's mean accuracy over the question sample (the summary step's
    accuracy_ci95), as text, or None where the totals file has none."""
    ci = setup.get("accuracy_ci95")
    return None if ci is None else f"{pct(ci['low'], digits)} to {pct(ci['high'], digits)}"


def ms(seconds: float) -> str:
    return f"{1000 * seconds:,.0f}"


def dollars(value: float) -> str:
    return f"${value:,.2f}" if value < 100 else f"${value:,.0f}"


def spread(item: dict[str, float], write: Any) -> str:
    """A mean of three runs with their range, as HTML: the mean, and the lowest to the highest run under it (write
    returns HTML)."""
    if write(item["min"]) == write(item["max"]):
        return f'{write(item["mean"])}<span class="small">each run</span>'
    return f'{write(item["mean"])}<span class="small">{write(item["min"])} to {write(item["max"])}</span>'


def lower(setup: dict[str, Any]) -> bool:
    """Whether a setup's cost is a lower bound: a web setup whose API reports no search count, so its cost is the tokens
    only (the summary step's cost_lower_bound)."""
    return setup.get("cost_lower_bound", False)


def upper(setup: dict[str, Any]) -> bool:
    """Whether a setup's cost is an upper bound: its search fee counted for every request where the bill counts only
    the searches made (Perplexity's per-request fee)."""
    return not lower(setup) and setup["price"].get("per_request", 0) > 0


def bound(setup: dict[str, Any], mark: str) -> str:
    """The mark before a setup's cost: the upper-bound mark (≤), ≥ for a lower bound, else nothing."""
    return f"{mark} " if upper(setup) else "≥ " if lower(setup) else ""


def search_fee(setup: dict[str, Any]) -> bool:
    """Whether a setup's cost includes a web search fee."""
    price = setup["price"]
    return web(setup) and not lower(setup) and (price.get("per_request", 0) > 0 or price.get("per_search", 0) > 0)


def fee_words(setup: dict[str, Any]) -> str:
    """What a setup's cost counts of the search fee, for a table cell or a tooltip."""
    if lower(setup):
        return "tokens only: the API reports no search count"
    return "includes the web search fee" if search_fee(setup) else "no search fee"


def lower_note(items: list[dict[str, Any]]) -> str:
    """What ≥ means, when a setup's cost is a lower bound: the tokens only, and what each search would add."""
    rows = [item for item in items if lower(item["setup"])]
    if not rows:
        return ""
    adds = "; ".join(f"{item['label']}: {cost_words(item['setup']['price']['per_search'] * 1000)}" for item in rows
                     if item["setup"]["price"].get("per_search"))
    return ("≥ Lower bound: the API reports no search count, so the cost counts the tokens only"
            + (f". Each search per question would add {adds}" if adds else "") + ".")


def cost_html(setup: dict[str, Any], value: float, mark: str) -> str:
    """A cost per question set as the unit switch shows it (cost_value takes dollars per 1,000 questions), with the
    upper- or lower-bound mark where it applies."""
    return cost_value(value / 1000, bound(setup, mark))


def link(site: Site, origin: str, item: dict[str, Any]) -> str:
    return rel(origin, site.model_path(item["run"]))


def marks_legend(items: list[dict[str, Any]], striped: str) -> str:
    """The legend's lines for the striped with-web bars and the chat rows, when the chart has them."""
    out = ""
    if any(web(item["setup"]) for item in items):
        out += f' <span><i class="swatch swatch-web"></i>{striped}</span>'
    if any(chat(item["setup"]) for item in items):
        out += (" <span>(chat): a chat model, asked each question in the benchmark's own words, its answer read from its "
                "reply; the other rows are decision models.</span>")
    return out


def accuracy_chart(site: Site, data: dict[str, Any], items: list[dict[str, Any]], origin: str, anchor: str,
                   mark: str) -> str:
    """Accuracy, one bar per setup in its family's colour (with web striped), the random-guess line on each, and the
    setup's cost and request times beside it."""
    digits = site.config["percent_digits"]
    random = data["random_accuracy"]
    rows = []
    for item in by_condition(items):
        setup = item["setup"]
        accuracy, cost = setup["accuracy"]["mean"], setup["cost_per_million_questions"]
        median, p95 = setup["median_request_seconds"]["mean"], setup["p95_request_seconds"]["mean"]
        priced = "n.m." if cost is None else cost_html(setup, cost["mean"], mark)
        ci = interval(setup, digits)
        rows.append({
            "group": condition(item), "label": item["label"], "family": item["family"]["name"], "href": link(site, origin, item),
            "bars": [{"value": accuracy, "colour": item["family"]["colour"], **({"kind": "web"} if web(setup) else {})}],
            "marker": random,
            "html": f"{esc(pct(accuracy, digits))} | {priced} | {ms(median)} · {ms(p95)}",
            "title": f"{item['label']}: {pct(accuracy, digits)} mean of {data['runs_per_setup']} runs "
                     f"(runs {pct(setup['accuracy']['min'], 0)} to {pct(setup['accuracy']['max'], 0)}"
                     + (f"; 95% interval from the question sample {ci}" if ci else "") + "); "
                     + ("cost not measured" if cost is None else cost_words(cost["mean"] / 1000, bound(setup, mark)))
                     + f"; median request {ms(median)} ms, 95th percentile {ms(p95)} ms"})
    chart = hbars(rows, head=("Accuracy | Cost | Median · p95 ms", "Acc | Cost | ms"))
    return (f'<figure class="panel chart-card chart-wide" id="{anchor}"><div class="chart-head"><h2>Accuracy</h2>'
            f'<p class="chart-sub">Share of the {data["questions"]} public questions answered right, the mean of our '
            f'{data["runs_per_setup"]} runs per setup · higher is better; beside it the cost ({cost_per()}) and the '
            f'median and 95th percentile request time</p>{cost_switch()}</div>{chart}'
            f'<p class="chart-legend">{family_legend([item["family"] for item in items])}'
            f'{marks_legend(items, "With web: the setup searched the web for each question (striped)")} '
            f'<span><i class="swatch swatch-marker"></i>The chance line: Parallel\'s random-guess baseline, {pct(random, 2)} '
            f'(<a href="{BASELINE_SOURCE}">the benchmark\'s README</a>), uniform guessing over each question\'s choices, a '
            f"property of the questions, not a run of ours.</span></p></figure>")


def cost_chart(site: Site, data: dict[str, Any], items: list[dict[str, Any]], origin: str, anchor: str, mark: str,
               note: str) -> str:
    """Cost per question set, log scale, cheapest first: tokens at list prices, plus the web search fee where a setup
    searched (≤ where it is counted per request)."""
    priced = sorted((item for item in items if item["setup"]["cost_per_million_questions"] is not None),
                    key=lambda item: (item["setup"]["cost_per_million_questions"]["mean"], item["label"].casefold()))
    place, axis = log_axis([item["setup"]["cost_per_million_questions"]["mean"] / 1000 for item in priced], lambda value: value)
    write = axis.pop("tick")
    rows = []
    for item in by_condition(priced):
        setup = item["setup"]
        value = setup["cost_per_million_questions"]["mean"]
        fee = " incl. search" if search_fee(setup) else " tokens only" if lower(setup) else ""
        rows.append({
            "group": condition(item), "label": item["label"], "family": item["family"]["name"], "href": link(site, origin, item),
            "bars": [{"value": place(value / 1000), "colour": item["family"]["colour"], **({"kind": "web"} if web(setup) else {})}],
            "html": cost_html(setup, value, mark) + esc(fee),
            "title": f"{item['label']}: " + cost_words(value / 1000, bound(setup, mark))
                     + f"; {fee_words(setup)} ({setup['price']['basis']})"})
    unpriced = [item["label"] for item in items if item["setup"]["cost_per_million_questions"] is None]
    chart = hbars(rows, head=("Cost", "Cost"), tick=lambda offset: cost_tick(write(offset)), **axis)
    lines = ["Without web: each run's tokens at the setup's list price, no search fee.",
             "With web: the same, plus the provider's web search fee (“incl. search”)."]
    if any(upper(item["setup"]) for item in priced):
        lines.append(f"{mark} {note}")
    if lower_note(priced):
        lines.append(lower_note(priced))
    if unpriced:
        lines.append(f"Not measured: {joined(unpriced)}.")
    return (f'<figure class="panel chart-card chart-wide" id="{anchor}"><div class="chart-head"><h2>Cost</h2>'
            f'<p class="chart-sub">Estimated dollars {cost_per()}, the mean of {data["runs_per_setup"]} runs, log scale; '
            f'with web search, then without, each cheapest first · lower is better</p>{cost_switch()}</div>{chart}'
            f'<p class="chart-legend">{family_legend([item["family"] for item in priced])}'
            f'{marks_legend(priced, "With web (striped)")} '
            + " ".join(f"<span>{esc(line)}</span>" for line in lines) + "</p></figure>")


def latency_chart(site: Site, data: dict[str, Any], items: list[dict[str, Any]], origin: str, anchor: str) -> str:
    """Median request time per setup, log scale, fastest first, with the 95th percentile as the line on each bar."""
    ordered = sorted(items, key=lambda item: (item["setup"]["median_request_seconds"]["mean"], item["label"].casefold()))
    values = [item["setup"][key]["mean"] for item in ordered for key in ("median_request_seconds", "p95_request_seconds")]
    place, axis = log_axis(values, seconds_tick)
    rows = []
    for item in by_condition(ordered):
        setup = item["setup"]
        median, p95 = setup["median_request_seconds"]["mean"], setup["p95_request_seconds"]["mean"]
        rows.append({
            "group": condition(item), "label": item["label"], "family": item["family"]["name"], "href": link(site, origin, item),
            "bars": [{"value": place(median), "colour": item["family"]["colour"], **({"kind": "web"} if web(setup) else {})}],
            "marker": place(p95), "text": f"{ms(median)} · {ms(p95)} ms",
            "title": f"{item['label']}: median {ms(median)} ms, 95th percentile {ms(p95)} ms per request, the mean of "
                     f"{data['runs_per_setup']} runs"})
    chart = hbars(rows, head=("Median · p95", "Med · p95"), **axis)
    return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>Latency</h2>'
            f'<p class="chart-sub">Median time per request (the bar) and 95th percentile by nearest rank (the line), one '
            f'question per request, from our machine, the mean of {data["runs_per_setup"]} runs, log scale; with web '
            f'search, then without, each fastest first · lower is better</p></div>{chart}'
            f'<p class="chart-legend">{family_legend([item["family"] for item in ordered])}'
            f'{marks_legend(ordered, "With web (striped)")} '
            '<span><i class="swatch swatch-marker"></i>95th percentile</span> <span>Request times include the network and '
            "any retries.</span></p></figure>")


def charts(site: Site, data: dict[str, Any], items: list[dict[str, Any]], origin: str, prefix: str,
           measures: bool = False) -> str:
    """Accuracy, Cost and Latency; with measures, each in its Measure section (the id the view bar's Measure row links
    to: pws-decisions/, where these are the page's own charts)."""
    upper_mark = site.config["first_cost_marks"]["upper"]
    cards = [("accuracy", "Accuracy", accuracy_chart(site, data, items, origin, f"{prefix}accuracy", upper_mark["mark"])),
             ("cost", "Cost", cost_chart(site, data, items, origin, f"{prefix}cost", upper_mark["mark"],
                                         upper_note(items, upper_mark))),
             ("latency", "Latency", latency_chart(site, data, items, origin, f"{prefix}latency"))]
    if not measures:
        return "".join(card for _, _, card in cards)
    return "".join(f'<section class="measure" id="{key}" aria-label="{title}">{card}</section>' for key, title, card in cards)


def upper_note(items: list[dict[str, Any]], upper_mark: dict[str, str]) -> str:
    """What the upper-bound mark means here: Perplexity's per-request search (the site's note), when a setup has it."""
    return upper_mark["note"] if any(upper(item["setup"]) for item in items) else ""


def framing(data: dict[str, Any]) -> str:
    """The one sentence on what the comparison is, and is not."""
    return (f'<p class="framing"><strong>What this measures.</strong> Parallel Web Systems made PWS-Decisions. This is an '
            f"end-to-end comparison of API setups with and without web search on its {data['questions']} public questions, "
            f'which Parallel chose “for their difficulty and alignment with customer outcomes” (<a href="{METHODOLOGY_SOURCE}">'
            "its methodology</a>), around its customers' needs for current facts from the web. It is not a general ranking "
            "of models: without search, most setups score near random guessing, because the answers depend on dated web "
            "facts they were not given.</p>")


def provenance(data: dict[str, Any]) -> str:
    """Where the numbers come from: the dataset and scorer revisions, the runs and their dates, and what is published."""
    runs = [run for setup in data["setups"] for run in setup["runs"]]
    started, ended = min(run["started"] for run in runs), max(run["ended"] for run in runs)
    days = sorted({started[:10], ended[:10]})
    when = (f"{long_date(days[0])}, {started[11:16]} to {ended[11:16]} UTC" if len(days) == 1 else
            f"{long_date(days[0])} to {long_date(days[-1])}")
    errors, missing = sum(run["errors"] for run in runs), sum(run["missing"] for run in runs)
    return (f'<dl class="facts provenance">'
            f'<dt>Dataset</dt><dd>{esc(data["name"])} {esc(data["version"])}, Hugging Face <code>{DATASET}</code> at '
            f'<code title="{DATASET_REVISION}">{DATASET_REVISION[:12]}</code></dd>'
            f'<dt>Scorer</dt><dd>Parallel\'s own (<code>python -m pws_decisions score</code>), unchanged, '
            f'<a href="{REPOSITORY}/tree/{SCORER_REVISION}"><code>{SCORER_REVISION[:12]}</code></a></dd>'
            f'<dt>Runs</dt><dd>{data["runs_per_setup"]} per setup, {len(runs)} in all; {errors:,} errors, {missing:,} '
            f"missing answers</dd>"
            f"<dt>Run dates</dt><dd>{esc(when)}</dd>"
            f"<dt>Published</dt><dd>Totals only: no question, answer or per-question result</dd></dl>")


def table(site: Site, data: dict[str, Any], items: list[dict[str, Any]], mark: str) -> str:
    digits = site.config["percent_digits"]
    sure = data["sure_threshold"]
    heads = [("Accuracy", f"mean of {data['runs_per_setup']} runs; under it the runs' range and the 95% interval from "
                          "the question sample; higher is better"),
             ("Median request", "ms; lower is better"), ("95th percentile request", "ms, nearest rank; lower is better"),
             ("Cost", f"{cost_per()}, list prices; lower is better"),
             ("Probability of the chosen answer", "mean; neither better nor worse on its own"),
             ("Wrong when sure", f"answers at ≥{pct(sure, 0)}, wrong of all, over the {data['runs_per_setup']} runs; "
                                 "lower is better")]
    labels = [f"{head} ({direction})" for head, direction in heads]
    plain = [f"{head}" for head, _ in heads]
    body = []
    for item in items:
        setup, run = item["setup"], item["run"]
        cost = setup["cost_per_million_questions"]
        fee = fee_words(setup)
        values = [
            accuracy_cell(setup, digits),
            spread(setup["median_request_seconds"], ms),
            spread(setup["p95_request_seconds"], ms),
            '<span class="nm">Not measured</span>' if cost is None else
            spread(cost, lambda value: cost_html(setup, value, mark)) + f'<span class="small">{fee}</span>',
        ]
        if "mean_chosen_probability" in setup:
            stated = '<span class="small">stated by the model</span>' if setup.get("confidence_kind") == "stated" else ""
            values.append(spread(setup["mean_chosen_probability"], lambda value: f"{value:.3f}") + stated)
            values.append(sure_cell(setup, sure))
        else:
            values += ['<span class="nm">No probabilities</span>'] * 2
        access = setup.get("access", run["access"])
        name = (f'<td class="model">{site.icon(run)}<a class="model-name" href="{rel(PATH, site.model_path(run))}" '
                f'title="{esc(site.detail(run))}">{esc(item["label"])}</a>'
                f'<span class="small">{esc(access)}; <code>{esc(setup["request_model"])}</code></span></td>')
        body.append(f"<tr>{name}" + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{text}<span class="small">{direction}</span></th>'
                   for text, direction in zip(plain, [direction for _, direction in heads]))
    return (f'<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr><th scope="col">Setup</th>{head}'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def accuracy_cell(setup: dict[str, Any], digits: int) -> str:
    """A setup's mean accuracy, with the lowest to highest run (run to run) and, where the totals file has it, the 95%
    bootstrap interval over the questions (the uncertainty from the question sample) as separate lines."""
    accuracy = setup["accuracy"]
    runs = ("each run" if pct(accuracy["min"], digits) == pct(accuracy["max"], digits) else
            f"runs {pct(accuracy['min'], digits)} to {pct(accuracy['max'], digits)}")
    ci = interval(setup, digits)
    return (f'{esc(pct(accuracy["mean"], digits))}<span class="small">{esc(runs)}</span>'
            + (f'<span class="small">95% interval {esc(ci)} (question sample)</span>' if ci else ""))


def sure_cell(setup: dict[str, Any], sure: float) -> str:
    """The answers given at the sure threshold or more over a setup's runs, and how many of them were wrong: integer
    totals over the runs, or that there were none."""
    held = sum(run["confidence"]["sure"] for run in setup["runs"] if run.get("confidence"))
    wrong = sum(run["confidence"]["sure_wrong"] for run in setup["runs"] if run.get("confidence"))
    if not held:
        return f'<span class="nm">No answers at ≥{esc(pct(sure, 0))}</span>'
    return f'{wrong:,}<span class="small">of {held:,}</span>'


def retried_note(items: list[dict[str, Any]]) -> str:
    """Which setups' requests were retried, and how often over their runs (their request times include the retries),
    and how many requests failed in the end."""
    retried = [f"{esc(item['label'])} {sum(run['retries'] for run in item['setup']['runs']):,}" for item in items
               if any(run["retries"] for run in item["setup"]["runs"])]
    failed = sum(run["errors"] for item in items for run in item["setup"]["runs"])
    retries = (f"Retries over the three runs: {joined(retried)}; none for the other setups. Their request times include "
               "the retries." if retried else "No request was retried.")
    return f"{retries} {'No request failed.' if not failed else f'{failed:,} requests failed, each scored as wrong.'}"


def pending(site: Site, data: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """The setups that wait: Parallel's own API, and the decision models that run on our GPUs (results.json), with what
    Baseten's Base Labs models gave (Mammoth-1 leaves the list once its Baseten setup is in)."""
    gpu = [site.row_name(run) for run in site.ranked() if site.decision(run) and run["hardware"] is not None]
    check = data["baseten_check"]
    gaps = {model: check[model] for model in ("baselabs/elephant-1", "baselabs/mammoth-1")}
    when = f'on the first {check["questions"]} Turkish questions ({esc(long_date(check["date"]))})'
    if any(item["setup"].get("host") == "Baseten" for item in items):
        baseten = (f"<li>Base Labs' Elephant-1 is also on Baseten's Model API, but not shown to be the same weights: {when} "
                   f"Baseten's probabilities differed from our runs by up to {gaps['baselabs/elephant-1']['largest_gap']:.2f}. "
                   "It waits with the GPU setups.</li>")
    else:
        baseten = (f"<li>Base Labs' Elephant-1 and Mammoth-1 are also on Baseten's Model API, but not shown to be the same "
                   f"weights: {when} Baseten's probabilities differed from our runs by up to "
                   f"{gaps['baselabs/elephant-1']['largest_gap']:.2f} (Elephant-1) and "
                   f"{gaps['baselabs/mammoth-1']['largest_gap']:.2f} (Mammoth-1, which chose differently on "
                   f"{check['questions'] - gaps['baselabs/mammoth-1']['same_choice']} of them). They wait with the GPU "
                   "setups.</li>")
    return ("<li>Parallel's own Decisions API: not run, no API key available to us yet.</li>"
            f"<li>Decision models on our GPUs: running now, added when done ({esc(joined(gpu))}).</li>" + baseten)


def load(site: Site) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """pws-decisions.json and its setups (entries), or None without the file."""
    if not DATA.exists():
        return None
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data, entries(site, data)


def summary_cards(items: list[dict[str, Any]], digits: int) -> str:
    """The first screen's cards, among the decision models (the chat rows are their own comparison in the charts): the
    best with web search, the same model without it, and the best without search (nothing without both kinds)."""
    decisions = [item for item in items if not chat(item["setup"])]
    searched = [item for item in decisions if web(item["setup"])]
    unsearched = [item for item in decisions if not web(item["setup"])]
    if not searched or not unsearched:
        return ""
    best = max(searched, key=lambda item: item["setup"]["accuracy"]["mean"])
    same = next((item for item in unsearched if (item["setup"]["provider"], item["setup"]["model"]) ==
                 (best["setup"]["provider"], best["setup"]["model"])), None)
    other = max(unsearched, key=lambda item: item["setup"]["accuracy"]["mean"])
    cards = [(best["label"], "with web search", best)]
    if same is not None:
        cards.append(("The same model without web", same["label"], same))
    cards.append(("Best decision model without search", other["label"], other))
    return '<div class="result-cards">' + "".join(
        f'<div class="result-card"><h2>{esc(title)}</h2><p class="result-main">{esc(pct(item["setup"]["accuracy"]["mean"], digits))}'
        f'</p><p class="result-cost">{esc(note)}</p></div>' for title, note, item in cards) + "</div>"


def chance_method(data: dict[str, Any]) -> str:
    """How the random-guess baseline is computed: from the questions' choice counts where the totals file has them."""
    counts = data.get("choice_counts")
    if counts:
        terms = " + ".join(f"{number} × 1/{choices}" for choices, number in sorted(counts.items(), key=lambda pair: int(pair[0])))
        return (f"The chance line, {pct(data['random_accuracy'], 2)}: the mean over the {data['questions']} questions of 1 / "
                f"the number of choices, ({terms}) / {data['questions']}.")
    return (f"The chance line, {pct(data['random_accuracy'], 2)}: the mean over the {data['questions']} questions of 1 / the "
            "number of choices, as Parallel's README gives it.")


def build(site: Site) -> dict[str, str]:
    loaded = load(site)
    if loaded is None:
        return {}
    data, items = loaded
    digits = site.config["percent_digits"]
    upper_mark = site.config["first_cost_marks"]["upper"]
    above = sum(item["setup"]["accuracy"]["mean"] > data["random_accuracy"] for item in items)
    boot = data.get("bootstrap")
    reported, parallel = data["reported"]["perplexity"], data["reported"]["parallel"]
    openai_web = data["openai_web"]
    not_run = "".join(f"<li><strong>{esc(site.row_name(named(site, item)))}.</strong> {esc(item['reason'])}</li>"
                      for item in data["not_run"])
    leaderboard = "; ".join(f"{esc(row['name'])} {row['public_percent']:.2f}%" for row in parallel["rows"])
    searched = [item["label"] for item in items if web(item["setup"])]
    chats = sum(chat(item["setup"]) for item in items)
    decisions = len(items) - chats
    who = (f"{decisions} decision model setups" + (f" and {chats} chat model setups" if chats else ""))
    fees = sorted({format(item["setup"]["price"]["per_request"], "g") for item in items
                   if web(item["setup"]) and item["setup"]["price"].get("per_request", 0) > 0})
    body = f"""    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>PWS-Decisions: the site's models on dated web facts</h1>
      <p>PWS-Decisions is Parallel Web Systems' benchmark of {data['questions']} public English multiple-choice questions whose answers depend on dated facts on the public web. We asked {who} that an API still serves, {data['runs_per_setup']} runs each, one question per request. {"With web search: " + esc(joined(searched)) + "; every other setup answered without search." if searched else "Every setup answered without search."} This page is not part of the Turkish ranking.</p>
      {summary_cards(items, digits)}
      {framing(data)}
      <p>{above} setups have a mean accuracy above the {pct(data['random_accuracy'], digits)} chance line (Parallel's random-guess baseline, not a run of ours); every accuracy here is the mean of our {data['runs_per_setup']} runs.</p>
      {provenance(data)}
      <nav class="face-nav" aria-label="On this page"><a href="#accuracy">Accuracy</a><a href="#cost">Cost</a><a href="#latency">Latency</a><a href="#results">Every number</a><a href="#not-run">Not run</a><a href="#method">Method</a></nav>
    </section>
    <section class="charts" aria-label="Charts">{charts(site, data, items, PATH, "chart-", measures=True)}</section>
    <section class="card" id="results">
      <h2>Every number, setup by setup</h2>
      <p class="note">Ranked by mean accuracy. Each value is the mean of the {data['runs_per_setup']} runs, with the lowest and highest run under it{"; under accuracy also the 95% interval from the question sample" if boot else ""}. Request times are from our machine. Probabilities: where the API returns them, the mean probability it gave the answer it chose, and how many answers given at {pct(data['sure_threshold'], 0)} or more (the site's “sure” threshold) were wrong, over the {data['runs_per_setup']} runs.</p>
      {cost_switch()}
      {table(site, data, items, upper_mark['mark'])}
      <ul class="note">
        {f"<li>{esc(upper_mark['mark'])} {esc(upper_note(items, upper_mark))}</li>" if upper_note(items, upper_mark) else ""}
        {f"<li>{esc(lower_note(items))}</li>" if lower_note(items) else ""}
        <li>{retried_note(items)}</li>
        <li>Cost: each run's tokens at the runner's list price for the setup, the price the Text tab uses, over its {data['questions']} questions{", plus the web search fee for setups with web" + (" ($" + " or $".join(fees) + " per request for Perplexity)" if fees else "") if searched else ""}.</li>
      </ul>
    </section>
    <section class="card" id="not-run">
      <h2>Not run, and why</h2>
      <ul>
        {not_run}
        <li><strong>GPT-6 Luna with web.</strong> OpenAI's Decisions API documents no web option: a request takes only {esc(joined([f"{name}" for name in openai_web['parameters']]))} (<a href="{esc(openai_web['guide'])}">guide</a>, <a href="{esc(openai_web['reference'])}">reference</a>, read {esc(long_date(openai_web['read']))}).</li>
      </ul>
      <h3>Waiting</h3>
      <ul>{pending(site, data, items)}</ul>
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>Each question went out as PWS-Decisions' own request (its state, and one choice question with its instructions and its choices), with the setup's model name, to the same API and endpoint as the setup's Text tab run. OpenAI's Decisions API takes the same parts under its own names. One question per request, each provider's requests one after another, the providers at the same time. Timeout {data['timeout_seconds']:g} s; the runner's retries (up to {data['retries']['max']}, on {esc(data['retries']['statuses'])}). Scored with PWS-Decisions' own scorer: a refusal, an error or an invalid answer counts as wrong.</p>
      <ul>
        <li>Request time: from sending a request to its answer, retries included, over the requests that got an answer; the median and the 95th percentile by nearest rank.</li>
        <li>{esc(chance_method(data))}</li>
        {f"<li>The 95% interval: {boot['resamples']:,} resamples of the {data['questions']} questions with replacement (seed {boot['seed']}), each question scored as the mean of its {data['runs_per_setup']} runs' correctness (a missing answer is wrong); the 2.5th and 97.5th percentiles of the resampled accuracy. It is the uncertainty from the question sample; the lowest to highest run is the run-to-run range.</li>" if boot else ""}
        <li>Liquid d1 was asked as <code>d1</code>: Liquid's API no longer serves the <code>d1:free</code> name of its Text tab run.</li>
        <li>Perplexity's own figures: {reported['on_percent']}% with web on these questions, with {ms(reported['on_median_ms'] / 1000)} ms at the median and {ms(reported['on_p95_ms'] / 1000)} ms at the 95th percentile from Perplexity's client (<a href="{esc(reported['source'])}">{esc(reported['title'])}</a>, {esc(long_date(reported['published']))}); the {reported['off_percent']}% without is Parallel's leaderboard figure.</li>
        <li>Parallel's leaderboard (public set, mean of three runs, evaluated {esc(long_date(parallel['evaluated']))}): {leaderboard} (<a href="{esc(parallel['source'])}">the benchmark's repository</a>).</li>
        <li>The questions and answers are Parallel's: {esc(data['name'])} version {esc(data['version'])}, gated, for evaluation only. We publish totals only, never a question, an answer or a per-question result.</li>
        <li>What the runs cost us at list prices: {dollars(data['run_cost_usd'])}.</li>
      </ul>
      <p class="note">Download: <a href="{rel(PATH, "pws-decisions.json")}" download>pws-decisions.json</a> (every number on this page, per run). The adapter is <code>pws/bench.py</code> in the repository.</p>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"{len(items)} setups on PWS-Decisions, Parallel's benchmark of dated web facts: "
                            "accuracy over three runs, cost, request time and confidence.", body)}
