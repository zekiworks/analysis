#!/usr/bin/env bash
# Gemini 3.8 Flash at high thinking, 4 requests at a time: a reasoning comparison on a stable model (its
# low-thinking run is run_gemini.sh). The key: GEMINI_API_KEY or ~/.config/gemini/key.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-3.8-flash \
  --provider gemini \
  --gemini-thinking high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
