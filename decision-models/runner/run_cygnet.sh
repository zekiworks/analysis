#!/usr/bin/env bash
# Cygnet through its decision server (shim/decision_server.py in Cygnet's repository), over vLLM 0.30.0 (start both
# first, and set CYGNET_URL).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py cygnet \
  --provider cygnet \
  --data questions-v2.sqlite \
  --timeout 180
