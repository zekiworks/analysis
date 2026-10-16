#!/usr/bin/env python3
"""Build the v3 redesign preview (v3/, at /analysis/decision-models/v3/) from its own copy of the results,
v3/results.json and v3/answers.json (until the switch), with page_config.json. It writes only inside v3/; the live
pages and their files stay as they are.

    cargo run --release --manifest-path chart-renderer/Cargo.toml -- v3/results.json /tmp/v3-charts
    cp /tmp/v3-charts/{coverage,calibration-all,sources,paired}{,-dark}.svg v3/charts/
    python3 v3/build_v3.py

The first two commands draw the four charts the Method page shows from the preview's results. The build needs Chrome
(CHROME, else google-chrome), as build_page.py does: it draws the link preview image from the preview's results into
v3/share/ and removes earlier ones there.

The preview copies the live site's build (build_v2.py and v2build/) and scripts, adapted to the redesign. Every page is
kept out of search engines, and no live page links to it. The home page, v3/index.html, keeps its copy; this script
rewrites what is inside its <!-- build:name --> markers: the meta tags, the top bar, the intro (its counts from
results.json), the counters, the results version, the plain table for readers without JavaScript (every setup) and the
note under it, the settings v3.js reads, the default setup count, the charts' "Show all" label, the topic list and the
questions in view. v3.js draws everything else in the browser from v3/results.json. Every other page is generated
whole by a module of v3/v3build/ (PAGE_MODULES) and written to v3/<path>index.html; the Method page runs reproduce.py
on the preview's results for its count of checks.

The home page's fixed copy (the summary lines, the note under the Accuracy table, the notes under the tabs, the meta
description) quotes numbers and comparisons; copy_checks() tests each against results.json and prints every one that
differs. The pages are still written, so they can be reviewed, and the script exits with status 1.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
V3 = Path(__file__).resolve().parent
ROOT = V3.parent
# v3build from this folder; build_page.py and benchmark_metrics.py from the site's folder, read only.
sys.path[:0] = [str(V3), str(ROOT)]
import benchmark_metrics as bm  # noqa: E402
import build_page as bp  # noqa: E402
from v3build.site import NOT_MEASURED, Site, topbar  # noqa: E402

PAGE = V3 / "index.html"
# The modules of v3build/ that write pages, in build order: questions writes data/picks.json, which the others read.
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
    "No model led on every measure. Liquid's d1-ultra got the most answers right; Perplexity's Decider v1.1 kept the "
    "most answers at 99% confidence with no mistakes. With every model at 1 question per request, the decision model "
    "with the largest share took 33% to 46% of each LLM's questions, with accuracy at most 0.32 points lower, in a "
    "replay of recorded answers."
)
# The note under the Accuracy table, with and without JavaScript; copy_checks tests both reasons against the run records.
NOT_MEASURED_NOTE = (
    "Not measured: cost for setups on our own hardware (no API price) and Liquid d1's free tier (no published price); "
    "latency for runs made before we timed each request."
)
# The LLMs the Routing tab puts behind a decision model, in its order, with the label of its control.
ROUTE_LLMS = (("opus", "Opus"), ("sonnet_high", "Sonnet"), ("astra", "Astra"), ("sol", "Sol"), ("gemini_low", "Gemini Flash"))
# Decision models in the charts by default, next to the routing LLMs at one question per request.
CHART_DECISION_MODELS = 8


class Data:
    """The preview's results.json and page_config.json, with the run lookups the page needs."""

    def __init__(self) -> None:
        self.results = json.loads((V3 / "results.json").read_text())
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
    return " · ".join(parts)


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
            f'<td class="num">{f"{latency:.3f}" if latency is not None else NOT_MEASURED}</td>'
            f'<td class="num">{f"{cost:.3f}" if cost is not None else NOT_MEASURED}</td>'
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


def share_images(site: Site) -> dict[str, dict[str, str]]:
    """The link preview image in both themes, drawn from the preview's results into v3/share/ by build_page.py; earlier
    images there are removed. Its names by image and theme, relative to v3/."""
    names = bp.render_images(site.snapshot, V3)
    current = {V3 / name for themes in names.values() for name in themes.values()}
    for old in (V3 / "share").glob("*.png"):
        if old not in current:
            old.unlink()
            print(f"Removed {old.relative_to(ROOT)}")
    return names


def head(data: Data, image: str) -> str:
    """The title, the description and the link preview of the page this preview would replace, with the preview's own
    image (its path inside v3/); kept out of search engines."""
    site = data.config["site_url"]
    image_url = site + "v3/" + image
    size = data.config["images"]["preview"]
    title = f"{TITLE} · Zeki Works"
    text = bp.esc(DESCRIPTION.format(**counts(data)))
    return (
        f"\n  <title>{bp.esc(title)}</title>\n"
        '  <meta name="robots" content="noindex">\n'
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
        # A saving whose first model has no price: its marker, tooltip and note, by billing.
        "unpricedFirst": {key: value for key, value in data.config["unpriced_first"].items() if key != "about"},
        # The note under the Accuracy table (NOT_MEASURED_NOTE), also under the plain table.
        "notMeasuredNote": NOT_MEASURED_NOTE,
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
    ultra, glide, decider, subq = (data.by_name(model) for model in
                                   ("d1-ultra", "fastino/GLiDE", "pplx-decider-v1.1-27b", "subq-snap-preview"))
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
    check("Decider v1.1 kept the most answers at 99% confidence with no mistakes",
          max(flawless, key=lambda run: run["confidence"]["sure"]["questions"]) is decider)
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
        check("Decider kept 51%", round(100 * test["routed"] / test["held_out"]) == 51)
        # The cutoff is the one the same live test chose on 16-per-request answers.
        sixteen = [item["threshold"] for item in results["pipelines"] if item["decision"] == decider["run"]
                   and item["frontier"] == sonnet16["run"] and item["batch_size"] == 16 and item["rule"] == "half"]
        check("with a cutoff chosen at 16 per request", sixteen == [test["threshold"]])
    one = cascades[(decider["run"], sonnet1["run"])]["held_out"]
    check("A cutoff chosen at 1 per request keeps 29%", round(100 * one["answered"]) == 29)
    check("and accuracy falls 0.16 points (replay)", round(-100 * one["difference"], 2) == 0.16)
    order = sorted((run for run in decision if (run["run"], sonnet16["run"]) in cascades),
                   key=lambda run: -cascades[(run["run"], sonnet16["run"])]["held_out"]["answered"])
    check("SubQ Snap third among decision models in front of Sonnet (16 per request)", order.index(subq) == 2)
    for size in (16, 1):
        for key, place, word in (("opus", 7, "seventh"), ("astra", 6, "sixth")):
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
    # replayed): Liquid d1-ultra leads on accuracy and shares a letter with no other decision model, GLiDE second; Luna
    # through the Decisions API has the smallest calibration gap; d1-ultra gives the biggest estimated saving in all 10
    # LLM setups.
    ranked = sorted(decision, key=lambda run: -accuracy(run)[0])
    luna = next(run for run in decision if run["model"] == "gpt-6-luna")

    def shares(first: dict[str, Any], second: dict[str, Any]) -> bool:
        return any(letter in (second.get("group") or "") for letter in (first.get("group") or ""))

    def percent(run: dict[str, Any]) -> str:
        correct, total = accuracy(run)
        return f"{100 * correct / total:.1f}"

    check("Summary: Liquid d1-ultra has the highest accuracy among decision models, at 77.1%",
          ranked[0] is ultra and percent(ultra) == "77.1")
    check("Summary: d1-ultra is clearly ahead: it shares a letter with no other decision model",
          not any(shares(ultra, run) for run in decision if run is not ultra))
    check("Summary: GLiDE second at 67.9%", ranked[1] is glide and percent(glide) == "67.9")
    calibrated = sorted(decision, key=lambda run: run["confidence"]["ece"])
    check("Summary: Luna (Decisions API) had the smallest calibration gap among decision models", calibrated[0] is luna)
    check("Summary: Jev 1.14 close behind (the second smallest gap, at most 0.5 points more)",
          calibrated[1] is data.by_name("jev-1.14.0")
          and calibrated[1]["confidence"]["ece"] - calibrated[0]["confidence"]["ece"] <= 0.005)

    def best_share(part: str) -> str:
        return f"{100 * max(run['groups'][part]['correct'] / run['groups'][part]['questions'] for run in decision):.1f}"

    check("Summary: decision models got up to 92.1% of the reading questions right", best_share("reading") == "92.1")
    check("Summary: but at most 70.7% of the grammar questions", best_share("grammar") == "70.7")
    # The note under the Accuracy table: no cost for setups on our hardware and for Liquid d1's free tier; no latency for
    # runs made before requests were timed one by one.
    check("Not measured note: every setup without a cost ran on our hardware or on Liquid d1's free tier",
          any(run["model"] == "d1:free" and run["billing"] == "free" for run in runs)
          and all(run["billing"] == "local" or (run["billing"] == "free" and run["model"] == "d1:free")
                  for run in runs if run["api_equivalent_usd"] is None))
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


def main() -> int:
    data, site = Data(), Site()
    blocks = {
        "head": head(data, share_images(site)["preview"]["dark"]),
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
        "board-note": f'<div class="tab-notes"><p>{bp.esc(NOT_MEASURED_NOTE)}</p></div>',
    }
    text = PAGE.read_text()
    seen = set()

    def fill(match: Any) -> str:
        seen.add(match.group(2))
        return match.group(1) + blocks[match.group(2)] + match.group(4)

    text = bp.BLOCK.sub(fill, text)
    if seen != set(blocks):
        raise ValueError(f"v3/index.html lacks the markers {sorted(set(blocks) - seen)}")
    PAGE.write_text(text)
    written = write_pages(site)
    differ = copy_checks(data)
    for claim in differ:
        print(f"copy differs from results.json: {claim}", file=sys.stderr)
    print(f"wrote v3/{PAGE.relative_to(V3)} and {written} other pages; {len(differ)} copy claims differ from results.json")
    return 1 if differ else 0


def write_pages(site: Site) -> int:
    """Every page of PAGE_MODULES, each to v3/<path>index.html; the number of pages written."""
    written = 0
    for name in PAGE_MODULES:
        module = importlib.import_module(f"v3build.{name}")
        for path, text in module.build(site).items():
            target = V3 / path / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written += 1
    return written


if __name__ == "__main__":
    sys.exit(main())
