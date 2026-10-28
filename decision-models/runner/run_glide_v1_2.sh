#!/usr/bin/env bash
# Fastino's GLiDE v1.2 (glide-v1.2) from its released checkpoint (fastino/GLiDE at a7e4589) behind the server its
# repository ships (python -m glide.server), on a DGX Spark (GB10): one question
# per request, one request at a time, so that no other request shares its forward pass. Add --repeat N (2 or more) for
# a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py glide-v1.2 \
  --provider glide \
  --data questions-v2.sqlite \
  --jev-url "${GLIDE_V1_2_URL:?set GLIDE_V1_2_URL to the GLiDE v1.2 server, as http://HOST:PORT}" \
  --timeout 60 \
  "$@"
