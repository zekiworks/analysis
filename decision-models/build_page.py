#!/usr/bin/env python3
"""Fill the page's generated parts from one data snapshot: results.json, with page_config.json.

    python3 build_page.py               # the page, the sharing images and the X posts
    python3 build_page.py --no-images   # without the images (no Chrome needed)

Every number in the overview, in the sharing images and in the X posts comes from the snapshot, and so do the
numbers in the study's sentences that carry a marker. index.html keeps the copy; this script rewrites what is
inside its markers, and the size of the chart images:

- <span data-value="key">…</span>: a number or a short text from values();
- <!-- build:name --> … <!-- /build:name -->: a block from blocks() (tables, bars, sentences, meta tags);
- <img src="charts/….svg">: the width and height of the chart's SVG, so its space is kept while it loads.

"lead" in page_config.json names the finding the page leads with (one of "leads"): it opens the page, comes
first in the confidence figure, and is what the link preview, the X image and the main X post show. The images
are drawn by headless Chrome from HTML made here, from the same rows as the page, and saved under share/ with
a short hash of their content in their names, so that a changed image gets a new address and no link preview shows
a cached copy; share/x-posts.md holds the announcement text. Earlier images are deleted until "announced" holds the
date of the first public post, and kept after it, so that earlier link previews keep working. With --no-images the
page keeps the images it links to. reproduce.py must pass first, and the build stops otherwise. Set CHROME to use
another Chrome or Chromium binary.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import benchmark_metrics as bm  # noqa: E402

# The page and its data sit next to this script: the folder is the site GitHub Pages serves.
ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"
SHARE = ROOT / "share"
X_POSTS = SHARE / "x-posts.md"
VALUE = re.compile(r'(<span data-value="([a-z0-9_]+)">)(.*?)(</span>)', re.S)
BLOCK = re.compile(r"(<!-- build:([a-z0-9-]+) -->)(.*?)(<!-- /build:\2 -->)", re.S)
# A chart image, with the size the build gives it, and an SVG's size.
CHART_IMAGE = re.compile(r'(<img src="(charts/[a-z0-9-]+\.svg)")(?: width="\d+" height="\d+")?')
SVG_SIZE = re.compile(r'<svg\b[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)"')
CHECKS = re.compile(r"^(\d+) checks match, (\d+) differ$", re.M)
# The X counts every link as this many characters.
X_LINK_LENGTH = 23
X_POST_LIMIT = 280
# The level below which an exact McNemar test counts as detecting a difference, as in the report and reproduce.py.
ALPHA = 0.05

esc = html.escape


# ---------------------------------------------------------------- formatting


class Format:
    def __init__(self, digits: int) -> None:
        self.digits = digits

    def pct(self, fraction: float, digits: int | None = None) -> str:
        return f"{100 * fraction:.{self.digits if digits is None else digits}f}%"

    def span(self, low: float, high: float) -> str:
        """A 95% interval as text: '0.3% to 1.9%'; a bound that rounds to zero (a Wilson bound is stored as 1e-16) reads 0%."""
        return " to ".join("0%" if round(100 * value, self.digits) == 0 else f"{100 * value:.{self.digits}f}%" for value in (low, high))

    def share(self, part: int, total: int) -> str:
        """part as a percentage of total; a nonzero part that would round to zero shows as below the last digit."""
        smallest = 10 ** -self.digits
        if part and 100 * part / total < smallest / 2:
            return f"<{smallest:.{self.digits}f}%"
        return self.pct(part / total)


def count(value: int) -> str:
    return f"{value:,}"


NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
# A count that opens a sentence is spelled out further.
OPENING_WORDS = {**NUMBER_WORDS, 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
                 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty"}


def in_words(value: int) -> str:
    """A count below ten in words, a larger one in figures."""
    return NUMBER_WORDS.get(value, count(value))


def opening_count(value: int) -> str:
    """A count at the start of a sentence: in words up to twenty."""
    return OPENING_WORDS.get(value, count(value)).capitalize()


def usd(value: float) -> str:
    """Dollars: cents from $0.10 up and three decimals below, so that $0.0078 does not read as $0.01."""
    if value >= 0.1 or value == 0:
        return f"${value:.2f}"
    text = f"{value:.3f}"
    return f"${text}" if text != "0.000" else f"${value:.2g}"


def times(ratio: float) -> str:
    """A ratio to two significant figures, for 'roughly N times': 689.7 becomes 690."""
    return f"{float(f'{ratio:.2g}'):,.0f}"


def points(fraction: float) -> str:
    return f"{'+' if fraction >= 0 else '−'}{abs(100 * fraction):.2f}"


def cutoff_text(value: float) -> str:
    """A confidence or a cutoff as a percentage, with the decimals that tell it apart, up to two: 0.99 is 99%, 0.999 is
    99.9% and 0.960506 is 96.05%. A stored score is compared before any rounding; this is only how it reads."""
    return f"{100 * value:.2f}".rstrip("0").rstrip(".") + "%"


def change_text(fraction: float) -> str:
    """A change in accuracy in words: '0.27 points higher', '0.09 points lower' or 'no change'."""
    if round(100 * fraction, 2) == 0:
        return "no change"
    return f"{abs(100 * fraction):.2f} points {'higher' if fraction > 0 else 'lower'}"


def seconds(value: float) -> str:
    """A response time in seconds, two decimals: 0.23."""
    return f"{value:.2f}"


def p_text(p: float) -> str:
    return "p < 0.0001" if p < 0.0001 else f"p = {p:.2g}"


def long_date(iso: str) -> str:
    day = datetime.date.fromisoformat(iso[:10])
    return f"{day.day} {day:%B} {day.year}"


def reasoning_label(value: str) -> str:
    return f"reasoning {value}" if value in ("on", "off") else f"{value} reasoning"


def setting(item: dict[str, Any]) -> str:
    parts = [item["variant"]] if item.get("variant") else []
    if item.get("reasoning"):
        parts.append(reasoning_label(item["reasoning"]))
    return ", ".join(parts)


def label(item: dict[str, Any]) -> str:
    detail = setting(item)
    return item["name"] + (f" · {detail}" if detail else "")


def named(item: dict[str, Any]) -> str:
    """A configuration's name with its setting in brackets, for use inside a longer label."""
    detail = setting(item)
    return item["name"] + (f" ({detail})" if detail else "")


def label_html(item: dict[str, Any]) -> str:
    detail = setting(item)
    return f'<span class="model-name">{esc(item["name"])}</span>' + (f'<span class="muted"> · {esc(detail)}</span>' if detail else "")


def alone(item: dict[str, Any]) -> str:
    """'GPT-6.1 Sol alone (low reasoning)': a configuration that answers every question itself."""
    detail = setting(item)
    return f"{item['name']} alone" + (f" ({detail})" if detail else "")


def minutes(seconds: float) -> str:
    """Request time in minutes: one decimal below ten, whole minutes from ten."""
    value = seconds / 60
    return f"{value:.1f}" if value < 10 else f"{value:.0f}"


def shares_letter(first: str | None, second: str | None) -> bool:
    """Whether two tie groups share a letter: the test over all pairs did not tell the configurations apart."""
    return any(letter in (second or "") for letter in (first or ""))


def and_list(items: list[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def per_thousand(run: dict[str, Any]) -> float | None:
    """A run's estimated API cost per 1,000 questions asked; None for free tiers and self-hosted runs."""
    return None if run.get("api_equivalent_usd") is None else 1000 * run["api_equivalent_usd"] / run["answered_questions"]


def chart_figure(name: str, alt: str, caption: str, lazy: bool = True) -> str:
    """A chart from charts/ in both themes: the dark SVG shows in the dark theme and the light one in the light theme,
    each linked at full size, with `alt` (plain text, from the data) and `caption` (HTML) below them. chart_sizes()
    gives the images their width and height."""
    loading = ' loading="lazy"' if lazy else ""
    links = "".join(
        f'<a class="chart-link theme-{theme}" href="charts/{name}{suffix}.svg" title="Open the full size chart">'
        f'<img src="charts/{name}{suffix}.svg" alt="{esc(alt)}"{loading if theme == "dark" else " decoding=\"async\""}></a>'
        for theme, suffix in (("dark", "-dark"), ("light", ""))
    )
    return f'<figure class="chart">{links}<figcaption>{caption}</figcaption></figure>'


# ---------------------------------------------------------------- the snapshot


def matches(item: dict[str, Any], spec: dict[str, Any]) -> bool:
    return all(item.get(key) == spec[key] for key in ("provider", "model", "reasoning", "variant") if key in spec)


def pick(items: list[dict[str, Any]], spec: dict[str, Any], what: str) -> dict[str, Any] | None:
    found = [item for item in items if matches(item, spec)]
    if len(found) > 1:
        raise ValueError(f"{what}: {spec} matches {len(found)} entries; name its reasoning or variant")
    if not found and not spec.get("optional"):
        raise ValueError(f"{what}: nothing matches {spec}")
    return found[0] if found else None


def reproduce() -> int:
    """Run reproduce.py; the number of checks, all of which must match."""
    done = subprocess.run([sys.executable, "-B", str(ROOT / "reproduce.py")], capture_output=True, text=True, cwd=ROOT)
    found = CHECKS.search(done.stdout)
    if done.returncode or not found or found.group(2) != "0":
        sys.stderr.write(done.stdout[-2000:] + done.stderr[-2000:])
        raise SystemExit("reproduce.py does not pass; fix the snapshot before building the page")
    return int(found.group(1))


class Snapshot:
    """The numbers the page shows, computed once from results.json and the page configuration."""

    def __init__(self, results: dict[str, Any], config: dict[str, Any], checks: int) -> None:
        if results.get("sure_threshold") != config["threshold"]:
            raise ValueError(f"results.json counts confidence at {results.get('sure_threshold')}, the page at {config['threshold']}")
        self.results, self.config, self.checks = results, config, checks
        self.fmt = Format(config["percent_digits"])
        self.total = results["questions"]
        self.runs = results["runs"]
        self.by_id = {run["run"]: run for run in self.runs}
        reading_units = set(config["reading_units"])
        self.reading_questions = sum(unit["questions"] for unit in results["units"] if unit["number"] in reading_units)
        self.grammar_questions = sum(unit["questions"] for unit in results["units"] if unit["number"] not in reading_units)
        self.models = len({run["model"] for run in self.runs})
        # The confidence rows: the lead finding first, then the other rows in page_config.json's order, an editorial
        # order that ranks nothing. Task rows by overall accuracy, the reference rows last; stability rows by changed
        # answers, fewest first. Ties keep the configuration's order.
        thresholds = [row for spec in config["confidence_rows"] if (row := self.threshold_row(spec))]
        keyed = {row["key"]: row for row in thresholds if row["key"]}
        self.lead_spec = config["leads"][config["lead"]]
        missing = [key for key in self.lead_spec["rows"] if key not in keyed]
        if missing:
            raise ValueError(f"lead {config['lead']!r} names confidence rows that do not exist: {', '.join(missing)}")
        self.lead = [keyed[key] for key in self.lead_spec["rows"]]
        self.thresholds = self.lead + [row for row in thresholds if all(row is not lead for lead in self.lead)]
        tasks = [row for spec in config["accuracy_rows"] if (row := self.task_row(spec))]
        self.tasks = sorted((row for row in tasks if not row["reference"]), key=lambda row: -row["overall"]) + [
            row for row in tasks if row["reference"]
        ]
        # The accuracy table's short list: the configurations the page's figures show, in the leaderboard's order.
        shown = {row["run"]["run"] for row in [*self.thresholds, *self.tasks]}
        self.featured = [run for run in self.runs if run["run"] in shown]
        # Runs the study's sentences name by key: the keyed rows, then page_config.json's named runs.
        self.named = {row["key"]: row["run"] for row in [*thresholds, *tasks] if row["key"]}
        for key, spec in config.get("named_runs", {}).items():
            found = pick(self.runs, spec, f"named run {key}")
            assert found is not None
            self.named[key] = found
        self.repeats_by_key: dict[str, dict[str, Any]] = {}
        for spec in config["stability_whole_bank"]:
            item = pick(results["repeats"], spec, "stability")
            assert item is not None
            if not item["whole_bank"] or item["questions_per_request"] != 1:
                raise ValueError(f"{label(item)}: its repeats are not one question per request over the whole bank")
            self.repeats_by_key[spec["key"]] = item
        self.whole_bank = sorted(self.repeats_by_key.values(), key=lambda item: item["changed_answer"])
        per_request = config["stability_sample_questions_per_request"]
        self.sample = sorted(
            (item for item in results["repeats"] if not item["whole_bank"] and item["questions_per_request"] == per_request),
            key=lambda item: item["changed_answer"],
        )
        self.prices = {(price["provider"], price["model"]): price for price in results["prices"]}
        self.plan, self.costs = self.cost_rows()
        self.cutoff = cutoff_text(config["threshold"])
        self.replay = self.replay_rows()

    def decision_model(self, run: dict[str, Any]) -> bool:
        return run["provider"] in self.config["decision_model_providers"] and run["model"] not in self.config["not_decision_models"]

    def threshold_row(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        run = pick(self.runs, spec, "confidence_rows")
        if run is None:
            return None
        sure = (run.get("confidence") or {}).get("sure") or {"questions": 0, "correct": 0, "interval": None}
        accepted, right, interval = sure["questions"], sure["correct"], sure.get("interval")
        if accepted:
            # The stored interval must be the Wilson interval of the counts.
            recomputed = bm.wilson_interval(right, accepted)
            if any(abs(stored - again) > 1e-12 for stored, again in zip(interval, recomputed)):
                raise ValueError(f"{label(run)}: stored interval {interval}, Wilson interval of the counts {recomputed}")
        return {
            "key": spec.get("key"),
            "run": run,
            "source": (run.get("confidence") or {}).get("label", "no confidence"),
            "accepted": accepted,
            "correct": right,
            "errors": accepted - right,
            "sent": self.total - accepted,
            "coverage": accepted / self.total,
            "error_rate": (accepted - right) / accepted if accepted else None,
            # The error interval is the accuracy interval turned around: [1 - U, 1 - L].
            "error_range": (1 - interval[1], 1 - interval[0]) if accepted else None,
        }

    def task_row(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        run = pick(self.runs, spec, "accuracy_rows")
        if run is None:
            return None
        groups = run["groups"]
        return {
            "key": spec.get("key"),
            "reference": spec.get("reference", False),
            "run": run,
            "overall": run["correct"] / self.total,
            "reading": groups["reading"]["correct"] / groups["reading"]["questions"],
            "grammar": groups["grammar"]["correct"] / groups["grammar"]["questions"],
        }

    def main_run(self, item: dict[str, Any]) -> dict[str, Any]:
        """The leaderboard run of the same configuration as a run on listed questions."""
        spec = {key: item.get(key) for key in ("provider", "model", "reasoning")}
        found = pick(self.runs, spec, "the leaderboard run of a routing test run")
        assert found is not None
        return found

    def cost_rows(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        spec = self.config["cost"]
        decision = pick(self.runs, spec["decision"], "cost decision")
        frontier = pick(self.runs, spec["frontier"], "cost frontier")
        assert decision is not None and frontier is not None
        plan = next(
            item
            for item in self.results["pipelines"]
            if item["decision"] == decision["run"] and item["frontier"] == frontier["run"] and item.get("measured")
        )
        measured = plan["measured"]
        rows = [
            {"label": alone(frontier), "runs": [frontier], "accuracy": measured["frontier_accuracy"], "versus": None,
             "cost": measured["frontier_cost_usd"], "seconds": measured["frontier_request_seconds"]},
            {"label": f"{named(decision)} followed by {named(frontier)}", "runs": [decision, frontier], "accuracy": measured["accuracy"],
             "versus": {key: measured[key] for key in ("difference", "low", "high", "p")},
             "cost": measured["cost_usd"], "seconds": measured["request_seconds"]},
        ]
        for alternative_spec in spec["alternatives"]:
            alternative = pick(measured["alternatives"], alternative_spec, "cost alternatives")
            assert alternative is not None
            rows.append({"label": alone(alternative), "runs": [self.main_run(alternative)], "accuracy": alternative["accuracy"],
                         "versus": alternative["versus_frontier"], "cost": alternative["cost_usd"], "seconds": alternative["request_seconds"]})
        return plan, rows

    def billing(self, run: dict[str, Any]) -> dict[str, str]:
        return self.config["billing"][run["billing"]]

    def price(self, run: dict[str, Any]) -> dict[str, Any] | None:
        return self.prices.get((run["provider"], run["model"]))

    def short(self, run: dict[str, Any]) -> str:
        """A configuration's short name, for a second mention in one sentence (page_config.json's short_names)."""
        return self.config["short_names"].get(run["model"], run["name"])

    def frontier_key(self, run: dict[str, Any]) -> str:
        """The key a second model has among page_config.json's named runs."""
        found = [key for key, named in self.named.items() if named is run]
        if not found:
            raise ValueError(f"{label(run)} answers after a first model; give it a key in page_config.json's named_runs")
        return found[0]

    def replay_rows(self) -> dict[str, Any]:
        """results.json's replay with what the page says about it: per second model, its accuracy and cost alone, then
        for each rule (99% cutoff, surest share, strict cutoff from the cascades) the share Decider takes, the estimated
        saving on the pair's cost, and the change in accuracy. The strict cutoff is None where no cascade was run."""
        replay = self.results["replay"]
        decision = self.by_id[replay["decision"]]
        cascades = {(item["decision"], item["frontier"]): item for item in self.results["cascades"]}
        frontiers = []
        for item in replay["frontiers"]:
            run = self.by_id[item["frontier"]]
            cost = per_thousand(run)
            assert cost is not None
            strict = cascades.get((decision["run"], run["run"]))
            frontiers.append({
                "key": self.frontier_key(run),
                "run": run,
                "accuracy": run["correct"] / self.total,
                "cost": cost,
                "sure": {**item["sure"], "share": item["sure"]["kept"] / self.total, "saving": 1 - item["sure"]["usd_per_1000"] / cost},
                "share": {**item["share"], "share": item["share"]["kept"] / self.total, "saving": 1 - item["share"]["usd_per_1000"] / cost},
                "strict": None if strict is None else {
                    **strict["held_out"], "share": strict["held_out"]["answered"], "usd_per_1000": strict["usd_per_1000"],
                    "saving": 1 - strict["usd_per_1000"] / cost,
                },
            })
        return {**replay, "run": decision, "frontiers": frontiers}


# ---------------------------------------------------------------- values for the page's spans


def values(snap: Snapshot) -> dict[str, str]:
    results, fmt = snap.results, snap.fmt
    per_request = snap.config["stability_sample_questions_per_request"]
    out = {
        "threshold": cutoff_text(snap.config["threshold"]),
        "questions": count(snap.total),
        "models": count(snap.models),
        "configs": count(len(snap.runs)),
        "featured_configs": count(len(snap.featured)),
        "reading_questions": count(snap.reading_questions),
        "grammar_questions": count(snap.grammar_questions),
        "grammar_share": f"{100 * snap.grammar_questions / snap.total:.0f}%",
        "published": long_date(snap.config["published"]),
        "results_updated": long_date(results["updated"]),
        "results_version": results["results_version"],
        "dataset_version": f"{results['dataset']['name']} ({(results['dataset']['graded_sha256'] or results['dataset']['sha256'])[:8]})",
        "checks": count(snap.checks),
        "comparisons": count(len(results["paired"])),
        "significant": count(sum(item["p_holm"] < ALPHA for item in results["paired"])),
        "pairs": count(results["group_pairs"]),
        "held_out": count(snap.plan["held_out"]),
        # Repeat runs beyond each configuration's leaderboard run, as in the answer export.
        "repeat_runs": count(len({run for item in results["repeats"] for run in item["runs"]} - snap.by_id.keys())),
        # Configurations by questions per request, and how many of each were repeated.
        "one_question_configs": count(sum(run["questions_per_request"] == 1 for run in snap.runs)),
        "batched_configs": count(sum(run["questions_per_request"] == per_request for run in snap.runs)),
        "repeated_whole_bank": count(sum(item["whole_bank"] and item["questions_per_request"] == 1 for item in results["repeats"])),
        "repeated_sample": count(len(snap.sample)),
        "sample_questions": count(snap.sample[0]["questions"]) if snap.sample else "0",
        "batch_size": count(per_request),
        # The Turkish section of the 2026 exam the Exam mix column reweights to.
        "exam_reading": in_words(results["tyt_mix"]["reading"]),
        "exam_grammar": in_words(results["tyt_mix"]["grammar"]),
        # What answering without reading would score: random guessing, and always the key's most used letter.
        "baseline_options": in_words(results["baselines"]["options"]),
        "baseline_random": fmt.pct(1 / results["baselines"]["options"], 0),
        "baseline_letter": results["baselines"]["letter"],
        "baseline_letter_share": fmt.pct(results["baselines"]["letter_share"]),
    }
    for row in snap.thresholds:
        if row["key"]:
            out[f"{row['key']}_accepted"] = count(row["accepted"])
            out[f"{row['key']}_coverage"] = fmt.pct(row["coverage"])
            out[f"{row['key']}_correct"] = count(row["correct"])
            out[f"{row['key']}_errors"] = count(row["errors"])
            out[f"{row['key']}_error_rate"] = fmt.pct(row["error_rate"]) if row["error_rate"] is not None else "not applicable"
            out[f"{row['key']}_error_high"] = fmt.pct(row["error_range"][1]) if row["error_range"] else "not applicable"
            out[f"{row['key']}_error_span"] = fmt.span(*row["error_range"]) if row["error_range"] else "not applicable"
            out[f"{row['key']}_accuracy_low"] = fmt.pct(1 - row["error_range"][1]) if row["error_range"] else "not applicable"
            out[f"{row['key']}_per_request"] = count(row["run"]["questions_per_request"])
    for key, run in snap.named.items():
        groups, confidence = run["groups"], run.get("confidence") or {}
        out[f"{key}_accuracy"] = fmt.pct(run["correct"] / snap.total)
        out[f"{key}_reading"] = fmt.pct(groups["reading"]["correct"] / groups["reading"]["questions"])
        out[f"{key}_grammar"] = fmt.pct(groups["grammar"]["correct"] / groups["grammar"]["questions"])
        out[f"{key}_auroc"] = f"{confidence['auroc']:.2f}" if confidence.get("auroc") is not None else "not available"
        out[f"{key}_ece"] = f"{confidence['ece']:.3f}" if confidence.get("ece") is not None else "not available"
        # The calibration gap in percentage points, as the page states it.
        out[f"{key}_ece_points"] = f"{100 * confidence['ece']:.1f}" if confidence.get("ece") is not None else "not available"
        out[f"{key}_tokens"] = count(round(run["output_tokens"] / run["answered_questions"])) if run.get("output_tokens") is not None else "not reported"
        out[f"{key}_cost"] = usd(1000 * run["api_equivalent_usd"] / run["answered_questions"]) if run.get("api_equivalent_usd") is not None else "not estimated"
        out[f"{key}_minutes"] = minutes(run["request_seconds"])
        out[f"{key}_concurrency"] = count(run["concurrency"])
        single = run["single_question_latency"]
        out[f"{key}_single_median"] = f"{single['median_request_seconds']:.2f}" if single else "not measured"
        out[f"{key}_single_p90"] = f"{single['p90_request_seconds']:.2f}" if single and single.get("p90_request_seconds") else "not measured"
        latency = run["latency"]
        out[f"{key}_median"] = seconds(latency["median_request_seconds"]) if latency else "not measured"
        out[f"{key}_p90"] = seconds(latency["p90_request_seconds"]) if latency and latency.get("p90_request_seconds") else "not measured"
        out[f"{key}_median_ms"] = f"{1000 * latency['median_request_seconds']:.0f}" if latency else "not measured"
        out[f"{key}_p90_ms"] = f"{1000 * latency['p90_request_seconds']:.0f}" if latency and latency.get("p90_request_seconds") else "not measured"
        # Questions left without a valid answer count as wrong; the accuracy on the rest shows what they cost.
        out[f"{key}_unanswered"] = count(run["invalid"])
        out[f"{key}_answered_accuracy"] = fmt.pct(run["correct"] / (snap.total - run["invalid"]))
    for key, item in snap.repeats_by_key.items():
        out[f"{key}_changed"] = count(item["changed_answer"])
        out[f"{key}_changed_share"] = fmt.pct(item["changed_answer"] / item["questions"], 0)
        out[f"{key}_same_wrong"] = count(item["wrong_every_run_same"])
        out[f"{key}_wrong_any"] = count(item["wrong_any"])
    # On all scored questions: what switching from GPT-6 Astra to GPT-6.1 Sol saves, and the accuracy it costs.
    astra, sol = snap.named["astra"], snap.named["sol"]
    per_thousand = {key: 1000 * run["api_equivalent_usd"] / run["answered_questions"] for key, run in (("astra", astra), ("sol", sol))}
    out["sol_saving"] = fmt.pct(1 - per_thousand["sol"] / per_thousand["astra"], 0)
    out["sol_gap"] = f"{100 * (astra['correct'] - sol['correct']) / snap.total:.1f}"
    out.update(replay_values(snap))
    out.update(paired_values(snap))
    out.update(top_values(snap))
    out.update(overview_values(snap))
    out.update(study_values(snap))
    out.update(method_values(snap))
    return out


def replay_values(snap: Snapshot) -> dict[str, str]:
    """The replay's numbers for the copy. cut_<tag>_*: Decider at each fixed cutoff, the tag being the cutoff's digits
    (99.9% is 999, 99% is 99). surest_*: its surest share (results.json's replay.share). <second>_sure_*,
    <second>_surest_* and <second>_strict_*: in front of each second model (its named-run key), at 99%, with the surest
    share and with the strict cutoff ('not run' where no cascade exists); *_whole rounds a share or saving to a whole
    percent for headlines. route_<first>_<second>_*: every routing simulation whose two runs have named keys."""
    fmt, replay, out = snap.fmt, snap.replay, {}
    for row in replay["cutoffs"]:
        tag = cutoff_text(row["cutoff"]).rstrip("%").replace(".", "")
        out[f"cut_{tag}_kept"] = count(row["kept"])
        out[f"cut_{tag}_share"] = fmt.pct(row["kept"] / snap.total)
        out[f"cut_{tag}_share_whole"] = fmt.pct(row["kept"] / snap.total, 0)
        out[f"cut_{tag}_wrong"] = count(row["wrong"])
    share = replay["share"]
    out["surest_rule"] = fmt.pct(share["share"], 0)
    out["surest_cut"] = cutoff_text(share["cut"])
    out["surest_kept"] = count(share["kept"])
    out["surest_correct"] = count(share["kept"] - share["wrong"])
    out["surest_wrong"] = count(share["wrong"])
    out["surest_coverage"] = fmt.pct(share["kept"] / snap.total)
    out["surest_accuracy"] = fmt.pct((share["kept"] - share["wrong"]) / share["kept"])
    out["surest_error_span"] = fmt.span(1 - share["interval"][1], 1 - share["interval"][0])
    for item in replay["frontiers"]:
        key = item["key"]
        for rule, prefix in (("sure", "sure"), ("share", "surest"), ("strict", "strict")):
            numbers = item[rule]
            if numbers is None:
                for part in ("share", "share_whole", "saving", "saving_whole", "change", "worse", "cost"):
                    out[f"{key}_{prefix}_{part}"] = "not run"
                continue
            out[f"{key}_{prefix}_share"] = fmt.pct(numbers["share"])
            out[f"{key}_{prefix}_share_whole"] = fmt.pct(numbers["share"], 0)
            out[f"{key}_{prefix}_saving"] = fmt.pct(numbers["saving"])
            out[f"{key}_{prefix}_saving_whole"] = fmt.pct(numbers["saving"], 0)
            out[f"{key}_{prefix}_change"] = change_text(numbers["difference"])
            out[f"{key}_{prefix}_cost"] = usd(numbers["usd_per_1000"])
        for rule, prefix in (("sure", "sure"), ("share", "surest")):
            numbers = item[rule]
            net = numbers["first_only"] - numbers["second_only"]
            out[f"{key}_{prefix}_first_only"] = count(numbers["first_only"])
            out[f"{key}_{prefix}_second_only"] = count(numbers["second_only"])
            out[f"{key}_{prefix}_net"] = "no more right or wrong" if not net else f"{count(abs(net))} more {'right' if net > 0 else 'wrong'}"
        held = item["share"]["held_out"]
        out[f"{key}_surest_held_change"] = change_text(held["difference"])
        out[f"{key}_surest_held_worse"] = fmt.pct(held["worse"], 0)
        out[f"{key}_surest_held_better"] = fmt.pct(held["better"], 0)
        if item["strict"] is not None:
            out[f"{key}_strict_worse"] = fmt.pct(item["strict"]["worse"], 0)
    keys = {run["run"]: key for key, run in snap.named.items()}
    for item in snap.results["cascades"]:
        first, second = keys.get(item["decision"]), keys.get(item["frontier"])
        if first and second:
            held = item["held_out"]
            out[f"route_{first}_{second}_share"] = fmt.pct(held["answered"])
            out[f"route_{first}_{second}_change"] = change_text(held["difference"])
            out[f"route_{first}_{second}_worse"] = fmt.pct(held["worse"], 0)
            out[f"route_{first}_{second}_cost"] = usd(item["usd_per_1000"])
    return out


def p_value(p: float) -> str:
    """A p-value to two significant figures; 1 when Holm's correction caps it."""
    return "1" if p >= 1 else f"{p:.2g}"


def paired_values(snap: Snapshot) -> dict[str, str]:
    """Each listed paired comparison whose two runs have named keys, as pair_<first>_<second>_*: the observed gap in
    points (first minus second), the questions only one got right, the p-value, Holm over the listed comparisons
    (_p_holm) and Holm over every pair of runs (_p_holm_all, the correction behind the comparison letters)."""
    keys = {run["run"]: key for key, run in snap.named.items()}
    out = {}
    for item in snap.results["paired"]:
        first, second = keys.get(item["first"]), keys.get(item["second"])
        if first and second:
            stem = f"pair_{first}_{second}"
            out[f"{stem}_difference"] = f"{abs(100 * item['difference']):.1f}"
            out[f"{stem}_first_only"] = count(item["first_only"])
            out[f"{stem}_second_only"] = count(item["second_only"])
            out[f"{stem}_p"] = p_value(item["p"])
            out[f"{stem}_p_holm"] = p_value(item["p_holm"])
            out[f"{stem}_p_holm_all"] = p_value(item["p_holm_all"])
    return out


# ---------------------------------------------------------------- blocks


# Below this share of a bar, an accepted-but-wrong segment is too thin to see at phone width; a marker outside the
# bar shows where it sits, and the segment keeps its true width.
MARKER_BELOW = 0.02


def stack_html(row: dict[str, Any], snap: Snapshot) -> str:
    """The three segments of a threshold bar, as shares of all scored questions, drawn to scale."""
    correct, wrong = row["correct"] / snap.total, row["errors"] / snap.total
    marker = f'<span class="wrong-marker" style="left: {100 * correct:.3f}%"></span>' if row["errors"] and wrong < MARKER_BELOW else ""
    wrong_class = "wrong nonzero" if row["errors"] else "wrong"
    return (
        '<span class="stack" aria-hidden="true"><span class="fill">'
        f'<span class="ok" style="flex-basis: {100 * correct:.3f}%"></span>'
        f'<span class="{wrong_class}" style="flex-basis: {100 * wrong:.3f}%"></span>'
        f'<span class="check"></span></span>{marker}</span>'
    )


def kept_sentences(row: dict[str, Any], snap: Snapshot) -> list[tuple[str, str]]:
    """The row template of the fixed cutoff, as (class, sentence) pairs: the answers we keep with their share of all
    questions, the wrong ones with their share of the kept answers, the 95% interval for that error rate and the
    questions that need another answer. A row with nothing kept gets no error rate. Only a nonzero wrong count is
    marked as wrong, so that zero wrong answers never take the error colour."""
    fmt = snap.fmt
    if not row["accepted"]:
        return [("", f"No answer reaches the {snap.cutoff} cutoff."),
                ("", f"All {count(snap.total)} questions need another answer."),
                ("", "Error rate among kept answers: not applicable.")]
    errors = row["errors"]
    wrong = ("None of them is wrong." if not errors
             else f"{opening_count(errors)} {'is' if errors == 1 else 'are'} wrong, {fmt.pct(row['error_rate'])} of the kept answers.")
    return [("", f"We keep {count(row['accepted'])} answers, {fmt.pct(row['coverage'])} of all questions."),
            ("v-wrong" if errors else "", wrong),
            ("", f"The 95% interval for the error rate is {fmt.span(*row['error_range'])}."),
            ("", f"{count(row['sent'])} questions need another answer.")]


LEGEND = (
    '<span class="legend"><span><i class="key ok"></i>Kept and correct</span> '
    '<span><i class="key wrong"></i>Kept but wrong</span> <span><i class="key check"></i>Needs another answer</span></span>'
)


def threshold_caption(snap: Snapshot) -> str:
    """Chart 03's caption: what the lead keeps at the fixed cutoff, and that the share of the cutoff chosen on half the
    questions in front of Astra is a different result. Only a single lead with no wrong kept answers fits the sentence."""
    if len(snap.lead) != 1 or not snap.lead[0]["accepted"] or snap.lead[0]["errors"]:
        return ""
    lead = snap.lead[0]
    strict = next((item["strict"] for item in snap.replay["frontiers"] if item["key"] == "astra" and item["strict"]), None)
    if strict is None:
        raise ValueError("chart 03's caption names the cutoff chosen on half the questions in front of Astra, which results.json no longer has")
    return (f"A separate check with one fixed cutoff. {esc(snap.short(lead['run']))} keeps {count(lead['accepted'])} answers, "
            f"or {snap.fmt.pct(lead['coverage'])}, with no wrong answers. This is not the {snap.fmt.pct(strict['share'])} it "
            "takes in front of Astra with the cutoff chosen on half the questions, which comes from a separate replay. ")


def threshold_figure(snap: Snapshot) -> str:
    items = []
    for row in snap.thresholds:
        is_lead = any(row is first for first in snap.lead)
        values = " ".join(f'<span class="{kind}">{esc(text)}</span>' if kind else f"<span>{esc(text)}</span>"
                          for kind, text in kept_sentences(row, snap))
        items.append(
            ('<li class="lead">' if is_lead else "<li>")
            + f'<p class="bar-label">{label_html(row["run"])}<span class="small">Confidence source: {esc(row["source"].lower())}</span></p>'
            + stack_html(row, snap)
            + f'<p class="bar-values">{values}</p></li>'
        )
    return (
        '<figure class="threshold-figure" aria-labelledby="threshold-title" aria-describedby="threshold-caption">'
        f'<p class="figure-title" id="threshold-title">Which answers pass a {snap.cutoff} confidence cutoff?</p>'
        f'<p class="legend-line">{LEGEND}</p>'
        f'<ul class="threshold-bars">{"".join(items)}</ul>'
        f'<figcaption id="threshold-caption">Each bar is all {count(snap.total)} scored questions. {threshold_caption(snap)}'
        f"{esc(snap.lead_spec['order'])}. This order is an editorial grouping, not a ranking.</figcaption></figure>"
    )


def overview_tip(text: str, about: str) -> str:
    """A small focusable mark that shows `text` on hover or keyboard focus; the copy around it says the same."""
    return (f' <span class="tip" tabindex="0" aria-label="About {esc(about)}">?'
            f'<span class="badge-tip" role="tooltip">{esc(text)}</span></span>')


INTERVAL_TIP = ("A range describing sampling uncertainty in this measured rate. It does not cover every source of error or "
                "guarantee a future rate.")


def threshold_table(snap: Snapshot) -> str:
    fmt = snap.fmt
    rows = []
    for row in snap.thresholds:
        run = row["run"]
        if row["accepted"]:
            kept = f'{count(row["accepted"])}<span class="small">{fmt.pct(row["coverage"])} of all questions</span>'
            rate = "0%" if not row["errors"] else fmt.pct(row["error_rate"])
            errors = f'{count(row["errors"])}<span class="small">{rate} of the kept answers</span>'
            span = fmt.span(*row["error_range"])
        else:
            kept = '0<span class="small">No answers reach this cutoff</span>'
            errors, span = "Not applicable", "Not applicable"
        rows.append(
            "<tr>"
            f'<td data-label="Model and setup">{label_html(run)}</td>'
            f'<td data-label="Where the confidence score comes from">{esc(row["source"])}</td>'
            f'<td class="num" data-label="Answers we keep">{kept}</td>'
            f'<td class="num" data-label="Wrong answers among those we keep">{errors}</td>'
            f'<td class="num" data-label="95% interval for the error rate">{span}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Model and setup</th><th scope="col">Where the confidence score comes from</th>'
        f'<th scope="col" class="num">Answers we keep<span class="small">at {snap.cutoff} confidence or higher</span></th>'
        '<th scope="col" class="num">Wrong answers among those we keep</th>'
        f'<th scope="col" class="num">95% interval for the error rate{overview_tip(INTERVAL_TIP, "the 95% interval")}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def task_title(snap: Snapshot) -> str:
    """The reading-and-grammar figure's title, on the page and in its sharing images. The figure shows the decision
    models above the chat models for comparison (accuracy_rows marks those as references); the build stops if a row
    no longer belongs to its group."""
    for row in snap.tasks:
        if snap.decision_model(row["run"]) == row["reference"]:
            raise ValueError(f"{label(row['run'])} no longer fits its group in the reading and grammar figure")
    return "How often do models get reading and grammar questions right?"


def task_groups(snap: Snapshot) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The decision model rows, the lead first and the others by overall accuracy, then the chat models for comparison."""
    lead = {row["run"]["run"] for row in snap.lead}
    decision = sorted((row for row in snap.tasks if not row["reference"]), key=lambda row: row["run"]["run"] not in lead)
    return decision, [row for row in snap.tasks if row["reference"]]


def task_check(snap: Snapshot) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The decision model, the chat model and the top model that the accuracy copy and chart 04's caption compare on
    reading and grammar. The build stops unless the chat model beats every decision model on both tasks with a grammar
    score at least ten points below its own reading score."""
    decision, chat, top = (snap.named[key] for key in snap.config["accuracy_lead"]["task"])
    deciders = [run for run in snap.runs if snap.decision_model(run)]

    def share(run: dict[str, Any], part: str) -> float:
        return run["groups"][part]["correct"] / run["groups"][part]["questions"]

    if (not snap.decision_model(decision) or snap.decision_model(chat) or snap.decision_model(top)
            or any(share(chat, part) <= max(share(run, part) for run in deciders) for part in ("reading", "grammar"))
            or share(chat, "reading") - share(chat, "grammar") < 0.1):
        raise ValueError("the reading and grammar comparison in the Accuracy section no longer fits the data")
    return decision, chat, top


def task_figure(snap: Snapshot) -> str:
    fmt = snap.fmt

    def bars(rows: list[dict[str, Any]]) -> str:
        items = []
        for row in rows:
            pairs = "".join(
                f'<span class="pair"><span class="part {part}">{name}</span><span class="track"><span class="bar {part}" style="width: {100 * row[part]:.2f}%"></span></span>'
                f'<span class="value">{fmt.pct(row[part])}</span></span>'
                for part, name in (("reading", "Reading"), ("grammar", "Grammar"))
            )
            items.append(f'<li><p class="bar-label">{label_html(row["run"])}</p>{pairs}</li>')
        return f'<ul class="task-bars">{"".join(items)}</ul>'

    decision, chat = task_groups(snap)
    _, model, _ = task_check(snap)
    name = esc(snap.short(model))
    lead = and_list([esc(snap.short(row["run"])) for row in snap.lead])
    # The axis is one more row of the same grid, so its ticks sit over the bars' own track.
    ticks = "".join(f'<span style="left: {tick}%">{tick}%</span>' for tick in (0, 25, 50, 75, 100))
    return (
        '<figure class="task-figure" aria-labelledby="task-title" aria-describedby="task-caption">'
        f'<p id="task-title" class="figure-title">{esc(task_title(snap))}</p>'
        f'<p class="caption">Reading: {count(snap.reading_questions)} questions. Grammar: {count(snap.grammar_questions)} questions. '
        "Each bar shows correct answers, from 0% to 100%.</p>"
        f'<p class="task-group">Decision models</p>{bars(decision)}'
        f'<p class="task-group">Chat models for comparison</p>{bars(chat)}'
        f'<p class="pair axis" aria-hidden="true"><span></span><span class="axis-track">{ticks}</span><span></span></p>'
        f'<figcaption id="task-caption" class="caption">{name} scores higher than every decision model on both reading and '
        "grammar. Its grammar result is lower than its own reading result. This test does not establish why the task scores "
        f"differ. We list {lead} first and the other decision models by correct answers overall; this is a reading order, "
        "not a rank.</figcaption></figure>"
    )


GROUP_TIP = ("The all pairs test did not detect a difference from setups sharing a letter. This does not establish equality.")


def results_rows(snap: Snapshot, runs: list[dict[str, Any]]) -> str:
    fmt = snap.fmt
    rows = []
    for run in runs:
        groups = run["groups"]
        decides = snap.decision_model(run)
        detail = setting(run) or ("Scores the supplied options" if decides else "Not applicable")
        badge = (
            '<span class="badge" tabindex="0" aria-describedby="decision-model-help">Decision model'
            '<span class="badge-tip" role="tooltip">Picks from the options we give it and gives each option a score. In this test, we used only the pick and the scores.</span></span>'
            if decides
            else ""
        )
        rows.append(
            "<tr>"
            f'<td><details class="model-details"><summary>{label_html(run)}</summary><dl>'
            f'<dt>How we called the model</dt><dd>{esc(run["access"])}</dd>'
            f'<dt>Reasoning setting</dt><dd>{esc(detail)}</dd>'
            f'<dt>Questions in each request</dt><dd>{run["questions_per_request"]}</dd>'
            f'<dt>Test started</dt><dd>{long_date(run["started"])}</dd>'
            f"</dl></details>{badge}</td>"
            f'<td class="num" data-label="Correct answers overall">{fmt.pct(run["correct"] / snap.total)}</td>'
            f'<td class="num reading" data-label="Reading accuracy">{fmt.pct(groups["reading"]["correct"] / groups["reading"]["questions"])}</td>'
            f'<td class="num grammar" data-label="Grammar accuracy">{fmt.pct(groups["grammar"]["correct"] / groups["grammar"]["questions"])}</td>'
            f'<td class="group" data-label="Comparison group">{esc(run.get("group") or "Not applicable")}</td>'
            "</tr>"
        )
    return "".join(rows)


def results_grid(snap: Snapshot, runs: list[dict[str, Any]], others: str) -> str:
    """One accuracy table: the decision models, then the other models under their own label, each by overall accuracy."""
    decision = [run for run in runs if snap.decision_model(run)]
    rest = [run for run in runs if not snap.decision_model(run)]
    return (
        '<div class="table-wrap"><table class="overview results">'
        '<thead><tr><th scope="col">Model and setup</th><th scope="col" class="num">Correct answers overall</th>'
        '<th scope="col" class="num reading"><i class="key reading"></i>Reading accuracy</th>'
        '<th scope="col" class="num grammar"><i class="key grammar"></i>Grammar accuracy</th>'
        f'<th scope="col">Comparison group{overview_tip(GROUP_TIP, "comparison groups")}</th></tr></thead>'
        f'<tbody><tr class="group-row"><th scope="colgroup" colspan="5">Decision models</th></tr>{results_rows(snap, decision)}'
        f'<tr class="group-row"><th scope="colgroup" colspan="5">{others}</th></tr>{results_rows(snap, rest)}</tbody></table></div>'
    )


def results_table(snap: Snapshot) -> str:
    """The setups the page's figures show, then every setup on request."""
    return (
        results_grid(snap, snap.featured, "Chat models for comparison")
        + f'<details class="all-configs"><summary>Show all {count(len(snap.runs))} model setups</summary>'
        + results_grid(snap, snap.runs, "Chat models and other models for comparison") + "</details>"
    )


def stability_table(items: list[dict[str, Any]], fmt: Format) -> str:
    # Every setup in a group has the same number of runs (group_heading checks it).
    repeated = f"Questions with the same wrong answer in all {in_words(len(items[0]['runs']))} runs"
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f'<td data-label="Model and setup">{label_html(item)}</td>'
            f'<td class="num" data-label="Questions where the answer changed">{count(item["changed_answer"])}'
            f'<span class="small">{fmt.pct(item["changed_answer"] / item["questions"])} of questions</span></td>'
            f'<td class="num" data-label="{repeated}">{count(item["wrong_every_run_same"])}'
            f'<span class="small">out of the {count(item["wrong_any"])} questions answered wrongly at least once</span></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Model and setup</th><th scope="col" class="num">Questions where the answer changed</th>'
        f'<th scope="col" class="num">{repeated}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def group_heading(items: list[dict[str, Any]], what: str) -> str:
    """A repeat group's questions, questions per request and runs, which every setup in it shares."""
    questions = {item["questions"] for item in items}
    per_request = {item["questions_per_request"] for item in items}
    runs = {len(item["runs"]) for item in items}
    if len(questions) != 1 or len(per_request) != 1 or len(runs) != 1:
        raise ValueError(f"{what}: the setups differ in questions, questions per request or runs")
    (questions_value,), (per_request_value,), (runs_value,) = questions, per_request, runs
    noun = "question" if per_request_value == 1 else "questions"
    return f"{count(questions_value)} questions, {in_words(per_request_value)} {noun} per request, {in_words(runs_value)} runs"


def stability(snap: Snapshot) -> str:
    if snap.whole_bank[0]["questions"] != snap.total or snap.sample[0]["questions"] >= snap.total:
        raise ValueError("the repeat groups no longer split into the full question set and a smaller one")
    return (
        f'<h3 id="stability-whole-bank">Full question set: {group_heading(snap.whole_bank, "full question set")}</h3>'
        + stability_table(snap.whole_bank, snap.fmt)
        + f'<h3 id="stability-sample">Smaller question set: {group_heading(snap.sample, "smaller question set")}</h3>'
        + stability_table(snap.sample, snap.fmt)
    )


def stability_lead(snap: Snapshot) -> str:
    """The section's opening: one setup's changed answers and repeated wrong answers, with their denominators."""
    item = snap.repeats_by_key[snap.config["stability_lead"]]
    name, runs, total = esc(snap.short(item)), in_words(len(item["runs"])), count(item["questions"])
    changed = (f"{name} chose the same answer every time on all {total} questions." if not item["changed_answer"]
               else f"{name} changed its answer on {count(item['changed_answer'])} of the {total} questions.")
    same = count(item["wrong_every_run_same"])
    if item["wrong_every_run_same"] == item["wrong_any"]:
        repeated = f"It also gave the same wrong answer every time on {same} questions: every question it got wrong at least once."
    else:
        repeated = (f"It also gave the same wrong answer every time on {same} of the {count(item['wrong_any'])} questions it "
                    "got wrong at least once.")
    return f"<p>We asked the same questions {runs} times with the same settings. {changed} {repeated}</p>"


# The live tests' rules in the order the savings table names them, with the label each has on the page.
LIVE_RULES = {"share": "Most confident quarter", "half": "Cutoff chosen on half the questions", "cutoff": "Fixed 99% rule"}


def live_tests(snap: Snapshot) -> dict[str, Any]:
    """The live tests with new calls to the second model, from results.json's pipelines, each with its plan, its measured
    results, its first and second models and the second model's key. "decider": the replay's first model (Decider v1.1)
    in front of each of page_config.json's live_tests seconds, by rule, with the second model's own number of questions
    per request; "timed": the same pairs with the cutoff chosen on half the questions and one question per request;
    "earlier": the cost section's first model (Decider v1) in front of the earlier seconds. The build stops when a test
    is missing, when a rule is not the one its label names, or when the tests do not share their questions and limit."""
    spec, replayed, earlier = snap.config["live_tests"], snap.replay["run"], snap.by_id[snap.plan["decision"]]
    decider: dict[str, dict[str, dict[str, Any]]] = {}
    timed: dict[str, dict[str, Any]] = {}
    before: dict[str, dict[str, Any]] = {}
    for item in snap.results["pipelines"]:
        if not item.get("measured"):
            continue
        decision, frontier = snap.by_id[item["decision"]], snap.by_id[item["frontier"]]
        test = {"plan": item, "measured": item["measured"], "decision": decision, "frontier": frontier, "key": snap.frontier_key(frontier)}
        if decision is replayed and item["batch_size"] == frontier["questions_per_request"]:
            decider.setdefault(test["key"], {})[item["rule"]] = test
        elif decision is replayed and item["batch_size"] == 1 and item["rule"] == "half":
            timed[test["key"]] = test
        elif decision is earlier and item["rule"] == "half":
            before[test["key"]] = test
    missing = ([f"{key} {rule}" for key in spec["seconds"] for rule in LIVE_RULES if rule not in decider.get(key, {})]
               + [f"{key} one question per request" for key in spec["seconds"] if key not in timed]
               + [f"{key} with {label(earlier)}" for key in spec["earlier"] if key not in before])
    if missing:
        raise ValueError(f"results.json lacks live tests: {', '.join(missing)}")
    tests = {
        "decider": {key: {rule: decider[key][rule] for rule in LIVE_RULES} for key in spec["seconds"]},
        "timed": {key: timed[key] for key in spec["seconds"]},
        "earlier": [before[key] for key in spec["earlier"]],
    }
    every = [test for rules in tests["decider"].values() for test in rules.values()] + list(tests["timed"].values()) + tests["earlier"]
    if (any(rules["share"]["plan"]["share"] != 0.25 for rules in tests["decider"].values())
            or any(rules["cutoff"]["plan"]["threshold"] != snap.config["threshold"] for rules in tests["decider"].values())
            or len({test["plan"]["held_out"] for test in every}) != 1 or len({test["plan"]["tolerance_points"] for test in every}) != 1):
        raise ValueError("the live tests no longer fit the copy: quarter, 99% cutoff, shared questions and loss limit")
    return tests


def decider_tests(snap: Snapshot) -> list[dict[str, Any]]:
    """Decider v1.1's batched live tests, by second model, then by rule."""
    return [test for rules in live_tests(snap)["decider"].values() for test in rules.values()]


def saving(measured: dict[str, Any]) -> float:
    """A live test's estimated saving: one minus the pair's estimated cost over the second model's alone."""
    return 1 - measured["cost_usd"] / measured["frontier_cost_usd"]


def live_name(snap: Snapshot, run: dict[str, Any]) -> str:
    """A second mention of a model in the live test copy: page_config.json's live_short_names, else its short name."""
    return snap.config["live_short_names"].get(run["model"], snap.short(run))


def pct2(fraction: float) -> str:
    """An accuracy on the live test's questions, to two decimals, so that changes of a few questions show."""
    return f"{100 * fraction:.2f}%"


def interval_points(low: float, high: float) -> str:
    return f"{points(low)} to {points(high)} points"


def and_list(items: list[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def passed_cost(test: dict[str, Any]) -> float:
    """What one question passed to the second model cost in a live test, over its average question alone."""
    plan, measured = test["plan"], test["measured"]
    passed = plan["held_out"] - plan["routed"]
    return ((measured["cost_usd"] - measured["decision_cost_usd"]) / passed) / (measured["frontier_cost_usd"] / plan["held_out"])


def cost_lead(snap: Snapshot) -> str:
    """Block 07: Decider v1.1's live tests with new calls to each second model, with each rule, then the earlier tests with
    Decider v1 and the cheaper models run alone on the same questions. The build stops unless the text still fits: the
    savings with the cutoff chosen on half the questions below the replay's, one share kept per fixed rule, and the cases
    of the loss limit and the McNemar sentences."""
    fmt, tests = snap.fmt, live_tests(snap)
    decider, earlier = tests["decider"], tests["earlier"]
    some = next(iter(decider.values()))["half"]
    questions, limit = some["plan"]["held_out"], some["plan"]["tolerance_points"]
    me = esc(live_name(snap, some["decision"]))
    names = [esc(live_name(snap, rules["half"]["frontier"])) for rules in decider.values()]
    earlier_alone = {test["measured"]["alone_run"] for test in earlier}
    reused = [esc(live_name(snap, rules["half"]["frontier"])) for rules in decider.values()
              if rules["half"]["measured"]["alone_run"] in earlier_alone]
    replayed = {item["key"]: item["strict"] for item in snap.replay["frontiers"]}
    if any(saving(rules["half"]["measured"]) >= replayed[key]["saving"] for key, rules in decider.items()):
        raise ValueError("block 07 says the live tests saved less than the replay")
    kept = {rule: {rules[rule]["plan"]["routed"] for rules in decider.values()} for rule in ("share", "cutoff")}
    if any(len(shares) != 1 for shares in kept.values()):
        raise ValueError("block 07 gives one share kept by the most confident quarter and one by the 99% cutoff")

    def costs(rule: str) -> str:
        return and_list([fmt.pct(saving(rules[rule]["measured"]), 0) for rules in decider.values()])

    def dearer(test: dict[str, Any]) -> str:
        factor = passed_cost(test) - 1
        return "as much as" if round(100 * factor) == 0 else f"{fmt.pct(abs(factor), 0)} {'more' if factor > 0 else 'less'}"

    halves = [rules["half"] for rules in decider.values()]
    paragraphs = [
        f"We ran the two-step setup live, with {me} in front of each of the {in_words(len(decider))} LLMs. {me}'s answers came "
        "from its recorded run; each LLM answered the questions it passed on, with new calls. We split the questions in half "
        f"at random, keeping the questions about one passage together, and tested on one half: {count(questions)} questions. "
        f"Each LLM also answered all {count(questions)} of them alone, in a separate run"
        + (f"; for {and_list(reused)}, that run comes from our earlier live tests on the same questions." if reused else "."),
        f"We tested all {in_words(len(LIVE_RULES))} rules. With the cutoff chosen on half the questions, we set the cutoff on "
        f"the other half. With the most confident quarter, {me} kept its {count(kept['share'].pop())} most confident answers "
        f"among the test questions. With the fixed {snap.cutoff} rule, it kept every answer at {snap.cutoff} or more, "
        f"{count(kept['cutoff'].pop())} of them.",
        f"With the cutoff chosen on half the questions, {me} kept "
        f"{and_list([fmt.pct(test['plan']['routed'] / questions, 0) for test in halves])} of the questions in front of "
        f"{and_list(names)}, and the estimated cost fell {costs('half')}. The replay of recorded answers gave "
        f"{and_list([fmt.pct(replayed[key]['saving'], 0) for key in decider])}. The replay averages "
        f"{count(snap.results['cascades'][0]['held_out']['splits'])} splits of the questions and gives every question passed to "
        "the LLM the same average cost. The live test used one split, and each LLM's own cost for the questions passed to it: "
        + f"a question passed to {names[0]} cost {dearer(halves[0])}{'' if dearer(halves[0]) == 'as much as' else ' than'} its "
        "average question, " + and_list([f"one passed to {name} {dearer(test)}" + (" its average" if dearer(test) == "as much as" else "")
                                          for name, test in zip(names[1:], halves[1:])])
        + ".",
        f"With the most confident quarter, the estimated cost fell {costs('share')} for {and_list(names)}. With the fixed "
        f"{snap.cutoff} rule, it fell {costs('cutoff')}.",
    ]
    every = decider_tests(snap)
    beyond = [test for test in every if -100 * test["measured"]["difference"] > limit]
    open_ended = [test for test in every if -100 * test["measured"]["low"] > limit]
    observed = (f"In all {in_words(len(every))} tests, the observed change stayed within it." if not beyond else
                f"In {in_words(len(every) - len(beyond))} of the {in_words(len(every))} tests, the observed change stayed within "
                "it; in the " + ("tests" if len(beyond) > 1 else "test") + " "
                + and_list([f"with {esc(live_name(snap, test['frontier']))} and the {LIVE_RULES[test['plan']['rule']].lower()}"
                            for test in beyond]) + ", the observed loss was larger.")
    if len(open_ended) == len(every):
        interval = "But in every test the 95% interval also allows a larger loss, so no test establishes that the loss stays within our limit."
    elif open_ended:
        interval = (f"In {in_words(len(open_ended))} of the {in_words(len(every))} tests, the 95% interval also allows a larger loss, "
                    "so those tests do not establish that the loss stays within our limit.")
    else:
        interval = "In every test the whole 95% interval stays within our limit."
    smallest = min(test["measured"]["p"] for test in every)
    if smallest < 0.05:
        raise ValueError("block 07 says no live test established a change in accuracy")
    paragraphs.append(
        f"Before the tests, we chose the largest accuracy loss we would accept: {limit:g} percentage points. {observed} {interval} "
        f"None of the {in_words(len(every))} tests established a change in accuracy from the LLM alone: the exact McNemar test "
        f"gave p = {smallest:.2g} or more."
    )
    paragraphs.append(
        f"Our first live tests used the earlier {esc(live_name(snap, earlier[0]['decision']))}, with the cutoff chosen on half the "
        "questions: " + "; ".join(
            f"in front of {esc(live_name(snap, test['frontier']))}, it kept {fmt.pct(test['plan']['routed'] / questions)} of the "
            f"questions and the estimated cost fell {fmt.pct(saving(test['measured']))}, with accuracy {change_text(test['measured']['difference'])}"
            for test in earlier) + "."
    )
    others = snap.costs[2:]
    if others:
        alone_text = " ".join(
            f"{esc(named(row['runs'][0]))} scored {pct2(row['accuracy'])} at an estimated {usd(1000 * row['cost'] / questions)} "
            "per 1,000 questions."
            for row in others
        )
        paragraphs.append(
            f"We also ran {in_words(len(others))} cheaper models alone on the same {count(questions)} questions. {alone_text} "
            "They can be good choices when their accuracy is enough for the task."
        )
    return "".join(f"<p>{text}</p>" for text in paragraphs)


def live_row(snap: Snapshot, test: dict[str, Any], detail: str) -> str:
    """One live test in block 07's table: the pair, the answers the first model kept, the pair's accuracy, the change
    against the second model alone with its interval and the loss limit, both costs and both total times."""
    fmt, plan, measured = snap.fmt, test["plan"], test["measured"]
    questions, limit = plan["held_out"], plan["tolerance_points"]
    together, alone_cost = 1000 * measured["cost_usd"] / questions, 1000 * measured["frontier_cost_usd"] / questions
    if -100 * measured["difference"] > limit:
        loss = "Observed loss above the chosen limit."
    elif -100 * measured["low"] > limit:
        loss = "Observed change within the chosen limit. The 95% interval still allows a larger loss."
    else:
        loss = "The whole 95% interval stays within the chosen limit."
    return (
        "<tr>"
        f'<td class="setup" data-label="Model or model pair"><span class="model-name">{esc(live_name(snap, test["decision"]))}, then '
        f'{esc(live_name(snap, test["frontier"]))}</span><span class="small">{detail}</span></td>'
        f'<td class="num" data-label="Final answers supplied by the first model">{count(plan["routed"])} of {count(questions)}'
        f'<span class="small">{fmt.pct(plan["routed"] / questions)}</span></td>'
        f'<td class="num" data-label="Correct answers">{pct2(measured["accuracy"])}<span class="small">With new answers from the '
        f'second model</span><span class="small">Replay of recorded answers from both models: {pct2(plan["simulated"]["accuracy"])}</span></td>'
        f'<td class="num" data-label="Accuracy change compared with the second model alone">{change_text(measured["difference"])}'
        f'<span class="small">95% interval: {interval_points(measured["low"], measured["high"])}</span>'
        f'<span class="small">Accuracy loss allowed before the test: {limit:g} points. {loss}</span></td>'
        f'<td class="num" data-label="Estimated cost per 1,000 questions">Combined cost {usd(together)}'
        f'<span class="small">Second model alone: {usd(alone_cost)}</span>'
        f'<span class="small">Saving: {fmt.pct(saving(measured))}</span></td>'
        f'<td class="num" data-label="Total time for this test">Combined process: {measured["request_seconds"] / 60:.1f} min'
        f'<span class="small">Second model alone: {measured["frontier_request_seconds"] / 60:.1f} min</span></td>'
        "</tr>"
    )


def cost_table(snap: Snapshot) -> str:
    """Block 07's table, a heading row before each group: each second model alone, then Decider v1.1 in front of it with
    each rule; the earlier tests with Decider v1; the cheaper models run alone, against GPT-6 Astra alone. Every cost
    cell names both of its values."""
    tests, questions = live_tests(snap), snap.plan["held_out"]
    rows = []

    def heading(text: str) -> None:
        rows.append(f'<tr class="group-row"><th scope="rowgroup" colspan="6">{text}</th></tr>')

    for rules in tests["decider"].values():
        some = rules["half"]
        frontier, measured = some["frontier"], some["measured"]
        heading(f"In front of {esc(named(frontier))}")
        rows.append(
            "<tr>"
            f'<td class="setup" data-label="Model or model pair"><span class="model-name">{esc(alone(frontier))}</span></td>'
            '<td class="num" data-label="Final answers supplied by the first model">Not applicable</td>'
            f'<td class="num" data-label="Correct answers">{pct2(measured["frontier_accuracy"])}</td>'
            '<td class="num" data-label="Accuracy change compared with the second model alone">Not applicable</td>'
            f'<td class="num" data-label="Estimated cost per 1,000 questions">{usd(1000 * measured["frontier_cost_usd"] / questions)}</td>'
            f'<td class="num" data-label="Total time for this test">{measured["frontier_request_seconds"] / 60:.1f} min</td>'
            "</tr>"
        )
        for rule, test in rules.items():
            rows.append(live_row(snap, test, f"{LIVE_RULES[rule]}: confidence cutoff {cutoff_text(test['plan']['threshold'])}"))
    heading(f"Earlier tests with {esc(named(tests['earlier'][0]['decision']))}")
    for test in tests["earlier"]:
        rows.append(live_row(snap, test, f"{LIVE_RULES['half']}: confidence cutoff {cutoff_text(test['plan']['threshold'])}"))
    reference = snap.costs[0]
    reference_name = esc(named(reference["runs"][0]))
    heading(f"Cheaper models alone on the same questions, against {reference_name} alone")
    for row in snap.costs[2:]:
        versus = row["versus"]
        rows.append(
            "<tr>"
            f'<td class="setup" data-label="Model or model pair"><span class="model-name">{esc(row["label"])}</span></td>'
            '<td class="num" data-label="Final answers supplied by the first model">Not applicable</td>'
            f'<td class="num" data-label="Correct answers">{pct2(row["accuracy"])}</td>'
            f'<td class="num" data-label="Accuracy change compared with the second model alone">{change_text(versus["difference"])}'
            f'<span class="small">compared with {reference_name} alone; 95% interval: {interval_points(versus["low"], versus["high"])}</span></td>'
            f'<td class="num" data-label="Estimated cost per 1,000 questions">{usd(1000 * row["cost"] / questions)}'
            f'<span class="small">{reference_name} alone: {usd(1000 * reference["cost"] / questions)}</span></td>'
            f'<td class="num" data-label="Total time for this test">{row["seconds"] / 60:.1f} min</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards costs">'
        f"<caption>Live tests on {count(questions)} questions reserved for testing</caption>"
        '<thead><tr><th scope="col">Model or model pair</th><th scope="col" class="num">Final answers supplied by the first model</th>'
        '<th scope="col" class="num">Correct answers</th><th scope="col" class="num">Accuracy change compared with the second model alone</th>'
        '<th scope="col" class="num">Estimated cost per 1,000 questions</th><th scope="col" class="num">Total time for this test</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def cost_summary(snap: Snapshot) -> str:
    """Each comparison of block 07 with its observed accuracy change, 95% interval and exact McNemar p-value."""
    tests, questions = live_tests(snap), snap.plan["held_out"]
    items = []
    for test in decider_tests(snap) + tests["earlier"]:
        measured = test["measured"]
        items.append(
            f"{esc(live_name(snap, test['decision']))}, then {esc(named(test['frontier']))}, "
            f"{LIVE_RULES[test['plan']['rule']].lower()}, against {esc(named(test['frontier']))} alone: "
            f"{change_text(measured['difference'])} (95% interval {interval_points(measured['low'], measured['high'])}; "
            f"exact McNemar test, {esc(p_text(measured['p']))})."
        )
    reference = named(snap.costs[0]["runs"][0])
    for row in snap.costs[2:]:
        versus = row["versus"]
        items.append(
            f"{esc(row['label'])} against {esc(reference)} alone: {change_text(versus['difference'])} (95% interval "
            f"{interval_points(versus['low'], versus['high'])}; exact McNemar test, {esc(p_text(versus['p']))})."
        )
    return f"<p>On the {count(questions)} questions reserved for testing:</p><ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def rate_text(rate: float) -> str:
    """A price per million tokens, with the decimals it was listed with: $4, $0.20, $0.075."""
    text = f"{rate:.3f}".rstrip("0")
    if text.endswith("."):
        return f"${text[:-1]}"
    return f"${text}" if len(text.split(".")[1]) > 1 else f"${rate:.2f}"


# The token kinds of a price, as part 5 of the brief names them, in the order the pricing pattern lists them.
RATE_NAMES = (
    ("input_tokens", "input"),
    ("cached_input_tokens", "reused input"),
    ("cache_write_input_tokens", "saving input for reuse"),
    ("cache_write_1h_input_tokens", "saving input for reuse for one hour"),
    ("output_tokens", "output"),
)


def price_sentence(snap: Snapshot, run: dict[str, Any]) -> str:
    """Part 5's pricing pattern for one run: the date, then the rate of each kind of token the run used, then the source."""
    if run["billing"] == "free":
        return "Free tier used; no paid rate in this record."
    if run["billing"] == "local":
        return "No dollar estimate; see hardware and time."
    price = snap.price(run)
    if price is None:
        return "Not published."
    rates = "; ".join(f"{name} {rate_text(price['rates'][key])}" for key, name in RATE_NAMES
                      if key == "input_tokens" or key == "output_tokens" or run.get(key))
    change = f" Price note: {esc(price['change'])}." if price.get("change") else ""
    return (f"Prices recorded {long_date(price['date'])}. Per one million tokens: {rates}. "
            f'Source: <a href="{esc(price["source"])}">{esc(price["basis"])}</a>.{change}')


def cost_setup(snap: Snapshot) -> str:
    """How we called each model in block 07, how we estimated its cost, its requests and its prices."""
    seen: dict[int, dict[str, Any]] = {}
    for test in decider_tests(snap) + live_tests(snap)["earlier"]:
        for run in (test["decision"], test["frontier"]):
            seen.setdefault(run["run"], run)
    for row in snap.costs[2:]:
        seen.setdefault(row["runs"][0]["run"], row["runs"][0])
    items = []
    for run in seen.values():
        billing = snap.billing(run)
        per_request = run["questions_per_request"]
        requests = (f"{opening_count(per_request)} question{'s' if per_request != 1 else ''} per request, "
                    + ("one request at a time" if run["concurrency"] == 1 else f"{run['concurrency']} simultaneous requests"))
        items.append(
            f"<li><b>{esc(named(run))}.</b> How we called the model: {esc(run['access'])} ({esc(billing['access'])}). "
            f"{requests}. {esc(billing['cost_basis'])}. {price_sentence(snap, run)}</li>"
        )
    return (
        "<ul>" + "".join(items) + "</ul>"
        '<p class="note">A service may save input so a later call can reuse it. It may charge one rate to save it and another '
        "to read it again.</p>"
    )


def timed_alone(run: dict[str, Any]) -> bool:
    """Whether the run timed its own requests with one question per request, as the page's latency examples need."""
    return run["questions_per_request"] == 1 and (run["latency"] or {}).get("source") == "run"


def time_text(value: float) -> str:
    """A response time: milliseconds below one second, seconds from one second."""
    return f"{1000 * value:.0f} ms" if value < 1 else f"{value:.2f} s"


def typical_text(latency: dict[str, Any]) -> str:
    text = f"Typical {time_text(latency['median_request_seconds'])}"
    return text if latency.get("p90_request_seconds") is None else f"{text}; 9 in 10 within {time_text(latency['p90_request_seconds'])}"


def numbers_text(numbers: list[int]) -> str:
    """'2 to 5' for consecutive numbers, else '2, 4 and 5'."""
    if len(numbers) > 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"{numbers[0]} to {numbers[-1]}"
    return and_list([str(number) for number in numbers])


def latency_cell(run: dict[str, Any]) -> str:
    """Part 4's time cell: typical and 9 in 10 within, then the questions in each request (a request of several
    questions is timed whole, never divided among them), where the times come from and the simultaneous requests. A
    setup also timed with one question per request adds that separate test."""
    latency = run["latency"]
    if latency is None:
        return "Not measured"
    per_request = run["questions_per_request"]
    notes = ["One question per request." if per_request == 1
             else f"One request contains {count(per_request)} questions; the time covers the whole request."]
    if latency["source"] == "repeats":
        notes.append(f"Times from repeats {numbers_text(latency['repeats'])} of the same setup.")
    elif latency["source"] == "sample":
        notes.append(f"Times from {in_words(len(latency['runs']))} runs of the same {count(latency['questions'])} questions.")
    else:
        notes.append("Main run.")
    concurrency = latency["concurrency"]
    if concurrency is not None:
        notes.append("One request at a time." if concurrency == 1 else f"{concurrency} simultaneous requests.")
    text = f'{typical_text(latency)}<span class="small">{esc(" ".join(notes))}</span>'
    single = run["single_question_latency"]
    if single:
        text += (f'<span class="small">Separate test: one question per request, {count(single["questions"])} questions. '
                 f'{typical_text(single)}.</span>')
    return text


def cost_cell(snap: Snapshot, run: dict[str, Any]) -> str:
    """The estimated cost per 1,000 questions with how we estimated it; free and own-hardware runs say why there is none."""
    basis = esc(snap.billing(run)["cost_basis"])
    cost = per_thousand(run)
    if cost is None:
        hardware = f'<span class="small">Hardware we used: {esc(run["hardware"])}</span>' if run.get("hardware") else ""
        return f'{basis}{hardware}'
    price = snap.price(run)
    tip = ""
    if price:
        tip = (f' title="{esc(price["basis"])}, recorded {long_date(price["date"])}. Rate per million tokens: input '
               f'{rate_text(price["rates"]["input_tokens"])}; output {rate_text(price["rates"]["output_tokens"])}. Actual invoice not checked."')
    return f'<span{tip}>{usd(cost)}</span><span class="small">{basis}</span>'


def latency_table(snap: Snapshot) -> str:
    """Block 08's table: single setups side by side on all scored questions, decision models first: correct answers,
    estimated cost per 1,000 questions, response time and the answers kept at the cutoff; then which setups have no
    request times."""
    fmt = snap.fmt
    shown = [pick(snap.runs, spec, "latency_rows") for spec in snap.config["latency_rows"]]
    groups: dict[bool, list[str]] = {True: [], False: []}
    for run in shown:
        assert run is not None
        sure = (run.get("confidence") or {}).get("sure") or {"questions": 0, "correct": 0}
        kept = sure["questions"]
        kept_cell = (f'{count(kept)}<span class="small">{fmt.pct(kept / snap.total)} of questions; {count(kept - sure["correct"])} wrong</span>'
                     if kept else '0<span class="small">No answers reach this cutoff</span>')
        groups[snap.decision_model(run)].append(
            "<tr>"
            f'<td data-label="Model and setup">{label_html(run)}</td>'
            f'<td class="num" data-label="Correct answers, all {count(snap.total)} questions">{fmt.pct(run["correct"] / snap.total)}</td>'
            f'<td class="num" data-label="Estimated cost per 1,000 questions">{cost_cell(snap, run)}</td>'
            f'<td class="num" data-label="Response time per request: typical; 9 in 10 within">{latency_cell(run)}</td>'
            f'<td class="num" data-label="Answers kept at {snap.cutoff} confidence or higher">{kept_cell}</td>'
            "</tr>"
        )
    untimed = [run for run in snap.runs if run["latency"] is None]
    notes = []
    if any(run["latency"] and run["latency"]["source"] != "run" for run in shown):
        notes.append("Where the original run has no request times, we use later runs of the same setup and say which runs "
                     "supplied them.")
    if untimed:
        notes.append(f"{and_list([named(run) for run in untimed])} still {'has' if len(untimed) == 1 else 'have'} no recorded "
                     "request times.")
    # The live test covers only its reserved questions, so the same setup costs a little differently there; one example
    # tells phone readers, who see the two tables as cards, why.
    reference = snap.costs[0]
    there, here = 1000 * reference["cost"] / snap.plan["held_out"], per_thousand(reference["runs"][0])
    if all(run is not reference["runs"][0] for run in shown) or here is None or abs(here / there - 1) > 0.25:
        raise ValueError("the scope sentence of the cost and response time table no longer fits the data")
    scope = (f"This table uses all {count(snap.total)} scored questions. The live test used {count(snap.plan['held_out'])} "
             f"questions, so its cost estimates differ slightly: {esc(reference['runs'][0]['name'])} costs an estimated "
             f"{usd(here)} per 1,000 questions here and {usd(there)} in that test.")
    body = "".join(
        f'<tr class="group-row"><th scope="colgroup" colspan="5">{title}</th></tr>' + "".join(groups[key])
        for key, title in ((True, "Decision models"), (False, "Chat models for comparison")) if groups[key]
    )
    return (
        f'<h3 id="accuracy-cost-latency">Cost and response time for each model</h3><p>{scope}</p>'
        '<div class="table-wrap"><table class="overview cards latency"><thead><tr><th scope="col">Model and setup</th>'
        f'<th scope="col" class="num">Correct answers<span class="small">all {count(snap.total)} questions</span></th>'
        '<th scope="col" class="num">Estimated cost per 1,000 questions</th>'
        '<th scope="col" class="num">Response time per request<span class="small">typical; 9 in 10 within</span></th>'
        f'<th scope="col" class="num">Answers kept at {snap.cutoff} confidence or higher<span class="small">share of questions; wrong among them</span></th>'
        f'</tr></thead><tbody>{body}</tbody></table></div>'
        + (f'<p class="note">{" ".join(notes)}</p>' if notes else "")
    )


# ---------------------------------------------------------------- the overview sections (blocks 04 to 09)


def overview_values(snap: Snapshot) -> dict[str, str]:
    """Values only the overview sections (blocks 04 to 09) use."""
    return {}


def overview_blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    """Blocks only the overview sections (blocks 04 to 09) use: chart 05's full version in block 08."""
    decision = snap.named[snap.config["model_kinds"]["decision"]]
    latency, cost = decision["latency"], per_thousand(decision)
    if latency is None or cost is None or decision["questions_per_request"] != 1:
        raise ValueError("chart 05's caption needs a priced first model timed with one question per request")
    name = snap.short(decision)
    typical, within = time_text(latency["median_request_seconds"]), time_text(latency["p90_request_seconds"])
    alt = (f"Two panels: estimated cost per 1,000 questions in US dollars, and response time per request, typical and 9 in "
           f"10 within. {name} costs about {usd(cost)} per 1,000 questions and has a typical response time of {typical}. Labels "
           "show the questions in each request, the simultaneous requests and whether the times come from the main run or "
           "later tests.")
    caption = (f"<b>What does a first answer cost, and how long does it take?</b> Times describe the services and hardware "
               f"we tested. {esc(name)}'s typical response time was {typical}; 9 in 10 requests finished within {within}. "
               "The speed section times the whole two-step setup, one question at a time.")
    return {"cost-time-figure": chart_figure("cost-time-all", alt, caption)}


def per_request_text(rows: list[dict[str, Any]]) -> str:
    return " versus ".join(str(row["run"]["questions_per_request"]) for row in rows)


def confidence_lead(snap: Snapshot) -> str:
    """Block 04's opening after its first paragraph: what the lead keeps at the fixed cutoff, the other decision models
    of page_config.json's confidence_lead_rows, and what no wrong answers in a sample do and do not show. The build
    stops when the data no longer fits a sentence: the lead must be one model whose kept answers are all right and the
    most of any decision model with none wrong; every compared row must be a decision model that keeps answers; and the
    first compared row with none wrong must keep fewer answers and so have the wider interval."""
    fmt, cut = snap.fmt, snap.cutoff
    if len(snap.lead) != 1:
        raise ValueError("block 04's opening speaks for one lead model")
    lead = snap.lead[0]
    clean = [run for run in snap.runs if snap.decision_model(run)
             and (sure := (run.get("confidence") or {}).get("sure")) and sure["questions"] and sure["questions"] == sure["correct"]]
    if not lead["accepted"] or lead["errors"] or max(clean, key=lambda run: run["confidence"]["sure"]["questions"]) is not lead["run"]:
        raise ValueError("the lead no longer keeps the most answers with none wrong: block 04's opening needs new wording")
    keyed = {row["key"]: row for row in snap.thresholds if row["key"]}
    others = [(keyed[key], name) for key, name in snap.config["confidence_lead_rows"].items()]
    if any(not snap.decision_model(row["run"]) or not row["accepted"] for row, _ in others):
        raise ValueError("a model compared in block 04's opening is no longer a decision model that keeps answers")
    widest = next(((row, name) for row, name in others if not row["errors"]), None)
    if widest is None or widest[0]["accepted"] >= lead["accepted"] or widest[0]["error_range"][1] <= lead["error_range"][1]:
        raise ValueError("block 04's interval comparison no longer fits the data")
    name, kept = esc(snap.short(lead["run"])), count(lead["accepted"])

    def compared(row: dict[str, Any], label_text: str) -> str:
        errors = row["errors"]
        wrong = "also with no mistakes" if not errors else f"with {in_words(errors)} mistake{'s' if errors != 1 else ''}"
        return f"{esc(label_text)} kept {count(row['accepted'])}, {wrong}."

    return (
        f"<p>We kept {kept} of {name}'s answers, {fmt.pct(lead['coverage'])} of the questions. All {kept} were right by the "
        f"checked answer key. The other {count(lead['sent'])} questions need another answer, from another model or a person.</p>"
        f"<p>{name} kept more answers with no mistakes than any other decision model at this cutoff. "
        + " ".join(compared(row, label_text) for row, label_text in others) + "</p>"
        f"<p>No mistakes in a sample does not prove zero risk. For {name}, the 95% interval for the error rate runs from "
        f"{fmt.span(*lead['error_range'])}. For {esc(widest[1])}, it runs from {fmt.span(*widest[0]['error_range'])}. "
        f"{esc(widest[1])} kept fewer answers, so its interval is wider. A 95% interval is not a model's confidence: "
        f"{name}'s {cut} is its own score for one answer, while the 95% interval is the range our statistics give for the "
        "error rate we measured. These intervals describe sampling uncertainty under the method's assumptions. They do not "
        "promise an error limit on your next task.</p>"
    )


def accuracy_lead(snap: Snapshot) -> str:
    """Block 05's opening: the two most accurate decision models, the stronger chat models, and reading against grammar.
    The build stops when the data no longer fits a sentence: the first of page_config.json's accuracy_lead pair must be
    the most accurate decision model and share a comparison group with the second; every chat example must be a chat
    model at least ten points above every decision model; and the task comparison must hold (task_check)."""
    fmt, config = snap.fmt, snap.config["accuracy_lead"]
    first, second = (snap.named[key] for key in config["pair"])
    best = max((run for run in snap.runs if snap.decision_model(run)), key=lambda run: run["correct"])
    chats = [snap.named[key] for key in config["chat"]]
    if (best is not first or not snap.decision_model(second) or second["correct"] >= first["correct"]
            or not shares_letter(first.get("group"), second.get("group"))
            or any(snap.decision_model(run) or run["correct"] - best["correct"] < 0.1 * snap.total for run in chats)):
        raise ValueError("block 05's opening no longer matches the data: rewrite it")
    decision, chat, top = task_check(snap)

    def pct(run: dict[str, Any], part: str | None = None) -> str:
        if part is None:
            return fmt.pct(run["correct"] / snap.total)
        return fmt.pct(run["groups"][part]["correct"] / run["groups"][part]["questions"])

    gap = f"{100 * (first['correct'] - second['correct']) / snap.total:.1f}"
    gap_text = "one percentage point" if gap == "1.0" else f"{gap} percentage points"
    one, two = esc(snap.short(first)), esc(snap.short(second))
    chat_list = [f"{esc(named(run))} {'reached ' if index == 0 else ''}{pct(run)}" for index, run in enumerate(chats)]
    return (
        f"<p>On all {count(snap.total)} questions, {one} answered {pct(first)} correctly and {two} {pct(second)}. "
        f"{one}'s score was {gap_text} higher. Our test did not establish a difference between them.</p>"
        f"<p>The stronger chat models answered many more questions right: {and_list(chat_list)}. We put {two} first to keep "
        f"its most confident answers at a low cost, and a stronger model such as {esc(chats[0]['name'])} answers the rest.</p>"
        f"<p>Reading and grammar give different results. {esc(snap.short(decision))} scored {pct(decision, 'reading')} on "
        f"reading and {pct(decision, 'grammar')} on grammar. {esc(chat['name'])} scored {pct(chat, 'reading')} and "
        f"{pct(chat, 'grammar')}. So {esc(chat['name'])} beat every decision model on both, even though its grammar score was "
        f"much lower than its own reading score. {esc(top['name'])} scored {pct(top, 'reading')} and {pct(top, 'grammar')}.</p>"
    )


def model_kinds(snap: Snapshot) -> str:
    """Block 05's box 'How the models answer': the two kinds of model, why Luna through the Decisions API counts as a
    decision model, one cheap and fast decision model, one chat model's short output and what more reasoning changed.
    The build stops when an example no longer fits its sentence."""
    fmt, kinds = snap.fmt, snap.config["model_kinds"]
    decision, general, api = snap.named[kinds["decision"]], snap.named[kinds["general"]], snap.named[kinds["decisions_api"]]
    low, high = (snap.named[key] for key in kinds["reasoning"])
    # The token count includes reasoning tokens: Codex CLI reports them in its output tokens (see the method section).
    tokens = round(general["output_tokens"] / general["answered_questions"])
    cost_ratio = per_thousand(high) / per_thousand(low)

    def grammar(run: dict[str, Any]) -> float:
        return run["groups"]["grammar"]["correct"] / run["groups"]["grammar"]["questions"]

    if (not snap.decision_model(decision) or not timed_alone(decision) or decision["median_request_seconds"] >= 1
            or snap.decision_model(general) or tokens > 50 or grammar(high) <= grammar(low) or cost_ratio <= 1
            or not snap.decision_model(api) or api["provider"] != "openai-decisions"):
        raise ValueError("an example in 'How the models answer' no longer fits its sentence")
    if 1.75 <= cost_ratio < 2:
        cost = "almost doubled"
    elif 2 <= cost_ratio < 2.25:
        cost = "about doubled"
    else:
        cost = f"rose to {cost_ratio:.1f} times as much"
    return (
        '<aside class="explainer" aria-labelledby="model-kinds-title">'
        '<p class="explainer-title" id="model-kinds-title">How the models answer</p>'
        "<p>A decision model scores the options we give it. A chat model writes an answer and may reason first. We count "
        f"{esc(api['name'])} through OpenAI's Decisions API as a decision model, because that service returns a probability "
        "for each option.</p>"
        f"<p>{esc(snap.short(decision))} cost an estimated {usd(per_thousand(decision))} per 1,000 questions. Its typical "
        f"response time was {1000 * decision['median_request_seconds']:.0f} milliseconds per request in our setup. A "
        "millisecond is one thousandth of a second.</p>"
        f"<p>{esc(named(general))} used about {tokens} output tokens per question, including reported reasoning tokens. A "
        "token is a small piece of text that a model reads or writes. Output length alone does not tell us how much "
        "computation a model used or why its accuracy was higher.</p>"
        f"<p>More reasoning helped some models. {esc(low['name'])}'s grammar score rose from {fmt.pct(grammar(low))} to "
        f"{fmt.pct(grammar(high))} when we changed its reasoning setting from {esc(low['reasoning'])} to "
        f"{esc(high['reasoning'])}. Its estimated cost {cost}.</p></aside>"
    )


def reasoning_table(snap: Snapshot) -> str:
    """Each reasoning pair from page_config.json: the same model at two reasoning settings, with part 4's labels."""
    fmt = snap.fmt
    rows = []
    for pair in snap.config["reasoning_pairs"]:
        for key in pair:
            run = snap.named[key]
            per_thousand = (
                usd(1000 * run["api_equivalent_usd"] / run["answered_questions"])
                if run.get("api_equivalent_usd") is not None
                else "No dollar estimate; see hardware and time"
            )
            in_flight = f", {run['concurrency']} simultaneous requests" if run["concurrency"] > 1 else ""
            grammar = run["groups"]["grammar"]
            reasoning = reasoning_label(run["reasoning"]) if run["reasoning"] else "Not applicable"
            rows.append(
                f"<tr><td>{esc(run['name'])}</td><td>{esc(reasoning[0].upper() + reasoning[1:])}</td>"
                f'<td class="num">{fmt.pct(run["correct"] / snap.total)}</td><td class="num">{fmt.pct(grammar["correct"] / grammar["questions"])}</td>'
                f'<td class="num">{count(round(run["output_tokens"] / run["answered_questions"]))}</td><td class="num">{per_thousand}</td>'
                f'<td class="num">{minutes(run["request_seconds"])} min{in_flight}</td></tr>'
            )
    return (
        '<div class="table-wrap"><table class="static"><thead><tr><th scope="col">Model and setup</th><th scope="col">Reasoning setting</th>'
        '<th scope="col" class="num">Correct answers overall</th><th scope="col" class="num">Grammar accuracy</th>'
        '<th scope="col" class="num">Output tokens per question</th><th scope="col" class="num">Estimated cost per 1,000 questions in US dollars</th>'
        f'<th scope="col" class="num">Total time for this test</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


# ---------------------------------------------------------------- the full study up to its confidence sections (blocks 10 to 22)


# The calibration chart leaves out confidence groups with fewer answers than this: the chart renderer's MIN_BIN_ANSWERS.
STUDY_CALIBRATION_MIN = 20


def study_share(snap: Snapshot, run: dict[str, Any], group: str) -> float:
    item = run["groups"][group]
    return item["correct"] / item["questions"]


def study_range_text(low: float, high: float) -> str:
    """A confidence group's range as the page reads it: '50% to below 60%'."""
    return f"{cutoff_text(low)} to below {cutoff_text(high)}"


def study_checks(snap: Snapshot) -> None:
    """The claims the study's copy makes in words; the build stops when the data no longer supports one of them."""
    named, total = snap.named, snap.total
    decision = [run for run in snap.runs if snap.decision_model(run)]
    gemma = named["gemma"]
    for group in ("reading", "grammar"):
        best = max(study_share(snap, run, group) for run in decision)
        if study_share(snap, gemma, group) <= best:
            raise ValueError(f"the study says Gemma beats every decision model on {group}; it does not")
    if max(decision, key=lambda run: run["correct"]) is not named["glide"]:
        raise ValueError("the study says GLiDE has the highest accuracy among the decision models")
    if max(decision, key=lambda run: run["confidence"]["auroc"]) is not named["decider_v11"]:
        raise ValueError("the study says Decider v1.1 has the highest ranking score among the decision models")
    if min(decision, key=lambda run: run["confidence"]["ece"]) is not named["luna_api"]:
        raise ValueError("the study says Luna through the Decisions API has the smallest calibration gap among the decision models")
    top = sorted(snap.runs, key=lambda run: -run["correct"])[:3]
    if [run["run"] for run in top] != [named[key]["run"] for key in ("gemini_high", "astra", "sol")]:
        raise ValueError("the study names Gemini 3.8 Flash (high), Astra and Sol as the three highest scores")
    by_runs = {(item["first"], item["second"]): item for item in snap.results["paired"]}
    for first, second in (("gemini_high", "astra"), ("glide", "decider_v11")):
        item = by_runs[(named[first]["run"], named[second]["run"])]
        if item["p_holm_all"] < ALPHA:
            raise ValueError(f"the study says the test over all pairs did not establish a difference between {first} and {second}")
    deepseek = named["deepseek_on"]["confidence"]["sure"]
    if deepseek["questions"] != total:
        raise ValueError("the study says DeepSeek with reasoning scores every answer letter at 99% or more")
    if named["decider_v11"]["confidence"]["sure"]["correct"] != named["decider_v11"]["confidence"]["sure"]["questions"]:
        raise ValueError("the study says Decider v1.1 got every answer at 99% or more right")


def study_values(snap: Snapshot) -> dict[str, str]:
    """Values only the full study's sections up to its confidence sections (blocks 10 to 22) use, all study_*."""
    study_checks(snap)
    results, fmt, named = snap.results, snap.fmt, snap.named
    reading = snap.config["reading_units"]
    units = [unit["number"] for unit in results["units"]]
    grammar = [number for number in units if number not in reading]
    splits = {item["held_out"]["splits"] for item in results["cascades"]}
    if len(splits) != 1:
        raise ValueError(f"the replays use different numbers of test splits: {sorted(splits)}")
    out = {
        "study_units": count(len(units)),
        "study_reading_units": f"{min(reading)} to {max(reading)}",
        "study_grammar_units": f"{min(grammar)} to {max(grammar)}",
        "study_splits": count(splits.pop()),
        "study_excluded": count(results["excluded"]["excluded"]),
        "study_calibration_min": count(STUDY_CALIBRATION_MIN),
        "study_glide_times": times(per_thousand(named["glide"]) / per_thousand(named["decider_v11"])),
        "study_repeats": in_words(len(snap.repeats_by_key["decider_v11"]["runs"])),
        "study_confidence_groups": OPENING_WORDS[len(named["decider_v11"]["confidence"]["reliability"])].lower(),
        "study_coverage_first": f"{100 * results['coverages'][0]:.0f}%",
        "study_coverage_rest": and_list([f"{100 * share:.0f}%" for share in results["coverages"][1:]]),
    }
    # The live tests with new second model calls: the limit set before them, the tests whose observed loss went beyond
    # it and the tests whose 95% interval allows a larger loss.
    measured = [item for item in results["pipelines"] if item.get("measured")]
    tolerances = {item["tolerance_points"] for item in measured}
    if len(tolerances) != 1:
        raise ValueError(f"the live tests set different accuracy limits: {sorted(tolerances)}")
    limit = tolerances.pop()
    out["study_live_tolerance"] = f"{limit:g}"
    beyond = sum(1 for item in measured if -100 * item["measured"]["difference"] > limit)
    open_ended = sum(1 for item in measured if -100 * item["measured"]["low"] > limit)
    if not beyond:
        raise ValueError("the study says the observed loss went beyond the limit in some live tests")
    out["study_live_beyond"] = f"{in_words(beyond)} test{'s' if beyond != 1 else ''}"
    out["study_live_open"] = "every test" if open_ended == len(measured) else f"{in_words(open_ended)} of the {in_words(len(measured))} tests"
    established = [item for item in measured if item["measured"]["p"] < 0.05]

    def described(item: dict[str, Any]) -> str:
        request = ", one question per request" if item["batch_size"] == 1 else ""
        return (f"{live_name(snap, snap.by_id[item['decision']])}, then {live_name(snap, snap.by_id[item['frontier']])}{request}, "
                f"with accuracy {change_text(item['measured']['difference'])}")

    out["study_live_established"] = (
        "No test established a change in accuracy." if not established else
        f"{opening_count(len(established))} test{'s' if len(established) != 1 else ''} established a change in accuracy: "
        + and_list([described(item) for item in established]) + "."
    )
    # Uncertainty (entropy) against the stronger models' mistakes: the share of those mistakes in the most uncertain
    # tenth, over the decision models, and what a random tenth of the questions would hold on average.
    found = [item["top_tenth"]["with_mistake"] / item["top_tenth"]["all_with_mistake"] for item in results["doubts"]]
    out["study_doubt_found"] = f"{fmt.pct(min(found), 0)} to {fmt.pct(max(found), 0)}"
    tenth = results["doubts"][0]["top_tenth"]["questions"] / snap.total
    out["study_doubt_random"] = fmt.pct(tenth, 0)
    aurocs = [item["auroc"] for item in results["doubts"]]
    out["study_doubt_auroc"] = f"{min(aurocs):.2f} to {max(aurocs):.2f}"
    # Open Jev's 50% to 60% confidence group: more right than its confidence says.
    group = next(item for item in named["open_jev"]["confidence"]["reliability"] if item["low"] == 0.5)
    out["study_open_jev_range"] = study_range_text(group["low"], group["high"])
    out["study_open_jev_group"] = count(group["questions"])
    out["study_open_jev_group_correct"] = count(round(group["accuracy"] * group["questions"]))
    # 99% or more from an answer letter probability (Gemma) and from agreement across ten answers (Qwen).
    for key in ("gemma", "qwen_votes", "deepseek_on"):
        sure = named[key]["confidence"]["sure"]
        out[f"study_{key}_sure_kept"] = count(sure["questions"])
        out[f"study_{key}_sure_correct"] = count(sure["correct"])
        out[f"study_{key}_sure_accuracy"] = fmt.pct(sure["correct"] / sure["questions"], 0)
    # Four confidence sources on one fixed set of Qwen answers.
    keys = {run["run"]: key for key, run in named.items()}
    fixed = results["sources"][0]
    out["study_sources_correct"] = count(fixed["correct"])
    out["study_sources_questions"] = count(fixed["questions"])
    for item in fixed["sources"]:
        out[f"study_source_{keys[item['run']]}_auroc"] = f"{item['auroc']:.2f}"
    # Prices: the date most rates were recorded, and the dated exceptions the copy names.
    dates = [price["date"] for price in results["prices"]]
    out["study_price_date"] = long_date(max(set(dates), key=dates.count))
    for key in ("decider_v1", "decider_v11", "celeris", "gemini_low"):
        price = snap.price(named[key])
        assert price is not None
        out[f"study_price_{key}"] = f"${price['rates']['input_tokens']:.2f}"
        out[f"study_price_{key}_date"] = long_date(price["date"])
        if price["change"]:
            out[f"study_price_{key}_change"] = price["change"]
    return out


def study_alt_scores(snap: Snapshot, keys: tuple[str, ...]) -> str:
    named = snap.named
    return "; ".join(
        f"{named[key]['name']} {snap.fmt.pct(study_share(snap, named[key], 'reading'))} and {snap.fmt.pct(study_share(snap, named[key], 'grammar'))}"
        for key in keys
    )


def study_blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    """Blocks only the full study's sections up to its confidence sections (blocks 10 to 22) use: their chart figures,
    with part 6's titles, captions and accessible descriptions, numbers from the snapshot."""
    named, results = snap.named, snap.results
    reading_units = snap.config["reading_units"]
    units = len(results["units"])
    shares = and_list([f"{100 * share:.0f}%" for share in results["coverages"]])
    fixed = results["sources"][0]
    keys = {run["run"]: key for key, run in named.items()}
    source_auroc = {keys[item["run"]]: f"{item['auroc']:.2f}" for item in fixed["sources"]}
    calibration = (
        "Each point groups answers with similar confidence. Its position across gives their average confidence; its height "
        "gives how many of them were right. The diagonal shows where confidence matches accuracy. Points below it show "
        "confidence higher than the real hit rate; points above it show confidence lower than the real hit rate. The chart "
        f"leaves out groups with fewer than {STUDY_CALIBRATION_MIN} "
        "answers; the table keeps them."
    )
    calibration_caption = (
        "A point on the diagonal means the average confidence matches the hit rate in that group. Points below it show "
        "confidence that was too high; points above it show confidence that was too low. Groups with fewer than "
        f"{STUDY_CALIBRATION_MIN} answers are left out of the chart; "
        "the table above keeps them."
    )
    return {
        "study-reading-grammar": chart_figure(
            "reading-grammar",
            "Chart: How often do models get reading and grammar questions right? Reading and grammar accuracy, with "
            f"decision models above chat models for comparison. {study_alt_scores(snap, ('decider_v11', 'glide', 'gemma', 'astra'))}. "
            f"Reading has {count(snap.reading_questions)} questions and grammar {count(snap.grammar_questions)}. "
            "The gap does not show its cause.",
            "Gemma scores higher than every decision model in both categories. Its grammar score is lower than its own "
            "reading score. This test does not show why the two scores differ.",
        ),
        "study-cascade": chart_figure(
            "cascade",
            "Chart: What happens as we keep more answers from the first model? Curves show the accuracy of the combined "
            "answers as the first model gives more of the final answers, with Astra, Opus and Sonnet as the second model. "
            "A reference line shows the second model answering every question. These curves choose and test the cutoffs on "
            "the same recorded questions, so they differ from the averages over separate test halves above.",
            "This curve explores the same recorded questions we used to choose each cutoff. It may look better than a test "
            "on new questions. The main result above uses separate halves.",
        ),
        "study-units": chart_figure(
            "units",
            f"Chart: Which topics cause the most mistakes? Correct answers in each of the {units} topics. Topics "
            f"{min(reading_units)} to {max(reading_units)} cover reading and topics {max(reading_units) + 1} to {units} "
            "cover grammar. Each topic shows its number of questions. The table above gives the exact results for every "
            "model setup.",
            "Each topic has a different number of questions. Topic scores show where an overall average hides uneven results.",
        ),
        "study-coverage": chart_figure(
            "coverage",
            "Chart: How accurate are the answers we keep? For each model, the curve starts with its most confident answers "
            "and adds less confident ones. Across: the share of answers we keep. Up: accuracy among those answers. The "
            f"{shares} marks are shares of answers, not confidence scores.",
            "We order each model's answers by confidence, then check accuracy as we keep more of them. This measures the "
            "kept answers only. No second model answers the rest here.",
        ),
        "study-calibration": chart_figure(
            "calibration",
            f"Chart: When a model scores answers at 80%, are about 80% right? {named['decider_v11']['name']} against "
            f"{named['opus']['name']}: calibration gap {study_gap(named['decider_v11'])} against {study_gap(named['opus'])} "
            f"points. {calibration}",
            calibration_caption,
        )
        + '<details class="study-more"><summary>Show all models</summary>'
        + chart_figure(
            "calibration-all",
            f"Chart: When a model scores answers at 80%, are about 80% right? All models, each with its confidence source. {calibration}",
            calibration_caption,
        )
        + "</details>",
        "study-sources": chart_figure(
            "sources",
            "Chart: Can different scores help us judge the same answers? Four confidence sources rank the same "
            f"{named['qwen_stated']['name']} answers, {count(fixed['correct'])} right out of {count(fixed['questions'])}. "
            f"Written estimate: ranking score (AUROC) about {source_auroc['qwen_stated']}; Qwen option score about "
            f"{source_auroc['qwen_yes_no']}; agreement across ten answers about {source_auroc['qwen_votes']}; Open Jev "
            f"score about {source_auroc['open_jev']}. Open Jev is a separately trained scoring model.",
            "Only the score we use to rank the fixed answers changes. The Open Jev row also changes the model that gives "
            "the score. The ranking score (AUROC) is how often a right answer gets higher confidence than a wrong one.",
        ),
    }


def study_gap(run: dict[str, Any]) -> str:
    """A run's calibration gap (ECE) in points, one decimal."""
    return f"{100 * run['confidence']['ece']:.1f}"


# ---------------------------------------------------------------- the top of the page, the head and the images


# The page's title and the link preview's (the headline on the page is the h1 in index.html).
TITLE = "When should you trust an AI model to make a decision? · Zeki Works"
# The three LLMs the opening puts Decider in front of, by named-run key; the opening orders them by saving.
OPENING_SECONDS = ("sonnet_high", "opus", "astra")
# The speed table's rows: a named run and whether the row is its separate one-question test.
SPEED_ROWS = (("decider_v11", False), ("glide", False), ("opus", False), ("sonnet_high", False), ("astra", True), ("astra", False))


def speed_words(value: float) -> str:
    """Decider's typical response time in words: 'a quarter of a second' while it is within 0.05 s of it."""
    return "a quarter of a second" if abs(value - 0.25) < 0.05 else f"{value:.2f} seconds"


def opening_seconds(snap: Snapshot) -> list[dict[str, Any]]:
    """The replay's three LLMs the opening names, by their strict-cutoff saving, largest first."""
    items = [item for item in snap.replay["frontiers"] if item["key"] in OPENING_SECONDS]
    if len(items) != len(OPENING_SECONDS) or any(item["strict"] is None for item in items):
        raise ValueError("the opening needs a strict cutoff for each of its three LLMs")
    return sorted(items, key=lambda item: -item["strict"]["saving"])


def strict_ranking(snap: Snapshot, frontier: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """The decision models in front of one LLM with the strict cutoff, by the share they take, largest first."""
    found = [(snap.by_id[item["decision"]], item) for item in snap.results["cascades"] if item["frontier"] == frontier["run"]]
    return sorted(((run, item) for run, item in found if snap.decision_model(run)), key=lambda pair: -pair[1]["held_out"]["answered"])


def top_values(snap: Snapshot) -> dict[str, str]:
    """Values only the top of the page uses: the opening and the sections before the confidence overview. Each claim
    the copy makes around them is checked here, and the build stops when the data no longer supports it."""
    fmt, decider, named = snap.fmt, snap.replay["run"], snap.named
    if decider is not named["decider_v11"]:
        raise ValueError("the opening speaks of Decider v1.1, but the replay leads with another run")
    seconds_list = opening_seconds(snap)
    out = {}
    latency = decider["latency"]
    out["decider_speed_words"] = speed_words(latency["median_request_seconds"])
    splits = {item["held_out"]["splits"] for item in snap.results["cascades"]}
    if len(splits) != 1:
        raise ValueError("the routing simulations use different numbers of splits")
    out["splits"] = count(splits.pop())
    out["decider_v11_accuracy_whole"] = fmt.pct(decider["correct"] / snap.total, 0)
    chat = max((run for run in snap.runs if not snap.decision_model(run)), key=lambda run: run["correct"])
    out["best_chat_accuracy_whole"] = fmt.pct(chat["correct"] / snap.total, 0)

    # "Decider v1.1 took the most questions off each LLM; GLiDE came second each time; accuracy fell in front of each."
    for item in seconds_list:
        ranking = strict_ranking(snap, item["run"])
        if ranking[0][0] is not decider or ranking[1][0] is not named["glide"]:
            raise ValueError(f"Decider v1.1 and GLiDE no longer lead the decision models in front of {label(item['run'])}")
    losses = [-item["strict"]["difference"] for item in seconds_list]
    if min(losses) <= 0:
        raise ValueError("the opening says accuracy fell in front of every LLM")

    # Why Decider v1.1: the most confident-and-right answers, the best ranking, no changed answers, the step from v1.
    clean = sorted(
        (run for run in snap.runs if snap.decision_model(run) and (sure := (run.get("confidence") or {}).get("sure"))
         and sure["questions"] and sure["questions"] == sure["correct"]),
        key=lambda run: -run["confidence"]["sure"]["questions"],
    )
    if clean[0] is not decider or len(clean) < 3:
        raise ValueError("Decider v1.1 no longer keeps the most answers with no mistakes at 99%")
    out["why_sure_others"] = and_list([f"{count(run['confidence']['sure']['questions'])} ({snap.short(run)})" for run in clean[1:3]])
    decision_aurocs = [run["confidence"]["auroc"] for run in snap.runs if snap.decision_model(run) and run.get("confidence")]
    if decider["confidence"]["auroc"] < max(decision_aurocs):
        raise ValueError("Decider v1.1 no longer has the highest ranking score of the decision models")
    repeats = snap.repeats_by_key["decider_v11"]
    if repeats["changed_answer"]:
        raise ValueError("the copy says Decider v1.1 never changed an answer across its repeats")
    out["decider_v11_repeat_runs"] = in_words(len(repeats["runs"]))
    v1 = named["decider_v1"]
    out["v11_gain"] = f"{100 * (decider['correct'] - v1['correct']) / snap.total:.1f}"
    out["v11_sure_ratio"] = times(decider["confidence"]["sure"]["questions"] / v1["confidence"]["sure"]["questions"])
    cost_ratio = per_thousand(decider) / per_thousand(v1)
    v1_price, v11_price = snap.price(v1)["rates"]["input_tokens"], snap.price(decider)["rates"]["input_tokens"]
    if not 0.45 <= cost_ratio <= 0.55 or not v11_price < v1_price:
        raise ValueError("the copy says Decider v1.1 costs half as much as v1 because Perplexity cut its price")
    # GLiDE comes close: in front of Opus it takes less of the work and loses less accuracy.
    glide_opus = next(item for run, item in strict_ranking(snap, named["opus"]) if run is named["glide"])
    opus_strict = next(item for item in snap.replay["frontiers"] if item["key"] == "opus")["strict"]
    if not (glide_opus["held_out"]["answered"] < opus_strict["share"] and -glide_opus["held_out"]["difference"] < -opus_strict["difference"]):
        raise ValueError("the copy says GLiDE takes less of Opus's work than Decider but loses less accuracy")
    out["glide_opus_loss"] = f"{-100 * glide_opus['held_out']['difference']:.2f}"
    out["decider_opus_loss"] = f"{-100 * opus_strict['difference']:.2f}"

    # Speed: GLiDE ran several requests at a time, the others one; sample timings.
    timed = [named[key] for key, _ in SPEED_ROWS]
    if any(run["latency"]["concurrency"] != 1 for run in timed if run is not named["glide"]):
        raise ValueError("the speed section says every model but GLiDE ran one request at a time")
    sampled = {(len(named[key]["latency"]["runs"]), named[key]["latency"]["questions"]) for key in ("opus", "sonnet_high", "astra")}
    if len(sampled) != 1 or any(named[key]["latency"]["source"] != "sample" for key in ("opus", "sonnet_high", "astra")):
        raise ValueError("the speed section says Opus, Sonnet and Astra were timed on the same sample runs")
    (runs, questions), = sampled
    out["speed_sample_runs"], out["speed_sample_questions"] = in_words(runs), count(questions)
    if named["astra"]["single_question_latency"]["questions"] != questions:
        raise ValueError("the speed section says Astra's one-question test used the same questions")

    # Savings: the most confident quarter on halves; the opening's live test, with the cutoff chosen on half the questions.
    sonnet = next(item for item in snap.replay["frontiers"] if item["key"] == "sonnet_high")
    better = sonnet["share"]["held_out"]["better"]
    out["sonnet_high_surest_held_words"] = "every time" if better == 1 else f"in {fmt.pct(better, 0)} of them"
    halves = {key: rules["half"] for key, rules in live_tests(snap)["decider"].items()}
    replayed = {item["key"]: item["strict"]["saving"] for item in snap.replay["frontiers"] if item["strict"]}
    if any(saving(test["measured"]) >= replayed[key] for key, test in halves.items()):
        raise ValueError("the opening says the live test's estimated cost fell by less than the replay's")
    if max(test["measured"]["difference"] for test in halves.values()) > 0 or min(test["measured"]["p"] for test in halves.values()) < 0.05:
        raise ValueError("the opening says accuracy fell by at most the largest loss and no live test established a change")
    for key, test in halves.items():
        out[f"live_{key}_saving_whole"] = fmt.pct(saving(test["measured"]), 0)
    out["live_questions"] = count(snap.plan["held_out"])
    out["live_most_lost"] = f"{-100 * min(test['measured']['difference'] for test in halves.values()):.2f}"
    # The savings note: in how many live tests the saving was smaller than the replay's for the same LLM and rule.
    rules_replayed = replay_rules(snap)
    every = [(key, rule, test) for key, rules in live_tests(snap)["decider"].items() for rule, test in rules.items()]
    smaller = sum(1 for key, rule, test in every if saving(test["measured"]) < rules_replayed[key][rule]["saving"])
    if not smaller:
        raise ValueError("the savings note says some live savings were smaller than the replay's")
    out["live_smaller"] = f"all {in_words(len(every))}" if smaller == len(every) else f"{in_words(smaller)} of the {in_words(len(every))}"
    # The opening's pointer to the timed test: an accuracy change that test established, with the LLM alone more accurate
    # there than with batched requests (the case the sentence describes).
    one = [(key, test) for key, test in live_tests(snap)["timed"].items() if test["measured"]["p"] < 0.05]
    if not one:
        out["live_one_question"] = "With one question per request, no test established a change in accuracy either"
    else:
        if any(test["measured"]["difference"] > 0 or test["measured"]["frontier_accuracy"] <= halves[key]["measured"]["frontier_accuracy"]
               for key, test in one):
            raise ValueError("the opening says one question per request made the LLM alone more accurate and the pair less")
        names = and_list([live_name(snap, test["frontier"]) for _, test in one])
        fewer = and_list(["%.2f" % (-100 * test["measured"]["difference"]) for _, test in one])
        out["live_one_question"] = (f"With one question per request, {names} alone got more answers right, and with Decider first "
                                    f"{'it' if len(one) == 1 else 'they'} got {fewer} points fewer right")
    # "Why Opus and Sonnet gain more: they make more mistakes than Astra"; "Sol gets cheaper with no change in accuracy";
    # "Decider wins on speed and price" over GLiDE.
    if not (named["opus"]["correct"] < named["astra"]["correct"] and named["sonnet_high"]["correct"] < named["astra"]["correct"]):
        raise ValueError("the savings notes say Opus and Sonnet make more mistakes than Astra")
    sol = next(item for item in snap.replay["frontiers"] if item["key"] == "sol")
    if sol["sure"]["difference"] != 0:
        raise ValueError("the savings notes say Decider at 99% leaves Sol's accuracy unchanged")
    glide = named["glide"]
    if not (latency["median_request_seconds"] < glide["latency"]["median_request_seconds"] and per_thousand(decider) < per_thousand(glide)):
        raise ValueError("the copy says Decider is faster and cheaper than GLiDE")
    out["opening_opus_per_request"] = count(named["opus"]["questions_per_request"])

    def mistakes(wrong: int) -> str:
        return "no mistakes" if not wrong else f"{count(wrong)} mistake{'s' if wrong != 1 else ''}"

    for row in snap.replay["cutoffs"]:
        tag = cutoff_text(row["cutoff"]).rstrip("%").replace(".", "")
        out[f"cut_{tag}_cutoff"] = cutoff_text(row["cutoff"])
        out[f"cut_{tag}_mistakes"] = mistakes(row["wrong"])
    out["surest_mistakes"] = mistakes(snap.replay["share"]["wrong"])

    # The opening: how many decision models we tested and put in front of an LLM, what GLiDE's calls cost against
    # Decider's, how many more answers the two-step setups got wrong per 1,000 questions, and that the best decision
    # models get about two answers in three right.
    tried, untried = decision_first_models(snap)
    out["decision_models"] = count(len(tried) + len(untried))
    out["decision_models_tried"] = count(len(tried))
    out["opening_llm_count"] = in_words(len(seconds_list))
    out["glide_cost_ratio"] = times(per_thousand(named["glide"]) / per_thousand(decider))
    out["opening_more_wrong"] = f"{more_wrong_span(snap)} more answers"
    best = max(run["correct"] for run in tried + untried) / snap.total
    if not 0.6 <= best <= 0.72:
        raise ValueError("the opening says the best decision models get about two answers in three right")
    return out


def decision_first_models(snap: Snapshot) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The decision models we put in front of an LLM, and those we did not, each in results.json's order."""
    first = {item["decision"] for item in snap.results["cascades"]}
    decision = [run for run in snap.runs if snap.decision_model(run)]
    return [run for run in decision if run["run"] in first], [run for run in decision if run["run"] not in first]


# How the opening names each LLM on second mention.
OPENING_SHORT = {"sonnet_high": "Sonnet", "opus": "Opus", "astra": "Astra"}
# The opening's table shows this many decision models; a details element holds all of them.
OPENING_ROWS = 6


def opening_table(snap: Snapshot) -> str:
    """The share of the questions each decision model took off each LLM with the cutoff chosen on half the questions: one
    row per decision model we put in front of an LLM, by the Opus column, the first OPENING_ROWS shown and all of them in
    a details element, each cell shaded by its share and the lead's row marked. The caption names the decision models we
    did not put in front of an LLM; the build stops unless each got about one answer in as many as there are options."""
    fmt, items, results = snap.fmt, opening_seconds(snap), snap.results
    tried, untried = decision_first_models(snap)
    shares = {(item["decision"], item["frontier"]): item["held_out"]["answered"] for item in results["cascades"]}
    rows = sorted(tried, key=lambda run: -shares[run["run"], snap.named["opus"]["run"]])
    top = max(shares[run["run"], item["run"]["run"]] for run in rows for item in items)
    options = results["baselines"]["options"]
    if any(abs(run["correct"] / snap.total - 1 / options) > 0.05 for run in untried):
        raise ValueError("the opening's table caption says the decision models left out got about one answer in "
                         f"{options} right")
    head = "".join(
        f'<th scope="col" class="num">{esc(item["run"]["name"])}<span class="small">{esc(setting(item["run"]))}</span></th>'
        for item in items
    )

    def table(selection: list[dict[str, Any]]) -> str:
        body = []
        for run in selection:
            cells = "".join(
                f'<td class="num share" data-label="{esc(item["run"]["name"])}" style="--share: {shares[run["run"], item["run"]["run"]] / top:.3f}">'
                f'{fmt.pct(shares[run["run"], item["run"]["run"]], 0)}</td>'
                for item in items
            )
            body.append(('<tr class="lead">' if run is snap.replay["run"] else "<tr>") + f'<th scope="row">{esc(named(run))}</th>{cells}</tr>')
        return (
            '<div class="table-wrap"><table class="overview shares"><caption>Share of the questions each decision model took off '
            f'each LLM</caption><thead><tr><th scope="col">Decision model</th>{head}</tr></thead><tbody>{"".join(body)}</tbody>'
            "</table></div>"
        )

    splits = count(next(iter(results["cascades"]))["held_out"]["splits"])
    left_out = and_list([named(run) for run in untried])
    caption = (
        f"Each cell is the share of questions the decision model answered, averaged over {splits} splits: we chose the cutoff "
        "on half of the questions and checked it on the other half. We replayed recorded answers. We did not put the other "
        f"{in_words(len(untried))} decision models ({esc(left_out)}) in front of an LLM: on their own they got about one answer "
        f"in {in_words(options)} right, no better than picking one of the {in_words(options)} options at random."
    )
    return (
        table(rows[:OPENING_ROWS])
        + f'<details class="show-more"><summary>Show all {count(len(rows))}</summary>{table(rows)}</details>'
        + f'<p class="caption">{caption}</p>'
    )


def speed_table(snap: Snapshot) -> str:
    """Typical and 9-in-10 response times of Decider, GLiDE and the three LLMs, with the questions in each request."""
    rows = []
    for key, single in SPEED_ROWS:
        run = snap.named[key]
        latency = run["single_question_latency"] if single else run["latency"]
        per_request = 1 if single else run["questions_per_request"]
        note = "Separate test: one question per request" if single else ""
        rows.append(
            "<tr>"
            f'<td data-label="Model">{esc(named(run))}' + (f'<span class="small">{note}</span>' if note else "") + "</td>"
            f'<td class="num" data-label="Questions per request">{per_request}</td>'
            f'<td class="num" data-label="Typical response time">{time_text(latency["median_request_seconds"])}</td>'
            f'<td class="num" data-label="9 in 10 within">{time_text(latency["p90_request_seconds"])}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards"><thead><tr><th scope="col">Model</th>'
        '<th scope="col" class="num">Questions per request</th><th scope="col" class="num">Typical response time</th>'
        f'<th scope="col" class="num">9 in 10 within</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


# A request this long counts as a stall: the speed text names the longest, since the averages include it.
STALL_SECONDS = 60


def speed_whole(snap: Snapshot) -> str:
    """T5's timed live test: each LLM alone and with Decider v1.1 first, one question per request and one request at a
    time, on the live test's questions with the cutoff chosen on half the questions. First how the typical and the
    average wait changed, with the longest request of any run that stalled; then accuracy, which one question per request
    changed too, against the same LLM alone with 16 questions per request; then per setup each question's typical wait,
    the wait nine in ten stayed within, the average and the answers right, with Decider first also the questions it kept
    and those it passed on. The build stops unless every cutoff was chosen on recorded runs of the batched size."""
    fmt, tests = snap.fmt, live_tests(snap)
    timed, batched = tests["timed"], tests["decider"]
    questions = snap.plan["held_out"]
    me = esc(live_name(snap, next(iter(timed.values()))["decision"]))
    sizes = {snap.named[key]["questions_per_request"] for key in timed}
    if len(sizes) != 1:
        raise ValueError("the speed section says every cutoff was chosen on recorded answers to one number of questions per request")
    (size,) = sizes

    def cell(label: str, wait: dict[str, Any], right: float, parts: str = "") -> str:
        return (f'<td class="num" data-label="{label}">Typical {time_text(wait["median_seconds"])}'
                f'<span class="small">9 in 10 within {time_text(wait["p90_seconds"])}</span>'
                f'<span class="small">Average {time_text(wait["mean_seconds"])}</span>'
                f'<span class="small">Correct answers: {pct2(right)}</span>{parts}</td>')

    rows, typical, changes, stalls, accuracy, established, unchanged = [], [], [], [], [], [], []
    for key, test in timed.items():
        measured, name = test["measured"], esc(live_name(snap, test["frontier"]))
        waits = measured["waits"]
        typical.append(f"from {time_text(waits['alone']['median_seconds'])} to {time_text(waits['pipeline']['median_seconds'])} with {name}")
        changes.append((1 - waits["pipeline"]["mean_seconds"] / waits["alone"]["mean_seconds"], name))
        longest = {part: waits[part]["max_seconds"] for part in ("alone", "pipeline")}
        if max(longest.values()) > STALL_SECONDS:
            stalls.append(f"the longest request with {name} took {longest['pipeline']:.0f} seconds after {me} and "
                          f"{longest['alone']:.0f} seconds alone")
        accuracy.append((name, measured["frontier_accuracy"], batched[key]["half"]["measured"]["frontier_accuracy"]))
        if measured["p"] < 0.05:
            established.append(
                f"With {me} first, {name} got {abs(100 * measured['difference']):.2f} points {'fewer' if measured['difference'] < 0 else 'more'} "
                f"right (95% interval {interval_points(measured['low'], measured['high'])}; exact McNemar test, {esc(p_text(measured['p']))})."
            )
        else:
            unchanged.append(name)
        parts = (f'<span class="small">Kept by {me}: typical {time_text(waits["kept"]["median_seconds"])}</span>'
                 f'<span class="small">Passed on: typical {time_text(waits["passed"]["median_seconds"])}</span>')
        rows.append(
            f'<tr><td data-label="LLM">{esc(named(test["frontier"]))}</td>{cell("LLM alone", waits["alone"], measured["frontier_accuracy"])}'
            f'{cell(f"{me}, then the LLM", waits["pipeline"], measured["accuracy"], parts)}</tr>'
        )
    average = (f"{'fell' if changes[0][0] > 0 else 'rose'} " + and_list([f"{fmt.pct(abs(change), 0)} with {name}" for change, name in changes])
               if len({change > 0 for change, _ in changes}) == 1
               else and_list([f"{'fell' if change > 0 else 'rose'} {fmt.pct(abs(change), 0)} with {name}" for change, name in changes]))
    speed = (f"<p>We also timed the whole two-step setup on the live test's {count(questions)} questions, with the cutoff chosen "
             f"on half the questions: one question per request, one request at a time. {me}'s times come from its recorded run; "
             f"each LLM answered with new calls, alone and after {me}. With {me} first, the typical wait per question went "
             f"{and_list(typical)}. The average wait {average}."
             + (f" {and_list(stalls)[0].upper()}{and_list(stalls)[1:]}; the averages include such waits." if stalls else "") + "</p>")
    right = ("<p>On their own, with one question per request, "
             + and_list([f"{name} got {pct2(one)} right" for name, one, _ in accuracy])
             + f"; with {size} questions per request, " + and_list([pct2(many) for _, _, many in accuracy]) + ". "
             + " ".join(established)
             + (f" We chose every cutoff on recorded answers to {size} questions per request." if established else "")
             + (f" With {and_list(unchanged)}, the test did not establish a change in accuracy." if unchanged else "") + "</p>")
    return speed + right + (
        '<div class="table-wrap"><table class="overview cards"><caption>Wait per question, one question per request</caption>'
        f'<thead><tr><th scope="col">LLM</th><th scope="col" class="num">LLM alone</th><th scope="col" class="num">{me}, then the LLM'
        f'</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def speed_figure(snap: Snapshot) -> str:
    """Chart 05 at the top: price and response time of the speed table's models."""
    latency = snap.replay["run"]["latency"]
    parts = []
    for key, single in SPEED_ROWS:
        run = snap.named[key]
        timing = run["single_question_latency"] if single else run["latency"]
        per_request = 1 if single else run["questions_per_request"]
        cost = per_thousand(run)
        parts.append(f"{named(run)}, {per_request} question{'s' if per_request != 1 else ''} per request: "
                     f"{usd(cost) if cost is not None else 'no dollar estimate'} per 1,000 questions, typical "
                     f"{time_text(timing['median_request_seconds'])}, 9 in 10 within {time_text(timing['p90_request_seconds'])}")
    alt = ("Two panels. Left, the estimated cost per 1,000 questions in US dollars on a logarithmic scale; right, the waiting "
           "time for one request, typical and 9 in 10 within. " + "; ".join(parts) + ".")
    caption = (f"Times describe the services and hardware we tested. Decider v1.1's typical response time was "
               f"{time_text(latency['median_request_seconds'])}; 9 in 10 answers arrived within {time_text(latency['p90_request_seconds'])}. "
               "A request of 16 questions is timed as a whole. The whole two-step setup is timed above, one question at a time.")
    return chart_figure("cost-time", alt, caption)


def cutoff_rows(snap: Snapshot) -> list[dict[str, Any]]:
    """Decider's fixed cutoffs and its most confident quarter, from the highest cutoff to the lowest."""
    replay = snap.replay
    rows = [{"cut": row["cutoff"], "kept": row["kept"], "wrong": row["wrong"], "surest": False} for row in replay["cutoffs"]]
    rows.append({"cut": replay["share"]["cut"], "kept": replay["share"]["kept"], "wrong": replay["share"]["wrong"], "surest": True})
    return sorted(rows, key=lambda row: -row["cut"])


def cutoff_alt(snap: Snapshot) -> str:
    """The cutoff chart in words, for its alt text and the link preview's."""
    fmt, rows, threshold = snap.fmt, cutoff_rows(snap), snap.config["threshold"]
    rule = next(row for row in rows if row["cut"] == threshold)
    surest = next(row for row in rows if row["surest"])
    return (f"Bar chart. As the cutoff drops from {cutoff_text(rows[0]['cut'])} to {cutoff_text(rows[-1]['cut'])}, Decider v1.1 "
            f"keeps more answers, from {fmt.pct(rows[0]['kept'] / snap.total, 0)} to {fmt.pct(rows[-1]['kept'] / snap.total, 0)} of all "
            f"questions, and makes more mistakes, from {count(rows[0]['wrong'])} to {count(rows[-1]['wrong'])}. At {snap.cutoff} it "
            f"keeps {count(rule['kept'])} answers with {'no' if not rule['wrong'] else count(rule['wrong'])} mistakes. At "
            f"{cutoff_text(surest['cut'])}, its most confident quarter, it keeps {count(surest['kept'])} answers with {count(surest['wrong'])} mistakes.")


def cutoff_figure(snap: Snapshot) -> str:
    """Chart 00, the cutoff trade-off, with the table of its numbers."""
    fmt, rows, threshold = snap.fmt, cutoff_rows(snap), snap.config["threshold"]
    rule = next(row for row in rows if row["cut"] == threshold)
    surest = next(row for row in rows if row["surest"])
    caption = (f"Decider v1.1 on {count(snap.total)} Turkish exam questions; we replayed recorded answers. At {snap.cutoff} it keeps "
               f"{count(rule['kept'])} answers with {'no' if not rule['wrong'] else count(rule['wrong'])} mistakes. At "
               f"{cutoff_text(surest['cut'])}, its most confident quarter, it keeps {count(surest['kept'])} and gets {count(surest['wrong'])} wrong.")
    table_rows = []
    for row in rows:
        name = cutoff_text(row["cut"]) + (" (most confident quarter)" if row["surest"] else " (our rule)" if row["cut"] == threshold else "")
        table_rows.append(
            ("<tr class=\"lead\">" if row["cut"] == threshold or row["surest"] else "<tr>")
            + f'<td data-label="Cutoff">{name}</td><td class="num" data-label="Answers kept">{count(row["kept"])}</td>'
            f'<td class="num" data-label="Share of all questions">{fmt.pct(row["kept"] / snap.total)}</td>'
            f'<td class="num" data-label="Wrong among kept">{count(row["wrong"])}</td></tr>'
        )
    # A lower fixed cutoff that also kept only right answers reads as a better rule; say why the page does not use it.
    looser = [row for row in rows if not row["surest"] and not row["wrong"] and row["cut"] < threshold]
    note = (f"<p class=\"note\">We did not make {cutoff_text(looser[-1]['cut'])} our rule, although it kept more answers with no "
            f"mistakes: we only know that because we looked at the answers. {snap.cutoff} is a round number we set in advance.</p>"
            if looser else "")
    table = (
        '<details class="show-table"><summary>Show the numbers</summary><div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Cutoff</th><th scope="col" class="num">Answers kept</th><th scope="col" class="num">Share of '
        f'all questions</th><th scope="col" class="num">Wrong among kept</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table></div>'
        f"{note}</details>"
    )
    return chart_figure("cutoffs", cutoff_alt(snap), caption) + table


def handoff_figure(snap: Snapshot) -> str:
    """Chart 01, the handoff diagram with Opus."""
    fmt, share = snap.fmt, snap.replay["share"]
    opus = next(item for item in snap.replay["frontiers"] if item["key"] == "opus")
    kept = share["kept"] / snap.total
    decider, opus_run = snap.replay["run"], snap.named["opus"]
    alt = (f"Flow diagram. Every question goes to Decider v1.1 first. If the question is among Decider's most confident quarter, we keep "
           f"its answer. Otherwise Claude Opus 5.5 answers. Decider answers {fmt.pct(kept, 0)} of the questions and gets "
           f"{count(share['kept'] - share['wrong'])} of {count(share['kept'])} right; Opus answers {fmt.pct(1 - kept, 0)}. Decider "
           f"takes about {seconds(decider['latency']['median_request_seconds'])} seconds per question; Opus takes about "
           f"{opus_run['latency']['median_request_seconds']:.0f} seconds per request of {opus_run['questions_per_request']} questions.")
    worse = {rule: -100 * opus[rule]["difference"] for rule in ("share", "strict")}
    if min(worse.values()) <= 0:
        raise ValueError("the handoff caption says accuracy fell with both rules in front of Opus")
    caption = (f"In a separate replay, we kept Decider's most confident quarter of answers. Decider got "
               f"{count(share['kept'] - share['wrong'])} of those {count(share['kept'])} answers right, and Opus answered the rest. "
               f"The estimated combined cost fell {fmt.pct(opus['share']['saving'], 0)}, and accuracy fell {worse['share']:.2f} points. "
               "This is a different rule from the one at the top of the page, where we chose the cutoff on half the questions "
               f"and accuracy fell {worse['strict']:.2f} points on average.")
    return chart_figure("handoff", alt, caption)


def first_models_figure(snap: Snapshot) -> str:
    """Chart 02: how much of Astra's work each first model takes with the strict cutoff, the full list behind a details
    element, and the numbers with each pair's estimated cost."""
    fmt, astra = snap.fmt, snap.named["astra"]
    found = sorted(((snap.by_id[item["decision"]], item) for item in snap.results["cascades"] if item["frontier"] == astra["run"]),
                   key=lambda pair: -pair[1]["held_out"]["answered"])
    decision = [pair for pair in found if snap.decision_model(pair[0])]
    chat = [pair for pair in found if not snap.decision_model(pair[0])]
    lead = next(item for run, item in found if run is snap.replay["run"])
    shares = [f"{named(run)} {fmt.pct(item['held_out']['answered'])}" for run, item in decision if run["billing"] in ("api", "free")]
    compared = [f"{named(run)} {fmt.pct(item['held_out']['answered'])}" for run, item in chat]
    alt = (f"Bar chart: the share of answers each first model supplies before GPT-6 Astra, averaged over "
           f"{count(lead['held_out']['splits'])} test splits. Decision models through a provider's service: {', '.join(shares)}. "
           f"For comparison, the chat model {and_list(compared)}. A second column gives each pair's average accuracy change "
           "against Astra alone. We replayed recorded answers.")
    caption = (f"Averages over {count(lead['held_out']['splits'])} test splits: we choose a cutoff on one half of the questions and test it "
               f"on the other half. Decider v1.1 handles {fmt.pct(lead['held_out']['answered'])}; combined accuracy averages "
               f"{abs(100 * lead['held_out']['difference']):.2f} percentage points {'below' if lead['held_out']['difference'] < 0 else 'above'} Astra alone.")
    rows = []
    for group, pairs in (("Decision models", decision), ("Chat model for comparison", chat)):
        rows.append(f'<tr class="group-row"><th scope="rowgroup" colspan="4">{group}</th></tr>')
        for run, item in pairs:
            cost = usd(item["usd_per_1000"])
            if run["billing"] == "local":
                cost += '<span class="small">plus the first model\'s hardware cost, which we have not estimated</span>'
            elif run["billing"] == "free":
                cost += '<span class="small">the first model used a free tier; this assumes no charge for it</span>'
            rows.append(
                ('<tr class="lead">' if run is snap.replay["run"] else "<tr>")
                + f'<td data-label="Model answering first">{esc(named(run))}</td>'
                f'<td class="num" data-label="Questions handled by the first model">{fmt.pct(item["held_out"]["answered"])}</td>'
                f'<td class="num" data-label="Accuracy change compared with Astra alone">{change_text(item["held_out"]["difference"])}</td>'
                f'<td class="num" data-label="Estimated combined cost per 1,000 questions">{cost}</td></tr>'
            )
    table = (
        '<details class="show-table"><summary>Show the numbers, with the cost of each pair</summary><div class="table-wrap">'
        '<table class="overview cards"><thead><tr><th scope="col">Model answering first</th><th scope="col" class="num">Questions '
        'handled by the first model</th><th scope="col" class="num">Accuracy change compared with Astra alone</th><th scope="col" '
        f'class="num">Estimated combined cost per 1,000 questions</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        f'<p class="note">Astra alone costs an estimated {usd(per_thousand(astra))} per 1,000 questions. This estimate gives each '
        "question passed to the second model the same average cost. In a new run, the remaining questions may cost more.</p></details>"
    )
    everyone = ('<details class="show-more"><summary>Show all first models</summary>'
                + chart_figure("first-models-all", alt.replace("Bar chart:", "Bar chart with every first model:"), caption) + "</details>")
    return chart_figure("first-models", alt, caption) + everyone + table


def savings_table(snap: Snapshot) -> str:
    """What each second model saves with Decider in front, by rule; the opening's three LLMs first, by saving."""
    fmt = snap.fmt
    first = opening_seconds(snap)
    items = first + [item for item in snap.replay["frontiers"] if item not in first]
    rule_names = ("Most confident quarter", "Cutoff chosen on half the questions", f"Fixed {snap.cutoff} rule")

    def rule(numbers: dict[str, Any] | None, takes: bool = False) -> str:
        if numbers is None:
            return "Not run"
        text = f"{fmt.pct(numbers['saving'])} cheaper, {change_text(numbers['difference'])}"
        return f"Decider takes {fmt.pct(numbers['share'])}: {text}" if takes else text

    rows = [
        "<tr>"
        f'<td data-label="Model behind Decider">{esc(named(item["run"]))}</td>'
        f'<td class="num" data-label="Its accuracy alone">{fmt.pct(item["accuracy"])}</td>'
        f'<td class="num" data-label="{esc(rule_names[0])}">{rule(item["share"])}</td>'
        f'<td class="num" data-label="{esc(rule_names[1])}">{rule(item["strict"], True)}</td>'
        f'<td class="num" data-label="{esc(rule_names[2])}">{rule(item["sure"])}</td>'
        "</tr>"
        for item in items
    ]
    head = "".join(f'<th scope="col" class="num">{esc(name)}</th>' for name in rule_names)
    return (
        '<div class="table-wrap"><table class="overview cards savings"><thead><tr><th scope="col">Model behind Decider</th>'
        f'<th scope="col" class="num">Its accuracy alone</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def savings_sure_table(snap: Snapshot) -> str:
    """With the fixed 99% rule, each of the opening's LLMs' estimated cost per 1,000 questions alone and with Decider in
    front (Decider on every question, the LLM on the rest at its average cost)."""
    rows = "".join(
        f'<tr><td data-label="LLM">{esc(named(item["run"]))}</td><td class="num" data-label="LLM alone">{usd(item["cost"])}</td>'
        f'<td class="num" data-label="Decider and LLM">{usd(item["sure"]["usd_per_1000"])}</td></tr>'
        for item in opening_seconds(snap)
    )
    return (
        f'<div class="table-wrap"><table class="overview cards"><caption>With the fixed {esc(snap.cutoff)} rule, cost per 1,000 '
        'questions</caption><thead><tr><th scope="col">LLM</th><th scope="col" class="num">LLM alone</th>'
        f'<th scope="col" class="num">Decider and LLM</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


def replay_rules(snap: Snapshot) -> dict[str, dict[str, Any]]:
    """The replay's numbers for each second model, by live test rule (None where the replay has no such rule)."""
    return {item["key"]: {"share": item["share"], "half": item["strict"], "cutoff": item["sure"]} for item in snap.replay["frontiers"]}


def savings_live_table(snap: Snapshot) -> str:
    """The savings section's live table: Decider v1.1 in front of each of the opening's LLMs with new calls, by rule in the replay table's
    order: the share it kept, the saving and the change in accuracy."""
    fmt, tests = snap.fmt, live_tests(snap)
    rows = []
    for rules in tests["decider"].values():
        cells = "".join(
            f'<td class="num" data-label="{esc(LIVE_RULES[rule])}">Decider kept {fmt.pct(test["plan"]["routed"] / test["plan"]["held_out"])}: '
            f'{fmt.pct(saving(test["measured"]))} cheaper, {change_text(test["measured"]["difference"])}</td>'
            for rule, test in rules.items()
        )
        rows.append(f'<tr><td data-label="LLM">{esc(named(rules["half"]["frontier"]))}</td>{cells}</tr>')
    head = "".join(f'<th scope="col" class="num">{esc(name)}</th>' for name in LIVE_RULES.values())
    questions = snap.plan["held_out"]
    return (
        f'<div class="table-wrap"><table class="overview cards savings"><caption>Live test with new calls to each LLM, on '
        f'{count(questions)} questions</caption><thead><tr><th scope="col">LLM</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def more_wrong_span(snap: Snapshot) -> str:
    """How many more answers per 1,000 questions the opening's two-step setups got wrong than their LLMs alone, with the
    cutoff chosen on half the questions, to one decimal: '1.0 to 2.3'. The build stops unless each got more wrong."""
    more = sorted(-1000 * item["strict"]["difference"] for item in opening_seconds(snap))
    if more[0] <= 0:
        raise ValueError("the opening says each two-step setup got more answers wrong per 1,000 questions than its LLM")
    low, high = f"{more[0]:.1f}", f"{more[-1]:.1f}"
    return low if low == high else f"{low} to {high}"


def head(snap: Snapshot, images: dict[str, dict[str, str]]) -> str:
    """The title, the description and the link preview: the preview image is the cutoff chart, in the dark theme like the site."""
    site, fmt = snap.config["site_url"], snap.fmt
    preview = snap.config["images"]["preview"]
    tried, untried = decision_first_models(snap)
    firsts = opening_seconds(snap)
    live = [live_tests(snap)["decider"][item["key"]]["half"]["measured"] for item in firsts]
    if any(measured["difference"] > 0 for measured in live):
        raise ValueError("the description says accuracy fell by at most the live test's largest loss")
    shares = [f"{fmt.pct(item['strict']['share'], 0)} of {item['run']['name']}'s" for item in firsts]
    shares[0] += " questions"
    description = (
        f"We tested {count(len(tried) + len(untried))} decision models on {count(snap.total)} Turkish exam questions. Perplexity's "
        f"Decider v1.1 took the most work off each LLM: {and_list(shares)}, in a replay of recorded answers. In a live test with "
        f"new calls, the estimated cost fell {and_list([fmt.pct(saving(measured), 0) for measured in live])}, and accuracy fell by "
        f"at most {-100 * min(measured['difference'] for measured in live):.2f} points."
    )
    alt = cutoff_alt(snap)
    image = site + images["preview"]["dark"]
    return "\n".join(
        [
            "",
            f"  <title>{esc(TITLE)}</title>",
            f'  <link rel="canonical" href="{esc(site)}">',
            f'  <meta name="description" content="{esc(description)}">',
            f'  <meta property="og:title" content="{esc(TITLE)}">',
            f'  <meta property="og:description" content="{esc(description)}">',
            '  <meta property="og:type" content="website">',
            f'  <meta property="og:url" content="{esc(site)}">',
            f'  <meta property="og:image" content="{esc(image)}">',
            f'  <meta property="og:image:width" content="{preview["width"]}">',
            f'  <meta property="og:image:height" content="{preview["height"]}">',
            f'  <meta property="og:image:alt" content="{esc(alt)}">',
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{esc(TITLE)}">',
            f'  <meta name="twitter:description" content="{esc(description)}">',
            f'  <meta name="twitter:image" content="{esc(image)}">',
            f'  <meta name="twitter:image:alt" content="{esc(alt)}">',
            "  ",
        ]
    )


def share_link(paths: dict[str, str], name: str) -> str:
    """'Share or download this chart' downloads the image in the theme being viewed; a small link offers the other one."""
    buttons = "".join(
        f'<a class="button secondary theme-{theme}" href="{esc(paths[theme])}" download>Share or download this chart</a>'
        for theme in THEMES
    )
    others = "".join(
        f'<a class="theme-{theme}" href="{esc(paths[other])}" download>Download with a {other} background</a>'
        for theme, other in (("dark", "light"), ("light", "dark"))
    )
    return f'<p class="share">{buttons} <span class="small">{esc(name)}, PNG · {others}</span></p>'


def blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    lead_names = ", ".join(dict.fromkeys(row["run"]["name"] for row in snap.lead))
    return {
        "head": head(snap, images),
        "confidence-lead": confidence_lead(snap),
        "threshold-figure": threshold_figure(snap) + share_link(images["finding"], f"Lead finding: {lead_names}"),
        "threshold-table": threshold_table(snap),
        "accuracy-lead": accuracy_lead(snap),
        "model-kinds": model_kinds(snap),
        "task-figure": task_figure(snap) + share_link(images["tasks"], "Reading and grammar figure"),
        "results-table": results_table(snap),
        "stability-lead": stability_lead(snap),
        "stability": stability(snap),
        "cost-lead": cost_lead(snap),
        "cost-table": cost_table(snap),
        "cost-summary": cost_summary(snap),
        "cost-setup": cost_setup(snap),
        "latency-table": latency_table(snap),
        "reasoning-table": reasoning_table(snap),
        **top_blocks(snap, images),
        **overview_blocks(snap, images),
        **study_blocks(snap, images),
        **method_blocks(snap, images),
    }


def top_blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    """Blocks only the top of the page uses: the opening and the sections before the confidence overview."""
    return {
        "opening-table": opening_table(snap),
        "handoff-figure": handoff_figure(snap),
        "first-models-figure": first_models_figure(snap),
        "speed-table": speed_table(snap),
        "speed-whole": speed_whole(snap),
        "speed-figure": speed_figure(snap),
        "cutoff-figure": cutoff_figure(snap) + share_link(images["preview"], "Cutoff chart"),
        "savings-table": savings_table(snap),
        "savings-sure-table": savings_sure_table(snap),
        "savings-live-table": savings_live_table(snap),
    }


# ---------------------------------------------------------------- the study's understanding, method and limits (blocks 23 to 36)


from functools import cache  # noqa: E402  (kept in this zone so the slices merge cleanly)


@cache
def method_answers() -> dict[str, Any]:
    """answers.json, read once per build: the few counts results.json does not hold (score statuses, distinct
    scores, passages) come from the exported answers."""
    return json.loads((ROOT / "answers.json").read_text(encoding="utf-8"))


def method_scored() -> list[int]:
    """Positions of the scored questions in answers.json (the excluded ones left out)."""
    return [index for index, status in enumerate(method_answers()["questions"]["status"]) if status != "excluded"]


def method_scores(run_id: int) -> list[float | None]:
    """A run's chosen-option scores on the scored questions, None where it gave no answer."""
    run = next(item for item in method_answers()["runs"] if item["run"] == run_id)
    return [run["score"][index] for index in method_scored()]


def method_answers_text(value: int) -> str:
    """'no answers', 'one answer', 'two answers', '14 answers'."""
    return "no answers" if value == 0 else f"{in_words(value)} answer{'' if value == 1 else 's'}"


def method_size(parameters: int) -> str:
    """'26.1 billion', '320 billion', '287 million'."""
    if parameters >= 1e9:
        return f"{parameters / 1e9:.1f}".removesuffix(".0") + " billion"
    return f"{parameters / 1e6:.0f} million"


def method_records(snap: Snapshot) -> dict[str, Any]:
    """page_config.json's method_records: numbers recorded outside results.json and answers.json, each group with
    its source. The counts that results.json does hold are checked against them here."""
    records = snap.config["method_records"]
    review = records["key_review"]
    if review["image_unsettled"] + review["key_disputed"] != snap.results["excluded"]["excluded"]:
        raise ValueError("method_records.key_review: its exclusions do not add up to results.json's excluded questions")
    if review["confirmed"] + snap.results["excluded"]["excluded"] != review["cases"]:
        raise ValueError("method_records.key_review: confirmed and excluded keys do not add up to the reviewed cases")
    return records


def method_values(snap: Snapshot) -> dict[str, str]:
    """Values only the study's sections from understanding to the references (blocks 23 to 36) use."""
    results, fmt, named, out = snap.results, snap.fmt, snap.named, {}
    records = method_records(snap)
    # 23: confidence ranking on reading and on grammar, and Open Jev's probability scale.
    for key in ("jev", "open_jev"):
        parts = named[key]["confidence"]["parts"]
        out[f"method_{key}_auroc_reading"] = f"{parts['meaning']['auroc']:.2f}"
        out[f"method_{key}_auroc_grammar"] = f"{parts['form']['auroc']:.2f}"
    scores = [score for score in method_scores(named["open_jev"]["run"]) if score is not None]
    correct = method_answers_correct(named["open_jev"]["run"])
    low, high = METHOD_OPEN_JEV_BAND
    band = [right for score, right in zip(method_scores(named["open_jev"]["run"]), correct) if score is not None and low <= score < high]
    out["method_open_jev_top"] = cutoff_text(max(scores))
    out["method_open_jev_band"] = f"{cutoff_text(low)} to below {cutoff_text(high)}"
    out["method_open_jev_band_answers"] = count(len(band))
    out["method_open_jev_band_result"] = "all" if all(band) else f"{count(sum(band))} of the"
    refit = records["recalibration_v1"]
    out["method_refit_ece_before"] = f"{100 * refit['ece_before']:.1f}"
    out["method_refit_ece_after"] = f"{100 * refit['ece_after']:.1f}"
    out["method_refit_auroc_before"] = f"{refit['auroc_before']:.4f}"
    out["method_refit_auroc_after"] = f"{refit['auroc_after']:.4f}"
    # 24: repeats. Every repeat runs the same number of times.
    times = {len(item["runs"]) for item in results["repeats"]}
    if len(times) != 1:
        raise ValueError(f"repeats run {sorted(times)} times; the page says one number")
    out["method_repeat_times"] = in_words(times.pop())
    for key in snap.repeats_by_key:
        out[f"method_{key}_changed_text"] = method_answers_text(snap.repeats_by_key[key]["changed_answer"])
    keys = {run["run"]: key for key, run in named.items()}
    for item in snap.sample:
        key = keys.get(snap.main_run(item)["run"])
        if key:
            changed = item["changed_answer"]
            out[f"method_sample_{key}_changed"] = f"{count(changed)} question{'' if changed == 1 else 's'}"
    # 25: the two pairs the text walks through; the text says the first model scored higher.
    by_pair = {(item["first"], item["second"]): item for item in results["paired"]}
    for first, second in (("astra", "sol"), ("deepseek_on", "opus")):
        item = by_pair[(named[first]["run"], named[second]["run"])]
        if item["difference"] <= 0:
            raise ValueError(f"{first} no longer scores above {second}; rewrite the comparison in #differences")
        out[f"method_pair_{first}_{second}_split"] = count(item["first_only"] + item["second_only"])
    out["method_alpha"] = f"{ALPHA:g}"
    # 28: the question set and its repairs.
    extraction = records["extraction"]
    for part in ("underline_questions", "underline_lost", "numbers_lost", "text_or_key_changed"):
        out[f"method_{part}"] = count(extraction[part])
    repaired = [run for run in snap.runs if run.get("previous")]
    added = {run["previous"]["added"]["questions"] for run in repaired}
    if len(added) != 1:
        raise ValueError("the runs on both question set versions disagree on the questions version 2 adds")
    out["method_added"] = count(added.pop())
    out["method_excluded"] = count(results["excluded"]["excluded"])
    statuses = [status for status in method_answers()["questions"]["status"]]
    if statuses.count("suspect") != results["suspect"]:
        raise ValueError("answers.json and results.json disagree on the questions still marked uncertain")
    out["method_suspect"] = count(results["suspect"])
    out["method_verified"] = count(statuses.count("verified"))
    rises = {run["run"]: (run["previous"]["changed"]["newer_correct"] - run["previous"]["changed"]["older_correct"])
             / run["previous"]["changed"]["questions"] for run in repaired}
    gained = [rise for rise in rises.values() if rise > 0]
    fell = list(dict.fromkeys(run["name"] for run in repaired if rises[run["run"]] <= 0))
    out["method_repair_low"] = f"{100 * min(gained):.0f}"
    out["method_repair_high"] = f"{100 * max(gained):.0f}"
    out["method_repair_others"] = (f", apart from {and_list(fell)}, whose accuracy on them did not rise" if fell else "")
    # 29 and 34: the separate tests with one question per request.
    single = {keys[snap.main_run(item)["run"]]: item for item in results["batching"]}
    out["method_single_questions"] = count(next(iter(single.values()))["questions"])
    for key, item in single.items():
        compared = sorted({other["correct"] for other in item["others"] if other["run"] not in snap.by_id})
        runs = [other for other in item["others"] if other["run"] not in snap.by_id]
        out[f"method_single_{key}_correct"] = count(item["correct"])
        out[f"method_single_{key}_compared"] = " or ".join(count(value) for value in compared)
        out[f"method_single_{key}_runs"] = in_words(len(runs))
    # 31: rounded scores.
    for key in ("luna_api", "celeris"):
        given = [score for score in method_scores(named[key]["run"]) if score is not None]
        out[f"method_{key}_distinct"] = count(len(set(given)))
        out[f"method_{key}_scored"] = count(len(given))
        out[f"method_{key}_top"] = cutoff_text(max(given))
    # 32: statistics.
    passage_of = method_answers()["questions"]["passage"]
    passages = [passage_of[index] for index in method_scored() if passage_of[index] is not None]
    out["method_bootstrap"] = count(bm.BOOTSTRAP_RESAMPLES)
    out["method_passage_questions"] = count(len(passages))
    out["method_passages"] = in_words(len(set(passages)))
    splits = {item["held_out"]["splits"] for item in results["cascades"]}
    if len(splits) != 1:
        raise ValueError(f"routing simulations use {sorted(splits)} splits; the page says one number")
    out["method_splits"] = count(splits.pop())
    # 34: training exposure, the key review and its effect on confident mistakes.
    exam, copy, review = records["exam_check"], records["copy_check"], records["key_review"]
    out["method_exam_questions"] = count(results["tyt_mix"]["reading"] + results["tyt_mix"]["grammar"])
    out["method_exam_models"] = count(exam["models"])
    out["method_exam_lowest"] = count(exam["lowest"])
    out["method_exam_highest"] = count(exam["highest"])
    out["method_copy_original"] = fmt.pct(copy["original"])
    out["method_copy_copy"] = fmt.pct(copy["copy"])
    out["method_copy_p"] = p_value(copy["p"])
    out["method_review_cases"] = count(review["cases"])
    out["method_review_confirmed"] = count(review["confirmed"])
    out["method_review_unsettled"] = in_words(review["image_unsettled"])
    out["method_review_disputed"] = in_words(review["key_disputed"])
    out["method_review_rise"] = f"{review['largest_rise_points']:.1f}"
    for key in ("qwen_yes_no", "astra", "jev", "d1"):
        confidence = named[key]["confidence"]
        before = confidence["sure_before_audit"]["questions"] - confidence["sure_before_audit"]["correct"]
        after = confidence["sure"]["questions"] - confidence["sure"]["correct"]
        out[f"method_audit_{key}_before"] = in_words(before)
        out[f"method_audit_{key}_removed"] = in_words(before - after)
    status = method_answers()["questions"]["status"]
    decider = method_scores(named["decider_v11"]["run"])
    suspect_sure = sum(1 for index, score in zip(method_scored(), decider)
                       if status[index] == "suspect" and score is not None and score >= snap.config["threshold"])
    out["method_decider_suspect_sure"] = "none" if not suspect_sure else count(suspect_sure)
    # 35: what the answer export holds.
    pipeline_runs = {run for item in results["pipelines"] if item.get("measured") for run in
                     (item["measured"]["pipeline_run"], item["measured"]["alone_run"])}
    alone = {other["run"] for item in results["pipelines"] if item.get("measured")
             for other in item["measured"]["alternatives"]} - pipeline_runs
    out["method_live_runs"] = in_words(len(pipeline_runs))
    out["method_live_tests"] = in_words(sum(1 for item in results["pipelines"] if item.get("measured")))
    out["method_alone_runs"] = in_words(len(alone))
    out["method_single_runs"] = in_words(len(results["batching"]))
    return out


# Open Jev's confidence band the understanding section counts answers in: 50% to below 60%.
METHOD_OPEN_JEV_BAND = (0.5, 0.6)


def method_answers_correct(run_id: int) -> list[int]:
    """A run's right (1) and wrong (0) answers on the scored questions."""
    run = next(item for item in method_answers()["runs"] if item["run"] == run_id)
    return [run["correct"][index] for index in method_scored()]


# Why each model appears in the test (the brief's part 5): which runs each row covers, and its text. {placeholders}
# come from the runs' data; every run appears in exactly one row.
METHOD_SETUPS: list[tuple[list[dict[str, str]], str]] = [
    ([{"provider": "jev"}], "We called TypeSafe's hosted decision model. It gives a probability for each option, and it is the model Open Jev compares with."),
    ([{"provider": "perplexity"}, {"provider": "liquid"}],
     "We called Perplexity's two decision model versions through its Decisions API, and Liquid d1 through a free tier. "
     "Perplexity says v1.1 changes both its training data and how its Qwen base model can use the input. We do not "
     "separate those two changes in this test."),
    ([{"model": "clef"}], "We ran Cloudflare's decision model on our own hardware. It adapts Qwen 3.8 27B and scores all the options in one pass through the model."),
    ([{"model": "clef-flash"}], "We ran Cloudflare's smaller decision model on our own hardware. It adapts Qwen 3.5 9B and uses the same scoring method and release code as Clef."),
    ([{"provider": "metask"}], "We ran this decision model on our own hardware. It adapts Qwen 3.5 4B. Its published training description lists Turkish among its languages. Claims about JevBench, a different test, belong to its authors and are separate from our measurements."),
    ([{"provider": "cygnet"}], "We ran the released recipe with an unchanged Gemma 4 12B IT model. It reads the probability of each answer letter and adjusts the probability scale with a temperature of 3.4. Its server uses vLLM. Its authors report results on JevBench, a different test."),
    ([{"provider": "winnow"}], "We ran a version of Gemma 4 12B IT that its author trained for decisions. We used the recommended Q8_0 model file, which stores each weight in eight bits, and the author's server settings. The author's JevBench comparison is separate from our test."),
    ([{"provider": "fastino"}], "We called Fastino's System One API. Fastino says GLiDE makes a first assessment and reasons more on uncertain cases before it returns option probabilities. We did not run a version with that internal reasoning switched off."),
    ([{"provider": "celeris"}], "We called Celeris's System One API. The service returns option probabilities rounded to whole percentage points. Celeris publishes no model size or design for it."),
    ([{"provider": "strands"}], "We ran Amazon's released decision model with its own server and probability settings. It adds a small trained adapter and a scoring part to Qwen 3.5 2B Base."),
    ([{"provider": "laya"}], "We ran both released decision models on our own hardware. Each reads the input and scores all options in one pass."),
    ([{"model": "gliner2.5-multi-v1"}], "We ran Fastino's model for extracting and classifying text, with {size} parameters. We gave it the same question and options and asked it to score the options as labels. It shows how a much smaller classifier does."),
    ([{"model": "gliner2.5-multi-decide"}], "We ran the version of the same {size} parameter model that Fastino trained for decisions. It uses the same server and request as the base model."),
    ([{"provider": "open-jev"}], "We ran the released open decision model on our own hardware, with its own scoring part and calibration setting."),
    ([{"provider": "vllm-yes-no"}], "We used the same base model and prompts as Open Jev, without its added trained parts. We scored each proposed answer by the model's preference for Yes over No, then turned the scores into option probabilities, with a calibration temperature of 1. The gap to Open Jev shows what its added parts do together."),
    ([{"provider": "vllm-verbal"}], "We asked the base model to choose an option and write a confidence estimate. We show its estimate as a percentage."),
    ([{"provider": "vllm-vote"}], "We asked the same question ten times with random sampling. We took the most common answer, and the share of answers that agree with it as confidence."),
    ([{"provider": "openai"}, {"provider": "claude"}, {"provider": "gemini"}],
     "These chat models give comparisons for accuracy, confidence and cost. Each also writes a confidence estimate when we ask for one. Sonnet and Gemini Flash ran with low and with high reasoning. The technical records keep each provider's exact setting name."),
    ([{"provider": "openai-decisions"}], "We used OpenAI's Decisions API, in beta, to get a probability for each option, {per_request} question per request. The other Luna run writes its confidence, through Codex, with {other_per_request} questions per request. The comparison changes both the access method and the request size."),
    ([{"model": "gemma-4-31B-it"}, {"model": "deepseek-v4.1-flash"}], "We ran these models on our own hardware and recorded the probability of each answer letter. DeepSeek ran with reasoning off and on. The reasoning run also uses sampling, so the pair does not isolate the reasoning setting."),
    ([{"provider": "vllm-stated"}], "We ran Z.ai's model on our own hardware with TensorFold. It has {size} parameters in total and uses about {active} for each token: this design (mixture of experts) uses only selected parts of the model for each token. The server did not return answer letter probabilities, so we asked the model to write its confidence. We ran it with reasoning off and with reasoning on. The technical record lists the checkpoint, the weight and cache precision, and the speculative decoding settings."),
    ([{"model": "qwen3-14b"}, {"model": "erk-14b"}], "Erk continues the training of this Qwen model on Turkish text. We ran both on our own hardware with the same requests and settings. The extra training may change more than language knowledge."),
]

# Technical notes for the setup records that results.json does not carry.
METHOD_SETUP_NOTES = {
    "glm-5.3-flash": "Mia's AI Lab's EXL3 checkpoint; speculative decoding with DFlash2 drafts.",
    "winnow-12b": "Published only as GGUF files; its own llama.cpp-based server, with its author's settings.",
    "cygnet": "blockbrain-ai's recipe.",
}


def method_setup_record(snap: Snapshot, run: dict[str, Any]) -> str:
    """One setup's exact identifiers, server and hardware, for the expandable technical record."""
    rows = [
        ("Setup", esc(label(run))),
        ("Model identifier", f"<code>{esc(run['model'])}</code>"),
        ("How we called the model", esc(run["access"])),
        ("Hardware we used", esc(run["hardware"]) if run.get("hardware") else "The provider's service"),
        ("Questions in each request", count(run["questions_per_request"])),
        ("Simultaneous requests", count(run["concurrency"])),
        ("Model size in parameters", method_size(run["parameters"]) if run.get("parameters") else "Not published"),
    ]
    if run.get("active_parameters"):
        rows.append(("Parameters used per token", and_list([method_size(value) for value in run["active_parameters"]])))
    if run.get("note"):
        rows.append(("Note", esc(run["note"])))
    if run["model"] in METHOD_SETUP_NOTES:
        rows.append(("Setup detail", esc(METHOD_SETUP_NOTES[run["model"]])))
    return "<dl>" + "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows) + "</dl>"


def method_setups(snap: Snapshot) -> str:
    """The setup table: why each model appears in the test, with the exact records behind an expandable summary."""
    used: set[int] = set()
    body = []
    for specs, text in METHOD_SETUPS:
        runs = [run for run in snap.runs if any(matches(run, spec) for spec in specs)]
        if not runs:
            raise ValueError(f"no run matches the setup row {specs}")
        if used & {run["run"] for run in runs}:
            raise ValueError(f"a run of {specs} already has a setup row")
        used |= {run["run"] for run in runs}
        first = runs[0]
        others = [run for run in snap.runs if run["model"] == first["model"] and run["run"] not in {item["run"] for item in runs}]
        fields = {
            "size": method_size(first["parameters"]) if first.get("parameters") else "",
            "active": and_list([method_size(value) for value in first.get("active_parameters") or []]) if first.get("active_parameters") else "",
            "per_request": in_words(first["questions_per_request"]),
            "other_per_request": count(others[0]["questions_per_request"]) if others else "",
        }
        names = and_list(list(dict.fromkeys(run["name"] for run in runs)))
        records = "".join(method_setup_record(snap, run) for run in runs)
        summary = "Technical record" if len(runs) == 1 else f"Technical records ({count(len(runs))} setups)"
        body.append(
            f'<tr><th scope="row">{esc(names)}</th><td><p>{esc(text.format(**fields))}</p>'
            f'<details class="setup-record"><summary>{summary}</summary>{records}</details></td></tr>'
        )
    missing = [label(run) for run in snap.runs if run["run"] not in used]
    if missing:
        raise ValueError(f"setups without a row in METHOD_SETUPS: {', '.join(missing)}")
    return (
        '<div class="table-wrap"><table class="setups"><thead><tr><th scope="col">Model or setup</th>'
        f'<th scope="col">Why we included it</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def method_timing(snap: Snapshot) -> str:
    """Where each response time comes from and which runs sent several requests at a time, from the runs' latency."""
    def names(runs: list[dict[str, Any]]) -> str:
        return and_list([named(run) for run in runs])

    busy: dict[int, list[dict[str, Any]]] = {}
    for run in snap.runs:
        if run["concurrency"] > 1:
            busy.setdefault(run["concurrency"], []).append(run)
    sentences = [f"{names(runs)} sent {in_words(at_once)} requests at a time." for at_once, runs in sorted(busy.items(), reverse=True)]
    concurrency = " ".join(sentences) + " These choices, along with hardware, network conditions and service limits, affect the measured rate."
    repeats = [run for run in snap.runs if run["latency"] and run["latency"]["source"] == "repeats"]
    sample = [run for run in snap.runs if run["latency"] and run["latency"]["source"] == "sample"]
    missing = [run for run in snap.runs if not run["latency"]]
    repeat_runs = {len(run["latency"]["runs"]) for run in repeats}
    sample_runs = {len(run["latency"]["runs"]) for run in sample}
    if len(repeat_runs) > 1 or len(sample_runs) > 1:
        raise ValueError("the borrowed timings use different numbers of runs; the page says one number for each group")
    sources = (
        "Some early runs recorded the total time but not the time of each request. For those, we take response times "
        "from later runs of the same setup. "
        + (f"{names(repeats)} use their {in_words(repeat_runs.pop())} later repeat runs on all {count(snap.total)} questions. " if repeats else "")
        + (f"{names(sample)} use their {in_words(sample_runs.pop())} repeat runs on the same {count(snap.sample[0]['questions'])} questions. " if sample else "")
        + (f"{names(missing)} have no recorded response times." if missing else "")
    )
    return f"<p>{esc(concurrency)}</p><p>{esc(sources)}</p>"


def method_paired_figure(snap: Snapshot) -> str:
    """Chart 11: the listed paired comparisons, each gap with its 95% interval, coloured by Holm's test over them."""
    results = snap.results
    listed, passed, pairs = count(len(results["paired"])), count(sum(item["p_holm"] < ALPHA for item in results["paired"])), count(results["group_pairs"])
    alt = (
        f"How large are the accuracy gaps, and how uncertain are they? For each of the {listed} selected pairs, a dot "
        "shows the observed accuracy of model A minus model B, in percentage points, with a horizontal 95% interval. "
        "Positive values favour A and negative values favour B. Colour marks the selected comparison test after "
        f"adjustment across {listed} pairs: {passed} of the {listed} pass it. Not detecting a difference does not "
        "establish equality."
    )
    caption = (
        '<span class="figure-title">How large are the accuracy gaps, and how uncertain are they?</span> '
        f"Dots show observed gaps and lines show 95% intervals. The colour marks results that pass the adjustment "
        f"across these {listed} selected comparisons ({passed} of {listed} do). A line that crosses zero and the colour "
        f"answer related but different questions. The full accuracy groups use all {pairs} pairs."
    )
    return chart_figure("paired", alt, caption)


def method_blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    """Blocks only the study's sections from understanding to the references (blocks 23 to 36) use."""
    return {
        "method-setups": method_setups(snap),
        "method-timing": method_timing(snap),
        "method-paired-figure": method_paired_figure(snap),
    }


# ---------------------------------------------------------------- the page


def chart_sizes(page: str) -> str:
    """Give every chart image the width and height of its SVG. In the dark theme the charts load lazily; with their size
    known, the page keeps its height while they arrive and does not jump."""

    def sized(match: re.Match[str]) -> str:
        found = SVG_SIZE.search((ROOT / match.group(2)).read_text(encoding="utf-8"))
        if not found:
            raise ValueError(f"{match.group(2)} has no viewBox")
        width, height = (round(float(value)) for value in found.groups())
        return f'{match.group(1)} width="{width}" height="{height}"'

    return CHART_IMAGE.sub(sized, page)


def fill(page: str, numbers: dict[str, str], parts: dict[str, str]) -> str:
    unknown = sorted({match.group(2) for match in VALUE.finditer(page)} - numbers.keys())
    if unknown:
        raise ValueError(f"index.html asks for values the snapshot does not give: {', '.join(unknown)}")
    missing = sorted(parts.keys() - {match.group(2) for match in BLOCK.finditer(page)})
    if missing:
        raise ValueError(f"index.html has no marker for blocks {', '.join(missing)}")
    page = VALUE.sub(lambda match: match.group(1) + esc(numbers[match.group(2)]) + match.group(4), page)
    stray = sorted({match.group(2) for match in BLOCK.finditer(page)} - parts.keys())
    if stray:
        raise ValueError(f"index.html has markers for unknown blocks {', '.join(stray)}")
    return BLOCK.sub(lambda match: match.group(1) + parts[match.group(2)] + match.group(4), page)


# ---------------------------------------------------------------- sharing images

# The sharing images' colours: the page's tokens, so the dark images look like the site and the light ones print well.
IMAGE_THEMES = {
    "dark": {
        "bg": "#161615", "text": "#ebe9e4", "values": "#ebe9e4", "sub": "#d6d3cc", "muted": "#a8a6a0", "rule": "#34332f",
        "ok": "#4ade80", "wrong": "#fca5a5", "check": "#2b2a27", "stripe": "#3d3c38", "key-border": "#6b6963",
        "outline": "#6b6963", "track": "#2b2a27", "reading": "#86b9f3", "grammar": "#f0a35e",
        "reading-text": "#86b9f3", "grammar-text": "#f0a35e",
    },
    "light": {
        "bg": "#ffffff", "text": "#0f172a", "values": "#1e293b", "sub": "#334155", "muted": "#475569", "rule": "#e2e8f0",
        "ok": "#15803d", "wrong": "#b91c1c", "check": "#e2e8f0", "stripe": "#cbd5e1", "key-border": "#cbd5e1",
        "outline": "#64748b", "track": "#f1f5f9", "reading": "#2563eb", "grammar": "#ea580c",
        "reading-text": "#1d4ed8", "grammar-text": "#c2410c",
    },
}
# The main images are the dark ones, on the page background like the cards of a thread; the light ones are for
# reports and slides.
THEMES = tuple(IMAGE_THEMES)
# The sharing images: their key in the code and the start of their file names, which end in a hash of the file.
IMAGE_STEMS = (("preview", "preview"), ("finding", "finding"), ("tasks", "reading-grammar"))
SHARED_IMAGE = re.compile(
    rf"share/({'|'.join(stem for _, stem in IMAGE_STEMS)})-({'|'.join(THEMES)})-([0-9a-f]{{8}})\.png"
)
FIGURE_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: %(width)dpx; height: %(height)dpx; overflow: hidden; background: var(--bg); color: var(--text);
  font-family: "Helvetica Neue", Arial, "Liberation Sans", sans-serif; }
body { padding: %(pad)dpx; display: flex; flex-direction: column; }
h1 { font-size: %(title)dpx; line-height: 1.1; letter-spacing: -.01em; }
.sub { font-size: %(sub)dpx; color: var(--sub); margin-top: .25em; }
i.key { display: inline-block; width: .8em; height: .8em; margin-right: .3em; border-radius: 2px; vertical-align: -.05em; }
i.key.ok { background: var(--ok); } i.key.wrong { background: var(--wrong); }
i.key.check { background: repeating-linear-gradient(135deg, var(--check) 0 4px, var(--stripe) 4px 8px); border: 1px solid var(--key-border); }
.rows { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: %(gap)dpx; }
.row-label { font-size: %(label)dpx; font-weight: 700; white-space: nowrap; }
.row-label .muted { font-weight: 400; color: var(--muted); }
.vals { font-size: %(value)dpx; color: var(--values); margin-top: .25em; line-height: 1.3; }
.vals .wrong { color: var(--wrong); font-weight: 700; }
.stack { position: relative; display: block; height: %(bar)dpx; margin-top: .35em; }
.stack .fill { display: flex; height: 100%%; border: 2px solid var(--outline); border-radius: 4px; overflow: hidden; background: var(--check); }
.stack .ok { background: var(--ok); flex-grow: 0; flex-shrink: 0; } .stack .wrong { background: var(--wrong); flex-grow: 0; flex-shrink: 0; }
.stack .wrong.nonzero { box-shadow: inset 3px 0 0 var(--bg); }
.stack .check { flex: 1 1 0; background: repeating-linear-gradient(135deg, var(--check) 0 10px, var(--stripe) 10px 20px); }
.wrong-marker { position: absolute; top: -10px; bottom: -10px; width: 5px; margin-left: -2px; background: var(--wrong); border-radius: 2px; }
.caveat { font-size: %(caveat)dpx; color: var(--values); border-top: 2px solid var(--rule); padding-top: .45em; line-height: 1.3; }
.foot { font-size: %(foot)dpx; color: var(--muted); margin-top: .3em; }
.pair { display: grid; grid-template-columns: %(part)dpx 1fr %(num)dpx; align-items: center; gap: 16px; font-size: %(value)dpx; }
.track { height: %(bar)dpx; background: var(--track); border-radius: 4px; overflow: hidden; }
.bar { display: block; height: 100%%; }
.reading { color: var(--reading-text); } .grammar { color: var(--grammar-text); }
.bar.reading { background: var(--reading); } .bar.grammar { background: var(--grammar); }
.num { text-align: right; font-weight: 700; }
"""

def figure_page(size: dict[str, int], scale: dict[str, int], body: str, theme: str, style: str = "") -> str:
    """An image's HTML page: the theme's colours, the shared figure style at this scale, then the image's own `style`."""
    palette = "; ".join(f"--{name}: {value}" for name, value in IMAGE_THEMES[theme].items())
    css = f":root {{ {palette}; }}" + FIGURE_STYLE % {**size, **scale} + style
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def footer(snap: Snapshot, caveat: str) -> str:
    """The image's caveats in readable type, then the results update date, results snapshot, question set and address."""
    results = snap.results
    site = snap.config["site_url"].removeprefix("https://").rstrip("/")
    dataset = (results["dataset"]["graded_sha256"] or results["dataset"]["sha256"])[:8]
    return (
        f'<p class="caveat">{count(snap.total)} Turkish exam questions (reading and grammar), not financial decisions. {esc(caveat)}</p>'
        f'<p class="foot">Results updated {long_date(results["updated"])} · Results snapshot {esc(results["results_version"])} · '
        f'Question set {esc(results["dataset"]["name"])} ({dataset}) · {esc(site)}</p>'
    )


def image_label(row: dict[str, Any]) -> str:
    run = row["run"]
    details = [part for part in (setting(run), f"confidence source: {row['source'].lower()}") if part]
    return f'<span class="row-label">{esc(run["name"])}<span class="muted"> · {esc(" · ".join(details))}</span></span>'


def finding_image(snap: Snapshot, size: dict[str, int], theme: str) -> str:
    """The fixed 99% cutoff as an image: the lead rows only, each with the answers kept and those needing another answer,
    then the wrong ones, their share of the kept answers and the 95% interval for that error rate."""
    fmt, rows = snap.fmt, snap.lead
    items = []
    for row in rows:
        bar = stack_html(row, snap).replace(' aria-hidden="true"', "")
        first = f'{count(row["accepted"])} kept ({fmt.pct(row["coverage"])} of questions) · {count(row["sent"])} need another answer'
        if not row["accepted"]:
            second = "No answers reach this cutoff; error rate not applicable"
        elif row["errors"]:
            second = (f'<span class="wrong">{count(row["errors"])} wrong</span>: {fmt.pct(row["error_rate"])} of the kept answers '
                      f'(95% interval for the error rate: {fmt.span(*row["error_range"])})')
        else:
            second = f'No mistakes among them (95% interval for the error rate: {fmt.span(*row["error_range"])})'
        items.append(f'<div>{image_label(row)}{bar}<p class="vals">{first}<br>{second}</p></div>')
    name = snap.short(rows[0]["run"])
    if len(rows) == 1:
        title = f"{name}: which answers pass a {snap.cutoff} confidence cutoff?"
        caveat = ("No mistakes in a sample does not prove zero risk. " if rows[0]["accepted"] and not rows[0]["errors"] else "") + (
            "The 95% interval describes sampling uncertainty in the error rate; it is not a promise about future errors."
        )
    else:
        title = f"{name}, {in_words(len(rows))} setups: which answers pass a {snap.cutoff} confidence cutoff?"
        caveat = f"The setups also differ in request format ({per_request_text(rows)} questions per request), so this does not isolate the confidence method."
    legend = ('<i class="key ok"></i>kept and correct · <i class="key wrong"></i>kept but wrong · '
              '<i class="key check"></i>needs another answer')
    # A single bar is drawn larger, so that it does not sit between wide empty bands.
    one = len(rows) == 1
    scale = {"pad": 52, "title": 56, "sub": 30, "gap": 34, "label": 46 if one else 40, "bar": 140 if one else 54,
             "value": 48 if one else 36, "caveat": 26, "foot": 20, "part": 0, "num": 0}
    sub = f"Each bar is all {count(snap.total)} questions; we replayed recorded answers: {legend}"
    body = f'<h1>{esc(title)}</h1><p class="sub">{sub}</p><div class="rows">{"".join(items)}</div>' + footer(snap, caveat)
    return figure_page(size, scale, body, theme)


# The cutoff image's own layout: one column per cutoff, the bar drawn to scale against the most answers kept. The bars take
# the height the title, labels, note and footer leave, so a longer note never pushes the footer off the image.
CUTOFF_STYLE = """
.cols { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(var(--count), 1fr); gap: 10px; margin-top: 16px; }
.col { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; border-radius: 6px; padding: 4px 2px; }
.col.rule { background: var(--track); }
.col .kept { font-size: 22px; font-weight: 700; color: var(--values); }
.col .top { font-size: 15px; color: var(--sub); margin-bottom: 6px; white-space: nowrap; }
.col .area { flex: 1; min-height: 0; width: 64%; display: flex; flex-direction: column-reverse; }
.col .ok { background: var(--ok); } .col .wrong { background: var(--wrong); }
.col .cut { font-size: 19px; font-weight: 700; margin-top: 8px; }
.col .tag { font-size: 13px; color: var(--muted); min-height: 34px; line-height: 1.25; text-align: center; }
.axis { font-size: 16px; color: var(--sub); margin: 6px 0 10px; }
"""


def cutoff_image(snap: Snapshot, size: dict[str, int], theme: str) -> str:
    """Chart 00 as the link preview: the answers Decider keeps and the wrong ones among them at each cutoff."""
    fmt, rows, threshold = snap.fmt, cutoff_rows(snap), snap.config["threshold"]
    top = max(row["kept"] for row in rows)
    columns = []
    for row in rows:
        ok, wrong = (row["kept"] - row["wrong"]) / top, row["wrong"] / top
        # A nonzero wrong segment keeps a few pixels, so that it never vanishes; the label above gives the count.
        wrong_style = f"height: max(4px, {100 * wrong:.2f}%)" if row["wrong"] else "height: 0"
        tag = "Our rule" if row["cut"] == threshold else "Most confident quarter" if row["surest"] else ""
        columns.append(
            f'<div class="col{" rule" if tag else ""}"><span class="kept">{count(row["kept"])}</span>'
            f'<span class="top">{fmt.pct(row["kept"] / snap.total, 0)} · {count(row["wrong"])} wrong</span>'
            f'<span class="area"><span class="ok" style="height: {100 * ok:.2f}%"></span><span class="wrong" style="{wrong_style}"></span></span>'
            f'<span class="cut">{cutoff_text(row["cut"])}</span><span class="tag">{tag}</span></div>'
        )
    legend = '<i class="key ok"></i>kept and right · <i class="key wrong"></i>kept but wrong'
    scale = {"pad": 38, "title": 38, "sub": 19, "gap": 0, "label": 0, "bar": 0, "value": 0, "caveat": 16, "foot": 13, "part": 0, "num": 0}
    body = (
        "<h1>Lower the cutoff: Decider keeps more, and makes more mistakes</h1>"
        f'<p class="sub">{esc(snap.short(snap.replay["run"]))} on {count(snap.total)} Turkish exam questions; we replayed recorded '
        f"answers · {legend}</p>"
        f'<div class="cols" style="--count: {len(rows)}">{"".join(columns)}</div>'
        f'<p class="axis">Cutoff (lowest confidence we keep). Bar height: answers kept, out of {count(snap.total)}. In a replay of '
        "recorded answers, the share Decider keeps is roughly the share of the second model's estimated cost you save.</p>"
        + footer(snap, "Choose a cutoff on one set of questions and test it on new ones.")
    )
    return figure_page(size, scale, body, theme, CUTOFF_STYLE)


# The reading and grammar image's own layout: one row per model setup, the two task bars side by side under their headings.
TASK_STYLE = """
.grid { flex: 1; display: grid; grid-template-columns: 430px 1fr 1fr; column-gap: 32px; row-gap: 10px; align-content: center; }
.grid .head { font-size: 26px; font-weight: 700; }
.grid .group { grid-column: 1 / -1; font-size: 19px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin-top: 10px; }
.grid .name { font-size: 26px; font-weight: 700; white-space: nowrap; }
.grid .name .muted { font-weight: 400; color: var(--muted); }
.grid .cell { display: grid; grid-template-columns: 1fr 100px; column-gap: 14px; align-items: center; }
.grid .track { height: 26px; }
.grid .num { font-size: 25px; }
"""


def task_image(snap: Snapshot, size: dict[str, int], theme: str) -> str:
    """Chart 04 as an image: reading and grammar side by side for each model setup, decision models first and the chat
    models for comparison below their own heading."""
    fmt = snap.fmt
    scale = {"pad": 46, "title": 46, "sub": 26, "gap": 0, "label": 0, "bar": 0, "value": 0, "caveat": 21, "foot": 17, "part": 0, "num": 0}
    cells = ['<span></span><span class="head reading">Reading</span><span class="head grammar">Grammar</span>']
    for group, rows in (("Decision models", [row for row in snap.tasks if not row["reference"]]),
                        ("Chat models for comparison", [row for row in snap.tasks if row["reference"]])):
        cells.append(f'<span class="group">{group}</span>')
        for row in rows:
            detail = setting(row["run"])
            cells.append(f'<span class="name">{esc(snap.short(row["run"]))}<span class="muted">{esc(" · " + detail if detail else "")}</span></span>')
            cells += [
                f'<span class="cell"><span class="track"><span class="bar {part}" style="width: {100 * row[part]:.2f}%"></span></span>'
                f'<span class="num">{fmt.pct(row[part])}</span></span>'
                for part in ("reading", "grammar")
            ]
    sub = (f"Correct answers, %, on a 0% to 100% scale: reading, {count(snap.reading_questions)} questions; grammar, "
           f"{count(snap.grammar_questions)} questions")
    caveat = "A good reading score does not establish a good grammar score. This test does not establish why the task scores differ."
    body = f'<h1>{esc(task_title(snap))}</h1><p class="sub">{esc(sub)}</p><div class="grid">{"".join(cells)}</div>' + footer(snap, caveat)
    return figure_page(size, scale, body, theme, TASK_STYLE)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[16:24]
    return int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big")


def render_images(snap: Snapshot) -> dict[str, dict[str, str]]:
    """Draw every sharing image in both themes and save it under share/ as <stem>-<theme>-<hash>.png, the hash being
    the start of the file's SHA-256. Returns the names by image and theme."""
    chrome = os.environ.get("CHROME", "google-chrome")
    sizes = snap.config["images"]
    pages = {
        "preview": (lambda theme: cutoff_image(snap, sizes["preview"], theme), sizes["preview"]),
        "finding": (lambda theme: finding_image(snap, sizes["share"], theme), sizes["share"]),
        "tasks": (lambda theme: task_image(snap, sizes["share"], theme), sizes["share"]),
    }
    names: dict[str, dict[str, str]] = {}
    SHARE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        for key, stem in IMAGE_STEMS:
            page, size = pages[key]
            for theme in THEMES:
                source, shot = Path(work) / f"{key}-{theme}.html", Path(work) / f"{key}-{theme}.png"
                source.write_text(page(theme), encoding="utf-8")
                subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={work}/profile",
                     "--force-device-scale-factor=1", "--hide-scrollbars", f"--window-size={size['width']},{size['height']}",
                     f"--screenshot={shot}", source.as_uri()],
                    check=True, capture_output=True,
                )
                if png_size(shot) != (size["width"], size["height"]):
                    raise SystemExit(f"{key} ({theme}) is {png_size(shot)}, not {size['width']}x{size['height']}")
                data = shot.read_bytes()
                name = f"share/{stem}-{theme}-{hashlib.sha256(data).hexdigest()[:8]}.png"
                (ROOT / name).write_bytes(data)
                os.chmod(ROOT / name, 0o644)
                names.setdefault(key, {})[theme] = name
                print(f"Wrote {name} ({size['width']}x{size['height']})")
    return names


def current_images(page: str) -> dict[str, dict[str, str]]:
    """The sharing images the page links to now, for a build without Chrome. The light preview is the one image the
    page does not link to; it is the single light preview in share/."""
    linked = {(found.group(1), found.group(2)): found.group(0) for found in SHARED_IMAGE.finditer(page)}
    names: dict[str, dict[str, str]] = {}
    for key, stem in IMAGE_STEMS:
        for theme in THEMES:
            name = linked.get((stem, theme))
            if name is None and len(files := sorted(SHARE.glob(f"{stem}-{theme}-*.png"))) == 1:
                name = f"share/{files[0].name}"
            if name is None or not (ROOT / name).is_file():
                raise ValueError(f"no {theme} {stem} image to keep; build once without --no-images")
            names.setdefault(key, {})[theme] = name
    return names


def remove_old_images(snap: Snapshot, names: dict[str, dict[str, str]]) -> None:
    """Before the first public post, earlier images go; after it, they stay, so that posted previews keep working."""
    if snap.config.get("announced"):
        return
    current = {ROOT / name for paths in names.values() for name in paths.values()}
    for old in SHARE.glob("*.png"):
        if old not in current:
            old.unlink()
            print(f"Removed {old.relative_to(ROOT)}")


# ---------------------------------------------------------------- X posts


def x_length(text: str) -> int:
    return len(re.sub(r"https?://\S+", "x" * X_LINK_LENGTH, text))


def main_post(snap: Snapshot, numbers: dict[str, str]) -> str:
    """The main X post: the opening's question and answer, the comparison of decision models, each LLM's saving with its
    change in accuracy, replayed from recorded answers, and the smaller savings of the live test with new calls."""
    fmt, site = snap.fmt, snap.config["site_url"]
    savings = [
        f"{item['run']['name']}: {fmt.pct(item['strict']['saving'], 0)} cheaper, accuracy {change_text(item['strict']['difference'])}"
        for item in opening_seconds(snap)
    ]
    live = [f"{numbers['live_' + item['key'] + '_saving_whole']} for {live_name(snap, item['run'])}" for item in opening_seconds(snap)]
    return "\n\n".join([
        "When should you trust an AI model to make a decision? When its confident answers turn out to be right.",
        f"We tested {numbers['decision_models']} decision models on {numbers['questions']} Turkish exam questions and put "
        f"{numbers['decision_models_tried']} of them in front of {numbers['opening_llm_count']} LLMs. When the decision model was "
        "confident, we kept its answer; when it was not, the LLM answered.",
        "Perplexity's Decider v1.1 took the most work off each LLM. Replaying our recorded answers:\n" + "\n".join(savings),
        f"In a live test with new calls to each LLM, the estimated cost fell by less: {and_list(live)}.",
        "Exam questions, not financial decisions. Test on your own task first.",
        site,
    ])


def sure_post(snap: Snapshot, numbers: dict[str, str]) -> str:
    """The follow-up on the fixed 99% cutoff: what Decider kept, the saving in front of the three LLMs and the interval."""
    fmt, site, row = snap.fmt, snap.config["site_url"], snap.lead[0]
    items = opening_seconds(snap)
    savings = {fmt.pct(item["sure"]["saving"], 0) for item in items}
    if row["run"] is not snap.replay["run"] or row["errors"] or len(savings) != 1 or any(item["sure"]["difference"] < 0 for item in items):
        raise ValueError("the 99% post says Decider's kept answers were all right and each LLM saved the same share with no loss")
    return "\n\n".join([
        f"At a {snap.cutoff} cutoff, Decider v1.1 kept {count(row['accepted'])} of {numbers['questions']} answers "
        f"({fmt.pct(row['coverage'])}), and all of them were right. With Decider in front, the estimated cost fell about "
        f"{savings.pop()} for each LLM with no loss of accuracy (we replayed recorded answers).",
        f"No mistakes in a sample is not zero risk: the 95% interval for the error rate runs from {fmt.span(*row['error_range'])}.",
        site,
    ])


def task_post(snap: Snapshot, numbers: dict[str, str]) -> str:
    """The follow-up on reading and grammar: Decider's two scores, with Gemma's for comparison."""
    return "\n\n".join([
        f"Where do decision models fall short? Grammar. Decider v1.1 got {numbers['decider_v11_reading']} of the reading questions "
        f"right but {numbers['decider_v11_grammar']} of the grammar questions. Gemma 4 31B, a chat model, scored "
        f"{numbers['gemma_reading']} and {numbers['gemma_grammar']}.",
        "A good reading score does not establish a good grammar score, so we keep Decider's answer only when it is confident.",
        snap.config["site_url"],
    ])


def cost_post(snap: Snapshot, numbers: dict[str, str]) -> str:
    """The follow-up on cost and speed: Decider against one LLM, each timed with its own request size, from the same values
    as the speed table."""
    site, decider = snap.config["site_url"], snap.replay["run"]
    reference = snap.named[snap.config["cost_post"]["reference"]]
    latency, other = decider["latency"], reference["latency"]
    return "\n\n".join([
        f"Decider v1.1 costs {usd(per_thousand(decider))} per 1,000 questions. One question at a time, its typical response time "
        f"was {seconds(latency['median_request_seconds'])} s, and 9 in 10 answers arrived within {seconds(latency['p90_request_seconds'])} s.",
        f"{reference['name']} costs about {usd(per_thousand(reference))} per 1,000 questions and took a typical "
        f"{seconds(other['median_request_seconds'])} s per request of {count(reference['questions_per_request'])} questions.",
        "Costs are estimates at list prices. We measured times from our own computer, so they include the network.",
        site,
    ])


def x_posts(snap: Snapshot, numbers: dict[str, str], names: dict[str, dict[str, str]]) -> str:
    def length_note(text: str) -> str:
        return " Longer than one post: needs a long-post account or a thread." if x_length(text) > X_POST_LIMIT else ""

    def attach(key: str) -> str:
        return f"Attach `{names[key]['dark']}` (light version: `{names[key]['light']}`)."

    posts = [
        ("Main post: the savings", main_post(snap, numbers), attach("preview")),
        (f"Follow-up: the {snap.cutoff} cutoff", sure_post(snap, numbers), attach("finding")),
        ("Follow-up: reading and grammar", task_post(snap, numbers), attach("tasks")),
        ("Follow-up: cost and speed", cost_post(snap, numbers), "No image."),
    ]
    results = snap.results
    lines = [
        "# X posts",
        "",
        f"Generated by build_page.py from results {results['results_version']} (question set {numbers['dataset_version']}), first "
        f"published {numbers['published']}, results updated {numbers['results_updated']}. Do not edit by hand: run the build again. "
        "Attach the dark images, which match the site; each post also names its light version.",
        "",
    ]
    for title, text, image in posts:
        lines += [f"## {title} ({x_length(text)} characters as X counts them)", "", image + length_note(text), "", "```text", text, "```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-images", action="store_true", help="skip the sharing images (no Chrome needed)")
    args = parser.parse_args()
    try:
        results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / "page_config.json").read_text(encoding="utf-8"))
        snap = Snapshot(results, config, reproduce())
        numbers = values(snap)
        page = PAGE.read_text(encoding="utf-8")
        # The page links to the images by names that hash their content, so they are drawn first.
        names = current_images(page) if args.no_images else render_images(snap)
        filled = chart_sizes(fill(page, numbers, blocks(snap, names)))
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"error: {error!r}", file=sys.stderr)
        return 1
    if filled != page:
        PAGE.write_text(filled, encoding="utf-8")
        print(f"Updated {PAGE.relative_to(ROOT)}")
    else:
        print(f"{PAGE.relative_to(ROOT)} is up to date")
    if not args.no_images:
        remove_old_images(snap, names)
    X_POSTS.parent.mkdir(parents=True, exist_ok=True)
    X_POSTS.write_text(x_posts(snap, numbers, names), encoding="utf-8")
    print(f"Wrote {X_POSTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
