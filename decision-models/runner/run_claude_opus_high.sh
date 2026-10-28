#!/usr/bin/env bash
# Claude Opus 5.5 through the Claude Code CLI signed in with a Claude subscription, at effort high (run 278).
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py claude-opus-5-5 \
  --provider claude \
  --claude-effort high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
