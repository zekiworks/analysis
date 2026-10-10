#!/usr/bin/env bash
# Fastino's GLiDE through its hosted System One API, 4 requests at a time. The key comes from FASTINO_API_KEY, or from
# ~/.config/fastino/key when that is unset. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${FASTINO_API_KEY:-}" ]; then
  FASTINO_API_KEY="$(cat "$HOME/.config/fastino/key")"
  export FASTINO_API_KEY
fi
./benchmark_ollama.py fastino/GLiDE \
  --provider fastino \
  --data questions-v2.sqlite \
  --timeout 300 \
  --concurrency 4 \
  "$@"
