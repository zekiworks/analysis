#!/usr/bin/env bash
# Refresh runner/ (and the metric code at the repository root) from a benchmark workspace:
#
#   ./sync_runner.sh WORKSPACE
#
# WORKSPACE is the folder holding benchmark_ollama.py and the run scripts. Copies the runner's Python
# files, the run scripts behind the published runs and the cascade plans in pipeline/; keeps
# runner/README.md and runner/servers/ (the self-hosted server wrappers, which live outside the
# workspace). Stops without changing anything when a file is missing or a copied file contains a
# local path.
set -euo pipefail
umask 022

if [ $# -ne 1 ] || [ ! -f "${1:-}/benchmark_ollama.py" ]; then
  sed -n '2,9p' "$0" >&2
  exit 2
fi
workspace=$1
repo=$(cd "$(dirname "$0")" && pwd)

python_files=(
  benchmark_ollama.py benchmark_metrics.py cascade_pipeline.py
  audit_questions.py extract_questions.py extract_questions_text.py vision_ocr.py osym_bank.py repair_questions.py
  test_benchmark_metrics.py test_benchmark_ollama.py
)
# Run scripts behind no published run: the PEGEM ALES extraction, an Ollama run on the second bank, the
# two Gemini 3.1 Pro (preview) runs, taken off the page because a preview model can be withdrawn, and
# Perplexity's Decider v1.1 on our GPUs (the page compares v1.1 with v1 through Perplexity's API).
skipped_scripts=(run_generate_questions.sh run_quiz.sh run_gemini_pro.sh run_gemini_pro_high.sh run_pplx_decider.sh)

staging=$(mktemp -d "$repo/.runner.XXXXXX")
trap 'rm -rf "$staging"' EXIT
chmod 755 "$staging"

for name in "${python_files[@]}"; do
  if head -n 1 "$workspace/$name" | grep -q '^#!'; then mode=755; else mode=644; fi
  install -m "$mode" "$workspace/$name" "$staging/$name"
done

scripts=()
for path in "$workspace"/run_*.sh; do
  name=$(basename "$path")
  if [[ " ${skipped_scripts[*]} " == *" $name "* ]]; then
    continue
  fi
  install -m 755 "$path" "$staging/$name"
  scripts+=("$name")
done

mkdir -m 755 "$staging/pipeline"
for path in "$workspace"/pipeline/*.json "$workspace"/pipeline/*.txt; do
  install -m 644 "$path" "$staging/pipeline/$(basename "$path")"
done

if [ -f "$repo/runner/README.md" ]; then
  install -m 644 "$repo/runner/README.md" "$staging/README.md"
fi
if [ -d "$repo/runner/servers" ]; then
  cp -a "$repo/runner/servers" "$staging/servers"
fi

if grep -rlE '/(home|Volumes)|T[7]' "$staging" >&2; then # local paths; the pattern doesn't match itself
  echo "the files above contain a local path; nothing was changed" >&2
  exit 1
fi

rm -rf "$repo/runner"
mv "$staging" "$repo/runner"
cp "$workspace/benchmark_metrics.py" "$repo/benchmark_metrics.py" # keeps the file's mode

echo "runner/: ${#python_files[@]} Python files, ${#scripts[@]} run scripts, $(ls "$repo/runner/pipeline" | wc -l) pipeline files"
echo "run scripts: ${scripts[*]}"
echo "left out: ${skipped_scripts[*]}"
