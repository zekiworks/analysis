#!/usr/bin/env bash
# Clef through Clef's server (server.py in its repository; start it first, on a free GPU, and set CLEF_URL).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py clef \
  --provider clef \
  --data questions-v2.sqlite \
  --timeout 120
