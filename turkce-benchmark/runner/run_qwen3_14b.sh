#!/usr/bin/env bash
# Qwen3-14B through its vLLM container on port 8892 (README, "Run against vLLM"), thinking off.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen3-14b \
  --provider vllm \
  --vllm-url http://127.0.0.1:8892 \
  --data questions-v2.sqlite \
  --batch-size 16
