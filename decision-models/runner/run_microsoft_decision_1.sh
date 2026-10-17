#!/usr/bin/env bash
# Microsoft-Decision-1 via OpenRouter's System One route, one request at a time as Decider v1.1 ran; the request time
# includes OpenRouter's own time. The key comes from OPENROUTER_API_KEY. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py microsoft/microsoft-decision-1 \
  --provider openrouter \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
