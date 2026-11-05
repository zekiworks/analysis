#!/usr/bin/env bash
# PWS-Decisions for the site's decision models (Ümit #1273): three runs of the public questions per setup, one question
# per request. Providers in parallel; each provider's setups and runs one after another. Then the totals
# (pws-decisions.json). Keys from ~/.keys (and Celeris's key file), under the runner's variable names; never printed.
set -uo pipefail
cd "$(dirname "$0")/.."
L=${PWS_LOG:-$HOME/vision-track/pws-grounding/bench.log}
set -a; . "$HOME/.keys"; set +a
export LIQUID_API_KEY="${LIQUID_API_KEY:-${LIQUIDAI_API_KEY:-}}" NACE_API_KEY="${NACE_API_KEY:-${NACEAI_API_KEY:-}}"
[ -z "${CELERIS_API_KEY:-}" ] && [ -f "$HOME/.config/celeris/key" ] && CELERIS_API_KEY="$(cat "$HOME/.config/celeris/key")" \
  && export CELERIS_API_KEY
export PYTHONDONTWRITEBYTECODE=1
lanes=(
  "perplexity-v1.2 perplexity-v1.2-web"
  "openai-luna"
  "jev-1.14 jev-1.13"
  "d1-ultra d1.1 d1-free"
  "celeris"
  "subq-1.1 subq-preview"
  "meragpt"
  "drex-max-1.1 drex-2.0"
  "ms-decision-1 mercury-decide"
)
echo "$(date -u +%FT%T) start" >> "$L"
pids=()
for lane in "${lanes[@]}"; do
  # shellcheck disable=SC2086
  python3 -B pws/bench.py run $lane >> "$L" 2>&1 & pids+=($!)
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
echo "$(date -u +%FT%T) runs done (exit $rc)" >> "$L"
python3 -B pws/bench.py summary >> "$L" 2>&1 || rc=1
echo "$(date -u +%FT%T) end (exit $rc)" >> "$L"
exit $rc
