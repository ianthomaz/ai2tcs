# 12 — Operações LLM / RAG (enxuto)

Checklist e pontos que **não** cabem noutros docs. **Novo cliente / chave API:** [02-api-integration.md § 1.3](./02-api-integration.md#13-onboarding-e-chave-api-por-projecto). Defaults de modelos e `OLLAMA_*`: [09-model-upgrade.md](./09-model-upgrade.md). Melhorias futuras: [11-improvements-roadmap.md](./11-improvements-roadmap.md).

**Anterior:** [11-improvements-roadmap.md](./11-improvements-roadmap.md) · **Seguinte:** [01-overview.md](./01-overview.md)

---

## Deploy local (Docker)

Na raiz do repo: `./scripts/deploy_llm.sh` (rebuild + `docker compose up` em `llm_api/`).

**Reload sem rebuild:** se só mudaste código Python ou `.env`, evita `--build` (rebuild pesado pode derrubar Docker Desktop). Preferir:

```bash
cd llm_api
docker compose up -d --no-build --force-recreate api
```

O serviço `api` usa `env_file: .env`; o bloco `environment:` do compose **sobrepõe** chaves como `DATABASE_URL` (Postgres interno) e **`OLLAMA_HOST`** (`http://host.docker.internal:11434`) — o `.env` com `127.0.0.1` é para correr a API no host, não dentro do contentor. Precisas de `llm_api/.env` no disco.

**Alinhar `.env` com o exemplo** (mantém tokens e chaves extra): em `llm_api/`, `python3 scripts/merge_env_from_example.py`.

### Flags RAG por projecto

Globais em `.env` (`RAG_HYBRID_ENABLED`, `RAG_RERANK_ENABLED`) são **fallback**. Cada projecto pode sobrepor em `config_json.policies`:

| Campo | Efeito |
|-------|--------|
| `rag_hybrid_enabled` | `true` / `false` / omitido (usa global) |
| `rag_rerank_enabled` | idem |

Chat creative (ex.: `aiclaudia`) costuma ter ambos `false` e `rag_mode: disabled`. FAQ vendas (ex.: `estudosmobi`) mantém `rag_mode: required` e flags `true`.

---

## Ingest e chunks skipped

Durante `POST /ingest`, falhas Ollama (ex.: HTTP 500) fazem **skip** de chunks individuais (vector zero + log `Skipping chunk`). No fim do job, logs e resposta incluem `indexed` e `skipped`.

Se **`skipped` > 0**, re-correr ingest quando Ollama estiver estável:

```bash
curl -X POST "$LLM_API_URL/ingest" \
  -H "Authorization: Bearer $LLM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"estudosmobi"}'
```

---

## Apps que consomem a API

Em regra **sem mudança** se usam aliases (`smart`, `reasoner`, …) e `project_id`. Só mexem se fixaram nome cru de modelo Ollama e o deixaste de ter no servidor.

---

## Embeddings

- Índice Chroma: **disco** da instância; `git pull` não apaga ingest.
- Trocar `embedding_model` ⇒ **dimensão diferente** ⇒ **re-ingest** desse projecto.
- **Onde editar:** dashboard → projecto → *Modelo de embedding*; ou `PUT /projects/{id}` (`config_json`); ou BD. Não há env global que substitua o campo por projecto.

---

## Referências

| Tema | Doc |
|------|-----|
| `config_json` completo | [08-project-config.md](./08-project-config.md) |
| Contratos HTTP | [02-api-integration.md](./02-api-integration.md) |
