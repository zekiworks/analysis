#!/usr/bin/env bash
# MiMo V2.6 Flash through OpenRouter pinned to Xiaomi's own endpoint (xiaomi/fp8), fallbacks off, required parameters, reasoning_effort high, ONE question per request (project lead's choice (a), bus #3152), a setup of its own: with 16 questions per request its reasoning looped on one Turkish grammar question and used the whole 65,536-token cap with no answer (smoke runs 835 at 32,768 and 855 at 65,536). The endpoint has structured outputs, so the request carries the answer schema of every other chat setup.
# Output cap 65,536 tokens per question (--openrouter-max-tokens); the endpoint allows 131,072. 8 requests in flight.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py xiaomi/mimo-v2.6-flash \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order xiaomi/fp8 \
  --openrouter-max-tokens 65536 \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 1 \
  --timeout 900 \
  --concurrency 8 \
  "$@"
