#!/usr/bin/env bash
# Anthropic's Claude Haiku 5.5 through OpenRouter pinned to Anthropic's own endpoint (anthropic), fallbacks off, the answer schema (the endpoint has structured outputs), reasoning_effort max (project lead bus #4257: a chat model on the reading bench, at its highest setting), 16 questions per request as for the other chat setups. No required parameters: the endpoint does not list temperature, which every OpenRouter chat request sets to 1.0 (Claude's default too), so requiring parameters would leave no endpoint. Add --english FILE, --dont-know and the rest as for the other chat setups.
# Output cap 65,536 tokens (--openrouter-max-tokens), as for every Flash setup; the endpoint allows 128,000.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py anthropic/claude-haiku-5.5 \
  --provider openrouter-chat \
  --openrouter-reasoning max \
  --openrouter-order anthropic \
  --openrouter-max-tokens 65536 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
