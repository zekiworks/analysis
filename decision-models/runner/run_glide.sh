#!/usr/bin/env bash
# Fastino's GLiDE through its hosted System One API; the key comes from FASTINO_API_KEY.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py fastino/GLiDE \
  --provider fastino \
  --data questions-v2.sqlite \
  --timeout 300 \
  --concurrency 4
