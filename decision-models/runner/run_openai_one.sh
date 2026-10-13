#!/usr/bin/env bash
# GPT-6 Astra at low reasoning, one question per request (v2 plan, part D): the questions, prompt and closed-book Codex
# settings of run_openai.sh, which asks 16 questions per request. A new run records its harness commit, so set
# HARNESS_REPO to a clone of the published repository when running from a folder outside git.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gpt-6-astra \
  --provider openai \
  --openai-reasoning low \
  --data questions-v2.sqlite \
  --batch-size 1 \
  --timeout 600 \
  "$@"
