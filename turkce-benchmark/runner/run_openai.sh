./benchmark_ollama.py gpt-6-astra \
  --provider openai \
  --openai-reasoning low \
  --data questions-v2.sqlite \
  --batch-size 16 \
  --timeout 600
