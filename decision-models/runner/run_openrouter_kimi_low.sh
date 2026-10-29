#!/usr/bin/env bash
# Kimi K3.1 Pro through OpenRouter pinned to Moonshot AI's endpoint (moonshotai/mxfp4), fallbacks off, reasoning_effort
# low: the route of run_openrouter_kimi.sh (backgammon's Kimi K3.1 Pro (off)) with low reasoning, as Ümit asked on
# 29 October 2026. Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py moonshotai/kimi-k3.1-pro \
  --provider openrouter-chat \
  --openrouter-reasoning low \
  --openrouter-order moonshotai/mxfp4 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
