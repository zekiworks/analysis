#!/usr/bin/env bash
# The swap test: each question's correct option shows the text of a fixed random wrong option, its twin
# (--replace-key-text 1, as GPT-6 Astra's run 56), so no option is right and two letters show the same text.
# Each lane runs one model with the settings of its run on the book; the report counts, by kind of option, its picks
# of the original letter, of the twin and of the rest. Swap runs stay out of the leaderboard (export_results.py).
# Lanes: d1-ultra jev-1.14 glide decider-v1.2 decider-flash-v1.2
set -euo pipefail
cd "$(dirname "$0")"

swap=(--replace-key-text 1)

run() {
  case "$1" in
    d1-ultra) ./run_d1_ultra.sh "${swap[@]}" ;;
    jev-1.14) JEV_API_KEY="$(cat "$HOME/code/jev/key")" ./benchmark_ollama.py jev-1.14.0 --provider jev \
      --data questions-v2.sqlite --timeout 30 "${swap[@]}" ;;
    glide) ./run_glide.sh "${swap[@]}" ;;
    decider-v1.2) ./run_perplexity_v1_2.sh "${swap[@]}" ;;
    decider-flash-v1.2) ./run_perplexity_flash_v1_2.sh "${swap[@]}" ;;
    *) echo "unknown lane: $1" >&2; exit 2 ;;
  esac
}

if [ "$#" -eq 0 ]; then
  sed -n '2,6p' "$0" >&2
  exit 2
fi
for lane in "$@"; do run "$lane"; done
