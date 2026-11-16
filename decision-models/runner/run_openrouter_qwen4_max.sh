#!/usr/bin/env bash
# qwen/qwen4-max through OpenRouter pinned to Alibaba's endpoint, the maker's (--openrouter-order alibaba), fallbacks off, reasoning_effort high
# (the model's default effort, as Logic & Math runs it), 16 questions per request with the answer schema (the endpoint
# takes structured outputs; --openrouter-require-parameters), output capped at 32,768 tokens (Ümit #9817, #10509: through
# the API). Paid: it sends only under a spending cap, --spend-cap-usd USD --spend-ledger FILE. Add --english FILE,
# --dont-know and the rest as arguments. Needs OPENROUTER_API_KEY; a new run records its harness commit (HARNESS_REPO).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen/qwen4-max \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order alibaba \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
