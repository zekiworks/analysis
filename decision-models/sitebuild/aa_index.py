"""Artificial Analysis's Decision Index models on our benchmark (aa-decision-index/): our numbers for the decision models
of Artificial Analysis's Decision Index v1.0, as its post of 22 October 2026 lists them (page_config.json's
aa_decision_index), in two charts and one table, after the cards of our thread on X (aa_decision_index.thread). It
needs no JavaScript, ranks nothing new and changes no number of the other pages: every value is results.json's or
vision.json's, as the Text, Page images and Hallucination tabs show it."""

from __future__ import annotations

import math
from typing import Any

import build_page as bp
from sitebuild.site import (NOT_MEASURED, ROOT, Site, cost_missing, esc, hbars, latency_text, pct, rank_fill, rel,
                            scale_legend)
from sitebuild.vision import NO_IMAGE, NOT_AVAILABLE, cell, joined

PATH = "aa-decision-index/"
TITLE = "Artificial Analysis's Decision Index models, on our benchmark"
NOT_RUN = '<span class="nm">Not run</span>'


def entries(site: Site) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """AA's models with our setup for each, and the names of those not in our benchmark; the build stops when a run is
    missing, is not a decision model, comes twice or asks more than one question per request (the page says one)."""
    pairs, absent, seen = [], [], set()
    for item in site.config["aa_decision_index"]["models"]:
        if item["run"] is None:
            absent.append(item["name"])
            continue
        run = site.by_id.get(item["run"])
        if run is None or not site.decision(run) or item["run"] in seen:
            raise SystemExit(f"page_config.json aa_decision_index: run {item['run']} ({item['name']}) is missing, not a decision model or listed twice")
        if run["questions_per_request"] != 1:
            raise SystemExit(f"page_config.json aa_decision_index: run {item['run']} ({item['name']}) asks {run['questions_per_request']} "
                             "questions per request, and the page says one")
        seen.add(item["run"])
        pairs.append((item["name"], run))
    return pairs, absent


def share(run: dict[str, Any], part: str | None = None) -> tuple[int, int]:
    """Right answers and questions of a run, on one part (reading or grammar) or both, as the Text tab counts them."""
    parts = [part] if part else ["reading", "grammar"]
    return sum(run["groups"][name]["correct"] for name in parts), sum(run["groups"][name]["questions"] for name in parts)


def cost_per_1000(run: dict[str, Any]) -> float | None:
    return None if run["api_equivalent_usd"] is None else 1000 * run["api_equivalent_usd"] / run["answered_questions"]


def per_million(cost: float) -> float:
    """Dollars per 1M questions: the cost per 1,000 questions as the site rounds it, times 1,000."""
    return round(cost, 3) * 1000


def route(run: dict[str, Any]) -> str:
    return {"local": "on our GPU, from the released weights", "free": "its API's free tier"}.get(run["billing"], "its API")


def reply_cards(site: Site) -> str:
    """Our reply charts: the cards of our thread on X in reply to Artificial Analysis's post (page_config.json's
    aa_decision_index.thread: each card's file in aa-decision-index/ and its alt text), in the thread's order, each
    opening its PNG, never redrawn. The build stops when a card's file is missing or not a PNG, or its alt text is empty."""
    thread = site.config["aa_decision_index"]["thread"]
    figures = []
    for index, card in enumerate(thread["cards"], 1):
        path = ROOT / PATH / card["file"]
        if not path.is_file() or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"page_config.json aa_decision_index.thread: {PATH}{card['file']} is missing or not a PNG")
        if not card["alt"].strip():
            raise SystemExit(f"page_config.json aa_decision_index.thread: {card['file']} has no alt text")
        width, height = bp.png_size(path)
        figures.append(
            f'<figure class="reply-card" style="margin:0 0 1.25rem"><a href="{esc(card["file"])}"><img src="{esc(card["file"])}" '
            f'width="{width}" height="{height}" loading="lazy" alt="{esc(card["alt"])}" style="display:block;width:100%;height:auto"></a>'
            f'<figcaption class="note">Card {index} of {len(thread["cards"])} · PNG, {width:,} × {height:,}</figcaption></figure>')
    return (f"<section class=\"card\" id=\"reply-charts\"><h2>Our {bp.in_words(len(thread['cards']))} reply charts</h2>"
            f"<p class=\"note\">The cards of our thread on X in reply to Artificial Analysis's post, in the thread's order "
            f"(results {esc(thread['results'])}); each opens as an image.</p>"
            f"{''.join(figures)}<p class=\"note\">{esc(thread['note'])}</p></section>")


def build(site: Site) -> dict[str, str]:
    config = site.config["aa_decision_index"]
    pairs, absent = entries(site)
    digits = site.config["percent_digits"]
    stops = site.config["rank_scale"]["stops"]
    shown = site.names([run for _, run in pairs])
    dont_know = site.results["dont_know"]
    option = dont_know["option"]
    held = {model["original_run"]: model for model in dont_know["models"]}
    vision = site.vision
    in_vision = {(model["provider"], model["model"]): model for model in vision["models"]}
    prices = {bp.price_key(price): price for price in site.results["prices"]}
    upper_cost = site.config["first_cost_marks"]["upper"]
    upper = lambda run: f"{upper_cost['mark']} " if run.get("cost_upper_bound") else ""  # noqa: E731
    reading_n, grammar_n = (site.runs[0]["groups"][part]["questions"] for part in ("reading", "grammar"))
    pages_n = vision["subset"]["questions"]
    total = site.total
    pairs.sort(key=lambda pair: (-share(pair[1])[0] / share(pair[1])[1], pair[1]["name"].casefold()))
    href = lambda run: rel(PATH, site.model_path(run))  # noqa: E731
    date = lambda run: bp.long_date(run["started"][:10])  # noqa: E731

    accuracies = [share(run)[0] / share(run)[1] for _, run in pairs]
    accuracy_rows = [{"label": shown[run["run"]], "family": site.families[run["run"]]["name"], "href": href(run), "text": pct(value, digits),
                      "bars": [{"value": value, "colour": rank_fill(stops, value, min(accuracies), max(accuracies))}],
                      "title": f"{site.row_name(run)} (Artificial Analysis: {name}): {share(run)[0]:,} of {total:,} right"}
                     for (name, run), value in zip(pairs, accuracies)]
    ran = sorted(((name, run, held[run["run"]]) for name, run in pairs if run["run"] in held and held[run["run"]]["non_hallucination"] is not None),
                 key=lambda item: -item[2]["non_hallucination"])
    rates = [model["non_hallucination"] for _, _, model in ran]
    rate_rows = [{"label": shown[run["run"]], "family": site.families[run["run"]]["name"], "href": href(run), "text": pct(model["non_hallucination"], digits),
                  "bars": [{"value": model["non_hallucination"], "colour": rank_fill(stops, model["non_hallucination"], min(rates), max(rates))}],
                  "title": f"{site.row_name(run)} (Artificial Analysis: {name}): {model['dont_know']:,} “{option}” of {model['dont_know'] + model['wrong']:,} not right"}
                 for name, run, model in ran]
    not_held = [site.row_name(run) for _, run in pairs if run["run"] not in held]
    priced = sorted(((name, run, per_million(cost_per_1000(run))) for name, run in pairs if cost_per_1000(run) is not None),
                    key=lambda item: (cost_per_1000(item[1]), item[1]["name"].casefold()))
    dollars = [value for _, _, value in priced]
    # A tick at each quarter of the axis, the quarter a round number of dollars that fits the dearest model.
    quarter = math.ceil(max(dollars) / 40) * 10 if max(dollars) >= 40 else max(1, math.ceil(max(dollars) / 4))
    cost_rows = [{"label": shown[run["run"]], "family": site.families[run["run"]]["name"], "href": href(run),
                  "text": f"{upper(run)}${value:,.0f}",
                  "bars": [{"value": value, "colour": rank_fill(stops, value, max(dollars), min(dollars))}],
                  "title": f"{site.row_name(run)} (Artificial Analysis: {name}): {upper(run)}${cost_per_1000(run):.3f} per 1,000 questions, "
                           f"{upper(run)}${value:,.0f} per 1M." + (f" {site.cost_tip(run)}" if site.cost_tip(run) else "")}
                 for name, run, value in priced]
    latency = lambda run: (run.get("latency") or {}).get("median_request_seconds")  # noqa: E731
    sample = lambda run: " *" if run["latency"]["source"] == "sample" else ""  # noqa: E731
    timed = sorted(((name, run) for name, run in pairs if latency(run) is not None),
                   key=lambda pair: (latency(pair[1]), pair[1]["name"].casefold()))
    seconds = [latency(run) for _, run in timed]
    # A tick at each quarter of the axis, the quarter a round number of seconds that fits the slowest model.
    step = 10 ** math.floor(math.log10(max(seconds) / 4))
    latency_quarter = round(math.ceil(max(seconds) / 4 / step) * step, 6)
    latency_rows = [{"label": shown[run["run"]], "family": site.families[run["run"]]["name"], "href": href(run), "text": f"{latency_text(value)}{sample(run)}",
                     "bars": [{"value": value, "colour": rank_fill(stops, value, max(seconds), min(seconds))}],
                     "title": f"{site.row_name(run)} (Artificial Analysis: {name}): median {latency_text(value)} per request"}
                    for (name, run), value in zip(timed, seconds)]
    flight: dict[int, list[str]] = {}
    for _, run in timed:
        flight.setdefault(run["latency"].get("concurrency") or 1, []).append(site.row_name(run))
    several_at_once = [(count, names) for count, names in sorted(flight.items()) if count > 1]
    in_flight = "; ".join(f"{esc(joined(names))} sent {count} requests at a time" for count, names in several_at_once)
    untimed = [site.row_name(run) for _, run in pairs if latency(run) is None]
    sampled = [run for _, run in timed if run["latency"]["source"] == "sample"]

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    charts = (
        card("chart-accuracy", "Accuracy", f"Share of the Text tab's {total:,} questions answered right · higher is better", accuracy_rows,
             scale_legend(stops, pct(min(accuracies), digits), pct(max(accuracies), digits)))
        + card("chart-non-hallucination", "Non-hallucination rate",
               f"“{esc(option)}” among the answers that were not right, with it offered as a sixth option (the Hallucination tab) · higher is better",
               rate_rows,
               scale_legend(stops, pct(min(rates), digits), pct(max(rates), digits))
               + (f" <span>Not run with “{esc(option)}”: {esc(joined(not_held))}.</span>" if not_held else ""))
        + card("chart-cost", "Cost per 1M questions",
               "Estimated from list prices and the token use recorded in each run, in US dollars per 1 million questions (the "
               "Text tab gives it per 1,000 questions) · lower is better",
               cost_rows,
               scale_legend(stops, f"${max(dollars):,.0f}", f"${min(dollars):,.0f}", higher=False)
               + f" <span>{esc(site.cost_note([run for _, run, _ in priced]))}</span>",
               top=4 * quarter, tick=lambda value: f"${value:,.0f}")
        + card("chart-latency", "Median latency per request",
               "Time from sending one request to its answer, measured from our computer: on our GPU for the setups run there, "
               "through the network for the APIs (with OpenRouter’s time for those via OpenRouter) · lower is better",
               latency_rows,
               scale_legend(stops, latency_text(max(seconds)), latency_text(min(seconds)), higher=False)
               + (f" <span>{in_flight}; the others one.</span>" if in_flight else "")
               + (f" <span>* Measured on a sample of questions: {esc(joined([site.row_name(run) for run in sampled]))}.</span>" if sampled else "")
               + (f" <span>No latency recorded: {esc(joined(untimed))}.</span>" if untimed else ""),
               top=4 * latency_quarter, tick=lambda value: f"{round(value, 2):g} s"))

    heads = [("Accuracy", f"{total:,} questions; higher is better"), ("Reading", f"{reading_n:,} questions; higher is better"),
             ("Grammar", f"{grammar_n:,} questions; higher is better"), ("Page images, picture alone", f"{pages_n:,} questions; higher is better"),
             ("Non-hallucination rate", f"with “{option}”; higher is better"), ("Attempt rate", f"with “{option}”; neither better nor worse on its own"),
             ("Cost per 1,000 questions", "estimated; lower is better"), ("Cost per 1M questions", "the same, × 1,000; lower is better"),
             ("Median latency per request", "seconds; lower is better")]
    labels = [f"{head} ({direction})" for head, direction in heads]
    rows = []
    for name, run in pairs:
        right, questions = share(run)
        parts = [share(run, part) for part in ("reading", "grammar")]
        entry = in_vision.get((run["provider"], run["model"]))
        picture = None if entry is None else entry["conditions"].get("B")
        model = held.get(run["run"])
        cost = cost_per_1000(run)
        tip = site.cost_tip(run)
        priced_cell = lambda text: f'<span title="{esc(tip)}">{text}</span>' if tip else text  # noqa: E731
        values = [
            f'{pct(right / questions, digits)}<span class="small">{right:,} of {questions:,}</span>',
            *(f'{pct(got / of, digits)}<span class="small">{got:,} of {of:,}</span>' for got, of in parts),
            (NOT_MEASURED if entry is None else NO_IMAGE if entry["kind"] == "text"
             else f'<span class="nm">{NOT_AVAILABLE}: {esc((entry.get("missing") or {}).get("B", "no result"))}</span>' if picture is None
             else f'{pct(picture["accuracy"], digits)}<span class="small">{picture["correct"]:,} of {picture["questions"]:,}</span>'),
            NOT_RUN if model is None else f'{pct(model["non_hallucination"], digits)}<span class="small">{model["dont_know"]:,} “{esc(option)}” of {model["dont_know"] + model["wrong"]:,} not right</span>',
            NOT_RUN if model is None else f'{pct(model["attempt_rate"], digits)}<span class="small">{model["right"] + model["wrong"]:,} of {total:,} answered</span>',
            cost_missing(run) if cost is None else priced_cell(f"{upper(run)}${cost:.3f}"),
            cost_missing(run) if cost is None else priced_cell(f"{upper(run)}${per_million(cost):,.0f}"),
            NOT_MEASURED if latency(run) is None else f"{latency_text(latency(run))}{sample(run)}" + (
                f'<span class="small">{run["latency"]["concurrency"]} in flight</span>' if (run["latency"].get("concurrency") or 1) > 1 else ""
            ) + ('<span class="small">its repeat runs</span>' if run["latency"]["source"] == "repeats" else
                 f'<span class="small">Measured on a sample ({run["latency"].get("questions", 0):,} questions)</span>' if run["latency"]["source"] == "sample" else ""),
        ]
        model_cell = (f'<td class="model" title="Run {run["run"]}, {date(run)}; {esc(route(run))}">'
                      f'<a class="model-name" href="{href(run)}">{esc(shown[run["run"]])}</a>'
                      f'<span class="small">Artificial Analysis: {esc(name)}</span></td>')
        rows.append(f"<tr>{model_cell}" + "".join(cell(label, value) for label, value in zip(labels, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">{esc(direction)}</span></th>' for text, direction in heads)
    table = (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')

    notes = [esc(site.cost_note([run for _, run in pairs]))]
    for name, run in pairs:
        price = prices.get(bp.price_key(run))
        if run["billing"] == "free":
            notes.append(f"{esc(site.row_name(run))}: its free tier, priced at {esc(price['basis'])}.")
        if price and price.get("change"):
            notes.append(f"{esc(site.row_name(run))}: at the price recorded on {bp.long_date(price['date'])}. Provider update: {esc(price['change'])}.")
    notes.append("Latency: the median time per request. Local setups ran on our hardware, listed on each setup’s page; "
                 "API latency includes the network, and via OpenRouter, OpenRouter’s time.")
    for name, run in timed:
        if run["latency"]["source"] == "repeats":
            notes.append(f"{esc(site.row_name(run))}: latency from its repeat runs "
                         f"(runs {esc(joined([str(number) for number in run['latency']['runs']]))}), "
                         f"{latency_text(latency(run))} median per request.")
    several = [site.row_name(run) for _, run, model in ran if len(model["runs"]) > 1]
    post = config["post"]
    not_ours = f"; {esc(joined(absent))} {'is' if len(absent) == 1 else 'are'} not" if absent else ""
    body = f"""    <section class="card">
      <p class="eyebrow">Compared with Artificial Analysis</p>
      <h1>{esc(TITLE)}</h1>
      <p>Artificial Analysis's <a href="{esc(post)}">post of {bp.long_date(config["date"])}</a> ranks {len(pairs) + len(absent)} decision models on its Decision Index v1.0, a weighted average of four of its own evaluations ({esc(config["evaluations"])}). {len(pairs)} of them are on our leaderboard{not_ours}. This page gathers our numbers for those {len(pairs)}, from our published results, and opens with our reply charts. Our tests are different from Artificial Analysis's, so the two rank different things. This page ranks nothing new and changes no number on the other pages.</p>
      <nav class="face-nav" aria-label="On this page"><a href="#reply-charts">Reply charts</a><a href="#chart-accuracy">Accuracy</a><a href="#chart-non-hallucination">Non-hallucination</a><a href="#chart-cost">Cost</a><a href="#chart-latency">Latency</a><a href="#table">Every number</a></nav>
    </section>
    {reply_cards(site)}
    <section class="charts" aria-label="Charts">{charts}</section>
    <section class="card" id="table">
      <h2>Every number, model by model</h2>
      <p class="note">Ranked by accuracy. Accuracy, reading and grammar: each model's run on the <a href="{rel(PATH, "")}">Text tab</a>, one question per request, on all its questions and on each part. Page images: the <a href="{rel(PATH, "vision/")}">Page images tab</a>, the page's picture alone (condition B). Non-hallucination and attempt rates: the <a href="{rel(PATH, "dont-know/")}">Hallucination tab</a>, each model's first run{" (" + esc(joined(several)) + " have five; that tab gives their range)" if several else ""}. Cost: estimated from list prices and the token use recorded in each run, per 1,000 questions as on the Text tab, and the same times 1,000 for comparison with Artificial Analysis's cost per 1 million tasks. Artificial Analysis's Elephant 9B is Base Labs' elephant-1, our Elephant-1.</p>
      {table}
      <ul class="note">{"".join(f"<li>{note}</li>" for note in notes)}</ul>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (the Text and Hallucination tabs' numbers) and <a href="{rel(PATH, "vision.json")}" download>vision.json</a> (the Page images tab's).</p>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"Our numbers for the {len(pairs)} decision models of Artificial Analysis's Decision Index v1.0 that are on "
                            "our benchmark: accuracy, reading and grammar, page images, non-hallucination and attempt rates, cost and latency.", body)}
