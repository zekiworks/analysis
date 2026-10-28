#!/usr/bin/env bash
# The vLLM Semantic Router's Decision 3.0 d3 (vllm-sr/d3 at 20f37b9) on vLLM's own System One endpoint, from a vLLM
# nightly (0.32.1rc1.dev613+g8977b13a1) on one RTX PRO 6000 Blackwell (96 GB), in BF16:
#   vllm serve vllm-sr/d3 --revision 20f37b9a892acc13d4b07a4f3c4f11b2518c615c --max-model-len 32768 \
#     --dtype bfloat16 --max-num-seqs 256 --host HOST --port PORT
# (--max-num-seqs 256 because the default, 1024, sizes the startup profiling past the GPU's memory). One question per
# request, one request at a time, with the timeout of the other System One runs. A new run records its harness commit,
# so run this file from a checkout of the published repository, or set HARNESS_REPO to a clone of it. Add --repeat N
# (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py vllm-sr/d3 \
  --provider vllm-sr \
  --data questions-v2.sqlite \
  --jev-url "${VLLM_SR_URL:?set VLLM_SR_URL to the vLLM server, as http://HOST:PORT}" \
  --timeout 30 \
  "$@"
