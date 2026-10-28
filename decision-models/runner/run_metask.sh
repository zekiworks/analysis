#!/usr/bin/env bash
# Metask-Jev-4B through Metask-Jev's server (server.py in its repository; start it first, on a free GPU, and set
# METASK_URL).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py metask-jev-4b-policy-mix \
  --provider metask \
  --data questions-v2.sqlite \
  --timeout 120
