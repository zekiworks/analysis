#!/usr/bin/env bash
# Anthropic's Claude Haiku 5.5 through OpenRouter pinned to Anthropic's own endpoint (anthropic), fallbacks off, the answer schema (the endpoint has structured outputs), reasoning_effort max (project lead bus #4257: a chat model on the reading bench, at its highest setting), 16 questions per request as for the other chat setups. No required parameters: the endpoint does not list temperature, which every OpenRouter chat request sets to 1.0 (Claude's default too), so requiring parameters would leave no endpoint. Add --english FILE, --dont-know and the rest as for the other chat setups.
# Output cap 128,000 tokens (--openrouter-max-tokens), the endpoint's maximum: at reasoning max, 5 of the 13 requests of
# the Turkish smoke (run 944) spent the Flash setups' whole 65,536 on reasoning and returned no answer; with 128,000 the
# same five requests answered (run 945). The request timeout is 1,800 s so that a long reply is not cut off.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py anthropic/claude-haiku-5.5 \
  --provider openrouter-chat \
  --openrouter-reasoning max \
  --openrouter-order anthropic \
  --openrouter-max-tokens 128000 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 1800 \
  --concurrency 4 \
  "$@"
