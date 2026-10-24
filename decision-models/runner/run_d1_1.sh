#!/usr/bin/env bash
# Liquid AI's d1.1 through its hosted decision API, under d1-ultra's protocol (run_d1_ultra.sh): one question per
# request, one request at a time, the same prompts, timeout and retries. The key comes from LIQUID_API_KEY, or from
# ~/.config/liquid/key when that is unset. A new run records its harness commit, so set HARNESS_REPO to a clone of the
# published repository when running from a folder outside git. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${LIQUID_API_KEY:-}" ]; then
  LIQUID_API_KEY="$(cat "$HOME/.config/liquid/key")"
  export LIQUID_API_KEY
fi
./benchmark_ollama.py d1.1 \
  --provider liquid \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
