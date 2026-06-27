#!/usr/bin/env bash
# SSH reverse tunnel: machine where the LLM API runs -> itcsVM1 (or other host).
# Exposes local API (127.0.0.1:28471) on the remote as 127.0.0.1:28471.
#
# Use when the remote cannot reach this host via Tailscale TCP (DERP-only, TCP fails).
# Run on the API host. On the remote after tunnel: LLM_API_URL=http://127.0.0.1:28471
#
# Required env (set in shell or source llm_api/.env before running):
#   ITCSVM1_HOST    — SSH host (default: itcsVM1; or public IP)
#   ITCSVM1_USER    — SSH user on remote (default: opc)
#   SSH_KEY         — path to private key (default: $HOME/.ssh/itcsvm_key)
#
# Optional: Oracle / firewall must allow this machine's IP to remote:22.
#
# Usage: ./scripts/llm-tunnel-api-host-to-itcsvm.sh
# Press Ctrl+C to stop.

set -e
ITCSVM1_HOST="${ITCSVM1_HOST:-${ITCSVM_IP:-itcsVM1}}"
ITCSVM1_USER="${ITCSVM1_USER:-${ITCSVM_USER:-opc}}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/itcsvm_key}"

if [[ ! -f "$SSH_KEY" ]]; then
  echo "Error: SSH key not found: $SSH_KEY" >&2
  exit 1
fi

echo "Starting tunnel: ${ITCSVM1_USER}@${ITCSVM1_HOST}:28471 -> 127.0.0.1:28471 (local LLM API)"
echo "On remote: LLM_API_URL=http://127.0.0.1:28471"
echo "Press Ctrl+C to stop."
echo ""

exec ssh -R 28471:127.0.0.1:28471 \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -N \
  -i "$SSH_KEY" \
  "$ITCSVM1_USER@$ITCSVM1_HOST"
