"""The Experiments tab (experiments/): one card for each test beside the ranking, each with one line on what it measures
and a status label from the data: Hallucination (results.json dont_know and the chat setups still running), Web
grounding (web-grounding.json), PWS-Decisions (pws-decisions.json, with its setups still waiting) and the Artificial
Analysis comparison (page_config.json aa_decision_index). Page images is the top bar's Vision tab. The pages themselves
are unchanged."""

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
    found.append(("dont-know/", "Hallucination (\u201cBilmiyorum\u201d)",
                  f"The Turkish questions with a sixth option, \u201c{idk['option']}\u201d (I don't know): how often a model "
                  "says it does not know instead of answering wrong.",
                  (f"Running: {plural(len(running), 'chat setup')} still running in Turkish" if running else
                   f"Done: {plural(len(idk['models']), 'setup')}") + (f" · {bp.count(not_run)} not run" if not_run else "")))
    grounding = site.results.get("web_grounding")
    grounding_file = ROOT / "web-grounding.json"
    if grounding and grounding_file.exists():
        runs = len(json.loads(grounding_file.read_text(encoding="utf-8"))["runs"])
        found.append(("web-grounding/", "Web grounding",
                      f"One model with web search off and on: {grounding['names']['off']} against {grounding['names']['on']}.",
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


def build(site: Site) -> dict[str, str]:
    items = "".join(
        f'<li class="panel exp-card"><h2><a href="{rel(PATH, path)}">{esc(title)}</a></h2><p>{esc(what)}</p>'
        f'<p class="exp-status">{esc(status)}</p></li>' for path, title, what, status in cards(site))
    body = f"""    <section class="card">
      <h1>Experiments</h1>
      <p>Tests beside the ranking. Each has its own page and its own method; no score combines them with the Leaderboard.</p>
      <ul class="exp-cards">{items}</ul>
    </section>"""
    return {PATH: site.page(PATH, TITLE, "The tests beside the ranking: page images, hallucination, web grounding, "
                            "PWS-Decisions and the Artificial Analysis comparison, each with its status.", body)}
