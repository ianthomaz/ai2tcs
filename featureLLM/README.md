# LLM API (local, 24/7, Tailscale)

API FastAPI para LLM local com RAG multi-projeto. Porta **28471**. Planejamento em `00_PLANEJAMENTO_LLM_LOCAL.md`.

**Integração (outros projetos / clientes HTTP):** ver `docs/MANUAL_INTEGRACAO.md` e `docs/INDEX.md`. NF Extract (multipart `/nfExtract`): ficheiro na raiz do clone ai2tcs, `../docs/ManualNF_Extract`.

**Deploy em produção:** só nesta máquina, via **Docker Compose**. Na raiz deste repositório (ai2tcs): `./scripts/deploy_llm.sh` — corre `docker compose up -d --build api` em `featureLLM/`. Não usar `run_api.sh` nem launchd para produção.

**Autostart (Docker):** `docker-compose.yml` usa `restart: unless-stopped` em `postgres` e `api`. Ative no Docker Desktop *Open Docker Desktop when you sign in*. Opcional: `launchd/com.itcs.llmapi.docker.plist.example` + `scripts/llm_docker_autostart.sh` (sobe o stack no login; ver comentários no plist). Descarregue o plist antigo `com.itcs.llmapi.plist` se ainda usar uvicorn nativo — conflito na porta 28471.

## Pré-requisitos

- **Python 3.12 ou 3.11** (recomendado 3.12; ChromaDB tem problemas com 3.14)
- PostgreSQL (local ou Docker)
- Ollama (modelos: `qwen2.5:14b-instruct`, `nomic-embed-text`)
- **Áudio / STT:** dependência Python `faster-whisper`; no host ou container da API é necessário **ffmpeg** (já instalado na imagem Docker). Modelos Whisper ficam em `data/whisper_models` por defeito.
- Tailscale (para acesso remoto)

## Setup rápido (script único)

**Pré-requisito:** PostgreSQL rodando e banco criado. Sem Postgres local, use Docker: `docker run -d --name llmapi_postgres -e POSTGRES_USER=llmapi -e POSTGRES_PASSWORD=llmapi -e POSTGRES_DB=llmapi -p 5437:5432 postgres:16-alpine` e depois `./scripts/setup.sh 'postgresql://llmapi:llmapi@localhost:5437/llmapi'`. (Migração manual: `docker exec -i llmapi_postgres psql -U llmapi -d llmapi < prisma/migrations/20250307000000_consolidated/migration.sql`.)

```bash
cd featureLLM
./scripts/setup.sh
# Ou passando DATABASE_URL:
./scripts/setup.sh 'postgresql://user:password@localhost:5432/llmapi'
```

O script faz: venv, dependências, `.env` (com token gerado), pastas `data/` e `logs/`, migração Postgres (via Python, sem Node), seed do projeto `bikeanjoall_2026`. No final imprime os próximos passos (Ollama, Tailscale, run_api).

### Setup manual (alternativa)

Se preferir fazer passo a passo: venv + `pip install -r requirements.txt`, copiar `.env.example` para `.env`, aplicar `prisma/migrations/.../migration.sql` no Postgres, rodar `python scripts/seed_bikeanjoall.py`.

### Configurar fontes do bikeanjoall_2026

As bibliotecas ficam **dentro das pastas de cada projeto**. Para o bikeanjoall_2026: conteúdo de texto do site institucional (pasta do projeto) e PDFs (quando tiver).

```bash
# No .env ou antes de rodar: caminhos das pastas a indexar (separados por vírgula)
# Ex.: BIKEANJOALL_2026_SOURCES=/path/to/2026b_bikeanjoAll_dbPrisma/bibliotecaConteudoLLM
export BIKEANJOALL_2026_SOURCES="/caminho/para/bikeanjoall_2026/content"
python scripts/seed_bikeanjoall.py
```

O **setup completo** (`./scripts/setup.sh`) já faz seed **e** ingest: a biblioteca fica ativa para o RAG. Se em um rebuild você perder o seed ou a biblioteca, rode de novo o setup (o `.env` é mantido) ou apenas:

```bash
source .env && .venv/bin/python scripts/seed_bikeanjoall.py && .venv/bin/python -c "import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('bikeanjoall_2026'))"
```

## Rodar a API (produção: use Docker)

Em produção, suba sempre com Docker (mesmo host = mini62):

```bash
cd featureLLM
docker compose up -d
```

A API escuta em `http://127.0.0.1:28471`. Health: `curl -H "Authorization: Bearer $LLM_API_TOKEN" http://127.0.0.1:28471/health`.

**Token:** O `LLM_API_TOKEN` é estável: gerado uma vez no primeiro setup e mantido em `.env`. Use o mesmo valor em todos os clientes (zapzap, servidores); o setup não regera o token em deploys posteriores.

## Expor via Tailscale (rede interna, sem Funnel)

No Mac onde a API roda:

```bash
./scripts/tailscale_serve.sh
```

A API fica acessível **só na sua tailnet** (ex.: `https://<seu-mac>.ts.net/`). Não usar Funnel. Detalhes: `docs/OPERACAO_TAILSCALE.md`.

## Rodar fora do container (só desenvolvimento/teste)

Para testes locais sem Docker: `source .venv/bin/activate && ./scripts/run_api.sh`. Não usar para produção; em produção usar apenas Docker (ver acima).

## Estrutura

- `app/` – FastAPI, registry, ingest, RAG, jobs (worker), STT (`app/stt/` — `/audio/*`), EDU (`app/edu/` — `/edu/*`; contrato em `docs/EDU_API_CONTRACT.md`)
- `prisma/` – schema e migrações Postgres
- `scripts/` – setup (implementação única), run_api, seed, tailscale_serve
- `docs/` – **Manual de uso da API:** [docs/MANUAL_INTEGRACAO.md](docs/MANUAL_INTEGRACAO.md) (§ 3.8: `/edu/chat` e resposta estruturada para toggles Pinyin/Tradução). Índice: [docs/INDEX.md](docs/INDEX.md). Contrato EDU: [docs/EDU_API_CONTRACT.md](docs/EDU_API_CONTRACT.md). Operação Tailscale: docs/OPERACAO_TAILSCALE.md
- `data/<project_id>/chroma` – índices vetoriais (não versionado)
