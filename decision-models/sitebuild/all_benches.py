"""All benches (TITLE, the project lead's name for it, bus #4172): every Zeki Works bench for the decision models on one
page, laid out after the Jev Decision Index page in the site's own style (project lead, bus #4057), and its Methodology
page. They live outside the Reading site, at /analysis/all-benches/ and /analysis/all-benches/method/ (page_config.json
all_benches.url): the build writes them into the git-ignored folder OUT (_suite/all-benches/) with copies of every file
they use (ASSETS), so the folder works on its own; the publishing step copies it to the mirror's analysis/all-benches/.
Their header is the suite strip with All benches marked, then the page's own title row (its name and the theme switch),
no Reading tabs. The old addresses in the Reading site, all-benches/ and all-benches/method/, are redirects to the new
ones that keep the query and the fragment.

Data: only the benches' published bench-scores.json files, one schema for the three sites (#4062): this site's own three
Reading benches, Reading · Turkish, Reading · English and Reading · Vision (#4173; sitebuild/bench_scores.py, the same
rows its bench-scores.json publishes; their keys here stay reading, reading-english and reading-vision) and the Logic &
Math and Backgammon sites' files at their published addresses (page_config.json all_benches.benches), which the build
reads and keeps in SNAPSHOT (in the repo, copied into OUT): a file the address does not serve yet is "not published yet"
on the page; when the address cannot be reached, the build keeps what it read before. Models join across benches by
Hugging Face repo, else by name and kind (join_key). Every score is 0 to 100: 0 = chance (Backgammon: a random
legal-move player's error rate), 100 = perfect. The combined score is the plain mean of Reading · Turkish, Logic & Math
and Backgammon, for a model on all three only, and only where one model answered every bench (page_config.json
all_benches.not_combined lists the rows where it did not); learning from experience (improvement points) stays outside
it. Two scores closer than their margin (margin) read "tied", the one rule the Methodology page states (#tied); no
interval or range is shown.

The page in order: the line on what it measures; the ranking (a column chart of the decision models, each bar in its
maker's colour with the maker's mark under it, the score switch, Combined · Reading · Turkish · Reading · English ·
Reading · Vision · Logic & Math · Backgammon, and the size slider; it opens on the #1 decision model); How it's scored;
Head to head; Full results; the three charts (size, calibration error and latency against the score); their score against
ours for the index's 15 models; one tab per bench. ?model=<name> shows one model's page instead (all-benches.js).
Without JavaScript the page is the default view's static parts and every bench's table."""

from __future__ import annotations

import json
import math
import statistics
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

import build_page as bp
from sitebuild import bench_scores
from sitebuild.site import (ROOT, SUITE_CSS, THEME_SWITCH, Site, asset, billions, esc, family_icon, family_sprite,
                            model_families, rel, suite_bar)

# The page's name (project lead, bus #4172: final); never "Index".
TITLE = "All benches"
# The folder the build writes for /analysis/all-benches/ (git-ignored), and the pages' paths inside it.
OUT = "_suite/all-benches/"
PATH = ""
METHOD = "method/"
# The files the two pages use, copied into OUT beside them, so the folder needs nothing from the Reading site.
ASSETS = (SUITE_CSS, "v3.css", "site.js", "all-benches.css", "all-benches.js")
# The pages' earlier addresses in the Reading site, now redirects to the new ones.
OLD_PATH = "all-benches/"
OLD_METHOD = "all-benches/method/"
# What the build last read from the other sites (in the repo, so the next build can fall back on it), with its copy in
# OUT, which the Methodology page links.
SNAPSHOT = "all-benches/benches.json"
SNAPSHOT_COPY = "benches.json"
UP, DOWN = "\u2191", "\u2193"
# This site's benches in the page's order, (key, label), after Combined and before the other sites' benches
# (page_config.json all_benches.benches). The keys stay as they were before Reading was split (#4173). The combined score
# averages COMBINED.
READING = (("reading", "Reading · Turkish"), ("reading-english", "Reading · English"), ("reading-vision", "Reading · Vision"))
COMBINED = ("reading", "logic", "backgammon")
KINDS = (("decision", "Decision models"), ("chat", "Chat models"), ("program", "Programs"))
NOT_PUBLISHED = "not published yet"
NOT_TIMED = "not timed on the pinned machine yet"
PINNED = "spark2, a DGX Spark (GB10)"
GREY = "#64748b"


def norm(text: str) -> str:
    """A name for matching: lower case letters and digits only, accents dropped ("Sthānika AI" and "Sthanika AI" match)."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(char for char in plain.lower() if char.isalnum())


def number(value: float, digits: int = 1) -> str:
    """A score as the page writes it, with a true minus sign."""
    text = f"{value:.{digits}f}"
    return "\u2212" + text[1:] if text.startswith("-") and text.strip("-0.") else text.lstrip("-")


def kind_of(row: dict[str, Any]) -> str:
    """decision, chat or program, whichever way a file words it ("decision model", "chat")."""
    kind = (row.get("kind") or "").lower()
    return "decision" if kind.startswith("decision") else "program" if kind.startswith("program") else "chat"


# ---------------------------------------------------------------------------------------------------------------- data


def fetch(url: str) -> tuple[str, Any]:
    """A published file: ("published", its JSON), ("missing", None) when the address serves no file (404), or
    ("unreachable", reason) when it could not be read."""
    request = urllib.request.Request(url, headers={"User-Agent": "zekiworks-reading-build", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return "published", json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return ("missing", None) if error.code == 404 else ("unreachable", f"HTTP {error.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        return "unreachable", str(error)


def file_benches(data: Any) -> list[dict[str, Any]]:
    """The bench objects of a bench-scores.json: one at the top, or several under "benches" (this site's)."""
    items = data.get("benches") if isinstance(data, dict) and "benches" in data else [data]
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("models"), list) or not all(
                isinstance(row.get("name"), str) and isinstance((row.get("raw") or {}).get("questions"), int)
                for row in item["models"]):
            raise ValueError("not in the bench-scores.json schema")
    return items


def external(site: Site) -> tuple[list[dict[str, Any]], str]:
    """The other sites' benches as page_config.json lists them, each with its file's bench (or None until published),
    read now; and the snapshot JSON the build keeps (all-benches/benches.json). An address that cannot be read keeps
    its earlier snapshot."""
    path = ROOT / SNAPSHOT
    before = json.loads(path.read_text()).get("benches", {}) if path.exists() else {}
    today = datetime.now(timezone.utc).date().isoformat()
    kept, out = {}, []
    for spec in site.config["all_benches"]["benches"]:
        status, data = fetch(spec["url"])
        previous = before.get(spec["key"])
        if status == "published":
            try:
                file_benches(data)
            except ValueError as error:
                status, data = "unreachable", str(error)
        if status == "unreachable":
            print(f"all-benches: {spec['url']} could not be read ({data}); "
                  + ("kept the earlier copy" if previous else "shown as not published yet"))
            entry = previous or {"url": spec["url"], "published": False, "seen": today, "file": None}
        else:
            entry = {"url": spec["url"], "published": status == "published", "seen": today,
                     "file": data if status == "published" else None}
            if previous and previous.get("published") == entry["published"] and previous.get("file") == entry["file"]:
                entry["seen"] = previous["seen"]
        kept[spec["key"]] = entry
        bench = None
        if entry["published"]:
            found = file_benches(entry["file"])
            bench = next((item for item in found if ("vision" in str(item.get("bench", ""))) == (spec["board"] == "vision")),
                         None)
        out.append({**spec, "bench": bench, "feed": spec["url"], "seen": entry["seen"]})
        print(f"all-benches: {spec['label']}: " + (f"published, {len(bench['models'])} rows" if bench else NOT_PUBLISHED))
    snapshot = {"about": "The other benches' bench-scores.json as this site's build last read them from their published "
                         "addresses (sitebuild/all_benches.py): file null while an address serves none; seen: the "
                         "first build that read this state.", "benches": kept}
    return out, json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n"


def join_key(row: dict[str, Any], shared: set[str]) -> str:
    """A row's key across benches: its repo, unless two rows of its bench name the same repo (Laya and Laya
    multilingual); else its name and kind."""
    repo = (row.get("repo") or "").lower()
    if repo and repo not in shared:
        return "repo:" + repo
    return f"name:{norm(row['name'])}|{kind_of(row)}"


def slug(name: str) -> str:
    return "-".join("".join(char if char.isalnum() else " " for char in name.lower()).split())


def latency(site: Site, run_id: int) -> dict[str, float] | None:
    """A Text tab run's time per request on the pinned machine, median and 95th percentile (nearest rank) in ms, from
    answers.json's request_seconds."""
    item = site.answer_runs.get(run_id) or site.answer_runs.get(str(run_id))
    seconds = sorted(value for value in (item or {}).get("request_seconds") or [] if value is not None)
    if not seconds:
        return None
    return {"median": 1000 * statistics.median(seconds), "p95": 1000 * seconds[math.ceil(0.95 * len(seconds)) - 1],
            "requests": len(seconds), "run": run_id}


class Data:
    """The benches and the models joined across them."""

    def __init__(self, site: Site) -> None:
        self.site = site
        config = site.config["all_benches"]
        mine = bench_scores.benches(site)
        feed = site.config["site_url"] + bench_scores.PATH
        others, self.snapshot = external(site)
        self.benches: list[dict[str, Any]] = [
            *({"key": key, "label": label, "bench": bench, "feed": feed, "seen": None} for (key, label), bench in zip(READING, mine)),
            *others]
        self.by_key = {bench["key"]: bench for bench in self.benches}
        colours = json.loads((ROOT / "maker_colours.json").read_text())
        self.maker_colour = {norm(maker): entry["colour"] for maker, entry in colours["makers"].items()}
        self.program_colour = colours["programs"]["colour"]
        self.maker_family = {}
        for family in model_families():
            self.maker_family.setdefault(norm(family["maker"]), family["name"])
        self.training = config["training"]
        self.missing_colours: set[str] = set()
        self.models: dict[str, dict[str, Any]] = {}
        for bench in self.benches:
            if bench["bench"]:
                self.add(bench)
        for model in self.models.values():
            model["combined"] = (statistics.fmean(model["scores"][key]["score_0_100"] for key in COMBINED)
                                 if all(key in model["scores"] for key in COMBINED) else None)
        # Rows whose benches one model did not answer (page_config.json all_benches.not_combined): their per-bench
        # scores stay, their combined score goes, with the reason the combined board and their page give.
        self.not_combined: list[dict[str, Any]] = []
        for entry in config["not_combined"]:
            match = entry["match"]
            key = ("repo:" + match["repo"].lower() if match.get("repo")
                   else f"name:{norm(match['name'])}|{match['kind']}")
            if key not in self.models:
                raise SystemExit(f"page_config.json all_benches.not_combined: no row matches {match}")
            self.models[key]["combined"] = None
            self.models[key]["not_combined"] = entry["reason"]
            self.not_combined.append(self.models[key])
        self.latency_runs(config["latency_runs"])
        self.their = config["their_score"]
        for item in self.their["models"]:
            self.colour(item["maker"], "decision")
        slugs = Counter(model["slug"] for model in self.models.values())
        for model in self.models.values():
            if slugs[model["slug"]] > 1:
                model["slug"] += "-" + model["kind"]

    def colour(self, maker: str | None, kind: str) -> str:
        if kind == "program" or not maker:
            return self.program_colour
        found = self.maker_colour.get(norm(maker))
        if not found:
            self.missing_colours.add(maker)
        return found or GREY

    def add(self, bench: dict[str, Any]) -> None:
        rows = [row for row in bench["bench"]["models"] if isinstance(row.get("score_0_100"), (int, float))]
        repos = Counter((row.get("repo") or "").lower() for row in rows if row.get("repo"))
        shared = {repo for repo, count in repos.items() if count > 1}
        for row in rows:
            key = join_key(row, shared)
            kind = kind_of(row)
            model = self.models.get(key)
            if model is None:
                family = None
                text_run = next((run for run in row.get("runs") or [] if str(run).startswith("text:")), None)
                if bench["key"] == "reading" and text_run:
                    family = self.site.families[int(str(text_run).split(":")[1])]["name"]
                family = family or self.maker_family.get(norm(row.get("maker") or ""))
                training = self.training.get(row.get("repo") or "") or self.training.get(row["name"])
                model = self.models[key] = {
                    "key": key, "name": row["name"], "slug": slug(row["name"]), "maker": row.get("maker"), "kind": kind,
                    "repo": row.get("repo"), "family": family, "colour": self.colour(row.get("maker"), kind),
                    "tag": training["tag"] if training else None, "size": row.get("params_total"),
                    "active": row.get("params_active"), "scores": {}, "latency": None, "not_combined": None}
            model["scores"][bench["key"]] = row
            if model["size"] is None and row.get("params_total") is not None:
                model["size"], model["active"] = row["params_total"], row.get("params_active")

    def latency_runs(self, runs: list[int]) -> None:
        for run_id in runs:
            model = next((model for model in self.models.values()
                          if f"text:{run_id}" in (model["scores"].get("reading") or {}).get("runs", [])), None)
            if model is None:
                raise SystemExit(f"page_config.json all_benches.latency_runs: run {run_id} is in no Reading · Turkish row")
            model["latency"] = latency(self.site, run_id)

    # ------------------------------------------------------------------------------------------------------- views

    def published(self, key: str) -> bool:
        return key == "combined" or self.by_key[key]["bench"] is not None

    def views(self) -> list[str]:
        """The score switch's views in its order: Combined, then each bench."""
        return ["combined", *(bench["key"] for bench in self.benches)]

    def view_label(self, view: str) -> str:
        return "Combined" if view == "combined" else self.by_key[view]["label"]

    def score(self, model: dict[str, Any], view: str) -> float | None:
        if view == "combined":
            return model["combined"]
        row = model["scores"].get(view)
        return None if row is None else row["score_0_100"]

    def margin(self, view: str, first: dict[str, Any], second: dict[str, Any]) -> float:
        """How far apart two models' scores must be to read as apart (#tied): on one bench 100 / sqrt(n), n the smaller
        of the two question counts; on the combined score sqrt(sum of the three benches' margins squared) / 3, as the
        noise of a mean of three adds up."""
        if view == "combined":
            return math.sqrt(sum(self.margin(key, first, second) ** 2 for key in COMBINED)) / 3
        count = min(first["scores"][view]["raw"]["questions"], second["scores"][view]["raw"]["questions"])
        return 100 / math.sqrt(count)

    def tied(self, view: str, first: dict[str, Any], second: dict[str, Any]) -> bool:
        return abs(self.score(first, view) - self.score(second, view)) < self.margin(view, first, second)

    def ranked(self, view: str, kind: str = "decision") -> list[dict[str, Any]]:
        if not self.published(view):
            return []
        models = [model for model in self.models.values() if model["kind"] == kind and self.score(model, view) is not None]
        return sorted(models, key=lambda model: (-self.score(model, view), model["name"]))

    def default_view(self) -> str:
        return next(view for view in self.views() if self.ranked(view))

    def decision(self) -> list[dict[str, Any]]:
        view = self.default_view()
        rest = [model for model in self.models.values() if model["kind"] == "decision" and self.score(model, view) is None]
        return self.ranked(view) + sorted(rest, key=lambda model: model["name"])

    def their_rows(self) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
        """The index's models in its order, each with our model joined by repo (None: on none of our benches)."""
        by_repo = {model["repo"].lower(): model for model in self.models.values() if model["repo"]}
        return [(item, by_repo.get(item["repo"].lower())) for item in self.their["models"]]

    def reference(self) -> dict[str, Any] | None:
        name = norm(self.their["reference"]["name"])
        return next((model for model in self.models.values() if norm(model["name"]) == name and model["kind"] == "decision"),
                    None)


# ------------------------------------------------------------------------------------------------------------- pieces


def model_href(model: dict[str, Any]) -> str:
    return "?model=" + urllib.request.quote(model["name"], safe="")


def icon(model: dict[str, Any]) -> str:
    if model["family"]:
        return family_icon(model["family"])
    return f'<span class="ab-noicon" style="background:{model["colour"]}" aria-hidden="true"></span>'


def tag(model: dict[str, Any]) -> str:
    return f' <span class="ab-tag">{esc(model["tag"])}</span>' if model["tag"] else ""


def size_text(model: dict[str, Any]) -> str:
    if model["size"] is None:
        return '<span class="nm">Not disclosed</span>'
    total = billions(round(model["size"] * 1e9))
    active = model["active"]
    return total + (f'<span class="small">{billions(round(active * 1e9))} active</span>'
                    if active is not None and abs(active - model["size"]) > 0.005 else "")


def latency_text(model: dict[str, Any]) -> str:
    """A table cell's latency: median, with p95 under it; "not timed yet" (the table's note says where)."""
    found = model["latency"]
    if found is None:
        return '<span class="nm">not timed yet</span>'
    return f'{found["median"]:,.0f}\u00a0ms<span class="small">p95 {found["p95"]:,.0f}\u00a0ms</span>'


def latency_words(model: dict[str, Any]) -> str:
    found = model["latency"]
    if found is None:
        return NOT_TIMED
    return (f'median {found["median"]:,.0f} ms, p95 {found["p95"]:,.0f} ms over {found["requests"]:,} requests on {PINNED} '
            f'(Text run {found["run"]})')


def ece_text(row: dict[str, Any] | None) -> str:
    value = None if row is None else row.get("calibration_error")
    return "" if value is None else f'<span class="small">ECE {number(100 * value)} {DOWN}</span>'


def name_cell(model: dict[str, Any], detail: str = "") -> str:
    return (f'<td class="model">{icon(model)}<a class="model-name" href="{model_href(model)}">{esc(model["name"])}</a>{tag(model)}'
            f'<span class="small">{esc(model["maker"] or "no maker")}{detail}</span></td>')


def keys(name: str, items: list[tuple[str, str, bool]], attribute: str, label: str) -> str:
    """A row of keys (site.js style): (value, label, pressed)."""
    return (f'<div class="ab-keys needs-js" role="group" aria-label="{esc(label)}"><span class="group-label">{esc(name)}</span>'
            + "".join(f'<button type="button" class="key" {attribute}="{value}" aria-pressed="{str(pressed).lower()}">'
                      f'<span class="lamp" aria-hidden="true"></span>{esc(text)}</button>' for value, text, pressed in items)
            + "</div>")


def shown_if(condition: bool) -> str:
    return "" if condition else " hidden"


# ------------------------------------------------------------------------------------------------------------- ranking


def bars(data: Data, view: str) -> str:
    ranked = data.ranked(view)
    if not ranked:
        return f'<p class="note ab-empty">{empty_note(data, view)}</p>'
    reference = data.reference()
    items = []
    for index, model in enumerate(ranked):
        value = data.score(model, view)
        tied = index and data.tied(view, ranked[index - 1], model)
        ref = model is reference
        title = (f"{model['name']} · {model['maker']}" + (f" · {model['tag']}" if model["tag"] else "")
                 + f" · {number(value)} {UP}" + (" · tied with the bar before it" if tied else "")
                 + (" · reference: TypeSafe's hosted Jev" if ref else ""))
        items.append(
            f'<li class="ab-bar{" ab-ref" if ref else ""}" data-size="{"" if model["size"] is None else model["size"]}" '
            f'style="--h:{max(0.0, min(100.0, value)):.2f}%;--c:{model["colour"]}">'
            f'<a href="{model_href(model)}" title="{esc(title)}">'
            f'<span class="ab-bar-track"><span class="ab-bar-value">{number(value)}'
            f'{"<span class=\"ab-tied\">tied</span>" if tied else ""}</span><span class="ab-bar-fill"></span></span>'
            f'<span class="ab-bar-logo">{icon(model)}</span>'
            f'<span class="ab-bar-name">{esc(model["name"])}{"<span class=\"ab-ref-word\"> (reference)</span>" if ref else ""}'
            f'{tag(model)}</span></a></li>')
    legend = "".join(f'<span><i class="swatch" style="background:{colour}"></i>{esc(maker)}</span>'
                     for maker, colour in dict.fromkeys((model["maker"] or "no maker", model["colour"]) for model in ranked))
    return (f'<ol class="ab-bars" aria-label="{esc(data.view_label(view))}: decision models by score, higher is better">'
            f'{"".join(items)}</ol><p class="ab-legend families">{legend}</p>{not_combined_note(data, view)}')


def not_combined_note(data: Data, view: str) -> str:
    """Under the combined board: the rows left out of it, each with its reason (Methodology #combined)."""
    if view != "combined" or not data.not_combined:
        return ""
    return "".join(f'<p class="note ab-not-combined">No combined score for <a href="{model_href(model)}">{esc(model["name"])}</a>: '
                   f'{esc(model["not_combined"])} (<a href="method/#combined">the rule</a>)</p>' for model in data.not_combined)


def empty_note(data: Data, view: str) -> str:
    if view == "combined":
        missing = [data.by_key[key]["label"] for key in COMBINED if not data.published(key)]
        if missing:
            return (f"No combined score yet: it needs a model on all three of Reading · Turkish, Logic & Math and Backgammon, and "
                    f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} {NOT_PUBLISHED}.")
        return "No decision model has a score on all three of Reading · Turkish, Logic & Math and Backgammon yet."
    if not data.published(view):
        bench = data.by_key[view]
        return f'{esc(bench["label"])}: {NOT_PUBLISHED} (its file, <a href="{esc(bench["feed"])}">bench-scores.json</a>, is not live).'
    return "No decision model on this bench yet."


def leader(data: Data, view: str) -> str:
    ranked = data.ranked(view)
    if not ranked:
        return ""
    first = ranked[0]
    level = [model for model in ranked[1:] if data.tied(view, first, model)]
    tie = (f"<span>tied with {', '.join(f'{esc(model['name'])} ({number(data.score(model, view))})' for model in level)}</span>"
           if level else "")
    cells = []
    for bench in data.benches:
        key = bench["key"]
        label = bench["label"]
        value = data.score(first, key)
        text = (NOT_PUBLISHED if not data.published(key) else "not run" if value is None else f"{number(value)} {UP}")
        cells.append(f"<li><span class=\"muted\">{esc(label)}</span> {text}</li>")
    if first["combined"] is not None:
        cells.insert(0, f'<li><span class="muted">Combined</span> {number(first["combined"])} {UP}</li>')
    return (f'<div class="ab-lead"><p class="ab-lead-line"><span class="eyebrow">#1 decision model · {esc(data.view_label(view))}</span>'
            f'{icon(first)}<a class="model-name" href="{model_href(first)}">{esc(first["name"])}</a>{tag(first)} '
            f'<strong>{number(data.score(first, view))} {UP}</strong>{tie}</p><ul class="ab-lead-scores">{"".join(cells)}</ul></div>')


def size_steps(data: Data) -> list[float]:
    return sorted({model["size"] for model in data.models.values() if model["kind"] == "decision" and model["size"] is not None})


def ranking(data: Data) -> str:
    views = data.views()
    default = data.default_view()
    view_keys = keys("Score", [(view, data.view_label(view) + ("" if data.published(view) else " (not published)"),
                                view == default) for view in views], "data-ab-view", "Score shown")
    panels = "".join(f'<div class="ab-view" data-view="{view}"{shown_if(view == default)}>{leader(data, view)}{bars(data, view)}</div>'
                     for view in views)
    steps = size_steps(data)
    slider = (f'<div class="ab-size needs-js"><label for="ab-size">Model size up to</label> '
              f'<input type="range" id="ab-size" min="0" max="{len(steps)}" value="{len(steps)}" step="1" '
              f'data-steps="{",".join(f"{step:g}" for step in steps)}"> '
              f'<output for="ab-size" class="ab-size-out">all sizes, with undisclosed ones</output></div>')
    reference = data.their["reference"]
    return (f'<section class="card" id="ranking" data-ab-main><h2>Ranking</h2>{slider}{view_keys}{panels}'
            f'<p class="note">Each bar is a decision model\'s score from 0 (chance) to 100 (perfect), higher is better {UP}, '
            f"in its maker's colour with the maker's mark under it; the training method is the small tag where our records "
            f'state it. "tied": too close to the bar before it to tell apart (<a href="method/#tied">the rule</a>). '
            f"{esc(reference['name'])} is the reference bar: {esc(reference['note'])}. A bar opens the model's page.</p></section>")


# --------------------------------------------------------------------------------------------------------------- parts


def scoring(data: Data) -> str:
    text, english, vision = (data.by_key[key]["bench"] for key, _ in READING)
    return f"""<section class="card prose" id="scoring" data-ab-main>
      <h2>How it's scored</h2>
      <ul>
        <li>Every bench on one scale: <strong>0 = random guessing, 100 = perfect</strong>; higher is better {UP}.</li>
        <li><strong>Reading · Turkish</strong> ({bp.count(text["models"][0]["raw"]["questions"])} Turkish questions, 5 options), <strong>Reading · English</strong> ({bp.count(english["models"][0]["raw"]["questions"])} of its reading questions translated into English, 5 options) and <strong>Logic &amp; Math</strong>: accuracy corrected for chance, (accuracy − 1/k) / (1 − 1/k) × 100, k the number of options. <strong>Reading · Vision</strong>: the same on Reading's {bp.count(vision["models"][0]["raw"]["questions"])} questions that depend on the printed page, read from the page image alone.</li>
        <li><strong>Backgammon</strong>: 0 = the error rate of a player that picks a random legal move, 100 = no error.</li>
        <li><strong>Combined</strong> = the plain mean of Reading · Turkish, Logic &amp; Math and Backgammon, equal weights, only for a model that ran all three, one model on every bench (<a href="method/#combined">the rule</a>); the others are in each bench's tab.</li>
        <li><strong>Learning from experience</strong> ("did it improve?", points gained, higher is better {UP}) is a column of its own, outside the combined score.</li>
        <li>Lower is better {DOWN} for calibration error (ECE, in points: how far the stated probabilities are from the hit rate) and latency. Close scores read <strong>tied</strong>, never with an interval: <a href="method/#tied">the rule</a>.</li>
      </ul>
      <p><a href="method/">Methodology</a>: every rule, the sources and how models are matched across benches.</p>
    </section>"""


def h2h_rows(data: Data, first: dict[str, Any], second: dict[str, Any]) -> str:
    rows = []
    for key, label in [("combined", "Combined"), *((bench["key"], bench["label"]) for bench in data.benches)]:
        a, b = data.score(first, key), data.score(second, key)
        if not data.published(key):
            verdict = f'<span class="nm">{NOT_PUBLISHED}</span>'
        elif key == "combined" and (first["not_combined"] or second["not_combined"]):
            verdict = (f'<span class="nm">no combined score for {esc((first if first["not_combined"] else second)["name"])}: '
                       f'one model did not answer every bench</span>')
        elif a is None and b is None:
            verdict = '<span class="nm">neither ran it</span>'
        elif a is None or b is None:
            verdict = f'<span class="nm">only {esc((first if b is None else second)["name"])} ran it</span>'
        elif data.tied(key, first, second):
            verdict = f"tied ({number(a - b, 1)})"
        else:
            verdict = f"{esc((first if a > b else second)['name'])} ahead by {number(abs(a - b))}"
        cell = lambda value: "–" if value is None else number(value)  # noqa: E731
        rows.append(f'<tr><th scope="row">{esc(label)} {UP}</th><td class="num">{cell(a)}</td><td class="num">{cell(b)}</td>'
                    f"<td>{verdict}</td></tr>")
    return "".join(rows)


def head_to_head(data: Data) -> str:
    ranked = data.decision()
    first, second = ranked[0], ranked[1]
    options = lambda chosen: "".join(  # noqa: E731
        f'<optgroup label="{label}">' + "".join(
            f'<option value="{esc(model["key"])}"{" selected" if model is chosen else ""}>{esc(model["name"])}</option>'
            for model in sorted((model for model in data.models.values() if model["kind"] == kind), key=lambda model: model["name"].lower()))
        + "</optgroup>" for kind, label in KINDS if any(model["kind"] == kind for model in data.models.values()))
    return f"""<section class="card" id="head-to-head" data-ab-main>
      <h2>Head to head</h2>
      <div class="compare-pickers ab-pickers needs-js">
        <label class="control">First <select data-ab-pick="a">{options(first)}</select></label>
        <label class="control">Second <select data-ab-pick="b">{options(second)}</select></label>
      </div>
      <div class="table-wrap"><table class="board ab-h2h"><thead><tr><th scope="col">Bench</th><th scope="col" class="num" data-ab-name="a">{esc(first["name"])}</th><th scope="col" class="num" data-ab-name="b">{esc(second["name"])}</th><th scope="col">Difference</th></tr></thead>
      <tbody data-ab-h2h>{h2h_rows(data, first, second)}</tbody></table></div>
      <p class="note">Scores 0 to 100, higher is better {UP}; "tied" where the two are too close to tell apart (<a href="method/#tied">the rule</a>).</p>
    </section>"""


def results_table(data: Data, models: list[dict[str, Any]], caption: str) -> str:
    head = ['<th scope="col">Model</th>', '<th scope="col" class="num">Size<span class="small">parameters</span></th>',
            f'<th scope="col" class="num">Combined {UP}<span class="small">mean of 3</span></th>']
    for bench in data.benches:
        sub = NOT_PUBLISHED if not bench["bench"] else f"ECE {DOWN} under it"
        head.append(f'<th scope="col" class="num">{esc(bench["label"])} {UP}<span class="small">{sub}</span></th>')
    head += [f'<th scope="col" class="num">Learning from experience {UP}<span class="small">points gained</span></th>',
             f'<th scope="col" class="num">Latency {DOWN}<span class="small">median, p95; {esc(PINNED)}</span></th>']
    body = []
    for model in models:
        cells = [name_cell(model), f'<td class="num">{size_text(model)}</td>',
                 f'<td class="num">{"–" if model["combined"] is None else number(model["combined"])}'
                 f'{"<span class=\"small\">not one model</span>" if model["not_combined"] else ""}</td>']
        for bench in data.benches:
            row = model["scores"].get(bench["key"])
            cells.append(f'<td class="num">{"–" if row is None else number(row["score_0_100"]) + ece_text(row)}</td>')
        points = [(data.by_key[key]["label"], row["improvement_points"]) for key, row in model["scores"].items()
                  if row.get("improvement_points") is not None]
        cells.append(f'<td class="num">{"<br>".join(f"{esc(label)} {number(value)}" for label, value in points) or "–"}</td>')
        cells.append(f'<td class="num">{latency_text(model)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div class="table-wrap"><table class="board ab-results"><caption>{esc(caption)}</caption><thead><tr>{"".join(head)}'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def full_results(data: Data) -> str:
    view = data.default_view()
    chat = sorted((model for model in data.models.values() if model["kind"] != "decision"),
                  key=lambda model: (model["kind"], -(data.score(model, view) or -1e9), model["name"]))
    return f"""<section class="card" id="results" data-ab-main>
      <h2>Full results</h2>
      <p class="note">Every decision model on every bench, highest first by {esc(data.view_label(view))}. Scores 0 to 100, higher is better {UP}; under each score its calibration error (ECE, points), lower is better {DOWN}. – : not on that bench. Latency: Reading · Turkish requests on the pinned machine ({esc(PINNED)}), one request at a time.</p>
      {results_table(data, data.decision(), "Decision models")}
      <details class="ab-more"><summary>Chat models and programs on the same benches</summary>{results_table(data, chat, "Chat models and programs")}</details>
    </section>"""


# --------------------------------------------------------------------------------------------------------------- charts

W, H, L, R, T, B = 640, 380, 52, 16, 14, 46


def ticks(low: float, high: float, log: bool) -> list[float]:
    if log:
        out = []
        for power in range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1):
            for step in (1, 3):
                value = step * 10 ** power
                if low <= value <= high:
                    out.append(value)
        return out
    span = high - low
    step = next(step for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000, 2000, 5000) if span / step <= 6)
    return [step * index for index in range(math.ceil(low / step), math.floor(high / step) + 1)]


def tick_text(value: float) -> str:
    return f"{value:g}" if value < 1000 else f"{value:,.0f}"


def scatter(points: list[tuple[dict[str, Any], float, float]], x_title: str, label: str, log: bool) -> str:
    """An inline SVG scatter, score (y) against a measure (x), each model a dot in its maker's colour with its name where
    it fits, readable in both themes (the site's CSS variables)."""
    xs, ys = [x for _, x, _ in points], [y for _, _, y in points]
    if log:
        low, high = 10 ** math.floor(math.log10(min(xs))), 10 ** math.ceil(math.log10(max(xs)))
        place_x = lambda value: L + (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low)) * (W - L - R)  # noqa: E731
    else:
        low, high = 0.0, max(5.0, math.ceil(max(xs) / 5) * 5)
        place_x = lambda value: L + (value - low) / (high - low) * (W - L - R)  # noqa: E731
    bottom = min(0.0, math.floor(min(ys) / 10) * 10)
    place_y = lambda value: T + (100 - value) / (100 - bottom) * (H - T - B)  # noqa: E731
    parts = []
    for value in ticks(bottom, 100, False):
        y = place_y(value)
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="tick" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{number(value, 0)}</text>')
    for value in ticks(low, high, log):
        x = place_x(value)
        parts.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{H - B}"/>'
                     f'<text class="tick" x="{x:.1f}" y="{H - B + 16}" text-anchor="middle">{tick_text(value)}</text>')
    parts.append(f'<line class="axis" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/><line class="axis" x1="{L}" x2="{L}" y1="{T}" y2="{H - B}"/>'
                 f'<text class="axis-title" x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">{esc(x_title)}</text>'
                 f'<text class="axis-title" transform="translate(13 {(T + H - B) / 2:.0f}) rotate(-90)" text-anchor="middle">Score 0–100 {UP}</text>')
    boxes: list[tuple[float, float, float, float]] = []
    dots, names = [], []
    for model, x_value, y_value in sorted(points, key=lambda item: -item[2]):
        x, y = place_x(x_value), place_y(y_value)
        dots.append(f'<a href="{model_href(model)}"><circle class="ab-dot" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{model["colour"]}">'
                    f'<title>{esc(model["name"])}: {number(y_value)}, {esc(x_title)} {tick_text(round(x_value, 1))}</title></circle></a>')
        width = 6.2 * len(model["name"])
        box = (x + 8, y - 9, x + 8 + width, y + 4)
        if box[2] > W - R:
            box = (x - 8 - width, y - 9, x - 8, y + 4)
        if box[0] >= L and not any(box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3] for other in boxes):
            boxes.append(box)
            names.append(f'<text class="ab-dot-label" x="{box[0]:.1f}" y="{y + 3.5:.1f}">{esc(model["name"])}</text>')
    return (f'<svg class="ab-scatter" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}{"".join(dots)}{"".join(names)}</svg>')


def charts_for(data: Data, view: str) -> str:
    ranked = data.ranked(view)
    if not ranked:
        return f'<p class="note">{empty_note(data, view)}</p>'
    title = data.view_label(view)
    if view == "combined":
        ece = lambda model: (statistics.fmean(model["scores"][key]["calibration_error"] for key in COMBINED)  # noqa: E731
                             if all(model["scores"][key].get("calibration_error") is not None for key in COMBINED) else None)
    else:
        ece = lambda model: model["scores"][view].get("calibration_error")  # noqa: E731
    specs = [
        ("size", "Size against score", "Parameters, billions (log scale)", lambda model: model["size"], True,
         "models whose maker discloses no size are left out"),
        ("calibration", f"Calibration error {DOWN} against score", "Calibration error, ECE in points" + (" (mean of the three benches)" if view == "combined" else ""),
         lambda model: None if ece(model) is None else 100 * ece(model), False, "models without a calibration error are left out"),
        ("latency", f"Latency {DOWN} against score", "Median time per request, ms (log scale)",
         lambda model: (model["latency"] or {}).get("median"), True, f"latency: Reading · Turkish requests on {PINNED}"),
    ]
    out = []
    for key, heading, x_title, measure, log, rule in specs:
        points = [(model, measure(model), data.score(model, view)) for model in ranked if measure(model) is not None]
        left = len(ranked) - len(points)
        if points:
            figure = scatter(points, x_title, f"{heading}: {title}, {len(points)} decision models", log)
        else:
            figure = (f'<p class="note ab-empty">No decision model on {esc(title)} has been {NOT_TIMED.replace("not timed", "timed")}.</p>'
                      if key == "latency" else f'<p class="note ab-empty">No points yet.</p>')
        sub = (f"{esc(title)}: {len(points)} decision models" + (f"; {left} left out ({rule})" if left else "")
               if points else esc(rule[:1].upper() + rule[1:]))
        out.append(f'<figure class="chart-card ab-chart" id="chart-{key}-{view}"><figcaption class="chart-head"><h3>{heading}</h3>'
                   f'<p class="chart-sub">{sub}</p></figcaption>{figure}</figure>')
    return "".join(out)


def charts(data: Data) -> str:
    default = data.default_view()
    panels = [f'<div class="ab-view ab-charts" data-view="{view}"{shown_if(view == default)}>{charts_for(data, view)}</div>'
              for view in data.views()]
    return (f'<section class="card" id="charts" data-ab-main><h2>Size, calibration and latency against score</h2>'
            f'<p class="note">The score in view above (switch it in the ranking). Each dot a decision model in its maker\'s colour; '
            f'a dot opens its page. Score: higher is better {UP}; calibration error and latency: lower is better {DOWN}.</p>'
            f'{"".join(panels)}</section>')


def their_for(data: Data, view: str) -> str:
    rows = data.their_rows()
    ours = [(item, model, data.score(model, view) if model else None) for item, model in rows]
    measured = [(item, model, value) for item, model, value in ours if value is not None]
    our_rank = {id(model): 1 + sum(other > value for _, _, other in measured) for _, model, value in measured}
    lines = []
    for index, (item, model, value) in enumerate(ours, start=1):
        colour = model["colour"] if model else data.colour(item["maker"], "decision")
        commit = (model["scores"].get(view) or {}).get("commit") if model and view != "combined" else None
        ours_cell = (f'<span class="ab-pair-bar ab-ours" style="--h:{max(0.0, min(100.0, value)):.2f}%;--c:{colour}"></span>'
                     f'<span class="ab-pair-value">{number(value)}</span>' if value is not None else
                     f'<span class="nm">{NOT_PUBLISHED if not data.published(view) else "not on this bench yet"}</span>')
        lines.append(
            f'<tr><td class="num">{index}</td><td class="model">'
            + (f'{icon(model)}<a class="model-name" href="{model_href(model)}">{esc(item["name"])}</a>' if model else
               f'<span class="ab-noicon" style="background:{colour}" aria-hidden="true"></span><span class="model-name">{esc(item["name"])}</span>')
            + f'<span class="small">{esc(item["repo"])}{" @ " + esc(commit[:7]) if commit else ""}</span></td>'
            f'<td class="ab-pair"><span class="ab-pair-bar ab-theirs" style="--h:{item["score"]:.2f}%"></span><span class="ab-pair-value">{number(item["score"])}</span></td>'
            f'<td class="ab-pair">{ours_cell}</td><td class="num">{our_rank.get(id(model), "–") if model else "–"}</td></tr>')
    reference = data.reference()
    if reference is not None and data.score(reference, view) is not None:
        value = data.score(reference, view)
        lines.append(f'<tr class="ab-ref-row"><td class="num">ref.</td><td class="model">{icon(reference)}<a class="model-name" href="{model_href(reference)}">{esc(reference["name"])}</a>'
                     f'<span class="small">reference, hosted</span></td><td class="ab-pair"><span class="nm">no index score here</span></td>'
                     f'<td class="ab-pair"><span class="ab-pair-bar ab-ours ab-ref" style="--h:{max(0.0, value):.2f}%;--c:{reference["colour"]}"></span>'
                     f'<span class="ab-pair-value">{number(value)}</span></td><td class="num">–</td></tr>')
    same = reversed_ = level = 0
    for first_index, (item, model, value) in enumerate(measured):
        for other_item, other_model, other_value in measured[first_index + 1:]:
            if data.tied(view, model, other_model):
                level += 1
            elif (item["score"] - other_item["score"]) * (value - other_value) > 0:
                same += 1
            else:
                reversed_ += 1
    pairs = same + reversed_ + level
    verdict = (f"{len(measured)} of the index's {len(rows)} models have a score here. Of their {pairs} pairs, "
               f"{same} keep the index's order, {reversed_} {'is' if reversed_ == 1 else 'are'} reversed and {level} "
               f"{'is' if level == 1 else 'are'} tied on our score." if pairs else
               f"{len(measured)} of the index's {len(rows)} models {'has' if len(measured) == 1 else 'have'} a score here: "
               "too few to compare orders.")
    return (f'<p class="note">{verdict}</p><div class="table-wrap"><table class="board ab-their"><thead><tr><th scope="col" class="num">Index rank</th>'
            f'<th scope="col">Model</th><th scope="col">Their score {UP}<span class="small">{esc(data.their["name"])} {esc(data.their["edition"])}, {esc(data.their["measure"])}</span></th>'
            f'<th scope="col">Our score {UP}<span class="small">{esc(data.view_label(view))}, 0–100</span></th><th scope="col" class="num">Our rank<span class="small">of these</span></th></tr></thead>'
            f'<tbody>{"".join(lines)}</tbody></table></div>')


def their_score(data: Data) -> str:
    default = data.default_view()
    panels = [f'<div class="ab-view" data-view="{view}"{shown_if(view == default)}>{their_for(data, view)}</div>'
              for view in data.views()]
    their = data.their
    return (f'<section class="card" id="their-score" data-ab-main><h2>Their score against ours</h2>'
            f'<p class="note">Does the {esc(their["name"])}\'s ranking hold on our private benches? Its {esc(their["measure"])} '
            f'(edition {esc(their["edition"])}, {bp.long_date(their["date"])}, <a href="{esc(their["source"])}">source</a>) is a sanity '
            f"check only, never our score. Its 15 open decision models in its order, joined to ours by Hugging Face repo; our "
            f"score is the one in view in the ranking.</p>{''.join(panels)}</section>")


# ---------------------------------------------------------------------------------------------------------------- tabs


def bench_table(data: Data, bench: dict[str, Any], kind: str) -> str:
    view = bench["key"]
    ranked = data.ranked(view, kind)
    if not ranked:
        return ""
    rows = []
    for index, model in enumerate(ranked):
        row = model["scores"][view]
        tie = (f'<span class="small">tied with {esc(ranked[index - 1]["name"])}</span>'
               if index and data.tied(view, ranked[index - 1], model) else "")
        raw = row["raw"]
        raw_text = (f'{100 * raw["value"]:.1f}%' if raw.get("metric") == "accuracy" else f'{raw["value"]:g}'
                    if isinstance(raw.get("value"), (int, float)) else "–")
        commit = row.get("commit")
        rows.append(f'<tr><td class="num">{index + 1}</td>{name_cell(model)}<td class="num">{size_text(model)}</td>'
                    f'<td class="num">{number(row["score_0_100"])}{tie}</td><td class="num">{raw_text}<span class="small">{bp.count(raw["questions"])} questions</span></td>'
                    f'<td class="num">{"–" if row.get("calibration_error") is None else number(100 * row["calibration_error"])}</td>'
                    f'<td>{esc(commit[:7]) if commit else "<span class=\"nm\">no repo</span>"}</td></tr>')
    metric = ranked[0]["scores"][view]["raw"].get("metric", "raw")
    return (f'<h4 class="board-group">{dict(KINDS)[kind]}</h4><div class="table-wrap"><table class="board ab-bench-table"><thead><tr>'
            f'<th scope="col" class="num">#</th><th scope="col">Model</th><th scope="col" class="num">Size</th>'
            f'<th scope="col" class="num">Score {UP}<span class="small">0–100</span></th><th scope="col" class="num">{esc(str(metric).capitalize())}</th>'
            f'<th scope="col" class="num">Calibration error {DOWN}<span class="small">ECE, points</span></th><th scope="col">Commit</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def bench_panel(data: Data, bench: dict[str, Any]) -> str:
    title = bench["label"]
    if not bench["bench"]:
        return (f'<h3>{esc(title)}</h3><p class="note">{NOT_PUBLISHED.capitalize()}: <a href="{esc(bench["feed"])}">'
                f"{esc(bench['feed'])}</a> serves no file yet. It shows here once its site publishes it.</p>")
    file = bench["bench"]
    score = file.get("score") or {}
    questions = sorted({row["raw"]["questions"] for row in file["models"]})
    count = bp.count(questions[0]) if len(questions) == 1 else f"{bp.count(questions[0])} to {bp.count(questions[-1])}"
    return (f'<h3><a href="{esc(file.get("url") or "")}">{esc(file.get("title") or title)}</a></h3>'
            f'<p class="note">{count} {"decisions" if bench["key"] == "backgammon" else "questions"} per model · updated '
            f'{esc(bp.long_date(file["updated"]) if file.get("updated") else "–")} · 0 = {esc(str(score.get("zero", "chance")))}; '
            f'100 = {esc(str(score.get("hundred", "perfect")))} · feed: <a href="{esc(bench["feed"])}">bench-scores.json</a></p>'
            + "".join(bench_table(data, bench, kind) for kind, _ in KINDS))


def learning_panel(data: Data) -> str:
    rows = [(model, [(data.by_key[key]["label"], row["improvement_points"]) for key, row in model["scores"].items()
                     if row.get("improvement_points") is not None]) for model in data.models.values()]
    rows = [(model, points) for model, points in rows if points]
    if not rows:
        return ('<h3>Learning from experience</h3><p class="note">No published bench file carries improvement points yet '
                '("did it improve?": the points a model gains from its own earlier games or answers). They show here, outside '
                "the combined score, once a bench publishes them.</p>")
    body = "".join(f'<tr>{name_cell(model)}<td class="num">{"<br>".join(f"{esc(label)} {number(value)}" for label, value in points)}</td></tr>'
                   for model, points in sorted(rows, key=lambda item: -max(value for _, value in item[1])))
    return (f'<h3>Learning from experience</h3><div class="table-wrap"><table class="board"><thead><tr><th scope="col">Model</th>'
            f'<th scope="col" class="num">Points gained {UP}</th></tr></thead><tbody>{body}</tbody></table></div>')


def bench_tabs(data: Data) -> str:
    tabs = [(bench["key"], bench["label"] + ("" if bench["bench"] else " (not published)")) for bench in data.benches] + [
        ("learning", "Learning from experience")]
    keys_html = "".join(f'<button type="button" class="key" role="tab" data-ab-tab="{key}" aria-selected="{str(index == 0).lower()}">'
                        f'<span class="lamp" aria-hidden="true"></span>{esc(label)}</button>' for index, (key, label) in enumerate(tabs))
    panels = "".join(f'<div class="ab-tab-panel" role="tabpanel" data-ab-panel="{bench["key"]}">{bench_panel(data, bench)}</div>'
                     for bench in data.benches)
    panels += f'<div class="ab-tab-panel" role="tabpanel" data-ab-panel="learning">{learning_panel(data)}</div>'
    return (f'<section class="card" id="benches" data-ab-main><h2>All benches</h2>'
            f'<div class="ab-keys ab-tabs needs-js" role="tablist" aria-label="Benches">{keys_html}</div>{panels}</section>')


# --------------------------------------------------------------------------------------------------------- model pages


def rank_text(data: Data, model: dict[str, Any], view: str) -> str:
    ranked = data.ranked(view, model["kind"])
    if model not in ranked:
        return "–"
    index = ranked.index(model)
    level = [other["name"] for other in ranked if other is not model and data.tied(view, model, other)]
    return (f"{index + 1} of {len(ranked)}" + (f'<span class="small">tied with {esc(", ".join(level[:3]))}'
                                               f'{f" and {len(level) - 3} more" if len(level) > 3 else ""}</span>' if level else ""))


def model_page(data: Data, model: dict[str, Any]) -> str:
    rows = []
    for key, label in [("combined", "Combined"), *((bench["key"], bench["label"]) for bench in data.benches)]:
        if not data.published(key):
            rows.append(f'<tr><th scope="row">{esc(label)}</th><td colspan="5"><span class="nm">{NOT_PUBLISHED}</span></td></tr>')
            continue
        value = data.score(model, key)
        if value is None:
            reason = ((model["not_combined"] or "needs all three of Reading · Turkish, Logic & Math and Backgammon") if key == "combined"
                      else "not on this bench")
            rows.append(f'<tr><th scope="row">{esc(label)}</th><td colspan="5"><span class="nm">{esc(reason)}</span></td></tr>')
            continue
        row = model["scores"].get(key) or {}
        commit = row.get("commit")
        runs = ", ".join(map(str, row.get("runs") or [])) or "–"
        rows.append(f'<tr><th scope="row">{esc(label)}</th><td class="num">{number(value)}</td><td class="num">{rank_text(data, model, key)}</td>'
                    f'<td class="num">{"–" if row.get("calibration_error") is None else number(100 * row["calibration_error"])}</td>'
                    f'<td>{f"<code title=\"{esc(commit)}\">{esc(commit[:7])}</code>" if commit else "–"}</td><td><span class="small">{esc(runs)}</span></td></tr>')
    points = [(data.by_key[key]["label"], row["improvement_points"]) for key, row in model["scores"].items()
              if row.get("improvement_points") is not None]
    their = next((item for item, joined in data.their_rows() if joined is model), None)
    facts = [f"<li>Maker: {esc(model['maker'] or 'none')}{' · training: ' + esc(model['tag']) if model['tag'] else ''}</li>",
             f"<li>Kind: {dict(KINDS)[model['kind']][:-1].lower()}</li>",
             f"<li>Size: {size_text(model).replace('<span class=\"small\">', ' (').replace('</span>', ')') if model['size'] is not None else 'not disclosed'}</li>",
             f"<li>Repo: {'<a href=\"https://huggingface.co/' + esc(model['repo']) + '\">' + esc(model['repo']) + '</a>' if model['repo'] else 'none (an API setup, or no released checkpoint)'}</li>",
             f"<li>Latency {DOWN}: {esc(latency_words(model))}</li>",
             f"<li>Learning from experience {UP}: {', '.join(f'{esc(label)} {number(value)} points' for label, value in points) or 'not published for it yet'}</li>"]
    if their:
        facts.append(f"<li>{esc(data.their['name'])} {esc(data.their['measure'])}: {number(their['score'])} (theirs, a sanity check; not our score)</li>")
    return (f'<section class="card ab-model" data-ab-model="{esc(model["slug"])}" data-ab-model-name="{esc(model["name"])}" '
            f'data-ab-model-key="{esc(model["key"])}" hidden><p class="ab-back"><a href="./" data-ab-back>← {TITLE}</a></p>'
            f'<h1>{icon(model)}{esc(model["name"])}{tag(model)}</h1><ul class="ab-facts">{"".join(facts)}</ul>'
            f'<div class="table-wrap"><table class="board"><thead><tr><th scope="col">Bench</th><th scope="col" class="num">Score {UP}<span class="small">0–100</span></th>'
            f'<th scope="col" class="num">Rank<span class="small">among {dict(KINDS)[model["kind"]].lower()}</span></th>'
            f'<th scope="col" class="num">Calibration error {DOWN}<span class="small">ECE, points</span></th><th scope="col">Commit</th><th scope="col">Runs</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


# ----------------------------------------------------------------------------------------------------------- the pages


def script_data(data: Data) -> str:
    """What all-benches.js needs: the benches and every model's scores with their question counts (Head to head)."""
    payload = {
        "benches": [{"key": bench["key"], "label": bench["label"], "published": bench["bench"] is not None}
                    for bench in data.benches],
        "combined": list(COMBINED),
        "default": data.default_view(),
        "models": [{"key": model["key"], "name": model["name"], "slug": model["slug"], "repo": model["repo"],
                    "scores": {key: [row["score_0_100"], row["raw"]["questions"]] for key, row in model["scores"].items()},
                    "combined": model["combined"], "nc": bool(model["not_combined"])} for model in data.models.values()],
    }
    return f'<script type="application/json" id="ab-data">{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}</script>'


def frame(data: Data, path: str, title: str, description: str, body: str, scripts: tuple[str, ...] = ()) -> str:
    """A whole page of OUT at path ("" or "method/"), for its address under /analysis/all-benches/: the head with its
    canonical address, the theme line of the Reading site's pages and the folder's own copies of the files (ASSETS,
    versioned as site.asset does), then the one sticky header: the suite strip with All benches marked (suite_bar), and
    the page's own title row, its name linking the page and the Dark / Light switch (site.js), without the Reading
    site's tabs; the family icons; the body; a footer."""
    root = rel(path, "")
    config = data.site.config["all_benches"]
    extra = "".join(f'\n  <script src="{root}{asset(script)}" defer></script>' for script in scripts)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Zeki Works</title>
  <link rel="canonical" href="{esc(config["url"] + path)}">
  <meta name="description" content="{esc(description)}">
  <script>document.documentElement.classList.add("js"); document.documentElement.dataset.theme = "dark"; try {{ if (localStorage.getItem("theme") === "light") document.documentElement.dataset.theme = "light"; }} catch (e) {{}}</script>
  <link rel="stylesheet" href="{root}{asset(SUITE_CSS)}">
  <link rel="stylesheet" href="{root}{asset("v3.css")}">
  <link rel="stylesheet" href="{root}{asset("all-benches.css")}">
  <script src="{root}{asset("site.js")}" defer></script>{extra}
</head>
<body class="v3">
  <a class="skip" href="#main">Skip to content</a>
  <div class="site-header">
  {suite_bar(suite_path(data.site))}
  <header class="site-bar"><div class="site-bar-in"><div class="site-title-row"><a class="site-title" href="{root}">{TITLE}</a>{THEME_SWITCH}</div></div></header>
  </div>
  {family_sprite()}
  <main id="main">
{body}
  </main>
  <footer class="footer">
    <nav class="footer-links" aria-label="Site"><a href="{root}">{TITLE}</a> · <a href="{root}{METHOD}">Methodology</a> · <a href="{esc(data.site.config["site_url"])}">Reading bench</a></nav>
    <p>Reading · Turkish, English and Vision: {data.site.version()}</p>
  </footer>
</body>
</html>
"""


def suite_path(site: Site) -> str:
    """The pages' address on the mirror, as the suite strip links it: /analysis/all-benches/."""
    return urllib.parse.urlparse(site.config["all_benches"]["url"]).path


def page(data: Data) -> str:
    published = [bench["label"] for bench in data.benches if bench["bench"]]
    missing = [bench["label"] for bench in data.benches if not bench["bench"]]
    status = f"Published now: {', '.join(published)}." + (f" {NOT_PUBLISHED.capitalize()}: {', '.join(missing)}." if missing else "")
    body = f"""    {script_data(data)}
    <section class="card ab-intro" id="top" data-ab-main>
      <p class="eyebrow">Zeki Works benches · draft</p>
      <h1>{TITLE}</h1>
      <p>How the decision models do on every Zeki Works bench, each scored 0 (random guessing) to 100 (perfect), higher is better {UP}: Reading in Turkish, in English and from the page image (Vision), Logic &amp; Math and Backgammon, their combined score, and learning from experience.</p>
      <p class="note">{esc(status)} <a href="{METHOD}">Methodology</a>.</p>
    </section>
    {ranking(data)}
    {scoring(data)}
    {head_to_head(data)}
    {full_results(data)}
    {charts(data)}
    {their_score(data)}
    {bench_tabs(data)}
    {"".join(model_page(data, model) for model in data.models.values())}"""
    return frame(data, PATH, TITLE, "Every Zeki Works bench for the decision models on one page: Reading in Turkish, in "
                 "English and from the page image, Logic & Math and Backgammon on one 0 to 100 scale, their combined score, "
                 "head to head, and each bench's full table.", body, scripts=("all-benches.js",))


def method_page(data: Data) -> str:
    site = data.site
    n_text, n_english, n_vision = (data.by_key[key]["bench"]["models"][0]["raw"]["questions"] for key, _ in READING)
    sources = "".join(
        f'<li>{esc(bench["label"])}: <a href="{esc(bench["feed"])}">{esc(bench["feed"])}</a> — '
        + (f'published, {len(bench["bench"]["models"])} rows, updated {esc(bp.long_date(bench["bench"]["updated"]))}'
           if bench["bench"] and bench["bench"].get("updated") else NOT_PUBLISHED)
        + "</li>" for bench in data.benches)
    missing = sorted(data.missing_colours)
    up = rel(METHOD, PATH)
    body = f"""    <section class="card prose" id="method">
      <p class="ab-back"><a href="{up}">← {TITLE}</a></p>
      <h1>{TITLE}: Methodology</h1>
      <p>How the page <a href="{up}">{TITLE}</a> puts the Zeki Works benches side by side. It uses only the files each bench publishes, bench-scores.json, in one schema for the three sites; a bench whose file is not live says "{NOT_PUBLISHED}".</p>
      <h2 id="scale">One scale: 0 = random guessing, 100 = perfect</h2>
      <ul>
        <li><strong>Reading · Turkish</strong>: {bp.count(n_text)} Turkish reading and grammar questions, 5 options each, as the Reading site's Text tab asks them. Score = (accuracy − 1/k) / (1 − 1/k) × 100 with k = 5: 20% right reads 0, every question right reads 100. Below 0 means worse than guessing.</li>
        <li><strong>Reading · English</strong>: the {bp.count(n_english)} reading questions kept after translation into English (the Reading site's <a href="{esc(site.config["site_url"])}english/">English reading</a> page), 5 options each, the same score with k = 5. A model's row is its first English run of the setup its Reading · Turkish row shows (else of another setup of the same row, in the Leaderboard's order); the models run only in English have a row here and none on Reading · Turkish.</li>
        <li><strong>Reading · Vision</strong>: the {bp.count(n_vision)} questions that depend on the printed page, asked with the page image alone (the Reading site's Vision tab, condition B), k = each question's number of options. Models that read only text are not on it.</li>
        <li><strong>Logic &amp; Math</strong>: the same correction, on its own questions (k = 5), as its file states.</li>
        <li><strong>Backgammon</strong>: 0 = the error rate of a player that picks a random legal move, 100 = no error, as its file states.</li>
        <li>Higher is better {UP} on every score; lower is better {DOWN} for calibration error and latency. Size has no better direction.</li>
      </ul>
      <h2 id="combined">Combined score</h2>
      <p>The plain mean, equal weights, of Reading · Turkish, Logic &amp; Math and Backgammon. Only a model with a score on all three gets one; the others appear in each bench's tab. Reading · English and Reading · Vision are not part of it.</p>
      <p>A row gets a combined score only if one model answered every bench: the same checkpoint (one repo, one set of weights) or the same served version of a hosted model. A hosted service that changed its model between the benches' runs keeps its score on each bench, but gets no combined score{":" if data.not_combined else "."}</p>
      {"<ul>" + "".join(f"<li>{esc(model['name'])}: {esc(model['not_combined'])}</li>" for model in data.not_combined) + "</ul>" if data.not_combined else ""}
      <h2 id="learning">Learning from experience</h2>
      <p>"Did it improve?": the points a model gains from its own experience, as a bench's file gives them (improvement_points). A column of its own, never part of the combined score.</p>
      <h2 id="tied">When we write "tied"</h2>
      <p>No interval bars and no ranges: where two scores are too close to tell apart, the page says <strong>tied</strong>. The rule, the same everywhere on the page:</p>
      <ul>
        <li>On one bench, two models are tied when their scores differ by less than <strong>100 ÷ √n points</strong>, n being the smaller of their two question counts on that bench (Backgammon: scored decisions). On Reading · Turkish's {bp.count(n_text)} questions that is {number(100 / math.sqrt(n_text), 2)} points; on Reading · English's {bp.count(n_english)} {number(100 / math.sqrt(n_english), 2)} points; on Reading · Vision's {bp.count(n_vision)} {number(100 / math.sqrt(n_vision), 2)} points. The margin is about the size of the noise a score on n questions carries, so a smaller bench needs a larger gap.</li>
        <li>On the combined score, a mean of three, the three benches' margins add up as noise does: √(m₁² + m₂² + m₃²) ÷ 3.</li>
        <li>The ranking marks a bar "tied" when it is within the margin of the bar before it; the #1 line names every model within the margin of #1; Head to head says "tied" for a bench where the two are within it; each bench's table writes "tied with" the row above. Ties are not chained: A tied with B and B with C does not tie A with C.</li>
      </ul>
      <h2 id="calibration">Calibration error</h2>
      <p>ECE: the answers sorted into 10 equal-width bins of the chosen option's probability; in each bin the gap between the mean probability and the share right, weighted by the answers in it; shown in points (×100), lower is better {DOWN}. Reading · Turkish's is its Text tab run's, as the Text tab gives it; Reading · English's is its first English run's, computed the same way over its answers that carry a probability (none for a run without one); Reading · Vision's the page-image run's; the other benches' as their files give them. On the combined view the chart uses the mean of the three.</p>
      <h2 id="latency">Latency</h2>
      <p>One pinned machine for every model: {esc(PINNED)}, one request at a time, Reading · Turkish requests (the Text tab's runs); the median and the 95th percentile (nearest rank) of the time per request, in milliseconds. A run's machine is read from the host its requests went to, not from the hardware text. Models timed elsewhere, on another machine or through an API, read "{NOT_TIMED}".</p>
      <h2 id="size">Size</h2>
      <p>Total parameters (and the active count for a mixture of experts) as the bench files give them, in billions; "not disclosed" where the maker states none. The size slider keeps the bars of models up to the size chosen; models of undisclosed size show only at "all sizes".</p>
      <h2 id="join">One model across benches</h2>
      <p>Rows join by Hugging Face repo id; a setup that ran through an API has none and joins by its name and kind (decision or chat). Each bench's commit is on the model's page: the benches may have run different commits of one repo. A setup on our hardware and the same model's API are separate rows.</p>
      <h2 id="their-score">Their score</h2>
      <p>{esc(data.their["name"])} {esc(data.their["edition"])}, "{esc(data.their["measure"])}", as of {bp.long_date(data.their["date"])} (<a href="{esc(data.their["source"])}">source</a>), for its 15 open decision models: a sanity check beside ours, never shown as our score. {esc(data.their["reference"]["name"])} is a reference bar: {esc(data.their["reference"]["note"])}.</p>
      <h2 id="colours">Colours, marks and tags</h2>
      <p>Each bar and dot takes its maker's colour from maker_colours.json, the one colour map of the three sites, with the maker's mark under the bar (a plain shape where the maker's mark is not freely licensed). Makers without a colour there yet read grey: {esc(", ".join(missing)) if missing else "none"}. The small tag is the training method where our setup records state it (fine-tune, post-trained, LoRA, blend …); blank where they do not.</p>
      <h2 id="sources">Sources</h2>
      <ul>{sources}</ul>
      <p class="note">The build reads the other sites' files from these addresses and keeps what it read in <a href="{rel(METHOD, SNAPSHOT_COPY)}">benches.json</a>.</p>
    </section>"""
    return frame(data, METHOD, f"{TITLE}: Methodology", f"How {TITLE} scores, combines and compares the Zeki Works benches.",
                 body)


def redirect(site: Site, old: str, new: str) -> str:
    """A page's earlier address in the Reading site: sends the reader to its address under /analysis/all-benches/ with
    the query (?model=) and the fragment, as v2/ does (the meta refresh alone drops both)."""
    target = suite_path(site) + new
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moved: {TITLE}</title>
  <link rel="canonical" href="{esc(site.config["all_benches"]["url"] + new)}">
  <meta http-equiv="refresh" content="0; url={target}">
  <!-- Keeps the query (?model=) and a deep link's section: the meta refresh alone drops both. -->
  <script>location.replace("{target}" + location.search + location.hash);</script>
</head>
<body>
  <p>{TITLE} has moved to <a href="{target}">zekiworks.github.io{target}</a>.</p>
</body>
</html>
"""


def build(site: Site) -> dict[str, str]:
    """The two pages and the snapshot's copy in OUT with the files they use (ASSETS); the snapshot in the repo; the
    redirects at the earlier addresses."""
    data = Data(site)
    if data.missing_colours:
        print(f"all-benches: makers without a colour in maker_colours.json: {', '.join(sorted(data.missing_colours))}")
    return {OUT + PATH: page(data), OUT + METHOD: method_page(data), OUT + SNAPSHOT_COPY: data.snapshot, SNAPSHOT: data.snapshot,
            **{OUT + name: (ROOT / name).read_text(encoding="utf-8") for name in ASSETS},
            OLD_PATH: redirect(site, OLD_PATH, PATH), OLD_METHOD: redirect(site, OLD_METHOD, METHOD)}
