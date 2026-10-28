#!/usr/bin/env bash
# Kimi K3.1 Pro through OpenRouter pinned to Moonshot AI's endpoint (moonshotai/mxfp4), fallbacks off, reasoning_effort none: backgammon League 3's Kimi K3.1 Pro (off) (openrouter:moonshotai/mxfp4, moonshotai/kimi-k3.1-pro, none). Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py moonshotai/kimi-k3.1-pro \
  --provider openrouter-chat \
  --openrouter-reasoning none \
  --openrouter-order moonshotai/mxfp4 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600 \
  --concurrency 4
