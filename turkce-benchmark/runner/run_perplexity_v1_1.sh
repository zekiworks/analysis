#!/usr/bin/env bash
# Perplexity's pplx-decider-v1.1-27b through its Decisions API, as run_perplexity.sh runs v1; the key comes
# from PERPLEXITY_API_KEY. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py pplx-decider-v1.1-27b \
  --provider perplexity \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
