# 12 — Operações LLM / RAG (enxuto)

Checklist e pontos que **não** cabem noutros docs. Defaults de modelos e `OLLAMA_*`: [09-model-upgrade.md](./09-model-upgrade.md). Melhorias futuras (reranker, hybrid, etc.): [11-improvements-roadmap.md](./11-improvements-roadmap.md).

**Anterior:** [11-improvements-roadmap.md](./11-improvements-roadmap.md) · **Seguinte:** [01-overview.md](./01-overview.md)

---

## Deploy local (Docker)

Na raiz do repo: `./scripts/deploy_llm.sh` (rebuild + `docker compose up` em `llm_api/`).

O serviço `api` usa `env_file: .env`; o bloco `environment:` do compose **sobrepõe** chaves como `DATABASE_URL` (Postgres interno) e **`OLLAMA_HOST`** (`http://host.docker.internal:11434`) — o `.env` com `127.0.0.1` é para correr a API no host, não dentro do contentor. Precisas de `llm_api/.env` no disco.

**Alinhar `.env` com o exemplo** (mantém tokens e chaves extra): em `llm_api/`, `python3 scripts/merge_env_from_example.py`.

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
