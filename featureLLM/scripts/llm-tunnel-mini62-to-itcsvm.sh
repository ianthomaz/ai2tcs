#!/usr/bin/env bash
# SSH reverse tunnel: mini62 -> itcsVM (public IP)
# Makes LLM API (mini62:28471) available on itcsVM as 127.0.0.1:28471
#
# Use when itcsVM cannot reach mini62 via Tailscale TCP (DERP-only, TCP fails).
# Run on mini62. webplacecc on itcsVM uses LLM_API_URL=http://127.0.0.1:28471
#
# Requires:
#   - Oracle Cloud: allow mini62 public IP on itcsVM inbound port 22
#   - mini62 has itcsvm_key (or SSH_KEY) for itcsVM
#   - API running on mini62:28471
#
# Usage: ./scripts/llm-tunnel-mini62-to-itcsvm.sh
# Press Ctrl+C to stop.

set -e
ITCSVM_IP="${ITCSVM_IP:-168.138.253.160}"
ITCSVM_USER="${ITCSVM_USER:-opc}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/itcsvm_key}"

if [[ ! -f "$SSH_KEY" ]]; then
  echo "Error: SSH key not found: $SSH_KEY" >&2
  exit 1
fi

echo "Starting tunnel: itcsVM:28471 -> mini62:28471 (LLM API)"
echo "Run on itcsVM: LLM_API_URL=http://127.0.0.1:28471"
echo "Press Ctrl+C to stop."
echo ""

exec ssh -R 28471:127.0.0.1:28471 \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -N \
  -i "$SSH_KEY" \
  "$ITCSVM_USER@$ITCSVM_IP"
