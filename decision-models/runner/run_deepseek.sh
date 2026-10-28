./benchmark_ollama.py deepseek-v4.1-flash \
  --provider vllm \
  --vllm-url "${DEEPSEEK_URL:?set DEEPSEEK_URL to the DeepSeek vLLM server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --batch-size 16
