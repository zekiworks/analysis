"""All benches (TITLE, the project lead's name for it, bus #4172): every bench of the three sites and Grading for the decision
models on one page, after the Jev Decision Index page in the site's style (project lead, bus #4057), and its Methodology
page. They live outside the Reading site, at /analysis/all-benches/ and /analysis/all-benches/method/ (page_config.json
all_benches.url): the build writes them into the git-ignored folder OUT (_suite/all-benches/) with copies of every file
they use (ASSETS), so the folder works on its own; the publishing step copies it to the mirror's analysis/all-benches/.
Their header is the suite strip with All benches marked, then the page's own title row (its name and the theme switch),
no Reading tabs. The old addresses in the Reading site, all-benches/ and all-benches/method/, are redirects to the new
ones that keep the query and the fragment.

Data: only the benches' published bench-scores.json files, one schema for the three sites (#4062): this site's own
Reading benches (sitebuild/bench_scores.py, the same rows its bench-scores.json publishes): Turkish Reading, Turkish
Grammar, English Reading and Vision on the page (#4239), and Reading · Turkish (all 2,198 questions), which only the
Combined score uses; and the other sites' files at their published addresses (page_config.json all_benches.benches,
one bench each), which the build reads and keeps in SNAPSHOT (in the repo, copied into OUT): a file the address does
not serve yet is "not published yet"; when the address cannot be reached, the build keeps what it read before. The
pooled Logic & Math shows until both its parts, Logic and Math, are live, and the Combined score uses it either way
(#4234). Rows join across benches by the three sites' rule (Data.add: matching repos, else model_key, #4243, #4253,
#4280, the route never splitting a model, #4270; else the alias list; else the name key), never two rows of one bench
into one model; a model whose
benches ran different setups says which ran which (Data.setups). Every score is 0 to 100: 0 = chance
(Backgammon: a random legal-move player's error rate), 100 = perfect. The combined score is the plain mean of Reading
· Turkish, Logic & Math and Backgammon, for a model on all three only, and only where one model answered every bench
(page_config.json all_benches.not_combined lists the rows where it did not); learning from experience (improvement
points) stays outside it. Two scores closer than their margin (margin) read "tied", the one rule the Methodology page
states (#tied); no interval or range is shown.

The page in order (after the Jev Decision Index page on Hugging Face, Ümit #4239): the line on what it measures; the
ranking: three key rows, the type (All · Chat models · Decision models, Decision models first) and the size (the Reading
site's Leaderboard's classes, Site.model_class), which choose the models in view across the page, and the score
(Combined · Turkish Reading · Turkish Grammar · English Reading · Vision · Logic · Math · Backgammon · Grading), which picks what
the ranking chart ranks by (a row per model: its maker's mark and name, then its bar in its maker's colour and its
score, so a long name reads in line with its bar, Ümit #4665), then the table of every model
in view on every bench, sortable by any column; How it's scored; Head to head; Full results (calibration, learning,
latency); the three charts (size, calibration error and latency against the score); their score against ours for the
index's 15 models; one tab per bench. ?model=<name> (its slug where two models share a name, told apart by their tags)
shows one model's page instead (all-benches.js). Without
JavaScript the page is the default view's static parts and every bench's table."""

from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import re
import statistics
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import build_page as bp
from sitebuild import bench_scores, leaderboard, names
from sitebuild.english_reading import english_only, setup_families, setup_run
from sitebuild.site import (ROOT, SUITE_CSS, THEME_SWITCH, Site, asset, billions, esc, family_icon, family_sprite,
                            label_count, model_families, rel, stated_total, suite_bar)

# The page's name (project lead, bus #4172: final); never "Index". Its titles end in the brand, as the Reading site's.
TITLE = "All benches"
BRAND = "Hilde"
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
# The link preview images' folder in OUT (share_images).
SHARE = "share/"
UP, DOWN = "\u2191", "\u2193"
# This site's benches in bench_scores.benches' order, (key, label, short label for the main table's heads, shown): the
# score selector's Turkish Reading, Turkish Grammar, English Reading and Vision (Ümit #4239), and Reading · Turkish (all
# 2,198 questions), which only the Combined score uses (not shown). The other sites' benches follow
# (page_config.json all_benches.benches). The combined score averages COMBINED: Reading · Turkish, the pooled Logic &
# Math and Backgammon, as before the splits (#4173, #4234, #4239).
READING = (("reading", "Reading · Turkish", "TR Reading & Grammar", False), ("turkish-reading", "Turkish Reading", "TR Reading", True),
           ("turkish-grammar", "Turkish Grammar", "TR Grammar", True), ("reading-english", "English Reading", "EN Reading", True),
           ("reading-vision", "Vision", "Vision", True))
COMBINED = ("reading", "logic-math", "backgammon")
# Combined's three benchmark groups as a row's breakdown names them (combined_parts), the label beside Combined and the
# unit, at each chart's head and once in the table's caption: a score of 0 to 100 is no accuracy and never takes a %
# sign (Ümit #4665, #6400).
COMBINED_SHORT = {"reading": "TR", "logic-math": "L&M", "backgammon": "BG"}
# Grading (the grading agent's bench, grading/bench-scores.json; Ümit #6275, #6278; grading #6284, #6296): a bench of
# its own, outside Combined. Its Methodology section (grading_section) is the grading agent's public copy (#6300, sha256
# d3ab8ab2…) without its editorial note and its two sentences on latency and token cost, which the feed does not carry
# (grading #6319); where it named the first two models it now counts the feed's rows, those on the makers' APIs and those
# on our own GPUs (grading #6569: 17 models). The copy states its cohort's count, so the build stops when a row's differs.
GRADING = "grading"
GRADING_PAIRS = 2_069
# Grading's own page (grading_page): its folder in the build, its address on the mirror (beside its file, which the
# publishing step never touches) and the suite strip's mark.
GRADING_OUT = "_suite/grading/"
GRADING_HOME = "/analysis/grading/"
GRADING_COPY = (
    "This benchmark tests whether a model can classify a machine-written English summary, a question and its reference "
    "answer into three categories: the summary states the reference answer, states a conflicting answer, or does not "
    "answer the question. It measures grading of summaries, not the quality of the grader's own free-form answers.",
    "Initial cohort: 2,069 consensus-labelled pairs from summaries of books, research papers, legal texts and agent "
    "sessions. Repository code is excluded. Raw texts, questions, reference answers, quotations and item-level "
    "predictions are not published.",
    "Reference labels come from independent Claude Opus 5.5 and GPT-6.1 Sol judgments, not human annotation. For labels "
    "that assert an answer, a supporting quotation must be found in the summary. Disputed or invalid judgments are "
    "excluded. Within this cohort, 2,325 pairs were sampled and 256 were excluded. Sampling deliberately enriched cases "
    "that an earlier grader called conflicting answers; this is not a natural class distribution. Excluding "
    "disagreements may remove difficult cases. The summaries are English and machine-written; these results should not "
    "be generalized to Turkish or human-written answers without further testing. d1-ultra was previously selected in "
    "part for agreement with Opus on a separate sample, so agreement with this judge may favor it.",
    "Accuracy is correct first outcomes divided by the frozen cohort size; missing or invalid terminal outputs count "
    "wrong. The displayed score is (accuracy − 1/3) / (2/3) × 100. Zero means uniform random choice among three labels, "
    "100 means every pair correct, and below-chance scores may be negative. ECE uses 10 equal-width probability bins and "
    "is null when usable option probabilities are absent.",
    "{models} models have completed this cohort so far: {api} through their makers' decisions APIs and {local} on our own "
    "GPUs (open decision models and chat models; a chat model's thinking setting is its row's tag). These numbers apply "
    "only to this cohort and request setting. Additional models receive rows only after completion on the same frozen "
    "cohort.",
    "Requests contain one question each. A chat model's reply without a final 'ANSWER: X' line counts wrong (the rule was "
    "fixed before the runs); each row's notes say how many replies that was, and whether it came from the reply format "
    "or from the reasoning parser is not established. The scores are first runs; no diagnostic run was made.",
    "Grading is a separate benchmark tab. Combined scoring is unchanged.",
)
# What a bench's table counts per model, where not questions.
COUNTED = {"backgammon": "decisions", GRADING: "pairs"}


def grading_rows(data: "Data") -> list[dict[str, Any]] | None:
    """Grading's rows once its file is live, else None; stops the build when a row is not on GRADING_PAIRS pairs (the copy
    states the cohort)."""
    if GRADING not in data.by_key or data.by_key[GRADING]["bench"] is None:
        return None
    rows = data.by_key[GRADING]["bench"]["models"]
    if any(row["raw"]["questions"] != GRADING_PAIRS for row in rows):
        raise SystemExit(f"grading feed: a row not on {GRADING_PAIRS:,} pairs; the Methodology copy (GRADING_COPY) states that cohort")
    return rows


def grading_section(data: "Data") -> str:
    """The Methodology page's Grading section (GRADING_COPY), empty until Grading's file is live; its counts of models
    from the feed: on our own GPUs where a row names a checkpoint or its notes say so (ran_here), else a maker's API."""
    rows = grading_rows(data)
    if rows is None:
        return ""
    local = sum(bool(row.get("repo") or ran_here(row.get("notes") or "")) for row in rows)
    facts = {"models": bp.count(len(rows)), "api": bp.count(len(rows) - local), "local": bp.count(local)}
    return (f'<h2 id="grading">Grading: does the text give this answer?</h2>'
            + "".join(f"<p>{esc(text.format_map(facts))}</p>" for text in GRADING_COPY))


GROUPS = "3 benchmark groups"
UNIT = "Score 0–100, chance = 0"
# A cell without a score says why (missing): not on that bench, or a score that does not apply.
NOT_RUN = "Not run"
NOT_APPLICABLE = "Not applicable"
KINDS = (("decision", "Decision models"), ("chat", "Chat models"), ("program", "Programs"))
# The type keys (the Leaderboard's, sitebuild/leaderboard.py TYPES), Decision models the default; the class keys are the
# Leaderboard's classes (Site.model_classes, the empty ones left out), All the default.
TYPES = leaderboard.TYPES
DEFAULT_TYPE = leaderboard.DEFAULT_TYPE
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
    """The other sites' benches as page_config.json lists them, one file each, each with its file's bench (or None until
    published), read now; and the snapshot JSON the build keeps (all-benches/benches.json, by bench key). An address
    that cannot be read keeps its earlier snapshot (found by its address). A file published in the same commit as the
    pages (ALL_BENCHES_LOCAL="key=path", push_pages.sh GRADING_FEED: page and file go live together) is read from disk
    and kept under its address."""
    path = ROOT / SNAPSHOT
    before = {entry["url"]: entry for entry in (json.loads(path.read_text()).get("benches", {}) if path.exists() else {}).values()}
    today = datetime.now(timezone.utc).date().isoformat()
    local = dict(item.split("=", 1) for item in os.environ.get("ALL_BENCHES_LOCAL", "").split(",") if "=" in item)
    kept, out = {}, []
    for spec in site.config["all_benches"]["benches"]:
        if spec["key"] in local:
            print(f"all-benches: {spec['label']}: read from {local[spec['key']]}, published with these pages at {spec['url']}")
            status, data = "published", json.loads(Path(local[spec["key"]]).read_text(encoding="utf-8"))
        else:
            status, data = fetch(spec["url"])
        previous = before.get(spec["url"])
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
            bench = next((item for item in file_benches(entry["file"]) if item.get("bench") == spec["bench"]), None)
        out.append({"key": spec["key"], "label": spec["label"], "short": spec["label"], "parts": spec.get("parts"),
                    "bench": bench, "feed": spec["url"], "seen": entry["seen"]})
        print(f"all-benches: {spec['label']}: " + (f"published, {len(bench['models'])} rows" if bench else NOT_PUBLISHED))
    snapshot = {"about": "The other benches' bench-scores.json as this site's build last read them from their published "
                         "addresses (sitebuild/all_benches.py), by bench: file null while an address serves none; seen: "
                         "the first build that read this state.", "benches": kept}
    return out, json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n"


# A bench file's notes saying a row ran on the site's own hardware (the Reading site's "our GPU (...)", Logic & Math's
# "run on our hardware", Backgammon's "run on our GPUs", Cygnet's "self-hosted"). A negated mention ("never on our GPUs",
# "not run on our hardware") says the opposite and does not count (NOT_LOCAL; Zeki #5188).
LOCAL = re.compile(r"\bour (?:gpus?|hardware)\b|\bself-hosted\b", re.I)
NOT_LOCAL = re.compile(r"\b(?:never|not)\s+(?:\w+\s+){0,2}on\s+our\s+(?:gpus?|hardware)\b", re.I)


def ran_here(notes: str) -> bool:
    """Whether a bench file's notes say the row ran on that site's own hardware (LOCAL, its negations left out)."""
    return bool(LOCAL.search(NOT_LOCAL.sub("", notes)))


# Words in a model's name that say how it ran rather than which model it is, dropped from its name key (name_key).
SETTING_WORDS = {"perplexity", "api", "local", "gpu", "open", "weights", "high", "low", "medium", "max", "minimal", "off",
                 "on"}


def name_key(row: dict[str, Any]) -> str:
    """A row's name for joining where a file has no model_key yet (Ümit #4270): its words in lower case, in any order,
    without its maker's name, setting and route words (SETTING_WORDS) and brackets, "with web" kept as a mark of its own
    (in its name, or in its tag where the file gives one, as this site's rows do): "Decider v1.2 27B" and "Perplexity
    Decider 27B v1.2" (tag "API") meet; the same with the tag "API · with web" stays apart."""
    words = re.sub(r"[(),=]", " ", row["name"].lower()).split()
    web = (any(first == "with" and second == "web" for first, second in zip(words, words[1:]))
           or "with web" in (row.get("tag") or "").lower())
    maker = set((row.get("maker") or "").lower().split())
    kept = sorted(word for word in words if word not in SETTING_WORDS | maker and not (web and word in ("with", "web")))
    return " ".join(kept) + (" +web" if web else "")


def row_keys(row: dict[str, Any]) -> tuple[str | None, str | None, str]:
    """A row's join keys across benches (#4243, #4270): its model_key (the three sites' key: the model's name without
    its setting or route, "-with-web" for a setup with web search; absent from a file that does not carry it yet), its
    repo (lower case, without a commit after @) and its name key (name_key)."""
    return row.get("model_key") or None, (row.get("repo") or "").lower().split("@")[0] or None, name_key(row)


def same_repo(first: str, second: str) -> bool:
    """Two repos (lower case, without a commit after @) name one checkpoint: equal, or equal without the org where one
    side gives none ("pplx-decider-v1.2" and "perplexity-ai/pplx-decider-v1.2")."""
    if first == second:
        return True
    return ("/" not in first or "/" not in second) and first.split("/")[-1] == second.split("/")[-1]


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
        # Every bench, shown or not (the Combined score's Reading · Turkish and pooled Logic & Math), in the page's order.
        self.all_benches: list[dict[str, Any]] = [
            *({"key": key, "label": label, "short": short, "shown": shown, "parts": None, "bench": bench, "feed": feed,
               "seen": None} for (key, label, short, shown), bench in zip(READING, mine)),
            *others]
        self.by_key = {bench["key"]: bench for bench in self.all_benches}
        # A bench with parts shows until every part is live; then its parts show in its place (#4234).
        parts = {part: bench for bench in others if bench["parts"] for part in bench["parts"]}
        split = lambda bench: all(self.by_key[part]["bench"] for part in bench["parts"])  # noqa: E731
        for bench in others:
            bench["shown"] = (not split(bench)) if bench["parts"] else (split(parts[bench["key"]]) if bench["key"] in parts else True)
        self.benches = [bench for bench in self.all_benches if bench["shown"]]
        colours = json.loads((ROOT / "maker_colours.json").read_text())
        self.maker_colour = {norm(maker): entry["colour"] for maker, entry in colours["makers"].items()}
        self.program_colour = colours["programs"]["colour"]
        self.maker_family = {}
        for family in model_families():
            self.maker_family.setdefault(norm(family["maker"]), family["name"])
        self.training = config["training"]
        self.missing_colours: set[str] = set()
        self.only_english = {entry["run"]: entry for entry in english_only(site.results["english_reading"])}
        self.aliases = {bench: names for bench, names in config["aliases"].items() if bench != "about"}
        self.models: dict[str, dict[str, Any]] = {}
        for bench in self.all_benches:
            if bench["bench"]:
                self.add(bench)
        for model in self.models.values():
            model["combined"] = (statistics.fmean(model["scores"][key]["score_0_100"] for key in COMBINED)
                                 if all(key in model["scores"] for key in COMBINED) else None)
            model["class"] = self.model_class(model)
            model["setups"] = self.setups(model)
        # Rows whose benches one model did not answer (page_config.json all_benches.not_combined): their per-bench
        # scores stay, their combined score goes, with the reason the combined board and their page give.
        self.not_combined: list[dict[str, Any]] = []
        for entry in config["not_combined"]:
            match = entry["match"]
            found = next((model for model in self.models.values()
                          if (match["repo"].lower() in model["repos"] if match.get("repo")
                              else match["model_key"] in model["keys"] and model["kind"] == match["kind"])), None)
            if found is None:
                raise SystemExit(f"page_config.json all_benches.not_combined: no row matches {match}")
            found["combined"] = None
            found["not_combined"] = entry["reason"]
            self.not_combined.append(found)
        self.latency_runs(config["latency_runs"])
        self.their = config["their_score"]
        for item in self.their["models"]:
            self.colour(item["maker"], "decision")
        slugs = Counter(model["slug"] for model in self.models.values())
        for model in self.models.values():
            if slugs[model["slug"]] > 1:
                model["slug"] += "-" + model["kind"]
        # A model's page address (?model=): its name, or its slug where another model shows the same name (two setups of
        # one model, told apart by their tags).
        shared = Counter(model["name"].casefold() for model in self.models.values())
        for model in self.models.values():
            model["query"] = model["slug"] if shared[model["name"].casefold()] > 1 else model["name"]

    def colour(self, maker: str | None, kind: str) -> str:
        if kind == "program" or not maker:
            return self.program_colour
        found = self.maker_colour.get(norm(maker))
        if not found:
            self.missing_colours.add(maker)
        return found or GREY

    def run_of(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """This site's setup behind a row of its own benches: its Text run, or an English-only setup as a run
        (english_reading.setup_run); None for the other sites' rows."""
        for item in row.get("runs") or []:
            bench, _, number = str(item).partition(":")
            if bench == "text" and int(number) in self.site.by_id:
                return self.site.by_id[int(number)]
            if bench == "english" and int(number) in self.only_english:
                return setup_run(self.site, self.only_english[int(number)])
        return None

    def add(self, bench: dict[str, Any]) -> None:
        """A bench's rows joined to the models (the three sites' rule, #4243, #4268, #4280): a row joins a model not yet
        on the bench when both have a repo and the repos match (same_repo); else, unless both have repos that differ, when their
        model_key match, whatever route each ran (the route never splits a model, #4270; web search does: its key
        differs), the model of the same kind first; else when page_config.json all_benches.aliases gives the row's name
        on its bench the model's model_key (#4277); else, for a row without model_key, when their name keys match
        (name_key). Else it is a model of its own. The model keeps the name of its first row (this site's, then Logic
        & Math's, then Backgammon's)."""
        rows = [row for row in bench["bench"]["models"] if isinstance(row.get("score_0_100"), (int, float))]
        for row in rows:
            key, repo, name = row_keys(row)
            # A Reading model_key the shared names table maps to the other sites' (its row's source_model_key).
            key = names.key_aliases().get(key, key) if key else key
            kind = kind_of(row)
            # Never two rows of one bench in one model, nor two rows whose repos differ.
            free = [model for model in self.models.values() if bench["key"] not in model["scores"]
                    and not (repo and model["repos"] and not any(same_repo(repo, other) for other in model["repos"]))]
            first = lambda found: min(found, default=None, key=lambda model: model["kind"] != kind)  # noqa: E731
            alias = self.aliases.get(bench["key"], {}).get(row["name"])
            model = (first([model for model in free if repo and any(same_repo(repo, other) for other in model["repos"])])
                     or first([model for model in free if key and key in model["keys"]])
                     or first([model for model in free if alias and alias in model["keys"]])
                     or (first([model for model in free if name in model["names"]]) if not key else None))
            if model is None:
                run = self.run_of(row)
                family = setup_families(self.site).get(run["run"]) if run else None
                family = family["name"] if family else self.maker_family.get(norm(row.get("maker") or ""))
                training = self.training.get(row.get("repo") or "") or self.training.get(row["name"])
                ident = f"repo:{repo}" if repo else f"name:{norm(row['name'] + (row.get('tag') or ''))}|{kind}"
                while ident in self.models:
                    ident += "+"
                model = self.models[ident] = {
                    "key": ident, "name": row["name"], "tag": row.get("tag") or "",
                    "slug": slug(" ".join(filter(None, (row["name"], row.get("tag"))))), "maker": row.get("maker"),
                    "kind": kind, "repo": row.get("repo"), "repos": set(), "keys": set(), "names": set(), "run": run,
                    "family": family, "colour": self.colour(row.get("maker"), kind),
                    "training": training["tag"] if training else None,
                    "size": row.get("params_total"), "active": row.get("params_active"), "scores": {}, "latency": None,
                    "not_combined": None, "setups": None}
            model["scores"][bench["key"]] = row
            model["repos"] |= {repo} - {None}
            model["keys"] |= {key} - {None}
            model["names"].add(name)
            model["repo"] = model["repo"] or row.get("repo")
            if model["size"] is None and row.get("params_total") is not None:
                model["size"], model["active"] = row["params_total"], row.get("params_active")

    def setups(self, model: dict[str, Any]) -> str | None:
        """Where the benches shown ran different setups of one model (Ümit #4270): our hardware (a row with a repo, or
        whose notes say it ran on ours: ran_here) or a hosted API, and the checkpoint where two benches ran different ones;
        which bench ran which, the most common last as "the other benches"; None where they ran one: "Backgammon: a
        hosted API; the other benches: our hardware"."""
        rows = [(bench["label"], model["scores"][bench["key"]]) for bench in self.benches if bench["key"] in model["scores"]]
        local = lambda row: bool(row.get("repo") or ran_here(row.get("notes") or ""))  # noqa: E731
        checkpoint = lambda row: row["repo"].lower().split("@")[0].split("/")[-1]  # noqa: E731  (as same_repo)
        repos = {checkpoint(row) for _, row in rows if row.get("repo")}
        groups: dict[str, list[str]] = {}
        for label, row in rows:
            setup = ("our hardware" + (f", the checkpoint {row['repo'].split('@')[0]}" if row.get("repo") and len(repos) > 1 else "")
                     if local(row) else "a hosted API")
            groups.setdefault(setup, []).append(label)
        if len(groups) < 2:
            return None
        ordered = sorted(groups.items(), key=lambda item: len(item[1]))
        parts = [f"{bp.and_list(labels)}: {setup}" for setup, labels in ordered[:-1]]
        return "; ".join([*parts, f"the other benches: {ordered[-1][0]}"]) + "."

    def model_class(self, model: dict[str, Any]) -> str | None:
        """A model's class (the Leaderboard's Class keys, Site.model_class, Ümit #4245): from this site's setup where it
        has one; else from its bench file: an open model by the total it gives (params_total), a model without one
        Undisclosed (the files give no list price); None where Site.model_class gives none (the setups only this site
        ran, under All only)."""
        if model["run"] is not None:
            return self.site.model_class(model["run"])
        classes = self.site.config["model_classes"]
        if model["size"] is None:
            return classes["undisclosed"]["key"]
        total = model["size"] * 1e9
        return next(item["key"] for item in classes["open"] if item["max"] is None or total <= item["max"])

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
        """The score selector's views in its order: Combined, then each bench shown."""
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

    def ranked(self, view: str, kind: str | None = "decision") -> list[dict[str, Any]]:
        """The models of a kind (every kind with None) with a score in view, highest first."""
        if not self.published(view):
            return []
        models = [model for model in self.models.values()
                  if kind in (None, model["kind"]) and self.score(model, view) is not None]
        return sorted(models, key=lambda model: (-self.score(model, view), model["name"]))

    def default_view(self) -> str:
        return next(view for view in self.views() if self.ranked(view))

    def ordered(self, kind: str | None = "decision") -> list[dict[str, Any]]:
        """The models of a kind (every kind with None) by the default view's score, then the rest by name."""
        view = self.default_view()
        rest = [model for model in self.models.values() if kind in (None, model["kind"]) and self.score(model, view) is None]
        return self.ranked(view, kind) + sorted(rest, key=lambda model: model["name"])

    def their_rows(self) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
        """The index's models in its order, each with our model joined by repo (None: on none of our benches)."""
        by_repo = {repo: model for model in self.models.values() for repo in model["repos"]}
        return [(item, by_repo.get(item["repo"].lower())) for item in self.their["models"]]

    def reference(self) -> dict[str, Any] | None:
        """The reference bar's model: the decision model whose rows carry the reference's model_key (never by its name,
        which may read differently on each site)."""
        key = self.their["reference"]["model_key"]
        return next((model for model in self.models.values() if key in model["keys"] and model["kind"] == "decision"), None)


# ------------------------------------------------------------------------------------------------------------- pieces


def model_href(model: dict[str, Any]) -> str:
    return "?model=" + urllib.request.quote(model["query"], safe="")


def icon(model: dict[str, Any]) -> str:
    if model["family"]:
        return family_icon(model["family"])
    return f'<span class="ab-noicon" style="background:{model["colour"]}" aria-hidden="true"></span>'


def plain_name(model: dict[str, Any]) -> str:
    """A model's name and its setup's tag as plain text (sitebuild/names.py plain): "Perplexity Decider 27B v1.2 · API ·
    with web"; its name alone where its row carries no tag."""
    return names.plain(model["name"], model["tag"])


def name_html(model: dict[str, Any]) -> str:
    """A model's name, then its setup's small tag (how this site ran it, names.tag_html), then its training tag."""
    return esc(model["name"]) + names.tag_html(model["tag"]) + training_tag(model)


def training_tag(model: dict[str, Any]) -> str:
    return f' <span class="ab-tag">{esc(model["training"])}</span>' if model["training"] else ""


def size_text(model: dict[str, Any]) -> str:
    if model["size"] is None:
        return '<span class="nm">Not disclosed</span>'
    total = billions(round(model["size"] * 1e9))
    active = model["active"]
    return total + (f'<span class="small">{billions(round(active * 1e9))} active</span>'
                    if active is not None and abs(active - model["size"]) > 0.005 else "")


def size_label(data: Data, model: dict[str, Any]) -> str:
    """The main table's size, as the Reading site's Leaderboard labels it (Site.label, #4229, #4245, #4269), after
    "Open ·" (Ümit #4445): an open model's total as its maker states it, "MoE" and the active count after a mixture of
    experts; for a model only on the other sites' benches the same from its file (params_total, params_active), "Open ·"
    where its row names a released checkpoint (repo), the size alone where its file settles no openness; empty where
    no size is disclosed."""
    run = model["run"]
    if run is not None:
        return data.site.label(run) if data.site.is_open(run) and stated_total(run) is not None else ""
    if model["size"] is None:
        return ""
    total, active = round(model["size"] * 1e9), model["active"]
    openness = "Open · " if model["repo"] else ""
    if active is None or active >= model["size"]:
        return f'<span class="lb-size">{openness}{label_count(total)}</span>'
    return (f'<span class="lb-size">{openness}{label_count(total)} <sup class="lb-mark" aria-label="mixture of experts">MoE</sup>'
            f' · {billions(round(active * 1e9))} active</span>')


def filters(model: dict[str, Any], css: str = "") -> str:
    """A model's attributes for the type and class keys (all-benches.js): its kind and class; out of view (ab-off)
    unless it is of the default type, as the page opens."""
    classes = " ".join(filter(None, (css, "" if model["kind"] == DEFAULT_TYPE else "ab-off")))
    return (f'{f" class=\"{classes}\"" if classes else ""} data-key="{esc(model["key"])}" data-kind="{model["kind"]}" '
            f'data-class="{model["class"] or ""}"')


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
    return (f'<td class="model">{icon(model)}<a class="model-name" href="{model_href(model)}">{esc(model["name"])}</a>'
            f'{names.tag_html(model["tag"])}{training_tag(model)}'
            f'<span class="small">{esc(model["maker"] or "no maker")}{detail}</span></td>')


def keys(name: str, items: list[tuple[str, str, bool]], attribute: str, label: str) -> str:
    """A row of keys (site.js style): (value, label, pressed)."""
    return (f'<div class="ab-keys needs-js" role="group" aria-label="{esc(label)}"><span class="group-label">{esc(name)}</span>'
            + "".join(f'<button type="button" class="key" {attribute}="{value}" aria-pressed="{str(pressed).lower()}">'
                      f'<span class="lamp" aria-hidden="true"></span>{esc(text)}</button>' for value, text, pressed in items)
            + "</div>")


def shown_if(condition: bool) -> str:
    return "" if condition else " hidden"


def status(word: str, reason: str) -> str:
    """A cell without a score: its status in words, its reason on hover and on keyboard focus (v3.css .hint)."""
    return f'<span class="nm hint" tabindex="0" data-tip="{esc(reason)}">{word}</span>'


def missing(data: Data, model: dict[str, Any], key: str) -> tuple[str, str]:
    """Why a model has no score in view key, (status, reason): Not applicable where the score does not apply (Combined
    without all three benchmark groups, or where one model did not answer every bench; a bench not published yet), else
    Not run (the model is not on that bench). all-benches.js words Head to head's cells the same (script_data's na)."""
    if key == "combined":
        if model["not_combined"]:
            return NOT_APPLICABLE, f"No combined score: {model['not_combined']}"
        lacking = [data.by_key[group]["label"] for group in COMBINED if group not in model["scores"]]
        return NOT_APPLICABLE, f"Combined needs all {GROUPS}; not run on {bp.and_list(lacking)}"
    if not data.published(key):
        return NOT_APPLICABLE, f"{data.by_key[key]['label']}: {NOT_PUBLISHED}"
    return NOT_RUN, f"No {data.by_key[key]['label']} run for this model: it is not in that bench's file"


def missing_cell(data: Data, model: dict[str, Any], key: str) -> str:
    return status(*missing(data, model, key))


def group_names(data: Data) -> list[tuple[str, str, str]]:
    """Combined's benchmark groups, (key, short name, full name): "TR", "Reading · Turkish (all 2,198 questions)"."""
    detail = {"reading": f"all {bp.count(data.by_key['reading']['bench']['models'][0]['raw']['questions'])} questions",
              "logic-math": "pooled"}
    return [(key, COMBINED_SHORT[key], data.by_key[key]["label"] + (f" ({detail[key]})" if key in detail else ""))
            for key in COMBINED]


def groups_label(data: Data) -> str:
    """The label beside Combined (its column's head and its chart's title), what it averages on hover and focus."""
    tip = "The mean, equal weights, of " + "; ".join(f"{short} = {full}" for _, short, full in group_names(data))
    return f'<span class="ab-groups hint" tabindex="0" data-tip="{esc(tip)}">{GROUPS}</span>'


def combined_parts(data: Data, model: dict[str, Any]) -> str:
    """Under a combined score, its three groups' scores: "TR 61.2 L&M 55.0 BG 70.1", each name spelt out on hover."""
    if model["combined"] is None:
        return ""
    return ('<span class="small ab-parts">' + " ".join(
        f'<span><abbr title="{esc(full)}">{esc(short)}</abbr>\u00a0{number(model["scores"][key]["score_0_100"])}</span>'
        for key, short, full in group_names(data)) + "</span>")


def chart_title(data: Data, view: str) -> str:
    """A ranking chart's own head: the score it ranks by (Combined with its groups' label) and the scale's unit."""
    return (f'<h3 class="ab-chart-title">{esc(data.view_label(view))}{" " + groups_label(data) if view == "combined" else ""}'
            f' <span class="small">{UNIT} · higher is better {UP}</span></h3>')


# ------------------------------------------------------------------------------------------------------------- ranking


def bars(data: Data, view: str) -> str:
    """The chart of one view under its title (chart_title): a row per model with a score in it, every kind, highest
    first, its mark and name, then its bar and score (horizontal, so a long name reads in line with its bar, Ümit #4665);
    the default type's in view (the others ab-off until the type keys show them). "tied" marks a bar within the margin
    of the bar in view before it (all-benches.js redraws it as the keys change). In Grading's view a bar's tag is its
    Grading row's where the row gives one (its thinking setting), as in Grading's table."""
    ranked = data.ranked(view, None)
    if not ranked:
        return f'{chart_title(data, view)}<p class="note ab-empty">{empty_note(data, view)}</p>'
    reference = data.reference()
    shown = [model for model in ranked if model["kind"] == DEFAULT_TYPE]
    items = []
    for model in ranked:
        value = data.score(model, view)
        index = shown.index(model) if model in shown else 0
        tied = bool(index) and data.tied(view, shown[index - 1], model)
        ref = model is reference
        title = (f"{plain_name(model)} · {model['maker']}" + (f" · {model['training']}" if model["training"] else "")
                 + f" · {number(value)} {UP}" + (" · reference: TypeSafe's hosted Jev" if ref else ""))
        items.append(
            f'<li{filters(model, "ab-bar" + (" ab-ref" if ref else ""))} data-maker="{esc(model["maker"] or "no maker")}" '
            f'style="--h:{max(0.0, min(100.0, value)):.2f}%;--c:{model["colour"]}">'
            f'<a href="{model_href(model)}" title="{esc(title)}">'
            f'<span class="ab-bar-logo">{icon(model)}</span>'
            f'<span class="ab-bar-name">{esc(model["name"])}{"<span class=\"ab-ref-word\"> (reference)</span>" if ref else ""}'
            f'{names.tag_html((model["scores"][view].get("tag") or model["tag"]) if view == GRADING else model["tag"])}'
            f'{training_tag(model)}</span>'
            f'<span class="ab-bar-track"><span class="ab-bar-fill"></span><span class="ab-bar-value">{number(value)}'
            f'<span class="ab-tied"{"" if tied else " hidden"}>tied</span></span></span></a></li>')
    makers = dict.fromkeys((model["maker"] or "no maker", model["colour"]) for model in ranked)
    visible = {model["maker"] or "no maker" for model in shown}
    legend = "".join(f'<span data-maker="{esc(maker)}"{"" if maker in visible else " class=\"ab-off\""}>'
                     f'<i class="swatch" style="background:{colour}"></i>{esc(maker)}</span>' for maker, colour in makers)
    return (f'{chart_title(data, view)}<ol class="ab-bars" aria-label="{esc(data.view_label(view))}: models by score, '
            f'{UNIT.lower()}, higher is better">'
            f'{"".join(items)}</ol><p class="note ab-none"{"" if not shown else " hidden"}>No model of this type and class '
            f'has a score here.</p><p class="ab-legend families">{legend}</p>{not_combined_note(data, view)}')


def not_combined_note(data: Data, view: str) -> str:
    """Under the combined board: the rows left out of it, each with its reason (Methodology #combined)."""
    if view != "combined" or not data.not_combined:
        return ""
    return "".join(f'<p class="note ab-not-combined">No combined score for <a href="{model_href(model)}">{esc(plain_name(model))}</a>: '
                   f'{esc(model["not_combined"])} (<a href="method/#combined">the rule</a>)</p>' for model in data.not_combined)


def empty_note(data: Data, view: str) -> str:
    if view == "combined":
        missing = [data.by_key[key]["label"] for key in COMBINED if not data.published(key)]
        if missing:
            return (f"No combined score yet: it needs a model on all three of Reading · Turkish, Logic & Math and Backgammon, and "
                    f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} {NOT_PUBLISHED}.")
        return "No model has a score on all three of Reading · Turkish, Logic & Math and Backgammon yet."
    if not data.published(view):
        bench = data.by_key[view]
        return f'{esc(bench["label"])}: {NOT_PUBLISHED} (its file, <a href="{esc(bench["feed"])}">bench-scores.json</a>, is not live).'
    return "No model on this bench yet."


def ranks(values: list[float | None]) -> list[str]:
    """The Rank column of rows in order: the place among the rows with a value, 1, 2, 3 without repeats, rows with the same
    value keeping the table's order, which claims no difference (Zeki #4629, #4630); empty without a value."""
    out, place = [], 0
    for value in values:
        if value is None:
            out.append("")
            continue
        place += 1
        out.append(str(place))
    return out


def main_table(data: Data) -> str:
    """The table under the chart (Ümit #4239): every model side by side, its rows following the type and class keys: #,
    model (maker dot and icon, as on the Leaderboard), size (size_label), Combined (each row's three group scores under its
    value: combined_parts) and each bench shown, the unit (UNIT) once in the caption, never under each head (Ümit #6400),
    a cell without a score its status (missing: Not run, Not applicable, the reason on hover and focus). Sorted
    by the view's score, highest first, the models without one last by name; a column head sorts by its column (again:
    the other way) and a score column's head picks the view (all-benches.js). Rank is the place by the view's score
    among the rows in view, 1, 2, 3 without repeats (Zeki #4630): no bench's file carries an all-pairs test, so no
    tiers."""
    view = data.default_view()
    # The heads name their columns only; the unit (UNIT) is said once, in the caption (Ümit #6400: crowded heads).
    columns = [("combined", "Combined", ""), *((bench["key"], bench["short"], "") for bench in data.benches)]
    models = data.ordered(None)
    numbers = dict(zip((id(model) for model in models if model["kind"] == DEFAULT_TYPE),
                       ranks([data.score(model, view) for model in models if model["kind"] == DEFAULT_TYPE])))
    # sub: the head's small line, as HTML.
    sort = lambda key, label, css="num", sub="": (  # noqa: E731
        f'<th scope="col" class="{css}" data-ab-col="{key}"{" aria-sort=\"descending\"" if key == view else ""}>'
        f'<button type="button" class="ab-sort" data-ab-sort="{key}">{esc(label)}</button>'
        + (f'<span class="small">{sub}</span>' if sub else "") + "</th>")
    head = ('<th scope="col" class="num ab-rank">Rank</th>' + sort("model", "Model", "model") + sort("size", "Size")
            + "".join(sort(key, label, "num" + (" ab-combined" if key == "combined" else ""), sub) for key, label, sub in columns))
    body = []
    for model in models:
        cells = []
        for key, _, _ in columns:
            value = data.score(model, key)
            cells.append(f'<td class="num">{missing_cell(data, model, key)}</td>' if value is None else
                         f'<td class="num" data-v="{value:.4f}">{number(value)}'
                         f'{combined_parts(data, model) if key == "combined" else ""}</td>')
        body.append(f'<tr{filters(model)} data-name="{esc(plain_name(model).casefold())}" '
                    f'data-size="{"" if model["size"] is None else model["size"]}">'
                    f'<td class="num ab-rank">{numbers.get(id(model), "")}</td>{model_cell(model)}'
                    f'<td class="num">{size_label(data, model)}</td>{"".join(cells)}</tr>')
    return (f'<div class="table-wrap ab-main-wrap"><table class="board ab-main"><caption class="ab-caption">Every model in view on '
            f'every bench · {UNIT} · higher is better {UP}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            + "".join(f'<p{filters(model, "note ab-setup-note")} id="setup-{esc(model["slug"])}"><a href="{model_href(model)}">'
                      f'{esc(plain_name(model))}</a>, different setups of one model: {esc(model["setups"])}</p>'
                      for model in models if model["setups"]))


def model_cell(model: dict[str, Any], setups: bool = True, tag: str | None = None, line: str = "") -> str:
    """A table row's model cell: the maker's dot, the family icon, the name opening the model's page, its tag (tag where a
    bench's own row gives one, as Grading's table does: its thinking setting) and training tag, and (setups) the mark when
    its benches ran different setups; line, a small line of its own under them (Grading: replies without an answer)."""
    return (f'<td class="model"><i class="lb-dot" style="background:{model["colour"]}" title="{esc(model["maker"] or "no maker")}"></i>'
            f'{icon(model)}<a class="model-name" href="{model_href(model)}">{esc(model["name"])}</a>'
            f'{names.tag_html(model["tag"] if tag is None else tag)}{training_tag(model)}'
            + (f'<a class="ab-setup-mark" href="#setup-{esc(model["slug"])}" title="{esc(model["setups"])}">setups differ</a>'
               if setups and model["setups"] else "")
            + (f'<span class="small ab-line">{line}</span>' if line else "") + "</td>")


# A Grading chat row's notes say how many of its replies had no final answer line; they count wrong (GRADING_COPY), and
# the table says how many under the row's name, in the model column a phone keeps in view (grading #6569, Zeki #6570:
# LFM3-1.7B's 838 of 2,069).
NO_ANSWER = re.compile(r"\b(\d[\d,]*) of [\d,]+ replies \(\d+%\) had no final 'ANSWER: X' line")


def grading_table(data: Data, models: list[dict[str, Any]]) -> str:
    """Grading's page's table (grading_page): its models as the main table's rows (the type and class keys filter them,
    all-benches.js sorts and ranks them): rank, model with its Grading row's tag and replies without an answer, size,
    score, accuracy (the row's notes on hover, focus and tap, v3.css .hint) and calibration error (ECE, points)."""
    ordered = sorted(models, key=lambda model: (-data.score(model, GRADING), plain_name(model).casefold()))
    decision = [model for model in ordered if model["kind"] == DEFAULT_TYPE]
    numbers = dict(zip((id(model) for model in decision), ranks([data.score(model, GRADING) for model in decision])))
    sort = lambda key, label, css="num": (  # noqa: E731
        f'<th scope="col" class="{css}" data-ab-col="{key}"{" aria-sort=\"descending\"" if key == GRADING else ""}>'
        f'<button type="button" class="ab-sort" data-ab-sort="{key}">{esc(label)}</button></th>')
    head = ('<th scope="col" class="num ab-rank">Rank</th>' + sort("model", "Model", "model") + sort("size", "Size")
            + sort(GRADING, "Score") + '<th scope="col" class="num">Accuracy</th>'
            + f'<th scope="col" class="num">Calibration error {DOWN}</th>')
    body = []
    for model in ordered:
        row = model["scores"][GRADING]
        error = row.get("calibration_error")
        notes = row.get("notes") or ""
        found = NO_ANSWER.search(notes)
        unanswered = int(found.group(1).replace(",", "")) if found else 0
        accuracy = f"{100 * row['raw']['value']:.1f}%"
        if notes:
            accuracy = f'<span class="hint" tabindex="0" data-tip="{esc(notes)}">{accuracy}</span>'
        line = f"{bp.count(unanswered)} of {bp.count(GRADING_PAIRS)} replies without an answer" if unanswered else ""
        body.append(f'<tr{filters(model)} data-name="{esc(plain_name(model).casefold())}" '
                    f'data-size="{"" if model["size"] is None else model["size"]}">'
                    f'<td class="num ab-rank">{numbers.get(id(model), "")}</td>'
                    f'{model_cell(model, setups=False, tag=row.get("tag") or None, line=line)}'
                    f'<td class="num">{size_label(data, model)}</td>'
                    f'<td class="num" data-v="{row["score_0_100"]:.4f}">{number(row["score_0_100"])}</td>'
                    f'<td class="num">{accuracy}</td>'
                    f'<td class="num">{"–" if error is None else number(100 * error)}</td></tr>')
    return (f'<div class="table-wrap ab-main-wrap ab-grading-wrap"><table class="board ab-main"><caption class="ab-caption">'
            f'{bp.count(GRADING_PAIRS)} pairs · {UNIT} · higher is better {UP} · a row\'s notes on its accuracy</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def filter_keys(data: Data, models: Any) -> str:
    """The type and class keys (all-benches.js), the classes only those of these models."""
    type_keys = keys("Type", [(value, label, value == DEFAULT_TYPE) for value, label in TYPES], "data-ab-type", "Model type")
    used = {model["class"] for model in models}
    return type_keys + keys("Class", [("all", "All", True), *((value, label, False) for value, label in data.site.model_classes()
                                                              if value in used)], "data-ab-class", "Class")


def ranking(data: Data) -> str:
    views = data.views()
    default = data.default_view()
    view_keys = keys("Score", [(view, data.view_label(view) + ("" if data.published(view) else " (not published)"),
                                view == default) for view in views], "data-ab-view", "Score the chart ranks by")
    panels = "".join(f'<div class="ab-view" data-view="{view}"{shown_if(view == default)}>{bars(data, view)}</div>'
                     for view in views)
    # No explanation under the chart (Ümit #6402): what the bars, tags, classes and Combined mean is in How it's scored.
    return (f'<section class="card" id="ranking" data-ab-main><h2>Ranking</h2>{filter_keys(data, data.models.values())}{view_keys}'
            f'{panels}{main_table(data)}</section>')


# --------------------------------------------------------------------------------------------------------------- parts


def scoring(data: Data) -> str:
    count = lambda key: bp.count(data.by_key[key]["bench"]["models"][0]["raw"]["questions"])  # noqa: E731
    logic = ("<strong>Logic</strong> and <strong>Math</strong>" if data.by_key["logic"]["shown"]
             else "<strong>Logic &amp; Math</strong>")
    grading = (f'<li><strong>Grading</strong> ({count(GRADING)} pairs of a machine-written English summary, a question and '
               "its reference answer; 3 labels: the summary states that answer, a conflicting one or none): the same "
               "correction with k = 3; its reference labels come from two model judges, not people "
               '(<a href="method/#grading">how it was built</a>).</li>' if grading_rows(data) else "")
    return f"""<section class="card prose" id="scoring" data-ab-main>
      <h2>How it's scored</h2>
      <ul>
        <li>Every bench on one scale: <strong>0 = random guessing, 100 = perfect</strong>; higher is better {UP}.</li>
        <li><strong>Turkish Reading</strong> ({count("turkish-reading")} questions) and <strong>Turkish Grammar</strong> ({count("turkish-grammar")}), 5 options each, <strong>English Reading</strong> ({count("reading-english")} of the reading questions translated into English, 5 options) and {logic}: accuracy corrected for chance, (accuracy − 1/k) / (1 − 1/k) × 100, k the number of options. <strong>Vision</strong>: the same on Reading's {count("reading-vision")} questions that depend on the printed page, read from the page image alone.</li>
        <li><strong>Backgammon</strong>: 0 = the error rate of a player that picks a random legal move, 100 = no error.</li>{grading}
        <li><strong>Combined</strong> = the plain mean of Reading · Turkish (all {count("reading")} Turkish questions), Logic &amp; Math (pooled) and Backgammon, equal weights, as before the splits, only for a model that ran all three, one model on every bench (<a href="method/#combined">the rule</a>).</li>
        <li>Each bar is a model's score in its maker's colour, the maker's mark before its name; the small tag beside the name says how the setup ran where its file gives one (setting · route · snapshot), then the training method where our records state it. A bar, like a dot on the charts, opens the model's page. {esc(data.their["reference"]["name"])} is the reference bar: {esc(data.their["reference"]["note"])}.</li>
        <li>Class: the Reading site's Leaderboard's, by total parameters, else by list price (<a href="method/#filters">the classes</a>).</li>
        <li><strong>Learning from experience</strong> ("did it improve?", points gained, higher is better {UP}) is a column of its own, outside the combined score.</li>
        <li>Lower is better {DOWN} for calibration error (ECE, in points: how far the stated probabilities are from the hit rate) and latency. Close scores read <strong>tied</strong>, never with an interval: <a href="method/#tied">the rule</a>.</li>
        <li>The table under the chart: <strong>Not run</strong>, the model is not on that bench; <strong>Not applicable</strong>, the score does not apply (Combined without all three groups), the reason on hover or focus. Rank is the place by the chosen score among the models in view, 1, 2, 3 without repeats; models with the same score keep the table's order, which claims no difference (no bench's file carries an all-pairs test, so no tiers). A column head sorts by it; again, the other way.</li>
        <li><strong>Full results</strong> adds under each score its calibration error (ECE, points), learning from experience and latency: Reading · Turkish requests on one pinned machine ({esc(PINNED)}), one request at a time, median and 95th percentile.</li>
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
            verdict = (f'<span class="nm">no combined score for {esc(plain_name(first if first["not_combined"] else second))}: '
                       f'one model did not answer every bench</span>')
        elif a is None and b is None:
            verdict = '<span class="nm">neither ran it</span>'
        elif a is None or b is None:
            verdict = f'<span class="nm">only {esc(plain_name(first if b is None else second))} ran it</span>'
        elif data.tied(key, first, second):
            verdict = f"tied ({number(a - b, 1)})"
        else:
            verdict = f"{esc(plain_name(first if a > b else second))} ahead by {number(abs(a - b))}"
        cell = lambda model, value: missing_cell(data, model, key) if value is None else number(value)  # noqa: E731
        rows.append(f'<tr><th scope="row">{esc(label)} {UP}</th><td class="num">{cell(first, a)}</td><td class="num">{cell(second, b)}</td>'
                    f"<td>{verdict}</td></tr>")
    return "".join(rows)


def head_to_head(data: Data) -> str:
    ranked = data.ordered()
    first, second = ranked[0], ranked[1]
    options = lambda chosen: "".join(  # noqa: E731
        f'<optgroup label="{label}">' + "".join(
            f'<option value="{esc(model["key"])}"{" selected" if model is chosen else ""}>{esc(plain_name(model))}</option>'
            for model in sorted((model for model in data.models.values() if model["kind"] == kind), key=lambda model: plain_name(model).lower()))
        + "</optgroup>" for kind, label in KINDS if any(model["kind"] == kind for model in data.models.values()))
    return f"""<section class="card" id="head-to-head" data-ab-main>
      <h2>Head to head</h2>
      <div class="compare-pickers ab-pickers needs-js">
        <label class="control">First <select data-ab-pick="a">{options(first)}</select></label>
        <label class="control">Second <select data-ab-pick="b">{options(second)}</select></label>
      </div>
      <div class="table-wrap"><table class="board ab-h2h"><caption class="ab-caption">{UNIT} · higher is better {UP} · the difference in points; "tied" where the two are too close to tell apart (<a href="method/#tied">the rule</a>)</caption><thead><tr><th scope="col">Bench</th><th scope="col" class="num"><span data-ab-name="a">{esc(plain_name(first))}</span></th><th scope="col" class="num"><span data-ab-name="b">{esc(plain_name(second))}</span></th><th scope="col">Difference</th></tr></thead>
      <tbody data-ab-h2h>{h2h_rows(data, first, second)}</tbody></table></div>
    </section>"""


def improvement(data: Data, model: dict[str, Any]) -> list[tuple[str, float]]:
    """A model's learning-from-experience points by bench shown."""
    return [(bench["label"], model["scores"][bench["key"]]["improvement_points"]) for bench in data.benches
            if model["scores"].get(bench["key"], {}).get("improvement_points") is not None]


def results_table(data: Data, kind: str, caption: str) -> str:
    """Full results for one kind: every model of it on every bench shown, with calibration error, learning from
    experience and latency; its rows follow the class keys, and the table the type keys (all-benches.js). The heads name
    their columns only; the score's unit and the calibration error under each score are said once, in the caption
    (Ümit #6400: crowded heads; Zeki #6436)."""
    models = data.ordered(kind)
    if not models:
        return ""
    head = ['<th scope="col">Model</th>', '<th scope="col" class="num">Size</th>',
            f'<th scope="col" class="num ab-combined">Combined {UP}</th>']
    for bench in data.benches:
        sub = "" if bench["bench"] else f'<span class="small">{NOT_PUBLISHED}</span>'
        head.append(f'<th scope="col" class="num">{esc(bench["label"])} {UP}{sub}</th>')
    head += [f'<th scope="col" class="num">Learning from experience {UP}<span class="small">points gained</span></th>',
             f'<th scope="col" class="num">Latency {DOWN}<span class="small">median, p95</span></th>']
    body = []
    for model in models:
        cells = [name_cell(model), f'<td class="num">{size_text(model)}</td>',
                 f'<td class="num">{missing_cell(data, model, "combined") if model["combined"] is None else number(model["combined"]) + combined_parts(data, model)}'
                 f'{"<span class=\"small\">not one model</span>" if model["not_combined"] else ""}</td>']
        for bench in data.benches:
            row = model["scores"].get(bench["key"])
            cells.append(f'<td class="num">{missing_cell(data, model, bench["key"]) if row is None else number(row["score_0_100"]) + ece_text(row)}</td>')
        cells.append(f'<td class="num">{"<br>".join(f"{esc(label)} {number(value)}" for label, value in improvement(data, model)) or "–"}</td>')
        cells.append(f'<td class="num">{latency_text(model)}</td>')
        body.append(f"<tr{filters(model)}>" + "".join(cells) + "</tr>")
    return (f'<div class="table-wrap ab-kind-table{"" if kind == DEFAULT_TYPE else " ab-off"}" data-kind="{kind}">'
            f'<table class="board ab-results"><caption>{esc(caption)}</caption><thead><tr>{"".join(head)}'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def full_results(data: Data) -> str:
    """Every number per model and kind; what its columns mean is in each table's caption and in How it's scored, no
    paragraph above it (Ümit #6402)."""
    first = f"highest first by {data.view_label(data.default_view())} · {UNIT} · ECE {DOWN} under each score"
    return f"""<section class="card" id="results" data-ab-main>
      <h2>Full results</h2>
      {"".join(results_table(data, kind, f"{label} · {first}") for kind, label in KINDS)}
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
    it fits, readable in both themes (the site's CSS variables); every kind's dots, each with the type and class keys'
    attributes (filters)."""
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
                 f'<text class="axis-title" transform="translate(13 {(T + H - B) / 2:.0f}) rotate(-90)" text-anchor="middle">{UNIT} {UP}</text>')
    boxes: list[tuple[float, float, float, float]] = []
    dots, names_drawn = [], []
    # The default type's names are placed first, so the page opens with as many of them named as fit.
    for model, x_value, y_value in sorted(points, key=lambda item: (item[0]["kind"] != DEFAULT_TYPE, -item[2])):
        x, y = place_x(x_value), place_y(y_value)
        dots.append(f'<a href="{model_href(model)}"{filters(model)}><circle class="ab-dot" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{model["colour"]}">'
                    f'<title>{esc(plain_name(model))}: {number(y_value)}, {esc(x_title)} {tick_text(round(x_value, 1))}</title></circle></a>')
        width = 6.2 * len(plain_name(model))
        box = (x + 8, y - 9, x + 8 + width, y + 4)
        if box[2] > W - R:
            box = (x - 8 - width, y - 9, x - 8, y + 4)
        if box[0] >= L and not any(box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3] for other in boxes):
            boxes.append(box)
            names_drawn.append(f'<text{filters(model, "ab-dot-label")} x="{box[0]:.1f}" y="{y + 3.5:.1f}">{esc(plain_name(model))}</text>')
    return (f'<svg class="ab-scatter" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}{"".join(dots)}{"".join(names_drawn)}</svg>')


def combined_ece(model: dict[str, Any]) -> float | None:
    """The calibration error on the Combined view (Ümit #4270): the mean of the calibration errors of the benches in
    Combined that give one for the model; none with fewer than two."""
    values = [model["scores"][key]["calibration_error"] for key in COMBINED
              if model["scores"].get(key, {}).get("calibration_error") is not None]
    return statistics.fmean(values) if len(values) >= 2 else None


def charts_for(data: Data, view: str) -> str:
    ranked = data.ranked(view, None)
    if not ranked:
        return f'<p class="note">{empty_note(data, view)}</p>'
    title = data.view_label(view)
    if view == "combined":
        ece = combined_ece
    else:
        ece = lambda model: model["scores"][view].get("calibration_error")  # noqa: E731
    specs = [
        ("size", "Size against score", "Parameters, billions (log scale)", lambda model: model["size"], True,
         "models whose maker discloses no size are left out"),
        ("calibration", f"Calibration error {DOWN} against score", "Calibration error, ECE in points" + (": mean of the benches' calibration errors" if view == "combined" else ""),
         lambda model: None if ece(model) is None else 100 * ece(model), False, "models without a calibration error are left out"),
        ("latency", f"Latency {DOWN} against score", "Median time per request, ms (log scale)",
         lambda model: (model["latency"] or {}).get("median"), True, f"latency: Reading · Turkish requests on {PINNED}"),
    ]
    out = []
    shown = [model for model in ranked if model["kind"] == DEFAULT_TYPE]
    for key, heading, x_title, measure, log, rule in specs:
        points = [(model, measure(model), data.score(model, view)) for model in ranked if measure(model) is not None]
        if points:
            figure = scatter(points, x_title, f"{heading}: {title}", log)
            dots = sum(model["kind"] == DEFAULT_TYPE for model, _, _ in points)
            left = len(shown) - dots
            sub = (f'<p class="chart-sub" data-ab-sub="{esc(title)}" data-rule="{esc(rule)}">{esc(title)}: {dots} decision models'
                   + (f"; {left} left out ({esc(rule)})" if left else "") + "</p>")
        else:
            figure = (f'<p class="note ab-empty">No model on {esc(title)} has been {NOT_TIMED.replace("not timed", "timed")}.</p>'
                      if key == "latency" else '<p class="note ab-empty">No points yet.</p>')
            sub = f'<p class="chart-sub">{esc(rule[:1].upper() + rule[1:])}</p>'
        out.append(f'<figure class="chart-card ab-chart" id="chart-{key}-{view}"><figcaption class="chart-head"><h3>{heading}</h3>'
                   f'{sub}</figcaption>{figure}</figure>')
    return "".join(out)


def charts(data: Data) -> str:
    default = data.default_view()
    panels = [f'<div class="ab-view ab-charts" data-view="{view}"{shown_if(view == default)}>{charts_for(data, view)}</div>'
              for view in data.views()]
    return (f'<section class="card" id="charts" data-ab-main><h2>Size, calibration and latency against score</h2>'
            f'{"".join(panels)}</section>')


def their_for(data: Data, view: str) -> str:
    rows = data.their_rows()
    ours = [(item, model, data.score(model, view) if model else None) for item, model in rows]
    measured = [(item, model, value) for item, model, value in ours if value is not None]
    # Our places 1, 2, 3 without repeats (Zeki #4630); models with the same score keep the index's order.
    our_rank = {id(model): place for place, (_, model, _) in enumerate(sorted(measured, key=lambda entry: -entry[2]), 1)}
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
        lines.append(f'<tr class="ab-ref-row"><td class="num">ref.</td><td class="model">{icon(reference)}<a class="model-name" href="{model_href(reference)}">{esc(reference["name"])}</a>{names.tag_html(reference["tag"])}'
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
            f'<th scope="col">Our score {UP}<span class="small">{esc(data.view_label(view))}, {UNIT.lower()}</span></th><th scope="col" class="num">Our rank<span class="small">of these</span></th></tr></thead>'
            f'<tbody>{"".join(lines)}</tbody></table></div>')


def their_score(data: Data) -> str:
    default = data.default_view()
    panels = [f'<div class="ab-view" data-view="{view}"{shown_if(view == default)}>{their_for(data, view)}</div>'
              for view in data.views()]
    their = data.their
    return (f'<section class="card" id="their-score" data-ab-main><h2>Their score against ours</h2>'
            f'<p class="note">{esc(their["name"])} {esc(their["edition"])}, {esc(their["measure"])} ({bp.long_date(their["date"])}, '
            f'<a href="{esc(their["source"])}">source</a>): a sanity check, never our score; its 15 open decision models joined '
            f"to ours by Hugging Face repo.</p>{''.join(panels)}</section>")


# ---------------------------------------------------------------------------------------------------------------- tabs


def bench_table(data: Data, bench: dict[str, Any], kind: str) -> str:
    view = bench["key"]
    ranked = data.ranked(view, kind)
    if not ranked:
        return ""
    rows = []
    for index, model in enumerate(ranked):
        row = model["scores"][view]
        tie = (f'<span class="small">tied with {esc(plain_name(ranked[index - 1]))}</span>'
               if index and data.tied(view, ranked[index - 1], model) else "")
        raw = row["raw"]
        raw_text = (f'{100 * raw["value"]:.1f}%' if raw.get("metric") == "accuracy" else f'{raw["value"]:g}'
                    if isinstance(raw.get("value"), (int, float)) else "–")
        commit = row.get("commit")
        rows.append(f'<tr><td class="num">{index + 1}</td>{name_cell(model)}<td class="num">{size_text(model)}</td>'
                    f'<td class="num">{number(row["score_0_100"])}{tie}</td><td class="num">{raw_text}<span class="small">{bp.count(raw["questions"])} {COUNTED.get(view, "questions")}</span></td>'
                    f'<td class="num">{"–" if row.get("calibration_error") is None else number(100 * row["calibration_error"])}</td>'
                    f'<td>{esc(commit[:7]) if commit else "<span class=\"nm\">no repo</span>"}</td></tr>')
    metric = ranked[0]["scores"][view]["raw"].get("metric", "raw")
    return (f'<h4 class="board-group">{dict(KINDS)[kind]}</h4><div class="table-wrap"><table class="board ab-bench-table"><thead><tr>'
            f'<th scope="col" class="num">Rank</th><th scope="col">Model</th><th scope="col" class="num">Size</th>'
            f'<th scope="col" class="num">Score {UP}<span class="small">{UNIT.removeprefix("Score ")}</span></th><th scope="col" class="num">{esc(str(metric).capitalize())}</th>'
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
            + "".join(bench_table(data, bench, kind) for kind, _ in KINDS)
            + f'<p class="note">{count} {COUNTED.get(bench["key"], "questions")} per model · updated '
            f'{esc(bp.long_date(file["updated"]) if file.get("updated") else "–")} · 0 = {esc(str(score.get("zero", "chance")))}; '
            f'100 = {esc(str(score.get("hundred", "perfect")))} · feed: <a href="{esc(bench["feed"])}">bench-scores.json</a></p>')


def learning_panel(data: Data) -> str:
    rows = [(model, improvement(data, model)) for model in data.models.values()]
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
    level = [plain_name(other) for other in ranked if other is not model and data.tied(view, model, other)]
    return (f"{index + 1} of {len(ranked)}" + (f'<span class="small">tied with {esc(", ".join(level[:3]))}'
                                               f'{f" and {len(level) - 3} more" if len(level) > 3 else ""}</span>' if level else ""))


def model_page(data: Data, model: dict[str, Any]) -> str:
    rows = []
    # Every bench, the ones only the Combined score uses (not shown elsewhere on the page) named so.
    for key, label in [("combined", "Combined"), *((bench["key"], bench["label"] + ("" if bench["shown"] else " (in Combined)"))
                                                   for bench in data.all_benches if bench["shown"] or bench["bench"])]:
        if not data.published(key):
            rows.append(f'<tr><th scope="row">{esc(label)}</th><td colspan="5"><span class="nm">{NOT_PUBLISHED}</span></td></tr>')
            continue
        value = data.score(model, key)
        head = f'<th scope="row">{esc(label)}{"<span class=\"small\">" + groups_label(data) + "</span>" if key == "combined" else ""}</th>'
        if value is None:
            word, reason = missing(data, model, key)
            rows.append(f'<tr>{head}<td colspan="5"><span class="nm">{word}</span><span class="small">{esc(reason)}</span></td></tr>')
            continue
        row = model["scores"].get(key) or {}
        commit = row.get("commit")
        runs = ", ".join(map(str, row.get("runs") or [])) or "–"
        # The bench file's own notes on the row (how and where it ran, a provisional status), as the file words them.
        notes = f'<span class="small ab-row-notes">{esc(row["notes"])}</span>' if row.get("notes") else ""
        rows.append(f'<tr>{head}<td class="num">{number(value)}{combined_parts(data, model) if key == "combined" else ""}</td><td class="num">{rank_text(data, model, key)}</td>'
                    f'<td class="num">{"–" if row.get("calibration_error") is None else number(100 * row["calibration_error"])}</td>'
                    f'<td>{f"<code title=\"{esc(commit)}\">{esc(commit[:7])}</code>" if commit else "–"}</td><td><span class="small">{esc(runs)}</span>{notes}</td></tr>')
    points = improvement(data, model)
    their = next((item for item, joined in data.their_rows() if joined is model), None)
    facts = [f"<li>Maker: {esc(model['maker'] or 'none')}{' · training: ' + esc(model['training']) if model['training'] else ''}</li>",
             f"<li>Kind: {dict(KINDS)[model['kind']][:-1].lower()} · class: {esc(dict(data.site.model_classes()).get(model['class'] or '', 'none'))}</li>",
             f"<li>Size: {size_text(model).replace('<span class=\"small\">', ' (').replace('</span>', ')') if model['size'] is not None else 'not disclosed'}</li>",
             f"<li>Repo: {'<a href=\"https://huggingface.co/' + esc(model['repo']) + '\">' + esc(model['repo']) + '</a>' if model['repo'] else 'none (an API setup, or no released checkpoint)'}</li>",
             f"<li>Latency {DOWN}: {esc(latency_words(model))}</li>",
             f"<li>Learning from experience {UP}: {', '.join(f'{esc(label)} {number(value)} points' for label, value in points) or 'not published for it yet'}</li>"]
    if model["setups"]:
        facts.append(f"<li>Setups: {esc(model['setups'])}</li>")
    if their:
        facts.append(f"<li>{esc(data.their['name'])} {esc(data.their['measure'])}: {number(their['score'])} (theirs, a sanity check; not our score)</li>")
    return (f'<section class="card ab-model" data-ab-model="{esc(model["slug"])}" data-ab-model-name="{esc(plain_name(model))}" '
            f'data-ab-model-key="{esc(model["key"])}" hidden><p class="ab-back"><a href="./" data-ab-back>← {TITLE}</a></p>'
            f'<h1>{icon(model)}{name_html(model)}</h1><ul class="ab-facts">{"".join(facts)}</ul>'
            f'<div class="table-wrap"><table class="board"><thead><tr><th scope="col">Bench</th><th scope="col" class="num">Score {UP}<span class="small">{UNIT.removeprefix("Score ")}</span></th>'
            f'<th scope="col" class="num">Rank<span class="small">among {dict(KINDS)[model["kind"]].lower()}</span></th>'
            f'<th scope="col" class="num">Calibration error {DOWN}<span class="small">ECE, points</span></th><th scope="col">Commit</th><th scope="col">Runs</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


# ----------------------------------------------------------------------------------------------------------- the pages


def script_data(data: Data, models: Any = None, view: str | None = None) -> str:
    """What all-benches.js needs: the benches shown, Combined's, and every model's kind, size class and scores with
    their question counts (Head to head, the margins of "tied"), and why it has no combined score (na: missing's
    reason) where it has none. A page of one bench (Grading's) gives its view and its models."""
    payload = {
        "benches": [{"key": bench["key"], "label": bench["label"], "published": bench["bench"] is not None}
                    for bench in data.benches if view is None or bench["key"] == view],
        "combined": list(COMBINED),
        "default": view or data.default_view(),
        "type": DEFAULT_TYPE,
        "types": {value: label for value, label in TYPES},
        "kinds": dict(KINDS),
        "models": [{"key": model["key"], "name": model["name"], "label": plain_name(model), "slug": model["slug"], "repo": model["repo"],
                    "kind": model["kind"], "class": model["class"],
                    "scores": {key: [row["score_0_100"], row["raw"]["questions"]] for key, row in model["scores"].items()},
                    "combined": model["combined"], "nc": bool(model["not_combined"]),
                    "na": None if model["combined"] is not None else missing(data, model, "combined")[1]}
                   for model in (data.models.values() if models is None else models)],
    }
    return f'<script type="application/json" id="ab-data">{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}</script>'


def frame(data: Data, path: str, title: str, description: str, body: str, image: str, scripts: tuple[str, ...] = (), *,
          home: str | None = None, here: str | None = None, name: str = TITLE, footer: str | None = None) -> str:
    """A whole page of OUT at path ("" or "method/"), for its address under /analysis/all-benches/: the head with its
    title and the brand (BRAND, as the Reading site's pages), its canonical address, its link preview (image: the
    preview's path in OUT, share_images; the same tags as the Reading site's pages, Site.page), the theme line of the
    Reading site's pages and the folder's own copies of the files (ASSETS, versioned as site.asset does), then the one
    sticky header: the suite strip with All benches marked (suite_bar), and the page's own title row, its name linking
    the page and the Dark / Light switch (site.js), without the Reading site's tabs; the family icons; the body; a
    footer. Another folder's page (Grading's) gives its own address (home), its suite strip mark (here), its name and its
    footer's contents."""
    root = rel(path, "")
    config = data.site.config["all_benches"]
    home = home or config["url"]
    extra = "".join(f'\n  <script src="{root}{asset(script)}" defer></script>' for script in scripts)
    named = f"{title} · {BRAND}"
    size = data.site.config["images"]["preview"]
    preview = "".join(f'\n  <meta {attr}="{name}" content="{value}">' for attr, name, value in (
        ("property", "og:title", esc(named)), ("property", "og:description", esc(description)),
        ("property", "og:type", "website"), ("property", "og:url", esc(home + path)),
        ("property", "og:image", esc(config["url"] + image)), ("property", "og:image:width", size["width"]),
        ("property", "og:image:height", size["height"]), ("name", "twitter:card", "summary_large_image"),
        ("name", "twitter:title", esc(named)), ("name", "twitter:description", esc(description)),
        ("name", "twitter:image", esc(config["url"] + image))))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(named)}</title>
  <link rel="canonical" href="{esc(home + path)}">
  <meta name="description" content="{esc(description)}">{preview}
  <script>document.documentElement.classList.add("js"); document.documentElement.dataset.theme = "dark"; try {{ if (localStorage.getItem("theme") === "light") document.documentElement.dataset.theme = "light"; }} catch (e) {{}}</script>
  <link rel="stylesheet" href="{root}{asset(SUITE_CSS)}">
  <link rel="stylesheet" href="{root}{asset("v3.css")}">
  <link rel="stylesheet" href="{root}{asset("all-benches.css")}">
  <script src="{root}{asset("site.js")}" defer></script>{extra}
</head>
<body class="v3">
  <a class="skip" href="#main">Skip to content</a>
  <div class="site-header">
  {suite_bar(here or suite_path(data.site))}
  <header class="site-bar"><div class="site-bar-in"><div class="site-title-row"><a class="site-title" href="{root}">{esc(name)}</a>{THEME_SWITCH}</div></div></header>
  </div>
  {family_sprite()}
  <main id="main">
{body}
  </main>
  <footer class="footer">
    {footer or f'<nav class="footer-links" aria-label="Site"><a href="{root}">{TITLE}</a> · <a href="{root}{METHOD}">Methodology</a> · <a href="{esc(data.site.config["site_url"])}">Reading bench</a></nav>'}
    {"" if footer else f"<p>Reading · Turkish, English and Vision: {data.site.version()}</p>"}
  </footer>
</body>
</html>
"""


def grading_page(data: Data, image: str) -> str | None:
    """Grading's own page (Ümit #6420, Zeki #6424), at /analysis/grading/ beside its file, its tab in the suite strip, in
    All benches' format: the type and class keys over its ranking and its table (all-benches.js), no paragraphs (Ümit
    #6402, #6440), one line with its count, its date and its file; a model's name opens its All benches page, the
    footer's Methodology All benches' Grading section. None until Grading's file is live."""
    if grading_rows(data) is None:
        return None
    home = urllib.parse.urljoin(data.site.config["all_benches"]["url"], GRADING_HOME)
    up = posixpath.relpath(suite_path(data.site), GRADING_HOME) + "/"
    bench = data.by_key[GRADING]
    models = [model for model in data.models.values() if GRADING in model["scores"]]
    line = (f'<p class="note">{bp.count(GRADING_PAIRS)} pairs per model · updated {esc(bp.long_date(bench["bench"]["updated"]))} '
            f'· <a href="{esc(bench["feed"])}">bench-scores.json</a></p>')
    body = (script_data(data, models, GRADING) + '<h1 class="visually-hidden" id="top">Grading</h1>'
            f'<section class="card" id="ranking" data-ab-main>{filter_keys(data, models)}'
            f'<div class="ab-view" data-view="{GRADING}">{bars(data, GRADING)}</div>{grading_table(data, models)}{line}</section>')
    footer = (f'<nav class="footer-links" aria-label="Site"><a href="./">Grading</a> · <a href="{up}{METHOD}#grading">'
              f'Methodology</a> · <a href="{up}">{TITLE}</a></nav>')
    html = frame(data, "", "Grading", f"Grading: does the text give this answer? Each model's score from 0 (chance) to 100 "
                 f"(perfect) on {GRADING_PAIRS:,} pairs.", body, image, home=home, here=GRADING_HOME, name="Grading",
                 footer=footer, scripts=("all-benches.js",))
    return html.replace('href="?model=', f'href="{up}?model=')


def suite_path(site: Site) -> str:
    """The pages' address on the mirror, as the suite strip links it: /analysis/all-benches/."""
    return urllib.parse.urlparse(site.config["all_benches"]["url"]).path


def page(data: Data, image: str) -> str:
    # No visible intro (Ümit via Zeki #4646): the keys, the chart and the results come first. The page's h1 stays for
    # screen readers and as #top; a model's page hides it with the rest (data-ab-main).
    body = f"""    {script_data(data)}
    <h1 class="visually-hidden" id="top" data-ab-main>{TITLE}</h1>
    {ranking(data)}
    {scoring(data)}
    {head_to_head(data)}
    {full_results(data)}
    {charts(data)}
    {their_score(data)}
    {bench_tabs(data)}
    {"".join(model_page(data, model) for model in data.models.values())}"""
    return frame(data, PATH, TITLE, "The decision and chat models on every bench of the three sites and Grading on one page: "
                 "Turkish reading and grammar, English reading, Vision, Logic, Math, Backgammon and Grading, each scored 0 to 100 (0 = "
                 "chance, 100 = perfect), their combined score, head to head, and each bench's full table.", body, image,
                 scripts=("all-benches.js",))


def method_page(data: Data, image: str) -> str:
    site = data.site
    n_text, n_reading, n_grammar, n_english, n_vision = (data.by_key[key]["bench"]["models"][0]["raw"]["questions"]
                                                         for key, *_ in READING)
    split = data.by_key["logic"]["shown"]
    sources = "".join(
        f'<li>{esc(bench["label"])}{"" if bench["shown"] else " (in Combined only)" if bench["key"] in COMBINED else " (not shown until both parts are live)"}: '
        f'<a href="{esc(bench["feed"])}">{esc(bench["feed"])}</a> — '
        + (f'published, {len(bench["bench"]["models"])} rows, updated {esc(bp.long_date(bench["bench"]["updated"]))}'
           if bench["bench"] and bench["bench"].get("updated") else NOT_PUBLISHED)
        + "</li>" for bench in data.all_benches)
    missing = sorted(data.missing_colours)
    up = rel(METHOD, PATH)
    body = f"""    <section class="card prose" id="method">
      <p class="ab-back"><a href="{up}">← {TITLE}</a></p>
      <h1>{TITLE}: Methodology</h1>
      <p>How the page <a href="{up}">{TITLE}</a> puts the benches of the three sites and Grading side by side. It uses only the files each bench publishes, bench-scores.json, in one schema for the three sites; a bench whose file is not live says "{NOT_PUBLISHED}".</p>
      <h2 id="scale">One scale: 0 = random guessing, 100 = perfect</h2>
      <ul>
        <li><strong>Turkish Reading</strong> and <strong>Turkish Grammar</strong>: the Reading site's {bp.count(n_reading)} Turkish reading questions (units 1 to 6) and its {bp.count(n_grammar)} grammar questions (units 7 to 20), 5 options each, as its Text tab asks them, each part scored on its own questions: Score = (accuracy − 1/k) / (1 − 1/k) × 100 with k = 5: 20% right reads 0, every question right reads 100. Below 0 means worse than guessing. The row is the setup the Text tab's Leaderboard shows, the same run on both parts.</li>
        <li><strong>English Reading</strong>: the {bp.count(n_english)} reading questions kept after translation into English (the Reading site's <a href="{esc(site.config["site_url"])}english/">English reading</a> page), 5 options each, the same score with k = 5. A model's row is its first English run of the setup its Turkish row shows (else of another setup of the same row, in the Leaderboard's order); the models run only in English have a row here and none on the Turkish benches.</li>
        <li><strong>Vision</strong>: the {bp.count(n_vision)} questions that depend on the printed page, asked with the page image alone (the Reading site's Vision tab, condition B), k = each question's number of options. Models that read only text are not on it.</li>
        <li>{"<strong>Logic</strong> and <strong>Math</strong>: the Logic &amp; Math site's two parts, each in a file of its own" if split else "<strong>Logic &amp; Math</strong>: the Logic &amp; Math site's pooled score; its two parts, Logic and Math, show in its place once their files are live"}: the same correction, on its own questions (k = 5), as its file states.</li>
        <li><strong>Backgammon</strong>: 0 = the error rate of a player that picks a random legal move, 100 = no error, as its file states.</li>
        {f'<li><strong>Grading</strong>: {bp.count(GRADING_PAIRS)} pairs of a machine-written English summary, a question and its reference answer, 3 labels each, the same correction with k = 3: one label in three at random reads 0, every pair right reads 100 (<a href="#grading">Grading</a>).</li>' if grading_rows(data) else ""}
        <li>Higher is better {UP} on every score; lower is better {DOWN} for calibration error and latency. Size has no better direction.</li>
        <li>A score is not a share of right answers: the chart's head and the table's caption name its unit, "{UNIT}", and a score never takes a % sign. Raw accuracy, in each bench's table, keeps its %.</li>
      </ul>
      <h2 id="combined">Combined score</h2>
      <p>The plain mean, equal weights, of Reading · Turkish (all {bp.count(n_text)} Turkish questions, reading and grammar together, the Reading site's own score), Logic &amp; Math (the Logic &amp; Math site's pooled score, logic-math in its bench-scores.json) and Backgammon, unchanged by the splits into Turkish Reading and Turkish Grammar and into Logic and Math (project lead, #4173, #4234, #4239): the parts are views of their own, never averaged in. Only a model with a score on all three gets one; the others appear in each bench's tab. English Reading, Vision and Grading are not part of it.</p>
      <p>A row gets a combined score only if one model answered every bench: the same checkpoint (one repo, one set of weights) or the same served version of a hosted model. A hosted service that changed its model between the benches' runs keeps its score on each bench, but gets no combined score{":" if data.not_combined else "."}</p>
      {"<ul>" + "".join(f"<li>{esc(model['name'])}: {esc(model['not_combined'])}</li>" for model in data.not_combined) + "</ul>" if data.not_combined else ""}
      <p>The page labels Combined "{GROUPS}" and shows under each combined score its three parts: {"; ".join(f"{esc(short)}, {esc(full)}" for _, short, full in group_names(data))}.</p>
      {grading_section(data)}
      <h2 id="missing">A cell without a score</h2>
      <p>Each says why, the reason on hover and on keyboard focus: <strong>{NOT_RUN}</strong>, the model is not on that bench; <strong>{NOT_APPLICABLE}</strong>, the score does not apply: Combined for a model without all {GROUPS}, or where one model did not answer every bench, and a bench whose file is not published yet. Sorting by a column puts such cells last.</p>
      <h2 id="learning">Learning from experience</h2>
      <p>"Did it improve?": the points a model gains from its own experience, as a bench's file gives them (improvement_points). A column of its own, never part of the combined score.</p>
      <h2 id="tied">When we write "tied"</h2>
      <p>No interval bars and no ranges: where two scores are too close to tell apart, the page says <strong>tied</strong>. The rule, the same everywhere on the page:</p>
      <ul>
        <li>On one bench, two models are tied when their scores differ by less than <strong>100 ÷ √n points</strong>, n being the smaller of their two question counts on that bench (Backgammon: scored decisions; Grading: pairs). On Turkish Reading's {bp.count(n_reading)} questions that is {number(100 / math.sqrt(n_reading), 2)} points; on Turkish Grammar's {bp.count(n_grammar)} {number(100 / math.sqrt(n_grammar), 2)}; on English Reading's {bp.count(n_english)} {number(100 / math.sqrt(n_english), 2)}; on Vision's {bp.count(n_vision)} {number(100 / math.sqrt(n_vision), 2)}; on Reading · Turkish's {bp.count(n_text)}, in the Combined score, {number(100 / math.sqrt(n_text), 2)}{f"; on Grading's {bp.count(GRADING_PAIRS)} pairs {number(100 / math.sqrt(GRADING_PAIRS), 2)}" if grading_rows(data) else ""}. The margin is about the size of the noise a score on n questions carries, so a smaller bench needs a larger gap.</li>
        <li>On the combined score, a mean of three, the three benches' margins add up as noise does: √(m₁² + m₂² + m₃²) ÷ 3.</li>
        <li>The ranking marks a bar "tied" when it is within the margin of the bar in view before it; Head to head says "tied" for a bench where the two are within it; each bench's table writes "tied with" the row above. Ties are not chained: A tied with B and B with C does not tie A with C.</li>
        <li>The table under the chart numbers its rows in a Rank column: the place by the score chosen among the models in view, 1, 2, 3 without repeats; models with the same score keep the table's order, which claims no difference. Each bench's table numbers its rows the same way, and "tied with" there marks the margin above. No bench's file carries the all-pairs test the Reading site's Leaderboard draws its tiers from, so there are no tiers here.</li>
      </ul>
      <h2 id="calibration">Calibration error</h2>
      <p>ECE: the answers sorted into 10 equal-width bins of the chosen option's probability; in each bin the gap between the mean probability and the share right, weighted by the answers in it; shown in points (×100), lower is better {DOWN}. Reading · Turkish's is its Text tab run's, as the Text tab gives it; Turkish Reading's and Turkish Grammar's are the same run's, computed the same way over the part's answers that carry a probability; English Reading's is its first English run's, computed the same way (none for a run without a probability); Vision's the page-image run's; the other benches' as their files give them. On the Combined view the chart uses the mean of the benches' calibration errors: the mean over the benches in Combined (Reading · Turkish, Logic &amp; Math, Backgammon) that give the model one, so a model without one on a bench gets the mean of the other two; a model with fewer than two is left out of that chart.</p>
      <h2 id="latency">Latency</h2>
      <p>One pinned machine for every model: {esc(PINNED)}, one request at a time, Reading · Turkish requests (the Text tab's runs); the median and the 95th percentile (nearest rank) of the time per request, in milliseconds. A run's machine is read from the host its requests went to, not from the hardware text. Models timed elsewhere, on another machine or through an API, read "{NOT_TIMED}".</p>
      <h2 id="filters">Type and size</h2>
      <p>The type keys (All · Chat models · Decision models; Decision models when the page opens) and the class keys (All and the Reading site's Leaderboard's classes, the ones no model here falls in left out) choose the models in view, the two combined: the chart, the table under it, Head to head's choices, Full results and the charts follow them. A second tap on a pressed key goes back to All, as on the three sites. The address keeps the choice: ?models=all or chat (the Reading site's form) and ?class= a class. {esc(leaderboard.class_line(site, []))} A model of this site is classed as on the Leaderboard (Site.model_class); a model only on the other sites' benches by its file's params_total, else Undisclosed, as the files give no list price.</p>
      <h2 id="size">Size</h2>
      <p>Total parameters (and the active count for a mixture of experts) as the bench files give them, in billions; "not disclosed" where the maker states none. The table's size is the Leaderboard's: the total only, MoE after a mixture of experts, 2× after two models run together, empty where undisclosed.</p>
      <h2 id="join">One model across benches</h2>
      <p>Two rows are one model (the three sites' rule) when both have a Hugging Face repo and the repos match (in any case, without a commit, and without the org where one side gives none); else, unless both have repos that differ, when their model_key match: the three sites' join key, the model's name without its setting or route, lower case, hyphens for spaces, "-with-web" for a setup with web search, which never joins the plain one; a Reading model_key the three sites' shared names table maps to another (its row's source_model_key: Reading's qwen-3.5-397b-a17b is qwen3.5-397b-a17b) joins as that one. A repo on one side never keeps rows apart, and the route never splits a model (Ümit #4270). Else, for a row another site names differently, by the model_key a fixed list gives its name (the alias list, page_config.json all_benches.aliases: Backgammon's "Decider v1.2 27B" is Perplexity Decider 27B v1.2, its "Mercury Decide" is Mercury Decide, and so on); else, for a row without model_key, by the name in lower case without the maker's name, setting and route words, in any word order ("Decider v1.2 27B" meets "Perplexity Decider 27B v1.2" with the tag "API"). A row never joins a model already on its bench. The model shows the name of this site's row, else Logic &amp; Math's. Where the benches ran different setups of one model (our hardware's checkpoint and a hosted API, or two checkpoints), the table under the chart says which bench ran which, and so does the model's page. Each bench's commit is on the model's page: the benches may have run different commits of one repo.</p>
      <h2 id="their-score">Their score</h2>
      <p>{esc(data.their["name"])} {esc(data.their["edition"])}, "{esc(data.their["measure"])}", as of {bp.long_date(data.their["date"])} (<a href="{esc(data.their["source"])}">source</a>), for its 15 open decision models: a sanity check beside ours, never shown as our score. {esc(data.their["reference"]["name"])} is a reference bar: {esc(data.their["reference"]["note"])}.</p>
      <h2 id="colours">Colours, marks and tags</h2>
      <p>Each bar and dot takes its maker's colour from maker_colours.json, the one colour map of the three sites, with the maker's mark before the model's name in the ranking (a plain shape where the maker's mark is not freely licensed). Makers without a colour there yet read grey: {esc(", ".join(missing)) if missing else "none"}. Every model shows by its maker's official name. Beside it, a small tag says how the setup ran where its bench's file gives one (the file's tag field: setting · route · snapshot, as "API · with web" or "high · chat"); two rows of one model differ only by their tag, and rows join by the rule above, never by their names. Then a second small tag, the training method, where our setup records state it (fine-tune, post-trained, LoRA, blend …); blank where they do not.</p>
      <h2 id="sources">Sources</h2>
      <ul>{sources}</ul>
      <p class="note">The build reads the other sites' files from these addresses and keeps what it read in <a href="{rel(METHOD, SNAPSHOT_COPY)}">benches.json</a>.</p>
    </section>"""
    return frame(data, METHOD, f"{TITLE}: Methodology", f"How {TITLE} scores, combines and compares the benches of the three sites and Grading.",
                 body, image)


def redirect(site: Site, old: str, new: str) -> str:
    """A page's earlier address in the Reading site: sends the reader to its address under /analysis/all-benches/ with
    the query (?model=) and the fragment, as v2/ does (the meta refresh alone drops both)."""
    target = suite_path(site) + new
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moved: {TITLE} · {BRAND}</title>
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


# ------------------------------------------------------------------------------------------------------- link preview


def share_page(data: Data, theme: str) -> str:
    """The link preview's HTML, in the Reading site's sharing image layout (build_page's figure_page and RANKING_STYLE,
    as its ranking_image): the bp.IMAGE_TOP decision models (the type the page opens with) with the highest score in the
    view the page opens with, highest first, each bar from 0 to 100 in its maker's colour, as on the page, with its
    score: 0 to 100, chance = 0, never a percentage."""
    view = data.default_view()
    label = data.view_label(view)
    ranked = data.ranked(view, DEFAULT_TYPE)
    marks = "".join(f'<span class="name">{esc(plain_name(model))}</span><span class="lane"><span class="bar" style="width: '
                    f'{max(0.0, min(100.0, data.score(model, view))):.2f}%; background: {model["colour"]}"></span></span>'
                    f'<span class="val">{number(data.score(model, view))}</span>' for model in ranked[:bp.IMAGE_TOP])
    fulls = [full for _, _, full in group_names(data)]
    what = (f"Combined: the mean of {GROUPS}, {', '.join(fulls[:-1])} and {fulls[-1]}" if view == "combined"
            else data.by_key[view]["label"])
    body = (f"<h1>{TITLE}: the {min(bp.IMAGE_TOP, len(ranked))} highest {esc(label)} scores</h1>"
            f'<p class="sub">{dict(KINDS)[DEFAULT_TYPE]} · {UNIT}, 100 = perfect · {esc(what)}.</p>'
            f'<div class="chart">{marks}</div><p class="more">Every model on all {len(data.benches)} benches: the {TITLE} '
            f"page.</p><p class=\"foot\">Reading · Turkish, English and Vision: {data.site.version()} · "
            f'{esc(data.site.config["all_benches"]["url"].removeprefix("https://").rstrip("/"))}</p>')
    return bp.figure_page(data.site.config["images"]["preview"], {"pad": 40, "title": 40, "sub": 23, "foot": 19}, body,
                          theme, bp.RANKING_STYLE)


def share_images(data: Data) -> dict[str, str]:
    """The link preview in both themes (bp.THEMES), the dark one in the pages' tags as on the Reading site, by theme:
    drawn by headless Chrome (bp.screenshot) at every build, the fast one too, as the scores come from the benches' files
    read at each build; saved in OUT's SHARE as preview-<theme>-<hash>.png, the hash the start of its SHA-256, so a
    changed image gets an address no link preview has cached. The publishing step copies it with the folder to the
    mirror's analysis/all-benches/share/. Earlier images there go until page_config.json's "announced" holds a date,
    as the Reading site's (bp.remove_old_images)."""
    folder = ROOT / OUT / SHARE
    folder.mkdir(parents=True, exist_ok=True)
    size = data.site.config["images"]["preview"]
    names = {}
    with tempfile.TemporaryDirectory() as work:
        for theme in bp.THEMES:
            png = bp.screenshot(share_page(data, theme), size, Path(work), f"all-benches-{theme}")
            name = f"{SHARE}preview-{theme}-{hashlib.sha256(png).hexdigest()[:8]}.png"
            (ROOT / OUT / name).write_bytes(png)
            os.chmod(ROOT / OUT / name, 0o644)
            names[theme] = name
            print(f"Wrote {OUT}{name} ({size['width']}x{size['height']})")
    if not data.site.config.get("announced"):
        for old in folder.glob("preview-*.png"):
            if SHARE + old.name not in names.values():
                old.unlink()
    return names


def build(site: Site) -> dict[str, str]:
    """The two pages with their link preview (share_images) and the snapshot's copy in OUT with the files they use
    (ASSETS); the snapshot in the repo; the redirects at the earlier addresses."""
    data = Data(site)
    if data.missing_colours:
        print(f"all-benches: makers without a colour in maker_colours.json: {', '.join(sorted(data.missing_colours))}")
    image = share_images(data)["dark"]
    grading = grading_page(data, image)
    return {OUT + PATH: page(data, image), OUT + METHOD: method_page(data, image), OUT + SNAPSHOT_COPY: data.snapshot,
            SNAPSHOT: data.snapshot, **{OUT + name: (ROOT / name).read_text(encoding="utf-8") for name in ASSETS},
            OLD_PATH: redirect(site, OLD_PATH, PATH), OLD_METHOD: redirect(site, OLD_METHOD, METHOD),
            **({GRADING_OUT: grading, **{GRADING_OUT + name: (ROOT / name).read_text(encoding="utf-8") for name in ASSETS}}
               if grading else {})}
