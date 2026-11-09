#!/usr/bin/env python3
"""Write results.json, the data behind the GitHub page, from the benchmark report.

The report (benchmark-results.md) embeds one JSON record per run and one with the comparisons between
runs. Only runs over a full question set are exported, those on the question bank of the most recently
finished full run, without runs whose correct option was replaced, and only aggregate numbers: no
question text, prompts, answers or local paths. Runs with the "I don't know" option (--dont-know) enter
only their own section, `dont_know`, and answers.json's `dont_know_runs`; runs in English (--english) only
theirs, `english_reading`, and answers.json's `english_runs`; runs in English with the option, and the Turkish runs
with the option on the English track's kept questions, only `english_reading.dont_know` and answers.json's
`english_dont_know_runs` and `english_dont_know_turkish_runs`. The option-word check's runs (--dont-know-word english)
enter only `dont_know_option_word` and answers.json's `dont_know_word_runs`, fresh runs of a setup (--rerun) only
`hosted_glide_rerun` and answers.json's `rerun_runs`, and the web grounding test's own runs (the pilots,
WEB_GROUNDING_PILOTS, and the repeats of its first runs, web_grounding_repeat) only `web_grounding` and answers.json's
`web_grounding_runs`. The answers' sections in ANSWER_FILES (the repeat runs, `repeat_runs`) are written to files of
their own beside answers.json, which lists them under `files`, so that no file nears GitHub's 100 MiB limit.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
import math
import random
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import benchmark_metrics as bm  # noqa: E402

RESULT_PATTERN = re.compile(r"<!-- benchmark-result: (\{.*?\}) -->")
ANALYSIS_PATTERN = re.compile(r"<!-- benchmark-analysis: (\{.*?\}) -->")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "results.json"
# The answers' sections written to files of their own next to answers.json, by file: GitHub takes no file over 100 MiB.
# Each file carries answers.json's ANSWERS_HEADER so it stands alone, and answers.json lists them under `files`
# (reproduce.load_answers merges them back). A file over ANSWERS_LIMIT stops the export: move a section out of it here.
ANSWER_FILES = {"answers-repeats.json": ("repeat_runs",)}
ANSWERS_HEADER = ("schema_version", "dataset")
ANSWERS_LIMIT = 80_000_000  # bytes
# The English reading track's public record (runner translate_reading.py publish): flags, per-question hashes, prompts.
ENGLISH_READING_PATH = Path(__file__).resolve().parent / "english-reading.json"
# The site's settings: which runs are decision models (decision_model_providers, not_decision_models; Site.decision).
PAGE_CONFIG_PATH = Path(__file__).resolve().parent / "page_config.json"
SCHEMA_VERSION = 5
# The frozen answer keys, by version (key-changelog.md): the question bank's SHA-256 and the fingerprint of its key as
# scored (bm.answer_key_fingerprint). An export graded against any other key stops: record the change in
# key-changelog.md, add the new key here as the next version and export again, which rescores every run.
ANSWER_KEYS = {
    2: {
        "graded_sha256": "797ad6c868bc1c9485bc54203f58839ad995b0443b7149f6a9e36cf0d07df4d7",
        "fingerprint": "cd7f998de262e355cd28f596465a51f4158211646ee0cbfbc85f5d8cdeced20a",
    },
}

# How each provider was reached and paid for. Scoring providers rate the supplied options instead of generating
# an answer, so they have no reasoning setting. billing: "api" (billed per token), "subscription" (a flat plan;
# the cost is what the same tokens cost on the API), "free" (a free tier) or "local" (our GPUs). A run's price comes
# from the report (PRICES, GPU_RATE and GPU_TIME in benchmark_ollama.py), and its cost basis from the price: a free-tier
# run is estimated at the list price of the model it called, and a local run at its maker's list price for the same
# model ("maker"), else at a public host's list price for the same weights ("weights"), else from its GPU time at a
# public on-demand GPU price ("gpu"); all three are estimates, not what our hardware cost. A local run the runner could
# not estimate (no request time) has no cost. A model's "access" and "billing" in MODELS replace its provider's.
# The cost bases each billing allows a priced run, by the price's applies_to: the basis results.json gives it.
COST_BASES = {"api": {"billed": "api"}, "subscription": {"billed": "subscription"}, "free": {"free tier": "free tier"},
              "local": {"maker": "maker", "weights": "weights", "gpu": "gpu"}}
PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {"access": "Ollama, self-hosted", "scoring": False, "billing": "local"},
    "vllm": {"access": "vLLM, self-hosted", "scoring": False, "billing": "local"},
    "jev": {"access": "TypeSafe System One API", "scoring": True, "billing": "api"},
    "open-jev": {"access": "Open-Jev server, self-hosted", "scoring": True, "billing": "local"},
    "perplexity": {"access": "Perplexity Decisions API", "scoring": True, "billing": "api"},
    "liquid": {"access": "Liquid AI decisions API", "scoring": True, "billing": "api"},
    "fastino": {"access": "Fastino System One API", "scoring": True, "billing": "api"},
    "celeris": {"access": "Celeris System One API", "scoring": True, "billing": "api"},
    "subq": {"access": "SubQ Decisions API (public preview)", "scoring": True, "billing": "api"},
    "meragpt": {"access": "meraGPT System One API", "scoring": True, "billing": "api"},
    "laya": {"access": "Laya server, self-hosted", "scoring": True, "billing": "local"},
    "gliner": {"access": "GLiNER2 server, self-hosted", "scoring": True, "billing": "local"},
    "clef": {"access": "Clef server, self-hosted", "scoring": True, "billing": "local"},
    "metask": {"access": "Metask-Jev server, self-hosted", "scoring": True, "billing": "local"},
    "cygnet": {"access": "Cygnet decision server on vLLM, self-hosted", "scoring": True, "billing": "local"},
    "winnow": {"access": "Winnow server (llama.cpp), self-hosted", "scoring": True, "billing": "local"},
    "strands": {"access": "Strands Decider server, self-hosted", "scoring": True, "billing": "local"},
    "pplx-decider": {"access": "Perplexity Decider server, self-hosted", "scoring": True, "billing": "local"},
    "glide": {"access": "GLiDE server (Fastino's release code), self-hosted", "scoring": True, "billing": "local"},
    "vllm-sr": {"access": "vLLM System One endpoint (nightly), self-hosted, BF16", "scoring": True, "billing": "local"},
    "d3-server": {"access": "d3 package server (transformers, the release code), self-hosted, BF16", "scoring": True, "billing": "local"},
    "onejev": {"access": "OneJev server (qev, OmniJev's release code), self-hosted, BF16", "scoring": True, "billing": "local"},
    "nace": {"access": "Nace.AI System One API", "scoring": True, "billing": "api"},
    "drex-max": {"access": "Drex Max server (Nace's loader, drex_max), self-hosted, BF16", "scoring": True, "billing": "local"},
    "d1-server": {"access": "d1 server (Liquid's model code in Transformers, the model card's call), self-hosted, BF16", "scoring": True, "billing": "local"},
    "baselabs": {"access": "Base Labs server (qev, the model card's loader), self-hosted, BF16", "scoring": True, "billing": "local"},
    "reax": {"access": "REAX Engine server (reax13 mode, the maker's release code), self-hosted, FP8", "scoring": True, "billing": "local"},
    "gemini": {"access": "Gemini API", "scoring": False, "billing": "api"},
    "vllm-yes-no": {"access": "vLLM, self-hosted, BF16", "scoring": True, "billing": "local"},
    # vLLM's chat API with the hosted models' stated-confidence request, for a server without token probabilities.
    "vllm-stated": {"access": "vLLM-compatible chat API, self-hosted", "scoring": False, "billing": "local"},
    "vllm-verbal": {"access": "vLLM, self-hosted, BF16", "scoring": False, "billing": "local"},
    "vllm-vote": {"access": "vLLM, self-hosted, BF16", "scoring": False, "billing": "local"},
    # Small open models on logic's server (Ümit, bus #3446, #3475): one question per request, a plain ANSWER: X line, the
    # run identity's request_params as the only request settings (english_reading's plain_access writes its access).
    "vllm-plain": {"access": "our GPU (logic's server)", "scoring": False, "billing": "local"},
    "claude": {"access": "Claude Code CLI, Claude subscription", "scoring": False, "billing": "subscription"},
    "openai": {"access": "Codex CLI, ChatGPT subscription", "scoring": False, "billing": "subscription"},
    "openai-decisions": {"access": "OpenAI Decisions API (public beta)", "scoring": True, "billing": "api"},
    # Other makers' decision models through OpenRouter's System One route; the request time includes OpenRouter's own.
    "openrouter": {"access": "OpenRouter System One API", "scoring": True, "billing": "api"},
    # The backgammon-paired runs: each model through the route, model ID and reasoning setting of its backgammon setup.
    "xai": {"access": "xAI Responses API, SuperGrok subscription", "scoring": False, "billing": "subscription"},
    "antigravity": {"access": "Google Antigravity, Google AI Ultra subscription", "scoring": False, "billing": "subscription"},
    "openrouter-chat": {"access": "OpenRouter chat API, one provider endpoint, fallbacks off", "scoring": False, "billing": "api"},
}
# The token totals a price applies to (TOKEN_KINDS in benchmark_ollama.py): every prompt token, the cache reads
# and writes among them, and the output.
TOKEN_KINDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "cache_write_1h_input_tokens",
    "output_tokens",
)
# Where a run's confidence comes from (the report's score_source), as the page names it: a scoring provider's score for
# the option it chose (SCORING_SOURCE), the probability of the answer letter a generative model wrote, the number a
# model writes with its answer, or the share of ten sampled answers that agree with the chosen one.
CONFIDENCE_SOURCES = {
    "probability": "Answer letter probability",
    "stated": "Written estimate",
    "votes": "Agreement across ten answers",
}
SCORING_SOURCE = "Option score"
# Runs of one model through different providers.
VARIANTS = {
    "vllm-yes-no": "yes/no scoring",
    "vllm-verbal": "stated confidence",
    "vllm-vote": "vote share",
    "openai-decisions": "Decisions API, beta",
    # The route, wherever a table, chart or model page shows the setup.
    "openrouter": "via OpenRouter",
    "pplx-decider": "local",
    "glide": "local",
    # The engine and the checkpoint revision of the d3 package server's one setup, vLLM-SR d3-ultra.
    "d3-server": "transformers, rev 52ba9e7",
}
GPU = "RTX PRO 6000 Blackwell (96 GB)"
SPARK = "DGX Spark, GB10 (128 GB unified memory)"
# Display names, and for models on our GPUs the hardware and precision. Each model's size is its record in SIZES.
MODELS: dict[str, dict[str, Any]] = {
    "gpt-6-astra": {"name": "GPT-6 Astra"},
    "gpt-6.1-sol": {"name": "GPT-6.1 Sol"},
    "gpt-6.1-terra": {"name": "GPT-6.1 Terra"},
    "gpt-6-luna": {"name": "GPT-6 Luna"},
    "claude-opus-5-5": {"name": "Claude Opus 5.5"},
    "claude-sonnet-5-5": {"name": "Claude Sonnet 5.5"},
    "gemma-4-31B-it": {
        "name": "Gemma 4 31B",
        "access": "vLLM, self-hosted, FP8",
        "hardware": f"1 × {GPU}; FP8 weights and KV cache",
    },
    "deepseek-v4.1-flash": {
        # Every DeepSeek-V4.1-Flash run here (58 to 121, 4 and 5 October 2026) served the first release: the server
        # pinned revision fb2764a until it moved to DeepSeek's minor update DeepSeek-V4.1-Flash-1017 on 17 October.
        "name": "DeepSeek-V4.1-Flash, first release",
        "access": "SGLang, self-hosted, published mixed precision; first-release weights (revision fb2764a), not the 1017 update",
        "hardware": f"4 × {GPU}; FP4 experts, FP8 and BF16 layers",
    },
    "deepseek-v4.1-flash-1017": {
        # DeepSeek's minor update of 17 October 2026 (deepseek-ai/DeepSeek-V4.1-Flash-1017, the same config, tokenizer
        # and inference code as the first release; every weight shard changed), on the first release's SGLang server
        # with its arguments, from 5 November 2026.
        "name": "DeepSeek-V4.1-Flash 1017",
        "access": "SGLang, self-hosted, published mixed precision; 1017 weights (revision 1bae0e1)",
        "hardware": f"4 × {GPU}; FP4 experts, FP8 and BF16 layers",
    },
    "deepseek/deepseek-v4.1-flash-1017": {
        "name": "DeepSeek-V4.1-Flash-1017",
        "access": "OpenRouter chat API, DeepSeek's own endpoint, fallbacks off",
    },
    "glm-5.3-flash": {
        "name": "GLM-5.3-Flash",
        "access": "TensorFold, self-hosted, EXL3 4-bit experts",
        "hardware": f"4 × {GPU}; EXL3 4-bit experts, FP8 dense layers and KV cache",
    },
    "grok-4.7": {"name": "Grok 4.7"},
    "gemini-4-argon": {"name": "Gemini 4 Argon"},
    "claude-fable-5-1": {"name": "Claude Fable 5.1"},
    "moonshotai/kimi-k3.1-pro": {
        "name": "Kimi K3.1 Pro",
        "access": "OpenRouter chat API, Moonshot AI's endpoint (mxfp4), fallbacks off",
    },
    "z-ai/glm-5.3": {"name": "GLM-5.3", "access": "OpenRouter chat API, Fireworks endpoint, fallbacks off"},
    # Open-weights chat models through OpenRouter, reasoning high; parameters from each model card.
    "minimax/minimax-m3.1-flash": {
        "name": "MiniMax-M3.1-Flash",
        "access": "OpenRouter chat API, MiniMax's own endpoint, fallbacks off, output cap 65,536 tokens, reasoning included; "
                  "JSON mode without the answer schema (the endpoint has no structured outputs), so the prompt adds a "
                  "paragraph stating the answer layout",
    },
    "thinkingmachines/inkling-small": {
        "name": "Inkling Small",
        "access": "OpenRouter chat API, DeepInfra's endpoint (fp8), fallbacks off, output cap 65,536 tokens, reasoning "
                  "included; no response format (the endpoint has no structured outputs), so the prompt adds a paragraph "
                  "stating the answer layout",
    },
    "qwen/qwen3.5-397b-a17b": {
        "name": "Qwen 3.5 397B-A17B",
        "access": "OpenRouter chat API, DeepInfra's endpoint (fp8), fallbacks off, output cap 65,536 tokens, reasoning included",
    },
    "xiaomi/mimo-v2.6-flash": {
        "name": "MiMo V2.6 Flash",
        "access": "OpenRouter chat API, Xiaomi's own endpoint (fp8), fallbacks off, output cap 65,536 tokens, reasoning included",
    },
    "jev-1.13.0": {"name": "Jev 1.13.0"},
    "jev-1.14.0": {"name": "Jev 1.14.0"},
    "open-jev-27b-v1.1": {
        "name": "Open-Jev 27B v1.1",
        "note": "Fine-tune of Qwen3.8-27B (LoRA and a scoring head)",
        "hardware": f"1 × {GPU}; BF16",
    },
    "pplx-decider-v1-27b": {"name": "Perplexity Decider 27B v1"},
    "pplx-decider-v1.1-27b": {"name": "Perplexity Decider 27B v1.1"},
    # Perplexity's released checkpoints run on a DGX Spark (GB10).
    "pplx-decider-v1.2": {
        "name": "Perplexity Decider 27B v1.2 (local GPU)",
        "note": "Perplexity's released checkpoint, run on our hardware. Its run through Perplexity's Decisions API is a "
        "setup of its own.",
        "hardware": f"1 × {SPARK}; BF16",
    },
    "pplx-decider-flash-v1.2": {
        "name": "Perplexity Decider Flash v1.2",
        "note": "Perplexity's released Flash checkpoint, based on Qwen3.5-4B, run on our hardware. An API run is pending; "
        "this is an additional local setup.",
        "hardware": f"1 × {SPARK}; BF16",
    },
    # It ran on a DGX Spark (GB10).
    "glide-v1.2": {
        "name": "Fastino GLiDE v1.2",
        "note": "Fastino's released checkpoint, a modified Qwen3.8-27B, run on our hardware through the server it ships. "
        "Fastino's hosted GLiDE gave the same answers on 20 sample questions on 22 October 2026; the other GLiDE row is "
        "the hosted model as it answered on 6 October 2026, before a change on Fastino's side.",
        "hardware": f"1 × {SPARK}; BF16",
    },
    # It ran on one RTX PRO 6000 Blackwell (96 GB).
    "vllm-sr/d3": {
        "name": "vLLM-SR d3",
        "note": "The vLLM Semantic Router's released Decision 3.0 checkpoint (vllm-sr/d3 at 20f37b9), fine-tuned from "
        "Qwen3.8-27B (Qwen3.5 architecture), served on our hardware through vLLM's System One endpoint by a nightly build "
        "(0.32.1rc1.dev613+g8977b13a1) with --max-num-seqs 256: with the default, vLLM's startup memory check did not fit "
        "the GPU. One request at a time, as for the other setups.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # It ran on one RTX PRO 6000 Blackwell (96 GB).
    "vllm-sr/d3-ultra": {
        "name": "vLLM-SR d3-ultra",
        "note": "The vLLM Semantic Router's released d3-ultra checkpoint (vllm-sr/d3-ultra at 52ba9e7), fine-tuned from "
        "Qwen3.8-27B (Qwen3.5 architecture), served on our hardware through the server its repository ships (d3_server.py, "
        "the package's transformers runtime as in the model card's Quickstart; transformers 5.17.0). vLLM cannot serve it "
        "yet: it rejects the checkpoint's attention mode (prefix_bidir). One request at a time, as for the other setups.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # It ran on one RTX PRO 6000 Blackwell (96 GB).
    "OmniJev/OneJev-27B": {
        "name": "OneJev 27B",
        "note": "OmniJev's released OneJev checkpoint (OmniJev/OneJev-27B at a5e5f55), a full fine-tune of Qwen3.8-27B that "
        "also reads images, served on our hardware through the server its package ships (qev 0.1.4, qev serve) with its "
        "defaults. One request at a time, as for the other setups. The five runs are identical because decoding is "
        "deterministic: each run sent all 2,198 questions again as separate requests.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # Nace.AI's hosted Drex Max v1.1 (released 28 October 2026): a newer checkpoint than the open v1; no published weights.
    "drex-max-v1.1": {
        "name": "Drex Max 1.1",
        "note": "Nace.AI's hosted Drex Max v1.1 (drex-max-v1.1, released 28 October 2026), a newer checkpoint than the open "
        "Drex Max v1 weights; Nace publishes no weights for it. Nace bills $0.03 per million input tokens during its launch, "
        "half the $0.06 list price the cost here uses.",
    },
    # It ran on one RTX PRO 6000 Blackwell (96 GB).
    "drex-max-v1": {
        "name": "Drex Max v1",
        "note": "Nace.AI's released Drex Max weights (nace-ai/drex-max-v1 at cac65e1), the original Drex Max, a fine-tune "
        "of Qwen3.8-27B that also reads images. It ran on our hardware through Nace's own loader (drex_max, from "
        "nace-ai/drex-decision-models at e206b27), which makes 16 of the 64 layers attend non-causally, behind our HTTP "
        "server (servers/drex_max_server.py). One request at a time, as for the other setups.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # Nace.AI's hosted Drex 2.0 (its size: SIZES).
    "drex-v2.0": {
        "name": "Drex 2.0",
        "note": "Nace.AI's hosted Drex 2.0 (drex-v2.0, released 6 October 2026), built on Qwen3.6-35B-A3B. It reads text "
        "only, so it is not on the Page images tab. Nace's API gives its option probabilities rounded to 4 decimal places, "
        "so they sum to 1 only within that rounding; the check before its runs allowed for it.",
    },
    # It ran on one RTX PRO 6000 Blackwell (96 GB).
    "LiquidAI/d1-2B": {
        "name": "Liquid d1-2B (open weights)",
        "note": "Liquid AI's released d1-2B weights (LiquidAI/d1-2B at 10e7671), a decision model built on LFM3-VL-2B that "
        "also reads images. It ran on our hardware through its model card's own call (model.system_one, Liquid's model code "
        "in Transformers) behind our HTTP server (servers/d1_server.py), one request at a time. Liquid lists 16 languages "
        "for it; Turkish is not among them.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # Each ran on one RTX PRO 6000 Blackwell (96 GB).
    "baselabs/elephant-1": {
        "name": "Elephant-1",
        "note": "Base Labs' released elephant-1 weights (baselabs/elephant-1 at b3f8a93), a decision model post-trained from "
        "Qwen3.5-9B that also reads images. It ran on our hardware through its model card's loader (qev's DecisionEngine from "
        "OneJev at 81ce62f with the checkpoint's serve.patch, as the card's setup.sh installs it) behind our HTTP server "
        "(servers/baselabs_server.py), one request at a time. That runtime reads images only through an engine the patch "
        "leaves without the attention the model was trained with, so it is not on the Page images tab. The card mentions a "
        "trained \"I don't know\" option, but its answers have no such output, and our questions offer five options. "
        "Probabilities rounded to 6 decimals by the model's own loader. They sum to 1 only within that rounding, and the "
        "check before its runs allowed for it. Its card lists English only.",
        "hardware": f"1 × {GPU}; BF16",
    },
    "baselabs/mammoth-1": {
        "name": "Mammoth-1",
        "note": "Base Labs' released mammoth-1 weights (baselabs/mammoth-1 at 61cec44), a decision model post-trained from "
        "Qwen3.5-27B that also reads images. It ran on our hardware through its model card's loader (qev's DecisionEngine from "
        "OneJev at 81ce62f with the checkpoint's serve.patch, as the card's setup.sh installs it) behind our HTTP server "
        "(servers/baselabs_server.py), one request at a time. That runtime reads images only through an engine the patch "
        "leaves without the attention the model was trained with, so it is not on the Page images tab. The card mentions a "
        "trained \"I don't know\" option, but its answers have no such output, and our questions offer five options. "
        "Probabilities rounded to 6 decimals by the model's own loader. They sum to 1 only within that rounding, and the "
        "check before its runs allowed for it. Its card lists English only.",
        "hardware": f"1 × {GPU}; BF16",
    },
    # The engine loads both parts in FP8 (block-128) on one RTX PRO 6000 Blackwell (96 GB), peak reserved memory about
    # 88.5 GiB (the model card).
    "reax13": {
        "name": "REAX 1.3",
        "note": "REAX's released REAX 1.3 weights (decisionmodels/REAX-1.3 at fa4bf7e), a decision model of two parts that "
        "both score every question; each option's probability is the 50/50 mean of the two parts'. Part G blends "
        "CharlieBT/gx31-decider (Gemma line, from tattrongvu/Jeffan-31b-1710) with PelaAI/KnowLine-31B-Gen1 (Gemma-4-31B); "
        "part Q blends gurujustin/sn92-gen-p5 (Qwen3.5-27B line, through baselabs/mammoth-1) with vllm-sr/d3-ultra. The "
        "model card calls REAX a decentralised lab on Bittensor subnet 92. It ran on our hardware through the maker's engine "
        "(the reax13 mode of reaxlabs/reax-engine at ff8f595, its own server, serve.py), both parts in FP8 (block-128) on "
        "one RTX PRO 6000 Blackwell, text only, one request at a time. Its card lists English only.",
        "hardware": f"1 × {GPU}; FP8 (block-128)",
    },
    "fastino/GLiDE": {"name": "Fastino GLiDE", "note": "Hosted decision model; Fastino describes it as reasoning on uncertain decisions"},
    "celeris-1-decision": {"name": "Celeris-1 Decision"},
    "celeris-1.1-decision": {"name": "Celeris-1.1 Decision"},
    "subq-snap-preview": {"name": "SubQ Snap Preview"},
    # SubQ's subq-snap-1.1 through its Decisions API, in public preview; it also reads images (Page images tab). Its
    # option probabilities arrive as 32-bit floats.
    "subq-snap-1.1": {
        "name": "SubQ Snap 1.1",
        "note": "SubQ's subq-snap-1.1, in public preview, through its Decisions API, which also takes images. Its option "
        "probabilities arrive as 32-bit floats, so they sum to 1 only within 32-bit rounding. Its probability check used an "
        "experimental 32-bit rule of ours. For this model only, the check before its runs accepted a sum within one 32-bit "
        "epsilon (2^-23) per option when every value is an exact 32-bit float, instead of 7 decimal places; this is our "
        "tolerance, not an error bound SubQ states. The values are stored as SubQ returned them.",
    },
    "decider-1": {"name": "meraGPT Decider 1", "note": "Hosted decision model; meraGPT serves its current version under this name"},
    "d1:free": {"name": "Liquid d1", "billing": "free"},
    "d1-ultra": {"name": "Liquid d1-ultra"},
    "d1.1": {"name": "Liquid d1.1"},
    # Through OpenRouter's System One route; the variant names the route.
    "microsoft/microsoft-decision-1": {
        "name": "Microsoft-Decision-1",
        "note": "Microsoft's decision model, called through OpenRouter's System One route.",
    },
    "inception/mercury-decide": {
        "name": "Inception Mercury Decide",
        "note": "Inception's decision model, called through OpenRouter's System One route (paid listing). It returns a "
        "probability for each option.",
    },
    "laya": {"name": "Laya", "note": "Encoder with a decision head", "hardware": f"1 × {GPU}"},
    "laya-multilingual": {
        "name": "Laya multilingual",
        "note": "Encoder with a decision head",
        "hardware": f"1 × {GPU}",
    },
    "qwen38-27b-bf16": {
        "name": "Qwen3.8-27B",
        "note": "Open-Jev's base model",
        "hardware": f"1 × {GPU}; BF16",
    },
    "gliner2.5-multi-v1": {
        "name": "GLiNER2.5 Multi (base)",
        "note": "Multilingual extraction and classification model",
        "hardware": f"1 × {GPU}; FP16",
    },
    "gliner2.5-multi-decide": {
        "name": "GLiNER2.5-multi-Decide",
        "note": "Fastino's decision fine-tune of GLiNER2.5 Multi",
        "hardware": f"1 × {GPU}; FP16",
    },
    "clef": {
        "name": "Clef",
        "note": "Cloudflare's decision model, post-trained from Qwen3.8-27B",
        "hardware": f"1 × {GPU}; BF16",
    },
    "clef-flash": {
        "name": "Clef-flash",
        "note": "Cloudflare's 9B decision model, post-trained from Qwen3.5-9B",
        "hardware": f"1 × {GPU}; BF16",
    },
    "metask-jev-4b-policy-mix": {
        "name": "Metask-Jev 4B",
        "note": "Fine-tune of Qwen3.5-4B (merged LoRA)",
        "hardware": f"1 × {GPU}; BF16",
    },
    "cygnet": {
        "name": "Cygnet",
        "note": "Gemma 4 12B IT, unchanged, read out by option letter",
        "hardware": f"1 × {GPU}; BF16",
    },
    "winnow-12b": {
        "name": "Winnow-12B",
        "note": "Fine-tune of Gemma 4 12B IT (Q8_0 GGUF)",
        "hardware": f"1 × {GPU}; Q8_0",
    },
    "strands-decider-2b": {
        "name": "Strands Decider 2B",
        "note": "Amazon's decision model: a LoRA adapter and a decision head on Qwen3.5-2B-Base",
        "hardware": f"1 × {GPU}; BF16",
    },
    "gemini-3.8-flash": {"name": "Gemini 3.8 Flash"},
    "erk-14b": {
        "name": "Erk-14B",
        "note": "Qwen3-14B with continued Turkish training (eCloud)",
        "access": "vLLM, self-hosted, BF16",
        "hardware": f"1 × {GPU}; BF16",
    },
    "qwen3-14b": {
        "name": "Qwen3-14B",
        "note": "Erk-14B's base model",
        "access": "vLLM, self-hosted, BF16",
        "hardware": f"1 × {GPU}; BF16",
    },
    # Ümit's small open models (bus #3446), Reading in English only, served by logic's queue (logic/work/small_models.py
    # SETUPS, whose keys are the model IDs) on one RTX PRO 6000 Blackwell each: the official repo at a pinned revision,
    # through backend in precision (vllm-plain's access text).
    **{key: {"name": name, "backend": backend, "precision": "BF16", "revision": revision, "hardware": f"1 × {GPU}; BF16"}
       for key, name, backend, revision in (
           ("vibethinker-3b", "VibeThinker-3B", "vLLM v0.30.0", "WeiboAI/VibeThinker-3B@77bd2cc"),
           ("lfm2.5-8b-a1b", "LFM2.5-8B-A1B", "vLLM v0.30.0", "LiquidAI/LFM2.5-8B-A1B@dd83f5c"),
           ("gemma-4-e4b-it", "Gemma 4 E4B", "vLLM v0.30.0", "google/gemma-4-E4B-it@4ecc2ba"),
           ("ministral-3-8b-reasoning", "Ministral 3 8B Reasoning", "vLLM v0.30.0",
            "mistralai/Ministral-3-8B-Reasoning-2512@81eaece"),
           ("qwen3.5-4b", "Qwen3.5-4B", "vLLM v0.30.0", "Qwen/Qwen3.5-4B@851bf6e"),
           ("lfm3-1.7b", "LFM3-1.7B", "llama.cpp b12020 (the official GGUF)", "LiquidAI/LFM3-1.7B-GGUF@cd0c74c"),
           ("gemma-4-e2b-it", "Gemma 4 E2B", "vLLM v0.30.0", "google/gemma-4-E2B-it@4adf157"),
           ("gemma-4-12b-it", "Gemma 4 12B", "vLLM v0.30.0", "google/gemma-4-12B-it@43c9d01"),
           ("ministral-3-3b-reasoning", "Ministral 3 3B Reasoning", "vLLM v0.30.0",
            "mistralai/Ministral-3-3B-Reasoning-2512@4a36357"),
           ("ministral-3-14b-reasoning", "Ministral 3 14B Reasoning", "vLLM v0.30.0",
            "mistralai/Ministral-3-14B-Reasoning-2512@51f9210"),
           ("qwen3.5-9b", "Qwen3.5-9B", "vLLM v0.30.0", "Qwen/Qwen3.5-9B@c202236"),
           ("lfm2.5-1.2b-thinking", "LFM2.5-1.2B-Thinking", "vLLM v0.30.0", "LiquidAI/LFM2.5-1.2B-Thinking@fa4681e"),
           ("lfm2-350m-math", "LFM2-350M-Math", "vLLM v0.30.0", "LiquidAI/LFM2-350M-Math@8eb8b70"),
       )},
}
# Setups whose model ID another setup shares, by (provider, model, Perplexity mode): their entry replaces the model's in
# MODELS. The hosted Decider v1.2 (Ümit #1138, #1219, #1229) has the self-hosted checkpoint's model ID; with web
# grounding (--perplexity-mode web_grounding) it is a setup of its own. Their names tell the three apart.
SETUP_MODELS: dict[tuple[str, str, str | None], dict[str, Any]] = {
    ("perplexity", "pplx-decider-v1.2", None): {
        "name": "Perplexity Decider 27B v1.2 (API)",
        "note": "Perplexity's hosted Decider v1.2 through its Decisions API, web grounding off. The other Decider v1.2 "
        "rows are Perplexity's released checkpoint on our hardware and this model with web grounding on.",
    },
    ("perplexity", "pplx-decider-v1.2", "web_grounding"): {
        "name": "Perplexity Decider 27B v1.2 (API, with web)",
        "note": "Perplexity's hosted Decider v1.2 through its Decisions API with web grounding on: a web search per "
        "question, its results added as evidence. The search sends the question out, and for some questions it returned "
        "pages of the bank's source book (the Web grounding page). Its cost is an upper-bound estimate: one $0.001 search "
        "billed per request, while Perplexity bills only completed searches.",
    },
}
# One size record per model ID of MODELS (bus #3467, #3473; coordinator, Zeki #3529), shared by every setup of the ID:
# total (the logical parameter count; None when the maker publishes no size: "not disclosed by maker"), active (a
# mixture of experts' parameters active per token; DeepSeek's two figures, prefill and decode, kept apart), effective
# (only where the maker states one), scope (what the count covers), sources (the maker's official pages, or the checkpoint
# counted as repo@revision from its safetensors headers' logical tensor shapes, never quantized storage, scales, buffers
# or an adapter file alone; for an undisclosed size every official page checked) and read (the date). Never guessed from
# a name, never taken from an open sibling of a hosted model, never a third party's estimate. results.json carries each
# run's record (size_record); the export stops for a setup whose model has none.
READ = "2026-11-09"
SIZES: dict[str, dict[str, Any]] = {
    # Hosted chat models: no maker states a size.
    "gpt-6-astra": {"total": None, "sources": ["https://developers.openai.com/api/docs/models/gpt-6-astra"], "read": READ},
    "gpt-6-luna": {"total": None, "sources": ["https://developers.openai.com/api/docs/models/gpt-6-luna"], "read": READ},
    "gpt-6.1-sol": {"total": None, "sources": ["https://developers.openai.com/api/docs/models/gpt-6.1-sol"], "read": READ},
    "gpt-6.1-terra": {"total": None, "sources": ["https://developers.openai.com/api/docs/models/gpt-6.1-terra"], "read": READ},
    "claude-opus-5-5": {"total": None, "sources": ["https://www.anthropic.com/claude-opus-5-5",
                                                   "https://platform.claude.com/docs/en/models/overview"], "read": READ},
    "claude-sonnet-5-5": {"total": None, "sources": ["https://www.anthropic.com/claude-sonnet-5-5",
                                                     "https://platform.claude.com/docs/en/models/overview"], "read": READ},
    "claude-fable-5-1": {"total": None, "sources": ["https://www.anthropic.com/claude/fable",
                                                    "https://platform.claude.com/docs/en/models/overview"], "read": READ},
    "gemini-3.8-flash": {"total": None, "sources": ["https://deepmind.google/models/model-cards/gemini-3-8-flash/"], "read": READ},
    # The card: "a large scale sparse mixture-of-experts (MoE) ... transformer-based model", with no number.
    "gemini-4-argon": {"total": None, "sources": ["https://deepmind.google/models/model-cards/gemini-4-argon/"], "read": READ},
    "grok-4.7": {"total": None, "sources": ["https://media.x.ai/v1/website/4p7card-5eccc980.pdf", "https://x.ai/news/grok-4-7",
                                            "https://docs.x.ai/developers/models"], "read": READ},
    # Hosted decision models: no maker states a size.
    "celeris-1-decision": {"total": None, "sources": ["https://docs.celeris.ai/decisions", "https://celeris.ai/decisions"],
                           "read": READ},
    "celeris-1.1-decision": {"total": None, "sources": ["https://docs.celeris.ai/decisions", "https://docs.celeris.ai/models",
                                                       "https://celeris.ai/pricing"], "read": READ},
    # Hosted Drex Max v1.1; the open Drex Max v1 weights are another checkpoint.
    "drex-max-v1.1": {"total": None, "sources": ["https://console.nace.ai/docs/drex/reference/models",
                                                 "https://console.nace.ai/docs/drex/guides/drex-max"], "read": READ},
    # Fastino's hosted GLiDE as it answered on 6 October 2026. Fastino's post of 5 November gives 26.09B for the GLiDE 27B
    # its API serves now; the hosted model answered differently from the open v1.2 checkpoint before (the note under
    # MODELS), so that figure is not this run's.
    "fastino/GLiDE": {"total": None, "sources": ["https://docs.fastino.ai/inference/systemone",
                                                 "https://fastino.ai/blog/introducing-glide-the-first-thinking-decision-model"],
                      "read": READ},
    "inception/mercury-decide": {"total": None, "sources": ["https://www.inceptionlabs.ai/"], "read": READ},
    "jev-1.13.0": {"total": None, "sources": ["https://docs.typesafe.ai/models", "https://typesafe.ai/blog/jev-1-14"], "read": READ},
    "jev-1.14.0": {"total": None, "sources": ["https://docs.typesafe.ai/models", "https://typesafe.ai/blog/jev-1-14"], "read": READ},
    # Microsoft names its base model (post-trained from Qwen3.5-9B, to be rebased on other models), not a size.
    "microsoft/microsoft-decision-1": {"total": None, "sources": [
        "https://commandline.microsoft.com/microsoft-decision-1-model-foundry/"], "read": READ},
    "d1:free": {"total": None, "sources": ["https://www.liquid.ai/blog/d1-decision-model"], "read": READ},
    # "we based d1-ultra on a larger open-weight model", unnamed.
    "d1-ultra": {"total": None, "sources": ["https://www.liquid.ai/blog/d1-ultra"], "read": READ},
    "d1.1": {"total": None, "sources": ["https://docs.liquid.ai/lfm/models/decision-models"], "read": READ},
    "subq-snap-preview": {"total": None, "sources": ["https://docs.subq.ai/using-the-api/models/"], "read": READ},
    "subq-snap-1.1": {"total": None, "sources": ["https://docs.subq.ai/using-the-api/models/"], "read": READ},
    # "it is a small model", with no number; the ID now serves Decider 1.1, whose weights meraGPT does not publish.
    "decider-1": {"total": None, "sources": ["https://meragpt.com/models/decider-1",
                                             "https://meragpt.com/blog/introducing-decider-1"], "read": READ},
    # Sizes the makers state. Drex 2.0: "35B parameters in total, about 3B active per token"; counted from its open
    # checkpoint, with the vision tower its card says is not loaded for text.
    "drex-v2.0": {"total": 35_107_181_936, "active": [3_000_000_000],
                  "scope": "mixture of experts: language model with its LM head + 0.45B vision tower (not loaded for text, "
                           "per the card); about 3B active per token, as Nace states it",
                  "sources": ["counted from the checkpoint's safetensors, nace-ai/drex-v2.0@e646674",
                              "https://huggingface.co/nace-ai/drex-v2.0", "https://console.nace.ai/docs/drex/reference/models"],
                  "read": READ},
    # The card's Model Summary: "Total Parameters | 2.8T", "Activated Parameters | 104B" (rounded; the safetensors at
    # d9e99b0 hold 2,780,110,363,392).
    "moonshotai/kimi-k3.1-pro": {"total": 2_800_000_000_000, "active": [104_000_000_000],
                                 "scope": "mixture of experts, as the model card states it",
                                 "sources": ["https://huggingface.co/moonshotai/Kimi-K3.1-Pro"], "read": READ},
    # Released decision checkpoints, counted from their safetensors headers (logical shapes; buffers such as a stored
    # calibration temperature or Gemma's layer_scalar left out). Hugging Face's own total for the Perplexity, vLLM-SR,
    # GLiDE and Drex Max repos counts only the index's files and so leaves out readout.safetensors (1,305,600).
    # Perplexity's API setups of a version share its released checkpoint's record.
    "pplx-decider-v1-27b": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                            "sources": ["counted from the checkpoint's safetensors, perplexity-ai/pplx-decider-v1-27b@5117a6c",
                                        "https://huggingface.co/perplexity-ai/pplx-decider-v1-27b"], "read": READ},
    "pplx-decider-v1.1-27b": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                              "sources": ["counted from the checkpoint's safetensors, perplexity-ai/pplx-decider-v1.1-27b@5cd25e3",
                                          "https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b"], "read": READ},
    "pplx-decider-v1.2": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                          "sources": ["counted from the checkpoint's safetensors, perplexity-ai/pplx-decider-v1.2@225c913 "
                                      "(the same weights as cce0f3f)", "https://huggingface.co/perplexity-ai/pplx-decider-v1.2"],
                          "read": READ},
    "pplx-decider-flash-v1.2": {"total": 4_539_918_336,
                                "scope": "language model (tied embeddings) + 0.33B vision encoder + 255-way readout",
                                "sources": ["counted from the checkpoint's safetensors, perplexity-ai/pplx-decider-flash-v1.2@6d771ad",
                                            "https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2"], "read": READ},
    # Fastino's post: "serves 57.36B parameters versus GLiDE's 26.09B".
    "glide-v1.2": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                   "sources": ["counted from the checkpoint's safetensors, fastino/GLiDE@a7e4589",
                               "https://fastino.space/blog/glide-decision-model-family"], "read": READ},
    # The cards: "26.09B, including the 0.46B vision encoder".
    "vllm-sr/d3": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                   "sources": ["counted from the checkpoint's safetensors, vllm-sr/d3@20f37b9", "https://huggingface.co/vllm-sr/d3"],
                   "read": READ},
    "vllm-sr/d3-ultra": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                         "sources": ["counted from the checkpoint's safetensors, vllm-sr/d3-ultra@52ba9e7",
                                     "https://huggingface.co/vllm-sr/d3-ultra"], "read": READ},
    "OmniJev/OneJev-27B": {"total": 27_356_728_560, "scope": "language model with its LM head + 0.46B vision encoder",
                           "sources": ["counted from the checkpoint's safetensors, OmniJev/OneJev-27B@a5e5f55",
                                       "https://huggingface.co/OmniJev/OneJev-27B"], "read": READ},
    # The card: "a dense 27B-parameter model with a 255-way readout head".
    "drex-max-v1": {"total": 26_086_635_760, "scope": "language model (no LM head) + 0.46B vision encoder + 255-way readout",
                    "sources": ["counted from the checkpoint's safetensors, nace-ai/drex-max-v1@cac65e1",
                                "https://huggingface.co/nace-ai/drex-max-v1"], "read": READ},
    # The card: 1.92B.
    "LiquidAI/d1-2B": {"total": 1_918_181_888, "scope": "language model (tied embeddings) + 0.16B vision encoder + projector",
                       "sources": ["counted from the checkpoint's safetensors, LiquidAI/d1-2B@10e7671",
                                   "https://huggingface.co/LiquidAI/d1-2B"], "read": READ},
    # The cards: "a 9B parameter decision model", "a 27B parameter decision model".
    "baselabs/elephant-1": {"total": 9_409_813_744, "scope": "language model with its LM head + 0.46B vision encoder",
                            "sources": ["counted from the checkpoint's safetensors, baselabs/elephant-1@b3f8a93",
                                        "https://huggingface.co/baselabs/elephant-1"], "read": READ},
    "baselabs/mammoth-1": {"total": 27_356_728_560, "scope": "language model with its LM head + 0.46B vision encoder",
                           "sources": ["counted from the checkpoint's safetensors, baselabs/mammoth-1@61cec44",
                                       "https://huggingface.co/baselabs/mammoth-1"], "read": READ},
    # Both parts score every question; the card states no count.
    "reax13": {"total": 57_359_722_272, "scope": "two full models: part G (Gemma 4 31B line, with vision encoder) + part Q "
                                                  "(Qwen3.8-27B line, with vision encoder and 255-way readout)",
               "sources": ["counted from the checkpoint's safetensors, decisionmodels/REAX-1.3@fa4bf7e",
                           "https://huggingface.co/decisionmodels/REAX-1.3"], "read": READ},
    # The card: "ModernBERT-large (395M ...) + a decision head ... 421M total"; laya multilingual "mmBERT-base | 322M".
    "laya": {"total": 421_293_827, "scope": "ModernBERT-large encoder + decision head",
             "sources": ["counted from the checkpoint's safetensors, convaiinnovations/laya@c5d7873",
                         "https://huggingface.co/convaiinnovations/laya"], "read": READ},
    "laya-multilingual": {"total": 321_908_995, "scope": "mmBERT-base encoder + decision head",
                          "sources": ["counted from the checkpoint's safetensors, convaiinnovations/laya@c5d7873 (multilingual/)",
                                      "https://huggingface.co/convaiinnovations/laya"], "read": READ},
    # The cards: 287M.
    "gliner2.5-multi-v1": {"total": 287_355_159, "scope": "mDeBERTa-v3-base encoder + extraction and classification heads",
                           "sources": ["counted from the checkpoint's safetensors, fastino/gliner2.5-multi-v1@2ca71aa",
                                       "https://huggingface.co/fastino/gliner2.5-multi-v1"], "read": READ},
    "gliner2.5-multi-decide": {"total": 287_355_159, "scope": "mDeBERTa-v3-base encoder + extraction and classification heads",
                               "sources": ["counted from the checkpoint's safetensors, fastino/GLiNER2.5-multi-Decide@a35a0cd",
                                           "https://huggingface.co/fastino/GLiNER2.5-multi-Decide"], "read": READ},
    # The cards: "a 27B multimodal model", "a 9B multimodal model".
    "clef": {"total": 27_484_784_884, "scope": "language model with its LM head + 0.46B vision encoder + joint schema head",
             "sources": ["counted from the checkpoint's safetensors, Cloudflare/clef@2f3de3d", "https://huggingface.co/Cloudflare/clef"],
             "read": READ},
    "clef-flash": {"total": 9_531_576_564, "scope": "language model with its LM head + 0.46B vision encoder + joint schema head",
                   "sources": ["counted from the checkpoint's safetensors, Cloudflare/clef-flash@fde727a",
                               "https://huggingface.co/Cloudflare/clef-flash"], "read": READ},
    # The card: "params | 4.54B".
    "metask-jev-4b-policy-mix": {"total": 4_539_265_536,
                                 "scope": "Qwen3.5-4B with its LoRA merged: language model (tied embeddings) + 0.33B vision encoder",
                                 "sources": ["counted from the checkpoint's safetensors, wayfind/metask-jev-4b-policy-mix@ea20fe8",
                                             "https://huggingface.co/wayfind/metask-jev-4b-policy-mix"], "read": READ},
    # Gemma 4 12B IT unchanged; the card: "Total Parameters ... 11.95B".
    "cygnet": {"total": 11_959_730_176, "scope": "Gemma 4 12B IT: language model (tied embeddings) + vision and audio embedders",
               "sources": ["counted from the checkpoint's safetensors, google/gemma-4-12B-it@707f0a3",
                           "https://huggingface.co/google/gemma-4-12B-it"], "read": READ},
    # Counted from the Q8_0 GGUF's logical tensor shapes (not its packed storage): exactly Gemma 4 12B's language model.
    "winnow-12b": {"total": 11_907_350_272, "scope": "language model only (Gemma 4 12B architecture, LoRA merged; text only)",
                   "sources": ["counted from the GGUF's logical tensor shapes, EldanRing/Winnow-12B@b2b1421 (Winnow-12B-Q8_0.gguf)",
                               "https://huggingface.co/EldanRing/Winnow-12B"], "read": READ},
    # The model as run (the three sites' rule, bus #3550-#3552): the base checkpoint as released, with the adapter and
    # head; the repos hold only the adapter and head. Strands: Qwen3.5-2B-Base 2,274,069,824 (its 0.33B vision encoder
    # and 61M multi-token prediction layer included) + LoRA 16,819,200 + head 1,053,184. Open-Jev, whose card says "a
    # trained LoRA adapter and scalar decision head for the text backbone of Qwen/Qwen3.8-27B ... 15,471,617 trained
    # parameters": Qwen3.8-27B 27,781,427,952 + 15,471,617.
    "strands-decider-2b": {"total": 2_291_942_208,
                           "scope": "Qwen3.5-2B-Base (with its vision encoder) + LoRA adapter + readout head; the repo "
                                    "holds only the adapter and head",
                           "sources": ["counted from the checkpoints' safetensors, StrandsAgents/strands-decider-2B-hobson-v21@2b52a62 "
                                       "on Qwen/Qwen3.5-2B-Base@b1485b2",
                                       "https://huggingface.co/StrandsAgents/strands-decider-2B-hobson-v21"], "read": READ},
    "open-jev-27b-v1.1": {"total": 27_796_899_569,
                          "scope": "Qwen3.8-27B (with its vision encoder) + LoRA adapter and scalar decision head (15.5M); "
                                   "the repo holds only the adapter and head",
                          "sources": ["counted from the checkpoints' safetensors, ZefanCai/Open-Jev-27B-v1.1@28cf730 on "
                                      "Qwen/Qwen3.8-27B@1d4bf0f", "https://huggingface.co/ZefanCai/Open-Jev-27B-v1.1"],
                          "read": READ},
    # Open chat models on our GPUs, counted from their checkpoints' safetensors headers. Gemma 4 31B's card: "Total
    # Parameters ... 30.7B" and "Vision Encoder Parameters ... ~550M"; its stored layer_scalar and vision std_bias and
    # std_scale buffers (2,364) are left out. Qwen3.8-27B's card: "Number of Parameters: 27B"; Qwen3-14B's: "14.8B";
    # Erk-14B's: "a 14-billion-parameter, Turkish-focused large language model".
    "gemma-4-31B-it": {"total": 31_273_086_512, "scope": "language model (tied embeddings) + 0.58B vision encoder",
                       "sources": ["counted from the checkpoint's safetensors, google/gemma-4-31B-it@842da37",
                                   "https://huggingface.co/google/gemma-4-31B-it"], "read": READ},
    "qwen38-27b-bf16": {"total": 27_781_427_952, "scope": "language model with its LM head + 0.42B multi-token prediction "
                                                          "layer + 0.46B vision encoder",
                        "sources": ["counted from the checkpoint's safetensors, Qwen/Qwen3.8-27B@1d4bf0f",
                                    "https://huggingface.co/Qwen/Qwen3.8-27B"], "read": READ},
    "qwen3-14b": {"total": 14_768_307_200, "scope": "language model with its LM head (text only)",
                  "sources": ["counted from the checkpoint's safetensors, Qwen/Qwen3-14B@40c0698",
                              "https://huggingface.co/Qwen/Qwen3-14B"], "read": READ},
    "erk-14b": {"total": 14_768_307_200, "scope": "language model with its LM head (text only)",
                "sources": ["counted from the checkpoint's safetensors, ecloudtech/Erk-14B@8584b14",
                            "https://huggingface.co/ecloudtech/Erk-14B"], "read": READ},
    # Mixtures of experts, as their makers state them. DeepSeek: "552B backbone parameters", 8B active per token in
    # prefill and 16B in decode; its separate Engram conditional memory (196B) is not in that figure. The 1017 update
    # states no size of its own, so it reads not disclosed, with the first release's figures in its note (as on the logic
    # and backgammon sites).
    "deepseek-v4.1-flash": {"total": 552_000_000_000, "active": [8_000_000_000, 16_000_000_000],
                            "scope": "backbone, as DeepSeek states it (8B active in prefill, 16B in decode); the 196B Engram "
                                     "memory is separate",
                            "sources": ["https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash"], "read": READ},
    "deepseek-v4.1-flash-1017": {"total": None,
                                 "scope": "V4.1 Flash card (first release): 552B backbone + 196B conditional memory; 8B "
                                          "active in prefill, 16B in decode; the 1017 card states no size",
                                 "sources": ["https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017",
                                             "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash"], "read": READ},
    "deepseek/deepseek-v4.1-flash-1017": {"total": None,
                                          "scope": "V4.1 Flash card (first release): 552B backbone + 196B conditional "
                                                   "memory; 8B active in prefill, 16B in decode; the 1017 card states no size",
                                          "sources": ["https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017",
                                                      "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash"],
                                          "read": READ},
    # "With 320B total parameters and just 18B active parameters"; served as a third party's EXL3 4-bit quantization.
    "glm-5.3-flash": {"total": 320_000_000_000, "active": [18_000_000_000], "scope": "mixture of experts, as Z.ai states it",
                      "sources": ["https://huggingface.co/zai-org/GLM-5.3-Flash"], "read": READ},
    # "Approximately 428B total; 23B activated per token".
    "minimax/minimax-m3.1-flash": {"total": 428_000_000_000, "active": [23_000_000_000],
                                   "scope": "mixture of experts, as MiniMax states it",
                                   "sources": ["https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash"], "read": READ},
    # Counted from the released BF16 checkpoint: language model 263,655,199,232 + multi-token prediction 2,231,912,448 +
    # vision 64,080,384 + audio 5,246,976. The card's "276B total, 12B active" is beside it; the checkpoint alone does not
    # verify the active count, so it stays the card's.
    "thinkingmachines/inkling-small": {"total": 265_956_439_040,
                                       "scope": "mixture of experts: language model + multi-token prediction layer + vision "
                                                "and audio encoders; card: 276B total, 12B active",
                                       "sources": ["counted from the checkpoint's safetensors, thinkingmachines/Inkling-Small@8cc5877",
                                                   "https://thinkingmachines.ai/model-card/inkling-small/",
                                                   "https://huggingface.co/thinkingmachines/Inkling-Small"], "read": READ},
    # "Number of Parameters: 397B in total and 17B activated".
    "qwen/qwen3.5-397b-a17b": {"total": 397_000_000_000, "active": [17_000_000_000],
                               "scope": "mixture of experts, as Qwen states it",
                               "sources": ["https://huggingface.co/Qwen/Qwen3.5-397B-A17B"], "read": READ},
    # "309B total / 15B activated parameters"; OpenRouter serves XiaomiMiMo/MiMo-V2.6-Flash-RL.
    "xiaomi/mimo-v2.6-flash": {"total": 309_000_000_000, "active": [15_000_000_000],
                               "scope": "mixture-of-experts backbone, as Xiaomi states it",
                               "sources": ["https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL"], "read": READ},
    # Z.ai states no size; counted from its checkpoint (logical shapes, FP8 scales left out), with its one multi-token
    # prediction layer (9,952,920,576). Z.ai states no active count.
    "z-ai/glm-5.3": {"total": 753_329_940_480, "scope": "mixture of experts: language model with its LM head + one "
                                                       "multi-token prediction layer (text only); Z.ai states no active count",
                     "sources": ["counted from the checkpoint's safetensors, zai-org/GLM-5.3@ba32f8c",
                                 "https://huggingface.co/zai-org/GLM-5.3", "https://docs.z.ai/guides/llm/glm-5.3"], "read": READ},
    # Ümit's small open models, counted from each released checkpoint at the revision served (logical shapes; Gemma's
    # stored layer_scalar and clip-bound buffers left out), vision encoders and multi-token prediction layers included
    # where the checkpoint holds them (the model as run: the three sites' rule). The makers' words beside each.
    # "with only 3B parameters"
    "vibethinker-3b": {"total": 3_085_938_688, "scope": "language model (tied embeddings, text only)",
                       "sources": ["counted from the checkpoint's safetensors, WeiboAI/VibeThinker-3B@77bd2cc",
                                   "https://huggingface.co/WeiboAI/VibeThinker-3B"], "read": READ},
    # The card: "Total parameters: 8.3B", "Active parameters: 1.5B", the figures of the older LFM2-8B-A1B; this
    # checkpoint's 128,000-token vocabulary adds 127,926,272 embedding parameters. Active: every non-expert parameter
    # and 4 of the 32 experts in each of the 22 expert layers.
    "lfm2.5-8b-a1b": {"total": 8_467_856_832, "active": [1_685_667_264],
                      "scope": "mixture of experts: language model (tied embeddings, text only), counted; the card says "
                               "8.3B total, 1.5B active",
                      "sources": ["counted from the checkpoint's safetensors, LiquidAI/LFM2.5-8B-A1B@dd83f5c",
                                  "https://huggingface.co/LiquidAI/LFM2.5-8B-A1B"], "read": READ},
    # The card: "4.5B effective (8B with embeddings)", "2.3B effective (5.1B with embeddings)"; 11.95B for the 12B.
    "gemma-4-e4b-it": {"total": 7_996_156_448, "effective": 4_500_000_000,
                       "scope": "language model with per-layer embeddings + vision and audio encoders; effective size as "
                                "Google states it",
                       "sources": ["counted from the checkpoint's safetensors, google/gemma-4-E4B-it@4ecc2ba",
                                   "https://huggingface.co/google/gemma-4-E4B-it"], "read": READ},
    "gemma-4-e2b-it": {"total": 5_123_178_016, "effective": 2_300_000_000,
                       "scope": "language model with per-layer embeddings + vision and audio encoders; effective size as "
                                "Google states it",
                       "sources": ["counted from the checkpoint's safetensors, google/gemma-4-E2B-it@4adf157",
                                   "https://huggingface.co/google/gemma-4-E2B-it"], "read": READ},
    "gemma-4-12b-it": {"total": 11_959_730_176, "scope": "language model (tied embeddings) + vision and audio embedders",
                       "sources": ["counted from the checkpoint's safetensors, google/gemma-4-12B-it@43c9d01",
                                   "https://huggingface.co/google/gemma-4-12B-it"], "read": READ},
    # The cards: "3.4B Language Model", "8.4B Language Model", "13.5B Language Model", each with a "0.4B Vision Encoder".
    "ministral-3-3b-reasoning": {"total": 3_849_090_048, "scope": "language model (tied embeddings) + 0.42B vision encoder "
                                                                  "and projector",
                                 "sources": ["counted from the checkpoint's safetensors, "
                                             "mistralai/Ministral-3-3B-Reasoning-2512@4a36357",
                                             "https://huggingface.co/mistralai/Ministral-3-3B-Reasoning-2512"], "read": READ},
    "ministral-3-8b-reasoning": {"total": 8_918_026_240, "scope": "language model with its LM head + 0.43B vision encoder "
                                                                  "and projector",
                                 "sources": ["counted from the checkpoint's safetensors, "
                                             "mistralai/Ministral-3-8B-Reasoning-2512@81eaece",
                                             "https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512"], "read": READ},
    "ministral-3-14b-reasoning": {"total": 13_945_031_680, "scope": "language model with its LM head + 0.44B vision "
                                                                    "encoder and projector",
                                  "sources": ["counted from the checkpoint's safetensors, "
                                              "mistralai/Ministral-3-14B-Reasoning-2512@51f9210",
                                              "https://huggingface.co/mistralai/Ministral-3-14B-Reasoning-2512"], "read": READ},
    # The cards: "Number of Parameters: 4B", "9B" (the language model alone).
    "qwen3.5-4b": {"total": 4_659_865_088, "scope": "language model (tied embeddings) + multi-token prediction layer + "
                                                    "0.33B vision encoder",
                   "sources": ["counted from the checkpoint's safetensors, Qwen/Qwen3.5-4B@851bf6e",
                               "https://huggingface.co/Qwen/Qwen3.5-4B"], "read": READ},
    "qwen3.5-9b": {"total": 9_653_104_368, "scope": "language model with its LM head + multi-token prediction layer + "
                                                    "0.46B vision encoder",
                   "sources": ["counted from the checkpoint's safetensors, Qwen/Qwen3.5-9B@c202236",
                               "https://huggingface.co/Qwen/Qwen3.5-9B"], "read": READ},
    # The cards: "Parameters | 1.73B", "Number of parameters: 1.17B"; LFM2-350M-Math's states none, its base LFM2-350M's
    # "354,483,968". The LFM3 GGUF served holds the same tensors, plus a 64-value RoPE buffer.
    "lfm3-1.7b": {"total": 1_728_801_536, "scope": "language model (tied embeddings, text only)",
                  "sources": ["counted from the checkpoint's safetensors, LiquidAI/LFM3-1.7B@0dc4268",
                              "https://huggingface.co/LiquidAI/LFM3-1.7B"], "read": READ},
    "lfm2.5-1.2b-thinking": {"total": 1_170_340_608, "scope": "language model (tied embeddings, text only)",
                             "sources": ["counted from the checkpoint's safetensors, LiquidAI/LFM2.5-1.2B-Thinking@fa4681e",
                                         "https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking"], "read": READ},
    "lfm2-350m-math": {"total": 354_483_968, "scope": "language model (tied embeddings, text only)",
                       "sources": ["counted from the checkpoint's safetensors, LiquidAI/LFM2-350M-Math@8eb8b70",
                                   "https://huggingface.co/LiquidAI/LFM2-350M-Math", "https://huggingface.co/LiquidAI/LFM2-350M"],
                       "read": READ},
}
# The variant a Perplexity mode adds to a setup's name in tables and charts.
MODE_VARIANTS = {"web_grounding": "with web"}


def model_info(provider: str, model: str, mode: str | None = None) -> dict[str, Any]:
    """A setup's display name, note, size, access, billing and hardware: SETUP_MODELS, else MODELS."""
    return SETUP_MODELS.get((provider, model, mode), MODELS.get(model, {}))


def size_record(model: str) -> dict[str, Any]:
    """A setup's size record as results.json gives it, from SIZES by model ID: total, active per token and effective
    parameters (None where the maker states none; a total of None means the maker discloses no size), the scope counted,
    the sources and the date read."""
    size = SIZES[model]
    return {"parameters": size["total"], "active_parameters": size.get("active"), "effective_parameters": size.get("effective"),
            "parameters_scope": size.get("scope"), "parameters_source": size["sources"], "parameters_read": size["read"]}


def plain_access(info: dict[str, Any], request_params: str) -> str:
    """A vllm-plain run's access text: logic's server with the model's backend, precision and revision (MODELS), the
    plain answer line, and the run identity's request settings (`request_params`, sorted compact JSON): every key but
    max_tokens and chat_template_kwargs as "key value", thinking on or off where chat_template_kwargs sets it, and the
    output cap from max_tokens."""
    params = json.loads(request_params)
    sampling = [f"{key} {value}" for key, value in params.items() if key not in ("max_tokens", "chat_template_kwargs")]
    kwargs = params.get("chat_template_kwargs") or {}
    thinking = next((kwargs[key] for key in ("enable_thinking", "thinking") if isinstance(kwargs.get(key), bool)), None)
    if thinking is not None:
        sampling.append(f"thinking {'on' if thinking else 'off'}")
    text = (f"our GPU (logic's server, {info['backend']} {info['precision']}, revision {info['revision']}), one question "
            f"per request, plain answer line ANSWER: X (no answer schema); sampling {', '.join(sampling) or 'none set'}")
    return text + (f"; output cap {params['max_tokens']:,}" if "max_tokens" in params else "")


def access_text(provider: str, info: dict[str, Any], record: dict[str, Any]) -> str:
    """How a run's setup was called: plain_access for vllm-plain, else the model's access (MODELS, SETUP_MODELS), else its
    provider's."""
    if provider == "vllm-plain":
        if not record.get("request_params"):
            raise ValueError(f"run {record['run_id']} ({record['model']}, vllm-plain): no request_params in its record")
        return plain_access(info, record["request_params"])
    return info.get("access", PROVIDERS[provider]["access"])


def plain_version(document: dict[str, Any], variant: str) -> str | None:
    """The prompt version of a vllm-plain run of a PLAIN_PROMPTS variant ("english", "english_dont_know"), from the
    answers file's plain_prompts hashed as the runner hashes them; None without them."""
    prompts = (document.get("plain_prompts") or {}).get(variant)
    return None if prompts is None else hashed_prompts(prompts)


def run_variant(record: dict[str, Any]) -> str | None:
    """A run's variant: its provider's (VARIANTS), its Perplexity mode's (MODE_VARIANTS) and shuffled options."""
    variants = [VARIANTS.get(record.get("provider", "ollama")), MODE_VARIANTS.get(record.get("perplexity_mode")),
                "options shuffled" if record.get("shuffle_options") is not None else None]
    return ", ".join(variant for variant in variants if variant) or None


def upper_bound_cost(record: dict[str, Any]) -> bool:
    """Whether a run's cost is an upper-bound estimate: with web grounding, the price's fee per request is a fee per
    completed search, counted here for every request."""
    return record.get("perplexity_mode") == "web_grounding" and bool((record.get("price") or {}).get("per_request"))


# Finished runs whose publication is held; the export leaves them out, with their answers, until the hold is lifted.
HELD_RUNS: dict[int, str] = {
    312: "Gemini 4 Argon (high), after the retry of its 9 cut requests: held by Ümit on 28 October 2026 until approval",
}
# Notes on single runs, after their model's note.
RUN_NOTES: dict[int, str] = {
    276: "It stopped after 1,792 answers when the service reported the model at capacity, and was resumed for the other "
         "406 questions; the usage and cost of the failed request are unknown.",
    311: "xAI did not answer 31 attempts within the time limit, and the runner sent each such request again. The run "
         "stopped twice and was resumed from the last answered question: at 1,696 answers, after one request timed out "
         "six times (the limit then went from 15 to 30 minutes), and at 2,144, when a retry sent an expired sign-in "
         "token. The usage and cost of the timed-out attempts are unknown.",
    312: "Antigravity ignored the answer schema in the field the Gemini API reads, so it went as responseSchema. We asked "
         "for up to 65,536 output tokens, the limit our other Gemini runs had; Antigravity cut 9 of the 138 requests at "
         "32,768 output tokens, and only those 9 were asked again, once: 5 came back answered and 4 were cut again, so "
         "their 64 questions count as wrong. The first pass scored 92.0%. The cost counts both attempts.",
    318: "Reasoning on at the chat template's low effort. Five of the 138 replies never left the thinking part, so their "
         "80 questions have no answer and count as wrong. The GPU was shared with another program during the run, so "
         "its request times are longer than on a free GPU.",
    314: "The Fireworks pin admits all of Fireworks' endpoints: OpenRouter billed 135 of the 138 requests at the spot "
         "endpoint's rates, 2 at the standard rates and 1 at the fast endpoint's rates ($1.82 in all); the cost shown "
         "uses the spot rates.",
    340: "Its request times come from one GPU with no other known work while its runs took place, though the GPU was not "
         "monitored throughout. Only this model's server showed on it at 11:55 UTC on 1 November 2026, before the runs, and "
         "nothing at 12:35 UTC, after them; the one other project with a claim on that GPU confirmed it ran nothing there "
         "in between.",
    346: "It was paused twice while the approval of its probability check was confirmed, for 12 minutes and then for 3 "
         "hours 24 minutes, and resumed from its stored answers. The two requests in flight count those pauses in their "
         "times (706 and 12,236 seconds; the first after one retry, when SubQ had closed the connection), so the run's total "
         "request time and questions per minute include them. Without them, its median request time stays 0.378 s and its "
         "90th percentile moves from 0.388 s to 0.387 s.",
}
# Each unit's plain English label; results.json keeps the printed Turkish title next to it.
UNITS_EN = {
    1: "Word and phrase meanings",
    2: "Sentence meanings",
    3: "How a writer explains and develops ideas",
    4: "Topic and main point of a paragraph",
    5: "How a paragraph fits together",
    6: "Details that support a paragraph’s main point",
    7: "Word types, such as nouns and verbs",
    8: "Groups of words built around a noun",
    9: "Verbs and their forms",
    10: "Verb forms used like nouns or modifiers",
    11: "Word endings and what they do",
    12: "How words are built",
    13: "The roles of words and phrases in a sentence",
    14: "How verbs show who acts and who receives the action",
    15: "Types of sentences",
    16: "Questions combining several grammar topics",
    17: "Sound patterns and changes",
    18: "Spelling",
    19: "Punctuation",
    20: "Problems in sentence wording",
}
# Question groups the page shows, from the report's groups.
GROUPS = ("reading", "grammar", "without_suspect")
# The 2026 TYT Türkçe paper's mix of reading and grammar questions, for the reweighted score.
TYT_MIX = {"reading": 33, "grammar": 7}
# The Decider v1.1 replay (results.json `replay`). The decision run answers first, keeping its answers at or above
# each cutoff, and separately its REPLAY_SHARE most confident answers, a share fixed in advance that no answer key
# tunes; the second run answers the rest. Runs by (provider, model, reasoning). The cutoffs include the sure
# threshold, bm.SURE_SCORE.
REPLAY_DECISION = ("perplexity", "pplx-decider-v1.1-27b", None)
REPLAY_FRONTIERS = (
    ("claude", "claude-opus-5-5", "low"),
    ("claude", "claude-sonnet-5-5", "high"),
    ("openai", "gpt-6-astra", "low"),
    ("openai", "gpt-6.1-sol", "low"),
    ("gemini", "gemini-3.8-flash", "low"),
)
# The LLM runs added later (16 questions per request only), placed after REPLAY_FRONTIERS and their format reruns so
# the earlier entries keep their place.
REPLAY_FRONTIERS_ADDED = (
    ("claude", "claude-opus-5-5", "high"),
    ("openai", "gpt-6-astra", "high"),
    ("openai", "gpt-6.1-sol", "high"),
    ("openai", "gpt-6.1-terra", "high"),
    ("openai", "gpt-6.1-terra", "low"),
    ("gemini", "gemini-3.8-flash", "high"),
)
REPLAY_CUTOFFS = (0.999, 0.995, 0.99, 0.985, 0.98, 0.97, 0.95, 0.9, 0.8)
REPLAY_SHARE = 0.25

# Reasoning by task (N3): each model at a lower and a higher reasoning setting, as the (provider, model, reasoning) of
# its setups' first runs, lower first. Units 1 to 6 test reading, as benchmark_ollama.py's READING_UNITS; the seed is
# the one the analysis fixed on 13 October.
REASONING_PAIRS = (
    (("claude", "claude-sonnet-5-5", "low"), ("claude", "claude-sonnet-5-5", "high")),
    (("vllm", "deepseek-v4.1-flash", "off"), ("vllm", "deepseek-v4.1-flash", "on")),
    (("gemini", "gemini-3.8-flash", "low"), ("gemini", "gemini-3.8-flash", "high")),
    (("vllm-stated", "glm-5.3-flash", "off"), ("vllm-stated", "glm-5.3-flash", "on")),
)
READING_UNITS = range(1, 7)
REASONING_SEED = 20261013


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="benchmark-results.md written by benchmark_ollama.py")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"default: {DEFAULT_OUTPUT}")
    parser.add_argument(
        "--answers",
        type=Path,
        required=True,
        help="the per-question file from benchmark_ollama.py --export-answers: the replays come from it, and it is "
        "written as answers.json next to --output with the exported runs only, ANSWER_FILES' sections in files of "
        "their own beside it",
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
    scoring = PROVIDERS[record.get("provider", "ollama")]["scoring"]
    return {
        "source": source,
        "label": SCORING_SOURCE if source == "probability" and scoring else CONFIDENCE_SOURCES[source],
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


# Runs of the same setup: provider, model and setting; a run's time per request may come from another run of its setup
# with the same number of questions per request.
SETUP_KEYS = ("provider", "model", "reasoning", "variant", "perplexity_mode")


def run_latency(run: dict[str, Any], repeats: list[dict[str, Any]], repeat_of: dict[int, int]) -> dict[str, Any] | None:
    """A run's time per request, median and 90th percentile: its own, or, for a run that predates per-request timing,
    the times pooled over the later runs of its setup: its repeats over the same questions, else its repeated runs on a
    fixed sample. None when no run of the setup was timed."""
    if run["median_request_seconds"] is not None:
        return {
            "source": "run",
            "runs": [run["run"]],
            "concurrency": run["concurrency"],
            "median_request_seconds": run["median_request_seconds"],
            "p90_request_seconds": run["p90_request_seconds"],
        }
    timed = [
        item
        for item in repeats
        if item["latency"]
        and item["questions_per_request"] == run["questions_per_request"]
        and all(item.get(key) == run.get(key) for key in SETUP_KEYS)
    ]
    own = [item for item in timed if run["run"] in item["runs"]]
    if len(own) > 1 or (not own and len(timed) > 1):
        raise ValueError(f"run {run['run']}: more than one set of repeated runs could give its time per request")
    if not timed:
        return None
    item = (own or timed)[0]
    latency = item["latency"]
    return {
        "source": "repeats" if own else "sample",
        "runs": latency["runs"],
        "repeats": [repeat_of[run_id] for run_id in latency["runs"]],
        "questions": item["questions"],
        "concurrency": latency["concurrency"],
        "median_request_seconds": latency["median_request_seconds"],
        "p90_request_seconds": latency["p90_request_seconds"],
    }


def single_question_latency(run: dict[str, Any], batching: list[dict[str, Any]]) -> dict[str, Any] | None:
    """For a batched run: the time per request of its setup's run with one question per request, where there is one."""
    found = [
        item
        for item in batching
        if item["batch_size"] == 1
        and item["compared_batch_size"] == run["questions_per_request"] != 1
        and item["median_request_seconds"] is not None
        and all(item.get(key) == run.get(key) for key in SETUP_KEYS)
    ]
    if len(found) > 1:
        raise ValueError(f"run {run['run']}: more than one run of its setup with one question per request")
    return {key: found[0][key] for key in ("run", "questions", "median_request_seconds", "p90_request_seconds")} if found else None



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
        and record["run_id"] not in HELD_RUNS
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
        return {
            "model": record["model"],
            "name": model_info(provider_name, record["model"], record.get("perplexity_mode")).get("name", record["model"]),
            "variant": run_variant(record),
            "reasoning": None if provider["scoring"] else record["thinking"],
            "provider": provider_name,
            "perplexity_mode": record.get("perplexity_mode"),
        }

    # The price of every priced run exported, by provider, model and Perplexity mode (the report's PRICES and
    # WEB_GROUNDING_PRICES).
    prices: dict[tuple[str, str, str | None], dict[str, Any]] = {}

    def priced(record: dict[str, Any]) -> dict[str, int]:
        """The record's token totals, with its price entered in the price table."""
        price = record.get("price")
        if price is not None:
            key = (record.get("provider", "ollama"), record["model"], record.get("perplexity_mode"))
            if prices.setdefault(key, price) != price:
                raise ValueError(f"run {record['run_id']}: its price differs from another run of {key[1]}")
        return {kind: record.get(kind, 0) for kind in TOKEN_KINDS}

    def per_thousand(record: dict[str, Any]) -> float | None:
        """A run's API cost per 1,000 questions asked, or None for a run without a price."""
        cost = record.get("cost_usd")
        return None if cost is None else 1000 * cost / record.get("as_run", {}).get("evaluated", record["evaluated"])

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
        model = model_info(provider_name, record["model"], record.get("perplexity_mode"))
        if record["model"] not in SIZES:
            raise ValueError(f"{label}: its model has no size record; add one to SIZES (its total, or None when the maker "
                             "discloses no size, with its sources and the date read; see the comment above SIZES)")
        billing = model.get("billing", provider["billing"])
        cost = record.get("cost_usd")
        if (cost is None) != (record.get("price") is None):
            raise ValueError(f"{label}: a cost needs its price, and a price its cost")
        if cost is None and billing != "local":
            raise ValueError(f"{label}: billed as {billing!r} without a price")
        applies = None if cost is None else record["price"].get("applies_to", "billed")
        if cost is not None and applies not in COST_BASES[billing]:
            raise ValueError(f"{label}: billed as {billing!r}, but its price applies to {applies!r}")
        cost_basis = None if cost is None else COST_BASES[billing][applies]
        if billing == "local" and "hardware" not in model:
            raise ValueError(f"{label}: runs on our GPUs; add its hardware to MODELS")
        if applies == "gpu" and not model["hardware"].startswith(f"{record['price']['gpus']} × "):
            raise ValueError(f"{label}: its GPU-time price counts {record['price']['gpus']} GPUs, its hardware {model['hardware']!r}")
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
                "note": " ".join(note for note in (model.get("note"), RUN_NOTES.get(record["run_id"])) if note) or None,
                **size_record(record["model"]),
                "provider": provider_name,
                "access": access_text(provider_name, model, record),
                "questions_per_request": record["batch_size"],
                "concurrency": record.get("concurrency", 1),
                "correct": record["correct"],
                "invalid": record["invalid"],
                # The rule on empty and broken chat replies (bus #3215), for the setups it applies to (the runner's
                # RESCUE_PROVIDERS; None for the others): answers read from broken replies, empty replies asked once
                # more, how many came back with answers and the answers they gave, the answers still invalid by kind,
                # and the invalid answers without the rule (the count before --rescue for a run rescued afterwards).
                "invalid_replies": record.get("invalid_replies"),
                "answered_questions": record.get("as_run", {}).get("evaluated", record["evaluated"]),
                "groups": groups,
                "tyt_mix": tyt_mix(groups),
                "questions_per_minute": record.get("questions_per_minute"),
                "request_seconds": record.get("timed_seconds"),
                "median_request_seconds": record.get("median_request_seconds"),
                "p90_request_seconds": record.get("p90_request_seconds"),
                "billing": billing,
                # The run's estimated cost at the price in `prices`: its tokens at the service's own list price, at the
                # list price of the model a free-tier run called, or for a local run at its maker's list price for the
                # same model or a public host's for the same weights; else a local run's request time x its GPUs at a
                # public GPU-hour price (request_seconds). cost_basis says which ("api", "subscription", "free tier",
                # "maker", "weights", "gpu"; None only for a local run without a request time); requests counts the
                # run's requests, for a price that bills tokens per request.
                "api_equivalent_usd": cost,
                "cost_basis": cost_basis,
                # An upper-bound estimate (upper_bound_cost): web grounding's search fee counted for every request.
                "cost_upper_bound": upper_bound_cost(record),
                "requests": record.get("requests"),
                "hardware": model.get("hardware") if billing == "local" else None,
                **priced(record),
                "confidence": confidence(record),
                "previous": previous,
                "units": [categories[name]["correct"] for name in unit_names],
                # When the run started and when its record last changed; the two are different dates.
                "started": record["started"],
                "updated": record["updated"],
            }
        )
    # A format rerun: a later main run of a setup (SETUP_KEYS) with another number of questions per request. It is a
    # setup of its own; format_of names its setup's first run, None for every other run.
    first_runs: dict[tuple[Any, ...], dict[str, Any]] = {}
    for run in sorted(runs, key=lambda run: run["run"]):
        base = first_runs.setdefault(tuple(run.get(key) for key in SETUP_KEYS), run)
        run["format_of"] = base["run"] if base["questions_per_request"] != run["questions_per_request"] else None
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
        first, frontier_cost = per_thousand(decision), per_thousand(frontier)
        cascades.append(
            {
                "decision": decision["run_id"],
                "frontier": frontier["run_id"],
                "frontier_accuracy": item["frontier_accuracy"],
                "in_sample": item["in_sample"],
                # [share answered by the decision model, cascade accuracy], highest threshold first.
                "curve": item.get("curve"),
                "held_out": item["held_out"],
                # API cost per 1,000 questions: the first model's, where it has a price, plus the frontier run's for
                # the held-out share passed on, as if every question cost the frontier run the same.
                "usd_per_1000": None
                if frontier_cost is None
                else (first or 0.0) + frontier_cost * (1 - item["held_out"]["answered"]),
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
        latency = item.get("latency")
        timed = [by_key[key] for key in latency["run_keys"]] if latency else []
        in_flight = {record.get("concurrency", 1) for record in timed}
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
                # Request times pooled over the runs that recorded them (median and 90th percentile).
                "latency": None
                if latency is None
                else {
                    "runs": [record["run_id"] for record in timed],
                    "concurrency": in_flight.pop() if len(in_flight) == 1 else None,
                    **{key: latency.get(key) for key in ("requests", "median_request_seconds", "p90_request_seconds")},
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
                **{key: item[key] for key in ("seed", "tolerance_points", "rule", "batch_size", "threshold", "held_out", "routed", "simulated")},
                # The rule "share" keeps the decision model's most confident share of the held-out questions.
                **({"share": item["share"]} if "share" in item else {}),
                "measured": None
                if measured is None
                else {
                    "pipeline_run": by_key[measured["pipeline_run"]]["run_id"],
                    "alone_run": by_key[measured["alone_run"]]["run_id"],
                    **{key: value for key, value in measured.items() if key not in ("pipeline_run", "alone_run", "alternatives")},
                    # The token totals behind cost_usd (with decision_cost_usd) and frontier_cost_usd.
                    "pipeline_tokens": priced(by_key[measured["pipeline_run"]]),
                    "alone_tokens": priced(by_key[measured["alone_run"]]),
                    # Other configurations run alone on the same held-out questions, for a matched cost.
                    "alternatives": [
                        {
                            **alternative,
                            "run": by_key[alternative["run"]]["run_id"],
                            **described(by_key[alternative["run"]]),
                            "tokens": priced(by_key[alternative["run"]]),
                        }
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
            **{key: by_key[item["run"]].get(key) for key in ("median_request_seconds", "p90_request_seconds")},
            "others": [
                {**other, "run": by_key[other["run"]]["run_id"], "repeat": by_key[other["run"]].get("repeat")}
                for other in item["others"]
            ],
        }
        for item in analysis.get("batching", [])
        if item["run"] in by_key and all(other["run"] in by_key for other in item["others"])
    ]
    # Each run's time per request, and for batched setups the time with one question per request where measured.
    repeat_of = {record["run_id"]: record.get("repeat") or 1 for record in by_key.values()}
    for run in runs:
        run["latency"] = run_latency(run, repeats, repeat_of)
        run["single_question_latency"] = single_question_latency(run, batching)
    reference = selected[0]
    suspect = None
    if "without_suspect" in reference["groups"]:
        suspect = reference["groups"]["all"]["questions"] - reference["groups"]["without_suspect"]["questions"]
    scored = next((record for record in selected if record.get("score_source")), None)
    return {
        "schema_version": SCHEMA_VERSION,
        # Set by main(): a hash of everything else in the file, so each published snapshot has its own version.
        "results_version": None,
        # Set by main(): when results with this content first went out (published_date).
        "updated": None,
        # The score at or above which an answer counts as very sure (the 0.99 threshold of the confidence tables).
        "sure_threshold": bm.SURE_SCORE,
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
        "prices": [{"provider": provider, "model": model, "perplexity_mode": mode, **price}
                   for (provider, model, mode), price in sorted(prices.items(), key=lambda item: (*item[0][:2], item[0][2] or ""))],
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


def baselines(answers: dict[str, Any], run_id: int) -> dict[str, Any]:
    """What answering without reading would score on the scored questions: guessing among the options at random (the
    options counted from one scoring run's option probabilities, which must give every question the same number), and
    always giving the letter the answer key uses most often."""
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    run = next(run for run in answers["runs"] if run["run"] == run_id)
    options = {len(run["probabilities"][index]) for index in scored if run["probabilities"][index]}
    if len(options) != 1:
        raise ValueError(f"run {run_id} gives questions different numbers of options: {sorted(options)}")
    letters = Counter(answers["questions"]["key"][index] for index in scored)
    letter, used = max(sorted(letters.items()), key=lambda item: item[1])
    return {"options": options.pop(), "letter": letter, "letter_share": used / len(scored)}


def holm_over_all_pairs(paired: list[dict[str, Any]], runs: list[dict[str, Any]], answers: dict[str, Any]) -> None:
    """Give each listed comparison its p-value with Holm's correction over every pair of main runs, the correction
    behind the leaderboard's comparison letters, so that the page can set the two corrections side by side."""
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    exported = {run["run"]: run for run in answers["runs"]}
    correct = {run["run"]: [int(bool(exported[run["run"]]["correct"][index])) for index in scored] for run in runs}
    pairs = list(itertools.combinations(sorted(correct), 2))
    adjusted = dict(zip(pairs, bm.holm([bm.paired_comparison(correct[first], correct[second])["p"] for first, second in pairs])))
    for item in paired:
        item["p_holm_all"] = adjusted[min(item["first"], item["second"]), max(item["first"], item["second"])]


def replay(runs: list[dict[str, Any]], answers: dict[str, Any]) -> dict[str, Any]:
    """The Decider v1.1 replay (results.json `replay`), from the exported answers (export_answers()) on the scored
    questions in question order with their passages as clusters, as the report's routing simulations take them: the
    decision run's answers kept at each cutoff, and its surest REPLAY_SHARE with the Wilson interval of their accuracy.
    For each second run: what keeping them changes at the sure threshold and with the share rule (bm.share_rule, on
    the same held-out halves as the cascades), and the pair's estimated cost per 1,000 questions as the cascades count
    it: the decision run on every question, the second run on the rest at its own average cost."""
    if bm.SURE_SCORE not in REPLAY_CUTOFFS:
        raise ValueError(f"REPLAY_CUTOFFS must include the sure threshold, {bm.SURE_SCORE}")

    def find(spec: tuple[str, str, str | None]) -> dict[str, Any]:
        found = [run for run in runs if (run["provider"], run["model"], run["reasoning"]) == spec and run.get("format_of") is None]
        if len(found) != 1:
            raise ValueError(f"replay: {len(found)} runs match {spec}")
        if found[0]["api_equivalent_usd"] is None:
            raise ValueError(f"replay: run {found[0]['run']} ({spec[1]}) has no cost")
        return found[0]

    questions = answers["questions"]
    order = sorted(
        (index for index, status in enumerate(questions["status"]) if status != "excluded"), key=lambda index: questions["id"][index]
    )
    clusters = [
        f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in order
    ]
    exported = {run["run"]: run for run in answers["runs"]}

    def outcomes(run: dict[str, Any]) -> tuple[list[int], list[float]]:
        answer = exported[run["run"]]
        return [int(bool(answer["correct"][index])) for index in order], [answer["score"][index] or 0.0 for index in order]

    def per_thousand(run: dict[str, Any]) -> float:
        return 1000 * run["api_equivalent_usd"] / run["answered_questions"]

    decision = find(REPLAY_DECISION)
    correct, scores = outcomes(decision)
    total, first_cost = len(order), per_thousand(decision)
    cut = bm.share_cut(scores, REPLAY_SHARE)
    surest = bm.kept_answers(scores, correct, cut)
    frontiers = []
    # Each second run's setup in its first format, then its format reruns, each a second run of its own; then the runs
    # added later.
    seconds = [find(spec) for spec in REPLAY_FRONTIERS]
    seconds += [run for base in seconds for run in sorted(runs, key=lambda run: run["run"]) if run.get("format_of") == base["run"]]
    seconds += [find(spec) for spec in REPLAY_FRONTIERS_ADDED]
    for frontier in seconds:
        if frontier["api_equivalent_usd"] is None:
            raise ValueError(f"replay: run {frontier['run']} ({frontier['model']}) has no cost")
        second, _ = outcomes(frontier)
        cost = per_thousand(frontier)
        sure = bm.handoff(scores, correct, second, bm.SURE_SCORE)
        rule = bm.share_rule(scores, correct, second, REPLAY_SHARE, clusters=clusters)
        del rule["cut"]
        frontiers.append(
            {
                "frontier": frontier["run"],
                "sure": {**sure, "usd_per_1000": first_cost + cost * (1 - sure["kept"] / total)},
                "share": {**rule, "usd_per_1000": first_cost + cost * (1 - rule["kept"] / total)},
            }
        )
    return {
        "decision": decision["run"],
        "questions": total,
        "cutoffs": [{"cutoff": cutoff, **bm.kept_answers(scores, correct, cutoff)} for cutoff in REPLAY_CUTOFFS],
        "share": {
            "share": REPLAY_SHARE,
            "cut": cut,
            **surest,
            "interval": bm.wilson_interval(surest["kept"] - surest["wrong"], surest["kept"]),
        },
        "frontiers": frontiers,
    }


def refit(runs: list[dict[str, Any]], answers: dict[str, Any]) -> None:
    """Give each run with a confidence score its calibration after refit (bm.refit_calibration, bm.REFIT_METHOD), from
    the exported answers: confidence.ece_refit, brier_refit, brier_base, refit_slopes, refit_questions and
    refit_converged. The folds come once from every scored question, each passage's questions one cluster and a
    question without a passage its own, and every run uses them; a run's questions without a score are left out, as
    in its calibration gap. Nothing else in results.json uses the refit."""
    questions = answers["questions"]
    scored = [index for index, status in enumerate(questions["status"]) if status != "excluded"]
    clusters = {
        index: f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in scored
    }
    fold_of = bm.refit_folds(clusters.values())
    exported = {run["run"]: run for run in answers["runs"]}
    for run in runs:
        if run["confidence"] is None:
            continue
        answer = exported[run["run"]]
        kept = [index for index in scored if answer["score"][index] is not None]
        result = bm.refit_calibration(
            [(float(answer["score"][index]), int(answer["correct"][index])) for index in kept],
            [fold_of[clusters[index]] for index in kept],
        )
        run["confidence"].update(
            ece_refit=result["ece_refit"],
            brier_refit=result["brier_refit"],
            brier_base=result["brier_base"],
            refit_slopes=result["slopes"],
            refit_questions=result["questions"],
            refit_converged=result["converged"],
        )


def formats(runs: list[dict[str, Any]], answers: dict[str, Any]) -> list[dict[str, Any]]:
    """Each format rerun against its setup's first run on the scored questions: the paired accuracy test (exact McNemar,
    bm.paired_comparison; first the rerun, second the first run), with Holm's correction over these comparisons."""
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    exported = {run["run"]: run for run in answers["runs"]}
    by_id = {run["run"]: run for run in runs}
    found = []
    for run in sorted((run for run in runs if run.get("format_of") is not None), key=lambda run: run["run"]):
        base = by_id[run["format_of"]]
        first = [int(bool(exported[run["run"]]["correct"][index])) for index in scored]
        second = [int(bool(exported[base["run"]]["correct"][index])) for index in scored]
        test = bm.paired_comparison(first, second)
        found.append({
            "run": run["run"],
            "base": base["run"],
            "questions_per_request": run["questions_per_request"],
            "base_questions_per_request": base["questions_per_request"],
            "correct": sum(first),
            "base_correct": sum(second),
            **{key: test[key] for key in ("questions", "first_only", "second_only", "difference", "low", "high", "p")},
        })
    for item, adjusted in zip(found, bm.holm([item["p"] for item in found])):
        item["p_holm"] = adjusted
    return found


def reasoning(runs: list[dict[str, Any]], answers: dict[str, Any]) -> dict[str, Any]:
    """N3: for each reasoning pair, the accuracy gain from the lower to the higher setting on reading and on grammar,
    and the 95% interval of the grammar gain minus the reading gain (bm.bootstrap_gain_difference), on the scored
    questions in question order with each passage's questions as one cluster, as the replay takes them. The export stops
    when READING_UNITS no longer gives the runs' reading questions."""
    questions = answers["questions"]
    order = sorted((index for index, status in enumerate(questions["status"]) if status != "excluded"),
                   key=lambda index: questions["id"][index])
    parts = ["reading" if questions["unit"][index] in READING_UNITS else "grammar" for index in order]
    clusters = [
        f"passage {questions['passage'][index]}" if questions["passage"][index] is not None else f"question {questions['id'][index]}"
        for index in order
    ]
    exported = {run["run"]: run for run in answers["runs"]}

    def find(spec: tuple[str, str, str]) -> dict[str, Any]:
        found = [run for run in runs if (run["provider"], run["model"], run["reasoning"]) == spec and run.get("format_of") is None]
        if len(found) != 1:
            raise ValueError(f"reasoning: {len(found)} runs match {spec}")
        return found[0]

    def outcomes(run: dict[str, Any]) -> list[int]:
        return [int(bool(exported[run["run"]]["correct"][index])) for index in order]

    pairs = []
    for low_spec, high_spec in REASONING_PAIRS:
        low, high = find(low_spec), find(high_spec)
        if parts.count("reading") != low["groups"]["reading"]["questions"]:
            raise ValueError("reasoning: READING_UNITS no longer gives the runs' reading questions")
        test = bm.bootstrap_gain_difference(outcomes(low), outcomes(high), parts, clusters, of="grammar", against="reading",
                                            seed=REASONING_SEED)
        pairs.append({
            "low": low["run"],
            "high": high["run"],
            "reading_gain": test["gains"]["reading"],
            "grammar_gain": test["gains"]["grammar"],
            "difference": test["difference"],
            "interval": test["interval"],
        })
    return {"reading_units": list(READING_UNITS), "seed": REASONING_SEED, "resamples": bm.BOOTSTRAP_RESAMPLES, "pairs": pairs}


def group_of(provider: str, model: str) -> str:
    """A setup's view bar group by page_config.json's rule (Site.decision): "decision" when its provider is one of
    decision_model_providers and its model not one of not_decision_models, else "chat"."""
    config = json.loads(PAGE_CONFIG_PATH.read_text(encoding="utf-8"))
    decision = provider in config["decision_model_providers"] and model not in config["not_decision_models"]
    return "decision" if decision else "chat"


def running_reason() -> str:
    """The reason shown for a side of a chat model's "I don't know" comparison whose run is still running
    (page_config.json's dont_know.running)."""
    return json.loads(PAGE_CONFIG_PATH.read_text(encoding="utf-8"))["dont_know"]["running"]


def setup_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """A run record's setup: provider, model, reasoning, questions per request and Perplexity mode."""
    return (record.get("provider", "ollama"), record["model"], record["thinking"], record["batch_size"], record.get("perplexity_mode"))


def dont_know(records: list[dict[str, Any]], data: dict[str, Any], by_record: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """The Hallucination tab (results.json `dont_know`) from the report's records of runs with the "I don't know" option
    (`dont_know_answers`), on the exported bank's full question set: one entry per setup (provider, model, reasoning,
    questions per request), from its first full run, with the range over all its full runs, and its view bar group
    (group_of). A decision model's original run (its first full run without the option) must be its model's run on
    the Text tab, or an earlier run of the same setup (by_record: every record of the report, by run), which the
    Text tab run then replaces; a chat model's Text tab run is the one of the same provider, model, reasoning,
    questions per request and Perplexity mode (its runner-named original run can be an earlier run). Where the
    original was replaced, and for every chat model, the derived abstention is computed on the Text tab run from the
    answers (dont_know_answers_part). None without such runs. The prompt texts and answers_changed come from the
    answers (dont_know_answers_part)."""
    graded = data["dataset"]["graded_sha256"] or data["dataset"]["sha256"]
    full = [
        record
        for record in records
        if record["evaluated"] == record["eligible_total"] == data["questions"]
        and record.get("replace_key_text") is None
        and not record.get("question_list")
        and record["run_id"] not in HELD_RUNS
        and (record.get("graded_sha256") or record["dataset_sha256"]) == graded
    ]
    if not full:
        return None
    setups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in sorted(full, key=lambda record: record["run_id"]):
        key = setup_key(record)
        setups.setdefault(key, []).append(record)
    by_id = {run["run"]: run for run in data["runs"]}
    metrics = ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability")
    models = []
    for (provider, model, thinking, batch_size, mode), found in setups.items():
        label = f"{model} ({provider}), \"I don't know\" runs {[record['run_id'] for record in found]}"
        group = group_of(provider, model)
        first = [record for record in found if record.get("repeat") is None]
        if len(first) != 1:
            raise ValueError(f"{label}: needs exactly one full run without a repeat number")
        found.sort(key=lambda record: (record.get("repeat") is not None, record["run_id"]))
        values = []
        for record in found:
            got = record["dont_know_answers"]
            if got["questions"] != data["questions"] or sum(got[key] for key in ("right", "wrong", "dont_know", "invalid")) != got["questions"]:
                raise ValueError(f"{label}: run {record['run_id']} does not count {data['questions']} questions")
            values.append({**got, "mean_dont_know_probability": got["mean_option_probability"]})
        head = values[0]
        original = head["original_run"]
        if any(value["original_run"] != original for value in values):
            raise ValueError(f"{label}: its runs name different original runs")
        if group == "chat":
            # A scoring provider's Text tab run has no reasoning setting (export), whatever its record's thinking.
            reasoning = None if PROVIDERS[provider]["scoring"] else thinking
            text = [run["run"] for run in data["runs"] if (run["provider"], run["model"], run["reasoning"], run["questions_per_request"],
                                                           run["perplexity_mode"]) == (provider, model, reasoning, batch_size, mode)]
            if len(text) != 1:
                raise ValueError(f"{label}: needs exactly one Text tab run of the same setup, found {text}")
            original, derived = text[0], None
        else:
            primary = min(
                (run["run"] for run in data["runs"]
                 if (run["provider"], run["model"], run["questions_per_request"], run["perplexity_mode"]) == (provider, model, batch_size, mode)),
                default=None,
            )
            derived = head["derived"]
            if original is not None and primary is not None and original != primary:
                # The runner can name an earlier run of the same setup as the original (Laya's 730 names 41, not 51);
                # then the setup's Text tab run is the original and its derived abstention comes from that run's
                # answers (dont_know_answers_part), as for a chat model.
                earlier = by_record.get(original)
                if earlier is None or setup_key(earlier) != (provider, model, thinking, batch_size, mode):
                    raise ValueError(f"{label}: its original run {original} is not a run of its setup in the report")
                original, derived = primary, None
            if original is None or original != primary:
                raise ValueError(f"{label}: its original run {original} is not the model's run on the Text tab ({primary})")
            if derived is None and head["original_run"] == original:
                raise ValueError(f"{label}: no derived abstention")
        models.append(
            {
                "name": by_id[original]["name"],
                "model": model,
                "provider": provider,
                "perplexity_mode": mode,
                "group": group,
                "run": found[0]["run_id"],
                "runs": [record["run_id"] for record in found],
                **{key: head[key] for key in ("right", "wrong", "dont_know", "invalid")},
                # The rule on empty and broken chat replies in its first run, as for a Text tab run (`runs[].invalid_replies`).
                "invalid_replies": found[0].get("invalid_replies"),
                **{key: head[key] for key in metrics},
                "spread": None
                if len(values) == 1
                else {
                    key: None
                    if any(value[key] is None for value in values)
                    else [min(value[key] for value in values), max(value[key] for value in values)]
                    for key in metrics
                },
                "answers_changed": None,
                "original_run": original,
                "original_accuracy": by_id[original]["correct"] / data["questions"],
                # A chat model's derived abstention, and a decision model's whose runner named an earlier original
                # run, come from the answers (dont_know_answers_part).
                "derived": None if derived is None else {
                    key: derived[key] for key in ("cut_off", "attempt_rate", "non_hallucination", "right", "wrong", "abstained")
                },
            }
        )
    models.sort(key=lambda item: (-item["accuracy"], item["name"].casefold(), item["run"]))
    return {"questions": data["questions"], "models": models}


# The "I don't know" option's letter: it follows each question's five options (DONT_KNOW_OPTION in benchmark_ollama.py).
DONT_KNOW_LETTER = "F"
# The share of the scored questions on which a model must choose the option for its comparison with confidence to count
# in the Holm family: below it a model chose the option too seldom for the comparison to say anything.
VS_CONFIDENCE_SHARE = 0.01


def hashed_prompts(prompts: dict[str, Any]) -> str:
    """A prompts dict's version, hashed as the runner hashes it (sorted keys, compact)."""
    return hashlib.sha256(json.dumps(prompts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


# The chat prompts' instructions, each of which a chat model's run with the "I don't know" option ends with the option's
# sentence (dont_know_chat in benchmark_ollama.py); its system prompts stay those of the five-option runs.
CHAT_INSTRUCTIONS = ("answer_instruction", "confidence_instruction", "verbal_instruction")
CHAT_SYSTEMS = ("answer_system", "confidence_system", "verbal_system")


def chat_dont_know_prompts(prompts: dict[str, Any] | None, base: dict[str, Any], option: str, name: str) -> dict[str, Any]:
    """The chat models' prompts with the "I don't know" option (dont_know_chat_prompts or english_dont_know_chat_prompts,
    `name`), checked against the five-option chat prompts `base`: the option is `option`, each instruction is the base
    one plus the prompts' own sentence, each system prompt the base one. Returns the published part: the sentence, the
    confidence system prompt and instruction (the chat models' prompts the site quotes) and the version."""
    if prompts is None:
        raise ValueError(f"the answers file has chat models' \"I don't know\" runs but no {name}")
    sentence = prompts["dont_know_sentence"]
    if prompts["dont_know_option"] != option:
        raise ValueError(f"{name}: the option is {prompts['dont_know_option']!r}, not {option!r}")
    for field in CHAT_INSTRUCTIONS:
        if prompts[field] != f"{base[field]} {sentence}":
            raise ValueError(f"{name}: {field} is not the five-option chat prompts' plus {sentence!r}")
    for field in CHAT_SYSTEMS:
        if prompts[field] != base[field]:
            raise ValueError(f"{name}: {field} is not the five-option chat prompts'")
    return {"sentence": sentence, "confidence_system": prompts["confidence_system"],
            "confidence_instruction": prompts["confidence_instruction"], "prompt_version": hashed_prompts(prompts)}


def dont_know_answers_part(section: dict[str, Any], document: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """The `dont_know` section with what comes from the answers file: the option, the decision models' instructions with
    their added sentence and the prompt version (DONT_KNOW_PROMPTS, hashed as the runner hashes them), the chat models'
    prompts with theirs (`chat`, chat_dont_know_prompts; omitted without a chat model's run); every run must carry its
    kind's version, decision for a scoring provider and chat for any other. Per setup with more than one run the scored
    questions whose answer differs across its runs; per chat model the derived abstention on its Text tab run at its
    first run's attempt rate, on the scored questions; and per decision model `vs_confidence`: its first run against
    its original run held back by its own confidence at the derived cut-off, on the scored questions, as wrong answers
    in each (the exact McNemar test, bm.paired_comparison: first the option, second confidence), with Holm's correction
    over the decision models that chose the option on at least VS_CONFIDENCE_SHARE of the questions (p_holm None for
    the others; vs_confidence None for a chat model)."""
    prompts = document.get("dont_know_prompts")
    if prompts is None:
        raise ValueError('the answers file has "I don\'t know" runs but no dont_know_prompts')
    option, instructions = prompts["dont_know_option"], prompts["system_one_instructions"]
    sentence = f"If you do not know the answer, choose {option}."
    if instructions != f"{document['prompts']['system_one_instructions']} {sentence}":
        raise ValueError(f"dont_know_prompts: the instructions are not the System One instructions plus {sentence!r}")
    version = hashed_prompts(prompts)
    by_id = {run["run"]: run for run in answers["dont_know_runs"]}
    chat = None
    if any(not PROVIDERS[run["provider"]]["scoring"] for run in by_id.values()):
        chat = chat_dont_know_prompts(document.get("dont_know_chat_prompts"), document["prompts"], option, "dont_know_chat_prompts")
    wrong = sorted(run for run, item in by_id.items()
                   if item["prompt_version"] != (version if PROVIDERS[item["provider"]]["scoring"] else chat["prompt_version"]))
    if wrong:
        raise ValueError(f"\"I don't know\" runs {wrong} were not run with their kind's prompt version")
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    for model in section["models"]:
        if len(model["runs"]) > 1:
            choices = [by_id[run]["choice"] for run in model["runs"]]
            answered = [index for index in scored if all(choice[index] is not None for choice in choices)]
            model["answers_changed"] = sum(1 for index in answered if len({choice[index] for choice in choices}) > 1)
    main = {run["run"]: run for run in answers["runs"]}
    family = []
    for model in section["models"]:
        run, original = by_id[model["runs"][0]], main[model["original_run"]]
        if model["group"] == "chat" or model["derived"] is None:
            pairs = [(None if original["score"][index] is None else float(original["score"][index]), int(original["correct"][index]))
                     for index in scored]
            model["derived"] = derived_abstention(pairs, model["attempt_rate"])
        if model["group"] == "chat":
            model["vs_confidence"] = None
            continue
        cut_off = model["derived"]["cut_off"]
        option_wrong = [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index]) for index in scored]
        confidence_wrong = [int(cut_off is not None and original["score"][index] is not None and float(original["score"][index]) >= cut_off
                                and not original["correct"][index]) for index in scored]
        if sum(option_wrong) != model["wrong"] or sum(confidence_wrong) != model["derived"]["wrong"]:
            raise ValueError(f"{model['name']}: its answers do not give its wrong answers with the option or held back by confidence")
        test = bm.paired_comparison(option_wrong, confidence_wrong)
        model["vs_confidence"] = {"option_only_wrong": test["first_only"], "confidence_only_wrong": test["second_only"], "p": test["p"], "p_holm": None}
        if model["dont_know"] >= VS_CONFIDENCE_SHARE * len(scored):
            family.append(model)
    for model, adjusted in zip(family, bm.holm([model["vs_confidence"]["p"] for model in family])):
        model["vs_confidence"]["p_holm"] = adjusted
    return {
        "option": option,
        "option_en": "I don't know",
        "sentence": sentence,
        "instructions": instructions,
        "prompt_version": version,
        **({"chat": chat} if chat else {}),
        "vs_confidence_share": VS_CONFIDENCE_SHARE,
        **section,
    }


# The option-word check (results.json `dont_know_option_word`): the Hallucination tab's test with the option's word in
# English, its prompts' version (DONT_KNOW_WORD_PROMPT_VERSION in benchmark_ollama.py), and the Hallucination tab models
# without an option-word run by (provider, model, Perplexity mode), with the reason the page gives.
OPTION_WORD = "I don't know"
OPTION_WORD_PROMPT_VERSION = "fb17d583a3af"
# The reason of the decision models on our GPUs added to the Hallucination tab after the option-word check.
OPTION_WORD_GPU_LATER = ("added to the Hallucination tab on 5 November 2026 with the runs on our GPUs, after the option-word "
                         "check; not asked with “I don't know” yet.")
OPTION_WORD_NOT_RUN: dict[tuple[str, str, str | None], str] = {
    ("perplexity", "pplx-decider-v1.2", None): "added to the Hallucination tab on 5 November 2026 (Ümit #1229), after the "
    "option-word check; not asked with “I don't know” yet.",
    ("perplexity", "pplx-decider-v1.2", "web_grounding"): "added to the Hallucination tab on 5 November 2026 (Ümit #1229), "
    "after the option-word check; not asked with “I don't know” yet.",
    **{(provider, model, None): OPTION_WORD_GPU_LATER for provider, model in (
        ("clef", "clef-flash"), ("cygnet", "cygnet"), ("gliner", "gliner2.5-multi-decide"), ("laya", "laya"),
        ("laya", "laya-multilingual"), ("d1-server", "LiquidAI/d1-2B"), ("metask", "metask-jev-4b-policy-mix"),
        ("strands", "strands-decider-2b"), ("winnow", "winnow-12b"), ("clef", "clef"), ("onejev", "OmniJev/OneJev-27B"),
        ("open-jev", "open-jev-27b-v1.1"), ("pplx-decider", "pplx-decider-flash-v1.2"))},
    ("reax", "reax13", None): "added to the Hallucination tab on 6 November 2026 (run on our GPU), after the option-word "
    "check; not asked with “I don't know” yet.",
}
# The hosted GLiDE rerun (results.json `hosted_glide_rerun`): Fastino changed the hosted model after 6 October, so a new
# five-option run with the main prompts' version replaces RERUN_REPLACES as the original run of the model's "I don't
# know" comparison; the published row stays as it is.
RERUN_REPLACES = 129
RERUN_PROMPT_VERSION = "254597b8be16"


def full_bank_run(record: dict[str, Any], data: dict[str, Any]) -> bool:
    """Whether a run was asked every question of the exported bank as it stands, with the options as published."""
    return (record["evaluated"] == record["eligible_total"] == data["questions"]
            and (record.get("graded_sha256") or record["dataset_sha256"]) == (data["dataset"]["graded_sha256"] or data["dataset"]["sha256"])
            and record.get("replace_key_text") is None and record.get("shuffle_options") is None
            and not record.get("question_list") and record.get("repeat") is None and not record.get("english"))


def setup_of(record: dict[str, Any]) -> tuple[Any, ...]:
    return record.get("provider", "ollama"), record["model"], record["thinking"], record["batch_size"], record.get("perplexity_mode")


def dont_know_option_word(records: list[dict[str, Any]], section: dict[str, Any] | None, data: dict[str, Any],
                          by_run: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """The option-word check (results.json `dont_know_option_word`) from the report's records of its runs
    (dont_know_word "english"): for each decision model of the Hallucination tab, in the `dont_know` section's order, its first run
    with "Bilmiyorum" and its one full-bank run of the same setup with "I don't know"; a model without such a run must
    be in OPTION_WORD_NOT_RUN. None without option-word runs. The prompts, prompt versions and the paired test come from
    the answers (dont_know_option_word_answers_part)."""
    records = [record for record in records if record["run_id"] not in HELD_RUNS]
    if not records:
        return None
    if section is None:
        raise ValueError(f"option-word runs {[record['run_id'] for record in records]}: no Hallucination tab runs to compare them with")
    by_setup: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in sorted(records, key=lambda record: record["run_id"]):
        label = f"option-word run {record['run_id']} ({record['model']}, {record.get('provider', 'ollama')})"
        if record.get("dont_know_word") != "english" or not record.get("dont_know") or record.get("rerun") is not None:
            raise ValueError(f"{label}: not a run with the \"I don't know\" option in Turkish (dont_know_word {record.get('dont_know_word')!r})")
        if not full_bank_run(record, data) or record["dont_know_answers"]["questions"] != data["questions"]:
            raise ValueError(f"{label}: not a run over all {data['questions']:,} questions of the exported bank")
        by_setup.setdefault(setup_of(record), []).append(record)
    for (provider, model, mode), _ in OPTION_WORD_NOT_RUN.items():
        if not any((item["provider"], item["model"], item["perplexity_mode"]) == (provider, model, mode) for item in section["models"]):
            raise ValueError(f"OPTION_WORD_NOT_RUN: {model} ({provider}, {mode}) is not a Hallucination tab model")

    def counted(record: dict[str, Any]) -> dict[str, Any]:
        got = record["dont_know_answers"]
        if sum(got[key] for key in ("right", "wrong", "dont_know", "invalid")) != data["questions"]:
            raise ValueError(f"run {record['run_id']}: its answers do not add up to {data['questions']:,} questions")
        return {
            "run": record["run_id"],
            "date": record["started"][:10],
            "prompt_version": None,
            **{key: got[key] for key in ("right", "wrong", "dont_know", "invalid", "accuracy", "attempt_rate", "non_hallucination")},
            "mean_dont_know_probability": got["mean_option_probability"],
        }

    models, not_run = [], []
    for item in (item for item in section["models"] if item["group"] == "decision"):
        found = by_setup.pop(setup_of(by_run[item["run"]]), [])
        reason = OPTION_WORD_NOT_RUN.get((item["provider"], item["model"], item["perplexity_mode"]))
        label = f"{item['name']} ({item['provider']})"
        if reason is not None:
            if found:
                raise ValueError(f"{label}: in OPTION_WORD_NOT_RUN but has option-word runs {[record['run_id'] for record in found]}")
            not_run.append({"name": item["name"], "reason": reason})
            continue
        if len(found) != 1:
            raise ValueError(f"{label}: needs exactly one option-word run of its Hallucination tab setup (run {item['run']}), "
                             f"found {[record['run_id'] for record in found]}; a model that could not run goes in OPTION_WORD_NOT_RUN")
        if found[0]["dont_know_answers"]["original_run"] != item["original_run"]:
            raise ValueError(f"{label}: option-word run {found[0]['run_id']} names original run "
                             f"{found[0]['dont_know_answers']['original_run']}, its Hallucination tab run {item['original_run']}")
        models.append({"name": item["name"], "model": item["model"], "provider": item["provider"],
                       "bilmiyorum": counted(by_run[item["run"]]), "i_dont_know": counted(found[0]), "paired": None})
    if by_setup:
        raise ValueError(f"option-word runs {[record['run_id'] for found in by_setup.values() for record in found]}: no "
                         f"Hallucination tab model of the same setup")
    return {"questions": data["questions"], "models": models, "not_run": not_run}


def dont_know_option_word_answers_part(section: dict[str, Any], document: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """The `dont_know_option_word` section with what comes from the answers file: the option, its sentence, the
    instructions (the System One instructions plus the sentence) and the prompt version (dont_know_word_prompts, hashed
    as the runner hashes them, which must be OPTION_WORD_PROMPT_VERSION and every option-word run's version), each run's
    prompt version, and per model the paired test of wrong answers on the scored questions (exact McNemar,
    bm.paired_comparison: first "Bilmiyorum", second "I don't know") with Holm's correction over the models compared."""
    prompts = document.get("dont_know_word_prompts")
    if prompts is None:
        raise ValueError("the answers file has option-word runs but no dont_know_word_prompts")
    option, instructions = prompts["dont_know_option"], prompts["system_one_instructions"]
    sentence = f"If you do not know the answer, choose {option}."
    if option != OPTION_WORD or instructions != f"{document['prompts']['system_one_instructions']} {sentence}":
        raise ValueError(f"dont_know_word_prompts: the option is not {OPTION_WORD!r} or the instructions are not the System One "
                         f"instructions plus {sentence!r}")
    version = hashlib.sha256(
        json.dumps(prompts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    if version != OPTION_WORD_PROMPT_VERSION:
        raise ValueError(f"dont_know_word_prompts hash to {version}, not {OPTION_WORD_PROMPT_VERSION}")
    words = {run["run"]: run for run in answers["dont_know_word_runs"]}
    turkish = {run["run"]: run for run in answers["dont_know_runs"]}
    wrong_version = sorted(run for run, item in words.items() if item["prompt_version"] != version)
    if wrong_version:
        raise ValueError(f"option-word runs {wrong_version} were not run with prompt version {version}")
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]

    def wrong(run: dict[str, Any], published: dict[str, Any]) -> list[int]:
        found = [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index]) for index in scored]
        if sum(found) != published["wrong"]:
            raise ValueError(f"run {run['run']}: its answers give {sum(found)} wrong answers, its record {published['wrong']}")
        return found

    for model in section["models"]:
        first, second = turkish[model["bilmiyorum"]["run"]], words[model["i_dont_know"]["run"]]
        model["bilmiyorum"]["prompt_version"] = first["prompt_version"]
        model["i_dont_know"]["prompt_version"] = second["prompt_version"]
        test = bm.paired_comparison(wrong(first, model["bilmiyorum"]), wrong(second, model["i_dont_know"]))
        model["paired"] = {"bilmiyorum_only_wrong": test["first_only"], "i_dont_know_only_wrong": test["second_only"],
                           "p": test["p"], "p_holm": None}
    for model, adjusted in zip(section["models"], bm.holm([model["paired"]["p"] for model in section["models"]])):
        model["paired"]["p_holm"] = adjusted
    return {"option": option, "sentence": sentence, "instructions": instructions, "prompt_version": version, **section}


def derived_abstention(answers: list[tuple[float | None, int]], target: float) -> dict[str, Any]:
    """derived_abstention in benchmark_ollama.py: answer only where the score reaches the cut-off whose attempt rate
    (answers at or above it, over all) comes nearest `target`, the higher cut-off on a tie, and abstain on the rest; an
    answer without a score is never an attempt. `answers` holds each question's (score, correct)."""
    total = len(answers)
    ranked = sorted(((score, correct) for score, correct in answers if score is not None), key=lambda item: -item[0])
    best: tuple[float, float | None, int, int] = (target, None, 0, 0)
    attempts = right = 0
    for index, (score, correct) in enumerate(ranked):
        attempts += 1
        right += correct
        if index + 1 < len(ranked) and ranked[index + 1][0] == score:
            continue
        distance = abs(attempts / total - target)
        if distance < best[0]:
            best = (distance, score, attempts, right)
    _, cut_off, attempts, right = best
    wrong, abstained = attempts - right, total - attempts
    return {
        "cut_off": cut_off,
        "attempt_rate": attempts / total,
        "non_hallucination": abstained / (abstained + wrong) if abstained + wrong else None,
        "right": right,
        "wrong": wrong,
        "abstained": abstained,
    }


def hosted_glide_rerun(records: list[dict[str, Any]], section: dict[str, Any] | None, data: dict[str, Any],
                       by_run: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """The hosted GLiDE rerun (results.json `hosted_glide_rerun`) from the report's records of fresh runs (rerun set):
    one full-bank five-option run of run RERUN_REPLACES's setup (provider, model, reasoning, questions per request),
    whose model's Hallucination tab row names RERUN_REPLACES as its original run. None without fresh runs. The prompt
    version, the derived abstention and the comparison with confidence come from the answers (hosted_glide_rerun_answers_part)."""
    records = [record for record in records if record["run_id"] not in HELD_RUNS]
    if not records:
        return None
    if len(records) != 1:
        raise ValueError(f"fresh runs {[record['run_id'] for record in records]}: the export takes one, the hosted GLiDE rerun")
    record = records[0]
    label = f"fresh run {record['run_id']} ({record['model']}, {record.get('provider', 'ollama')})"
    if record.get("dont_know") or record.get("dont_know_word") or not full_bank_run(record, data):
        raise ValueError(f"{label}: not a five-option run over all {data['questions']:,} questions of the exported bank")
    replaced = by_run.get(RERUN_REPLACES)
    if replaced is None or setup_of(record) != setup_of(replaced):
        raise ValueError(f"{label}: its setup {setup_of(record)} is not run {RERUN_REPLACES}'s "
                         f"{None if replaced is None else setup_of(replaced)}")
    if RERUN_REPLACES not in {run["run"] for run in data["runs"]}:
        raise ValueError(f"{label}: run {RERUN_REPLACES} is not on the Text tab")
    rows = [item for item in (section or {}).get("models", []) if item["original_run"] == RERUN_REPLACES]
    if len(rows) != 1 or (rows[0]["provider"], rows[0]["model"]) != setup_of(record)[:2]:
        raise ValueError(f"{label}: needs one Hallucination tab row of its model with original run {RERUN_REPLACES}, "
                         f"found {[item['run'] for item in rows]}")
    right, invalid = record["correct"], record["invalid"]
    return {
        "run": record["run_id"],
        "rerun": record["rerun"],
        "date": record["started"][:10],
        "prompt_version": None,
        "replaces_run": RERUN_REPLACES,
        "accuracy": right / data["questions"],
        "right": right,
        "wrong": data["questions"] - right - invalid,
        "invalid": invalid,
        "dont_know_run": rows[0]["run"],
        "derived": None,
        "vs_confidence": None,
    }


def hosted_glide_rerun_answers_part(rerun: dict[str, Any], dont_know_section: dict[str, Any], document: dict[str, Any],
                                    answers: dict[str, Any]) -> dict[str, Any]:
    """The `hosted_glide_rerun` section with what comes from the answers file: the run's prompt version (the main
    prompts hashed, RERUN_PROMPT_VERSION), and as dont_know_answers_part computes them for the published row with the
    rerun as the original run: the derived abstention at the "I don't know" run's attempt rate, on the scored questions,
    and `vs_confidence`, the "I don't know" run against the rerun held back by its own confidence at that cut-off, as
    wrong answers in each (exact McNemar, bm.paired_comparison: first the option, second confidence). The derived
    abstention is first recomputed for the published row from run RERUN_REPLACES and must match the report's."""
    version = hashlib.sha256(
        json.dumps(document["prompts"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    new = next(run for run in answers["rerun_runs"] if run["run"] == rerun["run"])
    if not version == new["prompt_version"] == RERUN_PROMPT_VERSION:
        raise ValueError(f"rerun {rerun['run']}: prompt version {new['prompt_version']}, the main prompts' {version}, "
                         f"expected {RERUN_PROMPT_VERSION}")
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    if sum(int(new["correct"][index]) for index in scored) != rerun["right"]:
        raise ValueError(f"rerun {rerun['run']}: its answers do not give its {rerun['right']} right answers")
    row = next(model for model in dont_know_section["models"] if model["run"] == rerun["dont_know_run"])
    option_run = next(run for run in answers["dont_know_runs"] if run["run"] == row["run"])
    replaced = next(run for run in answers["runs"] if run["run"] == RERUN_REPLACES)

    def derived(run: dict[str, Any]) -> dict[str, Any]:
        return derived_abstention(
            [(None if run["score"][index] is None else float(run["score"][index]), int(run["correct"][index])) for index in scored],
            row["attempt_rate"],
        )

    if derived(replaced) != row["derived"]:
        raise ValueError(f"{row['name']}: the derived abstention recomputed from run {RERUN_REPLACES} {derived(replaced)} is not "
                         f"the published {row['derived']}")
    found = derived(new)
    cut_off = found["cut_off"]
    option_wrong = [int(option_run["choice"][index] not in (None, DONT_KNOW_LETTER) and not option_run["correct"][index]) for index in scored]
    confidence_wrong = [int(cut_off is not None and new["score"][index] is not None and float(new["score"][index]) >= cut_off
                            and not new["correct"][index]) for index in scored]
    if sum(option_wrong) != row["wrong"] or sum(confidence_wrong) != found["wrong"]:
        raise ValueError(f"rerun {rerun['run']}: the answers do not give the wrong answers with the option or held back by confidence")
    test = bm.paired_comparison(option_wrong, confidence_wrong)
    return {
        **rerun,
        "prompt_version": version,
        "derived": found,
        "vs_confidence": {"option_only_wrong": test["first_only"], "confidence_only_wrong": test["second_only"], "p": test["p"]},
    }


# Perplexity's web grounding test (results.json `web_grounding`; Ümit #1138, #1204, #1219, #1229, 5 November 2026): the
# hosted Decider v1.2 (WEB_GROUNDING_SETUP) through Perplexity's Decisions API, one question per request, with grounding
# off and on. Since #1229 both modes are setups of the ranking: their Text tab runs (the full bank), English runs (the
# kept reading questions) and Hallucination tab runs ("Bilmiyorum", the full bank) are each pair's two arms, found by
# setup. The pilot pairs on the bank's 200-question sample (the runner's --sample 200 --seed 0), on which the protocol's
# rule was decided, are by run (WEB_GROUNDING_PILOTS) and enter no other section (WEB_GROUNDING_ONLY). The full bank's
# and the English pair's first runs have repeats (Ümit #1394-#1396, #1399: --repeat 2 and 3, the same questions in the
# same order, key, runner and settings): they enter only this section, as each pair's per-run results and the mean of
# its runs, and the ranking keeps each setup's first run. web-grounding.json (web_grounding_inputs.py) holds what
# answers.json cannot: each run's input tokens by group, what the search returned, and PWS-Decisions' aggregates.
WEB_GROUNDING_SETUP = ("perplexity", "pplx-decider-v1.2")
WEB_GROUNDING_MODE = "web_grounding"
WEB_GROUNDING_PILOTS = {"pilot": (631, 632), "pilot_dont_know": (634, 635)}
WEB_GROUNDING_ONLY = frozenset(run for pair in WEB_GROUNDING_PILOTS.values() for run in pair)
WEB_GROUNDING_SAMPLE = {"questions": 200, "seed": 0}
# The repeat numbers of the full bank's and the English pair's first runs (the first run is repeat 1).
WEB_GROUNDING_REPEATS = (2, 3)
WEB_GROUNDING_PATH = Path(__file__).resolve().parent / "web-grounding.json"
# Request times: the median and this percentile by nearest rank, as PWS-Decisions' summaries give it.
WEB_GROUNDING_PERCENTILE = 0.95
# What Perplexity published about PWS-Decisions (its blog post of 4 November 2026, read 5 November 2026).
WEB_GROUNDING_REPORTED = {
    "source": "https://www.perplexity.ai/hub/blog/web-grounding-for-the-decisions-api",
    "title": "Web grounding for the Decisions API",
    "published": "2026-11-04",
    "read": "2026-11-05",
    # 86 of the 100 public questions with grounding, Perplexity's run of 4 November 2026.
    "on_correct": 86,
    # 51 without: the benchmark authors' (Parallel's) leaderboard figure, which Perplexity says its own run matched.
    "off_correct": 51,
    # Grounded requests only, from Perplexity's client on the 100 public questions; no time is given without grounding.
    "on_median_request_seconds": 0.370,
    "on_p95_request_seconds": 0.685,
}


def nearest_rank(values: list[float], share: float) -> float:
    """The `share` percentile of `values` by nearest rank."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def web_grounding_repeat(record: dict[str, Any]) -> bool:
    """Whether a run is a repeat of one of the web grounding test's first runs: the test's setup with a repeat number,
    without the "Bilmiyorum" option."""
    return ((record.get("provider", "ollama"), record["model"]) == WEB_GROUNDING_SETUP and record.get("repeat") is not None
            and not record.get("dont_know"))


def web_grounding_runs(by_run: dict[int, dict[str, Any]]) -> frozenset[int]:
    """The web grounding test's own runs, which answers.json lists under `web_grounding_runs`: the pilots and the
    repeats (web_grounding_repeat), after checking each is in the report with its setup and kind; none when the report
    holds none of them."""
    repeats = frozenset(run for run, record in by_run.items() if web_grounding_repeat(record))
    if not (WEB_GROUNDING_ONLY | repeats) & set(by_run):
        return frozenset()
    if WEB_GROUNDING_ONLY - set(by_run):
        raise ValueError(f"web_grounding: the report lacks runs {sorted(WEB_GROUNDING_ONLY - set(by_run))}")
    for run in sorted(repeats):
        record = by_run[run]
        kind = [record["batch_size"], record["repeat"] in WEB_GROUNDING_REPEATS] + [record.get(key) for key in (
            "replace_key_text", "shuffle_options", "dont_know_word", "rerun")]
        if kind != [1, True, None, None, None, None]:
            raise ValueError(f"web_grounding: repeat run {run}: one question per request, repeat in {WEB_GROUNDING_REPEATS}, "
                             f"no key change, shuffle, option word or rerun expected, found {kind}")
    for part, pair in WEB_GROUNDING_PILOTS.items():
        for arm, run in zip(("off", "on"), pair):
            record = by_run[run]
            kind = {
                "setup": (record.get("provider", "ollama"), record["model"]),
                "one question per request": record["batch_size"],
                "grounding": record.get("perplexity_mode"),
                "Bilmiyorum": bool(record.get("dont_know")),
                "English": bool(record.get("english")),
                "repeat, key change, shuffle, option word, rerun, question list": [record.get(key) for key in (
                    "repeat", "replace_key_text", "shuffle_options", "dont_know_word", "rerun", "question_list")],
                "sample": record["evaluated"],
            }
            expected = {
                "setup": WEB_GROUNDING_SETUP,
                "one question per request": 1,
                "grounding": WEB_GROUNDING_MODE if arm == "on" else None,
                "Bilmiyorum": part == "pilot_dont_know",
                "English": False,
                "repeat, key change, shuffle, option word, rerun, question list": [None] * 6,
                "sample": WEB_GROUNDING_SAMPLE["questions"],
            }
            for name, value in kind.items():
                if value != expected[name]:
                    raise ValueError(f"web_grounding: run {run} ({part}, {arm}): {name} is {value!r}, not {expected[name]!r}")
    if len({by_run[run]["selection_sha256"] for run in WEB_GROUNDING_ONLY}) != 1:
        raise ValueError("web_grounding: the pilot runs were asked different questions")
    return WEB_GROUNDING_ONLY | repeats


def web_grounding(data: dict[str, Any], by_run: dict[int, dict[str, Any]], answers: dict[str, Any],
                  inputs: dict[str, Any]) -> dict[str, Any]:
    """Perplexity's web grounding test (results.json `web_grounding`) from the runs' records and answers and
    web-grounding.json. The pairs: the two setups' Text tab runs on the full bank (`turkish`), their English runs on the
    kept reading questions (`english`) and their Hallucination tab runs (`dont_know`), then the pilots on the 200-question
    sample (`pilot`, `pilot_dont_know`). Per arm the right answers, accuracy, median and WEB_GROUNDING_PERCENTILE request
    time and cost per 1M questions, overall and for the Turkish runs by group (reading, grammar), and the paired counts
    of right answers (exact McNemar, off only against on only); for the full bank and the English pair also each repeat
    (`repeats`: its runs, paired counts and source checks) and each arm's runs together (`mean`: mean, lowest and highest
    run); the "Bilmiyorum" pairs' counts and rates; what the grounded
    runs' searches returned, with the right answers off and on among the questions of each literal-match and source
    check; PWS-Decisions' aggregates at the same price, with its paired counts' exact McNemar test, and what Perplexity
    reported (WEB_GROUNDING_REPORTED). Costs: each request's input tokens at the grounded runs' price, plus its fee per
    request (one web search each) for every grounded request: an upper bound, as Perplexity bills completed searches."""
    questions = answers["questions"]
    scored = [index for index, status in enumerate(questions["status"]) if status != "excluded"]
    position = {question: index for index, question in enumerate(questions["id"])}
    exported = {run["run"]: run for key, runs in answers.items() if key.endswith("runs") for run in runs}
    tokens = {item["run"]: item for item in inputs["runs"]}

    def by_mode(items: list[dict[str, Any]], what: str) -> tuple[Any, Any]:
        """The off and on entries of the test's setup in a section's list (each with its perplexity_mode)."""
        found = {mode: [item for item in items if (item["provider"], item["model"]) == WEB_GROUNDING_SETUP
                        and item["perplexity_mode"] == mode] for mode in (None, WEB_GROUNDING_MODE)}
        if any(len(entries) != 1 for entries in found.values()):
            raise ValueError(f"web_grounding: needs one {what} with grounding off and one with it on, found "
                             f"{ {mode: [entry['run'] for entry in entries] for mode, entries in found.items()} }")
        return found[None][0], found[WEB_GROUNDING_MODE][0]

    text_off, text_on = by_mode(data["runs"], "Text tab run")
    english_off, english_on = by_mode([{**model, "perplexity_mode": by_run[model["run"]].get("perplexity_mode")}
                                       for model in data["english_reading"]["models"]], "English reading model")
    idk_off, idk_on = by_mode(data["dont_know"]["models"], "Hallucination tab model")
    # The English "I don't know" pair (Ümit #1219): the setup's first English runs with the option, by their records' mode.
    english_idk = data["english_reading"].get("dont_know") or {}
    english_idk_off, english_idk_on = by_mode(
        [{**model["english"], "text_run": model["text_run"], "provider": by_run[model["english"]["run"]].get("provider", "ollama"),
          "model": by_run[model["english"]["run"]]["model"], "perplexity_mode": by_run[model["english"]["run"]].get("perplexity_mode")}
         for model in english_idk.get("models", []) + english_idk.get("english_only", [])], "English \"I don't know\" model")
    pairs = {"turkish": (text_off["run"], text_on["run"]), "english": (english_off["run"], english_on["run"]),
             "dont_know": (idk_off["run"], idk_on["run"]),
             "english_dont_know": (english_idk_off["run"], english_idk_on["run"]), **WEB_GROUNDING_PILOTS}
    if (english_idk_off["text_run"], english_idk_on["text_run"]) != pairs["turkish"]:
        raise ValueError("web_grounding: the English \"I don't know\" runs are not those of the two Text tab runs")
    if (english_off["turkish_run"], english_on["turkish_run"]) != pairs["turkish"]:
        raise ValueError("web_grounding: the English runs are not those of the two Text tab runs")

    def repeats_of(first: int) -> dict[int, int]:
        """The repeats of a first run in answers.json's web_grounding_runs, by repeat number: the same setup, mode and
        language, asked the same questions in the same order with the same bank and settings."""
        record, found = by_run[first], {}
        for run in sorted(exported):
            other = by_run[run]
            if (run in WEB_GROUNDING_ONLY or not web_grounding_repeat(other)
                    or other.get("perplexity_mode") != record.get("perplexity_mode")
                    or bool(other.get("english")) != bool(record.get("english"))):
                continue
            for key in ("selection_sha256", "question_list", "english", "batch_size", "thinking", "dataset_sha256", "seed"):
                if other.get(key) != record.get(key):
                    raise ValueError(f"web_grounding: repeat run {run} differs from run {first} in {key}")
            if other["repeat"] in found:
                raise ValueError(f"web_grounding: runs {found[other['repeat']]} and {run} are both repeat {other['repeat']} of {first}")
            found[other["repeat"]] = run
        return dict(sorted(found.items()))

    repeated = {part: {"off": repeats_of(pairs[part][0]), "on": repeats_of(pairs[part][1])} for part in ("turkish", "english")}
    for part, sides in repeated.items():
        if list(sides["off"]) != list(sides["on"]):
            raise ValueError(f"web_grounding: the {part} repeats off {sides['off']} and on {sides['on']} are not in pairs")
    repeat_runs = {run for sides in repeated.values() for side in sides.values() for run in side.values()}
    stray = {run for run in exported if web_grounding_repeat(by_run[run])} - repeat_runs
    if stray:
        raise ValueError(f"web_grounding: runs {sorted(stray)} repeat none of the test's first runs")
    price = by_run[text_on["run"]]["price"]
    rates = price["rates"]
    for run in sorted({run for pair_runs in pairs.values() for run in pair_runs} | repeat_runs):
        record = by_run[run]
        grounded = record.get("perplexity_mode") is not None
        if record["price"]["rates"] != rates or record["price"]["per_request"] != (price["per_request"] if grounded else 0):
            raise ValueError(f"web_grounding: run {run} has another price than the grounded runs' rates")
        if rates["output_tokens"] or any(record.get(kind) for kind in ("cached_input_tokens", "cache_write_input_tokens",
                                                                       "cache_write_1h_input_tokens")):
            raise ValueError(f"web_grounding: run {run}: the cost here counts input tokens and requests only")
        if run not in tokens:
            raise ValueError(f"web_grounding: run {run} is not in web-grounding.json; run web_grounding_inputs.py")

    def group_of(index: int) -> str:
        return "reading" if questions["unit"][index] in READING_UNITS else "grammar"

    def asked(run: int) -> list[int]:
        return [index for index in scored if exported[run]["correct"][index] is not None]

    def measures(run: int, indices: list[int], input_tokens: int) -> dict[str, Any]:
        record, answered = by_run[run], exported[run]
        seconds = [answered["request_seconds"][index] for index in indices]
        correct = sum(int(answered["correct"][index]) for index in indices)
        searches = len(indices) if record.get("perplexity_mode") is not None else 0
        cost = input_tokens * rates["input_tokens"] / 1e6 + searches * price["per_request"]
        return {
            "questions": len(indices),
            "correct": correct,
            "accuracy": correct / len(indices),
            "median_request_seconds": statistics.median(seconds),
            "p95_request_seconds": nearest_rank(seconds, WEB_GROUNDING_PERCENTILE),
            "input_tokens": input_tokens,
            "searches": searches,
            "cost_usd": cost,
            "cost_per_million_questions": cost / len(indices) * 1e6,
        }

    def arm(run: int, by_group: bool) -> dict[str, Any]:
        record, indices = by_run[run], asked(run)
        groups = tokens[run]["groups"]
        found = {"run": run, **measures(run, indices, sum(item["input_tokens"] for item in groups.values()))}
        label = f"web_grounding: run {run}"
        if (found["questions"], found["correct"]) != (record["evaluated"], record["correct"]):
            raise ValueError(f"{label}: its answers count {found['correct']} of {found['questions']}, its record "
                             f"{record['correct']} of {record['evaluated']}")
        if found["input_tokens"] != record["input_tokens"] or not math.isclose(found["cost_usd"], record["cost_usd"], rel_tol=1e-9):
            raise ValueError(f"{label}: tokens {found['input_tokens']} and cost {found['cost_usd']} differ from its record's")
        # answers.json keeps request times to the millisecond, so the median from it is within half a millisecond.
        if not math.isclose(found["median_request_seconds"], record["median_request_seconds"], abs_tol=0.0005):
            raise ValueError(f"{label}: the answers' median request time differs from its record's")
        if by_group:
            parts = {name: [index for index in indices if group_of(index) == name] for name in ("reading", "grammar")}
            if any(len(parts[name]) != groups[name]["questions"] for name in parts):
                raise ValueError(f"{label}: its groups differ from web-grounding.json's")
            found["groups"] = {name: measures(run, parts[name], groups[name]["input_tokens"]) for name in parts}
        return found

    def paired(off: int, on: int, indices: list[int]) -> dict[str, Any]:
        """Off against on over `indices` (the questions of the pair's first off run) that both runs answered: both
        right, right only off, only on, both wrong, and the exact McNemar test; besides, per arm, its errors (an answer
        that was no option, scored wrong) and the questions it lacks."""
        runs = {"off": off, "on": on}
        both = [index for index in indices if all(exported[run]["correct"][index] is not None for run in runs.values())]
        right = {side: [int(exported[run]["correct"][index]) for index in both] for side, run in runs.items()}
        test = bm.paired_comparison(right["off"], right["on"])
        return {"questions": test["questions"],
                "both_right": sum(a and b for a, b in zip(right["off"], right["on"])),
                "off_only": test["first_only"], "on_only": test["second_only"],
                "both_wrong": sum(not a and not b for a, b in zip(right["off"], right["on"])),
                "errors": {side: sum(exported[run]["correct"][index] is not None and exported[run]["choice"][index] is None
                                     for index in indices) for side, run in runs.items()},
                "missing": {side: sum(exported[run]["correct"][index] is None for index in indices) for side, run in runs.items()},
                "p": test["p"]}

    def search(off: int, on: int) -> dict[str, Any] | None:
        """What a grounded run's search returned, with the right answers off and on among each check's questions; None
        for a run that returned no page (no source checks, not zero)."""
        found = tokens[on]["search"]
        if not found["pages"]:
            return None

        def checked(ids: list[int]) -> dict[str, Any]:
            """A check's questions, the right answers off and on among them, and those right only off (losses with
            grounding) and only on (gains)."""
            right = {run: [int(exported[run]["correct"][position[question]]) for question in ids] for run in (off, on)}
            return {"questions": len(ids), "ids": ids, "right_off": sum(right[off]), "right_on": sum(right[on]),
                    "off_only": sum(a and not b for a, b in zip(right[off], right[on])),
                    "on_only": sum(b and not a for a, b in zip(right[off], right[on]))}

        return {
            "run": on,
            **{key: found[key] for key in ("pages", "pages_per_question", "sites", "top_domains")},
            **{key: checked(found[key]) for key in ("shared_words", "publisher", "source_book")},
        }

    def spread(values: list[float]) -> dict[str, float]:
        return {"mean": statistics.mean(values), "min": min(values), "max": max(values)}

    def mean_arm(items: list[dict[str, Any]], by_group: bool) -> dict[str, Any]:
        """An arm's runs together: each measure's mean with the lowest and highest run, overall and by group."""
        keys = ("correct", "accuracy", "median_request_seconds", "p95_request_seconds", "cost_per_million_questions")

        def over(parts: list[dict[str, Any]]) -> dict[str, Any]:
            if len({part["questions"] for part in parts}) != 1:
                raise ValueError(f"web_grounding: runs {[item['run'] for item in items]} answered different numbers of questions")
            return {"questions": parts[0]["questions"], **{key: spread([part[key] for part in parts]) for key in keys}}

        found = {"runs": [item["run"] for item in items], **over(items)}
        if by_group:
            found["groups"] = {name: over([item["groups"][name] for item in items]) for name in ("reading", "grammar")}
        return found

    def pair(part: str, by_group: bool) -> dict[str, Any]:
        off, on = pairs[part]
        indices = asked(off)
        if asked(on) != indices:
            raise ValueError(f"web_grounding: runs {off} and {on} answered different questions")

        def compared(run_off: int, run_on: int) -> dict[str, Any]:
            found = {"off": arm(run_off, by_group), "on": arm(run_on, by_group), "paired": paired(run_off, run_on, indices)}
            if by_group:
                found["paired_groups"] = {name: paired(run_off, run_on, [index for index in indices if group_of(index) == name])
                                          for name in ("reading", "grammar")}
            return {**found, "search": search(run_off, run_on)}

        found = {"questions": len(indices), **compared(off, on)}
        if part in repeated:
            # Each repeat with its own pair of runs (repeat n off against repeat n on, on the first runs' questions),
            # then every run of each arm together (the first run and its repeats).
            found["repeats"] = [
                {"repeat": number, "dates": sorted({by_run[run]["started"][:10] for run in (run_off, run_on)}),
                 **compared(run_off, run_on)}
                for number, run_off, run_on in ((number, repeated[part]["off"][number], repeated[part]["on"][number])
                                                for number in repeated[part]["off"])]
            found["mean"] = {side: mean_arm([found[side], *(entry[side] for entry in found["repeats"])], by_group)
                             for side in ("off", "on")}
        return found

    def dont_know_pair(part: str) -> dict[str, Any]:
        found = {}
        for name, run in zip(("off", "on"), pairs[part]):
            got = by_run[run]["dont_know_answers"]
            answered = got["right"] + got["wrong"]
            found[name] = {
                "run": run,
                **{key: got[key] for key in ("questions", "right", "wrong", "dont_know", "invalid", "accuracy", "non_hallucination")},
                "answered": answered / got["questions"],
                "wrong_of_answers": got["wrong"] / answered if answered else None,
            }
        if found["off"]["questions"] != found["on"]["questions"]:
            raise ValueError(f"web_grounding: the {part} runs count different questions")
        return {"questions": found["off"]["questions"], **found}

    def english_dont_know_pair() -> dict[str, Any]:
        """The English "I don't know" pair as english_reading.dont_know counts it on the kept questions."""
        found = {}
        for name, side in (("off", english_idk_off), ("on", english_idk_on)):
            answered = side["right"] + side["wrong"]
            found[name] = {
                "run": side["run"],
                "questions": answered + side["dont_know"] + side["invalid"],
                **{key: side[key] for key in ("right", "wrong", "dont_know", "invalid", "accuracy", "non_hallucination")},
                "answered": side["attempt_rate"],
                "wrong_of_answers": side["wrong"] / answered if answered else None,
            }
        if found["off"]["questions"] != found["on"]["questions"]:
            raise ValueError("web_grounding: the English \"I don't know\" runs count different questions")
        return {"questions": found["off"]["questions"], **found}

    sample = asked(pairs["pilot"][0])
    if any(asked(run) != sample or exported[run]["seed"] != WEB_GROUNDING_SAMPLE["seed"] for run in WEB_GROUNDING_ONLY):
        raise ValueError("web_grounding: the pilot runs were not all asked the sample's questions")
    pws = inputs["pws"]

    def pws_arm(name: str) -> dict[str, Any]:
        got = pws[name]
        searches = got["questions"] if name == "on" else 0
        cost = got["input_tokens"] * rates["input_tokens"] / 1e6 + searches * price["per_request"]
        return {
            **{key: got[key] for key in ("questions", "correct", "errors", "median_request_seconds", "p95_request_seconds",
                                         "input_tokens")},
            "accuracy": got["correct"] / got["questions"],
            "searches": searches,
            "cost_usd": cost,
            "cost_per_million_questions": cost / got["questions"] * 1e6,
            **({"search": got["search"]} if "search" in got else {}),
        }

    return {
        "provider": WEB_GROUNDING_SETUP[0],
        "model": WEB_GROUNDING_SETUP[1],
        "names": {"off": text_off["name"], "on": text_on["name"]},
        "text_runs": {"off": text_off["run"], "on": text_on["run"]},
        "dates": sorted({by_run[run]["started"][:10] for pair_runs in pairs.values() for run in pair_runs}
                        | {by_run[run]["started"][:10] for run in repeat_runs}),
        "price": {key: price[key] for key in ("basis", "source", "date", "text")}
        | {"input_per_million": rates["input_tokens"], "per_search": price["per_request"], "upper_bound": True},
        "reading_units": list(READING_UNITS),
        "percentile": WEB_GROUNDING_PERCENTILE,
        "sample": {**WEB_GROUNDING_SAMPLE, "selection_sha256": by_run[pairs["pilot"][0]]["selection_sha256"]},
        "rules": inputs["rules"],
        "turkish": pair("turkish", True),
        "english": {**pair("english", False), "question_list": by_run[pairs["english"][0]]["question_list"]},
        "dont_know": dont_know_pair("dont_know"),
        "english_dont_know": english_dont_know_pair(),
        "pilot": pair("pilot", True),
        "pilot_dont_know": dont_know_pair("pilot_dont_know"),
        "pws": {
            **{key: pws[key] for key in ("name", "version", "questions_sha256", "language")},
            "off": pws_arm("off"),
            "on": pws_arm("on"),
            "paired": {"questions": pws["on"]["questions"], "off_only": pws["off_only"], "on_only": pws["on_only"],
                       "p": bm.sign_test(pws["off_only"], pws["on_only"])},
            "reported": WEB_GROUNDING_REPORTED,
        },
    }


# The Text tab model of an English run's model, by (provider, model), where the two names differ: Liquid's API no longer
# serves the d1:free name of d1 (its model list still names d1), so d1's English runs ask for d1 while its Text tab run
# asked for d1:free.
ENGLISH_TEXT_MODEL = {("liquid", "d1"): "d1:free"}
# Ümit's English "I don't know" comparison of four models (results.json `dont_know_english_option`), by Text tab run in
# this order, with Holm's correction over these four alone.
ENGLISH_OPTION_FOUR = (199, 346, 373, 374)
ENGLISH_OPTION_FOUR_SOURCE = ("Ümit's follow-up of 2 November 2026, step 2: the English “I don't know” comparison for "
                              "Liquid d1-ultra, SubQ Snap 1.1, Elephant-1 and Mammoth-1, with Holm's correction over these four")

# English "I don't know" setups published without a Turkish side (results.json `english_reading.dont_know.english_only`),
# by (provider, model), with the reason shown: Zeki's #883 of 3 November 2026. Any other setup without a Turkish side
# stops the export (but English-only setups, by rule, with ENGLISH_ONLY_SETUP), and so does a listed setup that has one.
ENGLISH_DONT_KNOW_ENGLISH_ONLY = {
    ("celeris", "celeris-1-decision"): ("no Turkish run with “Bilmiyorum” on these questions; new Turkish runs were "
                                        "outside the request of 3 November 2026"),
}
# The reason shown for an English "I don't know" setup whose English reading entry is English-only (no Text tab run).
ENGLISH_ONLY_SETUP = "no Turkish run: an English-only setup"


def english_reading(records: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any] | None:
    """The runs of the English reading track (results.json `english_reading`) from the report's records of runs in
    English: one entry per setup (provider, model, reasoning, questions per request, Perplexity mode) with its runs, the
    first run without a repeat number first and its repeats after it, and its Text tab run (same provider, model as
    ENGLISH_TEXT_MODEL maps it, reasoning, variant, questions per request and Perplexity mode) with that run's whole-bank
    repeats. Decision and chat
    models alike (Ümit via Zeki #1136, 5 November 2026: every Text tab setup in English too). A setup without such a
    Text tab run (Ümit's small models, run in English only) is an English-only entry (`english_only`): its name, settings,
    size record (size_record), view bar group (group_of), access (access_text), billing, hardware, note and its first
    English run's cost and latency, with no Turkish side. None without such runs. The numbers come from the answers
    (english_reading_answers_part)."""
    if not records:
        return None
    setups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in sorted(records, key=lambda record: record["run_id"]):
        key = (record.get("provider", "ollama"), record["model"], record["thinking"], record["batch_size"], record.get("perplexity_mode"))
        setups.setdefault(key, []).append(record)
    repeats = {item["runs"][0]: item["runs"] for item in data["repeats"] if item["whole_bank"]}
    models, english_only = [], []
    for (provider, model, thinking, batch_size, mode), found in setups.items():
        label = f"{model} ({provider}), English runs {[record['run_id'] for record in found]}"
        if provider not in PROVIDERS:
            raise ValueError(f"{label}: unknown provider; add it to PROVIDERS")
        if sum(1 for record in found if record.get("repeat") is None) != 1:
            raise ValueError(f"{label}: needs exactly one run without a repeat number")
        found.sort(key=lambda record: (record.get("repeat") or 1, record["run_id"]))
        reasoning = None if PROVIDERS[provider]["scoring"] else thinking
        text_model = ENGLISH_TEXT_MODEL.get((provider, model), model)
        paired = [
            run for run in data["runs"]
            if (run["provider"], run["model"], run["reasoning"], run["variant"], run["questions_per_request"], run["perplexity_mode"])
            == (provider, text_model, reasoning, run_variant({"provider": provider, "perplexity_mode": mode}), batch_size, mode)
        ]
        if len(paired) > 1:
            raise ValueError(f"{label}: needs at most one Text tab run of {text_model} with {batch_size} question"
                             f"{'' if batch_size == 1 else 's'} per request, found {[run['run'] for run in paired]}")
        first = found[0]
        # Cost and time per request of the first English run, beside its Text tab run's (Ümit via Zeki #1189): the run's
        # tokens at the price the runner records with it (its cost basis from its billing and the price, as for a main
        # run; a GPU-time estimate also gives the request time it counts), and its
        # median and 90th-percentile time per request as the runner measured it.
        info = model_info(provider, model, mode)
        billing = info.get("billing", PROVIDERS[provider]["billing"])
        cost, price = first.get("cost_usd"), first.get("price")
        if (cost is None) != (price is None):
            raise ValueError(f"{label}: a cost needs its price, and a price its cost")
        applies = None if price is None else price.get("applies_to", "billed")
        if price is not None and applies not in COST_BASES[billing]:
            raise ValueError(f"{label}: billed as {billing!r}, but its price applies to {applies!r}")
        tokens = {kind: first.get(kind, 0) for kind in TOKEN_KINDS}
        english_cost = None if cost is None else {
            "usd": cost, "per_1000": 1000 * cost / first["evaluated"], "basis": COST_BASES[billing][applies],
            "billing": billing, "tokens": tokens, "requests": first.get("requests"), "price": price,
            "upper_bound": upper_bound_cost(first),
            **({"request_seconds": first["timed_seconds"]} if applies == "gpu" else {}),
        }
        english_latency = None if first.get("median_request_seconds") is None else {
            "median_request_seconds": first["median_request_seconds"],
            "p90_request_seconds": first.get("p90_request_seconds"),
            "concurrency": first.get("concurrency"),
            "questions_per_request": batch_size,
        }
        if not paired:
            # An English-only setup (Ümit's small models, bus #3446): no Text tab run of the same setup, so no Turkish
            # side, no paired test and no Holm adjustment; it carries what the pages need without a Text tab run.
            if model not in SIZES:
                raise ValueError(f"{label}: its model has no size record; add one to SIZES")
            if cost is None and billing != "local":
                raise ValueError(f"{label}: billed as {billing!r} without a price")
            if billing == "local" and "hardware" not in info:
                raise ValueError(f"{label}: runs on our GPUs; add its hardware to MODELS")
            if applies == "gpu" and not info["hardware"].startswith(f"{price['gpus']} × "):
                raise ValueError(f"{label}: its GPU-time price counts {price['gpus']} GPUs, its hardware {info['hardware']!r}")
            english_only.append(
                {
                    "name": info.get("name", model),
                    "model": model,
                    "provider": provider,
                    "reasoning": reasoning,
                    "variant": run_variant({"provider": provider, "perplexity_mode": mode}),
                    "questions_per_request": batch_size,
                    "perplexity_mode": mode,
                    "run": first["run_id"],
                    "runs": [record["run_id"] for record in found],
                    "dates": sorted({record["started"][:10] for record in found}),
                    **size_record(model),
                    "group": group_of(provider, model),
                    "access": access_text(provider, info, first),
                    "billing": billing,
                    "hardware": info.get("hardware") if billing == "local" else None,
                    "note": " ".join(note for note in (info.get("note"), RUN_NOTES.get(first["run_id"])) if note) or None,
                    "cost": {"english": english_cost},
                    "latency": {"english": english_latency},
                }
            )
            continue
        turkish = paired[0]
        text_cost = turkish["api_equivalent_usd"]
        text_latency = turkish.get("latency")
        models.append(
            {
                "name": turkish["name"],
                "model": model,
                "provider": provider,
                "run": first["run_id"],
                "runs": [record["run_id"] for record in found],
                # The days the English runs started, for the setup's model page (its English section's settings).
                "dates": sorted({record["started"][:10] for record in found}),
                "perplexity_mode": mode,
                "turkish_run": turkish["run"],
                "turkish_runs": repeats.get(turkish["run"], [turkish["run"]]),
                "cost": {
                    "english": english_cost,
                    "turkish": None if text_cost is None else {
                        "usd": text_cost, "per_1000": 1000 * text_cost / turkish["answered_questions"], "basis": turkish["cost_basis"],
                        "upper_bound": turkish["cost_upper_bound"],
                    },
                },
                "latency": {
                    "english": english_latency,
                    "turkish": None if text_latency is None else {
                        "median_request_seconds": text_latency["median_request_seconds"],
                        "p90_request_seconds": text_latency["p90_request_seconds"],
                        "concurrency": text_latency["concurrency"],
                        "questions_per_request": turkish["questions_per_request"],
                        "source": text_latency["source"],
                    },
                },
            }
        )
    return {"models": models, "english_only": english_only, "records": {record["run_id"]: record for record in records}}


def kept_questions(answers: dict[str, Any], public: dict[str, Any]) -> list[int]:
    """The positions in the answers of the English reading track's kept questions (english-reading.json), after
    checking that its question list gives its counts and holds only scored questions of their units."""
    questions = answers["questions"]
    index_of = {question: index for index, question in enumerate(questions["id"])}
    listed = public["questions"]
    kept_ids = [item["question_id"] for item in listed if item["kept"]]
    if (len(listed) != public["reading_questions"] or len(kept_ids) != public["kept"]
            or len(listed) - len(kept_ids) != public["flagged"] or len({item["question_id"] for item in listed}) != len(listed)):
        raise ValueError(f"{ENGLISH_READING_PATH.name}: its question list does not give its counts")
    if any(item["question_id"] not in index_of or questions["unit"][index_of[item["question_id"]]] != item["unit"]
           or questions["status"][index_of[item["question_id"]]] == "excluded" for item in listed):
        raise ValueError(f"{ENGLISH_READING_PATH.name}: a listed question is not a scored question of its unit in the answers")
    return sorted(index_of[question] for question in kept_ids)


def english_reading_answers_part(section: dict[str, Any], document: dict[str, Any], answers: dict[str, Any],
                                 public: dict[str, Any]) -> dict[str, Any]:
    """The `english_reading` section from the answers file and the track's public record (english-reading.json): the
    English prompts (english_prompts, the decision models' System One instructions naming English, and
    english_chat_prompts, the chat models' Turkish run prompts in English, each hashed as the runner hashes them; every
    English run must carry its kind's version, decision for a scoring provider, plain_prompts' English one for vllm-plain
    and chat for any other, and the record's
    translations_sha256, and must have been asked exactly its kept questions), and per model, on the kept questions, the
    right, wrong and invalid answers and accuracy of its first English run and of its Text tab run, the difference, the
    accuracy range and the questions whose answer differs over each side's runs (None for a side with one run, and for
    both when both sides have one), and the first English run against the Text tab run as right answers in each (exact
    McNemar, bm.paired_comparison: first English, second Turkish) with Holm's correction over every model. Ordered by
    English accuracy, best first, then by name. The English-only setups (`english_only`) get their first English run's
    right, wrong and invalid answers and accuracy only, in the same order."""
    prompts = document.get("english_prompts")
    if prompts is None:
        raise ValueError("the answers file has English runs but no english_prompts")
    instructions, heading = prompts["system_one_instructions"], prompts["options_heading"]
    if instructions != document["prompts"]["system_one_instructions"].replace("Turkish", "English"):
        raise ValueError("english_prompts: the instructions are not the System One instructions naming English")

    def hashed(found: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(found, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]

    version = hashed(prompts)
    chat_prompts = document.get("english_chat_prompts")
    chat_version = None if chat_prompts is None else hashed(chat_prompts)
    if chat_prompts is not None and chat_prompts["options_heading"] != heading:
        raise ValueError("english_chat_prompts: the options heading is not the decision models' English one")
    translations = public["translations_sha256"]
    kept = kept_questions(answers, public)
    total = len(kept)
    by_id = {run["run"]: run for run in answers["english_runs"]}
    turkish_answers = {run["run"]: run for run in answers["runs"] + answers["repeat_runs"]}
    for run_id, run in sorted(by_id.items()):
        english = section["records"][run_id]["english"]
        if run["english"] != english:
            raise ValueError(f"English run {run_id}: the answers file and the report give different English records")
        if english.get("translations_sha256") != translations:
            raise ValueError(f"English run {run_id}: translations {str(english.get('translations_sha256'))[:12]}, not "
                             f"{ENGLISH_READING_PATH.name}'s {translations[:12]}")
        expected = (plain_version(document, "english") if run["provider"] == "vllm-plain"
                    else version if PROVIDERS[run["provider"]]["scoring"] else chat_version)
        if expected is None or english.get("prompt_version") != expected or run["prompt_version"] != expected:
            raise ValueError(f"English run {run_id} ({run['provider']}) was not run with its prompt version {expected}")
        asked = [index for index, value in enumerate(run["correct"]) if value is not None]
        if english.get("questions") != total or asked != kept:
            raise ValueError(f"English run {run_id} was not asked exactly the {total} kept questions")

    def counted(run: dict[str, Any]) -> dict[str, Any]:
        right = sum(1 for index in kept if run["correct"][index])
        invalid = sum(1 for index in kept if run["choice"][index] is None)
        return {"right": right, "wrong": total - right - invalid, "invalid": invalid, "accuracy": right / total}

    def changed(runs: list[dict[str, Any]]) -> int:
        choices = [run["choice"] for run in runs]
        return sum(1 for index in kept if all(choice[index] is not None for choice in choices)
                   and len({choice[index] for choice in choices}) > 1)

    models = []
    for model in section["models"]:
        missing = [run for run in model["turkish_runs"] if run not in turkish_answers]
        if missing:
            raise ValueError(f"{model['name']}: the answers file lacks its Text tab runs {missing}")
        sides = {"english": [by_id[run] for run in model["runs"]],
                 "turkish": [turkish_answers[run] for run in model["turkish_runs"]]}
        counts = {side: [counted(run) for run in runs] for side, runs in sides.items()}
        spread = {side: None if len(found) == 1 else {"low": min(item["accuracy"] for item in found),
                                                      "high": max(item["accuracy"] for item in found)}
                  for side, found in counts.items()}
        answers_changed = {side: None if len(runs) == 1 else changed(runs) for side, runs in sides.items()}
        test = bm.paired_comparison([int(bool(sides["english"][0]["correct"][index])) for index in kept],
                                    [int(bool(sides["turkish"][0]["correct"][index])) for index in kept])
        english, turkish = counts["english"][0], counts["turkish"][0]
        models.append(
            {
                **model,
                "english": english,
                "turkish": turkish,
                "difference": english["accuracy"] - turkish["accuracy"],
                "spread": None if all(value is None for value in spread.values()) else spread,
                "answers_changed": None if all(value is None for value in answers_changed.values()) else answers_changed,
                "paired": {"english_only_right": test["first_only"], "turkish_only_right": test["second_only"],
                           "p": test["p"], "p_holm": None},
            }
        )
    for model, adjusted in zip(models, bm.holm([model["paired"]["p"] for model in models])):
        model["paired"]["p_holm"] = adjusted
    models.sort(key=lambda item: (-item["english"]["accuracy"], item["name"].casefold(), item["run"]))
    # English-only setups: the first English run's answers only, in no paired test and no Holm family.
    english_only = [{**model, "english": counted(by_id[model["run"]])} for model in section["english_only"]]
    english_only.sort(key=lambda item: (-item["english"]["accuracy"], item["name"].casefold(), item["run"]))
    return {
        "instructions": instructions,
        "options_heading": heading.strip(),
        "prompt_version": version,
        "chat_prompts": chat_prompts,
        "chat_prompt_version": chat_version,
        "translations_sha256": translations,
        "reading_questions": public["reading_questions"],
        "questions": total,
        "flagged": public["flagged"],
        "models": models,
        "english_only": english_only,
    }


def english_dont_know(records: list[dict[str, Any]], dont_know_section: dict[str, Any] | None,
                      english_section: dict[str, Any] | None) -> dict[str, Any] | None:
    """The runs of the English "I don't know" comparison (results.json `english_reading.dont_know`) from the report's
    records of runs with the "I don't know" option: one entry per setup of its runs in English (provider, model,
    reasoning, questions per request as its English reading run's; the first run without a repeat number first, its
    repeats after it), named after its English reading model (the one whose first English run its runs name as their
    original run), with its view bar group (group_of), and its Turkish side, the same setup's runs with the option:
    its runs on exactly the English runs' questions with a question list (subset runs, same order) where it has them,
    even with a Hallucination tab row, else its full-bank runs on the Hallucination tab (the row of the same Text tab
    run, provider and model), counted
    on the kept questions. Turkish runs with the option on that many listed questions belong to no other section, so
    each must pair with an English setup. A setup without a Turkish side is published in English only
    (`english_only`): a decision model with its reason from ENGLISH_DONT_KNOW_ENGLISH_ONLY, a chat model with
    page_config.json's dont_know.running (`running` true), and, by rule, any setup whose English reading entry is
    English-only (ENGLISH_ONLY_SETUP; no Text tab run, so `text_run` None and `reading_run` its English reading entry's
    first run). A chat model's Hallucination tab row of an English reading
    model's Text tab run without English runs with the option is published in Turkish only (`turkish_only`, running).
    None without runs in English with the option. The numbers come from the answers (english_dont_know_answers_part)."""
    english = [record for record in records if record.get("english")]
    if not english:
        return None
    if english_section is None:
        raise ValueError('the report has runs in English with the "I don\'t know" option but no English reading runs')
    counts = {record["english"].get("questions") for record in english}
    if len(counts) != 1:
        raise ValueError(f'the runs in English with the "I don\'t know" option count different questions {sorted(counts, key=str)}')
    total = counts.pop()

    def setups(found: list[dict[str, Any]], kind: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for record in sorted(found, key=lambda record: record["run_id"]):
            key = (record.get("provider", "ollama"), record["model"], record["thinking"], record["batch_size"], record.get("perplexity_mode"))
            grouped.setdefault(key, []).append(record)
        for (provider, model, _, _size, _mode), group in grouped.items():
            label = f"{model} ({provider}), {kind} runs {[record['run_id'] for record in group]}"
            if sum(1 for record in group if record.get("repeat") is None) != 1:
                raise ValueError(f"{label}: needs exactly one run without a repeat number")
            group.sort(key=lambda record: (record.get("repeat") or 1, record["run_id"]))
        return grouped

    subsets = setups([record for record in records if not record.get("english") and record.get("question_list")
                      and record["evaluated"] == total], 'Turkish "I don\'t know" kept-question')
    by_record = {record["run_id"]: record for record in records}
    full = dont_know_section["models"] if dont_know_section else []
    models = []
    english_only = []
    claimed: list[dict[str, Any]] = []
    paired_rows: set[int] = set()
    for (provider, model, thinking, size, mode), found in setups(english, 'English "I don\'t know"').items():
        runs = [record["run_id"] for record in found]
        label = f"{model} ({provider}), English \"I don't know\" runs {runs}"
        originals = {record["dont_know_answers"]["original_run"] for record in found}
        reading = [item for item in english_section["models"] + english_section["english_only"] if item["run"] in originals]
        if len(originals) != 1 or len(reading) != 1 \
                or (reading[0]["provider"], reading[0]["model"], reading[0]["perplexity_mode"]) != (provider, model, mode):
            raise ValueError(f"{label}: its original runs {sorted(originals, key=str)} are not the first English run of one "
                             f"English reading model of the same provider and model")
        asked = english_section["records"][reading[0]["run"]]["batch_size"]
        if size != asked:
            raise ValueError(f"{label}: asked {size} questions per request, its English reading run {asked}")
        group = group_of(provider, model)
        subset = subsets.pop((provider, model, thinking, size, mode), None)
        if "turkish_run" not in reading[0]:
            if subset is not None:
                raise ValueError(f"{label}: an English-only setup with Turkish \"I don't know\" runs "
                                 f"{[record['run_id'] for record in subset]}")
            english_only.append({"name": reading[0]["name"], "model": model, "provider": provider, "group": group,
                                 "text_run": None, "reading_run": reading[0]["run"], "reason": ENGLISH_ONLY_SETUP,
                                 "running": False,
                                 "english": {"run": runs[0], "runs": runs, "invalid_replies": found[0].get("invalid_replies")}})
            continue
        text_run = reading[0]["turkish_run"]
        hallucination = [item for item in full if item["original_run"] == text_run
                         and (item["provider"], item["model"], item["perplexity_mode"]) == (provider, model, mode)]
        # A Turkish run on the kept questions is the setup's Turkish side even when the setup also has a full-bank row on
        # the Hallucination tab (that row stays the tab's); the full-bank runs are the Turkish side only without one.
        if subset is not None and hallucination:
            paired_rows.update(item["run"] for item in hallucination)
        reason = ENGLISH_DONT_KNOW_ENGLISH_ONLY.get((provider, model))
        if reason is not None:
            if subset is not None or hallucination:
                raise ValueError(f"{label}: listed in ENGLISH_DONT_KNOW_ENGLISH_ONLY but has Turkish \"I don't know\" runs "
                                 f"{[record['run_id'] for record in subset or []] or [item['runs'] for item in hallucination]}")
        if reason is not None or (group == "chat" and subset is None and not hallucination):
            english_only.append({"name": reading[0]["name"], "model": model, "provider": provider, "group": group,
                                 "text_run": text_run, "reason": reason or running_reason(), "running": reason is None,
                                 "english": {"run": runs[0], "runs": runs, "invalid_replies": found[0].get("invalid_replies")}})
            continue
        if subset is not None:
            turkish = [record["run_id"] for record in subset]
            claimed += subset
        elif len(hallucination) == 1 and all(
                (by_record[run]["thinking"], by_record[run]["batch_size"]) == (thinking, size) for run in hallucination[0]["runs"]):
            turkish = hallucination[0]["runs"]
            paired_rows.add(hallucination[0]["run"])
        else:
            raise ValueError(f"{label}: no Turkish \"I don't know\" runs of the same setup, on the kept questions or on "
                             f"the Hallucination tab (found {[item['runs'] for item in hallucination]}); a decision model "
                             f"published without a Turkish side must be listed in ENGLISH_DONT_KNOW_ENGLISH_ONLY")
        models.append(
            {
                "name": reading[0]["name"],
                "model": model,
                "provider": provider,
                "group": group,
                "text_run": text_run,
                "english": {"run": runs[0], "runs": runs, "invalid_replies": found[0].get("invalid_replies")},
                "turkish": {"run": turkish[0], "runs": turkish, "subset": subset is not None,
                            "invalid_replies": by_record[turkish[0]].get("invalid_replies")},
            }
        )
    if subsets:
        raise ValueError(f"Turkish \"I don't know\" runs on {total} listed questions "
                         f"{[record['run_id'] for group in subsets.values() for record in group]} have no English "
                         f"\"I don't know\" runs of the same setup")
    # A chat model's Hallucination tab row whose English run with the option is still running: Turkish only.
    reading_by_text = {item["turkish_run"]: item for item in english_section["models"]}
    turkish_only = [{"name": reading_by_text[row["original_run"]]["name"], "model": row["model"], "provider": row["provider"],
                     "group": row["group"], "text_run": row["original_run"], "reason": running_reason(), "running": True,
                     "turkish": {"run": row["run"], "runs": row["runs"], "subset": False,
                                 "invalid_replies": row["invalid_replies"]}}
                    for row in full if row["group"] == "chat" and row["run"] not in paired_rows
                    and row["original_run"] in reading_by_text]
    return {"models": models, "english_only": english_only, "turkish_only": turkish_only,
            "records": {record["run_id"]: record for record in english + claimed}}


def english_dont_know_answers_part(section: dict[str, Any], document: dict[str, Any], answers: dict[str, Any],
                                   public: dict[str, Any]) -> dict[str, Any]:
    """The `english_reading.dont_know` section from the answers file and english-reading.json: the option, its sentence,
    the English instructions with it and the prompt version (english_dont_know_prompts: the English prompts with the
    sentence added to the instructions and the option, hashed as the runner hashes them), and the chat models' English
    prompts with theirs (`chat`, chat_dont_know_prompts on english_dont_know_chat_prompts; omitted without a chat
    model's run). Every English run with the option must carry its kind's version (decision for a scoring provider,
    chat for any other) and the record's translations_sha256, every Turkish run on the kept questions the Turkish "I
    don't know" version (dont_know_prompts hashed), and both must have been asked exactly the kept questions and count,
    in their report records, what their answers give. Per model and side, on the kept questions, from its first run:
    right, wrong, "I don't know" (DONT_KNOW_LETTER) and invalid answers, accuracy, attempt rate, non-hallucination rate
    (None without "I don't know" or wrong answers) and the mean probability of the option over the answers that report
    it; the range of those over the side's runs (None for a side with one run, and for both when both have one); and
    the first runs' wrong answers against each other (exact McNemar, bm.paired_comparison: first English, second
    Turkish) with Holm's correction within each group (decision models, chat models). Ordered by English
    non-hallucination rate, best first and None last, then by name; english_only by its English rate and turkish_only
    (its Turkish side counted the same way) by its Turkish rate."""
    prompts = document.get("english_dont_know_prompts")
    if prompts is None:
        raise ValueError('the answers file has runs in English with the "I don\'t know" option but no english_dont_know_prompts')
    english_prompts = document["english_prompts"]
    option, instructions = prompts["dont_know_option"], prompts["system_one_instructions"]
    sentence = f"If you do not know the answer, choose {option}."
    if instructions != f"{english_prompts['system_one_instructions']} {sentence}":
        raise ValueError(f"english_dont_know_prompts: the instructions are not the English instructions plus {sentence!r}")
    if ({key: value for key, value in prompts.items() if key not in ("system_one_instructions", "dont_know_option")}
            != {key: value for key, value in english_prompts.items() if key != "system_one_instructions"}):
        raise ValueError("english_dont_know_prompts: besides the instructions and the option, not the English prompts")

    def hashed(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]

    version, turkish_version = hashed(prompts), hashed(document["dont_know_prompts"])
    translations = public["translations_sha256"]
    kept = kept_questions(answers, public)
    total = len(kept)
    english_runs = {run["run"]: run for run in answers["english_dont_know_runs"]}
    subset_runs = {run["run"]: run for run in answers["english_dont_know_turkish_runs"]}
    full_runs = {run["run"]: run for run in answers["dont_know_runs"]}
    chat = None
    if any(not PROVIDERS[run["provider"]]["scoring"] and run["provider"] != "vllm-plain" for run in english_runs.values()):
        chat = chat_dont_know_prompts(document.get("english_dont_know_chat_prompts"), document.get("english_chat_prompts") or {},
                                      option, "english_dont_know_chat_prompts")
    for run_id, run in sorted(english_runs.items()):
        english = section["records"][run_id]["english"]
        if run["english"] != english:
            raise ValueError(f"English \"I don't know\" run {run_id}: the answers file and the report give different English records")
        if english.get("translations_sha256") != translations:
            raise ValueError(f"English \"I don't know\" run {run_id}: translations {str(english.get('translations_sha256'))[:12]}, "
                             f"not {ENGLISH_READING_PATH.name}'s {translations[:12]}")
        expected = (plain_version(document, "english_dont_know") if run["provider"] == "vllm-plain"
                    else version if PROVIDERS[run["provider"]]["scoring"] else chat["prompt_version"])
        if english.get("prompt_version") != expected or run["prompt_version"] != expected:
            raise ValueError(f"English \"I don't know\" run {run_id} was not run with its kind's prompt version {expected}")
    for run_id, run in sorted(subset_runs.items()):
        if run["prompt_version"] != turkish_version:
            raise ValueError(f"Turkish \"I don't know\" run {run_id} on the kept questions was not run with prompt version {turkish_version}")
    for run_id, run in sorted({**english_runs, **subset_runs}.items()):
        asked = [index for index, value in enumerate(run["correct"]) if value is not None]
        if asked != kept or section["records"][run_id]["evaluated"] != total:
            raise ValueError(f"\"I don't know\" run {run_id} was not asked exactly the {total} kept questions")
    metrics = ("accuracy", "attempt_rate", "non_hallucination", "mean_dont_know_probability")

    def counted(run: dict[str, Any]) -> dict[str, Any]:
        found = {"right": 0, "wrong": 0, "dont_know": 0, "invalid": 0}
        shown = []
        for index in kept:
            choice, probabilities = run["choice"][index], run["probabilities"][index]
            if probabilities and DONT_KNOW_LETTER in probabilities:
                shown.append(float(probabilities[DONT_KNOW_LETTER]))
            if choice is None:
                found["invalid"] += 1
            elif choice == DONT_KNOW_LETTER:
                found["dont_know"] += 1
            elif run["correct"][index]:
                found["right"] += 1
            else:
                found["wrong"] += 1
        record = section["records"].get(run["run"])
        if record is not None and {key: record["dont_know_answers"][key] for key in found} != found:
            raise ValueError(f"\"I don't know\" run {run['run']}: its report record does not count what its answers give")
        return {
            **found,
            "accuracy": found["right"] / total,
            "attempt_rate": (found["right"] + found["wrong"]) / total,
            "non_hallucination": found["dont_know"] / (found["dont_know"] + found["wrong"]) if found["dont_know"] + found["wrong"] else None,
            "mean_dont_know_probability": sum(shown) / len(shown) if shown else None,
        }

    def wrong(run: dict[str, Any]) -> list[int]:
        return [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index]) for index in kept]

    models = []
    for model in section["models"]:
        sides = {"english": [english_runs[run] for run in model["english"]["runs"]],
                 "turkish": [(subset_runs if model["turkish"]["subset"] else full_runs)[run] for run in model["turkish"]["runs"]]}
        values = {side: [counted(run) for run in runs] for side, runs in sides.items()}
        spread = {
            side: None if len(found) == 1 else {
                key: None if any(value[key] is None for value in found) else [min(value[key] for value in found), max(value[key] for value in found)]
                for key in metrics
            }
            for side, found in values.items()
        }
        test = bm.paired_comparison(wrong(sides["english"][0]), wrong(sides["turkish"][0]))
        models.append(
            {
                **model,
                "english": {**model["english"], **values["english"][0]},
                "turkish": {**model["turkish"], **values["turkish"][0]},
                "spread": None if all(value is None for value in spread.values()) else spread,
                "paired": {"english_only_wrong": test["first_only"], "turkish_only_wrong": test["second_only"],
                           "p": test["p"], "p_holm": None},
            }
        )
    # Holm's correction within each view bar group: the decision models' family as before, the chat models' its own.
    for group in ("decision", "chat"):
        family = [model for model in models if model["group"] == group]
        for model, adjusted in zip(family, bm.holm([model["paired"]["p"] for model in family])):
            model["paired"]["p_holm"] = adjusted
    models.sort(key=lambda item: (item["english"]["non_hallucination"] is None, -(item["english"]["non_hallucination"] or 0),
                                  item["name"].casefold(), item["english"]["run"]))
    # Setups without a Turkish side (ENGLISH_DONT_KNOW_ENGLISH_ONLY, or a chat model's Turkish run still running): the
    # English first run's numbers only, in no Holm family.
    english_only = [{**model, "english": {**model["english"], **counted(english_runs[model["english"]["run"]])}}
                    for model in section["english_only"]]
    english_only.sort(key=lambda item: (item["english"]["non_hallucination"] is None, -(item["english"]["non_hallucination"] or 0),
                                        item["name"].casefold(), item["english"]["run"]))
    # A chat model's Hallucination tab run counted on the kept questions while its English run is still running.
    turkish_only = [{**model, "turkish": {**model["turkish"], **counted(full_runs[model["turkish"]["run"]])}}
                    for model in section["turkish_only"]]
    turkish_only.sort(key=lambda item: (item["turkish"]["non_hallucination"] is None, -(item["turkish"]["non_hallucination"] or 0),
                                        item["name"].casefold(), item["turkish"]["run"]))
    return {
        "option": option,
        "sentence": sentence,
        "instructions": instructions,
        "prompt_version": version,
        **({"chat": chat} if chat else {}),
        "questions": total,
        "models": models,
        **({"english_only": english_only} if english_only else {}),
        **({"turkish_only": turkish_only} if turkish_only else {}),
    }


def dont_know_english_option(section: dict[str, Any]) -> dict[str, Any]:
    """Ümit's four-model comparison (results.json `dont_know_english_option`) from `english_reading.dont_know`: per
    ENGLISH_OPTION_FOUR Text tab run, in that order, its entry's wrong answers only in English and only in Turkish and
    exact McNemar p, with Holm's correction over these four. Stops unless every listed run has exactly one entry."""
    models = []
    for text_run in ENGLISH_OPTION_FOUR:
        found = [model for model in section["models"] if model["text_run"] == text_run]
        if len(found) != 1:
            raise ValueError(f"English \"I don't know\" comparison of four: Text tab run {text_run} has {len(found)} entries, not one")
        paired = found[0]["paired"]
        models.append({"name": found[0]["name"], "text_run": text_run, "english_only_wrong": paired["english_only_wrong"],
                       "turkish_only_wrong": paired["turkish_only_wrong"], "p": paired["p"], "p_holm": None})
    for model, adjusted in zip(models, bm.holm([model["p"] for model in models])):
        model["p_holm"] = adjusted
    return {"source": ENGLISH_OPTION_FOUR_SOURCE, "questions": section["questions"], "models": models}


def option_word_vs_confidence(option_word: dict[str, Any], dont_know_section: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """`dont_know_option_word.vs_confidence`: per option-word model, in the section's order, its option-word run (the
    option written "I don't know") against its five-option run held back by its own confidence at the derived cut-off
    (derived_abstention at the option-word run's attempt rate, on the scored questions), as wrong answers in each (exact
    McNemar, bm.paired_comparison: first the option, second confidence), with Holm's correction over the models whose
    option-word run chose the option on at least VS_CONFIDENCE_SHARE of the scored questions. The five-option run is the
    Hallucination tab row's original run, except the hosted GLiDE rerun for RERUN_REPLACES. "below" and "above" name the
    neighbouring candidate cut-offs (the next lower and next higher distinct scores) with their answered counts. Stops
    unless the family is the Hallucination tab's own vs_confidence family."""
    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    words = {run["run"]: run for run in answers["dont_know_word_runs"]}
    main = {run["run"]: run for run in answers["runs"]}
    reruns = {run["run"]: run for run in answers.get("rerun_runs", [])}
    rows = {row["run"]: row for row in dont_know_section["models"]}
    if len(reruns) != 1:
        raise ValueError(f"vs_confidence: needs the one hosted GLiDE rerun, found runs {sorted(reruns)}")
    rerun_id = next(iter(reruns))
    models, family = [], []
    for model in option_word["models"]:
        row = rows[model["bilmiyorum"]["run"]]
        option_run = words[model["i_dont_know"]["run"]]
        replaces = row["original_run"] if row["original_run"] == RERUN_REPLACES else None
        five = reruns[rerun_id] if replaces is not None else main[row["original_run"]]
        published = model["i_dont_know"]
        option_wrong = [int(option_run["choice"][index] not in (None, DONT_KNOW_LETTER) and not option_run["correct"][index]) for index in scored]
        option_right = sum(1 for index in scored if option_run["choice"][index] not in (None, DONT_KNOW_LETTER) and option_run["correct"][index])
        option_dont_know = sum(1 for index in scored if option_run["choice"][index] == DONT_KNOW_LETTER)
        if (sum(option_wrong), option_right, option_dont_know) != (published["wrong"], published["right"], published["dont_know"]):
            raise ValueError(f"{model['name']}: option-word run {option_run['run']}'s answers do not give its published counts")
        pairs = [(None if five["score"][index] is None else float(five["score"][index]), int(five["correct"][index])) for index in scored]
        found = derived_abstention(pairs, published["attempt_rate"])
        cut_off = found["cut_off"]
        if cut_off is None:
            raise ValueError(f"{model['name']}: five-option run {five['run']} has no scores to derive a cut-off from")
        distinct = sorted({score for score, _ in pairs if score is not None})
        position = distinct.index(cut_off)

        def neighbour(at: int) -> dict[str, Any]:
            if not 0 <= at < len(distinct):
                return {"cut_off": None, "answered": None}
            return {"cut_off": distinct[at], "answered": sum(1 for score, _ in pairs if score is not None and score >= distinct[at])}

        confidence_wrong = [int(five["score"][index] is not None and float(five["score"][index]) >= cut_off and not five["correct"][index])
                            for index in scored]
        if sum(confidence_wrong) != found["wrong"]:
            raise ValueError(f"{model['name']}: run {five['run']}'s answers held back at {cut_off} do not give {found['wrong']} wrong answers")
        test = bm.paired_comparison(option_wrong, confidence_wrong)
        entry = {
            "name": model["name"],
            "option_run": option_run["run"],
            "five_option_run": five["run"],
            "replaces_run": replaces,
            "option": {"answered": published["right"] + published["wrong"], "attempt_rate": published["attempt_rate"],
                       "right": published["right"], "wrong": published["wrong"], "dont_know": published["dont_know"]},
            "derived": {"cut_off": cut_off, "answered": found["right"] + found["wrong"], "attempt_rate": found["attempt_rate"],
                        "right": found["right"], "wrong": found["wrong"], "abstained": found["abstained"],
                        "below": neighbour(position - 1), "above": neighbour(position + 1)},
            "option_only_wrong": test["first_only"],
            "confidence_only_wrong": test["second_only"],
            "p": test["p"],
            "p_holm": None,
        }
        models.append(entry)
        if published["dont_know"] >= VS_CONFIDENCE_SHARE * len(scored):
            family.append(entry)
    if [entry for entry in models if entry["replaces_run"] is not None] != [entry for entry in models if entry["five_option_run"] == rerun_id] \
            or sum(1 for entry in models if entry["five_option_run"] == rerun_id) != 1:
        raise ValueError(f"vs_confidence: run {rerun_id} must be the five-option run of exactly the model whose original run was {RERUN_REPLACES}")
    # The Hallucination tab's family among the models with an option-word run (OPTION_WORD_NOT_RUN's setups have none).
    asked = {model["name"] for model in option_word["models"]}
    existing = {row["name"] for row in dont_know_section["models"]
                if row["vs_confidence"] and row["vs_confidence"]["p_holm"] is not None and row["name"] in asked}
    if {entry["name"] for entry in family} != existing or len(family) != len(existing):
        raise ValueError(f"vs_confidence: the eligible family {sorted(entry['name'] for entry in family)} is not the Hallucination "
                         f"tab's among the option-word models, {sorted(existing)}")
    for entry, adjusted in zip(family, bm.holm([entry["p"] for entry in family])):
        entry["p_holm"] = adjusted
    return {"share": VS_CONFIDENCE_SHARE, "family": [entry["name"] for entry in family], "models": models}


COVERAGE_DEFINITIONS = (
    "All series are counted on the same kept reading questions; a full-bank run is restricted to them; first runs only. "
    "Answered = right + wrong (an invalid answer or one without a score is never answered). Coverage = answered / kept "
    "questions. Risk = error rate among answered = wrong / answered. Abstained: for a native point, the times the model "
    "chose the option; for a curve point, kept questions - answered - invalid. A native point is the run with its "
    "abstention option (Turkish \"Bilmiyorum\", Turkish \"I don't know\" as the wording control, English \"I don't "
    "know\"); Turkish \"Bilmiyorum\" is the Turkish side of the English \"I don't know\" comparison or, for a model "
    "outside it, its Hallucination tab run; a missing one reads Not run (Running while a chat model's run is still "
    "going). A curve is one five-option run held back "
    "by its recorded score (the "
    "probability of the chosen option): one point per distinct score s, answering when the score is at least s; "
    "answers with equal scores enter together, so coverage moves in jumps and every point is an achieved one; all "
    "distinct points kept, ordered by coverage."
)


def english_coverage(reading: dict[str, Any], option_word: dict[str, Any] | None, dont_know_section: dict[str, Any] | None,
                     answers: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    """`english_reading.coverage`: per model of `english_reading`, on the kept questions only, its native abstention
    points (Turkish "Bilmiyorum" from `english_reading.dont_know`'s Turkish side, or the Hallucination tab's first run of
    a model outside that comparison, Turkish "I don't know" from the
    option-word run of its Hallucination tab row, English "I don't know" from `english_reading.dont_know` including
    english_only; run None where not measured) and its confidence-derived risk-coverage curves (the Text tab run in
    Turkish, the first English run) from their recorded scores (COVERAGE_DEFINITIONS)."""
    kept = kept_questions(answers, public)
    total = len(kept)
    if total != public["kept"]:
        raise ValueError(f"coverage: {total} kept questions, english-reading.json says {public['kept']}")
    lists = {name: {run["run"]: run for run in answers.get(name, [])} for name in
             ("runs", "english_runs", "dont_know_runs", "english_dont_know_runs", "english_dont_know_turkish_runs", "dont_know_word_runs")}
    idk = reading.get("dont_know") or {"models": []}
    bilmiyorum = {model["text_run"]: model["turkish"] for model in idk["models"]}
    # English-only setups (text_run None) have no Turkish side and no coverage entry.
    english_idk = {model["text_run"]: model["english"] for model in idk["models"] + idk.get("english_only", [])
                   if model["text_run"] is not None}
    word_by_text: dict[int, int] = {}
    if option_word is not None:
        original = {row["run"]: row["original_run"] for row in dont_know_section["models"]}
        word_by_text = {original[model["bilmiyorum"]["run"]]: model["i_dont_know"]["run"] for model in option_word["models"]}
    # A model outside the English "I don't know" comparison: its Hallucination tab first run, by its Text tab run.
    hallucination = {row["original_run"]: row["run"] for row in (dont_know_section or {}).get("models", [])}

    def asked_all(run: dict[str, Any]) -> bool:
        return all(run["correct"][index] is not None for index in kept)

    def native(language: str, wording: str, run: dict[str, Any] | None, full_bank: bool) -> dict[str, Any]:
        if run is None:
            return {"language": language, "wording": wording, "run": None}
        if not asked_all(run):
            raise ValueError(f"coverage: run {run['run']} was not asked every kept question")
        found = {"right": 0, "wrong": 0, "abstained": 0, "invalid": 0}
        for index in kept:
            choice = run["choice"][index]
            key = "invalid" if choice is None else "abstained" if choice == DONT_KNOW_LETTER else "right" if run["correct"][index] else "wrong"
            found[key] += 1
        answered = found["right"] + found["wrong"]
        return {"language": language, "wording": wording, "run": run["run"], "full_bank_restricted": full_bank, **found,
                "coverage": answered / total, "risk": found["wrong"] / answered if answered else None}

    def curve(language: str, run: dict[str, Any]) -> dict[str, Any]:
        if not asked_all(run):
            raise ValueError(f"coverage: run {run['run']} was not asked every kept question")
        ranked = sorted(((float(run["score"][index]), bool(run["correct"][index])) for index in kept
                         if run["choice"][index] is not None and run["score"][index] is not None), key=lambda item: -item[0])
        points, answered, wrong = [], 0, 0
        for position, (score, correct) in enumerate(ranked):
            answered += 1
            wrong += not correct
            if position + 1 < len(ranked) and ranked[position + 1][0] == score:
                continue
            points.append([answered / total, wrong / answered, answered, wrong])
        return {"language": language, "run": run["run"], "points": points}

    models = []
    for model in reading["models"]:
        text_run = model["turkish_run"]
        turkish = bilmiyorum.get(text_run)
        if turkish is None:
            first_turkish = None if text_run not in hallucination else \
                native("Turkish", "Bilmiyorum", lists["dont_know_runs"][hallucination[text_run]], True)
        elif turkish["subset"]:
            first_turkish = native("Turkish", "Bilmiyorum", lists["english_dont_know_turkish_runs"][turkish["run"]], False)
        else:
            first_turkish = native("Turkish", "Bilmiyorum", lists["dont_know_runs"][turkish["run"]], True)
        word = word_by_text.get(text_run)
        english = english_idk.get(text_run)
        models.append({
            "name": model["name"],
            "text_run": text_run,
            "native": [
                first_turkish or native("Turkish", "Bilmiyorum", None, False),
                native("Turkish", "I don't know", None if word is None else lists["dont_know_word_runs"][word], True),
                native("English", "I don't know", None if english is None else lists["english_dont_know_runs"][english["run"]], False),
            ],
            "curves": [curve("Turkish", lists["runs"][text_run]), curve("English", lists["english_runs"][model["run"]])],
        })
    unmatched = (set(bilmiyorum) | set(english_idk)) - {model["turkish_run"] for model in reading["models"]}
    if unmatched:
        raise ValueError(f"coverage: \"I don't know\" setups of Text tab runs {sorted(unmatched)} have no English reading model")
    return {"questions": total, "definitions": COVERAGE_DEFINITIONS, "models": models}


def english_dont_know_word(reading: dict[str, Any], option_word: dict[str, Any], dont_know_section: dict[str, Any],
                           answers: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    """`english_reading.dont_know_word`, Ümit's request relayed by Zeki #963 (3 November 2026): "I don't know" in both
    languages on the kept questions, so only the language differs. Per English reading model, in that order: the English
    side, its first English run with "I don't know" (`english_reading.dont_know` models or english_only), and the
    Turkish side, the option-word run of its Hallucination tab row (`dont_know_option_word`, asked every Turkish
    question with option F written "I don't know"), each counted on the kept questions (right, wrong, "I don't know",
    invalid, accuracy, attempt rate, non-hallucination rate (None without "I don't know" or wrong answers) and the mean
    probability of the option over the answers that report it); None for a side without a run. Each side must equal its
    source (English: `english_reading.dont_know`; Turkish: `english_reading.coverage`'s Turkish "I don't know" point)
    and add to the kept questions. Where both sides exist, their wrong answers against each other (exact McNemar,
    bm.paired_comparison: first English, second Turkish) with Holm's correction over those models, a family of its own."""
    kept = kept_questions(answers, public)
    total = len(kept)
    idk = reading["dont_know"]
    english_sides = {model["text_run"]: model["english"] for model in idk["models"] + idk.get("english_only", [])
                     if model["text_run"] is not None}
    english_runs = {run["run"]: run for run in answers["english_dont_know_runs"]}
    word_runs = {run["run"]: run for run in answers["dont_know_word_runs"]}
    original = {row["run"]: row["original_run"] for row in dont_know_section["models"]}
    word_by_text: dict[int, int] = {}
    for model in option_word["models"]:
        bilmiyorum = model["bilmiyorum"]["run"]
        if bilmiyorum not in original:
            raise ValueError(f"dont_know_word: option-word run {model['i_dont_know']['run']} ({model['name']}) has no "
                             f"Hallucination tab row with \"Bilmiyorum\" run {bilmiyorum}")
        word_by_text[original[bilmiyorum]] = model["i_dont_know"]["run"]
    coverage = {model["text_run"]: model["native"] for model in reading["coverage"]["models"]}
    keys = ("right", "wrong", "dont_know", "invalid")

    def counted(run: dict[str, Any], label: str) -> dict[str, Any]:
        found = {key: 0 for key in keys}
        shown = []
        for index in kept:
            choice, probabilities = run["choice"][index], run["probabilities"][index]
            if run["correct"][index] is None:
                raise ValueError(f"dont_know_word: {label} run {run['run']} was not asked every kept question")
            if probabilities and DONT_KNOW_LETTER in probabilities:
                shown.append(float(probabilities[DONT_KNOW_LETTER]))
            if choice is None:
                found["invalid"] += 1
            elif choice == DONT_KNOW_LETTER:
                found["dont_know"] += 1
            elif run["correct"][index]:
                found["right"] += 1
            else:
                found["wrong"] += 1
        if sum(found.values()) != total:
            raise ValueError(f"dont_know_word: {label} run {run['run']} counts {sum(found.values())} answers, not {total}")
        return {
            "run": run["run"],
            **found,
            "accuracy": found["right"] / total,
            "attempt_rate": (found["right"] + found["wrong"]) / total,
            "non_hallucination": found["dont_know"] / (found["dont_know"] + found["wrong"]) if found["dont_know"] + found["wrong"] else None,
            "mean_dont_know_probability": sum(shown) / len(shown) if shown else None,
        }

    def wrong(run: dict[str, Any]) -> list[int]:
        return [int(run["choice"][index] not in (None, DONT_KNOW_LETTER) and not run["correct"][index]) for index in kept]

    models, family = [], []
    for model in reading["models"]:
        text_run = model["turkish_run"]
        source = english_sides.get(text_run)
        english = None if source is None else counted(english_runs[source["run"]], f"{model['name']} English")
        if english is not None and {key: english[key] for key in ("run", *keys)} != {key: source[key] for key in ("run", *keys)}:
            raise ValueError(f"dont_know_word: {model['name']} English counts differ from english_reading.dont_know's")
        word = word_by_text.get(text_run)
        turkish = None if word is None else counted(word_runs[word], f"{model['name']} Turkish")
        point = next(item for item in coverage[text_run] if item["language"] == "Turkish" and item["wording"] == "I don't know")
        if (None if turkish is None else [turkish["run"], *(turkish[key] for key in keys)]) != (
                None if point["run"] is None else [point["run"], point["right"], point["wrong"], point["abstained"], point["invalid"]]):
            raise ValueError(f"dont_know_word: {model['name']} Turkish counts differ from english_reading.coverage's "
                             "Turkish \"I don't know\" point")
        paired = None
        if english is not None and turkish is not None:
            test = bm.paired_comparison(wrong(english_runs[english["run"]]), wrong(word_runs[turkish["run"]]))
            paired = {"english_only_wrong": test["first_only"], "turkish_only_wrong": test["second_only"], "p": test["p"], "p_holm": None}
            family.append(paired)
        models.append({"name": model["name"], "text_run": text_run, "english": english, "turkish": turkish, "paired": paired})
    for paired, adjusted in zip(family, bm.holm([paired["p"] for paired in family])):
        paired["p_holm"] = adjusted
    return {"questions": total, "option": option_word["option"], "sentence": option_word["sentence"], "models": models}



# The same number of answers (results.json `dont_know_same_answers`), Ümit's #915 of 3 November 2026 with Zeki's
# corrections (#934): every model's five-option run keeps exactly k answers, its most confident, k being the
# reference's answered count with "I don't know", and each model's wrong answers among them are set against the
# reference's with a paired bootstrap over questions.
SAME_ANSWERS_REFERENCE = "Liquid d1-ultra"
SAME_ANSWERS_RESAMPLES = 10000
SAME_ANSWERS_SEED = 20261103
# The 95% interval: the SAME_ANSWERS_TAIL-th smallest and the SAME_ANSWERS_TAIL-th largest resampled difference.
SAME_ANSWERS_TAIL = 250
SAME_ANSWERS_RULE = (
    "Each model's five-option run (Turkish: every main run on the Text tab, all its setups, each its own Text tab run; "
    "English: its first English run) keeps exactly k answers, k being the reference's answered count (right + wrong) in "
    "its run with \"I don't know\". A run's scored answers (score and choice not null; any other answer is never kept) "
    "are ranked by score, highest first, equal scores by question id ascending (answers.json questions.id), never by "
    "correctness; the first k are kept, and wrong is the number of wrong answers among them, a whole number. "
    "wrong_of_answers = wrong / k; difference = a model's wrong_of_answers - the reference's. A curve has one point "
    "[answered, wrong] per k from 1 to the run's scored answers, under the same selection. Paired bootstrap over "
    f"questions: per family a new random.Random({SAME_ANSWERS_SEED}), Turkish first, English second; "
    f"{SAME_ANSWERS_RESAMPLES:,} resamples, each rng.choices(range(n), k=n) over the family's n question positions in "
    "answers.json order, each question counting as often as it was drawn (k stays fixed). In a resample the answers are "
    "ordered by (score descending, question id ascending), the copies of a question together, and the first k copies "
    "are kept, only as many copies of the boundary question as k needs: wrong = the wrong copies before the boundary "
    "question + (k - the copies before it) * (1 if it is wrong, else 0). d = a model's wrong / k - the reference's. "
    f"Two-sided p = min(1, 2 * min(1 + #{{d <= 0}}, 1 + #{{d >= 0}}) / {SAME_ANSWERS_RESAMPLES + 1:,}); the 95% "
    f"interval is the percentile interval, the {SAME_ANSWERS_TAIL}th smallest and the {SAME_ANSWERS_TAIL}th largest of "
    f"the {SAME_ANSWERS_RESAMPLES:,} resampled d. Holm's correction within each family over the models other than the "
    "reference (Turkish: the other main runs; English: the other English reading models), in the family's order."
)


def ranked_answers(run: dict[str, Any], positions: list[int], ids: list[int], label: str) -> dict[str, list[int]]:
    """A run's scored answers on the questions at `positions` (indices in the answers, whose question ids are `ids`; a
    scored answer has a score and a choice, any other is never kept), ranked by score, highest first, equal scores by
    question id ascending, as kept_wrong needs them: their question positions (indices into `positions`) in that order
    (`order`), 1 for a wrong answer and 0 for a right one in the same order (`wrong`), the positions of the wrong ones
    in the same order (`wrong_order`) and, per place in `order`, the wrong answers before it (`wrong_before`). Stops
    when the run was not asked every question."""
    if any(run["correct"][index] is None for index in positions):
        raise ValueError(f"same answers: {label}'s run {run['run']} was not asked every question")
    ranked = sorted(((-float(run["score"][index]), ids[index], position, int(not run["correct"][index]))
                     for position, index in enumerate(positions)
                     if run["score"][index] is not None and run["choice"][index] is not None))
    wrong = [item[3] for item in ranked]
    return {"order": [item[2] for item in ranked], "wrong": wrong,
            "wrong_order": [item[2] for item in ranked if item[3]],
            "wrong_before": [0, *itertools.accumulate(wrong)][:len(wrong)]}


def kept_wrong(ranked: dict[str, list[int]], weights: list[int], k: int) -> int | None:
    """The wrong answers among a run's first k scored answers (ranked_answers), each answer counting as often as
    `weights` gives its question position, taking only as many copies of the boundary answer as k needs; None when the
    weighted scored answers are fewer than k (SAME_ANSWERS_RULE)."""
    taken = list(itertools.accumulate(map(weights.__getitem__, ranked["order"])))
    if not taken or taken[-1] < k:
        return None
    at = bisect.bisect_left(taken, k)
    before = taken[at - 1] if at else 0
    wrong_before = sum(map(weights.__getitem__, itertools.islice(ranked["wrong_order"], ranked["wrong_before"][at])))
    return wrong_before + (k - before) * ranked["wrong"][at]


def wrong_by_rank(ranked: dict[str, list[int]]) -> str:
    """A run's scored answers in the selection order (ranked_answers) as one character each, "1" wrong and "0" right: the
    curve point at k is (k, the "1"s among the first k characters)."""
    return "".join("1" if wrong else "0" for wrong in ranked["wrong"])


def same_answers_compare(family: str, models: list[dict[str, Any]], ranked: list[dict[str, list[int]]], questions: int,
                         k: int, reference: int) -> None:
    """Fill in each model's wrong answers among its k most confident (`wrong`, `wrong_of_answers`) and, for every model
    but the reference (`models[reference]`), the difference from the reference with its paired bootstrap interval, p and
    Holm's p over the family (SAME_ANSWERS_RULE). Stops when a model has fewer than k scored answers, or a resample
    leaves it fewer."""
    ones = [1] * questions
    for model, found in zip(models, ranked):
        wrong = kept_wrong(found, ones, k)
        if wrong is None:
            raise ValueError(f"same answers, {family}: {model['name']} (Text tab run {model['text_run']})'s five-option run "
                             f"{model['five_option_run']} has {len(found['order'])} scored answers, fewer than k = {k}")
        model["wrong"] = wrong
        model["wrong_of_answers"] = wrong / k
    others = [index for index in range(len(models)) if index != reference]
    differences: dict[int, list[float]] = {index: [] for index in others}
    rng = random.Random(SAME_ANSWERS_SEED)
    for resample in range(SAME_ANSWERS_RESAMPLES):
        weights = [0] * questions
        for position in rng.choices(range(questions), k=questions):
            weights[position] += 1
        rates = []
        for model, found in zip(models, ranked):
            wrong = kept_wrong(found, weights, k)
            if wrong is None:
                raise ValueError(f"same answers, {family}: resample {resample + 1} leaves {model['name']} (Text tab run "
                                 f"{model['text_run']}) fewer than k = {k} weighted scored answers")
            rates.append(wrong / k)
        for index in others:
            differences[index].append(rates[index] - rates[reference])
    for index in others:
        drawn = sorted(differences[index])
        below, above = sum(1 for value in drawn if value <= 0), sum(1 for value in drawn if value >= 0)
        models[index]["difference"] = models[index]["wrong_of_answers"] - models[reference]["wrong_of_answers"]
        models[index]["interval"] = [drawn[SAME_ANSWERS_TAIL - 1], drawn[SAME_ANSWERS_RESAMPLES - SAME_ANSWERS_TAIL]]
        models[index]["p"] = min(1.0, 2 * min(1 + below, 1 + above) / (SAME_ANSWERS_RESAMPLES + 1))
    for index, adjusted in zip(others, bm.holm([models[index]["p"] for index in others])):
        models[index]["p_holm"] = adjusted


def dont_know_same_answers(data: dict[str, Any], answers: dict[str, Any], public: dict[str, Any] | None) -> dict[str, Any]:
    """The same number of answers (results.json `dont_know_same_answers`, SAME_ANSWERS_RULE). Turkish: every main run
    (`runs`, in its order) on the scored questions as its own five-option run, named as the run and keyed by its Text tab
    run, with its answers in the selection order (wrong_by_rank); the Hallucination tab's models also with their runs
    with the option as points ("Bilmiyorum" and the option-word run); k from the reference's option-word run. English:
    the models of `english_reading` on the kept questions, each with its first English run, its answers in the selection
    order and its first English "I don't know" run as its point; k from the reference's English "I don't know" run.
    Stops when a needed section or run is missing, a Hallucination tab model is not a main run or a run's answers do not
    give its published counts."""
    section, option_word = data.get("dont_know"), data.get("dont_know_option_word")
    reading = data.get("english_reading") or {}
    if section is None or option_word is None or public is None or "dont_know" not in reading:
        raise ValueError("same answers: needs `dont_know`, `dont_know_option_word` and `english_reading` with its \"I don't "
                         "know\" comparison")
    ids = answers["questions"]["id"]
    lists = {name: {run["run"]: run for run in answers.get(name, [])} for name in
             ("runs", "english_runs", "dont_know_runs", "dont_know_word_runs", "english_dont_know_runs")}

    def run_in(name: str, run_id: int, label: str) -> dict[str, Any]:
        run = lists[name].get(run_id)
        if run is None:
            raise ValueError(f"same answers: {label} run {run_id} is not among the answers' {name}")
        return run

    def option_point(wording: str, run: dict[str, Any], positions: list[int], published: dict[str, Any], label: str) -> dict[str, Any]:
        if any(run["correct"][index] is None for index in positions):
            raise ValueError(f"same answers: {label} run {run['run']} was not asked every question")
        answered = [index for index in positions if run["choice"][index] not in (None, DONT_KNOW_LETTER)]
        wrong = sum(1 for index in answered if not run["correct"][index])
        if (len(answered) - wrong, wrong) != (published["right"], published["wrong"]):
            raise ValueError(f"same answers: {label} run {run['run']}'s answers do not give its published counts")
        return {"wording": wording, "run": run["run"], "answered": len(answered), "wrong": wrong}

    def k_of(family: str, reference: dict[str, Any], wording: str) -> dict[str, int]:
        point = next((item for item in reference.get("points", []) if item["wording"] == wording), None)
        if point is None:
            raise ValueError(f"same answers, {family}: {SAME_ANSWERS_REFERENCE} has no run with “{wording}” to take k from")
        return {"k": point["answered"], "k_run": point["run"]}

    scored = [index for index, status in enumerate(answers["questions"]["status"]) if status != "excluded"]
    if len(scored) != data["questions"]:
        raise ValueError(f"same answers: {len(scored)} scored questions in the answers, results {data['questions']}")
    words = {model["bilmiyorum"]["run"]: model["i_dont_know"] for model in option_word["models"]}
    not_run = {item["name"] for item in option_word["not_run"]}
    # The decision models' rows: the chat models' runs with the option stay out of this comparison.
    option_rows = {row["original_run"]: row for row in section["models"] if row["group"] == "decision"}
    missing = sorted(set(option_rows) - {run["run"] for run in data["runs"]})
    if missing:
        raise ValueError(f"same answers: the Hallucination tab models of Text tab runs {missing} are not main runs")
    reference_runs = [row["original_run"] for row in section["models"] if row["name"] == SAME_ANSWERS_REFERENCE]
    if len(reference_runs) != 1:
        raise ValueError(f"same answers: needs exactly one Hallucination tab model {SAME_ANSWERS_REFERENCE}, found {len(reference_runs)}")
    turkish, turkish_ranked = [], []
    for main_run in data["runs"]:
        name, text_run = main_run["name"], main_run["run"]
        label = f"{name} (run {text_run})"
        five = run_in("runs", text_run, f"{label}'s five-option")
        ranked = ranked_answers(five, scored, ids, label)
        turkish_ranked.append(ranked)
        entry = {"name": name, "text_run": text_run, "five_option_run": five["run"], "wrong": None, "wrong_of_answers": None,
                 "difference": None, "interval": None, "p": None, "p_holm": None, "wrong_by_rank": wrong_by_rank(ranked)}
        row = option_rows.get(text_run)
        if row is not None:
            points = [option_point("Bilmiyorum", run_in("dont_know_runs", row["run"], f"{label}'s “Bilmiyorum”"), scored, row,
                                   f"{label}'s “Bilmiyorum”")]
            word = words.get(row["run"])
            if word is not None:
                points.append(option_point(OPTION_WORD, run_in("dont_know_word_runs", word["run"], f"{label}'s “{OPTION_WORD}”"),
                                           scored, word, f"{label}'s “{OPTION_WORD}”"))
            elif row["name"] not in not_run:
                raise ValueError(f"same answers: {row['name']} has no run with “{OPTION_WORD}” in `dont_know_option_word`")
            entry["points"] = points
        turkish.append(entry)
    turkish_reference = next(index for index, model in enumerate(turkish) if model["text_run"] == reference_runs[0])
    turkish_k = k_of("Turkish", turkish[turkish_reference], OPTION_WORD)
    same_answers_compare("Turkish", turkish, turkish_ranked, len(scored), turkish_k["k"], turkish_reference)

    kept = kept_questions(answers, public)
    idk = reading["dont_know"]
    # The decision models' English runs with the option, as in Turkish.
    first_english = {model["text_run"]: model["english"] for model in idk["models"] + idk.get("english_only", [])
                     if model["group"] == "decision" and model["text_run"] is not None}
    english, english_ranked = [], []
    for model in reading["models"]:
        name, text_run = model["name"], model["turkish_run"]
        five = run_in("english_runs", model["run"], f"{name}'s first English")
        ranked = ranked_answers(five, kept, ids, name)
        found = first_english.get(text_run)
        points = [] if found is None else [
            option_point(OPTION_WORD, run_in("english_dont_know_runs", found["run"], f"{name}'s English “{OPTION_WORD}”"), kept,
                         found, f"{name}'s English “{OPTION_WORD}”")]
        english_ranked.append(ranked)
        english.append({"name": name, "text_run": text_run, "five_option_run": five["run"], "wrong": None, "wrong_of_answers": None,
                        "difference": None, "interval": None, "p": None, "p_holm": None, "wrong_by_rank": wrong_by_rank(ranked),
                        "points": points})
    english_references = [index for index, model in enumerate(english) if model["name"] == SAME_ANSWERS_REFERENCE]
    if len(english_references) != 1:
        raise ValueError(f"same answers: needs exactly one English reading model {SAME_ANSWERS_REFERENCE}, found {len(english_references)}")
    english_k = k_of("English", english[english_references[0]], OPTION_WORD)
    same_answers_compare("English", english, english_ranked, len(kept), english_k["k"], english_references[0])
    return {
        "reference": SAME_ANSWERS_REFERENCE,
        "resamples": SAME_ANSWERS_RESAMPLES,
        "seed": SAME_ANSWERS_SEED,
        "rule": SAME_ANSWERS_RULE,
        "turkish": {"questions": len(scored), **turkish_k, "k_wording": OPTION_WORD, "models": turkish},
        "english": {"questions": len(kept), **english_k, "k_wording": OPTION_WORD, "models": english},
    }


# The three models Artificial Analysis's Decision Index v1.0 puts level at 65 (page_config `aa_decision_index`), each with
# its Text tab run and its repeat runs (results.json `repeats`, variant null), in that order.
HIGH_CONFIDENCE_FAMILY = (
    ("Liquid d1-ultra", 199, (200, 201, 202, 203)),
    ("SubQ Snap 1.1", 346, (387, 388, 389, 390)),
    ("Elephant-1", 373, (375, 376, 378, 379)),
)
HIGH_CONFIDENCE_THRESHOLD = 0.95
HIGH_CONFIDENCE_CUTOFFS = (0.5, 0.7, 0.8, 0.9, 0.95, 0.99)


def confident(run: dict[str, Any], positions: list[int], cutoff: float) -> tuple[int, list[int]]:
    """The answers of `run` on `positions` whose chosen option has probability at least `cutoff` (an answer without a
    score or without a valid choice never counts): how many, and the positions of those that are not right."""
    counted = [index for index in positions if run["score"][index] is not None and run["choice"][index] is not None
               and run["score"][index] >= cutoff]
    return len(counted), [index for index in counted if run["correct"][index] != 1]


def high_confidence(data: dict[str, Any], answers: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    """`high_confidence`: per main run, on the scored questions, the answers kept at HIGH_CONFIDENCE_THRESHOLD and the
    wrong ones among them; Liquid d1-ultra's repeat runs at the threshold; the three-model family's runs at each of
    HIGH_CONFIDENCE_CUTOFFS, with the check that at every whole percent from 0% to 98% d1-ultra's highest wrong share
    is lower than the lowest of each other model; and d1-ultra's English runs on the English track's kept questions."""
    questions = answers["questions"]
    scored = [index for index, status in enumerate(questions["status"]) if status != "excluded"]
    lists = {run["run"]: run for run in answers["runs"] + answers["repeat_runs"]}
    threshold = HIGH_CONFIDENCE_THRESHOLD
    models = []
    for run in data["runs"]:
        kept, wrong = confident(lists[run["run"]], scored, threshold)
        models.append({"name": run["name"], "text_run": run["run"], "kept": kept, "wrong": len(wrong)})
    repeat_sets = {item["runs"][0]: item["runs"] for item in data["repeats"] if item["variant"] is None}
    family = []
    for name, text_run, repeats in HIGH_CONFIDENCE_FAMILY:
        runs = [text_run, *repeats]
        if repeat_sets.get(text_run) != runs or next(run["name"] for run in data["runs"] if run["run"] == text_run) != name:
            raise ValueError(f"high_confidence: {name}'s runs {runs} are not its repeat set in results.json `repeats`")
        family.append((name, text_run, runs))
    name, text_run, runs = family[0]
    repeats = {"name": name, "text_run": text_run, "runs": []}
    for run in runs[1:]:
        kept, wrong = confident(lists[run], scored, threshold)
        repeats["runs"].append({"run": run, "kept": kept, "wrong": len(wrong)})

    def shares(runs: list[int], cutoff: float, label: str) -> list[float]:
        found = []
        for run in runs:
            kept, wrong = confident(lists[run], scored, cutoff)
            if kept == 0:
                raise ValueError(f"high_confidence: {label} run {run} keeps no answer at {cutoff:.2f}")
            found.append(len(wrong) / kept)
        return found

    holds = all(max(shares(family[0][2], k / 100, family[0][0]))
                < min(min(shares(runs, k / 100, name)) for name, _, runs in family[1:]) for k in range(99))
    cutoff_models = []
    for name, text_run, runs in family:
        rows = []
        for run in runs:
            counts = [confident(lists[run], scored, cutoff) for cutoff in HIGH_CONFIDENCE_CUTOFFS]
            rows.append({"run": run, "kept": [kept for kept, _ in counts], "wrong": [len(wrong) for _, wrong in counts]})
        cutoff_models.append({"name": name, "text_run": text_run, "runs": rows})
    reference = next(model for model in data["english_reading"]["models"] if model["turkish_run"] == family[0][1])
    kept_positions = kept_questions(answers, public)
    english_lists = {run["run"]: run for run in answers["english_runs"]}
    english = {"name": reference["name"], "questions": len(kept_positions), "runs": []}
    for run in reference["runs"]:
        kept, wrong = confident(english_lists[run], kept_positions, threshold)
        english["runs"].append({"run": run, "kept": kept, "wrong": len(wrong),
                                "wrong_questions": sorted(questions["id"][index] for index in wrong)})
    return {
        "threshold": threshold,
        "rule": "An answer counts when its chosen option has probability at least the cutoff; an answer without a score "
                "or without a valid choice never counts; wrong is a counted answer that is not right.",
        "models": models,
        "repeats": [repeats],
        "cutoffs": {"cutoffs": list(HIGH_CONFIDENCE_CUTOFFS), "models": cutoff_models,
                    "check": {"cutoffs": "every whole percent from 0% to 98%", "holds": holds}},
        "english": english,
    }


def against_reference(reading: dict[str, Any], answers: dict[str, Any], public: dict[str, Any],
                      runs: list[dict[str, Any]]) -> dict[str, Any]:
    """`english_reading.against_reference`: the first decision model's first English run (the most accurate decision
    model in English, `english_reading.models` order) against each other decision model's first English run, on the kept
    questions, as right answers in each (exact McNemar, bm.paired_comparison: first the reference), with Holm's correction
    over those models; models in `english_reading.models` order. A decision model by page_config.json's rule
    (Site.decision) on its Text tab run: its provider one of decision_model_providers and its model not one of
    not_decision_models. The chat models' English runs stay out: the comparison is among decision models."""
    kept = kept_questions(answers, public)
    lists = {run["run"]: run for run in answers["english_runs"]}
    decision = decision_setup(runs)

    def right(run: int) -> list[int]:
        return [int(lists[run]["correct"][index] == 1) for index in kept]

    reference = next(model for model in reading["models"] if decision(model))
    reference_name = reference["name"]
    models = []
    for model in reading["models"]:
        if model is reference or not decision(model):
            continue
        test = bm.paired_comparison(right(reference["run"]), right(model["run"]))
        models.append({"name": model["name"], "run": model["run"], "reference_only_right": test["first_only"],
                       "other_only_right": test["second_only"], "p": test["p"], "p_holm": None})
    for model, adjusted in zip(models, bm.holm([model["p"] for model in models])):
        model["p_holm"] = adjusted
    return {"reference": reference_name, "reference_run": reference["run"], "questions": len(kept), "models": models}


def decision_setup(runs: list[dict[str, Any]]) -> Any:
    """Whether an `english_reading` model is a decision model by page_config.json's rule (Site.decision) on its Text tab
    run, or an English-only entry on its own provider and model: its provider one of decision_model_providers and its
    model not one of not_decision_models."""
    config = json.loads(PAGE_CONFIG_PATH.read_text(encoding="utf-8"))
    text_runs = {run["run"]: run for run in runs}

    def decision(model: dict[str, Any]) -> bool:
        run = text_runs[model["turkish_run"]] if "turkish_run" in model else model
        return run["provider"] in config["decision_model_providers"] and run["model"] not in config["not_decision_models"]

    return decision


def decision_score(run: dict[str, Any], kept: list[int]) -> dict[str, Any]:
    """Artificial Analysis's Decision Score formula on one run's asked questions (`kept`): per question
    50 x (1 + c - (p - c)^2), p the probability the run gave the answer it chose and c 1 if that answer is right, else
    0; the run's score is the mean. Returns {"score", "accuracy", "brier", "n", "run"}, Brier the mean of (p - c)^2 over
    the chosen answers (not a multiclass Brier), with score == 50 x (1 + accuracy - Brier) asserted to 1e-9; or
    {"unavailable": reason} when any asked question lacks a chosen answer with a finite probability in [0, 1]: no
    probability is filled in and no subset is scored."""
    missing, invalid = 0, 0
    pairs = []
    for index in kept:
        choice, probabilities = run["choice"][index], run["probabilities"][index]
        p = probabilities.get(choice) if choice is not None and isinstance(probabilities, dict) else None
        if p is None:
            missing += 1
        elif isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
            invalid += 1
        else:
            pairs.append((float(p), 1 if run["correct"][index] == 1 else 0))
    n = len(kept)
    if missing or invalid or not n:
        reasons = ([f"{missing} of {n} answers without a probability for the chosen answer"] if missing else []) + (
            [f"{invalid} of {n} answers with a chosen-answer probability that is not a finite number in [0, 1]"] if invalid else [])
        return {"unavailable": "; ".join(reasons) or "no asked questions"}
    score = sum(50 * (1 + c - (p - c) ** 2) for p, c in pairs) / n
    accuracy = sum(c for _, c in pairs) / n
    brier = sum((p - c) ** 2 for p, c in pairs) / n
    if abs(score - 50 * (1 + accuracy - brier)) > 1e-9:
        raise ValueError(f"decision score: run {run['run']} gives {score}, not 50 x (1 + accuracy - Brier)")
    return {"score": score, "accuracy": accuracy, "brier": brier, "n": n, "run": run["run"]}


def decision_scores(reading: dict[str, Any], answers: dict[str, Any], public: dict[str, Any],
                    runs: list[dict[str, Any]]) -> None:
    """Per decision model of `english_reading.models` and `english_reading.english_only` (decision_setup), on its
    English standard run (the first, the one the English page shows) over the kept questions: `decision_score`
    (decision_score) or `decision_score_unavailable` with the reason. Chat models get neither, nor do the "I don't know"
    runs (`english_reading.dont_know`)."""
    kept = kept_questions(answers, public)
    lists = {run["run"]: run for run in answers["english_runs"]}
    decision = decision_setup(runs)
    for model in reading["models"] + reading.get("english_only", []):
        if not decision(model):
            continue
        found = decision_score(lists[model["run"]], kept)
        if "unavailable" in found:
            model["decision_score_unavailable"] = found["unavailable"]
        else:
            if abs(found["accuracy"] - model["english"]["accuracy"]) > 1e-12:
                raise ValueError(f"decision score: {model['name']}'s accuracy differs from english_reading's")
            model["decision_score"] = found



def export_answers(document: dict[str, Any], data: dict[str, Any], dont_know_section: dict[str, Any] | None = None,
                   english_section: dict[str, Any] | None = None,
                   english_dont_know_section: dict[str, Any] | None = None,
                   option_word_section: dict[str, Any] | None = None,
                   rerun_section: dict[str, Any] | None = None, grounding_runs: frozenset[int] = frozenset()) -> dict[str, Any]:
    """The per-question answers of the runs in `data`, from benchmark_ollama.py --export-answers: the main
    runs, the repeats of each repeated configuration, the runs of each measured routing pipeline, the runs with
    the "I don't know" option (`dont_know_section`), the runs in English (`english_section`), the English "I don't
    know" comparison's runs in English and its Turkish runs on the kept questions (`english_dont_know_section`), the
    option-word check's runs (`option_word_section`), the hosted GLiDE rerun (`rerun_section`) and the web grounding
    test's own runs (`grounding_runs`, web_grounding_runs), which no other list holds. A run's answers on questions it
    was not asked are None, also in `correct`."""
    dataset = next(
        (item for item in document["datasets"] if item["graded_sha256"] == data["dataset"]["graded_sha256"]), None
    )
    if dataset is None:
        raise ValueError("the answers file has no runs graded against the exported question bank")
    main = {run["run"] for run in data["runs"]}
    repeats = {run: item["runs"] for item in data["repeats"] for run in item["runs"] if run not in main}
    # A run can serve several plans (one run alone on the held-out half serves every plan with its configuration),
    # so each run lists every role it has.
    pipelines: dict[int, list[dict[str, Any]]] = {}
    for item in data["pipelines"]:
        measured = item.get("measured")
        if not measured:
            continue
        plan = {"decision": item["decision"], "frontier": item["frontier"], "rule": item["rule"],
                "questions_per_request": item["batch_size"]}
        for role, label in (("pipeline_run", "pipeline"), ("alone_run", "frontier alone")):
            pipelines.setdefault(measured[role], []).append({**plan, "role": label})
        for alternative in measured.get("alternatives", []):
            pipelines.setdefault(alternative["run"], []).append({**plan, "role": "same questions, other configuration"})
    batching = {
        item["run"]: {
            "questions_per_request": item["batch_size"],
            "compared_questions_per_request": item["compared_batch_size"],
            "compared_runs": [other["run"] for other in item["others"]],
        }
        for item in data.get("batching", [])
    }
    by_id = {run["run"]: run for run in dataset["runs"]}
    dont_know_sets = {run: model["runs"] for model in (dont_know_section or {}).get("models", []) for run in model["runs"]}
    english_sets = {run: model["runs"] for model in (english_section or {}).get("models", []) + (english_section or {}).get("english_only", [])
                    for run in model["runs"]}
    idk_models = (english_dont_know_section or {}).get("models", [])
    english_idk_sets = {run: model["english"]["runs"] for model in idk_models + (english_dont_know_section or {}).get("english_only", [])
                        for run in model["english"]["runs"]}
    turkish_idk_sets = {run: model["turkish"]["runs"] for model in idk_models if model["turkish"]["subset"]
                        for run in model["turkish"]["runs"]}
    word_runs = {model["i_dont_know"]["run"] for model in (option_word_section or {}).get("models", [])}
    rerun_runs = {rerun_section["run"]} if rerun_section else set()
    missing = (main | set(repeats) | set(pipelines) | set(batching) | set(dont_know_sets) | set(english_sets)
               | set(english_idk_sets) | set(turkish_idk_sets) | word_runs | rerun_runs | grounding_runs) - set(by_id)
    if missing:
        raise ValueError(f"the answers file lacks runs {sorted(missing)}")
    if grounding_runs & (main | set(repeats) | set(pipelines) | set(batching) | set(dont_know_sets) | set(english_sets)
                         | set(english_idk_sets) | set(turkish_idk_sets) | word_runs | rerun_runs):
        raise ValueError(f"runs {sorted(grounding_runs)}: the web grounding test's pilots and the others are mixed up")
    others = main | set(repeats) | set(pipelines) | set(batching)
    mixed = sorted(run for run in others | set(english_sets) | rerun_runs if by_id[run].get("dont_know"))
    if mixed or any(not by_id[run].get("dont_know") for run in {**dont_know_sets, **english_idk_sets, **turkish_idk_sets}):
        raise ValueError(f"runs {mixed or sorted(dont_know_sets)}: the \"I don't know\" runs and the others are mixed up")
    listed = others | set(dont_know_sets) | set(english_sets) | set(english_idk_sets) | set(turkish_idk_sets)
    mixed = sorted(run for run in listed | rerun_runs if by_id[run].get("dont_know_word"))
    if mixed or any(by_id[run].get("dont_know_word") != "english" or not by_id[run].get("dont_know") for run in word_runs):
        raise ValueError(f"runs {mixed or sorted(word_runs)}: the option-word runs and the others are mixed up")
    mixed = sorted(run for run in listed | word_runs if by_id[run].get("rerun") is not None)
    if mixed or any(by_id[run].get("rerun") is None for run in rerun_runs):
        raise ValueError(f"runs {mixed or sorted(rerun_runs)}: the fresh runs and the others are mixed up")
    mixed = sorted(run for run in others | set(dont_know_sets) | set(turkish_idk_sets) if by_id[run].get("english"))
    if mixed or any(not by_id[run].get("english") for run in {**english_sets, **english_idk_sets}):
        raise ValueError(f"runs {mixed or sorted(english_sets)}: the English runs and the others are mixed up")
    mixed = sorted(set(dont_know_sets) & set(turkish_idk_sets))
    if mixed or any(not by_id[run].get("question_list") for run in turkish_idk_sets):
        raise ValueError(f"runs {mixed or sorted(turkish_idk_sets)}: the Hallucination tab's runs and the Turkish \"I don't "
                         f"know\" runs on the kept questions are mixed up")
    return {
        "schema_version": document["schema_version"],
        "dataset": {"name": dataset["name"], "graded_sha256": dataset["graded_sha256"]},
        "prompts": document["prompts"],
        **({"dont_know_prompts": document["dont_know_prompts"]} if dont_know_sets or turkish_idk_sets else {}),
        # The chat models' prompts with the option, when one of their runs is published.
        **({"dont_know_chat_prompts": document["dont_know_chat_prompts"]}
           if any(not PROVIDERS[by_id[run]["provider"]]["scoring"] for run in dont_know_sets) else {}),
        **({"english_prompts": document["english_prompts"]} if english_sets else {}),
        **({"english_chat_prompts": document["english_chat_prompts"]} if english_sets and "english_chat_prompts" in document else {}),
        **({"english_dont_know_prompts": document["english_dont_know_prompts"]} if english_idk_sets else {}),
        **({"english_dont_know_chat_prompts": document["english_dont_know_chat_prompts"]}
           if any(not PROVIDERS[by_id[run]["provider"]]["scoring"] and by_id[run]["provider"] != "vllm-plain"
                  for run in english_idk_sets) else {}),
        # The plain answer line's prompts (the runner's PLAIN_PROMPTS), when a vllm-plain run is published.
        **({"plain_prompts": document["plain_prompts"]}
           if any(by_id[run]["provider"] == "vllm-plain" for run in {**english_sets, **english_idk_sets}) else {}),
        **({"dont_know_word_prompts": document["dont_know_word_prompts"]} if word_runs else {}),
        "questions": dataset["questions"],
        "runs": [by_id[run] for run in sorted(main)],
        # Each repeat lists the runs of its configuration's repeat set (results.json `repeats`).
        "repeat_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(repeats.items())],
        "pipeline_runs": [{**by_id[run], "pipelines": roles} for run, roles in sorted(pipelines.items())],
        # Runs of a configuration with another number of questions per request (results.json `batching`).
        "batching_runs": [{**by_id[run], "batching": batch} for run, batch in sorted(batching.items())],
        # Runs with the "I don't know" option, each with the runs of its setup (results.json `dont_know`).
        "dont_know_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(dont_know_sets.items())],
        # Runs in English, each with the runs of its setup (results.json `english_reading`).
        "english_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(english_sets.items())],
        # Runs in English with the "I don't know" option, each with the runs of its setup (results.json
        # `english_reading.dont_know`, English side).
        "english_dont_know_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(english_idk_sets.items())],
        # Runs with the "I don't know" option in Turkish on the kept questions, each with the runs of its setup
        # (results.json `english_reading.dont_know`, Turkish side where it is not a Hallucination tab run).
        "english_dont_know_turkish_runs": [{**by_id[run], "repeat_set": runs} for run, runs in sorted(turkish_idk_sets.items())],
        # The option-word check's runs, one per model (results.json `dont_know_option_word`).
        **({"dont_know_word_runs": [by_id[run] for run in sorted(word_runs)]} if word_runs else {}),
        # The hosted GLiDE rerun (results.json `hosted_glide_rerun`).
        **({"rerun_runs": [by_id[run] for run in sorted(rerun_runs)]} if rerun_runs else {}),
        # The web grounding test's own runs (results.json `web_grounding`).
        **({"web_grounding_runs": [by_id[run] for run in sorted(grounding_runs)]} if grounding_runs else {}),
    }


def answer_key(answers: dict[str, Any]) -> dict[str, Any]:
    """The frozen answer key (ANSWER_KEYS) the exported answers are graded against: its version, the bank's SHA-256, the
    key's fingerprint and the excluded questions. Stops when the key is not one of the frozen versions."""
    questions = answers["questions"]
    excluded = [status == "excluded" for status in questions["status"]]
    found = {
        "graded_sha256": answers["dataset"]["graded_sha256"],
        "fingerprint": bm.answer_key_fingerprint(questions["id"], questions["key"], excluded),
    }
    version = next((version for version, frozen in ANSWER_KEYS.items() if frozen == found), None)
    if version is None:
        raise ValueError(
            f"the answers are graded against an answer key that is not frozen (bank {found['graded_sha256'][:8]}, key "
            f"{found['fingerprint'][:8]}): record the change in key-changelog.md and add the key to ANSWER_KEYS as a new version"
        )
    return {"version": version, **found, "excluded": [question for question, out in zip(questions["id"], excluded) if out]}


def published_date(path: Path, data: dict[str, Any], newest: str) -> str:
    """The footer date (`updated`): when results with this content first went out. A re-export whose content equals
    the results.json already at `path` keeps that file's date, so the file and its results_version stay the same; a
    change of content takes the export time (UTC). Never older than `newest`, the newest published run's date."""

    def content(value: dict[str, Any]) -> str:
        plain = json.loads(json.dumps(value, ensure_ascii=False))
        return json.dumps({key: item for key, item in plain.items() if key not in ("results_version", "updated")},
                          ensure_ascii=False, sort_keys=True)

    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if content(previous) == content(data):
            return previous["updated"]
    return max(newest, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def answer_files(answers: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """ANSWER_FILES' files with the sections the answers hold, each file with at least one."""
    held = {name: tuple(section for section in sections if section in answers) for name, sections in ANSWER_FILES.items()}
    return {name: sections for name, sections in held.items() if sections}


def answer_texts(answers: dict[str, Any]) -> dict[str, str]:
    """The answers as written, by file name: answers.json (the header, `files`, each other file's name with its
    sections, then every section kept in it, in the answers' order) and each file of answer_files (the header and its
    sections), compact JSON."""
    files = answer_files(answers)
    moved = {section for sections in files.values() for section in sections}
    main = {**{key: answers[key] for key in ANSWERS_HEADER}, "files": {name: list(sections) for name, sections in files.items()},
            **{key: value for key, value in answers.items() if key not in moved and key not in ANSWERS_HEADER}}
    parts = {"answers.json": main} | {name: {**{key: answers[key] for key in ANSWERS_HEADER},
                                             **{section: answers[section] for section in sections}}
                                      for name, sections in files.items()}
    return {name: json.dumps(part, ensure_ascii=False, separators=(",", ":")) + "\n" for name, part in parts.items()}


def main() -> int:
    args = parse_args()
    try:
        text = args.report.read_text(encoding="utf-8")
        analysis = ANALYSIS_PATTERN.search(text)
        records = [json.loads(match.group(1)) for match in RESULT_PATTERN.finditer(text)]
        # The runs with the "I don't know" option enter only their own section, `dont_know` (full-bank runs in
        # Turkish), the runs in English only theirs, `english_reading`, and the runs with the option in English and
        # their Turkish counterparts on the kept questions only `english_reading.dont_know`. The option-word check's runs
        # enter only `dont_know_option_word` and fresh runs only `hosted_glide_rerun`. The web grounding test's own runs
        # (web_grounding_runs: its pilots and the repeats of its first runs) enter only `web_grounding`.
        by_run = {record["run_id"]: record for record in records}
        grounding = web_grounding_runs(by_run)
        words = [record for record in records if record.get("dont_know_word")]
        reruns = [record for record in records if record.get("rerun") is not None]
        kept = [record for record in records if not record.get("dont_know_word") and record.get("rerun") is None
                and record["run_id"] not in grounding]
        data = export(
            [record for record in kept if not record.get("dont_know") and not record.get("english")],
            json.loads(analysis.group(1)) if analysis else {},
        )
        section = dont_know([record for record in kept if record.get("dont_know") and not record.get("english")], data, by_run)
        english = english_reading([record for record in kept if record.get("english") and not record.get("dont_know")], data)
        english_idk = english_dont_know([record for record in kept if record.get("dont_know")], section, english)
        option_word = dont_know_option_word(words, section, data, by_run)
        rerun = hosted_glide_rerun(reruns, section, data, by_run)
        document = json.loads(args.answers.read_text(encoding="utf-8"))
        answers = export_answers(document, data, section, english, english_idk, option_word, rerun, grounding)
        if section is not None:
            data["dont_know"] = dont_know_answers_part(section, document, answers)
        if option_word is not None:
            data["dont_know_option_word"] = dont_know_option_word_answers_part(option_word, document, answers)
        if rerun is not None:
            data["hosted_glide_rerun"] = hosted_glide_rerun_answers_part(rerun, data["dont_know"], document, answers)
        public = None
        if english is not None:
            public = json.loads(ENGLISH_READING_PATH.read_text(encoding="utf-8"))
            data["english_reading"] = english_reading_answers_part(english, document, answers, public)
            if english_idk is not None:
                data["english_reading"]["dont_know"] = english_dont_know_answers_part(english_idk, document, answers, public)
                data["dont_know_english_option"] = dont_know_english_option(data["english_reading"]["dont_know"])
            data["english_reading"]["coverage"] = english_coverage(data["english_reading"], data.get("dont_know_option_word"),
                                                                   data.get("dont_know"), answers, public)
            if english_idk is not None and option_word is not None and section is not None:
                data["english_reading"]["dont_know_word"] = english_dont_know_word(
                    data["english_reading"], data["dont_know_option_word"], data["dont_know"], answers, public)
        if option_word is not None:
            if rerun is None:
                raise ValueError("vs_confidence: the option-word comparison needs the hosted GLiDE rerun")
            data["dont_know_option_word"]["vs_confidence"] = option_word_vs_confidence(data["dont_know_option_word"], data["dont_know"], answers)
        if section is not None:
            data["dont_know_same_answers"] = dont_know_same_answers(data, answers, public)
        data["answer_key"] = answer_key(answers)
        data["formats"] = formats(data["runs"], answers)
        data["reasoning"] = reasoning(data["runs"], answers)
        data["replay"] = replay(data["runs"], answers)
        refit(data["runs"], answers)
        holm_over_all_pairs(data["paired"], data["runs"], answers)
        if public is None:
            raise ValueError("high_confidence: needs `english_reading`")
        data["high_confidence"] = high_confidence(data, answers, public)
        data["english_reading"]["against_reference"] = against_reference(data["english_reading"], answers, public, data["runs"])
        decision_scores(data["english_reading"], answers, public, data["runs"])
        data["baselines"] = baselines(answers, data["replay"]["decision"])
        if grounding:
            data["web_grounding"] = web_grounding(data, by_run, answers, json.loads(WEB_GROUNDING_PATH.read_text(encoding="utf-8")))
        # The footer date: when results with this content first went out, never older than the newest `updated` of any
        # run a section publishes (every run in the answers file, from the report's records).
        published = {run["run"] for key, runs in answers.items() if key.endswith("runs") for run in runs}
        data["updated"] = published_date(args.output, data, max(by_run[run]["updated"] for run in published))
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    texts = answer_texts(answers)
    for name, text in texts.items():
        if (size := len(text.encode("utf-8"))) > ANSWERS_LIMIT:
            print(f"error: {name} would be {size:,} bytes, over {ANSWERS_LIMIT:,}: move a section of it to a file of its "
                  "own in ANSWER_FILES", file=sys.stderr)
            return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({**data, "results_version": None}, ensure_ascii=False, sort_keys=True)
    data["results_version"] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['runs'])} runs over {data['questions']:,} questions to {args.output}")
    for name, text in texts.items():
        (args.output.parent / name).write_text(text, encoding="utf-8")
    moved = "".join(f"; {', '.join(sections)} to {name}" for name, sections in answer_files(answers).items())
    print(f"Wrote the answers of {len(answers['runs'])} runs to {args.output.parent / 'answers.json'}{moved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
