#!/usr/bin/env bash
# Nace.AI's Drex Max 1.1 (drex-max-v1.1, released 28 October 2026; no open weights) through Nace's hosted System One
# endpoint (console.nace.ai/v1/systemone), under the protocol of the other decision models: one question per request,
# one request at a time, the same prompts, timeout and retries. The key comes from NACE_API_KEY, or from
# ~/.config/nace/key when that is unset. A new run records its harness commit, so set HARNESS_REPO to a clone of the
# published repository when running from a folder outside git. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${NACE_API_KEY:-}" ]; then
  NACE_API_KEY="$(cat "$HOME/.config/nace/key")"
  export NACE_API_KEY
fi
./benchmark_ollama.py drex-max-v1.1 \
  --provider nace \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
