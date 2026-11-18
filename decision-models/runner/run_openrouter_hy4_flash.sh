#!/usr/bin/env bash
# tencent/hy4-flash through OpenRouter pinned to Tencent's endpoint, the maker's (--openrouter-order tencent), fallbacks off,
# reasoning_effort high, 16 questions per request with the answer schema (the endpoint takes structured outputs;
# --openrouter-require-parameters), output capped at 32,768 tokens (Ümit #12072, #12075). Paid: it sends only under a
# spending cap, --spend-cap-usd USD --spend-ledger FILE. Add --english FILE, --dont-know and the rest as arguments. Needs
# OPENROUTER_API_KEY; a new run records its harness commit (HARNESS_REPO).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py tencent/hy4-flash \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order tencent \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
