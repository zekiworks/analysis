#!/usr/bin/env bash
# Celeris's celeris-1-decision through its hosted System One API, one request at a time as Decider v1.1 ran, so
# the request times compare. The key comes from CELERIS_API_KEY, or from ~/.config/celeris/key when that is unset.
# Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${CELERIS_API_KEY:-}" ]; then
  CELERIS_API_KEY="$(cat "$HOME/.config/celeris/key")"
  export CELERIS_API_KEY
fi
./benchmark_ollama.py celeris-1-decision \
  --provider celeris \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
