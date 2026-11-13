"""The Leaderboard (the home page's table, #leaderboard), as on the Backgammon site: one row per model at its highest
reasoning setting, a fixed rule and never the best score, with each row's other setups behind an expander and every
value of a row and of its details box from its one setup. Five parts, one table each, switched above the table
(site.js; Ümit #4181): Turkish, the 2,198-question ranking (results.json runs); Turkish reading and Turkish grammar, the
same rows ranked on their reading or grammar questions; English reading, the English setups on the kept reading
questions (english_reading.models, each with its Text tab run's settings, and the English-only setups,
english_reading.english_only, with no Text tab run); Both, Turkish and English accuracy on those same questions, as
turkish-vs-english/ computes them (paired setups only). A row is a model ID, its kind (chat or decision model) and web
search (a setup with web is its own row); a dated checkpoint joins its original's row only through page_config.json's
leaderboard.dated_checkpoints. Two key rows filter the rows (site.js): the type (All · Chat models · Decision models) and
the class (Class: All · Tiny · Small · Medium · Large · Efficient · Workhorse · Flagship, Site.model_class; Ümit #4217,
one scale with the Logic & Math site), combined; a class key with no row in the view hides. Each row carries its kind,
its class and its score; on the Turkish part also its tie-group letters (results.json runs' group), so its Tier column
shows each row's tier among the rows in view (tiers()); the other parts, which no all-pairs test covers, have a Rank
column, the rows' places 1, 2, 3 without repeats (places(); Zeki #4629, #4630). A setup with web search (its tag says
"with web") is in no tier and no rank: its first cell shows a dash. A row names its
model by its official name with the chosen setup's tag beside it (Site.title, Site.tag; sitebuild/names.py) and its
class label after them (Site.label: "Open · 27B", "Closed · Efficient")."""

from __future__ import annotations

from typing import Any

import benchmark_metrics as bm
import build_page as bp
from sitebuild import holding_back as hold
from sitebuild.english_reading import (BASIS_WORDS, english_only, entry_href, idk_key, setup_families, setup_run, under_way)
from sitebuild.names import base_model, tag_html
from sitebuild.site import (NO_ANSWERS, NOT_MEASURED, NOT_MEASURED_CONFIDENCE, Site, cost_missing, cost_per, cost_value, esc,
                            family_icon, latency_text, measure_keys, parameters_text, pct, plain_line, rel, request_size,
                            size_sentence, stated_total)

# The reasoning settings in order, as the requests sent them: none and off (and a setup without a setting, or a chat
# template's default, vllm-plain's "default") lowest; "on" is the setting of a model with thinking on or off only, above
# off; a model with "on" and a level fails the build.
LEVELS = {None: 0, "none": 0, "off": 0, "default": 0, "on": 1, "minimal": 2, "low": 3, "medium": 4, "high": 5, "xhigh": 6,
          "max": 7}
# The full row rule, on the About page; the table's own line is ROW_LINE.
RULE = ("Row rule: each model's highest reasoning setting (none, off or the chat template's default < minimal < low < "
        "medium < high < xhigh < max; "
        "on above off for a model with only on and off); a decision model has no setting. Tie-break: several setups at "
        "that setting give the row to the earliest run (the lowest run id), never to the higher score. A model with one "
        "setup uses it. Every value of a row and of its details box comes from that one chosen setup; its other setups "
        "are under the row's expander and under All setups. A setup with web search is its own row; different version "
        "names are separate rows; a dated checkpoint joins another model's row only through the map below, never by a "
        "similar name.")
ROW_LINE = "One row per model at its highest reasoning setting, never its best score; tap or point at a row for its details."
# The parts (Ümit #4181): Turkish, all 2,198 questions (the default, and the only part with the all-pairs test, so the
# only one with tiers); Turkish reading and Turkish grammar, the same rows ranked on their reading or grammar questions;
# English reading, the 547 kept reading questions in English; Both, Turkish and English on those 547.
PARTS = (("turkish", "Turkish"), ("turkish-reading", "Turkish reading"), ("turkish-grammar", "Turkish grammar"),
         ("english", "English reading"), ("both", "Both"))
DEFAULT_PART = "turkish"
# The type keys and the class keys (page_config.json model_classes, Site.model_classes; Ümit #4217): one of each
# pressed, All when none; the old addresses ?models=small-chat, small-decision and small press Tiny and Small together
# (site.js), the nearest view to the old small ones (the classes read the total, the old views also the active count).
TYPES = (("all", "All"), ("chat", "Chat models"), ("decision", "Decision models"))
DEFAULT_TYPE = "decision"
TYPE_LABEL = {True: "decision model", False: "chat model"}
# The Turkish runs' option "Bilmiyorum", named by its meaning in the board's labels ('with “I don't know”', the project
# lead via Zeki #4606); the prompts, the data and the Hallucination tab's comparison of the two option words keep it.
OPTION_SHOWN = {"Bilmiyorum": "I don't know"}
# The first column's line under each part's table: the Turkish part's tiers (head "Tier"), the other parts' ranks (head
# "Rank"; the project lead via Zeki #4629, #4630: a column says which it is, and a rank runs 1, 2, 3 without repeats).
TIER_LINE = ("Tier: ranked by accuracy among the rows in view, a row joins the tier of the tier's top row when the "
             "all-pairs test behind the Accuracy section's letters ({pairs} pairs, exact McNemar, Holm-corrected, 5%) found "
             "no difference between them, else it starts the next tier; a line separates tiers. Rows in one tier need not be "
             "equal. A setup with web search is in no tier (Tier: –).")
RANK_LINE = ("Rank: the row's place among the rows in view, by accuracy, 1, 2, 3 without repeats; rows with the same score "
             "keep the table's order, which claims no difference between them. No all-pairs test covers the {part} part, "
             "so it has no tiers. A setup with web search is not ranked (Rank: –).")
EMPTY_LINE = "No row of this part matches these keys. The small open chat models ran in English only."


def level(setting: str | None) -> int:
    if setting not in LEVELS:
        raise SystemExit(f"leaderboard: unknown reasoning setting {setting!r}")
    return LEVELS[setting]


def choose(setups: list[dict[str, Any]], run_of: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A row's setup by the fixed rule (RULE) and its other setups, highest setting first, then by run id."""
    settings = {run_of(item).get("reasoning") for item in setups}
    if "on" in settings and any(level(setting) > 1 for setting in settings):
        raise SystemExit(f"leaderboard: {run_of(setups[0])['model']} has 'on' and a reasoning level")
    order = sorted(setups, key=lambda item: (-level(run_of(item).get("reasoning")), run_of(item)["run"]))
    return order[0], order[1:]


class Board:
    """The rows of the three parts."""

    def __init__(self, site: Site) -> None:
        self.site = site
        self.checkpoints: dict[str, str] = site.config["leaderboard"]["dated_checkpoints"]
        self.english = site.results["english_reading"]
        self.total = site.results["questions"]
        self.kept = self.english["questions"]
        self.option = OPTION_SHOWN.get(site.results["dont_know"]["option"], site.results["dont_know"]["option"])
        self.english_option = self.english["dont_know"]["option"]
        self.rated = {model["original_run"]: model for model in site.results["dont_know"]["models"]}
        idk = self.english["dont_know"]
        self.english_rated = {idk_key(model): model["english"] for model in [*idk["models"], *english_only(idk)]}
        # Setups whose runs with the option are not in yet read Queued or Running for that side (Zeki #4748).
        self.under_way: dict[str, dict[str, str]] = site.config["dont_know"]["under_way"]["models"]
        self.check_under_way()

    def check_under_way(self) -> None:
        """Stops the build on an entry of page_config.json's dont_know.under_way that does not fit: a model the site does
        not show, a side other than english or turkish, a state other than queued or running, or a side whose run with
        the option is in (its Text tab run on the Hallucination tab, its English reading entry in the English
        comparison): that side then comes off the list."""
        entries = [*self.english["models"], *english_only(self.english)]
        for model, sides in sorted(self.under_way.items()):
            label = f"page_config.json dont_know.under_way: {model}"
            texts = [run for run in self.site.runs if run["model"] == model]
            english = [entry for entry in entries if entry["model"] == model]
            if not texts and not english:
                raise SystemExit(f"{label} is not on the site")
            if not set(sides) <= {"english", "turkish"} or not set(sides.values()) <= {"queued", "running"}:
                raise SystemExit(f"{label}: its sides are english or turkish, each queued or running (found {sides})")
            if "turkish" in sides and any(run["run"] in self.rated for run in texts):
                raise SystemExit(f"{label}: its Turkish run with the option is in; take turkish off")
            if "english" in sides and any(entry.get("turkish_run", entry["run"]) in self.english_rated for entry in english):
                raise SystemExit(f"{label}: its English run with the option is in; take english off")

    def pending(self, model: str, side: str) -> str | None:
        """A side's state while its run with the option is not in (dont_know.under_way): queued, running or None."""
        return under_way(self.site, model, side)

    def key(self, run: dict[str, Any]) -> tuple[str, bool, bool]:
        return self.checkpoints.get(run["model"], run["model"]), self.site.decision(run), run["perplexity_mode"] is not None

    def grouped(self, items: list[dict[str, Any]], run_of: Any) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        groups: dict[tuple[str, bool, bool], list[dict[str, Any]]] = {}
        for item in items:
            groups.setdefault(self.key(run_of(item)), []).append(item)
        return [choose(setups, run_of) for setups in groups.values()]

    def turkish_rows(self) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        return self.grouped(self.site.runs, lambda run: run)

    def english_rows(self, both: bool) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        """The English part's rows (the paired setups and the English-only ones) or, with both, the Both part's (the
        paired setups only)."""
        items = self.english["models"] + ([] if both else english_only(self.english))
        return self.grouped(items, lambda model: setup_run(self.site, model))


def accuracy(run: dict[str, Any]) -> tuple[int, int]:
    groups = run["groups"]
    return groups["reading"]["correct"] + groups["grammar"]["correct"], groups["reading"]["questions"] + groups["grammar"]["questions"]


def share(run: dict[str, Any], part: str) -> float:
    return run["groups"][part]["correct"] / run["groups"][part]["questions"]


def places(count: int) -> list[int]:
    """The Rank column of rows already in the table's order: 1, 2, 3 without repeats, rows with the same score keeping
    that order (the project lead via Zeki #4630: an ordinal display order, no tie-break claim)."""
    return list(range(1, count + 1))


def tiers(letters: list[str | None]) -> list[int]:
    """Each row's tier, the rows in rank order (Ümit #4156): the first row starts tier 1; a row joins the current tier
    when it shares a tie-group letter with that tier's top row (the all-pairs test found no difference between them,
    bp.shares_letter), else it starts the next tier and becomes its top row. site.js does the same for the rows in
    view."""
    out: list[int] = []
    top: str | None = None
    for group in letters:
        if out and bp.shares_letter(group, top):
            out.append(out[-1])
        else:
            top = group
            out.append(out[-1] + 1 if out else 1)
    return out




def under(site: Site, run: dict[str, Any]) -> str:
    """Beside the name and tag in the details box: maker · chat model / decision model (the tag says how it ran)."""
    return f"{setup_families(site)[run['run']]['maker']} · {TYPE_LABEL[site.decision(run)]}"


def bar(correct: int, total: int, colour: str, kind: str = "") -> str:
    """The main-score bar from 0 to 100% with its Wilson 95% interval as the whisker."""
    low, high = bm.wilson_interval(correct, total)
    return (f'<span class="lb-bar{kind}"><span class="lb-fill" style="width:{100 * correct / total:.2f}%;background:{colour}">'
            f'</span><span class="lb-whisker" style="left:{100 * low:.2f}%;width:{100 * (high - low):.2f}%"></span></span>')


def interval(correct: int, total: int) -> str:
    low, high = bm.wilson_interval(correct, total)
    return f"(95%: {100 * low:.1f}\u2013{pct(high)})"


def ci(correct: int, total: int) -> str:
    """The main score's Wilson 95% interval as a line under its value, as Logic & Math's table shows it (Zeki #4606):
    "56.4%–62.1%"; the whisker draws the same interval."""
    low, high = bm.wilson_interval(correct, total)
    return f'<span class="small lb-ci">{pct(low)}\u2013{pct(high)}</span>'


def cost_text(site: Site, run: dict[str, Any], value: float | None, basis: str | None, upper: bool) -> str:
    """The details box's cost line; a run without a cost says why, as its Cost cell does (cost_missing: No list price or
    Not measured), since below 900 px the box is where the cost shows (Zeki #4618)."""
    if value is None:
        return f"Cost: {cost_missing(run)}"
    mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if upper else ""
    words = f" ({esc(BASIS_WORDS[basis])})" if basis in BASIS_WORDS else ""
    return f"Cost {cost_value(value, mark)} {cost_per()}{words}"


def wide(value: str) -> str:
    return f'<td class="num lb-wide">{value}</td>'


def details(site: Site, run: dict[str, Any], box: str, lines: list[str | None], answers: str) -> str:
    """A setup's details box: its name line, the model its model is built on where the shared names table
    (model_names.json, names.base_model) gives one (there only, never in the name), its model's size (size_sentence, else
    parameters_text), its price line where it is classed by price (Site.price_note), then the lines the data has (never
    "n/a"), then the link to its answers (an English-only setup, with no Text tab run and no model page: its row on the
    English reading page)."""
    head = " · ".join([f"<strong>{site.shown(run)}</strong>", esc(under(site, run))])
    link = "Open its answers" if run["run"] in site.by_id else "Open its English results"
    size = size_sentence(run) or f"Parameters: {parameters_text(run)}"
    base = base_model(run)
    body = [head, f"Base model: {esc(base)}" if base else "", esc(size), esc(site.price_note(run) or ""), *lines,
            f'<a href="{answers}">{link} \u2192</a>']
    return (f'<div class="lb-box" id="{box}" role="group" aria-label="{esc(site.plain(run))}: details">'
            + "".join(f"<p>{line}</p>" for line in body if line) + "</div>")


def held_head(option: str) -> str:
    """The Non-hallucination column's head, with what it is in one phrase, as Logic & Math's (bus #4685)."""
    return f'Non-hallucination<span class="small">of answers not right, % \u201c{esc(option)}\u201d \u00b7 higher is better</span>'


def held_cell(counts: dict[str, Any] | None, digits: int, pending: str | None = None) -> str:
    """The Non-hallucination cell (Ümit #4665): the rate with, as a small second line as the score's interval, the share
    answered, as Logic & Math's ("answered 98%"); without a run with the option, Queued or Running while that run is
    not in (page_config.json's dont_know.under_way; Zeki #4748), else Not run; No rate where the rate is undefined."""
    if counts is None:
        return f'<span class="nm">{pending.capitalize() if pending else "Not run"}</span>'
    rate = '<span class="nm">No rate</span>' if counts["non_hallucination"] is None else pct(counts["non_hallucination"], digits)
    return f'{rate}<span class="small lb-ci">answered {pct(counts["attempt_rate"], 0)}</span>'


def held_line(option: str, counts: dict[str, Any] | None, digits: int, pending: str | None = None) -> str | None:
    """The details box's line on the run with the option: the non-hallucination rate, the share answered and the error
    rate among the answers together (Ümit #4665), in Logic & Math's words; Queued or Running while that run is not in;
    none without a run or a rate."""
    if counts is None and pending:
        return (f"Non-hallucination with \u201c{esc(option)}\u201d: {pending.capitalize()} (its run with the option "
                + ("is under way)" if pending == "running" else "has not started yet)"))
    if counts is None or counts["non_hallucination"] is None:
        return None
    error = hold.error_rate(counts)
    return (f"Non-hallucination with \u201c{esc(option)}\u201d {pct(counts['non_hallucination'], digits)} \u00b7 answered "
            f"{pct(counts['attempt_rate'], digits)}" + (f" \u00b7 error rate {pct(error, digits)}" if error is not None else ""))


def kept_line(sure: str, kept: dict[str, Any] | None, questions: int) -> str | None:
    """The details box's line on the answers kept at the threshold: none kept reads NO_ANSWERS, muted (Ümit #4665),
    never "no observed mistakes"."""
    if not kept:
        return None
    if not kept["questions"]:
        return f'Kept at {sure} confidence: <span class="nm">{NO_ANSWERS}</span>'
    if kept["correct"] == kept["questions"]:
        return f"Kept at {sure} confidence with no observed mistakes: {pct(kept['questions'] / questions)}"
    return (f"Kept at {sure} confidence: {pct(kept['questions'] / questions)}, {bp.count(kept['questions'] - kept['correct'])} "
            "of them wrong")


# With Accuracy pressed, a part's table shows every measure beside the accuracy, as Logic & Math's first table does
# (Ümit #6696, #6706 via Zeki #6718): Non-hallucination, Confidence, Cost and Latency, each from the row's one setup; their
# Measure keys still open their views. Below 900 px the columns stay too, the table scrolling inside its frame with the
# model column in place, and each row's latency and cost read under its name (glance_lines; v3.css, Zeki #6751, #6754).
CONFIDENCE_HEAD = 'Confidence<span class="small">calibration gap, points \u00b7 lower is better</span>'
BRIER_HEAD = 'Confidence<span class="small">chosen-answer Brier \u00b7 lower is better</span>'
LATENCY_HEAD = 'Latency<span class="small">median seconds per request \u00b7 lower is better</span>'


def confidence_cell(run: dict[str, Any]) -> str:
    """A Text tab run's Confidence cell: its calibration gap (runs[].confidence.ece, the gap the Confidence view's chart
    shows) in points, one decimal, with its confidence's source under it; Not measured without one (a setup asked for a
    plain answer line gives none)."""
    found = run.get("confidence")
    if not found:
        return NOT_MEASURED_CONFIDENCE if plain_line(run) else NOT_MEASURED
    return f'{100 * found["ece"]:.1f}<span class="small">{esc(found["label"].lower())}</span>'


def confidence_line(run: dict[str, Any]) -> str | None:
    """The details box's line on a Text tab run's confidence: its calibration gap and source, or not measured."""
    found = run.get("confidence")
    if found:
        return f"Confidence: calibration gap {100 * found['ece']:.1f} points ({esc(found['label'].lower())})"
    return "Confidence: not measured" if plain_line(run) else None


def brier_cell(model: dict[str, Any]) -> str:
    """An English setup's Confidence cell: the chosen-answer Brier of its first English run with its Decision Score (AA
    formula) under it (english_reading.models[].decision_score, decision models only); Unavailable with the reason in
    its title; Not measured for a chat model, whose confidence is not measured in English (a plain answer line has none)."""
    if "decision_score" in model:
        found = model["decision_score"]
        return f'{found["brier"]:.4f}<span class="small">Decision Score {found["score"]:.2f}</span>'
    if "decision_score_unavailable" in model:
        return f'<span class="nm" title="{esc(model["decision_score_unavailable"])}">Unavailable</span>'
    return NOT_MEASURED_CONFIDENCE if plain_line(model) else NOT_MEASURED


def latency_cell(entry: dict[str, Any] | None, size: int | None) -> str:
    """A Latency cell: the median seconds per request, under it the questions per request and the requests in flight,
    each a short line of its own that never breaks (lb-keep), so the column stays narrow (a run's latency, or an English
    setup's first English run's; the details box says it in words), said where it was measured on a sample or on the
    run's repeats; Not measured without a timing."""
    if not entry:
        return NOT_MEASURED
    where = {"sample": "on a sample", "repeats": "on its repeats"}.get(entry.get("source") or "")
    lines = [f"{bp.count(size)} per request" if size else None, f'{bp.count(entry["concurrency"])} in flight', where]
    return bp.seconds(entry["median_request_seconds"]) + "".join(
        f'<span class="small lb-keep">{esc(line)}</span>' for line in lines if line)


def latency_line(entry: dict[str, Any] | None) -> str | None:
    """The details box's line on a latency: the median per request and the requests in flight."""
    if not entry:
        return None
    return (f"Latency: {latency_text(entry['median_request_seconds'])} median per request, "
            f"{bp.count(entry['concurrency'])} in flight")


def glance_lines(glance: list[str | None]) -> str:
    """A row's glance lines under its name (HTML, its latency and its cost), shown below 900 px only (v3.css .lb-glance),
    where the table's farther columns lie past the screen's edge until it scrolls (Zeki #6754)."""
    return "".join(f'<span class="lb-glance">{line}</span>' for line in glance if line)


def turkish(site: Site, board: Board, group: str | None = None) -> tuple[list[str], list[str], int]:
    """The Turkish part (group None: all questions, ranked in tiers) or the Turkish reading or Turkish grammar part
    (group "reading" or "grammar": the same rows, ranked on that group's questions, with its accuracy and 95% interval;
    no all-pairs test covers them, so the first column is Rank; Ümit #4181): the head cells, the body rows and the number of model
    rows."""
    total, digits = board.total, site.config["percent_digits"]
    sure = pct(site.config["threshold"], 0)
    other = {"reading": "grammar", "grammar": "reading"}.get(group or "")

    def counts(run: dict[str, Any]) -> tuple[int, int]:
        return accuracy(run) if group is None else (run["groups"][group]["correct"], run["groups"][group]["questions"])

    def facts(run: dict[str, Any]) -> tuple[list[str | None], list[str], list[str | None]]:
        correct, questions = accuracy(run)
        model = board.rated.get(run["run"])
        pending = board.pending(run["model"], "turkish")
        kept = (run.get("confidence") or {}).get("sure") if site.decision(run) else None
        value = bp.per_thousand(run)
        lines = [
            (f"Turkish {group} {pct(counts(run)[0] / counts(run)[1])} {interval(*counts(run))}" if group else None),
            f"Accuracy {pct(correct / questions)} {interval(correct, questions)}",
            f"Reading {pct(share(run, 'reading'))} · grammar {pct(share(run, 'grammar'))}",
            turkish_line(site, run),
            held_line(board.option, model, digits, pending),
            kept_line(sure, kept, questions),
            confidence_line(run),
            " · ".join(filter(None, (cost_text(site, run, value, run.get("cost_basis"), bool(run.get("cost_upper_bound"))),
                                     bp.count(run["questions_per_request"]) + " question"
                                     + ("" if run["questions_per_request"] == 1 else "s") + " per request"))),
            latency_line(run.get("latency")),
        ]
        mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if run.get("cost_upper_bound") else ""
        cost = (cost_missing(run) if value is None else
                f'{cost_value(value, mark)}<span class="small">{esc(BASIS_WORDS[run["cost_basis"]])}</span>')
        cells = ([pct(share(run, "reading")), pct(share(run, "grammar"))] if group is None else
                 [pct(correct / questions), pct(share(run, other))]) + [
            held_cell(model, digits, pending), confidence_cell(run), cost,
            latency_cell(run.get("latency"), run["questions_per_request"])]
        # Below 900 px, under the name: its latency and its cost at a glance (Zeki #6754); the columns hold them too.
        latency = run.get("latency")
        spent = cost_missing(run) if value is None else f"{cost_value(value, mark)} {cost_per('per 1,000', 'per 1M')}"
        glance = [f"Latency {latency_text(latency['median_request_seconds'])}" if latency else None, f"Cost {spent}"]
        return lines, cells, glance

    def score(run: dict[str, Any]) -> tuple[str, int]:
        correct, questions = counts(run)
        colour = site.families[run["run"]]["colour"]
        return f'{bar(correct, questions, colour)}<span class="lb-value">{pct(correct / questions)}{ci(correct, questions)}</span>', correct

    rows = board.turkish_rows()
    heads = (["Reading", "Grammar"] if group is None else ["Turkish<span class=\"small\">all questions</span>", other.capitalize()])
    heads += [held_head(board.option), CONFIDENCE_HEAD, f"Cost<span class=\"small\">{cost_per()}</span>", LATENCY_HEAD]
    questions = total if group is None else counts(rows[0][0])[1]
    title = "Accuracy" if group is None else f"Accuracy on {group}"
    body = table_rows(site, board, "tr" if group is None else f"tr{group[0]}", rows, lambda run: run, facts, score,
                      lambda run: site.model_path(run), group is None, turkish=True)
    return [f"{title}<span class=\"small\">{bp.count(questions)} questions, 95% interval</span>", *heads], body, len(rows)


def english(site: Site, board: Board, both: bool) -> tuple[list[str], list[str]]:
    """The English part (both False) or the Both part: the head cells and the body rows."""
    kept, digits = board.kept, site.config["percent_digits"]
    run_of = lambda model: setup_run(site, model)  # noqa: E731

    def facts(model: dict[str, Any]) -> tuple[list[str | None], list[str], list[str | None]]:
        en, tr = model["english"], model.get("turkish")
        held = board.english_rated.get(model.get("turkish_run", model["run"]))
        pending = board.pending(model["model"], "english")
        cost = model["cost"]["english"]
        value = cost["per_1000"] if cost else None
        size = (model["latency"].get("english") or {}).get("questions_per_request")
        lines = ([f"Turkish {pct(tr['accuracy'])} {interval(tr['right'], kept)} · English {pct(en['accuracy'])} "
                  f"{interval(en['right'], kept)}, on the same {bp.count(kept)} kept reading questions",
                  f"English minus Turkish: {100 * model['difference']:+.1f} points"] if both else
                 [f"Accuracy in English {pct(en['accuracy'])} {interval(en['right'], kept)}, {bp.count(kept)} kept reading questions",
                  held_line(board.english_option, held, digits, pending),
                  " · ".join(filter(None, (cost_text(site, run_of(model), value, cost["basis"] if cost else None,
                                                     bool(cost and cost.get("upper_bound"))),
                                           f"{bp.count(size)} question{'' if size == 1 else 's'} per request" if size else None))),
                  # An English-only setup (no Text tab run, no model page): said so, with how it was called.
                  *(["English only: no Text tab run, so not in the Turkish and Both parts",
                     f"How we called it: {esc(model['access'])}"]
                    if tr is None else []),
                  "Confidence: not measured" if plain_line(model) else None,
                  (f"Confidence: chosen-answer Brier {model['decision_score']['brier']:.4f}, Decision Score (AA formula) "
                   f"{model['decision_score']['score']:.2f}" if "decision_score" in model else None),
                  latency_line(model["latency"].get("english"))])
        if both:
            cells = [pct(tr["accuracy"]), pct(en["accuracy"]), f"{100 * model['difference']:+.1f}"]
            glance: list[str | None] = []
        else:
            hall = held_cell(held, digits, pending)
            mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if cost and cost.get("upper_bound") else ""
            money = (cost_missing(run_of(model)) if value is None else
                     f'{cost_value(value, mark)}<span class="small">{esc(BASIS_WORDS[cost["basis"]])}</span>')
            cells = [hall, brier_cell(model), money, latency_cell(model["latency"].get("english"), size)]
            timing = model["latency"].get("english")
            spent = (cost_missing(run_of(model)) if value is None else
                     f"{cost_value(value, mark)} {cost_per('per 1,000', 'per 1M')}")
            glance = [f"Latency {latency_text(timing['median_request_seconds'])}" if timing else None, f"Cost {spent}"]
        return lines, cells, glance

    def score(model: dict[str, Any]) -> tuple[str, int]:
        colour = setup_families(site)[run_of(model)["run"]]["colour"]
        en, tr = model["english"], model.get("turkish")
        if both:
            return (f'{bar(tr["right"], kept, colour)}{bar(en["right"], kept, colour, " lb-en")}'
                    f'<span class="lb-value">{pct(tr["accuracy"])}<span class="small">{pct(en["accuracy"])}</span></span>',
                    tr["right"])
        return f'{bar(en["right"], kept, colour)}<span class="lb-value">{pct(en["accuracy"])}{ci(en["right"], kept)}</span>', en["right"]

    rows = board.english_rows(both)
    if both:
        heads = [f"Turkish · English<span class=\"small\">{bp.count(kept)} questions, 95% intervals</span>", "Turkish",
                 "English", "Difference<span class=\"small\">points, English minus Turkish</span>"]
    else:
        heads = [f"Accuracy in English<span class=\"small\">{bp.count(kept)} questions, 95% interval</span>",
                 held_head(board.english_option), BRIER_HEAD, f"Cost<span class=\"small\">{cost_per()}</span>", LATENCY_HEAD]
    body = table_rows(site, board, "bo" if both else "en", rows, run_of, facts, score,
                      lambda model: entry_href(site, "", model), False)
    return heads, body


# Ümit's #5067 item 3 (confirmed by Zeki #5085): on the Turkish leaderboards a model whose own card or maker docs do not
# list Turkish carries this mark beside its name, with the words in its details box and the legend under the table.
TR_MARK = "\u2021"
TR_NOT_SUPPORTED = "Turkish not officially supported"


def turkish_listed(site: Site, run: dict[str, Any]) -> bool:
    """Whether the setup's model's own card or maker docs list Turkish (Site.turkish_support)."""
    return site.turkish_support[(run["provider"], run["model"])]["status"] == "listed"


def turkish_line(site: Site, run: dict[str, Any]) -> str:
    """The details box line on Turkish support: listed, or the mark's words and why, with the source."""
    item = site.turkish_support[(run["provider"], run["model"])]
    source = f'<a href="{esc(item["source"])}">source</a>, read {esc(bp.long_date(item["read"]))}'
    if item["status"] == "listed":
        return f"Turkish: listed in its card ({source})"
    why = "it lists other languages" if item["status"] == "not listed" else "it names no language"
    return f"{TR_MARK} {TR_NOT_SUPPORTED}: {why} ({source})"


def name_cell(site: Site, href: str, box: str, run: dict[str, Any], turkish: bool = False) -> str:
    """A row's name link (the model's official name, Site.title), its tag beside it (Site.tag: how the setup ran, a
    space before it), on the Turkish parts the mark TR_MARK where its card does not list Turkish, then a space (so
    copied text and screen readers never run the two together, #4269) and its class label (Site.label)."""
    mark = (f'<span class="lb-tr-mark" title="{TR_NOT_SUPPORTED}" aria-label="{TR_NOT_SUPPORTED}">{TR_MARK}</span>'
            if turkish and not turkish_listed(site, run) else "")
    return (f'<a class="model-name" href="{href}" title="{esc(site.plain(run))}" aria-describedby="{box}">'
            f'{esc(site.title(run))}</a>{tag_html(site.tag(run))}{mark} {site.label(run, box)}')


def table_rows(site: Site, board: Board, prefix: str, rows: list[tuple[dict[str, Any], list[dict[str, Any]]]], run_of: Any,
               facts: Any, score: Any, answers: Any, tested: bool, turkish: bool = False) -> list[str]:
    """The body rows of one part: each model row (Tier or Rank cell, maker dot and icon, name with its label and its
    expander,
    the score, the wide cells; its details box in the name cell, the only place its maker and kind show: project lead,
    bus #3039), then its other setups' rows, hidden, each with its own tag beside its name, the one thing that tells it
    apart. Each model row carries its kind, class (data-class) and score (data-score), and with tested
    (the Turkish part) its tie-group letters (data-letters), from which site.js numbers the rows in view; the first cell
    holds the tier (tested) or the place 1, 2, 3 among every row (places()), as the table shows without JavaScript. A
    setup with web search (data-unranked) is numbered in neither: its first cell holds a dash (Ümit #4217)."""
    scored = [(item, others, *score(item)) for item, others in rows]
    scored.sort(key=lambda entry: (-entry[3], run_of(entry[0])["run"]))
    unranked = [run_of(item)["perplexity_mode"] is not None for item, *_ in scored]
    counted = [index for index, flag in enumerate(unranked) if not flag]
    letters = [run_of(item)["group"] for item, *_ in scored] if tested else []
    numbered = (tiers([letters[index] for index in counted]) if tested
                else places(len(counted)))
    numbers: list[int | None] = [None] * len(scored)
    for index, number in zip(counted, numbered):
        numbers[index] = number
    previous: int | None = None
    out = []
    for index, (item, others, cell, points) in enumerate(scored):
        run = run_of(item)
        family = setup_families(site)[run["run"]]
        kind = "decision" if site.decision(run) else "chat"
        row_id = f"lb-{prefix}-{index + 1}"
        box = f"{row_id}-box"
        lines, cells, glance = facts(item)
        checkpoints = sorted({run_of(other)["model"] for other in others if run_of(other)["model"] != run["model"]})
        if checkpoints:
            lines.append("With its dated checkpoint " + ", ".join(esc(model) for model in checkpoints)
                         + " under its other settings")
        sub_ids = [f"{row_id}-{number}" for number in range(1, len(others) + 1)]
        more = (f'<button type="button" class="lb-more needs-js" aria-expanded="false" aria-controls="{" ".join(sub_ids)}">'
                f'{len(others)} other setting{"s" if len(others) > 1 else ""}</button>' if others else "")
        tested_attributes = f' data-letters="{letters[index]}"' if tested else ""
        if unranked[index]:
            tested_attributes += " data-unranked"
        elif tested and previous is not None and numbers[index] != previous:
            tested_attributes += ' class="lb-tier-start"'
        if not unranked[index]:
            previous = numbers[index]
        out.append(
            f'<tr data-kind="{kind}"{site.class_attribute(run)} data-score="{points}"{tested_attributes} data-box="{box}">'
            f'<td class="num rank">{"–" if unranked[index] else numbers[index]}</td><td class="model">'
            f'<i class="lb-dot" style="background:{family["colour"]}" title="{esc(family["maker"])}"></i>{family_icon(family["name"])}'
            f'{name_cell(site, answers(item), box, run, turkish)}{glance_lines(glance)}{more}'
            f'{details(site, run, box, lines, answers(item))}</td><td class="lb-score">{cell}</td>'
            + "".join(wide(value) for value in cells) + "</tr>")
        for sub_id, other in zip(sub_ids, others):
            other_run = run_of(other)
            other_lines, other_cells, other_glance = facts(other)
            other_box = f"{sub_id}-box"
            out.append(
                f'<tr class="lb-sub" id="{sub_id}" hidden data-kind="{kind}"{site.class_attribute(other_run)} '
                f'data-box="{other_box}"><td class="num"></td>'
                f'<td class="model">{name_cell(site, answers(other), other_box, other_run, turkish)}<span class="small">'
                f'other setting of {esc(site.title(run))}</span>{glance_lines(other_glance)}'
                f'{details(site, other_run, other_box, other_lines, answers(other))}</td>'
                f'<td class="lb-score">{score(other)[0]}</td>' + "".join(wide(value) for value in other_cells) + "</tr>")
    return out


def table(part: str, heads: list[str], body: list[str], caption: str) -> str:
    head = "".join(f'<th scope="col" class="num lb-wide">{text}</th>' for text in heads[1:])
    number = "Tier" if part == "turkish" else "Rank"
    return (f'<div class="table-wrap"><table class="lb-table" data-part="{part}"><caption class="visually-hidden">{esc(caption)}'
            f'</caption><thead><tr><th scope="col" class="num">{number}</th><th scope="col">Model</th>'
            f'<th scope="col" class="lb-score">{heads[0]}</th>{head}</tr></thead><tbody>{"".join(body)}'
            "</tbody></table></div>")


def meaning(part: str, total: int, kept: int, groups: dict[str, int]) -> str:
    """What the score means, the one line under each part's table (groups: the reading and grammar question counts)."""
    return {
        "turkish": f"Accuracy: the share of the {bp.count(total)} Turkish questions answered right, with its 95% interval "
                   "as the whisker; higher is better.",
        "turkish-reading": f"Accuracy on reading: the share of the {bp.count(groups['reading'])} Turkish reading questions "
                           "answered right, with its 95% interval as the whisker; higher is better.",
        "turkish-grammar": f"Accuracy on grammar: the share of the {bp.count(groups['grammar'])} Turkish grammar questions "
                           "answered right, with its 95% interval as the whisker; higher is better.",
        "english": f"Accuracy in English: the share of the {bp.count(kept)} kept reading questions, translated, answered "
                   "right, with its 95% interval as the whisker; higher is better.",
        "both": f"Turkish (solid) and English (striped) accuracy on the same {bp.count(kept)} kept reading questions, with "
                "95% intervals, ranked by Turkish, as on English and Turkish.",
    }[part]


def model_count(site: Site) -> int:
    """The number of models on the Turkish part: its rows."""
    return len(Board(site).turkish_rows())


def class_line(site: Site, runs: list[dict[str, Any]]) -> str:
    """The Class keys' rule, under the table while a class is chosen: the project lead's words (page_config.json
    model_classes.line, #4245), the provisional classes (#4238) and the setups only this site ran, in no class."""
    provisional = sorted({site.title(run) for run in runs if (site.list_price(run) or {}).get("provisional")
                          and not (site.is_open(run) and stated_total(run) is not None)}, key=str.casefold)
    left_out = sorted({site.title(run) for run in runs
                       if run["model"] in site.config["small_models"].get("left_out_models", [])}, key=str.casefold)
    undisclosed = any(site.model_class(run) == "undisclosed" for run in runs)
    return (site.config["model_classes"]["line"]
            + (" Undisclosed: models with neither a disclosed size nor a per-token list price." if undisclosed else "")
            + (f" Provisional: {bp.and_list(provisional)}, whose maker publishes only a promotional price." if provisional else "")
            + (f" Left out here: the setups only this site ran ({bp.and_list(left_out)}); they show under Class: All."
               if left_out else ""))

# The In progress table's states (page_config.json in_progress) and its columns, by side.
PROGRESS_STATES = {"queued": "Queued", "running": "Running", "blocked": "Blocked", "done": "Done", "none": "–"}
PROGRESS_SIDES = (("english", "English"), ("turkish", "Turkish"), ("page_images", "Page images"))


def in_progress(site: Site, board: Board) -> str:
    """The In progress table under the Leaderboard (the project lead via Zeki #5064, #5065, #5071; Ümit #5067): the
    models joining Reading, each with the state of its English, Turkish and Page images sides from page_config.json
    `in_progress` (queued, running, blocked, done, or none where a side does not apply, each with an optional note),
    so a model shows before its results do, never as a 0. A side is done exactly when the model (provider and model
    id) has a published run of it, a Page images side when vision.json holds every one of its cells (none missing; a
    model publishes each cell as it completes, Zeki #5177): the build stops otherwise (mark it done, or take the model off
    once every side is in). A model not set up yet (no model id) has no done side. Empty when no model is listed."""
    section = site.config.get("in_progress") or {}
    if not section.get("models"):
        return ""
    vision = site.vision["models"]
    published = {
        "turkish": {(run["provider"], run["model"]) for run in site.runs},
        "english": {(item["provider"], item["model"]) for item in [*board.english["models"], *english_only(board.english)]},
        "page_images": {(item["provider"], item["model"]) for item in (vision if isinstance(vision, list) else vision.values())
                        if not item.get("missing")},
    }
    rows = []
    for model in section["models"]:
        label = f"page_config.json in_progress: {model['name']}"
        cells = []
        for side, _ in PROGRESS_SIDES:
            entry = model[side] if isinstance(model[side], dict) else {"state": model[side]}
            state, note = entry["state"], entry.get("note")
            if state not in PROGRESS_STATES:
                raise SystemExit(f"{label}: its {side} state {state!r} is not one of {', '.join(PROGRESS_STATES)}")
            found = model.get("model") is not None and (model.get("provider"), model["model"]) in published[side]
            if found != (state == "done"):
                raise SystemExit(f"{label}: its {side} side is {state}, but it has " + (
                    "a published run: mark it done" if found else "no published run: it is not done"))
            word = esc(PROGRESS_STATES[state])
            shown = word if state == "none" else f'<span class="nm">{word}</span>'
            cells.append(f'<td>{shown}' + (f'<span class="small">{esc(note)}</span>' if note else "") + "</td>")
        rows.append(f'<tr><td class="model"><span class="lb-progress-name">{esc(model["name"])}</span><span class="small">'
                    f'{esc(model["maker"])} · {esc(model["kind"])}</span></td>{"".join(cells)}</tr>')
    heads = "".join(f'<th scope="col">{esc(title)}</th>' for _, title in PROGRESS_SIDES)
    notes = "".join(f'<p class="table-note">{esc(line)}</p>' for line in section.get("notes", []))
    return (f'<section class="lb-progress" aria-labelledby="in-progress"><h3 id="in-progress">In progress</h3>'
            f'<p class="table-note">{esc(section["lead"])} As of {esc(section["as_of"])}.</p>'
            f'<div class="table-wrap"><table class="lb-table lb-progress-table" aria-labelledby="in-progress"><thead><tr>'
            f'<th scope="col">Model</th>{heads}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>{notes}</section>')



def leaderboard(site: Site, about: str = "about/#leaderboard") -> str:
    """The Leaderboard's controls (the part switch, the type keys, the All setups key, then the Class keys on a row of
    their own), then each part's Measure row (site.measure_keys, as on Logic & Math: Accuracy, this table, pressed; the
    other measures link to their views for the part), table, meaning line, empty-view line and # line (TIER_LINE or
    RANK_LINE), the row rule line and the class rule line (Turkish shown first, Decision models and Class: All the
    default, site.js); nothing else stands between the keys and the table. The All setups panel (today's full ranking
    with its tabs, #all-setups) follows it in index.html, then the line of counts."""
    board = Board(site)
    tr_heads, tr_body, _ = turkish(site, board)
    re_heads, re_body, _ = turkish(site, board, "reading")
    gr_heads, gr_body, _ = turkish(site, board, "grammar")
    en_heads, en_body = english(site, board, False)
    bo_heads, bo_body = english(site, board, True)
    runs = [*site.runs, *(setup_run(site, model) for model in english_only(board.english))]
    groups = {name: site.runs[0]["groups"][name]["questions"] for name in ("reading", "grammar")}
    parts = {"turkish": table("turkish", tr_heads, tr_body, "One row per model: Turkish accuracy"),
             "turkish-reading": table("turkish-reading", re_heads, re_body, "One row per model: Turkish reading accuracy"),
             "turkish-grammar": table("turkish-grammar", gr_heads, gr_body, "One row per model: Turkish grammar accuracy"),
             "english": table("english", en_heads, en_body, "One row per model: English accuracy"),
             "both": table("both", bo_heads, bo_body, "One row per model: Turkish and English accuracy")}
    numbers = {"turkish": TIER_LINE.format(pairs=bp.count(site.results["group_pairs"])),
               **{part: RANK_LINE.format(part=label) for part, label in PARTS if part != "turkish"}}
    keys = lambda name, options, current: "".join(  # noqa: E731
        f'<button type="button" class="key" data-lb-{name}="{value}" aria-pressed="{str(value == current).lower()}">'
        f'{esc(label)}</button>' for value, label in options)
    controls = (f'<div class="lb-controls needs-js"><span class="keys" role="group" aria-label="Part of the test">'
                f'{keys("part", PARTS, DEFAULT_PART)}</span><span class="keys" role="group" aria-label="Model type">'
                f'{keys("type", TYPES, DEFAULT_TYPE)}</span><button type="button" class="key lb-all-key" '
                'data-lb-all aria-pressed="false" aria-controls="all-setups">All setups</button></div>'
                '<div class="lb-controls lb-size-keys needs-js"><span class="keys" role="group" aria-label="Class">'
                f'<span class="lb-keys-label" aria-hidden="true">Class:</span>{keys("class", [("all", "All"), *site.model_classes()], "all")}'
                '</span></div>')
    listed = sorted({site.title(run) for run, _ in board.turkish_rows() if turkish_listed(site, run)}, key=str.casefold)
    read = max(item["read"] for item in site.turkish_support.values())
    tr_legend = (f'<p class="table-note lb-tr-note">{TR_MARK} {TR_NOT_SUPPORTED}: the model\'s own card or maker docs do not '
                 f'list Turkish (read {esc(bp.long_date(read))}; Ümit #5067)'
                 + (f"; of the models here only {esc(bp.and_list(listed))} list it" if listed else "") + ".</p>")
    panels = "".join(f'<div class="lb-part" data-lb-part="{part}"{"" if part == DEFAULT_PART else " hidden"}>'
                     f'{measure_keys("", (part,))}{parts[part]}'
                     f'<p class="chart-sub lb-meaning">{esc(meaning(part, board.total, board.kept, groups))}</p>'
                     f'<p class="table-note lb-empty" hidden>{esc(EMPTY_LINE)}</p>'
                     f'<p class="table-note lb-numbers">{esc(numbers[part])}</p>'
                     f'{tr_legend if part.startswith("turkish") else ""}</div>'
                     for part, _ in PARTS)
    return (f'{controls}<div class="lb-models" data-lb-view="models">{panels}'
            f'<p class="table-note lb-rule">{esc(ROW_LINE)} <a href="{about}">How rows are chosen</a></p>'
            f'<p class="table-note lb-size-line" hidden>{esc(class_line(site, runs))}</p></div>{in_progress(site, board)}')


def about_text(site: Site, origin: str) -> str:
    """The leaderboard rules for the About page: the row rule, the dated-checkpoint map, the ranks and the whiskers."""
    checkpoints = site.config["leaderboard"]["dated_checkpoints"]
    mapped = "; ".join(f"<code>{esc(dated)}</code> is listed under <code>{esc(original)}</code>, by this map"
                       for dated, original in checkpoints.items())
    return (f"<p>{esc(RULE)}</p>"
            + (f"<p>The dated-checkpoint map (page_config.json, leaderboard.dated_checkpoints), the only model IDs "
               f"listed under another: {mapped}. The row shows the original; the checkpoint's setups sit under its other "
               "settings.</p>" if mapped else "")
            + "<p>Ranks show observed scores; small gaps need not be meaningful. The type keys (All, Chat models, Decision "
            "models) and the Class keys (Tiny, Small, Medium and Large for an open model by its total parameters; "
            "Efficient, Workhorse and Flagship for a closed model, or an open one of undisclosed size, by its list price "
            "per 1M input tokens) choose the rows in view; the setups only this site ran are in no class and show under "
            "Class: All. On the Turkish part the Tier column holds each row's tier among the rows in view: ranked by "
            "accuracy, a row joins the tier of the tier's top row when the all-pairs test behind the full ranking's "
            "letters found no difference between them, else it starts the next tier. On Turkish reading, Turkish grammar, "
            "English reading and Both, which no all-pairs test covers, the Rank column holds the row's place, 1, 2, 3 "
            "without repeats; rows with the same score keep the table's order, which claims no difference. Each row "
            "names its model by its official name, with a small tag beside it for how the setup ran (setting · route · "
            "snapshot, as \u201chigh \u00b7 chat\u201d or \u201cAPI \u00b7 with web\u201d; a decision model with one setup has none), "
            "then its class label, starting Open or Closed; its details box gives the size in full and the model page its source.</p>"
            "<p>Each bar runs from 0 to 100%; its whisker is the Wilson 95% interval of the accuracy, the interval each "
            "setup's page gives. The paired tests behind the full ranking's letters are on "
            f'<a href="{rel(origin, "method/")}">Method</a>.</p>'
            f'<p>{NOT_MEASURED} or "Not run" in a column: the setup has no such value; the details box leaves such a line '
            "out.</p>")
