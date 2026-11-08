#!/usr/bin/env bash
# Qwen 3.5 397B-A17B through OpenRouter pinned to DeepInfra's endpoint (deepinfra/fp8), fallbacks off, required parameters, reasoning_effort high, 16 questions per request (project lead, bus #2959). DeepInfra's endpoint has structured outputs and reasons (smoke runs 849 and 851), so the request carries the answer schema of every other chat setup; Alibaba's own endpoint has no structured outputs and in JSON mode answered in a layout of its own. Add --english FILE, --dont-know and the rest as arguments. Needs OPENROUTER_API_KEY.
# Output cap 65,536 tokens (--openrouter-max-tokens), as for every Flash setup, so no reply is cut at the default 32,768; the endpoint allows 81,920.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen/qwen3.5-397b-a17b \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order deepinfra/fp8 \
  --openrouter-max-tokens 65536 \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
