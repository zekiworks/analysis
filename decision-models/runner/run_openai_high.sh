#!/usr/bin/env bash
# GPT-6 Astra through the Codex CLI signed in with ChatGPT, at reasoning effort high (run 277).
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gpt-6-astra \
  --provider openai \
  --openai-reasoning high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
