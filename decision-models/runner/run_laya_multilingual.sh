./benchmark_ollama.py laya-multilingual \
  --provider laya \
  --jev-url "${LAYA_MULTILINGUAL_URL:?set LAYA_MULTILINGUAL_URL to the multilingual Laya server, as http://HOST:PORT}" \
  --data questions-v2.sqlite \
  --timeout 30
