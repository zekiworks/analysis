#!/usr/bin/env bash
# Meta's Muse Ember (released 9 November 2026, closed weights) through OpenRouter pinned to Meta's own endpoint (meta), the only one that serves it, fallbacks off, required parameters and the answer schema (the endpoint has structured outputs), reasoning_effort max (its highest setting, project lead bus #4021: a chat-model comparison, not a decision model), 16 questions per request as for the other chat setups. Add --english FILE, --dont-know and the rest as for the other chat setups.
# Output cap 65,536 tokens (--openrouter-max-tokens), as for every Flash setup; the endpoint allows 943,718.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py meta/muse-ember \
  --provider openrouter-chat \
  --openrouter-reasoning max \
  --openrouter-order meta \
  --openrouter-max-tokens 65536 \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
