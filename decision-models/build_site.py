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

The home page, index.html, is the Text tab; vision/ (sitebuild/vision.py) is the Page images tab, dont-know/
(sitebuild/dont_know.py) the Hallucination tab and turkish-vs-english/ (sitebuild/english_reading.py) the Turkish vs
English tab, with a redirect at its earlier address english-reading/. index.html keeps its copy; this script rewrites
what is inside its <!-- build:name --> markers: the meta tags, the
top bar, the intro (its counts from results.json), the counters, the results version, the plain table for
readers without JavaScript (every setup, decision and chat models ranked together, the page's all view) and the note
under it, the settings v3.js reads, the default setup count, the topic list, the part keys with their question counts
and the questions in view. v3.js
draws everything else in the browser from data/home.json and data/home-more.json, which this script writes from
results.json (home_data). Every other page is generated whole by a module of sitebuild/
(PAGE_MODULES) and written to <path>index.html. v1/ keeps the earlier page as it was on 14 October 2026, and v2/ and v3/
send the preview addresses here; nothing rebuilds them.

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
from sitebuild.dont_know import ranked as dont_know_ranked, running_setups  # noqa: E402
from sitebuild.site import (GROUPS, NOT_MEASURED, ROUTE_LLMS, Site, asset, cost_missing, cost_unit_in, cost_value, experiments,  # noqa: E402
                            family_icon, family_legend, hbars, pct, route_labels, run_families, shown, topbar)

PAGE = ROOT / "index.html"
# The home page's data, from results.json, which stays the published download: HOME, preloaded, holds what v3.js's
# first draw reads (HOME_KEYS and the runs, each run's confidence cut to the sure counts the Cost table shows); HOME_MORE
# the runs' whole confidence and the cascades, which v3.js loads when the Calibration chart nears the view or the
# Confidence or Routing tab opens. Both are paths inside the site, as asset takes them.
HOME = "data/home.json"
HOME_MORE = "data/home-more.json"
HOME_KEYS = ("results_version", "questions", "sure_threshold", "units", "prices", "dont_know", "pipelines", "repeats",
             "replay")
# The modules of sitebuild/ that write pages, in build order: questions writes data/picks.json, which the others read.
PAGE_MODULES: tuple[str, ...] = ("questions", "disagreements", "topics", "models", "compare", "vision", "dont_know",
                                 "english_reading", "english_view", "aa_index", "web_grounding", "pws_decisions", "data",
                                 "method")
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
    """What the Accuracy table leaves unmeasured beyond its costs (Site.cost_note writes the cost line before it), with and
    without JavaScript: latency for runs made before requests were timed, and the sample marks; copy_checks tests its
    reasons against the run records."""
    untimed = sum(1 for run in data.runs if (run.get("latency") or {}).get("median_request_seconds") is None)
    latency = (f"Not measured: latency for {bp.count(untimed)} run{'' if untimed == 1 else 's'} made before we timed each "
               "request." if untimed else "")
    samples = sorted({label for run in data.runs if (label := sample_label(run))})
    return " ".join([latency, *(f"{SAMPLE_MARK} {label}." for label in samples)]).strip()


# The summary under the intro (fixed copy in index.html): its accuracy line, word for word as the user gave it, and the
# most words the whole block may show; summary_checks tests both on every build.
SUMMARY_ACCURACY = "Accuracy: Liquid d1-ultra, clearly ahead at 77.1%; then Decider v1.2 (with web), GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied), Drex Max v1 and 1.1, Mammoth-1, and Deciders v1.1 and v1.2, at 66.9% to 68.7%."
SUMMARY_WORDS = 150
# The LLMs the Routing tab puts behind a decision model: sitebuild.site.ROUTE_LLMS (key, label, URL slug, request sizes).
# Copy about the routing LLMs at one question per request covers only those with a run at that size.
ONE_PER_REQUEST_LLMS = tuple(key for key, _, _, sizes in ROUTE_LLMS if 1 in sizes)


class Data:
    """results.json and page_config.json, with the run lookups the home page needs."""

    def __init__(self) -> None:
        self.results = json.loads((ROOT / "results.json").read_text())
        self.config = json.loads((ROOT / "page_config.json").read_text())
        self.runs: list[dict[str, Any]] = self.results["runs"]
        self.by_id = {run["run"]: run for run in self.runs}
        # The route of each run whose model ID runs as both kinds of model, by run id (sitebuild.site.route_labels).
        self.route_labels = route_labels(self.runs, self.decision)

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

    def by_name(self, model: str, provider: str | None = None, mode: str | None = "any") -> dict[str, Any]:
        """The one run of `model` (through `provider`, and with the Perplexity `mode`, where other setups share the model
        ID)."""
        found = [run for run in self.runs if run["model"] == model and provider in (None, run["provider"])
                 and mode in ("any", run.get("perplexity_mode"))]
        if len(found) != 1:
            raise ValueError(f"{model} ({provider or 'any provider'}) matches {len(found)} runs")
        return found[0]


def accuracy(run: dict[str, Any]) -> tuple[int, int]:
    groups = run["groups"]
    return groups["reading"]["correct"] + groups["grammar"]["correct"], groups["reading"]["questions"] + groups["grammar"]["questions"]


def percent(fraction: float, digits: int = 1) -> str:
    """A share as a number of percent, for a column whose header names the unit: 98.1."""
    return f"{100 * fraction:.{digits}f}"


def fallback_table(data: Data, site: Site) -> str:
    """The Accuracy tab on all questions as one plain table, as v3.js opens the all view (?models=all, the default):
    every setup, decision and chat models ranked together by accuracy. Readers without JavaScript see it; with
    JavaScript, v3.js replaces it with the table of the group in view. Units sit in the headers, each column with one
    number of decimals, as in v3.js; each name is the full name with only what tells it apart (Site.names), its
    settings in its tooltip; a cost carries no basis mark (its tooltip and the note under the table give the basis)."""
    rows: list[str] = []
    names = site.names(data.runs)
    for run in sorted(data.runs, key=lambda run: -accuracy(run)[0]):
        correct, total = accuracy(run)
        low, high = bm.wilson_interval(correct, total)
        reading, grammar = run["groups"]["reading"], run["groups"]["grammar"]
        latency = (run.get("latency") or {}).get("median_request_seconds")
        cost = bp.per_thousand(run)
        upper_mark = f'<span class="mark">{bp.esc(data.config["first_cost_marks"]["upper"]["mark"])}</span> '
        sample_mark = f'<span class="mark">{SAMPLE_MARK}</span>' if latency is not None and sample_label(run) else ""
        about = f"{site.detail(run)} · {'Decision model' if data.decision(run) else 'Chat model'}"
        tip = site.cost_tip(run)
        cost_text = f'<span title="{bp.esc(tip)}">{cost:.3f}</span>' if cost is not None and tip else f"{cost:.3f}" if cost is not None else cost_missing(run)
        rows.append(
            "<tr>"
            f'<td class="model">{site.icon(run)}<a class="model-name" href="models/{run["run"]}/" title="{bp.esc(about)}">{bp.esc(names[run["run"]])}</a></td>'
            f'<td class="num">{percent(correct / total)}<span class="small">{percent(low)} to {percent(high)}</span></td>'
            f'<td class="num">{percent(reading["correct"] / reading["questions"])}</td>'
            f'<td class="num">{percent(grammar["correct"] / grammar["questions"])}</td>'
            f'<td class="num">{bp.seconds(latency) if latency is not None else NOT_MEASURED}{sample_mark}</td>'
            f'<td class="num">{upper_mark if run.get("cost_upper_bound") and cost is not None else ""}{cost_text}</td>'
            "</tr>"
        )
    questions = bp.count(data.results["questions"])
    return (
        '<h3 class="board-group">All models</h3><div class="table-frame"><div class="table-wrap"><table class="board fallback">'
        f"<caption>Accuracy on all {questions} questions, with its 95% interval</caption>"
        '<thead><tr><th scope="col">Model</th><th scope="col" class="num">Accuracy (%)</th><th scope="col" class="num">Reading (%)</th>'
        '<th scope="col" class="num">Grammar (%)</th><th scope="col" class="num unit-long">Median latency per request (s)</th>'
        '<th scope="col" class="num unit-long">$ per 1,000 questions</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>'
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
    """The setup count the page opens with: every setup, in its one table, on the Accuracy tab."""
    return f"{bp.count(len(data.runs))} of {bp.count(len(data.runs))} setups"


def topics(data: Data) -> str:
    """The Topic menu's options, Reading first, as v3.js draws them."""
    reading = set(data.config["reading_units"])
    groups = []
    for label, part in (("Reading", True), ("Grammar", False)):
        options = "".join(f'<option value="{unit["number"]}">{bp.esc(unit["english"])}</option>'
                          for unit in data.results["units"] if (unit["number"] in reading) == part)
        groups.append(f'<optgroup label="{label}">{options}</optgroup>')
    return '<option value="">All topics</option>' + "".join(groups)


def parts(data: Data) -> str:
    """The part keys above the Accuracy chart, each with its question count (runs[].groups, as v3.js counts them): All,
    Reading, Grammar. v3.js marks the pressed one."""
    groups = data.runs[0]["groups"]
    keys = (("all", "All", groups["reading"]["questions"] + groups["grammar"]["questions"]),
            ("reading", "Reading", groups["reading"]["questions"]), ("grammar", "Grammar", groups["grammar"]["questions"]))
    return "".join(
        f'<button type="button" class="key" data-part="{part}" aria-pressed="{str(part == "all").lower()}">'
        f'<span class="lamp" aria-hidden="true"></span>{label} <span class="key-count">{bp.count(count)}</span></button>'
        for part, label, count in keys
    )


def page_settings(data: Data) -> str:
    """What v3.js needs beyond its data files: their versioned addresses, which runs are decision models, the topics'
    parts, the routing LLMs."""
    settings = {
        "homeUrl": asset(HOME),
        "moreUrl": asset(HOME_MORE),
        "decisionProviders": data.config["decision_model_providers"],
        "notDecisionModels": data.config["not_decision_models"],
        "readingUnits": data.config["reading_units"],
        "threshold": data.config["threshold"],
        # Each route label, by run id.
        "routeLabels": data.route_labels,
        # The charts' colours: each run's model family by run id, and each family's colour (page_config.json
        # model_families; run_families stops the build unless every run has exactly one family).
        "families": {run: family["name"] for run, family in run_families(data.config, data.runs).items()},
        "familyColours": {family["name"]: family["colour"] for family in data.config["model_families"]["families"]},
        # A saving whose first model ran on our own hardware: its marker, tooltip and note, by how its cost was counted.
        "firstCostMarks": {key: value for key, value in data.config["first_cost_marks"].items() if key != "about"},
        # The note under the Accuracy table (not_measured_note), also under the plain table.
        "notMeasuredNote": not_measured_note(data),
        # The Routing tab's LLMs: each with its URL slug and its run at each request size we ran it at.
        "routeLlms": [
            {"key": key, "label": label, "slug": slug, "runs": {str(size): data.named(key, size)["run"] for size in sizes}}
            for key, label, slug, sizes in ROUTE_LLMS
        ],
        # The address and versions a downloaded chart names.
        "siteAddress": data.config["site_url"].removeprefix("https://").rstrip("/"),
        "keyVersion": data.results["answer_key"]["version"],
    }
    return f'<script type="application/json" id="v3-settings">{json.dumps(settings, separators=(",", ":"))}</script>'


def home_data(data: Data) -> None:
    """Write HOME and HOME_MORE (see there) from results.json, compact. A cascade drops its curve, which v3.js never
    reads."""
    results = data.results

    def first(run: dict[str, Any]) -> dict[str, Any]:
        slim = {key: value for key, value in run.items() if key != "confidence"}
        sure = (run.get("confidence") or {}).get("sure")
        if sure is not None:
            slim["confidence"] = {"sure": sure}
        return slim

    home = {key: results[key] for key in HOME_KEYS if key in results} | {"runs": [first(run) for run in data.runs]}
    more = {"confidence": {str(run["run"]): run["confidence"] for run in data.runs if run.get("confidence")},
            "cascades": [{key: value for key, value in item.items() if key != "curve"} for item in results["cascades"]]}
    for path, content in ((HOME, home), (HOME_MORE, more)):
        text = json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n"
        (ROOT / path).write_text(text, encoding="utf-8")
        print(f"Wrote {path} ({len(text.encode()):,} bytes)")


# What a view bar group's members are called on the home page's Non-hallucination part, one and several.
NON_HALLUCINATION_NOUNS = {"all": ("setup", "setups"), "decision": ("decision model", "decision models"),
                           "chat": ("chat model setup", "chat model setups")}


def non_hallucination(site: Site) -> str:
    """The home page's Non-hallucination part (#non-hallucination, row 3 of the view bar), in static HTML, once per group
    of the view bar (data-models, toggled by site.js; the all group shown without JavaScript): the group's Hallucination
    tab rows (results.json dont_know, each row's group; all: decision and chat models ranked together) in that tab's
    order, each bar its non-hallucination rate with the option in its model family's colour, then in columns of their
    own its attempt rate (the share of the questions answered, as that tab writes them) and its error rate among its
    answers (wrong over right + wrong); under the chart the group's chat setups whose Turkish run with the option is
    still running (running_setups), with page_config.json's reason, under the same one heading."""
    data = site.results["dont_know"]
    digits, option, total = site.config["percent_digits"], data["option"], data["questions"]
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    for model in data["models"]:
        if model["group"] != ("decision" if site.decision(run_of(model)) else "chat"):
            raise SystemExit(f"results.json dont_know: {model['name']} (run {model['run']}) is not in group {model['group']} on the Text tab")
    tab = '<a href="dont-know/">Hallucination tab</a>'

    def error(model: dict[str, Any]) -> str:
        answered = model["right"] + model["wrong"]
        return pct(model["wrong"] / answered, digits) if answered else NOT_MEASURED

    def copy(group: str) -> str:
        models = dont_know_ranked([model for model in data["models"] if group == "all" or model["group"] == group])
        rated = [model for model in models if model["non_hallucination"] is not None]
        undefined = [site.row_name(run_of(model)) for model in models if model["non_hallucination"] is None]
        runs = [run for run in running_setups(site) if group != "decision" and not site.decision(run)]
        names = site.names(runs)
        running = [names[run["run"]] for run in runs]
        one, many = NON_HALLUCINATION_NOUNS[group]
        rows = [{"label": site.row_name(run_of(model)), "family": site.families[model["original_run"]]["name"],
                 "href": site.model_path(run_of(model)),
                 "texts": [pct(model["non_hallucination"], digits), pct(model["attempt_rate"], digits), error(model)],
                 "bars": [{"value": model["non_hallucination"], "colour": site.families[model["original_run"]]["colour"]}],
                 "title": f"{site.row_name(run_of(model))}: {model['dont_know']:,} “{option}” of "
                          f"{model['dont_know'] + model['wrong']:,} not right; {model['right'] + model['wrong']:,} of {total:,} "
                          f"answered, {model['wrong']:,} of them wrong (run {model['run']})"}
                for model in rated]
        running_note = (f" <span>{bp.esc(site.config['dont_know']['running'].removesuffix('.'))}; still running in Turkish: "
                        f"{bp.esc(', '.join(running))}.</span>") if running else ""
        if not models:
            return (f'<div {shown(group)}><p class="note">No {one} has a run with “{bp.esc(option)}” yet.{running_note}</p>'
                    "</div>")
        return (f'<div {shown(group)}><p class="chart-sub">“{bp.esc(option)}” among the answers that were not right, with it '
                f"offered as a sixth option on the {total:,} questions; beside it the share answered (right + wrong of {total:,}) "
                f"and the error rate among the answers (wrong of right + wrong): each of the {len(models)} "
                f"{one if len(models) == 1 else many}' first run with it · higher non-hallucination is better, read with the "
                "share answered</p>"
                f'{hbars(rows, columns=[("Non-hallucination", "Non-hall."), ("Answered", "Ans."), ("Error rate (wrong / answered)", "Error")])}'
                f'<p class="chart-legend">{family_legend([site.families[model["original_run"]] for model in rated])} '
                "<span>A model that always chose the option would reach 100% with no right answers.</span>"
                + (f" <span>No rate (neither a wrong answer nor “{bp.esc(option)}”): {bp.esc(', '.join(undefined))}.</span>"
                   if undefined else "")
                + running_note
                + f" <span>The {tab} has the full table, the rate against each model's own confidence and the method.</span>"
                "</p></div>")

    return ('<figure class="panel chart-card" id="chart-non-hallucination"><div class="chart-head"><h2>Non-hallucination</h2>'
            "</div>" + "".join(copy(group) for group in GROUPS) + "</figure>")


# The groups of the view bar's row 2 (?models=) the result cards cover, each in the words that name a card's scope.
CARD_SCOPES = {"all": "all {n} setups", "decision": "the {n} decision-model setups", "chat": "the {n} chat-model setups"}


def group_runs(data: Data, group: str) -> list[dict[str, Any]]:
    """The setups of a view bar group: every setup, the decision models' or the chat models'."""
    return [run for run in data.runs if group == "all" or data.decision(run) == (group == "decision")]


def card_facts(data: Data, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The result cards' facts for a group's setups, from results.json: the setups with the most right answers; the setups
    that kept the most answers at the confidence threshold with none of them wrong, and how many setups kept more but got
    some wrong; and the cheapest setup per 1,000 questions among those with a cost within 1 point of the best accuracy
    (near), else among every setup with a cost."""
    best = max(accuracy(run)[0] for run in runs)
    kept = lambda run: run["confidence"]["sure"]["questions"]  # noqa: E731
    sure = [run for run in runs if (run.get("confidence") or {}).get("sure")]
    flawless = [run for run in sure if kept(run) and kept(run) == run["confidence"]["sure"]["correct"]]
    most = max(map(kept, flawless), default=0)
    # Within 1 point: at most 1 percentage point fewer right answers than the best, in whole answers.
    near = [run for run in runs if 100 * (best - accuracy(run)[0]) <= accuracy(run)[1] and bp.per_thousand(run) is not None]
    pool = near or [run for run in runs if bp.per_thousand(run) is not None]
    return {
        "best": best, "top": [run for run in runs if accuracy(run)[0] == best],
        "most": most, "keepers": [run for run in flawless if kept(run) == most], "more": [run for run in sure if kept(run) > most],
        "near": bool(near), "cheapest": min(pool, key=lambda run: (bp.per_thousand(run), -accuracy(run)[0])) if pool else None,
    }


def result_cards(data: Data, site: Site) -> str:
    """The three result cards above the Accuracy chart, one set per view bar group (data-models; site.js shows the one in
    view): the highest accuracy, the most answers kept at the confidence threshold with no observed mistakes, and the
    lowest cost per 1,000 questions within 1 point of the best accuracy (or, if no such setup has a cost, the lowest
    overall). Each card names its scope. card_checks tests the numbers against results.json."""
    total, sure = data.results["questions"], pct(data.config["threshold"], 0)
    sets = []
    for group, scope in CARD_SCOPES.items():
        runs = group_runs(data, group)
        names = site.names(runs)
        among = scope.format(n=bp.count(len(runs)))
        facts = card_facts(data, runs)

        def setups(chosen: list[dict[str, Any]]) -> str:
            return " and ".join(f'{family_icon(site.families[run["run"]]["name"])}<a href="{site.model_path(run)}">'
                                f'{bp.esc(names[run["run"]])}</a>' for run in chosen)

        def card(title: str, value: str, chosen: str, scope_text: str, tip: str | None = None) -> str:
            tip_attr = f' title="{bp.esc(tip)}"' if tip else ""
            return (f'<section class="panel result-card"><h2 class="card-title">{title}</h2>'
                    f'<p class="card-value"{tip_attr}>{value}</p><p class="card-setup">{chosen}</p>'
                    f'<p class="card-scope">{scope_text}</p></section>')

        best = facts["best"]
        cards = [card("Highest accuracy", f"{100 * best / total:.1f}%", setups(facts["top"]),
                      f"{bp.count(best)} right of {bp.count(total)} questions. Among {among}.")]
        more = len(facts["more"])
        caveat = f" {more} setup{'s' if more != 1 else ''} kept more but got some wrong." if more else ""
        cards.append(card(f"Most answers kept at the {sure} confidence threshold with no observed mistakes",
                          bp.count(facts["most"]), setups(facts["keepers"]),
                          f"{bp.count(facts['most'])} of {bp.count(total)} questions kept, all right. Among {among}.{caveat}")
                     if facts["keepers"] else
                     card(f"Most answers kept at the {sure} confidence threshold with no observed mistakes", "None", "",
                          f"Every setup that kept answers at {sure} got some wrong. Among {among}."))
        cheapest = facts["cheapest"]
        title = cost_unit_in("Lowest cost per 1,000 questions within 1 point of the best accuracy" if facts["near"]
                             else "Lowest cost per 1,000 questions overall")
        if cheapest is None:
            cards.append(card(title, NOT_MEASURED, "", f"No setup has a cost. Among {among}."))
        else:
            upper = data.config["first_cost_marks"]["upper"]["mark"] + " " if cheapest.get("cost_upper_bound") else ""
            at = f"At {100 * accuracy(cheapest)[0] / total:.1f}% accuracy; the best is {100 * best / total:.1f}%."
            why = "" if facts["near"] else " No setup within 1 point of the best accuracy has a cost, so this is the cheapest overall."
            cards.append(card(title, cost_value(bp.per_thousand(cheapest), upper), setups([cheapest]),
                              f"{at}{why} Among {among}.", site.cost_tip(cheapest)))
        hidden = "" if group == "all" else " hidden"
        sets.append(f'<div class="result-cards" data-models="{group}"{hidden}>{"".join(cards)}</div>')
    return "".join(sets)


def card_checks(page: str, data: Data, site: Site) -> list[str]:
    """The result cards (result_cards) against results.json: for each group, its block on the page states the highest
    accuracy and its setup, the most answers kept at the threshold with none wrong and that setup, and the cheapest setup
    near the best accuracy, each computed here anew by sorting the group's setups; the claims that differ."""
    found = []
    total = data.results["questions"]
    for group in CARD_SCOPES:
        runs = group_runs(data, group)
        names = site.names(runs)
        block = re.search(rf'<div class="result-cards" data-models="{group}"[^>]*>(.*?)</div>', page, re.S)
        if block is None:
            found.append(f"Result cards ({group}): index.html has the block")
            continue
        text = summary_text(block.group(1))
        claims = []
        by_right = sorted(runs, key=lambda run: -accuracy(run)[0])
        top = by_right[0]
        claims.append((f"Highest accuracy {100 * accuracy(top)[0] / total:.1f}%, {names[top['run']]}, "
                       f"{bp.count(accuracy(top)[0])} right of {bp.count(total)} questions",
                       [f"{100 * accuracy(top)[0] / total:.1f}%", names[top["run"]], f"right of {bp.count(total)} questions"]))
        clean = sorted((run for run in runs if run["confidence"]["sure"]["questions"]
                        and run["confidence"]["sure"]["correct"] == run["confidence"]["sure"]["questions"]),
                       key=lambda run: -run["confidence"]["sure"]["questions"])
        if clean:
            kept = clean[0]["confidence"]["sure"]["questions"]
            claims.append((f"Most kept with no observed mistakes: {names[clean[0]['run']]}, {kept}",
                           [names[clean[0]["run"]], f"{bp.count(kept)} of {bp.count(total)} questions kept, all right"]))
        best = accuracy(top)[0]
        priced = sorted((run for run in runs if bp.per_thousand(run) is not None), key=bp.per_thousand)
        near = [run for run in priced if (best - accuracy(run)[0]) / total <= 0.01]
        if priced:
            cheapest = (near or priced)[0]
            claims.append((f"Lowest cost per 1,000 questions {'within 1 point of the best' if near else 'overall'}: "
                           f"{names[cheapest['run']]}, ${bp.per_thousand(cheapest):.3f}",
                           [names[cheapest["run"]], f"${bp.per_thousand(cheapest):.3f}",
                            "within 1 point of the best accuracy" if near else "the cheapest overall"]))
        for claim, parts in claims:
            if not all(part in text for part in parts):
                found.append(f"Result cards ({group}): {claim}")
    return found


def version(data: Data) -> str:
    results = data.results
    return (f"Results {bp.esc(results['results_version'])}, updated {bp.long_date(results['updated'])}; "
            f"answer key version {results['answer_key']['version']}.")


def copy_checks(data: Data) -> list[str]:
    """Each number or comparison the fixed copy states, checked against results.json; the claims that differ."""
    results, runs = data.results, data.runs
    decision = [run for run in runs if data.decision(run)]
    # Decider v1.2 is the checkpoint on our hardware; the hosted v1.2 shares its model ID.
    ultra, glide, glide12, d3, d3_ultra, decider, subq, decider12, drex_v1, drex_11, mammoth = (
        data.by_name(*spec) for spec in (("d1-ultra",), ("fastino/GLiDE",), ("glide-v1.2",), ("vllm-sr/d3",),
                                         ("vllm-sr/d3-ultra",), ("pplx-decider-v1.1-27b",), ("subq-snap-preview",),
                                         ("pplx-decider-v1.2", "pplx-decider"), ("drex-max-v1",), ("drex-max-v1.1",),
                                         ("baselabs/mammoth-1",)))
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
    for key in ONE_PER_REQUEST_LLMS:
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
    check("SubQ Snap Preview twelfth among decision models in front of Sonnet (16 per request)", order.index(subq) == 11)
    for size in (16, 1):
        for key, place, word in (("opus", 19, "nineteenth"), ("astra", 17, "seventeenth")):
            frontier = data.named(key, size)["run"]
            ranked = sorted((run for run in decision if (run["run"], frontier) in cascades),
                            key=lambda run: -cascades[(run["run"], frontier)]["held_out"]["answered"])
            check(f"SubQ Snap Preview {word} in front of {key} ({size} per request): place {ranked.index(subq) + 1}",
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
    # replayed): Liquid d1-ultra leads on accuracy and shares a letter with no other decision model; then Decider v1.2
    # (with web), GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied on right answers), Drex Max v1 and 1.1, Mammoth-1, and
    # Deciders v1.1 and v1.2, in that order, at 66.9% to 68.7%;
    # Liquid d1.1 has the smallest calibration gap as
    # shipped; Perplexity Decider 27B v1.2 (API) scores highest on Better than a flat guess, then Open-Jev 27B v1.1, then
    # SubQ Snap 1.1 and Decider v1.1 (equal to one decimal); d1-ultra gives the biggest estimated saving in all 16 LLM
    # setups (every routing LLM at each request size
    # we ran it at).
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
    with_web = data.by_name("pplx-decider-v1.2", "perplexity", "web_grounding")
    check("Summary: then Decider v1.2 (with web), GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied), Drex Max v1 and 1.1, "
          "Mammoth-1, and Deciders v1.1 and v1.2, in that order",
          ranked[1] is with_web and ranked[2] is glide12 and ranked[3] is glide
          and {run["run"] for run in ranked[4:6]} == {d3["run"], d3_ultra["run"]}
          and accuracy(d3) == accuracy(d3_ultra) and ranked[6] is drex_v1 and ranked[7] is drex_11 and ranked[8] is mammoth
          and {run["run"] for run in ranked[9:11]} == {decider["run"], decider12["run"]})
    near = (with_web, glide12, glide, d3, d3_ultra, drex_v1, drex_11, mammoth, decider, decider12)
    check("Summary: at 66.9% to 68.7%",
          min(percent(run) for run in near) == "66.9" and max(percent(run) for run in near) == "68.7")
    calibrated = sorted(decision, key=lambda run: run["confidence"]["ece"])
    check("Summary: calibration gap, as shipped: Liquid d1.1 had the smallest gap among decision models",
          calibrated[0] is data.by_name("d1.1"))
    flat = sorted(decision, key=lambda run: -bp.flat_gain(run))
    check("Summary: better than a flat guess, after refit: Perplexity Decider 27B v1.2 (API) (32.1%), then Open-Jev 27B "
          "v1.1 (31.9%), then SubQ Snap 1.1 and Perplexity Decider 27B v1.1 (31.5% each), the four highest among decision "
          "models",
          flat[0]["run"] == data.by_name("pplx-decider-v1.2", "perplexity", None)["run"] and flat[1] is data.by_name("open-jev-27b-v1.1")
          and {run["run"] for run in flat[2:4]} == {data.by_name("subq-snap-1.1")["run"], data.by_name("pplx-decider-v1.1-27b")["run"]}
          and [f"{bp.flat_gain(run):.1f}" for run in flat[:4]] == ["32.1", "31.9", "31.5", "31.5"])

    def best_share(part: str) -> str:
        return f"{100 * max(run['groups'][part]['correct'] / run['groups'][part]['questions'] for run in decision):.1f}"

    check("Summary: decision models got up to 92.1% of the reading questions right", best_share("reading") == "92.1")
    check("Summary: but at most 70.7% of the grammar questions", best_share("grammar") == "70.7")
    # The cost notes: a setup without a cost runs on our hardware with no request time to estimate it from; every other
    # cost of a setup on our hardware is at its maker's list price for the same model, a public host's for the same
    # weights, or its GPU time at the rate and date the gpu note and tip state; Liquid d1 is estimated at Liquid's list
    # price; no latency for runs made before requests were timed one by one.
    prices = {bp.price_key(price): price for price in results["prices"]}
    check("No list price note: every setup without a cost runs on our hardware, with no request time to estimate it from",
          all(run["billing"] == "local" and run["cost_basis"] is None and not run["request_seconds"]
              for run in runs if run["api_equivalent_usd"] is None))
    bases = {"maker": r"'s list price for the same model( \(.+\))?", "weights": r"'s list price for the same weights \(.+\)",
             "gpu": r".+"}
    check("Cost notes: every cost of a setup on our hardware is at its maker's list price, a host's for the same weights, "
          "or its GPU time",
          all(run["cost_basis"] in bases and prices[bp.price_key(run)]["applies_to"] == run["cost_basis"]
              and re.search(bases[run["cost_basis"]] + "$", prices[bp.price_key(run)]["basis"])
              for run in runs if run["billing"] == "local" and run["api_equivalent_usd"] is not None))
    gpu_prices = [price for price in results["prices"] if price["applies_to"] == "gpu"]
    check("GPU-time note and tip: the rate per GPU-hour and the date read of every GPU-time price",
          all(f"${price['usd_per_gpu_hour']:.2f} per GPU-hour (read {bp.long_date(price['date'])})" in text
              for price in gpu_prices for text in (data.config["first_cost_marks"]["gpu"]["tip"],
                                                   data.config["first_cost_marks"]["gpu"]["note"])))
    d1 = data.by_name("d1:free")
    check("Liquid d1's run used the free tier and is estimated at Liquid's list price for the same model",
          d1["billing"] == "free" and d1["cost_basis"] == "free tier"
          and prices[bp.price_key(d1)]["basis"] == "Liquid's list price for the same model")
    first_timed = min(run["started"] for run in runs if run["median_request_seconds"] is not None)
    check("Not measured note: every run without a latency was made before requests were timed one by one",
          all(run["started"] < first_timed for run in runs if (run.get("latency") or {}).get("median_request_seconds") is None))
    # The biggest estimated saving in front of every routing LLM setup: each LLM at each request size we ran it at.
    winners = []
    for key, _, _, sizes in ROUTE_LLMS:
        for size in sizes:
            frontier = data.named(key, size)
            alone = bp.per_thousand(frontier)
            savings = [(1 - cascades[(run["run"], frontier["run"])]["usd_per_1000"] / alone, run["run"])
                       for run in decision if (run["run"], frontier["run"]) in cascades]
            winners.append(max(savings)[1])
    leader, times = Counter(winners).most_common(1)[0]
    check(f"Summary: d1-ultra gave the biggest estimated saving in all 16 LLM setups ({len(winners)} setups, {times} won by "
          f"{data.by_id[leader]['name']})", len(winners) == 16 and times == 16 and leader == ultra["run"])
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
    home_data(data)
    blocks = {
        "head": head(data, names["preview"]["dark"]),
        # The stylesheet and scripts at versioned addresses (asset), so a page and its scripts always come from one build;
        # the first data file preloads while the page parses (fetch's own mode, so v3.js's fetch takes it).
        "assets": (f'<link rel="stylesheet" href="{asset("v3.css")}">\n'
                   f'  <link rel="preload" href="{asset(HOME)}" as="fetch" crossorigin>\n'
                   f'  <script src="{asset("site.js")}" defer></script>\n'
                   f'  <script src="{asset("v3.js")}" defer></script>'),
        "intro": bp.esc(INTRO.format(**counts(data))),
        "topbar": topbar(""),
        "stats": stats(data),
        "version": version(data),
        "setups": setups(data),
        "topics": topics(data),
        "parts": parts(data),
        "questions": f"{bp.count(data.results['questions'])} questions",
        "board": fallback_table(data, site),
        "settings": page_settings(data),
        "board-note": f'<div class="tab-notes"><p>{bp.esc(" ".join(filter(None, [site.cost_note(data.runs), not_measured_note(data)])))}</p></div>',
        "experiments": experiments(data.results, ""),
        "non-hallucination": non_hallucination(site),
        "cards": result_cards(data, site),
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
    differ = copy_checks(data) + card_checks(text, data, site) + summary
    for claim in differ:
        print(f"copy differs from results.json: {claim}", file=sys.stderr)
    print(f"wrote index.html and {written} other pages; {len(differ)} copy claims differ from results.json")
    return 1 if differ else 0


def write_pages(site: Site) -> int:
    """Every page of PAGE_MODULES, each to <path>index.html, and the plain files they return under a path that does not
    end in "/" (as turkish-vs-english/kept-question-ids.txt); the number of pages written."""
    written = 0
    for name in PAGE_MODULES:
        module = importlib.import_module(f"sitebuild.{name}")
        for path, text in module.build(site).items():
            page = not path or path.endswith("/")
            target = ROOT / path / "index.html" if page else ROOT / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written += page
    return written


if __name__ == "__main__":
    sys.exit(main())
