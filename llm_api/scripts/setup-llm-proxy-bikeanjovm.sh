#!/usr/bin/env bash
# Setup proxy LLM no bikeanjovm: porta 28472 -> upstream API :28471 (Tailscale)
# Use quando itcsVM não consegue TCP via Tailscale.
# itcsVM usa LLM_API_URL=http://10.0.0.55:28472 (IP privado Oracle)
#
# Uso: ./scripts/setup-llm-proxy-bikeanjovm.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIKEANJOVM_IP="${BIKEANJOVM_IP:-136.248.79.126}"
BIKEANJOVM_USER="${BIKEANJOVM_USER:-opc}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

scp -i "$SSH_KEY" "$ROOT/docs/refs/nginx/bikeanjovm.conf" "$BIKEANJOVM_USER@$BIKEANJOVM_IP:/tmp/llm-proxy.conf"

ssh -t -i "$SSH_KEY" "$BIKEANJOVM_USER@$BIKEANJOVM_IP" "
  sudo cp /tmp/llm-proxy.conf /etc/nginx/conf.d/llm-proxy.conf
  sudo nginx -t && sudo systemctl reload nginx
  rm -f /tmp/llm-proxy.conf
  echo '[OK] Proxy LLM ativo em bikeanjovm:28472 -> upstream API :28471'
  echo 'itcsVM: LLM_API_URL=http://10.0.0.55:28472'
"
