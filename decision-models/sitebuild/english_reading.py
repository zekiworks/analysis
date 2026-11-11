"""Turkish vs English (turkish-vs-english/, earlier english-reading/, now a redirect), the site's fourth tab: the Text
tab's reading questions translated into English, asked of the Text tab's setups as on the Text tab, against the same
setups' Turkish runs on the same questions. Since 5 November 2026 every Text tab setup also runs in English, decision
models and chat models alike. From results.json's `english_reading` (every number), english-reading.json (the track's
public record: the translator, its prompts, the flags and each question's hash of its English text) and
page_config.json's `english_reading` (the reason of each Text tab setup without an English run, by provider with
overrides by run, and the structural check's facts) and `model_languages`.

Every part that depends on the setups shown comes once per group of the view bar (GROUPS: all, decision, chat;
data-models, toggled by site.js, with each setup's row and bar marked data-class for the Class keys; the all group is the one shown without JavaScript), its counts and sentences computed
for that group, its setups ranked within it: the face's charts (accuracy in both languages first, ranked by English
accuracy, then the paired test, Site hbars; cost and latency of the Text tab run and the first English
run, measure_card(), from english_reading.models[]'s cost and latency), the main table (main_table(): accuracy, "I don't
know" in both languages, cost and latency, the rank in both languages and the languages the model card lists), the
risk-coverage plots and the table of the runs with the option, the Non-hallucination part (#non-hallucination: the same
questions with an "I don't know" option in English against the Hallucination tab's "Bilmiyorum", dont_know_face(),
decision and chat models ranked together in the all group, a chat model's side still running read as Running), the
Results table and the setups without an English run. Nothing stands above the results but a group's empty-view line (no
intro, the project lead via Zeki #4663, #4666): the scope is in the first chart's heading and the translation check's limit
in one line (limit_line()) with More about this page sits under the accuracy charts; the lead with the headline,
limit_note() and the experiments line are in About's notes on each page (Site.note). The view bar's row 3 links to the
face's parts: #accuracy, #non-hallucination, #cost and
#latency, so the page has no links row of its own. The parts about decision models only come once, for the all and
decision groups: Liquid d1-ultra against each decision model (with one note for the chat group), the same with the
option written "I don't know" in Turkish too (dont_know_word_face()) and the option's word on the Turkish questions
(option_word()). Under Info: the tables, the setups without an English run, Our method and the full instructions and
prompts of each kind of run. The question text, Turkish or English, is never published. The tab ranks nothing on the
Text tab and changes none of its numbers. English-only setups (english_reading.english_only: English runs and no Text tab
run, Ümit's small models) are in no paired table or test here: each group's copy lists them under the main table
(english_only_list(), English accuracy, Turkish Not run); the English reading page (english_view.py) ranks them with the
others."""

from __future__ import annotations

import colorsys
import functools
import json
import math
from collections import Counter
from typing import Any, Callable

import benchmark_metrics as bm
import build_page as bp
from sitebuild.data import BLOB_URL
from sitebuild.dont_know import check_option_word, group_data, option_word_rows
from sitebuild.site import (DECISION_ONLY, GROUPS, NO_LIST_PRICE, NOT_MEASURED, ROOT, Site, chat_note, cost_missing,
                            cost_per, cost_switch, cost_tick, cost_unit_in, cost_value, cost_words, esc, experiments,
                            family_icon, family_legend, hbars, legend_mark, line_plot, log_axis, measure_rows, more_link,
                            pct, rel, request_size, run_families, seconds_tick, shown)
from sitebuild.names import tag_html
from sitebuild.vision import cell, joined, run_span

PATH = "turkish-vs-english/"
# The English reading page (sitebuild/english_view.py), where an English-only setup's name links (only_anchor).
ENGLISH_VIEW = "english/"
# The value column's name in every chart of the two languages, Turkish first: in full and on a phone (hbars head).
TR_EN = ("Turkish · English", "TR · EN")
NUMBERS = "<span>Numbers on the right: Turkish · English.</span>"
# The tab's earlier address, now a page that sends its readers to PATH with their fragment.
OLD_PATH = "english-reading/"
# The kept questions' IDs, one per line, written by the build from english-reading.json.
KEPT_IDS = "kept-question-ids.txt"
RECORD = ROOT / "english-reading.json"
# The options heading of the Text tab's prompts (runner/benchmark_ollama.py OPTIONS_HEADING); results.json gives the
# English one.
TURKISH_OPTIONS_HEADING = "Seçenekler:"
# The translator's name on the page, by model ID (english-reading.json translator.model).
TRANSLATORS = {"claude-opus-5-5": "Claude Opus 5.5"}
# A model asked in English under another model ID than its Turkish run: (provider, Turkish model ID, English model ID)
# with the reason, a clause after "because".
RENAMED = {
    ("liquid", "d1:free", "d1"): "Liquid's API no longer serves that name; its model list still names d1, released "
                                 "29 September 2026",
}
SIGNIFICANT = 0.05
# The native points of english_reading.coverage, in the table's and the legends' order: (language, wording), with each
# wording's marker shape in the plots.
NATIVE = (("Turkish", "Bilmiyorum"), ("Turkish", "I don't know"), ("English", "I don't know"))
SHAPES = {"Bilmiyorum": "circle", "I don't know": "square"}
# One colour per English setup, the same in every plot, in english_reading.models' order (model_colours); mid
# lightness, readable on both themes' panels. Past these, hues a golden angle apart (GOLDEN, a share of the circle).
COLOURS = ("#2f6fd6", "#d9622b", "#2e9e5b", "#c23b8a", "#8a6bd1", "#b8901a", "#1f9eb3", "#d13c3c", "#6d8a1f",
           "#9a5a33", "#5b7fa8", "#e0739f", "#3fae99", "#7c7871", "#9bbf1f", "#e3a21a", "#5fb4f0")
GOLDEN = 0.381966


def anchor(base: str, group: str) -> str:
    """A part's id in its group's copy: the all group keeps the plain id, the one links from other pages use."""
    return base if group == GROUPS[0] else f"{base}-{group}"


def group_models(site: Site, data: dict[str, Any], group: str) -> list[dict[str, Any]]:
    """The English setups of a group, in english_reading.models' order (by English right answers)."""
    return [model for model in data["models"] if site.in_group(site.by_id[model["turkish_run"]], group)]


def english_members(site: Site, data: dict[str, Any], group: str) -> list[dict[str, Any]]:
    """The English reading page's setups of a group: group_models with the group's English-only setups, by English right
    answers (a stable sort, so the paired setups keep english_reading.models' order among equals)."""
    alone = [model for model in english_only(data) if site.in_group(setup_run(site, model), group)]
    return sorted(group_models(site, data, group) + alone, key=lambda model: -model["english"]["right"])


def noun(group: str, count: int) -> str:
    """What a group's members are called: setups (all), decision models, chat model setups."""
    one, many = {"all": ("setup", "setups"), "decision": ("decision model", "decision models"),
                 "chat": ("chat model setup", "chat model setups")}[group]
    return one if count == 1 else many


def model_colours(site: Site) -> dict[int, str]:
    """Each English setup's colour by its Text tab run, in english_reading.models' order: COLOURS, then hues a golden
    angle apart at mid lightness, so that every setup has its own (here and in the Hallucination tab's plots)."""
    colours = {}
    for index, model in enumerate(site.results["english_reading"]["models"]):
        step = index - len(COLOURS)
        if step < 0:
            colours[model["turkish_run"]] = COLOURS[index]
            continue
        rgb = colorsys.hls_to_rgb((0.6 + step * GOLDEN) % 1, 0.47 if step % 2 else 0.55, 0.6)
        colours[model["turkish_run"]] = "#" + "".join(f"{round(255 * value):02x}" for value in rgb)
    return colours


def english_only(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The English-only setups (results.json english_reading.english_only, or english_reading.dont_know.english_only):
    for english_reading, the setups with English runs and no Text tab run of the same setup (Ümit's small models), each
    with its name, settings, size record, group, access, billing, hardware, cost, latency and English counts; for its
    dont_know, the models with English "I don't know" runs and no Turkish run with “Bilmiyorum” on the kept questions (a
    decision model with its reason, a chat model's run still running, or an English-only setup with text_run null and
    reading_run its English-only entry's first run), so in no paired test or Holm family."""
    return data.get("english_only") or []


def turkish_running(site: Site, data: dict[str, Any]) -> set[str]:
    """The English-only setups whose Text tab run is still running (page_config.json english_reading.turkish_running's
    models, by model id): their Turkish side reads Running, not Not run (the project lead via Zeki #4748: a measure still
    running is shown pending, never as 0 or another run's number). The build stops when a listed model is not an
    English-only setup: its Text tab run is in, so take it off the list."""
    listed = set((site.config["english_reading"].get("turkish_running") or {}).get("models", []))
    stale = sorted(listed - {model["model"] for model in english_only(data)})
    if stale:
        raise SystemExit(f"page_config.json english_reading.turkish_running: {', '.join(stale)} is not an English-only "
                         "setup (its Text tab run is published: take it off the list)")
    return listed


def setup_key(model: dict[str, Any]) -> int:
    """An English reading entry's key on the English pages: its Text tab run, or an English-only setup's first English
    run (run ids are unique across the report, so the two never collide)."""
    return model.get("turkish_run", model["run"])


def setup_run(site: Site, model: dict[str, Any]) -> dict[str, Any]:
    """An English reading entry's setup as a run: its Text tab run, or an English-only setup's entry itself (provider,
    model, settings, size record, billing, hardware) with its first English run's cost basis, cost, upper-bound mark and
    price (results.json prices holds the Text tab runs' only) in the Text tab runs' fields, for the view groups,
    families, names and cost words."""
    if "turkish_run" in model:
        return site.by_id[model["turkish_run"]]
    cost = model["cost"]["english"] or {}
    return {**model, "cost_basis": cost.get("basis"), "api_equivalent_usd": cost.get("usd"),
            "cost_upper_bound": bool(cost.get("upper_bound")), "price": cost.get("price")}


def idk_key(model: dict[str, Any]) -> int:
    """An english_reading.dont_know entry's English reading entry, by setup_key: its Text tab run, or an English-only
    setup's reading_run."""
    return model["reading_run"] if model["text_run"] is None else model["text_run"]


@functools.cache
def setup_families(site: Site) -> dict[int, dict[str, str]]:
    """Each English reading entry's model family by setup_key: Site.families for the Text tab runs, run_families
    (model_families) for the English-only setups."""
    return {**site.families, **run_families(english_only(site.results["english_reading"]))}


def setup_icon(site: Site, model: dict[str, Any]) -> str:
    """An English reading entry's family icon, for the left of its name."""
    return family_icon(setup_families(site)[setup_key(model)]["name"])


def only_anchor(model: dict[str, Any]) -> str:
    """The id of an English-only setup's row on the English reading page (its all group's table), which its name links to
    from every page: it has no model page."""
    return f"english-only-{model['run']}"


def entry_href(site: Site, origin: str, model: dict[str, Any]) -> str:
    """A link from the page at origin for an English reading entry: its model page's English section (setup_href), or
    an English-only setup's row on the English reading page."""
    if "turkish_run" in model:
        return setup_href(site, origin, model["turkish_run"])
    return f"{rel(origin, ENGLISH_VIEW)}#{only_anchor(model)}"


@functools.cache
def setup_labels(site: Site) -> dict[int, str]:
    """The English setups' plain names (site.plain: official name · tag) on both English pages, by setup_key, the
    English-only setups too (setup_run), so a setup reads the same in every group."""
    data = site.results["english_reading"]
    return {setup_key(model): site.plain(setup_run(site, model)) for model in [*data["models"], *english_only(data)]}


def not_run(site: Site, data: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """The Text tab setups without an English run, by reason, in page_config.json's english_reading.not_run order: each
    entry names providers or runs, an entry by run taking a setup over from its provider's. Stops the build when a Text
    tab setup has neither an English run nor a reason, or when an entry no longer fits: a run not on the Text tab or
    with an English run, a provider without a setup left to run, a run or provider listed twice."""
    problems = []
    ran = {model["turkish_run"] for model in data["models"]}
    entries = site.config["english_reading"]["not_run"]
    by_provider: dict[str, int] = {}
    by_run: dict[int, int] = {}
    for index, entry in enumerate(entries):
        if not entry.get("reason") or bool(entry.get("providers")) == bool(entry.get("runs")):
            problems.append(f"entry {index + 1}: not a reason with either providers or runs")
        for provider in entry.get("providers", []):
            if provider in by_provider:
                problems.append(f"provider {provider} listed twice")
            by_provider[provider] = index
        for run in entry.get("runs", []):
            if run in by_run:
                problems.append(f"run {run} listed twice")
            by_run[run] = index
            if run not in site.by_id:
                problems.append(f"run {run} is not on the Text tab")
            elif run in ran:
                problems.append(f"run {run} ({site.plain(site.by_id[run])}) has an English run: remove its reason")
    found: list[list[dict[str, Any]]] = [[] for _ in entries]
    for run in site.runs:
        if run["run"] in ran:
            continue
        index = by_run.get(run["run"], by_provider.get(run["provider"]))
        if index is None:
            problems.append(f"{site.plain(run)} (run {run['run']}, provider {run['provider']}) has neither an "
                            "English run nor a reason")
        else:
            found[index].append(run)
    for provider, index in by_provider.items():
        if not any(run["provider"] == provider for run in found[index]):
            problems.append(f"provider {provider}: no Text tab setup left without an English run")
    if problems:
        raise SystemExit("page_config.json english_reading.not_run:\n  " + "\n  ".join(problems))
    return [(entry["reason"], runs) for entry, runs in zip(entries, found)]


def check(site: Site, data: dict[str, Any], record: dict[str, Any]) -> None:
    """Stops the build when results.json's english_reading, english-reading.json and page_config.json's english_reading
    disagree, or when the data no longer fits what the page says about it."""
    problems = []
    for key, ours in (("translations_sha256", "translations_sha256"), ("reading_questions", "reading_questions"),
                      ("questions", "kept"), ("flagged", "flagged")):
        if data[key] != record[ours]:
            problems.append(f"{key} {data[key]!r}, english-reading.json {ours} {record[ours]!r}")
    questions = record["questions"]
    kept = sum(1 for question in questions if question["kept"])
    reasons = Counter(reason for question in questions if not question["kept"] for reason in question["reasons"])
    if len(questions) != record["reading_questions"] or kept != record["kept"] or len(questions) - kept != record["flagged"]:
        problems.append("english-reading.json: its question list does not give its counts")
    if dict(reasons) != record["reasons"] or any(question["kept"] == bool(question["reasons"]) for question in questions):
        problems.append("english-reading.json: its reasons are not its flagged questions' reasons")
    turkish = site.answers["prompts"]["system_one_instructions"]
    if turkish.count("Turkish") != 1 or data["instructions"] != turkish.replace("Turkish", "English"):
        problems.append("the English instructions are not the System One instructions with Turkish changed to English")
    if record["translator"]["model"] not in TRANSLATORS:
        problems.append(f"no name for the translator {record['translator']['model']}")
    makers = {run["provider"] for run in site.runs if run["model"] == record["translator"]["model"]}
    if any(site.decision(run) for run in site.runs if run["provider"] in makers):
        problems.append("the translator's maker has a decision model on the Text tab")
    for model in data["models"]:
        run = site.by_id.get(model["turkish_run"])
        if run is None:
            problems.append(f"{model['name']}: Turkish run {model['turkish_run']} is not on the Text tab")
            continue
        if model["name"] != run["name"] or model["provider"] != run["provider"]:
            problems.append(f"{model['name']}: not the setup of Turkish run {run['run']}")
        if site.decision(run) and run["questions_per_request"] != 1:
            problems.append(f"{model['name']}: Turkish run {run['run']} does not ask one question per request")
        if model["model"] != run["model"] and (run["provider"], run["model"], model["model"]) not in RENAMED:
            problems.append(f"{model['name']}: asked as {model['model']}, its Turkish run as {run['model']}, with no reason")
        if model["runs"][0] != model["run"] or model["turkish_runs"][0] != model["turkish_run"]:
            problems.append(f"{model['name']}: the first run is not the one compared")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["invalid"] != data["questions"]:
                problems.append(f"{model['name']}: its {side} answers do not cover the {data['questions']} questions")
        paired = model["paired"]
        if paired["english_only_right"] - paired["turkish_only_right"] != model["english"]["right"] - model["turkish"]["right"]:
            problems.append(f"{model['name']}: the paired counts do not give the difference in right answers")
    if len({model["turkish_run"] for model in data["models"]}) != len(data["models"]):
        problems.append("two English setups share a Text tab run")
    both = [model["paired"] for model in data["models"]]
    if any(abs(paired["p_holm"] - adjusted) > 1e-9 for paired, adjusted in zip(both, bm.holm([paired["p"] for paired in both]))):
        problems.append(f"the Holm-adjusted p values are not Holm's over the {len(both)} setups")
    if group_models(site, data, "chat"):
        prompts = data.get("chat_prompts") or {}
        if not data.get("chat_prompt_version") or not prompts.get("confidence_system") or not prompts.get("confidence_instruction"):
            problems.append("chat setups in English without the chat prompts and their version")
    if problems:
        raise SystemExit("english_reading:\n  " + "\n  ".join(problems))
    not_run(site, data)


def label(site: Site, model: dict[str, Any]) -> str:
    """An English reading entry's plain name (official name · tag) for text: tooltips, sort keys, prose lists."""
    return setup_labels(site)[setup_key(model)]


def name_html(site: Site, run: dict[str, Any], href: str, title: str = "") -> str:
    """A setup's name cell content: its official name linking href, the tag after the link, then its class label."""
    tip = f' title="{esc(title)}"' if title else ""
    return (f'<a class="model-name" href="{href}"{tip}>{esc(site.title(run))}</a>{tag_html(site.tag(run))} '
            f'{site.label(run)}')


# The id of the English section of a setup's model page (models.py english), which every setup name on the two English
# pages links to.
ENGLISH_ANCHOR = "english"


def setup_href(site: Site, origin: str, run: int) -> str:
    """A link from the page at origin to the model page of the setup whose Text tab run is run: to its English section
    where the setup has an English run (english_reading.models), else to the top of the page."""
    path = rel(origin, site.model_path(site.by_id[run]))
    return f"{path}#{ENGLISH_ANCHOR}" if run in setup_labels(site) else path


def href(site: Site, model: dict[str, Any]) -> str:
    return entry_href(site, PATH, model)


def family_bars(site: Site, run: int, *bars: tuple[float, str]) -> list[dict[str, Any]]:
    """A model's bars, each (value, language), in the model family's colour of its Text tab run (Site.families): the
    language only stripes the English bar (v3.css)."""
    colour = site.families[run]["colour"]
    return [{"value": value, "kind": language, "colour": colour} for value, language in bars]


# The two sides of a setup, as english_reading.models[] names them, and how the page names them.
SIDES = {"turkish": "Turkish", "english": "English"}
# What a cost's basis (results.json's cost_basis, as english_reading.models[].cost gives it) says under the cost.
BASIS_WORDS = {"api": "at list prices", "subscription": "subscription, priced as the API", "free tier":
               "free tier, at the list price", "maker": "at the maker's list price",
               "weights": "at a host's list price for the same weights", "gpu": "from GPU time"}


def measure_value(model: dict[str, Any], measure: str, side: str) -> float | None:
    """A setup's cost ($ per 1,000 questions) or latency (median seconds per request) on one side, from
    english_reading.models[].cost and .latency: the first English run's, or the Text tab run's; None when not measured."""
    entry = model[measure][side]
    if entry is None:
        return None
    return entry["per_1000"] if measure == "cost" else entry["median_request_seconds"]


def cost_title(site: Site, model: dict[str, Any]) -> str:
    """A cost value's tooltip attribute: site.cost_tip of the setup (setup_run), or nothing for plain API price."""
    tip = site.cost_tip(setup_run(site, model))
    return f' title="{esc(tip)}"' if tip else ""


def cost_note(site: Site, models: list[dict[str, Any]], sides: tuple[str, ...]) -> str:
    """The cost line under a cost chart or table (site.cost_note), with the upper-bound note where an English cost is
    marked and the Text tab runs' note does not already say it."""
    note = site.cost_note(setup_run(site, model) for model in models)
    upper = upper_note(site, models, sides)
    return note if not upper or upper[0] in note else f"{note} {upper[0]}"



def upper_mark(site: Site, entry: dict[str, Any] | None) -> str:
    """≤ before a cost that is an upper-bound estimate (the cost entry's upper_bound), else nothing."""
    return f"{site.config['first_cost_marks']['upper']['mark']} " if entry and entry.get("upper_bound") else ""


def upper_note(site: Site, models: list[dict[str, Any]], sides: tuple[str, ...]) -> list[str]:
    """The upper-bound note, when one of these setups' costs is marked."""
    upper = site.config["first_cost_marks"]["upper"]
    marked = any(upper_mark(site, model["cost"][side]) for model in models for side in sides)
    return [f"{upper['mark']} {upper['note']}"] if marked else []


def missing(site: Site, model: dict[str, Any], measure: str) -> str:
    """A missing value's cell: No list price for a cost of a setup on our own hardware whose maker lists no price
    (cost_missing, from the setup, setup_run), else Not measured."""
    return cost_missing(setup_run(site, model)) if measure == "cost" else NOT_MEASURED


def no_list_price(site: Site, model: dict[str, Any], measure: str) -> bool:
    return missing(site, model, measure) == NO_LIST_PRICE


def missing_note(site: Site, models: list[dict[str, Any]], sides: tuple[str, ...]) -> str:
    """A table note's words for its missing costs and latencies, each only where the table shows one: every cost
    without an estimate is of a setup on our own hardware (billing 'local'), so Not measured is a missing timing."""
    gaps = {missing(site, model, measure) for model in models for measure in ("cost", "latency") for side in sides
            if measure_value(model, measure, side) is None}
    words = []
    if NO_LIST_PRICE in gaps:
        words.append("No list price: a setup on our own hardware whose maker lists no price for the same model.")
    if NOT_MEASURED in gaps:
        words.append("Not measured: no timing.")
    return " ".join(words)


def measure_cell(site: Site, model: dict[str, Any], measure: str, side: str) -> str:
    """A table cell's content: the cost to three decimals with its basis under it (site.cost_tip in its tooltip), or the
    median latency with the request size and the requests in flight under it; without a value, No list price for a
    cost of a setup on our own hardware whose maker lists no price, else Not measured."""
    value = measure_value(model, measure, side)
    if value is None:
        return missing(site, model, measure)
    entry = model[measure][side]
    if measure == "cost":
        return (f'<span{cost_title(site, model)}>{cost_value(value, upper_mark(site, entry), dollar=False)}</span>'
                f'<span class="small">{esc(BASIS_WORDS[entry["basis"]])}</span>')
    flight = entry["concurrency"]
    sample = sample_size(site, model, side)
    measured = f", measured on a sample ({sample:,} questions)" if sample else ""
    return (f'{bp.seconds(value)}<span class="small">{esc(request_size(entry["questions_per_request"]))}, '
            f"{flight:,} in flight{measured}</span>")


SAMPLE_MARK = "*"  # a latency measured on a sample of the questions, as on the home page (build_site.SAMPLE_MARK)


def sample_size(site: Site, model: dict[str, Any], side: str) -> int | None:
    """The questions of the sample a side's latency was measured on (the Text tab setup's repeats on a fixed sample, as
    the home page marks it), or None for a latency of the run itself."""
    entry = model["latency"][side]
    if entry is None or entry.get("source") != "sample":
        return None
    return site.by_id[model["turkish_run"]]["latency"]["questions"]


def measure_heads(measure: str, sides: tuple[str, ...]) -> list[tuple[str, str]]:
    """The table columns of one measure, one per side: (header, the note under it)."""
    run = {"turkish": "Text tab run", "english": "first English run"}
    if measure == "cost":
        return [(f"{SIDES[side]} cost", f"$ per 1,000 questions, {run[side]}; lower is better") for side in sides]
    return [(f"{SIDES[side]} latency", f"median seconds per request, {run[side]}; lower is better") for side in sides]


def in_flight(requests: int) -> str:
    return f"{bp.count(requests)} request{'' if requests == 1 else 's'} in flight"


def counted(entries: list[dict[str, Any]], key: str, unit: Callable[[int], str]) -> str:
    """How many runs have each value of key, the most common first: "1 question per request for 24 runs and 16 for
    20"."""
    tally = sorted(Counter(entry[key] for entry in entries).items(), key=lambda item: (-item[1], item[0]))
    return joined([f"{unit(value) if index == 0 else bp.count(value)} for {bp.count(number)}"
                   + (f" run{'' if number == 1 else 's'}" if index == 0 else "")
                   for index, (value, number) in enumerate(tally)])


def measure_card(site: Site, data: dict[str, Any], group: str, measure: str, sides: tuple[str, ...],
                 link: Callable[[Site, dict[str, Any]], str], method: str,
                 members: Callable[[Site, dict[str, Any], str], list[dict[str, Any]]] = group_models) -> str:
    """A group's Cost or Latency card on the English pages, as the home page's Cost and Latency charts (log scale, lower
    is better, each bar in its model family's colour): English reading shows the first English run (sides
    ("english",)) of each of its setups (members: english_members, with the English-only ones), Turkish vs English the
    Text tab run and the first English run as paired bars, Turkish first, the
    English one striped. Ordered by the English value, lowest first; a setup without a value reads Not measured and is
    named in the note. link: a setup's link; method: the link to Our method on the comparison page."""
    models = members(site, data, group)
    families = setup_families(site)
    paired = len(sides) == 2
    total = data["questions"]
    cost = measure == "cost"
    values = [value for model in models for side in sides if (value := measure_value(model, measure, side)) is not None]
    order = lambda model: tuple(item for side in reversed(sides) for item in  # noqa: E731
                                (measure_value(model, measure, side) is None, measure_value(model, measure, side) or 0)) \
        + (label(site, model).casefold(),)
    ordered = sorted(models, key=order)
    position, axis = log_axis(values, cost_tick if cost else seconds_tick) if values else (None, {})

    def short(model: dict[str, Any], side: str) -> str:
        """The value as the chart writes it beside the bars, as HTML: a cost in both units (cost_value)."""
        value = measure_value(model, measure, side)
        if value is None:
            if no_list_price(site, model, measure):
                return "no list price"
            return "n.m." if paired else "Not measured"
        if cost:
            return cost_value(value, upper_mark(site, model["cost"][side]), dollar=not paired)
        text = esc(bp.seconds(value))
        if sample_size(site, model, side):
            text += esc(SAMPLE_MARK)
        return text if paired else f"{text}\u00a0s"

    def said(model: dict[str, Any], side: str) -> str:
        value, entry = measure_value(model, measure, side), model[measure][side]
        if value is None:
            return f"{'no list price' if no_list_price(site, model, measure) else 'not measured'} in {SIDES[side]}"
        if cost:
            return (f"{cost_words(value, upper_mark(site, entry))} in {SIDES[side]} ({BASIS_WORDS[entry['basis']]}"
                    f"{', an upper-bound estimate' if entry.get('upper_bound') else ''})")
        return (f"median {bp.seconds(value)} s, 90th percentile {bp.seconds(entry['p90_request_seconds'])} s per request in "
                f"{SIDES[side]}, {request_size(entry['questions_per_request'])}, {entry['concurrency']:,} in flight"
                + (f", measured on a sample ({sample_size(site, model, side):,} questions)" if sample_size(site, model, side) else ""))

    rows = []
    for model in ordered:
        colour = families[setup_key(model)]["colour"]
        bars = [{"value": position(value), "colour": colour, **({"kind": side} if paired else {})}
                for side in sides if (value := measure_value(model, measure, side)) is not None]
        text = " · ".join(short(model, side) for side in sides)
        tip = site.cost_tip(setup_run(site, model)) if cost else None
        rows.append({"label": site.title(setup_run(site, model)), "tag": site.tag(setup_run(site, model)),
                     "family": families[setup_key(model)]["name"], "href": link(site, model), "bars": bars, "html": text,
                     "class_key": site.model_class(setup_run(site, model)),
                     "title": f"{label(site, model)}: " + "; ".join(said(model, side) for side in sides)
                     + (f". {tip}" if tip else "")})
    count = len(models)
    whose = (f"each of the {bp.in_words(count)} {noun(group, count)}' Text tab run and its first English run" if paired else
             f"each of the {bp.in_words(count)} {noun(group, count)}' first English run")
    if cost:
        title = (f"Cost {cost_per()} in Turkish and in English" if paired else
                 f"Cost {cost_per('per 1,000 English questions', 'per 1M English questions')}")
        sub = f"Estimated dollars {cost_per()}: {whose}, ordered by English cost · lower is better"
        notes = [esc(cost_note(site, models, sides))]
    else:
        title = esc("Median latency per request in Turkish and in English" if paired else
                    f"Median latency per request on the {total:,} English questions")
        sub = f"Median time per request: {whose}, ordered by English latency · lower is better"
        notes = ["Time per request as measured from our computer during each run; API times include the network."]
        for side in sides:
            entries = [model["latency"][side] for model in models if model["latency"][side] is not None]
            if entries:
                runs = "Text tab runs" if side == "turkish" else "English runs"
                notes.append(f"{runs}: {counted(entries, 'questions_per_request', request_size)}; "
                             f"{counted(entries, 'concurrency', in_flight)}.")
        local = [model for model in models if site.decision(setup_run(site, model))
                 and setup_run(site, model)["billing"] == "local"
                 and model["latency"]["english"] is not None]
        if local:
            spark = [label(site, model) for model in local if "DGX Spark" in (setup_run(site, model)["hardware"] or "")]
            notes.append(f"The English runs of the {bp.in_words(len(local))} self-hosted decision "
                         f"model{'' if len(local) == 1 else 's'} ran on our RTX PRO 6000 GPU"
                         + (f"; the Text tab runs of {esc(joined(spark))} ran on an NVIDIA DGX Spark "
                            f'(<a href="{method}">Our method</a>)' if spark else "") + ".")
            clef = [label(site, model) for model in local if setup_run(site, model)["provider"] == "clef"]
            if len(clef) > 1:
                notes.append(f"{esc(joined(clef))} ran their English runs at the same time on one GPU.")
        for side in sides:
            sampled = sorted({sample_size(site, model, side) for model in models} - {None})
            if sampled:
                notes.append(f"{SAMPLE_MARK} Measured on a sample ({joined([f'{size:,}' for size in sampled])} questions): "
                             f"the {'Text tab' if side == 'turkish' else 'English'} setup's repeats on a fixed sample, as "
                             "on the home page.")
    notes.append("Log scale.")
    for side in sides:
        unpriced = [label(site, model) for model in ordered
                    if measure_value(model, measure, side) is None and no_list_price(site, model, measure)]
        unmeasured = [label(site, model) for model in ordered
                      if measure_value(model, measure, side) is None and not no_list_price(site, model, measure)]
        where = f" in {SIDES[side]}" if paired else ""
        if unpriced:
            notes.append(f"No list price{where}: {esc(joined(unpriced))}, on our own hardware; the maker lists no price "
                         "for the same model.")
        if unmeasured:
            notes.append(f"Not measured{where}{' (n.m.)' if paired else ''}: {esc(joined(unmeasured))}.")
    legend = ('<span><i class="swatch swatch-turkish"></i>Turkish (the Text tab run), the upper bar</span> '
              '<span><i class="swatch swatch-english"></i>English (first run), the lower bar, striped</span> '
              + NUMBERS + " ") if paired else ""
    legend += family_legend([families[setup_key(model)] for model in ordered]) + "".join(
        f" <span>{note}</span>" for note in notes)
    head = TR_EN if paired else ("Cost", "Cost") if cost else ("Median latency", "Median")
    priced = not cost or not all(no_list_price(site, model, measure) for model in models)
    chart = hbars(rows, head=head, **axis) if values else \
        f'<p class="note">{"Not measured" if priced else "No list price"} for any {noun(group, 1)}.</p>'
    return (f'<figure class="panel chart-card" id="{anchor(f"chart-{measure}", group)}" {shown(group)}>'
            f'<div class="chart-head"><h2>{title}</h2>{cost_switch() if cost else ""}<p class="chart-sub">{sub}</p></div>{chart}'
            f'<p class="chart-legend">{legend}</p></figure>')


def significant(model: dict[str, Any]) -> bool:
    return model["paired"]["p_holm"] < SIGNIFICANT


def direction(model: dict[str, Any]) -> str:
    """Which language the model scored higher in, as the headline and charts say it."""
    difference = model["english"]["right"] - model["turkish"]["right"]
    return "higher in English" if difference > 0 else "higher in Turkish" if difference < 0 else "the same in both"


def headline(site: Site, data: dict[str, Any], group: str) -> str:
    """One line at the top of a group's copy: how many of its setups scored higher in English, and how many of their
    differences are significant after Holm's correction (over every English setup, whatever the group shown)."""
    models = group_models(site, data, group)
    total, family = len(models), len(data["models"])
    higher = sum(1 for model in models if model["english"]["right"] > model["turkish"]["right"])
    lower = sum(1 for model in models if model["english"]["right"] < model["turkish"]["right"])
    same = total - higher - lower
    first = (f"{bp.opening_count(higher) if higher else 'None'} of the {bp.in_words(total)} {noun(group, total)} compared "
             "scored higher on the English translation than on the Turkish original")
    rest = []
    if lower:
        rest.append(f"{bp.in_words(lower)} scored lower")
    if same:
        rest.append(f"{bp.in_words(same)} the same")
    holm = f"after Holm's correction over all {bp.in_words(family)} English {noun('all', family)}"
    found = [model for model in models if significant(model)]
    if not found:
        verdict = ("the difference is not significant" if total == 1 else
                   "none of the differences is significant") + f" {holm}, so each could be chance"
    else:
        named = joined([f"{esc(label(site, model))} ({direction(model)})" for model in found])
        verdict = (f"{bp.in_words(len(found))} of the {bp.in_words(total)} differences "
                   f"{'is' if len(found) == 1 else 'are'} significant {holm}: {named}")
    return (f"<p><strong>{first}</strong>{''.join('; ' + part for part in rest)}; {verdict} "
            f'(<a href="#{anchor("chart-paired", group)}">Paired test</a>).</p>')


def face(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the tab's face: two chart cards, accuracy in Turkish and in English first (ranked by English
    accuracy), then the paired test of the two (the questions only one side got right, with p adjusted by Holm over every
    English setup), for the group's setups, every number from results.json's english_reading."""
    digits = site.config["percent_digits"]
    total, family = data["questions"], len(data["models"])
    models = group_models(site, data, group)
    count = len(models)

    def card(base: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor(base, group)}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    accuracy = card(
        "chart-accuracy", f"Accuracy in Turkish and in English · {total:,} reading questions, the English machine-translated",
        f"Share of the {total:,} kept reading questions answered right: each of the {bp.in_words(count)} "
        f"{noun(group, count)}' Text tab run and its first English run, ordered by English accuracy · higher is better",
        [{"label": site.title(site.by_id[model["turkish_run"]]), "tag": site.tag(site.by_id[model["turkish_run"]]),
          "family": site.families[model["turkish_run"]]["name"], "href": href(site, model),
          "class_key": site.model_class(site.by_id[model["turkish_run"]]),
          "text": f"{pct(model['turkish']['accuracy'], digits)} · {pct(model['english']['accuracy'], digits)}",
          "bars": family_bars(site, model["turkish_run"], (model["turkish"]["accuracy"], "turkish"), (model["english"]["accuracy"], "english")),
          "title": f"{label(site, model)}: {model['turkish']['right']:,} of {total:,} right in Turkish, "
                   f"{model['english']['right']:,} in English ({100 * model['difference']:+.{digits}f} points)"}
         for model in models],
        '<span><i class="swatch swatch-turkish"></i>Turkish (the Text tab run), the upper bar</span> '
        '<span><i class="swatch swatch-english"></i>English (first run), the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["turkish_run"]] for model in models]), head=TR_EN)
    tested = sorted(models, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"], label(site, model).casefold()))
    most = max(max(model["paired"]["english_only_right"], model["paired"]["turkish_only_right"]) for model in tested)
    # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    counts = lambda model: (model["paired"]["turkish_only_right"], model["paired"]["english_only_right"])  # noqa: E731
    found = [model for model in tested if significant(model)]
    others = [model for model in tested if not significant(model)]

    def adjusted(members: list[dict[str, Any]]) -> str:
        """The members' Holm-adjusted p values as the site writes p ("each" when they read the same)."""
        texts = [esc(bp.p_text(model["paired"]["p_holm"])) for model in members]
        return f"{texts[0]}{' each' if len(members) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below {SIGNIFICANT:g}): "
                f"{esc(joined([label(site, model) for model in found]))} ({adjusted(found)}).") if found else
               f"No difference is significant (Holm-adjusted p below {SIGNIFICANT:g}).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if found else f" Adjusted: {adjusted(others)}."
    paired = card(
        "chart-paired", "Right only in Turkish, or only in English?",
        f"Each setup's first English run against its Text tab run on the {total:,} kept questions: the questions only one of "
        f"the two got right, by the exact McNemar test with p adjusted by Holm's method over all {family} English "
        f"{noun('all', family)} · the longer bar is the language with more right answers",
        [{"label": site.title(site.by_id[model["turkish_run"]]), "tag": site.tag(site.by_id[model["turkish_run"]]),
          "family": site.families[model["turkish_run"]]["name"], "href": href(site, model),
          "class_key": site.model_class(site.by_id[model["turkish_run"]]),
          "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if significant(model) else ''}",
          "bars": family_bars(site, model["turkish_run"], (counts(model)[0], "turkish"), (counts(model)[1], "english")),
          "title": f"{label(site, model)}: {counts(model)[0]:,} right only in Turkish, {counts(model)[1]:,} right only in "
                   f"English; exact McNemar {bp.p_text(model['paired']['p'])}, Holm-adjusted {bp.p_text(model['paired']['p_holm'])}"}
         for model in tested],
        '<span><i class="swatch swatch-turkish"></i>Right only in Turkish, the upper bar</span> '
        '<span><i class="swatch swatch-english"></i>Right only in English, the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["turkish_run"]] for model in tested]) + " "
        f"<span>{verdict}</span>",
        top=4 * quarter, tick=lambda value: f"{value:,.0f}", head=TR_EN)
    return (f'<section class="charts" aria-label="Charts" {shown(group)}>'
            f"{accuracy}{paired}</section>")


def limit_note(translator: str, method: str) -> str:
    """The translation check's limit in full, among the notes on both English pages (the method gives it in full)."""
    return (f'<p class="limit"><strong>Limit:</strong> {esc(translator)} translated the questions and flagged those whose '
            "answer depends on Turkish wording. No person checked the translations or the flags, so an error could move a "
            f'setup\'s English accuracy (<a href="{method}">Our method</a>).</p>')


def limit_line(method: str) -> str:
    """The translation check's limit in one line, under the accuracy charts of both English pages (limit_note in their notes)."""
    return ('<p class="limit"><strong>Limit:</strong> a model translated the questions and no person checked them '
            f'(<a href="{method}">Our method</a>).</p>')


def experiments_note(site: Site, path: str) -> str:
    """The experiments line beside the ranking (site.experiments), in About's notes on both English pages."""
    line = experiments(site.results, path)
    return f'<p class="note experiments">{line}</p>' if line else ""


def against_verdict(model: dict[str, Any], reference: str) -> str:
    """A model's verdict against the reference: too close to call unless its Holm-adjusted p is below SIGNIFICANT, then
    behind or ahead by which of the two got more questions right that the other did not."""
    if model["p_holm"] >= SIGNIFICANT:
        return "too close to call"
    return f"behind {reference}" if model["reference_only_right"] > model["other_only_right"] else f"ahead of {reference}"


def check_against(site: Site, data: dict[str, Any], against: dict[str, Any]) -> None:
    """english_reading.against_reference, among the decision models only: the reference is the first decision model and
    its first English run, the others are the other decision models in order with their first English runs, on the kept
    questions; p fits under its Holm p; each significant row has a side ahead."""
    problems = []
    decision = group_models(site, data, "decision")
    first, others = decision[0], decision[1:]
    if (against["reference"], against["reference_run"]) != (first["name"], first["runs"][0]):
        problems.append("the reference is not the first decision model's first English run")
    if against["questions"] != data["questions"]:
        problems.append("the questions are not the kept questions")
    models = against["models"]
    if [(model["name"], model["run"]) for model in models] != [(model["name"], model["runs"][0]) for model in others]:
        problems.append("the models are not the other decision models with their first English runs, in order")
    for model in models:
        if not (0 <= model["p"] <= model["p_holm"] <= 1):
            problems.append(f"{model['name']}: p {model['p']} and Holm p {model['p_holm']} do not fit")
        if model["reference_only_right"] + model["other_only_right"] > against["questions"]:
            problems.append(f"{model['name']}: more questions right on one side only than questions")
        if model["p_holm"] < SIGNIFICANT and model["reference_only_right"] == model["other_only_right"]:
            problems.append(f"{model['name']}: significant with neither side ahead, outside the verdict rule")
    if problems:
        raise SystemExit("english_reading against_reference:\n  " + "\n  ".join(problems))


def against_reference(site: Site, data: dict[str, Any]) -> str:
    """The reference model's first English run against each other compared model's first English run on the kept
    questions (results.json english_reading.against_reference): the questions only one of the two got right, exact
    McNemar p, Holm p over the family, the verdict; ordered by p, highest first."""
    against = data.get("against_reference")
    if not against:
        return ""
    check_against(site, data, against)
    by_run = {model["runs"][0]: model for model in group_models(site, data, "decision")}
    reference = against["reference"]
    short = reference.removeprefix("Liquid ")
    total, family = against["questions"], len(against["models"])
    models = sorted(against["models"], key=lambda model: (-model["p"], label(site, by_run[model["run"]]).casefold()))
    heads = ("Run", f"Only {short} right", "Only the other right", "p", "Holm p", "Verdict")
    notes = ("first English run", "the other not right", f"{short} not right", "exact McNemar", f"over the {family}",
             f"by Holm p, {SIGNIFICANT:g}")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in zip(heads, notes))
    labels = [f"{name} ({note})" for name, note in zip(heads, notes)]
    verdicts = {model["name"]: against_verdict(model, short) for model in models}
    rows = []
    for model in models:
        compared = by_run[model["run"]]
        run = site.by_id[compared["turkish_run"]]
        name = (f'<td class="model">{site.icon(run)}{name_html(site, run, href(site, compared), site.detail(run))}'
                f'</td>')
        values = [
            run_span([model["run"]]),
            f"{model['reference_only_right']:,}",
            f"{model['other_only_right']:,}",
            esc(bp.p_text(model["p"]).removeprefix("p = ").removeprefix("p ")),
            esc(bp.p_text(model["p_holm"]).removeprefix("p = ").removeprefix("p ")),
            esc(verdicts[model["name"]]),
        ]
        rows.append(f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(text, value) for text, value in zip(labels, values)) + "</tr>")
    tally = Counter(verdicts.values())
    close, behind, ahead = (tally["too close to call"], tally[f"behind {short}"], tally[f"ahead of {short}"])
    parts = [f"{bp.in_words(close)} {'is' if close == 1 else 'are'} too close to call"]
    if behind:
        parts.append(f"{bp.in_words(behind)} {'is' if behind == 1 else 'are'} behind it")
    if ahead:
        parts.append(f"{bp.in_words(ahead)} {'is' if ahead == 1 else 'are'} ahead of it")
    summary = (f"<p><strong>In English, against {esc(reference)}, {joined(parts)}</strong> (of the {bp.in_words(family)} "
               f"other decision models, after Holm's correction).</p>")
    return (f'<section class="card" id="against-reference"><h2>{esc(reference)} against each decision model in English</h2>'
            f"{summary}"
            f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="note">Ordered by p, highest first. On the {total:,} kept reading questions, {esc(reference)}\'s '
            f"first English run (run {against['reference_run']}) against each other decision model's first English run: "
            "the exact McNemar test on the questions only one of the two got right, with p adjusted by Holm's method over "
            f"the {bp.in_words(family)} decision models. Verdict: too close to call when the Holm-adjusted p is "
            f"{SIGNIFICANT:g} or more; otherwise behind {esc(short)} when {esc(reference)} has more questions only "
            "it got right, ahead of it when the other model has more. Each model's name links its model page's English "
            'section, as in the tables above; <a href="#chart-paired">Paired test</a> compares each model with itself in '
            "Turkish.</p>"
            "</section>")


def ranks(models: list[dict[str, Any]], side: str) -> dict[int, int]:
    """Each setup's place by right answers in one language among these setups, 1, 2, 3 without repeats (1 = most right;
    Zeki #4630); setups with as many right keep their order in `models`, the table's, which claims no difference; by
    Turkish run."""
    ordered = sorted(models, key=lambda model: -model[side]["right"])
    return {model["turkish_run"]: place for place, model in enumerate(ordered, 1)}


def languages_text(text: str) -> str:
    """page_config.json's model_languages text as HTML, one `...` span as code."""
    return "<code>".join(esc(text).split("`", 1)).replace("`", "</code>", 1) if text.count("`") == 2 else esc(text)


def english_only_list(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the short list of its English-only setups (english_only: no Text tab run, so no Turkish side and
    no paired test), each with its English accuracy and Turkish Not run, linked to its row on the English reading page;
    nothing when the group has none."""
    digits = site.config["percent_digits"]
    alone = [model for model in english_only(data) if site.in_group(setup_run(site, model), group)]
    if not alone:
        return ""
    running = turkish_running(site, data)
    items = joined([f'<a href="{href(site, model)}">{esc(label(site, model))}</a>: English '
                    f'{pct(model["english"]["accuracy"], digits)} ({model["english"]["right"]:,} of {data["questions"]:,} '
                    f"right), Turkish {'still running' if model['model'] in running else 'Not run'}" for model in alone])
    return (f'<p class="note" {shown(group)}>English-only setups (no Turkish run, so in no paired test and no Holm '
            f"adjustment): {items}.</p>")


def main_table(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the face's main table: each of its setups in one row, ordered by Turkish accuracy: accuracy in
    Turkish and in English and the difference; for the all and decision groups, with “I don't know” in both languages
    (english_reading.dont_know_word), Answered and Wrong of answers in each, then the non-hallucination rate in each
    and the difference, and the published comparison's Turkish side with “Bilmiyorum” (english_reading.dont_know) in
    one column (Running for a chat model's run still running, Not run for a decision model without one); the rank by accuracy among the group's setups
    in each language, and, but for the chat group, the languages the model card lists (page_config.json's
    model_languages; Not checked without an entry). Every number from results.json's english_reading; * marks a
    difference whose paired test has a Holm-adjusted p below SIGNIFICANT."""
    digits = site.config["percent_digits"]
    idk = data.get("dont_know") or {}
    word = data.get("dont_know_word") if group != "chat" else None
    matched = {model["text_run"]: model for model in idk.get("models", [])}
    same_word = {model["text_run"]: model for model in (word or {}).get("models", [])}
    # Turkish "Bilmiyorum" outside the published comparison: coverage's native point (the Hallucination tab run).
    native_bilmiyorum = {model["text_run"]: next(point for point in model["native"]
                                                 if point["language"] == "Turkish" and point["wording"] == "Bilmiyorum")
                         for model in (data.get("coverage") or {}).get("models", [])}
    listed = {model["run"]: model for model in site.config["model_languages"]["models"]}
    with_languages = group != "chat"
    group_setups = group_models(site, data, group)
    models = sorted(group_setups, key=lambda model: (-model["turkish"]["accuracy"], label(site, model).casefold()))
    turkish_rank, english_rank = ranks(models, "turkish"), ranks(models, "english")
    total = data["questions"]
    option = (word or {}).get("option", "")
    difference_note = "points higher in English than in Turkish (negative: higher in Turkish)"
    bilmiyorum = "Turkish with “Bilmiyorum”"
    bilmiyorum_note = "wrong of answers, lower is better; answered and non-hallucination under it"
    # (group, its columns, the note under each column); a group of one column without a name spans both header rows.
    groups: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        ("Accuracy", ("Turkish", "English", "Difference"), ("higher is better",) * 2 + (difference_note,))]
    if word:
        groups += [
            (f"Answered with “{option}”", ("Turkish", "English"), (f"(right + wrong) / {total:,}; higher is better",) * 2),
            (f"Wrong of answers with “{option}”", ("Turkish", "English"), ("wrong / (right + wrong); lower is better",) * 2),
            (f"Non-hallucination with “{option}”", ("Turkish", "English", "Difference"),
             (f"“{option}” / (“{option}” + wrong); higher is better",) * 2
             + ("non-hallucination points higher in English than in Turkish (negative: higher in Turkish)",)),
            (bilmiyorum, ("",), (bilmiyorum_note,))]
    groups += [("Cost", ("Turkish", "English"), ("$ per 1,000 questions; lower is better",) * 2),
               ("Latency", ("Turkish", "English"), ("median seconds per request; lower is better",) * 2),
               ("Rank by accuracy", ("Turkish", "English"), (f"among the {len(models)}; lower is better",) * 2)]
    heads = [f"{part} {name} ({note})" if name else f"{part} ({note})"
             for part, names, notes in groups for name, note in zip(names, notes)]
    if with_languages:
        heads.append("Languages the model card lists")
    # The option-word check (“I don't know” in Turkish) was run for decision models only.
    word_missing = f'{NOT_RUN}<span class="small">decision models only</span>'

    def answered(counts: dict[str, Any]) -> str:
        count = counts["right"] + counts["wrong"]
        return f'{pct(counts["attempt_rate"], digits)}<span class="small">{count:,} of {total:,} answered</span>'

    def rate(counts: dict[str, Any]) -> str:
        value = counts["non_hallucination"]
        return (f'{NO_RATE if value is None else pct(value, digits)}<span class="small">{counts["dont_know"]:,} '
                f'“{esc(option)}” of {counts["dont_know"] + counts["wrong"]:,} not right</span>')

    rows = []
    for model in models:
        values = [pct(model["turkish"]["accuracy"], digits), pct(model["english"]["accuracy"], digits),
                  f"{100 * model['difference']:+.{digits}f}{' *' if significant(model) else ''}"]
        if word:
            entry = same_word[model["turkish_run"]]
            sides = [entry["turkish"], entry["english"]]
            # A missing English side: Running for a chat model, Not run for a decision model; a missing Turkish side
            # (the option-word run): Not run.
            gaps = [word_missing, missing_side(site, site.by_id[model["turkish_run"]])]
            values += [gap if side is None else answered(side) for side, gap in zip(sides, gaps)]
            values += [gap if side is None else wrong_of_answers(side, digits) for side, gap in zip(sides, gaps)]
            values += [gap if side is None else rate(side) for side, gap in zip(sides, gaps)]
            tr, en = (None if side is None else side["non_hallucination"] for side in sides)
            values.append(NO_RATE if sides[0] is not None and sides[1] is not None and (tr is None or en is None) else
                          gaps[0] if sides[0] is None else gaps[1] if sides[1] is None else
                          f"{100 * (en - tr):+.{digits}f}{' *' if idk_significant(entry) else ''}")
            other = matched.get(model["turkish_run"])
            point = native_bilmiyorum.get(model["turkish_run"])
            if other is not None:
                counts = other["turkish"]
                values.append(f'{wrong_of_answers(counts, digits)}<span class="small">answered '
                              f'{pct(counts["attempt_rate"], digits)}, non-hallucination '
                              f'{rate_text(counts["non_hallucination"], digits)}</span>')
            elif point is not None and point["run"] is not None:
                held = point["abstained"] + point["wrong"]
                values.append(f'{wrong_of_answers(point, digits)}<span class="small">answered '
                              f'{pct(point["coverage"], digits)}, non-hallucination '
                              f'{rate_text(point["abstained"] / held if held else None, digits)}</span>')
            else:
                values.append(missing_side(site, site.by_id[model["turkish_run"]]))
        values += [measure_cell(site, model, measure, side) for measure in ("cost", "latency") for side in SIDES]
        values += [str(turkish_rank[model["turkish_run"]]), str(english_rank[model["turkish_run"]])]
        entry = listed.get(model["turkish_run"])
        if with_languages and entry is None:
            values.append('<span class="nm">Not checked</span>')
        elif with_languages:
            source = esc(entry["source"].split("//", 1)[1].split("/", 1)[0])
            values.append(f'{languages_text(entry["languages"])}<span class="small"><a href="{esc(entry["source"])}">{source}</a></span>')
        run = site.by_id[model["turkish_run"]]
        name = f'<td class="model">{site.icon(run)}{name_html(site, run, href(site, model), site.detail(run))}</td>'
        rows.append(f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>")
    short = "".join(f'<th scope="col" class="num">{name}<span class="small">{cost_unit_in(esc(note))}</span></th>'
                    for part, names, notes in groups if names != ("",) for name, note in zip(names, notes))
    head = ('<tr><th scope="col" rowspan="2">Model</th>'
            + "".join(f'<th scope="col" rowspan="2" class="num">{esc(part)}<span class="small">{esc(notes[0])}</span></th>'
                      if names == ("",) else f'<th scope="colgroup" colspan="{len(names)}">{esc(part)}</th>'
                      for part, names, notes in groups)
            + ('<th scope="col" rowspan="2">Languages the model card lists<span class="small">and its source</span></th>'
               if with_languages else "")
            + f"</tr><tr>{short}</tr>")
    if word:
        family = sum(1 for entry in word["models"] if entry["paired"])
        idk_text = (f" The “{esc(option)}” columns: each model's first English run with “{esc(option)}” against its Turkish "
                    f"run with the option also written “{esc(option)}” (the Hallucination tab's option-word run, counted on "
                    "these questions), so only the language differs (<a href=\"#dont-know-word\">Only the language "
                    f"differs</a>). Answered: (right + wrong) / {total:,}; Wrong of answers: wrong / (right + wrong); "
                    f"Non-hallucination: “{esc(option)}” / (“{esc(option)}” + wrong); the difference's paired test is of "
                    f"wrong answers, with p adjusted by Holm's method over the {bp.in_words(family)} model"
                    f"{'' if family == 1 else 's'} with both runs. {bilmiyorum}: the Turkish side of the published "
                    "comparison with “Bilmiyorum”"
                    + (' (<a href="#dont-know">With “I don\'t know”</a>)' if idk else "")
                    + " or, for a model outside it, its Hallucination tab run counted on these questions; its wrong of "
                    "answers with its answered share and non-hallucination rate under it. Not run: no such run for a "
                    "decision model (the Turkish “I don't know” run is for decision models only); Running: a chat model's "
                    "run still running.")
    else:
        idk_text = ""
    languages_note = (" Languages: what each model's card or its maker's docs list, with the source (<a href=\"#languages\">"
                      "Languages the model cards list</a>); Not checked: no card checked yet." if with_languages else "")
    return (f'<section class="card" id="{anchor("main-table", group)}" {shown(group)}><h2>Turkish vs English</h2>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead>{head}'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="note">Ordered by Turkish accuracy, highest first. * marks a difference that is significant after '
            f"Holm's correction: its paired test (the exact McNemar test, with p adjusted by Holm's method over all "
            f"{len(data['models'])} English {noun('all', len(data['models']))}) has a Holm-adjusted p below {SIGNIFICANT:g}. "
            f"Accuracy: right answers over the {total:,} kept reading questions, the first English run against the Text "
            f'tab run (<a href="#{anchor("chart-accuracy", group)}">Accuracy</a>, '
            f'<a href="#{anchor("chart-paired", group)}">Paired test</a>).{idk_text} Cost and latency: the Text tab run '
            f"and the first English run, cost in $ {cost_per()} and the "
            "median time per request with the request size and the requests in flight under it "
            f'(<a href="#{anchor("chart-cost", group)}">Cost</a>, <a href="#{anchor("chart-latency", group)}">Latency</a>).'
            + (" " + missing_note(site, models, tuple(SIDES))).rstrip() + " Rank: by accuracy among the "
            f"{len(models)} {noun(group, len(models))} in each language, 1 the most accurate, tied setups sharing a rank."
            f'{languages_note} The full tables are under <a href="#info">Info</a>.'
            + "</p>"
            f'<p class="note">{esc(cost_note(site, models, tuple(SIDES)))}</p></section>')


def columns(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: header and what it holds."""
    family = len(data["models"])
    return (
        ("English runs", "the first is compared; answers changed between runs where more than one"),
        ("Turkish runs", "the Text tab run, then its repeats; answers changed between them"),
        ("Turkish accuracy", "the Text tab run on the kept questions; range over its runs; higher is better"),
        ("English accuracy", "the first English run; range over its runs; higher is better"),
        ("Difference", "points higher in English than in Turkish"),
        ("Right only in English", "questions the English run got right and the Turkish run did not"),
        ("Right only in Turkish", "questions the Turkish run got right and the English run did not"),
        ("p", "exact McNemar"),
        ("Holm p", f"adjusted over all {family} English {noun('all', family)}"),
    )


def row(site: Site, data: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    total = data["questions"]
    spread = model["spread"] or {}
    changed = model["answers_changed"] or {}

    def runs(side: str, numbers: list[int]) -> str:
        count = changed.get(side)
        return run_span(numbers) + ("" if count is None else
                                    f'<span class="small">{count:,} answer{"" if count == 1 else "s"} changed between runs</span>')

    def accuracy(side: str) -> str:
        counts, span = model[side], spread.get(side)
        invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
        text = f'{pct(counts["accuracy"], digits)}<span class="small">{counts["right"]:,} of {total:,} right{invalid}</span>'
        if span and span["low"] == span["high"]:
            text += '<span class="small">the same in every run</span>'
        elif span:
            text += f'<span class="small">range {pct(span["low"], digits)} to {pct(span["high"], digits)}</span>'
        return text

    paired = model["paired"]
    values = [
        runs("english", model["runs"]),
        runs("turkish", model["turkish_runs"]),
        accuracy("turkish"),
        accuracy("english"),
        f"{100 * model['difference']:+.{digits}f}",
        f"{paired['english_only_right']:,}",
        f"{paired['turkish_only_right']:,}",
        esc(bp.p_text(paired["p"]).removeprefix("p = ").removeprefix("p ")),
        esc(bp.p_text(paired["p_holm"]).removeprefix("p = ").removeprefix("p ")) + (" *" if significant(model) else ""),
    ]
    heads = [f"{head} ({note})" for head, note in columns(data)]
    run = site.by_id[model["turkish_run"]]
    name = f'<td class="model">{site.icon(run)}{name_html(site, run, href(site, model), site.detail(run))}</td>'
    return f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>"


def table(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the Results table, its setups by English right answers."""
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in columns(data))
    rows = "".join(row(site, data, model) for model in group_models(site, data, group))
    return (f'<div class="table-wrap" {shown(group)}><table class="board list stack idk"><thead><tr><th scope="col">Model'
            f"</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>")


def not_run_list(site: Site, data: dict[str, Any], group: str) -> str:
    """A group's copy of the Text tab setups without an English run (not_run): each reason once with its setups, each
    by its official name and tag, linking its model page (setup_href: no English section)."""
    entries = [(reason, [run for run in runs if site.in_group(run, group)]) for reason, runs in not_run(site, data)]
    count = sum(len(runs) for _, runs in entries)
    total = sum(1 for run in site.runs if site.in_group(run, group))
    if count:
        items = "".join(
            "<li>" + joined([f'<a href="{setup_href(site, PATH, run["run"])}">{esc(site.title(run))}</a>{tag_html(site.tag(run))}'
                             for run in runs])
            + f": {esc(reason)}</li>" for reason, runs in entries if runs)
        text = (f"<p>{bp.opening_count(count)} of the Text tab's {total:,} {noun(group, total)} "
                f"{'has' if count == 1 else 'have'} no English run yet, each with its reason:</p><ul>{items}</ul>")
    else:
        text = f"<p>Each of the Text tab's {total:,} {noun(group, total)} has an English run.</p>"
    return (f'<div id="{anchor("not-run", group)}" {shown(group)}><h3 class="board-group">Without an English run</h3>'
            f"{text}</div>")


def reason_name(key: str) -> str:
    return key.replace("_", " ")


def units_text(record: dict[str, Any]) -> str:
    units = sorted({question["unit"] for question in record["questions"]})
    if units != list(range(units[0], units[-1] + 1)):
        return "units " + joined([str(unit) for unit in units])
    return f"units {units[0]} to {units[-1]}"


def runs_text(site: Site, data: dict[str, Any]) -> str:
    """How many English runs each model has, from the data: the models with more than one named, by count."""
    by_count: dict[int, list[str]] = {}
    for model in data["models"]:
        by_count.setdefault(len(model["runs"]), []).append(esc(label(site, model)))
    parts = [f"{bp.in_words(count)} run{'' if count == 1 else 's'} for {joined(names)}"
             for count, names in sorted(by_count.items(), reverse=True) if count > 1]
    if 1 in by_count:
        single = len(by_count[1])
        parts.append(f"one for the other {bp.in_words(single)}" if parts else "one for each")
    return "; ".join(parts)


def renamed_text(site: Site, data: dict[str, Any]) -> str:
    """The models asked in English under another model ID than their Turkish runs, each with its reason."""
    sentences = []
    for model in data["models"]:
        run = site.by_id[model["turkish_run"]]
        if model["model"] != run["model"]:
            sentences.append(f" {esc(label(site, model))} was asked as <code>{esc(model['model'])}</code>, while its Turkish "
                             f"runs used <code>{esc(run['model'])}</code>, because "
                             f"{esc(RENAMED[(run['provider'], run['model'], model['model'])])}.")
    return "".join(sentences)


def check_dont_know(site: Site, data: dict[str, Any], idk: dict[str, Any]) -> None:
    """Stops the build when results.json's english_reading.dont_know does not add up: each side's answers cover the
    kept questions, its rates are its counts, the paired counts give the difference in wrong answers, the first run is
    the one compared, and every model is one of the accuracy comparison's."""
    problems = []
    total = idk["questions"]
    if total != data["questions"]:
        problems.append(f"{total} questions, the accuracy comparison {data['questions']}")
    compared = {model["turkish_run"]: model for model in data["models"]}
    close = lambda a, b: a is not None and abs(a - b) < 1e-9  # noqa: E731
    for model in idk["models"]:
        name = model["name"]
        other = compared.get(model["text_run"])
        if other is None:
            problems.append(f"{name}: Text tab run {model['text_run']} is not in the accuracy comparison")
            continue
        if name != other["name"] or model["provider"] != other["provider"] or model["model"] != other["model"]:
            problems.append(f"{name}: not the model of the accuracy comparison's run {model['text_run']}")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["dont_know"] + counts["invalid"] != total:
                problems.append(f"{name}: its {side} answers do not add up to {total}")
            if not close(counts["accuracy"], counts["right"] / total) or \
                    not close(counts["attempt_rate"], (counts["right"] + counts["wrong"]) / total):
                problems.append(f"{name}: its {side} accuracy or attempt rate is not its counts")
            unsure = counts["dont_know"] + counts["wrong"]
            if (counts["non_hallucination"] is None) != (unsure == 0) or \
                    (unsure and not close(counts["non_hallucination"], counts["dont_know"] / unsure)):
                problems.append(f"{name}: its {side} non-hallucination rate is not its counts")
            if not counts["runs"] or counts["runs"][0] != counts["run"]:
                problems.append(f"{name}: the first {side} run is not the one compared")
        paired = model["paired"]
        if paired["english_only_wrong"] - paired["turkish_only_wrong"] != model["english"]["wrong"] - model["turkish"]["wrong"]:
            problems.append(f"{name}: the paired counts do not give the difference in wrong answers")
        if paired["english_only_wrong"] > model["english"]["wrong"] or paired["turkish_only_wrong"] > model["turkish"]["wrong"]:
            problems.append(f"{name}: more wrong answers only on one side than on that side")
        if not (0 <= paired["p"] <= paired["p_holm"] <= 1):
            problems.append(f"{name}: p {paired['p']} and Holm p {paired['p_holm']} do not fit")
        if model["english"].get("subset"):
            problems.append(f"{name}: the English side is marked as a subset run")
    paired_runs = {model["text_run"] for model in idk["models"]}
    for model in idk["models"] + english_only(idk) + turkish_only(idk):
        run = site.by_id.get(model["text_run"]) if model["text_run"] is not None else \
            next((entry for entry in english_only(data) if entry["run"] == model.get("reading_run")), None)
        if run is None or model.get("group") != ("decision" if site.decision(run) else "chat"):
            problems.append(f"{model['name']}: its group is not its setup's")
    for model in english_only(idk):
        name, counts = model["name"], model["english"]
        other = compared.get(model["text_run"]) if model["text_run"] is not None else \
            next((entry for entry in english_only(data) if entry["run"] == model.get("reading_run")), None)
        if other is None or name != other["name"] or model["provider"] != other["provider"] or model["model"] != other["model"]:
            problems.append(f"{name}: English only, but not the model of an accuracy comparison entry or English-only "
                            f"setup (Text tab run {model['text_run']}, English run {model.get('reading_run')})")
        if model["text_run"] in paired_runs:
            problems.append(f"{name}: English only, but also among the paired models")
        if counts["right"] + counts["wrong"] + counts["dont_know"] + counts["invalid"] != total:
            problems.append(f"{name}: its English answers do not add up to {total}")
        if not close(counts["accuracy"], counts["right"] / total) or \
                not close(counts["attempt_rate"], (counts["right"] + counts["wrong"]) / total):
            problems.append(f"{name}: its English accuracy or attempt rate is not its counts")
        unsure = counts["dont_know"] + counts["wrong"]
        if (counts["non_hallucination"] is None) != (unsure == 0) or \
                (unsure and not close(counts["non_hallucination"], counts["dont_know"] / unsure)):
            problems.append(f"{name}: its English non-hallucination rate is not its counts")
        if not counts["runs"] or counts["runs"][0] != counts["run"]:
            problems.append(f"{name}: the first English run is not the one shown")
        if not model.get("reason") or (model.get("running") and model["reason"] != site.config["dont_know"]["running"]):
            problems.append(f"{name}: English only without its reason")
    for model in turkish_only(idk):
        name, counts = model["name"], model["turkish"]
        if model["text_run"] not in compared or model["text_run"] in paired_runs or not model.get("running"):
            problems.append(f"{name}: Turkish only, but not a running accuracy comparison entry outside the paired models")
        if counts["right"] + counts["wrong"] + counts["dont_know"] + counts["invalid"] != total:
            problems.append(f"{name}: its Turkish answers do not add up to {total}")
        if model["reason"] != site.config["dont_know"]["running"]:
            problems.append(f"{name}: Turkish only without its reason")
    if problems:
        raise SystemExit("english_reading dont_know:\n  " + "\n  ".join(problems))


def turkish_only(idk: dict[str, Any]) -> list[dict[str, Any]]:
    """results.json's english_reading.dont_know.turkish_only: chat models whose Hallucination tab run is published and
    whose English run with the option is still running, so in no paired test or Holm family."""
    return idk.get("turkish_only") or []


def idk_run(site: Site, model: dict[str, Any]) -> dict[str, Any]:
    """An english_reading.dont_know entry's setup as a run: its Text tab run, or its English-only setup (setup_run)."""
    if model["text_run"] is not None:
        return site.by_id[model["text_run"]]
    only = {entry["run"]: entry for entry in english_only(site.results["english_reading"])}
    return setup_run(site, only[model["reading_run"]])


def idk_group(site: Site, idk: dict[str, Any], group: str) -> dict[str, Any]:
    """english_reading.dont_know with the entries of one group of the view bar (all: every entry), by each entry's setup
    (idk_run)."""
    keep = lambda items: [model for model in items if site.in_group(idk_run(site, model), group)]  # noqa: E731
    return {**idk, "models": keep(idk["models"]), "english_only": keep(english_only(idk)), "turkish_only": keep(turkish_only(idk))}


# A side without a run: Not run for a decision model, or for a setup whose scoring cannot offer the option (with why);
# else Running, a chat model's run still running (page_config.json's dont_know.running).
RUNNING = '<span class="nm">Running</span>'
NOT_RUN = '<span class="nm">Not run</span>'
UNDEFINED = '<span class="nm">Undefined</span>'
NO_PROBABILITIES = '<span class="nm">No probabilities</span>'
# Providers whose scoring cannot offer an "I don't know" option: yes/no scoring asks about each option on its own, and
# the runner refuses --dont-know with it, so such a setup never has a run with the option.
NO_OPTION = {"vllm-yes-no": "yes/no scoring cannot offer it"}


def missing_side(site: Site, run: dict[str, Any]) -> str:
    """What a missing side with the option reads for a setup (a Text tab run, or an English-only setup's setup_run): Not
    run for a decision model, for a setup whose scoring cannot offer the option (NO_OPTION, with why) or for an
    English-only setup, else Running (a chat model's run still running)."""
    if run["provider"] in NO_OPTION:
        return f'{NOT_RUN}<span class="small">{esc(NO_OPTION[run["provider"]])}</span>'
    return NOT_RUN if site.decision(run) or run["run"] not in site.by_id else RUNNING


def idk_label(site: Site, model: dict[str, Any]) -> str:
    """An english_reading.dont_know entry's plain name (official name · tag) for text, by its setup (idk_run)."""
    return site.plain(idk_run(site, model))


def idk_href(site: Site, model: dict[str, Any]) -> str:
    if model["text_run"] is None:
        return entry_href(site, PATH, idk_run(site, model))
    return setup_href(site, PATH, model["text_run"])


def idk_significant(model: dict[str, Any]) -> bool:
    return model["paired"]["p_holm"] < SIGNIFICANT


def rate_text(value: float | None, digits: int) -> str:
    return "not measured" if value is None else pct(value, digits)


def dont_know_summary(site: Site, idk: dict[str, Any], group: str = "all") -> str:
    """One paragraph from the data: how many models had the higher non-hallucination rate in English, which paired
    differences in wrong answers are significant after Holm's correction (within each group), and the models with one
    side only (a decision model without a Turkish run, a chat model's side still running)."""
    digits = site.config["percent_digits"]
    models = idk["models"]
    total = len(models)
    rated = [model for model in models
             if model["english"]["non_hallucination"] is not None and model["turkish"]["non_hallucination"] is not None]
    higher = sum(1 for model in rated if model["english"]["non_hallucination"] > model["turkish"]["non_hallucination"])
    lower = sum(1 for model in rated if model["english"]["non_hallucination"] < model["turkish"]["non_hallucination"])
    parts = [f"{bp.opening_count(higher) if higher else 'None'} of the {bp.in_words(total)} model{'' if total == 1 else 's'} "
             f"with both runs had a higher non-hallucination rate in English than in Turkish"]
    if lower:
        parts.append(f"{bp.in_words(lower)} lower")
    if len(rated) - higher - lower:
        parts.append(f"{bp.in_words(len(rated) - higher - lower)} the same")
    if total - len(rated):
        parts.append(f"{bp.in_words(total - len(rated))} without a rate on one side")
    found = [model for model in models if idk_significant(model)]
    holm = "Holm's correction" + (" within each group (decision models, chat models)"
                                   if len({model["group"] for model in models}) > 1 else "")
    if not found:
        verdict = f"none of the differences in wrong answers is significant after {holm}, so each could be chance"
    else:
        named = joined([f"{esc(idk_label(site, model))} (more wrong answers in "
                        f"{'English' if model['paired']['english_only_wrong'] > model['paired']['turkish_only_wrong'] else 'Turkish'})"
                        for model in found])
        verdict = (f"{bp.in_words(len(found))} of the {bp.in_words(total)} differences in wrong answers "
                   f"{'is' if len(found) == 1 else 'are'} significant after {holm}: {named}")
    alone = ""
    for model in english_only(idk):
        if model.get("running"):
            continue
        counts = model["english"]
        alone += (f" {esc(idk_label(site, model))} has an English rate of {rate_text(counts['non_hallucination'], digits)} "
                  f"({counts['dont_know']:,} “{esc(idk['option'])}” of {counts['dont_know'] + counts['wrong']:,} not right) "
                  f"with an attempt rate of {pct(counts['attempt_rate'], digits)} ({counts['right'] + counts['wrong']:,} "
                  f"answered) but no Turkish run with the option on these questions, so no comparison or test.")
    for language, entries in (("Turkish", [model for model in english_only(idk) if model.get("running")]),
                              ("English", turkish_only(idk))):
        if entries:
            alone += (f" Still running in {language}, so charted with one side and in no test: "
                      f"{esc(joined([idk_label(site, model) for model in entries]))}.")
    if not models:
        return f"<p>No model in this group has both runs yet.{alone}</p>"
    return (f"<p>{'; '.join(parts)}; {verdict} (<a href=\"#{anchor('chart-idk-paired', group)}\">Paired test</a>).{alone} "
            "Read each rate with its attempt rate: a model that always chose the option would reach 100%.</p>")


def dont_know_charts(site: Site, idk: dict[str, Any], group: str = "all") -> str:
    """A group's copy of the section's two chart cards: the non-hallucination rate in Turkish and in English (attempt
    rates in the text and tooltip; a chat model's side still running reads Running, its other side charted alone) and
    the paired test of wrong answers (as the Hallucination tab's #chart-paired), every number from results.json's
    english_reading.dont_know. The Hallucination tab shows them too, for the decision models (sitebuild/dont_know.py)."""
    digits = site.config["percent_digits"]
    total = idk["questions"]
    models = idk["models"]

    def card(base: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor(base, group)}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    def side_title(model: dict[str, Any], side: str, language: str, word: str) -> str:
        counts = model.get(side)
        if counts is None:
            return f"{language} still running"
        return (f"{language} {rate_text(counts['non_hallucination'], digits)} ({counts['dont_know']:,} “{word}” "
                f"of {counts['dont_know'] + counts['wrong']:,} not right), attempt rate {pct(counts['attempt_rate'], digits)}")

    def side_text(model: dict[str, Any], side: str) -> str:
        counts = model.get(side)
        return "Running" if counts is None else rate_text(counts["non_hallucination"], digits)

    def side_value(model: dict[str, Any], side: str) -> float:
        counts = model.get(side)
        return 0 if counts is None else counts["non_hallucination"] or 0

    def attempt(model: dict[str, Any], side: str) -> str:
        counts = model.get(side)
        return "running" if counts is None else pct(counts["attempt_rate"], digits)

    alone = [esc(idk_label(site, model)) for model in english_only(idk) if not model.get("running")]
    not_charted = (f" <span>Not charted, with no Turkish run with the option on these questions: {joined(alone)} (in "
                   "the table under Info).</span>") if alone else ""
    running = [model for model in english_only(idk) if model.get("running")]
    # The paired models and the running ones in English by the English rate, then the running ones in Turkish only.
    charted = sorted(models + running, key=lambda model: (model["english"]["non_hallucination"] is None,
                                                          -(model["english"]["non_hallucination"] or 0),
                                                          idk_label(site, model).casefold())) + turkish_only(idk)
    running_note = (f" <span>Running: {esc(site.config['dont_know']['running'].removeprefix('Running: '))}</span>"
                    if running or turkish_only(idk) else "")
    rates = card(
        "chart-idk-rates", "Non-hallucination rate in Turkish and in English",
        f"The option among the answers that were not right, on the {total:,} kept questions: each model's first run in each "
        "language, ordered by the English rate · higher is better, read with the attempt rate (under the chart and in "
        "each bar's tooltip)",
        [{"label": site.title(idk_run(site, model)), "tag": site.tag(idk_run(site, model)),
          "family": site.families[model["text_run"]]["name"], "href": idk_href(site, model),
          "class_key": site.model_class(idk_run(site, model)),
          "text": f"{side_text(model, 'turkish')} · {side_text(model, 'english')}",
          "bars": family_bars(site, model["text_run"], (side_value(model, "turkish"), "turkish"),
                              (side_value(model, "english"), "english")),
          "title": f"{idk_label(site, model)}: {side_title(model, 'turkish', 'Turkish', idk['option'])}; "
                   f"{side_title(model, 'english', 'English', idk['option'])}"}
         for model in charted],
        '<span><i class="swatch swatch-turkish"></i>Turkish option, the upper bar</span> '
        '<span><i class="swatch swatch-english"></i>English option, the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["text_run"]] for model in charted]) + " "
        "<span>Attempt rate, Turkish · English: "
        + esc("; ".join(f"{idk_label(site, model)} {attempt(model, 'turkish')} · {attempt(model, 'english')}" for model in charted))
        + ". A model that always chose the option would reach 100% with no right answers.</span>" + running_note + not_charted,
        head=TR_EN)
    if not models:
        return f'<section class="charts" aria-label="Charts with “I don\'t know”">{rates}</section>'
    tested = sorted(models, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"], idk_label(site, model).casefold()))
    counts = lambda model: (model["paired"]["turkish_only_wrong"], model["paired"]["english_only_wrong"])  # noqa: E731
    most = max(max(counts(model)) for model in tested)
    # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    found = [model for model in tested if idk_significant(model)]
    others = [model for model in tested if not idk_significant(model)]

    def adjusted(group: list[dict[str, Any]]) -> str:
        texts = [esc(bp.p_text(model["paired"]["p_holm"])) for model in group]
        return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below {SIGNIFICANT:g}): "
                f"{esc(joined([idk_label(site, model) for model in found]))} ({adjusted(found)}).") if found else
               f"No difference is significant (Holm-adjusted p below {SIGNIFICANT:g}).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if found else f" Adjusted: {adjusted(others)}."
    paired = card(
        "chart-idk-paired", "Wrong only in Turkish, or only in English?",
        f"Each model's first run in each language, both with the option, on the {total:,} kept questions: the questions only "
        f"one of the two got wrong, by the exact McNemar test with p adjusted by Holm's method "
        + ("within each group (decision models, chat models)" if len({model["group"] for model in tested}) > 1 else
           f"over the {'decision' if tested[0]['group'] == 'decision' else 'chat'} models")
        + " · the shorter bar is the language with fewer wrong answers",
        [{"label": site.title(idk_run(site, model)), "tag": site.tag(idk_run(site, model)),
          "family": site.families[model["text_run"]]["name"], "href": idk_href(site, model),
          "class_key": site.model_class(idk_run(site, model)),
          "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if idk_significant(model) else ''}",
          "bars": family_bars(site, model["text_run"], (counts(model)[0], "turkish"), (counts(model)[1], "english")),
          "title": f"{idk_label(site, model)}: {counts(model)[0]:,} wrong only in Turkish, {counts(model)[1]:,} wrong only "
                   f"in English; exact McNemar {bp.p_text(model['paired']['p'])}, Holm-adjusted {bp.p_text(model['paired']['p_holm'])}"}
         for model in tested],
        '<span><i class="swatch swatch-turkish"></i>Wrong only in Turkish, the upper bar</span> '
        '<span><i class="swatch swatch-english"></i>Wrong only in English, the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["text_run"]] for model in tested]) + " "
        f"<span>{verdict}</span>" + not_charted,
        top=4 * quarter, tick=lambda value: f"{value:,.0f}", head=TR_EN)
    return f'<section class="charts" aria-label="Charts with “I don\'t know”">{rates}{paired}</section>'


def dont_know_face(site: Site, idk: dict[str, Any], word: dict[str, Any] | None, group: str = "all") -> str:
    """A group's copy of the section's face: a heading and summary, a sentence pointing to the same comparison with “I
    don't know” in both languages (dont_know_word_face, decision models) when results.json has it, then its two chart
    cards (dont_know_charts)."""
    option = esc(idk["option"])
    total = idk["questions"]
    pointer = (f"<p>With the option written “{esc(word['option'])}” in Turkish too, so that only the language differs, "
               'the decision models\' comparison is in the <a href="#dont-know-word">next section</a>.</p>') \
        if word and group in ("all", "decision") else ""
    return (f'<div {shown(group)}><section class="card" id="{anchor("dont-know", group)}"><h2>With an “I don\'t know” option</h2>'
            f"<p>The same {total:,} kept questions with a sixth option, “{option}”, in English and in Turkish, as "
            f'on the <a href="{rel(PATH, "dont-know/")}">Hallucination tab</a>, asked of the same models '
            f'(<a href="#dont-know-method">how</a>).</p>{dont_know_summary(site, idk, group)}{pointer}</section>'
            f"{dont_know_charts(site, idk, group)}</div>")


def dont_know_columns(idk: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: each language's non-hallucination rate, answered share and error rate side
    by side first, English then Turkish, so a phone's first view of the frame shows them with the model (Ümit #4665,
    Logic & Math's labels and order), then the runs, accuracy, the option's mean probability and the paired test."""
    families = Counter(model["group"] for model in idk["models"])
    holm = "; ".join(f"over the {count} {kind} model{'' if count == 1 else 's'}" for kind, count in sorted(families.items(), reverse=True))
    option = idk["option"]
    return (
        ("English non-hallucination", f"of answers not right, % “{option}” · higher is better, read with the answered share"),
        ("English answered", f"not “{option}”: (right + wrong) / {idk['questions']:,}"),
        ("English error rate", "of its answers: wrong / (right + wrong) · lower is better"),
        ("Turkish non-hallucination", "of answers not right, % the Turkish option · higher is better, read with the answered share"),
        ("Turkish answered", f"not the Turkish option: (right + wrong) / {idk['questions']:,}"),
        ("Turkish error rate", "of its answers: wrong / (right + wrong) · lower is better"),
        ("English runs", "with “I don't know”; the first is compared"),
        ("Turkish runs", "with the Turkish option; the first is compared"),
        ("English accuracy", "higher is better"),
        ("Turkish accuracy", "higher is better"),
        ("English mean probability", f"of “{option}”"),
        ("Turkish mean probability", "of the Turkish option"),
        ("Wrong only in English", "questions the English run got wrong and the Turkish run did not"),
        ("Wrong only in Turkish", "questions the Turkish run got wrong and the English run did not"),
        ("p", "exact McNemar"),
        ("Holm p", f"adjusted {holm or 'over none'}"),
    )


def wrong_of_answers(counts: dict[str, Any], digits: int) -> str:
    """Wrong / (right + wrong) with its counts, from the published counts; Undefined with no answer."""
    answered = counts["right"] + counts["wrong"]
    if not answered:
        return f'{UNDEFINED}<span class="small">no answers</span>'
    return f'{pct(counts["wrong"] / answered, digits)}<span class="small">{counts["wrong"]:,} of {answered:,}</span>'


def dont_know_row(site: Site, idk: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    total = idk["questions"]
    spread = model["spread"] or {}

    def span(side: str, key: str) -> str:
        values = (spread.get(side) or {}).get(key)
        if not values or values[0] is None:
            return ""
        if values[0] == values[1]:
            return '<span class="small">the same in every run</span>'
        return f'<span class="small">range {pct(values[0], digits)} to {pct(values[1], digits)}</span>'

    def value(side: str, key: str, note: str) -> str:
        number = model[side][key]
        shown = NO_RATE if number is None else pct(number, digits)
        return f'{shown}<span class="small">{note}</span>{span(side, key)}'

    def runs(side: str) -> str:
        counts = model[side]
        if side == "english":
            source = "new runs" if len(counts["runs"]) > 1 else "a new run"
        elif counts.get("subset"):
            source = "new runs on the kept questions" if len(counts["runs"]) > 1 else "a new run on the kept questions"
        else:
            source = "the Hallucination tab's full runs, counted on the kept questions"
        return run_span(counts["runs"]) + f'<span class="small">{source}</span>'

    def option(side: str) -> str:
        return idk["option"]  # both sides' option shown by its meaning (Ümit #4397, #4606); the column names the language

    def not_right(side: str) -> str:
        counts = model[side]
        return f"{counts['dont_know']:,} “{esc(option(side))}” of {counts['dont_know'] + counts['wrong']:,} not right"

    def answered(side: str) -> str:
        counts = model[side]
        invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
        return (f"{counts['right'] + counts['wrong']:,} of {total:,} answered, {counts['dont_know']:,} "
                f"“{esc(option(side))}”{invalid}")

    def wrong_of(side: str) -> str:
        return wrong_of_answers(model[side], digits)

    paired = model["paired"]
    values = [
        value("english", "non_hallucination", not_right("english")), value("english", "attempt_rate", answered("english")),
        wrong_of("english"),
        value("turkish", "non_hallucination", not_right("turkish")), value("turkish", "attempt_rate", answered("turkish")),
        wrong_of("turkish"),
        runs("english"), runs("turkish"),
        value("english", "accuracy", f"{model['english']['right']:,} of {total:,} right"),
        value("turkish", "accuracy", f"{model['turkish']['right']:,} of {total:,} right"),
        *((value("english", "mean_dont_know_probability", ""), value("turkish", "mean_dont_know_probability", ""))
          if model["group"] == "decision" else (NO_PROBABILITIES, NO_PROBABILITIES)),
        f"{paired['english_only_wrong']:,}", f"{paired['turkish_only_wrong']:,}",
        esc(bp.p_text(paired["p"]).removeprefix("p = ").removeprefix("p ")),
        esc(bp.p_text(paired["p_holm"]).removeprefix("p = ").removeprefix("p ")) + (" *" if idk_significant(model) else ""),
    ]
    heads = [f"{head} ({note})" for head, note in dont_know_columns(idk)]
    run = site.by_id[model["text_run"]]
    name = f'<td class="model">{site.icon(run)}{name_html(site, run, idk_href(site, model), site.detail(run))}</td>'
    return f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, item) for head, item in zip(heads, values)) + "</tr>"


# A chat model's mean probability of the option: it states a confidence and reports no option probabilities.
NO_PROBABILITIES = '<span class="nm">No probabilities</span><span class="small">a chat model states a confidence</span>'
# A rate with nothing to divide by (no wrong answer and no “I don't know”).
NO_RATE = '<span class="nm">No rate</span>'
# A setup asked for a plain answer line (vllm-plain): no option probabilities and no stated confidence.
PLAIN_PROVIDERS = ("vllm-plain",)
NOT_MEASURED_CONFIDENCE = '<span class="nm">Not measured</span><span class="small">a plain answer line, no confidence</span>'


def one_side_row(site: Site, idk: dict[str, Any], model: dict[str, Any], side: str) -> str:
    """A row of the table for an entry with one side (english_only, turkish_only): that side's columns filled, the other
    side's and the paired ones Running (a chat model's run still running) or Not run (a decision model; its reason in
    the method notes)."""
    digits = site.config["percent_digits"]
    total = idk["questions"]
    counts = model[side]
    word = esc(idk["option"])  # both sides' option shown by its meaning; the column names the language
    missing = RUNNING if model.get("running") else NOT_RUN

    def value(key: str, note: str) -> str:
        number = counts[key]
        return f'{NO_RATE if number is None else pct(number, digits)}<span class="small">{note}</span>'

    invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
    source = ("new runs" if len(counts["runs"]) > 1 else "a new run") if side == "english" else \
        "the Hallucination tab's full runs, counted on the kept questions"
    filled = {
        "runs": run_span(counts["runs"]) + f'<span class="small">{source}</span>',
        "answered": value("attempt_rate", f"{counts['right'] + counts['wrong']:,} of {total:,} answered, {counts['dont_know']:,} “{word}”{invalid}"),
        "wrong": wrong_of_answers(counts, digits),
        "rate": value("non_hallucination", f"{counts['dont_know']:,} “{word}” of {counts['dont_know'] + counts['wrong']:,} not right"),
        "accuracy": value("accuracy", f"{counts['right']:,} of {total:,} right"),
        "probability": value("mean_dont_know_probability", "") if model["group"] == "decision" else
        NOT_MEASURED_CONFIDENCE if model["provider"] in PLAIN_PROVIDERS else NO_PROBABILITIES,
    }
    side_cells = lambda keys: [item for key in keys for item in ((filled[key], missing) if side == "english" else (missing, filled[key]))]  # noqa: E731
    mine = [filled[key] for key in ("rate", "answered", "wrong")]
    values = ((mine + [missing] * 3 if side == "english" else [missing] * 3 + mine)
              + side_cells(("runs", "accuracy", "probability")) + [missing] * 4)
    heads = [f"{head} ({note})" for head, note in dont_know_columns(idk)]
    run = idk_run(site, model)
    icon = family_icon(setup_families(site)[idk_key(model)]["name"])
    name = f'<td class="model">{icon}{name_html(site, run, idk_href(site, model), site.detail(run))}</td>'
    return f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, item) for head, item in zip(heads, values)) + "</tr>"


def dont_know_table(site: Site, idk: dict[str, Any], attributes: str = "") -> str:
    """The table of english_reading.dont_know (or one group's entries, idk_group), its wrapper with `attributes`."""
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in dont_know_columns(idk))
    # The english_only rows go before the first paired row with a lower English rate, the paired order unchanged; the
    # turkish_only rows last.
    rows, alone = [], list(english_only(idk))
    for model in idk["models"]:
        rate = model["english"]["non_hallucination"]
        ahead = [single for single in alone if single["english"]["non_hallucination"] is not None
                 and (rate is None or single["english"]["non_hallucination"] > rate)]
        rows += [one_side_row(site, idk, single, "english") for single in ahead] + [dont_know_row(site, idk, model)]
        alone = [single for single in alone if single not in ahead]
    rows = "".join(rows + [one_side_row(site, idk, single, "english") for single in alone]
                   + [one_side_row(site, idk, single, "turkish") for single in turkish_only(idk)])
    return (f'<div class="table-wrap"{" " + attributes if attributes else ""}><table class="board list stack idk idk-lead"><thead><tr>'
            f'<th scope="col">Model</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>')


def english_only_text(site: Site, idk: dict[str, Any]) -> str:
    """The method sentences on the entries with one side: each decision model with its reason from results.json, then
    the chat models with a side still running, with page_config.json's reason."""
    text = "".join(f"<p>{esc(idk_label(site, model))} is shown in English only ({run_span(model['english']['runs'])}): "
                   f"{esc(model['reason'])}. Its Turkish and paired columns read Not run; it is in no paired test "
                   "and no Holm adjustment.</p>" for model in english_only(idk) if not model.get("running"))
    running = [model for model in english_only(idk) if model.get("running")] + turkish_only(idk)
    if running:
        text += (f"<p>{esc(site.config['dont_know']['running'])} Until both runs of a chat model are in, it is shown with "
                 f"the side it has and the other reads Running, in no paired test and no Holm adjustment: "
                 f"{esc(joined([idk_label(site, model) for model in running]))}.</p>")
    return text


def dont_know_sources(site: Site, idk: dict[str, Any]) -> str:
    """Each model's Turkish side, from the data: the Hallucination tab's published full runs counted on the kept
    questions, or new runs on the kept questions; then the models asked under another model ID than their Text tab run."""
    published = [model for model in idk["models"] if not model["turkish"].get("subset")]
    new = [model for model in idk["models"] if model["turkish"].get("subset")]
    parts = []
    if published:
        parts.append("the Hallucination tab's published full runs, counted on the kept questions only, for "
                     + joined([f"{esc(idk_label(site, model))} ({run_span(model['turkish']['runs'])})" for model in published]))
    if new:
        parts.append("new runs on the kept questions only, with the Hallucination tab's prompts, for "
                     + joined([f"{esc(idk_label(site, model))} ({run_span(model['turkish']['runs'])})" for model in new]))
    text = f"<p>The Turkish side: {'; '.join(parts)}. The new Turkish runs are not on the Hallucination tab, which uses full runs only.</p>"
    for model in idk["models"]:
        run = site.by_id[model["text_run"]]
        if model["model"] != run["model"]:
            text += (f"<p>{esc(idk_label(site, model))} was asked as <code>{esc(model['model'])}</code> in both languages, "
                     f"while its Text tab run used <code>{esc(run['model'])}</code>, because "
                     f"{esc(RENAMED[(run['provider'], run['model'], model['model'])])}.</p>")
    return text


def dont_know_runs(site: Site, idk: dict[str, Any]) -> str:
    """How many runs each model has on each side, grouped by the pair of counts."""
    by_count: dict[tuple[int, int], list[str]] = {}
    for model in idk["models"]:
        by_count.setdefault((len(model["english"]["runs"]), len(model["turkish"]["runs"])), []).append(esc(idk_label(site, model)))
    words = lambda count: f"{bp.in_words(count)} run{'' if count == 1 else 's'}"  # noqa: E731
    return "; ".join(f"{words(english)} in English and {words(turkish)} in Turkish for {joined(names)}"
                     for (english, turkish), names in sorted(by_count.items(), reverse=True))


def dont_know_info(site: Site, idk: dict[str, Any], tables: str | None = None) -> str:
    """Under Info: the table (or `tables`, a page's copies of it) and the method notes of the “I don't know” section,
    with the chat models' prompts when results.json has them (`chat`)."""
    total = f"{idk['questions']:,}"
    option = esc(idk["option"])
    families = Counter(model["group"] for model in idk["models"])
    holm = joined([f"the {bp.in_words(count)} {kind} model{'' if count == 1 else 's'}" for kind, count in sorted(families.items(), reverse=True)])
    holm_text = f"over {holm}" + (", each group a family of its own" if len(families) > 1 else "")
    chat = idk.get("chat")
    chat_text = (f"<p>A chat model is asked with the chat models' English prompts, the option after each question's own and "
                 f"one sentence added at the end of each instruction: “{esc(chat['sentence'])}” Its system prompt and "
                 f"instruction when it states a confidence:</p><blockquote><p>{esc(chat['confidence_system'])}</p>"
                 f"<p>{esc(chat['confidence_instruction'])}</p></blockquote><p>Chat prompt version "
                 f"{esc(chat['prompt_version'])}. Its Turkish side uses the Hallucination tab's chat prompts unchanged.</p>"
                 if chat and any(model["group"] == "chat" for model in idk["models"] + english_only(idk) + turkish_only(idk))
                 else "")
    return f"""
    <section class="card" id="dont-know-results">
      <h2>Results with an “I don't know” option</h2>{measure_rows(PATH, (PATH, "dont-know-results"))}
      <p class="note">Ordered by the non-hallucination rate in English, highest first. Each row compares the model's first run with the English option with its first run with the Turkish option, out of the {total} kept questions. Where a side has more than one run, its rates show the range over its runs. The paired counts, p and the Holm-adjusted p ({holm_text}) are those of the exact McNemar test on wrong answers; * marks a Holm-adjusted p below {SIGNIFICANT:g}.</p>
      {dont_know_table(site, idk) if tables is None else tables}
    </section>
    <section class="card method-notes" id="dont-know-method">
      <h2>Our method with an “I don't know” option</h2>
      <h3>The option</h3>
      <p>As on the <a href="{rel(PATH, "dont-know/")}">Hallucination tab</a>, each question gets a sixth option after its own five: F, “{option}” in English, “Bilmiyorum” in Turkish. It is always the last option, never shuffled and never correct. The English reading instructions of a decision model get one added sentence: “{esc(idk["sentence"])}” The full instructions:</p>
      <blockquote><p>{esc(idk["instructions"])}</p></blockquote>
      <p>Prompt version {esc(idk["prompt_version"])}. The question and its options are the English translation, as in the accuracy comparison above; no person checked the translations. The Turkish side uses the Hallucination tab's prompts unchanged.</p>
      {chat_text}
      <h3>The Turkish side</h3>
      {dont_know_sources(site, idk)}{english_only_text(site, idk)}
      <h3>Runs</h3>
      <p>{dont_know_runs(site, idk)}. These runs are kept out of the leaderboard, its repeats, the Hallucination tab and the accuracy comparison above.</p>
      <h3>The rates and how to read them</h3>
      <p>Each answer is right, wrong, the option or invalid. Out of the {total} kept questions, accuracy is right / {total}; Answered is (right + wrong) / {total}, the share of questions the model answered (the attempt rate), higher is better; Wrong of answers is wrong / (right + wrong), the share of its answers that were wrong, lower is better, and Undefined when it answered none. These two lead the table, with their counts under them. The non-hallucination rate, after them, is the option / (the option + wrong): among the answers that were not right, the share where the model said it did not know. As the Hallucination tab says, it is not a direct measure of what the model does not know: a model that always chose the option would reach 100% with no right answers, so read it with the attempt rate. With neither a wrong answer nor the option, the rate is undefined (No rate). The mean probability is the probability the model gave the option, averaged over its answers that report option probabilities; a chat model reports none. The paired test is the exact McNemar test on the questions only one of the two first runs got wrong, with p adjusted by Holm's method {holm_text}. No new combined score is made from these rates.</p>
    </section>"""


def check_dont_know_word(site: Site, data: dict[str, Any], word: dict[str, Any]) -> None:
    """Stops the build when results.json's english_reading.dont_know_word does not fit its sources: one entry per model
    of the accuracy comparison, in its order; the option and its sentence those of english_reading.dont_know and of
    dont_know_option_word; each side's answers cover the kept questions and its rates are its counts; the English side
    is the model's first English run of english_reading.dont_know, the Turkish side its Turkish “I don't know” point of
    english_reading.coverage; a paired test exactly where both sides are, its counts consistent with the wrong answers,
    and its Holm p adjusted over those models only."""
    problems = []
    total = word["questions"]
    if total != data["questions"]:
        problems.append(f"{total} questions, the accuracy comparison {data['questions']}")
    if [(model["name"], model["text_run"]) for model in word["models"]] != \
            [(model["name"], model["turkish_run"]) for model in data["models"]]:
        problems.append("not one entry per model of the accuracy comparison, in its order")
    idk = data.get("dont_know") or {}
    option_word = site.results.get("dont_know_option_word") or {}
    for source, found in (("english_reading.dont_know", idk), ("dont_know_option_word", option_word)):
        if (found.get("option"), found.get("sentence")) != (word["option"], word["sentence"]):
            problems.append(f"the option or its sentence is not {source}'s")
    # The method notes say the two languages' instructions differ in the one word that names the language.
    pair = [str(found.get("instructions", "")).split() for found in (option_word, idk)]
    if len(pair[0]) != len(pair[1]) or [a == b for a, b in zip(*pair)].count(False) != 1:
        problems.append("the Turkish and English instructions do not differ in exactly one word")
    english = {model["text_run"]: model["english"] for model in idk.get("models", []) + english_only(idk)}
    turkish = {}
    for model in (data.get("coverage") or {}).get("models", []):
        for point in coverage_native(model):
            if (point["language"], point["wording"]) == ("Turkish", word["option"]) and point["run"] is not None:
                turkish[model["text_run"]] = point
    close = lambda a, b: a is not None and abs(a - b) < 1e-9  # noqa: E731
    same = lambda a, b: (a is None and b is None) or (b is not None and close(a, b))  # noqa: E731
    keys = ("right", "wrong", "dont_know", "invalid")
    for model in word["models"]:
        name = model["name"]
        for side in ("english", "turkish"):
            counts = model[side]
            if counts is None:
                continue
            if sum(counts[key] for key in keys) != total:
                problems.append(f"{name}: its {side} answers do not add up to {total}")
            if not close(counts["accuracy"], counts["right"] / total) or \
                    not close(counts["attempt_rate"], (counts["right"] + counts["wrong"]) / total):
                problems.append(f"{name}: its {side} accuracy or attempt rate is not its counts")
            unsure = counts["dont_know"] + counts["wrong"]
            if (counts["non_hallucination"] is None) != (unsure == 0) or \
                    (unsure and not close(counts["non_hallucination"], counts["dont_know"] / unsure)):
                problems.append(f"{name}: its {side} non-hallucination rate is not its counts")
        source, counts = english.get(model["text_run"]), model["english"]
        if (source is None) != (counts is None):
            problems.append(f"{name}: an English side {'without' if source is None else 'missing, with'} a first English "
                            "run in english_reading.dont_know")
        elif counts is not None and (counts["run"] != source["run"] or any(counts[key] != source[key] for key in keys)
                                     or not same(counts["mean_dont_know_probability"], source["mean_dont_know_probability"])):
            problems.append(f"{name}: the English side is not english_reading.dont_know's first English run")
        point, counts = turkish.get(model["text_run"]), model["turkish"]
        if (point is None) != (counts is None):
            problems.append(f"{name}: a Turkish side {'without' if point is None else 'missing, with'} a Turkish "
                            f"“{word['option']}” point in english_reading.coverage")
        elif counts is not None and (counts["run"], counts["right"], counts["wrong"], counts["dont_know"], counts["invalid"]) != \
                (point["run"], point["right"], point["wrong"], point["abstained"], point["invalid"]):
            problems.append(f"{name}: the Turkish side is not english_reading.coverage's Turkish “{word['option']}” point")
        paired = model["paired"]
        if (paired is None) != (model["english"] is None or model["turkish"] is None):
            problems.append(f"{name}: a paired test {'missing' if paired is None else 'without both sides'}")
        elif paired is not None:
            en, tr = model["english"]["wrong"], model["turkish"]["wrong"]
            if paired["english_only_wrong"] - paired["turkish_only_wrong"] != en - tr:
                problems.append(f"{name}: the paired counts do not give the difference in wrong answers")
            if paired["english_only_wrong"] > en or paired["turkish_only_wrong"] > tr:
                problems.append(f"{name}: more wrong answers only on one side than on that side")
            if not (0 <= paired["p"] <= paired["p_holm"] <= 1):
                problems.append(f"{name}: p {paired['p']} and Holm p {paired['p_holm']} do not fit")
    both = word_both(word)
    if any(not close(model["paired"]["p_holm"], adjusted)
           for model, adjusted in zip(both, bm.holm([model["paired"]["p"] for model in both]))):
        problems.append(f"the Holm-adjusted p values are not Holm's over the {len(both)} models with both sides")
    if problems:
        raise SystemExit("english_reading dont_know_word:\n  " + "\n  ".join(problems))


def word_both(word: dict[str, Any]) -> list[dict[str, Any]]:
    """english_reading.dont_know_word's models with both sides, so in its paired test and Holm family, in its order."""
    return [model for model in word["models"] if model["paired"] is not None]


def word_only(word: dict[str, Any], side: str) -> list[dict[str, Any]]:
    """english_reading.dont_know_word's models with this side only."""
    other = "turkish" if side == "english" else "english"
    return [model for model in word["models"] if model[side] is not None and model[other] is None]


def wrong_share(counts: dict[str, Any]) -> float | None:
    """Wrong / (right + wrong); None with no answer."""
    answered = counts["right"] + counts["wrong"]
    return counts["wrong"] / answered if answered else None


def dont_know_word_summary(site: Site, word: dict[str, Any]) -> str:
    """One paragraph from the data: how many models have both runs, how their wrong of answers and non-hallucination
    compare, the Holm verdict over them with the smallest adjusted p, and the models with one side only."""
    models, both = word["models"], word_both(word)
    option = esc(word["option"])
    count = len(both)

    def compared(key: Any) -> str:
        pairs = [(key(model["english"]), key(model["turkish"])) for model in both]
        pairs = [(en, tr) for en, tr in pairs if en is not None and tr is not None]
        lower = sum(1 for en, tr in pairs if en < tr)
        higher = sum(1 for en, tr in pairs if en > tr)
        parts = [f"lower in English for {bp.in_words(lower)}", f"higher for {bp.in_words(higher)}"]
        if len(pairs) - lower - higher:
            parts.append(f"the same for {bp.in_words(len(pairs) - lower - higher)}")
        if count - len(pairs):
            parts.append(f"not measured on one side for {bp.in_words(count - len(pairs))}")
        return joined(parts)

    text = (f"{bp.opening_count(count)} of the {bp.in_words(len(models))} decision models have both runs. Among them, wrong of "
            f"answers was {compared(wrong_share)}; the non-hallucination rate was "
            f"{compared(lambda counts: counts['non_hallucination'])}.")
    if both:
        found = [model for model in both if idk_significant(model)]
        smallest = min(both, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"]))
        if found:
            named = joined([f"{esc(idk_label(site, model))} (more wrong answers in "
                            f"{'English' if model['paired']['english_only_wrong'] > model['paired']['turkish_only_wrong'] else 'Turkish'}, "
                            f"Holm-adjusted {esc(bp.p_text(model['paired']['p_holm']))})" for model in found])
            text += (f" {bp.opening_count(len(found))} of the {bp.in_words(count)} differences in wrong answers "
                     f"{'is' if len(found) == 1 else 'are'} significant after Holm's correction over the "
                     f"{bp.in_words(count)}: {named}")
        else:
            text += (f" None of the {bp.in_words(count)} differences in wrong answers is significant after Holm's "
                     f"correction over the {bp.in_words(count)}, so each could be chance; the smallest adjusted p is "
                     f"{esc(idk_label(site, smallest))}'s, {esc(bp.p_text(smallest['paired']['p_holm']))}")
        text += ' (<a href="#chart-word-paired">Paired test</a>).'
    alone = []
    turkish_only, english_side_only = word_only(word, "turkish"), word_only(word, "english")
    if turkish_only:
        alone.append(f"Turkish only, with no English run with “{option}”: "
                     + joined([esc(idk_label(site, model)) for model in turkish_only]))
    if english_side_only:
        alone.append(f"English only, with no Turkish run with the option written “{option}”: "
                     + joined([esc(idk_label(site, model)) for model in english_side_only]))
    if alone:
        text += " " + ". ".join(alone) + " (in the main table and the table under Info, with no test)."
    return f"<p>{text}</p>"


def dont_know_word_charts(site: Site, word: dict[str, Any]) -> str:
    """The section's two chart cards: wrong of answers in Turkish and in English for the models with both runs, and the
    paired test of wrong answers (as #chart-idk-paired), every number from results.json's english_reading.dont_know_word."""
    digits = site.config["percent_digits"]
    total = word["questions"]
    option = word["option"]
    both = word_both(word)

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    def share_text(counts: dict[str, Any]) -> str:
        share = wrong_share(counts)
        return "not measured" if share is None else pct(share, digits)

    def side_title(counts: dict[str, Any], language: str) -> str:
        return (f"{language} {share_text(counts)} wrong of answers ({counts['wrong']:,} of "
                f"{counts['right'] + counts['wrong']:,}), answered {pct(counts['attempt_rate'], digits)}")

    alone = [esc(idk_label(site, model)) for model in word["models"] if model["paired"] is None]
    not_charted = (f" <span>Not charted, with one side only: {joined(alone)} (in the table under Info).</span>"
                   if alone else "")
    ordered = sorted(both, key=lambda model: (wrong_share(model["turkish"]) is None, wrong_share(model["turkish"]) or 0,
                                              idk_label(site, model).casefold()))
    shares = [share for model in both for share in (wrong_share(model["turkish"]), wrong_share(model["english"]))
              if share is not None]
    # The axis up to the largest share, rounded up to a multiple of 4 points, so that each quarter is a whole point.
    top = max(0.04, math.ceil(100 * max(shares, default=0.04) / 4 - 1e-9) * 4 / 100)
    wrong = card(
        "chart-word-wrong", "Wrong of answers in Turkish and in English",
        f"Wrong / (right + wrong), with the option written “{esc(option)}” in both languages, on the {total:,} kept "
        "questions: each model's first run in each language, ordered by the Turkish share, lowest first · lower is "
        "better, read with the answered share (under the chart and in each bar's tooltip)",
        [{"label": site.title(site.by_id[model["text_run"]]), "tag": site.tag(site.by_id[model["text_run"]]),
          "family": site.families[model["text_run"]]["name"], "href": idk_href(site, model),
          "class_key": site.model_class(site.by_id[model["text_run"]]),
          "text": f"{share_text(model['turkish'])} · {share_text(model['english'])}",
          "bars": family_bars(site, model["text_run"], (wrong_share(model["turkish"]) or 0, "turkish"),
                              (wrong_share(model["english"]) or 0, "english")),
          "title": f"{idk_label(site, model)}: {side_title(model['turkish'], 'Turkish')}; "
                   f"{side_title(model['english'], 'English')}"}
         for model in ordered],
        f'<span><i class="swatch swatch-turkish"></i>Turkish, with “{esc(option)}”, the upper bar</span> '
        f'<span><i class="swatch swatch-english"></i>English, with “{esc(option)}”, the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["text_run"]] for model in ordered]) + " "
        "<span>Answered, Turkish · English: "
        + esc("; ".join(f"{idk_label(site, model)} {pct(model['turkish']['attempt_rate'], digits)} · "
                        f"{pct(model['english']['attempt_rate'], digits)}" for model in ordered))
        + ". A model that answered fewer questions can have fewer wrong answers among them.</span>" + not_charted,
        top=top, head=TR_EN)
    tested = sorted(both, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"], idk_label(site, model).casefold()))
    counts = lambda model: (model["paired"]["turkish_only_wrong"], model["paired"]["english_only_wrong"])  # noqa: E731
    most = max((max(counts(model)) for model in tested), default=0)
    # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    found = [model for model in tested if idk_significant(model)]
    others = [model for model in tested if not idk_significant(model)]

    def adjusted(group: list[dict[str, Any]]) -> str:
        texts = [esc(bp.p_text(model["paired"]["p_holm"])) for model in group]
        return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below {SIGNIFICANT:g}): "
                f"{esc(joined([idk_label(site, model) for model in found]))} ({adjusted(found)}).") if found else
               f"No difference is significant (Holm-adjusted p below {SIGNIFICANT:g}).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if found else f" Adjusted: {adjusted(others)}."
    paired = card(
        "chart-word-paired", "Wrong only in Turkish, or only in English?",
        f"Each model's first run in each language, both with the option written “{esc(option)}”, on the {total:,} kept "
        f"questions: the questions only one of the two got wrong, by the exact McNemar test with p adjusted by Holm's "
        f"method over the {len(tested)} model{'' if len(tested) == 1 else 's'} with both runs · the shorter bar is the "
        "language with fewer wrong answers",
        [{"label": site.title(site.by_id[model["text_run"]]), "tag": site.tag(site.by_id[model["text_run"]]),
          "family": site.families[model["text_run"]]["name"], "href": idk_href(site, model),
          "class_key": site.model_class(site.by_id[model["text_run"]]),
          "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if idk_significant(model) else ''}",
          "bars": family_bars(site, model["text_run"], (counts(model)[0], "turkish"), (counts(model)[1], "english")),
          "title": f"{idk_label(site, model)}: {counts(model)[0]:,} wrong only in Turkish, {counts(model)[1]:,} wrong only "
                   f"in English; exact McNemar {bp.p_text(model['paired']['p'])}, Holm-adjusted {bp.p_text(model['paired']['p_holm'])}"}
         for model in tested],
        '<span><i class="swatch swatch-turkish"></i>Wrong only in Turkish, the upper bar</span> '
        '<span><i class="swatch swatch-english"></i>Wrong only in English, the lower bar, striped</span> '
        + NUMBERS + " " + family_legend([site.families[model["text_run"]] for model in tested]) + " "
        f"<span>{verdict}</span>" + not_charted,
        top=4 * quarter, tick=lambda value: f"{value:,.0f}", head=TR_EN)
    return f'<section class="charts" aria-label="Charts with “{esc(option)}” in both languages">{wrong}{paired}</section>'


def dont_know_word_face(site: Site, word: dict[str, Any]) -> str:
    """The section's face: a heading and summary, then its two chart cards (dont_know_word_charts)."""
    option = esc(word["option"])
    return (f'<section class="card" id="dont-know-word"><h2>Only the language differs: “{option}” in both</h2>'
            f"<p>The same {word['questions']:,} kept questions with the sixth option written “{option}” in English and in "
            "Turkish too, with the same sentence added to the instructions: each model's first English run with the option, "
            "as in the section above, against its Turkish run from the option's word check of the "
            f'<a href="{rel(PATH, "dont-know/")}#option-word">Hallucination tab</a>, counted on these questions. Only the '
            "language differs: of the question and its options, of the word in the instructions that names it and of the "
            "options heading "
            f'(<a href="#dont-know-word-method">how</a>).</p>{dont_know_word_summary(site, word)}</section>'
            f"{dont_know_word_charts(site, word)}")


def dont_know_word_columns(word: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    family = len(word_both(word))
    option = word["option"]
    total = f"{word['questions']:,}"
    return (
        ("Turkish answered", f"(right + wrong) / {total}; higher is better"),
        ("English answered", f"(right + wrong) / {total}; higher is better"),
        ("Turkish wrong of answers", "wrong / (right + wrong); lower is better"),
        ("English wrong of answers", "wrong / (right + wrong); lower is better"),
        ("Turkish non-hallucination", f"“{option}” / (“{option}” + wrong); higher is better, read with the answered share"),
        ("English non-hallucination", f"“{option}” / (“{option}” + wrong); higher is better, read with the answered share"),
        ("Turkish accuracy", "higher is better"),
        ("English accuracy", "higher is better"),
        ("Turkish mean probability", f"of “{option}”"),
        ("English mean probability", f"of “{option}”"),
        ("Turkish run", "the option-word run, counted on the kept questions"),
        ("English run", f"the first English run with “{option}”"),
        ("Wrong only in English", "questions the English run got wrong and the Turkish run did not"),
        ("Wrong only in Turkish", "questions the Turkish run got wrong and the English run did not"),
        ("p", "exact McNemar"),
        ("Holm p", f"adjusted over the {family} model{'' if family == 1 else 's'} with both runs"),
    )


def dont_know_word_row(site: Site, word: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    total = word["questions"]
    option = esc(word["option"])
    sides = (model["turkish"], model["english"])

    def value(counts: dict[str, Any] | None, key: str, note: str) -> str:
        if counts is None:
            return NOT_RUN
        number = counts[key]
        return f'{UNDEFINED if number is None else pct(number, digits)}<span class="small">{note}</span>'

    def answered(counts: dict[str, Any]) -> str:
        invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
        return f"{counts['right'] + counts['wrong']:,} of {total:,} answered, {counts['dont_know']:,} “{option}”{invalid}"

    paired = model["paired"]
    values = [value(counts, "attempt_rate", "" if counts is None else answered(counts)) for counts in sides]
    values += [NOT_RUN if counts is None else wrong_of_answers(counts, digits) for counts in sides]
    values += [value(counts, "non_hallucination", "" if counts is None else
                     f"{counts['dont_know']:,} “{option}” of {counts['dont_know'] + counts['wrong']:,} not right")
               for counts in sides]
    values += [value(counts, "accuracy", "" if counts is None else f"{counts['right']:,} of {total:,} right") for counts in sides]
    values += [NOT_RUN if counts is None else
               NO_PROBABILITIES if counts["mean_dont_know_probability"] is None else pct(counts["mean_dont_know_probability"], digits)
               for counts in sides]
    values += [NOT_RUN if counts is None else run_span([counts["run"]]) for counts in sides]
    if paired is None:
        values += [NOT_RUN] * 4
    else:
        values += [f"{paired['english_only_wrong']:,}", f"{paired['turkish_only_wrong']:,}",
                   esc(bp.p_text(paired["p"]).removeprefix("p = ").removeprefix("p ")),
                   esc(bp.p_text(paired["p_holm"]).removeprefix("p = ").removeprefix("p "))
                   + (" *" if idk_significant(model) else "")]
    heads = [f"{head} ({note})" for head, note in dont_know_word_columns(word)]
    run = site.by_id[model["text_run"]]
    name = f'<td class="model">{site.icon(run)}{name_html(site, run, idk_href(site, model), site.detail(run))}</td>'
    return f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, item) for head, item in zip(heads, values)) + "</tr>"


def dont_know_word_info(site: Site, data: dict[str, Any], word: dict[str, Any]) -> str:
    """Under Info: the table and the method notes of the “I don't know” in both languages section."""
    total = f"{word['questions']:,}"
    option = esc(word["option"])
    both = word_both(word)
    family = len(both)
    option_word = site.results["dont_know_option_word"]
    idk = data["dont_know"]
    rows = "".join(dont_know_word_row(site, word, model) for model in word["models"]
                   if model["english"] is not None or model["turkish"] is not None)
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in dont_know_word_columns(word))
    runs = lambda side: joined([f"{esc(idk_label(site, model))} ({run_span([model[side]['run']])})"  # noqa: E731
                                for model in word["models"] if model[side] is not None])
    alone = []
    if word_only(word, "turkish"):
        alone.append(f"Turkish only, with no English run with “{option}”: "
                     + joined([esc(idk_label(site, model)) for model in word_only(word, "turkish")]))
    if word_only(word, "english"):
        alone.append(f"English only, with no Turkish run with the option written “{option}”: "
                     + joined([esc(idk_label(site, model)) for model in word_only(word, "english")]))
    alone_text = (f"<p>{'. '.join(alone)}. Their other side and paired columns read Not run; they are in no paired "
                  "test and no Holm adjustment.</p>") if alone else ""
    return f"""
    <section class="card" id="dont-know-word-results">
      <h2>Results with “{option}” in both languages</h2>
      <p class="note">In the order of the Results table above. Each row compares the model's first English run with “{option}” with its Turkish run with the option also written “{option}”, out of the {total} kept questions. The paired counts, p and the Holm-adjusted p (over the {family} model{"" if family == 1 else "s"} with both runs) are those of the exact McNemar test on wrong answers; * marks a Holm-adjusted p below {SIGNIFICANT:g}. Not run: no such run; Undefined: a rate with nothing to count.</p>
      <div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>
    </section>
    <section class="card method-notes" id="dont-know-word-method">
      <h2>Our method with “{option}” in both languages</h2>
      <h3>What is the same</h3>
      <p>In both languages the sixth option, F, is written “{option}”, always the last option, never shuffled and never correct, and the instructions get the same added sentence: “{esc(word["sentence"])}” Both sides are counted on the same {total} kept questions.</p>
      <h3>What differs</h3>
      <p>The language of the question and its options (the English translation, as in the accuracy comparison above, against the Turkish original); the one word of the instructions that names the language of the question; and the options heading, “{esc(TURKISH_OPTIONS_HEADING)}” against “{esc(data["options_heading"])}”. The instructions of the Turkish runs:</p>
      <blockquote><p>{esc(option_word["instructions"])}</p></blockquote>
      <p>The instructions of the English runs:</p>
      <blockquote><p>{esc(idk["instructions"])}</p></blockquote>
      <h3>The runs</h3>
      <p>The Turkish side is the Hallucination tab's option-word run (<a href="{rel(PATH, "dont-know/")}#option-word">the option's word</a>) on all {option_word["questions"]:,} Turkish questions, counted on the {total} kept questions only: {runs("turkish")}. The English side is the first English run with “{option}” of the section above: {runs("english")}. First runs only: where a model has more runs, the others are not counted here. No run was made for this comparison.</p>
      {alone_text}
      <h3>The test</h3>
      <p>A wrong answer is a valid choice other than “{option}” that is not right. The paired test is the exact McNemar test on the questions only one of the two runs got wrong, with p adjusted by Holm's method over the {bp.in_words(family)} model{"" if family == 1 else "s"} with both runs: a family of its own, separate from every other family on the site. The comparison with “Bilmiyorum” in Turkish stays as published in the <a href="#dont-know">section above</a> (<a href="#dont-know-results">its table</a>).</p>
    </section>"""


def languages(site: Site, data: dict[str, Any]) -> str:
    """Languages the model cards list: one row per model of page_config.json's model_languages (each card or maker's
    docs as checked), the model named as the Text tab names its run. The sentence above the table is computed from the
    entries; the build stops when they no longer fit it."""
    config = site.config["model_languages"]
    models = config["models"]
    stated = [model for model in models if model["languages"] != "not stated"]
    tagged = [model for model in stated if model["languages"].startswith("English (the card's `language: en` tag")]
    quoted = [model for model in stated if model["languages"].startswith('"')]
    primary = [model for model in quoted if "English is the primary" in model["languages"]]
    if len(tagged) + len(quoted) != len(stated) or primary != quoted or not tagged or not quoted:
        raise SystemExit("page_config.json model_languages: the sentence expects cards that name English by their tag and "
                         "docs that call English the primary language, and no other statement")
    if any("turkish" in model["languages"].casefold() for model in models):
        raise SystemExit("page_config.json model_languages: the sentence says no card names Turkish")
    name = lambda model: site.title(site.by_id[model["run"]])  # noqa: E731
    rows = "".join(
        f'<tr{site.class_attribute(site.by_id[model["run"]])}><td class="model">{site.icon(site.by_id[model["run"]])}'
        f'{name_html(site, site.by_id[model["run"]], setup_href(site, PATH, model["run"]))}</td><td data-label="Languages listed">{languages_text(model["languages"])}</td>'
        f'<td data-label="Source"><a href="{esc(model["source"])}">{esc(model["source"].split("//", 1)[1].split("/", 1)[0])}</a></td>'
        f'<td data-label="Checked">{esc(config["checked"])}</td></tr>' for model in models)
    maker = lambda model: esc(name(model).split()[0])  # noqa: E731
    listed = {model["run"] for model in models}
    unchecked = [model for model in data["models"] if model["turkish_run"] not in listed]
    decision = [esc(label(site, model)) for model in unchecked if site.decision(site.by_id[model["turkish_run"]])]
    chat = len(unchecked) - len(decision)
    parts = decision + ([f"the {bp.in_words(chat)} {noun('chat', chat)}"] if chat else [])
    summary = (f"<p>Of the {len(models)} models whose cards or docs we checked, only "
               f"{joined([esc(name(model)) for model in tagged])} name a language: English, by the card's "
               f"<code>language: en</code> tag. {joined([maker(model) for model in quoted])}'s docs call English "
               f"its primary language. No card names Turkish."
               + (f" Not checked yet, of the English setups: {joined(parts)}." if parts else "") + "</p>")
    return f"""
    <section class="card" id="languages">
      <h2>Languages the model cards list</h2>
      {summary}
      <p class="note">Each model's card at the revision we ran (local weights) or its maker's model page and docs (APIs), searched for language statements and the Hugging Face <code>language:</code> field, on {esc(config["checked"])}. “not stated”: neither names a language.</p>
      <div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th><th scope="col">Languages listed</th><th scope="col">Source</th><th scope="col">Checked</th></tr></thead><tbody>{rows}</tbody></table></div>
    </section>"""


def check_structural(site: Site, record: dict[str, Any]) -> dict[str, Any]:
    """Stops the build unless every question the structural check found a problem in (page_config.json's
    english_reading.structural_check) is a reading question the flags left out; returns the check's facts."""
    facts = site.config["english_reading"]["structural_check"]
    known = {question["question_id"]: question for question in record["questions"]}
    kept = [question for question in facts["problem_questions"] if question not in known or known[question]["kept"]]
    if kept:
        raise SystemExit("page_config.json english_reading.structural_check: problem questions not among the flagged "
                         f"ones: {kept}")
    return facts


def kept_ids(record: dict[str, Any]) -> str:
    """The plain file of the kept questions' IDs, one per line, under a comment header."""
    ids = [question["question_id"] for question in record["questions"] if question["kept"]]
    return (f"# The {len(ids):,} reading questions kept on the Turkish vs English tab ({PATH}), one question ID "
            "per line: english-reading.json's questions with kept true.\n" + "".join(f"{question}\n" for question in ids))


def redirect(site: Site) -> str:
    """The page at the tab's earlier address: sends the reader to PATH with the query and fragment, as v2/ does."""
    target = rel(OLD_PATH, PATH)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moved: Turkish vs English</title>
  <link rel="canonical" href="{esc(site.config['site_url'] + PATH)}">
  <meta http-equiv="refresh" content="0; url={target}">
  <!-- Keeps a deep link's section: the meta refresh alone drops it. -->
  <script>location.replace("{target}" + location.search + location.hash);</script>
</head>
<body>
  <p>The English reading tab is now the Turkish vs English tab: <a href="{target}">{PATH}</a>.</p>
</body>
</html>
"""


def option_word(site: Site) -> str:
    """The option's word on this tab: for each model of results.json's dont_know_option_word, Answered and Wrong of
    answers with “Bilmiyorum” and with “I don't know” on the Hallucination tab's Turkish questions, then the
    non-hallucination rates with the counts, the difference and the paired test's Holm-adjusted p; checked and ordered
    as the Hallucination tab does."""
    data, word = group_data(site.results["dont_know"], "decision"), site.results.get("dont_know_option_word")
    if not word:
        return ""
    check_option_word(site, data, word)
    digits, total = site.config["percent_digits"], word["questions"]
    old, new = data["option"], word["option"]
    heads = tuple(f"Answered with “{text}” ((right + wrong) / questions; higher is better)" for text in (old, new)) + tuple(
        f"Wrong of answers with “{text}” (wrong / (right + wrong); lower is better)" for text in (old, new)) + tuple(
        f"Non-hallucination with “{text}” (“{text}” / (“{text}” + wrong); higher is better)" for text in (old, new)) + (
        f"Difference (“{new}” minus “{old}” in non-hallucination, in points; positive = higher with the English word)",
        "Holm-adjusted p (exact McNemar test of wrong answers)")

    def answered(counts: dict[str, Any]) -> str:
        count = counts["right"] + counts["wrong"]
        return f'{pct(count / total, digits)}<span class="small">{count:,} of {total:,} answered</span>'

    def rate(counts: dict[str, Any], option: str) -> str:
        value = counts["non_hallucination"]
        shown = UNDEFINED if value is None else pct(value, digits)
        return (f'{shown}<span class="small">{counts["right"]:,} right, {counts["wrong"]:,} wrong, '
                f'{counts["dont_know"]:,} “{esc(option)}”</span>')

    rows = []
    for model in option_word_rows(site, data, word):
        b, e, paired = model["bilmiyorum"], model["i_dont_know"], model["paired"]
        found = paired["p_holm"] is not None and paired["p_holm"] < SIGNIFICANT
        difference = (UNDEFINED if b["non_hallucination"] is None or e["non_hallucination"] is None
                      else f"{100 * (e['non_hallucination'] - b['non_hallucination']):+.{digits}f}{' *' if found else ''}")
        holm = "not in Holm's family" if paired["p_holm"] is None else esc(bp.p_text(paired["p_holm"]))
        run = site.by_id[model["original_run"]]
        name = f'<td class="model">{site.icon(run)}{name_html(site, run, setup_href(site, PATH, run["run"]))}</td>'
        values = (answered(b), answered(e), wrong_of_answers(b, digits), wrong_of_answers(e, digits), rate(b, old),
                  rate(e, new), difference, holm)
        rows.append(f"<tr{site.class_attribute(run)}>{name}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(text.split(" (")[0])}<span class="small">{esc(text.split(" (", 1)[1][:-1])}</span></th>'
                   for text in heads)
    return (f'<section class="card" id="option-word"><h2>The option\'s word: “{esc(new)}” instead of “{esc(old)}”</h2>'
            f"<p>The Hallucination tab's {word['questions']:,} Turkish questions, with the sixth option “{esc(old)}” and "
            f"again with “{esc(new)}”, and only the sentence that names it changed: a model that skipped “{esc(old)}” "
            f"because it did not recognise the Turkish word should choose “{esc(new)}” more often. Each of the "
            f"{len(word['models'])} models' first run with each word, in the Hallucination tab's order; the full table and "
            f'method are on the <a href="{rel(PATH, "dont-know/")}#option-word">Hallucination tab</a>.</p>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="note">Answered: (right + wrong) / {total:,} questions. Wrong of answers: wrong / (right + wrong). '
            f"Both are worked out from the published counts; under each non-hallucination rate, of the {total:,} questions, "
            "the right answers, the wrong ones and the option. * marks a difference whose paired test (the exact McNemar "
            "test on the questions only one of the two runs got wrong, with p adjusted by Holm's method over the models) "
            f"has a Holm-adjusted p below {SIGNIFICANT:g}.</p>"
            "</section>")


def instructions(site: Site, data: dict[str, Any]) -> str:
    """Under Info: the full System One instructions of each kind of decision model run in both languages, and the chat
    models' system prompt and instruction in both languages, quoted from answers.json's and results.json's prompts; then
    the kinds with “I don't know”, the decision models' (for the all and decision groups) and the chat models' (for the
    all and chat groups, from results.json's dont_know.chat and english_reading.dont_know.chat)."""
    idk, word = data.get("dont_know"), site.results.get("dont_know_option_word")
    quote = lambda text: f"<blockquote><p>{esc(text)}</p></blockquote>"  # noqa: E731
    parts = [("Decision models, five options, in Turkish (the Text tab)", site.answers["prompts"]["system_one_instructions"]),
             ("Decision models, five options, in English", data["instructions"])]
    chat = data.get("chat_prompts")
    if chat and group_models(site, data, "chat"):
        turkish = site.answers["prompts"]
        parts += [("Chat models, in Turkish (the Text tab): the system prompt", turkish["confidence_system"]),
                  ("Chat models, in Turkish (the Text tab): the instruction", turkish["confidence_instruction"]),
                  (f"Chat models, in English (prompt version {data['chat_prompt_version']}): the system prompt",
                   chat["confidence_system"]),
                  ("Chat models, in English: the instruction", chat["confidence_instruction"])]
    with_option = []
    if idk:
        with_option += [(f"With the option, in Turkish (“{site.results['dont_know']['option']}”, the Hallucination tab)",
                         site.results["dont_know"]["instructions"]),
                        (f"With the option, in English (“{idk['option']}”)", idk["instructions"])]
    if word:
        with_option.append((f"The option's word: the Turkish questions with “{word['option']}”", word["instructions"]))
    chat_option = []
    for language, prompts in (("Turkish", site.results["dont_know"].get("chat")), ("English", (idk or {}).get("chat"))):
        if prompts:
            chat_option.append((f"Chat models with the option, in {language} (prompt version {prompts['prompt_version']}): "
                                "the instruction", prompts["confidence_instruction"]))
    listed = lambda items: "".join(f"<h3>{esc(title)}</h3>{quote(text)}" for title, text in items)  # noqa: E731
    return ('<section class="card method-notes" id="instructions"><h2>The instructions of each kind of run</h2>'
            "<p>Each decision model run's System One instructions in full, and each chat model run's system prompt and "
            "instruction, as results.json and answers.json give them; a chat model's run with the option keeps the "
            "system prompt of its five-option run. The question and its options follow in the run's "
            "language; their text is not published.</p>" + listed(parts)
            + (f"<div {DECISION_ONLY}>{listed(with_option)}</div>" if with_option else "")
            + (f'<div data-models="all chat">{listed(chat_option)}</div>' if chat_option else "") + "</section>")


def coverage_native(model: dict[str, Any]) -> list[dict[str, Any]]:
    """A model's native points in NATIVE's order; english_reading.coverage must give each exactly once."""
    found = {(point["language"], point["wording"]): point for point in model["native"]}
    if sorted(found) != sorted(NATIVE) or len(model["native"]) != len(NATIVE):
        raise SystemExit(f"english_reading.coverage: {model['name']} does not have one native point per wording")
    return [found[key] for key in NATIVE]


def coverage(site: Site, data: dict[str, Any]) -> str:
    """Risk and coverage on the kept questions (results.json english_reading.coverage): the definitions, the native
    abstention points of each model (Turkish with “Bilmiyorum”, Turkish with “I don't know”, the latter for decision
    models only, English with “I don't know”) in one table per group of the view bar, and, for each group, two
    risk-coverage plots, Turkish and English, each with the confidence curves of the group's setups' five-option runs as
    lines and their native points as markers, each setup in its colour (model_colours)."""
    cov = data.get("coverage")
    if not cov:
        return ""
    digits = site.config["percent_digits"]
    total = cov["questions"]
    if total != data["questions"] or [model["text_run"] for model in cov["models"]] != [model["turkish_run"] for model in data["models"]]:
        raise SystemExit("english_reading.coverage: not the comparison's questions or setups")
    colours = model_colours(site)
    name = lambda model: idk_label(site, model)  # noqa: E731
    risk = lambda value: pct(value, digits)  # noqa: E731
    members = lambda group: [model for model in cov["models"] if site.in_group(site.by_id[model["text_run"]], group)]  # noqa: E731
    chat_word = [model["name"] for model in members("chat")
                 if any(point["run"] is not None and point["language"] == "Turkish" and point["wording"] == "I don't know"
                        for point in model["native"])]
    if chat_word:
        raise SystemExit(f"english_reading.coverage: Turkish “I don't know” points for chat models ({', '.join(chat_word)}), "
                         "which the page says is a decision models' check")

    def series_name(point: dict[str, Any]) -> str:
        return f"{point['language']} with “{point['wording']}”, run {point['run']}"

    def native_text(point: dict[str, Any]) -> str:
        restricted = " (its full-bank run, restricted to these questions)" if point["full_bank_restricted"] else ""
        return (f"{series_name(point)}{restricted}: coverage {pct(point['coverage'], digits)}, error rate among answered "
                f"{risk(point['risk'])}; {point['right']:,} right, {point['wrong']:,} wrong, {point['abstained']:,} "
                f"abstained, {point['invalid']:,} invalid")

    heads = [f"{language} with “{wording}”" for language, wording in NATIVE]
    header = "".join(f'<th scope="col" class="num">{esc(text)}<span class="small">coverage · error rate among answered</span></th>'
                     for text in heads)

    def missing(model: dict[str, Any], point: dict[str, Any]) -> str:
        """A point without a run: the option's word in Turkish is a decision models' check (Not run); otherwise Running
        for a chat model, Not run for a decision model."""
        if point["language"] == "Turkish" and point["wording"] == "I don't know":
            return f'{NOT_RUN}<span class="small">decision models only</span>' if not site.decision(site.by_id[model["text_run"]]) else NOT_RUN
        return missing_side(site, site.by_id[model["text_run"]])

    def table(group: str) -> str:
        rows = []
        for model in members(group):
            cells = []
            for head, point in zip(heads, coverage_native(model)):
                if point["run"] is None:
                    cells.append(cell(head, missing(model, point)))
                    continue
                restricted = ", full bank restricted" if point["full_bank_restricted"] else ""
                cells.append(cell(head, f"{pct(point['coverage'], digits)} · {risk(point['risk'])}"
                                        f'<span class="small">{point["right"]:,} right, {point["wrong"]:,} wrong, '
                                        f'{point["abstained"]:,} abstained · run {point["run"]}{restricted}</span>'))
            run = site.by_id[model["text_run"]]
            rows.append(f'<tr{site.class_attribute(run)}><td class="model">{site.icon(run)}'
                        f'{name_html(site, run, setup_href(site, PATH, run["run"]))}</td>{"".join(cells)}</tr>')
        return (f'<div class="table-wrap" {shown(group)}><table class="board list stack idk"><thead><tr><th scope="col">Model</th>'
                f'{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>') if rows else ""

    table_html = ("<h3>The runs with the option</h3>" + "".join(table(group) for group in GROUPS)
                  + '<p class="note">Each cell: coverage · error rate among answered, then the counts and the run. Not run: '
                  "no such run for a decision model, or the Turkish “I don't know” run, which is for decision models only; "
                  "Running: a chat model's run still running.</p>")

    def plot(group: str, language: str, y_top: float) -> str:
        series, legend = [], []
        for model in members(group):
            colour, keys = colours[model["text_run"]], []
            for curve in (curve for curve in model["curves"] if curve["language"] == language):
                title = (f"{name(model)}: {language}, five options, held back by confidence, run {curve['run']} "
                         f"({len(curve['points']):,} points)")
                series.append({"colour": colour, "line": True, "title": title,
                               "points": [(x, y, "") for x, y, _, _ in curve["points"]]})
                keys.append(f"{legend_mark(colour)} confidence, run {curve['run']}")
            for point in coverage_native(model):
                if point["language"] != language or point["run"] is None:
                    continue
                shape = SHAPES[point["wording"]]
                series.append({"colour": colour, "shape": shape, "title": series_name(point),
                               "points": [(point["coverage"], point["risk"], f"{name(model)}: {native_text(point)}")]})
                keys.append(f"{legend_mark(colour, shape)} “{esc(point['wording'])}”, run {point['run']}")
            legend.append(f"<li><b>{esc(name(model))}</b>: {' · '.join(keys)}</li>")
        shapes = " ".join(f"{legend_mark('var(--text-2)', SHAPES[wording])} “{esc(wording)}”"
                          for wording in dict.fromkeys(wording for lang, wording in NATIVE if lang == language))
        marker = f"and a run with the option (the marker: {shapes})"
        title = f"Risk and coverage in {language}"
        return (f'<figure class="panel chart-card" id="{anchor(f"chart-coverage-{language.lower()}", group)}">'
                f'<div class="chart-head"><h2>{esc(title)}</h2><p class="chart-sub">The {total:,} kept questions in '
                f"{language}: each setup's five-option run answering only at or above a confidence score (the line), "
                f"{marker} · lower is better at the same coverage</p></div>"
                f'<div class="chart-box" style="min-height:0;overflow-x:auto">'
                + line_plot(series, "Coverage (answered / " + f"{total:,})", "Error rate among answered", y_top,
                            f"{title}: coverage against error rate among answered")
                + f'</div><ul class="chart-legend" style="list-style:none;padding:0">{"".join(legend)}</ul></figure>')

    def plots(group: str) -> str:
        if not members(group):
            return ""
        values = [point["risk"] for model in members(group) for point in model["native"] if point["run"] is not None]
        values += [point[1] for model in members(group) for curve in model["curves"] for point in curve["points"]]
        # The same y axis in both plots of a group: up to the largest error rate, rounded up to a multiple of 4 points.
        y_top = max(0.04, math.ceil(100 * max(values, default=0.04) / 4 - 1e-9) * 4 / 100)
        return (f'<section class="charts" aria-label="Risk-coverage plots" {shown(group)}>'
                f'{plot(group, "Turkish", y_top)}{plot(group, "English", y_top)}</section>')

    return (f'<section class="card" id="coverage"><h2>Risk and coverage</h2>{measure_rows(PATH, (PATH, "coverage"))}'
            f"<p>How often each setup answers and how often its answers are wrong, on the same {total:,} kept questions in "
            "both languages: without the option, by holding back the answers below a confidence score, and with the "
            "option, as the model chose it.</p>"
            "<h3>Method</h3>"
            f"<p>Answered = right + wrong (an invalid answer or one without a score is never answered). Coverage = answered / "
            f"{total:,}. Error rate among answered (risk) = wrong / answered. Abstained: for a run with the option, the "
            f"times it chose the option; for a confidence point, {total:,} minus answered minus invalid. Each confidence "
            "curve has one point per distinct score of the run on these questions (answer when the score is at least "
            "that score; the score is the recorded probability of the chosen option for a decision model and the "
            "confidence a chat model stated with its answer): answers with equal scores enter together, so coverage "
            "moves in jumps and every point is one the run achieved; a setup that reports its scores with few decimals "
            "has many equal scores, so its curve has fewer points, moves in larger steps and can start well above 0% "
            "coverage (each curve is drawn from its first point). Every series counts these questions only (a run on "
            "the full bank is restricted to them) and is each setup's first run. Turkish curves: the Text tab run; "
            "English curves: the first English run. Turkish with “Bilmiyorum” is the Turkish side of the English "
            "“I don't know” comparison or, for a model outside it, its Hallucination tab run, restricted to these; "
            "Turkish with “I don't know” is the option's word control on the Hallucination tab's questions, restricted "
            "to these, for decision models only. A run not yet in reads Not run for a decision model and Running for a "
            "chat model.</p>"
            f'<p class="note">{esc(cov["definitions"])}</p>'
            f"{table_html}</section>" + "".join(plots(group) for group in GROUPS))


def build(site: Site) -> dict[str, str]:
    if "english_reading" not in site.results:
        return {}
    data = site.results["english_reading"]
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    check(site, data, record)
    idk = data.get("dont_know")
    if idk:
        check_dont_know(site, data, idk)
    word = data.get("dont_know_word")
    if word:
        check_dont_know_word(site, data, word)
    rights = [model["english"]["right"] for model in data["models"]]
    rates = [model["english"]["non_hallucination"] or 0 for model in (idk or {}).get("models", [])]
    if rights != sorted(rights, reverse=True) or rates != sorted(rates, reverse=True):
        raise SystemExit("english_reading: the charts expect the setups ordered by English accuracy and, with the option, "
                         "by the English non-hallucination rate")
    structural = check_structural(site, record)
    grammar = site.runs[0]["groups"]["grammar"]["questions"]
    if grammar != site.total - data["reading_questions"]:
        raise SystemExit("english_reading: the grammar questions are not the Text tab's questions less the reading ones")
    problems = structural["problem_questions"]
    kept, flagged, reading = f"{data['questions']:,}", f"{data['flagged']:,}", f"{data['reading_questions']:,}"
    translator, prompts = record["translator"], record["prompts"]
    translator_name = TRANSLATORS[translator["model"]]
    family = len(data["models"])
    counts = {group: len(group_models(site, data, group)) for group in GROUPS}
    missing = {group: sum(1 for _, runs in not_run(site, data) for run in runs if site.in_group(run, group)) for group in GROUPS}
    text_tab = {group: sum(1 for run in site.runs if site.in_group(run, group)) for group in GROUPS}
    # "I don't know" in both languages: the decision models' entries (its Turkish side, the option-word run, is for
    # decision models only).
    word_decision = dict(word, models=[model for model in word["models"] if site.decision(site.by_id[model["text_run"]])]) \
        if word else None
    turkish_instructions = site.answers["prompts"]["system_one_instructions"]
    enum = prompts["flag"]["schema"]["properties"]["reasons"]["items"]["enum"]
    reasons = "".join(f"<li>{esc(reason_name(key))}: {record['reasons'][key]:,}</li>" for key in enum if key in record["reasons"])
    script = f'<a href="{BLOB_URL}runner/translate_reading.py"><code>runner/translate_reading.py</code></a>'
    download = f'<a href="{rel(PATH, "english-reading.json")}" download>english-reading.json</a>'
    ids_download = f'<a href="{KEPT_IDS}" download>{KEPT_IDS}</a>'
    split = (f"{bp.in_words(counts['decision'])} {noun('decision', counts['decision'])} and "
             f"{bp.in_words(counts['chat'])} {noun('chat', counts['chat'])}")
    against = against_reference(site, data) if counts["decision"] else ""

    def idk_entries(group: str) -> bool:
        part = idk_group(site, idk, group)
        return bool(part["models"] or english_only(part) or turkish_only(part))

    idk_groups = [group for group in GROUPS if idk and idk_entries(group)]
    idk_parts = "".join(dont_know_face(site, idk_group(site, idk, group), word_decision, group) for group in idk_groups)
    word_parts = "".join([dont_know_word_face(site, word_decision) if word_decision else "", option_word(site)])

    def lead(group: str) -> str:
        """A group's copy of the lead: what was asked of how many of its setups, then the headline."""
        count = counts[group]
        if not count:
            return (f'<div {shown(group)}><p>No {noun(group, 1)} has an English run yet (<a href="#{anchor("not-run", group)}">'
                    "which, and why</a>).</p></div>")
        return (f"<div {shown(group)}><p>{kept} of the Text tab's {reading} reading questions, translated into English, "
                f"asked of {bp.in_words(count)} {noun(group, count)}" + (f" ({split})" if group == "all" else "")
                + f", each compared with its own Turkish run.</p>{headline(site, data, group)}</div>")

    def empty(group: str) -> str:
        """A group's empty-view line at the top, where none of its setups has an English run (lead, with the headline,
        in the notes)."""
        return "" if counts[group] else lead(group)

    def copies(render: Callable[[str], str]) -> str:
        return "".join(render(group) for group in GROUPS if counts[group])

    chat = group_models(site, data, "chat")
    sizes = Counter(site.by_id[model["turkish_run"]]["questions_per_request"] for model in chat)
    size_text = joined([f"{bp.count(size)} question{'' if size == 1 else 's'} per request for {bp.in_words(number)}"
                        for size, number in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))])
    chat_method = (f"""
      <h3>Asking the chat models</h3>
      <p>Each chat model setup is asked as its Text tab run was, with the same settings (reasoning, and {size_text}), and with the Text tab's chat prompts in English: the system prompt and the instruction that ask for each answer's letter with a confidence score between 0 and 1, the question header and the options heading “{esc(data["chat_prompts"]["options_heading"].strip())}”. A chat model gives no option probabilities, so its confidence score is the one it stated. The English runs' system prompt:</p>
      <blockquote><p>{esc(data["chat_prompts"]["confidence_system"])}</p></blockquote>
      <p>Their instruction:</p>
      <blockquote><p>{esc(data["chat_prompts"]["confidence_instruction"])}</p></blockquote>
      <p>Chat prompt version {esc(data["chat_prompt_version"])}; the Text tab's Turkish prompts are under <a href="#instructions">The instructions of each kind of run</a>. The chat models' runs with an “I don't know” option are under <a href="#dont-know-method">Our method with an “I don't know” option</a>.</p>""" if chat else "")
    makers = {run["provider"] for run in site.runs if run["model"] == record["translator"]["model"]}
    maker_chat = list(dict.fromkeys(model["name"] for model in chat if model["provider"] in makers))
    own = any(model["model"] == record["translator"]["model"] for model in chat)
    maker_text = (f" Of its maker's chat models, {esc(joined(maker_chat))} answered the English questions too"
                  + (", the translator's own model among them" if own else "") + ".") if maker_chat else ""
    whole_bank = "" if not chat or any(len(model["turkish_runs"]) > 1 for model in chat) else \
        "; no chat setup run in English has whole-bank Turkish repeats, so each has one"
    against_block = (f"<div {DECISION_ONLY}>{against}</div>" + chat_note(
        "Liquid d1-ultra against each decision model in English is for decision models only.")) if against else ""
    idk_block = idk_parts + (f"<div {DECISION_ONLY}>{word_parts}</div>" if word_parts else "")
    method = "#method"
    site.note(PATH, "Turkish vs English", "".join(lead(group) for group in GROUPS) + limit_note(translator_name, method)
              + experiments_note(site, PATH))
    body = f"""    <section class="card">
      <p class="eyebrow">Turkish vs English</p>
      <h1>The Text tab's reading questions, in Turkish and in English</h1>
      {"".join(empty(group) for group in GROUPS)}
    </section>
    <section class="measure" id="accuracy" aria-label="Accuracy">{copies(lambda group: face(site, data, group))}{against_block}</section>
    {limit_line(method)}
    {more_link(PATH)}
    {copies(lambda group: main_table(site, data, group))}{"".join(english_only_list(site, data, group) for group in GROUPS)}
    <section class="measure" id="non-hallucination" aria-label="Non-hallucination">{measure_rows(PATH, (PATH, "non-hallucination"))}{idk_block}</section>
    <section class="measure" id="cost" aria-label="Cost">{measure_rows(PATH, (PATH, "cost"))}{copies(lambda group: measure_card(site, data, group, "cost", tuple(SIDES), href, method))}</section>
    <section class="measure" id="latency" aria-label="Latency">{measure_rows(PATH, (PATH, "latency"))}{copies(lambda group: measure_card(site, data, group, "latency", tuple(SIDES), href, method))}</section>
    {coverage(site, data)}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The table, the setups without an English run and our method{", then the same with “I don't know”" if idk else ""}</span></summary>
    <section class="card" id="about">
      <h2>About this test</h2>
      <p>Since 5 November 2026 every setup of the Text tab also runs in English, decision models and chat models alike, each with its Text tab run's settings and compared with that run. {bp.opening_count(family)} of the Text tab's {text_tab["all"]:,} setups have an English run so far, {split}; the other {bp.in_words(missing["all"])} are listed under <a href="#results">Results</a> with the reason each has none yet. This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its numbers.</p>
      <p>The Text tab's reading questions ({esc(units_text(record))}; the grammar questions are left out) were translated into English by {esc(translator_name)}. The same model flagged the questions whose answer depends on Turkish wording; the {flagged} flagged questions are left out and the other {kept} kept. Each of the {bp.in_words(family)} English setups answered the kept questions in English and is compared with its own Text tab run on the same {kept} questions.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (the comparison's numbers, under <code>english_reading</code>), <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each English run's answers, under <code>english_runs</code>), {download} (the translator, its prompts, the flags, the question units and each question's hash of its English text; no question text) and {ids_download} (the {kept} kept questions' IDs, one per line).</p>
    </section>
    <section class="card" id="results">
      <h2>Results</h2>
      <p class="note">The setups of the model group in view, ordered by accuracy in English, highest first. Each row compares the setup's first English run with its Text tab run, out of the {kept} kept questions; an invalid answer counts as not right. Where a side has more than one run, its accuracy shows the range over its runs and its runs show how many answers changed between them. The paired counts, p and the Holm-adjusted p (over all {family} English {noun("all", family)}, whatever the group shown) are those of the exact McNemar test; * marks a Holm-adjusted p below {SIGNIFICANT:g}.</p>
      {copies(lambda group: table(site, data, group))}
      {"".join(not_run_list(site, data, group) for group in GROUPS)}
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <h3>The translation</h3>
      <p>The translator is {esc(translator_name)} (<code>{esc(translator["model"])}</code>) at effort {esc(translator["effort"])}; route: {esc(translator["route"])}, Claude Code version {esc(translator["claude_code"].removesuffix(" (Claude Code)"))}. Its maker has no decision model on our board.{maker_text} It was told to translate faithfully, keep the option letters and their order, not solve the question and not add or remove information (translation prompt version {esc(prompts["translate"]["version"])}).</p>
      <h3>The flags</h3>
      <p>In a separate request, the same model was shown each Turkish question, its English translation and the keyed option, and asked whether answering it correctly depends on Turkish wording, with the reasons (flag prompt version {esc(prompts["flag"]["version"])}). It flagged {flagged} of the {reading} questions; they are left out, and {kept} are kept. By reason, as a flagged question can have several:</p>
      <ul>{reasons}</ul>
      <p>No person checked the translations or the flags, and this is a limit of the method: a translation error, or a question whose answer still depends on Turkish wording that the model did not flag, would stay among the {kept} kept questions and could move a setup's accuracy in English. Both prompts in full are in {download} and {script}.</p>
      <h3>The structural check</h3>
      <p>A script ({script}, its check step) then compared each translation with its Turkish original: a problem is a missing translation, option letters other than the original's, an empty text or a different count of underline markup; a warning is a change in the numbering or the numbers, Turkish letters in the English, or an English text under half or over 2.5 times the Turkish length. It found problems in {len(problems)} question{"" if len(problems) == 1 else "s"} ({esc(joined([str(question) for question in problems]))}), already left out by the flags, so it left out no further question; its {structural["warnings"]:,} warnings leave out nothing. In all, the checks left out {flagged} of the {reading} questions and kept {kept}: their IDs are in {ids_download}, one per line, and in {download}.</p>
      <h3>Why the grammar questions are not translated</h3>
      <p>The Text tab's {grammar:,} grammar questions test Turkish grammar itself, so a translation would test something else, not the same question in another language. Only the {reading} reading questions were translated.</p>
      <h3>Asking the decision models</h3>
      <p>Each decision model is asked exactly as on the Text tab, with its own settings, one question per request, and with its option probabilities, except for one word of the System One instructions, the options heading and the question itself. The Text tab's instructions:</p>
      <blockquote><p>{esc(turkish_instructions)}</p></blockquote>
      <p>The English runs' instructions:</p>
      <blockquote><p>{esc(data["instructions"])}</p></blockquote>
      <p>The options follow the heading “{esc(data["options_heading"])}” instead of “{esc(TURKISH_OPTIONS_HEADING)}”, and the question and its options are the English translation. Prompt version {esc(data["prompt_version"])}; every English run used the translations with SHA-256 <code>{esc(data["translations_sha256"])}</code>.{renamed_text(site, data)}{"".join(" " + esc(note) for note in site.config["english_reading"].get("method_notes", []))}</p>{chat_method}
      <h3>Runs</h3>
      <p>One English run per setup; five where the setup's whole-bank Turkish repeats on the Text tab changed answers{whole_bank}. Here: {runs_text(site, data)}. The English runs are kept out of the leaderboard and its repeats.</p>
      <h3>The comparison</h3>
      <p>On the {kept} kept questions only: accuracy is the right answers over {kept} for the first English run and for the Text tab run (an invalid answer counts as not right), and the difference is how many points higher the English run scored than the Turkish one (negative where Turkish is higher). The paired test is the exact McNemar test on the questions only one of the two runs got right, with p adjusted by Holm's method over all {family} English {noun("all", family)}, decision and chat alike, whatever the group shown. Where a side has more than one run, its range is the lowest and highest accuracy over its runs, and its answers changed are the kept questions whose answer differs between them.</p>
      <h3>Why the translations are not published</h3>
      <p>The site never publishes question text, Turkish or English: the publisher owns the questions. {download} holds instead each reading question's ID, unit, whether it was kept, its flag reasons and the SHA-256 of its English text, with the translator and both prompts, so that a copy of these translations can be checked against it. Translating again with {script} need not give the same text word for word.</p>
    </section>{instructions(site, data)}{dont_know_info(site, idk, "".join(dont_know_table(site, idk_group(site, idk, group), shown(group)) for group in idk_groups)) if idk else ""}<div {DECISION_ONLY}>{dont_know_word_info(site, data, word_decision) if word_decision else ""}</div>{languages(site, data)}
    </details>"""
    return {PATH: site.page(PATH, "Turkish vs English",
                            f"The Text tab's {kept} kept reading questions in Turkish and in English: accuracy of {family} "
                            f"setups ({split}) in both languages, with paired tests, and their "
                            "non-hallucination.", body),
            OLD_PATH: redirect(site), PATH + KEPT_IDS: kept_ids(record)}
