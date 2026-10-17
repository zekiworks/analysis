#!/usr/bin/env bash
# Perplexity's pplx-decider-flash-v1.2 (a separate model, from Qwen3.5-4B) through its Decisions API, with the
# settings run_perplexity_v1_1.sh gives v1.1; the key comes from PERPLEXITY_API_KEY. Add --repeat N (2 or more) for a
# repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py pplx-decider-flash-v1.2 \
  --provider perplexity \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
