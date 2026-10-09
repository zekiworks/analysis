#!/usr/bin/env bash
# Metask-Jev-4B through ~/code/metask-jev/server.py (start it first, on a free GPU).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py metask-jev-4b-policy-mix \
  --provider metask \
  --data questions-v2.sqlite \
  --timeout 120
