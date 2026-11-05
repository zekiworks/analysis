#!/usr/bin/env python3
"""PWS-Decisions (Parallel Web Systems' gated benchmark) for the decision models of the site (Ümit #1273).

    python3 pws/bench.py probe SETUP...                  one request per setup; what the API says it served
    python3 pws/bench.py run SETUP... [--runs 3]         the public questions, one per request, each run to its own file
    python3 pws/bench.py summary [--output pws-decisions.json]

Each question goes out as PWS-Decisions' own request (pws_decisions.build_request: the state, and the choice question
`answer` with its instructions and its choices as criteria), with the site's `model` field and, for Perplexity with
web, `"mode": "web_grounding"`, to the setup's System One service in the site's runner (runner/benchmark_ollama.py:
SYSTEM_ONE, post_json with its retries). OpenAI's Decisions API takes the same parts under its own names: the state as
`input` (a JSON state as an `input_json` part) and the choices as a list of values and descriptions. Each run is a
JSONL file in PWS-Decisions' prediction format (id, prediction, status), scored with its own scorer (`python -m
pws_decisions score`). Per request we record the time from our machine, the retries and the response.

The questions and answers are Parallel's (evaluation only, no redistribution): they are read from --data and the raw
runs stay in --runs-dir, both outside git. The summary writes totals only: no question, answer, state or per-question
row. Keys come from the environment (the runner's variables), never printed or written."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / "vision-track/pws-grounding"
DATA = HOME / "data"
HARNESS = HOME / "repo"
RUNS = HOME / "runs/bench"
OUTPUT = ROOT / "pws-decisions.json"
TIMEOUT = 60.0
PERCENTILE = 0.95  # nearest rank, as the web grounding page and PWS-Decisions' summaries give it

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "runner"))  # the runner imports benchmark_metrics from its folder
_spec = importlib.util.spec_from_file_location("benchmark_runner", ROOT / "runner/benchmark_ollama.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules["benchmark_runner"] = runner
_spec.loader.exec_module(runner)
sys.path.insert(0, str(HARNESS))
from pws_decisions.__main__ import build_request, load_questions, read_jsonl  # noqa: E402

# The setups we run, keyed like the site (results.json runs: provider, model, perplexity_mode), each without search
# unless its mode says so. Name: the folder of its runs.
SETUPS: dict[str, dict[str, Any]] = {
    "perplexity-v1.2": {"provider": "perplexity", "model": "pplx-decider-v1.2", "mode": None},
    "perplexity-v1.2-web": {"provider": "perplexity", "model": "pplx-decider-v1.2", "mode": "web_grounding"},
    "openai-luna": {"provider": "openai-decisions", "model": "gpt-6-luna", "mode": None},
    "jev-1.14": {"provider": "jev", "model": "jev-1.14.0", "mode": None},
    "jev-1.13": {"provider": "jev", "model": "jev-1.13.0", "mode": None},
    "d1-ultra": {"provider": "liquid", "model": "d1-ultra", "mode": None},
    "d1.1": {"provider": "liquid", "model": "d1.1", "mode": None},
    # The site's d1 ran as d1:free on Liquid's free tier; Liquid's API no longer serves that name (HTTP 404 on 5 November
    # 2026), so it is asked as `d1`, as the English track asks it.
    "d1-free": {"provider": "liquid", "model": "d1:free", "request_model": "d1", "mode": None},
    "celeris": {"provider": "celeris", "model": "celeris-1-decision", "mode": None},
    "subq-1.1": {"provider": "subq", "model": "subq-snap-1.1", "mode": None},
    "subq-preview": {"provider": "subq", "model": "subq-snap-preview", "mode": None},
    "meragpt": {"provider": "meragpt", "model": "decider-1", "mode": None},
    "drex-max-1.1": {"provider": "nace", "model": "drex-max-v1.1", "mode": None},
    "drex-2.0": {"provider": "nace", "model": "drex-v2.0", "mode": None},
    "ms-decision-1": {"provider": "openrouter", "model": "microsoft/microsoft-decision-1", "mode": None},
    "mercury-decide": {"provider": "openrouter", "model": "inception/mercury-decide", "mode": None},
    # Probed only: setups whose API may no longer serve the site's model.
    "perplexity-v1": {"provider": "perplexity", "model": "pplx-decider-v1-27b", "mode": None},
    "perplexity-v1.1": {"provider": "perplexity", "model": "pplx-decider-v1.1-27b", "mode": None},
    "glide": {"provider": "fastino", "model": "fastino/GLiDE", "mode": None},
}
# Setups of the site not run, with the reason, keyed like SETUPS (the page names them from results.json).
NOT_RUN: list[dict[str, Any]] = [
    {"provider": "perplexity", "model": "pplx-decider-v1-27b",
     "reason": "Perplexity's API now answers requests for v1 with v1.2. On five of these questions, each of its answers "
               "came within 0.007 of one of three v1.2 answers, while v1.2's own three answers differed by up to 0.085."},
    {"provider": "perplexity", "model": "pplx-decider-v1.1-27b",
     "reason": "Perplexity's API now answers requests for v1.1 with v1.2. On five of these questions, each of its answers "
               "matched one of three v1.2 answers exactly, while v1.2's own three answers differed by up to 0.085."},
    {"provider": "fastino", "model": "fastino/GLiDE",
     "reason": "Since 10 October Fastino's API answers with its glide_v2 engine, as it did again on 5 November, not the "
               "glide engine of the site's run."},
]
# Base Labs' models through Baseten's Model API (decision-models/baseten-elephant-9b-latest and
# decision-models/baseten-mammoth-27b-latest, named elephant-1 and mammoth-1): asked the site's first 20 Turkish
# questions in the runner's request on 5 November 2026 (baseten_check.py, outside git), their option probabilities
# differed from our runs 373 and 374 by up to these amounts, so they are not shown to be the same weights and run with
# the GPU setups.
BASETEN_CHECK = {"questions": 20, "date": "2026-11-05",
                 "baselabs/elephant-1": {"largest_gap": 0.283, "same_choice": 20},
                 "baselabs/mammoth-1": {"largest_gap": 0.082, "same_choice": 19}}
# Setups of the site that wait: Parallel's own API, and the decision models on our GPUs (found from results.json).
PENDING_PARALLEL = "Parallel's own Decisions API: no key on this machine yet (asked Ümit, #1283)."
PENDING_GPU = "Runs on our GPUs: waits for a GPU window."
# What OpenAI's Decisions API documents about the web: its guide and its request reference, read on this date.
OPENAI_WEB = {
    "guide": "https://developers.openai.com/api/docs/guides/decisions",
    "reference": "https://developers.openai.com/api/reference/resources/decisions/methods/create",
    "read": "2026-11-05",
    "parameters": ["model", "input", "questions", "prompt_cache_key", "prompt_cache_options", "safety_identifier"],
}
# Figures published by others, for context (the web grounding page cites the same post).
REPORTED = {
    "perplexity": {
        "source": "https://www.perplexity.ai/hub/blog/web-grounding-for-the-decisions-api",
        "title": "Web grounding for the Decisions API",
        "published": "2026-11-04",
        "on_percent": 86,
        "off_percent": 51,
        "on_median_ms": 370,
        "on_p95_ms": 685,
    },
    # Parallel's leaderboard (the benchmark's README and docs/results.md): public 100, mean of three runs.
    "parallel": {
        "source": "https://github.com/parallel-web/pws-decisions-benchmark",
        "evaluated": "2026-10-29",
        "rows": [
            {"name": "Parallel Decisions API (fast)", "public_percent": 78.33, "p50_s": 0.56, "p95_s": 0.71,
             "usd_per_1000": 1.00},
            {"name": "Perplexity Decisions (pplx-decider-v1.2, through OpenRouter)", "public_percent": 51.00},
            {"name": "OpenAI Decisions API (gpt-6-luna)", "public_percent": 42.00},
            {"name": "Baseten Mammoth (baseten-mammoth-27b-latest)", "public_percent": 37.00},
            {"name": "TypeSafe Jev 1.14 (jev-1.14.0)", "public_percent": 33.33},
        ],
        "random_percent": 44.67,
    },
}


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def payload(setup: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    """The setup's request for one question: PWS-Decisions' request with the site's model field (and mode), or for
    OpenAI's Decisions API the same parts in its format, as the runner's ask_jev sends them."""
    service = runner.SYSTEM_ONE[setup["provider"]]
    body: dict[str, Any] = {"model": setup.get("request_model", setup["model"])} if service.model_field else {}
    if setup["mode"] is not None:
        body["mode"] = setup["mode"]
    request = build_request(question)
    if not service.openai_format:
        body.update(request)
        return body
    state = request["state"]
    answer = request["questions"]["answer"]
    body.update(
        input=state if isinstance(state, str) else [{"role": "user", "content": [{"type": "input_json", "data": state}]}],
        questions=[{"type": "choice", "name": "answer", "instructions": answer["instructions"],
                    "choices": [{"value": value, "description": text} for value, text in answer["criteria"].items()]}],
    )
    return body


def ask(setup: dict[str, Any], question: dict[str, Any], key: str | None) -> dict[str, Any]:
    """One request: PWS-Decisions' prediction record plus the time from our machine, the retries and the response."""
    service = runner.SYSTEM_ONE[setup["provider"]]
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    record: dict[str, Any] = {"id": question["id"], "prediction": None, "status": "error", "utc": utc_now()}
    warnings = io.StringIO()
    started = time.perf_counter()
    try:
        with contextlib.redirect_stderr(warnings):
            response, response_headers = runner.post_json(service.url.rstrip("/") + service.path, payload(setup, question),
                                                          headers, TIMEOUT, None, service.name)
        record["request_seconds"] = time.perf_counter() - started
        record["response"] = response
        if service.request_id_header:
            record["request_id"] = response_headers.get(service.request_id_header)
        answer = runner.system_one_answer(response)
        if answer.get("type") == "refusal":
            record["status"] = "refusal"
        elif answer.get("choice") in {choice["value"] for choice in question["choices"]}:
            record.update(prediction=answer["choice"], status="success")
        else:
            record["status"] = "invalid_response"
    except RuntimeError as exc:
        record["request_seconds"] = time.perf_counter() - started
        record["error"] = str(exc)[:500]
    record["retries"] = warnings.getvalue().count("retry ")
    return record


def run_file(name: str, number: int) -> Path:
    return RUNS / name / f"run-{number}.jsonl"


def questions(args: argparse.Namespace) -> list[dict[str, Any]]:
    return load_questions(args.data / "public-100.jsonl")


def command_probe(args: argparse.Namespace) -> None:
    """One request per setup (a text state and, when --json-state, a JSON state): status, served model, usage keys,
    whether it returned probabilities. No question text is printed."""
    rows = questions(args)
    picks = [rows[0]] + ([next(row for row in rows if not isinstance(row["state"], str))] if args.json_state else [])
    for name in args.setups:
        setup = SETUPS[name]
        key = runner.jev_api_key(setup["provider"])
        for question in picks:
            record = ask(setup, question, key)
            response = record.get("response") or {}
            answer = runner.system_one_answer(response) if response else {}
            print(json.dumps({
                "setup": name, "state": type(question["state"]).__name__, "status": record["status"],
                "seconds": round(record["request_seconds"], 3), "retries": record["retries"],
                "served_model": response.get("model") if isinstance(response, dict) else None,
                "usage": (response.get("usage") if isinstance(response, dict) else None),
                "probabilities": isinstance(answer.get("probabilities"), dict),
                "error": record.get("error", "")[:300],
            }), flush=True)


def command_run(args: argparse.Namespace) -> None:
    rows = questions(args)
    for name in args.setups:
        setup = SETUPS[name]
        key = runner.jev_api_key(setup["provider"])
        for number in range(1, args.runs + 1):
            path = run_file(name, number)
            path.parent.mkdir(parents=True, exist_ok=True)
            done = {row["id"] for row in read_jsonl(path)} if path.exists() else set()
            with path.open("a", encoding="utf-8") as output:
                for question in rows:
                    if question["id"] in done:
                        continue
                    record = ask(setup, question, key)
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                    output.flush()
            print(f"{utc_now()} {name} run {number}: {score(args, path)['correct']} right", flush=True)


def score(args: argparse.Namespace, path: Path) -> dict[str, Any]:
    """PWS-Decisions' own scorer on one prediction file."""
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pws_decisions", "score", "--dataset", str(args.data / "public-100.jsonl"),
         "--answers", str(args.data / "public-100-answers.jsonl"), "--predictions", str(path)],
        cwd=HARNESS, capture_output=True, text=True, check=True,
    )
    return json.loads(done.stdout)


def nearest_rank(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def run_totals(args: argparse.Namespace, setup: dict[str, Any], path: Path, sure: float) -> dict[str, Any]:
    """One run's totals: their scorer's count, request times of the requests that returned a response, tokens and cost
    at the runner's list price, and with probabilities the chosen answer's mean probability and the sure answers."""
    rows = read_jsonl(path)
    scored = score(args, path)
    gold = {row["id"]: row["answer"] for row in read_jsonl(args.data / "public-100-answers.jsonl")}
    answered = [row for row in rows if "response" in row]
    tokens: dict[str, int] = {}
    chosen: list[tuple[float, bool]] = []
    for row in answered:
        stored = json.dumps({"request_id": row.get("request_id"), "response": row["response"]})
        counted, probability = runner.answer_usage(setup["provider"], 0, stored)
        for kind, value in counted.items():
            tokens[kind] = tokens.get(kind, 0) + int(value or 0)
        if row["status"] == "success" and probability is not None:
            chosen.append((probability, row["prediction"] == gold[row["id"]]))
    price = runner.run_price(setup["provider"], setup["model"], setup["mode"])
    cost = price.cost(tokens, len(rows)) if price is not None else None
    seconds = [row["request_seconds"] for row in answered]
    times = [row["utc"] for row in rows]
    totals: dict[str, Any] = {
        "started": min(times), "ended": max(times), "questions": scored["n"], "correct": scored["correct"],
        "accuracy": scored["correct"] / scored["n"], "missing": scored["missing"], "not_success": scored["non_success"],
        "errors": sum(row["status"] == "error" for row in rows), "retries": sum(row.get("retries", 0) for row in rows),
        "median_request_seconds": statistics.median(seconds), "p95_request_seconds": nearest_rank(seconds, PERCENTILE),
        "input_tokens": tokens.get("input_tokens", 0), "output_tokens": tokens.get("output_tokens", 0),
        "cost_usd": cost, "cost_per_million_questions": None if cost is None else cost / scored["n"] * 1_000_000,
        "served_models": sorted({str(row["response"].get("model")) for row in answered
                                 if isinstance(row["response"], dict) and row["response"].get("model")}),
    }
    if chosen:
        totals["confidence"] = {
            "answers": len(chosen), "mean_chosen_probability": statistics.mean(p for p, _ in chosen),
            "sure": sum(p >= sure for p, _ in chosen), "sure_wrong": sum(p >= sure and not right for p, right in chosen),
        }
    return totals


def spread(values: list[float | None]) -> dict[str, float] | None:
    if any(value is None for value in values) or not values:
        return None
    return {"mean": statistics.mean(values), "min": min(values), "max": max(values)}


def command_summary(args: argparse.Namespace) -> None:
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    sure = results["sure_threshold"]
    manifest = json.loads((args.data / "manifest.json").read_text(encoding="utf-8"))
    dataset = args.data / "public-100.jsonl"
    if hashlib.sha256(dataset.read_bytes()).hexdigest() != manifest["questions_sha256"]:
        sys.exit("public-100.jsonl does not match the manifest's checksum")
    rows = load_questions(dataset)
    setups, total_cost, dates = [], 0.0, set()
    for name, setup in SETUPS.items():
        paths = [run_file(name, number) for number in range(1, args.runs + 1)]
        if not all(path.exists() for path in paths):
            continue
        runs = [run_totals(args, setup, path, sure) for path in paths]
        if any(run["questions"] != len(rows) or run["missing"] for run in runs):
            sys.exit(f"{name}: a run is incomplete")
        price = runner.run_price(setup["provider"], setup["model"], setup["mode"])
        total_cost += sum(run["cost_usd"] or 0.0 for run in runs)
        dates.update(run[edge][:10] for run in runs for edge in ("started", "ended"))
        item = {
            "provider": setup["provider"], "model": setup["model"], "perplexity_mode": setup["mode"],
            "request_model": setup.get("request_model", setup["model"]),
            "price": None if price is None else {"basis": price.basis, "source": price.source, "date": price.date,
                                                 "input_per_million": price.input, "per_request": price.per_request},
            "runs": runs,
            "accuracy": spread([run["accuracy"] for run in runs]),
            "median_request_seconds": spread([run["median_request_seconds"] for run in runs]),
            "p95_request_seconds": spread([run["p95_request_seconds"] for run in runs]),
            "cost_per_million_questions": spread([run["cost_per_million_questions"] for run in runs]),
        }
        if all("confidence" in run for run in runs):
            item["mean_chosen_probability"] = spread([run["confidence"]["mean_chosen_probability"] for run in runs])
            item["sure_wrong"] = spread([run["confidence"]["sure_wrong"] for run in runs])
            item["sure"] = spread([run["confidence"]["sure"] for run in runs])
        setups.append(item)
    document = {
        "name": "PWS-Decisions", "version": manifest["version"], "questions_sha256": manifest["questions_sha256"],
        "questions": len(rows), "language": "English",
        "random_accuracy": statistics.mean(1 / len(row["choices"]) for row in rows),
        "harness": "https://github.com/parallel-web/pws-decisions-benchmark",
        "runs_per_setup": args.runs, "one_question_per_request": True, "timeout_seconds": TIMEOUT,
        "retries": {"statuses": "408, 425, 429 and 5xx, and transport failures", "max": runner.JEV_MAX_RETRIES},
        "percentile": PERCENTILE, "sure_threshold": sure, "dates": sorted(dates), "run_cost_usd": total_cost,
        "setups": setups, "not_run": NOT_RUN, "baseten_check": BASETEN_CHECK,
        "pending": {"parallel": PENDING_PARALLEL, "gpu": PENDING_GPU},
        "openai_web": OPENAI_WEB, "reported": REPORTED,
    }
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {len(setups)} setups, run cost ${total_cost:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", type=Path, default=DATA, help="the folder of public-100.jsonl, its answers and manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe")
    probe.add_argument("setups", nargs="+", choices=SETUPS)
    probe.add_argument("--json-state", action="store_true", help="also send a question whose state is JSON")
    run = commands.add_parser("run")
    run.add_argument("setups", nargs="+", choices=SETUPS)
    summary = commands.add_parser("summary")
    summary.add_argument("--output", type=Path, default=OUTPUT)
    for command in (run, summary):
        command.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    {"probe": command_probe, "run": command_run, "summary": command_summary}[args.command](args)


if __name__ == "__main__":
    main()
