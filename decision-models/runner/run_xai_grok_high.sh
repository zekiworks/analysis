#!/usr/bin/env bash
# Grok 4.7 through xAI's Responses API on the SuperGrok subscription (OMP's xai-oauth login), reasoning effort high: backgammon League 3's Grok 4.7 (on) (xai-subscription, xai/grok-4.7, high).
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py grok-4.7 \
  --provider xai \
  --xai-reasoning high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
