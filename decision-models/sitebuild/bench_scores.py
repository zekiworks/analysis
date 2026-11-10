"""Reading's bench-scores.json (at the site's root): the shared feed of the combined page (all-benches/, sitebuild/
all_benches.py), which each of the three benchmark sites publishes in one schema (project lead, bus #4057; schema #4062).
Its conventions follow the first file published, the Logic & Math site's (#4063 onward): runs as 'bench:run' strings,
sizes in billions with the active count equal to the total for a dense model, repo and commit null for a setup that ran
through an API and for Cygnet, ECE over 10 equal-width bins of the chosen option's probability, count-weighted.

This site measures two benches, so its file holds both under "benches": Text (results.json, the Leaderboard's rows split
by route, so a model's setup on our hardware and its API setup are rows of their own) and Vision (vision.json, condition
B: the page image only; the models that read only text are not on it). Each bench scores 0 = chance and 100 = every
question right: (accuracy - mean of 1/k) / (1 - mean of 1/k) x 100, k each question's number of options."""

from __future__ import annotations

import json
from typing import Any

import export_results as er
from sitebuild import leaderboard
from sitebuild.site import Site

PATH = "bench-scores.json"
TEXT_OPTIONS = 5  # every Text question has options A to E


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
    rule), each split by route, our hardware or an API, so each row is one checkpoint or one hosted service."""
    board = leaderboard.Board(site)
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for run in site.runs:
        groups.setdefault((*board.key(run), run["billing"] == "local"), []).append(run)
    return [leaderboard.choose(setups, lambda item: item) for setups in groups.values()]


def text_bench(site: Site) -> dict[str, Any]:
    total = site.results["questions"]
    models = []
    for run, others in text_rows(site):
        correct, questions = site.accuracy(run)
        repo, commit = checkpoint(run)
        params_total, params_active = sizes(run)
        models.append({
            "repo": repo, "commit": commit, "name": leaderboard.name_of(site, run),
            "maker": site.families[run["run"]]["maker"], "kind": "decision" if site.decision(run) else "chat",
            "params_total": params_total, "params_active": params_active, "quantization": quantization(run),
            "score_0_100": score(correct / questions, 1 / TEXT_OPTIONS),
            "raw": {"metric": "accuracy", "value": correct / questions, "questions": questions, "options": TEXT_OPTIONS},
            "calibration_error": (run.get("confidence") or {}).get("ece"), "improvement_points": None,
            "runs": [f"text:{item['run']}" for item in (run, *others)], "notes": run["access"]})
    return {"bench": "reading-text", "title": "Reading (Text)", "url": site.config["site_url"],
            "updated": site.results["updated"],
            "score": {"zero": f"chance: 1 of {TEXT_OPTIONS} options right on every question (accuracy 20%)",
                      "hundred": f"every one of the {total:,} Turkish reading and grammar questions right (accuracy 100%)"},
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
            "repo": repo, "commit": commit, "name": leaderboard.name_of(site, run), "maker": site.families[run["run"]]["maker"],
            "kind": "decision" if site.decision(run) else "chat", "params_total": params_total,
            "params_active": params_active, "quantization": quantization(run),
            "score_0_100": score(got["accuracy"], chance),
            "raw": {"metric": "accuracy", "value": got["accuracy"], "questions": got["questions"],
                    "options": options.pop() if len(options) == 1 else round(1 / chance, 3)},
            "calibration_error": got["ece"], "improvement_points": None,
            "runs": [f"vision:{item}" for item in got["runs"]], "notes": f"{run['access']}; the page image only (condition B)"})
    questions = data["subset"]["questions"]
    return {"bench": "reading-vision", "title": "Reading (Vision)", "url": site.config["site_url"] + "vision/",
            "updated": data["generated_at"],
            "score": {"zero": "chance: 1 of each question's options right on every question (accuracy 20% with 5 options)",
                      "hundred": f"every one of the {questions:,} questions that depend on the printed page right, read "
                                 "from the page image alone (accuracy 100%)"},
            "models": sorted(models, key=lambda model: -model["score_0_100"])}


def benches(site: Site) -> list[dict[str, Any]]:
    """Both benches, Text first."""
    return [text_bench(site), vision_bench(site)]


def build(site: Site) -> dict[str, str]:
    return {PATH: json.dumps({"benches": benches(site)}, ensure_ascii=False, indent=1) + "\n"}
