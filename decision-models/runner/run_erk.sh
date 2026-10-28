#!/usr/bin/env bash
# Erk-14B through its vLLM container (README, "Run against vLLM"), thinking off.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py erk-14b \
  --provider vllm \
  --vllm-url "${ERK_URL:?set ERK_URL to the Erk-14B vLLM server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --batch-size 16
