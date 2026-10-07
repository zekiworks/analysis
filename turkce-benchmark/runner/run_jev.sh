JEV_API_KEY="$(cat "$HOME/code/jev/key")" ./benchmark_ollama.py jev-1.13.0 \
  --provider jev \
  --data questions-v2.sqlite \
  --timeout 30
