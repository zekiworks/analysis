#!/usr/bin/env bash
# Inception's Mercury Decide via OpenRouter's System One route, its paid listing (not inception/mercury-decide:free), one
# request at a time as Decider v1.1 ran; the request time includes OpenRouter's own time. The key comes from
# OPENROUTER_API_KEY. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py inception/mercury-decide \
  --provider openrouter \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
