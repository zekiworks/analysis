#!/usr/bin/env bash
# Claude Fable 5.1 through the Claude Code CLI on the Claude subscription, effort high: backgammon League 3's Claude Fable 5.1 (on) (claude-subscription, anthropic/claude-fable-5-1, high).
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py claude-fable-5-1 \
  --provider claude \
  --claude-effort high \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
