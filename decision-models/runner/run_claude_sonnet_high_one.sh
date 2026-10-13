#!/usr/bin/env bash
# Claude Sonnet 5.5 at high effort, one question per request (v2 plan, part D): the questions, prompt and closed-book
# Claude Code settings of run_claude_sonnet_high.sh, which asks 16 questions per request. A new run records its harness
# commit, so set HARNESS_REPO to a clone of the published repository when running from a folder outside git.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py claude-sonnet-5-5 \
  --provider claude \
  --claude-effort high \
  --data questions-v2.sqlite \
  --batch-size 1 \
  --timeout 600 \
  "$@"
