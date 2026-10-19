#!/usr/bin/env bash
# meraGPT's Decider 1 (decider-1) through its hosted System One API, one request at a time as Decider v1.1 ran, so the
# request times compare. The key comes from MERAGPT_API_KEY, or from ~/.keys when that is unset. Add --repeat N (2 or
# more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${MERAGPT_API_KEY:-}" ]; then
  MERAGPT_API_KEY="$(bash -c 'source "$HOME/.keys" && printf %s "${MERAGPT_API_KEY:-}"')"
  export MERAGPT_API_KEY
fi
./benchmark_ollama.py decider-1 \
  --provider meragpt \
  --data questions-v2.sqlite \
  --timeout 30 \
  "$@"
