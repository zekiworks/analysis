#!/usr/bin/env bash
# Amazon's Strands Decider 2B (StrandsAgents/strands-decider-2B-hobson-v21 at 2b52a62) through the
# package's own System One server (server.py in the strands-decider repository); start it first and set STRANDS_URL.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py strands-decider-2b \
  --provider strands \
  --data questions-v2.sqlite \
  --timeout 120
