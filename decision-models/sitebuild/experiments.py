"""The Experiments tab (experiments/): one card for each test beside the ranking, each with one line on what it measures
and a status label from the data: Hallucination (results.json dont_know and the chat setups still running), Web
grounding (web-grounding.json), PWS-Decisions (pws-decisions.json, with its setups still waiting) and the Artificial
Analysis comparison (page_config.json aa_decision_index). Page images is the top bar's Vision tab. The pages themselves
are unchanged. After the cards, the repeat checks (results.json repeat_checks): one table, rows grouped by area, each
setup's first run and its repeat as right answers over the area's questions, with its status; the runs' ids, dates,
settings and cost basis under the name."""

from __future__ import annotations

import json
from typing import Any

import build_page as bp
from sitebuild.dont_know import running_setups
from sitebuild.site import ROOT, Site, esc, rel

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


def repeat_checks(site: Site) -> str:
    """The Repeat checks section: one table, rows grouped by area, each entry's first run and repeat(s) as right answers
    over the area's questions and its status, the runs and their settings under the name; the line that the published
    scores stay the first run's under the table."""
    section = site.results.get("repeat_checks")
    if not section:
        return ""
    rows = []
    for area in section["areas"]:
        entries = [entry for entry in section["entries"] if entry["area"] == area["area"]]
        if not entries:
            continue
        rows.append(f'<tr><th scope="rowgroup" colspan="3">{esc(area["title"])}<span class="small">{esc(area["scope"])}</span></th></tr>')
        for entry in entries:
            first, repeats = entry["first"], entry["repeats"]
            questions = bp.count(area["questions"])
            lines = [f'<span class="small">First: {esc(run_line(first))}</span>']
            lines += [f'<span class="small">Repeat: {esc(run_line(run))}'
                      + (f" · {bp.count(run['picks_differ'])} of {questions} picks differ" if "picks_differ" in run else "")
                      + "</span>" for run in repeats]
            settings = [f"First: {settings_text(first)}."] + [f"Repeat{'' if len(repeats) == 1 else ' ' + str(index)}: "
                                                             f"{settings_text(run)}." for index, run in enumerate(repeats, 1)]
            details = (f'<details class="chart-more"><summary>Settings</summary><p class="note">{esc(" ".join(settings))} '
                       f'{esc(entry["note"])}</p></details>')
            # Compact (no spaces around the slash, none after the arrow) so that the table fits a 375 px screen beside
            # the phone layout's fixed first column.
            values = [f"{bp.count(first['right'])}/{questions}"] + [
                f"→{bp.count(run['right'])}/{questions}" for run in repeats] + ([] if repeats else ["→—"])
            rows.append(f'<tr><td><span class="model-name">{esc(site.title({"name": entry["name"]}))}</span>{"".join(lines)}'
                        f'{details}</td><td class="num">{"<br>".join(values)}</td>'
                        f'<td>{STATUS_WORDS[entry["status"]]}</td></tr>')
    return f"""
    <section class="card" id="repeat-checks">
      <h2>Repeat checks</h2>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">Model</th><th scope="col" class="num">First run → Repeat<span class="small">right/questions</span></th><th scope="col">Status</th></tr></thead>
      <tbody>{"".join(rows)}</tbody></table></div>
      <p class="note">The published scores stay each setup's first run; a repeat changes no score or rank. Data: <a href="{rel(PATH, "results.json")}">results.json</a> (<code>repeat_checks</code>).</p>
    </section>"""


def build(site: Site) -> dict[str, str]:
    items = "".join(
        f'<li class="panel exp-card"><h2><a href="{rel(PATH, path)}">{esc(title)}</a></h2><p>{esc(what)}</p>'
        f'<p class="exp-status">{esc(status)}</p></li>' for path, title, what, status in cards(site))
    body = f"""    <section class="card">
      <h1>Experiments</h1>
      <ul class="exp-cards">{items}</ul>
    </section>{repeat_checks(site)}"""
    return {PATH: site.page(PATH, TITLE, "The tests beside the ranking: page images, hallucination, web grounding, "
                            "PWS-Decisions and the Artificial Analysis comparison, each with its status, and the repeat "
                            "checks.", body)}
