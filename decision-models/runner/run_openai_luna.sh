#!/usr/bin/env bash
# GPT-6 Luna through the Codex CLI signed in with ChatGPT, at low effort, as GPT-6 Astra and GPT-6.1 Sol.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gpt-6-luna \
  --provider openai \
  --openai-reasoning low \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
