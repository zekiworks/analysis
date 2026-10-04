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

# How each provider was reached and what its cost figure means. Scoring providers rate the supplied
# options instead of generating an answer, so they have no reasoning setting. "{price}" is replaced by
# the model's list price from MODELS; a model's "access" in MODELS replaces its provider's.
PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {"access": "Ollama, self-hosted", "scoring": False, "cost_basis": None},
    "vllm": {"access": "vLLM, self-hosted", "scoring": False, "cost_basis": None},
    "jev": {
        "access": "TypeSafe System One API",
        "scoring": True,
        "cost_basis": "TypeSafe's price: $0.042 per 1M input tokens, output free",
    },
    "open-jev": {
        "access": "Open-Jev server, self-hosted",
        "scoring": True,
        "cost_basis": "Jev's price applied to its tokens; self-hosted, so not billed",
    },
    "perplexity": {
        "access": "Perplexity Decisions API",
        "scoring": True,
        "cost_basis": "Perplexity's price: $0.04 per 1M input tokens, output free",
    },
    "liquid": {
        "access": "Liquid AI decisions API",
        "scoring": True,
        "cost_basis": "$0: the free d1 model (Liquid publishes no price for d1)",
    },
    "laya": {"access": "Laya server, self-hosted", "scoring": True, "cost_basis": None},
    "vllm-yes-no": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": True,
        "cost_basis": "$0.40 / $2.40 per 1M input / output tokens; self-hosted, so not billed",
    },
    "vllm-verbal": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": False,
        "cost_basis": "$0.40 / $2.40 per 1M input / output tokens; self-hosted, so not billed",
    },
    "claude": {
        "access": "Claude Code CLI, Claude subscription",
        "scoring": False,
        "cost_basis": "Anthropic API list price, {price}; the run used a subscription",
    },
    "openai": {
        "access": "Codex CLI, ChatGPT subscription",
        "scoring": False,
        "cost_basis": "OpenAI API list price, {price}; the run used a subscription",
    },
}
# Where a run's confidence comes from (the report's score_source).
CONFIDENCE_SOURCES = {"probability": "Probability of the chosen option", "stated": "Stated by the model"}
# Runs of one model through different providers.
VARIANTS = {"vllm-yes-no": "yes/no scoring", "vllm-verbal": "stated confidence"}
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
    "gemma-4-31B-it": {"name": "Gemma 4 31B", "access": "vLLM, self-hosted, FP8"},
    "deepseek-v4.1-flash": {
        "name": "DeepSeek-V4.1-Flash",
        "access": "SGLang, self-hosted, published mixed precision",
    },
    "gemma4:31b": {"name": "Gemma 4 31B"},
    "deepseek-v4-flash:latest": {"name": "DeepSeek V4 Flash"},
    "muse-glimmer:30b": {"name": "Muse Glimmer 30B"},
    "jev-1.13.0": {"name": "Jev 1.13.0"},
    "open-jev-27b-v1.1": {
        "name": "Open-Jev 27B v1.1",
        "note": "Fine-tune of Qwen3.8-27B (LoRA and a scoring head)",
    },
    "pplx-decider-v1-27b": {"name": "Perplexity Decider 27B"},
    "d1:free": {"name": "Liquid d1"},
    "laya": {"name": "Laya", "note": "Encoder with a decision head"},
    "laya-multilingual": {"name": "Laya multilingual", "note": "Encoder with a decision head"},
    "qwen38-27b-bf16": {"name": "Qwen3.8-27B", "note": "Open-Jev's base model"},
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="benchmark-results.md written by benchmark_ollama.py")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"default: {DEFAULT_OUTPUT}")
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
        "aurc": overall["aurc"],
        "ece": overall["ece"],
        "brier": overall["brier"],
        "coverage_accuracy": overall["coverage_accuracy"],
        "median_right": extremes["median_right"],
        "median_wrong": extremes["median_wrong"],
        "sure": extremes["sure"],
        "doubtful": extremes["doubtful"],
    }


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
        cost_basis = None
        if record.get("cost_usd") is not None:
            if provider["cost_basis"] is None or ("{price}" in provider["cost_basis"] and "price" not in model):
                raise ValueError(f"{label}: has a cost but no cost basis or list price")
            cost_basis = provider["cost_basis"].format(price=model.get("price"))
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
                "groups": {
                    name: {"questions": record["groups"][name]["questions"], "correct": record["groups"][name]["correct"]}
                    for name in GROUPS
                    if name in record["groups"]
                },
                "questions_per_minute": record.get("questions_per_minute"),
                "request_seconds": record.get("timed_seconds"),
                "cost_usd": record.get("cost_usd"),
                "cost_basis": cost_basis,
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
            **{key: item[key] for key in ("questions", "first_only", "second_only", "difference", "low", "high", "p")},
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
                "cost_usd": cost,
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
    reference = selected[0]
    suspect = None
    if "without_suspect" in reference["groups"]:
        suspect = reference["groups"]["all"]["questions"] - reference["groups"]["without_suspect"]["questions"]
    scored = next((record for record in selected if record.get("score_source")), None)
    return {
        "schema_version": SCHEMA_VERSION,
        "updated": max(run["updated"] for run in runs),
        "dataset": {"name": Path(reference["dataset"]).name, "sha256": reference["dataset_sha256"]},
        "questions": full_set,
        "suspect": suspect,
        "excluded": {reason: count for reason, count in reference["skipped"].items() if count},
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
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['runs'])} runs over {data['questions']:,} questions to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
