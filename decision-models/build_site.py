#!/usr/bin/env python3
"""Build the site (this folder, at /analysis/decision-models/) from results.json, answers.json and page_config.json, in
one step:

    python3 build_site.py               # charts, link preview images, CITATION.cff and every page
    python3 build_site.py --no-images   # the same, keeping the Reading pages' current link preview images
    python3 build_site.py --no-images --fast   # the same, reusing reproduce.py's count when its inputs are unchanged

It runs reproduce.py first and stops unless every check matches. reproduce.py takes about five minutes and the rest of
the build seconds, so a passing run stores its count under a hash of everything it reads (build_page.reproduce_key:
reproduce.py, benchmark_metrics.py, results.json, answers.json and every other JSON file beside them, with the Python
version), outside the site; --fast reuses a stored count for the same hash and runs reproduce.py when there is none.
Every other step, every page and every copy check runs either way. It also stops when a provider that serves both
decision and chat models has a run of a model whose type we have not decided (provider_checks), and when chart-renderer's
figures give a run another type than the tables do (type_checks). Then it draws the charts with chart-renderer (cargo),
the link preview image in both themes with headless Chrome (CHROME, else google-chrome) and CITATION.cff, both from
build_page.py, and writes the pages. All benches (sitebuild/all_benches.py) draws its own link preview the same way at
every build, --no-images and --fast too, as its scores come from the benches' files read at each build: Chrome is
needed either way.

The home page, index.html, is the Text tab; vision/ (sitebuild/vision.py) is the Page images tab, dont-know/
(sitebuild/dont_know.py) the Hallucination tab and turkish-vs-english/ (sitebuild/english_reading.py) the Turkish vs
English tab, with a redirect at its earlier address english-reading/. index.html keeps its copy; this script rewrites
what is inside its <!-- build:name --> markers: the meta tags, the
top bar, the hero's line of counts (from results.json), the counters, the results version, the plain table for
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
import statistics
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
from sitebuild import holding_back as hold  # noqa: E402
from sitebuild.site import (GROUPS, NOT_MEASURED, ROUTE_LLMS, SUITE_CSS, Site, asset, cost_missing, cost_per, cost_unit_in,  # noqa: E402
                            cost_value, family_icon, family_legend, footer, hbars, measure_rows, model_families, pct,
                            run_families, shown, topbar)
from sitebuild import about, leaderboard  # noqa: E402
from sitebuild.names import tag_html  # noqa: E402

PAGE = ROOT / "index.html"
# The home page's data, from results.json, which stays the published download: HOME, preloaded, holds what v3.js's
# first draw reads (HOME_KEYS and the runs, each run's confidence cut to the sure counts the Cost table shows); HOME_MORE
# the runs' whole confidence and the cascades, which v3.js loads when the Calibration chart nears the view or the
# Confidence or Routing tab opens. Both are paths inside the site, as asset takes them.
HOME = "data/home.json"
HOME_MORE = "data/home-more.json"
# Each setup's official name and tag by run id (Site.title, Site.tag; sitebuild/names.py), for chart-renderer, which
# draws from results.json, whose setup names stay as recorded.
NAMES = "data/names.json"
HOME_KEYS = ("results_version", "questions", "sure_threshold", "units", "prices", "dont_know", "pipelines", "repeats",
             "replay", "baselines")
# The modules of sitebuild/ that write pages, in build order: questions writes data/picks.json, which the others read.
# The About page comes after them, from the home page's parts (sitebuild/about.py).
PAGE_MODULES: tuple[str, ...] = ("questions", "disagreements", "topics", "models", "compare", "vision", "dont_know",
                                 "english_reading", "english_view", "aa_index", "web_grounding", "pws_decisions", "data",
                                 "method", "highlights", "experiments", "bench_scores", "all_benches")
TITLE = "When should you trust a decision model?"
# The intro (at the top of the About page, moved from the home page) and the meta description; their counts come from
# results.json (counts()).
INTRO = (
    "Our reading comprehension and grammar test: {questions} questions answered by {decision} decision models, with "
    "chat models for comparison. A decision model scores each answer option and picks one. Grammar questions test "
    "whether a model knows a rule and can apply it. Every answer is public."
)
DESCRIPTION = (
    "We tested {decision} decision models on a reading comprehension and grammar test in native Turkish (not "
    "translated): {questions} questions. "
    "No model led on every measure. KnowLine-31B-Gen1.5 got the most answers right, ahead of REAX 1.3 and Liquid's "
    "d1-ultra, which tied. Of the decision "
    "models with no observed mistakes at 99% confidence, Perplexity's Decider v1.2, run on our hardware, kept the most "
    "answers. With every model at 1 question per request, the decision model "
    "with the largest share took 34% to 56% of each LLM's questions, with accuracy at most 0.27 points lower, in a "
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
SUMMARY_ACCURACY = "Accuracy: KnowLine-31B-Gen1.5 clearly ahead at 81.8%; REAX 1.3 and Liquid's d1-ultra, tied at 77.9% and 77.1%; GLiDE 27B at 71.1%; then Decider v1.2 with web search, GLiDE v1.2, hosted GLiDE, d3 and d3-ultra, Drex Max and Drex Max v1.1, Mammoth-1, Decider v1.1 and Decider v1.2 on our DGX Spark, at 66.9% to 68.7%."
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
    number of decimals, as in v3.js; each name is the model's official name with its setup's tag beside it (Site.title,
    Site.tag), its settings in its tooltip; a cost carries no basis mark (its tooltip and the note under the table give
    the basis)."""
    rows: list[str] = []
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
            f'<td class="model">{site.icon(run)}<a class="model-name" href="models/{run["run"]}/" title="{bp.esc(about)}">{bp.esc(site.title(run))}</a>{tag_html(site.tag(run))}</td>'
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


def names_data(site: Site) -> None:
    """Write NAMES (see there): {"runs": {run id: {"name": official name, "tag": tag}}}, the Text tab's runs."""
    content = {"about": "Each setup's official name and the tag beside it, by run id (build_site.py from results.json and "
                        "page_config.json display_names; sitebuild/names.py). results.json keeps the setup names.",
               "runs": {str(run["run"]): {"name": site.title(run), "tag": site.tag(run)} for run in site.runs}}
    (ROOT / NAMES).write_text(json.dumps(content, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {NAMES}")


def charts() -> None:
    """Every chart in both themes, drawn from results.json into charts/ by chart-renderer, which takes the decision
    model lists from page_config.json and each setup's official name and tag from NAMES."""
    out = renderer("results.json", "page_config.json", NAMES, "charts")
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


def site_counts(data: Data, site: Site) -> str:
    """The line of counts under the Leaderboard: questions, models (the Leaderboard's rows), setups and the last update."""
    return (f"{bp.count(data.results['questions'])} questions · {bp.count(leaderboard.model_count(site))} models · "
            f"{bp.count(len(data.runs))} setups · updated {bp.long_date(data.results['updated'])}")


def page_settings(data: Data, site: Site) -> str:
    """What v3.js needs beyond its data files: their versioned addresses, which runs are decision models, each run's
    class, the topics' parts, the routing LLMs."""
    settings = {
        "homeUrl": asset(HOME),
        "moreUrl": asset(HOME_MORE),
        "decisionProviders": data.config["decision_model_providers"],
        "notDecisionModels": data.config["not_decision_models"],
        "readingUnits": data.config["reading_units"],
        "threshold": data.config["threshold"],
        # The charts' colours: each run's model family by run id, and each family's colour (model_families, from
        # maker_colours.json; run_families stops the build unless every run has exactly one family).
        "families": {run: family["name"] for run, family in run_families(data.runs).items()},
        "familyColours": {family["name"]: family["colour"] for family in model_families()},
        # Each run's Class key (Site.model_class; empty for a setup in no class, shown under Class: All only), so the
        # charts and the full ranking follow the Leaderboard's Class keys as its rows do (Ümit #4665).
        "classes": {run["run"]: site.model_class(run) or "" for run in data.runs},
        # A saving whose first model ran on our own hardware: its marker, tooltip and note, by how its cost was counted.
        "firstCostMarks": {key: value for key, value in data.config["first_cost_marks"].items() if key != "about"},
        # The note under the Accuracy table (not_measured_note), also under the plain table, after the ranking's line.
        "notMeasuredNote": not_measured_note(data),
        "ranksNote": RANKS_NOTE,
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


def home_data(data: Data, site: Site) -> None:
    """Write HOME and HOME_MORE (see there) from results.json, compact, each run with its model's official name as its
    name and its tag (Site.title, Site.tag; results.json keeps the setup names). A cascade drops its curve, which v3.js
    never reads."""
    results = data.results

    def first(run: dict[str, Any]) -> dict[str, Any]:
        slim = {key: value for key, value in run.items() if key != "confidence"} | {"name": site.title(run), "tag": site.tag(run)}
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


# What a block's members are called on the home page's Non-hallucination part, one and several.
NON_HALLUCINATION_NOUNS = {"decision": ("decision model", "decision models"), "chat": ("chat model setup", "chat model setups")}


def non_hallucination(site: Site, finding: str) -> str:
    """The home page's Non-hallucination finding (#non-hallucination), in static HTML, once per model group (data-models,
    shown for the Leaderboard's type by site.js; the all group shown without it), each bar with its Class key (data-class,
    which the Leaderboard's Class keys filter): the Hallucination tab's setups of the group (results.json
    dont_know, each row's group), held back two ways side by side (holding_back): (A) by confidence, each setup's Text tab
    run at the threshold, and (B) with the option, the tab's rows in its order, each bar its non-hallucination rate with
    the option in its model family's colour, then in columns of their own its attempt rate (the share of the questions
    answered, as that tab writes them) and its error rate among its answers (wrong over right + wrong). Each side shows
    decision and chat models as separate blocks, never one ranking (both under all); under the decision block the models
    that almost never chose the option (holding_back.rare_note), under the chat block the chat setups whose Turkish run
    with the option is still running (running_setups), with page_config.json's reason. Its heading is the part's finding
    (finding_html); one line with its link to the Hallucination tab closes it."""
    data = site.results["dont_know"]
    # The Turkish runs' option shown by its meaning, as in the Leaderboard (leaderboard.OPTION_SHOWN, Zeki #4606).
    digits, option, total = site.config["percent_digits"], leaderboard.OPTION_SHOWN.get(data["option"], data["option"]), data["questions"]
    run_of = lambda model: site.by_id[model["original_run"]]  # noqa: E731
    for model in data["models"]:
        if model["group"] != ("decision" if site.decision(run_of(model)) else "chat"):
            raise SystemExit(f"results.json dont_know: {model['name']} (run {model['run']}) is not in group {model['group']} on the Text tab")
    tab = '<a href="dont-know/">Hallucination tab</a>'
    runs = running_setups(site)

    def error(model: dict[str, Any]) -> str:
        answered = model["right"] + model["wrong"]
        return pct(model["wrong"] / answered, digits) if answered else NOT_MEASURED

    def option_block(group: str, kind: str, heading: str) -> str:
        models = dont_know_ranked([model for model in data["models"]
                                   if model["group"] == kind and site.in_group(run_of(model), group)])
        rated = [model for model in models if model["non_hallucination"] is not None]
        undefined = [site.plain(run_of(model)) for model in models if model["non_hallucination"] is None]
        running = [site.plain(run) for run in runs if kind == "chat" and not site.decision(run) and site.in_group(run, group)]
        one, many = NON_HALLUCINATION_NOUNS[kind]
        running_note = (f" <span>{bp.esc(site.config['dont_know']['running'].removesuffix('.'))}; still running in Turkish: "
                        f"{bp.esc(', '.join(running))}.</span>") if running else ""
        if not models:
            return (hold.block(heading, f'<p class="note">No {one} has a run with “{bp.esc(option)}” yet.{running_note}</p>')
                    if running else "")
        rows = [{"label": site.title(run_of(model)), "tag": site.tag(run_of(model)), "family": site.families[model["original_run"]]["name"],
                 "href": site.model_path(run_of(model)), "class_key": site.model_class(run_of(model)),
                 "texts": [pct(model["non_hallucination"], digits), pct(model["attempt_rate"], digits), error(model)],
                 "bars": [{"value": model["non_hallucination"], "colour": site.families[model["original_run"]]["colour"]}],
                 "title": f"{site.plain(run_of(model))}: {model['dont_know']:,} “{option}” of "
                          f"{model['dont_know'] + model['wrong']:,} not right; {model['right'] + model['wrong']:,} of {total:,} "
                          f"answered, {model['wrong']:,} of them wrong (run {model['run']})"}
                for model in rated]
        rare = hold.rare_note([(site.plain(run_of(model)), model["dont_know"], model["non_hallucination"]) for model in models],
                              total, data["vs_confidence_share"], option, digits) if kind == "decision" else ""
        return hold.block(heading, (
            f'<p class="hold-kind">Each of the {len(models)} {one if len(models) == 1 else many}\' first run with it.</p>'
            f'{hbars(rows, columns=hold.COLUMNS)}'
            f"{rare}"
            f'<p class="chart-legend">{family_legend([site.families[model["original_run"]] for model in rated])}'
            + (f" <span>No rate (neither a wrong answer nor “{bp.esc(option)}”): {bp.esc(', '.join(undefined))}.</span>"
               if undefined else "")
            + running_note + "</p>"))

    def copy(group: str) -> str:
        members = dont_know_ranked([model for model in data["models"] if site.in_group(run_of(model), group)])
        setups = [(run_of(model), site.plain(run_of(model)), site.model_path(run_of(model))) for model in members]
        confidence = hold.confidence_side(site, setups, group, ", in its Text tab run") if setups else ""
        with_option = hold.side(
            hold.option_title(option),
            f"“{bp.esc(option)}” among the answers that were not right, with it offered as a sixth option on the {total:,} "
            f"questions; beside it the share answered (right + wrong of {total:,}) and the error rate among the answers "
            "(wrong of right + wrong) · higher non-hallucination is better, read with the share answered; a model that "
            "always chose the option would reach 100% with no right answers",
            "".join(option_block(group, kind, heading) for kind, heading in hold.kinds(group)))
        return f'<div {shown(group)}>{hold.pair(confidence, with_option)}</div>'

    return ('<figure class="panel chart-card" id="chart-non-hallucination">' + finding
            + "".join(copy(group) for group in GROUPS)
            + caveat(f"Read non-hallucination with the share answered; the {tab} has the full table. "
                     '<a href="about/#notes-home-non-hallucination">More about this finding</a>') + "</figure>")


# The home page as a story: the hero (the title and one line of counts), the Leaderboard (sitebuild/leaderboard.py) and
# the finding sections, each a heading that states its finding, one chart and one link. Each finding's sentences, the
# intro and "How the scores work" are on the About page (Ümit via Zeki, bus #3521: less text at the top of pages).
RANKS_NOTE = "Ranks show observed scores; small gaps need not be meaningful."


def caveat(text: str) -> str:
    """A part's closing line, already HTML, with its one link."""
    return f'<p class="caveat">{text}</p>'


def share(run: dict[str, Any], part: str | None = None) -> float:
    """A setup's accuracy on all questions, or on one part (reading, grammar)."""
    if part is None:
        correct, total = accuracy(run)
        return correct / total
    return run["groups"][part]["correct"] / run["groups"][part]["questions"]


def how_scores(data: Data) -> str:
    """The How the scores work box (#how-scores): five plain bullets, their numbers from results.json."""
    runs, questions = data.runs, data.results["questions"]
    reading, grammar = (runs[0]["groups"][part]["questions"] for part in ("reading", "grammar"))
    decision = sum(map(data.decision, runs))
    sizes = sorted({run["questions_per_request"] for run in runs})
    bullets = [
        f"<strong>What is scored.</strong> {bp.count(questions)} questions written in Turkish, not translated: "
        f"{bp.count(reading)} reading and {bp.count(grammar)} grammar. Each answer is right or wrong against the answer "
        "key; an invalid answer counts as wrong.",
        "<strong>How models answer.</strong> A decision model scores each answer option and picks one, with a confidence "
        "for it. A chat model gets the question and its options in a prompt and replies with the letter of its answer.",
        f"<strong>What a setup is.</strong> One model with one setting: its reasoning level, how many questions go in one "
        f"request ({' or '.join(str(size) for size in sizes)}), where it ran (a provider's API, a subscription or our "
        f"GPUs) and whether it searched the web. {len(runs)} setups: {decision} decision-model and {len(runs) - decision} "
        "chat-model setups.",
        "<strong>How differences were tested.</strong> Paired tests on the same questions, with Holm's correction for the "
        "number of comparisons. Setups that share a letter in the ranking were not told apart by the paired test.",
        "<strong>What cost means.</strong> An estimate in dollars per 1,000 questions, not a bill: list prices and "
        "recorded token use for API setups; for our GPUs, a list price for the same model or weights, or the GPU time.",
    ]
    return (f'<section class="panel how-scores" id="how-scores" aria-labelledby="how-scores-title">'
            f'<h2 id="how-scores-title">How the scores work</h2><ul>'
            + "".join(f"<li>{bullet}</li>" for bullet in bullets)
            + '</ul><p class="caveat">The rest is on the <a href="method/">Method</a> page.</p></section>')


def findings(data: Data, site: Site) -> dict[str, dict[str, Any]]:
    """Each home part's finding: its neutral heading (the measure's name), the claim that states what the data shows (every
    number computed here), whether the claim holds, and one or two plain sentences. The part shows the claim only while
    it holds (finding_html), and findings_checks checks the page's heading against results.json."""
    runs = data.runs
    decision = [run for run in runs if data.decision(run)]
    chat = [run for run in runs if not data.decision(run)]
    questions = bp.count(data.results["questions"])
    tenths = lambda value: f"{10 * value:.1f}"  # noqa: E731
    out: dict[str, dict[str, Any]] = {}

    best_decision, best_chat = (max(group, key=lambda run: (accuracy(run)[0], -run["run"])) for group in (decision, chat))
    out["accuracy"] = {
        "label": "Accuracy", "holds": share(best_chat) > share(best_decision),
        "claim": (f"The best chat setup gets {tenths(share(best_chat))} in 10 questions right; the best decision model "
                  f"{tenths(share(best_decision))} in 10"),
        "text": (f"{site.plain(best_chat)} answered {pct(share(best_chat))} of the {questions} questions right; "
                 f"{site.plain(best_decision)}, the best decision model, {pct(share(best_decision))}.")}

    idk = data.results["dont_know"]
    rates = {kind: [(model["non_hallucination"], model) for model in idk["models"]
                    if model["group"] == kind and model["non_hallucination"] is not None] for kind in ("decision", "chat")}
    top = {kind: max(rates[kind], key=lambda item: item[0]) for kind in rates}
    name = lambda model: site.plain(site.by_id[model["original_run"]])  # noqa: E731
    shown = leaderboard.OPTION_SHOWN.get(idk["option"], idk["option"])  # by its meaning, as in the Leaderboard (Zeki #4606)
    out["non-hallucination"] = {
        "label": "Non-hallucination", "holds": top["decision"][0] > top["chat"][0],
        "claim": (f"The decision model that chooses “{bp.esc(shown)}” most does so on {round(100 * top['decision'][0])} "
                  f"in 100 of its answers that were not right; the chat model that does so most, on "
                  f"{round(100 * top['chat'][0])}"),
        "text": (f"{name(top['decision'][1])} chose “{shown}” on {pct(top['decision'][0])} of the questions it did "
                 f"not answer right; the top chat model, {name(top['chat'][1])}, on {pct(top['chat'][0])}. Read it with the "
                 "share answered.")}

    costs = {kind: [bp.per_thousand(run) for run in group if bp.per_thousand(run) is not None]
             for kind, group in (("decision", decision), ("chat", chat))}
    median = {kind: statistics.median(values) for kind, values in costs.items()}
    out["cost"] = {
        "label": "Cost", "holds": median["decision"] < median["chat"],
        "claim": (f"The median decision setup costs {cost_value(median['decision'])} {cost_per()}, the median chat setup "
                  f"{cost_value(median['chat'])}"),
        "text": (f"Costs are list prices or GPU-time estimates, as each setup is labelled; medians over the "
                 f"{len(costs['decision'])} decision and {len(costs['chat'])} chat setups with a cost estimate.")}

    single = {kind: [run["latency"]["median_request_seconds"] for run in group if run["questions_per_request"] == 1
                     and (run.get("latency") or {}).get("median_request_seconds") is not None]
              for kind, group in (("decision", decision), ("chat", chat))}
    speed = {kind: statistics.median(values) for kind, values in single.items()}
    out["latency"] = {
        "label": "Latency", "holds": speed["decision"] < speed["chat"],
        "claim": (f"At 1 question per request, the median decision setup answers in {speed['decision']:.2g} s, the median "
                  f"chat setup in {speed['chat']:.2g} s"),
        "text": (f"Median time per request, from our machine, over the {len(single['decision'])} decision and "
                 f"{len(single['chat'])} chat setups that sent 1 question per request.")}

    ahead = sum(share(run, "reading") > share(run, "grammar") for run in runs)
    top_reading = max(decision, key=lambda run: share(run, "reading"))
    top_grammar = max(decision, key=lambda run: share(run, "grammar"))
    reading, grammar = (runs[0]["groups"][part]["questions"] for part in ("reading", "grammar"))
    out["reading-grammar"] = {
        "label": "Reading vs grammar", "holds": 2 * ahead > len(runs),
        "claim": f"{ahead} of {len(runs)} setups score higher on reading than on grammar",
        "text": (f"Among decision models, the best on reading got {pct(share(top_reading, 'reading'))} of the "
                 f"{bp.count(reading)} reading questions right; the best on grammar, "
                 f"{pct(share(top_grammar, 'grammar'))} of the {bp.count(grammar)} grammar questions.")}
    out["calibration"] = calibration(data, site)
    return out


def calibration(data: Data, site: Site) -> dict[str, Any]:
    """The Calibration finding: the decision model with the smallest calibration gap as shipped (results.json runs[].
    confidence.ece, the Calibration chart's value), a claim only while no other decision model has the same gap."""
    decision = sorted((run for run in data.runs if data.decision(run)), key=lambda run: (run["confidence"]["ece"], run["run"]))
    best, second, worst = decision[0], decision[1], decision[-1]
    points = lambda run: f"{100 * run['confidence']['ece']:.1f}"  # noqa: E731
    return {
        "label": "Calibration", "holds": best["confidence"]["ece"] < second["confidence"]["ece"],
        "claim": (f"{bp.esc(site.plain(best))} has the smallest calibration gap of the {len(decision)} decision models, "
                  f"as shipped: {points(best)} points"),
        "text": (f"The gap is how far a model's confidence is from how often it is right. Among decision models, the "
                 f"largest is {site.plain(worst)}'s, {points(worst)} points.")}


# The views a finding heading reads for (Ümit #4665, via Main): the Leaderboard's type (all, decision or chat) with
# Class: All, one class key, or Tiny and Small together (the old small addresses). site.js shows the view's heading as
# the keys change (renderFindings); a view with no claim, or one not built here, shows the measure's name.
VIEW_TYPES = ("all", "decision", "chat")
OTHER_TYPE = {"decision": "chat", "chat": "decision"}


def views(site: Site) -> list[tuple[str, tuple[str, ...]]]:
    keys = [key for key, _ in site.model_classes()]
    return [(kind, chosen) for kind in VIEW_TYPES for chosen in [(), *((key,) for key in keys), ("small", "tiny")]]


def view_key(kind: str, chosen: tuple[str, ...]) -> str:
    """A view as site.js names it: the type, then the class keys in alphabetical order ("decision|small,tiny")."""
    return f"{kind}|{','.join(sorted(chosen))}"


def class_words(site: Site, chosen: tuple[str, ...]) -> str:
    """The classes of a view before a noun, in the keys' order ("Small ", "Tiny or Small "); nothing under Class: All."""
    order = [key for key, _ in site.model_classes()]
    labels = dict(site.model_classes())
    return " or ".join(labels[key] for key in sorted(chosen, key=order.index)) + " " if chosen else ""


# The headings that compare the two types, each as (both: under All with both types in view, the claim of findings();
# one: the sentence about one type; other: the other type's figure as a "not shown here" clause), from the view's
# classes in words (cw) and each type's figure as text. reading-grammar and calibration read for the setups in view
# (variant_headings).
PAIRED = {
    "accuracy": (
        lambda cw, f: f"The best {cw}chat setup gets {f['chat']} in 10 questions right; the best {cw}decision model {f['decision']} in 10",
        lambda cw, kind, x: f"The best {cw}{'decision model' if kind == 'decision' else 'chat setup'} gets {x} in 10 questions right",
        lambda cw, kind, x: f"; the best {cw}{'decision model' if kind == 'decision' else 'chat setup'}, not shown here, {x}"),
    "non-hallucination": (
        lambda cw, f, option: (f"The {cw}decision model that chooses “{option}” most does so on {f['decision']} in 100 of its "
                               f"answers that were not right; the {cw}chat model that does so most, on {f['chat']}"),
        lambda cw, kind, x, option: (f"The {cw}{kind} model that chooses “{option}” most does so on {x} in 100 of its answers "
                                     "that were not right"),
        lambda cw, kind, x, option: f"; the {cw}{kind} model that does so most, not shown here, on {x}"),
    "cost": (
        lambda cw, f: f"The median {cw}decision setup costs {f['decision']} {cost_per()}, the median {cw}chat setup {f['chat']}",
        lambda cw, kind, x: f"The median {cw}{kind} setup costs {x} {cost_per()}",
        lambda cw, kind, x: f"; the median {cw}{kind} setup, not shown here, {x}"),
    "latency": (
        lambda cw, f: (f"At 1 question per request, the median {cw}decision setup answers in {f['decision']} s, the median "
                       f"{cw}chat setup in {f['chat']} s"),
        lambda cw, kind, x: f"At 1 question per request, the median {cw}{kind} setup answers in {x} s",
        lambda cw, kind, x: f"; the median {cw}{kind} setup, not shown here, in {x} s"),
}


def paired(key: str, kind: str, cw: str, figures: dict[str, str | None], holds: bool, *extra: str) -> str | None:
    """A heading comparing the two types, for a view: under All with both types, the claim while it holds (else none);
    under All with one type only in the view's classes, that type's sentence; with one type in view, its sentence and
    the other type's figure for the same classes as a "not shown here" clause (none where the view has no setup)."""
    both, one, other = PAIRED[key]
    present = [name for name in ("decision", "chat") if figures[name] is not None]
    if kind == "all":
        if len(present) == 2:
            return both(cw, figures, *extra) if holds else None
        return one(cw, present[0], figures[present[0]], *extra) if present else None
    if figures[kind] is None:
        return None
    rest = figures[OTHER_TYPE[kind]]
    return one(cw, kind, figures[kind], *extra) + (other(cw, OTHER_TYPE[kind], rest, *extra) if rest is not None else "")


def reading_grammar_heading(cw: str, kind: str, ahead: int, count: int) -> str | None:
    """Reading vs grammar for the setups in view: a claim while more than half of two or more score higher on reading."""
    noun = "setups" if kind == "all" else f"{kind} setups"
    return f"{ahead} of {count} {cw}{noun} score higher on reading than on grammar" if count > 1 and 2 * ahead > count else None


def calibration_heading(cw: str, kind: str, name: str, count: int, points: str, unique: bool) -> str | None:
    """Calibration for the view: the decision models (the chat setups with Chat models in view) of its classes, a claim
    while one has the smallest gap among two or more."""
    noun = "chat setups" if kind == "chat" else "decision models"
    return (f"{bp.esc(name)} has the smallest calibration gap of the {count} {cw}{noun}, as shipped: {points} points"
            if count > 1 and unique else None)


def variant_headings(data: Data, site: Site) -> dict[str, dict[str, str]]:
    """Each finding's heading for every view (views): by view_key, the claim as HTML, or "" for the measure's name. The
    figures are those of findings(), for the setups of the view's classes (Site.model_class; a dont_know row by its
    Text tab run); findings_checks recomputes every one."""
    idk = data.results["dont_know"]
    option = bp.esc(leaderboard.OPTION_SHOWN.get(idk["option"], idk["option"]))
    tenths = lambda value: f"{10 * value:.1f}"  # noqa: E731
    out: dict[str, dict[str, str]] = {key: {} for key in ("accuracy", "non-hallucination", "cost", "latency", "reading-grammar", "calibration")}
    for kind, chosen in views(site):
        cw, view = class_words(site, chosen), view_key(kind, chosen)
        classed = lambda run: not chosen or site.model_class(run) in chosen  # noqa: E731
        runs = {name: [run for run in data.runs if classed(run) and data.decision(run) == (name == "decision")]
                for name in ("decision", "chat")}
        best = {name: max((share(run) for run in group), default=None) for name, group in runs.items()}
        rates = {name: max((model["non_hallucination"] for model in idk["models"] if model["group"] == name
                            and model["non_hallucination"] is not None and classed(site.by_id[model["original_run"]])), default=None)
                 for name in runs}
        costs = {name: [bp.per_thousand(run) for run in group if bp.per_thousand(run) is not None] for name, group in runs.items()}
        cost = {name: statistics.median(values) if values else None for name, values in costs.items()}
        single = {name: [run["latency"]["median_request_seconds"] for run in group if run["questions_per_request"] == 1
                         and (run.get("latency") or {}).get("median_request_seconds") is not None] for name, group in runs.items()}
        speed = {name: statistics.median(values) if values else None for name, values in single.items()}
        text = lambda values, write: {name: None if value is None else write(value) for name, value in values.items()}  # noqa: E731
        heads = {
            "accuracy": paired("accuracy", kind, cw, text(best, tenths),
                               None not in best.values() and best["chat"] > best["decision"]),
            "non-hallucination": paired("non-hallucination", kind, cw, text(rates, lambda value: str(round(100 * value))),
                                        None not in rates.values() and rates["decision"] > rates["chat"], option),
            "cost": paired("cost", kind, cw, text(cost, cost_value), None not in cost.values() and cost["decision"] < cost["chat"]),
            "latency": paired("latency", kind, cw, text(speed, lambda value: f"{value:.2g}"),
                              None not in speed.values() and speed["decision"] < speed["chat"]),
        }
        shown = [run for run in data.runs if classed(run) and site.in_group(run, kind)]
        heads["reading-grammar"] = reading_grammar_heading(
            cw, kind, sum(share(run, "reading") > share(run, "grammar") for run in shown), len(shown))
        gaps = sorted(runs["chat" if kind == "chat" else "decision"], key=lambda run: (run["confidence"]["ece"], run["run"]))
        heads["calibration"] = calibration_heading(
            cw, kind, site.plain(gaps[0]) if gaps else "", len(gaps), f"{100 * gaps[0]['confidence']['ece']:.1f}" if gaps else "",
            len(gaps) > 1 and gaps[0]["confidence"]["ece"] < gaps[1]["confidence"]["ece"])
        for key, heading in heads.items():
            out[key][view] = heading or ""
    return out


def finding_html(item: dict[str, Any], key: str, variants: dict[str, str]) -> str:
    """A part's heading: the finding while its claim holds, under a small label with the measure's name, else the neutral
    heading; with its heading for every view of the Leaderboard's keys (data-variants, variant_headings), which site.js
    shows as they change, the label hidden where a view has no claim. Its sentences go to the About page's notes
    (finding_notes). The claims carry HTML (a cost in both units)."""
    label = f'<p class="finding-label"{"" if item["holds"] else " hidden"}>{bp.esc(item["label"])}</p>'
    return (f'<div class="finding" data-finding="{key}" data-variants="{bp.esc(json.dumps(variants, ensure_ascii=False))}">'
            f'{label}<h2 class="finding-title">{finding_title(item)}</h2></div>')


def finding_title(item: dict[str, Any]) -> str:
    """A finding's heading: its claim while it holds, else the measure's name (HTML)."""
    return item["claim"] if item["holds"] else bp.esc(item["label"])


def finding_notes(site: Site, found: dict[str, dict[str, Any]]) -> None:
    """Each finding's sentences, moved to the About page's notes on the home page under the finding's own heading
    (#notes-home-<key>, linked from the part's last line)."""
    for key in ("accuracy", "non-hallucination", "cost", "latency", "reading-grammar", "calibration"):
        item = found[key]
        site.note("", "Leaderboard", f'<p>{bp.esc(item["text"])}</p>', key, finding_title(item))


def findings_checks(page: str, data: Data, site: Site) -> list[str]:
    """The finding headings as the page shows them, checked against results.json: a part shows its claim only where it
    holds, recomputed here from the runs, and otherwise its neutral heading; then every view's heading (variant_checks)."""
    runs = data.runs
    decision = [run for run in runs if data.decision(run)]
    chat = [run for run in runs if not data.decision(run)]
    rated = [model for model in data.results["dont_know"]["models"] if model["non_hallucination"] is not None]
    priced = lambda group: statistics.median([bp.per_thousand(run) for run in group  # noqa: E731
                                              if bp.per_thousand(run) is not None])
    fast = lambda group: statistics.median([run["latency"]["median_request_seconds"] for run in group  # noqa: E731
                                            if run["questions_per_request"] == 1
                                            and (run.get("latency") or {}).get("median_request_seconds") is not None])
    gaps = sorted(run["confidence"]["ece"] for run in decision)
    holds = {
        "accuracy": max(map(share, chat)) > max(map(share, decision)),
        "non-hallucination": (max(model["non_hallucination"] for model in rated if model["group"] == "decision")
                              > max(model["non_hallucination"] for model in rated if model["group"] == "chat")),
        "cost": priced(decision) < priced(chat),
        "latency": fast(decision) < fast(chat),
        "reading-grammar": 2 * sum(share(run, "reading") > share(run, "grammar") for run in runs) > len(runs),
        "calibration": sum(run["confidence"]["ece"] == gaps[0] for run in decision) == 1,
    }
    found = []
    for key, item in findings(data, site).items():
        title = re.search(rf'<div class="finding" data-finding="{key}"[^>]*>.*?<h2 class="finding-title">(.*?)</h2>', page, re.S)
        expected = item["claim"] if holds[key] else bp.esc(item["label"])
        if not title or title.group(1) != expected:
            found.append(f"finding heading {key}: {title.group(1) if title else 'missing'}")
    # The Calibration heading, worded as this computes it: the one decision model with the smallest gap as shipped,
    # among how many, and its gap in points to one decimal.
    lowest = [run for run in decision if run["confidence"]["ece"] == gaps[0]]
    title = re.search(r'<div class="finding" data-finding="calibration"[^>]*>.*?<h2 class="finding-title">(.*?)</h2>', page, re.S)
    if holds["calibration"] and (not title or title.group(1) != (
            f"{bp.esc(site.plain(lowest[0]))} has the smallest calibration gap of the {len(decision)} decision models, "
            f"as shipped: {100 * gaps[0]:.1f} points")):
        found.append(f"Calibration heading: {site.plain(lowest[0])}, the smallest gap of the {len(decision)} decision "
                     f"models, {100 * gaps[0]:.1f} points")
    return found + variant_checks(page, data, site)


def variant_checks(page: str, data: Data, site: Site) -> list[str]:
    """Every view's heading of every finding as the page carries it (data-variants), against the figures recomputed
    here for the view's type and classes from the runs and the Hallucination tab's rows: the claim, or "" (the
    measure's name) where it does not hold; the view of All models and Class: All is the heading the page shows."""
    idk = data.results["dont_know"]
    option = bp.esc(leaderboard.OPTION_SHOWN.get(idk["option"], idk["option"]))
    found = []
    for key in ("accuracy", "non-hallucination", "cost", "latency", "reading-grammar", "calibration"):
        block = re.search(rf'<div class="finding" data-finding="{key}" data-variants="([^"]*)">.*?<h2 class="finding-title">(.*?)</h2>',
                          page, re.S)
        if not block:
            found.append(f"finding {key}: no heading variants")
            continue
        shown = json.loads(html.unescape(block.group(1)))
        if (shown.get(view_key("all", ())) or bp.esc(findings(data, site)[key]["label"])) != block.group(2):
            found.append(f"finding {key}: the All models · Class: All variant is not the heading shown")
        for kind, chosen in views(site):
            cw = class_words(site, chosen)
            classes = {run["run"]: site.model_class(run) for run in data.runs}
            pool = [run for run in data.runs if not chosen or classes[run["run"]] in chosen]
            kinds = {"decision": [run for run in pool if data.decision(run)], "chat": [run for run in pool if not data.decision(run)]}
            if key == "accuracy":
                top = {name: max((accuracy(run)[0] / accuracy(run)[1] for run in group), default=None) for name, group in kinds.items()}
                figures = {name: None if value is None else f"{10 * value:.1f}" for name, value in top.items()}
                expected = paired(key, kind, cw, figures, None not in top.values() and top["chat"] > top["decision"])
            elif key == "non-hallucination":
                rows = [model for model in idk["models"] if model["non_hallucination"] is not None
                        and (not chosen or classes[model["original_run"]] in chosen)]
                top = {name: max((model["non_hallucination"] for model in rows
                                  if data.decision(site.by_id[model["original_run"]]) == (name == "decision")), default=None)
                       for name in kinds}
                figures = {name: None if value is None else str(round(100 * value)) for name, value in top.items()}
                expected = paired(key, kind, cw, figures, None not in top.values() and top["decision"] > top["chat"], option)
            elif key in ("cost", "latency"):
                value = ((lambda run: bp.per_thousand(run)) if key == "cost" else  # noqa: E731
                         (lambda run: (run.get("latency") or {}).get("median_request_seconds") if run["questions_per_request"] == 1 else None))
                middle = {name: statistics.median(values) if (values := [value(run) for run in group if value(run) is not None]) else None
                          for name, group in kinds.items()}
                figures = {name: None if found_value is None else (cost_value(found_value) if key == "cost" else f"{found_value:.2g}")
                           for name, found_value in middle.items()}
                expected = paired(key, kind, cw, figures, None not in middle.values() and middle["decision"] < middle["chat"])
            elif key == "reading-grammar":
                setups = pool if kind == "all" else kinds[kind]
                ahead = sum(run["groups"]["reading"]["correct"] * run["groups"]["grammar"]["questions"]
                            > run["groups"]["grammar"]["correct"] * run["groups"]["reading"]["questions"] for run in setups)
                expected = reading_grammar_heading(cw, kind, ahead, len(setups))
            else:
                group = kinds["chat" if kind == "chat" else "decision"]
                low = min((run["confidence"]["ece"] for run in group), default=None)
                lowest = sorted((run for run in group if run["confidence"]["ece"] == low), key=lambda run: run["run"])
                expected = calibration_heading(cw, kind, site.plain(lowest[0]) if lowest else "", len(group),
                                               f"{100 * low:.1f}" if lowest else "", len(lowest) == 1)
            if shown.get(view_key(kind, chosen)) != (expected or ""):
                found.append(f"finding {key}, view {view_key(kind, chosen)}: {shown.get(view_key(kind, chosen))!r} "
                             f"(expected {expected!r})")
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
    reax = data.by_name("reax13")
    found = []

    def check(claim: str, holds: bool) -> None:
        if not holds:
            found.append(claim)

    check("Stability: every repeated setup ran 5 times", all(len(item["runs"]) == 5 for item in results["repeats"]))
    best = max(decision, key=lambda run: accuracy(run)[0])
    knowline = data.by_name("PelaAI/KnowLine-31B-Gen1.5")
    check("KnowLine-31B-Gen1.5 got the most answers right (among decision models), ahead of REAX 1.3 and Liquid's "
          "d1-ultra, which tied",
          best is knowline and not any(letter in (run.get("group") or "") for run in (reax, ultra)
                                       for letter in (knowline.get("group") or ""))
          and any(letter in (ultra.get("group") or "") for letter in (reax.get("group") or "")))
    # No observed mistakes needs answers kept: a setup with none kept at 99% is in no such claim (Ümit #4665).
    flawless = [run for run in decision if 0 < run["confidence"]["sure"]["questions"] == run["confidence"]["sure"]["correct"]]
    flawless_kept = sorted((run["confidence"]["sure"]["questions"], run["run"]) for run in flawless)
    check("Of the decision models with no observed mistakes at 99% confidence, Decider v1.2 kept the most answers",
          flawless_kept[-1][1] == decider12["run"] and flawless_kept[-1][0] > flawless_kept[-2][0])
    check("Decider v1.2 ran on our hardware (description: run on our hardware)", decider12["billing"] == "local")
    # In front of each routing LLM at 1 question per request, the decision model with the largest share of its questions,
    # with the cutoff chosen on half the questions (REAX 1.3 in front of all five).
    best_first = []
    for key in ONE_PER_REQUEST_LLMS:
        frontier = data.named(key, 1)["run"]
        best_first.append(max((cascades[(run["run"], frontier)]["held_out"] for run in decision if (run["run"], frontier) in cascades),
                              key=lambda item: item["answered"]))
    check("the decision model with the largest share took 34% to 56% of each LLM's questions",
          (round(100 * min(item["answered"] for item in best_first)), round(100 * max(item["answered"] for item in best_first))) == (34, 56))
    check("accuracy at most 0.27 points lower", round(-100 * min(item["difference"] for item in best_first), 2) == 0.27)
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
    check("SubQ Snap Preview fourteenth among decision models in front of Sonnet (16 per request)", order.index(subq) == 13)
    for size in (16, 1):
        for key, place, word in (("opus", 21, "twenty-first"), ("astra", 19, "nineteenth")):
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
    # replayed): KnowLine-31B-Gen1.5 leads on accuracy, sharing a letter with no other decision model; then REAX 1.3 and
    # d1-ultra, sharing a letter with each other and with no other decision model; then GLiDE 27B; then Decider v1.2 with
    # web search (through its API), GLiDE v1.2, hosted GLiDE, d3 and d3-ultra (tied on right answers), Drex Max and Drex
    # Max v1.1, Mammoth-1, and Decider v1.1 and Decider v1.2 on our DGX Spark, in that order, at 66.9% to 68.7%;
    # d1.1 has the smallest calibration gap as shipped; hosted Perplexity Decider 27B v1.2 scores highest on Better than a
    # flat guess, then Open-Jev-27B-v1.1, then
    # SubQ Snap 1.1 and Decider v1.1 (equal to one decimal); d1-ultra gives the biggest estimated saving in 10 of the 16
    # LLM setups and REAX 1.3 in the other 6 (every routing LLM at each request size we ran it at).
    ranked = sorted(decision, key=lambda run: -accuracy(run)[0])

    def shares(first: dict[str, Any], second: dict[str, Any]) -> bool:
        return any(letter in (second.get("group") or "") for letter in (first.get("group") or ""))

    def percent(run: dict[str, Any]) -> str:
        correct, total = accuracy(run)
        return f"{100 * correct / total:.1f}"

    check("Summary: KnowLine-31B-Gen1.5 has the highest accuracy among decision models, at 81.8%, clearly ahead: it shares "
          "a letter with no other decision model",
          ranked[0] is knowline and percent(knowline) == "81.8"
          and not any(shares(knowline, run) for run in decision if run is not knowline))
    check("Summary: REAX 1.3 and d1-ultra next, tied at 77.9% and 77.1%: they share a letter with each other and "
          "with no other decision model",
          ranked[1] is reax and ranked[2] is ultra and percent(reax) == "77.9" and percent(ultra) == "77.1"
          and shares(reax, ultra)
          and not any(shares(lead, run) for lead in (reax, ultra) for run in decision if run is not reax and run is not ultra))
    with_web = data.by_name("pplx-decider-v1.2", "perplexity", "web_grounding")
    hosted = data.by_name("pplx-decider-v1.2", "perplexity", None)
    glide27 = data.by_name("glide-27b")
    check("Summary: GLiDE 27B at 71.1%", ranked[3] is glide27 and percent(glide27) == "71.1")
    check("Summary: then Decider v1.2 with web search (through its API), GLiDE v1.2, hosted GLiDE, d3 and d3-ultra "
          "(tied on right answers), Drex Max and Drex Max v1.1, Mammoth-1, Decider v1.1 and Decider v1.2 on our DGX Spark, "
          "in that order",
          "DGX Spark" in (decider12.get("hardware") or "") and with_web["billing"] == "api" and decider["billing"] == "api"
          and glide["billing"] == "api"
          and ranked[4] is with_web and ranked[5] is glide12 and ranked[6] is glide
          and {run["run"] for run in ranked[7:9]} == {d3["run"], d3_ultra["run"]}
          and accuracy(d3) == accuracy(d3_ultra) and ranked[9] is drex_v1 and ranked[10] is drex_11 and ranked[11] is mammoth
          and {run["run"] for run in ranked[12:14]} == {decider["run"], decider12["run"]})
    near = (with_web, glide12, glide, d3, d3_ultra, drex_v1, drex_11, mammoth, decider, decider12)
    check("Summary: at 66.9% to 68.7%",
          min(percent(run) for run in near) == "66.9" and max(percent(run) for run in near) == "68.7")
    calibrated = sorted(decision, key=lambda run: run["confidence"]["ece"])
    check("Summary: calibration gap, as shipped: d1.1 had the smallest gap among decision models",
          calibrated[0] is data.by_name("d1.1"))
    flat = sorted(decision, key=lambda run: -bp.flat_gain(run))
    check("Summary: better than a flat guess, after refit: hosted Perplexity Decider 27B v1.2 (32.1%), then "
          "Open-Jev-27B-v1.1 (31.9%), then SubQ Snap 1.1 and Perplexity Decider 27B v1.1 (31.5% each), the four highest "
          "among decision models",
          hosted["billing"] == "api" and
          flat[0] is hosted and flat[1] is data.by_name("open-jev-27b-v1.1")
          and {run["run"] for run in flat[2:4]} == {data.by_name("subq-snap-1.1")["run"], data.by_name("pplx-decider-v1.1-27b")["run"]}
          and [f"{bp.flat_gain(run):.1f}" for run in flat[:4]] == ["32.1", "31.9", "31.5", "31.5"])

    def best_share(part: str) -> str:
        return f"{100 * max(run['groups'][part]['correct'] / run['groups'][part]['questions'] for run in decision):.1f}"

    check("Summary: decision models got up to 92.8% of the reading questions right", best_share("reading") == "92.8")
    check("Summary: but at most 77.1% of the grammar questions", best_share("grammar") == "77.1")
    # The cost notes: a setup without a cost runs on our hardware with no request time to estimate it from, or on a DGX
    # Spark, which has no public hourly price (the GLiDE family's open checkpoints); every other cost of a setup on our
    # hardware is at its maker's list price for the same model, a public host's for the same weights, or its GPU time at
    # the rate and date the gpu note and tip state; Liquid d1 is estimated at Liquid's list price; no latency for runs
    # made before requests were timed one by one.
    prices = {bp.price_key(price): price for price in results["prices"]}
    check("No list price note: every setup without a cost runs on our hardware, with no request time to estimate it from "
          "or on a DGX Spark",
          all(run["billing"] == "local" and run["cost_basis"] is None
              and (not run["request_seconds"] or "DGX Spark" in (run.get("hardware") or ""))
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
    tally = Counter(winners)
    check(f"Summary: d1-ultra gave the biggest estimated saving in 8 of the 16 LLM setups, REAX 1.3 in 6, GLiDE 27B "
          f"in the other 2 ({len(winners)} setups: {dict((data.by_id[run]['name'], times) for run, times in tally.items())})",
          len(winners) == 16 and tally == Counter({ultra["run"]: 8, reax["run"]: 6, data.by_name("glide-27b")["run"]: 2}))
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
    parser.add_argument("--no-images", action="store_true",
                        help="keep the Reading pages' current link preview images (All benches draws its own either way)")
    parser.add_argument("--fast", action="store_true",
                        help="reuse reproduce.py's stored count when everything it reads is unchanged (a page-only change)")
    args = parser.parse_args()
    data, site = Data(), Site(reuse_checks=args.fast)
    provider_checks(data)
    snap = site.snapshot  # runs reproduce.py (--fast: unless stored): the build stops here unless every check matches
    type_checks(data, site, snap)
    names_data(site)
    charts()
    names = images(site, args.no_images)
    bp.CITATION.write_text(bp.citation(snap, site.values), encoding="utf-8")
    print(f"Wrote {bp.CITATION.relative_to(ROOT)}")
    home_data(data, site)
    found = findings(data, site)
    variants = variant_headings(data, site)
    blocks = {
        "head": head(data, names["preview"]["dark"]),
        # The stylesheets and scripts at versioned addresses (asset), so a page and its scripts always come from one build
        # (the suite strip's own stylesheet first); the first data file preloads while the page parses (fetch's own mode,
        # so v3.js's fetch takes it).
        "assets": (f'<link rel="stylesheet" href="{asset(SUITE_CSS)}">\n'
                   f'  <link rel="stylesheet" href="{asset("v3.css")}">\n'
                   f'  <link rel="preload" href="{asset(HOME)}" as="fetch" crossorigin>\n'
                   f'  <script src="{asset("site.js")}" defer></script>\n'
                   f'  <script src="{asset("v3.js")}" defer></script>'),
        "counts": site_counts(data, site),
        "topbar": topbar(""),
        "version": version(data),
        "questions": f"{bp.count(data.results['questions'])} questions",
        "board": fallback_table(data, site),
        "settings": page_settings(data, site),
        "leaderboard": leaderboard.leaderboard(site),
        # The Measure views on this page (site.measure_rows): each part's Measure keys under the finding.
        "non-hallucination": non_hallucination(site, finding_html(found["non-hallucination"], "non-hallucination",
                                                                  variants["non-hallucination"])
                                               + measure_rows("", ("", "non-hallucination"))),
        "footer": footer("", version(data)),
        **{f"finding-{key}": finding_html(found[key], key, variants[key])
                             + (measure_rows("", ("", key)) if key in ("cost", "latency", "calibration") else "")
           for key in ("accuracy", "cost", "latency", "reading-grammar", "calibration")},
    }
    text = PAGE.read_text()
    seen = set()

    def fill(match: Any) -> str:
        seen.add(match.group(2))
        return match.group(1) + blocks[match.group(2)] + match.group(4)

    text = site.in_prose(bp.BLOCK.sub(fill, text))
    if seen != set(blocks):
        raise ValueError(f"index.html lacks the markers {sorted(set(blocks) - seen)}")
    PAGE.write_text(text)
    written = write_pages(site)
    # The About page, from the home page's parts: the intro, How the scores work, the counters and the notes behind the
    # full ranking moved there, with the summary and the notes on each page; its summary is checked there.
    finding_notes(site, found)
    notes = (f"<p>{bp.esc(RANKS_NOTE)}</p><p>"
             f'{bp.esc(" ".join(filter(None, [site.cost_note(data.runs), not_measured_note(data)])))}</p>')
    about_page = site.in_prose(about.page(site, INTRO.format(**counts(data)), how_scores(data), notes, stats(data)))
    (ROOT / about.PATH).mkdir(exist_ok=True)
    (ROOT / about.PATH / "index.html").write_text(about_page)
    written += 1
    summary, words = summary_checks(about_page)
    print(f"Summary block: {words} words (at most {SUMMARY_WORDS})")
    differ = copy_checks(data) + findings_checks(text, data, site) + summary
    for claim in differ:
        print(f"copy differs from results.json: {claim}", file=sys.stderr)
    print(f"wrote index.html and {written} other pages; {len(differ)} copy claims differ from results.json")
    return 1 if differ else 0


# Pages whose fixed text names models by another's own label, kept as written: Artificial Analysis's names on its index's
# page. The Method page's names table (#names) lists the setup names as recorded, by design.
PROSE_KEPT = ("aa-decision-index/",)


def write_pages(site: Site) -> int:
    """Every page of PAGE_MODULES, each to <path>index.html, and the plain files they return under a path that does not
    end in "/" (as turkish-vs-english/kept-question-ids.txt); the number of pages written. A page's text written with
    the setups' recorded names (notes, fixed copy, results' own lists) reads them through Site.in_prose, the Method
    page's names table and PROSE_KEPT left as they are."""
    written = 0
    for name in PAGE_MODULES:
        module = importlib.import_module(f"sitebuild.{name}")
        for path, text in module.build(site).items():
            page = not path or path.endswith("/")
            if page and path not in PROSE_KEPT:
                kept = re.search(r'<h3 id="names">.*?</table>', text, re.S)
                text = (site.in_prose(text[:kept.start()]) + kept.group(0) + site.in_prose(text[kept.end():])
                        if kept else site.in_prose(text))
            target = ROOT / path / "index.html" if page else ROOT / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written += page
    return written


if __name__ == "__main__":
    sys.exit(main())
