#!/usr/bin/env python3
"""Evaluate local Ollama, OpenAI through Codex, Claude through Claude Code, TypeSafe Jev, self-hosted Open-Jev and Laya, Liquid AI d1, Perplexity Decisions, or vLLM-served models against the Turkish question bank."""

from __future__ import annotations

import argparse
import base64
import bisect
import fcntl
import functools
import hashlib
import itertools
import json
import math
import os
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import benchmark_metrics as bm

DEFAULT_DATA = Path("questions.sqlite")
DEFAULT_REPORT = Path("benchmark-results.md")
DEFAULT_DATABASE = Path("benchmark-results.sqlite")
DEFAULT_OLLAMA_URL = "http://192.168.1.126:11434"


@dataclass(frozen=True)
class SystemOneService:
    """A server of TypeSafe's System One request and response format."""

    name: str  # named in messages
    url: str  # default base URL
    path: str = "/v1/systemone"
    # Environment variables holding the API key, checked in order. Without key_required, requests
    # carry no key when none is set.
    key_vars: tuple[str, ...] = ()
    key_required: bool = False
    # False when the server has one checkpoint and no `model` field; the model argument is then only
    # the report label.
    model_field: bool = True
    # Response header holding the server's request ID, stored with each answer.
    request_id_header: str | None = None

    def key_help(self) -> str:
        if not self.key_vars:
            return "no key"
        names = " or ".join(self.key_vars)
        return f"key from {names}" if self.key_required else f"key from {names} if set"


SYSTEM_ONE = {
    "jev": SystemOneService(
        "TypeSafe",
        "https://api.typesafe.ai",
        key_vars=("JEV_API_KEY", "TYPESAFE_API_KEY"),
        key_required=True,
        request_id_header="x-typesafe-request-id",
    ),
    "open-jev": SystemOneService("Open-Jev", "http://192.168.1.126:8791", model_field=False),
    "liquid": SystemOneService(
        "Liquid AI", "https://api.liquid.ai/decisions", key_vars=("LIQUID_API_KEY",), key_required=True
    ),
    # ~/code/laya/server.py, which wants LAYA_API_KEY only when it was started with one.
    "laya": SystemOneService(
        "Laya", "http://127.0.0.1:18080", path="/v1/predict", key_vars=("LAYA_API_KEY",), model_field=False
    ),
    # Perplexity's Decisions API, which takes the same request and returns the same answers.
    "perplexity": SystemOneService(
        "Perplexity",
        "https://api.perplexity.ai",
        path="/v1/decisions",
        key_vars=("PERPLEXITY_API_KEY",),
        key_required=True,
        request_id_header="x-request-id",
    ),
    # ~/code/gliner2.5-multi-v1/server.py: GLiNER2.5 Multi's classifier behind the System One format.
    "gliner": SystemOneService("GLiNER", "http://127.0.0.1:18090"),
    # ~/code/clef/server.py: Cloudflare's Clef, whose release code answers System One requests.
    "clef": SystemOneService("Clef", "http://127.0.0.1:18091"),
    # ~/code/metask-jev/server.py: Metask-Jev-4B scored by its vendor's code behind the System One format.
    "metask": SystemOneService("Metask-Jev", "http://127.0.0.1:18092"),
    # ~/code/cygnet/shim/decision_server.py: Cygnet's own server, reading Gemma 4 12B IT on vLLM by option letter.
    "cygnet": SystemOneService("Cygnet", "http://127.0.0.1:18093"),
    # EldanRing/winnow-inference: Winnow-12B's own llama.cpp-based server, in its Docker image.
    "winnow": SystemOneService("Winnow", "http://127.0.0.1:8091"),
    # Fastino's hosted GLiDE (model fastino/GLiDE), which takes the same request and returns the same answers.
    "fastino": SystemOneService("Fastino", "https://api.fastino.ai", key_vars=("FASTINO_API_KEY",), key_required=True),
}
SYSTEM_ONE_PROVIDERS = tuple(SYSTEM_ONE)
# Self-hosted open-weight System One models with no published price to apply.
UNPRICED_SYSTEM_ONE = ("laya", "gliner", "clef", "metask", "cygnet", "winnow")
# TypeSafe's published System One price: input tokens only, output free
# (https://typesafe.ai/blog/introducing-system-one-models-and-jev). Reports apply the same
# rate to the input tokens Open-Jev's API reports, so the two providers compare directly.
TYPESAFE_USD_PER_INPUT_TOKEN = 0.042 / 1_000_000
# Liquid AI publishes no d1 price; d1:free is its free d1 model. Other Liquid models get no cost.
LIQUID_USD_PER_INPUT_TOKEN = {"d1:free": 0.0}
# Perplexity's published Decisions API price: input tokens only, output free
# (https://docs.perplexity.ai/docs/decisions/quickstart#pricing).
PERPLEXITY_USD_PER_INPUT_TOKEN = 0.04 / 1_000_000
# Fastino's published GLiDE price: input tokens only, output free (https://docs.fastino.ai/pricing).
FASTINO_USD_PER_INPUT_TOKEN = 0.15 / 1_000_000
DEFAULT_VLLM_URL = "http://192.168.1.126:8888"
# vllm sends the Ollama models' prompt, several questions per request; vllm-yes-no, vllm-verbal and
# vllm-vote send one question per request.
VLLM_PROVIDERS = ("vllm", "vllm-yes-no", "vllm-verbal", "vllm-vote")
SINGLE_QUESTION_PROVIDERS = (*SYSTEM_ONE_PROVIDERS, "vllm-yes-no", "vllm-verbal", "vllm-vote")
# --provider vllm-vote: the vllm-verbal request sampled VOTE_SAMPLES times with the instruct sampling
# settings of Qwen's model card (~/code/Qwen3.8-27B-DGX-Spark-RTX-6000/README.md). The answer is the
# most frequent letter and its score the share of samples that chose it.
VOTE_SAMPLES = 10
VOTE_SAMPLING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}
VOTE_PROVIDERS = ("vllm-vote",)
# Output tokens allowed per question for --provider vllm; enough for the letters, and a stop for a
# reply that runs on.
VLLM_TOKENS_PER_ANSWER = 32
# Output tokens allowed per request with --vllm-thinking: the thinking and the reply together.
VLLM_THINKING_MAX_TOKENS = 65536
# Alternatives vLLM and SGLang return for each generated token (top_logprobs). At an answer letter they are
# the other option letters, so 10 cover a question's five options, with room for duplicate spellings.
VLLM_TOP_LOGPROBS = 10
# Price set for Qwen served by vLLM, applied to the prompt and completion tokens vLLM reports.
VLLM_USD_PER_INPUT_TOKEN = 0.40 / 1_000_000
VLLM_USD_PER_OUTPUT_TOKEN = 2.40 / 1_000_000
# Providers whose answers carry option probabilities; the report scores each answer by the probability
# of the chosen option. vllm reads them from the token probabilities of the answer letters it writes.
# The other providers with a confidence state it with each answer.
PROBABILITY_PROVIDERS = (*SYSTEM_ONE_PROVIDERS, "vllm-yes-no", "vllm")
STATED_CONFIDENCE_PROVIDERS = ("vllm-verbal", "claude", "openai", "gemini")
READING_UNITS = range(1, 7)  # units 1–6 test reading, units 7–20 grammar
# Within-unit shuffles behind the p-value of the decision-model doubt analysis.
DOUBT_SHUFFLES = 200
# Paired comparisons made besides each run against the next one in the ranking: each side is a provider,
# or a (provider, model) pair when the provider serves several models.
PAIRED_CONFIGURATIONS: tuple[tuple[str | tuple[str, str], str | tuple[str, str]], ...] = (
    ("open-jev", "vllm-yes-no"),
    ("perplexity", "jev"),
    (("fastino", "fastino/GLiDE"), "perplexity"),
    (("vllm", "gemma-4-31B-it"), ("fastino", "fastino/GLiDE")),
)
# Tied groups: two runs over the same questions count as told apart when their exact paired test, Holm-
# adjusted over every pair of those runs, falls below this level.
TIE_ALPHA = 0.05
# Cascade simulation: a decision model answers when confident and passes the rest to a frontier run,
# given as (provider, model, thinking).
CASCADE_DECISION_PROVIDERS = ("perplexity", "jev", "open-jev", "liquid", "clef", "metask", "cygnet", "winnow", "fastino")
CASCADE_FRONTIER_RUNS = (
    ("openai", "gpt-6-astra", "low"),
    ("claude", "claude-opus-5-5", "low"),
    ("claude", "claude-sonnet-5-5", "high"),
)
# Question groups the report scores separately, by label. Missing markup: the question text refers to
# underlined or numbered words without marking them (see missing_markup).
GROUP_LABELS = {
    "all": "All questions",
    "reading": "Reading (1–6)",
    "grammar": "Grammar (7–20)",
    "missing_markup": "Missing markup",
    "marked": "Other",
    "without_suspect": "Without suspect",
}
# Groups whose AUROC also gets a bootstrap interval: the parts the page compares, meaning and form.
PART_GROUPS = ("reading", "grammar")
# A run's fields in the report that describe the run itself; the rest are metrics, recomputed whenever
# the report is written.
RESULT_FIELDS = (
    "run_key", "run_id", "model", "provider", "dataset", "database", "dataset_sha256", "selection_sha256",
    "eligible_total", "evaluated", "correct", "invalid", "skipped", "batch_size", "thinking", "num_ctx",
    "image_input", "shuffle_options", "replace_key_text", "categories", "updated", "concurrency", "as_run",
    "repeat", "question_list",
)
JEV_INSTRUCTIONS = "Which option is the correct answer to this Turkish multiple-choice question?"
# Open-Jev's per-option prompt (jev/api.py candidate_prompts), used by --provider vllm-yes-no.
YES_NO_PROMPT = (
    "Context:\n{state}\n\nQuestion: {question}\nProposed answer: {label}: {text}\n"
    "Is this proposed answer correct? Answer Yes or No."
)
ANSWER_SYSTEM_PROMPT = (
    "You are taking a Turkish multiple-choice benchmark. Select exactly one supplied option per question. "
    "Do not explain."
)
VERBAL_SYSTEM_PROMPT = (
    "You are taking a Turkish multiple-choice benchmark. Select exactly one supplied option and "
    "state your confidence in it. Do not explain."
)
VERBAL_INSTRUCTION = (
    "Aşağıdaki çoktan seçmeli soruyu yanıtlayın. Açıklama yapmadan, doğru seçeneğin harfini ve "
    "cevabınızın doğru olduğundan ne kadar emin olduğunuzu gösteren 0 ile 1 arasında bir güven "
    "puanını belirtilen JSON biçiminde birlikte döndürün."
)
ANSWER_INSTRUCTION = (
    "Aşağıdaki çoktan seçmeli soruların her birini yanıtlayın. Açıklama yapmadan, "
    "her soru için yalnızca doğru seçeneğin harfini belirtilen JSON biçiminde döndürün. "
    "Ekli görseller, soru metinlerindeki ekli görsel numarasıyla aynı sıradadır."
)
CONFIDENCE_INSTRUCTION = (
    "Aşağıdaki çoktan seçmeli soruların her birini yanıtlayın. Açıklama yapmadan, her soru için "
    "doğru seçeneğin harfini ve cevabınızın doğru olduğundan ne kadar emin olduğunuzu gösteren 0 ile "
    "1 arasında bir güven puanını belirtilen JSON biçiminde birlikte döndürün."
)
CONFIDENCE_SYSTEM_PROMPT = (
    "You are taking a Turkish multiple-choice benchmark. Select exactly one supplied option per "
    "question and state your confidence in each answer. Do not explain."
)
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Anthropic API list prices in USD per 1M input / output tokens. Claude runs use the subscription;
# the report prices every prompt token, including Claude Code's cache reads and writes, as input.
CLAUDE_USD_PER_MTOK = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}
# Gemini API list prices in USD per 1M input / output tokens, thinking billed as output: Gemini 3.8 Flash's
# introductory price through 31 December 2026 (https://ai.google.dev/gemini-api/docs/latest-model).
GEMINI_USD_PER_MTOK = {"gemini-3.8-flash": (0.75, 3.75), "gemini-3.1-pro-preview": (2.00, 12.00)}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
# The API key: GEMINI_API_KEY, else this file.
GEMINI_KEY_FILE = Path("~/.config/gemini/key")
# OpenAI API list prices in USD per 1M input / cached input / cache write / output tokens, for prompts
# up to 272K tokens. OpenAI runs use the ChatGPT subscription; Codex reports cached input and cache
# writes as parts of the input.
OPENAI_USD_PER_MTOK = {
    "gpt-6-astra": (10.00, 1.00, 12.50, 50.00),
    "gpt-6.1-sol": (2.00, 0.10, 2.50, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
}
# Codex features whose tools the OpenAI provider turns off: shell and exec, goals, apps and plugins
# with their MCP resources, image viewing and generation, and sleep. Web search is turned off through
# the `web_search` setting. Checked with Codex 0.159.0.
CODEX_DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "goals",
    "apps",
    "plugins",
    "remote_plugin",
    "tool_suggest",
    "skill_search",
    "view_image",
    "image_generation",
    "sleep_tool",
)
# 425: a model still warming up (Fastino); 408, 429 and 5xx: the usual transient failures.
JEV_RETRY_STATUSES = frozenset({408, 425, 429, *range(500, 600)})
JEV_MAX_RETRIES = 5
# The Claude Code CLI's transient failure when parallel processes refresh their shared sign-in at once.
CLAUDE_REFRESH_FAILURE = "Failed to refresh OAuth token"
CLAUDE_REFRESH_RETRIES = 5
CLAUDE_REFRESH_DELAY = 60.0
RESULT_PATTERN = re.compile(r"<!-- benchmark-result: (\{.*?\}) -->")
# A question that refers to underlined or numbered words its text doesn't mark lost that markup in
# extraction.
UNDERLINE_REFERENCE = re.compile(r"alt[ıi] ?çizili", re.IGNORECASE)
NUMBERED_REFERENCE = re.compile(r"numaralan", re.IGNORECASE)
# An inline number for a numbered word or sentence: "(I)", "(3)", or "II." / "IV)" after a non-letter.
INLINE_NUMBER = re.compile(
    r"\((?:I|II|III|IV|V|1|2|3|4|5)\)|(?<![A-Za-zÇĞİÖŞÜçğıöşü])(?:I|II|III|IV|V)\s*[.)]"
)
ROMAN_OPTIONS = (["I", "II"], ["I.", "II."])
OPTIONS_HEADING = "Seçenekler:\n"
# Option shapes for the --replace-key-text table. Single numerals and numeral combinations come in a
# fixed order that the replaced option breaks, so a model can find the key's slot by position.
SINGLE_NUMERAL_OPTION = re.compile(r"(?:I|II|III|IV|V|VI|VII|VIII|IX|X|[1-9])\.?")
NUMERAL_COMBINATION_OPTION = re.compile(
    r"(?:Yalnız )?(?:I|II|III|IV|V|VI|VII|VIII)(?:(?:, | ve | - )(?:I|II|III|IV|V|VI|VII|VIII))*\.?"
)
OPTION_SHAPES = {"numerals": "Single numerals", "combinations": "Numeral combinations", "text": "Text options"}
# What a --replace-key-text answer picked: the original key letter, its twin, another option, or nothing valid.
KEY_REPLACEMENT_PICKS = ("key", "twin", "other", "invalid")


@dataclass(frozen=True)
class Option:
    label: str
    text: str


@dataclass(frozen=True)
class Question:
    question_id: int
    category: str
    unit_number: str
    unit_title: str
    section_title: str
    test_type: str
    test_number: str
    question_number: str
    prompt: str
    options: tuple[Option, ...]
    answer: str
    source_page: int
    requires_image: bool
    image_path: Path | None
    status: str | None = None  # verified, suspect, excluded, or None when not checked by hand
    original_labels: tuple[str, ...] = ()  # each option's letter in the question bank, when shuffled
    twin: str | None = None  # with --replace-key-text, the wrong option whose text the key's option shows

    def original_label(self, label: str | None) -> str | None:
        """The question bank's letter for an option letter as shown to the model."""
        if label is None or not self.original_labels:
            return label
        return dict(zip((option.label for option in self.options), self.original_labels)).get(label)


@dataclass(frozen=True)
class Selection:
    questions: tuple[Question, ...]
    source_total: int
    filtered_total: int
    eligible_total: int
    skipped: dict[str, int]


@dataclass(frozen=True)
class RunIdentity:
    run_id: int
    run_key: str
    dataset_sha256: str
    selection_sha256: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the extracted Turkish multiple-choice benchmark against Ollama, OpenAI, Claude, TypeSafe Jev, Open-Jev, Liquid AI d1, Laya, Perplexity Decisions, or vLLM."
    )
    parser.add_argument("model", nargs="?", help="Provider model name (not needed with --refresh-report)")
    parser.add_argument(
        "--provider",
        choices=("ollama", "openai", "claude", "gemini", *SYSTEM_ONE_PROVIDERS, *VLLM_PROVIDERS),
        default="ollama",
        help="Inference provider (default: ollama)",
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Question-bank SQLite file")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT, help="Markdown score report")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Resumable benchmark result database",
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI executable used for OpenAI ChatGPT OAuth (default: codex)",
    )
    parser.add_argument(
        "--openai-reasoning",
        choices=("minimal", "low", "medium", "high", "xhigh"),
        default="low",
        help="Codex reasoning effort for --provider openai (default: low)",
    )
    parser.add_argument(
        "--jev-url",
        help="System One API base URL; default by provider: "
        + "; ".join(
            f"{provider} {service.url} ({service.key_help()})"
            for provider, service in SYSTEM_ONE.items()
        ),
    )
    parser.add_argument(
        "--vllm-url",
        default=DEFAULT_VLLM_URL,
        help=f"vLLM server base URL for --provider vllm, vllm-yes-no or vllm-verbal (default: {DEFAULT_VLLM_URL})",
    )
    parser.add_argument(
        "--vllm-thinking",
        action="store_true",
        help="let the model think before it answers, for --provider vllm (default: thinking off)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="requests in flight at once, for --provider vllm, gemini and the System One providers (default: 1)",
    )
    parser.add_argument(
        "--claude-bin",
        default="claude",
        help="Claude Code CLI signed in with a Claude subscription, for --provider claude (default: claude)",
    )
    parser.add_argument(
        "--claude-effort",
        choices=CLAUDE_EFFORTS,
        default="low",
        help="Claude Code effort level for --provider claude (default: low)",
    )
    parser.add_argument(
        "--gemini-thinking",
        choices=("low", "medium", "high"),
        default="low",
        help="Gemini thinking level for --provider gemini (default: low, the lowest Gemini 3.8 Flash supports)",
    )
    parser.add_argument(
        "--unit",
        action="append",
        help="Unit number or exact unit title; repeat to select multiple units",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--limit", type=int, help="Use the first N eligible questions")
    selection.add_argument(
        "--sample",
        type=int,
        help="Deterministically sample N eligible questions across the selected units",
    )
    parser.add_argument(
        "--image-input",
        choices=("auto", "on", "off"),
        default="auto",
        help=(
            "include questions that require their source image: auto detects Ollama vision "
            "capability, on requires it, off excludes them"
        ),
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-ctx", type=int)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--log-verbose", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    variant = parser.add_mutually_exclusive_group()
    variant.add_argument(
        "--shuffle-options",
        type=int,
        metavar="SEED",
        help="show each question's options in a fixed random order for this seed, relettered from A; "
        "answers are stored under the question bank's letters",
    )
    variant.add_argument(
        "--replace-key-text",
        type=int,
        metavar="SEED",
        help="give each question's correct option the text of a fixed random wrong option for this seed, so "
        "no option is right; the report counts how often the model still picks the original letter",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        metavar="N",
        help="run the same configuration again as repeat N (2 or more); the first run is repeat 1 and needs "
        "no flag. Repeats are reported as run-to-run variation, not in the main tables",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        metavar="FILE",
        help="only the question IDs listed in FILE, one per line, asked in the question bank's order",
    )
    parser.add_argument(
        "--refresh-report",
        action="store_true",
        help="recompute the metrics of every run in --output from --database and rewrite it, without running a model",
    )
    parser.add_argument(
        "--export-answers",
        type=Path,
        metavar="PATH",
        help="write every run in --output with its per-question answers, without question text, to PATH and exit",
    )
    args = parser.parse_args()
    if args.model is None and not args.refresh_report and args.export_answers is None:
        parser.error("the model argument is required")
    for name in ("limit", "sample", "num_ctx"):
        value = getattr(args, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.progress_every < 1:
        parser.error("--progress-every must be at least 1")
    if args.provider != "ollama" and args.num_ctx is not None:
        parser.error("--num-ctx is only supported by --provider ollama")
    if args.provider != "ollama" and args.image_input == "on":
        parser.error("--image-input=on is currently supported only by --provider ollama")
    if args.vllm_thinking and args.provider != "vllm":
        parser.error("--vllm-thinking is only supported by --provider vllm")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.concurrency > 1 and args.provider not in ("vllm", "gemini") and args.provider not in SYSTEM_ONE:
        parser.error("--concurrency is only supported by --provider vllm, gemini and the System One providers")
    if args.repeat is not None and args.repeat < 2:
        parser.error("--repeat must be at least 2; the first run of a configuration is repeat 1")
    if args.questions is not None and (args.sample is not None or args.limit is not None):
        parser.error("--questions cannot be combined with --sample or --limit")
    if args.provider in SINGLE_QUESTION_PROVIDERS and args.batch_size != 1:
        parser.error(f"--provider {args.provider} sends one question per request; use --batch-size 1")
    if args.jev_url is None and args.provider in SYSTEM_ONE:
        args.jev_url = SYSTEM_ONE[args.provider].url
    return args


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ollama_supports_vision(base_url: str, model: str, timeout: float) -> bool:
    endpoint = f"{base_url.rstrip('/')}/api/show"
    payload = json.dumps({"model": model}, separators=(",", ":")).encode()
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=min(timeout, 30.0)) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Ollama model capability lookup returned HTTP {exc.code}: {detail}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"could not query Ollama model capabilities at {endpoint}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama model capability lookup returned invalid JSON") from exc
    capabilities = result.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise RuntimeError("Ollama model capability lookup returned invalid capabilities")
    return "vision" in capabilities


def resolve_thinking(model: str) -> bool | str:
    name = model.rsplit("/", 1)[-1].lower()
    return "low" if name == "gpt-oss" or name.startswith("gpt-oss:") else False


def thinking_label(value: bool | str) -> str:
    return value if isinstance(value, str) else "on" if value else "off"


def oauth_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        environment.pop(name, None)
    return environment


def require_chatgpt_oauth(codex_bin: str) -> str:
    executable = shutil.which(codex_bin)
    if executable is None:
        candidate = Path(codex_bin).expanduser()
        if candidate.is_file():
            executable = str(candidate.resolve())
    if executable is None:
        raise ValueError(
            "Codex CLI was not found. Install it, run `codex login`, then retry "
            "with `--provider openai`."
        )
    status = subprocess.run(
        [executable, "login", "status"],
        capture_output=True,
        text=True,
        timeout=30,
        env=oauth_environment(),
        check=False,
    )
    detail = "\n".join(part.strip() for part in (status.stdout, status.stderr) if part.strip())
    if status.returncode != 0 or re.search(
        r"\blogged in (?:using|with) chatgpt\b", detail, re.IGNORECASE
    ) is None:
        raise ValueError(
            "OpenAI provider requires ChatGPT OAuth. Run `codex logout` if necessary, "
            "then `codex login` and choose Sign in with ChatGPT. "
            f"Codex status: {detail or 'not authenticated'}"
        )
    return executable


def claude_subscription_environment() -> dict[str, str]:
    """Environment that keeps Claude Code on the signed-in Claude subscription."""
    environment = os.environ.copy()
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        environment.pop(name, None)
    return environment


def require_claude_subscription(claude_bin: str) -> str:
    executable = shutil.which(claude_bin)
    if executable is None:
        candidate = Path(claude_bin).expanduser()
        if candidate.is_file():
            executable = str(candidate.resolve())
    if executable is None:
        raise ValueError(
            "Claude Code CLI was not found. Install it, run `claude` and sign in with a Claude "
            "subscription, then retry with `--provider claude`."
        )
    status = subprocess.run(
        [executable, "auth", "status"],
        capture_output=True,
        text=True,
        timeout=30,
        env=claude_subscription_environment(),
        check=False,
    )
    try:
        detail = json.loads(status.stdout)
    except json.JSONDecodeError:
        detail = {}
    if status.returncode != 0 or not detail.get("loggedIn") or detail.get("authMethod") != "claude.ai":
        raise ValueError(
            "Claude provider requires a Claude subscription login. Run `claude auth login` and sign "
            "in with your Claude account. "
            f"Claude Code status: {status.stdout.strip() or status.stderr.strip() or 'not authenticated'}"
        )
    return executable


def parse_json_array(value: Any, field: str, question_id: int) -> list[Any]:
    try:
        parsed = json.loads(value or "[]") if isinstance(value, str) else value or []
    except json.JSONDecodeError as exc:
        raise ValueError(f"question {question_id} has invalid {field}: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"question {question_id} has non-array {field}")
    return parsed


def visual_text(visuals: Any, question_id: int) -> str:
    records = parse_json_array(visuals, "visual JSON", question_id)
    rendered: list[str] = []
    for visual in records:
        if not isinstance(visual, dict):
            continue
        parts = [
            str(visual.get(key)).strip()
            for key in ("description", "markdown", "dot")
            if visual.get(key) not in (None, "")
        ]
        if parts:
            rendered.append("\n".join(parts))
    return "\n\n".join(rendered)


def compose_prompt(row: sqlite3.Row, options: tuple[Option, ...]) -> str:
    parts: list[str] = []
    passage_parts = [
        str(row[key]).strip()
        for key in ("passage_text", "passage_description", "passage_markdown")
        if row[key] not in (None, "")
    ]
    if passage_parts:
        parts.append("Ortak metin / bağlam:\n" + "\n\n".join(dict.fromkeys(passage_parts)))
    question_visual = visual_text(row["visuals_json"], int(row["question_id"]))
    if question_visual:
        parts.append("Soruya ait görselin metinsel gösterimi:\n" + question_visual)
    parts.append(str(row["question"]).strip())
    choices = "\n".join(f"{option.label}. {option.text}" for option in options)
    parts.append(OPTIONS_HEADING + choices)
    return "\n\n".join(parts)


def missing_markup(prompt: str, option_texts: list[str]) -> tuple[bool, bool]:
    """Whether a prompt refers to underlined words but marks none, and to numbered words but numbers none.

    `option_texts` must be in the question bank's order: options "I", "II", … make a question numbered.
    """
    body = prompt.rpartition("\n\n" + OPTIONS_HEADING)[0]
    underline = bool(UNDERLINE_REFERENCE.search(prompt)) and "<u>" not in prompt
    numbered = bool(NUMBERED_REFERENCE.search(prompt)) or option_texts[:2] in ROMAN_OPTIONS
    return underline, numbered and not INLINE_NUMBER.search(body)


def option_shape(texts: list[str]) -> str:
    """'numerals' when every option is a single numeral (I, II, … or 1, 2, …), 'combinations' when every
    option combines numerals (I ve II, Yalnız III), and 'text' otherwise."""
    texts = [text.strip() for text in texts]
    if all(SINGLE_NUMERAL_OPTION.fullmatch(text) for text in texts):
        return "numerals"
    if all(NUMERAL_COMBINATION_OPTION.fullmatch(text) for text in texts):
        return "combinations"
    return "text"


def parse_options(row: sqlite3.Row) -> tuple[Option, ...]:
    question_id = int(row["question_id"])
    records = parse_json_array(row["choices_json"], "choices_json", question_id)
    shared_visual = visual_text(row["visuals_json"], question_id)
    options: list[Option] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"question {question_id} has a non-object choice")
        label = str(record.get("label") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]", label) or label in seen:
            raise ValueError(f"question {question_id} has invalid or duplicate choice label {label!r}")
        text = str(record.get("text") or "").strip()
        choice_visual = visual_text(record.get("visuals", []), question_id)
        if choice_visual:
            text = f"{text}\n[Görsel gösterimi]\n{choice_visual}".strip()
        if not text and shared_visual:
            text = f"[Görsel seçenek {label}]"
        if not text:
            raise ValueError(f"question {question_id} choice {label} is empty")
        seen.add(label)
        options.append(Option(label, text))
    if len(options) < 2:
        raise ValueError(f"question {question_id} has fewer than two choices")
    return tuple(options)


def shuffle_options(
    options: tuple[Option, ...], answer: str, seed: int, question_id: int
) -> tuple[tuple[Option, ...], str, tuple[str, ...]]:
    """A fixed per-question random order of the options, relettered from A.

    Returns the options as shown, the key's letter among them, and each shown option's original letter.
    """
    order = list(options)
    random.Random(f"{seed}:{question_id}").shuffle(order)
    shown = tuple(Option(chr(ord("A") + index), option.text) for index, option in enumerate(order))
    original_labels = tuple(option.label for option in order)
    return shown, shown[original_labels.index(answer)].label, original_labels


def replace_key_text(
    options: tuple[Option, ...], answer: str, seed: int, question_id: int
) -> tuple[tuple[Option, ...], str]:
    """The options with the key's text replaced by that of a fixed per-question random wrong option.

    No option is then right, and the key's letter shows the same text as that wrong option, its twin.
    Returns the options as shown and the twin's letter.
    """
    twin = random.Random(f"{seed}:{question_id}").choice([option for option in options if option.label != answer])
    shown = tuple(Option(option.label, twin.text) if option.label == answer else option for option in options)
    return shown, twin.label


def read_question_ids(path: Path) -> frozenset[int]:
    """Question IDs listed one per line; blank lines and lines starting with # are skipped."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    ids = frozenset(int(line) for line in lines if line and not line.startswith("#"))
    if not ids:
        raise ValueError(f"{path} lists no question IDs")
    return ids


def load_questions(
    path: Path,
    units: list[str] | None,
    limit: int | None,
    sample: int | None,
    seed: int,
    allow_images: bool = False,
    shuffle_seed: int | None = None,
    replace_key_seed: int | None = None,
    include_excluded: bool = False,
    question_ids: frozenset[int] | None = None,
) -> Selection:
    """The benchmark questions, without those marked `excluded` unless `include_excluded` is set, and only
    those in `question_ids` when given."""
    if not path.is_file():
        raise ValueError(f"question database does not exist: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        view = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='benchmark_questions'"
        ).fetchone()
        if view is None:
            raise ValueError(f"{path} does not contain the benchmark_questions view")
        rows = connection.execute(
            """
            SELECT * FROM benchmark_questions
            ORDER BY CAST(unit_number AS INTEGER), source_page_start, question_id
            """
        ).fetchall()
    finally:
        connection.close()

    source_total = len(rows)
    available = {(str(row["unit_number"]), str(row["unit_title"])) for row in rows}
    if units:
        wanted = {value.casefold() for value in units}
        matched = {
            selector
            for selector in wanted
            if any(selector in {number.casefold(), title.casefold()} for number, title in available)
        }
        unknown = sorted(wanted - matched)
        if unknown:
            labels = ", ".join(f"{number}: {title}" for number, title in sorted(available))
            raise ValueError(f"unknown units: {', '.join(unknown)}; available: {labels}")
        rows = [
            row
            for row in rows
            if str(row["unit_number"]).casefold() in wanted
            or str(row["unit_title"]).casefold() in wanted
        ]

    filtered_total = len(rows)
    skipped = {
        "excluded": 0,
        "incomplete": 0,
        "unanswered": 0,
        "empty_question": 0,
        "malformed_choices": 0,
        "invalid_answer": 0,
        "requires_image": 0,
        "image_unavailable": 0,
    }
    questions: list[Question] = []
    for row in rows:
        status = row["status"] if "status" in row.keys() else None
        if status == "excluded" and not include_excluded:
            skipped["excluded"] += 1
            continue
        if not bool(row["complete"]):
            skipped["incomplete"] += 1
            continue
        requires_image = (
            "requires_image" in row.keys() and bool(row["requires_image"])
        )
        image_path: Path | None = None
        if requires_image and not allow_images:
            skipped["requires_image"] += 1
            continue
        if requires_image:
            raw_image_path = (
                str(row["image_path"] or "").strip()
                if "image_path" in row.keys()
                else ""
            )
            image_path = Path(raw_image_path) if raw_image_path else None
            if image_path is None or not image_path.is_file():
                skipped["image_unavailable"] += 1
                continue
        answer = str(row["answer"] or "").strip().upper()
        if not answer:
            skipped["unanswered"] += 1
            continue
        if not str(row["question"] or "").strip():
            skipped["empty_question"] += 1
            continue
        try:
            options = parse_options(row)
        except ValueError as exc:
            skipped["malformed_choices"] += 1
            print(f"warning: {exc}; skipping", file=sys.stderr)
            continue
        labels = {option.label for option in options}
        if answer not in labels:
            skipped["invalid_answer"] += 1
            print(
                f"warning: question {row['question_id']} answer {answer!r} is not in {sorted(labels)}; skipping",
                file=sys.stderr,
            )
            continue
        twin: str | None = None
        if replace_key_seed is not None:
            options, twin = replace_key_text(options, answer, replace_key_seed, int(row["question_id"]))
        original_labels: tuple[str, ...] = ()
        if shuffle_seed is not None:
            options, answer, original_labels = shuffle_options(options, answer, shuffle_seed, int(row["question_id"]))
        unit_number = str(row["unit_number"] or "?")
        unit_title = str(row["unit_title"] or "Bilinmeyen Ünite")
        prompt = compose_prompt(row, options)
        if requires_image:
            prompt += (
                "\n\nBu soru için kaynak sayfa görseli ayrıca sağlanmıştır; "
                "görselde yalnızca bu soru numarasına ait içeriği kullanın."
            )
        questions.append(
            Question(
                question_id=int(row["question_id"]),
                category=f"{unit_number}. {unit_title}",
                unit_number=unit_number,
                unit_title=unit_title,
                section_title=str(row["section_title"] or ""),
                test_type=str(row["test_type"] or ""),
                test_number=str(row["test_number"] or ""),
                question_number=str(row["question_number"] or ""),
                prompt=prompt,
                options=options,
                answer=answer,
                source_page=int(row["source_page_start"]),
                requires_image=requires_image,
                image_path=image_path,
                status=status,
                original_labels=original_labels,
                twin=twin,
            )
        )

    eligible_total = len(questions)
    if question_ids is not None:
        missing = question_ids - {question.question_id for question in questions}
        if missing:
            raise ValueError(f"not eligible benchmark questions: {sorted(missing)[:10]}")
        questions = [question for question in questions if question.question_id in question_ids]
    elif sample is not None and sample < len(questions):
        selected_indices = sorted(random.Random(seed).sample(range(len(questions)), sample))
        questions = [questions[index] for index in selected_indices]
    elif limit is not None:
        questions = questions[:limit]
    if not questions:
        raise ValueError("no eligible questions selected")
    return Selection(
        questions=tuple(questions),
        source_total=source_total,
        filtered_total=filtered_total,
        eligible_total=eligible_total,
        skipped=skipped,
    )


@functools.lru_cache(maxsize=None)
def current_bank(dataset: str, search_dir: str) -> tuple[str, dict[int, dict[str, Any]]] | None:
    """The question bank a run used, as it stands now: its SHA-256, and each question's printed number,
    passage ID, key and review status (None in a bank without statuses).

    The bank is looked up at `dataset`, then by its file name in `search_dir`; None when neither exists.
    Question IDs, numbers and passages stay fixed across a bank's versions, but a review can exclude a
    question or correct its key after a run, so the report grades every run with the bank's current keys
    and statuses (graded_answers).
    """
    for candidate in (Path(dataset), Path(search_dir) / Path(dataset).name):
        if not candidate.is_file():
            continue
        bank = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
        try:
            statuses = bank.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='question_status'").fetchone()
            query = (
                "SELECT q.id, q.printed_number, q.passage_id, q.answer, s.status FROM questions q "
                "LEFT JOIN question_status s ON s.question_id = q.id"
                if statuses
                else "SELECT id, printed_number, passage_id, answer, NULL FROM questions"
            )
            questions = {
                int(question): {"number": number, "passage": passage, "key": key, "status": status}
                for question, number, passage, key, status in bank.execute(query)
            }
        finally:
            bank.close()
        return file_sha256(candidate), questions
    return None


def passage_clusters(dataset: str, search_dir: str) -> dict[int, str]:
    """Each question's resampling cluster: its passage when it has one, else the question itself; empty
    when the question bank isn't found (see current_bank)."""
    bank = current_bank(dataset, search_dir)
    if bank is None:
        return {}
    return {
        question: f"passage {row['passage']}" if row["passage"] is not None else f"question {question}"
        for question, row in bank[1].items()
    }


def regrade(answer: dict[str, Any], now: dict[str, Any] | None, keep_excluded: bool = False) -> dict[str, Any] | None:
    """A stored answer graded against its question as the bank holds it now (`now`, from current_bank):
    None when the question is now excluded (unless keep_excluded), else the answer with the current
    status, and the current key and the correctness that follows from it."""
    if now is None:
        return answer
    if now["status"] == "excluded" and not keep_excluded:
        return None
    graded = {**answer, "status": now["status"]}
    if now["key"] != answer["expected_answer"]:
        graded.update(expected_answer=now["key"], correct=int(answer["predicted_answer"] == now["key"]))
    return graded


def graded_answers(
    connection: sqlite3.Connection, run_key: str, dataset: str, search_dir: Path, keep_excluded: bool = False
) -> list[dict[str, Any]]:
    """A run's stored answers graded against its question bank as it stands now (see regrade). The stored
    answers are not changed."""
    bank = current_bank(dataset, str(search_dir))
    questions = bank[1] if bank else {}
    graded = []
    for row in connection.execute(
        "SELECT answers.* FROM answers JOIN runs ON runs.id = answers.run_id WHERE runs.run_key = ?", (run_key,)
    ):
        answer = regrade(dict(row), questions.get(int(row["question_id"])), keep_excluded)
        if answer is not None:
            graded.append(answer)
    return graded


def export_answers(path: Path, report: Path, connection: sqlite3.Connection) -> int:
    """Write every reported run's answers without question text, grouped by the question bank they are
    graded against: the questions' IDs, units, pages, printed numbers, keys, statuses and passages, the
    prompt templates, and per run its settings, the bank version it ran on, and each answer's letter,
    correctness, score, option probabilities and request time. Answers are graded against the bank as it
    stands now; questions it now excludes keep their answers and show the status `excluded`. Returns the
    number of runs written."""
    datasets: dict[str, dict[str, Any]] = {}
    results = sorted(read_results(report).values(), key=lambda item: item["run_id"])
    for result in results:
        bank = current_bank(result["dataset"], str(report.parent))
        dataset = datasets.setdefault(
            bank[0] if bank else result["dataset_sha256"],
            {
                "name": Path(result["dataset"]).name,
                "graded_sha256": bank[0] if bank else result["dataset_sha256"],
                "bank": bank[1] if bank else {},
                "questions": {},
                "runs": [],
            },
        )
        run = connection.execute("SELECT seed FROM runs WHERE run_key=?", (result["run_key"],)).fetchone()
        answers = {}
        for row in graded_answers(connection, result["run_key"], result["dataset"], report.parent, keep_excluded=True):
            question = int(row["question_id"])
            unit = re.match(r"(\d+)\.", row["category"])
            dataset["questions"].setdefault(
                question,
                {"unit": int(unit.group(1)) if unit else None, "page": row["source_page"], "key": row["expected_answer"], "status": row["status"]},
            )
            _, score = answer_usage(result.get("provider", "ollama"), question, row["raw_response"])
            probabilities = option_probabilities(result.get("provider", "ollama"), row["raw_response"], question)
            answers[question] = {
                "choice": row["predicted_answer"],
                "correct": int(row["correct"]),
                # Full precision: rounding would tie distinct scores and change ranking metrics such as AUROC.
                "score": score,
                "probabilities": None if probabilities is None else {label: float(p) for label, p in probabilities.items()},
                "request_seconds": None if row["request_seconds"] is None else round(float(row["request_seconds"]), 3),
            }
        dataset["runs"].append(
            {
                "run": result["run_id"],
                "model": result["model"],
                "provider": result.get("provider", "ollama"),
                "dataset_sha256": result["dataset_sha256"],
                "thinking": result["thinking"],
                "questions_per_request": result["batch_size"],
                "concurrency": result.get("concurrency", 1),
                "seed": run["seed"],
                "shuffle_options": result.get("shuffle_options"),
                "replace_key_text": result.get("replace_key_text"),
                "repeat": result.get("repeat"),
                "question_list": result.get("question_list"),
                "answers": answers,
            }
        )
    output = []
    for dataset in datasets.values():
        order = sorted(dataset["questions"])
        bank = dataset["bank"]
        columns = ("choice", "correct", "score", "probabilities", "request_seconds")
        output.append(
            {
                "name": dataset["name"],
                "graded_sha256": dataset["graded_sha256"],
                "questions": {
                    "id": order,
                    "unit": [dataset["questions"][question]["unit"] for question in order],
                    "page": [dataset["questions"][question]["page"] for question in order],
                    "number": [bank.get(question, {}).get("number") for question in order],
                    "key": [dataset["questions"][question]["key"] for question in order],
                    "status": [dataset["questions"][question]["status"] for question in order],
                    "passage": [bank.get(question, {}).get("passage") for question in order],
                },
                "runs": [
                    {
                        **{key: value for key, value in run.items() if key != "answers"},
                        **{
                            column: [run["answers"].get(question, {}).get(column) for question in order]
                            for column in columns
                        },
                    }
                    for run in dataset["runs"]
                ],
            }
        )
    document = {
        "schema_version": 2,
        "prompts": {
            "answer_system": ANSWER_SYSTEM_PROMPT,
            "answer_instruction": ANSWER_INSTRUCTION,
            "confidence_system": CONFIDENCE_SYSTEM_PROMPT,
            "confidence_instruction": CONFIDENCE_INSTRUCTION,
            "verbal_system": VERBAL_SYSTEM_PROMPT,
            "verbal_instruction": VERBAL_INSTRUCTION,
            "system_one_instructions": JEV_INSTRUCTIONS,
            "yes_no": YES_NO_PROMPT,
        },
        "datasets": output,
    }
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(results)


def open_result_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY,
            run_key TEXT NOT NULL UNIQUE,
            model TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'ollama',
            dataset TEXT NOT NULL,
            dataset_sha256 TEXT NOT NULL,
            selection_sha256 TEXT NOT NULL,
            ollama_url TEXT NOT NULL,
            seed INTEGER NOT NULL,
            batch_size INTEGER NOT NULL,
            num_ctx INTEGER,
            shuffle_options INTEGER,
            replace_key_text INTEGER,
            thinking_mode TEXT NOT NULL,
            selected_total INTEGER NOT NULL,
            evaluated_total INTEGER NOT NULL,
            skipped_json TEXT NOT NULL,
            timed_questions INTEGER NOT NULL DEFAULT 0,
            timed_seconds REAL NOT NULL DEFAULT 0,
            questions_per_minute REAL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS answers (
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            source_page INTEGER NOT NULL,
            category TEXT NOT NULL,
            question TEXT NOT NULL,
            options_json TEXT NOT NULL,
            status TEXT,
            expected_answer TEXT NOT NULL,
            predicted_answer TEXT,
            correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
            raw_response TEXT NOT NULL,
            answered_at TEXT NOT NULL,
            PRIMARY KEY (run_id, ordinal)
        );
        CREATE INDEX IF NOT EXISTS answers_run_category ON answers(run_id, category);
        """
    )
    # Columns added after the first schema; older databases get them here.
    for table, column, definition in (
        ("runs", "provider", "TEXT NOT NULL DEFAULT 'ollama'"),
        ("runs", "shuffle_options", "INTEGER"),
        ("runs", "replace_key_text", "INTEGER"),
        ("answers", "status", "TEXT"),
        ("answers", "request_seconds", "REAL"),
        ("runs", "repeat", "INTEGER"),
    ):
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            with connection:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return connection


def start_run(
    connection: sqlite3.Connection,
    selection: Selection,
    model: str,
    data_path: Path,
    provider: str,
    endpoint: str,
    seed: int,
    batch_size: int,
    thinking: bool | str,
    num_ctx: int | None,
    image_input: bool,
    shuffle_seed: int | None,
    replace_key_seed: int | None,
    repeat: int | None,
    restart: bool,
) -> RunIdentity:
    dataset_hash = file_sha256(data_path)
    selection_text = "\n".join(str(question.question_id) for question in selection.questions)
    selection_hash = hashlib.sha256(selection_text.encode()).hexdigest()
    identity_config: dict[str, Any] = {
        "schema": 3,
        "model": model,
        "dataset_sha256": dataset_hash,
        "selection_sha256": selection_hash,
        "ollama_url": endpoint.rstrip("/"),
        "seed": seed,
        "batch_size": batch_size,
        "thinking": thinking_label(thinking),
        "num_ctx": num_ctx,
        "image_input": image_input,
    }
    if provider != "ollama":
        identity_config["provider"] = provider
    if provider == "openai":
        identity_config["oauth"] = "chatgpt"
        # Earlier OpenAI runs asked for letters only; never resume them with the confidence prompt.
        identity_config["stated_confidence"] = True
    if provider == "vllm":
        # Earlier vllm runs stored no letter probabilities; never resume them with the request that does.
        identity_config["letter_probabilities"] = True
    if shuffle_seed is not None:
        identity_config["shuffle_options"] = shuffle_seed
    if replace_key_seed is not None:
        identity_config["replace_key_text"] = replace_key_seed
    if repeat is not None:
        identity_config["repeat"] = repeat
    identity = json.dumps(
        identity_config,
        sort_keys=True,
        separators=(",", ":"),
    )
    run_key = hashlib.sha256(identity.encode()).hexdigest()
    now = utc_now()
    with connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO runs (
                run_key, model, provider, dataset, dataset_sha256, selection_sha256,
                ollama_url, seed, batch_size, num_ctx, shuffle_options, replace_key_text, repeat, thinking_mode,
                selected_total, evaluated_total, skipped_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                run_key,
                model,
                provider,
                str(data_path),
                dataset_hash,
                selection_hash,
                endpoint.rstrip("/"),
                seed,
                batch_size,
                num_ctx,
                shuffle_seed,
                replace_key_seed,
                repeat,
                thinking_label(thinking),
                selection.eligible_total,
                len(selection.questions),
                json.dumps(selection.skipped, sort_keys=True),
                now,
                now,
            ),
        )
        row = connection.execute("SELECT id FROM runs WHERE run_key=?", (run_key,)).fetchone()
        if row is None:
            raise RuntimeError("could not create benchmark run")
        run_id = int(row["id"])
        if restart:
            connection.execute("DELETE FROM answers WHERE run_id=?", (run_id,))
            connection.execute(
                "UPDATE runs SET timed_questions=0,timed_seconds=0,questions_per_minute=NULL WHERE id=?",
                (run_id,),
            )
        connection.execute(
            "UPDATE runs SET status='running',updated_at=? WHERE id=?", (now, run_id)
        )
    return RunIdentity(run_id, run_key, dataset_hash, selection_hash)


def mark_run(connection: sqlite3.Connection, run_id: int, status: str) -> None:
    with connection:
        connection.execute(
            "UPDATE runs SET status=?,updated_at=? WHERE id=?", (status, utc_now(), run_id)
        )


def score(connection: sqlite3.Connection, run_id: int) -> tuple[int, int, int, dict[str, dict[str, int]]]:
    row = connection.execute(
        """
        SELECT count(*) AS evaluated,coalesce(sum(correct),0) AS correct,
               coalesce(sum(predicted_answer IS NULL),0) AS invalid
        FROM answers WHERE run_id=?
        """,
        (run_id,),
    ).fetchone()
    assert row is not None
    categories = {
        str(item["category"]): {"correct": int(item["correct"]), "total": int(item["total"])}
        for item in connection.execute(
            "SELECT category,sum(correct) AS correct,count(*) AS total FROM answers WHERE run_id=? GROUP BY category ORDER BY category",
            (run_id,),
        )
    }
    return int(row["evaluated"]), int(row["correct"]), int(row["invalid"]), categories


def runtime_info(connection: sqlite3.Connection, run_id: int, remaining: int) -> str:
    row = connection.execute(
        "SELECT questions_per_minute FROM runs WHERE id=?", (run_id,)
    ).fetchone()
    rate = float(row["questions_per_minute"]) if row and row["questions_per_minute"] else None
    if not rate:
        return "q/min=collecting ETA=collecting"
    seconds = round(remaining * 60 / rate)
    if seconds < 60:
        eta = f"{seconds}s"
    elif seconds < 3600:
        eta = f"{seconds // 60}m"
    else:
        eta = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"q/min={rate:.2f} ETA={eta}"


def open_verbose_log(model: str) -> tuple[TextIO, Path]:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("._-") or "model"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = Path(f"verbose_log_{safe}_{stamp}.log")
    return path.open("x", encoding="utf-8"), path


# --concurrency writes the verbose log from several threads.
VERBOSE_LOCK = threading.Lock()


def write_verbose(log: TextIO | None, event: str, content: str) -> None:
    if log is not None:
        with VERBOSE_LOCK:
            log.write(f"=== {event} {utc_now()} ===\n{content}\n\n")
            log.flush()


def parse_ollama_content(value: str) -> Any:
    stripped = value.strip()
    content, end = json.JSONDecoder().raw_decode(stripped)
    trailing = stripped[end:].strip()
    if trailing not in ("", "<|eot|>"):
        raise json.JSONDecodeError("Unexpected trailing content", stripped, end)
    return content


def make_prompt(batch: list[Question], instruction: str = ANSWER_INSTRUCTION) -> str:
    rendered = []
    image_ordinal = 0
    for index, question in enumerate(batch, 1):
        image_note = ""
        if question.requires_image:
            image_ordinal += 1
            image_note = f"; ekli görsel {image_ordinal}"
        rendered.append(
            f"Soru {index} (kaynak sayfa {question.source_page}{image_note}):\n"
            f"{question.prompt}"
        )
    return instruction + "\n\n" + "\n\n---\n\n".join(rendered)


def answers_schema(batch: list[Question]) -> dict[str, Any]:
    """JSON schema of a reply to make_prompt: one of each question's option letters, keyed by its number."""
    properties = {
        str(index): {"type": "string", "enum": [option.label for option in question.options]}
        for index, question in enumerate(batch, 1)
    }
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }


def batch_predictions(content: Any, batch: list[Question], result: Any) -> list[str | None]:
    """Each question's letter in a parsed reply to make_prompt, or None when it is missing or not one of
    the question's options. content is None when the reply was no JSON; result is the whole response."""
    try:
        answers = content["answers"]
        predictions = [answers.get(str(index)) for index in range(1, len(batch) + 1)]
    except (AttributeError, KeyError, TypeError):
        print(f"warning: invalid model response: {result!r}", file=sys.stderr)
        return [None] * len(batch)
    validated = [
        prediction if prediction in [option.label for option in question.options] else None
        for prediction, question in zip(predictions, batch)
    ]
    if any(prediction is None for prediction in validated):
        print(f"warning: incomplete model response: {result!r}", file=sys.stderr)
    return validated


def ask_ollama(
    base_url: str,
    model: str,
    batch: list[Question],
    timeout: float,
    seed: int,
    thinking: bool | str,
    num_ctx: int | None,
    verbose_log: TextIO | None,
) -> tuple[list[str | None], str]:
    schema = answers_schema(batch)
    options: dict[str, Any] = {"temperature": 0, "seed": seed}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    images: list[str] = []
    image_metadata: list[dict[str, Any]] = []
    for question in batch:
        if not question.requires_image:
            continue
        if question.image_path is None:
            raise ValueError(f"question {question.question_id} requires a missing image")
        image_bytes = question.image_path.read_bytes()
        images.append(base64.b64encode(image_bytes).decode("ascii"))
        image_metadata.append(
            {
                "path": str(question.image_path),
                "bytes": len(image_bytes),
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": ANSWER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": make_prompt(batch),
                **({"images": images} if images else {}),
            },
        ],
        "stream": False,
        "think": thinking,
        "format": schema,
        "keep_alive": "10m",
        "options": options,
    }
    endpoint = f"{base_url.rstrip('/')}/api/chat"
    raw_request = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if verbose_log is not None:
        logged_payload = {
            **payload,
            "messages": [
                payload["messages"][0],
                {
                    **payload["messages"][1],
                    **({"images": image_metadata} if images else {}),
                },
            ],
        }
        write_verbose(
            verbose_log,
            f"RAW REQUEST POST {endpoint}",
            json.dumps(logged_payload, ensure_ascii=False, separators=(",", ":")),
        )
    request = Request(
        endpoint,
        data=raw_request.encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode("utf-8", errors="replace")
            write_verbose(verbose_log, f"RAW RESPONSE HTTP {response.status}", raw_response)
            result = json.loads(raw_response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        write_verbose(verbose_log, f"RAW RESPONSE HTTP {exc.code}", detail)
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        write_verbose(verbose_log, "TRANSPORT ERROR", str(exc))
        raise RuntimeError(f"could not reach Ollama at {endpoint}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

    stored_response = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    try:
        content = parse_ollama_content(result["message"]["content"])
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
        content = None
    return batch_predictions(content, batch, result), stored_response


def ask_vllm(
    base_url: str,
    model: str,
    batch: list[Question],
    timeout: float,
    seed: int,
    thinking: bool,
    verbose_log: TextIO | None,
) -> tuple[list[str | None], str]:
    """The Ollama request through vLLM's chat API, which SGLang also serves: the same prompt and answer
    schema and the run's seed. Without thinking it decodes greedily (temperature 0); with thinking it
    samples with the server's defaults, because greedy decoding makes reasoning loop. The answer
    schema applies to the reply after the thinking.

    The server also returns each generated token's log probability and top alternatives. The stored
    response keeps, instead of those, each question's answer and its letter probabilities
    (letter_probabilities), keyed by question ID."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": make_prompt(batch)},
        ],
        "seed": seed,
        "max_tokens": VLLM_THINKING_MAX_TOKENS if thinking else VLLM_TOKENS_PER_ANSWER * len(batch),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answers", "schema": answers_schema(batch), "strict": True},
        },
        # Qwen's and Gemma's chat templates read enable_thinking, DeepSeek's reads thinking; each ignores
        # the other.
        "chat_template_kwargs": {"enable_thinking": thinking, "thinking": thinking},
        "logprobs": True,
        "top_logprobs": VLLM_TOP_LOGPROBS,
    }
    if not thinking:
        payload["temperature"] = 0
    result, _ = post_json(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        payload,
        {"Content-Type": "application/json"},
        timeout,
        verbose_log,
        "vLLM",
    )
    try:
        message = result["choices"][0]["message"]["content"]
        content = parse_ollama_content(message)
    except (AttributeError, IndexError, KeyError, TypeError, json.JSONDecodeError):
        message, content = None, None
    predictions = batch_predictions(content, batch, result)
    probabilities = letter_probabilities(result, message, batch)
    for choice in result.get("choices") or []:
        choice.pop("logprobs", None)
    result["answers"] = {
        str(question.question_id): {"answer": prediction, "probabilities": probabilities.get(index)}
        for index, (question, prediction) in enumerate(zip(batch, predictions), 1)
    }
    return predictions, json.dumps(result, ensure_ascii=False, separators=(",", ":"))


# A question's answer in a reply to make_prompt: "<number>": "<letter>".
REPLY_ANSWER = re.compile(r'"(\d+)"\s*:\s*"([A-Z])"')


def letter_probabilities(result: Any, content: str | None, batch: list[Question]) -> dict[int, dict[str, float]]:
    """Each question's option probabilities, by its number in the batch, from the token log probabilities
    of a reply to make_prompt.

    The token that writes a question's answer letter, and its top alternatives, give the probability of
    each option letter at that point: alternatives that differ from the written token only in the letter
    count for their letter. The probabilities are renormalized over the question's options; a letter
    outside the top alternatives counts as 0. The reply is the end of the tokens, so thinking before it
    is skipped. Questions whose letter cannot be found are left out."""
    tokens = (((result.get("choices") or [{}])[0].get("logprobs") or {}).get("content")) or []
    text = "".join(token["token"] for token in tokens)
    start = text.rfind(content) if content else -1
    if start < 0:
        return {}
    offsets = list(itertools.accumulate((len(token["token"]) for token in tokens), initial=0))
    found: dict[int, dict[str, float]] = {}
    for match in REPLY_ANSWER.finditer(content):
        number, letter = int(match.group(1)), match.group(2)
        if not 1 <= number <= len(batch):
            continue
        position = start + match.start(2)
        index = bisect.bisect_right(offsets, position) - 1
        written, at = tokens[index]["token"], position - offsets[index]
        mass = dict.fromkeys((option.label for option in batch[number - 1].options), 0.0)
        counted_written = False
        for alternative in tokens[index].get("top_logprobs") or []:
            other = alternative["token"]
            if len(other) == len(written) and other[:at] == written[:at] and other[at + 1 :] == written[at + 1 :] and other[at] in mass:
                mass[other[at]] += math.exp(alternative["logprob"])
                counted_written = counted_written or other == written
        if not counted_written and letter in mass:
            mass[letter] += math.exp(tokens[index]["logprob"])
        total = sum(mass.values())
        if total > 0 and mass.get(letter, 0.0) > 0:
            found[number] = {label: value / total for label, value in mass.items()}
    return found


def confidence_schema(batch: list[Question]) -> dict[str, Any]:
    """Structured-output schema: one supplied option and a 0-1 confidence per numbered question."""
    properties = {
        str(index): {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": [option.label for option in question.options]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["answer", "confidence"],
            "additionalProperties": False,
        }
        for index, question in enumerate(batch, 1)
    }
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }


def confidence_answers(
    answers: Any, batch: list[Question]
) -> tuple[list[str | None], dict[str, dict[str, Any]]]:
    """Valid letters in batch order, and each answer with its confidence keyed by question ID."""
    predictions: list[str | None] = []
    per_question: dict[str, dict[str, Any]] = {}
    for index, question in enumerate(batch, 1):
        item = answers.get(str(index)) if isinstance(answers, dict) else None
        answer = item.get("answer") if isinstance(item, dict) else None
        confidence = item.get("confidence") if isinstance(item, dict) else None
        if answer not in [option.label for option in question.options]:
            answer = None
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = None
        predictions.append(answer)
        per_question[str(question.question_id)] = {"answer": answer, "confidence": confidence}
    return predictions, per_question


def ask_openai(
    codex_bin: str,
    model: str,
    batch: list[Question],
    timeout: float,
    reasoning: str,
    verbose_log: TextIO | None,
) -> tuple[list[str | None], str]:
    """Answer a batch with a stated 0-1 confidence per question through the Codex CLI."""
    schema = confidence_schema(batch)
    prompt = make_prompt(batch, CONFIDENCE_INSTRUCTION)
    with tempfile.TemporaryDirectory(prefix="turkce-codex-") as temporary:
        temporary_path = Path(temporary)
        instructions_path = temporary_path / "instructions.md"
        schema_path = temporary_path / "answer-schema.json"
        output_path = temporary_path / "answer.json"
        instructions_path.write_text(CONFIDENCE_SYSTEM_PROMPT, encoding="utf-8")
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        # Replace Codex's agent instructions, turn off web search and the tools that can be switched
        # off, and skip user config and rules. The prompt goes through stdin: given a prompt argument,
        # Codex also reads piped stdin and waits for it to close.
        command = [
            codex_bin,
            "-c",
            'forced_login_method="chatgpt"',
            "-c",
            f'model_reasoning_effort="{reasoning}"',
            "-c",
            f'model_instructions_file="{instructions_path}"',
            "-c",
            'web_search="disabled"',
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--model",
            model,
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            *(argument for feature in CODEX_DISABLED_FEATURES for argument in ("--disable", feature)),
            "-",
        ]
        write_verbose(
            verbose_log,
            "OPENAI CODEX OAUTH REQUEST",
            json.dumps(
                {"command": command, "prompt": prompt, "schema": schema},
                ensure_ascii=False,
                indent=2,
            ),
        )
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=oauth_environment(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"OpenAI Codex OAuth request timed out after {timeout:g}s"
            ) from exc
        write_verbose(verbose_log, "OPENAI CODEX OAUTH RESPONSE", completed.stdout or completed.stderr)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"OpenAI Codex CLI exited with {completed.returncode}: {detail}"
            )
        try:
            events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI Codex CLI printed a line that is not a JSON event: {exc}") from exc
        if not output_path.is_file():
            raise RuntimeError("OpenAI Codex CLI did not write its final structured response")
        final_output = output_path.read_text(encoding="utf-8").strip()
    usage = next(
        (event.get("usage") for event in reversed(events) if event.get("type") == "turn.completed"),
        None,
    )
    try:
        answers = json.loads(final_output)["answers"]
    except (KeyError, TypeError, json.JSONDecodeError):
        answers = None
    predictions, per_question = confidence_answers(answers, batch)
    stored_response = json.dumps(
        {
            "provider": "openai-chatgpt-oauth",
            "answers": per_question,
            "usage": usage,
            "events": events,
            "stderr": completed.stderr,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if any(prediction is None for prediction in predictions):
        print(f"warning: incomplete OpenAI response: {final_output!r}", file=sys.stderr)
    return predictions, stored_response


def ask_claude(
    claude_bin: str,
    model: str,
    batch: list[Question],
    timeout: float,
    effort: str,
    verbose_log: TextIO | None,
) -> tuple[list[str | None], str]:
    """Answer a batch with a stated 0-1 confidence per question through the Claude Code CLI."""
    schema = confidence_schema(batch)
    prompt = make_prompt(batch, CONFIDENCE_INSTRUCTION)
    # Replace Claude Code's agent prompt and drop tools, settings, MCP servers and saved sessions so
    # only the benchmark prompt reaches the model.
    command = [
        claude_bin,
        "--print",
        "--model",
        model,
        "--effort",
        effort,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--system-prompt",
        CONFIDENCE_SYSTEM_PROMPT,
        "--tools",
        "",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    write_verbose(
        verbose_log,
        "CLAUDE CODE SUBSCRIPTION REQUEST",
        json.dumps({"command": command, "prompt": prompt}, ensure_ascii=False, indent=2),
    )
    # Claude Code processes share one sign-in. When its token expires, parallel runs all try to refresh it
    # and the losers fail with a transient error that names this; they wait and retry.
    for attempt in range(CLAUDE_REFRESH_RETRIES + 1):
        with tempfile.TemporaryDirectory(prefix="turkce-claude-") as temporary:
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    cwd=temporary,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=claude_subscription_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"Claude Code request timed out after {timeout:g}s") from exc
        write_verbose(verbose_log, "CLAUDE CODE SUBSCRIPTION RESPONSE", completed.stdout or completed.stderr)
        detail = completed.stderr.strip() or completed.stdout.strip()
        if completed.returncode == 0 or CLAUDE_REFRESH_FAILURE not in detail or attempt == CLAUDE_REFRESH_RETRIES:
            break
        print(
            f"warning: Claude Code could not refresh its sign-in; retry {attempt + 1}/{CLAUDE_REFRESH_RETRIES} "
            f"in {CLAUDE_REFRESH_DELAY:g}s",
            file=sys.stderr,
        )
        time.sleep(CLAUDE_REFRESH_DELAY)
    if completed.returncode != 0:
        raise RuntimeError(f"Claude Code exited with {completed.returncode}: {detail}")
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude Code returned invalid JSON: {exc}") from exc
    if not isinstance(output, dict) or output.get("is_error"):
        raise RuntimeError(f"Claude Code reported an error: {completed.stdout.strip()}")
    answers = (output.get("structured_output") or {}).get("answers")
    predictions, per_question = confidence_answers(answers, batch)
    stored_response = json.dumps(
        {
            "provider": "claude-subscription",
            "answers": per_question,
            "output": output,
            "stderr": completed.stderr,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if any(prediction is None for prediction in predictions):
        print(f"warning: incomplete Claude response: {completed.stdout.strip()!r}", file=sys.stderr)
    return predictions, stored_response


def gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or (
        GEMINI_KEY_FILE.expanduser().read_text(encoding="utf-8").strip() if GEMINI_KEY_FILE.expanduser().is_file() else ""
    )
    if not key:
        raise ValueError(f"set GEMINI_API_KEY or put the key in {GEMINI_KEY_FILE} for --provider gemini")
    return key


def ask_gemini(
    api_key: str,
    model: str,
    batch: list[Question],
    timeout: float,
    thinking_level: str,
    verbose_log: TextIO | None,
) -> tuple[list[str | None], str]:
    """Answer a batch with a stated 0-1 confidence per question through the Gemini API's generateContent:
    the prompt, system instruction and schema the Claude and OpenAI providers use. Gemini 3 models take no
    temperature, top_p or top_k, so the request sends none; the thinking level is set."""
    payload = {
        "systemInstruction": {"parts": [{"text": CONFIDENCE_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": make_prompt(batch, CONFIDENCE_INSTRUCTION)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": confidence_schema(batch),
            "thinkingConfig": {"thinkingLevel": thinking_level},
        },
    }
    result, _ = post_json(
        f"{GEMINI_URL}/models/{model}:generateContent",
        payload,
        {"Content-Type": "application/json", "x-goog-api-key": api_key},
        timeout,
        verbose_log,
        "Gemini",
    )
    try:
        parts = result["candidates"][0]["content"]["parts"]
        # Thought summaries, when returned, are parts marked thought; the answer is the rest.
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        answers = json.loads(text).get("answers")
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError):
        answers = None
    predictions, per_question = confidence_answers(answers, batch)
    if any(prediction is None for prediction in predictions):
        print(f"warning: incomplete Gemini response: {result!r}", file=sys.stderr)
    stored_response = json.dumps({"answers": per_question, "response": result}, ensure_ascii=False, separators=(",", ":"))
    return predictions, stored_response


class NoRedirect(HTTPRedirectHandler):
    """Refuse redirects so the bearer token is sent only to the configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


JEV_OPENER = build_opener(NoRedirect)


def jev_api_key(provider: str) -> str | None:
    """The System One provider's API key from its environment variables, or None without one."""
    service = SYSTEM_ONE[provider]
    for name in service.key_vars:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if service.key_required:
        raise ValueError(f"--provider {provider} requires an API key in {' or '.join(service.key_vars)}")
    return None


def jev_retry_delay(headers: Any, attempt: int) -> float:
    """Back off exponentially, never sooner than the server's retry headers ask."""
    delay = min(2.0**attempt, 30.0)
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = headers.get(name) if headers is not None else None
        if value:
            try:
                return max(delay, float(value) * scale)
            except ValueError:
                pass
    return delay


def post_json(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    verbose_log: TextIO | None,
    service: str,
) -> tuple[Any, Any]:
    """POST JSON without following redirects; retry 408, 429, 5xx and transport failures."""
    raw_request = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    write_verbose(verbose_log, f"RAW REQUEST POST {endpoint}", raw_request)
    attempt = 0
    while True:
        request = Request(endpoint, data=raw_request.encode(), headers=headers, method="POST")
        try:
            with JEV_OPENER.open(request, timeout=timeout) as response:
                raw_response = response.read().decode("utf-8", errors="replace")
                response_headers = response.headers
                write_verbose(verbose_log, f"RAW RESPONSE HTTP {response.status}", raw_response)
            break
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            write_verbose(verbose_log, f"RAW RESPONSE HTTP {exc.code}", detail)
            if exc.code not in JEV_RETRY_STATUSES or attempt == JEV_MAX_RETRIES:
                raise RuntimeError(f"{service} returned HTTP {exc.code}: {detail}") from exc
            failure, delay = f"HTTP {exc.code}", jev_retry_delay(exc.headers, attempt)
        except OSError as exc:
            write_verbose(verbose_log, "TRANSPORT ERROR", str(exc))
            if attempt == JEV_MAX_RETRIES:
                raise RuntimeError(f"could not reach {service} at {endpoint}: {exc}") from exc
            failure, delay = str(exc), jev_retry_delay(None, attempt)
        attempt += 1
        print(
            f"warning: {service} request failed ({failure}); "
            f"retry {attempt}/{JEV_MAX_RETRIES} in {delay:.1f}s",
            file=sys.stderr,
        )
        time.sleep(delay)
    try:
        return json.loads(raw_response), response_headers
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{service} returned invalid JSON: {exc}") from exc


def ask_jev(
    service: SystemOneService,
    base_url: str,
    api_key: str | None,
    model: str,
    question: Question,
    timeout: float,
    verbose_log: TextIO | None,
) -> tuple[str | None, str]:
    """Ask one System One `choice` question; requests carry no key when `api_key` is None."""
    labels = [option.label for option in question.options]
    # Open-Jev and Laya serve one checkpoint and take no model field, so their model argument is only
    # the report label.
    payload: dict[str, Any] = {"model": model} if service.model_field else {}
    payload.update(
        state=question.prompt,
        questions={
            "answer": {
                "type": "choice",
                "instructions": JEV_INSTRUCTIONS,
                "criteria": {option.label: option.text for option in question.options},
            }
        },
    )
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    result, response_headers = post_json(
        base_url.rstrip("/") + service.path, payload, headers, timeout, verbose_log, service.name
    )
    request_id = response_headers.get(service.request_id_header) if service.request_id_header else None
    stored_response = json.dumps(
        {"request_id": request_id, "response": result},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        prediction = result["answers"]["answer"]["choice"]
    except (KeyError, TypeError):
        print(f"warning: invalid {service.name} response: {result!r}", file=sys.stderr)
        return None, stored_response
    if prediction not in labels:
        print(f"warning: {service.name} choice {prediction!r} is not in {labels}", file=sys.stderr)
        return None, stored_response
    return prediction, stored_response


def vllm_yes_no_ids(base_url: str, model: str, timeout: float) -> tuple[int, int]:
    """Token IDs of "Yes" and "No"; each must be a single token."""
    ids = []
    for word in ("Yes", "No"):
        tokenized, _ = post_json(
            f"{base_url.rstrip('/')}/tokenize",
            {"model": model, "prompt": word, "add_special_tokens": False},
            {"Content-Type": "application/json"},
            timeout,
            None,
            "vLLM",
        )
        tokens = tokenized.get("tokens") or []
        if len(tokens) != 1:
            raise ValueError(f"{word!r} is not a single token for {model}")
        ids.append(int(tokens[0]))
    return ids[0], ids[1]


def ask_vllm_yes_no(
    base_url: str,
    model: str,
    question: Question,
    timeout: float,
    verbose_log: TextIO | None,
    yes_no_ids: tuple[int, int],
) -> tuple[str | None, str]:
    """Score each option with Open-Jev's yes/no prompt: log P(Yes) - log P(No) at the answer."""
    base = base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    prompts = []
    for option in question.options:
        content = YES_NO_PROMPT.format(
            state=question.prompt, question=JEV_INSTRUCTIONS, label=option.label, text=option.text
        )
        tokenized, _ = post_json(
            f"{base}/tokenize",
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "add_generation_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            headers,
            timeout,
            verbose_log,
            "vLLM",
        )
        prompts.append(tokenized["tokens"])
    yes, no = yes_no_ids
    completion, _ = post_json(
        f"{base}/v1/completions",
        {
            "model": model,
            "prompt": prompts,
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": 1,
            "logprob_token_ids": [yes, no],
            "return_tokens_as_token_ids": True,
        },
        headers,
        timeout,
        verbose_log,
        "vLLM",
    )
    usage = completion.get("usage") or {}
    record: dict[str, Any] = {
        "method": "yes-no",
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
        "response": completion,
    }
    try:
        scores = {}
        for choice in completion["choices"]:
            top = choice["logprobs"]["top_logprobs"][0]
            scores[question.options[choice["index"]].label] = top[f"token_id:{yes}"] - top[f"token_id:{no}"]
        if len(scores) != len(question.options):
            raise KeyError("missing option scores")
    except (KeyError, TypeError, IndexError):
        print(f"warning: invalid vLLM yes/no response: {completion!r}", file=sys.stderr)
        return None, json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    highest = max(scores.values())
    weights = {label: math.exp(score - highest) for label, score in scores.items()}
    total = sum(weights.values())
    probabilities = {label: weight / total for label, weight in weights.items()}
    prediction = max(probabilities, key=probabilities.__getitem__)
    # Open-Jev's choice confidence: the top probability rescaled so uniform is 0 and certain is 1.
    uniform = 1 / len(probabilities)
    confidence = 1.0 if len(probabilities) == 1 else (probabilities[prediction] - uniform) / (1 - uniform)
    record.update(scores=scores, probabilities=probabilities, confidence=confidence)
    return prediction, json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def ask_vllm_verbal(
    base_url: str,
    model: str,
    question: Question,
    timeout: float,
    seed: int,
    verbose_log: TextIO | None,
) -> tuple[str | None, str]:
    """Ask for the answer letter and a 0-1 confidence together in one JSON reply."""
    labels = [option.label for option in question.options]
    payload = verbal_payload(model, question, seed)
    payload.update(temperature=0, max_tokens=64)
    result, _ = post_json(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        payload,
        {"Content-Type": "application/json"},
        timeout,
        verbose_log,
        "vLLM",
    )
    usage = result.get("usage") or {}
    record: dict[str, Any] = {
        "method": "verbal",
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
        "response": result,
    }
    try:
        content = json.loads(result["choices"][0]["message"]["content"])
        prediction, confidence = content["answer"], content["confidence"]
    except (KeyError, TypeError, IndexError, json.JSONDecodeError):
        print(f"warning: invalid vLLM response: {result!r}", file=sys.stderr)
        return None, json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    if isinstance(confidence, (int, float)) and 0 <= confidence <= 1:
        record["confidence"] = float(confidence)
    else:
        print(f"warning: vLLM confidence {confidence!r} is not between 0 and 1", file=sys.stderr)
    if prediction not in labels:
        print(f"warning: vLLM answer {prediction!r} is not in {labels}", file=sys.stderr)
        prediction = None
    record["answer"] = prediction
    return prediction, json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def verbal_payload(model: str, question: Question, seed: int) -> dict[str, Any]:
    """The vllm-verbal request without sampling settings: the question, and a JSON reply with one of its
    letters and a 0-1 confidence."""
    schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": [option.label for option in question.options]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["answer", "confidence"],
        "additionalProperties": False,
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": VERBAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{VERBAL_INSTRUCTION}\n\nSoru 1 (kaynak sayfa {question.source_page}):\n{question.prompt}",
            },
        ],
        "seed": seed,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer_with_confidence", "schema": schema, "strict": True},
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }


def ask_vllm_vote(
    base_url: str,
    model: str,
    question: Question,
    timeout: float,
    seed: int,
    verbose_log: TextIO | None,
) -> tuple[str | None, str]:
    """The vllm-verbal request sampled VOTE_SAMPLES times with VOTE_SAMPLING. The answer is the most
    frequent letter (a tie goes to the letter sampled first), stored with every sample and the votes."""
    labels = [option.label for option in question.options]
    payload = verbal_payload(model, question, seed)
    payload.update(VOTE_SAMPLING, n=VOTE_SAMPLES, max_tokens=64)
    result, _ = post_json(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        payload,
        {"Content-Type": "application/json"},
        timeout,
        verbose_log,
        "vLLM",
    )
    usage = result.get("usage") or {}
    samples: list[dict[str, Any]] = []
    for choice in result.get("choices") or []:
        try:
            content = json.loads(choice["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            samples.append({"answer": None, "confidence": None})
            continue
        answer = content.get("answer") if content.get("answer") in labels else None
        confidence = content.get("confidence")
        samples.append({"answer": answer, "confidence": confidence if isinstance(confidence, (int, float)) else None})
    votes: dict[str, int] = {}
    for sample in samples:
        if sample["answer"] is not None:
            votes[sample["answer"]] = votes.get(sample["answer"], 0) + 1
    # max keeps the first of equal counts, and the dict keeps the order letters were first sampled.
    prediction = max(votes, key=votes.__getitem__) if votes else None
    if prediction is None:
        print(f"warning: no valid vLLM sample: {result!r}", file=sys.stderr)
    record = {
        "method": "vote",
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
        "samples": samples,
        "votes": votes,
        "answer": prediction,
    }
    return prediction, json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def shown_options(question: Question) -> list[dict[str, str]]:
    """The options as shown to the model. With --shuffle-options each also gets its original letter; with
    --replace-key-text the key's option names the option whose text it shows ("copied_from")."""
    options = [{"label": option.label, "text": option.text} for option in question.options]
    for option, original in zip(options, question.original_labels):
        option["original"] = original
    for option in options:
        if question.twin is not None and option["label"] == question.answer:
            option["copied_from"] = question.twin
    return options


def store_answers(
    connection: sqlite3.Connection,
    run_id: int,
    batch: list[tuple[int, Question]],
    predictions: list[str | None],
    raw_response: str,
    elapsed: float,
    request_seconds: float,
) -> None:
    """Store each answer under the question bank's letters, with the options as shown to the model.
    elapsed is the batch's share of the run's request time; request_seconds its own request's duration."""
    now = utc_now()
    records = [
        (
            run_id,
            ordinal,
            question.question_id,
            question.source_page,
            question.category,
            question.prompt,
            json.dumps(shown_options(question), ensure_ascii=False),
            question.status,
            question.original_label(question.answer),
            question.original_label(prediction),
            int(prediction == question.answer),
            raw_response,
            now,
            request_seconds,
        )
        for (ordinal, question), prediction in zip(batch, predictions)
    ]
    with connection:
        connection.executemany(
            """
            INSERT OR REPLACE INTO answers (
                run_id,ordinal,question_id,source_page,category,question,options_json,status,
                expected_answer,predicted_answer,correct,raw_response,answered_at,request_seconds
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            records,
        )
        count = len(records)
        duration = max(elapsed, 1e-9)
        connection.execute(
            """
            UPDATE runs SET timed_questions=timed_questions+?,timed_seconds=timed_seconds+?,
                questions_per_minute=((timed_questions+?)*60.0)/(timed_seconds+?),updated_at=?
            WHERE id=?
            """,
            (count, duration, count, duration, now, run_id),
        )


def ask_batch(
    args: argparse.Namespace, questions: list[Question], thinking: bool | str, verbose_log: TextIO | None
) -> tuple[list[str | None], str]:
    """One request to the run's provider: an answer per question, and the raw response to store."""
    if args.provider == "openai":
        return ask_openai(args.codex_bin, args.model, questions, args.timeout, str(thinking), verbose_log)
    if args.provider in SYSTEM_ONE_PROVIDERS:
        prediction, raw_response = ask_jev(
            SYSTEM_ONE[args.provider], args.jev_url, args.jev_api_key, args.model, questions[0], args.timeout, verbose_log
        )
        return [prediction], raw_response
    if args.provider == "vllm-yes-no":
        prediction, raw_response = ask_vllm_yes_no(
            args.vllm_url, args.model, questions[0], args.timeout, verbose_log, args.yes_no_ids
        )
        return [prediction], raw_response
    if args.provider == "vllm":
        return ask_vllm(args.vllm_url, args.model, questions, args.timeout, args.seed, thinking, verbose_log)
    if args.provider == "vllm-verbal":
        prediction, raw_response = ask_vllm_verbal(
            args.vllm_url, args.model, questions[0], args.timeout, args.seed, verbose_log
        )
        return [prediction], raw_response
    if args.provider == "vllm-vote":
        prediction, raw_response = ask_vllm_vote(
            args.vllm_url, args.model, questions[0], args.timeout, args.seed, verbose_log
        )
        return [prediction], raw_response
    if args.provider == "gemini":
        return ask_gemini(args.gemini_api_key, args.model, questions, args.timeout, args.gemini_thinking, verbose_log)
    if args.provider == "claude":
        return ask_claude(args.claude_bin, args.model, questions, args.timeout, args.claude_effort, verbose_log)
    return ask_ollama(
        args.ollama_url, args.model, questions, args.timeout, args.seed, thinking, args.num_ctx, verbose_log
    )


def evaluate(
    selection: Selection,
    connection: sqlite3.Connection,
    identity: RunIdentity,
    args: argparse.Namespace,
    thinking: bool | str,
    verbose_log: TextIO | None,
) -> tuple[int, int, dict[str, dict[str, int]]]:
    completed = {
        int(row["ordinal"])
        for row in connection.execute("SELECT ordinal FROM answers WHERE run_id=?", (identity.run_id,))
    }
    pending = [
        (ordinal, question)
        for ordinal, question in enumerate(selection.questions)
        if ordinal not in completed
    ]
    evaluated, correct, invalid, _ = score(connection, identity.run_id)
    total = len(selection.questions)
    if evaluated:
        print(f"Resuming with {evaluated}/{total} answers ({runtime_info(connection, identity.run_id, total-evaluated)})")
    batches = [pending[offset : offset + args.batch_size] for offset in range(0, len(pending), args.batch_size)]
    queue = iter(batches)

    def request(batch: list[tuple[int, Question]]) -> tuple[list[tuple[int, Question]], list[str | None], str, float, float]:
        started = time.monotonic()
        predictions, raw_response = ask_batch(args, [question for _, question in batch], thinking, verbose_log)
        return batch, predictions, raw_response, started, time.monotonic()

    # Request time is the time at least one request was in flight: the sum of the request times when
    # they run one at a time, and the wall-clock time when several overlap (--concurrency).
    covered_until = 0.0
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        in_flight = {executor.submit(request, batch) for batch in itertools.islice(queue, args.concurrency)}
        while in_flight:
            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for batch, predictions, raw_response, started, finished in sorted(
                (future.result() for future in done), key=lambda item: item[4]
            ):
                elapsed = max(finished - max(started, covered_until), 0.0)
                covered_until = max(covered_until, finished)
                store_answers(connection, identity.run_id, batch, predictions, raw_response, elapsed, finished - started)
                evaluation = [
                    {
                        "question_id": question.question_id,
                        "expected": question.answer,
                        "predicted": prediction,
                        "correct": prediction == question.answer,
                    }
                    for (_, question), prediction in zip(batch, predictions)
                ]
                write_verbose(verbose_log, "EVALUATION", json.dumps(evaluation, ensure_ascii=False, indent=2))
                previous = evaluated
                evaluated += len(batch)
                correct += sum(prediction == question.answer for (_, question), prediction in zip(batch, predictions))
                invalid += sum(prediction is None for prediction in predictions)
                if previous == 0 or evaluated == total or evaluated // args.progress_every != previous // args.progress_every:
                    print(
                        f"[{evaluated}/{total}] score={correct/evaluated:.2%} correct={correct} invalid={invalid} "
                        f"{runtime_info(connection, identity.run_id, total-evaluated)}",
                        flush=True,
                    )
                following = next(queue, None)
                if following is not None:
                    in_flight.add(executor.submit(request, following))
    evaluated, correct, invalid, categories = score(connection, identity.run_id)
    if evaluated != total:
        raise RuntimeError(f"result database contains {evaluated}/{total} expected answers")
    return correct, invalid, categories


def percent(correct: int, total: int) -> str:
    return f"{100*correct/total:.2f}%" if total else "n/a"


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def category_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
    match = re.match(r"(\d+)\.", item[0])
    return (int(match.group(1)) if match else sys.maxsize, item[0].casefold())


def read_results(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[str, dict[str, Any]] = {}
    for match in RESULT_PATTERN.finditer(path.read_text(encoding="utf-8")):
        try:
            result = json.loads(match.group(1))
            results[str(result["run_key"])] = result
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return results


def format_rate(result: dict[str, Any]) -> str:
    value = result.get("questions_per_minute")
    return f"{value:.1f}" if value else "—"


def format_cost(result: dict[str, Any]) -> str:
    value = result.get("cost_usd")
    return f"${value:.4f}" if value is not None else "—"


def dataset_label(result: dict[str, Any]) -> str:
    """The question bank's file name and the start of its SHA-256, which tell v1 and v2 runs apart."""
    return f"{Path(result['dataset']).name}@{result['dataset_sha256'][:8]}"


def variant_note(result: dict[str, Any]) -> str:
    """How the run differs from its configuration's main run, if it does."""
    notes = []
    if result.get("shuffle_options") is not None:
        notes.append(f"options shuffled (seed {result['shuffle_options']})")
    if result.get("replace_key_text") is not None:
        notes.append(f"correct option's text replaced (seed {result['replace_key_text']})")
    if result.get("question_list"):
        notes.append(f"questions from {result['question_list']}")
    if result.get("repeat") is not None:
        notes.append(f"repeat {result['repeat']}")
    return "".join(f", {note}" for note in notes)


def run_label(result: dict[str, Any]) -> str:
    """Provider, model, settings and run ID, for tables that list runs."""
    thinking = "" if result["thinking"] == "off" else f" ({result['thinking']})"
    return markdown_escape(
        f"{result.get('provider', 'ollama')} {result['model']}{thinking}{variant_note(result)}, run {result['run_id']}"
    )


def format_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def format_p(value: float) -> str:
    return "< 0.0001" if value < 0.0001 else f"{value:.4f}"


def group_lines(ranked: list[dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Accuracy by question group",
        "",
        "Reading: units 1–6; grammar: units 7–20. Missing markup: questions that refer to underlined or "
        "numbered words their text doesn't mark, with their number in parentheses; other: the rest. "
        "Without suspect: every question not marked `suspect`, for question banks that record statuses.",
        "",
        "| Run | Dataset | " + " | ".join(GROUP_LABELS.values()) + " |",
        "|---|---|" + "---:|" * len(GROUP_LABELS),
    ]
    for result in ranked:
        cells = []
        for name in GROUP_LABELS:
            group = result.get("groups", {}).get(name)
            if group is None:
                cells.append("—")
            else:
                cell = percent(group["correct"], group["questions"])
                cells.append(f"{cell} ({group['questions']})" if name == "missing_markup" else cell)
        lines.append(f"| {run_label(result)} | {dataset_label(result)} | " + " | ".join(cells) + " |")
    return lines


def confidence_lines(scored: list[dict[str, Any]]) -> list[str]:
    coverages = " | ".join(f"Accuracy at {coverage:.0%}" for coverage in bm.COVERAGES)
    lines = [
        "",
        "## Confidence",
        "",
        "Each answer's score is the probability of the chosen option for the providers that return "
        "option probabilities: Jev, Open-Jev, Liquid AI's d1, Laya, Perplexity's pplx-decider-v1-27b, "
        "vllm-yes-no, which computes them from Qwen's Yes/No token probabilities as Open-Jev does, and vllm, "
        "which reads them from the token probabilities of the answer letters the model writes. "
        "For vllm-verbal, claude, openai and gemini it is the confidence the model states, and for vllm-vote the "
        "share of its 10 samples that chose the answer. AUROC: the chance "
        "that a right answer scores higher than a wrong one; 0.5 is chance. AURC: the area under the "
        "risk–coverage curve, the error rate of the k highest-scored answers averaged over every k; "
        "lower is better. Accuracy at a coverage: on that share of the answers, highest scores first. "
        "ECE: the gap between score and accuracy over 10 equal-width score bins, weighted by answers. "
        "Brier: the mean squared difference between score and correctness (1 or 0). Answers with equal "
        "scores count as tied.",
        "",
        f"| Run | Dataset | Score | AUROC | AUROC 95% interval | AURC | {coverages} | ECE | Brier |",
        "|---|---|---|---:|---:|---:|" + "---:|" * len(bm.COVERAGES) + "---:|---:|",
    ]
    for result in scored:
        group = result["groups"]["all"]
        accuracy = " | ".join(f"{100 * value:.1f}%" for value in group["coverage_accuracy"].values())
        interval = group.get("auroc_interval")
        lines.append(
            f"| {run_label(result)} | {dataset_label(result)} | {result['score_source']} | "
            f"{format_score(group['auroc'])} | {'—' if interval is None else f'{interval[0]:.3f}–{interval[1]:.3f}'} | "
            f"{group['aurc']:.3f} | {accuracy} | {group['ece']:.3f} | {group['brier']:.3f} |"
        )
    names = [name for name in GROUP_LABELS if name != "all"]
    lines.extend(
        [
            "",
            "### Confidence by question group",
            "",
            "AUROC / ECE on the question groups defined above.",
            "",
            "| Run | Dataset | " + " | ".join(GROUP_LABELS[name] for name in names) + " |",
            "|---|---|" + "---:|" * len(names),
        ]
    )
    for result in scored:
        cells = []
        for name in names:
            group = result["groups"].get(name)
            cells.append("—" if group is None or "ece" not in group else f"{format_score(group['auroc'])} / {group['ece']:.3f}")
        lines.append(f"| {run_label(result)} | {dataset_label(result)} | " + " | ".join(cells) + " |")
    intervals = " | ".join(f"{low:.2f}–{high:.2f}" for low, high in bm.CONFIDENCE_BINS)
    lines.extend(
        [
            "",
            "### Accuracy by score",
            "",
            "Each cell gives the accuracy of the answers whose score falls in that interval and, in "
            "parentheses, how many there were. Intervals include their lower bound; the last also includes "
            "1.00. The chosen option's probability is at least 1 divided by the number of options.",
            "",
            f"| Run | Dataset | {intervals} |",
            "|---|---|" + "---:|" * len(bm.CONFIDENCE_BINS),
        ]
    )
    for result in scored:
        cells = " | ".join(
            f"{percent(interval['correct'], interval['questions'])} ({interval['questions']})"
            if interval["questions"]
            else "— (0)"
            for interval in result["confidence_bins"]
        )
        lines.append(f"| {run_label(result)} | {dataset_label(result)} | {cells} |")
    lines.extend(
        [
            "",
            "### Very sure and doubtful answers",
            "",
            f"Median score of the right and of the wrong answers, and how many answers scored {bm.SURE_SCORE:.2f} or more "
            f"and below {bm.DOUBTFUL_SCORE:.2f}, with the share of them that are right and its 95% Wilson interval.",
            "",
            f"| Run | Dataset | Score | Median, right | Median, wrong | {bm.SURE_SCORE:.2f} or more | Right | Interval | "
            f"Below {bm.DOUBTFUL_SCORE:.2f} | Right |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in scored:
        extremes = result["confidence_extremes"]
        sure, doubtful = extremes["sure"], extremes["doubtful"]
        lines.append(
            f"| {run_label(result)} | {dataset_label(result)} | {result['score_source']} | "
            f"{format_score(extremes['median_right'])} | {format_score(extremes['median_wrong'])} | "
            f"{sure['questions']} | {percent(sure['correct'], sure['questions']) if sure['questions'] else '—'} | "
            + (f"{100 * sure['interval'][0]:.1f}–{100 * sure['interval'][1]:.1f}%" if sure.get("interval") else "—")
            + " | "
            f"{doubtful['questions']} | {percent(doubtful['correct'], doubtful['questions']) if doubtful['questions'] else '—'} |"
        )
    return lines


def summary_lines(ranked: list[dict[str, Any]], versions: list[dict[str, Any]]) -> list[str]:
    changes = {item["newer"]: item["unchanged"] for item in versions}
    lines = [
        "",
        "## Accuracy, stability, cost and speed",
        "",
        "Changed answer: the share of questions, asked identically, on which the run chose a different "
        "option than the same configuration's run on the previous question bank (see Question bank "
        "versions). Runs with 16 questions per request saw different neighbouring questions in the two runs. "
        "Cost per 1,000 questions and request seconds per question come from the score table; for runs "
        "with several requests at a time, request time is the time any request was in flight. Output "
        "tokens per question: the tokens each API or server reports generating, divided by the questions; "
        "they include thinking and reasoning tokens. The decision models return option probabilities: "
        "d1, Open-Jev and Laya report no output tokens, Perplexity 1 and Jev a fixed 52 per question.",
        "",
        "| Run | Dataset | Accuracy | Changed answer | Cost per 1,000 questions (USD) | Seconds per question | "
        "Output tokens per question | Questions per request |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in ranked:
        unchanged = changes.get(result["run_key"])
        changed = (
            f"{percent(unchanged['changed_answer'], unchanged['questions'])} ({unchanged['changed_answer']} of {unchanged['questions']})"
            if unchanged and unchanged["questions"]
            else "—"
        )
        cost = result.get("cost_usd")
        lines.append(
            f"| {run_label(result)} | {dataset_label(result)} | {percent(result['correct'], result['evaluated'])} | {changed} | "
            + ("—" if cost is None else f"${1000 * cost / result['evaluated']:.3f}")
            + f" | {result['timed_seconds'] / result['evaluated']:.2f}"
            + f" | {result['output_tokens'] / result['evaluated']:.1f} | {result['batch_size']} |"
        )
    return lines


def doubt_lines(doubts: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    frontier = ", ".join(f"{model} ({thinking})" for _, model, thinking in CASCADE_FRONTIER_RUNS)
    lines = [
        "",
        "## Decision-model doubt and frontier mistakes",
        "",
        "Whether a decision model's uncertainty, the entropy of its option probabilities in bits, points at "
        f"the questions the frontier runs on the same questions ({frontier}) got wrong. Spearman: rank "
        "correlation between the entropy and how many of the frontier runs got the question wrong. p: the "
        f"share of {DOUBT_SHUFFLES} seeded shuffles of those counts within each book unit that reach the observed "
        f"correlation, counting the observed order as one, so the smallest possible p is 1/{DOUBT_SHUFFLES + 1}; a "
        "correlation that only separates easy units from hard ones fails. AUROC: the chance "
        "that a question some frontier run got wrong has higher entropy than one they all got right. Most "
        "uncertain tenth: how many of the questions some frontier run got wrong fall in the decision model's "
        "most uncertain 10% of questions; chance is 10%.",
        "",
        "| Decision model | Dataset | Questions | Spearman | p | AUROC | Most uncertain tenth |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in doubts:
        decision, tenth = results[item["decision"]], item["top_tenth"]
        lines.append(
            f"| {run_label(decision)} | {dataset_label(decision)} | {item['questions']} | {format_score(item['rho'])} | "
            f"{'—' if item['p'] is None else format_p(item['p'])} | {format_score(item['auroc'])} | "
            f"{tenth['with_mistake']} of {tenth['all_with_mistake']} "
            f"({percent(tenth['with_mistake'], tenth['all_with_mistake']) if tenth['all_with_mistake'] else '—'}) |"
        )
    return lines


def source_lines(sources: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "### Confidence sources on the same answers",
        "",
        "Each vllm-verbal run's own answers, scored three ways: the confidence the model states with each "
        "answer, and the probability that the vllm-yes-no run of the same model and the Open-Jev runs give "
        "the option it chose. The answers stay the same, so only the confidence source changes. Interval: "
        f"95% bootstrap over {bm.BOOTSTRAP_RESAMPLES} resamples of the questions, those sharing a passage "
        "together.",
        "",
        "| Answers | Correct | Confidence from | AUROC | 95% interval |",
        "|---|---:|---|---:|---:|",
    ]
    for item in sources:
        answers = results[item["answers"]]
        for entry in item["sources"]:
            other = results[entry["run"]]
            if entry["run"] == item["answers"]:
                kind = "its stated confidence"
            elif other.get("provider") in VOTE_PROVIDERS:
                kind = f"{run_label(other)}, share of its samples"
            else:
                kind = f"{run_label(other)}, probability"
            interval = entry["auroc_interval"]
            lines.append(
                f"| {run_label(answers)} | {item['correct']} of {item['questions']} | {kind} | {format_score(entry['auroc'])} | "
                + ("—" if interval is None else f"{interval[0]:.3f}–{interval[1]:.3f}")
                + " |"
            )
    return lines


def paired_lines(paired: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Paired comparisons",
        "",
        "Each run against the next one in the ranking by accuracy, over the same questions, plus the "
        "pairs Open-Jev / vllm-yes-no, Perplexity / Jev, GLiDE / Perplexity and Gemma 4 31B / GLiDE. "
        "Difference: the first run's accuracy minus the "
        "second's, in points, with a paired 95% interval. Only first, only second: the questions only that "
        "run answered correctly. p: exact two-sided McNemar test on those two counts. Holm p: p adjusted "
        "with Holm's method for all the comparisons over the same questions.",
        "",
        "| First | Second | Dataset | Difference | 95% interval | Only first | Only second | p | Holm p |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in paired:
        first, second = results[item["first"]], results[item["second"]]
        lines.append(
            f"| {run_label(first)} | {run_label(second)} | {dataset_label(first)} | "
            f"{100 * item['difference']:+.1f} | {100 * item['low']:+.1f} to {100 * item['high']:+.1f} | "
            f"{item['first_only']} | {item['second_only']} | {format_p(item['p'])} | {format_p(item['p_holm'])} |"
        )
    return lines


def tied_group_lines(groups: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Tied groups",
        "",
        "Every pair of runs over the same questions, compared with the exact paired test and Holm's method "
        f"over all those pairs. Two runs are told apart when the adjusted p is below {TIE_ALPHA:g}. Runs that "
        "share a letter are told apart by no comparison; a run with two letters is tied with runs of both "
        "groups that are not tied with each other. Runs are in the order of the score table.",
        "",
        "| Run | Dataset | Accuracy | Group | Pairs tested |",
        "|---|---|---:|---|---:|",
    ]
    for item in groups:
        result = results[item["run_key"]]
        lines.append(
            f"| {run_label(result)} | {dataset_label(result)} | {100 * result['correct'] / result['evaluated']:.2f}% | "
            f"{item['letters']} | {item['pairs']} |"
        )
    return lines


def cascade_lines(cascades: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Cascade",
        "",
        "A decision model answers the questions where its score, the chosen option's probability, is at "
        "least a threshold, and passes the rest to a frontier run. In sample: the lowest threshold that "
        "keeps the frontier run's accuracy, chosen and scored on all questions. Held out: the threshold is "
        "chosen the same way on a random half of the questions and scored on the other half, over "
        f"{cascades[0]['held_out']['splits']} seeded splits, giving the mean share the decision model "
        "answers, the mean accuracy difference from the frontier run alone in points, and how often the "
        "cascade did worse. Cost: the decision model's run cost plus the frontier run's cost for the share "
        "of questions passed on.",
        "",
        "| Decision model | Frontier run | Dataset | Frontier accuracy | Answered | Accuracy | Cost (USD) | "
        "Frontier cost (USD) | Answered, held out | Difference, held out | Worse, held out |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in cascades:
        decision, frontier = results[item["decision"]], results[item["frontier"]]
        in_sample, held_out = item["in_sample"], item["held_out"]
        costs = (decision.get("cost_usd"), frontier.get("cost_usd"))
        cost = "—" if None in costs else f"${costs[0] + costs[1] * (1 - in_sample['answered']):.2f}"
        frontier_cost = "—" if costs[1] is None else f"${costs[1]:.2f}"
        lines.append(
            f"| {run_label(decision)} | {run_label(frontier)} | {dataset_label(decision)} | "
            f"{100 * item['frontier_accuracy']:.1f}% | {100 * in_sample['answered']:.1f}% | "
            f"{100 * in_sample['accuracy']:.1f}% | {cost} | {frontier_cost} | "
            f"{100 * held_out['answered']:.1f}% | {100 * held_out['difference']:+.2f} | "
            f"{100 * held_out['worse']:.0f}% |"
        )
    return lines


def repeat_lines(repeats: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Run-to-run variation (repeats)",
        "",
        "Each configuration run several times on the same questions: its first run and its repeats "
        "(`--repeat`). Only questions asked identically in every run count. Accuracy: the mean over the "
        "runs, with the lowest and highest. Changed answer: questions on which the runs did not all choose "
        "the same option. Wrong every time: questions every run got wrong with the same option (mistakes "
        "no repeat would reveal), out of those any run got wrong. Score spread: the median, over the "
        "questions, of the largest minus the smallest score of the chosen options; identical: questions "
        "scored the same in every run. Wrong at 0.99 or more: each run's count, and the questions wrong at "
        "that score in every run.",
        "",
        "| Configuration | Runs | Questions | Accuracy | Changed answer | Wrong every time, same option | "
        "Score spread | Identical scores | Wrong at 0.99 or more | In every run |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in repeats:
        runs = [results[key] for key in item["run_keys"]]
        if not item["questions"]:
            continue
        first, accuracy = runs[0], item["accuracy"]
        configuration = markdown_escape(f"{first.get('provider', 'ollama')} {first['model']}") + (
            "" if first["thinking"] == "off" else f" ({first['thinking']})"
        )
        lines.append(
            f"| {configuration} | {', '.join(str(run['run_id']) for run in runs)} | {item['questions']} | "
            f"{100 * sum(accuracy) / len(accuracy):.2f}% ({100 * min(accuracy):.1f}–{100 * max(accuracy):.1f}) | "
            f"{percent(item['changed_answer'], item['questions'])} ({item['changed_answer']}) | "
            f"{item['wrong_every_run_same']} of {item['wrong_any']} ({percent(item['wrong_every_run_same'], item['wrong_any'])}) | "
            f"{format_score(item['score_spread_median'])} | "
            + (f"{item['score_identical']} of {item['scored']}" if item["scored"] else "—")
            + f" | {' / '.join(str(count) for count in item['sure_wrong'])} | {item['sure_wrong_every_run']} |"
        )
    return lines


def pipeline_lines(pipelines: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Cascade as a pipeline",
        "",
        "Each plan (`cascade_pipeline.py`) splits the questions into two halves, keeping questions that "
        "share a passage together, and fixes the threshold on one half: the lowest that keeps the frontier "
        "run's accuracy there. On the other half, the held-out questions, the decision model answers the "
        "questions at or above the threshold, from its stored run, and a new frontier run answers the rest "
        "in batches of their own. The frontier configuration is run again on all held-out questions for "
        "comparison. Simulated: the same split scored with the stored whole-set runs, as the Cascade table "
        "does. Tolerance: the accuracy loss accepted before the runs. Cost and time: the decision model's "
        "share of its run plus the new frontier run, against the frontier run on all held-out questions.",
        "",
        "| Decision model | Frontier run | Held out | Threshold | Answered by the decision model | Simulated: "
        "cascade / frontier | Pipeline / frontier alone | Difference | 95% interval | p | Tolerance | Cost (USD) | "
        "Request time (min) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for item in pipelines:
        decision, frontier = results[item["decision"]], results[item["frontier"]]
        simulated = item["simulated"]
        measured = item.get("measured")
        common = (
            f"| {run_label(decision)} | {run_label(frontier)} | {item['held_out']} | {item['threshold']:.3f} | "
            f"{item['routed']} ({percent(item['routed'], item['held_out'])}) | "
            f"{100 * simulated['accuracy']:.1f}% / {100 * simulated['frontier_accuracy']:.1f}% | "
        )
        if measured is None:
            lines.append(common + f"not run yet | — | — | — | {item['tolerance_points']:.1f} points | — | — |")
            continue
        costs = (measured["cost_usd"], measured["frontier_cost_usd"])
        lines.append(
            common
            + f"{100 * measured['accuracy']:.1f}% / {100 * measured['frontier_accuracy']:.1f}% | "
            f"{100 * measured['difference']:+.1f} | {100 * measured['low']:+.1f} to {100 * measured['high']:+.1f} | "
            f"{format_p(measured['p'])} | {item['tolerance_points']:.1f} points, "
            + ("kept" if measured["within_tolerance"] else "missed")
            + " | "
            + ("—" if None in costs else f"${costs[0]:.2f} / ${costs[1]:.2f}")
            + f" | {measured['request_seconds'] / 60:.1f} / {measured['frontier_request_seconds'] / 60:.1f} |"
        )
    return lines


def key_replacement_lines(replaced: list[dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Correct option replaced",
        "",
        "Runs with `--replace-key-text`: each question's correct option shows the text of a randomly chosen "
        "wrong option, its twin, so no option is right and the original letter shows the same text as the "
        "twin. The options give no reason to prefer the original letter over its twin except by position: "
        "single numerals (I, II, … or 1, 2, …) and numeral combinations (I ve II, Yalnız III) come in a "
        "fixed order that the replaced option breaks, so a model that works out the answer can find its "
        "slot. Only text options therefore measure remembered letters: a clear excess of original letters "
        "there means the model remembers which letter answers the question. Options are classified as "
        "shown. These runs are left out of the accuracy, confidence, paired and cascade tables; their score "
        "counts original letters. p: exact two-sided sign test of original letters against twins.",
        "",
        "| Run | Dataset | Options | Questions | Original letter | Its twin | Another option | Invalid | p |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in replaced:
        for shape, label in (*OPTION_SHAPES.items(), ("all", "All")):
            picks = result["key_replacement"]["shapes"][shape]
            questions = sum(picks[name] for name in KEY_REPLACEMENT_PICKS)
            if not questions:
                continue
            lines.append(
                f"| {run_label(result)} | {dataset_label(result)} | {label} | {questions} | "
                + " | ".join(f"{percent(picks[name], questions)} ({picks[name]})" for name in ("key", "twin", "other"))
                + f" | {picks['invalid']} | {format_p(picks['p'])} |"
            )
    intervals = " | ".join(f"{low:.2f}–{high:.2f}" for low, high in bm.CONFIDENCE_BINS)
    lines.extend(
        [
            "",
            "### Confidence with the correct option replaced",
            "",
            "Each answer's score as defined under Confidence (the stated confidence for openai, claude and "
            "vllm-verbal, the chosen option's probability for the others), by option shape and by what the "
            "model picked. Mean: the answers' mean score. Unchanged mean: the mean score the same "
            "configuration gave the same questions with their options unchanged, in the run named in the "
            "Unchanged column. The interval columns count answers by score; intervals include their lower "
            "bound and the last also includes 1.00. No option is right, so every confident answer is wrong.",
            "",
            f"| Run | Unchanged | Options | Picked | Answers | Mean | Unchanged mean | {intervals} |",
            "|---|---|---|---|---:|---:|---:|" + "---:|" * len(bm.CONFIDENCE_BINS),
        ]
    )
    for result in replaced:
        data = result["key_replacement"]
        unchanged = "—" if data["unchanged_run"] is None else f"run {data['unchanged_run']}"
        for shape, label in (*OPTION_SHAPES.items(), ("all", "All")):
            for pick, pick_label in (("key", "Original letter"), ("twin", "Its twin"), ("other", "Another option"), ("all", "Any")):
                summary = data["shapes"][shape]["confidence"][pick]
                if not summary["answers"]:
                    continue
                lines.append(
                    f"| {run_label(result)} | {unchanged} | {label} | {pick_label} | {summary['answers']} | "
                    f"{format_score(summary['mean'])} | {format_score(summary['unchanged_mean'])} | "
                    + " | ".join(str(count) for count in summary["bins"])
                    + " |"
                )
    return lines


def version_lines(versions: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "",
        "## Question bank versions",
        "",
        "The same configuration on two versions of the question bank, older first. Changed: questions "
        "whose prompt or key differs between the versions, with accuracy before and after and an exact "
        "McNemar p-value. Unchanged: questions asked identically, which show the run-to-run variation "
        "(0 for runs that always answer alike). Flipped: answers that went from right to wrong or back. "
        "Changed answer: answers with a different option, right or wrong. Repeated mistakes: the newer "
        "run's wrong answers on these questions that chose the same option as the older run, mistakes "
        "that asking again would not have revealed. New: questions only the newer version scores.",
        "",
        "| Run | From → to | Changed | Before → after | p | Unchanged | Before → after | Flipped | Changed answer | "
        "Repeated mistakes | New |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def moved(part: dict[str, Any]) -> str:
        if not part["questions"]:
            return "—"
        return f"{percent(part['older_correct'], part['questions'])} → {percent(part['newer_correct'], part['questions'])}"

    for item in sorted(versions, key=lambda item: -results[item["newer"]]["correct"]):
        older, newer = results[item["older"]], results[item["newer"]]
        changed, unchanged, added = item["changed"], item["unchanged"], item["added"]
        lines.append(
            f"| {run_label(newer)} | {dataset_label(older)} → {dataset_label(newer)} | {changed['questions']} | "
            f"{moved(changed)} | {format_p(changed['p']) if changed['questions'] else '—'} | {unchanged['questions']} | "
            f"{moved(unchanged)} | {unchanged.get('flipped', '—')} | {unchanged.get('changed_answer', '—')} | "
            + (
                f"{unchanged['repeated_mistakes']} of {unchanged['newer_wrong']}"
                if unchanged["questions"] and unchanged["newer_wrong"]
                else "—"
            )
            + " | "
            + (f"{added['newer_correct']} of {added['questions']}" if added["questions"] else "—")
            + " |"
        )
    return lines


def render_report(results: dict[str, dict[str, Any]], comparisons: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# Turkish Question Bank — Model Benchmark",
        "",
        "Every run is graded against its question bank as it stands now: answers to questions the bank has "
        "since excluded are left out of every figure except time, tokens and cost, and correctness follows "
        "its current keys. The Dataset column names the bank version the run used.",
        "",
        "Questions/min counts request time only. Cost: Jev and Open-Jev at TypeSafe's System One "
        "price ($0.042 per 1M input tokens, output free) on the input tokens each API reports; "
        "Liquid AI's d1:free at $0, the free d1 model (Liquid publishes no d1 price); none for "
        "Laya, which runs on local weights; Perplexity's pplx-decider-v1-27b at its Decisions API "
        "price ($0.04 per 1M input tokens, output free); the vllm-yes-no and vllm-verbal entries (Qwen) "
        "at $0.40 / $2.40 per 1M input / output tokens on the tokens vLLM reports; none for the Ollama "
        "and vllm entries, which run on local weights; Claude "
        "at Anthropic's API list price (Opus 5.5: $4 / $20, Sonnet 5.5: $2 / $10 per 1M input / output "
        "tokens) on the tokens Claude Code reports, although those runs use the Claude subscription; "
        "OpenAI at its API list price (GPT-6 Astra: $10 input, $1 cached input, $12.50 cache write and "
        "$50 output per 1M tokens) on the tokens Codex reports, although those runs use the ChatGPT "
        "subscription. Dataset: the question bank's file name and the first 8 hex digits of its SHA-256.",
        "",
        "| Provider | Model | Thinking | Dataset | Questions | Score | Correct | Invalid | Batch | Questions/min | Cost (USD) | Updated (UTC) |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    ordered = sorted(results.values(), key=lambda item: (item["model"].casefold(), item["updated"]))
    for result in ordered:
        lines.append(
            f"| {result.get('provider', 'ollama')} | {markdown_escape(result['model'] + variant_note(result))} | "
            f"{result['thinking']} | {dataset_label(result)} | "
            f"{result['evaluated']} | {percent(result['correct'], result['evaluated'])} | "
            f"{result['correct']} | {result['invalid']} | {result['batch_size']} | "
            f"{format_rate(result)} | {format_cost(result)} | {result['updated']} |"
        )
    # Runs with a replaced key have no right option to score; they get their own table. Repeats and runs
    # on part of the questions have their own sections too.
    replaced = [result for result in results.values() if result.get("replace_key_text") is not None]
    ranked = sorted(
        (result for result in results.values() if in_main_tables(result)),
        key=lambda item: (-item["correct"] / item["evaluated"], item["run_id"]),
    )
    if comparisons.get("versions") is not None:
        lines.extend(summary_lines(ranked, comparisons["versions"]))
    lines.extend(group_lines(ranked))
    scored = [result for result in ranked if result.get("score_source")]
    if scored:
        lines.extend(confidence_lines(scored))
    if comparisons.get("sources"):
        lines.extend(source_lines(comparisons["sources"], results))
    if comparisons["paired"]:
        lines.extend(paired_lines(comparisons["paired"], results))
    if comparisons.get("groups"):
        lines.extend(tied_group_lines(comparisons["groups"], results))
    if comparisons["cascades"]:
        lines.extend(cascade_lines(comparisons["cascades"], results))
    if comparisons.get("doubts"):
        lines.extend(doubt_lines(comparisons["doubts"], results))
    if comparisons.get("versions"):
        lines.extend(version_lines(comparisons["versions"], results))
    if comparisons.get("repeats"):
        lines.extend(repeat_lines(comparisons["repeats"], results))
    if comparisons.get("pipelines"):
        lines.extend(pipeline_lines(comparisons["pipelines"], results))
    if replaced:
        lines.extend(key_replacement_lines(sorted(replaced, key=lambda item: item["run_id"])))
    for result in ordered:
        details = [f"Invalid model responses: {result['invalid']}"]
        if result.get("questions_per_minute"):
            details.append(
                f"Throughput: {format_rate(result)} questions/min "
                f"({result['timed_seconds'] / 60:.1f} min of request time"
                + (f", {result['concurrency']} requests at a time" if result.get("concurrency", 1) > 1 else "")
                + ")"
            )
        if result.get("cost_usd") is not None:
            cache = ", ".join(
                f"{result[key]:,} {label}"
                for key, label in (
                    ("cached_input_tokens", "cached"),
                    ("cache_write_input_tokens", "written to cache"),
                )
                if result.get(key)
            )
            details.append(
                f"Cost: {format_cost(result)} for {result['input_tokens']:,} input "
                + (f"({cache}) " if cache else "")
                + f"and {result['output_tokens']:,} output tokens"
            )
        else:
            details.append(
                f"Tokens: {result['input_tokens']:,} input and {result['output_tokens']:,} output, with no price "
                "to apply"
            )
        options = [] if result.get("shuffle_options") is None else [f"Options: shuffled with seed {result['shuffle_options']}  "]
        if result.get("replace_key_text") is not None:
            options.append(f"Correct option: shows a random wrong option's text, seed {result['replace_key_text']}  ")
        lines.extend(
            [
                "",
                f"## `{result['model'].replace('`', '')}` — run {result['run_id']}",
                f"Provider: {result.get('provider', 'ollama')}  ",
                "",
                f"Source database: `{result['dataset']}` (SHA-256 {result['dataset_sha256'][:8]}…)  ",
                f"Result database: `{result['database']}`  ",
                f"Selection: {result['evaluated']} of {result['eligible_total']} eligible questions  ",
                *(
                    [f"Graded against the question bank as it is now: {result['excluded_since_run']} answers left out, their questions since excluded  "]
                    if result.get("excluded_since_run")
                    else []
                ),
                f"Skipped extraction rows: `{json.dumps(result['skipped'], ensure_ascii=False, sort_keys=True)}`  ",
                f"Batch size: {result['batch_size']}  ",
                *options,
                f"Thinking: {result['thinking']}  ",
                f"Context window: {result['num_ctx'] or 'model default'}  ",
                f"Overall: **{percent(result['correct'], result['evaluated'])}** ({result['correct']} / {result['evaluated']})  ",
                *(f"{line}  " for line in details[:-1]),
                details[-1],
                "",
                "| Unit | Score | Correct / Questions |",
                "|---|---:|---:|",
            ]
        )
        for category, counts in sorted(
            result["categories"].items(), key=category_sort_key
        ):
            lines.append(
                f"| {markdown_escape(category)} | {percent(counts['correct'], counts['total'])} | "
                f"{counts['correct']} / {counts['total']} |"
            )
        lines.extend(["", f"<!-- benchmark-result: {json.dumps(result, ensure_ascii=False, separators=(',', ':'))} -->"])
    lines.extend(["", f"<!-- benchmark-analysis: {json.dumps(comparisons, ensure_ascii=False, separators=(',', ':'))} -->"])
    return "\n".join(lines) + "\n"


def answer_usage(
    provider: str, question_id: int, raw_response: str
) -> tuple[dict[str, int], float | None]:
    """Token counts of the request behind one answer, and the answer's score.

    The score is the chosen option's probability for PROBABILITY_PROVIDERS and the stated confidence
    for the others, or None when the response has neither. input_tokens counts every prompt token
    (Ollama: the ones it evaluated, without the part it reused from its prompt cache); output_tokens
    includes thinking and reasoning tokens. For Codex, the cached and cache-write parts of the input
    are also given.
    """
    record = json.loads(raw_response)
    score = None
    if provider in SYSTEM_ONE_PROVIDERS:
        response = record["response"]
        usage = response.get("usage") or {}
        answer = (response.get("answers") or {}).get("answer") or {}
        score = (answer.get("probabilities") or {}).get(answer.get("choice"))
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    elif provider == "claude":
        usage = (record.get("output") or {}).get("usage") or {}
        score = ((record.get("answers") or {}).get(str(question_id)) or {}).get("confidence")
        input_tokens = sum(
            int(usage.get(key) or 0)
            for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        output_tokens = usage.get("output_tokens")
    elif provider == "gemini":
        usage = (record.get("response") or {}).get("usageMetadata") or {}
        score = ((record.get("answers") or {}).get(str(question_id)) or {}).get("confidence")
        input_tokens = usage.get("promptTokenCount")
        # Thinking is billed as output.
        output_tokens = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
    elif provider == "openai":
        usage = record.get("usage") or {}
        score = ((record.get("answers") or {}).get(str(question_id)) or {}).get("confidence")
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    elif provider == "vllm":
        # vLLM's response, stored as it came apart from the token log probabilities (see ask_vllm).
        usage = record.get("usage") or {}
        answer = (record.get("answers") or {}).get(str(question_id)) or {}
        score = (answer.get("probabilities") or {}).get(answer.get("answer"))
        input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    elif provider in VOTE_PROVIDERS:
        usage = record.get("usage") or {}
        votes = record.get("votes") or {}
        samples = sum(votes.values())
        score = votes.get(record.get("answer"), 0) / samples if samples else None
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    elif provider in VLLM_PROVIDERS:
        usage = record.get("usage") or {}
        # vllm-yes-no answers with the most probable option.
        probabilities = (record.get("probabilities") or {}).values()
        score = max(probabilities, default=None) if provider == "vllm-yes-no" else record.get("confidence")
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    else:
        # Ollama's response, stored as it came.
        input_tokens, output_tokens = record.get("prompt_eval_count"), record.get("eval_count")
    tokens = {"input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0)}
    if provider == "openai":
        for key in ("cached_input_tokens", "cache_write_input_tokens"):
            tokens[key] = int(usage.get(key) or 0)
    return tokens, float(score) if isinstance(score, (int, float)) else None


def answer_groups(row: sqlite3.Row) -> list[str]:
    """The GROUP_LABELS groups a stored answer belongs to. Reading and grammar need a numbered book unit."""
    unit = re.match(r"(\d+)\.", row["category"])
    groups = ["all"]
    if unit:
        groups.append("reading" if int(unit.group(1)) in READING_UNITS else "grammar")
    options = sorted(json.loads(row["options_json"]), key=lambda option: option.get("original", option["label"]))
    lost = any(missing_markup(row["question"], [option["text"] for option in options]))
    groups.append("missing_markup" if lost else "marked")
    if row["status"] != "suspect":
        groups.append("without_suspect")
    return groups


def run_metrics(connection: sqlite3.Connection, run_key: str, search_dir: Path) -> dict[str, Any]:
    """Request time, token counts and accuracy by question group for any run; cost and confidence metrics
    where the provider has them, with bootstrap intervals clustered by passage. Time, tokens and cost cover
    every request the run made; everything else is graded against the question bank as it stands now
    (graded_answers), including the run's totals and units."""
    run = connection.execute(
        "SELECT id,model,provider,timed_seconds,questions_per_minute,replace_key_text,thinking_mode,batch_size,"
        "dataset,dataset_sha256,selection_sha256 FROM runs WHERE run_key=?",
        (run_key,),
    ).fetchone()
    if run is None:
        return {}
    provider = run["provider"]
    metrics: dict[str, Any] = {
        "timed_seconds": float(run["timed_seconds"]),
        "questions_per_minute": run["questions_per_minute"],
    }
    totals = dict.fromkeys(
        ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"), 0
    )
    requests: set[bytes] = set()
    request_seconds: list[float] = []
    stored = 0
    for row in connection.execute("SELECT question_id,raw_response,request_seconds FROM answers WHERE run_id=?", (run["id"],)):
        stored += 1
        # Batched providers store one response for every answer in the request; count it once.
        request = hashlib.sha256(row["raw_response"].encode()).digest()
        if request not in requests:
            requests.add(request)
            for key, count in answer_usage(provider, row["question_id"], row["raw_response"])[0].items():
                totals[key] += count
            if row["request_seconds"] is not None:
                request_seconds.append(float(row["request_seconds"]))
    members: dict[str, list[tuple[float | None, int]]] = {}
    clusters = passage_clusters(run["dataset"], str(search_dir))
    # The passage cluster of each scored answer, per group, in the order of that group's scored answers.
    scored_clusters: dict[str, list[str]] = {}
    categories: dict[str, dict[str, int]] = {}
    graded = graded_answers(connection, run_key, run["dataset"], search_dir)
    has_status = False
    for row in graded:
        score = answer_usage(provider, row["question_id"], row["raw_response"])[1]
        has_status = has_status or row["status"] is not None
        for group in answer_groups(row):
            members.setdefault(group, []).append((score, int(row["correct"])))
            if score is not None:
                scored_clusters.setdefault(group, []).append(clusters.get(int(row["question_id"]), f"question {row['question_id']}"))
        unit = categories.setdefault(row["category"], {"correct": 0, "total": 0})
        unit["correct"] += int(row["correct"])
        unit["total"] += 1
    metrics.update(
        evaluated=len(graded),
        correct=sum(int(row["correct"]) for row in graded),
        invalid=sum(row["predicted_answer"] is None for row in graded),
        categories=dict(sorted(categories.items())),
        excluded_since_run=stored - len(graded),
    )
    bank = current_bank(run["dataset"], str(search_dir))
    metrics.update(
        graded_sha256=bank[0] if bank else None,
    )
    if not has_status:
        members.pop("without_suspect", None)
    groups: dict[str, dict[str, Any]] = {}
    for name in GROUP_LABELS:
        answers = members.get(name)
        if not answers:
            continue
        group: dict[str, Any] = {"questions": len(answers), "correct": sum(correct for _, correct in answers)}
        scored = [(score, correct) for score, correct in answers if score is not None]
        if scored:
            ranking = bm.ranking_metrics(scored)
            calibration = bm.calibration(scored)
            group.update(
                scored=len(scored),
                auroc=ranking["auroc"],
                aurc=ranking["aurc"],
                coverage_accuracy=ranking["coverage_accuracy"],
                ece=calibration["ece"],
                brier=calibration["brier"],
            )
            if name == "all":
                bootstrap = bm.bootstrap_ranking(scored, scored_clusters[name])
                group.update(auroc_interval=bootstrap["auroc"], coverage_intervals=bootstrap["coverage_accuracy"])
                metrics.update(
                    score_source=(
                        "probability" if provider in PROBABILITY_PROVIDERS else "votes" if provider in VOTE_PROVIDERS else "stated"
                    ),
                    risk_coverage=ranking["risk_coverage"],
                    reliability=calibration["reliability"],
                    confidence_bins=bm.binned_accuracy(scored),
                    confidence_extremes=bm.score_extremes(scored),
                )
                # The same counts before the key audit, with the questions it excluded graded by the printed
                # key; only for runs that answered those questions.
                everything = graded_answers(connection, run_key, run["dataset"], search_dir, keep_excluded=True)
                if len(everything) > len(graded):
                    before = [
                        (score, int(row["correct"]))
                        for row in everything
                        if (score := answer_usage(provider, row["question_id"], row["raw_response"])[1]) is not None
                    ]
                    metrics.update(confidence_extremes_before_audit=bm.score_extremes(before))
            elif name in PART_GROUPS:
                group["auroc_interval"] = bm.bootstrap_ranking(scored, scored_clusters[name])["auroc"]
        groups[name] = group
    metrics["groups"] = groups
    if request_seconds:
        metrics["median_request_seconds"] = statistics.median(request_seconds)
    metrics.update(totals)
    input_tokens, output_tokens = totals["input_tokens"], totals["output_tokens"]
    if provider == "liquid":
        price = LIQUID_USD_PER_INPUT_TOKEN.get(run["model"])
        cost_usd = None if price is None else input_tokens * price
    elif provider == "fastino":
        cost_usd = input_tokens * FASTINO_USD_PER_INPUT_TOKEN
    elif provider == "perplexity":
        cost_usd = input_tokens * PERPLEXITY_USD_PER_INPUT_TOKEN
    elif provider in SYSTEM_ONE_PROVIDERS and provider not in UNPRICED_SYSTEM_ONE:
        cost_usd = input_tokens * TYPESAFE_USD_PER_INPUT_TOKEN
    elif provider in ("vllm-yes-no", "vllm-verbal", "vllm-vote"):
        cost_usd = input_tokens * VLLM_USD_PER_INPUT_TOKEN + output_tokens * VLLM_USD_PER_OUTPUT_TOKEN
    elif provider == "claude":
        prices = CLAUDE_USD_PER_MTOK.get(run["model"])
        cost_usd = None if prices is None else (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
    elif provider == "gemini":
        prices = GEMINI_USD_PER_MTOK.get(run["model"])
        cost_usd = None if prices is None else (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
    elif provider == "openai":
        prices = OPENAI_USD_PER_MTOK.get(run["model"])
        cached, written = totals["cached_input_tokens"], totals["cache_write_input_tokens"]
        cost_usd = None if prices is None else (
            (input_tokens - cached - written) * prices[0]
            + cached * prices[1]
            + written * prices[2]
            + output_tokens * prices[3]
        ) / 1_000_000
    else:
        cost_usd = None  # Laya, Ollama and vllm run on local weights; no price to apply
    if cost_usd is not None:
        metrics["cost_usd"] = cost_usd
    if run["replace_key_text"] is not None:
        metrics["key_replacement"] = key_replacement(connection, run, graded, search_dir)
    return metrics


def key_replacement(
    connection: sqlite3.Connection, run: sqlite3.Row, graded: list[dict[str, Any]], search_dir: Path
) -> dict[str, Any]:
    """For a --replace-key-text run, overall and by option shape: how often the model picked the original
    key letter, the wrong option whose text that letter showed (its twin), another option, or none, with the
    sign test of key against twin. For each kind of pick also the answers' scores, next to the scores the
    configuration's latest completed run without changed options gave the same questions ("unchanged").
    `graded` holds the run's graded answers (graded_answers)."""
    unchanged = connection.execute(
        """
        SELECT id, run_key, dataset FROM runs WHERE provider=? AND model=? AND thinking_mode=? AND batch_size=? AND dataset_sha256=?
            AND selection_sha256=? AND replace_key_text IS NULL AND shuffle_options IS NULL AND status='completed'
        ORDER BY id DESC LIMIT 1
        """,
        (run["provider"], run["model"], run["thinking_mode"], run["batch_size"], run["dataset_sha256"], run["selection_sha256"]),
    ).fetchone()
    unchanged_scores: dict[int, float | None] = {}
    if unchanged is not None:
        for row in graded_answers(connection, unchanged["run_key"], unchanged["dataset"], search_dir):
            unchanged_scores[int(row["question_id"])] = answer_usage(run["provider"], int(row["question_id"]), row["raw_response"])[1]
    counts = {shape: dict.fromkeys(KEY_REPLACEMENT_PICKS, 0) for shape in ("all", *OPTION_SHAPES)}
    scores: dict[str, dict[str, list[tuple[float, float | None]]]] = {
        shape: {pick: [] for pick in ("key", "twin", "other", "all")} for shape in counts
    }
    for row in graded:
        options = json.loads(row["options_json"])
        twin = next(option["copied_from"] for option in options if "copied_from" in option)
        prediction = row["predicted_answer"]
        if prediction is None:
            pick = "invalid"
        elif prediction == row["expected_answer"]:
            pick = "key"
        elif prediction == twin:
            pick = "twin"
        else:
            pick = "other"
        score = answer_usage(run["provider"], int(row["question_id"]), row["raw_response"])[1]
        for shape in ("all", option_shape([option["text"] for option in options])):
            counts[shape][pick] += 1
            if pick != "invalid" and score is not None:
                pair = (score, unchanged_scores.get(int(row["question_id"])))
                scores[shape][pick].append(pair)
                scores[shape]["all"].append(pair)

    def summary(pairs: list[tuple[float, float | None]]) -> dict[str, Any]:
        bins = [0] * len(bm.CONFIDENCE_BINS)
        for score, _ in pairs:
            bins[bm.confidence_bin(score)] += 1
        before = [score for _, score in pairs if score is not None]
        return {
            "answers": len(pairs),
            "mean": sum(score for score, _ in pairs) / len(pairs) if pairs else None,
            "unchanged_mean": sum(before) / len(before) if before else None,
            "bins": bins,
        }

    return {
        "unchanged_run": unchanged["id"] if unchanged is not None else None,
        "shapes": {
            shape: {
                **picks,
                "p": bm.sign_test(picks["key"], picks["twin"]),
                "confidence": {pick: summary(pairs) for pick, pairs in scores[shape].items()},
            }
            for shape, picks in counts.items()
        },
    }


def run_outcomes(
    connection: sqlite3.Connection, result: dict[str, Any], search_dir: Path, with_scores: bool = False
) -> dict[int, tuple[int, float | None]]:
    """Each graded answer's correctness and, if asked, its score, by question ID."""
    return {
        int(row["question_id"]): (
            int(row["correct"]),
            answer_usage(result["provider"], int(row["question_id"]), row["raw_response"])[1] if with_scores else None,
        )
        for row in graded_answers(connection, result["run_key"], result["dataset"], search_dir)
    }


def run_questions(connection: sqlite3.Connection, result: dict[str, Any], search_dir: Path) -> dict[int, tuple[int, str, str | None]]:
    """Each graded answer's correctness, the question as asked (its prompt and key) and the chosen option, by
    question ID."""
    return {
        int(row["question_id"]): (int(row["correct"]), f"{row['question']}\n{row['expected_answer']}", row["predicted_answer"])
        for row in graded_answers(connection, result["run_key"], result["dataset"], search_dir)
    }


def option_probabilities(provider: str, raw_response: str, question_id: int | None = None) -> dict[str, float] | None:
    """The probability of every option, for the providers that return them. A vllm response holds a batch,
    so it needs the question's ID."""
    record = json.loads(raw_response)
    if provider in SYSTEM_ONE_PROVIDERS:
        return ((record["response"].get("answers") or {}).get("answer") or {}).get("probabilities")
    if provider == "vllm-yes-no":
        return record.get("probabilities")
    if provider == "vllm":
        return ((record.get("answers") or {}).get(str(question_id)) or {}).get("probabilities")
    if provider in VOTE_PROVIDERS:
        votes = record.get("votes") or {}
        samples = sum(votes.values())
        return {label: count / samples for label, count in votes.items()} if samples else None
    return None


def run_doubt(
    connection: sqlite3.Connection, decision: dict[str, Any], frontier: list[dict[int, tuple[int, float | None]]]
) -> dict[str, Any] | None:
    """How well a decision model's uncertainty (entropy of its option probabilities) points at the questions
    the frontier runs got wrong; `frontier` holds each frontier run's outcomes by question ID."""
    entropies: list[float] = []
    mistakes: list[int] = []
    units: list[str] = []
    for row in connection.execute(
        "SELECT answers.question_id,answers.category,answers.raw_response FROM answers JOIN runs ON runs.id=answers.run_id "
        "WHERE runs.run_key=?",
        (decision["run_key"],),
    ):
        question = int(row["question_id"])
        probabilities = option_probabilities(decision["provider"], row["raw_response"])
        if not probabilities or any(question not in outcomes for outcomes in frontier):
            continue
        entropies.append(bm.entropy_bits(list(probabilities.values())))
        mistakes.append(sum(1 - outcomes[question][0] for outcomes in frontier))
        units.append(row["category"])
    if not entropies:
        return None
    correlation = bm.spearman(entropies, mistakes, units, shuffles=DOUBT_SHUFFLES)
    most_uncertain = sorted(range(len(entropies)), key=lambda index: -entropies[index])[: len(entropies) // 10]
    return {
        "questions": len(entropies),
        "rho": correlation["rho"],
        "p": correlation["p"],
        "auroc": bm.auroc([(entropy, int(count > 0)) for entropy, count in zip(entropies, mistakes)]),
        "top_tenth": {
            "questions": len(most_uncertain),
            "with_mistake": sum(mistakes[index] > 0 for index in most_uncertain),
            "all_with_mistake": sum(count > 0 for count in mistakes),
        },
    }



def in_main_tables(result: dict[str, Any]) -> bool:
    """Whether a run belongs in the report's main tables: a run over its question bank's whole question
    set, neither a repeat nor a run with a replaced correct option."""
    return (
        result.get("replace_key_text") is None
        and result.get("repeat") is None
        and result["evaluated"] == result["eligible_total"]
    )


def matches_side(result: dict[str, Any], side: str | tuple[str, str]) -> bool:
    """Whether a run is one side of a PAIRED_CONFIGURATIONS pair: its provider, or its provider and model."""
    provider, model = (side, None) if isinstance(side, str) else side
    return result.get("provider") == provider and (model is None or result["model"] == model)


def run_comparisons(
    connection: sqlite3.Connection, results: dict[str, dict[str, Any]], search_dir: Path
) -> dict[str, list[dict[str, Any]]]:
    """Between the main-table runs over the same questions: paired accuracy tests (with Holm-adjusted
    p-values within each such set), tied groups (every pair tested, Holm-adjusted over all pairs; see
    bm.tied_groups), cascade simulations, decision-model doubt and confidence sources
    scored on the same answers; each configuration's change between versions of the question bank; the
    run-to-run variation of repeated runs; and the cascade pipelines.

    Runs are over the same questions when they are graded against the same question bank, as it stands
    now, on the same questions: a run made before a review excluded questions joins the runs made after.
    """
    paired: list[dict[str, Any]] = []
    cascades: list[dict[str, Any]] = []
    doubts: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    outcomes = {key: run_outcomes(connection, result, search_dir) for key, result in results.items() if in_main_tables(result)}
    same_questions: dict[tuple[str, str | None, frozenset[int]], list[dict[str, Any]]] = {}
    for key, answered in outcomes.items():
        if answered:
            result = results[key]
            group = (Path(result["dataset"]).name, result.get("graded_sha256"), frozenset(answered))
            same_questions.setdefault(group, []).append(result)
    for members in same_questions.values():
        clusters = passage_clusters(members[0]["dataset"], str(search_dir))
        members = sorted(members, key=lambda result: (-result["correct"], result["run_id"]))
        pairs = [(first["run_key"], second["run_key"]) for first, second in zip(members, members[1:])]
        for first_side, second_side in PAIRED_CONFIGURATIONS:
            for first in members:
                for second in members:
                    pair = (first["run_key"], second["run_key"])
                    if matches_side(first, first_side) and matches_side(second, second_side) and pair not in pairs:
                        pairs.append(pair)
        family: list[dict[str, Any]] = []
        for first, second in pairs:
            questions = sorted(outcomes[first])
            test = bm.paired_comparison(
                [outcomes[first][question][0] for question in questions],
                [outcomes[second][question][0] for question in questions],
            )
            family.append({"first": first, "second": second, **test})
        for item, adjusted in zip(family, bm.holm([item["p"] for item in family])):
            item["p_holm"] = adjusted
        paired.extend(family)
        ranked = [result["run_key"] for result in members]
        questions = sorted(outcomes[ranked[0]])
        vectors = [[outcomes[key][question][0] for question in questions] for key in ranked]
        every_pair = list(itertools.combinations(range(len(ranked)), 2))
        adjusted = dict(zip(every_pair, bm.holm([bm.paired_comparison(vectors[i], vectors[j])["p"] for i, j in every_pair])))
        letters = bm.tied_groups(len(ranked), lambda i, j: adjusted[min(i, j), max(i, j)] < TIE_ALPHA)
        groups.extend({"run_key": key, "letters": letter, "pairs": len(every_pair)} for key, letter in zip(ranked, letters))
        frontier_runs = [
            result
            for result in members
            if (result.get("provider"), result["model"], result["thinking"]) in CASCADE_FRONTIER_RUNS
            and result.get("shuffle_options") is None
        ]
        for decision in members:
            if (
                decision.get("provider") not in CASCADE_DECISION_PROVIDERS
                or decision.get("shuffle_options") is not None
                or not frontier_runs
            ):
                continue
            scored = run_outcomes(connection, decision, search_dir, with_scores=True)
            questions = sorted(scored)
            for frontier in frontier_runs:
                simulation = bm.cascade(
                    [scored[question][1] or 0.0 for question in questions],
                    [scored[question][0] for question in questions],
                    [outcomes[frontier["run_key"]][question][0] for question in questions],
                    clusters=[clusters.get(question, f"question {question}") for question in questions],
                )
                cascades.append({"decision": decision["run_key"], "frontier": frontier["run_key"], **simulation})
            doubt = run_doubt(connection, decision, [outcomes[frontier["run_key"]] for frontier in frontier_runs])
            if doubt is not None:
                doubts.append({"decision": decision["run_key"], "frontier": [run["run_key"] for run in frontier_runs], **doubt})
        sources.extend(confidence_sources(connection, members, clusters, search_dir))
    # The same configuration on two versions of the question bank, older first.
    versions: list[dict[str, Any]] = []
    configurations: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for result in results.values():
        if not in_main_tables(result):
            continue
        key = (
            result.get("provider", "ollama"), result["model"], result["thinking"], result["batch_size"],
            result.get("shuffle_options"),
        )
        configurations.setdefault(key, []).append(result)
    for runs in configurations.values():
        runs = sorted(runs, key=lambda result: result["updated"])
        for older, newer in zip(runs, runs[1:]):
            if older["dataset_sha256"] != newer["dataset_sha256"] and Path(older["dataset"]).name != Path(newer["dataset"]).name:
                change = bm.version_change(run_questions(connection, older, search_dir), run_questions(connection, newer, search_dir))
                versions.append({"older": older["run_key"], "newer": newer["run_key"], **change})
    return {
        "paired": paired,
        "cascades": cascades,
        "doubts": doubts,
        "sources": sources,
        "groups": groups,
        "versions": versions,
        "repeats": run_repeats(connection, results, search_dir),
        "pipelines": run_pipelines(connection, results, search_dir),
    }


def run_repeats(connection: sqlite3.Connection, results: dict[str, dict[str, Any]], search_dir: Path) -> list[dict[str, Any]]:
    """Each configuration with repeats (--repeat): its runs on the same question bank and the same
    questions (the whole set, or one sample), and how their answers agree (bm.repeat_stability) on the
    questions every run was asked identically."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for result in results.values():
        if result.get("replace_key_text") is not None or result.get("question_list"):
            continue
        selection = "whole" if result["evaluated"] == result["eligible_total"] else result["selection_sha256"]
        key = (
            Path(result["dataset"]).name, result.get("provider", "ollama"), result["model"], result["thinking"],
            result["batch_size"], result.get("shuffle_options"), selection,
        )
        groups.setdefault(key, []).append(result)
    found = []
    for runs in groups.values():
        if len(runs) < 2 or all(run.get("repeat") is None for run in runs):
            continue
        runs = sorted(runs, key=lambda run: (run.get("repeat") or 1, run["run_id"]))
        answers = [
            {
                int(row["question_id"]): (
                    int(row["correct"]),
                    row["predicted_answer"],
                    answer_usage(run.get("provider", "ollama"), row["question_id"], row["raw_response"])[1],
                    f"{row['question']}\n{row['expected_answer']}",
                )
                for row in graded_answers(connection, run["run_key"], run["dataset"], search_dir)
            }
            for run in runs
        ]
        common = set.intersection(*(set(run_answers) for run_answers in answers))
        identical = {question for question in common if len({run_answers[question][3] for run_answers in answers}) == 1}
        stability = bm.repeat_stability(
            [{question: run_answers[question][:3] for question in identical} for run_answers in answers]
        )
        found.append({"run_keys": [run["run_key"] for run in runs], **stability})
    return found


def run_pipelines(connection: sqlite3.Connection, results: dict[str, dict[str, Any]], search_dir: Path) -> list[dict[str, Any]]:
    """Each cascade pipeline planned by cascade_pipeline.py (pipeline/*.json next to the report).

    On the plan's held-out questions, the pipeline takes the decision model's answers at or above the
    threshold and the answers of a frontier run made on just the questions passed on; it is compared with
    the same frontier configuration run on all held-out questions, both made for the plan (--questions).
    The simulation's prediction from the stored whole-set runs is given beside it.
    """
    found = []
    for path in sorted((search_dir / "pipeline").glob("*.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        decision, frontier = results.get(plan["decision"]), results.get(plan["frontier"])
        if decision is None or frontier is None:
            continue
        held_out, routed, passed = (frozenset(plan[key]) for key in ("held_out", "routed", "passed"))
        order = sorted(held_out)
        decided = run_outcomes(connection, decision, search_dir)
        stored = run_outcomes(connection, frontier, search_dir)

        def accuracy(outcomes: list[int]) -> float:
            return sum(outcomes) / len(outcomes)

        item: dict[str, Any] = {
            "name": plan["name"],
            "decision": plan["decision"],
            "frontier": plan["frontier"],
            "seed": plan["seed"],
            "tolerance_points": plan["tolerance_points"],
            "threshold": plan["threshold"],
            "held_out": len(order),
            "routed": len(routed),
            "simulated": {
                "accuracy": accuracy([decided[q][0] if q in routed else stored[q][0] for q in order]),
                "frontier_accuracy": accuracy([stored[q][0] for q in order]),
            },
        }

        def configuration(run: dict[str, Any]) -> tuple[Any, ...]:
            return (run.get("provider", "ollama"), run["model"], run["thinking"], run["batch_size"])

        made: dict[str, dict[str, Any]] = {}
        for run in results.values():
            if run.get("question_list") and configuration(run) == configuration(frontier):
                answered = frozenset(run_outcomes(connection, run, search_dir))
                if answered == passed:
                    made["pipeline"] = run
                elif answered == held_out:
                    made["alone"] = run
        if len(made) == 2:
            pipeline_run, alone_run = made["pipeline"], made["alone"]
            asked, alone_answers = run_outcomes(connection, pipeline_run, search_dir), run_outcomes(connection, alone_run, search_dir)
            measured = [decided[q][0] if q in routed else asked[q][0] for q in order]
            alone = [alone_answers[q][0] for q in order]
            test = bm.paired_comparison(measured, alone)
            # The decision model answers every held-out question; its cost and time are spread evenly
            # over the requests its run made.
            share = len(order) / decision.get("as_run", {}).get("evaluated", decision["evaluated"])
            decision_cost = None if decision.get("cost_usd") is None else decision["cost_usd"] * share
            item["measured"] = {
                "pipeline_run": pipeline_run["run_key"],
                "alone_run": alone_run["run_key"],
                "accuracy": accuracy(measured),
                "frontier_accuracy": accuracy(alone),
                **{key: test[key] for key in ("difference", "low", "high", "p")},
                "within_tolerance": 100 * test["difference"] >= -plan["tolerance_points"],
                "cost_usd": None
                if decision_cost is None or pipeline_run.get("cost_usd") is None
                else decision_cost + pipeline_run["cost_usd"],
                "frontier_cost_usd": alone_run.get("cost_usd"),
                "request_seconds": decision["timed_seconds"] * share + pipeline_run["timed_seconds"],
                "frontier_request_seconds": alone_run["timed_seconds"],
            }
        found.append(item)
    return found


def confidence_sources(
    connection: sqlite3.Connection, members: list[dict[str, Any]], clusters: dict[int, str], search_dir: Path
) -> list[dict[str, Any]]:
    """Each vllm-verbal run's own answers scored four ways: the confidence it states, the probability that
    the vllm-yes-no run of the same model and the Open-Jev runs give the option it chose, and the share
    of the vllm-vote run's samples (same model and prompt) that chose it."""

    def answers(result: dict[str, Any]) -> dict[int, dict[str, Any]]:
        return {
            int(row["question_id"]): row
            for row in graded_answers(connection, result["run_key"], result["dataset"], search_dir)
        }

    found = []
    for verbal in members:
        if verbal.get("provider") != "vllm-verbal" or verbal.get("shuffle_options") is not None:
            continue
        rows = answers(verbal)
        questions = sorted(rows)
        scorers = [(verbal, {question: json.loads(rows[question]["raw_response"]).get("confidence") for question in questions})]
        for other in members:
            vote = other.get("provider") in VOTE_PROVIDERS and other["model"] == verbal["model"]
            if vote or (other.get("provider") == "vllm-yes-no" and other["model"] == verbal["model"]) or other.get("provider") == "open-jev":
                probabilities = {
                    question: option_probabilities(other["provider"], row["raw_response"]) or {}
                    for question, row in answers(other).items()
                }
                # An option no sample chose has a vote share of 0.
                scores = {
                    question: None
                    if question not in probabilities
                    else probabilities[question].get(rows[question]["predicted_answer"], 0.0 if vote else None)
                    for question in questions
                }
                scorers.append((other, scores))
        entries = []
        for scorer, scores in scorers:
            kept = [question for question in questions if isinstance(scores[question], (int, float))]
            scored = [(float(scores[question]), int(rows[question]["correct"])) for question in kept]
            bootstrap = bm.bootstrap_ranking(scored, [clusters.get(question, f"question {question}") for question in kept])
            entries.append(
                {
                    "run": scorer["run_key"],
                    "questions": len(kept),
                    "auroc": bm.auroc(scored),
                    "auroc_interval": bootstrap["auroc"],
                    "risk_coverage": bm.ranking_metrics(scored)["risk_coverage"],
                }
            )
        found.append(
            {
                "answers": verbal["run_key"],
                "questions": len(questions),
                "correct": sum(int(rows[question]["correct"]) for question in questions),
                "sources": entries,
            }
        )
    return found


@contextmanager
def report_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on the report's directory while a run reads and rewrites the report.

    Runs that finish at the same time would otherwise each write the report without the other's run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        yield
    finally:
        os.close(directory)  # closing releases the lock


def write_report(path: Path, results: dict[str, dict[str, Any]], connection: sqlite3.Connection) -> None:
    """Recompute every run's metrics and the comparisons between runs, and write the report."""
    fresh = {}
    for run_key, item in results.items():
        record = {field: item[field] for field in RESULT_FIELDS if field in item}
        # The totals as the run recorded them, kept so that grading against a changed bank stays repeatable.
        record.setdefault("as_run", {field: record[field] for field in ("eligible_total", "evaluated", "correct", "invalid", "categories")})
        record.update(run_metrics(connection, run_key, path.parent))
        record["eligible_total"] = record["as_run"]["eligible_total"] - record.get("excluded_since_run", 0)
        fresh[run_key] = record
    comparisons = run_comparisons(connection, fresh, path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_report(fresh, comparisons), encoding="utf-8")
    temporary.replace(path)


def update_report(
    path: Path,
    result_database: Path,
    data_path: Path,
    selection: Selection,
    identity: RunIdentity,
    args: argparse.Namespace,
    thinking: bool | str,
    correct: int,
    invalid: int,
    categories: dict[str, dict[str, int]],
    connection: sqlite3.Connection,
) -> None:
    with report_lock(path):
        results = read_results(path)
        results[identity.run_key] = run_record(
            identity, args, data_path, result_database, selection, thinking, correct, invalid, categories
        )
        write_report(path, results, connection)


def run_record(
    identity: RunIdentity,
    args: argparse.Namespace,
    data_path: Path,
    result_database: Path,
    selection: Selection,
    thinking: bool | str,
    correct: int,
    invalid: int,
    categories: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """The report fields that describe a finished run (RESULT_FIELDS)."""
    return {
        "run_key": identity.run_key,
        "run_id": identity.run_id,
        "model": args.model,
        "provider": args.provider,
        "dataset": str(data_path),
        "database": str(result_database),
        "dataset_sha256": identity.dataset_sha256,
        "selection_sha256": identity.selection_sha256,
        "eligible_total": selection.eligible_total,
        "evaluated": len(selection.questions),
        "correct": correct,
        "invalid": invalid,
        "skipped": selection.skipped,
        "batch_size": args.batch_size,
        "thinking": thinking_label(thinking),
        "num_ctx": args.num_ctx,
        "image_input": args.image_input,
        "shuffle_options": args.shuffle_options,
        "replace_key_text": args.replace_key_text,
        "categories": categories,
        "updated": utc_now(),
        "concurrency": args.concurrency,
        "repeat": args.repeat,
        "question_list": args.questions.name if args.questions else None,
    }


def main() -> int:
    args = parse_args()
    result_connection: sqlite3.Connection | None = None
    identity: RunIdentity | None = None
    verbose_log: TextIO | None = None
    try:
        data_path = args.data.resolve()
        result_path = args.database.resolve()
        if args.export_answers is not None:
            result_connection = open_result_database(result_path)
            count = export_answers(args.export_answers.resolve(), args.output.resolve(), result_connection)
            print(f"Wrote the answers of {count} runs to {args.export_answers}")
            return 0
        if args.refresh_report:
            with report_lock(args.output.resolve()):
                results = read_results(args.output.resolve())
                if not results:
                    raise ValueError(f"{args.output} contains no benchmark results")
                result_connection = open_result_database(result_path)
                write_report(args.output.resolve(), results, result_connection)
            print(f"Updated {args.output}: {len(results)} runs")
            return 0
        if args.provider == "openai":
            args.codex_bin = require_chatgpt_oauth(args.codex_bin)
            thinking: bool | str = args.openai_reasoning
            endpoint = "codex-cli-chatgpt-oauth"
            image_input = False
        elif args.provider in SYSTEM_ONE_PROVIDERS:
            args.jev_api_key = jev_api_key(args.provider)
            thinking = False
            endpoint = args.jev_url
            image_input = False
        elif args.provider in VLLM_PROVIDERS:
            thinking = args.vllm_thinking
            endpoint = args.vllm_url
            image_input = False
            if args.provider == "vllm-yes-no":
                args.yes_no_ids = vllm_yes_no_ids(args.vllm_url, args.model, args.timeout)
        elif args.provider == "gemini":
            args.gemini_api_key = gemini_api_key()
            thinking = args.gemini_thinking
            endpoint = GEMINI_URL
            image_input = False
        elif args.provider == "claude":
            args.claude_bin = require_claude_subscription(args.claude_bin)
            thinking = args.claude_effort
            endpoint = "claude-code-subscription"
            image_input = False
        else:
            thinking = resolve_thinking(args.model)
            endpoint = args.ollama_url
            supports_vision = (
                ollama_supports_vision(args.ollama_url, args.model, args.timeout)
                if args.image_input != "off"
                else False
            )
            if args.image_input == "on" and not supports_vision:
                raise ValueError(
                    f"Ollama model {args.model!r} does not report vision capability"
                )
            image_input = supports_vision
        args.image_input = "on" if image_input else "off"
        selection = load_questions(
            data_path,
            args.unit,
            args.limit,
            args.sample,
            args.seed,
            allow_images=image_input,
            shuffle_seed=args.shuffle_options,
            replace_key_seed=args.replace_key_text,
            question_ids=read_question_ids(args.questions) if args.questions else None,
        )
        print(
            f"Extraction validation: source={selection.source_total}, "
            f"filtered={selection.filtered_total}, eligible={selection.eligible_total}, "
            f"skipped={json.dumps(selection.skipped, sort_keys=True)}; "
            f"evaluating={len(selection.questions)}"
        )
        result_connection = open_result_database(result_path)
        identity = start_run(
            result_connection,
            selection,
            args.model,
            data_path,
            args.provider,
            endpoint,
            args.seed,
            args.batch_size,
            thinking,
            args.num_ctx,
            image_input,
            args.shuffle_options,
            args.replace_key_text,
            args.repeat,
            args.restart,
        )
        if args.log_verbose:
            verbose_log, log_path = open_verbose_log(args.model)
            print(f"Verbose log: {log_path}")
        print(
            f"Evaluating {args.model} with {args.provider} on "
            f"{len(selection.questions)} question(s) "
            f"(batch={args.batch_size}, thinking={thinking_label(thinking)}, "
            f"image_input={'on' if image_input else 'off'}, shuffle_options={args.shuffle_options}, "
            f"replace_key_text={args.replace_key_text}, run={identity.run_id})"
        )
        correct, invalid, categories = evaluate(
            selection, result_connection, identity, args, thinking, verbose_log
        )
        mark_run(result_connection, identity.run_id, "completed")
        update_report(
            args.output.resolve(),
            result_path,
            data_path,
            selection,
            identity,
            args,
            thinking,
            correct,
            invalid,
            categories,
            result_connection,
        )
    except KeyboardInterrupt:
        if result_connection is not None and identity is not None:
            mark_run(result_connection, identity.run_id, "interrupted")
            evaluated, _, _, _ = score(result_connection, identity.run_id)
            print(f"\nInterrupted after {evaluated} stored answers; rerun the same command to resume.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        if result_connection is not None and identity is not None:
            mark_run(result_connection, identity.run_id, "failed")
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if verbose_log is not None:
            verbose_log.close()
        if result_connection is not None:
            result_connection.close()
    print(f"Final score: {correct}/{len(selection.questions)} ({correct/len(selection.questions):.2%})")
    print(f"Stored answers in {args.database}")
    print(f"Updated {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
