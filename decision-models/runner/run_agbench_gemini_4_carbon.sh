#!/usr/bin/env bash
# Gemini 4 Carbon through Can's Antigravity subscription bridge (agbench, --agbench-url, default
# http://192.168.1.120:8899/v1/chat/completions) at high thinking, with ~11k tokens of Antigravity's own context in
# every request: a setup apart from the Gemini API route. One request at a time, 16 questions per request as for the
# other chat setups, the answer schema as response_format. $0 billed (the Antigravity subscription; Ümit via Zeki
# #5133); its cost is the same tokens at the Gemini API's price. Add --english FILE and the rest as for the other chat
# setups; add --agbench-answer-layout only if a smoke shows the bridge rejects response_format.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gemini-4-carbon \
  --provider agbench \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 1800 \
  --concurrency 1 \
  "$@"
