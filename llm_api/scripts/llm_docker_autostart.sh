#!/bin/bash
# Run after login so the LLM stack is up even if Docker cleared state.
# Used by launchd (com.itcs.llmapi.docker.plist). Production = Docker only.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DOCKER_BIN="$(command -v docker)"
if [ -z "${DOCKER_BIN}" ]; then
  echo "docker not found in PATH=$PATH" >&2
  exit 127
fi
# Wait for Docker daemon (Docker Desktop can lag a few seconds after login)
for _ in $(seq 1 45); do
  if "$DOCKER_BIN" info >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  echo "Docker daemon not ready after wait" >&2
  exit 1
fi
# No --build here: login should be fast; rebuild manually when you deploy.
exec "$DOCKER_BIN" compose up -d
