# Project `webplace` (LLM API)

Internal RAG + instructions for **HIS** address normalization and dev tooling.

## Layout

| Path | Role |
|------|------|
| `fluxosLLM/instrucoes-llm.md` | Behavior rules (JSON-only, no placeholders, no sales tone) |
| `bibliotecaConteudoLLM/*.md` | Short contracts / scope text indexed for retrieval |

## After editing markdown

From this repo `featureLLM/` (host venv must use same `chromadb` as Docker — see `requirements.txt`):

```bash
DATABASE_URL=postgresql://llmapi:llmapi_dev@127.0.0.1:5437/llmapi DATA_DIR=./data \
  .venv/bin/python -c "import asyncio; from app.ingest.indexer import run_ingest; asyncio.run(run_ingest('webplace', incremental=False))"
```

Or `POST /ingest` with `{"project_id":"webplace"}` and Bearer token.

## DB project row

Apply / refresh config + sources: `python scripts/seed_webplace.py` with `DATABASE_URL` set (see script header).

## HIS client

Repo `HIS`: set `LLM_PROJECT_ID=webplace`, `LLM_ASK_MODEL=fast`, tune `LLM_STATUS_POLL_MS` / `LLM_ROW_SLEEP_MS` in `.env`. Script: `scripts/llmNormalizeEnderecos.mjs`.
