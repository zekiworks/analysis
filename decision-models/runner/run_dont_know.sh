#!/usr/bin/env bash
# The "I don't know" track: every question gets the option "Bilmiyorum" after its five, never shuffled and never correct,
# and the System One instructions end with "If you do not know the answer, choose Bilmiyorum." (--dont-know). Each lane
# runs one decision model through the script of its text runs, with the same settings; REPEAT=N makes it repeat N.
# These runs stay out of the leaderboard (export_results.py).
# Lanes: d1-ultra glide-v1.2 glide d3 d3-ultra drex-max-v1 drex-max-1.1 decider-v1.2 subq-preview subq-1.1 elephant-1
# mammoth-1
set -euo pipefail
cd "$(dirname "$0")"

variant=(--dont-know ${REPEAT:+--repeat "$REPEAT"})

run() {
  case "$1" in
    d1-ultra) ./run_d1_ultra.sh "${variant[@]}" ;;
    glide-v1.2) ./run_glide_v1_2.sh "${variant[@]}" ;;
    glide) ./run_glide.sh "${variant[@]}" ;;
    d3) ./run_vllm_sr_d3.sh "${variant[@]}" ;;
    d3-ultra) ./run_d3_ultra.sh "${variant[@]}" ;;
    drex-max-v1) ./run_drex_max_v1.sh "${variant[@]}" ;;
    drex-max-1.1) ./run_drex_max_1_1.sh "${variant[@]}" ;;
    decider-v1.2) ./run_pplx_decider_v1_2.sh "${variant[@]}" ;;
    subq-preview) ./run_subq.sh "${variant[@]}" ;;
    subq-1.1) ./run_subq_1_1.sh "${variant[@]}" ;;
    elephant-1) ./run_elephant_1.sh "${variant[@]}" ;;
    mammoth-1) ./run_mammoth_1.sh "${variant[@]}" ;;
    *) echo "unknown lane: $1" >&2; exit 2 ;;
  esac
}

if [ "$#" -eq 0 ]; then
  sed -n '2,7p' "$0" >&2
  exit 2
fi
for lane in "$@"; do run "$lane"; done
