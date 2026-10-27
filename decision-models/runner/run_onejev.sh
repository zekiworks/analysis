#!/usr/bin/env bash
# OmniJev's OneJev-27B (OmniJev/OneJev-27B at a5e5f55) behind the server its package ships (qev 0.1.4, from
# github.com/OmniJev/OneJev) on bariton's GPU 2, an RTX PRO 6000 Blackwell, in BF16 with the calibration shipped next to
# the weights (the server's defaults):
#   qev serve --model <the OmniJev/OneJev-27B snapshot at a5e5f55bdbdc9deda44f3fcb5b163776b9b369e8> \
#     --name OmniJev/OneJev-27B --multimodal --host 127.0.0.1 --port 18111
# One question per request, one request at a time, with the timeout of the other System One runs. A new run records its
# harness commit, so run this file from a checkout of the published repository, or set HARNESS_REPO to a clone of it.
# Add --repeat N (2 or more) for a repeat.
set -euo pipefail
cd "$(dirname "$0")"
./benchmark_ollama.py OmniJev/OneJev-27B \
  --provider onejev \
  --data questions-v2.sqlite \
  --jev-url http://127.0.0.1:18111 \
  --timeout 30 \
  "$@"
