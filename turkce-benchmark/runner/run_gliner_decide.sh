#!/usr/bin/env bash
# GLiNER2.5-multi-Decide, Fastino's decision fine-tune of GLiNER2.5 Multi, through the same server with
# --model-dir model-decide --model-name gliner2.5-multi-decide on port 18094 (start it first, on a free GPU).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gliner2.5-multi-decide \
  --provider gliner \
  --jev-url http://127.0.0.1:18094 \
  --data questions-v2.sqlite \
  --timeout 60
