#!/usr/bin/env bash
# Gemma 4 31B with reasoning off on vLLM, one question per request (v2 plan, part D): the questions, prompt and server of
# run_gemma.sh, which asks 16 questions per request. A new run records its harness commit, so set HARNESS_REPO to a
# clone of the published repository when running from a folder outside git.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemma-4-31B-it \
  --provider vllm \
  --vllm-url http://192.168.1.126:8010 \
  --data questions-v2.sqlite \
  --batch-size 1 \
  "$@"
