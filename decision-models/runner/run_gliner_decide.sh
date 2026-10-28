#!/usr/bin/env bash
# GLiNER2.5-multi-Decide, Fastino's decision fine-tune of GLiNER2.5 Multi, through the same server with
# --model-dir model-decide --model-name gliner2.5-multi-decide (start it first, on a free GPU).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gliner2.5-multi-decide \
  --provider gliner \
  --jev-url "${GLINER_DECIDE_URL:?set GLINER_DECIDE_URL to the GLiNER2.5-multi-Decide server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --timeout 60
