#!/usr/bin/env python3
"""The link preview image and CITATION.cff, from one data snapshot: results.json, with page_config.json.

    python3 build_page.py               # the link preview image and CITATION.cff
    python3 build_page.py --no-images   # keep the current image (no Chrome needed)

The site itself is built by build_v2.py, whose Method page uses this module's Snapshot, values() and table and
figure code. v1/ keeps the earlier page as it was on 14 October 2026; nothing rebuilds it.

The link preview shows every decision model's accuracy with its 95% interval. It is drawn by headless Chrome from
HTML made here, in both themes, and saved under share/ with a short hash of its content in its name, so that a changed
image gets a new address and no link preview shows a cached copy. share/images.json names the current files, which
the home page's link preview uses. Earlier images are deleted until "announced" holds the date of the first public
post, and kept after it, so that earlier link previews keep working. reproduce.py must pass first, and the build stops
otherwise. Set CHROME to use another Chrome or Chromium binary.
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

# The site and its data sit next to this script: the folder is what GitHub Pages serves.
ROOT = Path(__file__).resolve().parent
SHARE = ROOT / "share"
# The current sharing images by image and theme, written with every build that draws them.
IMAGES = SHARE / "images.json"
CITATION = ROOT / "CITATION.cff"
BLOCK = re.compile(r"(<!-- build:([a-z0-9-]+) -->)(.*?)(<!-- /build:\2 -->)", re.S)
# A chart image, with the size the build gives it, and an SVG's size.
CHART_IMAGE = re.compile(r'(<img src="(charts/[a-z0-9-]+\.svg)")(?: width="\d+" height="\d+")?')
SVG_SIZE = re.compile(r'<svg\b[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)"')
CHECKS = re.compile(r"^(\d+) checks match, (\d+) differ$", re.M)
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
    if item.get("format"):
        parts.append(item["format"])
    return ", ".join(parts)


def label(item: dict[str, Any]) -> str:
    detail = setting(item)
    return item["name"] + (f" · {detail}" if detail else "")


def named(item: dict[str, Any]) -> str:
    """A configuration's name with its setting in brackets, for use inside a longer label."""
    detail = setting(item)
    return item["name"] + (f" ({detail})" if detail else "")


def alone(item: dict[str, Any]) -> str:
    """'GPT-6.1 Sol alone (low reasoning)': a configuration that answers every question itself, without its request size:
    the live tests' tables and texts name the request size of the test."""
    detail = setting({**item, "format": None})
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
    keys = ("provider", "model", "reasoning", "variant", "questions_per_request")
    return all(item.get(key) == spec[key] for key in keys if key in spec)


def pick(items: list[dict[str, Any]], spec: dict[str, Any], what: str) -> dict[str, Any] | None:
    found = [item for item in items if matches(item, spec)]
    if len(found) > 1 and "questions_per_request" not in spec:
        # A spec without a request size names its setup's first run, not a format rerun (results.json format_of).
        found = [item for item in found if item.get("format_of") is None]
    if len(found) > 1:
        raise ValueError(f"{what}: {spec} matches {len(found)} entries; name its reasoning, variant or questions_per_request")
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
        # A setup that also ran with another number of questions per request (format_of): both of its runs name their
        # request size wherever the page names them.
        bases = {run["format_of"] for run in self.runs if run.get("format_of") is not None}
        for run in self.runs:
            if run.get("format_of") is not None or run["run"] in bases:
                run["format"] = request_size_text(run["questions_per_request"])
        reading_units = set(config["reading_units"])
        self.reading_questions = sum(unit["questions"] for unit in results["units"] if unit["number"] in reading_units)
        self.grammar_questions = sum(unit["questions"] for unit in results["units"] if unit["number"] not in reading_units)
        self.models = len({run["model"] for run in self.runs})
        # The confidence rows, in page_config.json's order, an editorial order that ranks nothing. Task rows by overall
        # accuracy, the reference rows last; stability rows by changed answers, fewest first. Ties keep the
        # configuration's order.
        thresholds = [row for spec in config["confidence_rows"] if (row := self.threshold_row(spec))]
        self.thresholds = thresholds
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
            {"label": f"{named(decision)} followed by {setup_name(frontier)}", "runs": [decision, frontier], "accuracy": measured["accuracy"],
             "versus": {key: measured[key] for key in ("difference", "low", "high", "p")},
             "cost": measured["cost_usd"], "seconds": measured["request_seconds"]},
        ]
        for alternative_spec in spec["alternatives"]:
            alternative = pick(measured["alternatives"], alternative_spec, "cost alternatives")
            assert alternative is not None
            rows.append({"label": alone(alternative), "runs": [self.main_run(alternative)], "run": alternative["run"],
                         "accuracy": alternative["accuracy"], "versus": alternative["versus_frontier"], "cost": alternative["cost_usd"],
                         "seconds": alternative["request_seconds"]})
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


# ---------------------------------------------------------------- values: the numbers the Method page quotes


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
    out.update(subq_values(snap))
    out.update(key_values(snap))
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


# The live tests' rules in the order the savings table names them, with the label each has on the page.
LIVE_RULES = {"share": "Most confident quarter", "half": "Cutoff chosen on half the questions", "cutoff": "Fixed 99% rule"}


def request_size_text(size: int) -> str:
    """'1 question per request', '16 questions per request': the request format a live test table names."""
    return f"{count(size)} question{'' if size == 1 else 's'} per request"


def per_request_words(size: int) -> str:
    """'one question per request', '16 questions per request': a request size in running text."""
    return f"{in_words(size)} question{'' if size == 1 else 's'} per request"


def one_size(sizes: set[int], where: str) -> int:
    """The one number of questions per request a table's title names; the build stops when its rows use several."""
    if len(sizes) != 1:
        raise ValueError(f"{where} names one number of questions per request, but its tests use {sorted(sizes)}")
    return next(iter(sizes))


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


def passed_cost(test: dict[str, Any]) -> float:
    """What one question passed to the second model cost in a live test, over its average question alone."""
    plan, measured = test["plan"], test["measured"]
    passed = plan["held_out"] - plan["routed"]
    return ((measured["cost_usd"] - measured["decision_cost_usd"]) / passed) / (measured["frontier_cost_usd"] / plan["held_out"])


# ---------------------------------------------------------------- the earlier page's overview values (blocks 04 to 09) and the reasoning table


# The decision models block 04 says kept no answer at the fixed cutoff.
NONE_KEPT = ("celeris", "subq")


def overview_values(snap: Snapshot) -> dict[str, str]:
    """Values only the overview sections (blocks 04 to 09) use: the highest score of each model that kept no answer at
    the fixed cutoff. The build stops when one of them now keeps answers there."""
    out = {}
    for key in NONE_KEPT:
        run = snap.named[key]
        if ((run.get("confidence") or {}).get("sure") or {}).get("questions"):
            raise ValueError(f"block 04 says {run['name']} kept no answers at the fixed cutoff")
        out[f"overview_{key}_top"] = cutoff_text(max(score for score in method_scores(run["run"]) if score is not None))
    return out


def subq_values(snap: Snapshot) -> dict[str, str]:
    """The numbers of block 03's SubQ Snap paragraph that the per-run values do not give: its release date (page_config.json
    subq_release), its share in front of Sonnet, its cost against Decider's and the context its maker claims. The build
    stops when the paragraph's claims no longer hold: tested the day after the release, not told apart from Decider v1.1
    or GLiDE, second to Decider v1.1 in front of Sonnet."""
    named, release = snap.named, snap.config["subq_release"]
    subq, decider = named["subq"], named["decider_v11"]
    day = datetime.date.fromisoformat(release["date"])
    if datetime.date.fromisoformat(subq["started"][:10]) != day + datetime.timedelta(days=1):
        raise ValueError("block 03 says we tested SubQ Snap the day after its release")
    for other in (decider, named["glide"]):
        if not set(subq["group"]) & set(other["group"]):
            raise ValueError(f"block 03 says our test did not separate SubQ Snap from {other['name']}")
    sonnet = next(item for item in opening_seconds(snap) if item["key"] == "sonnet_high")
    ranking = strict_ranking(snap, sonnet["run"])
    if ranking[0][0] is not decider or ranking[1][0] is not subq:
        raise ValueError("block 03 says SubQ Snap came second to Decider v1.1 in front of Sonnet")
    ratio = per_thousand(subq) / per_thousand(decider)
    return {
        "subq_released": long_date(release["date"]),
        "subq_sonnet_share": snap.fmt.pct(ranking[1][1]["held_out"]["answered"], 0),
        "subq_cost_ratio": times(ratio) if ratio >= 10 else f"{ratio:.1f}",
        "subq_context": release["context"],
    }


KEY_CHANGELOG = ROOT / "key-changelog.md"


def key_values(snap: Snapshot) -> dict[str, str]:
    """The frozen answer key's version (results.json answer_key). The build stops when key-changelog.md has no section for
    this version or leaves out of its tables a question the key excludes."""
    key = snap.results["answer_key"]
    text = KEY_CHANGELOG.read_text(encoding="utf-8")
    if re.search(rf"^## Version {key['version']}\b", text, re.M) is None:
        raise ValueError(f"key-changelog.md has no section for answer key version {key['version']}")
    listed = {int(found) for found in re.findall(r"^\| (\d+) \|", text, re.M)}
    missing = [question for question in key["excluded"] if question not in listed]
    if missing:
        raise ValueError(f"key-changelog.md does not list the excluded questions {missing}")
    return {"key_version": f"version {key['version']}"}


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
    by_runs = {(item["first"], item["second"]): item for item in snap.results["paired"]}
    for first, second in (("glide", "decider_v11"),):
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
    # Prices: the date most rates were recorded, and the dated exceptions the copy names; the build stops when a price
    # recorded on another date is not among them.
    dates = [price["date"] for price in results["prices"]]
    common = max(set(dates), key=dates.count)
    out["study_price_date"] = long_date(common)
    priced = ("decider_v1", "decider_v11", "celeris", "subq", "gemini_low")
    named_prices = {(named[key]["provider"], named[key]["model"]) for key in priced}
    unnamed = sorted(f"{price['provider']} {price['model']}" for price in results["prices"]
                     if price["date"] != common and (price["provider"], price["model"]) not in named_prices)
    if unnamed:
        raise ValueError(f"the study's price sentence does not name the prices recorded on another date: {unnamed}")
    for key in priced:
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


def study_top(snap: Snapshot) -> str:
    """The full accuracy table's three highest scores in words, the second and third together when they are one setup at
    two request sizes, and whether the test over all pairs told the first two apart (their comparison group letters)."""
    first, second, third = sorted(snap.runs, key=lambda run: (-run["correct"], run["run"]))[:3]

    def pct(run: dict[str, Any]) -> str:
        return snap.fmt.pct(run["correct"] / snap.total)

    if second.get("format_of") == third["run"] or third.get("format_of") == second["run"]:
        follow = (f"{esc(setup_name(second))} followed at {pct(second)} with {per_request_words(second['questions_per_request'])} "
                  f"and {pct(third)} with {per_request_words(third['questions_per_request'])}")
    else:
        follow = f"{esc(named(second))} followed at {pct(second)} and {esc(named(third))} at {pct(third)}"
    apart = ("did not establish a difference between" if shares_letter(first.get("group"), second.get("group"))
             else "established a difference between")
    return (f"{esc(named(first))} had the highest score, {pct(first)}. {follow}. The test over all pairs {apart} "
            f"{esc(snap.short(first))} and {esc(snap.short(second))}.")


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
    # The cascade chart's second models: each first-format run the routing simulations put second, in their order.
    seconds: dict[int, dict[str, Any]] = {}
    for item in results["cascades"]:
        if snap.by_id[item["frontier"]].get("format_of") is None:
            seconds.setdefault(item["frontier"], snap.by_id[item["frontier"]])
    cascade_seconds = [run["name"] for run in seconds.values()]
    return {
        "study-top": study_top(snap),
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
            f"answers as the first model gives more of the final answers, with {and_list(cascade_seconds)} as the second "
            "model. A reference line shows the second model answering every question. These curves choose and test the "
            "cutoffs on the same recorded questions, so they differ from the averages over separate test halves above.",
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


# ---------------------------------------------------------------- the opening's numbers, the title and the images


# The page's title and the link preview's (the headline on the page is the h1 in index.html).
TITLE = "When should you trust an AI model to make a decision? · Zeki Works"
# The three LLMs the opening puts Decider in front of, by named-run key; the opening orders them by saving.
OPENING_SECONDS = ("sonnet_high", "opus", "astra")
# How the opening names a decision model that came second in front of an LLM; others go by their short name.
RUNNER_UP_NAMES = {"fastino/GLiDE": "Fastino's GLiDE", "subq-snap-preview": "SubQ Snap"}
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

    # "Decider v1.1 took the most questions off each LLM", then which decision model came second in front of each LLM
    # and what its own calls cost against Decider's; "accuracy fell in front of each".
    runners: dict[int, list[str]] = {}
    for item in seconds_list:
        ranking = strict_ranking(snap, item["run"])
        if ranking[0][0] is not decider:
            raise ValueError(f"Decider v1.1 no longer takes the most questions off {label(item['run'])}")
        runners.setdefault(ranking[1][0]["run"], []).append(live_name(snap, item["run"]))

    def ratio_text(run: dict[str, Any]) -> str:
        ratio = per_thousand(run) / per_thousand(decider)
        return times(ratio) if ratio >= 10 else f"{ratio:.1f}".rstrip("0").rstrip(".")

    second = [(snap.by_id[run_id], llms) for run_id, llms in runners.items()]
    if len(second) == 1:
        out["opening_runner_up"] = (f"{RUNNER_UP_NAMES.get(second[0][0]['model'], snap.short(second[0][0]))} came second each "
                                    f"time, but its own calls cost {ratio_text(second[0][0])} times as much as Decider's.")
    else:
        places = [f"{RUNNER_UP_NAMES.get(run['model'], snap.short(run))}{' came second' if index == 0 else ''} in front of "
                  f"{and_list(llms)}" for index, (run, llms) in enumerate(second)]
        last = ", and " if len(places) == 2 else "; and "
        out["opening_runner_up"] = (f"{'; '.join(places[:-1])}{last}{places[-1]}. Their own calls cost "
                                    f"{and_list([ratio_text(run) for run, _ in second])} times as much as Decider's.")
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


def setup_name(item: dict[str, Any]) -> str:
    """A setup's name with its setting in brackets, without its request size: tables that compare request sizes name
    them in their headings."""
    return named({**item, "format": None})


def savings_table(snap: Snapshot) -> str:
    """What each second model saves with Decider in front, by rule; the opening's three LLMs first, by saving. Where some
    second models also ran with another number of questions per request, a heading row before each size names it, and
    each format rerun keeps its setup's place."""
    fmt = snap.fmt
    first = opening_seconds(snap)
    items = first + [item for item in snap.replay["frontiers"] if item not in first]
    place = {item["run"]["run"]: index for index, item in enumerate(items)}
    rule_names = ("Most confident quarter", "Cutoff chosen on half the questions", f"Fixed {snap.cutoff} rule")

    def rule(numbers: dict[str, Any] | None, takes: bool = False) -> str:
        if numbers is None:
            return "Not run"
        text = f"{fmt.pct(numbers['saving'])} cheaper, {change_text(numbers['difference'])}"
        return f"Decider takes {fmt.pct(numbers['share'])}: {text}" if takes else text

    def row(item: dict[str, Any]) -> str:
        return (
            "<tr>"
            f'<td data-label="Model behind Decider">{esc(setup_name(item["run"]))}</td>'
            f'<td class="num" data-label="Its accuracy alone">{fmt.pct(item["accuracy"])}</td>'
            f'<td class="num" data-label="{esc(rule_names[0])}">{rule(item["share"])}</td>'
            f'<td class="num" data-label="{esc(rule_names[1])}">{rule(item["strict"], True)}</td>'
            f'<td class="num" data-label="{esc(rule_names[2])}">{rule(item["sure"])}</td>'
            "</tr>"
        )

    sizes = sorted({item["run"]["questions_per_request"] for item in items}, reverse=True)
    rows = []
    for size in sizes:
        group = sorted((item for item in items if item["run"]["questions_per_request"] == size),
                       key=lambda item: place[item["run"].get("format_of") or item["run"]["run"]])
        if len(sizes) > 1:
            rows.append(f'<tr class="group-row"><th scope="rowgroup" colspan="5">Second model: {request_size_text(size)}</th></tr>')
        rows.extend(row(item) for item in group)
    head = "".join(f'<th scope="col" class="num">{esc(name)}</th>' for name in rule_names)
    return (
        '<div class="table-wrap"><table class="overview cards savings"><thead><tr><th scope="col">Model behind Decider</th>'
        f'<th scope="col" class="num">Its accuracy alone</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def format_table(snap: Snapshot) -> str:
    """The request format table: each setup asked every question with both numbers of questions per request (results.json
    formats), its accuracy with each and the change, with its 95% interval and the exact McNemar p after Holm's
    correction over these comparisons. Largest change first."""
    items = snap.results.get("formats") or []
    if not items:
        raise ValueError("the request format table needs format reruns in results.json")
    first = one_size({item["base_questions_per_request"] for item in items}, "the request format table")
    again = one_size({item["questions_per_request"] for item in items}, "the request format table")
    heads = (request_size_text(first).capitalize(), request_size_text(again).capitalize(), "Change",
             "Exact McNemar test, Holm-adjusted")
    rows = []
    for item in sorted(items, key=lambda item: -item["difference"]):
        cells = (pct2(item["base_correct"] / snap.total), pct2(item["correct"] / snap.total),
                 f'{change_text(item["difference"])}<span class="small">95% interval: {interval_points(item["low"], item["high"])}</span>',
                 esc(p_text(item["p_holm"])))
        rows.append(f'<tr><td data-label="Setup">{esc(setup_name(snap.by_id[item["base"]]))}</td>'
                    + "".join(f'<td class="num" data-label="{esc(head)}">{cell}</td>' for head, cell in zip(heads, cells)) + "</tr>")
    return (f'<div class="table-wrap"><table class="overview cards"><caption>Accuracy on all {count(snap.total)} questions, by '
            'questions per request</caption><thead><tr><th scope="col">Setup</th>'
            + "".join(f'<th scope="col" class="num">{esc(head)}</th>' for head in heads)
            + f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def rerun_frontiers(snap: Snapshot) -> list[dict[str, Any]]:
    """The lead replay's second models that are format reruns, in results.json's order. The build stops when one has no
    routing simulation with the cutoff chosen on half the questions, the rule the request format's verdict uses."""
    items = [item for item in snap.replay["frontiers"] if item["run"].get("format_of") is not None]
    if any(item["strict"] is None for item in items):
        raise ValueError("a format rerun in the replay has no routing simulation with the cutoff chosen on half the questions")
    return items


def replay_rules(snap: Snapshot) -> dict[str, dict[str, Any]]:
    """The replay's numbers for each second model, by live test rule (None where the replay has no such rule)."""
    return {item["key"]: {"share": item["share"], "half": item["strict"], "cutoff": item["sure"]} for item in snap.replay["frontiers"]}


def more_wrong_span(snap: Snapshot) -> str:
    """How many more answers per 1,000 questions the opening's two-step setups got wrong than their LLMs alone, with the
    cutoff chosen on half the questions, to one decimal: '1.0 to 2.3'. The build stops unless each got more wrong."""
    more = sorted(-1000 * item["strict"]["difference"] for item in opening_seconds(snap))
    if more[0] <= 0:
        raise ValueError("the opening says each two-step setup got more answers wrong per 1,000 questions than its LLM")
    low, high = f"{more[0]:.1f}", f"{more[-1]:.1f}"
    return low if low == high else f"{low} to {high}"


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
    ([{"provider": "subq"}], "We called SubQ's Decisions API, in public preview. It returns a probability for each option. SubQ says preview models can change before general availability, and it publishes no model size or design for this one."),
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


def method_timing(snap: Snapshot) -> str:
    """Where each response time comes from and which runs sent several requests at a time, from the runs' latency."""
    def names(runs: list[dict[str, Any]]) -> str:
        """The runs as a list; when they share one request size and a setup was asked with two, that size comes once,
        first ('With 16 questions per request, A, B and C')."""
        sizes = {run["questions_per_request"] for run in runs}
        if len(sizes) == 1 and any(run.get("format") for run in runs):
            return f"With {request_size_text(sizes.pop())}, {and_list([setup_name(run) for run in runs])}"
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


# ---------------------------------------------------------------- chart figures


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


# ---------------------------------------------------------------- sharing images

# The sharing image's colours: the page's tokens, so the dark image looks like the site and the light one prints well.
# "bar" is the decision models' colour in the site's charts (style.css --primary).
IMAGE_THEMES = {
    "dark": {"bg": "#161615", "text": "#ebe9e4", "values": "#ebe9e4", "sub": "#d6d3cc", "muted": "#a8a6a0", "rule": "#34332f",
             "bar": "#86b9f3"},
    "light": {"bg": "#ffffff", "text": "#0f172a", "values": "#1e293b", "sub": "#334155", "muted": "#475569", "rule": "#e2e8f0",
              "bar": "#2563eb"},
}
# The main images are the dark ones, on the page background like the cards of a thread; the light ones are for
# reports and slides.
THEMES = tuple(IMAGE_THEMES)
# The sharing images: their key in the code and the start of their file names, which end in a hash of the file.
IMAGE_STEMS = (("preview", "preview"),)
FIGURE_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: %(width)dpx; height: %(height)dpx; overflow: hidden; background: var(--bg); color: var(--text);
  font-family: "Helvetica Neue", Arial, "Liberation Sans", sans-serif; }
body { padding: %(pad)dpx; display: flex; flex-direction: column; }
h1 { font-size: %(title)dpx; line-height: 1.1; letter-spacing: -.01em; }
.sub { font-size: %(sub)dpx; color: var(--sub); margin-top: .25em; }
.foot { font-size: %(foot)dpx; color: var(--muted); margin-top: .3em; }
"""


def figure_page(size: dict[str, int], scale: dict[str, int], body: str, theme: str, style: str = "") -> str:
    """An image's HTML page: the theme's colours, the shared figure style at this scale, then the image's own `style`."""
    palette = "; ".join(f"--{name}: {value}" for name, value in IMAGE_THEMES[theme].items())
    css = f":root {{ {palette}; }}" + FIGURE_STYLE % {**size, **scale} + style
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


# The link preview's own layout: a row per decision model on one 0% to 100% scale, the accuracy as a dot, its 95%
# interval as a line, and the value in a column of its own, so that no label meets a mark.
ACCURACY_STYLE = """
.chart { flex: 1; min-height: 0; display: grid; grid-template-columns: 250px 1fr 80px; grid-auto-rows: 1fr;
  column-gap: 18px; align-items: center; margin-top: 14px; }
.name { font-size: 17px; font-weight: 600; text-align: right; white-space: nowrap; }
.lane { position: relative; height: 100%; border-right: 1px solid var(--rule);
  background: linear-gradient(to right, var(--rule) 0 1px, transparent 1px) 0 0 / 25% 100% repeat-x; }
.ci { position: absolute; top: 50%; height: 2px; margin-top: -1px; background: var(--text); }
.ci::before, .ci::after { content: ""; position: absolute; top: -5px; width: 2px; height: 12px; background: var(--text); }
.ci::before { left: -1px; } .ci::after { right: -1px; }
.dot { position: absolute; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
  background: var(--bar); box-shadow: 0 0 0 2px var(--bg); }
.val { font-size: 17px; font-weight: 700; text-align: right; color: var(--values); font-variant-numeric: tabular-nums; }
.axis { display: grid; grid-template-columns: 250px 1fr 80px; column-gap: 18px; height: 24px; margin-top: 4px; }
.axis .ticks { position: relative; font-size: 14px; color: var(--muted); }
.axis .ticks span { position: absolute; top: 3px; transform: translateX(-50%); }
"""


def chart_label(snap: Snapshot, run: dict[str, Any]) -> str:
    """A setup's label in the site's charts (v2.js chartLabels): page_config.json's chart_labels, else its short name
    and variant."""
    named = snap.config["chart_labels"].get(run["provider"], {}).get(run["model"])
    if named:
        return named
    return f"{snap.short(run)} ({run['variant']})" if run.get("variant") else snap.short(run)


def accuracy_image(snap: Snapshot, size: dict[str, int], theme: str) -> str:
    """The link preview: every decision model's accuracy on all questions with its 95% interval (Wilson, as the site's
    tables), most accurate first, all drawn alike so that no model is singled out. The footer gives the results
    version, the answer key version and the page address."""
    runs = [run for run in snap.runs if snap.decision_model(run)]
    totals = {run["run"]: (run["groups"]["reading"]["correct"] + run["groups"]["grammar"]["correct"],
                           run["groups"]["reading"]["questions"] + run["groups"]["grammar"]["questions"]) for run in runs}
    rows = []
    for run in sorted(runs, key=lambda run: -totals[run["run"]][0]):
        correct, total = totals[run["run"]]
        low, high = bm.wilson_interval(correct, total)
        rows.append(
            f'<span class="name">{esc(chart_label(snap, run))}</span>'
            f'<span class="lane"><span class="ci" style="left: {100 * low:.2f}%; width: {100 * (high - low):.2f}%"></span>'
            f'<span class="dot" style="left: {100 * correct / total:.2f}%"></span></span>'
            f'<span class="val">{100 * correct / total:.1f}%</span>'
        )
    results = snap.results
    site = snap.config["site_url"].removeprefix("https://").rstrip("/")
    ticks = "".join(f'<span style="left: {tick}%">{tick}%</span>' for tick in (0, 25, 50, 75, 100))
    body = (
        f"<h1>Accuracy of the {count(len(runs))} decision models, with 95% intervals</h1>"
        f'<p class="sub">Our reading comprehension and grammar test: {count(snap.total)} questions in native Turkish (not translated). '
        "Dot: accuracy; line: 95% interval.</p>"
        f'<div class="chart">{"".join(rows)}</div>'
        f'<div class="axis"><span></span><span class="ticks">{ticks}</span><span></span></div>'
        f'<p class="foot">Results {esc(results["results_version"])} · Answer key version {results["answer_key"]["version"]} · '
        f"{esc(site)}</p>"
    )
    scale = {"pad": 34, "title": 32, "sub": 18, "foot": 15}
    return figure_page(size, scale, body, theme, ACCURACY_STYLE)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[16:24]
    return int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big")


def render_images(snap: Snapshot) -> dict[str, dict[str, str]]:
    """Draw every sharing image in both themes and save it under share/ as <stem>-<theme>-<hash>.png, the hash being
    the start of the file's SHA-256. Returns the names by image and theme."""
    chrome = os.environ.get("CHROME", "google-chrome")
    sizes = snap.config["images"]
    pages = {"preview": (lambda theme: accuracy_image(snap, sizes["preview"], theme), sizes["preview"])}
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


def current_images() -> dict[str, dict[str, str]]:
    """The sharing images of the last build that drew them (share/images.json), by image and theme: what a build
    without Chrome keeps, and the home page's link preview."""
    if not IMAGES.is_file():
        raise ValueError(f"{IMAGES.relative_to(ROOT)} is missing; run build_page.py once without --no-images")
    names: dict[str, dict[str, str]] = json.loads(IMAGES.read_text(encoding="utf-8"))
    for key, stem in IMAGE_STEMS:
        for theme in THEMES:
            name = names.get(key, {}).get(theme)
            if name is None or not (ROOT / name).is_file():
                raise ValueError(f"no {theme} {stem} image in {IMAGES.relative_to(ROOT)}; build once without --no-images")
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


# ---------------------------------------------------------------- citation


def citation(snap: Snapshot, numbers: dict[str, str]) -> str:
    """CITATION.cff: how to cite these results, with the results version and the answer key version they come from."""
    results, config = snap.results, snap.config
    return "\n".join([
        "# Generated by build_page.py from results.json. Do not edit by hand: run the build again.",
        "cff-version: 1.2.0",
        'message: "If you use these results, please cite them with the results version, the answer key version and the '
        'commit of zekiworks/analysis you used."',
        f'title: "{TITLE.removesuffix(" · Zeki Works")}"',
        f'abstract: "We tested {numbers["models"]} models, {numbers["decision_models"]} of them decision models, on a reading '
        f'comprehension and grammar test in native Turkish (not translated): {numbers["questions"]} questions."',
        "type: dataset",
        "authors:",
        '  - name: "Zeki Works"',
        f'version: "results {results["results_version"]}, answer key version {results["answer_key"]["version"]}"',
        f'date-released: "{results["updated"][:10]}"',
        f'url: "{config["site_url"]}"',
        f'repository-code: "{config["code_url"]}"',
        "license: MIT",
        "keywords:",
        '  - "decision models"',
        '  - "confidence"',
        '  - "calibration"',
        '  - "Turkish"',
        "",
    ])


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-images", action="store_true", help="keep the current sharing images (no Chrome needed)")
    args = parser.parse_args()
    try:
        results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / "page_config.json").read_text(encoding="utf-8"))
        snap = Snapshot(results, config, reproduce())
        numbers = values(snap)
        names = current_images() if args.no_images else render_images(snap)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"error: {error!r}", file=sys.stderr)
        return 1
    if not args.no_images:
        remove_old_images(snap, names)
        IMAGES.write_text(json.dumps(names, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {IMAGES.relative_to(ROOT)}")
    CITATION.write_text(citation(snap, numbers), encoding="utf-8")
    print(f"Wrote {CITATION.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
