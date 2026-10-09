./benchmark_ollama.py gemma-4-31B-it \
  --provider vllm \
  --vllm-url http://192.168.1.126:8010 \
  --data questions-v2.sqlite \
  --batch-size 16
