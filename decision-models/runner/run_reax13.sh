#!/usr/bin/env bash
# REAX 1.3 (decisionmodels/REAX-1.3 at fa4bf7ee3bb56a8bc421dad090631be1c5845c2d, Apache-2.0) on one RTX PRO 6000
# Blackwell (96 GB): two parts in FP8 on the one GPU (part G: CharlieBT/gx31-decider blended with PelaAI/KnowLine-31B-Gen1,
# Gemma-4-31B line; part Q: gurujustin/sn92-gen-p5 blended with vllm-sr/d3-ultra, Qwen 27B line), each option's
# probability the 50/50 mean of the two parts'. Served by the REAX Engine's own server, as the model card runs it: the
# reax13 mode of github.com/reaxlabs/reax-engine at ff8f595f149abdd50ea914455eadc74cf97a277f (images reax13-base from
# reax13/Dockerfile and reax13-runtime from reax13/Dockerfile.conv, built from the engine files alone; the Decision Index
# kit at 25c6ec7b6b5f44a216c63c3a700de3a9c6d6699d mounted at /kit), bound to 127.0.0.1. The card's command with two host
# differences: the GPU through the NVIDIA runtime (our Docker refuses --gpus without it), and no --security-opt
# no-new-privileges, because with it every exec in the container failed here with EPERM (cause not established). Neither
# changes the model or its answers, but the second is a security deviation of the runs of 6 November 2026 (not equivalent
# protection; outbound network was also open), not a default for other runs:
#   docker run -d --runtime nvidia --gpus device=GPU -p 127.0.0.1:PORT:8080 --read-only --user "$(id -u):$(id -g)" \
#     --cap-drop ALL --shm-size 8g --tmpfs /tmp:rw,exec,size=8g -v MODEL_REPO:/model:ro \
#     -v DECISION_INDEX/decision_index:/kit/decision_index:ro --entrypoint env reax13-runtime -i \
#     PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONPATH=/engine:/kit DUO_ISOLATED=1 HF_HUB_OFFLINE=1 \
#     TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/tmp/hf KERNELS_CACHE=/opt/kernels \
#     LOCAL_KERNELS=kernels-community/finegrained-fp8=/opt/fp8-kernel D3_STATE_ONCE=0 OMP_NUM_THREADS=4 \
#     OPENBLAS_NUM_THREADS=4 PYTORCH_ALLOC_CONF=expandable_segments:True TRITON_CACHE_DIR=/tmp/triton \
#     python /engine/serve.py --host 0.0.0.0 --port 8080 --model /model --config /engine/reax13.json
# One question per request, one request at a time, as every System One decision model here; the client timeout the
# model card asks for (1,800 s). A new run records its harness commit, so run this file from a checkout of the published
# repository, or set HARNESS_REPO to a clone of it. Smoke run first: this script with --sample 100 --seed 0, then
# ./benchmark_ollama.py --check-probabilities RUN must print PASS before the full run.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py reax13 \
  --provider reax \
  --data questions-v2.sqlite \
  --jev-url "${REAX_URL:?set REAX_URL to the REAX server, as http://HOST:PORT}" \
  --timeout 1800 \
  "$@"
