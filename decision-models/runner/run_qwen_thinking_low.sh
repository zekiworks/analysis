#!/usr/bin/env bash
# Qwen3.8-27B with thinking on at the chat template's reasoning_effort low, as backgammon League 2's Qwen3.8-27B (on)
# asks it, on the BF16 vLLM server of the earlier Qwen3.8-27B runs; 16 questions per request with answer letter
# probabilities, as DeepSeek-V4.1-Flash's reasoning run. Four requests at a time, the server's four sequences.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py qwen38-27b-bf16 \
  --provider vllm \
  --vllm-thinking \
  --vllm-reasoning-effort low \
  --concurrency 4 \
  --vllm-url "${QWEN_URL:?set QWEN_URL to the Qwen3.8-27B BF16 vLLM server, as http://host:port}" \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 3600
