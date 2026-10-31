#!/usr/bin/env bash
# Nace.AI's Drex Max v1 open weights (nace-ai/drex-max-v1 at cac65e1982a0237e996419ba559004522d9a33ac, bf16) on one RTX
# PRO 6000 Blackwell (96 GB), scored by Nace's own loader (drex_max, from github.com/nace-ai/drex-decision-models at
# e206b278e3988ad1b58e6f1556b559a65947a4e6, Python 3.12 with only models/drex-max-v1/requirements.txt installed: torch
# 2.15.0, transformers 5.17.0, flash-linear-attention 0.6.0; causal_conv1d not installed, so its reference path) behind
# servers/drex_max_server.py:
#   CUDA_VISIBLE_DEVICES=GPU .venv-drex-max/bin/python servers/drex_max_server.py \
#     --checkpoint <the nace-ai/drex-max-v1 snapshot at cac65e1> --code <the drex-decision-models checkout at e206b27> \
#     --name drex-max-v1 --host HOST --port PORT
# One question per request, one request at a time, with the timeout of the other System One runs. A new run records its
# harness commit, so run this file from a checkout of the published repository, or set HARNESS_REPO to a clone of it.
# Add --repeat N (2 or more) for a repeat. Smoke run first: this script with --sample 100 --seed 0, then
# ./benchmark_ollama.py --check-probabilities RUN must print PASS before the five full runs.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py drex-max-v1 \
  --provider drex-max \
  --data questions-v2.sqlite \
  --jev-url "${DREX_MAX_URL:?set DREX_MAX_URL to the Drex Max server, as http://HOST:PORT}" \
  --timeout 30 \
  "$@"
