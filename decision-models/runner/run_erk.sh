#!/usr/bin/env bash
# Erk-14B through its vLLM container on port 8893 (README, "Run against vLLM"), thinking off.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py erk-14b \
  --provider vllm \
  --vllm-url http://127.0.0.1:8893 \
  --data questions-v2.sqlite \
  --batch-size 16
