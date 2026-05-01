#!/usr/bin/env bash
# Script de desenvolvimento: sobe postgres, aplica migrations, roda API com reload.
# Uso: ./scripts/dev.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "==> Subindo PostgreSQL via Docker Compose..."
docker compose up -d postgres

echo "==> Aguardando PostgreSQL ficar pronto..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U llmapi > /dev/null 2>&1; then
        echo "    PostgreSQL pronto!"
        break
    fi
    sleep 1
done

echo "==> Aplicando migrations..."
DATABASE_URL="postgresql://llmapi:llmapi_dev@localhost:5437/llmapi" npx prisma migrate deploy --schema=prisma/schema.prisma

echo "==> Iniciando API com auto-reload..."
DATABASE_URL="postgresql://llmapi:llmapi_dev@localhost:5437/llmapi" \
    uvicorn app.main:app --host 127.0.0.1 --port 28471 --reload
