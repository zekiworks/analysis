#!/usr/bin/env bash
# The runs of plan step 5.3: repeats, Qwen's vote share and the cascade pipelines.
#
#   ./run_experiments.sh LANE
#
# A lane runs its configuration's runs one after another; lanes can run side by side. Repeat 1 is the run
# without --repeat. Every run resumes where it stopped when started again. Override REPEATS (e.g.
# REPEATS="4 5") to split a lane over servers, and the server URLs below to point at another server.
set -euo pipefail
cd "$(dirname "$0")"

DATA=questions-v2.sqlite
SAMPLE=200 # the batched repeats' fixed sample (benchmark_ollama.py's default seed)
GEMMA_URL=${GEMMA_URL:-http://192.168.1.126:8010}
QWEN_URL=${QWEN_URL:-http://127.0.0.1:8897}
OPEN_JEV_URL=${OPEN_JEV_URL:-http://192.168.1.126:8791}
DEEPSEEK_URL=${DEEPSEEK_URL:-http://192.168.1.126:8010}

bench() { # one run; with RETRIES set, a failed run is started again (it resumes) after RETRY_WAIT seconds
  local attempt=0
  until ./benchmark_ollama.py "$@"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt "${RETRIES:-0}" ]; then
      return 1
    fi
    echo "run failed; starting it again in ${RETRY_WAIT:-300}s (restart $attempt of ${RETRIES:-0})" >&2
    sleep "${RETRY_WAIT:-300}"
  done
}

repeats() { # repeats DEFAULT_REPEATS ARGS...
  local default=$1
  shift
  for n in ${REPEATS:-$default}; do
    if [ "$n" -eq 1 ]; then
      bench "$@"
    else
      bench "$@" --repeat "$n"
    fi
  done
}

astra=(gpt-6-astra --provider openai --openai-reasoning low --data "$DATA" --batch-size 16 --timeout 600)
sonnet_high=(claude-sonnet-5-5 --provider claude --claude-effort high --data "$DATA" --batch-size 16 --timeout 600)

case "${1:-}" in
  # Batched setups: 5 runs on one fixed 200-question sample, the same batches every time.
  gemma-sample) repeats "1 2 3 4 5" gemma-4-31B-it --provider vllm --vllm-url "$GEMMA_URL" --data "$DATA" --batch-size 16 --sample "$SAMPLE" ;;
  astra-sample) repeats "1 2 3 4 5" "${astra[@]}" --sample "$SAMPLE" ;;
  opus-sample) repeats "1 2 3 4 5" claude-opus-5-5 --provider claude --claude-effort low --data "$DATA" --batch-size 16 --timeout 600 --sample "$SAMPLE" ;;
  sonnet-high-sample) repeats "1 2 3 4 5" "${sonnet_high[@]}" --sample "$SAMPLE" ;;
  # DeepSeek needs all four GPUs (deepseek-v41.service), so Gemma is stopped while these run.
  deepseek-sample) repeats "1 2 3 4 5" deepseek-v4.1-flash --provider vllm --vllm-url "$DEEPSEEK_URL" --data "$DATA" --batch-size 16 --sample "$SAMPLE" ;;
  deepseek-thinking-sample) repeats "1 2 3 4 5" deepseek-v4.1-flash --provider vllm --vllm-thinking --concurrency 8 --vllm-url "$DEEPSEEK_URL" --data "$DATA" --batch-size 16 --timeout 3600 --sample "$SAMPLE" ;;
  # One-question setups: repeats 2–5 of the whole-bank run.
  jev)
    JEV_API_KEY="$(cat "$HOME/code/jev/key")"
    export JEV_API_KEY
    repeats "2 3 4 5" jev-1.13.0 --provider jev --data "$DATA" --timeout 30
    ;;
  decider) repeats "2 3 4 5" pplx-decider-v1-27b --provider perplexity --data "$DATA" --timeout 30 ;;
  d1) repeats "2 3 4 5" d1:free --provider liquid --data "$DATA" --timeout 30 ;;
  open-jev) repeats "2 3 4 5" open-jev-27b-v1.1 --provider open-jev --jev-url "$OPEN_JEV_URL" --data "$DATA" --timeout 30 ;;
  qwen-yes-no) repeats "2 3 4 5" qwen38-27b-bf16 --provider vllm-yes-no --vllm-url "$QWEN_URL" --data "$DATA" --timeout 30 ;;
  qwen-stated) repeats "2 3 4 5" qwen38-27b-bf16 --provider vllm-verbal --vllm-url "$QWEN_URL" --data "$DATA" --timeout 30 ;;
  # Qwen's stated-confidence prompt sampled 10 times per question: the vote share.
  qwen-vote) bench qwen38-27b-bf16 --provider vllm-vote --vllm-url "$QWEN_URL" --data "$DATA" --timeout 120 ;;
  # Cascade pipelines (plans in pipeline/, from cascade_pipeline.py): the frontier configuration on the
  # questions the Decider passes on, and on every held-out question.
  astra-passed) bench "${astra[@]}" --questions pipeline/decider-astra-passed.txt ;;
  astra-held-out) bench "${astra[@]}" --questions pipeline/decider-astra-held-out.txt ;;
  sonnet-high-passed) bench "${sonnet_high[@]}" --questions pipeline/decider-sonnet-high-passed.txt ;;
  sonnet-high-held-out) bench "${sonnet_high[@]}" --questions pipeline/decider-sonnet-high-held-out.txt ;;
  *)
    sed -n '2,8p' "$0" >&2
    exit 2
    ;;
esac
