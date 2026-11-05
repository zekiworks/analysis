#!/usr/bin/env python3
"""PWS-Decisions (Parallel Web Systems' gated benchmark) for the decision models (Ümit #1273) and chat models (#1324) of
the site.

    python3 pws/bench.py probe SETUP...                  one request per setup; what the API says it served
    python3 pws/bench.py run SETUP... [--runs 3] [--workers N]   the public questions, one per request, each run to its file
    python3 pws/bench.py summary [--output pws-decisions.json]

Each question goes out as PWS-Decisions' own request (pws_decisions.build_request: the state, and the choice question
`answer` with its instructions and its choices as criteria), with the site's `model` field and, for Perplexity with
web, `"mode": "web_grounding"`, to the setup's System One service in the site's runner (runner/benchmark_ollama.py:
SYSTEM_ONE, post_json with its retries). OpenAI's Decisions API takes the same parts under its own names: the state as
`input` (a JSON state as an `input_json` part) and the choices as a list of values and descriptions. Each run is a
JSONL file in PWS-Decisions' prediction format (id, prediction, status), scored with its own scorer (`python -m
pws_decisions score`). Per request we record the time from our machine, the retries and the response.
The chat models (CHAT_MODELS) get the same parts in the site's English chat prompts through the runner's asker of their
Text tab run, with or without the maker's own web search (WEB_SEARCH); see CHAT_MODELS.

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
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
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
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261105

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
    # The "I don't know" check (Ümit #1410), kept apart from the scored runs: each question gets the choice
    # DONT_KNOW_VALUE after its own and its instructions the runner's English sentence asking for it when unsure.
    "perplexity-v1.2-idk": {"provider": "perplexity", "model": "pplx-decider-v1.2", "mode": None, "dont_know": True},
    "perplexity-v1.2-web-idk": {"provider": "perplexity", "model": "pplx-decider-v1.2", "mode": "web_grounding",
                                "dont_know": True},
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
    # Base Labs' Mammoth-1 hosted by Baseten (its Model API, not our GPUs): the model of Parallel's Baseten row.
    "mammoth-baseten": {"provider": "baseten", "model": "decision-models/baseten-mammoth-27b-latest", "mode": None,
                        "host": "Baseten", "run": 374},  # run: the site's Mammoth-1 row (on our GPU)
    # The decision models on our GPUs (Ümit via Zeki #1310), each through the runner's System One service of its
    # provider at the address in that provider's variable (BASELABS_URL, CLEF_URL, ...), as gpu-lanes/pws_gpu.py runs them.
    **{name: {"provider": provider, "model": model, "mode": None, "host": "our GPU"} for name, (provider, model) in {
        "elephant-1": ("baselabs", "baselabs/elephant-1"),
        "mammoth-1": ("baselabs", "baselabs/mammoth-1"),
        "decider-v1.2-local": ("pplx-decider", "pplx-decider-v1.2"),
        "decider-flash-v1.2": ("pplx-decider", "pplx-decider-flash-v1.2"),
        "glide-v1.2": ("glide", "glide-v1.2"),
        "d3": ("vllm-sr", "vllm-sr/d3"),
        "d3-ultra": ("d3-server", "vllm-sr/d3-ultra"),
        "drex-max-v1": ("drex-max", "drex-max-v1"),
        "clef": ("clef", "clef"),
        "clef-flash": ("clef", "clef-flash"),
        "cygnet": ("cygnet", "cygnet"),
        "open-jev": ("open-jev", "open-jev-27b-v1.1"),
        "winnow": ("winnow", "winnow-12b"),
        "metask": ("metask", "metask-jev-4b-policy-mix"),
        "d1-2b": ("d1-server", "LiquidAI/d1-2B"),
        "strands": ("strands", "strands-decider-2b"),
        "gliner-decide": ("gliner", "gliner2.5-multi-decide"),
        "laya": ("laya", "laya"),
        "laya-multilingual": ("laya", "laya-multilingual"),
        "onejev": ("onejev", "OmniJev/OneJev-27B"),
    }.items()},
    # Probed only: setups whose API may no longer serve the site's model.
    "perplexity-v1": {"provider": "perplexity", "model": "pplx-decider-v1-27b", "mode": None},
    "perplexity-v1.1": {"provider": "perplexity", "model": "pplx-decider-v1.1-27b", "mode": None},
    "glide": {"provider": "fastino", "model": "fastino/GLiDE", "mode": None},
}
# Baseten's Model API, a System One service: the request and response of the decision models, BASETEN_API_KEY.
BASETEN = runner.SystemOneService("Baseten", "https://inference.baseten.co", key_vars=("BASETEN_API_KEY",),
                                  key_required=True)
SERVICES = {**runner.SYSTEM_ONE, "baseten": BASETEN}
# What Baseten bills for Mammoth-1, the list price the runner gives our own Mammoth runs (input only, output free).
BASETEN_PRICE = replace(runner.PRICES[("baselabs", "baselabs/mammoth-1")], basis="Baseten's Model API list price",
                        applies_to="billed")

# The chat models of the Text tab (Ümit #1324), each once at its best setting there: the results.json run with the
# highest Turkish accuracy for the model (`run`; command_summary checks it), through the access of that run. PWS-Decisions
# has no chat request of its own (its repository sends only decision-API requests; its native-search rows name the
# APIs and tools but publish no prompt), so each question goes out as the benchmark's request in the site's English
# chat prompts (runner.ENGLISH_CHAT, the stated-confidence prompts of the English reading runs, each question headed
# "Question 1:"): the state, the question's instructions and its choices as lettered options ("value: description"),
# one question per request, the reply one letter and a 0-1 confidence in JSON; the letter maps back to the choice's
# value for PWS-Decisions' scorer.
CHAT_MODELS: dict[str, dict[str, Any]] = {
    "gpt-6-astra": {"provider": "openai", "model": "gpt-6-astra", "reasoning": "high", "run": 277},
    "gpt-6.1-sol": {"provider": "openai", "model": "gpt-6.1-sol", "reasoning": "high", "run": 276},
    "gpt-6.1-terra": {"provider": "openai", "model": "gpt-6.1-terra", "reasoning": "high", "run": 275},
    "gpt-6-luna-codex": {"provider": "openai", "model": "gpt-6-luna", "reasoning": "low", "run": 133},
    "gemini-3.8-flash": {"provider": "gemini", "model": "gemini-3.8-flash", "reasoning": "high", "run": 140},
    "gemini-4-argon": {"provider": "gemini", "model": "gemini-4-argon", "reasoning": "low", "run": 557},
    "claude-fable-5-1": {"provider": "claude", "model": "claude-fable-5-1", "reasoning": "high", "run": 310},
    "claude-opus-5-5": {"provider": "claude", "model": "claude-opus-5-5", "reasoning": "high", "run": 278},
    "claude-sonnet-5-5": {"provider": "claude", "model": "claude-sonnet-5-5", "reasoning": "high", "run": 193},
    "grok-4.7": {"provider": "xai", "model": "grok-4.7", "reasoning": "high", "run": 311},
    # Pinned to the endpoint of the Text tab run without fallbacks, as runner/run_openrouter_kimi_low.sh and
    # run_openrouter_glm.sh ask them.
    "kimi-k3.1-pro": {"provider": "openrouter-chat", "model": "moonshotai/kimi-k3.1-pro", "reasoning": "low", "run": 320,
                      "order": "moonshotai/mxfp4", "require_parameters": False},
    "glm-5.3": {"provider": "openrouter-chat", "model": "z-ai/glm-5.3", "reasoning": "low", "run": 314,
                "order": "fireworks", "require_parameters": True},
    # On our GPUs (Ümit #1349, #1351), each at the setting of its Text tab row, through that row's server (vLLM, or
    # SGLang for DeepSeek, its chat API at the URL in `url_var`, as the runner/run_*.sh scripts take it) and its
    # provider: `vllm` asks for the letter and reads its token probabilities. DeepSeek-V4.1-Flash 1017 runs as both of
    # its Text tab rows, reasoning on (its best) and off (`extra`). They run after the GPU decision models.
    "gemma-4-31b": {"provider": "vllm", "model": "gemma-4-31B-it", "reasoning": "off", "run": 119, "thinking": False,
                    "url_var": "GEMMA_URL"},
    "qwen3.8-27b": {"provider": "vllm", "model": "qwen38-27b-bf16", "reasoning": "low", "run": 318, "thinking": "low",
                    "url_var": "QWEN_URL"},
    "qwen3-14b": {"provider": "vllm", "model": "qwen3-14b", "reasoning": "off", "run": 131, "thinking": False,
                  "url_var": "QWEN3_14B_URL"},
    "erk-14b": {"provider": "vllm", "model": "erk-14b", "reasoning": "off", "run": 132, "thinking": False,
                "url_var": "ERK_URL"},
    "deepseek-v4.1-flash-1017": {"provider": "vllm", "model": "deepseek-v4.1-flash-1017", "reasoning": "on", "run": 585,
                                 "thinking": True, "url_var": "DEEPSEEK_URL", "priced": True},
    "deepseek-v4.1-flash-1017-off": {"provider": "vllm", "model": "deepseek-v4.1-flash-1017", "reasoning": "off",
                                     "run": 558, "thinking": False, "url_var": "DEEPSEEK_URL", "extra": True,
                                     "priced": True},
    # Through the makers' APIs with a key, billed (Ümit #1408, #1409): the settings of the CLI rows (same model, effort,
    # prompts, schema, choice order, one question per request), labelled API next to the CLI rows; `text_provider` names
    # the provider of the Text tab row. The Anthropic rows wait for an ANTHROPIC_API_KEY.
    "gpt-6.1-sol-api": {"provider": "openai-api", "text_provider": "openai", "model": "gpt-6.1-sol", "reasoning": "high",
                        "run": 276, "access": "OpenAI Responses API (API key)"},
    "claude-fable-5-1-api": {"provider": "claude-api", "text_provider": "claude", "model": "claude-fable-5-1",
                             "reasoning": "high", "run": 310, "access": "Anthropic Messages API (API key)"},
    "claude-opus-5-5-api": {"provider": "claude-api", "text_provider": "claude", "model": "claude-opus-5-5",
                            "reasoning": "high", "run": 278, "access": "Anthropic Messages API (API key)"},
    "claude-sonnet-5-5-api": {"provider": "claude-api", "text_provider": "claude", "model": "claude-sonnet-5-5",
                              "reasoning": "high", "run": 193, "access": "Anthropic Messages API (API key)"},
}
SELF_HOSTED = ("vllm",)
CHAT_TIMEOUT = 900.0  # the API Text tab runs' limit per request
SELF_HOSTED_TIMEOUT = 3600.0  # the self-hosted Text tab runs' limit per request
# Requests in flight per chat run: 4, as most Text tab chat runs had (concurrency 4); 2 for Codex, whose ChatGPT
# subscription answered 429 to eight requests in flight (two lanes of four) on 5 November 2026.
CHAT_WORKERS = {"openai": 2}
CHAT_PROMPTS = replace(runner.ENGLISH_CHAT, question_header="Question {index}:")
# Each maker's own web search, as its API or CLI documents it (read 5 November 2026), and its list price per search.
# OpenAI and Anthropic through the subscription CLIs of their Text tab runs, priced at the API's tool fee as their tokens
# are; Gemini through its API key; xAI through the SuperGrok token of its Text tab run.
WEB_SEARCH: dict[str, dict[str, Any]] = {
    "openai": {
        "how": 'Codex CLI with web_search="live" (live web access; the default "cached" uses an OpenAI-kept index)',
        "doc": "https://developers.openai.com/codex/config-reference", "read": "2026-11-05",
        "price_source": "https://developers.openai.com/api/docs/pricing", "per_search": 0.010,
        "price_note": "$10 per 1,000 web search calls; search content tokens billed at the model's rates",
    },
    "claude": {
        "how": "Claude Code CLI with its WebSearch tool (the Claude API's web search tool)",
        "doc": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool", "read": "2026-11-05",
        "price_source": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool",
        "per_search": 0.010, "price_note": "$10 per 1,000 searches plus the tokens of the search results",
    },
    "gemini": {
        "how": "Gemini API generateContent with the google_search tool (Grounding with Google Search)",
        "doc": "https://ai.google.dev/gemini-api/docs/google-search", "read": "2026-11-05",
        "price_source": "https://ai.google.dev/gemini-api/docs/google-search", "per_search": 0.014,
        "price_note": "Gemini 3 and newer: $14 per 1,000 search queries the model runs, after 5,000 free a month "
                      "(not deducted here)",
    },
    "xai": {
        "how": "xAI Responses API with the web_search tool",
        "doc": "https://docs.x.ai/developers/tools/web-search", "read": "2026-11-05",
        "price_source": "https://docs.x.ai/developers/pricing", "per_search": 0.005,
        "price_note": "$5 per 1,000 web_search calls plus tokens",
    },
    "openai-api": {
        "how": 'Responses API with the {"type": "web_search"} tool (live web access, external_web_access left at its '
               "default, true)",
        "doc": "https://developers.openai.com/api/docs/guides/tools-web-search", "read": "2026-11-05",
        "price_source": "https://developers.openai.com/api/docs/pricing", "per_search": 0.010,
        "price_note": "$10 per 1,000 web search calls; search content tokens billed at the model's rates",
    },
    "claude-api": {
        "how": 'Messages API with the {"type": "web_search_20260318", "name": "web_search"} tool, no max_uses; a '
               "pause_turn reply is continued",
        "doc": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool", "read": "2026-11-05",
        "price_source": "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool",
        "per_search": 0.010, "price_note": "$10 per 1,000 searches plus the tokens of the search results",
    },
}
SETUPS.update({name: {**setup, "mode": None, "group": "chat", "web": False,
                      "workers": CHAT_WORKERS.get(setup["provider"], 4)}
               for name, setup in CHAT_MODELS.items()})
SETUPS.update({f"{name}-web": {**setup, "mode": None, "group": "chat", "web": True,
                               "workers": CHAT_WORKERS.get(setup["provider"], 4)}
               for name, setup in CHAT_MODELS.items() if setup["provider"] in WEB_SEARCH})
CHAT_WEB_NOT_RUN = ("Kimi K3.1 Pro and GLM-5.3 run through OpenRouter, whose web search is OpenRouter's own plugin, not "
                    "the makers' search; they run without web only.")
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
# differed from our runs 373 and 374 by up to these amounts, so they are not shown to be the same weights: Baseten's
# Mammoth-1 is its own setup (mammoth-baseten, Baseten-hosted), and our GPU setups wait for the GPU queue.
BASETEN_CHECK = {"questions": 20, "date": "2026-11-05",
                 "baselabs/elephant-1": {"largest_gap": 0.283, "same_choice": 20},
                 "baselabs/mammoth-1": {"largest_gap": 0.082, "same_choice": 19}}
# Setups of the site that wait: Parallel's own API, and the decision models on our GPUs (found from results.json).
PENDING_PARALLEL = "Parallel's own Decisions API: no key on this machine yet."
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


class ThreadStderr(io.TextIOBase):
    """sys.stderr that a worker thread can capture on its own (the runner prints its retries there): each thread's writes
    go to its buffer while it has one, the rest to the real stderr."""

    def __init__(self, real: Any) -> None:
        self.real = real
        self.local = threading.local()

    def write(self, text: str) -> int:
        buffer = getattr(self.local, "buffer", None)
        return (buffer or self.real).write(text)

    def flush(self) -> None:
        self.real.flush()

    @contextlib.contextmanager
    def capture(self) -> Iterator[io.StringIO]:
        self.local.buffer = io.StringIO()
        try:
            yield self.local.buffer
        finally:
            self.local.buffer = None


STDERR = ThreadStderr(sys.stderr)
sys.stderr = STDERR


def payload(setup: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    """The setup's request for one question: PWS-Decisions' request with the site's model field (and mode), or for
    OpenAI's Decisions API the same parts in its format, as the runner's ask_jev sends them."""
    service = SERVICES[setup["provider"]]
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


def chat_question(question: dict[str, Any]) -> runner.Question:
    """A PWS-Decisions question as the runner's chat providers ask one (CHAT_MODELS): the state (JSON as indented
    JSON), the instructions, and the choices as options lettered from A, each "value: description"."""
    if len(question["choices"]) > 26:
        raise ValueError("more choices than letters")
    state = question["state"] if isinstance(question["state"], str) else json.dumps(question["state"], ensure_ascii=False,
                                                                                    indent=1)
    options = tuple(runner.Option(chr(ord("A") + index), f"{choice['value']}: {choice['description']}")
                    for index, choice in enumerate(question["choices"]))
    listed = "\n".join(f"{option.label}. {option.text}" for option in options)
    prompt = f"State:\n{state.strip()}\n\n{question['instructions'].strip()}\n\n{runner.ENGLISH_OPTIONS_HEADING}{listed}"
    return runner.Question(0, "", "", "", "", "", "", "", prompt, options, "", 0, False, None)


def chat_access(setup: dict[str, Any]) -> dict[str, Any]:
    """What a chat setup's requests need, found once per run: the CLI's path (signed in to the subscription), the
    Gemini, OpenAI or Anthropic key, or our server's URL."""
    if setup["provider"] == "openai":
        return {"bin": runner.require_chatgpt_oauth("codex")}
    if setup["provider"] == "claude":
        return {"bin": runner.require_claude_subscription("claude")}
    if setup["provider"] == "gemini":
        return {"key": runner.gemini_api_key()}
    for provider, variable in (("openai-api", "OPENAI_API_KEY"), ("claude-api", "ANTHROPIC_API_KEY")):
        if setup["provider"] == provider:
            key = os.environ.get(variable, "").strip()
            if not key:
                sys.exit(f"{setup['model']} through the API needs {variable}")
            return {"key": key}
    if setup["provider"] in SELF_HOSTED:
        url = os.environ.get(setup["url_var"], "").strip()
        if not url:
            sys.exit(f"set {setup['url_var']} to the {setup['model']} server, as http://HOST:PORT")
        return {"url": url}
    return {}


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"  # the version the Messages API docs send (read 5 November 2026)
CLAUDE_API_MAX_TOKENS = 64000  # a hard limit on thinking plus reply; the effort docs ask for a large one at high effort
CLAUDE_API_CONTINUATIONS = 5  # pause_turn replies continued per request, at most


def ask_openai_api(key: str, model: str, batch: list[runner.Question], effort: str, web: bool) -> tuple[list[str | None], str]:
    """The Codex CLI row's request through OpenAI's Responses API: the same system prompt (as `instructions`), user
    message and answer schema (as text.format json_schema, strict), reasoning.effort set, not stored; with `web`, the
    web_search tool. Stored like the xAI provider's response (whose usage has the same shape)."""
    payload: dict[str, Any] = {
        "model": model, "instructions": CHAT_PROMPTS.confidence_system,
        "input": [{"role": "user", "content": runner.make_prompt(batch, CHAT_PROMPTS.confidence_instruction, CHAT_PROMPTS)}],
        "store": False, "reasoning": {"effort": effort},
        "text": {"format": {"type": "json_schema", "name": "answers", "schema": runner.confidence_schema(batch),
                            "strict": True}},
    }
    if web:
        payload["tools"] = [{"type": "web_search"}]
    result, _ = runner.post_json(OPENAI_RESPONSES_URL, payload, {"Content-Type": "application/json",
                                                                 "Authorization": f"Bearer {key}"}, CHAT_TIMEOUT, None,
                                 "OpenAI")
    text = "".join(part.get("text", "") for item in (result.get("output") or []) if item.get("type") == "message"
                   for part in (item.get("content") or []) if part.get("type") == "output_text")
    answers = runner.json_answers(text) if result.get("status") == "completed" else None
    predictions, per_question = runner.confidence_answers(answers, batch)
    return predictions, json.dumps({"answers": per_question, "response": result}, ensure_ascii=False)


def ask_claude_api(key: str, model: str, batch: list[runner.Question], effort: str, web: bool) -> tuple[list[str | None], str]:
    """The Claude Code row's request through Anthropic's Messages API: the same system prompt, user message and answer
    schema (output_config.format json_schema), output_config.effort set; with `web`, the web search tool, continuing a
    pause_turn reply. Stored like the Claude Code provider's response (`output` with the summed usage), so the runner's
    token counting applies."""
    payload: dict[str, Any] = {
        "model": model, "max_tokens": CLAUDE_API_MAX_TOKENS, "system": CHAT_PROMPTS.confidence_system,
        "messages": [{"role": "user",
                      "content": runner.make_prompt(batch, CHAT_PROMPTS.confidence_instruction, CHAT_PROMPTS)}],
        "output_config": {"effort": effort,
                          "format": {"type": "json_schema", "schema": runner.confidence_schema(batch)}},
    }
    if web:
        payload["tools"] = [{"type": "web_search_20260318", "name": "web_search"}]
    headers = {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    usage: dict[str, Any] = {}
    replies = []
    for _ in range(CLAUDE_API_CONTINUATIONS + 1):
        result, _ = runner.post_json(ANTHROPIC_MESSAGES_URL, payload, headers, CHAT_TIMEOUT, None, "Anthropic")
        replies.append(result)
        for kind, value in (result.get("usage") or {}).items():
            if isinstance(value, int):
                usage[kind] = usage.get(kind, 0) + value
            elif kind == "server_tool_use":
                tools = usage.setdefault(kind, {})
                for name, count in value.items():
                    tools[name] = tools.get(name, 0) + int(count or 0)
        if result.get("stop_reason") != "pause_turn":
            break
        payload["messages"] = [*payload["messages"], {"role": "assistant", "content": result.get("content") or []}]
    text = "".join(part.get("text", "") for part in (replies[-1].get("content") or []) if part.get("type") == "text")
    predictions, per_question = runner.confidence_answers(runner.json_answers(text), batch)
    output = {"usage": usage, "stop_reason": replies[-1].get("stop_reason"), "model": replies[-1].get("model"),
              "replies": replies}
    return predictions, json.dumps({"provider": "claude-api", "answers": per_question, "output": output},
                                   ensure_ascii=False)


def ask_chat(setup: dict[str, Any], question: dict[str, Any], access: dict[str, Any]) -> dict[str, Any]:
    """One request of a chat setup through the runner's asker of its Text tab run (with the maker's web search when the
    setup has web): PWS-Decisions' prediction record (the chosen letter's choice value) plus the time, the retries and
    the stored response."""
    asked = [chat_question(question)]
    provider, model, level, web = setup["provider"], setup["model"], setup["reasoning"], setup["web"]
    record: dict[str, Any] = {"id": question["id"], "prediction": None, "status": "error", "utc": utc_now()}
    started = time.perf_counter()
    with STDERR.capture() as warnings:
        try:
            if provider == "openai":
                letters, stored = runner.ask_openai(access["bin"], model, asked, CHAT_TIMEOUT, level, None, CHAT_PROMPTS, web)
            elif provider == "claude":
                letters, stored = runner.ask_claude(access["bin"], model, asked, CHAT_TIMEOUT, level, None, CHAT_PROMPTS, web)
            elif provider == "gemini":
                letters, stored = runner.ask_gemini(access["key"], model, asked, CHAT_TIMEOUT, level, None, CHAT_PROMPTS, web)
            elif provider == "openai-api":
                letters, stored = ask_openai_api(access["key"], model, asked, level, web)
            elif provider == "claude-api":
                letters, stored = ask_claude_api(access["key"], model, asked, level, web)
            elif provider == "xai":
                letters, stored = runner.ask_xai(model, asked, CHAT_TIMEOUT, level, None, CHAT_PROMPTS, web)
            elif provider in SELF_HOSTED:
                letters, stored = runner.ask_vllm(access["url"], model, asked, SELF_HOSTED_TIMEOUT, 0, setup["thinking"],
                                                  None, CHAT_PROMPTS)
            else:
                letters, stored = runner.ask_openrouter_chat(model, asked, CHAT_TIMEOUT, level, setup["order"],
                                                             setup["require_parameters"], False, None, CHAT_PROMPTS)
            record["request_seconds"] = time.perf_counter() - started
            record["response"] = json.loads(stored)
            record["letter"] = letters[0]
            values = {option.label: choice["value"] for option, choice in zip(asked[0].options, question["choices"])}
            stand_in = claude_stand_in(record["response"], model) if provider == "claude" else None
            if stand_in:
                # Not the asked model's answer: count it as that model's refusal and say who answered.
                record.update(status="refusal", answered_by=stand_in)
            elif letters[0] in values:
                record.update(prediction=values[letters[0]], status="success")
            else:
                record["status"] = "invalid_response"
        except RuntimeError as exc:
            record["request_seconds"] = time.perf_counter() - started
            record["error"] = str(exc)[:500]
    record["retries"] = warnings.getvalue().count("retry ")
    if web and "response" in record:
        record["searches"] = searches(provider, record["response"])
    return record


def searches(provider: str, stored: dict[str, Any]) -> int | None:
    """The web searches behind one chat answer as its response reports them, or None where it reports none."""
    if provider == "openai":
        return sum(event.get("type") == "item.completed" and (event.get("item") or {}).get("type") == "web_search"
                   for event in stored.get("events") or [])
    if provider in ("claude", "claude-api"):
        usage = (stored.get("output") or {}).get("usage") or {}
        found = (usage.get("server_tool_use") or {}).get("web_search_requests")
        models = (stored.get("output") or {}).get("modelUsage") or {}
        counted = [entry.get("webSearchRequests") for entry in models.values() if isinstance(entry, dict)]
        if any(isinstance(count, int) for count in counted):
            return sum(count or 0 for count in counted)
        return found if isinstance(found, int) else None
    if provider == "gemini":
        # Grounding metadata lists the queries; Gemini 3.8 Flash and Gemini 4 Argon return none with a JSON reply
        # (5 November 2026), though their prompt tokens show search results: then the count is unknown.
        candidates = (stored.get("response") or {}).get("candidates") or [{}]
        metadata = candidates[0].get("groundingMetadata")
        return None if metadata is None else len(metadata.get("webSearchQueries") or [])
    if provider in ("xai", "openai-api"):
        usage = (stored.get("response") or {}).get("usage") or {}
        details = usage.get("server_side_tool_usage_details") or {}
        if isinstance(details.get("web_search_calls"), int):
            return details["web_search_calls"]
        return sum(item.get("type") == "web_search_call" for item in (stored.get("response") or {}).get("output") or [])
    return None


def setup_key(setup: dict[str, Any]) -> str | None:
    service = SERVICES[setup["provider"]]
    for name in service.key_vars:
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    if service.key_required:
        sys.exit(f"{service.name} needs {service.key_help()}")
    return None


DONT_KNOW_VALUE = runner.ENGLISH_DONT_KNOW_OPTION  # "I don't know", value and description, as the runner's --dont-know


def dont_know_question(question: dict[str, Any]) -> dict[str, Any]:
    """The question with the "I don't know" choice after its own, and the runner's English sentence asking for it
    (ENGLISH_DONT_KNOW_SENTENCE) after its instructions."""
    return {**question, "instructions": f"{question['instructions'].rstrip()} {runner.ENGLISH_DONT_KNOW_SENTENCE}",
            "choices": [*question["choices"], {"value": DONT_KNOW_VALUE, "description": DONT_KNOW_VALUE}]}


def ask(setup: dict[str, Any], question: dict[str, Any], key: str | None) -> dict[str, Any]:
    """One request: PWS-Decisions' prediction record plus the time from our machine, the retries and the response."""
    if setup.get("dont_know"):
        question = dont_know_question(question)
    service = SERVICES[setup["provider"]]
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    record: dict[str, Any] = {"id": question["id"], "prediction": None, "status": "error", "utc": utc_now()}
    started = time.perf_counter()
    with STDERR.capture() as warnings:
        try:
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


def asker(setup: dict[str, Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """The setup's one-question request, its access found once."""
    if setup.get("group") == "chat":
        access = chat_access(setup)
        return lambda question: ask_chat(setup, question, access)
    key = setup_key(setup)
    return lambda question: ask(setup, question, key)


def run_file(name: str, number: int) -> Path:
    return RUNS / name / f"run-{number}.jsonl"


def questions(args: argparse.Namespace) -> list[dict[str, Any]]:
    return load_questions(args.data / "public-100.jsonl")


def command_probe(args: argparse.Namespace) -> None:
    """One request per setup (a text state and, when --json-state, a JSON state): status, served model, usage keys,
    whether it returned probabilities, and for a chat setup its searches and the keys of its stored response (kept in
    --runs-dir/probe). No question text is printed."""
    rows = questions(args)
    picks = [rows[0]] + ([next(row for row in rows if not isinstance(row["state"], str))] if args.json_state else [])
    for name in args.setups:
        setup = SETUPS[name]
        ask_one = asker(setup)
        for question in picks:
            record = ask_one(question)
            response = record.get("response") or {}
            if setup.get("group") == "chat":
                kept = RUNS / "probe" / f"{name}.json"
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
                print(json.dumps({"setup": name, "status": record["status"], "seconds": round(record["request_seconds"], 3),
                                  "retries": record["retries"], "searches": record.get("searches"),
                                  "response_keys": sorted(response), "error": record.get("error", "")[:300]}), flush=True)
                continue
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
    """Each setup's runs one after another, each run's questions over the setup's parallel requests (`workers`, or
    --workers; one question per request), each answer appended to the run's file as it comes; a run resumes from the
    questions its file lacks. With --retry-errors, the run's failed requests (status error: a subscription's 429 after
    the CLI's own retries, say) move to run-N.errors.jsonl and are asked again. A stored Claude Code answer that another
    model gave in the asked model's place (claude_stand_in; earlier records lack the check) becomes a refusal."""
    rows = questions(args)
    for name in args.setups:
        setup = SETUPS[name]
        ask_one = asker(setup)
        workers = args.workers or setup.get("workers", 1)
        for number in range(1, args.runs + 1):
            path = run_file(name, number)
            path.parent.mkdir(parents=True, exist_ok=True)
            kept = read_jsonl(path) if path.exists() else []
            changed = False
            if setup["provider"] == "claude" and setup.get("group") == "chat":
                for row in kept:
                    stand_in = claude_stand_in(row["response"], setup["model"]) if "response" in row else None
                    if stand_in and row["status"] != "refusal":
                        row.update(prediction=None, status="refusal", answered_by=stand_in)
                        changed = True
            if args.retry_errors and any(row["status"] == "error" for row in kept):
                with path.with_suffix(".errors.jsonl").open("a", encoding="utf-8") as errors:
                    errors.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in kept if row["status"] == "error")
                kept = [row for row in kept if row["status"] != "error"]
                changed = True
            if changed:
                path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept), encoding="utf-8")
            done = {row["id"] for row in kept}
            with path.open("a", encoding="utf-8") as output, ThreadPoolExecutor(workers) as pool:
                pending = [pool.submit(ask_one, question) for question in rows if question["id"] not in done]
                for future in as_completed(pending):
                    output.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
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


def setup_price(setup: dict[str, Any]) -> runner.Price | None:
    """The list price of a setup's requests: Baseten's for Mammoth there, none for our GPU chat setups but those marked
    `priced` (Zeki #1357: DeepSeek-V4.1-Flash 1017 at DeepSeek's list price), else the runner's for its Text tab run."""
    if setup["provider"] == "baseten":
        return BASETEN_PRICE
    if setup["provider"] in SELF_HOSTED and not setup.get("priced"):
        return None
    return runner.run_price(setup.get("text_provider", setup["provider"]), setup["model"], setup["mode"])


# The API rows' responses in the shape of a runner provider's: OpenAI's Responses API as xAI's, the Messages API's
# summed usage as Claude Code's.
USAGE_SHAPES = {"openai-api": "xai", "claude-api": "claude"}


def bootstrap_interval(args: argparse.Namespace, paths: list[Path]) -> dict[str, Any]:
    """A 95% percentile bootstrap interval of the accuracy over the questions: each question scores the share of the
    runs that answered it right; the questions are resampled with replacement BOOTSTRAP_RESAMPLES times (fixed seed)."""
    gold = {row["id"]: row["answer"] for row in read_jsonl(args.data / "public-100-answers.jsonl")}
    runs = [{row["id"]: row for row in read_jsonl(path)} for path in paths]
    scores = [statistics.mean(run.get(key, {}).get("status") == "success" and run[key].get("prediction") == answer
                              for run in runs) for key, answer in gold.items()]
    draw = random.Random(BOOTSTRAP_SEED)
    means = sorted(statistics.fmean(draw.choices(scores, k=len(scores))) for _ in range(BOOTSTRAP_RESAMPLES))
    return {"low": means[int(0.025 * BOOTSTRAP_RESAMPLES)], "high": means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]}


# Models Claude Code calls besides the asked one, at Anthropic's API list price (read 5 November 2026; 1-hour cache
# writes at 2x input, 5-minute ones at 1.25x, cache reads at 0.1x): Claude Haiku 5.5, which its WebSearch tool runs on
# (prompts up to 100,000 tokens), and Claude Opus 4.8, which answers in Fable's place after Fable's safety stops.
CLAUDE_CODE_PRICES = {
    "claude-haiku-5-5": runner.Price("Anthropic's API list price", runner.ANTHROPIC_PRICING, "2026-11-05", 0.10, 0.50,
                                     cached_input=0.01, cache_write=0.125, cache_write_1h=0.20),
    "claude-opus-4-8": runner.Price("Anthropic's API list price", runner.ANTHROPIC_PRICING, "2026-11-05", 5.00, 25.00,
                                    cached_input=0.50, cache_write=6.25, cache_write_1h=10.00),
}


def claude_stand_in(response: dict[str, Any], model: str) -> str | None:
    """The model that answered for `model` in a Claude Code response, when Claude Code's safety stops passed the
    question on (the asked model wrote nothing, another one the answer); None when the asked model answered."""
    output = response.get("output") or {}
    used = output.get("modelUsage") or {}
    if not output.get("safety_stops") or (used.get(model) or {}).get("outputTokens"):
        return None
    others = sorted((name for name, entry in used.items() if name != model and entry.get("outputTokens")),
                    key=lambda name: name == "claude-haiku-5-5")  # Haiku runs the WebSearch tool, not answers
    return others[0] if others else None


def claude_tokens(response: dict[str, Any]) -> dict[str, dict[str, int]]:
    """The tokens of a Claude Code answer by the model that used them (its modelUsage: the asked model, and any other
    model Claude Code called for it), in the runner's token kinds."""
    tokens = {}
    for model, used in ((response.get("output") or {}).get("modelUsage") or {}).items():
        read = int(used.get("cacheReadInputTokens") or 0)
        hour = int(used.get("cacheCreationEphemeral1hInputTokens") or 0)
        written = int(used.get("cacheCreationInputTokens") or 0)
        tokens[model] = {"input_tokens": int(used.get("inputTokens") or 0) + read + written,
                         "output_tokens": int(used.get("outputTokens") or 0), "cached_input_tokens": read,
                         "cache_write_input_tokens": written - hour, "cache_write_1h_input_tokens": hour}
    return tokens


def request_usage(setup: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, int], float | None, float | None]:
    """One answered request's tokens, its cost at list prices (search fees included; None without a price) and the
    chosen answer's probability, or for a chat model its stated confidence."""
    provider = setup["provider"]
    if setup.get("group") == "chat":
        shape = USAGE_SHAPES.get(provider, provider)
        _, score = runner.answer_usage(shape, 0, json.dumps(row["response"]))
        if provider == "claude":
            by_model = claude_tokens(row["response"])
            prices = {**{model: price for (maker, model), price in runner.PRICES.items() if maker == "claude"},
                      **CLAUDE_CODE_PRICES}
            missing = [model for model in by_model if model not in prices]
            if missing:
                sys.exit(f"no Anthropic list price for {missing}")
            cost = sum(prices[model].cost(counted) for model, counted in by_model.items())
            tokens: dict[str, int] = {}
            for counted in by_model.values():
                for kind, value in counted.items():
                    tokens[kind] = tokens.get(kind, 0) + value
        else:
            tokens, _ = runner.answer_usage(shape, 0, json.dumps(row["response"]))
            if provider == "openai-api":  # the Responses API also reports cache writes, billed at their own rate
                details = ((row["response"].get("response") or {}).get("usage") or {}).get("input_tokens_details") or {}
                tokens["cache_write_input_tokens"] = int(details.get("cache_write_tokens") or 0)
            price = setup_price(setup)
            cost = None if price is None else price.cost(tokens)
        found = searches(provider, row["response"]) if setup["web"] else 0
        if found and cost is not None:
            # Searches the response does not report add a fee left out here (the setup's cost is then a lower bound).
            cost += WEB_SEARCH[provider]["per_search"] * found
        return tokens, cost, score
    # A System One response; Baseten's is in the same format as TypeSafe's.
    stored = json.dumps({"request_id": row.get("request_id"), "response": row["response"]})
    tokens, probability = runner.answer_usage("jev" if provider == "baseten" else provider, 0, stored)
    price = setup_price(setup)
    return tokens, None if price is None else price.cost(tokens, 1), probability


def served_models(setup: dict[str, Any], answered: list[dict[str, Any]]) -> list[str]:
    """The models the responses name: a System One response's or chat API's `model` (Gemini: modelVersion), Claude
    Code's modelUsage; the Codex CLI names none."""
    names: set[str] = set()
    for row in answered:
        response = row["response"]
        if not isinstance(response, dict):
            continue
        if setup.get("group") != "chat":
            names.add(str(response.get("model") or ""))
        elif setup["provider"] == "claude":
            names.update((response.get("output") or {}).get("modelUsage") or {})
        else:
            inner = response.get("response") or response.get("output") or response
            names.add(str(inner.get("model") or inner.get("modelVersion") or ""))
    return sorted(names - {""})


def run_totals(args: argparse.Namespace, setup: dict[str, Any], path: Path, sure: float) -> dict[str, Any]:
    """One run's totals: their scorer's count, request times of the requests that returned a response, tokens and cost
    at list prices (search fees included), with web the searches, and with probabilities (or a chat model's stated
    confidence) the chosen answer's mean and the sure answers."""
    rows = read_jsonl(path)
    scored = score(args, path)
    gold = {row["id"]: row["answer"] for row in read_jsonl(args.data / "public-100-answers.jsonl")}
    answered = [row for row in rows if "response" in row]
    tokens: dict[str, int] = {}
    chosen: list[tuple[float, bool]] = []
    costs: list[float | None] = []
    for row in answered:
        counted, cost, probability = request_usage(setup, row)
        costs.append(cost)
        for kind, value in counted.items():
            tokens[kind] = tokens.get(kind, 0) + int(value or 0)
        if row["status"] == "success" and probability is not None:
            chosen.append((probability, row["prediction"] == gold[row["id"]]))
    # Requests without a response: their tokens are unknown; a priced request adds its per-request fee.
    price = setup_price(setup)
    fees = 0.0 if price is None or setup.get("group") == "chat" else price.cost({}, len(rows) - len(answered))
    cost = None if any(value is None for value in costs) else sum(costs) + fees
    seconds = [row["request_seconds"] for row in answered]
    times = [row["utc"] for row in rows]
    totals: dict[str, Any] = {
        "started": min(times), "ended": max(times), "questions": scored["n"], "correct": scored["correct"],
        "accuracy": scored["correct"] / scored["n"], "missing": scored["missing"], "not_success": scored["non_success"],
        "errors": sum(row["status"] == "error" for row in rows), "retries": sum(row.get("retries", 0) for row in rows),
        "median_request_seconds": statistics.median(seconds), "p95_request_seconds": nearest_rank(seconds, PERCENTILE),
        "input_tokens": tokens.get("input_tokens", 0), "output_tokens": tokens.get("output_tokens", 0),
        "cost_usd": cost, "cost_per_million_questions": None if cost is None else cost / scored["n"] * 1_000_000,
        "served_models": served_models(setup, answered),
        # Requests asked again after the run's first pass (--retry-errors), their failed rows kept in run-N.errors.jsonl.
        "re_asked": len(read_jsonl(errors)) if (errors := path.with_suffix(".errors.jsonl")).exists() else 0,
    }
    if setup["provider"] == "claude" and setup.get("group") == "chat":
        if any(claude_stand_in(row["response"], setup["model"]) and row["status"] != "refusal" for row in answered):
            sys.exit(f"{path}: answers by a stand-in model are not marked yet; resume the run (bench.py run) first")
        totals["stand_in_refusals"] = sum("answered_by" in row for row in rows)
    if setup.get("web") and setup.get("group") == "chat":
        counts = [searches(setup["provider"], row["response"]) for row in answered]
        if any(count is None for count in counts):
            totals["searches"] = {"reported": False, "total": None, "per_question": None, "questions_with_search": None}
        else:
            totals["searches"] = {"reported": True, "total": sum(counts), "per_question": sum(counts) / scored["n"],
                                  "questions_with_search": sum(count > 0 for count in counts)}
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
    text_runs = {run["run"]: run for run in results["runs"]}

    def best_run(provider: str, model: str) -> dict[str, Any]:
        """The model's Text tab run with the highest Turkish accuracy."""
        own = [run for run in results["runs"] if run["provider"] == provider and run["model"] == model]
        return max(own, key=lambda run: run["correct"] / run["answered_questions"])

    def dont_know_arm(name: str) -> dict[str, Any] | None:
        """The "I don't know" check's totals of one setup's three runs: right, wrong, "I don't know" and failed
        requests (errors, refusals, invalid replies) per run, and from them accuracy, answered share, wrong of the
        answers and non-hallucination ("I don't know" of "I don't know" plus wrong)."""
        paths = [run_file(name, number) for number in range(1, args.runs + 1)]
        if not all(path.exists() for path in paths):
            return None
        gold = {row["id"]: row["answer"] for row in read_jsonl(args.data / "public-100-answers.jsonl")}
        per_run = []
        for path in paths:
            stored = read_jsonl(path)
            if {row["id"] for row in stored} != set(gold):
                return None
            answered = [row for row in stored if row["status"] == "success" and row["prediction"] != DONT_KNOW_VALUE]
            right = sum(row["prediction"] == gold[row["id"]] for row in answered)
            wrong = len(answered) - right
            unsure = sum(row["status"] == "success" and row["prediction"] == DONT_KNOW_VALUE for row in stored)
            per_run.append({
                "started": min(row["utc"] for row in stored), "questions": len(stored), "right": right, "wrong": wrong,
                "dont_know": unsure, "errors": len(stored) - len(answered) - unsure, "accuracy": right / len(stored),
                "answered": (right + wrong) / len(stored), "wrong_of_answers": wrong / (right + wrong) if answered else None,
                "non_hallucination": unsure / (unsure + wrong) if unsure + wrong else None,
            })
        arm = {"perplexity_mode": SETUPS[name]["mode"], "runs": per_run}
        for key in ("right", "wrong", "dont_know", "errors", "accuracy", "answered", "wrong_of_answers", "non_hallucination"):
            arm[key] = spread([run[key] for run in per_run])
        return arm

    setups, total_cost, dates, unfinished = [], 0.0, set(), []
    for name, setup in SETUPS.items():
        if setup.get("dont_know"):
            continue
        paths = [run_file(name, number) for number in range(1, args.runs + 1)]
        if not all(path.exists() for path in paths):
            continue
        # A setup counts once its three runs hold every question; a chat setup also once no request failed (failed
        # requests are asked again with --retry-errors) and no Claude Code stand-in answer is left unmarked. Until then
        # it is listed as unfinished.
        stored = [read_jsonl(path) for path in paths]
        chat = setup.get("group") == "chat"
        unmarked = chat and setup["provider"] == "claude" and any(
            "response" in row and row["status"] != "refusal" and claude_stand_in(row["response"], setup["model"])
            for run_rows in stored for row in run_rows)
        failed = chat and any(row["status"] == "error" for run_rows in stored for row in run_rows)
        if unmarked or failed or any({row["id"] for row in run_rows} != {row["id"] for row in rows} for run_rows in stored):
            unfinished.append(name)
            continue
        runs = [run_totals(args, setup, path, sure) for path in paths]
        price = setup_price(setup)
        total_cost += sum(run["cost_usd"] or 0.0 for run in runs)
        dates.update(run[edge][:10] for run in runs for edge in ("started", "ended"))
        item = {
            "provider": setup["provider"], "model": setup["model"], "perplexity_mode": setup["mode"],
            "request_model": setup.get("request_model", setup["model"]),
            "group": "chat" if chat else "decision", "web": setup["web"] if chat else setup["mode"] is not None,
            "price": None if price is None else {"basis": price.basis, "source": price.source, "date": price.date,
                                                 "input_per_million": price.input, "per_request": price.per_request},
            "runs": runs,
            "accuracy": spread([run["accuracy"] for run in runs]),
            "accuracy_ci95": bootstrap_interval(args, paths),
            "re_asked": [run["re_asked"] for run in runs],
            "median_request_seconds": spread([run["median_request_seconds"] for run in runs]),
            "p95_request_seconds": spread([run["p95_request_seconds"] for run in runs]),
            "cost_per_million_questions": spread([run["cost_per_million_questions"] for run in runs]),
        }
        if "host" in setup or setup["provider"] in SELF_HOSTED:
            item["host"] = setup.get("host", "our GPU")
        if "run" in setup:
            item["run"] = setup["run"]
        if chat:
            text_run = text_runs[setup["run"]]
            best = best_run(setup.get("text_provider", setup["provider"]), setup["model"])
            if text_run["reasoning"] != setup["reasoning"] or (best["run"] != setup["run"] and not setup.get("extra")):
                sys.exit(f"{name}: the best Text tab run of {setup['model']} is {best['run']} ({best['reasoning']})")
            api = setup["provider"] in USAGE_SHAPES
            item.update(run=setup["run"], reasoning=setup["reasoning"], access=setup.get("access", text_run["access"]),
                        interface="API" if api else "CLI" if setup["provider"] in ("openai", "claude") else None,
                        billing="api" if api else text_run["billing"],
                        workers=setup["workers"], best_setting=not setup.get("extra"),
                        confidence_kind="probability" if setup["provider"] in SELF_HOSTED else "stated")
            if price is not None:
                item["price"].update(output_per_million=price.output, applies_to=price.applies_to, per_search=0.0)
            if setup["web"]:
                search = WEB_SEARCH[setup["provider"]]
                reported = all(run["searches"]["reported"] for run in runs)
                item["price"].update(per_search=search["per_search"], searches="counted" if reported else "not reported",
                                     search_source=search["price_source"], search_note=search["price_note"])
                # Without reported searches the cost covers the tokens only: a lower bound, each search query per
                # question adding per_search x 1M to the cost per 1M questions.
                item["cost_lower_bound"] = not reported
                item["searches_per_question"] = spread([run["searches"]["per_question"] for run in runs])
                item["questions_with_search"] = spread([run["searches"]["questions_with_search"] for run in runs])
        elif all("confidence" in run for run in runs):
            item["confidence_kind"] = "probability"
        if all("confidence" in run for run in runs):
            item["mean_chosen_probability"] = spread([run["confidence"]["mean_chosen_probability"] for run in runs])
            item["sure_wrong"] = spread([run["confidence"]["sure_wrong"] for run in runs])
            item["sure"] = spread([run["confidence"]["sure"] for run in runs])
        setups.append(item)
    # Our GPU setups of the chat models without three runs yet: they wait for the GPU queue.
    pending_chat = [{"setup": name, "provider": setup["provider"], "model": setup["model"], "run": setup["run"],
                     "reasoning": setup["reasoning"], "url_var": setup["url_var"], "host": "our GPU",
                     "group": "chat", "web": False, "name": text_runs[setup["run"]]["name"]}
                    for name, setup in SETUPS.items() if setup["provider"] in SELF_HOSTED
                    and not all(run_file(name, number).exists() for number in range(1, args.runs + 1))]
    dont_know = {"off": dont_know_arm("perplexity-v1.2-idk"), "on": dont_know_arm("perplexity-v1.2-web-idk")}
    document = {
        "name": "PWS-Decisions", "version": manifest["version"], "questions_sha256": manifest["questions_sha256"],
        "questions": len(rows), "language": "English",
        "random_accuracy": statistics.mean(1 / len(row["choices"]) for row in rows),
        "choice_counts": {str(k): sum(len(row["choices"]) == k for row in rows)
                          for k in sorted({len(row["choices"]) for row in rows})},
        "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED, "unit": "question",
                      "percentiles": [2.5, 97.5], "score": "a question's mean correctness over the setup's runs"},
        "harness": "https://github.com/parallel-web/pws-decisions-benchmark",
        "runs_per_setup": args.runs, "one_question_per_request": True, "timeout_seconds": TIMEOUT,
        "retries": {"statuses": "408, 425, 429 and 5xx, and transport failures", "max": runner.JEV_MAX_RETRIES},
        "percentile": PERCENTILE, "sure_threshold": sure, "dates": sorted(dates), "run_cost_usd": total_cost,
        "setups": setups, "not_run": NOT_RUN, "baseten_check": BASETEN_CHECK,
        "pending": {"parallel": PENDING_PARALLEL, "gpu": PENDING_GPU, "chat_gpu": pending_chat, "chat_unfinished": unfinished},
        "chat": {
            "request": "PWS-Decisions has no chat request of its own, so each question goes out as the benchmark's "
                       "request (the state, the question's instructions, its choices as lettered options) in the "
                       "site's English chat prompts, one question per request; the reply is one letter and a 0-1 "
                       "confidence in JSON, scored with PWS-Decisions' scorer.",
            "system_prompt": CHAT_PROMPTS.confidence_system, "instruction": CHAT_PROMPTS.confidence_instruction,
            "timeout_seconds": CHAT_TIMEOUT, "setting": "each model's best Text tab setting (highest Turkish accuracy)",
            "web_search": WEB_SEARCH, "web_not_run": CHAT_WEB_NOT_RUN,
        },
        "openai_web": OPENAI_WEB, "reported": REPORTED,
        # Attempts set aside whole (never merged into a run), with PWS-Decisions' scorer result of each run file.
        "failed_attempts": [
            {"setup": score_file.parent.parent.name, "attempt": score_file.parent.name,
             "run": int(score_file.name.split("-")[1].split(".")[0]), "rows": len(read_jsonl(score_file.with_name(
                 score_file.name.replace(".score.json", ".jsonl")))),
             "errors": sum(row["status"] == "error" for row in read_jsonl(score_file.with_name(
                 score_file.name.replace(".score.json", ".jsonl")))),
             "correct": json.loads(score_file.read_text(encoding="utf-8"))["correct"]}
            for score_file in sorted(RUNS.glob("*/attempt-*/run-*.score.json"))],
        "dont_know": {"option": DONT_KNOW_VALUE, "sentence": runner.ENGLISH_DONT_KNOW_SENTENCE, "provider": "perplexity",
                      "model": "pplx-decider-v1.2", "dates": sorted({run["started"][:10] for arm in dont_know.values()
                                                                     if arm for run in arm["runs"]}), **dont_know},
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
    run.add_argument("--workers", type=int, help="requests in flight per run (default: the setup's workers, else 1)")
    run.add_argument("--retry-errors", action="store_true", help="ask the run's failed requests again")
    summary = commands.add_parser("summary")
    summary.add_argument("--output", type=Path, default=OUTPUT)
    for command in (run, summary):
        command.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    {"probe": command_probe, "run": command_run, "summary": command_summary}[args.command](args)


if __name__ == "__main__":
    main()
