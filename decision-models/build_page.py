#!/usr/bin/env python3
"""Fill the page's generated parts from one data snapshot: results.json, with page_config.json.

    python3 build_page.py               # the page, the sharing images and the X posts
    python3 build_page.py --no-images   # without the images (no Chrome needed)

Every number in the overview, in the sharing images and in the X posts comes from the snapshot, and so do the
numbers in the study's sentences that carry a marker. index.html keeps the copy; this script rewrites what is
inside its markers:

- <span data-value="key">…</span>: a number or a short text from values();
- <!-- build:name --> … <!-- /build:name -->: a block from blocks() (tables, bars, sentences, meta tags).

"lead" in page_config.json names the finding the page leads with (one of "leads"): it opens the page, comes
first in the confidence figure, and is what the link preview, the X image and the main X post show. The images
are drawn by headless Chrome from HTML made here, from the same rows as the page, and saved under share/ with
the results version in their names; share/x-posts.md holds the announcement text. Earlier images are
deleted until "announced" holds the date of the first public post, and kept after it, so that earlier link
previews keep working. reproduce.py must pass first, and the build stops otherwise. Set CHROME to use another
Chrome or Chromium binary.
"""

from __future__ import annotations

import argparse
import datetime
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
        return f"{100 * low:.{self.digits}f}–{100 * high:.{self.digits}f}%"

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


# ---------------------------------------------------------------- values for the page's spans


def values(snap: Snapshot) -> dict[str, str]:
    results, fmt = snap.results, snap.fmt
    per_request = snap.config["stability_sample_questions_per_request"]
    out = {
        "threshold": f"{snap.config['threshold']:.2f}",
        "questions": count(snap.total),
        "models": count(snap.models),
        "configs": count(len(snap.runs)),
        "featured_configs": count(len(snap.featured)),
        "reading_questions": count(snap.reading_questions),
        "grammar_questions": count(snap.grammar_questions),
        "grammar_share": f"{100 * snap.grammar_questions / snap.total:.0f}%",
        "published": long_date(snap.config["published"]),
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
        out[f"{key}_tokens"] = count(round(run["output_tokens"] / run["answered_questions"])) if run.get("output_tokens") is not None else "not reported"
        out[f"{key}_cost"] = usd(1000 * run["api_equivalent_usd"] / run["answered_questions"]) if run.get("api_equivalent_usd") is not None else "not estimated"
        out[f"{key}_minutes"] = minutes(run["request_seconds"])
        out[f"{key}_concurrency"] = count(run["concurrency"])
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


def bar_values(row: dict[str, Any], fmt: Format) -> str:
    """Under a bar: the answers accepted with their share of all questions, the wrong ones with their share of
    the accepted answers and the 95% error estimate range of that share, and the answers sent to check."""
    if not row["accepted"]:
        return f'<span>0 accepted; error rate not applicable</span> <span>{count(row["sent"])} sent to check</span>'
    return (
        f'<span>{count(row["accepted"])} accepted ({fmt.pct(row["coverage"])} of questions)</span> '
        f'<span class="v-wrong">{count(row["errors"])} wrong ({fmt.pct(row["error_rate"])} of accepted answers; '
        f'95% error estimate range {fmt.span(*row["error_range"])})</span> '
        f'<span>{count(row["sent"])} sent to check</span>'
    )


LEGEND = (
    '<span class="legend"><span><i class="key ok"></i>accepted and correct</span> '
    '<span><i class="key wrong"></i>accepted but wrong</span> <span><i class="key check"></i>sent to check</span></span>'
)


def threshold_figure(snap: Snapshot) -> str:
    items = []
    for row in snap.thresholds:
        is_lead = any(row is first for first in snap.lead)
        items.append(
            ('<li class="lead">' if is_lead else "<li>")
            + f'<p class="bar-label">{label_html(row["run"])}<span class="small">Confidence: {esc(row["source"].lower())}</span></p>'
            + stack_html(row, snap)
            + f'<p class="bar-values">{bar_values(row, snap.fmt)}</p></li>'
        )
    threshold = f"{snap.config['threshold']:.2f}"
    return (
        '<figure class="threshold-figure" aria-labelledby="threshold-title">'
        f'<figcaption id="threshold-title">Confidence of {threshold} or higher, applied to recorded answers. Each bar is all '
        f"{count(snap.total)} scored questions: {LEGEND}. {esc(snap.lead_spec['order'])}. The order is editorial, not a "
        "ranking.</figcaption>"
        f'<ul class="threshold-bars">{"".join(items)}</ul></figure>'
    )


def threshold_table(snap: Snapshot) -> str:
    fmt = snap.fmt
    rows = []
    for row in snap.thresholds:
        run = row["run"]
        if row["accepted"]:
            errors = f'{count(row["errors"])}<span class="small">{fmt.pct(row["error_rate"])} of accepted</span>'
            span = fmt.span(*row["error_range"])
        else:
            errors, span = '0<span class="small">not applicable</span>', "not applicable"
        rows.append(
            "<tr>"
            f'<td data-label="Model and configuration">{label_html(run)}<span class="small">Confidence: {esc(row["source"].lower())}</span></td>'
            f'<td class="num" data-label="Answers accepted">{count(row["accepted"])}<span class="small">{fmt.pct(row["coverage"])} of all scored questions</span></td>'
            f'<td class="num" data-label="Errors among accepted answers">{errors}</td>'
            f'<td class="num" data-label="Error estimate range (95%)">{span}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Model and configuration</th><th scope="col" class="num">Answers accepted</th>'
        '<th scope="col" class="num">Errors among accepted answers</th><th scope="col" class="num">Error estimate range (95%)</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def task_figure(snap: Snapshot) -> str:
    fmt = snap.fmt
    items = []
    for row in snap.tasks:
        bars = "".join(
            f'<span class="pair"><span class="part {part}">{name}</span><span class="track"><span class="bar {part}" style="width: {100 * row[part]:.2f}%"></span></span>'
            f'<span class="value">{fmt.pct(row[part])}</span></span>'
            for part, name in (("reading", "Reading"), ("grammar", "Grammar"))
        )
        items.append(f'<li><p class="bar-label">{label_html(row["run"])}</p>{bars}</li>')
    # The axis is one more row of the same grid, so its ticks sit over the bars' own track.
    ticks = "".join(f'<span style="left: {tick}%">{tick}%</span>' for tick in (0, 25, 50, 75, 100))
    return (
        '<figure class="task-figure" aria-labelledby="task-title">'
        '<figcaption id="task-title" class="figure-title">Strong reading scores, weaker grammar scores</figcaption>'
        f'<ul class="task-bars">{"".join(items)}</ul>'
        f'<p class="pair axis" aria-hidden="true"><span></span><span class="axis-track">{ticks}</span><span></span></p>'
        f'<p class="caption">{count(snap.reading_questions)} reading questions and {count(snap.grammar_questions)} grammar questions. '
        "Selected configurations. Performance on one task type does not establish performance on another. "
        "These results do not identify the cause of the gap.</p></figure>"
    )


def results_rows(snap: Snapshot, runs: list[dict[str, Any]]) -> str:
    fmt = snap.fmt
    rows = []
    for run in runs:
        groups = run["groups"]
        detail = setting(run) or "option scoring, no reasoning setting"
        badge = (
            '<span class="badge" tabindex="0" aria-describedby="decision-model-help">Decision model'
            '<span class="badge-tip" role="tooltip">Chooses from the given options and returns a probability for each option.</span></span>'
            if snap.decision_model(run)
            else ""
        )
        rows.append(
            "<tr>"
            f'<td><details class="model-details"><summary>{label_html(run)}</summary><dl>'
            f'<dt>Access</dt><dd>{esc(run["access"])}</dd>'
            f'<dt>Setting</dt><dd>{esc(detail)}</dd>'
            f'<dt>Questions per request</dt><dd>{run["questions_per_request"]}</dd>'
            f'<dt>Run started</dt><dd>{long_date(run["started"])}</dd>'
            f"</dl></details>{badge}</td>"
            f'<td class="num" data-label="Overall">{fmt.pct(run["correct"] / snap.total)}</td>'
            f'<td class="num reading" data-label="Reading">{fmt.pct(groups["reading"]["correct"] / groups["reading"]["questions"])}</td>'
            f'<td class="num grammar" data-label="Grammar">{fmt.pct(groups["grammar"]["correct"] / groups["grammar"]["questions"])}</td>'
            f'<td class="group" data-label="Tie group">{esc(run.get("group") or "—")}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview results">'
        '<thead><tr><th scope="col">Model and setting</th><th scope="col" class="num">Overall</th>'
        '<th scope="col" class="num reading"><i class="key reading"></i>Reading</th>'
        '<th scope="col" class="num grammar"><i class="key grammar"></i>Grammar</th><th scope="col">Tie group</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def results_table(snap: Snapshot) -> str:
    """The configurations the page's figures show, by overall accuracy, then every configuration on request."""
    everything = count(len(snap.runs))
    return (
        results_rows(snap, snap.featured)
        + f'<details class="all-configs"><summary>View all configurations ({everything})</summary>{results_rows(snap, snap.runs)}</details>'
    )


def stability_table(items: list[dict[str, Any]], fmt: Format) -> str:
    # Every configuration in a group has the same number of runs (group_heading checks it).
    repeated = f"Same wrong answer in all {in_words(len(items[0]['runs']))} runs"
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f'<td data-label="Configuration">{label_html(item)}</td>'
            f'<td class="num" data-label="Changed answers">{count(item["changed_answer"])}'
            f'<span class="small">{fmt.pct(item["changed_answer"] / item["questions"])} of questions</span></td>'
            f'<td class="num" data-label="{repeated}">{count(item["wrong_every_run_same"])}'
            f'<span class="small">of the {count(item["wrong_any"])} questions it got wrong at least once</span></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Configuration</th><th scope="col" class="num">Changed answers</th>'
        f'<th scope="col" class="num">{repeated}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def group_heading(items: list[dict[str, Any]], what: str) -> str:
    """A stability group's questions, questions per request and runs, which every configuration in it shares."""
    questions = {item["questions"] for item in items}
    per_request = {item["questions_per_request"] for item in items}
    runs = {len(item["runs"]) for item in items}
    if len(questions) != 1 or len(per_request) != 1 or len(runs) != 1:
        raise ValueError(f"{what}: the configurations differ in questions, questions per request or runs")
    (questions_value,), (per_request_value,), (runs_value,) = questions, per_request, runs
    noun = "question" if per_request_value == 1 else "questions"
    return f"{count(questions_value)} questions, {in_words(per_request_value)} {noun} per request, {in_words(runs_value)} runs each"


def stability(snap: Snapshot) -> str:
    return (
        f'<h3 id="stability-whole-bank">Whole bank: {group_heading(snap.whole_bank, "whole bank")}</h3>'
        + stability_table(snap.whole_bank, snap.fmt)
        + f'<h3 id="stability-sample">Fixed sample: {group_heading(snap.sample, "sample")}</h3>'
        + stability_table(snap.sample, snap.fmt)
    )


def stability_lead(snap: Snapshot) -> str:
    """The section's opening finding: one configuration's changed answers and repeated mistakes."""
    item = snap.repeats_by_key[snap.config["stability_lead"]]
    changed = "changed no answers" if not item["changed_answer"] else f"changed its answer on {count(item['changed_answer'])} questions"
    runs = in_words(len(item["runs"]))
    if item["wrong_every_run_same"] == item["wrong_any"]:
        same = f"gave the same wrong answer in all {runs} runs to all {count(item['wrong_any'])} questions it got wrong at least once"
    else:
        same = (f"gave the same wrong answer in all {runs} runs to {count(item['wrong_every_run_same'])} of the "
                f"{count(item['wrong_any'])} questions it got wrong at least once")
    return (
        f"<p>{esc(label(item))} {changed} across {runs} runs of all {count(item['questions'])} questions, "
        f"and {same}. Stable is not the same as correct.</p>"
    )


def short_date(iso: str) -> str:
    day = datetime.date.fromisoformat(iso[:10])
    return f"{day.day} {day:%b} {day.year}"


def price_note(snap: Snapshot, runs: list[dict[str, Any]]) -> str:
    """The date of each price behind a cost, naming the model when the dates differ."""
    dated = [(run["name"], snap.price(run)["date"]) for run in runs if snap.price(run)]
    if not dated:
        return "no price"
    if len({date for _, date in dated}) == 1:
        return f"prices of {short_date(dated[0][1])}"
    return "prices of " + ", ".join(f"{short_date(date)} ({name})" for name, date in dated)


def cost_table(snap: Snapshot) -> str:
    """The four setups on the held-out questions; tests, access, cost basis and price dates are in the details below."""
    fmt, held_out = snap.fmt, snap.plan["held_out"]
    rows = []
    for row in snap.costs:
        versus = row["versus"]
        difference = "reference" if versus is None else f'{points(versus["difference"])} points'
        per_request = " / ".join(str(run["questions_per_request"]) for run in row["runs"])
        rows.append(
            "<tr>"
            f'<td class="setup" data-label="Setup"><span class="model-name">{esc(row["label"])}</span>'
            f'<span class="small">Questions per request: {per_request}</span></td>'
            f'<td class="num" data-label="Accuracy">{fmt.pct(row["accuracy"])}</td>'
            f'<td class="num" data-label="Difference from the first row">{difference}</td>'
            f'<td class="num" data-label="Estimated API cost per 1,000 questions">{usd(1000 * row["cost"] / held_out)}</td>'
            f'<td class="num" data-label="Request time">{row["seconds"] / 60:.1f} min<span class="small">for {count(held_out)} questions</span></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards costs">'
        '<thead><tr><th scope="col">Setup</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Difference from the first row</th>'
        '<th scope="col" class="num">Estimated API cost per 1,000 questions</th><th scope="col" class="num">Request time</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def cost_lead(snap: Snapshot) -> str:
    """The routing tradeoff above the table, against the reference: the estimated API cost, the total request time and
    the accuracy difference with its interval; then how the experiment was run and what it did not measure."""
    fmt, held_out = snap.fmt, snap.plan["held_out"]
    reference, routed = snap.costs[0], snap.costs[1]
    decision, frontier = routed["runs"]
    versus = routed["versus"]
    saving = 1 - routed["cost"] / reference["cost"]
    cost_change = (f"reduced the estimated API cost by {fmt.pct(saving, 0)}" if saving > 0
                   else f"increased the estimated API cost by {fmt.pct(-saving, 0)}")
    before, after = reference["seconds"] / 60, routed["seconds"] / 60
    time_change = f"{'increased' if after > before else 'reduced'} total request time from {before:.1f} to {after:.1f} minutes"
    verdict = ("so the test did not detect a difference" if versus["p"] >= ALPHA
               else f"a difference the test detects (exact McNemar test, {p_text(versus['p'])})")
    others = len(snap.costs) - 2
    return (
        f"<p>Compared with {esc(reference['label'])}, {esc(routed['label'])} {cost_change} and {time_change}. "
        f"Its accuracy was {abs(100 * versus['difference']):.2f} percentage points {'lower' if versus['difference'] < 0 else 'higher'}, "
        f"with a 95% interval from {points(versus['low'])} to {points(versus['high'])}, {verdict}. The table also shows "
        f"{in_words(others)} cheaper models, each run alone on the same questions. For single configurations side by side, "
        'including the time per request, see <a href="#accuracy-cost-latency">Accuracy, cost and latency</a> below.</p>'
        f'<p class="note">The experiment combined stored {esc(decision["name"])} answers with new {esc(frontier["name"])} calls on '
        f"the same {count(held_out)} held-out questions; in it, one question is one decision. Human review time, human accuracy, "
        "production costs and the financial consequences of mistakes were not measured. The monetary figures are API cost "
        f"estimates. Request time is the total for all {count(held_out)} questions, not the latency of one question.</p>"
    )


def cost_summary(snap: Snapshot) -> str:
    fmt, held_out = snap.fmt, snap.plan["held_out"]
    reference = snap.costs[0]
    sentences = []
    for row in snap.costs[1:]:
        saving = 1 - row["cost"] / reference["cost"]
        versus = row["versus"]
        sentences.append(
            f'{esc(row["label"])} had an estimated API cost {fmt.pct(abs(saving), 0)} {"lower" if saving > 0 else "higher"} than '
            f'{esc(reference["label"])} ({usd(1000 * row["cost"] / held_out)} against {usd(1000 * reference["cost"] / held_out)} '
            f'per 1,000 questions). Its accuracy was {abs(100 * versus["difference"]):.2f} percentage points '
            f'{"lower" if versus["difference"] < 0 else "higher"} (95% interval {points(versus["low"])} to {points(versus["high"])} '
            f'points; exact McNemar test, {p_text(versus["p"])}).'
        )
    return (
        f"<p>On the {count(held_out)} held-out questions:</p>"
        + "<ul>" + "".join(f"<li>{sentence}</li>" for sentence in sentences) + "</ul>"
    )


def cost_setup(snap: Snapshot) -> str:
    """Each setup's access mode, cost basis and price dates; then the runs' batching, concurrency, prices and known
    price changes."""
    setups = []
    for row in snap.costs:
        access = " + ".join(dict.fromkeys(snap.billing(run)["access"] for run in row["runs"]))
        basis = " + ".join(dict.fromkeys(snap.billing(run)["cost_basis"] for run in row["runs"]))
        setups.append(
            f"<li><b>{esc(row['label'])}</b>: access mode {esc(access)}; cost basis {esc(basis)}; {esc(price_note(snap, row['runs']))}.</li>"
        )
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snap.costs:
        for run in row["runs"]:
            seen.setdefault((run["provider"], run["model"]), run)
    runs = []
    for run in seen.values():
        price = snap.price(run)
        price_text = (
            f"{price['text']} ({price['basis']}, {long_date(price['date'])}"
            + (f"; {price['change']}" if price.get("change") else "")
            + ")"
            if price
            else "no price"
        )
        runs.append(
            f"<li><b>{esc(run['name'])}</b>: {esc(run['access'])}; {run['questions_per_request']} "
            f"question{'s' if run['questions_per_request'] != 1 else ''} per request, {run['concurrency']} at a time. Price: {esc(price_text)}.</li>"
        )
    return (
        "<p><b>Access mode, cost basis and price dates</b></p><ul>" + "".join(setups) + "</ul>"
        "<p><b>Batching, concurrency and prices of each run</b></p><ul>" + "".join(runs) + "</ul>"
    )


def latency_text(run: dict[str, Any]) -> tuple[str, str]:
    """A run's time per request: median and 90th percentile with the requests in flight, only when it sent one question
    per request and recorded each request's time. A batch's time is never divided among its questions."""
    if run.get("median_request_seconds") is None:
        return "not recorded", ""
    if run["questions_per_request"] != 1:
        return f"batched ({run['questions_per_request']} per request)", ""
    seconds = f"{run['median_request_seconds']:.2f} s"
    if run.get("p90_request_seconds") is not None:
        seconds += f" / {run['p90_request_seconds']:.2f} s"
    return seconds, f"{run['concurrency']} at a time"


def latency_table(snap: Snapshot) -> str:
    """Single configurations side by side on all scored questions: accuracy, estimated API cost per 1,000 decisions, the
    time per request and the answers accepted at the threshold; then what the times include and which runs lack them."""
    fmt, threshold = snap.fmt, f"{snap.config['threshold']:.2f}"
    shown = [pick(snap.runs, spec, "latency_rows") for spec in snap.config["latency_rows"]]
    rows = []
    for run in shown:
        assert run is not None
        cost = per_thousand(run)
        if cost is None:
            cost_cell = "free tier, not priced" if run["billing"] == "free" else "self-hosted, not priced"
        else:
            cost_cell = usd(cost) + ('<span class="small">API-price estimate</span>' if run["billing"] == "subscription" else "")
        latency, in_flight = latency_text(run)
        sure = (run.get("confidence") or {}).get("sure") or {"questions": 0, "correct": 0}
        accepted = sure["questions"]
        rows.append(
            "<tr>"
            f'<td data-label="Configuration">{label_html(run)}</td>'
            f'<td class="num" data-label="Accuracy">{fmt.pct(run["correct"] / snap.total)}</td>'
            f'<td class="num" data-label="Estimated API cost per 1,000 decisions">{cost_cell}</td>'
            f'<td class="num" data-label="Latency per request (median / 90th percentile)">{latency}'
            + (f'<span class="small">{in_flight}</span>' if in_flight else "")
            + f'</td><td class="num" data-label="Accepted at {threshold}">{count(accepted)} ({fmt.pct(accepted / snap.total)})'
            f'<span class="small">{count(accepted - sure["correct"])} wrong</span></td>'
            "</tr>"
        )
    concurrent = sorted({run["concurrency"] for run in shown if run["concurrency"] > 1 and latency_text(run)[1]})
    untimed = [run for run in snap.runs if run.get("median_request_seconds") is None]
    examples = [pick(snap.runs, spec, "latency_untimed_examples") for spec in snap.config["latency_untimed_examples"]]
    if any(run is None or run.get("median_request_seconds") is not None for run in examples):
        raise ValueError("latency_untimed_examples names a run whose time per request was recorded")
    note = ("Latency is the time per request, measured from our machine with one question per request; it includes network "
            "time and any retry waits after errors. ")
    if concurrent:
        marked = f"Runs marked “{concurrent[0]} at a time”" if len(concurrent) == 1 else "Runs with several requests at a time"
        note += f"{marked} also include waiting behind our own parallel requests. "
    note += (
        "Hosted and self-hosted runs differ in setup, so latency compares setups, not models. "
        f"{opening_count(len(untimed))} runs, including {and_list(list(dict.fromkeys(run['name'] for run in examples)))}, ran "
        "before per-request timing was switched on, so their latency was not recorded. Costs are estimates at API list prices."
    )
    return (
        '<h3 id="accuracy-cost-latency">Accuracy, cost and latency</h3>'
        '<div class="table-wrap"><table class="overview cards latency"><thead><tr><th scope="col">Configuration</th>'
        f'<th scope="col" class="num">Accuracy<span class="small">all {count(snap.total)} questions</span></th>'
        '<th scope="col" class="num">Estimated API cost per 1,000 decisions<span class="small">one question is one decision</span></th>'
        '<th scope="col" class="num">Latency per request<span class="small">median / 90th percentile</span></th>'
        f'<th scope="col" class="num">Accepted at {threshold}<span class="small">share of questions; wrong among them</span></th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div><p class="note">{note}</p>'
    )


# How the lead finding names each setup of one model, in full on the page and briefly in the meta description.
SETUP_PHRASES = {
    "luna_api": ("Through OpenAI's Decisions API, which returns a probability for each option", "Decisions API"),
    "luna_stated": ("With the confidence it states itself", "stated confidence"),
}


def per_request_text(rows: list[dict[str, Any]]) -> str:
    return " versus ".join(str(row["run"]["questions_per_request"]) for row in rows)


ZERO_ERRORS = "Zero observed errors does not establish an error limit for future decisions."


def rule_text(threshold: str) -> str:
    """The rule the lead finding applies, stated before its numbers."""
    return (f"<p><b>The rule:</b> accept an answer only when the model reports a confidence of {threshold} or higher. Send "
            "every other answer to be checked, by a stronger model or a person.</p>")


def lead_finding(snap: Snapshot) -> str:
    """The finding under the page's headline: the rule, then what the lead rows let through, how many of those were wrong
    with the 95% error estimate range, and how many go to check."""
    fmt, rows, total = snap.fmt, snap.lead, count(snap.total)
    threshold = f"{snap.config['threshold']:.2f}"
    if len(rows) == 1:
        row = rows[0]
        name, accepted = esc(row["run"]["name"]), count(row["accepted"])
        if not row["accepted"]:
            text = f"{name} passed this rule on none of {total} non-English exam questions; all of them go to check."
        else:
            span = f"95% error estimate range {fmt.span(*row['error_range'])}"
            if row["errors"]:
                wrong = (f"{count(row['errors'])} of those {accepted} answers were wrong ({fmt.pct(row['error_rate'])} of "
                         f"accepted answers; {span}).")
            else:
                wrong = f"None of those {accepted} answers was wrong ({span})."
            text = (f"{name} passed this rule on {accepted} of {total} non-English exam questions ({fmt.pct(row['coverage'])}). "
                    f"{wrong} The other {count(row['sent'])} go to check." + ("" if row["errors"] else f" {ZERO_ERRORS}"))
    else:
        parts = [
            f"{esc(SETUP_PHRASES.get(row['key'], (label(row['run']), ''))[0])}: {count(row['accepted'])} answers passed "
            f"({fmt.pct(row['coverage'])} of questions), {fmt.pct(row['error_rate'])} of them wrong."
            for row in rows
        ]
        text = (
            f"{esc(rows[0]['run']['name'])} in {in_words(len(rows))} setups on {total} non-English exam questions. " + " ".join(parts)
            + f" The setups also differ in request format ({per_request_text(rows)} questions per request), so this does not "
            "isolate the confidence method."
        )
    return (
        f'<div class="finding"><p class="finding-label">Finding</p>{rule_text(threshold)}'
        f'<p>{text}</p><p class="small"><a href="#overview-confidence">See the confidence results</a></p></div>'
    )


def finding_sentence(snap: Snapshot) -> str:
    """The lead finding in one plain sentence, for the link preview's description and the images' alt text."""
    fmt, rows, total = snap.fmt, snap.lead, count(snap.total)
    threshold = f"{snap.config['threshold']:.2f}"
    if len(rows) == 1:
        row = rows[0]
        wrong = "zero observed errors" if not row["errors"] else f"{count(row['errors'])} wrong"
        span = f"; 95% error estimate range {fmt.span(*row['error_range'])}" if row["accepted"] else ""
        return (f"{row['run']['name']} on {total} non-English exam questions: {count(row['accepted'])} answers accepted at a "
                f"reported confidence of {threshold} or higher ({fmt.pct(row['coverage'])} of questions), {wrong}{span}.")
    parts = [
        f"{count(row['accepted'])} accepted with {count(row['errors'])} wrong ({SETUP_PHRASES.get(row['key'], ('', setting(row['run'])))[1]})"
        for row in rows
    ]
    return (f"{rows[0]['run']['name']} in {in_words(len(rows))} setups on {total} non-English exam questions, accepting only "
            f"answers with a reported confidence of {threshold} or higher: " + ", ".join(parts) + ".")


def confidence_lead(snap: Snapshot) -> str:
    """The Confidence section's opening: which decision model does best, measure by measure. It names no overall winner,
    and the build stops if one model ever leads every measure, since the sentence would then be wrong."""
    decision = [run for run in snap.runs if snap.decision_model(run)]
    best = max(decision, key=lambda run: run["correct"])
    tied = [run for run in decision if run is not best and shares_letter(run.get("group"), best.get("group"))]
    clean = [run for run in decision
             if (sure := (run.get("confidence") or {}).get("sure")) and sure["questions"] and sure["questions"] == sure["correct"]]
    surest = max(clean, key=lambda run: run["confidence"]["sure"]["questions"])
    stable = sorted((item for item in snap.whole_bank if not item["changed_answer"] and snap.decision_model(item)),
                    key=lambda item: item["model"] != surest["model"])
    if best is surest and all(item["model"] == best["model"] for item in stable):
        raise ValueError("one decision model leads every measure: the Confidence section's opening needs new wording")
    if tied:
        accuracy = (f"{and_list([best['name'], *(run['name'] for run in tied)])} could not be told apart on accuracy (exact "
                    f"McNemar tests on all {count(snap.results['group_pairs'])} pairs, Holm correction)")
    else:
        accuracy = f"{best['name']} was the most accurate"
    clauses = [accuracy, f"{snap.short(surest)} had the most answers accepted at {snap.config['threshold']:.2f} with zero "
                         f"observed errors ({count(surest['confidence']['sure']['questions'])})"]
    if stable:
        clauses.append(f"{and_list([snap.short(item) for item in stable])} changed no answers across "
                       f"{in_words(len(stable[0]['runs']))} runs of all {count(snap.total)} questions")
    return f"<p>{esc('No single decision model led on every measure: ' + '; '.join(clauses[:-1]) + '; and ' + clauses[-1])}.</p>"


def accuracy_lead(snap: Snapshot) -> str:
    """The Accuracy section's opening: the most accurate general-purpose models against the decision models. The build
    stops if the example no longer leads every decision model by ten points or costs ten times the dearest one."""
    fmt, example = snap.fmt, snap.named[snap.config["accuracy_example"]]
    decision = [run for run in snap.runs if snap.decision_model(run)]
    best = max(decision, key=lambda run: run["correct"])
    dearest = max(cost for run in decision if (cost := per_thousand(run)) is not None)
    example_cost = per_thousand(example)
    if (snap.decision_model(example) or example["correct"] - best["correct"] < 0.1 * snap.total
            or example_cost is None or example_cost < 10 * dearest):
        raise ValueError("the Accuracy section's opening no longer matches the data: rewrite it")
    return (
        f"<p>The most accurate general-purpose models were far more accurate on these questions: {esc(named(example))} answered "
        f"{fmt.pct(example['correct'] / snap.total)} correctly, against {fmt.pct(best['correct'] / snap.total)} for the most "
        f"accurate decision model, {esc(best['name'])}; decision models cost much less per question than those models and "
        "return a probability for every option.</p>"
    )


def model_kinds(snap: Snapshot) -> str:
    """How the two kinds of model answer: one example of each, and one of what reasoning changed. The build stops when an
    example no longer fits its sentence."""
    fmt, kinds = snap.fmt, snap.config["model_kinds"]
    decision, general = snap.named[kinds["decision"]], snap.named[kinds["general"]]
    low, high = (snap.named[key] for key in kinds["reasoning"])
    top = max(snap.runs, key=lambda run: run["correct"])
    standing = ("the most accurate configuration" if general is top
                else "one of the most accurate configurations" if shares_letter(general.get("group"), top.get("group")) else None)
    # The token count includes reasoning tokens: Codex CLI reports them in its output tokens (see the method section).
    tokens = round(general["output_tokens"] / general["answered_questions"])
    cost_ratio = per_thousand(high) / per_thousand(low)
    if (not snap.decision_model(decision) or latency_text(decision)[1] == "" or snap.decision_model(general)
            or standing is None or tokens > 50 or high["correct"] <= low["correct"]):
        raise ValueError("an example in 'How the two kinds of model answer' no longer fits its sentence")
    ratio = "almost twice the cost" if 1.75 <= cost_ratio < 2 else f"{cost_ratio:.1f} times the cost"

    def grammar(run: dict[str, Any]) -> str:
        return fmt.pct(run["groups"]["grammar"]["correct"] / run["groups"]["grammar"]["questions"])

    return (
        '<aside class="explainer" aria-labelledby="model-kinds-title">'
        '<p class="explainer-title" id="model-kinds-title">How the two kinds of model answer</p>'
        "<p>A decision model reads the question and the options, and returns a probability for each option. It does not write "
        f"an answer. This makes it cheap and fast: {esc(decision['name'])} has an estimated API cost of {usd(per_thousand(decision))} "
        f"per 1,000 decisions, with a median latency of {decision['median_request_seconds']:.2f} seconds.</p>"
        f"<p>A general-purpose model writes its answer, and it can reason first. In this test, {standing} wrote very little: "
        f"{esc(general['name'])}, with {esc(general['reasoning'])} reasoning, used about {tokens} output tokens per question, "
        f"reasoning tokens included, and answered {fmt.pct(general['correct'] / snap.total)} correctly. So reasoning does not "
        "explain the accuracy gap here, and the benchmark does not isolate what does.</p>"
        f"<p>Reasoning did help some models: {esc(low['name'])} went from {grammar(low)} to {grammar(high)} on grammar between "
        f"{esc(low['reasoning'])} and {esc(high['reasoning'])} effort, at {ratio}.</p></aside>"
    )


def reasoning_table(snap: Snapshot) -> str:
    """Each reasoning pair from page_config.json: the same model at two settings."""
    fmt = snap.fmt
    rows = []
    for pair in snap.config["reasoning_pairs"]:
        for key in pair:
            run = snap.named[key]
            per_thousand = (
                usd(1000 * run["api_equivalent_usd"] / run["answered_questions"]) if run.get("api_equivalent_usd") is not None else "Not estimated"
            )
            in_flight = f", {run['concurrency']} requests at a time" if run["concurrency"] > 1 else ""
            grammar = run["groups"]["grammar"]
            rows.append(
                f"<tr><td>{esc(run['name'])}</td><td>{esc(run['reasoning'] or '—')}</td>"
                f'<td class="num">{fmt.pct(run["correct"] / snap.total)}</td><td class="num">{fmt.pct(grammar["correct"] / grammar["questions"])}</td>'
                f'<td class="num">{count(round(run["output_tokens"] / run["answered_questions"]))}</td><td class="num">{per_thousand}</td>'
                f'<td class="num">{minutes(run["request_seconds"])} min{in_flight}</td></tr>'
            )
    return (
        '<div class="table-wrap"><table class="static"><thead><tr><th>Model</th><th>Reasoning</th><th class="num">Score</th>'
        '<th class="num">Grammar</th><th class="num">Output tokens per question</th><th class="num">Estimated API cost per 1,000 questions</th>'
        f'<th class="num">Request time</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


# The page's headline, also its title and the link preview's.
HEADLINE = "When should you trust an AI model to make a decision?"


def head(snap: Snapshot, images: dict[str, dict[str, str]]) -> str:
    site = snap.config["site_url"]
    preview = snap.config["images"]["preview"]
    title = HEADLINE
    description = (
        "Accuracy, confidence, answer stability and cost across decision models and general-purpose models, evaluated on "
        "non-English exam questions. Methods, code and recorded answers."
    )
    # The link preview's description and alt text state the finding its image shows; the image is the dark one, like the site.
    finding = finding_sentence(snap)
    shared = f"{finding} Methods, code and recorded answers."
    alt = f"Bar chart. {finding}"
    image = site + images["preview"]["dark"]
    return "\n".join(
        [
            "",
            f"  <title>{esc(title.rstrip('.'))}</title>",
            f'  <link rel="canonical" href="{esc(site)}">',
            f'  <meta name="description" content="{esc(description)}">',
            f'  <meta property="og:title" content="{esc(title)}">',
            f'  <meta property="og:description" content="{esc(shared)}">',
            '  <meta property="og:type" content="website">',
            f'  <meta property="og:url" content="{esc(site)}">',
            f'  <meta property="og:image" content="{esc(image)}">',
            f'  <meta property="og:image:width" content="{preview["width"]}">',
            f'  <meta property="og:image:height" content="{preview["height"]}">',
            f'  <meta property="og:image:alt" content="{esc(alt)}">',
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{esc(title)}">',
            f'  <meta name="twitter:description" content="{esc(shared)}">',
            f'  <meta name="twitter:image" content="{esc(image)}">',
            f'  <meta name="twitter:image:alt" content="{esc(alt)}">',
            "  ",
        ]
    )


def share_link(paths: dict[str, str], name: str) -> str:
    """'Share figure' downloads the image in the theme being viewed; a small link offers the other one."""
    buttons = "".join(
        f'<a class="button secondary theme-{theme}" href="{esc(paths[theme])}" download>Share figure</a>' for theme in THEMES
    )
    others = "".join(
        f'<a class="theme-{theme}" href="{esc(paths[other])}" download>{other} version</a>'
        for theme, other in (("dark", "light"), ("light", "dark"))
    )
    return f'<p class="share">{buttons} <span class="small">{esc(name)}, PNG · {others}</span></p>'


def blocks(snap: Snapshot, images: dict[str, dict[str, str]]) -> dict[str, str]:
    lead_names = ", ".join(dict.fromkeys(row["run"]["name"] for row in snap.lead))
    return {
        "head": head(snap, images),
        "lead-finding": lead_finding(snap),
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
    }


# ---------------------------------------------------------------- the page


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
        "bg": "#1e293b", "text": "#e2e8f0", "values": "#e2e8f0", "sub": "#cbd5e1", "muted": "#94a3b8", "rule": "#334155",
        "ok": "#cbd5e1", "wrong": "#e879f9", "check": "#334155", "stripe": "#475569", "key-border": "#64748b",
        "outline": "#64748b", "track": "#273449", "reading": "#60a5fa", "grammar": "#fb923c",
        "reading-text": "#60a5fa", "grammar-text": "#fb923c",
    },
    "light": {
        "bg": "#ffffff", "text": "#0f172a", "values": "#1e293b", "sub": "#334155", "muted": "#475569", "rule": "#e2e8f0",
        "ok": "#334155", "wrong": "#c026d3", "check": "#e2e8f0", "stripe": "#cbd5e1", "key-border": "#cbd5e1",
        "outline": "#64748b", "track": "#f1f5f9", "reading": "#2563eb", "grammar": "#ea580c",
        "reading-text": "#1d4ed8", "grammar-text": "#c2410c",
    },
}
# The main images are the dark ones; the light ones are for reports and slides.
THEMES = tuple(IMAGE_THEMES)
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
# How an image names a confidence source, shorter than the page.
SHORT_SOURCES = {"Probability of the chosen option": "option probability", "Stated by the model": "stated confidence"}


def figure_page(size: dict[str, int], scale: dict[str, int], body: str, theme: str) -> str:
    palette = "; ".join(f"--{name}: {value}" for name, value in IMAGE_THEMES[theme].items())
    style = f":root {{ {palette}; }}" + FIGURE_STYLE % {**size, **scale}
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{style}</style></head><body>{body}</body></html>'


def footer(snap: Snapshot, caveat: str) -> str:
    """The image's caveats in readable type, then its data version, results version, date and address."""
    results = snap.results
    site = snap.config["site_url"].removeprefix("https://").rstrip("/")
    dataset = (results["dataset"]["graded_sha256"] or results["dataset"]["sha256"])[:8]
    return (
        f'<p class="caveat">{count(snap.total)} non-English exam questions (reading and grammar), not market predictions or financial tasks. {esc(caveat)}</p>'
        f'<p class="foot">Data {esc(results["dataset"]["name"])} ({dataset}) · results {esc(results["results_version"])} · '
        f"published {long_date(snap.config['published'])} · {esc(site)}</p>"
    )


def image_label(row: dict[str, Any]) -> str:
    run = row["run"]
    details = [part for part in (setting(run), SHORT_SOURCES.get(row["source"], row["source"].lower())) if part]
    return f'<span class="row-label">{esc(run["name"])}<span class="muted"> · {esc(" · ".join(details))}</span></span>'


def finding_image(snap: Snapshot, size: dict[str, int], compact: bool, theme: str) -> str:
    """The lead finding as an image: its rows only, each with answers accepted and sent to check, then the wrong
    answers, their share of the accepted ones and the 95% error estimate range."""
    fmt, threshold, rows = snap.fmt, f"{snap.config['threshold']:.2f}", snap.lead
    items = []
    for row in rows:
        bar = stack_html(row, snap).replace(' aria-hidden="true"', "")
        first = f'{count(row["accepted"])} accepted ({fmt.pct(row["coverage"])} of questions) · {count(row["sent"])} sent to check'
        if not row["accepted"]:
            second = "Error rate not applicable"
        elif row["errors"]:
            second = (f'<span class="wrong">{count(row["errors"])} wrong</span>: {fmt.pct(row["error_rate"])} of accepted answers '
                      f'(95% error estimate range {fmt.span(*row["error_range"])})')
        else:
            second = f'<span class="wrong">Zero observed errors</span> (95% error estimate range {fmt.span(*row["error_range"])})'
        items.append(f'<div>{image_label(row)}{bar}<p class="vals">{first}<br>{second}</p></div>')
    name = rows[0]["run"]["name"]
    if len(rows) == 1:
        title = f"{name}: answers accepted at a reported confidence of {threshold} or higher"
        caveat = (f"{ZERO_ERRORS} " if rows[0]["accepted"] and not rows[0]["errors"] else "") + (
            "The range is a 95% Wilson interval for the error rate among accepted answers."
        )
    else:
        title = f"{name}, {in_words(len(rows))} setups: answers accepted at a reported confidence of {threshold} or higher"
        caveat = f"The setups also differ in request format ({per_request_text(rows)} questions per request), so this does not isolate the confidence method."
    legend = ('<i class="key ok"></i>accepted and correct · <i class="key wrong"></i>accepted but wrong · '
              '<i class="key check"></i>sent to check')
    # A single bar is drawn larger, so that it does not sit between wide empty bands.
    one = len(rows) == 1
    if compact:
        scale = {"pad": 36, "title": 40, "sub": 22, "gap": 18, "label": 42 if one else 30, "bar": 84 if one else 32,
                 "value": 34 if one else 25, "caveat": 20, "foot": 15, "part": 0, "num": 0}
        sub = legend
    else:
        scale = {"pad": 52, "title": 58, "sub": 30, "gap": 34, "label": 62 if one else 44, "bar": 140 if one else 54,
                 "value": 54 if one else 38, "caveat": 26, "foot": 20, "part": 0, "num": 0}
        sub = f"Each bar is all {count(snap.total)} scored questions: {legend}"
    body = f'<h1>{esc(title)}</h1><p class="sub">{sub}</p><div class="rows">{"".join(items)}</div>' + footer(snap, caveat)
    return figure_page(size, scale, body, theme)


def task_image(snap: Snapshot, size: dict[str, int], theme: str) -> str:
    fmt = snap.fmt
    scale = {"pad": 46, "title": 56, "sub": 28, "gap": 16, "label": 30, "bar": 30, "value": 28, "caveat": 22, "foot": 18, "part": 160, "num": 120}
    items = []
    for row in snap.tasks:
        pairs = "".join(
            f'<div class="pair"><span class="{part}">{name}</span><span class="track"><span class="bar {part}" style="width: {100 * row[part]:.2f}%"></span></span>'
            f'<span class="num">{fmt.pct(row[part])}</span></div>'
            for part, name in (("reading", "Reading"), ("grammar", "Grammar"))
        )
        items.append(f'<div><p class="row-label">{esc(row["run"]["name"])}<span class="muted">{esc(" · " + setting(row["run"]) if setting(row["run"]) else "")}</span></p>{pairs}</div>')
    sub = f"Accuracy on {count(snap.reading_questions)} reading and {count(snap.grammar_questions)} grammar questions; selected configurations, axis 0–100%"
    caveat = "Performance on one task type does not establish performance on another; these results do not identify the cause of the gap."
    body = f'<h1>Strong reading scores, weaker grammar scores</h1><p class="sub">{esc(sub)}</p><div class="rows">{"".join(items)}</div>' + footer(snap, caveat)
    return figure_page(size, scale, body, theme)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[16:24]
    return int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big")


def render_images(snap: Snapshot, names: dict[str, dict[str, str]]) -> None:
    chrome = os.environ.get("CHROME", "google-chrome")
    sizes = snap.config["images"]
    pages = {
        "preview": (lambda theme: finding_image(snap, sizes["preview"], True, theme), sizes["preview"]),
        "finding": (lambda theme: finding_image(snap, sizes["share"], False, theme), sizes["share"]),
        "tasks": (lambda theme: task_image(snap, sizes["share"], theme), sizes["share"]),
    }
    SHARE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        for key, (page, size) in pages.items():
            for theme in THEMES:
                source, target = Path(work) / f"{key}-{theme}.html", ROOT / names[key][theme]
                source.write_text(page(theme), encoding="utf-8")
                subprocess.run(
                    [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={work}/profile",
                     "--force-device-scale-factor=1", "--hide-scrollbars", f"--window-size={size['width']},{size['height']}",
                     f"--screenshot={target}", source.as_uri()],
                    check=True, capture_output=True,
                )
                if png_size(target) != (size["width"], size["height"]):
                    raise SystemExit(f"{target} is {png_size(target)}, not {size['width']}x{size['height']}")
                os.chmod(target, 0o644)
                print(f"Wrote {target.relative_to(ROOT)} ({size['width']}x{size['height']})")
    # Before the first public post, earlier versions go; after it, they stay, so that posted previews keep working.
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
    """The main X post for the lead finding: the rule first, then one model in two setups, or one configuration with its
    accuracy on all questions and its repeats."""
    rows, fmt, site, threshold, total = snap.lead, snap.fmt, snap.config["site_url"], numbers["threshold"], numbers["questions"]

    def number(fraction: float) -> str:
        return fmt.pct(fraction).rstrip("%")

    rule = (f"We tested a simple rule for trusting a model's answers: accept an answer only when the model reports a "
            f"confidence of {threshold} or higher, and send every other answer to a stronger model or a person.")
    if len(rows) == 2:
        first, second = rows
        return (
            f"{rule}\n\n"
            f"We tested one model, {first['run']['name']}, in two setups on {total} non-English exam questions.\n"
            f"Setup 1, OpenAI's Decisions API, which returns a probability for each option: {count(first['accepted'])} answers "
            f"passed ({number(first['coverage'])}% of questions), {count(first['errors'])} wrong ({number(first['error_rate'])}%).\n"
            f"Setup 2, {second['run']['name'].split()[-1]} states its own confidence: {count(second['accepted'])} passed "
            f"({number(second['coverage'])}%), {count(second['errors'])} wrong ({number(second['error_rate'])}%).\n\n"
            "The setups also used different request formats, so this does not isolate the confidence method. It does not set an "
            "error limit for future tasks. Exam questions, not market predictions.\n\n"
            f"{site}"
        )
    row = rows[0]
    run, item = row["run"], snap.repeats_by_key.get(row["key"])
    if not row["accepted"]:
        raise ValueError(f"the lead finding, {label(run)}, accepts no answers")
    if row["errors"]:
        wrong = (f"{count(row['errors'])} of those {count(row['accepted'])} answers were wrong ({number(row['error_rate'])}%; 95% "
                 f"error estimate range {fmt.span(*row['error_range'])}).")
    else:
        wrong = f"None of those {count(row['accepted'])} answers was wrong."
    passed = (f"it passed the rule on {count(row['accepted'])} ({number(row['coverage'])}%). {wrong} The other "
              f"{count(row['sent'])} went to check.")
    if snap.decision_model(run):
        result = (f"{run['name']} is a decision model: it chooses from given options and returns a probability for each option. "
                  f"On {total} non-English exam questions, {passed}")
    else:
        result = f"{run['name']} was tested on {total} non-English exam questions: {passed}"
    accuracy = (f"On all {total} questions, its accuracy was {number(run['correct'] / snap.total)}%. The rule kept only the "
                "answers it was sure of.")
    if not row["errors"]:
        accuracy += (" Zero observed errors does not set an error limit for future decisions: the 95% error estimate range runs "
                     f"up to {number(row['error_range'][1])}%.")
    parts = [rule, result, accuracy]
    if item:
        runs = in_words(len(item["runs"]))
        stable = "it chose the same option on every question" if not item["changed_answer"] else f"it changed its answer on {count(item['changed_answer'])} questions"
        parts.append(
            f"In {runs} repeated runs, {stable}. Stable is not the same as correct: it repeated the same wrong answer on "
            f"{count(item['wrong_every_run_same'])} questions."
        )
    parts += ["Exam questions, not market predictions.", site]
    return "\n\n".join(parts)


def cost_post(snap: Snapshot, numbers: dict[str, str]) -> str:
    """The follow-up on cost and latency: one decision model against a more accurate reference, from the same values as
    the Accuracy, cost and latency table."""
    fmt, site = snap.fmt, snap.config["site_url"]
    model, reference = (snap.named[snap.config["cost_post"][key]] for key in ("model", "reference"))
    model_cost, reference_cost = per_thousand(model), per_thousand(reference)
    if model_cost is None or reference_cost is None or not latency_text(model)[1] or reference["correct"] <= model["correct"]:
        raise ValueError("the cost post needs a priced, timed one-question model and a priced, more accurate reference")
    accurate = "far more accurate" if reference["correct"] - model["correct"] >= 0.1 * snap.total else "more accurate"
    measured = ("" if latency_text(reference)[1]
                else f" {reference['name']}'s latency was not measured the same way.")
    return (
        f"{model['name']} costs {usd(model_cost)} per 1,000 decisions, with a median latency of "
        f"{model['median_request_seconds']:.2f} seconds ({model['p90_request_seconds']:.2f} s at the 90th percentile). "
        f"{reference['name']} costs about {usd(reference_cost)} per 1,000, roughly {times(reference_cost / model_cost)} times more, "
        f"but it is {accurate}: {fmt.pct(reference['correct'] / snap.total)} against {fmt.pct(model['correct'] / snap.total)} on "
        f"the same {numbers['questions']} non-English exam questions.\n\n"
        "Costs are estimates at API list prices. Latency was measured from our machine, one question per request, including "
        f"network time.{measured}\n\n{site}"
    )


def x_posts(snap: Snapshot, numbers: dict[str, str], names: dict[str, dict[str, str]]) -> str:
    glide = next(row for row in snap.tasks if row["key"] == "glide")
    site, fmt = snap.config["site_url"], snap.fmt

    def number(fraction: float) -> str:
        return fmt.pct(fraction).rstrip("%")

    def length_note(text: str) -> str:
        return " Longer than one post: needs a long-post account or a thread." if x_length(text) > X_POST_LIMIT else ""

    main = main_post(snap, numbers)
    costs = cost_post(snap, numbers)
    follow = (
        f"{glide['run']['name'].split()[-1]}, a decision model, scored {number(glide['reading'])}% on reading questions and "
        f"{number(glide['grammar'])}% on grammar questions in our benchmark of {numbers['questions']} non-English exam questions.\n\n"
        "Performance on one kind of task does not establish performance on another. We compare decision models with "
        "general-purpose models and report the task scores separately.\n\n"
        "Inspect the tested configurations, methods, code and recorded answers:\n\n"
        f"{site}"
    )
    results = snap.results
    lines = [
        "# X posts",
        "",
        f"Generated by build_page.py from results {results['results_version']} (data {numbers['dataset_version']}), published "
        f"{numbers['published']}. Do not edit by hand: run the build again. The images are the dark versions; each has a light "
        "one next to it, with `light` in place of `dark` in its name.",
        "",
        f"## Main post: confidence and checking ({x_length(main)} characters as X counts them)",
        "",
        f"Attach `{names['finding']['dark']}`." + (" Longer than one post: it needs a long-post account, or split it into a thread with the caveat paragraph in the first post's image." if x_length(main) > X_POST_LIMIT else ""),
        "",
        "```text",
        main,
        "```",
        "",
        f"## Follow-up: cost and latency ({x_length(costs)} characters as X counts them)",
        "",
        "No image." + length_note(costs),
        "",
        "```text",
        costs,
        "```",
        "",
        f"## Follow-up: task differences ({x_length(follow)} characters as X counts them)",
        "",
        f"Attach `{names['tasks']['dark']}`." + length_note(follow),
        "",
        "```text",
        follow,
        "```",
        "",
    ]
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
        version = results["results_version"]
        names = {
            key: {theme: f"share/{stem}-{theme}-{version}.png" for theme in THEMES}
            for key, stem in (("preview", "preview"), ("finding", "finding"), ("tasks", "reading-grammar"))
        }
        numbers = values(snap)
        page = PAGE.read_text(encoding="utf-8")
        filled = fill(page, numbers, blocks(snap, names))
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"error: {error!r}", file=sys.stderr)
        return 1
    if filled != page:
        PAGE.write_text(filled, encoding="utf-8")
        print(f"Updated {PAGE.relative_to(ROOT)}")
    else:
        print(f"{PAGE.relative_to(ROOT)} is up to date")
    if not args.no_images:
        render_images(snap, names)
    X_POSTS.parent.mkdir(parents=True, exist_ok=True)
    X_POSTS.write_text(x_posts(snap, numbers, names), encoding="utf-8")
    print(f"Wrote {X_POSTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
