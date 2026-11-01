#!/usr/bin/env bash
# Liquid AI's open d1-2B weights (LiquidAI/d1-2B at 10e7671d44e4b37700020b1eed3f594c5f2af0b4, bf16, built on LFM3-VL-2B)
# on one RTX PRO 6000 Blackwell (96 GB), answered by the model card's call (model.system_one, Liquid's own model code
# through transformers' AutoModel with trust_remote_code=True; Python 3.12 with only the card's requirements:
# transformers 5.22.1, torch 2.15.0, torchvision 0.29.2, pillow 13.0.0) behind servers/d1_server.py:
#   CUDA_VISIBLE_DEVICES=GPU HF_HUB_OFFLINE=1 .venv/bin/python servers/d1_server.py --model LiquidAI/d1-2B \
#     --revision 10e7671d44e4b37700020b1eed3f594c5f2af0b4 --host HOST --port PORT
# One question per request, one request at a time, the request of the hosted Liquid d1 runs, the timeout of the other
# System One runs. A new run records its harness commit, so run this file from a checkout of the published repository,
# or set HARNESS_REPO to a clone of it. Add --repeat N (2 or more) for a repeat. Smoke run first: this script with
# --sample 100 --seed 0, then ./benchmark_ollama.py --check-probabilities RUN must print PASS before the five full runs.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py LiquidAI/d1-2B \
  --provider d1-server \
  --data questions-v2.sqlite \
  --jev-url "${D1_SERVER_URL:?set D1_SERVER_URL to the d1 server, as http://HOST:PORT}" \
  --timeout 30 \
  "$@"
