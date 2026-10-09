#!/usr/bin/env bash
# GLiNER2.5 Multi through ~/code/gliner2.5-multi-v1/server.py (start it first, on a free GPU).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gliner2.5-multi-v1 \
  --provider gliner \
  --data questions-v2.sqlite \
  --timeout 60
