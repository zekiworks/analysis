#!/usr/bin/env bash
# Google's Gemini Decision 1 via OpenRouter's System One route (google/gemini-decision-1, served by its one endpoint,
# Google AI Studio), one question per request as Microsoft-Decision-1 ran; the request time includes OpenRouter's own
# time. The key comes from OPENROUTER_API_KEY. Add --dont-know, --english FILE and --repeat N (2 or more) as for the
# other decision models.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py google/gemini-decision-1 \
  --provider openrouter \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
