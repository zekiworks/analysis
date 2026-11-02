#!/usr/bin/env bash
# The English reading track (approved by Ümit, 2 November 2026): the kept reading questions in English translation
# (translate_reading.py), asked as the text runs ask them, with the System One instructions naming English instead of
# Turkish (--english). Each lane runs one decision model through the script of its text runs, with the same settings,
# on the kept questions; REPEAT=N makes it repeat N. ENGLISH_TRANSLATIONS names the translations (JSONL) and
# ENGLISH_KEPT the kept question IDs, one per line. These runs stay out of the leaderboard (export_results.py).
# Lanes: d1-ultra subq-1.1 elephant-1 mammoth-1 jev-1.14 decider-v1.2 decider-flash-v1.2 decider-v1.1 glide glide-v1.2
# ms-decision-1 mercury-decide celeris d1 clef luna d3 d3-ultra drex-max-v1 drex-max-1.1
set -euo pipefail
cd "$(dirname "$0")"

variant=(
  --english "${ENGLISH_TRANSLATIONS:?set ENGLISH_TRANSLATIONS to the translations (JSONL)}"
  --questions "${ENGLISH_KEPT:?set ENGLISH_KEPT to the file of kept question IDs}"
  ${REPEAT:+--repeat "$REPEAT"}
)

run() {
  case "$1" in
    d1-ultra) ./run_d1_ultra.sh "${variant[@]}" ;;
    subq-1.1) ./run_subq_1_1.sh "${variant[@]}" ;;
    elephant-1) ./run_elephant_1.sh "${variant[@]}" ;;
    mammoth-1) ./run_mammoth_1.sh "${variant[@]}" ;;
    jev-1.14) ./run_jev_114.sh "${variant[@]}" ;;
    decider-v1.2) ./run_pplx_decider_v1_2.sh "${variant[@]}" ;;
    decider-flash-v1.2) ./run_pplx_decider_flash_v1_2.sh "${variant[@]}" ;;
    decider-v1.1) ./run_perplexity_v1_1.sh "${variant[@]}" ;;
    glide) ./run_glide.sh "${variant[@]}" ;;
    glide-v1.2) ./run_glide_v1_2.sh "${variant[@]}" ;;
    ms-decision-1) ./run_microsoft_decision_1.sh "${variant[@]}" ;;
    mercury-decide) ./run_mercury_decide.sh "${variant[@]}" ;;
    celeris) ./run_celeris.sh "${variant[@]}" ;;
    d1) ./run_liquid_d1.sh "${variant[@]}" ;;
    clef) ./run_clef.sh "${variant[@]}" ;;
    luna) ./run_openai_decisions.sh "${variant[@]}" ;;
    d3) ./run_vllm_sr_d3.sh "${variant[@]}" ;;
    d3-ultra) ./run_d3_ultra.sh "${variant[@]}" ;;
    drex-max-v1) ./run_drex_max_v1.sh "${variant[@]}" ;;
    drex-max-1.1) ./run_drex_max_1_1.sh "${variant[@]}" ;;
    *) echo "unknown lane: $1" >&2; exit 2 ;;
  esac
}

if [ "$#" -eq 0 ]; then
  sed -n '2,8p' "$0" >&2
  exit 2
fi
for lane in "$@"; do run "$lane"; done
