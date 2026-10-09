#!/usr/bin/env bash
# Step 3.5: the frontier runs and the best decision models on the fresh 2026-TYT Türkçe questions,
# with the same settings as their runs on the book. Run it after the 40 questions have been checked
# (fresh/review/review.html, then repair_questions.py apply). Everything stays in fresh/; publish
# only aggregates. Open-Jev needs open-jev.service on 192.168.1.126:8791; Erk-14B and Qwen3-14B need
# their vLLM containers on ports 8893 and 8892 (README, "Run against vLLM").
set -euo pipefail

bank=(--data fresh/tyt-2026.sqlite --database fresh/results.sqlite --output fresh/results.md)

./benchmark_ollama.py gpt-6-astra --provider openai --openai-reasoning low --batch-size 16 --timeout 600 "${bank[@]}"
./benchmark_ollama.py claude-opus-5-5 --provider claude --claude-effort low --batch-size 16 --timeout 600 "${bank[@]}"
./benchmark_ollama.py claude-sonnet-5-5 --provider claude --claude-effort high --batch-size 16 --timeout 600 "${bank[@]}"
./benchmark_ollama.py pplx-decider-v1-27b --provider perplexity --timeout 30 "${bank[@]}"
JEV_API_KEY="$(cat "$HOME/code/jev/key")" ./benchmark_ollama.py jev-1.13.0 --provider jev --timeout 30 "${bank[@]}"
./benchmark_ollama.py d1:free --provider liquid --timeout 30 "${bank[@]}"
./benchmark_ollama.py open-jev-27b-v1.1 --provider open-jev --timeout 30 "${bank[@]}"
./benchmark_ollama.py erk-14b --provider vllm --vllm-url http://127.0.0.1:8893 --batch-size 16 "${bank[@]}"
./benchmark_ollama.py qwen3-14b --provider vllm --vllm-url http://127.0.0.1:8892 --batch-size 16 "${bank[@]}"
