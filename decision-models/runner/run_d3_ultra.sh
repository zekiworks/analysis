#!/usr/bin/env bash
# The vLLM Semantic Router's d3-ultra (vllm-sr/d3-ultra at 52ba9e7) through the server its repository ships (d3_server.py,
# on the package's own transformers runtime, as AutoModel loads it in the model card's Quickstart; transformers 5.17.0,
# torch 2.14.1, flash-linear-attention 0.5.2, from the repository's requirements.txt) on one RTX PRO 6000 Blackwell
# (96 GB):
#   python d3_server.py --model <the vllm-sr/d3-ultra snapshot at 52ba9e7a00402f9560c7fba8c039608e7ddee7fb> \
#     --device cuda:0 --host HOST --port PORT
# vLLM cannot serve d3-ultra yet: it rejects the checkpoint's attention mode (prefix_bidir). One question per request,
# one request at a time. A new run records its harness commit, so run this file from a checkout of the published
# repository, or set HARNESS_REPO to a clone of it. Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py vllm-sr/d3-ultra \
  --provider d3-server \
  --data questions-v2.sqlite \
  --jev-url "${D3_SERVER_URL:?set D3_SERVER_URL to the d3 server, as http://HOST:PORT}" \
  --timeout 60 \
  "$@"
