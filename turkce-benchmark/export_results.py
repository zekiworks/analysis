#!/usr/bin/env python3
"""Write docs/results.json, the data behind the GitHub page, from the benchmark report.

The report (benchmark-results.md) embeds one JSON record per run. Only runs over the full question
set are exported, and only aggregate numbers: no question text, prompts, answers or local paths.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RESULT_PATTERN = re.compile(r"<!-- benchmark-result: (\{.*?\}) -->")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "docs" / "results.json"

# How each provider was reached, where its confidence comes from, and what its cost figure means.
# Scoring providers rate the supplied options instead of generating an answer, so they have no
# reasoning setting. "{price}" is replaced by the model's list price from MODELS.
PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "access": "Ollama, self-hosted",
        "scoring": False,
        "confidence": None,
        "cost_basis": None,
    },
    "jev": {
        "access": "TypeSafe System One API",
        "scoring": True,
        "confidence": "Reported by the API",
        "cost_basis": "TypeSafe's price: $0.042 per 1M input tokens, output free",
    },
    "open-jev": {
        "access": "Open-Jev server, self-hosted",
        "scoring": True,
        "confidence": "Reported by the server",
        "cost_basis": "Jev's price applied to its tokens; self-hosted, so not billed",
    },
    "vllm-yes-no": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": True,
        "confidence": "Computed from Yes/No token probabilities",
        "cost_basis": "$0.40 / $2.40 per 1M input / output tokens; self-hosted, so not billed",
    },
    "vllm-verbal": {
        "access": "vLLM, self-hosted, BF16",
        "scoring": False,
        "confidence": "Stated by the model",
        "cost_basis": "$0.40 / $2.40 per 1M input / output tokens; self-hosted, so not billed",
    },
    "claude": {
        "access": "Claude Code CLI, Claude subscription",
        "scoring": False,
        "confidence": "Stated by the model",
        "cost_basis": "Anthropic API list price, {price}; the run used a subscription",
    },
    "openai": {
        "access": "Codex CLI, ChatGPT subscription",
        "scoring": False,
        "confidence": "Stated by the model",
        "cost_basis": "OpenAI API list price, {price}; the run used a subscription",
    },
}
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
    "gemma4:31b": {"name": "Gemma 4 31B"},
    "deepseek-v4-flash:latest": {"name": "DeepSeek V4 Flash"},
    "muse-glimmer:30b": {"name": "Muse Glimmer 30B"},
    "jev-1.13.0": {"name": "Jev 1.13.0"},
    "open-jev-27b-v1.1": {
        "name": "Open-Jev 27B v1.1",
        "note": "Fine-tune of Qwen3.8-27B (LoRA and a scoring head)",
    },
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


def export(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("the report contains no benchmark-result records")
    full_set = max(record["eligible_total"] for record in records)
    records = [record for record in records if record["evaluated"] == record["eligible_total"] == full_set]
    unit_names = sorted(records[0]["categories"], key=unit_number)
    totals = {name: records[0]["categories"][name]["total"] for name in unit_names}
    runs = []
    for record in records:
        label = f"run {record['run_id']} ({record['model']}, {record.get('provider', 'ollama')})"
        provider = PROVIDERS.get(record.get("provider", "ollama"))
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
            if "{price}" in provider["cost_basis"] and "price" not in model:
                raise ValueError(f"{label}: has a cost but no list price in MODELS")
            cost_basis = provider["cost_basis"].format(price=model.get("price"))
        confidence = None
        if record.get("confidence_bins"):
            confidence = {
                "source": provider["confidence"],
                "bins": [
                    {"questions": interval["questions"], "correct": interval["correct"]}
                    for interval in record["confidence_bins"]
                ],
                "mean": record["mean_confidence"],
                "above_mean": {
                    "questions": record["above_mean_questions"],
                    "correct": record["above_mean_correct"],
                },
            }
        runs.append(
            {
                "run": record["run_id"],
                "model": record["model"],
                "name": model.get("name", record["model"]),
                "variant": VARIANTS.get(record.get("provider", "ollama")),
                "note": model.get("note"),
                "provider": record.get("provider", "ollama"),
                "access": provider["access"],
                "reasoning": None if provider["scoring"] else record["thinking"],
                "questions_per_request": record["batch_size"],
                "correct": record["correct"],
                "invalid": record["invalid"],
                "questions_per_minute": record.get("questions_per_minute"),
                "request_seconds": record.get("timed_seconds"),
                "cost_usd": record.get("cost_usd"),
                "cost_basis": cost_basis,
                "input_tokens": record.get("input_tokens"),
                "output_tokens": record.get("output_tokens"),
                "confidence": confidence,
                "units": [categories[name]["correct"] for name in unit_names],
                "updated": record["updated"],
            }
        )
    runs.sort(key=lambda run: (-run["correct"], run["name"].casefold(), run["run"]))
    confidence_bins = next(
        (
            [[interval["low"], interval["high"]] for interval in record["confidence_bins"]]
            for record in records
            if record.get("confidence_bins")
        ),
        [],
    )
    excluded = {reason: count for reason, count in records[0]["skipped"].items() if count}
    return {
        "updated": max(run["updated"] for run in runs),
        "questions": full_set,
        "excluded": excluded,
        "confidence_bins": confidence_bins,
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
    }


def main() -> int:
    args = parse_args()
    try:
        text = args.report.read_text(encoding="utf-8")
        data = export([json.loads(match.group(1)) for match in RESULT_PATTERN.finditer(text)])
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['runs'])} runs over {data['questions']:,} questions to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
