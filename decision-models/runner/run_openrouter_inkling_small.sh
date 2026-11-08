#!/usr/bin/env bash
# Inkling Small through OpenRouter pinned to DeepInfra's endpoint (deepinfra/fp8), the only one that serves it, fallbacks off, reasoning_effort high, 16 questions per request (project lead, bus #2959). The endpoint takes no response_format at all, so the request has neither the answer schema nor JSON mode nor required parameters, and states the answer layout in the prompt (--openrouter-answer-layout): a prompt difference from the other chat setups, and its answers are read strictly in that layout (without it it answered with keys of its own or {}, runs 844 and 846). Add --english FILE, --dont-know and the rest as arguments. Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py thinkingmachines/inkling-small \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order deepinfra/fp8 \
  --openrouter-answer-layout \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
