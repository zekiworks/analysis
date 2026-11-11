#!/usr/bin/env bash
# Alibaba's Qwen3.8 Flash (closed weights) through OpenRouter's chat API, pinned to Alibaba's endpoint (alibaba, its
# only provider), fallbacks off, required parameters and the answer schema; reasoning off, as its backgammon setup
# (jevgammon's qwen3-8-flash-off) and its Logic & Math setup run it (the project lead via Zeki #4806, logic #4807);
# 16 questions per request, as every chat model on the reading bench. Key: OPENROUTER_API_KEY. New runs record the
# harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen/qwen3.8-flash \
  --provider openrouter-chat \
  --openrouter-reasoning none \
  --openrouter-order alibaba \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
