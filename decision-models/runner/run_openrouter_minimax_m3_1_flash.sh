#!/usr/bin/env bash
# MiniMax-M3.1-Flash through OpenRouter pinned to MiniMax's own endpoint (minimax), fallbacks off, required parameters, reasoning_effort high, 16 questions per request (project lead, bus #2959). Only this endpoint reports reasoning tokens (Parasail's and Nebius' reported 0, so their reasoning could not be verified); it has JSON mode but no structured outputs, and in JSON mode alone it answered in a layout of its own (run 843). So the request asks for JSON mode (--openrouter-json-object; required parameters kept, since JSON mode is required) and states the answer layout in the prompt (--openrouter-answer-layout): a prompt difference from the other chat setups, and its answers are read strictly in that layout. Add --english FILE, --dont-know and the rest as arguments. Needs OPENROUTER_API_KEY.
# A new run records its harness commit, so set HARNESS_REPO to a clone of the published repository.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py minimax/minimax-m3.1-flash \
  --provider openrouter-chat \
  --openrouter-reasoning high \
  --openrouter-order minimax \
  --openrouter-require-parameters \
  --openrouter-json-object \
  --openrouter-answer-layout \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 900 \
  --concurrency 4 \
  "$@"
