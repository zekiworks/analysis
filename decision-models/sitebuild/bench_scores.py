"""Reading's bench-scores.json (at the site's root): the shared feed of the combined page (all-benches/, sitebuild/
all_benches.py), which each of the three benchmark sites publishes in one schema (project lead, bus #4057; schema #4062).
Its conventions follow the first file published, the Logic & Math site's (#4063 onward): runs as 'bench:run' strings,
sizes in billions with the active count equal to the total for a dense model, repo and commit null for a setup that ran
through an API and for Cygnet, ECE over 10 equal-width bins of the chosen option's probability, count-weighted.

This site measures five benches, so its file holds them under "benches", their keys kept from before the splits (the
combined page joins on them): reading-text, titled Reading · Turkish (results.json, the Leaderboard's rows, one per
model ID, kind and web search: the route never splits a model, Ümit #4270; all 2,198 Turkish questions, the one
All benches' Combined score uses); turkish-reading and turkish-grammar, Turkish Reading and Turkish Grammar (the same
rows on the reading units' and the grammar units' questions only, Ümit #4239); reading-english, Reading · English
(results.json english_reading: the same rows' first English run on the kept reading questions, and the English-only
setups); reading-vision, Reading · Vision (vision.json, condition B: the page image only; the models that read only text
are not on it). Each bench scores 0 = chance and 100 = every question right: (accuracy - mean of 1/k) / (1 - mean of
1/k) x 100, k each question's number of options. Every row carries name, the model's official name (Site.title, the
project lead's naming rule, Ümit #4445), and tag, how the row's setup ran ('API · with web', 'high · chat'; '' for none;
Site.tag), and model_key, the three sites' join key (#4243), unchanged: the setup name without its setting or route,
lower case, spaces as hyphens, dots kept, "(open)" dropped, "-with-web" after it for a setup with web search (#4253)."""

from __future__ import annotations

import json
from typing import Any

import benchmark_metrics as bm
import export_results as er
from sitebuild import leaderboard
from sitebuild.english_reading import english_only, setup_families
from sitebuild.names import model_key
from sitebuild.site import Site

PATH = "bench-scores.json"
TEXT_OPTIONS = 5  # every Text question has options A to E, in Turkish and in English
# The benches' titles (project lead, bus #4173); their keys stay reading-text and reading-vision.
TITLES = {"text": "Reading · Turkish", "english": "Reading · English", "vision": "Reading · Vision",
          "reading": "Turkish Reading", "grammar": "Turkish Grammar"}
# The Turkish parts (Ümit #4239): (bench key, results.json group, the questions in words).
PARTS = (("turkish-reading", "reading", "Turkish reading questions (units 1 to 6)"),
         ("turkish-grammar", "grammar", "Turkish grammar questions (units 7 to 20)"))


def run_key(run: dict[str, Any]) -> str:
    """A setup's model_key: its run's name's (model_key), with "-with-web" for a setup with web search (#4253), so a
    with-web row never joins the plain one."""
    return model_key(run["name"]) + ("-with-web" if run.get("perplexity_mode") else "")


def billions(value: int | None) -> float | None:
    return None if value is None else round(value / 1e9, 2)


def score(accuracy: float, chance: float) -> float:
    """The 0-100 score: 0 at chance, 100 with every question right."""
    return (accuracy - chance) / (1 - chance) * 100


def checkpoint(run: dict[str, Any]) -> tuple[str | None, str | None]:
    """The released checkpoint a setup ran (SIZES' repo and commit); none for a setup that ran through an API or a
    record that names none (Cygnet's)."""
    if run["billing"] != "local":
        return None, None
    size = er.SIZES[run["model"]]
    return size.get("repo"), size.get("commit")


def quantization(run: dict[str, Any]) -> str | None:
    """The precision a setup on our hardware ran at, as its hardware record writes it after the machine ("FP8 (block-128)"
    reads FP8); none for an API setup or a record without one."""
    if run["billing"] != "local" or "; " not in (run.get("hardware") or ""):
        return None
    return run["hardware"].split("; ", 1)[1].split(" (")[0]


def sizes(run: dict[str, Any]) -> tuple[float | None, float | None]:
    """Total and active parameters in billions; a dense model's active count is its total."""
    total, active = run.get("parameters"), run.get("active_parameters") or []
    return billions(total), billions(max(active)) if active else billions(total)


def text_rows(site: Site) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """The Text bench's rows: the Leaderboard's (one per model ID, kind and web search, its setup by the Leaderboard's
    rule, whichever route it ran: the route never splits a model, Ümit #4270), each with its other setups."""
    board = leaderboard.Board(site)
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for run in site.runs:
        groups.setdefault(board.key(run), []).append(run)
    return [leaderboard.choose(setups, lambda item: item) for setups in groups.values()]


def part_ece(site: Site, run_id: int, part: str) -> float | None:
    """A Text run's calibration error on one part's questions (Site.part of each question's unit), as its whole run's
    (results.json runs[].confidence.ece): the scored questions that carry a confidence, 10 equal-width bins."""
    answers = site.answer_runs[run_id]
    units = site.answers["questions"]["unit"]
    scored = [(answers["score"][index], int(answers["correct"][index])) for index in site.scored
              if site.part(units[index]) == part and answers["score"][index] is not None
              and answers["correct"][index] is not None]
    return bm.calibration(scored)["ece"] if scored else None


def text_bench(site: Site, part: tuple[str, str, str] | None = None) -> dict[str, Any]:
    """Reading · Turkish (reading-text, every Turkish question), or with part one of PARTS: the same rows on that
    part's questions, scored and calibrated on them."""
    total = site.results["questions"]
    models = []
    for run, others in text_rows(site):
        if part:
            group = run["groups"][part[1]]
            correct, questions = group["correct"], group["questions"]
            ece = part_ece(site, run["run"], part[1]) if run.get("confidence") else None
        else:
            correct, questions = site.accuracy(run)
            ece = (run.get("confidence") or {}).get("ece")
        repo, commit = checkpoint(run)
        params_total, params_active = sizes(run)
        models.append({
            "repo": repo, "commit": commit, "name": site.title(run), "tag": site.tag(run), "model_key": run_key(run),
            "maker": site.families[run["run"]]["maker"], "kind": "decision" if site.decision(run) else "chat",
            "params_total": params_total, "params_active": params_active, "quantization": quantization(run),
            "score_0_100": score(correct / questions, 1 / TEXT_OPTIONS),
            "raw": {"metric": "accuracy", "value": correct / questions, "questions": questions, "options": TEXT_OPTIONS},
            "calibration_error": ece, "improvement_points": None,
            "runs": [f"text:{item['run']}" for item in (run, *others)], "notes": run["access"]})
    count = models[0]["raw"]["questions"]
    return {"bench": part[0] if part else "reading-text", "title": TITLES[part[1] if part else "text"],
            "url": site.config["site_url"], "updated": site.results["updated"],
            "score": {"zero": f"chance: 1 of {TEXT_OPTIONS} options right on every question (accuracy 20%)",
                      "hundred": (f"every one of the {count:,} {part[2]} right (accuracy 100%)" if part else
                                  f"every one of the {total:,} Turkish reading and grammar questions right (accuracy 100%)")},
            "models": sorted(models, key=lambda model: -model["score_0_100"])}


def vision_bench(site: Site) -> dict[str, Any]:
    data = site.vision
    models = []
    for model in data["models"]:
        if model["kind"] != "image":
            continue
        got = model["conditions"]["B"]
        answers = data["answers"][f"{model['provider']}|{model['model']}|B"]
        # Each question's number of options, from the option probabilities its answer gave.
        chance = sum(1 / len(answer[1]) for answer in answers.values()) / len(answers)
        options = {len(answer[1]) for answer in answers.values()}
        run = site.by_id[model["a_run"]]
        repo, commit = checkpoint(run)
        params_total, params_active = sizes(run)
        models.append({
            "repo": repo, "commit": commit, "name": site.title(run), "tag": site.tag(run), "model_key": run_key(run), "maker": site.families[run["run"]]["maker"],
            "kind": "decision" if site.decision(run) else "chat", "params_total": params_total,
            "params_active": params_active, "quantization": quantization(run),
            "score_0_100": score(got["accuracy"], chance),
            "raw": {"metric": "accuracy", "value": got["accuracy"], "questions": got["questions"],
                    "options": options.pop() if len(options) == 1 else round(1 / chance, 3)},
            "calibration_error": got["ece"], "improvement_points": None,
            "runs": [f"vision:{item}" for item in got["runs"]], "notes": f"{run['access']}; the page image only (condition B)"})
    questions = data["subset"]["questions"]
    return {"bench": "reading-vision", "title": TITLES["vision"], "url": site.config["site_url"] + "vision/",
            "updated": data["generated_at"],
            "score": {"zero": "chance: 1 of each question's options right on every question (accuracy 20% with 5 options)",
                      "hundred": f"every one of the {questions:,} questions that depend on the printed page right, read "
                                 "from the page image alone (accuracy 100%)"},
            "models": sorted(models, key=lambda model: -model["score_0_100"])}


def english_ece(site: Site, run_id: int) -> float | None:
    """An English run's calibration error as the Text runs' (results.json runs[].confidence.ece): over its answers to
    the scored questions that carry a confidence, 10 equal-width bins (benchmark_metrics.calibration); None for a run
    without one."""
    answers = next(item for item in site.answers["english_runs"] if item["run"] == run_id)
    scored = [(answers["score"][index], int(answers["correct"][index])) for index in site.scored
              if answers["score"][index] is not None and answers["correct"][index] is not None]
    return bm.calibration(scored)["ece"] if scored else None


def english_bench(site: Site) -> dict[str, Any]:
    """Reading · English: the kept reading questions in English (results.json english_reading). One row per Text row
    with an English run: the English entry of the row's chosen Text run, else of its other runs in their order, its
    first English run scored; then each English-only setup (no Text tab run). The row's name, repo, maker, kind and size
    are its Text row's, so the combined page joins the two."""
    data = site.results["english_reading"]
    total = data["questions"]
    by_text = {entry["turkish_run"]: entry for entry in data["models"]}
    families = setup_families(site)
    models = []

    def add(entry: dict[str, Any], run: dict[str, Any], maker: str, kind: str) -> None:
        counts = entry["english"]
        repo, commit = checkpoint(run)
        params_total, params_active = sizes(run)
        models.append({
            "repo": repo, "commit": commit, "name": site.title(run), "tag": site.tag(run), "model_key": run_key(run),
            "maker": maker, "kind": kind,
            "params_total": params_total, "params_active": params_active, "quantization": quantization(run),
            "score_0_100": score(counts["accuracy"], 1 / TEXT_OPTIONS),
            "raw": {"metric": "accuracy", "value": counts["accuracy"], "questions": total, "options": TEXT_OPTIONS},
            "calibration_error": english_ece(site, entry["run"]), "improvement_points": None,
            "runs": [f"english:{item}" for item in entry["runs"]],
            "notes": f"{run['access']}; the kept reading questions in English"})

    for run, others in text_rows(site):
        entry = next((by_text[item["run"]] for item in (run, *others) if item["run"] in by_text), None)
        if entry is not None:
            add(entry, run, site.families[run["run"]]["maker"], "decision" if site.decision(run) else "chat")
    for entry in english_only(data):
        add(entry, entry, families[entry["run"]]["maker"], "decision" if site.decision(entry) else "chat")
    return {"bench": "reading-english", "title": TITLES["english"], "url": site.config["site_url"] + "english/",
            "updated": site.results["updated"],
            "score": {"zero": f"chance: 1 of {TEXT_OPTIONS} options right on every question (accuracy 20%)",
                      "hundred": f"every one of the {total:,} kept reading questions, translated into English, right "
                                 "(accuracy 100%)"},
            "models": sorted(models, key=lambda model: -model["score_0_100"])}


def benches(site: Site) -> list[dict[str, Any]]:
    """The five benches: Turkish (all), Turkish Reading, Turkish Grammar, English, Vision."""
    return [text_bench(site), *(text_bench(site, part) for part in PARTS), english_bench(site), vision_bench(site)]


def build(site: Site) -> dict[str, str]:
    return {PATH: json.dumps({"benches": benches(site)}, ensure_ascii=False, indent=1) + "\n"}
