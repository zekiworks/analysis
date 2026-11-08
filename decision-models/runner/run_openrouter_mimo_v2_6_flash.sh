#!/usr/bin/env bash
# MiMo V2.6 Flash through OpenRouter pinned to Xiaomi's own endpoint (xiaomi/fp8), fallbacks off, required parameters, reasoning_effort high, 16 questions per request (project lead, bus #2959). The endpoint has structured outputs, so the request carries the answer schema of every other chat setup; its output cap is 65,536 tokens (--openrouter-max-tokens 65536) because its Turkish smoke batch spent all 32,768 on reasoning and gave no answer (run 835). Add --english FILE, --dont-know and the rest as arguments. Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py xiaomi/mimo-v2.6-flash \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order xiaomi/fp8 \
  --openrouter-require-parameters \
  --openrouter-max-tokens 65536 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
