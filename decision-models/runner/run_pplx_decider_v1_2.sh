#!/usr/bin/env bash
# Perplexity's pplx-decider-v1.2 from its released checkpoint behind servers/pplx_decider_server.py on spark3, a DGX
# Spark (GB10) at 192.168.1.139, port 18097, with the settings run_perplexity_v1_1.sh gives v1.1. Add --repeat N (2 or
# more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py pplx-decider-v1.2 \
  --provider pplx-decider \
  --data questions-v2.sqlite \
  --jev-url http://192.168.1.139:18097 \
  --timeout 30 \
  "$@"
