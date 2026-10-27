#!/usr/bin/env python3
"""Build the site (this folder, at /analysis/decision-models/) from results.json, answers.json and page_config.json, in
one step:

    python3 build_site.py               # charts, link preview image, CITATION.cff and every page
    python3 build_site.py --no-images   # the same, keeping the current link preview image (no Chrome needed)

It runs reproduce.py first and stops unless every check matches. It also stops when a provider that serves both decision
and chat models has a run of a model whose type we have not decided (provider_checks), and when chart-renderer's figures
give a run another type than the tables do (type_checks). Then it draws the charts with chart-renderer (cargo), the link
preview image in both themes with headless Chrome (CHROME, else google-chrome) and CITATION.cff, both from build_page.py,
and writes the pages.

The home page, index.html, keeps its copy; this script rewrites what is inside its <!-- build:name --> markers: the meta
tags, the top bar, the intro (its counts from results.json), the counters, the results version, the plain table for
readers without JavaScript (every setup) and the note under it, the settings v3.js reads, the default setup count, the
charts' "Show all" label, the topic list and the questions in view. v3.js draws everything else in the browser from
results.json. Every other page is generated whole by a module of sitebuild/ (PAGE_MODULES) and written to
<path>index.html. v1/ keeps the earlier page as it was on 14 October 2026, and v2/ and v3/ send the preview addresses
here; nothing rebuilds them.

The home page's fixed copy (the summary lines, the note under the Accuracy table, the notes under the tabs, the meta
description) quotes numbers and comparisons; copy_checks() tests each against results.json and prints every one that
differs. The pages are still written, so they can be reviewed, and the script exits with status 1.
"""

from __future__ import annotations

import argparse
import html
import importlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
ROOT = Path(__file__).resolve().parent
import benchmark_metrics as bm  # noqa: E402
import build_page as bp  # noqa: E402
from sitebuild.site import NOT_MEASURED, Site, topbar  # noqa: E402

PAGE = ROOT / "index.html"
# The modules of sitebuild/ that write pages, in build order: questions writes data/picks.json, which the others read.
PAGE_MODULES: tuple[str, ...] = ("questions", "disagreements", "topics", "models", "compare", "data", "method")
TITLE = "When should you trust a decision model?"
# The intro and the meta description; their counts come from results.json (counts()).
INTRO = (
    "Our reading comprehension and grammar test: {questions} questions answered by {decision} decision models, with "
    "chat models for comparison. A decision model scores each answer option and picks one. Grammar questions test "
    "whether a model knows a rule and can apply it. Every answer is public."
)
DESCRIPTION = (
    "We tested {decision} decision models on a reading comprehension and grammar test in native Turkish (not "
    "translated): {questions} questions. "
    "No model led on every measure. Liquid's d1-ultra got the most answers right. Of the decision models with no "
    "observed mistakes at 99% confidence, Perplexity's Decider v1.2, run on our hardware, kept the most answers. With "
    "every model at 1 question per request, the decision model "
    "with the largest share took 33% to 46% of each LLM's questions, with accuracy at most 0.32 points lower, in a "
    "replay of recorded answers."
)


SAMPLE_MARK = "*"  # a latency measured on a sample of the questions (v3.js SAMPLE_MARK)


def sample_label(run: dict[str, Any]) -> str | None:
    """"Measured on a sample (N questions)" for a latency taken from the setup's repeats on a fixed sample, else None."""
    latency = run.get("latency") or {}
    return f"Measured on a sample ({bp.count(latency['questions'])} questions)" if latency.get("source") == "sample" else None


def not_measured_note(data: Data) -> str:
    """The note under the Accuracy table, with and without JavaScript; copy_checks tests its reasons and the § note
    against the run records."""
    untimed = sum(1 for run in data.runs if (run.get("latency") or {}).get("median_request_seconds") is None)
    latency = f"; latency for {bp.count(untimed)} run{'' if untimed == 1 else 's'} made before we timed each request" if untimed else ""
    samples = sorted({label for run in data.runs if (label := sample_label(run))})
    return (f"Not measured: cost for setups on our own hardware whose maker lists no price for the same model{latency}. "
            f"{data.config['first_cost_marks']['maker']['mark']} Estimated at the maker's list price for the same model; our "
            "hardware cost is not measured." + "".join(f" {SAMPLE_MARK} {label}." for label in samples))


# The summary under the intro (fixed copy in index.html): its accuracy line, word for word as the user gave it, and the
# most words the whole block may show; summary_checks tests both on every build.
SUMMARY_ACCURACY = "Accuracy: Liquid d1-ultra, clearly ahead at 77.1%; then GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied), and Deciders v1.1 and v1.2, at 66.9% to 68.5%."
SUMMARY_WORDS = 150
# The LLMs the Routing tab puts behind a decision model, in its order, with the label of its control.
ROUTE_LLMS = (("opus", "Opus"), ("sonnet_high", "Sonnet"), ("astra", "Astra"), ("sol", "Sol"), ("gemini_low", "Gemini Flash"))
# Decision models in the charts by default, next to the routing LLMs at one question per request.
CHART_DECISION_MODELS = 8


class Data:
    """results.json and page_config.json, with the run lookups the home page needs."""

    def __init__(self) -> None:
        self.results = json.loads((ROOT / "results.json").read_text())
        self.config = json.loads((ROOT / "page_config.json").read_text())
        self.runs: list[dict[str, Any]] = self.results["runs"]
        self.by_id = {run["run"]: run for run in self.runs}

    def decision(self, run: dict[str, Any]) -> bool:
        return run["provider"] in self.config["decision_model_providers"] and run["model"] not in self.config["not_decision_models"]

    def named(self, key: str, size: int) -> dict[str, Any]:
        """A named run (page_config.json's named_runs) at a request size: its first run, or its rerun at that size."""
        spec = self.config["named_runs"][key]
        found = [run for run in self.runs
                 if all(run.get(field) == value for field, value in spec.items() if field != "questions_per_request")
                 and run["questions_per_request"] == size]
        if len(found) != 1:
            raise ValueError(f"{key} at {size} per request matches {len(found)} runs")
        return found[0]

    def by_name(self, model: str) -> dict[str, Any]:
        found = [run for run in self.runs if run["model"] == model]
        if len(found) != 1:
            raise ValueError(f"{model} matches {len(found)} runs")
        return found[0]


def accuracy(run: dict[str, Any]) -> tuple[int, int]:
    groups = run["groups"]
    return groups["reading"]["correct"] + groups["grammar"]["correct"], groups["reading"]["questions"] + groups["grammar"]["questions"]


def request_size(size: int) -> str:
    return f"{bp.count(size)} question{'' if size == 1 else 's'} per request"


def detail(run: dict[str, Any]) -> str:
    parts = [run["variant"]] if run.get("variant") else []
    if run.get("reasoning"):
        parts.append(bp.reasoning_label(run["reasoning"]))
    parts.append(request_size(run["questions_per_request"]))
    return " · ".join(parts)


def percent(fraction: float, digits: int = 1) -> str:
    """A share as a number of percent, for a column whose header names the unit: 98.1."""
    return f"{100 * fraction:.{digits}f}"


def short_detail(run: dict[str, Any]) -> str:
    """The settings in the short form a phone shows, as v3.js: "1 per request · low reasoning"; a variant keeps its part
    before a comma."""
    parts = [f"{bp.count(run['questions_per_request'])} per request"]
    if run.get("reasoning"):
        parts.append(bp.reasoning_label(run["reasoning"]))
    if run.get("variant"):
        parts.append(run["variant"].split(",")[0])
    return " · ".join(parts)


def table_name(data: Data, run: dict[str, Any]) -> str:
    """A setup's name in the table, as v3.js: on a phone, the charts' short name where it has one."""
    short = data.config["short_names"].get(run["model"])
    if not short or short == run["name"]:
        return bp.esc(run["name"])
    return f'<span class="name-long">{bp.esc(run["name"])}</span><span class="name-short">{bp.esc(short)}</span>'


def fallback_table(data: Data) -> str:
    """The Accuracy tab on all questions, every setup, as a plain table: what readers without JavaScript see. Units sit
    in the headers, each column with one number of decimals, as in v3.js. With JavaScript, the chat models' rows are
    hidden from the first paint (html.js), so the page opens as v3.js then draws it, decision models first, without a
    jump; the settings line has v3.js's long form and, on a phone, its short form."""
    rows = []
    for run in sorted(data.runs, key=lambda run: -accuracy(run)[0]):
        correct, total = accuracy(run)
        low, high = bm.wilson_interval(correct, total)
        reading, grammar = run["groups"]["reading"], run["groups"]["grammar"]
        latency = (run.get("latency") or {}).get("median_request_seconds")
        cost = bp.per_thousand(run)
        maker_mark = f'<span class="mark">{bp.esc(data.config["first_cost_marks"]["maker"]["mark"])}</span>'
        sample_mark = f'<span class="mark">{SAMPLE_MARK}</span>' if latency is not None and sample_label(run) else ""
        decision = data.decision(run)
        kind = "Decision model" if decision else "Chat model"
        rows.append(
            ("<tr>" if decision else '<tr class="chat">')
            + f'<td class="model"><a class="model-name" href="models/{run["run"]}/">{table_name(data, run)}</a>'
            f'<span class="small settings-long">{bp.esc(detail(run))} · {kind}</span>'
            f'<span class="small settings-short">{bp.esc(short_detail(run))}{"" if decision else " · chat model"}</span></td>'
            f'<td class="num">{percent(correct / total)}<span class="small">{percent(low)} to {percent(high)}</span></td>'
            f'<td class="num">{percent(reading["correct"] / reading["questions"])}</td>'
            f'<td class="num">{percent(grammar["correct"] / grammar["questions"])}</td>'
            f'<td class="num">{f"{latency:.3f}" if latency is not None else NOT_MEASURED}{sample_mark}</td>'
            f'<td class="num">{f"{cost:.3f}" if cost is not None else NOT_MEASURED}{maker_mark if run["cost_basis"] == "maker" else ""}</td>'
            "</tr>"
        )
    return (
        '<table class="board fallback"><caption>Accuracy on all '
        f'{bp.count(data.results["questions"])} questions, with its 95% interval</caption>'
        '<thead><tr><th scope="col">Model</th><th scope="col" class="num">Accuracy (%)</th><th scope="col" class="num">Reading (%)</th>'
        '<th scope="col" class="num">Grammar (%)</th><th scope="col" class="num unit-long">Median latency per request (s)</th>'
        '<th scope="col" class="num unit-long">$ per 1,000 questions</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def counts(data: Data) -> dict[str, str]:
    """The counts the intro and the meta description state: questions and decision models, from results.json."""
    return {"questions": bp.count(data.results["questions"]), "decision": bp.count(sum(map(data.decision, data.runs)))}


# chart-renderer, run through cargo: it draws the charts and reports each run's type in them (charts --types).
RENDERER = ("cargo", "run", "--release", "--quiet", "--manifest-path", "chart-renderer/Cargo.toml", "--")


def renderer(*args: str) -> str:
    """chart-renderer's standard output for args; the build stops when it fails."""
    done = subprocess.run([*RENDERER, *args], cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        sys.stderr.write(done.stdout[-2000:] + done.stderr[-2000:])
        raise SystemExit("chart-renderer failed")
    return done.stdout


def charts() -> None:
    """Every chart in both themes, drawn from results.json into charts/ by chart-renderer, which takes the decision
    model lists from page_config.json."""
    out = renderer("results.json", "page_config.json", "charts")
    print(f"Wrote {sum(line.startswith('Wrote ') for line in out.splitlines())} charts to charts/")


def provider_checks(data: Data) -> None:
    """Stops the build when a provider that serves both decision and chat models (page_config.json's mixed_providers,
    each with the models whose type we have decided) has a run of another model. The rule stays as it is: a run is a
    decision model when its provider is one of decision_model_providers and its model not one of not_decision_models.
    Decide each new model, list it under its provider, and add it to not_decision_models when it is not a decision
    model."""
    mixed = data.config["mixed_providers"]
    new = sorted({(run["provider"], run["model"]) for run in data.runs
                  if run["provider"] in mixed and run["model"] not in mixed[run["provider"]]})
    if new:
        raise SystemExit(
            "decide whether each of these is a decision model, then list it under its provider in page_config.json's "
            "mixed_providers (and in not_decision_models when it is not): "
            + ", ".join(f"{model} (provider {provider}, which serves both kinds)" for provider, model in new))


def type_checks(data: Data, site: Site, snap: bp.Snapshot) -> None:
    """Stops the build unless the figures give every run the type the tables give it. chart-renderer reports each run's
    type in the figures (charts --types); the tables' types come from build_site.py (the home page's plain table and
    counts), sitebuild (the model, compare and data pages) and build_page.py (the Method page). All of them read
    page_config.json's decision_model_providers and not_decision_models."""
    figures = {int(run): kind for run, kind in json.loads(renderer("--types", "results.json", "page_config.json")).items()}
    differ = []
    for run in data.runs:
        tables = sorted({"decision" if decide(run) else "chat" for decide in (data.decision, site.decision, snap.decision_model)})
        drawn = figures.pop(run["run"], "missing")
        if tables != [drawn]:
            differ.append(f"run {run['run']} ({run['name']}): figures {drawn}, tables {' and '.join(tables)}")
    differ += [f"run {run}: in the figures but not in results.json" for run in sorted(figures)]
    if differ:
        raise SystemExit("the figures and the tables give runs different types:\n  " + "\n  ".join(differ))
    print(f"Run types: the figures and the tables agree on all {len(data.runs)} runs")


def images(site: Site, keep: bool) -> dict[str, dict[str, str]]:
    """The link preview image in both themes, by image and theme: with keep, the current files; else drawn anew by
    build_page.py, with share/images.json naming them and earlier images removed until "announced" holds a date."""
    if keep:
        return bp.current_images()
    names = bp.render_images(site.snapshot)
    bp.remove_old_images(site.snapshot, names)
    bp.IMAGES.write_text(json.dumps(names, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return names


def head(data: Data, image: str) -> str:
    """The title, the description, the canonical address and the link preview (image: its path in the site)."""
    site = data.config["site_url"]
    image_url = site + image
    size = data.config["images"]["preview"]
    title = f"{TITLE} · Hilde"
    text = bp.esc(DESCRIPTION.format(**counts(data)))
    return (
        f"\n  <title>{bp.esc(title)}</title>\n"
        f'  <link rel="canonical" href="{site}">\n'
        f'  <meta name="description" content="{text}">\n'
        f'  <meta property="og:title" content="{bp.esc(title)}">\n'
        f'  <meta property="og:description" content="{text}">\n'
        '  <meta property="og:type" content="website">\n'
        f'  <meta property="og:url" content="{site}">\n'
        f'  <meta property="og:image" content="{image_url}">\n'
        f'  <meta property="og:image:width" content="{size["width"]}">\n'
        f'  <meta property="og:image:height" content="{size["height"]}">\n'
        '  <meta name="twitter:card" content="summary_large_image">\n'
        f'  <meta name="twitter:title" content="{bp.esc(title)}">\n'
        f'  <meta name="twitter:description" content="{text}">\n'
        f'  <meta name="twitter:image" content="{image_url}">\n  '
    )


def stats(data: Data) -> str:
    """The counters, as read-only readouts."""
    items = (
        (data.results["questions"], "questions"),
        (len(data.results["units"]), "topics"),
        (sum(map(data.decision, data.runs)), "decision models"),
        (len(data.runs), "setups"),
    )
    return "".join(
        f'<li class="readout"><span class="readout-value">{bp.count(value)}</span> <span class="readout-label">{label}</span></li>'
        for value, label in items
    )


def setups(data: Data) -> str:
    """The setup count the page opens with: the decision models, the default model type, on the Accuracy tab."""
    return f"{bp.count(sum(map(data.decision, data.runs)))} of {bp.count(len(data.runs))} setups"


def show_all(data: Data) -> str:
    """The charts' "Show all" key as the page opens, on the default model type (decision models): every setup it would
    show. v3.js relabels it for the filters in view and hides it when it would add nothing."""
    return f"Show all {bp.count(sum(map(data.decision, data.runs)))}"


def topics(data: Data) -> str:
    """The Topic menu's options, Reading first, as v3.js draws them."""
    reading = set(data.config["reading_units"])
    groups = []
    for label, part in (("Reading", True), ("Grammar", False)):
        options = "".join(f'<option value="{unit["number"]}">{bp.esc(unit["english"])}</option>'
                          for unit in data.results["units"] if (unit["number"] in reading) == part)
        groups.append(f'<optgroup label="{label}">{options}</optgroup>')
    return '<option value="">All topics</option>' + "".join(groups)


def page_settings(data: Data) -> str:
    """What v3.js needs beyond results.json: which runs are decision models, the topics' parts, the routing LLMs."""
    settings = {
        "decisionProviders": data.config["decision_model_providers"],
        "notDecisionModels": data.config["not_decision_models"],
        "readingUnits": data.config["reading_units"],
        "threshold": data.config["threshold"],
        "shortNames": data.config["short_names"],
        # A chart label for a setup whose model ID another setup shares, by provider then model.
        "chartLabels": data.config["chart_labels"],
        "chartDecisionModels": CHART_DECISION_MODELS,
        # The ranking charts' colours for decision models, worst to best (page_config.json rank_scale).
        "rankScale": data.config["rank_scale"]["stops"],
        # A saving whose first model ran on our own hardware: its marker, tooltip and note, by how its cost was counted.
        "firstCostMarks": {key: value for key, value in data.config["first_cost_marks"].items() if key != "about"},
        # The note under the Accuracy table (not_measured_note), also under the plain table.
        "notMeasuredNote": not_measured_note(data),
        "routeLlms": [
            {"key": key, "label": label, "runs": {str(size): data.named(key, size)["run"] for size in (1, 16)}}
            for key, label in ROUTE_LLMS
        ],
        # The address and versions a downloaded chart names.
        "siteAddress": data.config["site_url"].removeprefix("https://").rstrip("/"),
        "keyVersion": data.results["answer_key"]["version"],
    }
    return f'<script type="application/json" id="v3-settings">{json.dumps(settings, separators=(",", ":"))}</script>'


def version(data: Data) -> str:
    results = data.results
    return (f"Results {bp.esc(results['results_version'])}, updated {bp.long_date(results['updated'])}; "
            f"answer key version {results['answer_key']['version']}.")


def copy_checks(data: Data) -> list[str]:
    """Each number or comparison the fixed copy states, checked against results.json; the claims that differ."""
    results, runs = data.results, data.runs
    decision = [run for run in runs if data.decision(run)]
    ultra, glide, glide12, d3, d3_ultra, decider, subq, decider12 = (data.by_name(model) for model in
                                                                     ("d1-ultra", "fastino/GLiDE", "glide-v1.2", "vllm-sr/d3",
                                                                      "vllm-sr/d3-ultra", "pplx-decider-v1.1-27b",
                                                                      "subq-snap-preview", "pplx-decider-v1.2"))
    cascades = {(item["decision"], item["frontier"]): item for item in results["cascades"]}
    sonnet16, sonnet1 = data.named("sonnet_high", 16), data.named("sonnet_high", 1)
    found = []

    def check(claim: str, holds: bool) -> None:
        if not holds:
            found.append(claim)

    check("Stability: every repeated setup ran 5 times", all(len(item["runs"]) == 5 for item in results["repeats"]))
    best = max(decision, key=lambda run: accuracy(run)[0])
    check("Liquid's d1-ultra got the most answers right (among decision models)", best is ultra)
    flawless = [run for run in decision if run["confidence"]["sure"]["questions"] == run["confidence"]["sure"]["correct"]]
    flawless_kept = sorted((run["confidence"]["sure"]["questions"], run["run"]) for run in flawless)
    check("Of the decision models with no observed mistakes at 99% confidence, Decider v1.2 kept the most answers",
          flawless_kept[-1][1] == decider12["run"] and flawless_kept[-1][0] > flawless_kept[-2][0])
    check("Decider v1.2 ran on our hardware (description: run on our hardware)", decider12["billing"] == "local")
    # In front of each routing LLM at 1 question per request, the decision model with the largest share of its questions,
    # with the cutoff chosen on half the questions (d1-ultra in front of all five).
    best_first = []
    for key, _ in ROUTE_LLMS:
        frontier = data.named(key, 1)["run"]
        best_first.append(max((cascades[(run["run"], frontier)]["held_out"] for run in decision if (run["run"], frontier) in cascades),
                              key=lambda item: item["answered"]))
    check("the decision model with the largest share took 33% to 46% of each LLM's questions",
          (round(100 * min(item["answered"] for item in best_first)), round(100 * max(item["answered"] for item in best_first))) == (33, 46))
    check("accuracy at most 0.32 points lower", round(-100 * min(item["difference"] for item in best_first), 2) == 0.32)
    check("every decision model at 1 question per request", all(run["questions_per_request"] == 1 for run in decision))
    # Better than chance: an overall AUROC above 0.5. Laya and Laya multilingual rank below it.
    for run in decision:
        confidence = run["confidence"]
        parts = confidence["parts"]
        check(f"Every decision model that ranks its answers better than chance ranks them less well on grammar than on "
              f"reading: {run['name']} (reading {parts['meaning']['auroc']:.3f}, grammar {parts['form']['auroc']:.3f})",
              confidence["auroc"] <= 0.5 or parts["form"]["auroc"] < parts["meaning"]["auroc"])
    live = [item for item in results["pipelines"] if item["decision"] == decider["run"] and item["frontier"] == sonnet16["run"]
            and item["batch_size"] == 1 and item["rule"] == "half"]
    check("one live test with Sonnet at 1 question per request", len(live) == 1)
    if live:
        test = live[0]
        check("accuracy fell 4.73 points", round(-100 * test["measured"]["difference"], 2) == 4.73)
        check("Decider v1.1 kept 51%", round(100 * test["routed"] / test["held_out"]) == 51)
        # The cutoff is the one the same live test chose on 16-per-request answers.
        sixteen = [item["threshold"] for item in results["pipelines"] if item["decision"] == decider["run"]
                   and item["frontier"] == sonnet16["run"] and item["batch_size"] == 16 and item["rule"] == "half"]
        check("with a cutoff chosen at 16 per request", sixteen == [test["threshold"]])
    one = cascades[(decider["run"], sonnet1["run"])]["held_out"]
    check("A cutoff chosen at 1 per request keeps 29%", round(100 * one["answered"]) == 29)
    check("and accuracy falls 0.16 points (replay)", round(-100 * one["difference"], 2) == 0.16)
    order = sorted((run for run in decision if (run["run"], sonnet16["run"]) in cascades),
                   key=lambda run: -cascades[(run["run"], sonnet16["run"])]["held_out"]["answered"])
    check("SubQ Snap seventh among decision models in front of Sonnet (16 per request)", order.index(subq) == 6)
    for size in (16, 1):
        for key, place, word in (("opus", 13, "thirteenth"), ("astra", 11, "eleventh")):
            frontier = data.named(key, size)["run"]
            ranked = sorted((run for run in decision if (run["run"], frontier) in cascades),
                            key=lambda run: -cascades[(run["run"], frontier)]["held_out"]["answered"])
            check(f"SubQ Snap {word} in front of {key} ({size} per request): place {ranked.index(subq) + 1}",
                  ranked.index(subq) + 1 == place)
    for run, text in ((subq, 98.6), (decider, 99.3), (glide, 99.5)):
        check(f"{run['name']}'s most confident fifth was {text}% right",
              round(100 * run["confidence"]["coverage_accuracy"]["0.20"], 1) == text)
    luna = [run for run in runs if run["model"] == "gpt-6-luna"]
    check("Luna's two setups differ in request format (1 against 16 questions)",
          sorted(run["questions_per_request"] for run in luna) == [1, 16])
    # The Stability note: decision models and two Qwen3.8-27B setups repeated on all questions, the other chat models on
    # a sample of 200 questions. A repeat entry names its provider and model, as a run does.
    chat_repeats = [item for item in results["repeats"] if not data.decision(item)]
    check("Stability note: every repeated decision model ran on all questions",
          all(item["whole_bank"] for item in results["repeats"] if data.decision(item)))
    chat_whole = [item for item in chat_repeats if item["whole_bank"]]
    check("Stability note: two Qwen3.8-27B setups were the chat models repeated on all questions",
          len(chat_whole) == 2 and all(item["name"].startswith("Qwen3.8-27B") for item in chat_whole))
    check("Stability note: the other chat models were repeated on a sample of 200",
          all(item["questions"] == 200 for item in chat_repeats if not item["whole_bank"]))
    # The summary under the intro, with the Routing tab's default choices (the cutoff chosen on half the questions,
    # replayed): Liquid d1-ultra leads on accuracy and shares a letter with no other decision model; then GLiDE v1.2,
    # GLiDE, vLLM-SR d3 and d3-ultra (tied on right answers) and Deciders v1.1 and v1.2, in that order, at 66.9% to 68.5%;
    # Liquid d1.1 has the smallest calibration gap as
    # shipped; Open-Jev 27B v1.1 and Decider v1.1 score highest on Better than a flat guess; d1-ultra gives the biggest
    # estimated saving in all 10 LLM setups.
    ranked = sorted(decision, key=lambda run: -accuracy(run)[0])

    def shares(first: dict[str, Any], second: dict[str, Any]) -> bool:
        return any(letter in (second.get("group") or "") for letter in (first.get("group") or ""))

    def percent(run: dict[str, Any]) -> str:
        correct, total = accuracy(run)
        return f"{100 * correct / total:.1f}"

    check("Summary: Liquid d1-ultra has the highest accuracy among decision models, at 77.1%",
          ranked[0] is ultra and percent(ultra) == "77.1")
    check("Summary: d1-ultra is clearly ahead: it shares a letter with no other decision model",
          not any(shares(ultra, run) for run in decision if run is not ultra))
    check("Summary: then GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied), and Deciders v1.1 and v1.2, in that order",
          ranked[1] is glide12 and ranked[2] is glide and {run["run"] for run in ranked[3:5]} == {d3["run"], d3_ultra["run"]}
          and accuracy(d3) == accuracy(d3_ultra) and {run["run"] for run in ranked[5:7]} == {decider["run"], decider12["run"]})
    near = (glide12, glide, d3, d3_ultra, decider, decider12)
    check("Summary: at 66.9% to 68.5%",
          min(percent(run) for run in near) == "66.9" and max(percent(run) for run in near) == "68.5")
    calibrated = sorted(decision, key=lambda run: run["confidence"]["ece"])
    check("Summary: calibration gap, as shipped: Liquid d1.1 had the smallest gap among decision models",
          calibrated[0] is data.by_name("d1.1"))
    flat = sorted(decision, key=lambda run: -bp.flat_gain(run))
    check("Summary: better than a flat guess, after refit: Open-Jev 27B v1.1 (31.9%) and Perplexity Decider 27B v1.1 (31.5%), "
          "the two highest among decision models",
          flat[0] is data.by_name("open-jev-27b-v1.1") and flat[1] is data.by_name("pplx-decider-v1.1-27b")
          and [f"{bp.flat_gain(run):.1f}" for run in flat[:2]] == ["31.9", "31.5"])

    def best_share(part: str) -> str:
        return f"{100 * max(run['groups'][part]['correct'] / run['groups'][part]['questions'] for run in decision):.1f}"

    check("Summary: decision models got up to 92.1% of the reading questions right", best_share("reading") == "92.1")
    check("Summary: but at most 70.7% of the grammar questions", best_share("grammar") == "70.7")
    # The note under the Accuracy table: a setup without a cost runs on our hardware, and its maker lists no price for
    # the same model; every other cost of a setup on our hardware is at its maker's list price (§); Liquid d1 is
    # estimated at Liquid's list price; no latency for runs made before requests were timed one by one.
    prices = {(price["provider"], price["model"]): price for price in results["prices"]}
    check("Not measured note: every setup without a cost runs on our hardware, with no maker's price for the same model",
          all(run["billing"] == "local" and run["cost_basis"] is None for run in runs if run["api_equivalent_usd"] is None))
    check("§ note: every cost of a setup on our hardware is at its maker's list price for the same model",
          all(run["cost_basis"] == "maker" and prices[(run["provider"], run["model"])]["applies_to"] == "maker"
              and prices[(run["provider"], run["model"])]["basis"].endswith("'s list price for the same model")
              for run in runs if run["billing"] == "local" and run["api_equivalent_usd"] is not None))
    d1 = data.by_name("d1:free")
    check("Liquid d1's run used the free tier and is estimated at Liquid's list price for the same model",
          d1["billing"] == "free" and d1["cost_basis"] == "free tier"
          and prices[(d1["provider"], d1["model"])]["basis"] == "Liquid's list price for the same model")
    first_timed = min(run["started"] for run in runs if run["median_request_seconds"] is not None)
    check("Not measured note: every run without a latency was made before requests were timed one by one",
          all(run["started"] < first_timed for run in runs if (run.get("latency") or {}).get("median_request_seconds") is None))
    winners = []
    for key, _ in ROUTE_LLMS:
        for size in (1, 16):
            frontier = data.named(key, size)
            alone = bp.per_thousand(frontier)
            savings = [(1 - cascades[(run["run"], frontier["run"])]["usd_per_1000"] / alone, run["run"])
                       for run in decision if (run["run"], frontier["run"]) in cascades]
            winners.append(max(savings)[1])
    leader, times = Counter(winners).most_common(1)[0]
    check("Summary: d1-ultra gave the biggest estimated saving in all 10 LLM setups",
          len(winners) == 10 and times == 10 and leader == ultra["run"])
    return found


def summary_text(fragment: str) -> str:
    """The text a fragment of index.html shows: block tags end a word, inline tags don't; whitespace collapsed."""
    text = re.sub(r"</?(?:p|li|ul|div)\b[^>]*>", " ", fragment)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def summary_checks(page: str) -> tuple[list[str], int]:
    """The summary under the intro: its accuracy line word for word (SUMMARY_ACCURACY) and at most SUMMARY_WORDS words
    in the whole block; the claims that differ, and the block's word count."""
    block = re.search(r'<div class="summary">(.*?)</div>', page, re.S)
    if block is None:
        return ["index.html has its summary block"], 0
    lines = [summary_text(item) for item in re.findall(r"<li>(.*?)</li>", block.group(1), re.S)]
    words = len(summary_text(block.group(1)).split())
    found = []
    if SUMMARY_ACCURACY not in lines:
        found.append(f"Summary accuracy line, word for word: {SUMMARY_ACCURACY}")
    if words > SUMMARY_WORDS:
        found.append(f"Summary block at most {SUMMARY_WORDS} words ({words})")
    return found, words


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-images", action="store_true", help="keep the current link preview image (no Chrome needed)")
    args = parser.parse_args()
    data, site = Data(), Site()
    provider_checks(data)
    snap = site.snapshot  # runs reproduce.py: the build stops here unless every check matches
    type_checks(data, site, snap)
    charts()
    names = images(site, args.no_images)
    bp.CITATION.write_text(bp.citation(snap, site.values), encoding="utf-8")
    print(f"Wrote {bp.CITATION.relative_to(ROOT)}")
    blocks = {
        "head": head(data, names["preview"]["dark"]),
        "intro": bp.esc(INTRO.format(**counts(data))),
        "topbar": topbar(""),
        "stats": stats(data),
        "version": version(data),
        "setups": setups(data),
        "topics": topics(data),
        "show-all": show_all(data),
        "questions": f"{bp.count(data.results['questions'])} questions",
        "board": fallback_table(data),
        "settings": page_settings(data),
        "board-note": f'<div class="tab-notes"><p>{bp.esc(not_measured_note(data))}</p></div>',
    }
    text = PAGE.read_text()
    seen = set()

    def fill(match: Any) -> str:
        seen.add(match.group(2))
        return match.group(1) + blocks[match.group(2)] + match.group(4)

    text = bp.BLOCK.sub(fill, text)
    if seen != set(blocks):
        raise ValueError(f"index.html lacks the markers {sorted(set(blocks) - seen)}")
    PAGE.write_text(text)
    written = write_pages(site)
    summary, words = summary_checks(text)
    print(f"Summary block: {words} words (at most {SUMMARY_WORDS})")
    differ = copy_checks(data) + summary
    for claim in differ:
        print(f"copy differs from results.json: {claim}", file=sys.stderr)
    print(f"wrote index.html and {written} other pages; {len(differ)} copy claims differ from results.json")
    return 1 if differ else 0


def write_pages(site: Site) -> int:
    """Every page of PAGE_MODULES, each to <path>index.html; the number of pages written."""
    written = 0
    for name in PAGE_MODULES:
        module = importlib.import_module(f"sitebuild.{name}")
        for path, text in module.build(site).items():
            target = ROOT / path / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written += 1
    return written


if __name__ == "__main__":
    sys.exit(main())
