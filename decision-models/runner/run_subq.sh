#!/usr/bin/env bash
# SubQ's subq-snap-preview (public preview) through its hosted Decisions API, one request at a time as Decider v1.1
# ran, so the request times compare. The key comes from SUBQ_API_KEY, or from ~/.config/subq/key when that is unset.
# Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${SUBQ_API_KEY:-}" ]; then
  SUBQ_API_KEY="$(cat "$HOME/.config/subq/key")"
  export SUBQ_API_KEY
fi
./benchmark_ollama.py subq-snap-preview \
  --provider subq \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
