#!/usr/bin/env bash
# Base Labs' elephant-1 (baselabs/elephant-1 at b3f8a93462fb1051a9de031e94a7ff380e254072, bf16) on one RTX PRO 6000
# Blackwell (96 GB), answered by the model card's loader (qev's DecisionEngine from OneJev at 81ce62f with the
# checkpoint's serve.patch, as the card's setup.sh installs it in pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel) behind
# servers/baselabs_server.py:
#   docker run --rm --gpus device=GPU -p 127.0.0.1:PORT:PORT -v ~/.cache/huggingface/hub:/hf:ro \
#     -v "$PWD/servers:/servers:ro" baselabs-serve:81ce62f python /servers/baselabs_server.py \
#     --checkpoint <the baselabs/elephant-1 snapshot at b3f8a93> --name baselabs/elephant-1 --host 0.0.0.0 --port PORT
# One question per request, one request at a time, with the timeout of the other System One runs. A new run records its
# harness commit, so run this file from a checkout of the published repository, or set HARNESS_REPO to a clone of it.
# Add --repeat N (2 or more) for a repeat. Smoke run first: this script with --sample 100 --seed 0, then
# ./benchmark_ollama.py --check-probabilities RUN must print PASS before the five full runs.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py baselabs/elephant-1 \
  --provider baselabs \
  --data questions-v2.sqlite \
  --jev-url "${BASELABS_URL:?set BASELABS_URL to the Base Labs server, as http://HOST:PORT}" \
  --timeout 30 \
  "$@"
