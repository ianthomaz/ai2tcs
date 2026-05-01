#!/usr/bin/env bash
# Deploy featureLLM on THIS machine: rebuild and restart the API container.
# Run from anywhere: ./scripts/deploy_llm.sh (from ai2tcs repo root) or bash scripts/deploy_llm.sh
# Requires: Docker, docker compose, repo at expected path (script resolves featureLLM/ next to scripts/).

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FLM="$REPO_ROOT/featureLLM"

if [[ ! -f "$FLM/docker-compose.yml" ]]; then
  echo "error: featureLLM/docker-compose.yml not found at $FLM" >&2
  exit 1
fi

cd "$FLM"
echo "Deploy featureLLM (local Docker Compose)"
echo "========================================="
docker compose up -d --build api
echo "Done. API: http://127.0.0.1:28471"
