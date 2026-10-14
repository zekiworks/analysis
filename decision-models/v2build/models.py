"""One page per setup (v2/models/<run id>/): how we called it, its settings, results, confidence, repeats, latency
and cost, and, for a first model, what it took off each LLM in the replay."""

from __future__ import annotations

from typing import Any

import build_page as bp

from v2build.site import NOT_MEASURED, Site, esc, interval, latency_text, pct, rel, request_size

GROUP_TIP = "The all-pairs test did not detect a difference between setups that share a letter. This does not establish equality."
# The home page's Routing tab LLMs, by their key in page_config.json's named_runs, with the slug of its URL.
ROUTE_SLUGS = {"opus": "opus", "sonnet_high": "sonnet", "astra": "astra", "sol": "sol", "gemini_low": "gemini-flash"}
UNPRICED_FIRST = {
    "local": "Leaves out the first model's hardware cost, which we have not estimated.",
    "free": "The first model used a free tier; this assumes no charge for it.",
}


def facts(items: list[tuple[str, str | None]]) -> str:
    """A definition list of the items that have a value."""
    return '<dl class="facts">' + "".join(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in items if value) + "</dl>"


def parameters_text(run: dict[str, Any]) -> str | None:
    count = run.get("parameters")
    if not count:
        return None
    billions = lambda value: f"{value / 1e9:.1f}".rstrip("0").rstrip(".")  # noqa: E731
    size = f"{billions(count)}B" if count >= 1e9 else f"{round(count / 1e6)}M"
    active = run.get("active_parameters")
    return f"{size} ({' to '.join(billions(value) for value in active)}B active per token)" if active else size


def section(title: str, body: str, anchor: str) -> str:
    return f'    <section class="card" id="{anchor}">\n      <h2>{title}</h2>\n      {body}\n    </section>'


def called(site: Site, run: dict[str, Any]) -> str:
    billing = site.config["billing"][run["billing"]]
    items = [
        ("Kind", site.kind(run)),
        ("Access", esc(run["access"])),
        ("Paid as", esc(billing["access"])),
        ("Model ID", f"<code>{esc(run['model'])}</code>"),
        ("Variant", esc(run["variant"]) if run.get("variant") else None),
        ("Reasoning", esc(bp.reasoning_label(run["reasoning"])) if run.get("reasoning") else None),
        ("Request format", request_size(run["questions_per_request"])),
        ("Requests at once", str(run["concurrency"])),
        ("Parameters", parameters_text(run)),
        ("Hardware", esc(run["hardware"]) if run.get("hardware") else None),
        ("Note", esc(run["note"]) if run.get("note") else None),
        ("Confidence from", esc(run["confidence"]["label"])),
        ("Run", f"{run['run']}, {bp.long_date(run['started'])}" if run.get("started") else str(run["run"])),
    ]
    return facts(items)


def results(site: Site, run: dict[str, Any]) -> str:
    correct, total = site.accuracy(run)
    groups = run["groups"]
    rows = "".join(
        f'<tr><th scope="row">{label}</th><td class="num">{pct(item["correct"] / item["questions"])}</td>'
        f'<td class="num">{interval(item["correct"], item["questions"])}</td><td class="num">{item["correct"]:,} of {item["questions"]:,}</td></tr>'
        for label, item in (("All questions", {"correct": correct, "questions": total}), ("Reading", groups["reading"]),
                            ("Grammar", groups["grammar"]))
    )
    group = (f'<p>Comparison group: <span class="hint" tabindex="0" data-tip="{esc(GROUP_TIP)}"><strong>{esc(run["group"])}</strong></span>. '
             f'<a href="{rel(site.model_path(run), "compare/")}?a={run["run"]}">Compare with another setup</a>.</p>')
    invalid = f"<p>{run['invalid']:,} questions got no valid answer; they count as wrong.</p>" if run["invalid"] else ""
    topics = "".join(
        f'<tr><td><a href="{rel(site.model_path(run), f"topics/{unit["number"]}/")}">{esc(unit["english"])}</a></td>'
        f'<td data-label="Part">{site.part(unit["number"]).capitalize()}</td>'
        f'<td class="num" data-label="Accuracy">{pct(run["units"][index] / unit["questions"])}</td>'
        f'<td class="num" data-label="Right">{run["units"][index]} of {unit["questions"]}</td></tr>'
        for index, unit in enumerate(site.units)
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th scope="col">Questions</th><th scope="col" class="num">Accuracy</th>'
        f'<th scope="col" class="num">95% interval</th><th scope="col" class="num">Right</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f"{group}{invalid}"
        '<details class="show-table"><summary>Accuracy by topic</summary><div class="table-wrap"><table class="board list">'
        '<thead><tr><th scope="col">Topic</th><th scope="col">Part</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Right</th></tr></thead>'
        f"<tbody>{topics}</tbody></table></div></details>"
    )


def confidence(site: Site, run: dict[str, Any]) -> str:
    item = run["confidence"]
    sure = item["sure"]
    threshold = pct(site.config["threshold"], 0)
    sure_text = (f"{sure['questions']:,}, of which {sure['questions'] - sure['correct']:,} wrong"
                 + (f" (share right: {interval(sure['correct'], sure['questions'])}, 95% interval)" if sure["questions"] else ""))
    parts = item["parts"]

    def auroc(entry: dict[str, Any]) -> str:
        low, high = entry["auroc_interval"]
        return f"{entry['auroc']:.2f} <span class=\"small inline\">{low:.2f} to {high:.2f}</span>"

    coverage = "; ".join(
        f"most confident {share}: {pct(item['coverage_accuracy'][key])} right"
        for key, share in (("0.20", "fifth"), ("0.50", "half"), ("0.80", "four fifths"))
    )
    return facts([
        (f"Answers kept at {threshold} or more", sure_text),
        ("Calibration gap", f"{100 * item['ece']:.1f} points"),
        ('<span class="hint" tabindex="0" data-tip="ranking score">AUROC</span>, all questions', auroc(item)),
        ("AUROC, reading", auroc(parts["meaning"])),
        ("AUROC, grammar", auroc(parts["form"])),
        ("Brier score", f"{item['brier']:.3f}"),
        ("Accuracy of its surest answers", coverage),
        ("Typical score of a right answer", pct(item["median_right"])),
        ("Typical score of a wrong answer", pct(item["median_wrong"])),
    ])


def repeats(site: Site, run: dict[str, Any]) -> str:
    found = [item for item in site.results["repeats"] if all(item[key] == run[key] for key in
             ("provider", "model", "reasoning", "variant", "questions_per_request"))]
    if not found:
        return "<p>We did not repeat this setup.</p>"
    item = found[0]
    scope = "all questions" if item["whole_bank"] else f"a sample of {item['questions']:,} questions"
    return f"<p>Run {len(item['runs'])} times on {scope}.</p>" + facts([
        (f"Answers changed in {len(item['runs'])} runs", f"{item['changed_answer']:,} of {item['questions']:,}"),
        (f"Same wrong answer in all {len(item['runs'])}", f"{item['wrong_every_run_same']:,} of {item['questions']:,}"),
        ("Wrong in at least one run", f"{item['wrong_any']:,} of {item['questions']:,}"),
        ("Accuracy in each run", ", ".join(pct(value) for value in item["accuracy"])),
    ])


def latency(run: dict[str, Any]) -> str:
    item = run.get("latency")
    source = {"run": "this run", "sample": "its repeated runs on a sample", "repeats": "its repeated runs"}
    single = run.get("single_question_latency")
    return facts([
        ("Latency, median request", f"{latency_text(item['median_request_seconds'])} ({source.get(item['source'], item['source'])})" if item else NOT_MEASURED),
        ("Latency, 90th percentile", latency_text(item.get("p90_request_seconds")) if item and item.get("p90_request_seconds") else None),
        ("Latency at 1 question per request",
         f"{latency_text(single['median_request_seconds'])} median, on {single['questions']:,} questions" if single else None),
        ("Requests at once", str(item["concurrency"]) if item else None),
        ("Throughput", f"{run['questions_per_minute']:.1f} questions per minute" if run.get("questions_per_minute") else None),
        ("Total run time", f"{run['request_seconds'] / 60:.1f} minutes" if run.get("request_seconds") else None),
    ]) + '<p class="note">Latency: the time from sending one request to receiving its answer, measured from our computer, network and retries included.</p>'


def cost(site: Site, run: dict[str, Any]) -> str:
    per = site.per_thousand(run)
    billing = site.config["billing"][run["billing"]]
    price = next((item for item in site.results["prices"] if item["provider"] == run["provider"] and item["model"] == run["model"]), None)
    tokens = (lambda key: f"{run[key] / run['answered_questions']:,.0f}" if run.get(key) is not None else None)
    return facts([
        ("$ per 1,000 questions", bp.usd(per) if per is not None else NOT_MEASURED),
        ("Whole run", bp.usd(run["api_equivalent_usd"]) if run.get("api_equivalent_usd") is not None else None),
        ("Basis", esc(billing["cost_basis"])),
        ("Price", f'{esc(price["text"])} (<a href="{esc(price["source"])}">source</a>, {esc(price["date"])})' if price else None),
        ("Input tokens per question", tokens("input_tokens")),
        ("Output tokens per question", tokens("output_tokens")),
    ])


def routing(site: Site, run: dict[str, Any]) -> str | None:
    """What this first model took off each LLM in the replay with the cutoff chosen on half the questions."""
    path = site.model_path(run)
    rows = []
    for item in site.results["cascades"]:
        if item["decision"] != run["run"]:
            continue
        frontier = site.by_id[item["frontier"]]
        alone = site.per_thousand(frontier)
        held = item["held_out"]
        saving = f"{pct(1 - item['usd_per_1000'] / alone, 0)}" if alone else NOT_MEASURED
        caveat = UNPRICED_FIRST.get(run["billing"])
        if caveat and alone:
            saving = f'<span class="hint" tabindex="0" data-tip="{esc(caveat)}">{saving}</span>'
        rows.append(
            f"<tr>{site.model_cell(path, frontier)}<td class=\"num\" data-label=\"Share taken\">{pct(held['answered'])}</td>"
            f'<td class="num" data-label="Accuracy change">{bp.points(held["difference"])} points</td>'
            f'<td class="num" data-label="Saving">{saving}</td></tr>'
        )
    if not rows:
        return None
    return ('<p class="note">Replay of recorded answers, cutoff chosen on half the questions, averaged over the splits. '
            f'Savings are estimates from API prices; the <a href="{rel(path, "method/")}#average-cost">Method page</a> explains how.</p>'
            '<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">LLM behind it</th>'
            '<th scope="col" class="num">Share taken</th><th scope="col" class="num">Accuracy change</th><th scope="col" class="num">Saving</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def routed_llm(site: Site, run: dict[str, Any]) -> str | None:
    """For a routing LLM: a link to the home page's Routing tab with it chosen."""
    for key, slug in ROUTE_SLUGS.items():
        spec = site.config["named_runs"][key]
        if all(run.get(field) == value for field, value in spec.items()):
            url = f"{rel(site.model_path(run), '')}?tab=routing&llm={slug}&per-request={run['questions_per_request']}&rule=half&test=replay"
            return f'<p>Which decision model can go first in front of it? See the <a href="{url}">Routing tab</a>.</p>'
    return None


def formats(site: Site, run: dict[str, Any]) -> str | None:
    """The same setup at the other request format, where we ran both."""
    for item in site.results["formats"]:
        if run["run"] in (item["run"], item["base"]):
            other = site.by_id[item["base"] if run["run"] == item["run"] else item["run"]]
            return (f'<p>We also ran this setup at {request_size(other["questions_per_request"])}: '
                    f'<a href="{rel(site.model_path(run), site.model_path(other))}">{esc(site.full_name(other))}</a>.</p>')
    return None


def model_page(site: Site, run: dict[str, Any]) -> str:
    path = site.model_path(run)
    correct, total = site.accuracy(run)
    lead = (f"<p>{pct(correct / total)} of the {total:,} questions right ({interval(correct, total)}, 95% interval). "
            f'<a href="{rel(path, "")}">Back to the leaderboard</a>.</p>')
    parts = [
        f'    <section class="card">\n      <p class="eyebrow">{site.kind(run)}</p>\n      <h1>{esc(run["name"])}</h1>\n'
        f'      <p class="subtitle">{esc(site.detail(run))}</p>\n      {lead}{formats(site, run) or ""}{routed_llm(site, run) or ""}\n    </section>',
        section("How we called it", called(site, run), "called"),
        section("Results", results(site, run), "results"),
        section("Confidence", confidence(site, run), "confidence"),
        section("Repeats", repeats(site, run), "repeats"),
        section("Latency", latency(run), "latency"),
        section("Cost", cost(site, run), "cost"),
    ]
    first = routing(site, run)
    if first:
        parts.append(section("Going first in front of an LLM", first, "routing"))
    return site.page(path, site.full_name(run), f"{site.full_name(run)}: how we called it, results, confidence, latency and cost.",
                     "\n".join(parts))


def build(site: Site) -> dict[str, str]:
    return {site.model_path(run): model_page(site, run) for run in site.runs}
