"""What every page of the v3 preview shares: the data, setup names, links between pages and the page shell (head,
navigation bar, footer). The preview lives in v3/; the site's data (results.json, answers.json, charts/) stays one
folder up, where the live pages read it."""

from __future__ import annotations

import html
import json
from functools import cached_property
from pathlib import Path
from typing import Any

import benchmark_metrics as bm
import build_page as bp

# The site's folder (results.json, page_config.json, charts/) and the preview's folder inside it.
ROOT = Path(__file__).resolve().parent.parent.parent
V3 = ROOT / "v3"
KICKER = "Zeki Works · Decision models · answer key v2"
ISSUE_URL = "https://github.com/zekiworks/analysis/issues/new?template="
REPO_URL = "https://github.com/zekiworks/analysis"
esc = html.escape

# The navigation bar of every page, in order: (path inside v3/, label). The brand links to the home page.
MENU = (
    ("questions/", "Every question"),
    ("disagreements/", "Where models disagree"),
    ("topics/", "Topics"),
    ("compare/", "Compare"),
    ("method/", "Method"),
    ("data/", "Data"),
)
# A value nobody measured reads as words; a value a filter leaves out is a dash with its reason; a zero is a number.
NOT_MEASURED = '<span class="nm">Not measured</span>'


def rel(origin: str, target: str) -> str:
    """A relative link from the page at origin to target, both paths inside v3/ ('' is its home page, 'models/145/')."""
    up = "../" * origin.count("/")
    return (up + target) or "./"


def up(origin: str, target: str) -> str:
    """A relative link from the page at origin (a path inside v3/) to target in the site's folder: results.json,
    answers.json, charts/."""
    return "../" * (origin.count("/") + 1) + target


def topbar(path: str) -> str:
    """The bar at the top of every page: the brand, which links home, the navigation bar and the theme switch."""
    current = ' aria-current="page"'
    links = "".join(
        f'<li><a href="{rel(path, target)}"{current if path.startswith(target) else ""}>{esc(label)}</a></li>' for target, label in MENU
    )
    return (
        '<header class="topbar">\n'
        f'    <a class="brand" href="{rel(path, "")}">{esc(KICKER)}</a>\n'
        f'    <nav class="nav" aria-label="Pages"><ul>{links}</ul></nav>\n'
        '    <div class="theme-switch" role="group" aria-label="Colour theme" hidden><button type="button" class="key" '
        'data-theme-choice="dark" aria-pressed="true" aria-label="Dark background"><span class="lamp" aria-hidden="true"></span>'
        'Dark<span class="long"> background</span></button><button type="button" class="key" data-theme-choice="light" '
        'aria-pressed="false" aria-label="Light background"><span class="lamp" aria-hidden="true"></span>Light<span class="long">'
        " background</span></button></div>\n"
        "  </header>"
    )


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
        """A whole preview page at path (inside v3/): head, top bar with the navigation bar, body, footer. Kept out of
        search engines, like every page of the preview."""
        root = rel(path, "")
        extra = "".join(f'\n  <script src="{rel(path, script)}" defer></script>' for script in scripts)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Zeki Works</title>
  <meta name="robots" content="noindex">
  <meta name="description" content="{esc(description)}">
  <script>document.documentElement.classList.add("js"); try {{ if (localStorage.getItem("theme") === "light") document.documentElement.dataset.theme = "light"; }} catch (e) {{}}</script>
  <link rel="stylesheet" href="{root}v3.css">
  <script src="{root}site.js" defer></script>{extra}
</head>
<body class="v3">
  <a class="skip" href="#main">Skip to content</a>
  {topbar(path)}
  <main id="main">
{body}
  </main>
  <footer class="footer">
    <p>Download: <a href="{up(path, "results.json")}" download>results.json</a> · <a href="{up(path, "answers.json")}" download>answers.json</a></p>
    <p>{self.version()}</p>
  </footer>
</body>
</html>
"""
