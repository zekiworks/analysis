#!/usr/bin/env python3
"""Fill the page's generated parts from one data snapshot: docs/results.json, with page_config.json.

    python3 build_page.py               # the page, the sharing images and the X posts
    python3 build_page.py --no-images   # without the images (no Chrome needed)

Every number in the overview, in the sharing images and in the X posts comes from the snapshot. docs/index.html
keeps the copy; this script rewrites what is inside its markers:

- <span data-value="key">…</span>: a number or a short text from values();
- <!-- build:name --> … <!-- /build:name -->: a block from blocks() (tables, bars, meta tags).

The images are drawn by headless Chrome from HTML made here, from the same rows as the page, and saved under
docs/share/ with the results version in their names; share/x-posts.md holds the announcement text.
reproduce.py must pass first, and the build stops otherwise. Set CHROME to use another Chrome or Chromium binary.
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

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PAGE = DOCS / "index.html"
SHARE = DOCS / "share"
X_POSTS = ROOT / "share" / "x-posts.md"
VALUE = re.compile(r'(<span data-value="([a-z0-9_]+)">)(.*?)(</span>)', re.S)
BLOCK = re.compile(r"(<!-- build:([a-z0-9-]+) -->)(.*?)(<!-- /build:\2 -->)", re.S)
CHECKS = re.compile(r"^(\d+) checks match, (\d+) differ$", re.M)
# The X counts every link as this many characters.
X_LINK_LENGTH = 23
X_POST_LIMIT = 280

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


def usd(value: float) -> str:
    return f"${value:.2f}"


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
        # Each section orders its rows by its own measure, ties in the configuration's order: confidence rows by
        # answers accepted, after the preview rows; task rows by overall accuracy, before the reference rows;
        # stability rows by changed answers, fewest first.
        thresholds = [row for spec in config["confidence_rows"] if (row := self.threshold_row(spec))]
        self.thresholds = [row for row in thresholds if row["preview"]] + sorted(
            (row for row in thresholds if not row["preview"]), key=lambda row: -row["accepted"]
        )
        tasks = [row for spec in config["accuracy_rows"] if (row := self.task_row(spec))]
        self.tasks = sorted((row for row in tasks if not row["reference"]), key=lambda row: -row["overall"]) + [
            row for row in tasks if row["reference"]
        ]
        whole_bank = [item for spec in config["stability_whole_bank"] if (item := pick(results["repeats"], spec, "stability"))]
        for item in whole_bank:
            if not item["whole_bank"] or item["questions_per_request"] != 1:
                raise ValueError(f"{label(item)}: its repeats are not one question per request over the whole bank")
        self.whole_bank = sorted(whole_bank, key=lambda item: item["changed_answer"])
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
            "preview": spec.get("preview", False),
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
            {"label": f"{named(frontier)}, alone", "runs": [frontier], "accuracy": measured["frontier_accuracy"], "versus": None,
             "cost": measured["frontier_cost_usd"], "seconds": measured["frontier_request_seconds"]},
            {"label": f"{named(decision)}, then {named(frontier)}", "runs": [decision, frontier], "accuracy": measured["accuracy"],
             "versus": {key: measured[key] for key in ("difference", "low", "high", "p")},
             "cost": measured["cost_usd"], "seconds": measured["request_seconds"]},
        ]
        for alternative_spec in spec["alternatives"]:
            alternative = pick(measured["alternatives"], alternative_spec, "cost alternatives")
            assert alternative is not None
            rows.append({"label": f"{named(alternative)}, alone", "runs": [self.main_run(alternative)], "accuracy": alternative["accuracy"],
                         "versus": alternative["versus_frontier"], "cost": alternative["cost_usd"], "seconds": alternative["request_seconds"]})
        return plan, rows

    def billing(self, run: dict[str, Any]) -> dict[str, str]:
        return self.config["billing"][run["billing"]]

    def price(self, run: dict[str, Any]) -> dict[str, Any] | None:
        return self.prices.get((run["provider"], run["model"]))


# ---------------------------------------------------------------- values for the page's spans


def values(snap: Snapshot) -> dict[str, str]:
    results, fmt = snap.results, snap.fmt
    out = {
        "threshold": f"{snap.config['threshold']:.2f}",
        "questions": count(snap.total),
        "models": count(snap.models),
        "configs": count(len(snap.runs)),
        "reading_questions": count(snap.reading_questions),
        "grammar_questions": count(snap.grammar_questions),
        "grammar_share": f"{100 * snap.grammar_questions / snap.total:.0f}%",
        "published": long_date(snap.config["published"]),
        "results_version": results["results_version"],
        "dataset_version": f"{results['dataset']['name']} ({(results['dataset']['graded_sha256'] or results['dataset']['sha256'])[:8]})",
        "checks": count(snap.checks),
        "comparisons": count(len(results["paired"])),
        "significant": count(sum(item["p_holm"] < 0.05 for item in results["paired"])),
        "pairs": count(results["group_pairs"]),
        "held_out": count(snap.plan["held_out"]),
        # Repeat runs beyond each configuration's leaderboard run, as in the answer export.
        "repeat_runs": count(len({run for item in results["repeats"] for run in item["runs"]} - snap.by_id.keys())),
    }
    for row in snap.thresholds:
        if row["key"]:
            out[f"{row['key']}_accepted"] = count(row["accepted"])
            out[f"{row['key']}_coverage"] = fmt.pct(row["coverage"])
            out[f"{row['key']}_correct"] = count(row["correct"])
            out[f"{row['key']}_errors"] = count(row["errors"])
            out[f"{row['key']}_error_rate"] = fmt.pct(row["error_rate"]) if row["error_rate"] is not None else "not applicable"
            out[f"{row['key']}_error_high"] = fmt.pct(row["error_range"][1]) if row["error_range"] else "not applicable"
            out[f"{row['key']}_accuracy_low"] = fmt.pct(1 - row["error_range"][1]) if row["error_range"] else "not applicable"
            out[f"{row['key']}_per_request"] = count(row["run"]["questions_per_request"])
    for row in snap.tasks:
        if row["key"]:
            out[f"{row['key']}_reading"] = fmt.pct(row["reading"])
            out[f"{row['key']}_grammar"] = fmt.pct(row["grammar"])
    for spec in snap.config["stability_whole_bank"]:
        item = pick(results["repeats"], spec, "stability") if spec.get("key") else None
        if item:
            out[f"{spec['key']}_changed"] = count(item["changed_answer"])
            out[f"{spec['key']}_changed_share"] = fmt.pct(item["changed_answer"] / item["questions"], 0)
    return out


# ---------------------------------------------------------------- blocks


def stack_html(row: dict[str, Any], snap: Snapshot) -> str:
    """The three segments of a threshold bar, as shares of all scored questions."""
    total = snap.total
    widths = [100 * row["correct"] / total, 100 * row["errors"] / total]
    wrong_class = "wrong nonzero" if row["errors"] else "wrong"
    return (
        '<span class="stack" aria-hidden="true">'
        f'<span class="ok" style="flex-basis: {widths[0]:.3f}%"></span>'
        f'<span class="{wrong_class}" style="flex-basis: {widths[1]:.3f}%"></span>'
        '<span class="check"></span></span>'
    )


def threshold_figure(snap: Snapshot) -> str:
    fmt, total = snap.fmt, snap.total
    items = []
    for row in snap.thresholds:
        run = row["run"]
        items.append(
            "<li>"
            f'<p class="bar-label">{label_html(run)}<span class="small">Confidence: {esc(row["source"].lower())}</span></p>'
            + stack_html(row, snap)
            + '<p class="bar-values">'
            f'<span><i class="key ok"></i>Accepted and correct: {count(row["correct"])} ({fmt.share(row["correct"], total)})</span> '
            f'<span class="v-wrong"><i class="key wrong"></i>Accepted but wrong: {count(row["errors"])} ({fmt.share(row["errors"], total)})</span> '
            f'<span><i class="key check"></i>Sent to check: {count(row["sent"])} ({fmt.share(row["sent"], total)})</span>'
            "</p></li>"
        )
    threshold = f"{snap.config['threshold']:.2f}"
    return (
        '<figure class="threshold-figure" aria-labelledby="threshold-title">'
        f'<figcaption id="threshold-title">Confidence of {threshold} or higher, applied to recorded answers. Each bar is all {count(total)} '
        "scored questions; percentages are shares of all of them.</figcaption>"
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
    return (
        '<figure class="task-figure" aria-labelledby="task-title">'
        '<figcaption id="task-title" class="figure-title">Strong reading scores, weaker grammar scores</figcaption>'
        f'<ul class="task-bars">{"".join(items)}</ul>'
        '<p class="axis" aria-hidden="true"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></p>'
        f'<p class="caption">{count(snap.reading_questions)} reading questions and {count(snap.grammar_questions)} grammar questions. '
        "Selected configurations. Performance on one task type does not establish performance on another. "
        "These results do not identify the cause of the gap.</p></figure>"
    )


def results_table(snap: Snapshot) -> str:
    fmt = snap.fmt
    rows = []
    for run in snap.runs:
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
            f'<td class="num" data-label="Reading">{fmt.pct(groups["reading"]["correct"] / groups["reading"]["questions"])}</td>'
            f'<td class="num" data-label="Grammar">{fmt.pct(groups["grammar"]["correct"] / groups["grammar"]["questions"])}</td>'
            f'<td class="group" data-label="Group">{esc(run.get("group") or "—")}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview results">'
        '<thead><tr><th scope="col">Model and setting</th><th scope="col" class="num">Overall</th><th scope="col" class="num">Reading</th>'
        '<th scope="col" class="num">Grammar</th><th scope="col">Group</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def stability_table(items: list[dict[str, Any]], fmt: Format) -> str:
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f'<td data-label="Configuration">{label_html(item)}</td>'
            f'<td class="num" data-label="Runs">{len(item["runs"])}</td>'
            f'<td class="num" data-label="Questions">{count(item["questions"])}</td>'
            f'<td class="num" data-label="Changed answers">{count(item["changed_answer"])}'
            f'<span class="small">{fmt.pct(item["changed_answer"] / item["questions"])} of questions</span></td>'
            f'<td class="num" data-label="Same mistake in every run">{count(item["wrong_every_run_same"])}'
            f'<span class="small">of {count(item["wrong_any"])} questions answered wrong in any run</span></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards">'
        '<thead><tr><th scope="col">Configuration</th><th scope="col" class="num">Runs</th><th scope="col" class="num">Questions</th>'
        '<th scope="col" class="num">Changed answers</th><th scope="col" class="num">Same mistake in every run</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def stability(snap: Snapshot) -> str:
    sample = snap.sample[0]["questions"] if snap.sample else 0
    return (
        '<h3 id="stability-whole-bank">Whole bank, one question per request</h3>'
        + stability_table(snap.whole_bank, snap.fmt)
        + f'<h3 id="stability-sample">Fixed sample of {count(sample)} questions, '
        f'{snap.config["stability_sample_questions_per_request"]} questions per request</h3>'
        + stability_table(snap.sample, snap.fmt)
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
    fmt, held_out = snap.fmt, snap.plan["held_out"]
    rows = []
    for row in snap.costs:
        versus = row["versus"]
        difference = (
            "reference"
            if versus is None
            else f'{points(versus["difference"])} points<span class="small">95% interval {points(versus["low"])} to {points(versus["high"])}; {p_text(versus["p"])}</span>'
        )
        access = " + ".join(dict.fromkeys(snap.billing(run)["access"] for run in row["runs"]))
        basis = " + ".join(dict.fromkeys(snap.billing(run)["cost_basis"] for run in row["runs"]))
        per_request = " / ".join(str(run["questions_per_request"]) for run in row["runs"])
        rows.append(
            "<tr>"
            f'<td class="setup" data-label="Setup"><span class="model-name">{esc(row["label"])}</span>'
            f'<span class="small">Access mode: {esc(access)}</span>'
            f'<span class="small">Cost basis: {esc(basis)}</span>'
            f'<span class="small">Questions per request: {per_request}</span></td>'
            f'<td class="num" data-label="Accuracy">{fmt.pct(row["accuracy"])}</td>'
            f'<td class="num" data-label="Difference from the first row">{difference}</td>'
            f'<td class="num" data-label="Cost per 1,000 questions">{usd(1000 * row["cost"] / held_out)}'
            f'<span class="small">{esc(price_note(snap, row["runs"]))}</span></td>'
            f'<td class="num" data-label="Request time">{row["seconds"] / 60:.1f} min<span class="small">for {count(held_out)} questions</span></td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="overview cards costs">'
        '<thead><tr><th scope="col">Setup</th><th scope="col" class="num">Accuracy</th><th scope="col" class="num">Difference from the first row</th>'
        '<th scope="col" class="num">Cost per 1,000 questions</th><th scope="col" class="num">Request time</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def cost_summary(snap: Snapshot) -> str:
    fmt, held_out = snap.fmt, snap.plan["held_out"]
    reference = snap.costs[0]
    sentences = []
    for row in snap.costs[1:]:
        saving = 1 - row["cost"] / reference["cost"]
        versus = row["versus"]
        sentences.append(
            f'{esc(row["label"])} cost {fmt.pct(saving, 0)} less than {esc(reference["label"])} '
            f'({usd(1000 * row["cost"] / held_out)} against {usd(1000 * reference["cost"] / held_out)} per 1,000 questions). '
            f'Its accuracy was {abs(100 * versus["difference"]):.2f} points {"lower" if versus["difference"] < 0 else "higher"} '
            f'(95% interval {points(versus["low"])} to {points(versus["high"])} points; exact McNemar test, {p_text(versus["p"])}).'
        )
    return "<ul>" + "".join(f"<li>{sentence}</li>" for sentence in sentences) + "</ul>"


def cost_setup(snap: Snapshot) -> str:
    """Price dates, known price changes, batching and concurrency of the runs in the cost comparison."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snap.costs:
        for run in row["runs"]:
            seen.setdefault((run["provider"], run["model"]), run)
    items = []
    for run in seen.values():
        price = snap.price(run)
        price_text = (
            f"{price['text']} ({price['basis']}, {long_date(price['date'])}"
            + (f"; {price['change']}" if price.get("change") else "")
            + ")"
            if price
            else "no price"
        )
        items.append(
            f"<li><b>{esc(run['name'])}</b>: {esc(run['access'])}; {run['questions_per_request']} "
            f"question{'s' if run['questions_per_request'] != 1 else ''} per request, {run['concurrency']} at a time. Price: {esc(price_text)}.</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def head(snap: Snapshot, images: dict[str, str]) -> str:
    site = snap.config["site_url"]
    preview = snap.config["images"]["preview"]
    title = "Test decision models before you automate."
    description = (
        "Accuracy, confidence, answer stability and cost across decision models and generative models, evaluated on Turkish "
        "exam questions. Methods, code and recorded answers."
    )
    rows = [row for row in snap.thresholds if row["preview"]]
    alt = (
        f"{rows[0]['run']['name']} in two setups on {count(snap.total)} Turkish exam questions: answers accepted at a confidence of "
        f"{snap.config['threshold']:.2f} or higher, and how many of them were wrong."
        if rows
        else title
    )
    image = site + images["preview"]
    return "\n".join(
        [
            "",
            f"  <title>{esc(title.rstrip('.'))}</title>",
            f'  <meta name="description" content="{esc(description)}">',
            f'  <meta property="og:title" content="{esc(title)}">',
            f'  <meta property="og:description" content="{esc(description)}">',
            '  <meta property="og:type" content="website">',
            f'  <meta property="og:url" content="{esc(site)}">',
            f'  <meta property="og:image" content="{esc(image)}">',
            f'  <meta property="og:image:width" content="{preview["width"]}">',
            f'  <meta property="og:image:height" content="{preview["height"]}">',
            f'  <meta property="og:image:alt" content="{esc(alt)}">',
            '  <meta name="twitter:card" content="summary_large_image">',
            f'  <meta name="twitter:title" content="{esc(title)}">',
            f'  <meta name="twitter:description" content="{esc(description)}">',
            f'  <meta name="twitter:image" content="{esc(image)}">',
            f'  <meta name="twitter:image:alt" content="{esc(alt)}">',
            "  ",
        ]
    )


def share_link(path: str, name: str) -> str:
    return f'<p class="share"><a class="button secondary" href="{esc(path)}" download>Share figure</a> <span class="small">{esc(name)}, PNG</span></p>'


def blocks(snap: Snapshot, images: dict[str, str]) -> dict[str, str]:
    return {
        "head": head(snap, images),
        "threshold-figure": threshold_figure(snap) + share_link(images["confidence"], "Confidence threshold figure"),
        "threshold-table": threshold_table(snap),
        "task-figure": task_figure(snap) + share_link(images["tasks"], "Reading and grammar figure"),
        "results-table": results_table(snap),
        "stability": stability(snap),
        "cost-table": cost_table(snap),
        "cost-summary": cost_summary(snap),
        "cost-setup": cost_setup(snap),
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

FIGURE_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: %(width)dpx; height: %(height)dpx; overflow: hidden; background: #fff; color: #0f172a;
  font-family: "Helvetica Neue", Arial, "Liberation Sans", sans-serif; }
body { padding: %(pad)dpx; display: flex; flex-direction: column; }
h1 { font-size: %(title)dpx; line-height: 1.1; letter-spacing: -.01em; }
.sub { font-size: %(sub)dpx; color: #334155; margin-top: .25em; }
.rows { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: %(gap)dpx; }
.head { display: flex; justify-content: space-between; align-items: baseline; gap: 24px; }
.row-label { font-size: %(label)dpx; font-weight: 700; white-space: nowrap; }
.row-label .muted { font-weight: 400; color: #475569; }
.nums { font-size: %(value)dpx; color: #1e293b; text-align: right; white-space: nowrap; }
.nums b.wrong, .vals b.wrong { color: #b91c1c; }
.vals { font-size: %(value)dpx; color: #1e293b; margin-top: .15em; }
.stack { display: flex; height: %(bar)dpx; margin-top: .2em; border-radius: 4px; overflow: hidden; background: #e2e8f0; }
.stack .ok { background: #334155; flex-grow: 0; flex-shrink: 0; } .stack .wrong { background: #dc2626; flex-grow: 0; flex-shrink: 0; }
.stack .wrong.nonzero { min-width: 7px; }
.stack .check { flex: 1 1 0; background: repeating-linear-gradient(135deg, #e2e8f0 0 10px, #cbd5e1 10px 20px); }
.caveat { font-size: %(caveat)dpx; color: #1e293b; border-top: 2px solid #e2e8f0; padding-top: .45em; line-height: 1.3; }
.foot { font-size: %(foot)dpx; color: #475569; margin-top: .3em; }
.pair { display: grid; grid-template-columns: %(part)dpx 1fr %(num)dpx; align-items: center; gap: 16px; font-size: %(value)dpx; }
.track { height: %(bar)dpx; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
.bar { display: block; height: 100%%; }
.reading { color: #1d4ed8; } .grammar { color: #c2410c; }
.bar.reading { background: #2563eb; } .bar.grammar { background: #ea580c; }
.num { text-align: right; font-weight: 700; }
"""
# How an image names a confidence source, shorter than the page.
SHORT_SOURCES = {"Probability of the chosen option": "option probability", "Stated by the model": "stated confidence"}


def figure_page(size: dict[str, int], scale: dict[str, int], body: str) -> str:
    style = FIGURE_STYLE % {**size, **scale}
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{style}</style></head><body>{body}</body></html>'


def footer(snap: Snapshot, caveat: str) -> str:
    """The image's caveats in readable type, then its data version, results version, date and address."""
    results = snap.results
    site = snap.config["site_url"].removeprefix("https://").rstrip("/")
    dataset = (results["dataset"]["graded_sha256"] or results["dataset"]["sha256"])[:8]
    return (
        f'<p class="caveat">{count(snap.total)} Turkish exam questions (reading and grammar), not market predictions or financial tasks. {esc(caveat)}</p>'
        f'<p class="foot">Data {esc(results["dataset"]["name"])} ({dataset}) · results {esc(results["results_version"])} · '
        f"published {long_date(snap.config['published'])} · {esc(site)}</p>"
    )


def image_label(row: dict[str, Any]) -> str:
    run = row["run"]
    details = [part for part in (setting(run), SHORT_SOURCES.get(row["source"], row["source"].lower())) if part]
    return f'<span class="row-label">{esc(run["name"])}<span class="muted"> · {esc(" · ".join(details))}</span></span>'


def threshold_image(snap: Snapshot, rows: list[dict[str, Any]], size: dict[str, int], compact: bool) -> str:
    fmt, total, threshold = snap.fmt, snap.total, f"{snap.config['threshold']:.2f}"
    items = []
    for row in rows:
        bar = stack_html(row, snap).replace(' aria-hidden="true"', "")
        if row["accepted"]:
            wrong = f'<b class="wrong">{count(row["errors"])} wrong</b> ({fmt.pct(row["error_rate"])}; range {fmt.span(*row["error_range"])})'
        else:
            wrong = "none accepted"
        if compact:
            wrong_long = wrong.replace(f"{fmt.pct(row['error_rate'])};", f"{fmt.pct(row['error_rate'])} of accepted;") if row["accepted"] else wrong
            items.append(
                f"<div>{image_label(row)}{bar}"
                f'<p class="vals">{count(row["accepted"])} accepted ({fmt.pct(row["coverage"])}) · {wrong_long}<br>'
                f'{count(row["sent"])} sent to check</p></div>'
            )
        else:
            items.append(
                f'<div><p class="head">{image_label(row)}<span class="nums">{count(row["accepted"])} accepted · {wrong}</span></p>{bar}</div>'
            )
    if compact:
        scale = {"pad": 40, "title": 42, "sub": 24, "gap": 18, "label": 31, "bar": 36, "value": 26, "caveat": 21, "foot": 16, "part": 0, "num": 0}
        title = f"{rows[0]['run']['name']}, two setups: answers accepted at a confidence of {threshold} or higher"
        sub = "Dark: accepted and correct · red: accepted but wrong · striped: sent to check"
        formats = " against ".join(str(row["run"]["questions_per_request"]) for row in rows)
        caveat = f"The setups also differ in request format ({formats} questions per request), so this does not isolate the confidence method."
    else:
        scale = {"pad": 46, "title": 54, "sub": 27, "gap": 13, "label": 30, "bar": 24, "value": 28, "caveat": 22, "foot": 18, "part": 0, "num": 0}
        title = f"What gets through a {threshold} confidence threshold?"
        sub = (f"Each bar is all {count(total)} scored questions. Dark: accepted and correct · red: accepted but wrong · striped: sent to check. "
               "Wrong % is of accepted answers.")
        caveat = ("The range is the 95% Wilson interval of that error rate, not an error limit for future decisions. "
                  "The two GPT-6 Luna rows also differ in request format.")
    body = f'<h1>{esc(title)}</h1><p class="sub">{esc(sub)}</p><div class="rows">{"".join(items)}</div>' + footer(snap, caveat)
    return figure_page(size, scale, body)


def task_image(snap: Snapshot, size: dict[str, int]) -> str:
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
    return figure_page(size, scale, body)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[16:24]
    return int.from_bytes(data[:4], "big"), int.from_bytes(data[4:], "big")


def render_images(snap: Snapshot, names: dict[str, str]) -> None:
    chrome = os.environ.get("CHROME", "google-chrome")
    sizes = snap.config["images"]
    pages = {
        "preview": (threshold_image(snap, [row for row in snap.thresholds if row["preview"]], sizes["preview"], True), sizes["preview"]),
        "confidence": (threshold_image(snap, snap.thresholds, sizes["share"], False), sizes["share"]),
        "tasks": (task_image(snap, sizes["share"]), sizes["share"]),
    }
    SHARE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        for key, (page, size) in pages.items():
            source, target = Path(work) / f"{key}.html", DOCS / names[key]
            source.write_text(page, encoding="utf-8")
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
    current = {DOCS / name for name in names.values()}
    for old in SHARE.glob("*.png"):
        if old not in current:
            old.unlink()
            print(f"Removed {old.relative_to(ROOT)}")


# ---------------------------------------------------------------- X posts


def x_length(text: str) -> int:
    return len(re.sub(r"https?://\S+", "x" * X_LINK_LENGTH, text))


def x_posts(snap: Snapshot, numbers: dict[str, str], names: dict[str, str]) -> str:
    rows = {row["key"]: row for row in snap.thresholds if row["key"]}
    api, stated = rows["luna_api"], rows["luna_stated"]
    glide = next(row for row in snap.tasks if row["key"] == "glide")
    site, fmt = snap.config["site_url"], snap.fmt

    def number(fraction: float) -> str:
        return fmt.pct(fraction).rstrip("%")

    main = (
        f"We tested one model, {api['run']['name']}, in two setups on {numbers['questions']} Turkish exam questions. In both setups, "
        f"we accepted only answers with a confidence of {numbers['threshold']} or higher.\n\n"
        f"Setup 1, OpenAI's Decisions API, which returns a probability for each option: {count(api['accepted'])} answers accepted "
        f"({number(api['coverage'])}% of questions), {count(api['errors'])} wrong ({number(api['error_rate'])}%).\n"
        f"Setup 2, {stated['run']['name'].split()[-1]} states its own confidence: {count(stated['accepted'])} accepted "
        f"({number(stated['coverage'])}%), {count(stated['errors'])} wrong ({number(stated['error_rate'])}%).\n\n"
        "The setups also used different request formats, so this does not isolate the confidence method. It does not set an error "
        "limit for future tasks. Exam questions, not market predictions.\n\n"
        f"{site}"
    )
    follow = (
        f"{glide['run']['name'].split()[-1]}, a decision model, scored {number(glide['reading'])}% on reading questions and "
        f"{number(glide['grammar'])}% on grammar questions in our Turkish benchmark.\n\n"
        "Performance on one kind of task does not establish performance on another. We compare decision models with generative "
        "models and report the task scores separately.\n\n"
        "Inspect the tested configurations, methods, code and recorded answers:\n\n"
        f"{site}"
    )
    results = snap.results
    lines = [
        "# X posts",
        "",
        f"Generated by build_page.py from results {results['results_version']} (data {numbers['dataset_version']}), published "
        f"{numbers['published']}. Do not edit by hand: run the build again.",
        "",
        f"## Main post: confidence and checking ({x_length(main)} characters as X counts them)",
        "",
        f"Attach `docs/{names['confidence']}`." + (" Longer than one post: it needs a long-post account, or split it into a thread with the caveat paragraph in the first post's image." if x_length(main) > X_POST_LIMIT else ""),
        "",
        "```text",
        main,
        "```",
        "",
        f"## Follow-up: task differences ({x_length(follow)} characters as X counts them)",
        "",
        f"Attach `docs/{names['tasks']}`." + (" Longer than one post: needs a long-post account or a thread." if x_length(follow) > X_POST_LIMIT else ""),
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
        results = json.loads((DOCS / "results.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / "page_config.json").read_text(encoding="utf-8"))
        snap = Snapshot(results, config, reproduce())
        version = results["results_version"]
        names = {
            "preview": f"share/preview-{version}.png",
            "confidence": f"share/confidence-{version}.png",
            "tasks": f"share/reading-grammar-{version}.png",
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
