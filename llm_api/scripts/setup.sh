#!/usr/bin/env bash
# Setup completo: venv, deps, .env, migração Postgres, seed bikeanjoall_2026.
# Uso: ./scripts/setup.sh [DATABASE_URL]
# Ex.: ./scripts/setup.sh
#      ./scripts/setup.sh postgresql://user:pass@localhost:5432/llmapi
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

echo "[1/8] Python"
# Prefer 3.12 (chromadb has issues with 3.14)
PYTHON=
for p in python3.12 python3.11 python3; do
  if command -v "$p" &>/dev/null; then
    PYTHON="$p"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Erro: python3 não encontrado."
  exit 1
fi
PY_VER=$($PYTHON -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')
echo "  $PYTHON $PY_VER"

echo "[2/8] Venv e dependências"
if [ ! -d .venv ]; then
  $PYTHON -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
echo "  OK"

echo "[3/8] .env"
if [ ! -f .env ]; then
  cp .env.example .env
  TOKEN=$(openssl rand -hex 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(24))")
  if grep -q 'LLM_API_TOKEN=' .env; then
    sed -i.bak "s/^LLM_API_TOKEN=.*/LLM_API_TOKEN=$TOKEN/" .env
  else
    echo "LLM_API_TOKEN=$TOKEN" >> .env
  fi
  echo "  Criado .env com token gerado."
else
  echo "  .env já existe; LLM_API_TOKEN e demais variáveis mantidos (token estável para clientes)."
fi
if [ -n "$1" ]; then
  if grep -q '^DATABASE_URL=' .env; then
    sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=$1|" .env
  else
    echo "DATABASE_URL=$1" >> .env
  fi
  echo "  DATABASE_URL definido."
  export DATABASE_URL="$1"
fi
set -a
source .env 2>/dev/null || true
set +a

echo "[4/8] Pastas data/ e logs/"
mkdir -p data logs
echo "  OK"

echo "[5/8] Banco PostgreSQL (migrações)"
export PYTHONPATH="$ROOT"
# Apply all migrations in order
MIGRATION_FILES="$ROOT/prisma/migrations/20250306000000_init/migration.sql $ROOT/prisma/migrations/20250306100000_add_conversation_history/migration.sql $ROOT/prisma/migrations/20250306200000_add_user_profile_and_conv_summary/migration.sql $ROOT/prisma/migrations/20250306300000_add_job_user_context/migration.sql"
MIGRATION_FILE="$ROOT/prisma/migrations/20250306000000_init/migration.sql"
if [ ! -f "$MIGRATION_FILE" ]; then
  echo "  Erro: migração não encontrada em $MIGRATION_FILE"
  exit 1
fi
export MIGRATION_FILES
if ! .venv/bin/python -c "
import asyncio
import os
import re
import sys
import asyncpg

async def run():
    url = os.environ.get('DATABASE_URL', 'postgresql://localhost:5432/llmapi')
    try:
        conn = await asyncpg.connect(url)
    except Exception as e:
        print('  Erro ao conectar:', e, file=sys.stderr)
        print('  Crie o banco (ex.: createdb llmapi) e/ou ajuste DATABASE_URL no .env', file=sys.stderr)
        sys.exit(1)
    mig_paths = os.environ.get('MIGRATION_FILES', '').split()
    for mig_path in mig_paths:
        if not mig_path or not os.path.isfile(mig_path):
            print(f'  Migração não encontrada: {mig_path}', file=sys.stderr)
            continue
        with open(mig_path) as f:
            migration = f.read()
        parts = re.split(r';\s*\n', migration)
        statements = []
        for p in parts:
            s = p.strip()
            if not s or s.startswith('--'):
                continue
            if not s.endswith(';'):
                s += ';'
            statements.append(s)
        for stmt in statements:
            try:
                await conn.execute(stmt)
            except Exception as e:
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    pass
                else:
                    print(f'  Aviso ao aplicar migração: {e}', file=sys.stderr)
        print(f'  Migração aplicada: {os.path.basename(os.path.dirname(mig_path))}')
    await conn.close()

asyncio.run(run())
"; then
  echo "  Falha ao aplicar migrações. Verifique DATABASE_URL e se o banco existe."
  exit 1
fi

echo "[6/8] Seed bikeanjoall_2026"
.venv/bin/python scripts/seed_bikeanjoall.py
echo "  OK"

echo "[7/8] Ingest bikeanjoall_2026 (biblioteca ativa para RAG)"
set -a
source .env 2>/dev/null || true
set +a
export PYTHONPATH="$ROOT"
if .venv/bin/python -c "
import asyncio
import os
import sys
from app.registry import get_project
from app.ingest.indexer import run_ingest

async def main():
    proj = await get_project('bikeanjoall_2026')
    if not proj or not (proj.get('sources') or []):
        print('  Aviso: BIKEANJOALL_2026_SOURCES não definido ou projeto sem sources; ingest ignorado.', file=sys.stderr)
        return
    result = await run_ingest('bikeanjoall_2026', incremental=False)
    docs = result.get('documents', 0)
    chunks = result.get('chunks', 0)
    if result.get('error'):
        print(f'  Aviso: ingest falhou: {result.get(\"error\")}', file=sys.stderr)
        return
    print(f'  Indexados {docs} documentos, {chunks} chunks.')

asyncio.run(main())
"; then
  echo "  OK"
else
  echo "  Aviso: ingest falhou ou sem sources; defina BIKEANJOALL_2026_SOURCES no .env e rode: .venv/bin/python -c \"import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('bikeanjoall_2026'))\""
fi

echo "[8/8] Pronto."
echo ""
echo "Próximos passos:"
echo "  1. Ollama: brew install ollama && ollama pull gemma3:12b && ollama pull qwen2.5:7b-instruct && ollama pull llama3:8b && ollama pull deepseek-r1:14b && ollama pull mxbai-embed-large"
echo "  2. No .env: BIKEANJOALL_2026_SOURCES=/caminho/para/bibliotecaConteudoLLM (para seed + ingest com conteúdo real)"
echo "  3. Subir API: ./scripts/run_api.sh"
echo "  4. Expor via Tailscale: ./scripts/tailscale_serve.sh"
echo ""
echo "Se perder o seed ou a biblioteca: rode de novo ./scripts/setup.sh (mantém .env) ou apenas:"
echo "  .venv/bin/python scripts/seed_bikeanjoall.py && .venv/bin/python -c \"import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('bikeanjoall_2026'))\""
echo ""
