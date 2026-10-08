#!/usr/bin/env bash
# GPT-6 Luna through OpenAI's Decisions API (public beta), POST /v1/decisions, 4 requests at a time.
# The key: OPENAI_API_KEY, an API key with billing (the Codex-based openai provider never uses one).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gpt-6-luna \
  --provider openai-decisions \
  --data questions-v2.sqlite \
  --timeout 60 \
  --concurrency 4
