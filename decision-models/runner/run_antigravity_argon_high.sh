#!/usr/bin/env bash
# Gemini 4 Argon through Google Antigravity on the Google AI Ultra subscription (OMP's google-antigravity login), thinking level high: backgammon League 3's Gemini 4 Argon (on) (antigravity-subscription, antigravity/gemini-4-argon, high).
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-4-argon \
  --provider antigravity \
  --antigravity-thinking high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4
