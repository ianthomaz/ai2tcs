#!/usr/bin/env bash
# Run LLM API (port 28471). Load .env from featureLLM root.
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
export PYTHONPATH=.
PYTHON=python
if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
fi
# API_HOST=0.0.0.0 in .env to accept tailnet IP access (http://<mac-ip>:28471 from other nodes)
exec "$PYTHON" -m uvicorn app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-28471}"
