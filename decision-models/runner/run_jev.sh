JEV_API_KEY="$(cat "${JEV_KEY_FILE:?set JEV_KEY_FILE to the file holding the Jev API key}")" ./benchmark_ollama.py jev-1.13.0 \
  --provider jev \
  --data questions-v2.sqlite \
  --timeout 30
