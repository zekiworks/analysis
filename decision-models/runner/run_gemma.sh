./benchmark_ollama.py gemma-4-31B-it \
  --provider vllm \
  --vllm-url "${GEMMA_URL:?set GEMMA_URL to the Gemma vLLM server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --batch-size 16
