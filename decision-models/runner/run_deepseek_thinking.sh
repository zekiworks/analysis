./benchmark_ollama.py deepseek-v4.1-flash \
  --provider vllm \
  --vllm-thinking \
  --concurrency 8 \
  --vllm-url http://192.168.1.126:8010 \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 3600
