"""The Leaderboard (the home page's table, #leaderboard), as on the Backgammon site: one row per model at its highest
reasoning setting, a fixed rule and never the best score, with each row's other setups behind an expander and every
value of a row and of its details box from its one setup. Three parts, one table each, switched above the table
(site.js): Turkish, the 2,198-question ranking (results.json runs); English, the English setups on the kept reading
questions (english_reading.models, each with its Text tab run's settings, and the English-only setups,
english_reading.english_only, with no Text tab run); Both, Turkish and English accuracy on those same questions, as
turkish-vs-english/ computes them (paired setups only). A row is a model ID, its kind (chat or decision model) and web
search (a setup with web is its own row); a dated checkpoint joins its original's row only through page_config.json's
leaderboard.dated_checkpoints. Every row carries its rank among all models, among its kind and, for a small model
(Site.small), among the small models, so the filter (All · Chat models · Decision models · Small models, site.js) shows
the ranks of the rows in view."""

from __future__ import annotations

from typing import Any

import benchmark_metrics as bm
import build_page as bp
from sitebuild.english_reading import (BASIS_WORDS, english_only, entry_href, idk_key, setup_families, setup_run)
from sitebuild.site import (NOT_MEASURED, Site, billions, cost_missing, cost_per, cost_value, esc, family_icon,
                            parameters_text, pct, rel)

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
PARTS = (("english", "English"), ("turkish", "Turkish"), ("both", "Both"))
DEFAULT_PART = "turkish"
FILTERS = (("all", "All"), ("chat", "Chat models"), ("decision", "Decision models"), ("small", "Small models"))
DEFAULT_FILTER = "decision"
TYPE_LABEL = {True: "decision model", False: "chat model"}


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
        self.option = site.results["dont_know"]["option"]
        self.english_option = self.english["dont_know"]["option"]
        self.rated = {model["original_run"]: model for model in site.results["dont_know"]["models"]}
        idk = self.english["dont_know"]
        self.english_rated = {idk_key(model): model["english"] for model in [*idk["models"], *english_only(idk)]}

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


def ranks(entries: list[tuple[int, bool]]) -> list[int]:
    """Each entry's rank (score, kind) among all entries: 1 + the number with a higher score; ties share a rank."""
    return [1 + sum(other > score for other, _ in entries) for score, _ in entries]


def name_of(site: Site, run: dict[str, Any]) -> str:
    name = site.row_name(run)
    return f"{name} (with web)" if run["perplexity_mode"] and "with web" not in name else name


def setting(site: Site, run: dict[str, Any]) -> str | None:
    """The setting the record has, in words: its variant where another setup of the model ID has one, its reasoning
    level and its request size ("high reasoning, 16 per request"), and where it ran ("our GPU" or "API") where that
    tells it apart from another setup of the model ID. A decision model sends no reasoning level and no request size:
    only its variant or where it ran, when they tell it apart. Nothing the record lacks."""
    same = [other for other in site.runs if other["model"] == run["model"] and other["run"] != run["run"]]
    name = name_of(site, run).casefold()
    where = lambda item: "our GPU" if item["billing"] == "local" else "API"  # noqa: E731
    # A variant or a place the row's name already says ("with web", "local GPU", "API") is not repeated.
    parts = [run["variant"]] if run.get("variant") and same and run["variant"].casefold() not in name else []
    if not site.decision(run):
        if run.get("reasoning"):
            parts.append(bp.reasoning_label(run["reasoning"]))
        parts.append(f"{bp.count(run['questions_per_request'])} per request")
    if any(where(other) != where(run) for other in same) and not any(word in name for word in ("gpu", "api")):
        parts.append(where(run))
    return ", ".join(parts) or None


def under(site: Site, run: dict[str, Any]) -> str:
    """Under the name: maker · chat model / decision model · the setting the record has (setting)."""
    return " · ".join(filter(None, (setup_families(site)[run["run"]]["maker"], TYPE_LABEL[site.decision(run)],
                                    setting(site, run))))


def bar(correct: int, total: int, colour: str, kind: str = "") -> str:
    """The main-score bar from 0 to 100% with its Wilson 95% interval as the whisker."""
    low, high = bm.wilson_interval(correct, total)
    return (f'<span class="lb-bar{kind}"><span class="lb-fill" style="width:{100 * correct / total:.2f}%;background:{colour}">'
            f'</span><span class="lb-whisker" style="left:{100 * low:.2f}%;width:{100 * (high - low):.2f}%"></span></span>')


def interval(correct: int, total: int) -> str:
    low, high = bm.wilson_interval(correct, total)
    return f"(95%: {100 * low:.1f}\u2013{pct(high)})"


def cost_text(site: Site, run: dict[str, Any], value: float | None, basis: str | None, upper: bool) -> str | None:
    if value is None:
        return None
    mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if upper else ""
    words = f" ({esc(BASIS_WORDS[basis])})" if basis in BASIS_WORDS else ""
    return f"Cost {cost_value(value, mark)} {cost_per()}{words}"


def wide(value: str) -> str:
    return f'<td class="num lb-wide">{value}</td>'


def details(site: Site, run: dict[str, Any], box: str, lines: list[str | None], answers: str) -> str:
    """A setup's details box: its name line, its model's size (parameters_text), then the lines the data has (never
    "n/a"), then the link to its answers (an English-only setup, with no Text tab run and no model page: its row on the
    English reading page)."""
    head = " · ".join([f"<strong>{esc(name_of(site, run))}</strong>", esc(under(site, run))])
    link = "Open its answers" if run["run"] in site.by_id else "Open its English results"
    body = [head, f"Parameters: {esc(parameters_text(run))}", *lines, f'<a href="{answers}">{link} \u2192</a>']
    return (f'<div class="lb-box" id="{box}" role="group" aria-label="{esc(name_of(site, run))}: details">'
            + "".join(f"<p>{line}</p>" for line in body if line) + "</div>")


def turkish(site: Site, board: Board) -> tuple[list[str], list[str], int]:
    """The Turkish part: the head cells, the body rows and the number of model rows."""
    total, digits = board.total, site.config["percent_digits"]
    sure = pct(site.config["threshold"], 0)

    def facts(run: dict[str, Any]) -> tuple[list[str | None], list[str]]:
        correct, questions = accuracy(run)
        model = board.rated.get(run["run"])
        rate = None if model is None or model["non_hallucination"] is None else pct(model["non_hallucination"], digits)
        kept = (run.get("confidence") or {}).get("sure") if site.decision(run) else None
        value = bp.per_thousand(run)
        lines = [
            f"Accuracy {pct(correct / questions)} {interval(correct, questions)}",
            f"Reading {pct(share(run, 'reading'))} · grammar {pct(share(run, 'grammar'))}",
            f"Non-hallucination with \u201c{esc(board.option)}\u201d: {rate}" if rate else None,
            (f"Kept at {sure} confidence with no observed mistakes: {pct(kept['questions'] / questions)}"
             if kept["correct"] == kept["questions"] else
             f"Kept at {sure} confidence: {pct(kept['questions'] / questions)}, {bp.count(kept['questions'] - kept['correct'])} "
             f"of them wrong") if kept and kept["questions"] else None,
            " · ".join(filter(None, (cost_text(site, run, value, run.get("cost_basis"), bool(run.get("cost_upper_bound"))),
                                     bp.count(run["questions_per_request"]) + " question"
                                     + ("" if run["questions_per_request"] == 1 else "s") + " per request"))),
        ]
        hall = ('<span class="nm">Not run</span>' if model is None else rate or '<span class="nm">No rate</span>')
        mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if run.get("cost_upper_bound") else ""
        cost = (cost_missing(run) if value is None else
                f'{cost_value(value, mark)}<span class="small">{esc(BASIS_WORDS[run["cost_basis"]])}</span>')
        cells = [pct(share(run, "reading")), pct(share(run, "grammar")), hall, cost]
        return lines, cells

    def score(run: dict[str, Any]) -> tuple[str, int]:
        correct, questions = accuracy(run)
        colour = site.families[run["run"]]["colour"]
        return f'{bar(correct, questions, colour)}<span class="lb-value">{pct(correct / questions)}</span>', correct

    rows = board.turkish_rows()
    heads = ["Reading", "Grammar", f"Non-hallucination<span class=\"small\">with \u201c{esc(board.option)}\u201d</span>",
             f"Cost<span class=\"small\">{cost_per()}</span>"]
    body = table_rows(site, board, "tr", rows, lambda run: run, facts, score,
                      lambda run: site.model_path(run))
    return [f"Accuracy<span class=\"small\">{bp.count(total)} questions, 95% interval</span>", *heads], body, len(rows)


def english(site: Site, board: Board, both: bool) -> tuple[list[str], list[str]]:
    """The English part (both False) or the Both part: the head cells and the body rows."""
    kept, digits = board.kept, site.config["percent_digits"]
    run_of = lambda model: setup_run(site, model)  # noqa: E731

    def facts(model: dict[str, Any]) -> tuple[list[str | None], list[str]]:
        en, tr = model["english"], model.get("turkish")
        held = board.english_rated.get(model.get("turkish_run", model["run"]))
        rate = None if held is None or held["non_hallucination"] is None else pct(held["non_hallucination"], digits)
        cost = model["cost"]["english"]
        value = cost["per_1000"] if cost else None
        size = (model["latency"].get("english") or {}).get("questions_per_request")
        lines = ([f"Turkish {pct(tr['accuracy'])} {interval(tr['right'], kept)} · English {pct(en['accuracy'])} "
                  f"{interval(en['right'], kept)}, on the same {bp.count(kept)} kept reading questions",
                  f"English minus Turkish: {100 * model['difference']:+.1f} points"] if both else
                 [f"Accuracy in English {pct(en['accuracy'])} {interval(en['right'], kept)}, {bp.count(kept)} kept reading questions",
                  f"Non-hallucination with \u201c{esc(board.english_option)}\u201d: {rate}" if rate else None,
                  " · ".join(filter(None, (cost_text(site, run_of(model), value, cost["basis"] if cost else None,
                                                     bool(cost and cost.get("upper_bound"))),
                                           f"{bp.count(size)} question{'' if size == 1 else 's'} per request" if size else None))),
                  # An English-only setup (no Text tab run, no model page): said so, with how it was called.
                  *(["English only: no Text tab run, so not in the Turkish and Both parts",
                     f"How we called it: {esc(model['access'])}",
                     "Confidence: not measured" if model["provider"] == "vllm-plain" else None]
                    if tr is None else [])])
        if both:
            cells = [pct(tr["accuracy"]), pct(en["accuracy"]), f"{100 * model['difference']:+.1f}"]
        else:
            hall = ('<span class="nm">Not run</span>' if held is None else rate or '<span class="nm">No rate</span>')
            mark = f'{site.config["first_cost_marks"]["upper"]["mark"]} ' if cost and cost.get("upper_bound") else ""
            money = (cost_missing(run_of(model)) if value is None else
                     f'{cost_value(value, mark)}<span class="small">{esc(BASIS_WORDS[cost["basis"]])}</span>')
            cells = [hall, money]
        return lines, cells

    def score(model: dict[str, Any]) -> tuple[str, int]:
        colour = setup_families(site)[run_of(model)["run"]]["colour"]
        en, tr = model["english"], model.get("turkish")
        if both:
            return (f'{bar(tr["right"], kept, colour)}{bar(en["right"], kept, colour, " lb-en")}'
                    f'<span class="lb-value">{pct(tr["accuracy"])}<span class="small">{pct(en["accuracy"])}</span></span>',
                    tr["right"])
        return f'{bar(en["right"], kept, colour)}<span class="lb-value">{pct(en["accuracy"])}</span>', en["right"]

    rows = board.english_rows(both)
    if both:
        heads = [f"Turkish · English<span class=\"small\">{bp.count(kept)} questions, 95% intervals</span>", "Turkish",
                 "English", "Difference<span class=\"small\">points, English minus Turkish</span>"]
    else:
        heads = [f"Accuracy in English<span class=\"small\">{bp.count(kept)} questions, 95% interval</span>",
                 f"Non-hallucination<span class=\"small\">with \u201c{esc(board.english_option)}\u201d</span>",
                 f"Cost<span class=\"small\">{cost_per()}</span>"]
    body = table_rows(site, board, "bo" if both else "en", rows, run_of, facts, score,
                      lambda model: entry_href(site, "", model))
    return heads, body


def table_rows(site: Site, board: Board, prefix: str, rows: list[tuple[dict[str, Any], list[dict[str, Any]]]], run_of: Any,
               facts: Any, score: Any, answers: Any) -> list[str]:
    """The body rows of one part: each model row (rank, maker dot and icon, name and its expander, the score, the wide
    cells; its details box in the name cell, the only place its maker · kind · setting shows: project lead, bus #3039),
    then its other setups' rows, hidden, each with its setting under its name, the one thing that tells it apart."""
    scored = [(item, others, *score(item)) for item, others in rows]
    scored.sort(key=lambda entry: (-entry[3], run_of(entry[0])["run"]))
    kinds = [site.decision(run_of(item)) for item, *_ in scored]
    small = [site.small(run_of(item)) for item, *_ in scored]
    every = ranks([(entry[3], kind) for entry, kind in zip(scored, kinds)])
    by_kind = {}
    for kind in (True, False):
        mine = [index for index, other in enumerate(kinds) if other == kind]
        for index, rank in zip(mine, ranks([(scored[index][3], kind) for index in mine])):
            by_kind[index] = rank
    mine = [index for index, flag in enumerate(small) if flag]
    by_small = dict(zip(mine, ranks([(scored[index][3], True) for index in mine])))
    out = []
    for index, (item, others, cell, _) in enumerate(scored):
        run = run_of(item)
        family = setup_families(site)[run["run"]]
        kind = "decision" if kinds[index] else "chat"
        row_id = f"lb-{prefix}-{index + 1}"
        box = f"{row_id}-box"
        lines, cells = facts(item)
        checkpoints = sorted({run_of(other)["model"] for other in others if run_of(other)["model"] != run["model"]})
        if checkpoints:
            lines.append("With its dated checkpoint " + ", ".join(esc(model) for model in checkpoints)
                         + " under its other settings")
        sub_ids = [f"{row_id}-{number}" for number in range(1, len(others) + 1)]
        more = (f'<button type="button" class="lb-more needs-js" aria-expanded="false" aria-controls="{" ".join(sub_ids)}">'
                f'{len(others)} other setting{"s" if len(others) > 1 else ""}</button>' if others else "")
        name = name_of(site, run)
        out.append(
            f'<tr data-kind="{kind}"{" data-small" if small[index] else ""} data-box="{box}"><td class="num rank" '
            f'data-rank-all="{every[index]}" data-rank-{kind}="{by_kind[index]}"'
            f'{f" data-rank-small={chr(34)}{by_small[index]}{chr(34)}" if small[index] else ""}>{every[index]}</td><td class="model">'
            f'<i class="lb-dot" style="background:{family["colour"]}" title="{esc(family["maker"])}"></i>{family_icon(family["name"])}'
            f'<a class="model-name" href="{answers(item)}" title="{esc(name)}" aria-describedby="{box}">{esc(name)}</a>'
            f'{more}'
            f'{details(site, run, box, lines, answers(item))}</td><td class="lb-score">{cell}</td>'
            + "".join(wide(value) for value in cells) + "</tr>")
        for sub_id, other in zip(sub_ids, others):
            other_run = run_of(other)
            other_lines, other_cells = facts(other)
            other_box = f"{sub_id}-box"
            out.append(
                f'<tr class="lb-sub" id="{sub_id}" hidden data-kind="{kind}"{" data-small" if site.small(other_run) else ""} '
                f'data-box="{other_box}"><td class="num"></td>'
                f'<td class="model"><a class="model-name" href="{answers(other)}" title="{esc(name_of(site, other_run))}" '
                f'aria-describedby="{other_box}">'
                f'{esc(name_of(site, other_run))}</a><span class="small">'
                f'{esc(setting(site, other_run) + " · ") if setting(site, other_run) else ""}other setting of '
                f'{esc(name)}</span>{details(site, other_run, other_box, other_lines, answers(other))}</td>'
                f'<td class="lb-score">{score(other)[0]}</td>' + "".join(wide(value) for value in other_cells) + "</tr>")
    return out


def table(part: str, heads: list[str], body: list[str], caption: str) -> str:
    head = "".join(f'<th scope="col" class="num lb-wide">{text}</th>' for text in heads[1:])
    return (f'<div class="table-wrap"><table class="lb-table" data-part="{part}"><caption class="visually-hidden">{esc(caption)}'
            f'</caption><thead><tr><th scope="col" class="num">#</th><th scope="col">Model</th>'
            f'<th scope="col" class="lb-score">{heads[0]}</th>{head}</tr></thead><tbody>{"".join(body)}'
            "</tbody></table></div>")


def meaning(part: str, total: int, kept: int) -> str:
    """What the score means, the one line above each part's table."""
    return {
        "turkish": f"Accuracy: the share of the {bp.count(total)} Turkish questions answered right, with its 95% interval "
                   "as the whisker; higher is better.",
        "english": f"Accuracy in English: the share of the {bp.count(kept)} kept reading questions, translated, answered "
                   "right, with its 95% interval as the whisker; higher is better.",
        "both": f"Turkish (solid) and English (striped) accuracy on the same {bp.count(kept)} kept reading questions, with "
                "95% intervals, ranked by Turkish, as on English and Turkish.",
    }[part]


def model_count(site: Site) -> int:
    """The number of models on the Turkish part: its rows."""
    return len(Board(site).turkish_rows())


def chosen(site: Site) -> dict[str, list[int]]:
    """For every row with several setups, the chosen run first, then the others."""
    return {name_of(site, run): [run["run"], *(other["run"] for other in others)]
            for run, others in Board(site).turkish_rows() if others}


def leaderboard(site: Site, about: str = "about/#leaderboard") -> str:
    """The Leaderboard's controls in one row (the part switch, the filter, the All setups key), then each part's meaning
    line and table (Turkish shown first, Decision models the default filter, site.js) and the row rule line. The All
    setups panel (today's full ranking with its tabs, #all-setups) follows it in index.html."""
    board = Board(site)
    tr_heads, tr_body, _ = turkish(site, board)
    en_heads, en_body = english(site, board, False)
    bo_heads, bo_body = english(site, board, True)
    parts = {"turkish": table("turkish", tr_heads, tr_body, "One row per model: Turkish accuracy"),
             "english": table("english", en_heads, en_body, "One row per model: English accuracy"),
             "both": table("both", bo_heads, bo_body, "One row per model: Turkish and English accuracy")}
    keys = lambda name, options, current: "".join(  # noqa: E731
        f'<button type="button" class="key" data-lb-{name}="{value}" aria-pressed="{str(value == current).lower()}">'
        f'{esc(label)}</button>' for value, label in options)
    controls = (f'<div class="lb-controls needs-js"><span class="keys" role="group" aria-label="Part of the test">'
                f'{keys("part", PARTS, DEFAULT_PART)}</span><span class="keys" role="group" aria-label="Models">'
                f'{keys("filter", FILTERS, DEFAULT_FILTER)}</span><button type="button" class="key lb-all-key" '
                'data-lb-all aria-pressed="false" aria-controls="all-setups">All setups</button></div>')
    panels = "".join(f'<div class="lb-part" data-lb-part="{part}"{"" if part == DEFAULT_PART else " hidden"}>'
                     f'<p class="chart-sub lb-meaning">{esc(meaning(part, board.total, board.kept))}</p>{parts[part]}</div>'
                     for part, _ in PARTS)
    return (f'{controls}<div class="lb-models" data-lb-view="models">{panels}'
            f'<p class="table-note lb-rule">{esc(ROW_LINE)} <a href="{about}">How rows are chosen</a></p>'
            f'<p class="table-note lb-small-line" data-lb-small hidden>{esc(site.small_line())}</p></div>')


def about_text(site: Site, origin: str) -> str:
    """The leaderboard rules for the About page: the row rule, the dated-checkpoint map, the ranks and the whiskers."""
    checkpoints = site.config["leaderboard"]["dated_checkpoints"]
    mapped = "; ".join(f"<code>{esc(dated)}</code> is listed under <code>{esc(original)}</code>, by this map"
                       for dated, original in checkpoints.items())
    return (f"<p>{esc(RULE)}</p>"
            + (f"<p>The dated-checkpoint map (page_config.json, leaderboard.dated_checkpoints), the only model IDs "
               f"listed under another: {mapped}. The row shows the original; the checkpoint's setups sit under its other "
               "settings.</p>" if mapped else "")
            + "<p>Ranks show observed scores; small gaps need not be meaningful. # is the rank among the models in view: "
            "All ranks every model; Chat models and Decision models rank within their kind; Small models ranks the "
            f"models of at most {esc(billions(site.small_max))} parameters in total, as their makers disclose them, chat "
            "and decision models together. Tied scores share a rank. Each row's details box gives its model's size and "
            "the model page its source.</p>"
            "<p>Each bar runs from 0 to 100%; its whisker is the Wilson 95% interval of the accuracy, the interval each "
            "setup's page gives. The paired tests behind the full ranking's letters are on "
            f'<a href="{rel(origin, "method/")}">Method</a>.</p>'
            f'<p>{NOT_MEASURED} or "Not run" in a column: the setup has no such value; the details box leaves such a line '
            "out.</p>")
