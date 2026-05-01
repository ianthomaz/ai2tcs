#!/usr/bin/env bash
# Run after login so the LLM stack is up even if Docker cleared state.
# Used by launchd (com.itcs.llmapi.docker.plist). Production = Docker only.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Wait for Docker daemon (Docker Desktop can lag a few seconds after login)
for _ in $(seq 1 45); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
# No --build here: login should be fast; rebuild manually when you deploy.
exec docker compose up -d
