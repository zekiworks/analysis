#!/usr/bin/env bash
# PWS-Decisions for the site's decision models (Ümit #1273) and chat models (#1324): three runs of the public questions
# per setup, one question per request. Providers (for the chat models: each access, with and without web) in parallel;
# each lane's setups and runs one after another; a chat lane asks its failed requests again (--retry-errors). Then the
# totals (pws-decisions.json). Keys from ~/.keys (and Celeris's key file), under the runner's variable names; never
# printed. The subscriptions (Codex, Claude Code, SuperGrok) are the signed-in logins of the Text tab runs.
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
  "mammoth-baseten"
)
chat_lanes=(
  "gpt-6-astra gpt-6.1-sol gpt-6.1-terra gpt-6-luna-codex"
  "gpt-6-astra-web gpt-6.1-sol-web gpt-6.1-terra-web gpt-6-luna-codex-web"
  "claude-fable-5-1 claude-opus-5-5 claude-sonnet-5-5"
  "claude-fable-5-1-web claude-opus-5-5-web claude-sonnet-5-5-web"
  "gemini-3.8-flash gemini-4-argon"
  "gemini-3.8-flash-web gemini-4-argon-web"
  "grok-4.7"
  "grok-4.7-web"
  "kimi-k3.1-pro"
  "glm-5.3"
)
echo "$(date -u +%FT%T) start" >> "$L"
pids=()
for lane in "${lanes[@]}"; do
  # shellcheck disable=SC2086
  python3 -B pws/bench.py run $lane >> "$L" 2>&1 & pids+=($!)
done
for lane in "${chat_lanes[@]}"; do
  # shellcheck disable=SC2086
  python3 -B pws/bench.py run --retry-errors $lane >> "$L" 2>&1 & pids+=($!)
done
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
echo "$(date -u +%FT%T) runs done (exit $rc)" >> "$L"
python3 -B pws/bench.py summary >> "$L" 2>&1 || rc=1
echo "$(date -u +%FT%T) end (exit $rc)" >> "$L"
exit $rc
