#!/usr/bin/env bash
# Gemini 3.8 Flash at low thinking, one question per request (v2 plan, part D): the questions, prompt and settings of
# run_gemini.sh, which asks 16 questions per request. A new run records its harness commit, so set HARNESS_REPO to a
# clone of the published repository when running from a folder outside git.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-3.8-flash \
  --provider gemini \
  --gemini-thinking low \
  --data questions-v2.sqlite \
  --batch-size 1 \
  --timeout 600 \
  "$@"
