#!/usr/bin/env bash
# DeepSeek-V4.1-Flash-1017 through OpenRouter pinned to DeepSeek's own endpoint (deepseek), fallbacks off, required parameters, reasoning_effort low: backgammon League 2's DeepSeek V4.1 Flash 1017 (on) (openrouter:deepseek, deepseek/deepseek-v4.1-flash-1017, low). Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py deepseek/deepseek-v4.1-flash-1017 \
  --provider openrouter-chat \
  --openrouter-reasoning low \
  --openrouter-order deepseek \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
