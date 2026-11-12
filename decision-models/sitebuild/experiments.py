"""The Experiments tab (experiments/): first, under the page title, the repeat checks (results.json repeat_checks; the
project lead via Zeki #4831, #4838, #4844: at the top, one compact table per area, stacked, ranked by Run 2): for each
area (Turkish Text, English reading, Vision with the picture only) under its own heading and scope, a table in the
Leaderboard's layout (v3.css .lb-table): Rank over the rows with a Run 2, the model (maker dot in its family's colour,
official name with its tag, linked to its model page), Run 2 (the first repeat) and the first run as share and right
answers over the area's questions, the questions and the status; every run's ids, dates, settings and cost and the note
in the row's details box (site.js leaderboardDetails, as the Leaderboard's). Then one card
for each test beside the ranking, each with one line on what it measures and a status label from the data:
Hallucination (results.json dont_know and the chat setups still running), Web grounding (web-grounding.json),
PWS-Decisions (pws-decisions.json, with its setups still waiting) and the Artificial Analysis comparison
(page_config.json aa_decision_index). Page images is the top bar's Vision tab. The pages themselves are unchanged."""

from __future__ import annotations

import json
from typing import Any

import build_page as bp
from sitebuild.dont_know import running_setups
from sitebuild.english_reading import entry_href, setup_families, setup_run
from sitebuild.names import tag_html
from sitebuild.site import ROOT, Site, esc, family_icon, pct, rel
from sitebuild.vision import family as vision_family
from sitebuild.vision import text_run

PATH = "experiments/"
TITLE = "Experiments"


def plural(count: int, noun: str) -> str:
    return f"{bp.count(count)} {noun}{'' if count == 1 else 's'}"


def cards(site: Site) -> list[tuple[str, str, str, str]]:
    """(path, title, what it measures, status) of each experiment. Page images is the Vision tab of the top bar, not one."""
    found = []
    idk = site.results["dont_know"]
    running = running_setups(site)
    not_run = len(site.config["dont_know"].get("not_run") or [])
    found.append(("dont-know/", "Hallucination (\u201cI don't know\u201d)",
                  "The Turkish questions with a sixth option, \u201cI don't know\u201d: how often a model "
                  "says it does not know instead of answering wrong.",
                  (f"Running: {plural(len(running), 'chat setup')} still running in Turkish" if running else
                   f"Done: {plural(len(idk['models']), 'setup')}") + (f" · {bp.count(not_run)} not run" if not_run else "")))
    grounding = site.results.get("web_grounding")
    grounding_file = ROOT / "web-grounding.json"
    if grounding and grounding_file.exists():
        runs = len(json.loads(grounding_file.read_text(encoding="utf-8"))["runs"])
        found.append(("web-grounding/", "Web grounding",
                      f"One model with web search off and on: {site.plain(site.by_id[grounding['text_runs']['off']])} against "
                      f"{site.plain(site.by_id[grounding['text_runs']['on']])}.",
                      f"Done: {plural(runs, 'run')}"))
    pws_file = ROOT / "pws-decisions.json"
    if pws_file.exists():
        pws: dict[str, Any] = json.loads(pws_file.read_text(encoding="utf-8"))
        blocked = pws.get("blocked") or []
        needs = [word for word, needle in (("an API key", "key"), ("API credit", "credit"))
                 if any(needle in item["reason"] for item in blocked)]
        found.append(("pws-decisions/", "PWS-Decisions",
                      "Parallel Web Systems' benchmark of dated web facts, asked of the decision models and chat models; not "
                      "part of the Turkish ranking.",
                      f"Done: {plural(len(pws['setups']), 'setup')}"
                      + (f" · Waiting: {plural(len(blocked), 'setup')} need {' or '.join(needs)}" if blocked else "")))
    aa = site.config.get("aa_decision_index")
    if aa and (ROOT / "aa-decision-index" / "index.html").exists():
        ours = sum(1 for model in aa["models"] if model.get("run"))
        found.append(("aa-decision-index/", "Artificial Analysis comparison",
                      "Our numbers for the decision models of Artificial Analysis's Decision Index v1.0.",
                      f"Done: {bp.count(ours)} of its {plural(len(aa['models']), 'model')} in our benchmark"))
    return found


# How a run's cost was counted (results.json cost_basis), in a few words.
BASIS_WORDS = {"api": "API list price", "subscription": "subscription", "free tier": "the free tier's list price",
               "maker": "the maker's list price for the same model", "weights": "a host's list price for the same weights",
               "gpu": "GPU-time estimate"}
STATUS_WORDS = {"retained": "Retained", "queued": "Queued", "running": "Running", "done": "Done"}


def run_line(run: dict[str, Any]) -> str:
    """A first run's or repeat's ids and dates: 'run 957 · 10 November 2026', 'runs 2, 5 · 27 October 2026',
    'pass 2, run 3 · 11 November 2026'."""
    ids = run.get("runs") or [run["run"]]
    dates = run.get("dates") or [run["date"]]
    named = f"run{'s' if len(ids) > 1 else ''} {', '.join(map(str, ids))}"
    return (f"pass {run['pass']}, {named}" if "pass" in run else named) + " · " + ", ".join(bp.long_date(day) for day in dates)


def settings_text(run: dict[str, Any]) -> str:
    """Where a run ran and how its cost was counted: its hardware and number format, or its access route, then the cost."""
    where = run["hardware"] or run["access"] or "not recorded"
    if run.get("usd") is not None:
        cost = f"{bp.usd(run['usd'])} at {BASIS_WORDS[run['cost_basis']]}"
    elif run.get("cost_basis"):
        cost = BASIS_WORDS[run["cost_basis"]]
    else:
        cost = "not counted (our hardware)"
    return f"{where}; cost: {cost}"


def setup_of(site: Site, area: str, entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], str]:
    """An entry's setup as a run (for its name and tag), its model family (maker and colour) and its link from this page:
    a Text entry's first run is its Text tab run; an English entry's is the English reading model's first run (its model
    page's English section, as elsewhere); a Vision entry's model is vision.json's of that name (its Text tab run's page)."""
    if area == "text":
        run = site.by_id[entry["first"]["run"]]
        return run, site.families[run["run"]], rel(PATH, site.model_path(run))
    if area == "english":
        model = next(item for item in site.results["english_reading"]["models"] if item["run"] == entry["first"]["run"])
        run = setup_run(site, model)
        return run, setup_families(site)[run["run"]], entry_href(site, PATH, model)
    model = next(item for item in site.vision["models"] if item["name"] == entry["name"])
    run = text_run(site, model)
    return run, vision_family(site, model), rel(PATH, site.model_path(run))


def score_cell(run: dict[str, Any] | None, questions: int) -> str:
    """A run's share right, its right answers over the questions under it; '–' for a run not made yet, never 0."""
    if run is None:
        return '<span class="rc-score" title="Not run yet">\u2013</span>'
    return (f'<span class="rc-score">{pct(run["right"] / questions)}<span class="small">{bp.count(run["right"])}/'
            f'{bp.count(questions)}</span></span>')


def repeat_checks(site: Site) -> str:
    """The Repeat checks section, first on the page: per area its heading with its scope, then its table (Rank · Model ·
    Run 2 · First run · Questions · Status; Questions and Status from 900 px, below it the heading giving the questions
    and a line under the name the status, so a phone keeps four columns). Run 2 is the area's
    second full run, the entry's first repeat (repeat 2, or Vision's pass 2), never the best repeat or a mean of them
    (Zeki #4838, #4844). Rows with a Run 2 come first, by its right answers, highest first, ranked 1, 2, 3 without
    repeats (#4630; equal scores keep the area's order); the rows without one (queued, running) follow unranked ('–'), in
    the area's order. Each row's runs (repeats 3 to 5 too), dates, settings, cost and note are in its details box, opened
    by its Details key, a tap, the pointer or the focus (site.js leaderboardDetails); the line that the published scores
    stay the first run's under the tables."""
    section = site.results.get("repeat_checks")
    if not section:
        return ""
    tables = []
    for area in section["areas"]:
        entries = [entry for entry in section["entries"] if entry["area"] == area["area"]]
        if not entries:
            continue
        questions = area["questions"]
        boxes = {id(entry): f"rc-{area['area']}-{index}-box" for index, entry in enumerate(entries, 1)}
        ran = sorted((entry for entry in entries if entry["repeats"]), key=lambda entry: -entry["repeats"][0]["right"])
        ordered = [(rank, entry) for rank, entry in enumerate(ran, 1)] + [
            (None, entry) for entry in entries if not entry["repeats"]]
        rows = []
        for rank, entry in ordered:
            first, repeats = entry["first"], entry["repeats"]
            run, family, href = setup_of(site, area["area"], entry)
            box = boxes[id(entry)]
            # One line per run: its ids and dates, then where it ran and its cost; each repeat by its run number in the
            # data (repeat 2 to 5, Vision's pass 2), else by its place after the first run.
            lines = [f"First run: {esc(run_line(first))}; {esc(settings_text(first))}."]
            lines += [f"Run {item.get('repeat') or item.get('pass') or number}: {esc(run_line(item))}"
                      + (f" · {bp.count(item['picks_differ'])} of {bp.count(questions)} picks differ"
                         if "picks_differ" in item else "") + f"; {esc(settings_text(item))}."
                      for number, item in enumerate(repeats, 2)]
            lines += [f"Questions: {bp.count(questions)}", esc(entry["note"])]
            details = (f'<div class="lb-box" id="{box}" role="group" aria-label="{esc(site.plain(run))}: details">'
                       f'<p><strong>{site.shown(run)}</strong> · {esc(family["maker"])}</p>'
                       + "".join(f"<p>{line}</p>" for line in lines)
                       + f'<p><a href="{href}">Open its model page \u2192</a></p></div>')
            rows.append(
                f'<tr data-box="{box}"><td class="num rank">{rank or "–"}</td>'
                f'<td class="model"><i class="lb-dot" style="background:{family["colour"]}" '
                f'title="{esc(family["maker"])}"></i>{family_icon(family["name"])}<a class="model-name" href="{href}" '
                f'title="{esc(site.plain(run))}" aria-describedby="{box}">{esc(site.title(run))}</a>'
                f'{tag_html(site.tag(run))}<span class="small rc-status-line">{STATUS_WORDS[entry["status"]]}</span>'
                f'{details}</td>'
                f'<td class="num">{score_cell(repeats[0] if repeats else None, questions)}</td>'
                f'<td class="num">{score_cell(first, questions)}</td>'
                f'<td class="num lb-wide">{bp.count(questions)}</td>'
                f'<td class="rc-status lb-wide">{STATUS_WORDS[entry["status"]]}</td></tr>')
        heading = f"rc-{area['area']}"
        tables.append(
            f'<h3 class="rc-area" id="{heading}">{esc(area["title"])}<span class="small">{esc(area["scope"])}</span></h3>'
            f'<div class="table-wrap"><table class="lb-table rc-table" aria-labelledby="{heading}"><thead><tr>'
            '<th scope="col" class="num">Rank</th><th scope="col">Model</th>'
            '<th scope="col" class="num">Run 2<span class="small">% · right / questions</span></th>'
            '<th scope="col" class="num">First run<span class="small">% · right / questions</span></th>'
            '<th scope="col" class="num lb-wide">Questions</th><th scope="col" class="lb-wide">Status</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')
    return f"""
    <section class="card" id="repeat-checks">
      <h1>Experiments</h1>
      <h2>Repeat checks</h2>
      {"".join(tables)}
      <p class="note">The published scores stay each setup's first run; a repeat changes no score or rank. Data: <a href="{rel(PATH, "results.json")}">results.json</a> (<code>repeat_checks</code>).</p>
    </section>"""


def build(site: Site) -> dict[str, str]:
    items = "".join(
        f'<li class="panel exp-card"><h2><a href="{rel(PATH, path)}">{esc(title)}</a></h2><p>{esc(what)}</p>'
        f'<p class="exp-status">{esc(status)}</p></li>' for path, title, what, status in cards(site))
    checks = repeat_checks(site)
    title = "" if checks else "\n      <h1>Experiments</h1>"
    body = f"""{checks}
    <section class="card" id="tests">{title}
      <h2>Tests beside the ranking</h2>
      <ul class="exp-cards">{items}</ul>
    </section>"""
    return {PATH: site.page(PATH, TITLE, "The repeat checks of the top decision models, then the tests beside the ranking: "
                            "page images, hallucination, web grounding, PWS-Decisions and the Artificial Analysis "
                            "comparison, each with its status.", body)}
