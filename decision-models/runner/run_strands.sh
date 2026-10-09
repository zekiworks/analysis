#!/usr/bin/env bash
# Amazon's Strands Decider 2B (StrandsAgents/strands-decider-2B-hobson-v21 at 2b52a62) through the
# package's own System One server, ~/code/strands-decider/server.py, on port 18096; start it first.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py strands-decider-2b \
  --provider strands \
  --data questions-v2.sqlite \
  --timeout 120
