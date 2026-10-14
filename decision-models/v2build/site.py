"""What every v2 page shares: the data, setup names, links between pages and the page shell (head, menu, footer)."""

from __future__ import annotations

import html
import json
from functools import cached_property
from pathlib import Path
from typing import Any

import benchmark_metrics as bm
import build_page as bp

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "v2"
SITE_URL = "https://zekiworks.github.io/analysis/decision-models/v2/"
KICKER = "Zeki Works · Decision models · answer key v2"
ISSUE_URL = "https://github.com/zekiworks/analysis/issues/new?template="
REPO_URL = "https://github.com/zekiworks/analysis"
esc = html.escape

# Every page's menu, in order: (path under v2/, label). The home page's own link list is in v2/index.html.
MENU = (
    ("", "Home"),
    ("questions/", "Every question"),
    ("disagreements/", "Where models disagree with the answer key"),
    ("topics/", "Topics"),
    ("compare/", "Compare"),
    ("method/", "Method"),
    ("data/", "Data"),
)
NOT_MEASURED = '<span class="hint" tabindex="0" data-tip="Not measured">—</span>'


def rel(origin: str, target: str) -> str:
    """A relative link from the page at origin to target, both paths under v2/ ('' is the home page, 'models/145/')."""
    up = "../" * origin.count("/")
    return (up + target) or "./"


def pct(fraction: float, digits: int = 1) -> str:
    return f"{100 * fraction:.{digits}f}%"


def interval(correct: int, total: int) -> str:
    low, high = bm.wilson_interval(correct, total)
    return f"{pct(low)} to {pct(high)}"


def latency_text(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    return f"{1000 * seconds:.0f}\u00a0ms" if seconds < 1 else f"{seconds:.{2 if seconds < 10 else 1}f}\u00a0s"


def request_size(size: int) -> str:
    return f"{bp.count(size)} question{'' if size == 1 else 's'} per request"


class Site:
    """results.json, page_config.json and, when a page needs it, answers.json."""

    def __init__(self) -> None:
        self.results: dict[str, Any] = json.loads((ROOT / "results.json").read_text())
        self.config: dict[str, Any] = json.loads((ROOT / "page_config.json").read_text())
        self.runs: list[dict[str, Any]] = self.results["runs"]
        self.by_id = {run["run"]: run for run in self.runs}
        self.total: int = self.results["questions"]
        self.units: list[dict[str, Any]] = self.results["units"]

    @cached_property
    def answers(self) -> dict[str, Any]:
        return json.loads((ROOT / "answers.json").read_text())

    @cached_property
    def scored(self) -> list[int]:
        """Indices into answers.json's question columns of the scored questions: all but the key audit's exclusions."""
        status = self.answers["questions"]["status"]
        return [index for index, value in enumerate(status) if value != "excluded"]

    @cached_property
    def answer_runs(self) -> dict[int, dict[str, Any]]:
        """Each leaderboard run's per-question answers, by run id."""
        return {item["run"]: item for item in self.answers["runs"]}

    def decision(self, run: dict[str, Any]) -> bool:
        return run["provider"] in self.config["decision_model_providers"] and run["model"] not in self.config["not_decision_models"]

    def kind(self, run: dict[str, Any]) -> str:
        return "Decision model" if self.decision(run) else "Chat model"

    def part(self, unit_number: int) -> str:
        return "reading" if unit_number in self.config["reading_units"] else "grammar"

    def unit(self, number: int) -> dict[str, Any]:
        return next(unit for unit in self.units if unit["number"] == number)

    @staticmethod
    def accuracy(run: dict[str, Any]) -> tuple[int, int]:
        groups = run["groups"]
        return groups["reading"]["correct"] + groups["grammar"]["correct"], groups["reading"]["questions"] + groups["grammar"]["questions"]

    def ranked(self) -> list[dict[str, Any]]:
        """Every setup by accuracy on all questions, highest first."""
        return sorted(self.runs, key=lambda run: -self.accuracy(run)[0])

    @staticmethod
    def detail(run: dict[str, Any]) -> str:
        """A setup's variant, reasoning setting and request size: 'low reasoning · 16 questions per request'."""
        parts = [run["variant"]] if run.get("variant") else []
        if run.get("reasoning"):
            parts.append(bp.reasoning_label(run["reasoning"]))
        parts.append(request_size(run["questions_per_request"]))
        return " · ".join(parts)

    def full_name(self, run: dict[str, Any]) -> str:
        return f"{run['name']} · {self.detail(run)}"

    @staticmethod
    def model_path(run: dict[str, Any]) -> str:
        return f"models/{run['run']}/"

    def model_cell(self, origin: str, run: dict[str, Any], kind: bool = False) -> str:
        """A table cell naming a setup, linked to its page, with its details under the name."""
        extra = f" · {self.kind(run)}" if kind else ""
        return (f'<td class="model"><a class="model-name" href="{rel(origin, self.model_path(run))}">{esc(run["name"])}</a>'
                f'<span class="small">{esc(self.detail(run))}{extra}</span></td>')

    def per_thousand(self, run: dict[str, Any]) -> float | None:
        return bp.per_thousand(run)

    def version(self) -> str:
        results = self.results
        return (f"Results {esc(results['results_version'])}, updated {bp.long_date(results['updated'])}; "
                f"answer key version {results['answer_key']['version']}.")

    def page(self, path: str, title: str, description: str, body: str, scripts: tuple[str, ...] = ()) -> str:
        """A whole v2 page at path (under v2/): head, menu, body, footer. Kept out of search engines, like the home page."""
        root = rel(path, "")
        current = ' aria-current="page"'
        menu = "".join(
            f'<li><a href="{rel(path, target)}"{current if target == path else ""}>{esc(label)}</a></li>'
            for target, label in MENU
        )
        extra = "".join(f'\n  <script src="{rel(path, script)}" defer></script>' for script in scripts)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Zeki Works</title>
  <meta name="robots" content="noindex">
  <meta name="description" content="{esc(description)}">
  <script>try {{ if (localStorage.getItem("theme") === "light") document.documentElement.dataset.theme = "light"; }} catch (e) {{}}</script>
  <link rel="stylesheet" href="{root}../style.css">
  <link rel="stylesheet" href="{root}v2.css">
  <script src="{root}site.js" defer></script>{extra}
</head>
<body class="v2">
  <header class="v2-top">
    <div class="theme-switch" role="group" aria-label="Colour theme" hidden><button type="button" data-theme-choice="dark" aria-pressed="true">Dark background</button><button type="button" data-theme-choice="light" aria-pressed="false">Light background</button></div>
    <p class="kicker"><a href="{root}">{esc(KICKER)}</a></p>
    <nav class="v2-nav" aria-label="Pages"><ul>{menu}</ul></nav>
  </header>
  <main>
{body}
  </main>
  <footer class="v2-footer">
    <p>Download: <a href="{root}../results.json" download>results.json</a> · <a href="{root}../answers.json" download>answers.json</a></p>
    <p>{self.version()}</p>
  </footer>
</body>
</html>
"""
