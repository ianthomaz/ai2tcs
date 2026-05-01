#!/usr/bin/env bash
# Setup proxy LLM no pcvelho: porta 28472 -> mini62:28471
# Use quando itcsVM não consegue conectar diretamente ao Mac (DERP/TCP).
# Clientes usam LLM_API_URL=http://100.89.195.56:28472
#
# Uso: ./scripts/setup-llm-proxy-pcvelho.sh
# (será pedida a senha sudo no pcvelho)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PCVELHO_IP="${PCVELHO_IP:-100.89.195.56}"
PCVELHO_USER="${PCVELHO_USER:-itcs}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_macmini}"

scp -i "$SSH_KEY" "$ROOT/docs/nginx-llm-proxy-pcvelho.conf" "$PCVELHO_USER@$PCVELHO_IP:/tmp/llm-proxy.conf"

ssh -t -i "$SSH_KEY" "$PCVELHO_USER@$PCVELHO_IP" "
  sudo cp /tmp/llm-proxy.conf /etc/nginx/conf.d/llm-proxy.conf
  sudo nginx -t && sudo systemctl reload nginx
  rm -f /tmp/llm-proxy.conf
  echo '[OK] Proxy LLM ativo em pcvelho:28472 -> mini62:28471'
"
