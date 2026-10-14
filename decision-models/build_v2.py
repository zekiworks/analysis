#!/usr/bin/env python3
"""Build the site from results.json and answers.json, with page_config.json: the home page and every page under it,
in this folder, which GitHub Pages serves at /analysis/decision-models/.

    python3 build_v2.py

The home page, index.html, keeps its copy; this script rewrites what is inside its <!-- build:name --> markers:
the meta tags, the stats row, the leaderboard as a plain table for readers without JavaScript, the settings
v2.js reads, and the results version in the footer. v2.js draws everything else there in the browser from
results.json. The link preview is build_page.py's current preview image (share/images.json).

Every other page is generated whole by a module of v2build/ (PAGE_MODULES): build(site) returns {path: html}, and
each page is written to <path>index.html. The Method page runs reproduce.py for its count of checks.

The home page's fixed copy (the intro, the notes under the tabs, the meta description) quotes numbers from the brief.
copy_checks() compares each with results.json and prints every one that differs; the pages are still written, so
they can be reviewed, and the script exits with status 1.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import benchmark_metrics as bm  # noqa: E402
import build_page as bp  # noqa: E402
from v2build.site import Site  # noqa: E402

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"
# The modules of v2build/ that write pages, in build order: questions writes data/picks.json, which the others read.
PAGE_MODULES: tuple[str, ...] = ("questions", "disagreements", "topics", "models", "compare", "data", "method")
TITLE = "When should you trust an AI model to make a decision?"
DESCRIPTION = (
    "We tested 18 decision models on a reading and grammar test in native Turkish (not translated): 2,198 questions. "
    "No model led on every measure. Fastino's GLiDE got the most answers right; Perplexity's Decider v1.1 kept the "
    "most answers at 99% confidence with no mistakes. With every model at 1 question per request, the decision model "
    "with the largest share took 20% to 29% of each LLM's questions, with accuracy at most 0.18 points lower, in a "
    "replay of recorded answers."
)
# The LLMs the Routing tab puts behind a decision model, in its order, with the label of its control.
ROUTE_LLMS = (("opus", "Opus"), ("sonnet_high", "Sonnet"), ("astra", "Astra"), ("sol", "Sol"), ("gemini_low", "Gemini Flash"))
# Decision models in the charts by default, next to the routing LLMs at one question per request.
CHART_DECISION_MODELS = 8


class Data:
    """results.json and page_config.json, with the run lookups the page needs."""

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


def pct(fraction: float, digits: int = 1) -> str:
    return f"{100 * fraction:.{digits}f}%"


def latency_text(run: dict[str, Any]) -> str | None:
    latency = run.get("latency")
    if not latency:
        return None
    value = latency["median_request_seconds"]
    return f"{1000 * value:.0f}\u00a0ms" if value < 1 else f"{value:.{2 if value < 10 else 1}f}\u00a0s"


NOT_MEASURED = '<span class="hint" tabindex="0" data-tip="Not measured">—</span>'


def fallback_table(data: Data) -> str:
    """The Accuracy tab on all questions, every setup, as a plain table: what readers without JavaScript see."""
    rows = []
    for run in sorted(data.runs, key=lambda run: -accuracy(run)[0]):
        correct, total = accuracy(run)
        low, high = bm.wilson_interval(correct, total)
        reading, grammar = run["groups"]["reading"], run["groups"]["grammar"]
        latency = latency_text(run)
        cost = bp.per_thousand(run)
        kind = "Decision model" if data.decision(run) else "Chat model"
        rows.append(
            "<tr>"
            f'<td class="model"><a class="model-name" href="models/{run["run"]}/">{bp.esc(run["name"])}</a><span class="small">{bp.esc(detail(run))} · {kind}</span></td>'
            f'<td class="num" data-label="Accuracy">{pct(correct / total)}<span class="small">{pct(low)} to {pct(high)}</span></td>'
            f'<td class="num" data-label="Reading">{pct(reading["correct"] / reading["questions"])}</td>'
            f'<td class="num" data-label="Grammar">{pct(grammar["correct"] / grammar["questions"])}</td>'
            f'<td class="num" data-label="Latency">{latency or NOT_MEASURED}</td>'
            f'<td class="num" data-label="$ per 1,000">{bp.usd(cost) if cost is not None else NOT_MEASURED}</td>'
            "</tr>"
        )
    return (
        '<table class="board list"><caption>Accuracy on all '
        f'{bp.count(data.results["questions"])} questions, with its 95% interval</caption>'
        '<thead><tr><th scope="col">Model</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Reading</th>'
        '<th scope="col" class="num">Grammar</th><th scope="col" class="num">Latency</th><th scope="col" class="num">$ per 1,000</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def head(data: Data) -> str:
    site = data.config["site_url"]
    image_url = site + bp.current_images()["preview"]["dark"]
    title = f"{TITLE} · Zeki Works"
    text = bp.esc(DESCRIPTION)
    return (
        f"\n  <title>{bp.esc(title)}</title>\n"
        f'  <link rel="canonical" href="{site}">\n'
        f'  <meta name="description" content="{text}">\n'
        f'  <meta property="og:title" content="{bp.esc(title)}">\n'
        f'  <meta property="og:description" content="{text}">\n'
        '  <meta property="og:type" content="website">\n'
        f'  <meta property="og:url" content="{site}">\n'
        f'  <meta property="og:image" content="{image_url}">\n'
        '  <meta name="twitter:card" content="summary_large_image">\n'
        f'  <meta name="twitter:title" content="{bp.esc(title)}">\n'
        f'  <meta name="twitter:description" content="{text}">\n'
        f'  <meta name="twitter:image" content="{image_url}">\n  '
    )


def stats(data: Data) -> str:
    items = (
        (data.results["questions"], "questions"),
        (len(data.results["units"]), "topics"),
        (sum(map(data.decision, data.runs)), "decision models"),
        (len(data.runs), "setups"),
    )
    return "".join(f"<li><strong>{bp.count(value)}</strong> {label}</li>" for value, label in items)


def page_settings(data: Data) -> str:
    """What v2.js needs beyond results.json: which runs are decision models, the topics' parts, the routing LLMs."""
    settings = {
        "decisionProviders": data.config["decision_model_providers"],
        "notDecisionModels": data.config["not_decision_models"],
        "readingUnits": data.config["reading_units"],
        "threshold": data.config["threshold"],
        "shortNames": data.config["short_names"],
        # A chart label for a setup whose model ID another setup shares, by provider then model.
        "chartLabels": data.config["chart_labels"],
        "chartDecisionModels": CHART_DECISION_MODELS,
        "routeLlms": [
            {"key": key, "label": label, "runs": {str(size): data.named(key, size)["run"] for size in (1, 16)}}
            for key, label in ROUTE_LLMS
        ],
    }
    return f'<script type="application/json" id="v2-settings">{json.dumps(settings, separators=(",", ":"))}</script>'


def version(data: Data) -> str:
    results = data.results
    return (f"Results {bp.esc(results['results_version'])}, updated {bp.long_date(results['updated'])}; "
            f"answer key version {results['answer_key']['version']}.")


def copy_checks(data: Data) -> list[str]:
    """Each number or comparison the fixed copy states, checked against results.json; the claims that differ."""
    results, runs = data.results, data.runs
    decision = [run for run in runs if data.decision(run)]
    glide, decider, subq = (data.by_name(model) for model in ("fastino/GLiDE", "pplx-decider-v1.1-27b", "subq-snap-preview"))
    cascades = {(item["decision"], item["frontier"]): item for item in results["cascades"]}
    sonnet16, sonnet1 = data.named("sonnet_high", 16), data.named("sonnet_high", 1)
    found = []

    def check(claim: str, holds: bool) -> None:
        if not holds:
            found.append(claim)

    check("2,198 questions", results["questions"] == 2198)
    check("20 topics", len(results["units"]) == 20)
    check("18 decision models", len(decision) == 18)
    check("43 setups", len(runs) == 43)
    check("Stability: every repeated setup ran 5 times", all(len(item["runs"]) == 5 for item in results["repeats"]))
    best = max(decision, key=lambda run: accuracy(run)[0])
    check("GLiDE got the most answers right (among decision models)", best is glide)
    flawless = [run for run in decision if run["confidence"]["sure"]["questions"] == run["confidence"]["sure"]["correct"]]
    check("Decider v1.1 kept the most answers at 99% confidence with no mistakes",
          max(flawless, key=lambda run: run["confidence"]["sure"]["questions"]) is decider)
    # In front of each routing LLM at 1 question per request, the decision model with the largest share of its questions,
    # with the cutoff chosen on half the questions (GLiDE in front of four, Decider v1.1 in front of Sonnet).
    best_first = []
    for key, _ in ROUTE_LLMS:
        frontier = data.named(key, 1)["run"]
        best_first.append(max((cascades[(run["run"], frontier)]["held_out"] for run in decision if (run["run"], frontier) in cascades),
                              key=lambda item: item["answered"]))
    check("the decision model with the largest share took 20% to 29% of each LLM's questions",
          (round(100 * min(item["answered"] for item in best_first)), round(100 * max(item["answered"] for item in best_first))) == (20, 29))
    check("accuracy at most 0.18 points lower", round(-100 * min(item["difference"] for item in best_first), 2) == 0.18)
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
    check("SubQ Snap second among decision models in front of Sonnet (16 per request)", order.index(subq) == 1)
    for size in (16, 1):
        for key in ("opus", "astra"):
            frontier = data.named(key, size)["run"]
            ranked = sorted((run for run in decision if (run["run"], frontier) in cascades),
                            key=lambda run: -cascades[(run["run"], frontier)]["held_out"]["answered"])
            check(f"SubQ Snap about fifth in front of {key} ({size} per request): place {ranked.index(subq) + 1}",
                  4 <= ranked.index(subq) + 1 <= 6)
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
    return found


def main() -> int:
    data = Data()
    blocks = {
        "head": head(data),
        "stats": stats(data),
        "board": fallback_table(data),
        "settings": page_settings(data),
        "version": version(data),
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
    written = write_pages()
    differ = copy_checks(data)
    for claim in differ:
        print(f"copy differs from results.json: {claim}", file=sys.stderr)
    print(f"wrote {PAGE.relative_to(ROOT)} and {written} other pages; {len(differ)} copy claims differ from results.json")
    return 1 if differ else 0


def write_pages() -> int:
    """Every page of PAGE_MODULES, each to <path>index.html; the number of pages written."""
    site = Site()
    written = 0
    for name in PAGE_MODULES:
        module = importlib.import_module(f"v2build.{name}")
        for path, text in module.build(site).items():
            target = ROOT / path / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written += 1
    return written


if __name__ == "__main__":
    sys.exit(main())
