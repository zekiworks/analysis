#!/usr/bin/env bash
# GLM-5.3-Flash with thinking on (run_glm.sh has it off), at the server's high reasoning effort, sampling with the
# server's defaults (temperature 1.0 and top-p 0.95 from Z.ai's generation config, TensorFold's top-k 20), 8 requests
# at a time.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py glm-5.3-flash \
  --provider vllm-stated \
  --vllm-thinking \
  --concurrency 8 \
  --vllm-url http://192.168.1.126:8010 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 3600 \
  "$@"
