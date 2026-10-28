#!/usr/bin/env bash
# Cloudflare's Clef-flash (9B) through the Clef-flash server (server.py in its repository), the Clef server with the
# Clef-flash release (Cloudflare/clef-flash at fde727a); start it first, on a free GPU.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py clef-flash \
  --provider clef \
  --jev-url "${CLEF_FLASH_URL:?set CLEF_FLASH_URL to the Clef-flash server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --timeout 60
