#!/usr/bin/env bash
# Perplexity's pplx-decider-flash-v1.2 (a separate model, from Qwen3.5-4B) from its released checkpoint behind
# servers/pplx_decider_server.py on a DGX Spark (GB10), with the settings
# run_perplexity_v1_1.sh gives v1.1. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py pplx-decider-flash-v1.2 \
  --provider pplx-decider \
  --data questions-v2.sqlite \
  --jev-url "${PPLX_DECIDER_V1_2_URL:?set PPLX_DECIDER_V1_2_URL to the pplx_decider_server.py server, as http://HOST:PORT}" \
  --timeout 30 \
  "$@"
