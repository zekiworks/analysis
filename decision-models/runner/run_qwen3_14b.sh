#!/usr/bin/env bash
# Qwen3-14B through its vLLM container (README, "Run against vLLM"), thinking off.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen3-14b \
  --provider vllm \
  --vllm-url "${QWEN3_14B_URL:?set QWEN3_14B_URL to the Qwen3-14B vLLM server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --batch-size 16
