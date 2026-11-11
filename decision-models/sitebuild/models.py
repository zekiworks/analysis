"""One page per setup (models/<run id>/): at the top a summary of its main results (accuracy, the answers kept at the
threshold, cost and latency); then how we called it, its settings (the run record's harness seed, commit and prompt
version folded away), results, for a setup with an English run its English section (#english, which every setup name
on the two English pages links to), confidence, repeats, latency
and cost, and, for a first model, what it took off each LLM in the replay; and at models/ itself a page that sends the
reader to the home page's All models view, which replaced the list of every setup that address held."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import build_page as bp

from sitebuild import english_view, holding_back as hold, vision
from sitebuild.english_reading import (ENGLISH_ANCHOR, PATH as COMPARISON, english_only, measure_cell, missing_side,
                                       setup_labels)
from sitebuild.site import (NO_ANSWERS, NOT_MEASURED, REPO_URL, ROUTE_LLMS, Site, cost_missing, cost_per, cost_switch,
                            cost_value, esc, interval, latency_text, parameters_text, pct, rel, request_size, size_sentence)

GROUP_TIP = "The all-pairs test did not detect a difference between setups that share a letter. This does not establish equality."
# The documentation page page_config.json's reasoning_levels cite, by its host, as the Settings line names it.
LEVEL_SOURCES = {"developers.openai.com": "OpenAI's model page", "platform.claude.com": "Anthropic's effort documentation",
                 "ai.google.dev": "Google's thinking documentation"}
# What the Settings section shows where a run record holds no value. It never fills in a default.
NOT_RECORDED = "not recorded"
# The address of the former list of every setup, now a page that sends its readers to the All models view (redirect).
INDEX = "models/"
# The rule on empty and broken chat replies (project lead, bus #3215), in one plain sentence, as the model pages and the
# Method page's notes (#REPLY_ANCHOR) state it.
REPLY_RULE = ("An empty reply is asked once more; in a broken reply, any letter that is clearly readable is scored and "
              "the rest count as wrong.")
REPLY_ANCHOR = "empty-broken-replies"
# How the page names results.json's invalid_by_kind kinds (the runner's INVALID_KINDS).
INVALID_KIND_NAMES = {"empty after retry": "still empty when asked again", "empty, not retried": "empty and not yet asked again",
                      "cut off": "cut off at the output limit", "unreadable": "unreadable",
                      "letter not allowed": "with a letter the question does not allow"}


def reply_counts(run: dict[str, Any]) -> str | None:
    """A setup's invalid answers beside what the rule on empty and broken replies did (results.json's invalid_replies):
    "Invalid answers: N; read from broken replies: M; empty replies asked again: K" (with the letters read without a
    confidence where there are any), the still invalid answers by kind and the count without the rule where it differs.
    None for a setup the rule does not apply to, or with nothing to count."""
    replies = run.get("invalid_replies")
    if replies is None:
        return None
    unconfident = replies.get("read_without_confidence", 0)
    if not (run["invalid"] or replies["read_from_broken_replies"] or unconfident or replies["empty_replies_asked_again"]):
        return None
    text = f"Invalid answers: {run['invalid']:,}; read from broken replies: {replies['read_from_broken_replies']:,}; "
    if unconfident:
        text += f"read without a confidence: {unconfident:,}; "
    text += f"empty replies asked again: {replies['empty_replies_asked_again']:,}"
    if replies["empty_replies_asked_again"]:
        text += (f" ({replies['asked_again_with_answers']:,} came back with answers, "
                 f"{replies['answers_after_asking_again']:,} answers)")
    kinds = replies["invalid_by_kind"]
    if kinds:
        text += ". Still invalid: " + ", ".join(f"{count:,} {INVALID_KIND_NAMES[kind]}" for kind, count in kinds.items())
    if replies["invalid_without_rule"] != run["invalid"]:
        text += f". Without the rule: {replies['invalid_without_rule']:,} invalid"
    return text + "."


def idk_runs(results: dict[str, Any]) -> list[tuple[int, str, str, dict[str, Any]]]:
    """Each run with the "I don't know" option that results.json gives the rule's counts for (invalid_replies): the
    Hallucination tab's rows (`dont_know`, their first runs, with "Bilmiyorum") and english_reading.dont_know's English
    runs (with "I don't know") and Turkish runs on the kept questions (a Turkish side that is a Hallucination tab row is
    that row). Each as (its setup's Text tab run, "turkish" or "english", the option, {"run", "invalid",
    "invalid_replies"} for reply_counts), the option's run's own invalid answers."""
    found = []
    tab = results.get("dont_know") or {}
    for row in tab.get("models", []):
        found.append((row["original_run"], "turkish", tab["option"],
                      {"run": row["run"], "invalid": row["invalid"], "invalid_replies": row.get("invalid_replies")}))
    idk = (results.get("english_reading") or {}).get("dont_know") or {}
    for item in idk.get("models", []) + idk.get("english_only", []) + idk.get("turkish_only", []):
        for side, option in (("english", idk["option"]), ("turkish", tab.get("option"))):
            counts = item.get(side)
            if counts is not None and (side == "english" or counts["subset"]):
                found.append((item["text_run"], side, option, {"run": counts["run"], "invalid": counts["invalid"],
                                                               "invalid_replies": counts.get("invalid_replies")}))
    return found


def idk_counts(site: Site, run: dict[str, Any], side: str) -> str:
    """The rule's counts line (reply_counts) for each of the setup's runs with the "I don't know" option in `side`
    (idk_runs), named by its option and run, linked to the Method notes; empty without any."""
    path = site.model_path(run)
    return "".join(
        f"<p>With “{esc(option)}” (run {item['run']}): {esc(counts)} "
        f'(<a href="{rel(path, "method/")}#{REPLY_ANCHOR}">how</a>)</p>'
        for text_run, found, option, item in idk_runs(site.results)
        if text_run == run["run"] and found == side and (counts := reply_counts(item)) is not None
    )


def facts(items: list[tuple[str, str | None]]) -> str:
    """A definition list of the items that have a value."""
    return '<dl class="facts">' + "".join(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in items if value) + "</dl>"


def size_fact(run: dict[str, Any]) -> str:
    """The Parameters fact: the size in the details box's words (size_sentence for a mixture of experts or two models
    run together, else parameters_text), then what it covers, its sources (results.json parameters_source: each page
    linked, or the checkpoint counted, repo@revision) and the date read."""
    sources = ", ".join(f'<a href="{esc(source)}">{esc(source.removeprefix("https://"))}</a>' if source.startswith("https://")
                        else esc(source) for source in run["parameters_source"])
    scope = f"{esc(run['parameters_scope'])}; " if run.get("parameters_scope") else ""
    checked = "pages checked" if run.get("parameters") is None else "source"
    return (f'{esc((size_sentence(run) or parameters_text(run)).removeprefix("Parameters: "))}<span class="small">{scope}{checked}: {sources}; read '
            f'{bp.long_date(run["parameters_read"])}</span>')


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
        ("Parameters", size_fact(run)),
        ("Hardware", esc(run["hardware"]) if run.get("hardware") else None),
        ("Note", esc(run["note"]) if run.get("note") else None),
        ("Confidence from", esc(run["confidence"]["label"])),
        ("Run", f"{run['run']}, {bp.long_date(run['started'])}" if run.get("started") else str(run["run"])),
    ]
    return facts(items)


def settings(site: Site, run: dict[str, Any]) -> str:
    """The request settings as the setup's run record in answers.json holds them, each "not recorded" where the record
    holds no value: no run record names a temperature, and older runs have no harness commit or prompt version. The
    harness seed goes only into the local servers' requests (vLLM, Ollama) and into picking sampled questions."""
    record = site.answer_runs[run["run"]]

    def recorded(key: str, show: Callable[[Any], str] = lambda value: esc(str(value))) -> str:
        value = record.get(key)
        return NOT_RECORDED if value is None else show(value)

    record_facts = facts([
        ("Harness seed", recorded("seed")),
        ("Harness commit", recorded("harness_commit", lambda commit: f'<a href="{REPO_URL}/commit/{esc(commit)}"><code>{esc(commit[:12])}</code></a>')),
        ("Prompt version", recorded("prompt_version", lambda prompt: f"<code>{esc(prompt)}</code>")),
    ])
    return facts([
        ("Reasoning", recorded("thinking")),
        ("Request format", recorded("questions_per_request", request_size)),
        ("Requests at once", recorded("concurrency")),
        ("Temperature", recorded("temperature")),
    ]) + reasoning_levels(site, run) + (
        '<details class="setup-record"><summary>Run record: harness seed, harness commit and prompt version</summary>'
        f"{record_facts}</details>")


def reasoning_levels(site: Site, run: dict[str, Any]) -> str:
    """The model's reasoning levels as its provider documents them (page_config.json's reasoning_levels), in the
    provider's own term and level names: lowest first, the default marked where the documentation names one, the top
    level, and this run's. Empty for a model without an entry."""
    item = site.config["reasoning_levels"]["models"].get(run["model"])
    if item is None:
        return ""
    if run.get("reasoning") not in item["levels"] or item["top"] not in item["levels"] or (
            item["default"] is not None and item["default"] not in item["levels"]):
        raise SystemExit(f"page_config.json reasoning_levels: run {run['run']}'s reasoning ({run.get('reasoning')}) or the "
                         f"default or top level is not one of {run['model']}'s levels")
    host = item["source"].split("/")[2]
    if host not in LEVEL_SOURCES:
        raise SystemExit(f"page_config.json reasoning_levels: name the documentation at {host} in models.LEVEL_SOURCES")
    term = item["term"].removesuffix(" level")
    levels = ", ".join(f"{esc(level)} (default)" if level == item["default"] else esc(level) for level in item["levels"])
    return (f'<p>{esc(term[:1].upper() + term[1:])} levels (<a href="{esc(item["source"])}">{esc(LEVEL_SOURCES[host])}</a>, read '
            f'{bp.long_date(item["read"])}): {levels}. Top level: {esc(item["top"])}. This run: {esc(run["reasoning"])}.</p>')


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
    counts = reply_counts(run)
    if counts is not None:
        invalid = (f"<p>{esc(counts)} {esc(REPLY_RULE)} Invalid answers count as wrong "
                   f'(<a href="{rel(site.model_path(run), "method/")}#{REPLY_ANCHOR}">how</a>).</p>')
    else:
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
        f"{group}{invalid}{idk_counts(site, run, 'turkish')}"
        '<details class="show-table"><summary>Accuracy by topic</summary><div class="table-wrap"><table class="board list">'
        '<thead><tr><th scope="col">Topic</th><th scope="col">Part</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Right</th></tr></thead>'
        f"<tbody>{topics}</tbody></table></div></details>"
    )


def confidence(site: Site, run: dict[str, Any]) -> str:
    item = run["confidence"]
    sure = item["sure"]
    threshold = pct(site.config["threshold"], 0)
    skipped = site.results["questions"] - sure["questions"]
    if run["invalid"]:
        unsure = sum(entry["questions"] for entry in item["bins"]) - sure["questions"]
        if unsure + run["invalid"] != skipped:
            raise SystemExit(f"run {run['run']}: {unsure} unsure + {run['invalid']} invalid is not {skipped} skipped")
        skipped_text = (f"; {skipped:,} skipped: {unsure:,} with the model less than {threshold} sure"
                        f" and {run['invalid']:,} without a valid answer")
    else:
        skipped_text = f"; {skipped:,} skipped, the model less than {threshold} sure"
    sure_text = ((f"{sure['questions']:,}, of which {sure['questions'] - sure['correct']:,} wrong"
                  f" (share right: {interval(sure['correct'], sure['questions'])}, 95% interval)") if sure["questions"]
                 else f'<span class="nm">{NO_ANSWERS}</span>') + skipped_text
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
    source = {"run": "this run", "repeats": "its repeated runs"}
    single = run.get("single_question_latency")
    if not item:
        median = NOT_MEASURED
    elif item["source"] == "sample":
        median = f"{latency_text(item['median_request_seconds'])}, measured on a sample ({item['questions']:,} questions) over {len(item['runs'])} runs"
    else:
        median = f"{latency_text(item['median_request_seconds'])} ({source.get(item['source'], item['source'])})"
    return facts([
        ("Latency, median request", median),
        ("Latency, 90th percentile", latency_text(item.get("p90_request_seconds")) if item and item.get("p90_request_seconds") else None),
        ("Latency at 1 question per request",
         f"{latency_text(single['median_request_seconds'])} median, on {single['questions']:,} questions" if single else None),
        ("Requests at once", str(item["concurrency"]) if item else None),
        ("Throughput", f"{run['questions_per_minute']:.1f} questions per minute of request time"
         if run.get("questions_per_minute") else None),
        ("Request time", f"{run['request_seconds'] / 60:.1f} minutes, over the requests whose answers were kept"
         if run.get("request_seconds") else None),
    ]) + ('<p class="note">Latency: the time from sending one request to receiving its answer, measured from our computer, '
          'network and any retries within the request included. Request time: the time at least one request was in '
          'flight, over the requests whose answers were kept. It is not the run\'s elapsed time: it leaves out requests '
          'that failed and any pause before a run was resumed.</p>')


def per_thousand_text(site: Site, run: dict[str, Any]) -> str:
    """The setup's $ per 1,000 questions as the page shows it, in the summary and under Cost: with the upper-bound mark
    where the cost is an upper bound; No list price or Not measured without one (cost_missing)."""
    per = site.per_thousand(run)
    upper = site.config["first_cost_marks"]["upper"] if run.get("cost_upper_bound") else None
    mark = f'<span class="mark">{esc(upper["mark"])}</span> ' if upper else ""
    return f"{mark}{cost_value(per)}" if per is not None else cost_missing(run)


def cost(site: Site, run: dict[str, Any]) -> str:
    price = next((item for item in site.results["prices"] if bp.price_key(item) == bp.price_key(run)), None)
    tokens = (lambda key: f"{run[key] / run['answered_questions']:,.0f}" if run.get(key) is not None else None)
    basis = site.cost_basis_text(run)
    upper = site.config["first_cost_marks"]["upper"] if run.get("cost_upper_bound") else None
    mark = f'<span class="mark">{esc(upper["mark"])}</span> ' if upper else ""
    return cost_switch() + facts([
        (f"Cost {cost_per()}", per_thousand_text(site, run)),
        ("Whole run", f"{mark}{bp.usd(run['api_equivalent_usd'])}" if run.get("api_equivalent_usd") is not None else None),
        ("Basis", esc(basis)),
        ("Price", f'{esc(price["text"])} (<a href="{esc(price["source"])}">source</a>, {esc(price["date"])})' if price else None),
        ("Input tokens per question", tokens("input_tokens")),
        ("Output tokens per question", tokens("output_tokens")),
    ]) + (f'<p class="note">{esc(upper["mark"])} {esc(upper["note"])}</p>' if upper else "")


def routing(site: Site, run: dict[str, Any]) -> str | None:
    """What this first model took off each LLM in the replay with the cutoff chosen on half the questions."""
    path = site.model_path(run)
    marks = site.config["first_cost_marks"]
    unpriced = marks["maker"] if run.get("cost_basis") == "maker" else marks.get(run["billing"]) if run.get("api_equivalent_usd") is None else None
    marked = False
    rows = []
    items = [item for item in site.results["cascades"] if item["decision"] == run["run"]]
    for item in items:
        frontier = site.by_id[item["frontier"]]
        alone = site.per_thousand(frontier)
        held = item["held_out"]
        saving = f"{pct(1 - item['usd_per_1000'] / alone, 0)}" if alone else cost_missing(frontier)
        if unpriced and alone:
            # The maker-priced basis shows in the tooltip only, with no mark; the † keeps its mark and note.
            saving = f'<span class="hint" tabindex="0" data-tip="{esc(unpriced["tip"])}">{saving}</span>'
            if unpriced is not marks["maker"]:
                saving += f'<span class="mark">{esc(unpriced["mark"])}</span>'
                marked = True
        rows.append(
            f"<tr>{site.model_cell(path, frontier)}<td class=\"num\" data-label=\"Share taken\">{pct(held['answered'])}</td>"
            f'<td class="num" data-label="Accuracy change">{bp.points(held["difference"])} points</td>'
            f'<td class="num" data-label="Saving">{saving}</td></tr>'
        )
    if not rows:
        return None
    # The note for the †, only when the marker is in the table.
    note = f'<p class="table-note">{esc(unpriced["mark"])} {esc(unpriced["note"])}</p>' if marked else ""
    return ('<p class="note">Replay of recorded answers, cutoff chosen on half the questions, averaged over the splits. '
            f'Savings are estimates from API prices; the <a href="{rel(path, "method/")}#average-cost">Method page</a> explains how.</p>'
            '<div class="table-wrap"><table class="board list"><thead><tr><th scope="col">LLM behind it</th>'
            '<th scope="col" class="num">Share taken</th><th scope="col" class="num">Accuracy change</th><th scope="col" class="num">Saving</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>{note}')


def routed_llm(site: Site, run: dict[str, Any]) -> str | None:
    """For a routing LLM at a request size we put it behind first models: a link to the home page's Routing tab with
    it chosen."""
    for key, _, slug, sizes in ROUTE_LLMS:
        spec = site.config["named_runs"][key]
        if all(run.get(field) == value for field, value in spec.items()) and run["questions_per_request"] in sizes:
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


def page_images(site: Site, run: dict[str, Any]) -> str | None:
    """For a setup that is condition A of a model in the Page images tab: that model's row, as the tab shows it. Model
    pages keep the Preliminary caveat and heading; only the tab itself dropped them."""
    found = [model for model in site.vision["models"] if model["a_run"] == run["run"]]
    if not found:
        return None
    path = site.model_path(run)
    return (f'<p class="preliminary"><strong>Preliminary:</strong> these numbers are not final and may change. This setup is '
            f'condition A of the <a href="{rel(path, vision.PATH)}">Vision tab</a>, which asks the '
            f'{site.vision["subset"]["questions"]:,} questions with underlined or numbered words as text (A), as a page image (B), '
            "as both (C) and through OCR models (D); the share answered right, its 95% interval in the number's tooltip.</p>"
            + vision.model_table(site, path, site.vision, found))


def web_grounding(site: Site, run: dict[str, Any]) -> str | None:
    """For a setup of the model family of the web grounding test's setup: a link to that experiment's page."""
    data = site.results.get("web_grounding")
    if data is None or site.families[run["run"]] != site.families[data["text_runs"]["off"]]:
        return None
    link = f'<a href="{rel(site.model_path(run), "web-grounding/")}">Web grounding</a>'
    arm = next((arm for arm, text_run in data["text_runs"].items() if text_run == run["run"]), None)
    named = {side: site.plain(site.by_id[text_run]) for side, text_run in data["text_runs"].items()}
    if arm is not None:
        other = named["on" if arm == "off" else "off"]
        return f"<p>The same model with Perplexity's web search {'on' if arm == 'off' else 'off'} is {esc(other)}: {link} compares the two.</p>"
    return (f"<p>{esc(named['off'])} and {esc(named['on'])}, with Perplexity's web search off and on, are "
            f"compared on {link}.</p>")


def english(site: Site, run: dict[str, Any]) -> str | None:
    """For a setup with an English run (results.json english_reading.models, by its Text tab run): its right answers of
    the kept reading questions in its first English run and its accuracy (the range over its English runs where it has
    several), its English non-hallucination rate with “I don't know” where measured (english_reading.dont_know), the
    first English run's cost and median latency, the English runs' settings from their records in answers.json, and the
    rule on empty and broken replies' counts for its English “I don't know” runs (idk_counts)."""
    data = site.results.get("english_reading")
    if data is None or run["run"] not in setup_labels(site):
        return None
    model = next(item for item in data["models"] if item["turkish_run"] == run["run"])
    path, digits, total = site.model_path(run), site.config["percent_digits"], data["questions"]
    records = {item["run"]: item for item in site.answers["english_runs"]}
    held = [records[number] for number in model["runs"]]
    spread = (model["spread"] or {}).get("english")
    accuracy = pct(model["english"]["accuracy"], digits) + (
        f"; {pct(spread['low'], digits)} to {pct(spread['high'], digits)} over its {len(held)} English runs"
        if spread else "")
    idk = data["dont_know"]
    found = next((item["english"] for item in idk["models"] + english_only(idk) if item["text_run"] == run["run"]), None)
    option = esc(idk["option"])
    if found is None:
        rate, answered, error = missing_side(site, run), None, None
    else:
        value = "No rate" if found["non_hallucination"] is None else pct(found["non_hallucination"], digits)
        rate = (f"{value}: {found['dont_know']:,} “{option}” of {found['dont_know'] + found['wrong']:,} not right "
                f"(run {found['run']})")
        answered = f"{pct(found['attempt_rate'], digits)}: {found['right'] + found['wrong']:,} of {total:,}"
        wrong = hold.error_rate(found)
        error = ("No answers" if wrong is None else
                 f"{pct(wrong, digits)}: {found['wrong']:,} of {found['right'] + found['wrong']:,} answers")
    # A setting as the English runs' records hold it, each value once.
    each = lambda show: esc(", ".join(dict.fromkeys(show(record) for record in held)))  # noqa: E731
    dates = [bp.long_date(day) for day in model["dates"]]
    timing = model["latency"]["english"]
    latency_value = NOT_MEASURED if timing is None else (
        f"{latency_text(timing['median_request_seconds'])}; {timing['concurrency']:,} "
        f"request{'' if timing['concurrency'] == 1 else 's'} at once")
    return (f"<p>The Text tab's {total:,} kept reading questions translated into English, asked with this setup's Text "
            f'tab settings. Every setup: <a href="{rel(path, english_view.PATH)}">English reading</a>; against Turkish: '
            f'<a href="{rel(path, COMPARISON)}">English and Turkish</a>.</p>'
            + facts([
                ("Right answers", f"{model['english']['right']:,} of {total:,}, first English run ({model['run']})"),
                ("Accuracy", accuracy),
                (f"Non-hallucination with “{option}”", rate),
                (f"Answered with “{option}”", answered),
                (f"Error rate with “{option}”", error),
                (f"Cost, $ {cost_per()}, first English run", measure_cell(site, model, "cost", "english")),
                ("Latency, median request, first English run", latency_value),
                (f"English run{'s' if len(held) > 1 else ''}", esc(", ".join(map(str, model["runs"])))),
                (f"Date{'s' if len(dates) > 1 else ''}", esc(", ".join(dates))),
                ("Request format", each(lambda record: request_size(record["questions_per_request"]))),
                ("Reasoning", each(lambda record: NOT_RECORDED if record.get("thinking") is None else str(record["thinking"]))),
                ("Prompt version", "<code>" + each(lambda record: record["english"]["prompt_version"]) + "</code>"),
                ("Translations, SHA-256", "<code>" + each(lambda record: record["english"]["translations_sha256"]) + "</code>"),
            ])
            + idk_counts(site, run, "english"))


def summary(site: Site, run: dict[str, Any]) -> str:
    """The page's main results at the top: accuracy with its 95% interval, the answers kept at the threshold with the
    wrong ones among them, cost and the median latency, each labelled with what it covers; the sections below give the
    detail."""
    path = site.model_path(run)
    correct, total = site.accuracy(run)
    sure = run["confidence"]["sure"]
    threshold = pct(site.config["threshold"], 0)
    wrong = sure["questions"] - sure["correct"]
    kept_value = (f"{sure['questions']:,} of {site.results['questions']:,}" if sure["questions"]
                  else f'<span class="nm">{NO_ANSWERS}</span>')
    kept_detail = (f"{wrong:,} wrong; share right {interval(sure['correct'], sure['questions'])}, 95% interval"
                   if sure["questions"] else f"none of the {site.results['questions']:,} questions at {threshold} or more")
    item = run.get("latency")
    if item:
        latency_value = latency_text(item["median_request_seconds"])
        latency_detail = (f"median request, {request_size(run['questions_per_request'])}"
                          + (f", on a sample of {item['questions']:,} questions" if item["source"] == "sample" else ""))
    else:
        latency_value, latency_detail = NOT_MEASURED, "median request"
    figures = (
        (f"Accuracy, all {total:,} questions", pct(correct / total),
         f"{interval(correct, total)}, 95% interval; {correct:,} right"),
        (f"Answers kept at {threshold} confidence", kept_value, kept_detail),
        (f"Cost, $ {cost_per()}", per_thousand_text(site, run), '<a href="#cost">Basis and price under Cost</a>'),
        ("Latency", latency_value, latency_detail),
    )
    items = "".join(f'<div><dt>{label}</dt><dd><span class="key-figure">{value}</span><span class="small">{detail}</span></dd></div>'
                    for label, value, detail in figures)
    return f'<dl class="key-figures">{items}</dl><p><a href="{rel(path, "")}">Back to the leaderboard</a>.</p>'


def model_page(site: Site, run: dict[str, Any]) -> str:
    path = site.model_path(run)
    lead = summary(site, run)
    parts = [
        f'    <section class="card">\n      <p class="eyebrow">{site.kind(run)}</p>\n      <h1>{site.shown(run)}</h1>\n'
        f'      <p class="subtitle">{esc(site.detail(run))}</p>\n      {lead}{formats(site, run) or ""}{routed_llm(site, run) or ""}'
        f'{web_grounding(site, run) or ""}\n    </section>',
        section("How we called it", called(site, run), "called"),
        section("Settings", settings(site, run), "settings"),
        section("Results", results(site, run), "results"),
    ]
    images = page_images(site, run)
    if images:
        parts.append(section("Vision (preliminary)", images, "page-images"))
    english_part = english(site, run)
    if english_part:
        parts.append(section("English", english_part, ENGLISH_ANCHOR))
    parts += [
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


def redirect(site: Site) -> str:
    """The page at INDEX: sends the reader to the home page's All models view (or the group its query asks for), with
    the fragment, as english-reading/ does."""
    target = rel(INDEX, "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moved: All models</title>
  <link rel="canonical" href="{esc(site.config['site_url'])}">
  <meta http-equiv="refresh" content="0; url={target}?models=all">
  <!-- Keeps the address's group and section: the meta refresh alone drops them. -->
  <script>location.replace("{target}" + (location.search || "?models=all") + location.hash);</script>
</head>
<body>
  <p>The list of every model is now the All models view of the home page: <a href="{target}?models=all">All models</a>.</p>
</body>
</html>
"""


def build(site: Site) -> dict[str, str]:
    return {INDEX: redirect(site), **{site.model_path(run): model_page(site, run) for run in site.runs}}
