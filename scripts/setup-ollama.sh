#!/usr/bin/env bash
# Pull the LLM + embedding models NeuraSWE needs.
set -euo pipefail

CHAT_MODEL="${OLLAMA_CHAT_MODEL:-deepseek-coder-v2:16b}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

echo "Pulling chat model: $CHAT_MODEL"
if command -v docker >/dev/null && docker compose ps ollama >/dev/null 2>&1; then
  docker compose exec ollama ollama pull "$CHAT_MODEL"
  docker compose exec ollama ollama pull "$EMBED_MODEL"
else
  ollama pull "$CHAT_MODEL"
  ollama pull "$EMBED_MODEL"
fi
echo "Done."
