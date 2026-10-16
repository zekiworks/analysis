#!/usr/bin/env bash
# Liquid AI's d1-ultra through its hosted decision API, one request at a time as d1 and Decider v1.1 ran, so the
# request times compare. The key comes from LIQUID_API_KEY, or from ~/.config/liquid/key when that is unset.
# Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${LIQUID_API_KEY:-}" ]; then
  LIQUID_API_KEY="$(cat "$HOME/.config/liquid/key")"
  export LIQUID_API_KEY
fi
./benchmark_ollama.py d1-ultra \
  --provider liquid \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
