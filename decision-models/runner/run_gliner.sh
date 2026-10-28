#!/usr/bin/env bash
# GLiNER2.5 Multi through its server (server.py in the gliner2.5-multi-v1 repository; start it first, on a free GPU,
# and set GLINER_URL).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py gliner2.5-multi-v1 \
  --provider gliner \
  --data questions-v2.sqlite \
  --timeout 60
