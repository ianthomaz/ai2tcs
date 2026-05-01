# 05 — Arquitetura

Camadas e fluxo de dados. Pastas e fluxo de dev: [04-developer-guide.md](./04-developer-guide.md).

---

## Camadas

1. **Cliente HTTP** — aplicações externas ou serviços na mesma tailnet; contrato em [02-api-integration.md](./02-api-integration.md).
2. **API FastAPI** (`llm_api/app/`) — rotas síncronas e orquestração; registo de projetos; parte do trabalho pesado delega a **jobs**.
3. **Worker** (`app/jobs/worker.py`) — fila de jobs: RAG + chamadas ao modelo; conversa com **Ollama** e índices.
4. **Dados** — **PostgreSQL** (Prisma): projetos, conversas, chaves, domínio EDU, etc.; **Chroma** (ou equivalente configurado) para embeddings / retrieval conforme o desenho actual.
5. **Modelo** — **Ollama** no host (ou remoto); aliases de modelo (`fast`, `smart`, `compact`, `reasoner`) mapeados por env — ver [09-model-upgrade.md](./09-model-upgrade.md).

---

## Rede e exposição

**127.0.0.1** no **llm_server**; **tailnet** (Tailscale Serve); ou **proxy/nginx** / **túnel SSH** se TCP entre peers for instável. [refs/operacao-tailscale.md](./refs/operacao-tailscale.md); [refs/nginx/](./refs/nginx/).

---

## Evolução

[`llm_api/UPGRADES.md`](../llm_api/UPGRADES.md). Plano histórico: [10-historical-router-plan.md](./10-historical-router-plan.md).

---

**Anterior:** [04-developer-guide.md](./04-developer-guide.md) · **Seguinte:** [06-edu-contract.md](./06-edu-contract.md)
