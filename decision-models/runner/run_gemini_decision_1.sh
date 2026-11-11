#!/usr/bin/env bash
# Google's Gemini Decision 1 (gemini-decision-1, launched 11 November 2026) through Google's Decisions API, POST
# /v1beta/decisions, one question per request as the other decision models. The key: GEMINI_API_KEY, else
# ~/.config/gemini/key (as for run_gemini.sh), on a project with billing: an empty prepayment answers HTTP 402, which
# stops the run. Add --dont-know, --english FILE and --repeat N (2 or more) as for the other decision models.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-decision-1 \
  --provider gemini-decisions \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
