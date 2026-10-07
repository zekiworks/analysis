#!/usr/bin/env python3
"""Write docs/results.json, the data behind the GitHub page, from the benchmark report.

The report (benchmark-results.md) embeds one JSON record per run and one with the comparisons between
runs. Only runs over a full question set are exported, those on the question bank of the most recently
finished full run, without runs whose correct option was replaced, and only aggregate numbers: no
question text, prompts, answers or local paths.
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
    "fastino": {
        "access": "Fastino System One API",
        "scoring": True,
        "billing": "api",
        "cost_basis": "Fastino's price: $0.15 per 1M input tokens, output free",
    },
    "laya": {"access": "Laya server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "gliner": {"access": "GLiNER2 server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "clef": {"access": "Clef server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "metask": {"access": "Metask-Jev server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "cygnet": {"access": "Cygnet decision server on vLLM, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "winnow": {"access": "Winnow server (llama.cpp), self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "strands": {"access": "Strands Decider server, self-hosted", "scoring": True, "billing": "local", "cost_basis": None},
    "gemini": {
        "access": "Gemini API",
        "scoring": False,
        "billing": "api",
        "cost_basis": "Gemini API list price, {price}",
    },
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
    "vllm-vote": {
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
CONFIDENCE_SOURCES = {
    "probability": "Probability of the chosen option",
    "stated": "Stated by the model",
    "votes": "Share of 10 samples",
}
# Runs of one model through different providers.
VARIANTS = {"vllm-yes-no": "yes/no scoring", "vllm-verbal": "stated confidence", "vllm-vote": "vote share"}
GPU = "RTX PRO 6000 Blackwell (96 GB)"
# Display names, list prices, and for models on our GPUs the hardware and precision.
# parameters: the model's weights, counted from the tensor shapes in each local checkpoint's safetensors
# files (Open-Jev: Qwen3.8-27B plus its LoRA adapter and scoring head; Clef: the backbone plus its joint
# head); Perplexity's Decider from the total_parameters of its published index; DeepSeek-V4.1-Flash from
# its model card, a mixture of experts with 552B backbone parameters, of which 8B are active per token in
# prefill and 16B in decode (active_parameters). Models whose makers publish no size have neither.
MODELS: dict[str, dict[str, Any]] = {
    "gpt-6-astra": {
        "name": "GPT-6 Astra",
        "price": "$10 per 1M input tokens ($1 cached), $50 per 1M output tokens",
    },
    "gpt-6.1-sol": {
        "name": "GPT-6.1 Sol",
        "price": "$2 per 1M input tokens ($0.10 cached), $10 per 1M output tokens",
    },
    "gpt-6-luna": {
        "name": "GPT-6 Luna",
        "price": "$0.10 per 1M input tokens ($0.01 cached), $0.50 per 1M output tokens",
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
        "parameters": 31_273_088_876,
    },
    "deepseek-v4.1-flash": {
        "name": "DeepSeek-V4.1-Flash",
        "access": "SGLang, self-hosted, published mixed precision",
        "hardware": f"4 × {GPU}; FP4 experts, FP8 and BF16 layers",
        "parameters": 552_000_000_000,
        "active_parameters": [8_000_000_000, 16_000_000_000],
    },
    "gemma4:31b": {"name": "Gemma 4 31B"},
    "deepseek-v4-flash:latest": {"name": "DeepSeek V4 Flash"},
    "muse-glimmer:30b": {"name": "Muse Glimmer 30B"},
    "jev-1.13.0": {"name": "Jev 1.13.0"},
    "open-jev-27b-v1.1": {
        "name": "Open-Jev 27B v1.1",
        "note": "Fine-tune of Qwen3.8-27B (LoRA and a scoring head)",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 27_796_899_569,
    },
    "pplx-decider-v1-27b": {"name": "Perplexity Decider 27B", "parameters": 26_085_330_160},
    "fastino/GLiDE": {"name": "Fastino GLiDE", "note": "Hosted decision model; Fastino describes it as reasoning on uncertain decisions"},
    "d1:free": {"name": "Liquid d1"},
    "laya": {"name": "Laya", "note": "Encoder with a decision head", "hardware": f"1 × {GPU}", "parameters": 421_293_830},
    "laya-multilingual": {
        "name": "Laya multilingual",
        "note": "Encoder with a decision head",
        "hardware": f"1 × {GPU}",
        "parameters": 321_908_998,
    },
    "qwen38-27b-bf16": {
        "name": "Qwen3.8-27B",
        "note": "Open-Jev's base model",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 27_781_427_952,
    },
    "gliner2.5-multi-v1": {
        "name": "GLiNER2.5 Multi (base)",
        "note": "Multilingual extraction and classification model",
        "hardware": f"1 × {GPU}; FP16",
        "parameters": 287_355_159,
    },
    "gliner2.5-multi-decide": {
        "name": "GLiNER2.5-multi-Decide",
        "note": "Fastino's decision fine-tune of GLiNER2.5 Multi",
        "hardware": f"1 × {GPU}; FP16",
        "parameters": 287_355_159,
    },
    "clef": {
        "name": "Clef",
        "note": "Cloudflare's decision model, post-trained from Qwen3.8-27B",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 27_484_784_884,
    },
    "clef-flash": {
        "name": "Clef-flash",
        "note": "Cloudflare's 9B decision model, post-trained from Qwen3.5-9B",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 9_531_576_564,
    },
    "metask-jev-4b-policy-mix": {
        "name": "Metask-Jev 4B",
        "note": "Fine-tune of Qwen3.5-4B (merged LoRA)",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 4_539_265_536,
    },
    "cygnet": {
        "name": "Cygnet",
        "note": "Gemma 4 12B IT, unchanged, read out by option letter",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 11_959_730_224,
    },
    "winnow-12b": {
        "name": "Winnow-12B",
        "note": "Fine-tune of Gemma 4 12B IT (Q8_0 GGUF)",
        "hardware": f"1 × {GPU}; Q8_0",
        "parameters": 11_907_350_576,
    },
    "strands-decider-2b": {
        "name": "Strands Decider 2B",
        "note": "Amazon's decision model: a LoRA adapter and a decision head on Qwen3.5-2B-Base",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 2_291_942_208,
    },
    "gemini-3.8-flash": {
        "name": "Gemini 3.8 Flash",
        "price": "$0.75 per 1M input tokens, $3.75 per 1M output tokens, thinking included (introductory price through 2026)",
    },
    "erk-14b": {
        "name": "Erk-14B",
        "note": "Qwen3-14B with continued Turkish training (eCloud)",
        "access": "vLLM, self-hosted, BF16",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 14_768_307_200,
    },
    "qwen3-14b": {
        "name": "Qwen3-14B",
        "note": "Erk-14B's base model",
        "access": "vLLM, self-hosted, BF16",
        "hardware": f"1 × {GPU}; BF16",
        "parameters": 14_768_307_200,
    },
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
        # AUROC on the meaning (reading, units 1–6) and form (grammar, units 7–20) questions.
        "parts": {
            part: {
                "questions": record["groups"][group]["scored"],
                "auroc": record["groups"][group]["auroc"],
                "auroc_interval": record["groups"][group].get("auroc_interval"),
            }
            for part, group in (("meaning", "reading"), ("form", "grammar"))
            if record["groups"].get(group, {}).get("auroc") is not None
        },
        "aurc": overall["aurc"],
        "ece": overall["ece"],
        "brier": overall["brier"],
        "coverage_accuracy": overall["coverage_accuracy"],
        "coverage_intervals": overall.get("coverage_intervals"),
        # [coverage, risk] at even coverages, highest confidence first: the risk–coverage curve.
        "risk_coverage": record.get("risk_coverage"),
        # Calibration bins: answers, mean confidence and accuracy per equal-width confidence bin.
        "reliability": [
            {key: interval[key] for key in ("low", "high", "questions", "mean_confidence", "accuracy")}
            for interval in record.get("reliability") or []
        ],
        "median_right": extremes["median_right"],
        "median_wrong": extremes["median_wrong"],
        "sure": extremes["sure"],
        # The same counts before the key audit, with the questions it excluded graded by the printed key;
        # None for runs that never answered those questions.
        "sure_before_audit": (record.get("confidence_extremes_before_audit") or {}).get("sure"),
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
    # Runs over a whole question set; repeats and runs on listed questions have their own report sections.
    full = [
        record
        for record in records
        if record["evaluated"] == record["eligible_total"]
        and record.get("replace_key_text") is None
        and record.get("repeat") is None
        and not record.get("question_list")
    ]
    if not full:
        raise ValueError("the report holds no run over a full question set")
    # The runs graded against the same question bank as the newest one, whichever version they ran on.
    newest = max(full, key=lambda record: record["updated"])
    full_set = newest["eligible_total"]

    def bank(record: dict[str, Any]) -> str:
        return record.get("graded_sha256") or record["dataset_sha256"]

    selected = [record for record in full if bank(record) == bank(newest)]
    if any(record["eligible_total"] != full_set for record in selected):
        raise ValueError(f"the full runs on {Path(newest['dataset']).name} do not all cover {full_set} questions")
    unit_names = sorted(selected[0]["categories"], key=unit_number)
    totals = {name: selected[0]["categories"][name]["total"] for name in unit_names}
    versions = {item["newer"]: item for item in analysis.get("versions", [])}

    def described(record: dict[str, Any]) -> dict[str, Any]:
        """How the page names a run: its model's display name, the variant and the reasoning setting."""
        provider_name = record.get("provider", "ollama")
        provider = PROVIDERS.get(provider_name)
        if provider is None:
            raise ValueError(f"run {record['run_id']} ({record['model']}, {provider_name}): unknown provider; add it to PROVIDERS")
        variants = [VARIANTS.get(provider_name), "options shuffled" if record.get("shuffle_options") is not None else None]
        return {
            "model": record["model"],
            "name": MODELS.get(record["model"], {}).get("name", record["model"]),
            "variant": ", ".join(variant for variant in variants if variant) or None,
            "reasoning": None if provider["scoring"] else record["thinking"],
        }

    runs = []
    for record in selected:
        provider_name = record.get("provider", "ollama")
        label = f"run {record['run_id']} ({record['model']}, {provider_name})"
        names = described(record)
        provider = PROVIDERS[provider_name]
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
                **names,
                "note": model.get("note"),
                "parameters": model.get("parameters"),
                "active_parameters": model.get("active_parameters"),
                "provider": provider_name,
                "access": model.get("access", provider["access"]),
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
                # A self-hosted run priced at another model's rate or an assumed rate: a valuation, not a charge.
                "hypothetical_cost": cost is not None and provider["billing"] == "local",
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
    exported = {record["run_key"]: record for record in selected}
    # Tied groups (the report's compact letter display): the letters, and how many pairs were tested.
    groups = {exported[item["run_key"]]["run_id"]: item for item in analysis.get("groups", []) if item["run_key"] in exported}
    for run in runs:
        run["group"] = groups[run["run"]]["letters"] if run["run"] in groups else None
    group_pairs = max((item["pairs"] for item in groups.values()), default=0)
    runs.sort(key=lambda run: (-run["correct"], run["name"].casefold(), run["run"]))
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
                # [share answered by the decision model, cascade accuracy], highest threshold first.
                "curve": item.get("curve"),
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
                    # The answering run's own stated confidence, another run's option probabilities, or the
                    # share of a sampling run's samples that chose the same option.
                    "kind": "stated"
                    if entry["run"] == item["answers"]
                    else "votes"
                    if exported[entry["run"]].get("provider") == "vllm-vote"
                    else "probability",
                    **{key: entry[key] for key in ("questions", "auroc", "auroc_interval", "risk_coverage")},
                }
                for entry in item["sources"]
                if entry["run"] in exported
            ],
        }
        for item in analysis.get("sources", [])
        if item["answers"] in exported
    ]
    # Repeated runs of one configuration on the same questions: the whole bank, or one fixed sample.
    repeats = []
    for item in analysis.get("repeats", []):
        records = [by_key[key] for key in item["run_keys"] if key in by_key]
        if len(records) != len(item["run_keys"]) or bank(records[0]) != bank(newest) or not item["questions"]:
            continue
        first = records[0]
        repeats.append(
            {
                **described(first),
                "questions_per_request": first["batch_size"],
                "whole_bank": first["evaluated"] == first["eligible_total"],
                "runs": [record["run_id"] for record in records],
                **{
                    key: item[key]
                    for key in (
                        "questions", "accuracy", "changed_answer", "wrong_any", "wrong_every_run_same", "scored",
                        "score_spread_median", "score_identical", "sure_wrong", "sure_wrong_every_run",
                    )
                },
            }
        )
    # Batched setups first, then by mean accuracy.
    repeats.sort(key=lambda item: (-item["questions_per_request"], -sum(item["accuracy"]) / len(item["accuracy"])))
    # Cascades run as pipelines: a frontier run on the questions the decision model passes on.
    pipelines = []
    for item in analysis.get("pipelines", []):
        if item["decision"] not in exported or item["frontier"] not in exported:
            continue
        measured = item.get("measured")
        pipelines.append(
            {
                "decision": exported[item["decision"]]["run_id"],
                "frontier": exported[item["frontier"]]["run_id"],
                **{key: item[key] for key in ("seed", "tolerance_points", "threshold", "held_out", "routed", "simulated")},
                "measured": None
                if measured is None
                else {
                    "pipeline_run": by_key[measured["pipeline_run"]]["run_id"],
                    "alone_run": by_key[measured["alone_run"]]["run_id"],
                    **{key: value for key, value in measured.items() if key not in ("pipeline_run", "alone_run", "alternatives")},
                    # Other configurations run alone on the same held-out questions, for a matched cost.
                    "alternatives": [
                        {**alternative, "run": by_key[alternative["run"]]["run_id"], **described(by_key[alternative["run"]])}
                        for alternative in measured.get("alternatives", [])
                        if alternative["run"] in by_key
                    ],
                },
            }
        )
    # The same configuration asked the same questions with another number of questions per request.
    batching = [
        {
            "run": by_key[item["run"]]["run_id"],
            **described(by_key[item["run"]]),
            **{key: item[key] for key in ("batch_size", "compared_batch_size", "questions", "correct")},
            "others": [
                {**other, "run": by_key[other["run"]]["run_id"], "repeat": by_key[other["run"]].get("repeat")}
                for other in item["others"]
            ],
        }
        for item in analysis.get("batching", [])
        if item["run"] in by_key and all(other["run"] in by_key for other in item["others"])
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
        "group_pairs": group_pairs,
        "paired": paired,
        "cascades": cascades,
        "doubts": doubts,
        "sources": sources,
        "repeats": repeats,
        "pipelines": pipelines,
        "batching": batching,
    }


def export_answers(document: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """The per-question answers of the runs in `data`, from benchmark_ollama.py --export-answers: the main
    runs, the repeats of each repeated configuration and the runs of each measured routing pipeline."""
    dataset = next(
        (item for item in document["datasets"] if item["graded_sha256"] == data["dataset"]["graded_sha256"]), None
    )
    if dataset is None:
        raise ValueError("the answers file has no runs graded against the exported question bank")
    main = {run["run"] for run in data["runs"]}
    repeats = {run: item["runs"] for item in data["repeats"] for run in item["runs"] if run not in main}
    pipelines = {
        item["measured"][role]: {"decision": item["decision"], "frontier": item["frontier"], "role": label}
        for item in data["pipelines"]
        if item.get("measured")
        for role, label in (("pipeline_run", "pipeline"), ("alone_run", "frontier alone"))
    }
    for item in data["pipelines"]:
        for alternative in (item.get("measured") or {}).get("alternatives", []):
            pipelines.setdefault(
                alternative["run"],
                {"decision": item["decision"], "frontier": item["frontier"], "role": "same questions, other configuration"},
            )
    batching = {
        item["run"]: {
            "questions_per_request": item["batch_size"],
            "compared_questions_per_request": item["compared_batch_size"],
            "compared_runs": [other["run"] for other in item["others"]],
        }
        for item in data.get("batching", [])
    }
    by_id = {run["run"]: run for run in dataset["runs"]}
    missing = (main | set(repeats) | set(pipelines) | set(batching)) - set(by_id)
    if missing:
        raise ValueError(f"the answers file lacks runs {sorted(missing)}")
    return {
        "schema_version": document["schema_version"],
        "dataset": {"name": dataset["name"], "graded_sha256": dataset["graded_sha256"]},
        "prompts": document["prompts"],
        "questions": dataset["questions"],
        "runs": [by_id[run] for run in sorted(main)],
        # Each repeat lists the runs of its configuration's repeat set (results.json `repeats`).
        "repeat_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(repeats.items())],
        "pipeline_runs": [{**by_id[run], "pipeline": pipeline} for run, pipeline in sorted(pipelines.items())],
        # Runs of a configuration with another number of questions per request (results.json `batching`).
        "batching_runs": [{**by_id[run], "batching": batch} for run, batch in sorted(batching.items())],
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
