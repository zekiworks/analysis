#!/usr/bin/env bash
# GLM-5.3 (not GLM-5.3-Flash) through OpenRouter pinned to Fireworks, fallbacks off, required parameters, reasoning_effort low: backgammon League 2's GLM-5.3 (on) (openrouter:fireworks, z-ai/glm-5.3, low). Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py z-ai/glm-5.3 \
  --provider openrouter-chat \
  --openrouter-reasoning low \
  --openrouter-order fireworks \
  --openrouter-require-parameters \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
