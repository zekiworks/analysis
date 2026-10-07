#!/usr/bin/env bash
# Clef through ~/code/clef/server.py (start it first, on a free GPU).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py clef \
  --provider clef \
  --data questions-v2.sqlite \
  --timeout 120
