"""PWS-Decisions (pws-decisions/): the site's models on Parallel Web Systems' benchmark of dated web facts, three runs
each, from pws-decisions.json (totals written by pws/bench.py's summary step). Three charts in the home page's format
(accuracy with cost and request time beside it, cost, latency: one bar per setup in its family's colour, with web
striped) and one table, with the framing, the provenance, whether a setup could score without knowing the facts (habits,
when the file has it, with a note beside each setup its habits explain), the “I don't know” runs when the file has them (dont_know),
what was not run and why, and what waits. The charts (decision models only), the framing, the provenance and the
“I don't know” runs also show on web-grounding/. Not part of the Turkish ranking.
The questions and answers are Parallel's and never published; the JSON holds totals only."""

from __future__ import annotations

import json
import math
import statistics
from typing import Any

from build_page import long_date
from sitebuild.site import (DECISION_ONLY, ROOT, Site, chat_note, cost_per, cost_switch, cost_tick, cost_words, cost_value,
                            esc, family_legend, hbars, log_axis, pct, rel, seconds_tick)
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


def models(setup: dict[str, Any]) -> str:
    """The view bar's groups a setup's rows show in (data-models): all, and its own."""
    return "all chat" if chat(setup) else "all decision"


# The models a CLI handed requests to, as the page names them (pws/bench.py's stand_in).
STAND_IN_NAMES = {"claude-opus-4-8": "Claude Opus 4.8"}


def stand_in_words(setup: dict[str, Any]) -> str | None:
    """The requests of a setup's runs that another model answered, which the scorer counted as failures."""
    handed = setup.get("stand_in")
    if not handed:
        return None
    total = sum(handed["requests"])
    names = " and ".join(STAND_IN_NAMES.get(model, model) for model in handed["models"])
    return f"{total} {'request' if total == 1 else 'requests'} handed to {names}, counted wrong"


def setup_notes(setup: dict[str, Any]) -> str:
    """A setup's method note (what its CLI adds) and cost note (what its estimate leaves out), as one sentence each."""
    return " ".join(f"{text[0].upper()}{text[1:]}." for text in (setup.get("method_note"), setup.get("cost_note")) if text)


def cost_kind(setup: dict[str, Any]) -> str:
    """What a setup's cost is: an API usage cost estimate (list price × recorded usage, not the provider's bill), an
    API-equivalent estimate (a subscription), or a list-price estimate (a model on our GPU)."""
    return setup.get("cost_kind") or "API usage cost estimate"



def entries(site: Site, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Each setup with its run, family, view bar groups (models: "all decision" or "all chat") and chart label: its full
    name, with "chat" for a chat model, its interface where the setup names one (CLI, API: two rows of one model never
    read the same), its host where the setup names one (Baseten, our GPU), "with web" for a setup that searched where
    the name does not say so, and the requests another model answered (stand_in_words), so a mixed-model run never
    reads as one model's. Ranked by mean accuracy."""
    out = []
    for setup in data["setups"]:
        run = setup_run(site, setup)
        name = site.row_name(run)
        # The Text tab's route label ("GPT-6 Luna (chat API)", set apart from the Decisions API row) gives way to the
        # setup's own interface here, so a row never reads "(chat API) (chat, CLI)".
        if setup.get("interface") and name.endswith(" (chat API)"):
            name = name.removesuffix(" (chat API)")
        twins = [other for other in data["setups"] if other is not setup and other["model"] == setup["model"]
                 and other.get("host") == setup.get("host") and web(other) == web(setup)
                 and other.get("interface") == setup.get("interface") and other.get("reasoning") != setup.get("reasoning")]
        marks = ((["chat"] if chat(setup) else []) + ([setup["interface"]] if setup.get("interface") else [])
                 + ([f"reasoning {setup['reasoning']}"] if twins and setup.get("reasoning") else [])
                 + ([f"on {setup['host']}"] if setup.get("host") else [])
                 + (["with web"] if web(setup) and "with web" not in name else []))
        inside = "; ".join(part for part in (", ".join(marks), stand_in_words(setup)) if part)
        label = f"{name} ({inside})" if inside else name
        out.append({"setup": setup, "run": run, "family": site.families[run["run"]], "models": models(setup),
                    "label": label})
    return sorted(out, key=lambda item: (-item["setup"]["accuracy"]["mean"], item["label"].casefold()))


def cli_notes(items: list[dict[str, Any]]) -> str:
    """The method section's notes on the CLI setups: a CLI is not only another way to the same model, so each CLI's
    additions (method_note) and any requests it handed to another model (stand_in) are named per setup."""
    lines = []
    for item in items:
        setup = item["setup"]
        if setup.get("interface") != "CLI":
            continue
        parts = [f"{setup['method_note'][0].upper()}{setup['method_note'][1:]}"] if setup.get("method_note") else []
        handed = setup.get("stand_in")
        if handed:
            parts.append(f"Claude Code's safety stops passed {sum(handed['requests'])} of its requests "
                         f"({' + '.join(str(count) for count in handed['requests'])} over the runs, "
                         f"{handed['questions']} {'question' if handed['questions'] == 1 else 'questions'}) to "
                         + " and ".join(STAND_IN_NAMES.get(model, model) for model in handed["models"])
                         + "; the scorer counted each as a failure (a refusal), not with that model's answer")
        if parts:
            lines.append(f"<li data-models=\"all chat\"><strong>{esc(item['label'])}.</strong> {esc('. '.join(parts))}.</li>")
    return "".join(lines)


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


def no_price(setup: dict[str, Any]) -> str:
    """Why a setup has no cost: a setup on our GPU is priced only where an API list price exists for its model."""
    return ("on our GPU, priced only where an API list price exists" if setup.get("host") == "our GPU"
            else "no list price for this setup")


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
        out += (" <span data-models=\"all chat\">(chat): a chat model, asked each question in the benchmark's own words, its answer read from its "
                "reply; the other rows are decision models.</span>")
    return out


def accuracy_chart(site: Site, data: dict[str, Any], items: list[dict[str, Any]], origin: str, anchor: str,
                   mark: str, notes: bool = False) -> str:
    """Accuracy, one bar per setup in its family's colour (with web striped), the random-guess line on each, and the
    setup's cost and request times beside it; with notes, the habits note (habits_note) under a setup's name."""
    digits = site.config["percent_digits"]
    random = data["random_accuracy"]
    rows = []
    for item in by_condition(items):
        setup = item["setup"]
        accuracy, cost = setup["accuracy"]["mean"], setup["cost_per_million_questions"]
        median, p95 = setup["median_request_seconds"]["mean"], setup["p95_request_seconds"]["mean"]
        priced = "no price" if cost is None else cost_html(setup, cost["mean"], mark)
        ci = interval(setup, digits)
        note = habits_note(data, setup) if notes else None
        rows.append({
            "group": condition(item), "label": item["label"], "family": item["family"]["name"], "href": link(site, origin, item),
            "models": item["models"], **({"note": note} if note else {}),
            "bars": [{"value": accuracy, "colour": item["family"]["colour"], **({"kind": "web"} if web(setup) else {})}],
            "marker": random,
            "html": f"{esc(pct(accuracy, digits))} | {priced} | {ms(median)} · {ms(p95)}",
            "title": f"{item['label']}: {pct(accuracy, digits)} mean of {data['runs_per_setup']} runs "
                     f"(runs {pct(setup['accuracy']['min'], 0)} to {pct(setup['accuracy']['max'], 0)}"
                     + (f"; 95% interval from the question sample {ci}" if ci else "") + "); "
                     + (f"no price: {no_price(setup)}" if cost is None else cost_words(cost["mean"] / 1000, bound(setup, mark)))
                     + f"; median request {ms(median)} ms, 95th percentile {ms(p95)} ms"
                     + (f". {setup_notes(setup)}" if setup_notes(setup) else "")
                     + (f". Habits: {note}" if note else "")})
    chart = hbars(rows, head=("Accuracy | Cost | Median · p95 ms", "Acc | Cost | ms"))
    return (f'<figure class="panel chart-card chart-wide" id="{anchor}"><div class="chart-head"><h2>Accuracy</h2>'
            f'<p class="chart-sub">Share of the {data["questions"]} public questions answered right, the mean of our '
            f'{data["runs_per_setup"]} runs per setup · higher is better; beside it the cost ({cost_per()}) and the '
            f'median and 95th percentile request time</p>{cost_switch()}</div>{chart}'
            f'<p class="chart-legend">{family_legend([item["family"] for item in items])}'
            f'{marks_legend(items, "With web: the setup searched the web for each question (striped)")} '
            f'<span><i class="swatch swatch-marker"></i>The chance line: Parallel\'s random-guess baseline, {pct(random, 2)} '
            f'(<a href="{BASELINE_SOURCE}">the benchmark\'s README</a>), uniform guessing over each question\'s choices, a '
            f"property of the questions, not a run of ours.</span>"
            + (f' <span {DECISION_ONLY}>A line under a setup\'s name: its score is at most {round(100 * data["habits"]["explained_margin"], 1):g} '
               f'point above what its answering habits alone would score (<a href="#habits">without knowing the facts</a>).</span>'
               if any("note" in row for row in rows) else "")
            + "</p></figure>")


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
            "models": item["models"],
            "bars": [{"value": place(value / 1000), "colour": item["family"]["colour"], **({"kind": "web"} if web(setup) else {})}],
            "html": cost_html(setup, value, mark) + esc(fee),
            "title": f"{item['label']}: " + cost_words(value / 1000, bound(setup, mark))
                     + f", {cost_kind(setup)}; {fee_words(setup)} ({setup['price']['basis']})"
                     + (f". {setup_notes(setup)}" if setup_notes(setup) else "")})
    unpriced = [item for item in items if item["setup"]["cost_per_million_questions"] is None]
    chart = hbars(rows, head=("Cost", "Cost"), tick=lambda offset: cost_tick(write(offset)), **axis)
    lines = ["Every cost is an estimate: the list price × the tokens and searches our runs recorded, not a provider's "
             "bill; for a subscription run, what the same usage would cost on the API (API-equivalent estimate).",
             "Without web: each run's tokens at the setup's list price, no search fee.",
             "With web: the same, plus the provider's web search fee (“incl. search”)."]
    if any(upper(item["setup"]) for item in priced):
        lines.append(f"{mark} {note}")
    if lower_note(priced):
        lines.append(lower_note(priced))
    if unpriced:
        lines += [f"{item['label']}: no price: {no_price(item['setup'])}." for item in unpriced]
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
            "models": item["models"],
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
    to: pws-decisions/, where these are the page's own charts) and the Accuracy rows with their habits notes."""
    upper_mark = site.config["first_cost_marks"]["upper"]
    cards = [("accuracy", "Accuracy", accuracy_chart(site, data, items, origin, f"{prefix}accuracy", upper_mark["mark"],
                                                     notes=measures)),
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
             ("Cost", f"{cost_per()}, estimate at list prices; lower is better"),
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
            f'<span class="nm">No price</span><span class="small">{esc(no_price(setup))}</span>' if cost is None else
            spread(cost, lambda value: cost_html(setup, value, mark))
            + f'<span class="small">{esc(cost_kind(setup))}; {fee}'
            + (f"; {esc(setup['cost_note'])}" if setup.get("cost_note") else "") + "</span>",
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
                f'<span class="small">{esc(access)}; <code>{esc(setup["request_model"])}</code></span>'
                + (f'<span class="small">{esc(setup["method_note"][0].upper() + setup["method_note"][1:])}.</span>'
                   if setup.get("method_note") else "")
                + (f'<span class="small habits-note">{esc(note)}</span>' if (note := habits_note(data, setup)) else "")
                + "</td>")
        body.append(f'<tr data-models="{item["models"]}">{name}' + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")
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
    """The setups that wait: Parallel's own API, the decision models on our GPUs (results.json) that have no setup on the
    page yet (no line when none is missing), the API setups that are blocked (pws-decisions.json's blocked, each with
    its reason), with what Baseten's Base Labs models gave (Mammoth-1 leaves the list once its Baseten setup is in)."""
    shown = {(item["setup"]["provider"], item["setup"]["model"]) for item in items}
    gpu = [site.row_name(run) for run in site.ranked()
           if site.decision(run) and run["hardware"] is not None and (run["provider"], run["model"]) not in shown]
    check = data["baseten_check"]
    gaps = {model: check[model] for model in ("baselabs/elephant-1", "baselabs/mammoth-1")}
    when = f'on the first {check["questions"]} Turkish questions ({esc(long_date(check["date"]))})'
    if any(item["setup"].get("host") == "Baseten" for item in items):
        elephant_on_gpu = ("baselabs", "baselabs/elephant-1") in shown
        baseten = (f"<li>Base Labs' Elephant-1 is also on Baseten's Model API, but not shown to be the same weights: {when} "
                   f"Baseten's probabilities differed from our runs by up to {gaps['baselabs/elephant-1']['largest_gap']:.2f}. "
                   + ("Not run on Baseten; our GPU run is on the page.</li>" if elephant_on_gpu
                      else "It waits with the GPU setups.</li>"))
    else:
        baseten = (f"<li>Base Labs' Elephant-1 and Mammoth-1 are also on Baseten's Model API, but not shown to be the same "
                   f"weights: {when} Baseten's probabilities differed from our runs by up to "
                   f"{gaps['baselabs/elephant-1']['largest_gap']:.2f} (Elephant-1) and "
                   f"{gaps['baselabs/mammoth-1']['largest_gap']:.2f} (Mammoth-1, which chose differently on "
                   f"{check['questions'] - gaps['baselabs/mammoth-1']['same_choice']} of them). They wait with the GPU "
                   "setups.</li>")
    blocked_keys = {row["setup"] for row in data.get("blocked", [])}
    waiting = unfinished_chat(site, data, blocked_keys)
    chats = (f'<li data-models="all chat">Chat setups without three complete runs yet: {esc(joined(waiting))}; added when '
             "they have them.</li>" if waiting else "")
    blocked = "".join(f'<li data-models="all chat">{esc(setup_name(site, row["setup"]))}: {esc(row["reason"])}.</li>'
                      for row in data.get("blocked", []))
    return ("<li>Parallel's own Decisions API: not run, no API key available to us yet.</li>"
            + (f"<li>Decision models on our GPUs: running now, added when done ({esc(joined(gpu))}).</li>" if gpu else "")
            + blocked + baseten + chats)


def setup_name(site: Site, key: str) -> str:
    """A pws/bench.py setup key's model as the site names it: the name of results.json's runs of that model (the key
    without "-web" and "-api"), with "(API)" for a key with "-api" and "with web" for a key ending in "-web"."""
    model, web_key, api = setup_key(key)
    names = {run["name"] for run in site.runs if run["model"] == model}
    if len(names) != 1:
        raise SystemExit(f"pws-decisions.json: setup {key} matches the names {sorted(names)} in results.json")
    return names.pop() + (" (API)" if api else "") + (" with web" if web_key else "")


def setup_key(key: str) -> tuple[str, bool, bool]:
    """A pws/bench.py setup key's model, whether it searches the web ("-web") and whether it goes through the maker's
    API with a key ("-api")."""
    web_key = key.endswith("-web")
    base = key.removesuffix("-web")
    return base.removesuffix("-api"), web_key, base.endswith("-api")


def unfinished_chat(site: Site, data: dict[str, Any], blocked: set[str] = frozenset()) -> list[str]:
    """The chat setups without three complete runs: those the summary step lists as unfinished, and those with attempts
    set aside (failed_attempts) and no setup of their model and web search among the setups yet; the blocked setups
    (listed with their reason instead) left out."""
    done = {(setup["model"], web(setup), setup.get("interface") == "API") for setup in data["setups"] if chat(setup)}
    keys = [key for key in data["pending"].get("chat_unfinished", []) if key not in blocked]
    keys += [key for key in dict.fromkeys(row["setup"] for row in data.get("failed_attempts", []))
             if key not in keys and key not in blocked and setup_key(key) not in done]
    return [setup_name(site, key) for key in keys]


def attempts_note(site: Site, data: dict[str, Any]) -> str:
    """The attempts set aside whole (failed_attempts: never merged into a run), per setup and attempt: its runs, answers,
    errors and right answers by PWS-Decisions' scorer; nothing without them."""
    found: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in data.get("failed_attempts", []):
        found.setdefault((row["setup"], row["attempt"]), []).append(row)
    if not found:
        return ""
    parts = [f"{setup_name(site, setup)}, {attempt}: {len(rows)} runs, {sum(row['rows'] for row in rows):,} answers, "
             f"{sum(row['errors'] for row in rows):,} errors, {sum(row['correct'] for row in rows):,} right"
             for (setup, attempt), rows in found.items()]
    return f'<li data-models="all chat">Attempts set aside whole, never merged into a run: {esc("; ".join(parts))}.</li>'


def load(site: Site) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """pws-decisions.json and its setups (entries), or None without the file."""
    if not DATA.exists():
        return None
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data, entries(site, data)


def dont_know_block(data: dict[str, Any]) -> dict[str, Any] | None:
    """PWS-Decisions with “I don't know” as an extra choice (the summary step's dont_know: Perplexity Decider v1.2's
    runs off and with web), or None until both arms have their runs."""
    block = data.get("dont_know")
    return block if block and block.get("off") and block.get("on") else None


def dont_know_item(items: list[dict[str, Any]], block: dict[str, Any], side: str) -> dict[str, Any]:
    """The setup entry (label, run, family) of one arm of the “I don't know” runs: the same provider, model and mode."""
    key = (block["provider"], block["model"], block[side]["perplexity_mode"])
    found = [item for item in items if (item["setup"]["provider"], item["setup"]["model"], item["setup"]["perplexity_mode"]) == key]
    if len(found) != 1:
        raise SystemExit(f"pws-decisions.json dont_know: {key} matches {len(found)} setups")
    return found[0]


def count(value: float) -> str:
    """A count, or a mean of counts over runs: a whole number as one, else to one decimal."""
    return f"{round(value):,}" if math.isclose(value, round(value), abs_tol=1e-9) else f"{value:,.1f}"


def dont_know_section(site: Site, data: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """The “I don't know” runs (dont_know_block): per arm the mean right, wrong and “I don't know” answers, and the
    accuracy, answered share, wrong share of the answers and non-hallucination rate, each with the lowest and highest
    run; nothing until both arms have their runs."""
    block = dont_know_block(data)
    if block is None:
        return ""
    digits = site.config["percent_digits"]
    option = block["option"]
    heads = [(f"Right · wrong · {option}", "mean of the runs"), ("Accuracy", "right / questions; higher is better"),
             ("Answered", "(right + wrong) / questions"), ("Wrong of answers", "wrong / (right + wrong); lower is better"),
             ("Non-hallucination", f"{option} / ({option} + wrong); higher is better"),
             ("Errors", "requests without an answer, scored wrong")]
    labels = [f"{head} ({direction})" for head, direction in heads]
    rate = lambda value: esc(pct(value, digits))  # noqa: E731
    body = []
    for side in ("off", "on"):
        arm, item = block[side], dont_know_item(items, block, side)
        values = [esc(" · ".join(count(arm[key]["mean"]) for key in ("right", "wrong", "dont_know")))]
        values += ['<span class="nm">n/a</span>' if arm[key] is None else spread(arm[key], rate)
                   for key in ("accuracy", "answered", "wrong_of_answers", "non_hallucination")]
        values.append(spread(arm["errors"], lambda value: esc(count(value))))
        name = (f'<td class="model">{site.icon(item["run"])}<a class="model-name" href="{link(site, PATH, item)}">'
                f'{esc(item["label"])}</a><span class="small">{len(arm["runs"])} runs</span></td>')
        body.append(f'<tr data-models="{item["models"]}">{name}' + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{esc(direction)}</span></th>'
                   for text, direction in heads)
    dates = sorted(block.get("dates", []))
    when = "" if not dates else f" Run on {esc(long_date(dates[0]))}" + (
        f" to {esc(long_date(dates[-1]))}." if dates[-1] != dates[0] else ".")
    return f"""<section class="card" id="dont-know" {DECISION_ONLY}>
      <h2>With “{esc(option)}” as an extra choice</h2>
      <p>{esc(block_name(items, block))}, off and with web, asked the same {data['questions']} questions with “{esc(option)}” offered as an extra choice, {len(block['off']['runs'])} runs each.{when} Non-hallucination: the share of the answers that were not right where the setup chose “{esc(option)}” instead of a wrong answer. Each value is the mean of the runs, with the lowest and highest run under it.</p>
      <div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr><th scope="col">Setup</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>
    </section>"""


def block_name(items: list[dict[str, Any]], block: dict[str, Any]) -> str:
    """The model of the “I don't know” runs, as its setup without web is named."""
    return dont_know_item(items, block, "off")["label"]


def summary_cards(items: list[dict[str, Any]], digits: int) -> str:
    """The first screen's cards, among the decision models (the chat rows are their own comparison in the charts), under
    a "Decision models" heading, for the view bar's all and decision groups: the best with web search, the same model
    without it, and the best without search (nothing without both kinds)."""
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
    return (f'<div {DECISION_ONLY}><h2 class="board-group">Decision models</h2><div class="result-cards">' + "".join(
        f'<div class="result-card"><h2>{esc(title)}</h2><p class="result-main">{esc(pct(item["setup"]["accuracy"]["mean"], digits))}'
        f'</p><p class="result-cost">{esc(note)}</p></div>' for title, note, item in cards) + "</div></div>")


def whole(fraction: float) -> str:
    """A share as a percentage without needless decimals (0.68 as 68%, 0.6267 as 62.7%)."""
    return f"{round(100 * fraction, 1):g}%"


def habits_note(data: dict[str, Any], setup: dict[str, Any]) -> str | None:
    """The ranking's note beside a setup whose score its habits explain (the summary step's habits: accuracy at most
    explained_margin above its habit baseline; never a setup with web search), in the project lead's words; None
    otherwise or without the habits block."""
    block, habits = data.get("habits"), setup.get("habits")
    if not block or not habits or not habits.get("explained") or web(setup):
        return None
    return (f"picks the first choice in {habits['first_in_10']} of 10 questions; always picking the first choice scores "
            f"{whole(block['lazy']['always_first'])}")


def signed(value: float) -> str:
    """A difference in points, signed."""
    return f"{100 * value:+.1f}"


def habits_table(heads: list[tuple[str, str]], rows: list[tuple[str, list[str]]], first: str = "Setup") -> str:
    """One step's table: a first column (first: Setup, or Strategy for step 1), then the heads (name, what it is), each
    row its label and its cells (HTML)."""
    labels = [f"{head} ({what})" if what else head for head, what in heads]
    head = "".join(f'<th scope="col" class="num">{esc(text)}' + (f'<span class="small">{esc(what)}</span>' if what else "")
                   + "</th>" for text, what in heads)
    body = "".join(f'<tr><td class="model">{label}</td>'
                   + "".join(cell(name, value) for name, value in zip(labels, values)) + "</tr>"
                   for label, values in rows)
    return (f'<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr><th scope="col">{esc(first)}</th>'
            f"{head}</tr></thead><tbody>{body}</tbody></table></div>")


def habits_section(site: Site, data: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """Can a model score here without knowing the facts (the summary step's habits block): a summary, then one table
    per step: strategies that never read the question, each decision setup's habits and habit baseline, the hard
    questions, the probability of the chosen choice, the reversed-choices run's status, and the open setups' weights
    dates against the questions' earliest public records. A decision-model part (DECISION_ONLY): the chat group shows
    a one-line note in its place. Nothing without the block."""
    block = data.get("habits")
    if not block:
        return ""
    digits = site.config["percent_digits"]
    rows = [item for item in items if "habits" in item["setup"]]
    plain = [item for item in rows if not web(item["setup"])]
    lazy, n, runs = block["lazy"], block["questions"], data["runs_per_setup"]
    first = lazy["always_first"]
    best = max(plain, key=lambda item: item["setup"]["accuracy"]["mean"])
    reached = sum(item["setup"]["accuracy"]["mean"] >= first for item in plain)
    where = ("above every decision setup without search here" if not reached else
             f"as much as or more than {reached} of the {len(plain)} decision setups without search here")
    summary = (f"Always choosing the first option scores {whole(first)}, {where}. Answer-position and yes/true imbalances "
               "complicate the ranking; these checks cannot establish whether a model has seen the questions.")
    rights, yes = block["right_positions"], block["yes_no"]
    yes_n = yes["yes"]["questions"] + yes["true"]["questions"]
    yes_right = lazy["always_yes"]["right"]
    ordinals = ["first", "second", "third", "fourth", "fifth", "sixth"]
    said = [f"the {ordinals[index]} on {count}" for index, count in enumerate(rights)]
    said[0] = f"the first choice on {rights[0]} questions"
    positions = ", ".join(said[:-1]) + f" and {said[-1]}"
    key_words = (f"The right answer is {positions}. {yes_n} questions are yes/no ({yes['yes']['questions']}) or true/false "
                 f"({yes['true']['questions']}); "
                 + ('on every one "yes" or "true" is the first choice, and ' if block["positive_first"] else "")
                 + f'"yes" or "true" is right on {yes_right} of them ({yes["yes"]["right"]} of {yes["yes"]["questions"]} '
                 f'and {yes["true"]["right"]} of {yes["true"]["questions"]}).')
    random = lazy["random"]
    others = n - yes_n
    step1 = habits_table(
        [("Score", f"on the {n} questions"), ("Uniform random guessing", "the same questions")],
        [("Always the first choice", [whole(first), whole(random)]),
         ("Always the last choice", [whole(lazy["always_last"]), whole(random)]),
         (f"Always the position most often right in the key (the {ordinals[lazy['most_often']['position'] - 1]})",
          [whole(lazy["most_often"]["score"]), whole(random)]),
         (f'Always "yes" or "true" on the {yes_n} yes/no and true/false questions',
          [f"{yes_right} of {yes_n} right ({whole(yes_right / yes_n)})", "50% on them"]),
         (f'Always "yes" or "true" on those {yes_n}, a uniform random guess on the other {others}',
          [whole(lazy["yes_then_uniform"]), whole(random)])], first="Strategy")
    above_random = sum(item["setup"]["accuracy"]["mean"] > random for item in plain)
    two_other = block["two_choice_other"]
    margin = round(100 * block["explained_margin"], 1)
    # The mark's rule is one-sided: accuracy at or below the habit baseline + margin (no lower limit).
    mark_words = f"at or below habit baseline + {margin:g} pt"
    key_row = ("<strong>Answer key</strong>", ["", *(whole(count / n) for count in rights), whole(yes_right / yes_n),
                                              whole(block["first_right_other"] / others), "", "", "", ""])
    step2_rows = [key_row]
    for item in rows:
        setup = item["setup"]
        habits = setup["habits"]
        shares = habits["positions"] + [0.0] * (len(rights) - len(habits["positions"]))
        explained = f'<span class="small">{esc(mark_words)}</span>' if habits["explained"] else ""
        step2_rows.append((esc(item["label"]), [
            esc(pct(setup["accuracy"]["mean"], digits)), *(esc(pct(share, digits)) for share in shares),
            esc(pct(habits["yes_share"], digits)), esc(pct(habits["first_share_other"], digits)),
            esc(pct(habits["baseline"], digits)), f"{esc(signed(habits['above']))}{explained}",
            f"{habits['p']:.3f}", f"{habits['p_holm']:.3f}" if "p_holm" in habits else "with search: not tested"]))
    step2 = habits_table(
        [("Accuracy", f"mean of {runs} runs"), *((f"{ordinals[index].capitalize()} choice", "share of answers")
                                                 for index in range(len(rights))),
         ('"Yes" or "true"', f"share on the {yes_n} yes/no and true/false questions"),
         ("First choice, other questions", f"share on the other {others}"),
         ("Same habits, no reading", "habit baseline"), ("Above the habits", "points"), ("p", "one-sided, exploratory"),
         ("p, Holm", f"over the {len(plain)} without search")], step2_rows)
    lowest_holm = min(item["setup"]["habits"]["p_holm"] for item in plain)
    explained = [item for item in plain if item["setup"]["habits"]["explained"]]
    within = mark_words
    hard = block["hard"]
    sizes = " and ".join(f"{count} with {choices} choices" for choices, count in hard["by_choices"].items())
    step3 = habits_table(
        [("Right, runs " + " / ".join(str(index + 1) for index in range(runs)), f"of {hard['questions']}"),
         ("Mean", "of the runs"), (f"Right in all {runs} runs", "")],
        [(esc(item["label"]), [" / ".join(str(value) for value in item["setup"]["habits"]["hard_right"]),
                               f"{statistics.mean(item['setup']['habits']['hard_right']):.2f}",
                               str(item["setup"]["habits"]["hard_right_all_runs"])]) for item in rows])
    sure = data["sure_threshold"]
    step4_rows = []
    for item in rows:
        confidence = item["setup"]["habits"].get("confidence")
        if not confidence:
            step4_rows.append((esc(item["label"]), ['<span class="nm">No probabilities</span>'] * 4))
            continue
        per_run = [run["confidence"]["sure"] for run in item["setup"]["runs"]]
        mean = lambda value: "none" if value is None else esc(pct(value, digits))  # noqa: E731
        step4_rows.append((esc(item["label"]), [
            mean(confidence["mean_right"]), mean(confidence["mean_wrong"]),
            f"{confidence['sure']:,}<span class=\"small\">runs {' / '.join(str(value) for value in per_run)}</span>",
            f"{confidence['sure_wrong']:,}"]))
    step4 = habits_table(
        [("Right answers", "mean probability of the chosen choice"), ("Wrong answers", "the same"),
         (f"At ≥{pct(sure, 0)}", f"answers over the {runs} runs"), ("Of them wrong", "")], step4_rows)
    reversed_words = {"run, excluded": "Run once with the choices reversed; excluded, because the dataset terms do not "
                                       "explicitly allow changing the order of a question's choices",
                      "not run": "Not run (no API credit)"}
    step5 = habits_table([("Status", "")], [(esc(item["label"]), [esc(reversed_words[item["setup"]["habits"]["reversed"]])])
                                            for item in rows if "reversed" in item["setup"]["habits"]])
    opened = sorted((item for item in rows if "weights" in item["setup"]["habits"]),
                    key=lambda item: (-item["setup"]["habits"]["weights"]["days_before"], item["label"].casefold()))
    step6 = habits_table(
        [("Hugging Face repository", ""), ("Revision we ran", ""), ("Revision committed", "UTC"),
         ("Days before the questions were public", "")],
        [(esc(item["label"]), [
            f"<code>{esc(weights['repo'])}</code>" + (f'<span class="small">{esc(weights["note"])}</span>'
                                                      if weights.get("note") else ""),
            f"<code>{esc(weights['revision'])}</code>", esc(weights["committed"]), str(weights["days_before"])])
         for item in opened for weights in [item["setup"]["habits"]["weights"]]])
    days = [item["setup"]["habits"]["weights"]["days_before"] for item in opened]
    public = block["public_records"]
    when = lambda stamp: f"{long_date(stamp[:10])} at {stamp[11:16]} UTC"  # noqa: E731
    read = block["weights"]
    return f"""<section class="card" id="habits" {DECISION_ONLY}>
      <h2>Can a model score here without knowing the facts?</h2>
      <p><strong>{esc(summary)}</strong></p>
      <p>{esc(key_words)} The checks below use only totals: the answer key's positions, each decision setup's answers over its {runs} runs, and public dates.</p>
      <h3>1. Strategies that never read the question</h3>
      {step1}
      <p class="note">No decision setup without search reaches the {whole(first)} of always picking the first choice; the best, {esc(best['label'])}, scores {esc(pct(best['setup']['accuracy']['mean'], digits))}. {above_random} of the {len(plain)} score above uniform random guessing ({esc(pct(random, digits))}).</p>
      <h3>2. Answering habits</h3>
      {step2}
      <ul class="note">
        <li>Shares are of each setup's answers over its {runs} runs. The habit baseline is the score of a strategy that never reads the question but has the setup's habits, by number of choices: on the {yes_n} yes/no and true/false questions it says "yes" or "true" as often as the setup does there; on the other {two_other} two-choice questions it picks the first choice as often as the setup does on them; on three- and four-choice questions it picks each position as often as the setup does on questions of that size. "Above the habits" is accuracy minus that baseline.</li>
        <li>The p values are exploratory, not a validated test: the one-sided chance that the habit strategy, answering each question independently, scores at least the setup's mean accuracy, by a normal approximation with the variance of one run of {n} questions (the habits come from the same answers and are treated as known; the {runs} runs of the same questions are not independent). Holm's correction over the {len(plain)} setups without search: lowest adjusted p {lowest_holm:.2f}. Across those {len(plain)}, the share of first-choice answers and accuracy correlate at r = {block['first_share_accuracy_r']:.2f}.</li>
        <li>"{within.capitalize()}" marks the {len(explained)} setups whose accuracy is below their habit baseline or at most {margin:g} point above it (a one-sided rule: no lower limit). It is a descriptive threshold: a score at or below that line is consistent with the habits, not proof that they cause it. The setup with web search never gets the mark. The ranking's note beside these setups gives their first-choice share over all {n} questions; {'since "yes" or "true" is always the first choice, that share mixes the "yes" habit with a pure position habit' if block['positive_first'] else 'that share mixes the "yes" habit with a pure position habit'}. The two columns before the baseline separate them.</li>
      </ul>
      <h3>3. Hard questions</h3>
      {step3}
      <p class="note">Hard: answered right by at most {pct(hard['share'], 0)} of the {len(plain)} decision setups without search (each setup's mean over its runs). {hard['questions']} questions ({sizes}); uniform random guessing expects {hard['uniform_expected']:.2f} of them right, and the right answer is the first choice on {hard['first_right']} of them. The hard set comes from the same setups' answers, so it is no independent contamination test.</p>
      <h3>4. Probability of the chosen choice</h3>
      {step4}
      <p class="note">The probability each setup's output gave its chosen choice, from the per-choice probabilities recorded in its runs (not the providers' own "confidence" field, which differs from setup to setup). The answers at ≥{pct(sure, 0)} are the “sure” answers of the table above.</p>
      <h3>5. Reversed choices</h3>
      {step5}
      <p class="note">Left out: no number from this run is used or shown.</p>
      <h3>6. Weights and question dates</h3>
      {step6}
      <p class="note">Earliest public records of the questions we can observe: the Hugging Face dataset {esc(DATASET)} was created on {esc(when(public['dataset_created']))}; its only commit, <code>{esc(public['dataset_commit'])}</code>, of {esc(when(public['dataset_committed']))}, holds the questions. The GitHub repository's only commit, <code>{esc(public['repository_commit'])}</code>, of {esc(when(public['repository_committed']))}, holds none. Each open setup's revision was committed {min(days)} to {max(days)} days before (commit dates as the {esc(read['source'])} gave them, read {esc(long_date(read['read']))}; files can be older). These dates do not rule out earlier exposure to the questions or their sources; the API setups' training dates are unknown.</p>
    </section>
    <section class="card" data-models="chat" hidden>{chat_note("Can a model score here without knowing the facts? That section covers the decision models: see All models or Decision models.")}</section>"""


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
    block = dont_know_block(data)
    idk_nav = f'<a href="#dont-know" {DECISION_ONLY}>{esc(block["option"])}</a>' if block else ""
    body = f"""    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>PWS-Decisions: the site's models on dated web facts</h1>
      <p>PWS-Decisions is Parallel Web Systems' benchmark of {data['questions']} public English multiple-choice questions whose answers depend on dated facts on the public web. We asked {who} that an API still serves, {data['runs_per_setup']} runs each, one question per request. {"With web search: " + esc(joined(searched)) + "; every other setup answered without search." if searched else "Every setup answered without search."} This page is not part of the Turkish ranking.</p>
      {summary_cards(items, digits)}
      {framing(data)}
      <p>{above} setups have a mean accuracy above the {pct(data['random_accuracy'], digits)} chance line (Parallel's random-guess baseline, not a run of ours); every accuracy here is the mean of our {data['runs_per_setup']} runs.</p>
      {provenance(data)}
      <nav class="face-nav" aria-label="On this page"><a href="#accuracy">Accuracy</a><a href="#cost">Cost</a><a href="#latency">Latency</a><a href="#results">Every number</a>{f'<a href="#habits" {DECISION_ONLY}>Without the facts</a>' if data.get("habits") else ""}{idk_nav}<a href="#not-run">Not run</a><a href="#method">Method</a></nav>
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
        <li>Cost: an estimate, each run's recorded tokens at the runner's list price for the setup, the price the Text tab uses, over its {data['questions']} questions{", plus the web search fee for setups with web" + (" ($" + " or $".join(fees) + " per request for Perplexity)" if fees else "") if searched else ""}. It is not a provider's bill: an API usage cost estimate for a run through an API key, an API-equivalent estimate for a run through a subscription, a list-price estimate for a model on our GPU. Where a fee is missing from the estimate, the setup's row says so.</li>
        {f'<li {DECISION_ONLY}>A line under a name, “picks the first choice in N of 10 questions; …”: that setup scores at most {round(100 * data["habits"]["explained_margin"], 1):g} point above what its answering habits alone would score (<a href="#habits">without knowing the facts</a>).</li>' if any(habits_note(data, item["setup"]) for item in items) else ""}
      </ul>
    </section>
    {habits_section(site, data, items)}
    {dont_know_section(site, data, items)}
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
        <li>The runs' API usage cost estimate at list prices (subscription runs as API-equivalent estimates): {dollars(data['run_cost_usd'])}; not a provider's bill.</li>
        {cli_notes(items)}
        {attempts_note(site, data)}
      </ul>
      <p class="note">Download: <a href="{rel(PATH, "pws-decisions.json")}" download>pws-decisions.json</a> (every number on this page, per run). The adapter is <code>pws/bench.py</code> in the repository.</p>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"{len(items)} setups on PWS-Decisions, Parallel's benchmark of dated web facts: "
                            "accuracy over three runs, cost, request time and confidence.", body)}
