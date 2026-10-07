#!/usr/bin/env bash
# Gemini 3.1 Pro (preview) at its default thinking level, high, 4 requests at a time: at low it does no
# thinking and answers the first questions of each request poorly. The key: GEMINI_API_KEY or ~/.config/gemini/key.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-3.1-pro-preview \
  --provider gemini \
  --gemini-thinking high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
