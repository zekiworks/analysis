#!/usr/bin/env bash
# Cloudflare's Clef-flash (9B) through ~/code/clef-flash/server.py, the Clef server with the Clef-flash
# release (Cloudflare/clef-flash at fde727a), on port 18095; start it first, on a free GPU.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py clef-flash \
  --provider clef \
  --jev-url http://127.0.0.1:18095 \
  --data questions-v2.sqlite \
  --timeout 60
