#!/usr/bin/env bash
# Winnow-12B (Q8_0) through its own server, the winnow-inference Docker image (start it first).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py winnow-12b \
  --provider winnow \
  --data questions-v2.sqlite \
  --timeout 180
