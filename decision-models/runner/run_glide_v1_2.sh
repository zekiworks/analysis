#!/usr/bin/env bash
# Fastino's GLiDE v1.2 (glide-v1.2) from its released checkpoint (fastino/GLiDE at a7e4589) behind the server its
# repository ships (python -m glide.server), on spark3, a DGX Spark (GB10) at 192.168.1.139, port 8888: one question
# per request, one request at a time, so that no other request shares its forward pass. Add --repeat N (2 or more) for
# a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py glide-v1.2 \
  --provider glide \
  --data questions-v2.sqlite \
  --jev-url http://192.168.1.139:8888 \
  --timeout 60 \
  "$@"
