#!/usr/bin/env bash
# GLM-5.3-Flash on the four GPUs, served by TensorFold (the GLM-5.3-Flash-EXL3-4x-RTX-PRO-6000-TensorFold model folder):
# Mia's AI Lab's EXL3 checkpoint with 4-bit routed experts, dense layers and KV cache in FP8, thinking off. TensorFold
# returns no token probabilities, so the model states a confidence per question, as the hosted models do
# (--provider vllm-stated).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py glm-5.3-flash \
  --provider vllm-stated \
  --vllm-url "${GLM_URL:?set GLM_URL to the GLM TensorFold server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --batch-size 16 \
  "$@"
