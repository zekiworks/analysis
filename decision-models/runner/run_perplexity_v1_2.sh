#!/usr/bin/env bash
# Perplexity's pplx-decider-v1.2 through its Decisions API, one question per request, as run_perplexity_v1_1.sh runs
# v1.1; the key comes from PERPLEXITY_API_KEY. Add --perplexity-mode web_grounding for Perplexity's web grounding, and
# --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py pplx-decider-v1.2 \
  --provider perplexity \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
