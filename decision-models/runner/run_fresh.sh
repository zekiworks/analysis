#!/usr/bin/env bash
# Step 3.5: configurations on the fresh 2026-TYT Türkçe questions, each with the settings of its run on the book.
# Run it after the 40 questions have been checked (fresh/review/review.html, then repair_questions.py apply).
# Everything stays in fresh/; publish only aggregates. Give one or more lanes:
#   astra opus sonnet-high decider-v1 jev-1.13 d1 open-jev erk qwen3-14b   (run on 3 and 6 October 2026)
#   d1-ultra jev-1.14 glide decider-v1.2 decider-flash-v1.2
# Open-Jev needs open-jev.service on 192.168.1.126:8791; Erk-14B and Qwen3-14B need their vLLM containers on ports
# 8893 and 8892 (README, "Run against vLLM").
set -euo pipefail
cd "$(dirname "$0")"

bank=(--data fresh/tyt-2026.sqlite --database fresh/results.sqlite --output fresh/results.md)

run() {
  case "$1" in
    astra) ./benchmark_ollama.py gpt-6-astra --provider openai --openai-reasoning low --batch-size 16 --timeout 600 "${bank[@]}" ;;
    opus) ./benchmark_ollama.py claude-opus-5-5 --provider claude --claude-effort low --batch-size 16 --timeout 600 "${bank[@]}" ;;
    sonnet-high) ./benchmark_ollama.py claude-sonnet-5-5 --provider claude --claude-effort high --batch-size 16 --timeout 600 "${bank[@]}" ;;
    decider-v1) ./benchmark_ollama.py pplx-decider-v1-27b --provider perplexity --timeout 30 "${bank[@]}" ;;
    jev-1.13) JEV_API_KEY="$(cat "$HOME/code/jev/key")" ./benchmark_ollama.py jev-1.13.0 --provider jev --timeout 30 "${bank[@]}" ;;
    d1) ./benchmark_ollama.py d1:free --provider liquid --timeout 30 "${bank[@]}" ;;
    open-jev) ./benchmark_ollama.py open-jev-27b-v1.1 --provider open-jev --timeout 30 "${bank[@]}" ;;
    erk) ./benchmark_ollama.py erk-14b --provider vllm --vllm-url http://127.0.0.1:8893 --batch-size 16 "${bank[@]}" ;;
    qwen3-14b) ./benchmark_ollama.py qwen3-14b --provider vllm --vllm-url http://127.0.0.1:8892 --batch-size 16 "${bank[@]}" ;;
    d1-ultra) ./run_d1_ultra.sh "${bank[@]}" ;;
    jev-1.14) JEV_API_KEY="$(cat "$HOME/code/jev/key")" ./benchmark_ollama.py jev-1.14.0 --provider jev --timeout 30 "${bank[@]}" ;;
    glide) ./run_glide.sh "${bank[@]}" ;;
    decider-v1.2) ./run_perplexity_v1_2.sh "${bank[@]}" ;;
    decider-flash-v1.2) ./run_perplexity_flash_v1_2.sh "${bank[@]}" ;;
    *) echo "unknown lane: $1" >&2; exit 2 ;;
  esac
}

if [ "$#" -eq 0 ]; then
  sed -n '2,8p' "$0" >&2
  exit 2
fi
for lane in "$@"; do run "$lane"; done
