#!/usr/bin/env python3
"""Write docs/results.json, the data behind the GitHub page, from the benchmark report.

The report (benchmark-results.md) embeds one JSON record per run and one with the comparisons between
runs. Only runs over the full question set are exported (the newest question bank's), without runs
whose correct option was replaced, and only aggregate numbers: no question text, prompts, answers or
local paths.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RESULT_PATTERN = re.compile(r"<!-- benchmark-result: (\{.*?\}) -->")
ANALYSIS_PATTERN = re.compile(r"<!-- benchmark-analysis: (\{.*?\}) -->")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "docs" / "results.json"
SCHEMA_VERSION = 2

# How each provider was reached, how it was paid for and what its cost figure means. Scoring providers
# rate the supplied options instead of generating an answer, so they have no reasoning setting.
# billing: "api" (billed per token), "subscription" (a flat plan, priced at list rates for comparison)
# or "local" (our GPUs; any price is an assumption). "{price}" is replaced by the model's list price
# from MODELS; a model's "access" in MODELS replaces its provider's.
PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {"access": "Ollama, self-hosted", "scoring": False, "billing": "local", "cost_basis": None},
    "vllm": {"access": "vLLM, self-hosted", "scoring": False, "billing": "local", "cost_basis": None},
    "jev": {
        "access": "TypeSafe System One API",
        "scoring": True,
        "billing": "api",
        "cost_basis": "TypeSafe's price: $0.042 per 1M input tokens, output free",
    },
    "open-jev": {
        "access": "Open-Jev server, self-hosted",
        "scoring": True,
        "billing": "local",
        "cost_basis": "Jev's API price applied to its tokens, for comparison",
    },
    "perplexity": {
        "access": "Perplexity Decisions API",
        "scoring": True,
        "billing": "api",
        "cost_basis": "Perplexity's price: $0.04 per 1M input tokens, output free",
    },
    "liquid": {
        "access": "Liquid AI decisions API",
        "scoring": True,
        "billing": "api",
        "cost_basis": "the free d1 model; Liquid publishes no price for d1",
    },
    "laya": {"access": "Laya server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "vllm-yes-no": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": True,
        "billing": "local",
        "cost_basis": "an assumed $0.40 / $2.40 per 1M input / output tokens",
    },
    "vllm-verbal": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": False,
        "billing": "local",
        "cost_basis": "an assumed $0.40 / $2.40 per 1M input / output tokens",
    },
    "claude": {
        "access": "Claude Code CLI, Claude subscription",
        "scoring": False,
        "billing": "subscription",
        "cost_basis": "Anthropic API list price, {price}",
    },
    "openai": {
        "access": "Codex CLI, ChatGPT subscription",
        "scoring": False,
        "billing": "subscription",
        "cost_basis": "OpenAI API list price, {price}",
    },
}
# Where a run's confidence comes from (the report's score_source).
CONFIDENCE_SOURCES = {"probability": "Probability of the chosen option", "stated": "Stated by the model"}
# Runs of one model through different providers.
VARIANTS = {"vllm-yes-no": "yes/no scoring", "vllm-verbal": "stated confidence"}
GPU = "RTX PRO 6000 Blackwell (96 GB)"
# Display names, list prices, and for models on our GPUs the hardware and precision.
MODELS: dict[str, dict[str, str]] = {
    "gpt-6-astra": {
        "name": "GPT-6 Astra",
        "price": "$10 per 1M input tokens ($1 cached), $50 per 1M output tokens",
    },
    "claude-opus-5-5": {
        "name": "Claude Opus 5.5",
        "price": "$4 / $20 per 1M input / output tokens",
    },
    "claude-sonnet-5-5": {
        "name": "Claude Sonnet 5.5",
        "price": "$2 / $10 per 1M input / output tokens",
    },
    "gemma-4-31B-it": {
        "name": "Gemma 4 31B",
        "access": "vLLM, self-hosted, FP8",
        "hardware": f"1 × {GPU}; FP8 weights and KV cache",
    },
    "deepseek-v4.1-flash": {
        "name": "DeepSeek-V4.1-Flash",
        "access": "SGLang, self-hosted, published mixed precision",
        "hardware": f"4 × {GPU}; FP4 experts, FP8 and BF16 layers",
    },
    "gemma4:31b": {"name": "Gemma 4 31B"},
    "deepseek-v4-flash:latest": {"name": "DeepSeek V4 Flash"},
    "muse-glimmer:30b": {"name": "Muse Glimmer 30B"},
    "jev-1.13.0": {"name": "Jev 1.13.0"},
    "open-jev-27b-v1.1": {
        "name": "Open-Jev 27B v1.1",
        "note": "Fine-tune of Qwen3.8-27B (LoRA and a scoring head)",
        "hardware": f"1 × {GPU}; BF16",
    },
    "pplx-decider-v1-27b": {"name": "Perplexity Decider 27B"},
    "d1:free": {"name": "Liquid d1"},
    "laya": {"name": "Laya", "note": "Encoder with a decision head", "hardware": f"1 × {GPU}"},
    "laya-multilingual": {"name": "Laya multilingual", "note": "Encoder with a decision head", "hardware": f"1 × {GPU}"},
    "qwen38-27b-bf16": {"name": "Qwen3.8-27B", "note": "Open-Jev's base model", "hardware": f"1 × {GPU}; BF16"},
}
UNITS_EN = {
    1: "Meaning of words and phrases",
    2: "Sentence meaning",
    3: "Modes of expression and ways of developing ideas",
    4: "Topic and main idea of a paragraph",
    5: "Paragraph structure",
    6: "Supporting ideas in a paragraph",
    7: "Parts of speech",
    8: "Noun phrases",
    9: "Verbs",
    10: "Verbals",
    11: "Suffixes",
    12: "Word structure",
    13: "Sentence elements",
    14: "Verb voice",
    15: "Sentence types",
    16: "Mixed grammar",
    17: "Phonology",
    18: "Spelling rules",
    19: "Punctuation",
    20: "Expression errors",
}
# Question groups the page shows, from the report's groups.
GROUPS = ("reading", "grammar", "without_suspect")
# The 2026 TYT Türkçe paper's mix of reading and grammar questions, for the reweighted score.
TYT_MIX = {"reading": 33, "grammar": 7}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="benchmark-results.md written by benchmark_ollama.py")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"default: {DEFAULT_OUTPUT}")
    parser.add_argument(
        "--answers",
        type=Path,
        help="the per-question file from benchmark_ollama.py --export-answers; writes answers.json next to --output "
        "with the exported runs only",
    )
    return parser.parse_args()


def unit_number(name: str) -> int:
    match = re.match(r"(\d+)\.\s", name)
    if match is None or int(match.group(1)) not in UNITS_EN:
        raise ValueError(f"unknown unit {name!r}; add its English name to UNITS_EN")
    return int(match.group(1))


def confidence(record: dict[str, Any]) -> dict[str, Any] | None:
    """The run's confidence metrics, or None for runs that give no confidence."""
    source = record.get("score_source")
    if source is None:
        return None
    overall = record["groups"]["all"]
    extremes = record["confidence_extremes"]
    return {
        "source": source,
        "label": CONFIDENCE_SOURCES[source],
        "bins": [{"questions": interval["questions"], "correct": interval["correct"]} for interval in record["confidence_bins"]],
        "auroc": overall["auroc"],
        "auroc_interval": overall.get("auroc_interval"),
        "aurc": overall["aurc"],
        "ece": overall["ece"],
        "brier": overall["brier"],
        "coverage_accuracy": overall["coverage_accuracy"],
        "coverage_intervals": overall.get("coverage_intervals"),
        "median_right": extremes["median_right"],
        "median_wrong": extremes["median_wrong"],
        "sure": extremes["sure"],
        "doubtful": extremes["doubtful"],
    }


def tyt_mix(groups: dict[str, Any]) -> float | None:
    """Accuracy with reading and grammar weighted like the 2026 TYT paper."""
    if not all(name in groups for name in TYT_MIX):
        return None
    weighted = sum(weight * groups[name]["correct"] / groups[name]["questions"] for name, weight in TYT_MIX.items())
    return weighted / sum(TYT_MIX.values())


def export(records: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    if not records:
        raise ValueError("the report contains no benchmark-result records")
    by_key = {record["run_key"]: record for record in records}
    full_set = max(record["eligible_total"] for record in records)
    selected = [
        record
        for record in records
        if record["evaluated"] == record["eligible_total"] == full_set and record.get("replace_key_text") is None
    ]
    datasets = {record["dataset_sha256"] for record in selected}
    if len(datasets) != 1:
        raise ValueError(f"the runs over {full_set} questions use {len(datasets)} question banks")
    unit_names = sorted(selected[0]["categories"], key=unit_number)
    totals = {name: selected[0]["categories"][name]["total"] for name in unit_names}
    versions = {item["newer"]: item for item in analysis.get("versions", [])}
    runs = []
    for record in selected:
        provider_name = record.get("provider", "ollama")
        label = f"run {record['run_id']} ({record['model']}, {provider_name})"
        provider = PROVIDERS.get(provider_name)
        if provider is None:
            raise ValueError(f"{label}: unknown provider; add it to PROVIDERS")
        categories = record["categories"]
        if {name: counts["total"] for name, counts in categories.items()} != totals:
            raise ValueError(f"{label}: its units differ from the other runs'")
        if sum(counts["correct"] for counts in categories.values()) != record["correct"]:
            raise ValueError(f"{label}: unit results do not add up to its score")
        model = MODELS.get(record["model"], {})
        cost = record.get("cost_usd")
        cost_basis = None
        if cost is not None:
            if provider["cost_basis"] is None or ("{price}" in provider["cost_basis"] and "price" not in model):
                raise ValueError(f"{label}: has a cost but no cost basis or list price")
            cost_basis = provider["cost_basis"].format(price=model.get("price"))
        if provider["billing"] == "local" and "hardware" not in model:
            raise ValueError(f"{label}: runs on our GPUs; add its hardware to MODELS")
        groups = {
            name: {"questions": record["groups"][name]["questions"], "correct": record["groups"][name]["correct"]}
            for name in GROUPS
            if name in record["groups"]
        }
        variants = [VARIANTS.get(provider_name), "options shuffled" if record.get("shuffle_options") is not None else None]
        version = versions.get(record["run_key"])
        previous = None
        if version is not None and version["older"] in by_key:
            previous = {
                "run": by_key[version["older"]]["run_id"],
                **{part: version[part] for part in ("changed", "unchanged", "added")},
            }
        runs.append(
            {
                "run": record["run_id"],
                "model": record["model"],
                "name": model.get("name", record["model"]),
                "variant": ", ".join(variant for variant in variants if variant) or None,
                "note": model.get("note"),
                "provider": provider_name,
                "access": model.get("access", provider["access"]),
                "reasoning": None if provider["scoring"] else record["thinking"],
                "questions_per_request": record["batch_size"],
                "concurrency": record.get("concurrency", 1),
                "correct": record["correct"],
                "invalid": record["invalid"],
                "answered_questions": record.get("as_run", {}).get("evaluated", record["evaluated"]),
                "groups": groups,
                "tyt_mix": tyt_mix(groups),
                "questions_per_minute": record.get("questions_per_minute"),
                "request_seconds": record.get("timed_seconds"),
                "median_request_seconds": record.get("median_request_seconds"),
                "billing": provider["billing"],
                "billed_usd": cost if provider["billing"] == "api" else None,
                "api_equivalent_usd": cost,
                "cost_basis": cost_basis,
                "hardware": model.get("hardware") if provider["billing"] == "local" else None,
                "input_tokens": record.get("input_tokens"),
                "output_tokens": record.get("output_tokens"),
                "confidence": confidence(record),
                "previous": previous,
                "units": [categories[name]["correct"] for name in unit_names],
                "updated": record["updated"],
            }
        )
    runs.sort(key=lambda run: (-run["correct"], run["name"].casefold(), run["run"]))
    exported = {record["run_key"]: record for record in selected}
    paired = [
        {
            "first": exported[item["first"]]["run_id"],
            "second": exported[item["second"]]["run_id"],
            **{key: item[key] for key in ("questions", "first_only", "second_only", "difference", "low", "high", "p", "p_holm")},
        }
        for item in analysis.get("paired", [])
        if item["first"] in exported and item["second"] in exported
    ]
    cascades = []
    for item in analysis.get("cascades", []):
        if item["decision"] not in exported or item["frontier"] not in exported:
            continue
        decision, frontier = exported[item["decision"]], exported[item["frontier"]]
        cost = None
        if decision.get("cost_usd") is not None and frontier.get("cost_usd") is not None:
            cost = decision["cost_usd"] + frontier["cost_usd"] * (1 - item["in_sample"]["answered"])
        cascades.append(
            {
                "decision": decision["run_id"],
                "frontier": frontier["run_id"],
                "frontier_accuracy": item["frontier_accuracy"],
                "in_sample": item["in_sample"],
                "held_out": item["held_out"],
                "api_equivalent_usd": cost,
            }
        )
    doubts = [
        {
            "decision": exported[item["decision"]]["run_id"],
            "frontier": [exported[key]["run_id"] for key in item["frontier"]],
            **{key: item[key] for key in ("questions", "rho", "p", "auroc", "top_tenth")},
        }
        for item in analysis.get("doubts", [])
        if item["decision"] in exported and all(key in exported for key in item["frontier"])
    ]
    sources = [
        {
            "answers": exported[item["answers"]]["run_id"],
            "questions": item["questions"],
            "correct": item["correct"],
            "sources": [
                {
                    "run": exported[entry["run"]]["run_id"],
                    "stated": entry["run"] == item["answers"],
                    **{key: entry[key] for key in ("questions", "auroc", "auroc_interval")},
                }
                for entry in item["sources"]
                if entry["run"] in exported
            ],
        }
        for item in analysis.get("sources", [])
        if item["answers"] in exported
    ]
    reference = selected[0]
    suspect = None
    if "without_suspect" in reference["groups"]:
        suspect = reference["groups"]["all"]["questions"] - reference["groups"]["without_suspect"]["questions"]
    scored = next((record for record in selected if record.get("score_source")), None)
    return {
        "schema_version": SCHEMA_VERSION,
        "updated": max(run["updated"] for run in runs),
        "dataset": {
            "name": Path(reference["dataset"]).name,
            "sha256": reference["dataset_sha256"],
            "graded_sha256": reference.get("graded_sha256"),
        },
        "excluded_since_run": reference.get("excluded_since_run", 0),
        "questions": full_set,
        "suspect": suspect,
        "excluded": {reason: count for reason, count in reference["skipped"].items() if count},
        "tyt_mix": TYT_MIX,
        "confidence_bins": (
            [[interval["low"], interval["high"]] for interval in scored["confidence_bins"]] if scored else []
        ),
        "coverages": sorted(float(coverage) for coverage in scored["groups"]["all"]["coverage_accuracy"]) if scored else [],
        "units": [
            {
                "number": unit_number(name),
                "name": re.sub(r"^\d+\.\s*", "", name),
                "english": UNITS_EN[unit_number(name)],
                "questions": totals[name],
            }
            for name in unit_names
        ],
        "runs": runs,
        "paired": paired,
        "cascades": cascades,
        "doubts": doubts,
        "sources": sources,
    }


def export_answers(document: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """The per-question answers of the runs in `data`, from benchmark_ollama.py --export-answers."""
    dataset = next((item for item in document["datasets"] if item["sha256"] == data["dataset"]["sha256"]), None)
    if dataset is None:
        raise ValueError("the answers file has no runs on the exported question bank")
    wanted = {run["run"] for run in data["runs"]}
    runs = [run for run in dataset["runs"] if run["run"] in wanted]
    missing = wanted - {run["run"] for run in runs}
    if missing:
        raise ValueError(f"the answers file lacks runs {sorted(missing)}")
    return {
        "schema_version": document["schema_version"],
        "dataset": {"name": dataset["name"], "sha256": dataset["sha256"]},
        "prompts": document["prompts"],
        "questions": dataset["questions"],
        "runs": runs,
    }


def main() -> int:
    args = parse_args()
    try:
        text = args.report.read_text(encoding="utf-8")
        analysis = ANALYSIS_PATTERN.search(text)
        data = export(
            [json.loads(match.group(1)) for match in RESULT_PATTERN.finditer(text)],
            json.loads(analysis.group(1)) if analysis else {},
        )
        answers = None
        if args.answers is not None:
            answers = export_answers(json.loads(args.answers.read_text(encoding="utf-8")), data)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['runs'])} runs over {data['questions']:,} questions to {args.output}")
    if answers is not None:
        path = args.output.parent / "answers.json"
        path.write_text(json.dumps(answers, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Wrote the answers of {len(answers['runs'])} runs to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
