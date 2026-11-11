#!/usr/bin/env bash
# Claude Fable 5.2 at max effort (Anthropic's highest level), through the Claude Code CLI signed in with the Claude
# subscription, 16 questions per request. Up to 30 minutes per request: at max the model thinks long.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py claude-fable-5-2 \
  --provider claude \
  --claude-effort max \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 1800 \
  "$@"
