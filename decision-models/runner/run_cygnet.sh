#!/usr/bin/env bash
# Cygnet through its decision server, ~/code/cygnet/shim/decision_server.py, over vLLM 0.30.0 (start both first).
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py cygnet \
  --provider cygnet \
  --data questions-v2.sqlite \
  --timeout 180
