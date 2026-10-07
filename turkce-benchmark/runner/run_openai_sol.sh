#!/usr/bin/env bash
# GPT-6.1 Sol through the Codex CLI signed in with ChatGPT, at its lowest reasoning effort.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gpt-6.1-sol \
  --provider openai \
  --openai-reasoning low \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
