#!/usr/bin/env bash
# Gemini 3.1 Pro (preview) through the Gemini API, at its lowest thinking level. The key: GEMINI_API_KEY or ~/.config/gemini/key.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-3.1-pro-preview \
  --provider gemini \
  --gemini-thinking low \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
